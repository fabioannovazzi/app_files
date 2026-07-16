from __future__ import annotations

"""Helper functions shared by deterministic statement reconciliation flows."""

import datetime as dt
import json
from typing import Any, Iterable, Sequence, Tuple

import polars as pl


def _stage_match_count(
    stage_counts: dict, count_keys: Sequence[str] | str, indices_key: str | None
) -> int:
    """Return explicit stage match counts, trying multiple numeric keys if provided."""
    keys: Sequence[str]
    if isinstance(count_keys, str):
        keys = (count_keys,)
    else:
        keys = count_keys
    for key in keys:
        value = stage_counts.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:  # pragma: no cover - defensive fallback
            continue
    if not indices_key:
        return 0
    indices = stage_counts.get(indices_key)
    if indices is None:
        return 0
    try:
        return int(len(indices))
    except Exception:  # pragma: no cover - defensive fallback
        return 0


def compute_balanced_clusters(
    filtered_unmatched_bank: pl.DataFrame,
    unmatched_ledger_rows: list[dict],
    unmatched_ledger_schema: dict[str, Any],
) -> tuple[list[dict], list[dict]]:
    """Return balanced amount/date clusters and a JSON‑serialisable copy.

    A cluster is balanced when, for the same (date, signed amount), the bank and
    ledger have the same occurrence count.
    """
    if filtered_unmatched_bank.is_empty():
        return [], []
    ldf = pl.DataFrame(
        unmatched_ledger_rows, schema=unmatched_ledger_schema, infer_schema_length=None
    )

    b_grp = filtered_unmatched_bank.group_by(["date", "amount"]).agg(
        pl.len().alias("bank_count")
    )
    l_grp = ldf.group_by(["date", "amount"]).agg(pl.len().alias("ledger_count"))
    balanced = (
        b_grp.join(l_grp, on=["date", "amount"], how="inner")
        .filter(pl.col("bank_count") == pl.col("ledger_count"))
        .sort(["date", "amount"])
    )
    rows = balanced.to_dicts()
    # JSON‑serialisable copy (dates → ISO)
    rows_json: list[dict] = []
    for r in rows:
        r2 = dict(r)
        d = r2.get("date")
        try:
            if isinstance(d, dt.datetime):
                r2["date"] = d.date().isoformat()
            elif isinstance(d, dt.date):
                r2["date"] = d.isoformat()
        except Exception:
            r2["date"] = str(d)
        rows_json.append(r2)
    return rows, rows_json


def bucket_table(df: pl.DataFrame) -> list[dict]:
    """Return a compact amount bucket table (absolute amount)."""
    if df.is_empty():
        return []

    def _bucket_expr(col: pl.Expr) -> pl.Expr:
        a = col.abs()
        return (
            pl.when(a <= 5)
            .then(pl.lit("0-5"))
            .when(a <= 10)
            .then(pl.lit("5-10"))
            .when(a <= 25)
            .then(pl.lit("10-25"))
            .when(a <= 50)
            .then(pl.lit("25-50"))
            .when(a <= 100)
            .then(pl.lit("50-100"))
            .when(a <= 250)
            .then(pl.lit("100-250"))
            .when(a <= 500)
            .then(pl.lit("250-500"))
            .when(a <= 1000)
            .then(pl.lit("500-1000"))
            .when(a <= 2500)
            .then(pl.lit("1000-2500"))
            .when(a <= 5000)
            .then(pl.lit("2500-5000"))
            .otherwise(pl.lit(">5000"))
        )

    tmp = (
        df.with_columns(
            [
                pl.col("amount").abs().alias("abs_amount"),
                _bucket_expr(pl.col("amount")).alias("bucket"),
            ]
        )
        .group_by("bucket")
        .agg(
            [
                pl.len().alias("count"),
                pl.col("amount").sum().alias("signed_total"),
                pl.col("abs_amount").sum().alias("abs_total"),
            ]
        )
    )
    order = {
        "0-5": 0,
        "5-10": 1,
        "10-25": 2,
        "25-50": 3,
        "50-100": 4,
        "100-250": 5,
        "250-500": 6,
        "500-1000": 7,
        "1000-2500": 8,
        "2500-5000": 9,
        ">5000": 10,
    }
    tmp = (
        tmp.with_columns(
            pl.col("bucket")
            .map_elements(lambda b: order.get(b, 99), return_dtype=pl.Int32)
            .alias("__ord__")
        )
        .sort("__ord__")
        .drop("__ord__")
    )
    return tmp.to_dicts()


def build_stage_summary_table(stage_counts: dict) -> pl.DataFrame:
    """Return a Polars table summarising accepted and at-least counts per stage."""
    origin_counts: dict[int, int] = {}
    try:
        raw_origin = stage_counts.get("stage_origin_counts")
        if isinstance(raw_origin, dict):
            origin_counts = {
                int(k): int(v)
                for k, v in raw_origin.items()
                if isinstance(k, (int, str)) and isinstance(v, (int, float))
            }
    except Exception:
        origin_counts = {}

    s3 = _stage_match_count(
        stage_counts, ("stage3_evidence", "stage3_cash"), "stage3_cash_indices"
    )
    s4 = _stage_match_count(
        stage_counts, ("stage4_evidence", "stage4_card"), "stage4_card_indices"
    )
    s5 = stage_counts.get("stage5_salary_gate", 0)
    s6 = stage_counts.get("stage6_beneficiary", 0)
    s7 = stage_counts.get("stage7_iban", 0)
    s8 = stage_counts.get("stage8_reference", 0)
    s5_plus = s5 + s6 + s7 + s8
    s3_at_least = int(stage_counts.get("stage3_at_least", s3 + s4 + s5_plus))
    s4_at_least = int(stage_counts.get("stage4_at_least", s4 + s5_plus))
    s5_at_least = int(stage_counts.get("stage5_at_least", s5_plus))
    rows = [
        {
            "stage": "1 Amount and Date Window",
            "accepted": int(origin_counts.get(1, stage_counts.get("stage1_assign", 0))),
            "at_least": int(stage_counts.get("stage1_assign", 0)),
        },
        {
            "stage": "2 Bank Fees and Charges",
            "accepted": int(
                origin_counts.get(2, stage_counts.get("stage2_fix_fee", 0))
            ),
            "at_least": None,
        },
        {
            "stage": "3 Cash Withdrawals/Deposits",
            "accepted": int(origin_counts.get(3, s3)),
            "at_least": s3_at_least,
        },
        {
            "stage": "4 Card Payments",
            "accepted": int(origin_counts.get(4, s4)),
            "at_least": s4_at_least,
        },
        {
            "stage": "5 Payroll and Taxes",
            "accepted": int(origin_counts.get(5, s5)),
            "at_least": s5_at_least,
        },
        {
            "stage": "6 Beneficiary Name",
            "accepted": int(origin_counts.get(6, s6)),
            "at_least": int(
                stage_counts.get(
                    "stage6_at_least", stage_counts.get("stage6_beneficiary", 0)
                )
            ),
        },
        {
            "stage": "7 IBAN",
            "accepted": int(origin_counts.get(7, s7)),
            "at_least": int(
                stage_counts.get("stage7_at_least", stage_counts.get("stage7_iban", 0))
            ),
        },
        {
            "stage": "8 References (Invoice/CRO/TRN)",
            "accepted": int(origin_counts.get(8, s8)),
            "at_least": int(
                stage_counts.get(
                    "stage8_at_least", stage_counts.get("stage8_reference", 0)
                )
            ),
        },
    ]
    return pl.DataFrame(rows)


def build_bank_funnel(
    bank_txns: list,
    stage_counts: dict,
    dropped_rows: int,
    unmatched_before: int | None = None,
    unmatched_after: int | None = None,
) -> pl.DataFrame:
    """Build bank-side funnel reflecting requested stage semantics.

    Semantics (as requested):
    - Step 1 start = bank transactions after dropping non‑transactions/garbage.
      If ``unmatched_after`` is provided, prefer it; otherwise use ``len(bank_txns)``
      (which is already post‑filter in the UI flow).
    - Step 2 start = non‑matched of Step 1 (start1 − matched1).
    - Steps 3–8 start = matched of Step 1.
    - Matched for Steps 3–8 = total accepted by that step (not cumulative "at least").
    """
    bank_total = len(bank_txns)
    origin_counts: dict[int, int] = {}
    try:
        raw_origin = stage_counts.get("stage_origin_counts")
        if isinstance(raw_origin, dict):
            origin_counts = {
                int(k): int(v)
                for k, v in raw_origin.items()
                if isinstance(k, (int, str)) and isinstance(v, (int, float))
            }
    except Exception:
        origin_counts = {}

    p1 = int(origin_counts.get(1, stage_counts.get("stage1_assign", 0)))
    p2 = int(origin_counts.get(2, stage_counts.get("stage2_fix_fee", 0)))
    # For steps 3..8, use per-step evidence/acceptance counters (non-exclusive)
    # so that "matched" is identical across Bank and Ledger funnels.
    p3 = _stage_match_count(
        stage_counts, ("stage3_evidence", "stage3_cash"), "stage3_cash_indices"
    )
    p4 = _stage_match_count(
        stage_counts, ("stage4_evidence", "stage4_card"), "stage4_card_indices"
    )
    p5 = int(stage_counts.get("stage5_salary_gate", 0))
    p6 = int(stage_counts.get("stage6_beneficiary", 0))
    p7 = int(stage_counts.get("stage7_iban", 0))
    p8 = int(stage_counts.get("stage8_reference", 0))

    s3_at_least = int(stage_counts.get("stage3_at_least", p3))
    s4_at_least = int(stage_counts.get("stage4_at_least", p4))
    s5_at_least = int(stage_counts.get("stage5_at_least", p5))
    s6_at_least = int(stage_counts.get("stage6_at_least", p6))
    s7_at_least = int(stage_counts.get("stage7_at_least", p7))
    s8_at_least = int(stage_counts.get("stage8_at_least", p8))

    rows: list[dict] = []

    def row(step: str, starting: int, matched: int, atleast: int | None = None) -> dict:
        not_matched = max(0, int(starting) - int(matched))
        return {
            "step": step,
            "starting": int(starting),
            "matched": int(matched),
            "not_matched": int(not_matched),
            "at_least": int(atleast) if atleast is not None else None,
        }

    # Step 1: start equals the number of bank rows that actually entered
    # matching (bank_txns is already post early-drop). Do not subtract again.
    s1_start = int(bank_total)
    rows.append(row("1 Amount and Date Window", s1_start, p1, p1))

    # Step 2: start from non‑matched of Step 1
    s2_start = max(0, s1_start - p1)
    rows.append(
        {
            "step": "2 Bank Fees and Charges",
            "starting": int(s2_start),
            "matched": int(p2),
            "not_matched": int(max(0, s2_start - p2)),
            "at_least": None,
        }
    )
    rows.append(
        row(
            "3 Cash Withdrawals/Deposits",
            p1,
            p3,
            s3_at_least,
        )
    )
    rows.append(
        row(
            "4 Card Payments",
            p1,
            p4,
            s4_at_least,
        )
    )
    rows.append(
        row(
            "5 Payroll and Taxes",
            p1,
            p5,
            s5_at_least,
        )
    )
    rows.append(
        row(
            "6 Beneficiary Name",
            p1,
            p6,
            s6_at_least,
        )
    )
    rows.append(
        row(
            "7 IBAN",
            p1,
            p7,
            s7_at_least,
        )
    )
    rows.append(
        row(
            "8 References (Invoice/CRO/TRN)",
            p1,
            p8,
            s8_at_least,
        )
    )
    df = pl.DataFrame(rows)
    # Ensure consistent column order
    if set(["step", "starting", "matched", "not_matched", "at_least"]).issubset(
        df.columns
    ):
        df = df.select(["step", "starting", "matched", "not_matched", "at_least"])
    return df


def build_ledger_funnel(ledger_txns: list, stage_counts: dict) -> pl.DataFrame:
    """Build ledger-side funnel using the same stage semantics.

    - Step 1 start = total ledger transactions provided.
    - Step 2 start = non‑matched of Step 1 (start1 − matched1).
    - Steps 3–8 start = matched of Step 1.
    - Matched for Steps 3–8 = total accepted by that step (not cumulative).
    """
    ledger_total = len(ledger_txns)
    # Prefer origin counts when available so "matched" equals per‑step acceptances
    origin_counts: dict[int, int] = {}
    try:
        raw_origin = stage_counts.get("stage_origin_counts")
        if isinstance(raw_origin, dict):
            origin_counts = {
                int(k): int(v)
                for k, v in raw_origin.items()
                if isinstance(k, (int, str)) and isinstance(v, (int, float))
            }
    except Exception:
        origin_counts = {}

    p1 = int(origin_counts.get(1, stage_counts.get("stage1_assign", 0)))
    p2 = int(origin_counts.get(2, stage_counts.get("stage2_fix_fee", 0)))
    # For steps 3..8, always use per-step evidence/acceptance counters
    p3 = _stage_match_count(
        stage_counts, ("stage3_evidence", "stage3_cash"), "stage3_cash_indices"
    )
    p4 = _stage_match_count(
        stage_counts, ("stage4_evidence", "stage4_card"), "stage4_card_indices"
    )
    p5 = int(stage_counts.get("stage5_salary_gate", 0))
    p6 = int(stage_counts.get("stage6_beneficiary", 0))
    p7 = int(stage_counts.get("stage7_iban", 0))
    p8 = int(stage_counts.get("stage8_reference", 0))

    s3_at_least = int(stage_counts.get("stage3_at_least", p3))
    s4_at_least = int(stage_counts.get("stage4_at_least", p4))
    s5_at_least = int(stage_counts.get("stage5_at_least", p5))
    s6_at_least = int(stage_counts.get("stage6_at_least", p6))
    s7_at_least = int(stage_counts.get("stage7_at_least", p7))
    s8_at_least = int(stage_counts.get("stage8_at_least", p8))

    rows: list[dict] = []

    def row(step: str, starting: int, matched: int, atleast: int | None = None) -> dict:
        not_matched = max(0, int(starting) - int(matched))
        return {
            "step": step,
            "starting": int(starting),
            "matched": int(matched),
            "not_matched": int(not_matched),
            "at_least": int(atleast) if atleast is not None else None,
        }

    s1_start = int(ledger_total)
    rows.append(row("1 Amount and Date Window", s1_start, p1, p1))
    s2_start = max(0, s1_start - p1)
    rows.append(
        {
            "step": "2 Bank Fees and Charges",
            "starting": int(s2_start),
            "matched": int(p2),
            "not_matched": int(max(0, s2_start - p2)),
            "at_least": None,
        }
    )
    rows.append(
        row(
            "3 Cash Withdrawals/Deposits",
            p1,
            p3,
            s3_at_least,
        )
    )
    rows.append(
        row(
            "4 Card Payments",
            p1,
            p4,
            s4_at_least,
        )
    )
    rows.append(
        row(
            "5 Payroll and Taxes",
            p1,
            p5,
            s5_at_least,
        )
    )
    rows.append(
        row(
            "6 Beneficiary Name",
            p1,
            p6,
            s6_at_least,
        )
    )
    rows.append(
        row(
            "7 IBAN",
            p1,
            p7,
            s7_at_least,
        )
    )
    rows.append(
        row(
            "8 References (Invoice/CRO/TRN)",
            p1,
            p8,
            s8_at_least,
        )
    )
    # No explicit unmatched summary row in the funnel display
    df = pl.DataFrame(rows)
    if set(["step", "starting", "matched", "not_matched", "at_least"]).issubset(
        df.columns
    ):
        df = df.select(["step", "starting", "matched", "not_matched", "at_least"])
    return df


def build_stage_leftovers_for_excel(
    bank_txns: list,
    stage_counts: dict,
    max_rows: int = 10000,
) -> list[dict]:
    """Return a list of leftover bank rows with reason labels for Excel."""
    staged_leftovers: list[dict] = []

    def _rows_from_indices(indices: Iterable[int], reason: str) -> None:
        for i in list(indices)[:max_rows]:
            t = bank_txns[i]
            d = t.date.date() if hasattr(t.date, "date") else t.date
            staged_leftovers.append(
                {
                    "reason": reason,
                    "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "amount": float(t.amount),
                    "description": t.description or "",
                    "beneficiary": t.beneficiary or "",
                }
            )

    _rows_from_indices(stage_counts.get("stage1_no_candidates", []), "1:no_candidates")
    _rows_from_indices(
        stage_counts.get("stage1_has_candidates_unassigned", []), "1:unassigned"
    )
    _rows_from_indices(
        stage_counts.get("stage5_empty_desc_unmatched", []), "5:empty_desc_leftover"
    )
    _rows_from_indices(
        stage_counts.get("stage6_considered_not_accepted", []),
        "6:benef_considered_not_accepted",
    )
    _rows_from_indices(
        stage_counts.get("stage6_present_not_considered", []),
        "6:benef_present_not_considered",
    )
    _rows_from_indices(
        stage_counts.get("stage7_considered_not_accepted", []),
        "7:iban_considered_not_accepted",
    )
    _rows_from_indices(
        stage_counts.get("stage7_present_no_equal", []), "7:iban_present_no_equal"
    )
    return staged_leftovers
