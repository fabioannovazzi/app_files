from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import polars as pl

_PLACEHOLDER_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "unknown",
    "not stated",
    "n/a (not stated)",
}


@dataclass(frozen=True, slots=True)
class ExplicitPrecisionMetric:
    run_id: str
    category_key: str
    attribute_id: str
    explicit_positive_count: int
    deterministic_match_on_explicit: int
    llm_match_on_explicit: int
    deterministic_precision_proxy: float
    llm_precision_proxy: float


__all__ = [
    "ExplicitPrecisionMetric",
    "compute_explicit_precision_metrics",
]


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_stage_value(value: object | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.casefold()
    if lowered in _PLACEHOLDER_VALUES:
        return None
    if lowered.startswith("not in taxonomy"):
        detail = ""
        if "(" in text and text.endswith(")"):
            detail = text[text.find("(") + 1 : -1].strip().casefold()
        if not detail or detail in _PLACEHOLDER_VALUES:
            return None
    return text


def _normalize_row_key(values: Sequence[object | None]) -> tuple[str, ...]:
    return tuple(_normalize_text(value) for value in values)


def _index_stage_values(
    df: pl.DataFrame,
    *,
    key_columns: Sequence[str],
    attribute_columns: Sequence[str],
) -> dict[tuple[tuple[str, ...], str], str]:
    if df.is_empty():
        return {}
    if any(column not in df.columns for column in key_columns):
        return {}
    tracked_columns = [column for column in attribute_columns if column in df.columns]
    if not tracked_columns:
        return {}

    indexed: dict[tuple[tuple[str, ...], str], str] = {}
    for row in df.select([*key_columns, *tracked_columns]).to_dicts():
        key = _normalize_row_key([row.get(column) for column in key_columns])
        for attribute_id in tracked_columns:
            value = _normalize_stage_value(row.get(attribute_id))
            if value is None:
                continue
            indexed[(key, attribute_id)] = value.casefold()
    return indexed


def _collect_metrics_for_stage(
    *,
    stage_df: pl.DataFrame,
    key_columns: Sequence[str],
    category_column: str,
    explicit_attributes: Sequence[str],
    deterministic_lookup: Mapping[tuple[tuple[str, ...], str], str],
    llm_lookup: Mapping[tuple[tuple[str, ...], str], str],
    counters: dict[tuple[str, str], dict[str, int]],
) -> None:
    if stage_df.is_empty():
        return
    if any(column not in stage_df.columns for column in key_columns):
        return
    if category_column not in stage_df.columns:
        return

    tracked_attributes = [
        attribute_id
        for attribute_id in explicit_attributes
        if attribute_id in stage_df.columns
    ]
    if not tracked_attributes:
        return

    selected_columns = list(
        dict.fromkeys([*key_columns, category_column, *tracked_attributes])
    )
    for row in stage_df.select(selected_columns).to_dicts():
        key = _normalize_row_key([row.get(column) for column in key_columns])
        category_key = _normalize_text(row.get(category_column)).casefold() or "unknown"
        for attribute_id in tracked_attributes:
            explicit_value = _normalize_stage_value(row.get(attribute_id))
            if explicit_value is None:
                continue
            metric_key = (category_key, attribute_id)
            bucket = counters.setdefault(
                metric_key,
                {
                    "explicit_positive_count": 0,
                    "deterministic_match_on_explicit": 0,
                    "llm_match_on_explicit": 0,
                },
            )
            bucket["explicit_positive_count"] += 1
            explicit_casefold = explicit_value.casefold()
            if deterministic_lookup.get((key, attribute_id)) == explicit_casefold:
                bucket["deterministic_match_on_explicit"] += 1
            if llm_lookup.get((key, attribute_id)) == explicit_casefold:
                bucket["llm_match_on_explicit"] += 1


def compute_explicit_precision_metrics(
    *,
    run_id: str,
    explicit_parent_stage: pl.DataFrame,
    explicit_variant_stage: pl.DataFrame,
    explicit_parent_attributes: Sequence[str],
    explicit_variant_attributes: Sequence[str],
    deterministic_parent_stage: pl.DataFrame,
    deterministic_variant_stage: pl.DataFrame,
    deterministic_parent_attributes: Sequence[str],
    deterministic_variant_attributes: Sequence[str],
    llm_parent_stage: pl.DataFrame,
    llm_variant_stage: pl.DataFrame,
    llm_parent_attributes: Sequence[str],
    llm_variant_attributes: Sequence[str],
) -> list[ExplicitPrecisionMetric]:
    if not run_id.strip():
        raise ValueError("run_id must be non-empty for explicit precision metrics.")

    det_parent_lookup = _index_stage_values(
        deterministic_parent_stage,
        key_columns=["retailer", "parent_product_id", "category_key"],
        attribute_columns=deterministic_parent_attributes,
    )
    det_variant_lookup = _index_stage_values(
        deterministic_variant_stage,
        key_columns=["retailer", "variant_id", "category_key"],
        attribute_columns=deterministic_variant_attributes,
    )
    llm_parent_lookup = _index_stage_values(
        llm_parent_stage,
        key_columns=["retailer", "parent_product_id", "category_key"],
        attribute_columns=llm_parent_attributes,
    )
    llm_variant_lookup = _index_stage_values(
        llm_variant_stage,
        key_columns=["retailer", "variant_id", "category_key"],
        attribute_columns=llm_variant_attributes,
    )

    counters: dict[tuple[str, str], dict[str, int]] = {}

    _collect_metrics_for_stage(
        stage_df=explicit_parent_stage,
        key_columns=["retailer", "parent_product_id", "category_key"],
        category_column="category_key",
        explicit_attributes=explicit_parent_attributes,
        deterministic_lookup=det_parent_lookup,
        llm_lookup=llm_parent_lookup,
        counters=counters,
    )
    _collect_metrics_for_stage(
        stage_df=explicit_variant_stage,
        key_columns=["retailer", "variant_id", "category_key"],
        category_column="category_key",
        explicit_attributes=explicit_variant_attributes,
        deterministic_lookup=det_variant_lookup,
        llm_lookup=llm_variant_lookup,
        counters=counters,
    )

    metrics: list[ExplicitPrecisionMetric] = []
    for (category_key, attribute_id), counts in sorted(counters.items()):
        denominator = counts["explicit_positive_count"]
        if denominator <= 0:
            continue
        deterministic_matches = counts["deterministic_match_on_explicit"]
        llm_matches = counts["llm_match_on_explicit"]
        metrics.append(
            ExplicitPrecisionMetric(
                run_id=run_id,
                category_key=category_key,
                attribute_id=attribute_id,
                explicit_positive_count=denominator,
                deterministic_match_on_explicit=deterministic_matches,
                llm_match_on_explicit=llm_matches,
                deterministic_precision_proxy=(deterministic_matches / denominator),
                llm_precision_proxy=(llm_matches / denominator),
            )
        )
    return metrics
