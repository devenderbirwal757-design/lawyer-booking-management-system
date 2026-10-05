from __future__ import annotations

import pytest

from common.money import currency_symbol, format_price

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_format_price_whole_amounts_drop_decimals() -> None:
    assert format_price("500.00", "INR") == "₹500"
    assert format_price(300, "INR") == "₹300"
    assert format_price("700.00", "INR") == "₹700"


def test_format_price_keeps_fractional_money() -> None:
    assert format_price("500.50", "INR") == "₹500.50"
    assert format_price("0.05", "USD") == "$0.05"


def test_format_price_decimal_and_int_inputs() -> None:
    from decimal import Decimal

    assert format_price(Decimal("25"), "USD") == "$25"
    assert format_price(Decimal("25.99"), "USD") == "$25.99"


def test_unknown_currency_degrades_to_code_not_a_symbol() -> None:
    assert format_price("100", "XYZ") == "XYZ 100"


def test_currency_symbol_is_case_insensitive() -> None:
    assert currency_symbol("inr") == "₹"
    assert currency_symbol("usd") == "$"
    assert currency_symbol(None) == ""
