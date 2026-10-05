"""Request/response serializers for the OTP flow (plan §4).

Three contracts:

- `OtpRequestSerializer` ({phone}) validates the phone into canonical E.164 so
  the send-window counters and the channel are always fed a normalized number.
- `OtpVerifySerializer` ({phone, code, name?, email?}) - `create()` runs the
  verify service and returns the token pair + created customer. It raises the
  flow's domain errors directly, which the shared exception handler turns into
  the single error envelope.
- `CustomerProfileSerializer` backs `GET /auth/me` for the customer side: a
  whitelisted, read-only view of the customer's own row (never `tenant_id`,
  never `notes`, per S §A4 "public/exposed endpoints expose only whitelisted
  fields").
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import serializers

from apps.auth_otp.services import verify_otp
from apps.customers.models import Customer
from apps.customers.phone import PhoneValidationError, normalize_phone


def validated_phone(value: str) -> str:
    try:
        return normalize_phone(value)
    except PhoneValidationError as err:
        raise serializers.ValidationError(str(err)) from err


class OtpRequestSerializer(serializers.Serializer[dict[str, Any]]):
    phone = serializers.CharField(write_only=True)

    def validate_phone(self, value: str) -> str:
        return validated_phone(value)

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"phone": validated_data["phone"]}


class OtpVerifySerializer(serializers.Serializer[dict[str, Any]]):
    phone = serializers.CharField(write_only=True)
    code = serializers.CharField(write_only=True, min_length=4, max_length=8)
    name = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=200)
    email = serializers.EmailField(
        write_only=True, required=False, allow_blank=True, max_length=254
    )

    def validate_phone(self, value: str) -> str:
        return validated_phone(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        tenant = self.context.get("tenant")
        if tenant is None:
            raise serializers.ValidationError({"detail": "No tenant context for this request."})
        result = verify_otp(
            tenant,
            attrs["phone"],
            attrs["code"],
            now=timezone.now(),
            name=attrs.get("name"),
            email=attrs.get("email"),
        )
        attrs.update(result)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "access": validated_data["access"],
            "refresh": validated_data["refresh"],
            "customer": validated_data["customer"],
        }


class CustomerProfileSerializer(serializers.ModelSerializer[Customer]):
    class Meta:
        model = Customer
        fields = ("id", "phone", "name", "email", "is_active", "created_at")
        read_only_fields = fields


__all__ = (
    "CustomerProfileSerializer",
    "OtpRequestSerializer",
    "OtpVerifySerializer",
)
