"""Models that exist only to test the shared `common/` layer.

The real domain models (Tenant, Customer, Service, ...) arrive in Phases 1-6.
`Widget` is a minimal tenant-scoped model so the Phase 0 seams -
`TenantScopedManager`, `TenantScopedQuerySet`, `BaseViewSet` tenant filtering,
soft delete and the error envelope - are verified against a real database
rather than mocks.

Registered in INSTALLED_APPS by `config/settings/test.py` only.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from common.models import BaseModel
from common.querysets import TenantScopedManager, TenantScopedQuerySet


class WidgetQuerySet(TenantScopedQuerySet["Widget"]):
    def expensive(self) -> WidgetQuerySet:
        return self.filter(is_active=True)


class Widget(BaseModel):
    """Stand-in for a tenant-scoped domain model."""

    tenant_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    objects = TenantScopedManager.from_queryset(WidgetQuerySet)()

    class Meta:
        db_table = "test_widgets"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ActiveWidgetManager(models.Manager["Widget"]):
    def get_queryset(self) -> Any:
        return super().get_queryset().filter(is_active=True)
