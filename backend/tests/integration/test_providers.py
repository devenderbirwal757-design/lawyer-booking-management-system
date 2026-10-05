"""Provider catalogue + service/provider binding (plan §3 Phase 3)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework import status

from apps.providers.models import Provider
from apps.tenants.models import Tenant
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PUBLIC = "/api/v1/providers/"
ADMIN_SERVICES = "/api/v1/admin/services/"

CREDS = {"email": "owner@dwyer.com", "password": "Str0ng-Passw0rd!"}


@pytest.fixture
def tenants() -> list[Tenant]:
    return [
        Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone="UTC"),
        Tenant.objects.create(slug="mason", name="Mason & Co", timezone="UTC"),
    ]


@pytest.fixture
def tenant(tenants: list[Tenant]) -> Tenant:
    return tenants[0]


@pytest.fixture
def other(tenants: list[Tenant]) -> Tenant:
    return tenants[1]


def _provider(tenant: Tenant, *, name: str = "Adv. Dwyer", active: bool = True) -> Provider:
    return Provider.objects.unfiltered().create(tenant=tenant, name=name, is_active=active)


def _owner(tenant: Tenant) -> Any:
    from apps.accounts.models import Role, User

    return User.objects.create_user(
        email=f"owner@{tenant.slug}.com",
        password=CREDS["password"],
        tenant=tenant,
        role=Role.OWNER,
    )


def _token(api_client: Any, owner: Any) -> str:
    response = api_client.post("/api/v1/auth/admin/login", CREDS, format="json")
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access"]


# ------------------------------------------------------------------- public
def test_public_provider_detail(api_client: Any, tenant: Tenant) -> None:
    provider = _provider(tenant)

    with tenant_context(tenant):
        response = api_client.get(f"{PUBLIC}{provider.pk}/")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "Adv. Dwyer"
    assert "tenant_id" not in body


def test_public_provider_list_shows_only_the_tenants_active_providers(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    _provider(tenant, name="Adv. Dwyer")
    _provider(tenant, name="Adv. Dormant", active=False)
    _provider(other, name="Adv. Mason")

    with tenant_context(tenant):
        response = api_client.get(PUBLIC)

    assert response.status_code == status.HTTP_200_OK
    assert [row["name"] for row in response.json()["results"]] == ["Adv. Dwyer"]


def test_public_provider_hides_inactive_and_other_tenants(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    dormant = _provider(tenant, name="Adv. Dormant", active=False)
    theirs = _provider(other, name="Adv. Mason")

    for pk in (dormant.pk, theirs.pk):
        with tenant_context(tenant):
            response = api_client.get(f"{PUBLIC}{pk}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "not_found"


def test_public_provider_requires_no_auth(api_client: Any, tenant: Tenant) -> None:
    provider = _provider(tenant)

    with tenant_context(tenant):
        response = api_client.get(f"{PUBLIC}{provider.pk}/")

    assert response.status_code == status.HTTP_200_OK


# ------------------------------------------------- service/provider binding
def test_admin_can_assign_its_own_provider_to_a_service(api_client: Any, tenant: Tenant) -> None:
    provider = _provider(tenant)
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        ADMIN_SERVICES,
        {
            "name": "Consultation",
            "provider": str(provider.pk),
            "duration_minutes": 30,
            "price_amount": "500.00",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["provider"] == str(provider.pk)


def test_admin_cannot_bind_another_tenants_provider(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    theirs = _provider(other, name="Adv. Mason")
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        ADMIN_SERVICES,
        {
            "name": "Consultation",
            "provider": str(theirs.pk),
            "duration_minutes": 30,
            "price_amount": "500.00",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "validation_error"
