"""OpenAPI bearer-token schemes for the two custom authenticators.

drf-spectacular ships an extension for stock simplejwt's
`JWTAuthentication`, but not for our scoped subclasses
(`apps.accounts.authentication.AdminJWTAuthentication` and
`apps.auth_otp.authentication.CustomerJWTAuthentication`). Without these,
`schema` generation cannot annotate the auth header and `check --deploy`
reports `drf_spectacular.W001` for every view.

Both are HTTP bearer JWT schemes; the security plan draws no distinction
between them in the schema, only the tokens themselves carry the `scope`
claim. The module is imported from `apps.accounts.apps.ready()` so the
registry is populated before schema generation and system checks run.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class _BearerJWTScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    name = "bearerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class AdminJWTExtension(_BearerJWTScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.accounts.authentication.AdminJWTAuthentication"
    name = "bearerAuthAdmin"


class CustomerJWTExtension(_BearerJWTScheme):  # type: ignore[no-untyped-call]
    target_class = "apps.auth_otp.authentication.CustomerJWTAuthentication"
    name = "bearerAuthCustomer"


__all__ = ("AdminJWTExtension", "CustomerJWTExtension", "_BearerJWTScheme")
