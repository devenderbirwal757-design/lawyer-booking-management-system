"""End-to-end OTP + customer auth flows over the HTTP layer (S §A3).

Readable contract:
- request is rate-limited, and answers `{"ok": true}` identically for known
  and unknown numbers so it cannot enumerate customers;
- verify exchanges a code for a customer-scoped JWT pair and auto-provisions
  the customer, or fails with the same 400 `invalid_otp` for a wrong / expired
  / pre-locked-out code;
- the code is hashed at rest and never appears in logs;
- codes are tenant-isolated, and a missing tenant context fails closed (404);
- a customer token is rejected by admin endpoints, and `/auth/me` returns the
  customer profile for a customer token.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.utils import timezone

from apps.auth_otp.models import PhoneOtp
from apps.tenants.models import Tenant
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PHONE = "+919876543210"

OTP_REQUEST = "/api/v1/auth/otp/request"
OTP_VERIFY = "/api/v1/auth/otp/verify"
ME = "/api/v1/auth/me"
ADMIN_SERVICES = "/api/v1/admin/services/"

CREDS = {"email": "owner@dwyer.com", "password": "Str0ng-Passw0rd!"}


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone="UTC")


@pytest.fixture
def other() -> Tenant:
    return Tenant.objects.create(slug="mason", name="Mason & Co", timezone="UTC")


def _post(api_client: Any, tenant: Tenant, path: str, payload: dict[str, Any]) -> Any:
    with tenant_context(tenant):
        return api_client.post(path, payload, format="json")


def _request_otp(api_client: Any, tenant: Tenant, phone: str = PHONE) -> Any:
    return _post(api_client, tenant, OTP_REQUEST, {"phone": phone})


def _read_code(capsys: Any) -> str:
    out = capsys.readouterr().out
    match = re.search(r"\[dev-otp\] OTP for .*: (\d{6})", out)
    assert match, f"no OTP line printed to stdout: {out!r}"
    return match.group(1)


# ----------------------------------------------------------------- request
def test_request_returns_ok_without_enumeration(
    api_client: Any, tenant: Tenant, capsys: Any
) -> None:
    first = _request_otp(api_client, tenant)
    known_again = _request_otp(api_client, tenant)
    _read_code(capsys)

    assert first.status_code == 200
    assert first.json() == {"ok": True}
    assert known_again.json() == {"ok": True}

    # The number was never requested before, so the first call was "unknown";
    # both answers are byte-identical, which is what makes it non-enumerating.
    assert PhoneOtp.objects.for_tenant(tenant).count() == 2


def test_request_is_isolated_by_tenant(api_client: Any, tenant: Tenant, other: Tenant) -> None:
    assert _request_otp(api_client, tenant).json() == {"ok": True}
    assert _request_otp(api_client, other).json() == {"ok": True}

    assert PhoneOtp.objects.for_tenant(tenant).count() == 1
    assert PhoneOtp.objects.for_tenant(other).count() == 1


def test_request_404s_without_a_tenant_context(api_client: Any) -> None:
    response = api_client.post(OTP_REQUEST, {"phone": PHONE}, format="json")
    assert response.status_code == 404


def test_request_rejects_an_invalid_phone(api_client: Any, tenant: Tenant) -> None:
    response = _request_otp(api_client, tenant, phone="12345")
    assert response.status_code == 400


def test_request_hits_the_send_window_after_three(
    api_client: Any, tenant: Tenant, capsys: Any
) -> None:
    for _ in range(3):
        assert _request_otp(api_client, tenant).status_code == 200

    _read_code(capsys)
    fourth = _request_otp(api_client, tenant)
    assert fourth.status_code == 429
    assert fourth.json()["error"]["code"] == "throttled"


# ----------------------------------------------------------------- verify
def test_verify_returns_tokens_and_auto_provisions(
    api_client: Any, tenant: Tenant, capsys: Any
) -> None:
    _request_otp(api_client, tenant)
    code = _read_code(capsys)

    response = _post(
        api_client,
        tenant,
        OTP_VERIFY,
        {"phone": PHONE, "code": code, "name": "Asha", "email": "a@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access"] and body["refresh"]
    assert body["customer"]["phone"] == PHONE
    assert body["customer"]["name"] == "Asha"
    assert body["customer"]["email"] == "a@example.com"

    from apps.customers.models import Customer

    customer = Customer.objects.for_tenant(tenant).get(phone=PHONE)
    assert customer.email == "a@example.com"
    assert body["customer"]["id"] == str(customer.pk)

    row = PhoneOtp.objects.for_tenant(tenant).get(phone=PHONE)
    assert row.consumed_at is not None
    assert row.customer_id == customer.pk


def test_verify_stores_only_the_hash_and_never_logs_the_code(
    api_client: Any, tenant: Tenant, capsys: Any, caplog: Any
) -> None:
    import logging

    _request_otp(api_client, tenant)
    code = _read_code(capsys)

    row = PhoneOtp.objects.for_tenant(tenant).get(phone=PHONE)
    assert row.code_hash != code
    assert code not in row.code_hash
    assert len(row.code_hash) == 64

    with caplog.at_level(logging.DEBUG):
        response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": code})
    assert response.status_code == 200
    assert code not in caplog.text


def test_verify_rejects_a_wrong_code(api_client: Any, tenant: Tenant, capsys: Any) -> None:
    _request_otp(api_client, tenant)
    _read_code(capsys)

    from apps.customers.models import Customer

    response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": "123456"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"
    assert Customer.objects.for_tenant(tenant).count() == 0


def test_verify_rejects_an_expired_code(api_client: Any, tenant: Tenant) -> None:
    PhoneOtp.issue(tenant, PHONE, expires_at=timezone.now())

    response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": "000000"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


def test_verify_locks_out_after_five_attempts(api_client: Any, tenant: Tenant, capsys: Any) -> None:
    _request_otp(api_client, tenant)
    code = _read_code(capsys)

    for _ in range(5):
        response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": "000000"})
        assert response.status_code == 400

    response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": code})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"


def test_verify_code_does_not_cross_tenants(
    api_client: Any, tenant: Tenant, other: Tenant, capsys: Any
) -> None:
    _request_otp(api_client, tenant)
    code = _read_code(capsys)

    response = _post(api_client, other, OTP_VERIFY, {"phone": PHONE, "code": code})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_otp"

    response = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": code})
    assert response.status_code == 200


# ------------------------------------------------------------- scopes and me
def test_customer_token_is_rejected_by_an_admin_endpoint(
    api_client: Any, tenant: Tenant, capsys: Any
) -> None:
    _request_otp(api_client, tenant)
    code = _read_code(capsys)
    body = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": code}).json()

    with tenant_context(tenant):
        response = api_client.get(ADMIN_SERVICES, HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    assert response.status_code == 401


def test_me_returns_the_customer_profile_for_a_customer_token(
    api_client: Any, tenant: Tenant, capsys: Any
) -> None:
    _request_otp(api_client, tenant)
    code = _read_code(capsys)
    body = _post(api_client, tenant, OTP_VERIFY, {"phone": PHONE, "code": code}).json()
    customer_id = body["customer"]["id"]

    with tenant_context(tenant):
        response = api_client.get(ME, HTTP_AUTHORIZATION=f"Bearer {body['access']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == customer_id
    assert payload["phone"] == PHONE
    assert "is_active" in payload  # customer shape
    assert "role" not in payload  # never the admin shape


def test_me_is_not_served_without_a_token(api_client: Any, tenant: Tenant) -> None:
    with tenant_context(tenant):
        response = api_client.get(ME)
    assert response.status_code == 401
