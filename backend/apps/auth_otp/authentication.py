"""Customer JWT authentication (plan §4, S §A3).

`CustomerJWTAuthentication` decodes the same SimpleJWT bearer tokens admins
use, then *rejects anything that is not explicitly customer-scoped*:

- `scope != customer` (admin tokens, or tokens minted before Phase 4): returns
  None so a further authentication class (e.g. the admin `JWTAuthentication`
  on the polymorphic `/auth/me`) can run.
- `scope == customer` but the customer is missing or deactivated: InvalidToken
  (401) - an issued claim that no longer holds is an error, not a fallback.

The discovered customer is exposed as `request.customer`; `request.user` also
carries it so permissions/responders can rely on the DRF contract. Admin
endpoints use the global `AdminJWTAuthentication`, which rejects any token
whose `scope` claim is `customer` outright and answers 401 when a `user_id`
does not resolve to an admin user - so a customer token trying `/admin/*` is
turned away cleanly, never with a 500.
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings

from apps.auth_otp.tokens import CUSTOMER_SCOPE, SCOPE_CLAIM
from apps.customers.models import Customer


class CustomerJWTAuthentication(JWTAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        header = self.get_header(request)
        raw_token = self.get_raw_token(header) if header is not None else None
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)

        customer = self.get_user(validated_token)
        if customer is None:
            # Not a customer-scoped token: let the next auth class decide.
            return None
        request.customer = customer  # type: ignore[attr-defined]
        return (customer, validated_token)

    def get_user(self, validated_token: Any) -> Any:
        if validated_token.get(SCOPE_CLAIM) != CUSTOMER_SCOPE:
            return None
        user_id = validated_token.get(api_settings.USER_ID_CLAIM)
        try:
            customer = Customer.objects.unfiltered().get(pk=user_id, is_active=True)
        except Customer.DoesNotExist:
            raise AuthenticationFailed(
                "This session is no longer valid.",
                code="invalid_token",
            ) from None
        return customer


__all__ = ("CustomerJWTAuthentication",)
