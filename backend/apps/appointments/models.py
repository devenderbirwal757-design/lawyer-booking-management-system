"""Appointments, holds and the status trail (plan §3, §5; PRD §7-8).

One `Appointment` row is one booked slot (or one hold). It carries a
denormalised `provider` because the plan's overbooking guarantee is a
PostgreSQL exclusion constraint over `(provider_id, tstzrange(start_at,
end_at))` - the store needs the provider on the row itself, not behind a
join through `service` (§5 layer 2, migration 0002).

The state machine lives in `apps.appointments.state` and is the *only* code
that may write `status`: views call the domain services
(`apps.appointments.services`), which lock the row and apply a transition. A
direct `PATCH status=CONFIRMED` is rejected at the serializer (S §A8).

`AppointmentStatusHistory` records every leg of that trail, including the
initial `PENDING_PAYMENT`, so the audit trail and the client detail both have
a truthful story to tell (PRD §12 `appointment_status_history`).
"""

from __future__ import annotations

from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager


class AppointmentStatus(models.TextChoices):
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No show"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"
    EXPIRED = "EXPIRED", "Expired"


#: Statuses that occupy the provider's calendar (plan §5 layer 2 `WHERE`).
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.CONFIRMED}
)

#: A request may hold a slot while payment is in flight; `EXPIRED` is the
#: swept-failed hold and `RESCHEDULED` the superseded original (plan §6.1,
#: PRD §33 deviation for payments).
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
        AppointmentStatus.RESCHEDULED,
        AppointmentStatus.EXPIRED,
    }
)


class CreatedVia(models.TextChoices):
    API = "api", "Client API"
    ADMIN = "admin", "Admin console"


class AppointmentActor(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    ADMIN = "admin", "Admin user"
    SYSTEM = "system", "Background job"


class Appointment(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="The practice this booking belongs to.",
    )
    provider = models.ForeignKey(
        "providers.Provider",
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="Denormalised from `service` so the overlap exclusion "
        "constraint can key on the provider directly (plan §5 layer 2).",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="Who this booking belongs to.",
    )
    service = models.ForeignKey(
        "services.Service",
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="PROTECT: a service referenced by a booking can never be hard-deleted (plan §2).",
    )
    start_at = models.DateTimeField(db_index=True, help_text="Slot start, stored UTC.")
    end_at = models.DateTimeField(db_index=True, help_text="Consultation end = start + duration.")
    timezone = models.CharField(max_length=64, help_text="Tenant TZ captured for rendering.")
    status = models.CharField(
        max_length=16,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.PENDING_PAYMENT,
        db_index=True,
    )
    slot_hold_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When a PENDING_PAYMENT hold lapses; swept to EXPIRED (plan §5 layer 3).",
    )
    cancellation_reason = models.CharField(max_length=500, blank=True, default="")
    customer_notes = models.TextField(blank=True, default="")
    rescheduled_from = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rescheduled_to",
        help_text="The appointment this one replaced (atomic cancel + create, plan §5).",
    )
    created_via = models.CharField(
        max_length=16,
        choices=CreatedVia.choices,
        default=CreatedVia.API,
    )

    objects = TenantScopedManager()

    class Meta:
        db_table = "appointments"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "status"), name="idx_appts_tenant_status"),
            models.Index(fields=("provider_id", "start_at"), name="idx_appts_provider_start"),
            models.Index(fields=("customer_id", "start_at"), name="idx_appts_customer_start"),
        ]

    def __str__(self) -> str:
        return f"{self.service_id} @ {self.start_at.isoformat()} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class AppointmentStatusHistory(BaseModel):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    # Empty string (not NULL) means "no prior status" - the first leg written
    # on creation. A nullable CharField would make every read special-case NULL.
    from_status = models.CharField(max_length=16, blank=True, default="")
    to_status = models.CharField(max_length=16)
    actor_type = models.CharField(
        max_length=16,
        choices=AppointmentActor.choices,
        default=AppointmentActor.SYSTEM,
    )
    actor_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Who acted. A bare user/customer UUID, or a typed label such as "
        "'payment:<uuid>' for a capture-driven confirmation, so the audit leg "
        "says *what* paid for the slot and not merely that something did.",
    )
    note = models.TextField(blank=True, default="")

    objects = models.Manager()

    class Meta:
        db_table = "appointment_status_history"
        ordering = ("created_at", "id")
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("appointment_id", "created_at"), name="idx_history_appt_time"),
        ]

    def __str__(self) -> str:
        return f"{self.from_status or '—'} -> {self.to_status}"


__all__ = (
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "Appointment",
    "AppointmentActor",
    "AppointmentStatus",
    "AppointmentStatusHistory",
    "CreatedVia",
)
