"""OTP delivery channels (plan §4, S §A3).

SMS/WhatsApp are Phase 7 (`apps.notifications` owns the real channels). Phase 4
ships a `console` backend that prints the code to stdout so a developer can run
the flow end-to-end; it is the documented dev default and never used in
production (selection is via `DJANGO_OTP_SMS_BACKEND`, and any other backend
name raises instead of silently pretending to send).

The code reaches *stdout*, never a logger: S §A3 forbids the code from appearing
in logs, Sentry breadcrumbs or error reports, and `structlog` records would be
exactly that. `send-otp` feed the console backend, and the test suite asserts
no logging record contains the code.
"""

from __future__ import annotations

import sys
from typing import Protocol


class OtpSender(Protocol):
    """Deliver a code to its phone. Phase 7 replaces this with real SMS."""

    def send(self, phone: str, code: str) -> None: ...


class ConsoleOtpSender:
    """Write the code to stdout, visibly marked as developer-only."""

    def send(self, phone: str, code: str) -> None:
        print(f"[dev-otp] OTP for {phone}: {code}", file=sys.stdout)


_BACKENDS: dict[str, OtpSender] = {
    "console": ConsoleOtpSender(),
}


def get_sender() -> OtpSender:
    from django.conf import settings

    name = str(getattr(settings, "OTP_SMS_BACKEND", "console")).strip().lower()
    sender = _BACKENDS.get(name)
    if sender is None:
        raise RuntimeError(
            f"Unknown DJANGO_OTP_SMS_BACKEND {name!r} - only {sorted(_BACKENDS)} exist "
            "in Phase 4; SMS arrives with Phase 7."
        )
    return sender


def send_otp(phone: str, code: str) -> bool:
    """Deliver a code. Raises if no usable backend is configured."""
    get_sender().send(phone, code)
    return True


__all__ = ("ConsoleOtpSender", "OtpSender", "get_sender", "send_otp")
