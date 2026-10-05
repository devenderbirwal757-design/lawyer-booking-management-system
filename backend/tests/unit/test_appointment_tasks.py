"""The hold sweep (plan §5 layer 3) - the task and its beat entry.

An unpaid hold is only a promise. `expire_slot_holds` is what turns the promise
into reality, so both halves are tested: the schedule actually fires, and the
sweep actually frees the slot.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentStatus
from apps.appointments.tasks import expire_slot_holds

pytestmark = pytest.mark.django_db


def test_beat_schedules_the_hold_sweep() -> None:
    """A task nothing schedules is a task that never runs."""
    entry = settings.CELERY_BEAT_SCHEDULE["expire-appointment-holds"]
    assert entry["task"] == "appointments.expire_slot_holds"
    # At least once per hold window, so a lapsed hold frees its slot on time.
    assert entry["schedule"]


def test_the_sweep_expires_a_lapsed_hold_and_frees_the_slot(
    booking_tenant: Any,
    booking_service: Any,
    booking_customer: Any,
) -> None:
    from tests.conftest import slot_at

    hold = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
        slot_hold_expires_at=timezone.now() - timedelta(minutes=1),
    )
    live = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(1),
        end_at=slot_at(1, 30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
        slot_hold_expires_at=timezone.now() + timedelta(minutes=10),
    )

    swept = expire_slot_holds()

    assert swept == 1
    hold.refresh_from_db()
    live.refresh_from_db()
    assert hold.status == AppointmentStatus.EXPIRED
    assert live.status == AppointmentStatus.PENDING_PAYMENT


def test_the_sweep_skips_appointments_that_are_not_holds(
    booking_tenant: Any,
    booking_service: Any,
    booking_customer: Any,
) -> None:
    """A confirmed booking whose start has passed is history, not a hold."""
    from tests.conftest import slot_at

    past = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
        slot_hold_expires_at=timezone.now() - timedelta(minutes=1),
    )

    assert expire_slot_holds() == 0
    past.refresh_from_db()
    assert past.status == AppointmentStatus.CONFIRMED
