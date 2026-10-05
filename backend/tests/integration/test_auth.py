from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

LOGIN = "/api/v1/auth/admin/login"
REFRESH = "/api/v1/auth/admin/refresh"
LOGOUT = "/api/v1/auth/admin/logout"
ME = "/api/v1/auth/me"

CREDS = {"email": "owner@dwyer.com", "password": "Str0ng-Passw0rd!"}


@pytest.fixture
def owner() -> Any:
    from apps.accounts.models import Role, User
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone="UTC")
    return User.objects.create_user(
        email=CREDS["email"], password=CREDS["password"], tenant=tenant, role=Role.OWNER
    )


def _login(api_client: APIClient, data: dict[str, str] | None = None) -> Any:
    return api_client.post(LOGIN, data or CREDS, format="json")


# ----------------------------------------------------------------- login
def test_login_returns_access_refresh_and_profile(api_client: APIClient, owner: Any) -> None:
    response = _login(api_client)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "access" in body and "refresh" in body
    assert body["user"]["email"] == owner.email
    assert body["user"]["role"] == owner.role
    assert body["user"]["tenant"]["slug"] == owner.tenant.slug


def test_login_failure_is_401_generic_and_does_not_enumerate(
    api_client: APIClient, owner: Any
) -> None:
    attempts = [
        {"email": CREDS["email"], "password": "wrong-password"},
        {"email": "ghost@dwyer.com", "password": CREDS["password"]},
        {"email": "ghost@dwyer.com", "password": "wrong-password"},
    ]
    responses = [api_client.post(LOGIN, data, format="json") for data in attempts]

    assert all(r.status_code == status.HTTP_401_UNAUTHORIZED for r in responses)
    messages = {r.json()["error"]["message"] for r in responses}
    assert messages == {"Incorrect email or password."}


def test_login_for_non_admin_role_is_refused(api_client: APIClient, owner: Any) -> None:
    from apps.accounts.models import Role

    owner.role = Role.VIEWER
    owner.save(update_fields=["role", "updated_at"])

    response = _login(api_client)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "cannot use the admin API" in response.json()["error"]["message"]


def test_login_for_inactive_user_is_generic(api_client: APIClient, owner: Any) -> None:
    owner.is_active = False
    owner.save(update_fields=["is_active", "updated_at"])

    response = _login(api_client)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["message"] == "Incorrect email or password."


def test_login_sets_access_claims(api_client: APIClient, owner: Any) -> None:
    from apps.accounts.serializers import _read_claims
    from apps.accounts.tokens import FAMILY_CLAIM

    response = _login(api_client)
    claims = _read_claims(response.json()["access"])

    assert claims["user_id"] == str(owner.pk)
    assert claims["role"] == owner.role
    assert claims["tenant"] == str(owner.tenant_id)
    assert claims[FAMILY_CLAIM]


# ----------------------------------------------------------------- refresh
def test_refresh_rotates_to_a_new_working_pair(api_client: APIClient, owner: Any) -> None:
    first = _login(api_client).json()

    rotated = api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json")
    assert rotated.status_code == status.HTTP_200_OK
    body = rotated.json()
    assert body["access"] != first["access"]
    assert body["refresh"] != first["refresh"]

    me = api_client.get(ME, HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    assert me.status_code == status.HTTP_200_OK
    assert me.json()["email"] == owner.email


def test_replay_of_a_spent_refresh_revokes_the_whole_family(
    api_client: APIClient, owner: Any
) -> None:
    first = _login(api_client).json()
    rotated = api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json")

    replay = api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json")
    assert replay.status_code == status.HTTP_401_UNAUTHORIZED

    # The winner's rotated refresh is dead too: the family was revoked, so
    # the theft cost the attacker at most a single exchange.
    winner = api_client.post(REFRESH, {"refresh": rotated.json()["refresh"]}, format="json")
    assert winner.status_code == status.HTTP_401_UNAUTHORIZED

    # A fresh login is unaffected: revocation is per-family, not per-user.
    assert _login(api_client).status_code == status.HTTP_200_OK


def test_reuse_revokes_rotated_refresh_too(api_client: APIClient, owner: Any) -> None:
    first = _login(api_client).json()
    rotated = api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json").json()

    api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json")  # replay detected

    retry = api_client.post(REFRESH, {"refresh": rotated["refresh"]}, format="json")
    assert retry.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_after_logout_is_rejected(api_client: APIClient, owner: Any) -> None:
    first = _login(api_client).json()
    logout = api_client.post(LOGOUT, {"refresh": first["refresh"]}, format="json")
    assert logout.status_code == status.HTTP_204_NO_CONTENT

    retry = api_client.post(REFRESH, {"refresh": first["refresh"]}, format="json")
    assert retry.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_with_garbage_token_fails_silently(api_client: APIClient, owner: Any) -> None:
    response = api_client.post(REFRESH, {"refresh": "not-a-token"}, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "session is no longer valid" in response.json()["error"]["message"]


# ----------------------------------------------------------------- logout
def test_logout_is_idempotent_and_non_probing(api_client: APIClient, owner: Any) -> None:
    login = _login(api_client).json()

    assert api_client.post(LOGOUT, {"refresh": login["refresh"]}, format="json").status_code == 204
    # Logging out again with the same (now-spent) token is still a 204.
    assert api_client.post(LOGOUT, {"refresh": login["refresh"]}, format="json").status_code == 204
    # Garbage tokens cannot be distinguished from real ones at logout.
    garbage = api_client.post(LOGOUT, {"refresh": "garbage"}, format="json")
    assert garbage.status_code == status.HTTP_204_NO_CONTENT


# ----------------------------------------------------------------- me
def test_me_requires_authentication(api_client: APIClient, owner: Any) -> None:
    assert api_client.get(ME).status_code == status.HTTP_401_UNAUTHORIZED

    bogus = api_client.get(ME, HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert bogus.status_code == status.HTTP_401_UNAUTHORIZED


def test_me_returns_own_profile(api_client: APIClient, owner: Any) -> None:
    access = _login(api_client).json()["access"]
    response = api_client.get(ME, HTTP_AUTHORIZATION=f"Bearer {access}")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["email"] == owner.email
    assert body["role"] == owner.role
    assert body["tenant"]["slug"] == owner.tenant.slug
    assert set(body) >= {"id", "email", "full_name", "role", "is_active", "date_joined", "tenant"}


# ----------------------------------------------------------------- TTLs
def test_jwt_lifetimes_comply_with_s_a2(owner: Any) -> None:
    assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=15)
    assert settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"] <= timedelta(days=7)
    assert settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"] is True
    assert settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"] is True


# ----------------------------------------------------------------- throttling
def test_login_is_throttled_per_ip_and_per_email(api_client: APIClient, owner: Any) -> None:
    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"]
    assert rate == "5/15min"

    for _ in range(5):
        response = _login(api_client, {"email": CREDS["email"], "password": "wrong"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    throttled = _login(api_client, {"email": CREDS["email"], "password": "wrong"})
    assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert throttled.json()["error"]["code"] == "throttled"

    # A different email from the same IP is still limited per-email; but the
    # per-IP bucket is now exhausted too, so fresh addresses also hit 429.
    other = api_client.post(LOGIN, {"email": "other@dwyer.com", "password": "wrong"}, format="json")
    assert other.status_code == status.HTTP_429_TOO_MANY_REQUESTS
