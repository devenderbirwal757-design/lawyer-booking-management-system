"""Public provider catalogue (plan §4 `GET /providers/{id}`)."""

from __future__ import annotations

from typing import Any

from apps.providers.models import Provider
from apps.providers.serializers import PublicProviderSerializer
from common.viewset import ReadOnlyModelViewSet


class ProviderViewSet(ReadOnlyModelViewSet):
    """Public provider profile; only active providers of the request's tenant."""

    queryset = Provider.objects.unfiltered()
    serializer_class = PublicProviderSerializer

    def get_queryset(self) -> Any:
        return super().get_queryset().filter(is_active=True)


__all__ = ("ProviderViewSet",)
