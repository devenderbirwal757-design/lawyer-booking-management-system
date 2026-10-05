"""Django admin for appointments (plan §1 "internal debugging").

Support staff confirm, complete, cancel and no-show bookings here; every write
is audited exactly like an API write. Status is never set directly - the
`Appointment` model has no `status` setter here either (the API funnels
transitions through the domain services), so the admin mirrors the API's
guarantee that a booking never skips a step.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.appointments.models import Appointment, AppointmentStatusHistory
from apps.audit.audit import audit, snapshot


def _audited_save(
    request: Any, obj: Appointment, form: Any, change: bool, save: Any, action: str
) -> None:
    before = snapshot(obj) if change else None
    save(request, obj, form, change)
    audit(
        action=action,
        entity_type=obj._meta.label_lower,
        entity_id=obj.pk,
        before=before,
        after=snapshot(obj),
        actor=request.user,
        tenant=obj.tenant,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT"),
    )


class StatusHistoryInline(admin.TabularInline):  # type: ignore[type-arg]
    model = AppointmentStatusHistory
    extra = 0
    can_delete = False
    # The trail is evidence, not content: nothing in it is editable, including
    # the actor, or an audit leg could be rewritten after the fact.
    readonly_fields = (
        "id",
        "from_status",
        "to_status",
        "actor_type",
        "actor_id",
        "note",
        "created_at",
    )

    def has_add_permission(self, request: Any, obj: Appointment | None = None) -> bool:
        return False


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "id",
        "customer",
        "provider",
        "service",
        "start_at",
        "end_at",
        "status",
        "created_via",
        "created_at",
    )
    list_filter = ("status", "created_via", "provider__tenant", "provider", "service")
    search_fields = ("customer__name", "customer__phone", "id")
    readonly_fields = (
        "id",
        "start_at",
        "end_at",
        "status",
        "slot_hold_expires_at",
        "cancellation_reason",
        "rescheduled_from",
        "created_via",
        "created_at",
        "updated_at",
    )
    inlines = (StatusHistoryInline,)

    def has_add_permission(self, request: Any) -> bool:
        # Bookings are created by clients or the API; the admin's job is
        # running the lifecycle, not carving arbitrary slots.
        return False

    def has_delete_permission(self, request: Any, obj: Appointment | None = None) -> bool:
        # No hard deletes: rows are windows into auditable history.
        return False

    def save_model(self, request: Any, obj: Appointment, form: Any, change: bool) -> None:
        # `customer_notes` is the one editable field (the API's notes-only PATCH
        # has the same shape). Anything else that changed is refused here rather
        # than persisted, so a lifecycle field can never be nudged from the
        # admin behind the state machine's back.
        if not change or set(form.changed_data) <= {"customer_notes"}:
            _audited_save(
                request,
                obj,
                form,
                change,
                lambda r, o, f, c: super().save_model(r, o, f, c),
                "appointments.appointment.update",
            )
            return
        raise PermissionError(
            "Appointment fields other than notes cannot be edited through the admin."
        )


__all__ = ("AppointmentAdmin",)
