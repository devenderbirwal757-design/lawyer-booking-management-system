from __future__ import annotations

from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from common.exceptions import SlotUnavailableError
from common.viewset import BaseViewSet
from tests.testapp.models import Widget


class WidgetSerializer(serializers.ModelSerializer[Widget]):
    class Meta:
        model = Widget
        fields = ("id", "name", "tenant_id", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "tenant_id", "created_at", "updated_at")


class WidgetViewSet(BaseViewSet):
    """Exercises BaseViewSet against a real table, tenant scoping included."""

    # Tenant-scoped viewsets are the isolation boundary, so the class-level
    # queryset must not depend on a request context (it is built at import
    # time). `unfiltered()` is the escape hatch for that; TenantFilterMixin
    # re-applies the tenant on every request.
    queryset = Widget.objects.unfiltered()
    serializer_class = WidgetSerializer

    @action(detail=False, methods=["post"], url_path="conflict")
    def conflict(self, request: object) -> Response:
        raise SlotUnavailableError()
