"""Phone OTP codes: hashed at rest, single-shot, short-lived (S §A3).

The code itself is never stored - only a salted SHA-256 digest (`code_hash`
plus a fresh `salt` per row). Five minutes to use it, at most
`DJANGO_OTP_MAX_ATTEMPTS` guesses, then it is consumed and dead. `consumed_at`
is set both by a successful verify and by the attempt lockout, so a row is a
closed book once it has served its purpose.

The row is tenant-scoped and also carries the normalized phone, which is what
enables the S §A3 send-window limits (`request_otp` counts recent rows) and the
per-tenant isolation of codes: a code issued to tenant A can never verify under
tenant B because `verify` only ever looks inside one tenant's rows.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import BaseModel
from common.querysets import TenantScopedManager


def _make_salt() -> str:
    return secrets.token_hex(8)


def hash_code(code: str, salt: str) -> str:
    """Salted SHA-256 digest of an OTP code.

    Chosen over Argon2/PBKDF2 deliberately: OTP codes are 6 random digits with
    a 5-minute life and hard attempt caps, so the expensive KDFs buy nothing
    here, and cheap salted hashing keeps verify latency below noise.
    """
    return hashlib.sha256(f"{salt}:{code}".encode("ascii")).hexdigest()


def constant_time_eq(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def generate_code(length: int = 6) -> str:
    return f"{secrets.randbelow(10**length):0{length}d}"


def otp_lifetime() -> timedelta:
    return timedelta(minutes=int(getattr(settings, "OTP_LIFETIME_MINUTES", 5)))


def max_attempts() -> int:
    return int(getattr(settings, "OTP_MAX_ATTEMPTS", 5))


class PhoneOtp(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="otp_codes",
        help_text="The practice the code was issued for.",
    )
    phone = models.CharField(max_length=20, help_text="Normalized E.164 phone.")
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="otp_codes",
        help_text="Filled in on successful verification only.",
    )
    salt = models.CharField(max_length=32, editable=False)
    code_hash = models.CharField(max_length=64, editable=False)
    expires_at = models.DateTimeField(db_index=True, editable=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)

    objects = TenantScopedManager()

    class Meta:
        db_table = "phone_otps"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(
                fields=("tenant_id", "phone", "created_at"),
                name="idx_otp_tenant_phone_window",
            ),
            models.Index(
                fields=("tenant_id", "phone", "consumed_at"),
                name="idx_otp_tenant_phone_consumed",
            ),
        ]

    @classmethod
    def issue(
        cls, tenant: Any, phone: str, *, expires_at: datetime | None = None
    ) -> tuple[PhoneOtp, str]:
        """Mint a new code and return (row, plaintext_code).

        The plaintext code is returned exactly once, for the send channel; it
        is never persisted. Bypasses the tenant-scoped manager because
        `create` touches only the row being made (see `TenantScopedManager`).
        """
        code = generate_code()
        salt = _make_salt()
        row = cls.objects.create(
            tenant=tenant,
            phone=phone,
            salt=salt,
            code_hash=hash_code(code, salt),
            expires_at=expires_at or (timezone.now() + otp_lifetime()),
            attempts=0,
        )
        return row, code

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or timezone.now())

    def is_valid(self, now: datetime | None = None) -> bool:
        return not self.is_consumed and not self.is_expired(now) and self.attempts < max_attempts()

    def code_matches(self, code: str) -> bool:
        return constant_time_eq(hash_code(code, self.salt), self.code_hash)

    def record_failed_attempt(self, *, now: datetime | None = None) -> int:
        """Count a wrong guess; lock the code out once attempts run out.

        Returns the number of attempts left (0 means the code was invalidated).
        """
        self.attempts += 1
        if self.attempts >= max_attempts():
            self.consumed_at = now or timezone.now()
        self.save(update_fields=["attempts", "consumed_at", "updated_at"])
        return max(max_attempts() - self.attempts, 0)

    def consume(self, customer: Any | None = None, *, now: datetime | None = None) -> None:
        self.customer_id = getattr(customer, "pk", None)
        self.consumed_at = now or timezone.now()
        self.save(update_fields=["customer_id", "consumed_at", "updated_at"])

    def __str__(self) -> str:
        return f"otp for {self.phone}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.pk),
            "phone": self.phone,
            "expires_at": self.expires_at,
            "attempts": self.attempts,
            "consumed_at": self.consumed_at,
        }


def otl_lifetime() -> timedelta:
    return otp_lifetime()


__all__ = (
    "PhoneOtp",
    "constant_time_eq",
    "generate_code",
    "hash_code",
    "max_attempts",
    "otp_lifetime",
)
