from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from common import schema  # noqa: F401 - register OpenAPI auth schemes

        from . import authentication  # noqa: F401 - define AdminJWTAuthentication
