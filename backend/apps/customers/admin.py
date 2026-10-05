"""Django admin for customers (plan §1 "internal debugging", Phase 3 §6.3).

Customers are soft-deleted via `is_active` like providers - deactivating a
client blocks future OTP logins but keeps their booking history intact and
auditable (no PROTECT surprises on appointment rows that reference them).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.audit import audit, snapshot
from apps.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("phone", "name", "email", "tenant", "is_active", "created_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("phone", "name", "email")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request: Any, obj: Customer, form: Any, change: bool) -> None:
        before = snapshot(obj) if change else None
        super().save_model(request, obj, form, change)
        action = "customer.update" if change else "customer.create"
        audit(
            action=action,
            entity_type="customers.customer",
            entity_id=obj.pk,
            before=before,
            after=snapshot(obj),
            actor=request.user,
            tenant=obj.tenant,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

    def delete_model(self, request: Any, obj: Customer) -> None:
        if obj.is_active:
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])

    def has_delete_permission(self, request: Any, obj: Customer | None = None) -> bool:
        return True


__all__ = ("CustomerAdmin",)
