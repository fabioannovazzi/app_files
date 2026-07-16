from __future__ import annotations

"""Final pass filter for unmatched bank statement rows.

This module provides :func:`clean_bank_not_matched` which removes rows that are
almost certainly not transactions from a Polars ``DataFrame``.  It applies a
set of conservative heuristics and returns both the cleaned frame and a
:class:`FilterReport` detailing the actions taken.  Two notable rules are:

* **Numeric table drop** – lines containing multiple amounts and no letters or
  a balance-like shape are discarded as summary tables.
* **Balance summary drop** – rows originating from balance summary sections or
  mentioning ``EXTRAFIDO`` are removed unless they contain whitelisted
  transaction keywords.

Example
-------
>>> import polars as pl
>>> from src.final_pass_filter import clean_bank_not_matched
>>> data = [
...     {"description": "29/06/24 COMPETENZE", "amount": -105.0, "accounting_date": "2024-06-29"},
...     {"description": "RIASSUNTO SCALARE DEL CONTO CORRENTE N. 503", "amount": None},
...     {"description": "10/06/24 F24 TELEMATICO DELEGA", "amount": -447.82, "accounting_date": "2024-06-10"},
...     {"description": "NUOVI ORARI FILIALE", "amount": None},
...     {"description": "BON.DA EXAMPLE SUPPLIER S.R.L.", "amount": 31160.72, "accounting_date": "2024-06-01"},
...     {"description": "COORDINATE BANCARIE INTERNAZIONALI IBAN", "amount": None},
... ]
>>> df = pl.DataFrame(data)
>>> cleaned, report = clean_bank_not_matched(df)
>>> cleaned.height
3
>>> report.dropped_rows
3
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import polars as pl

from finance.bank_statements.ignore_patterns import DROP_PATTERNS
from modules.utilities.utils import (
    ensure_polars_df,
    get_row_count,
    get_schema_and_column_names,
)

# -- Public API -----------------------------------------------------------------

__all__ = [
    "FilterReport",
    "FinalPassConfig",
    "clean_bank_not_matched",
    "is_it_amount",
    "count_amounts",
    "has_letters",
    "CURRENCY_RE",
    "DATE_RE",
    "LETTER_RE",
    "digit_ratio",
]


@dataclass(frozen=True)
class FilterReport:
    """Summary of the filtering process."""

    input_rows: int
    kept_rows: int
    dropped_rows: int
    counts_by_rule: Dict[str, int]
    examples_by_rule: Dict[str, List[str]]
    notes: List[str]


@dataclass(frozen=True)
class FinalPassConfig:
    """Options controlling the behaviour of :func:`clean_bank_not_matched`."""

    numeric_table_drop_enabled: bool = True


CURRENCY_RE = re.compile(r"\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*-?")
"""Pattern matching Italian currency amounts such as ``1.234,56-``."""

DATE_RE = re.compile(r"\b\d{2}/\d{2}/(?:\d{2}|\d{4})\b")
"""Simple date pattern ``DD/MM/YY`` or ``DD/MM/YYYY``."""

LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
"""Alphabetic characters including basic Latin and extended ranges."""

_AMOUNT_FULL_RE = re.compile(rf"^{CURRENCY_RE.pattern}$")
_NUMERIC_BALANCE_SHAPE_RE = re.compile(
    r"^\d{2}/\d{2}/\d{4}\s+\d[\d.\s]*,\d{2}\s*-?\s+\d+\s+\d[\d.\s]*,\d{2}\s*-?$"
)
_EXTRAFIDO_SAFELIST = {
    "BON.",
    "BONIFICO",
    "VS.DISP.",
    "RIF.",
    "COMM.",
    "ANT.",
    "GIROCONTO",
    "SPESE",
    "PERC.",
    "STORNO",
    "F24",
}
_EXTRAFIDO_SAFELIST_RE = re.compile("|".join(re.escape(w) for w in _EXTRAFIDO_SAFELIST))

_NUMERIC_TABLE_SAFELIST = {
    "BON.",
    "BONIFICO",
    "VS.DISP.",
    "RIF.",
    "COMM.",
    "GIROCONTO",
    "F24",
    "STORNO",
}
_NUMERIC_TABLE_SAFELIST_RE = re.compile(
    "|".join(re.escape(w) for w in _NUMERIC_TABLE_SAFELIST)
)


def is_it_amount(s: str) -> bool:
    """Return ``True`` if ``s`` matches an Italian-formatted amount."""

    return bool(_AMOUNT_FULL_RE.match(s.strip()))


def count_amounts(text: str) -> int:
    """Count monetary amounts present in ``text``."""

    return len(CURRENCY_RE.findall(text))


def has_letters(text: str) -> bool:
    """Return ``True`` if ``text`` contains alphabetic characters."""

    return bool(LETTER_RE.search(text))


def digit_ratio(text: str) -> float:
    """Return the ratio of digits to the total of digits and letters."""

    if not text:
        return 0.0
    digits = sum(ch.isdigit() for ch in text)
    letters = len(LETTER_RE.findall(text))
    total = digits + letters
    return digits / total if total else 0.0


def _parse_amount(token: str) -> Optional[float]:
    token = token.strip()
    negative = token.endswith("-")
    token = (
        token.rstrip("-").strip().replace(".", "").replace(" ", "").replace(",", ".")
    )
    try:
        value = float(token)
    except ValueError:
        return None
    return -value if negative else value


def _is_numeric_table_line(desc: str) -> bool:
    if not desc:
        return False
    d = desc.casefold()
    if _NUMERIC_BALANCE_SHAPE_RE.match(d):
        return True
    if count_amounts(d) >= 2 and digit_ratio(d) >= 0.85:
        return True
    if digit_ratio(d) >= 0.85:
        amounts = [_parse_amount(a) for a in CURRENCY_RE.findall(d)]
        if len(amounts) >= 2 and None not in amounts[:2]:
            if abs(abs(amounts[0]) - abs(amounts[1])) <= 0.01:
                return True
    return False


def _normalize_text(s: str) -> str:
    """Return NFKC normalised, upper-case text with collapsed whitespace."""

    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())
    return s.upper()


def _compile_patterns(patterns: Iterable[str]) -> List[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


KEEP_PATTERNS: Dict[str, List[re.Pattern[str]]] = {
    "keep_bonifici": _compile_patterns(
        [
            r"\bBON\.?",
            r"\bBONIFICO",
            r"\bGIROCONTO",
            r"\bVOSTRA\s+DISPOSIZIONE",
            r"\bVS\.?.?DISP\.?.?",
            r"\bRIF\.?.?MB\w+",
        ]
    ),
    "keep_charges_taxes": _compile_patterns(
        [
            r"\bCOMPETENZE\b",
            r"\bIMP\.\s?BOLLO\b",
            r"\bF24\b",
            r"\bCOMMISSIONE\b",
            r"\bCOMM\.\s?PIGN\.\?",
        ]
    ),
    "keep_adjustments": _compile_patterns(
        [
            r"\bSTORNO\s+SCRITTURE\b",
            r"\bSCARICO\s+ANT\.\b",
            r"\bSC\.\s?PARZ\.\s?ANT\.\b",
            r"\bESTINZIONE\s+CONTO\s+ANTICIPI\b",
        ]
    ),
    "keep_counterparty": _compile_patterns(
        [
            r"\bFAVORE\b",
            r"\bMB(VT|0B)\d{6,}\b",
        ]
    ),
}


def _mask_contains_any(text_col: str, patterns: List[re.Pattern[str]]) -> pl.Expr:
    expr = pl.lit(False)
    for pat in patterns:
        expr = expr | pl.col(text_col).str.contains(pat.pattern)
    return expr


def clean_bank_not_matched(
    df: pl.DataFrame,
    *,
    desc_col: str = "description",
    amount_col: str | None = "amount",
    date_col: str | None = "accounting_date",
    value_date_col: str | None = "value_date",
    debit_col: str | None = None,
    credit_col: str | None = None,
    page_col: str | None = None,
    max_example_per_rule: int = 5,
    collect_stats: bool = False,
    return_dropped_rows: bool = False,
    debug: bool = False,
    config: FinalPassConfig | None = None,
) -> (
    pl.DataFrame
    | Tuple[pl.DataFrame, FilterReport]
    | Tuple[pl.DataFrame, pl.DataFrame, FilterReport]
):
    """Filter non-transaction rows from ``df``.

    Parameters
    ----------
    df:
        Frame containing statement rows marked as ``bank_not_matched``.
    return_dropped_rows:
        If ``True``, the rows filtered out by any rule are returned alongside
        the cleaned frame.
    debug:
        When ``True``, include a ``__final_pass_reason__`` column in the dropped
        frame indicating the rule that triggered.

    Returns
    -------
    pl.DataFrame | tuple[pl.DataFrame, FilterReport] | tuple[pl.DataFrame, pl.DataFrame, FilterReport]
        Cleaned frame.  If ``collect_stats`` or ``return_dropped_rows`` is
        ``True`` a tuple is returned.  When ``return_dropped_rows`` is ``True``
        the tuple contains ``(cleaned_df, dropped_df, FilterReport)``.  When only
        ``collect_stats`` is ``True`` the tuple is ``(cleaned_df, FilterReport)``.
    """

    df = ensure_polars_df(df)
    config = config or FinalPassConfig()
    collect_stats = collect_stats or return_dropped_rows
    columns, schema = get_schema_and_column_names(df)
    if amount_col is None and (debit_col is None or credit_col is None):
        raise ValueError("Provide either amount_col or both debit_col and credit_col")
    if desc_col not in columns:
        raise ValueError(f"Missing description column: {desc_col}")

    # Normalised text
    df = df.with_columns(
        pl.col(desc_col)
        .fill_null("")
        .map_elements(_normalize_text, return_dtype=pl.String)
        .alias("__norm_desc")
    )

    # Amount handling
    if amount_col is not None and amount_col in columns:
        df = df.with_columns(
            [
                pl.col(amount_col).alias("__effective_amount"),
                pl.col(amount_col).is_not_null().alias("__has_amount"),
                pl.lit(False).alias("__has_one_side"),
            ]
        )
    else:
        df = df.with_columns(
            [
                (
                    pl.col(credit_col).fill_null(0) - pl.col(debit_col).fill_null(0)
                ).alias("__effective_amount"),
                (
                    pl.col(credit_col).is_not_null() | pl.col(debit_col).is_not_null()
                ).alias("__has_amount"),
                (
                    pl.col(credit_col).is_not_null() ^ pl.col(debit_col).is_not_null()
                ).alias("__has_one_side"),
            ]
        )

    # Date handling
    if date_col is not None and date_col in columns:
        dtype = schema.get(date_col) if schema else None
        if dtype == pl.Utf8:
            date_expr = pl.col(date_col).str.strptime(
                pl.Date, strict=False, format=None
            )
        else:
            date_expr = pl.col(date_col).cast(pl.Date, strict=False)
        df = df.with_columns(
            [
                date_expr.alias("__parsed_date"),
                date_expr.is_not_null().alias("__has_date"),
            ]
        )
    else:
        df = df.with_columns(
            [
                pl.lit(None, dtype=pl.Date).alias("__parsed_date"),
                pl.lit(False).alias("__has_date"),
            ]
        )

    if value_date_col is not None and value_date_col in columns:
        v_dtype = schema.get(value_date_col) if schema else None
        if v_dtype == pl.Utf8:
            v_date_expr = pl.col(value_date_col).str.strptime(
                pl.Date, strict=False, format=None
            )
        else:
            v_date_expr = pl.col(value_date_col).cast(pl.Date, strict=False)
        df = df.with_columns([v_date_expr.alias("__value_date")])
    else:
        df = df.with_columns([pl.lit(None, dtype=pl.Date).alias("__value_date")])

    # Row numbering for page-aware rules
    df = df.with_row_count("__row_nr")

    # Rule masks
    keep_masks: Dict[str, pl.Series] = {}
    drop_masks: Dict[str, pl.Series] = {}

    for name, patterns in KEEP_PATTERNS.items():
        mask = df.select(_mask_contains_any("__norm_desc", patterns)).to_series()
        keep_masks[name] = mask

    any_keep = pl.Series([False] * get_row_count(df))
    for mask in keep_masks.values():
        any_keep = any_keep | mask

    for name, patterns in DROP_PATTERNS.items():
        mask = df.select(_mask_contains_any("__norm_desc", patterns)).to_series()
        drop_masks[name] = mask

    # Non movement numeric table rule
    digit_ratio_mask = (
        df["__norm_desc"].map_elements(digit_ratio, return_dtype=pl.Float64) >= 0.85
    )
    numeric_table_mask = (
        (df["__norm_desc"].str.count_matches(CURRENCY_RE.pattern) >= 3)
        & df["__norm_desc"].str.contains(r"NUMERI|TASSI|GIORNI|FIDI")
        & digit_ratio_mask
    )
    drop_masks["drop_numeric_table"] = numeric_table_mask

    # Numeric-only balance lines from Riassunto scalare tables
    if config.numeric_table_drop_enabled:
        pure_numeric_balance_mask = df[desc_col].map_elements(
            _is_numeric_table_line,
            return_dtype=pl.Boolean,
            skip_nulls=False,
        )
        safelist_mask = df["__norm_desc"].str.contains(
            _NUMERIC_TABLE_SAFELIST_RE.pattern
        )
        drop_masks["drop_pure_numeric_balance"] = pure_numeric_balance_mask & (
            ~safelist_mask
        )

    # Dettaglio saldi / EXTRAFIDO lines
    transaction_token_mask = df["__norm_desc"].str.contains(
        _EXTRAFIDO_SAFELIST_RE.pattern
    )
    counterparty_mask = keep_masks.get(
        "keep_counterparty", pl.Series([False] * get_row_count(df))
    )
    extrafido_word_mask = df["__norm_desc"].str.contains("EXTRAFIDO")
    date_amount_no_token_mask = (
        df["__norm_desc"].str.contains(DATE_RE.pattern)
        & df["__norm_desc"].str.contains(CURRENCY_RE.pattern)
        & (~transaction_token_mask)
        & (~counterparty_mask)
    )
    if page_col is not None and page_col in columns:
        header_positions = (
            df.filter(pl.col("__norm_desc") == "DETTAGLIO SALDI")
            .group_by(page_col)
            .agg(pl.min("__row_nr").alias("__header_row"))
        )
        df = df.join(header_positions, on=page_col, how="left")
        preceded_header_mask = df["__header_row"].is_not_null() & (
            df["__row_nr"] > df["__header_row"]
        )
    else:
        df = df.with_columns(pl.lit(None).alias("__header_row"))
        preceded_header_mask = pl.Series([False] * get_row_count(df))
    extrafido_mask = (
        extrafido_word_mask | date_amount_no_token_mask | preceded_header_mask
    ) & (~transaction_token_mask)
    existing_balance_mask = drop_masks.get(
        "drop_balance_summary", pl.Series([False] * get_row_count(df))
    )
    drop_masks["drop_balance_summary"] = existing_balance_mask | extrafido_mask

    # Missing shape rule
    desc_len = df["__norm_desc"].str.len_bytes()
    digit_ratio_series = df["__norm_desc"].str.count_matches(r"\d").cast(
        pl.Float64
    ) / desc_len.cast(pl.Float64)
    missing_shape_mask = (
        (~df["__has_date"])
        & (~df["__has_amount"])
        & (desc_len > 30)
        & (digit_ratio_series < 0.05)
    )
    drop_masks["drop_missing_shape"] = missing_shape_mask

    # Combine drop masks excluding keep matches
    drop_mask = pl.Series([False] * get_row_count(df))
    for mask in drop_masks.values():
        drop_mask = drop_mask | mask
    drop_mask = drop_mask & (~any_keep)

    if collect_stats:
        counts_by_rule: Dict[str, int] = {}
        examples_by_rule: Dict[str, List[str]] = {}

        for name, mask in keep_masks.items():
            count = int(mask.sum())
            if count:
                counts_by_rule[name] = count
                examples = (
                    df.filter(mask)[desc_col].head(max_example_per_rule).to_list()
                )
                examples_by_rule[name] = examples

        for name, mask in drop_masks.items():
            effective_mask = mask & (~any_keep)
            count = int(effective_mask.sum())
            if count:
                counts_by_rule[name] = count
                examples = (
                    df.filter(effective_mask)[desc_col]
                    .head(max_example_per_rule)
                    .to_list()
                )
                examples_by_rule[name] = examples

    drop_cols = [
        "__norm_desc",
        "__effective_amount",
        "__has_amount",
        "__has_one_side",
        "__parsed_date",
        "__has_date",
        "__value_date",
        "__row_nr",
        "__header_row",
    ]
    cleaned_df = df.filter(~drop_mask).drop(drop_cols)

    dropped_df: Optional[pl.DataFrame] = None
    if return_dropped_rows:
        dropped_df = df.filter(drop_mask).drop(drop_cols)
        if debug:
            reason_series = pl.Series([None] * get_row_count(df), dtype=pl.Utf8)
            for name, mask in drop_masks.items():
                effective_mask = mask & (~any_keep)
                reason_series = reason_series.where(~effective_mask, name)
            dropped_df = dropped_df.with_columns(
                reason_series.filter(drop_mask).alias("__final_pass_reason__")
            )

    if not collect_stats:
        if return_dropped_rows:
            return cleaned_df, dropped_df  # type: ignore[return-value]
        return cleaned_df

    input_rows = get_row_count(df)
    kept_rows = get_row_count(cleaned_df)
    dropped_rows = input_rows - kept_rows

    notes: List[str] = []
    if dropped_rows == 0:
        notes.append("No rows were dropped")
    if input_rows > 0 and dropped_rows / input_rows > 0.8:
        notes.append("Dropped more than 80% of rows")

    report = FilterReport(
        input_rows=input_rows,
        kept_rows=kept_rows,
        dropped_rows=dropped_rows,
        counts_by_rule=counts_by_rule,
        examples_by_rule=examples_by_rule,
        notes=notes,
    )

    if return_dropped_rows:
        return cleaned_df, dropped_df, report  # type: ignore[return-value]
    return cleaned_df, report
