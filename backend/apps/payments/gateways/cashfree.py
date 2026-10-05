"""`CashfreeGateway` - the stub that proves the seam is real (plan §6).

The plan requires a second implementation so the interface is not accidentally
shaped around one vendor. This one raises `NotImplementedError` from every
operation instead of pretending to work, which is the useful behaviour: if any
code path ever selects Cashfree by configuration, it fails loudly and
immediately instead of silently accepting payments it never verified.

Selecting it in production is a configuration error, not a supported state
(S §A5: production refuses to start with a test double).
"""

from __future__ import annotations

from decimal import Decimal

from apps.payments.gateways.base import GatewayOrder, GatewayPayment, PaymentGateway

_MESSAGE = (
    "Cashfree is not implemented in this MVP. Accepted gateway names: razorpay. "
    "Decision D1 selects Razorpay."
)


class CashfreeGateway(PaymentGateway):
    name = "cashfree"

    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> GatewayOrder:
        raise NotImplementedError(_MESSAGE)

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        raise NotImplementedError(_MESSAGE)

    def verify_checkout_signature(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> bool:
        raise NotImplementedError(_MESSAGE)

    def fetch_order(self, gateway_order_id: str) -> GatewayOrder | None:
        raise NotImplementedError(_MESSAGE)

    def fetch_payment(self, gateway_payment_id: str) -> GatewayPayment | None:
        raise NotImplementedError(_MESSAGE)


__all__ = ("CashfreeGateway",)
