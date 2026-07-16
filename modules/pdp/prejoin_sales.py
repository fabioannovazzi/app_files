from __future__ import annotations

"""
Dataset-specific sales joins for already-mapped PDP attributes.

Pipeline boundary: this module is downstream of PDP scraping, taxonomy export,
and attribute mapping. It expects already-normalized PDP/category/attribute data
and should mainly match sales rows to catalog rows, preferably by SKU key.
Cross-retailer category and attribute normalization belongs upstream in the
attribute export/mapping pipeline, not here. Brand-fit diagnostics should inspect
attribute mapping outputs and report package inputs, not this sales join.

Outputs:
  - <sales_join_output_dir>/full_sales.parquet
  - <sales_join_output_dir>/joined.parquet
  - <sales_join_output_dir>/joined_manifest.json
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

import polars as pl

from modules.add_attributes.pdp_attribute_export import _ATTRIBUTE_PLACEHOLDERS
from modules.pdp.attribute_mapping_core import (
    _load_postfill_attribute_cache,
    _log_duplicate_keys,
    _normalize_text,
    _write_postfill_attribute_cache,
)
from modules.pdp.attribute_mapping_paths import get_attribute_mapping_dir
from modules.pdp.canonical import compute_canonical_values
from modules.pdp.sales_dataset_paths import (
    DEFAULT_SALES_DATASET,
    SALES_DATASET_ENV_VAR,
    get_sales_dataset_csv_dir,
    get_sales_dataset_dir,
    get_sales_dataset_join_dir,
    get_sales_dataset_name,
)
from modules.utilities.utils import get_schema_and_column_names

APP_ROOT = Path(__file__).resolve().parents[2]
KEY_CONFIG_PATHS = [
    APP_ROOT / "config" / "sales_join_keys.json",
    APP_ROOT / "config" / "sales_join_keys.yaml",
    APP_ROOT / "config" / "sales_join_keys.yml",
]

ACTIVE_SALES_DATASET = DEFAULT_SALES_DATASET
SALES_DATASET_DIR = get_sales_dataset_dir(DEFAULT_SALES_DATASET)
SALES_CSV_DIR = get_sales_dataset_csv_dir(DEFAULT_SALES_DATASET)
SALES_DIR = get_sales_dataset_join_dir(DEFAULT_SALES_DATASET)
MAPPING_DIR = get_attribute_mapping_dir()
POSTFILL_ATTRIBUTE_CACHE_DIR = MAPPING_DIR / "postfill_attribute_cache"
JOINED_OUTPUT = SALES_DIR / "joined.parquet"
MANIFEST_OUTPUT = SALES_DIR / "joined_manifest.json"
FULL_SALES_OUTPUT = SALES_DIR / "full_sales.parquet"
POSTFILL_PARENTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents.parquet"
POSTFILL_VARIANTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "variants.parquet"
POSTFILL_PARENTS_ALL_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents_all.parquet"
POSTFILL_COMBINED_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "combined.parquet"
VISION_FILL_AUDIT_CHECKPOINT_DIR = MAPPING_DIR / "attribute_vision_fill_audit_chunks"
WEB_FILL_AUDIT_CHECKPOINT_DIR = MAPPING_DIR / "attribute_web_fill_audit_chunks"
ATTRIBUTE_FILL_STATE_PATH = MAPPING_DIR / "attribute_fill_state.json"
VISION_CONFIDENCE_THRESHOLD = 0.8
VISION_SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
VISION_IMAGE_DOWNLOAD_LIMIT_BYTES = 12_000_000
WEB_CONFIDENCE_THRESHOLD = 0.8
NO_VALUE_SUPPRESSION_RUNS = 2
MIN_LLM_ATTRIBUTE_COVERAGE = 0.7

BRAND_ALIASES_PATH = APP_ROOT / "brand_aliases.json"

ATTRIBUTE_PLACEHOLDER_VALUES: list[str] = sorted(
    {
        str(item).strip().casefold()
        for item in _ATTRIBUTE_PLACEHOLDERS
        if isinstance(item, str)
    }
)

REQUIRED_SALES_COLUMNS = [
    "month",
    "merchant",
    "category",
    "brand",
    "sku",
    "product_description",
    "sales",
    "units",
]
OPTIONAL_SALES_COLUMNS = [
    "period",
    "product_collection",
    "line",
]
SALES_COLUMN_RENAMES = {
    "time": "month",
    "l3": "category",
    "sku_number": "sku",
    "product_name": "product_description",
    "gmv": "sales",
}
ALLOWED_SALES_COLUMNS = set(REQUIRED_SALES_COLUMNS + OPTIONAL_SALES_COLUMNS)

# Some sales sources split "setting spray" and "setting powder" while the taxonomy treats them
# as one category. Normalize to the taxonomy label so category selection is consistent even
# when SKU→catalog joins are unavailable.
_CATEGORY_NORMALIZATION_MAP: dict[str, str] = {
    "blushes": "blush",
    "bronzers": "bronzer",
    "concealers": "concealer",
    "eyebrows": "eyebrow",
    "eyeshadows": "eyeshadow",
    "highlighters face": "highlighter",
    "mascaras": "mascara",
    "primers and fixers face": "face primer",
    "primers face": "face primer",
    "powders": "setting spray & powder",
    "setting spray": "setting spray & powder",
    "setting powder": "setting spray & powder",
    "automatic eye pencil": "eyeliner",
    "face make up kit": "palette",
    "face make-up kit": "palette",
    "eyes make up kit": "palette",
    "eyes make-up kit": "palette",
    "lips make up kit": "palette",
    "lips make-up kit": "palette",
    "lip marker": "lipstick",
    "contouring": "contour",
    "stick contouring": "contour",
    "wood eye pencil": "wood eye pencils",
}

# Kiko uses "wood eye pencils" as a catalog class that spans multiple taxonomy buckets
# (eyeliner / eyebrow / highlighter). Treat these as category-compatible during joins.
_CATEGORY_MATCH_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "wood eye pencils": ("eyeliner", "eyebrow", "highlighter"),
    "eyeliner": ("wood eye pencils",),
    "eyebrow": ("wood eye pencils",),
    "highlighter": ("wood eye pencils",),
}

_CATEGORY_SOURCE_PRIORITY: tuple[str, ...] = (
    "prodlast_lev4",
    "prodlast_lev3",
    "prodlast_lev2",
    "prodlast_lev1",
)
_CATEGORY_EXACT_MAP: dict[str, str] = {
    "blush": "blush",
    "blushes": "blush",
    "foundation": "foundation",
    "bronzers": "bronzer",
    "bronzer": "bronzer",
    "lipstick": "lipstick",
    "fluid lipstick": "liquid lipstick",
    "liquid lipstick": "liquid lipstick",
    "lip gloss": "lip gloss",
    "concealers": "concealer",
    "concealer": "concealer",
    "highlighters face": "highlighter",
    "highlighter": "highlighter",
    "mascaras": "mascara",
    "mascara": "mascara",
    "eyeshadows": "eyeshadow",
    "eyeshadow": "eyeshadow",
    "eyeliner": "eyeliner",
    "eyebrows": "eyebrow",
    "eyebrow": "eyebrow",
    "primers and fixers face": "face primer",
    "primers face": "face primer",
    "face primer": "face primer",
    "powders": "setting spray & powder",
    "eyes make-up kit": "palette",
    "face make-up kit": "palette",
    "lips make up kit": "palette",
    "blush face palette": "palette",
    "eyeshadow palette": "palette",
    "concealers palette": "palette",
    "contouring palette": "palette",
    "contouring": "contour",
    "stick contouring": "contour",
    "wood eye pencils": "wood eye pencils",
    "wood eye pencil": "wood eye pencils",
}
_DATASET_DEFAULT_BRANDS: dict[str, str] = {
    "kiko": "kiko milano",
}

_VARIANT_SEPARATOR_REGEX = r"^(.*)\s[-–—]\s(.+)$"

ATTRIBUTE_RETAILER_PRIORITY: list[str] = ["ulta", "kiko", "sephora", "amazon"]


def _configure_sales_paths(dataset: str | None) -> str:
    """Set module-level sales input/output paths for the selected dataset."""

    global ACTIVE_SALES_DATASET
    global SALES_DATASET_DIR
    global SALES_DIR
    global SALES_CSV_DIR
    global MAPPING_DIR
    global POSTFILL_ATTRIBUTE_CACHE_DIR
    global JOINED_OUTPUT
    global MANIFEST_OUTPUT
    global FULL_SALES_OUTPUT
    global POSTFILL_PARENTS_OUTPUT
    global POSTFILL_VARIANTS_OUTPUT
    global POSTFILL_PARENTS_ALL_OUTPUT
    global POSTFILL_COMBINED_OUTPUT
    global VISION_FILL_AUDIT_CHECKPOINT_DIR
    global WEB_FILL_AUDIT_CHECKPOINT_DIR
    global ATTRIBUTE_FILL_STATE_PATH

    ACTIVE_SALES_DATASET = get_sales_dataset_name(dataset)
    SALES_DATASET_DIR = get_sales_dataset_dir(ACTIVE_SALES_DATASET)
    SALES_CSV_DIR = get_sales_dataset_csv_dir(ACTIVE_SALES_DATASET)
    SALES_DIR = get_sales_dataset_join_dir(ACTIVE_SALES_DATASET)
    MAPPING_DIR = get_attribute_mapping_dir()
    POSTFILL_ATTRIBUTE_CACHE_DIR = MAPPING_DIR / "postfill_attribute_cache"
    JOINED_OUTPUT = SALES_DIR / "joined.parquet"
    MANIFEST_OUTPUT = SALES_DIR / "joined_manifest.json"
    FULL_SALES_OUTPUT = SALES_DIR / "full_sales.parquet"
    POSTFILL_PARENTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents.parquet"
    POSTFILL_VARIANTS_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "variants.parquet"
    POSTFILL_PARENTS_ALL_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "parents_all.parquet"
    POSTFILL_COMBINED_OUTPUT = POSTFILL_ATTRIBUTE_CACHE_DIR / "combined.parquet"
    VISION_FILL_AUDIT_CHECKPOINT_DIR = (
        MAPPING_DIR / "attribute_vision_fill_audit_chunks"
    )
    WEB_FILL_AUDIT_CHECKPOINT_DIR = MAPPING_DIR / "attribute_web_fill_audit_chunks"
    ATTRIBUTE_FILL_STATE_PATH = MAPPING_DIR / "attribute_fill_state.json"
    return ACTIVE_SALES_DATASET


# Keep legacy behaviour by default (single dataset rooted at data/pdp/sales_data).
_configure_sales_paths(DEFAULT_SALES_DATASET)


def _load_key_config() -> dict:
    for path in KEY_CONFIG_PATHS:
        if path.exists():
            try:
                if path.suffix in {".yaml", ".yml"}:
                    try:
                        import yaml  # type: ignore
                    except Exception:
                        return {}
                    return yaml.safe_load(path.read_text())
                return json.loads(path.read_text())
            except Exception:
                return {}
    return {}


def _normalize_sales_column_name(name: str) -> str:
    normalized = name.strip().lower().replace(" ", "_")
    return SALES_COLUMN_RENAMES.get(normalized, normalized)


def _build_sales_rename_map(columns: Iterable[str]) -> dict[str, str]:
    rename_map: dict[str, str] = {}
    seen: dict[str, str] = {}
    for column in columns:
        column_str = str(column)
        normalized = _normalize_sales_column_name(column_str)
        if normalized in seen:
            raise ValueError(
                "Duplicate sales columns after normalization: "
                f"{seen[normalized]!r} and {column_str!r} -> {normalized!r}"
            )
        rename_map[column] = normalized
        seen[normalized] = column_str
    return rename_map


def _standardize_sales_headers(df: pl.DataFrame) -> pl.DataFrame:
    columns, _ = get_schema_and_column_names(df)
    rename_map = _build_sales_rename_map(columns)
    return df.rename(rename_map)


def _dataset_default_brand(dataset_name: str) -> str:
    normalized = str(dataset_name or "").strip().lower()
    if not normalized or normalized == DEFAULT_SALES_DATASET:
        return ""
    return _DATASET_DEFAULT_BRANDS.get(normalized, normalized.replace("_", " "))


def _sales_text_expr(column_name: str) -> pl.Expr:
    return (
        pl.col(column_name)
        .cast(pl.Utf8)
        .map_elements(_normalize_text)
        .str.to_lowercase()
    )


def _map_sales_category_expr(source_expr: pl.Expr) -> pl.Expr:
    return (
        pl.when(source_expr.is_in(list(_CATEGORY_EXACT_MAP.keys())))
        .then(source_expr.replace(_CATEGORY_EXACT_MAP))
        .when(source_expr.str.contains(r"\bwood\\s+eye\\s+pencils?\\b"))
        .then(pl.lit("wood eye pencils"))
        .when(source_expr.str.contains(r"\blip marker\b"))
        .then(pl.lit("lipstick"))
        .when(source_expr.str.contains(r"\blip oil\b"))
        .then(pl.lit("lip oil"))
        .when(
            source_expr.str.contains(r"\b(liquid|fluid)\s+lipstick\b")
            | source_expr.str.contains(r"\blipstick\b")
        )
        .then(
            pl.when(source_expr.str.contains(r"\b(liquid|fluid)\s+lipstick\b"))
            .then(pl.lit("liquid lipstick"))
            .otherwise(pl.lit("lipstick"))
        )
        .when(source_expr.str.contains(r"\blip gloss\b"))
        .then(pl.lit("lip gloss"))
        .when(source_expr.str.contains(r"\bblush"))
        .then(pl.lit("blush"))
        .when(source_expr.str.contains(r"\bbronzer"))
        .then(pl.lit("bronzer"))
        .when(source_expr.str.contains(r"\bfoundation\b"))
        .then(pl.lit("foundation"))
        .when(source_expr.str.contains(r"\bconcealer"))
        .then(pl.lit("concealer"))
        .when(source_expr.str.contains(r"\bhighlighter"))
        .then(pl.lit("highlighter"))
        .when(source_expr.str.contains(r"\bmascara"))
        .then(pl.lit("mascara"))
        .when(source_expr.str.contains(r"\beyeshadow"))
        .then(pl.lit("eyeshadow"))
        .when(source_expr.str.contains(r"\beyeliner"))
        .then(pl.lit("eyeliner"))
        .when(source_expr.str.contains(r"\beyebrow"))
        .then(pl.lit("eyebrow"))
        .when(source_expr.str.contains(r"\b(face\\s+)?primer\\b"))
        .then(pl.lit("face primer"))
        .when(
            source_expr.str.contains(r"\bsetting\b")
            | source_expr.str.contains(r"\bpowder\\b")
        )
        .then(pl.lit("setting spray & powder"))
        .when(
            source_expr.str.contains(r"\bpalette\\b")
            | source_expr.str.contains(r"\bkit\\b")
            | source_expr.str.contains(r"clics")
        )
        .then(pl.lit("palette"))
        .otherwise(pl.lit(None))
    )


def _derive_category_expr(columns: set[str]) -> pl.Expr:
    mapped_candidates: list[pl.Expr] = []

    for column_name in _CATEGORY_SOURCE_PRIORITY:
        if column_name in columns:
            mapped_candidates.append(
                _map_sales_category_expr(_sales_text_expr(column_name))
            )

    if "product_description" in columns:
        mapped_candidates.append(
            _map_sales_category_expr(_sales_text_expr("product_description"))
        )

    if not mapped_candidates:
        return pl.lit(None)
    return pl.coalesce(mapped_candidates)


def _ensure_required_sales_columns(df: pl.DataFrame) -> pl.DataFrame:
    columns, _ = get_schema_and_column_names(df)
    column_set = set(columns)
    additions: list[pl.Expr] = []

    if "month" not in column_set and "period" in column_set:
        additions.append(pl.col("period").alias("month"))
    if "product_description" not in column_set and "product_name" in column_set:
        additions.append(pl.col("product_name").alias("product_description"))

    if "line" not in column_set and "channel" in column_set:
        additions.append(_sales_text_expr("channel").alias("line"))

    if "merchant" not in column_set:
        if ACTIVE_SALES_DATASET != DEFAULT_SALES_DATASET:
            additions.append(pl.lit(ACTIVE_SALES_DATASET).alias("merchant"))
        elif "channel" in column_set:
            additions.append(_sales_text_expr("channel").alias("merchant"))

    if "brand" not in column_set:
        default_brand = _dataset_default_brand(ACTIVE_SALES_DATASET)
        if default_brand:
            additions.append(pl.lit(default_brand).alias("brand"))

    if "category" not in column_set:
        additions.append(_derive_category_expr(column_set).alias("category"))

    if additions:
        return df.with_columns(additions)
    return df


def _normalize_join_text(expr: pl.Expr) -> pl.Expr:
    """Normalize free text for joins (lowercase, strip punctuation/extra whitespace)."""
    return (
        expr.cast(pl.Utf8)
        .str.to_lowercase()
        .str.replace_all(r"[^a-z0-9]+", " ")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def _parse_month(series: pl.Series) -> pl.Series:
    month_raw = series.cast(pl.Utf8).str.strip_chars()
    parsed = pl.coalesce(
        [
            month_raw.str.strptime(pl.Date, format="%Y-%m-%d", strict=False),
            month_raw.str.strptime(pl.Date, format="%m/%d/%Y", strict=False),
            month_raw.str.strptime(pl.Date, format="%m/%d/%y", strict=False),
            month_raw.str.strptime(pl.Date, format="%Y", strict=False),
        ]
    )
    return parsed


def _preflight_sales(columns: Iterable[str]) -> list[str]:
    column_set = set(columns)
    return [col for col in REQUIRED_SALES_COLUMNS if col not in column_set]


def _normalize_sales(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    before_rows = df.height
    columns, _ = get_schema_and_column_names(df)
    rename_map = _build_sales_rename_map(columns)
    df = df.rename(rename_map)
    columns, _ = get_schema_and_column_names(df)
    has_period_only_time = "period" in set(columns) and "month" not in set(columns)
    df = _ensure_required_sales_columns(df)
    columns, _ = get_schema_and_column_names(df)
    missing = _preflight_sales(columns)
    if missing:
        raise ValueError(f"Missing required sales columns: {missing}")
    drop_cols = [col for col in columns if col not in ALLOWED_SALES_COLUMNS]
    if drop_cols:
        df = df.drop(drop_cols)
    category_raw = (
        pl.col("category")
        .cast(pl.Utf8)
        .map_elements(_normalize_text)
        .str.to_lowercase()
    )
    category_mapped = category_raw.replace(_CATEGORY_NORMALIZATION_MAP)
    category_value = (
        pl.when(category_mapped.is_not_null() & (category_mapped != ""))
        .then(category_mapped)
        .otherwise(pl.lit(None))
    )
    category_from_description = _map_sales_category_expr(
        pl.col("product_description")
        .cast(pl.Utf8)
        .map_elements(_normalize_text)
        .str.to_lowercase()
    )
    month_expr = (
        pl.col("month").cast(pl.Utf8).map_elements(_normalize_text).alias("month")
        if has_period_only_time
        else _parse_month(pl.col("month")).alias("month")
    )
    normalize_exprs: list[pl.Expr] = [
        month_expr,
        pl.col("merchant")
        .cast(pl.Utf8)
        .map_elements(_normalize_text)
        .str.to_lowercase()
        .alias("merchant"),
        pl.coalesce([category_value, category_from_description]).alias("category"),
        pl.col("brand").cast(pl.Utf8).map_elements(_normalize_text).alias("brand"),
        pl.col("product_description")
        .cast(pl.Utf8)
        .map_elements(_normalize_text)
        .alias("product_description"),
        pl.col("sku").cast(pl.Utf8).map_elements(_normalize_text).alias("sku"),
        pl.col("sales").cast(pl.Float64).alias("sales"),
        pl.col("units").cast(pl.Float64).alias("units"),
    ]
    if "period" in columns:
        normalize_exprs.append(
            pl.col("period").cast(pl.Utf8).map_elements(_normalize_text).alias("period")
        )
    df = df.with_columns(normalize_exprs)
    df = df.drop_nulls(subset=["sales", "units"])
    after_rows = df.height
    dropped = before_rows - after_rows
    if logging.getLogger().isEnabledFor(logging.INFO):
        logging.info(
            "Sales normalization row count: %s -> %s (dropped=%s).",
            before_rows,
            after_rows,
            dropped,
        )
    if df.is_empty():
        return df

    description = pl.col("product_description").cast(pl.Utf8).str.strip_chars()
    base = description.str.extract(_VARIANT_SEPARATOR_REGEX, 1)
    variant_hint = description.str.extract(_VARIANT_SEPARATOR_REGEX, 2)
    df = df.with_columns(
        [
            pl.when(base.is_not_null() & (base.str.strip_chars() != ""))
            .then(base)
            .otherwise(description)
            .alias("product_base_name"),
            pl.when(variant_hint.is_not_null() & (variant_hint.str.strip_chars() != ""))
            .then(variant_hint)
            .otherwise(pl.lit(None))
            .alias("variant_hint"),
            _normalize_join_text(description).alias("product_description_norm"),
            _normalize_join_text(variant_hint).alias("variant_hint_norm"),
        ]
    )

    _log_duplicate_keys(
        df,
        subset=("merchant", "sku", "month"),
        label="Sales (normalized)",
    )
    sales_series = df.get_column("sales")
    units_series = df.get_column("units")
    sales_min = sales_series.min()
    sales_max = sales_series.max()
    units_min = units_series.min()
    units_max = units_series.max()
    logging.info(
        "Normalized sales: sales_unique=%s sales_min=%s sales_max=%s units_unique=%s units_min=%s units_max=%s",
        sales_series.n_unique(),
        float(sales_min) if sales_min is not None else None,
        float(sales_max) if sales_max is not None else None,
        units_series.n_unique(),
        float(units_min) if units_min is not None else None,
        float(units_max) if units_max is not None else None,
    )
    # Canonical fields for product-level fallback joins.
    df = df.with_columns(
        [
            pl.struct(["brand", "product_base_name"])
            .map_elements(
                lambda row: (
                    lambda triple: {
                        "canonical_id": triple[0],
                        "brand_norm": triple[1],
                        "product_name_norm": triple[2],
                    }
                )(
                    compute_canonical_values(
                        row.get("brand"), row.get("product_base_name")
                    )
                ),
                return_dtype=pl.Struct(
                    {
                        "canonical_id": pl.Utf8,
                        "brand_norm": pl.Utf8,
                        "product_name_norm": pl.Utf8,
                    }
                ),
            )
            .alias("_canonical_struct")
        ]
    )
    df = df.with_columns(
        [
            pl.col("_canonical_struct")
            .struct.field("canonical_id")
            .alias("canonical_id"),
            pl.col("_canonical_struct").struct.field("brand_norm").alias("brand_norm"),
            pl.col("_canonical_struct")
            .struct.field("product_name_norm")
            .alias("product_name_norm"),
        ]
    ).drop("_canonical_struct")
    return df


def _load_sales_csvs() -> tuple[pl.DataFrame, list[Path]]:
    if not SALES_CSV_DIR.exists():
        raise SystemExit(f"Sales CSV directory not found: {SALES_CSV_DIR}")

    sales_paths = sorted(
        [path for path in SALES_CSV_DIR.glob("*.csv") if path.is_file()]
    )
    if not sales_paths:
        raise SystemExit(f"No sales CSV files found in {SALES_CSV_DIR}")

    frames: list[pl.DataFrame] = []
    file_row_counts: list[int] = []
    expected_columns: list[str] | None = None
    expected_set: set[str] | None = None

    for path in sales_paths:
        df = pl.read_csv(path)
        try:
            df = _standardize_sales_headers(df)
        except ValueError as exc:
            raise SystemExit(
                f"Sales file {path} has duplicate columns after normalization: {exc}"
            ) from exc
        columns, _ = get_schema_and_column_names(df)
        if expected_columns is None:
            expected_columns = columns
            expected_set = set(columns)
        else:
            if expected_set is not None and set(columns) != expected_set:
                raise SystemExit(
                    f"Sales file structure mismatch: {path} columns do not match {sales_paths[0]}"
                )
        if expected_columns is not None and columns != expected_columns:
            df = df.select(expected_columns)
        logging.info(
            "Loaded sales CSV (%s): rows=%s cols=%s",
            path.name,
            df.height,
            df.width,
        )
        _log_duplicate_keys(
            df,
            subset=("merchant", "sku", "month"),
            label=f"Sales CSV ({path.name})",
        )
        frames.append(df)
        file_row_counts.append(df.height)

    if len(frames) == 1:
        return frames[0], sales_paths
    combined = pl.concat(frames, how="vertical")
    logging.info(
        "Concatenated %s sales CSVs: %s rows (sum of files=%s).",
        len(frames),
        combined.height,
        sum(file_row_counts),
    )
    return combined, sales_paths


def _parse_price_to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    import re

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def _compute_price_bands(
    variants: pl.DataFrame, categories: Iterable[str] | None = None
) -> pl.DataFrame:
    if (
        variants.is_empty()
        or "price_raw" not in variants.columns
        or "variant_id" not in variants.columns
    ):
        return pl.DataFrame()
    category_norms = (
        [str(c).strip().lower() for c in categories] if categories is not None else None
    )
    price_df = variants.with_columns(
        pl.col("variant_id").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm"),
        pl.col("price_raw")
        .map_elements(_parse_price_to_float, return_dtype=pl.Float64)
        .alias("price_numeric"),
        (
            pl.col("category_label")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("category_norm")
            if "category_label" in variants.columns
            else pl.lit(None).alias("category_norm")
        ),
    ).drop_nulls(subset=["price_numeric"])
    if category_norms:
        price_df = price_df.filter(pl.col("category_norm").is_in(category_norms))
    if price_df.is_empty():
        return pl.DataFrame()
    series = price_df.get_column("price_numeric")
    try:
        low = float(series.quantile(0.35, interpolation="nearest"))
        high = float(series.quantile(0.85, interpolation="nearest"))
    except Exception:
        return pl.DataFrame()
    price_df = price_df.with_columns(
        pl.when(pl.col("price_numeric") > high)
        .then(pl.lit("premium"))
        .when(pl.col("price_numeric") < low)
        .then(pl.lit("value"))
        .otherwise(pl.lit("mid"))
        .alias("price_band")
    )
    return price_df.select("variant_id_norm", "price_band")


def _compute_pareto(joined: pl.DataFrame) -> pl.DataFrame:
    if (
        joined.is_empty()
        or "parent_product_id" not in joined.columns
        or "sales" not in joined.columns
    ):
        return pl.DataFrame()
    parent_sales = (
        joined.select(["parent_product_id", "sales"])
        .group_by("parent_product_id")
        .agg(pl.col("sales").sum().alias("sales_total"))
        .sort(pl.col("sales_total"), descending=True)
    )
    if parent_sales.is_empty():
        return pl.DataFrame()
    total_sales_all = float(parent_sales.get_column("sales_total").sum())
    cumulative = 0.0
    pareto_map: MutableMapping[str, str] = {}
    for pid, sales_val in parent_sales.iter_rows():
        val = float(sales_val or 0.0)
        share = (val / total_sales_all) if total_sales_all > 0 else 0.0
        cumulative += share
        if cumulative <= 0.80 + 1e-9:
            bucket = "A"
        elif cumulative <= 0.95 + 1e-9:
            bucket = "B"
        else:
            bucket = "C"
        pareto_map[str(pid)] = bucket
    return pl.DataFrame(
        {
            "parent_product_id": list(pareto_map.keys()),
            "pareto_class": list(pareto_map.values()),
        }
    )


def _normalized_category_match_expr(column_name: str) -> pl.Expr:
    return (
        pl.col(column_name)
        .cast(pl.Utf8)
        .str.to_lowercase()
        .str.replace_all(r"[_-]+", " ")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
        .replace(_CATEGORY_NORMALIZATION_MAP)
    )


def _category_match_compatibility_expr(
    *, sales_column: str, catalog_column: str
) -> pl.Expr:
    expr = pl.lit(False)
    for catalog_category, sales_categories in _CATEGORY_MATCH_COMPATIBILITY.items():
        expr = expr | (
            (pl.col(catalog_column) == pl.lit(catalog_category))
            & pl.col(sales_column).is_in(list(sales_categories))
        )
    return expr


def _enforce_join_category_match(
    joined: pl.DataFrame, *, retailer: str, stage: str
) -> pl.DataFrame:
    if joined.is_empty():
        return joined
    if "category" not in joined.columns or "category_label" not in joined.columns:
        return joined

    filtered = (
        joined.with_columns(
            _normalized_category_match_expr("category").alias("_sales_category_norm"),
            _normalized_category_match_expr("category_label").alias(
                "_catalog_category_norm"
            ),
        )
        .with_columns(
            _category_match_compatibility_expr(
                sales_column="_sales_category_norm",
                catalog_column="_catalog_category_norm",
            ).alias("_category_compatible")
        )
        .filter(
            (pl.col("_sales_category_norm").is_not_null())
            & (pl.col("_sales_category_norm") != "")
            & (pl.col("_catalog_category_norm").is_not_null())
            & (pl.col("_catalog_category_norm") != "")
            & (
                (pl.col("_sales_category_norm") == pl.col("_catalog_category_norm"))
                | pl.col("_category_compatible")
            )
        )
        .drop(
            ["_sales_category_norm", "_catalog_category_norm", "_category_compatible"]
        )
    )
    dropped = joined.height - filtered.height
    if dropped > 0:
        logging.info(
            (
                "Dropped %s joined rows for %s at %s due to category mismatch "
                "(sales category vs catalog category_label)."
            ),
            dropped,
            retailer,
            stage,
        )
    return filtered


@dataclass
class JoinConfig:
    sales_sku_field: str
    catalog_variant_field: str | None
    catalog_parent_field: str | None


def _skip_kiko_primary_category_filter(retailer: str, cfg: JoinConfig) -> bool:
    """Allow KIKO exact backend-SKU matches even when category labels differ."""
    return retailer.lower() == "kiko" and (
        (cfg.catalog_variant_field or "").strip().lower() == "variant_id_or_backend_id"
    )


def _load_join_config() -> dict[str, JoinConfig]:
    raw = _load_key_config()
    default_cfg = raw.get("default", {}) if isinstance(raw, dict) else {}
    retailers_cfg = raw.get("retailers", {}) if isinstance(raw, dict) else {}

    def build(entry: Mapping[str, Any]) -> JoinConfig:
        return JoinConfig(
            sales_sku_field=str(entry.get("sales_sku_field", "sku")).strip() or "sku",
            catalog_variant_field=(
                str(entry.get("catalog_variant_field") or "variant_id").strip()
                if entry.get("catalog_variant_field") is not None
                else None
            ),
            catalog_parent_field=str(
                entry.get("catalog_parent_field", "parent_product_id")
            ).strip()
            or "parent_product_id",
        )

    default = build(default_cfg)
    result: dict[str, JoinConfig] = {"default": default}
    if isinstance(retailers_cfg, Mapping):
        for retailer, entry in retailers_cfg.items():
            if not isinstance(retailer, str):
                continue
            result[retailer.lower()] = build(
                entry if isinstance(entry, Mapping) else {}
            )
    return result


def _row_id(df: pl.DataFrame, name: str) -> pl.DataFrame:
    return df.with_row_count(name=name)


def _log_join_fanout(retailer: str, stage: str, joined: pl.DataFrame) -> None:
    if joined.is_empty() or "_row_id" not in joined.columns:
        return
    joined_rows = joined.height
    unique_sales_rows = joined.get_column("_row_id").n_unique()
    if joined_rows <= unique_sales_rows:
        return
    top_dupes = (
        joined.group_by("_row_id")
        .len()
        .filter(pl.col("len") > 1)
        .sort("len", descending=True)
        .head(10)
        .to_dicts()
    )
    logging.error(
        "Join fanout detected for %s at %s: joined_rows=%s unique_sales_rows=%s top_duplicate_row_ids=%s",
        retailer,
        stage,
        joined_rows,
        unique_sales_rows,
        top_dupes,
    )


def _keep_unique_right_keys(
    df: pl.DataFrame, *, key: str, label: str
) -> tuple[pl.DataFrame, int]:
    """Return ``df`` filtered to rows where ``key`` appears exactly once (and is non-empty)."""
    if df.is_empty() or key not in df.columns:
        return pl.DataFrame(), 0
    base = df.drop_nulls(subset=[key]).filter(
        pl.col(key).cast(pl.Utf8).str.strip_chars() != ""
    )
    if base.is_empty():
        return pl.DataFrame(), 0
    counts = base.group_by(key).len()
    dupes = counts.filter(pl.col("len") > 1)
    duplicate_keys = dupes.height
    if duplicate_keys:
        logging.warning("%s: %s duplicate join keys on %s", label, duplicate_keys, key)
    unique_keys = counts.filter(pl.col("len") == 1).select(key)
    return base.join(unique_keys, on=key, how="inner"), duplicate_keys


def _stable_variant_attributes(
    variants: pl.DataFrame,
    *,
    parent_columns: set[str],
) -> pl.DataFrame:
    """Collapse variant-level attributes to 1 row per parent_product_id when stable across variants."""
    if variants.is_empty() or "parent_product_id" not in variants.columns:
        return pl.DataFrame()

    exclude = {
        "retailer",
        "parent_product_id",
        "parent_product_id_norm",
        "variant_id",
        "variant_id_norm",
        "variant_key",
        "canonical_id",
        "brand_norm",
        "product_name_norm",
        "shade_name_raw",
        "shade_name_normalized",
        "size_text_raw",
        "price_raw",
        "currency",
        "barcode",
        "availability",
        "swatch_image_url",
        "hero_image_url",
        "variant_description",
    }
    placeholders = {"", "null", "none", "n/a", "na", "unknown"}

    agg_exprs: list[pl.Expr] = []
    for col, dtype in variants.schema.items():
        if col in exclude or col in parent_columns:
            continue
        # Skip complex dtypes; keep this conservative.
        if str(dtype).startswith("list") or str(dtype).startswith("struct"):
            continue

        col_expr = pl.col(col)
        if dtype == pl.Utf8:
            cleaned = col_expr.cast(pl.Utf8).str.strip_chars()
            lowered = cleaned.str.to_lowercase()
            meaningful = (
                cleaned.is_not_null()
                & (cleaned != "")
                & lowered.is_in(list(placeholders)).not_()
            )
            stable_value = (
                pl.when(col_expr.filter(meaningful).n_unique() <= 1)
                .then(col_expr.filter(meaningful).first())
                .otherwise(pl.lit(None))
                .alias(col)
            )
            agg_exprs.append(stable_value)
        else:
            meaningful = col_expr.is_not_null()
            stable_value = (
                pl.when(col_expr.filter(meaningful).n_unique() <= 1)
                .then(col_expr.filter(meaningful).first())
                .otherwise(pl.lit(None))
                .alias(col)
            )
            agg_exprs.append(stable_value)

    if not agg_exprs:
        return pl.DataFrame()

    return variants.group_by("parent_product_id", maintain_order=True).agg(agg_exprs)


def _join_retailer(
    retailer: str,
    sales_df: pl.DataFrame,
    variants_df: pl.DataFrame,
    cfg: JoinConfig,
    manifest: dict,
    parents_df: pl.DataFrame | None = None,
) -> pl.DataFrame:
    # Filter by retailer
    sret = sales_df.filter(pl.col("merchant") == retailer)
    vret = variants_df.filter(pl.col("retailer") == retailer)
    if sret.is_empty() or vret.is_empty():
        manifest["retailers"].append(
            {
                "retailer": retailer,
                "sales_rows": sret.height,
                "catalog_rows": vret.height,
                "joined_rows": 0,
            }
        )
        return pl.DataFrame()

    # Price bands for this retailer
    category_norms = sret.get_column("category").unique().to_list()
    price_bands = _compute_price_bands(vret, categories=category_norms)

    # Prepare for joins
    sret = _row_id(sret, "_row_id")
    vret = vret.with_columns(
        pl.col("variant_id").cast(pl.Utf8).str.strip_chars().alias("variant_id_norm"),
        pl.col("parent_product_id")
        .cast(pl.Utf8)
        .str.strip_chars()
        .alias("parent_product_id_norm"),
    )
    join_key = cfg.catalog_variant_field or "variant_id"
    _log_duplicate_keys(
        vret, subset=(join_key,), label=f"Catalog variants ({retailer})"
    )

    matched_row_ids: set[int] = set()
    parts: list[pl.DataFrame] = []
    matched_primary = 0
    matched_variant_name = 0
    matched_product = 0
    skip_primary_category_filter = _skip_kiko_primary_category_filter(retailer, cfg)

    # Primary join on SKU/variant_id
    if cfg.catalog_variant_field:
        left_key = cfg.sales_sku_field
        right_key = cfg.catalog_variant_field
        if left_key in sret.columns and right_key in vret.columns:
            s_join = sret.with_columns(
                pl.col(left_key).cast(pl.Utf8).str.strip_chars().alias("_join_key")
            )
            v_join = vret.with_columns(
                pl.col(right_key).cast(pl.Utf8).str.strip_chars().alias("_join_key")
            )
            primary = s_join.join(
                v_join, on="_join_key", how="inner", suffix="_cat"
            ).drop("_join_key")
            if not skip_primary_category_filter:
                primary = _enforce_join_category_match(
                    primary,
                    retailer=retailer,
                    stage=f"primary_join[{left_key}->{right_key}]",
                )
            _log_join_fanout(
                retailer, f"primary_join[{left_key}->{right_key}]", primary
            )
            if not primary.is_empty():
                matched_ids = [int(x) for x in primary.get_column("_row_id").to_list()]
                matched_row_ids.update(matched_ids)
                matched_primary = primary.height
                parts.append(primary)

    remaining = (
        sret
        if not matched_row_ids
        else sret.filter(~pl.col("_row_id").is_in(list(matched_row_ids)))
    )

    # Secondary: match variants by name when SKU is missing/invalid (unique-or-nothing).
    if not remaining.is_empty() and {"canonical_id", "brand_norm"}.issubset(
        set(remaining.columns)
    ):
        shade_source = None
        if "shade_name_normalized" in vret.columns:
            shade_source = pl.col("shade_name_normalized")
        elif "shade_name_raw" in vret.columns:
            shade_source = pl.col("shade_name_raw")

        if shade_source is not None and "variant_hint_norm" in remaining.columns:
            v_hint = vret.with_columns(
                _normalize_join_text(shade_source).alias("_shade_norm")
            )
            v_hint = v_hint.with_columns(
                pl.concat_str(
                    [pl.col("canonical_id"), pl.col("_shade_norm")], separator="::"
                ).alias("_variant_hint_key")
            )
            v_hint_unique, _ = _keep_unique_right_keys(
                v_hint,
                key="_variant_hint_key",
                label=f"{retailer} catalog variant_hint_key",
            )
            sales_hint = remaining.with_columns(
                pl.concat_str(
                    [pl.col("canonical_id"), pl.col("variant_hint_norm")],
                    separator="::",
                ).alias("_variant_hint_key")
            ).drop_nulls(subset=["_variant_hint_key"])
            sales_hint = sales_hint.filter(
                pl.col("_variant_hint_key").cast(pl.Utf8).str.strip_chars() != ""
            )
            if not sales_hint.is_empty() and not v_hint_unique.is_empty():
                hint_join = sales_hint.join(
                    v_hint_unique,
                    on="_variant_hint_key",
                    how="inner",
                    suffix="_cat",
                )
                hint_join = _enforce_join_category_match(
                    hint_join,
                    retailer=retailer,
                    stage="variant_name_join[canonical_id+shade]",
                )
                _log_join_fanout(
                    retailer, "variant_name_join[canonical_id+shade]", hint_join
                )
                if not hint_join.is_empty():
                    matched_ids = [
                        int(x) for x in hint_join.get_column("_row_id").to_list()
                    ]
                    matched_row_ids.update(matched_ids)
                    matched_variant_name += hint_join.height
                    parts.append(hint_join.drop(["_variant_hint_key", "_shade_norm"]))

        remaining = (
            sret
            if not matched_row_ids
            else sret.filter(~pl.col("_row_id").is_in(list(matched_row_ids)))
        )
        if (
            not remaining.is_empty()
            and "product_description_norm" in remaining.columns
            and "brand_norm" in remaining.columns
        ):
            shade_display = pl.coalesce(
                [
                    (
                        pl.col("shade_name_raw")
                        if "shade_name_raw" in vret.columns
                        else pl.lit(None)
                    ),
                    (
                        pl.col("shade_name_normalized")
                        if "shade_name_normalized" in vret.columns
                        else pl.lit(None)
                    ),
                ]
            )
            full_name_raw = (
                pl.when(
                    shade_display.is_not_null()
                    & (shade_display.cast(pl.Utf8).str.strip_chars() != "")
                )
                .then(
                    pl.concat_str(
                        [pl.col("product_name"), shade_display], separator=" — "
                    )
                )
                .otherwise(pl.col("product_name"))
            )
            v_full = vret.with_columns(
                _normalize_join_text(full_name_raw).alias("_variant_full_name_norm")
            )
            v_full = v_full.with_columns(
                pl.concat_str(
                    [pl.col("brand_norm"), pl.col("_variant_full_name_norm")],
                    separator="::",
                ).alias("_variant_full_key")
            )
            v_full_unique, _ = _keep_unique_right_keys(
                v_full,
                key="_variant_full_key",
                label=f"{retailer} catalog variant_full_key",
            )
            sales_full = remaining.with_columns(
                pl.concat_str(
                    [pl.col("brand_norm"), pl.col("product_description_norm")],
                    separator="::",
                ).alias("_variant_full_key")
            ).drop_nulls(subset=["_variant_full_key"])
            sales_full = sales_full.filter(
                pl.col("_variant_full_key").cast(pl.Utf8).str.strip_chars() != ""
            )
            if not sales_full.is_empty() and not v_full_unique.is_empty():
                full_join = sales_full.join(
                    v_full_unique,
                    on="_variant_full_key",
                    how="inner",
                    suffix="_cat",
                )
                full_join = _enforce_join_category_match(
                    full_join,
                    retailer=retailer,
                    stage="variant_name_join[brand+full_name]",
                )
                _log_join_fanout(
                    retailer, "variant_name_join[brand+full_name]", full_join
                )
                if not full_join.is_empty():
                    matched_ids = [
                        int(x) for x in full_join.get_column("_row_id").to_list()
                    ]
                    matched_row_ids.update(matched_ids)
                    matched_variant_name += full_join.height
                    parts.append(
                        full_join.drop(["_variant_full_key", "_variant_full_name_norm"])
                    )

    # Tertiary: product-level join (no variant fanout).
    remaining = (
        sret
        if not matched_row_ids
        else sret.filter(~pl.col("_row_id").is_in(list(matched_row_ids)))
    )
    if (
        not remaining.is_empty()
        and parents_df is not None
        and not parents_df.is_empty()
        and "canonical_id" in remaining.columns
    ):
        parents_ret = parents_df.filter(pl.col("retailer") == retailer)
        if not parents_ret.is_empty() and "canonical_id" in parents_ret.columns:
            stable_variant_df = _stable_variant_attributes(
                variants=vret, parent_columns=set(parents_ret.columns)
            )
            if not stable_variant_df.is_empty():
                parents_ret = parents_ret.join(
                    stable_variant_df, on="parent_product_id", how="left"
                )

            parents_unique, _ = _keep_unique_right_keys(
                parents_ret,
                key="canonical_id",
                label=f"{retailer} catalog parents canonical_id",
            )
            if not parents_unique.is_empty():
                product_join = remaining.join(
                    parents_unique,
                    on="canonical_id",
                    how="inner",
                    suffix="_cat",
                )
                product_join = _enforce_join_category_match(
                    product_join,
                    retailer=retailer,
                    stage="product_join[canonical_id]",
                )
                _log_join_fanout(retailer, "product_join[canonical_id]", product_join)
                if not product_join.is_empty():
                    matched_ids = [
                        int(x) for x in product_join.get_column("_row_id").to_list()
                    ]
                    matched_row_ids.update(matched_ids)
                    matched_product = product_join.height
                    parts.append(product_join)

    joined = pl.concat(parts, how="diagonal_relaxed") if parts else pl.DataFrame()
    if not skip_primary_category_filter:
        joined = _enforce_join_category_match(
            joined, retailer=retailer, stage="post_join"
        )
    _log_join_fanout(retailer, "post_join", joined)
    if joined.is_empty():
        manifest["retailers"].append(
            {
                "retailer": retailer,
                "sales_rows": sret.height,
                "catalog_rows": vret.height,
                "joined_rows": 0,
                "matched_primary": 0,
                "matched_variant_name": 0,
                "matched_product": 0,
                "unmatched_rows": sret.height,
            }
        )
        return joined

    matched_primary = parts[0].height if parts else 0
    manifest["retailers"].append(
        {
            "retailer": retailer,
            "sales_rows": sret.height,
            "catalog_rows": vret.height,
            "joined_rows": joined.height,
            "matched_primary": matched_primary,
            "matched_variant_name": matched_variant_name,
            "matched_product": matched_product,
            "unmatched_rows": sret.height - len(matched_row_ids),
        }
    )

    # Attach price bands
    if not price_bands.is_empty():
        joined = joined.join(
            price_bands,
            left_on="variant_id_norm",
            right_on="variant_id_norm",
            how="left",
        )

    # Pareto per retailer slice
    pareto_df = _compute_pareto(joined)
    if not pareto_df.is_empty():
        joined = joined.join(pareto_df, on="parent_product_id", how="left")

    # Ensure category column aligns with catalog label for downstream filters
    if "category_label" in joined.columns:
        joined = joined.with_columns(
            pl.col("category_label")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("category")
        )

    # Clean up helper columns
    if "_row_id" in joined.columns:
        joined = joined.drop("_row_id")

    # Unique counts and unmatched tracking for manifest
    joined_variants = (
        set(joined.get_column("variant_id").drop_nulls().to_list())
        if "variant_id" in joined.columns
        else set()
    )
    joined_parents = (
        set(joined.get_column("parent_product_id").drop_nulls().to_list())
        if "parent_product_id" in joined.columns
        else set()
    )

    unmatched_sales = (
        sret
        if not matched_row_ids
        else sret.filter(~pl.col("_row_id").is_in(list(matched_row_ids)))
    )
    unmatched_catalog = vret
    if joined_variants:
        unmatched_catalog = unmatched_catalog.filter(
            ~pl.col("variant_id").is_in(list(joined_variants))
        )

    # Recency buckets for sales-only unmatched
    recent_6m = recent_12m = 0
    latest_month = None
    latest_period = None
    if "month" in sret.columns:
        month_dtype = sret.schema.get("month")
        is_temporal_month = bool(
            month_dtype == pl.Date
            or month_dtype == pl.Datetime
            or (
                month_dtype is not None
                and str(month_dtype).lower().startswith("datetime")
            )
        )
        if is_temporal_month:
            latest_month = sret.select(pl.col("month").max()).item()
            if latest_month:
                cutoff_6 = latest_month - timedelta(days=180)
                cutoff_12 = latest_month - timedelta(days=365)
                recent_6m = unmatched_sales.filter(pl.col("month") >= cutoff_6).height
                recent_12m = unmatched_sales.filter(pl.col("month") >= cutoff_12).height
        elif "period" in sret.columns:
            latest_period = sret.select(pl.col("period").drop_nulls().max()).item()

    manifest["retailers"][-1].update(
        {
            "unique_counts": {
                "sales_sku": (
                    sret.get_column("sku").n_unique() if "sku" in sret.columns else 0
                ),
                "sales_canonical": (
                    sret.get_column("canonical_id").n_unique()
                    if "canonical_id" in sret.columns
                    else 0
                ),
                "catalog_variants": (
                    vret.get_column("variant_id").n_unique()
                    if "variant_id" in vret.columns
                    else 0
                ),
                "catalog_parents": (
                    vret.get_column("parent_product_id").n_unique()
                    if "parent_product_id" in vret.columns
                    else 0
                ),
                "matched_variants": len(joined_variants),
                "matched_parents": len(joined_parents),
                "unmatched_sales_sku": (
                    unmatched_sales.get_column("sku").n_unique()
                    if "sku" in unmatched_sales.columns
                    else 0
                ),
                "unmatched_catalog_variants": (
                    unmatched_catalog.get_column("variant_id").n_unique()
                    if "variant_id" in unmatched_catalog.columns
                    else 0
                ),
                "unmatched_catalog_parents": (
                    unmatched_catalog.get_column("parent_product_id").n_unique()
                    if "parent_product_id" in unmatched_catalog.columns
                    else 0
                ),
            },
            "recency": {
                "latest_month": latest_month.isoformat() if latest_month else None,
                "latest_period": latest_period,
                "unmatched_sales_recent_6m": recent_6m,
                "unmatched_sales_recent_12m": recent_12m,
            },
        }
    )

    # Optional audit CSVs
    if not unmatched_sales.is_empty():
        sales_out = SALES_DIR / f"unmatched_sales_{retailer}.csv"
        sales_cols = [
            c
            for c, dt in unmatched_sales.schema.items()
            if c not in {"_row_id"}
            and not str(dt).startswith("struct")
            and not str(dt).startswith("list")
        ]
        try:
            unmatched_sales.select(sales_cols).write_csv(sales_out)
            manifest["retailers"][-1]["unmatched_sales_path"] = str(sales_out)
        except Exception:
            pass
    if not unmatched_catalog.is_empty():
        cat_out = SALES_DIR / f"unmatched_catalog_{retailer}.csv"
        catalog_cols = [
            col
            for col in (
                "retailer",
                "parent_product_id",
                "variant_id",
                "brand",
                "product_name",
            )
            if col in unmatched_catalog.columns
        ]
        catalog_export = (
            unmatched_catalog.select(catalog_cols).unique()
            if catalog_cols
            else pl.DataFrame()
        )

        if parents_df is not None and not parents_df.is_empty():
            parents_ret = parents_df.filter(pl.col("retailer") == retailer)
            parent_cols = [
                col
                for col in ("parent_product_id", "brand", "product_name", "pdp_url")
                if col in parents_ret.columns
            ]
            if not parents_ret.is_empty() and parent_cols:
                catalog_export = catalog_export.join(
                    parents_ret.select(parent_cols),
                    on="parent_product_id",
                    how="left",
                    suffix="_parent",
                )
                if "brand_parent" in catalog_export.columns:
                    catalog_export = catalog_export.with_columns(
                        pl.coalesce(
                            [
                                (
                                    pl.col("brand")
                                    if "brand" in catalog_export.columns
                                    else pl.lit(None)
                                ),
                                pl.col("brand_parent"),
                            ]
                        ).alias("brand")
                    ).drop("brand_parent")
                if "product_name_parent" in catalog_export.columns:
                    catalog_export = catalog_export.with_columns(
                        pl.coalesce(
                            [
                                (
                                    pl.col("product_name")
                                    if "product_name" in catalog_export.columns
                                    else pl.lit(None)
                                ),
                                pl.col("product_name_parent"),
                            ]
                        ).alias("product_name")
                    ).drop("product_name_parent")
                if "pdp_url_parent" in catalog_export.columns:
                    catalog_export = catalog_export.rename(
                        {"pdp_url_parent": "pdp_url"}
                    )

        desired_cols = [
            col
            for col in (
                "retailer",
                "parent_product_id",
                "variant_id",
                "brand",
                "product_name",
                "pdp_url",
            )
            if col in catalog_export.columns
        ]
        catalog_export = (
            catalog_export.select(desired_cols).unique()
            if desired_cols
            else pl.DataFrame()
        )

        try:
            catalog_export.write_csv(cat_out)
            manifest["retailers"][-1]["unmatched_catalog_path"] = str(cat_out)
        except Exception:
            pass

    return joined


def _run_join_stage(
    *,
    sales_df: pl.DataFrame,
    sales_paths: list[Path],
    variants_df: pl.DataFrame,
    parents_df: pl.DataFrame,
    variant_paths: list[Path],
    resolution_run_id: str,
    resolution_consensus_rows: int,
    web_checkpoint_rows: int,
    web_checkpoint_chunks: int,
    web_checkpoint_paths: list[Path],
) -> None:
    if logging.getLogger().isEnabledFor(logging.INFO):
        logging.info(
            "Combined raw sales: rows=%s cols=%s", sales_df.height, sales_df.width
        )

    sales_df = _normalize_sales(sales_df)
    FULL_SALES_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    sales_df.write_parquet(FULL_SALES_OUTPUT)
    logging.info("Wrote normalized full sales to %s", FULL_SALES_OUTPUT)

    merchants = sorted(
        {
            m
            for m in sales_df.get_column("merchant").unique().to_list()
            if isinstance(m, str) and m
        }
    )
    if not merchants:
        raise SystemExit("No merchants found in sales file.")

    cfg_map = _load_join_config()
    default_cfg = cfg_map.get("default")
    if not isinstance(default_cfg, JoinConfig):
        default_cfg = JoinConfig("sku", "variant_id", "parent_product_id")
    join_cfgs: dict[str, JoinConfig] = {}
    for merchant in merchants:
        cfg = cfg_map.get(merchant)
        if isinstance(cfg, JoinConfig):
            join_cfgs[merchant] = cfg
        elif isinstance(cfg, Mapping):
            join_cfgs[merchant] = JoinConfig(
                sales_sku_field=str(cfg.get("sales_sku_field", "sku")).strip() or "sku",
                catalog_variant_field=(
                    str(cfg.get("catalog_variant_field") or "variant_id").strip()
                    if cfg.get("catalog_variant_field") is not None
                    else None
                ),
                catalog_parent_field=str(
                    cfg.get("catalog_parent_field", "parent_product_id")
                ).strip()
                or "parent_product_id",
            )
        else:
            join_cfgs[merchant] = default_cfg

    manifest: Dict[str, Any] = {
        "sales_dataset": ACTIVE_SALES_DATASET,
        "sales_dataset_dir": str(SALES_DATASET_DIR),
        "sales_join_output_dir": str(SALES_DIR),
        "shared_mapping_dir": str(MAPPING_DIR),
        "sales_files": [str(path) for path in sales_paths],
        "sales_mtime": [path.stat().st_mtime for path in sales_paths],
        "variants_files": [str(p) for p in variant_paths],
        "variants_mtime": [p.stat().st_mtime for p in variant_paths if p.exists()],
        "retailers": [],
        "generated_at": date.today().isoformat(),
        "full_sales_path": str(FULL_SALES_OUTPUT),
        "postfill_attribute_cache_dir": str(POSTFILL_ATTRIBUTE_CACHE_DIR),
        "postfill_attribute_parents_path": str(POSTFILL_PARENTS_OUTPUT),
        "postfill_attribute_variants_path": str(POSTFILL_VARIANTS_OUTPUT),
        "postfill_attribute_parents_all_path": str(POSTFILL_PARENTS_ALL_OUTPUT),
        "postfill_attribute_combined_path": str(POSTFILL_COMBINED_OUTPUT),
        "attribute_resolution_consensus_rows": resolution_consensus_rows,
        "attribute_resolution_run_id": resolution_run_id,
        "attribute_web_fill_checkpoint_dir": str(WEB_FILL_AUDIT_CHECKPOINT_DIR),
        "attribute_web_fill_checkpoint_rows": web_checkpoint_rows,
        "attribute_web_fill_checkpoint_chunks": web_checkpoint_chunks,
        "attribute_web_fill_checkpoint_latest": (
            str(web_checkpoint_paths[-1]) if web_checkpoint_paths else ""
        ),
    }

    joined_parts: list[pl.DataFrame] = []
    for merchant in merchants:
        cfg = join_cfgs.get(merchant)
        if not cfg:
            continue
        joined = _join_retailer(
            merchant, sales_df, variants_df, cfg, manifest, parents_df
        )
        if not joined.is_empty():
            joined = joined.with_columns(pl.lit(merchant).alias("merchant"))
            joined_parts.append(joined)

    if not joined_parts:
        raise SystemExit("No joined data produced.")

    joined_df = pl.concat(joined_parts, how="diagonal_relaxed")
    JOINED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    joined_df.write_parquet(JOINED_OUTPUT)
    MANIFEST_OUTPUT.write_text(json.dumps(manifest, indent=2))
    logging.info("Wrote %s rows to %s", joined_df.height, JOINED_OUTPUT)
    logging.info("Wrote manifest to %s", MANIFEST_OUTPUT)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run dataset-specific sales-join outputs from the shared mapped "
            "PDP attribute cache."
        )
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help=(
            "Sales dataset name. Uses data/pdp/sales_data for 'default' and "
            "data/pdp/sales_data/datasets/<name> for named datasets. "
            f"If omitted, reads {SALES_DATASET_ENV_VAR}."
        ),
    )
    return parser.parse_args()


def main(
    dataset: str | None = None,
    stage: str = "join",
    mapping_steps: Sequence[str] | str | None = None,
    mapping_retailers: Sequence[str] | str | None = None,
) -> None:
    """Run the downstream sales-join stage only."""
    stage_norm = str(stage or "join").strip().lower()
    if stage_norm != "join":
        raise SystemExit(
            "Attribute fill moved upstream; run scripts/brand_web_search_attribute_fill.py "
            "for brand-site web search or scripts/export_pdp_attributes.py --run-vlm "
            "for VLM."
        )
    if mapping_steps is not None or mapping_retailers is not None:
        raise SystemExit(
            "Attribute fill options are not valid for prejoin sales. Run "
            "scripts/brand_web_search_attribute_fill.py for brand-site web search."
        )

    active_dataset = _configure_sales_paths(dataset)
    logging.info(
        (
            "Using sales dataset '%s'. inputs=%s join_outputs=%s shared_mapping=%s "
            "(override with --dataset or %s)."
        ),
        active_dataset,
        SALES_CSV_DIR,
        SALES_DIR,
        MAPPING_DIR,
        SALES_DATASET_ENV_VAR,
    )
    logging.info("Running prejoin stage: join")

    sales_df, sales_paths = _load_sales_csvs()
    parents_df, variants_df, variant_paths, cache_source = (
        _load_postfill_attribute_cache()
    )
    logging.info(
        (
            "Loaded attribute cache for join stage: source=%s "
            "variant_files=%s shared_mapping_dir=%s"
        ),
        cache_source,
        len(variant_paths),
        MAPPING_DIR,
    )
    if cache_source.endswith("_plus_base_delta"):
        _write_postfill_attribute_cache(
            parents_df=parents_df,
            variants_df=variants_df,
            parents_all_df=parents_df,
        )
        logging.info(
            "Updated shared post-fill cache from base delta at %s",
            POSTFILL_ATTRIBUTE_CACHE_DIR,
        )

    _run_join_stage(
        sales_df=sales_df,
        sales_paths=sales_paths,
        variants_df=variants_df,
        parents_df=parents_df,
        variant_paths=variant_paths,
        resolution_run_id="",
        resolution_consensus_rows=0,
        web_checkpoint_rows=0,
        web_checkpoint_chunks=0,
        web_checkpoint_paths=[],
    )


def run_sales_join(dataset: str | None = None) -> None:
    """Run dataset-specific sales join outputs from the shared mapped cache."""
    main(dataset=dataset, stage="join")


def cli_main() -> None:
    args = _parse_args()
    main(dataset=args.dataset)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    cli_main()
