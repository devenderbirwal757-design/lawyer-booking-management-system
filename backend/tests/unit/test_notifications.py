"""Notification rendering and delivery (plan §7).

Three things have to hold for a message to be useful, and each is a way this
can be quietly wrong:

1. The template renders. A placeholder that silently survives into the body is
   a customer-facing bug that no log line would catch, so the renderer's
   "leave unknown keys alone" behaviour is pinned rather than assumed.
2. Failure is retried, then given up on - never the reverse. A notification
   that is marked FAILED after one attempt looks handled while the customer
   silently received nothing.
3. A tenant's message never picks up another tenant's template.

Delivery itself is tested against two transports: the real `EmailChannel` on
the locmem backend (so the production code path runs), and `RecordingChannel`
injected at the `_CHANNELS` seam (the only way to make a send *fail* on demand).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from apps.notifications import services
from apps.notifications.channels import _render_template
from apps.notifications.models import Notification, NotificationTemplate
from apps.notifications.services import (
    InternalError,
    create_notification,
    send_notification,
)
from apps.notifications.tasks import send_notification_task
from common.querysets import tenant_context
from tests.factories.notifications import RecordingChannel

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

EVENT = NotificationTemplate.Event.BOOKING_CONFIRMED
EMAIL = NotificationTemplate.Channel.EMAIL
SMS = NotificationTemplate.Channel.SMS


@pytest.fixture
def recording_channel(monkeypatch: Any) -> RecordingChannel:
    """Replace the EMAIL transport; everything else in the service is real."""
    channel = RecordingChannel()
    monkeypatch.setitem(services._CHANNELS, EMAIL, channel)
    return channel


@pytest.fixture
def make_template(booking_tenant: Any) -> Any:
    def _make(
        *,
        tenant: Any = None,
        event: str = EVENT,
        channel: str = EMAIL,
        subject: str = "",
        body: str = "",
        is_active: bool = True,
    ) -> NotificationTemplate:
        return NotificationTemplate.objects.create(
            tenant=tenant or booking_tenant,
            event=event,
            channel=channel,
            subject=subject,
            body=body,
            is_active=is_active,
        )

    return _make


@pytest.fixture
def notify(booking_tenant: Any) -> Any:
    """Create a notification the way the booking flows do.

    `create_notification` reads the template table, which is tenant-scoped, so
    the tenant has to be bound exactly as it is during a request.
    """

    def _notify(
        *,
        event: str = EVENT,
        channel: str = EMAIL,
        context: dict[str, Any] | None = None,
        to_email: str = "priya@example.com",
        to_phone: str = "+919876543210",
    ) -> Notification:
        with tenant_context(booking_tenant):
            return create_notification(
                tenant_id=booking_tenant.pk,
                event=event,
                channel=channel,
                to_email=to_email,
                to_phone=to_phone,
                context=context,
            )

    return _notify


# --------------------------------------------------------------- rendering


def test_placeholders_in_the_subject_and_body_are_substituted(
    make_template: Any,
    notify: Any,
) -> None:
    make_template(
        subject="Your {{service}} is booked for {{date}}",
        body="Hi {{name}}, your {{service}} on {{date}} is confirmed.",
    )

    notification = notify(
        context={
            "service": "Consultation",
            "date": "2026-11-02",
            "name": "Priya",
        }
    )

    assert notification.subject == "Your Consultation is booked for 2026-11-02"
    assert notification.body == "Hi Priya, your Consultation on 2026-11-02 is confirmed."


def test_a_placeholder_repeated_in_one_body_is_replaced_everywhere() -> None:
    rendered = _render_template(
        "{{name}} - ref {{ref}} for {{name}}", {"name": "Priya", "ref": "7"}
    )
    assert rendered == "Priya - ref 7 for Priya"


def test_an_unknown_placeholder_is_left_intact() -> None:
    """Deliberate: rendering must not silently delete text it cannot fill.

    A stripped `{{name}}` ships "Hi ," to a customer with no trace of why. An
    intact placeholder at least shows up in a manual review.
    """
    rendered = _render_template("Hi {{name}}, ref {{unknown}}.", {"name": "Priya"})
    assert rendered == "Hi Priya, ref {{unknown}}."


def test_a_none_valued_placeholder_is_left_intact() -> None:
    """A null context value is 'not known', not 'empty' - don't erase the token."""
    assert _render_template("Hi {{name}}", {"name": None}) == "Hi {{name}}"


def test_non_string_values_are_stringified() -> None:
    """Money and dates arrive as `Decimal`/`date` and must not raise."""
    rendered = _render_template(
        "Pay {{amount}} on {{day}}",
        {"amount": Decimal("500.00"), "day": date(2026, 11, 2)},
    )
    assert rendered == "Pay 500.00 on 2026-11-02"


def test_a_blank_template_renders_to_a_blank_string() -> None:
    assert _render_template("", {"name": "Priya"}) == ""


def test_a_notification_with_no_template_is_created_empty(notify: Any) -> None:
    """No template is not an error - but the message will have nothing in it.

    Pinned because the empty body is a real customer-visible outcome that a
    missing seed migration would otherwise hide.
    """
    notification = notify(context={"name": "Priya"})

    assert notification.template is None
    assert notification.subject == ""
    assert notification.body == ""
    assert notification.status == Notification.Status.PENDING


def test_an_inactive_template_is_ignored(make_template: Any, notify: Any) -> None:
    """`is_active=False` is how a tenant switches a message off."""
    make_template(subject="On {{service}}", body="Body", is_active=False)

    notification = notify(context={"service": "Consultation"})

    assert notification.template is None
    assert notification.subject == ""


def test_another_tenants_template_is_never_borrowed(booking_tenant: Any, notify: Any) -> None:
    """The isolation guarantee, on the one path that reads templates by hand.

    `create_notification` filters by `tenant_id` explicitly rather than relying
    on request context, so a matching event on another tenant must be invisible.
    """
    from apps.tenants.models import Tenant

    other = Tenant.objects.create(
        slug="okafor",
        name="Okafor & Co",
        timezone=booking_tenant.timezone,
    )
    NotificationTemplate.objects.create(
        tenant=other,
        event=EVENT,
        channel=EMAIL,
        subject="OTHER TENANT",
        body="Should never be read.",
    )

    notification = notify(context={"name": "Priya"})

    assert notification.template is None
    assert notification.body == ""


def test_the_attempt_budget_comes_from_settings(
    make_template: Any,
    notify: Any,
    settings: Any,
) -> None:
    """Max attempts is configuration, so it must be read at create time."""
    make_template(body="Body")
    default = notify()
    assert default.max_attempts == 3  # the getattr fallback

    settings.NOTIFICATION_MAX_ATTEMPTS = 7
    assert notify().max_attempts == 7


# --------------------------------------------------------------- delivery


def test_a_successful_send_is_marked_sent_and_stamped(make_template: Any, notify: Any) -> None:
    make_template(body="Body")
    notification = notify()

    send_notification(notification)

    notification.refresh_from_db()
    assert notification.status == Notification.Status.SENT
    assert notification.sent_at is not None
    assert notification.error == ""


def test_the_recording_channel_receives_the_notification_context(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """The stored context travels to the transport - that is the whole contract."""
    make_template(body="Body")
    notification = notify(context={"name": "Priya"})

    send_notification(notification)

    assert recording_channel.call_count == 1
    _, context = recording_channel.attempts[0]
    assert context == {"name": "Priya"}


def test_a_failure_stays_pending_and_keeps_its_attempt_budget(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """One bad attempt must not look like a dead notification."""
    make_template(body="Body")
    notification = notify()
    recording_channel.fail_with("smtp timeout")

    send_notification(notification)

    notification.refresh_from_db()
    assert notification.status == Notification.Status.PENDING
    assert notification.attempts == 1
    assert notification.error == "smtp timeout"
    assert notification.sent_at is None


def test_it_is_marked_failed_only_once_the_attempts_run_out(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """Three attempts, then FAILED. Failing early would be unrecoverable."""
    make_template(body="Body")
    notification = notify()
    recording_channel.fail_with("smtp timeout")

    for expected_attempts in (1, 2):
        send_notification(notification)
        notification.refresh_from_db()
        assert notification.status == Notification.Status.PENDING
        assert notification.attempts == expected_attempts

    send_notification(notification)
    notification.refresh_from_db()
    assert notification.status == Notification.Status.FAILED
    assert notification.attempts == 3
    assert recording_channel.call_count == 3


def test_a_recovered_send_is_marked_sent_and_clears_the_error(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """The reason this app retries instead of failing once."""
    make_template(body="Body")
    notification = notify()
    recording_channel.fail_with("smtp timeout")
    send_notification(notification)

    recording_channel.succeed()
    send_notification(notification)

    notification.refresh_from_db()
    assert notification.status == Notification.Status.SENT
    assert notification.error == ""
    assert notification.attempts == 1  # failures are not forgotten, just superseded


def test_an_absurdly_long_failure_reason_is_truncated(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """`error` is unbounded text; the column is not."""
    make_template(body="Body")
    notification = notify()
    recording_channel.fail_with("x" * 9000)

    send_notification(notification)

    notification.refresh_from_db()
    assert len(notification.error) == 5000


def test_an_already_sent_notification_is_not_delivered_twice(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """At-least-once delivery is the goal; double-charging a customer is not."""
    make_template(body="Body")
    notification = notify()
    send_notification(notification)

    send_notification(notification)

    assert recording_channel.call_count == 1


def test_a_cancelled_notification_is_never_delivered(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """The customer withdrew; the confirmation must not still go out."""
    make_template(body="Body")
    notification = notify()
    notification.status = Notification.Status.CANCELLED
    notification.save(update_fields=("status", "updated_at"))

    send_notification(notification)

    assert recording_channel.call_count == 0
    notification.refresh_from_db()
    assert notification.status == Notification.Status.CANCELLED


def test_force_redelivers_an_already_sent_notification(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """The escape hatch for a message that went out but was not received."""
    make_template(body="Body")
    notification = notify()
    send_notification(notification)

    send_notification(notification, force=True)

    assert recording_channel.call_count == 2


def test_an_unrecognised_channel_is_refused(notify: Any) -> None:
    """No template and no transport: refuse loudly rather than drop the message."""
    notification = notify(channel="SMS")
    notification.channel = "CARRIER_PIGEON"
    notification.save(update_fields=("channel", "updated_at"))

    with pytest.raises(InternalError):
        send_notification(notification)


# ------------------------------------------------------ the email channel


def test_the_email_channel_delivers_subject_body_and_recipient(
    make_template: Any,
    notify: Any,
    mailoutbox: Any,
) -> None:
    """The real channel on the locmem backend - no double in the path."""
    make_template(subject="Confirmed: {{service}}", body="Hi {{name}}, see you.")
    notification = notify(context={"service": "Consultation", "name": "Priya"})

    send_notification(notification)

    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.subject == "Confirmed: Consultation"
    assert "Hi Priya, see you." in message.body
    assert message.to == ["priya@example.com"]


def test_a_message_with_no_recipient_fails_instead_of_reporting_success(
    make_template: Any,
    notify: Any,
    mailoutbox: Any,
) -> None:
    """`send_mail` reports 0 delivered for nobody.

    Treating that as a success would mark the row SENT with `sent_at` set and
    nothing ever delivered - the one outcome worse than a visible failure.
    """
    make_template(body="Body")
    notification = notify(to_email="")

    send_notification(notification)

    notification.refresh_from_db()
    assert notification.status == Notification.Status.PENDING
    assert notification.attempts == 1
    assert notification.sent_at is None
    assert "send_mail returned 0" in notification.error
    assert len(mailoutbox) == 0


# ------------------------------------------------------------- the task


def test_the_task_delivers_a_pending_notification(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """A worker has no request and therefore no tenant context.

    The task looks the row up by primary key, so it must not go through the
    request-scoped manager - `TenantContextMissing` here is a crash in the
    worker, and this is the test that says so.
    """
    make_template(body="Body")
    notification = notify()

    assert send_notification_task(str(notification.pk)) == Notification.Status.SENT

    notification.refresh_from_db()
    assert notification.status == Notification.Status.SENT
    assert recording_channel.call_count == 1


def test_the_task_reports_a_missing_notification(notify: Any) -> None:
    """A row deleted between enqueue and delivery is not a worker crash."""
    assert send_notification_task(str(uuid.uuid4())) == "missing"


def test_the_task_skips_a_notification_that_is_already_sent(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    """Celery redelivers on `acks_late`; the second delivery must be a no-op."""
    make_template(body="Body")
    notification = notify()
    send_notification(notification)

    assert send_notification_task(str(notification.pk)) == "already_sent"
    assert recording_channel.call_count == 1


def test_the_task_skips_a_cancelled_notification(
    make_template: Any,
    notify: Any,
    recording_channel: RecordingChannel,
) -> None:
    make_template(body="Body")
    notification = notify()
    notification.status = Notification.Status.CANCELLED
    notification.save(update_fields=("status", "updated_at"))

    assert send_notification_task(str(notification.pk)) == "cancelled"
    assert recording_channel.call_count == 0
