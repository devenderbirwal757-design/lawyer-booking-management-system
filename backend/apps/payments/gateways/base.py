"""The gateway seam (plan §6, PRD §11 "Payment abstraction").

    PaymentGateway
        ├── RazorpayGateway     live implementation (D1)
        ├── CashfreeGateway     NotImplementedError stub
        └── (future providers)

Four operations, declared once, so the services never import a vendor SDK:
`create_order`, `verify_signature`, `fetch_order`, `create_refund`. The last
one is intentionally unused in the MVP (plan §6.2, D2) - refunds are manual -
but it stays on the interface so adding an automatic path later is an
implementation, not an interface change.

Two signature checks, because they are not the same thing:

- `verify_signature` guards the *webhook*: HMAC over the **raw request bytes**.
  The service hands it the untouched body; nothing may re-serialize the JSON
  first, or key order and whitespace change the digest and a legitimate
  delivery fails verification.
- `verify_checkout_signature` guards the *client's* return from checkout, over
  the `order_id|payment_id` pair the gateway returns to the browser.

Both compare in constant time. A `==` on an HMAC leaks the digest one byte at a
time to anyone who can time the response (S §A5).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


class GatewayError(Exception):
    """Any failure talking to, or trusting, a payment gateway."""


class GatewayUnavailableError(GatewayError):
    """The gateway could not be reached or answered unusably.

    Distinct from a *rejection* (bad signature, unknown order): this one means
    "we do not know", so callers retry or fall back to reconciliation rather
    than treating it as a definitive no.
    """


@dataclass(frozen=True, slots=True)
class GatewayOrder:
    """What the gateway says about an order, normalised.

    `amount_minor`/`currency` are the gateway's own echo of what we asked for.
    The service compares them against the database row: a gateway that charged
    a different number than the order says is a reconciliation failure, not a
    payment.
    """

    gateway_order_id: str
    amount_minor: int
    currency: str
    status: str
    receipt: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GatewayPayment:
    gateway_payment_id: str
    gateway_order_id: str
    amount_minor: int
    currency: str
    status: str
    method: str = ""
    failure_reason: str = ""
    raw: dict[str, object] = field(default_factory=dict)


class PaymentGateway(abc.ABC):
    """Provider-agnostic payment operations."""

    #: Stable provider key, stored on orders/payments so a row always says
    #: which gateway produced it.
    name: str = ""

    #: `test` or `live`. Orders are stamped with the mode of the gateway that
    #: created them, and an event is only applied to an order of the same mode.
    mode: str = "test"

    @abc.abstractmethod
    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> GatewayOrder:
        """Create an order at the gateway for an amount we computed server-side.

        Raises `GatewayUnavailableError` when the call cannot be completed.
        """

    @abc.abstractmethod
    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """Constant-time check of a webhook signature over the raw body."""

    @abc.abstractmethod
    def verify_checkout_signature(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> bool:
        """Constant-time check of the signature handed back to the client."""

    @abc.abstractmethod
    def fetch_order(self, gateway_order_id: str) -> GatewayOrder | None:
        """Read the gateway's current truth for an order.

        `None` when the gateway has no such order - an order id we never
        created is not an error to raise over, it is simply "no truth".
        """

    def fetch_order_payments(self, gateway_order_id: str) -> list[GatewayPayment]:
        """Every payment the gateway has against an order.

        Optional, and optional is meaningful: a provider that cannot list
        payments can only ever confirm from a `payment.captured` event that
        carries an id, so reconciliation for it degrades to "ask the client to
        poll" instead of inventing a payment row.
        """
        raise NotImplementedError(f"{type(self).__name__} cannot list order payments.")

    def create_refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> str:
        """Refund at the gateway. Unused in the MVP (plan §6.2, D2)."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support automatic refunds; "
            "Phase 6 refunds are settled manually in the gateway dashboard."
        )

    def to_minor(self, amount: Decimal) -> int:
        """Decimal currency units to the gateway's integer minor units (paise).

        Rounded half **up**, and never truncated: dropping a paisa is a silent
        undercharge. `Decimal.quantize` defaults to banker's rounding, which
        sends an exact half-paisa to the nearest even number - so `10.005` would
        become `1000`, undercharging by one paisa. Every amount the services
        pass here is already quantised to `0.01`, so this only ever decides the
        tie-break, but the tie-break has to round up.
        """
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def from_minor(self, amount_minor: int, currency: str) -> Decimal:
        return (Decimal(amount_minor) / 100).quantize(Decimal("0.01"))


__all__ = (
    "GatewayError",
    "GatewayOrder",
    "GatewayPayment",
    "GatewayUnavailableError",
    "PaymentGateway",
)
