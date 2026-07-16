from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping

import polars as pl

from journal_ingest.core import BaseJournalParser
from journal_ingest.core.utils.numbers import infer_number
from journal_ingest.core.validators import validate_double_entry
from modules.utilities.utils import get_schema_and_column_names

ACCOUNT_RE = re.compile(r"\d+(?:\s*[\/\-.]\s*\d+){1,3}")
AMOUNT_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})")


def _is_filled(val: object) -> bool:
    """Return ``True`` for non-empty strings or non-null ``pl.Series``."""

    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, pl.Series):
        return val.drop_nulls().len() > 0
    return False


def _is_line_col(col: pl.Series) -> bool:
    try:
        ints = col.cast(pl.Int64, strict=False).drop_nulls().to_list()
    except Exception as e:
        logging.exception(e)
        return False
    if len(ints) < 2:
        return False
    if ints[0] not in (0, 1):
        return False
    return all(b - a == 1 for a, b in zip(ints, ints[1:]))


def _account_ratio(col: pl.Series) -> float:
    s = col.cast(pl.Utf8, strict=False).drop_nulls()
    if not s.len():
        return 0.0
    matches = sum(bool(ACCOUNT_RE.fullmatch(str(v).strip())) for v in s)
    return matches / s.len()


def _is_amount_col(col: pl.Series) -> bool:
    if col.dtype in pl.NUMERIC_DTYPES:
        return col.drop_nulls().len() > 0
    s = col.cast(pl.Utf8, strict=False).drop_nulls()
    if not s.len():
        return False
    matches = sum(bool(AMOUNT_RE.fullmatch(str(v).strip())) for v in s)
    return matches > 0


def detect_table_columns(df: pl.DataFrame) -> dict[str, str | None]:
    cols = get_schema_and_column_names(df)[0]
    line_col: str | None = None
    for name in cols:
        if _is_line_col(df[name]):
            line_col = name
            break
    account_col: str | None = None
    for name in cols:
        if name == line_col:
            continue
        if _account_ratio(df[name]) > 0.6:
            account_col = name
            break
    amount_candidates: list[str] = []
    for name in reversed(cols):
        if name in {line_col, account_col}:
            continue
        if _is_amount_col(df[name]):
            amount_candidates.append(name)
        if len(amount_candidates) == 2:
            break
    amount_candidates.reverse()
    debit_col = amount_candidates[0] if amount_candidates else None
    credit_col = amount_candidates[1] if len(amount_candidates) > 1 else None
    text_cols = [
        c for c in cols if c not in {line_col, account_col, debit_col, credit_col}
    ]
    account_desc_col = text_cols[0] if text_cols else None
    memo_col = text_cols[1] if len(text_cols) > 1 else None
    return {
        "line_no": line_col,
        "account_code": account_col,
        "debit": debit_col,
        "credit": credit_col,
        "account_desc": account_desc_col,
        "memo": memo_col,
    }


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return infer_number(text, [".", ","], [",", ".", ""])
    except ValueError:
        return None


def parse_table_dataframe(df: pl.DataFrame) -> list[dict[str, Any]]:
    mapping = detect_table_columns(df)
    rows: list[dict[str, Any]] = []
    for rec in df.iter_rows(named=True):
        line_no = rec.get(mapping["line_no"]) if mapping["line_no"] else None
        line_no = int(line_no) if line_no is not None else None
        account_code = (
            str(rec.get(mapping["account_code"])) if mapping["account_code"] else None
        )
        account_desc = (
            str(rec.get(mapping["account_desc"])) if mapping["account_desc"] else ""
        )
        memo = str(rec.get(mapping["memo"])) if mapping["memo"] else ""
        debit = _parse_number(rec.get(mapping["debit"])) if mapping["debit"] else None
        credit = (
            _parse_number(rec.get(mapping["credit"])) if mapping["credit"] else None
        )
        rows.append(
            {
                "entry_date": None,
                "line_no": line_no,
                "account_code": account_code,
                "account_desc": account_desc,
                "memo": memo,
                "debit": debit,
                "credit": credit,
            }
        )
    validate_double_entry(rows)
    return rows


class JournalStrategyTableArea(BaseJournalParser):
    """Parse journal tables from pre-extracted table frames."""

    def _get_frame(self, meta: Mapping[str, Any] | None) -> pl.DataFrame | None:
        if not meta:
            return None
        candidate = None
        for key in ("df", "dataframe", "table", "frame"):
            val = meta.get(key)
            if isinstance(val, pl.DataFrame):
                candidate = val
                break
        return candidate

    def probe(self, file_bytes: bytes, meta: Mapping[str, Any] | None = None) -> float:
        df = self._get_frame(meta)
        if df is None:
            return 0.0
        mapping = detect_table_columns(df)
        if _is_filled(mapping.get("account_code")) and _is_filled(mapping.get("debit")):
            return 0.8
        return 0.4

    def parse(
        self, file_bytes: bytes, meta: Mapping[str, Any] | None = None
    ) -> Iterable[dict[str, Any]]:
        df = self._get_frame(meta)
        if df is None:
            return []
        return parse_table_dataframe(df)
