from __future__ import annotations

from django.apps import AppConfig


class AuthOtpConfig(AppConfig):
    name = "apps.auth_otp"
    label = "auth_otp"
    verbose_name = "Auth OTP"
    default_auto_field = "django.db.models.BigAutoField"
