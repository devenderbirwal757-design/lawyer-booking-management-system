"""Reminder models (Phase 8)."""

from __future__ import annotations

from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager


class Reminder(BaseModel):
    class Kind(models.TextChoices):
        UPCOMING = "UPCOMING", "Upcoming"
        DAY_OF = "DAY_OF", "Day of"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="reminders",
    )
    appointment = models.ForeignKey(
        "appointments.Appointment",
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    error = models.TextField(blank=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "reminders_reminder"
        constraints = [
            models.UniqueConstraint(
                fields=("appointment", "kind"),
                name="uniq_reminder_appointment_kind",
            )
        ]
        indexes = [
            models.Index(
                fields=("tenant_id", "status", "scheduled_for"),
                name="idx_reminders_t_stat_sched",
            )
        ]
        ordering = ("scheduled_for",)

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.appointment_id}:{self.kind}:{self.status}"
