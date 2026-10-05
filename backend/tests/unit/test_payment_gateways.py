"""The gateway seam (plan §6, security.md §A5).

The gateway is the only place a vendor name is read and the only place money
crosses the wire, so its guards are tested without a database and without a
network:

- a typo in `PAYMENT_GATEWAY` is a startup error, not a surprise on the first
  real booking;
- a stub gateway refuses to build when `DEBUG` is off, so production cannot
  come up talking to an implementation that raises from every call;
- the webhook HMAC is computed over the exact bytes received, so reordering
  keys or changing whitespace invalidates it (and, symmetrically, a genuine
  delivery is never rejected for cosmetic reasons);
- amounts convert to integer paise by rounding, never by truncation, so a
  sub-paisa amount cannot be silently undercharged.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.payments.gateways import (
    CashfreeGateway,
    GatewayConfigurationError,
    RazorpayGateway,
    build_gateway,
)

SECRET = "whsec_test_secret"


def _gateway(**overrides: str) -> RazorpayGateway:
    return RazorpayGateway(
        key_id=overrides.get("key_id", "rzp_test_key"),
        key_secret=overrides.get("key_secret", "key_secret"),
        webhook_secret=overrides.get("webhook_secret", SECRET),
        mode=overrides.get("mode", "test"),
    )


# ------------------------------------------------------------------ factory
def test_an_unknown_gateway_name_is_a_startup_error() -> None:
    """`PAYMENT_GATEWAY=razorpayy` must not silently fall back to anything."""
    with pytest.raises(GatewayConfigurationError) as excinfo:
        build_gateway("razorpayy")
    assert "razorpayy" in str(excinfo.value)


def test_a_stub_gateway_is_refused_when_debug_is_off() -> None:
    """security.md §A5: production refuses to start against a test double.

    The test settings run with `DEBUG = False`, which is exactly the condition
    this guards.
    """
    with pytest.raises(GatewayConfigurationError) as excinfo:
        build_gateway("cashfree")
    assert "cashfree" in str(excinfo.value)


@override_settings(DEBUG=True)
def test_a_stub_gateway_loads_only_under_debug() -> None:
    """Under `DEBUG` it *builds* - so local work is possible - but still raises.

    Building is not working: `CashfreeGateway` raises from every method, so a
    code path that reaches one fails loudly instead of accepting payments that
    were never verified.
    """
    gateway = build_gateway("cashfree")
    assert isinstance(gateway, CashfreeGateway)
    with pytest.raises(NotImplementedError):
        gateway.create_order(amount=Decimal("100.00"), currency="INR", receipt="r1")


def test_the_configured_gateway_comes_from_settings() -> None:
    with override_settings(
        PAYMENT_GATEWAY="razorpay",
        RAZORPAY_KEY_ID="rzp_live_key",
        RAZORPAY_KEY_SECRET="live_secret",
        RAZORPAY_WEBHOOK_SECRET="live_webhook_secret",
        PAYMENT_MODE="live",
    ):
        gateway = build_gateway()
    assert isinstance(gateway, RazorpayGateway)
    # The mode is operator-supplied and never inferred from the key material:
    # setting it wrong is exactly what the order/event mode check catches.
    assert gateway.mode == "live"
    assert gateway.key_id == "rzp_live_key"


# --------------------------------------------------------------- signatures
def test_a_genuine_webhook_signature_verifies() -> None:
    raw_body = b'{"event":"payment.captured","payload":{}}'
    gateway = _gateway()
    assert gateway.verify_signature(raw_body, gateway.sign_webhook_payload(raw_body)) is True


def test_the_signature_covers_the_exact_bytes_received() -> None:
    """Reordering keys or reflowing whitespace changes the digest.

    This is the proof that verification happens on `request.body` rather than
    on a re-serialized `request.data`: a parse-then-verify implementation would
    accept all three of these bodies interchangeably.
    """
    gateway = _gateway()
    body = b'{"a": 1, "b": 2}'
    signature = gateway.sign_webhook_payload(body)

    assert gateway.verify_signature(body, signature) is True
    assert gateway.verify_signature(b'{"b": 2, "a": 1}', signature) is False
    assert gateway.verify_signature(b'{"a":1,"b":2}', signature) is False


def test_a_tampered_body_fails_verification() -> None:
    gateway = _gateway()
    body = b'{"amount": 50000}'
    signature = gateway.sign_webhook_payload(body)
    tampered = json.dumps({"amount": 100}).encode()
    assert gateway.verify_signature(tampered, signature) is False


def test_a_missing_or_empty_signature_is_refused_not_guessed() -> None:
    gateway = _gateway()
    body = b'{"a": 1}'
    assert gateway.verify_signature(body, "") is False
    assert gateway.verify_signature(body, "0" * 64) is False


def test_a_missing_webhook_secret_refuses_everything() -> None:
    """With no secret there is nothing to verify against, so nothing passes."""
    gateway = _gateway(webhook_secret="")
    body = b'{"a": 1}'
    assert gateway.verify_signature(body, gateway.sign_webhook_payload(body)) is False


def test_the_checkout_signature_binds_the_order_to_the_payment() -> None:
    """`order_id|payment_id` - swapping either half must not verify."""
    gateway = _gateway(key_secret="checkout_secret")
    import hmac

    signature = hmac.new(b"checkout_secret", b"order_1|pay_1", "sha256").hexdigest()

    assert (
        gateway.verify_checkout_signature(
            gateway_order_id="order_1",
            gateway_payment_id="pay_1",
            signature=signature,
        )
        is True
    )
    # The same signature replayed against a different payment is refused.
    assert (
        gateway.verify_checkout_signature(
            gateway_order_id="order_1",
            gateway_payment_id="pay_2",
            signature=signature,
        )
        is False
    )


# ------------------------------------------------------------------ amounts
def test_amounts_cross_the_wire_as_rounded_paise() -> None:
    gateway = _gateway()
    assert gateway.to_minor(Decimal("500.00")) == 50000
    # Rounded, never truncated: dropping a paisa is a silent undercharge.
    assert gateway.to_minor(Decimal("10.005")) == 1001
    assert gateway.to_minor(Decimal("0.01")) == 1


def test_minor_units_convert_back_without_drift() -> None:
    gateway = _gateway()
    for rupees in ("0.01", "1.00", "99.99", "1234.56", "250000.75"):
        assert gateway.from_minor(gateway.to_minor(Decimal(rupees)), "INR") == Decimal(rupees)


def test_one_paise_survives_many_charges() -> None:
    """The round-trip is exact, so repeated small charges never accumulate
    rounding error the way float arithmetic would."""
    gateway = _gateway()
    total = sum(
        (gateway.from_minor(gateway.to_minor(Decimal("0.01")), "INR") for _ in range(100)),
        Decimal("0.00"),
    )
    assert total == Decimal("1.00")
