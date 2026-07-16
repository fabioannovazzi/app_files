"""Utilities for normalising language, dates and amounts."""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from .lexicon import HEADERS

try:  # optional dependency
    from dateutil.parser import parse as dateutil_parse
except Exception as e:  # pragma: no cover
    logging.exception(e)
    dateutil_parse = None  # type: ignore

try:  # optional
    from langdetect import detect  # type: ignore
except Exception as e:  # pragma: no cover
    logging.exception(e)
    detect = None  # type: ignore


LANG_FALLBACK = "en"


def detect_language(text: str) -> str:
    """Detect language using keyword counts and optional langdetect."""
    counts = {lang: 0 for lang in ["it", "en", "de", "fr", "es"]}
    lower = text.lower()
    for _, words in HEADERS.items():
        for w in words:
            for lang in counts:
                if w in lower:
                    counts[lang] += 1
    best = max(counts, key=counts.get)
    if counts[best] == 0 and detect is not None:
        try:
            best = detect(text)
        except Exception as e:  # pragma: no cover - langdetect errors
            logging.exception(e)
            best = LANG_FALLBACK
    return best


def _parse_date_fallback(value: str, dayfirst: bool) -> date:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", value)
    if not match:
        raise ValueError(f"Unrecognised date: {value}")
    d, m, y = match.groups()
    y = int(y)
    if y < 100:
        y += 2000
    if dayfirst:
        day, month = int(d), int(m)
    else:
        month, day = int(d), int(m)
    return date(y, month, day)


def parse_date(value: str, lang: str) -> date | None:
    """Parse a date string using locale hints.

    Returns ``None`` when parsing fails instead of raising ``ValueError``.
    """
    value = value.strip()
    dayfirst = lang in {"it", "fr", "es", "de"}
    if dateutil_parse is not None:
        try:
            return dateutil_parse(value, dayfirst=dayfirst).date()
        except Exception as e:
            logging.debug("dateutil parse failed: %s", e)
            pass
    return _parse_date_fallback(value, dayfirst)


def detect_number_format(samples: Iterable[str]) -> Tuple[str, str]:
    """Return decimal and thousand separators inferred from samples."""
    decimal = "."
    thousand = ","
    for s in samples:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                decimal = ","
                thousand = "."
            break
        if s.count(",") >= 1 and s.count(".") == 0:
            decimal = ","
            thousand = "."
        if s.count(".") > 1 and s.count(",") == 0:
            decimal = "."
            thousand = ","
    return decimal, thousand


def parse_number(value: str, decimal_sep: str, thousand_sep: str) -> Decimal:
    clean = value.replace(thousand_sep, "").replace(decimal_sep, ".")
    clean = clean.replace(" ", "").replace("\xa0", "")
    return Decimal(clean)


def parse_amount(
    value: str,
    lang: str,
    decimal_sep: Optional[str] = None,
    thousand_sep: Optional[str] = None,
) -> Decimal:
    """Parse an amount string into Decimal respecting locale separators."""
    if decimal_sep is None or thousand_sep is None:
        decimal_sep, thousand_sep = detect_number_format([value])
    sign = -1 if re.search(r"^[-(]", value.strip()) else 1
    value = re.sub(r"[()]", "", value)
    amount = parse_number(value, decimal_sep, thousand_sep)
    return amount * sign


def combine_debit_credit(debit: str | None, credit: str | None, lang: str) -> Decimal:
    """Combine debit/credit strings into a signed amount."""
    dec, thou = detect_number_format(filter(None, [debit or "0", credit or "0"]))
    debit_amt = parse_number(debit or "0", dec, thou)
    credit_amt = parse_number(credit or "0", dec, thou)
    return credit_amt - debit_amt
