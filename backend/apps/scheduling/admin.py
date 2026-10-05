"""Django admin for the availability calendar (plan §1 "internal debugging").

Recurring windows (`AvailabilityRule`) and one-off overrides/blockouts
(`AvailabilityException`) are edited here by support staff. Rule rows are
never deleted - a window is made ineffective by shrinking its range - matching
the API surface, which exposes no DELETE for rules. Exceptions are transient
and genuinely deleteable. Writes are audited exactly like API writes.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.audit.audit import audit, snapshot
from apps.scheduling.models import AvailabilityException, AvailabilityRule

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _audited_save(request: Any, obj: Any, form: Any, change: bool, save: Any, action: str) -> None:
    before = snapshot(obj) if change else None
    save(request, obj, form, change)
    audit(
        action=action,
        entity_type=obj._meta.label_lower,
        entity_id=obj.pk,
        before=before,
        after=snapshot(obj),
        actor=request.user,
        tenant=obj.provider.tenant,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "provider",
        "weekday_display",
        "start_time",
        "end_time",
        "effective_from",
        "effective_to",
    )
    list_filter = ("weekday", "provider__tenant", "provider")
    search_fields = ("provider__name",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Weekday")
    def weekday_display(self, obj: AvailabilityRule) -> str:
        return WEEKDAYS[obj.weekday]

    def save_model(self, request: Any, obj: AvailabilityRule, form: Any, change: bool) -> None:
        action = (
            "scheduling.availability_rule.create"
            if not change
            else "scheduling.availability_rule.update"
        )
        _audited_save(
            request,
            obj,
            form,
            change,
            lambda r, o, f, c: super().save_model(r, o, f, c),
            action,
        )

    def has_delete_permission(self, request: Any, obj: AvailabilityRule | None = None) -> bool:
        return False


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("provider", "date", "start_time", "end_time", "type", "reason")
    list_filter = ("type", "date", "provider__tenant", "provider")
    search_fields = ("provider__name", "reason")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request: Any, obj: AvailabilityException, form: Any, change: bool) -> None:
        _audited_save(
            request,
            obj,
            form,
            change,
            lambda r, o, f, c: super().save_model(r, o, f, c),
            "scheduling.availability_exception.create"
            if not change
            else "scheduling.availability_exception.update",
        )
