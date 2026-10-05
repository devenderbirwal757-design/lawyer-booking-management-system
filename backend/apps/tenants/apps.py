from __future__ import annotations

from django.apps import AppConfig


class TenantsConfig(AppConfig):
    name = "apps.tenants"
    label = "tenants"
    verbose_name = "Tenants"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.tenants import checks  # noqa: F401 - register the tenant system checks

        super().ready()
