"""Appointment endpoints (plan §4; PRD §7-8; S §A4, §A8).

Three surfaces, one row:

- `BookingViewSet` (`POST /appointments`, `GET /appointments/{id}`) — the
  client creates a hold; the retrieve is ownership-scoped so a booking is only
  readable by its owner (AD appointment id, S §A4).
- `CustomerAppointmentViewSet` (`/me/appointments`) — the client's dashboard:
  list with upcoming/past/cancelled buckets (PRD §9), detail, cancel and
  reschedule, all resolved through `customer=request.customer`, so a foreign
  appointment answers 404, never 403.
- `AdminAppointmentViewSet` (`/admin/appointments`) — the practice side: the
  PRD §15 filters (date, status, service, payment status, customer, search),
  a notes-only PATCH (a direct `PATCH status=CONFIRMED` is rejected, S §A8),
  and the confirm/cancel/complete/no-show/reschedule actions, each of which
  funnels through `apps.appointments.services`.

No view touches `status` directly: transitions run through the domain
services, which lock the row and enforce the state machine.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.appointments import services as appointment_services
from apps.appointments.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentActor,
    AppointmentStatus,
)
from apps.appointments.serializers import (
    AdminAppointmentDetailSerializer,
    AdminAppointmentNotesSerializer,
    AdminAppointmentSerializer,
    AdminCancelSerializer,
    AppointmentDetailSerializer,
    AppointmentSerializer,
    BookingSerializer,
    CancelSerializer,
    RescheduleSerializer,
)
from apps.auth_otp.authentication import CustomerJWTAuthentication
from apps.payments.models import PaymentOrderStatus
from common.permissions import IsAdmin, IsCustomer
from common.throttles import BookingRateThrottle
from common.viewset import BaseViewSet, ReadOnlyModelViewSet


class _CustomerScopedMixin:
    """Resolve the tenant from the *customer* and scope every read to them.

    Two separate jobs, both about ownership:

    - `get_tenant` prefers the customer principal's own tenant. The stock
      implementation reads `request.user`, which is only an admin `User`;
    - `get_queryset` narrows to their rows, so another customer's appointment
      is a 404 from `get_object()` and never a 403 (S §A4).

    `super()` reaches the real implementations on the concrete viewset, in the
    same cooperative style as `common.mixins.TenantFilterMixin`.
    """

    # DRF sets this per request; declaring it here keeps the mixin typed
    # without inheriting from the viewset (which would shadow `super()`).
    request: Any

    def get_tenant(self) -> Any:
        customer = getattr(self.request, "customer", None)
        tenant = getattr(customer, "tenant", None)
        if tenant is not None:
            return tenant
        # Provided by the concrete viewset (`BaseViewSet.get_tenant`).
        return super().get_tenant()  # type: ignore[misc]

    def get_queryset(self) -> Any:
        # Provided by the concrete viewset (`BaseViewSet.get_queryset`).
        qs = super().get_queryset()  # type: ignore[misc]
        customer = getattr(self.request, "customer", None)
        if customer is None:
            return qs.none()
        return qs.filter(customer=customer)


# ------------------------------------------------------------------ booking
@extend_schema(
    tags=["appointments"],
    responses={
        201: OpenApiResponse(description="hold created"),
        409: OpenApiResponse(description="slot_unavailable"),
    },
)
class BookingViewSet(_CustomerScopedMixin, BaseViewSet):
    """`POST /appointments` (hold + payment order) and owner-scoped retrieve."""

    queryset = Appointment.objects.unfiltered()
    serializer_class = AppointmentDetailSerializer
    authentication_classes = [CustomerJWTAuthentication]  # noqa: RUF012 - DRF's own style
    permission_classes = [IsCustomer]  # noqa: RUF012 - DRF's own style
    throttle_classes = [BookingRateThrottle]  # noqa: RUF012 - DRF's own style
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012 - DRF

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = BookingSerializer(
            data=request.data,
            context={"tenant": self.get_tenant(), "customer": request.customer},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        appointment, created = appointment_services.book_appointment(
            tenant=self.get_tenant(),
            customer=request.customer,
            # `validate_service_id` resolves the id to a tenant-checked
            # Service, so the instance arrives under the field's own name.
            service=data["service_id"],
            start_at=data["start_at"],
            customer_notes=data["customer_notes"],
            idempotency_key=self.get_idempotency_key(),
            actor_type=AppointmentActor.CUSTOMER,
            actor_id=str(request.customer.pk),
        )
        body = AppointmentDetailSerializer(appointment).data
        return Response(
            body,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ------------------------------------------------------------ customer (/me)
@extend_schema(tags=["appointments"])
class CustomerAppointmentViewSet(_CustomerScopedMixin, ReadOnlyModelViewSet):
    """The client dashboard under `/me/appointments` (plan §4, PRD §9)."""

    queryset = Appointment.objects.unfiltered()
    serializer_class = AppointmentSerializer
    authentication_classes = [CustomerJWTAuthentication]  # noqa: RUF012 - DRF's own style
    permission_classes = [IsCustomer]  # noqa: RUF012 - DRF's own style

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        if self.action in ("retrieve", "cancel", "reschedule"):
            return AppointmentDetailSerializer
        return AppointmentSerializer

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        bucket = (self.request.query_params.get("status") or "").strip().lower()
        now = timezone.now()
        if bucket == "upcoming":
            qs = qs.filter(status__in=ACTIVE_STATUSES, end_at__gte=now)
        elif bucket == "past":
            qs = qs.filter(
                Q(status__in=(AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW))
                | Q(status__in=ACTIVE_STATUSES, end_at__lt=now)
            )
        elif bucket == "cancelled":
            qs = qs.filter(
                status__in=(
                    AppointmentStatus.CANCELLED,
                    AppointmentStatus.EXPIRED,
                    AppointmentStatus.RESCHEDULED,
                )
            )
        return qs.order_by("-start_at")

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Any, pk: Any = None) -> Response:
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = appointment_services.cancel_appointment(
            appointment=self.get_object(),
            reason=serializer.validated_data["reason"],
            client_side=True,
            actor_type=AppointmentActor.CUSTOMER,
            actor_id=str(request.customer.pk),
        )
        return Response(AppointmentDetailSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request: Any, pk: Any = None) -> Response:
        serializer = RescheduleSerializer(
            data=request.data,
            context={"tenant": self.get_tenant()},
        )
        serializer.is_valid(raise_exception=True)
        created = appointment_services.reschedule_appointment(
            appointment=self.get_object(),
            new_start=serializer.validated_data["start_at"],
            # The client cannot reschedule its way out of the cancellation
            # policy: a move is a cancel plus a rebook.
            client_side=True,
            actor_type=AppointmentActor.CUSTOMER,
            actor_id=str(request.customer.pk),
        )
        return Response(AppointmentDetailSerializer(created).data)


# ------------------------------------------------------------------- admin
@extend_schema(tags=["admin/appointments"])
class AdminAppointmentViewSet(BaseViewSet):
    """Practice-side appointments: filters, notes PATCH, lifecycle actions."""

    queryset = Appointment.objects.unfiltered()
    serializer_class = AdminAppointmentSerializer
    permission_classes = [IsAdmin]  # noqa: RUF012 - DRF's own style
    # `post` is here for the lifecycle actions; the list/retrieve surface stays
    # read-only, and `patch` is the notes-only edit.
    http_method_names = ["get", "post", "patch", "head", "options"]  # noqa: RUF012 - DRF

    def get_serializer_class(self) -> type[serializers.Serializer[Any]]:
        # `self.action` is the *method* name, so the `no-show` route arrives
        # here as `no_show`; `url_path` only changes the URL.
        if self.action in ("update", "partial_update"):
            return AdminAppointmentNotesSerializer
        if self.action in ("retrieve", "confirm", "cancel", "complete", "no_show", "reschedule"):
            return AdminAppointmentDetailSerializer
        return AdminAppointmentSerializer

    # ------------------------------------------------------------- filtering
    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("service", "provider", "customer")
        params = self.request.query_params

        raw_status = (params.get("status") or "").upper()
        if raw_status == "ACTIVE":
            qs = qs.filter(status__in=ACTIVE_STATUSES)
        elif raw_status in AppointmentStatus.values:
            qs = qs.filter(status=raw_status)
        elif raw_status:
            # An unregulated status filter must not widen into a different set.
            return qs.none()

        raw_date = params.get("date")
        if raw_date:
            try:
                day = date.fromisoformat(raw_date)
            except ValueError:
                return qs.none()
            tenant = self.get_tenant()
            zone = (
                ZoneInfo(getattr(tenant, "timezone", None) or "UTC") if tenant else ZoneInfo("UTC")
            )
            start = datetime.combine(day, dtime.min, tzinfo=zone)
            qs = qs.filter(start_at__gte=start, start_at__lt=start + timedelta(days=1))

        for param, field in (
            ("service_id", "service_id"),
            ("customer_id", "customer_id"),
        ):
            value = params.get(param)
            if value:
                try:
                    uuid.UUID(str(value))
                except ValueError:
                    return qs.none()
                qs = qs.filter(**{field: value})

        raw_payment = (params.get("payment_status") or "").upper()
        if raw_payment:
            if raw_payment not in PaymentOrderStatus.values:
                return qs.none()
            qs = qs.filter(payment_order__status=raw_payment)

        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(customer__name__icontains=q)
                | Q(customer__phone__icontains=q)
                | Q(service__name__icontains=q)
                | Q(id__icontains=q)
            )
        return qs

    # -------------------------------------------------------------- partial
    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        if "status" in request.data:
            raise ValidationError(
                {"status": "Status changes run through the appointment actions, not PATCH."}
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        if "status" in request.data:
            raise ValidationError(
                {"status": "Status changes run through the appointment actions, not PATCH."}
            )
        return super().partial_update(request, *args, **kwargs)

    # --------------------------------------------------------------- actions
    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request: Any, pk: Any = None) -> Response:
        updated = appointment_services.confirm_appointment(
            appointment=self.get_object(),
            actor_type=AppointmentActor.ADMIN,
            actor_id=str(request.user.pk),
        )
        return Response(AdminAppointmentDetailSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Any, pk: Any = None) -> Response:
        serializer = AdminCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = appointment_services.cancel_appointment(
            appointment=self.get_object(),
            reason=serializer.validated_data["reason"],
            actor_type=AppointmentActor.ADMIN,
            actor_id=str(request.user.pk),
        )
        return Response(AdminAppointmentDetailSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request: Any, pk: Any = None) -> Response:
        updated = appointment_services.complete_appointment(
            appointment=self.get_object(),
            actor_type=AppointmentActor.ADMIN,
            actor_id=str(request.user.pk),
        )
        return Response(AdminAppointmentDetailSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request: Any, pk: Any = None) -> Response:
        updated = appointment_services.mark_no_show(
            appointment=self.get_object(),
            actor_type=AppointmentActor.ADMIN,
            actor_id=str(request.user.pk),
        )
        return Response(AdminAppointmentDetailSerializer(updated).data)

    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request: Any, pk: Any = None) -> Response:
        serializer = RescheduleSerializer(data=request.data, context={"tenant": self.get_tenant()})
        serializer.is_valid(raise_exception=True)
        created = appointment_services.reschedule_appointment(
            appointment=self.get_object(),
            new_start=serializer.validated_data["start_at"],
            created_via="admin",
            actor_type=AppointmentActor.ADMIN,
            actor_id=str(request.user.pk),
        )
        return Response(AdminAppointmentDetailSerializer(created).data)


__all__ = (
    "AdminAppointmentViewSet",
    "BookingViewSet",
    "CustomerAppointmentViewSet",
)
