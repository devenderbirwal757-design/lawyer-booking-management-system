"""Domain errors for the OTP flow (plan §4, S §A3).

`InvalidOtpError` is deliberately one generic message for every failure mode -
wrong code, expired code, unknown phone, no code issued - so the verify
endpoint is not an "is this number on file" oracle. `OtpThrottledError` uses
the same `throttled` machine code the DRF throttles emit, so clients handle one
abuse response.
"""

from __future__ import annotations

from rest_framework import status

from common.exceptions import BusinessRuleException


class InvalidOtpError(BusinessRuleException):
    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_otp"
    default_detail = "The verification code is invalid or has expired."


class OtpThrottledError(BusinessRuleException):
    status_code: int = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "throttled"
    default_detail = "Too many OTP requests. Please try again later."


__all__ = ("InvalidOtpError", "OtpThrottledError")
