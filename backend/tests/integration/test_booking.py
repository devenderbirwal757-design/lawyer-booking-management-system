"""The customer-facing booking lifecycle (plan §4, §5; PRD §8-9).

Exercised through the real HTTP surface with a customer JWT, because the claims
worth testing here are mostly about *who* may act: the AD appointment id in the
PRD is the ownership boundary, and every read/cancel/reschedule here is resolved
through `customer=request.customer`, so a foreign appointment must be a 404 and
never a 403 (S §A4 IDOR).

Also covers the client rules that need an API to exercise: the slot must be
server-generated, the same `Idempotency-Key` must not double-book, an expired
hold must free the slot again, and the cancellation window must bite.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from rest_framework import status

from apps.appointments.models import Appointment, AppointmentStatus
from apps.customers.models import Customer
from apps.payments.models import PaymentOrder
from common.querysets import tenant_context

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

BOOK = "/api/v1/appointments/"
ME = "/api/v1/me/appointments"
ADMIN = "/api/v1/admin/appointments/"

#: Idempotency keys must be UUIDs (common.idempotency validates them).
IDEMPOTENCY_KEY = str(UUID(int=1))
IDEMPOTENCY_KEY_1 = str(UUID(int=1))
IDEMPOTENCY_KEY_2 = str(UUID(int=2))


def _book(
    client: Any,
    tenant: Any,
    service: Any,
    start: str | None = None,
    **extra: Any,
) -> Any:
    from tests.conftest import slot_iso

    payload: dict[str, Any] = {
        "service_id": str(service.pk),
        "start_at": start or slot_iso(),
    }
    payload.update(extra)
    with tenant_context(tenant):
        return client.post(BOOK, payload, format="json")


# ------------------------------------------------------------------- creating
def test_booking_a_slot_creates_a_hold_with_the_server_duration(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    response = _book(customer_client, booking_tenant, booking_service)
    assert response.status_code == status.HTTP_201_CREATED, response.content

    body = response.json()
    assert body["status"] == AppointmentStatus.PENDING_PAYMENT
    assert body["start_at"] == slot_iso()
    assert body["service"]["duration_minutes"] == booking_service.duration_minutes
    assert body["price_amount"] == "500.00"
    assert body["currency"] == "INR"
    assert len(body["status_history"]) == 1

    appointment = Appointment.objects.unfiltered().get(pk=body["id"])
    assert appointment.provider_id == booking_service.provider_id
    assert appointment.slot_hold_expires_at is not None
    assert appointment.created_via == "api"
    # Consultation end, buffer excluded: the buffer is turnaround, not billable
    # time, and the exclusion constraint must not over-block the next slot.
    assert appointment.end_at - appointment.start_at == timedelta(
        minutes=booking_service.duration_minutes
    )


def test_booking_returns_409_when_the_time_is_not_a_generated_slot(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    # 10:07 is inside the working window but off the 30-minute grid.
    response = _book(customer_client, booking_tenant, booking_service, start=slot_iso(0, 7))
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "slot_unavailable"
    assert not Appointment.objects.unfiltered().exists()


def test_booking_returns_409_outside_working_hours(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    # The rule runs 10:00-13:00; 18:00 is not on the grid at all.
    response = _book(customer_client, booking_tenant, booking_service, start=slot_iso(8))
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "slot_unavailable"


def test_booking_the_same_slot_twice_returns_409(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    first = _book(customer_client, booking_tenant, booking_service)
    assert first.status_code == status.HTTP_201_CREATED

    second = _book(customer_client, booking_tenant, booking_service, start=first.json()["start_at"])
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["error"]["code"] == "slot_unavailable"
    assert Appointment.objects.unfiltered().count() == 1


def test_a_paid_service_also_creates_a_payment_order(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    booking_service.requires_payment = True
    booking_service.save(update_fields=["requires_payment"])

    response = _book(customer_client, booking_tenant, booking_service)
    assert response.status_code == status.HTTP_201_CREATED

    order = PaymentOrder.objects.unfiltered().get(appointment_id=response.json()["id"])
    assert str(order.amount) == booking_service.price_amount
    assert order.currency == booking_service.currency
    assert order.tenant_id == booking_tenant.pk
    assert order.customer is not None


def test_a_pay_later_service_creates_no_payment_order(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    _book(customer_client, booking_tenant, booking_service)
    assert not PaymentOrder.objects.unfiltered().exists()


def test_booking_creates_an_order_only_once_per_idempotency_key(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    payload = {"service_id": str(booking_service.pk), "start_at": slot_iso()}
    with tenant_context(booking_tenant):
        first = customer_client.post(
            BOOK, payload, format="json", HTTP_IDEMPOTENCY_KEY=IDEMPOTENCY_KEY
        )
        second = customer_client.post(
            BOOK, payload, format="json", HTTP_IDEMPOTENCY_KEY=IDEMPOTENCY_KEY
        )

    assert first.status_code == status.HTTP_201_CREATED
    # A replay resolves the original hold instead of carving a second one, so
    # it is 200, not 201 - the client learns nothing new was created.
    assert second.status_code == status.HTTP_200_OK
    assert second.json()["id"] == first.json()["id"]
    assert Appointment.objects.unfiltered().count() == 1


def test_a_different_idempotency_key_books_a_different_slot(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    with tenant_context(booking_tenant):
        first = customer_client.post(
            BOOK,
            {"service_id": str(booking_service.pk), "start_at": slot_iso()},
            format="json",
            HTTP_IDEMPOTENCY_KEY=IDEMPOTENCY_KEY_1,
        )
        second = customer_client.post(
            BOOK,
            {"service_id": str(booking_service.pk), "start_at": slot_iso(0, 30)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=IDEMPOTENCY_KEY_2,
        )

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_201_CREATED
    assert first.json()["id"] != second.json()["id"]


def test_booking_requires_a_customer_session(
    api_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    with tenant_context(booking_tenant):
        response = api_client.post(
            BOOK,
            {"service_id": str(booking_service.pk), "start_at": slot_iso()},
            format="json",
        )
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


def test_booking_another_tenants_service_is_rejected(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.services.models import Service
    from apps.tenants.models import Tenant
    from tests.conftest import slot_iso

    rival = Tenant.objects.create(slug="mason", name="Mason & Co", timezone="UTC")
    theirs = Service.objects.unfiltered().create(
        tenant=rival,
        name="Rival consultation",
        slug="rival",
        duration_minutes=30,
        price_amount="900.00",
    )

    with tenant_context(booking_tenant):
        response = customer_client.post(
            BOOK,
            {"service_id": str(theirs.pk), "start_at": slot_iso()},
            format="json",
        )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not Appointment.objects.unfiltered().exists()


# ------------------------------------------------------------- /me dashboard
def test_my_appointments_lists_only_my_bookings(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.customers.models import Customer
    from tests.conftest import slot_at, slot_iso

    _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    _book(customer_client, booking_tenant, booking_service, start=slot_iso(1))

    stranger = Customer.objects.unfiltered().create(
        tenant=booking_tenant, phone="+919000000000", name="Someone Else"
    )
    Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=stranger,
        service=booking_service,
        start_at=slot_iso(2),
        end_at=slot_at(2) + timedelta(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        response = customer_client.get(f"{ME}/")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["count"] == 2
    assert all(item["id"] != "" for item in body["results"])


def test_upcoming_and_past_buckets_partition_the_appointments(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    from django.utils import timezone as dj_timezone

    from tests.conftest import slot_iso

    _book(customer_client, booking_tenant, booking_service, start=slot_iso())

    Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=dj_timezone.now() - timedelta(days=1),
        end_at=dj_timezone.now() - timedelta(days=1) + timedelta(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.COMPLETED,
    )

    with tenant_context(booking_tenant):
        upcoming = customer_client.get(f"{ME}/", {"status": "upcoming"})
        history = customer_client.get(f"{ME}/", {"status": "past"})

    assert upcoming.json()["count"] == 1
    assert history.json()["count"] == 1
    assert history.json()["results"][0]["status"] == AppointmentStatus.COMPLETED


def test_reading_my_appointment_returns_the_status_history(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    booked = _book(customer_client, booking_tenant, booking_service)
    appointment_id = booked.json()["id"]

    with tenant_context(booking_tenant):
        response = customer_client.get(f"{ME}/{appointment_id}/")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == appointment_id
    assert [leg["to_status"] for leg in body["status_history"]] == [
        AppointmentStatus.PENDING_PAYMENT
    ]


def test_another_customers_appointment_is_a_404_not_a_403(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.customers.models import Customer
    from tests.conftest import slot_at

    stranger = Customer.objects.unfiltered().create(
        tenant=booking_tenant, phone="+919111111111", name="Not Mine"
    )
    theirs = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=stranger,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        response = customer_client.get(f"{ME}/{theirs.pk}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cancelling_my_appointment_records_the_reason(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    booked = _book(customer_client, booking_tenant, booking_service)
    appointment_id = booked.json()["id"]

    with tenant_context(booking_tenant):
        response = customer_client.post(
            f"{ME}/{appointment_id}/cancel/", {"reason": "Cannot make it."}, format="json"
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == AppointmentStatus.CANCELLED
    assert body["cancellation_reason"] == "Cannot make it."

    appointment = Appointment.objects.unfiltered().get(pk=appointment_id)
    assert appointment.status == AppointmentStatus.CANCELLED
    last_change = appointment.status_history.last()
    assert last_change is not None
    assert last_change.actor_type == "customer"


def test_a_cancelled_slot_becomes_bookable_again(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:

    booked = _book(customer_client, booking_tenant, booking_service)
    appointment_id, start = booked.json()["id"], booked.json()["start_at"]

    with tenant_context(booking_tenant):
        customer_client.post(f"{ME}/{appointment_id}/cancel/", {}, format="json")
        again = _book(customer_client, booking_tenant, booking_service, start=start)

    assert again.status_code == status.HTTP_201_CREATED
    assert Appointment.objects.unfiltered().count() == 2


def test_a_cancelled_appointment_cannot_be_cancelled_again(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    booked = _book(customer_client, booking_tenant, booking_service)
    appointment_id = booked.json()["id"]

    with tenant_context(booking_tenant):
        customer_client.post(f"{ME}/{appointment_id}/cancel/", {}, format="json")
        again = customer_client.post(f"{ME}/{appointment_id}/cancel/", {}, format="json")

    assert again.status_code == status.HTTP_409_CONFLICT
    assert again.json()["error"]["code"] == "invalid_state_transition"


def test_an_expired_hold_stops_occupying_the_slot(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from django.utils import timezone as dj_timezone

    booked = _book(customer_client, booking_tenant, booking_service)
    appointment_id, start = booked.json()["id"], booked.json()["start_at"]

    # Backdate the hold: it is now lapsed, so the slot must be offered again
    # and the stale hold must be swept rather than blocking the insert.
    Appointment.objects.unfiltered().filter(pk=appointment_id).update(
        slot_hold_expires_at=dj_timezone.now() - timedelta(minutes=1)
    )

    with tenant_context(booking_tenant):
        again = _book(customer_client, booking_tenant, booking_service, start=start)

    assert again.status_code == status.HTTP_201_CREATED
    stale = Appointment.objects.unfiltered().get(pk=appointment_id)
    assert stale.status == AppointmentStatus.EXPIRED


# ------------------------------------------------------------------ reschedule
def test_rescheduling_retires_the_original_and_holds_the_new_slot(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    booked = _book(customer_client, booking_tenant, booking_service)
    original_id = booked.json()["id"]

    with tenant_context(booking_tenant):
        response = customer_client.post(
            f"{ME}/{original_id}/reschedule/", {"start_at": slot_iso(1)}, format="json"
        )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] != original_id
    assert body["start_at"] == slot_iso(1)
    assert body["rescheduled_from_id"] == original_id

    original = Appointment.objects.unfiltered().get(pk=original_id)
    assert original.status == AppointmentStatus.RESCHEDULED
    # The new hold is a fresh hold, exactly like a first booking.
    assert body["status"] == AppointmentStatus.PENDING_PAYMENT


def test_rescheduling_frees_the_original_slot(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    booked = _book(customer_client, booking_tenant, booking_service)
    original_id, original_start = booked.json()["id"], booked.json()["start_at"]

    with tenant_context(booking_tenant):
        customer_client.post(
            f"{ME}/{original_id}/reschedule/", {"start_at": slot_iso(1)}, format="json"
        )
        rebooked = _book(customer_client, booking_tenant, booking_service, start=original_start)

    assert rebooked.status_code == status.HTTP_201_CREATED


def test_rescheduling_onto_an_unavailable_slot_returns_409(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_iso

    booked = _book(customer_client, booking_tenant, booking_service)
    original_id = booked.json()["id"]

    with tenant_context(booking_tenant):
        response = customer_client.post(
            f"{ME}/{original_id}/reschedule/", {"start_at": slot_iso(0, 7)}, format="json"
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "slot_unavailable"
    # The original is untouched: a failed move must not half-apply.
    assert (
        Appointment.objects.unfiltered().get(pk=original_id).status
        == AppointmentStatus.PENDING_PAYMENT
    )


def test_rescheduling_another_customers_appointment_is_a_404(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.customers.models import Customer
    from tests.conftest import slot_at, slot_iso

    stranger = Customer.objects.unfiltered().create(tenant=booking_tenant, phone="+919222222222")
    theirs = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=stranger,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
    )

    with tenant_context(booking_tenant):
        response = customer_client.post(
            f"{ME}/{theirs.pk}/reschedule/", {"start_at": slot_iso(1)}, format="json"
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_rescheduling_another_customers_appointment_cannot_cancel_it_either(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.customers.models import Customer
    from tests.conftest import slot_at

    stranger = Customer.objects.unfiltered().create(tenant=booking_tenant, phone="+919333333333")
    theirs = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=stranger,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
    )

    with tenant_context(booking_tenant):
        response = customer_client.post(f"{ME}/{theirs.pk}/cancel/", {}, format="json")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    theirs.refresh_from_db()
    assert theirs.status == AppointmentStatus.PENDING_PAYMENT


# --------------------------------------------------------- policy & conflicts
def test_a_confirmed_appointment_inside_the_policy_window_cannot_be_cancelled(
    customer_client: Any,
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    settings: Any,
) -> None:
    """The window is a policy, not a suggestion: the client is refused, the
    practice is not. Same appointment, same moment, two answers."""
    from django.utils import timezone as dj_timezone

    from tests.conftest import slot_iso

    settings.CANCELLATION_POLICY_MIN_HOURS = 24
    booked = _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    appointment_id = booked.json()["id"]

    # Pull the appointment inside the policy window: the slot it was booked for
    # is weeks out, which is exactly when a client *can* still cancel.
    Appointment.objects.unfiltered().filter(pk=appointment_id).update(
        start_at=dj_timezone.now() + timedelta(hours=1),
        end_at=dj_timezone.now() + timedelta(hours=1, minutes=30),
    )

    with tenant_context(booking_tenant):
        confirmed = booking_admin_client.post(
            f"{ADMIN}{appointment_id}/confirm/", {}, format="json"
        )
        client_cancel = customer_client.post(f"{ME}/{appointment_id}/cancel/", {}, format="json")
        admin_cancel = booking_admin_client.post(
            f"{ADMIN}{appointment_id}/cancel/", {"reason": "Client called."}, format="json"
        )

    assert confirmed.status_code == status.HTTP_200_OK, confirmed.content
    assert confirmed.json()["status"] == AppointmentStatus.CONFIRMED
    assert client_cancel.status_code == status.HTTP_409_CONFLICT, client_cancel.content
    assert client_cancel.json()["error"]["code"] == "cancellation_window"
    assert admin_cancel.status_code == status.HTTP_200_OK, admin_cancel.content
    assert admin_cancel.json()["status"] == AppointmentStatus.CANCELLED


def test_a_blocked_window_over_an_appointment_cannot_be_created(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    """An exception marks time *off* the grid; it may not swallow a booking."""
    from apps.scheduling.models import ExceptionType
    from tests.conftest import slot_at

    Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.post(
            "/api/v1/admin/availability/exceptions/",
            {
                "provider": str(booking_service.provider_id),
                "date": slot_at().date().isoformat(),
                "start_time": "10:00",
                "end_time": "12:00",
                "type": ExceptionType.BLOCKED,
                "reason": "Court appearance.",
            },
            format="json",
        )

    assert response.status_code == status.HTTP_409_CONFLICT, response.content
    assert response.json()["error"]["code"] == "slot_occupied"


def test_the_same_slot_cannot_be_booked_twice(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    """The second request gets 409, not a second row: the service checks first
    and the exclusion constraint is the backstop behind it."""
    from tests.conftest import slot_iso

    first = _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    assert first.status_code == status.HTTP_201_CREATED

    second = _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    assert second.status_code == status.HTTP_409_CONFLICT
    assert Appointment.objects.unfiltered().count() == 1


def test_a_completed_appointment_is_terminal(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    from tests.conftest import slot_at

    confirmed = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        done = booking_admin_client.post(f"{ADMIN}{confirmed.pk}/complete/", {}, format="json")
        again = booking_admin_client.post(f"{ADMIN}{confirmed.pk}/confirm/", {}, format="json")

    assert done.status_code == status.HTTP_200_OK, done.content
    assert done.json()["status"] == AppointmentStatus.COMPLETED
    assert again.status_code == status.HTTP_409_CONFLICT, again.content
    assert again.json()["error"]["code"] == "invalid_state_transition"


def test_a_booked_slot_disappears_from_the_slots_endpoint(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    """Availability must reflect live appointments, not just the rules grid."""
    from tests.conftest import FIRST_SLOT, slot_iso

    _book(customer_client, booking_tenant, booking_service, start=slot_iso())

    with tenant_context(booking_tenant):
        response = customer_client.get(
            "/api/v1/availability/slots",
            {
                "provider_id": str(booking_service.provider_id),
                "service_id": str(booking_service.pk),
                "date": FIRST_SLOT.date().isoformat(),
            },
        )

    assert response.status_code == status.HTTP_200_OK, response.content
    offered = set(response.json()["slots"])
    # The hold blocks its own slot; the rest of the day is still offered.
    assert slot_iso() not in offered
    assert slot_iso(1) in offered


# --------------------------------------------------------- admin / practice
def test_admin_cannot_confirm_a_paid_service_before_payment(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    """A paid hold is not confirmable by hand - the payment must land first."""
    from tests.conftest import slot_at

    booking_service.requires_payment = True
    booking_service.save(update_fields=["requires_payment"])
    hold = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.post(f"{ADMIN}{hold.pk}/confirm/", {}, format="json")

    assert response.status_code == status.HTTP_409_CONFLICT, response.content
    hold.refresh_from_db()
    assert hold.status == AppointmentStatus.PENDING_PAYMENT


def test_admin_can_mark_an_appointment_no_show(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
    booking_owner: Any,
) -> None:
    from tests.conftest import slot_at

    confirmed = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.post(f"{ADMIN}{confirmed.pk}/no-show/", {}, format="json")

    assert response.status_code == status.HTTP_200_OK, response.content
    assert response.json()["status"] == AppointmentStatus.NO_SHOW
    last_leg = response.json()["status_history"][-1]
    assert last_leg["actor_type"] == "admin"
    assert last_leg["actor_id"] == str(booking_owner.pk)


def test_admin_reschedule_creates_a_new_appointment_for_the_practice(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    from tests.conftest import slot_at

    confirmed = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.post(
            f"{ADMIN}{confirmed.pk}/reschedule/",
            {"start_at": slot_at(1).isoformat()},
            format="json",
        )

    assert response.status_code == status.HTTP_200_OK, response.content
    body = response.json()
    assert body["id"] != str(confirmed.pk)
    assert body["rescheduled_from_id"] == str(confirmed.pk)
    assert body["created_via"] == "admin"
    confirmed.refresh_from_db()
    assert confirmed.status == AppointmentStatus.RESCHEDULED


def test_admin_cannot_patch_the_status_directly(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    """S §A8: the state machine is the only way in, so a raw PATCH is refused."""
    from tests.conftest import slot_at

    hold = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.patch(
            f"{ADMIN}{hold.pk}/", {"status": AppointmentStatus.CONFIRMED}, format="json"
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.content
    hold.refresh_from_db()
    assert hold.status == AppointmentStatus.PENDING_PAYMENT


def test_admin_can_patch_only_the_customer_notes(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    from tests.conftest import slot_at

    hold = Appointment.objects.unfiltered().create(
        tenant=booking_tenant,
        provider=booking_service.provider,
        customer=booking_customer,
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=booking_tenant.timezone,
        status=AppointmentStatus.PENDING_PAYMENT,
    )

    with tenant_context(booking_tenant):
        response = booking_admin_client.patch(
            f"{ADMIN}{hold.pk}/", {"customer_notes": "Called about the venue."}, format="json"
        )

    assert response.status_code == status.HTTP_200_OK, response.content
    hold.refresh_from_db()
    assert hold.customer_notes == "Called about the venue."

    # Anything outside the whitelist is ignored, not applied: the appointment's
    # own fields stay owned by the services.
    with tenant_context(booking_tenant):
        ignored = booking_admin_client.patch(
            f"{ADMIN}{hold.pk}/",
            {"customer_notes": "Updated.", "end_at": slot_at(2).isoformat()},
            format="json",
        )

    assert ignored.status_code == status.HTTP_200_OK
    hold.refresh_from_db()
    assert hold.customer_notes == "Updated."
    assert hold.end_at == slot_at(minutes=30)


def test_admin_filters_by_status_date_and_search(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    from tests.conftest import FIRST_SLOT, slot_at

    for appointment_status, offset in (
        (AppointmentStatus.PENDING_PAYMENT, 0),
        (AppointmentStatus.CONFIRMED, 1),
    ):
        Appointment.objects.unfiltered().create(
            tenant=booking_tenant,
            provider=booking_service.provider,
            customer=booking_customer,
            service=booking_service,
            start_at=slot_at(offset),
            end_at=slot_at(offset, 30),
            timezone=booking_tenant.timezone,
            status=appointment_status,
        )

    day = FIRST_SLOT.date().isoformat()
    with tenant_context(booking_tenant):
        by_status = booking_admin_client.get(ADMIN, {"status": "confirmed"})
        active = booking_admin_client.get(ADMIN, {"status": "active"})
        by_date = booking_admin_client.get(ADMIN, {"date": day})
        other_day = booking_admin_client.get(ADMIN, {"date": "2001-01-01"})
        by_service = booking_admin_client.get(ADMIN, {"service_id": str(booking_service.pk)})
        by_customer = booking_admin_client.get(ADMIN, {"customer_id": str(booking_customer.pk)})
        by_search = booking_admin_client.get(ADMIN, {"q": "Priya"})
        nonsense = booking_admin_client.get(ADMIN, {"status": "not-a-status"})

    assert by_status.json()["count"] == 1
    assert active.json()["count"] == 2
    assert by_date.json()["count"] == 2
    assert other_day.json()["count"] == 0
    assert by_service.json()["count"] == 2
    assert by_customer.json()["count"] == 2
    assert by_search.json()["count"] == 2
    # An unknown filter value is an empty set, never an unfiltered list.
    assert nonsense.json()["count"] == 0


def test_admin_never_sees_another_tenants_appointments(
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from apps.tenants.models import Tenant
    from tests.conftest import slot_at

    rival = Tenant.objects.create(
        slug="whitmore", name="Whitmore", timezone=booking_tenant.timezone
    )
    theirs = Appointment.objects.unfiltered().create(
        tenant=rival,
        provider=booking_service.provider,
        customer=Customer.objects.unfiltered().create(
            tenant=rival, phone="+919444444444", name="Rival Client"
        ),
        service=booking_service,
        start_at=slot_at(),
        end_at=slot_at(minutes=30),
        timezone=rival.timezone,
        status=AppointmentStatus.CONFIRMED,
    )

    with tenant_context(booking_tenant):
        listing = booking_admin_client.get(ADMIN)
        detail = booking_admin_client.get(f"{ADMIN}{theirs.pk}/")

    assert listing.json()["count"] == 0
    assert detail.status_code == status.HTTP_404_NOT_FOUND


def test_a_customer_token_cannot_reach_the_admin_surface(
    customer_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
) -> None:
    from tests.conftest import slot_at

    with tenant_context(booking_tenant):
        response = customer_client.get(ADMIN, {"date": slot_at().date().isoformat()})

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_booking_of_one_slot_produces_exactly_one_hold(
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    booking_customer: Any,
) -> None:
    """The database is the referee (S §A8).

    Two real connections race for the same slot. Whatever the interleaving,
    exactly one hold may exist: the loser is translated into the same 409 the
    sequential path returns, never a second row and never a 500.
    """
    import threading

    from django.db import connections

    from apps.appointments import services as appointment_services
    from apps.appointments.services import SlotUnavailableError
    from tests.conftest import slot_at

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        # Each thread gets its own connection, or they would share one
        # transaction and never actually race.
        connections.close_all()
        try:
            barrier.wait(timeout=10)
            with tenant_context(booking_tenant):
                appointment_services.book_appointment(
                    tenant=booking_tenant,
                    customer=booking_customer,
                    service=booking_service,
                    start_at=slot_at(),
                    actor_type="customer",
                    actor_id=str(booking_customer.pk),
                )
            result = "created"
        except SlotUnavailableError:
            result = "conflict"
        finally:
            connections.close_all()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(outcomes) == 2
    assert sorted(outcomes) == ["conflict", "created"]
    assert Appointment.objects.unfiltered().count() == 1


def test_a_customer_cannot_grief_the_calendar_with_unpaid_holds(
    customer_client: Any,
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    settings: Any,
) -> None:
    """S §A7: a throttle bounds rate, this bounds inventory.

    A patient client could otherwise book a whole week of slots as holds and
    pay for none of them. The cap is on *unpaid* holds only, so a real customer
    with several confirmed appointments is never blocked.
    """
    from tests.conftest import slot_iso

    settings.MAX_ACTIVE_HOLDS_PER_CUSTOMER = 2

    first = _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    second = _book(customer_client, booking_tenant, booking_service, start=slot_iso(1))
    third = _book(customer_client, booking_tenant, booking_service, start=slot_iso(2))

    assert first.status_code == status.HTTP_201_CREATED, first.content
    assert second.status_code == status.HTTP_201_CREATED, second.content
    assert third.status_code == status.HTTP_409_CONFLICT, third.content
    assert third.json()["error"]["code"] == "hold_limit_reached"
    assert Appointment.objects.unfiltered().count() == 2

    # Confirming one frees a slot in the budget: it is no longer inventory.
    with tenant_context(booking_tenant):
        confirmed = booking_admin_client.post(
            f"{ADMIN}{first.json()['id']}/confirm/", {}, format="json"
        )
    assert confirmed.status_code == status.HTTP_200_OK, confirmed.content
    with tenant_context(booking_tenant):
        fourth = _book(customer_client, booking_tenant, booking_service, start=slot_iso(2))
    assert fourth.status_code == status.HTTP_201_CREATED, fourth.content


def test_rescheduling_cannot_bypass_the_cancellation_window(
    customer_client: Any,
    booking_admin_client: Any,
    booking_tenant: Any,
    booking_service: Any,
    booking_rule: Any,
    settings: Any,
) -> None:
    """S §A8: a move is a cancel plus a rebook, so the window applies to it too."""
    from django.utils import timezone as dj_timezone

    from tests.conftest import slot_at, slot_iso

    settings.CANCELLATION_POLICY_MIN_HOURS = 24
    booked = _book(customer_client, booking_tenant, booking_service, start=slot_iso())
    appointment_id = booked.json()["id"]
    Appointment.objects.unfiltered().filter(pk=appointment_id).update(
        start_at=dj_timezone.now() + timedelta(hours=1),
        end_at=dj_timezone.now() + timedelta(hours=1, minutes=30),
    )

    with tenant_context(booking_tenant):
        confirmed = booking_admin_client.post(
            f"{ADMIN}{appointment_id}/confirm/", {}, format="json"
        )
        refused = customer_client.post(
            f"{ME}/{appointment_id}/reschedule/",
            {"start_at": slot_at(1).isoformat()},
            format="json",
        )
        allowed = booking_admin_client.post(
            f"{ADMIN}{appointment_id}/reschedule/",
            {"start_at": slot_at(1).isoformat()},
            format="json",
        )

    assert confirmed.status_code == status.HTTP_200_OK, confirmed.content
    assert refused.status_code == status.HTTP_409_CONFLICT, refused.content
    assert refused.json()["error"]["code"] == "cancellation_window"
    assert allowed.status_code == status.HTTP_200_OK, allowed.content
