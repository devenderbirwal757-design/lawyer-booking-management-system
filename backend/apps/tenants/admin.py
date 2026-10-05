"""Django admin for tenants (plan §1 Phase 1 "internal debugging").

Registration is intentionally read-mostly: `profile` is the vertical-config
JSON edge and is shown read-only to discourage hand-editing it into a shape
the scheduler cannot parse.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.tenants.models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "slug", "timezone", "currency", "status", "created_at")
    list_filter = ("status", "timezone")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}  # noqa: RUF012 - Django's own style
    readonly_fields = ("profile", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "slug")}),
        ("Region & money", {"fields": ("timezone", "currency", "status")}),
        ("Vertical config", {"fields": ("profile",)}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_view_permission(self, request: Any, obj: Tenant | None = None) -> bool:
        return hasattr(request, "user") and request.user.is_authenticated

    def has_delete_permission(self, request: Any, obj: Tenant | None = None) -> bool:
        return False
