from __future__ import annotations

from typing import Any

from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from common.idempotency import ActorStampMixin, IdempotencyMixin, RequestIdMixin
from common.mixins import TenantFilterMixin
from common.querysets import get_current_tenant

ModelT = Any


class TenantScopedViewSet(
    TenantFilterMixin,
    IdempotencyMixin,
    ActorStampMixin,
    RequestIdMixin,
    viewsets.GenericViewSet[ModelT],
):
    """Everything shared by every tenant-scoped endpoint.

    Provides tenant filtering, `Idempotency-Key` validation, actor stamping
    and soft delete, without deciding which HTTP verbs are exposed. Concrete
    viewsets compose the verbs they need on top of this.

    Concrete subclasses must declare their base queryset as
    `queryset = Model.objects.unfiltered()`: class attributes are evaluated
    at import time, when no tenant is bound yet, and `TenantFilterMixin`
    re-applies the tenant on every request.
    """

    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style

    def get_tenant(self) -> Any:
        # The middleware binds whatever it could resolve before DRF ran; for
        # JWT-authenticated requests that is at best the default tenant. Once
        # the view authenticates, the user's own tenant is authoritative - a
        # client cannot override it with a header (S §A4).
        user = getattr(self.request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            tenant = getattr(user, "tenant", None)
            if tenant is not None:
                return tenant
        return get_current_tenant()

    def initial(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        self.validate_idempotency_key()

    def get_serializer_context(self) -> dict[str, Any]:
        context: dict[str, Any] = dict(super().get_serializer_context())
        context["tenant"] = self.get_tenant()
        context["actor"] = self.get_actor()
        return context

    def perform_destroy(self, instance: Any) -> None:
        """Soft delete when the model supports it, hard delete otherwise.

        Rows referenced by appointments must never be hard deleted (plan §2).
        """
        if hasattr(instance, "is_active"):
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            return
        instance.delete()


class BaseViewSet(
    TenantScopedViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
):
    """Full CRUD for a tenant-scoped resource.

    The shared base comes first in the MRO on purpose: it owns the behaviour
    (`perform_destroy`, `initial`, `get_queryset`) that the verb mixins
    delegate to, so it must win over their defaults.
    """


class ReadOnlyModelViewSet(
    TenantScopedViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """Public catalogue endpoints (`GET /services`, `GET /providers/{id}`)."""
