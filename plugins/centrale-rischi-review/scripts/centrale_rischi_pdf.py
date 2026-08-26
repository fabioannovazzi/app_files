#!/usr/bin/env python3
"""Normalize native-text Centrale Rischi PDF tables for professional review."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

import pdfplumber
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

__all__ = [
    "PDF_NORMALIZATION_SCHEMA",
    "normalize_pdf",
    "write_normalized_workbook",
]

PDF_NORMALIZATION_SCHEMA = "vera.centrale_rischi_pdf_normalization.v1"

EXPOSURE_HEADERS = (
    "reference_month",
    "intermediary",
    "category",
    "location",
    "original_duration",
    "residual_duration",
    "currency",
    "import_export",
    "activity_type",
    "relationship_status",
    "guarantee_type",
    "borrower_role",
    "granted",
    "operational_granted",
    "used",
    "average_balance",
    "guaranteed_amount",
    "record_status",
    "valid_from",
    "valid_to",
    "source_page",
    "source_region",
    "source_row_locator",
    "extraction_confidence",
    "source_document_sha256",
)

GUARANTEE_HEADERS = (
    "reference_month",
    "intermediary",
    "category",
    "location",
    "guaranteed_party",
    "relationship_status",
    "guarantee_type",
    "guarantee_value",
    "guaranteed_amount",
    "record_status",
    "valid_from",
    "valid_to",
    "source_page",
    "source_region",
    "source_row_locator",
    "extraction_confidence",
    "source_document_sha256",
)

EVENT_HEADERS = (
    "intermediary",
    "event_date",
    "event_type",
    "event_cancelled",
    "source_page",
    "source_region",
    "source_row_locator",
    "extraction_confidence",
    "source_document_sha256",
)

REQUEST_HEADERS = (
    "intermediary",
    "request_date",
    "requested_period",
    "request_type",
    "request_reason_code",
    "request_reason",
    "validity_period",
    "notes",
    "source_page",
    "source_region",
    "source_row_locator",
    "extraction_confidence",
    "source_document_sha256",
)

SHEET_CONTRACTS: Mapping[str, tuple[str, ...]] = {
    "Esposizioni": EXPOSURE_HEADERS,
    "Garanzie ricevute": GUARANTEE_HEADERS,
    "Eventi inframensili": EVENT_HEADERS,
    "Richieste informazioni": REQUEST_HEADERS,
}

_HEADER_ALIASES = {
    "categoria": "category",
    "localizzazione": "location",
    "durata originaria": "original_duration",
    "durata residua": "residual_duration",
    "divisa": "currency",
    "import export": "import_export",
    "tipo attivita": "activity_type",
    "stato rapporto": "relationship_status",
    "tipo garanzia": "guarantee_type",
    "ruolo affidato": "borrower_role",
    "accordato": "granted",
    "accordato operativo": "operational_granted",
    "utilizzato": "used",
    "saldo medio": "average_balance",
    "importo garantito": "guaranteed_amount",
    "garantito": "guaranteed_party",
    "valore garanzia": "guarantee_value",
    "da": "valid_from",
    "a": "valid_to",
    "data evento": "event_date",
    "tipo evento": "event_type",
    "evento cancellato": "event_cancelled",
    "data della richiesta di informazione": "request_date",
    "periodo richiesto": "requested_period",
    "tipo richiesta di informazione": "request_type",
    "causale della richiesta": "request_reason_code",
    "descrizione causale": "request_reason",
    "periodo validita": "validity_period",
    "note": "notes",
}

_ITALIAN_MONTHS = {
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
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\u00a0", " ").split())


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean_cell(value))
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _canonical_header(value: Any) -> str:
    folded = _fold(value)
    if folded in _HEADER_ALIASES:
        return _HEADER_ALIASES[folded]
    # Diagonal educational watermarks can cross a header cell. This removes
    # only isolated leading letters when the remaining text is an exact label.
    candidate = re.sub(r"^(?:[a-z]\s+){1,4}", "", folded)
    return _HEADER_ALIASES.get(candidate, folded.replace(" ", "_"))


def _collapse_blank_header_columns(rows: Sequence[Sequence[Any]]) -> list[list[str]]:
    if not rows:
        return []
    normalized = [[_clean_cell(cell) for cell in row] for row in rows]
    width = max(len(row) for row in normalized)
    padded = [row + [""] * (width - len(row)) for row in normalized]
    groups: list[list[int]] = []
    for index, header in enumerate(padded[0]):
        if not _fold(header) and groups:
            groups[-1].append(index)
        else:
            groups.append([index])
    collapsed: list[list[str]] = []
    for row in padded:
        collapsed.append(
            [_clean_cell(" ".join(row[index] for index in group)) for group in groups]
        )
    return collapsed


def _classify_table(headers: set[str]) -> str | None:
    if {"event_date", "event_type", "event_cancelled"} <= headers:
        return "inframonthly_events"
    if {"request_date", "requested_period", "request_type"} <= headers:
        return "information_requests"
    if {"guaranteed_party", "guarantee_value", "guaranteed_amount"} <= headers:
        return "guarantees_received"
    if {"category", "used"} <= headers:
        return "exposures"
    return None


def _reference_month(page_text: str) -> str:
    match = re.search(
        r"DATA\s+DI\s+RIFERIMENTO\s*:\s*([A-Za-zÀ-ÿ]+)\s+(\d{4})",
        page_text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    month_number = _ITALIAN_MONTHS.get(_fold(match.group(1)))
    return f"{match.group(2)}-{month_number:02d}" if month_number else ""


def _page_lines(page: Any) -> list[tuple[float, str]]:
    words = sorted(page.extract_words() or [], key=lambda word: word["top"])
    lines: list[tuple[float, list[Mapping[str, Any]]]] = []
    for word in words:
        top = float(word["top"])
        if lines and abs(lines[-1][0] - top) <= 2.0:
            lines[-1][1].append(word)
        else:
            lines.append((top, [word]))
    return [
        (
            top,
            _line_text(line_words),
        )
        for top, line_words in lines
    ]


def _line_text(words: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(words, key=lambda word: word["x0"])
    parts: list[str] = []
    previous_x1: float | None = None
    for word in ordered:
        if previous_x1 is not None and float(word["x0"]) - previous_x1 > 30:
            parts.append("|")
        parts.append(str(word["text"]))
        previous_x1 = float(word["x1"])
    return " ".join(parts)


def _nearest_intermediary(lines: Sequence[tuple[float, str]], table_top: float) -> str:
    matches: list[tuple[float, str]] = []
    for top, text in lines:
        if top >= table_top:
            continue
        match = re.search(
            r"\bIntermediario\s*:\s*(.+?)(?:\s+\|\s+|$)",
            text,
            re.IGNORECASE,
        )
        if match:
            matches.append((top, _clean_cell(match.group(1)).lstrip("| ")))
    return matches[-1][1] if matches else ""


def _amount(value: str) -> str:
    text = _clean_cell(value).replace(" ", "")
    if not text:
        return "0"
    watermark_match = re.fullmatch(r"(?:[A-Za-z])+([+-]?\d[\d.,]*)", text)
    if watermark_match:
        text = watermark_match.group(1)
    if not re.fullmatch(r"[+-]?\d[\d.,]*", text):
        raise InvalidOperation
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        groups = text.split(",")
        text = (
            "".join(groups)
            if all(len(group) == 3 for group in groups[1:])
            else text.replace(",", ".")
        )
    elif "." in text:
        groups = text.split(".")
        if all(len(group) == 3 for group in groups[1:]):
            text = "".join(groups)
    number = Decimal(text)
    rendered = format(number, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _row_map(headers: Sequence[str], row: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header, value in zip(headers, row):
        if header and header not in result:
            result[header] = _clean_cell(value)
    return result


def _region(bbox: Sequence[float]) -> str:
    return ",".join(f"{float(value):.2f}" for value in bbox)


def _base_provenance(
    *,
    page_number: int,
    table_number: int,
    row_number: int,
    bbox: Sequence[float],
    source_hash: str,
) -> dict[str, str | int]:
    return {
        "source_page": page_number,
        "source_region": _region(bbox),
        "source_row_locator": f"page:{page_number}:table:{table_number}:row:{row_number}",
        "source_document_sha256": source_hash,
    }


def _exposure_row(
    source: Mapping[str, str],
    *,
    reference_month: str,
    intermediary: str,
    provenance: Mapping[str, str | int],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    output: dict[str, Any] = {
        "reference_month": reference_month,
        "intermediary": intermediary,
        "category": source.get("category", ""),
        "location": source.get("location", ""),
        "original_duration": source.get("original_duration", ""),
        "residual_duration": source.get("residual_duration", ""),
        "currency": source.get("currency", ""),
        "import_export": source.get("import_export", ""),
        "activity_type": source.get("activity_type", ""),
        "relationship_status": source.get("relationship_status", ""),
        "guarantee_type": source.get("guarantee_type", ""),
        "borrower_role": source.get("borrower_role", ""),
        "record_status": (
            "previous" if "valid_from" in source or "valid_to" in source else "current"
        ),
        "valid_from": source.get("valid_from", ""),
        "valid_to": source.get("valid_to", ""),
        **provenance,
    }
    for field in (
        "granted",
        "operational_granted",
        "used",
        "average_balance",
        "guaranteed_amount",
    ):
        try:
            output[field] = _amount(source.get(field, ""))
        except InvalidOperation:
            output[field] = source.get(field, "")
            issues.append(f"invalid_amount:{field}")
    if not reference_month:
        issues.append("missing_reference_month")
    if not intermediary:
        issues.append("missing_intermediary")
    if output["record_status"] == "previous" and not (
        output["valid_from"] and output["valid_to"]
    ):
        issues.append("incomplete_previous_validity")
    output["extraction_confidence"] = "high" if not issues else "review_required"
    return output, issues


def _guarantee_row(
    source: Mapping[str, str],
    *,
    reference_month: str,
    intermediary: str,
    provenance: Mapping[str, str | int],
) -> tuple[dict[str, Any], list[str]]:
    issues: list[str] = []
    output: dict[str, Any] = {
        "reference_month": reference_month,
        "intermediary": intermediary,
        "category": source.get("category", ""),
        "location": source.get("location", ""),
        "guaranteed_party": source.get("guaranteed_party", ""),
        "relationship_status": source.get("relationship_status", ""),
        "guarantee_type": source.get("guarantee_type", ""),
        "record_status": (
            "previous" if "valid_from" in source or "valid_to" in source else "current"
        ),
        "valid_from": source.get("valid_from", ""),
        "valid_to": source.get("valid_to", ""),
        **provenance,
    }
    for field in ("guarantee_value", "guaranteed_amount"):
        try:
            output[field] = _amount(source.get(field, ""))
        except InvalidOperation:
            output[field] = source.get(field, "")
            issues.append(f"invalid_amount:{field}")
    if not reference_month:
        issues.append("missing_reference_month")
    if not intermediary:
        issues.append("missing_intermediary")
    output["extraction_confidence"] = "high" if not issues else "review_required"
    return output, issues


def normalize_pdf(path: Path) -> dict[str, Any]:
    """Extract native-text tables without assigning professional classifications."""

    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise ValueError(f"Expected one readable PDF: {path}")
    source_hash = _sha256_file(path)
    collections: dict[str, list[dict[str, Any]]] = {
        "exposures": [],
        "guarantees_received": [],
        "inframonthly_events": [],
        "information_requests": [],
    }
    issues: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    native_character_count = 0
    page_count = 0
    with pdfplumber.open(path) as document:
        page_count = len(document.pages)
        for page in document.pages:
            page_text = page.extract_text() or ""
            native_character_count += len(page_text.strip())
            reference_month = _reference_month(page_text)
            lines = _page_lines(page)
            for table_number, table in enumerate(page.find_tables(), start=1):
                rows = _collapse_blank_header_columns(table.extract())
                if not rows:
                    continue
                headers = [_canonical_header(value) for value in rows[0]]
                family = _classify_table(set(headers))
                if family is None:
                    unclassified.append(
                        {
                            "source_page": page.page_number,
                            "source_region": _region(table.bbox),
                            "headers": headers,
                        }
                    )
                    continue
                intermediary = _nearest_intermediary(lines, float(table.bbox[1]))
                for row_number, raw_row in enumerate(rows[1:], start=2):
                    source = _row_map(headers, raw_row)
                    if not any(source.values()):
                        continue
                    provenance = _base_provenance(
                        page_number=page.page_number,
                        table_number=table_number,
                        row_number=row_number,
                        bbox=table.bbox,
                        source_hash=source_hash,
                    )
                    row_issues: list[str] = []
                    if family == "exposures":
                        output, row_issues = _exposure_row(
                            source,
                            reference_month=reference_month,
                            intermediary=intermediary,
                            provenance=provenance,
                        )
                    elif family == "guarantees_received":
                        output, row_issues = _guarantee_row(
                            source,
                            reference_month=reference_month,
                            intermediary=intermediary,
                            provenance=provenance,
                        )
                    else:
                        output = {
                            **source,
                            "intermediary": intermediary,
                            **provenance,
                        }
                        output["extraction_confidence"] = (
                            "high" if intermediary else "review_required"
                        )
                        if not intermediary:
                            row_issues.append("missing_intermediary")
                    collections[family].append(output)
                    if row_issues:
                        issues.append(
                            {
                                "source_row_locator": provenance["source_row_locator"],
                                "issues": row_issues,
                            }
                        )
    if native_character_count == 0:
        raise ValueError(
            "The PDF has no readable native text. Use the official digital Centrale Rischi report downloaded from the Banca d'Italia service."
        )
    if not any(collections.values()):
        raise ValueError(
            "No supported Centrale Rischi table layout was found in the native-text PDF."
        )
    return {
        "schema_version": PDF_NORMALIZATION_SCHEMA,
        "workflow_id": "centrale-rischi-review",
        "source": {
            "source_document_sha256": source_hash,
            "source_kind": "native_pdf_extraction",
            "page_count": page_count,
        },
        "review_status": "pending_professional_review",
        "semantic_roles_assigned": False,
        "tables": collections,
        "issues": issues,
        "unclassified_tables": unclassified,
        "implementation_reason": (
            "Header-shape recognition, cell extraction, Italian-number parsing, record provenance and current-versus-previous separation are deterministic because they are mechanically reviewable. Duration meaning, risk family, materiality and professional conclusions remain reviewed judgments."
        ),
    }


def write_normalized_workbook(path: Path, payload: Mapping[str, Any]) -> None:
    """Write separate review sheets from a PDF-normalization payload."""

    if payload.get("schema_version") != PDF_NORMALIZATION_SCHEMA:
        raise ValueError("Unsupported PDF-normalization payload.")
    tables = payload.get("tables")
    if not isinstance(tables, Mapping):
        raise ValueError("PDF-normalization tables are missing.")
    table_keys = {
        "Esposizioni": "exposures",
        "Garanzie ricevute": "guarantees_received",
        "Eventi inframensili": "inframonthly_events",
        "Richieste informazioni": "information_requests",
    }
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, contract in SHEET_CONTRACTS.items():
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(contract)
        rows = tables.get(table_keys[sheet_name], [])
        if not isinstance(rows, list):
            raise ValueError(f"Invalid normalized table: {table_keys[sheet_name]}")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"Invalid row in normalized table: {table_keys[sheet_name]}"
                )
            sheet.append([row.get(header, "") for header in contract])
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="002060")
        for column_cells in sheet.columns:
            width = min(
                42,
                max(12, max(len(str(cell.value or "")) for cell in column_cells) + 2),
            )
            sheet.column_dimensions[column_cells[0].column_letter].width = width
    workbook.save(path)
