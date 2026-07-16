"""Locale-specific helpers for bank statement parsing."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Dict, List

from .normalize import detect_number_format, parse_number

DATE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}"),
    re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{1,2}\s+[A-Za-z]{3,}\s+\d{2,4}"),
]

COLUMN_ALIASES: Dict[str, Dict[str, str]] = {
    "DATE": {"it": "DATA", "en": "DATE", "de": "BUCHUNG", "fr": "DATE", "es": "FECHA"},
    "VALUE_DATE": {
        "it": "VALUTA",
        "en": "VALUE DATE",
        "de": "VALUTA",
        "fr": "VALEUR",
        "es": "VALOR",
    },
    "DEBIT": {
        "it": "USCITE",
        "en": "DEBITS",
        "de": "SOLL",
        "fr": "DÉBITS",
        "es": "CARGOS",
    },
    "CREDIT": {
        "it": "ENTRATE",
        "en": "CREDITS",
        "de": "HABEN",
        "fr": "CRÉDITS",
        "es": "ABONOS",
    },
    "DESCRIPTION": {
        "it": "DESCRIZIONE",
        "en": "DESCRIPTION",
        "de": "VERWENDUNGSZWECK",
        "fr": "LIBELLÉ",
        "es": "CONCEPTO",
    },
}

TRAILING_TOKENS: List[str] = [
    "spese",
    "commissioni",
    "comm.",
    "num. bonifico",
    "num. bon sepa",
    "num.bon.sepa",
    "bon. sepa",
    "bon.sepa",
    "cro",
    "trn",
    "id",
    "abi-cab",
    "cig",
    "rif.",
    "pagata",
    "pagate",
    "fattura",
    "fatt.",
]

NEGATIVE_HINTS: List[str] = [
    "addebito",
    "disposizione a favore di",
    "pagam",
    "prelievo",
]

POSITIVE_HINTS: List[str] = [
    "bonifico o/c",
    "rientro",
    "anticipo su documenti",
    "accredito",
]


def parse_generic_number(value: str) -> Decimal:
    dec, thou = detect_number_format([value])
    return parse_number(value, dec, thou)
