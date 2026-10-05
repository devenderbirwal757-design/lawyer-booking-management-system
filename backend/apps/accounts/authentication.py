"""Admin JWT authentication (plan §4, S §A3).

The global default is this class rather than stock simplejwt. It keeps the
admin contract and adds the two-scope guard:

- A token that explicitly claims `scope: "customer"` is rejected outright, so
  a customer session can never be accepted by an admin endpoint even if the
  underlying `USER_ID_CLAIM` ever collided.
- A token whose `user_id` does not resolve to an admin user is answered 401
  instead of surfacing a `ValueError` (customer ids are UUIDs, admin ids are
  integers) — an out-of-place token is an authentication failure, never a 500.

Tokens minted by the admin login carry no `scope` claim at all, so they are
unaffected; this only ever adds rejections, never new acceptances.
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.auth_otp.tokens import CUSTOMER_SCOPE, SCOPE_CLAIM


class AdminJWTAuthentication(JWTAuthentication):
    keyword = "Bearer"

    def get_user(self, validated_token: Any) -> Any:
        if validated_token.get(SCOPE_CLAIM) == CUSTOMER_SCOPE:
            raise AuthenticationFailed(
                "This session does not have access to admin endpoints.",
                code="invalid_token",
            )
        try:
            user = super().get_user(validated_token)
        except (TypeError, ValueError):
            raise AuthenticationFailed(
                "This session is no longer valid.",
                code="invalid_token",
            ) from None
        return user


__all__ = ("AdminJWTAuthentication",)
