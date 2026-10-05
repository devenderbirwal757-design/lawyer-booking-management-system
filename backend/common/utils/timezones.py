from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.utils import timezone


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open [start, end) interval expressed in wall-clock time."""

    start: time
    end: time

    def contains(self, moment: time) -> bool:
        return self.start <= moment < self.end

    def overlaps(self, other: TimeWindow) -> bool:
        return self.start < other.end and other.start < self.end

    @property
    def duration(self) -> timedelta:
        start_dt = datetime.combine(date(2000, 1, 1), self.start)
        end_dt = datetime.combine(date(2000, 1, 1), self.end)
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return end_dt - start_dt


def tenant_tz(tenant: Any) -> ZoneInfo:
    """The one place a tenant's timezone name becomes a tzinfo (plan §12)."""
    return ZoneInfo(str(getattr(tenant, "timezone", None) or "UTC"))


def to_local(moment: datetime, tenant: Any) -> datetime:
    if timezone.is_naive(moment):
        raise ValueError("Naive datetimes are not accepted; store everything in UTC.")
    return moment.astimezone(tenant_tz(tenant))


def to_utc(local_moment: datetime, tenant: Any) -> datetime:
    if timezone.is_naive(local_moment):
        local_moment = local_moment.replace(tzinfo=tenant_tz(tenant))
    return local_moment.astimezone(ZoneInfo("UTC"))


def start_of_day_utc(day: date, tenant: Any) -> datetime:
    return to_utc(datetime.combine(day, time.min), tenant)


def end_of_day_utc(day: date, tenant: Any) -> datetime:
    return start_of_day_utc(day + timedelta(days=1), tenant)


def local_date(moment: datetime, tenant: Any) -> date:
    return to_local(moment, tenant).date()


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))
