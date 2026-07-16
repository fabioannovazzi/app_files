from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
root_str = str(REPO_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from modules.pdp.attribute_table_templates import (
    ATTRIBUTE_TABLE_DIRNAME,
    ATTRIBUTE_TABLE_TEMPLATE_FILES,
    build_attribute_table_frames,
    write_attribute_table_artifacts,
)
from modules.pdp.cdp_retailer_strategy import strategy_for_retailer
from modules.pdp.postgres_compat import connect_pdp_database, pdp_database_exists
from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    add_pdp_store_path_argument,
)
from modules.pdp.review_theme_codebook import ensure_review_theme_schema
from modules.pdp.signal_quality import (
    DEFAULT_SIGNAL_QUALITY_CONFIG,
    normalize_signal_text,
    parse_signal_bundle_key,
    signal_component_family,
)
from modules.pdp.sort_sequence_quality import (
    EXCLUDED_RANKED_SORT_MODES,
    HIGH_TOP_WINDOW_OVERLAP_THRESHOLD,
    SORT_TOP_WINDOW_SIZE,
)
from modules.pdp.store import PDPStore
from modules.pdp.ulta_taxonomy_bridge import (
    bridged_ulta_category_keys,
    canonicalize_ulta_category_key,
)
from modules.pdp.web_shelf_discovery import (
    discover_web_shelves,
    empty_web_shelf_outputs,
    refine_selected_shelves_with_third_attribute,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_schema_and_column_names

CSV_LIST_SEPARATOR = " | "
LOGGER = logging.getLogger(__name__)
MAX_EXPORTED_REVIEW_SNIPPETS = 5
DEFAULT_CLI_ROOT = Path("data/pdp/cli")
DEFAULT_OUTPUT_ROOT = Path("data/pdp/reports/packages/launch")
MIN_SORT_SEQUENCE_PRODUCTS = 5
TOP_SELLER_COHORT_SHARE = 0.20
PARETO_B_COHORT_SHARE = 0.30
REVIEW_THEME_MIN_FOCUS_REVIEWED_PRODUCTS = 3
REVIEW_THEME_MIN_BASELINE_REVIEWED_PRODUCTS = 6
REVIEW_THEME_MIN_FOCUS_PRODUCTS_WITH_THEME = 2
REVIEW_THEME_MIN_ABS_PRODUCT_RATE_DELTA = 0.08
REVIEW_THEME_MIN_RATIO = 1.35
REVIEW_THEME_MIN_ABS_POLARITY_RATE_DELTA = 0.01
REVIEW_THEME_STRONG_ABS_POLARITY_RATE_DELTA = 0.03
REVIEW_THEME_MIN_POLARITY_RATIO = 1.20
REVIEW_THEME_MIN_FOCUS_PRODUCTS_WITH_POLARITY = 2
REVIEW_THEME_MIN_BASELINE_PRODUCTS_WITH_POLARITY = 3
REVIEW_THEME_TABLE_STAKES_MIN_REVIEW_MENTION_RATE = 0.30
REVIEW_THEME_TABLE_STAKES_MIN_PRODUCT_MENTION_RATE = 0.50
REVIEW_THEME_TABLE_STAKES_MAX_ABS_NET_DELTA = 0.03
REVIEW_THEME_MAX_SURFACED_PER_COMPARISON = 12
WEB_SHELF_ALPHAS = (0.0, 0.7, 1.0, 1.2)
WEB_SHELF_CENTRAL_ALPHA = 1.0
WEB_SHELF_MIN_SKUS = 5
WEB_SHELF_MIN_BRANDS = 2
WEB_SHELF_MAX_SELECTED_SHELVES = 100
WEB_SHELF_REFINEMENT_MIN_SKUS = 2
WEB_SHELF_REFINEMENT_MIN_BRANDS = 1
WEB_SHELF_MAX_REFINEMENT_BASE_SHELVES = 10
PACK_IMAGE_HARD_LIMIT = 200
RECENT_SORT_MODE_FALLBACKS = ("new_arrivals", "newest", "most_recent")
TOP_SELLER_SORT_MODE_FALLBACKS = (
    "best_sellers",
    "best_selling",
    "top_sellers",
    "most_popular",
)
SALE_PRESSURE_SORT_MODE_FALLBACKS = (
    "sales_first",
    "sale_first",
    "sale",
    "promotions",
    "promotion",
    "clearance",
)
APP_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_CATEGORIES_DIR = APP_ROOT / "config" / "attribute_taxonomy" / "categories"
OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
SAKS_PARENT_FROM_URL_RE = re.compile(
    r"/product/[^/?#]*?([0-9]{8,})\.html",
    re.IGNORECASE,
)
MAPPED_EXPORT_METADATA_COLUMNS = {
    "retailer",
    "parent_product_id",
    "pdp_url",
    "brand",
    "product_name",
    "canonical_id",
    "canonical_owner",
    "canonical_accept",
    "category_key",
    "category_id",
    "category_label",
    "category_path",
    "description",
    "hero_image_url",
    "canonical_id_export",
}
RESOLUTION_SLOT_CONFIG = {
    "finish": {
        "ulta_column": "finish",
        "mapped_candidates": ["finish", "finish effect"],
    },
    "coverage": {
        "ulta_column": "coverage",
        "mapped_candidates": ["coverage", "color payoff"],
    },
    "color": {
        "ulta_column": "color lips",
        "filter_candidates": ["color"],
        "rollup_candidates": ["available_color_families"],
        "mapped_candidates": ["color family", "shade family"],
    },
    "form": {
        "ulta_column": "form",
        "mapped_candidates": [
            "form",
            "format",
            "product type",
            "applicator type",
            "treatment type",
        ],
    },
}
PRICE_BAND_LABELS = [
    "under_10",
    "10_to_14_99",
    "15_to_24_99",
    "25_to_39_99",
    "40_plus",
]
PLACEHOLDER_VALUES = {
    "",
    "n/a",
    "n/a (not stated)",
    "na",
    "unknown",
    "null",
    "none",
    "not stated",
    "not in taxonomy",
    "false",
    "true",
    "0",
    "1",
    "yes",
    "no",
}
MIN_RECENT_COUNT_BY_BUNDLE_SIZE = {
    2: 3,
    3: 3,
}
MIN_RECENT_BRAND_COUNT = 2
TOP_SELLER_REVIEW_VALIDATION_LIMITS = {
    2: 20,
    3: 10,
}
TOP_SELLER_REVIEW_VALIDATION_PRODUCTS_PER_BUNDLE = 3
ANALYSIS_EXCLUDED_ATTRIBUTE_COLUMNS = {
    "canonical_id",
    "canonical_owner",
    "canonical_accept",
    "sales_share",
    "cumulative_sales_share",
    "pareto_rank",
    "pareto_bucket",
    "price_band",
}
SIGNAL_INSIGHT_METADATA_SCHEMA = {
    "signal_usefulness": pl.Utf8,
    "signal_role": pl.Utf8,
    "differentiating_component_count": pl.Int64,
    "category_center_component_count": pl.Int64,
    "insight_adjusted_signal_score": pl.Float64,
    "signal_quality_note": pl.Utf8,
    "signal_role_note": pl.Utf8,
}
PRO_HIDDEN_SIGNAL_COLUMNS = frozenset({"category_center_component_count"})
REVIEW_SNIPPET_FIELDS = ("headline", "comment", "rating", "created_date")


class PackageBuildSkipped(RuntimeError):
    """Raised when a package has insufficient source data to build usefully."""


RETAILER_CATEGORY_BUNDLE_COLUMNS: dict[tuple[str, str], list[str]] = {
    (
        "ulta",
        "blush",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "benefits",
        "skin benefits",
        "preference",
    ],
    (
        "ulta",
        "bronzer",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "benefits",
        "undertone",
        "preference",
    ],
    (
        "ulta",
        "concealer",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "concealer type",
        "tone depth",
        "skin benefits",
    ],
    (
        "ulta",
        "eyebrow",
    ): [
        "resolved_form",
        "resolved_finish",
        "applicator type",
        "benefits",
        "wear claims",
    ],
    (
        "ulta",
        "eyeliner",
    ): [
        "resolved_form",
        "resolved_finish",
        "color family",
        "applicator type",
        "pigment level",
        "wear claims",
        "resistance claims",
        "safety claims",
    ],
    (
        "ulta",
        "eyeshadow",
    ): [
        "resolved_form",
        "resolved_finish",
        "color family",
        "pigmentation",
        "palette type",
        "color story",
    ],
    (
        "ulta",
        "foundation",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "skin type",
        "skin benefits",
        "benefits",
        "preference",
    ],
    (
        "ulta",
        "highlighter",
    ): [
        "resolved_form",
        "resolved_finish",
        "glow intensity",
        "sparkle content",
        "application areas",
        "wear resistance",
    ],
    (
        "ulta",
        "lip_gloss",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "benefits",
        "applicator type",
        "product type",
        "preference",
    ],
    (
        "ulta",
        "lipstick",
    ): [
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
        "benefits",
        "wear claims",
        "preference",
    ],
    (
        "ulta",
        "mascara",
    ): [
        "effect",
        "formula type",
        "applicator shape",
        "bristle material",
        "wear claims",
        "water resistance",
        "color family",
    ],
    (
        "saloncentric",
        "permanent",
    ): [
        "product form",
        "product benefit",
        "ingredient preference",
        "hair condition",
        "haircolor tone",
    ],
    (
        "saksfifthavenue",
        "cashmere_sweaters",
    ): [
        "color",
        "style",
        "sleeve_length",
        "garment type",
        "neckline",
        "knit_detail",
    ],
}
FILTER_PRIMARY_ATTRIBUTE_OVERRIDES: dict[tuple[str, str], dict[str, str]] = {
    (
        "saloncentric",
        "permanent",
    ): {
        "product type": "product type",
        "product benefit": "benefit",
        "product form": "product form",
        "ingredient preference": "ingredient_preference",
        "haircolor tone": "haircolor_tone",
        "haircolor level": "haircolor level",
        "hair condition": "hair_condition",
    },
    (
        "saksfifthavenue",
        "low_top_sneakers",
    ): {
        "color": "color",
        "material": "material",
    },
    (
        "saksfifthavenue",
        "cashmere_sweaters",
    ): {
        "color": "color",
        "style": "style",
        "sleeve length": "sleeve_length",
        "lifestyle": "lifestyle",
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one retailer/category evidence pack from discovery, filter, and PDP scrape outputs."
    )
    parser.add_argument(
        "--retailer",
        required=True,
        help="Retailer key, e.g. ulta, saksfifthavenue, chewy, or saloncentric.",
    )
    parser.add_argument(
        "--category",
        dest="categories",
        action="append",
        default=None,
        help=(
            "Category key, e.g. lip_gloss. Repeat to build selected categories. "
            "Omit categories to build every discovered category for --retailer."
        ),
    )
    parser.add_argument(
        "--categories",
        dest="category_groups",
        nargs="+",
        default=None,
        help=(
            "One or more category keys. This is a convenience alternative to "
            "repeating --category."
        ),
    )
    parser.add_argument(
        "--all-categories",
        "--all",
        dest="all_categories",
        action="store_true",
        help=(
            "Explicitly build every category discovered in the PDP store for --retailer. "
            "This is also the default when no categories are supplied."
        ),
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop the bulk rebuild on the first failed retailer/category package.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=(
            "Optional discovery run folder used only for run summary metadata. "
            "Listing and filter observations are read from the PDP store."
        ),
    )
    add_pdp_store_path_argument(
        parser,
        default=DEFAULT_PDP_STORE_PATH,
        dest="pdp_store_path",
    )
    parser.add_argument(
        "--cli-root",
        type=Path,
        default=DEFAULT_CLI_ROOT,
        help="Root folder for run_pdp_parser exports.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=(
            "Root folder for evidence-pack outputs. Packages are written as "
            "<output-root>/<category>/<retailer>/ plus <category>_<retailer>.zip."
        ),
    )
    parser.add_argument(
        "--summary-path",
        type=Path,
        default=None,
        help=(
            "Optional CSV path for the bulk rebuild summary. Defaults to "
            "<output-root>/_bulk_rebuild_summary/<retailer>.csv for retailer "
            "rebuilds."
        ),
    )
    parser.add_argument(
        "--max-pack-images",
        type=int,
        default=PACK_IMAGE_HARD_LIMIT,
        help=(
            "Maximum product images to copy into each package. Use zero for a "
            "URL-only portable package. The builder hard-caps this at "
            f"{PACK_IMAGE_HARD_LIMIT}."
        ),
    )
    args = parser.parse_args()
    selected_categories = list(args.categories or [])
    for category_group in args.category_groups or []:
        selected_categories.append(category_group)
    args.categories = list(dict.fromkeys(selected_categories))
    delattr(args, "category_groups")
    if args.all_categories and args.categories:
        parser.error("--category cannot be combined with --all-categories.")
    if args.max_pack_images < 0:
        parser.error("--max-pack-images cannot be negative.")
    if args.max_pack_images > PACK_IMAGE_HARD_LIMIT:
        parser.error(f"--max-pack-images cannot exceed {PACK_IMAGE_HARD_LIMIT}.")
    return args


def _empty_listing_observations() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "crawl_ts": pl.Utf8,
            "retailer": pl.Utf8,
            "category_key": pl.Utf8,
            "source_surface": pl.Utf8,
            "sort_mode": pl.Utf8,
            "page": pl.Int64,
            "position": pl.Int64,
            "pdp_url": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "product_name": pl.Utf8,
            "brand": pl.Utf8,
            "has_new_badge": pl.Boolean,
            "listing_url": pl.Utf8,
        }
    )


def _empty_filter_observations() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "crawl_ts": pl.Utf8,
            "retailer": pl.Utf8,
            "category_key": pl.Utf8,
            "filter_family": pl.Utf8,
            "filter_value": pl.Utf8,
            "source_surface": pl.Utf8,
            "pdp_url": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "page": pl.Int64,
            "position": pl.Int64,
            "listing_url": pl.Utf8,
        }
    )


def _latest_discovery_crawl_ts(
    pdp_store_path: Path,
    *,
    retailer: str,
    category_key: str,
) -> str | None:
    if not pdp_database_exists(pdp_store_path):
        return None
    with connect_pdp_database(pdp_store_path) as conn:
        row = conn.execute(
            """
            SELECT MAX(crawl_ts)
            FROM retailer_listing_observations
            WHERE retailer = ?
              AND category_key = ?
            """,
            (retailer, category_key),
        ).fetchone()
        if row and row[0]:
            return str(row[0])
        row = conn.execute(
            """
            SELECT MAX(crawl_ts)
            FROM retailer_filter_observations
            WHERE retailer = ?
              AND category_key = ?
            """,
            (retailer, category_key),
        ).fetchone()
    return str(row[0]) if row and row[0] else None


def _load_discovery_observations_from_store(
    pdp_store_path: Path,
    *,
    retailer: str,
    category_key: str,
) -> tuple[pl.DataFrame, pl.DataFrame, str | None]:
    crawl_ts = _latest_discovery_crawl_ts(
        pdp_store_path,
        retailer=retailer,
        category_key=category_key,
    )
    if not crawl_ts:
        return _empty_listing_observations(), _empty_filter_observations(), None

    listing_columns = [
        "crawl_ts",
        "retailer",
        "category_key",
        "source_surface",
        "sort_mode",
        "page",
        "position",
        "pdp_url",
        "parent_product_id",
        "product_name",
        "brand",
        "has_new_badge",
        "listing_url",
    ]
    filter_columns = [
        "crawl_ts",
        "retailer",
        "category_key",
        "filter_family",
        "filter_value",
        "source_surface",
        "pdp_url",
        "parent_product_id",
        "page",
        "position",
        "listing_url",
    ]
    with connect_pdp_database(pdp_store_path) as conn:
        listing_rows = conn.execute(
            f"""
            SELECT {', '.join(listing_columns)}
            FROM retailer_listing_observations
            WHERE crawl_ts = ?
              AND retailer = ?
              AND category_key = ?
            """,
            (crawl_ts, retailer, category_key),
        ).fetchall()
        filter_rows = conn.execute(
            f"""
            SELECT {', '.join(filter_columns)}
            FROM retailer_filter_observations
            WHERE crawl_ts = ?
              AND retailer = ?
              AND category_key = ?
            """,
            (crawl_ts, retailer, category_key),
        ).fetchall()

    listing_df = (
        pl.DataFrame(listing_rows, schema=listing_columns, orient="row")
        if listing_rows
        else _empty_listing_observations()
    )
    filter_df = (
        pl.DataFrame(filter_rows, schema=filter_columns, orient="row")
        if filter_rows
        else _empty_filter_observations()
    )
    if not listing_df.is_empty():
        listing_df = listing_df.with_columns(
            pl.col("has_new_badge").cast(pl.Boolean, strict=False).fill_null(False)
        )
    return listing_df, filter_df, crawl_ts


def _discovered_retailer_categories(
    pdp_store_path: Path, *, retailer: str | None = None
) -> list[tuple[str, str]]:
    """Return retailer/category pairs with listing observations in the PDP store."""
    if not pdp_database_exists(pdp_store_path):
        return []
    query = """
        SELECT retailer, category_key
        FROM retailer_listing_observations
    """
    params: tuple[str, ...] = ()
    if retailer:
        query += " WHERE retailer = ?"
        params = (retailer,)
    query += " GROUP BY retailer, category_key ORDER BY retailer, category_key"
    with connect_pdp_database(pdp_store_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows if row[0] and row[1]]


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iter_text_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, pl.Series):
        return _iter_text_values(value.to_list())
    if isinstance(value, (list, tuple, set)):
        out: list[Any] = []
        for item in value:
            out.extend(_iter_text_values(item))
        return out
    return [value]


def _meaningful_text_values(value: Any) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in _iter_text_values(value):
        text = _normalize_text(item)
        if not text:
            continue
        if text.casefold() in PLACEHOLDER_VALUES:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(text)
    return values


def _join_meaningful_text_values(value: Any) -> str | None:
    values = _meaningful_text_values(value)
    return CSV_LIST_SEPARATOR.join(values) if values else None


def _stringify_nested_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    _columns, schema = get_schema_and_column_names(df)
    list_columns = [
        column
        for column, dtype in schema.items()
        if getattr(dtype, "base_type", lambda: None)() == pl.List
    ]
    if not list_columns:
        return df
    return df.with_columns(
        [
            pl.col(column)
            .map_elements(_join_meaningful_text_values, return_dtype=pl.Utf8)
            .alias(column)
            for column in list_columns
        ]
    )


def _normalize_url_text(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.replace("\\u002F", "/")


def _canonical_parent_product_id(
    retailer: str, parent_product_id: Any, pdp_url: Any
) -> str | None:
    normalized_parent_id = _normalize_text(parent_product_id)
    normalized_url = _normalize_url_text(pdp_url)
    if str(retailer or "").strip().lower() == "saksfifthavenue" and normalized_url:
        match = SAKS_PARENT_FROM_URL_RE.search(normalized_url)
        if match:
            return match.group(1)
    return normalized_parent_id


def _normalize_parent_product_ids(df: pl.DataFrame, *, retailer: str) -> pl.DataFrame:
    if df.is_empty() or "parent_product_id" not in df.columns:
        return df
    if "pdp_url" not in df.columns:
        return df.with_columns(
            pl.col("parent_product_id")
            .cast(pl.Utf8, strict=False)
            .alias("parent_product_id")
        )
    return df.with_columns(
        pl.struct(["parent_product_id", "pdp_url"])
        .map_elements(
            lambda row: _canonical_parent_product_id(
                retailer,
                row.get("parent_product_id"),
                row.get("pdp_url"),
            ),
            return_dtype=pl.Utf8,
        )
        .alias("parent_product_id")
    )


def _parse_json_text(value: Any) -> dict[str, Any]:
    text = _normalize_text(value)
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=1)
def _observed_category_center_config() -> dict[str, float | int]:
    default_config: dict[str, float | int] = {
        "rank_weight_alpha": 1.0,
        "min_ranked_products": 3,
        "min_assortment_products": 5,
        "min_rank_weighted_presence": 0.12,
        "min_assortment_presence": 0.12,
        "max_rank_weighted_lift": 1.35,
    }
    try:
        payload = json.loads(DEFAULT_SIGNAL_QUALITY_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config
    if not isinstance(payload, Mapping):
        return default_config
    raw_config = payload.get("observed_category_center")
    if not isinstance(raw_config, Mapping):
        return default_config
    rank_weight_alpha = _numeric_float(raw_config.get("rank_weight_alpha"))
    min_ranked_products = _numeric_int(raw_config.get("min_ranked_products"))
    min_assortment_products = _numeric_int(raw_config.get("min_assortment_products"))
    min_rank_weighted_presence = _numeric_float(
        raw_config.get("min_rank_weighted_presence")
    )
    min_assortment_presence = _numeric_float(raw_config.get("min_assortment_presence"))
    max_rank_weighted_lift = _numeric_float(raw_config.get("max_rank_weighted_lift"))
    return {
        "rank_weight_alpha": (
            rank_weight_alpha if rank_weight_alpha is not None else 1.0
        ),
        "min_ranked_products": (
            min_ranked_products if min_ranked_products is not None else 3
        ),
        "min_assortment_products": (
            min_assortment_products if min_assortment_products is not None else 5
        ),
        "min_rank_weighted_presence": (
            min_rank_weighted_presence
            if min_rank_weighted_presence is not None
            else 0.12
        ),
        "min_assortment_presence": (
            min_assortment_presence if min_assortment_presence is not None else 0.12
        ),
        "max_rank_weighted_lift": (
            max_rank_weighted_lift if max_rank_weighted_lift is not None else 1.35
        ),
    }


def _to_category_label(category_key: str) -> str:
    return category_key.replace("_", " ")


def _package_slug(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one path-safe character.")
    return normalized


def _canonical_package_retailer_key(retailer: str) -> str:
    return _package_slug(retailer, field_name="retailer")


_CANONICAL_PACKAGE_CATEGORY_KEYS = {
    "cashmere_sweaters": "cashmere_sweaters",
    "lip_balms": "lip_balm",
    "lip_gloss": "lip_gloss",
    "lip_liner": "lip_liner",
    "lip_oil": "lip_oil",
    "lip_plumpers": "lip_plumping",
    "lip_stain": "lip_stain",
    "lip_treatments": "lip_treatment",
    "lipstick": "lipstick",
    "low_top_sneakers": "low_top_sneakers",
    "permanent": "permanent",
    "setting_spray_powder": "setting_spray_powder",
    "wet_cat_food": "wet_cat_food",
}

_CANONICAL_PACKAGE_CATEGORY_LABELS = {
    "cashmere_sweaters": "cashmere sweaters",
    "lip_balm": "lip balm",
    "lip_gloss": "lip gloss",
    "lip_liner": "lip liner",
    "lip_oil": "lip oil",
    "lip_plumping": "lip plumping",
    "lip_stain": "lip stain",
    "lip_treatment": "lip treatment",
    "lipstick": "lipstick",
    "low_top_sneakers": "low-top sneakers",
    "permanent": "permanent haircolor",
    "setting_spray_powder": "setting spray & powder",
    "wet_cat_food": "wet cat food",
}


def _canonical_package_category_key(category_key: str) -> str:
    normalized = _package_slug(category_key, field_name="category")
    return _CANONICAL_PACKAGE_CATEGORY_KEYS.get(normalized, normalized)


def _package_output_dir(output_root: Path, *, retailer: str, category_key: str) -> Path:
    return (
        output_root
        / _canonical_package_category_key(category_key)
        / _canonical_package_retailer_key(retailer)
    )


def _package_zip_path(output_dir: Path) -> Path:
    category = _package_slug(output_dir.parent.name, field_name="category")
    retailer = _package_slug(output_dir.name, field_name="retailer")
    return output_dir.parent / f"{category}_{retailer}.zip"


def _prepare_package_output_dir(
    output_root: Path, *, retailer: str, category_key: str
) -> Path:
    output_dir = _clear_existing_package_output_dir(
        output_root,
        retailer=retailer,
        category_key=category_key,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _clear_existing_package_output_dir(
    output_root: Path, *, retailer: str, category_key: str
) -> Path:
    output_dir = _package_output_dir(
        output_root,
        retailer=retailer,
        category_key=category_key,
    )
    zip_path = _package_zip_path(output_dir)
    if zip_path.exists():
        zip_path.unlink()
    legacy_zip_path = output_dir.with_suffix(".zip")
    if legacy_zip_path != zip_path and legacy_zip_path.exists():
        legacy_zip_path.unlink()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    return output_dir


def _canonical_package_category_label(category_key: str) -> str:
    canonical_key = _canonical_package_category_key(category_key)
    return _CANONICAL_PACKAGE_CATEGORY_LABELS.get(
        canonical_key,
        _to_category_label(canonical_key),
    )


def _to_retailer_label(retailer: str) -> str:
    labels = {
        "ulta": "Ulta",
        "saksfifthavenue": "Saks Fifth Avenue",
        "saloncentric": "SalonCentric",
    }
    normalized = retailer.strip().lower()
    return labels.get(normalized, normalized.replace("_", " ").title())


def _meaningful_text(value: Any) -> str | None:
    values = _meaningful_text_values(value)
    return values[0] if values else None


def _filter_primary_attribute_targets(
    *,
    retailer: str,
    category_key: str,
    mapped_attribute_columns: list[str],
    row: Mapping[str, Any],
) -> dict[str, str]:
    mapping = {column: column for column in mapped_attribute_columns if column in row}
    mapping.update(
        FILTER_PRIMARY_ATTRIBUTE_OVERRIDES.get((retailer.lower(), category_key), {})
    )
    return mapping


def _taxonomy_lookup_key(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    return re.sub(r"\s+", " ", key) or None


def _taxonomy_attribute_keys(attribute_name: Any) -> set[str]:
    key = _taxonomy_lookup_key(attribute_name)
    keys = {key} if key else set()
    text = _normalize_text(attribute_name)
    if text and "_" in text:
        underscore_key = _taxonomy_lookup_key(text.replace("_", " "))
        if underscore_key:
            keys.add(underscore_key)
    if key == "color":
        keys.add("color family")
    return keys


def _taxonomy_node_value_keys(value: Any) -> set[str]:
    key = _taxonomy_lookup_key(value)
    keys = {key} if key else set()
    text = _normalize_text(value)
    if text and "_" in text:
        underscore_key = _taxonomy_lookup_key(text.replace("_", " "))
        if underscore_key:
            keys.add(underscore_key)
    return keys


def _iter_taxonomy_nodes(nodes: Any) -> list[Mapping[str, Any]]:
    if not isinstance(nodes, list):
        return []
    out: list[Mapping[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        out.append(node)
        out.extend(_iter_taxonomy_nodes(node.get("children")))
    return out


@lru_cache(maxsize=128)
def _category_taxonomy_value_lookup(
    category_key: str,
) -> dict[str, dict[str, str]]:
    taxonomy_path = TAXONOMY_CATEGORIES_DIR / f"{category_key}.json"
    if not taxonomy_path.exists():
        return {}
    try:
        taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    lookup: dict[str, dict[str, str]] = {}
    for attribute in taxonomy.get("attributes", []):
        if not isinstance(attribute, Mapping):
            continue
        attr_keys = _taxonomy_attribute_keys(attribute.get("id"))
        attr_keys.update(_taxonomy_attribute_keys(attribute.get("label")))
        if not attr_keys:
            continue

        value_lookup: dict[str, str] = {}
        for node in _iter_taxonomy_nodes(attribute.get("nodes")):
            canonical = _meaningful_text(node.get("label"))
            if canonical is None:
                continue
            candidates: list[Any] = [node.get("id"), node.get("label")]
            synonyms = node.get("synonyms")
            if isinstance(synonyms, list):
                candidates.extend(synonyms)
            for candidate in candidates:
                for key in _taxonomy_node_value_keys(candidate):
                    value_lookup[key] = canonical
        if not value_lookup:
            continue

        for attr_key in attr_keys:
            lookup[attr_key] = value_lookup
    return lookup


def _canonical_taxonomy_attribute_value(
    *,
    category_key: str,
    attribute_name: str,
    value: Any,
) -> str | None:
    lookup = _category_taxonomy_value_lookup(category_key)
    if not lookup:
        return None
    value_keys = _taxonomy_node_value_keys(value)
    if not value_keys:
        return None
    for attr_key in _taxonomy_attribute_keys(attribute_name):
        value_lookup = lookup.get(attr_key)
        if not value_lookup:
            continue
        for value_key in value_keys:
            canonical = value_lookup.get(value_key)
            if canonical:
                return canonical
    return None


def _canonical_filter_primary_value(
    value: Any,
    *,
    retailer: str,
    category_key: str,
    target_column: str,
) -> str:
    text = _normalize_text(value)
    if text is None:
        return ""

    canonical_values: list[str] = []
    seen: set[str] = set()
    for raw_part in text.split(CSV_LIST_SEPARATOR):
        part = _meaningful_text(raw_part)
        if not part:
            continue
        canonical = (
            _canonical_taxonomy_attribute_value(
                category_key=category_key,
                attribute_name=target_column,
                value=part,
            )
            or part
        )
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        canonical_values.append(canonical)
    return CSV_LIST_SEPARATOR.join(canonical_values) if canonical_values else text


def _mapped_effective_source(
    row: Mapping[str, Any], *, fallback_column: str, target_column: str
) -> str:
    """Return recorded PDP-value provenance, with a safe legacy fallback."""

    source_base = (
        fallback_column[: -len("_mapped")]
        if fallback_column.endswith("_mapped")
        else fallback_column
    )
    return next(
        (
            source
            for source in (
                _normalize_text(row.get(f"{source_base}_effective_source")),
                _normalize_text(row.get(f"{source_base}_effective_source_mapped")),
                _normalize_text(row.get(f"{target_column}_effective_source")),
                _normalize_text(row.get(f"{target_column}_effective_source_mapped")),
            )
            if source is not None
        ),
        "pdp_attribute_values",
    )


def _merge_filter_primary_attributes(
    row: Mapping[str, Any],
    *,
    retailer: str,
    category_key: str,
    mapped_attribute_columns: list[str],
) -> dict[str, Any]:
    merged = dict(row)
    mapping = _filter_primary_attribute_targets(
        retailer=retailer,
        category_key=category_key,
        mapped_attribute_columns=mapped_attribute_columns,
        row=row,
    )
    filter_overrides = FILTER_PRIMARY_ATTRIBUTE_OVERRIDES.get(
        (retailer.lower(), category_key), {}
    )
    for filter_family, target_column in mapping.items():
        if filter_family not in row and target_column not in row:
            continue

        fallback_column = (
            f"{target_column}_mapped"
            if filter_family == target_column and f"{target_column}_mapped" in row
            else target_column
        )
        filter_raw = row.get(filter_family)
        fallback_raw = row.get(fallback_column)
        is_retailer_filter_input = (
            filter_overrides.get(filter_family) == target_column
            or fallback_column != target_column
        )
        filter_value = (
            _meaningful_text(filter_raw) if is_retailer_filter_input else None
        )
        fallback_value = _meaningful_text(fallback_raw)
        chosen = filter_value or fallback_value
        if chosen is not None:
            merged[target_column] = _canonical_filter_primary_value(
                chosen,
                retailer=retailer,
                category_key=category_key,
                target_column=target_column,
            )
            if filter_value is not None:
                effective_source = "retailer_filter"
            else:
                effective_source = _mapped_effective_source(
                    row,
                    fallback_column=fallback_column,
                    target_column=target_column,
                )
            merged[f"{target_column}_effective_source"] = effective_source
            continue

        if fallback_raw is not None:
            merged[target_column] = fallback_raw
            if is_retailer_filter_input and fallback_column == filter_family:
                merged[f"{target_column}_effective_source"] = "retailer_filter"
            else:
                merged[f"{target_column}_effective_source"] = _mapped_effective_source(
                    row,
                    fallback_column=fallback_column,
                    target_column=target_column,
                )
        elif filter_raw is not None:
            merged[target_column] = filter_raw
            merged[f"{target_column}_effective_source"] = (
                "retailer_filter"
                if is_retailer_filter_input
                else "pdp_attribute_values"
            )
    return merged


def _merge_metadata_fallbacks(row: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    for column in (
        "product_name",
        "brand",
        "pdp_url",
        "category_label",
        "category_path",
    ):
        fallback_column = f"{column}_mapped"
        if fallback_column not in row:
            continue
        chosen = _meaningful_text(row.get(column)) or _meaningful_text(
            row.get(fallback_column)
        )
        if chosen is not None:
            merged[column] = chosen
    return merged


def _mapped_attribute_columns(df: pl.DataFrame) -> list[str]:
    return [
        column
        for column in df.columns
        if column not in MAPPED_EXPORT_METADATA_COLUMNS
        and not column.startswith("also_")
        and not column.endswith("_effective_source")
    ]


@dataclass(frozen=True, slots=True)
class _MappedAttributeFrames:
    """Shared mapped PDP attribute frames for a retailer/category build batch."""

    parent_df: pl.DataFrame
    variant_df: pl.DataFrame


def _is_analysis_attribute_column(column: str) -> bool:
    normalized = column.strip().casefold().replace("_", " ")
    if column in ANALYSIS_EXCLUDED_ATTRIBUTE_COLUMNS:
        return False
    if column.startswith(("brand_claims_", "inferred_", "also_", "our_")):
        return False
    if column.startswith(("filter_", "rollup_", "mapped_")):
        return False
    if column.endswith(("_source", "_source_column", "_path", "_url")):
        return False
    if normalized.endswith((" source", " source column", " path", " url")):
        return False
    if "authority source" in normalized:
        return False
    if normalized in {
        "summary",
        "description excerpt",
        "title raw",
        "badges",
        "rating",
        "review count",
        "review snippet count",
        "available color source",
        "available color family count",
        "variant count",
        "priced variant count",
    }:
        return False
    if normalized.startswith(("review ", "reviews ")):
        return False
    if normalized.endswith((" at", " count")):
        return False
    return True


def _category_filter_keys(retailer: str, category_key: str) -> tuple[str, ...]:
    return (
        tuple(bridged_ulta_category_keys(category_key))
        if retailer.lower() == "ulta"
        else (category_key,)
    )


def _prepare_mapped_attribute_frame(
    export_df: pl.DataFrame,
    *,
    retailer: str,
    category_key: str,
) -> tuple[pl.DataFrame, list[str]]:
    if export_df.is_empty():
        return pl.DataFrame(), []
    category_filter_keys = _category_filter_keys(retailer, category_key)
    category_df = (
        export_df.filter(
            (pl.col("retailer").str.to_lowercase() == retailer.lower())
            & pl.col("category_key").is_in(category_filter_keys)
        )
        .group_by("parent_product_id", maintain_order=True)
        .agg(
            [
                pl.col(column).first().alias(column)
                for column in export_df.columns
                if column != "parent_product_id"
            ]
        )
    )
    if "category_key" in category_df.columns:
        category_df = category_df.with_columns(
            pl.col("category_key")
            .cast(pl.Utf8, strict=False)
            .map_elements(canonicalize_ulta_category_key, return_dtype=pl.Utf8)
            .alias("category_key")
        )
    category_df = _stringify_nested_columns(category_df)
    mapped_columns = [
        column
        for column in _mapped_attribute_columns(category_df)
        if category_df.select(
            pl.col(column)
            .cast(pl.Utf8)
            .fill_null("")
            .str.strip_chars()
            .str.len_chars()
            .sum()
        ).item()
        > 0
    ]
    return category_df, mapped_columns


def _prepare_mapped_attributes_from_store(
    *,
    pdp_store_path: Path,
    retailer: str,
    category_key: str,
    attribute_frames: _MappedAttributeFrames | None = None,
) -> tuple[pl.DataFrame, list[str], pl.DataFrame]:
    if attribute_frames is None:
        attribute_frames = _load_mapped_attribute_frames(
            pdp_store_path=pdp_store_path,
            retailer=retailer,
            category_keys=[category_key],
        )
    mapped_export_df, mapped_attribute_columns = _prepare_mapped_attribute_frame(
        attribute_frames.parent_df,
        retailer=retailer,
        category_key=category_key,
    )
    return mapped_export_df, mapped_attribute_columns, attribute_frames.variant_df


def _load_mapped_attribute_frames(
    *,
    pdp_store_path: Path,
    retailer: str,
    category_keys: Sequence[str],
) -> _MappedAttributeFrames:
    """Load persisted mapped PDP attributes once for a retailer/category batch."""

    from modules.add_attributes.pdp_attribute_export import (
        load_persisted_pdp_attributes,
    )

    normalized_categories = [
        category_key for category_key in dict.fromkeys(category_keys) if category_key
    ]
    parent_df, variant_df, *_ = load_persisted_pdp_attributes(
        pdp_store_path,
        retailers=[retailer],
        categories=normalized_categories,
    )
    return _MappedAttributeFrames(parent_df=parent_df, variant_df=variant_df)


def _empty_available_color_rollups() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "parent_product_id": pl.Utf8,
            "available_color_families": pl.Utf8,
            "available_color_family_count": pl.Int64,
            "available_color_source": pl.Utf8,
        }
    )


def _prepare_variant_color_rollups_from_frame(
    export_df: pl.DataFrame,
    *,
    retailer: str,
    category_key: str,
    parent_ids: set[str],
    category_filter_keys: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    if not parent_ids or export_df.is_empty():
        return _empty_available_color_rollups()

    required_columns = {
        "retailer",
        "parent_product_id",
        "category_key",
        "color family",
    }
    if not required_columns.issubset(set(export_df.columns)):
        return _empty_available_color_rollups()

    filter_keys = category_filter_keys or _category_filter_keys(retailer, category_key)
    category_df = (
        _normalize_parent_product_ids(export_df, retailer=retailer)
        .filter(
            (pl.col("retailer").str.to_lowercase() == retailer.lower())
            & pl.col("category_key").is_in(filter_keys)
            & pl.col("parent_product_id").is_in(parent_ids)
        )
        .with_columns(
            pl.col("color family")
            .cast(pl.Utf8, strict=False)
            .map_elements(_meaningful_text, return_dtype=pl.Utf8)
            .alias("available_color_family")
        )
        .filter(pl.col("available_color_family").is_not_null())
    )
    if category_df.is_empty():
        return _empty_available_color_rollups()

    return (
        category_df.group_by("parent_product_id")
        .agg(
            [
                pl.col("available_color_family")
                .sort()
                .unique()
                .str.join(CSV_LIST_SEPARATOR)
                .alias("available_color_families"),
                pl.col("available_color_family")
                .n_unique()
                .alias("available_color_family_count"),
            ]
        )
        .with_columns(pl.lit("variant_export").alias("available_color_source"))
    )


def _separated_value_count(value: Any) -> int | None:
    values = _split_bundle_values(value)
    return len(values) if values else None


def _apply_available_color_fallbacks(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df

    if "available_color_families" not in df.columns:
        df = df.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("available_color_families")
        )
    if "available_color_family_count" not in df.columns:
        df = df.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("available_color_family_count")
        )
    if "available_color_source" not in df.columns:
        df = df.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("available_color_source")
        )

    filter_color_expr = (
        pl.col("color")
        .cast(pl.Utf8, strict=False)
        .map_elements(_meaningful_text, return_dtype=pl.Utf8)
        if "color" in df.columns
        else pl.lit(None, dtype=pl.Utf8)
    )
    current_color_expr = (
        pl.col("available_color_families")
        .cast(pl.Utf8, strict=False)
        .map_elements(_meaningful_text, return_dtype=pl.Utf8)
    )
    return (
        df.with_columns(
            current_color_expr.alias("_available_color_families"),
            filter_color_expr.alias("_filter_color_families"),
        )
        .with_columns(
            pl.coalesce(
                [pl.col("_available_color_families"), pl.col("_filter_color_families")]
            ).alias("available_color_families"),
            pl.when(pl.col("_available_color_families").is_not_null())
            .then(pl.col("available_color_source"))
            .when(pl.col("_filter_color_families").is_not_null())
            .then(pl.lit("retailer_filter"))
            .otherwise(None)
            .alias("available_color_source"),
        )
        .with_columns(
            pl.col("available_color_families")
            .map_elements(_separated_value_count, return_dtype=pl.Int64)
            .alias("available_color_family_count")
        )
        .drop(["_available_color_families", "_filter_color_families"])
    )


def _resolve_slot_values(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resolved_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        for slot, config in RESOLUTION_SLOT_CONFIG.items():
            ulta_column = config["ulta_column"]
            filter_candidates = config.get("filter_candidates", [])
            rollup_candidates = config.get("rollup_candidates", [])
            mapped_candidates = config["mapped_candidates"]

            ulta_value = _meaningful_text(enriched.get(ulta_column))
            filter_value = None
            filter_source_column = None
            for candidate in filter_candidates:
                candidate_value = _meaningful_text(enriched.get(candidate))
                if candidate_value:
                    filter_value = candidate_value
                    filter_source_column = candidate
                    break

            rollup_value = None
            rollup_source_column = None
            for candidate in rollup_candidates:
                candidate_value = _meaningful_text(enriched.get(candidate))
                if candidate_value:
                    rollup_value = candidate_value
                    rollup_source_column = candidate
                    break

            mapped_value = None
            mapped_source_column = None
            for candidate in mapped_candidates:
                candidate_value = _meaningful_text(enriched.get(candidate))
                if candidate_value:
                    mapped_value = candidate_value
                    mapped_source_column = candidate
                    break

            resolved_value = ulta_value or filter_value or rollup_value or mapped_value
            if ulta_value:
                resolved_source = "ulta"
            elif filter_value:
                resolved_source = "retailer_filter"
            elif rollup_value:
                resolved_source = "attribute_rollup"
            elif mapped_value:
                resolved_source = "mapped"
            else:
                resolved_source = "missing"

            enriched[f"ulta_{slot}"] = ulta_value
            enriched[f"filter_{slot}"] = filter_value
            enriched[f"filter_{slot}_source_column"] = filter_source_column
            enriched[f"rollup_{slot}"] = rollup_value
            enriched[f"rollup_{slot}_source_column"] = rollup_source_column
            enriched[f"mapped_{slot}"] = mapped_value
            enriched[f"mapped_{slot}_source_column"] = mapped_source_column
            enriched[f"resolved_{slot}"] = resolved_value
            enriched[f"resolved_{slot}_source"] = resolved_source
        resolved_rows.append(enriched)
    return resolved_rows


def _build_value_comparison(
    *,
    df: pl.DataFrame,
    attribute_columns: list[str],
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for column in attribute_columns:
        if column not in df.columns:
            continue
        value_df = (
            df.select(["listing_status", column])
            .rename({column: "attribute_value"})
            .with_columns(pl.lit(column).alias("attribute_name"))
            .with_columns(
                pl.col("attribute_value")
                .cast(pl.Utf8)
                .map_elements(_meaningful_text, return_dtype=pl.Utf8)
                .alias("attribute_value")
            )
            .filter(pl.col("attribute_value").is_not_null())
        )
        if value_df.height == 0:
            continue

        denominators = value_df.group_by(["attribute_name", "listing_status"]).agg(
            pl.len().alias("group_base")
        )
        pivoted = (
            value_df.group_by(["attribute_name", "attribute_value", "listing_status"])
            .agg(pl.len().alias("product_count"))
            .pivot(
                values="product_count",
                index=["attribute_name", "attribute_value"],
                on="listing_status",
                aggregate_function="first",
            )
        )
        if "recent" not in pivoted.columns:
            pivoted = pivoted.with_columns(pl.lit(0).alias("recent"))
        if "rest" not in pivoted.columns:
            pivoted = pivoted.with_columns(pl.lit(0).alias("rest"))
        comparison = (
            pivoted.with_columns(
                pl.col("recent").fill_null(0).cast(pl.Int64),
                pl.col("rest").fill_null(0).cast(pl.Int64),
            )
            .rename({"recent": "count_recent", "rest": "count_rest"})
            .join(
                denominators.filter(pl.col("listing_status") == "recent").select(
                    ["attribute_name", pl.col("group_base").alias("recent_base")]
                ),
                on="attribute_name",
                how="left",
            )
            .join(
                denominators.filter(pl.col("listing_status") == "rest").select(
                    ["attribute_name", pl.col("group_base").alias("rest_base")]
                ),
                on="attribute_name",
                how="left",
            )
            .with_columns(
                pl.when(pl.col("recent_base") > 0)
                .then(pl.col("count_recent") / pl.col("recent_base"))
                .otherwise(None)
                .alias("pct_recent"),
                pl.when(pl.col("rest_base") > 0)
                .then(pl.col("count_rest") / pl.col("rest_base"))
                .otherwise(None)
                .alias("pct_rest"),
            )
            .with_columns((pl.col("pct_recent") - pl.col("pct_rest")).alias("delta"))
            .sort(
                ["attribute_name", "delta", "count_recent"],
                descending=[False, True, True],
            )
        )
        frames.append(comparison)

    if not frames:
        return pl.DataFrame(
            schema={
                "attribute_name": pl.Utf8,
                "attribute_value": pl.Utf8,
                "count_recent": pl.Int64,
                "count_rest": pl.Int64,
                "recent_base": pl.Int64,
                "rest_base": pl.Int64,
                "pct_recent": pl.Float64,
                "pct_rest": pl.Float64,
                "delta": pl.Float64,
            }
        )
    return pl.concat(frames, how="diagonal_relaxed")


def _comparison_frame_for_status(
    df: pl.DataFrame,
    *,
    status_column: str,
    focus_label: str,
    other_label: str,
) -> pl.DataFrame:
    return df.with_columns(
        pl.when(pl.col(status_column) == focus_label)
        .then(pl.lit("recent"))
        .otherwise(pl.lit("rest"))
        .alias("listing_status")
    )


def _rename_recent_rest_columns(
    df: pl.DataFrame,
    *,
    focus_prefix: str,
    other_prefix: str,
) -> pl.DataFrame:
    rename_map: dict[str, str] = {}
    for source, target in {
        "count_recent": f"count_{focus_prefix}",
        "count_rest": f"count_{other_prefix}",
        "recent_base": f"{focus_prefix}_base",
        "rest_base": f"{other_prefix}_base",
        "pct_recent": f"pct_{focus_prefix}",
        "pct_rest": f"pct_{other_prefix}",
        "recent_brand_count": f"{focus_prefix}_brand_count",
        "rest_brand_count": f"{other_prefix}_brand_count",
        "recent_products_with_pareto": f"{focus_prefix}_products_with_pareto",
        "recent_pareto_a_count": f"{focus_prefix}_pareto_a_count",
        "recent_pareto_b_count": f"{focus_prefix}_pareto_b_count",
        "recent_pareto_c_count": f"{focus_prefix}_pareto_c_count",
        "recent_pareto_ab_count": f"{focus_prefix}_pareto_ab_count",
        "best_recent_pareto_rank": f"best_{focus_prefix}_pareto_rank",
        "recent_sales_share_sum": f"{focus_prefix}_sales_share_sum",
        "recent_sales_share_mean": f"{focus_prefix}_sales_share_mean",
        "recent_brands": f"{focus_prefix}_brands",
        "recent_top_pareto_products": f"{focus_prefix}_top_pareto_products",
        "recent_example_products": f"{focus_prefix}_example_products",
    }.items():
        if source in df.columns:
            rename_map[source] = target
    return df.rename(rename_map) if rename_map else df


def _top_seller_status(value: Any) -> str:
    return "top_seller" if _normalized_pareto_bucket(value) == "A" else "other"


def _build_focus_value_comparison(
    *,
    df: pl.DataFrame,
    attribute_columns: list[str],
    status_column: str,
    focus_label: str,
    other_label: str,
    focus_prefix: str,
    other_prefix: str,
) -> pl.DataFrame:
    comparison = _build_value_comparison(
        df=_comparison_frame_for_status(
            df,
            status_column=status_column,
            focus_label=focus_label,
            other_label=other_label,
        ),
        attribute_columns=attribute_columns,
    )
    return _rename_recent_rest_columns(
        comparison,
        focus_prefix=focus_prefix,
        other_prefix=other_prefix,
    )


def _empty_focus_value_comparison(
    *,
    focus_prefix: str,
    other_prefix: str,
) -> pl.DataFrame:
    return _rename_recent_rest_columns(
        _build_value_comparison(df=pl.DataFrame(), attribute_columns=[]),
        focus_prefix=focus_prefix,
        other_prefix=other_prefix,
    )


def _build_focus_bundle_signals(
    *,
    df: pl.DataFrame,
    attribute_columns: list[str],
    bundle_size: int,
    status_column: str,
    focus_label: str,
    other_label: str,
    focus_prefix: str,
    other_prefix: str,
) -> pl.DataFrame:
    signals = _build_bundle_signals(
        df=_comparison_frame_for_status(
            df,
            status_column=status_column,
            focus_label=focus_label,
            other_label=other_label,
        ),
        attribute_columns=attribute_columns,
        bundle_size=bundle_size,
    )
    return _rename_recent_rest_columns(
        signals,
        focus_prefix=focus_prefix,
        other_prefix=other_prefix,
    )


def _build_brand_top_seller_comparison(df: pl.DataFrame) -> pl.DataFrame:
    if (
        df.is_empty()
        or "brand" not in df.columns
        or "top_seller_status" not in df.columns
    ):
        return pl.DataFrame(
            schema={
                "brand": pl.Utf8,
                "catalog_count": pl.Int64,
                "top_seller_count": pl.Int64,
                "other_count": pl.Int64,
                "catalog_share": pl.Float64,
                "top_seller_share_of_brand": pl.Float64,
                "top_seller_share_of_cohort": pl.Float64,
                "over_index_vs_catalog_share": pl.Float64,
            }
        )
    branded = df.filter(
        pl.col("brand").is_not_null()
        & (pl.col("brand").cast(pl.Utf8).str.strip_chars() != "")
    )
    if branded.is_empty():
        return pl.DataFrame(
            schema={
                "brand": pl.Utf8,
                "catalog_count": pl.Int64,
                "top_seller_count": pl.Int64,
                "other_count": pl.Int64,
                "catalog_share": pl.Float64,
                "top_seller_share_of_brand": pl.Float64,
                "top_seller_share_of_cohort": pl.Float64,
                "over_index_vs_catalog_share": pl.Float64,
            }
        )
    total_catalog = branded.height
    total_top = branded.filter(pl.col("top_seller_status") == "top_seller").height
    out = (
        branded.group_by("brand")
        .agg(
            [
                pl.len().alias("catalog_count"),
                (pl.col("top_seller_status") == "top_seller")
                .cast(pl.Int64)
                .sum()
                .alias("top_seller_count"),
            ]
        )
        .with_columns(
            (pl.col("catalog_count") - pl.col("top_seller_count")).alias("other_count"),
            (pl.col("catalog_count") / total_catalog).alias("catalog_share"),
            pl.when(pl.col("catalog_count") > 0)
            .then(pl.col("top_seller_count") / pl.col("catalog_count"))
            .otherwise(None)
            .alias("top_seller_share_of_brand"),
            pl.when(pl.lit(total_top) > 0)
            .then(pl.col("top_seller_count") / pl.lit(total_top))
            .otherwise(None)
            .alias("top_seller_share_of_cohort"),
        )
        .with_columns(
            pl.when(pl.col("catalog_share") > 0)
            .then(pl.col("top_seller_share_of_cohort") / pl.col("catalog_share"))
            .otherwise(None)
            .alias("over_index_vs_catalog_share")
        )
        .sort(
            [
                "over_index_vs_catalog_share",
                "top_seller_count",
                "catalog_count",
                "brand",
            ],
            descending=[True, True, True, False],
            nulls_last=True,
        )
    )
    return out


def _run_recent_share(run_dir: Path) -> float:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return 0.20
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return 0.20
    try:
        return float(payload.get("recent_share", 0.20))
    except Exception:
        return 0.20


def _parent_detail_rows(
    pdp_store_path: Path, retailer: str, parent_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not parent_ids:
        return {}
    placeholders = ",".join("?" for _ in parent_ids)
    query = f"""
        SELECT parent_product_id, title_raw, brand_raw, pdp_url, extras
        FROM parent_products
        WHERE retailer = ? AND parent_product_id IN ({placeholders})
    """
    rows: dict[str, dict[str, Any]] = {}
    with connect_pdp_database(pdp_store_path) as conn:
        params = (retailer, *parent_ids)
        for parent_id, title_raw, brand_raw, pdp_url, extras in conn.execute(
            query, params
        ).fetchall():
            payload = _parse_json_text(extras)
            details = payload.get("details", {})
            summary = _normalize_text(payload.get("summary"))
            description_markdown = None
            if isinstance(details, dict):
                description_markdown = _normalize_text(
                    details.get("description_markdown")
                )
            review_fields = _flatten_review_fields(payload)
            rows[str(parent_id)] = {
                "title_raw": _normalize_text(title_raw),
                "brand_raw": _normalize_text(brand_raw),
                "pdp_url": _normalize_text(pdp_url),
                "summary": summary,
                "description_markdown": description_markdown,
                "hero_image_url": _normalize_url_text(
                    payload.get("hero_image_url")
                    or (
                        details.get("hero_image_url")
                        if isinstance(details, dict)
                        else None
                    )
                ),
                "rating": payload.get("rating"),
                "review_count": payload.get("review_count"),
                "badges": payload.get("badges"),
                **review_fields,
            }
    return rows


def _parent_price_rows(
    pdp_store_path: Path, retailer: str, parent_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not parent_ids:
        return {}
    placeholders = ",".join("?" for _ in parent_ids)
    query = f"""
        SELECT
            parent_product_id,
            COUNT(*) AS variant_count,
            SUM(CASE WHEN price IS NOT NULL THEN 1 ELSE 0 END) AS priced_variant_count,
            MIN(price) AS entry_price,
            MAX(price) AS max_price,
            MIN(batch_generated_at) AS price_snapshot_min_at,
            MAX(batch_generated_at) AS price_snapshot_max_at
        FROM variants
        WHERE retailer = ? AND parent_product_id IN ({placeholders})
        GROUP BY parent_product_id
    """
    rows: dict[str, dict[str, Any]] = {}
    with connect_pdp_database(pdp_store_path) as conn:
        params = (retailer, *parent_ids)
        for (
            parent_id,
            variant_count,
            priced_variant_count,
            entry_price,
            max_price,
            price_snapshot_min_at,
            price_snapshot_max_at,
        ) in conn.execute(query, params).fetchall():
            rows[str(parent_id)] = {
                "variant_count": int(variant_count or 0),
                "priced_variant_count": int(priced_variant_count or 0),
                "entry_price": float(entry_price) if entry_price is not None else None,
                "max_price": float(max_price) if max_price is not None else None,
                "price_snapshot_min_at": _normalize_text(price_snapshot_min_at),
                "price_snapshot_max_at": _normalize_text(price_snapshot_max_at),
            }
    return rows


def _attribute_value_coverage_rows(
    pdp_store_path: Path,
    *,
    retailer: str,
    category_key: str,
) -> list[dict[str, Any]]:
    if not pdp_database_exists(pdp_store_path):
        return []
    columns = [
        "retailer",
        "row_type",
        "category_key",
        "source",
        "decision_rows",
        "no_value_rows",
        "taxonomy_miss_rows",
        "valued_rows",
    ]
    try:
        with connect_pdp_database(pdp_store_path) as conn:
            rows = conn.execute(
                f"""
                SELECT {', '.join(columns)}
                FROM pdp_attribute_value_coverage
                WHERE retailer = ?
                  AND category_key = ?
                ORDER BY row_type, source
                """,
                (retailer, category_key),
            ).fetchall()
    except Exception:
        return []
    return [{key: value for key, value in zip(columns, row)} for row in rows]


def _image_map_from_directory(images_dir: Path) -> dict[str, str]:
    if not images_dir.exists():
        return {}
    image_map: dict[str, str] = {}
    for image_path in sorted(images_dir.iterdir()):
        if not image_path.is_file():
            continue
        suffix = image_path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
            continue
        stem = image_path.stem
        if stem.endswith("_hero") or stem.endswith("_swatch"):
            stem = stem.rsplit("_", 1)[0]
        parent_id = stem.split("_", 1)[0]
        if parent_id and parent_id not in image_map:
            image_map[parent_id] = str(image_path.resolve())
    return image_map


def _image_rows(
    cli_root: Path,
    retailer: str,
    category_key: str,
    variant_df: pl.DataFrame,
) -> dict[str, dict[str, str | None]]:
    category_candidates = [category_key, _canonical_package_category_key(category_key)]
    seen_candidates: set[str] = set()
    local_image_map: dict[str, str] = {}
    image_dirs: list[Path] = []
    for candidate_key in category_candidates:
        normalized_candidate = _package_slug(candidate_key, field_name="category")
        if normalized_candidate in seen_candidates:
            continue
        seen_candidates.add(normalized_candidate)

        category_dir = cli_root / f"{retailer}_{normalized_candidate}"
        images_dir = category_dir / "images"
        image_dirs.append(images_dir)
        for parent_id, local_path in _image_map_from_directory(images_dir).items():
            local_image_map.setdefault(parent_id, local_path)

    rows: dict[str, dict[str, str | None]] = {}
    variant_columns, _schema = get_schema_and_column_names(variant_df)
    if variant_df.width > 0 and "parent_product_id" in variant_columns:
        variants = variant_df
        if "retailer" in variant_columns:
            retailer_key = _canonical_package_retailer_key(retailer)
            variants = variants.filter(
                pl.col("retailer")
                .cast(pl.Utf8, strict=False)
                .map_elements(
                    lambda value: _canonical_package_retailer_key(value)
                    == retailer_key,
                    return_dtype=pl.Boolean,
                )
                .fill_null(False)
            )
        if "category_key" in variant_columns:
            category_key_set = set(category_candidates)
            variants = variants.filter(
                pl.col("category_key")
                .cast(pl.Utf8, strict=False)
                .is_in(category_key_set)
            )
        if variants.is_empty():
            grouped = []
        else:
            selected_variant_columns, _selected_schema = get_schema_and_column_names(
                variants
            )
            for column in ("variant_id", "hero_image_url", "swatch_image_url"):
                if column not in selected_variant_columns:
                    variants = variants.with_columns(
                        pl.lit(None, dtype=pl.Utf8).alias(column)
                    )
            variants = variants.select(
                [
                    "parent_product_id",
                    "variant_id",
                    "hero_image_url",
                    "swatch_image_url",
                ]
            )
            grouped = (
                variants.group_by("parent_product_id")
                .agg(
                    [
                        pl.col("variant_id").first().alias("variant_id"),
                        pl.col("hero_image_url")
                        .drop_nulls()
                        .first()
                        .alias("hero_image_url"),
                        pl.col("swatch_image_url")
                        .drop_nulls()
                        .first()
                        .alias("swatch_image_url"),
                    ]
                )
                .to_dicts()
            )

        for row in grouped:
            parent_id = _normalize_text(row.get("parent_product_id"))
            if not parent_id:
                continue
            variant_id = _normalize_text(row.get("variant_id"))
            image_path = local_image_map.get(parent_id)
            if not image_path and variant_id:
                for images_dir in image_dirs:
                    for suffix in (".png", ".jpg", ".jpeg", ".webp", ".avif"):
                        candidate = (
                            images_dir / f"{parent_id}_{variant_id}_hero{suffix}"
                        )
                        if candidate.exists():
                            image_path = str(candidate.resolve())
                            break
                    if image_path:
                        break
            rows[parent_id] = {
                "hero_image_url": _normalize_url_text(row.get("hero_image_url")),
                "swatch_image_url": _normalize_url_text(row.get("swatch_image_url")),
                "local_image_path": image_path,
            }
    for parent_id, local_path in local_image_map.items():
        rows.setdefault(
            parent_id,
            {
                "hero_image_url": None,
                "swatch_image_url": None,
                "local_image_path": local_path,
            },
        )
    return rows


def _require_pack_images(
    *,
    retailer: str,
    category_key: str,
    recent_products: int,
    recent_products_with_pack_image: int,
) -> None:
    if recent_products <= 0:
        return
    if recent_products_with_pack_image > 0:
        return
    raise RuntimeError(
        "Package build produced zero pack images for "
        f"retailer={retailer} category={category_key} despite {recent_products} recent products. "
        "This indicates a broken image input or packaging path."
    )


def _bounded_pack_image_limit(max_pack_images: int | None) -> int:
    if max_pack_images is None:
        return PACK_IMAGE_HARD_LIMIT
    if max_pack_images < 0:
        raise ValueError("max_pack_images cannot be negative.")
    return min(max_pack_images, PACK_IMAGE_HARD_LIMIT)


def _resolve_category_label(
    *, category_key: str, mapped_export_df: pl.DataFrame
) -> str:
    if mapped_export_df.height > 0 and "category_label" in mapped_export_df.columns:
        category_label = _meaningful_text(mapped_export_df.item(0, "category_label"))
        if category_label:
            return category_label
    return _to_category_label(category_key)


def _retailer_sort_preferences(retailer: str) -> tuple[str | None, str | None]:
    retailer_lower = str(retailer or "").strip().lower()
    if not retailer_lower:
        return (None, None)
    if retailer_lower == "ulta":
        return ("new_arrivals", "best_sellers")
    try:
        strategy = strategy_for_retailer(retailer_lower)
    except ValueError:
        return (None, None)
    return (strategy.recent_sort_mode, strategy.popularity_sort_mode)


def _select_recent_sort_mode(
    category_listing_raw: pl.DataFrame,
    *,
    retailer: str,
) -> str | None:
    if (
        category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return None
    normalized_modes = _available_ranked_sort_modes(category_listing_raw)
    preferred_recent, _ = _retailer_sort_preferences(retailer)
    if preferred_recent and preferred_recent in normalized_modes:
        return preferred_recent
    for preferred in RECENT_SORT_MODE_FALLBACKS:
        if preferred in normalized_modes:
            return preferred
    return None


def _canonical_sort_mode(retailer: str, sort_mode: str | None) -> str | None:
    normalized_mode = _normalize_text(sort_mode)
    if not normalized_mode:
        return None
    normalized_retailer = str(retailer or "").strip().lower()
    if normalized_retailer == "cosmoprofbeauty":
        if normalized_mode == "most_popular":
            return "top_sellers"
        if normalized_mode == "newest":
            return "new_arrivals"
    return normalized_mode


def _display_sort_mode_label(retailer: str, sort_mode: str | None) -> str:
    normalized_mode = _canonical_sort_mode(retailer, sort_mode)
    if not normalized_mode:
        return "unavailable ranked sort"
    return normalized_mode


def _available_ranked_sort_modes(category_listing_raw: pl.DataFrame) -> set[str]:
    if (
        category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return set()
    return {
        mode
        for value in category_listing_raw.get_column("sort_mode").drop_nulls().to_list()
        if (mode := str(value or "").strip().lower())
        and mode not in EXCLUDED_RANKED_SORT_MODES
    }


def _observed_sort_modes(category_listing_raw: pl.DataFrame) -> set[str]:
    if (
        category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return set()
    return {
        mode
        for value in category_listing_raw.get_column("sort_mode").drop_nulls().to_list()
        if (mode := str(value or "").strip().lower())
    }


def _select_sale_pressure_sort_mode(category_listing_raw: pl.DataFrame) -> str | None:
    observed_modes = _observed_sort_modes(category_listing_raw)
    for preferred in SALE_PRESSURE_SORT_MODE_FALLBACKS:
        if preferred in observed_modes:
            return preferred
    return None


def _ranked_sequence_for_sort(
    category_listing_raw: pl.DataFrame,
    *,
    sort_mode: str | None,
) -> list[str]:
    normalized_mode = str(sort_mode or "").strip().lower()
    if (
        not normalized_mode
        or category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return []
    ranked_source = _with_listing_identity(category_listing_raw).filter(
        pl.col("sort_mode").cast(pl.Utf8, strict=False).fill_null("").str.to_lowercase()
        == normalized_mode
    )
    if ranked_source.height == 0 or "listing_identity" not in ranked_source.columns:
        return []
    ranked = (
        ranked_source.with_columns(
            [
                pl.col("page")
                .cast(pl.Int64, strict=False)
                .fill_null(1)
                .alias("_rank_page"),
                pl.col("position")
                .cast(pl.Int64, strict=False)
                .fill_null(1)
                .alias("_rank_position"),
                pl.col("pdp_url")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("_rank_url"),
            ]
        )
        .sort(["_rank_page", "_rank_position", "_rank_url"])
        .group_by("listing_identity", maintain_order=True)
        .agg(pl.col("_rank_page").first())
    )
    return [
        identity
        for value in ranked.get_column("listing_identity").drop_nulls().to_list()
        if (identity := str(value or "").strip())
    ]


def _ranked_sort_overlap_quality(
    *,
    retailer: str,
    category_key: str,
    recent_sort_mode: str,
    top_seller_sort_mode: str,
    recent_sequence: list[str],
    top_seller_sequence: list[str],
    min_products: int,
    top_window_size: int = SORT_TOP_WINDOW_SIZE,
    high_overlap_threshold: float = HIGH_TOP_WINDOW_OVERLAP_THRESHOLD,
) -> dict[str, Any]:
    window_size = min(top_window_size, len(recent_sequence), len(top_seller_sequence))
    payload: dict[str, Any] = {
        "status": "passed",
        "analysis_mode": "cohort_contrast",
        "retailer": retailer,
        "category_key": category_key,
        "recent_sort_mode": recent_sort_mode,
        "top_seller_sort_mode": top_seller_sort_mode,
        "recent_product_count": len(recent_sequence),
        "top_seller_product_count": len(top_seller_sequence),
        "top_window_size": int(window_size),
        "high_top_window_overlap_threshold": float(high_overlap_threshold),
    }
    if (
        len(recent_sequence) < min_products
        or len(top_seller_sequence) < min_products
        or window_size < min_products
    ):
        payload["status"] = "insufficient_data"
        payload["analysis_mode"] = "insufficient_rank_evidence"
        return payload

    recent_window = recent_sequence[:window_size]
    top_seller_window = top_seller_sequence[:window_size]
    overlap_ids = sorted(set(recent_window) & set(top_seller_window))
    overlap_ratio = len(overlap_ids) / window_size
    payload.update(
        {
            "top_window_overlap_count": len(overlap_ids),
            "top_window_overlap_ratio": overlap_ratio,
            "sample_overlap_product_ids": overlap_ids[:10],
            "recent_sample_product_ids": recent_window[:10],
            "top_seller_sample_product_ids": top_seller_window[:10],
        }
    )
    if overlap_ratio >= high_overlap_threshold:
        payload["status"] = "warning"
        payload["analysis_mode"] = "rank_order_contrast"
        payload["warning"] = (
            "newest and top-seller ranked surfaces have unusually high "
            "top-window overlap"
        )
        payload["interpretation"] = (
            "Treat the overlap as a market signal after manual confirmation: "
            "innovation and sales may be tightly linked, so compare rank "
            "movement inside overlapping products instead of reading newest "
            "and top-seller cohorts as independent groups."
        )
    return payload


def _validate_distinct_ranked_sort_sequences(
    category_listing_raw: pl.DataFrame,
    *,
    retailer: str,
    category_key: str,
    recent_sort_mode: str | None,
    top_seller_sort_mode: str | None,
    min_products: int = MIN_SORT_SEQUENCE_PRODUCTS,
) -> dict[str, Any]:
    if not recent_sort_mode or not top_seller_sort_mode:
        available_modes = sorted(_available_ranked_sort_modes(category_listing_raw))
        raise PackageBuildSkipped(
            "Cannot build retailer category package without both newest and "
            "top-seller ranked sort surfaces. "
            f"retailer={retailer} category={category_key} "
            f"newest_sort={recent_sort_mode!r} "
            f"top_seller_sort={top_seller_sort_mode!r} "
            f"available_ranked_sorts={available_modes}"
        )
    if recent_sort_mode == top_seller_sort_mode:
        raise PackageBuildSkipped(
            "Cannot build retailer category package because newest and top-seller "
            f"resolve to the same sort mode. retailer={retailer} "
            f"category={category_key} sort_mode={recent_sort_mode}"
        )
    recent_sequence = _ranked_sequence_for_sort(
        category_listing_raw,
        sort_mode=recent_sort_mode,
    )
    top_seller_sequence = _ranked_sequence_for_sort(
        category_listing_raw,
        sort_mode=top_seller_sort_mode,
    )
    if (
        len(recent_sequence) >= min_products
        and len(top_seller_sequence) >= min_products
        and recent_sequence == top_seller_sequence
    ):
        sample = recent_sequence[:10]
        raise PackageBuildSkipped(
            "Cannot build retailer category package because newest and top-seller "
            "ranked sort surfaces have identical product order. "
            f"retailer={retailer} category={category_key} "
            f"newest_sort={recent_sort_mode} top_seller_sort={top_seller_sort_mode} "
            f"product_count={len(recent_sequence)} sample_product_ids={sample}"
        )
    sort_overlap_quality = _ranked_sort_overlap_quality(
        retailer=retailer,
        category_key=category_key,
        recent_sort_mode=recent_sort_mode,
        top_seller_sort_mode=top_seller_sort_mode,
        recent_sequence=recent_sequence,
        top_seller_sequence=top_seller_sequence,
        min_products=min_products,
    )
    return sort_overlap_quality


def _rank_frame_for_sort(
    category_listing_raw: pl.DataFrame,
    *,
    sort_mode: str | None,
    rank_column: str,
) -> pl.DataFrame:
    schema = {"listing_identity": pl.Utf8, rank_column: pl.Int64}
    normalized_mode = str(sort_mode or "").strip().lower()
    if (
        not normalized_mode
        or category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return pl.DataFrame(schema=schema)
    source = _with_listing_identity(category_listing_raw)
    if "listing_identity" not in source.columns:
        return pl.DataFrame(schema=schema)
    ranked_source = source.filter(
        pl.col("sort_mode").cast(pl.Utf8, strict=False).fill_null("").str.to_lowercase()
        == normalized_mode
    )
    if ranked_source.height == 0:
        return pl.DataFrame(schema=schema)
    ranked = (
        ranked_source.with_columns(
            [
                pl.col("page")
                .cast(pl.Int64, strict=False)
                .fill_null(1)
                .alias("_rank_page"),
                pl.col("position")
                .cast(pl.Int64, strict=False)
                .fill_null(1)
                .alias("_rank_position"),
                pl.col("pdp_url")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("_rank_url"),
            ]
        )
        .sort(["_rank_page", "_rank_position", "_rank_url"])
        .group_by("listing_identity", maintain_order=True)
        .agg(pl.col("_rank_page").first())
        .with_row_index(rank_column, offset=1)
    )
    return ranked.select(["listing_identity", rank_column])


def _apply_sale_pressure_layer(
    df: pl.DataFrame,
    *,
    category_listing_raw: pl.DataFrame,
    sale_pressure_sort_mode: str | None,
) -> pl.DataFrame:
    if df.is_empty():
        return df.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("sale_pressure_rank"),
            pl.lit("not_observed_sale_pressure").alias("sale_pressure_status"),
        )
    sale_pressure_ranks = _rank_frame_for_sort(
        category_listing_raw,
        sort_mode=sale_pressure_sort_mode,
        rank_column="sale_pressure_rank",
    )
    if sale_pressure_ranks.height > 0:
        df = df.join(sale_pressure_ranks, on="listing_identity", how="left")
    else:
        df = df.with_columns(pl.lit(None, dtype=pl.Int64).alias("sale_pressure_rank"))
    return df.with_columns(
        pl.when(pl.col("sale_pressure_rank").is_not_null())
        .then(pl.lit("sale_pressure"))
        .otherwise(pl.lit("not_observed_sale_pressure"))
        .alias("sale_pressure_status")
    )


def _build_sale_pressure_overlap_summary(df: pl.DataFrame) -> pl.DataFrame:
    schema = {
        "comparison": pl.Utf8,
        "left_cohort": pl.Utf8,
        "right_cohort": pl.Utf8,
        "left_count": pl.Int64,
        "right_count": pl.Int64,
        "overlap_count": pl.Int64,
        "pct_left": pl.Float64,
        "pct_right": pl.Float64,
    }
    if df.is_empty() or "listing_identity" not in df.columns:
        return pl.DataFrame(schema=schema)

    def _ids_for(column: str, value: str) -> set[str]:
        if column not in df.columns:
            return set()
        return {
            identity
            for raw_identity in df.filter(pl.col(column) == value)
            .get_column("listing_identity")
            .drop_nulls()
            .to_list()
            if (identity := _normalize_text(raw_identity))
        }

    sale_ids = _ids_for("sale_pressure_status", "sale_pressure")
    recent_ids = _ids_for("listing_status", "recent")
    top_seller_ids = _ids_for("top_seller_status", "top_seller")
    recent_top_seller_ids = recent_ids & top_seller_ids
    rows = []
    for comparison, left_name, left_ids, right_name, right_ids in [
        (
            "sale_pressure_vs_recent",
            "sale_pressure",
            sale_ids,
            "recent",
            recent_ids,
        ),
        (
            "sale_pressure_vs_top_seller",
            "sale_pressure",
            sale_ids,
            "top_seller",
            top_seller_ids,
        ),
        (
            "sale_pressure_vs_recent_top_seller",
            "sale_pressure",
            sale_ids,
            "recent_and_top_seller",
            recent_top_seller_ids,
        ),
        (
            "recent_vs_top_seller",
            "recent",
            recent_ids,
            "top_seller",
            top_seller_ids,
        ),
    ]:
        overlap_count = len(left_ids & right_ids)
        rows.append(
            {
                "comparison": comparison,
                "left_cohort": left_name,
                "right_cohort": right_name,
                "left_count": len(left_ids),
                "right_count": len(right_ids),
                "overlap_count": overlap_count,
                "pct_left": overlap_count / len(left_ids) if left_ids else None,
                "pct_right": overlap_count / len(right_ids) if right_ids else None,
            }
        )
    return pl.DataFrame(rows, schema=schema)


def _empty_sort_rank_delta_products() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "listing_identity": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "brand": pl.Utf8,
            "product_name": pl.Utf8,
            "pdp_url": pl.Utf8,
            "newest_rank": pl.Int64,
            "top_seller_rank": pl.Int64,
            "rank_delta": pl.Int64,
            "rank_delta_status": pl.Utf8,
        }
    )


def _build_sort_rank_delta_products(
    *,
    enriched: pl.DataFrame,
    category_listing_raw: pl.DataFrame,
    recent_sort_mode: str | None,
    top_seller_sort_mode: str | None,
    attribute_columns: list[str],
) -> pl.DataFrame:
    if enriched.is_empty() or not recent_sort_mode or not top_seller_sort_mode:
        return _empty_sort_rank_delta_products()
    recent_ranks = _rank_frame_for_sort(
        category_listing_raw,
        sort_mode=recent_sort_mode,
        rank_column="newest_rank",
    )
    top_seller_ranks = _rank_frame_for_sort(
        category_listing_raw,
        sort_mode=top_seller_sort_mode,
        rank_column="top_seller_rank",
    )
    if recent_ranks.is_empty() or top_seller_ranks.is_empty():
        return _empty_sort_rank_delta_products()

    base_columns = [
        "listing_identity",
        "parent_product_id",
        "brand",
        "product_name",
        "pdp_url",
        "listing_status",
        "top_seller_status",
        "pareto_rank",
        "pareto_bucket",
        "entry_price",
        "rating",
        "review_count",
    ]
    selected_columns = list(
        dict.fromkeys(
            column
            for column in base_columns + attribute_columns
            if column in enriched.columns
        )
    )
    ranked = (
        recent_ranks.join(top_seller_ranks, on="listing_identity", how="inner")
        .with_columns(
            (pl.col("newest_rank") - pl.col("top_seller_rank")).alias("rank_delta")
        )
        .with_columns(
            pl.when(pl.col("rank_delta") > 0)
            .then(pl.lit("sales_rank_lead"))
            .when(pl.col("rank_delta") < 0)
            .then(pl.lit("newness_rank_lead"))
            .otherwise(pl.lit("rank_tie"))
            .alias("rank_delta_status")
        )
    )
    if ranked.is_empty():
        return _empty_sort_rank_delta_products()
    return ranked.join(
        enriched.select(selected_columns).unique("listing_identity"),
        on="listing_identity",
        how="left",
    ).sort(
        ["rank_delta", "top_seller_rank", "newest_rank"],
        descending=[True, False, False],
    )


def _split_attribute_values(value: Any) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []
    values = [
        candidate.strip()
        for candidate in text.split(CSV_LIST_SEPARATOR)
        if candidate.strip()
    ]
    return sorted({value for value in values if _value_is_meaningful(value)})


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[midpoint])
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _product_rank_label(row: dict[str, Any]) -> str:
    label = _normalize_text(row.get("product_name")) or _normalize_text(
        row.get("parent_product_id")
    )
    brand = _normalize_text(row.get("brand"))
    if brand and label and not label.casefold().startswith(brand.casefold()):
        label = f"{brand} {label}"
    delta = _numeric_int(row.get("rank_delta"))
    if delta is None:
        return label or ""
    sign = "+" if delta > 0 else ""
    return f"{label} ({sign}{delta})" if label else f"{sign}{delta}"


def _build_sort_rank_delta_attributes(
    rank_delta_products: pl.DataFrame,
    *,
    attribute_columns: list[str],
) -> pl.DataFrame:
    schema = {
        "attribute_name": pl.Utf8,
        "attribute_value": pl.Utf8,
        "product_count": pl.Int64,
        "sales_rank_lead_count": pl.Int64,
        "newness_rank_lead_count": pl.Int64,
        "rank_tie_count": pl.Int64,
        "mean_rank_delta": pl.Float64,
        "median_rank_delta": pl.Float64,
        "mean_newest_rank": pl.Float64,
        "mean_top_seller_rank": pl.Float64,
        "example_sales_rank_lead_products": pl.Utf8,
        "example_newness_rank_lead_products": pl.Utf8,
    }
    if rank_delta_products.is_empty():
        return pl.DataFrame(schema=schema)
    available_attribute_columns = [
        column for column in attribute_columns if column in rank_delta_products.columns
    ]
    if not available_attribute_columns:
        return pl.DataFrame(schema=schema)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rank_delta_products.to_dicts():
        for column in available_attribute_columns:
            for value in _split_attribute_values(row.get(column)):
                grouped.setdefault((column, value), []).append(row)

    rows: list[dict[str, Any]] = []
    for (attribute_name, attribute_value), product_rows in grouped.items():
        deltas = [
            delta
            for row in product_rows
            if (delta := _numeric_int(row.get("rank_delta"))) is not None
        ]
        newest_ranks = [
            rank
            for row in product_rows
            if (rank := _numeric_int(row.get("newest_rank"))) is not None
        ]
        top_seller_ranks = [
            rank
            for row in product_rows
            if (rank := _numeric_int(row.get("top_seller_rank"))) is not None
        ]
        sales_leaders = [
            row
            for row in product_rows
            if (_numeric_int(row.get("rank_delta")) or 0) > 0
        ]
        newness_leaders = [
            row
            for row in product_rows
            if (_numeric_int(row.get("rank_delta")) or 0) < 0
        ]
        sales_leaders.sort(key=lambda row: -(_numeric_int(row.get("rank_delta")) or 0))
        newness_leaders.sort(key=lambda row: _numeric_int(row.get("rank_delta")) or 0)
        rows.append(
            {
                "attribute_name": attribute_name,
                "attribute_value": attribute_value,
                "product_count": len(product_rows),
                "sales_rank_lead_count": len(sales_leaders),
                "newness_rank_lead_count": len(newness_leaders),
                "rank_tie_count": sum(1 for delta in deltas if delta == 0),
                "mean_rank_delta": (sum(deltas) / len(deltas)) if deltas else None,
                "median_rank_delta": _median(deltas),
                "mean_newest_rank": (
                    sum(newest_ranks) / len(newest_ranks) if newest_ranks else None
                ),
                "mean_top_seller_rank": (
                    sum(top_seller_ranks) / len(top_seller_ranks)
                    if top_seller_ranks
                    else None
                ),
                "example_sales_rank_lead_products": CSV_LIST_SEPARATOR.join(
                    label
                    for row in sales_leaders[:5]
                    if (label := _product_rank_label(row))
                ),
                "example_newness_rank_lead_products": CSV_LIST_SEPARATOR.join(
                    label
                    for row in newness_leaders[:5]
                    if (label := _product_rank_label(row))
                ),
            }
        )
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows).sort(
        ["mean_rank_delta", "product_count", "attribute_name", "attribute_value"],
        descending=[True, True, False, False],
    )


def _bucket_from_rank(
    rank: int | None,
    total_ranked: int | None,
    total_universe_count: int | None = None,
) -> str | None:
    if rank is None or total_ranked is None or total_ranked <= 0:
        return None
    universe_denominator = max(total_ranked, int(total_universe_count or 0))
    a_cutoff = _observed_top_seller_cutoff(
        captured_ranked_count=total_ranked,
        universe_count=universe_denominator,
    )
    b_universe_cutoff = max(
        a_cutoff,
        math.ceil(
            universe_denominator * (TOP_SELLER_COHORT_SHARE + PARETO_B_COHORT_SHARE)
        ),
    )
    b_cutoff = min(total_ranked, b_universe_cutoff)
    if rank <= a_cutoff:
        return "A"
    if rank <= b_cutoff:
        return "B"
    return "C"


def _universe_top_seller_cutoff(universe_count: int | None) -> int:
    universe = int(universe_count or 0)
    if universe <= 0:
        return 0
    return max(1, math.ceil(universe * TOP_SELLER_COHORT_SHARE))


def _observed_top_seller_cutoff(
    *,
    captured_ranked_count: int | None,
    universe_count: int | None,
) -> int:
    captured = int(captured_ranked_count or 0)
    if captured <= 0:
        return 0
    universe = max(captured, int(universe_count or 0))
    return min(captured, _universe_top_seller_cutoff(universe))


def _popularity_rank_rows(
    category_listing_raw: pl.DataFrame,
    *,
    retailer: str,
    total_universe_count: int | None = None,
) -> pl.DataFrame:
    if (
        category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return pl.DataFrame(
            schema={
                "listing_identity": pl.Utf8,
                "pareto_rank": pl.Int64,
                "pareto_bucket": pl.Utf8,
            }
        )
    if "listing_identity" not in category_listing_raw.columns:
        category_listing_raw = category_listing_raw.with_columns(
            pl.when(
                pl.col("parent_product_id").is_not_null()
                & (pl.col("parent_product_id") != "")
            )
            .then(pl.col("parent_product_id"))
            .otherwise(pl.col("pdp_url"))
            .alias("listing_identity")
        )
    available_modes = {
        str(value).strip().lower()
        for value in category_listing_raw.get_column("sort_mode").drop_nulls().to_list()
        if str(value).strip()
    }
    popularity_mode = _preferred_popularity_mode(
        retailer=retailer, available_modes=available_modes
    )
    if not popularity_mode:
        return pl.DataFrame(
            schema={
                "listing_identity": pl.Utf8,
                "pareto_rank": pl.Int64,
                "pareto_bucket": pl.Utf8,
            }
        )

    ranked = (
        category_listing_raw.filter(pl.col("sort_mode") == popularity_mode)
        .sort(["page", "position"])
        .group_by("listing_identity", maintain_order=True)
        .agg(
            [
                pl.col("page").first().alias("rank_page"),
                pl.col("position").first().alias("rank_position"),
            ]
        )
    )
    if ranked.height == 0:
        return pl.DataFrame(
            schema={
                "listing_identity": pl.Utf8,
                "pareto_rank": pl.Int64,
                "pareto_bucket": pl.Utf8,
            }
        )
    total_ranked = ranked.height
    ranked = ranked.with_row_index("pareto_rank", offset=1).with_columns(
        pl.col("pareto_rank").cast(pl.Int64),
        pl.col("pareto_rank")
        .map_elements(
            lambda value: _bucket_from_rank(
                _numeric_int(value),
                total_ranked,
                total_universe_count,
            ),
            return_dtype=pl.Utf8,
        )
        .alias("pareto_bucket"),
    )
    return ranked.select(["listing_identity", "pareto_rank", "pareto_bucket"])


def _preferred_popularity_mode(
    *,
    retailer: str,
    available_modes: set[str],
) -> str | None:
    _, preferred_popularity = _retailer_sort_preferences(retailer)
    if preferred_popularity and preferred_popularity in available_modes:
        return preferred_popularity
    for fallback in TOP_SELLER_SORT_MODE_FALLBACKS:
        if fallback in available_modes:
            return fallback
    return None


def _apply_common_traction_layer(
    df: pl.DataFrame,
    *,
    category_listing_raw: pl.DataFrame,
    retailer: str,
    rank_universe_count: int | None = None,
) -> pl.DataFrame:
    popularity_ranks = _popularity_rank_rows(
        category_listing_raw,
        retailer=retailer,
        total_universe_count=rank_universe_count,
    )
    if popularity_ranks.height > 0:
        df = df.join(
            popularity_ranks.rename(
                {
                    "pareto_rank": "discovery_pareto_rank",
                    "pareto_bucket": "discovery_pareto_bucket",
                }
            ),
            on="listing_identity",
            how="left",
        )

    existing_rank_max = None
    if "pareto_rank" in df.columns:
        existing_rank_max = _numeric_int(df.get_column("pareto_rank").max())

    def _fallback_bucket(value: Any) -> str | None:
        return _bucket_from_rank(_numeric_int(value), existing_rank_max)

    with_columns: list[pl.Expr] = []
    if "discovery_pareto_rank" in df.columns:
        if "pareto_rank" in df.columns:
            with_columns.append(
                pl.coalesce(
                    [pl.col("discovery_pareto_rank"), pl.col("pareto_rank")]
                ).alias("pareto_rank")
            )
            with_columns.append(
                pl.when(pl.col("discovery_pareto_rank").is_not_null())
                .then(pl.col("discovery_pareto_bucket"))
                .otherwise(
                    pl.col("pareto_rank").map_elements(
                        _fallback_bucket,
                        return_dtype=pl.Utf8,
                    )
                )
                .alias("pareto_bucket")
            )
        else:
            with_columns.append(
                pl.col("discovery_pareto_rank")
                .map_elements(_numeric_int, return_dtype=pl.Int64)
                .alias("pareto_rank")
            )
            with_columns.append(
                pl.coalesce(
                    [
                        pl.col("discovery_pareto_bucket"),
                        pl.col("discovery_pareto_rank").map_elements(
                            _fallback_bucket,
                            return_dtype=pl.Utf8,
                        ),
                    ]
                ).alias("pareto_bucket")
            )
    elif "pareto_rank" in df.columns:
        with_columns.append(
            pl.col("pareto_rank")
            .map_elements(_numeric_int, return_dtype=pl.Int64)
            .alias("pareto_rank")
        )
        with_columns.append(
            pl.col("pareto_rank")
            .map_elements(_fallback_bucket, return_dtype=pl.Utf8)
            .alias("pareto_bucket")
        )

    if with_columns:
        df = df.with_columns(with_columns)
    cleanup = [
        column
        for column in ["discovery_pareto_rank", "discovery_pareto_bucket"]
        if column in df.columns
    ]
    if cleanup:
        df = df.drop(cleanup)
    return df


def _empty_product_universe() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "listing_identity": pl.Utf8,
            "category_key": pl.Utf8,
            "parent_product_id": pl.Utf8,
            "brand": pl.Utf8,
            "product_name": pl.Utf8,
            "pdp_url": pl.Utf8,
            "has_new_badge": pl.Boolean,
        }
    )


def _with_listing_identity(df: pl.DataFrame) -> pl.DataFrame:
    if "listing_identity" in df.columns:
        return df
    if "parent_product_id" not in df.columns and "pdp_url" not in df.columns:
        return df
    parent_expr = (
        pl.col("parent_product_id").cast(pl.Utf8, strict=False)
        if "parent_product_id" in df.columns
        else pl.lit(None, dtype=pl.Utf8)
    )
    url_expr = (
        pl.col("pdp_url").cast(pl.Utf8, strict=False)
        if "pdp_url" in df.columns
        else pl.lit(None, dtype=pl.Utf8)
    )
    return df.with_columns(
        pl.when(parent_expr.is_not_null() & (parent_expr.str.strip_chars() != ""))
        .then(parent_expr)
        .otherwise(url_expr)
        .alias("listing_identity")
    )


def _universe_source_rows(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return _empty_product_universe()
    source = _with_listing_identity(df)
    if "listing_identity" not in source.columns:
        return _empty_product_universe()

    def _source_column(name: str, dtype: pl.DataType = pl.Utf8) -> pl.Expr:
        if name in source.columns:
            return pl.col(name).cast(dtype, strict=False).alias(name)
        return pl.lit(None, dtype=dtype).alias(name)

    has_new_badge = (
        pl.col("has_new_badge").cast(pl.Boolean, strict=False).fill_null(False)
        if "has_new_badge" in source.columns
        else pl.lit(False, dtype=pl.Boolean)
    )
    return source.select(
        [
            pl.col("listing_identity")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .alias("listing_identity"),
            _source_column("category_key"),
            _source_column("parent_product_id"),
            _source_column("brand"),
            _source_column("product_name"),
            _source_column("pdp_url"),
            has_new_badge.alias("has_new_badge"),
        ]
    ).filter(
        pl.col("listing_identity").is_not_null() & (pl.col("listing_identity") != "")
    )


def _build_product_universe(
    *,
    category_listing_raw: pl.DataFrame,
    category_filters: pl.DataFrame,
    mapped_export_df: pl.DataFrame,
) -> pl.DataFrame:
    del category_filters
    del mapped_export_df

    listing_source = _universe_source_rows(category_listing_raw)
    if listing_source.height == 0:
        return _empty_product_universe()
    return (
        listing_source.group_by("listing_identity")
        .agg(
            [
                pl.col("category_key").drop_nulls().first().alias("category_key"),
                pl.col("parent_product_id")
                .drop_nulls()
                .first()
                .alias("parent_product_id"),
                pl.col("brand").drop_nulls().first().alias("brand"),
                pl.col("product_name").drop_nulls().first().alias("product_name"),
                pl.col("pdp_url").drop_nulls().first().alias("pdp_url"),
                pl.col("has_new_badge").fill_null(False).any().alias("has_new_badge"),
            ]
        )
        .sort("product_name")
    )


def _ranked_identities_for_sort(
    category_listing_raw: pl.DataFrame,
    *,
    sort_mode: str | None,
    cutoff: int,
) -> set[str]:
    if (
        cutoff <= 0
        or not sort_mode
        or category_listing_raw.height == 0
        or "sort_mode" not in category_listing_raw.columns
    ):
        return set()
    ranked_source = _with_listing_identity(category_listing_raw).filter(
        pl.col("sort_mode") == sort_mode
    )
    if ranked_source.height == 0:
        return set()
    ranked = (
        ranked_source.sort(["page", "position"])
        .group_by("listing_identity", maintain_order=True)
        .agg(pl.col("page").first().alias("rank_page"))
    )
    return set(ranked.head(cutoff).get_column("listing_identity").to_list())


def _apply_recent_status(
    product_universe: pl.DataFrame,
    category_listing_raw: pl.DataFrame,
    *,
    recent_share: float,
    recent_sort_mode: str | None,
) -> pl.DataFrame:
    if product_universe.height == 0:
        return product_universe.with_columns(pl.lit("rest").alias("listing_status"))
    cutoff = min(
        int(product_universe.height),
        max(1, math.ceil(int(product_universe.height) * recent_share)),
    )
    recent_ids = _ranked_identities_for_sort(
        category_listing_raw,
        sort_mode=recent_sort_mode,
        cutoff=cutoff,
    )
    return product_universe.with_columns(
        pl.col("listing_identity")
        .map_elements(lambda value: "recent" if value in recent_ids else "rest")
        .alias("listing_status")
    )


def _value_is_meaningful(value: Any) -> bool:
    return bool(_meaningful_text_values(value))


def _products_without_any_attributes(
    df: pl.DataFrame,
    *,
    attribute_columns: list[str],
) -> int:
    if df.is_empty():
        return 0
    present_columns = [column for column in attribute_columns if column in df.columns]
    if not present_columns:
        return int(df.height)

    def _row_has_attribute(row: dict[str, Any]) -> bool:
        return any(_value_is_meaningful(row.get(column)) for column in present_columns)

    return sum(
        1
        for row in df.select(present_columns).to_dicts()
        if not _row_has_attribute(row)
    )


def _products_with_any_attributes(
    df: pl.DataFrame,
    *,
    attribute_columns: list[str],
) -> int:
    if df.is_empty():
        return 0
    return int(df.height) - _products_without_any_attributes(
        df,
        attribute_columns=attribute_columns,
    )


def _products_with_attribute(df: pl.DataFrame, *, attribute_column: str) -> int:
    if df.is_empty() or attribute_column not in df.columns:
        return 0
    return sum(
        1
        for row in df.select(attribute_column).to_dicts()
        if _value_is_meaningful(row.get(attribute_column))
    )


SOURCE_SNAPSHOT_DIRNAME = "source_snapshots"
SOURCE_MATRIX_COMPARE_COLUMNS = (
    "category_key",
    "parent_product_id",
    "brand",
    "product_name",
    "pdp_url",
    "has_new_badge",
    "listing_status",
    "filter_membership_count",
    "filter_family_count",
    "has_filter_observations",
    "pareto_rank",
    "pareto_bucket",
    "top_seller_status",
    "sales_share",
    "sale_pressure_rank",
    "sale_pressure_status",
)
SOURCE_SNAPSHOT_SORT_COLUMNS = (
    "crawl_ts",
    "retailer",
    "category_key",
    "source_surface",
    "sort_mode",
    "page",
    "position",
    "filter_family",
    "filter_value",
    "listing_identity",
    "parent_product_id",
    "pdp_url",
)


def _source_snapshot_frame(df: pl.DataFrame) -> pl.DataFrame:
    if df.width == 0:
        return df
    normalized = _stringify_nested_columns(df)
    sort_columns = [
        column
        for column in SOURCE_SNAPSHOT_SORT_COLUMNS
        if column in normalized.columns
    ]
    if not sort_columns:
        sort_columns = list(normalized.columns)
    try:
        return normalized.sort(sort_columns)
    except pl.exceptions.PolarsError:
        return normalized


def _source_snapshot_hash(df: pl.DataFrame) -> str:
    payload = {
        "columns": list(df.columns),
        "rows": df.to_dicts() if df.width > 0 else [],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_source_snapshots(
    output_dir: Path,
    *,
    listing_observations: pl.DataFrame,
    filter_observations: pl.DataFrame,
    mapped_product_attributes: pl.DataFrame,
    retailer: str,
    category_key: str,
    discovery_crawl_ts: str | None,
    recent_share: float,
    recent_sort_mode: str | None,
    top_seller_sort_mode: str | None,
    sale_pressure_sort_mode: str | None,
) -> dict[str, Any]:
    snapshot_dir = output_dir / SOURCE_SNAPSHOT_DIRNAME
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_specs = {
        "listing_observations": (
            "listing_observations.csv",
            listing_observations,
            "Raw listing observation rows used for the package category/run.",
        ),
        "filter_observations": (
            "filter_observations.csv",
            filter_observations,
            "Raw retailer filter observation rows used for package attributes.",
        ),
        "mapped_product_attributes": (
            "mapped_product_attributes.csv",
            mapped_product_attributes,
            "Mapped PDP attribute rows joined into the package matrix.",
        ),
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for name, (filename, frame, description) in snapshot_specs.items():
        normalized = _source_snapshot_frame(frame)
        relative_path = Path(SOURCE_SNAPSHOT_DIRNAME) / filename
        normalized.write_csv(output_dir / relative_path)
        snapshots[name] = {
            "file": relative_path.as_posix(),
            "description": description,
            "row_count": int(normalized.height),
            "column_count": int(normalized.width),
            "columns": list(normalized.columns),
            "sha256": _source_snapshot_hash(normalized),
        }
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "retailer": retailer,
        "category_key": category_key,
        "discovery_crawl_ts": discovery_crawl_ts,
        "recent_share": recent_share,
        "recent_sort_mode": recent_sort_mode,
        "top_seller_sort_mode": top_seller_sort_mode,
        "sale_pressure_sort_mode": sale_pressure_sort_mode,
        "snapshots": snapshots,
    }
    (snapshot_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def _filter_source_category(df: pl.DataFrame, category_key: str) -> pl.DataFrame:
    if df.is_empty() or "category_key" not in df.columns:
        return df
    return df.filter(pl.col("category_key") == category_key)


def _filter_mapped_source_to_parents(
    mapped_export_df: pl.DataFrame,
    parent_ids: set[str],
) -> pl.DataFrame:
    if (
        mapped_export_df.is_empty()
        or "parent_product_id" not in mapped_export_df.columns
        or not parent_ids
    ):
        return mapped_export_df
    return mapped_export_df.filter(pl.col("parent_product_id").is_in(parent_ids))


def _build_source_expected_product_matrix(
    *,
    retailer: str,
    category_key: str,
    source_listing_observations: pl.DataFrame,
    source_filter_observations: pl.DataFrame,
    source_mapped_attributes: pl.DataFrame,
    recent_share: float,
    recent_sort_mode: str | None,
    sale_pressure_sort_mode: str | None,
) -> pl.DataFrame:
    source_listing = _normalize_parent_product_ids(
        _filter_source_category(source_listing_observations, category_key),
        retailer=retailer,
    )
    source_filters = _with_listing_identity(
        _normalize_parent_product_ids(
            _filter_source_category(source_filter_observations, category_key),
            retailer=retailer,
        )
    )
    source_mapped = _normalize_parent_product_ids(
        source_mapped_attributes,
        retailer=retailer,
    )
    product_universe = _build_product_universe(
        category_listing_raw=source_listing,
        category_filters=source_filters,
        mapped_export_df=source_mapped,
    )
    category_listing = _apply_recent_status(
        product_universe,
        source_listing,
        recent_share=recent_share,
        recent_sort_mode=recent_sort_mode,
    )
    filter_presence = (
        source_filters.group_by("listing_identity").agg(
            [
                pl.len().alias("filter_membership_count"),
                pl.col("filter_family").n_unique().alias("filter_family_count"),
            ]
        )
        if source_filters.height > 0
        else pl.DataFrame(
            {
                "listing_identity": [],
                "filter_membership_count": [],
                "filter_family_count": [],
            },
            schema={
                "listing_identity": pl.Utf8,
                "filter_membership_count": pl.Int64,
                "filter_family_count": pl.Int64,
            },
        )
    )
    product_filter_lists = source_filters.group_by(
        ["listing_identity", "filter_family"]
    ).agg(
        pl.col("filter_value")
        .sort()
        .unique()
        .str.join(CSV_LIST_SEPARATOR)
        .alias("filter_values")
    )
    pivot_values = (
        product_filter_lists.pivot(
            values="filter_values",
            index="listing_identity",
            on="filter_family",
            aggregate_function="first",
        )
        if product_filter_lists.height > 0
        else pl.DataFrame(
            {"listing_identity": []}, schema={"listing_identity": pl.Utf8}
        )
    )
    expected = (
        category_listing.join(pivot_values, on="listing_identity", how="left")
        .join(filter_presence, on="listing_identity", how="left")
        .with_columns(
            pl.col("filter_membership_count").fill_null(0).cast(pl.Int64),
            pl.col("filter_family_count").fill_null(0).cast(pl.Int64),
            (pl.col("filter_membership_count").fill_null(0) > 0).alias(
                "has_filter_observations"
            ),
        )
    )
    if source_mapped.height > 0:
        expected = expected.join(
            source_mapped,
            on="parent_product_id",
            how="left",
            suffix="_mapped",
        )
    expected = _apply_common_traction_layer(
        expected,
        category_listing_raw=source_listing,
        retailer=retailer,
        rank_universe_count=int(category_listing.height),
    )
    expected = _apply_sale_pressure_layer(
        expected,
        category_listing_raw=source_listing,
        sale_pressure_sort_mode=sale_pressure_sort_mode,
    )
    if "pareto_bucket" not in expected.columns:
        expected = expected.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("pareto_bucket")
        )
    expected = expected.with_columns(
        pl.col("pareto_bucket")
        .map_elements(_top_seller_status, return_dtype=pl.Utf8)
        .alias("top_seller_status")
    )
    mapped_attribute_columns = _mapped_attribute_columns(source_mapped)
    expected_rows = [
        _merge_metadata_fallbacks(
            _merge_filter_primary_attributes(
                row,
                retailer=retailer,
                category_key=category_key,
                mapped_attribute_columns=mapped_attribute_columns,
            )
        )
        for row in expected.to_dicts()
    ]
    return (
        pl.from_dicts(expected_rows, infer_schema_length=len(expected_rows))
        if expected_rows
        else expected
    )


def _source_matrix_row_index(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if df.is_empty() or "listing_identity" not in df.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in df.to_dicts():
        listing_identity = _normalize_text(row.get("listing_identity"))
        if listing_identity is not None:
            rows[listing_identity] = row
    return rows


def _source_matrix_values_match(expected: Any, observed: Any) -> bool:
    expected_float = _numeric_float(expected)
    observed_float = _numeric_float(observed)
    if expected_float is not None or observed_float is not None:
        if expected_float is None or observed_float is None:
            return False
        return abs(expected_float - observed_float) <= 1e-9
    expected_values = _split_attribute_values(expected)
    if not expected_values:
        return True
    observed_values = _split_attribute_values(observed)
    if not observed_values:
        return False
    return {value.casefold() for value in expected_values} == {
        value.casefold() for value in observed_values
    }


def _source_matrix_compare_columns(
    expected: pl.DataFrame,
    actual: pl.DataFrame,
    source_filter_observations: pl.DataFrame,
) -> list[str]:
    filter_columns = (
        [
            column
            for column in source_filter_observations.get_column("filter_family")
            .drop_nulls()
            .unique()
            .to_list()
            if isinstance(column, str)
        ]
        if source_filter_observations.height > 0
        and "filter_family" in source_filter_observations.columns
        else []
    )
    candidates = [*SOURCE_MATRIX_COMPARE_COLUMNS, *sorted(filter_columns)]
    return [
        column
        for column in dict.fromkeys(candidates)
        if column in expected.columns and column in actual.columns
    ]


def _build_source_matrix_integrity_check(
    *,
    retailer: str,
    category_key: str,
    product_filter_matrix: pl.DataFrame,
    source_listing_observations: pl.DataFrame,
    source_filter_observations: pl.DataFrame,
    source_mapped_attributes: pl.DataFrame,
    recent_share: float,
    recent_sort_mode: str | None,
    sale_pressure_sort_mode: str | None,
    source_snapshot_manifest: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = _build_source_expected_product_matrix(
        retailer=retailer,
        category_key=category_key,
        source_listing_observations=source_listing_observations,
        source_filter_observations=source_filter_observations,
        source_mapped_attributes=source_mapped_attributes,
        recent_share=recent_share,
        recent_sort_mode=recent_sort_mode,
        sale_pressure_sort_mode=sale_pressure_sort_mode,
    )
    expected_rows = _source_matrix_row_index(expected)
    actual_rows = _source_matrix_row_index(product_filter_matrix)
    expected_keys = set(expected_rows)
    actual_keys = set(actual_rows)
    missing_keys = sorted(expected_keys - actual_keys)
    unexpected_keys = sorted(actual_keys - expected_keys)
    issues: list[dict[str, Any]] = []

    if not source_snapshot_manifest:
        issues.append(
            {
                "severity": "fail",
                "check_id": "source_snapshots_present",
                "message": "Package source snapshot manifest is missing.",
            }
        )
    if source_listing_observations.height == 0:
        issues.append(
            {
                "severity": "fail",
                "check_id": "source_listing_observations_nonempty",
                "message": "Source listing observation snapshot has no rows.",
            }
        )
    if source_filter_observations.height == 0:
        issues.append(
            {
                "severity": "warning",
                "check_id": "source_filter_observations_empty",
                "message": (
                    "Source filter observation snapshot has no rows; package "
                    "attribute signal depends entirely on mapped PDP attributes."
                ),
            }
        )
    if source_mapped_attributes.height == 0:
        issues.append(
            {
                "severity": "warning",
                "check_id": "source_mapped_attributes_empty",
                "message": (
                    "Source mapped PDP attribute snapshot has no rows; package "
                    "attribute signal depends entirely on retailer filters."
                ),
            }
        )

    if missing_keys or unexpected_keys:
        issues.append(
            {
                "severity": "fail",
                "check_id": "product_filter_matrix_source_rebuild",
                "message": (
                    "product_filter_matrix listing identities do not match the "
                    "matrix rebuilt from source snapshots."
                ),
                "missing_listing_identity_count": len(missing_keys),
                "unexpected_listing_identity_count": len(unexpected_keys),
                "missing_listing_identity_samples": missing_keys[:10],
                "unexpected_listing_identity_samples": unexpected_keys[:10],
            }
        )

    compare_columns = _source_matrix_compare_columns(
        expected,
        product_filter_matrix,
        source_filter_observations,
    )
    value_mismatches: list[dict[str, Any]] = []
    for listing_identity in sorted(expected_keys & actual_keys):
        expected_row = expected_rows[listing_identity]
        actual_row = actual_rows[listing_identity]
        for column in compare_columns:
            if _source_matrix_values_match(
                expected_row.get(column),
                actual_row.get(column),
            ):
                continue
            value_mismatches.append(
                {
                    "listing_identity": listing_identity,
                    "column": column,
                    "expected_from_source": expected_row.get(column),
                    "observed_in_product_filter_matrix": actual_row.get(column),
                }
            )
    if value_mismatches:
        issues.append(
            {
                "severity": "fail",
                "check_id": "product_filter_matrix_source_rebuild",
                "message": (
                    "product_filter_matrix source-derived values do not match "
                    "the matrix rebuilt from source snapshots."
                ),
                "value_mismatch_count": len(value_mismatches),
                "value_mismatch_samples": value_mismatches[:20],
            }
        )

    mapped_attribute_columns = _mapped_attribute_columns(source_mapped_attributes)
    products_with_mapped_attributes = _products_with_any_attributes(
        product_filter_matrix,
        attribute_columns=mapped_attribute_columns,
    )
    if (
        product_filter_matrix.height > 0
        and mapped_attribute_columns
        and products_with_mapped_attributes < product_filter_matrix.height
    ):
        issues.append(
            {
                "severity": "warning",
                "check_id": "mapped_attribute_source_coverage_brittle",
                "message": (
                    "Some package products have no usable mapped PDP attributes; "
                    "signals for those rows rely on filters or remain sparse."
                ),
                "products_with_mapped_attributes": products_with_mapped_attributes,
                "product_filter_matrix_rows": int(product_filter_matrix.height),
            }
        )

    check_issues = [
        issue
        for issue in issues
        if issue.get("check_id")
        in {
            "source_snapshots_present",
            "source_listing_observations_nonempty",
            "product_filter_matrix_source_rebuild",
        }
    ]
    return (
        {
            "check_id": "product_filter_matrix_source_rebuild",
            "status": _package_integrity_status(check_issues),
            "source_listing_observation_rows": int(source_listing_observations.height),
            "source_filter_observation_rows": int(source_filter_observations.height),
            "source_mapped_attribute_rows": int(source_mapped_attributes.height),
            "expected_product_rows": len(expected_keys),
            "actual_product_rows": len(actual_keys),
            "missing_listing_identity_count": len(missing_keys),
            "unexpected_listing_identity_count": len(unexpected_keys),
            "value_mismatch_count": len(value_mismatches),
            "compared_columns": compare_columns,
            "source_snapshot_manifest": dict(source_snapshot_manifest or {}),
        },
        issues,
    )


def _package_diagnostic_warnings(
    *,
    listing_products: int,
    products_with_brand: int,
    materialized_filter_attribute_rows: int,
    mapped_attribute_comparison_rows: int,
    top_seller_mapped_attribute_comparison_rows: int,
    recent_products: int,
    top_seller_products: int,
    innovation_pair_rows: int,
    innovation_triple_rows: int,
    top_seller_pair_rows: int,
    top_seller_triple_rows: int,
    recent_products_with_reviews: int,
    top_seller_review_validation_rows: int,
    bundle_review_validation_rows: int,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    def add_warning(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    if listing_products > 0 and products_with_brand == 0:
        add_warning(
            "brand_column_empty",
            "Package output has products but no populated brand values. "
            "This is usually a packaging bug, not a real catalog condition.",
        )

    if (
        top_seller_products > 0
        and top_seller_mapped_attribute_comparison_rows > 0
        and top_seller_pair_rows == 0
        and top_seller_triple_rows == 0
    ):
        add_warning(
            "top_seller_bundles_empty_despite_attribute_signal",
            "Top-seller attribute comparisons are populated but top-seller bundle tables are empty. "
            "Check bundle input columns, brand coverage, and bundle-filter thresholds.",
        )

    if (
        recent_products > 0
        and materialized_filter_attribute_rows > 0
        and mapped_attribute_comparison_rows > 0
        and innovation_pair_rows == 0
        and innovation_triple_rows == 0
    ):
        add_warning(
            "innovation_bundles_empty_despite_attribute_signal",
            "Recent-vs-rest attribute comparisons are populated but innovation bundle tables are empty. "
            "Check bundle input columns, brand coverage, and bundle-filter thresholds.",
        )

    if (
        top_seller_products > 0
        and recent_products_with_reviews > 0
        and top_seller_pair_rows + top_seller_triple_rows > 0
        and top_seller_review_validation_rows == 0
    ):
        add_warning(
            "top_seller_review_validation_empty_despite_bundles_and_reviews",
            "Top-seller bundles exist and reviews are present, but top-seller review validation is empty. "
            "Check review extraction and bundle-to-product matching.",
        )

    if (
        recent_products > 0
        and recent_products_with_reviews > 0
        and innovation_pair_rows + innovation_triple_rows > 0
        and bundle_review_validation_rows == 0
    ):
        add_warning(
            "innovation_review_validation_empty_despite_bundles_and_reviews",
            "Innovation bundles exist and reviews are present, but bundle review validation is empty. "
            "Check review extraction and bundle-to-product matching.",
        )

    return warnings


def _warning_payload(
    *,
    package_type: str,
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    normalized_warnings = [dict(warning) for warning in warnings]
    return {
        "package_type": package_type,
        "status": "pass_with_warnings" if normalized_warnings else "pass",
        "warning_count": len(normalized_warnings),
        "warnings": normalized_warnings,
    }


def _integrity_warning_rows(
    package_integrity: Mapping[str, Any],
    *,
    source: str,
) -> list[dict[str, Any]]:
    issues = package_integrity.get("issues")
    if not isinstance(issues, Sequence) or isinstance(issues, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, Mapping) or issue.get("severity") != "warning":
            continue
        rows.append(
            {
                "source": source,
                "severity": "warning",
                "code": issue.get("check_id") or "package_integrity_warning",
                "message": issue.get("message") or "Package integrity warning.",
                "details": dict(issue),
            }
        )
    return rows


def _launch_package_warning_payload(
    *,
    summary: Mapping[str, Any],
    package_integrity: Mapping[str, Any],
    diagnostic_warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    warnings.extend(
        _integrity_warning_rows(
            package_integrity,
            source="package_integrity",
        )
    )
    for diagnostic in diagnostic_warnings:
        warnings.append(
            {
                "source": "package_diagnostics",
                "severity": "warning",
                "code": diagnostic.get("code") or "diagnostic_warning",
                "message": diagnostic.get("message") or "Package diagnostic warning.",
                "details": dict(diagnostic),
            }
        )
    if int(summary.get("sale_pressure_products") or 0) == 0:
        sale_pressure_available = bool(summary.get("sale_pressure_available"))
        warning_code = (
            "sale_pressure_absence_not_proof_of_no_discount"
            if sale_pressure_available
            else "sale_pressure_surface_unavailable"
        )
        warning_message = (
            "No sale-pressure products were observed in the captured ranked "
            "window. This is not proof that products were undiscounted."
            if sale_pressure_available
            else (
                "No sale-first or promotion-first ranked sort surface was "
                "observed. Do not discuss sale-pressure evidence as available "
                "or infer discount status from its absence."
            )
        )
        warnings.append(
            {
                "source": "package_context",
                "severity": "warning",
                "code": warning_code,
                "message": warning_message,
                "details": {
                    "sale_pressure_available": sale_pressure_available,
                    "sale_pressure_sort_mode": summary.get("sale_pressure_sort_mode"),
                    "sale_pressure_absence_interpretation": summary.get(
                        "sale_pressure_absence_interpretation"
                    ),
                },
            }
        )
    return _warning_payload(
        package_type="retailer_category_evidence", warnings=warnings
    )


def _bundle_attribute_columns(
    *,
    retailer: str,
    category_key: str,
    available_columns: list[str],
    default_columns: list[str],
) -> list[str]:
    override = RETAILER_CATEGORY_BUNDLE_COLUMNS.get((retailer.lower(), category_key))
    if override:
        return [column for column in override if column in available_columns]
    return [column for column in default_columns if column in available_columns]


SIGNAL_INTEGRITY_METRIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "innovation": (
        "count_recent",
        "count_rest",
        "recent_brand_count",
        "rest_brand_count",
        "recent_base",
        "rest_base",
        "pct_recent",
        "pct_rest",
        "delta",
        "prevalence_ratio",
    ),
    "winning_now": (
        "count_top_seller",
        "count_other",
        "top_seller_brand_count",
        "other_brand_count",
        "top_seller_base",
        "other_base",
        "pct_top_seller",
        "pct_other",
        "delta",
        "prevalence_ratio",
    ),
    "sale_pressure": (
        "count_sale_pressure",
        "count_not_observed_sale_pressure",
        "sale_pressure_brand_count",
        "not_observed_sale_pressure_brand_count",
        "sale_pressure_base",
        "not_observed_sale_pressure_base",
        "pct_sale_pressure",
        "pct_not_observed_sale_pressure",
        "delta",
        "prevalence_ratio",
    ),
}


def _package_integrity_status(issues: Sequence[Mapping[str, Any]]) -> str:
    if any(issue.get("severity") == "fail" for issue in issues):
        return "fail"
    if any(issue.get("severity") == "warning" for issue in issues):
        return "pass_with_warnings"
    return "pass"


def _package_integrity_counts(issues: Sequence[Mapping[str, Any]]) -> tuple[int, int]:
    fail_count = sum(1 for issue in issues if issue.get("severity") == "fail")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    return fail_count, warning_count


def _nonempty_unique_count(df: pl.DataFrame, column: str) -> int:
    if df.is_empty() or column not in df.columns:
        return 0
    values = {
        text
        for value in df.get_column(column).to_list()
        if (text := _normalize_text(value))
    }
    return len(values)


def _bundle_row_index(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if df.is_empty() or "bundle_key" not in df.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in df.to_dicts():
        key = _normalize_text(row.get("bundle_key"))
        if key is not None:
            rows[key] = row
    return rows


def _integrity_values_match(expected: Any, observed: Any) -> bool:
    expected_float = _numeric_float(expected)
    observed_float = _numeric_float(observed)
    if expected_float is not None or observed_float is not None:
        if expected_float is None or observed_float is None:
            return False
        return abs(expected_float - observed_float) <= 1e-9
    return _normalize_text(expected) == _normalize_text(observed)


def _expected_signal_table(
    *,
    df: pl.DataFrame,
    attribute_columns: list[str],
    bundle_size: int,
    signal_layer: str,
) -> pl.DataFrame:
    if signal_layer == "winning_now":
        signals = _build_focus_bundle_signals(
            df=df,
            attribute_columns=attribute_columns,
            bundle_size=bundle_size,
            status_column="top_seller_status",
            focus_label="top_seller",
            other_label="other",
            focus_prefix="top_seller",
            other_prefix="other",
        )
    elif signal_layer == "sale_pressure":
        signals = _build_focus_bundle_signals(
            df=df,
            attribute_columns=attribute_columns,
            bundle_size=bundle_size,
            status_column="sale_pressure_status",
            focus_label="sale_pressure",
            other_label="not_observed_sale_pressure",
            focus_prefix="sale_pressure",
            other_prefix="not_observed_sale_pressure",
        )
    else:
        signals = _build_bundle_signals(
            df=df,
            attribute_columns=attribute_columns,
            bundle_size=bundle_size,
        )
    category_center_components = _category_center_component_table(
        df,
        attribute_columns=attribute_columns,
    )
    signals = _with_signal_insight_metadata(
        signals,
        signal_layer=signal_layer,
        category_center_components=category_center_components,
    )
    selected, _context = _split_signal_rows_by_usefulness(signals)
    return selected


def _build_signal_integrity_check(
    *,
    check_id: str,
    expected: pl.DataFrame,
    actual: pl.DataFrame,
    signal_layer: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected_rows = _bundle_row_index(expected)
    actual_rows = _bundle_row_index(actual)
    expected_keys = set(expected_rows)
    actual_keys = set(actual_rows)
    missing_keys = sorted(expected_keys - actual_keys)
    unexpected_keys = sorted(actual_keys - expected_keys)
    issues: list[dict[str, Any]] = []

    if missing_keys or unexpected_keys:
        issues.append(
            {
                "severity": "fail",
                "check_id": check_id,
                "message": (
                    "Signal table does not match the signal rows recomputed from "
                    "the final product_filter_matrix inputs."
                ),
                "missing_bundle_keys": missing_keys[:10],
                "unexpected_bundle_keys": unexpected_keys[:10],
                "missing_bundle_count": len(missing_keys),
                "unexpected_bundle_count": len(unexpected_keys),
            }
        )

    metric_mismatches: list[dict[str, Any]] = []
    for bundle_key in sorted(expected_keys & actual_keys):
        expected_row = expected_rows[bundle_key]
        actual_row = actual_rows[bundle_key]
        for column in SIGNAL_INTEGRITY_METRIC_COLUMNS[signal_layer]:
            if column not in expected_row:
                continue
            if column not in actual_row:
                metric_mismatches.append(
                    {
                        "bundle_key": bundle_key,
                        "column": column,
                        "expected": expected_row.get(column),
                        "observed": None,
                    }
                )
                continue
            if _integrity_values_match(
                expected_row.get(column), actual_row.get(column)
            ):
                continue
            metric_mismatches.append(
                {
                    "bundle_key": bundle_key,
                    "column": column,
                    "expected": expected_row.get(column),
                    "observed": actual_row.get(column),
                }
            )
    if metric_mismatches:
        issues.append(
            {
                "severity": "fail",
                "check_id": check_id,
                "message": (
                    "Signal table metric values do not match recomputed package "
                    "values."
                ),
                "metric_mismatch_count": len(metric_mismatches),
                "metric_mismatch_samples": metric_mismatches[:10],
            }
        )

    return (
        {
            "check_id": check_id,
            "status": _package_integrity_status(issues),
            "expected_row_count": len(expected_keys),
            "actual_row_count": len(actual_keys),
            "missing_bundle_count": len(missing_keys),
            "unexpected_bundle_count": len(unexpected_keys),
            "metric_mismatch_count": len(metric_mismatches),
        },
        issues,
    )


def _product_subset_count(df: pl.DataFrame, *, column: str, value: str) -> int:
    if df.is_empty() or column not in df.columns:
        return 0
    return int(df.filter(pl.col(column) == value).height)


def _build_launch_package_integrity_audit(
    *,
    retailer: str | None = None,
    category_key: str,
    source_category_key: str | None = None,
    product_filter_matrix: pl.DataFrame,
    recent_products: pl.DataFrame,
    top_seller_products: pl.DataFrame,
    sale_pressure_products: pl.DataFrame,
    innovation_pairs: pl.DataFrame,
    innovation_triples: pl.DataFrame,
    top_seller_pairs: pl.DataFrame,
    top_seller_triples: pl.DataFrame,
    sale_pressure_pairs: pl.DataFrame,
    sale_pressure_triples: pl.DataFrame,
    bundle_attribute_columns: list[str],
    source_listing_observations: pl.DataFrame | None = None,
    source_filter_observations: pl.DataFrame | None = None,
    source_mapped_attributes: pl.DataFrame | None = None,
    recent_share: float | None = None,
    recent_sort_mode: str | None = None,
    sale_pressure_sort_mode: str | None = None,
    source_snapshot_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit launch package tables against the final package product matrix."""

    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    source_rebuild_check: dict[str, Any] | None = None
    matrix_row_count = int(product_filter_matrix.height)
    present_bundle_attribute_columns = [
        column
        for column in bundle_attribute_columns
        if column in product_filter_matrix.columns
    ]
    products_with_bundle_attributes = _products_with_any_attributes(
        product_filter_matrix,
        attribute_columns=present_bundle_attribute_columns,
    )
    listing_identity_count = _nonempty_unique_count(
        product_filter_matrix,
        "listing_identity",
    )
    parent_id_count = _nonempty_unique_count(product_filter_matrix, "parent_product_id")
    duplicate_listing_count = max(0, matrix_row_count - listing_identity_count)
    recent_count = _product_subset_count(
        product_filter_matrix,
        column="listing_status",
        value="recent",
    )
    rest_count = _product_subset_count(
        product_filter_matrix,
        column="listing_status",
        value="rest",
    )
    top_seller_count = _product_subset_count(
        product_filter_matrix,
        column="top_seller_status",
        value="top_seller",
    )
    sale_pressure_count = _product_subset_count(
        product_filter_matrix,
        column="sale_pressure_status",
        value="sale_pressure",
    )
    if matrix_row_count == 0:
        issues.append(
            {
                "severity": "fail",
                "check_id": "product_filter_matrix_nonempty",
                "message": "product_filter_matrix has no package product rows.",
            }
        )
    if not present_bundle_attribute_columns:
        issues.append(
            {
                "severity": "fail",
                "check_id": "bundle_attribute_inputs_nonempty",
                "message": (
                    "No usable bundle attribute columns are present in "
                    "product_filter_matrix."
                ),
                "configured_bundle_attribute_columns": bundle_attribute_columns,
            }
        )
    elif matrix_row_count > 0 and products_with_bundle_attributes == 0:
        issues.append(
            {
                "severity": "fail",
                "check_id": "bundle_attribute_inputs_nonempty",
                "message": (
                    "Bundle attribute columns are present, but no package products "
                    "have usable bundle attribute values."
                ),
                "bundle_attribute_columns": present_bundle_attribute_columns,
            }
        )
    if duplicate_listing_count:
        issues.append(
            {
                "severity": "fail",
                "check_id": "product_filter_matrix_identity",
                "message": "product_filter_matrix contains duplicate listing identities.",
                "duplicate_listing_count": duplicate_listing_count,
            }
        )
    if recent_count != int(recent_products.height):
        issues.append(
            {
                "severity": "fail",
                "check_id": "recent_products_consistency",
                "message": "recent_products does not match product_filter_matrix.",
                "expected_recent_products": recent_count,
                "observed_recent_products": int(recent_products.height),
            }
        )
    if top_seller_count != int(top_seller_products.height):
        issues.append(
            {
                "severity": "fail",
                "check_id": "top_seller_products_consistency",
                "message": "top_seller_products does not match product_filter_matrix.",
                "expected_top_seller_products": top_seller_count,
                "observed_top_seller_products": int(top_seller_products.height),
            }
        )
    if sale_pressure_count != int(sale_pressure_products.height):
        issues.append(
            {
                "severity": "fail",
                "check_id": "sale_pressure_products_consistency",
                "message": (
                    "sale_pressure_products does not match product_filter_matrix."
                ),
                "expected_sale_pressure_products": sale_pressure_count,
                "observed_sale_pressure_products": int(sale_pressure_products.height),
            }
        )
    checks.extend(
        [
            {
                "check_id": "product_filter_matrix_nonempty",
                "status": "fail" if matrix_row_count == 0 else "pass",
                "product_row_count": matrix_row_count,
            },
            {
                "check_id": "bundle_attribute_inputs_nonempty",
                "status": (
                    "pass"
                    if present_bundle_attribute_columns
                    and products_with_bundle_attributes > 0
                    else "fail"
                ),
                "configured_bundle_attribute_columns": bundle_attribute_columns,
                "present_bundle_attribute_columns": present_bundle_attribute_columns,
                "products_with_bundle_attributes": products_with_bundle_attributes,
            },
            {
                "check_id": "product_filter_matrix_identity",
                "status": "fail" if duplicate_listing_count else "pass",
                "product_row_count": matrix_row_count,
                "unique_listing_identity_count": listing_identity_count,
                "unique_parent_product_id_count": parent_id_count,
                "duplicate_listing_count": duplicate_listing_count,
            },
            {
                "check_id": "product_cohort_outputs_consistency",
                "status": (
                    "fail"
                    if recent_count != int(recent_products.height)
                    or top_seller_count != int(top_seller_products.height)
                    or sale_pressure_count != int(sale_pressure_products.height)
                    else "pass"
                ),
                "recent_products_expected": recent_count,
                "recent_products_actual": int(recent_products.height),
                "rest_products_expected": rest_count,
                "top_seller_products_expected": top_seller_count,
                "top_seller_products_actual": int(top_seller_products.height),
                "sale_pressure_products_expected": sale_pressure_count,
                "sale_pressure_products_actual": int(sale_pressure_products.height),
            },
        ]
    )

    if (
        retailer is not None
        and source_listing_observations is not None
        and source_filter_observations is not None
        and source_mapped_attributes is not None
    ):
        source_rebuild_check, source_issues = _build_source_matrix_integrity_check(
            retailer=retailer,
            category_key=source_category_key or category_key,
            product_filter_matrix=product_filter_matrix,
            source_listing_observations=source_listing_observations,
            source_filter_observations=source_filter_observations,
            source_mapped_attributes=source_mapped_attributes,
            recent_share=recent_share if recent_share is not None else 0.20,
            recent_sort_mode=recent_sort_mode,
            sale_pressure_sort_mode=sale_pressure_sort_mode,
            source_snapshot_manifest=source_snapshot_manifest,
        )
        checks.append(source_rebuild_check)
        issues.extend(source_issues)

    signal_specs = [
        ("innovation_pairs_recompute", "innovation", 2, innovation_pairs),
        ("innovation_triples_recompute", "innovation", 3, innovation_triples),
        ("top_seller_pairs_recompute", "winning_now", 2, top_seller_pairs),
        ("top_seller_triples_recompute", "winning_now", 3, top_seller_triples),
        ("sale_pressure_pairs_recompute", "sale_pressure", 2, sale_pressure_pairs),
        ("sale_pressure_triples_recompute", "sale_pressure", 3, sale_pressure_triples),
    ]
    for check_id, signal_layer, bundle_size, actual in signal_specs:
        expected = _expected_signal_table(
            df=product_filter_matrix,
            attribute_columns=bundle_attribute_columns,
            bundle_size=bundle_size,
            signal_layer=signal_layer,
        )
        check, check_issues = _build_signal_integrity_check(
            check_id=check_id,
            expected=expected,
            actual=actual,
            signal_layer=signal_layer,
        )
        checks.append(check)
        issues.extend(check_issues)

    failure_count, warning_count = _package_integrity_counts(issues)
    return {
        "status": _package_integrity_status(issues),
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "check_count": len(checks),
            "failure_count": failure_count,
            "warning_count": warning_count,
            "product_filter_matrix_rows": matrix_row_count,
            "unique_listing_identity_count": listing_identity_count,
            "unique_parent_product_id_count": parent_id_count,
            "recent_products": recent_count,
            "top_seller_products": top_seller_count,
            "sale_pressure_products": sale_pressure_count,
            "source_rebuild": source_rebuild_check,
        },
        "checks": checks,
        "issues": issues,
    }


def _semantic_analysis_attribute_columns(
    *,
    mapped_semantic_columns: list[str],
    filter_attribute_columns: list[str],
    available_columns: list[str],
) -> list[str]:
    if mapped_semantic_columns:
        return mapped_semantic_columns
    return [
        column
        for column in filter_attribute_columns
        if column in available_columns and _is_analysis_attribute_column(column)
    ]


def _fetch_og_image_url(pdp_url: str | None) -> str | None:
    url = _normalize_url_text(pdp_url)
    if not url:
        return None
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            html = response.read(800_000).decode("utf-8", errors="replace")
    except (OSError, URLError):
        return None
    match = OG_IMAGE_RE.search(html)
    if not match:
        return None
    return _normalize_url_text(match.group(1))


def _infer_image_suffix(image_url: str | None) -> str:
    url = _normalize_url_text(image_url)
    if not url:
        return ".jpg"
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".jpg"


def _download_image(image_url: str | None, destination: Path) -> str | None:
    url = _normalize_url_text(image_url)
    if not url:
        return None
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
    except (OSError, URLError):
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return str(destination.resolve())


def _materialize_pack_image(
    *,
    output_dir: Path,
    parent_id: str | None,
    local_image_path: str | None,
    hero_image_url: str | None,
    swatch_image_url: str | None,
    pdp_url: str | None,
) -> dict[str, str | None]:
    normalized_parent = _normalize_text(parent_id)
    if not normalized_parent:
        return {
            "pack_image_path": None,
            "pack_image_source": None,
            "og_image_url": None,
        }

    images_dir = output_dir / "images"
    og_image_url = None

    if local_image_path:
        source = Path(local_image_path)
        if source.exists():
            destination = (
                images_dir / f"{normalized_parent}{source.suffix.lower() or '.png'}"
            )
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            return {
                "pack_image_path": str(destination.resolve()),
                "pack_image_source": "local_image_path",
                "og_image_url": None,
            }

    for source_name, image_url in (
        ("hero_image_url", hero_image_url),
        ("swatch_image_url", swatch_image_url),
    ):
        normalized_url = _normalize_url_text(image_url)
        if not normalized_url:
            continue
        destination = (
            images_dir / f"{normalized_parent}{_infer_image_suffix(normalized_url)}"
        )
        image_path = _download_image(normalized_url, destination)
        if image_path:
            return {
                "pack_image_path": image_path,
                "pack_image_source": source_name,
                "og_image_url": None,
            }

    og_image_url = _fetch_og_image_url(pdp_url)
    if og_image_url:
        destination = (
            images_dir / f"{normalized_parent}{_infer_image_suffix(og_image_url)}"
        )
        image_path = _download_image(og_image_url, destination)
        if image_path:
            return {
                "pack_image_path": image_path,
                "pack_image_source": "og_image_url",
                "og_image_url": og_image_url,
            }

    return {
        "pack_image_path": None,
        "pack_image_source": None,
        "og_image_url": og_image_url,
    }


def _empty_pack_image_meta() -> dict[str, str | None]:
    return {
        "pack_image_path": None,
        "pack_image_source": None,
        "og_image_url": None,
    }


def _materialize_limited_pack_image(
    *,
    output_dir: Path,
    parent_id: str | None,
    local_image_path: str | None,
    hero_image_url: str | None,
    swatch_image_url: str | None,
    pdp_url: str | None,
    listing_status: str | None,
    copied_pack_images: int,
    max_pack_images: int,
) -> tuple[dict[str, str | None], int]:
    if _normalize_text(listing_status) != "recent":
        return _empty_pack_image_meta(), copied_pack_images
    if copied_pack_images >= max_pack_images:
        return _empty_pack_image_meta(), copied_pack_images

    pack_image_meta = _materialize_pack_image(
        output_dir=output_dir,
        parent_id=parent_id,
        local_image_path=local_image_path,
        hero_image_url=hero_image_url,
        swatch_image_url=swatch_image_url,
        pdp_url=pdp_url,
    )
    if pack_image_meta.get("pack_image_path"):
        copied_pack_images += 1
    return pack_image_meta, copied_pack_images


def _relative_output_path(output_dir: Path, file_path: str | None) -> str | None:
    path_text = _normalize_text(file_path)
    if not path_text:
        return None
    try:
        return str(Path(path_text).resolve().relative_to(output_dir.resolve()))
    except Exception:
        return None


def _build_family_denominators(
    filter_df: pl.DataFrame, status_df: pl.DataFrame
) -> pl.DataFrame:
    required_columns = {"listing_identity", "filter_family"}
    if filter_df.is_empty() or not required_columns.issubset(set(filter_df.columns)):
        return pl.DataFrame(
            schema={
                "filter_family": pl.Utf8,
                "listing_status": pl.Utf8,
                "family_product_count": pl.Int64,
            }
        )
    return (
        filter_df.select(["listing_identity", "filter_family"])
        .unique()
        .join(status_df, on="listing_identity", how="inner")
        .group_by(["filter_family", "listing_status"])
        .agg(pl.len().alias("family_product_count"))
    )


def _markdown_excerpt(text: str | None, *, limit: int = 500) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"#+\\s*", "", text)
    cleaned = re.sub(r"\\n{2,}", "\n", cleaned)
    cleaned = re.sub(r"[*_`>-]", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _review_excerpt(text: str | None, *, limit: int = 280) -> str | None:
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _review_validation_schema() -> dict[str, pl.DataType]:
    schema: dict[str, pl.DataType] = {
        "bundle_size": pl.Int64,
        "bundle_key": pl.Utf8,
        "bundle_label": pl.Utf8,
        "product_name": pl.Utf8,
        "brand": pl.Utf8,
        "parent_product_id": pl.Utf8,
        "pareto_rank": pl.Int64,
        "pareto_bucket": pl.Utf8,
        "sales_share": pl.Float64,
        "rating": pl.Float64,
        "review_count": pl.Int64,
        "review_snippet_count": pl.Int64,
        "reviews_json": pl.Utf8,
        "reviews_positive_headline": pl.Utf8,
        "reviews_positive_comment": pl.Utf8,
        "reviews_negative_headline": pl.Utf8,
        "reviews_negative_comment": pl.Utf8,
    }
    for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1):
        schema[f"review_{index}_headline"] = pl.Utf8
        schema[f"review_{index}_comment"] = pl.Utf8
        schema[f"review_{index}_rating"] = pl.Float64
        schema[f"review_{index}_created_date"] = pl.Utf8
    return schema


def _review_theme_comparison_schema() -> dict[str, pl.DataType]:
    return {
        "comparison_type": pl.Utf8,
        "theme_level": pl.Utf8,
        "theme_id": pl.Utf8,
        "theme_label": pl.Utf8,
        "theme_family": pl.Utf8,
        "focus_label": pl.Utf8,
        "baseline_label": pl.Utf8,
        "focus_reviewed_products": pl.Int64,
        "baseline_reviewed_products": pl.Int64,
        "focus_review_count": pl.Int64,
        "baseline_review_count": pl.Int64,
        "focus_products_with_theme": pl.Int64,
        "baseline_products_with_theme": pl.Int64,
        "focus_reviews_with_theme": pl.Int64,
        "baseline_reviews_with_theme": pl.Int64,
        "focus_product_mention_rate": pl.Float64,
        "baseline_product_mention_rate": pl.Float64,
        "product_mention_rate_delta": pl.Float64,
        "product_mention_rate_ratio": pl.Float64,
        "focus_review_mention_rate": pl.Float64,
        "baseline_review_mention_rate": pl.Float64,
        "review_mention_rate_delta": pl.Float64,
        "focus_positive_tags": pl.Int64,
        "focus_negative_tags": pl.Int64,
        "focus_mixed_tags": pl.Int64,
        "baseline_positive_tags": pl.Int64,
        "baseline_negative_tags": pl.Int64,
        "baseline_mixed_tags": pl.Int64,
        "focus_positive_reviews": pl.Int64,
        "focus_negative_reviews": pl.Int64,
        "focus_mixed_reviews": pl.Int64,
        "baseline_positive_reviews": pl.Int64,
        "baseline_negative_reviews": pl.Int64,
        "baseline_mixed_reviews": pl.Int64,
        "focus_positive_review_rate": pl.Float64,
        "baseline_positive_review_rate": pl.Float64,
        "positive_review_rate_delta": pl.Float64,
        "positive_review_rate_ratio": pl.Float64,
        "focus_negative_review_rate": pl.Float64,
        "baseline_negative_review_rate": pl.Float64,
        "negative_review_rate_delta": pl.Float64,
        "negative_review_rate_ratio": pl.Float64,
        "focus_mixed_review_rate": pl.Float64,
        "baseline_mixed_review_rate": pl.Float64,
        "mixed_review_rate_delta": pl.Float64,
        "focus_net_positive_review_rate": pl.Float64,
        "baseline_net_positive_review_rate": pl.Float64,
        "net_positive_review_rate_delta": pl.Float64,
        "focus_positive_products": pl.Int64,
        "focus_negative_products": pl.Int64,
        "baseline_positive_products": pl.Int64,
        "baseline_negative_products": pl.Int64,
        "focus_positive_product_rate": pl.Float64,
        "baseline_positive_product_rate": pl.Float64,
        "positive_product_rate_delta": pl.Float64,
        "focus_negative_product_rate": pl.Float64,
        "baseline_negative_product_rate": pl.Float64,
        "negative_product_rate_delta": pl.Float64,
        "experience_signal_class": pl.Utf8,
        "experience_signal_direction": pl.Utf8,
        "experience_signal_score": pl.Float64,
        "experience_signal_summary": pl.Utf8,
        "focus_evidence_json": pl.Utf8,
        "baseline_evidence_json": pl.Utf8,
        "sample_size_status": pl.Utf8,
    }


def _fetch_review_theme_cohort_comparison(
    pdp_store_path: Path,
    *,
    retailer: str,
    category_key: str,
    product_matrix: pl.DataFrame,
) -> pl.DataFrame:
    schema = _review_theme_comparison_schema()
    comparison_specs = _review_theme_package_comparison_specs(product_matrix)
    if not comparison_specs:
        return pl.DataFrame(schema=schema)
    with connect_pdp_database(pdp_store_path) as conn:
        ensure_review_theme_schema(conn)
        latest = conn.execute(
            """
            SELECT run_id
            FROM pdp_review_theme_runs
            WHERE retailer = ?
              AND category_key = ?
              AND run_scope = 'full'
              AND package_eligible = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (retailer, category_key),
        ).fetchone()
        run_id = latest[0] if latest else None
        if not run_id:
            return pl.DataFrame(schema=schema)
        review_rows = conn.execute(
            """
            SELECT review_id, parent_product_id
            FROM pdp_review_theme_reviews
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
        tag_rows = conn.execute(
            """
            SELECT
                t.review_id,
                t.parent_product_id,
                t.theme_id,
                c.theme_label,
                c.theme_family,
                t.polarity,
                t.evidence_span,
                t.actor,
                t.target,
                t.confidence,
                r.brand,
                r.product_name,
                r.rating
            FROM pdp_review_theme_tags t
            JOIN pdp_review_theme_codebook c
              ON c.run_id = t.run_id
             AND c.theme_id = t.theme_id
            JOIN pdp_review_theme_reviews r
              ON r.run_id = t.run_id
             AND r.review_id = t.review_id
            WHERE t.run_id = ?
            """,
            (run_id,),
        ).fetchall()
    rows = _build_review_theme_package_comparison_rows(
        review_rows=review_rows,
        tag_rows=tag_rows,
        comparison_specs=comparison_specs,
    )
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(
        rows,
        schema=schema,
    ).sort(
        [
            "comparison_type",
            "experience_signal_score",
            "product_mention_rate_delta",
            "theme_label",
        ],
        descending=[False, True, True, False],
    )


def _review_theme_package_comparison_specs(
    product_matrix: pl.DataFrame,
) -> tuple[dict[str, object], ...]:
    columns, _schema = get_schema_and_column_names(product_matrix)
    if "parent_product_id" not in columns:
        return ()
    selected_columns = [
        column
        for column in ("parent_product_id", "top_seller_status", "listing_status")
        if column in columns
    ]
    rows = product_matrix.select(selected_columns).to_dicts()
    all_ids = {
        str(row["parent_product_id"])
        for row in rows
        if _normalize_text(row.get("parent_product_id"))
    }
    if not all_ids:
        return ()
    specs: list[dict[str, object]] = []
    if "top_seller_status" in selected_columns:
        top_ids = {
            str(row["parent_product_id"])
            for row in rows
            if _normalize_text(row.get("parent_product_id"))
            and row.get("top_seller_status") == "top_seller"
        }
        if top_ids and all_ids - top_ids:
            specs.append(
                {
                    "comparison_type": "top_seller_vs_other",
                    "focus_label": "top sellers",
                    "baseline_label": "other products",
                    "focus_product_ids": top_ids,
                    "baseline_product_ids": all_ids - top_ids,
                }
            )
    if "listing_status" in selected_columns:
        recent_ids = {
            str(row["parent_product_id"])
            for row in rows
            if _normalize_text(row.get("parent_product_id"))
            and row.get("listing_status") == "recent"
        }
        if recent_ids and all_ids - recent_ids:
            specs.append(
                {
                    "comparison_type": "recent_vs_rest",
                    "focus_label": "recent products",
                    "baseline_label": "rest of shelf",
                    "focus_product_ids": recent_ids,
                    "baseline_product_ids": all_ids - recent_ids,
                }
            )
    return tuple(specs)


def _build_review_theme_package_comparison_rows(
    *,
    review_rows: Sequence[Sequence[object]],
    tag_rows: Sequence[Sequence[object]],
    comparison_specs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    review_product_by_id = {
        str(review_id): str(parent_product_id)
        for review_id, parent_product_id in review_rows
        if review_id and parent_product_id
    }
    review_ids_by_product: dict[str, set[str]] = {}
    for review_id, parent_product_id in review_product_by_id.items():
        review_ids_by_product.setdefault(parent_product_id, set()).add(review_id)
    tags = [_review_theme_tag_row(row) for row in tag_rows]
    tags = [tag for tag in tags if tag["review_id"] in review_product_by_id]
    theme_groups = _review_theme_tag_groups(tags)
    rows: list[dict[str, object]] = []
    for spec in comparison_specs:
        focus_ids = _coerce_review_theme_product_ids(spec.get("focus_product_ids"))
        baseline_ids = _coerce_review_theme_product_ids(
            spec.get("baseline_product_ids")
        )
        if not focus_ids or not baseline_ids:
            continue
        focus_review_ids = _review_ids_for_products(review_ids_by_product, focus_ids)
        baseline_review_ids = _review_ids_for_products(
            review_ids_by_product, baseline_ids
        )
        focus_reviewed_product_ids = {
            product_id
            for product_id in focus_ids
            if review_ids_by_product.get(product_id)
        }
        baseline_reviewed_product_ids = {
            product_id
            for product_id in baseline_ids
            if review_ids_by_product.get(product_id)
        }
        for theme_group in theme_groups:
            theme_tags = list(theme_group["tags"])
            focus_tags = [
                tag for tag in theme_tags if tag["review_id"] in focus_review_ids
            ]
            baseline_tags = [
                tag for tag in theme_tags if tag["review_id"] in baseline_review_ids
            ]
            row = _build_review_theme_package_comparison_row(
                comparison_type=str(spec["comparison_type"]),
                theme_level=str(theme_group["theme_level"]),
                theme_id=str(theme_group["theme_id"]),
                theme_label=str(theme_group["theme_label"]),
                theme_family=str(theme_group["theme_family"]),
                focus_label=str(spec["focus_label"]),
                baseline_label=str(spec["baseline_label"]),
                focus_review_ids=focus_review_ids,
                baseline_review_ids=baseline_review_ids,
                focus_reviewed_product_ids=focus_reviewed_product_ids,
                baseline_reviewed_product_ids=baseline_reviewed_product_ids,
                focus_tags=focus_tags,
                baseline_tags=baseline_tags,
            )
            if row and _review_theme_package_row_surfaces(row):
                rows.append(row)
    return _limit_review_theme_package_rows(rows)


def _review_theme_tag_groups(
    tags: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    by_theme: dict[str, list[Mapping[str, object]]] = {}
    by_family: dict[str, list[Mapping[str, object]]] = {}
    family_theme_ids: dict[str, set[str]] = {}
    for tag in tags:
        theme_id = str(tag["theme_id"])
        theme_family = str(tag["theme_family"])
        by_theme.setdefault(theme_id, []).append(tag)
        by_family.setdefault(theme_family, []).append(tag)
        family_theme_ids.setdefault(theme_family, set()).add(theme_id)

    groups: list[dict[str, object]] = []
    for theme_id in sorted(by_theme):
        group_tags = by_theme[theme_id]
        first_tag = group_tags[0]
        groups.append(
            {
                "theme_level": "subtheme",
                "theme_id": theme_id,
                "theme_label": str(first_tag["theme_label"]),
                "theme_family": str(first_tag["theme_family"]),
                "tags": tuple(group_tags),
            }
        )
    for theme_family in sorted(by_family):
        if len(family_theme_ids.get(theme_family, set())) <= 1:
            continue
        groups.append(
            {
                "theme_level": "parent_theme",
                "theme_id": f"parent::{_package_slug(theme_family, field_name='review_theme_family')}",
                "theme_label": theme_family,
                "theme_family": theme_family,
                "tags": tuple(by_family[theme_family]),
            }
        )
    return groups


def _coerce_review_theme_product_ids(value: object) -> set[str]:
    if not isinstance(value, (set, list, tuple)):
        return set()
    return {str(item) for item in value if _normalize_text(item) is not None}


def _review_theme_tag_row(row: Sequence[object]) -> dict[str, object]:
    (
        review_id,
        parent_product_id,
        theme_id,
        theme_label,
        theme_family,
        polarity,
        evidence_span,
        actor,
        target,
        confidence,
        brand,
        product_name,
        rating,
    ) = row
    return {
        "review_id": str(review_id),
        "parent_product_id": str(parent_product_id),
        "theme_id": str(theme_id),
        "theme_label": str(theme_label),
        "theme_family": str(theme_family),
        "polarity": str(polarity),
        "evidence_span": str(evidence_span),
        "actor": str(actor),
        "target": str(target),
        "confidence": _numeric_float(confidence),
        "brand": _normalize_text(brand),
        "product_name": _normalize_text(product_name),
        "rating": _numeric_float(rating),
    }


def _review_ids_for_products(
    review_ids_by_product: Mapping[str, set[str]],
    product_ids: set[str],
) -> set[str]:
    review_ids: set[str] = set()
    for product_id in product_ids:
        review_ids.update(review_ids_by_product.get(product_id, set()))
    return review_ids


def _build_review_theme_package_comparison_row(
    *,
    comparison_type: str,
    theme_level: str,
    theme_id: str,
    theme_label: str,
    theme_family: str,
    focus_label: str,
    baseline_label: str,
    focus_review_ids: set[str],
    baseline_review_ids: set[str],
    focus_reviewed_product_ids: set[str],
    baseline_reviewed_product_ids: set[str],
    focus_tags: Sequence[Mapping[str, object]],
    baseline_tags: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    all_tags = [*focus_tags, *baseline_tags]
    if not all_tags:
        return None
    focus_products_with_theme = {str(tag["parent_product_id"]) for tag in focus_tags}
    baseline_products_with_theme = {
        str(tag["parent_product_id"]) for tag in baseline_tags
    }
    focus_reviews_with_theme = {str(tag["review_id"]) for tag in focus_tags}
    baseline_reviews_with_theme = {str(tag["review_id"]) for tag in baseline_tags}
    focus_product_rate = _ratio(
        len(focus_products_with_theme),
        len(focus_reviewed_product_ids),
    )
    baseline_product_rate = _ratio(
        len(baseline_products_with_theme),
        len(baseline_reviewed_product_ids),
    )
    focus_review_rate = _ratio(len(focus_reviews_with_theme), len(focus_review_ids))
    baseline_review_rate = _ratio(
        len(baseline_reviews_with_theme),
        len(baseline_review_ids),
    )
    ratio = (
        focus_product_rate / baseline_product_rate
        if baseline_product_rate > 0
        else None
    )
    focus_counts = _review_theme_polarity_counts(focus_tags)
    baseline_counts = _review_theme_polarity_counts(baseline_tags)
    focus_review_polarity = _review_theme_polarity_review_counts(focus_tags)
    baseline_review_polarity = _review_theme_polarity_review_counts(baseline_tags)
    focus_product_polarity = _review_theme_polarity_product_counts(focus_tags)
    baseline_product_polarity = _review_theme_polarity_product_counts(baseline_tags)
    focus_positive_review_rate = _ratio(
        focus_review_polarity["positive"],
        len(focus_review_ids),
    )
    baseline_positive_review_rate = _ratio(
        baseline_review_polarity["positive"],
        len(baseline_review_ids),
    )
    focus_negative_review_rate = _ratio(
        focus_review_polarity["negative"],
        len(focus_review_ids),
    )
    baseline_negative_review_rate = _ratio(
        baseline_review_polarity["negative"],
        len(baseline_review_ids),
    )
    focus_mixed_review_rate = _ratio(
        focus_review_polarity["mixed"],
        len(focus_review_ids),
    )
    baseline_mixed_review_rate = _ratio(
        baseline_review_polarity["mixed"],
        len(baseline_review_ids),
    )
    focus_positive_product_rate = _ratio(
        focus_product_polarity["positive"],
        len(focus_reviewed_product_ids),
    )
    baseline_positive_product_rate = _ratio(
        baseline_product_polarity["positive"],
        len(baseline_reviewed_product_ids),
    )
    focus_negative_product_rate = _ratio(
        focus_product_polarity["negative"],
        len(focus_reviewed_product_ids),
    )
    baseline_negative_product_rate = _ratio(
        baseline_product_polarity["negative"],
        len(baseline_reviewed_product_ids),
    )
    focus_net_positive_rate = focus_positive_review_rate - focus_negative_review_rate
    baseline_net_positive_rate = (
        baseline_positive_review_rate - baseline_negative_review_rate
    )
    positive_review_rate_delta = (
        focus_positive_review_rate - baseline_positive_review_rate
    )
    negative_review_rate_delta = (
        focus_negative_review_rate - baseline_negative_review_rate
    )
    row = {
        "comparison_type": comparison_type,
        "theme_level": theme_level,
        "theme_id": theme_id,
        "theme_label": theme_label,
        "theme_family": theme_family,
        "focus_label": focus_label,
        "baseline_label": baseline_label,
        "focus_reviewed_products": len(focus_reviewed_product_ids),
        "baseline_reviewed_products": len(baseline_reviewed_product_ids),
        "focus_review_count": len(focus_review_ids),
        "baseline_review_count": len(baseline_review_ids),
        "focus_products_with_theme": len(focus_products_with_theme),
        "baseline_products_with_theme": len(baseline_products_with_theme),
        "focus_reviews_with_theme": len(focus_reviews_with_theme),
        "baseline_reviews_with_theme": len(baseline_reviews_with_theme),
        "focus_product_mention_rate": focus_product_rate,
        "baseline_product_mention_rate": baseline_product_rate,
        "product_mention_rate_delta": focus_product_rate - baseline_product_rate,
        "product_mention_rate_ratio": ratio,
        "focus_review_mention_rate": focus_review_rate,
        "baseline_review_mention_rate": baseline_review_rate,
        "review_mention_rate_delta": focus_review_rate - baseline_review_rate,
        "focus_positive_tags": focus_counts["positive"],
        "focus_negative_tags": focus_counts["negative"],
        "focus_mixed_tags": focus_counts["mixed"],
        "baseline_positive_tags": baseline_counts["positive"],
        "baseline_negative_tags": baseline_counts["negative"],
        "baseline_mixed_tags": baseline_counts["mixed"],
        "focus_positive_reviews": focus_review_polarity["positive"],
        "focus_negative_reviews": focus_review_polarity["negative"],
        "focus_mixed_reviews": focus_review_polarity["mixed"],
        "baseline_positive_reviews": baseline_review_polarity["positive"],
        "baseline_negative_reviews": baseline_review_polarity["negative"],
        "baseline_mixed_reviews": baseline_review_polarity["mixed"],
        "focus_positive_review_rate": focus_positive_review_rate,
        "baseline_positive_review_rate": baseline_positive_review_rate,
        "positive_review_rate_delta": positive_review_rate_delta,
        "positive_review_rate_ratio": _rate_ratio(
            focus_positive_review_rate,
            baseline_positive_review_rate,
        ),
        "focus_negative_review_rate": focus_negative_review_rate,
        "baseline_negative_review_rate": baseline_negative_review_rate,
        "negative_review_rate_delta": negative_review_rate_delta,
        "negative_review_rate_ratio": _rate_ratio(
            focus_negative_review_rate,
            baseline_negative_review_rate,
        ),
        "focus_mixed_review_rate": focus_mixed_review_rate,
        "baseline_mixed_review_rate": baseline_mixed_review_rate,
        "mixed_review_rate_delta": focus_mixed_review_rate - baseline_mixed_review_rate,
        "focus_net_positive_review_rate": focus_net_positive_rate,
        "baseline_net_positive_review_rate": baseline_net_positive_rate,
        "net_positive_review_rate_delta": (
            focus_net_positive_rate - baseline_net_positive_rate
        ),
        "focus_positive_products": focus_product_polarity["positive"],
        "focus_negative_products": focus_product_polarity["negative"],
        "baseline_positive_products": baseline_product_polarity["positive"],
        "baseline_negative_products": baseline_product_polarity["negative"],
        "focus_positive_product_rate": focus_positive_product_rate,
        "baseline_positive_product_rate": baseline_positive_product_rate,
        "positive_product_rate_delta": (
            focus_positive_product_rate - baseline_positive_product_rate
        ),
        "focus_negative_product_rate": focus_negative_product_rate,
        "baseline_negative_product_rate": baseline_negative_product_rate,
        "negative_product_rate_delta": (
            focus_negative_product_rate - baseline_negative_product_rate
        ),
        "focus_evidence_json": _review_theme_evidence_json(focus_tags),
        "baseline_evidence_json": _review_theme_evidence_json(baseline_tags),
        "sample_size_status": _review_theme_sample_size_status(
            focus_reviewed_products=len(focus_reviewed_product_ids),
            baseline_reviewed_products=len(baseline_reviewed_product_ids),
            focus_products_with_theme=len(focus_products_with_theme),
        ),
    }
    row.update(_review_theme_experience_signal(row))
    return row


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _rate_ratio(focus_rate: float, baseline_rate: float) -> float | None:
    if baseline_rate <= 0:
        return None
    return float(focus_rate / baseline_rate)


def _review_theme_sample_size_status(
    *,
    focus_reviewed_products: int,
    baseline_reviewed_products: int,
    focus_products_with_theme: int,
) -> str:
    if focus_reviewed_products < REVIEW_THEME_MIN_FOCUS_REVIEWED_PRODUCTS:
        return "focus_sample_too_small"
    if baseline_reviewed_products < REVIEW_THEME_MIN_BASELINE_REVIEWED_PRODUCTS:
        return "baseline_sample_too_small"
    if focus_products_with_theme < REVIEW_THEME_MIN_FOCUS_PRODUCTS_WITH_THEME:
        return "theme_focus_hits_too_small"
    return "ok"


def _review_theme_package_row_surfaces(row: Mapping[str, object]) -> bool:
    if row["sample_size_status"] != "ok":
        return False
    signal_class = str(row.get("experience_signal_class") or "no_clear_signal")
    if signal_class == "no_clear_signal":
        return False
    if signal_class == "table_stakes":
        return True
    if signal_class not in {"salience_only", "baseline_salience_only"}:
        return True
    delta = abs(float(row["product_mention_rate_delta"]))
    if delta < REVIEW_THEME_MIN_ABS_PRODUCT_RATE_DELTA:
        return False
    ratio = row["product_mention_rate_ratio"]
    if ratio is None:
        return float(row["focus_product_mention_rate"]) > 0
    ratio_value = float(ratio)
    return ratio_value >= REVIEW_THEME_MIN_RATIO or (
        ratio_value > 0 and (1 / ratio_value) >= REVIEW_THEME_MIN_RATIO
    )


def _limit_review_theme_package_rows(
    rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["comparison_type"]), []).append(row)
    limited: list[dict[str, object]] = []
    for comparison_rows in grouped.values():
        ranked = sorted(
            comparison_rows,
            key=lambda row: (
                _review_theme_signal_priority(
                    str(row.get("experience_signal_class") or "")
                ),
                float(row.get("experience_signal_score") or 0.0),
                str(row.get("theme_level") or "") == "parent_theme",
                int(row["focus_products_with_theme"]),
                int(row["focus_reviews_with_theme"]),
            ),
            reverse=True,
        )
        limited.extend(ranked[:REVIEW_THEME_MAX_SURFACED_PER_COMPARISON])
    return limited


def _review_theme_signal_priority(signal_class: str) -> int:
    return {
        "positive_over_index": 6,
        "negative_over_index": 6,
        "polarized_over_index": 5,
        "positive_under_index": 4,
        "negative_under_index": 4,
        "baseline_polarized_over_index": 4,
        "salience_only": 3,
        "baseline_salience_only": 3,
        "table_stakes": 2,
    }.get(signal_class, 0)


def _review_theme_polarity_counts(
    tags: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "mixed": 0}
    for tag in tags:
        polarity = str(tag.get("polarity") or "mixed")
        counts[polarity if polarity in counts else "mixed"] += 1
    return counts


def _review_theme_polarity_review_counts(
    tags: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    review_ids_by_polarity = _review_theme_polarity_id_sets(tags, "review_id")
    return {
        polarity: len(review_ids)
        for polarity, review_ids in review_ids_by_polarity.items()
    }


def _review_theme_polarity_product_counts(
    tags: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    product_ids_by_polarity = _review_theme_polarity_id_sets(tags, "parent_product_id")
    return {
        polarity: len(product_ids)
        for polarity, product_ids in product_ids_by_polarity.items()
    }


def _review_theme_polarity_id_sets(
    tags: Sequence[Mapping[str, object]],
    key: str,
) -> dict[str, set[str]]:
    ids_by_polarity = {"positive": set(), "negative": set(), "mixed": set()}
    for tag in tags:
        polarity = str(tag.get("polarity") or "mixed")
        normalized_polarity = polarity if polarity in ids_by_polarity else "mixed"
        item_id = _normalize_text(tag.get(key))
        if item_id:
            ids_by_polarity[normalized_polarity].add(item_id)
    return ids_by_polarity


def _review_theme_experience_signal(
    row: Mapping[str, object],
) -> dict[str, object]:
    if row["sample_size_status"] != "ok":
        return _review_theme_signal_payload(
            "no_clear_signal",
            "balanced",
            0.0,
            "Sample size is too small for a review-visible experience read.",
        )
    if _review_theme_is_table_stakes(row):
        return _review_theme_signal_payload(
            "table_stakes",
            "balanced",
            _review_theme_table_stakes_score(row),
            _review_theme_signal_summary(row, "table_stakes"),
        )

    focus_positive_higher = _review_theme_polarity_is_higher(
        row,
        polarity="positive",
        side="focus",
    )
    focus_negative_higher = _review_theme_polarity_is_higher(
        row,
        polarity="negative",
        side="focus",
    )
    baseline_positive_higher = _review_theme_polarity_is_higher(
        row,
        polarity="positive",
        side="baseline",
    )
    baseline_negative_higher = _review_theme_polarity_is_higher(
        row,
        polarity="negative",
        side="baseline",
    )
    if focus_positive_higher and focus_negative_higher:
        signal_class = "polarized_over_index"
        direction = "focus_higher"
    elif focus_positive_higher:
        signal_class = "positive_over_index"
        direction = "focus_higher"
    elif focus_negative_higher:
        signal_class = "negative_over_index"
        direction = "focus_higher"
    elif baseline_positive_higher and baseline_negative_higher:
        signal_class = "baseline_polarized_over_index"
        direction = "baseline_higher"
    elif baseline_positive_higher:
        signal_class = "positive_under_index"
        direction = "baseline_higher"
    elif baseline_negative_higher:
        signal_class = "negative_under_index"
        direction = "baseline_higher"
    elif _review_theme_mentions_are_higher(row, side="focus"):
        signal_class = "salience_only"
        direction = "focus_higher"
    elif _review_theme_mentions_are_higher(row, side="baseline"):
        signal_class = "baseline_salience_only"
        direction = "baseline_higher"
    else:
        signal_class = "no_clear_signal"
        direction = "balanced"
    score = _review_theme_signal_score(row, signal_class)
    return _review_theme_signal_payload(
        signal_class,
        direction,
        score,
        _review_theme_signal_summary(row, signal_class),
    )


def _review_theme_signal_payload(
    signal_class: str,
    direction: str,
    score: float,
    summary: str,
) -> dict[str, object]:
    return {
        "experience_signal_class": signal_class,
        "experience_signal_direction": direction,
        "experience_signal_score": float(score),
        "experience_signal_summary": summary,
    }


def _review_theme_is_table_stakes(row: Mapping[str, object]) -> bool:
    review_mentions_are_common = (
        min(
            float(row["focus_review_mention_rate"]),
            float(row["baseline_review_mention_rate"]),
        )
        >= REVIEW_THEME_TABLE_STAKES_MIN_REVIEW_MENTION_RATE
    )
    product_mentions_are_common = (
        min(
            float(row["focus_product_mention_rate"]),
            float(row["baseline_product_mention_rate"]),
        )
        >= REVIEW_THEME_TABLE_STAKES_MIN_PRODUCT_MENTION_RATE
    )
    if not review_mentions_are_common and not product_mentions_are_common:
        return False
    return (
        abs(float(row["net_positive_review_rate_delta"]))
        <= REVIEW_THEME_TABLE_STAKES_MAX_ABS_NET_DELTA
    )


def _review_theme_table_stakes_score(row: Mapping[str, object]) -> float:
    return max(
        min(
            float(row["focus_review_mention_rate"]),
            float(row["baseline_review_mention_rate"]),
        ),
        min(
            float(row["focus_product_mention_rate"]),
            float(row["baseline_product_mention_rate"]),
        ),
    )


def _review_theme_polarity_is_higher(
    row: Mapping[str, object],
    *,
    polarity: str,
    side: str,
) -> bool:
    focus_rate = float(row[f"focus_{polarity}_review_rate"])
    baseline_rate = float(row[f"baseline_{polarity}_review_rate"])
    focus_products = int(row[f"focus_{polarity}_products"])
    baseline_products = int(row[f"baseline_{polarity}_products"])
    if side == "focus":
        if focus_products < REVIEW_THEME_MIN_FOCUS_PRODUCTS_WITH_POLARITY:
            return False
        return _review_theme_rate_is_higher(focus_rate, baseline_rate)
    if baseline_products < REVIEW_THEME_MIN_BASELINE_PRODUCTS_WITH_POLARITY:
        return False
    return _review_theme_rate_is_higher(baseline_rate, focus_rate)


def _review_theme_rate_is_higher(candidate_rate: float, other_rate: float) -> bool:
    delta = candidate_rate - other_rate
    if delta < REVIEW_THEME_MIN_ABS_POLARITY_RATE_DELTA:
        return False
    if delta >= REVIEW_THEME_STRONG_ABS_POLARITY_RATE_DELTA:
        return True
    if other_rate <= 0:
        return True
    return candidate_rate / other_rate >= REVIEW_THEME_MIN_POLARITY_RATIO


def _review_theme_mentions_are_higher(
    row: Mapping[str, object],
    *,
    side: str,
) -> bool:
    product_delta = float(row["product_mention_rate_delta"])
    review_delta = float(row["review_mention_rate_delta"])
    if side == "focus":
        return (
            product_delta >= REVIEW_THEME_MIN_ABS_PRODUCT_RATE_DELTA
            or review_delta >= REVIEW_THEME_MIN_ABS_POLARITY_RATE_DELTA
        )
    return (
        product_delta <= -REVIEW_THEME_MIN_ABS_PRODUCT_RATE_DELTA
        or review_delta <= -REVIEW_THEME_MIN_ABS_POLARITY_RATE_DELTA
    )


def _review_theme_signal_score(
    row: Mapping[str, object],
    signal_class: str,
) -> float:
    if signal_class in {
        "positive_over_index",
        "positive_under_index",
        "polarized_over_index",
        "baseline_polarized_over_index",
    }:
        return abs(float(row["positive_review_rate_delta"]))
    if signal_class in {"negative_over_index", "negative_under_index"}:
        return abs(float(row["negative_review_rate_delta"]))
    if signal_class in {"salience_only", "baseline_salience_only"}:
        return max(
            abs(float(row["product_mention_rate_delta"])),
            abs(float(row["review_mention_rate_delta"])),
        )
    if signal_class == "table_stakes":
        return _review_theme_table_stakes_score(row)
    return 0.0


def _review_theme_signal_summary(
    row: Mapping[str, object],
    signal_class: str,
) -> str:
    focus = str(row["focus_label"])
    baseline = str(row["baseline_label"])
    theme = str(row["theme_label"])
    if signal_class == "table_stakes":
        return (
            f"{theme} is common in both {focus} and {baseline}, with a similar "
            "positive-minus-negative balance. Treat it as table stakes, not a "
            f"{focus} advantage."
        )
    if signal_class == "positive_over_index":
        return (
            f"{focus} show higher positive review language for {theme} than "
            f"{baseline}, without the theme being reduced to a plain mention count."
        )
    if signal_class == "negative_over_index":
        return (
            f"{focus} show higher negative review language for {theme} than "
            f"{baseline}. Treat this as a review-visible risk, not an advantage."
        )
    if signal_class == "polarized_over_index":
        return (
            f"{theme} is more polarized in {focus}: both positive and negative "
            f"review language are higher than in {baseline}."
        )
    if signal_class == "positive_under_index":
        return (
            f"{focus} under-index on positive review language for {theme} versus "
            f"{baseline}."
        )
    if signal_class == "negative_under_index":
        return (
            f"{focus} show lower negative review language for {theme} than "
            f"{baseline}; read as a lower-friction signal."
        )
    if signal_class == "baseline_polarized_over_index":
        return (
            f"{theme} is more polarized in {baseline}: both positive and negative "
            f"review language are higher than in {focus}."
        )
    if signal_class == "salience_only":
        return (
            f"{theme} is discussed more often in {focus}, but polarity does not "
            "show a clear positive or negative experience advantage."
        )
    if signal_class == "baseline_salience_only":
        return (
            f"{theme} is discussed more often in {baseline}, but polarity does not "
            f"show a clear {focus} advantage or risk."
        )
    return f"{theme} does not produce a clear review-visible experience signal."


def _review_theme_evidence_json(tags: Sequence[Mapping[str, object]]) -> str:
    examples: list[dict[str, object]] = []
    seen: set[str] = set()
    for tag in sorted(
        tags,
        key=lambda item: (
            item.get("polarity") != "negative",
            -float(item.get("confidence") or 0.0),
            str(item.get("evidence_span") or ""),
        ),
    ):
        evidence = _normalize_text(tag.get("evidence_span"))
        if not evidence:
            continue
        key = evidence.casefold()
        if key in seen:
            continue
        seen.add(key)
        examples.append(
            {
                "evidence": evidence,
                "polarity": tag.get("polarity"),
                "actor": tag.get("actor"),
                "target": tag.get("target"),
                "brand": tag.get("brand"),
                "product_name": tag.get("product_name"),
                "rating": tag.get("rating"),
            }
        )
        if len(examples) >= 5:
            break
    return json.dumps(examples, ensure_ascii=False, separators=(",", ":"))


def _review_item_identity(item: Mapping[str, Any]) -> str:
    review_id = _normalize_text(item.get("review_id"))
    if review_id:
        return f"id:{review_id}"
    parts = [
        _normalize_text(item.get("headline")) or "",
        _normalize_text(item.get("comment")) or "",
        str(_numeric_float(item.get("rating")) or ""),
        _normalize_text(item.get("created_date")) or "",
    ]
    return "text:" + "\n".join(parts).casefold()


def _dedupe_review_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        identity = _review_item_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(item)
    return deduped


def _review_items_json(items: list[dict[str, Any]]) -> str | None:
    payload: list[dict[str, Any]] = []
    for item in items[:MAX_EXPORTED_REVIEW_SNIPPETS]:
        normalized = {
            "headline": _review_excerpt(
                _normalize_text(item.get("headline")), limit=120
            ),
            "comment": _review_excerpt(_normalize_text(item.get("comment"))),
            "rating": _numeric_float(item.get("rating")),
            "created_date": _normalize_text(item.get("created_date")),
        }
        if any(value is not None for value in normalized.values()):
            payload.append(normalized)
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _flatten_review_fields(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    positive = payload.get("reviews_positive")
    if isinstance(positive, dict):
        out["reviews_positive_headline"] = _review_excerpt(
            _normalize_text(positive.get("headline")),
            limit=120,
        )
        out["reviews_positive_comment"] = _review_excerpt(
            _normalize_text(positive.get("comment")),
        )
    else:
        out["reviews_positive_headline"] = None
        out["reviews_positive_comment"] = None

    negative = payload.get("reviews_negative")
    if isinstance(negative, dict):
        out["reviews_negative_headline"] = _review_excerpt(
            _normalize_text(negative.get("headline")),
            limit=120,
        )
        out["reviews_negative_comment"] = _review_excerpt(
            _normalize_text(negative.get("comment")),
        )
    else:
        out["reviews_negative_headline"] = None
        out["reviews_negative_comment"] = None

    reviews = payload.get("reviews")
    if isinstance(reviews, list):
        review_items = [
            dict(item)
            for item in reviews
            if isinstance(item, dict)
            and (
                _normalize_text(item.get("headline"))
                or _normalize_text(item.get("comment"))
            )
        ]
    else:
        review_items = []
    review_items = _dedupe_review_items(review_items)
    exported_review_items = review_items[:MAX_EXPORTED_REVIEW_SNIPPETS]
    out["review_snippet_count"] = len(exported_review_items)
    out["reviews_json"] = _review_items_json(review_items)
    for index, item in enumerate(
        exported_review_items,
        start=1,
    ):
        out[f"review_{index}_headline"] = _review_excerpt(
            _normalize_text(item.get("headline")),
            limit=120,
        )
        out[f"review_{index}_comment"] = _review_excerpt(
            _normalize_text(item.get("comment")),
        )
        out[f"review_{index}_rating"] = _numeric_float(item.get("rating"))
        out[f"review_{index}_created_date"] = _normalize_text(item.get("created_date"))
    for index in range(
        len(exported_review_items) + 1,
        MAX_EXPORTED_REVIEW_SNIPPETS + 1,
    ):
        out[f"review_{index}_headline"] = None
        out[f"review_{index}_comment"] = None
        out[f"review_{index}_rating"] = None
        out[f"review_{index}_created_date"] = None
    return out


def _price_band(value: Any) -> str | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 10:
        return "under_10"
    if numeric < 15:
        return "10_to_14_99"
    if numeric < 25:
        return "15_to_24_99"
    if numeric < 40:
        return "25_to_39_99"
    return "40_plus"


def _series_stat(values: list[float], stat: str) -> float | None:
    if not values:
        return None
    series = pl.Series("value", values, dtype=pl.Float64)
    if stat == "mean":
        return float(series.mean())
    if stat == "median":
        return float(series.median())
    if stat == "min":
        return float(series.min())
    if stat == "max":
        return float(series.max())
    raise ValueError(f"Unsupported stat: {stat}")


def _build_price_summary(df: pl.DataFrame) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "definition": (
            "Prices are stored product snapshots derived from variant prices at the time the PDP "
            "was scraped. They are not a live-price read and not a historical time series."
        ),
        "price_band_definition": {
            "under_10": "Entry price < $10",
            "10_to_14_99": "$10 to $14.99",
            "15_to_24_99": "$15 to $24.99",
            "25_to_39_99": "$25 to $39.99",
            "40_plus": "Entry price >= $40",
        },
        "groups": {},
    }
    for status in ["recent", "rest"]:
        group_df = df.filter(pl.col("listing_status") == status)
        priced_df = group_df.filter(pl.col("entry_price").is_not_null())
        entry_prices = priced_df.get_column("entry_price").cast(pl.Float64).to_list()
        max_prices = (
            priced_df.filter(pl.col("max_price").is_not_null())
            .get_column("max_price")
            .cast(pl.Float64)
            .to_list()
        )
        payload["groups"][status] = {
            "products": int(group_df.height),
            "priced_products": int(priced_df.height),
            "priced_product_share": (
                float(priced_df.height / group_df.height)
                if group_df.height > 0
                else None
            ),
            "entry_price_mean": _series_stat(entry_prices, "mean"),
            "entry_price_median": _series_stat(entry_prices, "median"),
            "entry_price_min": _series_stat(entry_prices, "min"),
            "entry_price_max": _series_stat(entry_prices, "max"),
            "max_price_mean": _series_stat(max_prices, "mean"),
            "max_price_median": _series_stat(max_prices, "median"),
            "snapshot_min_at": _normalize_text(
                priced_df.get_column("price_snapshot_min_at").drop_nulls().min()
                if "price_snapshot_min_at" in priced_df.columns and priced_df.height > 0
                else None
            ),
            "snapshot_max_at": _normalize_text(
                priced_df.get_column("price_snapshot_max_at").drop_nulls().max()
                if "price_snapshot_max_at" in priced_df.columns and priced_df.height > 0
                else None
            ),
        }
    return payload


def _build_image_index(df: pl.DataFrame) -> pl.DataFrame:
    if df.height == 0:
        return pl.DataFrame(
            schema={
                "parent_product_id": pl.Utf8,
                "product_name": pl.Utf8,
                "image_file": pl.Utf8,
                "image_available": pl.Boolean,
                "image_source": pl.Utf8,
                "inspect_rule": pl.Utf8,
            }
        )
    return (
        df.select(
            [
                "parent_product_id",
                "product_name",
                pl.col("pack_image_file").alias("image_file"),
                pl.col("pack_image_file").is_not_null().alias("image_available"),
                pl.col("pack_image_source").alias("image_source"),
            ]
        )
        .with_columns(
            pl.lit("Open only if this product matters to your analysis.").alias(
                "inspect_rule"
            )
        )
        .sort("product_name")
    )


def _strip_provenance_columns(df: pl.DataFrame) -> pl.DataFrame:
    keep_columns = [
        column
        for column in df.columns
        if not (
            column.startswith("ulta_")
            or column.startswith("mapped_")
            or column.endswith("_mapped")
            or column.endswith("_source")
            or column.endswith("_source_column")
        )
    ]
    return df.select(keep_columns)


def _bundle_family_name(column: str) -> str:
    if column.startswith("resolved_"):
        column = column.removeprefix("resolved_")
    if column == "format":
        return "form"
    return column


def _split_bundle_values(value: Any) -> list[str]:
    parts = [
        _meaningful_text(part)
        for text in _meaningful_text_values(value)
        for part in text.split(CSV_LIST_SEPARATOR)
    ]
    seen: set[str] = set()
    values: list[str] = []
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(part)
    return values


def _bundle_items_for_row(
    row: dict[str, Any],
    *,
    attribute_columns: list[str],
) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    items: list[tuple[str, str]] = []
    for column in attribute_columns:
        if "__" in column:
            family_name, raw_value = column.split("__", 1)
            raw_flag = row.get(column)
            enabled = raw_flag is True
            if not enabled:
                normalized_flag = _normalize_text(raw_flag)
                enabled = (
                    normalized_flag is not None
                    and normalized_flag.casefold()
                    in {
                        "true",
                        "1",
                        "yes",
                    }
                )
            if enabled:
                family = _bundle_family_name(family_name).replace("_", " ")
                value = _meaningful_text(raw_value.replace("_", " "))
                if value:
                    key = (family, value.casefold())
                    if key not in seen:
                        seen.add(key)
                        items.append((family, value))
            continue
        family = _bundle_family_name(column)
        for value in _split_bundle_values(row.get(column)):
            key = (family, value.casefold())
            if key in seen:
                continue
            seen.add(key)
            items.append((family, value))
    return sorted(items, key=lambda item: (item[0], item[1].casefold()))


def _numeric_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_pareto_bucket(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    bucket = text.upper()
    return bucket if bucket in {"A", "B", "C"} else None


def _empty_bundle_signals_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "bundle_size": pl.Int64,
            "bundle_key": pl.Utf8,
            "bundle_label": pl.Utf8,
            "count_recent": pl.Int64,
            "count_rest": pl.Int64,
            "recent_brand_count": pl.Int64,
            "rest_brand_count": pl.Int64,
            "recent_base": pl.Int64,
            "rest_base": pl.Int64,
            "pct_recent": pl.Float64,
            "pct_rest": pl.Float64,
            "delta": pl.Float64,
            "prevalence_ratio": pl.Float64,
            "recent_products_with_pareto": pl.Int64,
            "recent_pareto_a_count": pl.Int64,
            "recent_pareto_b_count": pl.Int64,
            "recent_pareto_c_count": pl.Int64,
            "recent_pareto_ab_count": pl.Int64,
            "best_recent_pareto_rank": pl.Int64,
            "recent_sales_share_sum": pl.Float64,
            "recent_sales_share_mean": pl.Float64,
            "recent_brands": pl.Utf8,
            "recent_top_pareto_products": pl.Utf8,
            "recent_example_products": pl.Utf8,
        }
    )


def _build_bundle_signals(
    *,
    df: pl.DataFrame,
    attribute_columns: list[str],
    bundle_size: int,
) -> pl.DataFrame:
    if df.is_empty() or not attribute_columns:
        return _empty_bundle_signals_df()

    recent_base = int(df.filter(pl.col("listing_status") == "recent").height)
    rest_base = int(df.filter(pl.col("listing_status") == "rest").height)
    stats: dict[
        tuple[tuple[str, str], ...],
        dict[str, Any],
    ] = {}

    for row in df.to_dicts():
        listing_status = _normalize_text(row.get("listing_status")) or "rest"
        listing_identity = _normalize_text(row.get("listing_identity"))
        if not listing_identity:
            continue
        brand = _normalize_text(row.get("brand"))
        product_name = _normalize_text(row.get("product_name"))
        pareto_rank = _numeric_int(row.get("pareto_rank"))
        pareto_bucket = _normalized_pareto_bucket(row.get("pareto_bucket"))
        sales_share = _numeric_float(row.get("sales_share"))
        items = _bundle_items_for_row(row, attribute_columns=attribute_columns)
        if len(items) < bundle_size:
            continue

        seen_for_product: set[tuple[tuple[str, str], ...]] = set()
        for combo in combinations(items, bundle_size):
            families = {family for family, _value in combo}
            if len(families) != bundle_size:
                continue
            combo_key = tuple(
                sorted(combo, key=lambda item: (item[0], item[1].casefold()))
            )
            if combo_key in seen_for_product:
                continue
            seen_for_product.add(combo_key)
            slot = stats.setdefault(
                combo_key,
                {
                    "bundle_size": bundle_size,
                    "bundle_key": " + ".join(
                        f"{family}={value}" for family, value in combo_key
                    ),
                    "bundle_label": " + ".join(value for _family, value in combo_key),
                    "count_recent": 0,
                    "count_rest": 0,
                    "recent_brands": set(),
                    "rest_brands": set(),
                    "recent_pareto_ranks": [],
                    "recent_sales_shares": [],
                    "recent_pareto_buckets": {"A": 0, "B": 0, "C": 0},
                    "recent_ranked_examples": [],
                    "recent_examples": [],
                },
            )
            count_key = "count_recent" if listing_status == "recent" else "count_rest"
            slot[count_key] += 1
            if brand:
                brand_key = (
                    "recent_brands" if listing_status == "recent" else "rest_brands"
                )
                slot[brand_key].add(brand)
            if listing_status == "recent" and product_name:
                examples = slot["recent_examples"]
                if product_name not in examples and len(examples) < 5:
                    examples.append(product_name)
            if listing_status == "recent":
                if pareto_rank is not None:
                    slot["recent_pareto_ranks"].append(pareto_rank)
                    if product_name:
                        slot["recent_ranked_examples"].append(
                            (pareto_rank, product_name)
                        )
                if sales_share is not None:
                    slot["recent_sales_shares"].append(sales_share)
                if pareto_bucket is not None:
                    slot["recent_pareto_buckets"][pareto_bucket] += 1

    threshold = MIN_RECENT_COUNT_BY_BUNDLE_SIZE.get(bundle_size, 3)
    rows: list[dict[str, Any]] = []
    for payload in stats.values():
        count_recent = int(payload["count_recent"])
        count_rest = int(payload["count_rest"])
        recent_brand_count = len(payload["recent_brands"])
        rest_brand_count = len(payload["rest_brands"])
        pct_recent = count_recent / recent_base if recent_base > 0 else None
        pct_rest = count_rest / rest_base if rest_base > 0 else None
        recent_pareto_ranks = payload["recent_pareto_ranks"]
        recent_sales_shares = payload["recent_sales_shares"]
        ranked_examples = sorted(
            payload["recent_ranked_examples"], key=lambda item: (item[0], item[1])
        )
        top_ranked_labels = [
            f"{product_name} (#{pareto_rank})"
            for pareto_rank, product_name in ranked_examples[:5]
        ]
        if pct_recent is None:
            continue
        if count_recent < threshold:
            continue
        if recent_brand_count < MIN_RECENT_BRAND_COUNT:
            continue
        if pct_rest is not None and pct_recent <= pct_rest:
            continue
        prevalence_ratio = None
        if pct_rest is not None and pct_rest > 0:
            prevalence_ratio = pct_recent / pct_rest
        rows.append(
            {
                "bundle_size": int(payload["bundle_size"]),
                "bundle_key": payload["bundle_key"],
                "bundle_label": payload["bundle_label"],
                "count_recent": count_recent,
                "count_rest": count_rest,
                "recent_brand_count": recent_brand_count,
                "rest_brand_count": rest_brand_count,
                "recent_base": recent_base,
                "rest_base": rest_base,
                "pct_recent": pct_recent,
                "pct_rest": pct_rest,
                "delta": (pct_recent - pct_rest) if pct_rest is not None else None,
                "prevalence_ratio": prevalence_ratio,
                "recent_products_with_pareto": len(recent_pareto_ranks),
                "recent_pareto_a_count": int(payload["recent_pareto_buckets"]["A"]),
                "recent_pareto_b_count": int(payload["recent_pareto_buckets"]["B"]),
                "recent_pareto_c_count": int(payload["recent_pareto_buckets"]["C"]),
                "recent_pareto_ab_count": int(
                    payload["recent_pareto_buckets"]["A"]
                    + payload["recent_pareto_buckets"]["B"]
                ),
                "best_recent_pareto_rank": (
                    min(recent_pareto_ranks) if recent_pareto_ranks else None
                ),
                "recent_sales_share_sum": (
                    sum(recent_sales_shares) if recent_sales_shares else None
                ),
                "recent_sales_share_mean": _series_stat(recent_sales_shares, "mean"),
                "recent_brands": CSV_LIST_SEPARATOR.join(
                    sorted(payload["recent_brands"])
                ),
                "recent_top_pareto_products": (
                    CSV_LIST_SEPARATOR.join(top_ranked_labels)
                    if top_ranked_labels
                    else None
                ),
                "recent_example_products": CSV_LIST_SEPARATOR.join(
                    payload["recent_examples"]
                ),
            }
        )

    if not rows:
        return _empty_bundle_signals_df()
    return pl.DataFrame(rows).sort(
        ["delta", "count_recent", "recent_brand_count", "bundle_label"],
        descending=[True, True, True, False],
    )


def _parse_bundle_key(bundle_key: str | None) -> tuple[tuple[str, str], ...]:
    text = _normalize_text(bundle_key)
    if not text:
        return ()
    items: list[tuple[str, str]] = []
    for segment in text.split(" + "):
        family, separator, value = segment.partition("=")
        if separator != "=":
            continue
        normalized_family = _normalize_text(family)
        normalized_value = _normalize_text(value)
        if normalized_family and normalized_value:
            items.append((normalized_family, normalized_value))
    return tuple(sorted(items, key=lambda item: (item[0], item[1].casefold())))


RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA = {
    "rank_weighted_gross_visibility_share": pl.Float64,
    "rank_weighted_incremental_visibility_share": pl.Float64,
    "rank_weighted_visibility_density_index": pl.Float64,
    "rank_weighted_visibility_alpha_scenarios": pl.Int64,
    "rank_weighted_visibility_best_shelf_rank": pl.Int64,
    "rank_weighted_visibility_gross_sku_count": pl.Int64,
    "rank_weighted_visibility_incremental_sku_count": pl.Int64,
    "rank_weighted_visibility_gross_brand_count": pl.Int64,
    "rank_weighted_visibility_incremental_brand_count": pl.Int64,
    "rank_weighted_visibility_top_products": pl.Utf8,
    "rank_weighted_visibility_top_brands": pl.Utf8,
    "rank_weighted_visibility_incremental_available": pl.Boolean,
}


def _canonical_bundle_metric_key(bundle_key: Any) -> str | None:
    items = _parse_bundle_key(_normalize_text(bundle_key))
    if not items:
        return None
    return " + ".join(
        f"{family.replace('_', ' ').casefold()}={value.casefold()}"
        for family, value in items
    )


def _mean_metric(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _first_metric_text(rows: list[dict[str, Any]], column: str) -> str | None:
    for row in rows:
        text = _normalize_text(row.get(column))
        if text:
            return text
    return None


def _rank_weighted_visibility_lookup(
    *,
    candidate_shelves: pl.DataFrame,
    selected_shelves: pl.DataFrame,
    robustness_summary: pl.DataFrame,
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    candidate_groups: dict[str, list[dict[str, Any]]] = {}
    if candidate_shelves.width > 0 and candidate_shelves.height > 0:
        for row in candidate_shelves.to_dicts():
            key = _canonical_bundle_metric_key(row.get("bundle_key"))
            if key:
                candidate_groups.setdefault(key, []).append(row)
    for key, rows in candidate_groups.items():
        gross_values = [
            value
            for row in rows
            if (value := _numeric_float(row.get("gross_weight_share"))) is not None
        ]
        density_values = [
            value
            for row in rows
            if (value := _numeric_float(row.get("density_index"))) is not None
        ]
        lookup[key] = {
            "rank_weighted_gross_visibility_share": _mean_metric(gross_values),
            "rank_weighted_visibility_density_index": _mean_metric(density_values),
            "rank_weighted_visibility_gross_sku_count": max(
                (
                    value
                    for row in rows
                    if (value := _numeric_int(row.get("gross_sku_count"))) is not None
                ),
                default=None,
            ),
            "rank_weighted_visibility_gross_brand_count": max(
                (
                    value
                    for row in rows
                    if (value := _numeric_int(row.get("gross_brand_count"))) is not None
                ),
                default=None,
            ),
            "rank_weighted_visibility_top_products": _first_metric_text(
                rows, "top_products"
            ),
            "rank_weighted_visibility_top_brands": _first_metric_text(
                rows, "top_brands"
            ),
        }

    selected_groups: dict[str, list[dict[str, Any]]] = {}
    if selected_shelves.width > 0 and selected_shelves.height > 0:
        for row in selected_shelves.to_dicts():
            key = _canonical_bundle_metric_key(row.get("bundle_key"))
            if key and row.get("bundle_key") != "__residual__":
                selected_groups.setdefault(key, []).append(row)
    robustness_by_key = (
        {
            key: row
            for row in robustness_summary.to_dicts()
            if (key := _canonical_bundle_metric_key(row.get("bundle_key")))
        }
        if robustness_summary.width > 0 and robustness_summary.height > 0
        else {}
    )
    for key, rows in selected_groups.items():
        central_rows = [
            row
            for row in rows
            if _numeric_float(row.get("alpha")) == WEB_SHELF_CENTRAL_ALPHA
        ]
        selected_row = (central_rows or rows)[0]
        robustness_row = robustness_by_key.get(key, {})
        slot = lookup.setdefault(key, {})
        slot.update(
            {
                "rank_weighted_incremental_visibility_share": (
                    _numeric_float(
                        robustness_row.get("average_incremental_weight_share")
                    )
                    if robustness_row
                    else None
                )
                or _numeric_float(selected_row.get("incremental_weight_share")),
                "rank_weighted_visibility_alpha_scenarios": _numeric_int(
                    robustness_row.get("times_selected")
                ),
                "rank_weighted_visibility_best_shelf_rank": _numeric_int(
                    robustness_row.get("best_shelf_rank")
                )
                or _numeric_int(selected_row.get("shelf_rank")),
                "rank_weighted_visibility_incremental_sku_count": _numeric_int(
                    selected_row.get("incremental_sku_count")
                ),
                "rank_weighted_visibility_incremental_brand_count": _numeric_int(
                    selected_row.get("incremental_brand_count")
                ),
                "rank_weighted_visibility_top_products": _normalize_text(
                    selected_row.get("top_products")
                )
                or slot.get("rank_weighted_visibility_top_products"),
                "rank_weighted_visibility_top_brands": _normalize_text(
                    selected_row.get("top_brands")
                )
                or slot.get("rank_weighted_visibility_top_brands"),
            }
        )
        if robustness_row:
            slot["rank_weighted_gross_visibility_share"] = _numeric_float(
                robustness_row.get("average_gross_weight_share")
            ) or slot.get("rank_weighted_gross_visibility_share")
            slot["rank_weighted_visibility_density_index"] = _numeric_float(
                robustness_row.get("average_density_index")
            ) or slot.get("rank_weighted_visibility_density_index")

    for slot in lookup.values():
        slot["rank_weighted_visibility_incremental_available"] = (
            _numeric_float(slot.get("rank_weighted_incremental_visibility_share"))
            is not None
        )
    return lookup


def _with_rank_weighted_visibility_metrics(
    df: pl.DataFrame,
    *,
    candidate_shelves: pl.DataFrame,
    selected_shelves: pl.DataFrame,
    robustness_summary: pl.DataFrame,
) -> pl.DataFrame:
    columns, schema = get_schema_and_column_names(df)
    output_columns = [*columns, *RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA.keys()]
    if df.is_empty():
        return pl.DataFrame(schema={**schema, **RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA})

    lookup = _rank_weighted_visibility_lookup(
        candidate_shelves=candidate_shelves,
        selected_shelves=selected_shelves,
        robustness_summary=robustness_summary,
    )
    rows: list[dict[str, Any]] = []
    for row in df.to_dicts():
        key = _canonical_bundle_metric_key(row.get("bundle_key"))
        metrics = lookup.get(key or "", {})
        enriched = dict(row)
        for column in RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA:
            enriched[column] = metrics.get(column)
        if enriched["rank_weighted_visibility_incremental_available"] is None:
            enriched["rank_weighted_visibility_incremental_available"] = False
        rows.append(enriched)
    out = pl.DataFrame(
        rows,
        schema={**schema, **RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA},
        strict=False,
    )
    return out.with_columns(
        [
            pl.col(column).cast(dtype, strict=False)
            for column, dtype in RANK_WEIGHTED_VISIBILITY_METRIC_SCHEMA.items()
        ]
    ).select(output_columns)


def _rank_weighted_visibility_metric_count(df: pl.DataFrame) -> int:
    if "rank_weighted_gross_visibility_share" not in df.columns:
        return 0
    return int(
        df.filter(pl.col("rank_weighted_gross_visibility_share").is_not_null()).height
    )


def _signal_components_from_bundle_key(
    bundle_key: Any,
) -> tuple[tuple[str, str], ...]:
    return parse_signal_bundle_key(bundle_key)


def _bundle_signal_base_score(row: Mapping[str, Any], signal_layer: str) -> float:
    if signal_layer == "winning_now":
        return (
            (_numeric_float(row.get("top_seller_sales_share_sum")) or 0.0) * 100.0
            + (_numeric_float(row.get("delta")) or 0.0) * 100.0
            + (_numeric_float(row.get("pct_top_seller")) or 0.0) * 10.0
            + (_numeric_int(row.get("count_top_seller")) or 0) / 10.0
        )
    if signal_layer == "sale_pressure":
        return (
            (_numeric_float(row.get("sale_pressure_sales_share_sum")) or 0.0) * 100.0
            + (_numeric_float(row.get("delta")) or 0.0) * 100.0
            + (_numeric_float(row.get("pct_sale_pressure")) or 0.0) * 10.0
            + (_numeric_int(row.get("count_sale_pressure")) or 0) / 10.0
        )
    return (
        (_numeric_float(row.get("recent_sales_share_sum")) or 0.0) * 100.0
        + (_numeric_float(row.get("delta")) or 0.0) * 100.0
        + (_numeric_float(row.get("pct_recent")) or 0.0) * 10.0
        + (_numeric_float(row.get("prevalence_ratio")) or 0.0)
        + (_numeric_int(row.get("count_recent")) or 0) / 10.0
    )


def _category_center_component_keys(
    category_center_components: pl.DataFrame,
) -> set[tuple[str, str]]:
    if (
        category_center_components.is_empty()
        or "attribute_family" not in category_center_components.columns
        or "attribute_value" not in category_center_components.columns
    ):
        return set()
    return {
        (signal_component_family(row.get("attribute_family")), normalized_value)
        for row in category_center_components.to_dicts()
        if (normalized_value := normalize_signal_text(row.get("attribute_value")))
    }


def _observed_signal_insight_metadata(
    *,
    category_center_keys: set[tuple[str, str]],
    components: Sequence[tuple[str, str]],
    base_score: float,
    signal_layers: Sequence[str],
) -> dict[str, Any]:
    normalized_components = tuple(
        (signal_component_family(attribute), normalize_signal_text(value))
        for attribute, value in components
        if signal_component_family(attribute) and normalize_signal_text(value)
    )
    category_center_count = sum(
        1 for component in normalized_components if component in category_center_keys
    )
    differentiating_count = max(0, len(normalized_components) - category_center_count)
    normalized_layers = [
        normalize_signal_text(layer).replace(" ", "_") for layer in signal_layers
    ]
    layer_bonus_by_layer = {"innovation": 8.0, "winning_now": 4.0}
    layer_bonus = sum(
        layer_bonus_by_layer.get(layer, 0.0) for layer in normalized_layers
    )

    if normalized_components and differentiating_count == 0:
        note = (
            "Observed broad-baseline bundle. Use as market-center context, "
            "not as a headline differentiating signal."
        )
        return {
            "signal_usefulness": "category_center",
            "signal_role": "category_center",
            "differentiating_component_count": differentiating_count,
            "category_center_component_count": category_center_count,
            "insight_adjusted_signal_score": round(base_score * 0.05, 6),
            "signal_quality_note": note,
            "signal_role_note": note,
        }

    if differentiating_count >= 2:
        signal_usefulness = "headline_signal"
        signal_role = "differentiating"
    elif differentiating_count == 1:
        signal_usefulness = "supporting_signal"
        signal_role = "supporting_differentiation"
    else:
        signal_usefulness = "selected_signal"
        signal_role = "unclassified_signal"

    note = (
        "Contains observed differentiating component(s) beyond broad baseline attributes."
        if differentiating_count > 0
        else None
    )
    adjusted_score = (
        base_score
        + layer_bonus
        + (2.0 * differentiating_count)
        - (12.0 * category_center_count)
    )
    return {
        "signal_usefulness": signal_usefulness,
        "signal_role": signal_role,
        "differentiating_component_count": differentiating_count,
        "category_center_component_count": category_center_count,
        "insight_adjusted_signal_score": round(adjusted_score, 6),
        "signal_quality_note": note,
        "signal_role_note": note,
    }


def _sort_signal_insight_rows(
    df: pl.DataFrame,
    *,
    signal_layer: str,
) -> pl.DataFrame:
    if df.is_empty() or "insight_adjusted_signal_score" not in df.columns:
        return df
    columns = set(df.columns)
    sort_columns = ["insight_adjusted_signal_score"]
    descending = [True]
    for column in [
        "rank_weighted_incremental_visibility_share",
        "rank_weighted_gross_visibility_share",
        "delta",
        {
            "winning_now": "count_top_seller",
            "innovation": "count_recent",
            "sale_pressure": "count_sale_pressure",
        }.get(signal_layer, "count_recent"),
        "bundle_label",
    ]:
        if column in columns and column not in sort_columns:
            sort_columns.append(column)
            descending.append(column != "bundle_label")
    return df.sort(sort_columns, descending=descending, nulls_last=True)


def _with_signal_insight_metadata(
    df: pl.DataFrame,
    *,
    signal_layer: str,
    category_center_components: pl.DataFrame,
) -> pl.DataFrame:
    columns, schema = get_schema_and_column_names(df)
    output_columns = [*columns, *SIGNAL_INSIGHT_METADATA_SCHEMA.keys()]
    if df.is_empty():
        return pl.DataFrame(schema={**schema, **SIGNAL_INSIGHT_METADATA_SCHEMA}).select(
            output_columns
        )

    category_center_keys = _category_center_component_keys(category_center_components)
    rows: list[dict[str, Any]] = []
    for row in df.to_dicts():
        components = _signal_components_from_bundle_key(row.get("bundle_key"))
        base_score = _bundle_signal_base_score(row, signal_layer)
        metadata = _observed_signal_insight_metadata(
            category_center_keys=category_center_keys,
            components=components,
            base_score=base_score,
            signal_layers=(signal_layer,),
        )
        enriched = dict(row)
        enriched.update(metadata)
        rows.append(enriched)

    out = pl.DataFrame(
        rows,
        schema={**schema, **SIGNAL_INSIGHT_METADATA_SCHEMA},
        strict=False,
    ).with_columns(
        [
            pl.col(column).cast(dtype, strict=False)
            for column, dtype in SIGNAL_INSIGHT_METADATA_SCHEMA.items()
        ]
    )
    return _sort_signal_insight_rows(
        out.select(output_columns),
        signal_layer=signal_layer,
    )


def _split_signal_rows_by_usefulness(
    df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    if df.is_empty():
        return df, pl.DataFrame(schema={})
    if "signal_role" in df.columns:
        selected = df.filter(pl.col("signal_role") != "category_center")
        context = df.filter(pl.col("signal_role") == "category_center")
    else:
        return df, pl.DataFrame(schema={})
    return selected, context


def _combined_signal_table(
    sources: Sequence[tuple[str, pl.DataFrame]],
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for source_file, df in sources:
        if df.is_empty():
            continue
        frames.append(df.with_columns(pl.lit(source_file).alias("source_file")))
    if not frames:
        return pl.DataFrame(schema={"source_file": pl.Utf8})
    out = pl.concat(frames, how="diagonal_relaxed")
    sort_columns = [
        column
        for column in ["source_file", "insight_adjusted_signal_score", "bundle_label"]
        if column in out.columns
    ]
    descending = [False, True, False][: len(sort_columns)]
    return out.sort(sort_columns, descending=descending, nulls_last=True)


def _pro_visible_signal_table(df: pl.DataFrame) -> pl.DataFrame:
    """Drop internal guardrail fields before writing Pro-facing signal files."""

    if df.is_empty():
        return df
    hidden_columns = [
        column for column in PRO_HIDDEN_SIGNAL_COLUMNS if column in df.columns
    ]
    if not hidden_columns:
        return df
    return df.drop(hidden_columns)


def _differentiating_signal_table(
    sources: Sequence[tuple[str, pl.DataFrame]],
) -> pl.DataFrame:
    return _combined_signal_table(sources)


def _rank_weight_for_rank(rank: Any, *, alpha: float) -> float | None:
    numeric_rank = _numeric_int(rank)
    if numeric_rank is None or numeric_rank <= 0:
        return None
    return 1.0 / (float(numeric_rank) ** alpha)


def _category_center_component_table(
    df: pl.DataFrame,
    *,
    attribute_columns: list[str],
) -> pl.DataFrame:
    center_config = _observed_category_center_config()
    rank_weight_alpha = float(center_config["rank_weight_alpha"])
    if rank_weight_alpha <= 0:
        rank_weight_alpha = 1.0
    min_ranked_products = int(center_config["min_ranked_products"])
    min_assortment_products = int(center_config["min_assortment_products"])
    min_rank_weighted_presence = float(center_config["min_rank_weighted_presence"])
    min_assortment_presence = float(center_config["min_assortment_presence"])
    max_rank_weighted_lift = float(center_config["max_rank_weighted_lift"])
    schema = {
        "attribute_family": pl.Utf8,
        "attribute_value": pl.Utf8,
        "ranked_product_count": pl.Int64,
        "ranked_product_base": pl.Int64,
        "assortment_product_count": pl.Int64,
        "assortment_product_base": pl.Int64,
        "signal_role": pl.Utf8,
        "interpretation_note": pl.Utf8,
    }
    if df.is_empty() or not attribute_columns or "listing_identity" not in df.columns:
        return pl.DataFrame(schema=schema)

    note = (
        "Rank-weighted broad-baseline candidate. Use as context inside bundles, "
        "not as a standalone differentiating recommendation."
    )

    family_stats: dict[str, dict[str, Any]] = {}
    component_stats: dict[tuple[str, str], dict[str, Any]] = {}

    for row in df.to_dicts():
        listing_identity = _normalize_text(row.get("listing_identity"))
        if not listing_identity:
            continue
        rank_weight = _rank_weight_for_rank(
            row.get("pareto_rank"),
            alpha=rank_weight_alpha,
        )
        items_by_family: dict[str, dict[str, str]] = {}
        for family_raw, value_raw in _bundle_items_for_row(
            row,
            attribute_columns=attribute_columns,
        ):
            family = signal_component_family(family_raw)
            value_key = normalize_signal_text(value_raw)
            value_label = _meaningful_text(value_raw)
            if not family or not value_key or not value_label:
                continue
            items_by_family.setdefault(family, {})[value_key] = value_label

        for family, value_map in items_by_family.items():
            family_slot = family_stats.setdefault(
                family,
                {
                    "assortment_ids": set(),
                    "ranked_ids": set(),
                    "rank_weight_base": 0.0,
                },
            )
            if listing_identity not in family_slot["assortment_ids"]:
                family_slot["assortment_ids"].add(listing_identity)
            if (
                rank_weight is not None
                and listing_identity not in family_slot["ranked_ids"]
            ):
                family_slot["ranked_ids"].add(listing_identity)
                family_slot["rank_weight_base"] += rank_weight

            for value_key, value_label in value_map.items():
                component_key = (family, value_key)
                component_slot = component_stats.setdefault(
                    component_key,
                    {
                        "attribute_family": family,
                        "attribute_value": value_label,
                        "assortment_ids": set(),
                        "ranked_ids": set(),
                        "rank_weight_sum": 0.0,
                    },
                )
                if listing_identity not in component_slot["assortment_ids"]:
                    component_slot["assortment_ids"].add(listing_identity)
                if (
                    rank_weight is not None
                    and listing_identity not in component_slot["ranked_ids"]
                ):
                    component_slot["ranked_ids"].add(listing_identity)
                    component_slot["rank_weight_sum"] += rank_weight

    rows: list[dict[str, Any]] = []
    for (family, _value_key), component_slot in component_stats.items():
        family_slot = family_stats.get(family, {})
        ranked_product_base = len(family_slot.get("ranked_ids", set()))
        assortment_product_base = len(family_slot.get("assortment_ids", set()))
        rank_weight_base = float(family_slot.get("rank_weight_base") or 0.0)
        ranked_product_count = len(component_slot["ranked_ids"])
        assortment_product_count = len(component_slot["assortment_ids"])
        rank_weight_sum = float(component_slot["rank_weight_sum"])
        if (
            ranked_product_base <= 0
            or assortment_product_base <= 0
            or rank_weight_base <= 0
        ):
            continue
        rank_weighted_presence = rank_weight_sum / rank_weight_base
        assortment_presence = assortment_product_count / assortment_product_base
        rank_weighted_lift = (
            rank_weighted_presence / assortment_presence
            if assortment_presence > 0
            else None
        )
        if rank_weighted_lift is None:
            continue
        if ranked_product_count < min_ranked_products:
            continue
        if assortment_product_count < min_assortment_products:
            continue
        if rank_weighted_presence < min_rank_weighted_presence:
            continue
        if assortment_presence < min_assortment_presence:
            continue
        if rank_weighted_lift > max_rank_weighted_lift:
            continue
        rows.append(
            {
                "attribute_family": component_slot["attribute_family"],
                "attribute_value": component_slot["attribute_value"],
                "ranked_product_count": ranked_product_count,
                "ranked_product_base": ranked_product_base,
                "assortment_product_count": assortment_product_count,
                "assortment_product_base": assortment_product_base,
                "signal_role": "category_center",
                "interpretation_note": note,
                "_rank_weighted_presence": rank_weighted_presence,
                "_assortment_presence": assortment_presence,
            }
        )

    if not rows:
        return pl.DataFrame(schema=schema)
    rows.sort(
        key=lambda row: (
            -float(row["_rank_weighted_presence"]),
            -float(row["_assortment_presence"]),
            -int(row["ranked_product_count"]),
            str(row["attribute_family"]),
            str(row["attribute_value"]),
        )
    )
    return pl.DataFrame(
        [
            {key: value for key, value in row.items() if not str(key).startswith("_")}
            for row in rows
        ],
        schema=schema,
    )


def _build_bundle_review_validation(
    *,
    recent_products: pl.DataFrame,
    innovation_pairs: pl.DataFrame,
    innovation_triples: pl.DataFrame,
    attribute_columns: list[str],
    max_pairs: int | None = None,
    max_triples: int | None = None,
    max_products_per_bundle: int = 5,
) -> pl.DataFrame:
    schema = _review_validation_schema()
    if recent_products.is_empty():
        return pl.DataFrame(schema=schema)

    selected_pairs = (
        innovation_pairs.head(max_pairs) if max_pairs is not None else innovation_pairs
    )
    selected_triples = (
        innovation_triples.head(max_triples)
        if max_triples is not None
        else innovation_triples
    )
    bundle_signal_rows = selected_pairs.to_dicts() + selected_triples.to_dicts()
    if not bundle_signal_rows:
        return pl.DataFrame(schema=schema)

    recent_rows: list[dict[str, Any]] = []
    for row in recent_products.to_dicts():
        review_count = _numeric_int(row.get("review_count")) or 0
        has_review_content = any(
            _normalize_text(row.get(column))
            for column in [
                "reviews_positive_comment",
                "reviews_negative_comment",
                *[
                    f"review_{index}_comment"
                    for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1)
                ],
            ]
        )
        if review_count <= 0 and not has_review_content:
            continue
        row_items = set(_bundle_items_for_row(row, attribute_columns=attribute_columns))
        if not row_items:
            continue
        row["_bundle_items"] = row_items
        recent_rows.append(row)
    if not recent_rows:
        return pl.DataFrame(schema=schema)

    review_rows: list[dict[str, Any]] = []
    for signal in bundle_signal_rows:
        bundle_key = _normalize_text(signal.get("bundle_key"))
        bundle_items = set(_parse_bundle_key(bundle_key))
        if not bundle_items:
            continue
        matched_products = [
            row for row in recent_rows if bundle_items.issubset(row["_bundle_items"])
        ]
        if not matched_products:
            continue
        matched_products.sort(
            key=lambda row: (
                _numeric_int(row.get("pareto_rank")) is None,
                _numeric_int(row.get("pareto_rank")) or 10**9,
                -(_numeric_int(row.get("review_count")) or 0),
                (_normalize_text(row.get("product_name")) or "").casefold(),
            )
        )
        for row in matched_products[:max_products_per_bundle]:
            review_rows.append(
                {
                    "bundle_size": int(signal.get("bundle_size") or 0),
                    "bundle_key": bundle_key,
                    "bundle_label": _normalize_text(signal.get("bundle_label")),
                    "product_name": _normalize_text(row.get("product_name")),
                    "brand": _normalize_text(row.get("brand")),
                    "parent_product_id": _normalize_text(row.get("parent_product_id")),
                    "pareto_rank": _numeric_int(row.get("pareto_rank")),
                    "pareto_bucket": _normalized_pareto_bucket(
                        row.get("pareto_bucket")
                    ),
                    "sales_share": _numeric_float(row.get("sales_share")),
                    "rating": _numeric_float(row.get("rating")),
                    "review_count": _numeric_int(row.get("review_count")),
                    "review_snippet_count": _numeric_int(
                        row.get("review_snippet_count")
                    ),
                    "reviews_json": _normalize_text(row.get("reviews_json")),
                    "reviews_positive_headline": _normalize_text(
                        row.get("reviews_positive_headline")
                    ),
                    "reviews_positive_comment": _normalize_text(
                        row.get("reviews_positive_comment")
                    ),
                    "reviews_negative_headline": _normalize_text(
                        row.get("reviews_negative_headline")
                    ),
                    "reviews_negative_comment": _normalize_text(
                        row.get("reviews_negative_comment")
                    ),
                    **{
                        f"review_{index}_{field}": (
                            _numeric_float(row.get(f"review_{index}_{field}"))
                            if field == "rating"
                            else _normalize_text(row.get(f"review_{index}_{field}"))
                        )
                        for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1)
                        for field in REVIEW_SNIPPET_FIELDS
                    },
                }
            )
    if not review_rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(review_rows).sort(
        ["bundle_size", "bundle_key", "pareto_rank", "review_count", "product_name"],
        descending=[False, False, False, True, False],
        nulls_last=True,
    )


def _write_pack_zip(output_dir: Path) -> Path:
    zip_path = _package_zip_path(output_dir)
    legacy_zip_path = output_dir.with_suffix(".zip")
    if legacy_zip_path != zip_path and legacy_zip_path.exists():
        legacy_zip_path.unlink()
    include_files = [
        "summary.json",
        "package_integrity.json",
        "package_warnings.json",
        "pack_manifest.json",
        "filter_comparison.csv",
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "differentiating_signals.csv",
        "top_seller_brand_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
        "top_seller_review_validation.csv",
        "top_seller_products.csv",
        "sale_pressure_pairs.csv",
        "sale_pressure_triples.csv",
        "sale_pressure_attribute_comparison.csv",
        "sale_pressure_products.csv",
        "sale_pressure_overlap.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
        "sort_rank_delta_products.csv",
        "sort_rank_delta_attributes.csv",
        "resolved_core_comparison.csv",
        "mapped_attribute_comparison.csv",
        "price_comparison.json",
        "price_band_comparison.csv",
        "bundle_review_validation.csv",
        "web_shelf_selected_shelves.csv",
        "web_shelf_candidate_shelves.csv",
        "web_shelf_robustness_summary.csv",
        "web_shelf_product_assignments.csv",
        "web_shelf_third_attribute_refinements.csv",
        f"{ATTRIBUTE_TABLE_DIRNAME}/manifest.json",
        *[
            f"{ATTRIBUTE_TABLE_DIRNAME}/{file_name}"
            for file_name in ATTRIBUTE_TABLE_TEMPLATE_FILES.values()
        ],
        *[
            f"{ATTRIBUTE_TABLE_DIRNAME}/{Path(file_name).stem}.html"
            for file_name in ATTRIBUTE_TABLE_TEMPLATE_FILES.values()
        ],
        "product_filter_matrix.csv",
        "recent_products.csv",
        "recent_product_pdp_extracts.csv",
        "image_index.csv",
        f"{SOURCE_SNAPSHOT_DIRNAME}/source_manifest.json",
        f"{SOURCE_SNAPSHOT_DIRNAME}/listing_observations.csv",
        f"{SOURCE_SNAPSHOT_DIRNAME}/filter_observations.csv",
        f"{SOURCE_SNAPSHOT_DIRNAME}/mapped_product_attributes.csv",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in include_files:
            candidate = output_dir / name
            if candidate.exists():
                zf.write(candidate, arcname=str(Path(output_dir.name) / name))
        images_dir = output_dir / "images"
        if images_dir.exists():
            for image_path in sorted(images_dir.rglob("*")):
                if image_path.is_file():
                    zf.write(
                        image_path,
                        arcname=str(
                            Path(output_dir.name) / image_path.relative_to(output_dir)
                        ),
                    )
    return zip_path


def _recent_status_by_listing(
    category_listing_raw: pl.DataFrame,
    *,
    recent_share: float,
    recent_sort_mode: str | None,
) -> pl.DataFrame:
    if "listing_identity" not in category_listing_raw.columns:
        category_listing_raw = category_listing_raw.with_columns(
            pl.when(
                pl.col("parent_product_id").is_not_null()
                & (pl.col("parent_product_id") != "")
            )
            .then(pl.col("parent_product_id"))
            .otherwise(pl.col("pdp_url"))
            .alias("listing_identity")
        )
    base_listing = (
        category_listing_raw.group_by("listing_identity")
        .agg(
            [
                pl.col("category_key").first().alias("category_key"),
                pl.col("parent_product_id")
                .drop_nulls()
                .first()
                .alias("parent_product_id"),
                pl.col("product_name").drop_nulls().first().alias("product_name"),
                pl.col("pdp_url").drop_nulls().first().alias("pdp_url"),
                pl.col("has_new_badge").any().alias("has_new_badge"),
            ]
        )
        .sort("product_name")
    )
    if base_listing.height == 0:
        return base_listing.with_columns(pl.lit("rest").alias("listing_status"))

    ranked_source = category_listing_raw
    if recent_sort_mode:
        ranked_source = category_listing_raw.filter(
            pl.col("sort_mode") == recent_sort_mode
        )
    ranked = (
        ranked_source.sort(["page", "position"])
        .group_by("listing_identity", maintain_order=True)
        .agg(
            [
                pl.col("page").first().alias("rank_page"),
                pl.col("position").first().alias("rank_position"),
            ]
        )
    )
    cutoff = min(
        int(base_listing.height),
        max(1, math.ceil(int(base_listing.height) * recent_share)),
    )
    recent_ids = set(
        ranked.head(cutoff).get_column("listing_identity").to_list()
        if ranked.height > 0
        else []
    )
    return base_listing.with_columns(
        pl.col("listing_identity")
        .map_elements(lambda value: "recent" if value in recent_ids else "rest")
        .alias("listing_status")
    )


def _build_pack_impl(
    *,
    retailer: str,
    category_key: str,
    run_dir: Path | None,
    pdp_store_path: Path,
    cli_root: Path,
    output_root: Path,
    max_pack_images: int | None = PACK_IMAGE_HARD_LIMIT,
    attribute_frames: _MappedAttributeFrames | None = None,
) -> Path:
    max_pack_images = _bounded_pack_image_limit(max_pack_images)
    _clear_existing_package_output_dir(
        output_root,
        retailer=retailer,
        category_key=category_key,
    )
    listing_df, filter_df, discovery_crawl_ts = _load_discovery_observations_from_store(
        pdp_store_path,
        retailer=retailer,
        category_key=category_key,
    )
    if not discovery_crawl_ts or listing_df.is_empty():
        raise RuntimeError(
            "No listing discovery observations found in the PDP store for "
            f"{retailer} / {category_key}. Rerun discovery before building the package."
        )
    materialized_filter_attribute_rows = (
        PDPStore(pdp_store_path).materialize_retailer_filter_attributes(
            retailer=retailer,
            category_key=category_key,
            crawl_ts=discovery_crawl_ts,
        )
        if discovery_crawl_ts
        else 0
    )
    recent_share = _run_recent_share(run_dir) if run_dir is not None else 0.20
    attribute_input_source = "pdp_store:pdp_attribute_values"
    mapped_export_df, mapped_attribute_columns, variant_df = (
        _prepare_mapped_attributes_from_store(
            pdp_store_path=pdp_store_path,
            retailer=retailer,
            category_key=category_key,
            attribute_frames=attribute_frames,
        )
    )
    mapped_export_df = _normalize_parent_product_ids(
        mapped_export_df, retailer=retailer
    )

    listing_df = _normalize_parent_product_ids(listing_df, retailer=retailer)
    filter_df = _normalize_parent_product_ids(filter_df, retailer=retailer)
    category_listing_raw = listing_df.filter(pl.col("category_key") == category_key)
    recent_sort_mode = _select_recent_sort_mode(
        category_listing_raw,
        retailer=retailer,
    )
    top_seller_sort_mode = _preferred_popularity_mode(
        retailer=retailer,
        available_modes=_available_ranked_sort_modes(category_listing_raw),
    )
    sale_pressure_sort_mode = _select_sale_pressure_sort_mode(category_listing_raw)
    sort_overlap_quality = _validate_distinct_ranked_sort_sequences(
        category_listing_raw,
        retailer=retailer,
        category_key=category_key,
        recent_sort_mode=recent_sort_mode,
        top_seller_sort_mode=top_seller_sort_mode,
    )
    category_filters = _with_listing_identity(
        filter_df.filter(pl.col("category_key") == category_key)
    )
    product_universe = _build_product_universe(
        category_listing_raw=category_listing_raw,
        category_filters=category_filters,
        mapped_export_df=mapped_export_df,
    )
    source_parent_ids = {
        parent_id
        for value in product_universe.get_column("parent_product_id").to_list()
        if (parent_id := _normalize_text(value))
    }
    source_mapped_attributes = _filter_mapped_source_to_parents(
        mapped_export_df,
        source_parent_ids,
    )
    category_listing = _apply_recent_status(
        product_universe,
        category_listing_raw,
        recent_share=recent_share,
        recent_sort_mode=recent_sort_mode,
    )
    top_seller_captured_ranked_products = len(
        _ranked_sequence_for_sort(
            category_listing_raw,
            sort_mode=top_seller_sort_mode,
        )
    )
    top_seller_universe_cutoff = _universe_top_seller_cutoff(
        int(category_listing.height)
    )
    top_seller_observed_cohort_limit = _observed_top_seller_cutoff(
        captured_ranked_count=top_seller_captured_ranked_products,
        universe_count=int(category_listing.height),
    )
    filter_presence = (
        category_filters.group_by("listing_identity").agg(
            [
                pl.len().alias("filter_membership_count"),
                pl.col("filter_family").n_unique().alias("filter_family_count"),
            ]
        )
        if category_filters.height > 0
        else pl.DataFrame(
            {
                "listing_identity": [],
                "filter_membership_count": [],
                "filter_family_count": [],
            },
            schema={
                "listing_identity": pl.Utf8,
                "filter_membership_count": pl.Int64,
                "filter_family_count": pl.Int64,
            },
        )
    )

    status_df = category_listing.select(["listing_identity", "listing_status"]).unique()
    family_denominators = _build_family_denominators(category_filters, status_df)

    comparison = (
        category_filters.select(["listing_identity", "filter_family", "filter_value"])
        .unique()
        .join(status_df, on="listing_identity", how="inner")
        .group_by(["filter_family", "filter_value", "listing_status"])
        .agg(pl.len().alias("product_count"))
        .pivot(
            values="product_count",
            index=["filter_family", "filter_value"],
            on="listing_status",
            aggregate_function="first",
        )
        .rename({"recent": "count_recent", "rest": "count_rest"})
        .with_columns(
            pl.col("count_recent").fill_null(0).cast(pl.Int64),
            pl.col("count_rest").fill_null(0).cast(pl.Int64),
        )
        .join(
            family_denominators.filter(pl.col("listing_status") == "recent").select(
                [
                    "filter_family",
                    pl.col("family_product_count").alias("recent_family_base"),
                ]
            ),
            on="filter_family",
            how="left",
        )
        .join(
            family_denominators.filter(pl.col("listing_status") == "rest").select(
                [
                    "filter_family",
                    pl.col("family_product_count").alias("rest_family_base"),
                ]
            ),
            on="filter_family",
            how="left",
        )
        .with_columns(
            pl.when(pl.col("recent_family_base") > 0)
            .then(pl.col("count_recent") / pl.col("recent_family_base"))
            .otherwise(None)
            .alias("pct_recent"),
            pl.when(pl.col("rest_family_base") > 0)
            .then(pl.col("count_rest") / pl.col("rest_family_base"))
            .otherwise(None)
            .alias("pct_rest"),
        )
        .with_columns((pl.col("pct_recent") - pl.col("pct_rest")).alias("delta"))
        .sort(
            ["filter_family", "delta", "count_recent"], descending=[False, True, True]
        )
        if category_filters.height > 0
        else pl.DataFrame(
            schema={
                "filter_family": pl.Utf8,
                "filter_value": pl.Utf8,
                "count_recent": pl.Int64,
                "count_rest": pl.Int64,
                "recent_family_base": pl.Int64,
                "rest_family_base": pl.Int64,
                "pct_recent": pl.Float64,
                "pct_rest": pl.Float64,
                "delta": pl.Float64,
            }
        )
    )

    product_filter_lists = category_filters.group_by(
        ["listing_identity", "filter_family"]
    ).agg(
        pl.col("filter_value")
        .sort()
        .unique()
        .str.join(CSV_LIST_SEPARATOR)
        .alias("filter_values")
    )

    pivot_values = (
        product_filter_lists.pivot(
            values="filter_values",
            index="listing_identity",
            on="filter_family",
            aggregate_function="first",
        )
        if product_filter_lists.height > 0
        else pl.DataFrame(
            {"listing_identity": []}, schema={"listing_identity": pl.Utf8}
        )
    )

    all_products = (
        category_listing.join(pivot_values, on="listing_identity", how="left")
        .join(filter_presence, on="listing_identity", how="left")
        .with_columns(
            pl.col("filter_membership_count").fill_null(0).cast(pl.Int64),
            pl.col("filter_family_count").fill_null(0).cast(pl.Int64),
            (pl.col("filter_membership_count").fill_null(0) > 0).alias(
                "has_filter_observations"
            ),
        )
    )
    if mapped_export_df.height > 0:
        all_products = all_products.join(
            mapped_export_df,
            on="parent_product_id",
            how="left",
            suffix="_mapped",
        )
    all_products = _apply_common_traction_layer(
        all_products,
        category_listing_raw=category_listing_raw,
        retailer=retailer,
        rank_universe_count=int(category_listing.height),
    )
    all_products = _apply_sale_pressure_layer(
        all_products,
        category_listing_raw=category_listing_raw,
        sale_pressure_sort_mode=sale_pressure_sort_mode,
    )
    all_products = all_products.with_columns(
        pl.col("pareto_bucket")
        .map_elements(_top_seller_status, return_dtype=pl.Utf8)
        .alias("top_seller_status")
    )

    parent_ids = [
        value
        for value in all_products.get_column("parent_product_id").to_list()
        if _normalize_text(value)
    ]
    variant_color_rollups = _prepare_variant_color_rollups_from_frame(
        variant_df,
        retailer=retailer,
        category_key=category_key,
        parent_ids=set(parent_ids),
    )
    if variant_color_rollups.height > 0:
        all_products = all_products.join(
            variant_color_rollups,
            on="parent_product_id",
            how="left",
        )
    all_products = _apply_available_color_fallbacks(all_products)

    parent_details = _parent_detail_rows(pdp_store_path, retailer, parent_ids)
    parent_prices = _parent_price_rows(pdp_store_path, retailer, parent_ids)
    image_rows = _image_rows(cli_root, retailer, category_key, variant_df)
    package_category_key = _canonical_package_category_key(category_key)
    output_dir = _prepare_package_output_dir(
        output_root,
        retailer=retailer,
        category_key=category_key,
    )
    source_snapshot_manifest = _write_source_snapshots(
        output_dir,
        listing_observations=category_listing_raw,
        filter_observations=category_filters,
        mapped_product_attributes=source_mapped_attributes,
        retailer=retailer,
        category_key=category_key,
        discovery_crawl_ts=discovery_crawl_ts,
        recent_share=recent_share,
        recent_sort_mode=recent_sort_mode,
        top_seller_sort_mode=top_seller_sort_mode,
        sale_pressure_sort_mode=sale_pressure_sort_mode,
    )
    retailer_label = _to_retailer_label(retailer)
    source_category_label = _resolve_category_label(
        category_key=category_key, mapped_export_df=mapped_export_df
    )
    category_label = _canonical_package_category_label(category_key)

    enriched_rows: list[dict[str, Any]] = []
    copied_pack_images = 0
    for row in all_products.to_dicts():
        out = _merge_filter_primary_attributes(
            row,
            retailer=retailer,
            category_key=category_key,
            mapped_attribute_columns=mapped_attribute_columns,
        )
        out = _merge_metadata_fallbacks(out)
        parent_id = _normalize_text(out.get("parent_product_id"))
        details = parent_details.get(parent_id or "", {})
        price_details = parent_prices.get(parent_id or "", {})
        image_meta = image_rows.get(parent_id or "", {})
        hero_image_url = image_meta.get("hero_image_url") or details.get(
            "hero_image_url"
        )
        swatch_image_url = image_meta.get("swatch_image_url")
        pack_image_meta, copied_pack_images = _materialize_limited_pack_image(
            output_dir=output_dir,
            parent_id=parent_id,
            local_image_path=image_meta.get("local_image_path"),
            hero_image_url=hero_image_url,
            swatch_image_url=swatch_image_url,
            pdp_url=out.get("pdp_url") or details.get("pdp_url"),
            listing_status=out.get("listing_status"),
            copied_pack_images=copied_pack_images,
            max_pack_images=max_pack_images,
        )
        if not _meaningful_text(out.get("brand")):
            out["brand"] = details.get("brand_raw")
        out["title_raw"] = details.get("title_raw")
        out["summary"] = details.get("summary")
        out["description_excerpt"] = _markdown_excerpt(
            details.get("description_markdown")
        )
        out["rating"] = details.get("rating")
        out["review_count"] = details.get("review_count")
        out["badges"] = (
            CSV_LIST_SEPARATOR.join(str(item) for item in details.get("badges", []))
            if isinstance(details.get("badges"), list)
            else None
        )
        out["reviews_positive_headline"] = details.get("reviews_positive_headline")
        out["reviews_positive_comment"] = details.get("reviews_positive_comment")
        out["reviews_negative_headline"] = details.get("reviews_negative_headline")
        out["reviews_negative_comment"] = details.get("reviews_negative_comment")
        out["review_snippet_count"] = details.get("review_snippet_count")
        out["reviews_json"] = details.get("reviews_json")
        for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1):
            out[f"review_{index}_headline"] = details.get(f"review_{index}_headline")
            out[f"review_{index}_comment"] = details.get(f"review_{index}_comment")
            out[f"review_{index}_rating"] = details.get(f"review_{index}_rating")
            out[f"review_{index}_created_date"] = details.get(
                f"review_{index}_created_date"
            )
        out["variant_count"] = price_details.get("variant_count")
        out["priced_variant_count"] = price_details.get("priced_variant_count")
        out["entry_price"] = price_details.get("entry_price")
        out["max_price"] = price_details.get("max_price")
        out["price_snapshot_min_at"] = price_details.get("price_snapshot_min_at")
        out["price_snapshot_max_at"] = price_details.get("price_snapshot_max_at")
        out["entry_price_band"] = _price_band(price_details.get("entry_price"))
        out["hero_image_url"] = hero_image_url
        out["swatch_image_url"] = swatch_image_url
        out["local_image_path"] = image_meta.get("local_image_path")
        out["og_image_url"] = pack_image_meta.get("og_image_url")
        out["pack_image_path"] = pack_image_meta.get("pack_image_path")
        out["pack_image_file"] = _relative_output_path(
            output_dir, pack_image_meta.get("pack_image_path")
        )
        out["pack_image_source"] = pack_image_meta.get("pack_image_source")
        enriched_rows.append(out)

    resolved_rows = _resolve_slot_values(enriched_rows)
    enriched = (
        pl.from_dicts(resolved_rows, infer_schema_length=len(resolved_rows))
        if resolved_rows
        else all_products
    )
    resolved_core_columns = [
        column
        for column in [
            "resolved_finish",
            "resolved_coverage",
            "resolved_color",
            "resolved_form",
        ]
        if column in enriched.columns
    ]
    mapped_semantic_columns = [
        column
        for column in mapped_attribute_columns
        if column in enriched.columns
        and _is_analysis_attribute_column(column)
        and column
        not in {
            "finish",
            "finish effect",
            "coverage",
            "color family",
            "shade family",
            "color payoff",
            "form",
            "format",
            "product type",
            "applicator type",
            "treatment type",
        }
    ]
    filter_attribute_columns = (
        [
            column
            for column in category_filters.get_column("filter_family")
            .drop_nulls()
            .unique()
            .to_list()
        ]
        if category_filters.height > 0
        else []
    )
    semantic_analysis_columns = _semantic_analysis_attribute_columns(
        mapped_semantic_columns=mapped_semantic_columns,
        filter_attribute_columns=filter_attribute_columns,
        available_columns=enriched.columns,
    )
    rank_delta_attribute_columns = sorted(
        {
            column
            for column in (
                resolved_core_columns
                + semantic_analysis_columns
                + filter_attribute_columns
            )
            if column in enriched.columns and _is_analysis_attribute_column(column)
        }
    )
    sort_rank_delta_products = _build_sort_rank_delta_products(
        enriched=enriched,
        category_listing_raw=category_listing_raw,
        recent_sort_mode=recent_sort_mode,
        top_seller_sort_mode=top_seller_sort_mode,
        attribute_columns=rank_delta_attribute_columns,
    )
    sort_rank_delta_attributes = _build_sort_rank_delta_attributes(
        sort_rank_delta_products,
        attribute_columns=rank_delta_attribute_columns,
    )
    resolved_core_comparison = _build_value_comparison(
        df=enriched,
        attribute_columns=resolved_core_columns,
    )
    mapped_attribute_comparison = _build_value_comparison(
        df=enriched,
        attribute_columns=semantic_analysis_columns,
    )
    top_seller_mapped_attribute_comparison = _build_focus_value_comparison(
        df=enriched,
        attribute_columns=semantic_analysis_columns,
        status_column="top_seller_status",
        focus_label="top_seller",
        other_label="other",
        focus_prefix="top_seller",
        other_prefix="other",
    )
    sale_pressure_attribute_comparison = (
        _build_focus_value_comparison(
            df=enriched,
            attribute_columns=rank_delta_attribute_columns,
            status_column="sale_pressure_status",
            focus_label="sale_pressure",
            other_label="not_observed_sale_pressure",
            focus_prefix="sale_pressure",
            other_prefix="not_observed_sale_pressure",
        )
        if sale_pressure_sort_mode
        else _empty_focus_value_comparison(
            focus_prefix="sale_pressure",
            other_prefix="not_observed_sale_pressure",
        )
    )
    price_band_comparison = _build_value_comparison(
        df=enriched,
        attribute_columns=["entry_price_band"],
    )
    bundle_attribute_columns = _bundle_attribute_columns(
        retailer=retailer,
        category_key=category_key,
        available_columns=enriched.columns,
        default_columns=resolved_core_columns + semantic_analysis_columns,
    )
    innovation_pairs = _build_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=2,
    )
    innovation_triples = _build_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=3,
    )
    top_seller_pairs = _build_focus_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=2,
        status_column="top_seller_status",
        focus_label="top_seller",
        other_label="other",
        focus_prefix="top_seller",
        other_prefix="other",
    )
    top_seller_triples = _build_focus_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=3,
        status_column="top_seller_status",
        focus_label="top_seller",
        other_label="other",
        focus_prefix="top_seller",
        other_prefix="other",
    )
    sale_pressure_pairs = _build_focus_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=2,
        status_column="sale_pressure_status",
        focus_label="sale_pressure",
        other_label="not_observed_sale_pressure",
        focus_prefix="sale_pressure",
        other_prefix="not_observed_sale_pressure",
    )
    sale_pressure_triples = _build_focus_bundle_signals(
        df=enriched,
        attribute_columns=bundle_attribute_columns,
        bundle_size=3,
        status_column="sale_pressure_status",
        focus_label="sale_pressure",
        other_label="not_observed_sale_pressure",
        focus_prefix="sale_pressure",
        other_prefix="not_observed_sale_pressure",
    )
    sale_pressure_overlap = _build_sale_pressure_overlap_summary(enriched)
    brand_top_seller_comparison = _build_brand_top_seller_comparison(enriched)
    price_summary = _build_price_summary(enriched)
    recent_products = enriched.filter(pl.col("listing_status") == "recent").sort(
        "product_name"
    )
    rest_products = enriched.filter(pl.col("listing_status") == "rest")
    top_seller_products = enriched.filter(
        pl.col("top_seller_status") == "top_seller"
    ).sort("pareto_rank", "product_name")
    sale_pressure_products = enriched.filter(
        pl.col("sale_pressure_status") == "sale_pressure"
    ).sort("sale_pressure_rank", "product_name")
    sale_pressure_observed_share = (
        sale_pressure_products.height / category_listing.height
        if category_listing.height > 0
        else None
    )
    category_center_components = _category_center_component_table(
        enriched,
        attribute_columns=bundle_attribute_columns,
    )
    innovation_pairs = _with_signal_insight_metadata(
        innovation_pairs,
        signal_layer="innovation",
        category_center_components=category_center_components,
    )
    innovation_triples = _with_signal_insight_metadata(
        innovation_triples,
        signal_layer="innovation",
        category_center_components=category_center_components,
    )
    top_seller_pairs = _with_signal_insight_metadata(
        top_seller_pairs,
        signal_layer="winning_now",
        category_center_components=category_center_components,
    )
    top_seller_triples = _with_signal_insight_metadata(
        top_seller_triples,
        signal_layer="winning_now",
        category_center_components=category_center_components,
    )
    sale_pressure_pairs = _with_signal_insight_metadata(
        sale_pressure_pairs,
        signal_layer="sale_pressure",
        category_center_components=category_center_components,
    )
    sale_pressure_triples = _with_signal_insight_metadata(
        sale_pressure_triples,
        signal_layer="sale_pressure",
        category_center_components=category_center_components,
    )
    innovation_pairs, _ = _split_signal_rows_by_usefulness(innovation_pairs)
    innovation_triples, _ = _split_signal_rows_by_usefulness(innovation_triples)
    top_seller_pairs, _ = _split_signal_rows_by_usefulness(top_seller_pairs)
    top_seller_triples, _ = _split_signal_rows_by_usefulness(top_seller_triples)
    sale_pressure_pairs, _ = _split_signal_rows_by_usefulness(sale_pressure_pairs)
    sale_pressure_triples, _ = _split_signal_rows_by_usefulness(sale_pressure_triples)
    bundle_review_validation = _build_bundle_review_validation(
        recent_products=recent_products,
        innovation_pairs=innovation_pairs,
        innovation_triples=innovation_triples,
        attribute_columns=bundle_attribute_columns,
    )
    top_seller_review_validation = _build_bundle_review_validation(
        recent_products=top_seller_products,
        innovation_pairs=top_seller_pairs.select(
            ["bundle_size", "bundle_key", "bundle_label"]
        ),
        innovation_triples=top_seller_triples.select(
            ["bundle_size", "bundle_key", "bundle_label"]
        ),
        attribute_columns=bundle_attribute_columns,
        max_pairs=TOP_SELLER_REVIEW_VALIDATION_LIMITS[2],
        max_triples=TOP_SELLER_REVIEW_VALIDATION_LIMITS[3],
        max_products_per_bundle=TOP_SELLER_REVIEW_VALIDATION_PRODUCTS_PER_BUNDLE,
    )
    review_theme_cohort_comparison = _fetch_review_theme_cohort_comparison(
        pdp_store_path,
        retailer=retailer,
        category_key=category_key,
        product_matrix=enriched,
    )
    web_shelf_source = (
        enriched.filter(
            pl.col("pareto_rank").is_not_null()
            & (pl.col("pareto_rank").cast(pl.Float64, strict=False) > 0)
        )
        if "pareto_rank" in enriched.columns
        else pl.DataFrame(schema=enriched.schema)
    )
    web_shelf_outputs = (
        discover_web_shelves(
            web_shelf_source,
            product_id_col="listing_identity",
            rank_col="pareto_rank",
            attributes_col=None,
            attribute_columns=filter_attribute_columns,
            brand_col="brand",
            product_name_col="product_name",
            alphas=WEB_SHELF_ALPHAS,
            bundle_size=2,
            max_selected_shelves=WEB_SHELF_MAX_SELECTED_SHELVES,
            min_skus=WEB_SHELF_MIN_SKUS,
            min_brands=WEB_SHELF_MIN_BRANDS,
            exclude_dimensions=("brand",),
            include_only_filterable=False,
        )
        if filter_attribute_columns and web_shelf_source.height > 0
        else empty_web_shelf_outputs(WEB_SHELF_ALPHAS)
    )
    web_shelf_third_attribute_refinements = (
        refine_selected_shelves_with_third_attribute(
            web_shelf_source,
            web_shelf_outputs["selected_shelves"],
            alpha=WEB_SHELF_CENTRAL_ALPHA,
            max_base_shelves=WEB_SHELF_MAX_REFINEMENT_BASE_SHELVES,
            product_id_col="listing_identity",
            rank_col="pareto_rank",
            attributes_col=None,
            attribute_columns=filter_attribute_columns,
            brand_col="brand",
            product_name_col="product_name",
            min_skus=WEB_SHELF_REFINEMENT_MIN_SKUS,
            min_brands=WEB_SHELF_REFINEMENT_MIN_BRANDS,
            exclude_dimensions=("brand",),
            include_only_filterable=False,
        )
        if filter_attribute_columns and web_shelf_source.height > 0
        else refine_selected_shelves_with_third_attribute(
            web_shelf_source,
            web_shelf_outputs["selected_shelves"],
            alpha=WEB_SHELF_CENTRAL_ALPHA,
            product_id_col="listing_identity",
            rank_col="pareto_rank",
            attributes_col=None,
            attribute_columns=filter_attribute_columns,
        )
    )
    visibility_metric_kwargs = {
        "candidate_shelves": web_shelf_outputs["candidate_shelves"],
        "selected_shelves": web_shelf_outputs["selected_shelves"],
        "robustness_summary": web_shelf_outputs["robustness_summary"],
    }
    top_seller_pairs = _with_rank_weighted_visibility_metrics(
        top_seller_pairs,
        **visibility_metric_kwargs,
    )
    top_seller_triples = _with_rank_weighted_visibility_metrics(
        top_seller_triples,
        **visibility_metric_kwargs,
    )
    innovation_pairs = _with_rank_weighted_visibility_metrics(
        innovation_pairs,
        **visibility_metric_kwargs,
    )
    innovation_triples = _with_rank_weighted_visibility_metrics(
        innovation_triples,
        **visibility_metric_kwargs,
    )
    differentiating_signals = _differentiating_signal_table(
        [
            ("top_seller_pairs.csv", top_seller_pairs),
            ("top_seller_triples.csv", top_seller_triples),
            ("innovation_pairs.csv", innovation_pairs),
            ("innovation_triples.csv", innovation_triples),
            ("sale_pressure_pairs.csv", sale_pressure_pairs),
            ("sale_pressure_triples.csv", sale_pressure_triples),
        ]
    )
    attribute_table_frames = build_attribute_table_frames(
        {
            "top_seller_pairs": top_seller_pairs,
            "top_seller_triples": top_seller_triples,
            "innovation_pairs": innovation_pairs,
            "innovation_triples": innovation_triples,
            "web_shelf_selected_shelves": web_shelf_outputs["selected_shelves"],
            "web_shelf_robustness_summary": web_shelf_outputs["robustness_summary"],
            "top_seller_products": top_seller_products,
            "recent_products": recent_products,
        }
    )
    image_index = _build_image_index(recent_products)
    family_coverage_rows = (
        family_denominators.pivot(
            values="family_product_count",
            index="filter_family",
            on="listing_status",
            aggregate_function="first",
        )
        .rename({"recent": "recent_family_base", "rest": "rest_family_base"})
        .with_columns(
            pl.col("recent_family_base").fill_null(0).cast(pl.Int64),
            pl.col("rest_family_base").fill_null(0).cast(pl.Int64),
        )
        .sort("filter_family")
        .to_dicts()
        if family_denominators.height > 0
        else []
    )
    core_attribute_coverage_rows = []
    for attribute_name in resolved_core_columns:
        value_column = attribute_name
        core_attribute_coverage_rows.append(
            {
                "attribute_name": attribute_name,
                "recent_non_missing": int(
                    recent_products.filter(
                        pl.col(value_column).is_not_null()
                        & (pl.col(value_column).cast(pl.Utf8).str.strip_chars() != "")
                    ).height
                ),
                "recent_total": int(recent_products.height),
                "rest_non_missing": int(
                    rest_products.filter(
                        pl.col(value_column).is_not_null()
                        & (pl.col(value_column).cast(pl.Utf8).str.strip_chars() != "")
                    ).height
                ),
                "rest_total": int(rest_products.height),
            }
        )
    filter_observed_products = (
        category_filters.select("listing_identity").unique().height
        if category_filters.height > 0
        else 0
    )
    attribute_coverage_columns = sorted(
        set(filter_attribute_columns) | set(mapped_semantic_columns)
    )
    products_without_attributes = _products_without_any_attributes(
        enriched,
        attribute_columns=attribute_coverage_columns,
    )
    products_with_brand = _products_with_attribute(
        enriched,
        attribute_column="brand",
    )
    pdp_store_attribute_value_coverage = _attribute_value_coverage_rows(
        pdp_store_path,
        retailer=retailer,
        category_key=category_key,
    )
    review_comment_exprs = [
        pl.col(f"review_{index}_comment").is_not_null()
        for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1)
        if f"review_{index}_comment" in recent_products.columns
    ]
    review_snippet_expr = (
        pl.any_horizontal(review_comment_exprs)
        if review_comment_exprs
        else pl.lit(False)
    )
    recent_products_with_reviews = int(
        recent_products.filter(
            (pl.col("review_count").fill_null(0) > 0)
            | pl.col("reviews_positive_comment").is_not_null()
            | pl.col("reviews_negative_comment").is_not_null()
            | review_snippet_expr
        ).height
    )
    recent_products_with_pack_image = int(
        recent_products.filter(pl.col("pack_image_path").is_not_null()).height
    )
    if max_pack_images > 0:
        _require_pack_images(
            retailer=retailer,
            category_key=category_key,
            recent_products=int(recent_products.height),
            recent_products_with_pack_image=recent_products_with_pack_image,
        )

    diagnostic_warnings = _package_diagnostic_warnings(
        listing_products=int(category_listing.height),
        products_with_brand=int(products_with_brand),
        materialized_filter_attribute_rows=int(materialized_filter_attribute_rows),
        mapped_attribute_comparison_rows=int(mapped_attribute_comparison.height),
        top_seller_mapped_attribute_comparison_rows=int(
            top_seller_mapped_attribute_comparison.height
        ),
        recent_products=int(recent_products.height),
        top_seller_products=int(top_seller_products.height),
        innovation_pair_rows=int(innovation_pairs.height),
        innovation_triple_rows=int(innovation_triples.height),
        top_seller_pair_rows=int(top_seller_pairs.height),
        top_seller_triple_rows=int(top_seller_triples.height),
        recent_products_with_reviews=recent_products_with_reviews,
        top_seller_review_validation_rows=int(top_seller_review_validation.height),
        bundle_review_validation_rows=int(bundle_review_validation.height),
    )
    package_integrity = _build_launch_package_integrity_audit(
        retailer=retailer,
        category_key=package_category_key,
        source_category_key=category_key,
        product_filter_matrix=enriched,
        recent_products=recent_products,
        top_seller_products=top_seller_products,
        sale_pressure_products=sale_pressure_products,
        innovation_pairs=innovation_pairs,
        innovation_triples=innovation_triples,
        top_seller_pairs=top_seller_pairs,
        top_seller_triples=top_seller_triples,
        sale_pressure_pairs=sale_pressure_pairs,
        sale_pressure_triples=sale_pressure_triples,
        bundle_attribute_columns=bundle_attribute_columns,
        source_listing_observations=category_listing_raw,
        source_filter_observations=category_filters,
        source_mapped_attributes=source_mapped_attributes,
        recent_share=recent_share,
        recent_sort_mode=recent_sort_mode,
        sale_pressure_sort_mode=sale_pressure_sort_mode,
        source_snapshot_manifest=source_snapshot_manifest,
    )
    if package_integrity["status"] == "fail":
        (output_dir / "package_integrity.json").write_text(
            json.dumps(package_integrity, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        failure_count = package_integrity["summary"]["failure_count"]
        raise RuntimeError(
            "Retailer category package integrity audit failed before report handoff. "
            f"retailer={retailer} category={category_key} "
            f"failures={failure_count}. See package_integrity.json."
        )
    package_integrity_summary = package_integrity["summary"]

    summary = {
        "retailer": retailer,
        "retailer_label": retailer_label,
        "category_key": package_category_key,
        "category_label": category_label,
        "source_category_key": category_key,
        "source_category_label": source_category_label,
        "discovered_products": int(category_listing.height),
        "listing_products": int(category_listing.height),
        "filter_observed_products": int(filter_observed_products),
        "products_without_attributes": int(products_without_attributes),
        "products_with_attributes": int(
            category_listing.height - products_without_attributes
        ),
        "products_with_brand": int(products_with_brand),
        "recent_products": int(recent_products.height),
        "rest_products": int(rest_products.height),
        "attribute_source_contract": {
            "source_of_truth": "pdp_store:pdp_attribute_values",
            "csv_role": "package/report output only; package inputs are the PDP store",
            "coverage_view": "pdp_store:pdp_attribute_value_coverage",
        },
        "discovery_source": "pdp_store:retailer_listing_observations+retailer_filter_observations",
        "discovery_crawl_ts": discovery_crawl_ts,
        "attribute_input_source": attribute_input_source,
        "materialized_filter_attribute_rows": int(materialized_filter_attribute_rows),
        "pdp_store_attribute_value_coverage": pdp_store_attribute_value_coverage,
        "source_snapshot_manifest": source_snapshot_manifest,
        "mapped_export_products": int(mapped_export_df.height),
        "products_with_available_color": _products_with_attribute(
            enriched,
            attribute_column="available_color_families",
        ),
        "products_with_resolved_color": _products_with_attribute(
            enriched,
            attribute_column="resolved_color",
        ),
        "recent_products_with_price": int(
            recent_products.filter(pl.col("entry_price").is_not_null()).height
        ),
        "rest_products_with_price": int(
            rest_products.filter(pl.col("entry_price").is_not_null()).height
        ),
        "recent_products_with_pack_image": recent_products_with_pack_image,
        "max_pack_images": max_pack_images,
        "filter_families": (
            sorted(category_filters.get_column("filter_family").unique().to_list())
            if category_filters.height > 0
            else []
        ),
        "comparison_rows": int(comparison.height),
        "innovation_pair_rows": int(innovation_pairs.height),
        "innovation_triple_rows": int(innovation_triples.height),
        "top_seller_pair_rows": int(top_seller_pairs.height),
        "top_seller_triple_rows": int(top_seller_triples.height),
        "differentiating_signal_rows": int(differentiating_signals.height),
        "sale_pressure_pair_rows": int(sale_pressure_pairs.height),
        "sale_pressure_triple_rows": int(sale_pressure_triples.height),
        "sale_pressure_attribute_comparison_rows": int(
            sale_pressure_attribute_comparison.height
        ),
        "sale_pressure_overlap_rows": int(sale_pressure_overlap.height),
        "innovation_pair_rank_weighted_visibility_rows": _rank_weighted_visibility_metric_count(
            innovation_pairs
        ),
        "top_seller_pair_rank_weighted_visibility_rows": _rank_weighted_visibility_metric_count(
            top_seller_pairs
        ),
        "resolved_core_comparison_rows": int(resolved_core_comparison.height),
        "mapped_attribute_comparison_rows": int(mapped_attribute_comparison.height),
        "top_seller_mapped_attribute_comparison_rows": int(
            top_seller_mapped_attribute_comparison.height
        ),
        "price_band_comparison_rows": int(price_band_comparison.height),
        "bundle_review_validation_rows": int(bundle_review_validation.height),
        "top_seller_review_validation_rows": int(top_seller_review_validation.height),
        "review_theme_cohort_comparison_rows": int(
            review_theme_cohort_comparison.height
        ),
        "attribute_table_rows": {
            table_key: int(frame.height)
            for table_key, frame in attribute_table_frames.items()
        },
        "diagnostic_warning_count": int(len(diagnostic_warnings)),
        "diagnostic_warnings": diagnostic_warnings,
        "package_integrity": {
            "status": package_integrity["status"],
            "summary": package_integrity_summary,
        },
        "package_integrity_failures": int(package_integrity_summary["failure_count"]),
        "package_integrity_warnings": int(package_integrity_summary["warning_count"]),
        "web_shelf_selected_rows": int(web_shelf_outputs["selected_shelves"].height),
        "web_shelf_candidate_rows": int(web_shelf_outputs["candidate_shelves"].height),
        "web_shelf_refinement_rows": int(web_shelf_third_attribute_refinements.height),
        "top_seller_products": int(top_seller_products.height),
        "top_seller_threshold_share": TOP_SELLER_COHORT_SHARE,
        "top_seller_captured_ranked_products": int(top_seller_captured_ranked_products),
        "top_seller_universe_cutoff": int(top_seller_universe_cutoff),
        "top_seller_observed_cohort_limit": int(top_seller_observed_cohort_limit),
        "top_seller_cutoff_formula": (
            "min(top_seller_captured_ranked_products, "
            "ceil(listing_products * top_seller_threshold_share))"
        ),
        "top_seller_capture_capped_by_observed_window": bool(
            top_seller_observed_cohort_limit < top_seller_universe_cutoff
        ),
        "sale_pressure_products": int(sale_pressure_products.height),
        "sale_pressure_observed_products": int(sale_pressure_products.height),
        "sale_pressure_observed_share_of_listing_products": (
            float(sale_pressure_observed_share)
            if sale_pressure_observed_share is not None
            else None
        ),
        "recent_sort_mode": _canonical_sort_mode(retailer, recent_sort_mode),
        "recent_sort_mode_label": _display_sort_mode_label(retailer, recent_sort_mode),
        "top_seller_sort_mode": _canonical_sort_mode(retailer, top_seller_sort_mode),
        "top_seller_sort_mode_label": _display_sort_mode_label(
            retailer, top_seller_sort_mode
        ),
        "sale_pressure_available": bool(sale_pressure_sort_mode),
        "sale_pressure_sort_mode": _canonical_sort_mode(
            retailer, sale_pressure_sort_mode
        ),
        "sale_pressure_sort_mode_label": _display_sort_mode_label(
            retailer, sale_pressure_sort_mode
        ),
        "sale_pressure_capture_scope": "captured_ranked_window_only",
        "sale_pressure_absence_interpretation": (
            "Absence from the captured sale-pressure window means only that the "
            "product was not observed in the captured sale-first/promotion-first "
            "ranked window. It is not proof that the product was not discounted."
        ),
        "observed_sort_modes": sorted(_observed_sort_modes(category_listing_raw)),
        "sort_overlap_quality": sort_overlap_quality,
        "sort_rank_delta_products": int(sort_rank_delta_products.height),
        "sort_rank_delta_attributes": int(sort_rank_delta_attributes.height),
        "recent_products_with_reviews": recent_products_with_reviews,
        "family_coverage": family_coverage_rows,
        "core_attribute_coverage": core_attribute_coverage_rows,
        "recent_share": recent_share,
    }
    package_warnings = _launch_package_warning_payload(
        summary=summary,
        package_integrity=package_integrity,
        diagnostic_warnings=diagnostic_warnings,
    )
    summary["package_warning_status"] = package_warnings["status"]
    summary["package_warning_count"] = package_warnings["warning_count"]
    summary["package_warnings"] = package_warnings["warnings"]

    for diagnostic in diagnostic_warnings:
        LOGGER.warning(
            "Package diagnostic [%s] %s",
            diagnostic["code"],
            diagnostic["message"],
        )

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "package_integrity.json").write_text(
        json.dumps(package_integrity, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "package_warnings.json").write_text(
        json.dumps(package_warnings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    attribute_table_artifacts = write_attribute_table_artifacts(
        attribute_table_frames,
        output_dir,
    )
    manifest = {
        "retailer": retailer,
        "retailer_label": retailer_label,
        "category_key": package_category_key,
        "category_label": category_label,
        "source_category_key": category_key,
        "source_category_label": source_category_label,
        "run_dir": str(run_dir.resolve()) if run_dir is not None else None,
        "pdp_store_path": str(pdp_store_path.resolve()),
        "discovery_source": summary["discovery_source"],
        "discovery_crawl_ts": discovery_crawl_ts,
        "attribute_input_source": attribute_input_source,
        "attribute_source_contract": summary["attribute_source_contract"],
        "sort_overlap_quality": sort_overlap_quality,
        "files": {
            "summary": "summary.json",
            "package_integrity": "package_integrity.json",
            "package_warnings": "package_warnings.json",
            "filter_comparison": "filter_comparison.csv",
            "innovation_pairs": "innovation_pairs.csv",
            "innovation_triples": "innovation_triples.csv",
            "top_seller_pairs": "top_seller_pairs.csv",
            "top_seller_triples": "top_seller_triples.csv",
            "differentiating_signals": "differentiating_signals.csv",
            "attribute_tables_manifest": f"{ATTRIBUTE_TABLE_DIRNAME}/manifest.json",
            **{
                table_key: f"{ATTRIBUTE_TABLE_DIRNAME}/{file_name}"
                for table_key, file_name in ATTRIBUTE_TABLE_TEMPLATE_FILES.items()
            },
            **{
                f"{table_key}_html": (
                    f"{ATTRIBUTE_TABLE_DIRNAME}/{Path(file_name).stem}.html"
                )
                for table_key, file_name in ATTRIBUTE_TABLE_TEMPLATE_FILES.items()
            },
            "top_seller_brand_comparison": "top_seller_brand_comparison.csv",
            "top_seller_mapped_attribute_comparison": "top_seller_mapped_attribute_comparison.csv",
            "top_seller_review_validation": "top_seller_review_validation.csv",
            "top_seller_products": "top_seller_products.csv",
            "sale_pressure_pairs": "sale_pressure_pairs.csv",
            "sale_pressure_triples": "sale_pressure_triples.csv",
            "sale_pressure_attribute_comparison": "sale_pressure_attribute_comparison.csv",
            "sale_pressure_products": "sale_pressure_products.csv",
            "sale_pressure_overlap": "sale_pressure_overlap.csv",
            "sort_rank_delta_products": "sort_rank_delta_products.csv",
            "sort_rank_delta_attributes": "sort_rank_delta_attributes.csv",
            "resolved_core_comparison": "resolved_core_comparison.csv",
            "mapped_attribute_comparison": "mapped_attribute_comparison.csv",
            "price_comparison": "price_comparison.json",
            "price_band_comparison": "price_band_comparison.csv",
            "bundle_review_validation": "bundle_review_validation.csv",
            "review_theme_cohort_comparison": "review_theme_cohort_comparison.csv",
            "web_shelf_selected_shelves": "web_shelf_selected_shelves.csv",
            "web_shelf_candidate_shelves": "web_shelf_candidate_shelves.csv",
            "web_shelf_robustness_summary": "web_shelf_robustness_summary.csv",
            "web_shelf_product_assignments": "web_shelf_product_assignments.csv",
            "web_shelf_third_attribute_refinements": "web_shelf_third_attribute_refinements.csv",
            "product_filter_matrix": "product_filter_matrix.csv",
            "recent_products": "recent_products.csv",
            "recent_product_pdp_extracts": "recent_product_pdp_extracts.csv",
            "image_index": "image_index.csv",
            "images_dir": "images",
            "source_snapshot_manifest": f"{SOURCE_SNAPSHOT_DIRNAME}/source_manifest.json",
            "source_listing_observations": f"{SOURCE_SNAPSHOT_DIRNAME}/listing_observations.csv",
            "source_filter_observations": f"{SOURCE_SNAPSHOT_DIRNAME}/filter_observations.csv",
            "source_mapped_product_attributes": f"{SOURCE_SNAPSHOT_DIRNAME}/mapped_product_attributes.csv",
        },
        "attribute_tables": attribute_table_artifacts,
        "definitions": {
            "package_integrity": (
                "package_integrity.json is the deterministic source-to-package "
                "audit. It rebuilds product_filter_matrix.csv from source "
                "snapshots, checks product identity/cohort table consistency, "
                "and recomputes top-seller, innovation, and sale-pressure signal "
                "rows from the final product_filter_matrix inputs."
            ),
            "package_warnings": (
                "package_warnings.json is the builder-computed warning contract for "
                "Pro. It consolidates deterministic integrity warnings, package "
                "diagnostics, and data-caveat warnings. Pro should report these "
                "warnings when relevant, not invent package-integrity caveats."
            ),
            "source_snapshots": (
                "source_snapshots/ contains the listing, filter, and mapped PDP "
                "attribute rows used by the builder. These files are audit inputs, "
                "not narrative evidence for Pro."
            ),
            "recent": (
                f"Top {recent_share:.0%} of discovered products in this category by "
                f"{retailer_label} {_display_sort_mode_label(retailer, recent_sort_mode)} in the latest discovery run."
            ),
            "rest": f"All other discovered {retailer_label} products in this category.",
            "innovation_pairs": (
                "Cross-family 2-attribute combinations built from present analysis attributes only. "
                "For families covered by retailer filters, retailer filter values are primary and exported PDP "
                "attributes fill gaps. Missing values, N/A, and not-in-taxonomy values are ignored."
            ),
            "innovation_triples": (
                "Cross-family 3-attribute combinations built from present analysis attributes only. "
                "For families covered by retailer filters, retailer filter values are primary and exported PDP "
                "attributes fill gaps. Triples are more specific than pairs and may be sparse."
            ),
            "bundle_filters": (
                f"Keep only combinations with recent_count >= {MIN_RECENT_COUNT_BY_BUNDLE_SIZE[2]} for pairs or "
                f">= {MIN_RECENT_COUNT_BY_BUNDLE_SIZE[3]} for triples, recent_brand_count >= {MIN_RECENT_BRAND_COUNT}, "
                "and recent prevalence higher than rest prevalence."
            ),
            "differentiating_signals": (
                "differentiating_signals.csv combines selected top-seller, innovation, "
                "and sale-pressure rows after broad-baseline demotion. Use it to inspect "
                "what differentiates products inside the broad baseline."
            ),
            "attribute_tables": (
                "attribute_tables/ contains deterministic report-table templates built from "
                "the package signal, web-shelf, and product rows. Use these compact tables "
                "as fixed evidence tables in reports instead of asking the report writer to "
                "invent table structure or recompute values."
            ),
            "bundle_prevalence": (
                "pct_recent and pct_rest compare bundle prevalence inside the recent and rest cohorts. "
                "Use these normalized percentages, and prevalence_ratio when available, as the main comparison. "
                "Do not treat raw counts alone as comparable because the cohorts are different sizes."
            ),
            "bundle_sales_validation": (
                "Bundle files also include recent-product traction fields derived from a common ranking layer. "
                "When the discovery run includes an explicit retailer top-seller or popularity surface, "
                "pareto_rank and pareto_bucket come from that ranking. Otherwise they fall back to the "
                "exported ranking layer. "
                "Bucket A uses the full discovered category universe as the denominator, not only the "
                "captured ranked window: observed_top_seller_limit = "
                "min(top_seller_captured_ranked_products, ceil(listing_products * 0.20)). "
                "If the retailer-ranked window is shorter than the 20% universe cutoff, every captured "
                "ranked product in that window can be bucket A because that is all the observed ranking "
                "surface can support. Buckets B and C remain the next 30% and last 50% by rank position "
                "when enough ranked products are captured. "
                "These fields validate whether a recurring bundle is already getting traction; they do not define "
                "innovation by themselves."
            ),
            "bundle_review_validation": (
                "bundle_review_validation.csv contains review excerpts for recent products that belong to the "
                "identified pairs and triples when the retailer exposes usable reviews. Use it to check whether "
                "consumer experience supports or contradicts the bundle thesis. Reviews validate the proposition; "
                "they do not define innovation or recency. Empty review-validation files mean review evidence is "
                "not available for this retailer/category, not that consumers rejected the products."
            ),
            "top_sellers": (
                "Top sellers are the products in pareto bucket A, derived from the retailer top-seller or "
                "equivalent popularity surface when available. The threshold is based on the full discovered "
                "category universe, not the size of the captured top-seller page window: "
                "observed_top_seller_limit = min(top_seller_captured_ranked_products, "
                "ceil(listing_products * top_seller_threshold_share)), where top_seller_threshold_share is 0.20."
            ),
            "sale_pressure": (
                "sale_pressure means the product appears in a retailer sale-first or promotion-first ranked "
                "surface when that surface was observed. This package captures the ranked window collected "
                "during discovery, not necessarily the retailer's full promoted assortment. Treat it as a "
                "promotion-exposure proxy only: it is weaker than a true discount flag, and absence from this "
                "captured window is not proof that a product was not discounted."
            ),
            "sale_pressure_files": (
                "sale_pressure_products.csv lists products found on the sale-pressure sort surface with their "
                "sale_pressure_rank. sale_pressure_attribute_comparison.csv, sale_pressure_pairs.csv, and "
                "sale_pressure_triples.csv compare promo-proxy products against products not observed in the "
                "captured sale-pressure window. sale_pressure_overlap.csv summarizes overlap with recent and "
                "top-seller cohorts."
            ),
            "rank_weighted_bundle_visibility": (
                "top_seller_pairs.csv and innovation_pairs.csv include rank_weighted_* visibility columns "
                "when a 2-attribute bundle can be matched to retailer filter attributes. "
                "Gross visibility is the full rank-weighted share of products matching the bundle and can "
                "overlap across bundles. Incremental visibility is available only for bundles selected by "
                "greedy overlap removal; it measures the additional rank-weighted share left after earlier "
                "selected bundles have claimed their products."
            ),
            "top_seller_brand_comparison": (
                "top_seller_brand_comparison.csv shows how much each brand is over- or under-indexed in the "
                "top-seller cohort relative to its catalog share."
            ),
            "top_seller_review_validation": (
                "top_seller_review_validation.csv contains a trimmed review-validation sample for the strongest "
                "top-seller bundles when the retailer exposes usable reviews, capped to keep the pack readable. "
                "If empty, treat reviews as unavailable evidence."
            ),
            "review_theme_cohort_comparison": (
                "review_theme_cohort_comparison.csv is computed by this package from the latest frozen "
                "review-theme codebook run. The review run only discovers themes from stratified samples "
                "and tags reviews against the fixed codebook; this package applies the current top-seller "
                "and recent-product cohorts. Use this as a secondary review-visible experience layer, "
                "not as taxonomy or causality. The experience_signal_class column separates positive "
                "over-index, negative risk, salience-only, and table-stakes themes."
            ),
            "rank_weighted_visibility_audit": (
                "web_shelf_selected_shelves.csv is the audit table behind incremental rank-weighted bundle "
                "visibility. It decomposes retailer-ranked products into greedy, non-overlapping "
                "2-filter-attribute product sets. Rank is converted to visibility weight using "
                "alpha assumptions "
                f"{', '.join(str(alpha) for alpha in WEB_SHELF_ALPHAS)}. "
                "Use it to audit the rank_weighted_* columns on bundle files, not as a separate report concept."
            ),
            "web_shelf_robustness": (
                "web_shelf_robustness_summary.csv shows which incremental visibility calculations survive under "
                "multiple alpha assumptions. A bundle that appears only under the steepest alpha may be driven by very few "
                "top-ranked products."
            ),
            "web_shelf_product_assignments": (
                "web_shelf_product_assignments.csv is the audit trail for greedy removal. Each product is assigned "
                "to at most one selected product set per alpha, with unassigned leftovers grouped into __residual__."
            ),
            "web_shelf_refinements": (
                "web_shelf_third_attribute_refinements.csv refines the central alpha 2-attribute visibility "
                "sets with a third retailer-filter attribute. Treat refinements as product-set concentration, not proof that "
                "shoppers used those filters."
            ),
            "sort_rank_delta": (
                "When newest and top-seller surfaces overlap heavily, product-set contrast is weak and rank order "
                "becomes the signal. sort_rank_delta_products.csv compares overlapping products by "
                "rank_delta = newest_rank - top_seller_rank; positive values mean the product ranks better in "
                "top sellers than in newest, while negative values mean it ranks better in newest. "
                "sort_rank_delta_attributes.csv aggregates that movement by attribute value."
            ),
            "filter_denominator": "pct_recent and pct_rest are computed against products in the same group that have at least one observed value in that filter family.",
            "resolved_core_attributes": (
                "Resolved core attributes are the best available shopper-facing values for finish, coverage, "
                "color, and form in this category. Retailer filter color is preferred for product-level color; "
                "variant-scoped exported color is retained separately as available_color_families."
            ),
            "available_color_families": (
                "available_color_families is a product-level multi-value rollup from variant color-family "
                "attributes when a matching variant export is available, with retailer filter color as fallback."
            ),
            "mapped_semantic_attributes": (
                f"Analysis attributes prefer {retailer_label} retailer-filter values for overlapping families and "
                "fall back to exported PDP attributes when filters do not provide a value."
            ),
            "pricing": "Entry and max price come from stored variant-price snapshots at PDP scrape time, not from a live-price read and not from a historical time series.",
        },
    }
    (output_dir / "pack_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    prompt = f"""You are a skeptical market analyst working for a marketer, not for a strategy professor.\n\nAnalyze the {retailer_label} {summary['category_label']} evidence pack and answer two linked questions: what attribute bundles are winning now, and what innovation signals are emerging relative to that baseline?\n\nCore logic:\n- Check package_integrity.json before trusting the package tables. If the status is not pass, treat the integrity issues as package caveats rather than report evidence.\n- Check package_warnings.json immediately after package_integrity.json. These are builder-computed warnings and data caveats. Preserve relevant warnings, but do not invent package-integrity caveats outside this file.\n- Start with top_seller_pairs.csv and top_seller_triples.csv. This is the primary backbone because it tells you what wins now.\n- Use top_seller_brand_comparison.csv to avoid confusing brand scale with attribute signal. If a top-seller bundle is mostly just one over-indexed brand, say so.\n- Use top_seller_mapped_attribute_comparison.csv as supporting context for the winning-now layer.\n- Use top_seller_review_validation.csv and PDP text/images only to validate whether the winning bundle is credibly expressed in product reality and consumer response.\n- Then move to innovation_pairs.csv and innovation_triples.csv as the emerging layer.\n- Use bundle_review_validation.csv only after the innovation bundles are identified.\n- Use resolved_core_comparison.csv and mapped_attribute_comparison.csv only as supporting context.\n- Use price_comparison.json and price_band_comparison.csv for pricing context only, not to define the main signal.\n- Use filter_comparison.csv only as QA on the raw {retailer_label} filter layer.\n\nImportant rules:\n- Bundles are built from present analysis attributes. For families covered by {retailer_label} retailer filters, use those values first and rely on exported PDP attributes only when the filter layer has no value. Missing values, N/A, and not-in-taxonomy values are ignored.\n- Top sellers are the products in pareto bucket A, derived from the retailer popularity ranking when available.\n- A top-seller pair or triple matters only if it repeats across several top sellers. Note whether it appears across more than one brand or is dominated by a single brand.\n- Do not assume recent means new-to-market; it means the product is in the top {recent_share:.0%} of this category by {retailer_label} {_display_sort_mode_label(retailer, recent_sort_mode)} in the latest discovery run.\n- For innovation, a pair or triple matters only if it repeats across several recent products, appears across more than one brand, and is more common in recent than in rest.\n- Because cohorts are different-sized, compare bundles using pct_top_seller vs pct_other for the winning-now layer and pct_recent vs pct_rest for the innovation layer. Do not use raw counts alone as the main evidence line.\n- Reviews are not the discovery layer. Use them only to validate or challenge the identified bundle when they are present. If review-validation files are empty, state that consumer-review evidence is unavailable; do not treat missing reviews as a package failure or negative consumer signal.\n- Prefer strong evidence for small useful signals over weak evidence for big stories.\n- Do not hunt for world-moving narratives. If the only valid conclusion is modest, say the modest thing clearly.\n- Present findings only. Do not give recommendations, action items, implications, strategic advice, or \"what marketers should do\" sections.\n- Keep the output descriptive and evidence-led. End with a factual synthesis, not a prescriptive one.\n- Do not do slide planning, deck structure, or presentation treatment. Your job is the story only.\n\nFiles:\n- summary.json: cohort size, thresholds, and basic coverage.\n- package_integrity.json: source-to-package audit; it rebuilds product_filter_matrix.csv from source_snapshots/ and recomputes signal tables from product_filter_matrix.csv.
- package_warnings.json: builder-computed warning contract. Use this for package caveats instead of inferring your own.
- source_snapshots/: audit-only source rows used by the builder. Do not use these files as narrative evidence except to explain package caveats from package_integrity.json.\n- attribute_tables/: deterministic compact report-table templates. Prefer these files when the report needs tables; do not recreate their arithmetic or table structure manually.\n- top_seller_pairs.csv: filtered recurring 2-attribute combinations in top sellers vs others.\n- top_seller_triples.csv: filtered recurring 3-attribute combinations in top sellers vs others.\n- top_seller_brand_comparison.csv: brand over-indexing in the top-seller cohort.\n- top_seller_mapped_attribute_comparison.csv: supporting top-seller vs other differences for mapped attributes.\n- top_seller_review_validation.csv: review excerpts for top-seller products that belong to the identified winning bundles when review evidence is available.\n- top_seller_products.csv: top-seller products with attributes, pricing, and image paths.\n- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest.\n- innovation_triples.csv: filtered recurring 3-attribute combinations in recent vs rest.\n- bundle_review_validation.csv: review excerpts for recent products that belong to the identified innovation bundles when review evidence is available.\n- resolved_core_comparison.csv: supporting recent-vs-rest differences for resolved core shopper attributes.\n- mapped_attribute_comparison.csv: supporting recent-vs-rest differences for mapped semantic attributes.\n- price_comparison.json: pricing summary from stored price snapshots.\n- price_band_comparison.csv: comparison of entry-price bands.\n- filter_comparison.csv: raw {retailer_label}-filter differences between recent and rest.\n- recent_products.csv: recent products with attributes, pricing, and image paths.\n- recent_product_pdp_extracts.csv: PDP summaries/excerpts for the recent products.\n- images/: one image per recent product.\n\nOutput:\n1. Winning now: what are the clearest top-selling bundles in this category?\n2. Brand context: which winning signals survive contact with brand concentration, and which are mostly brand effects?\n3. PDP/review validation of winners: where do PDP text and reviews confirm the top-selling propositions, and where do they reveal friction or limits?\n4. Innovation layer: what recurring innovation signal is emerging, if any?\n5. Innovation vs winners: which emerging bundles align with current winners, which diverge, and which look too thin to matter yet?\n6. What did not produce a clear signal: where the category is stable, noisy, or too fragmented.\n7. Standout products: which 2 to 4 products best embody the winning-now layer, and which 2 to 4 best embody the innovation layer?\n8. Factual synthesis: the shortest evidence-led read of what is true in this category right now, with no recommendations.\n9. Analytical recap block with exactly these fields:\n   - Winning now\n   - Emerging signal\n   - Brand effect level: high / medium / low\n   - Confidence: high / medium / low\n   - Most relevant examples\n"""
    prompt = prompt.replace(
        "- images/: one image per recent product.\n",
        (
            f"- images/: up to {max_pack_images} recent-product images; "
            "use image_index.csv to see which products have copied images.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Top sellers are the products in pareto bucket A, derived from the retailer popularity "
            "ranking when available.\n"
        ),
        (
            "- Top sellers are the products in pareto bucket A, derived from the retailer popularity "
            "ranking when available. The cutoff uses the full discovered category universe, not the "
            "captured ranked window alone: observed_top_seller_limit = "
            "min(top_seller_captured_ranked_products, ceil(listing_products * 0.20)).\n"
        ),
    )
    prompt = prompt.replace(
        "- top_seller_pairs.csv: filtered recurring 2-attribute combinations in top sellers vs others.\n",
        "- top_seller_pairs.csv: filtered recurring 2-attribute combinations in top sellers vs others, with rank_weighted_* visibility metrics when available.\n",
    )
    prompt = prompt.replace(
        "- Use top_seller_review_validation.csv and PDP text/images only to validate whether the winning bundle is credibly expressed in product reality and consumer response.\n",
        "- Use top_seller_review_validation.csv and PDP text/images only to validate whether the winning bundle is credibly expressed in product reality and consumer response.\n"
        "- Use review_theme_cohort_comparison.csv only as a secondary review-visible experience layer. It is not a taxonomy attribute layer and it is not causal evidence. Use experience_signal_class and experience_signal_summary before using raw mention rates.\n",
    )
    prompt = prompt.replace(
        "- Reviews are not the discovery layer. Use them only to validate or challenge the identified bundle when they are present. If review-validation files are empty, state that consumer-review evidence is unavailable; do not treat missing reviews as a package failure or negative consumer signal.\n",
        "- Reviews are not the discovery layer. Use them only to validate or challenge the identified bundle when they are present. If review-validation files are empty, state that consumer-review evidence is unavailable; do not treat missing reviews as a package failure or negative consumer signal.\n"
        '- When using review_theme_cohort_comparison.csv, say "review-visible dimensions over-indexing among..." rather than "drivers" or "causes." Always preserve polarity: positive_over_index, negative_over_index, salience_only, and table_stakes mean different things.\n',
    )
    prompt = prompt.replace(
        "- top_seller_review_validation.csv: review excerpts for top-seller products that belong to the identified winning bundles when review evidence is available.\n",
        "- top_seller_review_validation.csv: review excerpts for top-seller products that belong to the identified winning bundles when review evidence is available.\n"
        "- review_theme_cohort_comparison.csv: package-computed comparisons of frozen-codebook review dimensions across current package cohorts, classified into positive/negative/polarized/salience/table-stakes experience signals with polarity rates and evidence snippets. Use only as secondary experience evidence.\n",
    )
    prompt = prompt.replace(
        "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest.\n",
        "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest, with rank_weighted_* visibility metrics when available.\n",
    )
    prompt = prompt.replace(
        "1. Winning now: what are the clearest top-selling bundles in this category?\n",
        "1. Winning now: what are the clearest top-selling bundles in this category, and how much gross/incremental rank-weighted visibility do they carry where available?\n",
    )
    prompt = prompt.replace(
        "   - Winning now\n   - Emerging signal\n",
        "   - Winning now\n   - Rank-weighted visibility read\n   - Emerging signal\n",
    )
    prompt = prompt.replace(
        (
            "- Bundles are built from present analysis attributes. For families covered by "
            f"{retailer_label} retailer filters, use those values first and rely on "
            "exported PDP attributes only when the filter layer has no value. Missing "
            "values, N/A, and not-in-taxonomy values are ignored.\n"
        ),
        (
            "- Bundles are built from present analysis attributes. For families covered by "
            f"{retailer_label} retailer filters, use those values first and rely on "
            "exported PDP attributes only when the filter layer has no value. Missing "
            "values, N/A, and not-in-taxonomy values are ignored.\n"
            '- Use "form" as the attribute name for product delivery type, such as '
            "stick, liquid, pressed powder, wand, tube, compact, or balm.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Use bundle_review_validation.csv only after the innovation bundles are identified.\n"
            "- Use resolved_core_comparison.csv and mapped_attribute_comparison.csv only as supporting context.\n"
        ),
        (
            "- Use bundle_review_validation.csv only after the innovation bundles are identified.\n"
            "- If summary.json shows sort_overlap_quality.analysis_mode = rank_order_contrast, "
            "use sort_rank_delta_products.csv and sort_rank_delta_attributes.csv as the main "
            "bridge between innovation and winners. In that case, product overlap is a market "
            "signal, not a package failure.\n"
            "- Use resolved_core_comparison.csv and mapped_attribute_comparison.csv only as supporting context.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Because cohorts are different-sized, compare bundles using pct_top_seller vs pct_other "
            "for the winning-now layer and pct_recent vs pct_rest for the innovation layer. Do not "
            "use raw counts alone as the main evidence line.\n"
        ),
        (
            "- Because cohorts are different-sized, compare bundles using pct_top_seller vs pct_other "
            "for the winning-now layer and pct_recent vs pct_rest for the innovation layer. Do not "
            "use raw counts alone as the main evidence line.\n"
            "- If newest and top-seller cohorts overlap heavily, do not present the two cohorts as "
            "independent. Read rank_delta = newest_rank - top_seller_rank instead: positive values "
            "mean the attribute or product moved up in top sellers, negative values mean it is more "
            "prominent in newest than in top sellers, and near-zero values mean it is strong in both views.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- top_seller_products.csv: top-seller products with attributes, pricing, and image paths.\n"
            "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest, with rank_weighted_* visibility metrics when available.\n"
        ),
        (
            "- top_seller_products.csv: top-seller products with attributes, pricing, and image paths.\n"
            "- sort_rank_delta_products.csv: overlapping newest/top-seller products with newest_rank, "
            "top_seller_rank, rank_delta, and attributes.\n"
            "- sort_rank_delta_attributes.csv: attribute-level aggregation of rank movement inside "
            "overlapping newest/top-seller products.\n"
            "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest, with rank_weighted_* visibility metrics when available.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Use top_seller_mapped_attribute_comparison.csv as supporting context for the winning-now layer.\n"
            "- Use top_seller_review_validation.csv and PDP text/images only to validate whether the winning bundle "
            "is credibly expressed in product reality and consumer response.\n"
        ),
        (
            "- Use top_seller_mapped_attribute_comparison.csv as supporting context for the winning-now layer.\n"
            "- Use rank_weighted_* columns in top_seller_pairs.csv and innovation_pairs.csv as visibility metrics "
            "attached to the same bundles, not as a separate signal family.\n"
            "- Use web_shelf_selected_shelves.csv and web_shelf_robustness_summary.csv only as audit files behind "
            "those gross and incremental rank-weighted visibility metrics.\n"
            "- Use top_seller_review_validation.csv and PDP text/images only to validate whether the winning bundle "
            "is credibly expressed in product reality and consumer response.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- A top-seller pair or triple matters only if it repeats across several top sellers. Note whether it appears "
            "across more than one brand or is dominated by a single brand.\n"
            "- Do not assume recent means new-to-market; it means the product is in the top "
        ),
        (
            "- A top-seller pair or triple matters only if it repeats across several top sellers. Note whether it appears "
            "across more than one brand or is dominated by a single brand.\n"
            "- Rank-weighted visibility metrics are based on retailer filter attributes and retailer rank only. "
            "They are not sell-out sales, demand proof, or shopper path attribution.\n"
            "- Gross rank-weighted visibility can overlap across bundles; incremental visibility is non-overlapping "
            "because selected products are removed before the next bundle is calculated.\n"
            "- Do not assume recent means new-to-market; it means the product is in the top "
        ),
    )
    prompt = prompt.replace(
        (
            "- sort_rank_delta_attributes.csv: attribute-level aggregation of rank movement inside "
            "overlapping newest/top-seller products.\n"
            "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest.\n"
        ),
        (
            "- sort_rank_delta_attributes.csv: attribute-level aggregation of rank movement inside "
            "overlapping newest/top-seller products.\n"
            "- web_shelf_selected_shelves.csv: audit table for the incremental rank-weighted visibility metrics "
            "attached to 2-attribute retailer-filter bundles.\n"
            "- web_shelf_candidate_shelves.csv: audit table for overlapping gross visibility before greedy removal.\n"
            "- web_shelf_robustness_summary.csv: selected incremental visibility calculations across alpha assumptions.\n"
            "- web_shelf_third_attribute_refinements.csv: strongest third-attribute refinements inside the central-alpha "
            "2-attribute visibility sets.\n"
            "- innovation_pairs.csv: filtered recurring 2-attribute combinations in recent vs rest, with rank_weighted_* visibility metrics when available.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "2. Brand context: which winning signals survive contact with brand concentration, and which are mostly brand effects?\n"
            "3. PDP/review validation of winners: where do PDP text and reviews confirm the top-selling propositions, and where do they reveal friction or limits?\n"
            "4. Innovation layer: what recurring innovation signal is emerging, if any?\n"
            "5. Innovation vs winners: which emerging bundles align with current winners, which diverge, and which look too thin to matter yet?\n"
            "6. What did not produce a clear signal: where the category is stable, noisy, or too fragmented.\n"
            "7. Standout products: which 2 to 4 products best embody the winning-now layer, and which 2 to 4 best embody the innovation layer?\n"
            "8. Factual synthesis: the shortest evidence-led read of what is true in this category right now, with no recommendations.\n"
            "9. Analytical recap block with exactly these fields:\n"
            "   - Winning now\n"
            "   - Rank-weighted visibility read\n"
            "   - Emerging signal\n"
        ),
        (
            "2. Brand context: which winning signals survive contact with brand concentration, and which are mostly brand effects?\n"
            "3. Rank-weighted visibility of winners: where gross visibility is broad, where incremental visibility adds new information, and where overlap makes bundles repetitive.\n"
            "4. PDP/review validation of winners: where do PDP text and reviews confirm the top-selling propositions, and where do they reveal friction or limits?\n"
            "5. Innovation layer: what recurring innovation signal is emerging, if any?\n"
            "6. Innovation vs winners: which emerging bundles align with current winners, which diverge, and which look too thin to matter yet?\n"
            "7. What did not produce a clear signal: where the category is stable, noisy, or too fragmented.\n"
            "8. Standout products: which 2 to 4 products best embody the winning-now layer and which 2 to 4 best embody the innovation layer?\n"
            "9. Factual synthesis: the shortest evidence-led read of what is true in this category right now, with no recommendations.\n"
            "10. Analytical recap block with exactly these fields:\n"
            "   - Winning now\n"
            "   - Rank-weighted visibility read\n"
            "   - Emerging signal\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Use bundle_review_validation.csv only after the innovation bundles are identified.\n"
            "- If summary.json shows sort_overlap_quality.analysis_mode = rank_order_contrast, "
            "use sort_rank_delta_products.csv and sort_rank_delta_attributes.csv as the main "
            "bridge between innovation and winners. In that case, product overlap is a market "
            "signal, not a package failure.\n"
            "- Use resolved_core_comparison.csv and mapped_attribute_comparison.csv only as supporting context.\n"
        ),
        (
            "- Use bundle_review_validation.csv only after the innovation bundles are identified.\n"
            "- If summary.json shows sort_overlap_quality.analysis_mode = rank_order_contrast, "
            "use sort_rank_delta_products.csv and sort_rank_delta_attributes.csv as the main "
            "bridge between innovation and winners. In that case, product overlap is a market "
            "signal, not a package failure.\n"
            "- Use sale_pressure_products.csv, sale_pressure_attribute_comparison.csv, "
            "sale_pressure_pairs.csv, sale_pressure_triples.csv, and sale_pressure_overlap.csv "
            "only as a promotion-exposure proxy layer. Use it to qualify whether winners or "
            "recent products may be promotion-assisted; do not let it define winners or innovation by itself.\n"
            "- Use resolved_core_comparison.csv and mapped_attribute_comparison.csv only as supporting context.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "mean the attribute or product moved up in top sellers, negative values mean it is more "
            "prominent in newest than in top sellers, and near-zero values mean it is strong in both views.\n"
            "- Reviews are not the discovery layer."
        ),
        (
            "mean the attribute or product moved up in top sellers, negative values mean it is more "
            "prominent in newest than in top sellers, and near-zero values mean it is strong in both views.\n"
            "- sale_pressure is not a definitive discount flag. Products in sale-pressure files have evidence "
            "of sale-first or promotion-first exposure inside the captured ranked window; products absent from "
            "those files are not proven to be full-price or not discounted.\n"
            "- Read sale-pressure overlap directionally: best seller + sale-pressure may be promo-assisted "
            "traction; best seller without sale-pressure is a cleaner demand/rank signal; recent + "
            "sale-pressure deserves caution; recent + top seller without sale-pressure is stronger early traction.\n"
            "- Reviews are not the discovery layer."
        ),
    )
    prompt = prompt.replace(
        (
            "- top_seller_products.csv: top-seller products with attributes, pricing, and image paths.\n"
            "- sort_rank_delta_products.csv: overlapping newest/top-seller products with newest_rank, "
        ),
        (
            "- top_seller_products.csv: top-seller products with attributes, pricing, and image paths.\n"
            "- sale_pressure_products.csv: products appearing in the sale-first or promotion-first sort surface when observed.\n"
            "- sale_pressure_attribute_comparison.csv: attribute values over- or under-indexing among sale-pressure products vs products not observed in the captured sale-pressure window.\n"
            "- sale_pressure_pairs.csv and sale_pressure_triples.csv: recurring bundles concentrated among sale-pressure products vs the rest of the category.\n"
            "- sale_pressure_overlap.csv: cohort overlap between sale-pressure, recent, and top-seller products.\n"
            "- sort_rank_delta_products.csv: overlapping newest/top-seller products with newest_rank, "
        ),
    )
    prompt = prompt.replace(
        (
            "3. Rank-weighted visibility of winners: where gross visibility is broad, where incremental visibility adds new information, and where overlap makes bundles repetitive.\n"
            "4. PDP/review validation of winners: where do PDP text and reviews confirm the top-selling propositions, and where do they reveal friction or limits?\n"
            "5. Innovation layer: what recurring innovation signal is emerging, if any?\n"
            "6. Innovation vs winners: which emerging bundles align with current winners, which diverge, and which look too thin to matter yet?\n"
            "7. What did not produce a clear signal: where the category is stable, noisy, or too fragmented.\n"
            "8. Standout products: which 2 to 4 products best embody the winning-now layer and which 2 to 4 best embody the innovation layer?\n"
            "9. Factual synthesis: the shortest evidence-led read of what is true in this category right now, with no recommendations.\n"
            "10. Analytical recap block with exactly these fields:\n"
            "   - Winning now\n"
            "   - Rank-weighted visibility read\n"
            "   - Emerging signal\n"
        ),
        (
            "3. Rank-weighted visibility of winners: where gross visibility is broad, where incremental visibility adds new information, and where overlap makes bundles repetitive.\n"
            "4. Promotion-pressure read: where sale-pressure exposure overlaps with winners or newness, and where the signal is too weak to matter.\n"
            "5. PDP/review validation of winners: where do PDP text and reviews confirm the top-selling propositions, and where do they reveal friction or limits?\n"
            "6. Innovation layer: what recurring innovation signal is emerging, if any?\n"
            "7. Innovation vs winners: which emerging bundles align with current winners, which diverge, and which look too thin to matter yet?\n"
            "8. What did not produce a clear signal: where the category is stable, noisy, too fragmented, or only promotion-exposed.\n"
            "9. Standout products: which 2 to 4 products best embody the winning-now layer, which 2 to 4 best embody the innovation layer, and whether any are sale-pressure exposed.\n"
            "10. Factual synthesis: the shortest evidence-led read of what is true in this category right now, with no recommendations.\n"
            "11. Analytical recap block with exactly these fields:\n"
            "   - Winning now\n"
            "   - Rank-weighted visibility read\n"
            "   - Emerging signal\n"
            "   - Promotion-pressure read\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- Start with top_seller_pairs.csv and top_seller_triples.csv. This is the primary backbone because it tells you what wins now.\n"
        ),
        "- Start with top_seller_pairs.csv and top_seller_triples.csv. This is the primary backbone because it tells you what wins now.\n",
    )
    prompt = prompt.replace(
        (
            "- Because cohorts are different-sized, compare bundles using pct_top_seller vs pct_other "
            "for the winning-now layer and pct_recent vs pct_rest for the innovation layer. Do not "
            "use raw counts alone as the main evidence line.\n"
        ),
        (
            "- Because cohorts are different-sized, compare bundles using pct_top_seller vs pct_other "
            "for the winning-now layer and pct_recent vs pct_rest for the innovation layer. Do not "
            "use raw counts alone as the main evidence line.\n"
            "- Do not let broad baseline attributes dominate the story. Use them only as context unless the same bundle also contains a differentiating axis.\n"
        ),
    )
    prompt = prompt.replace(
        (
            "- top_seller_triples.csv: filtered recurring 3-attribute combinations in top sellers vs others.\n"
        ),
        (
            "- top_seller_triples.csv: filtered recurring 3-attribute combinations in top sellers vs others.\n"
            "- differentiating_signals.csv: combined selected top-seller, innovation, and promotion-pressure rows after broad-baseline demotion.\n"
        ),
    )
    (output_dir / "prompt_for_pro.txt").write_text(prompt, encoding="utf-8")
    comparison.write_csv(output_dir / "filter_comparison.csv")
    _pro_visible_signal_table(innovation_pairs).write_csv(
        output_dir / "innovation_pairs.csv"
    )
    _pro_visible_signal_table(innovation_triples).write_csv(
        output_dir / "innovation_triples.csv"
    )
    _pro_visible_signal_table(top_seller_pairs).write_csv(
        output_dir / "top_seller_pairs.csv"
    )
    _pro_visible_signal_table(top_seller_triples).write_csv(
        output_dir / "top_seller_triples.csv"
    )
    _pro_visible_signal_table(differentiating_signals).write_csv(
        output_dir / "differentiating_signals.csv"
    )
    brand_top_seller_comparison.write_csv(
        output_dir / "top_seller_brand_comparison.csv"
    )
    top_seller_mapped_attribute_comparison.write_csv(
        output_dir / "top_seller_mapped_attribute_comparison.csv"
    )
    resolved_core_comparison.write_csv(output_dir / "resolved_core_comparison.csv")
    mapped_attribute_comparison.write_csv(
        output_dir / "mapped_attribute_comparison.csv"
    )
    (output_dir / "price_comparison.json").write_text(
        json.dumps(price_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    price_band_comparison.write_csv(output_dir / "price_band_comparison.csv")
    bundle_review_validation.write_csv(output_dir / "bundle_review_validation.csv")
    top_seller_review_validation.write_csv(
        output_dir / "top_seller_review_validation.csv"
    )
    review_theme_cohort_comparison.write_csv(
        output_dir / "review_theme_cohort_comparison.csv"
    )
    _pro_visible_signal_table(sale_pressure_pairs).write_csv(
        output_dir / "sale_pressure_pairs.csv"
    )
    _pro_visible_signal_table(sale_pressure_triples).write_csv(
        output_dir / "sale_pressure_triples.csv"
    )
    sale_pressure_attribute_comparison.write_csv(
        output_dir / "sale_pressure_attribute_comparison.csv"
    )
    sale_pressure_overlap.write_csv(output_dir / "sale_pressure_overlap.csv")
    web_shelf_outputs["selected_shelves"].write_csv(
        output_dir / "web_shelf_selected_shelves.csv"
    )
    web_shelf_outputs["candidate_shelves"].write_csv(
        output_dir / "web_shelf_candidate_shelves.csv"
    )
    web_shelf_outputs["robustness_summary"].write_csv(
        output_dir / "web_shelf_robustness_summary.csv"
    )
    web_shelf_outputs["product_shelf_assignments"].write_csv(
        output_dir / "web_shelf_product_assignments.csv"
    )
    web_shelf_third_attribute_refinements.write_csv(
        output_dir / "web_shelf_third_attribute_refinements.csv"
    )
    enriched.write_csv(output_dir / "product_filter_matrix.csv")
    recent_products_pro = _strip_provenance_columns(recent_products)
    recent_products_pro.write_csv(output_dir / "recent_products.csv")
    _strip_provenance_columns(top_seller_products).write_csv(
        output_dir / "top_seller_products.csv"
    )
    _strip_provenance_columns(sale_pressure_products).write_csv(
        output_dir / "sale_pressure_products.csv"
    )
    _strip_provenance_columns(sort_rank_delta_products).write_csv(
        output_dir / "sort_rank_delta_products.csv"
    )
    sort_rank_delta_attributes.write_csv(output_dir / "sort_rank_delta_attributes.csv")
    image_index.write_csv(output_dir / "image_index.csv")
    _strip_provenance_columns(
        recent_products.select(
            [
                "parent_product_id",
                "product_name",
                "pdp_url",
                "entry_price",
                "max_price",
                "entry_price_band",
                "variant_count",
                "priced_variant_count",
                "price_snapshot_min_at",
                "price_snapshot_max_at",
                "summary",
                "description_excerpt",
                "rating",
                "review_count",
                "badges",
                "has_new_badge",
                "has_filter_observations",
                "filter_family_count",
                "filter_membership_count",
                "pack_image_path",
                "pack_image_file",
                "pack_image_source",
                "local_image_path",
                "hero_image_url",
                "og_image_url",
                "available_color_families",
                "available_color_family_count",
                "available_color_source",
                "resolved_finish",
                "resolved_coverage",
                "resolved_color",
                "resolved_form",
            ]
            + [
                column
                for column in recent_products.columns
                if column in mapped_semantic_columns
            ]
        )
    ).write_csv(output_dir / "recent_product_pdp_extracts.csv")
    _write_pack_zip(output_dir)
    return output_dir


def build_pack(
    *,
    retailer: str,
    category_key: str,
    run_dir: Path | None,
    pdp_store_path: Path,
    cli_root: Path,
    output_root: Path,
    max_pack_images: int | None = PACK_IMAGE_HARD_LIMIT,
    attribute_frames: _MappedAttributeFrames | None = None,
) -> Path:
    """Build a retailer package and remove partial output if generation fails."""

    output_dir = _package_output_dir(
        output_root,
        retailer=retailer,
        category_key=category_key,
    )
    try:
        return _build_pack_impl(
            retailer=retailer,
            category_key=category_key,
            run_dir=run_dir,
            pdp_store_path=pdp_store_path,
            cli_root=cli_root,
            output_root=output_root,
            max_pack_images=max_pack_images,
            attribute_frames=attribute_frames,
        )
    except Exception:
        _clear_existing_package_output_dir(
            output_root,
            retailer=retailer,
            category_key=category_key,
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        raise


def build_all_packs(
    *,
    pdp_store_path: Path,
    cli_root: Path,
    output_root: Path,
    retailer: str,
    category_keys: list[str] | None = None,
    run_dir: Path | None = None,
    fail_fast: bool = False,
    max_pack_images: int | None = PACK_IMAGE_HARD_LIMIT,
) -> pl.DataFrame:
    """Build selected or discovered category packages for a retailer."""
    max_pack_images = _bounded_pack_image_limit(max_pack_images)
    if category_keys:
        pairs = [(retailer, category_key) for category_key in category_keys]
    else:
        pairs = _discovered_retailer_categories(pdp_store_path, retailer=retailer)
    if not pairs:
        raise RuntimeError(
            "No retailer/category listing observations found in the PDP store "
            f"for retailer={retailer}."
        )

    category_keys_for_batch = [category_key for _retailer, category_key in pairs]
    LOGGER.info(
        "Preloading mapped PDP attributes once for retailer package batch: retailer=%s categories=%s",
        retailer,
        len(category_keys_for_batch),
    )
    attribute_frames = _load_mapped_attribute_frames(
        pdp_store_path=pdp_store_path,
        retailer=retailer,
        category_keys=category_keys_for_batch,
    )
    summary_rows: list[dict[str, str | None]] = []
    total_pairs = len(pairs)
    for package_index, (retailer_key, category_key) in enumerate(pairs, start=1):
        LOGGER.info(
            "Building retailer/category package %s of %s: %s / %s",
            package_index,
            total_pairs,
            retailer_key,
            category_key,
        )
        try:
            output_dir = build_pack(
                retailer=retailer_key,
                category_key=category_key,
                run_dir=run_dir,
                pdp_store_path=pdp_store_path,
                cli_root=cli_root,
                output_root=output_root,
                max_pack_images=max_pack_images,
                attribute_frames=attribute_frames,
            )
        except PackageBuildSkipped as exc:
            LOGGER.warning(
                "Skipped retailer/category package: %s / %s (%s)",
                retailer_key,
                category_key,
                exc,
            )
            summary_rows.append(
                {
                    "retailer": retailer_key,
                    "category_key": category_key,
                    "status": "skipped",
                    "output_dir": None,
                    "package_zip": None,
                    "error": str(exc),
                }
            )
            continue
        except Exception as exc:
            LOGGER.exception(
                "Failed to build retailer/category package: %s / %s",
                retailer_key,
                category_key,
            )
            summary_rows.append(
                {
                    "retailer": retailer_key,
                    "category_key": category_key,
                    "status": "failed",
                    "output_dir": None,
                    "package_zip": None,
                    "error": str(exc),
                }
            )
            if fail_fast:
                break
            continue

        summary_rows.append(
            {
                "retailer": retailer_key,
                "category_key": category_key,
                "status": "built",
                "output_dir": str(output_dir),
                "package_zip": str(_package_zip_path(output_dir)),
                "error": None,
            }
        )

    return pl.DataFrame(
        summary_rows,
        schema={
            "retailer": pl.Utf8,
            "category_key": pl.Utf8,
            "status": pl.Utf8,
            "output_dir": pl.Utf8,
            "package_zip": pl.Utf8,
            "error": pl.Utf8,
        },
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    load_env_from_secrets_file()
    if args.categories:
        if len(args.categories) == 1:
            category_key = args.categories[0]
            try:
                output_dir = build_pack(
                    retailer=args.retailer,
                    category_key=category_key,
                    run_dir=args.run_dir,
                    pdp_store_path=args.pdp_store_path,
                    cli_root=args.cli_root,
                    output_root=args.output_root,
                    max_pack_images=args.max_pack_images,
                )
            except PackageBuildSkipped as exc:
                LOGGER.warning(
                    "Skipped retailer/category package: %s / %s (%s)",
                    args.retailer,
                    category_key,
                    exc,
                )
                return 0
            print(output_dir)
            return 0

        summary = build_all_packs(
            pdp_store_path=args.pdp_store_path,
            cli_root=args.cli_root,
            output_root=args.output_root,
            retailer=args.retailer,
            category_keys=args.categories,
            run_dir=args.run_dir,
            fail_fast=args.fail_fast,
            max_pack_images=args.max_pack_images,
        )
    else:
        summary = build_all_packs(
            pdp_store_path=args.pdp_store_path,
            cli_root=args.cli_root,
            output_root=args.output_root,
            retailer=args.retailer,
            run_dir=args.run_dir,
            fail_fast=args.fail_fast,
            max_pack_images=args.max_pack_images,
        )

    summary_path = args.summary_path or (
        args.output_root
        / "_bulk_rebuild_summary"
        / _canonical_package_retailer_key(args.retailer)
    ).with_suffix(".csv")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.write_csv(summary_path)
    failed_count = summary.filter(pl.col("status") == "failed").height
    built_count = summary.filter(pl.col("status") == "built").height
    skipped_count = summary.filter(pl.col("status") == "skipped").height
    LOGGER.info(
        "Retailer/category package rebuild complete: built=%s skipped=%s failed=%s summary=%s",
        built_count,
        skipped_count,
        failed_count,
        summary_path,
    )
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
