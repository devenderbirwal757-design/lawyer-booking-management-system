from __future__ import annotations

from typing import Any

from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness probe: the process is up and serving. No dependencies touched."""
    return JsonResponse({"status": "ok"})


@never_cache
@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    """Readiness probe: PostgreSQL and Redis must both answer."""
    checks: dict[str, Any] = {"database": _check_database(), "cache": _check_cache()}
    healthy = all(result["ok"] for result in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )


def _check_database() -> dict[str, Any]:
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


def _check_cache() -> dict[str, Any]:
    from django.core.cache import cache

    try:
        cache.set("healthcheck", "ok", timeout=5)
        return {"ok": cache.get("healthcheck") == "ok"}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
