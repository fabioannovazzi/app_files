"""Map multilingual headers to canonical field names."""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

HEADER_SYNONYMS: Dict[str, List[str]] = {
    "booking_date": [
        "booking date",
        "data contabile",
        "data registrazione",
        "buchungstag",
        "fecha contable",
        "fecha operación",
        "fecha de operación",
        "date comptable",
    ],
    "value_date": [
        "value date",
        "data valuta",
        "valutadatum",
        "fecha valor",
        "date de valeur",
    ],
    "description": [
        "description",
        "descrizione",
        "causale",
        "descrizione operazione",
        "beschreibung",
        "libellé",
        "concepto",
        "descripción",
        "descripcion",
        "detalle",
        "detalle de operación",
    ],
    "amount": [
        "amount",
        "importo",
        "betrag",
        "importe",
        "montant",
        "valor",
    ],
    "currency": [
        "currency",
        "valuta",
        "währung",
        "moneda",
        "devise",
    ],
    "debit": ["debit", "dare", "addebito", "soll", "cargo", "débit"],
    "credit": ["credit", "avere", "accredito", "haben", "abono", "crédit"],
    "balance": ["balance", "saldo", "kontostand", "solde"],
    "reference": [
        "reference",
        "riferimento",
        "cro",
        "trn",
        "rif.",
        "référence",
        "referenz",
        "referencia",
        "número de referencia",
    ],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


_COMPILED = {
    key: [re.compile(rf"\b{re.escape(_norm(p))}\b") for p in vals]
    for key, vals in HEADER_SYNONYMS.items()
}


def map_headers(headers: List[str], lang: str) -> Dict[str, int]:
    """Return mapping of canonical field -> column index."""
    mapping: Dict[str, int] = {}
    for idx, header in enumerate(headers):
        norm = _norm(header)
        for canon, patterns in _COMPILED.items():
            if any(p.search(norm) for p in patterns):
                mapping[canon] = idx
                break
    return mapping
