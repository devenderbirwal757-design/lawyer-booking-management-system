"""The appointment state machine, tested on its own (plan §5, PRD §8).

The unit under test is `can_transition`/`transition` *as a table*, with no HTTP
and no service layer. That keeps the interesting question - "which moves exist
at all?" - separate from "does the API perform them correctly?", so a failure
names the layer that broke.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.appointments.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    Appointment,
    AppointmentActor,
    AppointmentStatus,
)
from apps.appointments.state import can_transition, transition, write_initial_history
from common.exceptions import InvalidStateTransitionError

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

PENDING = AppointmentStatus.PENDING_PAYMENT
CONFIRMED = AppointmentStatus.CONFIRMED

ALL_STATUSES = tuple(AppointmentStatus.values)


@pytest.fixture
def real_appointment(
    booking_tenant: Any,
    booking_provider: Any,
    booking_service: Any,
    booking_customer: Any,
) -> Appointment:
    """A real `PENDING_PAYMENT` hold, built directly (no service layer)."""
    from datetime import timedelta

    from django.utils import timezone

    start = timezone.now() + timedelta(days=3)
    appointment = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_provider,
        customer=booking_customer,
        service=booking_service,
        start_at=start,
        end_at=start + timedelta(minutes=booking_service.duration_minutes),
        timezone=booking_tenant.timezone,
        status=PENDING,
    )
    # The booking service writes this opening leg; the trail starts here so
    # the tests exercise transitions the way the API produces them.
    write_initial_history(appointment, actor_type=AppointmentActor.CUSTOMER, actor_id="customer-1")
    return appointment


# ------------------------------------------------------------------- the table
def test_pending_payment_reaches_confirmed_cancelled_expired_and_rescheduled() -> None:
    for target in (
        CONFIRMED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.EXPIRED,
        AppointmentStatus.RESCHEDULED,
    ):
        assert can_transition(PENDING, target), f"PENDING_PAYMENT -> {target} must be legal"


def test_confirmed_reaches_completed_no_show_cancelled_and_rescheduled() -> None:
    for target in (
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.RESCHEDULED,
    ):
        assert can_transition(CONFIRMED, target), f"CONFIRMED -> {target} must be legal"


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_terminal_statuses_reach_nothing(status: str) -> None:
    for target in ALL_STATUSES:
        assert not can_transition(status, target), f"{status} -> {target} must be illegal"


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_no_status_may_reach_itself(status: str) -> None:
    """A double-tapped confirm is a client bug, not a hoisting signal."""
    assert not can_transition(status, status)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (PENDING, AppointmentStatus.COMPLETED),
        (PENDING, AppointmentStatus.NO_SHOW),
        (CONFIRMED, AppointmentStatus.EXPIRED),
        (AppointmentStatus.COMPLETED, CONFIRMED),
        (AppointmentStatus.CANCELLED, CONFIRMED),
    ],
)
def test_skipping_steps_is_illegal(current: str, target: str) -> None:
    assert not can_transition(current, target)


def test_every_status_is_either_active_or_terminal() -> None:
    assert set(ALL_STATUSES) == set(ACTIVE_STATUSES) | set(TERMINAL_STATUSES)
    assert not set(ACTIVE_STATUSES) & set(TERMINAL_STATUSES)


# ------------------------------------------------------------------- transition
def test_transition_writes_history_and_persists_the_new_status(
    real_appointment: Appointment,
) -> None:
    history = transition(
        real_appointment,
        CONFIRMED,
        actor_type=AppointmentActor.ADMIN,
        actor_id="admin-1",
        note="Payment captured.",
    )

    assert history.from_status == PENDING
    assert history.to_status == CONFIRMED
    assert history.actor_type == AppointmentActor.ADMIN
    assert history.actor_id == "admin-1"
    assert history.note == "Payment captured."

    real_appointment.refresh_from_db()
    assert real_appointment.status == CONFIRMED


def test_transition_refuses_an_illegal_move_and_leaves_the_row_alone(
    real_appointment: Appointment,
) -> None:
    with pytest.raises(InvalidStateTransitionError):
        transition(real_appointment, AppointmentStatus.COMPLETED)

    real_appointment.refresh_from_db()
    assert real_appointment.status == PENDING
    assert real_appointment.status_history.count() == 1


def test_initial_history_records_the_entry_point(real_appointment: Appointment) -> None:
    history = write_initial_history(
        real_appointment,
        actor_type=AppointmentActor.CUSTOMER,
        actor_id="customer-1",
    )
    assert history.from_status == ""
    assert history.to_status == PENDING


def test_history_keeps_every_leg_in_order(real_appointment: Appointment) -> None:
    transition(real_appointment, CONFIRMED)
    transition(real_appointment, AppointmentStatus.COMPLETED)

    legs = list(real_appointment.status_history.all())
    assert [(leg.from_status, leg.to_status) for leg in legs] == [
        ("", PENDING),
        (PENDING, CONFIRMED),
        (CONFIRMED, AppointmentStatus.COMPLETED),
    ]


def test_actor_defaults_to_system(real_appointment: Appointment) -> None:
    history = transition(real_appointment, CONFIRMED)
    assert history.actor_type == AppointmentActor.SYSTEM
    assert history.actor_id == ""
