"""Customer JWT issuance (plan §4, S §A3).

Customers are a separate principal from admins, and the separation must be
*in the token*: an access token that cannot tell "admin" from "customer" would
let a customer token masquerade on admin endpoints (and vice versa). Every
customer token therefore carries `scope: "customer"`.

Building the pair on a bare `RefreshToken()` keeps customers off
simplejwt's admin token machinery entirely - no `RefreshSession`, no blacklist,
no `OutstandingToken` rows tied to `AUTH_USER_MODEL`. Phase 4 issues the pair;
a customer refresh/logout endpoint is not in the plan's auth surface and is
added with the booking flow.
"""

from __future__ import annotations

from typing import Any

from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

SCOPE_CLAIM = "scope"
CUSTOMER_SCOPE = "customer"


def issue_customer_token_pair(customer: Any) -> dict[str, Any]:
    """Mint an access + refresh pair whose claims are scoped to `customer`."""
    refresh = RefreshToken()
    refresh[SCOPE_CLAIM] = CUSTOMER_SCOPE
    refresh[api_settings.USER_ID_CLAIM] = str(customer.pk)

    access = refresh.access_token
    access[SCOPE_CLAIM] = CUSTOMER_SCOPE
    access["tenant"] = str(customer.tenant_id)

    return {
        "access": str(access),
        "refresh": str(refresh),
        "customer_id": str(customer.pk),
    }


__all__ = ("CUSTOMER_SCOPE", "SCOPE_CLAIM", "issue_customer_token_pair")
