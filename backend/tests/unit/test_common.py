from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from common.exceptions import TenantContextMissing
from common.querysets import (
    TenantScopedManager,
    TenantScopedQuerySet,
    actor_context,
    get_current_actor,
    get_current_tenant,
    tenant_context,
    tenant_q,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


class FakeTenant:
    def __init__(self, pk: str) -> None:
        self.pk = pk


# ---------------------------------------------------------------- contextvars
def test_tenant_context_roundtrip() -> None:
    assert get_current_tenant() is None
    with tenant_context(FakeTenant("t-1")):
        assert get_current_tenant().pk == "t-1"
    assert get_current_tenant() is None


def test_actor_context_roundtrip() -> None:
    assert get_current_actor() is None
    with actor_context("someone"):
        assert get_current_actor() == "someone"
    assert get_current_actor() is None


# ---------------------------------------------------------------- querysets
def test_for_tenant_returns_only_that_tenants_rows() -> None:
    from tests.testapp.models import Widget

    a, b = (
        Widget.objects.create(tenant_id="t-1", name="a"),
        Widget.objects.create(tenant_id="t-1", name="b"),
    )
    Widget.objects.create(tenant_id="t-2", name="c")

    scoped = Widget.objects.for_tenant("t-1")

    assert set(scoped) == {a, b}


def test_for_tenant_with_no_tenant_returns_nothing() -> None:
    from tests.testapp.models import Widget

    Widget.objects.create(tenant_id="t-1", name="a")

    assert list(Widget.objects.for_tenant(None)) == []


def test_for_tenant_works_inside_a_context_too() -> None:
    """`for_tenant` narrows explicitly, so it must not be capped by the context."""
    from tests.testapp.models import Widget

    Widget.objects.create(tenant_id="t-1", name="a")
    Widget.objects.create(tenant_id="t-2", name="b")

    with tenant_context(FakeTenant("t-1")):
        assert [w.name for w in Widget.objects.for_tenant("t-2")] == ["b"]


def test_manager_is_scoped_by_the_context_tenant() -> None:
    from tests.testapp.models import Widget

    Widget.objects.create(tenant_id="t-1", name="a")
    Widget.objects.create(tenant_id="t-2", name="b")

    with tenant_context(FakeTenant("t-2")):
        assert [w.name for w in Widget.objects.all()] == ["b"]


def test_reads_without_a_tenant_raise_instead_of_leaking() -> None:
    from tests.testapp.models import Widget

    Widget.objects.create(tenant_id="t-1", name="a")
    Widget.objects.create(tenant_id="t-2", name="b")

    # The dangerous default would be returning both rows here.
    with pytest.raises(TenantContextMissing):
        Widget.objects.all().count()
    with pytest.raises(TenantContextMissing):
        Widget.objects.get(tenant_id="t-1")
    with pytest.raises(TenantContextMissing):
        Widget.objects.filter(tenant_id="t-1").exists()


def test_create_does_not_require_a_tenant_context() -> None:
    """Inserts touch only the rows the caller names, so they stay open."""
    from tests.testapp.models import Widget

    widget = Widget.objects.create(tenant_id="t-1", name="a")
    assert widget.pk is not None
    assert list(Widget.objects.unfiltered().filter(tenant_id="t-1")) == [widget]


def test_bulk_create_does_not_require_a_tenant_context() -> None:
    from tests.testapp.models import Widget

    Widget.objects.bulk_create(
        [Widget(tenant_id="t-1", name="a"), Widget(tenant_id="t-1", name="b")]
    )
    assert Widget.objects.unfiltered().filter(tenant_id="t-1").count() == 2


def test_none_does_not_require_a_tenant_context() -> None:
    """drf-spectacular calls `_default_manager.none()` with no request context."""
    from tests.testapp.models import Widget

    assert list(Widget.objects.none()) == []


def test_manager_unfiltered_escapes_the_scope() -> None:
    from tests.testapp.models import Widget

    Widget.objects.create(tenant_id="t-1", name="a")
    Widget.objects.create(tenant_id="t-2", name="b")

    with tenant_context(FakeTenant("t-1")):
        assert Widget.objects.unfiltered().count() == 2


def test_tenant_q_matches_current_tenant() -> None:
    with tenant_context(FakeTenant("t-9")):
        q = tenant_q()
    assert q.children == [("tenant_id", "t-9")]


def test_tenant_q_without_tenant_matches_nothing() -> None:
    # With no tenant bound, the Q is built against an impossible pk.
    q = tenant_q()
    assert "pk__in" in str(q)


def test_queryset_subclasses_are_preserved() -> None:
    from tests.testapp.models import Widget

    # Outside any context, reads raise, so use the escape hatch here.
    assert isinstance(Widget.objects.unfiltered(), TenantScopedQuerySet)
    assert isinstance(Widget.objects, TenantScopedManager)
    with tenant_context(FakeTenant("t-1")):
        assert isinstance(Widget.objects.all(), TenantScopedQuerySet)


# ---------------------------------------------------------------- permissions
def test_is_admin_requires_authenticated_tenant_admin() -> None:
    from apps.accounts.models import Role, User
    from common.permissions import IsAdmin

    permission = IsAdmin()
    request = APIRequestFactory().get("/")
    request.user = AnonymousUser()
    assert permission.has_permission(request, None) is False

    # OWNER/ADMIN within a tenant grant access (S §A2, §A4).
    user = User(email="owner@example.com", is_active=True, role=Role.OWNER, tenant_id="t-1")
    request.user = user
    assert permission.has_permission(request, None) is True

    user.role = Role.VIEWER
    assert permission.has_permission(request, None) is False

    # A superuser is the documented break-glass for a locked-out tenant.
    user.role = Role.VIEWER
    user.is_superuser = True
    assert permission.has_permission(request, None) is True

    # `is_staff` alone (django.contrib.admin flag) is not enough: API access
    # must stay independently revocable from admin-panel access (S §A4).
    staff = User(
        email="staff@example.com", is_active=True, is_staff=True, role=Role.VIEWER, tenant_id="t-1"
    )
    request.user = staff
    assert permission.has_permission(request, None) is False


def test_is_tenant_member_blocks_cross_tenant_objects() -> None:
    from common.permissions import IsTenantMember
    from tests.testapp.models import Widget

    permission = IsTenantMember()
    request = APIRequestFactory().get("/")

    assert permission.has_object_permission(request, None, Widget(tenant_id="t-1")) is False

    with tenant_context(FakeTenant("t-1")):
        assert permission.has_object_permission(request, None, Widget(tenant_id="t-1")) is True
        assert permission.has_object_permission(request, None, Widget(tenant_id="t-2")) is False


# ---------------------------------------------------------------- middleware
def test_request_id_middleware_echoes_inbound_id() -> None:
    from django.http import HttpResponse

    from common.middleware import RequestIDMiddleware

    middleware = RequestIDMiddleware(lambda request: HttpResponse("ok"))
    request = APIRequestFactory().get("/healthz", HTTP_X_REQUEST_ID="abc123")
    response = middleware(request)

    assert response["X-Request-ID"] == "abc123"
    assert request.request_id == "abc123"  # type: ignore[attr-defined]


def test_request_id_middleware_generates_one_when_absent() -> None:
    from django.http import HttpResponse

    from common.middleware import RequestIDMiddleware

    middleware = RequestIDMiddleware(lambda request: HttpResponse("ok"))
    response = middleware(APIRequestFactory().get("/healthz"))

    assert len(response["X-Request-ID"]) == 32


# ---------------------------------------------------------------- config surface
def test_pagination_page_size_caps() -> None:
    from django.conf import settings

    from common.pagination import StandardPagination

    assert StandardPagination.max_page_size == 100
    assert settings.REST_FRAMEWORK["PAGE_SIZE"] <= 100


def test_all_planned_throttle_scopes_are_configured() -> None:
    from django.conf import settings

    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope in ("anon", "user", "otp_request", "otp_verify", "login", "booking", "webhook"):
        assert "/" in rates[scope], f"{scope} must be a rate like '5/hour'"


def test_flexible_rate_parses_multi_unit_windows() -> None:
    from common.throttles import FlexibleRateThrottle

    class _LoginThrottle(FlexibleRateThrottle):
        scope = "login"

    throttle = _LoginThrottle()
    assert throttle.parse_rate("5/15min") == (5, 900)
    assert throttle.parse_rate("60/min") == (60, 60)
    assert throttle.parse_rate("5/hour") == (5, 3600)
    assert throttle.parse_rate("100/day") == (100, 86400)
    assert throttle.parse_rate("10/15min") == (10, 900)


def _throttle_view() -> Any:
    """The `view` DRF would hand `get_cache_key`.

    Both login throttles are `ScopedRateThrottle`s that already know their
    scope, so the argument is unused by the implementations under test; it is
    passed as a real `APIView` because that is what the base class demands.
    """
    from rest_framework.views import APIView

    return APIView()


def test_admin_login_throttle_keys_on_ip_and_submitted_email() -> None:
    """The per-email side must come from the *body*, not the resolved user,
    so a spray against nonexistent addresses still accumulates (S §A2)."""
    from common.throttles import AdminLoginRateThrottle, LoginRateThrottle

    login = LoginRateThrottle()
    admin = AdminLoginRateThrottle()

    request = _login_request(" Victim@Example.com ")
    ip_key = login.get_cache_key(request, _throttle_view())
    email_key = admin.get_cache_key(request, _throttle_view())

    assert ip_key is not None and email_key is not None
    assert ip_key != email_key
    assert "victim@example.com" in email_key
    assert "victim@example.com" not in ip_key

    # Both hit the same IP bucket even for different emails...
    other = _login_request("other@example.com")
    assert login.get_cache_key(other, _throttle_view()) == ip_key
    # ...but the per-email bucket is distinct per address.
    assert admin.get_cache_key(other, _throttle_view()) != email_key


def _login_request(email: str) -> Any:
    """An anonymous, unauthenticated login POST, the way the view sees it.

    Wrapped in a DRF `Request` rather than assigned to `.data` by hand: `data`
    is a read-only property backed by the parsed body, and a throttle that
    reads a hand-set attribute would not be reading what it reads in production.
    """
    from rest_framework.parsers import JSONParser
    from rest_framework.request import Request as DRFRequest

    raw = APIRequestFactory().post(
        "/api/v1/auth/admin/login",
        {"email": email, "password": "x"},
        format="json",
    )
    request = DRFRequest(raw, parsers=[JSONParser()])
    request.user = AnonymousUser()
    return request


def test_api_is_versioned_from_day_one() -> None:
    from django.conf import settings

    assert settings.REST_FRAMEWORK["DEFAULT_VERSION"] == "v1"
    assert settings.REST_FRAMEWORK["ALLOWED_VERSIONS"] == ["v1"]


def test_error_envelope_is_wired() -> None:
    from django.conf import settings

    assert settings.REST_FRAMEWORK["EXCEPTION_HANDLER"] == "common.exceptions.api_exception_handler"
