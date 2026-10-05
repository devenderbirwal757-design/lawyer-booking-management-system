"""Payment Celery tasks (plan §6).

One task, `reconcile_pending_payments`, scheduled hourly. It is the safety net
under the webhook: a delivery the gateway could not make (a network partition at
their end, a misconfigured endpoint) would otherwise leave an order `PENDING`
and an appointment holding a slot until the hold sweep closes it with the wrong
verdict.

The task only ever moves an order to `SUCCESS` when `fetch_order` says `paid`
*and* a captured payment can be read back. An order that reads paid with no
payment id behind it is left alone and logged - that combination is either a
gateway bug or a replayed order number, and neither is grounds for confirming
a booking.
"""

from __future__ import annotations

import structlog
from celery import shared_task

from apps.payments import services

logger: structlog.stdlib.BoundLogger = structlog.get_logger("payments.tasks")


@shared_task(name="payments.reconcile_pending_payments")
def reconcile_pending_payments() -> dict[str, int]:
    """Compare open orders older than the threshold against the gateway."""
    return services.reconcile_pending_payments()


__all__ = ("reconcile_pending_payments",)
