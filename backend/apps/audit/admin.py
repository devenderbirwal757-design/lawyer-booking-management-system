"""Django admin for the audit log: internal debugging only, read-only.

The log must never be editable from the admin, or the whole point of an
immutable history is gone. `has_*_permission` on the non-list verbs return
False so rows cannot be added, changed or deleted through the UI (an admin can
still read the log, which is the debugging surface the plan asks for).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "created_at",
        "action",
        "actor_type",
        "actor_id",
        "entity_type",
        "entity_id",
        "tenant",
    )
    list_filter = ("action", "actor_type", "entity_type", "tenant")
    search_fields = ("actor_id", "entity_id")
    date_hierarchy = "created_at"
    readonly_fields = (
        "tenant",
        "actor_type",
        "actor_id",
        "action",
        "entity_type",
        "entity_id",
        "before",
        "after",
        "ip",
        "user_agent",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_view_permission(self, request: Any, obj: AuditLog | None = None) -> bool:
        # Read-only is still readable: the admin exists for internal debugging.
        return hasattr(request, "user") and request.user.is_authenticated

    def has_change_permission(self, request: Any, obj: AuditLog | None = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: AuditLog | None = None) -> bool:
        return False
