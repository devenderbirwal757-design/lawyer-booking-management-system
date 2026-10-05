"""Slot engine + availability model constraints (plan §3.1, D4, §B3).

The engine's rules, encoded here:

- step = `duration + buffer_after`, anchored at the window start;
- keep a start iff `start + duration <= window_end` (the consultation must fit);
- the buffer may overrun the window end and is never truncated;
- exceptions subtract (BLOCKED) or replace (OVERRIDE);
- `busy` spans exclude any slot whose full span overlaps them.

The D-tests in the plan surface as: the PRD 30-min/10:00-13:00 example yields
10:00...12:30; a 45-min(+5) service walks 10:00/10:50/11:40; a 60-min service
never offers 12:30; `buffer_after=0` reproduces the PRD example; and the final
slot of the day survives when its buffer overruns closing time.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from apps.providers.models import Provider
from apps.scheduling.service import SlotService
from apps.services.models import Service
from apps.tenants.models import Tenant
from common.querysets import tenant_context

pytestmark = [pytest.mark.django_db]

KOLKATA = "Asia/Kolkata"
MON = date(2026, 1, 5)  # a fixed Monday
TUE = date(2026, 1, 6)
NOW = datetime(2026, 1, 5, 0, 0)  # fixed Monday 00:00 (tenant TZ)

FUTURE_MONDAY = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 + 28)


def _at(hour: int, minute: int = 0, day: date = MON) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(KOLKATA))


def _t(value: str) -> dtime:
    hour, minute = map(int, value.split(":"))
    return dtime(hour, minute)


def _times(slots: list[datetime]) -> list[str]:
    return [slot.strftime("%H:%M") for slot in slots]


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(slug="dwyer", name="Dwyer LLP", timezone=KOLKATA)


@pytest.fixture
def provider(tenant: Tenant) -> Provider:
    return Provider.objects.unfiltered().create(tenant=tenant, name="Adv. Dwyer")


def _service(provider: Provider, *, duration: int = 30, buffer_after: int = 0) -> Service:
    from apps.services.models import Service as ServiceModel

    return ServiceModel.objects.unfiltered().create(
        tenant=provider.tenant,
        provider=provider,
        name=f"Service {duration}min",
        slug=f"svc-{duration}-{buffer_after}",
        duration_minutes=duration,
        buffer_after_minutes=buffer_after,
        price_amount="500.00",
    )


def _rule(provider: Provider, *, day: date = MON, start: str = "10:00", end: str = "13:00") -> Any:
    from apps.scheduling.models import AvailabilityRule

    return AvailabilityRule.objects.unfiltered().create(
        provider=provider,
        weekday=day.isoweekday() % 7,
        start_time=_t(start),
        end_time=_t(end),
    )


def _engine(provider: Provider, service: Service, **kwargs: Any) -> SlotService:
    kwargs.setdefault("now", NOW)
    return SlotService(provider=provider, service=service, **kwargs)


def _exceptions(provider: Provider, **kwargs: Any) -> Any:
    from apps.scheduling.models import AvailabilityException, ExceptionType

    return AvailabilityException.objects.unfiltered().create(
        provider=provider,
        type=kwargs.pop("type", ExceptionType.BLOCKED),
        **kwargs,
    )


# ------------------------------------------------------------------ grids
def test_prd_example_30_min_no_buffer_produces_10_to_12_30(provider: Provider) -> None:
    service = _service(provider, duration=30, buffer_after=0)
    _rule(provider, day=MON)

    assert _times(_engine(provider, service).slots(MON)) == [
        "10:00",
        "10:30",
        "11:00",
        "11:30",
        "12:00",
        "12:30",
    ]


def test_d4_45_min_plus_5_walks_anchored_not_30_min_steps(provider: Provider) -> None:
    service = _service(provider, duration=45, buffer_after=5)
    _rule(provider, day=MON)

    slots = _engine(provider, service).slots(MON)

    assert _times(slots) == ["10:00", "10:50", "11:40"]
    # A 30-minute booking at 10:45 is never offered (the grid has no :45 starts).
    assert "10:45" not in _times(slots)


def test_60_min_service_filters_out_the_12_30_start(provider: Provider) -> None:
    thirty = _service(provider, duration=30, buffer_after=0)
    sixty = _service(provider, duration=60, buffer_after=0)
    _rule(provider, day=MON)

    half_hour_grid = _times(_engine(provider, thirty).slots(MON))
    hour_grid = _times(_engine(provider, sixty).slots(MON))

    assert "12:30" in half_hour_grid
    assert "12:30" not in hour_grid
    assert hour_grid == ["10:00", "11:00", "12:00"]


def test_final_slot_survives_when_its_buffer_overruns_close(provider: Provider) -> None:
    service = _service(provider, duration=50, buffer_after=10)
    _rule(provider, day=MON, end="12:00")

    # 10:00 and 11:00 both fit their consultation (ends 10:50 / 11:50 <= 12:00);
    # the 11:00 buffer runs 11:50 -> 12:10, past close, and is not shaved off,
    # and no truncation turns it into a shorter "11:10" slot.
    assert _times(_engine(provider, service).slots(MON)) == ["10:00", "11:00"]


# ---------------------------------------------------------------- exceptions
def test_blocked_exception_splits_the_window(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    _exceptions(provider, date=MON, start_time=_t("10:00"), end_time=_t("11:00"))

    assert _times(_engine(provider, service).slots(MON)) == [
        "11:00",
        "11:30",
        "12:00",
        "12:30",
    ]


def test_override_replaces_the_weekday_rules(provider: Provider) -> None:
    from apps.scheduling.models import ExceptionType

    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    _exceptions(
        provider,
        date=MON,
        type=ExceptionType.OVERRIDE,
        start_time=_t("14:00"),
        end_time=_t("16:00"),
    )

    assert _times(_engine(provider, service).slots(MON)) == [
        "14:00",
        "14:30",
        "15:00",
        "15:30",
    ]


def test_full_day_blockout_removes_every_slot(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    _exceptions(provider, date=MON, start_time=_t("00:00"), end_time=_t("23:59"))

    assert _engine(provider, service).slots(MON) == []


# ---------------------------------------------------------------- busy spans
def test_busy_span_excludes_slots_it_overlaps(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    busy = [(_at(10, 15), _at(10, 45))]

    slots = _engine(provider, service, busy=busy).slots(MON)

    assert _times(slots) == ["11:00", "11:30", "12:00", "12:30"]


def test_busy_accepts_objects_with_start_at_end_at(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)

    class Span:
        start_at = _at(10, 0)
        end_at = _at(13, 0)

    slots = _engine(provider, service, busy=[Span()]).slots(MON)

    assert slots == []


# ---------------------------------------------------------- timezone + window
def test_slots_are_aware_and_in_the_tenant_timezone(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)

    first = _engine(provider, service).slots(MON)[0]

    offset = first.utcoffset()
    assert first.isoformat() == "2026-01-05T10:00:00+05:30"
    assert first.tzinfo is not None
    assert offset is not None
    assert offset.total_seconds() == 5 * 3600 + 30 * 60


def test_lead_time_hides_slots_before_now_plus_lead(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON, end="12:00")
    engine = _engine(
        provider,
        service,
        now=datetime(2026, 1, 5, 10, 30, tzinfo=ZoneInfo(KOLKATA)),
        lead_time=timedelta(minutes=15),
    )

    assert _times(engine.slots(MON)) == ["11:00", "11:30"]


def test_horizon_excludes_days_beyond_the_lookahead(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    engine = _engine(provider, service, horizon_days=0)

    assert engine.slots(MON) != []
    assert engine.slots(date(2026, 1, 12)) == []


def test_rule_effective_range_bounds_the_window(provider: Provider) -> None:
    from apps.scheduling.models import AvailabilityRule

    service = _service(provider, duration=30)
    _rule(provider, day=MON)
    AvailabilityRule.objects.unfiltered().filter(provider=provider).update(
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 1, 6),
    )

    assert _engine(provider, service).slots(MON) != []
    assert _engine(provider, service).slots(date(2026, 1, 12)) == []


# ---------------------------------------------------------------- validation
def test_rule_rejects_end_before_or_equal_to_start(provider: Provider) -> None:
    from django.core.exceptions import ValidationError

    from apps.scheduling.models import AvailabilityRule

    bad = AvailabilityRule(
        provider=provider,
        weekday=MON.isoweekday() % 7,
        start_time=_t("12:00"),
        end_time=_t("12:00"),
    )
    with tenant_context(provider.tenant), pytest.raises(ValidationError):
        bad.full_clean()


def test_overlapping_rules_for_same_weekday_rejected(provider: Provider) -> None:
    from django.core.exceptions import ValidationError

    from apps.scheduling.models import AvailabilityRule

    _rule(provider, day=MON, start="10:00", end="13:00")
    conflict = AvailabilityRule(
        provider=provider,
        weekday=MON.isoweekday() % 7,
        start_time=_t("12:00"),
        end_time=_t("14:00"),
    )
    with tenant_context(provider.tenant), pytest.raises(ValidationError):
        conflict.full_clean()


def test_same_window_on_different_weekdays_is_fine(provider: Provider) -> None:
    from apps.scheduling.models import AvailabilityRule

    _rule(provider, day=MON, start="10:00", end="13:00")
    other = AvailabilityRule(
        provider=provider,
        weekday=TUE.isoweekday() % 7,
        start_time=_t("10:00"),
        end_time=_t("13:00"),
    )
    with tenant_context(provider.tenant):
        other.full_clean()  # must not raise


def test_exception_rejects_end_before_or_equal_to_start(provider: Provider) -> None:
    from django.core.exceptions import ValidationError

    from apps.scheduling.models import AvailabilityException

    bad = AvailabilityException(
        provider=provider,
        date=MON,
        start_time=_t("09:00"),
        end_time=_t("09:00"),
    )
    with tenant_context(provider.tenant), pytest.raises(ValidationError):
        bad.full_clean()


# ---------------------------------------------------------------- isolation
def test_scheduling_managers_fail_closed_without_a_tenant(
    provider: Provider, tenant: Tenant
) -> None:
    from apps.scheduling.models import AvailabilityRule
    from common.exceptions import TenantContextMissing

    _rule(provider, day=MON)
    with pytest.raises(TenantContextMissing):
        AvailabilityRule.objects.all()


def test_provider_queries_are_tied_to_the_tenant(tenant: Tenant, provider: Provider) -> None:
    other = Tenant.objects.create(slug="mason", name="Mason & Co", timezone="UTC")
    Provider.objects.unfiltered().create(tenant=other, name="Adv. Mason")

    with tenant_context(tenant):
        assert list(Provider.objects.all()) == [provider]


# ------------------------------------------------------------------- cache
def test_cache_is_invalidated_when_a_rule_changes(provider: Provider) -> None:
    service = _service(provider, duration=30)
    _rule(provider, day=FUTURE_MONDAY, end="12:00")
    engine = SlotService(provider=provider, service=service)

    before = engine.slots(FUTURE_MONDAY)
    assert SlotService(provider=provider, service=service).slots(FUTURE_MONDAY) == before

    # A new rule saves through the ORM, firing post_save -> revision bump.
    _rule(provider, day=FUTURE_MONDAY, start="14:00", end="16:00")

    after = SlotService(provider=provider, service=service).slots(FUTURE_MONDAY)
    assert len(after) > len(before)
    assert after[-1] > before[-1]
