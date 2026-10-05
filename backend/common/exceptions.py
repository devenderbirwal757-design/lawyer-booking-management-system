from __future__ import annotations

from typing import Any

import structlog
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, NotAuthenticated, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger: Any = structlog.get_logger("common.exceptions")

# Error envelope (plan §4): {"error": {"code": ..., "message": ..., "details": ...}}
DEFAULT_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthenticated",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_406_NOT_ACCEPTABLE: "not_acceptable",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "unprocessable_entity",
    status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}


class BusinessRuleException(APIException):
    """Base class for domain errors with a stable machine-readable code.

    Domain code lives in `default_code`; subclasses map to the 4xx status they
    deserve (e.g. SlotUnavailable -> 409).
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule_violation"
    default_detail = "The request could not be completed."

    def __init__(
        self,
        detail: str | None = None,
        code: str | None = None,
        errors: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        super().__init__(detail or self.default_detail, code or self.default_code)
        self.errors = errors


class ConflictError(BusinessRuleException):
    status_code: int = status.HTTP_409_CONFLICT
    default_code = "conflict"


class SlotUnavailableError(ConflictError):
    default_code = "slot_unavailable"
    default_detail = "That time slot is no longer available."


class SlotOccupiedError(ConflictError):
    """The inverse of `SlotUnavailableError`: a *block* that would sit on top
    of an existing booking. The appointment wins and the admin is told
    (plan §5.5): blocking over a booked slot is rejected with 409
    `slot_occupied`.
    """

    default_code = "slot_occupied"
    default_detail = "That window contains an existing booking."


class InvalidStateTransitionError(ConflictError):
    default_code = "invalid_state_transition"
    default_detail = "The resource cannot move to the requested state."


class HoldLimitReachedError(ConflictError):
    """Too many unpaid holds open at once (S §A7 "slot-hold abuse").

    A per-minute throttle bounds *rate*; this bounds *inventory*. Without it, a
    patient client can walk away from a whole week of slots and never pay for
    any of them - each hold is legal on its own, and together they are a denial
    of service on the practice's inventory. Only unpaid holds count: a
    confirmed booking is a real appointment and must never be blocked by this.
    """

    default_code = "hold_limit_reached"
    default_detail = (
        "You already have unpaid bookings open. Complete or cancel one before booking another."
    )


class InvalidSignatureError(BusinessRuleException):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_signature"
    default_detail = "The signature could not be verified."


class ServiceDisabledError(BusinessRuleException):
    status_code: int = status.HTTP_409_CONFLICT
    default_code = "service_disabled"
    default_detail = "This service is not currently bookable."


class TenantContextMissing(ImproperlyConfigured):
    """No tenant is bound to the current context for a tenant-scoped query.

    Raised by `TenantScopedManager.get_queryset()` instead of silently
    returning an empty queryset: an empty result hides the bug, and an
    unfiltered result leaks other tenants' rows (plan risk register: "Tenant
    leakage in a new endpoint"). Management commands, Celery tasks and
    migrations must opt out explicitly via `Model.objects.unfiltered()`.
    """


def _flatten_drf_detail(detail: Any) -> Any:
    if isinstance(detail, dict):
        return {key: _flatten_drf_detail(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_flatten_drf_detail(item) for item in detail]
    return str(detail)


def _detail_code(detail: Any, default: str) -> str:
    """DRF embeds the error code on the ErrorDetail; dig it out if present."""
    if isinstance(detail, dict):
        for value in detail.values():
            return _detail_code(value, default)
        return default
    if isinstance(detail, list | tuple):
        return _detail_code(detail[0], default) if detail else default
    return str(getattr(detail, "code", None) or default)


def _normalise(exc: Exception) -> tuple[int, str, str, Any]:
    """Map any exception onto (status_code, code, message, details)."""
    if isinstance(exc, DRFValidationError):
        details = _flatten_drf_detail(exc.detail)
        return (
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
            "Request validation failed.",
            details,
        )
    if isinstance(exc, DjangoValidationError):
        raw = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        return (
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
            "Validation failed.",
            _flatten_drf_detail(raw),
        )
    if isinstance(exc, Http404 | ObjectDoesNotExist):
        return status.HTTP_404_NOT_FOUND, "not_found", "Resource not found.", None
    if isinstance(exc, NotAuthenticated):
        return status.HTTP_401_UNAUTHORIZED, "unauthenticated", "Authentication is required.", None
    if isinstance(exc, PermissionDenied):
        return (
            status.HTTP_403_FORBIDDEN,
            "permission_denied",
            "You do not have permission to perform this action.",
            None,
        )
    if isinstance(exc, IntegrityError):
        return (
            status.HTTP_409_CONFLICT,
            "integrity_error",
            "The request conflicts with existing data.",
            None,
        )
    if isinstance(exc, APIException):
        fallback = DEFAULT_CODES.get(exc.status_code, "error")
        default = str(getattr(exc, "default_code", "") or fallback)
        return (
            exc.status_code,
            _detail_code(exc.detail, default),
            str(exc.detail),
            getattr(exc, "errors", None),
        )
    if isinstance(exc, TenantContextMissing):
        # Server misconfiguration, not a client error: a tenant-scoped query was
        # reached without a bound tenant, so the request cannot be answered
        # correctly at all. `internal_error` and "An unexpected error occurred"
        # is actively harmful here - it sends an operator hunting a bug in the
        # endpoint when the fix is one environment variable. Named after the
        # cause so it is greppable in the logs.
        return (
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "tenant_context_missing",
            (
                "This request could not be attributed to a practice, so tenant-scoped "
                "data cannot be read. Set DJANGO_DEFAULT_TENANT_SLUG, or address the "
                "API by tenant subdomain."
            ),
            None,
        )
    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
        None,
    )


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """DRF EXCEPTION_HANDLER producing the plan's single error envelope.

    DRF handles the exception first (so auth/permission/throttle headers such
    as `WWW-Authenticate` and `Retry-After` survive), then the body is
    normalised to `{"error": {code, message, details}}`.
    """
    drf_response = drf_exception_handler(exc, context)
    status_code, code, message, details = _normalise(exc)

    if drf_response is None:
        logger.error(
            "unhandled_exception",
            exc_info=exc,
            path=getattr(context.get("request"), "path", None),
        )
        response = Response(status=status_code)
    else:
        response = drf_response
        status_code = drf_response.status_code

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
