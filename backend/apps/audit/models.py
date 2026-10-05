"""Audit log: who changed what, before and after (plan §3.1, §1 Phase 1).

Rows are append-only by design: there is no update/delete path exposed, and
`AuditLogAdmin` is read-only so a misconfigured internal tool cannot silently
rewrite history. The write is synchronous on purpose for Phase 1 - the risk
register note about sampling/async writes is a Phase 10 hardening item.
"""

from __future__ import annotations

from django.db import models

from common.models import BaseModel


class AuditLog(BaseModel):
    """One fact about a mutation.

    `tenant` denormalises the row so audit browsing never has to join, and
    `actor_type`/`actor_id` make the actor a polymorphic reference (user,
    system, customer) instead of a hard FK that would block all other kinds.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    actor_type = models.CharField(max_length=32, default="user")
    actor_id = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=128, db_index=True)
    entity_type = models.CharField(max_length=64, blank=True, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("tenant", "created_at"), name="idx_audit_tenant_created"),
            models.Index(fields=("entity_type", "entity_id"), name="idx_audit_entity"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.action} {self.entity_type}:{self.entity_id} "
            f"by {self.actor_type}:{self.actor_id}"
        )


# Re-export so the model is discoverable via `apps.audit.models` as installed.
__all__ = ("AuditLog",)
