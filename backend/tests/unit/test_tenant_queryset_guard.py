"""Fail the build when a viewset overrides `get_queryset()` without `super()`.

`TenantFilterMixin.get_queryset()` (common/mixins.py) is what stops a
tenant-scoped endpoint reading another practice's rows. A subclass that
overrides it and forgets `super()` drops that filter completely, and the
override reads like ordinary narrowing, so nothing in review catches it. This
guard turns it into a build failure.

The check is on the *real* class objects - `__mro__` decides tenant scoping and
`__dict__` decides whether the override is the class's own - so it cannot be
fooled by import aliases or inheritance depth the way an AST-only scan of base
names can. AST is used only to read one method's body.

Deliberately fail-closed: if a class's source cannot be read or parsed, that is
reported as a violation rather than skipped. A guard that quietly stops looking
is worse than no guard, because it reads as coverage.

The self-tests below matter as much as the scan. They pin the detector against
known-bad input, so a refactor that makes the AST walk return `True` for
everything fails here instead of silently passing every real viewset.
"""

from __future__ import annotations

import pytest

from tests.unit.architecture import (
    EXEMPT_ATTR,
    class_source,
    concrete_tenant_viewsets,
    exemption,
    override_calls_super,
)

pytestmark = pytest.mark.unit


class BaseViewSetStub:
    """Stand-in for a tenant-scoped viewset in the synthetic tests.

    `exemption()` only inspects `__dict__`, so these do not need a real DRF
    base - and not being real viewsets keeps them out of `_find_bypasses()`.
    """


def _find_bypasses() -> list[str]:
    violations: list[str] = []
    for cls in concrete_tenant_viewsets():
        qualified = f"{cls.__module__}.{cls.__qualname__}"
        try:
            source = class_source(cls)
        except (OSError, TypeError) as exc:  # pragma: no cover - defensive
            violations.append(f"{qualified}: could not read source ({exc}); guard cannot verify it")
            continue
        try:
            calls_super = override_calls_super(source)
        except SyntaxError as exc:
            violations.append(
                f"{qualified}: could not parse source ({exc}); guard cannot verify it"
            )
            continue
        if calls_super is None or calls_super:
            continue
        if exemption(cls) is not None:
            continue
        violations.append(
            f"{qualified}: overrides get_queryset() without calling super(), "
            f"which drops the tenant filter. Either call super(), or set "
            f"{EXEMPT_ATTR} to a non-empty reason if the model has no tenant column."
        )
    return violations


# ----------------------------------------------------------------- the build gate


def test_no_viewset_drops_the_tenant_filter() -> None:
    """The gate itself. Fails with an actionable message, not a class name alone."""
    violations = _find_bypasses()

    assert violations == [], "Tenant-isolation bypasses:\n" + "\n".join(
        f"  - {violation}" for violation in violations
    )


def test_guard_actually_inspects_viewsets() -> None:
    """A guard that scans nothing passes forever; pin that it is scanning.

    This is the fail-closed guard on the guard: the enumeration broke silently
    during development (a subclass test against DRF's concrete `ViewSet` matched
    zero classes because `GenericViewSet` combines `ViewSetMixin` rather than
    inheriting `ViewSet`), and every scan-based test then passed vacuously.
    """
    scanned = concrete_tenant_viewsets()

    assert scanned, "guard scanned zero viewsets: enumeration is broken"
    assert len(scanned) >= 8, f"expected the whole API surface, found {len(scanned)}"


def test_shared_bases_are_excluded_but_concrete_views_are_not() -> None:
    scanned = concrete_tenant_viewsets()
    modules = {cls.__module__ for cls in scanned}

    assert "common.viewset" not in modules
    assert "common.mixins" not in modules
    assert "apps.payments.views" in modules


def test_only_the_declaration_own_get_queryset_counts_as_an_override() -> None:
    """A viewset that never overrides `get_queryset` is not a bypass."""
    class_inherited = [
        cls
        for cls in concrete_tenant_viewsets()
        if "get_queryset" not in cls.__dict__ and cls.__name__.startswith("AdminPayment")
    ]

    assert class_inherited == [] or all(
        override_calls_super(class_source(cls)) is None for cls in class_inherited
    )


# ------------------------------------------------------- detector self-tests
# Known-bad and known-good source, so the AST walk cannot rot unnoticed.


def test_detector_rejects_the_canonical_bypass() -> None:
    """The exact shape that leaked data before: narrowing, but not tenant-safe."""
    assert not override_calls_super(
        """
        class BadViewSet(BaseViewSet):
            def get_queryset(self):
                return Payment.objects.none()
        """
    )


def test_detector_rejects_a_bypass_that_mentions_the_tenant() -> None:
    """A convincing-looking override is still a bypass if it skips `super()`."""
    assert not override_calls_super(
        """
        class SneakyViewSet(BaseViewSet):
            def get_queryset(self):
                return Payment.objects.filter(tenant_id=self.request.user.tenant_id)
        """
    )


def test_detector_accepts_zero_argument_super() -> None:
    assert override_calls_super(
        """
        class GoodViewSet(BaseViewSet):
            def get_queryset(self):
                return super().get_queryset().select_related("service")
        """
    )


def test_detector_accepts_explicit_two_argument_super() -> None:
    assert override_calls_super(
        """
        class GoodViewSet(BaseViewSet):
            def get_queryset(self):
                return super(GoodViewSet, self).get_queryset()
        """
    )


def test_detector_accepts_super_assigned_before_filtering() -> None:
    assert override_calls_super(
        """
        class GoodViewSet(BaseViewSet):
            def get_queryset(self):
                qs = super().get_queryset()
                return qs.filter(status="ACTIVE")
        """
    )


def test_detector_ignores_super_in_a_sibling_method() -> None:
    """Guards against a whole-class walk, which would pass every bypass."""
    assert not override_calls_super(
        """
        class BadViewSet(BaseViewSet):
            def get_queryset(self):
                return Payment.objects.none()

            def get_serializer_context(self):
                return super().get_queryset().first()
        """
    )


def test_detector_reports_none_when_the_class_does_not_override() -> None:
    assert (
        override_calls_super(
            """
            class PlainViewSet(BaseViewSet):
                serializer_class = ThingSerializer
            """
        )
        is None
    )


# ----------------------------------------------------------- exemption hygiene


def test_the_known_exemption_is_present_and_reasons_itself() -> None:
    """`PaymentEvent` has no tenant column, so it must scope itself by hand."""
    from apps.payments.views import AdminPaymentEventViewSet

    reason = exemption(AdminPaymentEventViewSet)

    assert reason is not None
    assert "PaymentEvent" in reason


def test_an_empty_exemption_does_not_count() -> None:
    """Whitespace must not pass as a justification."""

    class Empty(BaseViewSetStub):
        tenant_queryset_override_reason = "   "

    assert exemption(Empty) is None


def test_a_missing_exemption_does_not_count() -> None:
    class Missing(BaseViewSetStub):
        pass

    assert exemption(Missing) is None


def test_exemptions_are_declared_in_the_class_that_needs_them() -> None:
    """Inherited justifications are ignored, so a stale one cannot excuse a new bypass."""

    class Parent(BaseViewSetStub):
        tenant_queryset_override_reason = "parent had a reason"

    class Child(Parent):
        pass

    assert exemption(Child) is None
    assert exemption(Parent) == "parent had a reason"


def test_exemptions_are_few_and_justified() -> None:
    """Every exempt viewset is a standing exception; keep the count honest."""
    exempt = [cls for cls in concrete_tenant_viewsets() if exemption(cls) is not None]

    assert exempt == [] or all(len(exemption(cls) or "") >= 40 for cls in exempt), [
        f"{cls.__name__}: exemption too terse to review" for cls in exempt
    ]
