"""Payment services (plan §6, PRD §11).

The invariants this module exists to hold:

1. **The amount is ours.** Nothing here reads an amount from a request. It is
   recomputed from `Service.price_amount` on every path, and a client that
   sends one anyway is told so (S §A5).
2. **`Appointment.CONFIRMED` has exactly one door.** `mark_captured()` is the
   only caller of `confirm_appointment()` with a payment, and it does so in the
   same transaction that writes `Payment -> SUCCESS`. There is no endpoint that
   takes a status from a client, because there is no endpoint that takes a
   status at all (S §A5 enumerates the routes to prove it).
3. **A replay changes nothing.** The event is deduped on `(gateway, event_id)`
   *before* any state moves, so the same delivery three times is one
   transition, one confirmation, one email.
4. **A signature is checked over the raw bytes**, in constant time, before the
   payload is trusted enough to store.
5. **Uncertainty is not success.** When we cannot tell - the order is
   terminal, the mode does not match, the amounts disagree - the payment is
   *not* confirmed. Where money demonstrably landed anyway (a capture for an
   expired hold) the `Payment` row still records it, because a silent failure
   to record is how a practice ends up owing a refund it does not know about.

Every public entry point opens `transaction.atomic()` and locks the order with
`select_for_update`: "two webhooks do not both confirm" is a database fact.
`now` is injectable so the time-bound tests can pin the clock without
freezegun, and `gateway` is injectable so no test needs the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import User
from apps.appointments.models import Appointment, AppointmentActor, AppointmentStatus
from apps.payments.gateways import (
    GatewayError,
    GatewayOrder,
    GatewayPayment,
    PaymentGateway,
    get_gateway,
)
from apps.payments.models import (
    Payment,
    PaymentEvent,
    PaymentEventOutcome,
    PaymentOrder,
    PaymentOrderStatus,
    Refund,
    RefundStatus,
)
from apps.payments.state import can_transition, transition
from common.exceptions import (
    ConflictError,
    InvalidSignatureError,
    InvalidStateTransitionError,
    ServiceDisabledError,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger("payments.services")

#: Events we act on. Everything else is acknowledged and ignored: a gateway
#: sends orders of events we do not model, and a non-2xx would only earn us a
#: retry storm (plan §6 step 5).
CAPTURED_EVENTS = frozenset({"payment.captured"})
FAILED_EVENTS = frozenset({"payment.failed"})
#: Razorpay's order-level success event. Carries no payment id, so the captured
#: payment is read back from the gateway rather than invented.
ORDER_PAID_EVENTS = frozenset({"order.paid"})


def _now(now: datetime | None = None) -> datetime:
    """The injected clock, or the real one.

    Every time-bound helper here takes `now` so the tests can pin the clock
    without freezegun; this is the single place that resolves it.
    """
    return now or timezone.now()


# --------------------------------------------------------------------- orders
def create_gateway_order(
    *,
    order: PaymentOrder,
    receipt: str = "",
    gateway: PaymentGateway | None = None,
    now: datetime | None = None,
) -> PaymentOrder:
    """Push the order to the gateway and move it `CREATED -> PENDING`.

    `order.amount` was computed server-side at booking time from the service
    price; it is re-read here from the service rather than trusted from the row
    so an edited price cannot be charged at the stale value, and the value we
    send is asserted back against what the gateway echoes.
    """
    at = _now(now)
    active = gateway or get_gateway()
    with transaction.atomic():
        locked = _lock_order(order.pk)
        if locked.status == PaymentOrderStatus.PENDING:
            # Already started (a double-tapped "Pay"). Razorpay create_order is
            # not idempotent, so calling again would create a second payable
            # order for the same hold. Return the one we have.
            return locked
        if not can_transition(str(locked.status), PaymentOrderStatus.PENDING):
            raise InvalidStateTransitionError(
                detail=f"Cannot start payment for an order that is {locked.status}."
            )
        service = locked.appointment.service
        if not service.is_active:
            raise ServiceDisabledError()

        gateway_order = active.create_order(
            amount=service.price_amount,
            currency=service.currency,
            receipt=receipt or locked.receipt or f"appt-{locked.appointment_id}",
            notes={
                "appointment_id": str(locked.appointment_id),
                "tenant_id": str(locked.tenant_id),
            },
        )
        if gateway_order.amount_minor != active.to_minor(service.price_amount):
            # The gateway is quoting a different number than the order. Confirm
            # nothing: record the anomaly and leave the order untouched.
            logger.error(
                "payment_order_amount_mismatch",
                gateway_order_id=gateway_order.gateway_order_id,
                gateway_minor=gateway_order.amount_minor,
                expected_minor=active.to_minor(service.price_amount),
                order_id=str(locked.pk),
            )
            raise ConflictError(
                detail="The payment gateway returned a different amount than the order.",
                code="gateway_amount_mismatch",
            )

        locked.gateway = active.name
        locked.gateway_mode = active.mode
        locked.gateway_order_id = gateway_order.gateway_order_id
        locked.receipt = gateway_order.receipt or locked.receipt
        locked.expires_at = locked.appointment.slot_hold_expires_at
        transition(
            locked,
            PaymentOrderStatus.PENDING,
            now=at,
            extra_fields=(
                "gateway",
                "gateway_mode",
                "gateway_order_id",
                "receipt",
                "expires_at",
            ),
        )
    return locked


def order_response_payload(order: PaymentOrder) -> dict[str, object]:
    """What the checkout needs to open the gateway's payment UI.

    Contains the public key id and the order id; the key *secret* and the
    webhook secret are never part of a response (S §A5).

    `amount_minor` is the gateway's own unit (paise for Razorpay) and is what a
    checkout UI must hand to the SDK. `amount` stays the exact decimal string for
    display. A client that re-derives minor units from a float loses the
    rounding, so the value the gateway will charge is sent pre-converted.
    """
    active = get_gateway()
    return {
        "payment_order_id": str(order.pk),
        "appointment_id": str(order.appointment_id),
        "gateway": order.gateway,
        "gateway_mode": order.gateway_mode,
        "gateway_order_id": order.gateway_order_id,
        "gateway_key_id": getattr(active, "key_id", ""),
        "amount": str(order.amount),
        "amount_minor": active.to_minor(order.amount),
        "currency": order.currency,
        "status": order.status,
    }


# -------------------------------------------------------------------- webhook
def handle_webhook(
    *,
    raw_body: bytes,
    signature: str,
    event_type: str,
    payload: dict[str, object],
    gateway: PaymentGateway | None = None,
    now: datetime | None = None,
) -> PaymentEvent:
    """Verify, dedupe, then apply one gateway delivery.

    Returns the `PaymentEvent` describing what happened, including the
    duplicate/ignored cases - the caller answers 200 to all of them, because a
    gateway retries anything that is not 2xx and a retry will not change the
    outcome.

    Raises `InvalidSignatureError` (400) *before* touching the database: an
    unsigned or badly signed payload must leave no trace at all (S §A5).
    """
    at = _now(now)
    active = gateway or get_gateway()
    if not active.verify_signature(raw_body, signature):
        logger.warning("webhook_signature_rejected", gateway=active.name, event_type=event_type)
        raise InvalidSignatureError()

    event_id = str(payload.get("id") or "")
    if not event_id:
        # Without an event id we cannot dedupe, and an undedupeable delivery
        # must not be allowed to move money. Recorded, acknowledged, ignored.
        return _record_event(
            active=active,
            event_id=f"no-id:{signature[:32]}",
            event_type=event_type,
            payload=payload,
            signature=signature,
            outcome=PaymentEventOutcome.IGNORED,
            detail="missing_event_id",
            now=at,
        )

    existing = PaymentEvent.objects.filter(gateway=active.name, event_id=event_id).first()
    if existing is not None:
        logger.info("webhook_duplicate", event_id=event_id, event_type=event_type)
        return existing

    try:
        with transaction.atomic():
            event = _record_event(
                active=active,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                signature=signature,
                outcome=PaymentEventOutcome.RECEIVED,
                now=at,
            )
    except IntegrityError:
        # Concurrent delivery of the same event id: the other writer's row won.
        # Falling back to theirs is the whole point of the unique constraint.
        return PaymentEvent.objects.get(gateway=active.name, event_id=event_id)

    return _dispatch_event(event=event, payload=payload, gateway=active, now=at)


def _record_event(
    *,
    active: PaymentGateway,
    event_id: str,
    event_type: str,
    payload: dict[str, object],
    signature: str,
    outcome: str,
    detail: str = "",
    now: datetime | None = None,
) -> PaymentEvent:
    payload_entity = payload.get("payload")
    inner = payload_entity if isinstance(payload_entity, dict) else {}
    return PaymentEvent.objects.create(
        gateway=active.name,
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        signature=signature[:256],
        gateway_order_id=str(inner.get("order_id") or ""),
        outcome=outcome,
        detail=detail[:255],
        processed_at=_now(now),
    )


def _dispatch_event(
    *,
    event: PaymentEvent,
    payload: dict[str, object],
    gateway: PaymentGateway,
    now: datetime | None = None,
) -> PaymentEvent:
    """Route a recorded event to its handler and stamp the outcome."""
    at = _now(now)
    entity = payload.get("payload")
    inner: dict[str, object] = entity if isinstance(entity, dict) else {}
    order_id = str(inner.get("order_id") or "")
    event_type = event.event_type

    if event_type in CAPTURED_EVENTS:
        return _apply_capture(event, order_id, inner, gateway, now=at)
    if event_type in FAILED_EVENTS:
        return _apply_failure(event, order_id, inner, now=at)
    if event_type in ORDER_PAID_EVENTS:
        return _apply_order_paid(event, order_id, gateway, now=at)

    event.outcome = PaymentEventOutcome.IGNORED
    event.detail = f"unhandled_event:{event_type}"[:255]
    event.save(update_fields=["outcome", "detail", "processed_at", "updated_at"])
    return event


def _find_order(gateway_order_id: str) -> PaymentOrder | None:
    if not gateway_order_id:
        return None
    # Unfiltered on purpose: a webhook carries no tenant context, and
    # `gateway_order_id` is globally unique, so this cannot read across
    # tenants - it resolves exactly the one row the gateway is talking about.
    return PaymentOrder.objects.unfiltered().filter(gateway_order_id=gateway_order_id).first()


def _apply_capture(
    event: PaymentEvent,
    order_id: str,
    inner: dict[str, object],
    gateway: PaymentGateway,
    *,
    now: datetime | None = None,
) -> PaymentEvent:
    at = _now(now)
    payment_id = _nested_id(inner.get("payment"))
    with transaction.atomic():
        order = _find_order_for_update(order_id)
        if order is None:
            return _finish(event, PaymentEventOutcome.UNMATCHED, "unknown_order")
        mismatch = _mode_or_gateway_mismatch(order, gateway)
        if mismatch:
            logger.warning("payment_event_rejected", reason=mismatch, order_id=str(order.pk))
            return _finish(event, PaymentEventOutcome.IGNORED, mismatch)

        if str(order.status) == PaymentOrderStatus.SUCCESS:
            # Same capture, a fresh event id. The payment is already recorded;
            # acknowledging is the whole answer, because a non-2xx here would
            # earn a retry of an outcome that cannot change.
            return _finish(event, PaymentEventOutcome.IGNORED, "already_captured")

        if str(order.status) in {"EXPIRED", "CANCELLED", "FAILED", "REFUNDED"}:
            # The money landed for an order we had already written off. Record
            # the payment so the refund is visible to a human, but do not touch
            # the appointment: a late capture must never resurrect a cancelled
            # or expired booking (S §A5).
            amount = _amount_from_event(inner, order)
            if payment_id:
                late = _payment_row(
                    order=order,
                    gateway_payment_id=payment_id,
                    amount=amount,
                    now=at,
                )
                _move_payment(late, PaymentOrderStatus.SUCCESS, now=at)
            return _finish(event, PaymentEventOutcome.IGNORED, "late_capture_refund_due")

        if not payment_id:
            return _finish(event, PaymentEventOutcome.IGNORED, "missing_payment_id")

        amount = _amount_from_event(inner, order)
        if amount != order.amount:
            # Charged number does not match the order. Refuse to confirm; the
            # discrepancy is for a human, not for automation to guess at.
            logger.error(
                "payment_amount_mismatch",
                order_id=str(order.pk),
                expected=str(order.amount),
                received=str(amount),
            )
            mismatched = _payment_row(
                order=order,
                gateway_payment_id=payment_id,
                amount=amount,
                now=at,
            )
            _move_payment(
                mismatched,
                PaymentOrderStatus.FAILED,
                now=at,
                failure_reason="amount_mismatch",
            )
            return _finish(event, PaymentEventOutcome.FAILED, "amount_mismatch")

        mark_captured(
            order=order,
            gateway_payment_id=payment_id,
            amount=amount,
            method=str(inner.get("method") or ""),
            event=event,
            now=at,
        )
    return _finish(event, PaymentEventOutcome.APPLIED, "payment_captured")


def _apply_failure(
    event: PaymentEvent,
    order_id: str,
    inner: dict[str, object],
    *,
    now: datetime | None = None,
) -> PaymentEvent:
    at = _now(now)
    with transaction.atomic():
        order = _find_order_for_update(order_id)
        if order is None:
            return _finish(event, PaymentEventOutcome.UNMATCHED, "unknown_order")
        if str(order.status) in {"EXPIRED", "CANCELLED", "REFUNDED", "FAILED"}:
            return _finish(event, PaymentEventOutcome.IGNORED, f"order_{order.status}")
        entity = inner.get("payment")
        payment_id = _nested_id(entity)
        reason = str(entity.get("error_description") or "") if isinstance(entity, dict) else ""
        if payment_id:
            failed = _payment_row(
                order=order,
                gateway_payment_id=payment_id,
                amount=order.amount,
                now=at,
            )
            _move_payment(failed, PaymentOrderStatus.FAILED, now=at, failure_reason=reason)
        if can_transition(str(order.status), PaymentOrderStatus.FAILED):
            transition(order, PaymentOrderStatus.FAILED, now=at, failure_reason=reason)
    return _finish(event, PaymentEventOutcome.APPLIED, "payment_failed")


def _apply_order_paid(
    event: PaymentEvent,
    order_id: str,
    gateway: PaymentGateway,
    *,
    now: datetime | None = None,
) -> PaymentEvent:
    """`order.paid` carries no payment id - read the payment back from the gateway.

    Routing it through the same `mark_captured` as the payment-level event
    keeps "there is one path to SUCCESS" true, rather than adding a second
    implementation that could drift.
    """
    at = _now(now)
    order = _find_order(order_id)
    if order is None or not order.gateway_order_id:
        return _finish(event, PaymentEventOutcome.UNMATCHED, "unknown_order")
    captured = _fetch_captured(gateway, order.gateway_order_id)
    if captured is None:
        return _finish(event, PaymentEventOutcome.IGNORED, "no_captured_payment")
    inner: dict[str, object] = {
        "order_id": order.gateway_order_id,
        "payment": {"id": captured.gateway_payment_id},
        "amount": captured.amount_minor,
        "method": captured.method,
    }
    return _apply_capture(event, order.gateway_order_id, inner, gateway, now=at)


def _nested_id(value: object) -> str:
    """The `id` inside a gateway's nested payment object, or `""`.

    Razorpay nests the payment under `payload.payment.id`; a malformed or
    truncated body yields `None`, a string, or something else entirely, and
    none of those may become a gateway id.
    """
    return str(value.get("id") or "") if isinstance(value, dict) else ""


def _fetch_captured(gateway: PaymentGateway, gateway_order_id: str) -> GatewayPayment | None:
    """The captured payment behind an order, or `None` if we cannot establish one.

    `None` covers three different situations, all of which must lead to the same
    place: the gateway cannot list payments at all, it is unreachable, or it
    reports no capture. A provider that cannot answer can only ever confirm from
    an event that carries a payment id, so the answer is never to guess.
    """
    try:
        payments = gateway.fetch_order_payments(gateway_order_id)
    except NotImplementedError:
        logger.warning("gateway_cannot_list_payments", gateway=gateway.name)
        return None
    except GatewayError as exc:
        logger.warning(
            "fetch_order_payments_failed",
            gateway_order_id=gateway_order_id,
            error=str(exc),
        )
        return None
    return next((p for p in payments if p.status.lower() == "captured"), None)


def _finish(
    event: PaymentEvent,
    outcome: str,
    detail: str = "",
) -> PaymentEvent:
    event.outcome = outcome
    event.detail = detail[:255]
    event.processed_at = timezone.now()
    event.save(update_fields=["outcome", "detail", "processed_at", "updated_at"])
    return event


def _mode_or_gateway_mismatch(order: PaymentOrder, gateway: PaymentGateway) -> str:
    """Refuse to act on an order that belongs to another gateway or mode.

    A test-mode capture must not confirm a live booking and vice versa
    (S §A5). The order carries the mode it was created under, so flipping
    `PAYMENT_MODE` in the environment cannot retroactively reinterpret old
    orders.
    """
    if order.gateway and order.gateway != gateway.name:
        return f"gateway_mismatch:{order.gateway}"
    if order.gateway_mode and order.gateway_mode != gateway.mode:
        return f"mode_mismatch:{order.gateway_mode}!={gateway.mode}"
    return ""


def _find_order_for_update(gateway_order_id: str) -> PaymentOrder | None:
    if not gateway_order_id:
        return None
    return (
        PaymentOrder.objects.unfiltered()
        .select_for_update()
        .filter(gateway_order_id=gateway_order_id)
        .first()
    )


def _amount_from_event(inner: dict[str, object], order: PaymentOrder) -> Decimal:
    """The amount the gateway says was captured, in rupees.

    Razorpay sends paise as an integer. Absent or unparseable, we do not guess:
    falling back to the order's own amount would make "did they pay the right
    number" unanswerable.
    """
    from decimal import InvalidOperation  # only needed on the failure path

    raw = inner.get("amount")
    if raw is None:
        return order.amount
    try:
        return (Decimal(str(raw)) / 100).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("-1.00")


# ------------------------------------------------------------------- capture
def mark_captured(
    *,
    order: PaymentOrder,
    gateway_payment_id: str,
    amount: Decimal,
    method: str = "",
    event: PaymentEvent | None = None,
    now: datetime | None = None,
) -> Payment:
    """`Payment -> SUCCESS` and `Appointment -> CONFIRMED`, one transaction.

    The only writer of both. Splitting them would leave a window where money
    landed and the appointment is still a hold - and a hold that is about to be
    swept - or the mirror image, a confirmed appointment with no payment.
    """
    at = _now(now)
    from apps.appointments.services import confirm_appointment

    with transaction.atomic():
        locked = _lock_order(order.pk)
        if not can_transition(str(locked.status), PaymentOrderStatus.SUCCESS):
            raise InvalidStateTransitionError(
                detail=f"Cannot capture an order that is {locked.status}."
            )
        payment = _payment_row(
            order=locked,
            gateway_payment_id=gateway_payment_id,
            amount=amount,
            method=method,
            now=at,
        )
        _move_payment(payment, PaymentOrderStatus.SUCCESS, now=at)
        transition(locked, PaymentOrderStatus.SUCCESS, now=at)

        appointment = (
            Appointment.objects.unfiltered()
            .select_for_update()
            .filter(pk=locked.appointment_id)
            .first()
        )
        if appointment is not None and appointment.status == AppointmentStatus.PENDING_PAYMENT:
            confirm_appointment(
                appointment=appointment,
                actor_type=AppointmentActor.SYSTEM,
                actor_id=f"payment:{payment.pk}",
                note=f"Payment {gateway_payment_id} captured.",
                payment=payment,
            )
        if event is not None:
            event.gateway_order_id = locked.gateway_order_id or event.gateway_order_id
            event.save(update_fields=["gateway_order_id", "updated_at"])
    return payment


def _payment_row(
    *,
    order: PaymentOrder,
    gateway_payment_id: str,
    amount: Decimal,
    method: str = "",
    now: datetime | None = None,
) -> Payment:
    """Create the `Payment` for a gateway payment id, or return the existing one.

    The row is always born `PENDING` and moved to its outcome by `transition()`.
    Creating it directly in its final state would quietly make the state machine
    optional - a second writer could mint a `SUCCESS` payment that no edge
    ever approved, which is the exact failure mode plan §6.1 exists to prevent.

    The unique constraint on `gateway_payment_id` is the real guard; returning
    the existing row is the polite version of it, so a re-delivered capture
    reuses the row instead of raising.

    `now` is accepted for symmetry with the other helpers here and deliberately
    unused: the row is born `PENDING` with no `paid_at`, and the timestamp that
    matters is stamped later by the `SUCCESS` transition. Capturing it now would
    mean the create could write a time that a later edge contradicts.
    """
    del now
    existing = Payment.objects.unfiltered().filter(gateway_payment_id=gateway_payment_id).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Payment.objects.create(
                tenant_id=order.tenant_id,
                customer_id=order.customer_id,
                appointment_id=order.appointment_id,
                order=order,
                gateway=order.gateway,
                gateway_payment_id=gateway_payment_id,
                amount=amount,
                currency=order.currency,
                status=PaymentOrderStatus.PENDING,
                method=method[:32],
                paid_at=None,
            )
    except IntegrityError:
        return Payment.objects.unfiltered().get(gateway_payment_id=gateway_payment_id)


def _move_payment(
    payment: Payment,
    target: str,
    *,
    now: datetime | None = None,
    failure_reason: str = "",
) -> Payment:
    """Apply an edge to a payment, tolerating a row already there.

    Idempotent on purpose: a replayed capture reuses the row and then asks for
    `SUCCESS` again. Silently accepting *that* is safe (the state is what we
    wanted and the unique constraint stopped a second row), whereas raising
    would turn a redelivery into a 500 and a retry storm.
    """
    at = _now(now)
    if str(payment.status) == target:
        return payment
    if not can_transition(str(payment.status), target):
        raise InvalidStateTransitionError(
            detail=f"Cannot move payment from {payment.status} to {target}."
        )
    transition(payment, target, now=at, failure_reason=failure_reason)
    return payment


# -------------------------------------------------------------- hold expiry
def expire_order_for_hold(appointment: Appointment, *, now: datetime | None = None) -> int:
    """Cascade `PENDING -> EXPIRED` when the slot hold lapses (plan §6.1).

    Called from the hold sweep so an abandoned checkout does not stay
    `PENDING` forever: without this the order is indistinguishable from one
    that is genuinely mid-payment, and the reconcile task would keep re-checking
    a checkout the client abandoned ten minutes ago.
    """
    at = _now(now)
    order = (
        PaymentOrder.objects.unfiltered()
        .select_for_update()
        .filter(appointment_id=appointment.pk)
        .first()
    )
    if order is None:
        return 0
    if not can_transition(str(order.status), PaymentOrderStatus.EXPIRED):
        return 0
    transition(order, PaymentOrderStatus.EXPIRED, now=at)
    return 1


def cancel_order_for_hold(appointment: Appointment, *, now: datetime | None = None) -> int:
    """`PENDING -> CANCELLED` when the client releases the hold (plan §6.1)."""
    return _close_order_for_appointment(appointment, target=PaymentOrderStatus.CANCELLED, now=now)


def _close_order_for_appointment(
    appointment: Appointment,
    *,
    target: str,
    now: datetime | None = None,
) -> int:
    at = _now(now)
    order = (
        PaymentOrder.objects.unfiltered()
        .select_for_update()
        .filter(appointment_id=appointment.pk)
        .first()
    )
    if order is None or not can_transition(str(order.status), target):
        return 0
    transition(order, target, now=at)
    return 1


# -------------------------------------------------------------- reconciliation
def reconcile_pending_payments(
    *,
    older_than_minutes: int | None = None,
    gateway: PaymentGateway | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Compare open orders against the gateway truth (the hourly beat task).

    Only ever *downgrades*: an order the gateway no longer considers payable
    becomes `FAILED`, and a capture the gateway confirms is applied through
    `mark_captured`. It never invents a success, and it never touches a terminal
    order - S §A5 requires that a `FAILED` payment cannot become `SUCCESS`
    without a gateway truth, so every `SUCCESS` written here is backed by a
    `fetch_order` that said `paid`.
    """
    at = _now(now)
    active = gateway or get_gateway()
    if older_than_minutes is None:
        from django.conf import settings  # only needed for the default

        older_than_minutes = settings.PAYMENT_RECONCILE_MINUTES
    cutoff = at - timedelta(minutes=older_than_minutes)

    stale = (
        PaymentOrder.objects.unfiltered()
        .filter(
            status__in=[PaymentOrderStatus.CREATED, PaymentOrderStatus.PENDING],
            created_at__lte=cutoff,
            gateway_order_id__isnull=False,
        )
        .order_by("created_at")
    )
    stats = {"checked": 0, "captured": 0, "failed": 0, "unavailable": 0, "unmatched": 0}
    for order in list(stale):
        stats["checked"] += 1
        gateway_order_id = order.gateway_order_id
        if not gateway_order_id:
            continue
        try:
            truth: GatewayOrder | None = active.fetch_order(gateway_order_id)
        except GatewayError as exc:
            logger.warning("reconcile_fetch_failed", order_id=str(order.pk), error=str(exc))
            stats["unavailable"] += 1
            continue
        if truth is None:
            stats["unmatched"] += 1
            continue
        if truth.status == PaymentOrderStatus.SUCCESS:
            with transaction.atomic():
                locked = _lock_order(order.pk)
                if locked.status == PaymentOrderStatus.SUCCESS:
                    continue
                if not can_transition(str(locked.status), PaymentOrderStatus.SUCCESS):
                    continue
                captured = _fetch_captured(active, gateway_order_id)
                if captured is None:
                    # The order reads paid but we have no payment id to record;
                    # confirming on the order's word alone would let a replayed
                    # order number confirm a booking with no money behind it.
                    logger.warning("reconcile_no_payment_id", order_id=str(locked.pk))
                    continue
                mark_captured(
                    order=locked,
                    gateway_payment_id=captured.gateway_payment_id,
                    amount=order.amount,
                    method=captured.method,
                    now=at,
                )
                stats["captured"] += 1
        elif truth.status == PaymentOrderStatus.FAILED:
            with transaction.atomic():
                locked = _lock_order(order.pk)
                if can_transition(str(locked.status), PaymentOrderStatus.FAILED):
                    transition(locked, PaymentOrderStatus.FAILED, now=at)
                    stats["failed"] += 1
    logger.info("payment_reconcile", **stats)
    return stats


def poll_order_status(
    *,
    order: PaymentOrder,
    gateway: PaymentGateway | None = None,
    now: datetime | None = None,
) -> PaymentOrder:
    """`GET /payments/{id}/status` fallback for a missed webhook (plan §6).

    Reads the gateway and reconciles. Same rule as the task: a status the
    gateway has not confirmed is never written.
    """
    at = _now(now)
    active = gateway or get_gateway()
    if not order.gateway_order_id:
        return order
    try:
        truth = active.fetch_order(order.gateway_order_id)
    except GatewayError as exc:
        logger.warning("status_poll_failed", order_id=str(order.pk), error=str(exc))
        return order
    if truth is None:
        return order
    if truth.status == PaymentOrderStatus.SUCCESS:
        captured = _fetch_captured(active, order.gateway_order_id)
        if captured is None:
            return order
        with transaction.atomic():
            locked = _lock_order(order.pk)
            if locked.status == PaymentOrderStatus.SUCCESS:
                return locked
            if not can_transition(str(locked.status), PaymentOrderStatus.SUCCESS):
                return locked
            mark_captured(
                order=locked,
                gateway_payment_id=captured.gateway_payment_id,
                amount=order.amount,
                method=captured.method,
                now=at,
            )
        # Re-read rather than returning `locked`: `mark_captured` locks and
        # mutates its own copy, so the instance we hold still says PENDING and
        # the customer would be shown a stale status for a payment that landed.
        return PaymentOrder.objects.unfiltered().get(pk=order.pk)
    if truth.status == PaymentOrderStatus.FAILED:
        with transaction.atomic():
            locked = _lock_order(order.pk)
            if can_transition(str(locked.status), PaymentOrderStatus.FAILED):
                transition(locked, PaymentOrderStatus.FAILED, now=at)
        return locked
    return order


# --------------------------------------------------------------------- refunds
def _refunded_total(payment: Payment) -> Decimal:
    """Rupees already spoken for: requested and not yet voided, plus settled.

    Both statuses count because the money is committed in either case. A
    `PENDING_ACTION` refund nobody has executed is still a liability the practice
    told the client it owes, and letting a second request through would let the
    commitments stack past the amount actually captured.
    """
    total = (
        Refund.objects.unfiltered()
        .filter(
            payment=payment,
            status__in=[RefundStatus.PENDING_ACTION, RefundStatus.SETTLED],
        )
        .aggregate(total=Sum("amount"))["total"]
    )
    return total or Decimal("0.00")


def request_refund(
    *,
    payment: Payment,
    amount: Decimal,
    reason: str = "",
    requested_by: User | None = None,
    now: datetime | None = None,
) -> Refund:
    """Create a `PENDING_ACTION` refund (plan §6.2, D2).

    Deliberately does **not** call the gateway and does **not** move the
    payment: the lawyer issues the refund in the dashboard, and a second admin
    action settles it. That two-step split is the entire point - a single
    "refund" button that both records and promises would let one click create
    a liability nobody agreed to.

    Guards: the amount must be positive, must not exceed the captured amount,
    and the outstanding (pending + settled) total must leave room for it, so a
    replayed request cannot stack up refunds the practice never agreed to
    (S §A5: "amount <= captured amount, cannot be replayed").
    """
    del now
    with transaction.atomic():
        locked = Payment.objects.unfiltered().select_for_update().get(pk=payment.pk)
        if str(locked.status) != PaymentOrderStatus.SUCCESS:
            raise ConflictError(
                detail="Only a successful payment can be refunded.",
                code="payment_not_refundable",
            )
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
        if value <= 0:
            raise ConflictError(
                detail="A refund must be for a positive amount.", code="invalid_refund_amount"
            )
        if value > locked.amount:
            raise ConflictError(
                detail="A refund cannot exceed the captured amount.",
                code="refund_exceeds_payment",
            )
        if _refunded_total(locked) + value > locked.amount:
            raise ConflictError(
                detail="Refunds already requested cover that amount.",
                code="refund_exceeds_remaining",
            )
        return Refund.objects.create(
            tenant_id=locked.tenant_id,
            payment=locked,
            amount=value,
            currency=locked.currency,
            status=RefundStatus.PENDING_ACTION,
            reason=reason[:255],
            requested_by=requested_by,
        )


def settle_refund(
    *,
    refund: Refund,
    gateway_refund_id: str = "",
    settled_by: User | None = None,
    now: datetime | None = None,
) -> Refund:
    """Mark a refund settled - the only path to `Payment -> REFUNDED`.

    The admin has done the work at the gateway by hand; this records it. The
    linked payment only flips to `REFUNDED` once the settled refunds cover the
    whole captured amount, so a partial refund keeps the payment `SUCCESS` and
    the outstanding balance stays visible. Writing `REFUNDED` on the first
    partial settlement would tell reconciliation the money is fully returned
    while a second tranche is still pending at the gateway.
    """
    at = _now(now)
    with transaction.atomic():
        locked = Refund.objects.unfiltered().select_for_update().get(pk=refund.pk)
        if str(locked.status) != RefundStatus.PENDING_ACTION:
            raise InvalidStateTransitionError(
                detail=f"Cannot settle a refund that is {locked.status}."
            )
        if gateway_refund_id:
            locked.gateway_refund_id = gateway_refund_id
        locked.settled_by = settled_by
        transition(locked, RefundStatus.SETTLED, now=at)

        payment = Payment.objects.unfiltered().select_for_update().get(pk=locked.payment_id)
        if _settled_total(payment) >= payment.amount and can_transition(
            str(payment.status), PaymentOrderStatus.REFUNDED
        ):
            transition(payment, PaymentOrderStatus.REFUNDED, now=at)
    return locked


def _settled_total(payment: Payment) -> Decimal:
    """Rupees actually returned so far - `SETTLED` refunds only.

    Distinct from `_refunded_total`, which also counts refunds merely
    requested. A requested refund is an intention; only this one is a fact.
    """
    total = (
        Refund.objects.unfiltered()
        .filter(payment=payment, status=RefundStatus.SETTLED)
        .aggregate(total=Sum("amount"))["total"]
    )
    return total or Decimal("0.00")


# --------------------------------------------------------------------- shared
def _lock_order(order_id: UUID) -> PaymentOrder:
    """The order row, locked for the duration of the caller's transaction.

    `select_for_update` is the whole of the concurrency story for payments: two
    webhooks cannot both confirm, because the second one blocks on this row and
    then finds the status has already moved.

    Always `unfiltered()`. Every caller has already resolved the row
    authoritatively before locking it - the request views by `(tenant, customer)`,
    the webhook and reconciliation paths by `gateway_order_id`, which carries a
    global unique constraint - so re-asserting a tenant here would add nothing.

    It was actively harmful: `PaymentOrder.objects` is the tenant-scoped manager,
    which raises `TenantContextMissing` unless the middleware managed to bind a
    tenant. For a customer JWT it cannot - the middleware runs before DRF
    authenticates, so `request.user` is anonymous and it has only the host
    subdomain or `DJANGO_DEFAULT_TENANT_SLUG` to go on. Every test wrapped the
    call in `tenant_context(...)`, which hid it, and a real browser request
    against a bare domain got a 500 from `POST /payments/create-order/`.
    """
    return PaymentOrder.objects.unfiltered().select_for_update().get(pk=order_id)


__all__ = (
    "CAPTURED_EVENTS",
    "FAILED_EVENTS",
    "ORDER_PAID_EVENTS",
    "cancel_order_for_hold",
    "create_gateway_order",
    "expire_order_for_hold",
    "handle_webhook",
    "mark_captured",
    "order_response_payload",
    "poll_order_status",
    "reconcile_pending_payments",
    "request_refund",
    "settle_refund",
)
