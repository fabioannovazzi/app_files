from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import openpyxl
import polars as pl
from invoice_support import InvoiceRecord, load_invoice_records, match_invoice

SCRIPT_DIR = Path(__file__).resolve().parent


def _ensure_local_review_session_import() -> None:
    """Use this plugin's review-session module in multi-plugin test runs."""

    script_dir = str(SCRIPT_DIR)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    module = sys.modules.get("review_session")
    module_file = getattr(module, "__file__", None) if module is not None else None
    if module_file and Path(module_file).resolve().is_relative_to(SCRIPT_DIR.resolve()):
        return
    if module is not None:
        del sys.modules["review_session"]


_ensure_local_review_session_import()
from review_session import write_review_session_artifacts, write_run_intake

LOGGER = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("it", "en", "fr", "de")
SUPPORTED_JOURNAL_SUFFIXES = {".csv", ".xls", ".xlsx", ".xlsm", ".pdf"}
PDF_SUFFIXES = {".pdf"}
CANONICAL_ENTRY_COLUMNS = [
    "movement_number",
    "entry_date",
    "description",
    "beneficiary_expected",
    "amount_signed",
    "amount_abs",
    "source_file",
    "source_row",
]
RESULT_COLUMNS = [
    *CANONICAL_ENTRY_COLUMNS,
    "status",
    "matched_pdf",
    "checks_run",
    "mismatches",
    "review_notes",
    "amount_found",
    "date_found",
    "beneficiary_found",
    "matched_support",
    "support_type",
]
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%m/%d/%Y",
    "%Y/%m/%d",
)
DATE_TOKEN_RE = re.compile(
    r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})\b"
)
AMOUNT_TOKEN_RE = re.compile(
    r"(?<!\w)\(?-?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})\)?(?!\w)"
)
WORD_RE = re.compile(r"[a-z0-9]+")

__all__ = [
    "CANONICAL_ENTRY_COLUMNS",
    "RESULT_COLUMNS",
    "InspectionResult",
    "CheckRunResult",
    "add_common_args",
    "configure_logging",
    "inspect_entries",
    "normalize_language",
    "run_entry_checks",
    "write_json",
]


@dataclass(frozen=True)
class InspectionResult:
    """Deterministic inspection output for journal entries and support files."""

    journal: dict[str, Any]
    pdfs: list[dict[str, Any]]
    invoices: list[dict[str, Any]]
    suggested_recipe: dict[str, Any]


@dataclass(frozen=True)
class CheckRunResult:
    """Check output plus reviewable audit metadata."""

    frame: pl.DataFrame
    audit: dict[str, Any]


def configure_logging(verbose: bool = False) -> None:
    """Configure script logging without affecting imported use."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def normalize_language(
    language: object | None,
    *,
    default: str = "en",
    allow_auto: bool = False,
) -> str:
    """Normalize a language tag to one supported plugin locale."""

    text = str(language or default).strip().lower().replace("_", "-")
    code = text.split("-", 1)[0]
    if allow_auto and code == "auto":
        return "auto"
    return code if code in SUPPORTED_LANGUAGES else default


def language_assumptions(
    recipe: dict[str, Any],
    *,
    language: object | None = None,
    document_language: object | None = None,
) -> dict[str, str]:
    """Resolve working and source-document language assumptions."""

    working = normalize_language(language or recipe.get("language"), default="en")
    source = normalize_language(
        document_language or recipe.get("document_language") or "auto",
        default=working,
        allow_auto=True,
    )
    return {"language": working, "document_language": source}


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_json(path: Path | None) -> dict[str, Any]:
    """Return a JSON object or an empty mapping when no file is provided."""

    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Recipe must be a JSON object: {path}")
    return payload


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\u00a0", " ").replace("\u202f", " ").strip()


def _norm_label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean_text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    return re.sub(r"\s+", " ", text)


def _normalize_search_text(value: Any) -> str:
    text = _norm_label(value)
    return " ".join(WORD_RE.findall(text))


def _excel_column_name(index: int) -> str:
    idx = index + 1
    letters: list[str] = []
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _unique_names(values: Sequence[Any]) -> list[str]:
    names: list[str] = []
    seen: dict[str, int] = {}
    for idx, value in enumerate(values):
        text = _clean_text(value)
        base = (
            text
            if text and text.lower() not in {"none", "nan"}
            else _excel_column_name(idx)
        )
        count = seen.get(base, 0)
        seen[base] = count + 1
        names.append(base if count == 0 else f"{base}_{count + 1}")
    return names


def _row_values(df: pl.DataFrame, idx: int) -> list[Any]:
    return list(df.row(idx))


def _nonempty_count(row: Sequence[Any]) -> int:
    return sum(1 for value in row if _clean_text(value))


def _read_excel_raw(path: Path) -> pl.DataFrame:
    try:
        return pl.read_excel(
            path,
            has_header=False,
            drop_empty_rows=False,
            drop_empty_cols=False,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        LOGGER.info(
            "Polars Excel read failed for %s; trying openpyxl: %s", path.name, exc
        )

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    sheet = workbook.worksheets[0]
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    max_width = max((len(row) for row in rows), default=0)
    if max_width == 0:
        return pl.DataFrame()
    return pl.DataFrame(
        {
            f"column_{idx}": [row[idx] if idx < len(row) else None for row in rows]
            for idx in range(max_width)
        }
    )


def _read_csv_raw(path: Path) -> pl.DataFrame:
    return pl.read_csv(path, has_header=False, infer_schema=False, ignore_errors=True)


def _read_tabular_raw(path: Path) -> pl.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_raw(path)
    if suffix in {".xls", ".xlsx", ".xlsm"}:
        return _read_excel_raw(path)
    raise ValueError(f"Unsupported tabular file: {path}")


def _drop_empty_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() or df.width == 0:
        return df
    keep: list[str] = []
    for col in df.columns:
        values = (
            df.get_column(col)
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.strip_chars()
        )
        if int((values != "").sum()) > 0:
            keep.append(col)
    return df.select(keep) if keep else pl.DataFrame()


def _drop_empty_rows(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() or df.width == 0:
        return df
    exprs = [
        pl.col(col).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars() == ""
        for col in df.columns
    ]
    return df.filter(~pl.all_horizontal(exprs))


def _suggest_header_rows(df: pl.DataFrame) -> list[int]:
    if df.is_empty():
        return [1]
    best_idx = 0
    best_score = -1
    header_tokens = (
        "data",
        "date",
        "datum",
        "movimento",
        "movement",
        "mouvement",
        "bewegung",
        "registrazione",
        "reference",
        "riferimento",
        "beleg",
        "descrizione",
        "description",
        "libelle",
        "libellé",
        "beschreibung",
        "beneficiario",
        "beneficiary",
        "payee",
        "vendor",
        "fournisseur",
        "beguenstigter",
        "dare",
        "debit",
        "soll",
        "avere",
        "credit",
        "haben",
        "amount",
        "importo",
        "montant",
        "betrag",
    )
    for idx in range(min(df.height, 25)):
        row = _row_values(df, idx)
        score = _nonempty_count(row)
        for value in row:
            label = _norm_label(value)
            if any(token in label for token in header_tokens):
                score += 3
            elif any(ch.isalpha() for ch in label):
                score += 1
        if score > best_score:
            best_idx = idx
            best_score = score
    return [best_idx + 1]


def _merge_header_rows(rows: Sequence[Sequence[Any]]) -> list[str]:
    width = max((len(row) for row in rows), default=0)
    labels: list[str] = []
    for idx in range(width):
        parts = []
        for row in rows:
            value = _clean_text(row[idx] if idx < len(row) else "")
            if value and value.lower() not in {"none", "nan"}:
                parts.append(value)
        labels.append(" ".join(parts))
    return _unique_names(labels)


def _apply_header(df: pl.DataFrame, rows_1_indexed: Sequence[int]) -> pl.DataFrame:
    if df.is_empty():
        return df
    row_indexes = sorted({int(row) - 1 for row in rows_1_indexed})
    if not row_indexes or min(row_indexes) < 0:
        raise ValueError("Header rows must be 1-indexed positive integers.")
    if max(row_indexes) >= df.height:
        raise ValueError("Header row exceeds available rows.")
    labels = _merge_header_rows([_row_values(df, idx) for idx in row_indexes])
    body = df.slice(max(row_indexes) + 1)
    if body.width != len(labels):
        labels = _unique_names(labels[: body.width])
    body.columns = labels
    return _drop_empty_rows(_drop_empty_columns(body))


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        serial = float(value)
        if 20000 <= serial <= 60000:
            return date(1899, 12, 30) + timedelta(days=int(serial))
        return None
    text = _clean_text(value)
    if not text:
        return None
    token_match = DATE_TOKEN_RE.search(text)
    token = token_match.group(1) if token_match else text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)):
            return None
        return float(value)
    text = _clean_text(value)
    if not text:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text or text == "-":
        return None
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
    elif "," in text:
        decimal = ","
        thousands = "."
    else:
        decimal = "."
        thousands = ","
    text = text.replace(thousands, "").replace(decimal, ".").replace("-", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _date_ratio(series: pl.Series) -> float:
    values = [_parse_date(value) for value in series.drop_nulls().head(100).to_list()]
    if not values:
        return 0.0
    return sum(value is not None for value in values) / len(values)


def _amount_ratio(series: pl.Series) -> float:
    values = series.drop_nulls().head(100).to_list()
    if not values:
        return 0.0
    matches = sum(_parse_number(value) is not None for value in values)
    return matches / len(values)


def _first_matching_column(df: pl.DataFrame, tokens: Sequence[str]) -> str | None:
    for col in df.columns:
        label = _norm_label(col)
        if any(token in label for token in tokens):
            return col
    return None


def infer_mapping(df: pl.DataFrame) -> dict[str, str | None]:
    """Infer journal-entry fields from headers and lightweight profiles."""

    mapping: dict[str, str | None] = {
        "movement_number": _first_matching_column(
            df,
            (
                "nr. reg",
                "n. reg",
                "numero registrazione",
                "movimento",
                "movement",
                "mouvement",
                "bewegung",
                "reference",
                "riferimento",
                "beleg",
                "document",
            ),
        ),
        "date": _first_matching_column(df, ("data", "date", "datum")),
        "description": _first_matching_column(
            df,
            (
                "descrizione",
                "description",
                "causale",
                "libelle",
                "libellé",
                "beschreibung",
                "narrative",
            ),
        ),
        "beneficiary": _first_matching_column(
            df,
            (
                "beneficiario",
                "beneficiary",
                "payee",
                "fornitore",
                "supplier",
                "vendor",
                "fournisseur",
                "beguenstigter",
                "begünstigter",
                "creditore",
                "counterparty",
            ),
        ),
        "amount": _first_matching_column(
            df, ("amount", "importo", "montant", "betrag", "totale", "total")
        ),
        "debit_amount": _first_matching_column(df, ("dare", "debit", "débit", "soll")),
        "credit_amount": _first_matching_column(
            df, ("avere", "credit", "crédit", "haben")
        ),
    }
    if mapping["date"] is None:
        candidates = [(col, _date_ratio(df.get_column(col))) for col in df.columns]
        if candidates and max(score for _, score in candidates) >= 0.5:
            mapping["date"] = max(candidates, key=lambda item: item[1])[0]
    if (
        mapping["amount"] is None
        and mapping["debit_amount"] is None
        and mapping["credit_amount"] is None
    ):
        candidates = [(col, _amount_ratio(df.get_column(col))) for col in df.columns]
        amount_cols = [col for col, score in candidates if score >= 0.3]
        if len(amount_cols) >= 2:
            mapping["debit_amount"] = amount_cols[-2]
            mapping["credit_amount"] = amount_cols[-1]
        elif amount_cols:
            mapping["amount"] = amount_cols[-1]
    return mapping


def _mapped_value(row: dict[str, Any], mapping: dict[str, Any], key: str) -> Any:
    col = mapping.get(key)
    return row.get(str(col)) if col else None


def _normalize_entries(
    table: pl.DataFrame, mapping: dict[str, Any], path: Path
) -> pl.DataFrame:
    records: list[dict[str, Any]] = []
    for row_idx, row in enumerate(table.iter_rows(named=True), start=1):
        debit = _parse_number(_mapped_value(row, mapping, "debit_amount"))
        credit = _parse_number(_mapped_value(row, mapping, "credit_amount"))
        amount = _parse_number(_mapped_value(row, mapping, "amount"))
        if amount is not None and debit is None and credit is None:
            amount_signed = amount
        elif debit is not None or credit is not None:
            amount_signed = float(debit or 0.0) - float(credit or 0.0)
        else:
            amount_signed = None
        parsed_date = _parse_date(_mapped_value(row, mapping, "date"))
        movement = _clean_text(_mapped_value(row, mapping, "movement_number"))
        description = _clean_text(_mapped_value(row, mapping, "description"))
        beneficiary = _clean_text(_mapped_value(row, mapping, "beneficiary"))
        if not movement and not description and amount_signed is None:
            continue
        records.append(
            {
                "movement_number": movement or str(row_idx),
                "entry_date": parsed_date.isoformat() if parsed_date else None,
                "description": description or None,
                "beneficiary_expected": beneficiary or None,
                "amount_signed": amount_signed,
                "amount_abs": abs(amount_signed) if amount_signed is not None else None,
                "source_file": path.name,
                "source_row": row_idx,
            }
        )
    return (
        pl.DataFrame(records, schema=CANONICAL_ENTRY_COLUMNS)
        if records
        else pl.DataFrame(schema=CANONICAL_ENTRY_COLUMNS)
    )


def _load_journal_entries(
    path: Path, recipe: dict[str, Any]
) -> tuple[pl.DataFrame, dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raise ValueError(
            "Text-PDF journal parsing is not supported for Check Entries v1. "
            "Use Journal Sampling to normalize the PDF first, then run Check Entries."
        )
    raw_df = _read_tabular_raw(path)
    recipe_journal = (
        recipe.get("journal") if isinstance(recipe.get("journal"), dict) else {}
    )
    header_rows = recipe_journal.get("header_rows") or _suggest_header_rows(raw_df)
    table = _apply_header(raw_df, header_rows)
    mapping = (
        recipe_journal.get("mapping")
        if isinstance(recipe_journal.get("mapping"), dict)
        else infer_mapping(table)
    )
    frame = _normalize_entries(table, mapping, path)
    diagnostics = {
        "source_file": path.name,
        "header_rows": header_rows,
        "mapping": mapping,
        "raw_columns": table.columns,
        "row_count": frame.height,
        "preview": frame.head(20).to_dicts(),
        "missing_required_mapping": _missing_mapping(mapping),
    }
    return frame, diagnostics


def _missing_mapping(mapping: dict[str, Any]) -> list[str]:
    missing = []
    if not mapping.get("movement_number"):
        missing.append("movement_number")
    if not (
        mapping.get("amount")
        or (mapping.get("debit_amount") and mapping.get("credit_amount"))
    ):
        missing.append("amount or debit_amount/credit_amount")
    return missing


def supported_pdfs(pdf_path: Path) -> list[Path]:
    """Return supported PDF files from a file or folder path."""

    path = pdf_path.expanduser()
    if path.is_file():
        return [path] if path.suffix.lower() in PDF_SUFFIXES else []
    if not path.exists():
        raise FileNotFoundError(f"PDF path does not exist: {path}")
    return [
        candidate
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file()
        and candidate.suffix.lower() in PDF_SUFFIXES
        and not candidate.name.startswith("~$")
    ]


def _extract_pdf_text(path: Path) -> str:
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return "\n".join(lines)


def _pdf_inventory(pdf_path: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for file_path in supported_pdfs(pdf_path):
        text = ""
        extractable = False
        error = None
        try:
            text = _extract_pdf_text(file_path)
            extractable = bool(text.strip())
        except (OSError, ValueError, RuntimeError) as exc:
            error = str(exc)
        inventory.append(
            {
                "filename": file_path.name,
                "path": file_path.as_posix(),
                "extractable_text": extractable,
                "text_chars": len(text),
                "error": error,
            }
        )
    return inventory


def _invoice_inventory(
    support_path: Path,
) -> tuple[list[InvoiceRecord], list[dict[str, str]]]:
    """Load FatturaPA XML only where the supplied support path can contain it."""

    if support_path.is_dir() or support_path.suffix.lower() in {".zip", ".xml", ".p7m"}:
        return load_invoice_records(support_path)
    return [], []


def inspect_entries(
    journal: Path,
    pdf_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    language: object | None = None,
    document_language: object | None = None,
) -> InspectionResult:
    """Inspect journal entries and PDF/XML support, then write Codex artifacts."""

    recipe = read_json(recipe_path)
    languages = language_assumptions(
        recipe, language=language, document_language=document_language
    )
    frame, journal_diag = _load_journal_entries(journal, recipe)
    pdfs = _pdf_inventory(pdf_path)
    invoices, invoice_errors = _invoice_inventory(pdf_path)
    confidence = 0.9
    if journal_diag["missing_required_mapping"]:
        confidence -= 0.3
    if not pdfs and not invoices:
        confidence -= 0.3
    if any(not item["extractable_text"] for item in pdfs):
        confidence -= 0.2
    suggested_recipe = {
        "version": 1,
        "description": "Deterministic check-entries recipe generated by Codex.",
        **languages,
        "journal": {
            "parser": "tabular",
            "header_rows": journal_diag["header_rows"],
            "mapping": journal_diag["mapping"],
        },
        "pdf_matching": {
            "mode": "filename_or_text_contains_movement_number",
            "allow_single_pdf_single_entry": True,
        },
        "acquisition_ladder": [
            "fatturapa_zip",
            "authorized_connector_export",
            "targeted_pdf_fallback",
        ],
        "xml_matching": {
            "mode": "unique_two_signal_match",
            "signals": ["invoice_number", "amount", "date", "beneficiary"],
            "ambiguous_matches_require_review": True,
        },
        "checks": {
            "amount_tolerance": 0.0,
            "date_window_days": 0,
            "beneficiary_match": "token containment when beneficiary_expected is mapped",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "inspection.json",
        {
            **languages,
            "confidence": round(max(confidence, 0.0), 2),
            "journal": journal_diag,
            "pdfs": pdfs,
            "invoices": [invoice.as_dict() for invoice in invoices],
            "invoice_errors": invoice_errors,
        },
    )
    write_json(output_dir / "suggested_recipe.json", suggested_recipe)
    return InspectionResult(
        journal=journal_diag,
        pdfs=pdfs,
        invoices=[invoice.as_dict() for invoice in invoices],
        suggested_recipe=suggested_recipe,
    )


def _movement_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _norm_label(value))


def _load_pdf_texts(pdf_path: Path) -> dict[str, dict[str, Any]]:
    pdfs: dict[str, dict[str, Any]] = {}
    for file_path in supported_pdfs(pdf_path):
        try:
            text = _extract_pdf_text(file_path)
            pdfs[file_path.name] = {
                "path": file_path,
                "text": text,
                "text_norm": _normalize_search_text(text),
                "error": None,
            }
        except (OSError, ValueError, RuntimeError) as exc:
            pdfs[file_path.name] = {
                "path": file_path,
                "text": "",
                "text_norm": "",
                "error": str(exc),
            }
    return pdfs


def _match_pdf_for_entry(
    entry: dict[str, Any], pdfs: dict[str, dict[str, Any]]
) -> str | None:
    movement = _movement_key(entry.get("movement_number"))
    if len(pdfs) == 1 and movement:
        return next(iter(pdfs))
    if not movement:
        return None
    for filename in pdfs:
        if movement and movement in _movement_key(filename):
            return filename
    for filename, payload in pdfs.items():
        if movement and movement in _movement_key(payload["text"]):
            return filename
    return None


def _amounts_in_text(text: str) -> list[float]:
    values: list[float] = []
    for match in AMOUNT_TOKEN_RE.finditer(text):
        value = _parse_number(match.group(0))
        if value is not None:
            values.append(value)
    return values


def _dates_in_text(text: str) -> list[date]:
    values: list[date] = []
    for match in DATE_TOKEN_RE.finditer(text):
        parsed = _parse_date(match.group(1))
        if parsed is not None:
            values.append(parsed)
    return values


def _amount_found(expected: float | None, text: str, tolerance: float) -> float | None:
    if expected is None:
        return None
    for value in _amounts_in_text(text):
        if abs(abs(value) - abs(expected)) <= tolerance:
            return value
    return None


def _date_found(expected: str | None, text: str, window_days: int) -> str | None:
    parsed = _parse_date(expected)
    if parsed is None:
        return None
    for value in _dates_in_text(text):
        if abs((value - parsed).days) <= window_days:
            return value.isoformat()
    return None


def _beneficiary_found(expected: str | None, text_norm: str) -> str | None:
    expected_norm = _normalize_search_text(expected)
    if not expected_norm:
        return None
    if expected_norm in text_norm:
        return expected
    tokens = [token for token in expected_norm.split() if len(token) > 2]
    if tokens and all(token in text_norm for token in tokens):
        return expected
    return None


def _check_one_entry(
    entry: dict[str, Any],
    pdfs: dict[str, dict[str, Any]],
    *,
    amount_tolerance: float,
    date_window_days: int,
) -> dict[str, Any]:
    matched_pdf = _match_pdf_for_entry(entry, pdfs)
    if matched_pdf is None:
        return {
            **entry,
            "status": "missing_support",
            "matched_pdf": None,
            "checks_run": "",
            "mismatches": "support_pdf",
            "review_notes": "No supporting PDF matched the movement number.",
            "amount_found": None,
            "date_found": None,
            "beneficiary_found": None,
            "matched_support": None,
            "support_type": None,
        }

    pdf_payload = pdfs[matched_pdf]
    text = str(pdf_payload["text"])
    text_norm = str(pdf_payload["text_norm"])
    checks_run: list[str] = []
    mismatches: list[str] = []
    review_notes: list[str] = []

    expected_amount = entry.get("amount_abs")
    amount_value = _amount_found(
        float(expected_amount) if expected_amount is not None else None,
        text,
        amount_tolerance,
    )
    if expected_amount is not None:
        checks_run.append("amount")
        if amount_value is None:
            mismatches.append("amount")

    expected_date = entry.get("entry_date")
    date_value = _date_found(
        str(expected_date) if expected_date else None, text, date_window_days
    )
    if expected_date:
        checks_run.append("date")
        if date_value is None:
            mismatches.append("date")

    expected_beneficiary = entry.get("beneficiary_expected")
    beneficiary_value = _beneficiary_found(
        str(expected_beneficiary) if expected_beneficiary else None, text_norm
    )
    if expected_beneficiary:
        checks_run.append("beneficiary")
        if beneficiary_value is None:
            mismatches.append("beneficiary")

    if pdf_payload["error"]:
        mismatches.append("pdf_text")
        review_notes.append(f"PDF text extraction error: {pdf_payload['error']}")
    if not checks_run:
        status = "manual_review"
        review_notes.append("No amount, date, or beneficiary fields were available.")
    elif mismatches:
        status = "mismatch"
    else:
        status = "ok"

    return {
        **entry,
        "status": status,
        "matched_pdf": matched_pdf,
        "checks_run": ",".join(checks_run),
        "mismatches": ",".join(dict.fromkeys(mismatches)),
        "review_notes": " ".join(review_notes),
        "amount_found": amount_value,
        "date_found": date_value,
        "beneficiary_found": beneficiary_value,
        "matched_support": matched_pdf,
        "support_type": "pdf",
    }


def _check_entry_with_support_ladder(
    entry: dict[str, Any],
    invoices: list[InvoiceRecord],
    pdfs: dict[str, dict[str, Any]],
    *,
    amount_tolerance: float,
    date_window_days: int,
) -> dict[str, Any]:
    """Try structured XML first and fall back to a matching PDF."""

    invoice, signals, xml_issue = match_invoice(
        entry,
        invoices,
        amount_tolerance=amount_tolerance,
        date_window_days=date_window_days,
    )
    if invoice is not None:
        mismatches: list[str] = []
        for field, signal in (
            ("amount_abs", "amount"),
            ("entry_date", "date"),
            ("beneficiary_expected", "beneficiary"),
        ):
            if entry.get(field) not in (None, "") and signal not in signals:
                mismatches.append(signal)
        status = "mismatch" if mismatches else "ok"
        return {
            **entry,
            "status": status,
            "matched_pdf": None,
            "checks_run": ",".join(signals),
            "mismatches": ",".join(mismatches),
            "review_notes": (
                "Matched a unique FatturaPA XML using at least two independent fields."
                if not mismatches
                else "Matched a unique FatturaPA XML, but one or more available fields differ."
            ),
            "amount_found": invoice.total_amount if "amount" in signals else None,
            "date_found": invoice.invoice_date if "date" in signals else None,
            "beneficiary_found": (
                entry.get("beneficiary_expected") if "beneficiary" in signals else None
            ),
            "matched_support": invoice.source_name,
            "support_type": "fatturapa_xml",
        }
    pdf_result = _check_one_entry(
        entry,
        pdfs,
        amount_tolerance=amount_tolerance,
        date_window_days=date_window_days,
    )
    if xml_issue and pdf_result["status"] == "missing_support":
        pdf_result["review_notes"] = (
            "Multiple FatturaPA XML candidates matched; targeted support or reviewer selection is required."
        )
        pdf_result["mismatches"] = "ambiguous_invoice_support"
    return pdf_result


def _status_counts(frame: pl.DataFrame) -> dict[str, int]:
    if frame.is_empty() or "status" not in frame.columns:
        return {}
    counts = frame.group_by("status").len(name="count").to_dicts()
    return {str(item["status"]): int(item["count"]) for item in counts}


def _write_review_notes(path: Path, audit: dict[str, Any]) -> None:
    lines = [
        "# Check Entries Review Notes",
        "",
        f"- Language: {audit['language']}",
        f"- Journal rows: {audit['journal_row_count']}",
        f"- Support PDFs: {audit['pdf_count']}",
        f"- FatturaPA XMLs: {audit['invoice_count']}",
        f"- Result rows: {audit['result_row_count']}",
        "",
        "## Status Counts",
    ]
    counts = audit.get("status_counts", {})
    if counts:
        for status, count in sorted(counts.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Review Policy",
            "The scripts only compare deterministic evidence. Codex must explain unresolved cases, inspect support where needed, and keep professional judgment explicit.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_entry_checks(
    journal: Path,
    pdf_path: Path,
    output_dir: Path,
    recipe_path: Path | None = None,
    *,
    amount_tolerance: float = 0.0,
    date_window_days: int = 0,
    language: object | None = None,
    document_language: object | None = None,
    connector_name: str | None = None,
) -> CheckRunResult:
    """Run deterministic support checks and write reviewable artifacts."""

    recipe = read_json(recipe_path)
    languages = language_assumptions(
        recipe, language=language, document_language=document_language
    )
    entries, journal_diag = _load_journal_entries(journal, recipe)
    pdfs = _load_pdf_texts(pdf_path)
    invoices, invoice_errors = _invoice_inventory(pdf_path)
    records = [
        _check_entry_with_support_ladder(
            row,
            invoices,
            pdfs,
            amount_tolerance=amount_tolerance,
            date_window_days=date_window_days,
        )
        for row in entries.to_dicts()
    ]
    result_frame = (
        pl.DataFrame(records, schema=RESULT_COLUMNS)
        if records
        else pl.DataFrame(schema=RESULT_COLUMNS)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / "normalized_entries.csv"
    results_path = output_dir / "check_results.csv"
    xlsx_path = output_dir / "check_results.xlsx"
    inventory_path = output_dir / "pdf_inventory.json"
    invoice_inventory_path = output_dir / "invoice_inventory.json"
    audit_path = output_dir / "check_audit.json"
    review_notes_path = output_dir / "review_notes.md"

    entries.write_csv(normalized_path)
    result_frame.write_csv(results_path)
    try:
        result_frame.write_excel(xlsx_path)
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError) as exc:
        LOGGER.warning("Could not write XLSX results; CSV is available: %s", exc)
    pdf_inventory = [
        {
            "filename": filename,
            "path": str(payload["path"]),
            "extractable_text": bool(payload["text"].strip()),
            "text_chars": len(str(payload["text"])),
            "error": payload["error"],
        }
        for filename, payload in pdfs.items()
    ]
    run_intake = write_run_intake(
        output_dir,
        journal,
        pdf_path,
        recipe_path=recipe_path,
        language=languages["language"],
        document_language=languages["document_language"],
        amount_tolerance=amount_tolerance,
        date_window_days=date_window_days,
        mapping=journal_diag["mapping"],
        journal_row_count=entries.height,
        pdf_count=len(pdfs),
        invoice_count=len(invoices),
        connector_name=connector_name,
    )
    write_json(inventory_path, pdf_inventory)
    write_json(
        invoice_inventory_path,
        {
            "source_kind": (
                "authorized_connector_export" if connector_name else "local_upload"
            ),
            "connector_name": connector_name,
            "invoice_count": len(invoices),
            "invoices": [invoice.as_dict() for invoice in invoices],
            "errors": invoice_errors,
        },
    )
    audit = {
        **languages,
        "run_id": run_intake.run_id,
        "journal": journal.as_posix(),
        "pdf_path": pdf_path.as_posix(),
        "journal_row_count": entries.height,
        "pdf_count": len(pdfs),
        "invoice_count": len(invoices),
        "invoice_error_count": len(invoice_errors),
        "connector_name": connector_name,
        "result_row_count": result_frame.height,
        "status_counts": _status_counts(result_frame),
        "amount_tolerance": amount_tolerance,
        "date_window_days": date_window_days,
        "mapping": journal_diag["mapping"],
        "outputs": {
            "normalized_entries_csv": normalized_path.as_posix(),
            "check_results_csv": results_path.as_posix(),
            "check_results_xlsx": xlsx_path.as_posix() if xlsx_path.exists() else None,
            "pdf_inventory_json": inventory_path.as_posix(),
            "invoice_inventory_json": invoice_inventory_path.as_posix(),
            "review_notes_md": review_notes_path.as_posix(),
        },
    }
    write_json(audit_path, audit)
    _write_review_notes(review_notes_path, audit)
    review_session = write_review_session_artifacts(
        output_dir,
        journal,
        pdf_path,
        run_id=run_intake.run_id,
        run_intake_path=run_intake.path,
        recipe_path=recipe_path,
        language=languages["language"],
        document_language=languages["document_language"],
        amount_tolerance=amount_tolerance,
        date_window_days=date_window_days,
        mapping=journal_diag["mapping"],
        result_rows=result_frame.to_dicts(),
        pdf_inventory=pdf_inventory,
        audit=audit,
    )
    audit["review_session"] = {
        "run_intake_path": review_session.run_intake_path.name,
        "review_payload_path": review_session.review_payload_path.name,
        "ui_decisions_path": review_session.ui_decisions_path.name,
        "final_artifacts_path": review_session.final_artifacts_path.name,
        "review_item_count": review_session.review_item_count,
    }
    write_json(audit_path, audit)
    return CheckRunResult(frame=result_frame, audit=audit)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--language",
        help="Working/output language locale: it, en, fr, or de. Defaults to recipe or en.",
    )
    parser.add_argument(
        "--document-language",
        help="Source-document language locale: it, en, fr, de, or auto. Defaults to recipe or auto.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
