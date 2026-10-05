"""E.164 phone normalisation (plan §6.3, S §A3 line: "no duplicate customers").

The plan demands that `+91 98765 43210`, `91 98765 43210` and `0 98765 43210`
all reduce to the same canonical string so they cannot create three customers.
"""

from __future__ import annotations

import pytest

from apps.customers.phone import PhoneValidationError, normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "+919876543210"),
        ("91 98765 43210", "+919876543210"),
        ("0 98765 43210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("+1 (415) 555-2671", "+14155552671"),
        ("00 44 20 7946 0958", "+442079460958"),
        ("+33 6 12 34 56 78", "+33612345678"),
        ("  +91 98765 43210  ", "+919876543210"),
    ],
)
def test_normalize_phone_reduces_to_canonical_e164(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        None,
        "12345",
        "abc",
        "+",
        "+123",
        "+99999999999999999",
    ],
)
def test_normalize_phone_rejects_invalid_input(raw: str | None) -> None:
    with pytest.raises(PhoneValidationError):
        normalize_phone(raw)
