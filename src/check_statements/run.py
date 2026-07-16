from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Sequence

import polars as pl

from src.check_statements import (
    Transaction,
    auto_filter_overlap,
    staged_reconcile,
)
from src.final_pass_filter import clean_bank_not_matched

logger = logging.getLogger(__name__)


class ReconciliationError(Exception):
    """Raised when the statement reconciliation pipeline fails."""


@dataclass(frozen=True)
class ReconciliationContext:
    """Container for the transactions to reconcile."""

    bank_transactions: Sequence[Transaction]
    ledger_transactions: Sequence[Transaction]
    llm_wrapper: object | None = None


@dataclass(frozen=True)
class ReconciliationParams:
    """User-configured reconciliation parameters."""

    tolerance: float
    date_window: int
    use_absolute_amounts: bool = True
    apply_overlap_filter: bool = True
    apply_bank_cleanup: bool = True
    stage_limit: int = 8


@dataclass(frozen=True)
class ReconciliationResult:
    """Structured output produced after reconciliation."""

    bank_transactions: list[Transaction]
    ledger_transactions: list[Transaction]
    matched_pairs: list[tuple[int, int | tuple[int | None, ...] | None, str]]
    unmatched_bank: list[int]
    unmatched_ledger: list[int | None]
    stage_counts: dict[str, Any]
    has_collision: bool
    early_drop_count: int
    overlap_info: Mapping[str, Any] | None


def _apply_bank_cleanup(
    bank_txns: list[Transaction],
) -> tuple[list[Transaction], int]:
    """Apply the non-transaction filter to bank rows and return the reduced list."""

    if not bank_txns:
        return bank_txns, 0

    try:
        records = []
        for row_id, txn in enumerate(bank_txns):
            date_value = txn.date.date() if isinstance(txn.date, dt.datetime) else txn.date
            amount_value = float(txn.amount) if txn.amount is not None else None
            records.append(
                {
                    "row_id": row_id,
                    "description": txn.description or "",
                    "amount": amount_value,
                    "accounting_date": date_value,
                }
            )
        frame = pl.DataFrame(
            records,
            schema={
                "row_id": pl.Int64,
                "description": pl.Utf8,
                "amount": pl.Float64,
                "accounting_date": pl.Date,
            },
            strict=False,
            infer_schema_length=None,
        )
        cleaned, dropped, report = clean_bank_not_matched(
            frame, collect_stats=True, return_dropped_rows=True
        )
        kept_ids = {
            int(value)
            for value in cleaned.get_column("row_id").drop_nulls().cast(pl.Int64).to_list()
        }
        dropped_count = len(bank_txns) - len(kept_ids) if kept_ids else len(bank_txns)
        if kept_ids:
            bank_txns = [txn for idx, txn in enumerate(bank_txns) if idx in kept_ids]
        else:
            bank_txns = []
        if report:
            try:
                dropped_count = max(
                    dropped_count,
                    int(getattr(report, "dropped_rows", dropped_count) or dropped_count),
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed extracting dropped_rows from filter report")
        return bank_txns, dropped_count
    except Exception:
        logger.exception("Bank cleanup failed; continuing with original transactions")
        return bank_txns, 0


def _detect_collision_days(
    bank_txns: Sequence[Transaction],
    use_absolute_amounts: bool,
) -> bool:
    """Return True when several transactions share the same day/amount signature."""

    try:
        counts: dict[tuple[dt.date, float], int] = {}
        for txn in bank_txns:
            txn_date = txn.date.date() if isinstance(txn.date, dt.datetime) else txn.date
            amount_val = float(txn.amount or 0.0)
            if use_absolute_amounts:
                amount_val = abs(amount_val)
            key = (txn_date, round(amount_val, 2))
            counts[key] = counts.get(key, 0) + 1
        return any(value >= 3 for value in counts.values())
    except Exception:
        logger.exception("Collision-day detection failed")
        return False


def run_reconciliation(
    context: ReconciliationContext,
    params: ReconciliationParams,
) -> ReconciliationResult:
    """Execute reconciliation using staged matching and return the outcome."""

    bank_txns = list(context.bank_transactions)
    ledger_txns = list(context.ledger_transactions)

    overlap_info: Mapping[str, Any] | None = None
    if params.apply_overlap_filter:
        overlap = auto_filter_overlap(bank_txns, ledger_txns)
        if overlap is not None:
            bank_txns, ledger_txns, overlap_info = overlap

    early_drop_count = 0
    if params.apply_bank_cleanup and bank_txns:
        bank_txns, early_drop_count = _apply_bank_cleanup(bank_txns)

    has_collision = _detect_collision_days(bank_txns, params.use_absolute_amounts)

    try:
        (
            matched_pairs,
            unmatched_bank,
            unmatched_ledger,
            stage_counts,
        ) = staged_reconcile(
            bank_txns,
            ledger_txns,
            tolerance=float(params.tolerance),
            date_window=int(params.date_window),
            use_absolute_amounts=bool(params.use_absolute_amounts),
            up_to_stage=int(params.stage_limit),
            dense_day=bool(has_collision),
            llm_wrapper=context.llm_wrapper,
        )
    except Exception as exc:  # pragma: no cover - error surfaced to UI/tests
        logger.exception("staged_reconcile execution failed")
        raise ReconciliationError("Reconciling the statements failed.") from exc

    if early_drop_count:
        try:
            stage_counts = dict(stage_counts) if not isinstance(stage_counts, dict) else stage_counts
            stage_counts["early_non_transaction_drop"] = int(early_drop_count)
            stage_counts["unmatched_bank_dropped"] = int(
                max(
                    int(stage_counts.get("unmatched_bank_dropped", 0) or 0),
                    early_drop_count,
                )
            )
        except Exception:
            logger.exception("Updating stage counts with early drop information failed")

    return ReconciliationResult(
        bank_transactions=bank_txns,
        ledger_transactions=ledger_txns,
        matched_pairs=matched_pairs,
        unmatched_bank=unmatched_bank,
        unmatched_ledger=unmatched_ledger,
        stage_counts=stage_counts,
        has_collision=has_collision,
        early_drop_count=int(early_drop_count),
        overlap_info=overlap_info,
    )


__all__ = [
    "ReconciliationContext",
    "ReconciliationError",
    "ReconciliationParams",
    "ReconciliationResult",
    "run_reconciliation",
]
