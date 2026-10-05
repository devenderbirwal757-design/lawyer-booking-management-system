from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

# Tests must never read a developer's local .env.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def admin_user(db: Any) -> Any:
    from apps.accounts.models import User

    return User.objects.create_user(
        email="admin@example.com",
        password="Str0ng-Passw0rd!",
        full_name="Test Admin",
        is_staff=True,
    )


@pytest.fixture
def api_client() -> Any:
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def admin_client(admin_user: Any) -> Any:
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def celery_app() -> Any:
    from config.celery import app

    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    return app


# ------------------------------------------------------- booking scenario (Phase 5)
# A minimal but *bookable* practice: tenant + provider + an active service + a
# customer, plus a working-hours rule on a known future weekday. Tests that need
# a second tenant, a second provider, a paid service or a different duration
# override or extend these, so the common case stays one fixture.
KOLKATA = "Asia/Kolkata"

#: A Monday far enough out to clear the booking lead time on any run.
BOOKING_DAY = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 21)
#: The first generated slot of the day, as an aware local datetime.
FIRST_SLOT = datetime.combine(BOOKING_DAY, dtime(10, 0), tzinfo=ZoneInfo(KOLKATA))


@pytest.fixture
def booking_tenant() -> Any:
    from apps.tenants.models import Tenant

    return Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone=KOLKATA)


@pytest.fixture
def booking_provider(booking_tenant: Any) -> Any:
    from apps.providers.models import Provider

    return Provider.objects.unfiltered().create(tenant=booking_tenant, name="Adv. Dwyer")


@pytest.fixture
def booking_service(booking_tenant: Any, booking_provider: Any) -> Any:
    from apps.services.models import Service

    return Service.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_provider,
        name="Consultation",
        slug="consultation",
        duration_minutes=30,
        buffer_after_minutes=0,
        price_amount="500.00",
        requires_payment=False,
    )


@pytest.fixture
def booking_rule(booking_provider: Any) -> Any:
    from apps.scheduling.models import AvailabilityRule

    return AvailabilityRule.objects.unfiltered().create(
        provider=booking_provider,
        weekday=BOOKING_DAY.isoweekday() % 7,
        start_time=dtime(10, 0),
        end_time=dtime(13, 0),
    )


@pytest.fixture
def paid_service(booking_tenant: Any, booking_provider: Any) -> Any:
    """A service that must be paid for, so only a capture can confirm it.

    Phase 6 tests need the paid path specifically: `booking_service` is
    pay-at-the-door, which confirms through the admin endpoint and would let a
    broken payment flow pass unnoticed.
    """
    from apps.services.models import Service

    return Service.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_provider,
        name="Paid Consultation",
        slug="paid-consultation",
        duration_minutes=30,
        buffer_after_minutes=0,
        price_amount="500.00",
        requires_payment=True,
    )


@pytest.fixture
def booking_customer(booking_tenant: Any) -> Any:
    from apps.customers.models import Customer

    return Customer.objects.unfiltered().create(
        tenant=booking_tenant,
        phone="+919876543210",
        name="Priya Sharma",
    )


@pytest.fixture
def customer_client(booking_customer: Any) -> Any:
    """An APIClient holding a customer JWT, scoped to their tenant."""
    from rest_framework.test import APIClient

    from apps.auth_otp.tokens import issue_customer_token_pair

    client = APIClient()
    tokens = issue_customer_token_pair(booking_customer)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def booking_owner(booking_tenant: Any) -> Any:
    from apps.accounts.models import Role, User

    return User.objects.create_user(
        email="owner@dwyer.com",
        password="Str0ng-Passw0rd!",
        full_name="Test Owner",
        tenant=booking_tenant,
        role=Role.OWNER,
    )


@pytest.fixture
def booking_admin_client(booking_owner: Any) -> Any:
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=booking_owner)
    return client


@pytest.fixture
def paid_hold(
    customer_client: Any,
    booking_tenant: Any,
    paid_service: Any,
    booking_rule: Any,
) -> Any:
    """A booked hold on a paid service, plus its `PaymentOrder`.

    The starting point for most Phase 6 tests: a slot is held, nothing is paid,
    and the only thing that may confirm it is a captured payment.
    """
    from apps.appointments.models import Appointment
    from apps.payments.models import PaymentOrder
    from common.querysets import tenant_context
    from tests.conftest import slot_iso

    with tenant_context(booking_tenant):
        response = customer_client.post(
            "/api/v1/appointments/",
            {"service_id": str(paid_service.pk), "start_at": slot_iso()},
            format="json",
        )
    assert response.status_code == 201, response.data
    appointment = Appointment.objects.unfiltered().get(pk=response.data["id"])
    return appointment, PaymentOrder.objects.unfiltered().get(appointment=appointment)


@pytest.fixture
def fake_gateway(monkeypatch: Any) -> Any:
    """Swap the gateway seam for a double everywhere the services read it.

    Patched in both the service and view modules because each imported
    `get_gateway` into its own namespace; patching only one would leave the
    other making real HTTP calls.
    """
    import apps.payments.services as payments_services
    import apps.payments.views as payments_views
    from tests.factories.gateway import FakeGateway

    gateway = FakeGateway()
    monkeypatch.setattr(payments_services, "get_gateway", lambda: gateway)
    monkeypatch.setattr(payments_views, "get_gateway", lambda: gateway)
    return gateway


def slot_at(hours: int = 0, minutes: int = 0) -> datetime:
    """An aware local datetime for a slot offset from `FIRST_SLOT`."""
    return FIRST_SLOT + timedelta(hours=hours, minutes=minutes)


def slot_iso(hours: int = 0, minutes: int = 0) -> str:
    """The same slot as an ISO-8601 string, for request bodies."""
    return slot_at(hours, minutes).isoformat()
