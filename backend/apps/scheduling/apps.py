from __future__ import annotations

from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"
    label = "scheduling"
    verbose_name = "Scheduling"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.scheduling import signals  # noqa: F401 - wire post_save/post_delete hooks

        super().ready()
