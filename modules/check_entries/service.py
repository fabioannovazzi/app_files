from __future__ import annotations
import logging
from pathlib import Path
from typing import Callable, Iterable, Mapping, Tuple

import polars as pl

from modules.check_entries.constants import BeneficiaryCheckMode
from modules.check_entries.logic import PartialCheckError, run_automatic_check
from modules.check_entries.pdf_matching import build_pdf_map
from modules.check_entries.summary import summarize_results
from modules.llm.function_calls import function_specs, mapping_examples
from modules.llm.random_entries_queries import infer_column_mapping
from modules.process_excel.logic import _as_dict
from modules.process_pdf_journal.logic import parse_journal
from src.check_statements import (
    _detect_excel_header_polars as detect_excel_header_polars,
)
from src.check_statements import _rebuild_df_with_header as rebuild_df_with_header


def _load_dataframe(
    data: str | Path | bytes | pl.DataFrame | pl.LazyFrame,
) -> pl.DataFrame:
    """Return a DataFrame from *data* which may be a path or in-memory object."""
    if isinstance(data, pl.LazyFrame):
        return data.collect()
    if isinstance(data, pl.DataFrame):
        return data
    if isinstance(data, (str, Path)):
        path = Path(data)
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            content = path.read_bytes()
            header_row = detect_excel_header_polars(content)
            return rebuild_df_with_header(content, header_row)
        if suffix == ".csv":
            return pl.read_csv(path)
        if suffix == ".pdf":
            with open(path, "rb") as fh:
                return parse_journal(fh.read())
        raise ValueError(f"Unsupported file type: {suffix}")
    if isinstance(data, bytes):
        header_row = detect_excel_header_polars(data)
        return rebuild_df_with_header(data, header_row)
    raise TypeError("Unsupported data type for journal input")


def _infer_mapping(llm_wrapper, df: pl.DataFrame) -> Mapping[str, str]:
    """Infer a journal column mapping using the LLM."""
    examples = mapping_examples()
    specs = function_specs()
    inferred = infer_column_mapping(llm_wrapper, df, examples, specs)
    return _as_dict(inferred.get("fields", {}))


def check_entries_pipeline(
    data: str | Path | bytes | pl.DataFrame | pl.LazyFrame,
    pdf_files: Iterable,
    llm_wrapper,
    *,
    mapping: Mapping[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    debug: bool = False,
    lang: str = "eng",
    amount_tolerance: float = 0.0,
    date_window: int = 0,
    timing_difference_window: int | None = None,
    beneficiary_similarity: float = 100.0,
    beneficiary_check_mode: BeneficiaryCheckMode = BeneficiaryCheckMode.COMPARE,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> Tuple[pl.DataFrame, str, dict[str, pl.DataFrame], str | None]:
    """Run the full entry checking pipeline.

    Parameters
    ----------
    data:
        Source journal data. Can be a path, bytes, or a pre-loaded DataFrame.
    pdf_files:
        Iterable of PDF files corresponding to journal movements.
    llm_wrapper:
        Wrapper used for LLM calls.
    mapping:
        Optional explicit column mapping. When not provided the mapping is
        inferred automatically.

    Returns
    -------
    tuple
        ``(result_df, summary_text, summary_metrics, error_message)``
    """

    df = _load_dataframe(data)
    mapping = mapping or _infer_mapping(llm_wrapper, df)
    pdf_map = build_pdf_map(pdf_files)

    result_df = run_automatic_check(
        df,
        mapping,
        pdf_map,
        llm_wrapper,
        provider=provider,
        model=model,
        debug=debug,
        lang=lang,
        amount_tolerance=amount_tolerance,
        date_window=date_window,
        timing_difference_window=timing_difference_window,
        beneficiary_similarity=beneficiary_similarity,
        beneficiary_check_mode=beneficiary_check_mode,
        progress=progress,
        is_cancelled=is_cancelled,
    )

    error_message: str | None = None
    try:
        summary_text, summary_metrics = summarize_results(llm_wrapper, result_df, lang)
    except Exception as e:  # pragma: no cover - unexpected errors surfaced
        logging.exception(e)
        summary_text = ""
        summary_metrics = {}
        error_message = f"Could not summarize results: {e}"
    return result_df, summary_text, summary_metrics, error_message


__all__ = ["check_entries_pipeline", "PartialCheckError"]
