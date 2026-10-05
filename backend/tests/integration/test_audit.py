from __future__ import annotations

from typing import Any

import pytest
from rest_framework import status

from apps.audit.audit import audit, audited, snapshot
from apps.audit.models import AuditLog
from tests.testapp.models import Widget

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def tenant() -> Any:
    from apps.tenants.models import Tenant

    return Tenant.objects.create(slug="auditco", name="Audit LLP", timezone="UTC")


def test_audit_row_captures_explicit_values(tenant: Any) -> None:
    row = audit(
        action="widget.create",
        entity_type="testapp.widget",
        entity_id="w-1",
        before={"name": "old"},
        after={"name": "new"},
        actor=tenant,  # any model stands in for the actor here
        tenant=tenant,
        ip="203.0.113.5",
        user_agent="pytest",
    )

    assert row.action == "widget.create"
    assert row.entity_type == "testapp.widget"
    assert row.entity_id == "w-1"
    assert row.before == {"name": "old"}
    assert row.after == {"name": "new"}
    assert row.actor_type == "tenant"
    assert row.actor_id == str(tenant.pk)
    assert row.tenant_id == tenant.pk
    assert row.ip == "203.0.113.5"
    assert row.user_agent == "pytest"
    assert row.created_at is not None


def test_actor_model_type_is_derived_from_label(tenant: Any) -> None:
    from apps.accounts.models import Role, User

    user = User.objects.create_user(
        email="admin@auditco.com", password="Str0ng-Passw0rd!", tenant=tenant, role=Role.OWNER
    )

    row = audit(action="user.update", actor=user, tenant=tenant)

    assert row.actor_type == "user"
    assert row.actor_id == str(user.pk)
    assert row.tenant_id == tenant.pk


def test_audit_values_are_json_safe(tenant: Any) -> None:
    row = audit(
        action="widget.update",
        before={"name": "old"},
        after={"name": "new"},
        tenant=tenant,
    )
    assert row.before == {"name": "old"}
    assert row.after == {"name": "new"}
    assert row.tenant_id == tenant.pk


def test_snapshot_flattens_a_model(tenant: Any) -> None:
    widget = Widget.objects.create(tenant_id=str(tenant.pk), name="widget")

    data = snapshot(widget)

    assert data["name"] == "widget"
    assert data["tenant_id"] == str(tenant.pk)
    assert data["is_active"] is True
    assert data["id"] == str(widget.pk)


def test_audited_records_before_and_after(tenant: Any) -> None:
    widget = Widget.objects.create(tenant_id=str(tenant.pk), name="before")

    @audited(action="widget.update")
    def rename(instance: Widget, name: str) -> Widget:
        instance.name = name
        instance.save(update_fields=["name", "updated_at"])
        return instance

    renamed = rename(widget, "after")

    assert renamed.name == "after"
    row = AuditLog.objects.get(action="widget.update")
    assert row.entity_type == "testapp.widget"
    assert row.entity_id == str(widget.pk)
    assert row.before["name"] == "before"
    assert row.after["name"] == "after"


def test_audited_entity_type_can_be_overridden(tenant: Any) -> None:
    widget = Widget.objects.create(tenant_id=str(tenant.pk), name="w")

    @audited(action="widget.custom", entity_type="custom.entity")
    def touch(instance: Widget) -> Widget:
        return instance

    touch(widget)

    assert AuditLog.objects.get(action="widget.custom").entity_type == "custom.entity"


def test_audited_never_silently_drops_history(tenant: Any) -> None:
    """A failed audit write rolls the mutation back with it (Django transaction)."""
    widget = Widget.objects.create(tenant_id=str(tenant.pk), name="w")

    @audited(action="widget.boom")
    def boom(instance: Widget) -> Widget:
        instance.name = "mutated"
        instance.save(update_fields=["name", "updated_at"])
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        boom(widget)

    assert not AuditLog.objects.exists()
    assert Widget.objects.unfiltered().get(pk=widget.pk).name == "w"


def test_audit_rows_are_append_only_and_read_only_via_admin(tenant: Any) -> None:
    from django.contrib import admin
    from django.test import Client

    from apps.accounts.models import Role, User

    staff = User.objects.create_user(
        email="auditadmin@auditco.com",
        password="Str0ng-Passw0rd!",
        tenant=tenant,
        role=Role.ADMIN,
        is_staff=True,
    )
    client = Client()
    client.force_login(staff)

    log = client.get("/admin/audit/auditlog/")
    assert log.status_code == status.HTTP_200_OK

    # The log is read-only: no add/change/delete links are offered.
    assert "Add audit log" not in log.content.decode()

    # A superuser's changes through the admin panel are themselves audited
    # (the Phase 1 wiring proof: `save_model` -> `audit()` with a diff).
    superuser = User.objects.create_user(
        email="su@auditco.com",
        password="Str0ng-Passw0rd!",
        tenant=tenant,
        role=Role.OWNER,
        is_staff=True,
        is_superuser=True,
    )
    from rest_framework.test import APIRequestFactory

    from apps.accounts.admin import UserAdmin
    from apps.audit.admin import AuditLogAdmin

    admin_instance = UserAdmin(model=User, admin_site=admin.site)
    request = APIRequestFactory().post("/admin/accounts/user/1/change/")
    request.user = superuser
    request.META["REMOTE_ADDR"] = "198.51.100.9"
    request.META["HTTP_USER_AGENT"] = "admin-test"

    class _Form:
        pass

    admin_instance.save_model(request, staff, _Form(), change=True)

    row = AuditLog.objects.get(action="user.update")
    assert row.entity_id == str(staff.pk)
    assert row.actor_id == str(superuser.pk)
    assert row.tenant_id == tenant.pk
    assert row.ip == "198.51.100.9"
    assert row.after["email"] == staff.email

    # AuditLogAdmin is read-only end to end.
    audit_admin = AuditLogAdmin(model=AuditLog, admin_site=admin.site)
    assert audit_admin.has_add_permission(request) is False
    assert audit_admin.has_change_permission(request) is False
    assert audit_admin.has_delete_permission(request) is False


def test_audit_without_context_defaults_safely(tenant: Any) -> None:
    row = audit(action="system.run")
    assert row.tenant_id is None
    assert row.actor_id == ""
    assert row.actor_type == ""
    assert row.ip is None
    assert row.user_agent == ""
