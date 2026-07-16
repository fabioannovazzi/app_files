from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "PackageCalculationHelper",
    "PackageCalculationResult",
    "calculate_package_frames",
    "get_package_calculation_helpers",
]


_PRODUCT_MATRIX_FILE = "product_filter_matrix.csv"
_CALCULATION_SOURCE = _PRODUCT_MATRIX_FILE
_BUNDLE_FILES = (
    "top_seller_pairs.csv",
    "top_seller_triples.csv",
    "innovation_pairs.csv",
    "innovation_triples.csv",
)
_ATTRIBUTE_FILES = (
    "filter_comparison.csv",
    "mapped_attribute_comparison.csv",
    "resolved_core_comparison.csv",
    "top_seller_mapped_attribute_comparison.csv",
)
_NON_OBSERVED_VALUES = {
    "missing",
    "n/a",
    "na",
    "nan",
    "none",
    "not in taxonomy",
    "null",
    "unknown",
}


@dataclass(frozen=True, slots=True)
class PackageCalculationHelper:
    """Deterministic calculation helper registered for one package type."""

    helper_id: str
    package_type: str
    claim_family: str
    required_files: tuple[str, ...]
    output_files: tuple[str, ...]
    calculate: Callable[[Mapping[str, pl.DataFrame]], dict[str, pl.DataFrame]]


@dataclass(frozen=True, slots=True)
class PackageCalculationResult:
    """Recomputed frames plus a compact audit trail for a package."""

    frames: dict[str, pl.DataFrame]
    summaries: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _ProductValueIndex:
    """Fast lookup index over product-filter matrix values."""

    products: tuple[dict[str, Any], ...]
    columns: tuple[str, ...]
    exact: dict[str, dict[str, set[int]]]
    atoms: dict[str, dict[str, set[int]]]
    observed: dict[str, set[int]]
    recent: set[int]
    rest: set[int]
    top_seller: set[int]
    other: set[int]


def calculate_package_frames(
    package_type: str,
    frames: Mapping[str, pl.DataFrame],
) -> PackageCalculationResult:
    """Run registered calculation helpers for ``package_type``."""

    calculated_frames: dict[str, pl.DataFrame] = {}
    summaries: list[dict[str, Any]] = []
    for helper in get_package_calculation_helpers(package_type):
        missing_files = [
            file_name
            for file_name in helper.required_files
            if _frame_is_empty(frames.get(file_name))
        ]
        if missing_files:
            summaries.append(
                {
                    "helper_id": helper.helper_id,
                    "claim_family": helper.claim_family,
                    "status": "skipped",
                    "reason": "missing required files",
                    "missing_files": missing_files,
                    "output_files": list(helper.output_files),
                    "row_count": 0,
                }
            )
            continue

        helper_frames = helper.calculate(frames)
        row_count = sum(get_row_count(frame) for frame in helper_frames.values())
        calculated_frames.update(helper_frames)
        summaries.append(
            {
                "helper_id": helper.helper_id,
                "claim_family": helper.claim_family,
                "status": "calculated" if helper_frames else "skipped",
                "reason": None if helper_frames else "no compatible source rows",
                "output_files": sorted(helper_frames),
                "row_count": row_count,
            }
        )
    return PackageCalculationResult(
        frames=calculated_frames,
        summaries=tuple(summaries),
    )


def get_package_calculation_helpers(
    package_type: str,
) -> tuple[PackageCalculationHelper, ...]:
    """Return deterministic helper registrations for ``package_type``."""

    if package_type != "launch":
        return ()
    return (
        PackageCalculationHelper(
            helper_id="launch.bundle_incidence.v1",
            package_type="launch",
            claim_family="bundle_metric",
            required_files=(_PRODUCT_MATRIX_FILE,),
            output_files=_BUNDLE_FILES,
            calculate=_calculate_launch_bundle_frames,
        ),
        PackageCalculationHelper(
            helper_id="launch.attribute_incidence.v1",
            package_type="launch",
            claim_family="attribute_metric",
            required_files=(_PRODUCT_MATRIX_FILE,),
            output_files=_ATTRIBUTE_FILES,
            calculate=_calculate_launch_attribute_frames,
        ),
        PackageCalculationHelper(
            helper_id="launch.brand_share.v1",
            package_type="launch",
            claim_family="brand_share",
            required_files=(_PRODUCT_MATRIX_FILE,),
            output_files=("top_seller_brand_comparison.csv",),
            calculate=_calculate_launch_brand_frames,
        ),
    )


def _calculate_launch_bundle_frames(
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    product_df = frames[_PRODUCT_MATRIX_FILE]
    product_index = _build_product_value_index(
        product_df,
        _bundle_index_columns(product_df, frames),
    )
    family_column_cache: dict[str, tuple[str, ...]] = {}
    output: dict[str, pl.DataFrame] = {}
    for file_name in _BUNDLE_FILES:
        source_df = frames.get(file_name, pl.DataFrame())
        if _frame_is_empty(source_df):
            continue
        source_rows = source_df.to_dicts()
        calculated_rows: list[dict[str, Any]] = []
        replaced_count = 0
        for row in source_rows:
            calculated = _calculate_bundle_row(
                row,
                product_index=product_index,
                file_name=file_name,
                family_column_cache=family_column_cache,
            )
            if calculated is None:
                calculated_rows.append(row)
                continue
            replaced_count += 1
            calculated_rows.append(calculated)
        if replaced_count:
            output[file_name] = pl.DataFrame(calculated_rows)
    return output


def _calculate_launch_attribute_frames(
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    product_df = frames[_PRODUCT_MATRIX_FILE]
    product_index = _build_product_value_index(
        product_df,
        _attribute_index_columns(product_df, frames),
    )
    attribute_column_cache: dict[str, str | None] = {}
    output: dict[str, pl.DataFrame] = {}
    for file_name in _ATTRIBUTE_FILES:
        source_df = frames.get(file_name, pl.DataFrame())
        if _frame_is_empty(source_df):
            continue
        calculated_rows: list[dict[str, Any]] = []
        replaced_count = 0
        for row in source_df.to_dicts():
            calculated = _calculate_attribute_row(
                row,
                product_index=product_index,
                file_name=file_name,
                attribute_column_cache=attribute_column_cache,
            )
            if calculated is None:
                calculated_rows.append(row)
                continue
            replaced_count += 1
            calculated_rows.append(calculated)
        if replaced_count:
            output[file_name] = pl.DataFrame(calculated_rows)
    return output


def _calculate_launch_brand_frames(
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    product_df = frames[_PRODUCT_MATRIX_FILE]
    source_df = frames.get("top_seller_brand_comparison.csv", pl.DataFrame())
    if _frame_is_empty(source_df):
        return {}

    product_index = _build_product_value_index(
        product_df,
        ("brand", "top_seller_status", "pareto_bucket"),
    )
    products = list(product_index.products)
    brand_rows = [row for row in products if _clean_text(row.get("brand"))]
    top_seller_rows = [
        row for row in brand_rows if _is_top_seller_row(row, product_index)
    ]
    catalog_base = len(brand_rows)
    top_seller_base = len(top_seller_rows)

    calculated_rows: list[dict[str, Any]] = []
    replaced_count = 0
    for row in source_df.to_dicts():
        brand = _clean_text(row.get("brand"))
        if not brand:
            calculated_rows.append(row)
            continue
        brand_key = _canonical_text(brand)
        brand_product_rows = [
            product
            for product in brand_rows
            if _canonical_text(product.get("brand")) == brand_key
        ]
        if not brand_product_rows:
            calculated_rows.append(row)
            continue
        top_count = sum(
            1
            for product in brand_product_rows
            if _is_top_seller_row(product, product_index)
        )
        catalog_count = len(brand_product_rows)
        other_count = catalog_count - top_count
        catalog_share = _safe_divide(catalog_count, catalog_base)
        top_seller_share_of_brand = _safe_divide(top_count, catalog_count)
        top_seller_share_of_cohort = _safe_divide(top_count, top_seller_base)
        over_index = _safe_divide(top_seller_share_of_cohort, catalog_share)
        calculated = {
            **row,
            "catalog_count": catalog_count,
            "top_seller_count": top_count,
            "other_count": other_count,
            "catalog_share": catalog_share,
            "top_seller_share_of_brand": top_seller_share_of_brand,
            "top_seller_share_of_cohort": top_seller_share_of_cohort,
            "over_index_vs_catalog_share": over_index,
        }
        calculated_rows.append(_mark_calculated(calculated, "launch.brand_share.v1"))
        replaced_count += 1

    if not replaced_count:
        return {}
    return {"top_seller_brand_comparison.csv": pl.DataFrame(calculated_rows)}


def _calculate_bundle_row(
    row: dict[str, Any],
    *,
    product_index: _ProductValueIndex,
    file_name: str,
    family_column_cache: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any] | None:
    bundle_key = _clean_text(row.get("bundle_key"))
    bundle_parts = _parse_bundle_key(bundle_key)
    if not bundle_parts:
        return None

    if file_name.startswith("top_seller_"):
        left_indices = product_index.top_seller
        right_indices = product_index.other
        left_prefix = "top_seller"
        right_prefix = "other"
        helper_id = "launch.bundle_incidence.v1"
    else:
        left_indices = product_index.recent
        right_indices = product_index.rest
        left_prefix = "recent"
        right_prefix = "rest"
        helper_id = "launch.bundle_incidence.v1"

    bundle_matchers = tuple(
        (
            _cached_bundle_family_columns(
                family,
                product_index,
                family_column_cache,
            ),
            value,
        )
        for family, value in bundle_parts
    )
    if any(not columns for columns, _value in bundle_matchers):
        return None

    matched_indices = _matching_bundle_indices(product_index, bundle_matchers)
    left_match_indices = matched_indices & left_indices
    right_match_indices = matched_indices & right_indices
    left_count = len(left_match_indices)
    right_count = len(right_match_indices)
    left_base = len(left_indices)
    right_base = len(right_indices)
    left_pct = _safe_divide(left_count, left_base)
    right_pct = _safe_divide(right_count, right_base)

    calculated = dict(row)
    calculated[f"count_{left_prefix}"] = left_count
    calculated[f"count_{right_prefix}"] = right_count
    calculated[f"{left_prefix}_base"] = left_base
    calculated[f"{right_prefix}_base"] = right_base
    calculated[f"pct_{left_prefix}"] = left_pct
    calculated[f"pct_{right_prefix}"] = right_pct
    calculated["delta"] = _delta(left_pct, right_pct)
    calculated["prevalence_ratio"] = _safe_divide(left_pct, right_pct)
    _add_bundle_descriptives(
        calculated,
        product_index=product_index,
        left_match_indices=left_match_indices,
        right_match_indices=right_match_indices,
        left_prefix=left_prefix,
        right_prefix=right_prefix,
    )
    return _mark_calculated(calculated, helper_id)


def _calculate_attribute_row(
    row: dict[str, Any],
    *,
    product_index: _ProductValueIndex,
    file_name: str,
    attribute_column_cache: dict[str, str | None] | None = None,
) -> dict[str, Any] | None:
    if file_name == "filter_comparison.csv":
        attribute_name = _clean_text(row.get("filter_family"))
        attribute_value = _clean_text(row.get("filter_value"))
        left_base_key = "recent_family_base"
        right_base_key = "rest_family_base"
    else:
        attribute_name = _clean_text(row.get("attribute_name"))
        attribute_value = _clean_text(row.get("attribute_value"))
        left_base_key = (
            "top_seller_base" if file_name.startswith("top_seller_") else "recent_base"
        )
        right_base_key = (
            "other_base" if file_name.startswith("top_seller_") else "rest_base"
        )
    if not attribute_name or not attribute_value:
        return None

    column_name = _cached_attribute_column(
        attribute_name,
        product_index,
        attribute_column_cache,
    )
    if column_name is None:
        return None

    if file_name.startswith("top_seller_"):
        left_indices = product_index.top_seller
        right_indices = product_index.other
        left_prefix = "top_seller"
        right_prefix = "other"
    else:
        left_indices = product_index.recent
        right_indices = product_index.rest
        left_prefix = "recent"
        right_prefix = "rest"

    observed_indices = product_index.observed.get(column_name, set())
    matched_indices = _matching_value_indices(
        product_index,
        column_name,
        attribute_value,
        include_atoms=file_name == "filter_comparison.csv",
    )
    left_base = len(left_indices & observed_indices)
    right_base = len(right_indices & observed_indices)
    left_count = len(left_indices & matched_indices)
    right_count = len(right_indices & matched_indices)
    left_pct = _safe_divide(left_count, left_base)
    right_pct = _safe_divide(right_count, right_base)

    calculated = dict(row)
    calculated[f"count_{left_prefix}"] = left_count
    calculated[f"count_{right_prefix}"] = right_count
    calculated[left_base_key] = left_base
    calculated[right_base_key] = right_base
    calculated[f"pct_{left_prefix}"] = left_pct
    calculated[f"pct_{right_prefix}"] = right_pct
    calculated["delta"] = _delta(left_pct, right_pct)
    calculated["calculation_column"] = column_name
    return _mark_calculated(calculated, "launch.attribute_incidence.v1")


def _add_bundle_descriptives(
    row: dict[str, Any],
    *,
    product_index: _ProductValueIndex,
    left_match_indices: set[int],
    right_match_indices: set[int],
    left_prefix: str,
    right_prefix: str,
) -> None:
    # The validator consumes counts, bases, percentages, ratios, and brand counts.
    # Preserve heavier display fields from the package CSV instead of rebuilding them
    # for every candidate row during validation.
    row[f"{left_prefix}_brand_count"] = _brand_count(product_index, left_match_indices)
    row[f"{right_prefix}_brand_count"] = _brand_count(
        product_index,
        right_match_indices,
    )
    left_dominant = _dominant_brand_stats(product_index, left_match_indices)
    right_dominant = _dominant_brand_stats(product_index, right_match_indices)
    for key, value in left_dominant.items():
        row[f"{left_prefix}_{key}"] = value
    for key, value in right_dominant.items():
        row[f"{right_prefix}_{key}"] = value


def _matching_bundle_indices(
    product_index: _ProductValueIndex,
    bundle_matchers: tuple[tuple[tuple[str, ...], str], ...],
) -> set[int]:
    matching_indices: set[int] | None = None
    for columns, value in bundle_matchers:
        value_indices: set[int] = set()
        for column_name in columns:
            value_indices.update(
                _matching_value_indices(product_index, column_name, value)
            )
        matching_indices = (
            value_indices
            if matching_indices is None
            else matching_indices & value_indices
        )
        if not matching_indices:
            return set()
    return matching_indices if matching_indices is not None else set()


def _matching_value_indices(
    product_index: _ProductValueIndex,
    column_name: str,
    value: str,
    *,
    include_atoms: bool = True,
) -> set[int]:
    canonical_value = _canonical_text(value)
    if not canonical_value:
        return set()
    exact_matches = product_index.exact.get(column_name, {}).get(
        canonical_value,
        set(),
    )
    if "|" in _clean_text(value):
        return set(exact_matches)
    if not include_atoms:
        return set(exact_matches)
    atom_matches = product_index.atoms.get(column_name, {}).get(canonical_value, set())
    return set(exact_matches) | set(atom_matches)


def _parse_bundle_key(bundle_key: str) -> tuple[tuple[str, str], ...]:
    if not bundle_key:
        return ()
    parts: list[tuple[str, str]] = []
    for raw_part in re.split(r"\s+\+\s+", bundle_key):
        if "=" not in raw_part:
            return ()
        family, value = raw_part.split("=", 1)
        family = _clean_text(family)
        value = _clean_text(value)
        if not family or not value:
            return ()
        parts.append((family, value))
    return tuple(parts)


def _bundle_index_columns(
    product_df: pl.DataFrame,
    frames: Mapping[str, pl.DataFrame],
) -> tuple[str, ...]:
    product_columns, _schema = get_schema_and_column_names(product_df)
    selected = set(_metadata_columns(product_columns))
    family_column_cache: dict[str, tuple[str, ...]] = {}
    for file_name in _BUNDLE_FILES:
        source_df = frames.get(file_name, pl.DataFrame())
        if _frame_is_empty(source_df):
            continue
        source_columns, _source_schema = get_schema_and_column_names(source_df)
        if "bundle_key" not in source_columns:
            continue
        for bundle_key in source_df.get_column("bundle_key").drop_nulls().to_list():
            for family, _value in _parse_bundle_key(_clean_text(bundle_key)):
                family_key = _canonical_text(family)
                if family_key not in family_column_cache:
                    family_column_cache[family_key] = (
                        _bundle_family_columns_from_columns(family, product_columns)
                    )
                selected.update(family_column_cache[family_key])
    return tuple(column for column in product_columns if column in selected)


def _attribute_index_columns(
    product_df: pl.DataFrame,
    frames: Mapping[str, pl.DataFrame],
) -> tuple[str, ...]:
    product_columns, _schema = get_schema_and_column_names(product_df)
    selected = set(_metadata_columns(product_columns))
    attribute_column_cache: dict[str, str | None] = {}
    for file_name in _ATTRIBUTE_FILES:
        source_df = frames.get(file_name, pl.DataFrame())
        if _frame_is_empty(source_df):
            continue
        source_columns, _source_schema = get_schema_and_column_names(source_df)
        if file_name == "filter_comparison.csv":
            name_column = "filter_family"
        else:
            name_column = "attribute_name"
        if name_column not in source_columns:
            continue
        for attribute_name in source_df.get_column(name_column).drop_nulls().to_list():
            cache_key = _canonical_text(attribute_name)
            if cache_key not in attribute_column_cache:
                attribute_column_cache[cache_key] = (
                    _resolve_attribute_column_from_columns(
                        _clean_text(attribute_name),
                        product_columns,
                    )
                )
            column_name = attribute_column_cache[cache_key]
            if column_name is not None:
                selected.add(column_name)
    return tuple(column for column in product_columns if column in selected)


def _metadata_columns(product_columns: list[str]) -> tuple[str, ...]:
    wanted = {
        "brand",
        "listing_status",
        "pareto_bucket",
        "pareto_rank",
        "product_name",
        "sales_share",
        "top_seller_status",
    }
    return tuple(column for column in product_columns if column in wanted)


def _bundle_family_columns(
    family: str,
    product_index: _ProductValueIndex,
) -> tuple[str, ...]:
    return _bundle_family_columns_from_columns(family, product_index.columns)


def _cached_bundle_family_columns(
    family: str,
    product_index: _ProductValueIndex,
    cache: dict[str, tuple[str, ...]] | None,
) -> tuple[str, ...]:
    key = _canonical_text(family)
    if cache is not None and key in cache:
        return cache[key]
    columns = _bundle_family_columns(family, product_index)
    if cache is not None:
        cache[key] = columns
    return columns


def _bundle_family_columns_from_columns(
    family: str,
    columns: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    normalized_columns: dict[str, list[str]] = {}
    for column in columns:
        normalized_columns.setdefault(_canonical_text(column), []).append(column)
    family_key = _canonical_text(family)
    direct_matches = normalized_columns.get(family_key, [])
    if direct_matches:
        return tuple(dict.fromkeys(direct_matches))

    candidate_columns = {
        "color": (
            "resolved_color",
            "mapped_color",
            "color lips",
            "color family",
            "shade family",
        ),
        "finish": ("resolved_finish", "mapped_finish", "finish", "finish_mapped"),
        "form": (
            "resolved_form",
            "mapped_form",
            "form",
            "product form",
            "product type",
            "resolved_format",
            "mapped_format",
            "format",
        ),
        "format": (
            "resolved_form",
            "mapped_form",
            "form",
            "product form",
            "product type",
            "resolved_format",
            "mapped_format",
            "format",
        ),
        "coverage": ("resolved_coverage", "mapped_coverage", "coverage"),
    }.get(family_key, (family,))

    # Use one semantic source for a bundle family. Unioning every alias
    # overcounts when raw, mapped, and resolved columns coexist.
    for column_name in candidate_columns:
        matches = normalized_columns.get(_canonical_text(column_name), [])
        if matches:
            return tuple(dict.fromkeys(matches))
    return ()


def _resolve_attribute_column(
    attribute_name: str,
    product_index: _ProductValueIndex,
) -> str | None:
    return _resolve_attribute_column_from_columns(attribute_name, product_index.columns)


def _cached_attribute_column(
    attribute_name: str,
    product_index: _ProductValueIndex,
    cache: dict[str, str | None] | None,
) -> str | None:
    key = _canonical_text(attribute_name)
    if cache is not None and key in cache:
        return cache[key]
    column_name = _resolve_attribute_column(attribute_name, product_index)
    if cache is not None:
        cache[key] = column_name
    return column_name


def _resolve_attribute_column_from_columns(
    attribute_name: str,
    columns: tuple[str, ...] | list[str],
) -> str | None:
    normalized_columns: dict[str, list[str]] = {}
    for column in columns:
        normalized_columns.setdefault(_canonical_text(column), []).append(column)
    direct = normalized_columns.get(_canonical_text(attribute_name), [])
    if direct:
        return direct[0]
    for column_name in _bundle_family_columns_from_columns(attribute_name, columns):
        return column_name
    return None


def _split_multi_value(value: str) -> tuple[str, ...]:
    return tuple(
        part.strip() for part in re.split(r"\s*\|\s*", value) if part and part.strip()
    )


def _has_observed_value(value: Any) -> bool:
    text = _clean_text(value)
    return bool(text) and text.casefold() not in _NON_OBSERVED_VALUES


def _build_product_value_index(
    product_df: pl.DataFrame,
    include_columns: tuple[str, ...],
) -> _ProductValueIndex:
    all_columns, _schema = get_schema_and_column_names(product_df)
    selected_columns = [
        column for column in all_columns if column in set(include_columns)
    ]
    products = tuple(product_df.select(selected_columns).to_dicts())
    columns = selected_columns
    exact: dict[str, dict[str, set[int]]] = {column: {} for column in columns}
    atoms: dict[str, dict[str, set[int]]] = {column: {} for column in columns}
    observed: dict[str, set[int]] = {column: set() for column in columns}
    recent: set[int] = set()
    rest: set[int] = set()
    top_seller: set[int] = set()
    other: set[int] = set()

    for row_index, row in enumerate(products):
        listing_status = _clean_text(row.get("listing_status")).casefold()
        if listing_status == "recent":
            recent.add(row_index)
        elif listing_status == "rest":
            rest.add(row_index)

        seller_status = _clean_text(row.get("top_seller_status")).casefold()
        if seller_status == "top_seller":
            top_seller.add(row_index)
        elif seller_status == "other":
            other.add(row_index)
        elif "pareto_bucket" in columns:
            if _clean_text(row.get("pareto_bucket")).casefold() == "a":
                top_seller.add(row_index)
            else:
                other.add(row_index)

        for column_name in columns:
            value = row.get(column_name)
            if not _has_observed_value(value):
                continue
            observed[column_name].add(row_index)
            canonical_full = _canonical_text(value)
            if canonical_full:
                exact[column_name].setdefault(canonical_full, set()).add(row_index)
            for part in _split_multi_value(_clean_text(value)):
                canonical_part = _canonical_text(part)
                if canonical_part:
                    atoms[column_name].setdefault(canonical_part, set()).add(row_index)

    return _ProductValueIndex(
        products=products,
        columns=tuple(columns),
        exact=exact,
        atoms=atoms,
        observed=observed,
        recent=recent,
        rest=rest,
        top_seller=top_seller,
        other=other,
    )


def _is_top_seller_row(
    row: dict[str, Any],
    product_index: _ProductValueIndex,
) -> bool:
    status = _clean_text(row.get("top_seller_status")).casefold()
    if status:
        return status == "top_seller"
    if "pareto_bucket" in product_index.columns:
        return _clean_text(row.get("pareto_bucket")).casefold() == "a"
    return False


def _frame_is_empty(frame: pl.DataFrame | None) -> bool:
    return frame is None or frame.is_empty()


def _mark_calculated(row: dict[str, Any], helper_id: str) -> dict[str, Any]:
    row["calculation_helper_id"] = helper_id
    row["calculation_source"] = _CALCULATION_SOURCE
    return row


def _brand_count(product_index: _ProductValueIndex, indices: set[int]) -> int:
    return len(
        {
            _canonical_text(product_index.products[index].get("brand"))
            for index in indices
            if _canonical_text(product_index.products[index].get("brand"))
        }
    )


def _dominant_brand_stats(
    product_index: _ProductValueIndex,
    indices: set[int],
) -> dict[str, Any]:
    canonical_to_display: dict[str, str] = {}
    brand_counts: dict[str, int] = {}
    for index in indices:
        brand = _clean_text(product_index.products[index].get("brand"))
        canonical_brand = _canonical_text(brand)
        if not canonical_brand:
            continue
        canonical_to_display.setdefault(canonical_brand, brand)
        brand_counts[canonical_brand] = brand_counts.get(canonical_brand, 0) + 1

    if not brand_counts:
        return {}

    dominant_count = max(brand_counts.values())
    dominant_brand_keys = sorted(
        key for key, count in brand_counts.items() if count == dominant_count
    )
    dominant_brand_key = dominant_brand_keys[0]
    return {
        "dominant_brand": canonical_to_display[dominant_brand_key],
        "dominant_brand_count": dominant_count,
        "dominant_brand_share": _safe_divide(dominant_count, len(indices)),
        "dominant_brand_tied": len(dominant_brand_keys) > 1,
    }


def _safe_divide(
    numerator: int | float | None, denominator: int | float | None
) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _canonical_text(value: Any) -> str:
    raw_text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", _clean_text(value))
    text = unicodedata.normalize("NFKD", raw_text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold())
    return re.sub(r"\s+", " ", text).strip()
