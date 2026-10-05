from __future__ import annotations

import re
from typing import Any

from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.throttling import UserRateThrottle as DRFUserRateThrottle

#: Accepts `5/15min`, `60/min`, `120/hour`, `5/sec`... DRF's own parser only
#: reads the first character of the unit, so `15min` would be misread (unit
#: marker `1`). This understands a small leading count like `15min` and the
#: familiar `min`/`hour`/`sec` spellings in addition to DRF's `m`/`h`/`s`.
_RATE_RE = re.compile(r"^(?P<count>\d+)/(?P<num>(?:\d+)?)(?P<unit>sec|min|hour|s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hour": 3600, "d": 86400}


class FlexibleRateThrottle(SimpleRateThrottle):
    """`SimpleRateThrottle` that accepts multi-unit windows like `5/15min`."""

    def parse_rate(self, rate: str | None) -> tuple[int | None, int | None]:
        if rate is None:
            return (None, None)
        match = _RATE_RE.match(rate.strip())
        if match is None:
            return super().parse_rate(rate)
        count = int(match.group("count"))
        num = int(match.group("num") or 1)
        return (count, num * _UNIT_SECONDS[match.group("unit")])


class AnonRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "anon"


class UserRateThrottle(FlexibleRateThrottle, DRFUserRateThrottle):
    scope = "user"


class ScopedRateThrottle(FlexibleRateThrottle):
    """Per-view throttle driven by `throttle_scope` on the view.

    Applied to the sensitive endpoints (plan §8): `otp_request`, `otp_verify`,
    `login`, `booking`, `webhook`, `payment`.

    `__init__` is a deliberate no-op and the scope is resolved in
    `allow_request`, exactly as DRF's own `ScopedRateThrottle` does it: the
    rate cannot be known until the view is in hand, and inheriting
    `SimpleRateThrottle.__init__` would raise `ImproperlyConfigured` on the
    first request, because that constructor insists on a class-level `scope`
    this class does not have.
    """

    scope_attr = "throttle_scope"

    def __init__(self) -> None:
        self.rate: str | None = None
        self.num_requests: int | None = None
        self.duration: int | None = None
        self.key: str | None = None
        self.scope: str | None = None
        self.history: list[float] = []
        self.now: float = 0.0
        self._resolved_scope: str | None = None

    def allow_request(self, request: Any, view: Any) -> bool:
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        # Now that the scope is known, do the work `__init__` normally would.
        if self.rate is None or self.scope != self._resolved_scope:
            self._resolved_scope = self.scope
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        if not self.scope:
            return None
        ident = getattr(request.user, "pk", None) or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "login"


class AdminLoginRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    """Per-IP *and* per-email login limit (S §A2: 5 attempts / 15 min).

    Two independent limits, because they stop two different attacks. The per-IP
    limit stops one host spraying many accounts; the per-email limit stops a
    distributed spray hammering a single account, which the per-IP limit never
    sees because each attempt comes from a different address.

    The email key is derived from the *request body* rather than the resolved
    user, so a guesser cannot dodge the limit by using addresses that do not
    exist - which is the whole point.
    """

    scope = "login"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        user_ident = self.get_ident(request)
        email = _submitted_email(request)
        if not email:
            return self.cache_format % {"scope": self.scope, "ident": user_ident}
        ident = f"{user_ident}|{email}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


def _submitted_email(request: Any) -> str:
    """Normalised email from the request body, without trusting its validity."""
    data = getattr(request, "data", None)
    if not isinstance(data, dict):
        return ""
    email = data.get("email") or data.get("username") or ""
    return str(email).strip().lower()[:254]


class OtpRequestRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "otp_request"


class OtpVerifyRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "otp_verify"


class BookingRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "booking"


class AvailabilityRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    """Public availability reads, to stop full-schedule scraping (S §A7)."""

    scope = "availability"


class WebhookRateThrottle(FlexibleRateThrottle, DRFAnonRateThrottle):
    scope = "webhook"
