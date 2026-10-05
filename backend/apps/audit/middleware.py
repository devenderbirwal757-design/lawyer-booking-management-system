"""Fix the actor + request context for the `audit()` helper (plan §1 Phase 1).

Runs after `AuthenticationMiddleware`, so `request.user` is populated for
session/header-authenticated requests. JWT requests are a known gap: DRF
authenticates inside the view, after middleware, so `request.user` is
anonymous here. Callers in views pass `actor=request.user` explicitly (both
`audit()` and `@audited` accept it), which lands in the context anyway because
DRF replaces `request.user` on the *same* request object the middleware saw.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.http import HttpRequest, HttpResponse

from common.querysets import actor_context, set_request


class AuditContextMiddleware:
    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        set_request(request)
        user = getattr(request, "user", None)
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and isinstance(user, models.Model)
        ):
            with actor_context(user):
                return self.get_response(request)  # type: ignore[no-any-return]
        return self.get_response(request)  # type: ignore[no-any-return]


__all__ = ("AuditContextMiddleware",)
