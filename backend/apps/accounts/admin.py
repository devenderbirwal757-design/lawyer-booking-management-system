"""Django admin for back-office users (plan §1 Phase 1 "internal debugging").

The `save_model` override is the Phase 1 audit wiring proof: any change made
through the admin panel (role changes, tenant moves, deactivation) lands in
`AuditLog` with a before/after diff, so an operator's actions are traceable
just like an API actor's.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from apps.accounts.models import RefreshSession, User
from apps.audit.audit import audit, snapshot


@admin.register(User)
class UserAdmin(DjangoUserAdmin):  # type: ignore[type-arg]
    ordering = ("email",)
    list_display = ("email", "full_name", "role", "tenant", "is_active", "is_staff", "created_at")
    list_filter = ("role", "is_active", "is_staff", "tenant")
    search_fields = ("email", "full_name")
    readonly_fields = ("date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password", "full_name")}),
        (
            "Practice",
            {"fields": ("tenant", "role")},
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2", "tenant", "role"),
            },
        ),
    )

    def save_model(self, request: Any, obj: User, form: Any, change: bool) -> None:
        before = snapshot(obj) if change else None
        super().save_model(request, obj, form, change)
        action = "user.update" if change else "user.create"
        after = snapshot(obj)
        audit(
            action=action,
            entity_type="accounts.user",
            entity_id=obj.pk,
            before=before,
            after=after,
            actor=request.user,
            tenant=obj.tenant,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT"),
        )


@admin.register(RefreshSession)
class RefreshSessionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("user", "tenant", "created_at", "revoked_at", "revoked_reason")
    list_filter = ("tenant", "revoked_reason")
    search_fields = ("user__email",)
    date_hierarchy = "created_at"
    readonly_fields = ("user", "tenant", "revoked_at", "revoked_reason", "created_at", "updated_at")

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_view_permission(self, request: Any, obj: RefreshSession | None = None) -> bool:
        return hasattr(request, "user") and request.user.is_authenticated

    def has_change_permission(self, request: Any, obj: RefreshSession | None = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: RefreshSession | None = None) -> bool:
        return False


admin.site.unregister(Group)
