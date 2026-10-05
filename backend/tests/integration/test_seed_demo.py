from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def seed(monkeypatch: Any) -> Any:
    import scripts.seed_demo as seed_demo

    def run(**overrides: str) -> int:
        env = {
            "SEED_TENANT_SLUG": "demo",
            "SEED_TENANT_NAME": "Demo Law Office",
            "SEED_ADMIN_EMAIL": "boss@demo.com",
            "SEED_ADMIN_PASSWORD": "Str0ng-Passw0rd!",
        }
        env.update(overrides)
        monkeypatch.setattr("os.environ", {**__import__("os").environ, **env})
        return seed_demo.main()

    return run


def test_seed_demo_creates_tenant_and_owner(seed: Any) -> None:
    from apps.accounts.models import Role, User
    from apps.tenants.models import Tenant

    assert seed() == 0

    tenant = Tenant.objects.get(slug="demo")
    assert tenant.name == "Demo Law Office"
    admin = User.objects.get(email="boss@demo.com")
    assert admin.tenant_id == tenant.pk
    assert admin.role == Role.OWNER
    assert admin.is_tenant_admin is True


def test_seed_demo_is_idempotent_and_never_resets_passwords(seed: Any) -> None:
    from apps.accounts.models import User
    from apps.tenants.models import Tenant

    assert seed() == 0
    admin = User.objects.get(email="boss@demo.com")

    # A later operation changed the password; rerunning the seed must not
    # clobber it back to the seed-time value.
    admin.set_password("Changed-Later-Passw0rd!")
    admin.save(update_fields=["password", "updated_at"])
    assert seed() == 0

    admin.refresh_from_db()
    assert admin.check_password("Changed-Later-Passw0rd!")
    assert Tenant.objects.filter(slug="demo").count() == 1
    assert User.objects.filter(email="boss@demo.com").count() == 1


def test_seed_demo_promotes_an_existing_viewer(seed: Any) -> None:
    from apps.accounts.models import Role, User
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.create(slug="demo", name="Existing", timezone="UTC")
    User.objects.create_user(
        email="boss@demo.com", password="Str0ng-Passw0rd!", tenant=tenant, role=Role.VIEWER
    )

    assert seed() == 0

    admin = User.objects.get(email="boss@demo.com")
    assert admin.tenant_id == tenant.pk
    assert admin.role == Role.OWNER


def test_seed_demo_requires_a_password_for_a_new_admin(seed: Any) -> None:
    from apps.accounts.models import User

    assert seed(SEED_ADMIN_PASSWORD="", ADMIN_PASSWORD="") == 1
    assert not User.objects.filter(email="boss@demo.com").exists()
    # The tenant is still created, so a rerun with a password can attach to it.
    from apps.tenants.models import Tenant

    assert Tenant.objects.filter(slug="demo").exists()
