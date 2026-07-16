from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import polars as pl

from modules.utilities.utils import get_schema_and_column_names

from .models import ListingObservation

__all__ = [
    "build_parent_sort_snapshot",
    "assign_new_rest_from_newest",
    "assign_pareto_from_most_popular",
    "build_parent_discovery_classification",
]


def build_parent_sort_snapshot(
    observations: Iterable[ListingObservation],
) -> pl.DataFrame:
    """Collapse listing observations to one row per parent product and sort mode."""

    rows: list[dict[str, Any]] = []
    for item in observations:
        parent_id = str(item.parent_product_id or "").strip()
        if not parent_id:
            parent_id = str(item.pdp_url or "").strip()
        if not parent_id:
            continue
        rows.append(
            {
                "retailer": str(item.retailer or "").strip().lower(),
                "category_key": str(item.category_key or "").strip().lower(),
                "sort_mode": str(item.sort_mode or "").strip().lower(),
                "parent_product_id": parent_id,
                "brand": str(item.brand or "").strip() or None,
                "product_name": str(item.product_name or "").strip() or None,
                "pdp_url": str(item.pdp_url or "").strip() or None,
                "has_new_badge": bool(item.has_new_badge),
                "rank_score": _rank_score(item.page, item.position),
            }
        )
    if not rows:
        return pl.DataFrame()
    frame = pl.from_dicts(rows, infer_schema_length=None)
    frame = frame.sort("rank_score")
    frame = frame.unique(
        subset=["retailer", "category_key", "sort_mode", "parent_product_id"],
        keep="first",
    )
    return frame


def assign_new_rest_from_newest(
    frame: pl.DataFrame,
    *,
    newest_sort_mode: str = "newest",
    new_share: float = 0.20,
) -> pl.DataFrame:
    """Assign ``new``/``rest`` using rank on newest sort."""

    return _assign_rank_bands(
        frame,
        source_sort_mode=newest_sort_mode,
        output_column="new_rest_class",
        thresholds=[(new_share, "new"), (1.0, "rest")],
    )


def assign_pareto_from_most_popular(
    frame: pl.DataFrame,
    *,
    popular_sort_mode: str = "most_popular",
    a_share: float = 0.20,
    b_share: float = 0.50,
) -> pl.DataFrame:
    """Assign Pareto A/B/C from rank on most popular sort."""

    return _assign_rank_bands(
        frame,
        source_sort_mode=popular_sort_mode,
        output_column="pareto_class",
        thresholds=[(a_share, "A"), (b_share, "B"), (1.0, "C")],
    )


def build_parent_discovery_classification(
    observations: Iterable[ListingObservation],
    *,
    newest_sort_mode: str = "newest",
    popular_sort_mode: str = "most_popular",
) -> pl.DataFrame:
    """Build parent-level discovery classification from raw listing observations."""

    snapshot = build_parent_sort_snapshot(observations)
    if snapshot.is_empty():
        return snapshot
    new_rest = assign_new_rest_from_newest(
        snapshot,
        newest_sort_mode=newest_sort_mode,
    )
    pareto = assign_pareto_from_most_popular(
        snapshot,
        popular_sort_mode=popular_sort_mode,
    )
    key_cols = ["retailer", "category_key", "parent_product_id"]
    cols, _ = get_schema_and_column_names(snapshot)
    base_cols = [
        col
        for col in (
            "retailer",
            "category_key",
            "parent_product_id",
            "brand",
            "product_name",
            "pdp_url",
            "has_new_badge",
        )
        if col in cols
    ]
    base = snapshot.select(base_cols).unique(subset=key_cols, keep="first")
    merged = base.join(
        new_rest.select(key_cols + ["new_rest_class"]),
        on=key_cols,
        how="left",
    ).join(
        pareto.select(key_cols + ["pareto_class"]),
        on=key_cols,
        how="left",
    )
    return merged


def _rank_score(page: int, position: int) -> int:
    safe_page = int(page) if int(page) > 0 else 1
    safe_position = int(position) if int(position) > 0 else 1
    return (safe_page - 1) * 10_000 + safe_position


def _assign_rank_bands(
    frame: pl.DataFrame,
    *,
    source_sort_mode: str,
    output_column: str,
    thresholds: list[tuple[float, str]],
) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    mode = str(source_sort_mode or "").strip().lower()
    scoped = frame.filter(pl.col("sort_mode") == mode)
    if scoped.is_empty():
        key_cols = ["retailer", "category_key", "parent_product_id"]
        return frame.select(key_cols).unique().with_columns(
            pl.lit(None, dtype=pl.Utf8).alias(output_column)
        )
    partitions: list[pl.DataFrame] = []
    for group in scoped.partition_by(["retailer", "category_key"], maintain_order=True):
        count = max(1, group.height)
        ordered = group.sort("rank_score")
        labels: list[str] = []
        for index in range(count):
            pct = (index + 1) / count
            label = thresholds[-1][1]
            for threshold, threshold_label in thresholds:
                if pct <= threshold + 1e-12:
                    label = threshold_label
                    break
            labels.append(label)
        partitions.append(ordered.with_columns(pl.Series(output_column, labels)))
    combined = pl.concat(partitions, how="diagonal_relaxed")
    return combined
