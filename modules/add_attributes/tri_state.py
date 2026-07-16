from __future__ import annotations

"""Helpers to derive tri-state views for multi-select attributes.

A multi-select attribute is represented by:
- One-hot leaf columns: ``attr_id__<leaf_id>`` booleans (True/False)
- Attribute flags: ``attr_id__unknown`` and ``attr_id__not_in_taxonomy`` (booleans)

This module exposes a small helper to derive a per-leaf tri-state column
from those booleans so UIs can show "true"/"false"/"N/A"/"not in taxonomy"
without ad-hoc logic scattered around.
"""

from typing import Literal

import polars as pl

__all__ = ["derive_leaf_tri_state"]


def derive_leaf_tri_state(
    df: pl.DataFrame,
    attr_id: str,
    leaf_id: str,
    *,
    col_name: str | None = None,
    mode: Literal["string", "optional_bool"] = "string",
) -> pl.DataFrame:
    """Add a tri-state column for a given multi-select leaf.

    Parameters
    ----------
    df:
        Input DataFrame containing the one-hot columns and attribute flags.
    attr_id:
        Attribute identifier used in column names (e.g. "skin_type").
    leaf_id:
        Leaf identifier used in column names (e.g. "oily").
    col_name:
        Optional output column name. Defaults to ``f"{attr_id}__{leaf_id}_tri"``.
    mode:
        - "string": values are "true", "false", "N/A", or "not in taxonomy".
        - "optional_bool": values are True/False/None (None for unknown/not in taxonomy).

    Returns
    -------
    pl.DataFrame
        A new DataFrame with the derived tri-state column appended.
    """
    leaf_col = f"{attr_id}__{leaf_id}"
    unknown_col = f"{attr_id}__unknown"
    not_in_taxonomy_col = f"{attr_id}__not_in_taxonomy"
    out_col = col_name or f"{leaf_col}_tri"

    if mode == "string":
        expr = (
            pl.when(pl.col(leaf_col)).then(pl.lit("true"))
            .when(pl.col(unknown_col)).then(pl.lit("N/A"))
            .when(pl.col(not_in_taxonomy_col)).then(pl.lit("not in taxonomy"))
            .otherwise(pl.lit("false"))
        )
    elif mode == "optional_bool":
        expr = (
            pl.when(pl.col(unknown_col) | pl.col(not_in_taxonomy_col))
            .then(pl.lit(None, dtype=pl.Boolean))
            .otherwise(pl.col(leaf_col).cast(pl.Boolean))
        )
    else:  # pragma: no cover - defensive
        raise ValueError("mode must be 'string' or 'optional_bool'")

    return df.with_columns(expr.alias(out_col))

