"""Currencies and money formatting.

Amounts are integers in the currency's minor unit (cents for USD and KES) and
are always paired with an ISO 4217 code. There is no floating-point arithmetic
and no automatic conversion between currencies anywhere in the application.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Currency:
    code: str
    name: str
    exponent: int  # number of minor-unit digits
    symbol: str


# Currencies the catalogue can price in. Which of them a shopper can actually pay
# in is decided by the payment configuration (provider support + merchant setup).
CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in (
        Currency("USD", "US dollar", 2, "$"),
        Currency("KES", "Kenyan shilling", 2, "KSh"),
        Currency("EUR", "Euro", 2, "€"),
        Currency("GBP", "Pound sterling", 2, "£"),
        Currency("NGN", "Nigerian naira", 2, "₦"),
        Currency("GHS", "Ghanaian cedi", 2, "GH₵"),
        Currency("ZAR", "South African rand", 2, "R"),
    )
}
DEFAULT_CATALOGUE_CURRENCIES = ("USD", "KES")
MAX_AMOUNT_MINOR = 100_000_000_00  # 100 million major units: a sanity bound, not a price cap


def is_supported(code: str) -> bool:
    return code in CURRENCIES


def to_decimal_string(amount_minor: int, code: str) -> str:
    """Exact decimal representation, e.g. (1250, "USD") -> "12.50"."""
    exponent = CURRENCIES[code].exponent
    value = Decimal(amount_minor).scaleb(-exponent)
    return f"{value:.{exponent}f}"


def format_money(amount_minor: int, code: str) -> str:
    """Unambiguous label with the currency code, e.g. "USD 12.50" or "KES 1,500.00"."""
    exponent = CURRENCIES[code].exponent
    value = Decimal(amount_minor).scaleb(-exponent)
    return f"{code} {value:,.{exponent}f}"


def parse_major(value: str, code: str) -> int:
    """Parse a major-unit decimal string ("12.50") into minor units exactly."""
    exponent = CURRENCIES[code].exponent
    text = str(value).strip().replace(",", "")
    if not text or text.startswith("-"):
        raise ValueError("Enter a positive amount.")
    amount = Decimal(text)
    scaled = amount.scaleb(exponent)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"Use at most {exponent} decimal places.")
    return int(scaled)


def money(amount_minor: int, code: str) -> dict:
    return {
        "amount_minor": amount_minor,
        "currency": code,
        "amount": to_decimal_string(amount_minor, code),
        "formatted": format_money(amount_minor, code),
    }
