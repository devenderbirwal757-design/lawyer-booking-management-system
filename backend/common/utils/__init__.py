from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.text import slugify


def unique_slug(model: Any, value: str, field: str = "slug", pk: Any = None) -> str:
    """Return a slug unique within `model`, appending -2, -3, ... on collision."""
    base = slugify(value)[:180] or "item"
    candidate = base
    suffix = 2
    queryset = model._default_manager.all()
    if pk is not None:
        queryset = queryset.exclude(pk=pk)
    while queryset.filter(**{field: candidate}).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def now() -> Any:
    """Single entry point for 'now' so tests can freeze one thing."""
    return timezone.now()


def local_now(tenant: Any) -> Any:
    """Current time in the tenant's timezone (plan §3)."""
    from zoneinfo import ZoneInfo

    tz_name = getattr(tenant, "timezone", None) or "UTC"
    return timezone.now().astimezone(ZoneInfo(str(tz_name)))


def as_decimal(value: Any, places: str = "0.01") -> Any:
    from decimal import ROUND_HALF_UP, Decimal

    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def client_ip(request: Any) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        first: str = forwarded.split(",")[0].strip()
        return first
    remote = request.META.get("REMOTE_ADDR")
    return str(remote) if remote else None
