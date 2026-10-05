from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

User = get_user_model()


def test_user_is_email_keyed_not_username() -> None:
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []


def test_email_is_normalised_to_lowercase() -> None:
    user = User.objects.create_user(email="Admin@Example.COM", password="x")

    assert user.email == "admin@example.com"


def test_emails_are_unique() -> None:
    from django.db import IntegrityError, transaction

    User.objects.create_user(email="dup@example.com", password="x")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="dup@example.com", password="x")


def test_create_superuser_sets_flags() -> None:
    user = User.objects.create_superuser(email="root@example.com", password="x")

    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_active is True


def test_create_superuser_rejects_missing_flags() -> None:
    with pytest.raises(ValueError, match="is_staff"):
        User.objects.create_superuser(email="a@example.com", password="x", is_staff=False)


def test_email_is_required() -> None:
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="", password="x")


def test_user_without_password_is_unusable() -> None:
    user = User.objects.create_user(email="nopass@example.com")

    assert user.has_usable_password() is False


def test_argon2_is_the_default_hasher() -> None:
    """Test settings swap in MD5 for speed; base is what prod runs."""
    from config.settings import base

    assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")


def test_argon2_cffi_is_installed() -> None:
    from importlib.metadata import version

    assert version("argon2-cffi")


def test_natural_key_lookup_is_case_insensitive() -> None:
    User.objects.create_user(email="Case@Example.com", password="x")

    assert User.objects.get_by_natural_key("case@example.com") is not None


def test_str_is_the_email() -> None:
    user = User(email="x@example.com")

    assert str(user) == "x@example.com"


def test_invalid_email_is_rejected_by_full_clean() -> None:
    user = User(email="not-an-email")

    with pytest.raises(ValidationError):
        user.full_clean()
