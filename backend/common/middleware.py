from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from django.db import connections
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from common.querysets import new_request_id, set_request

logger: Any = structlog.get_logger("common.request")

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"


class RequestIDMiddleware:
    """Attach a request id to every request/response and to the log context.

    Plan §8: "X-Request-ID middleware + structured logging with request ID."
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = str(request.META.get(REQUEST_ID_HEADER) or new_request_id())
        request.request_id = request_id  # type: ignore[attr-defined]
        request.started_at = timezone.now()  # type: ignore[attr-defined]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.path,
            method=request.method,
        )
        set_request(request)
        try:
            response: HttpResponse = self.get_response(request)
        except Exception:
            logger.exception("request_failed", request_id=request_id)
            raise
        finally:
            structlog.contextvars.clear_contextvars()
            set_request(None)
        response["X-Request-ID"] = request_id
        return response


def database_is_reachable(alias: str = "default") -> bool:
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return False
    return True
