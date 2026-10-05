from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIRequestFactory

from common.exceptions import (
    BusinessRuleException,
    ConflictError,
    InvalidStateTransitionError,
    SlotUnavailableError,
    api_exception_handler,
)

pytestmark = pytest.mark.unit


def _handler() -> tuple[object, dict[str, object]]:
    request = APIRequestFactory().get("/api/v1/whatever/")
    return Http404(), {"request": request}


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (Http404(), status.HTTP_404_NOT_FOUND, "not_found"),
        (NotAuthenticated(), status.HTTP_401_UNAUTHORIZED, "unauthenticated"),
        (PermissionDenied(), status.HTTP_403_FORBIDDEN, "permission_denied"),
        (
            DRFValidationError({"email": ["required"]}),
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
        ),
        (
            DjangoValidationError({"email": ["required"]}),
            status.HTTP_400_BAD_REQUEST,
            "validation_error",
        ),
        (SlotUnavailableError(), status.HTTP_409_CONFLICT, "slot_unavailable"),
        (InvalidStateTransitionError(), status.HTTP_409_CONFLICT, "invalid_state_transition"),
        (ConflictError(), status.HTTP_409_CONFLICT, "conflict"),
    ],
)
def test_error_envelope_shape(exc: Exception, expected_status: int, expected_code: str) -> None:
    request = APIRequestFactory().get("/api/v1/whatever/")
    response = api_exception_handler(exc, {"request": request})

    assert response is not None
    assert response.status_code == expected_status
    assert set(response.data) == {"error"}
    assert set(response.data["error"]) == {"code", "message", "details"}
    assert response.data["error"]["code"] == expected_code


def test_validation_details_are_preserved() -> None:
    request = APIRequestFactory().post("/api/v1/whatever/")
    exc = DRFValidationError({"phone": ["This field is required."]})

    response = api_exception_handler(exc, {"request": request})

    assert response is not None
    assert response.data["error"]["details"] == {"phone": ["This field is required."]}


def test_unhandled_exception_becomes_500() -> None:
    request = APIRequestFactory().get("/api/v1/whatever/")

    response = api_exception_handler(RuntimeError("boom"), {"request": request})

    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["error"]["code"] == "internal_error"
    assert response.data["error"]["details"] is None


def test_business_rule_exception_carries_custom_details() -> None:
    request = APIRequestFactory().post("/api/v1/whatever/")
    exc = BusinessRuleException("nope", code="teapot", errors={"slot": "11:30"})

    response = api_exception_handler(exc, {"request": request})

    assert response is not None
    assert response.data["error"] == {
        "code": "teapot",
        "message": "nope",
        "details": {"slot": "11:30"},
    }


def test_inherits_status_code() -> None:
    assert issubclass(ConflictError, BusinessRuleException)
    assert issubclass(SlotUnavailableError, ConflictError)
    assert SlotUnavailableError.default_code == "slot_unavailable"
