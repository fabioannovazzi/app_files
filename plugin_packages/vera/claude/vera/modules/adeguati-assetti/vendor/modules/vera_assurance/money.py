"""Exact monetary parsing and comparison primitives.

These functions are deterministic because numeric syntax, exact arithmetic,
and tolerance comparisons are mechanically verifiable. They do not decide
currency, source meaning, sign convention, materiality, or an acceptable
tolerance.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "MoneyValidationError",
    "decimal_text",
    "difference_within_tolerance",
    "parse_canonical_decimal",
    "parse_localized_decimal",
]

_CANONICAL_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CURRENCY_EDGE_RE = re.compile(
    r"^(?:(?:EUR|USD|GBP|CHF|CAD|AUD|JPY)\s*|[€$£]\s*)"
    r"|(?:\s*(?:EUR|USD|GBP|CHF|CAD|AUD|JPY)|\s*[€$£])$",
    re.IGNORECASE,
)
_INTEGER_RE = re.compile(r"^\d+$")


class MoneyValidationError(ValueError):
    """Raised when a monetary value cannot be represented exactly."""


def _finite(value: Decimal, *, label: str) -> Decimal:
    if not value.is_finite():
        raise MoneyValidationError(f"{label} must be finite")
    return value


def decimal_text(value: Decimal) -> str:
    """Return canonical non-exponent Decimal text."""

    number = _finite(value, label="value")
    if number == 0:
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def parse_canonical_decimal(value: object, *, label: str = "value") -> Decimal:
    """Parse Decimal text that already uses the canonical contract syntax."""

    if not isinstance(value, str) or _CANONICAL_DECIMAL_RE.fullmatch(value) is None:
        raise MoneyValidationError(f"{label} must be canonical Decimal text")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise MoneyValidationError(f"{label} must be canonical Decimal text") from exc
    _finite(number, label=label)
    if decimal_text(number) != value:
        raise MoneyValidationError(f"{label} must be canonical Decimal text")
    return number


def _strip_currency_edges(text: str) -> str:
    previous = None
    result = text
    while result != previous:
        previous = result
        result = _CURRENCY_EDGE_RE.sub("", result).strip()
    return result


def _separator_roles(
    text: str,
    *,
    decimal_separator: str | None,
    thousands_separator: str | None,
    label: str,
) -> tuple[str | None, str | None]:
    if decimal_separator not in {None, ".", ","}:
        raise MoneyValidationError(
            f"{label} decimal_separator must be '.', ',', or None"
        )
    if thousands_separator not in {None, ".", ","}:
        raise MoneyValidationError(
            f"{label} thousands_separator must be '.', ',', or None"
        )
    if (
        decimal_separator is not None
        and thousands_separator is not None
        and decimal_separator == thousands_separator
    ):
        raise MoneyValidationError(
            f"{label} decimal and thousands separators must differ"
        )
    if decimal_separator is not None:
        inferred_thousands = thousands_separator
        if inferred_thousands is None:
            inferred_thousands = "," if decimal_separator == "." else "."
        return decimal_separator, inferred_thousands
    if thousands_separator is not None:
        # A reviewed separator role is mechanical authority: source punctuation
        # must not reinterpret an explicit thousands separator as a decimal one.
        inferred_decimal = "," if thousands_separator == "." else "."
        return inferred_decimal, thousands_separator

    dot_count = text.count(".")
    comma_count = text.count(",")
    if dot_count and comma_count:
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        return decimal, "," if decimal == "." else "."
    separator = "." if dot_count else "," if comma_count else None
    if separator is None:
        return None, thousands_separator

    groups = text.split(separator)
    if any(not group or _INTEGER_RE.fullmatch(group) is None for group in groups):
        raise MoneyValidationError(f"{label} contains invalid separator grouping")
    if len(groups) > 2:
        if all(len(group) == 3 for group in groups[1:]):
            return None, separator
        return separator, thousands_separator

    fractional_digits = len(groups[1])
    if fractional_digits == 3:
        raise MoneyValidationError(
            f"{label} is ambiguous without an explicit decimal separator"
        )
    return separator, thousands_separator


def _remove_auxiliary_grouping(
    text: str,
    *,
    decimal_separator: str | None,
    label: str,
) -> str:
    """Validate and remove space or apostrophe thousands grouping."""

    normalized = text.replace("\u00a0", " ").replace("\u202f", " ")
    used = [separator for separator in (" ", "'") if separator in normalized]
    if len(used) > 1:
        raise MoneyValidationError(
            f"{label} contains multiple thousands-separator conventions"
        )
    if not used:
        return normalized

    separator = used[0]
    integral = normalized
    fractional = ""
    if decimal_separator is not None and decimal_separator in normalized:
        if normalized.count(decimal_separator) > 1:
            raise MoneyValidationError(f"{label} contains multiple decimal separators")
        integral, fractional = normalized.rsplit(decimal_separator, 1)
        if separator in fractional:
            raise MoneyValidationError(
                f"{label} contains a thousands separator after the decimal separator"
            )
    groups = integral.split(separator)
    if (
        not 1 <= len(groups[0]) <= 3
        or any(_INTEGER_RE.fullmatch(group) is None for group in groups)
        or any(len(group) != 3 for group in groups[1:])
    ):
        raise MoneyValidationError(f"{label} contains invalid thousands grouping")
    compact_integral = "".join(groups)
    if decimal_separator is None:
        return compact_integral
    return compact_integral + decimal_separator + fractional


def _validate_thousands_grouping(
    text: str,
    *,
    decimal_separator: str | None,
    thousands_separator: str | None,
    label: str,
) -> None:
    """Reject malformed dot/comma grouping before separators are removed."""

    if thousands_separator is None or thousands_separator not in text:
        return
    integral = text
    fractional = ""
    if decimal_separator is not None and decimal_separator in text:
        if text.count(decimal_separator) > 1:
            raise MoneyValidationError(f"{label} contains multiple decimal separators")
        integral, fractional = text.rsplit(decimal_separator, 1)
        if thousands_separator in fractional:
            raise MoneyValidationError(
                f"{label} contains a thousands separator after the decimal separator"
            )
    groups = integral.split(thousands_separator)
    if (
        not 1 <= len(groups[0]) <= 3
        or any(_INTEGER_RE.fullmatch(group) is None for group in groups)
        or any(len(group) != 3 for group in groups[1:])
    ):
        raise MoneyValidationError(f"{label} contains invalid thousands grouping")


def parse_localized_decimal(
    value: Any,
    *,
    label: str = "value",
    decimal_separator: str | None = None,
    thousands_separator: str | None = None,
    allow_float: bool = False,
) -> Decimal:
    """Parse a localized number without silently resolving ambiguous syntax.

    ``allow_float`` must be explicit because a Python float may already have
    lost source precision before this function receives it.
    """

    if isinstance(value, bool) or value is None:
        raise MoneyValidationError(f"{label} must be a monetary value")
    if isinstance(value, Decimal):
        return _finite(value, label=label)
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not allow_float:
            raise MoneyValidationError(
                f"{label} is a binary float; exact source precision is unproven"
            )
        if not math.isfinite(value):
            raise MoneyValidationError(f"{label} must be finite")
        return Decimal(str(value))
    if not isinstance(value, str):
        raise MoneyValidationError(f"{label} must be text, int, or Decimal")

    text = _strip_currency_edges(value.strip())
    if not text:
        raise MoneyValidationError(f"{label} must be non-empty")
    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1].strip()
    sign = ""
    if text.startswith(("+", "-")):
        sign, text = text[0], text[1:].strip()
    if not text or text.startswith(("+", "-")):
        raise MoneyValidationError(f"{label} contains an invalid sign")
    if negative_parentheses and sign:
        raise MoneyValidationError(f"{label} contains two sign conventions")

    compact_for_roles = (
        text.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace(" ", "")
        .replace("'", "")
    )
    if re.search(r"[^0-9.,]", compact_for_roles):
        raise MoneyValidationError(f"{label} contains unsupported characters")

    decimal, thousands = _separator_roles(
        compact_for_roles,
        decimal_separator=decimal_separator,
        thousands_separator=thousands_separator,
        label=label,
    )
    text = _remove_auxiliary_grouping(
        text,
        decimal_separator=decimal,
        label=label,
    )
    _validate_thousands_grouping(
        text,
        decimal_separator=decimal,
        thousands_separator=thousands,
        label=label,
    )
    normalized = text
    if thousands:
        normalized = normalized.replace(thousands, "")
    if decimal:
        if normalized.count(decimal) > 1:
            raise MoneyValidationError(f"{label} contains multiple decimal separators")
        normalized = normalized.replace(decimal, ".")
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized) is None:
        raise MoneyValidationError(f"{label} is not a valid monetary value")

    prefix = "-" if negative_parentheses or sign == "-" else ""
    try:
        return _finite(Decimal(prefix + normalized), label=label)
    except InvalidOperation as exc:
        raise MoneyValidationError(f"{label} is not a valid monetary value") from exc


def difference_within_tolerance(
    actual: Decimal,
    expected: Decimal,
    tolerance: Decimal,
) -> tuple[Decimal, bool]:
    """Return the exact difference and reviewed-tolerance result."""

    actual = _finite(actual, label="actual")
    expected = _finite(expected, label="expected")
    tolerance = _finite(tolerance, label="tolerance")
    if tolerance < 0:
        raise MoneyValidationError("tolerance must not be negative")
    difference = actual - expected
    return difference, abs(difference) <= tolerance
