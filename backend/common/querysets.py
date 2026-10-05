from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import models
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from common.exceptions import TenantContextMissing

_tenant: ContextVar[Any] = ContextVar("current_tenant", default=None)
_actor: ContextVar[Any] = ContextVar("current_actor", default=None)
_request: ContextVar[HttpRequest | None] = ContextVar("current_request", default=None)


# ------------------------------------------------------------------ tenant
def get_current_tenant() -> Any:
    """Return the Tenant bound to this request/task, or None."""
    return _tenant.get()


@contextmanager
def tenant_context(tenant: Any) -> Iterator[Any]:
    token = _tenant.set(tenant)
    try:
        yield tenant
    finally:
        _tenant.reset(token)


# ------------------------------------------------------------------ actor
def get_current_actor() -> Any:
    return _actor.get()


@contextmanager
def actor_context(actor: Any) -> Iterator[Any]:
    token = _actor.set(actor)
    try:
        yield actor
    finally:
        _actor.reset(token)


# ------------------------------------------------------------------ request
def get_current_request() -> HttpRequest | None:
    return _request.get()


def set_request(request: HttpRequest | None) -> None:
    _request.set(request)


def new_request_id() -> str:
    return uuid.uuid4().hex


# ------------------------------------------------------------------ querysets
class TenantScopedQuerySet[ModelT: models.Model](QuerySet[ModelT]):
    """QuerySet that refuses to leak across tenants.

    Plan §12 risk register: "Tenant leakage in a new endpoint -> Shared
    TenantScopedQuerySet; test that asserts 404 for cross-tenant access on
    every viewset."

    `for_tenant(None)` returns an empty queryset rather than everything, so a
    missing tenant context can never expose all rows. Note that `.none()` is
    sticky - a later `.filter()` cannot widen it - so this is only safe
    because `TenantScopedManager` refuses to build one implicitly.
    """

    tenant_field = "tenant_id"

    def for_tenant(self, tenant: Any) -> TenantScopedQuerySet[ModelT]:
        if tenant is None:
            return self.none()
        return self.filter(**self._tenant_filter(tenant))

    def active(self) -> TenantScopedQuerySet[ModelT]:
        return self.filter(is_active=True)

    @classmethod
    def _tenant_filter(cls, tenant: Any) -> dict[str, Any]:
        return {cls.tenant_field: getattr(tenant, "pk", tenant)}


class TenantScopedManager[ModelT: models.Model](models.Manager[ModelT]):
    """Manager whose reads are tenant-scoped and fail closed.

    With no tenant bound to the context, `get_queryset()` raises
    `TenantContextMissing` instead of returning every row. Reads are the leak
    vector, so they are guarded. Insert paths (`create`, `bulk_create`) are
    not: they touch exactly the rows the caller names, never someone else's,
    and requiring a context for them would break fixtures, management
    commands and Celery tasks. Read-modify-write helpers
    (    `get_or_create`, `update_or_create`) *do* read, so they stay guarded.

    `use_in_migrations` stays False (Django's default): serialising this
    dynamically-generated `from_queryset` manager would make every future
    migration unserialisable, and migrations never go through a request
    context anyway.

    **Custom tenant fields.** Rows of some models belong to a tenant only
    through a join (`AvailabilityRule.tenant == provider__tenant_id`); those
    models configure `tenant_field` on a `TenantScopedQuerySet` subclass and
    point this manager's `queryset_class` at it, and the isolation guarantee
    still holds.
    """

    use_in_migrations = False
    queryset_class: type[TenantScopedQuerySet[Any]] = TenantScopedQuerySet

    def get_queryset(self) -> TenantScopedQuerySet[ModelT]:
        tenant = get_current_tenant()
        if tenant is None:
            raise TenantContextMissing(
                f"{self.model.__name__} is tenant-scoped but no tenant is bound to this "
                f"context. Wrap the call in `tenant_context(...)`, or use "
                f"`{self.model.__name__}.objects.unfiltered()` outside a request/task."
            )
        return self.queryset_class(self.model, using=self._db).for_tenant(tenant)

    def for_tenant(self, tenant: Any) -> TenantScopedQuerySet[ModelT]:
        """Filter explicitly by tenant, valid even with no tenant in context."""
        return self.unfiltered().for_tenant(tenant)

    def unfiltered(self) -> TenantScopedQuerySet[ModelT]:
        """Escape hatch for management commands, Celery tasks and migrations.

        Every caller is a place where cross-tenant access is intentional and
        must be auditable; keep the surface small.
        """
        return self.queryset_class(self.model, using=self._db)

    def create(self, **kwargs: Any) -> ModelT:
        return self.unfiltered().create(**kwargs)

    def none(self) -> TenantScopedQuerySet[ModelT]:
        """Build an empty queryset. Never touches the database, so it is safe
        without a tenant - drf-spectacular calls this while generating the
        OpenAPI schema, where no request context exists."""
        return self.unfiltered().none()

    def bulk_create(
        self,
        objs: Iterable[ModelT],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list[ModelT]:
        return self.unfiltered().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


def tenant_q(field: str = "tenant_id", tenant: Any = None) -> Q:
    """Q object narrowing a queryset to the request's current tenant.

    Pass `tenant` explicitly when the caller has re-resolved it (e.g. a
    JWT-authenticated view's `get_tenant()`); otherwise the context-bound
    tenant is used.
    """
    if tenant is None:
        tenant = get_current_tenant()
    if tenant is None:
        return Q(pk__in=[])
    return Q(**{field: getattr(tenant, "pk", tenant)})
