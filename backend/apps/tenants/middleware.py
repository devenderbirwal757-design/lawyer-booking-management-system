"""Resolve the request's tenant and bind it to the context (plan §2, S §A4).

Order of precedence, most trustworthy first:

1. **The authenticated principal.** A JWT is issued for a user who belongs to
   one tenant, so `request.user.tenant` is authoritative. A client cannot
   reach another tenant by changing a header, a cookie or the hostname.
2. **Host subdomain** (`alice.lawyer.test`) for unauthenticated traffic, which
   is how a public booking page addresses the practice.
3. **An explicitly configured default tenant**, for single-tenant installs
   served from a bare domain (the V1 case, PRD §32).
4. **Nothing.** No tenant is bound and tenant-scoped reads raise
   `TenantContextMissing` rather than returning another tenant's rows.

Only a *suspended* tenant is rejected, and with a 404 rather than a 403 so
the response does not confirm that a slug exists.

JWT requests are a special case: DRF authenticates inside the view, after
middleware has run, so `request.user` is anonymous here even for a valid
token. `common.viewset.TenantScopedViewSet.get_tenant()` re-resolves from the
authenticated user for those requests; see the note there.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.tenants.models import Tenant
from common.querysets import tenant_context

logger: Any = structlog.get_logger("apps.tenants.middleware")

TENANT_HEADER = "HTTP_X_TENANT_SLUG"
#: Hosts whose leftmost label is a routing artefact, not a tenant slug.
RESERVED_SUBDOMAINS = frozenset({"www", "api", "app", "admin"})


def _error_response(message: str, status: int) -> HttpResponse:
    body = {"error": {"code": "tenant_unavailable", "message": message, "details": None}}
    return HttpResponse(json.dumps(body), status=status, content_type="application/json")


def slug_from_host(host: str | None) -> str | None:
    """Return the leftmost host label when it could be a tenant slug."""
    if not host:
        return None
    labels = host.split(":")[0].lower().split(".")
    if len(labels) < 3:
        return None
    candidate = labels[0]
    if candidate in RESERVED_SUBDOMAINS:
        return None
    return candidate


def tenant_for_user(user: Any) -> Any:
    """The tenant a principal belongs to, or None.

    Shared by the middleware and the viewset so both agree on what "the user's
    tenant" means.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "tenant", None)


class TenantMiddleware:
    """Bind `get_current_tenant()` for the duration of the request."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        self.default_slug: str | None = getattr(settings, "DEFAULT_TENANT_SLUG", None)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        tenant, error = self.resolve(request)
        if error is not None:
            return error
        if tenant is None:
            # Nothing to bind. Tenant-scoped reads raise rather than leak.
            return self.get_response(request)  # type: ignore[no-any-return]
        with tenant_context(tenant):
            request.tenant = tenant  # type: ignore[attr-defined]
            return self.get_response(request)  # type: ignore[no-any-return]

    def resolve(self, request: HttpRequest) -> tuple[Any, HttpResponse | None]:
        """Return `(tenant, error_response)`; exactly one is not None."""
        user_tenant = tenant_for_user(getattr(request, "user", None))
        if user_tenant is not None:
            return self._require_active(user_tenant, request)
        if getattr(request, "user", None) is not None and getattr(
            getattr(request, "user", None), "is_authenticated", False
        ):
            # Authenticated but tenantless. Refuse rather than fall back to a
            # default, or this user would silently inherit a practice's data.
            logger.warning("authenticated_user_without_tenant", path=request.path)
            return None, _error_response("Your account is not attached to a practice.", 403)

        slug = request.META.get(TENANT_HEADER) or slug_from_host(request.get_host())
        if not slug and self.default_slug:
            slug = self.default_slug
        if not slug:
            return None, None

        try:
            tenant = Tenant.objects.get(slug=slug.strip().lower())
        except Tenant.DoesNotExist:
            logger.info("tenant_not_found", tenant_slug=slug, path=request.path)
            return None, _error_response("Unknown practice.", 404)
        return self._require_active(tenant, request)

    def _require_active(self, tenant: Any, request: HttpRequest) -> tuple[Any, HttpResponse | None]:
        if tenant.is_active:
            return tenant, None
        logger.info("tenant_suspended", tenant_slug=tenant.slug, path=request.path)
        return None, _error_response("This practice is not accepting bookings right now.", 404)


@contextmanager
def tenant_for_task(tenant_id: uuid.UUID | str) -> Iterator[Any]:
    """Bind a tenant for a Celery task, which has no request to read it from.

    A task that carries a tenant id in its arguments should use this. One that
    does not must call `Model.objects.unfiltered()` and say why in a comment:
    there is no ambient context to fall back on, and a silent cross-tenant
    read in a background job is exactly the failure S §A4 is about.
    """
    tenant = Tenant.objects.get(pk=tenant_id)
    with tenant_context(tenant):
        yield tenant


__all__ = (
    "RESERVED_SUBDOMAINS",
    "TENANT_HEADER",
    "TenantMiddleware",
    "slug_from_host",
    "tenant_for_task",
    "tenant_for_user",
)
