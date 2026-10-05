from __future__ import annotations

from typing import Any

from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.querysets import get_current_tenant


class IsAdmin(BasePermission):
    """Access to `/admin/*` endpoints (plan §8, S §A2).

    A user is an admin when `User.is_tenant_admin`: OWNER/ADMIN role within
    their tenant, or a superuser as break-glass. `is_staff` alone is not
    enough - it gates Django's `django.contrib.admin`, and one must be
    independently revocable from API access (S §A4). Customers authenticate as
    a separate principal (`request.customer`) and never satisfy this check.
    """

    message = "Administrator access is required."

    def has_permission(self, request: Any, view: Any) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return bool(getattr(user, "is_tenant_admin", False))

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        return self.has_permission(request, view)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return IsAdmin().has_permission(request, view)


class IsAuthenticatedAdmin(IsAdmin):
    """Alias kept for readability at call sites."""


class IsCustomer(BasePermission):
    """Access to the customer's own endpoints (plan §8, S §A4).

    Satisfied only by a customer-scoped session: `CustomerJWTAuthentication`
    sets `request.customer`, and admins never do. Ownership of individual rows
    is enforced separately by each view resolving through
    `Appointment.objects.filter(customer=request.customer)`, so a customer
    reaches only their own bookings (S §A4 IDOR -> 404).
    """

    message = "A customer session is required."

    def has_permission(self, request: Any, view: Any) -> bool:
        return getattr(request, "customer", None) is not None

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        return self.has_permission(request, view)


class IsTenantMember(BasePermission):
    """Deny anything that does not belong to the request's current tenant."""

    message = "Cross-tenant access is not allowed."

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        tenant = get_current_tenant()
        if tenant is None:
            return False
        obj_tenant = getattr(obj, "tenant_id", None)
        if obj_tenant is None:
            return True
        return bool(obj_tenant == getattr(tenant, "pk", tenant))
