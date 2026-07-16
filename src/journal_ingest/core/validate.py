from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import polars as pl


def normalize_number(
    token: str, number_format: Mapping[str, Any] | None = None
) -> float:
    """Return a float from ``token`` using ``number_format`` hints.

    When ``number_format['infer']`` is true or not provided, the decimal
    separator is inferred per token by looking at the last occurrence of
    ``.`` or ``,``. Thousands separators are removed accordingly.
    """

    number_format = number_format or {}
    token = token.strip().replace("\u00a0", "")
    decimal_candidates = number_format.get("decimal_candidates") or [".", ","]
    thousands_candidates = number_format.get("thousands_candidates") or [",", "."]

    decimal = decimal_candidates[0]
    thousands = thousands_candidates[0] if thousands_candidates else ""

    if number_format.get("infer", True):
        if "," in token and "." in token:
            decimal = "," if token.rfind(",") > token.rfind(".") else "."
            thousands = "." if decimal == "," else ","
        elif "," in token:
            decimal = ","
            thousands = "." if "." in token else ""
        elif "." in token:
            decimal = "."
            thousands = "," if "," in token else ""
    cleaned = token.replace(thousands, "").replace(decimal, ".")
    return float(cleaned)


def validate_entry_balances(rows: Iterable[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    """Check that debit and credit totals balance per journal entry.

    Returns a list of issues where each item contains the grouping key and the
    debit/credit sums. An empty list indicates all entries balance.
    """

    df = pl.DataFrame(list(rows))
    if df.height == 0:
        return []
    agg = (
        df.fill_null(0.0)
        .group_by(["entry_date", "entry_label", "unit", "location"])
        .agg(
            [
                pl.col("debit").sum().alias("debit_sum"),
                pl.col("credit").sum().alias("credit_sum"),
            ]
        )
    )
    issues: list[tuple[Any, ...]] = []
    for row in agg.iter_rows(named=True):
        if abs(row["debit_sum"] - row["credit_sum"]) > 0.01:
            issues.append(
                (
                    row["entry_date"],
                    row["entry_label"],
                    row["unit"],
                    row["location"],
                    row["debit_sum"],
                    row["credit_sum"],
                )
            )
    return issues


def validate_page_totals(
    rows: Sequence[Mapping[str, Any]],
    page_total_hints: Sequence[Mapping[str, Any]],
    epsilon: float = 0.01,
) -> list[tuple[Any, ...]]:
    """Validate detected page totals against per-page sums.

    ``page_total_hints`` should contain mappings with ``src_page``, ``debit``
    and ``credit`` values representing candidate totals found in the source
    document. The function compares these values with sums computed from
    ``rows`` and returns mismatches.
    """

    if len(rows) == 0 or len(page_total_hints) == 0:
        return []
    df = pl.DataFrame(list(rows)).fill_null(0.0)
    sums = (
        df.group_by("src_page")
        .agg(
            [
                pl.col("debit").sum().alias("debit_sum"),
                pl.col("credit").sum().alias("credit_sum"),
            ]
        )
        .to_dicts()
    )
    sum_map = {d["src_page"]: (d["debit_sum"], d["credit_sum"]) for d in sums}
    issues: list[tuple[Any, ...]] = []
    for hint in page_total_hints:
        page = hint.get("src_page")
        if page not in sum_map:
            continue
        d_sum, c_sum = sum_map[page]
        d_hint = float(hint.get("debit") or 0.0)
        c_hint = float(hint.get("credit") or 0.0)
        if abs(d_sum - d_hint) > epsilon or abs(c_sum - c_hint) > epsilon:
            issues.append((page, d_sum, c_sum, d_hint, c_hint))
    return issues


@dataclass(slots=True)
class ValidationReport:
    """Aggregated validation metrics."""

    rows_parsed: int
    line_match_pct: float
    amount_normalized_pct: float
    dropped_lines_by_rule: dict[str, int] = field(default_factory=dict)
    balance_issues: Sequence[tuple[Any, ...]] = field(default_factory=list)

    def compact(self) -> str:
        """Return a one-line summary suitable for CLI output."""
        return (
            f"rows={self.rows_parsed} "
            f"matched={self.line_match_pct:.1f}% "
            f"normalized={self.amount_normalized_pct:.1f}% "
            f"imbalances={len(self.balance_issues)}"
        )
