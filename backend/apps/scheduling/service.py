"""The server-side slot generator (plan §3.1, D4/D5).

`SlotService.slots(provider, service, date)` is the single source of truth the
booking endpoint will re-run at Phase 5, so an arbitrary client-supplied time
never gets booked. The recipe, per day:

    recurring rules (that weekday, effective that day)
        ∪ day-level OVERRIDE exception            (OVERRIDE replaces the week)
        − BLOCKED exceptions
        − busy spans (other appointments/holds)   (Phase 5 supplies these)
    then walk forward in `duration + buffer_after` steps from each window's
    start, keeping every start whose consultation fits before the window end.

Two rules are load-bearing and both are §B1/D4 contracts:

- **Anchoring.** The grid is anchored at the window start, and the step is
  `duration + buffer_after`. There is no separate interval field, so a
  45-minute and a 30-minute service interleave without ever producing the
  unusable 10:45-11:00 gap a fixed grid creates.
- **The consultation must fit; the buffer may overrun.** "Fits" means
  `start + duration <= end`: the last slot is *never* truncated to pull its
  buffer back inside the window (a provider needs their five minutes after
  close). The buffer also counts as occupied time when checking a busy span,
  so a slot is never offered that would collide with the *next* booking's
  turnaround.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from itertools import chain
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache

from apps.scheduling.models import AvailabilityException, AvailabilityRule

Window = tuple[datetime, datetime]

#: Slot results are cached briefly keyed by provider+service+date so the
#: calendar cannot hammer the DB (plan §3 Phase 3); `bump_provider_revision`
#: invalidates a provider's keys the moment a rule or exception changes.
_SLOTS_PREFIX = "availability-slots:v1"
_REVISION_KEY = "availability-revision:%s"


def _lead_time() -> timedelta:
    return timedelta(minutes=getattr(settings, "AVAILABILITY_LEAD_TIME_MINUTES", 0))


def _horizon_days() -> int:
    return int(getattr(settings, "AVAILABILITY_HORIZON_DAYS", 60))


def _cache_seconds() -> int:
    return int(getattr(settings, "AVAILABILITY_CACHE_SECONDS", 60))


def bump_provider_revision(provider_id: Any) -> None:
    """Invalidate every cache entry for one provider's availability."""
    if not provider_id:
        return
    key = _REVISION_KEY % provider_id
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1)


class SlotService:
    """Compute bookable start times for one provider/service on days in one tenant TZ.

    `timezone` defaults to the provider's tenant timezone; `busy` is an
    iterable of aware `(start, end)` pairs (or objects with `start_at`/`end_at`)
    occupying the provider's calendar, which Phase 5 will feed from the
    appointment table. `now`, `lead_time` and `horizon_days` exist so tests can
    pin time - pinning any of them (or supplying `busy`) turns the brief cache
    off for that run, because the answer is now a point in time, not a grid.
    """

    def __init__(
        self,
        *,
        provider: Any,
        service: Any,
        timezone: str | None = None,
        busy: Iterable[Any] = (),
        now: datetime | None = None,
        lead_time: timedelta | None = None,
        horizon_days: int | None = None,
    ) -> None:
        self.provider = provider
        self.service = service
        self.tz = ZoneInfo(timezone or provider.tenant.timezone or "UTC")
        self.busy = self._normalise_busy(busy)
        self.now = (now or datetime.now(self.tz)).astimezone(self.tz)
        self.lead_time = _lead_time() if lead_time is None else lead_time
        self.horizon_days = _horizon_days() if horizon_days is None else horizon_days
        self._cacheable = (
            not self.busy and now is None and lead_time is None and horizon_days is None
        )

    # ------------------------------------------------------------ public API
    def slots(self, day: date) -> list[datetime]:
        """Bookable start times for one day, aware datetimes in the tenant TZ."""
        if not self._cacheable:
            return self._compute_slots(day)
        key = self._cache_key(day)
        cached = cache.get(key)
        if cached is not None:
            return [datetime.fromisoformat(slot) for slot in cached]
        result = self._compute_slots(day)
        cache.set(key, [slot.isoformat() for slot in result], timeout=_cache_seconds())
        return result

    def dates_for_month(self, year: int, month: int) -> list[date]:
        """Days of the month that have at least one bookable slot (calendar view)."""
        days = [date(year, month, d) for d in range(1, monthrange(year, month)[1] + 1)]
        return [day for day in days if self.slots(day)]

    # ------------------------------------------------------------ internals
    def _cache_key(self, day: date) -> str:
        revision = cache.get(_REVISION_KEY % self.provider.pk, 0)
        return (
            f"{_SLOTS_PREFIX}:{self.provider.pk}:{self.service.pk}:{day.isoformat()}:"
            f"{self.tz.key}:{self.horizon_days}:{revision}"
        )

    def _compute_slots(self, day: date) -> list[datetime]:
        if self._beyond_horizon(day):
            return []
        windows = self._windows_for(day)
        return sorted(chain.from_iterable(self._walk(window) for window in windows))

    def _beyond_horizon(self, day: date) -> bool:
        return day > self.now.date() + timedelta(days=self.horizon_days)

    def _normalise_busy(self, busy: Iterable[Any]) -> list[Window]:
        spans: list[Window] = []
        for item in busy:
            if isinstance(item, (tuple, list)) and len(item) == 2:
                spans.append((item[0], item[1]))
            elif hasattr(item, "start_at") and hasattr(item, "end_at"):
                spans.append((item.start_at, item.end_at))
            else:  # pragma: no cover - defensive
                raise TypeError(f"Cannot read a busy span from {item!r}")
        return [(s.astimezone(self.tz), e.astimezone(self.tz)) for s, e in spans]

    def _windows_for(self, day: date) -> list[Window]:
        """Working windows for `day`: weekday rules, OR the override, minus blocks."""
        # Read unfiltered on purpose: the related managers inherit the
        # tenant-scoped manager, and the engine is given an explicit provider -
        # it must see that provider's calendar even with no ambient tenancy.
        exceptions = AvailabilityException.objects.unfiltered().filter(
            provider=self.provider, date=day
        )
        override = next((e for e in exceptions if e.type == "OVERRIDE"), None)
        if override is not None:
            base = [override.window_as(self.tz.key)]
        else:
            base = []
            for rule in AvailabilityRule.objects.unfiltered().filter(
                provider=self.provider, weekday=day.isoweekday() % 7
            ):
                if rule.is_effective_on(day):
                    base.append(rule_window(rule, day, self.tz))
        blocked = [e.window_as(self.tz.key) for e in exceptions if e.type == "BLOCKED"]
        windows = _subtract(base, blocked)
        return [w for w in windows if w[1] > w[0]]

    def _walk(self, window: Window) -> list[datetime]:
        duration = timedelta(minutes=self.service.duration_minutes)
        step = timedelta(minutes=self.service.duration_minutes + self.service.buffer_after_minutes)
        start, end = window
        result: list[datetime] = []
        cursor = start
        while cursor + duration <= end:
            if self._available(cursor, step):
                result.append(cursor)
            cursor += step
        return result

    def _available(self, start: datetime, span: timedelta) -> bool:
        if start < self.now + self.lead_time:
            return False
        contender = (start, start + span)
        return not any(
            contender[0] < busy_end and busy_start < contender[1]
            for busy_start, busy_end in self.busy
        )


def rule_window(rule: Any, day: date, tz: ZoneInfo) -> Window:
    """The rule's window on `day` as aware datetimes in the provider's TZ."""
    return (
        datetime.combine(day, rule.start_time, tzinfo=tz),
        datetime.combine(day, rule.end_time, tzinfo=tz),
    )


def _subtract(base: list[Window], removals: list[Window]) -> list[Window]:
    """Base windows minus any blocked windows, preserving order."""
    out = list(base)
    for removal in sorted(removals):
        next_out: list[Window] = []
        for segment in out:
            next_out.extend(_cut(segment, removal))
        out = next_out
    return out


def _cut(segment: Window, removal: Window) -> list[Window]:
    a0, a1 = segment
    b0, b1 = removal
    if b1 <= a0 or b0 >= a1:
        return [segment]
    pieces: list[Window] = []
    if a0 < b0:
        pieces.append((a0, min(b0, a1)))
    if b1 < a1:
        pieces.append((max(b1, a0), a1))
    return pieces


__all__ = ("SlotService",)
