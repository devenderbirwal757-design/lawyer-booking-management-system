"""Provider serializers (plan §4).

`PublicProviderSerializer` backs the public profile. `TenantProviderField` is
the shared submission rule for every serializer that lets an admin pick a
provider: the provider must belong to the request's tenant, or it is rejected
at field level - an admin can never point a rule at another practice's
provider.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.providers.models import Provider


class PublicProviderSerializer(serializers.ModelSerializer[Provider]):
    class Meta:
        model = Provider
        fields = ("id", "name", "email", "phone", "bio")
        read_only_fields = fields


class TenantProviderField(serializers.PrimaryKeyRelatedField[Provider]):
    """A provider PK, accepted only when the provider is in the tenant."""

    def __init__(self, **kwargs: Any) -> None:
        # `unfiltered()` because the field resolves providers for a tenant the
        # caller names, not whatever context is currently ambient.
        kwargs.setdefault("queryset", Provider.objects.unfiltered())
        super().__init__(**kwargs)

    def to_internal_value(self, data: Any) -> Provider:
        provider = super().to_internal_value(data)
        tenant = self.context.get("tenant")
        if tenant is not None and provider.tenant_id != getattr(tenant, "pk", tenant):
            self.fail("does_not_exist", pk_value=data)
        return provider


__all__ = ("PublicProviderSerializer", "TenantProviderField")
