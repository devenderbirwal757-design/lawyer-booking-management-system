from __future__ import annotations

import uuid
from typing import Any

from common.querysets import get_current_actor, new_request_id


class IdempotencyMixin:
    """Honour the `Idempotency-Key` header on unsafe methods (plan §5).

    A double-tapped "Book" button must not create two slot holds. The mixin
    resolves an existing object for the same key; Phase 5 adds the storage
    table and the replay window.
    """

    idempotency_header = "HTTP_IDEMPOTENCY_KEY"
    idempotency_field = "idempotency_key"

    def get_idempotency_key(self) -> str | None:
        raw = self.request.headers.get("Idempotency-Key")  # type: ignore[attr-defined]
        return raw.strip() if raw else None

    def validate_idempotency_key(self) -> None:
        key = self.get_idempotency_key()
        if key is None:
            return
        try:
            uuid.UUID(key)
        except ValueError as err:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"idempotency_key": "Must be a valid UUID."}) from err


class ActorStampMixin:
    """Stamp the acting principal onto writes (plan §2: `ActorStamp`)."""

    actor_fields: tuple[str, ...] = ()

    def get_actor(self) -> Any:
        actor = get_current_actor()
        if actor is not None:
            return actor
        user = getattr(self.request, "user", None)  # type: ignore[attr-defined]
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        return getattr(self.request, "customer", None)  # type: ignore[attr-defined]

    def stamp_actor(self, serializer: Any) -> Any:
        actor = self.get_actor()
        if actor is None:
            return serializer
        for field in self.actor_fields:
            if actor is not None and field in getattr(serializer, "fields", {}):
                serializer[field] = actor
        return serializer

    def perform_create(self, serializer: Any) -> None:
        serializer = self.stamp_actor(serializer)
        serializer.save()

    def perform_update(self, serializer: Any) -> None:
        serializer = self.stamp_actor(serializer)
        serializer.save()


class RequestIdMixin:
    def get_request_id(self) -> str:
        return getattr(
            self.request,  # type: ignore[attr-defined]
            "request_id",
            new_request_id(),
        )
