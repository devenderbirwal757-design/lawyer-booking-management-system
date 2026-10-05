from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from common.querysets import tenant_context
from tests.testapp.models import Widget

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

WIDGETS = "/api/v1/test-widgets/"


class FakeTenant:
    def __init__(self, pk: str) -> None:
        self.pk = pk


def _make(tenant: str, name: str = "w") -> Widget:
    return Widget.objects.create(tenant_id=tenant, name=name)


def test_list_is_empty_without_a_tenant(api_client: APIClient) -> None:
    _make("t-1")

    response = api_client.get(WIDGETS)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 0


def test_list_only_returns_the_current_tenants_rows(api_client: APIClient) -> None:
    _make("t-1", "mine")
    _make("t-2", "theirs")

    with tenant_context(FakeTenant("t-1")):
        response = api_client.get(WIDGETS)

    assert response.status_code == status.HTTP_200_OK
    names = [row["name"] for row in response.json()["results"]]
    assert names == ["mine"]


def test_pagination_envelope_is_present(api_client: APIClient) -> None:
    for index in range(3):
        _make("t-1", f"w{index}")

    with tenant_context(FakeTenant("t-1")):
        response = api_client.get(WIDGETS, {"page_size": 2})

    body = response.json()
    assert body["count"] == 3
    assert body["page_size"] == 2
    assert body["num_pages"] == 2
    assert body["next"] is not None
    assert len(body["results"]) == 2


def test_cross_tenant_retrieve_is_404_not_403(api_client: APIClient) -> None:
    """Leaking existence via 403 would confirm the row exists (plan §12)."""
    theirs = _make("t-2", "theirs")

    with tenant_context(FakeTenant("t-1")):
        response = api_client.get(f"{WIDGETS}{theirs.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "not_found"


def test_business_errors_use_the_error_envelope(api_client: APIClient) -> None:
    with tenant_context(FakeTenant("t-1")):
        response = api_client.post(f"{WIDGETS}conflict/")

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "error": {
            "code": "slot_unavailable",
            "message": "That time slot is no longer available.",
            "details": None,
        }
    }


def test_validation_errors_use_the_error_envelope(api_client: APIClient) -> None:
    with tenant_context(FakeTenant("t-1")):
        response = api_client.post(WIDGETS, {}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert "name" in body["details"]


def test_malformed_idempotency_key_is_rejected(api_client: APIClient) -> None:
    with tenant_context(FakeTenant("t-1")):
        response = api_client.post(
            WIDGETS, {"name": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="not-a-uuid"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "idempotency_key" in response.json()["error"]["details"]


def test_valid_idempotency_key_is_accepted(api_client: APIClient) -> None:
    with tenant_context(FakeTenant("t-1")):
        response = api_client.post(
            WIDGETS, {"name": "x"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )

    assert response.status_code == status.HTTP_201_CREATED


def test_delete_is_a_soft_delete(api_client: APIClient) -> None:
    widget = _make("t-1", "doomed")

    with tenant_context(FakeTenant("t-1")):
        response = api_client.delete(f"{WIDGETS}{widget.pk}/")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert Widget.objects.unfiltered().get(pk=widget.pk).is_active is False


def test_admin_django_login_page_is_reachable(client: Any) -> None:
    response = client.get("/admin/login/")

    assert response.status_code == status.HTTP_200_OK
