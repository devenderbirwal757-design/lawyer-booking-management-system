from __future__ import annotations

from django.db import transaction

from config.celery import app as celery_app


@celery_app.task(
    name="appointments.expire_slot_holds",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def expire_slot_holds() -> int:
    """Beat sweep for lapsed slot holds (plan §5 layer 3).

    Runs inside a transaction so `select_for_update(skip_locked=True)` inside
    `expire_stale_holds` actually holds provider-scoped locks for the sweep;
    rows another worker already locked are skipped.
    """
    from apps.appointments import services

    with transaction.atomic():
        return services.expire_all_stale_holds()


__all__ = ("expire_slot_holds",)
