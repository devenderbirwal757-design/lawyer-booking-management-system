from __future__ import annotations

from typing import Any

import pytest
from django.urls import reverse

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_healthz_is_liveness_only(client: Any) -> None:
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["X-Request-ID"]


def test_healthz_is_never_cached(client: Any) -> None:
    response = client.get(reverse("healthz"))

    assert "no-cache" in response["Cache-Control"]


def test_readyz_checks_database_and_cache(client: Any) -> None:
    response = client.get(reverse("readyz"))
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] == {"ok": True}
    assert payload["checks"]["cache"] == {"ok": True}


def test_readyz_reports_degraded_when_cache_is_down(client: Any, settings: Any) -> None:
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            "LOCATION": "unused",
        }
    }
    from django.core.cache import cache

    cache.clear()

    response = client.get(reverse("readyz"))

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["cache"]["ok"] is False
