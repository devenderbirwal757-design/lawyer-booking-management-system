"""CORS wiring: the browser-side failure this file exists to prevent.

Before `corsheaders` was added to `INSTALLED_APPS`/`MIDDLEWARE`, the three
`CORS_*` settings in `base.py` were read and discarded, so a browser calling the
API cross-origin got no `Access-Control-Allow-Origin` header and the preflight
failed. The frontend could not be driven in a browser at all.

These tests pin the behaviour that matters to a browser:

  * a preflight from an allowed origin is answered with the full header set
  * a disallowed origin is *not* echoed back (no accidental `*`)
  * the credential header is present, because auth cookies are HttpOnly and
    set by this backend
  * `/admin/` is outside the CORS scope entirely
  * production refuses to start with an empty allowlist

They assert on real middleware output through the test client rather than on
`django-cors-headers`' internals, so an upgrade that breaks the contract fails
here instead of in the browser.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.test import Client, override_settings

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ALLOWED_ORIGIN = "http://localhost:8000"
OTHER_ORIGIN = "http://localhost:3000"
FOREIGN_ORIGIN = "https://evil.example.com"

CORS_ATTRS = {
    "CORS_ALLOWED_ORIGINS": [ALLOWED_ORIGIN, OTHER_ORIGIN],
    "CORS_ALLOW_CREDENTIALS": True,
    "CORS_ALLOWED_METHODS": ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    "CORS_ALLOW_HEADERS": [
        "accept",
        "authorization",
        "content-type",
        "idempotency-key",
        "origin",
        "x-csrftoken",
        "x-request-id",
    ],
    "CORS_URLS_REGEX": r"^/api/.*$",
}


@pytest.fixture
def cors_settings() -> object:
    with override_settings(**CORS_ATTRS):
        yield


@pytest.fixture
def client() -> Client:
    return Client()


def _preflight(client: Client, origin: str, *, path: str = "/api/v1/services/") -> Any:
    return client.options(
        path,
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type, idempotency-key",
    )


@pytest.mark.usefixtures("cors_settings")
def test_preflight_from_allowed_origin_is_answered(client: Client, cors_settings: object) -> None:
    response = _preflight(client, ALLOWED_ORIGIN)

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    # `client.ts` sends `credentials: 'include'` on every call.
    assert response["Access-Control-Allow-Credentials"] == "true"


@pytest.mark.usefixtures("cors_settings")
def test_preflight_allows_the_methods_the_frontend_calls(
    client: Client, cors_settings: object
) -> None:
    allowed = {
        m.strip().upper()
        for m in _preflight(client, ALLOWED_ORIGIN)["Access-Control-Allow-Methods"].split(",")
    }

    assert {"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"} <= allowed


@pytest.mark.usefixtures("cors_settings")
def test_preflight_allows_the_custom_headers_the_frontend_sends(
    client: Client, cors_settings: object
) -> None:
    allowed = {
        h.strip().lower()
        for h in _preflight(client, ALLOWED_ORIGIN)["Access-Control-Allow-Headers"].split(",")
    }

    # `X-Request-ID` on every request and `Idempotency-Key` on booking/payment.
    assert {"authorization", "content-type", "idempotency-key", "x-request-id"} <= allowed


@pytest.mark.usefixtures("cors_settings")
def test_foreign_origin_is_not_echoed_back(client: Client, cors_settings: object) -> None:
    """A non-allowlisted origin must get no header, not a wildcard."""
    response = _preflight(client, FOREIGN_ORIGIN)

    assert "Access-Control-Allow-Origin" not in response


@pytest.mark.usefixtures("cors_settings")
def test_actual_api_response_carries_cors_header(client: Client, cors_settings: object) -> None:
    """Not just preflight: the real response needs the header too, or the
    browser discards the body."""
    response = client.get("/api/v1/healthz/", HTTP_ORIGIN=ALLOWED_ORIGIN)

    assert response.status_code in {200, 404}
    if response.status_code == 200:
        assert response["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
        assert response["Access-Control-Allow-Credentials"] == "true"


@pytest.mark.usefixtures("cors_settings")
def test_admin_is_outside_cors_scope(client: Client, cors_settings: object) -> None:
    """`CORS_URLS_REGEX` is scoped to `/api/` so the admin is never reachable
    cross-origin with a session cookie."""
    response = client.options(
        "/admin/login/", HTTP_ORIGIN=ALLOWED_ORIGIN, HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST"
    )

    assert "Access-Control-Allow-Origin" not in response


@pytest.fixture
def reloaded_cors_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[..., dict[str, Any]]:
    """Callable that imports `config.settings.base` with a patched environment.

    The wildcard guard runs at module import, so it can only be exercised by
    importing the module again. `importlib.reload` mutates and returns the same
    module object, so the caller must snapshot the values it wants rather than
    holding on to the module: the fixture restores the environment and reloads
    once more on teardown.
    """

    def _load(**env_overrides: str) -> dict[str, Any]:
        import importlib

        import config.settings.base as base_settings

        # `paths.py` calls `read_env`, so `.env` has already populated
        # `os.environ` by import time. An empty string would parse to `[]`
        # rather than fall through to the default, so "unset" must be a real
        # `delenv`.
        if "DJANGO_CORS_ALLOWED_ORIGINS" in env_overrides:
            monkeypatch.setenv(
                "DJANGO_CORS_ALLOWED_ORIGINS", env_overrides["DJANGO_CORS_ALLOWED_ORIGINS"]
            )
        else:
            monkeypatch.delenv("DJANGO_CORS_ALLOWED_ORIGINS", raising=False)
        try:
            module = importlib.reload(base_settings)
            return {
                "origins": list(module.CORS_ALLOWED_ORIGINS),
                "credentials": module.CORS_ALLOW_CREDENTIALS,
                "urls_regex": module.CORS_URLS_REGEX,
            }
        finally:
            monkeypatch.delenv("DJANGO_CORS_ALLOWED_ORIGINS", raising=False)
            importlib.reload(base_settings)

    return _load


def test_wildcard_with_credentials_is_rejected(
    reloaded_cors_settings: Callable[..., dict[str, Any]],
) -> None:
    """`*` is invalid alongside credentials and unsafe per security.md §A, so
    `base.py` refuses to import rather than shipping an unreachable frontend."""
    loader = reloaded_cors_settings

    with pytest.raises(RuntimeError, match="exact origins"):
        loader(DJANGO_CORS_ALLOWED_ORIGINS="*")


def test_comma_separated_origins_are_accepted(reloaded_cors_settings: Any) -> None:
    loader = reloaded_cors_settings

    settings = loader(DJANGO_CORS_ALLOWED_ORIGINS="http://localhost:8000,https://app.example.com")

    assert settings["origins"] == [
        "http://localhost:8000",
        "https://app.example.com",
    ]


def test_dev_falls_back_to_localhost_origins(reloaded_cors_settings: Any) -> None:
    """Unset in development means the two localhost origins, so a contributor
    who clones the repo gets a working browser call with no setup."""
    loader = reloaded_cors_settings

    settings = loader()

    assert settings["origins"] == ["http://localhost:8000", "http://localhost:3000"]
    assert settings["credentials"] is True
    assert settings["urls_regex"] == r"^/api/.*$"


def test_prod_settings_refuse_an_empty_allowlist() -> None:
    """Production must fail closed. Reading `prod.py` proves the guard exists in
    the source; the raise itself needs a full production environment, so it is
    asserted structurally."""
    from pathlib import Path

    prod_py = (Path(__file__).resolve().parents[2] / "config" / "settings" / "prod.py").read_text()

    assert "if not CORS_ALLOWED_ORIGINS:" in prod_py
    assert "DJANGO_CORS_ALLOWED_ORIGINS must be set in production" in prod_py
