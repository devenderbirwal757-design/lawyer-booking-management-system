"""Availability: recurring rules and one-off exceptions (plan §3, D4).

- `AvailabilityRule`: the practice's normal week. One row per
  `(provider, weekday)` window, optionally restricted to an effective date
  range. Deliberately has **no interval field** (D4): slot spacing comes only
  from `service.duration_minutes + buffer_after_minutes`, so a 30-minute and a
  45-minute service interleave on one concept instead of begging for a second
  grid field that would drift out of sync.
- `AvailabilityException`: a one-off day. `OVERRIDE` replaces the weekday
  rules for that date; `BLOCKED` removes a window. A holiday, a court
  appearance, or "closed 1pm Friday".

Neither row carries `tenant_id`; the tenant is `provider__tenant_id`, and the
managers below enforce isolation through that join, so the fail-closed
guarantee holds exactly as it does for rows that store the tenant directly.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager, TenantScopedQuerySet


class ExceptionType(models.TextChoices):
    BLOCKED = "BLOCKED", "Blocked"
    OVERRIDE = "OVERRIDE", "Override"


class _SchedulingQuerySet(TenantScopedQuerySet[Any]):
    tenant_field = "provider__tenant_id"


class _SchedulingManager(TenantScopedManager[Any]):
    queryset_class = _SchedulingQuerySet


class AvailabilityRule(BaseModel):
    """A recurring working-hours window, e.g. Mondays 10:00-13:00."""

    provider = models.ForeignKey(
        "providers.Provider",
        on_delete=models.PROTECT,
        related_name="rules",
        help_text="Whose week this is.",
    )
    weekday = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        help_text="0 = Monday ... 6 = Sunday (ISO weekday).",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    objects = _SchedulingManager()

    class Meta:
        db_table = "availability_rules"
        ordering = ("weekday", "start_time")
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(
                fields=("provider_id", "weekday", "effective_from", "effective_to"),
                name="idx_avrules_provider_weekday",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Weekday {self.weekday} {self.start_time}-{self.end_time} "
            f"(provider {self.provider_id})"
        )

    def is_effective_on(self, day: date) -> bool:
        if self.effective_from is not None and day < self.effective_from:
            return False
        if self.effective_to is not None and day > self.effective_to:
            return False
        return True

    def overlaps(self, other: AvailabilityRule) -> bool:
        """True when both rules apply to a shared weekday on some shared date."""
        if self.provider_id != other.provider_id or self.weekday != other.weekday:
            return False
        a_from = self.effective_from or date.min
        a_to = self.effective_to or date.max
        b_from = other.effective_from or date.min
        b_to = other.effective_to or date.max
        if a_from > b_to or b_from > a_to:
            return False
        return not (self.end_time <= other.start_time or other.end_time <= self.start_time)

    def conflicts(self) -> list[AvailabilityRule]:
        """Existing rules that would overlap this one, excluding itself."""
        qs = (
            type(self)
            .objects.unfiltered()
            .filter(
                provider_id=self.provider_id,
                weekday=self.weekday,
            )
        )
        if self.pk is not None:
            qs = qs.exclude(pk=self.pk)
        return [rule for rule in qs if self.overlaps(rule)]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "End time must be after start time."
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "Effective end must be after effective start."
        if not errors and self.provider_id and self.start_time and self.end_time:
            if self.conflicts():
                errors["weekday"] = "This window overlaps another rule for the same weekday."
        if errors:
            raise ValidationError(errors)


class AvailabilityException(BaseModel):
    """A one-off change for a single date: `BLOCKED` or `OVERRIDE`."""

    provider = models.ForeignKey(
        "providers.Provider",
        on_delete=models.PROTECT,
        related_name="exceptions",
        help_text="Whose calendar this exception edits.",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    type = models.CharField(
        max_length=16,
        choices=ExceptionType.choices,
        default=ExceptionType.BLOCKED,
        db_index=True,
    )
    reason = models.CharField(max_length=200, blank=True, default="")

    objects = _SchedulingManager()

    class Meta:
        db_table = "availability_exceptions"
        ordering = ("date", "start_time")
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("provider_id", "date"), name="idx_avexc_provider_date"),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.date} {self.start_time}-{self.end_time}"

    def window_as(self, zone: str) -> tuple[datetime, datetime]:
        tz = ZoneInfo(zone)
        return (
            datetime.combine(self.date, self.start_time, tzinfo=tz),
            datetime.combine(self.date, self.end_time, tzinfo=tz),
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "End time must be after start time."
        if errors:
            raise ValidationError(errors)


__all__ = (
    "AvailabilityException",
    "AvailabilityRule",
    "ExceptionType",
    "_SchedulingManager",
)
