from __future__ import annotations

from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.services.models import Service, ServiceStatus
from apps.tenants.models import Tenant
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PUBLIC = "/api/v1/services/"
ADMIN = "/api/v1/admin/services/"

CREDS = {"email": "owner@dwyer.com", "password": "Str0ng-Passw0rd!"}

PAYLOAD: dict[str, Any] = {
    "name": "Initial Consultation",
    "description": "First meeting to discuss the case.",
    "duration_minutes": 30,
    "price_amount": "500.00",
}


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


def _make(
    tenant: Tenant, *, name: str = "Initial Consultation", status_: str = "ACTIVE"
) -> Service:
    slug = name.lower().replace(" ", "-")
    return Service.objects.unfiltered().create(
        tenant=tenant,
        name=name,
        slug=slug,
        duration_minutes=30,
        price_amount="500.00",
        status=status_,
    )


def _owner(tenant: Tenant) -> Any:
    from apps.accounts.models import Role, User

    return User.objects.create_user(
        email=f"owner@{tenant.slug}.com",
        password=CREDS["password"],
        tenant=tenant,
        role=Role.OWNER,
    )


def _token(api_client: APIClient, owner: Any) -> str:
    response = api_client.post("/api/v1/auth/admin/login", CREDS, format="json")
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access"]


# ----------------------------------------------------------------- model
def test_manager_reads_fail_closed_without_a_tenant(tenant: Tenant) -> None:
    from common.exceptions import TenantContextMissing

    Service.objects.unfiltered().create(
        tenant=tenant,
        name="Initial Consultation",
        slug="initial-consultation",
        duration_minutes=30,
        price_amount="500.00",
    )

    with pytest.raises(TenantContextMissing):
        Service.objects.all()


def test_make_slug_is_unique_within_the_tenant(tenant: Tenant, other: Tenant) -> None:
    _make(tenant, name="Initial Consultation")
    _make(other, name="Initial Consultation")

    assert Service.make_slug(tenant, "Initial Consultation") == "initial-consultation-2"
    # Another practice calls theirs whatever it wants; tenancy is the boundary.
    assert Service.make_slug(other, "Initial Consultation") == "initial-consultation-2"


# ----------------------------------------------------------------- public
def test_public_list_shows_only_the_current_tenants_active_services(
    api_client: APIClient, tenant: Tenant, other: Tenant
) -> None:
    visible = _make(tenant, name="Initial Consultation")
    _make(tenant, name="Follow-up Consultation", status_="INACTIVE")
    _make(tenant, name="Old Service", status_="DELETED")
    _make(other, name="Mason Consultation")

    with tenant_context(tenant):
        response = api_client.get(PUBLIC)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["count"] == 1
    assert [row["slug"] for row in body["results"]] == [visible.slug]


def test_public_retrieve_by_slug_serves_active_services(
    api_client: APIClient, tenant: Tenant
) -> None:
    service = _make(tenant, name="Document Consultation", status_="ACTIVE")

    with tenant_context(tenant):
        response = api_client.get(f"{PUBLIC}{service.slug}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "Document Consultation"
    assert response.json()["price"] == "₹500"


def test_public_retrieve_hides_inactive_and_other_tenants(
    api_client: APIClient, tenant: Tenant, other: Tenant
) -> None:
    inactive = _make(tenant, name="Inactive Service", status_="INACTIVE")
    theirs = _make(other, name="Theirs Service")

    for slug in (inactive.slug, theirs.slug):
        with tenant_context(tenant):
            response = api_client.get(f"{PUBLIC}{slug}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "not_found"


def test_public_status_param_cannot_widen_beyond_active(
    api_client: APIClient, tenant: Tenant
) -> None:
    _make(tenant, name="Initial Consultation", status_="ACTIVE")
    _make(tenant, name="Hidden Service", status_="INACTIVE")

    with tenant_context(tenant):
        response = api_client.get(PUBLIC, {"status": "inactive"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 0


def test_public_list_without_a_tenant_is_empty_not_an_error(
    api_client: APIClient, tenant: Tenant
) -> None:
    _make(tenant, name="Initial Consultation")

    response = api_client.get(PUBLIC)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 0


def test_public_read_requires_no_authentication(api_client: APIClient, tenant: Tenant) -> None:
    _make(tenant, name="Initial Consultation")

    with tenant_context(tenant):
        response = api_client.get(PUBLIC)

    assert response.status_code == status.HTTP_200_OK


# ----------------------------------------------------------------- admin create
def test_admin_creates_service_in_own_tenant_and_autoslug(
    api_client: APIClient, tenant: Tenant
) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        ADMIN, {**PAYLOAD}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["tenant_id"] == str(tenant.pk)
    assert body["slug"] == "initial-consultation"
    assert body["price"] == "₹500"
    assert body["currency"] == "INR"
    assert body["status"] == "ACTIVE"


def test_admin_slug_gets_a_numeric_suffix_on_collision(
    api_client: APIClient, tenant: Tenant
) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)
    _make(tenant, name="Initial Consultation")

    with tenant_context(tenant):
        second = api_client.post(
            ADMIN, {**PAYLOAD}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    assert second.status_code == status.HTTP_201_CREATED
    body = second.json()
    assert body["slug"] == "initial-consultation-2"
    assert Service.objects.unfiltered().filter(tenant=tenant, slug=body["slug"]).exists()


def test_admin_cannot_mass_assign_tenant_id(
    api_client: APIClient, tenant: Tenant, other: Tenant
) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)

    payload = {**PAYLOAD, "tenant_id": str(other.pk)}
    response = api_client.post(ADMIN, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["tenant_id"] == str(tenant.pk)


def test_admin_rejects_negative_or_zero_price_and_bad_duration(
    api_client: APIClient, tenant: Tenant
) -> None:
    # S §A8: negative/zero price, duration 0, and "99999" are all rejected.
    owner = _owner(tenant)
    token = _token(api_client, owner)

    bad_payloads: list[dict[str, Any]] = [
        {**PAYLOAD, "price_amount": "0.00"},
        {**PAYLOAD, "price_amount": "-5.00"},
        {**PAYLOAD, "duration_minutes": 0},
        {**PAYLOAD, "duration_minutes": 99999},
    ]
    for payload in bad_payloads:
        response = api_client.post(
            ADMIN, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"]["code"] == "validation_error"


def test_admin_rejects_currency_the_tenant_does_not_charge_in(
    api_client: APIClient, tenant: Tenant
) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        ADMIN, {**PAYLOAD, "currency": "USD"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "validation_error"


def test_admin_status_cannot_be_deleted_directly(api_client: APIClient, tenant: Tenant) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)
    service = _make(tenant, name="Initial Consultation")

    response = api_client.patch(
        f"{ADMIN}{service.pk}/",
        {"status": "DELETED"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_admin_delete_is_a_soft_delete(api_client: APIClient, tenant: Tenant) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)
    service = _make(tenant, name="Initial Consultation")

    response = api_client.delete(f"{ADMIN}{service.pk}/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    row = Service.objects.unfiltered().get(pk=service.pk)
    assert row.status == ServiceStatus.DELETED
    # Gone from the public catalogue and the default admin list, listed under ?status=deleted.
    with tenant_context(tenant):
        assert api_client.get(PUBLIC).json()["count"] == 0
        assert api_client.get(ADMIN, HTTP_AUTHORIZATION=f"Bearer {token}").json()["count"] == 0
        deleted = api_client.get(
            ADMIN, {"status": "deleted"}, HTTP_AUTHORIZATION=f"Bearer {token}"
        ).json()
    assert [row["id"] for row in deleted["results"]] == [str(service.pk)]


def test_admin_list_defaults_to_excluding_deleted(api_client: APIClient, tenant: Tenant) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)
    _make(tenant, name="Active Service", status_="ACTIVE")
    _make(tenant, name="Inactive Service", status_="INACTIVE")
    _make(tenant, name="Old Service", status_="DELETED")

    response = api_client.get(ADMIN, HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_200_OK
    names = {row["slug"] for row in response.json()["results"]}
    assert names == {"active-service", "inactive-service"}


# ----------------------------------------------------------------- admin authz
def test_admin_cannot_touch_another_tenants_service(
    api_client: APIClient, tenant: Tenant, other: Tenant
) -> None:
    theirs = _make(other, name="Theirs Service")
    intruder = _owner(tenant)
    token = _token(api_client, intruder)

    for verb in ("get", "patch", "delete"):
        request = getattr(api_client, verb)
        kwargs: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        if verb == "patch":
            kwargs["data"] = {"name": "Renamed"}
            kwargs["format"] = "json"
        response = request(f"{ADMIN}{theirs.pk}/", **kwargs)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "not_found"


def test_admin_viewer_role_is_denied(api_client: APIClient, tenant: Tenant) -> None:
    from rest_framework.test import APIClient as AuthClient

    from apps.accounts.models import Role, User

    viewer = User.objects.create_user(
        email="viewer@dwyer.com",
        password=CREDS["password"],
        tenant=tenant,
        role=Role.VIEWER,
    )
    client: AuthClient = APIClient()
    client.force_authenticate(user=viewer)

    response = client.get(ADMIN)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "permission_denied"


def test_admin_anonymous_is_unauthorized(api_client: APIClient) -> None:
    response = api_client.get(ADMIN)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_admin_update_patch_is_isolated_to_the_fields_sent(
    api_client: APIClient, tenant: Tenant
) -> None:
    owner = _owner(tenant)
    token = _token(api_client, owner)
    service = _make(tenant, name="Initial Consultation")

    response = api_client.patch(
        f"{ADMIN}{service.pk}/",
        {"description": "Updated pitch."},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["description"] == "Updated pitch."
    assert body["price"] == "₹500"
    assert body["duration_minutes"] == 30
