"""Payment serializers (plan §6, PRD §12).

The read side exposes gateway ids and amounts so a client can reconcile, and
nothing else - no key secret, no webhook secret, no raw webhook payload.

The write side is one input, `appointment_id`, and that is deliberate: there is
no serializer field anywhere in this module that accepts a status, an amount
that gets charged, or a gateway payment id. `amount` exists on `CreateOrderSerializer`
only so a client that sends one is *told* it is wrong (S §A5) instead of
having it silently dropped, which is the failure mode that makes a client
integrator believe their ₹1 test payment worked.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.payments.models import (
    Payment,
    PaymentEvent,
    PaymentOrder,
    PaymentOrderStatus,
    Refund,
    RefundStatus,
)


class PaymentOrderSerializer(serializers.ModelSerializer[PaymentOrder]):
    """The order as the owning customer sees it."""

    # Declared explicitly (rather than left to ModelSerializer) so the read
    # shape is pinned, and `read_only` restated on the declaration: an
    # explicitly-declared field ignores `read_only_fields`, which would
    # otherwise leave `amount` silently writable on a serializer that has no
    # write route at all.
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    appointment_status = serializers.CharField(source="appointment.status", read_only=True)

    class Meta:
        model = PaymentOrder
        fields = (
            "id",
            "appointment_id",
            "gateway",
            "gateway_mode",
            "amount",
            "currency",
            "status",
            "appointment_status",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields


class CreateOrderSerializer(serializers.Serializer[dict[str, Any]]):
    """Start checkout for an appointment the customer already holds.

    `amount` is write-only and advisory: it is checked against the server-side
    price and rejected on mismatch, never used to charge (S §A5).
    """

    appointment_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Optional. Rejected when it differs from the service price.",
    )


class PaymentCustomerSerializer(serializers.Serializer[dict[str, Any]]):
    """Just enough of a client to label a row in the admin tables.

    Exposed to admins only. The customer list endpoint is a separate, richer
    surface so this stays a reference rather than a second way to enumerate
    clients.
    """

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_null=True)


class PaymentSerializer(serializers.ModelSerializer[Payment]):
    """A payment attempt.

    `customer` and `gateway_order_id` are denormalised in so the admin table
    renders one row per payment without a second request; `gateway_order_id`
    comes from the parent order, not from the attempt.
    """

    customer = PaymentCustomerSerializer(read_only=True)
    gateway_order_id = serializers.CharField(source="order.gateway_order_id", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "appointment_id",
            "order_id",
            "gateway",
            "gateway_payment_id",
            "gateway_order_id",
            "customer",
            "amount",
            "currency",
            "status",
            "method",
            "failure_reason",
            "paid_at",
            "created_at",
        )
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer[Refund]):
    """Refund as the admin sees it. `amount` defaults to the full capture."""

    payment_id = serializers.UUIDField(read_only=True)
    appointment_id = serializers.UUIDField(source="payment.appointment_id", read_only=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = Refund
        fields = (
            "id",
            "payment_id",
            "appointment_id",
            "amount",
            "currency",
            "status",
            "reason",
            "gateway_refund_id",
            "requested_by",
            "settled_by",
            "settled_at",
            "created_at",
        )
        read_only_fields = (
            "id",
            "payment_id",
            "appointment_id",
            "currency",
            "status",
            "gateway_refund_id",
            "requested_by",
            "settled_by",
            "settled_at",
            "created_at",
        )

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("A refund must be for a positive amount.")
        return value


class SettleRefundSerializer(serializers.Serializer[dict[str, Any]]):
    """Mark a `PENDING_ACTION` refund as done at the gateway (plan §6.2)."""

    gateway_refund_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
        help_text="The id the gateway dashboard shows, when available.",
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class PaymentEventSerializer(serializers.ModelSerializer[PaymentEvent]):
    """Read-only audit of webhook deliveries (admin troubleshooting)."""

    class Meta:
        model = PaymentEvent
        fields = (
            "id",
            "gateway",
            "event_id",
            "event_type",
            "gateway_order_id",
            "outcome",
            "detail",
            "signature",
            "payload",
            "received_at",
            "processed_at",
        )
        read_only_fields = fields


class PaymentStatusChoicesSerializer(serializers.Serializer[dict[str, Any]]):
    """A tiny endpoint helper so a client can render statuses it may see."""

    order_statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=PaymentOrderStatus.choices), read_only=True
    )
    refund_statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=RefundStatus.choices), read_only=True
    )


__all__ = (
    "CreateOrderSerializer",
    "PaymentEventSerializer",
    "PaymentOrderSerializer",
    "PaymentSerializer",
    "PaymentStatusChoicesSerializer",
    "RefundSerializer",
    "SettleRefundSerializer",
)
