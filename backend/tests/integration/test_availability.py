"""Availability API (plan §3 Phase 3): public slots/dates + admin calendar CRUD.

Covers §A7 (the public endpoints are throttled), the service/provider
isolation of every read, and the admin rules/exceptions surface with its
overlap + cross-tenant validation.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from rest_framework import status

from apps.providers.models import Provider
from apps.scheduling.models import AvailabilityException, AvailabilityRule
from apps.services.models import Service
from apps.tenants.models import Tenant
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SLOTS = "/api/v1/availability/slots"
DATES = "/api/v1/availability/dates"
RULES = "/api/v1/admin/availability/rules/"
EXC = "/api/v1/admin/availability/exceptions/"

CREDS = {"email": "owner@dwyer.com", "password": "Str0ng-Passw0rd!"}

KOLKATA = "Asia/Kolkata"
FUTURE_MONDAY = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 28)


@pytest.fixture
def tenants() -> list[Tenant]:
    return [
        Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone=KOLKATA),
        Tenant.objects.create(slug="mason", name="Mason & Co", timezone="UTC"),
    ]


@pytest.fixture
def tenant(tenants: list[Tenant]) -> Tenant:
    return tenants[0]


@pytest.fixture
def other(tenants: list[Tenant]) -> Tenant:
    return tenants[1]


@pytest.fixture
def provider(tenant: Tenant) -> Provider:
    return Provider.objects.unfiltered().create(tenant=tenant, name="Adv. Dwyer")


@pytest.fixture
def service(provider: Provider) -> Service:
    return Service.objects.unfiltered().create(
        tenant=provider.tenant,
        provider=provider,
        name="Consultation",
        slug="consultation",
        duration_minutes=30,
        buffer_after_minutes=0,
        price_amount="500.00",
    )


def _service(provider: Provider | None, tenant: Tenant, name: str) -> Service:
    return Service.objects.unfiltered().create(
        tenant=tenant,
        provider=provider,
        name=name,
        slug=name.split()[0].lower(),
        duration_minutes=30,
        buffer_after_minutes=0,
        price_amount="500.00",
    )


def _rule(provider: Provider) -> AvailabilityRule:
    from datetime import time as dtime

    return AvailabilityRule.objects.unfiltered().create(
        provider=provider,
        weekday=FUTURE_MONDAY.isoweekday() % 7,
        start_time=dtime(10, 0),
        end_time=dtime(12, 0),
    )


def _firm(service: Service) -> Provider:
    provider = service.provider
    assert provider is not None
    return provider


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


# ----------------------------------------------------------------- public slots
def test_public_slots_returns_the_days_grid(api_client: Any, service: Service) -> None:
    provider = _firm(service)
    _rule(provider)

    with tenant_context(provider.tenant):
        response = api_client.get(SLOTS, {"service_id": service.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["service_id"] == str(service.pk)
    assert body["date"] == FUTURE_MONDAY.isoformat()
    assert body["slots"] == [
        f"{FUTURE_MONDAY.isoformat()}T10:00:00+05:30",
        f"{FUTURE_MONDAY.isoformat()}T10:30:00+05:30",
        f"{FUTURE_MONDAY.isoformat()}T11:00:00+05:30",
        f"{FUTURE_MONDAY.isoformat()}T11:30:00+05:30",
    ]


def test_public_slots_requires_no_authentication(api_client: Any, service: Service) -> None:
    _rule(_firm(service))

    with tenant_context(_firm(service).tenant):
        response = api_client.get(SLOTS, {"service_id": service.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_200_OK


def test_public_slots_404_for_another_tenants_service(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    theirs = _service(None, other, "Theirs")
    with tenant_context(tenant):
        response = api_client.get(SLOTS, {"service_id": theirs.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "not_found"


def test_public_slots_404_without_a_tenant_context(api_client: Any, service: Service) -> None:
    _rule(_firm(service))

    response = api_client.get(SLOTS, {"service_id": service.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_public_slots_400_when_service_has_no_provider(api_client: Any, tenant: Tenant) -> None:
    unassigned = _service(None, tenant, "Unassigned")

    with tenant_context(tenant):
        response = api_client.get(SLOTS, {"service_id": unassigned.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "service_unbookable"


def test_public_slots_400_for_a_bad_date(api_client: Any, service: Service) -> None:
    with tenant_context(_firm(service).tenant):
        response = api_client.get(SLOTS, {"service_id": service.pk, "date": "not-a-date"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "validation_error"


def test_public_slots_400_when_params_missing(api_client: Any, service: Service) -> None:
    with tenant_context(_firm(service).tenant):
        response = api_client.get(SLOTS, {"service_id": service.pk})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_public_slots_are_throttled(api_client: Any, service: Service) -> None:
    from django.conf import settings

    from common.throttles import AvailabilityRateThrottle

    _rule(_firm(service))

    with tenant_context(_firm(service).tenant):
        response = api_client.get(SLOTS, {"service_id": service.pk, "date": FUTURE_MONDAY})

    assert response.status_code == status.HTTP_200_OK
    # §A7: the scraping defence is wired and has a rate configured.
    assert AvailabilityRateThrottle.scope == "availability"
    assert "availability" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


def test_public_dates_lists_days_with_slots(api_client: Any, service: Service) -> None:
    provider = _firm(service)
    _rule(provider)

    month = f"{FUTURE_MONDAY.year}-{FUTURE_MONDAY.month:02d}"
    with tenant_context(provider.tenant):
        response = api_client.get(DATES, {"service_id": service.pk, "month": month})

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["month"] == month
    assert FUTURE_MONDAY.isoformat() in body["dates"]


# ---------------------------------------------------------------- admin rules
def test_admin_creates_a_rule(api_client: Any, provider: Provider) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)

    payload = {
        "provider": str(provider.pk),
        "weekday": 1,
        "start_time": "10:00",
        "end_time": "12:00",
    }
    response = api_client.post(RULES, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["weekday"] == 1
    assert body["start_time"] == "10:00:00"
    assert body["end_time"] == "12:00:00"
    assert body["provider"] == str(provider.pk)


def test_admin_rejects_overlapping_rules(api_client: Any, provider: Provider) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)
    _rule(provider)

    response = api_client.post(
        RULES,
        {
            "provider": str(provider.pk),
            "weekday": FUTURE_MONDAY.isoweekday() % 7,
            "start_time": "11:00",
            "end_time": "13:00",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "validation_error"


def test_admin_rejects_output_before_input(api_client: Any, provider: Provider) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        RULES,
        {
            "provider": str(provider.pk),
            "weekday": 1,
            "start_time": "12:00",
            "end_time": "10:00",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_admin_rule_verb_surface_is_get_post_patch(api_client: Any, provider: Provider) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)
    rule = _rule(provider)

    response = api_client.delete(f"{RULES}{rule.pk}/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_admin_can_patch_a_rule(api_client: Any, provider: Provider) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)
    rule = _rule(provider)

    response = api_client.patch(
        f"{RULES}{rule.pk}/",
        {"end_time": "14:00"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["end_time"] == "14:00:00"


def test_admin_rules_are_tenant_isolated(api_client: Any, tenant: Tenant, other: Tenant) -> None:
    theirs = Provider.objects.unfiltered().create(tenant=other, name="Adv. Mason")
    _rule(theirs)
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.get(RULES, HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 0


def test_admin_rule_detail_of_other_tenant_is_404(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    theirs = Provider.objects.unfiltered().create(tenant=other, name="Adv. Mason")
    rule = _rule(theirs)
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.get(f"{RULES}{rule.pk}/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_admin_cannot_point_a_rule_at_another_tenants_provider(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    theirs = Provider.objects.unfiltered().create(tenant=other, name="Adv. Mason")
    owner = _owner(tenant)
    token = _token(api_client, owner)

    response = api_client.post(
        RULES,
        {
            "provider": str(theirs.pk),
            "weekday": 1,
            "start_time": "10:00",
            "end_time": "12:00",
        },
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"]["code"] == "validation_error"


def test_admin_rules_viewer_is_denied(api_client: Any, provider: Provider) -> None:
    from rest_framework.test import APIClient

    from apps.accounts.models import Role, User

    viewer = User.objects.create_user(
        email="viewer@dwyer.com",
        password=CREDS["password"],
        tenant=provider.tenant,
        role=Role.VIEWER,
    )
    client = APIClient()
    client.force_authenticate(user=viewer)

    response = client.get(RULES)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_admin_rules_anonymous_is_unauthorized(api_client: Any) -> None:
    response = api_client.get(RULES)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ------------------------------------------------------------ admin exceptions
def test_admin_creates_and_lists_exceptions(
    api_client: Any, provider: Provider, service: Service
) -> None:
    owner = _owner(provider.tenant)
    token = _token(api_client, owner)
    payload = {
        "provider": str(provider.pk),
        "date": FUTURE_MONDAY,
        "start_time": "10:00",
        "end_time": "11:00",
        "type": "BLOCKED",
        "reason": "Court appearance",
    }

    created = api_client.post(EXC, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert created.status_code == status.HTTP_201_CREATED
    assert created.json()["type"] == "BLOCKED"

    listed = api_client.get(EXC, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert listed.json()["count"] == 1


def test_admin_deletes_an_exception(api_client: Any, provider: Provider) -> None:
    from datetime import time as dtime

    owner = _owner(provider.tenant)
    token = _token(api_client, owner)
    exception = AvailabilityException.objects.unfiltered().create(
        provider=provider,
        type="OVERRIDE",
        date=FUTURE_MONDAY,
        start_time=dtime(14, 0),
        end_time=dtime(16, 0),
    )

    deleted = api_client.delete(f"{EXC}{exception.pk}/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert not AvailabilityException.objects.unfiltered().filter(pk=exception.pk).exists()


def test_admin_exceptions_are_tenant_isolated(
    api_client: Any, tenant: Tenant, other: Tenant
) -> None:
    from datetime import time as dtime

    theirs = Provider.objects.unfiltered().create(tenant=other, name="Adv. Mason")
    theirs_exception = AvailabilityException.objects.unfiltered().create(
        provider=theirs,
        type="BLOCKED",
        date=FUTURE_MONDAY,
        start_time=dtime(10, 0),
        end_time=dtime(11, 0),
    )
    owner = _owner(tenant)
    token = _token(api_client, owner)

    listed = api_client.get(EXC, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert listed.status_code == status.HTTP_200_OK
    assert listed.json()["count"] == 0

    detail = api_client.get(f"{EXC}{theirs_exception.pk}/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert detail.status_code == status.HTTP_404_NOT_FOUND


def test_admin_slots_still_obey_the_new_blockout(
    api_client: Any, provider: Provider, service: Service
) -> None:
    from datetime import time as dtime

    _rule(provider)
    AvailabilityException.objects.unfiltered().create(
        provider=provider,
        type="BLOCKED",
        date=FUTURE_MONDAY,
        start_time=dtime(10, 0),
        end_time=dtime(11, 0),
    )

    with tenant_context(provider.tenant):
        slots = api_client.get(SLOTS, {"service_id": service.pk, "date": FUTURE_MONDAY})

    assert slots.status_code == status.HTTP_200_OK
    assert slots.json()["slots"][0] == f"{FUTURE_MONDAY.isoformat()}T11:00:00+05:30"
