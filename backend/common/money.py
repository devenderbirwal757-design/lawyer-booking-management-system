"""Display helpers for money (plan §3 `price_amount` + `currency`).
Prices are stored as `Decimal` and the ISO code; presentation ("₹500") is a
view concern, so the formatter lives beside the store, not in the model.
Unknown currencies degrade to the code plus a space, never a guessed symbol.
"""

from __future__ import annotations

from decimal import Decimal

#: Symbols for the currencies the platform is likely to meet. The map is
#: short on purpose: an unknown code must render something honest, not guess.
_CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
    "SGD": "S$",
    "AUD": "A$",
    "CAD": "C$",
    "JPY": "¥",
    "CNY": "¥",
}


def currency_symbol(currency: str | None) -> str:
    """Symbol for a 3-letter ISO code, the code itself if unknown, or '' if none."""
    code = (currency or "").upper()
    if not code:
        return ""
    return _CURRENCY_SYMBOLS.get(code, f"{code} ")


def format_price(amount: Decimal | int | str, currency: str = "INR") -> str:
    """Render a stored price for display, e.g. `₹500` or `₹500.50`.

    Whole amounts drop the decimals (`₹500`, matching the PRD §5.2 table);
    fractional amounts keep exactly the money that was stored.
    """
    value = Decimal(amount)
    if value != value.to_integral_value():
        value = value.quantize(Decimal("0.01"))
        body = format(value, "f")
    else:
        body = str(int(value))
    return f"{currency_symbol(currency)}{body}"


__all__ = ("currency_symbol", "format_price")
