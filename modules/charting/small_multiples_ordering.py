from __future__ import annotations

import logging
from typing import Any

import polars as pl

from modules.utilities.utils import get_schema_and_column_names

__all__ = ["order_small_multiple_facets_by_total"]

_LOGGER = logging.getLogger(__name__)


def _item_label(item: Any) -> str:
    return str(item or "").strip()


def _is_other_like(item: Any, aggregate_prefix: str) -> bool:
    label = _item_label(item).casefold()
    prefix = str(aggregate_prefix or "").strip().casefold()
    return (
        label in {"other", "others", "other (aggregated)"}
        or label.startswith("other ")
        or label.startswith("others ")
        or label.startswith("all other")
        or (bool(prefix) and label.startswith(prefix))
    )


def order_small_multiple_facets_by_total(
    lf: pl.LazyFrame,
    facet_dimension: str,
    metric_column: str,
    facet_items: list[Any],
    aggregate_prefix: str,
) -> list[Any]:
    """Order small-multiple panels by plotted scale, with residual buckets last.

    This is deterministic because panel order is a chart-rendering contract:
    the same plotted metric and facet values should always produce the same
    panel sequence, independent of input row order.
    """

    if not facet_items:
        return facet_items
    cols, _ = get_schema_and_column_names(lf)
    if facet_dimension not in cols or metric_column not in cols:
        return facet_items
    try:
        totals = (
            lf.group_by(facet_dimension)
            .agg(pl.col(metric_column).sum().alias("__total"))
            .collect()
        )
    except (pl.exceptions.PolarsError, TypeError, ValueError):
        _LOGGER.exception("Facet ordering failed; keeping original subplot order.")
        return facet_items
    if totals.is_empty():
        return facet_items

    totals_map: dict[str, float] = {}
    for row in totals.to_dicts():
        key = _item_label(row.get(facet_dimension))
        if not key:
            continue
        try:
            totals_map[key] = float(row.get("__total") or 0.0)
        except (TypeError, ValueError):
            totals_map[key] = 0.0

    aggregate_items = [
        item for item in facet_items if _is_other_like(item, aggregate_prefix)
    ]
    regular_items = [item for item in facet_items if item not in aggregate_items]
    regular_items.sort(
        key=lambda item: (
            -float(totals_map.get(_item_label(item), 0.0)),
            _item_label(item).casefold(),
        )
    )
    return regular_items + aggregate_items
