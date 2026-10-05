"""The `audit()` helper and `@audited` decorator (plan §1 Phase 1).

Contract: a business mutation calls `audit()` (or is wrapped in `@audited`)
inside the request/task that caused the mutation, so the actor, tenant and
request metadata are picked up from the context instead of being threaded
through every call site by hand. The plan §3 schema is
`tenant, actor_type, actor_id, action, entity_type, entity_id, before, after,
ip, user_agent, created_at`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from functools import wraps
from typing import Any

from django.db import models, transaction

from apps.audit.models import AuditLog
from common.querysets import get_current_actor, get_current_request, get_current_tenant

_SIMPLE = (str, int, float, bool, type(None))


def snapshot(obj: models.Model) -> dict[str, Any]:
    """Plain, JSON-safe dict of an instance's concrete field values.

    Used for the `before`/`after` columns. Only current field values are kept:
    reverse relations and M2M are deliberately excluded (they belong to a
    different entity and would bloat every row).
    """
    data: dict[str, Any] = {}
    for field in obj._meta.concrete_fields:
        data[field.name] = _to_audit_value(getattr(obj, field.name))
    return data


def _to_audit_value(value: Any) -> Any:
    if isinstance(value, _SIMPLE):
        return value
    if isinstance(value, models.Model):
        return str(value.pk)
    if isinstance(value, uuid.UUID | datetime | date | time | Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _to_audit_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_to_audit_value(item) for item in value]
    return str(value)


def _resolve_tenant(explicit: Any) -> Any:
    if explicit is not None:
        return explicit
    return get_current_tenant()


def _resolve_actor(explicit: Any) -> tuple[str, str]:
    """Return `(actor_type, actor_id)` for an explicit value or the context."""
    if explicit is not None:
        if isinstance(explicit, models.Model):
            return _actor_label(explicit), str(explicit.pk)
        return "user", str(explicit)
    actor = get_current_actor()
    if isinstance(actor, models.Model):
        return _actor_label(actor), str(actor.pk)
    if actor is not None:
        return "user", str(actor)
    return "", ""


def _actor_label(actor: models.Model) -> str:
    """The polymorphic `actor_type`: `accounts.User` -> `user`."""
    label = actor._meta.label_lower
    return label.split(".")[-1]


def _request_metadata() -> tuple[str | None, str]:
    request = get_current_request()
    if request is None:
        return None, ""
    ip = request.META.get("REMOTE_ADDR")
    return (ip or None), (request.META.get("HTTP_USER_AGENT") or "")[:256]


def audit(
    *,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | uuid.UUID | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    actor: Any = None,
    tenant: Any = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append one `AuditLog` row, resolving context from the request/task."""
    actor_type, actor_id = _resolve_actor(actor)
    request_ip, request_agent = _request_metadata()
    return AuditLog.objects.create(
        tenant=_resolve_tenant(tenant),
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type or "",
        entity_id=str(entity_id) if entity_id is not None else "",
        before=dict(before or {}),
        after=dict(after or {}),
        ip=ip if ip is not None else request_ip,
        user_agent=user_agent if user_agent is not None else request_agent,
    )


def audited(
    action: str,
    entity_type: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a mutating callable so a before/after audit row is appended.

    The first positional argument (when it is a model instance) is the
    `before` snapshot; the return value (again when it is a model instance) is
    the `after`. Explicit values win over inference:

        @audited(action="pricing.update", entity_type="service")
        def apply_discount(service: Service, percent: int) -> Service:
            service.price = ...
            service.save()
            return service

    The audit row is written in the same transaction as the mutation, so a
    failed audit write rolls the mutation back too - history is never
    optional.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # The audit row and the mutation are written in one transaction:
            # a failed audit write (or any exception) revokes the mutation, so
            # a world where a change happened but was never recorded cannot be
            # observed. Completed audit rows commit with the change.
            with transaction.atomic():
                candidate = args[0] if args else None
                before = snapshot(candidate) if isinstance(candidate, models.Model) else None

                result = fn(*args, **kwargs)

                target = result if isinstance(result, models.Model) else candidate
                after = snapshot(target) if isinstance(target, models.Model) else None
                resolved_type = entity_type or (
                    target._meta.label_lower if isinstance(target, models.Model) else None
                )
                resolved_id = (
                    getattr(target, "pk", None) if isinstance(target, models.Model) else None
                )

                audit(
                    action=action,
                    entity_type=resolved_type,
                    entity_id=resolved_id,
                    before=before,
                    after=after,
                )
            return result

        return wrapper

    return decorate


__all__ = ("AuditLog", "audit", "audited", "snapshot")
