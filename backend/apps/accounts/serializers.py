"""Admin authentication: login, refresh, logout, me (plan §4, S §A2).

Three rules shape this file, all from S §A2:

- **No user enumeration.** One generic message for "no such email", "wrong
  password" and "inactive account", otherwise the response is a free
  account-existence oracle.
- **Reuse detection.** simplejwt's blacklist already stops a *spent* refresh
  token from being exchanged twice, but it does not stop the winner of a race
  from continuing: if a copy of a refresh token is stolen, whichever of the
  attacker and the real client presents it first gets a fresh pair, and the
  loser's later replay looks like an ordinary failure. This module treats any
  replay of an already-blacklisted token as proof of compromise and revokes
  the whole *family*, so a stolen token is worth at most one exchange.
- **Short-lived access, revocable refresh.** Access tokens last minutes;
  logout kills the family server-side rather than relying on expiry.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

from apps.accounts.models import RefreshSession, User
from apps.accounts.tokens import FAMILY_CLAIM, verified_signature

#: One message for every credential failure, so the response cannot be used to
#: enumerate accounts (S §A2 "Login error message does not reveal whether the
#: email exists").
INVALID_CREDENTIALS = "Incorrect email or password."
#: Used for every refresh failure, so a token's state is not observable either.
INVALID_REFRESH = "This session is no longer valid. Please sign in again."


class _UnblacklistedRefreshToken(RefreshToken):
    """`RefreshToken` whose blacklist check is skipped.

    The caller has already inspected the blacklist itself, because it needs to
    distinguish "replayed" (revoke the family) from "expired or forged" (do
    not). Letting `verify()` raise first would collapse both into one error.
    """

    def check_blacklist(self) -> None:
        return None


class AdminLoginSerializer(serializers.Serializer[dict[str, Any]]):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = authenticate(
            self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if user is None or not user.is_active:
            raise AuthenticationFailed(INVALID_CREDENTIALS, code="invalid_credentials")
        if not user.is_tenant_admin:
            # Covers role VIEWER/STAFF, and tenantless non-superusers.
            raise AuthenticationFailed(
                "This account cannot use the admin API.",
                code="forbidden",
            )
        return {"user": user}

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return issue_token_pair(validated_data["user"])


class AdminRefreshSerializer(serializers.Serializer[dict[str, Any]]):
    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        raw = attrs["refresh"]
        claims = _read_claims(raw)
        family_id = claims.get(FAMILY_CLAIM)
        jti = claims.get(api_settings.JTI_CLAIM)
        if not family_id or not jti:
            raise AuthenticationFailed(INVALID_REFRESH, code="invalid_token")

        session = RefreshSession.objects.filter(pk=family_id).first()
        if session is None or not session.is_active:
            # Unknown family, or already revoked by an earlier replay.
            raise AuthenticationFailed(INVALID_REFRESH, code="invalid_token")

        if BlacklistedToken.objects.filter(token__jti=str(jti)).exists():
            # The signature was not even checked yet, and that is deliberate:
            # a replay is only meaningful for a token we actually issued, and
            # the family is keyed on a jti we minted.
            session.revoke("reuse_detected")
            raise AuthenticationFailed(INVALID_REFRESH, code="token_reused")

        try:
            token = _UnblacklistedRefreshToken(raw)
        except Exception as err:
            # Expired, bad signature, wrong algorithm: not evidence of theft,
            # so the family is left alone.
            raise AuthenticationFailed(INVALID_REFRESH, code="invalid_token") from err

        user = get_user_model().objects.filter(pk=token[api_settings.USER_ID_CLAIM]).first()
        if user is None or not user.is_active or not user.is_tenant_admin:
            # Deactivated or demoted after the token was issued. Kill the
            # family rather than mint an access token from a stale claim.
            session.revoke("user_no_longer_privileged")
            raise AuthenticationFailed(INVALID_REFRESH, code="invalid_token")

        return {"session": session, "user": user, "token": token}

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        session = validated_data["session"]
        user = validated_data["user"]
        token = validated_data["token"]

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    token.blacklist()
                except AttributeError:  # pragma: no cover - blacklist app absent
                    pass
            token.set_jti()
            token.set_exp()
            token.set_iat()
            token.outstand()

        access = token.access_token
        access["role"] = user.role
        access["tenant"] = str(user.tenant_id)

        return {
            "access": str(access),
            "refresh": str(token),
            "session": str(session.pk),
        }


class AdminLogoutSerializer(serializers.Serializer[dict[str, Any]]):
    """Blacklist the presented refresh token and revoke its family."""

    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        raw = attrs["refresh"]
        claims = _read_claims(raw)
        if not verified_signature(raw):
            # Not signed by us: nothing to revoke, and the response stays
            # identical so logout cannot probe whether a token is real.
            return {}
        family_id = claims.get(FAMILY_CLAIM)
        if family_id:
            session = RefreshSession.objects.filter(pk=family_id).first()
            if session is not None:
                session.revoke("logout")
        return {}

    def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {}


class AdminUserSerializer(serializers.ModelSerializer[User]):
    """The admin's own profile, for `GET /auth/me`."""

    tenant = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "role",
            "is_active",
            "is_staff",
            "date_joined",
            "tenant",
        )
        read_only_fields = fields

    def get_tenant(self, obj: Any) -> dict[str, Any] | None:
        tenant = getattr(obj, "tenant", None)
        return tenant.as_dict() if tenant is not None else None


def _read_claims(raw: str) -> dict[str, Any]:
    """Decode without verifying, to read the family and jti claims.

    Nothing is granted from this: it only identifies which session to revoke.
    Revoking on a forged `family` claim is harmless (it can only revoke a
    family the forger already knows the id of, and they could revoke their own
    login by logging out anyway).
    """
    try:
        token = UntypedToken(raw, verify=False)  # type: ignore[arg-type]
        return dict(token.payload)
    except Exception:
        return {}


def issue_token_pair(user: Any) -> dict[str, Any]:
    """Mint an access + refresh pair bound to a new refresh family.

    `role` and `tenant` ride along in the access token so `IsAdmin` does not
    need a database hit per request. Both are re-checked against the user row
    on every refresh, so a demotion or tenant change takes effect at the
    victim's next refresh rather than at token expiry.
    """
    session = RefreshSession.objects.create(user=user, tenant_id=user.tenant_id)

    refresh = RefreshToken.for_user(user)
    refresh[FAMILY_CLAIM] = str(session.pk)
    # `for_user` stored the OutstandingToken row *before* the family claim was
    # added, and `RefreshSession.revoke` reads the claim off that stored
    # string, so the row has to be rewritten.
    OutstandingToken.objects.filter(jti=refresh[api_settings.JTI_CLAIM]).update(token=str(refresh))

    access = refresh.access_token
    access[FAMILY_CLAIM] = str(session.pk)
    access["role"] = user.role
    access["tenant"] = str(user.tenant_id)

    return {
        "access": str(access),
        "refresh": str(refresh),
        "session": str(session.pk),
    }


__all__ = (
    "INVALID_CREDENTIALS",
    "INVALID_REFRESH",
    "AdminLoginSerializer",
    "AdminLogoutSerializer",
    "AdminRefreshSerializer",
    "AdminUserSerializer",
    "issue_token_pair",
)
