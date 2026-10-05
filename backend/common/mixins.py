from __future__ import annotations

from typing import Any

from common.querysets import tenant_q


class TenantFilterMixin:
    """Force every queryset returned by a view into the current tenant.

    Viewsets inherit this instead of filtering by hand so a new endpoint
    cannot accidentally read across tenants (plan §12).

    A subclass that overrides `get_queryset()` must call `super()`, or the
    tenant filter this mixin applies is silently dropped and the endpoint reads
    the whole table. That mistake is invisible in review - the override looks
    like ordinary narrowing - so `tests/unit/test_tenant_queryset_guard.py`
    fails the build on it.

    The one legitimate reason not to call `super()` is a model with no `tenant`
    column, where `filter(tenant_id=...)` would raise `FieldError`. Such a
    class must scope itself and say why, in its own body:

        class AdminPaymentEventViewSet(...):
            tenant_queryset_override_reason = (
                "PaymentEvent has no tenant column; scoped through "
                "gateway_order_id, which is unique table-wide."
            )

    The attribute is read from the class's own `__dict__`, so the
    justification has to sit next to the override rather than be inherited
    from some ancestor that stopped needing it.
    """

    tenant_field = "tenant_id"

    #: Set to a non-empty explanation to override `get_queryset()` without
    #: calling `super()`. Enforced by the guard test; inherited as `None`.
    tenant_queryset_override_reason: str | None = None

    def get_tenant(self) -> Any:
        """The tenant resolving this request; overridden by viewsets."""
        return None

    def get_queryset(self) -> Any:
        qs = super().get_queryset()  # type: ignore[misc]
        tenant = self.get_tenant()
        if tenant is None:
            return qs.none()
        return qs.filter(**{self.tenant_field: getattr(tenant, "pk", tenant)})

    def get_tenant_filter(self) -> Any:
        return tenant_q(self.tenant_field, tenant=self.get_tenant())
