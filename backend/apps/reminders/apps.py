from __future__ import annotations

from django.apps import AppConfig


class RemindersConfig(AppConfig):
    name = "apps.reminders"
    label = "reminders"
    verbose_name = "Reminders"
    default_auto_field = "django.db.models.BigAutoField"
