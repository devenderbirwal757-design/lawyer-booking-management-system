"""Service endpoints (plan §4, S §A8).

Two surfaces, one model:

- `ServiceViewSet` is the public, unauthenticated catalogue. It can only ever
  return `ACTIVE` rows of the request's tenant, and a `status` query param
  cannot widen that - `?status=inactive` returns an empty result, never the
  hidden rows.
- `AdminServiceViewSet` is the tenant-admin CRUD. Unlike the shared base it
  soft-deletes via `status = DELETED` rather than touching `is_active`
  (services carry no `is_active` field; plan §2 "soft-delete via status"),
  and it never hard-deletes.
"""

from __future__ import annotations

from typing import Any

from apps.services.models import Service, ServiceStatus
from apps.services.permissions import CanEditService
from apps.services.serializers import AdminServiceSerializer, PublicServiceSerializer
from common.viewset import BaseViewSet, ReadOnlyModelViewSet


class ServiceViewSet(ReadOnlyModelViewSet):
    """Public catalogue: `GET /services` and `GET /services/{slug}`."""

    queryset = Service.objects.unfiltered()
    serializer_class = PublicServiceSerializer
    lookup_field = "slug"
    lookup_value_regex = r"[-a-zA-Z0-9]+"

    def get_queryset(self) -> Any:
        qs = super().get_queryset().filter(status=ServiceStatus.ACTIVE)
        requested = (self.request.query_params.get("status") or "").upper()
        if requested and requested != ServiceStatus.ACTIVE:
            # Refuse to turn a loose status filter into a leak.
            return qs.none()
        return qs


class AdminServiceViewSet(BaseViewSet):
    """Admin CRUD for the tenant's catalogue (`/admin/services`)."""

    queryset = Service.objects.unfiltered()
    serializer_class = AdminServiceSerializer
    permission_classes = [CanEditService]  # noqa: RUF012 - DRF's own style

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        requested = (self.request.query_params.get("status") or "").upper()
        if requested == ServiceStatus.DELETED:
            return qs.filter(status=ServiceStatus.DELETED)
        if requested in ServiceStatus.values:
            return qs.filter(status=requested)
        if requested == "ALL":
            return qs
        # Soft-deleted rows are management's past, not the working list.
        return qs.exclude(status=ServiceStatus.DELETED)

    def perform_destroy(self, instance: Service) -> None:
        """Soft-delete via status; the row must survive for the audit trail."""
        if instance.status != ServiceStatus.DELETED:
            instance.status = ServiceStatus.DELETED
            instance.save(update_fields=["status", "updated_at"])


__all__ = ("AdminServiceViewSet", "ServiceViewSet")
