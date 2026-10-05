from __future__ import annotations

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """Project-wide base: UUID primary key + created_at/updated_at.

    Plan §3: "All tables: id (UUID), created_at, updated_at."
    """

    class Meta:
        abstract = True


class IdempotencyRecord(BaseModel):
    """One `Idempotency-Key` seen by the API (plan §5 layer 4).

    The booking endpoint stores a record per key so a double-tapped "Book"
    button resolves the appointment it already created instead of carving a
    second hold. `(tenant, endpoint, key)` is unique, which is what turns a
    concurrent replay from a race into an `IntegrityError` the called service
    can re-resolve. `endpoint` keeps the table usable by other unsafe routes
    without keys colliding across them.

    Intentionally a plain manager: this is a cross-cutting bookkeeping table,
    not tenant data with rows the client can enumerate; every caller filters
    by `tenant` explicitly.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="idempotency_records",
        help_text="The practice the request ran against.",
    )
    key = models.CharField(max_length=72, help_text="The Idempotency-Key header value.")
    endpoint = models.CharField(
        max_length=72, help_text="Route scoping the key, e.g. 'appointments'."
    )
    object_id = models.CharField(
        max_length=36,
        blank=True,
        default="",
        help_text="Primary key of the object created for this key, once it exists.",
    )

    objects = models.Manager()

    class Meta:
        db_table = "idempotency_records"
        ordering = ("-created_at",)
        constraints = [  # noqa: RUF012 - Django's own class-list style
            models.UniqueConstraint(
                fields=("tenant", "endpoint", "key"),
                name="uniq_idempotency_tenant_endpoint_key",
            ),
        ]
        # No extra index: the unique constraint already indexes
        # (tenant, endpoint, key) in the order every lookup uses.

    def __str__(self) -> str:
        return f"{self.endpoint}/{self.key} -> {self.object_id or '(pending)'}"
