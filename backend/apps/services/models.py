"""Bookable services and pricing (plan §3, PRD §5.2).

A `Service` is one line in the practice's catalogue - "Initial Consultation",
30 minutes, ₹500. It hangs off a tenant (never hard-deleted once referenced:
appointments arrive in Phase 5 and hold a PROTECT foreign key, so Django
itself will refuse a hard delete that would orphan a booking).

Delete semantics are deliberately `status`-based, not a deleted row
(plan §2 Phase 2): `DELETED` hides a service everywhere while keeping the row
auditable, and nothing else in the system goes through a destructive path.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

from common.models import BaseModel
from common.querysets import TenantScopedManager


class ServiceStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    DELETED = "DELETED", "Deleted"


#: §A8 bounds a service duration to stop a booking-DoS; 720min = 12 working
#: hours, far beyond any legal service.
MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 720
#: Turnaround on either side of a booking (plan §3.1, `buffer_after` default 5).
MAX_BUFFER_MINUTES = 240
#: Nothing is offered for free/non-positive (S §A8 "negative/zero price").
MIN_PRICE = Decimal("0.01")


class Service(BaseModel):
    """A bookable catalogue line, scoped to exactly one tenant.

    `slug` is the public identity (plan §4 `GET /services/{slug}`) and is
    unique per tenant; it is auto-generated from the name when not supplied.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="services",
        help_text="The practice this service belongs to; PROTECT so a referenced "
        "service can never be hard-deleted once appointments exist.",
    )
    provider = models.ForeignKey(
        "providers.Provider",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="services",
        help_text="Who delivers this service. Required before the service can be "
        "booked/slotted; nullable only for rows created before providers existed.",
    )
    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True, default="")
    duration_minutes = models.PositiveIntegerField(
        validators=[
            MinValueValidator(MIN_DURATION_MINUTES),
            MaxValueValidator(MAX_DURATION_MINUTES),
        ]
    )
    buffer_before_minutes = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(MAX_BUFFER_MINUTES)]
    )
    buffer_after_minutes = models.PositiveIntegerField(
        default=5, validators=[MaxValueValidator(MAX_BUFFER_MINUTES)]
    )
    price_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(MIN_PRICE)],
    )
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=16,
        choices=ServiceStatus.choices,
        default=ServiceStatus.ACTIVE,
        db_index=True,
    )
    requires_payment = models.BooleanField(default=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "services"
        ordering = ("name",)
        constraints = [  # noqa: RUF012 - Django's own class-list style
            models.UniqueConstraint(fields=("tenant", "slug"), name="uniq_services_tenant_slug"),
        ]
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "status"), name="idx_services_tenant_status"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency} {self.price_amount})"

    @property
    def is_active(self) -> bool:
        """True when the service may be publicly listed and booked."""
        return self.status == ServiceStatus.ACTIVE

    @classmethod
    def make_slug(cls, tenant: Any, name: str) -> str:
        """A slug unique within the tenant, generated from `name`.

        `slugify` gives "Initial Consultation" -> "initial-consultation";
        collisions get a numeric suffix ("initial-consultation-2"). Runs
        unfiltered on purpose: slug uniqueness is a *tenant-wide* fact and
        must not depend on the current request context.
        """
        base = slugify(name)[:80] or "service"
        used = set(cls.objects.unfiltered().filter(tenant=tenant).values_list("slug", flat=True))
        candidate = base
        counter = 2
        while candidate in used:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not (self.currency or "").strip():
            errors["currency"] = "Required."
        elif len(self.currency) != 3 or not self.currency.isalpha():
            errors["currency"] = "Must be a 3-letter ISO 4217 code."
        if errors:
            raise ValidationError(errors)


__all__ = (
    "MAX_BUFFER_MINUTES",
    "MAX_DURATION_MINUTES",
    "MIN_DURATION_MINUTES",
    "Service",
    "ServiceStatus",
)
