"""Django admin for providers (plan §1 "internal debugging").

Soft-delete via `is_active` matches the model's destroy semantics elsewhere -
an operator deactivates, they do not delete.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.audit import audit, snapshot
from apps.providers.models import Provider


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "tenant", "email", "phone", "is_active", "created_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("name", "email", "phone")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request: Any, obj: Provider, form: Any, change: bool) -> None:
        before = snapshot(obj) if change else None
        super().save_model(request, obj, form, change)
        action = "provider.update" if change else "provider.create"
        audit(
            action=action,
            entity_type="providers.provider",
            entity_id=obj.pk,
            before=before,
            after=snapshot(obj),
            actor=request.user,
            tenant=obj.tenant,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )

    def delete_model(self, request: Any, obj: Provider) -> None:
        if obj.is_active:
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])

    def has_delete_permission(self, request: Any, obj: Provider | None = None) -> bool:
        return True
