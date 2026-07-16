from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import polars as pl

from modules.add_attributes.attribute_taxonomy import get_attribute_activity
from modules.add_attributes.pdp_attribute_export import (
    get_attribute_cache_mtime,
    load_persisted_pdp_attributes,
)
from modules.pdp.postgres_compat import connect_pdp_database, pdp_database_exists
from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "AttributeFilterSetup",
    "PlaceholderValues",
    "load_review_tables",
    "refresh_review_cache",
    "list_retailers",
    "list_brands",
    "build_category_lookup",
    "category_options_for_tables",
    "filter_tables_by_retailer",
    "filter_tables_by_brands",
    "filter_tables_by_categories",
    "load_stage_attribute_table",
    "prepare_attribute_filters",
    "apply_attribute_filters",
    "compute_attribute_coverage_report",
    "ensure_record_identifiers",
    "normalize_category_key",
    "repair_text_encoding",
]


@dataclass(frozen=True)
class ReviewTables:
    parents: pl.DataFrame
    variants: pl.DataFrame
    combined: pl.DataFrame
    parents_all: pl.DataFrame


@dataclass(frozen=True)
class AttributeFilterSetup:
    placeholder_values: set[str]
    valid_attributes: list[dict[str, object]]
    attr_column_lookup: dict[str, str]
    attribute_filters: list[tuple[str, str, str]]
    allowed_attr_ids: set[str]
    filter_source: pl.DataFrame


PlaceholderValues = {
    "n/a",
    "na",
    "none",
    "unknown",
    "n/a (not stated)",
    "not in taxonomy",
    "-",
    "--",
}


_NOT_IN_TAXONOMY_PREFIX = "not in taxonomy"
_DETAIL_PLACEHOLDERS = PlaceholderValues | {"null"}


def _strip_wrapping_quotes(text: str) -> str:
    result = text.strip()
    while len(result) >= 2 and (
        (result[0] == result[-1] == '"') or (result[0] == result[-1] == "'")
    ):
        result = result[1:-1].strip()
    return result


def _extract_not_in_taxonomy_detail(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if not lowered.startswith(_NOT_IN_TAXONOMY_PREFIX):
        return None
    suffix = text[len(_NOT_IN_TAXONOMY_PREFIX) :].strip()
    if not suffix:
        return ""
    if suffix.startswith("(") and suffix.endswith(")") and len(suffix) > 2:
        detail = suffix[1:-1].strip()
    elif suffix.startswith(":") or suffix.startswith("-"):
        detail = suffix[1:].strip()
    else:
        detail = suffix.strip()
    return _strip_wrapping_quotes(detail)


def _is_placeholder_detail(detail: str | None) -> bool:
    if detail is None:
        return False
    lowered = detail.strip().lower()
    if not lowered:
        return True
    if lowered in _DETAIL_PLACEHOLDERS:
        return True
    return lowered.startswith(_NOT_IN_TAXONOMY_PREFIX)


def _is_not_in_taxonomy_value(value: object | None) -> bool:
    detail = _extract_not_in_taxonomy_detail(value)
    if detail is None:
        return False
    return not _is_placeholder_detail(detail)


def _is_not_in_taxonomy_placeholder_value(value: object | None) -> bool:
    detail = _extract_not_in_taxonomy_detail(value)
    if detail is None:
        return False
    return _is_placeholder_detail(detail)


def _not_in_taxonomy_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .map_elements(_is_not_in_taxonomy_value, return_dtype=pl.Boolean)
        .fill_null(False)
    )


def _not_in_taxonomy_placeholder_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .map_elements(_is_not_in_taxonomy_placeholder_value, return_dtype=pl.Boolean)
        .fill_null(False)
    )


ALLOWED_STAGE_TABLES = {
    "pdp_attributes_deterministic_explicit",
    "pdp_attributes_deterministic",
    "pdp_attributes_llm",
    "pdp_attribute_values",
}

STAGE_SOURCE_TABLES: tuple[str, str, str] = (
    "pdp_attributes_deterministic_explicit",
    "pdp_attributes_deterministic",
    "pdp_attributes_llm",
)


def repair_text_encoding(value: str) -> str:
    """Best-effort fix for UTF-8 text that was decoded as latin-1 (e.g., 'EstÃ©e')."""
    if not isinstance(value, str):
        return value
    candidate = value
    if "&" in candidate and ";" in candidate:
        candidate = html.unescape(candidate)
    if "Ã" in candidate or "Â" in candidate or "â" in candidate:
        try:
            candidate = candidate.encode("latin-1").decode("utf-8")
        except Exception:
            candidate = candidate
    if "\\u" in candidate:
        try:
            decoded = bytes(candidate, "utf-8").decode("unicode_escape")
            candidate = decoded or candidate
        except Exception:
            pass
    return candidate


def _clean_text_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Fix common encoding issues on user-facing text fields."""
    if df.is_empty():
        return df
    target_cols = [
        "brand",
        "product_name",
        "variant_description",
        "title_raw",
        "title_normalized",
        "brand_raw",
        "brand_normalized",
    ]
    exprs: list[pl.Expr] = []
    for col in target_cols:
        if col in df.columns:
            exprs.append(
                pl.col(col).cast(pl.Utf8).map_elements(repair_text_encoding).alias(col)
            )
    return df.with_columns(exprs) if exprs else df


def _stage_tables_signature(pdp_store_path: Path) -> tuple[tuple[str, int], ...]:
    path = Path(pdp_store_path)
    if not pdp_database_exists(path):
        return tuple()
    signatures: list[tuple[str, int]] = []
    with connect_pdp_database(path) as conn:
        for table in STAGE_SOURCE_TABLES:
            try:
                max_updated, row_count = conn.execute(
                    f"SELECT COALESCE(MAX(updated_at), ''), COUNT(*) FROM {table}"
                ).fetchone()
            except Exception:
                signatures.append(("", 0))
            else:
                signatures.append((str(max_updated or ""), int(row_count or 0)))
    return tuple(signatures)


def load_review_tables(pdp_store_path: Path) -> ReviewTables:
    (
        parents_df,
        variants_df,
        combined_df,
        _unmatched,
        parents_all_df,
        _unmatched_examples,
        _metadata,
    ) = load_persisted_pdp_attributes(pdp_store_path)
    parents_df = _clean_text_columns(parents_df)
    variants_df = _clean_text_columns(variants_df)
    combined_df = _clean_text_columns(combined_df)
    parents_all_df = _clean_text_columns(parents_all_df)
    return ReviewTables(
        parents=parents_df,
        variants=variants_df,
        combined=combined_df,
        parents_all=parents_all_df,
    )


def refresh_review_cache(pdp_store_path: Path, cache: dict | None) -> dict:
    current_mtime = get_attribute_cache_mtime(pdp_store_path)
    stage_signature = _stage_tables_signature(pdp_store_path)
    if (
        cache
        and cache.get("path") == str(pdp_store_path)
        and cache.get("mtime") == current_mtime
        and cache.get("stage_signature") == stage_signature
    ):
        return cache

    (
        parents_df,
        variants_df,
        combined_df,
        unmatched,
        parents_all_df,
        unmatched_examples,
        metadata,
    ) = load_persisted_pdp_attributes(pdp_store_path)
    return {
        "path": str(pdp_store_path),
        "mtime": current_mtime,
        "stage_signature": stage_signature,
        "parents": parents_df,
        "variants": variants_df,
        "combined": combined_df,
        "parents_all": parents_all_df,
        "unmatched": unmatched,
        "unmatched_examples": unmatched_examples,
        "metadata": metadata,
    }


def list_retailers(tables: ReviewTables) -> list[str]:
    retailer_values: set[str] = set()
    for frame in (tables.combined, tables.parents_all):
        if frame.is_empty() or "retailer" not in frame.columns:
            continue
        retailer_values.update(
            repair_text_encoding(str(value).strip())
            for value in frame.get_column("retailer").unique().to_list()
            if isinstance(value, str) and value.strip()
        )
    return sorted(retailer_values)


def list_brands(tables: ReviewTables) -> list[str]:
    brand_values: set[str] = set()
    for frame in (tables.combined, tables.parents, tables.variants, tables.parents_all):
        if frame.is_empty() or "brand" not in frame.columns:
            continue
        brand_values.update(
            repair_text_encoding(str(value).strip())
            for value in frame.get_column("brand").unique().to_list()
            if isinstance(value, str) and value.strip()
        )
    return sorted(brand_values)


def build_category_lookup(taxonomy: Mapping[str, object]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for cat in taxonomy.get("categories", []) or []:
        if not isinstance(cat, dict):
            continue
        cid = normalize_category_key(str(cat.get("id", "")))
        clabel = normalize_category_key(str(cat.get("label", "")))
        if cid:
            lookup[cid] = cat
        if clabel:
            lookup.setdefault(clabel, cat)
    return lookup


def category_options_for_tables(
    category_lookup: Mapping[str, dict],
    tables: ReviewTables,
) -> list[tuple[str, str]]:
    category_keys: set[str] = set()
    for df_source in (tables.combined, tables.parents):
        if df_source.is_empty() or "category_key" not in df_source.columns:
            continue
        for key in df_source.get_column("category_key").unique().to_list():
            if isinstance(key, str) and key and key in category_lookup:
                category_keys.add(key)
    available_keys = sorted(category_keys)
    options: list[tuple[str, str]] = []
    for key in available_keys:
        cat = category_lookup.get(key, {})
        label = str(cat.get("label") or cat.get("id") or key).strip()
        options.append((label, key))
    options.sort(key=lambda item: item[0].lower())
    return options


def filter_tables_by_retailer(
    tables: ReviewTables,
    retailer: str | Sequence[str] | None,
) -> ReviewTables:
    if retailer is None:
        return tables
    if isinstance(retailer, str):
        targets = {retailer}
    else:
        targets = {str(r) for r in retailer if isinstance(r, str)}
    if not targets:
        return tables

    def _apply(frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty() or "retailer" not in frame.columns:
            return frame
        return frame.filter(pl.col("retailer").is_in(list(targets)))

    return ReviewTables(
        parents=_apply(tables.parents),
        variants=_apply(tables.variants),
        combined=_apply(tables.combined),
        parents_all=_apply(tables.parents_all),
    )


def filter_tables_by_brands(
    tables: ReviewTables,
    brands: Sequence[str] | None,
) -> ReviewTables:
    if not brands:
        return tables
    normalized = {
        repair_text_encoding(str(brand).strip()).lower()
        for brand in brands
        if isinstance(brand, str) and str(brand).strip()
    }
    if not normalized:
        return tables

    brand_list = sorted(normalized)

    def _apply(frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty() or "brand" not in frame.columns:
            return frame
        return frame.filter(
            pl.col("brand")
            .cast(pl.Utf8)
            .map_elements(repair_text_encoding)
            .str.strip_chars()
            .str.to_lowercase()
            .is_in(brand_list)
        )

    return ReviewTables(
        parents=_apply(tables.parents),
        variants=_apply(tables.variants),
        combined=_apply(tables.combined),
        parents_all=_apply(tables.parents_all),
    )


def filter_tables_by_categories(
    tables: ReviewTables,
    selected_keys: Sequence[str],
) -> ReviewTables:
    if not selected_keys:
        empty_schema = tables.combined.schema
        empty = pl.DataFrame(schema=empty_schema)
        return ReviewTables(
            parents=empty, variants=empty, combined=empty, parents_all=empty
        )

    def _apply(frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty() or "category_key" not in frame.columns:
            return pl.DataFrame(schema=frame.schema)
        return frame.filter(pl.col("category_key").is_in(selected_keys))

    return ReviewTables(
        parents=_apply(tables.parents),
        variants=_apply(tables.variants),
        combined=_apply(tables.combined),
        parents_all=_apply(tables.parents_all),
    )


def load_stage_attribute_table(
    pdp_store_path: Path,
    table_name: str,
    retailer: str | None,
    parent_ids: Sequence[str],
    variant_ids: Sequence[str],
) -> pl.DataFrame:
    normalized_table = table_name.strip().lower()
    if normalized_table not in ALLOWED_STAGE_TABLES:
        raise ValueError(f"Unsupported attribute table '{table_name}'")

    parent_keys = [str(value).strip() for value in parent_ids if str(value).strip()]
    if not parent_keys:
        return pl.DataFrame()

    variant_keys = [str(value).strip() for value in variant_ids if str(value).strip()]

    conditions: list[str] = []
    params: list[str] = []

    parent_placeholder = ",".join("?" for _ in parent_keys)
    conditions.append(f"parent_product_id IN ({parent_placeholder})")
    params.extend(parent_keys)

    if variant_keys:
        variant_placeholder = ",".join("?" for _ in variant_keys)
        conditions.append(f"(variant_id = '' OR variant_id IN ({variant_placeholder}))")
        params.extend(variant_keys)

    if retailer:
        conditions.append("LOWER(retailer) = ?")
        params.append(retailer.lower())

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = (
        f"SELECT * FROM {normalized_table}{where_clause} "
        "ORDER BY parent_product_id, variant_id, attribute_id"
    )

    with connect_pdp_database(pdp_store_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        column_names = [column[0] for column in cursor.description]

    if not rows:
        return pl.DataFrame()

    records = [dict(zip(column_names, row)) for row in rows]
    frame = pl.DataFrame(records)
    if "extras_json" in frame.columns:
        frame = frame.drop("extras_json")
    sort_cols = [
        col
        for col in ("parent_product_id", "variant_id", "attribute_id", "source")
        if col in frame.columns
    ]
    if sort_cols:
        frame = frame.sort(sort_cols)
    return frame


def prepare_attribute_filters(
    filtered_tables: ReviewTables,
    category_lookup: Mapping[str, dict],
    selected_keys: Sequence[str],
) -> AttributeFilterSetup:
    category_metas = [category_lookup.get(key, {}) for key in selected_keys]
    if not category_metas:
        return AttributeFilterSetup(
            placeholder_values=PlaceholderValues,
            valid_attributes=[],
            attr_column_lookup={},
            attribute_filters=[],
            allowed_attr_ids=set(),
            filter_source=pl.DataFrame(),
        )

    def _attr_map(meta: Mapping[str, object]) -> dict[str, dict]:
        attrs = meta.get("attributes", []) or []
        mapping: dict[str, dict] = {}
        if isinstance(attrs, list):
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                attr_id = str(attr.get("id", "")).strip()
                if attr_id:
                    mapping[attr_id] = attr
        return mapping

    base_map = _attr_map(category_metas[0])
    common_ids = set(base_map.keys())
    for meta in category_metas[1:]:
        meta_ids = set(_attr_map(meta).keys())
        common_ids &= meta_ids
    attributes_meta = [
        base_map[attr_id] for attr_id in base_map.keys() if attr_id in common_ids
    ]

    filter_frames = [
        df
        for df in (filtered_tables.combined, filtered_tables.parents)
        if not df.is_empty()
    ]
    filter_source = (
        pl.concat(filter_frames, how="diagonal_relaxed")
        if filter_frames
        else filtered_tables.combined
    )

    filter_columns, _ = get_schema_and_column_names(filter_source)
    column_aliases = build_column_aliases(filter_columns)

    activity_map = get_attribute_activity()
    category_meta = category_metas[0]
    category_activity: dict[str, str] = {}
    for key in (
        str(category_meta.get("id", "")).strip().lower(),
        str(category_meta.get("label", "")).strip().lower(),
    ):
        if key and key in activity_map:
            category_activity.update(activity_map[key])

    attr_column_lookup: dict[str, str] = {}
    valid_attributes: list[dict[str, object]] = []
    for attr in attributes_meta:
        if not isinstance(attr, dict):
            continue
        attr_id = str(attr.get("id", "")).strip()
        attr_label = str(attr.get("label", attr_id))
        if not attr_id:
            continue
        column_name = resolve_attribute_column(attr_id, attr_label, column_aliases)
        if not column_name or column_name not in filter_columns:
            continue
        values = (
            filter_source.select(pl.col(column_name))
            .drop_nulls()
            .unique()
            .get_column(column_name)
            .to_list()
        )
        cleaned_values = sorted(
            {v.strip() for v in values if isinstance(v, str) and v.strip()}
        )
        lower_values = [v.lower() for v in values if isinstance(v, str)]
        has_na_placeholder = any(
            (val in PlaceholderValues and not _is_not_in_taxonomy_value(val))
            or _is_not_in_taxonomy_placeholder_value(val)
            for val in lower_values
        )
        has_not_in_taxonomy = any(
            _is_not_in_taxonomy_value(val) for val in lower_values
        )

        usable_values = [
            v
            for v in cleaned_values
            if (
                v.lower() not in PlaceholderValues
                and not _is_not_in_taxonomy_value(v)
                and not _is_not_in_taxonomy_placeholder_value(v)
            )
        ]
        if has_na_placeholder:
            usable_values.append("N/A")
        if has_not_in_taxonomy:
            usable_values.append("Not in taxonomy")
        if not usable_values:
            continue
        attr_column_lookup[attr_id] = column_name
        attr_label_clean = attr_label.strip()
        attr_status = category_activity.get(attr_id.lower()) or category_activity.get(
            attr_label_clean.lower(), "active"
        )
        is_active = str(attr_status).lower() == "active"
        valid_attributes.append(
            {
                "id": attr_id,
                "label": attr_label,
                "column": column_name,
                "values": usable_values,
                "active": is_active,
            }
        )

    allowed_attr_ids = {str(attr["id"]) for attr in valid_attributes}
    attribute_filters = [
        (attr["id"], attr["label"], attr["column"]) for attr in valid_attributes
    ]

    return AttributeFilterSetup(
        placeholder_values=PlaceholderValues,
        valid_attributes=valid_attributes,
        attr_column_lookup=attr_column_lookup,
        attribute_filters=attribute_filters,
        allowed_attr_ids=allowed_attr_ids,
        filter_source=filter_source,
    )


def apply_attribute_filters(
    frame: pl.DataFrame,
    selections: Mapping[str, Sequence[str]],
    attr_column_lookup: Mapping[str, str],
    *,
    placeholder_values: Iterable[str] = PlaceholderValues,
    exclude: str | None = None,
) -> pl.DataFrame:
    if frame.is_empty() or not selections:
        return frame
    result = frame
    placeholders = set(str(v).lower() for v in placeholder_values)
    placeholder_na = {val for val in placeholders if val != "not in taxonomy"}
    for attr_id, values in selections.items():
        if attr_id == exclude:
            continue
        column_name = attr_column_lookup.get(attr_id)
        if not column_name or column_name not in result.columns:
            continue
        include_na = False
        include_not_in_taxonomy = False
        include_found = False
        target_values: list[str] = []
        for value in values:
            normalized = str(value).strip()
            lowered = normalized.lower()
            if lowered == "not in taxonomy":
                include_not_in_taxonomy = True
            elif lowered == "n/a" or lowered in placeholder_na:
                include_na = True
            elif lowered in {"found", "has value", "has_value"}:
                include_found = True
            else:
                target_values.append(normalized)
        expr: pl.Expr | None = None
        if target_values:
            expr = pl.col(column_name).is_in(target_values)
        if include_na:
            placeholder_expr = (
                pl.col(column_name).is_null()
                | pl.col(column_name)
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.to_lowercase()
                .is_in(list(placeholder_na))
                | _not_in_taxonomy_placeholder_expr(column_name)
            )
            expr = placeholder_expr if expr is None else (expr | placeholder_expr)
        if include_not_in_taxonomy:
            notax_expr = _not_in_taxonomy_expr(column_name)
            expr = notax_expr if expr is None else (expr | notax_expr)
        if include_found:
            normalized_expr = (
                pl.col(column_name).cast(pl.Utf8).str.strip_chars().str.to_lowercase()
            )
            found_expr = (
                pl.col(column_name).is_not_null()
                & (normalized_expr != "")
                & ~normalized_expr.is_in(list(placeholder_na))
                & ~normalized_expr.str.starts_with("not in taxonomy")
            )
            expr = found_expr if expr is None else (expr | found_expr)
        if expr is not None:
            result = result.filter(expr)
    return result


def compute_attribute_coverage_report(
    frame: pl.DataFrame,
    filter_setup: AttributeFilterSetup,
    category_lookup: Mapping[str, dict],
) -> dict[str, object]:
    """Return coverage metrics for attribute completeness and taxonomy misses."""
    if frame.is_empty() or not filter_setup.valid_attributes:
        return {
            "total_records": 0,
            "attributes": [],
            "categories": [],
        }

    placeholder_set = {
        str(val).strip().lower() for val in filter_setup.placeholder_values
    }
    placeholder_na = {val for val in placeholder_set if val != "not in taxonomy"}

    def _attribute_metrics(
        target: pl.DataFrame, attr_meta: Mapping[str, object]
    ) -> dict[str, object]:
        column_name = str(attr_meta["column"])
        total_records = get_row_count(target)
        if total_records == 0 or column_name not in target.columns:
            return {
                "id": str(attr_meta["id"]),
                "label": str(attr_meta["label"]),
                "column": column_name,
                "total": total_records,
                "filled": 0,
                "filled_pct": 0.0,
                "missing": 0,
                "missing_pct": 0.0,
                "not_in_taxonomy": 0,
                "not_in_taxonomy_pct": 0.0,
            }

        normalized = (
            pl.col(column_name).cast(pl.Utf8).str.strip_chars().str.to_lowercase()
        )
        not_in_tax_expr = _not_in_taxonomy_expr(column_name)
        not_in_tax_placeholder_expr = _not_in_taxonomy_placeholder_expr(column_name)
        missing_expr = (
            pl.col(column_name).is_null()
            | (normalized == "")
            | normalized.is_in(list(placeholder_na))
            | not_in_tax_placeholder_expr
        )
        counts = target.select(
            missing_expr.cast(pl.Int64).sum().alias("missing"),
            not_in_tax_expr.cast(pl.Int64).sum().alias("not_in_taxonomy"),
        ).row(0)
        missing_count = int(counts[0] or 0)
        not_in_tax_count = int(counts[1] or 0)
        filled_count = max(0, total_records - missing_count - not_in_tax_count)

        metrics = {
            "id": str(attr_meta["id"]),
            "label": str(attr_meta["label"]),
            "column": column_name,
            "total": total_records,
            "filled": filled_count,
            "filled_pct": 0.0,
            "missing": missing_count,
            "missing_pct": 0.0,
            "not_in_taxonomy": not_in_tax_count,
            "not_in_taxonomy_pct": 0.0,
        }

        total_float = float(total_records) if total_records else 0.0
        metrics.update(
            {
                "filled_pct": (filled_count / total_float) if total_float else 0.0,
                "missing_pct": (missing_count / total_float) if total_float else 0.0,
                "not_in_taxonomy_pct": (
                    (not_in_tax_count / total_float) if total_float else 0.0
                ),
            }
        )

        return metrics

    overall_attributes = [
        _attribute_metrics(frame, attr_meta)
        for attr_meta in filter_setup.valid_attributes
    ]

    categories: list[dict[str, object]] = []
    if "category_key" in frame.columns:
        category_keys = frame.get_column("category_key").drop_nulls().unique().to_list()
        activity_map = get_attribute_activity()
        for raw_key in category_keys:
            key = str(raw_key).strip().lower()
            if not key:
                continue
            category_meta = category_lookup.get(key, {})
            label = str(category_meta.get("label") or key)
            category_frame = frame.filter(pl.col("category_key") == raw_key)
            cat_total = get_row_count(category_frame)
            attrs: list[dict[str, object]] = []
            for attr_meta in filter_setup.valid_attributes:
                metrics = _attribute_metrics(category_frame, attr_meta)
                attr_id = str(attr_meta["id"]).strip().lower()
                attr_label = str(attr_meta["label"]).strip().lower()
                activity_status = "active"
                for lookup_key in (
                    str(category_meta.get("id", "")).strip().lower(),
                    str(category_meta.get("label", "")).strip().lower(),
                    key,
                ):
                    if lookup_key and lookup_key in activity_map:
                        activity_status = (
                            activity_map[lookup_key].get(attr_id)
                            or activity_map[lookup_key].get(attr_label)
                            or activity_status
                        )
                        if activity_status:
                            break
                metrics["status"] = str(activity_status or "active")
                if str(metrics["status"]).lower() != "active":
                    metrics["inactive_filled"] = metrics["filled"]
                    metrics["inactive_filled_pct"] = metrics["filled_pct"]
                else:
                    metrics["inactive_filled"] = 0
                    metrics["inactive_filled_pct"] = 0.0
                attrs.append(metrics)
            categories.append(
                {
                    "category_key": key,
                    "category_label": label,
                    "total": cat_total,
                    "attributes": attrs,
                }
            )

    report: dict[str, object] = {
        "total_records": get_row_count(frame),
        "attributes": overall_attributes,
        "categories": categories,
    }
    return report


def ensure_record_identifiers(frame: pl.DataFrame, record_type: str) -> pl.DataFrame:
    result = frame
    if result.is_empty():
        return result
    if "record_type" not in result.columns:
        result = result.with_columns(pl.lit(record_type).alias("record_type"))
    if "product" not in result.columns and "parent_product_id" in result.columns:
        result = result.with_columns(pl.col("parent_product_id").alias("product"))
    if record_type == "parent":
        if "variant" not in result.columns:
            result = result.with_columns(pl.lit("").alias("variant"))
    else:
        if "variant" not in result.columns and "variant_id" in result.columns:
            result = result.with_columns(pl.col("variant_id").alias("variant"))
    return result


def normalize_category_key(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower().replace(" ", "_")


def build_column_aliases(columns: Sequence[str]) -> dict[str, str]:
    column_aliases: dict[str, str] = {}
    for raw_name in columns:
        column_name = str(raw_name)
        lowered = column_name.lower()
        column_aliases.setdefault(column_name, column_name)
        column_aliases.setdefault(lowered, column_name)
        normalized = normalize_category_key(column_name)
        if normalized:
            column_aliases.setdefault(normalized, column_name)
            column_aliases.setdefault(normalized.lower(), column_name)
        underscored = column_name.replace(" ", "_")
        column_aliases.setdefault(underscored, column_name)
        column_aliases.setdefault(underscored.lower(), column_name)
        hyphen_normalized = column_name.replace("-", "_")
        column_aliases.setdefault(hyphen_normalized, column_name)
        column_aliases.setdefault(hyphen_normalized.lower(), column_name)
        slash_normalized = column_name.replace("/", "_")
        column_aliases.setdefault(slash_normalized, column_name)
        column_aliases.setdefault(slash_normalized.lower(), column_name)
    return column_aliases


def resolve_attribute_column(
    attr_id: str,
    attr_label: str,
    column_aliases: Mapping[str, str],
) -> str | None:
    candidates: list[str] = []
    for candidate in (
        attr_id,
        attr_label,
        attr_id.replace("_", " "),
        attr_id.replace("_", "-"),
        attr_id.replace("_", "/"),
        attr_label.replace("-", " "),
        attr_label.replace("/", " "),
        attr_label.replace("-", "_"),
        attr_label.replace("/", "_"),
    ):
        cleaned = candidate.strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    if attr_id.strip().lower() == "form" or attr_label.strip().lower() == "form":
        for candidate in ("format",):
            if candidate not in candidates:
                candidates.append(candidate)
    for candidate in candidates:
        resolved = column_aliases.get(candidate)
        if resolved:
            return resolved
        resolved = column_aliases.get(candidate.lower())
        if resolved:
            return resolved
    return None
