"""Provider: the person whose calendar is being booked (plan §3).

Every core table hangs off a tenant, and providers are no exception. V1 runs a
single provider per practice (plan §1 "single tenant + single provider in
MVP"), but the many-to-one shape is what keeps the schema reusable when a
practice grows.

`is_active` is the soft-delete flag: `BaseViewSet.perform_destroy` sets it
False rather than deleting, and the public profile hides inactive providers.
PROTECT on `tenant` means a provider is never silently orphaned.
"""

from __future__ import annotations

from django.core.validators import MinLengthValidator
from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager


class Provider(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="providers",
        help_text="The practice this provider works for.",
    )
    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    objects = TenantScopedManager()

    class Meta:
        db_table = "providers"
        ordering = ("name",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant_id", "is_active"), name="idx_providers_tenant_active"),
        ]

    def __str__(self) -> str:
        return self.name


__all__ = ("Provider",)
