"""Refresh-token family helpers for reuse detection (security.md §A2).

§A2 requires: "Refresh-token reuse detection invalidates the token family."

Rotation alone does not achieve that. simplejwt's blacklist makes a *spent*
token unusable, but if an attacker has stolen a copy of a refresh token they
can race the legitimate client: whichever presents it first gets a fresh pair,
and the loser's later replay looks like an ordinary transaction failure. The
whole family must die when a token is replayed.

Every refresh token carries a `family` claim (a `RefreshSession` primary key,
from `apps.accounts.models`). simplejwt's `OutstandingToken` table answers "is
this jti dead"; `RefreshSession` answers "which tokens came from this login".
`OutstandingToken` stores the encoded token, so the family claim has to be
decoded back out of it - that is all the helpers here do.
"""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework_simplejwt.tokens import UntypedToken

FAMILY_CLAIM = "family"


def family_of(encoded: str) -> str | None:
    """Read the `family` claim without verifying the signature.

    Signature verification is the caller's job; this only groups rows for a
    revocation that has already been authorised. A malformed token yields no
    family, which means it is simply not revoked with its family.
    """
    payload = _payload(encoded)
    family = payload.get(FAMILY_CLAIM)
    return str(family) if family else None


def jti_of(encoded: str) -> str | None:
    from rest_framework_simplejwt.settings import api_settings

    payload = _payload(encoded)
    jti = payload.get(api_settings.JTI_CLAIM)
    return str(jti) if jti else None


def _payload(encoded: str) -> dict[str, Any]:
    try:
        token = UntypedToken(encoded, verify=False)  # type: ignore[arg-type]
        return dict(token.payload)
    except Exception:
        return {}


def verified_signature(encoded: str) -> bool:
    """True when `encoded` carries a valid signature from this app's key.

    Used by logout: a session must only be revocable by a token we actually
    signed. Expiry is deliberately ignored - a user logging out with an
    already-expired refresh token still has the right to kill the family.
    """
    import jwt as pyjwt
    from rest_framework_simplejwt.settings import api_settings

    key: Any = api_settings.SIGNING_KEY
    if not api_settings.ALGORITHM.startswith("HS"):
        key = api_settings.VERIFYING_KEY

    try:
        payload = pyjwt.decode(
            encoded,
            key,
            algorithms=[api_settings.ALGORITHM],
            audience=api_settings.AUDIENCE,
            issuer=api_settings.ISSUER,
            options={"verify_exp": False},
        )
    except Exception:
        return False
    return payload.get("token_type") in ("access", "refresh")


def revoke_family(
    user_id: Any,
    family_id: uuid.UUID | Any,
) -> int:
    """Blacklist every outstanding refresh token carrying the family claim.

    Returns the number of tokens blacklisted. Idempotent: already-blacklisted
    tokens are skipped and can never be un-blacklisted, so a concurrent replay
    cannot double-count or resurrect anything.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    revoked = 0
    rows = OutstandingToken.objects.filter(user_id=user_id).only("id", "token").iterator()
    for row in rows:
        if family_of(row.token) != str(family_id):
            continue
        jti = jti_of(row.token)
        if not jti:
            continue
        if BlacklistedToken.objects.filter(token_id=row.pk).exists():
            continue
        BlacklistedToken.objects.create(token_id=row.pk)
        revoked += 1
    return revoked
