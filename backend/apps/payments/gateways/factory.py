"""Gateway selection from settings (plan §6) - the only place a vendor name is read.

Two rules, both enforced here rather than trusted to configuration hygiene:

- `PAYMENT_GATEWAY` must be a name this build actually implements. A typo is a
  startup error, not a runtime surprise on the first booking.
- A non-Razorpay gateway is refused outright, so the process cannot boot
  against a stub in production (S §A5: "production refuses to start with
  `PAYMENT_GATEWAY=stub`").
"""

from __future__ import annotations

from django.conf import settings

from apps.payments.gateways.base import PaymentGateway
from apps.payments.gateways.cashfree import CashfreeGateway
from apps.payments.gateways.razorpay import RazorpayGateway

#: name -> (class, usable in production?)
GATEWAYS: dict[str, tuple[type[PaymentGateway], bool]] = {
    RazorpayGateway.name: (RazorpayGateway, True),
    CashfreeGateway.name: (CashfreeGateway, False),
}


class GatewayConfigurationError(RuntimeError):
    """`PAYMENT_GATEWAY` names something this build cannot safely run."""


def build_gateway(name: str | None = None) -> PaymentGateway:
    """Instantiate the configured gateway."""
    key = (name or settings.PAYMENT_GATEWAY or RazorpayGateway.name).strip().lower()
    entry = GATEWAYS.get(key)
    if entry is None:
        raise GatewayConfigurationError(
            f"Unknown PAYMENT_GATEWAY={key!r}; expected one of {sorted(GATEWAYS)}."
        )
    gateway_cls, production_ready = entry
    if not production_ready and not settings.DEBUG:
        raise GatewayConfigurationError(
            f"PAYMENT_GATEWAY={key!r} is a stub and must not run outside DEBUG."
        )
    if gateway_cls is RazorpayGateway:
        return RazorpayGateway(
            key_id=settings.RAZORPAY_KEY_ID,
            key_secret=settings.RAZORPAY_KEY_SECRET,
            webhook_secret=settings.RAZORPAY_WEBHOOK_SECRET,
            mode=settings.PAYMENT_MODE,
        )
    return gateway_cls()


def get_gateway() -> PaymentGateway:
    """The gateway for the current request/task."""
    return build_gateway()


__all__ = (
    "GATEWAYS",
    "GatewayConfigurationError",
    "build_gateway",
    "get_gateway",
)
