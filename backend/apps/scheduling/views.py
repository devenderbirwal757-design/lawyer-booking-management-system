"""Availability endpoints (plan §4, §A7).

Public:

- `GET /availability/slots?service_id=&date=YYYY-MM-DD`
- `GET /availability/dates?service_id=&month=YYYY-MM`

Both are unauthenticated but throttled (`AvailabilityRateThrottle`, S §A7) so
the full schedule cannot be scraped, and both resolve service and provider
strictly inside the request's tenant: no tenant context, no rows, 404.

Admin:

- `GET/POST/PATCH /admin/availability/rules`
- `GET/POST/DELETE /admin/availability/exceptions`

Rules have no DELETE on purpose (the plan's surface): deactivate a window by
editing it. Exceptions are transient one-offs - DELETE revokes them. Both are
isolated by `provider__tenant_id`, so touching another tenant's calendar is a
404, and an admin can never point a rule at another practice's provider.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appointments.services import active_windows
from apps.scheduling.models import AvailabilityException, AvailabilityRule
from apps.scheduling.serializers import (
    AvailabilityExceptionSerializer,
    AvailabilityRuleSerializer,
)
from apps.scheduling.service import SlotService
from apps.services.models import Service, ServiceStatus
from common.permissions import IsAdmin
from common.querysets import get_current_tenant
from common.throttles import AvailabilityRateThrottle
from common.viewset import BaseViewSet


def _engine_for(provider: Any, service: Any, zone: str, day: date) -> SlotService:
    """A live engine: supply that day's occupied spans (holds + confirmed
    bookings, buffer included) so the grid reflects real occupancy - which
    disables the brief cache, the correct trade for a ground-truth answer."""
    return SlotService(
        provider=provider,
        service=service,
        timezone=zone,
        busy=active_windows(provider, day=day, zone=zone),
    )


# ------------------------------------------------------------------ public
def _service_in_tenant(service_id: str, tenant: Any) -> Service | None:
    if tenant is None:
        return None
    return (
        Service.objects.for_tenant(tenant)
        .filter(pk=service_id, status=ServiceStatus.ACTIVE)
        .first()
    )


@extend_schema(
    tags=["availability"],
    parameters=[
        OpenApiParameter("service_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("date", OpenApiTypes.DATE, OpenApiParameter.QUERY, required=True),
    ],
    responses={
        200: OpenApiResponse(description="Bookable slot start times (ISO-8601) for the day"),
        400: OpenApiResponse(description="Missing or malformed parameters"),
        404: OpenApiResponse(description="Service not found in this tenant"),
    },
)
class SlotsView(APIView):
    permission_classes = [AllowAny]  # noqa: RUF012 - DRF's own style
    # Public and identity-free: the client browses slots *before* it has a
    # booking, and nothing here reads `request.user`. Authenticating would only
    # make a customer token (or a missing one) change the answer, so the
    # `AllowAny` promise is kept by not authenticating at all.
    authentication_classes: list[type[BaseAuthentication]] = []  # noqa: RUF012
    throttle_classes = [AvailabilityRateThrottle]  # noqa: RUF012 - DRF's own style

    def get(self, request: Any) -> Response:
        service_id = request.query_params.get("service_id")
        raw_date = request.query_params.get("date")
        if not service_id or not raw_date:
            return Response(
                _missing_params_error(),
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = _service_in_tenant(service_id, get_current_tenant())
        if service is None:
            raise Http404
        if service.provider_id is None:
            return Response(
                {
                    "error": {
                        "code": "service_unbookable",
                        "message": "This service is not assigned to a provider yet.",
                        "details": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            return Response(
                _bad_date_error(raw_date),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = get_current_tenant()
        zone = getattr(tenant, "timezone", None) or "UTC"
        slots = _engine_for(service.provider, service, zone, day).slots(day)
        return Response(
            {
                "date": day.isoformat(),
                "service_id": str(service.pk),
                "slots": [slot.isoformat() for slot in slots],
            }
        )


@extend_schema(
    tags=["availability"],
    parameters=[
        OpenApiParameter("service_id", OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
        OpenApiParameter("month", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True),
    ],
    responses={
        200: OpenApiResponse(description="Days in the month that have at least one slot"),
        400: OpenApiResponse(description="Missing or malformed parameters"),
        404: OpenApiResponse(description="Service not found in this tenant"),
    },
)
class AvailableDatesView(APIView):
    permission_classes = [AllowAny]  # noqa: RUF012 - DRF's own style
    # Same reasoning as `SlotsView`: a public calendar lookup, no principal.
    authentication_classes: list[type[BaseAuthentication]] = []  # noqa: RUF012
    throttle_classes = [AvailabilityRateThrottle]  # noqa: RUF012 - DRF's own style

    def get(self, request: Any) -> Response:
        service_id = request.query_params.get("service_id")
        raw_month = request.query_params.get("month")
        if not service_id or not raw_month:
            return Response(
                _missing_params_error(),
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = _service_in_tenant(service_id, get_current_tenant())
        if service is None:
            raise Http404
        if service.provider_id is None:
            return Response(
                {
                    "error": {
                        "code": "service_unbookable",
                        "message": "This service is not assigned to a provider yet.",
                        "details": None,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            month = datetime.strptime(raw_month, "%Y-%m").date().replace(day=1)
        except ValueError:
            return Response(
                _bad_date_error(raw_month),
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = get_current_tenant()
        zone = getattr(tenant, "timezone", None) or "UTC"
        dates: list[str] = []
        for offset in range(monthrange(month.year, month.month)[1]):
            day = month.replace(day=1 + offset)
            if _engine_for(service.provider, service, zone, day).slots(day):
                dates.append(day.isoformat())
        return Response({"month": raw_month, "service_id": str(service.pk), "dates": dates})


# ------------------------------------------------------------------- admin
class AdminAvailabilityRuleViewSet(BaseViewSet):
    queryset = AvailabilityRule.objects.unfiltered()
    serializer_class = AvailabilityRuleSerializer
    permission_classes = [IsAdmin]  # noqa: RUF012 - DRF's own style
    http_method_names = ["get", "post", "patch", "head", "options"]  # noqa: RUF012 - DRF
    tenant_field = "provider__tenant_id"


class AdminAvailabilityExceptionViewSet(BaseViewSet):
    queryset = AvailabilityException.objects.unfiltered()
    serializer_class = AvailabilityExceptionSerializer
    permission_classes = [IsAdmin]  # noqa: RUF012 - DRF's own style
    # The plan's surface for exceptions is GET/POST/DELETE: a one-off day is
    # revoked, not edited - revoke it and re-add it correctly.
    http_method_names = ["get", "post", "delete", "head", "options"]  # noqa: RUF012 - DRF
    tenant_field = "provider__tenant_id"

    def perform_destroy(self, instance: AvailabilityException) -> None:
        # Exceptions are transient one-offs; revoking one deletes it outright.
        instance.delete()


# ------------------------------------------------------------------ helpers
def _missing_params_error() -> dict[str, Any]:
    return {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": {"query": "service_id and date are required."},
        }
    }


def _bad_date_error(raw: str) -> dict[str, Any]:
    return {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": {"date": f'"{raw}" is not a valid date.'},
        }
    }


__all__ = (
    "AdminAvailabilityExceptionViewSet",
    "AdminAvailabilityRuleViewSet",
    "AvailableDatesView",
    "SlotsView",
)
