from __future__ import annotations

"""File loaders and header inference helpers.

This module centralises spreadsheet/PDF header inference helpers used by
bank/ledger loaders. Implementations were previously in
``check_statements_logic`` and are now extracted here to reduce coupling.
"""

import io
import itertools
import json
import logging
import re
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import polars as pl

from src.bank_keywords import BASE_BANK_KEYWORDS

logger = logging.getLogger(__name__)

try:
    from modules.utilities.fastexcel import suppress_fastexcel_dtype_warnings
except Exception:  # pragma: no cover - fallback when helper is unavailable

    @contextmanager
    def suppress_fastexcel_dtype_warnings():
        local_logger = logging.getLogger("fastexcel.types.dtype")
        previous_level = local_logger.level
        local_logger.setLevel(logging.ERROR)
        try:
            yield
        finally:
            local_logger.setLevel(previous_level)


def _norm_token(s: str) -> str:
    """lowercase, strip accents, remove punctuation/spaces for robust matching."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"[^a-z0-9]", "", s)


# Normalised keyword groups for quick membership checks
_KW_NORM = {k: {_norm_token(x) for x in v} for k, v in BASE_BANK_KEYWORDS.items()}

# Extended mapping including optional beneficiary column
BANK_KEYWORDS = {
    **BASE_BANK_KEYWORDS,
    "beneficiary": [
        "beneficiario",
        "beneficiary",
        "conto",
        "c/c",
        "cliente",
        "fornitore",
        "cliente/fornitore",
        "beneficiario/cliente",
        "beneficiario/fornitore",
    ],
}


def _detect_excel_header_polars(content: bytes, max_rows: int = 50) -> int | None:
    """Detect the header row in an Excel sheet using Polars only.

    Reads the sheet with ``has_header=False`` and scans the first ``max_rows``
    looking for a row that matches at least two semantic groups among
    ``date``, ``description``, ``debit``, ``credit``, ``amount``.
    """
    try:
        with suppress_fastexcel_dtype_warnings():
            df0 = pl.read_excel(
                source=io.BytesIO(content),
                has_header=False,
                drop_empty_rows=False,
                drop_empty_cols=False,
                raise_if_empty=False,
                engine="calamine",
            )
    except (IndexError, pl.exceptions.PolarsError) as exc:  # pragma: no cover
        raise ValueError("Excel file has no sheets") from exc
    if df0.height == 0 or df0.width == 0:
        return None

    head = df0.head(max_rows).fill_null("")
    for i in range(head.height):
        row = head.slice(i, 1).rows()[0]
        tokens = {_norm_token(v) for v in row if isinstance(v, str) and v.strip()}
        if not tokens:
            continue
        hits = 0
        for group in ("date", "description", "debit", "credit", "amount"):
            if tokens & _KW_NORM[group]:
                hits += 1
        if hits >= 2:
            return i
    return None


def _rebuild_df_with_header(content: bytes, header_row: int | None) -> pl.DataFrame:
    """Promote a detected header row to column names and drop rows above it."""
    if header_row is None:
        try:
            with suppress_fastexcel_dtype_warnings():
                df = pl.read_excel(
                    source=io.BytesIO(content),
                    has_header=False,
                    drop_empty_rows=False,
                    drop_empty_cols=False,
                    engine="calamine",
                )
        except (IndexError, pl.exceptions.PolarsError) as exc:  # pragma: no cover
            raise ValueError("Excel file has no sheets") from exc
        df.columns = [f"col_{i+1}" for i in range(df.width)]
        return df

    try:
        with suppress_fastexcel_dtype_warnings():
            df0 = pl.read_excel(
                source=io.BytesIO(content),
                has_header=False,
                drop_empty_rows=False,
                drop_empty_cols=False,
                engine="calamine",
            )
    except (IndexError, pl.exceptions.PolarsError) as exc:  # pragma: no cover
        raise ValueError("Excel file has no sheets") from exc
    if df0.height <= header_row + 1:
        try:
            with suppress_fastexcel_dtype_warnings():
                return pl.read_excel(
                    source=io.BytesIO(content),
                    has_header=True,
                    drop_empty_rows=True,
                    drop_empty_cols=True,
                    engine="calamine",
                )
        except (IndexError, pl.exceptions.PolarsError) as exc:  # pragma: no cover
            raise ValueError("Excel file has no sheets") from exc

    header_vals = list(df0.slice(header_row, 1).rows()[0])
    header_names: list[str] = []
    seen: dict[str, int] = {}
    for j, v in enumerate(header_vals[: df0.width]):
        name = str(v).strip() if isinstance(v, str) and v.strip() else f"col_{j+1}"
        base = re.sub(r"\s+", " ", name)
        cnt = seen.get(base, 0)
        seen[base] = cnt + 1
        header_names.append(base if cnt == 0 else f"{base}_{cnt+1}")

    df = df0.slice(header_row + 1).with_columns([pl.all().cast(pl.Utf8, strict=False)])
    df.columns = header_names
    # Drop rows that are completely empty across all columns
    try:
        mask = None
        for c in df.columns:
            col = df.get_column(c)
            col_mask = col.is_not_null() & (
                col.cast(pl.Utf8).str.strip_chars().cast(pl.Utf8) != ""
            )
            mask = col_mask if mask is None else (mask | col_mask)
        if mask is not None:
            df = df.filter(mask)
    except Exception as e:
        logger.exception("Failed to drop empty rows in rebuilt Excel frame: %s", e)
    return df


def _infer_columns(
    headers: Sequence[str], known_keys: Dict[str, List[str]]
) -> Dict[str, Optional[int]]:
    """Infer column indices for known fields from a list of headers."""
    mapping: Dict[str, Optional[int]] = {}
    lowered = [h.lower().strip() for h in headers]
    for field, options in known_keys.items():
        idx = None
        for i, name in enumerate(lowered):
            for opt in options:
                if opt in name:
                    idx = i
                    break
            if idx is not None:
                break
        mapping[field] = idx
    logger.debug("Column mapping resolved: %s", mapping)
    return mapping


def _resolve_account_col(df: pl.DataFrame) -> str | None:
    """Return the column holding account identifiers, if any."""
    try:
        from modules.utilities.utils import get_schema_and_column_names
    except Exception:  # pragma: no cover

        def get_schema_and_column_names(df):  # type: ignore
            return (getattr(df, "columns", []), getattr(df, "schema", {}))

    cols, _ = get_schema_and_column_names(df)
    ACCOUNT_COL_KEYWORDS: list[str] = ["conto", "account", "acct", "iban"]
    for col in cols:
        if col.lower() in ACCOUNT_COL_KEYWORDS:
            return col
    for col in cols:
        tokens = [
            token.lower()
            for token in re.split(r"[_\W]+|(?<=[a-z])(?=[A-Z])", col)
            if token
        ]
        if any(keyword in tokens for keyword in ACCOUNT_COL_KEYWORDS):
            return col
    return None


__all__ = (
    "_detect_excel_header_polars",
    "_infer_columns",
    "_rebuild_df_with_header",
    "_resolve_account_col",
    "guess_columns_from_data",
    "parse_spreadsheet_prepare",
    "parse_spreadsheet_prepare_with_keywords",
    "ocr_extract_pdf_text",
    "_resolve_mapping",
    "_validate_required_columns",
    "parse_pdf_prepare",
    "load_ledger_rows",
    "load_bank_rows",
    "parse_bank_text_prepare",
)


def guess_columns_from_data(df: pl.DataFrame, sample_rows: int = 20) -> Dict[str, int]:
    """Heuristically guess date/amount/description columns from data values.

    This is a lightweight, self-contained variant to avoid importing from the
    main logic module and creating cycles. It aims to be conservative and only
    used when header inference fails to identify key columns.
    """
    try:
        from modules.utilities.utils import get_schema_and_column_names
    except Exception:  # pragma: no cover

        def get_schema_and_column_names(df):  # type: ignore
            return (getattr(df, "columns", []), getattr(df, "schema", {}))

    def _parse_amount(value: object) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return None
        negative = False
        if s.startswith("(") and s.endswith(")"):
            negative = True
            s = s[1:-1]
        if s.endswith("-"):
            negative = True
            s = s[:-1]
        s = s.replace("€", "").replace("£", "")
        s = re.sub(r"[€$£\s\u00A0]", "", s)
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "." in s:
            s = s.replace(",", "")
        try:
            val = float(s)
        except ValueError:
            m = re.search(r"[-+]?[0-9]+(?:[.,][0-9]+)?", s)
            if not m:
                return None
            try:
                val = float(m.group(0).replace(",", "."))
            except ValueError:
                return None
        return -val if negative else val

    def _parse_date_any(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return False
        s = str(value).strip()
        if not s:
            return False
        # Common date formats
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", s):
            return True
        if re.search(r"\b\d{2}/\d{2}/\d{2,4}\b", s):
            return True
        return False

    head = df.head(sample_rows)
    cols, _ = get_schema_and_column_names(df)
    stats: List[Dict[str, object]] = []
    for idx, col in enumerate(cols):
        series = head.get_column(col)
        date_count = 0
        num_count = 0
        pos = 0
        neg = 0
        present: set[int] = set()
        for row_idx, val in enumerate(series.to_list()):
            if _parse_date_any(val):
                date_count += 1
            amt = _parse_amount(val)
            if amt is not None:
                num_count += 1
                present.add(row_idx)
                pos += 1 if amt > 0 else 0
                neg += 1 if amt < 0 else 0
        stats.append(
            {
                "idx": idx,
                "date": date_count,
                "num": num_count,
                "pos": pos,
                "neg": neg,
                "rows": present,
            }
        )

    mapping: Dict[str, int] = {}
    if any(s["date"] > 0 for s in stats):
        mapping["date"] = max(stats, key=lambda s: s["date"])  # type: ignore[index]
        mapping["date"] = mapping["date"]["idx"]  # type: ignore[index]

    numeric_stats = [s for s in stats if s["num"] > 0]
    if len(numeric_stats) >= 2:
        pos_only = [s for s in numeric_stats if s["pos"] > 0 and s["neg"] == 0]
        neg_only = [s for s in numeric_stats if s["neg"] > 0 and s["pos"] == 0]
        if len(pos_only) == 1 and len(neg_only) == 1:
            mapping["credit"] = pos_only[0]["idx"]  # type: ignore[index]
            mapping["debit"] = neg_only[0]["idx"]  # type: ignore[index]
        else:
            for a, b in itertools.combinations(numeric_stats, 2):
                if a["rows"] and b["rows"] and not (a["rows"] & b["rows"]):  # type: ignore[operator]
                    mapping["debit"] = a["idx"]  # type: ignore[index]
                    mapping["credit"] = b["idx"]  # type: ignore[index]
                    break

    if "credit" not in mapping and "debit" not in mapping and numeric_stats:
        both = [s for s in numeric_stats if s["pos"] > 0 and s["neg"] > 0]
        if both:
            mapping["amount"] = max(both, key=lambda s: s["num"])  # type: ignore[index]
            mapping["amount"] = mapping["amount"]["idx"]  # type: ignore[index]
        else:
            mapping["amount"] = max(numeric_stats, key=lambda s: s["num"])  # type: ignore[index]
            mapping["amount"] = mapping["amount"]["idx"]  # type: ignore[index]

    used = {mapping[k] for k in mapping}
    for s in stats:
        if s["idx"] in used:
            continue
        if s["num"] == 0 and s["date"] == 0:
            mapping["description"] = s["idx"]  # type: ignore[index]
            break
    return mapping


def parse_spreadsheet_prepare(
    content: bytes,
    filename: str,
    *,
    max_header_scan_rows: int = 50,
) -> tuple[pl.DataFrame, Dict[str, Optional[int]]]:
    """Read a spreadsheet (CSV/XLS/XLSX) and infer column indices.

    Args:
        content: File bytes (CSV/XLS/XLSX).
        filename: Used only for extension detection (no I/O).
        max_header_scan_rows: Max rows to scan to detect the header row in Excel.

    Returns:
        A tuple ``(df, mapping)`` where ``df`` is the parsed DataFrame and
        ``mapping`` contains index positions for canonical fields
        ``date``, ``amount``, ``debit``, ``credit``, ``description``
        when they can be inferred. Missing entries are left as ``None``.
    """
    data = io.BytesIO(content)
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pl.read_csv(data)
    else:
        hdr = _detect_excel_header_polars(content, max_rows=max_header_scan_rows)
        df = _rebuild_df_with_header(content, hdr)
    if df is None or df.height == 0:
        return df, {}
    # Build header-based mapping first
    headers = [str(c) for c in df.columns]
    mapping = _infer_columns(headers, BANK_KEYWORDS)
    # Fallback to data-driven guess when key fields are missing
    if mapping.get("date") is None or mapping.get("amount") is None:
        guessed = guess_columns_from_data(df)
        for key, idx in guessed.items():
            if mapping.get(key) is None:
                mapping[key] = idx
    return df, mapping


def parse_spreadsheet_prepare_with_keywords(
    content: bytes,
    filename: str,
    keywords: Dict[str, List[str]],
    *,
    max_header_scan_rows: int = 50,
) -> tuple[pl.DataFrame, Dict[str, Optional[int]]]:
    """Same as ``parse_spreadsheet_prepare`` but using caller-provided header keywords.

    Args:
        content: File bytes (CSV/XLS/XLSX).
        filename: Used only for extension detection (no I/O).
        keywords: Mapping of canonical fields to header keywords.
        max_header_scan_rows: Max rows to scan to detect the header row in Excel.

    Returns:
        ``(df, mapping)`` as for ``parse_spreadsheet_prepare``.
    """
    data = io.BytesIO(content)
    name_lower = (filename or "").lower()
    if name_lower.endswith(".csv"):
        df = pl.read_csv(data)
    else:
        hdr = _detect_excel_header_polars(content, max_rows=max_header_scan_rows)
        df = _rebuild_df_with_header(content, hdr)
    if df is None or df.height == 0:
        return df, {}
    headers = [str(c) for c in df.columns]
    mapping = _infer_columns(headers, keywords)
    if mapping.get("date") is None or mapping.get("amount") is None:
        guessed = guess_columns_from_data(df)
        for key, idx in guessed.items():
            if mapping.get(key) is None:
                mapping[key] = idx
    return df, mapping


def ocr_extract_pdf_text(
    content: bytes,
    *,
    llm_wrapper: object | None,
    language: str,
    retries: int = 2,
) -> str:
    """Return OCR-extracted text from a PDF.

    Args:
        content: PDF file bytes.
        llm_wrapper: Accepted for compatibility; OCR helpers ignore it.
        language: OCR language hint (e.g., "ita").
        retries: Number of retry attempts for OCR failures.

    Notes:
        This is a thin helper around ``modules.pdf_utils.pdf_utils.extract_pdf_text_with_ocr``
        to keep PDF OCR concerns outside the main logic module. OCR is local-only.
    """
    try:
        from modules.pdf_utils.pdf_utils import (
            extract_pdf_text_with_ocr,  # type: ignore
        )
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ImportError("extract_pdf_text_with_ocr not available") from exc

    result = extract_pdf_text_with_ocr(
        pdf_bytes=content, llm_wrapper=llm_wrapper, lang=language, retries=retries
    )
    return result.text if hasattr(result, "text") else str(result)


def _resolve_mapping(
    columns: Sequence[str],
    mapping: Dict[str, Optional[int]],
) -> Dict[str, str]:
    """Return a field→column-name map (validating index bounds)."""
    resolved: Dict[str, str] = {}
    for field, idx in mapping.items():
        if isinstance(idx, int) and 0 <= idx < len(columns):
            resolved[field] = columns[idx]
    return resolved


def _validate_required_columns(resolved: Dict[str, str]) -> None:
    """Ensure mandatory columns are present after header resolution.

    Requires either ``amount`` or both ``debit`` and ``credit``.
    Raises ``ValueError`` when required fields are missing.
    """
    missing: List[str] = []
    if "date" not in resolved:
        missing.append("date")
    if "amount" not in resolved and not ("debit" in resolved and "credit" in resolved):
        if "amount" not in resolved:
            missing.append("amount")
        if "debit" not in resolved:
            missing.append("debit")
        if "credit" not in resolved:
            missing.append("credit")
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def parse_pdf_prepare(
    content: bytes,
    filename: str,
    *,
    language: str,
    deterministic_only: bool,
    progress_callback: Callable[[float, int, tuple[date, date]], None] | None = None,
    strict: bool = False,
) -> list[dict]:
    """Fast-path PDF parsing using GenericStatementParser or bank_agent.

    Args:
        content: PDF file bytes.
        filename: Used to infer suffix and for source metadata.
        language: Locale hint for PDF parsing.
        deterministic_only: When True, disable any non-deterministic heuristics.
        progress_callback: Optional callback ``(file_progress, rows_so_far, (min_date, max_date))``.
        strict: When True, propagate parser exceptions.

    Returns:
        List of row dicts: ``date`` (date|None), ``amount`` (float), ``description`` (str),
        ``beneficiary`` (str|None), ``reference_ids`` (list[str]). Empty list if nothing parsed.
    """
    rows_out: list[dict] = []

    def _tmp_file(bytes_obj: bytes, name: str) -> Path:
        suffix = ""
        try:
            dot = name.rfind(".")
            suffix = name[dot:] if dot != -1 else ""
        except Exception:
            suffix = ""
        f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        f.write(bytes_obj)
        f.flush()
        f.close()
        return Path(f.name)

    # 1) try new generic parser
    try:
        from parsers.generic_statement import GenericStatementParser  # type: ignore

        try:
            tmp_path = _tmp_file(content, filename)
            parser = GenericStatementParser(
                deterministic_only=deterministic_only,
                progress_callback=progress_callback,
                strict=strict,
            )
            rows = parser.parse(
                tmp_path, locale_hint=language, progress_callback=progress_callback
            )
            if rows:
                for r in rows:
                    desc = (r.description or "").strip()
                    ben = getattr(r, "counterparty", None) or None
                    amt = (
                        float(r.amount)
                        if isinstance(r.amount, Decimal)
                        else float(r.amount)
                    )
                    d = r.booking_date if isinstance(r.booking_date, date) else None
                    if d is None and isinstance(r.booking_date, datetime):
                        d = r.booking_date.date()
                    rows_out.append(
                        {
                            "date": d,
                            "amount": amt,
                            "description": desc,
                            "beneficiary": ben,
                            "reference_ids": list(
                                getattr(r, "reference_ids", []) or []
                            ),
                        }
                    )
                # keep rows and allow supplemental parsing below
        except Exception:
            # Fall through to bank_agent path
            pass
        finally:
            try:
                if "tmp_path" in locals():
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception as e:
                logger.exception("Temporary file cleanup failed: %s", e)
    except Exception:
        # Optional dependency may be unavailable
        pass

    # 2) bank-agent parser
    try:
        from modules.pdf_utils.bank_agent import extract_bank_pdf  # type: ignore

        try:
            parsed_tx = extract_bank_pdf(content, lang=language)
            if parsed_tx:
                for t in parsed_tx:
                    desc = (t.description or "").strip()
                    d = (
                        t.date.date()
                        if isinstance(t.date, datetime)
                        else (t.date if isinstance(t.date, date) else None)
                    )
                    rows_out.append(
                        {
                            "date": d,
                            "amount": float(t.amount),
                            "description": desc,
                            "beneficiary": None,
                            "reference_ids": [],
                        }
                    )
                # keep rows, allow manual fallbacks to add missing movements
        except Exception as e:
            logger.exception("bank_agent parsing failed: %s", e)
    except Exception as e:
        logger.exception("bank_agent import failed: %s", e)

    # 3) fallback: manual parsing for statement layouts not handled above
    try:
        extra_rows = _parse_pdf_prelevi_fallback(content, language=language)
        if extra_rows:
            existing = {
                (row.get("date"), round(float(row.get("amount", 0.0)), 2))
                for row in rows_out
            }
            for r in extra_rows:
                key = (r.get("date"), round(float(r.get("amount", 0.0)), 2))
                if key not in existing:
                    rows_out.append(r)
                    existing.add(key)
    except Exception as e:
        logger.exception("Manual PDF fallback failed: %s", e)

    return rows_out


def _parse_date_text(value: object) -> Optional[date]:
    """Parse common date formats from text into a date object.

    Supports YYYY-MM-DD and DD/MM/YYYY (or DD/MM/YY → 20YY).
    Returns None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", s):
            y, m, d = s.split("-")
            return date(int(y), int(m), int(d))
        m2 = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s)
        if m2:
            a, b, c = m2.groups()
            yy = int(c)
            yy = 2000 + yy if yy < 100 else yy
            return date(yy, int(b), int(a))
    except Exception:
        return None
    return None


def _parse_pdf_prelevi_fallback(content: bytes, *, language: str) -> list[dict]:
    """Extract PRELIEVO rows from PDFs when generic parsers miss them."""

    try:
        import pdfplumber
    except Exception:  # pragma: no cover - optional dependency might be missing
        return []

    lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    lines.extend(text.split("\n"))
    except Exception:
        return []

    pattern = re.compile(
        r"^(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})\s+([0-9.,]+)\s+(.*)$"
    )
    results: list[dict] = []
    seen: set[tuple[date, float]] = set()
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        match = pattern.match(raw)
        if not match:
            i += 1
            continue
        desc_fragment = match.group(4).strip()
        if "PREL" not in desc_fragment.upper():
            i += 1
            continue
        txn_date = _parse_date_text(match.group(1))
        amount = _parse_amount_local(match.group(3))
        if txn_date is None or amount is None:
            i += 1
            continue
        parts = [desc_fragment]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if pattern.match(nxt):
                break
            if nxt:
                parts.append(nxt)
            j += 1
        description = " ".join(parts)
        key = (txn_date, round(abs(amount), 2))
        if key in seen:
            i = j
            continue
        results.append(
            {
                "date": txn_date,
                "amount": -abs(amount),
                "description": description,
                "beneficiary": None,
                "reference_ids": [],
            }
        )
        seen.add(key)
        i = j
    return results


def _finalise_bank_row_prepare(
    row: Dict[str, Any],
    filename: str,
    month: Optional[int],
    year: Optional[int],
    language: Optional[str] = None,
) -> Optional[dict]:
    """Convert parsed text row into a dict with date/amount/description.

    Filters by month/year when provided. Returns None when parsing fails.
    """
    d = _parse_date_text(row.get("date"))
    if not d:
        return None
    if month and d.month != month:
        return None
    if year and d.year != year and d.year != (year % 100):
        return None
    rest = str(row.get("rest", ""))
    m_amt = re.search(
        r"([-+]?[0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[-+]?[0-9]+(?:\.[0-9]+)?)\s*€?",
        rest,
    )
    if not m_amt:
        m_amt = re.search(
            r"([-+]?[0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[-+]?[0-9]+(?:\.[0-9]+)?)\s*(?:[\u20AC\u00A3$])?",
            rest,
        )
    amt = _parse_amount_local(m_amt.group(1)) if m_amt else None
    if amt is None:
        return None
    desc = rest[: m_amt.start()].strip() if m_amt else rest.strip()
    lines = row.get("description_lines", []) or []
    if lines:
        desc = (desc + " " + " ".join(x.strip() for x in lines if x)).strip()
    return {
        "date": d,
        "amount": float(amt),
        "description": desc,
        "beneficiary": None,
        "metadata": {"source": filename, "language": language},
    }


def parse_bank_text_prepare(
    text: str,
    filename: str,
    month: Optional[int],
    year: Optional[int],
    language: Optional[str] = None,
) -> List[dict]:
    """Heuristic parser for bank statement text (from OCR).

    Args:
        text: OCR-extracted text.
        filename: Source file name, used in metadata.
        month: Optional month filter.
        year: Optional year filter.
        language: Optional language hint for metadata only.

    Returns:
        Row dicts; does not construct ``Transaction`` objects.
    """
    rows: List[dict] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    current: Optional[Dict[str, Any]] = None
    for ln in lines:
        m = re.match(r"\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+", ln)
        if m:
            if current:
                t = _finalise_bank_row_prepare(current, filename, month, year, language)
                if t:
                    rows.append(t)
            current = {
                "date": m.group(1),
                "rest": ln[m.end() :].strip(),
                "description_lines": [],
            }
        elif current:
            current["description_lines"].append(ln.strip())
    if current:
        t = _finalise_bank_row_prepare(current, filename, month, year, language)
        if t:
            rows.append(t)
    return rows


def load_bank_rows(
    files: List[tuple[str, bytes]],
    *,
    month: Optional[int] = None,
    year: Optional[int] = None,
    language: str = "ita",
) -> List[dict]:
    """Load bank files and return row dicts (ready for ``Transaction`` construction).

    Args:
        files: Sequence of ``(filename, content_bytes)``.
        month: Optional month filter.
        year: Optional year filter.
        language: Language hint used for metadata.

    Behavior:
        - Spreadsheets: uses ``parse_spreadsheet_prepare`` for header/mapping inference.
        - PDFs: uses ``parse_pdf_prepare`` (generic/bank-agent) in deterministic mode.

    Returns:
        Rows with keys: ``date`` (date), ``amount`` (float), ``description`` (str),
        ``beneficiary`` (str|None), and ``metadata`` (dict with at least ``source``/``language``).
    """
    try:
        from modules.utilities.utils import get_schema_and_column_names  # type: ignore
    except Exception:  # pragma: no cover

        def get_schema_and_column_names(df):  # type: ignore
            return (getattr(df, "columns", []), getattr(df, "schema", {}))

    out: List[dict] = []

    for filename, content in files:
        name_lower = (filename or "").lower()
        if name_lower.endswith((".xlsx", ".xls", ".csv")):
            # Spreadsheet path
            try:
                df, mapping = parse_spreadsheet_prepare(
                    content, filename, max_header_scan_rows=50
                )
            except Exception:
                continue
            if df is None or df.height == 0:
                continue
            columns, _ = get_schema_and_column_names(df)
            columns = [str(c) for c in columns]
            resolved = _resolve_mapping(columns, mapping)
            _validate_required_columns(resolved)
            for row in df.iter_rows(named=True):
                # Date
                raw_date = row.get(resolved.get("date"))
                try:
                    s = str(raw_date)
                    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", s):
                        y, m, d = s.split("-")
                        d_obj = date(int(y), int(m), int(d))
                    elif re.search(r"\b\d{2}/\d{2}/\d{2,4}\b", s):
                        a, b, c = s.split("/")
                        yy = int(c)
                        yy = 2000 + yy if yy < 100 else yy
                        d_obj = date(yy, int(b), int(a))
                    else:
                        d_obj = None
                except Exception:
                    d_obj = None
                if not d_obj:
                    continue
                if month and d_obj.month != month:
                    continue
                if year and d_obj.year != year and d_obj.year != (year % 100):
                    continue

                # Amount
                amt = None
                if "amount" in resolved:
                    amt = _parse_amount_local(row.get(resolved["amount"]))
                if amt is None:
                    debit = (
                        _parse_amount_local(row.get(resolved.get("debit")))
                        if "debit" in resolved
                        else None
                    )
                    credit = (
                        _parse_amount_local(row.get(resolved.get("credit")))
                        if "credit" in resolved
                        else None
                    )
                    if debit is not None and credit is not None:
                        amt = credit - debit
                    elif credit is not None:
                        amt = credit
                    elif debit is not None:
                        amt = -debit
                if amt is None:
                    continue

                desc = str(row.get(resolved.get("description"), "") or "").strip()
                beneficiary = (
                    str(row.get(resolved.get("beneficiary"), "") or "").strip() or None
                )

                # Join small printable cells as details
                try:
                    row_texts = []
                    for v in row.values():
                        if v is None:
                            continue
                        s = str(v)
                        if s and len(s) < 2000:
                            row_texts.append(s)
                    combined_details = " ".join(row_texts)
                except Exception:
                    combined_details = ""

                out.append(
                    {
                        "date": d_obj,
                        "amount": float(amt),
                        "description": desc,
                        "beneficiary": beneficiary,
                        "metadata": {
                            "source": filename,
                            "details": combined_details,
                            "language": language,
                        },
                    }
                )

        elif name_lower.endswith(".pdf"):
            # PDF path: generic/bank-agent fast parse only
            try:
                rows = parse_pdf_prepare(
                    content,
                    filename,
                    language=language,
                    deterministic_only=True,
                )
            except Exception:
                rows = []
            for r in rows:
                d = r.get("date")
                if d and month and isinstance(d, date) and d.month != month:
                    continue
                if (
                    d
                    and year
                    and isinstance(d, date)
                    and d.year not in {year, year % 100}
                ):
                    continue
                out.append(
                    {
                        "date": d,
                        "amount": float(r.get("amount", 0.0)),
                        "description": str(r.get("description", "")),
                        "beneficiary": r.get("beneficiary"),
                        "metadata": {"source": filename, "language": language},
                    }
                )
        else:
            # Unknown type: ignore
            continue

    return out


# ----------------------
# Ledger-specific helpers
# ----------------------


def _default_ledger_headers() -> Dict[str, List[str]]:
    return {
        "date": [
            "data",
            "date",
            "data operazione",
            "data reg",
            "data registrazione",
            "fecha",
            "fecha operacion",
            "fecha registro",
            "datum",
            "daten",
            "valuta",
            "datavaluta",
            "valuedate",
            "data valuta",
        ],
        "description": [
            "descrizione",
            "descrizione causale",
            "descrizione agg",
            "causale",
            "descr",
            "desc",
            "descrizione aggiuntiva",
            "description",
            "description causale",
            "descripcion",
            "beschreibung",
            "descrizione deposito",
            "narrative",
            "riferimento",
            "reference",
        ],
        "debit": [
            "addebito",
            "uscite",
            "dare",
            "debit",
            "debe",
            "débit",
            "débito",
            "lastschrift",
            "prelievo",
        ],
        "credit": [
            "accredito",
            "entrate",
            "avere",
            "accrediti",
            "accreditation",
            "credit",
            "credito",
            "crédito",
            "haber",
            "gutschrift",
            "versamento",
            "deposito",
        ],
        "amount": [
            "importo",
            "amount",
            "importe",
            "betrag",
            "montant",
            "ammontare",
        ],
        "beneficiary": [
            "benef",
            "beneficiario",
            "beneficiary",
            "cliente",
            "fornitore",
            "cliente/fornitore",
            "beneficiario/cliente",
            "beneficiario/fornitore",
        ],
        "extra_desc": [
            "descr. agg",
            "descrizione agg",
            "descrizione aggiuntiva",
            "desc add",
            "desc. add",
            "note",
            "notes",
            "dettagli",
            "details",
        ],
        "account_desc": [
            "descrizione conto",
            "descr. conto",
            "account description",
            "account name",
            "nome conto",
        ],
        "counter_account_desc": [
            "descrizione contropartita",
            "conto contropartita",
            "descrizione sottoconto",
            "sottoconto",
            "descrizione cliente/fornitore",
            "cliente/fornitore",
        ],
        "journal_id": [
            "num. reg",
            "num reg",
            "n. reg",
            "numero registrazione",
            "n. registrazione",
            "registrazione",
            "id registrazione",
            "protocollo",
            "protocol",
            "prima nota",
            "pn",
        ],
    }


def _load_ledger_headers(path: Path | None = None) -> Dict[str, List[str]]:
    base = _default_ledger_headers()
    p = path or (
        Path(__file__).resolve().parent.parent
        / "config"
        / "lexicon"
        / "ledger_headers.json"
    )
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            for k, v in data.items():
                if isinstance(v, list):
                    base[k] = [str(x) for x in v]
    except Exception as exc:
        logger.warning("Failed to load ledger header lexicon: %s", exc)
    return base


def load_ledger_rows(
    files: List[tuple[str, bytes]],
    *,
    month: Optional[int] = None,
    year: Optional[int] = None,
    language: str = "ita",
    ignore_patterns_path: Path | None = None,
    account_column: str | None = None,
    account_desc_column: str | None = None,
    counter_account_desc_column: str | None = None,
    extra_desc_column: str | None = None,
) -> List[dict]:
    """Load ledger files and return row dicts (ready for ``Transaction`` construction).

    Args:
        files: Sequence of ``(filename, content_bytes)``.
        month: Optional month filter.
        year: Optional year filter.
        language: Language hint used for metadata.
        ignore_patterns_path: Optional path of regex patterns to ignore ledger rows.
        account_column: Optional column name for account identifier; if omitted a heuristic is used.
        account_desc_column: Optional human-readable account description column name.
        counter_account_desc_column: Optional counter-account description column name.

    Returns:
        Rows with keys: ``date`` (date), ``amount`` (float), ``description`` (str),
        ``beneficiary`` (str|None), and ``metadata`` (dict with at least ``source``/``language``).
    """
    try:
        from finance.ledger.ignore_patterns import load_ignore_patterns  # type: ignore
    except Exception:  # pragma: no cover

        def load_ignore_patterns(_path):  # type: ignore
            return []

    patterns = load_ignore_patterns(ignore_patterns_path)
    keywords = _load_ledger_headers()
    out: List[dict] = []

    for filename, content in files:
        name_lower = (filename or "").lower()
        if name_lower.endswith((".xlsx", ".xls", ".csv")):
            df, mapping = parse_spreadsheet_prepare_with_keywords(
                content, filename, keywords, max_header_scan_rows=50
            )
            if df is None or df.height == 0:
                continue
            columns = [str(c) for c in df.columns]
            resolved = _resolve_mapping(columns, mapping)
            if account_desc_column and account_desc_column in columns:
                resolved["account_desc"] = account_desc_column
            if counter_account_desc_column and counter_account_desc_column in columns:
                resolved["counter_account_desc"] = counter_account_desc_column
            if extra_desc_column and extra_desc_column in columns:
                resolved["extra_desc"] = extra_desc_column
            _validate_required_columns(resolved)
            if account_column and account_column in columns:
                account_col = account_column
            else:
                account_col = _resolve_account_col(df)
            for row in df.iter_rows(named=True):
                raw_date = row.get(resolved.get("date"))
                d = None
                try:
                    # Simple ISO/dd/mm parse, tolerate optional time suffix
                    s = str(raw_date)
                    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", s):
                        core = s[:10]
                        parts = core.split("-")
                        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    elif re.search(r"\b\d{2}/\d{2}/\d{2,4}\b", s):
                        a, b, c = s.split("/")
                        yy = int(c)
                        yy = 2000 + yy if yy < 100 else yy
                        d = date(yy, int(b), int(a))
                    else:
                        d = None
                except Exception:
                    d = None
                if not d:
                    continue
                if month and d.month != month:
                    continue
                if year and d.year != year and d.year != (year % 100):
                    continue
                amt = None
                if "amount" in resolved:
                    amt = _parse_amount_local(row.get(resolved["amount"]))
                if amt is None:
                    debit = (
                        _parse_amount_local(row.get(resolved.get("debit")))
                        if "debit" in resolved
                        else None
                    )
                    credit = (
                        _parse_amount_local(row.get(resolved.get("credit")))
                        if "credit" in resolved
                        else None
                    )
                    if debit is not None and credit is not None:
                        amt = credit - debit
                    elif credit is not None:
                        amt = credit
                    elif debit is not None:
                        amt = -debit
                if amt is None:
                    continue
                # Description & beneficiary
                desc = str(row.get(resolved.get("description"), "") or "").strip()
                extra_desc_val: str | None = None
                if "extra_desc" in resolved:
                    extra_raw = row.get(resolved["extra_desc"])
                    if extra_raw is not None:
                        text = str(extra_raw).strip()
                        if text:
                            extra_desc_val = text
                try:
                    if extra_desc_val is None and any(
                        p.search(desc.upper()) for p in patterns
                    ):
                        continue
                except Exception as e:
                    logger.exception(
                        "Failed to apply description filters for CSV row: %s", e
                    )
                beneficiary = (
                    str(row.get(resolved.get("beneficiary"), "") or "").strip() or None
                )
                # Metadata fields
                account = (
                    str(row.get(account_col)).strip()
                    if account_col and row.get(account_col) is not None
                    else None
                )
                account_desc = (
                    str(row.get(resolved["account_desc"])).strip()
                    if "account_desc" in resolved
                    and row.get(resolved["account_desc"]) is not None
                    else None
                )
                extra_desc = (
                    extra_desc_val
                    if "extra_desc" in resolved and extra_desc_val is not None
                    else None
                )
                counter_account_desc = (
                    str(row.get(resolved["counter_account_desc"])).strip()
                    if "counter_account_desc" in resolved
                    and row.get(resolved["counter_account_desc"]) is not None
                    else None
                )
                # Combined details text
                try:
                    row_texts = []
                    for v in row.values():
                        if v is None:
                            continue
                        s = str(v)
                        if s and len(s) < 2000:
                            row_texts.append(s)
                    combined_details = " ".join(row_texts)
                except Exception:
                    combined_details = ""
                meta: Dict[str, object] = {
                    "source": filename,
                    "details": combined_details,
                    "language": language,
                }
                jid = (
                    str(row.get(resolved.get("journal_id")))
                    if "journal_id" in resolved
                    and row.get(resolved.get("journal_id")) is not None
                    else None
                )
                if jid:
                    meta["journal_id"] = jid
                if account:
                    meta["account_id"] = account
                if account_desc:
                    meta["account_desc"] = account_desc
                if extra_desc:
                    meta["extra_desc"] = extra_desc
                if counter_account_desc:
                    meta["counter_account_desc"] = counter_account_desc
                out.append(
                    {
                        "date": d,
                        "amount": float(amt),
                        "description": desc,
                        "beneficiary": beneficiary,
                        "metadata": meta,
                    }
                )
        elif name_lower.endswith(".pdf"):
            # Try parser(s) that can extract tabular rows from ledger PDFs
            try:
                from modules.process_pdf_journal.logic import (  # type: ignore
                    normalize_ocr_language,
                    parse_journal,
                )
            except Exception:
                parse_journal = None  # type: ignore
            parsed_rows: List[dict] = []
            if parse_journal is not None:
                try:
                    df = parse_journal(
                        content,
                        lang=normalize_ocr_language(language),
                    )
                    if df.height > 0:
                        columns = [str(c) for c in df.columns]
                        headers = [str(col) for col in columns]
                        mapping = _infer_columns(headers, keywords)
                        if mapping.get("date") is None or mapping.get("amount") is None:
                            guessed = guess_columns_from_data(df)
                            for key, idx in guessed.items():
                                if mapping.get(key) is None:
                                    mapping[key] = idx
                        resolved = _resolve_mapping(columns, mapping)
                        for row in df.iter_rows(named=True):
                            raw_date = row.get(resolved.get("date"))
                            try:
                                s = str(raw_date)
                                if re.search(r"\b\d{4}-\d{2}-\d{2}\b", s):
                                    core = s[:10]
                                    parts = core.split("-")
                                    d = date(
                                        int(parts[0]), int(parts[1]), int(parts[2])
                                    )
                                elif re.search(r"\b\d{2}/\d{2}/\d{2,4}\b", s):
                                    a, b, c = s.split("/")
                                    yy = int(c)
                                    yy = 2000 + yy if yy < 100 else yy
                                    d = date(yy, int(b), int(a))
                                else:
                                    d = None
                            except Exception:
                                d = None
                            if not d:
                                continue
                            if month and d.month != month:
                                continue
                            if year and d.year != year and d.year != (year % 100):
                                continue
                            amt = None
                            if "amount" in resolved:
                                amt = _parse_amount_local(row.get(resolved["amount"]))
                            if amt is None:
                                debit = (
                                    _parse_amount_local(row.get(resolved.get("debit")))
                                    if "debit" in resolved
                                    else None
                                )
                                credit = (
                                    _parse_amount_local(row.get(resolved.get("credit")))
                                    if "credit" in resolved
                                    else None
                                )
                                if debit is not None and credit is not None:
                                    amt = credit - debit
                                elif credit is not None:
                                    amt = credit
                                elif debit is not None:
                                    amt = -debit
                            if amt is None:
                                continue
                            desc = str(
                                row.get(resolved.get("description"), "") or ""
                            ).strip()
                            beneficiary = (
                                str(
                                    row.get(resolved.get("beneficiary"), "") or ""
                                ).strip()
                                or None
                            )
                            meta = {"source": filename, "language": language}
                            out.append(
                                {
                                    "date": d,
                                    "amount": float(amt),
                                    "description": desc,
                                    "beneficiary": beneficiary,
                                    "metadata": meta,
                                }
                            )
                except Exception as e:
                    logger.exception("Failed to decode uploaded Excel row: %s", e)
            if not parsed_rows:
                # fallback: try generic/bank-agent PDF parse
                rows = parse_pdf_prepare(
                    content, filename, language=language, deterministic_only=True
                )
                for r in rows:
                    d = r.get("date")
                    if d and month and d.month != month:
                        continue
                    if d and year and d.year != year and d.year != (year % 100):
                        continue
                    out.append(
                        {
                            "date": d,
                            "amount": float(r.get("amount", 0.0)),
                            "description": str(r.get("description", "")),
                            "beneficiary": r.get("beneficiary"),
                            "metadata": {"source": filename, "language": language},
                        }
                    )
        else:
            # Unknown type: ignore
            continue

    return out


# local helper used by loaders only
def _parse_amount_local(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.endswith("-"):
        negative = True
        s = s[:-1]
    s = s.replace("€", "").replace("£", "")
    s = re.sub(r"[€$£\s\u00A0]", "", s)
    if "," in s and "." in s:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_dot > last_comma:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        m = re.search(r"[-+]?[0-9]+(?:[.,][0-9]+)?", s)
        if not m:
            return None
        try:
            val = float(m.group(0).replace(",", "."))
        except ValueError:
            return None
    return -val if negative else val
