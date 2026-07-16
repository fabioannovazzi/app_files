"""UI helper to pick category or subcategory grouping for attribute discovery."""

from __future__ import annotations

import polars as pl
from modules.utilities.ui_notifier import ui

from modules.utilities.utils import get_schema_and_column_names

__all__ = ["select_grouping_level"]


def _grouping_info(mapping: dict, lf: pl.LazyFrame) -> dict[str, tuple[str, int]]:
    """Return available grouping columns with their unique counts."""

    columns, schema = get_schema_and_column_names(lf)

    def _has_column(col: str) -> bool:
        """Return ``True`` if ``lf`` contains ``col``."""
        if columns:
            return col in columns
        if schema:
            return col in schema
        if hasattr(lf, "data") and isinstance(lf.data, dict):
            return col in lf.data
        return True  # fallback for stubs without metadata

    def nunique(col: str) -> int:
        return lf.select(pl.col(col).n_unique()).collect()[0, 0]

    info: dict[str, tuple[str, int]] = {}
    cat_col = mapping.get("category_column")
    if cat_col and _has_column(cat_col):
        info["category"] = (cat_col, nunique(cat_col))
    sub_col = mapping.get("subcategory_column")
    if sub_col and _has_column(sub_col):
        info["subcategory"] = (sub_col, nunique(sub_col))
    return info


def select_grouping_level(
    mapping: dict, lazy_df: pl.LazyFrame
) -> tuple[str, str | None]:
    """Choose product grouping level via UI radio selector.

    Parameters
    ----------
    mapping:
        Dictionary with keys ``product_column``, ``category_column`` and
        ``subcategory_column`` from :func:`infer_column_roles`.
    lazy_df:
        Original ``LazyFrame`` used only to compute unique value counts.

    Returns
    -------
    tuple
        ``("category", column)`` if the category level was chosen,
        ``("subcategory", column)`` if subcategory was chosen,
        or ``("none", None)`` when no grouping columns exiui.
    """
    info = _grouping_info(mapping, lazy_df)
    if "category" in info and "subcategory" in info:
        opts = ["category", "subcategory"]
        labels = {
            "category": f"Category ({info['category'][0]}, {info['category'][1]} unique values)",
            "subcategory": f"Subcategory ({info['subcategory'][0]}, {info['subcategory'][1]} unique values)",
        }
        choice = ui.radio(
            "Choose grouping level for attribute discovery",
            opts,
            index=0,
            format_func=lambda o: labels[o],
        )
        return choice, info[choice][0]

    if "category" in info:
        ui.info("Only one grouping level detected ('Category'). Using it by default.")
        return "category", info["category"][0]

    if "subcategory" in info:
        ui.info(
            "Only one grouping level detected ('Subcategory'). Using it by default."
        )
        return "subcategory", info["subcategory"][0]

    ui.warning(
        "No category fields detected. All products will be treated as one group."
    )
    return "none", None
