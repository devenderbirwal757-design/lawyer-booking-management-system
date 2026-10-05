"""System checks for tenant resolution (plan §2, PRD §32).

`TenantMiddleware` can identify a practice in three ways: the authenticated
principal, a host subdomain (`alice.lawyer.test`), or `DJANGO_DEFAULT_TENANT_SLUG`.
With none of them it binds nothing, and because the failure is quiet rather than
loud it is worth catching before traffic arrives:

* tenant-scoped *lists* return `200` with zero rows (`TenantFilterMixin` calls
  `qs.none()`), so an unconfigured install looks like an empty practice;
* anything that reads through a tenant-scoped manager raises
  `TenantContextMissing`, which reaches the client as an opaque `500`.

Neither says "you forgot a setting". These checks do.

Unset is a **warning**, not an error: serving every practice by subdomain or by
`X-Tenant-Slug` header is a legitimate multi-tenant deployment with no default,
and hard-failing `manage.py check` there would break a valid configuration. A
default that is *set but does not resolve* is an error in every deployment - no
subdomain routing can rescue it - so that one blocks.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

from common.middleware import database_is_reachable

#: Stable ids so a deploy can silence or grep for one specifically.
NO_DEFAULT_TENANT = "tenants.W001"
UNRESOLVED_DEFAULT_TENANT = "tenants.E001"
SUSPENDED_DEFAULT_TENANT = "tenants.E002"

_HOW_TO_FIX = (
    "Set DJANGO_DEFAULT_TENANT_SLUG to the slug of a practice (it must match the "
    "slug scripts/seed_demo.py creates), or address the API by tenant subdomain. "
    "See .env.example and backend/README.md."
)


@register()
def check_default_tenant_slug(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Warn when there is no default tenant; error when it cannot resolve."""
    slug = getattr(settings, "DEFAULT_TENANT_SLUG", None)
    if not slug:
        return [
            Warning(
                "DJANGO_DEFAULT_TENANT_SLUG is not set.",
                hint=(
                    "Any request that is not addressed by tenant subdomain or the "
                    "X-Tenant-Slug header will bind no tenant, so tenant-scoped "
                    "lists answer 200 with zero rows and reads that go through a "
                    "tenant-scoped manager raise TenantContextMissing (an opaque "
                    f"500). {_HOW_TO_FIX}"
                ),
                id=NO_DEFAULT_TENANT,
            )
        ]

    if not database_is_reachable():
        # `manage.py check` runs before migrations on a fresh database. Not
        # knowing is not the same as being wrong; report nothing.
        return []

    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.get(slug=str(slug).strip().lower())
    except Tenant.DoesNotExist:
        return [
            Error(
                f"DJANGO_DEFAULT_TENANT_SLUG is {slug!r}, but no practice has that slug.",
                hint=(
                    "Every request that relies on the default will be answered 404 "
                    f"'Unknown practice.' {_HOW_TO_FIX}"
                ),
                id=UNRESOLVED_DEFAULT_TENANT,
            )
        ]

    if not tenant.is_active:
        return [
            Error(
                f"DJANGO_DEFAULT_TENANT_SLUG is {slug!r} and that practice is suspended.",
                hint=(
                    "TenantMiddleware answers 404 for a suspended practice, so every "
                    "default-routed request fails. Reactivate it in the Django admin "
                    "or point the setting at another practice."
                ),
                id=SUSPENDED_DEFAULT_TENANT,
            )
        ]

    return []


__all__ = (
    "NO_DEFAULT_TENANT",
    "SUSPENDED_DEFAULT_TENANT",
    "UNRESOLVED_DEFAULT_TENANT",
    "check_default_tenant_slug",
)
