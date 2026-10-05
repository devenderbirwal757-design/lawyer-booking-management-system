"""`RazorpayGateway` - the live implementation (plan §6, decision D1).

Talks to Razorpay's REST API over `urllib` (no vendor SDK, no new dependency)
and, more importantly, owns the two things a payment backend must get right:
the webhook HMAC over the raw bytes, and mode isolation.

Amounts cross the wire as integer paise. The database keeps `Decimal` rupees
(PRD §12): converting once, here, at the boundary is what keeps ₹0.01 from
drifting (S §A5).
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.payments.gateways.base import (
    GatewayOrder,
    GatewayPayment,
    GatewayUnavailableError,
    PaymentGateway,
)

logger = logging.getLogger(__name__)

#: Razorpay order statuses, mapped onto our vocabulary. An order the gateway
#: reports as anything else is left to the caller to interpret as "still open".
_ORDER_STATUS_MAP = {
    "created": "PENDING",
    "authorized": "PENDING",
    "paid": "SUCCESS",
    "attempted": "FAILED",
    "failed": "FAILED",
}


class RazorpayGateway(PaymentGateway):
    name = "razorpay"

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        mode: str = "test",
        timeout: int = 10,
        base_url: str = "https://api.razorpay.com/v1",
    ) -> None:
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.mode = mode
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ orders
    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> GatewayOrder:
        payload = {
            "amount": self.to_minor(amount),
            "currency": currency,
            "receipt": receipt,
            "notes": {k: str(v) for k, v in (notes or {}).items()},
        }
        data = self._request("POST", "/orders", json_body=payload)
        return self._to_order(data)

    def fetch_order(self, gateway_order_id: str) -> GatewayOrder | None:
        try:
            data = self._request("GET", f"/orders/{gateway_order_id}")
        except GatewayUnavailableError as exc:
            # A 404 from the fetch endpoint means "no such order", which is a
            # legitimate answer to "what does the gateway think?". Anything else
            # is a transport problem and stays an error.
            if exc.args and exc.args[0] == 404:
                return None
            raise
        return self._to_order(data)

    def fetch_payment(self, gateway_payment_id: str) -> GatewayPayment | None:
        try:
            data = self._request("GET", f"/payments/{gateway_payment_id}")
        except GatewayUnavailableError as exc:
            if exc.args and exc.args[0] == 404:
                return None
            raise
        return self._to_payment(data)

    def fetch_order_payments(self, gateway_order_id: str) -> list[GatewayPayment]:
        """Payments the gateway recorded against an order.

        Needed because Razorpay's `order.paid` event - and the order endpoint
        itself - do not carry a payment id, so a capture can only be recorded
        once we know which payment it was.
        """
        data = self._request("GET", f"/orders/{gateway_order_id}/payments")
        entity = data.get("payments")
        if not isinstance(entity, list):
            return []
        return [self._to_payment(item) for item in entity if isinstance(item, dict)]

    # -------------------------------------------------------------- signatures
    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256 over the exact bytes the gateway sent.

        The caller passes `request.body` untouched. Parsing and re-dumping the
        JSON first would reorder keys and normalise whitespace, and the digest
        would stop matching a delivery that is perfectly genuine (S §A5).
        """
        if not self.webhook_secret or not signature:
            return False
        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, "sha256").hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_checkout_signature(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        signature: str,
    ) -> bool:
        if not self.key_secret or not signature:
            return False
        expected = hmac.new(
            self.key_secret.encode("utf-8"),
            f"{gateway_order_id}|{gateway_payment_id}".encode(),
            "sha256",
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign_webhook_payload(self, raw_body: bytes) -> str:
        """Test/helper hook: the signature a delivery of `raw_body` carries.

        Production never calls this - the gateway signs. It exists so the
        signature tests can produce a *real* HMAC instead of asserting against
        a fixture string that rots the day the secret changes.
        """
        return hmac.new(self.webhook_secret.encode("utf-8"), raw_body, "sha256").hexdigest()

    # ---------------------------------------------------------------- refunds
    def create_refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> str:
        # Reachable only from a future automatic-refund feature (plan §6.2).
        payload: dict[str, Any] = {"amount": self.to_minor(amount)}
        if reason:
            payload["notes"] = {"reason": reason}
        data = self._request("POST", f"/payments/{gateway_payment_id}/refund", json_body=payload)
        refund_id = str(data.get("id") or "")
        if not refund_id:
            raise GatewayUnavailableError("Razorpay refund response carried no id")
        return refund_id

    # ----------------------------------------------------------------- mapping
    def _to_order(self, data: dict[str, Any]) -> GatewayOrder:
        order_id = str(data.get("id") or "")
        if not order_id:
            raise GatewayUnavailableError("Razorpay order response carried no id")
        try:
            amount_minor = int(data.get("amount") or 0)
        except (TypeError, ValueError) as exc:
            raise GatewayUnavailableError("Razorpay order amount was not an integer") from exc
        return GatewayOrder(
            gateway_order_id=order_id,
            amount_minor=amount_minor,
            currency=str(data.get("currency") or "INR"),
            status=_ORDER_STATUS_MAP.get(str(data.get("status") or "").lower(), "PENDING"),
            receipt=str(data.get("receipt") or ""),
            raw=data,
        )

    def _to_payment(self, data: dict[str, Any]) -> GatewayPayment:
        payment_id = str(data.get("id") or "")
        if not payment_id:
            raise GatewayUnavailableError("Razorpay payment response carried no id")
        try:
            amount_minor = int(data.get("amount") or 0)
        except (TypeError, ValueError) as exc:
            raise GatewayUnavailableError("Razorpay payment amount was not an integer") from exc
        method = data.get("method")
        if isinstance(method, dict):
            method = str(method.get("type") or "")
        return GatewayPayment(
            gateway_payment_id=payment_id,
            gateway_order_id=str(data.get("order_id") or ""),
            amount_minor=amount_minor,
            currency=str(data.get("currency") or "INR"),
            status=str(data.get("status") or ""),
            method=str(method or ""),
            failure_reason=str(data.get("error_description") or ""),
            raw=data,
        )

    # ------------------------------------------------------------------- http
    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        request.add_header(
            "Authorization",
            f"Basic {base64.b64encode(f'{self.key_id}:{self.key_secret}'.encode()).decode()}",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace")
            logger.warning("razorpay %s %s failed: %s %s", method, path, exc.code, detail)
            raise GatewayUnavailableError(exc.code, detail) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("razorpay %s %s unreachable: %s", method, path, exc)
            raise GatewayUnavailableError(0, str(exc)) from exc

        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise GatewayUnavailableError("Razorpay returned non-JSON") from exc
        if not isinstance(parsed, dict):
            raise GatewayUnavailableError("Razorpay returned a non-object body")
        return parsed

    @staticmethod
    def decimal_from_minor(amount_minor: int) -> Decimal:
        try:
            return (Decimal(int(amount_minor)) / 100).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise GatewayUnavailableError("Unusable gateway amount") from exc


__all__ = ("RazorpayGateway",)
