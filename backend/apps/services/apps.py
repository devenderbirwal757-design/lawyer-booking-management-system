from __future__ import annotations

from django.apps import AppConfig


class ServicesConfig(AppConfig):
    name = "apps.services"
    label = "services"
    verbose_name = "Services"
    default_auto_field = "django.db.models.BigAutoField"
