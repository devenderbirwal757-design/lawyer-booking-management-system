"""Tenant: the lawyer's practice. Every core table hangs off one (plan §3).

`Tenant` is the root of the hierarchy the PRD describes in §23 - providers,
customers, services, appointments and payments all belong to exactly one. V1
runs a single lawyer (PRD §32), but keeping `tenant_id` on every core table is
what makes the schema reusable, and S §A4 makes the isolation testable.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models

from common.models import BaseModel


class TenantStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"


class Tenant(BaseModel):
    """A practice, and the edge where lawyer-specific config lives.

    `profile` holds the vertical's configuration (PRD §32: "core generic, config
    at edge") - consultation durations, catalogue copy, FAQ entries - so the
    core models never hard-code a "lawyer" concept. It is unvalidated JSON on
    purpose: its shape belongs to the vertical, and the plan's §11 open
    questions cover validating it later.

    Note this model is deliberately *not* tenant-scoped: it is the tenant.
    """

    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    timezone = models.CharField(max_length=64, default="UTC")
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=16,
        choices=TenantStatus.choices,
        default=TenantStatus.ACTIVE,
        db_index=True,
    )
    profile = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "tenants"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not self.timezone:
            errors["timezone"] = "Required."
        else:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                errors["timezone"] = f'Unknown IANA timezone "{self.timezone}".'
        currency = (self.currency or "").strip()
        if len(currency) != 3 or not currency.isalpha():
            errors["currency"] = "Must be a 3-letter ISO 4217 code."
        if errors:
            raise ValidationError(errors)

    def available_currencies(self) -> list[str]:
        """Currencies the tenant may charge in, defaulting to its own."""
        configured = (self.profile or {}).get("currencies")
        if isinstance(configured, list) and configured:
            return [str(code).upper() for code in configured]
        return [self.currency]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.pk),
            "name": self.name,
            "slug": self.slug,
            "timezone": self.timezone,
            "currency": self.currency,
            "status": self.status,
        }
