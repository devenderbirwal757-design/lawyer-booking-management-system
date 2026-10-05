"""Notification service and task (Phase 7)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.notifications.channels import (
    EmailChannel,
    NotificationChannel,
    SmsChannel,
    WhatsAppChannel,
    _render_template,
)
from apps.notifications.models import Notification, NotificationTemplate


class InternalError(Exception):
    """Internal error for service failures."""

    pass


now = timezone.now

logger = logging.getLogger(__name__)

_CHANNELS: dict[str, NotificationChannel] = {
    NotificationTemplate.Channel.EMAIL: EmailChannel(),
    NotificationTemplate.Channel.SMS: SmsChannel(),
    NotificationTemplate.Channel.WHATSAPP: WhatsAppChannel(),
}


def _get_channel(channel: str) -> NotificationChannel:
    try:
        return _CHANNELS[channel]
    except KeyError as exc:
        logger.exception("notification.unknown_channel", exc_info=exc)
        raise InternalError("Unknown notification channel") from exc


def _resolve_template(
    tenant_id: Any,
    event: NotificationTemplate.Event,
    channel: NotificationTemplate.Channel,
) -> NotificationTemplate | None:
    return (
        NotificationTemplate.objects.filter(
            tenant_id=tenant_id,
            event=event,
            channel=channel,
            is_active=True,
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )


def create_notification(
    *,
    tenant_id: Any,
    event: NotificationTemplate.Event,
    channel: NotificationTemplate.Channel,
    to_email: str = "",
    to_phone: str = "",
    context: dict[str, Any] | None = None,
    appointment_id: Any = None,
    customer_id: Any = None,
) -> Notification:
    context = context or {}
    template = _resolve_template(tenant_id, event, channel)

    subject = ""
    body = ""
    if template:
        subject = _render_template(template.subject, context)
        body = _render_template(template.body, context)

    notification = Notification.objects.create(
        tenant_id=tenant_id,
        template=template,
        event=event,
        channel=channel,
        to_email=to_email,
        to_phone=to_phone,
        subject=subject,
        body=body,
        context=context,
        status=Notification.Status.PENDING,
        attempts=0,
        max_attempts=getattr(settings, "NOTIFICATION_MAX_ATTEMPTS", 3),
        appointment_id=appointment_id,
        customer_id=customer_id,
    )
    logger.info("notification.created %s", notification.pk)
    return notification


def _mark_sent(notification: Notification) -> None:
    notification.status = Notification.Status.SENT
    notification.sent_at = now()
    notification.error = ""
    notification.save(update_fields=("status", "sent_at", "error", "updated_at"))


def _mark_failed(notification: Notification, error: str) -> None:
    notification.attempts += 1
    notification.error = error[:5000]
    if notification.attempts >= notification.max_attempts:
        notification.status = Notification.Status.FAILED
    else:
        notification.status = Notification.Status.PENDING
    notification.save(update_fields=("attempts", "status", "error", "updated_at"))


def send_notification(notification: Notification, *, force: bool = False) -> None:
    if notification.status == Notification.Status.SENT and not force:
        return
    if notification.status == Notification.Status.CANCELLED and not force:
        return

    channel = _get_channel(notification.channel)
    result = channel.send(notification, notification.context or {})

    if result.success:
        _mark_sent(notification)
        logger.info("notification.sent %s", notification.pk)
        return

    _mark_failed(notification, result.error)
    logger.warning("notification.failed %s attempts=%s", notification.pk, notification.attempts)
