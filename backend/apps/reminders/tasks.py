"""Reminder tasks (Phase 8)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.notifications.models import NotificationTemplate
from apps.notifications.services import create_notification
from apps.notifications.tasks import enqueue_notification
from apps.reminders.models import Reminder

now = timezone.now

logger = logging.getLogger(__name__)


def create_reminders_for_appointment(appointment: Appointment) -> list[Reminder]:
    """Create reminders for a confirmed appointment based on tenant offsets."""
    # Offsets default to simple values if not configured on tenant
    tenant = appointment.tenant
    offsets = getattr(tenant, "reminder_offsets", None) or {}

    upcoming_minutes = offsets.get("upcoming_minutes", 60)
    day_of_minutes = offsets.get("day_of_minutes", 30)

    reminders: list[Reminder] = []
    for kind, minutes in (
        (Reminder.Kind.UPCOMING, upcoming_minutes),
        (Reminder.Kind.DAY_OF, day_of_minutes),
    ):
        scheduled = appointment.start_at
        # naive subtraction handled by datetime arithmetic; USE_TZ is True
        from datetime import timedelta

        scheduled_for = scheduled - timedelta(minutes=minutes) if scheduled else now()

        try:
            r, created = Reminder.objects.get_or_create(
                tenant=appointment.tenant,
                appointment=appointment,
                kind=kind,
                defaults={
                    "status": Reminder.Status.PENDING,
                    "scheduled_for": scheduled_for,
                },
            )
            if not created:
                # reschedule if appointment moved
                if r.scheduled_for != scheduled_for:
                    r.scheduled_for = scheduled_for
                    r.status = Reminder.Status.PENDING
                    r.attempts = 0
                    r.error = ""
                    r.save(
                        update_fields=("scheduled_for", "status", "attempts", "error", "updated_at")
                    )
            reminders.append(r)
        except Exception as exc:
            logger.exception("reminder.create_failed", exc_info=exc)

    return reminders


@shared_task(
    bind=True,
    queue="notifications",
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def dispatch_due_reminders(self: Any) -> int:
    at = now()
    # select pending due reminders, skip_locked to avoid duplication across workers
    qs = (
        Reminder.objects.select_related("appointment", "tenant", "appointment__customer")
        .filter(
            status=Reminder.Status.PENDING,
            scheduled_for__lte=at,
        )
        .filter(
            Q(appointment__status=AppointmentStatus.CONFIRMED)
            | Q(appointment__status=AppointmentStatus.PENDING_PAYMENT)
        )
        .order_by("scheduled_for")
    )
    sent_count = 0
    for reminder in qs:
        try:
            with transaction.atomic():
                # claim row if still pending/due
                locked = Reminder.objects.select_for_update(skip_locked=True).get(pk=reminder.pk)
                if locked.status != Reminder.Status.PENDING:
                    continue
                if locked.scheduled_for > at:
                    continue
                # create notification
                channel = NotificationTemplate.Channel.EMAIL
                notification = create_notification(
                    tenant_id=locked.tenant_id,
                    event=(
                        NotificationTemplate.Event.REMINDER_UPCOMING
                        if locked.kind == Reminder.Kind.UPCOMING
                        else NotificationTemplate.Event.REMINDER_DAY_OF
                    ),
                    channel=channel,
                    to_email=locked.appointment.customer.email or ""
                    if locked.appointment.customer
                    else "",
                    context={
                        "name": locked.appointment.customer.name
                        if locked.appointment.customer
                        else "",
                        "service": getattr(locked.appointment.service, "name", ""),
                        "start_at": locked.appointment.start_at.isoformat()
                        if locked.appointment.start_at
                        else "",
                    },
                    appointment_id=locked.appointment_id,
                    customer_id=locked.appointment.customer_id
                    if locked.appointment.customer_id
                    else None,
                )
                locked.status = Reminder.Status.SENT
                locked.sent_at = at
                locked.save(update_fields=("status", "sent_at", "updated_at"))
            enqueue_notification(notification)
            sent_count += 1
        except Exception as exc:
            logger.exception("reminder.dispatch_failed", exc_info=exc)
            try:
                r = Reminder.objects.get(pk=reminder.pk)
                r.attempts += 1
                if r.attempts >= r.max_attempts:
                    r.status = Reminder.Status.FAILED
                r.error = str(exc)[:2000]
                r.save(update_fields=("attempts", "status", "error", "updated_at"))
            except Exception:
                pass

    return sent_count
