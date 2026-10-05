"""Permissions for the services catalogue (plan §2 Phase 2).

The plan names `CanEditService` for the admin CRUD explicitly. For now it is
exactly `IsAdmin` - OWNER/ADMIN within the tenant may edit the catalogue -
kept as its own class so a finer-grained role can be slotted in later without
touching call sites (S §A4 keeps the role and `is_staff` independent).
"""

from __future__ import annotations

from common.permissions import IsAdmin


class CanEditService(IsAdmin):
    """Administrators of the tenant may create/edit/delete its services."""

    message = "Service catalogue editing is restricted to practice administrators."


__all__ = ("CanEditService",)
