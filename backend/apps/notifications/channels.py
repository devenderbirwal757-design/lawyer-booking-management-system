"""Notification delivery channels (Phase 7 stubs + basic implementation)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import send_mail

from apps.notifications.models import Notification, NotificationTemplate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendResult:
    success: bool
    error: str = ""


class NotificationChannel(ABC):
    """Abstract delivery channel."""

    channel: NotificationTemplate.Channel

    @abstractmethod
    def send(self, notification: Notification, context: dict[str, Any]) -> SendResult:
        raise NotImplementedError


def _render_template(template: str, context: dict[str, Any]) -> str:
    """Simple {{key}} placeholder substitution.

    The plan calls for template rendering with correct placeholders; this is a
    minimal, explicit renderer (no Jinja dependency). It leaves unknown
    placeholders as-is to avoid silently mangling text.
    """
    if not template:
        return ""
    rendered = template
    for key, value in context.items():
        if value is None:
            continue
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


class EmailChannel(NotificationChannel):
    channel = NotificationTemplate.Channel.EMAIL

    def send(self, notification: Notification, context: dict[str, Any]) -> SendResult:
        try:
            subject = notification.subject or ""
            body = notification.body or ""
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[notification.to_email] if notification.to_email else [],
                fail_silently=True,
            )
            if sent == 0:
                return SendResult(success=False, error="send_mail returned 0")
            return SendResult(success=True)
        except Exception as exc:
            logger.exception("notification.email_failed", exc_info=exc)
            return SendResult(success=False, error=str(exc))


class SmsChannel(NotificationChannel):
    channel = NotificationTemplate.Channel.SMS

    def send(self, notification: Notification, context: dict[str, Any]) -> SendResult:
        # Stub implementation per Phase 7 requirements
        logger.info(
            "notification.sms_stub notification_id=%s to=%s",
            str(notification.pk),
            notification.to_phone,
        )
        return SendResult(success=True, error="")


class WhatsAppChannel(NotificationChannel):
    channel = NotificationTemplate.Channel.WHATSAPP

    def send(self, notification: Notification, context: dict[str, Any]) -> SendResult:
        logger.info(
            "notification.whatsapp_stub notification_id=%s to=%s",
            str(notification.pk),
            notification.to_phone,
        )
        return SendResult(success=True, error="")
