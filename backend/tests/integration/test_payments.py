"""Phase 6 payments: the webhook is the only door (plan §6, PRD §11-12, S §A5).

Every claim here is an attack that a payment backend is expected to lose:

- an unsigned or tampered delivery changes nothing and returns 400;
- a valid delivery confirms the booking, and the *same* delivery three times
  still confirms it once;
- a client that asserts "I paid" gets nowhere, because no route accepts a
  status - asserted by walking the URLconf, not by trusting this comment;
- a ₹1 amount from the client is rejected, and the charged amount is compared
  against the server-side price before anything is confirmed;
- a capture that arrives after the hold expired records the money but does not
  resurrect the appointment;
- a test-mode capture cannot confirm a live booking, and the reverse;
- a refund needs two separate human actions, and neither can be replayed.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.urls import get_resolver

from apps.appointments.models import (
    AppointmentActor,
    AppointmentStatus,
    AppointmentStatusHistory,
)
from apps.audit.models import AuditLog
from apps.payments.models import (
    Payment,
    PaymentEvent,
    PaymentEventOutcome,
    PaymentOrder,
    PaymentOrderStatus,
    Refund,
    RefundStatus,
)
from apps.payments.serializers import (
    CreateOrderSerializer,
    PaymentEventSerializer,
    PaymentOrderSerializer,
    PaymentSerializer,
    RefundSerializer,
)
from common.exceptions import InvalidStateTransitionError
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

WEBHOOK = "/api/v1/payments/webhook"
CREATE_ORDER = "/api/v1/payments/create-order/"
ADMIN_PAYMENTS = "/api/v1/admin/payments/"
ADMIN_REFUNDS = "/api/v1/admin/refunds/"


def _captured_body(
    *,
    event_id: str,
    gateway_order_id: str,
    payment_id: str = "pay_test_1",
    amount_minor: int = 50000,
    method: str = "upi",
) -> bytes:
    """A byte-exact `payment.captured` body, as a gateway would send it.

    Key order and spacing are fixed here on purpose: the signature covers the
    raw bytes, so a test that rebuilt this through `json.dumps` with different
    formatting would be testing a different delivery.
    """
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_test",
            "event": "payment.captured",
            "contains": ["payment"],
            "id": event_id,
            "payload": {
                "entity": "payment",
                "amount": amount_minor,
                "currency": "INR",
                "method": method,
                "order_id": gateway_order_id,
                "payment": {"entity": "payment", "id": payment_id, "method": method},
            },
        }
    ).encode()


def _deliver(
    client: Any,
    fake_gateway: Any,
    body: bytes,
    *,
    event_type: str = "payment.captured",
    sign: bool = True,
) -> Any:
    headers = {"HTTP_X_RAZORPAY_EVENT": event_type}
    if sign:
        headers["HTTP_X_RAZORPAY_SIGNATURE"] = fake_gateway.sign(body)
    return client.post(WEBHOOK, data=body, content_type="application/json", **headers)


def _start_checkout(
    customer_client: Any,
    tenant: Any,
    appointment: Any,
    fake_gateway: Any,
    **extra: Any,
) -> Any:
    payload: dict[str, Any] = {"appointment_id": str(appointment.pk)}
    payload.update(extra)
    with tenant_context(tenant):
        return customer_client.post(CREATE_ORDER, payload, format="json")


# ------------------------------------------------------------------- checkout
def test_create_order_pushes_to_the_gateway_and_returns_the_public_key(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    response = _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)

    assert response.status_code == 201, response.data
    assert response.data["gateway_order_id"] == "order_test_1"
    assert response.data["amount"] == "500.00"
    # The publishable key id is what the client needs; the secret is not here
    # and must never be (S §A5).
    assert response.data["gateway_key_id"] == "rzp_test_key"
    assert "key_secret" not in json.dumps(response.data)
    assert "webhook_secret" not in json.dumps(response.data)
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.PENDING
    assert order.gateway_mode == "test"
    assert fake_gateway.created == [Decimal("500.00")]


def test_create_order_rejects_a_client_supplied_amount(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A ₹1 checkout for a ₹500 service is refused, not silently ignored.

    Ignoring it would leave the client believing the ₹1 is what will be
    charged, and the practice undercharging without anyone noticing.
    """
    appointment, _order = paid_hold
    response = _start_checkout(
        customer_client, booking_tenant, appointment, fake_gateway, amount="1.00"
    )

    assert response.status_code == 409
    assert response.data["error"]["code"] == "amount_mismatch"
    assert fake_gateway.created == []
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    assert order.status == PaymentOrderStatus.CREATED


def test_create_order_for_someone_elses_appointment_is_404(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    _appointment, order = paid_hold
    with tenant_context(booking_tenant):
        response = customer_client.post(
            CREATE_ORDER, {"appointment_id": str(order.appointment_id)}, format="json"
        )
    assert response.status_code == 201  # own appointment, sanity check

    from apps.customers.models import Customer

    other = Customer.objects.unfiltered().create(tenant=booking_tenant, phone="+919999999999")
    from rest_framework.test import APIClient

    from apps.auth_otp.tokens import issue_customer_token_pair

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_customer_token_pair(other)['access']}")
    with tenant_context(booking_tenant):
        response = client.post(
            CREATE_ORDER, {"appointment_id": str(order.appointment_id)}, format="json"
        )
    assert response.status_code == 404


def test_create_order_is_idempotent_per_hold(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A double-tapped "Pay" must not mint a second payable order.

    Razorpay's create_order is not idempotent, so a second call would leave the
    customer able to pay either order and the practice collecting twice.
    """
    appointment, _order = paid_hold
    first = _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    second = _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["gateway_order_id"] == second.data["gateway_order_id"]
    assert len(fake_gateway.created) == 1


# -------------------------------------------------------------------- webhook
def test_valid_capture_confirms_the_appointment(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_1", gateway_order_id="order_test_1")

    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.APPLIED
    appointment.refresh_from_db()
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    payment = Payment.objects.unfiltered().get(order=order)
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert order.status == PaymentOrderStatus.SUCCESS
    assert order.paid_at is not None
    assert payment.status == PaymentOrderStatus.SUCCESS
    assert payment.amount == Decimal("500.00")
    assert payment.paid_at is not None
    # The confirmation is attributed to the payment, not to a mystery actor.
    history = AppointmentStatusHistory.objects.get(
        appointment=appointment,
        to_status=AppointmentStatus.CONFIRMED,
    )
    assert history.actor_type == AppointmentActor.SYSTEM
    assert history.actor_id == f"payment:{payment.pk}"


def test_unsigned_webhook_is_400_and_changes_nothing(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_1", gateway_order_id="order_test_1")

    response = _deliver(customer_client, fake_gateway, body, sign=False)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid_signature"
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT
    assert PaymentOrder.objects.unfiltered().get(appointment=appointment).status == (
        PaymentOrderStatus.PENDING
    )
    # Not even a rejected delivery leaves a row: an attacker cannot fill the
    # event table with forged envelopes.
    assert not PaymentEvent.objects.all().exists()
    assert not Payment.objects.unfiltered().exists()


def test_tampered_signature_is_400(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_1", gateway_order_id="order_test_1")

    response = customer_client.post(
        WEBHOOK,
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_EVENT="payment.captured",
        HTTP_X_RAZORPAY_SIGNATURE="0" * 64,
    )

    assert response.status_code == 400
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_signature_is_verified_over_the_raw_bytes_not_reserialized_json(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Reordered keys and different spacing must not change the verdict.

    If the view parsed then re-serialized before verifying, this delivery - a
    byte-different but semantically identical JSON document - would fail its own
    signature check and the payment would silently never confirm.
    """
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    payload = json.loads(_captured_body(event_id="evt_1", gateway_order_id="order_test_1"))
    reordered = (
        json.dumps(
            {
                "payload": payload["payload"],
                "id": payload["id"],
                "event": payload["event"],
                "entity": payload["entity"],
            },
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    assert reordered != _captured_body(event_id="evt_1", gateway_order_id="order_test_1")

    response = _deliver(customer_client, fake_gateway, reordered)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.APPLIED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_replayed_webhook_confirms_exactly_once(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_1", gateway_order_id="order_test_1")

    for _ in range(3):
        response = _deliver(customer_client, fake_gateway, body)
        assert response.status_code == 200

    assert PaymentEvent.objects.all().count() == 1
    assert Payment.objects.unfiltered().count() == 1
    confirmations = AppointmentStatusHistory.objects.filter(
        appointment=appointment, to_status=AppointmentStatus.CONFIRMED
    )
    assert confirmations.count() == 1
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_duplicate_capture_with_a_different_event_id_still_cannot_double_record(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A gateway re-signing the same payment is deduped on the payment id too.

    `event_id` dedupe covers redelivery. A *new* event id describing the same
    capture is a different attack, and the unique constraint on
    `gateway_payment_id` is what stops it becoming a second `Payment`.
    """
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)

    first = _deliver(
        customer_client,
        fake_gateway,
        _captured_body(event_id="evt_1", gateway_order_id="order_test_1"),
    )
    second = _deliver(
        customer_client,
        fake_gateway,
        _captured_body(event_id="evt_2", gateway_order_id="order_test_1"),
    )

    assert first.data["outcome"] == PaymentEventOutcome.APPLIED
    assert second.status_code == 200
    assert Payment.objects.unfiltered().count() == 1
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_duplicate_gateway_payment_id_cannot_be_inserted(
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    from django.db import IntegrityError, transaction

    appointment, order = paid_hold
    Payment.objects.unfiltered().create(
        tenant_id=order.tenant_id,
        customer_id=order.customer_id,
        appointment=appointment,
        order=order,
        gateway="razorpay",
        gateway_payment_id="pay_dup",
        amount="500.00",
        status=PaymentOrderStatus.PENDING,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.unfiltered().create(
            tenant_id=order.tenant_id,
            customer_id=order.customer_id,
            appointment=appointment,
            order=order,
            gateway="razorpay",
            gateway_payment_id="pay_dup",
            amount="500.00",
            status=PaymentOrderStatus.PENDING,
        )
    del fake_gateway


def test_duplicate_gateway_order_id_cannot_be_inserted(
    paid_hold: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_customer: Any,
) -> None:
    """§A5: gateway ids are unique at the *schema*, for orders as well as payments.

    The webhook resolves an order by a globally unique `gateway_order_id` with
    no tenant context in hand, so two orders sharing one id would make that
    lookup ambiguous - and the loser would silently never be confirmed.
    """
    from django.db import IntegrityError, transaction
    from django.utils import timezone

    from apps.appointments.models import Appointment
    from tests.conftest import slot_at

    _appointment, order = paid_hold
    order.gateway_order_id = "order_shared"
    order.save(update_fields=["gateway_order_id"])

    # A second hold and its order, both legal until the id is set.
    other_appointment = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(2),
        end_at=slot_at(2, 30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
        slot_hold_expires_at=timezone.now() + timedelta(minutes=10),
    )
    other_order = PaymentOrder.objects.unfiltered().create(
        tenant=booking_tenant,
        customer=booking_customer,
        appointment=other_appointment,
        gateway="razorpay",
        gateway_mode="test",
        gateway_order_id=None,
        amount="500.00",
        currency="INR",
        status=PaymentOrderStatus.CREATED,
    )
    assert other_order.gateway_order_id is None  # NULL before it exists at the gateway

    with pytest.raises(IntegrityError), transaction.atomic():
        other_order.gateway_order_id = "order_shared"
        other_order.save(update_fields=["gateway_order_id"])


def test_unknown_gateway_order_is_200_with_no_state_change(
    customer_client: Any,
    fake_gateway: Any,
) -> None:
    body = _captured_body(event_id="evt_x", gateway_order_id="order_never_made")

    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.UNMATCHED
    event = PaymentEvent.objects.all().get(event_id="evt_x")
    assert event.outcome == PaymentEventOutcome.UNMATCHED
    assert not Payment.objects.unfiltered().exists()


def test_capture_for_a_different_amount_does_not_confirm(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Charged ₹1 against a ₹500 order: refuse, and say why.

    The order is left `PENDING` rather than failed because the money genuinely
    landed - writing it off would hide a real charge from the reconciliation
    and refund queues.
    """
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_1", gateway_order_id="order_test_1", amount_minor=100)

    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.FAILED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    assert order.status == PaymentOrderStatus.PENDING
    payment = Payment.objects.unfiltered().get(order=order)
    assert payment.status == PaymentOrderStatus.FAILED
    assert payment.failure_reason == "amount_mismatch"
    assert payment.amount == Decimal("1.00")


def test_payment_failed_event_moves_the_order_to_failed(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_fail", gateway_order_id="order_test_1")

    response = _deliver(customer_client, fake_gateway, body, event_type="payment.failed")

    assert response.status_code == 200
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    assert order.status == PaymentOrderStatus.FAILED
    appointment.refresh_from_db()
    # The appointment stays a hold until the sweep expires it; a declined
    # payment is not the same as a lapsed hold (plan §6.1).
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_unhandled_event_is_acknowledged_and_ignored(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_sub", gateway_order_id="order_test_1")

    response = _deliver(customer_client, fake_gateway, body, event_type="subscription.charged")

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    assert order.status == PaymentOrderStatus.PENDING


def test_late_capture_after_hold_expiry_does_not_resurrect_the_appointment(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Money that lands after the slot is gone is recorded, not honoured.

    The `Payment` row is created as `SUCCESS` on purpose: a real charge with no
    record is how a practice ends up owing a refund it cannot see. The
    appointment stays `EXPIRED`, and the normal refund flow picks it up.
    """
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)

    from apps.appointments import services as appointment_services

    with tenant_context(booking_tenant):
        appointment_services.expire_stale_holds(
            appointment.provider_id, now=appointment.slot_hold_expires_at + timedelta(seconds=1)
        )
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.EXPIRED

    body = _captured_body(event_id="evt_late", gateway_order_id="order_test_1")
    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.EXPIRED
    assert (
        AppointmentStatusHistory.objects.filter(
            appointment=appointment, to_status=AppointmentStatus.CONFIRMED
        ).count()
        == 0
    )
    order = PaymentOrder.objects.unfiltered().get(appointment=appointment)
    payment = Payment.objects.unfiltered().get(order=order)
    assert payment.status == PaymentOrderStatus.SUCCESS
    assert order.status == PaymentOrderStatus.EXPIRED


def test_capture_in_the_wrong_mode_is_refused(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A test-mode capture cannot confirm a live booking (S §A5).

    Simulated by delivering with a gateway whose `mode` differs from the one the
    order was stamped with - the same thing that happens when someone flips
    `PAYMENT_MODE` in the environment and old orders are still in flight.
    """
    appointment, order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    order.refresh_from_db()
    assert order.gateway_mode == "test"

    fake_gateway.mode = "live"
    body = _captured_body(event_id="evt_mode", gateway_order_id="order_test_1")
    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT
    assert not Payment.objects.unfiltered().exists()
    event = PaymentEvent.objects.all().get(event_id="evt_mode")
    assert event.detail == "mode_mismatch:test!=live"


def test_live_order_does_not_accept_a_test_mode_capture(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    fake_gateway.mode = "live"
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    order.refresh_from_db()
    assert order.gateway_mode == "live"

    fake_gateway.mode = "test"
    body = _captured_body(event_id="evt_mode2", gateway_order_id="order_test_1")
    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_order_paid_event_reads_the_payment_back_from_the_gateway(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """`order.paid` carries no payment id, so it is resolved, not trusted."""
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    fake_gateway.captured_payment("order_test_1", payment_id="pay_from_list")
    body = json.dumps(
        {
            "entity": "event",
            "event": "order.paid",
            "id": "evt_order_paid",
            "payload": {"entity": "order", "amount": 50000, "order_id": "order_test_1"},
        }
    ).encode()

    response = _deliver(customer_client, fake_gateway, body, event_type="order.paid")

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.APPLIED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert Payment.objects.unfiltered().get().gateway_payment_id == "pay_from_list"


def test_order_paid_with_no_captured_payment_does_not_confirm(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    fake_gateway.money_nowhere("order_test_1")
    body = json.dumps(
        {
            "entity": "event",
            "event": "order.paid",
            "id": "evt_no_money",
            "payload": {"entity": "order", "amount": 50000, "order_id": "order_test_1"},
        }
    ).encode()

    response = _deliver(customer_client, fake_gateway, body, event_type="order.paid")

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_webhook_without_an_event_id_is_recorded_but_never_applies(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """An event we cannot dedupe is an event we must not act on."""
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "order_id": "order_test_1",
                "amount": 50000,
                "payment": {"id": "pay_anon"},
            },
        }
    ).encode()

    response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT
    assert not Payment.objects.unfiltered().exists()


def test_webhook_needs_no_authentication_but_a_bad_signature_still_fails(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """The gateway holds no JWT; its credential is the HMAC, and only the HMAC."""
    appointment, _order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    body = _captured_body(event_id="evt_noauth", gateway_order_id="order_test_1")

    from rest_framework.test import APIClient

    anonymous = APIClient()
    response = _deliver(anonymous, fake_gateway, body)
    assert response.status_code == 200

    tampered = _deliver(anonymous, fake_gateway, body, sign=False)
    assert tampered.status_code == 400
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


# ------------------------------------------------------------- no client path
def test_no_route_lets_a_client_assert_a_payment_status() -> None:
    """Enumerate the URLconf: nothing accepts a client-asserted payment status.

    S §A5 asks for this as a structural claim, so it is checked structurally -
    every non-GET route in the project is walked, and the write surface under
    `payments/` is asserted to be exactly two endpoints, neither of which has a
    status field on its serializer. Adding a "mark paid" route fails here
    before it ships.
    """
    writes = _write_routes()

    customer_writes = {route for route, _ in writes if "payments" in route and "admin" not in route}
    assert customer_writes == {
        "api/v1/payments/create-order/",
        "api/v1/payments/webhook",
    }, customer_writes

    admin_actions = {
        _action_name(route)
        for route, _ in writes
        if "/admin/payments" in route or "/admin/refunds" in route
    }
    assert admin_actions == {"refund", "settle"}, admin_actions

    # Nothing anywhere else in the API mutates a payment either. The routes
    # above are the entire write surface, so anything left is one that appeared
    # after this test was written.
    known = customer_writes | {route for route, _ in writes if _action_name(route) in admin_actions}
    stray = [
        route
        for route, _ in writes
        if ("payment" in route or "refund" in route) and route not in known
    ]
    assert not stray, stray


def test_no_payment_write_serializer_accepts_a_status_or_an_amount_that_is_charged() -> None:
    """The customer-facing write is inspected field by field.

    A route with no status field is only as safe as its serializer, so this
    names the fields explicitly: `create-order` takes an appointment id and an
    advisory amount, and the webhook takes a signed body. `status` appears
    nowhere, and the read serializers are entirely read-only - which is what
    makes "no PATCH /payments/{id}" sufficient rather than lucky. The one
    partial-write serializer is `RefundSerializer`, admin-only, and it is held
    to an explicit field list instead of the blanket assertion.
    """
    assert set(CreateOrderSerializer().fields) == {"appointment_id", "amount"}
    assert CreateOrderSerializer().fields["amount"].write_only is True

    for serializer_cls in (
        PaymentOrderSerializer,
        PaymentSerializer,
        PaymentEventSerializer,
    ):
        writable = {name for name, field in serializer_cls().fields.items() if not field.read_only}
        assert not writable, f"{serializer_cls.__name__} accepts {writable}"

    # The refund write is the one place an amount is legitimately accepted, and
    # it is admin-only, partial-capable, and never sets a status. `RefundSerializer`
    # is therefore the one exception to the loop above, and it is checked here
    # explicitly rather than waved through.
    writable = set(RefundSerializer().fields) - set(RefundSerializer.Meta.read_only_fields)
    assert writable == {"amount", "reason"}
    assert RefundSerializer().fields["status"].read_only is True


def _write_routes() -> list[tuple[str, str]]:
    """Every non-GET API route in the project as `(normalised_path, method)`.

    Router views expose an `actions` map; plain `APIView`s (the webhook) do
    not, so their verbs are read off the class. DRF's format-suffix twins are
    dropped - they are the same endpoint, and counting them twice would let a
    new route hide behind a format variant.

    Scoped to the API namespace on purpose. The Django admin is a superuser
    debugging tool rather than an API surface, and the money tables are already
    registered there read-only (no add, change or delete permission), so it
    would add noise without adding a claim. If that ever changes, the check
    belongs here - not in a comment.
    """
    from django.urls import URLPattern, URLResolver

    found: list[tuple[str, str]] = []
    verbs = ("get", "post", "put", "patch", "delete")

    def walk(pattern: Any, prefix: str) -> None:
        if isinstance(pattern, URLResolver):
            for sub in pattern.url_patterns:
                walk(sub, prefix + str(pattern.pattern))
            return
        if not isinstance(pattern, URLPattern):
            return
        raw = prefix + str(pattern.pattern)
        if not raw.startswith("api/"):
            return
        route = _normalise_route(raw)
        actions = getattr(pattern.callback, "actions", None)
        if actions:
            methods = [m for m in actions if m.lower() not in {"get", "head", "options"}]
        else:
            view_class = getattr(pattern.callback, "view_class", None)
            methods = [m for m in verbs if view_class is not None and hasattr(view_class, m)]
        found.extend((route, method.lower()) for method in methods)

    for top in get_resolver().url_patterns:
        walk(top, "")
    return found


def _action_name(route: str) -> str:
    """The last path segment of a route, with the trailing slash removed.

    Every router action ends in `/`, so splitting on `/` and taking the tail
    yields `""` for all of them - an audit that reports one nameless action
    rather than the two it was asked about.
    """
    return route.rstrip("/").rsplit("/", 1)[-1]


def _normalise_route(route: str) -> str:
    """Turn a DRF regex pattern into the path a human would recognise.

    The format-suffix twin (`…\\.(?P<format>[a-z0-9]+)/?$`) is the same endpoint
    as its plain sibling, so it is stripped rather than counted - otherwise a
    new route could hide behind a format variant and still pass the audit.

    Anchors are removed with a lookbehind rather than `str.replace`: DRF's own
    `(?P<pk>[^/.]+)` contains a `^` inside a character class, and a blanket
    replace turns "not a slash or a dot" into "a slash or a dot" - which then
    defeats the `{pk}` substitution below and leaves the audit reading
    `{pk}/.]+)/refund/`.
    """
    import re

    route = re.sub(r"\\\.\(\?P<format>[^)]*\)", "", route)
    route = re.sub(r"(?<!\[)\^", "", route)
    route = re.sub(r"(?<!\[)\$", "", route)
    # Stripping the format suffix leaves the `/?` that the suffixed twin adds,
    # so `…/create-order/?` would survive as a phantom sibling of
    # `…/create-order/` and the endpoint would be counted twice.
    if route.endswith("/?"):
        route = route[:-1]
    route = re.sub(r"\(\?P<pk>[^)]*\)", "{pk}", route)
    route = re.sub(r"\(\?P<slug>[^)]*\)", "{slug}", route)
    return route


# ----------------------------------------------------------------- status poll
def test_status_poll_reconciles_a_missed_webhook(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    fake_gateway.truth_for("order_test_1", "SUCCESS")
    fake_gateway.captured_payment("order_test_1")

    with tenant_context(booking_tenant):
        response = customer_client.get(f"/api/v1/payments/{order.pk}/status/")

    assert response.status_code == 200
    assert response.data["status"] == PaymentOrderStatus.SUCCESS
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_status_poll_does_not_invent_a_success_without_a_payment(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    fake_gateway.money_nowhere("order_test_1")

    with tenant_context(booking_tenant):
        response = customer_client.get(f"/api/v1/payments/{order.pk}/status/")

    assert response.status_code == 200
    assert response.data["status"] == PaymentOrderStatus.PENDING
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_status_poll_survives_a_gateway_outage(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """An unreachable gateway must not 500 a status read or change anything."""
    appointment, order = paid_hold
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    fake_gateway.unavailable = True

    with tenant_context(booking_tenant):
        response = customer_client.get(f"/api/v1/payments/{order.pk}/status/")

    assert response.status_code == 200
    assert response.data["status"] == PaymentOrderStatus.PENDING
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_status_poll_of_another_customers_order_is_404(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    _appointment, order = paid_hold
    from rest_framework.test import APIClient

    from apps.auth_otp.tokens import issue_customer_token_pair
    from apps.customers.models import Customer

    other = Customer.objects.unfiltered().create(tenant=booking_tenant, phone="+919888888888")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_customer_token_pair(other)['access']}")
    with tenant_context(booking_tenant):
        response = client.get(f"/api/v1/payments/{order.pk}/status/")
    assert response.status_code == 404


# ------------------------------------------------------------------ hold sweep
def test_hold_expiry_expires_the_order_not_fails_it(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """An abandoned checkout is `EXPIRED`, so "we gave up" stays distinguishable.

    Folding it into `FAILED` would make the reconciliation task unable to tell
    a lapsed hold from a gateway decline (plan §6.1, flagged deviation).
    """
    appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        appointment_services_expiry = appointment.provider_id
        from apps.appointments import services as appointment_services

        appointment_services.expire_stale_holds(
            appointment_services_expiry,
            now=appointment.slot_hold_expires_at + timedelta(seconds=1),
        )

    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.EXPIRED
    assert order.status != PaymentOrderStatus.FAILED


def test_hold_cancellation_cancels_the_order(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        response = customer_client.post(
            f"/api/v1/me/appointments/{appointment.pk}/cancel/",
            {"reason": "Changed my mind."},
            format="json",
        )
    assert response.status_code == 200, response.data
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.CANCELLED


# ---------------------------------------------------------------- reconciliation
def test_reconcile_marks_a_gone_checkout_failed(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        fake_gateway.truth_for("order_test_1", "FAILED")
        stats = payment_services.reconcile_pending_payments(older_than_minutes=0)

    assert stats["failed"] == 1
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.FAILED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_reconcile_never_resurrects_a_failed_payment(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """S §A5: a `FAILED` order stays failed, even if the gateway says paid later.

    An order the reconcile pass already gave up on is not a candidate, at all,
    for any status - otherwise a stale `fetch_order` reading could confirm a
    booking whose hold is long gone.
    """
    appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        fake_gateway.truth_for("order_test_1", "FAILED")
        payment_services.reconcile_pending_payments(older_than_minutes=0)
        order.refresh_from_db()
        assert order.status == PaymentOrderStatus.FAILED

        fake_gateway.truth_for("order_test_1", "SUCCESS")
        fake_gateway.captured_payment("order_test_1")
        payment_services.reconcile_pending_payments(older_than_minutes=0)

    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.FAILED
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.PENDING_PAYMENT


def test_reconcile_confirms_a_capture_the_webhook_never_delivered(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        fake_gateway.truth_for("order_test_1", "SUCCESS")
        fake_gateway.captured_payment("order_test_1", payment_id="pay_reconciled")
        stats = payment_services.reconcile_pending_payments(older_than_minutes=0)

    assert stats["captured"] == 1
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.SUCCESS
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_reconcile_leaves_orders_alone_while_the_gateway_is_down(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Uncertainty is not failure. A dead gateway must not close live orders."""
    _appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        fake_gateway.unavailable = True
        stats = payment_services.reconcile_pending_payments(older_than_minutes=0)

    assert stats["unavailable"] == 1
    assert stats["failed"] == 0
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.PENDING


def test_reconcile_ignores_orders_young_enough_to_still_be_paying(
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    _appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        fake_gateway.truth_for("order_test_1", "FAILED")
        stats = payment_services.reconcile_pending_payments(older_than_minutes=60)

    assert stats["checked"] == 0
    order.refresh_from_db()
    assert order.status == PaymentOrderStatus.PENDING


def test_reconcile_task_is_scheduled_hourly() -> None:
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["reconcile-pending-payments"]
    assert entry["task"] == "payments.reconcile_pending_payments"
    assert entry["schedule"].minute == {0}
    assert entry["schedule"].hour == set(range(24))  # crontab expands "*"


# --------------------------------------------------------------------- refunds
def _capture_money(
    customer_client: Any,
    booking_tenant: Any,
    appointment: Any,
    fake_gateway: Any,
    *,
    event_id: str = "evt_paid",
) -> Payment:
    _start_checkout(customer_client, booking_tenant, appointment, fake_gateway)
    _deliver(
        customer_client,
        fake_gateway,
        _captured_body(event_id=event_id, gateway_order_id="order_test_1"),
    )
    return Payment.objects.unfiltered().get(appointment=appointment)


def test_refund_creates_a_pending_action_row_and_does_not_refund(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """D2: one click records a liability. It does not move money and does not
    mark the payment refunded."""
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)

    with tenant_context(booking_tenant):
        response = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/",
            {"reason": "Client cancelled."},
            format="json",
        )

    assert response.status_code == 201, response.data
    assert response.data["status"] == RefundStatus.PENDING_ACTION
    refund = Refund.objects.unfiltered().get(pk=response.data["id"])
    assert refund.amount == Decimal("500.00")
    payment.refresh_from_db()
    assert payment.status == PaymentOrderStatus.SUCCESS
    assert AuditLog.objects.filter(action="payment.refund_requested").exists()


def test_settle_is_required_before_a_payment_becomes_refunded(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        created = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {}, format="json"
        )
        refund_id = created.data["id"]
        payment.refresh_from_db()
        assert payment.status == PaymentOrderStatus.SUCCESS

        settled = booking_admin_client.post(
            f"{ADMIN_REFUNDS}{refund_id}/settle/",
            {"gateway_refund_id": "rfnd_1"},
            format="json",
        )

    assert settled.status_code == 200, settled.data
    assert settled.data["status"] == RefundStatus.SETTLED
    assert settled.data["payment_status"] == PaymentOrderStatus.REFUNDED
    payment.refresh_from_db()
    assert payment.status == PaymentOrderStatus.REFUNDED
    order = payment.order
    assert order.status == PaymentOrderStatus.SUCCESS  # the order is not rewritten
    assert AuditLog.objects.filter(action="payment.refund_settled").exists()


def test_settle_cannot_precede_creating_a_refund(
    booking_admin_client: Any,
    booking_tenant: Any,
) -> None:
    """There is nothing to settle: no refund row means no endpoint to call."""
    response = booking_admin_client.post(
        f"{ADMIN_REFUNDS}{'0' * 8}-0000-0000-0000-{'0' * 12}/settle/", {}, format="json"
    )
    assert response.status_code == 404


def test_settling_a_refund_twice_is_rejected(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        created = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {}, format="json"
        )
        refund_id = created.data["id"]
        first = booking_admin_client.post(f"{ADMIN_REFUNDS}{refund_id}/settle/", {}, format="json")
        second = booking_admin_client.post(f"{ADMIN_REFUNDS}{refund_id}/settle/", {}, format="json")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.data["error"]["code"] == "invalid_state_transition"


def test_refund_cannot_exceed_the_captured_amount(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        response = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "5000.00"}, format="json"
        )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "refund_exceeds_payment"
    assert not Refund.objects.unfiltered().exists()


def test_a_second_refund_cannot_stack_past_the_captured_amount(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Replaying the refund request must not manufacture a second liability."""
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        first = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "300.00"}, format="json"
        )
        replay = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "300.00"}, format="json"
        )
        over = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "250.00"}, format="json"
        )

    assert first.status_code == 201
    assert replay.status_code == 409
    assert replay.data["error"]["code"] == "refund_exceeds_remaining"
    assert over.status_code == 409
    assert Refund.objects.unfiltered().count() == 1


def test_partial_refund_keeps_the_payment_successful_until_fully_returned(
    booking_admin_client: Any,
    booking_tenant: Any,
    customer_client: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        part = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "200.00"}, format="json"
        )
        rest = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {"amount": "300.00"}, format="json"
        )
        booking_admin_client.post(f"{ADMIN_REFUNDS}{part.data['id']}/settle/", {}, format="json")
        payment.refresh_from_db()
        assert payment.status == PaymentOrderStatus.SUCCESS

        booking_admin_client.post(f"{ADMIN_REFUNDS}{rest.data['id']}/settle/", {}, format="json")

    payment.refresh_from_db()
    assert payment.status == PaymentOrderStatus.REFUNDED


def test_refund_is_admin_only(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A customer refunding themselves would be the whole vulnerability."""
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    with tenant_context(booking_tenant):
        response = customer_client.post(f"{ADMIN_PAYMENTS}{payment.pk}/refund/", {}, format="json")
    assert response.status_code in {401, 403, 404}
    assert not Refund.objects.unfiltered().exists()


def test_refund_requires_a_successful_payment(
    booking_admin_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """A ₹0 "refund" of money that never arrived is not an operation."""
    _appointment, order = paid_hold
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        payment_services.create_gateway_order(order=order)
        pending = Payment.objects.unfiltered().create(
            tenant_id=order.tenant_id,
            customer_id=order.customer_id,
            appointment_id=order.appointment_id,
            order=order,
            gateway="razorpay",
            gateway_payment_id="pay_never",
            amount="500.00",
            status=PaymentOrderStatus.PENDING,
        )
        response = booking_admin_client.post(
            f"{ADMIN_PAYMENTS}{pending.pk}/refund/", {}, format="json"
        )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "payment_not_refundable"


def test_refunded_payment_cannot_be_captured_again(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """Terminal is terminal: no webhook may walk a `REFUNDED` order back."""
    appointment, _order = paid_hold
    payment = _capture_money(customer_client, booking_tenant, appointment, fake_gateway)
    from apps.payments import services as payment_services

    with tenant_context(booking_tenant):
        refund = payment_services.request_refund(payment=payment, amount=payment.amount)
        payment_services.settle_refund(refund=refund)
        payment.refresh_from_db()
        assert payment.status == PaymentOrderStatus.REFUNDED

        body = _captured_body(event_id="evt_after_refund", gateway_order_id="order_test_1")
        response = _deliver(customer_client, fake_gateway, body)

    assert response.status_code == 200
    assert response.data["outcome"] == PaymentEventOutcome.IGNORED
    payment.refresh_from_db()
    assert payment.status == PaymentOrderStatus.REFUNDED


# ------------------------------------------------------------------- money type
def test_amounts_stay_decimal_across_many_small_charges(
    customer_client: Any,
    booking_tenant: Any,
    paid_hold: Any,
    fake_gateway: Any,
) -> None:
    """₹0.01 × N must stay exact - a float here is a real reconciliation bug."""
    from apps.payments.gateways.razorpay import RazorpayGateway

    gateway = RazorpayGateway(key_id="k", key_secret="s", webhook_secret="w")
    for paise in (1, 7, 10, 99, 100, 101, 999, 1000):
        assert gateway.to_minor(Decimal("0.01") * paise) == paise
    assert gateway.from_minor(1, "INR") == Decimal("0.01")
    assert gateway.from_minor(12345, "INR") == Decimal("123.45")
    total = sum((gateway.from_minor(p, "INR") for p in (1, 2, 3)), Decimal("0.00"))
    assert total == Decimal("0.06")
    assert _capture_money(
        customer_client, booking_tenant, paid_hold[0], fake_gateway
    ).amount == Decimal("500.00")


# -------------------------------------------------------------- state machine
def test_illegal_payment_transitions_are_refused() -> None:
    from apps.payments.state import can_transition

    assert can_transition(PaymentOrderStatus.CREATED, PaymentOrderStatus.PENDING)
    assert can_transition(PaymentOrderStatus.PENDING, PaymentOrderStatus.SUCCESS)
    assert can_transition(PaymentOrderStatus.SUCCESS, PaymentOrderStatus.REFUNDED)
    # A capture against an order the gateway never acknowledged is an anomaly,
    # not a shortcut.
    assert not can_transition(PaymentOrderStatus.CREATED, PaymentOrderStatus.SUCCESS)
    assert not can_transition(PaymentOrderStatus.SUCCESS, PaymentOrderStatus.FAILED)
    assert not can_transition(PaymentOrderStatus.FAILED, PaymentOrderStatus.SUCCESS)
    assert not can_transition(PaymentOrderStatus.EXPIRED, PaymentOrderStatus.SUCCESS)
    assert not can_transition(PaymentOrderStatus.REFUNDED, PaymentOrderStatus.SUCCESS)
    # Re-applying a status is a duplicate, not an edge.
    assert not can_transition(PaymentOrderStatus.SUCCESS, PaymentOrderStatus.SUCCESS)


def test_transition_raises_for_an_illegal_edge(paid_hold: Any) -> None:
    from django.utils import timezone

    from apps.payments.state import transition

    _appointment, order = paid_hold
    order.status = PaymentOrderStatus.FAILED
    order.save(update_fields=["status"])
    with pytest.raises(InvalidStateTransitionError):
        transition(order, PaymentOrderStatus.SUCCESS, now=timezone.now())


def test_paid_at_is_only_stamped_by_the_transition(paid_hold: Any) -> None:
    from django.utils import timezone

    from apps.payments.state import transition

    _appointment, order = paid_hold
    now = timezone.now()
    transition(order, PaymentOrderStatus.PENDING, now=now)
    assert order.paid_at is None
    transition(order, PaymentOrderStatus.SUCCESS, now=now)
    assert order.paid_at is not None


# ---------------------------------------------------------------- event trail
def test_payment_events_are_admin_readable(booking_admin_client: Any) -> None:
    with tenant_context(booking_tenant_of(booking_admin_client)):
        response = booking_admin_client.get("/api/v1/admin/payment-events/")
    assert response.status_code == 200


def test_payment_events_are_not_customer_readable(customer_client: Any) -> None:
    response = customer_client.get("/api/v1/admin/payment-events/")
    assert response.status_code in {401, 403}


# ------------------------------------------------------------ django admin
def test_the_django_admin_cannot_edit_or_delete_money_rows(
    paid_hold: Any, booking_tenant: Any
) -> None:
    """§6 forbids a confirmation with no gateway behind it, delete included.

    `has_change_permission` alone does not cover this: Django still serves
    the delete confirmation page when only that is overridden, so a superuser
    could have removed the row that every reconciliation later looks for.
    """
    from django.contrib import admin
    from rest_framework.test import APIRequestFactory

    from apps.accounts.models import Role, User
    from apps.payments.admin import (
        PaymentAdmin,
        PaymentEventAdmin,
        PaymentOrderAdmin,
        RefundAdmin,
    )
    from apps.payments.models import Payment, PaymentEvent, Refund

    request = APIRequestFactory().post("/admin/payments/payment/1/delete/")
    request.user = User.objects.create_user(
        email="root@dwyer.com",
        password="Str0ng-Passw0rd!",
        full_name="Root",
        tenant=booking_tenant,
        role=Role.OWNER,
        is_staff=True,
        is_superuser=True,
    )

    for model, admin_class in (
        (PaymentOrder, PaymentOrderAdmin),
        (Payment, PaymentAdmin),
        (Refund, RefundAdmin),
        (PaymentEvent, PaymentEventAdmin),
    ):
        instance = admin_class(model=model, admin_site=admin.site)
        assert instance.has_add_permission(request) is False, model.__name__
        assert instance.has_change_permission(request) is False, model.__name__
        assert instance.has_delete_permission(request) is False, model.__name__


def booking_tenant_of(client: Any) -> Any:
    return client.handler._force_user.tenant
