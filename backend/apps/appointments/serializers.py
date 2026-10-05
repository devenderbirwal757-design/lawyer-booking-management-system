"""Serializers for appointments (plan §4; PRD §8, §10).

Input side: `BookingSerializer` / `RescheduleSerializer` / `CancelSerializer`
whitelist exactly what the booking flow accepts; `start_at` is parsed and
timezone-normalised by the domain service, never booked as a literal string.
`AdminCancelSerializer` makes the reason mandatory for admin cancellations
(plan checklist line 548).

Output side mirrors the PRD §10 booking details (booking id, service, date,
time, lawyer, amount, payment status, booking status) plus the status history
in the *detail* variants, and the admin variants add the customer identity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from rest_framework import serializers

from apps.appointments.models import Appointment, AppointmentStatusHistory
from apps.appointments.services import parse_start_at
from apps.customers.models import Customer
from apps.services.models import Service, ServiceStatus
from common.exceptions import ServiceDisabledError
from common.money import format_price


# ------------------------------------------------------------------ inputs
class BookingSerializer(serializers.Serializer[dict[str, Any]]):
    service_id = serializers.UUIDField()
    start_at = serializers.CharField()
    customer_notes = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=2000
    )

    def _tenant(self) -> Any:
        return self.context.get("tenant")

    def _customer(self) -> Any:
        return self.context.get("customer")

    def validate_service_id(self, value: str) -> Service:
        tenant = self._tenant()
        if tenant is None:
            raise serializers.ValidationError("No tenant context for this request.")
        try:
            service = Service.objects.unfiltered().select_related("provider").get(pk=value)
        except Service.DoesNotExist:
            raise serializers.ValidationError("Unknown service.") from None
        if service.tenant_id != getattr(tenant, "pk", tenant):
            raise serializers.ValidationError("Unknown service.")
        if str(service.status) != ServiceStatus.ACTIVE:
            raise ServiceDisabledError()
        if service.provider_id is None:
            raise ServiceDisabledError(
                detail="This service is not assigned to a provider yet.",
                code="service_unbookable",
            )
        return service

    def validate_start_at(self, value: str) -> datetime:
        tenant = self._tenant()
        if tenant is None:
            raise serializers.ValidationError("No tenant context for this request.")
        try:
            return parse_start_at(value, tenant)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        """Normalise the payload for `book_appointment`.

        `service_id` becomes `service` (an instance, resolved by
        `validate_service_id`) and `start_at` is already an aware UTC datetime
        from `validate_start_at`, so the domain service receives a value, not a
        string to re-parse.
        """
        return {
            "service": validated_data["service_id"],
            "start_at": validated_data["start_at"],
            "customer_notes": validated_data.get("customer_notes", ""),
        }


class RescheduleSerializer(serializers.Serializer[dict[str, Any]]):
    start_at = serializers.CharField()

    def validate_start_at(self, value: str) -> datetime:
        tenant = self.context.get("tenant")
        if tenant is None:
            raise serializers.ValidationError("No tenant context for this request.")
        try:
            return parse_start_at(value, tenant)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err


class CancelSerializer(serializers.Serializer[dict[str, Any]]):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class AdminCancelSerializer(CancelSerializer):
    reason = serializers.CharField(max_length=500)


# ----------------------------------------------------------------- outputs
class ServiceSummarySerializer(serializers.ModelSerializer[Service]):
    price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields: tuple[str, ...] = (
            "id",
            "name",
            "slug",
            "duration_minutes",
            "price_amount",
            "price",
            "currency",
        )
        read_only_fields = fields

    def get_price(self, obj: Service) -> str:
        return format_price(obj.price_amount, obj.currency)


class StatusHistorySerializer(serializers.ModelSerializer[AppointmentStatusHistory]):
    """One leg of the audit trail.

    `actor_id` is exposed on purpose: the practice side needs to know *which*
    staff member moved an appointment, and a history leg without its actor is
    an audit trail with the interesting part missing.
    """

    class Meta:
        model = AppointmentStatusHistory
        fields: tuple[str, ...] = (
            "id",
            "from_status",
            "to_status",
            "actor_type",
            "actor_id",
            "note",
            "created_at",
        )
        read_only_fields = fields


class AppointmentSerializer(serializers.ModelSerializer[Appointment]):
    service = ServiceSummarySerializer(read_only=True)
    provider_id = serializers.UUIDField(read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    price_amount = serializers.DecimalField(
        source="service.price_amount",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    currency = serializers.CharField(source="service.currency", read_only=True)

    class Meta:
        model = Appointment
        fields: tuple[str, ...] = (
            "id",
            "service",
            "provider_id",
            "provider_name",
            "start_at",
            "end_at",
            "status",
            "slot_hold_expires_at",
            "cancellation_reason",
            "customer_notes",
            "price_amount",
            "currency",
            "rescheduled_from_id",
            "created_via",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AppointmentDetailSerializer(AppointmentSerializer):
    status_history = StatusHistorySerializer(many=True, read_only=True)

    class Meta(AppointmentSerializer.Meta):
        fields: tuple[str, ...] = (*AppointmentSerializer.Meta.fields, "status_history")


class CustomerSummarySerializer(serializers.ModelSerializer[Customer]):
    class Meta:
        model = Customer
        fields: tuple[str, ...] = ("id", "name", "phone", "email")
        read_only_fields = fields


class AdminAppointmentSerializer(AppointmentSerializer):
    customer = CustomerSummarySerializer(read_only=True)
    payment_status = serializers.SerializerMethodField()

    class Meta(AppointmentSerializer.Meta):
        fields: tuple[str, ...] = (
            *AppointmentSerializer.Meta.fields,
            "customer",
            "tenant_id",
            "payment_status",
        )

    def get_payment_status(self, obj: Appointment) -> str | None:
        order = getattr(obj, "payment_order", None)
        return None if order is None else str(order.status)


class AdminAppointmentDetailSerializer(AdminAppointmentSerializer, AppointmentDetailSerializer):
    class Meta(AdminAppointmentSerializer.Meta):
        fields: tuple[str, ...] = (
            *AdminAppointmentSerializer.Meta.fields,
            "status_history",
        )


class AdminAppointmentNotesSerializer(serializers.ModelSerializer[Appointment]):
    """The only writable surface for `PATCH /admin/appointments/{id}`.

    Field whitelist doubles as the API contract: notes may be edited, anything
    else - including `status` - is rejected rather than silently ignored.
    """

    class Meta:
        model = Appointment
        fields: tuple[str, ...] = ("customer_notes",)


__all__ = (
    "AdminAppointmentDetailSerializer",
    "AdminAppointmentNotesSerializer",
    "AdminAppointmentSerializer",
    "AdminCancelSerializer",
    "AppointmentDetailSerializer",
    "AppointmentSerializer",
    "BookingSerializer",
    "CancelSerializer",
    "RescheduleSerializer",
    "StatusHistorySerializer",
)
