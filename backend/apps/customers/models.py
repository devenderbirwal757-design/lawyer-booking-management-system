"""Customer: the client side of the practice (plan §6.3, D3).

Customers are a *separate* principal from admin `User`s: they authenticate by
phone OTP (`apps.auth_otp`, Phase 4), have no password, and a customer token can
never reach `/admin/*` (S §A3). `phone` is the identity key, normalised to
E.164 and unique per tenant; `email` is optional per D3 and unique per tenant
when present (a `UniqueConstraint` with a null-friendly condition).

`is_active` is the soft-delete flag and the one that auth refuses: a
deactivated customer's token is rejected by `CustomerJWTAuthentication`.

Every read is tenant-scoped through `TenantScopedManager`, the same fail-closed
contract as every other tenant table (S §A4).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.customers.phone import PhoneValidationError, normalize_phone
from common.models import BaseModel
from common.querysets import TenantScopedManager


class Customer(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="customers",
        help_text="The practice this client belongs to.",
    )
    phone = models.CharField(
        max_length=20,
        db_index=True,
        help_text="E.164 phone number, e.g. +919876543210. Unique per tenant.",
    )
    email = models.EmailField(  # noqa: DJ001 - D3 requires "unique per tenant WHEN SET":
        # a NULL represents "no email on file", which an empty string would
        # collide with in the conditional UniqueConstraint below.
        null=True,
        blank=True,
        help_text="Optional per D3. Unique per tenant when present.",
    )
    name = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default="")

    objects = TenantScopedManager()

    class Meta:
        db_table = "customers"
        ordering = ("-created_at",)
        constraints = [  # noqa: RUF012 - Django's own class-list style
            models.UniqueConstraint(
                fields=("tenant", "phone"),
                name="uniq_customer_phone_per_tenant",
            ),
            models.UniqueConstraint(
                fields=("tenant", "email"),
                condition=Q(email__isnull=False),
                name="uniq_customer_email_per_tenant",
            ),
        ]
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(
                fields=("tenant_id", "phone"),
                name="idx_customers_tenant_phone",
            ),
            models.Index(
                fields=("tenant_id", "is_active"),
                name="idx_customers_tenant_active",
            ),
        ]

    def __str__(self) -> str:
        return self.name or self.phone

    @property
    def is_authenticated(self) -> bool:
        """Always true - and deliberately not a database column.

        `CustomerJWTAuthentication` only resolves a customer from a valid,
        customer-scoped token and refuses deactivated rows, so a `Customer`
        instance reaching a view *is* an authenticated principal. DRF's
        throttles, `IsAuthenticated` and the tenant middleware all read this
        attribute, so its absence made every customer-authenticated request
        raise `AttributeError` instead of answering.

        It is not a stand-in for `User`: nothing grants admin rights from it -
        `IsAdmin` requires `is_tenant_admin`, which only `User` has, and
        `CustomerJWTAuthentication` never populates `request.user` for a
        customer-scoped token on the admin surface.
        """
        return True

    @classmethod
    def _clean_phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except PhoneValidationError as err:
            raise ValidationError({"phone": str(err)}) from err

    def clean(self) -> None:
        super().clean()
        if self.phone:
            self.phone = self._clean_phone(self.phone)
        if self.email:
            self.email = self.email.strip().lower()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.phone:
            self.phone = self._clean_phone(self.phone)
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


__all__ = ("Customer",)
