"""The payment state machine, declared once (plan §6.1, PRD §12).

    CREATED ----> PENDING ----+----> SUCCESS ----> REFUNDED
                             |
                             +----> FAILED
                             +----> EXPIRED
                             +----> CANCELLED

`PaymentOrder` and `Payment` share this table on purpose: they are two rows
describing one piece of money, and a schema that lets them disagree
(order `SUCCESS`, payment `FAILED`) is a schema that can confirm an appointment
against a payment that never landed. `Refund` has its own, much shorter table.

`SUCCESS` is terminal except for `REFUNDED`; `FAILED`, `EXPIRED` and `CANCELLED`
are terminal. Re-applying the same status is rejected too - a duplicate
`payment.captured` webhook is a replay to be absorbed at the event-dedupe layer,
not a second edge to walk.

Two edges that are not in the plan's table are allowed deliberately, because the
schema has a row that must be honest before a gateway ever sees it:

- `CREATED -> EXPIRED` and `CREATED -> CANCELLED` - the slot hold can lapse or
  the client can walk away before checkout starts, and leaving the order in
  `CREATED` forever would make the reconcile sweep re-check it hourly forever.

`CREATED -> SUCCESS` is *not* allowed. An order reaches `PENDING` only after the
gateway acknowledged it, so a capture against a `CREATED` order is an anomaly;
the webhook records it and returns 200 rather than confirming a booking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.payments.models import (
    PaymentOrderStatus,
    Refund,
    RefundStatus,
)
from common.exceptions import InvalidStateTransitionError

#: Legal edges for the order/payment vocabulary, one set per source status.
_PAYMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentOrderStatus.CREATED: frozenset(
        {
            PaymentOrderStatus.PENDING,
            PaymentOrderStatus.EXPIRED,
            PaymentOrderStatus.CANCELLED,
        }
    ),
    PaymentOrderStatus.PENDING: frozenset(
        {
            PaymentOrderStatus.SUCCESS,
            PaymentOrderStatus.FAILED,
            PaymentOrderStatus.EXPIRED,
            PaymentOrderStatus.CANCELLED,
        }
    ),
    PaymentOrderStatus.SUCCESS: frozenset({PaymentOrderStatus.REFUNDED}),
}

#: Legal edges for refunds (plan §6.2). `SETTLED` is written by the settle
#: action only; there is no gateway callback that could set it.
_REFUND_TRANSITIONS: dict[str, frozenset[str]] = {
    RefundStatus.PENDING_ACTION: frozenset(
        {RefundStatus.SETTLED, RefundStatus.FAILED, RefundStatus.CANCELLED}
    ),
}


def can_transition(current: str, target: str) -> bool:
    """True when `current -> target` is a legal edge."""
    if target == current:
        return False
    return target in _PAYMENT_TRANSITIONS.get(current, frozenset())


def can_transition_refund(current: str, target: str) -> bool:
    """True when `current -> target` is a legal refund edge."""
    if target == current:
        return False
    return target in _REFUND_TRANSITIONS.get(current, frozenset())


def _payment_update_fields(obj: Any, current: str, target: str, now: datetime) -> list[str]:
    fields = ["status", "updated_at"]
    if target == PaymentOrderStatus.SUCCESS:
        # `paid_at` is stamped here and nowhere else. No client call, no admin
        # call and no reconcile pass can move a payment to SUCCESS, so this is
        # the single place the "money landed at" time is written.
        if obj.paid_at is None:
            obj.paid_at = now
        fields.append("paid_at")
    reason = getattr(obj, "failure_reason", None)
    if reason is not None:
        fields.append("failure_reason")
    del current
    return fields


def _refund_update_fields(obj: Any, target: str, now: datetime) -> list[str]:
    fields = ["status", "updated_at"]
    if target == RefundStatus.SETTLED:
        obj.settled_at = now
        fields.append("settled_at")
    return fields


def transition(
    obj: Any,
    target: str,
    *,
    now: datetime,
    failure_reason: str = "",
    extra_fields: tuple[str, ...] = (),
) -> str:
    """Move a payment-ish row to `target`, returning the status it left.

    Handles `PaymentOrder`, `Payment` and `Refund`; which table applies is
    decided by the row type, so there is one enforcement point instead of three
    copies of "is this edge legal". Raises `InvalidStateTransitionError` (409,
    S §A8) for an edge that is not in the table.

    Callers must hold the row lock and an open transaction: "two webhooks do
    not both confirm" is a database fact, not a convenience.

    `extra_fields` names other fields the caller has already mutated and wants
    written by this save. It exists because the save is deliberately narrow -
    a blanket `save()` would write whatever happens to be dirty on an instance
    the caller has been mutating for other reasons - and a caller that forgets
    to list a field gets it silently dropped. `create_gateway_order` setting
    `gateway_order_id` and losing it here is the bug that shaped it.
    """
    if isinstance(obj, Refund):
        current = str(obj.status)
        if not can_transition_refund(current, target):
            raise InvalidStateTransitionError(
                detail=f"Cannot move refund from {current} to {target}."
            )
        obj.status = target
        update_fields = _refund_update_fields(obj, target, now)
    else:
        current = str(obj.status)
        if not can_transition(current, target):
            raise InvalidStateTransitionError(
                detail=f"Cannot move payment from {current} to {target}."
            )
        if failure_reason:
            obj.failure_reason = failure_reason[:255]
        obj.status = target
        update_fields = _payment_update_fields(obj, current, target, now)

    update_fields.extend(name for name in extra_fields if name not in update_fields)
    obj.save(update_fields=update_fields)
    return current


__all__ = (
    "can_transition",
    "can_transition_refund",
    "transition",
)
