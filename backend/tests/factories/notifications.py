"""A `NotificationChannel` test double (plan §7).

Same shape as `tests/factories/gateway.py`: real call recording and an explicit
failure switch, so a test asserts on what was delivered rather than on how many
times a mock was called. The `EmailChannel` in production is exercised directly
against the locmem backend elsewhere - this double exists for the cases where
delivery must be *made* to fail, which the real channel cannot be talked into on
demand.
"""

from __future__ import annotations

from typing import Any

from apps.notifications.channels import NotificationChannel, SendResult
from apps.notifications.models import Notification, NotificationTemplate


class RecordingChannel(NotificationChannel):
    """Records every send attempt and fails on demand.

    Injected by replacing the matching entry in `services._CHANNELS`, so
    `send_notification` keeps its real lookup, retry and bookkeeping logic and
    only the transport is replaced.
    """

    channel = NotificationTemplate.Channel.EMAIL

    def __init__(self, *, fails_with: str = "") -> None:
        self.fails_with = fails_with
        self.attempts: list[tuple[Notification, dict[str, Any]]] = []

    def send(self, notification: Notification, context: dict[str, Any]) -> SendResult:
        self.attempts.append((notification, context))
        if self.fails_with:
            return SendResult(success=False, error=self.fails_with)
        return SendResult(success=True)

    def fail_with(self, error: str) -> None:
        """Make every subsequent send fail with `error`."""
        self.fails_with = error

    def succeed(self) -> None:
        """Stop failing; the next send is delivered."""
        self.fails_with = ""

    @property
    def call_count(self) -> int:
        return len(self.attempts)

    @property
    def last_body(self) -> str:
        return self.attempts[-1][0].body


class RecordingTask:
    """Stand-in for `send_notification_task`, recording `.delay()` enqueues."""

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def delay(self, notification_id: str) -> None:
        self.enqueued.append(notification_id)


__all__ = ("RecordingChannel", "RecordingTask")
