from __future__ import annotations

from typing import Any

import pytest
from django.core.checks import Error, Warning
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.tenants.checks import (
    NO_DEFAULT_TENANT,
    SUSPENDED_DEFAULT_TENANT,
    UNRESOLVED_DEFAULT_TENANT,
    check_default_tenant_slug,
)
from apps.tenants.models import TenantStatus
from common.exceptions import TenantContextMissing, api_exception_handler

pytestmark = pytest.mark.unit


def _run() -> list[Any]:
    return check_default_tenant_slug(None)


def _handler(exc: Exception) -> tuple[int, str, str]:
    request = APIRequestFactory().get("/api/v1/whatever/")
    response = api_exception_handler(exc, {"request": request})
    error = response.data["error"]
    return response.status_code, error["code"], error["message"]


# ------------------------------------------------------------------ system check


def test_unset_default_slug_warns_but_does_not_error(settings: Any) -> None:
    """Unset is legal: subdomain and X-Tenant-Slug routing need no default.

    Hard-failing here would break a valid multi-tenant deployment, so the check
    reports a Warning and leaves the exit code alone.
    """
    settings.DEFAULT_TENANT_SLUG = None

    messages = _run()

    assert len(messages) == 1
    assert isinstance(messages[0], Warning)
    assert not isinstance(messages[0], Error)
    assert messages[0].id == NO_DEFAULT_TENANT
    hint = messages[0].hint
    assert hint is not None
    assert "DJANGO_DEFAULT_TENANT_SLUG" in hint


def test_unset_default_slug_warning_explains_the_quiet_symptom(settings: Any) -> None:
    """The whole point: `200` with zero rows is indistinguishable from empty."""
    settings.DEFAULT_TENANT_SLUG = None

    hint = _run()[0].hint

    assert hint is not None
    assert "zero rows" in hint
    assert "TenantContextMissing" in hint


@pytest.mark.django_db
def test_unresolvable_default_slug_is_an_error(settings: Any) -> None:
    """Set but bogus fails every deployment, so it must block the boot."""
    settings.DEFAULT_TENANT_SLUG = "no-such-practice"

    messages = _run()

    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert messages[0].id == UNRESOLVED_DEFAULT_TENANT
    assert "no-such-practice" in messages[0].msg


@pytest.mark.django_db
def test_suspended_default_slug_is_an_error(settings: Any, booking_tenant: Any) -> None:
    """A suspended practice 404s every default-routed request (`_require_active`)."""
    booking_tenant.status = TenantStatus.SUSPENDED
    booking_tenant.save(update_fields=["status"])
    settings.DEFAULT_TENANT_SLUG = booking_tenant.slug

    messages = _run()

    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert messages[0].id == SUSPENDED_DEFAULT_TENANT


@pytest.mark.django_db
def test_valid_default_slug_is_clean(settings: Any, booking_tenant: Any) -> None:
    settings.DEFAULT_TENANT_SLUG = booking_tenant.slug

    assert _run() == []


@pytest.mark.django_db
@pytest.mark.parametrize("configured", ["  DWYER  ", "dwyer"])
def test_slug_is_normalised_the_way_the_middleware_normalises_it(
    settings: Any, booking_tenant: Any, configured: str
) -> None:
    """`TenantMiddleware` looks up `slug.strip().lower()`; the check must agree.

    If it did not, the check would pass a deployment that 404s on every request.
    """
    assert booking_tenant.slug == "dwyer"
    settings.DEFAULT_TENANT_SLUG = configured

    assert _run() == []


# ------------------------------------------------------------- runtime envelope


def test_tenant_context_missing_is_named_not_opaque() -> None:
    """A 500 telling the operator which variable to set beats a generic 500."""
    status_code, code, message = _handler(TenantContextMissing())

    assert status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert code == "tenant_context_missing"
    assert code != "internal_error"
    assert "DJANGO_DEFAULT_TENANT_SLUG" in message


def test_unrelated_exceptions_are_still_generic() -> None:
    """The actionable message must not leak into ordinary bugs."""
    _, code, message = _handler(RuntimeError("boom"))

    assert code == "internal_error"
    assert message == "An unexpected error occurred."
    assert "DJANGO_DEFAULT_TENANT_SLUG" not in message
