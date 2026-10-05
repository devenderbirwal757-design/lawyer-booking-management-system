"""Permissions for customer-scoped endpoints (plan §4, S §A3/A4).

`IsAuthenticatedCustomer` is what `/me/*` will use from Phase 5 on: it requires
a real, active customer loaded by `CustomerJWTAuthentication`. Because customer
tokens never survive plain `JWTAuthentication`, this permission is also the
guarantee that an admin token can never reach `/me/*`.

`IsAdminOrCustomer` backs the polymorphic `GET /auth/me`, which serves either
principal.
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission


class IsAuthenticatedCustomer(BasePermission):
    message = "Customer authentication is required."

    def has_permission(self, request: Any, view: Any) -> bool:
        customer = getattr(request, "customer", None)
        return bool(customer is not None and getattr(customer, "is_active", False))


class IsAdminOrCustomer(BasePermission):
    """Allow an authenticated admin (request.user) or customer."""

    def has_permission(self, request: Any, view: Any) -> bool:
        if IsAuthenticatedCustomer().has_permission(request, view):
            return True
        user = getattr(request, "user", None)
        return bool(user is not None and getattr(user, "is_authenticated", False))


__all__ = ("IsAdminOrCustomer", "IsAuthenticatedCustomer")
