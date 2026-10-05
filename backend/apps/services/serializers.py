"""Service serializers (plan §4).

Two contracts share one model:

- `PublicServiceSerializer` (read-only) backs the unauthenticated catalogue,
  so it can only ever expose `ACTIVE` rows and every field is read-only.
- `AdminServiceSerializer` backs the `/admin/services` CRUD. `tenant_id` is
  read-only here too: the tenant comes from the authenticated principal, never
  from the payload (S §A4 "`tenant_id` ... cannot be set by a client"). `slug`
  is auto-generated when blank; `DELETED` is not a writeable status, so the
  only path to it is the DELETE verb.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.providers.serializers import TenantProviderField
from apps.services.models import Service, ServiceStatus
from common.money import format_price

_PUBLIC_FIELDS = (
    "id",
    "slug",
    "name",
    "description",
    "duration_minutes",
    "buffer_before_minutes",
    "buffer_after_minutes",
    "price_amount",
    "price",
    "currency",
    "requires_payment",
)


class PublicServiceSerializer(serializers.ModelSerializer[Service]):
    price = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = _PUBLIC_FIELDS
        read_only_fields = _PUBLIC_FIELDS

    def get_price(self, obj: Service) -> str:
        return format_price(obj.price_amount, obj.currency)


class AdminServiceSerializer(serializers.ModelSerializer[Service]):
    price = serializers.SerializerMethodField()
    slug = serializers.SlugField(max_length=100, required=False, allow_blank=True)
    provider = TenantProviderField(required=False, allow_null=True)

    class Meta:
        model = Service
        fields = (
            "id",
            "tenant_id",
            "name",
            "slug",
            "description",
            "provider",
            "duration_minutes",
            "buffer_before_minutes",
            "buffer_after_minutes",
            "price_amount",
            "price",
            "currency",
            "status",
            "requires_payment",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "tenant_id", "price", "created_at", "updated_at")

    def get_price(self, obj: Service) -> str:
        return format_price(obj.price_amount, obj.currency)

    def _tenant(self) -> Any:
        tenant = self.context.get("tenant")
        if tenant is not None:
            return tenant
        instance = getattr(self, "instance", None)
        return getattr(instance, "tenant", None) if instance is not None else None

    def validate_currency(self, value: str) -> str:
        tenant = self._tenant()
        if tenant is not None and value.upper() not in (tenant.available_currencies() or []):
            raise serializers.ValidationError("The tenant does not charge in this currency.")
        return value.upper()

    def validate_slug(self, value: str) -> str | None:
        value = (value or "").strip()
        if not value:
            # Blank on create means auto-generate; on update it means "keep".
            return None if self.instance is None else self.instance.slug
        tenant = self._tenant()
        if tenant is not None:
            dupes = Service.objects.unfiltered().filter(tenant=tenant, slug=value)
            if self.instance is not None:
                dupes = dupes.exclude(pk=self.instance.pk)
            if dupes.exists():
                raise serializers.ValidationError(
                    "A service with this slug already exists in your practice."
                )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        requested = attrs.get("status")
        if requested == ServiceStatus.DELETED:
            raise serializers.ValidationError(
                {"status": "Use DELETE to remove a service; status cannot be set directly."}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Service:
        tenant = self.context.get("tenant")
        if tenant is None:
            # The view always injects its resolved tenant; this is the fail-fast
            # guard for any caller that forgot to.
            raise serializers.ValidationError({"tenant": "No tenant context for this request."})
        validated_data["tenant"] = tenant
        if not validated_data.get("slug"):
            validated_data["slug"] = Service.make_slug(tenant, validated_data["name"])
        return super().create(validated_data)


__all__ = ("AdminServiceSerializer", "PublicServiceSerializer")
