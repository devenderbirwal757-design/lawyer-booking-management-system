"""Celery tasks for notifications (Phase 7)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.notifications.models import Notification
from apps.notifications.services import send_notification

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="notifications",
    retry_backoff=True,
    retry_jitter=True,
    max_retries=10,
    acks_late=True,
)
def send_notification_task(self: Any, notification_id: str) -> str:
    try:
        notification = Notification.objects.select_related("template").get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("notification.task_missing %s", notification_id)
        return "missing"

    if notification.status == Notification.Status.SENT:
        return "already_sent"
    if notification.status == Notification.Status.CANCELLED:
        return "cancelled"

    send_notification(notification)
    return notification.status


def enqueue_notification(notification: Notification) -> None:
    """Enqueue a notification to be sent after commit."""

    def _enqueue() -> None:
        send_notification_task.delay(str(notification.pk))

    transaction.on_commit(_enqueue)
