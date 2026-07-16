from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

import polars as pl

from modules.check_entries.constants import BeneficiaryCheckMode
from modules.check_entries.service import (
    PartialCheckError,
    check_entries_pipeline,
)
from modules.check_entries.utils import hide_line_numbers
from modules.utils.polars_excel_writer import write_polars_excel

__all__ = [
    "CheckEntriesRunContext",
    "CheckEntriesRunParams",
    "CheckEntriesRunResult",
    "run_check_entries",
]


@dataclass(frozen=True)
class CheckEntriesRunContext:
    """Execution context for the check entries pipeline."""

    data: pl.DataFrame | pl.LazyFrame | bytes | str
    pdf_files: Sequence
    llm_wrapper: object
    provider: str | None
    model: str | None


@dataclass(frozen=True)
class CheckEntriesRunParams:
    """User-configured parameters for the pipeline."""

    mapping: Mapping[str, str | None]
    debug: bool
    lang: str
    amount_tolerance: float
    date_window: int
    timing_difference_window: int | None
    beneficiary_similarity: float
    beneficiary_check_mode: BeneficiaryCheckMode


@dataclass(frozen=True)
class CheckEntriesRunResult:
    """Structured output returned after running the checks."""

    result_df: pl.DataFrame
    summary_text: str
    summary_metrics: Mapping[str, pl.DataFrame]
    excel_bytes: bytes
    error_message: str | None
    partial: bool = False
    partial_reason: str | None = None


def _build_excel_payload(
    result_df: pl.DataFrame,
    summary_metrics: Mapping[str, pl.DataFrame],
) -> bytes:
    with io.BytesIO() as buffer:
        sheets = {"results": hide_line_numbers(result_df)}
        sheets.update(summary_metrics)
        write_polars_excel(sheets, buffer)
        return buffer.getvalue()


def run_check_entries(
    context: CheckEntriesRunContext,
    params: CheckEntriesRunParams,
    *,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> CheckEntriesRunResult:
    """Execute the check entries pipeline and build the export payload."""

    try:
        (
            result_df,
            summary_text,
            summary_metrics,
            error_message,
        ) = check_entries_pipeline(
            context.data,
            context.pdf_files,
            context.llm_wrapper,
            mapping=params.mapping,
            provider=context.provider,
            model=context.model,
            debug=params.debug,
            lang=params.lang,
            amount_tolerance=params.amount_tolerance,
            date_window=params.date_window,
            timing_difference_window=params.timing_difference_window,
            beneficiary_similarity=params.beneficiary_similarity,
            beneficiary_check_mode=params.beneficiary_check_mode,
            progress=progress,
            is_cancelled=is_cancelled,
        )
    except PartialCheckError as exc:
        partial_df = exc.partial_df
        excel_bytes = _build_excel_payload(partial_df, {})
        cause_text = str(exc.cause) if exc.cause else None
        return CheckEntriesRunResult(
            result_df=partial_df,
            summary_text="",
            summary_metrics={},
            excel_bytes=excel_bytes,
            error_message=cause_text,
            partial=True,
            partial_reason=cause_text,
        )

    excel_bytes = _build_excel_payload(result_df, summary_metrics)
    return CheckEntriesRunResult(
        result_df=result_df,
        summary_text=summary_text,
        summary_metrics=summary_metrics,
        excel_bytes=excel_bytes,
        error_message=error_message,
        partial=False,
        partial_reason=None,
    )
