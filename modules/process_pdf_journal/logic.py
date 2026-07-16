from __future__ import annotations

import io
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

import pdfplumber
import polars as pl
from pdfplumber.utils.exceptions import PdfminerException

from journal_ingest.config import get_recipe
from journal_ingest.core import ParserConfidenceError, ValidationError
from journal_ingest.router import Router
from journal_ingest.strategies import (
    JournalStrategyTableArea,
    JournalStrategyTextLayout,
    TablePDFParser,
    TextPDFParser,
)
from modules.pdf_utils.pdf_utils import _extract_pdf_text_with_ocr_once
from modules.utilities.utils import get_row_count, get_schema_and_column_names
from modules.utils.polars_excel_writer import write_polars_excel

from .pdf_text_fallback import (
    parse_pdf_group_lines,
    parse_pdf_posting_groups,
    parse_pdf_text_mode,
)

DEFAULT_STRATEGY_ORDER = ["tables", "text", "ocr"]


"""Generic journal PDF parser.

This module exposes :func:`parse_journal_any` which orchestrates a
format–agnostic parsing pipeline for "journal" style PDFs.  The pipeline
tries multiple strategies in order: table extraction, text heuristics and
finally OCR.  Each strategy must satisfy basic quality gates (minimum
number of rows and numeric sanity) before being accepted.  The thin
wrapper :func:`parse_journal` keeps backwards compatibility with previous
callers.

``parse_journal_any`` can optionally return a mapping object that
contains inferred column roles, locale information and the strategy used
for successful extraction.  Column names are normalised to ``snake_case``
but the original names are preserved in the mapping metadata.

Usage example::

    df, mapping = parse_journal_any(pdf_bytes, return_mapping=True)

The implementation deliberately avoids pandas and relies solely on
`polars`.
"""
# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ensure_bytes(data: Any) -> bytes:
    """Return *data* as bytes.

    Parameters
    ----------
    data:
        Either a path, raw bytes or a file like object.
    """

    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, (str, Path)):
        return Path(data).read_bytes()
    return data.read()


def _normalize_name(name: str | None, idx: int | None = None) -> str:
    """Return a snake_case column name for *name*.

    When *name* is ``None`` or empty, fall back to ``col`` or ``col_{idx}``.
    Non-string values are converted to strings before normalisation.
    """

    if not name:
        return f"col_{idx}" if idx is not None else "col"
    base = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower()
    return base if base else (f"col_{idx}" if idx is not None else "col")


def parse_number_token(token: str) -> float | None:
    """Parse *token* into a float trying common decimal conventions."""

    token = token.strip().replace("\u00a0", "")
    if not re.search(r"\d", token):
        return None
    # determine decimal separator from token itself
    if "," in token and "." in token:
        decimal = "," if token.rfind(",") > token.rfind(".") else "."
        thousands = "." if decimal == "," else ","
    elif "," in token:
        decimal = ","
        thousands = ""
    else:
        decimal = "."
        thousands = ""
    token = token.replace(thousands, "").replace(decimal, ".")
    try:
        return float(token)
    except ValueError:
        return None


_DATE_PATTERNS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
]


def parse_date_str(s: str) -> date | None:
    s = s.strip()
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _detect_locale(numeric_tokens: Sequence[str]) -> dict[str, Any]:
    """Infer decimal/thousand separators from observed tokens."""

    comma = dot = 0
    for tok in numeric_tokens:
        if "," in tok and "." in tok:
            if tok.rfind(",") > tok.rfind("."):
                comma += 1
            else:
                dot += 1
        elif "," in tok:
            if len(tok.split(",")[-1]) in {2, 3}:
                comma += 1
        elif "." in tok:
            if len(tok.split(".")[-1]) in {2, 3}:
                dot += 1
    decimal = "," if comma > dot else "."
    thousands = "." if decimal == "," else ","
    total = comma + dot
    conf = (max(comma, dot) / total) if total else 0.0
    return {
        "decimal": decimal,
        "thousands": thousands,
        "date_pattern": None,
        "confidence": round(conf, 2),
    }


def _tokenize_lines(text: str) -> List[List[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    counts: dict[str, int] = {}
    for ln in lines:
        counts[ln] = counts.get(ln, 0) + 1
    filtered = [ln for ln in lines if not (counts[ln] > 1 and len(ln) < 40)]
    return [ln.split() for ln in filtered]


CANONICAL_JOURNAL_COLUMNS = [
    "attivita",
    "filiale",
    "data_registrazione",
    "causale",
    "riga",
    "conto",
    "descrizione_conto",
    "descrizione_operazione",
    "dare",
    "avere",
]


def _has_journal_fields(df: pl.DataFrame, *, threshold: int = 3) -> bool:
    """Return ``True`` when at least ``threshold`` canonical columns exist.

    Parameters
    ----------
    df:
        DataFrame to inspect.
    threshold:
        Minimum number of canonical columns required to consider ``df``
        structured.  Defaults to 3.
    """

    columns, _ = get_schema_and_column_names(df)
    return sum(1 for col in CANONICAL_JOURNAL_COLUMNS if col in columns) >= threshold


# ---------------------------------------------------------------------------
# table parsing helpers
# ---------------------------------------------------------------------------

HEADER_KEYWORDS = [
    "attivita",
    "filiale",
    "data registrazione",
    "causale",
    "riga",
    "conto",
    "descrizione conto",
    "descrizione dell'operazione",
    "descrizione",
    "operazione",
    "note",
    "rif",
    "riferimento",
    "dare",
    "avere",
]

HEADER_MAP = {
    "attivita": "attivita",
    "filiale": "filiale",
    "data registrazione": "data_registrazione",
    "causale": "causale",
    "riga": "riga",
    "conto": "conto",
    "descrizione conto": "descrizione_conto",
    "descrizione dell'operazione": "descrizione_operazione",
    "dare": "dare",
    "avere": "avere",
}


def _clean_cell(cell: str | None) -> str:
    """Return *cell* normalised for comparisons."""

    return re.sub(r"\s+", " ", (cell or "")).strip()


def parse_amount(s: str) -> float | None:
    """Parse Italian formatted numbers like ``1.234,56``.

    Blanks or em dashes return ``None``.
    """

    txt = _clean_cell(s).replace("\u00a0", "")
    if txt in {"", "-", "—"}:
        return None
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def _header_hits(row: list[str]) -> set[str]:
    """Return header keywords found in *row* with partial token matches."""

    tokens: list[str] = []
    for cell in row:
        cleaned = _clean_cell(cell).lower()
        if not cleaned:
            continue
        tokens.extend(re.split(r"[^0-9a-zA-Z]+", cleaned))
    return {kw for kw in HEADER_KEYWORDS if any(kw in tok for tok in tokens if tok)}


def infer_header_rows(
    rows: list[list[str]], candidates: list[str]
) -> int | tuple[int, int]:
    """Return row index(es) most likely representing the header.

    Scans the first 12 rows and evaluates keyword hits for the row alone and in
    combination with the subsequent one or the one after that.  The combination
    yielding the highest score is returned.
    """

    limit = min(12, len(rows))
    best: int | tuple[int, int] = 0
    best_score = -1
    for i in range(limit):
        checks: list[tuple[int | tuple[int, int], int]] = []
        checks.append((i, len(_header_hits(rows[i]))))
        if i + 1 < limit:
            checks.append(((i, i + 1), len(_header_hits(rows[i] + rows[i + 1]))))
        if i + 2 < limit:
            checks.append(((i, i + 2), len(_header_hits(rows[i] + rows[i + 2]))))
        for idxs, score in checks:
            if score > best_score:
                best_score = score
                best = idxs
    return best


def infer_header_row(rows: list[list[str]], candidates: list[str]) -> int:
    """Backward compatible wrapper returning the first index."""

    res = infer_header_rows(rows, candidates)
    return res if isinstance(res, int) else min(res)


def _merge_header_rows(row1: list[str], row2: list[str]) -> list[str]:
    """Merge two header rows giving precedence to ``row2`` values."""

    header: list[str] = []
    for h1, h2 in zip(row1, row2):
        h1 = _clean_cell(h1)
        h2 = _clean_cell(h2)
        header.append(h2 if h2 else h1)
    if len(row1) > len(row2):
        for h1 in row1[len(row2) :]:
            header.append(_clean_cell(h1))
    elif len(row2) > len(row1):
        for h2 in row2[len(row1) :]:
            header.append(_clean_cell(h2))
    return header


def _is_footer_row(row: list[str]) -> bool:
    """Return ``True`` if *row* looks like a carry-forward/footer line."""

    cells = [_clean_cell(c) for c in row]
    first = next((c.upper() for c in cells if c), "")
    if first.startswith("RIPORTI") or first.startswith("TOTALE PAGINA"):
        return True
    if any("ULTIMA RIGA SCRITTURE CONTABILI" in c.upper() for c in cells):
        return True
    numeric_count = sum(parse_amount(c) is not None for c in cells)
    non_blank = [c for c in cells if c]
    if numeric_count == 2 and len(non_blank) == 2:
        return True
    return False


def _parse_date_it(s: str) -> date | None:
    try:
        return datetime.strptime(_clean_cell(s), "%d/%m/%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------


def _build_df_from_tables(
    pdf_bytes: bytes, header_row: int | tuple[int, int] | None
) -> tuple[pl.DataFrame, List[str]]:
    rows: list[dict[str, Any]] = []
    numeric_tokens: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            for table in page.extract_tables() or []:
                if not table:
                    continue
                if isinstance(header_row, tuple):
                    hdr_idx = min(header_row)
                    second_idx = max(header_row)
                    header = _merge_header_rows(table[hdr_idx], table[second_idx])
                    start = second_idx + 1
                else:
                    hdr_idx = (
                        header_row
                        if header_row is not None
                        else infer_header_rows(table, HEADER_KEYWORDS)
                    )
                    if isinstance(hdr_idx, tuple):
                        h1, h2 = hdr_idx
                        header = _merge_header_rows(table[h1], table[h2])
                        start = max(h1, h2) + 1
                    else:
                        header = table[hdr_idx]
                        start = hdr_idx + 1
                        if header_row is None:
                            nxt = start
                            while nxt < len(table) and _is_footer_row(table[nxt]):
                                nxt += 1
                            if nxt < len(table):
                                merged = _merge_header_rows(header, table[nxt])
                                if _header_hits(merged):
                                    header = merged
                                    start = nxt + 1
                names: list[str] = []
                for i, h in enumerate(header):
                    norm_h = _clean_cell(h)
                    norm = norm_h.lower()
                    mapped = None
                    for key, val in HEADER_MAP.items():
                        if key in norm:
                            mapped = val
                            break
                    names.append(mapped or _normalize_name(norm_h, i))
                for r_off, raw in enumerate(table[start:], start=start):
                    if _is_footer_row(raw):
                        continue
                    rec: dict[str, Any] = {
                        "page_index": p_idx,
                        "row_index": r_off,
                    }
                    for name, cell in zip(names, raw):
                        txt = _clean_cell(cell)
                        if name in {"dare", "avere"}:
                            num = parse_amount(txt)
                            rec[name] = num if num is not None else 0.0
                            if num is not None:
                                numeric_tokens.append(txt)
                        elif name == "data_registrazione":
                            rec[name] = _parse_date_it(txt)
                        elif name == "riga":
                            rec[name] = int(txt) if txt.isdigit() else txt
                        else:
                            rec[name] = txt
                    rows.append(rec)
    if len(rows) == 0 and header_row is None:
        return _build_df_from_tables(pdf_bytes, 0)
    df = pl.DataFrame(rows) if len(rows) > 0 else pl.DataFrame()
    expected = [
        "attivita",
        "filiale",
        "data_registrazione",
        "causale",
        "riga",
        "conto",
        "descrizione_conto",
        "descrizione_operazione",
        "dare",
        "avere",
    ]
    if df.height > 0:
        cols, _ = get_schema_and_column_names(df)
        for col in expected:
            if col not in cols:
                if col in {"dare", "avere"}:
                    df = df.with_columns(pl.lit(0.0).alias(col))
                else:
                    df = df.with_columns(pl.lit(None).alias(col))
        df = df.select(
            expected
            + [c for c in get_schema_and_column_names(df)[0] if c not in expected]
        )
    return df, numeric_tokens


def _build_df_from_text(
    pdf_bytes: bytes, use_ocr: bool
) -> tuple[pl.DataFrame, List[str]]:
    res = _extract_pdf_text_with_ocr_once(pdf_bytes, lang="eng")
    if use_ocr:
        if not res.text.strip():
            return pl.DataFrame(), []
    else:
        if res.method in {"ocr", "paddle_ocr", "llm_ocr"}:
            return pl.DataFrame(), []
    tokens = _tokenize_lines(res.text)
    rows: list[dict[str, Any]] = []
    numeric_tokens: List[str] = []
    header: List[str] | None = None
    if tokens and all(parse_number_token(t) is None for t in tokens[0]):
        header = [_normalize_name(t, i) for i, t in enumerate(tokens[0])]
        tokens = tokens[1:]
    for parts in tokens:
        if not parts:
            continue
        amt = None
        amt_tok = None
        for tok in reversed(parts):
            num = parse_number_token(tok)
            if num is not None:
                amt = num
                amt_tok = tok
                parts.remove(tok)
                break
        if amt is None:
            continue
        numeric_tokens.append(amt_tok or "")
        if not parts:
            continue
        d = parse_date_str(parts[0])
        desc_parts = parts[1:] if d else parts
        if header and len(header) >= 3:
            rec = {header[0]: d if d else parts[0]}
            if len(header) > 1:
                rec[header[1]] = " ".join(desc_parts)
            rec[header[-1]] = amt
        else:
            rec = {
                "description": " ".join(desc_parts),
                "amount": amt,
            }
            if d:
                rec["date"] = d
        rows.append(rec)
    df = pl.DataFrame(rows) if len(rows) > 0 else pl.DataFrame()
    return df, numeric_tokens


# ---------------------------------------------------------------------------
# column inference
# ---------------------------------------------------------------------------


def _infer_columns(df: pl.DataFrame, hints: dict[str, Sequence[str]]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    names, _ = get_schema_and_column_names(df)
    norm_names = {n: _normalize_name(n) for n in names}

    def _match_hint(role: str) -> None:
        options = hints.get(role, [])
        for name in names:
            if any(_normalize_name(opt) == norm_names[name] for opt in options):
                roles[role] = {"name": name, "confidence": 0.9}
                break

    for role in ["date", "amount", "debit", "credit", "line_id"]:
        _match_hint(role)

    if "date" not in roles:
        for name in names:
            col = df[name]
            if col.dtype == pl.Date:
                roles["date"] = {"name": name, "confidence": 1.0}
                break
            if col.dtype == pl.Utf8:
                parsed = col.map_elements(
                    lambda s: parse_date_str(s) if s else None,
                    return_dtype=pl.Date,
                )
                ratio = parsed.drop_nulls().len() / col.len() if col.len() else 0.0
                if ratio > 0.7:
                    roles["date"] = {"name": name, "confidence": round(ratio, 2)}
                    break

    numeric = [n for n in names if df[n].dtype in (pl.Float64, pl.Int64)]
    if numeric:
        amt = numeric[-1]
        rows = get_row_count(df)
        if "amount" not in roles:
            ratio = df[amt].is_not_null().mean() if rows > 0 else 0.0
            roles["amount"] = {"name": amt, "confidence": float(ratio)}
        if len(numeric) >= 2:
            roles.setdefault("debit", {"name": numeric[0], "confidence": 0.6})
            roles.setdefault("credit", {"name": numeric[1], "confidence": 0.6})

    for name in names:
        col = df[name]
        if col.dtype == pl.Int64 and col.is_sorted() and col.n_unique() == col.len():
            roles.setdefault("line_id", {"name": name, "confidence": 0.7})
            break
    return roles


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def _parse_journal_any_impl(
    data: Any,
    *,
    strategy_order: Sequence[str] | None = None,
    locale_hint: str | None = None,  # noqa: ARG001 - reserved for future use
    column_hints: dict[str, Sequence[str]] | None = None,
    min_rows: int = 5,
    return_mapping: bool = False,
    header_row: int | tuple[int, int] | None = None,
) -> pl.DataFrame | tuple[pl.DataFrame, dict[str, Any]]:
    """Parse a journal PDF using multiple strategies."""

    pdf_bytes = _ensure_bytes(data)
    strategies = list(strategy_order or DEFAULT_STRATEGY_ORDER)
    attempts: List[dict[str, Any]] = []
    mapping: dict[str, Any] = {
        "columns": {},
        "locale": {},
        "strategy_used": None,
        "attempts": attempts,
    }

    # ------------------------------------------------------------------
    # First attempt journal_ingest router for modern parsing
    # ------------------------------------------------------------------
    try:
        recipe = get_recipe("journal_generic_v1")
        parsers = [
            JournalStrategyTextLayout(recipe),
            TablePDFParser(),
            TextPDFParser(),
            JournalStrategyTableArea(),
        ]
        router = Router(parsers)
        parser_impl = router.route(pdf_bytes, meta={})
        try:
            rows = list(parser_impl.parse(pdf_bytes, meta={}))
        except Exception as e:  # pragma: no cover - parser failure
            logging.exception(e)
            attempts.append(
                {
                    "method": f"journal_ingest.{parser_impl.__class__.__name__}",
                    "success": False,
                    "error": str(e),
                }
            )
        else:
            df = pl.DataFrame(rows)
            try:
                structured = _has_journal_fields(df)
            except Exception as e:  # pragma: no cover - defensive
                logging.exception(e)
                attempts.append(
                    {
                        "method": f"journal_ingest.{parser_impl.__class__.__name__}",
                        "success": False,
                        "error": str(e),
                    }
                )
            else:
                ok = df.height >= min_rows and structured
                attempts.append(
                    {
                        "method": f"journal_ingest.{parser_impl.__class__.__name__}",
                        "success": ok,
                    }
                )
                if ok:
                    tokens = [
                        str(v)
                        for row in rows
                        for v in row.values()
                        if isinstance(v, (int, float, str))
                    ]
                    mapping["locale"] = _detect_locale(tokens)
                    mapping["columns"] = _infer_columns(df, column_hints or {})
                    mapping["strategy_used"] = (
                        f"journal_ingest.{parser_impl.__class__.__name__}"
                    )
                    try:
                        df.meta = mapping  # type: ignore[attr-defined]
                    except Exception as e:  # pragma: no cover - best effort
                        logging.exception(e)
                        pass
                    return (df, mapping) if return_mapping else df
    except (ParserConfidenceError, ValidationError) as e:
        attempts.append({"method": "journal_ingest", "success": False, "error": str(e)})
    except Exception as e:
        logging.exception(e)
        msg = str(e).lower()
        if "series" in msg and "ambiguous" in msg:
            attempts.append(
                {
                    "method": "journal_ingest",
                    "success": False,
                    "error": str(e),
                }
            )
        else:
            raise

    for strat in strategies:
        try:
            if strat == "tables":
                df, tokens = _build_df_from_tables(pdf_bytes, header_row)
            elif strat == "text":
                df, tokens = _build_df_from_text(pdf_bytes, use_ocr=False)
            elif strat == "ocr":
                df, tokens = _build_df_from_text(pdf_bytes, use_ocr=True)
            else:
                continue
        except Exception as e:
            logging.exception(e)
            msg = str(e).lower()
            if "series" in msg and "ambiguous" in msg:
                attempts.append({"method": strat, "success": False, "error": str(e)})
                continue
            raise
        try:
            structured = _has_journal_fields(df)
        except Exception as e:
            logging.exception(e)
            attempts.append({"method": strat, "success": False, "error": str(e)})
            continue
        ok = df.height >= min_rows and structured
        attempts.append({"method": strat, "success": ok})
        if not ok:
            continue
        locale = _detect_locale(tokens)
        mapping["locale"] = locale
        mapping["columns"] = _infer_columns(df, column_hints or {})
        mapping["strategy_used"] = strat
        try:
            df.meta = mapping  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - best effort
            logging.exception(e)
            pass
        return (df, mapping) if return_mapping else df

    # fall back: all strategies failed
    fb = pl.DataFrame()
    if pdf_bytes.startswith(b"%PDF"):
        fb = parse_pdf_text_mode(pdf_bytes)
    attempts.append({"method": "text_fallback", "success": fb.height > 0})
    if fb.height > 0:
        tokens = [
            str(v)
            for row in fb.iter_rows(named=True)
            for v in row.values()
            if isinstance(v, (int, float, str))
        ]
        mapping["locale"] = _detect_locale(tokens)
        mapping["columns"] = _infer_columns(fb, column_hints or {})
        mapping["strategy_used"] = "text_fallback"
        try:
            fb.meta = mapping  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - best effort
            logging.exception(e)
            pass
        return (fb, mapping) if return_mapping else fb
    # NEW grouping fallback
    gb = pl.DataFrame()
    if pdf_bytes.startswith(b"%PDF") and fb.height == 0:
        gb = parse_pdf_group_lines(pdf_bytes)
    attempts.append({"method": "group_lines_fallback", "success": gb.height > 0})
    if gb.height > 0:
        tokens = [
            str(v)
            for row in gb.iter_rows(named=True)
            for v in row.values()
            if isinstance(v, (int, float, str))
        ]
        mapping["locale"] = _detect_locale(tokens)
        mapping["columns"] = _infer_columns(gb, column_hints or {})
        mapping["strategy_used"] = "group_lines_fallback"
        try:
            gb.meta = mapping  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - best effort
            logging.exception(e)
            pass
        return (gb, mapping) if return_mapping else gb
    # Posting-group fallback (runs only if the previous fallbacks yielded no rows)
    pg = pl.DataFrame()
    if pdf_bytes.startswith(b"%PDF") and fb.height == 0 and gb.height == 0:
        pg = parse_pdf_posting_groups(pdf_bytes)
    attempts.append({"method": "posting_groups_fallback", "success": pg.height > 0})
    if pg.height > 0:
        tokens = [
            str(v)
            for row in pg.iter_rows(named=True)
            for v in row.values()
            if isinstance(v, (int, float, str))
        ]
        mapping["locale"] = _detect_locale(tokens)
        mapping["columns"] = _infer_columns(pg, column_hints or {})
        mapping["strategy_used"] = "posting_groups_fallback"
        try:
            pg.meta = mapping  # type: ignore[attr-defined]
        except Exception as e:  # pragma: no cover - best effort
            logging.exception(e)
            pass
        return (pg, mapping) if return_mapping else pg
    # If we reach here, return empty as before
    if return_mapping:
        return pl.DataFrame(), mapping
    return pl.DataFrame()


def parse_journal_any(
    *args: Any, return_mapping: bool = False, **kwargs: Any
) -> pl.DataFrame | tuple[pl.DataFrame, dict[str, Any]]:
    """Wrapper around :func:`_parse_journal_any_impl` with a catch-all and fallback."""
    pdf_bytes = _ensure_bytes(args[0] if args else kwargs.get("data"))
    try:
        result = _parse_journal_any_impl(*args, return_mapping=return_mapping, **kwargs)
    except PdfminerException:
        fb = parse_pdf_text_mode(pdf_bytes)
        gb = pl.DataFrame()
        pg = pl.DataFrame()
        attempts = [{"method": "text_fallback", "success": bool(fb.height)}]
        if fb.height == 0:
            gb = parse_pdf_group_lines(pdf_bytes)
            attempts.append(
                {"method": "group_lines_fallback", "success": bool(gb.height)}
            )
        else:
            attempts.append({"method": "group_lines_fallback", "success": False})
        if fb.height == 0 and gb.height == 0:
            pg = parse_pdf_posting_groups(pdf_bytes)
        attempts.append(
            {"method": "posting_groups_fallback", "success": bool(pg.height)}
        )
        mapping = {"attempts": attempts}
        df = fb if fb.height else gb if gb.height else pg
        if df.height:
            tokens = [
                str(v)
                for row in df.iter_rows(named=True)
                for v in row.values()
                if isinstance(v, (int, float, str))
            ]
            mapping["locale"] = _detect_locale(tokens)
            mapping["columns"] = _infer_columns(df, kwargs.get("column_hints") or {})
            mapping["strategy_used"] = (
                "text_fallback"
                if df is fb
                else "group_lines_fallback" if df is gb else "posting_groups_fallback"
            )
            try:
                df.meta = mapping  # type: ignore[attr-defined]
            except Exception as e:  # pragma: no cover - best effort
                logging.exception(e)
                pass
        return (df, mapping) if return_mapping else df
    except Exception as e:  # pragma: no cover - broad catch intentional
        logging.exception(e)
        msg = str(e).lower()
        if "series" in msg and "ambiguous" in msg:
            mapping = {
                "attempts": [{"method": "catch_all", "success": False, "error": str(e)}]
            }
            empty = pl.DataFrame()
            return (empty, mapping) if return_mapping else empty
        raise

    if return_mapping:
        df, mapping = result
        if df.height == 0:
            fb = parse_pdf_text_mode(pdf_bytes)
            attempts = mapping.setdefault("attempts", [])
            attempts.append({"method": "text_fallback", "success": bool(fb.height)})
            if fb.height:
                mapping["strategy_used"] = "text_fallback"
                return fb, mapping
            gb = parse_pdf_group_lines(pdf_bytes)
            attempts.append(
                {"method": "group_lines_fallback", "success": bool(gb.height)}
            )
            if gb.height:
                mapping["strategy_used"] = "group_lines_fallback"
                return gb, mapping
            pg = parse_pdf_posting_groups(pdf_bytes)
            attempts.append(
                {"method": "posting_groups_fallback", "success": bool(pg.height)}
            )
            if pg.height:
                mapping["strategy_used"] = "posting_groups_fallback"
                return pg, mapping
            return pg, mapping
        return result

    df = result
    if df.height == 0:
        fb = parse_pdf_text_mode(pdf_bytes)
        if fb.height == 0:
            gb = parse_pdf_group_lines(pdf_bytes)
            if gb.height == 0:
                return parse_pdf_posting_groups(pdf_bytes)
            return gb
        return fb
    return df


# ---------------------------------------------------------------------------
# legacy wrapper
# ---------------------------------------------------------------------------


def parse_journal(
    pdf_binary: bytes, header_row: int | tuple[int, int] | None = None
) -> pl.DataFrame:
    """Backward compatible wrapper for :func:`parse_journal_any`.

    Parameters
    ----------
    pdf_binary:
        The PDF contents.
    header_row:
        Optional override for the header row index in table parsing. Provide a
        tuple ``(r1, r2)`` to merge two header rows with ``r2`` taking precedence.
    """

    result = parse_journal_any(pdf_binary, return_mapping=False, header_row=header_row)
    assert isinstance(result, pl.DataFrame)
    return result


def to_excel_bytes(df: pl.DataFrame) -> bytes:
    """Return the DataFrame as an Excel workbook in memory."""
    with io.BytesIO() as buffer:
        write_polars_excel({"journal": df}, buffer)
        return buffer.getvalue()
