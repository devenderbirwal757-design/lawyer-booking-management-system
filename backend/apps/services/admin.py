"""Django admin for the service catalogue (plan §1 "internal debugging").

Writes here are audited exactly like API writes: `save_model` records a
before/after diff in `AuditLog`, so a price changed by an operator is as
traceable as one changed over the API.

Delete is disabled on purpose: services must never be hard-deleted (they hold
PROTECT once appointments reference them, and the API's DELETE only
soft-deletes). The catalogue is edited or deactivated here, destroyed only
through the articulated API path.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.audit import audit, snapshot
from apps.services.models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "name",
        "slug",
        "tenant",
        "status",
        "currency",
        "price_amount",
        "duration_minutes",
        "updated_at",
    )
    list_filter = ("status", "tenant", "requires_payment")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}  # noqa: RUF012 - Django's own style
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)

    def save_model(self, request: Any, obj: Service, form: Any, change: bool) -> None:
        before = snapshot(obj) if change else None
        super().save_model(request, obj, form, change)
        action = "service.update" if change else "service.create"
        after = snapshot(obj)
        audit(
            action=action,
            entity_type="services.service",
            entity_id=obj.pk,
            before=before,
            after=after,
            actor=request.user,
            tenant=obj.tenant,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

    def has_delete_permission(self, request: Any, obj: Service | None = None) -> bool:
        # The only deletion path is the API's soft-delete (plan §2 Phase 2).
        return False
