"""Django admin for the money tables (plan §6).

Deliberately read-only. An `Admin` form with a status dropdown is exactly the
back door plan §6 forbids - a `Payment` moved to `SUCCESS` in the Django admin
would be a confirmation with no gateway behind it, invisible to the webhook
dedupe and to the audit trail. The only writing path for these rows is the
service layer, reached through the API.

Deletion is refused for the same reason as editing: removing a payment or a
refund destroys the evidence that money moved, and reconciliation cannot
reconstruct what it never saw. The ledger is append-only from here.

`PaymentEvent.payload` is shown because "why did this not confirm" is
unanswerable without it; the signature column makes "was this signed correctly"
answerable too.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.audit import snapshot
from apps.payments.models import Payment, PaymentEvent, PaymentOrder, Refund


class PaymentInline(admin.TabularInline):  # type: ignore[type-arg]
    model = Payment
    extra = 0
    can_delete = False
    fields = ("gateway_payment_id", "amount", "currency", "status", "paid_at", "method")
    readonly_fields = fields
    max_num = 0

    def has_add_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "appointment",
        "tenant",
        "amount",
        "currency",
        "status",
        "gateway",
        "gateway_mode",
        "gateway_order_id",
        "created_at",
    )
    list_filter = ("status", "gateway", "gateway_mode", "tenant", "currency")
    search_fields = ("gateway_order_id", "receipt", "appointment_id", "customer__phone")
    readonly_fields = tuple(f.name for f in PaymentOrder._meta.fields)
    inlines = (PaymentInline,)
    date_hierarchy = "created_at"

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "gateway_payment_id",
        "appointment",
        "tenant",
        "amount",
        "currency",
        "status",
        "gateway",
        "paid_at",
    )
    list_filter = ("status", "gateway", "currency", "tenant")
    search_fields = ("gateway_payment_id", "order__gateway_order_id", "appointment_id")
    readonly_fields = tuple(f.name for f in Payment._meta.fields)
    date_hierarchy = "created_at"

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "payment",
        "tenant",
        "amount",
        "currency",
        "status",
        "reason",
        "gateway_refund_id",
        "settled_at",
    )
    list_filter = ("status", "tenant", "currency")
    search_fields = ("gateway_refund_id", "payment__gateway_payment_id")
    readonly_fields = tuple(f.name for f in Refund._meta.fields)

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "event_id",
        "gateway",
        "event_type",
        "outcome",
        "detail",
        "gateway_order_id",
        "received_at",
    )
    list_filter = ("gateway", "event_type", "outcome")
    search_fields = ("event_id", "gateway_order_id")
    readonly_fields = (*(f.name for f in PaymentEvent._meta.fields), "signature")
    date_hierarchy = "received_at"

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return False

    def save_model(self, request: Any, obj: Any, form: Any, change: bool) -> None:
        """Unreachable - `has_change_permission` is False - kept as a guard."""
        before = snapshot(obj) if change else None
        super().save_model(request, obj, form, change)
        from apps.audit.audit import audit

        audit(
            action="payment.event_update",
            entity_type="payments.paymentevent",
            entity_id=obj.pk,
            before=before,
            after=snapshot(obj),
            actor=request.user,
        )
