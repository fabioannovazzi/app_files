"""Locale and language utilities for statement parsing."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Iterable, Tuple

from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException

MONTHS: Dict[str, Dict[str, int]] = {
    "it": {
        "gennaio": 1,
        "febbraio": 2,
        "marzo": 3,
        "aprile": 4,
        "maggio": 5,
        "giugno": 6,
        "luglio": 7,
        "agosto": 8,
        "settembre": 9,
        "ottobre": 10,
        "novembre": 11,
        "dicembre": 12,
        "gen": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "mag": 5,
        "giu": 6,
        "lug": 7,
        "ago": 8,
        "set": 9,
        "ott": 10,
        "nov": 11,
        "dic": 12,
    },
    "de": {
        "januar": 1,
        "februar": 2,
        "märz": 3,
        "maerz": 3,
        "marz": 3,
        "april": 4,
        "mai": 5,
        "juni": 6,
        "juli": 7,
        "august": 8,
        "september": 9,
        "oktober": 10,
        "november": 11,
        "dezember": 12,
    },
    "fr": {
        "janvier": 1,
        "février": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "août": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "décembre": 12,
    },
    "es": {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    },
    "pt": {
        "janeiro": 1,
        "fevereiro": 2,
        "março": 3,
        "marco": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    },
    "en": {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    },
}

CURRENCY_SYMBOLS = {
    "€": "EUR",
    "eur": "EUR",
    "$": "USD",
    "usd": "USD",
    "chf": "CHF",
    "fr": "CHF",
    "£": "GBP",
    "gbp": "GBP",
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def detect_language(text: str) -> Tuple[str, float]:
    """Return ISO language code and confidence."""
    try:
        langs = detect_langs(text)
        if langs:
            top = langs[0]
            return top.lang, top.prob
    except LangDetectException:  # pragma: no cover - langdetect may fail
        pass
    return "en", 0.0


def detect_currency(text: str) -> str:
    lowered = _strip_accents(text).lower()
    for sym, iso in CURRENCY_SYMBOLS.items():
        if sym in lowered:
            return iso
    return "EUR"


def parse_number(s: str, locale: str) -> Decimal:
    """Parse a locale aware number into :class:`Decimal`."""
    s = s.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.endswith("-"):
        neg = True
        s = s[:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    s = s.replace(" ", "")
    if locale in {"it", "de", "fr", "es", "pt"}:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    value = Decimal(s)
    return -value if neg else value


_DATE_PATTERNS = [
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d %m %Y",
]


def parse_date(value: str, locale: str) -> date:
    """Parse a date string considering locale month names."""
    value_norm = _strip_accents(value.lower())
    months = MONTHS.get(locale, {})
    for name, idx in months.items():
        value_norm = re.sub(rf"\b{name}\b", f"{idx:02d}", value_norm)
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(value_norm, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {value}")
