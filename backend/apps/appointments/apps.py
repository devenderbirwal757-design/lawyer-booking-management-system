from __future__ import annotations

from django.apps import AppConfig


class AppointmentsConfig(AppConfig):
    name = "apps.appointments"
    label = "appointments"
    verbose_name = "Appointments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.appointments import signals  # noqa: F401 - wire post_save/post_delete hooks

        super().ready()
