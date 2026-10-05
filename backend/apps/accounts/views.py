"""Admin auth endpoints (plan §4).

`/auth/admin/*` is rate limited per IP *and* per email (S §A2), and every view
here is explicitly `AllowAny` with an explicit throttle, so the global DRF
defaults cannot accidentally make login open or closed.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    INVALID_CREDENTIALS,
    INVALID_REFRESH,
    AdminLoginSerializer,
    AdminLogoutSerializer,
    AdminRefreshSerializer,
    AdminUserSerializer,
)
from common.throttles import AdminLoginRateThrottle, LoginRateThrottle


@extend_schema(
    tags=["auth"],
    request=AdminLoginSerializer,
    responses={
        200: OpenApiResponse(description="access/refresh pair"),
        401: OpenApiResponse(description=INVALID_CREDENTIALS),
        429: OpenApiResponse(description="throttled"),
    },
)
class AdminLoginView(APIView):
    """`POST /auth/admin/login` - email + password to a JWT pair."""

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style
    throttle_classes: list[Any] = [AdminLoginRateThrottle, LoginRateThrottle]  # noqa: RUF012 - DRF's own style

    def post(self, request: Request) -> Response:
        serializer = AdminLoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        tokens = serializer.save()
        return Response(
            {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "user": AdminUserSerializer(serializer.validated_data["user"]).data,
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["auth"],
    request=AdminRefreshSerializer,
    responses={
        200: OpenApiResponse(description="rotated pair"),
        401: OpenApiResponse(description=INVALID_REFRESH),
    },
)
class AdminRefreshView(APIView):
    """`POST /auth/admin/refresh` - rotates, and detects replay."""

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style

    def post(self, request: Request) -> Response:
        serializer = AdminRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=status.HTTP_200_OK)


@extend_schema(
    tags=["auth"],
    request=AdminLogoutSerializer,
    responses={204: OpenApiResponse(description="revoked")},
)
class AdminLogoutView(APIView):
    """`POST /auth/admin/logout` - server-side revocation of the family."""

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style

    def post(self, request: Request) -> Response:
        serializer = AdminLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
