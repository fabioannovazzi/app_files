from __future__ import annotations

import argparse
import html
import io
import json
import logging
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import polars as pl
from rapidfuzz import fuzz

from modules.add_attributes.pdp_attribute_export import _deserialize_frame
from modules.pdp.postgres_compat import is_postgres_enabled
from modules.pdp.review_constants import (
    DEFAULT_PDP_STORE_PATH,
    enforce_default_pdp_store_path,
)
from modules.pdp.signal_quality import (
    signal_component_family,
)
from modules.pdp.signal_quality import (
    signal_insight_metadata as category_signal_insight_metadata,
)
from modules.pdp.store import PDPStore
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = ["build_all_packages", "build_package", "main"]

LOGGER = logging.getLogger(__name__)

DEFAULT_CLI_ROOT = Path("data/pdp/cli")
DEFAULT_INNOVATION_ROOT = Path("data/pdp/reports/packages/launch")
DEFAULT_BRIEF_ROOT = Path("data/pdp/reports/briefs/launch")
DEFAULT_OUTPUT_ROOT = Path("data/pdp/reports/packages/brand_fit")
CSV_LIST_SEPARATOR = " | "
IMAGE_PREVIEW_MAX_DIMENSION = 1200
IMAGE_PREVIEW_QUALITY = 82
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 20
IMAGE_DOWNLOAD_MAX_BYTES = 15 * 1024 * 1024
MAX_EXPORTED_REVIEW_SNIPPETS = 5
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
_DATABASE_ATTRIBUTE_CACHE_BY_RETAILER: dict[str, dict[str, pl.DataFrame]] = {}
PURINA_PORTFOLIO_BRAND_ALIASES = {
    "fancy feast",
    "friskies",
    "pro plan",
    "pro plan veterinary diets",
    "purina one",
    "purina pro plan",
    "purina pro plan veterinary diets",
}
PRODUCT_NAME_CANDIDATES = ["product_name", "title_normalized", "title_raw", "name"]
BRAND_CANDIDATES = ["brand", "brand_normalized", "brand_raw"]
CORE_PRODUCT_COLUMNS = [
    "source",
    "product_scope",
    "product_name",
    "product_key",
    "parent_product_id",
    "pdp_url",
    "brand",
    "category_key",
    "variant_count",
    "image_file",
]
ANCHOR_OUTPUT_EXTRA_COLUMNS = [
    "owned_product_name",
    "owned_parent_product_id",
    "owned_pdp_url",
    "product_identity_match_method",
    "product_identity_match_score",
    "product_identity_match_margin",
]
PRODUCT_ATTRIBUTE_COLUMNS = [
    "form",
    "finish",
    "finish effect",
    "coverage",
    "color payoff",
    "benefits",
    "skin benefits",
    "product type",
    "color",
    "color lips",
    "color family",
    "color_family",
    "shade family",
    "wear claims",
    "preference",
    "ethical/regulatory claims",
    "base formula",
    "packaging type",
    "applicator type",
    "variant_color_family",
    "variant_shade_family",
    "variant_shade_names",
    "variant_finish",
    "variant_coverage",
    "variant_form",
    "variant_benefits",
    "variant_wear_claims",
    "variant_package_count",
    "variant_packaging_type",
    "closure",
    "material",
    "design_detail",
    "usage_context",
    "silhouette",
    "sole type",
    "toe shape",
    "fit note",
    "garment type",
    "garment_type",
    "knit_detail",
    "neckline",
    "sleeve_length",
    "style",
    "flavor",
    "food_texture",
    "food texture",
    "lifestage",
    "special_diet",
    "special diet",
    "health_feature",
    "health feature",
    "package_count",
    "package count",
    "packaging_type",
    "product_assortment",
    "product assortment",
    "prescription_status",
    "animal_protein_source",
    "animal protein source",
    "brand_line",
]
PACKAGE_INTEGRITY_ATTRIBUTE_COLUMNS = [
    "form",
    "finish",
    "finish effect",
    "coverage",
    "color payoff",
    "benefits",
    "skin benefits",
    "product type",
    "color",
    "color lips",
    "color family",
    "color_family",
    "shade family",
    "wear claims",
    "preference",
    "ethical/regulatory claims",
    "base formula",
    "packaging type",
    "applicator type",
]
REVIEW_OUTPUT_SCHEMA = {
    "rating": pl.Float64,
    "review_count": pl.Int64,
    "review_snippet_count": pl.Int64,
    "reviews_json": pl.Utf8,
    "reviews_positive_headline": pl.Utf8,
    "reviews_positive_comment": pl.Utf8,
    "reviews_negative_headline": pl.Utf8,
    "reviews_negative_comment": pl.Utf8,
}
for _review_index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1):
    REVIEW_OUTPUT_SCHEMA[f"review_{_review_index}_headline"] = pl.Utf8
    REVIEW_OUTPUT_SCHEMA[f"review_{_review_index}_comment"] = pl.Utf8
    REVIEW_OUTPUT_SCHEMA[f"review_{_review_index}_rating"] = pl.Float64
    REVIEW_OUTPUT_SCHEMA[f"review_{_review_index}_created_date"] = pl.Utf8
REVIEW_OUTPUT_SCHEMA["review_evidence_source_file"] = pl.Utf8
REVIEW_OUTPUT_COLUMNS = list(REVIEW_OUTPUT_SCHEMA)
REVIEW_SOURCE_FILE_CANDIDATES = (
    "product_filter_matrix.csv",
    "top_seller_products.csv",
    "recent_products.csv",
)
PRODUCT_EVIDENCE_SOURCE_FILE_CANDIDATES = (
    "product_filter_matrix.csv",
    "top_seller_products.csv",
    "recent_products.csv",
)
PRODUCT_EVIDENCE_ATTRIBUTE_COLUMNS = {
    "form": (
        "resolved_form",
        "form",
        "filter_form",
        "ulta_form",
        "mapped_form",
        "rollup_form",
        "format",
        "form_children",
        "format_children",
    ),
    "finish": (
        "resolved_finish",
        "finish",
        "filter_finish",
        "ulta_finish",
        "mapped_finish",
        "rollup_finish",
        "finish types present",
        "finish mix",
    ),
    "finish effect": (
        "finish effect",
        "finish_effect",
    ),
    "coverage": (
        "resolved_coverage",
        "coverage",
        "filter_coverage",
        "ulta_coverage",
        "mapped_coverage",
        "rollup_coverage",
        "color payoff",
        "buildable coverage",
    ),
    "color payoff": (
        "color payoff",
        "buildable coverage",
    ),
    "benefits": (
        "benefits",
        "skin benefits",
        "key benefits",
        "benefits/claims",
        "benefits (claims)",
        "benefits_claims",
        "performance benefits (care)",
        "performance_benefits_care",
        "performance benefits (control)",
        "performance_benefits_control",
    ),
    "skin benefits": (
        "skin benefits",
        "benefits",
        "key benefits",
        "benefits/claims",
        "benefits (claims)",
        "benefits_claims",
        "performance benefits (care)",
        "performance_benefits_care",
    ),
    "product type": (
        "product type",
        "product_type",
        "format",
    ),
    "color": (
        "resolved_color",
        "color",
        "filter_color",
        "available_color_families",
        "available_color_family",
        "color family",
        "color_family",
        "shade family",
    ),
    "color lips": (
        "resolved_color",
        "color lips",
        "color",
        "filter_color",
        "available_color_families",
        "color family",
        "color_family",
    ),
    "color family": (
        "available_color_families",
        "available_color_family",
        "resolved_color",
        "color family",
        "color_family",
        "shade family",
        "color",
        "filter_color",
    ),
    "color_family": (
        "available_color_families",
        "available_color_family",
        "resolved_color",
        "color_family",
        "color family",
        "shade family",
        "color",
        "filter_color",
    ),
    "shade family": (
        "shade family",
        "available_color_families",
        "available_color_family",
        "resolved_color",
        "color family",
        "color_family",
    ),
    "wear claims": (
        "wear claims",
        "resistance/transfer claims",
        "transfer/smudge resistance",
        "performance claims",
        "performance_claims",
        "variant_wear_claims",
    ),
    "preference": (
        "preference",
        "ethical/regulatory claims",
        "regulatory claims",
        "ethical claims",
        "free from",
    ),
    "ethical/regulatory claims": (
        "ethical/regulatory claims",
        "regulatory claims",
        "ethical claims",
        "preference",
        "free from",
    ),
    "base formula": (
        "base formula",
        "formula base",
        "formula type",
        "formula_type",
        "formulation type",
        "formulation_type",
    ),
    "packaging type": (
        "packaging type",
        "packaging_type",
        "packaging features",
        "packaging_features",
    ),
    "applicator type": (
        "applicator type",
        "applicator_type",
    ),
}
LIVE_RETAILER_AUDIT_SCHEMA = {
    "owned_product_name": pl.Utf8,
    "owned_product_key": pl.Utf8,
    "owned_parent_product_id": pl.Utf8,
    "package_anchor_present_before_live_check": pl.Boolean,
    "live_brand_page_present": pl.Boolean,
    "live_brand_page_product_name": pl.Utf8,
    "live_brand_page_url": pl.Utf8,
    "live_added_to_retailer_products": pl.Boolean,
    "live_removed_from_retailer_products": pl.Boolean,
    "audit_status": pl.Utf8,
    "audit_note": pl.Utf8,
}
TIKICAT_CHEWY_MATCH_MIN_SCORE = 76.0
TIKICAT_CHEWY_MATCH_HIGH_CONFIDENCE_SCORE = 85.0
TIKICAT_CHEWY_MATCH_MIN_MARGIN = 1.5
GENERIC_PRODUCT_MATCH_MIN_SCORE = 92.0
GENERIC_PRODUCT_MATCH_HIGH_CONFIDENCE_SCORE = 97.0
GENERIC_PRODUCT_MATCH_MIN_MARGIN = 5.0
TIKICAT_CHEWY_GENERIC_MATCH_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "bag",
        "bags",
        "box",
        "boxes",
        "can",
        "canned",
        "cans",
        "case",
        "cat",
        "count",
        "ct",
        "entree",
        "food",
        "foods",
        "for",
        "formula",
        "formulas",
        "free",
        "grain",
        "in",
        "lifestage",
        "meal",
        "natural",
        "of",
        "ounce",
        "ounces",
        "oz",
        "pack",
        "packs",
        "pouch",
        "pouches",
        "premium",
        "recipe",
        "recipes",
        "replacement",
        "replacer",
        "the",
        "tiki",
        "tray",
        "trays",
        "wet",
        "with",
    }
)
TIKICAT_CHEWY_COLLECTION_TERMS = {
    "after_dark": ("after dark", "after-dark"),
    "baby": ("baby", "kitten", "kittens"),
    "friends": ("aloha friends", "friends mousse", "friends"),
    "gelee": ("gelee", "gelée"),
    "grill": ("grill", "king kamehameha"),
    "luau": ("luau",),
    "silver": ("silver",),
    "solutions": ("solutions", "veterinary"),
    "velvet": ("velvet",),
}
TIKICAT_CHEWY_STRONG_COLLECTIONS = frozenset(
    {"after_dark", "baby", "friends", "grill", "luau", "silver", "solutions"}
)
TIKICAT_CHEWY_TEXTURE_TERMS = {
    "gelee": ("gelee", "gelée"),
    "liquid": ("liquid", "milk"),
    "mousse": ("mousse",),
    "pate": ("pate", "paté"),
    "puree": ("puree", "purée"),
    "shredded": ("bits", "flaked", "minced", "shredded", "shreds"),
}
TIKICAT_CHEWY_INGREDIENT_SYNONYMS = {
    "oceanwhitefish": "whitefish",
    "prawn": "shrimp",
    "prawns": "shrimp",
    "sardines": "sardine",
}
TIKICAT_CHEWY_INGREDIENT_TOKENS = frozenset(
    {
        "beef",
        "calamari",
        "cheese",
        "chicken",
        "crab",
        "duck",
        "egg",
        "fish",
        "goat",
        "herring",
        "lamb",
        "liver",
        "lobster",
        "mackerel",
        "milk",
        "pork",
        "pumpkin",
        "quail",
        "rabbit",
        "salmon",
        "sardine",
        "seabass",
        "seafood",
        "shrimp",
        "tilapia",
        "tuna",
        "turkey",
        "venison",
        "whitefish",
    }
)
TIKICAT_CHEWY_VARIETY_TOKENS = frozenset(
    {"craves", "favorites", "mega", "selects", "variety"}
)
ULTA_BRAND_SLUG_OVERRIDES = {
    "l oreal": "loreal",
    "l oreal paris": "loreal",
    "loreal": "loreal",
    "loreal paris": "loreal",
}
ULTA_CATEGORY_FILTER_PATHS = {
    "blush": "makeup,face,blush",
    "bronzer": "makeup,face,bronzer",
}
VARIANT_ROLLUP_COLUMNS = {
    "color family": "variant_color_family",
    "shade family": "variant_shade_family",
    "shade_name_normalized": "variant_shade_names",
    "finish": "variant_finish",
    "coverage": "variant_coverage",
    "form": "variant_form",
    "format": "variant_form",
    "benefits": "variant_benefits",
    "wear claims": "variant_wear_claims",
    "package count": "variant_package_count",
    "package_count": "variant_package_count",
    "packaging type": "variant_packaging_type",
    "packaging_type": "variant_packaging_type",
}
ATTRIBUTE_CANDIDATE_COLUMNS = {
    "color": [
        "resolved_color",
        "color",
        "color lips",
        "color family",
        "color_family",
        "shade family",
        "variant_color_family",
        "variant_shade_family",
        "variant_shade_names",
    ],
    "color lips": [
        "resolved_color",
        "color lips",
        "color",
        "color family",
        "color_family",
        "shade family",
        "variant_color_family",
        "variant_shade_family",
        "variant_shade_names",
    ],
    "coverage": [
        "resolved_coverage",
        "coverage",
        "color payoff",
        "buildable coverage",
        "variant_coverage",
    ],
    "finish": ["resolved_finish", "finish", "finish effect", "variant_finish"],
    "form": [
        "resolved_form",
        "form",
        "format",
        "product type",
        "applicator type",
        "variant_form",
        "product_name",
    ],
    "product type": [
        "product type",
        "form",
        "format",
        "resolved_form",
        "variant_form",
        "product_name",
    ],
    "preference": [
        "preference",
        "ethical/regulatory claims",
        "regulatory claims",
        "ethical claims",
        "free from",
    ],
    "claims": [
        "preference",
        "ethical/regulatory claims",
        "regulatory claims",
        "ethical claims",
        "free from",
    ],
    "benefits": ["benefits", "primary benefits", "benefits/claims", "variant_benefits"],
    "wear claims": [
        "wear claims",
        "resistance/transfer claims",
        "transfer/smudge resistance",
        "variant_wear_claims",
    ],
    "closure": ["closure", "product_name"],
    "material": ["material", "upper material", "product_name"],
    "design detail": ["design detail", "design_detail", "product_name"],
    "usage context": ["usage context", "usage_context"],
    "silhouette": ["silhouette", "product_name"],
    "sole type": ["sole type", "sole_type", "product_name"],
    "toe shape": ["toe shape", "toe_shape", "product_name"],
    "fit note": ["fit note", "fit_note"],
}
ONE_HOT_ATTRIBUTE_PREFIXES = {
    "material": "material",
    "design_detail": "design_detail",
    "usage_context": "usage_context",
}
SIGNAL_SOURCE_CONFIG = [
    ("winning_now", "top_seller_pairs.csv", "pair"),
    ("winning_now", "top_seller_triples.csv", "triple"),
    ("innovation", "innovation_pairs.csv", "pair"),
    ("innovation", "innovation_triples.csv", "triple"),
]
SIGNAL_LAYER_ORDER = {"winning_now": 0, "innovation": 1}
SIGNAL_IMAGE_REFERENCE_COLUMNS = [
    "top_seller_example_products",
    "top_seller_top_pareto_products",
    "recent_example_products",
    "recent_top_pareto_products",
    "rank_weighted_visibility_top_products",
]
SOURCE_WEB_SHELF_ARTIFACTS = (
    ("web_shelf_selected_shelves.csv", "source_web_shelf_selected_shelves.csv"),
    ("web_shelf_candidate_shelves.csv", "source_web_shelf_candidate_shelves.csv"),
    (
        "web_shelf_robustness_summary.csv",
        "source_web_shelf_robustness_summary.csv",
    ),
    (
        "web_shelf_product_assignments.csv",
        "source_web_shelf_product_assignments.csv",
    ),
    (
        "web_shelf_third_attribute_refinements.csv",
        "source_web_shelf_third_attribute_refinements.csv",
    ),
)
SOURCE_WEB_SHELF_ARTIFACT_ROW_KEYS = {
    "source_web_shelf_selected_shelves.csv": "web_shelf_selected_rows",
    "source_web_shelf_candidate_shelves.csv": "web_shelf_candidate_rows",
    "source_web_shelf_product_assignments.csv": "web_shelf_product_assignment_rows",
    "source_web_shelf_third_attribute_refinements.csv": "web_shelf_refinement_rows",
}
SOURCE_WEB_SHELF_SUMMARY_ROW_KEYS = (
    "web_shelf_selected_rows",
    "web_shelf_candidate_rows",
    "web_shelf_refinement_rows",
    "web_shelf_product_assignment_rows",
    "top_seller_pair_rank_weighted_visibility_rows",
    "top_seller_triple_rank_weighted_visibility_rows",
    "innovation_pair_rank_weighted_visibility_rows",
    "innovation_triple_rank_weighted_visibility_rows",
)
SOURCE_REVIEW_EVIDENCE_ARTIFACTS = (
    (
        "review_theme_cohort_comparison.csv",
        "source_review_theme_cohort_comparison.csv",
        "review_theme_cohort_comparison_rows",
    ),
    (
        "top_seller_review_validation.csv",
        "source_top_seller_review_validation.csv",
        "top_seller_review_validation_rows",
    ),
    (
        "bundle_review_validation.csv",
        "source_bundle_review_validation.csv",
        "bundle_review_validation_rows",
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Brand Fit package that translates an existing retailer "
            "innovation package into brand-retailer reference opportunities."
        )
    )
    parser.add_argument("--brand-source-retailer", required=True)
    parser.add_argument("--brand-name", required=True)
    parser.add_argument(
        "--category",
        dest="categories",
        action="append",
        default=None,
        help=(
            "Retailer/category key to build. Repeat to build selected categories. "
            "Omit categories to build every source package for --retailer."
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
        "--owned-category-key",
        action="append",
        default=None,
        help=(
            "Manufacturer/catalog category_key to include. Repeat for aliases; "
            "defaults to --category."
        ),
    )
    parser.add_argument("--retailer", required=True)
    parser.add_argument("--innovation-package-dir", type=Path, default=None)
    parser.add_argument("--innovation-brief-path", type=Path, default=None)
    parser.add_argument(
        "--owned-cli-dir",
        type=Path,
        action="append",
        default=None,
        help=(
            "Manufacturer CLI directory used for product images. Repeat when a "
            "package combines source categories."
        ),
    )
    parser.add_argument(
        "--retailer-category-key",
        action="append",
        default=None,
        help=(
            "Retailer category_key to include. Repeat for aliases; defaults to "
            "--category."
        ),
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-bundles-per-layer", type=int, default=24)
    parser.add_argument("--max-reference-candidates", type=int, default=16)
    parser.add_argument(
        "--skip-retailer-live-check",
        action="store_true",
        help=(
            "Skip the retailer brand-page presence check before finalizing "
            "current brand-at-retailer anchors."
        ),
    )
    parser.add_argument(
        "--retailer-live-check-timeout",
        type=float,
        default=12.0,
        help="Network timeout, in seconds, for the retailer brand-page check.",
    )
    parser.add_argument(
        "--allow-missing-brand-images",
        action="store_true",
        help=(
            "Allow a package to be written even when no brand/manufacturer images "
            "are available for reference candidates. By default this fails loudly "
            "because Pro and NotebookLM depend on those images for visual checks."
        ),
    )
    return parser.parse_args()


def _columns(df: pl.DataFrame) -> list[str]:
    columns, _schema = get_schema_and_column_names(df)
    return columns


def _slug(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError(f"{field_name} must contain a path-safe value.")
    return normalized


def _package_output_dir(
    output_root: Path,
    *,
    brand_source_retailer: str,
    retailer: str,
    category_key: str,
) -> Path:
    return (
        output_root
        / _slug(category_key, field_name="category")
        / _slug(retailer, field_name="retailer")
        / _slug(brand_source_retailer, field_name="brand_source_retailer")
    )


def _package_zip_path(output_dir: Path) -> Path:
    category = _slug(output_dir.parent.parent.name, field_name="category")
    retailer = _slug(output_dir.parent.name, field_name="retailer")
    brand = _slug(output_dir.name, field_name="brand_source_retailer")
    return output_dir.parent / f"{category}_{retailer}_{brand}.zip"


def _bulk_summary_path(
    output_root: Path,
    *,
    brand_source_retailer: str,
    retailer: str,
) -> Path:
    return (
        output_root
        / "_bulk_rebuild_summary"
        / _slug(retailer, field_name="retailer")
        / f"{_slug(brand_source_retailer, field_name='brand_source_retailer')}.csv"
    )


def _selected_category_keys(args: argparse.Namespace) -> list[str] | None:
    categories: list[str] = []
    for category in args.categories or []:
        categories.append(str(category))
    for group in args.category_groups or []:
        categories.append(str(group))
    if not categories:
        return None
    seen: set[str] = set()
    ordered: list[str] = []
    for category in categories:
        category_key = _slug(category, field_name="category")
        if category_key in seen:
            continue
        seen.add(category_key)
        ordered.append(category_key)
    return ordered


def _source_package_categories(retailer: str) -> list[str]:
    retailer_slug = _slug(retailer, field_name="retailer")
    root = DEFAULT_INNOVATION_ROOT
    if not root.exists():
        raise FileNotFoundError(
            f"Retailer source package directory does not exist: {root}"
        )
    new_layout_categories = sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / retailer_slug).is_dir()
    )
    if new_layout_categories:
        return new_layout_categories

    legacy_root = root / retailer_slug
    if not legacy_root.exists():
        raise FileNotFoundError(
            "Retailer source package directory does not exist in either "
            f"layout: {root}/<category>/{retailer_slug} or {legacy_root}"
        )
    return sorted(path.name for path in legacy_root.iterdir() if path.is_dir())


def _prepare_output_dir(
    output_root: Path,
    *,
    brand_source_retailer: str,
    retailer: str,
    category_key: str,
) -> Path:
    output_dir = _clear_existing_output_dir(
        output_root,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _clear_existing_output_dir(
    output_root: Path,
    *,
    brand_source_retailer: str,
    retailer: str,
    category_key: str,
) -> Path:
    output_dir = _package_output_dir(
        output_root,
        brand_source_retailer=brand_source_retailer,
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


def _innovation_package_dir(retailer: str, category_key: str) -> Path:
    retailer_slug = _slug(retailer, field_name="retailer")
    category_slug = _slug(category_key, field_name="category")
    new_layout = DEFAULT_INNOVATION_ROOT / category_slug / retailer_slug
    legacy_layout = DEFAULT_INNOVATION_ROOT / retailer_slug / category_slug
    if legacy_layout.exists() and not new_layout.exists():
        return legacy_layout
    return new_layout


def _innovation_brief_path(retailer: str, category_key: str) -> Path:
    retailer_slug = _slug(retailer, field_name="retailer")
    category_slug = _slug(category_key, field_name="category")
    new_layout = DEFAULT_BRIEF_ROOT / category_slug / f"{retailer_slug}.md"
    legacy_layout = DEFAULT_BRIEF_ROOT / retailer_slug / f"{category_slug}.md"
    if legacy_layout.exists() and not new_layout.exists():
        return legacy_layout
    return new_layout


def _default_owned_cli_dir(brand_source_retailer: str, category_key: str) -> Path:
    return DEFAULT_CLI_ROOT / (
        f"{_slug(brand_source_retailer, field_name='brand_source_retailer')}_"
        f"{_slug(category_key, field_name='category')}"
    )


def _filter_database_cache_retailer(
    frame: pl.DataFrame,
    *,
    retailer: str,
) -> pl.DataFrame:
    if frame.is_empty() or "retailer" not in frame.columns:
        return frame
    return frame.filter(
        pl.col("retailer")
        .cast(pl.Utf8, strict=False)
        .str.strip_chars()
        .str.to_lowercase()
        == retailer
    )


def _load_pdp_database_attribute_cache_for_retailer(
    retailer: str,
) -> dict[str, pl.DataFrame]:
    cached = _DATABASE_ATTRIBUTE_CACHE_BY_RETAILER.get(retailer)
    if cached is not None:
        return cached
    if not is_postgres_enabled():
        raise RuntimeError(
            "Brand Fit package generation requires the PDP database. "
            "Set PDP_DATABASE_URL or PDP_STORE_BACKEND=postgres with DATABASE_URL."
        )

    store_path = enforce_default_pdp_store_path(DEFAULT_PDP_STORE_PATH)
    store = PDPStore(store_path)
    entries = store.read_attribute_cache_entries()
    if not entries:
        raise FileNotFoundError("PDP database attribute cache is empty.")

    def _load_required_frame(entry_name: str) -> pl.DataFrame:
        payload = entries.get(entry_name)
        if payload is None:
            raise FileNotFoundError(
                f"PDP database attribute cache is missing '{entry_name}'."
            )
        return _deserialize_frame(payload[0])

    parents = _load_required_frame("parent_filtered")
    variants = _load_required_frame("variant_result")
    combined = _load_required_frame("combined")
    parents_all = _load_required_frame("parents_all")
    tables = {
        "parents": _filter_database_cache_retailer(parents, retailer=retailer),
        "variants": _filter_database_cache_retailer(variants, retailer=retailer),
        "combined": _filter_database_cache_retailer(combined, retailer=retailer),
        "parents_all": _filter_database_cache_retailer(
            parents_all,
            retailer=retailer,
        ),
    }
    _DATABASE_ATTRIBUTE_CACHE_BY_RETAILER[retailer] = tables
    return tables


def _load_database_catalog_products(
    *,
    source_label: str,
    category_key: str,
    category_keys: Sequence[str] | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    retailer = _normalized_retailer_key(source_label)
    tables = _load_pdp_database_attribute_cache_for_retailer(retailer)
    keys = category_keys or (category_key,)
    parents = _filter_category(tables["parents"], keys)
    variants = _filter_category(tables["variants"], keys)
    LOGGER.info(
        "Loaded PDP catalog from database cache: source=%s category_keys=%s parents=%s variants=%s",
        source_label,
        CSV_LIST_SEPARATOR.join(str(key) for key in keys),
        get_row_count(parents),
        get_row_count(variants),
    )
    return parents, variants


def _read_csv_if_exists(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return pl.read_csv(path, infer_schema_length=10000)


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _require_source_package_integrity(innovation_package_dir: Path) -> dict[str, Any]:
    path = innovation_package_dir / "package_integrity.json"
    if not path.exists():
        raise RuntimeError(
            "Brand Fit package generation requires a validated source retailer "
            f"package. Missing source package_integrity.json: {path}. Rebuild the "
            "retailer package before building Brand Fit."
        )
    payload = _read_json_if_exists(path)
    status = _meaningful_text(payload.get("status"))
    if status is None or status == "fail":
        raise RuntimeError(
            "Brand Fit package generation requires a source retailer package "
            f"with package_integrity status pass or pass_with_warnings. {path} "
            f"status={status or 'missing'}."
        )
    return payload


def _require_source_package_snapshot_manifest(
    innovation_package_dir: Path,
    source_innovation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    path = innovation_package_dir / "source_snapshots" / "source_manifest.json"
    if path.exists():
        return _read_json_if_exists(path)
    summary_manifest = source_innovation_summary.get("source_snapshot_manifest")
    if isinstance(summary_manifest, Mapping) and summary_manifest:
        return dict(summary_manifest)
    raise RuntimeError(
        "Brand Fit package generation requires source retailer package snapshots "
        f"for product-matrix provenance. Missing {path}. Rebuild the retailer "
        "package with source snapshots before building Brand Fit."
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def _meaningful_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in PLACEHOLDER_VALUES:
        return None
    return text


def _repair_mojibake_text(text: str) -> str:
    """Repair common UTF-8-as-Latin-1 text without touching clean strings."""

    mojibake_markers = ("\u00c3", "\u00c2", "\u00e2")
    if not any(marker in text for marker in mojibake_markers):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    original_markers = sum(text.count(marker) for marker in mojibake_markers)
    repaired_markers = sum(repaired.count(marker) for marker in mojibake_markers)
    return repaired if repaired_markers < original_markers else text


def _normalize_search_text(value: Any) -> str:
    text = _meaningful_text(value)
    if text is None:
        return ""
    text = _repair_mojibake_text(text)
    normalized = unicodedata.normalize("NFKD", text)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.casefold()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_product_key(value: Any) -> str | None:
    normalized = _normalize_search_text(value).replace("colour", "color")
    return normalized or None


def _normalized_retailer_key(value: Any) -> str:
    return _normalize_product_key(value) or ""


def _normalize_web_slug(value: Any) -> str | None:
    normalized = _normalize_search_text(value)
    if not normalized:
        return None
    return normalized.replace(" ", "-")


def _brand_key_aliases(value: Any) -> set[str]:
    key = _normalize_product_key(value)
    if key is None:
        return set()
    aliases = {key}
    compact = key.replace(" ", "")
    if key.endswith(" paris"):
        aliases.add(key.removesuffix(" paris").strip())
    if compact in {"loreal", "lorealparis"}:
        aliases.update({"l oreal", "l oreal paris", "loreal", "loreal paris"})
    if key == "purina":
        aliases.update(PURINA_PORTFOLIO_BRAND_ALIASES)
    return {alias for alias in aliases if alias}


def _iter_match_text_parts(value: Any) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if _meaningful_text(item) is not None)
    return (str(value),) if _meaningful_text(value) is not None else ()


def _tikicat_chewy_match_text(row: Mapping[str, Any]) -> str:
    columns = (
        "product_name",
        "retailer_product_name",
        "owned_product_name",
        "parent_product_id",
        "retailer_parent_product_id",
        "owned_parent_product_id",
        "pdp_url",
        "retailer_pdp_url",
        "owned_pdp_url",
        "category_path",
        "raw_category_path",
        "flavor",
        "food_texture",
        "food texture",
        "health_feature",
        "health feature",
        "lifestage",
        "product_assortment",
        "product assortment",
    )
    parts: list[str] = []
    for column in columns:
        for part in _iter_match_text_parts(row.get(column)):
            parts.append(part)
    normalized = _normalize_search_text(" ".join(parts))
    normalized = normalized.replace("ocean whitefish", "whitefish")
    normalized = normalized.replace("consomme", "broth")
    for source, replacement in TIKICAT_CHEWY_INGREDIENT_SYNONYMS.items():
        normalized = re.sub(rf"\b{re.escape(source)}\b", replacement, normalized)
    return normalized


def _tikicat_chewy_match_features(row: Mapping[str, Any]) -> dict[str, Any]:
    text = _tikicat_chewy_match_text(row)
    tokens = [
        token
        for token in text.split()
        if len(token) > 1
        and not token.isdigit()
        and token not in TIKICAT_CHEWY_GENERIC_MATCH_TOKENS
    ]
    token_set = frozenset(tokens)
    collections = frozenset(
        collection
        for collection, terms in TIKICAT_CHEWY_COLLECTION_TERMS.items()
        if any(term in text for term in terms)
    )
    textures = frozenset(
        texture
        for texture, terms in TIKICAT_CHEWY_TEXTURE_TERMS.items()
        if any(term in text for term in terms)
    )
    ingredients = frozenset(
        token for token in tokens if token in TIKICAT_CHEWY_INGREDIENT_TOKENS
    )
    variety_tokens = frozenset(
        token for token in tokens if token in TIKICAT_CHEWY_VARIETY_TOKENS
    )
    return {
        "collections": collections,
        "ingredients": ingredients,
        "stripped_text": " ".join(tokens),
        "textures": textures,
        "tokens": token_set,
        "variety_tokens": variety_tokens,
        "is_variety": bool(variety_tokens),
    }


def _tikicat_chewy_features_compatible(
    retailer_features: Mapping[str, Any],
    owned_features: Mapping[str, Any],
) -> bool:
    retailer_collections = set(retailer_features["collections"])
    owned_collections = set(owned_features["collections"])
    retailer_strong = retailer_collections & TIKICAT_CHEWY_STRONG_COLLECTIONS
    owned_strong = owned_collections & TIKICAT_CHEWY_STRONG_COLLECTIONS
    if retailer_strong and owned_strong and not retailer_strong & owned_strong:
        return False

    retailer_is_variety = bool(retailer_features["is_variety"])
    owned_is_variety = bool(owned_features["is_variety"])
    if retailer_is_variety != owned_is_variety:
        return False
    if retailer_is_variety:
        pack_token_overlap = set(retailer_features["variety_tokens"]) & set(
            owned_features["variety_tokens"]
        )
        ingredient_overlap = set(retailer_features["ingredients"]) & set(
            owned_features["ingredients"]
        )
        if not pack_token_overlap and not ingredient_overlap:
            return False

    retailer_ingredients = set(retailer_features["ingredients"])
    owned_ingredients = set(owned_features["ingredients"])
    if retailer_ingredients and owned_ingredients:
        ingredient_overlap = retailer_ingredients & owned_ingredients
        if not ingredient_overlap:
            return False
        larger_count = max(len(retailer_ingredients), len(owned_ingredients))
        if (
            len(retailer_ingredients) >= 2
            and len(owned_ingredients) >= 2
            and len(ingredient_overlap) / larger_count < 0.5
        ):
            return False
    return True


def _ratio_overlap(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _tikicat_chewy_match_score(
    retailer_features: Mapping[str, Any],
    owned_features: Mapping[str, Any],
) -> float:
    if not _tikicat_chewy_features_compatible(retailer_features, owned_features):
        return -1.0

    retailer_text = str(retailer_features["stripped_text"])
    owned_text = str(owned_features["stripped_text"])
    token_set_score = fuzz.token_set_ratio(retailer_text, owned_text)
    token_sort_score = fuzz.token_sort_ratio(retailer_text, owned_text)
    collection_score = _ratio_overlap(
        set(retailer_features["collections"]),
        set(owned_features["collections"]),
    )
    ingredient_score = _ratio_overlap(
        set(retailer_features["ingredients"]),
        set(owned_features["ingredients"]),
    )
    retailer_textures = set(retailer_features["textures"])
    owned_textures = set(owned_features["textures"])
    texture_score = 0.0
    if retailer_textures and owned_textures:
        texture_score = 1.0 if retailer_textures & owned_textures else -0.2
    variety_score = (
        1.0
        if bool(retailer_features["is_variety"]) == bool(owned_features["is_variety"])
        else 0.0
    )
    return (
        (0.36 * token_set_score)
        + (0.24 * token_sort_score)
        + (18.0 * collection_score)
        + (18.0 * ingredient_score)
        + (5.0 * texture_score)
        + (4.0 * variety_score)
    )


def _use_tikicat_chewy_product_matching(
    *,
    brand_source_retailer: str | None,
    retailer: str | None,
    category_key: str | None,
) -> bool:
    category = _normalized_retailer_key(category_key).replace(" ", "_")
    return (
        _normalized_retailer_key(brand_source_retailer) == "tikicat"
        and _normalized_retailer_key(retailer) == "chewy"
        and category == "wet_cat_food"
    )


def _tikicat_chewy_product_identity_matches(
    owned: pl.DataFrame,
    retailer_anchors: pl.DataFrame,
) -> pl.DataFrame:
    schema = {
        "retailer_parent_product_id": pl.Utf8,
        "owned_product_name": pl.Utf8,
        "owned_parent_product_id": pl.Utf8,
        "owned_pdp_url": pl.Utf8,
        "owned_variant_count": pl.Int64,
        "owned_image_file": pl.Utf8,
        "product_identity_match_method": pl.Utf8,
        "product_identity_match_score": pl.Float64,
        "product_identity_match_margin": pl.Float64,
    }
    if (
        owned.width == 0
        or retailer_anchors.width == 0
        or get_row_count(owned) == 0
        or get_row_count(retailer_anchors) == 0
    ):
        return pl.DataFrame(schema=schema)

    owned_rows = owned.to_dicts()
    retailer_rows = retailer_anchors.to_dicts()
    for row in owned_rows:
        row["_match_features"] = _tikicat_chewy_match_features(row)
    for row in retailer_rows:
        row["_match_features"] = _tikicat_chewy_match_features(row)

    candidates: list[dict[str, Any]] = []
    for retailer_row in retailer_rows:
        scored: list[tuple[float, dict[str, Any]]] = []
        retailer_features = retailer_row["_match_features"]
        for owned_row in owned_rows:
            score = _tikicat_chewy_match_score(
                retailer_features,
                owned_row["_match_features"],
            )
            scored.append((score, owned_row))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            continue
        best_score, best_owned = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else -1.0
        margin = best_score - second_score
        retailer_parent_id = _meaningful_text(
            retailer_row.get("retailer_parent_product_id")
            or retailer_row.get("parent_product_id")
        )
        if retailer_parent_id is None:
            continue
        candidates.append(
            {
                "retailer_parent_product_id": retailer_parent_id,
                "owned_product_name": best_owned.get("product_name"),
                "owned_parent_product_id": best_owned.get("parent_product_id"),
                "owned_pdp_url": best_owned.get("pdp_url"),
                "owned_variant_count": best_owned.get("variant_count"),
                "owned_image_file": best_owned.get("image_file"),
                "product_identity_match_method": "tikicat_chewy_name_line_fuzzy",
                "product_identity_match_score": round(float(best_score), 3),
                "product_identity_match_margin": round(float(margin), 3),
            }
        )

    rows: list[dict[str, Any]] = []
    candidates.sort(
        key=lambda row: (
            float(row["product_identity_match_score"]),
            float(row["product_identity_match_margin"]),
        ),
        reverse=True,
    )
    for row in candidates:
        score = float(row["product_identity_match_score"])
        margin = float(row["product_identity_match_margin"])
        owned_parent_id = _meaningful_text(row.get("owned_parent_product_id"))
        if (
            score < TIKICAT_CHEWY_MATCH_MIN_SCORE
            or (
                margin < TIKICAT_CHEWY_MATCH_MIN_MARGIN
                and score < TIKICAT_CHEWY_MATCH_HIGH_CONFIDENCE_SCORE
            )
            or owned_parent_id is None
        ):
            continue
        rows.append(row)
    return pl.DataFrame(rows, schema=schema)


def _generic_product_match_score(retailer_key: str, owned_key: str) -> float:
    if retailer_key == owned_key:
        return 100.0
    token_sort_score = float(fuzz.token_sort_ratio(retailer_key, owned_key))
    token_set_score = float(fuzz.token_set_ratio(retailer_key, owned_key))
    retailer_tokens = set(retailer_key.split())
    owned_tokens = set(owned_key.split())
    smaller_tokens = (
        retailer_tokens if len(retailer_tokens) <= len(owned_tokens) else owned_tokens
    )
    larger_token_count = max(len(retailer_tokens), len(owned_tokens))
    token_coverage = (
        len(retailer_tokens & owned_tokens) / larger_token_count
        if larger_token_count
        else 0.0
    )
    if (
        token_set_score >= 98.0
        and len(smaller_tokens) >= 2
        and smaller_tokens.issubset(retailer_tokens | owned_tokens)
        and smaller_tokens.issubset(retailer_tokens & owned_tokens)
    ):
        return max(token_sort_score, 96.0)
    if token_set_score >= 98.0 and token_coverage >= 0.75:
        return max(token_sort_score, 94.0)
    return token_sort_score


def _product_match_score_is_accepted(best_score: float, margin: float) -> bool:
    return not (
        best_score < GENERIC_PRODUCT_MATCH_MIN_SCORE
        or (
            margin < GENERIC_PRODUCT_MATCH_MIN_MARGIN
            and best_score < GENERIC_PRODUCT_MATCH_HIGH_CONFIDENCE_SCORE
        )
    )


def _generic_product_identity_matches(
    owned: pl.DataFrame,
    retailer_anchors: pl.DataFrame,
) -> pl.DataFrame:
    schema = {
        "retailer_parent_product_id": pl.Utf8,
        "owned_product_name": pl.Utf8,
        "owned_parent_product_id": pl.Utf8,
        "owned_pdp_url": pl.Utf8,
        "owned_variant_count": pl.Int64,
        "owned_image_file": pl.Utf8,
        "product_identity_match_method": pl.Utf8,
        "product_identity_match_score": pl.Float64,
        "product_identity_match_margin": pl.Float64,
    }
    if (
        owned.width == 0
        or retailer_anchors.width == 0
        or get_row_count(owned) == 0
        or get_row_count(retailer_anchors) == 0
    ):
        return pl.DataFrame(schema=schema)

    owned_rows = owned.select(
        [
            "product_key",
            "product_name",
            "parent_product_id",
            "pdp_url",
            "variant_count",
            "image_file",
        ]
    ).to_dicts()
    rows: list[dict[str, Any]] = []
    for retailer_row in retailer_anchors.select(
        ["retailer_parent_product_id", "retailer_product_name", "product_key"]
    ).to_dicts():
        retailer_key = _meaningful_text(retailer_row.get("product_key"))
        if retailer_key is None:
            continue
        scored: list[tuple[float, Mapping[str, Any]]] = []
        for owned_row in owned_rows:
            owned_key = _meaningful_text(owned_row.get("product_key"))
            if owned_key is None:
                continue
            scored.append(
                (
                    _generic_product_match_score(retailer_key, owned_key),
                    owned_row,
                )
            )
        if not scored:
            continue
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_owned = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score
        if not _product_match_score_is_accepted(best_score, margin):
            continue
        rows.append(
            {
                "retailer_parent_product_id": retailer_row.get(
                    "retailer_parent_product_id"
                ),
                "owned_product_name": best_owned.get("product_name"),
                "owned_parent_product_id": best_owned.get("parent_product_id"),
                "owned_pdp_url": best_owned.get("pdp_url"),
                "owned_variant_count": best_owned.get("variant_count"),
                "owned_image_file": best_owned.get("image_file"),
                "product_identity_match_method": "name_token_sort_fuzzy",
                "product_identity_match_score": round(float(best_score), 3),
                "product_identity_match_margin": round(float(margin), 3),
            }
        )
    return pl.DataFrame(rows, schema=schema)


def _brand_stripped_product_key(value: Any, brand_name: str) -> str | None:
    product_key = _normalize_product_key(value)
    if product_key is None:
        return None
    brand_aliases = sorted(_brand_key_aliases(brand_name), key=len, reverse=True)
    for brand_key in brand_aliases:
        if product_key.startswith(f"{brand_key} "):
            stripped = product_key[len(brand_key) + 1 :].strip()
            return stripped or product_key
        compact_brand_key = brand_key.replace(" ", "")
        if compact_brand_key and product_key.startswith(f"{compact_brand_key} "):
            stripped = product_key[len(compact_brand_key) + 1 :].strip()
            return stripped or product_key
    return product_key


def _brand_stripped_product_key_aliases(value: Any, brand_name: str) -> set[str]:
    product_key = _normalize_product_key(value)
    if product_key is None:
        return set()
    keys = {product_key}
    for brand_key in _brand_key_aliases(brand_name):
        if product_key.startswith(f"{brand_key} "):
            stripped = product_key[len(brand_key) + 1 :].strip()
            if stripped:
                keys.add(stripped)
        compact_brand_key = brand_key.replace(" ", "")
        if compact_brand_key and product_key.startswith(f"{compact_brand_key} "):
            stripped = product_key[len(compact_brand_key) + 1 :].strip()
            if stripped:
                keys.add(stripped)
    return keys


def _brand_stripped_product_name(value: Any, brand_name: str) -> str | None:
    text = _meaningful_text(value)
    if text is None:
        return None
    product_key = _normalize_product_key(text)
    if product_key is None:
        return text
    words = text.split()
    for brand_key in sorted(_brand_key_aliases(brand_name), key=len, reverse=True):
        for word_count in range(1, min(len(words), 4) + 1):
            prefix_key = _normalize_product_key(" ".join(words[:word_count]))
            if prefix_key == brand_key:
                stripped = " ".join(words[word_count:]).strip()
                return stripped or text
    brand_text = _meaningful_text(brand_name)
    if brand_text is None:
        return text
    pattern = rf"^\s*{re.escape(brand_text)}\s+"
    stripped = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return stripped or text


def _brand_matches(value: Any, brand_key: str) -> bool:
    normalized = _normalize_product_key(value)
    if normalized is None:
        return False
    aliases = _brand_key_aliases(brand_key)
    if not aliases:
        return False
    return any(alias in normalized or normalized in alias for alias in aliases)


def _filter_brand_if_possible(df: pl.DataFrame, brand_name: str) -> pl.DataFrame:
    brand_column = _first_existing(_columns(df), BRAND_CANDIDATES)
    if brand_column is None:
        return df
    brand_key = _normalize_product_key(brand_name)
    if brand_key is None:
        return df
    return df.filter(
        pl.col(brand_column)
        .cast(pl.Utf8)
        .map_elements(
            lambda value: _brand_matches(value, brand_key),
            return_dtype=pl.Boolean,
        )
    )


def _retailer_brand_listing_url(
    retailer: str,
    brand_name: str,
    category_key: str | None = None,
) -> str | None:
    retailer_key = _normalize_product_key(retailer)
    brand_key = _normalize_product_key(brand_name)
    brand_slug = ULTA_BRAND_SLUG_OVERRIDES.get(brand_key or "") or _normalize_web_slug(
        brand_name
    )
    if retailer_key == "ulta" and brand_slug:
        base_url = f"https://www.ulta.com/brand/{brand_slug}"
        category_filter = ULTA_CATEGORY_FILTER_PATHS.get(
            _normalize_product_key(category_key) or ""
        )
        if category_filter:
            return (
                f"{base_url}?category="
                f"{urllib.parse.quote(category_filter, safe='')}"
            )
        return base_url
    return None


def _fetch_url_text(url: str, *, timeout: float) -> tuple[str | None, str | None]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": (
                "Mozilla/5.0 (compatible; MparanzaBrandFitAudit/1.0; "
                "+https://mparanza.com)"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            encoding = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(encoding, errors="replace"), None
    except urllib.error.HTTPError as exc:
        return None, f"http_error_{exc.code}"
    except urllib.error.URLError as exc:
        return None, f"url_error_{exc.reason}"
    except TimeoutError:
        return None, "timeout"
    except OSError as exc:
        return None, f"os_error_{exc}"


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_html_attribute(tag: str, attribute: str) -> str | None:
    pattern = rf"\b{re.escape(attribute)}\s*=\s*(['\"])(?P<value>.*?)\1"
    match = re.search(pattern, tag, flags=re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    return html.unescape(match.group("value"))


def _parse_ulta_brand_page_products(
    html_text: str,
    *,
    brand_name: str,
) -> dict[str, dict[str, str]]:
    products: dict[str, dict[str, str]] = {}
    anchor_pattern = re.compile(
        r"(?P<tag><a\b[^>]*\bhref\s*=\s*['\"](?:https?://[^'\"]+)?/p/[^'\"]+['\"][^>]*>)"
        r"(?P<body>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    brand_key = _normalize_product_key(brand_name)
    for match in anchor_pattern.finditer(html_text):
        tag = match.group("tag")
        href = _extract_html_attribute(tag, "href")
        if href is None:
            continue
        if href.startswith("/"):
            href = f"https://www.ulta.com{href}"
        if "ulta.com/p/" not in href:
            continue
        label = _extract_html_attribute(tag, "aria-label") or _strip_html(
            match.group("body")
        )
        if not label:
            continue
        if brand_key and not _brand_matches(label, brand_key):
            continue
        product_keys = _brand_stripped_product_key_aliases(label, brand_name)
        url_slug = _ulta_product_slug_from_url(href)
        if url_slug is not None:
            product_keys.update(
                _brand_stripped_product_key_aliases(url_slug, brand_name)
            )
        if not product_keys:
            continue
        live_product = {
            "product_name": _brand_stripped_product_name(label, brand_name) or label,
            "retailer_product_name": label,
            "pdp_url": href,
        }
        for product_key in product_keys:
            products.setdefault(product_key, live_product)
    return products


def _ulta_brand_page_declared_result_count(html_text: str) -> int | None:
    text = _strip_html(html_text).casefold()
    matches = [
        int(match.group("count"))
        for match in re.finditer(r"\b(?P<count>\d+)\s+results\b", text)
    ]
    return matches[0] if matches else None


def _ulta_product_slug_from_url(value: Any) -> str | None:
    text = _meaningful_text(value)
    if text is None:
        return None
    path = urllib.parse.urlparse(text).path
    slug = Path(path).name
    slug = re.sub(
        r"-(?:pimprod|xlsImpprod|prod|mkt|VP)[A-Za-z0-9]+$",
        "",
        slug,
        flags=re.IGNORECASE,
    )
    return _normalize_product_key(slug)


def _retailer_product_id_from_url(value: Any) -> str | None:
    text = _meaningful_text(value)
    if text is None:
        return None
    chewy_match = re.search(r"/dp/(?P<product_id>\d+)(?:[/?#]|$)", text)
    if chewy_match is not None:
        return chewy_match.group("product_id")
    match = re.search(
        r"-(?P<product_id>(?:pimprod|xlsImpprod|prod|mkt)[A-Za-z0-9]+)(?:[/?#]|$)",
        text,
    )
    if match is None:
        return None
    return match.group("product_id")


def _empty_live_retailer_audit_df() -> pl.DataFrame:
    return pl.DataFrame(schema=LIVE_RETAILER_AUDIT_SCHEMA)


def _split_values(value: Any) -> list[str]:
    text = _meaningful_text(value)
    if text is None:
        return []
    parts = re.split(r"\s+\|\s+|[,;]", text)
    return [part.strip() for part in parts if _meaningful_text(part)]


def _is_truthy_one_hot(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def _attribute_token(value: Any) -> str:
    return _normalize_search_text(value).replace(" ", "_")


def _one_hot_label(column_name: str, *, prefix: str) -> str:
    token = column_name.removeprefix(f"{prefix}__")
    return token.replace("_", " ").strip()


def _derive_one_hot_attribute_columns(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    for prefix, output_column in ONE_HOT_ATTRIBUTE_PREFIXES.items():
        one_hot_columns = [
            column for column in df.columns if column.startswith(f"{prefix}__")
        ]
        if not one_hot_columns:
            continue

        def _derive(row: Mapping[str, Any]) -> str | None:
            values = [
                _one_hot_label(column, prefix=prefix)
                for column in one_hot_columns
                if _is_truthy_one_hot(row.get(column))
            ]
            return CSV_LIST_SEPARATOR.join(values) if values else None

        derived = pl.struct(one_hot_columns).map_elements(
            _derive,
            return_dtype=pl.Utf8,
        )
        if output_column in df.columns:
            has_value = pl.col(output_column).map_elements(
                lambda value: _meaningful_text(value) is not None,
                return_dtype=pl.Boolean,
            )
            df = df.with_columns(
                pl.when(has_value)
                .then(pl.col(output_column))
                .otherwise(derived)
                .alias(output_column)
            )
        else:
            df = df.with_columns(derived.alias(output_column))
    return df


def _filter_category(
    df: pl.DataFrame, category_keys: str | Sequence[str]
) -> pl.DataFrame:
    if "category_key" not in _columns(df):
        return df
    if isinstance(category_keys, str):
        keys = [category_keys]
    else:
        keys = [str(key).strip() for key in category_keys if str(key).strip()]
    if not keys:
        return df
    return df.filter(pl.col("category_key").cast(pl.Utf8).is_in(keys))


def _join_unique_values() -> pl.Expr:
    return (
        pl.col("")
        .cast(pl.Utf8)
        .drop_nulls()
        .unique()
        .sort()
        .implode()
        .list.join(CSV_LIST_SEPARATOR)
    )


def _variant_rollups_from_frame(
    variants: pl.DataFrame,
    *,
    source_label: str | None = None,
) -> pl.DataFrame:
    schema = {"parent_product_id": pl.Utf8, "variant_count": pl.Int64}
    if variants.width == 0 or get_row_count(variants) == 0:
        return pl.DataFrame(schema=schema)
    variants = _filter_source_label(variants, source_label=source_label)
    columns = _columns(variants)
    if "parent_product_id" not in columns:
        return pl.DataFrame(schema=schema)
    aggregations: list[pl.Expr] = [pl.len().cast(pl.Int64).alias("variant_count")]
    output_columns: set[str] = {"variant_count"}
    for source_column, output_column in VARIANT_ROLLUP_COLUMNS.items():
        if source_column not in columns:
            continue
        if output_column in output_columns:
            continue
        output_columns.add(output_column)
        aggregations.append(
            pl.col(source_column)
            .cast(pl.Utf8)
            .drop_nulls()
            .unique()
            .sort()
            .implode()
            .list.join(CSV_LIST_SEPARATOR)
            .alias(output_column)
        )
    return variants.group_by("parent_product_id").agg(aggregations)


def _filter_source_label(
    df: pl.DataFrame,
    *,
    source_label: str | None,
) -> pl.DataFrame:
    if source_label is None or "retailer" not in _columns(df):
        return df
    source_key = _normalized_retailer_key(source_label)
    if not source_key:
        return df
    return df.filter(
        pl.col("retailer")
        .cast(pl.Utf8)
        .map_elements(
            lambda value: _normalized_retailer_key(value) == source_key,
            return_dtype=pl.Boolean,
        )
        .fill_null(False)
    )


def _add_standard_columns(
    df: pl.DataFrame,
    *,
    category_key: str,
    source_label: str,
    product_scope: str,
) -> pl.DataFrame:
    columns = _columns(df)
    product_column = _first_existing(columns, PRODUCT_NAME_CANDIDATES)
    brand_column = _first_existing(columns, BRAND_CANDIDATES)
    expressions: list[pl.Expr] = [
        pl.lit(source_label).alias("source"),
        pl.lit(product_scope).alias("product_scope"),
    ]

    if product_column is None:
        expressions.append(pl.lit(None, dtype=pl.Utf8).alias("product_name"))
    elif product_column != "product_name":
        expressions.append(pl.col(product_column).cast(pl.Utf8).alias("product_name"))

    if brand_column is None:
        expressions.append(pl.lit(None, dtype=pl.Utf8).alias("brand"))
    elif brand_column != "brand":
        expressions.append(pl.col(brand_column).cast(pl.Utf8).alias("brand"))

    if "category_key" not in columns:
        expressions.append(pl.lit(category_key).alias("category_key"))
    if "parent_product_id" not in columns:
        expressions.append(pl.lit(None, dtype=pl.Utf8).alias("parent_product_id"))
    if "pdp_url" not in columns:
        expressions.append(pl.lit(None, dtype=pl.Utf8).alias("pdp_url"))
    if "variant_count" not in columns:
        expressions.append(pl.lit(0, dtype=pl.Int64).alias("variant_count"))
    if "image_file" not in columns:
        expressions.append(pl.lit(None, dtype=pl.Utf8).alias("image_file"))
    for column in PRODUCT_ATTRIBUTE_COLUMNS:
        if column not in columns:
            expressions.append(pl.lit(None, dtype=pl.Utf8).alias(column))

    df = df.with_columns(expressions)
    df = _derive_one_hot_attribute_columns(df)
    return df.with_columns(
        pl.col("product_name")
        .map_elements(_normalize_product_key, return_dtype=pl.Utf8)
        .alias("product_key")
    )


def _load_owned_products(
    *,
    category_key: str,
    category_keys: Sequence[str] | None = None,
    source_label: str,
) -> pl.DataFrame:
    raw_parents, raw_variants = _load_database_catalog_products(
        source_label=source_label,
        category_key=category_key,
        category_keys=category_keys,
    )
    parents = _add_standard_columns(
        _filter_category(raw_parents, category_keys or (category_key,)),
        category_key=category_key,
        source_label=source_label,
        product_scope="manufacturer_catalog",
    )
    rollups = _variant_rollups_from_frame(raw_variants, source_label=source_label)
    if get_row_count(rollups) > 0:
        parents = parents.drop("variant_count").join(
            rollups,
            on="parent_product_id",
            how="left",
        )
        parents = parents.with_columns(
            pl.col("variant_count").fill_null(0).cast(pl.Int64)
        )
    return parents.filter(pl.col("product_key").is_not_null())


def _require_owned_products(
    owned: pl.DataFrame,
    *,
    brand_source_retailer: str,
    brand_name: str,
    category_key: str,
    category_keys: Sequence[str] | None,
) -> None:
    if get_row_count(owned) > 0:
        return
    selected_keys = tuple(category_keys or (category_key,))
    category_text = CSV_LIST_SEPARATOR.join(str(key) for key in selected_keys)
    raise ValueError(
        "Brand Fit package generation requires brand catalog products after "
        f"category filtering. brand_source_retailer={brand_source_retailer} "
        f"brand_name={brand_name!r} category_keys={category_text} "
        "source=PDP database"
    )


def _load_retailer_brand_products(
    *,
    category_key: str,
    category_keys: Sequence[str] | None = None,
    brand_name: str,
    source_label: str,
) -> pl.DataFrame:
    products, _variants = _load_database_catalog_products(
        source_label=source_label,
        category_key=category_key,
        category_keys=category_keys,
    )
    products = _filter_category(products, category_keys or (category_key,))
    products = _filter_brand_if_possible(products, brand_name)
    products = _add_standard_columns(
        products,
        category_key=category_key,
        source_label=source_label,
        product_scope="brand_at_retailer",
    )
    return products.filter(pl.col("product_key").is_not_null())


def _live_presence_unavailable_audit(
    owned: pl.DataFrame,
    *,
    retailer_products: pl.DataFrame,
    note: str,
) -> pl.DataFrame:
    existing_retailer_keys = _key_set(retailer_products)
    rows = [
        {
            "owned_product_name": row.get("product_name"),
            "owned_product_key": row.get("product_key"),
            "owned_parent_product_id": row.get("parent_product_id"),
            "package_anchor_present_before_live_check": (
                row.get("product_key") in existing_retailer_keys
            ),
            "live_brand_page_present": False,
            "live_brand_page_product_name": None,
            "live_brand_page_url": None,
            "live_added_to_retailer_products": False,
            "live_removed_from_retailer_products": False,
            "audit_status": "live_check_unavailable",
            "audit_note": note,
        }
        for row in owned.select(_product_output_columns(owned)).to_dicts()
    ]
    if not rows:
        return _empty_live_retailer_audit_df()
    return pl.DataFrame(rows, schema=LIVE_RETAILER_AUDIT_SCHEMA)


def _live_presence_row_from_owned(
    row: Mapping[str, Any],
    *,
    retailer: str,
    brand_name: str,
    category_key: str,
    live_product: Mapping[str, str],
) -> dict[str, Any]:
    output = dict(row)
    output.update(
        {
            "source": retailer,
            "product_scope": "brand_at_retailer",
            "product_name": live_product.get("product_name") or row.get("product_name"),
            "pdp_url": live_product.get("pdp_url") or row.get("pdp_url"),
            "brand": brand_name,
            "category_key": category_key,
        }
    )
    retailer_parent_id = _retailer_product_id_from_url(output.get("pdp_url"))
    if retailer_parent_id is not None:
        output["parent_product_id"] = retailer_parent_id
    return output


def _owned_live_match_keys(row: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for column in ("product_key", "product_name", "parent_product_id"):
        key = _normalize_product_key(row.get(column))
        if key is not None:
            keys.add(key)
    url_slug = _ulta_product_slug_from_url(row.get("pdp_url"))
    if url_slug is not None:
        keys.add(url_slug)
    return keys


def _live_product_match_for_owned(
    row: Mapping[str, Any],
    live_products: Mapping[str, Mapping[str, str]],
) -> Mapping[str, str] | None:
    product_keys = _owned_live_match_keys(row)
    if not product_keys:
        return None
    for product_key in product_keys:
        exact = live_products.get(product_key)
        if exact is not None:
            return exact

    scored_by_live_product: dict[str, tuple[float, Mapping[str, str]]] = {}
    for product_key in product_keys:
        for live_key, live_product in live_products.items():
            score = _generic_product_match_score(live_key, product_key)
            live_identity = _live_product_identity_key(live_product)
            current = scored_by_live_product.get(live_identity)
            if current is None or score > current[0]:
                scored_by_live_product[live_identity] = (score, live_product)
    if not scored_by_live_product:
        return None
    scored = list(scored_by_live_product.values())
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_product = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second_score
    if not _product_match_score_is_accepted(best_score, margin):
        return None
    return best_product


def _live_product_identity_key(row: Mapping[str, str]) -> str:
    return (
        _meaningful_text(row.get("pdp_url"))
        or _meaningful_text(row.get("retailer_product_name"))
        or _meaningful_text(row.get("product_name"))
        or str(id(row))
    )


def _unique_live_product_count(live_products: Mapping[str, Mapping[str, str]]) -> int:
    unique_keys = set()
    for row in live_products.values():
        unique_keys.add(_live_product_identity_key(row))
    return len(unique_keys)


def _product_key_matches_any(
    product_key: str | None,
    candidate_keys: set[str],
) -> bool:
    if product_key is None:
        return False
    if product_key in candidate_keys:
        return True
    scored = [
        _generic_product_match_score(candidate_key, product_key)
        for candidate_key in candidate_keys
    ]
    if not scored:
        return False
    scored.sort(reverse=True)
    best_score = scored[0]
    second_score = scored[1] if len(scored) > 1 else 0.0
    return _product_match_score_is_accepted(best_score, best_score - second_score)


def _audit_live_retailer_presence(
    *,
    owned: pl.DataFrame,
    retailer_products: pl.DataFrame,
    brand_name: str,
    category_key: str,
    retailer: str,
    enabled: bool,
    timeout: float,
    fetcher: Callable[[str], str | None] | None,
) -> tuple[pl.DataFrame, pl.DataFrame, int, str | None]:
    if not enabled:
        return retailer_products, _empty_live_retailer_audit_df(), 0, None

    brand_listing_url = _retailer_brand_listing_url(
        retailer,
        brand_name,
        category_key=category_key,
    )
    if brand_listing_url is None:
        return retailer_products, _empty_live_retailer_audit_df(), 0, None

    if fetcher is None:
        html_text, error = _fetch_url_text(brand_listing_url, timeout=timeout)
    else:
        html_text = fetcher(brand_listing_url)
        error = None if html_text else "fetcher_returned_no_html"
    if not html_text:
        LOGGER.warning(
            "Retailer live presence audit unavailable for %s / %s at %s: %s",
            retailer,
            brand_name,
            brand_listing_url,
            error,
        )
        return (
            retailer_products,
            _live_presence_unavailable_audit(
                owned,
                retailer_products=retailer_products,
                note=(
                    f"Could not fetch retailer brand page {brand_listing_url}: "
                    f"{error or 'unknown error'}"
                ),
            ),
            0,
            brand_listing_url,
        )

    live_products = _parse_ulta_brand_page_products(
        html_text,
        brand_name=brand_name,
    )
    declared_result_count = _ulta_brand_page_declared_result_count(html_text)
    if (
        not live_products
        and declared_result_count is not None
        and declared_result_count > 0
    ):
        LOGGER.warning(
            "Retailer live presence audit parsed no products for %s / %s at %s.",
            retailer,
            brand_name,
            brand_listing_url,
        )
        return (
            retailer_products,
            _live_presence_unavailable_audit(
                owned,
                retailer_products=retailer_products,
                note=(
                    f"Fetched retailer brand page {brand_listing_url}, but parsed "
                    "no product rows. Treating live check as inconclusive."
                ),
            ),
            0,
            brand_listing_url,
        )
    if not live_products:
        LOGGER.info(
            "Retailer live presence audit found no current products for %s / %s at %s.",
            retailer,
            brand_name,
            brand_listing_url,
        )
    live_product_keys = set(live_products)
    existing_retailer_keys = _key_set(retailer_products)
    if live_product_keys and "product_key" in _columns(retailer_products):
        validated_retailer_products = retailer_products.filter(
            pl.col("product_key")
            .map_elements(
                lambda value: _product_key_matches_any(
                    _meaningful_text(value),
                    live_product_keys,
                ),
                return_dtype=pl.Boolean,
            )
            .fill_null(False)
        )
    else:
        validated_retailer_products = retailer_products.head(0)
    rows: list[dict[str, Any]] = []
    live_rows: list[dict[str, Any]] = []
    for row in owned.select(_product_output_columns(owned)).to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        live_product = _live_product_match_for_owned(row, live_products)
        anchor_present = _product_key_matches_any(product_key, existing_retailer_keys)
        live_present = live_product is not None
        should_add = bool(live_present and not anchor_present)
        should_remove = bool(anchor_present and not live_present)
        if should_add and live_product is not None:
            live_rows.append(
                _live_presence_row_from_owned(
                    row,
                    retailer=retailer,
                    brand_name=brand_name,
                    category_key=category_key,
                    live_product=live_product,
                )
            )
            status = "live_brand_page_missing_from_package"
            note = (
                "Matched current retailer brand-page product to owned catalog; "
                "added as brand-at-retailer anchor for this package."
            )
        elif anchor_present and live_present:
            status = "ok_present_in_package_and_live"
            note = "Package anchor is also visible on current retailer brand page."
        elif anchor_present:
            status = "cached_package_anchor_not_on_live_brand_page"
            note = (
                "Package anchor came from cached retailer data but was not visible "
                "on the current retailer brand page; removed from current anchors."
            )
        else:
            status = "not_seen_live_brand_page"
            note = (
                "Owned catalog product was not found on the current retailer brand "
                "page audit."
            )
        rows.append(
            {
                "owned_product_name": row.get("product_name"),
                "owned_product_key": product_key,
                "owned_parent_product_id": row.get("parent_product_id"),
                "package_anchor_present_before_live_check": anchor_present,
                "live_brand_page_present": live_present,
                "live_brand_page_product_name": (
                    live_product.get("product_name") if live_product else None
                ),
                "live_brand_page_url": (
                    live_product.get("pdp_url") if live_product else None
                ),
                "live_added_to_retailer_products": should_add,
                "live_removed_from_retailer_products": should_remove,
                "audit_status": status,
                "audit_note": note,
            }
        )

    audit_df = (
        pl.DataFrame(rows, schema=LIVE_RETAILER_AUDIT_SCHEMA)
        if rows
        else _empty_live_retailer_audit_df()
    )
    if not live_rows:
        return (
            validated_retailer_products,
            audit_df,
            _unique_live_product_count(live_products),
            brand_listing_url,
        )
    augmented = pl.concat(
        [validated_retailer_products, pl.DataFrame(live_rows)],
        how="diagonal_relaxed",
    )
    return (
        augmented,
        audit_df,
        _unique_live_product_count(live_products),
        brand_listing_url,
    )


def _copy_file(source: Path, destination: Path) -> str | None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except OSError as exc:
        LOGGER.warning("Could not copy image %s to %s: %s", source, destination, exc)
        return None
    return str(destination)


def _write_file_bytes(data: bytes, destination: Path) -> str | None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    except OSError as exc:
        LOGGER.warning("Could not write image %s: %s", destination, exc)
        return None
    return str(destination)


def _copy_image_preview(source: Path, destination: Path) -> str | None:
    preview_destination = destination.with_suffix(".webp")
    try:
        __import__("pillow_avif")
    except ImportError:
        pass
    try:
        from PIL import Image, ImageOps

        with Image.open(source) as image:
            preview = ImageOps.exif_transpose(image)
            preview.thumbnail(
                (IMAGE_PREVIEW_MAX_DIMENSION, IMAGE_PREVIEW_MAX_DIMENSION)
            )
            if preview.mode != "RGB":
                if "A" in preview.getbands():
                    background = Image.new("RGB", preview.size, "white")
                    background.paste(
                        preview.convert("RGBA"), mask=preview.getchannel("A")
                    )
                    preview = background
                else:
                    preview = preview.convert("RGB")
            preview_destination.parent.mkdir(parents=True, exist_ok=True)
            preview.save(
                preview_destination,
                "WEBP",
                quality=IMAGE_PREVIEW_QUALITY,
                method=6,
            )
    except (ImportError, OSError, ValueError) as exc:
        LOGGER.warning(
            "Could not create image preview for %s; copying original image: %s",
            source,
            exc,
        )
        return _copy_file(source, destination)
    return str(preview_destination)


def _copy_image_preview_from_bytes(
    image_bytes: bytes,
    *,
    source_label: str,
    destination: Path,
) -> str | None:
    preview_destination = destination.with_suffix(".webp")
    try:
        __import__("pillow_avif")
    except ImportError:
        pass
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as image:
            preview = ImageOps.exif_transpose(image)
            preview.thumbnail(
                (IMAGE_PREVIEW_MAX_DIMENSION, IMAGE_PREVIEW_MAX_DIMENSION)
            )
            if preview.mode != "RGB":
                if "A" in preview.getbands():
                    background = Image.new("RGB", preview.size, "white")
                    background.paste(
                        preview.convert("RGBA"), mask=preview.getchannel("A")
                    )
                    preview = background
                else:
                    preview = preview.convert("RGB")
            preview_destination.parent.mkdir(parents=True, exist_ok=True)
            preview.save(
                preview_destination,
                "WEBP",
                quality=IMAGE_PREVIEW_QUALITY,
                method=6,
            )
    except (ImportError, OSError, ValueError) as exc:
        LOGGER.warning(
            "Could not create image preview for %s; writing original image: %s",
            source_label,
            exc,
        )
        return _write_file_bytes(image_bytes, destination)
    return str(preview_destination)


def _image_suffix_from_url(url: str, content_type: str | None) -> str:
    parsed_path = urllib.parse.urlparse(url).path
    suffix = Path(parsed_path).suffix.casefold()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        return suffix
    content_type_key = (content_type or "").split(";", maxsplit=1)[0].casefold()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }.get(content_type_key, ".jpg")


def _download_image_preview(url: str, destination: Path) -> str | None:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (compatible; MparanzaBrandFitAudit/1.0; "
                "+https://mparanza.com)"
            ),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS
        ) as response:
            image_bytes = response.read(IMAGE_DOWNLOAD_MAX_BYTES + 1)
            if len(image_bytes) > IMAGE_DOWNLOAD_MAX_BYTES:
                LOGGER.warning("Skipping oversized image %s", url)
                return None
            content_type = response.headers.get("Content-Type")
    except urllib.error.HTTPError as exc:
        LOGGER.warning("Could not download image %s: HTTP %s", url, exc.code)
        return None
    except urllib.error.URLError as exc:
        LOGGER.warning("Could not download image %s: %s", url, exc.reason)
        return None
    except TimeoutError:
        LOGGER.warning("Timed out downloading image %s", url)
        return None
    except OSError as exc:
        LOGGER.warning("Could not download image %s: %s", url, exc)
        return None
    if not image_bytes:
        return None
    target = destination.with_suffix(_image_suffix_from_url(url, content_type))
    return _copy_image_preview_from_bytes(
        image_bytes,
        source_label=url,
        destination=target,
    )


def _split_product_examples(value: Any) -> list[str]:
    text = _meaningful_text(value)
    if text is None:
        return []
    examples: list[str] = []
    for part in re.split(r"\s+\|\s+", text):
        example = part.strip()
        example = re.sub(r"\s+\(#[^)]+\)\s*$", "", example).strip()
        if _meaningful_text(example):
            examples.append(example)
    return examples


def _signal_image_reference_keys(
    signal_bundles: pl.DataFrame,
) -> dict[str, list[str]]:
    if signal_bundles.width == 0 or get_row_count(signal_bundles) == 0:
        return {}
    reference_keys: dict[str, list[str]] = {}
    for row in signal_bundles.to_dicts():
        bundle_label = _meaningful_text(row.get("bundle_label")) or "selected signal"
        for column in SIGNAL_IMAGE_REFERENCE_COLUMNS:
            for example in _split_product_examples(row.get(column)):
                key = _normalize_product_key(example)
                if key is None:
                    continue
                reference_keys.setdefault(key, [])
                reference_note = f"{bundle_label} via {column}"
                if reference_note not in reference_keys[key]:
                    reference_keys[key].append(reference_note)
    return reference_keys


def _image_map_from_cli_dir(cli_dir: Path | None) -> dict[str, Path]:
    if cli_dir is None:
        return {}
    images_dir = cli_dir / "images"
    if not images_dir.exists():
        return {}
    image_map: dict[str, Path] = {}
    for image_path in sorted(images_dir.iterdir()):
        if not image_path.is_file():
            continue
        if image_path.suffix.casefold() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        parent_id = image_path.stem.split("_", maxsplit=1)[0]
        if parent_id and parent_id not in image_map:
            image_map[parent_id] = image_path
    return image_map


def _image_map_from_cli_dirs(cli_dirs: Sequence[Path]) -> dict[str, Path]:
    image_map: dict[str, Path] = {}
    for cli_dir in cli_dirs:
        for parent_id, image_path in _image_map_from_cli_dir(cli_dir).items():
            image_map.setdefault(parent_id, image_path)
    return image_map


def _relative_output_path(output_dir: Path, absolute_path: str | None) -> str | None:
    if not absolute_path:
        return None
    path = Path(absolute_path)
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _copy_manufacturer_images(
    products: pl.DataFrame,
    *,
    cli_dir: Path | None,
    cli_dirs: Sequence[Path] | None = None,
    output_dir: Path,
    parent_ids: set[str] | None = None,
) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    source_dirs = tuple(cli_dirs or ())
    if not source_dirs and cli_dir is not None:
        source_dirs = (cli_dir,)
    image_map = _image_map_from_cli_dirs(source_dirs)
    parent_id_filter = (
        {
            str(parent_id)
            for parent_id in parent_ids
            if _meaningful_text(parent_id) is not None
        }
        if parent_ids is not None
        else None
    )
    image_files: dict[str, str] = {}
    image_rows: list[dict[str, Any]] = []
    row_columns = ["parent_product_id", "product_name", "product_scope"]
    if "hero_image_url" in _columns(products):
        row_columns.append("hero_image_url")
    for row in products.select(row_columns).to_dicts():
        parent_id = str(row.get("parent_product_id") or "")
        if parent_id_filter is not None and parent_id not in parent_id_filter:
            continue
        source = image_map.get(parent_id)
        image_source: str | None = None
        if source is not None:
            copied = _copy_image_preview(
                source,
                output_dir
                / "images"
                / "manufacturer_catalog"
                / f"{parent_id}{source.suffix.casefold()}",
            )
            image_source = str(source)
        else:
            image_url = _meaningful_text(row.get("hero_image_url"))
            if image_url is None:
                continue
            copied = _download_image_preview(
                image_url,
                output_dir / "images" / "manufacturer_catalog" / f"{parent_id}.jpg",
            )
            image_source = image_url
        if copied is None:
            continue
        image_file = _relative_output_path(output_dir, copied)
        if image_file is None:
            continue
        image_files[parent_id] = image_file
        image_rows.append(
            {
                "image_scope": "manufacturer_catalog",
                "parent_product_id": parent_id,
                "product_name": row.get("product_name"),
                "image_file": image_file,
                "image_available": True,
                "image_source": image_source,
                "inspect_rule": "Use to verify product form, finish cue, packaging, and shade-family fit.",
            }
        )
    enriched = products.with_columns(
        pl.col("parent_product_id")
        .cast(pl.Utf8)
        .map_elements(
            lambda value: image_files.get(str(value or "")), return_dtype=pl.Utf8
        )
        .alias("image_file")
    )
    return enriched, image_rows


def _collect_nonempty_column_values(df: pl.DataFrame, column: str) -> set[str]:
    if df.width == 0 or column not in _columns(df):
        return set()
    return {
        str(value)
        for value in df.select(column).to_series().to_list()
        if _meaningful_text(value) is not None
    }


def _nonempty_column_count(df: pl.DataFrame, column: str) -> int:
    if df.width == 0 or column not in _columns(df):
        return 0
    return sum(
        1
        for value in df.select(column).to_series().to_list()
        if _meaningful_text(value) is not None
    )


def _attribute_value_count(
    df: pl.DataFrame,
    *,
    columns: Sequence[str],
) -> int:
    if df.width == 0 or get_row_count(df) == 0:
        return 0
    present_columns = [column for column in columns if column in _columns(df)]
    if not present_columns:
        return 0
    return sum(
        1
        for row in df.select(present_columns).to_dicts()
        for value in row.values()
        if _meaningful_text(value) is not None
    )


def _missing_image_product_names(df: pl.DataFrame, *, limit: int = 8) -> list[str]:
    if df.width == 0 or "image_file" not in _columns(df):
        return []
    names: list[str] = []
    for row in df.select(["product_name", "image_file"]).to_dicts():
        if _meaningful_text(row.get("image_file")) is not None:
            continue
        product_name = _meaningful_text(row.get("product_name"))
        if product_name is None:
            continue
        names.append(product_name)
        if len(names) >= limit:
            break
    return names


def _validate_brand_image_coverage(
    *,
    brand_source_retailer: str,
    brand_name: str,
    retailer: str,
    category_key: str,
    owned: pl.DataFrame,
    candidates: pl.DataFrame,
    manufacturer_image_rows: Sequence[Mapping[str, Any]],
    allow_missing_brand_images: bool,
) -> None:
    catalog_count = get_row_count(owned)
    catalog_image_count = _nonempty_column_count(owned, "image_file")
    candidate_count = get_row_count(candidates) if candidates.width > 0 else 0
    candidate_image_count = _nonempty_column_count(candidates, "image_file")
    manufacturer_image_count = len(manufacturer_image_rows)
    context = (
        f"{brand_name} / {retailer} / {category_key}: "
        f"{manufacturer_image_count} brand images copied, "
        f"{candidate_image_count}/{candidate_count} reference candidates with images, "
        f"{catalog_image_count}/{catalog_count} catalog products with images. "
        f"Expected local source is data/pdp/cli/{brand_source_retailer}_{category_key}/images "
        "or cached hero_image_url in the brand product cache."
    )
    if candidate_count > 0 and candidate_image_count == 0:
        message = (
            "Brand image coverage failure. No reference candidate has a brand image. "
            f"{context}"
        )
        if not allow_missing_brand_images:
            raise RuntimeError(
                f"{message} Rebuild the brand scrape/images before submitting this "
                "package to Pro or NotebookLM, or pass --allow-missing-brand-images "
                "only for a deliberate text-only run."
            )
        LOGGER.error(
            "%s Proceeding because --allow-missing-brand-images was set.", message
        )
        return
    if catalog_count > 0 and manufacturer_image_count == 0:
        message = (
            f"Brand image coverage failure. No brand images were copied. {context}"
        )
        if not allow_missing_brand_images:
            raise RuntimeError(
                f"{message} Rebuild the brand scrape/images before submitting this "
                "package to Pro or NotebookLM, or pass --allow-missing-brand-images "
                "only for a deliberate text-only run."
            )
        LOGGER.error(
            "%s Proceeding because --allow-missing-brand-images was set.",
            message,
        )
        return
    if candidate_count > 0 and candidate_image_count < candidate_count:
        missing_names = _missing_image_product_names(candidates)
        LOGGER.warning(
            "Brand image coverage warning. Some reference candidates are missing "
            "brand images. %s Missing candidates: %s",
            context,
            "; ".join(missing_names) if missing_names else "(names unavailable)",
        )
        return
    LOGGER.info("Brand image coverage OK. %s", context)


def _brand_mismatch_examples(
    df: pl.DataFrame,
    *,
    brand_name: str,
    limit: int = 8,
) -> list[str]:
    if df.width == 0 or get_row_count(df) == 0:
        return []
    brand_column = _first_existing(_columns(df), BRAND_CANDIDATES)
    if brand_column is None:
        return []
    brand_key = _normalize_product_key(brand_name)
    if brand_key is None:
        return []
    wanted_columns = [
        column for column in ("product_name", brand_column) if column in _columns(df)
    ]
    examples: list[str] = []
    for row in df.select(wanted_columns).to_dicts():
        brand_value = _meaningful_text(row.get(brand_column))
        if brand_value is None or _brand_matches(brand_value, brand_key):
            continue
        product_name = _meaningful_text(row.get("product_name")) or "(unnamed product)"
        examples.append(f"{product_name} [{brand_value}]")
        if len(examples) >= limit:
            break
    return examples


def _validate_package_ready_for_pro(
    *,
    brand_name: str,
    retailer: str,
    category_key: str,
    anchors: pl.DataFrame,
    retailer_live_audit: pl.DataFrame,
    retailer_live_check: bool,
    package_integrity: Mapping[str, Any] | None = None,
) -> None:
    """Fail before writing a package whose evidence should not be sent to Pro."""

    failures: list[str] = []
    anchor_brand_mismatches = _brand_mismatch_examples(
        anchors,
        brand_name=brand_name,
    )
    if anchor_brand_mismatches:
        failures.append(
            "Current retailer anchors contain products from a different brand: "
            f"{'; '.join(anchor_brand_mismatches)}."
        )

    live_unavailable_count = 0
    if (
        retailer_live_check
        and retailer_live_audit.width > 0
        and "audit_status" in _columns(retailer_live_audit)
    ):
        live_unavailable_count = get_row_count(
            retailer_live_audit.filter(
                pl.col("audit_status") == "live_check_unavailable"
            )
        )
    if live_unavailable_count:
        failures.append(
            "Retailer live presence audit did not complete "
            f"({live_unavailable_count} catalog products unchecked)."
        )
    if (
        isinstance(package_integrity, Mapping)
        and package_integrity.get("status") == "fail"
    ):
        integrity_summary = package_integrity.get("summary")
        integrity_failure_count = 0
        if isinstance(integrity_summary, Mapping):
            integrity_failure_count = _safe_int(integrity_summary.get("failure_count"))
        failures.append(
            "Package integrity audit failed "
            f"({integrity_failure_count} deterministic issue(s)). "
            "See package_integrity.json."
        )

    if not failures:
        return

    context = f"{brand_name} / {retailer} / {category_key}"
    raise RuntimeError(
        "Brand Fit package quality gate failed before Pro handoff. "
        f"{context}: {' '.join(failures)} Rebuild or repair the source data before "
        "submitting this package to Pro."
    )


def _manufacturer_image_parent_ids(
    *,
    anchors: pl.DataFrame,
    candidates: pl.DataFrame,
) -> set[str]:
    parent_ids = _collect_nonempty_column_values(candidates, "parent_product_id")
    parent_ids.update(
        _collect_nonempty_column_values(anchors, "owned_parent_product_id")
    )
    return parent_ids


def _copy_innovation_example_images(
    innovation_package_dir: Path,
    *,
    output_dir: Path,
    signal_bundles: pl.DataFrame,
) -> list[dict[str, Any]]:
    image_index_path = innovation_package_dir / "image_index.csv"
    image_index = _read_csv_if_exists(image_index_path)
    if image_index.width == 0 or get_row_count(image_index) == 0:
        return []
    reference_keys = _signal_image_reference_keys(signal_bundles)
    if not reference_keys:
        return []
    rows: list[dict[str, Any]] = []
    for row in image_index.to_dicts():
        image_file = _meaningful_text(row.get("image_file"))
        if image_file is None:
            continue
        product_key = _normalize_product_key(row.get("product_name"))
        if product_key is None or product_key not in reference_keys:
            continue
        source = innovation_package_dir / image_file
        if not source.exists():
            continue
        destination = output_dir / "images" / "innovation_examples" / source.name
        copied = _copy_image_preview(source, destination)
        copied_relative = _relative_output_path(output_dir, copied)
        if copied_relative is None:
            continue
        rows.append(
            {
                "image_scope": "innovation_example",
                "parent_product_id": row.get("parent_product_id"),
                "product_name": row.get("product_name"),
                "image_file": copied_relative,
                "image_available": True,
                "image_source": f"{image_index_path}:{image_file}",
                "inspect_rule": (
                    "Use only as visual evidence for the selected source retailer "
                    f"signal examples: {'; '.join(reference_keys[product_key][:3])}."
                ),
            }
        )
    return rows


def _copy_innovation_brief(
    innovation_brief_path: Path | None,
    *,
    output_dir: Path,
) -> str | None:
    if innovation_brief_path is None or not innovation_brief_path.exists():
        return None
    copied = output_dir / "source_innovation_brief.md"
    brief_text = innovation_brief_path.read_text(encoding="utf-8")
    brief_text = re.sub(r"\bformats\b", "forms", brief_text, flags=re.IGNORECASE)
    brief_text = re.sub(r"\bformat\b", "form", brief_text, flags=re.IGNORECASE)
    copied.write_text(brief_text, encoding="utf-8")
    return _relative_output_path(output_dir, copied)


def _source_summary_count(
    source_innovation_summary: Mapping[str, Any],
    key: str,
) -> int:
    value = source_innovation_summary.get(key)
    counts = source_innovation_summary.get("counts")
    if value is None and isinstance(counts, Mapping):
        value = counts.get(key)
    return _safe_int(value)


def _signal_bundles_have_rank_weighted_visibility(
    signal_bundles: pl.DataFrame,
) -> bool:
    if signal_bundles.width == 0 or get_row_count(signal_bundles) == 0:
        return False
    columns = [
        column
        for column in [
            "rank_weighted_gross_visibility_share",
            "rank_weighted_incremental_visibility_share",
            "rank_weighted_visibility_density_index",
            "rank_weighted_visibility_alpha_scenarios",
            "rank_weighted_visibility_best_shelf_rank",
        ]
        if column in _columns(signal_bundles)
    ]
    if not columns:
        return False
    return any(
        any(row.get(column) is not None for column in columns)
        for row in signal_bundles.select(columns).to_dicts()
    )


def _source_web_shelf_artifacts_expected(
    source_innovation_summary: Mapping[str, Any],
    signal_bundles: pl.DataFrame,
) -> bool:
    return _signal_bundles_have_rank_weighted_visibility(signal_bundles) or any(
        _source_summary_count(source_innovation_summary, key) > 0
        for key in SOURCE_WEB_SHELF_SUMMARY_ROW_KEYS
    )


def _csv_data_row_count(path: Path) -> int:
    try:
        return get_row_count(pl.read_csv(path, infer_schema_length=10000))
    except pl.exceptions.NoDataError as exc:
        raise RuntimeError(f"CSV artifact is empty or unreadable: {path}") from exc


def _copy_source_web_shelf_artifacts(
    innovation_package_dir: Path,
    *,
    output_dir: Path,
    source_innovation_summary: Mapping[str, Any],
    signal_bundles: pl.DataFrame,
) -> dict[str, Any]:
    expected = _source_web_shelf_artifacts_expected(
        source_innovation_summary,
        signal_bundles,
    )
    copied_files: list[dict[str, Any]] = []
    missing_files: list[str] = []
    row_mismatches: list[str] = []
    row_counts: dict[str, int] = {}
    source_summary_counts: dict[str, int] = {}
    for source_name, package_name in SOURCE_WEB_SHELF_ARTIFACTS:
        summary_key = SOURCE_WEB_SHELF_ARTIFACT_ROW_KEYS.get(package_name)
        expected_rows = (
            _source_summary_count(source_innovation_summary, summary_key)
            if summary_key is not None
            else 0
        )
        if summary_key is not None:
            source_summary_counts[package_name] = expected_rows
        source = innovation_package_dir / source_name
        if not source.exists():
            missing_files.append(source_name)
            continue
        destination = output_dir / package_name
        shutil.copy2(source, destination)
        row_count = _csv_data_row_count(destination)
        if expected_rows > 0 and row_count != expected_rows:
            row_mismatches.append(
                f"{source_name}: summary={expected_rows} file={row_count}"
            )
        copied_files.append(
            {
                "source_file": source_name,
                "package_file": package_name,
                "summary_count_key": summary_key,
                "source_summary_row_count": expected_rows,
                "row_count": row_count,
            }
        )
        row_counts[package_name] = row_count
    if (expected and missing_files) or row_mismatches:
        problems = []
        if expected and missing_files:
            problems.append("missing files: " + CSV_LIST_SEPARATOR.join(missing_files))
        if row_mismatches:
            problems.append(
                "row-count mismatches: " + CSV_LIST_SEPARATOR.join(row_mismatches)
            )
        raise RuntimeError(
            "Brand Fit package generation found rank-weighted visibility or "
            "web-shelf evidence in the source retailer package, but the source "
            "web-shelf audit files are incomplete. "
            f"{'; '.join(problems)}. Rebuild the retailer "
            "package before building Brand Fit."
        )
    return {
        "expected": expected,
        "files": copied_files,
        "missing_files": missing_files,
        "row_counts": row_counts,
        "source_summary_row_counts": source_summary_counts,
    }


def _copy_source_review_evidence_artifacts(
    innovation_package_dir: Path,
    *,
    output_dir: Path,
    source_innovation_summary: Mapping[str, Any],
) -> dict[str, Any]:
    copied_files: list[dict[str, Any]] = []
    missing_files: list[str] = []
    row_mismatches: list[str] = []
    row_counts: dict[str, int] = {}
    source_summary_counts: dict[str, int] = {}
    for source_name, package_name, summary_key in SOURCE_REVIEW_EVIDENCE_ARTIFACTS:
        expected_rows = _source_summary_count(source_innovation_summary, summary_key)
        source_summary_counts[package_name] = expected_rows
        source = innovation_package_dir / source_name
        if not source.exists():
            if expected_rows > 0:
                missing_files.append(source_name)
            continue
        destination = output_dir / package_name
        shutil.copy2(source, destination)
        row_count = _csv_data_row_count(destination)
        if expected_rows > 0 and row_count != expected_rows:
            row_mismatches.append(
                f"{source_name}: summary={expected_rows} file={row_count}"
            )
        copied_files.append(
            {
                "source_file": source_name,
                "package_file": package_name,
                "summary_count_key": summary_key,
                "source_summary_row_count": expected_rows,
                "row_count": row_count,
            }
        )
        row_counts[package_name] = row_count
    if missing_files or row_mismatches:
        problems = []
        if missing_files:
            problems.append("missing files: " + CSV_LIST_SEPARATOR.join(missing_files))
        if row_mismatches:
            problems.append(
                "row-count mismatches: " + CSV_LIST_SEPARATOR.join(row_mismatches)
            )
        raise RuntimeError(
            "Brand Fit package generation found source review evidence in the "
            "retailer package summary, but the source review evidence files are "
            f"incomplete. {'; '.join(problems)}. Rebuild the retailer package "
            "before building Brand Fit."
        )
    return {
        "expected": any(count > 0 for count in source_summary_counts.values()),
        "files": copied_files,
        "missing_files": missing_files,
        "row_counts": row_counts,
        "source_summary_row_counts": source_summary_counts,
    }


def _source_web_shelf_package_files(summary: Mapping[str, Any]) -> list[str]:
    sources = summary.get("sources")
    if not isinstance(sources, Mapping):
        return []
    artifacts = sources.get("source_web_shelf_artifacts")
    if not isinstance(artifacts, Mapping):
        return []
    files = artifacts.get("files")
    if not isinstance(files, Sequence):
        return []
    return [
        str(file_info.get("package_file"))
        for file_info in files
        if isinstance(file_info, Mapping)
        and _meaningful_text(file_info.get("package_file")) is not None
    ]


def _web_shelf_prompt_line(summary: Mapping[str, Any]) -> str:
    files = _source_web_shelf_package_files(summary)
    if not files:
        return ""
    formatted_files = ", ".join(f"`{file_name}`" for file_name in files)
    return (
        "- Use the copied source web-shelf audit files "
        f"({formatted_files}) as the audit trail behind rank-weighted visibility. "
        "They explain which attribute shelves were selected, their robustness, "
        "and the products contributing visibility. They are not a separate signal "
        "family and should not get their own report section."
    )


def _web_shelf_file_lines(summary: Mapping[str, Any]) -> str:
    files = _source_web_shelf_package_files(summary)
    if not files:
        return ""
    return "\n".join(
        (
            f"- `{file_name}`: copied source retailer web-shelf audit file behind "
            "rank-weighted visibility metrics."
        )
        for file_name in files
    )


def _source_review_evidence_package_files(summary: Mapping[str, Any]) -> list[str]:
    sources = summary.get("sources")
    if not isinstance(sources, Mapping):
        return []
    artifacts = sources.get("source_review_evidence_artifacts")
    if not isinstance(artifacts, Mapping):
        return []
    files = artifacts.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)):
        return []
    return [
        str(file_info.get("package_file"))
        for file_info in files
        if isinstance(file_info, Mapping)
        and _meaningful_text(file_info.get("package_file")) is not None
    ]


def _review_evidence_prompt_line(summary: Mapping[str, Any]) -> str:
    files = _source_review_evidence_package_files(summary)
    if not files:
        return ""
    formatted_files = ", ".join(f"`{file_name}`" for file_name in files)
    return (
        "- Use the copied source review evidence files "
        f"({formatted_files}) only as a secondary retailer-level experience layer. "
        "They can validate or complicate source retailer signals, but they are not "
        f"brand-specific evidence for {summary['brand_name']} unless the same "
        "product also appears in `brand_at_retailer_review_validation.csv`."
    )


def _review_evidence_file_lines(summary: Mapping[str, Any]) -> str:
    files = _source_review_evidence_package_files(summary)
    if not files:
        return ""
    descriptions = {
        "source_review_theme_cohort_comparison.csv": (
            "copied source retailer review-theme cohort comparison; use only as "
            "secondary review-visible experience evidence"
        ),
        "source_top_seller_review_validation.csv": (
            "copied source retailer review excerpts for current winning bundles"
        ),
        "source_bundle_review_validation.csv": (
            "copied source retailer review excerpts for recent-arrival bundles"
        ),
    }
    return "\n".join(
        f"- `{file_name}`: {descriptions.get(file_name, 'copied source retailer review evidence file')}."
        for file_name in files
    )


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


def _brand_fit_package_warning_payload(
    *,
    summary: Mapping[str, Any],
    package_integrity: Mapping[str, Any],
) -> dict[str, Any]:
    warnings = _integrity_warning_rows(
        package_integrity,
        source="brand_fit_package_integrity",
    )
    sources = summary.get("sources")
    source_integrity: Mapping[str, Any] = {}
    if isinstance(sources, Mapping):
        raw_source_integrity = sources.get("source_innovation_package_integrity")
        if isinstance(raw_source_integrity, Mapping):
            source_integrity = raw_source_integrity
        if sources.get("retailer_live_check_enabled") is False:
            warnings.append(
                {
                    "source": "brand_fit_context",
                    "severity": "warning",
                    "code": "retailer_live_check_disabled",
                    "message": (
                        "Retailer live presence check was disabled for this package. "
                        "Current retailer presence relies on cached source data."
                    ),
                    "details": {
                        "retailer_live_check_enabled": False,
                        "retailer_live_brand_page_url": sources.get(
                            "retailer_live_brand_page_url"
                        ),
                    },
                }
            )
    if source_integrity.get("status") == "pass_with_warnings":
        warnings.append(
            {
                "source": "source_retailer_package_integrity",
                "severity": "warning",
                "code": "source_retailer_package_integrity_warnings",
                "message": (
                    "The source retailer package passed with warnings. Preserve "
                    "those caveats when using source retailer signals."
                ),
                "details": dict(source_integrity),
            }
        )
    counts = summary.get("counts")
    if isinstance(counts, Mapping):
        anchor_count = _safe_int(counts.get("retailer_brand_anchor_products"))
        anchors_with_reviews = _safe_int(
            counts.get("retailer_brand_anchor_products_with_rating_or_review_count")
        )
        if anchor_count > 0 and anchors_with_reviews == 0:
            warnings.append(
                {
                    "source": "brand_fit_context",
                    "severity": "warning",
                    "code": "current_brand_review_evidence_unavailable",
                    "message": (
                        "Current brand-at-retailer anchors have no rating or "
                        "review-count evidence in the package. Do not interpret "
                        "missing reviews as negative consumer response."
                    ),
                    "details": {
                        "retailer_brand_anchor_products": anchor_count,
                        "retailer_brand_anchor_products_with_rating_or_review_count": (
                            anchors_with_reviews
                        ),
                    },
                }
            )
    return _warning_payload(
        package_type="brand_retailer_reference_handoff",
        warnings=warnings,
    )


def _build_anchors(
    owned: pl.DataFrame,
    retailer_products: pl.DataFrame,
    *,
    brand_source_retailer: str | None = None,
    retailer: str | None = None,
    category_key: str | None = None,
) -> pl.DataFrame:
    owned_lookup = owned.select(
        [
            "product_key",
            pl.col("product_name").alias("owned_product_name"),
            pl.col("parent_product_id").alias("owned_parent_product_id"),
            pl.col("pdp_url").alias("owned_pdp_url"),
            pl.col("variant_count").alias("owned_variant_count"),
            pl.col("image_file").alias("owned_image_file"),
        ]
    )
    anchors = (
        retailer_products.join(owned_lookup, on="product_key", how="left")
        .with_columns(
            [
                pl.when(pl.col("owned_product_name").is_not_null())
                .then(pl.lit("exact_product_key"))
                .otherwise(pl.lit(None, dtype=pl.Utf8))
                .alias("product_identity_match_method"),
                pl.when(pl.col("owned_product_name").is_not_null())
                .then(pl.lit(100.0))
                .otherwise(pl.lit(None, dtype=pl.Float64))
                .alias("product_identity_match_score"),
                pl.lit(None, dtype=pl.Float64).alias("product_identity_match_margin"),
            ]
        )
        .with_columns(
            pl.when(pl.col("owned_product_name").is_not_null())
            .then(pl.lit("matched_owned_product"))
            .otherwise(pl.lit("retailer_only"))
            .alias("anchor_status")
        )
        .rename(
            {
                "product_name": "retailer_product_name",
                "parent_product_id": "retailer_parent_product_id",
                "pdp_url": "retailer_pdp_url",
                "variant_count": "retailer_variant_count",
            }
        )
    )
    if _use_tikicat_chewy_product_matching(
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    ):
        anchors = _apply_tikicat_chewy_product_identity_matches(anchors, owned)
    else:
        anchors = _apply_generic_product_identity_matches(anchors, owned)
    return anchors.with_columns(
        [
            pl.col("retailer_product_name").alias("product_name"),
            pl.col("retailer_parent_product_id").alias("parent_product_id"),
            pl.col("retailer_pdp_url").alias("pdp_url"),
            pl.col("retailer_variant_count").alias("variant_count"),
            pl.col("owned_image_file").alias("image_file"),
        ]
    )


def _apply_tikicat_chewy_product_identity_matches(
    anchors: pl.DataFrame,
    owned: pl.DataFrame,
) -> pl.DataFrame:
    if anchors.width == 0 or get_row_count(anchors) == 0:
        return anchors
    unmatched = anchors.filter(pl.col("owned_parent_product_id").is_null())
    matches = _tikicat_chewy_product_identity_matches(owned, unmatched)
    return _apply_product_identity_matches(anchors, matches)


def _apply_generic_product_identity_matches(
    anchors: pl.DataFrame,
    owned: pl.DataFrame,
) -> pl.DataFrame:
    if anchors.width == 0 or get_row_count(anchors) == 0:
        return anchors
    unmatched = anchors.filter(pl.col("owned_parent_product_id").is_null())
    matches = _generic_product_identity_matches(owned, unmatched)
    return _apply_product_identity_matches(anchors, matches)


def _apply_product_identity_matches(
    anchors: pl.DataFrame,
    matches: pl.DataFrame,
) -> pl.DataFrame:
    if matches.width == 0 or get_row_count(matches) == 0:
        return anchors

    match_columns = [
        "owned_product_name",
        "owned_parent_product_id",
        "owned_pdp_url",
        "owned_variant_count",
        "owned_image_file",
        "product_identity_match_method",
        "product_identity_match_score",
        "product_identity_match_margin",
    ]
    match_lookup = matches.rename(
        {column: f"{column}_match" for column in match_columns}
    )
    joined = anchors.join(match_lookup, on="retailer_parent_product_id", how="left")
    joined = joined.with_columns(
        [
            pl.coalesce(pl.col(column), pl.col(f"{column}_match")).alias(column)
            for column in match_columns
        ]
    )
    joined = joined.with_columns(
        pl.when(pl.col("owned_product_name").is_not_null())
        .then(pl.lit("matched_owned_product"))
        .otherwise(pl.lit("retailer_only"))
        .alias("anchor_status")
    )
    return joined.drop([f"{column}_match" for column in match_columns])


def _key_set(df: pl.DataFrame) -> set[str]:
    if get_row_count(df) == 0:
        return set()
    return {
        str(value)
        for value in df.select("product_key").to_series().to_list()
        if _meaningful_text(value)
    }


def _build_missing_owned(
    owned: pl.DataFrame,
    retailer_products: pl.DataFrame,
    *,
    anchors: pl.DataFrame | None = None,
) -> pl.DataFrame:
    if (
        anchors is not None
        and anchors.width > 0
        and "owned_parent_product_id" in _columns(anchors)
    ):
        matched_owned_ids = {
            str(value)
            for value in anchors.select("owned_parent_product_id").to_series().to_list()
            if _meaningful_text(value)
        }
        if matched_owned_ids:
            return owned.filter(
                ~pl.col("parent_product_id")
                .cast(pl.Utf8)
                .is_in(sorted(matched_owned_ids))
            )
    retailer_keys = _key_set(retailer_products)
    if not retailer_keys:
        return owned
    return owned.filter(~pl.col("product_key").is_in(sorted(retailer_keys)))


def _parse_bundle_key(bundle_key: Any) -> tuple[dict[str, str], ...]:
    text = _meaningful_text(bundle_key)
    if text is None:
        return tuple()
    components: list[dict[str, str]] = []
    for part in text.split(" + "):
        if "=" not in part:
            continue
        attribute, value = part.split("=", maxsplit=1)
        attribute_text = _component_semantic_family(attribute)
        value_text = _normalize_search_text(value)
        if not attribute_text or not value_text:
            continue
        components.append({"attribute": attribute_text, "value": value_text})
    return tuple(
        sorted(components, key=lambda item: (item["attribute"], item["value"]))
    )


def _component_semantic_family(attribute: str) -> str:
    return signal_component_family(attribute)


def _bundle_components_are_usable(components: Sequence[Mapping[str, str]]) -> bool:
    semantic_families = [
        _component_semantic_family(component["attribute"]) for component in components
    ]
    return len(set(semantic_families)) == len(semantic_families)


def _bundle_id(components: Sequence[Mapping[str, str]]) -> str:
    canonical = " + ".join(
        f"{component['attribute']}={component['value']}" for component in components
    )
    return f"bundle_{uuid.uuid5(uuid.NAMESPACE_URL, canonical).hex[:10]}"


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _signal_row_score(row: Mapping[str, Any], layer: str) -> float:
    if layer == "winning_now":
        return (
            _safe_float(row.get("top_seller_sales_share_sum")) * 100.0
            + _safe_float(row.get("delta")) * 100.0
            + _safe_float(row.get("pct_top_seller")) * 10.0
            + _safe_int(row.get("count_top_seller")) / 10.0
        )
    return (
        _safe_float(row.get("delta")) * 100.0
        + _safe_float(row.get("pct_recent")) * 10.0
        + _safe_float(row.get("recent_sales_share_sum")) * 100.0
        + _safe_float(row.get("prevalence_ratio"))
        + _safe_int(row.get("count_recent")) / 10.0
    )


def _signal_insight_metadata(
    *,
    category_key: str | None,
    components: Sequence[Mapping[str, str]],
    base_score: float,
    signal_layers: Sequence[str],
) -> dict[str, Any]:
    return category_signal_insight_metadata(
        category_key=category_key,
        components=components,
        base_score=base_score,
        signal_layers=signal_layers,
        layer_bonus_by_layer={"innovation": 8.0},
        combined_layer_bonus=8.0,
    )


def _signal_row_is_usable(row: Mapping[str, Any], layer: str) -> bool:
    if layer == "winning_now":
        return (
            _safe_int(row.get("count_top_seller")) >= 3
            and _safe_int(row.get("top_seller_brand_count")) >= 2
            and _safe_float(row.get("delta")) > 0
        )
    return (
        _safe_int(row.get("count_recent")) >= 3
        and _safe_int(row.get("recent_brand_count")) >= 2
        and _safe_float(row.get("delta")) > 0
    )


def _rank_weighted_visibility_score(row: Mapping[str, Any]) -> float:
    return (
        _safe_float(row.get("rank_weighted_incremental_visibility_share")) * 100.0
        + _safe_float(row.get("rank_weighted_gross_visibility_share")) * 25.0
        + _safe_float(row.get("rank_weighted_visibility_density_index"))
        + _safe_int(row.get("rank_weighted_visibility_alpha_scenarios")) * 5.0
        + _safe_int(row.get("rank_weighted_visibility_incremental_sku_count")) / 10.0
    )


def _row_has_rank_weighted_visibility(row: Mapping[str, Any]) -> bool:
    return (
        _safe_float(row.get("rank_weighted_gross_visibility_share")) > 0
        or _safe_float(row.get("rank_weighted_incremental_visibility_share")) > 0
    )


def _apply_rank_weighted_visibility_metrics(
    entry: dict[str, Any],
    row: Mapping[str, Any],
) -> None:
    if not _row_has_rank_weighted_visibility(row):
        return
    score = _rank_weighted_visibility_score(row)
    if score <= _safe_float(entry.get("rank_weighted_visibility_score")):
        return
    entry.update(
        {
            "rank_weighted_visibility_score": score,
            "rank_weighted_visibility_rank": row.get(
                "rank_weighted_visibility_best_shelf_rank"
            ),
            "rank_weighted_visibility_alpha_scenarios": row.get(
                "rank_weighted_visibility_alpha_scenarios"
            ),
            "rank_weighted_gross_visibility_share": row.get(
                "rank_weighted_gross_visibility_share"
            ),
            "rank_weighted_incremental_visibility_share": row.get(
                "rank_weighted_incremental_visibility_share"
            ),
            "rank_weighted_visibility_density_index": row.get(
                "rank_weighted_visibility_density_index"
            ),
            "rank_weighted_visibility_sku_count": row.get(
                "rank_weighted_visibility_incremental_sku_count"
            )
            or row.get("rank_weighted_visibility_gross_sku_count"),
            "rank_weighted_visibility_brand_count": row.get(
                "rank_weighted_visibility_incremental_brand_count"
            )
            or row.get("rank_weighted_visibility_gross_brand_count"),
            "rank_weighted_visibility_top_products": row.get(
                "rank_weighted_visibility_top_products"
            ),
            "rank_weighted_visibility_top_brands": row.get(
                "rank_weighted_visibility_top_brands"
            ),
        }
    )


def _extract_candidate_signal_rows(
    innovation_package_dir: Path,
    *,
    max_bundles_per_layer: int,
    category_key: str | None,
) -> list[dict[str, Any]]:
    layer_rows: dict[str, list[dict[str, Any]]] = {
        "winning_now": [],
        "innovation": [],
    }
    for layer, filename, bundle_family in SIGNAL_SOURCE_CONFIG:
        path = innovation_package_dir / filename
        df = _read_csv_if_exists(path)
        if df.width == 0 or get_row_count(df) == 0:
            continue
        for row in df.to_dicts():
            components = _parse_bundle_key(row.get("bundle_key"))
            if (
                not components
                or not _bundle_components_are_usable(components)
                or not _signal_row_is_usable(row, layer)
            ):
                continue
            row_score = _signal_row_score(row, layer)
            insight_metadata = _signal_insight_metadata(
                category_key=category_key,
                components=components,
                base_score=row_score,
                signal_layers=(layer,),
            )
            enriched = dict(row)
            enriched.update(
                {
                    "_components": components,
                    "_layer": layer,
                    "_source_file": filename,
                    "_bundle_family": bundle_family,
                    "_row_score": insight_metadata["insight_adjusted_signal_score"],
                    "_raw_row_score": row_score,
                    "_signal_usefulness": insight_metadata["signal_usefulness"],
                    "_signal_role": insight_metadata.get("signal_role"),
                }
            )
            layer_rows[layer].append(enriched)
    selected: list[dict[str, Any]] = []
    for rows in layer_rows.values():
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            bundle_id = _bundle_id(row["_components"])
            existing = deduped.get(bundle_id)
            if existing is None or row["_row_score"] > existing["_row_score"]:
                deduped[bundle_id] = row
        sorted_rows = sorted(
            deduped.values(),
            key=lambda item: item["_row_score"],
            reverse=True,
        )
        selected_rows = sorted_rows[:max_bundles_per_layer]
        selected_ids = {_bundle_id(row["_components"]) for row in selected_rows}
        context_rows = [
            row
            for row in sorted_rows
            if row.get("_signal_role") == "category_center"
            and _bundle_id(row["_components"]) not in selected_ids
        ][:max_bundles_per_layer]
        selected.extend([*selected_rows, *context_rows])
    return selected


def _load_signal_bundles(
    innovation_package_dir: Path,
    *,
    max_bundles_per_layer: int,
    category_key: str | None,
) -> pl.DataFrame:
    candidate_rows = _extract_candidate_signal_rows(
        innovation_package_dir,
        max_bundles_per_layer=max_bundles_per_layer,
        category_key=category_key,
    )
    bundles: dict[str, dict[str, Any]] = {}
    for row in candidate_rows:
        components = row["_components"]
        bundle_id = _bundle_id(components)
        entry = bundles.setdefault(
            bundle_id,
            {
                "bundle_id": bundle_id,
                "bundle_key": " + ".join(
                    f"{component['attribute']}={component['value']}"
                    for component in components
                ),
                "bundle_label": row.get("bundle_label"),
                "bundle_size": len(components),
                "components_json": json.dumps(components, ensure_ascii=False),
                "component_labels": CSV_LIST_SEPARATOR.join(
                    f"{component['attribute']}={component['value']}"
                    for component in components
                ),
                "signal_layers": set(),
                "signal_roles": set(),
                "source_files": set(),
                "winning_now_score": 0.0,
                "innovation_score": 0.0,
                "rank_weighted_visibility_score": 0.0,
                "rank_weighted_visibility_rank": None,
                "rank_weighted_visibility_alpha_scenarios": None,
                "rank_weighted_gross_visibility_share": None,
                "rank_weighted_incremental_visibility_share": None,
                "rank_weighted_visibility_density_index": None,
                "rank_weighted_visibility_sku_count": None,
                "rank_weighted_visibility_brand_count": None,
                "rank_weighted_visibility_top_products": None,
                "rank_weighted_visibility_top_brands": None,
            },
        )
        layer = str(row["_layer"])
        entry["signal_layers"].add(layer)
        signal_role = _meaningful_text(row.get("_signal_role"))
        if signal_role:
            entry["signal_roles"].add(signal_role)
        entry["source_files"].add(str(row["_source_file"]))
        entry["bundle_label"] = entry["bundle_label"] or row.get("bundle_label")
        if layer == "winning_now" and row["_row_score"] > entry["winning_now_score"]:
            entry.update(
                {
                    "winning_now_score": row["_row_score"],
                    "count_top_seller": row.get("count_top_seller"),
                    "count_other": row.get("count_other"),
                    "top_seller_brand_count": row.get("top_seller_brand_count"),
                    "pct_top_seller": row.get("pct_top_seller"),
                    "pct_other": row.get("pct_other"),
                    "winning_delta": row.get("delta"),
                    "top_seller_brands": row.get("top_seller_brands"),
                    "top_seller_example_products": row.get(
                        "top_seller_example_products"
                    ),
                    "top_seller_top_pareto_products": row.get(
                        "top_seller_top_pareto_products"
                    ),
                }
            )
        if layer == "innovation" and row["_row_score"] > entry["innovation_score"]:
            entry.update(
                {
                    "innovation_score": row["_row_score"],
                    "count_recent": row.get("count_recent"),
                    "count_rest": row.get("count_rest"),
                    "recent_brand_count": row.get("recent_brand_count"),
                    "pct_recent": row.get("pct_recent"),
                    "pct_rest": row.get("pct_rest"),
                    "innovation_delta": row.get("delta"),
                    "recent_brands": row.get("recent_brands"),
                    "recent_example_products": row.get("recent_example_products"),
                    "recent_top_pareto_products": row.get("recent_top_pareto_products"),
                }
            )
        _apply_rank_weighted_visibility_metrics(entry, row)

    output_rows: list[dict[str, Any]] = []
    for entry in bundles.values():
        signal_layers = sorted(
            entry["signal_layers"],
            key=lambda layer: SIGNAL_LAYER_ORDER.get(layer, 99),
        )
        source_files = sorted(entry["source_files"])
        signal_score = (
            float(entry.get("winning_now_score") or 0.0)
            + float(entry.get("innovation_score") or 0.0)
            + (5.0 if len(signal_layers) > 1 else 0.0)
        )
        if "category_center" in entry["signal_roles"]:
            insight_metadata = {
                "signal_usefulness": "category_center",
                "signal_role": "category_center",
                "discriminating_component_count": 0,
                "category_center_component_count": entry["bundle_size"],
                "base_rate_component_count": entry["bundle_size"],
                "insight_adjusted_signal_score": round(signal_score, 6),
                "signal_quality_note": (
                    "Observed broad-baseline bundle. Use as market-center context, "
                    "not as a headline differentiating signal."
                ),
                "signal_role_note": (
                    "Observed broad-baseline bundle. Use as market-center context, "
                    "not as a headline differentiating signal."
                ),
            }
        else:
            insight_metadata = _signal_insight_metadata(
                category_key=category_key,
                components=json.loads(str(entry["components_json"])),
                base_score=signal_score,
                signal_layers=signal_layers,
            )
        row = dict(entry)
        row["signal_layers"] = CSV_LIST_SEPARATOR.join(signal_layers)
        row.pop("signal_roles", None)
        row["source_files"] = CSV_LIST_SEPARATOR.join(source_files)
        row["signal_score"] = round(signal_score, 6)
        row.update(insight_metadata)
        output_rows.append(row)
    if not output_rows:
        return pl.DataFrame(schema={})
    return pl.DataFrame(output_rows).sort(
        ["insight_adjusted_signal_score", "signal_score"],
        descending=[True, True],
    )


def _split_signal_bundles_by_usefulness(
    signal_bundles: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    if signal_bundles.width == 0 or get_row_count(signal_bundles) == 0:
        return signal_bundles, pl.DataFrame(schema={})
    columns = _columns(signal_bundles)
    if "signal_role" in columns:
        context = signal_bundles.filter(pl.col("signal_role") == "category_center")
        selected = signal_bundles.filter(pl.col("signal_role") != "category_center")
    elif "signal_usefulness" in columns:
        context = signal_bundles.filter(
            pl.col("signal_usefulness") == "category_center"
        )
        selected = signal_bundles.filter(
            pl.col("signal_usefulness") != "category_center"
        )
    else:
        return signal_bundles, pl.DataFrame(schema={})
    return selected, context


def _component_aliases(value: str) -> set[str]:
    normalized = _normalize_search_text(value)
    aliases = {normalized}
    coverage_aliases = {
        "buildable coverage": "buildable",
        "full coverage": "full",
        "medium coverage": "medium",
        "sheer coverage": "sheer",
    }
    if normalized in coverage_aliases:
        aliases.add(coverage_aliases[normalized])
    if normalized == "high shine":
        aliases.update({"shine", "glossy", "glossy high shine"})
    if normalized == "stick":
        aliases.update({"stylo", "crayon", "pencil", "bullet", "bullet lipstick"})
    if normalized == "cream":
        aliases.add("creamy")
    if normalized == "matte":
        aliases.update({"semi matte", "soft matte"})
    return {alias for alias in aliases if alias}


def _candidate_columns_for_attribute(attribute: str) -> list[str]:
    normalized = _normalize_search_text(attribute)
    candidates = ATTRIBUTE_CANDIDATE_COLUMNS.get(normalized, [])
    generic = [
        normalized,
        normalized.replace(" ", "_"),
        normalized.replace("_", " "),
    ]
    return [*candidates, *generic]


def _product_attribute_text(row: Mapping[str, Any], attribute: str) -> str:
    values: list[str] = []
    for column in _candidate_columns_for_attribute(attribute):
        if column not in row:
            continue
        for value in _split_values(row.get(column)):
            values.append(value)
    return _normalize_search_text(CSV_LIST_SEPARATOR.join(values))


def _product_one_hot_matches_component(
    row: Mapping[str, Any],
    *,
    attribute: str,
    value: str,
) -> bool:
    prefixes = {
        _attribute_token(attribute),
        _attribute_token(_component_semantic_family(attribute)),
    }
    value_tokens = {_attribute_token(alias) for alias in _component_aliases(value)}
    for prefix in prefixes:
        if not prefix:
            continue
        for value_token in value_tokens:
            if value_token and _is_truthy_one_hot(row.get(f"{prefix}__{value_token}")):
                return True
    return False


def _product_matches_component(
    row: Mapping[str, Any],
    *,
    attribute: str,
    value: str,
) -> bool:
    if _product_one_hot_matches_component(row, attribute=attribute, value=value):
        return True
    product_text = _product_attribute_text(row, attribute)
    if not product_text:
        return False
    return any(alias in product_text for alias in _component_aliases(value))


def _product_matches_bundle(
    product_row: Mapping[str, Any],
    components: Sequence[Mapping[str, str]],
) -> bool:
    for component in components:
        if not _product_matches_component(
            product_row,
            attribute=component["attribute"],
            value=component["value"],
        ):
            return False
    return True


def _build_product_bundle_matches(
    products: pl.DataFrame,
    signal_bundles: pl.DataFrame,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    bundle_rows = signal_bundles.to_dicts()
    for product in products.to_dicts():
        for bundle in bundle_rows:
            components = json.loads(str(bundle["components_json"]))
            if not _product_matches_bundle(product, components):
                continue
            rows.append(
                {
                    "product_scope": product.get("product_scope"),
                    "source": product.get("source"),
                    "product_name": product.get("product_name"),
                    "product_key": product.get("product_key"),
                    "parent_product_id": product.get("parent_product_id"),
                    "pdp_url": product.get("pdp_url"),
                    "brand": product.get("brand"),
                    "category_key": product.get("category_key"),
                    "variant_count": product.get("variant_count"),
                    "image_file": product.get("image_file"),
                    **{
                        column: product.get(column)
                        for column in REVIEW_OUTPUT_COLUMNS
                        if column in product
                    },
                    "bundle_id": bundle.get("bundle_id"),
                    "bundle_label": bundle.get("bundle_label"),
                    "bundle_key": bundle.get("bundle_key"),
                    "bundle_size": bundle.get("bundle_size"),
                    "component_labels": bundle.get("component_labels"),
                    "signal_layers": bundle.get("signal_layers"),
                    "signal_score": bundle.get("signal_score"),
                    "source_files": bundle.get("source_files"),
                    "rank_weighted_gross_visibility_share": bundle.get(
                        "rank_weighted_gross_visibility_share"
                    ),
                    "rank_weighted_incremental_visibility_share": bundle.get(
                        "rank_weighted_incremental_visibility_share"
                    ),
                    "rank_weighted_visibility_density_index": bundle.get(
                        "rank_weighted_visibility_density_index"
                    ),
                    "matched_components": bundle.get("component_labels"),
                }
            )
    if not rows:
        return pl.DataFrame(schema={})
    return pl.DataFrame(rows, infer_schema_length=None).sort(
        ["product_name", "signal_score"], descending=[False, True]
    )


def _review_output_columns(df: pl.DataFrame) -> list[str]:
    columns = _columns(df)
    return [column for column in REVIEW_OUTPUT_COLUMNS if column in columns]


def _review_lookup_keys(
    row: Mapping[str, Any],
    *,
    brand_name: str,
) -> set[str]:
    keys: set[str] = set()
    for column in (
        "product_key",
        "product_name",
        "retailer_product_name",
        "title_raw",
    ):
        keys.update(_brand_stripped_product_key_aliases(row.get(column), brand_name))

    for column in (
        "parent_product_id",
        "retailer_parent_product_id",
        "listing_identity",
    ):
        value = _meaningful_text(row.get(column))
        if value is None:
            continue
        keys.add(f"id:{value}")
        normalized = _normalize_product_key(value)
        if normalized is not None:
            keys.add(normalized)

    for column in ("pdp_url", "retailer_pdp_url"):
        value = _meaningful_text(row.get(column))
        if value is None:
            continue
        keys.add(f"url:{value.rstrip('/')}")
        product_id = _retailer_product_id_from_url(value)
        if product_id is not None:
            keys.add(f"id:{product_id}")
        slug = _ulta_product_slug_from_url(value)
        if slug is not None:
            keys.update(_brand_stripped_product_key_aliases(slug, brand_name))
    return {key for key in keys if key}


def _package_integrity_value_tokens(value: Any) -> set[str]:
    tokens = {_normalize_search_text(part) for part in _split_values(value)}
    return {token for token in tokens if token}


def _package_integrity_value_covers(observed: Any, expected: Any) -> bool:
    expected_tokens = _package_integrity_value_tokens(expected)
    if not expected_tokens:
        return True
    observed_tokens = _package_integrity_value_tokens(observed)
    if not observed_tokens:
        return False
    for expected_token in expected_tokens:
        aliases = _component_aliases(expected_token)
        if expected_token not in aliases:
            aliases.add(expected_token)
        if observed_tokens.isdisjoint(aliases):
            return False
    return True


def _product_attribute_lookup_match(
    row: Mapping[str, Any],
    attribute_lookup: Mapping[str, Mapping[str, Any]],
    *,
    brand_name: str,
) -> tuple[str, Mapping[str, Any]] | None:
    for key in _review_lookup_keys(row, brand_name=brand_name):
        payload = attribute_lookup.get(key)
        if payload is not None:
            return key, payload
    return None


def _bundle_match_key_set(matches: pl.DataFrame) -> set[tuple[str, str]]:
    required_columns = {"product_key", "bundle_id"}
    if (
        matches.width == 0
        or get_row_count(matches) == 0
        or not required_columns.issubset(set(_columns(matches)))
    ):
        return set()
    keys: set[tuple[str, str]] = set()
    for row in matches.select(["product_key", "bundle_id"]).to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        bundle_id = _meaningful_text(row.get("bundle_id"))
        if product_key is not None and bundle_id is not None:
            keys.add((product_key, bundle_id))
    return keys


def _bundle_match_samples(
    matches: pl.DataFrame,
    keys: set[tuple[str, str]],
    *,
    limit: int = 8,
) -> list[dict[str, str]]:
    if (
        not keys
        or matches.width == 0
        or get_row_count(matches) == 0
        or not {"product_key", "bundle_id"}.issubset(set(_columns(matches)))
    ):
        return []
    samples: list[dict[str, str]] = []
    for row in matches.to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        bundle_id = _meaningful_text(row.get("bundle_id"))
        if product_key is None or bundle_id is None:
            continue
        if (product_key, bundle_id) not in keys:
            continue
        samples.append(
            {
                "product_name": _meaningful_text(row.get("product_name")) or "",
                "product_key": product_key,
                "bundle_id": bundle_id,
                "bundle_label": _meaningful_text(row.get("bundle_label")) or "",
            }
        )
        if len(samples) >= limit:
            break
    return samples


def _signal_fit_expectations(
    anchor_matches: pl.DataFrame,
) -> dict[str, dict[str, Any]]:
    if (
        anchor_matches.width == 0
        or get_row_count(anchor_matches) == 0
        or "product_key" not in _columns(anchor_matches)
    ):
        return {}
    grouped: dict[str, set[str]] = {}
    for row in anchor_matches.to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        label = _meaningful_text(row.get("bundle_label"))
        if product_key is None or label is None:
            continue
        grouped.setdefault(product_key, set()).add(label)
    return {
        product_key: {
            "matched_signal_count": len(labels),
            "matched_signal_labels": sorted(labels),
        }
        for product_key, labels in grouped.items()
    }


def _build_package_integrity_audit(
    *,
    brand_name: str,
    anchors: pl.DataFrame,
    owned: pl.DataFrame | None = None,
    signal_bundles: pl.DataFrame,
    anchor_matches: pl.DataFrame,
    anchor_signal_fit: pl.DataFrame,
    attribute_lookup: Mapping[str, Mapping[str, Any]],
    attribute_source_files: Sequence[str],
    pre_attribute_anchor_matches: pl.DataFrame,
) -> dict[str, Any]:
    """Build deterministic package-internal checks before the report layer."""

    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    anchor_rows = anchors.to_dicts() if anchors.width > 0 else []
    owned_row_count = (
        get_row_count(owned) if owned is not None and owned.width > 0 else 0
    )
    anchor_attribute_value_count = _attribute_value_count(
        anchors,
        columns=PRODUCT_ATTRIBUTE_COLUMNS,
    )
    owned_attribute_value_count = (
        _attribute_value_count(owned, columns=PRODUCT_ATTRIBUTE_COLUMNS)
        if owned is not None
        else 0
    )
    source_matched_anchor_count = 0
    expected_attribute_value_count = 0

    if anchor_rows and anchor_attribute_value_count == 0:
        issues.append(
            {
                "severity": "fail",
                "check_id": "brand_fit_product_attributes_nonempty",
                "message": (
                    "Current retailer anchors exist, but none have usable product "
                    "attribute values."
                ),
                "product_scope": "brand_at_retailer",
                "product_count": len(anchor_rows),
            }
        )
    if owned is not None and owned_row_count > 0 and owned_attribute_value_count == 0:
        issues.append(
            {
                "severity": "fail",
                "check_id": "brand_fit_product_attributes_nonempty",
                "message": (
                    "Manufacturer catalog products exist, but none have usable "
                    "product attribute values."
                ),
                "product_scope": "manufacturer_catalog",
                "product_count": owned_row_count,
            }
        )
    attribute_input_failures = [
        issue
        for issue in issues
        if issue.get("check_id") == "brand_fit_product_attributes_nonempty"
    ]
    checks.append(
        {
            "check_id": "brand_fit_product_attributes_nonempty",
            "status": "fail" if attribute_input_failures else "pass",
            "anchor_count": len(anchor_rows),
            "anchor_attribute_value_count": anchor_attribute_value_count,
            "manufacturer_catalog_product_count": owned_row_count,
            "manufacturer_catalog_attribute_value_count": owned_attribute_value_count,
            "failure_count": len(attribute_input_failures),
        }
    )

    for anchor in anchor_rows:
        lookup_match = _product_attribute_lookup_match(
            anchor,
            attribute_lookup,
            brand_name=brand_name,
        )
        if lookup_match is None:
            continue
        match_key, evidence = lookup_match
        source_matched_anchor_count += 1
        for column in PACKAGE_INTEGRITY_ATTRIBUTE_COLUMNS:
            expected_value = evidence.get(column)
            if _meaningful_text(expected_value) is None:
                continue
            expected_attribute_value_count += 1
            observed_value = anchor.get(column)
            if _package_integrity_value_covers(observed_value, expected_value):
                continue
            issues.append(
                {
                    "severity": "fail",
                    "check_id": "retailer_anchor_attribute_propagation",
                    "product_name": _meaningful_text(anchor.get("product_name")) or "",
                    "product_key": _meaningful_text(anchor.get("product_key")) or "",
                    "parent_product_id": (
                        _meaningful_text(anchor.get("parent_product_id")) or ""
                    ),
                    "match_key": match_key,
                    "attribute": column,
                    "expected_from_source": expected_value,
                    "observed_in_anchor": observed_value,
                    "message": (
                        "Retailer anchor did not preserve mapped attribute evidence "
                        "from the source package."
                    ),
                }
            )

    if attribute_lookup and anchor_rows and source_matched_anchor_count == 0:
        issues.append(
            {
                "severity": "warning",
                "check_id": "retailer_anchor_attribute_source_linkage",
                "message": (
                    "Mapped retailer product attributes were available, but no current "
                    "retailer anchors matched that source evidence."
                ),
            }
        )

    propagation_failures = [
        issue
        for issue in issues
        if issue.get("check_id") == "retailer_anchor_attribute_propagation"
    ]
    checks.append(
        {
            "check_id": "retailer_anchor_attribute_propagation",
            "status": "fail" if propagation_failures else "pass",
            "anchor_count": len(anchor_rows),
            "source_matched_anchor_count": source_matched_anchor_count,
            "expected_attribute_value_count": expected_attribute_value_count,
            "failure_count": len(propagation_failures),
            "source_files": list(attribute_source_files),
        }
    )

    expected_anchor_matches = _build_product_bundle_matches(anchors, signal_bundles)
    expected_match_keys = _bundle_match_key_set(expected_anchor_matches)
    actual_match_keys = _bundle_match_key_set(anchor_matches)
    missing_match_keys = expected_match_keys - actual_match_keys
    unexpected_match_keys = actual_match_keys - expected_match_keys
    if missing_match_keys or unexpected_match_keys:
        issues.append(
            {
                "severity": "fail",
                "check_id": "retailer_anchor_bundle_match_recompute",
                "message": (
                    "Final anchor bundle matches do not recompute from final anchor "
                    "attributes and selected signal bundles."
                ),
                "missing_match_count": len(missing_match_keys),
                "unexpected_match_count": len(unexpected_match_keys),
                "missing_match_samples": _bundle_match_samples(
                    expected_anchor_matches,
                    missing_match_keys,
                ),
                "unexpected_match_samples": _bundle_match_samples(
                    anchor_matches,
                    unexpected_match_keys,
                ),
            }
        )
    checks.append(
        {
            "check_id": "retailer_anchor_bundle_match_recompute",
            "status": "fail" if missing_match_keys or unexpected_match_keys else "pass",
            "expected_match_count": len(expected_match_keys),
            "actual_match_count": len(actual_match_keys),
            "missing_match_count": len(missing_match_keys),
            "unexpected_match_count": len(unexpected_match_keys),
        }
    )

    expected_fit = _signal_fit_expectations(anchor_matches)
    fit_failures = 0
    fit_rows = anchor_signal_fit.to_dicts() if anchor_signal_fit.width > 0 else []
    for row in fit_rows:
        product_key = _meaningful_text(row.get("product_key"))
        if product_key is None:
            continue
        expected = expected_fit.get(
            product_key,
            {"matched_signal_count": 0, "matched_signal_labels": []},
        )
        observed_count = _safe_int(row.get("matched_signal_count"))
        observed_labels = sorted(_split_values(row.get("matched_signal_labels")))
        expected_count = int(expected["matched_signal_count"])
        expected_labels = list(expected["matched_signal_labels"])
        if observed_count == expected_count and observed_labels == expected_labels:
            continue
        fit_failures += 1
        issues.append(
            {
                "severity": "fail",
                "check_id": "retailer_anchor_signal_fit_consistency",
                "product_name": _meaningful_text(row.get("product_name")) or "",
                "product_key": product_key,
                "expected_matched_signal_count": expected_count,
                "observed_matched_signal_count": observed_count,
                "expected_matched_signal_labels": expected_labels,
                "observed_matched_signal_labels": observed_labels,
                "message": (
                    "Anchor signal-fit summary is inconsistent with final bundle "
                    "match rows."
                ),
            }
        )
    checks.append(
        {
            "check_id": "retailer_anchor_signal_fit_consistency",
            "status": "fail" if fit_failures else "pass",
            "anchor_signal_fit_rows": len(fit_rows),
            "failure_count": fit_failures,
        }
    )

    pre_match_keys = _bundle_match_key_set(pre_attribute_anchor_matches)
    recovered_match_keys = actual_match_keys - pre_match_keys
    removed_stale_match_keys = pre_match_keys - actual_match_keys
    checks.append(
        {
            "check_id": "retailer_attribute_enrichment_effect",
            "status": "pass",
            "pre_enrichment_match_count": len(pre_match_keys),
            "post_enrichment_match_count": len(actual_match_keys),
            "recovered_match_count": len(recovered_match_keys),
            "removed_stale_match_count": len(removed_stale_match_keys),
            "recovered_match_samples": _bundle_match_samples(
                anchor_matches,
                recovered_match_keys,
            ),
            "removed_stale_match_samples": _bundle_match_samples(
                pre_attribute_anchor_matches,
                removed_stale_match_keys,
            ),
        }
    )

    fail_count = sum(1 for issue in issues if issue.get("severity") == "fail")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    status = "pass"
    if fail_count:
        status = "fail"
    elif warning_count:
        status = "pass_with_warnings"
    return {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "check_count": len(checks),
            "failure_count": fail_count,
            "warning_count": warning_count,
            "anchor_count": len(anchor_rows),
            "source_matched_anchor_count": source_matched_anchor_count,
            "expected_attribute_value_count": expected_attribute_value_count,
            "pre_enrichment_anchor_bundle_matches": len(pre_match_keys),
            "post_enrichment_anchor_bundle_matches": len(actual_match_keys),
            "recovered_anchor_bundle_matches_after_attribute_enrichment": (
                len(recovered_match_keys)
            ),
            "removed_stale_anchor_bundle_matches_after_attribute_enrichment": (
                len(removed_stale_match_keys)
            ),
        },
        "checks": checks,
        "issues": issues,
    }


def _review_text_snippet_count(row: Mapping[str, Any]) -> int:
    direct_count = 0
    for polarity in ("positive", "negative"):
        if (
            _meaningful_text(row.get(f"reviews_{polarity}_headline")) is not None
            or _meaningful_text(row.get(f"reviews_{polarity}_comment")) is not None
        ):
            direct_count += 1
    for index in range(1, MAX_EXPORTED_REVIEW_SNIPPETS + 1):
        if (
            _meaningful_text(row.get(f"review_{index}_headline")) is not None
            or _meaningful_text(row.get(f"review_{index}_comment")) is not None
        ):
            direct_count += 1
    source_count = _safe_int(row.get("review_snippet_count"))
    return max(direct_count, source_count)


def _has_rating_or_review_count(row: Mapping[str, Any]) -> bool:
    return _safe_float(row.get("rating")) > 0 or _safe_int(row.get("review_count")) > 0


def _has_review_evidence(row: Mapping[str, Any]) -> bool:
    return _has_rating_or_review_count(row) or _review_text_snippet_count(row) > 0


def _review_evidence_score(row: Mapping[str, Any]) -> int:
    return (
        _review_text_snippet_count(row) * 100
        + min(_safe_int(row.get("review_count")), 10)
        + (1 if _safe_float(row.get("rating")) > 0 else 0)
    )


def _review_payload(
    row: Mapping[str, Any],
    *,
    source_file: str | None,
) -> dict[str, Any]:
    payload = {
        column: row.get(column)
        for column in REVIEW_OUTPUT_COLUMNS
        if column != "review_evidence_source_file"
    }
    payload["review_evidence_source_file"] = source_file
    return payload


def _product_evidence_column_candidates(attribute_column: str) -> list[str]:
    candidates = PRODUCT_EVIDENCE_ATTRIBUTE_COLUMNS.get(attribute_column, ())
    generic = (
        attribute_column,
        attribute_column.replace("_", " "),
        attribute_column.replace(" ", "_"),
    )
    return list(dict.fromkeys([*candidates, *generic]))


def _product_attribute_evidence_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for attribute_column in PRODUCT_ATTRIBUTE_COLUMNS:
        for source_column in _product_evidence_column_candidates(attribute_column):
            if source_column not in row:
                continue
            value = row.get(source_column)
            if _meaningful_text(value) is None:
                continue
            payload[attribute_column] = value
            break
    return payload


def _product_attribute_evidence_score(payload: Mapping[str, Any]) -> int:
    important_columns = {"form", "finish", "coverage", "benefits", "skin benefits"}
    score = 0
    for column, value in payload.items():
        if _meaningful_text(value) is None:
            continue
        score += 3 if column in important_columns else 1
    return score


def _load_retailer_product_attribute_lookup(
    innovation_package_dir: Path,
    *,
    brand_name: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load package-facing retailer attributes keyed for brand-at-retailer products."""

    lookup: dict[str, dict[str, Any]] = {}
    source_files: list[str] = []
    for source_index, filename in enumerate(PRODUCT_EVIDENCE_SOURCE_FILE_CANDIDATES):
        path = innovation_package_dir / filename
        products = _read_csv_if_exists(path)
        if products.width == 0 or get_row_count(products) == 0:
            continue
        products = _filter_brand_if_possible(products, brand_name)
        source_has_payload = False
        for row in products.to_dicts():
            payload = _product_attribute_evidence_payload(row)
            score = _product_attribute_evidence_score(payload)
            if score <= 0:
                continue
            source_has_payload = True
            payload["_product_attribute_evidence_score"] = score
            payload["_product_attribute_source_priority"] = (
                len(PRODUCT_EVIDENCE_SOURCE_FILE_CANDIDATES) - source_index
            )
            for key in _review_lookup_keys(row, brand_name=brand_name):
                previous = lookup.get(key)
                if previous is None:
                    lookup[key] = payload
                    continue
                previous_score = int(
                    previous.get("_product_attribute_evidence_score") or 0
                )
                previous_priority = int(
                    previous.get("_product_attribute_source_priority") or 0
                )
                payload_priority = int(
                    payload.get("_product_attribute_source_priority") or 0
                )
                if (score, payload_priority) > (previous_score, previous_priority):
                    lookup[key] = payload
        if source_has_payload:
            source_files.append(filename)

    cleaned_lookup: dict[str, dict[str, Any]] = {}
    for key, payload in lookup.items():
        cleaned_lookup[key] = {
            column: value
            for column, value in payload.items()
            if not column.startswith("_")
        }
    return cleaned_lookup, source_files


def _enrich_products_with_retailer_product_attributes(
    products: pl.DataFrame,
    attribute_lookup: Mapping[str, Mapping[str, Any]],
    *,
    brand_name: str,
) -> pl.DataFrame:
    if products.width == 0 or get_row_count(products) == 0 or not attribute_lookup:
        return products

    rows: list[dict[str, Any]] = []
    for product in products.to_dicts():
        output = dict(product)
        attribute_row = None
        for key in _review_lookup_keys(product, brand_name=brand_name):
            attribute_row = attribute_lookup.get(key)
            if attribute_row is not None:
                break
        if attribute_row is not None:
            for column in PRODUCT_ATTRIBUTE_COLUMNS:
                value = attribute_row.get(column)
                if _meaningful_text(value) is not None:
                    output[column] = value
        rows.append(output)
    return pl.DataFrame(rows, infer_schema_length=None)


def _load_retailer_review_lookup(
    innovation_package_dir: Path,
    *,
    brand_name: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load retailer review evidence keyed for brand-at-retailer products."""

    lookup: dict[str, dict[str, Any]] = {}
    source_files: list[str] = []
    for filename in REVIEW_SOURCE_FILE_CANDIDATES:
        path = innovation_package_dir / filename
        products = _read_csv_if_exists(path)
        if products.width == 0 or get_row_count(products) == 0:
            continue
        available_review_columns = [
            column for column in REVIEW_OUTPUT_COLUMNS if column in _columns(products)
        ]
        if not available_review_columns:
            continue
        source_files.append(filename)
        products = _filter_brand_if_possible(products, brand_name)
        for row in products.to_dicts():
            payload = _review_payload(row, source_file=filename)
            if not _has_review_evidence(payload):
                continue
            score = _review_evidence_score(payload)
            payload["_review_evidence_score"] = score
            for key in _review_lookup_keys(row, brand_name=brand_name):
                previous = lookup.get(key)
                if previous is None or score > int(
                    previous.get("_review_evidence_score") or 0
                ):
                    lookup[key] = payload

    cleaned_lookup: dict[str, dict[str, Any]] = {}
    for key, payload in lookup.items():
        cleaned_lookup[key] = {
            column: value
            for column, value in payload.items()
            if not column.startswith("_")
        }
    return cleaned_lookup, source_files


def _enrich_products_with_retailer_reviews(
    products: pl.DataFrame,
    review_lookup: Mapping[str, Mapping[str, Any]],
    *,
    brand_name: str,
) -> pl.DataFrame:
    if products.width == 0 or get_row_count(products) == 0:
        return products
    existing_review_columns = _review_output_columns(products)
    if not review_lookup and not existing_review_columns:
        return products

    rows: list[dict[str, Any]] = []
    for product in products.to_dicts():
        output = dict(product)
        review_row = None
        for key in _review_lookup_keys(product, brand_name=brand_name):
            review_row = review_lookup.get(key)
            if review_row is not None:
                break
        for column in REVIEW_OUTPUT_COLUMNS:
            existing_value = output.get(column)
            review_value = review_row.get(column) if review_row is not None else None
            output[column] = (
                review_value
                if _meaningful_text(review_value) is not None
                else existing_value
            )
        rows.append(output)
    return pl.DataFrame(rows, infer_schema_length=None)


def _brand_at_retailer_review_validation_df(anchors: pl.DataFrame) -> pl.DataFrame:
    output_columns = list(
        dict.fromkeys(
            [
                *CORE_PRODUCT_COLUMNS,
                *ANCHOR_OUTPUT_EXTRA_COLUMNS,
                "anchor_status",
                *REVIEW_OUTPUT_COLUMNS,
            ]
        )
    )
    available_columns = [
        column for column in output_columns if column in _columns(anchors)
    ]
    schema = {
        column: REVIEW_OUTPUT_SCHEMA.get(column, pl.Utf8)
        for column in output_columns
        if column in REVIEW_OUTPUT_COLUMNS
        or column in CORE_PRODUCT_COLUMNS
        or column in ANCHOR_OUTPUT_EXTRA_COLUMNS
        or column == "anchor_status"
    }
    schema["stored_review_text_count"] = pl.Int64
    if anchors.width == 0 or get_row_count(anchors) == 0:
        return pl.DataFrame(schema=schema)

    rows: list[dict[str, Any]] = []
    for row in anchors.select(available_columns).to_dicts():
        text_count = _review_text_snippet_count(row)
        if not _has_rating_or_review_count(row) and text_count == 0:
            continue
        output = dict(row)
        output["stored_review_text_count"] = text_count
        rows.append(output)
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, infer_schema_length=None)


def _load_top_seller_product_lookup(
    innovation_package_dir: Path,
    *,
    brand_name: str,
) -> dict[str, dict[str, Any]]:
    """Load top-seller product rows by product key and parent id when available."""

    products = _read_csv_if_exists(innovation_package_dir / "top_seller_products.csv")
    if products.width == 0 or get_row_count(products) == 0:
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    for row in products.to_dicts():
        keys = {
            _normalize_product_key(row.get("product_name")),
            _brand_stripped_product_key(row.get("product_name"), brand_name),
        }
        parent_id = _meaningful_text(row.get("parent_product_id"))
        if parent_id:
            keys.add(f"id:{parent_id}")
        for key in keys:
            if key:
                lookup.setdefault(key, row)
    return lookup


def _build_anchor_signal_fit(
    anchors: pl.DataFrame,
    anchor_matches: pl.DataFrame,
    top_seller_lookup: Mapping[str, Mapping[str, Any]] | None = None,
) -> pl.DataFrame:
    """Summarize whether current retailer anchors explain selected retailer signals."""

    schema = {
        "product_name": pl.Utf8,
        "product_key": pl.Utf8,
        "parent_product_id": pl.Utf8,
        "pdp_url": pl.Utf8,
        "brand": pl.Utf8,
        "category_key": pl.Utf8,
        "anchor_status": pl.Utf8,
        "top_seller_sort_present": pl.Boolean,
        "top_seller_pareto_bucket": pl.Utf8,
        "top_seller_pareto_rank": pl.Float64,
        "top_seller_sales_share": pl.Float64,
        "top_seller_status": pl.Utf8,
        "matched_signal_count": pl.Int64,
        "winning_now_signal_count": pl.Int64,
        "innovation_signal_count": pl.Int64,
        "rank_weighted_visibility_signal_count": pl.Int64,
        "matched_signal_labels": pl.Utf8,
        "fit_status": pl.Utf8,
        "commercial_read": pl.Utf8,
    }
    schema.update(REVIEW_OUTPUT_SCHEMA)
    if anchors.width == 0 or get_row_count(anchors) == 0:
        return pl.DataFrame(schema=schema)

    grouped: dict[str, list[dict[str, Any]]] = {}
    if anchor_matches.width > 0 and get_row_count(anchor_matches) > 0:
        for match in anchor_matches.to_dicts():
            product_key = _meaningful_text(match.get("product_key"))
            if product_key is None:
                continue
            grouped.setdefault(product_key, []).append(match)

    rows: list[dict[str, Any]] = []
    top_seller_lookup = top_seller_lookup or {}
    for anchor in anchors.select(
        [
            col
            for col in [*_product_output_columns(anchors), "anchor_status"]
            if col in _columns(anchors)
        ]
    ).to_dicts():
        product_key = _meaningful_text(anchor.get("product_key")) or ""
        parent_id = _meaningful_text(anchor.get("parent_product_id")) or ""
        top_seller_row = top_seller_lookup.get(product_key) or top_seller_lookup.get(
            f"id:{parent_id}"
        )
        top_seller_present = top_seller_row is not None
        matches = grouped.get(product_key, [])
        signal_labels = sorted(
            {
                str(match.get("bundle_label"))
                for match in matches
                if _meaningful_text(match.get("bundle_label"))
            }
        )
        winning_count = sum(
            1
            for match in matches
            if "winning_now" in str(match.get("signal_layers") or "")
        )
        innovation_count = sum(
            1
            for match in matches
            if "innovation" in str(match.get("signal_layers") or "")
        )
        visibility_count = sum(
            1
            for match in matches
            if _safe_float(match.get("rank_weighted_gross_visibility_share")) > 0
            or _safe_float(match.get("rank_weighted_incremental_visibility_share")) > 0
        )
        matched_count = len(signal_labels)
        if matched_count:
            fit_status = "current_anchor_matches_selected_retailer_signals"
            commercial_read = (
                "Current retailer presence is explained by the selected retailer "
                "signal mix."
            )
        elif top_seller_present:
            fit_status = "top_seller_anchor_not_explained_by_selected_retailer_signals"
            commercial_read = (
                "This anchor appears in the source top-seller sort, but the "
                "selected attribute signal mix does not explain it. Treat this "
                "as commercially important current evidence outside the selected "
                "bundle logic, not as brand/category misalignment."
            )
        else:
            fit_status = "current_anchor_not_explained_by_selected_retailer_signals"
            commercial_read = (
                "Current retailer presence is real, but the selected attribute "
                "signal mix does not explain this anchor. Do not infer weak "
                "commercial relevance from absence of bundle support; treat it as "
                "a possible brand, price, promo, review, distribution, or missing-"
                "taxonomy explanation."
            )
        rows.append(
            {
                **anchor,
                "top_seller_sort_present": top_seller_present,
                "top_seller_pareto_bucket": (
                    top_seller_row.get("pareto_bucket") if top_seller_row else None
                ),
                "top_seller_pareto_rank": (
                    _safe_float(top_seller_row.get("pareto_rank"))
                    if top_seller_row
                    else None
                ),
                "top_seller_sales_share": (
                    _safe_float(top_seller_row.get("sales_share"))
                    if top_seller_row
                    else None
                ),
                "top_seller_status": (
                    top_seller_row.get("top_seller_status") if top_seller_row else None
                ),
                "matched_signal_count": matched_count,
                "winning_now_signal_count": winning_count,
                "innovation_signal_count": innovation_count,
                "rank_weighted_visibility_signal_count": visibility_count,
                "matched_signal_labels": CSV_LIST_SEPARATOR.join(signal_labels),
                "fit_status": fit_status,
                "commercial_read": commercial_read,
            }
        )

    return pl.DataFrame(rows, schema=schema, strict=False)


def _bundle_ids_by_product(matches: pl.DataFrame) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    if matches.width == 0 or get_row_count(matches) == 0:
        return grouped
    for row in matches.select(["product_key", "bundle_id"]).to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        bundle_id = _meaningful_text(row.get("bundle_id"))
        if product_key is None or bundle_id is None:
            continue
        grouped.setdefault(product_key, set()).add(bundle_id)
    return grouped


def _product_output_columns(df: pl.DataFrame) -> list[str]:
    columns = _columns(df)
    one_hot_prefixes = set(ONE_HOT_ATTRIBUTE_PREFIXES)
    one_hot_columns = [
        column
        for column in columns
        if "__" in column and column.split("__", maxsplit=1)[0] in one_hot_prefixes
    ]
    wanted = [
        *CORE_PRODUCT_COLUMNS,
        *PRODUCT_ATTRIBUTE_COLUMNS,
        *one_hot_columns,
        *REVIEW_OUTPUT_COLUMNS,
    ]
    output: list[str] = []
    seen: set[str] = set()
    for column in wanted:
        if column in columns and column not in seen:
            output.append(column)
            seen.add(column)
    return output


def _candidate_rows(
    missing_owned: pl.DataFrame,
    manufacturer_matches: pl.DataFrame,
    anchor_matches: pl.DataFrame,
    *,
    max_reference_candidates: int,
) -> pl.DataFrame:
    if manufacturer_matches.width == 0 or get_row_count(manufacturer_matches) == 0:
        return pl.DataFrame(schema={})
    anchor_bundle_ids = (
        {
            str(value)
            for value in anchor_matches.select("bundle_id").to_series().to_list()
            if _meaningful_text(value)
        }
        if anchor_matches.width > 0 and get_row_count(anchor_matches) > 0
        else set()
    )
    missing_keys = _key_set(missing_owned)
    product_metadata = {
        str(row["product_key"]): row
        for row in missing_owned.select(
            _product_output_columns(missing_owned)
        ).to_dicts()
        if _meaningful_text(row.get("product_key"))
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in manufacturer_matches.to_dicts():
        product_key = _meaningful_text(row.get("product_key"))
        if product_key is None or product_key not in missing_keys:
            continue
        grouped.setdefault(product_key, []).append(row)
    rows: list[dict[str, Any]] = []
    for product_key, matches in grouped.items():
        bundle_ids = sorted(
            {
                str(match["bundle_id"])
                for match in matches
                if _meaningful_text(match.get("bundle_id"))
            }
        )
        bundle_labels = sorted(
            {
                str(match["bundle_label"])
                for match in matches
                if _meaningful_text(match.get("bundle_label"))
            }
        )
        winning_count = sum(
            1
            for match in matches
            if "winning_now" in str(match.get("signal_layers") or "")
        )
        innovation_count = sum(
            1
            for match in matches
            if "innovation" in str(match.get("signal_layers") or "")
        )
        visibility_count = sum(
            1
            for match in matches
            if _safe_float(match.get("rank_weighted_gross_visibility_share")) > 0
            or _safe_float(match.get("rank_weighted_incremental_visibility_share")) > 0
        )
        overlap_count = sum(
            1
            for match in matches
            if "winning_now" in str(match.get("signal_layers") or "")
            and "innovation" in str(match.get("signal_layers") or "")
        )
        anchor_overlap = len(set(bundle_ids).intersection(anchor_bundle_ids))
        signal_score = sum(_safe_float(match.get("signal_score")) for match in matches)
        metadata = product_metadata.get(product_key, {})
        variant_count = _safe_int(metadata.get("variant_count"))
        score = signal_score + anchor_overlap * 8 + overlap_count * 5
        rationale: list[str] = []
        if winning_count:
            rationale.append("expresses winning-now retailer signals")
        if innovation_count:
            rationale.append("expresses emerging innovation signals")
        if visibility_count:
            rationale.append("has rank-weighted visibility support")
        if overlap_count:
            rationale.append(
                "matches signals present in both current and recent layers"
            )
        if anchor_overlap:
            rationale.append("shares signal support with current retailer anchors")
        if variant_count >= 24:
            score += 4
            rationale.append("broad variant range")
        elif variant_count >= 12:
            score += 2
            rationale.append("credible variant range")
        rows.append(
            {
                **metadata,
                "reference_score": round(score, 6),
                "matched_bundle_count": len(bundle_ids),
                "winning_now_bundle_count": winning_count,
                "innovation_bundle_count": innovation_count,
                "rank_weighted_visibility_bundle_count": visibility_count,
                "overlap_bundle_count": overlap_count,
                "anchor_bundle_overlap_count": anchor_overlap,
                "matched_bundle_ids": CSV_LIST_SEPARATOR.join(bundle_ids),
                "matched_bundle_labels": CSV_LIST_SEPARATOR.join(bundle_labels),
                "reference_rationale": CSV_LIST_SEPARATOR.join(rationale),
            }
        )
    if not rows:
        return pl.DataFrame(schema={})
    return (
        pl.DataFrame(rows)
        .sort(
            ["reference_score", "variant_count", "product_name"],
            descending=[True, True, False],
        )
        .head(max_reference_candidates)
    )


def _image_index_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            schema={
                "image_scope": pl.Utf8,
                "parent_product_id": pl.Utf8,
                "product_name": pl.Utf8,
                "image_file": pl.Utf8,
                "image_available": pl.Boolean,
                "image_source": pl.Utf8,
                "inspect_rule": pl.Utf8,
            }
        )
    return pl.DataFrame(rows, strict=False, infer_schema_length=None)


def _format_share(value: Any) -> str:
    share = _safe_float(value)
    if share <= 0:
        return ""
    return f"{share * 100:.1f}%"


def _metric_text(
    row: Mapping[str, Any],
    *,
    count_column: str,
    share_column: str,
    rest_count_column: str,
    rest_share_column: str,
    brand_count_column: str,
    product_label: str,
    rest_label: str,
) -> str:
    count = _safe_int(row.get(count_column))
    brand_count = _safe_int(row.get(brand_count_column))
    if count <= 0:
        return ""
    share = _format_share(row.get(share_column))
    rest_count = _safe_int(row.get(rest_count_column))
    rest_share = _format_share(row.get(rest_share_column))
    parts = [f"{count} {product_label}"]
    if share:
        parts.append(f"({share})")
    if brand_count > 0:
        parts.append(f"across {brand_count} brands")
    if rest_count > 0:
        rest = f"versus {rest_count} {rest_label}"
        if rest_share:
            rest = f"{rest} ({rest_share})"
        parts.append(rest)
    return " ".join(parts)


def _short_examples(value: Any, *, max_items: int = 4) -> str:
    items = _split_values(value)
    return CSV_LIST_SEPARATOR.join(items[:max_items])


def _signal_read(row: Mapping[str, Any]) -> str:
    label = _meaningful_text(row.get("bundle_label")) or "this signal"
    layers = str(row.get("signal_layers") or "")
    recent_count = _safe_int(row.get("count_recent"))
    recent_brands = _safe_int(row.get("recent_brand_count"))
    top_count = _safe_int(row.get("count_top_seller"))
    top_brands = _safe_int(row.get("top_seller_brand_count"))
    has_winning = "winning_now" in layers
    has_innovation = "innovation" in layers
    has_visibility = _row_has_rank_weighted_visibility(row)
    if has_winning and has_innovation:
        read = (
            f"{label} connects today's top-selling shelf with recent arrivals. "
            "Treat it as the cleanest bridge from retailer signal to brand fit."
        )
    elif has_winning:
        read = (
            f"{label} is over-represented among current top sellers. "
            "Treat it as a proven shelf pattern, not necessarily a novelty claim."
        )
    else:
        read = (
            f"{label} is over-represented in recent arrivals. "
            "Treat it as emerging until top-seller evidence catches up."
        )
    if has_visibility:
        read = (
            f"{read} Rank-weighted visibility metrics quantify how much ranked "
            "shelf mass the same bundle carries, including any incremental share "
            "after overlap removal."
        )
    if (recent_count and recent_count < 6) or (top_count and top_count < 6):
        read = f"{read} Counts are thin, so use as supporting evidence."
    if (recent_brands and recent_brands < 4) or (top_brands and top_brands < 4):
        read = f"{read} Brand breadth is limited."
    return read


def _rank_weighted_visibility_metric_text(row: Mapping[str, Any]) -> str:
    if not _row_has_rank_weighted_visibility(row):
        return ""
    incremental = _format_share(row.get("rank_weighted_incremental_visibility_share"))
    gross = _format_share(row.get("rank_weighted_gross_visibility_share"))
    sku_count = _safe_int(row.get("rank_weighted_visibility_sku_count"))
    brand_count = _safe_int(row.get("rank_weighted_visibility_brand_count"))
    times_selected = _safe_int(row.get("rank_weighted_visibility_alpha_scenarios"))
    parts = []
    if incremental:
        parts.append(f"{incremental} incremental rank-weighted visibility")
    if gross:
        parts.append(f"{gross} gross visibility")
    if sku_count:
        parts.append(f"{sku_count} products")
    if brand_count:
        parts.append(f"across {brand_count} brands")
    if times_selected:
        parts.append(f"selected under {times_selected} alpha scenarios")
    return "; ".join(parts)


def _signal_type(row: Mapping[str, Any]) -> str:
    layers = str(row.get("signal_layers") or "")
    has_winning = "winning_now" in layers
    has_innovation = "innovation" in layers
    has_visibility = _row_has_rank_weighted_visibility(row)
    if has_winning and has_innovation:
        base = "current winners and recent arrivals"
        return f"{base} with rank-weighted visibility" if has_visibility else base
    if has_winning:
        base = "current top sellers"
        return f"{base} with rank-weighted visibility" if has_visibility else base
    base = "recent arrivals"
    return f"{base} with rank-weighted visibility" if has_visibility else base


def _plain_language_signal_guide(signal_bundles: pl.DataFrame) -> pl.DataFrame:
    if signal_bundles.width == 0 or get_row_count(signal_bundles) == 0:
        return pl.DataFrame(schema={})
    rows: list[dict[str, Any]] = []
    for row in signal_bundles.to_dicts():
        rows.append(
            {
                "signal_name": row.get("bundle_label"),
                "signal_type": _signal_type(row),
                "plain_english_read": _signal_read(row),
                "current_shelf_evidence": _metric_text(
                    row,
                    count_column="count_top_seller",
                    share_column="pct_top_seller",
                    rest_count_column="count_other",
                    rest_share_column="pct_other",
                    brand_count_column="top_seller_brand_count",
                    product_label="top sellers",
                    rest_label="other products",
                ),
                "recent_arrival_evidence": _metric_text(
                    row,
                    count_column="count_recent",
                    share_column="pct_recent",
                    rest_count_column="count_rest",
                    rest_share_column="pct_rest",
                    brand_count_column="recent_brand_count",
                    product_label="recent products",
                    rest_label="rest products",
                ),
                "rank_weighted_visibility_evidence": _rank_weighted_visibility_metric_text(
                    row
                ),
                "current_examples": _short_examples(
                    row.get("top_seller_example_products")
                    or row.get("top_seller_top_pareto_products")
                ),
                "recent_examples": _short_examples(
                    row.get("recent_example_products")
                    or row.get("recent_top_pareto_products")
                ),
                "rank_weighted_visibility_examples": _short_examples(
                    row.get("rank_weighted_visibility_top_products")
                ),
                "audit_bundle_id": row.get("bundle_id"),
            }
        )
    return pl.DataFrame(rows)


def _attribute_coverage_df(
    products: pl.DataFrame,
    *,
    product_scope: str,
) -> pl.DataFrame:
    total = get_row_count(products) if products.width > 0 else 0
    rows: list[dict[str, Any]] = []
    for column in PRODUCT_ATTRIBUTE_COLUMNS:
        values: list[str] = []
        if products.width > 0 and column in _columns(products):
            for value in products.select(column).to_series().to_list():
                text = _meaningful_text(value)
                if text is not None:
                    values.append(text)
        non_missing = len(values)
        coverage = (non_missing / total) if total else 0.0
        if coverage >= 0.8:
            read = "well populated"
        elif coverage >= 0.4:
            read = "partially populated"
        else:
            read = "sparse - absence of a match may reflect missing mapped attributes"
        rows.append(
            {
                "product_scope": product_scope,
                "attribute_column": column,
                "products_with_value": non_missing,
                "total_products": total,
                "coverage_pct": round(coverage * 100, 1),
                "coverage_read": read,
                "sample_values": CSV_LIST_SEPARATOR.join(sorted(set(values))[:8]),
            }
        )
    return pl.DataFrame(rows)


def _combined_attribute_coverage(
    *,
    anchors: pl.DataFrame,
    owned: pl.DataFrame,
) -> pl.DataFrame:
    frames = [
        _attribute_coverage_df(anchors, product_scope="brand_at_retailer"),
        _attribute_coverage_df(owned, product_scope="manufacturer_catalog"),
    ]
    return pl.concat(frames, how="vertical")


def _brand_fit_context_text(
    summary: Mapping[str, Any],
    plain_signal_guide: pl.DataFrame,
    attribute_coverage: pl.DataFrame,
) -> str:
    top_candidates = summary.get("top_reference_candidates") or []
    top_candidate = top_candidates[0] if top_candidates else {}
    candidate_name = top_candidate.get("product_name") or "No clear candidate"
    candidate_matches = top_candidate.get("matched_bundle_labels") or ""
    sparse_rows = (
        attribute_coverage.filter(pl.col("coverage_pct") < 40.0)
        if attribute_coverage.width > 0
        else pl.DataFrame(schema={})
    )
    sparse_count = get_row_count(sparse_rows) if sparse_rows.width > 0 else 0
    primary_signals = (
        plain_signal_guide.select(["signal_name", "plain_english_read"]).head(5)
        if plain_signal_guide.width > 0
        else pl.DataFrame(schema={})
    )
    signal_lines = []
    for row in primary_signals.to_dicts() if primary_signals.width > 0 else []:
        signal_lines.append(f"- {row['signal_name']}: {row['plain_english_read']}")
    if not signal_lines:
        signal_lines.append("- No selected retailer signals were available.")
    signal_text = "\n".join(signal_lines)
    source_review_rule = ""
    if _source_review_evidence_package_files(summary):
        source_review_rule = (
            "\nUse copied source review evidence files only as retailer-level "
            "secondary evidence behind the source signals. They are not "
            "brand-specific unless the same product also appears in "
            "`brand_at_retailer_review_validation.csv`."
        )
    web_shelf_section = ""
    if _source_web_shelf_package_files(summary):
        web_shelf_section = """
## Web-shelf evidence rule

Use copied source web-shelf audit files only to validate the rank-weighted visibility metrics attached to selected retailer signals. They should not become a separate report section or a new signal family.
"""
    source_web_shelf_count_line = ""
    if summary["counts"].get("source_web_shelf_artifact_files", 0):
        source_web_shelf_count_line = (
            "- Source web-shelf audit files copied: "
            f"{summary['counts'].get('source_web_shelf_artifact_files', 0)}.\n"
        )
    source_review_evidence_count_line = ""
    if summary["counts"].get("source_review_evidence_artifact_files", 0):
        source_review_evidence_count_line = (
            "- Source review evidence files copied: "
            f"{summary['counts'].get('source_review_evidence_artifact_files', 0)}.\n"
        )

    return f"""# Brand Fit Context Guide

Use this file to write the final Brand Fit report in human language.

## Objective

Explain whether {summary['brand_name']} has a credible fit with the {summary['retailer_label']} {summary['category_label']} shelf signals. The reader should understand:

1. What the retailer shelf appears to reward.
2. Whether {summary['brand_name']} is already present in that shelf logic at {summary['retailer_label']}.
3. Which {summary['brand_name']} catalog products credibly support the story.
4. Which gaps prevent a stronger claim.

## Plain-language terms to use

- Use "retailer signal" instead of "bundle".
- Use "current {summary['brand_name']} at {summary['retailer_label']}" or "current retailer presence" instead of "anchor layer".
- Use "{summary['brand_name']} catalog product" instead of "manufacturer layer".
- Use "same signal", "partial match", or "gap" instead of "overlap", "intersection", or "mapped internally".
- Use "form" as the attribute name for product delivery type, such as stick, liquid, pressed powder, wand, tube, compact, or balm.
- Do not print internal IDs such as `bundle_...` in the final narrative. Use them only for audit tracing.

## Current package read

- Current retailer products from {summary['brand_name']} at {summary['retailer_label']}: {summary['counts']['retailer_brand_anchor_products']}.
- Current retailer products that match selected shelf signals: {summary['counts'].get('retailer_brand_anchor_products_with_signal_matches', 0)}.
- Current retailer products not explained by selected shelf signals: {summary['counts'].get('retailer_brand_anchor_products_without_signal_matches', 0)}.
- Current top-seller-sort retailer products not explained by selected shelf signals: {summary['counts'].get('retailer_top_seller_anchor_products_without_signal_matches', 0)}.
- Current retailer products with rating or review-count evidence: {summary['counts'].get('retailer_brand_anchor_products_with_rating_or_review_count', 0)}.
- Current retailer products with review text snippets: {summary['counts'].get('retailer_brand_anchor_products_with_review_text', 0)} products / {summary['counts'].get('retailer_brand_anchor_review_text_snippets', 0)} stored snippets.
- {summary['brand_name']} catalog products in this category: {summary['counts']['manufacturer_catalog_products']}.
- Candidate catalog references found: {summary['counts']['reference_candidates']}.
- Signals with rank-weighted visibility metrics: {summary['counts'].get('signal_bundles_with_rank_weighted_visibility', 0)}.
{source_web_shelf_count_line}{source_review_evidence_count_line}- Package integrity status: {summary.get('package_integrity', {}).get('status', 'unknown')}.
- Live retailer brand-page products added as anchors: {summary['counts'].get('retailer_live_products_added_as_anchors', 0)}.
- Cached retailer products removed because absent from live brand page: {summary['counts'].get('retailer_live_cached_products_removed_as_anchors', 0)}.
- Top candidate: {candidate_name}.
- Top candidate signal matches: {candidate_matches or 'none'}.

## Primary retailer signals

{signal_text}

## Attribute completeness warning

The mapped brand catalog has {sparse_count} sparse attribute fields across current-retailer and manufacturer-catalog products. If a product fails to match a signal that depends on sparse fields, say "the package does not show support" rather than "the product lacks the feature." Use `attribute_coverage.csv` to decide when a missing match may be a mapping limitation.

## Review evidence rule

Use `brand_at_retailer_review_validation.csv` only to validate current {summary['brand_name']} products already present at {summary['retailer_label']}. Review text can strengthen or complicate the "reason to trust" for current anchors, but it does not create retailer signals and it should not be used as proof of sell-out demand.
{source_review_rule}
{web_shelf_section}

## Writing rule

Every section should answer "so what?" Avoid evidence dumps. A good sentence names the retailer signal, names the {summary['brand_name']} product evidence, and states the commercial implication plus caveat.
Use broad baseline attributes only as context. Do not turn broad category facts into recommendations.
"""


def _build_prompt(summary: Mapping[str, Any]) -> str:
    title = (
        f"{summary['brand_name']} Brand Fit for "
        f"{summary['retailer_label']} {summary['category_label'].title()} "
        "Retailer Signals"
    )
    web_shelf_prompt_line = _web_shelf_prompt_line(summary)
    review_evidence_prompt_line = _review_evidence_prompt_line(summary)
    web_shelf_file_lines = _web_shelf_file_lines(summary)
    review_evidence_file_lines = _review_evidence_file_lines(summary)
    if web_shelf_file_lines:
        web_shelf_file_lines = f"{web_shelf_file_lines}\n"
    if review_evidence_file_lines:
        review_evidence_file_lines = f"{review_evidence_file_lines}\n"
    return f"""The task is to write a buyer-readable Brand Fit report for {summary['brand_name']} in {summary['retailer_label']} {summary['category_label']}. The report must connect three things: what the {summary['retailer_label']} shelf appears to reward, where {summary['brand_name']} is already present at {summary['retailer_label']}, and which {summary['brand_name']} catalog products credibly fit those retailer signals.

Report title:
{title}

You are receiving a Brand Fit package, not a final report. Use the package data to write the final report text. Use images only as inspection evidence while reasoning; do not embed images in the output. The final reader is commercial, not technical: make every point understandable without knowing how the data was produced.

Core logic:
- The existing retailer innovation package is the source of truth for retailer signals.
- Read `source_innovation_brief.md` first when it is present. It is the narrative interpretation of the source innovation package and contains category-specific caveats that raw signal rows do not carry.
- Read `brand_fit_context.md` second. It translates the package into buyer-readable terms and explains the intended Brand Fit logic.
- Check `package_integrity.json` before trusting the package tables. If the status is not `pass`, use the integrity issues as data caveats and do not treat report-level consistency as evidence that the package is true.
- Check `package_warnings.json` immediately after `package_integrity.json`. These are builder-computed warnings and data caveats. Preserve relevant warnings, but do not invent package-integrity caveats outside this file.
- Use `plain_language_signal_guide.csv` before `signal_bundles.csv` when writing prose. It contains human-readable signal names, evidence summaries, examples, and caveats.
- Use `signal_bundles.csv` only as the audit table behind the signal guide. Do not discover new signals, invent new signals, or reason from isolated attributes.
- Use broad baseline attributes only as background context. Do not lead with broad facts like "adult food in cans" or convert them into recommendations.
- Use `attribute_coverage.csv` to judge whether missing matches are real evidence gaps or possible mapping limitations.
- Use `retailer_live_presence_audit.csv` to sanity-check current retailer presence against the retailer brand page. A cached category row or direct PDP artifact does not count as current brand-at-retailer presence when the product is absent from the live brand page.
- Be skeptical. A match in the data is a lead to evaluate, not proof of a commercial opportunity.
- Treat current top-seller signals as first-class signals. They indicate what {summary['retailer_label']} {summary['category_label']} appears to reward now, regardless of product age.
- Treat recent-arrival signals as first-class signals. They indicate what is overrepresented in recent products versus the rest.
- Treat signals that appear in both current top sellers and recent arrivals as especially important, but do not overclaim if product counts or brand counts are thin.
- Treat rank-weighted visibility as a metric attached to retailer signals, not as a separate signal family. It shows where highly ranked products concentrate before and after greedy overlap removal; it does not prove sales, demand, or shopper path attribution.
{web_shelf_prompt_line}
- Use `retailer_brand_anchors.csv` and `brand_at_retailer_bundle_matches.csv` to explain whether {summary['brand_name']} is already present in the relevant {summary['retailer_label']} shelf logic.
- Use `retailer_brand_anchor_signal_fit.csv` to separate three facts: current {summary['brand_name']} presence at {summary['retailer_label']}, whether that presence appears in the source top-seller sort, and whether it is explained by the selected retailer signal mix. A current or top-seller anchor with no selected signal match is not automatically weak; it may be winning for brand equity, price, promo, reviews, distribution, or an unmapped/missing attribute.
- Use `brand_at_retailer_review_validation.csv` to check whether current {summary['brand_name']} products at {summary['retailer_label']} have rating, review-count, or review-text support from the source retailer package. Treat this as validation or friction evidence for current anchors, not as a source of new retailer signals.
{review_evidence_prompt_line}
- Use `manufacturer_catalog_products.csv`, `manufacturer_catalog_bundle_matches.csv`, and `reference_candidates.csv` to explain which {summary['brand_name']} catalog products can credibly support the story.
- Use images to sanity-check whether the product visually and propositionally expresses the signal. Do not rely on images alone, and do not place images in the deliverable.
- This is not an assortment gap report. Do not frame the story as "{summary['brand_name']} has these products and {summary['retailer_label']} has those products."
- Treat manufacturer products as reference evidence for a commercial conversation, not as automatic launch, listing, or assortment recommendations.

Language rules:
- Do not print internal IDs such as `bundle_20545dc185` in the final report. If an audit reference is absolutely necessary, put it in a footnote or omit it.
- Avoid internal jargon: "anchor layer", "manufacturer layer", "overlap lane", "intersection", "mapped internally", "bundle universe", "bundle match", and "lacks specific innovation support".
- Preferred terms: "retailer signal", "current {summary['brand_name']} at {summary['retailer_label']}", "{summary['brand_name']} catalog product", "same signal", "partial match", "gap", "reason to trust", "reason to be cautious".
- Use "form" as the attribute name for product delivery type, such as stick, liquid, pressed powder, wand, tube, compact, or balm.
- Avoid saying only "no match." Explain what that means commercially: for example, "the package does not show {summary['brand_name']} already winning this exact {summary['retailer_label']} signal" or "the catalog product supports one component of the signal but not the full signal."
- If a current {summary['brand_name']} at {summary['retailer_label']} anchor has no selected signal match, write that the product is commercially present but not explained by the selected attribute-bundle logic. If `top_seller_sort_present` is true, say the top-seller-sort evidence makes it commercially important despite the missing signal match. Do not phrase that as "{summary['brand_name']} is out of sync" unless the product also lacks independent current-retailer evidence.
- Every section must answer "so what?" for the business reader.

Important rules:
- Reason by retailer signals, not isolated single attributes.
- If the source brief says a signal is shade-range, variant-level, baseline, or otherwise fragile, preserve that caveat and do not promote it to a standalone parent-product recommendation.
- For color, shade, size, scent, or other variant-level attributes, distinguish parent-line architecture from product proposition. Do not let those attributes drive the reference ranking unless the source brief explicitly supports that interpretation.
- Do not try to find something positive if the evidence is weak. It is acceptable to conclude that the package does not support a strong reference opportunity.
- Treat `reference_candidates.csv` as candidate leads, not as final recommendations. Re-rank, downgrade, or reject candidates when the supporting bundles are broad, thin, variant-level, visually unsupported, or lack anchor support.
- Do not say that {summary['retailer_label']} will definitely accept a product.
- Say that a product is a stronger or weaker reference because it expresses retailer-relevant signals.
- Separate current winning evidence from emerging innovation evidence.
- Use rank-weighted visibility as support for current winning or emerging evidence; do not give it its own report section.
- Call out when a candidate has no evidence from {summary['brand_name']} products already at {summary['retailer_label']}.
- Use caveats from the source innovation metrics: support count, brand concentration, small recent counts, and broad baseline signals.
- Review evidence is retailer-dependent. If `brand_at_retailer_review_validation.csv`, the source package, or the source brief says review-validation files are empty, write that consumer-review validation is not available; do not treat missing reviews as a package failure or as negative consumer response.
- Use caveats from `attribute_coverage.csv`: if {summary['brand_name']} product attributes are sparse, write "the package does not show support" rather than implying the product definitively lacks the feature.
- Keep the report evidence-led and commercial, not academic.
- Prefer a smaller, defensible set of references over a long list. If no product clears the evidence bar, say so plainly and explain why.
- Do not create a Word or DOCX document. Return the report as structured text or markdown.
- Do not insert screenshots, product photos, or image grids. Mention image filenames only when a visual check materially changes the interpretation.

Files:
- `summary.json`: counts, source paths, and package metadata.
- `package_integrity.json`: deterministic source-to-package and table-consistency audit. It checks whether current-retailer anchor attributes preserve mapped source evidence and whether signal-fit tables recompute from final package rows.
- `package_warnings.json`: builder-computed warning contract. Use this for package caveats instead of inferring your own.
- `brand_fit_context.md`: plain-language guide to the Brand Fit objective and terms to use.
- `source_innovation_brief.md`: the source innovation report brief. Use it to interpret and caveat the raw bundle files.
- `plain_language_signal_guide.csv`: buyer-readable signal summary. Use this for prose.
- `signal_bundles.csv`: audit table of selected current top-seller and recent-arrival signals from the source retailer package, with rank-weighted visibility metrics when available.
- `retailer_brand_anchors.csv`: {summary['brand_name']} products already found at {summary['retailer_label']}.
- `retailer_live_presence_audit.csv`: lightweight live check against the current retailer brand page. It flags products visible live but missing from the cached retailer scrape, and removes cached anchors that are absent from the brand page.
- `retailer_brand_anchor_signal_fit.csv`: per-anchor read of whether each current {summary['brand_name']} product at {summary['retailer_label']} appears in the source top-seller sort and whether it matches selected retailer signals, or is current presence not explained by the selected signal mix.
- `brand_at_retailer_review_validation.csv`: rating, review-count, and review-text evidence carried from the source retailer package for current {summary['brand_name']} products at {summary['retailer_label']}.
{review_evidence_file_lines}- `brand_at_retailer_bundle_matches.csv`: current {summary['brand_name']} at {summary['retailer_label']} products mapped to retailer signals.
- `manufacturer_catalog_products.csv`: {summary['brand_name']} owned catalog products in this category.
- `manufacturer_catalog_bundle_matches.csv`: owned catalog products mapped to retailer signals.
- `reference_candidates.csv`: ranked manufacturer products to reference in the report.
- `attribute_coverage.csv`: completeness of mapped product attributes for current-retailer and manufacturer catalog products.
{web_shelf_file_lines}- `image_index.csv`: all copied images and how to inspect them.
- `images/innovation_examples/`: examples from the source innovation package.
- `images/manufacturer_catalog/`: {summary['brand_name']} product images from the manufacturer scrape.

Output:
1. Short thesis: whether the {summary['retailer_label']} {summary['category_label']} evidence creates a strong, weak, or unclear Brand Fit case for {summary['brand_name']}.
2. Retailer signal in plain English: what the {summary['retailer_label']} shelf currently rewards and what recent arrivals add.
3. Current {summary['brand_name']} at {summary['retailer_label']}: whether existing retailer presence supports those signals or is thin.
4. {summary['brand_name']} catalog fit: which owned products, if any, are credible references, without internal IDs.
5. Visual/product reality check: what the images confirm or complicate, translated into business implications.
6. Data caveats: thin counts, brand concentration, current-retailer proof level, and mapped-attribute gaps.
7. Final read: concise ranked reference list with reasons, or a clear statement that no product is strong enough to use as a reference.
"""


def _readme_text(summary: Mapping[str, Any]) -> str:
    counts = summary["counts"]
    web_shelf_file_lines = _web_shelf_file_lines(summary)
    web_shelf_section = ""
    if web_shelf_file_lines:
        web_shelf_section = (
            "\n## Source Web-Shelf Audit Files\n\n"
            "These files are copied from the source retailer package as the audit "
            "trail behind rank-weighted visibility. They should validate the "
            "visibility metrics attached to retailer signals, not create a separate "
            "signal family.\n\n"
            f"{web_shelf_file_lines}\n"
        )
    review_evidence_file_lines = _review_evidence_file_lines(summary)
    review_evidence_section = ""
    if review_evidence_file_lines:
        review_evidence_section = (
            "\n## Source Review Evidence Files\n\n"
            "These files are copied from the source retailer package as secondary "
            "retailer-level experience evidence. They validate or complicate source "
            "retailer signals, but they are not brand-specific unless the same "
            "product is also present in brand_at_retailer_review_validation.csv.\n\n"
            f"{review_evidence_file_lines}\n"
        )
    source_artifact_count_lines = ""
    if counts.get("source_web_shelf_artifact_files", 0):
        source_artifact_count_lines += (
            "- Source web-shelf audit files: "
            f"`{counts.get('source_web_shelf_artifact_files', 0)}`\n"
            "- Source web-shelf selected rows: "
            f"`{counts.get('source_web_shelf_selected_shelves_rows', 0)}`\n"
        )
    if counts.get("source_review_evidence_artifact_files", 0):
        source_artifact_count_lines += (
            "- Source review evidence files: "
            f"`{counts.get('source_review_evidence_artifact_files', 0)}`\n"
            "- Source review-theme cohort rows: "
            f"`{counts.get('source_review_theme_cohort_comparison_rows', 0)}`\n"
        )
    return f"""# {summary["brand_name"]} Brand Fit for {summary["retailer_label"]} {summary["category_label"]}

This is a downstream Brand Fit package for Pro. It does not create the final
report. It marries an existing retailer innovation package with scraped
manufacturer/catalog data so Pro can write the report.

## Logic

1. `signal_bundles.csv` imports selected winning-now and innovation bundles from
   the source retailer package, with rank-weighted visibility metrics attached
   where the source package can calculate them. Category-specific filters demote
   broad baseline facts so they do not drive reference recommendations.
2. `plain_language_signal_guide.csv` translates those rows into buyer-readable
   retailer signals, examples, and caveats.
3. `brand_fit_context.md` explains the commercial Brand Fit objective and the
   vocabulary Pro should use.
4. `package_integrity.json` audits whether the final package tables preserve
   mapped source evidence and recompute from the final rows before report text
   is trusted.
5. `package_warnings.json` consolidates builder-computed warnings and data
   caveats so Pro does not infer package quality by itself.
6. `brand_at_retailer_bundle_matches.csv` maps the brand products already at
   the retailer to those bundles.
7. `retailer_brand_anchor_signal_fit.csv` states whether each current retailer
   anchor is explained by selected signals or is current presence outside the
   selected signal mix.
8. `retailer_live_presence_audit.csv` validates current retailer presence
   against the retailer brand page before anchors are finalized.
9. `brand_at_retailer_review_validation.csv` carries rating, review-count, and
   review-text evidence from the source retailer package for current anchors.
10. `manufacturer_catalog_bundle_matches.csv` maps the brand-owned catalog to
   those same bundles.
11. `reference_candidates.csv` ranks owned products that can be used as
   references in the final report.
12. `attribute_coverage.csv` shows where mapped brand attributes are sparse, so
   missing support is not over-read as proof that a product lacks a feature.
13. Broad baseline attributes are context only and excluded from
   matching and ranking.
{web_shelf_section}
{review_evidence_section}

## Counts

- Signal bundles: `{counts["signal_bundles"]}`
- Signal bundles with rank-weighted visibility: `{counts.get("signal_bundles_with_rank_weighted_visibility", 0)}`
{source_artifact_count_lines}- Package warning status: `{summary.get("package_warning_status", "unknown")}`
- Package warnings: `{summary.get("package_warning_count", 0)}`
- Package integrity status: `{summary.get("package_integrity", {}).get("status", "unknown")}`
- Package integrity failures: `{counts.get("package_integrity_failures", 0)}`
- Package integrity warnings: `{counts.get("package_integrity_warnings", 0)}`
- Retailer brand anchors: `{counts["retailer_brand_anchor_products"]}`
- Retailer brand anchors with selected signal matches: `{counts.get("retailer_brand_anchor_products_with_signal_matches", 0)}`
- Retailer brand anchors not explained by selected signals: `{counts.get("retailer_brand_anchor_products_without_signal_matches", 0)}`
- Top-seller-sort retailer brand anchors not explained by selected signals: `{counts.get("retailer_top_seller_anchor_products_without_signal_matches", 0)}`
- Retailer brand anchors with rating or review-count evidence: `{counts.get("retailer_brand_anchor_products_with_rating_or_review_count", 0)}`
- Retailer brand anchors with review text: `{counts.get("retailer_brand_anchor_products_with_review_text", 0)}`
- Stored review text snippets for anchors: `{counts.get("retailer_brand_anchor_review_text_snippets", 0)}`
- Anchor bundle match rows: `{counts["brand_at_retailer_bundle_matches"]}`
- Retailer live audit rows: `{counts.get("retailer_live_presence_audit_rows", 0)}`
- Live products added as anchors: `{counts.get("retailer_live_products_added_as_anchors", 0)}`
- Cached products removed as anchors: `{counts.get("retailer_live_cached_products_removed_as_anchors", 0)}`
- Manufacturer products: `{counts["manufacturer_catalog_products"]}`
- Manufacturer bundle matches: `{counts["manufacturer_catalog_bundle_matches"]}`
- Reference candidates: `{counts["reference_candidates"]}`
- Images copied: `{counts["images"]}`
"""


def _write_zip(output_dir: Path) -> Path:
    zip_path = _package_zip_path(output_dir)
    legacy_zip_path = output_dir.with_suffix(".zip")
    if legacy_zip_path != zip_path and legacy_zip_path.exists():
        legacy_zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                zf.write(
                    path,
                    arcname=str(Path(output_dir.name) / path.relative_to(output_dir)),
                )
    return zip_path


def _summary_payload(
    *,
    brand_source_retailer: str,
    brand_name: str,
    category_key: str,
    retailer: str,
    innovation_package_dir: Path,
    source_innovation_summary: Mapping[str, Any],
    source_innovation_brief_file: str | None,
    signal_bundles: pl.DataFrame,
    anchors: pl.DataFrame,
    anchor_matches: pl.DataFrame,
    anchor_signal_fit: pl.DataFrame,
    brand_review_validation: pl.DataFrame,
    owned: pl.DataFrame,
    manufacturer_matches: pl.DataFrame,
    candidates: pl.DataFrame,
    image_index: pl.DataFrame,
    retailer_live_audit: pl.DataFrame,
    retailer_live_brand_page_product_count: int,
    package_integrity: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> dict[str, Any]:
    retailer_label = str(source_innovation_summary.get("retailer_label") or retailer)
    category_label = str(
        source_innovation_summary.get("category_label") or category_key
    )
    live_added_count = 0
    live_missing_count = 0
    live_removed_count = 0
    live_unavailable_count = 0
    if retailer_live_audit.width > 0 and get_row_count(retailer_live_audit) > 0:
        live_added_count = get_row_count(
            retailer_live_audit.filter(pl.col("live_added_to_retailer_products"))
        )
        live_removed_count = get_row_count(
            retailer_live_audit.filter(pl.col("live_removed_from_retailer_products"))
        )
        live_missing_count = get_row_count(
            retailer_live_audit.filter(
                pl.col("audit_status") == "live_brand_page_missing_from_package"
            )
        )
        live_unavailable_count = get_row_count(
            retailer_live_audit.filter(
                pl.col("audit_status") == "live_check_unavailable"
            )
        )
    anchor_signal_fit_count = (
        get_row_count(anchor_signal_fit) if anchor_signal_fit.width > 0 else 0
    )
    anchors_with_signal_matches = (
        get_row_count(anchor_signal_fit.filter(pl.col("matched_signal_count") > 0))
        if anchor_signal_fit.width > 0
        and "matched_signal_count" in anchor_signal_fit.columns
        else 0
    )
    anchors_without_signal_matches = (
        get_row_count(anchor_signal_fit.filter(pl.col("matched_signal_count") == 0))
        if anchor_signal_fit.width > 0
        and "matched_signal_count" in anchor_signal_fit.columns
        else 0
    )
    top_seller_anchors_without_signal_matches = (
        get_row_count(
            anchor_signal_fit.filter(
                pl.col("top_seller_sort_present")
                & (pl.col("matched_signal_count") == 0)
            )
        )
        if anchor_signal_fit.width > 0
        and "top_seller_sort_present" in anchor_signal_fit.columns
        and "matched_signal_count" in anchor_signal_fit.columns
        else 0
    )
    review_validation_rows = (
        get_row_count(brand_review_validation)
        if brand_review_validation.width > 0
        else 0
    )
    review_validation_dicts = (
        brand_review_validation.to_dicts()
        if brand_review_validation.width > 0 and review_validation_rows > 0
        else []
    )
    anchors_with_rating_or_review_count = sum(
        1 for row in review_validation_dicts if _has_rating_or_review_count(row)
    )
    anchors_with_review_text = sum(
        1 for row in review_validation_dicts if _review_text_snippet_count(row) > 0
    )
    anchor_review_text_snippets = sum(
        _review_text_snippet_count(row) for row in review_validation_dicts
    )
    manufacturer_catalog_images = (
        get_row_count(
            image_index.filter(pl.col("image_scope") == "manufacturer_catalog")
        )
        if image_index.width > 0 and "image_scope" in _columns(image_index)
        else 0
    )
    package_integrity_summary = package_integrity.get("summary")
    package_integrity_failure_count = 0
    package_integrity_warning_count = 0
    if isinstance(package_integrity_summary, Mapping):
        package_integrity_failure_count = _safe_int(
            package_integrity_summary.get("failure_count")
        )
        package_integrity_warning_count = _safe_int(
            package_integrity_summary.get("warning_count")
        )
    source_web_shelf_artifacts = sources.get("source_web_shelf_artifacts")
    source_web_shelf_row_counts: Mapping[str, Any] = {}
    source_web_shelf_file_count = 0
    if isinstance(source_web_shelf_artifacts, Mapping):
        row_counts = source_web_shelf_artifacts.get("row_counts")
        if isinstance(row_counts, Mapping):
            source_web_shelf_row_counts = row_counts
        files = source_web_shelf_artifacts.get("files")
        if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
            source_web_shelf_file_count = sum(
                1 for file_info in files if isinstance(file_info, Mapping)
            )
    source_review_evidence_artifacts = sources.get("source_review_evidence_artifacts")
    source_review_evidence_row_counts: Mapping[str, Any] = {}
    source_review_evidence_file_count = 0
    if isinstance(source_review_evidence_artifacts, Mapping):
        row_counts = source_review_evidence_artifacts.get("row_counts")
        if isinstance(row_counts, Mapping):
            source_review_evidence_row_counts = row_counts
        files = source_review_evidence_artifacts.get("files")
        if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
            source_review_evidence_file_count = sum(
                1 for file_info in files if isinstance(file_info, Mapping)
            )
    return {
        "analysis_type": "brand_retailer_reference_handoff",
        "generated_at": datetime.now(UTC).isoformat(),
        "brand_source_retailer": brand_source_retailer,
        "brand_name": brand_name,
        "category_key": category_key,
        "category_label": category_label,
        "retailer": retailer,
        "retailer_label": retailer_label,
        "innovation_package_dir": str(innovation_package_dir),
        "source_innovation_brief_file": source_innovation_brief_file,
        "source_innovation_summary": dict(source_innovation_summary),
        "counts": {
            "signal_bundles": (
                get_row_count(signal_bundles) if signal_bundles.width > 0 else 0
            ),
            "signal_bundles_with_rank_weighted_visibility": (
                signal_bundles.filter(
                    pl.col("rank_weighted_gross_visibility_share").is_not_null()
                    | pl.col("rank_weighted_incremental_visibility_share").is_not_null()
                ).height
                if signal_bundles.width > 0
                and "rank_weighted_gross_visibility_share" in signal_bundles.columns
                else 0
            ),
            "source_web_shelf_artifact_files": source_web_shelf_file_count,
            "source_web_shelf_selected_shelves_rows": _safe_int(
                source_web_shelf_row_counts.get("source_web_shelf_selected_shelves.csv")
            ),
            "source_web_shelf_candidate_shelves_rows": _safe_int(
                source_web_shelf_row_counts.get(
                    "source_web_shelf_candidate_shelves.csv"
                )
            ),
            "source_web_shelf_robustness_summary_rows": _safe_int(
                source_web_shelf_row_counts.get(
                    "source_web_shelf_robustness_summary.csv"
                )
            ),
            "source_web_shelf_product_assignments_rows": _safe_int(
                source_web_shelf_row_counts.get(
                    "source_web_shelf_product_assignments.csv"
                )
            ),
            "source_web_shelf_third_attribute_refinements_rows": _safe_int(
                source_web_shelf_row_counts.get(
                    "source_web_shelf_third_attribute_refinements.csv"
                )
            ),
            "source_review_evidence_artifact_files": source_review_evidence_file_count,
            "source_review_theme_cohort_comparison_rows": _safe_int(
                source_review_evidence_row_counts.get(
                    "source_review_theme_cohort_comparison.csv"
                )
            ),
            "source_top_seller_review_validation_rows": _safe_int(
                source_review_evidence_row_counts.get(
                    "source_top_seller_review_validation.csv"
                )
            ),
            "source_bundle_review_validation_rows": _safe_int(
                source_review_evidence_row_counts.get(
                    "source_bundle_review_validation.csv"
                )
            ),
            "retailer_brand_anchor_products": get_row_count(anchors),
            "retailer_brand_anchor_products_matched_to_owned": (
                anchors.filter(
                    pl.col("anchor_status") == "matched_owned_product"
                ).height
                if anchors.width > 0 and "anchor_status" in anchors.columns
                else 0
            ),
            "retailer_brand_anchor_products_fuzzy_matched": (
                anchors.filter(
                    pl.col("product_identity_match_method")
                    == "tikicat_chewy_name_line_fuzzy"
                ).height
                if anchors.width > 0
                and "product_identity_match_method" in anchors.columns
                else 0
            ),
            "retailer_brand_anchor_fit_rows": anchor_signal_fit_count,
            "retailer_brand_anchor_products_with_signal_matches": (
                anchors_with_signal_matches
            ),
            "retailer_brand_anchor_products_without_signal_matches": (
                anchors_without_signal_matches
            ),
            "retailer_top_seller_anchor_products_without_signal_matches": (
                top_seller_anchors_without_signal_matches
            ),
            "retailer_brand_anchor_products_with_rating_or_review_count": (
                anchors_with_rating_or_review_count
            ),
            "retailer_brand_anchor_products_with_review_text": (
                anchors_with_review_text
            ),
            "retailer_brand_anchor_review_text_snippets": (anchor_review_text_snippets),
            "brand_at_retailer_review_validation_rows": review_validation_rows,
            "brand_at_retailer_bundle_matches": (
                get_row_count(anchor_matches) if anchor_matches.width > 0 else 0
            ),
            "manufacturer_catalog_products": get_row_count(owned),
            "manufacturer_catalog_products_with_images": _nonempty_column_count(
                owned,
                "image_file",
            ),
            "manufacturer_catalog_bundle_matches": (
                get_row_count(manufacturer_matches)
                if manufacturer_matches.width > 0
                else 0
            ),
            "reference_candidates": (
                get_row_count(candidates) if candidates.width > 0 else 0
            ),
            "reference_candidates_with_images": _nonempty_column_count(
                candidates,
                "image_file",
            ),
            "manufacturer_catalog_images": manufacturer_catalog_images,
            "images": get_row_count(image_index),
            "retailer_live_presence_audit_rows": get_row_count(retailer_live_audit),
            "retailer_live_brand_page_products": (
                retailer_live_brand_page_product_count
            ),
            "retailer_live_products_added_as_anchors": live_added_count,
            "retailer_live_cached_products_removed_as_anchors": live_removed_count,
            "retailer_live_products_missing_from_cache": live_missing_count,
            "retailer_live_check_unavailable_products": live_unavailable_count,
            "package_integrity_failures": package_integrity_failure_count,
            "package_integrity_warnings": package_integrity_warning_count,
        },
        "top_reference_candidates": (
            candidates.select(
                [
                    "product_name",
                    "reference_score",
                    "matched_bundle_count",
                    "winning_now_bundle_count",
                    "innovation_bundle_count",
                    "rank_weighted_visibility_bundle_count",
                    "anchor_bundle_overlap_count",
                    "matched_bundle_labels",
                    "reference_rationale",
                    "image_file",
                ]
            )
            .head(8)
            .to_dicts()
            if candidates.width > 0 and get_row_count(candidates) > 0
            else []
        ),
        "package_integrity": {
            "status": package_integrity.get("status", "unknown"),
            "summary": (
                dict(package_integrity_summary)
                if isinstance(package_integrity_summary, Mapping)
                else {}
            ),
        },
        "sources": dict(sources),
    }


def _build_package_impl(
    *,
    brand_source_retailer: str,
    brand_name: str,
    category_key: str,
    retailer: str,
    innovation_package_dir: Path | None = None,
    innovation_brief_path: Path | None = None,
    owned_cli_dir: Path | None = None,
    owned_cli_dirs: Sequence[Path] | None = None,
    owned_category_keys: Sequence[str] | None = None,
    retailer_category_keys: Sequence[str] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    max_bundles_per_layer: int = 24,
    max_reference_candidates: int = 16,
    retailer_live_check: bool = True,
    retailer_live_check_timeout: float = 12.0,
    retailer_live_fetcher: Callable[[str], str | None] | None = None,
    allow_missing_brand_images: bool = False,
) -> Path:
    """Build a Brand Fit package from innovation, retailer, and catalog data."""

    _clear_existing_output_dir(
        output_root,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    innovation_package_dir = innovation_package_dir or _innovation_package_dir(
        retailer,
        category_key,
    )
    if not innovation_package_dir.exists():
        raise FileNotFoundError(
            f"Innovation package directory does not exist: {innovation_package_dir}"
        )
    innovation_brief_path = innovation_brief_path or _innovation_brief_path(
        retailer,
        category_key,
    )
    if not innovation_brief_path.exists():
        raise FileNotFoundError(
            "Brand Fit package generation requires an existing retailer signal "
            f"brief for {retailer}/{category_key}: {innovation_brief_path}. "
            "Do not generate a Brand Fit package from raw signal tables alone."
        )
    default_owned_cli_dir = _default_owned_cli_dir(
        brand_source_retailer,
        category_key,
    )
    resolved_owned_cli_dirs = tuple(owned_cli_dirs or ())
    if owned_cli_dir is not None:
        resolved_owned_cli_dirs = (owned_cli_dir, *resolved_owned_cli_dirs)
    if not resolved_owned_cli_dirs:
        resolved_owned_cli_dirs = (default_owned_cli_dir,)
    owned_cli_dir = resolved_owned_cli_dirs[0]

    source_innovation_summary = _read_json_if_exists(
        innovation_package_dir / "summary.json"
    )
    source_package_integrity = _require_source_package_integrity(innovation_package_dir)
    source_snapshot_manifest = _require_source_package_snapshot_manifest(
        innovation_package_dir,
        source_innovation_summary,
    )
    signal_bundles = _load_signal_bundles(
        innovation_package_dir,
        max_bundles_per_layer=max_bundles_per_layer,
        category_key=category_key,
    )
    signal_bundles, _ = _split_signal_bundles_by_usefulness(signal_bundles)
    if signal_bundles.width == 0 or get_row_count(signal_bundles) == 0:
        raise ValueError(
            f"No usable winning-now or innovation bundles found in {innovation_package_dir}."
        )

    owned = _load_owned_products(
        category_key=category_key,
        category_keys=owned_category_keys,
        source_label=brand_source_retailer,
    )
    _require_owned_products(
        owned,
        brand_source_retailer=brand_source_retailer,
        brand_name=brand_name,
        category_key=category_key,
        category_keys=owned_category_keys,
    )
    output_dir = _prepare_output_dir(
        output_root,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    source_innovation_brief_file = _copy_innovation_brief(
        innovation_brief_path,
        output_dir=output_dir,
    )
    source_web_shelf_artifacts = _copy_source_web_shelf_artifacts(
        innovation_package_dir,
        output_dir=output_dir,
        source_innovation_summary=source_innovation_summary,
        signal_bundles=signal_bundles,
    )
    source_review_evidence_artifacts = _copy_source_review_evidence_artifacts(
        innovation_package_dir,
        output_dir=output_dir,
        source_innovation_summary=source_innovation_summary,
    )
    retailer_products = _load_retailer_brand_products(
        category_key=category_key,
        category_keys=retailer_category_keys,
        brand_name=brand_name,
        source_label=retailer,
    )
    attribute_lookup, attribute_source_files = _load_retailer_product_attribute_lookup(
        innovation_package_dir,
        brand_name=brand_name,
    )
    (
        retailer_products,
        retailer_live_audit,
        retailer_live_brand_page_product_count,
        retailer_live_brand_page_url,
    ) = _audit_live_retailer_presence(
        owned=owned,
        retailer_products=retailer_products,
        brand_name=brand_name,
        category_key=category_key,
        retailer=retailer,
        enabled=retailer_live_check,
        timeout=retailer_live_check_timeout,
        fetcher=retailer_live_fetcher,
    )
    retailer_products_before_attribute_enrichment = retailer_products
    retailer_products = _enrich_products_with_retailer_product_attributes(
        retailer_products,
        attribute_lookup,
        brand_name=brand_name,
    )
    review_lookup, review_source_files = _load_retailer_review_lookup(
        innovation_package_dir,
        brand_name=brand_name,
    )
    retailer_products = _enrich_products_with_retailer_reviews(
        retailer_products,
        review_lookup,
        brand_name=brand_name,
    )
    anchors = _build_anchors(
        owned,
        retailer_products,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    missing_owned = _build_missing_owned(owned, retailer_products, anchors=anchors)

    anchor_matches = _build_product_bundle_matches(anchors, signal_bundles)
    top_seller_lookup = _load_top_seller_product_lookup(
        innovation_package_dir,
        brand_name=brand_name,
    )
    anchor_signal_fit = _build_anchor_signal_fit(
        anchors,
        anchor_matches,
        top_seller_lookup=top_seller_lookup,
    )
    brand_review_validation = _brand_at_retailer_review_validation_df(anchors)
    manufacturer_matches = _build_product_bundle_matches(owned, signal_bundles)
    candidates = _candidate_rows(
        missing_owned,
        manufacturer_matches,
        anchor_matches,
        max_reference_candidates=max_reference_candidates,
    )
    manufacturer_image_parent_ids = _manufacturer_image_parent_ids(
        anchors=anchors,
        candidates=candidates,
    )
    owned, manufacturer_image_rows = _copy_manufacturer_images(
        owned,
        cli_dir=owned_cli_dir,
        cli_dirs=resolved_owned_cli_dirs,
        output_dir=output_dir,
        parent_ids=manufacturer_image_parent_ids,
    )
    anchors = _build_anchors(
        owned,
        retailer_products,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    missing_owned = _build_missing_owned(owned, retailer_products, anchors=anchors)
    anchor_matches = _build_product_bundle_matches(anchors, signal_bundles)
    anchor_signal_fit = _build_anchor_signal_fit(
        anchors,
        anchor_matches,
        top_seller_lookup=top_seller_lookup,
    )
    brand_review_validation = _brand_at_retailer_review_validation_df(anchors)
    manufacturer_matches = _build_product_bundle_matches(owned, signal_bundles)
    candidates = _candidate_rows(
        missing_owned,
        manufacturer_matches,
        anchor_matches,
        max_reference_candidates=max_reference_candidates,
    )
    _validate_brand_image_coverage(
        brand_source_retailer=brand_source_retailer,
        brand_name=brand_name,
        retailer=retailer,
        category_key=category_key,
        owned=owned,
        candidates=candidates,
        manufacturer_image_rows=manufacturer_image_rows,
        allow_missing_brand_images=allow_missing_brand_images,
    )
    pre_attribute_anchors = _build_anchors(
        owned,
        retailer_products_before_attribute_enrichment,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    pre_attribute_anchor_matches = _build_product_bundle_matches(
        pre_attribute_anchors,
        signal_bundles,
    )
    package_integrity = _build_package_integrity_audit(
        brand_name=brand_name,
        anchors=anchors,
        owned=owned,
        signal_bundles=signal_bundles,
        anchor_matches=anchor_matches,
        anchor_signal_fit=anchor_signal_fit,
        attribute_lookup=attribute_lookup,
        attribute_source_files=attribute_source_files,
        pre_attribute_anchor_matches=pre_attribute_anchor_matches,
    )
    if package_integrity.get("status") == "fail":
        _write_json(output_dir / "package_integrity.json", package_integrity)
    _validate_package_ready_for_pro(
        brand_name=brand_name,
        retailer=retailer,
        category_key=category_key,
        anchors=anchors,
        retailer_live_audit=retailer_live_audit,
        retailer_live_check=retailer_live_check,
        package_integrity=package_integrity,
    )
    plain_signal_guide = _plain_language_signal_guide(signal_bundles)
    attribute_coverage = _combined_attribute_coverage(anchors=anchors, owned=owned)
    innovation_image_rows = _copy_innovation_example_images(
        innovation_package_dir,
        output_dir=output_dir,
        signal_bundles=signal_bundles,
    )
    anchor_image_rows = [
        {
            "image_scope": "brand_at_retailer_anchor",
            "parent_product_id": row.get("parent_product_id"),
            "product_name": row.get("product_name"),
            "image_file": row.get("image_file"),
            "image_available": bool(row.get("image_file")),
            "image_source": "matched manufacturer catalog image",
            "inspect_rule": "Use to verify the anchor product's visual fit to matched bundles.",
        }
        for row in anchors.select(_product_output_columns(anchors)).to_dicts()
        if _meaningful_text(row.get("image_file"))
    ]
    image_index = _image_index_df(
        [*innovation_image_rows, *manufacturer_image_rows, *anchor_image_rows]
    )
    sources = {
        "innovation_package_dir": str(innovation_package_dir),
        "innovation_brief_path": (
            str(innovation_brief_path) if innovation_brief_path else None
        ),
        "owned_catalog_source": "pdp_database",
        "owned_cli_dir": str(owned_cli_dir),
        "owned_cli_dirs": [str(path) for path in resolved_owned_cli_dirs],
        "owned_category_keys": list(owned_category_keys or (category_key,)),
        "retailer_catalog_source": "pdp_database",
        "retailer_category_keys": list(retailer_category_keys or (category_key,)),
        "retailer_live_check_enabled": retailer_live_check,
        "retailer_live_brand_page_url": retailer_live_brand_page_url,
        "retailer_product_attribute_source_files": attribute_source_files,
        "retailer_review_source_files": review_source_files,
        "source_innovation_package_integrity": {
            "status": source_package_integrity.get("status"),
            "summary": source_package_integrity.get("summary", {}),
        },
        "source_innovation_source_snapshot_manifest": source_snapshot_manifest,
        "source_web_shelf_artifacts": source_web_shelf_artifacts,
        "source_review_evidence_artifacts": source_review_evidence_artifacts,
    }
    summary = _summary_payload(
        brand_source_retailer=brand_source_retailer,
        brand_name=brand_name,
        category_key=category_key,
        retailer=retailer,
        innovation_package_dir=innovation_package_dir,
        source_innovation_summary=source_innovation_summary,
        source_innovation_brief_file=source_innovation_brief_file,
        signal_bundles=signal_bundles,
        anchors=anchors,
        anchor_matches=anchor_matches,
        anchor_signal_fit=anchor_signal_fit,
        brand_review_validation=brand_review_validation,
        owned=owned,
        manufacturer_matches=manufacturer_matches,
        candidates=candidates,
        image_index=image_index,
        retailer_live_audit=retailer_live_audit,
        retailer_live_brand_page_product_count=(retailer_live_brand_page_product_count),
        package_integrity=package_integrity,
        sources=sources,
    )
    package_warnings = _brand_fit_package_warning_payload(
        summary=summary,
        package_integrity=package_integrity,
    )
    summary["package_warning_status"] = package_warnings["status"]
    summary["package_warning_count"] = package_warnings["warning_count"]
    summary["package_warnings"] = package_warnings["warnings"]

    signal_bundles.drop(
        [
            column
            for column in ["category_center_component_count"]
            if column in signal_bundles.columns
        ]
    ).write_csv(output_dir / "signal_bundles.csv")
    plain_signal_guide.write_csv(output_dir / "plain_language_signal_guide.csv")
    attribute_coverage.write_csv(output_dir / "attribute_coverage.csv")
    anchor_output_columns = [
        *_product_output_columns(anchors),
        *[
            column
            for column in ANCHOR_OUTPUT_EXTRA_COLUMNS
            if column in _columns(anchors)
        ],
        "anchor_status",
    ]
    anchors.select(list(dict.fromkeys(anchor_output_columns))).write_csv(
        output_dir / "retailer_brand_anchors.csv"
    )
    retailer_live_audit.write_csv(output_dir / "retailer_live_presence_audit.csv")
    anchor_signal_fit.write_csv(output_dir / "retailer_brand_anchor_signal_fit.csv")
    brand_review_validation.write_csv(
        output_dir / "brand_at_retailer_review_validation.csv"
    )
    owned.select(_product_output_columns(owned)).write_csv(
        output_dir / "manufacturer_catalog_products.csv"
    )
    missing_owned.select(_product_output_columns(missing_owned)).write_csv(
        output_dir / "manufacturer_products_not_at_retailer.csv"
    )
    anchor_matches.write_csv(output_dir / "brand_at_retailer_bundle_matches.csv")
    manufacturer_matches.write_csv(
        output_dir / "manufacturer_catalog_bundle_matches.csv"
    )
    candidates.write_csv(output_dir / "reference_candidates.csv")
    image_index.write_csv(output_dir / "image_index.csv")
    _write_json(output_dir / "package_integrity.json", package_integrity)
    _write_json(output_dir / "package_warnings.json", package_warnings)
    _write_json(output_dir / "summary.json", summary)
    (output_dir / "brand_fit_context.md").write_text(
        _brand_fit_context_text(summary, plain_signal_guide, attribute_coverage),
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(_readme_text(summary), encoding="utf-8")
    (output_dir / "prompt_for_pro.txt").write_text(
        _build_prompt(summary), encoding="utf-8"
    )
    _write_json(
        output_dir / "pack_manifest.json",
        {
            "package_type": "brand_retailer_reference_handoff",
            "files": sorted(
                path.relative_to(output_dir).as_posix()
                for path in output_dir.rglob("*")
                if path.is_file()
            ),
            "summary": summary,
        },
    )
    _write_zip(output_dir)
    return output_dir


def build_package(
    *,
    brand_source_retailer: str,
    brand_name: str,
    category_key: str,
    retailer: str,
    innovation_package_dir: Path | None = None,
    innovation_brief_path: Path | None = None,
    owned_cli_dir: Path | None = None,
    owned_cli_dirs: Sequence[Path] | None = None,
    owned_category_keys: Sequence[str] | None = None,
    retailer_category_keys: Sequence[str] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    max_bundles_per_layer: int = 24,
    max_reference_candidates: int = 16,
    retailer_live_check: bool = True,
    retailer_live_check_timeout: float = 12.0,
    retailer_live_fetcher: Callable[[str], str | None] | None = None,
    allow_missing_brand_images: bool = False,
) -> Path:
    """Build a Brand Fit package and remove partial output if generation fails."""

    output_dir = _package_output_dir(
        output_root,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
        category_key=category_key,
    )
    try:
        return _build_package_impl(
            brand_source_retailer=brand_source_retailer,
            brand_name=brand_name,
            category_key=category_key,
            retailer=retailer,
            innovation_package_dir=innovation_package_dir,
            innovation_brief_path=innovation_brief_path,
            owned_cli_dir=owned_cli_dir,
            owned_cli_dirs=owned_cli_dirs,
            owned_category_keys=owned_category_keys,
            retailer_category_keys=retailer_category_keys,
            output_root=output_root,
            max_bundles_per_layer=max_bundles_per_layer,
            max_reference_candidates=max_reference_candidates,
            retailer_live_check=retailer_live_check,
            retailer_live_check_timeout=retailer_live_check_timeout,
            retailer_live_fetcher=retailer_live_fetcher,
            allow_missing_brand_images=allow_missing_brand_images,
        )
    except Exception:
        zip_path = _package_zip_path(output_dir)
        legacy_zip_path = output_dir.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        if legacy_zip_path != zip_path and legacy_zip_path.exists():
            legacy_zip_path.unlink()
        if output_dir.exists():
            shutil.rmtree(output_dir)
        raise


def build_all_packages(
    *,
    brand_source_retailer: str,
    brand_name: str,
    retailer: str,
    category_keys: Sequence[str] | None = None,
    owned_cli_dirs: Sequence[Path] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    max_bundles_per_layer: int = 24,
    max_reference_candidates: int = 16,
    retailer_live_check: bool = True,
    retailer_live_check_timeout: float = 12.0,
    allow_missing_brand_images: bool = False,
    fail_fast: bool = False,
) -> pl.DataFrame:
    """Build Brand Fit packages for selected or discovered categories."""

    selected_categories = (
        list(category_keys) if category_keys else _source_package_categories(retailer)
    )
    if not selected_categories:
        raise RuntimeError(
            f"No source package categories found for retailer={retailer}."
        )

    rows: list[dict[str, str | None]] = []
    total = len(selected_categories)
    for index, category_key in enumerate(selected_categories, start=1):
        LOGGER.info(
            "Building Brand Fit package %s of %s: %s / %s / %s",
            index,
            total,
            brand_source_retailer,
            retailer,
            category_key,
        )
        try:
            output_dir = build_package(
                brand_source_retailer=brand_source_retailer,
                brand_name=brand_name,
                category_key=category_key,
                retailer=retailer,
                owned_cli_dirs=owned_cli_dirs,
                output_root=output_root,
                max_bundles_per_layer=max_bundles_per_layer,
                max_reference_candidates=max_reference_candidates,
                retailer_live_check=retailer_live_check,
                retailer_live_check_timeout=retailer_live_check_timeout,
                allow_missing_brand_images=allow_missing_brand_images,
            )
        except FileNotFoundError as exc:
            LOGGER.warning(
                "Skipped Brand Fit package: %s / %s / %s (%s)",
                brand_source_retailer,
                retailer,
                category_key,
                exc,
            )
            rows.append(
                {
                    "brand_source_retailer": brand_source_retailer,
                    "retailer": retailer,
                    "category_key": category_key,
                    "status": "skipped",
                    "output_dir": None,
                    "package_zip": None,
                    "error": str(exc),
                }
            )
            if fail_fast:
                raise
            continue
        except Exception as exc:
            LOGGER.exception(
                "Failed to build Brand Fit package: %s / %s / %s",
                brand_source_retailer,
                retailer,
                category_key,
            )
            rows.append(
                {
                    "brand_source_retailer": brand_source_retailer,
                    "retailer": retailer,
                    "category_key": category_key,
                    "status": "failed",
                    "output_dir": None,
                    "package_zip": None,
                    "error": str(exc),
                }
            )
            if fail_fast:
                raise
            continue
        rows.append(
            {
                "brand_source_retailer": brand_source_retailer,
                "retailer": retailer,
                "category_key": category_key,
                "status": "built",
                "output_dir": str(output_dir),
                "package_zip": str(_package_zip_path(output_dir)),
                "error": None,
            }
        )

    summary = pl.DataFrame(rows)
    summary_path = _bulk_summary_path(
        output_root,
        brand_source_retailer=brand_source_retailer,
        retailer=retailer,
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.write_csv(summary_path)
    LOGGER.info(
        "Brand Fit package rebuild complete: built=%s failed=%s skipped=%s summary=%s",
        summary.filter(pl.col("status") == "built").height,
        summary.filter(pl.col("status") == "failed").height,
        summary.filter(pl.col("status") == "skipped").height,
        summary_path,
    )
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    load_env_from_secrets_file()
    args = _parse_args()
    category_keys = _selected_category_keys(args)
    if category_keys is None or len(category_keys) > 1:
        if (
            args.innovation_package_dir is not None
            or args.innovation_brief_path is not None
        ):
            raise ValueError(
                "--innovation-package-dir and --innovation-brief-path are only valid "
                "when building one --category."
            )
        if args.owned_category_key or args.retailer_category_key:
            raise ValueError(
                "--owned-category-key and --retailer-category-key are only valid "
                "when building one --category."
            )
        summary = build_all_packages(
            brand_source_retailer=args.brand_source_retailer,
            brand_name=args.brand_name,
            retailer=args.retailer,
            category_keys=category_keys,
            owned_cli_dirs=tuple(args.owned_cli_dir) if args.owned_cli_dir else None,
            output_root=args.output_root,
            max_bundles_per_layer=args.max_bundles_per_layer,
            max_reference_candidates=args.max_reference_candidates,
            retailer_live_check=not args.skip_retailer_live_check,
            retailer_live_check_timeout=args.retailer_live_check_timeout,
            allow_missing_brand_images=args.allow_missing_brand_images,
        )
        failed_count = summary.filter(pl.col("status") == "failed").height
        return 1 if failed_count else 0

    category_key = category_keys[0]
    output_dir = build_package(
        brand_source_retailer=args.brand_source_retailer,
        brand_name=args.brand_name,
        category_key=category_key,
        retailer=args.retailer,
        innovation_package_dir=args.innovation_package_dir,
        innovation_brief_path=args.innovation_brief_path,
        owned_cli_dirs=tuple(args.owned_cli_dir) if args.owned_cli_dir else None,
        owned_category_keys=(
            tuple(args.owned_category_key) if args.owned_category_key else None
        ),
        retailer_category_keys=(
            tuple(args.retailer_category_key) if args.retailer_category_key else None
        ),
        output_root=args.output_root,
        max_bundles_per_layer=args.max_bundles_per_layer,
        max_reference_candidates=args.max_reference_candidates,
        retailer_live_check=not args.skip_retailer_live_check,
        retailer_live_check_timeout=args.retailer_live_check_timeout,
        allow_missing_brand_images=args.allow_missing_brand_images,
    )
    LOGGER.info("Wrote Brand Fit package to %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
