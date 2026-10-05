"""Payment models (plan §6, PRD §11-12).

Four tables, each with one job:

- `PaymentOrder` - what we asked the gateway to hold for a booking. Created in
  the same transaction as the slot hold (plan §5), one order per appointment,
  amount recomputed from the `Service` price server-side. Never accepts an
  amount from the client (S §A8: balances are never derivable from
  client-submitted values).
- `Payment` - money that actually moved. A gateway can fail and retry, so this
  is a FK to the order, not a one-to-one; only the captured attempt becomes
  `SUCCESS` and only its row carries `paid_at`.
- `Refund` - the manual (D2) reversal. Created `PENDING_ACTION` by an admin and
  moved to `SETTLED` by a *second* admin action; that second action is the only
  thing in the codebase that writes `Payment -> REFUNDED`.
- `PaymentEvent` - the raw webhook envelope, stored before processing and
  deduped on `event_id` so a gateway redelivery cannot double-apply.

Statuses mirror each other on purpose: order and payment share one transition
table (`apps.payments.state`), so "the order says SUCCESS but the payment says
FAILED" is not a state this schema can represent.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager

#: Terminal statuses of the order/payment vocabulary (plan §6.1).
TERMINAL_PAYMENT_STATUSES = frozenset({"FAILED", "EXPIRED", "CANCELLED", "REFUNDED"})


class PaymentOrderStatus(models.TextChoices):
    CREATED = "CREATED", "Created"
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    EXPIRED = "EXPIRED", "Expired"
    CANCELLED = "CANCELLED", "Cancelled"
    REFUNDED = "REFUNDED", "Refunded"


#: `Payment` speaks the same vocabulary as `PaymentOrder` (plan §6.1).
PaymentStatus = PaymentOrderStatus


class PaymentOrder(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="payment_orders",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="payment_orders",
    )
    appointment = models.OneToOneField(
        "appointments.Appointment",
        on_delete=models.PROTECT,
        related_name="payment_order",
    )
    gateway = models.CharField(max_length=32, default="razorpay")
    gateway_mode = models.CharField(
        max_length=8,
        default="test",
        help_text="test|live, stamped from settings at creation. A capture for a "
        "test-mode order can never confirm a live booking (S §A5).",
    )
    gateway_order_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text="Gateway order id (Phase 6); NULL until then, and NULLs do "
        "not collide (plan §3: unique gateway ids).",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=16,
        choices=PaymentOrderStatus.choices,
        default=PaymentOrderStatus.CREATED,
        db_index=True,
    )
    receipt = models.CharField(max_length=64, blank=True, default="")
    notes = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the gateway told us the money landed (never set by a client call).",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Mirror of the slot hold's expiry; drives `PENDING -> EXPIRED` (plan §6.1).",
    )

    objects = TenantScopedManager()

    class Meta:
        db_table = "payment_orders"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "status"), name="idx_orders_tenant_status"),
            models.Index(fields=("appointment_id",), name="idx_orders_appointment"),
            # The reconcile sweep reads "(still open) and (created before X)".
            models.Index(fields=("status", "created_at"), name="idx_orders_status_created"),
        ]

    def __str__(self) -> str:
        return f"{self.currency} {self.amount} / {self.appointment_id} ({self.status})"


class Payment(BaseModel):
    """Money that actually moved against a `PaymentOrder` (PRD §12).

    A separate row rather than a column on the order because a gateway can
    fail an attempt and the client can retry against the same order: one order
    may hold several `FAILED` attempts and at most one `SUCCESS`. The success
    is what the appointment confirmation and the refund flow key off, and
    `gateway_payment_id` is uniquely constrained so the same gateway event can
    never be recorded as two payments (plan §3, S §A5).
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    order = models.ForeignKey(
        "payments.PaymentOrder",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    gateway = models.CharField(max_length=32)
    gateway_payment_id = models.CharField(
        max_length=64,
        unique=True,
        help_text="Gateway payment id. Unique so a replayed capture cannot mint a second row.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=16,
        choices=PaymentOrderStatus.choices,
        default=PaymentOrderStatus.PENDING,
        db_index=True,
    )
    method = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Gateway instrument (card/upi/netbanking) when reported.",
    )
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "payments"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "status"), name="idx_payments_tenant_status"),
            models.Index(fields=("order_id",), name="idx_payments_order"),
        ]
        constraints = [  # noqa: RUF012 - Django's own class-list style
            # At most one captured payment per order. Two rows both claiming to
            # have moved the money is a double charge; refuse it at the schema
            # rather than trusting the webhook handler to be called once.
            models.UniqueConstraint(
                fields=("order",),
                condition=models.Q(status=PaymentOrderStatus.SUCCESS),
                name="uniq_payments_order_success",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.gateway_payment_id} {self.currency} {self.amount} ({self.status})"


class RefundStatus(models.TextChoices):
    PENDING_ACTION = "PENDING_ACTION", "Pending action"
    SETTLED = "SETTLED", "Settled"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Refund(BaseModel):
    """A manual reversal awaiting a human (plan §6.2, D2).

    `PENDING_ACTION` means "an admin has asked for this, nobody has done it at
    the gateway yet" - the lawyer issues the refund in the Razorpay dashboard.
    `settle` is the only writer of `SETTLED`, and that action is the only thing
    in the codebase that moves the linked `Payment` to `REFUNDED`. There is no
    automatic path (`PaymentGateway.create_refund()` is deliberately unused),
    so the UI must never promise an instant refund.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=16,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING_ACTION,
        db_index=True,
    )
    reason = models.CharField(max_length=255, blank=True, default="")
    gateway_refund_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text="Set by an admin when the dashboard confirms the refund id.",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_requested",
    )
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds_settled",
    )
    settled_at = models.DateTimeField(null=True, blank=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "refunds"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "status"), name="idx_refunds_tenant_status"),
            models.Index(fields=("payment_id",), name="idx_refunds_payment"),
        ]

    def __str__(self) -> str:
        return f"{self.currency} {self.amount} -> payment {self.payment_id} ({self.status})"


class PaymentEventOutcome(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    APPLIED = "APPLIED", "Applied"
    DUPLICATE = "DUPLICATE", "Duplicate"
    UNMATCHED = "UNMATCHED", "Unmatched"
    IGNORED = "IGNORED", "Ignored"
    FAILED = "FAILED", "Failed"


class PaymentEvent(BaseModel):
    """Raw webhook envelope, persisted before any processing (plan §6 step 2).

    Deduped on `(gateway, event_id)`: the unique constraint is what makes a
    redelivery a cheap `IntegrityError` instead of a second confirmation. The
    payload is stored verbatim (JSON, not reserialized) so an incident review
    can see exactly what the gateway sent, and `signature` is kept because
    "was this signed correctly" is the first question anyone asks afterwards.
    """

    gateway = models.CharField(max_length=32)
    event_id = models.CharField(max_length=80)
    event_type = models.CharField(max_length=80, blank=True, default="")
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parsed body, stored as received. Signature is verified over the raw bytes.",
    )
    signature = models.CharField(max_length=256, blank=True, default="")
    gateway_order_id = models.CharField(max_length=64, blank=True, default="")
    outcome = models.CharField(
        max_length=16,
        choices=PaymentEventOutcome.choices,
        default=PaymentEventOutcome.RECEIVED,
    )
    detail = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()

    class Meta:
        db_table = "payment_events"
        ordering = ("-received_at",)
        constraints = [  # noqa: RUF012 - Django's own class-list style
            models.UniqueConstraint(
                fields=("gateway", "event_id"),
                name="uniq_payment_events_gateway_event",
            ),
        ]
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("event_type",), name="idx_payment_events_type"),
        ]

    def __str__(self) -> str:
        return f"{self.gateway}:{self.event_id} {self.event_type} ({self.outcome})"


__all__ = (
    "TERMINAL_PAYMENT_STATUSES",
    "Payment",
    "PaymentEvent",
    "PaymentEventOutcome",
    "PaymentOrder",
    "PaymentOrderStatus",
    "PaymentStatus",
    "Refund",
    "RefundStatus",
)
