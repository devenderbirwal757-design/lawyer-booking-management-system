"""Notification dispatch is deferred to commit (plan §7).

`enqueue_notification` wraps `.delay()` in `transaction.on_commit`, and that one
line is the difference between "the customer was told" and "the customer was
told about an appointment that does not exist".

The failure it guards against is quiet. If the send were enqueued eagerly, a
booking that failed payment verification a few statements later would still
produce a "your appointment is confirmed" email, and nothing in the logs would
distinguish that from a real one. The row would be rolled back; the message
would not.

So these tests assert the negative: after a rollback, nothing is enqueued and
nothing exists to enqueue. They use `transaction=True` because the guarantee
being tested is about real commit and real rollback - under the default
transactional wrapper the outer atomic never commits, so the positive case
could not be distinguished from a bug.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import transaction

from apps.notifications import tasks as notification_tasks
from apps.notifications.models import Notification, NotificationTemplate
from apps.notifications.services import create_notification
from common.querysets import tenant_context
from tests.factories.notifications import RecordingTask

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

EVENT = NotificationTemplate.Event.BOOKING_CONFIRMED
SMS = NotificationTemplate.Channel.SMS


@pytest.fixture
def recording_task(monkeypatch: Any) -> RecordingTask:
    """Capture `.delay()` calls instead of reaching a broker."""
    task = RecordingTask()
    monkeypatch.setattr(notification_tasks, "send_notification_task", task)
    return task


@pytest.fixture
def make_pending(booking_tenant: Any) -> Any:
    """Create a notification inside tenant context, as a request would.

    The body comes from a template, the same way the booking flows produce it -
    what is under test here is *when* the send is enqueued, so the message
    itself only has to be a realistic one.
    """

    def _make() -> Notification:
        with tenant_context(booking_tenant):
            return create_notification(
                tenant_id=booking_tenant.pk,
                event=EVENT,
                channel=SMS,
                to_phone="+919876543210",
                context={"service": "Consultation"},
            )

    NotificationTemplate.objects.create(
        tenant=booking_tenant,
        event=EVENT,
        channel=SMS,
        body="Your {{service}} appointment is confirmed.",
    )
    return _make


def test_a_rolled_back_transaction_never_enqueues_the_send(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """The headline guarantee: no commit, no send."""
    with pytest.raises(RuntimeError), transaction.atomic():
        notification = make_pending()
        notification_tasks.enqueue_notification(notification)
        raise RuntimeError("payment verification failed; booking rolled back")

    assert recording_task.enqueued == []


def test_a_rollback_leaves_no_row_behind_to_send_later(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """Both halves matter: the row and the send must disappear together.

    Asserting only on the enqueue would still pass if the row survived and a
    later sweep picked it up.
    """
    with pytest.raises(RuntimeError), transaction.atomic():
        notification = make_pending()
        notification_tasks.enqueue_notification(notification)
        pk = notification.pk
        raise RuntimeError("rolled back")

    assert not Notification.objects.unfiltered().filter(pk=pk).exists()
    assert recording_task.enqueued == []


def test_a_committed_transaction_enqueues_the_send_exactly_once(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """The other half: the guarantee must not degrade into never sending."""
    with transaction.atomic():
        notification = make_pending()
        notification_tasks.enqueue_notification(notification)

    assert recording_task.enqueued == [str(notification.pk)]


def test_an_inner_savepoint_rollback_also_discards_the_send(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """A nested failure unwinds to the savepoint without committing.

    Booking flows wrap individual steps in `atomic()`, so this is the shape a
    real partial failure takes - not the outermost rollback above.
    """
    with transaction.atomic():
        notification = make_pending()
        notification_tasks.enqueue_notification(notification)
        with pytest.raises(RuntimeError), transaction.atomic():
            raise RuntimeError("step three failed")

    assert recording_task.enqueued == [str(notification.pk)]


def test_several_notifications_commit_together(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """A confirmation and a payment notice go out on the same commit."""
    with transaction.atomic():
        first = make_pending()
        second = make_pending()
        notification_tasks.enqueue_notification(first)
        notification_tasks.enqueue_notification(second)

    assert recording_task.enqueued == [str(first.pk), str(second.pk)]


def test_a_rollback_discards_every_enqueue_in_the_block(
    make_pending: Any,
    recording_task: RecordingTask,
) -> None:
    """Not just the last one - a partial fan-out is the worst case."""
    with pytest.raises(RuntimeError), transaction.atomic():
        notification_tasks.enqueue_notification(make_pending())
        notification_tasks.enqueue_notification(make_pending())
        raise RuntimeError("rolled back")

    assert recording_task.enqueued == []
