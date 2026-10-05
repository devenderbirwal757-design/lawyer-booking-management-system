"""E.164 phone normalisation (plan §6.3, S §A3).

Phone numbers are the customer identity key, so every path that touches one -
OTP lookups, `Customer` writes - must first reduce it to a canonical E.164
string. Otherwise `+91 98765 43210`, `91 98765 43210` and `0 98765 43210` would
all create distinct customers (S §A3: "Phone numbers normalised (E.164) before
lookup").

No phone-number library is in the dependency tree, so the reduction is a small
deterministic routine with one configurable assumption: an input that carries no
`+` is treated as a *national* number whose country code is the configured
default (`DJANGO_DEFAULT_COUNTRY_CODE`, default `+91`). The rules:

- A leading `+` is kept; `00` is converted to `+` (the international prefix).
- Without a leading `+`, a leading national trunk prefix `0` is stripped, and:
  - 10 digits are left  ->  `{default_country}{digits}` (national form)
  - 11+ digits are left ->  `+{digits}` (international form typed without `+`)
- Only `+`, digits and the separators space/dash/paren/dot are accepted; any
  other character is rejected. The result must be `+` followed by 7-15 digits
  (the E.164 length bound).

These rules make the three spellings above converge on `+919876543210`, which
is the behaviour the identity model depends on. The assumption is documented in
`config/paths.py` so an operator can point the default at their own country.
"""

from __future__ import annotations

from django.conf import settings


class PhoneValidationError(ValueError):
    """Raised when a string cannot be reduced to a valid E.164 number."""


_SEPARATORS = frozenset(" .-()")
_DIGITS = frozenset("0123456789")
_MIN_TOTAL_DIGITS = 8
_MAX_TOTAL_DIGITS = 15
_MIN_SUBSCRIBER_DIGITS = 7
_MAX_SUBSCRIBER_DIGITS = 10


def default_country_code() -> str:
    """The country code assumed for `+`-less input, e.g. `+91`."""
    raw = getattr(settings, "DEFAULT_COUNTRY_CODE", "+91")
    value = str(raw).strip()
    if not value.startswith("+"):
        value = "+" + value
    return value


def normalize_phone(raw: str | None) -> str:
    """Reduce `raw` to a canonical E.164 string, or raise `PhoneValidationError`."""
    if raw is None:
        raise PhoneValidationError("A phone number is required.")
    text = raw.strip()
    if not text:
        raise PhoneValidationError("A phone number is required.")

    if text.startswith("00"):
        text = "+" + text[2:]

    if text.startswith("+"):
        digits = _number_digits(text[1:])
        result = "+" + digits
    else:
        digits = _number_digits(text).lstrip("0")
        if not digits:
            raise PhoneValidationError("A phone number is required.")
        if len(digits) >= 11:
            result = "+" + digits
        else:
            if not (_MIN_SUBSCRIBER_DIGITS <= len(digits) <= _MAX_SUBSCRIBER_DIGITS):
                raise PhoneValidationError("Enter a valid phone number.")
            result = default_country_code() + digits

    total_digits = len(result) - 1
    if not (_MIN_TOTAL_DIGITS <= total_digits <= _MAX_TOTAL_DIGITS):
        raise PhoneValidationError("Enter a valid phone number.")
    return result


def _number_digits(text: str) -> str:
    digits: list[str] = []
    for char in text:
        if char in _DIGITS:
            digits.append(char)
        elif char in _SEPARATORS:
            continue
        else:
            raise PhoneValidationError("Enter a valid phone number.")
    return "".join(digits)


__all__ = ("PhoneValidationError", "normalize_phone")
