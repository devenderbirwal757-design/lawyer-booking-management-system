"""The appointment state machine, declared once (plan §5, PRD §8).

Every legal move and a single `transition()` that enforces it. The service
layer wraps calls in a transaction and locks the row (`select_for_update`),
because "no two writes race to COMPLETED" is a database fact, not a
convenience - the same claim the exclusion constraint makes for slots.

The table:

    PENDING_PAYMENT -> CONFIRMED   (only via a captured payment, Phase 6)
    PENDING_PAYMENT -> CANCELLED   (client abandons / admin cancels)
    PENDING_PAYMENT -> EXPIRED     (hold swept, plan §5 layer 3)
    PENDING_PAYMENT -> RESCHEDULED (customer/admin moves the hold)
    CONFIRMED        -> COMPLETED  (admin)
    CONFIRMED        -> NO_SHOW    (admin)
    CONFIRMED        -> CANCELLED  (cancellation; reason required)
    CONFIRMED        -> RESCHEDULED

Everything else is terminal: `COMPLETED`, `CANCELLED`, `NO_SHOW`,
`RESCHEDULED`, `EXPIRED` accept no further edges, and applying the same
status twice is rejected too (a double-tapped confirm is a client bug, not a
hoisting signal).
"""

from __future__ import annotations

from apps.appointments.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    Appointment,
    AppointmentActor,
    AppointmentStatus,
    AppointmentStatusHistory,
)
from apps.scheduling.service import bump_provider_revision
from common.exceptions import InvalidStateTransitionError

#: Legal edges, one set per source status. Terminal statuses have no key.
_TRANSITIONS: dict[str, frozenset[str]] = {
    AppointmentStatus.PENDING_PAYMENT: frozenset(
        {
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.EXPIRED,
            AppointmentStatus.RESCHEDULED,
        }
    ),
    AppointmentStatus.CONFIRMED: frozenset(
        {
            AppointmentStatus.COMPLETED,
            AppointmentStatus.CANCELLED,
            AppointmentStatus.NO_SHOW,
            AppointmentStatus.RESCHEDULED,
        }
    ),
}


def can_transition(current: str, target: str) -> bool:
    """True when `current -> target` is a legal edge."""
    if target == current:
        return False
    edges = _TRANSITIONS.get(current)
    return edges is not None and target in edges


def write_initial_history(
    appointment: Appointment,
    *,
    actor_type: str = AppointmentActor.SYSTEM,
    actor_id: str = "",
    note: str = "",
) -> AppointmentStatusHistory:
    """Record the terminal edge into the *current* status on creation."""
    return AppointmentStatusHistory.objects.create(
        appointment=appointment,
        from_status="",
        to_status=appointment.status,
        actor_type=actor_type,
        actor_id=actor_id,
        note=note,
    )


def transition(
    appointment: Appointment,
    target: str,
    *,
    actor_type: str = AppointmentActor.SYSTEM,
    actor_id: str = "",
    note: str = "",
) -> AppointmentStatusHistory:
    """Move `appointment` to `target`, writing a status-history leg.

    Raises `InvalidStateTransitionError` (409, S §A8) when the edge is not in
    the table. `appointment` is mutated in place (`status` updated and saved);
    callers must hold the row lock and an open transaction.
    """
    current = str(appointment.status)
    if not can_transition(current, target):
        raise InvalidStateTransitionError(
            detail=f"Cannot move appointment from {current} to {target}."
        )

    appointment.status = target
    appointment.save(update_fields=["status", "updated_at"])
    history = AppointmentStatusHistory.objects.create(
        appointment=appointment,
        from_status=current,
        to_status=target,
        actor_type=actor_type,
        actor_id=actor_id,
        note=note,
    )
    # A status change alters what occupies the calendar: drop every cached
    # slot grid for this provider so availability reflects the transition.
    bump_provider_revision(appointment.provider_id)
    return history


__all__ = (
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "can_transition",
    "transition",
    "write_initial_history",
)
