from __future__ import annotations

from django.apps import AppConfig


class CommonConfig(AppConfig):
    name = "common"
    verbose_name = "Common"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from common.logging import configure_logging

        configure_logging()
