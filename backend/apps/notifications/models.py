"""Notification models (Phase 7)."""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager


class NotificationTemplate(BaseModel):
    """Reusable, tenant-configurable message templates.

    Placeholders use double-curly braces, e.g. `{{name}}`, `{{service}}`.
    """

    class Event(models.TextChoices):
        BOOKING_CONFIRMED = "BOOKING_CONFIRMED", "Booking confirmed"
        PAYMENT_SUCCESS = "PAYMENT_SUCCESS", "Payment success"
        APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED", "Appointment cancelled"
        APPOINTMENT_RESCHEDULED = "APPOINTMENT_RESCHEDULED", "Appointment rescheduled"
        REMINDER_UPCOMING = "REMINDER_UPCOMING", "Reminder upcoming"
        REMINDER_DAY_OF = "REMINDER_DAY_OF", "Reminder day of"

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="notification_templates",
    )
    event = models.CharField(max_length=40, choices=Event.choices)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    placeholder_keys = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="Known placeholder keys for validation",
    )

    objects = TenantScopedManager()

    class Meta:
        db_table = "notifications_notificationtemplate"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "event", "channel"),
                name="uniq_notificationtemplate_tenant_event_channel",
            )
        ]
        ordering = ("event", "channel")

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.event}:{self.channel}"


class Notification(BaseModel):
    """A queued/sent notification instance.

    Status values match the minimal set needed for retries and audit.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    template = models.ForeignKey(
        "notifications.NotificationTemplate",
        on_delete=models.SET_NULL,
        null=True,
        related_name="notifications",
    )
    event = models.CharField(max_length=40, choices=NotificationTemplate.Event.choices)
    channel = models.CharField(max_length=20, choices=NotificationTemplate.Channel.choices)
    to_email = models.EmailField(blank=True)
    to_phone = models.CharField(max_length=32, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    sent_at = models.DateTimeField(null=True, blank=True)
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    objects = TenantScopedManager()

    class Meta:
        db_table = "notifications_notification"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.event}:{self.channel}:{self.status}"
