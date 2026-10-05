"""Shared machinery for the architectural guards.

Two guards depend on the same question - "which classes in this project are
tenant-scoped viewsets?" - and both must answer it identically. Asking twice is
how the two guards drift apart and start protecting different populations, so
the answer lives here.

The rules that depend on it:

* `test_tenant_queryset_guard.py` - a tenant-scoped viewset may not override
  `get_queryset()` without calling `super()`.
* `test_filterset_guard.py` - a tenant-scoped viewset may not declare
  `filterset_fields` or `filterset_class`.

Tenancy is decided from the real `__mro__` and overrides from the real
`__dict__`, rather than by parsing base names, so import aliases, mixin ordering
and inheritance depth cannot mislead either guard.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import textwrap
from typing import Any

from rest_framework.viewsets import ViewSetMixin

from common.mixins import TenantFilterMixin

#: Justification a viewset must declare to override `get_queryset()` without
#: calling `super()`. Read from the class's own `__dict__`, so a stale
#: justification on an ancestor cannot excuse a new bypass.
EXEMPT_ATTR = "tenant_queryset_override_reason"

#: Where the tenant filter itself lives. `TenantFilterMixin.get_queryset` *is*
#: the filter, not an override of it, and these bases are the highest-leverage,
#: most-reviewed code here. An explicit list, so widening the exemption is a
#: visible decision rather than a side effect of skipping a directory.
SHARED_BASE_MODULES = frozenset({"common.mixins", "common.viewset"})


def concrete_tenant_viewsets() -> list[type[Any]]:
    """Every tenant-scoped viewset under `apps/`, excluding the shared bases.

    Uses `ViewSetMixin` rather than DRF's concrete `ViewSet`: `GenericViewSet`
    *combines* `ViewSetMixin`, it does not inherit `ViewSet`, so
    `issubclass(TenantScopedViewSet, ViewSet)` is False and a guard written
    against `ViewSet` matches nothing while passing every test.
    """
    import apps

    found: list[type[Any]] = []
    for module_info in pkgutil.walk_packages(apps.__path__, prefix="apps."):
        if not module_info.name.endswith(".views"):
            continue
        module = importlib.import_module(module_info.name)
        for obj in vars(module).values():
            if not inspect.isclass(obj) or obj.__module__ != module_info.name:
                continue
            if not issubclass(obj, ViewSetMixin):
                continue
            if TenantFilterMixin not in obj.__mro__:
                continue
            if obj.__module__ in SHARED_BASE_MODULES:
                continue
            found.append(obj)
    return found


def class_source(cls: type[Any]) -> str:
    return inspect.getsource(cls)


def override_calls_super(class_source_text: str, method: str = "get_queryset") -> bool | None:
    """Does `method`'s body call `super().<method>()`?

    `None` when the class does not define `method` at all. Accepts both the
    zero-argument `super().get_queryset()` and the explicit
    `super(Cls, self).get_queryset()` form.
    """
    tree = ast.parse(textwrap.dedent(class_source_text))
    class_def = next((n for n in tree.body if isinstance(n, ast.ClassDef)), None)
    if class_def is None:
        return None
    func = next(
        (
            n
            for n in class_def.body
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == method
        ),
        None,
    )
    if func is None:
        return None
    for node in ast.walk(func):
        # `super().get_queryset()` parses as Call(func=Attribute(
        # value=Call(func=Name("super")))). Matching a bare Name for the receiver
        # matches only the nonsensical `super.get_queryset()`, so every real
        # `super()` call would read as a bypass.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == method
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "super"
        ):
            return True
    return False


def exemption(cls: type[Any]) -> str | None:
    """The class's own non-empty justification for skipping `super()`, else None."""
    reason = cls.__dict__.get(EXEMPT_ATTR)
    return reason if isinstance(reason, str) and reason.strip() else None
