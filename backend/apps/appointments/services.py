"""Appointment domain services (plan §5, S §A8).

This module is the only place the booking lifecycle is written:

- `book_appointment` validates the slot against the server-generated grid,
  creates the hold + `PaymentOrder` in one transaction and honours the
  `Idempotency-Key`;
- `reschedule_appointment` atomically retires the original (`RESCHEDULED`)
  and creates the new hold;
- `cancel/confirm/complete/no-show` shrink-wrap the state machine behind the
  business rules (cancellation policy window, payment required for paid
  services);
- `expire_stale_holds` + the Celery sweep free expired holds (plan §5 layer 3).

Every public entry point runs in `transaction.atomic()` and locks rows with
`select_for_update`: concurrent writes lose at the database (the exclusion
constraint is the *last* line), not in application memory. `now` is injectable
so the S §A8 time-bound tests can pin the clock without freezegun.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from apps.appointments.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentActor,
    AppointmentStatus,
    CreatedVia,
)
from apps.appointments.state import transition as apply_transition
from apps.appointments.state import write_initial_history
from apps.payments.models import PaymentOrder
from apps.scheduling.service import SlotService
from apps.services.models import Service, ServiceStatus
from common.exceptions import (
    ConflictError,
    HoldLimitReachedError,
    InvalidStateTransitionError,
    ServiceDisabledError,
    SlotOccupiedError,
    SlotUnavailableError,
)
from common.models import IdempotencyRecord


def _tz(zone: str | None) -> ZoneInfo:
    return ZoneInfo(zone or "UTC")


def _hold_until(now: datetime) -> datetime:
    return now + timedelta(minutes=int(getattr(settings, "SLOT_HOLD_MINUTES", 10)))


def _cancellation_window() -> timedelta:
    hours = int(getattr(settings, "CANCELLATION_POLICY_MIN_HOURS", 0))
    return timedelta(hours=hours)


def _assert_hold_budget(customer: Any) -> None:
    """Refuse a booking that would exceed the customer's unpaid-hold budget.

    A throttle bounds how *fast* holds are created; this bounds how many are
    left dangling. A patient client can otherwise occupy a whole week of slots
    with holds it never intends to pay for (S §A7 "slot-hold abuse"). Only
    `PENDING_PAYMENT` counts - a confirmed appointment is not inventory abuse -
    and holds lapse on their own, so the budget frees itself.
    """
    cap = int(getattr(settings, "MAX_ACTIVE_HOLDS_PER_CUSTOMER", 5))
    if cap <= 0:
        return
    open_holds = (
        Appointment.objects.unfiltered()
        .filter(customer_id=getattr(customer, "pk", customer))
        .filter(status=AppointmentStatus.PENDING_PAYMENT)
        .count()
    )
    if open_holds >= cap:
        raise HoldLimitReachedError()


def parse_start_at(raw: object, tenant: Any) -> datetime:
    """Normalise a booking `start_at` into an aware UTC datetime.

    Accepts either an ISO-8601 string or a datetime, so the same function
    serves the request boundary (a raw body string) and the already-parsed
    value a serializer hands down. Naive inputs are interpreted in the tenant
    timezone, so a client sending "2026-10-15T11:30" means 11:30 *at the
    practice*. Sub-minute noise is truncated (slots are minute-granular) and
    the result is normalised to UTC for storage (plan §3: "Timestamps stored
    UTC").
    """
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as err:
            raise ValueError("start_at must be an ISO-8601 datetime.") from err
    else:
        raise ValueError("start_at must be an ISO-8601 datetime.")
    if dt.tzinfo is None:
        zone = getattr(tenant, "timezone", None) or "UTC"
        try:
            dt = dt.replace(tzinfo=_tz(zone))
        except (ZoneInfoNotFoundError, ValueError, KeyError) as err:
            raise ValueError("The tenant timezone is not a valid IANA zone.") from err
    return dt.replace(second=0, microsecond=0).astimezone(UTC)


def active_windows(
    provider: Any,
    *,
    day: date,
    zone: str | None,
    exclude_pk: Any | None = None,
    now: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """Occupied spans for `provider` on `day`, buffer included.

    Blocks/holds are returned as `(start, end + buffer_after)` so a following
    service's slots are never offered during another booking's turnaround
    (plan §3.1). A `PENDING_PAYMENT` hold whose `slot_hold_expires_at` is in
    the past is treated as free - plan §5 layer 1 subtracts *expired* holds
    from the grid even before the sweep task catches up.
    """
    tz = _tz(zone)
    day_start = datetime.combine(day, dtime.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    at = (now or timezone.now()).astimezone(UTC)

    rows = (
        Appointment.objects.unfiltered()
        .filter(
            provider_id=provider.pk,
            status__in=ACTIVE_STATUSES,
            start_at__lt=day_end.astimezone(UTC),
        )
        .exclude(
            status=AppointmentStatus.PENDING_PAYMENT,
            slot_hold_expires_at__lte=at,
        )
        .select_related("service")
    )
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)

    spans: list[tuple[datetime, datetime]] = []
    for row in rows:
        end = row.end_at + timedelta(minutes=row.service.buffer_after_minutes)
        spans.append((row.start_at, end))
    return spans


def validate_slot(
    service: Service,
    start_utc: datetime,
    tenant: Any,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Re-run the server-side slot grid and require an exact match.

    A client-supplied time is never booked as-is: it must be *one of the
    generated slots*, which already folds in lead time, look-ahead, blocked
    windows and other bookings (plan §5 layer 1 + "Slot must exactly match a
    server-generated slot", S §A8). Returns `(start, end)` in UTC.
    """
    if str(service.status) != ServiceStatus.ACTIVE:
        raise ServiceDisabledError()
    if service.provider_id is None:
        raise ServiceDisabledError(
            detail="This service is not assigned to a provider yet.",
            code="service_unbookable",
        )
    zone = getattr(tenant, "timezone", None) or "UTC"
    local = start_utc.astimezone(_tz(zone))
    day = local.date()

    engine = SlotService(
        provider=service.provider,
        service=service,
        timezone=zone,
        busy=active_windows(service.provider, day=day, zone=zone, now=now),
        now=now,
    )
    if local not in engine.slots(day):
        raise SlotUnavailableError()

    end_local = local + timedelta(minutes=service.duration_minutes)
    return local.astimezone(UTC), end_local.astimezone(UTC)


def expire_stale_holds(
    provider_id: Any,
    *,
    now: datetime | None = None,
) -> int:
    """Flip lapsed `PENDING_PAYMENT` holds for one provider to `EXPIRED`.

    The Celery sweep calls this globally (see `tasks`); the booking path calls
    it scoped to the provider it is about to write, so an expired hold already
    left in `PENDING_PAYMENT` cannot trip the exclusion constraint on the next
    insert. Rows locked by another sweep are skipped, not blocked: two workers
    may sweep at the same time.
    """
    at = (now or timezone.now()).astimezone(UTC)
    stale = (
        Appointment.objects.unfiltered()
        .filter(
            provider_id=provider_id,
            status=AppointmentStatus.PENDING_PAYMENT,
            slot_hold_expires_at__isnull=False,
            slot_hold_expires_at__lte=at,
        )
        .select_for_update(skip_locked=True)
    )
    count = 0
    for appt in stale:
        apply_transition(appt, AppointmentStatus.EXPIRED, note="Slot hold expired.")
        # The payment order for this hold is now unpayable, so it expires with
        # it (plan §6.1). Without the cascade the order sits in PENDING forever
        # and the reconcile task re-checks an abandoned checkout hourly.
        # Imported here: payments.services imports this module, so a top-level
        # import would be circular.
        from apps.payments.services import expire_order_for_hold

        expire_order_for_hold(appt, now=at)
        count += 1
    return count


def expire_all_stale_holds(*, now: datetime | None = None) -> int:
    """Sweep every provider's lapsed holds (the Celery beat task).

    Collects the distinct provider ids that hold a lapsed `PENDING_PAYMENT`
    appointment, then expires each provider's stale holds in its own
    `select_for_update` pass - one provider at a time so two sweepers never
    contend on unrelated rows (`skip_locked` handled here means the lock is
    taken across the entire sweep for that provider).
    """
    at = (now or timezone.now()).astimezone(UTC)
    provider_ids = (
        Appointment.objects.unfiltered()
        .filter(
            status=AppointmentStatus.PENDING_PAYMENT,
            slot_hold_expires_at__isnull=False,
            slot_hold_expires_at__lte=at,
        )
        .values_list("provider_id", flat=True)
        .distinct()
    )
    total = 0
    # Materialised first: we change rows we are iterating over.
    for provider_id in list(provider_ids):
        total += expire_stale_holds(provider_id, now=now)
    return total


def _stamp(actor_type: str | None, actor_id: Any) -> tuple[str, str]:
    return actor_type or AppointmentActor.SYSTEM, str(actor_id or "")


def book_appointment(
    *,
    tenant: Any,
    customer: Any,
    service: Service,
    start_at: object,
    customer_notes: str = "",
    idempotency_key: str | None = None,
    created_via: str = CreatedVia.API,
    actor_type: str | None = None,
    actor_id: Any = None,
    now: datetime | None = None,
) -> tuple[Appointment, bool]:
    """Create a hold + `PaymentOrder` (plan §5 layer 3, checklist line 545).

    Returns `(appointment, created)`: a double-tap with the same
    `Idempotency-Key` resolves the already-created hold and reports
    `created=False` instead of carving a second one.
    """
    start_utc = parse_start_at(start_at, tenant)
    if idempotency_key:
        existing = _resolve_idempotent(tenant, idempotency_key)
        if existing is not None:
            return existing, False

    provider_id = service.provider_id
    if provider_id is None:
        raise ServiceDisabledError(
            detail="This service is not assigned to a provider yet.",
            code="service_unbookable",
        )
    actor, actor_pk = _stamp(actor_type, actor_id)
    _assert_hold_budget(customer)

    try:
        with transaction.atomic():
            # Never book over a hold that has already lapsed: transition it
            # first so the exclusion constraint sees a clean calendar.
            expire_stale_holds(provider_id, now=now)
            start, end = validate_slot(service, start_utc, tenant, now=now)
            appointment = Appointment.objects.create(
                tenant=tenant,
                provider_id=provider_id,
                customer=customer,
                service=service,
                start_at=start,
                end_at=end,
                timezone=getattr(tenant, "timezone", None) or "UTC",
                status=AppointmentStatus.PENDING_PAYMENT,
                slot_hold_expires_at=_hold_until(now or timezone.now()),
                customer_notes=customer_notes or "",
                created_via=created_via,
            )
            write_initial_history(appointment, actor_type=actor, actor_id=actor_pk)
            if service.requires_payment:
                PaymentOrder.objects.create(
                    tenant=tenant,
                    customer=customer,
                    appointment=appointment,
                    amount=service.price_amount,
                    currency=service.currency,
                )
            if idempotency_key:
                IdempotencyRecord.objects.create(
                    tenant=tenant,
                    endpoint="appointments",
                    key=idempotency_key,
                    object_id=str(appointment.pk),
                )
        return appointment, True
    except (IntegrityError, OperationalError) as err:
        # `created=False`: the client's retry resolves the winner's row.
        return _lost_the_race(tenant, idempotency_key, err), False


def _lock(appointment: Appointment) -> Appointment:
    return (
        Appointment.objects.unfiltered()
        .select_for_update()
        .select_related("service")
        .get(pk=appointment.pk)
    )


def cancel_appointment(
    *,
    appointment: Appointment,
    reason: str = "",
    client_side: bool = False,
    actor_type: str | None = None,
    actor_id: Any = None,
    now: datetime | None = None,
) -> Appointment:
    """Cancel a hold or confirmed booking.

    Client-side cancellations honour the cancellation-policy window for
    `CONFIRMED` appointments (plan §4 settings, S §A8 "Cancellation blocked
    inside the policy window"); admin cancellations always proceed and require
    a reason at the serializer. `PENDING_PAYMENT` holds cancel freely.
    """
    with transaction.atomic():
        locked = _lock(appointment)
        if locked.status not in (
            AppointmentStatus.PENDING_PAYMENT,
            AppointmentStatus.CONFIRMED,
        ):
            raise InvalidStateTransitionError(
                detail=f"Cannot cancel an appointment that is {locked.status}."
            )
        if client_side and locked.status == AppointmentStatus.CONFIRMED:
            at = (now or timezone.now()).astimezone(UTC)
            if at + _cancellation_window() >= locked.start_at:
                detail = (
                    "Cancellation is no longer available this close to the appointment."
                    if not _has_window()
                    else "Cancellation is no longer available inside the cancellation window."
                )
                raise ConflictError(detail=detail, code="cancellation_window")
        was_unpaid_hold = locked.status == AppointmentStatus.PENDING_PAYMENT
        apply_transition(
            locked,
            AppointmentStatus.CANCELLED,
            actor_type=actor_type
            or (AppointmentActor.CUSTOMER if client_side else AppointmentActor.ADMIN),
            actor_id=actor_id,
            note=reason,
        )
        if reason:
            locked.cancellation_reason = reason
            locked.save(update_fields=["cancellation_reason", "updated_at"])
        if was_unpaid_hold:
            # An abandoned checkout is `PENDING -> CANCELLED` on the order too
            # (plan §6.1). A *paid* appointment is not touched here: its order
            # is `SUCCESS` and reversing it is the manual refund flow (D2).
            from apps.payments.services import cancel_order_for_hold

            cancel_order_for_hold(locked, now=now)
    return locked


def _has_window() -> bool:
    return _cancellation_window() > timedelta(0)


def reschedule_appointment(
    *,
    appointment: Appointment,
    new_start: object,
    reason: str = "",
    created_via: str = CreatedVia.API,
    actor_type: str | None = None,
    actor_id: Any = None,
    now: datetime | None = None,
    client_side: bool = False,
) -> Appointment:
    """Atomically retire the original and hold the new slot.

    The original moves to `RESCHEDULED` (releasing its slot) and a new
    appointment is created for the revalidated start, linked via
    `rescheduled_from` (plan checklist line 548). The new booking starts as a
    fresh hold - the same semantics as `book_appointment` (plan §4
    `/reschedule -> new hold + revalidation`).

    `client_side=True` applies the cancellation-policy window to a
    `CONFIRMED` appointment, exactly as `cancel_appointment` does. Without it
    "reschedule" would be a free cancellation: moving an appointment out of the
    window is the same act as cancelling it inside the window (S §A8).
    """
    start_utc = parse_start_at(new_start, appointment.tenant)
    try:
        with transaction.atomic():
            locked = _lock(appointment)
            if locked.status not in (
                AppointmentStatus.PENDING_PAYMENT,
                AppointmentStatus.CONFIRMED,
            ):
                raise InvalidStateTransitionError(
                    detail=f"Cannot reschedule an appointment that is {locked.status}."
                )
            if client_side and locked.status == AppointmentStatus.CONFIRMED:
                at = (now or timezone.now()).astimezone(UTC)
                if at + _cancellation_window() >= locked.start_at:
                    detail = (
                        "Rescheduling is no longer available this close to the appointment."
                        if not _has_window()
                        else "Rescheduling is no longer available inside the cancellation window."
                    )
                    raise ConflictError(detail=detail, code="cancellation_window")
            expire_stale_holds(locked.provider_id, now=now)
            start, end = validate_slot(locked.service, start_utc, appointment.tenant, now=now)
            apply_transition(
                locked,
                AppointmentStatus.RESCHEDULED,
                actor_type=actor_type or AppointmentActor.CUSTOMER,
                actor_id=actor_id,
                note=f"Rescheduled to {start.isoformat()}" + (f": {reason}" if reason else ""),
            )
            created = Appointment.objects.create(
                tenant=locked.tenant,
                provider_id=locked.provider_id,
                customer=locked.customer,
                service=locked.service,
                start_at=start,
                end_at=end,
                timezone=getattr(locked.tenant, "timezone", None) or "UTC",
                status=AppointmentStatus.PENDING_PAYMENT,
                slot_hold_expires_at=_hold_until(now or timezone.now()),
                rescheduled_from=locked,
                created_via=created_via,
            )
            actor, actor_pk = _stamp(actor_type, actor_id)
            write_initial_history(created, actor_type=actor, actor_id=actor_pk)
            if locked.service.requires_payment:
                PaymentOrder.objects.create(
                    tenant=locked.tenant,
                    customer=locked.customer,
                    appointment=created,
                    amount=locked.service.price_amount,
                    currency=locked.service.currency,
                )
        return created
    except (IntegrityError, OperationalError) as err:
        return _lost_the_race(locked.tenant, None, err)


def confirm_appointment(
    *,
    appointment: Appointment,
    actor_type: str | None = None,
    actor_id: Any = None,
    note: str = "",
    payment: Any = None,
) -> Appointment:
    """The single path to `CONFIRMED` (plan §6.1).

    Two ways in, one function:

    - `payment` given - the webhook/reconcile path for a paid service. The
      payment is a captured `Payment` against this same appointment, so the
      money and the confirmation commit together.
    - `payment` omitted - the admin path, allowed only for pay-at-the-door
      services (`requires_payment=False`, open Q6).

    A paid service with no payment is refused, so "confirm" is not a back door
    around the gateway.
    """
    with transaction.atomic():
        locked = _lock(appointment)
        if locked.status != AppointmentStatus.PENDING_PAYMENT:
            raise InvalidStateTransitionError(
                detail=f"Cannot confirm an appointment that is {locked.status}."
            )
        if locked.service.requires_payment and payment is None:
            raise ConflictError(
                detail="Confirming a paid appointment requires a successful payment.",
                code="payment_required",
            )
        if payment is not None and str(getattr(payment, "status", "")) != "SUCCESS":
            raise ConflictError(
                detail="Confirming requires a successful payment.",
                code="payment_not_successful",
            )
        if payment is not None and str(payment.appointment_id) != str(locked.pk):
            raise ConflictError(
                detail="That payment belongs to a different appointment.",
                code="payment_appointment_mismatch",
            )
        apply_transition(
            locked,
            AppointmentStatus.CONFIRMED,
            actor_type=actor_type or AppointmentActor.ADMIN,
            actor_id=actor_id,
            note=note,
        )
        locked.slot_hold_expires_at = None
        locked.save(update_fields=["slot_hold_expires_at", "updated_at"])
    return locked


def complete_appointment(
    *,
    appointment: Appointment,
    actor_type: str | None = None,
    actor_id: Any = None,
    note: str = "",
) -> Appointment:
    """Mark a confirmed consultation done."""
    return _admin_move(appointment, AppointmentStatus.COMPLETED, actor_type, actor_id, note)


def mark_no_show(
    *,
    appointment: Appointment,
    actor_type: str | None = None,
    actor_id: Any = None,
    note: str = "",
) -> Appointment:
    """Record that the client never showed."""
    return _admin_move(appointment, AppointmentStatus.NO_SHOW, actor_type, actor_id, note)


def _admin_move(
    appointment: Appointment,
    target: str,
    actor_type: str | None = None,
    actor_id: Any = None,
    note: str = "",
) -> Appointment:
    with transaction.atomic():
        locked = _lock(appointment)
        if locked.status != AppointmentStatus.CONFIRMED:
            raise InvalidStateTransitionError(
                detail=f"Cannot move an appointment that is {locked.status} to {target}."
            )
        apply_transition(
            locked,
            target,
            actor_type=actor_type or AppointmentActor.ADMIN,
            actor_id=actor_id,
            note=note,
        )
    return locked


def ensure_no_blocked_over_appointment(exception: Any) -> None:
    """Plan §5.5: a `BLOCKED` exception may not overlap an active booking.

    The appointment wins; creating the block anyway would produce a confirmed
    booking inside a blocked window, so the admin is told to cancel or
    reschedule first. Answered 409 `slot_occupied`.
    """
    tz = _tz(getattr(exception.provider.tenant, "timezone", None) or "UTC")
    start = datetime.combine(exception.date, exception.start_time, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(exception.date, exception.end_time, tzinfo=tz).astimezone(UTC)
    clash = (
        Appointment.objects.unfiltered()
        .filter(
            provider_id=exception.provider_id,
            status__in=ACTIVE_STATUSES,
            start_at__lt=end,
            end_at__gt=start,
        )
        .exists()
    )
    if clash:
        raise SlotOccupiedError(
            detail="That window contains an existing booking; cancel or reschedule it first."
        )


def _is_transaction_abort(err: OperationalError) -> bool:
    """Did PostgreSQL abort this transaction to break a deadlock?

    Only these are safe to answer with a conflict; any other `OperationalError`
    is a genuine fault (connection lost, permission, ...) and must surface.
    """
    message = str(err).lower()
    return "deadlock" in message or "could not serialize" in message


def _lost_the_race(tenant: Any, idempotency_key: str | None, err: Exception) -> Appointment:
    """Translate a lost insert race into the client's 409.

    When two transactions probe the same slot at once, PostgreSQL can reject
    the loser in either of two ways:

    - the exclusion constraint fires and surfaces as `IntegrityError`;
    - or it refuses to order the two index probes and aborts one transaction
      with a deadlock/serialisation failure - an `OperationalError`, which
      would otherwise become a 500 for a user who simply lost a race.

    Both mean the same thing to the client: the slot went to someone else. With
    an idempotency key the winner's row is resolved instead, so a double-tap
    still lands on one appointment (S §A8).
    """
    if isinstance(err, OperationalError) and not _is_transaction_abort(err):
        raise err
    existing = _resolve_idempotent(tenant, idempotency_key) if idempotency_key else None
    if existing is not None:
        return existing
    raise SlotUnavailableError() from None


def _resolve_idempotent(tenant: Any, key: str) -> Appointment | None:
    record = (
        IdempotencyRecord.objects.filter(tenant_id=getattr(tenant, "pk", tenant), key=key)
        .exclude(object_id="")
        .values_list("object_id", flat=True)
        .first()
    )
    if not record:
        return None
    return Appointment.objects.unfiltered().filter(pk=record).first()


__all__ = (
    # Re-exported so a caller can catch it without reaching into
    # `common.exceptions` for a name the booking flow is expected to raise.
    "SlotUnavailableError",
    "active_windows",
    "book_appointment",
    "cancel_appointment",
    "complete_appointment",
    "confirm_appointment",
    "ensure_no_blocked_over_appointment",
    "expire_all_stale_holds",
    "expire_stale_holds",
    "mark_no_show",
    "parse_start_at",
    "reschedule_appointment",
    "validate_slot",
)
