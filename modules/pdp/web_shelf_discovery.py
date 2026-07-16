from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations
from typing import Any, Mapping, Sequence

import polars as pl

from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "discover_web_shelves",
    "empty_web_shelf_outputs",
    "normalize_attribute_tokens",
    "refine_selected_shelves_with_third_attribute",
    "refine_shelf_with_third_attribute",
]

CSV_LIST_SEPARATOR = " | "
RESIDUAL_BUNDLE_KEY = "__residual__"
DEFAULT_ALPHAS = (0.0, 0.7, 1.0, 1.2)
PLACEHOLDER_VALUES = {
    "",
    "0",
    "1",
    "false",
    "n/a",
    "n/a (not stated)",
    "na",
    "no",
    "none",
    "not in taxonomy",
    "not stated",
    "null",
    "true",
    "unknown",
    "yes",
}

SELECTED_SHELVES_SCHEMA = {
    "alpha": pl.Float64,
    "shelf_rank": pl.Int64,
    "bundle_key": pl.Utf8,
    "bundle_size": pl.Int64,
    "attributes": pl.Utf8,
    "gross_weight_share": pl.Float64,
    "incremental_weight_share": pl.Float64,
    "cumulative_weight_share": pl.Float64,
    "gross_sku_count": pl.Int64,
    "incremental_sku_count": pl.Int64,
    "gross_sku_share": pl.Float64,
    "incremental_sku_share": pl.Float64,
    "density_index": pl.Float64,
    "gross_brand_count": pl.Int64,
    "incremental_brand_count": pl.Int64,
    "top_brand_weight_share": pl.Float64,
    "brand_hhi": pl.Float64,
    "top_products": pl.Utf8,
    "top_brands": pl.Utf8,
}

CANDIDATE_SHELVES_SCHEMA = {
    "alpha": pl.Float64,
    "bundle_key": pl.Utf8,
    "bundle_size": pl.Int64,
    "attributes": pl.Utf8,
    "gross_weight_share": pl.Float64,
    "gross_sku_count": pl.Int64,
    "gross_sku_share": pl.Float64,
    "density_index": pl.Float64,
    "gross_brand_count": pl.Int64,
    "top_brand_weight_share": pl.Float64,
    "brand_hhi": pl.Float64,
    "top_products": pl.Utf8,
    "top_brands": pl.Utf8,
}

PRODUCT_ASSIGNMENTS_SCHEMA = {
    "alpha": pl.Float64,
    "shelf_rank": pl.Int64,
    "bundle_key": pl.Utf8,
    "product_id": pl.Utf8,
    "rank": pl.Float64,
    "product_weight": pl.Float64,
}

ROBUSTNESS_BASE_SCHEMA = {
    "bundle_key": pl.Utf8,
    "times_selected": pl.Int64,
    "best_shelf_rank": pl.Int64,
    "average_shelf_rank": pl.Float64,
    "average_gross_weight_share": pl.Float64,
    "average_incremental_weight_share": pl.Float64,
    "average_density_index": pl.Float64,
}

THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA = {
    "alpha": pl.Float64,
    "base_shelf_rank": pl.Int64,
    "base_bundle_key": pl.Utf8,
    "refinement_rank": pl.Int64,
    "refinement_bundle_key": pl.Utf8,
    "third_attribute": pl.Utf8,
    "full_category_weight_share": pl.Float64,
    "base_shelf_weight_share": pl.Float64,
    "full_category_sku_share": pl.Float64,
    "base_shelf_sku_share": pl.Float64,
    "density_index": pl.Float64,
    "refinement_sku_count": pl.Int64,
    "refinement_brand_count": pl.Int64,
    "top_brand_weight_share": pl.Float64,
    "brand_hhi": pl.Float64,
    "top_products": pl.Utf8,
    "top_brands": pl.Utf8,
}


def _columns(df: pl.DataFrame) -> list[str]:
    columns, _schema = get_schema_and_column_names(df)
    return columns


def _empty_frame(schema: Mapping[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(schema=dict(schema))


def _alpha_column_name(alpha: float) -> str:
    suffix = f"{alpha:g}".replace("-", "neg_").replace(".", "_")
    return f"selected_under_alpha_{suffix}"


def _robustness_schema(alphas: Sequence[float]) -> dict[str, pl.DataType]:
    schema = dict(ROBUSTNESS_BASE_SCHEMA)
    for alpha in alphas:
        schema[_alpha_column_name(float(alpha))] = pl.Boolean
    return schema


def _meaningful_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.casefold() in PLACEHOLDER_VALUES:
        return None
    return " ".join(text.split())


def _dimension_key(value: Any) -> str | None:
    text = _meaningful_text(value)
    if not text:
        return None
    return text.replace("_", " ").casefold()


def _dimension_label(value: Any) -> str | None:
    key = _dimension_key(value)
    return key


def _value_label(value: Any) -> str | None:
    text = _meaningful_text(value)
    if not text:
        return None
    return text.casefold()


def _token(dimension: Any, value: Any) -> str | None:
    dim = _dimension_label(dimension)
    val = _value_label(value)
    if not dim or not val:
        return None
    return f"{dim}={val}"


def _token_dimension(token: str) -> str:
    return token.split("=", 1)[0]


def _split_list_text(value: str) -> list[str]:
    if CSV_LIST_SEPARATOR in value:
        return [part.strip() for part in value.split(CSV_LIST_SEPARATOR)]
    return [value.strip()]


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split_list_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out: list[Any] = []
        for item in value:
            out.extend(_iter_values(item))
        return out
    return [value]


def _parse_atomic_token(value: Any) -> str | None:
    text = _meaningful_text(value)
    if not text or "=" not in text:
        return None
    dimension, atomic_value = text.split("=", 1)
    return _token(dimension, atomic_value)


def _filterable_keys(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        keys: set[str] = set()
        for raw_key, raw_allowed in value.items():
            if not raw_allowed:
                continue
            token = _parse_atomic_token(raw_key)
            if token:
                keys.add(token)
            dimension = _dimension_key(raw_key)
            if dimension:
                keys.add(dimension)
        return keys
    keys = set()
    for item in _iter_values(value):
        token = _parse_atomic_token(item)
        if token:
            keys.add(token)
        dimension = _dimension_key(item)
        if dimension:
            keys.add(dimension)
    return keys


def normalize_attribute_tokens(
    attributes: Any,
    *,
    exclude_dimensions: Sequence[str] = ("brand",),
    filterable_attributes: Any = None,
    include_only_filterable: bool = True,
) -> tuple[str, ...]:
    """Normalize a product's attributes into stable ``dimension=value`` tokens."""

    excluded = {
        key
        for value in exclude_dimensions
        if (key := _dimension_key(value)) is not None
    }
    filterable = _filterable_keys(filterable_attributes)
    tokens: set[str] = set()
    if isinstance(attributes, Mapping):
        for raw_dimension, raw_values in attributes.items():
            dimension = _dimension_key(raw_dimension)
            if not dimension or dimension in excluded:
                continue
            for raw_value in _iter_values(raw_values):
                token = _token(dimension, raw_value)
                if token:
                    tokens.add(token)
    else:
        for raw_value in _iter_values(attributes):
            token = _parse_atomic_token(raw_value)
            if not token:
                continue
            dimension = _token_dimension(token)
            if dimension in excluded:
                continue
            tokens.add(token)

    if include_only_filterable and filterable:
        tokens = {
            token
            for token in tokens
            if token in filterable or _token_dimension(token) in filterable
        }
    return tuple(sorted(tokens, key=lambda token: (_token_dimension(token), token)))


def _row_tokens_from_columns(
    row: Mapping[str, Any],
    *,
    attribute_columns: Sequence[str],
    exclude_dimensions: Sequence[str],
) -> tuple[str, ...]:
    attributes: dict[str, list[Any]] = {}
    for column in attribute_columns:
        values = _iter_values(row.get(column))
        if values:
            attributes[column] = values
    return normalize_attribute_tokens(
        attributes,
        exclude_dimensions=exclude_dimensions,
        include_only_filterable=False,
    )


def _numeric_rank(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        rank = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rank) or rank <= 0:
        return None
    return rank


def _prepare_product_records(
    df: pl.DataFrame,
    *,
    product_id_col: str,
    rank_col: str,
    attributes_col: str | None,
    attribute_columns: Sequence[str] | None,
    brand_col: str | None,
    product_name_col: str | None,
    filterable_col: str | None,
    exclude_dimensions: Sequence[str],
    include_only_filterable: bool,
) -> list[dict[str, Any]]:
    columns = _columns(df)
    required = [product_id_col, rank_col]
    if attributes_col is None and not attribute_columns:
        raise ValueError("Either attributes_col or attribute_columns must be provided.")
    if attributes_col is not None:
        required.append(attributes_col)
    if brand_col is not None:
        required.append(brand_col)
    if product_name_col is not None:
        required.append(product_name_col)
    if filterable_col is not None:
        required.append(filterable_col)
    missing = [column for column in required if column not in columns]
    if missing:
        raise ValueError(f"Missing required web shelf columns: {', '.join(missing)}")

    seen_product_ids: set[str] = set()
    invalid_rank_ids: list[str] = []
    records: list[dict[str, Any]] = []
    for row in df.to_dicts():
        product_id = _meaningful_text(row.get(product_id_col))
        if not product_id:
            continue
        if product_id in seen_product_ids:
            raise ValueError(f"Duplicate product_id in web shelf input: {product_id}")
        seen_product_ids.add(product_id)
        rank = _numeric_rank(row.get(rank_col))
        if rank is None:
            invalid_rank_ids.append(product_id)
            continue
        if attribute_columns is not None:
            tokens = _row_tokens_from_columns(
                row,
                attribute_columns=attribute_columns,
                exclude_dimensions=exclude_dimensions,
            )
        else:
            tokens = normalize_attribute_tokens(
                row.get(attributes_col),
                exclude_dimensions=exclude_dimensions,
                filterable_attributes=(
                    row.get(filterable_col) if filterable_col else None
                ),
                include_only_filterable=include_only_filterable,
            )
        records.append(
            {
                "product_id": product_id,
                "rank": rank,
                "brand": _meaningful_text(row.get(brand_col)) if brand_col else None,
                "product_name": (
                    _meaningful_text(row.get(product_name_col))
                    if product_name_col
                    else None
                ),
                "tokens": tokens,
            }
        )
    if invalid_rank_ids:
        sample = ", ".join(invalid_rank_ids[:5])
        raise ValueError(
            "Web shelf discovery requires positive numeric ranks. "
            f"Invalid products: {sample}"
        )
    return records


def _product_weights(
    records: Sequence[Mapping[str, Any]],
    *,
    alpha: float,
) -> dict[str, float]:
    raw_weights = {
        str(record["product_id"]): float(record["rank"]) ** (-float(alpha))
        for record in records
    }
    total = sum(raw_weights.values())
    if total <= 0:
        return {product_id: 0.0 for product_id in raw_weights}
    return {
        product_id: raw_weight / total for product_id, raw_weight in raw_weights.items()
    }


def _bundle_key(tokens: Sequence[str]) -> str:
    return " + ".join(
        sorted(tokens, key=lambda token: (_token_dimension(token), token))
    )


def _valid_bundle_combinations(
    tokens: Sequence[str], bundle_size: int
) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for combo in combinations(tokens, bundle_size):
        dimensions = {_token_dimension(token) for token in combo}
        if len(dimensions) != bundle_size:
            continue
        out.append(
            tuple(sorted(combo, key=lambda token: (_token_dimension(token), token)))
        )
    return out


def _top_products(
    product_ids: set[str],
    *,
    record_by_id: Mapping[str, Mapping[str, Any]],
    limit: int = 5,
) -> str | None:
    ranked = sorted(
        (record_by_id[product_id] for product_id in product_ids),
        key=lambda record: (float(record["rank"]), str(record["product_id"])),
    )
    labels = []
    for record in ranked[:limit]:
        label = record.get("product_name") or record["product_id"]
        labels.append(f"{label} (#{int(float(record['rank']))})")
    return CSV_LIST_SEPARATOR.join(labels) if labels else None


def _brand_metrics(
    product_ids: set[str],
    *,
    record_by_id: Mapping[str, Mapping[str, Any]],
    weights: Mapping[str, float],
    limit: int = 5,
) -> dict[str, Any]:
    brand_weights: dict[str, float] = defaultdict(float)
    for product_id in product_ids:
        brand = _meaningful_text(record_by_id[product_id].get("brand"))
        if brand:
            brand_weights[brand] += float(weights.get(product_id, 0.0))
    total = sum(brand_weights.values())
    if total <= 0:
        return {
            "brand_count": 0,
            "top_brand_weight_share": None,
            "brand_hhi": None,
            "top_brands": None,
        }
    ranked = sorted(
        brand_weights.items(), key=lambda item: (-item[1], item[0].casefold())
    )
    shares = [weight / total for _brand, weight in ranked]
    top_labels = [
        f"{brand} ({share:.1%})"
        for (brand, _weight), share in zip(ranked[:limit], shares[:limit])
    ]
    return {
        "brand_count": len(brand_weights),
        "top_brand_weight_share": shares[0] if shares else None,
        "brand_hhi": sum(share * share for share in shares),
        "top_brands": CSV_LIST_SEPARATOR.join(top_labels) if top_labels else None,
    }


def _build_candidate_payloads(
    records: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, float],
    alpha: float,
    bundle_size: int,
    min_skus: int,
    min_brands: int,
    brand_filter_enabled: bool,
) -> list[dict[str, Any]]:
    record_by_id = {str(record["product_id"]): record for record in records}
    product_count = len(records)
    candidate_products: dict[str, set[str]] = defaultdict(set)
    candidate_tokens: dict[str, tuple[str, ...]] = {}

    for record in records:
        product_id = str(record["product_id"])
        tokens = tuple(record.get("tokens") or ())
        for combo in _valid_bundle_combinations(tokens, bundle_size):
            key = _bundle_key(combo)
            candidate_tokens[key] = combo
            candidate_products[key].add(product_id)

    payloads: list[dict[str, Any]] = []
    for key, product_ids in candidate_products.items():
        gross_sku_count = len(product_ids)
        if gross_sku_count < min_skus:
            continue
        brand_metrics = _brand_metrics(
            product_ids,
            record_by_id=record_by_id,
            weights=weights,
        )
        gross_brand_count = int(brand_metrics["brand_count"])
        if brand_filter_enabled and gross_brand_count < min_brands:
            continue
        gross_weight_share = sum(
            float(weights[product_id]) for product_id in product_ids
        )
        gross_sku_share = gross_sku_count / product_count if product_count > 0 else None
        density_index = (
            gross_weight_share / gross_sku_share
            if gross_sku_share is not None and gross_sku_share > 0
            else None
        )
        payloads.append(
            {
                "product_ids": product_ids,
                "tokens": candidate_tokens[key],
                "row": {
                    "alpha": float(alpha),
                    "bundle_key": key,
                    "bundle_size": int(bundle_size),
                    "attributes": CSV_LIST_SEPARATOR.join(candidate_tokens[key]),
                    "gross_weight_share": gross_weight_share,
                    "gross_sku_count": gross_sku_count,
                    "gross_sku_share": gross_sku_share,
                    "density_index": density_index,
                    "gross_brand_count": gross_brand_count,
                    "top_brand_weight_share": brand_metrics["top_brand_weight_share"],
                    "brand_hhi": brand_metrics["brand_hhi"],
                    "top_products": _top_products(
                        product_ids,
                        record_by_id=record_by_id,
                    ),
                    "top_brands": brand_metrics["top_brands"],
                },
            }
        )

    return sorted(
        payloads,
        key=lambda payload: (
            -float(payload["row"]["gross_weight_share"] or 0.0),
            -float(payload["row"]["density_index"] or 0.0),
            -int(payload["row"]["gross_sku_count"] or 0),
            str(payload["row"]["bundle_key"]),
        ),
    )


def _incremental_payload(
    product_ids: set[str],
    *,
    record_by_id: Mapping[str, Mapping[str, Any]],
    weights: Mapping[str, float],
    product_count: int,
) -> dict[str, Any]:
    incremental_sku_count = len(product_ids)
    incremental_sku_share = (
        incremental_sku_count / product_count if product_count > 0 else None
    )
    incremental_weight_share = sum(
        float(weights[product_id]) for product_id in product_ids
    )
    brand_metrics = _brand_metrics(
        product_ids,
        record_by_id=record_by_id,
        weights=weights,
    )
    return {
        "incremental_weight_share": incremental_weight_share,
        "incremental_sku_count": incremental_sku_count,
        "incremental_sku_share": incremental_sku_share,
        "incremental_brand_count": int(brand_metrics["brand_count"]),
        "top_products": _top_products(product_ids, record_by_id=record_by_id),
        "top_brands": brand_metrics["top_brands"],
        "top_brand_weight_share": brand_metrics["top_brand_weight_share"],
        "brand_hhi": brand_metrics["brand_hhi"],
    }


def _run_greedy_selection(
    records: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, float],
    alpha: float,
    candidates: Sequence[Mapping[str, Any]],
    max_selected_shelves: int,
    min_skus: int,
    min_brands: int,
    brand_filter_enabled: bool,
    target_coverage: float,
    min_incremental_weight_share: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    record_by_id = {str(record["product_id"]): record for record in records}
    product_count = len(records)
    uncovered = set(record_by_id)
    selected_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    cumulative_weight_share = 0.0
    shelf_rank = 1

    while (
        shelf_rank <= max_selected_shelves
        and uncovered
        and cumulative_weight_share < target_coverage
    ):
        options: list[dict[str, Any]] = []
        for candidate in candidates:
            incremental_ids = set(candidate["product_ids"]).intersection(uncovered)
            incremental = _incremental_payload(
                incremental_ids,
                record_by_id=record_by_id,
                weights=weights,
                product_count=product_count,
            )
            if incremental["incremental_sku_count"] < min_skus:
                continue
            if (
                brand_filter_enabled
                and incremental["incremental_brand_count"] < min_brands
            ):
                continue
            if incremental["incremental_weight_share"] < min_incremental_weight_share:
                continue
            options.append(
                {
                    "candidate": candidate,
                    "product_ids": incremental_ids,
                    "incremental": incremental,
                }
            )
        if not options:
            break
        options.sort(
            key=lambda option: (
                -float(option["incremental"]["incremental_weight_share"] or 0.0),
                -float(option["candidate"]["row"]["gross_weight_share"] or 0.0),
                -float(option["candidate"]["row"]["density_index"] or 0.0),
                -int(option["incremental"]["incremental_sku_count"] or 0),
                str(option["candidate"]["row"]["bundle_key"]),
            )
        )
        selected = options[0]
        candidate_row = dict(selected["candidate"]["row"])
        incremental = selected["incremental"]
        cumulative_weight_share += float(incremental["incremental_weight_share"] or 0.0)
        selected_rows.append(
            {
                "alpha": float(alpha),
                "shelf_rank": shelf_rank,
                "bundle_key": candidate_row["bundle_key"],
                "bundle_size": candidate_row["bundle_size"],
                "attributes": candidate_row["attributes"],
                "gross_weight_share": candidate_row["gross_weight_share"],
                "incremental_weight_share": incremental["incremental_weight_share"],
                "cumulative_weight_share": min(cumulative_weight_share, 1.0),
                "gross_sku_count": candidate_row["gross_sku_count"],
                "incremental_sku_count": incremental["incremental_sku_count"],
                "gross_sku_share": candidate_row["gross_sku_share"],
                "incremental_sku_share": incremental["incremental_sku_share"],
                "density_index": candidate_row["density_index"],
                "gross_brand_count": candidate_row["gross_brand_count"],
                "incremental_brand_count": incremental["incremental_brand_count"],
                "top_brand_weight_share": incremental["top_brand_weight_share"],
                "brand_hhi": incremental["brand_hhi"],
                "top_products": incremental["top_products"],
                "top_brands": incremental["top_brands"],
            }
        )
        for product_id in sorted(
            selected["product_ids"],
            key=lambda value: (float(record_by_id[value]["rank"]), value),
        ):
            assignment_rows.append(
                {
                    "alpha": float(alpha),
                    "shelf_rank": shelf_rank,
                    "bundle_key": candidate_row["bundle_key"],
                    "product_id": product_id,
                    "rank": float(record_by_id[product_id]["rank"]),
                    "product_weight": float(weights[product_id]),
                }
            )
        uncovered.difference_update(selected["product_ids"])
        shelf_rank += 1

    if uncovered:
        residual = _incremental_payload(
            uncovered,
            record_by_id=record_by_id,
            weights=weights,
            product_count=product_count,
        )
        residual_weight = float(residual["incremental_weight_share"] or 0.0)
        residual_sku_share = residual["incremental_sku_share"]
        cumulative_weight_share += residual_weight
        selected_rows.append(
            {
                "alpha": float(alpha),
                "shelf_rank": shelf_rank,
                "bundle_key": RESIDUAL_BUNDLE_KEY,
                "bundle_size": 0,
                "attributes": None,
                "gross_weight_share": residual_weight,
                "incremental_weight_share": residual_weight,
                "cumulative_weight_share": min(cumulative_weight_share, 1.0),
                "gross_sku_count": residual["incremental_sku_count"],
                "incremental_sku_count": residual["incremental_sku_count"],
                "gross_sku_share": residual_sku_share,
                "incremental_sku_share": residual_sku_share,
                "density_index": (
                    residual_weight / residual_sku_share
                    if residual_sku_share and residual_sku_share > 0
                    else None
                ),
                "gross_brand_count": residual["incremental_brand_count"],
                "incremental_brand_count": residual["incremental_brand_count"],
                "top_brand_weight_share": residual["top_brand_weight_share"],
                "brand_hhi": residual["brand_hhi"],
                "top_products": residual["top_products"],
                "top_brands": residual["top_brands"],
            }
        )
        for product_id in sorted(
            uncovered,
            key=lambda value: (float(record_by_id[value]["rank"]), value),
        ):
            assignment_rows.append(
                {
                    "alpha": float(alpha),
                    "shelf_rank": shelf_rank,
                    "bundle_key": RESIDUAL_BUNDLE_KEY,
                    "product_id": product_id,
                    "rank": float(record_by_id[product_id]["rank"]),
                    "product_weight": float(weights[product_id]),
                }
            )
    return selected_rows, assignment_rows


def _build_robustness_summary(
    selected_shelves: pl.DataFrame,
    *,
    alphas: Sequence[float],
) -> pl.DataFrame:
    schema = _robustness_schema(alphas)
    if get_row_count(selected_shelves) == 0:
        return _empty_frame(schema)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected_shelves.filter(
        pl.col("bundle_key") != RESIDUAL_BUNDLE_KEY
    ).to_dicts():
        grouped[str(row["bundle_key"])].append(row)
    if not grouped:
        return _empty_frame(schema)

    rows: list[dict[str, Any]] = []
    for bundle_key, bundle_rows in grouped.items():
        selected_alphas = {float(row["alpha"]) for row in bundle_rows}
        shelf_ranks = [float(row["shelf_rank"]) for row in bundle_rows]
        gross_weights = [float(row["gross_weight_share"]) for row in bundle_rows]
        incremental_weights = [
            float(row["incremental_weight_share"]) for row in bundle_rows
        ]
        density_values = [
            float(row["density_index"])
            for row in bundle_rows
            if row.get("density_index") is not None
        ]
        out = {
            "bundle_key": bundle_key,
            "times_selected": len(bundle_rows),
            "best_shelf_rank": int(min(shelf_ranks)),
            "average_shelf_rank": sum(shelf_ranks) / len(shelf_ranks),
            "average_gross_weight_share": sum(gross_weights) / len(gross_weights),
            "average_incremental_weight_share": sum(incremental_weights)
            / len(incremental_weights),
            "average_density_index": (
                sum(density_values) / len(density_values) if density_values else None
            ),
        }
        for alpha in alphas:
            out[_alpha_column_name(float(alpha))] = float(alpha) in selected_alphas
        rows.append(out)
    return pl.DataFrame(rows, schema=schema).sort(
        ["times_selected", "best_shelf_rank", "average_incremental_weight_share"],
        descending=[True, False, True],
    )


def discover_web_shelves(
    df: pl.DataFrame,
    *,
    product_id_col: str = "product_id",
    rank_col: str = "rank",
    attributes_col: str | None = "attributes",
    attribute_columns: Sequence[str] | None = None,
    brand_col: str | None = "brand",
    product_name_col: str | None = "product_name",
    filterable_col: str | None = None,
    alphas: Sequence[float] = DEFAULT_ALPHAS,
    bundle_size: int = 2,
    max_selected_shelves: int = 100,
    min_skus: int = 5,
    min_brands: int = 2,
    exclude_dimensions: Sequence[str] = ("brand",),
    target_coverage: float = 1.0,
    min_incremental_weight_share: float = 0.0,
    include_only_filterable: bool = True,
) -> dict[str, pl.DataFrame]:
    """Discover rank-weighted web-shelf lanes from product attribute bundles."""

    if bundle_size < 2:
        raise ValueError("bundle_size must be at least 2.")
    if max_selected_shelves < 1:
        raise ValueError("max_selected_shelves must be at least 1.")
    if min_skus < 1:
        raise ValueError("min_skus must be at least 1.")
    if min_brands < 1:
        raise ValueError("min_brands must be at least 1.")
    if not 0 < target_coverage <= 1.0:
        raise ValueError("target_coverage must be greater than 0 and no more than 1.")

    columns = _columns(df)
    effective_brand_col = brand_col if brand_col in columns else None
    records = _prepare_product_records(
        df,
        product_id_col=product_id_col,
        rank_col=rank_col,
        attributes_col=attributes_col if attribute_columns is None else None,
        attribute_columns=attribute_columns,
        brand_col=effective_brand_col,
        product_name_col=product_name_col if product_name_col in columns else None,
        filterable_col=filterable_col if filterable_col in columns else None,
        exclude_dimensions=exclude_dimensions,
        include_only_filterable=include_only_filterable,
    )
    if not records:
        empty_robustness = _empty_frame(_robustness_schema(alphas))
        return {
            "selected_shelves": _empty_frame(SELECTED_SHELVES_SCHEMA),
            "candidate_shelves": _empty_frame(CANDIDATE_SHELVES_SCHEMA),
            "robustness_summary": empty_robustness,
            "product_shelf_assignments": _empty_frame(PRODUCT_ASSIGNMENTS_SCHEMA),
        }

    brand_filter_enabled = effective_brand_col is not None and any(
        record.get("brand") for record in records
    )
    candidate_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    for alpha in alphas:
        weights = _product_weights(records, alpha=float(alpha))
        candidates = _build_candidate_payloads(
            records,
            weights=weights,
            alpha=float(alpha),
            bundle_size=bundle_size,
            min_skus=min_skus,
            min_brands=min_brands,
            brand_filter_enabled=brand_filter_enabled,
        )
        candidate_rows.extend(dict(candidate["row"]) for candidate in candidates)
        alpha_selected, alpha_assignments = _run_greedy_selection(
            records,
            weights=weights,
            alpha=float(alpha),
            candidates=candidates,
            max_selected_shelves=max_selected_shelves,
            min_skus=min_skus,
            min_brands=min_brands,
            brand_filter_enabled=brand_filter_enabled,
            target_coverage=target_coverage,
            min_incremental_weight_share=min_incremental_weight_share,
        )
        selected_rows.extend(alpha_selected)
        assignment_rows.extend(alpha_assignments)

    selected_shelves = (
        pl.DataFrame(selected_rows, schema=SELECTED_SHELVES_SCHEMA)
        if selected_rows
        else _empty_frame(SELECTED_SHELVES_SCHEMA)
    )
    candidate_shelves = (
        pl.DataFrame(candidate_rows, schema=CANDIDATE_SHELVES_SCHEMA)
        if candidate_rows
        else _empty_frame(CANDIDATE_SHELVES_SCHEMA)
    )
    assignments = (
        pl.DataFrame(assignment_rows, schema=PRODUCT_ASSIGNMENTS_SCHEMA)
        if assignment_rows
        else _empty_frame(PRODUCT_ASSIGNMENTS_SCHEMA)
    )
    return {
        "selected_shelves": selected_shelves,
        "candidate_shelves": candidate_shelves,
        "robustness_summary": _build_robustness_summary(
            selected_shelves,
            alphas=alphas,
        ),
        "product_shelf_assignments": assignments,
    }


def empty_web_shelf_outputs(
    alphas: Sequence[float] = DEFAULT_ALPHAS,
) -> dict[str, pl.DataFrame]:
    """Return empty web-shelf output frames with stable schemas."""

    return {
        "selected_shelves": _empty_frame(SELECTED_SHELVES_SCHEMA),
        "candidate_shelves": _empty_frame(CANDIDATE_SHELVES_SCHEMA),
        "robustness_summary": _empty_frame(_robustness_schema(alphas)),
        "product_shelf_assignments": _empty_frame(PRODUCT_ASSIGNMENTS_SCHEMA),
    }


def _parse_bundle_tokens(bundle: Any) -> tuple[str, ...]:
    if isinstance(bundle, Mapping):
        return normalize_attribute_tokens(bundle, include_only_filterable=False)
    if isinstance(bundle, str):
        return normalize_attribute_tokens(
            [part.strip() for part in bundle.split("+")],
            include_only_filterable=False,
        )
    return normalize_attribute_tokens(bundle, include_only_filterable=False)


def refine_shelf_with_third_attribute(
    df: pl.DataFrame,
    base_bundle: Any,
    *,
    product_id_col: str = "product_id",
    rank_col: str = "rank",
    attributes_col: str | None = "attributes",
    attribute_columns: Sequence[str] | None = None,
    brand_col: str | None = "brand",
    product_name_col: str | None = "product_name",
    filterable_col: str | None = None,
    alpha: float = 1.0,
    min_skus: int = 2,
    min_brands: int = 1,
    max_refinements: int = 20,
    exclude_dimensions: Sequence[str] = ("brand",),
    include_only_filterable: bool = True,
    base_shelf_rank: int | None = None,
) -> pl.DataFrame:
    """Return the strongest third-attribute refinements within a base shelf."""

    base_tokens = _parse_bundle_tokens(base_bundle)
    if len(base_tokens) != 2:
        raise ValueError("base_bundle must contain exactly two attributes.")
    base_dimensions = {_token_dimension(token) for token in base_tokens}
    if len(base_dimensions) != 2:
        raise ValueError("base_bundle cannot contain two values from one dimension.")

    columns = _columns(df)
    effective_brand_col = brand_col if brand_col in columns else None
    records = _prepare_product_records(
        df,
        product_id_col=product_id_col,
        rank_col=rank_col,
        attributes_col=attributes_col if attribute_columns is None else None,
        attribute_columns=attribute_columns,
        brand_col=effective_brand_col,
        product_name_col=product_name_col if product_name_col in columns else None,
        filterable_col=filterable_col if filterable_col in columns else None,
        exclude_dimensions=exclude_dimensions,
        include_only_filterable=include_only_filterable,
    )
    if not records:
        return _empty_frame(THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)

    record_by_id = {str(record["product_id"]): record for record in records}
    brand_filter_enabled = effective_brand_col is not None and any(
        record.get("brand") for record in records
    )
    weights = _product_weights(records, alpha=float(alpha))
    base_set = set(base_tokens)
    base_product_ids = {
        str(record["product_id"])
        for record in records
        if base_set.issubset(set(record.get("tokens") or ()))
    }
    if not base_product_ids:
        return _empty_frame(THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)
    base_weight = sum(float(weights[product_id]) for product_id in base_product_ids)
    third_products: dict[str, set[str]] = defaultdict(set)
    for product_id in base_product_ids:
        record_tokens = set(record_by_id[product_id].get("tokens") or ())
        for token in record_tokens:
            if token in base_set or _token_dimension(token) in base_dimensions:
                continue
            third_products[token].add(product_id)

    rows: list[dict[str, Any]] = []
    product_count = len(records)
    base_count = len(base_product_ids)
    for third_attribute, product_ids in third_products.items():
        if len(product_ids) < min_skus:
            continue
        brand_metrics = _brand_metrics(
            product_ids,
            record_by_id=record_by_id,
            weights=weights,
        )
        brand_count = int(brand_metrics["brand_count"])
        if brand_filter_enabled and brand_count < min_brands:
            continue
        full_weight_share = sum(
            float(weights[product_id]) for product_id in product_ids
        )
        base_weight_share = full_weight_share / base_weight if base_weight > 0 else None
        full_sku_share = len(product_ids) / product_count if product_count > 0 else None
        base_sku_share = len(product_ids) / base_count if base_count > 0 else None
        refinement_tokens = tuple(
            sorted(
                [*base_tokens, third_attribute],
                key=lambda token: (_token_dimension(token), token),
            )
        )
        rows.append(
            {
                "alpha": float(alpha),
                "base_shelf_rank": int(base_shelf_rank or 0),
                "base_bundle_key": _bundle_key(base_tokens),
                "refinement_rank": 0,
                "refinement_bundle_key": _bundle_key(refinement_tokens),
                "third_attribute": third_attribute,
                "full_category_weight_share": full_weight_share,
                "base_shelf_weight_share": base_weight_share,
                "full_category_sku_share": full_sku_share,
                "base_shelf_sku_share": base_sku_share,
                "density_index": (
                    base_weight_share / base_sku_share
                    if base_weight_share is not None
                    and base_sku_share is not None
                    and base_sku_share > 0
                    else None
                ),
                "refinement_sku_count": len(product_ids),
                "refinement_brand_count": brand_count,
                "top_brand_weight_share": brand_metrics["top_brand_weight_share"],
                "brand_hhi": brand_metrics["brand_hhi"],
                "top_products": _top_products(
                    product_ids,
                    record_by_id=record_by_id,
                ),
                "top_brands": brand_metrics["top_brands"],
            }
        )
    if not rows:
        return _empty_frame(THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)
    ranked = sorted(
        rows,
        key=lambda row: (
            -float(row["base_shelf_weight_share"] or 0.0),
            -float(row["full_category_weight_share"] or 0.0),
            -int(row["refinement_sku_count"] or 0),
            str(row["refinement_bundle_key"]),
        ),
    )[:max_refinements]
    for index, row in enumerate(ranked, start=1):
        row["refinement_rank"] = index
    return pl.DataFrame(ranked, schema=THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)


def refine_selected_shelves_with_third_attribute(
    df: pl.DataFrame,
    selected_shelves: pl.DataFrame,
    *,
    alpha: float = 1.0,
    max_base_shelves: int = 10,
    **kwargs: Any,
) -> pl.DataFrame:
    """Refine selected 2-attribute shelves with strongest third attributes."""

    if get_row_count(selected_shelves) == 0:
        return _empty_frame(THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)
    base_rows = (
        selected_shelves.filter(
            (pl.col("alpha") == float(alpha))
            & (pl.col("bundle_key") != RESIDUAL_BUNDLE_KEY)
            & (pl.col("bundle_size") == 2)
        )
        .sort("shelf_rank")
        .head(max_base_shelves)
        .to_dicts()
    )
    frames: list[pl.DataFrame] = []
    for row in base_rows:
        frames.append(
            refine_shelf_with_third_attribute(
                df,
                row["bundle_key"],
                alpha=alpha,
                base_shelf_rank=int(row["shelf_rank"]),
                **kwargs,
            )
        )
    frames = [frame for frame in frames if get_row_count(frame) > 0]
    if not frames:
        return _empty_frame(THIRD_ATTRIBUTE_REFINEMENTS_SCHEMA)
    return pl.concat(frames, how="diagonal_relaxed").sort(
        ["base_shelf_rank", "refinement_rank"]
    )
