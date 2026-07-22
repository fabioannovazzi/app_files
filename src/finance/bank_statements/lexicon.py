"""Multilingual keywords and patterns for bank statement parsing.

This module centralises small keyword lists used to detect headers, columns
and non-transaction sections. All terms are stored in lowercase and should
be matched case-insensitively after normalisation.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List

LANGUAGE_HEADER_MARKERS: Dict[str, List[str]] = {
    "it": [
        "data contabile",
        "data valuta",
        "uscite",
        "addebito",
        "entrate",
        "accredito",
        "descrizione",
        "causale",
    ],
    "en": [
        "booking date",
        "value date",
        "debit",
        "credit",
        "description",
        "details",
    ],
    "de": [
        "buchungstag",
        "valutadatum",
        "abbuchung",
        "gutschrift",
        "beschreibung",
        "kontostand",
    ],
    "fr": [
        "date opération",
        "date operation",
        "date comptable",
        "date valeur",
        "débité",
        "debite",
        "crédit",
        "libellé",
        "libelle",
        "solde",
    ],
    "es": [
        "fecha",
        "fecha valor",
        "cargo",
        "abono",
        "concepto",
        "descripción",
        "descripcion",
        "importe",
        "moneda",
    ],
}

HEADERS: Dict[str, List[str]] = {
    "date": ["data", "date", "fecha", "datum", "date opération", "date comptable"],
    "value_date": [
        "valuta",
        "value date",
        "fecha valor",
        "valutadatum",
        "date valeur",
    ],
    "debit": ["uscite", "addebito", "debit", "débité", "abbuchung", "cargo"],
    "credit": ["entrate", "accredito", "credit", "crédit", "gutschrift", "abono"],
    "description": [
        "descrizione",
        "causale",
        "description",
        "beschreibung",
        "concepto",
    ],
    "balance": ["saldo", "balance", "saldo contabile", "kontostand", "solde"],
    "currency": ["currency", "währung", "moneda", "devise"],
}


def canonical_header(value: str, headers: Dict[str, List[str]] | None = None) -> str:
    """Return the canonical field name for a localized statement header."""

    normalized = _normalize_keyword(value)
    for canonical, synonyms in (headers or HEADERS).items():
        if any(normalized == _normalize_keyword(synonym) for synonym in synonyms):
            return canonical
    return normalized


def _normalize_keyword(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return (
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .strip()
        .casefold()
    )


TRANSACTION_HEADER_PATTERNS = [
    r"data\s+valuta\s+(uscite|addebito).*(entrate|accredito).*(descrizione|causale)",
    r"date.*(debit|dr).*(credit|cr).*(description|details)",
    r"fecha.*(cargo|debe).*(abono|haber).*(concepto|descripci[oó]n)",
    r"fecha.*(concepto|descripci[oó]n).*(cargo|debe).*(abono|haber)",
]

SENTINELS = [
    "elementi per il conteggio delle competenze",
    "riepilogo competenze",
    "interest summary",
    "fees summary",
    "zusammenfassung",
    "récapitulatif",
    "resumen",
    "resumen de intereses",
    "resumen de comisiones",
]


@dataclass
class Lexicon:
    """Container for lexicon data."""

    headers: Dict[str, List[str]] = field(default_factory=lambda: HEADERS.copy())
    header_patterns: List[str] = field(
        default_factory=lambda: TRANSACTION_HEADER_PATTERNS[:]
    )
    sentinels: List[str] = field(default_factory=lambda: SENTINELS[:])
