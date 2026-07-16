"""Multilingual keywords and patterns for bank statement parsing.

This module centralises small keyword lists used to detect headers, columns
and non-transaction sections. All terms are stored in lowercase and should
be matched case-insensitively after normalisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

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
}

TRANSACTION_HEADER_PATTERNS = [
    r"data\s+valuta\s+(uscite|addebito).*(entrate|accredito).*(descrizione|causale)",
    r"date.*(debit|dr).*(credit|cr).*(description|details)",
]

SENTINELS = [
    "elementi per il conteggio delle competenze",
    "riepilogo competenze",
    "interest summary",
    "fees summary",
    "zusammenfassung",
    "récapitulatif",
]


@dataclass
class Lexicon:
    """Container for lexicon data."""

    headers: Dict[str, List[str]] = field(default_factory=lambda: HEADERS.copy())
    header_patterns: List[str] = field(default_factory=lambda: TRANSACTION_HEADER_PATTERNS[:])
    sentinels: List[str] = field(default_factory=lambda: SENTINELS[:])
