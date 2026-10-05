from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from common.utils.timezones import (
    TimeWindow,
    add_months,
    end_of_day_utc,
    local_date,
    start_of_day_utc,
    tenant_tz,
    to_local,
    to_utc,
)

pytestmark = pytest.mark.unit

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


class FakeTenant:
    def __init__(self, tz: str = "Asia/Kolkata") -> None:
        self.timezone = tz


def test_tenant_tz_falls_back_to_utc() -> None:
    assert tenant_tz(FakeTenant("Asia/Kolkata")) == IST
    assert tenant_tz(FakeTenant("")) == UTC


def test_utc_storage_and_local_rendering() -> None:
    """Everything is stored in UTC and rendered in the tenant's timezone."""
    tenant = FakeTenant()
    stored = datetime(2026, 10, 15, 5, 30, tzinfo=UTC)  # 11:00 IST

    assert to_local(stored, tenant).hour == 11
    assert local_date(stored, tenant) == date(2026, 10, 15)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Naive"):
        to_local(datetime(2026, 10, 15, 11, 0), FakeTenant())


def test_to_utc_assumes_tenant_local_time() -> None:
    local = datetime(2026, 10, 15, 11, 0)

    assert to_utc(local, FakeTenant()) == datetime(2026, 10, 15, 5, 30, tzinfo=UTC)


def test_day_boundaries_in_tenant_tz() -> None:
    tenant = FakeTenant()

    start = start_of_day_utc(date(2026, 10, 15), tenant)
    end = end_of_day_utc(date(2026, 10, 15), tenant)

    assert start == datetime(2026, 10, 14, 18, 30, tzinfo=UTC)
    assert end - start == timedelta(days=1)


def test_time_window_is_half_open() -> None:
    window = TimeWindow(start=time(10, 0), end=time(13, 0))

    assert window.contains(time(10, 0)) is True
    assert window.contains(time(12, 59, 59)) is True
    assert window.contains(time(13, 0)) is False
    assert window.duration == timedelta(hours=3)


def test_time_window_overlap() -> None:
    window = TimeWindow(start=time(10, 0), end=time(13, 0))

    assert window.overlaps(TimeWindow(start=time(12, 0), end=time(14, 0))) is True
    assert window.overlaps(TimeWindow(start=time(13, 0), end=time(14, 0))) is False


def test_time_window_across_midnight() -> None:
    window = TimeWindow(start=time(23, 0), end=time(1, 0))

    assert window.duration == timedelta(hours=2)


def test_add_months_clamps_to_month_length() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)


def test_stored_instants_are_utc() -> None:
    """The project runs with USE_TZ, so now() is always tz-aware UTC."""
    assert timezone.is_aware(timezone.now())
