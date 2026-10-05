"""OTP issue + verify as pure services (plan §4, S §A3).

Everything a caller could get wrong about the *window rules* lives here so the
API views stay thin. The rules, all DB-backed (so they survive a restart, the
"Redis with a DB fallback" the security plan calls for):

- **Send windows** (per number): at most 3 codes in any 15 minutes and at most
  10 in any hour, counted off real `PhoneOtp` rows.
- **Verify**: the newest still-valid code for the number is the one that
  counts. Wrong code -> attempt recorded; at `DJANGO_OTP_MAX_ATTEMPTS` failures
  the code is consumed and dead. Expired or consumed codes are simply not
  found, producing the same `invalid_otp` as a random guess (no oracle).
- **Tenant isolation**: rows and customer lookups are always scoped to one
  tenant. A code minted under tenant A can never verify under tenant B.
- **No enumeration**: request responses are identical for known and unknown
  numbers (the oracle lives here too, by simply never looking the customer up).

`verify_otp` returns the customer and a token pair; the customer is
auto-provisioned on first success (plan: "customer row auto-provisioned on
first verified OTP"), with name/email filled only when the verify payload
supplies them.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.auth_otp.channels import send_otp
from apps.auth_otp.exceptions import InvalidOtpError, OtpThrottledError
from apps.auth_otp.models import PhoneOtp
from apps.auth_otp.tokens import issue_customer_token_pair
from apps.customers.models import Customer
from apps.customers.phone import PhoneValidationError, normalize_phone
from common.querysets import TenantScopedQuerySet

SEND_WINDOW_SHORT = timedelta(minutes=15)
SEND_WINDOW_LONG = timedelta(hours=1)
SEND_LIMIT_SHORT = 3
SEND_LIMIT_LONG = 10


def _clean_phone(phone: str) -> str:
    try:
        return normalize_phone(phone)
    except PhoneValidationError as err:
        raise InvalidOtpError() from err


def request_otp(tenant: Any, phone: str, *, now: datetime | None = None) -> None:
    """Validate send windows, mint a code, and deliver it. No return value:
    the code goes only to the send channel, never to the caller."""
    phone = _clean_phone(phone)
    _enforce_send_windows(tenant, phone, now)
    _otp, code = PhoneOtp.issue(tenant, phone)
    send_otp(phone, code)


def _enforce_send_windows(tenant: Any, phone: str, now: datetime | None = None) -> None:
    now = now or timezone.now()
    recent = _codes_since(tenant, phone)
    if recent.filter(created_at__gte=now - SEND_WINDOW_SHORT).count() >= SEND_LIMIT_SHORT:
        raise OtpThrottledError()
    if recent.filter(created_at__gte=now - SEND_WINDOW_LONG).count() >= SEND_LIMIT_LONG:
        raise OtpThrottledError()


def _codes_since(tenant: Any, phone: str) -> TenantScopedQuerySet[PhoneOtp]:
    return PhoneOtp.objects.for_tenant(tenant).filter(phone=phone)


def verify_otp(
    tenant: Any,
    phone: str,
    code: str,
    *,
    now: datetime | None = None,
    name: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Verify a code, auto-provision the customer, and return a token pair.

    Any failure - wrong, expired, consumed, unknown, or from another tenant's
    rows - raises the same `InvalidOtpError` so responses stay non-informative.
    """
    phone = _clean_phone(phone)
    now = now or timezone.now()
    otp = _find_valid_code(tenant, phone, now)
    if otp is None or not otp.code_matches(code):
        if otp is not None:
            otp.record_failed_attempt(now=now)
        raise InvalidOtpError()

    customer = _upsert_customer(tenant, phone, name, email)
    otp.consume(customer, now=now)
    pair = issue_customer_token_pair(customer)
    pair["customer"] = customer
    return pair


def _find_valid_code(tenant: Any, phone: str, now: datetime) -> PhoneOtp | None:
    for otp in _codes_since(tenant, phone).order_by("-created_at"):
        if otp.is_valid(now):
            return otp
    return None


def _upsert_customer(
    tenant: Any,
    phone: str,
    name: str | None,
    email: str | None,
) -> Customer:
    customer = Customer.objects.for_tenant(tenant).filter(phone=phone).first()
    if customer is None:
        return Customer.objects.create(
            tenant=tenant,
            phone=phone,
            name=(name or "").strip(),
            email=_email_or_none(email),
        )
    update: dict[str, Any] = {}
    if name and name.strip():
        update["name"] = name.strip()
    if email and email.strip():
        update["email"] = _email_or_none(email)
    if update:
        Customer.objects.filter(pk=customer.pk).update(**update)
        customer.refresh_from_db(fields=list(update))
    return customer


def _email_or_none(email: str | None) -> str | None:
    value = (email or "").strip().lower()
    return value or None


__all__ = ("request_otp", "verify_otp")
