"""A `PaymentGateway` test double (plan §6).

Real HMAC, real HMAC comparison, deterministic ids - so the signature tests
prove the production code path rather than a mock's idea of it. Only the
network is faked, via `truth_for()` / `payments_for()` and `unavailable`.

`create_order` mints ids from a counter instead of a random uuid so a failing
assertion names a specific order.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from decimal import Decimal

from apps.payments.gateways.base import (
    GatewayOrder,
    GatewayPayment,
    GatewayUnavailableError,
    PaymentGateway,
)

WEBHOOK_SECRET = "whsec_test_secret"
KEY_SECRET = "key_secret_test"


class FakeGateway(PaymentGateway):
    name = "razorpay"

    def __init__(
        self,
        *,
        mode: str = "test",
        secret: str = WEBHOOK_SECRET,
        unavailable: bool = False,
    ) -> None:
        self.mode = mode
        self.secret = secret
        self.unavailable = unavailable
        self.counter = 0
        self.orders: dict[str, GatewayOrder] = {}
        self.payments: dict[str, list[GatewayPayment]] = {}
        self.order_truth: dict[str, Callable[[], GatewayOrder | None]] = {}
        self.key_id = "rzp_test_key"
        self.key_secret = KEY_SECRET
        self.created: list[Decimal] = []

    # ------------------------------------------------------------- interface
    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> GatewayOrder:
        if self.unavailable:
            raise GatewayUnavailableError(0, "fake gateway offline")
        self.counter += 1
        order = GatewayOrder(
            gateway_order_id=f"order_test_{self.counter}",
            amount_minor=self.to_minor(amount),
            currency=currency,
            status="PENDING",
            receipt=receipt,
            raw={"notes": notes or {}},
        )
        self.orders[order.gateway_order_id] = order
        self.created.append(amount)
        return order

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self.secret.encode(), raw_body, "sha256").hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_checkout_signature(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> bool:
        expected = hmac.new(
            self.key_secret.encode(),
            f"{gateway_order_id}|{gateway_payment_id}".encode(),
            "sha256",
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def fetch_order(self, gateway_order_id: str) -> GatewayOrder | None:
        if self.unavailable:
            raise GatewayUnavailableError(0, "fake gateway offline")
        override = self.order_truth.get(gateway_order_id)
        if override is not None:
            return override()
        return self.orders.get(gateway_order_id)

    def fetch_order_payments(self, gateway_order_id: str) -> list[GatewayPayment]:
        if self.unavailable:
            raise GatewayUnavailableError(0, "fake gateway offline")
        return self.payments.get(gateway_order_id, [])

    def create_refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> str:
        return f"rfnd_test_{gateway_payment_id}"

    # ----------------------------------------------------------------- setup
    def sign(self, raw_body: bytes) -> str:
        """The signature a delivery of `raw_body` would carry."""
        return hmac.new(self.secret.encode(), raw_body, "sha256").hexdigest()

    def truth_for(self, gateway_order_id: str, status: str) -> None:
        """Pin what `fetch_order` reports for an order."""
        existing = self.orders.get(gateway_order_id)
        amount_minor = existing.amount_minor if existing else 50000
        currency = existing.currency if existing else "INR"
        self.order_truth[gateway_order_id] = lambda: GatewayOrder(
            gateway_order_id=gateway_order_id,
            amount_minor=amount_minor,
            currency=currency,
            status=status,
        )

    def captured_payment(
        self,
        gateway_order_id: str,
        *,
        payment_id: str = "pay_test_1",
        amount_minor: int = 50000,
        method: str = "upi",
    ) -> GatewayPayment:
        payment = GatewayPayment(
            gateway_payment_id=payment_id,
            gateway_order_id=gateway_order_id,
            amount_minor=amount_minor,
            currency="INR",
            status="captured",
            method=method,
        )
        self.payments.setdefault(gateway_order_id, []).append(payment)
        return payment

    def money_nowhere(self, gateway_order_id: str) -> None:
        """An order the gateway reports as paid but with no captured payment."""
        self.truth_for(gateway_order_id, "SUCCESS")
        self.payments[gateway_order_id] = []


__all__ = ("KEY_SECRET", "WEBHOOK_SECRET", "FakeGateway")
