"""Django admin for OTP codes (plan §1 "internal debugging", S §A3).

Read-only on purpose: codes are transient, single-shot secrets and an operator
should never be able to mint or edit one. The plaintext code is never stored,
so the admin can only ever show the digest - which is also the "hashed at rest"
proof surface for the security review (S §A3).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin

from apps.auth_otp.models import PhoneOtp


@admin.register(PhoneOtp)
class PhoneOtpAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("phone", "tenant", "customer", "expires_at", "attempts", "consumed_at")
    list_filter = ("tenant",)
    search_fields = ("phone",)
    readonly_fields = (
        "phone",
        "tenant",
        "customer",
        "salt",
        "code_hash",
        "expires_at",
        "attempts",
        "consumed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: Any) -> bool:
        return False

    def has_change_permission(self, request: Any, obj: PhoneOtp | None = None) -> bool:
        return False

    def has_delete_permission(self, request: Any, obj: PhoneOtp | None = None) -> bool:
        return False


__all__ = ("PhoneOtpAdmin",)
