import logging
import math
from typing import Dict, List, Sequence

import polars as pl
from modules.utilities.ui_notifier import ui

from modules.llm.batch_runner import run_step_json
from modules.utilities.config import get_naming_params
from modules.utilities.utils import get_schema_and_column_names


def _collect_samples(
    lf: pl.LazyFrame, columns: Sequence[str], n: int = 5
) -> pl.DataFrame:
    """Return a Polars DataFrame with up to ``n * 20`` rows for the given columns."""
    if not columns:
        return pl.DataFrame()
    # Read more rows than required to increase the chance of getting unique values
    return lf.select(columns).head(n * 20).collect()


def _column_uniqueness(lf: pl.LazyFrame, columns: Sequence[str]) -> Dict[str, float]:
    """Return uniqueness ratio for each column."""
    if not columns:
        return {}
    total = lf.select(pl.len()).collect()[0, 0]
    uniques = lf.select([pl.col(c).n_unique().alias(c) for c in columns]).collect()
    return {c: (float(uniques[c][0]) / total if total else 0.0) for c in columns}


def _build_prompt(
    column_samples: Dict[str, List[str]], uniqueness: Dict[str, float]
) -> str:
    """Create the user prompt for the LLM with the given column samples."""
    lines = ["Columns, uniqueness ratio and example values:"]
    for col, values in column_samples.items():
        sample_text = ", ".join(values) if values else "(no values)"
        uniq = uniqueness.get(col, 0.0)
        lines.append(f"- {col} (unique {uniq:.2f}): [{sample_text}]")

    instructions = """
The dataset above is a sales table. Identify:
1. The product identifier column (contains product names or IDs).
2. The category column (broad product grouping) – if one exists.
3. The subcategory column (more specific grouping within the category) – if one exists.

When choosing columns consider the uniqueness ratio: product columns often have high uniqueness, while category fields have lower uniqueness. Column names may appear in any language.
Do not confuse channel, region or segment columns with product categories.
Output a JSON dictionary with keys 'product_column', 'category_column', 'subcategory_column'.
Use null if a key is not applicable.
    """
    return "\n".join(lines) + "\n" + instructions


def infer_column_roles(llm_wrapper, lf: pl.LazyFrame) -> Dict[str, str | None]:
    """Infer product, category and subcategory columns using an LLM."""
    columns, schema = get_schema_and_column_names(lf)

    namingParams = get_naming_params()
    inferColumnQuery = namingParams["inferColumnQuery"]
    numeric = set()
    if schema is not None:
        for name, dtype in schema.items():
            try:
                if dtype.is_numeric():
                    numeric.add(name)
            except Exception as e:
                logging.exception(e)
                ui.error("Something went wrong while inferring column data types.")
                continue
    relevant = [c for c in columns if c not in numeric]

    sample_df = _collect_samples(lf, relevant, 5)
    column_samples: Dict[str, List[str]] = {}
    for col in relevant:
        values = []
        if col in get_schema_and_column_names(sample_df)[0]:
            for val in sample_df[col].to_list():
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    continue
                sval = str(val)
                if sval in values:
                    # Skip duplicate values so samples are unique
                    continue
                values.append(sval)
                if len(values) >= 5:
                    break
        column_samples[col] = values

    uniqueness = _column_uniqueness(lf, relevant)
    user_prompt = _build_prompt(column_samples, uniqueness)
    system_prompt = "You are a data expert. Return JSON only."

    resp = run_step_json(
        llm_wrapper,
        inferColumnQuery,
        system_prompt,
        user_prompt,
    )[0]
    expected = {"product_column", "category_column", "subcategory_column"}
    if not isinstance(resp, dict):
        result = {k: None for k in expected}
    else:
        result = {k: resp.get(k) for k in expected}
    return result


__all__ = ["infer_column_roles"]
