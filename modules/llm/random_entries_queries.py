import io
import logging
import re

import polars as pl

from modules.llm.batch_runner import run_step_text
from modules.llm.batch_runner import run_step_json
from modules.utilities.config import get_naming_params
from modules.utilities.ui_notifier import ui
from modules.utilities.utils import (
    get_schema_and_column_names,
)


def clean_header_row_result(resp):
    match = re.search(r"-?\d+", str(resp))
    if match:
        idx = int(match.group())
        return idx if idx >= 0 else None
    return None


def infer_header_row(llm_wrapper, preview: pl.DataFrame) -> int | None:
    """Use an LLM to guess which row in *preview* is the header."""
    namingParams = get_naming_params()
    randomMovementsQuery = namingParams["randomMovementsQuery"]
    # ------ 1. Build an enumerated preview ------
    rows = []
    for idx, row in enumerate(preview.head(10).rows()):
        csv_line = "; ".join(map(str, row))
        rows.append(f"{idx}: {csv_line}")
    table_preview = "\n".join(rows)

    # ------ 2. Few-shot example helps a lot ------
    example = (
        "Example:\n"
        "0: Data; Dare; Avere; Conto\n"
        "1: 01/01/24; 100,00;;4000\n"
        "Answer: 0\n\n"
    )

    promptUser = (
        example + "Given the preview below, which *row number* (0-indexed) "
        "contains the column titles?\n"
        f"{table_preview}\n"
        "Reply with -1 if unsure."
    )
    promptSystem = "You are a helpful assistant that returns only an integer."
    try:
        reply = run_step_text(
            llm_wrapper,
            randomMovementsQuery,
            promptSystem,
            promptUser,
        )[0]
        idx = int(re.search(r"-?\d+", reply).group())
    except Exception as e:
        idx = 0
        logging.exception(e)
        ui.error("Something went wrong while processing random entry column mapping.")
    return max(0, min(idx, preview.height - 1))


def _preview(df: pl.DataFrame | pl.LazyFrame, n: int = 5) -> str:
    """Return a CSV preview for the first ``n`` rows of ``df``.

    ``infer_column_mapping`` sometimes passes a :class:`~polars.LazyFrame`, so
    this helper converts lazy inputs before writing the CSV used for the LLM
    prompt.
    """
    buf = io.StringIO()
    head = df.head(n)
    if isinstance(head, pl.LazyFrame):
        head = head.collect()
    head.write_csv(buf, include_header=True)
    return buf.getvalue()


def infer_column_mapping(
    llm_wrapper, df: pl.DataFrame, examples: str, specs: dict
) -> dict:
    """Ask an LLM to map *df* columns to standard journal fields."""
    namingParams = get_naming_params()
    inferColumnQuery = namingParams["inferColumnQuery"]
    promptSystem = "Return ONLY valid json for the function call."
    columns, schema = get_schema_and_column_names(df)
    promptUser = (
        examples + "\nNow map the following preview. Row numbers start at 0.\n"
        f"Columns: {list(columns)}\nPreview:\n{_preview(df)}\n"
        "Please respond in json."
    )
    tools = [{"type": "function", "function": specs}]
    toolChoice = {"type": "function", "function": {"name": "map_journal_columns"}}
    try:
        return run_step_json(
            llm_wrapper,
            inferColumnQuery,
            promptSystem,
            promptUser,
            tools=tools,
            tool_choice=toolChoice,
        )[0]
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong while processing random entry column mapping.")
        return {}
