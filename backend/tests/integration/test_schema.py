from __future__ import annotations

from typing import Any

import pytest
from django.urls import reverse
from drf_spectacular.validation import validate_schema

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def schema(admin_client: Any) -> dict[str, Any]:
    response = admin_client.get(reverse("schema"), HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    return response.json()


def test_schema_is_generated_without_errors(schema: dict[str, Any]) -> None:
    """drf-spectacular warnings are API contract bugs; fail on them."""
    validate_schema(schema)

    assert str(schema["openapi"]).startswith("3.")
    assert "/api/v1/test-widgets/" in schema["paths"]


def test_schema_is_served_under_the_versioned_prefix(schema: dict[str, Any]) -> None:
    assert schema["servers"] == [{"url": "/api/v1"}]
    # NamespaceVersioning appends the namespace to the version string.
    assert schema["info"]["version"] == "1.0.0 (v1)"


def test_swagger_ui_is_mounted(client: Any) -> None:
    response = client.get("/api/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.content.lower()
