from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Tuple

# Regular expressions exported for reuse
DATE_RE = re.compile(
    r"("  # day-month-year variations
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"  # 31/12/2024 or 31.12.24
    r"|\b\d{4}-\d{2}-\d{2}\b"  # 2024-12-31
    r"|\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
    r"gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic|"
    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
    r"januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+\d{2,4}\b"  # month names
    r")",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(
    r"[+-]?\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\b|€|CHF|£|\$|USD|EUR",
    re.IGNORECASE,
)

TX_MIN_ROWS = 5
TX_MIN_DATE_DENSITY = 0.15
SUMMARY_MAX_DATE_DENSITY = 0.10
SUMMARY_MIN_CUES = 2

SUMMARY_TOKENS = [
    "riepilogo",
    "totale",
    "elementi per il conteggio delle competenze",
    "interessi",
    "spese",
    "imposte",
    "résumé",
    "récapitulatif",
    "intérêts",
    "frais",
    "summary",
    "totals",
    "fees",
    "resumen",
    "interés",
    "interes",
    "comisión",
    "comision",
    "comisiones",
    "gastos",
    "impuesto",
    "impuestos",
    "zusammenfassung",
    "zinsen",
    "gebühren",
]

HEADER_TOKENS = {
    "date",
    "data",
    "datum",
    "fecha",
    "fechaoperacion",
    "valuta",
    "valore",
    "wert",
    "description",
    "descrizione",
    "descripcion",
    "concepto",
    "detalle",
    "beschreibung",
    "importe",
    "cargo",
    "abono",
    "saldo",
    "referencia",
    "debit",
    "credito",
    "credit",
    "dare",
    "avere",
}

BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*page\s+\d+", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
    re.compile(r"^\s*page\s+\d+\s+of\s+\d+", re.IGNORECASE),
]


@dataclass
class PageClassifier:
    """Deterministic multilingual page classifier."""

    def classify(
        self,
        page_text: str,
        lang_hint: str | None = None,
        page_index: int | None = None,
        is_last_page: bool | None = None,
    ) -> Tuple[str, float, Dict[str, int | float | bool]]:
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        cleaned_lines = [
            l for l in lines if not any(pat.search(l) for pat in BOILERPLATE_PATTERNS)
        ]
        total_lines = len(cleaned_lines) or 1
        date_lines = [l for l in cleaned_lines if DATE_RE.search(l)]
        amount_lines = [l for l in cleaned_lines if AMOUNT_RE.search(l)]
        candidate_rows = 0
        for idx, line in enumerate(cleaned_lines):
            if DATE_RE.search(line):
                if AMOUNT_RE.search(line):
                    candidate_rows += 1
                elif idx + 1 < len(cleaned_lines) and AMOUNT_RE.search(
                    cleaned_lines[idx + 1]
                ):
                    candidate_rows += 1
        header_cues = False
        for line in cleaned_lines[:5]:
            tokens = {
                re.sub(
                    r"[^a-z]",
                    "",
                    "".join(
                        char
                        for char in unicodedata.normalize("NFKD", token.lower())
                        if not unicodedata.combining(char)
                    ),
                )
                for token in line.split()
            }
            if len(tokens & HEADER_TOKENS) >= 2:
                header_cues = True
                break
        summary_cues = 0
        norm_lines = [line.lower() for line in cleaned_lines]
        for token in SUMMARY_TOKENS:
            summary_cues += sum(1 for line in norm_lines if token in line)
        date_density = len(date_lines) / total_lines
        amount_density = len(amount_lines) / total_lines
        label = "other"
        confidence = 0.5
        if (
            candidate_rows >= TX_MIN_ROWS and date_density >= TX_MIN_DATE_DENSITY
        ) or header_cues:
            label = "transaction"
            confidence = 0.9
        elif (
            summary_cues >= SUMMARY_MIN_CUES
            and date_density < SUMMARY_MAX_DATE_DENSITY
            and candidate_rows <= 2
        ):
            label = "summary"
            confidence = 0.9
        if label != "transaction" and is_last_page:
            confidence = min(0.95, confidence + 0.1)
        details: Dict[str, int | float | bool] = {
            "date_lines": len(date_lines),
            "amount_lines": len(amount_lines),
            "candidate_rows": candidate_rows,
            "summary_cues": summary_cues,
            "header_cues": header_cues,
            "date_density": date_density,
            "amount_density": amount_density,
            "total_lines": total_lines,
        }
        return label, confidence, details
