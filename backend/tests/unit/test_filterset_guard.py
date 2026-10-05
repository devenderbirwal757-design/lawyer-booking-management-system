"""Fail the build when a tenant-scoped viewset declares `filterset_fields`.

Why this is banned, verified rather than assumed - see
`tests/integration/test_filterset_hazard.py`, which reproduces each claim and
fails loudly if django-filter is ever upgraded into being safe:

1. **It discloses other practices.** A relation field becomes a
   `ModelChoiceFilter` whose choice list is built from the *related* model's
   `_default_manager`. On `Provider` that is `Tenant.objects`, so declaring
   `filterset_fields = ["tenant"]` publishes every practice's slug and UUID to a
   caller who may only ever see their own. For a lawyer-management product the
   client list is commercially sensitive, and it also lands in the OpenAPI
   schema. Rows stay correctly scoped - this is disclosure, not leakage.

2. **It needs a bound tenant to exist at all.** Building the filterset introspects
   `Model._default_manager`, which here is the tenant-scoped manager. With no
   tenant bound that raises `TenantContextMissing` - and it raises inside
   `AutoFilterSet.get_filters()`, i.e. before any queryset is filtered, so it
   fires on every list request. It also breaks `manage.py spectacular`, since
   schema generation has no request and therefore no tenant.

The alternative already exists: `_filter_params()` in `apps/payments/views.py`
validates query params explicitly, returns a 400 on an unsupported value
instead of a silently empty list, and keeps every check inside the viewset where
the tenant filter is applied.

Note `DjangoFilterBackend` stays in `DEFAULT_FILTER_BACKENDS`. Removing it would
make a future `filterset_fields` silently filter nothing, which is worse than
the loud failure this ban produces; leaving it loaded means misuse is caught by
the guard below.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.architecture import concrete_tenant_viewsets

pytestmark = pytest.mark.unit

#: Declaring either of these switches DRF's filter machinery on for the view.
BANNED_ATTRS = ("filterset_fields", "filterset_class")


def violations_for(cls: type[Any]) -> list[str]:
    """Why `cls` is banned, or an empty list.

    Reads the *effective* attribute rather than `__dict__`: a `filterset_fields`
    declared on a shared base is active for every subclass, so it must count
    for all of them. An empty collection declares nothing and is allowed.
    """
    qualified = f"{cls.__module__}.{cls.__qualname__}"
    found: list[str] = []
    for attr in BANNED_ATTRS:
        value = getattr(cls, attr, None)
        if value is None:
            continue
        if isinstance(value, list | tuple | set | dict) and not value:
            continue
        found.append(
            f"{qualified}: declares {attr} = {value!r}. Tenant-scoped filtering must be "
            f"explicit and stay inside the viewset (see _filter_params in "
            f"apps/payments/views.py); a django-filter filterset discloses related "
            f"models across tenants and requires a bound tenant to be constructed."
        )
    return found


def find_violations() -> list[str]:
    return [violation for cls in concrete_tenant_viewsets() for violation in violations_for(cls)]


# ------------------------------------------------------------------ the build gate


def test_no_viewset_declares_a_filterset() -> None:
    violations = find_violations()

    assert violations == [], "Banned filter declarations:\n" + "\n".join(
        f"  - {violation}" for violation in violations
    )


def test_guard_actually_scans_viewsets() -> None:
    """A guard that scans nothing passes forever; pin that it is scanning."""
    scanned = concrete_tenant_viewsets()

    assert scanned, "guard scanned zero viewsets: enumeration is broken"
    assert len(scanned) >= 8, f"expected the whole API surface, found {len(scanned)}"


# ------------------------------------------------------- detector self-tests


class BaseViewSetStub:
    """Not a real viewset, so these never enter the project-wide scan."""


class Clean(BaseViewSetStub):
    filterset_fields = None
    filterset_class = None


def test_clean_viewset_has_no_violations() -> None:
    assert violations_for(Clean) == []


def test_absent_attributes_are_not_violations() -> None:
    class Bare(BaseViewSetStub):
        pass

    assert violations_for(Bare) == []


def test_empty_collections_declare_nothing() -> None:
    class Empty(BaseViewSetStub):
        filterset_fields: list[str] = []  # noqa: RUF012 - declaring the attribute is the point
        filterset_class: list[Any] = []  # noqa: RUF012 - likewise

    assert violations_for(Empty) == []


def test_declaring_filterset_fields_is_a_violation() -> None:
    class Offender(BaseViewSetStub):
        filterset_fields = ["status"]  # noqa: RUF012 - declaring the attribute is the point

    violations = violations_for(Offender)

    assert len(violations) == 1
    assert "filterset_fields" in violations[0]
    assert "['status']" in violations[0]


def test_declaring_filterset_class_is_a_violation() -> None:
    class Offender(BaseViewSetStub):
        filterset_class = object

    violations = violations_for(Offender)

    assert len(violations) == 1
    assert "filterset_class" in violations[0]


def test_a_relation_field_is_the_dangerous_case() -> None:
    """The disclosure vector: a FK publishes its related model's rows."""

    class Offender(BaseViewSetStub):
        filterset_fields = ["tenant"]  # noqa: RUF012 - the disclosure case

    violation = violations_for(Offender)[0]

    assert "discloses related" in violation


def test_inherited_declarations_are_caught() -> None:
    """A filter declared on a shared base applies to every subclass."""

    class Parent(BaseViewSetStub):
        filterset_fields = ["status"]  # noqa: RUF012 - declaring the attribute is the point

    class Child(Parent):
        pass

    assert violations_for(Child) != []
    assert violations_for(Parent) != []


@pytest.mark.parametrize("declared", [["status"], ("status",), {"status"}])
def test_any_non_empty_collection_is_a_violation(declared: Any) -> None:
    class Offender(BaseViewSetStub):
        filterset_fields = declared

    assert violations_for(Offender) != []


# ------------------------------------------------- consistency with guard #3


def test_guards_cover_the_same_population() -> None:
    """Both guards must read the same set, or one of them is protecting a ghost."""
    from tests.unit.test_tenant_queryset_guard import test_no_viewset_drops_the_tenant_filter

    assert concrete_tenant_viewsets() == concrete_tenant_viewsets()
    assert callable(test_no_viewset_drops_the_tenant_filter)
