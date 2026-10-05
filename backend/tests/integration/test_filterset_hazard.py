"""Reproduces the two hazards behind the `filterset_fields` ban.

`tests/unit/test_filterset_guard.py` bans `filterset_fields` on tenant-scoped
viewsets and explains why. This file is the evidence for that explanation: it
demonstrates the behaviour against the real installed django-filter, so the
rationale cannot rot into folklore.

These tests assert *third-party* behaviour on purpose. If a future django-filter
upgrade stops disclosing related models, or stops needing a bound tenant, the
failure here is the signal to revisit the ban rather than a nuisance.
"""

from __future__ import annotations

from typing import Any

import pytest
from django_filters.rest_framework import DjangoFilterBackend  # type: ignore[import-untyped]
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.providers.models import Provider
from apps.tenants.models import Tenant
from common.exceptions import TenantContextMissing
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class FakeView:
    """The three attributes `DjangoFilterBackend` reads off a real viewset."""

    filterset_class = None

    def __init__(self, queryset: Any, filterset_fields: list[str] | None) -> None:
        self.queryset = queryset
        self.filterset_fields = filterset_fields

    def get_queryset(self) -> Any:
        return self.queryset


@pytest.fixture
def three_tenants(db: Any) -> list[Tenant]:
    tenants = []
    for slug in ("alpha", "beta", "gamma"):
        tenant = Tenant.objects.create(slug=slug, name=f"{slug} LLP", timezone="Asia/Kolkata")
        Provider.objects.unfiltered().create(tenant=tenant, name=f"Dr-{slug}", is_active=True)
        tenants.append(tenant)
    return tenants


def _request(query: str) -> Request:
    return Request(APIRequestFactory().get(f"/api/v1/providers/{query}"))


# ----------------------------------------- hazard 1: it discloses other practices


def test_relation_field_publishes_every_tenant(three_tenants: list[Tenant]) -> None:
    """The leak. `?tenant=` choices enumerate all practices, not just your own."""
    alpha = three_tenants[0]
    queryset = Provider.objects.unfiltered().filter(tenant_id=alpha.pk)
    view = FakeView(queryset, ["tenant"])

    with tenant_context(alpha):
        filterset_class = DjangoFilterBackend().get_filterset_class(view, queryset)
        choices = filterset_class.base_filters["tenant"].field.queryset
        revealed = sorted(choices.values_list("slug", flat=True))

    assert revealed == ["alpha", "beta", "gamma"]
    assert len(revealed) > 1, "the disclosure is the point: one caller, three practices"


def test_rows_themselves_stay_scoped(three_tenants: list[Tenant]) -> None:
    """The disclosure is the real problem; be precise that rows do not leak.

    If this ever changes to a row leak, the ban is more urgent, not less - but
    the two must not be conflated in the rationale.
    """
    alpha, beta, _ = three_tenants
    queryset = Provider.objects.unfiltered().filter(tenant_id=alpha.pk)
    view = FakeView(queryset, ["tenant"])

    with tenant_context(alpha):
        result = DjangoFilterBackend().filter_queryset(
            _request(f"?tenant={beta.pk}"), view.get_queryset(), view
        )

    assert result.count() == 0


# ------------------------------------------- hazard 2: it needs a bound tenant


def test_building_the_filterset_raises_with_no_tenant(three_tenants: list[Tenant]) -> None:
    """Schema generation has no request, so this is what breaks spectacular."""
    queryset = Provider.objects.unfiltered()

    with pytest.raises(TenantContextMissing):
        DjangoFilterBackend().get_filterset_class(FakeView(queryset, ["name"]), queryset)


def test_filtering_raises_with_no_tenant(three_tenants: list[Tenant]) -> None:
    """Any list request reached before a tenant is bound fails outright."""
    queryset = Provider.objects.unfiltered()

    with pytest.raises(TenantContextMissing):
        DjangoFilterBackend().filter_queryset(
            _request("?name=x"), queryset, FakeView(queryset, ["name"])
        )


def test_it_works_when_a_tenant_is_bound(three_tenants: list[Tenant]) -> None:
    """The behaviour that makes it a landmine rather than an outright bug.

    Passes in a request with a tenant, so it survives casual use and fails only
    in the cases that are hardest to notice.
    """
    alpha = three_tenants[0]
    with tenant_context(alpha):
        # Built inside the context: `Provider.objects.all()` is itself a read.
        queryset = Provider.objects.all()
        result = DjangoFilterBackend().filter_queryset(
            _request("?name=Dr-alpha"), queryset, FakeView(queryset, ["name"])
        )

    assert result.count() == 1


# ------------------------------------------------------- the sanctioned approach


def test_explicit_filter_params_needs_no_filterset(three_tenants: list[Tenant]) -> None:
    """`_filter_params()` validates in the viewset, so it needs no tenant at all."""
    from rest_framework.exceptions import ValidationError

    from apps.payments.views import _filter_params

    # Outside any tenant context entirely: this is the schema-generation case,
    # which is where a django-filter filterset raises.
    good = Request(APIRequestFactory().get("/api/v1/admin/payments/?outcome=SUCCEEDED"))
    assert _filter_params(good, choices={"outcome": {"SUCCEEDED"}}) == {"outcome": "SUCCEEDED"}

    # And a typo is a 400 rather than a silently empty page.
    bad = Request(APIRequestFactory().get("/api/v1/admin/payments/?outcome=NOPE"))
    with pytest.raises(ValidationError):
        _filter_params(bad, choices={"outcome": {"SUCCEEDED"}})
