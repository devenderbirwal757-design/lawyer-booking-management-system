"""PhoneOtp hashing, expiry, lockout, and the service send-windows (S §A3).

The security plan's contract, tested here at the unit level:

- codes are hashed at rest (a salted SHA-256, never plaintext);
- codes expire after `OTP_LIFETIME_MINUTES` and expired codes are rejected;
- at most `OTP_MAX_ATTEMPTS` wrong guesses per code, then it is invalidated;
- send limits: <=3 codes/15 min and <=10/hour per number, DB-backed.

These tests drive the services with an explicit tenant and clock (no request
context), which is exactly how the DB-backed spend limits survive a restart.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

PHONE = "+919876543210"


@pytest.fixture
def tenant() -> Any:
    from apps.tenants.models import Tenant

    return Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone="UTC")


# ----------------------------------------------------------------- hashing
def test_code_is_hashed_at_rest_not_plaintext(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp

    row, code = PhoneOtp.issue(tenant, PHONE)

    assert row.code_hash != code
    assert len(row.code_hash) == 64
    assert row.salt and row.salt != code
    assert row.code_matches(code)
    assert not row.code_matches("000000")


# ----------------------------------------------------------------- expiry
def test_expired_code_is_invalid(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp

    past = timezone.now() - timedelta(seconds=1)
    row, _code = PhoneOtp.issue(tenant, PHONE, expires_at=past)

    assert row.is_expired(timezone.now())
    assert not row.is_valid(timezone.now())


def test_unexpired_code_is_valid(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp

    row, _code = PhoneOtp.issue(tenant, PHONE)
    assert not row.is_expired(timezone.now())
    assert row.is_valid(timezone.now())


# ----------------------------------------------------------------- lockout
def test_wrong_code_records_attempt(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp

    row, _code = PhoneOtp.issue(tenant, PHONE)
    row.record_failed_attempt()
    row.refresh_from_db()
    assert row.attempts == 1
    assert not row.is_consumed


def test_fifth_wrong_code_locks_the_code_out(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp

    row, _code = PhoneOtp.issue(tenant, PHONE)
    remaining = None
    for _ in range(5):
        remaining = row.record_failed_attempt()
    row.refresh_from_db()
    assert remaining == 0
    assert row.is_consumed
    assert not row.is_valid(timezone.now())


# ----------------------------------------------------------------- send windows
def test_telephone_window_allows_three_then_blocks(tenant: Any, capsys: Any) -> None:
    from apps.auth_otp.exceptions import OtpThrottledError
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import request_otp

    for _ in range(3):
        request_otp(tenant, PHONE)

    with pytest.raises(OtpThrottledError):
        request_otp(tenant, PHONE)
    assert PhoneOtp.objects.for_tenant(tenant).filter(phone=PHONE).count() == 3


def test_hourly_window_blocks_when_short_window_does_not(tenant: Any) -> None:
    from datetime import timedelta

    from apps.auth_otp.exceptions import OtpThrottledError
    from apps.auth_otp.models import PhoneOtp

    now = timezone.now()
    for _ in range(10):
        PhoneOtp.issue(tenant, PHONE)
    # Backdate every row to 30 minutes ago: inside the hour, outside the 15-min
    # window, so only the hourly limit can reject the next send.
    PhoneOtp.objects.for_tenant(tenant).filter(phone=PHONE).update(
        created_at=now - timedelta(minutes=30)
    )

    with pytest.raises(OtpThrottledError):
        from apps.auth_otp.services import request_otp

        request_otp(tenant, PHONE, now=now)


# ----------------------------------------------------------------- verify
def test_verify_auto_provisions_customer_and_returns_tokens(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp
    from apps.customers.models import Customer

    row, code = PhoneOtp.issue(tenant, PHONE)
    result = verify_otp(tenant, PHONE, code, name=" Asha ", email=" Asha@Example.COM ")

    customer = Customer.objects.for_tenant(tenant).get(phone=PHONE)
    assert result["customer"].pk == customer.pk
    assert customer.name == "Asha"
    assert customer.email == "asha@example.com"
    assert result["access"] and result["refresh"]

    row.refresh_from_db()
    assert row.consumed_at is not None
    assert row.customer_id == customer.pk

    from rest_framework_simplejwt.tokens import AccessToken

    from apps.auth_otp.tokens import SCOPE_CLAIM

    claims = AccessToken(result["access"]).payload
    assert claims[SCOPE_CLAIM] == "customer"


def test_verify_with_blank_profile_keeps_existing_customer(tenant: Any) -> None:
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp
    from apps.customers.models import Customer

    Customer.objects.create(tenant=tenant, phone=PHONE, name="Old", email=None)
    first, _code = PhoneOtp.issue(tenant, PHONE)
    _row, code = PhoneOtp.issue(tenant, PHONE)

    result = verify_otp(tenant, PHONE, code, name="", email="")
    customer = result["customer"]
    assert customer.name == "Old"
    assert customer.email is None
    first.refresh_from_db()
    assert first.consumed_at is None  # only the verified code was consumed


def test_verify_wrong_code_is_rejected_and_counts(tenant: Any) -> None:
    from apps.auth_otp.exceptions import InvalidOtpError
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp

    _row, _code = PhoneOtp.issue(tenant, PHONE)
    with pytest.raises(InvalidOtpError):
        verify_otp(tenant, PHONE, "xxxxxx")
    with pytest.raises(InvalidOtpError):
        verify_otp(tenant, PHONE, "999999")

    from apps.customers.models import Customer

    assert Customer.objects.for_tenant(tenant).filter(phone=PHONE).count() == 0


def test_verify_expired_code_is_rejected(tenant: Any) -> None:
    from apps.auth_otp.exceptions import InvalidOtpError
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp

    _row, code = PhoneOtp.issue(tenant, PHONE, expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(InvalidOtpError):
        verify_otp(tenant, PHONE, code)


def test_verify_after_lockout_rejects_even_correct_code(tenant: Any) -> None:
    from apps.auth_otp.exceptions import InvalidOtpError
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp

    _row, code = PhoneOtp.issue(tenant, PHONE)
    for _ in range(5):
        with pytest.raises(InvalidOtpError):
            verify_otp(tenant, PHONE, "000000")

    with pytest.raises(InvalidOtpError):
        verify_otp(tenant, PHONE, code)


def test_verify_unknown_number_is_rejected_silently(tenant: Any) -> None:
    from apps.auth_otp.exceptions import InvalidOtpError
    from apps.auth_otp.services import verify_otp

    with pytest.raises(InvalidOtpError):
        verify_otp(tenant, PHONE, "123456")


def test_verify_is_isolated_by_tenant(tenant: Any) -> None:
    from apps.auth_otp.exceptions import InvalidOtpError
    from apps.auth_otp.models import PhoneOtp
    from apps.auth_otp.services import verify_otp
    from apps.tenants.models import Tenant

    _row, code = PhoneOtp.issue(tenant, PHONE)

    other = Tenant.objects.create(slug="haas", name="Haas", timezone="UTC")
    with pytest.raises(InvalidOtpError):
        verify_otp(other, PHONE, code)

    result = verify_otp(tenant, PHONE, code)
    assert result["customer"] is not None
