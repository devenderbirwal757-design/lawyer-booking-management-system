"""Customer OTP auth endpoints + the polymorphic `/auth/me` (plan §4, S §A3).

- `POST /auth/otp/request` - `{ phone }`. Unauthenticated, throttled. Always
  answers `{"ok": true}` whether or not the number is known, so it cannot
  enumerate customers. Resolves the tenant from the request context; no tenant
  context, no OTP, 404.
- `POST /auth/otp/verify` - `{ phone, code, name?, email? }`. Unauthenticated,
  throttled. Returns a customer-scoped JWT pair + the (auto-provisioned)
  profile. Any code failure parses to the same 400 `invalid_otp`.
- `GET /auth/me` - polymorphic: an admin bearer token gets the admin profile,
  a customer token gets the customer profile, and the two principals can never
  cross (S §A3 "an admin token cannot be used on /me/* and vice versa").
"""

from __future__ import annotations

from typing import Any

from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.serializers import AdminUserSerializer
from apps.auth_otp import services
from apps.auth_otp.authentication import CustomerJWTAuthentication
from apps.auth_otp.permissions import IsAdminOrCustomer
from apps.auth_otp.serializers import (
    CustomerProfileSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
)
from common.querysets import get_current_tenant
from common.throttles import OtpRequestRateThrottle, OtpVerifyRateThrottle


def _request_tenant() -> Any:
    tenant = get_current_tenant()
    if tenant is None:
        raise Http404
    return tenant


@extend_schema(
    tags=["auth"],
    request=OtpRequestSerializer,
    responses={
        200: OpenApiResponse(description='{"ok": true} - identical for known and unknown numbers'),
        400: OpenApiResponse(description="Invalid phone number"),
        404: OpenApiResponse(description="No tenant context"),
        429: OpenApiResponse(description="throttled (send window or rate limit)"),
    },
)
class OtpRequestView(APIView):
    """`POST /auth/otp/request` - send a one-time code to a phone."""

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style
    throttle_classes: list[Any] = [OtpRequestRateThrottle]  # noqa: RUF012 - DRF's own style

    def post(self, request: Request) -> Response:
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = _request_tenant()
        services.request_otp(tenant, serializer.validated_data["phone"])
        return Response({"ok": True}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["auth"],
    request=OtpVerifySerializer,
    responses={
        200: OpenApiResponse(description="customer JWT pair + profile"),
        400: OpenApiResponse(description="invalid_otp or validation_error"),
        404: OpenApiResponse(description="No tenant context"),
        429: OpenApiResponse(description="throttled"),
    },
)
class OtpVerifyView(APIView):
    """`POST /auth/otp/verify` - exchange a code for a customer JWT pair."""

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style
    throttle_classes: list[Any] = [OtpVerifyRateThrottle]  # noqa: RUF012 - DRF's own style

    def post(self, request: Request) -> Response:
        serializer = OtpVerifySerializer(data=request.data, context={"tenant": _request_tenant()})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "access": result["access"],
                "refresh": result["refresh"],
                "customer": CustomerProfileSerializer(result["customer"]).data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["auth"],
    responses={
        200: OpenApiResponse(description="admin or customer profile, whichever the token is"),
        401: OpenApiResponse(description="unauthenticated"),
    },
)
class MeView(APIView):
    """`GET /auth/me` - the profile of whoever holds a valid token."""

    authentication_classes: list[Any] = [  # noqa: RUF012 - DRF's own style
        CustomerJWTAuthentication,
        JWTAuthentication,
    ]
    permission_classes: list[Any] = [IsAdminOrCustomer]  # noqa: RUF012 - DRF's own style
    throttle_classes: list[Any] = []  # noqa: RUF012 - DRF's own style

    def get(self, request: Request) -> Response:
        customer = getattr(request, "customer", None)
        if customer is not None:
            return Response(
                CustomerProfileSerializer(customer).data,
                status=status.HTTP_200_OK,
            )
        user: Any = request.user
        return Response(AdminUserSerializer(user).data, status=status.HTTP_200_OK)


__all__ = ("MeView", "OtpRequestView", "OtpVerifyView")
