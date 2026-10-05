"""Admin authentication (plan §8: email + password, `IsAdmin`).

An email-keyed user model, one practice per user (`tenant`), and a `role`.
Customers are a *separate* principal (`apps.customers.Customer`, Phase 4) that
authenticates by phone OTP, so an admin token can never be used on `/me/*` and
a customer token can never reach `/admin/*` (S §A3).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.accounts.tokens import revoke_family
from apps.tenants.models import Tenant
from common.models import BaseModel, TimeStampedModel
from common.querysets import TenantScopedManager


class Role(models.TextChoices):
    """Capabilities within one practice.

    `is_staff` stays the Django-admin flag; `role` is the API's authorisation
    input. Keeping them separate means "can log into /admin/" and "can edit the
    price of a consultation" remain independently revocable (S §A4).
    """

    OWNER = "OWNER", "Owner"
    ADMIN = "ADMIN", "Admin"
    STAFF = "STAFF", "Staff"
    VIEWER = "VIEWER", "Viewer"

    @classmethod
    def admin_roles(cls) -> tuple[str, ...]:
        """Roles allowed to reach `/admin/*` API endpoints."""
        return (cls.OWNER, cls.ADMIN)


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> User:
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if extra["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None) -> User:
        if not username:
            raise self.model.DoesNotExist("An email address is required.")
        return self.get(email__iexact=username)

    def for_tenant(self, tenant: Tenant) -> models.QuerySet[User]:
        return self.filter(tenant=tenant)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """A back-office user. Customers are a separate principal (Phase 4)."""

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # Plan §3: `User ... role(admin), is_active, tenant`. PROTECT because
    # deleting a practice must not silently orphan or delete its staff logins;
    # deactivating a user is the revocation path.
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
    )

    # Email is globally unique, so the default manager needs no tenant scope;
    # `scoped_objects` is the tenant-filtered alias used by list endpoints.
    objects = UserManager()
    scoped_objects = TenantScopedManager["User"]()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        db_table = "users"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email

    @property
    def is_tenant_admin(self) -> bool:
        """Whether this user may reach the admin API.

        `is_superuser` is included deliberately: it is the documented
        break-glass for the person who cannot get into their own tenant.
        """
        return bool(
            self.is_active
            and (
                self.is_superuser
                or (self.tenant_id is not None and self.role in Role.admin_roles())
            )
        )


class RefreshSession(BaseModel):
    """One login. Rotating tokens keep the same `family` claim.

    See `apps.accounts.tokens.revoke_family` for why this exists alongside
    simplejwt's `OutstandingToken`: that table answers "is this jti dead",
    this one answers "which tokens came from this login", and only the second
    can group a family for §A2 reuse detection.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
    )
    # Denormalised from the user so revoking a family never needs a join, and
    # so a user whose tenant changed cannot take their session with them.
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
        null=True,
        blank=True,
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "refresh_sessions"
        ordering = ("-created_at",)
        indexes = [  # noqa: RUF012 - Django's own class-list style
            models.Index(fields=("user", "revoked_at"), name="idx_session_user_revoked"),
        ]

    def __str__(self) -> str:
        return f"session {self.pk} for {self.user_id}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self, reason: str) -> int:
        """Blacklist every outstanding refresh token in this family.

        Returns the number of tokens blacklisted. Idempotent: revoking an
        already-revoked family is a no-op, so a concurrent replay cannot
        double-count or resurrect anything.
        """
        if self.revoked_at is not None:
            return 0
        revoked = revoke_family(self.user_id, self.pk)
        self.revoked_at = timezone.now()
        self.revoked_reason = reason[:64]
        self.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])
        return revoked
