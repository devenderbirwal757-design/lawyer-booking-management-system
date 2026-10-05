"""Seed the demo install: default tenant + an owner admin + default provider
(plan §1 Phase 1, plan §3 Phase 3).

Usage:
    python scripts/seed_demo.py
    SEED_ADMIN_EMAIL=boss@example.com SEED_ADMIN_PASSWORD='...' python scripts/seed_demo.py

Env vars, with fallbacks:

- `SEED_TENANT_SLUG`  -> `DJANGO_DEFAULT_TENANT_SLUG` -> "demo"
- `SEED_TENANT_NAME`  -> "Demo Law Office" (or the slug title-cased)
- `SEED_PROVIDER_NAME` -> "Demo Law Office" (health-check webhook recipient)
- `SEED_ADMIN_EMAIL`  -> `ADMIN_EMAIL` -> "admin@example.com"
- `SEED_ADMIN_PASSWORD` -> `ADMIN_PASSWORD` (required unless the user already
  exists with a usable password)

It is idempotent - rerunning it never changes an existing tenant's slug, an
existing admin's password, or an existing provider's details.
"""

from __future__ import annotations

import os
import sys


def _load_django() -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()


def _config() -> dict[str, str]:
    slug = (
        os.environ.get("SEED_TENANT_SLUG") or os.environ.get("DJANGO_DEFAULT_TENANT_SLUG") or "demo"
    )
    return {
        "slug": slug.strip().lower(),
        "name": os.environ.get("SEED_TENANT_NAME") or slug.title(),
        "email": os.environ.get("SEED_ADMIN_EMAIL")
        or os.environ.get("ADMIN_EMAIL")
        or "admin@example.com",
        "password": os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD") or "",
    }


def main() -> int:
    config = _config()
    _load_django()

    from apps.accounts.models import Role, User
    from apps.providers.models import Provider
    from apps.tenants.models import Tenant

    tenant, created = Tenant.objects.get_or_create(
        slug=config["slug"],
        defaults={"name": config["name"], "timezone": "UTC"},
    )
    print(f"{'Created' if created else 'Using existing'} tenant: {tenant.slug}")

    user = User.objects.filter(email=config["email"]).first()
    if user is None:
        if not config["password"]:
            print(
                "Set $SEED_ADMIN_PASSWORD (or $ADMIN_PASSWORD) on first run so the admin "
                "can log in, then rerun.",
                file=sys.stderr,
            )
            return 1
        user = User.objects.create_user(
            email=config["email"],
            password=config["password"],
            full_name=config["name"],
            role=Role.OWNER,
            tenant=tenant,
            is_staff=True,
            is_active=True,
        )
        was_created = True
    else:
        was_created = False
    if user.role not in Role.admin_roles():
        # The seed ran before; make sure the admin can actually reach /admin/*.
        user.role = Role.OWNER
        user.tenant = tenant
        user.save(update_fields=["role", "tenant", "updated_at"])

    print(f"{'Created' if was_created else 'Using existing'} admin: {user.email} ({user.role})")

    provider, provider_created = Provider.objects.unfiltered().get_or_create(
        tenant=tenant,
        name=config["name"],
    )
    print(
        f"{'Created' if provider_created else 'Using existing'} provider: "
        f"{provider.name} ({provider.pk})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
