from __future__ import annotations

import hashlib
import itertools
import json
import logging
import math
import re
import shutil
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl
from polars.exceptions import NoDataError

from modules.utilities.utils import get_row_count, get_schema_and_column_names
from src.slides.launch_calculation_helpers import calculate_package_frames

__all__ = [
    "DEFAULT_LAUNCH_BRIEF_ROOTS",
    "DEFAULT_LAUNCH_PACKAGE_ROOTS",
    "LaunchValidationOpenAIError",
    "LaunchPackageData",
    "LaunchPackageRef",
    "build_pdf_reading_payload_for_validation",
    "build_launch_package_content_fingerprint",
    "discover_launch_packages",
    "load_launch_package_data",
    "review_launch_report_validation_with_llm",
    "resolve_launch_package_for_pdf",
    "validate_launch_report_batch",
    "validate_launch_report_pdf",
    "write_launch_report_batch_artifacts",
    "write_launch_report_validation_artifacts",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_LAUNCH_PACKAGE_ROOTS = (Path("data/pdp/reports/packages/launch"),)
DEFAULT_LAUNCH_BRIEF_ROOTS = (Path("data/pdp/reports/briefs/launch"),)
_READING_CACHE_DIRNAME = ".launch_report_reading_cache"
_READING_CACHE_META_FILENAME = "reading_cache_meta.json"
_READING_CACHE_PIPELINE_VERSION = 2
_REPORT_SOURCE_SIDECAR_SUFFIXES = (
    ".launch_report_source.json",
    ".source.json",
    ".report_payload.json",
)
_PACKAGE_REQUIRED_FILES = (
    "summary.json",
    "pack_manifest.json",
    "top_seller_pairs.csv",
    "top_seller_triples.csv",
    "innovation_pairs.csv",
    "innovation_triples.csv",
    "filter_comparison.csv",
    "mapped_attribute_comparison.csv",
    "resolved_core_comparison.csv",
    "top_seller_mapped_attribute_comparison.csv",
    "top_seller_brand_comparison.csv",
    "bundle_review_validation.csv",
    "top_seller_review_validation.csv",
    "sale_pressure_pairs.csv",
    "sale_pressure_triples.csv",
    "sale_pressure_overlap.csv",
    "recent_product_pdp_extracts.csv",
    "product_filter_matrix.csv",
    "recent_products.csv",
    "top_seller_products.csv",
    "web_shelf_selected_shelves.csv",
    "web_shelf_robustness_summary.csv",
    "web_shelf_candidate_shelves.csv",
    "web_shelf_third_attribute_refinements.csv",
)


class LaunchValidationOpenAIError(RuntimeError):
    """Raised when OpenAI-backed launch validation review fails."""


_REPORT_PACKAGE_ALIASES = {
    "cashmere": "cashmere_sweaters",
    "cream": "bb_cc_creams",
    "setting_spray_and_powder": "setting_spray_powder",
    "sneaker": "low_top_sneakers",
}
_REPORT_RETAILER_SUFFIXES = {
    "_ulta": "ulta",
    "_saks": "saksfifthavenue",
    "_chewy": "chewy",
    "_saloncentric": "saloncentric",
    "_cosmoprof": "cosmoprofbeauty",
}
_SUMMARY_REPORT_CHILD_BRIEFS = {
    "lips": (
        ("ulta", "lip_balm"),
        ("ulta", "lip_gloss"),
        ("ulta", "lip_liner"),
        ("ulta", "lip_oil"),
        ("ulta", "lip_plumper"),
        ("ulta", "lip_stain"),
        ("ulta", "lip_treatment"),
        ("ulta", "lipstick"),
    ),
    "face": (
        ("ulta", "face"),
        ("ulta", "blush"),
        ("ulta", "bronzer"),
        ("ulta", "color_correct"),
        ("ulta", "concealer"),
        ("ulta", "contour"),
        ("ulta", "creams"),
        ("ulta", "face_primer"),
        ("ulta", "foundation"),
        ("ulta", "highlighter"),
        ("ulta", "setting spray"),
        ("ulta", "tinted_moisturer"),
    ),
    "permanent": (
        ("cosmoprofbeauty", "permanent"),
        ("saloncentric", "permanent"),
    ),
}
_BUNDLE_CONNECTOR_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
_BUNDLE_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_COUNT_RATIO_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_MULTIPLIER_RE = re.compile(r"(\d+(?:\.\d+)?)x")
_DELTA_PERCENT_POINT_RE = re.compile(
    r"\b(?:difference|delta|gap|lift)\s*(?:of|:)?\s*"
    r"(?P<value>[+-]?\d+(?:\.\d+)?)\s*"
    r"(?:pp|percentage\s+points?)\b",
    re.IGNORECASE,
)
_SIGNED_RANK_DELTA_RE = re.compile(
    r"\b(?:mean\s+signed\s+delta|signed\s+delta|rank\s+delta)\s*"
    r"(?:of|:)?\s*\(?\s*(?P<value>[+-]?\d+(?:\.\d+)?)\s*\)?",
    re.IGNORECASE,
)
_PRICE_MONEY_RE = re.compile(
    r"(?P<symbol>[$€£])\s*(?P<amount>\d+(?:,\d{3})*(?:\.\d+)?)"
)
_BRAND_COUNT_RE = re.compile(
    r"(?:across\s+|brand\s+(?:breadth|count|span|spread)\s*:?\s*)"
    r"(\d+)\s+(?:distinct\s+)?brands?",
    re.IGNORECASE,
)
_BUNDLE_BRAND_SPAN_RE = re.compile(
    r"(?:spans|distributed\s+across|spread\s+across)\s+(\d+)\s+"
    r"(?:distinct\s+)?(?:top[-\s]?selling\s+)?brands?",
    re.IGNORECASE,
)
_BUNDLE_BRAND_DISTRIBUTION_RE = re.compile(
    r"\bbrand\s+distribution\s*:?\s*(\d+)\s+(?:distinct\s+)?brands?\b",
    re.IGNORECASE,
)
_BUNDLE_MATCHED_TOP_SELLER_COUNT_RE = re.compile(
    r"\bmatched\s+products?\s*:?\s*(\d+)\s+top[-\s]?sellers?\b",
    re.IGNORECASE,
)
_BUNDLE_DOMINANT_BRAND_SHARE_RE = re.compile(
    r"\baccounts\s+for\s+(\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
_BUNDLE_DOMINANT_BRAND_COUNT_RE = re.compile(
    r"\baccounts\s+for\s+(\d+)\s+of\s+(\d+)\s+products?\b",
    re.IGNORECASE,
)
_BUNDLE_NO_BRAND_ABOVE_RE = re.compile(
    r"\bno\s+brand\s+above\s+(\d+)\s+products?\b",
    re.IGNORECASE,
)
_BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT = 50.0
_BUNDLE_BRAND_CONCENTRATION_MIN_BRAND_SPAN = 2
_PRODUCT_RANK_RE = re.compile(
    r"(?P<name>[^()\n]+?)\s*\(#(?P<rank>\d+)\s+Pareto\s+(?P<bucket>[ABC])\)",
    re.IGNORECASE,
)
_PRODUCT_BUCKET_RE = re.compile(r"\bPareto\s+([ABC])\b", re.IGNORECASE)
_PRODUCT_RANK_NUMBER_RE = re.compile(
    r"(?:rank(?:ed)?(?:\s+at)?\s*#?|position\s*#?|#)(\d+)\b",
    re.IGNORECASE,
)
_TRAILING_PRODUCT_RANK_ANNOTATION_RE = re.compile(
    r"\s*\(#?\d+\s*(?:(?:Pareto\s+)?[ABC]|(?:overall\s+)?rank|"
    r"top[-\s]?sellers?|sellers?)\)\s*$",
    re.IGNORECASE,
)
_PRODUCT_RANK_ITEM_RE = re.compile(
    r"(?P<name>[^,\n]+?)\s*\(#(?P<rank>\d+)\s*"
    r"(?:(?:Pareto\s+)?(?P<bucket>[ABC])|(?:overall\s+)?rank|"
    r"top[-\s]?sellers?|sellers?)\)",
    re.IGNORECASE,
)
_BUNDLE_RANKED_PRODUCTS_RE = re.compile(
    r"(?P<label>[^:\n]+):.+?\btop[-\s]?ranked\s+products?\s*"
    r"\((?P<rank_text>[^)]*#\d+[^)]*)\)",
    re.IGNORECASE,
)
_NUMBER_ONE_TOP_SELLING_PRODUCT_RE = re.compile(
    r"\b(?:the\s+)?(?:number\s+one|#1|no\.?\s*1|rank(?:ed)?\s*#?1)\s+"
    r"top[-\s]?selling\s+product(?:\s+overall)?\s+is\s+(?P<name>[^.;\n]+)",
    re.IGNORECASE,
)
_COHORT_COUNT_MENTION_RE = re.compile(
    r"\b(?P<count>\d+)\s+"
    r"(?P<label>"
    r"top[-\s]?selling(?:\s+products?)?|"
    r"top[-\s]?sellers?(?:\s+products?)?|"
    r"recent(?:\s+(?:launches?|products?))?"
    r")\b",
    re.IGNORECASE,
)
_COHORT_OVERLAP_TOP_WINDOW_RE = re.compile(
    r"\bonly\s+(?P<overlap>\d+)\s+of\s+(?:the\s+)?top\s+"
    r"(?P<top_count>\d+)\s+(?:products?|items?)\s+overlap\b",
    re.IGNORECASE,
)
_BRAND_RANKING_OVERLAP_RE = re.compile(
    r"(?:^|[(;,:])\s*(?P<brand>[A-Z][A-Za-z0-9&' .-]{1,40}?)\s+"
    r"ranking\s+(?P<ranks>#\d+(?:\s*(?:,|and)\s*#\d+)*)",
    re.IGNORECASE,
)
_HASH_RANK_RE = re.compile(r"#(\d+)")
_COHORT_PRODUCT_ID_COLUMNS = (
    "canonical_id_export",
    "canonical_id",
    "parent_product_id",
    "listing_identity",
    "pdp_url",
    "product_name_norm",
    "product_name",
)
_ATTRIBUTE_SHARE_TEXT_NOISE_TOKENS = {
    "attribute",
    "attributes",
    "claim",
    "claims",
    "explicit",
    "language",
    "overall",
    "prevalence",
    "share",
}
_ATTRIBUTE_SHARE_LABEL_NOISE_TOKENS = _ATTRIBUTE_SHARE_TEXT_NOISE_TOKENS | {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
    "versus",
    "vs",
    "with",
    "without",
}
_BUNDLE_SINGLE_ATTRIBUTE_EXCLUDED_NAMES = {
    "productname",
    "productnamenorm",
    "producttitle",
}
_COMPUTED_BUNDLE_MAX_SELECTOR_COMBINATIONS = 300
_COMPUTED_BUNDLE_MAX_DISTINCT_COLUMN_VALUES = 250
_COMPUTED_BUNDLE_EXCLUDED_COLUMN_TOKENS = {
    "brand",
    "brand_norm",
    "canonical_accept",
    "canonical_id",
    "canonical_id_export",
    "canonical_owner",
    "category_id",
    "category_key",
    "category_label",
    "category_path",
    "description",
    "description_excerpt",
    "hero_image_url",
    "image",
    "listing_identity",
    "listing_status",
    "max_price",
    "parent_product_id",
    "pdp_url",
    "price",
    "product_name",
    "product_name_norm",
    "raw_category_path",
    "retailer",
    "review",
    "summary",
    "top_seller_status",
    "url",
}
_REVIEW_POSITIVE_TEXT_COLUMNS = (
    "reviews_positive_headline",
    "reviews_positive_comment",
    "review_1_headline",
    "review_1_comment",
    "review_2_headline",
    "review_2_comment",
    "review_3_headline",
    "review_3_comment",
    "review_4_headline",
    "review_4_comment",
    "review_5_headline",
    "review_5_comment",
)
_REVIEW_NEGATIVE_TEXT_COLUMNS = (
    "reviews_negative_headline",
    "reviews_negative_comment",
    "review_1_headline",
    "review_1_comment",
    "review_2_headline",
    "review_2_comment",
    "review_3_headline",
    "review_3_comment",
    "review_4_headline",
    "review_4_comment",
    "review_5_headline",
    "review_5_comment",
)
_PRODUCT_REVIEW_NEGATIVE_TEXT_COLUMNS = (
    "reviews_negative_headline",
    "reviews_negative_comment",
)
_REVIEW_VALIDATION_TOPIC_KEYWORDS = {
    "texture": ("texture", "smooth", "velvety", "creamy"),
    "comfort": ("comfort", "comfortable", "soft", "hydrat", "moistur"),
    "glide": ("glide", "glides", "gliding", "applies easily", "easy application"),
    "coverage": ("coverage", "cover", "pigment", "pigmented", "color payoff"),
}
_PDP_DESCRIPTOR_TEXT_COLUMNS = (
    "product_name",
    "title_raw",
    "food texture",
    "food_texture",
    "packaging type",
    "packaging_type",
    "flavor",
    "description",
    "description_excerpt",
    "summary",
)
_PDP_DESCRIPTOR_TOPIC_KEYWORD_GROUPS = {
    "savory_gravy": (("savory", "savoury"), ("gravy",)),
    "meat_aroma": (("meat",), ("aroma", "aromas", "aromatic")),
    "hydration": (("hydrat", "moisture", "broth", "gravy"),),
}
_REVIEW_FRICTION_TOPIC_KEYWORDS = {
    "shade_accuracy": ("shade", "color", "colour"),
    "formula_consistency": (
        "formula",
        "consistency",
        "patchy",
        "dry",
        "drying",
        "crumbly",
        "break",
        "transfer",
    ),
    "removal_difficulty": (
        "remove",
        "removal",
        "hard to remove",
        "difficult to remove",
    ),
    "heavier_feel": ("heavy", "heavier", "thick", "sticky"),
    "price_point": ("price", "price point", "worth the money", "expensive", "pricey"),
    "packaging_opening": ("open", "opening", "seal", "packag", "dented", "cans"),
}
_PRODUCT_REVIEW_POSITIVE_TOPIC_KEYWORDS = {
    "texture_blend": (
        "blend",
        "blendable",
        "blending",
        "creamy",
        "glide",
        "glides",
        "smooth",
        "streak free",
        "streak-free",
        "texture",
        "velvety",
    ),
    "color_payoff": ("color payoff", "pigment", "pigmented", "payoff"),
    "glow_finish": ("airbrush", "blur", "glow", "luminous", "radiant", "shimmer"),
    "multi_use": (
        "face + lips",
        "face and lips",
        "lip color",
        "multi use",
        "multi-use",
        "on the go",
        "on-the-go",
        "travel",
    ),
    "natural_finish": ("natural", "natural-looking", "natural looking"),
}
_PRODUCT_REVIEW_NEGATIVE_TOPIC_KEYWORDS = {
    "shade_expectation": (
        "brown",
        "colour",
        "dark",
        "fair complexion",
        "orange",
        "red",
        "shade",
    ),
    "packaging": ("casing", "compact", "lid", "packag", "pan"),
    "limited_color_payoff": ("payoff", "pigment", "sheer", "show much"),
    "application_fit": ("application", "apply", "brush", "patchy"),
    "price_value": ("expensive", "money", "price", "pricey", "worth"),
    "product_identity": ("bronzer", "contour", "confus"),
    "wear_finish": ("finish", "last", "longevity", "oily", "wear"),
}
_BRAND_NUMERIC_WINDOW_CHARS = 45
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_BRAND_NOISE_TOKENS = {"professional", "professionnel"}
_BRAND_ALIAS_NOISE_TOKENS = _BRAND_NOISE_TOKENS | {
    "beauty",
    "by",
    "co",
    "company",
    "cosmetics",
    "inc",
    "llc",
    "makeup",
    "the",
}
_BRAND_ALIAS_TOKEN_BLOCKLIST = {
    "and",
    "for",
    "in",
    "it",
    "of",
    "on",
    "the",
    "too",
    "with",
}
_PRODUCT_NOISE_TOKENS = _BRAND_NOISE_TOKENS | {
    "advanced",
    "ammonia",
    "color",
    "coloring",
    "colour",
    "cream",
    "creme",
    "free",
    "hair",
    "haircolor",
    "liqui",
    "new",
    "no",
    "oz",
    "performance",
    "permanent",
}
_PRODUCT_MATCH_NOISE_TOKENS = _PRODUCT_NOISE_TOKENS | {"a", "aa", "ma", "m"}
_PRODUCT_TOKEN_ALIASES = {
    "cximal": "maximal",
}
_PERCENT_TOLERANCE = 0.11
_MULTIPLIER_TOLERANCE = 0.02
_VISIBILITY_PERCENT_TOLERANCE = 0.35
_BUNDLE_COHORT_HINTS = (
    "recent",
    "rest",
    "top seller",
    "top sellers",
    "top-seller",
    "others",
    "other",
    "winner",
    "winners",
    "winning",
    "evidence ratio",
)
_CONTAINING_BUNDLE_FALLBACK_HINTS = (
    "adding",
    "combination",
    "combinations",
    "combined with",
    "paired with",
    "sub-expression",
    "sub expression",
    "variant",
)
_BRAND_SHARE_HINTS = (
    "top-seller cohort",
    "top seller cohort",
    "catalog share",
    "over-index",
    "over index",
    "share of the top-seller cohort",
    "share of the top seller cohort",
    "share of catalog",
)
_BRAND_OVERINDEX_RE = re.compile(
    r"\bover[-\s]?index(?:es|ed|ing)?\b",
    re.IGNORECASE,
)
_BRAND_OVERINDEX_INTENSITY_RE = re.compile(
    r"\b(?:heavily|materially|strongly|significantly)\s+over[-\s]?index",
    re.IGNORECASE,
)
_CATEGORY_BRAND_CONCENTRATION_SURVIVAL_RE = re.compile(
    r"\b(?:survive|survives|not\s+merely|not\s+just)\b.*\bbrand\b.*\b(?:concentration|artifact)\b|"
    r"\bbrand\b.*\b(?:concentration|artifact)\b.*\b(?:survive|survives|not\s+merely|not\s+just)\b",
    re.IGNORECASE,
)
_CATEGORY_NO_SINGLE_OWNER_RE = re.compile(
    r"\bno\s+single\s+(?:brand|house|player|retailer)\s+(?:owns|dominates|controls)\b|"
    r"\bnot\s+(?:owned|dominated|controlled)\s+by\s+(?:a\s+)?single\s+(?:brand|house|player|retailer)\b",
    re.IGNORECASE,
)
_ATTRIBUTE_DIRECTION_RE = re.compile(
    r"(?P<label>[A-Za-z0-9][A-Za-z0-9/&'\"\-\s]{0,80}?)\s+"
    r"(?P<direction>over[-\s]?index(?:es|ed|ing)?|under[-\s]?index(?:es|ed|ing)?)\b",
    re.IGNORECASE,
)
_ATTRIBUTE_FLAT_DELTA_MAX = 0.05
_ATTRIBUTE_FLAT_RE = re.compile(
    r"(?:^|[,;:]\s*|\band\s+)[\"“”']?"
    r"(?P<label>[A-Za-z][A-Za-z0-9/&'\"\-\s]{0,40}?)[\"“”']?\s+"
    r"(?:(?:presence|claims?|share)\s+)?"
    r"(?:(?:is|are|remain|remains)\s+)?"
    r"(?:essentially\s+|basically\s+|mostly\s+)?flat\b",
    re.IGNORECASE,
)
_ATTRIBUTE_NOT_CENTRAL_BUNDLE_RE = re.compile(
    r"(?:^|[,;:]\s*|\band\s+)[\"“”']?"
    r"(?P<label>[A-Za-z][A-Za-z0-9/&'\"\-\s]{0,40}?)[\"“”']?\s+"
    r"(?:claims?|positioning|presence)\s+"
    r"(?:do|does)\s+not\s+form\s+(?:a\s+)?(?:central|main|core)\s+"
    r"(?:winning\s+)?bundle\b",
    re.IGNORECASE,
)
_ATTRIBUTE_DIRECTION_FRAGMENT_NOISE_TOKENS = {
    "appeal",
    "attribute",
    "attributes",
    "claim",
    "claims",
    "delivery",
    "direction",
    "expression",
    "expressions",
    "finish",
    "finishes",
    "form",
    "format",
    "formats",
    "hybrid",
    "product",
    "products",
    "recent",
    "structure",
    "structures",
}
_NON_CLAIM_SECTION_PREFIXES = (
    "analytical recap",
    "category constants",
    "factual synthesis",
    "friction diagnostic",
    "product embodiment",
)
_NON_CLAIM_STRUCTURAL_LABELS = {
    "briefing matrix",
    "intelligence dossier",
}
_NON_CLAIM_TABLE_HEADER_LABELS = {
    "attribute",
    "attribute bundle",
    "others",
    "recent",
    "recent %",
    "rest",
    "rest %",
    "shade bundle",
    "top sellers",
}
_NON_CLAIM_META_PURPOSE_START_RE = re.compile(
    r"^(?:identifies|maps|summarizes|summarises|frames|outlines|describes)\b",
    re.IGNORECASE,
)
_NON_CLAIM_SETUP_LABEL_RE = re.compile(
    r"\btarget\s*:.*\bmethodology\s*:.*\bstatus\s*:",
    re.IGNORECASE,
)
_NON_CLAIM_PREDICATE_RE = re.compile(
    r"\b(?:is|are|remain|remains|represent|represents|confirm|confirms|"
    r"signal|signals|move|moves|reveal|reveals|survive|survives|collapse|"
    r"collapses|under-index|under-indexes|over-index|over-indexes|win|wins|"
    r"validate|validates)\b",
    re.IGNORECASE,
)
_LAYER_MARKER_RE = re.compile(r"^layer\s+\d+\b", re.IGNORECASE)
_TABLE_HEADER_PERCENT_RE = re.compile(
    r"^(?:recent|rest|top sellers?|others?)\s*\(%\)$",
    re.IGNORECASE,
)
_STANDALONE_VISIBILITY_METRIC_RE = re.compile(
    r"^(?:gross|incremental|total)\s+visibility\s*:?\s*\d+(?:\.\d+)?%$",
    re.IGNORECASE,
)
_OCR_FUSED_WORD_MARKERS = (
    "existsbroadly",
    "tleatherbaseline",
    "tonalaccent",
)
_OCR_STRAY_TOKEN_RE = re.compile(
    r"\b(?:signal\s+al\s+exists|but\s+r\s+remains|in\s+1\s+total\s+volume)\b",
    re.IGNORECASE,
)
_OCR_LONG_DIGIT_TOKEN_RE = re.compile(r"\b\d{8,}\b")
_EXHIBIT_LABEL_TEXT_RE = re.compile(r"^exhibit\s+[a-z]\s*:", re.IGNORECASE)
_PRODUCT_LABEL_TEXT_RE = re.compile(
    r"^product\s*:.*\bmapped\s+attributes\s*:",
    re.IGNORECASE,
)
_SHORT_FRAGMENT_NON_CLAIM_WORD_LIMIT = 5
_CLAIM_TEXT_HINTS = (
    "anchored by",
    "baseline",
    "difference",
    "divergence",
    "emerging",
    "led by",
    "outperform",
    "over-index",
    "recent",
    "rest",
    "share",
    "stable",
    "top seller",
    "top sellers",
    "validation",
    "winner",
    "winners",
    "winning",
)
_RESIDUAL_CLAIM_DOMAIN_RE = re.compile(
    r"\b(?:anchors?|architecture|arrivals|attributes?|baseline|brands?|"
    r"brand[-\s]?concentration|bundles?|category|cohorts?|compact|"
    r"construction|formats?|friction|health\s+needs|innovation|models?|"
    r"pate|pdp|pockets?|products?|propositions?|reviews?|sale\s+pressure|"
    r"shelf|shifts?|signals?|skus?|textures?|top[-\s]?sellers?|"
    r"visibility)\b",
    re.IGNORECASE,
)
_RESIDUAL_CLAIM_PREDICATE_RE = re.compile(
    r"\b(?:adds?|anchors?|anchored|are|carried|carries|confirms?|consolidates?|"
    r"constitutes?|defined|defines|demonstrates?|dominates?|driven|"
    r"duplicates?|emphasizes?|emphasises?|establish(?:es)?|explained|explains?|"
    r"functions?|indicates?|is|lacks?|matches?|match|operates|provides?|qualifies?|"
    r"registers?|reinforces?|relies|remain|remains|represents?|shows?|"
    r"survives?|validates?|utilizes?|utilises?)\b|"
    r"\bsignal\s+read\b|\bvisibility\s+metric\b",
    re.IGNORECASE,
)
_QUALIFIED_COHORT_SCOPE_RE = re.compile(
    r"\b(?:of|among|within|in)\s+"
    r"(?P<cohort>top[-\s]sellers?|others?|other products?|recent|rest|remaining products?)"
    r"\s+(?P<qualifier>[a-z][a-z0-9/&'\-\s]{1,60}?)\s+"
    r"(?P<object>products?|items?|bundles?|structures?|lip products?)\b",
    re.IGNORECASE,
)
_COHORT_SCOPE_STOPWORDS = {
    "all",
    "and",
    "category",
    "core",
    "data",
    "products",
    "product",
    "the",
}
_BUNDLE_PART_NOISE_TOKENS = {
    "benefit",
    "benefits",
    "claim",
    "claims",
    "color",
    "coverage",
    "finish",
    "form",
    "flavor",
    "flavour",
    "format",
    "lips",
    "resolved",
    "scent",
    "wear",
}
_READING_BLOCK_CONFIDENCE_WARNING = 0.55
_READING_VISUAL_CONFIDENCE_WARNING = 0.60
_READING_TABLE_CONFIDENCE_WARNING = 0.60
_READING_SPARSE_TEXT_LIMIT = 40
_READING_POOR_SLIDE_RATIO_DIVISOR = 5
_READING_COMPLETENESS_MIN_CANONICAL_CHARS = 12
_READING_COMPLETENESS_MIN_TOKENS = 3
_READING_COMPLETENESS_WARNING_MISSING_RATIO = 0.20
_READING_COMPLETENESS_POOR_MISSING_RATIO = 0.60
_READING_COMPLETENESS_POOR_MISSING_COUNT = 3
_SUMMARY_TEXT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "reports",
    "report",
    "that",
    "the",
    "this",
    "to",
    "vs",
    "with",
}
_SUMMARY_SYNTHESIS_SUPPORT_NOISE_TOKENS = _SUMMARY_TEXT_STOPWORDS | {
    "baseline",
    "brand",
    "brands",
    "category",
    "but",
    "claim",
    "claims",
    "core",
    "current",
    "dominant",
    "emerging",
    "gross",
    "incremental",
    "market",
    "primary",
    "product",
    "products",
    "rank",
    "read",
    "recent",
    "secondary",
    "seller",
    "sellers",
    "signal",
    "signals",
    "strongest",
    "structural",
    "top",
    "visibility",
    "weight",
    "winner",
    "winners",
    "winning",
}
_SUMMARY_SYNTHESIS_TOKEN_ALIASES = {
    "branding": ("logo", "detail"),
    "branded": ("logo", "detail"),
    "buildability": ("buildable",),
    "cans": ("can",),
    "cardigans": ("cardigan",),
    "crewnecks": ("crewneck",),
    "duplicates": ("duplicate",),
    "formats": ("format",),
    "glow": ("luminous",),
    "hems": ("hem",),
    "hydration": ("hydrating",),
    "modifiers": ("modifier",),
    "powders": ("powder",),
    "pullovers": ("pullover",),
    "ribbed": ("rib",),
    "soled": ("sole",),
    "sticks": ("stick",),
    "trays": ("tray",),
}
_SUMMARY_SYNTHESIS_COMPONENT_MATCH_NOISE_TOKENS = {
    "architecture",
    "architectures",
    "bundle",
    "bundles",
    "concentration",
    "confirming",
    "fatal",
    "genuinely",
    "material",
    "materially",
    "multi",
    "robust",
    "strictly",
    "survive",
    "survives",
}
_SUMMARY_SYNTHESIS_SUPPORT_FAMILIES = {
    "attribute_direction",
    "attribute_share",
    "brand_share",
    "bundle_brand_concentration",
    "bundle_metric",
    "category_brand_concentration",
    "cohort_overlap",
    "entry_price_comparison",
    "product_rank",
    "rank_weighted_visibility",
    "ranked_bundle_product_evidence",
    "review_friction",
    "review_validation",
    "sale_pressure_exposure",
}
_SUMMARY_NUMERIC_FACT_RE = re.compile(
    r"(?P<ratio>\b\d[\d,]*\s*/\s*\d[\d,]*\b)"
    r"|(?P<currency>[$€£]\s*\d[\d,]*(?:\.\d+)?)"
    r"|(?P<percent>\b\d[\d,]*(?:\.\d+)?\s*%)"
    r"|(?P<multiplier>\b\d[\d,]*(?:\.\d+)?\s*x\b)"
    r"|(?P<rank>#\s*\d[\d,]*)"
    r"|(?P<count>\b\d[\d,]*(?:\.\d+)?\+?\s+(?:brands?|products?|items?|reports?|categories?|slides?)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LaunchPackageRef:
    """Location and identity of one launch package on disk."""

    package_dir: Path
    retailer: str
    category_key: str
    category_label: str


@dataclass(slots=True)
class LaunchPackageData:
    """Loaded launch package data and derived label indexes."""

    ref: LaunchPackageRef
    manifest: dict[str, Any]
    summary: dict[str, Any]
    content_fingerprint: dict[str, Any]
    frames: dict[str, pl.DataFrame]
    calculation_summary: tuple[dict[str, Any], ...]
    bundle_labels: tuple[str, ...]
    brand_names: tuple[str, ...]
    product_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BundleLabelRecord:
    label: str
    tokens: frozenset[str]
    required_token_counts: tuple[tuple[str, int], ...]
    part_count: int


@dataclass(frozen=True, slots=True)
class _PercentMention:
    value: float
    tolerance: float
    role: str | None
    lower_bound: float | None = None
    upper_bound: float | None = None
    span: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class _MoneyMention:
    value: float
    tolerance: float
    role: str | None
    span: tuple[int, int]


def _read_optional_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    try:
        return pl.read_csv(path, infer_schema_length=10000)
    except NoDataError:
        return pl.DataFrame()


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _fold_text(value: Any) -> str:
    raw_text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", _normalize_text(value))
    text = raw_text.casefold()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _canonical_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold_text(value))


def _canonical_tokens(
    value: Any,
    *,
    ignored_tokens: set[str] | None = None,
) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", _fold_text(value)) if token}
    if ignored_tokens:
        return {token for token in tokens if token not in ignored_tokens}
    return tokens


def _token_list(value: Any) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", _fold_text(value)) if token]


def _product_match_tokens(value: Any) -> set[str]:
    tokens = _canonical_tokens(value, ignored_tokens=_PRODUCT_MATCH_NOISE_TOKENS)
    return {_PRODUCT_TOKEN_ALIASES.get(token, token) for token in tokens if token}


def _bundle_part_tokens(value: Any) -> tuple[str, ...]:
    tokens = tuple(
        token for token in _token_list(value) if token not in _BUNDLE_PART_NOISE_TOKENS
    )
    if tokens:
        return tokens
    return tuple(_token_list(value))


def _bundle_label_tokens(value: Any) -> set[str]:
    return {
        token
        for part in _bundle_parts_in_order(value)
        for token in _bundle_part_tokens(part)
    } or set(_token_list(value))


def _normalize_bundle_part(part: str) -> str:
    candidate = part.strip().strip("\"'“”‘’")
    if "=" in candidate:
        _key, rhs = candidate.split("=", 1)
        candidate = rhs.strip().strip("\"'“”‘’")
    return candidate.strip().strip("\"'“”‘’")


def _bundle_parts_in_order(value: Any) -> tuple[str, ...]:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", _normalize_text(value)).casefold()
    if not text:
        return ()

    plus_parts = [
        _normalize_bundle_part(part)
        for part in text.split("+")
        if _normalize_bundle_part(part)
    ]
    if len(plus_parts) >= 2:
        return tuple(plus_parts)

    connector_parts = [
        _normalize_bundle_part(part)
        for part in _BUNDLE_CONNECTOR_RE.split(text)
        if _normalize_bundle_part(part)
    ]
    if 2 <= len(connector_parts) <= 3:
        return tuple(connector_parts)
    return ()


def _bundle_parts(value: Any) -> tuple[str, ...]:
    return tuple(sorted(_bundle_parts_in_order(value)))


def _bundle_label_matches(expected: Any, actual: Any) -> bool:
    if _canonical_text(expected) == _canonical_text(actual):
        return True
    expected_parts = _bundle_parts(expected)
    actual_parts = _bundle_parts(actual)
    return bool(expected_parts and actual_parts and expected_parts == actual_parts)


def _bundle_label_key(label: str) -> str:
    parts = _bundle_parts(label)
    if parts:
        return "bundle:" + "|".join(parts)
    return "text:" + _canonical_text(label)


def _best_bundle_span(segment: str, label: str) -> tuple[int, int] | None:
    lowered_segment = segment.casefold()
    direct_label = _normalize_text(label).casefold()
    if direct_label:
        start = lowered_segment.find(direct_label)
        if start != -1:
            return start, start + len(direct_label)

    parts = tuple(part.casefold() for part in _bundle_parts(label))
    if not parts:
        return None

    part_spans: list[list[tuple[int, int]]] = []
    for part in parts:
        spans = [
            (match.start(), match.end())
            for match in re.finditer(re.escape(part), lowered_segment)
        ]
        if not spans:
            part_tokens = _bundle_part_tokens(part)
            raw_part_tokens = _token_list(part)
            if len(raw_part_tokens) > 1:
                flexible_part_pattern = r"\s*".join(
                    re.escape(token) for token in raw_part_tokens
                )
                spans.extend(
                    (match.start(), match.end())
                    for match in re.finditer(
                        rf"(?<![a-z0-9]){flexible_part_pattern}(?![a-z0-9])",
                        lowered_segment,
                    )
                )
            for token in part_tokens:
                spans.extend(
                    (match.start(), match.end())
                    for match in re.finditer(
                        rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])",
                        lowered_segment,
                    )
                )
        if not spans:
            return None
        part_spans.append(spans)

    best_span: tuple[int, int] | None = None
    best_width: int | None = None
    for candidate in itertools.product(*part_spans):
        start = min(span[0] for span in candidate)
        end = max(span[1] for span in candidate)
        width = end - start
        if best_width is None or width < best_width:
            best_span = (start, end)
            best_width = width
    return best_span


def _has_fused_bundle_part_match(segment: str, label: str) -> bool:
    lowered_segment = _fold_text(segment)
    for part in _bundle_parts(label):
        raw_tokens = _token_list(part)
        if len(raw_tokens) < 2:
            continue
        fused_part = "".join(raw_tokens)
        if re.search(
            rf"(?<![a-z0-9]){re.escape(fused_part)}(?![a-z0-9])",
            lowered_segment,
        ):
            return True
    return False


def _localize_bundle_segment(segment: str, label: str) -> str:
    span = _best_bundle_span(segment, label)
    if span is None:
        return segment
    start, end = span
    clause_start = 0
    clause_end = len(segment)
    for match in re.finditer(r"[.;,]\s+", segment):
        if match.group(0).startswith(".") and segment[
            : match.start()
        ].rstrip().casefold().endswith("vs"):
            continue
        if match.end() <= start:
            clause_start = match.end()
            continue
        if match.start() >= end:
            following = segment[match.end() : match.end() + 40].casefold()
            following_clause = re.split(
                r"(?<=[.!?])\s+",
                segment[match.end() :],
                maxsplit=1,
            )[0]
            if match.group(0).startswith(",") and re.match(
                r"(?:across|spanning|distributed|spread)\b",
                following,
            ):
                continue
            if match.group(0).startswith(",") and _contains_numeric_evidence(
                following_clause
            ):
                continue
            if match.group(0).startswith(";") and re.match(
                r"(?:others?|rest|recent|top[-\s]?sellers?|remaining|"
                r"brand\s+(?:breadth|count|span|spread)|read\b|"
                r"evidence\s+ratio|market\s+signal)\b",
                following,
            ):
                continue
            if match.group(0).startswith(";") and _contains_numeric_evidence(
                following_clause
            ):
                continue
            clause_end = match.start()
            break
    localized = segment[clause_start:clause_end].strip()
    return re.sub(r"^(?:and|but)\s+", "", localized, flags=re.IGNORECASE).strip()


def _clean_explicit_bundle_label(value: str) -> str:
    label = _normalize_text(value).strip("•-–—:;,. ")
    if "•" in label:
        label = label.rsplit("•", 1)[-1].strip("•-–—:;,. ")
    label = label.strip("\"'“”‘’")
    label = re.sub(
        r"^(?:dominant\s+attributes?|attribute\s+bundle|bundle|lane|signal)\s*:?\s+",
        "",
        label,
        flags=re.IGNORECASE,
    )
    label = re.split(
        r"\b(?:market\s+signal|visibility\s+metric|matched\s+products|"
        r"brand\s+distribution|prevalence|recent\s+vs|rest\s+prevalence|"
        r"top[-\s]?sellers?)\b",
        label,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    label = label.strip("•-–—:;,. ").strip("\"'“”‘’")
    if "+" not in label or len(label) > 120:
        return ""
    if re.search(r"\b(?:vs|versus)\b", label, flags=re.IGNORECASE):
        return ""
    return label if len(_bundle_parts(label)) >= 2 else ""


def _explicit_bundle_labels_from_segment(segment: str) -> list[str]:
    labels: list[str] = []
    normalized = _normalize_text(segment).lstrip("•-–— ")

    for match in re.finditer(
        r"[\"'“”‘’]([^\"'“”‘’]{1,120}\+[^\"'“”‘’]{1,120})[\"'“”‘’]", normalized
    ):
        label = _clean_explicit_bundle_label(match.group(1))
        if label:
            labels.append(label)

    prefix_match = re.match(r"(?P<label>[^:;]{1,120}\+[^:;]{1,120})\s*:", normalized)
    if prefix_match is not None:
        label = _clean_explicit_bundle_label(prefix_match.group("label"))
        if label:
            labels.append(label)

    for match in re.finditer(
        r"\b(?:dominant\s+attributes?|attribute\s+bundle|bundle|lane|signal)\s*:?\s+"
        r"(?P<label>[^;:.]{1,120}\+[^;:.]{1,120})(?=;|,|\.|$)",
        normalized,
        flags=re.IGNORECASE,
    ):
        label = _clean_explicit_bundle_label(match.group("label"))
        if label:
            labels.append(label)

    for match in re.finditer(
        r"(?P<label>[^;:.]{1,120}\+[^;:.]{1,120})\s+"
        r"(?:spans|distributed\s+across|spread\s+across)\s+\d+\s+"
        r"(?:distinct\s+)?(?:top[-\s]?selling\s+)?brands?",
        normalized,
        flags=re.IGNORECASE,
    ):
        label = _clean_explicit_bundle_label(match.group("label"))
        if label:
            labels.append(label)

    return _unique_texts(labels)


def _explicit_bundle_label_matches_resolved_label(
    explicit_label: str,
    resolved_label: str,
) -> bool:
    if _bundle_label_matches(explicit_label, resolved_label):
        return True
    explicit_tokens = _bundle_label_tokens(explicit_label)
    resolved_tokens = _bundle_label_tokens(resolved_label)
    return bool(explicit_tokens and explicit_tokens == resolved_tokens)


def _resolved_explicit_bundle_labels_from_segment(
    segment: str,
    bundle_records: list[_BundleLabelRecord],
    frames: dict[str, pl.DataFrame],
) -> list[str]:
    labels: list[str] = []
    for explicit_label in _explicit_bundle_labels_from_segment(segment):
        resolved_labels = _matched_bundle_labels(explicit_label, bundle_records)
        resolved_multipart_labels = [
            label
            for label in resolved_labels
            if len(_bundle_parts(label)) >= 2
            and _explicit_bundle_label_matches_resolved_label(explicit_label, label)
        ]
        if resolved_multipart_labels:
            labels.extend(
                _prefer_explicit_longest_bundle_labels(
                    explicit_label,
                    resolved_multipart_labels,
                )
            )
            continue
        if _bundle_candidates(explicit_label, frames) or _computed_bundle_candidates(
            explicit_label,
            frames,
        ):
            labels.append(explicit_label)
            continue
        labels.append(explicit_label)
    return _unique_texts(labels)


def _looks_like_multi_claim_bundle_sentence(segment: str) -> bool:
    if len(_BUNDLE_PERCENT_RE.findall(segment)) >= 4:
        return True
    lowered = segment.casefold()
    return " vs " in lowered and " and " in lowered and "+" in segment


def _prefer_explicit_longest_bundle_labels(
    text: str,
    labels: list[str],
) -> list[str]:
    if "each" in text.casefold():
        return labels
    explicit_multipart = [
        label
        for label in labels
        if len(_bundle_parts(label)) >= 2 and _best_bundle_span(text, label) is not None
    ]
    if not explicit_multipart:
        return labels
    maximal: list[str] = []
    explicit_part_sets = {
        label: set(_bundle_parts(label)) for label in explicit_multipart
    }
    for label, parts in explicit_part_sets.items():
        if any(
            label != other_label and parts < other_parts
            for other_label, other_parts in explicit_part_sets.items()
        ):
            continue
        maximal.append(label)
    return _unique_texts(maximal) if maximal else labels


def _split_atomic_bundle_labels(label: str) -> list[str]:
    text = _normalize_text(label)
    if not text:
        return []
    parts = [
        _normalize_text(part)
        for part in re.split(r"\s*\+\s*", text)
        if _normalize_text(part)
    ]
    if len(parts) < 2:
        return []
    return parts


def _slash_alternative_bundle_labels(label: str) -> list[str]:
    atomic_parts = _split_atomic_bundle_labels(label)
    if len(atomic_parts) < 2 or not any("/" in part for part in atomic_parts):
        return []

    option_groups: list[list[str]] = []
    for part in atomic_parts:
        options = [
            _normalize_text(option)
            for option in re.split(r"\s*/\s*", part)
            if _normalize_text(option)
        ]
        if not options:
            return []
        option_groups.append(options)

    labels: list[str] = []
    for combination in itertools.product(*option_groups):
        labels.append(" + ".join(combination))
    return _unique_texts(labels)


def _resolve_bundle_label_targets(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    if _bundle_candidates(label, frames):
        return {"kind": "direct", "labels": [label]}
    alternative_labels = [
        alternative
        for alternative in _slash_alternative_bundle_labels(label)
        if _bundle_candidates(alternative, frames)
        or _computed_bundle_candidates(alternative, frames)
    ]
    if alternative_labels:
        passing_alternatives = [
            alternative
            for alternative in alternative_labels
            if (
                result := _best_bundle_candidate(
                    segment,
                    alternative,
                    frames,
                    context_segment=segment,
                )
            )
            is not None
            and result.get("status") == "pass"
        ]
        return {
            "kind": "alternatives",
            "labels": passing_alternatives or alternative_labels,
        }
    atomic_parts = _split_atomic_bundle_labels(label)
    if "each" in segment.casefold() and len(atomic_parts) >= 2:
        valid_parts = [
            part for part in atomic_parts if _bundle_candidates(part, frames)
        ]
        if len(valid_parts) == len(atomic_parts):
            return {"kind": "split", "labels": _unique_texts(valid_parts)}
    return {"kind": "direct", "labels": [label]}


def _approx_equal(left: float | None, right: float | None, tolerance: float) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance


def _percent_tolerance(raw_value: str) -> float:
    decimals = len(raw_value.split(".", 1)[1]) if "." in raw_value else 0
    rounding_tolerance = 0.5 * (10**-decimals)
    return max(_PERCENT_TOLERANCE, rounding_tolerance + 1e-9)


def _percent_role(segment: str, span: tuple[int, int]) -> str | None:
    immediate_after = segment[span[1] : span[1] + 32].casefold()
    immediate_before = segment[max(0, span[0] - 32) : span[0]].casefold()
    immediate_role_patterns = (
        ("top_seller", r"\btop[-\s]?sellers?\b|\bwinners?\b|\bwinning\b"),
        ("other", r"\bothers?\b|\bremaining\b"),
        ("recent", r"\brecent\b"),
        ("rest", r"\brest\b"),
    )
    for role, pattern in immediate_role_patterns:
        if re.match(rf"\s*[\(\[]?\s*(?:{pattern})\b", immediate_after):
            return role
    for role, pattern in immediate_role_patterns:
        if re.search(rf"(?:{pattern})\s*(?:\(%\)|%|:)?\s*$", immediate_before):
            return role

    window_start = max(0, span[0] - 45)
    window_end = min(len(segment), span[1] + 45)
    window = segment[window_start:window_end].casefold()
    percent_center = ((span[0] + span[1]) / 2) - window_start
    role_patterns = {
        "top_seller": (r"\btop[-\s]?sellers?\b", r"\bwinners?\b", r"\bwinning\b"),
        "other": (r"\bothers?\b", r"\bremaining\b"),
        "recent": (r"\brecent\b",),
        "rest": (r"\brest\b",),
    }
    candidates: list[tuple[float, str]] = []
    for role, patterns in role_patterns.items():
        for pattern in patterns:
            for match in re.finditer(pattern, window):
                keyword_center = (match.start() + match.end()) / 2
                candidates.append((abs(keyword_center - percent_center), role))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _percent_mentions(segment: str) -> list[_PercentMention]:
    mentions: list[_PercentMention] = []
    for match in _BUNDLE_PERCENT_RE.finditer(segment):
        raw_value = match.group(1)
        leading_context = segment[max(0, match.start() - 12) : match.start()]
        tolerance = _percent_tolerance(raw_value)
        lower_bound: float | None = None
        upper_bound: float | None = None
        range_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-–]\s*$",
            leading_context,
        )
        if range_match is not None:
            lower_bound = float(range_match.group(1))
            upper_bound = float(raw_value)
            if lower_bound > upper_bound:
                lower_bound, upper_bound = upper_bound, lower_bound
            tolerance = max(tolerance, 0.5 + 1e-9)
        if re.search(r"(?:~|≈|about|approx\.?|around)\s*$", leading_context):
            tolerance = max(tolerance, 0.5 + 1e-9)
        mentions.append(
            _PercentMention(
                value=float(raw_value),
                tolerance=tolerance,
                role=_percent_role(segment, match.span()),
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                span=match.span(),
            )
        )
    return mentions


def _percent_matches(mention: _PercentMention, expected: float | None) -> bool:
    if expected is None:
        return False
    if mention.lower_bound is not None and mention.upper_bound is not None:
        return (
            mention.lower_bound - mention.tolerance
            <= expected
            <= mention.upper_bound + mention.tolerance
        )
    return _approx_equal(mention.value, expected, mention.tolerance)


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def _percent_from_fraction(value: Any) -> float | None:
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        key = _canonical_text(text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _truncate_text(value: Any, *, limit: int = 220) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _load_package_frames(package_dir: Path) -> dict[str, pl.DataFrame]:
    return {
        name: _read_optional_csv(package_dir / name)
        for name in _PACKAGE_REQUIRED_FILES
        if name.endswith(".csv")
    }


def _hash_file_content(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _package_content_fingerprint(package_dir: Path) -> dict[str, Any]:
    """Return a stable content fingerprint for package data files."""

    package_digest = hashlib.sha256()
    file_records: list[dict[str, Any]] = []
    if not package_dir.exists():
        return {
            "algorithm": "sha256",
            "scope": "top-level csv/json package files",
            "content_sha256": package_digest.hexdigest(),
            "file_count": 0,
            "files": [],
        }

    for path in sorted(package_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix.casefold() not in {".csv", ".json"}:
            continue
        file_hash, size_bytes = _hash_file_content(path)
        file_name = path.name
        file_records.append(
            {
                "file": file_name,
                "sha256": file_hash,
                "size_bytes": size_bytes,
            }
        )
        package_digest.update(file_name.encode("utf-8"))
        package_digest.update(b"\0")
        package_digest.update(str(size_bytes).encode("ascii"))
        package_digest.update(b"\0")
        package_digest.update(file_hash.encode("ascii"))
        package_digest.update(b"\n")

    return {
        "algorithm": "sha256",
        "scope": "top-level csv/json package files",
        "content_sha256": package_digest.hexdigest(),
        "file_count": len(file_records),
        "files": file_records,
    }


def build_launch_package_content_fingerprint(package_dir: Path) -> dict[str, Any]:
    """Return the content fingerprint used to bind reports to packages."""

    return _package_content_fingerprint(Path(package_dir))


def _launch_report_source_sidecar_candidates(pdf_path: Path) -> tuple[Path, ...]:
    candidates = [
        pdf_path.with_suffix(suffix) for suffix in _REPORT_SOURCE_SIDECAR_SUFFIXES
    ]
    canonical_pdf_stem = _canonical_text(pdf_path.stem)
    for path in sorted(pdf_path.parent.glob("*.launch_report_source.json")):
        sidecar_stem = path.name[: -len(".launch_report_source.json")]
        if _canonical_text(sidecar_stem) != canonical_pdf_stem:
            continue
        if path not in candidates:
            candidates.append(path)
    return tuple(candidates)


def _source_package_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("source_package", "sourcePackage"):
        source_package = payload.get(key)
        if isinstance(source_package, dict):
            return source_package
    if isinstance(payload.get("content_fingerprint"), dict):
        return payload
    return {}


def _source_package_content_hash(source_package: dict[str, Any]) -> str:
    fingerprint = source_package.get("content_fingerprint")
    if not isinstance(fingerprint, dict):
        fingerprint = source_package.get("contentFingerprint")
    if isinstance(fingerprint, dict):
        return _normalize_text(fingerprint.get("content_sha256"))
    return _normalize_text(source_package.get("content_sha256"))


def _launch_report_generation_source(
    pdf_path: Path,
    *,
    current_package: LaunchPackageData,
) -> dict[str, Any]:
    sidecar_candidates = _launch_report_source_sidecar_candidates(pdf_path)
    current_hash = _normalize_text(
        current_package.content_fingerprint.get("content_sha256")
    )
    for sidecar_path in sidecar_candidates:
        if not sidecar_path.exists():
            continue
        payload = _read_optional_json(sidecar_path)
        source_package = _source_package_from_payload(payload)
        if not source_package:
            return {
                "status": "invalid",
                "sidecar_path": str(sidecar_path.resolve()),
                "message": "source sidecar did not contain source_package metadata",
            }
        generation_hash = _source_package_content_hash(source_package)
        fingerprint_match = (
            generation_hash == current_hash
            if generation_hash and current_hash
            else None
        )
        if fingerprint_match is True:
            status = "matched_current_package"
        elif fingerprint_match is False:
            status = "package_mismatch"
        else:
            status = "found_without_comparable_fingerprint"
        return {
            "status": status,
            "sidecar_path": str(sidecar_path.resolve()),
            "source_package": source_package,
            "generation_package_content_sha256": generation_hash or None,
            "current_package_content_sha256": current_hash or None,
            "package_fingerprint_matches_current": fingerprint_match,
        }
    return {
        "status": "not_found",
        "expected_sidecars": [path.name for path in sidecar_candidates],
    }


def _bundle_single_attribute_row_is_excluded(row: dict[str, Any]) -> bool:
    attribute_name = _canonical_text(
        row.get("attribute_name") or row.get("filter_family")
    )
    return attribute_name in _BUNDLE_SINGLE_ATTRIBUTE_EXCLUDED_NAMES


def _bundle_candidates(
    label: str, frames: dict[str, pl.DataFrame]
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name in (
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
    ):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            if _bundle_label_matches(label, row.get("bundle_label")):
                candidates.append({"file": file_name, "row": row, "kind": "bundle"})

    df = frames["top_seller_mapped_attribute_comparison.csv"]
    if not df.is_empty() and "attribute_value" in df.columns:
        for row in df.to_dicts():
            if _bundle_single_attribute_row_is_excluded(row):
                continue
            if _bundle_label_matches(label, row.get("attribute_value")):
                candidates.append(
                    {
                        "file": "top_seller_mapped_attribute_comparison.csv",
                        "row": row,
                        "kind": "mapped",
                    }
                )

    for file_name, value_column in (
        ("mapped_attribute_comparison.csv", "attribute_value"),
        ("resolved_core_comparison.csv", "attribute_value"),
        ("filter_comparison.csv", "filter_value"),
    ):
        df = frames[file_name]
        if df.is_empty() or value_column not in df.columns:
            continue
        for row in df.to_dicts():
            if _bundle_single_attribute_row_is_excluded(row):
                continue
            if _bundle_label_matches(label, row.get(value_column)):
                candidates.append(
                    {
                        "file": file_name,
                        "row": row,
                        "kind": "single_attribute",
                    }
                )

    return candidates


def _computed_bundle_column_allowed(column_name: str, series: pl.Series) -> bool:
    canonical_column = _canonical_text(column_name)
    if not canonical_column:
        return False
    if any(
        token in canonical_column for token in _COMPUTED_BUNDLE_EXCLUDED_COLUMN_TOKENS
    ):
        return False
    if series.dtype == pl.Boolean:
        return True
    if series.dtype not in (pl.String, pl.Utf8):
        return False
    return series.drop_nulls().n_unique() <= _COMPUTED_BUNDLE_MAX_DISTINCT_COLUMN_VALUES


def _computed_bundle_selector_candidates(
    part: str,
    product_df: pl.DataFrame,
) -> list[dict[str, Any]]:
    part_key = _canonical_text(part)
    if not part_key:
        return []

    selectors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for column_name in product_df.columns:
        series = product_df.get_column(column_name)
        if not _computed_bundle_column_allowed(column_name, series):
            continue

        if series.dtype == pl.Boolean:
            suffix = column_name.rsplit("__", 1)[-1].replace("_", " ")
            if _canonical_text(suffix) == part_key:
                key = (column_name, "true")
                if key not in seen:
                    seen.add(key)
                    selectors.append(
                        {
                            "column": column_name,
                            "value": True,
                            "display_value": part,
                            "selector_kind": "boolean_indicator",
                        }
                    )
            continue

        for value in series.drop_nulls().unique().to_list():
            if _canonical_text(value) != part_key:
                continue
            key = (column_name, _normalize_text(value).casefold())
            if key in seen:
                break
            seen.add(key)
            selectors.append(
                {
                    "column": column_name,
                    "value": value,
                    "display_value": _normalize_text(value),
                    "selector_kind": "value_match",
                }
            )
            break
    return selectors


def _computed_bundle_selector_mask(
    product_df: pl.DataFrame,
    selector: dict[str, Any],
) -> pl.Series:
    column_name = _normalize_text(selector.get("column"))
    series = product_df.get_column(column_name)
    if series.dtype == pl.Boolean:
        return series.fill_null(False)
    expected_key = _canonical_text(selector.get("value"))
    return series.cast(pl.String).map_elements(
        lambda value: _canonical_text(value) == expected_key,
        return_dtype=pl.Boolean,
    )


def _computed_bundle_role_row(
    *,
    label: str,
    product_df: pl.DataFrame,
    mask: pl.Series,
    selectors: tuple[dict[str, Any], ...],
    file_name: str,
    left_role: str,
    right_role: str,
    status_column: str,
) -> dict[str, Any] | None:
    if status_column not in product_df.columns:
        return None

    status = product_df.get_column(status_column).cast(pl.String)
    left_mask = status == left_role
    right_mask = status == right_role
    left_base = int(left_mask.sum())
    right_base = int(right_mask.sum())
    if left_base <= 0 or right_base <= 0:
        return None

    left_match = mask & left_mask
    right_match = mask & right_mask
    all_match = left_match | right_match
    left_count = int(left_match.sum())
    right_count = int(right_match.sum())
    left_pct = left_count / left_base
    right_pct = right_count / right_base
    ratio = left_pct / right_pct if right_pct > 0 else None

    row: dict[str, Any] = {
        "bundle_label": label,
        "bundle_size": len(selectors),
        "computed_selectors": [
            {
                "column": selector["column"],
                "value": selector["display_value"],
                "selector_kind": selector["selector_kind"],
            }
            for selector in selectors
        ],
        "calculation_helper_id": "computed_bundle_from_product_filter_matrix",
        "calculation_source": "product_filter_matrix.csv",
        "all_match_count": int(all_match.sum()),
        "all_brand_count": (
            int(
                product_df.filter(all_match).get_column("brand").drop_nulls().n_unique()
            )
            if "brand" in product_df.columns
            else None
        ),
    }
    if left_role == "top_seller":
        row.update(
            {
                "count_top_seller": left_count,
                "count_other": right_count,
                "top_seller_base": left_base,
                "other_base": right_base,
                "pct_top_seller": left_pct,
                "pct_other": right_pct,
                "top_seller_brand_count": (
                    int(
                        product_df.filter(left_match)
                        .get_column("brand")
                        .drop_nulls()
                        .n_unique()
                    )
                    if "brand" in product_df.columns
                    else None
                ),
                "other_brand_count": (
                    int(
                        product_df.filter(right_match)
                        .get_column("brand")
                        .drop_nulls()
                        .n_unique()
                    )
                    if "brand" in product_df.columns
                    else None
                ),
            }
        )
    else:
        row.update(
            {
                "count_recent": left_count,
                "count_rest": right_count,
                "recent_base": left_base,
                "rest_base": right_base,
                "pct_recent": left_pct,
                "pct_rest": right_pct,
                "recent_brand_count": (
                    int(
                        product_df.filter(left_match)
                        .get_column("brand")
                        .drop_nulls()
                        .n_unique()
                    )
                    if "brand" in product_df.columns
                    else None
                ),
                "rest_brand_count": (
                    int(
                        product_df.filter(right_match)
                        .get_column("brand")
                        .drop_nulls()
                        .n_unique()
                    )
                    if "brand" in product_df.columns
                    else None
                ),
            }
        )
    if ratio is not None:
        row["prevalence_ratio"] = ratio
    return {"file": file_name, "row": row, "kind": "computed_bundle"}


def _computed_bundle_candidates(
    label: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    product_df = frames.get("product_filter_matrix.csv", pl.DataFrame())
    if product_df.is_empty():
        return []

    parts = _bundle_parts(label)
    if not (2 <= len(parts) <= 3):
        return []
    if any("/" in part for part in parts):
        return []

    selector_groups = [
        _computed_bundle_selector_candidates(part, product_df) for part in parts
    ]
    if any(not group for group in selector_groups):
        return []

    combination_count = 1
    for group in selector_groups:
        combination_count *= len(group)
    if combination_count > _COMPUTED_BUNDLE_MAX_SELECTOR_COMBINATIONS:
        return []

    candidates: list[dict[str, Any]] = []
    row_count = get_row_count(product_df)
    for selectors in itertools.product(*selector_groups):
        mask = pl.Series([True] * row_count)
        for selector in selectors:
            mask = mask & _computed_bundle_selector_mask(product_df, selector)

        top_seller_candidate = _computed_bundle_role_row(
            label=label,
            product_df=product_df,
            mask=mask,
            selectors=selectors,
            file_name="top_seller_computed_bundle_from_product_filter_matrix.csv",
            left_role="top_seller",
            right_role="other",
            status_column="top_seller_status",
        )
        if top_seller_candidate is not None:
            candidates.append(top_seller_candidate)

        innovation_candidate = _computed_bundle_role_row(
            label=label,
            product_df=product_df,
            mask=mask,
            selectors=selectors,
            file_name="innovation_computed_bundle_from_product_filter_matrix.csv",
            left_role="recent",
            right_role="rest",
            status_column="listing_status",
        )
        if innovation_candidate is not None:
            candidates.append(innovation_candidate)
    return candidates


def _containing_bundle_candidates(
    label: str, frames: dict[str, pl.DataFrame]
) -> list[dict[str, Any]]:
    label_tokens = _bundle_label_tokens(label)
    if not label_tokens:
        return []
    label_part_count = max(1, len(_bundle_parts(label)))
    candidates: list[dict[str, Any]] = []
    for file_name in (
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "innovation_pairs.csv",
        "innovation_triples.csv",
    ):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            candidate_label = _normalize_text(row.get("bundle_label"))
            candidate_part_count = max(1, len(_bundle_parts(candidate_label)))
            if candidate_part_count <= label_part_count:
                continue
            if label_tokens.issubset(_bundle_label_tokens(candidate_label)):
                candidates.append(
                    {
                        "file": file_name,
                        "row": row,
                        "kind": "bundle",
                        "match_scope": "containing_bundle",
                    }
                )
    return candidates


def _allows_containing_bundle_fallback(segment: str) -> bool:
    lowered = segment.casefold()
    return any(hint in lowered for hint in _CONTAINING_BUNDLE_FALLBACK_HINTS)


def _context_priority(segment: str, file_name: str) -> int:
    lowered = segment.casefold()
    if "observation" in lowered and file_name == "filter_comparison.csv":
        return 4
    if "resolved" in lowered and file_name == "resolved_core_comparison.csv":
        return 4
    if "mapped" in lowered and file_name in {
        "mapped_attribute_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
    }:
        return 4
    if "top seller" in lowered or "winning" in lowered or "winner" in lowered:
        if file_name.startswith("top_seller_"):
            return 3
    if "recent" in lowered or "emerging" in lowered or "innovation" in lowered:
        if file_name.startswith("innovation_"):
            return 3
        if file_name in {
            "filter_comparison.csv",
            "mapped_attribute_comparison.csv",
            "resolved_core_comparison.csv",
        }:
            return 3
    if file_name.startswith("top_seller_"):
        return 2
    if file_name.startswith("innovation_"):
        return 1
    if file_name in {
        "filter_comparison.csv",
        "mapped_attribute_comparison.csv",
        "resolved_core_comparison.csv",
    }:
        return 1
    return 0


def _role_labeled_percent_mentions(
    segment: str,
    candidate: dict[str, Any],
) -> list[tuple[_PercentMention, str, float]] | None:
    mentions = _percent_mentions(segment)
    strict_roles = [_strict_percent_role(segment, mention.span) for mention in mentions]
    if not mentions or not all(strict_roles):
        return None
    if len(mentions) > 1 and len(set(strict_roles)) != len(strict_roles):
        return None
    supported_roles = _candidate_supported_cohort_roles(candidate)
    labeled: list[tuple[_PercentMention, str, float]] = []
    for mention, strict_role in zip(mentions, strict_roles):
        role = _coerce_percent_role_for_supported_source(
            strict_role,
            supported_roles,
        )
        if role is None:
            return None
        expected = _candidate_percent_for_role(candidate, role)
        if expected is None:
            return None
        labeled.append((mention, role, expected))
    return labeled


def _strict_percent_role(segment: str, span: tuple[int, int]) -> str | None:
    immediate_after = segment[span[1] : span[1] + 48].casefold()
    immediate_before = segment[max(0, span[0] - 48) : span[0]].casefold()
    role_patterns = (
        ("top_seller", r"top[-\s]?sellers?|winners?|winning"),
        ("other", r"others?|remaining"),
        ("recent", r"recent"),
        ("rest", r"rest"),
    )
    for role, pattern in role_patterns:
        if re.match(
            rf"\s*(?:[\(\[]\s*)?(?:of|in|among|within)?\s*(?:all\s+)?(?:{pattern})\b",
            immediate_after,
        ):
            return role
    for role, pattern in role_patterns:
        if re.search(
            rf"\b(?:{pattern})\b(?:\s+(?:penetration|prevalence|share|percent|percentage|rate))?\s*(?:\(%\)|%|:)?\s*$",
            immediate_before,
        ):
            return role
    return None


def _brand_count_expectations(
    segment: str,
    span: tuple[int, int],
    candidate: dict[str, Any],
) -> tuple[str | None, list[tuple[str, int]]]:
    supported_roles = _candidate_supported_cohort_roles(candidate)
    explicit_role = _coerce_percent_role_for_supported_source(
        _strict_percent_role(segment, span),
        supported_roles,
    )
    if explicit_role:
        expected = _candidate_brand_span_for_role(candidate, explicit_role)
        return explicit_role, (
            [(explicit_role, expected)] if expected is not None else []
        )

    expectations: list[tuple[str, int]] = []
    all_brand_count = _candidate_brand_span_for_role(candidate, "all")
    if all_brand_count is not None:
        expectations.append(("all", all_brand_count))
    for role in ("top_seller", "recent", "other", "rest"):
        if role not in supported_roles:
            continue
        expected = _candidate_brand_span_for_role(candidate, role)
        if expected is not None:
            expectations.append((role, expected))
    return None, expectations


def _format_brand_count_expectation(
    expectations: list[tuple[str, int]],
) -> str:
    if not expectations:
        return "unavailable"
    if len(expectations) == 1:
        return str(expectations[0][1])
    return "one of " + " / ".join(f"{role}={value}" for role, value in expectations)


def _delta_pct_point_mentions(segment: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for match in _DELTA_PERCENT_POINT_RE.finditer(segment):
        raw_value = match.group("value")
        mentions.append(
            {
                "value": float(raw_value),
                "tolerance": _percent_tolerance(raw_value),
                "signed": raw_value.startswith(("+", "-")),
            }
        )
    return mentions


def _bundle_candidate_signed_delta_pct_points(
    candidate: dict[str, Any],
) -> float | None:
    row = candidate["row"]
    raw_delta = _float_or_none(row.get("delta"))
    if raw_delta is not None:
        return raw_delta * 100.0 if abs(raw_delta) <= 1.0 else raw_delta
    left_pct = _candidate_percent_for_side(candidate, "left")
    right_pct = _candidate_percent_for_side(candidate, "right")
    if left_pct is None or right_pct is None:
        return None
    return left_pct - right_pct


def _score_bundle_candidate(
    segment: str,
    candidate: dict[str, Any],
    *,
    context_segment: str | None = None,
) -> tuple[bool, int, list[str], dict[str, Any]]:
    row = candidate["row"]
    file_name = candidate["file"]
    score = _context_priority(context_segment or segment, file_name)
    reasons: list[str] = []
    matched_metrics: list[str] = []
    mismatched_metrics: list[str] = []

    percents = _percent_mentions(segment)
    cohort_count_mentions = _extract_cohort_count_mentions(segment)
    ratios = [float(match) for match in _MULTIPLIER_RE.findall(segment)]
    delta_mentions = _delta_pct_point_mentions(segment)
    count_pairs = [
        (int(left), int(right)) for left, right in _COUNT_RATIO_RE.findall(segment)
    ]
    brand_match = _BRAND_COUNT_RE.search(segment)
    supported_roles = _candidate_supported_cohort_roles(candidate)
    mentioned_roles = {
        _coerce_percent_role_for_supported_source(mention.role, supported_roles)
        for mention in percents
        if mention.role
    }
    mentioned_roles.update(
        _coerce_percent_role_for_supported_source(mention["cohort"], supported_roles)
        for mention in cohort_count_mentions
    )
    mentioned_roles.discard(None)
    if mentioned_roles and not mentioned_roles <= supported_roles:
        reasons.append(
            "cohort label mismatch: text uses "
            + "/".join(sorted(mentioned_roles))
            + " but source row supports "
            + ("/".join(sorted(supported_roles)) or "unknown")
        )
        mismatched_metrics.append("cohort_basis")
        return (
            False,
            score,
            reasons,
            {
                "matched_metrics": matched_metrics,
                "mismatched_metrics": mismatched_metrics,
            },
        )

    if "pct_top_seller" in row or "pct_recent" in row:
        role_labeled_percents = _role_labeled_percent_mentions(segment, candidate)
        if role_labeled_percents is not None:
            for mention, role, expected_pct in role_labeled_percents:
                metric_name = f"{role}_percent"
                if _percent_matches(mention, expected_pct):
                    score += 1
                    matched_metrics.append(metric_name)
                else:
                    reasons.append(
                        f"{role} percent mismatch: expected "
                        f"{_format_optional_percent(expected_pct)}"
                    )
                    mismatched_metrics.append(metric_name)
        else:
            left_pct = _percent_from_fraction(
                row.get("pct_top_seller", row.get("pct_recent"))
            )
            right_pct = _percent_from_fraction(
                row.get("pct_other", row.get("pct_rest"))
            )
            if len(percents) >= 2:
                if left_pct is None or right_pct is None:
                    reasons.append(
                        "candidate is missing one or more comparable percent values"
                    )
                    mismatched_metrics.append("percent_pair")
                else:
                    left_role = (
                        "top_seller"
                        if "pct_top_seller" in row or "count_top_seller" in row
                        else "recent"
                    )
                    right_role = "other" if left_role == "top_seller" else "rest"
                    for mention, role, expected_pct in (
                        (percents[0], left_role, left_pct),
                        (percents[1], right_role, right_pct),
                    ):
                        metric_name = f"{role}_percent"
                        if _percent_matches(mention, expected_pct):
                            score += 1
                            matched_metrics.append(metric_name)
                        else:
                            reasons.append(
                                f"{role} percent mismatch: expected "
                                f"{_format_optional_percent(expected_pct)}"
                            )
                            mismatched_metrics.append(metric_name)
                    if not reasons and not matched_metrics and not mismatched_metrics:
                        matched_metrics.append("percent_pair")
                        score += 2
            elif len(percents) == 1:
                comparable_pcts = [
                    value for value in (left_pct, right_pct) if value is not None
                ]
                if not comparable_pcts:
                    reasons.append("candidate is missing comparable percent values")
                    mismatched_metrics.append("single_percent")
                elif any(
                    _percent_matches(percents[0], value) for value in comparable_pcts
                ):
                    score += 1
                    matched_metrics.append("single_percent")
                else:
                    reasons.append(
                        "single percent mismatch: expected one of "
                        + " / ".join(
                            _format_optional_percent(value) for value in comparable_pcts
                        )
                    )
                    mismatched_metrics.append("single_percent")

    for mention in cohort_count_mentions:
        cohort_role = (
            _coerce_percent_role_for_supported_source(
                mention["cohort"],
                supported_roles,
            )
            or mention["cohort"]
        )
        expected_count = _candidate_count_for_role(candidate, cohort_role)
        if expected_count is None:
            reasons.append(f"{cohort_role} count unavailable for candidate source row")
            mismatched_metrics.append(f"{cohort_role}_count")
        elif expected_count != mention["count"]:
            reasons.append(f"{cohort_role} count mismatch: expected {expected_count}")
            mismatched_metrics.append(f"{cohort_role}_count")
        else:
            score += 1
            matched_metrics.append(f"{cohort_role}_count")

    if count_pairs:
        left_count = _int_or_none(row.get("count_top_seller", row.get("count_recent")))
        left_base = _int_or_none(
            row.get(
                "top_seller_base",
                row.get("recent_base", row.get("recent_family_base")),
            )
        )
        if left_count is not None and left_base is not None:
            if (left_count, left_base) not in count_pairs:
                reasons.append(
                    f"count/base mismatch: expected {left_count}/{left_base}"
                )
                mismatched_metrics.append("count_base")
            else:
                score += 1
                matched_metrics.append("count_base")

    if brand_match:
        explicit_brand_role, brand_expectations = _brand_count_expectations(
            segment,
            brand_match.span(),
            candidate,
        )
        observed_brand_count = int(brand_match.group(1))
        if not brand_expectations:
            reasons.append("brand-count unavailable for candidate source row")
            mismatched_metrics.append("brand_count")
        elif not any(
            expected == observed_brand_count for _role, expected in brand_expectations
        ):
            prefix = f"{explicit_brand_role} " if explicit_brand_role else ""
            reasons.append(
                f"{prefix}brand-count mismatch: expected "
                f"{_format_brand_count_expectation(brand_expectations)}"
            )
            mismatched_metrics.append("brand_count")
        else:
            score += 1
            matched_metrics.append("brand_count")

    if delta_mentions:
        expected_delta = _bundle_candidate_signed_delta_pct_points(candidate)
        if expected_delta is None:
            reasons.append("delta percentage-point value unavailable for candidate row")
            mismatched_metrics.append("delta_pct_points")
        else:
            delta_matched = False
            for mention in delta_mentions:
                observed_delta = _float_or_none(mention.get("value"))
                if observed_delta is None:
                    continue
                expected_for_match = (
                    expected_delta
                    if bool(mention.get("signed"))
                    else abs(expected_delta)
                )
                tolerance = _float_or_none(mention.get("tolerance"))
                if _approx_equal(
                    observed_delta,
                    expected_for_match,
                    tolerance if tolerance is not None else _PERCENT_TOLERANCE,
                ):
                    delta_matched = True
                    break
            if delta_matched:
                score += 1
                matched_metrics.append("delta_pct_points")
            else:
                reasons.append(
                    "delta percentage-point mismatch: expected "
                    f"{expected_delta:+.1f} pp"
                )
                mismatched_metrics.append("delta_pct_points")

    if ratios:
        expected_ratio = _float_or_none(row.get("prevalence_ratio"))
        if expected_ratio is not None:
            if any(
                _approx_equal(value, expected_ratio, _MULTIPLIER_TOLERANCE)
                for value in ratios
            ):
                score += 1
                matched_metrics.append("prevalence_ratio")
            else:
                reasons.append(f"ratio mismatch: expected {expected_ratio:.2f}x")
                mismatched_metrics.append("prevalence_ratio")

    return (
        not reasons,
        score,
        reasons,
        {
            "matched_metrics": matched_metrics,
            "mismatched_metrics": mismatched_metrics,
        },
    )


def _extract_numeric_claim_evidence(segment: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    percents = _percent_mentions(segment)
    if percents:
        evidence["percents"] = [mention.value for mention in percents]
    count_pairs = [
        {"count": int(left), "base": int(right)}
        for left, right in _COUNT_RATIO_RE.findall(segment)
    ]
    if count_pairs:
        evidence["count_pairs"] = count_pairs
    cohort_counts = _extract_cohort_count_mentions(segment)
    if cohort_counts:
        evidence["cohort_counts"] = {
            mention["cohort"]: mention["count"] for mention in cohort_counts
        }
    ratios = [float(match) for match in _MULTIPLIER_RE.findall(segment)]
    if ratios:
        evidence["ratios"] = ratios
    delta_mentions = _delta_pct_point_mentions(segment)
    if delta_mentions:
        evidence["delta_pct_points"] = [
            mention["value"]
            for mention in delta_mentions
            if _float_or_none(mention.get("value")) is not None
        ]
    brand_match = _BRAND_COUNT_RE.search(segment)
    if brand_match is not None:
        evidence["brand_count"] = int(brand_match.group(1))
    return evidence


def _signed_rank_delta_mentions(segment: str) -> list[float]:
    values: list[float] = []
    for match in _SIGNED_RANK_DELTA_RE.finditer(segment):
        value = _float_or_none(match.group("value"))
        if value is not None:
            values.append(value)
    return values


def _looks_like_unanchored_rank_delta_claim(segment: str) -> bool:
    match = _SIGNED_RANK_DELTA_RE.search(segment)
    if match is None:
        return False
    prefix = _normalize_text(segment[: match.start()])
    if ":" in prefix:
        return False
    lowered = segment.casefold()
    return any(
        marker in lowered
        for marker in (
            "newness-skewed",
            "newness skewed",
            "top-seller",
            "top seller",
            "bundle strength",
            "rank",
        )
    )


def _unanchored_rank_delta_details(segment: str) -> dict[str, Any]:
    values = _signed_rank_delta_mentions(segment)
    observed_values: dict[str, Any] = {}
    if values:
        observed_values["signed_rank_delta"] = values
    return {
        "message": (
            "rank-delta text has no visible attribute or bundle anchor in the "
            "mapped OCR text; deterministic validation requires an explicit "
            "same-unit entity label before matching package rows"
        ),
        "observed_values": observed_values,
        "aggregation_rule_id": "rank_delta_anchor_required_v1",
        "required_anchor": "attribute or bundle label in the same mapped text unit",
        "source_file_candidates": ["sort_rank_delta_attributes.csv"],
    }


def _bundle_candidate_package_values(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    values: dict[str, Any] = {}
    for key in (
        "bundle_label",
        "attribute_name",
        "attribute_value",
        "filter_family",
        "filter_value",
        "count_top_seller",
        "top_seller_base",
        "count_other",
        "other_base",
        "pct_top_seller",
        "pct_other",
        "pct_recent",
        "pct_rest",
        "count_recent",
        "recent_base",
        "recent_family_base",
        "count_rest",
        "rest_base",
        "rest_family_base",
        "top_seller_brand_count",
        "other_brand_count",
        "recent_brand_count",
        "rest_brand_count",
        "all_match_count",
        "all_brand_count",
        "top_seller_dominant_brand",
        "top_seller_dominant_brand_count",
        "top_seller_dominant_brand_share",
        "top_seller_dominant_brand_tied",
        "other_dominant_brand",
        "other_dominant_brand_count",
        "other_dominant_brand_share",
        "other_dominant_brand_tied",
        "recent_dominant_brand",
        "recent_dominant_brand_count",
        "recent_dominant_brand_share",
        "recent_dominant_brand_tied",
        "rest_dominant_brand",
        "rest_dominant_brand_count",
        "rest_dominant_brand_share",
        "rest_dominant_brand_tied",
        "prevalence_ratio",
        "computed_selectors",
        "calculation_helper_id",
        "calculation_source",
        "calculation_column",
    ):
        if key not in row or row.get(key) is None:
            continue
        value = row.get(key)
        if key.startswith("pct_"):
            values[key] = _percent_from_fraction(value)
            continue
        if isinstance(value, float):
            values[key] = round(value, 4)
            continue
        values[key] = value
    delta_pct_points = _bundle_candidate_signed_delta_pct_points(candidate)
    if delta_pct_points is not None:
        values["delta_pct_points"] = round(delta_pct_points, 4)
    return values


def _candidate_primary_label(candidate: dict[str, Any]) -> str:
    row = candidate["row"]
    return _normalize_text(
        row.get("bundle_label") or row.get("attribute_value") or row.get("filter_value")
    )


def _candidate_bundle_part_count(candidate: dict[str, Any]) -> int:
    return max(1, len(_bundle_parts(_candidate_primary_label(candidate))))


def _candidate_percent_for_side(
    candidate: dict[str, Any],
    side: str,
) -> float | None:
    row = candidate["row"]
    if side == "left":
        return _percent_from_fraction(row.get("pct_top_seller", row.get("pct_recent")))
    return _percent_from_fraction(row.get("pct_other", row.get("pct_rest")))


def _candidate_percent_for_role(
    candidate: dict[str, Any],
    role: str,
) -> float | None:
    row = candidate["row"]
    if role == "top_seller":
        return _percent_from_fraction(row.get("pct_top_seller"))
    if role == "other":
        return _percent_from_fraction(row.get("pct_other"))
    if role == "recent":
        return _percent_from_fraction(row.get("pct_recent"))
    if role == "rest":
        return _percent_from_fraction(row.get("pct_rest"))
    return None


def _candidate_count_for_role(candidate: dict[str, Any], role: str) -> int | None:
    row = candidate["row"]
    if role == "top_seller":
        return _int_or_none(row.get("count_top_seller"))
    if role == "other":
        return _int_or_none(row.get("count_other"))
    if role == "recent":
        return _int_or_none(row.get("count_recent"))
    if role == "rest":
        return _int_or_none(row.get("count_rest"))
    return None


def _candidate_base_for_role(candidate: dict[str, Any], role: str) -> int | None:
    row = candidate["row"]
    if role == "top_seller":
        return _int_or_none(row.get("top_seller_base"))
    if role == "other":
        return _int_or_none(row.get("other_base"))
    if role == "recent":
        return _int_or_none(row.get("recent_base", row.get("recent_family_base")))
    if role == "rest":
        return _int_or_none(row.get("rest_base", row.get("rest_family_base")))
    return None


def _candidate_brand_span_for_role(candidate: dict[str, Any], role: str) -> int | None:
    row = candidate["row"]
    if role == "all":
        return _int_or_none(row.get("all_brand_count"))
    if role == "top_seller":
        return _int_or_none(row.get("top_seller_brand_count"))
    if role == "other":
        return _int_or_none(row.get("other_brand_count"))
    if role == "recent":
        return _int_or_none(row.get("recent_brand_count"))
    if role == "rest":
        return _int_or_none(row.get("rest_brand_count"))
    return None


def _candidate_percent_role_mentions(
    segment: str,
    candidate: dict[str, Any],
) -> list[tuple[_PercentMention, str]]:
    mentions = _percent_mentions(segment)
    if not mentions:
        return []

    role_labeled_mentions = _role_labeled_percent_mentions(segment, candidate)
    if role_labeled_mentions is not None:
        return [(mention, role) for mention, role, _expected in role_labeled_mentions]

    supported_roles = _candidate_supported_cohort_roles(candidate)
    if len(mentions) >= 2:
        basis = _candidate_source_cohort_basis(candidate)
        if basis == "top_seller_vs_other":
            roles = ["top_seller", "other"]
        elif basis == "recent_vs_rest":
            roles = ["recent", "rest"]
        else:
            return []
        return [
            (mention, role)
            for mention, role in zip(mentions[: len(roles)], roles, strict=False)
        ]

    strict_role = _coerce_percent_role_for_supported_source(
        _strict_percent_role(segment, mentions[0].span) or mentions[0].role,
        supported_roles,
    )
    if strict_role is not None:
        return [(mentions[0], strict_role)]

    primary_role = _candidate_primary_population_role(candidate)
    if primary_role is None:
        return []
    return [(mentions[0], primary_role)]


def _numeric_basis_diagnostics(
    segment: str,
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for mention, role in _candidate_percent_role_mentions(segment, candidate):
        expected_percent = _candidate_percent_for_role(candidate, role)
        if expected_percent is None or _percent_matches(mention, expected_percent):
            continue
        current_count = _candidate_count_for_role(candidate, role)
        current_base = _candidate_base_for_role(candidate, role)
        diagnostic: dict[str, Any] = {
            "role": role,
            "observed_percent": mention.value,
            "expected_percent": expected_percent,
            "current_count": current_count,
            "current_base": current_base,
            "note": "observed percentage does not match current package count/base",
        }
        if current_count is not None and mention.value > 0:
            implied_base = round(current_count * 100.0 / mention.value)
            if implied_base > 0:
                diagnostic["implied_base_if_current_count_held"] = implied_base
                diagnostic["implied_percent_if_current_count_held"] = (
                    100.0 * current_count / implied_base
                )
        if current_base is not None and current_base > 0:
            implied_count = round(mention.value * current_base / 100.0)
            if 0 <= implied_count <= current_base:
                diagnostic["implied_count_if_current_base_held"] = implied_count
                diagnostic["implied_percent_if_current_base_held"] = (
                    100.0 * implied_count / current_base
                )
        diagnostics.append(diagnostic)
    return diagnostics


def _numeric_basis_diagnostic_fields(
    segment: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = _numeric_basis_diagnostics(segment, candidate)
    if not diagnostics:
        return {}
    return {"numeric_basis_diagnostics": diagnostics}


def _candidate_dominant_brand_for_role(
    candidate: dict[str, Any],
    role: str,
) -> str | None:
    return _normalize_text(candidate["row"].get(f"{role}_dominant_brand")) or None


def _candidate_dominant_brand_count_for_role(
    candidate: dict[str, Any],
    role: str,
) -> int | None:
    return _int_or_none(candidate["row"].get(f"{role}_dominant_brand_count"))


def _candidate_dominant_brand_share_for_role(
    candidate: dict[str, Any],
    role: str,
) -> float | None:
    row = candidate["row"]
    value = _percent_from_fraction(row.get(f"{role}_dominant_brand_share"))
    if value is not None:
        return value
    dominant_count = _candidate_dominant_brand_count_for_role(candidate, role)
    bundle_count = _candidate_count_for_role(candidate, role)
    if dominant_count is None or bundle_count in (None, 0):
        return None
    return 100.0 * dominant_count / bundle_count


def _brand_names_compatible(observed: Any, expected: Any) -> bool:
    observed_key = _canonical_text(observed)
    expected_key = _canonical_text(expected)
    if not observed_key or not expected_key:
        return False
    return (
        observed_key == expected_key
        or expected_key.startswith(observed_key)
        or observed_key.startswith(expected_key)
    )


def _candidate_primary_population_role(candidate: dict[str, Any]) -> str | None:
    file_name = _normalize_text(candidate.get("file"))
    if file_name.startswith("top_seller_"):
        return "top_seller"
    if file_name.startswith("innovation_"):
        return "recent"
    basis = _candidate_source_cohort_basis(candidate)
    if basis.startswith("top_seller"):
        return "top_seller"
    if basis.startswith("recent"):
        return "recent"
    return None


def _candidate_supported_cohort_roles(candidate: dict[str, Any]) -> set[str]:
    row = candidate["row"]
    roles: set[str] = set()
    if any(key in row for key in ("pct_top_seller", "count_top_seller")):
        roles.add("top_seller")
    if any(key in row for key in ("pct_other", "count_other")):
        roles.add("other")
    if any(key in row for key in ("pct_recent", "count_recent")):
        roles.add("recent")
    if any(key in row for key in ("pct_rest", "count_rest")):
        roles.add("rest")
    return roles


def _candidate_source_cohort_basis(candidate: dict[str, Any]) -> str:
    roles = _candidate_supported_cohort_roles(candidate)
    if {"top_seller", "other"} <= roles:
        return "top_seller_vs_other"
    if {"recent", "rest"} <= roles:
        return "recent_vs_rest"
    if "top_seller" in roles:
        return "top_seller"
    if "recent" in roles:
        return "recent"
    return "unknown"


def _parsed_cohort_labels(segment: str) -> list[str]:
    labels = _unique_texts(
        mention.role for mention in _percent_mentions(segment) if mention.role
    )
    if labels:
        return labels
    lowered = segment.casefold()
    inferred: list[str] = []
    for label, pattern in (
        ("top_seller", r"\btop[-\s]?sellers?\b|\bwinners?\b|\bwinning\b"),
        ("other", r"\bothers?\b|\bremaining\b"),
        ("recent", r"\brecent\b"),
        ("rest", r"\brest\b"),
    ):
        if re.search(pattern, lowered):
            inferred.append(label)
    return inferred


def _candidate_row_keys(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    keys: dict[str, Any] = {}
    for key in (
        "bundle_label",
        "attribute_name",
        "attribute_value",
        "filter_family",
        "filter_value",
        "brand",
        "product_name",
        "calculation_helper_id",
    ):
        value = row.get(key)
        if value is not None and _normalize_text(value):
            keys[key] = value
    return keys


def _numeric_tolerance_policy() -> dict[str, Any]:
    return {
        "percent_tolerance_points": _PERCENT_TOLERANCE,
        "multiplier_tolerance": _MULTIPLIER_TOLERANCE,
        "rounding": "accepts displayed percentage rounding based on decimal precision",
    }


def _bundle_evidence_details(
    segment: str,
    candidate: dict[str, Any],
    *,
    reasons: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = _candidate_population_profile(candidate)
    details: dict[str, Any] = {
        "observed_values": _extract_numeric_claim_evidence(segment),
        "package_values": _bundle_candidate_package_values(candidate),
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "parsed_cohort_labels": _parsed_cohort_labels(segment),
        "source_cohort_basis": _candidate_source_cohort_basis(candidate),
        "denominators": {
            profile["left_label"]: profile["left_base"],
            profile["right_label"]: profile["right_base"],
        },
        "counts": {
            profile["left_label"]: profile["left_count"],
            profile["right_label"]: profile["right_count"],
        },
        "tolerance_policy": _numeric_tolerance_policy(),
    }
    if reasons:
        details["reasons"] = reasons
    numeric_basis_diagnostics = _numeric_basis_diagnostics(segment, candidate)
    if numeric_basis_diagnostics:
        details["numeric_basis_diagnostics"] = numeric_basis_diagnostics
    if extra:
        details.update(extra)
    return details


def _bundle_brand_concentration_threshold_policy() -> dict[str, Any]:
    return {
        "single_brand_share_threshold_pct": (
            _BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT
        ),
        "minimum_brand_span": _BUNDLE_BRAND_CONCENTRATION_MIN_BRAND_SPAN,
    }


def _computed_bundle_selector_quality(candidate: dict[str, Any]) -> float:
    if candidate.get("kind") != "computed_bundle":
        return 0.0
    selectors = candidate.get("row", {}).get("computed_selectors")
    if not isinstance(selectors, list):
        return 0.0

    score = 0.0
    low_quality_column_tokens = (
        "also",
        "brandclaims",
        "children",
        "evidence",
        "inferred",
        "mapped",
        "notintaxonomy",
        "other",
        "secondary",
        "source",
        "unknown",
    )
    for selector in selectors:
        if not isinstance(selector, dict):
            continue
        column_key = _canonical_text(selector.get("column"))
        score += 10.0
        if any(token in column_key for token in low_quality_column_tokens):
            score -= 4.0
        score -= min(len(column_key), 40) / 100.0
        if selector.get("selector_kind") == "boolean_indicator":
            score -= 0.5
    return score


def _looks_like_bundle_brand_concentration_claim(text: str) -> bool:
    lowered = text.casefold()
    if (
        any(
            marker in lowered
            for marker in ("evidence ratio", "market signal", "penetration")
        )
        and "brand concentration" not in lowered
    ):
        return False
    return bool(
        _BUNDLE_BRAND_SPAN_RE.search(text)
        or (_BUNDLE_BRAND_DISTRIBUTION_RE.search(text) and "+" in text)
        or (
            "distinct brands" in lowered
            and ("+" in text or "bundle" in lowered or "triple" in lowered)
        )
        or ("top-selling brands" in lowered and ("+" in text or "bundle" in lowered))
        or ("top selling brands" in lowered and ("+" in text or "bundle" in lowered))
        or (
            "concentrated in rank" in lowered
            and ("+" in text or "bundle" in lowered or "lane" in lowered)
        )
        or (
            "highly concentrated" in lowered
            and ("+" in text or "bundle" in lowered or "lane" in lowered)
        )
        or (
            "brand concentration" in lowered
            and ("+" in text or "bundle" in lowered or "lane" in lowered)
        )
        or (
            "concentration" in lowered
            and "brand" in lowered
            and ("+" in text or "bundle" in lowered)
        )
        or (
            "distributed across" in lowered
            and ("+" in text or "bundle" in lowered or "triple" in lowered)
        )
        or (
            "spread across" in lowered
            and ("+" in text or "bundle" in lowered or "triple" in lowered)
        )
        or (
            "spans" in lowered
            and "brands" in lowered
            and ("+" in text or "bundle" in lowered)
        )
        or (
            "single-brand artifact" in lowered
            or "single-brand lock-in" in lowered
            or "multi-brand movement" in lowered
            or "provides amplitude" in lowered
            or "direction itself" in lowered
        )
        or ("concentration" in lowered and "bundle" in lowered)
        or (
            "accounts for" in lowered
            and "concentration" in lowered
            and "brand" in lowered
        )
    )


def _looks_like_bundle_brand_concentration_row(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        (
            _BUNDLE_BRAND_SPAN_RE.search(text)
            or _BUNDLE_BRAND_DISTRIBUTION_RE.search(text)
            and (
                "accounts for" in lowered
                or "no brand above" in lowered
                or "multi-brand" in lowered
            )
        )
        or _BUNDLE_BRAND_SPAN_RE.search(text)
        or _BUNDLE_BRAND_DISTRIBUTION_RE.search(text)
        or (
            "accounts for" in lowered
            and "concentration" in lowered
            and "brand" in lowered
        )
    )


def _extract_accounts_for_brand_name(text: str) -> str | None:
    match = re.search(r"\baccounts\s+for\b", text, flags=re.IGNORECASE)
    if match is None:
        return None
    prefix = _normalize_text(text[: match.start()])
    if not prefix:
        return None
    for separator in ("|", ";", ":"):
        if separator in prefix:
            prefix = prefix.split(separator)[-1]
    if "(" in prefix:
        prefix = prefix.rsplit("(", 1)[-1]
    prefix = prefix.rsplit(".", 1)[-1].strip(" -")
    return _normalize_text(prefix) or None


def _extract_bundle_brand_concentration_evidence(segment: str) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    brand_span_match = _BUNDLE_BRAND_SPAN_RE.search(segment)
    if brand_span_match is not None:
        evidence["brand_span"] = int(brand_span_match.group(1))
    brand_distribution_match = _BUNDLE_BRAND_DISTRIBUTION_RE.search(segment)
    if brand_distribution_match is not None:
        evidence["brand_span"] = int(brand_distribution_match.group(1))
    matched_top_seller_count_match = _BUNDLE_MATCHED_TOP_SELLER_COUNT_RE.search(segment)
    if matched_top_seller_count_match is not None:
        evidence["bundle_count"] = int(matched_top_seller_count_match.group(1))

    brand_name = _extract_accounts_for_brand_name(segment)
    share_match = _BUNDLE_DOMINANT_BRAND_SHARE_RE.search(segment)
    if brand_name and share_match is not None:
        evidence["dominant_brand_name"] = brand_name
        evidence["dominant_brand_share"] = float(share_match.group(1))

    count_match = _BUNDLE_DOMINANT_BRAND_COUNT_RE.search(segment)
    if brand_name and count_match is not None:
        evidence["dominant_brand_name"] = brand_name
        evidence["dominant_brand_count"] = int(count_match.group(1))
        evidence["bundle_count"] = int(count_match.group(2))
        if (
            evidence.get("dominant_brand_share") is None
            and int(count_match.group(2)) > 0
        ):
            evidence["dominant_brand_share"] = (
                100.0 * int(count_match.group(1)) / int(count_match.group(2))
            )

    no_brand_above_match = _BUNDLE_NO_BRAND_ABOVE_RE.search(segment)
    if no_brand_above_match is not None:
        evidence["dominant_brand_count_ceiling"] = int(no_brand_above_match.group(1))

    return evidence


def _best_bundle_brand_concentration_candidate(
    label: str,
    frames: dict[str, pl.DataFrame],
    *,
    context_segment: str,
) -> dict[str, Any] | None:
    target_label = _normalize_text(label)
    candidates: list[tuple[int, dict[str, Any]]] = []
    candidate_rows = _bundle_candidates(label, frames)
    if not candidate_rows:
        candidate_rows = _computed_bundle_candidates(label, frames)
    for candidate in candidate_rows:
        if candidate.get("kind") not in {"bundle", "computed_bundle"}:
            continue
        primary_role = _candidate_primary_population_role(candidate)
        if primary_role is None:
            continue
        if _candidate_brand_span_for_role(candidate, primary_role) is None:
            continue
        score = _context_priority(context_segment, candidate["file"])
        score += 2
        candidate_label = _normalize_text(_candidate_primary_label(candidate))
        if candidate_label.casefold() == target_label.casefold():
            score += 4
        elif _bundle_label_key(candidate_label) == _bundle_label_key(target_label):
            score += 3
        elif _bundle_label_matches(label, candidate_label):
            score += 2
        if (
            _candidate_dominant_brand_count_for_role(candidate, primary_role)
            is not None
        ):
            score += 1
        candidates.append((score, candidate))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[0],
            _normalize_text(_candidate_primary_label(item[1])).casefold()
            == target_label.casefold(),
            _bundle_label_key(_candidate_primary_label(item[1]))
            == _bundle_label_key(target_label),
            _candidate_bundle_part_count(item[1]),
            item[1]["file"].startswith("top_seller_"),
        ),
        reverse=True,
    )
    best_score, best_candidate = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best_score:
        tied_candidates = [
            candidate for score, candidate in candidates if score == best_score
        ]

        def _support_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
            role = _candidate_primary_population_role(candidate) or ""
            return (
                candidate["file"],
                _bundle_label_key(_candidate_primary_label(candidate)),
                role,
                _candidate_brand_span_for_role(candidate, role),
                _candidate_dominant_brand_for_role(candidate, role),
                _candidate_dominant_brand_count_for_role(candidate, role),
                round(
                    _candidate_dominant_brand_share_for_role(candidate, role) or -1.0,
                    4,
                ),
            )

        exact_label_matches = [
            candidate
            for candidate in tied_candidates
            if _normalize_text(_candidate_primary_label(candidate)).casefold()
            == target_label.casefold()
        ]
        if len(exact_label_matches) == 1:
            return exact_label_matches[0]

        support_signatures = {
            _support_signature(candidate) for candidate in tied_candidates
        }
        if len(support_signatures) == 1:
            return tied_candidates[0]
        if all(
            candidate.get("kind") == "computed_bundle" for candidate in tied_candidates
        ):
            tied_candidates.sort(
                key=lambda candidate: _computed_bundle_selector_quality(candidate),
                reverse=True,
            )
            return tied_candidates[0]
        return None
    return best_candidate


def _candidate_is_not_single_brand_artifact(
    candidate: dict[str, Any],
) -> tuple[bool, list[str]]:
    role = _candidate_primary_population_role(candidate)
    if role is None:
        return False, ["candidate has no clear primary cohort role"]

    reasons: list[str] = []
    brand_span = _candidate_brand_span_for_role(candidate, role)
    dominant_share = _candidate_dominant_brand_share_for_role(candidate, role)
    dominant_count = _candidate_dominant_brand_count_for_role(candidate, role)
    bundle_count = _candidate_count_for_role(candidate, role)

    if (
        brand_span is not None
        and brand_span < _BUNDLE_BRAND_CONCENTRATION_MIN_BRAND_SPAN
    ):
        reasons.append("brand span falls below minimum broad-based threshold")
    if (
        dominant_share is not None
        and dominant_share >= _BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT
    ):
        reasons.append("dominant brand share meets single-brand collapse threshold")
    elif (
        dominant_count is not None
        and bundle_count not in (None, 0)
        and dominant_count >= bundle_count
    ):
        reasons.append("one brand occupies the full matched bundle count")

    return not reasons, reasons


def _bundle_brand_concentration_details(
    *,
    observed_values: dict[str, Any],
    candidate: dict[str, Any],
    reasons: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = _candidate_primary_population_role(candidate)
    details: dict[str, Any] = {
        "observed_values": observed_values,
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "bundle_label": _candidate_primary_label(candidate),
        "brand_span": _candidate_brand_span_for_role(candidate, role or ""),
        "dominant_brand_name": _candidate_dominant_brand_for_role(
            candidate, role or ""
        ),
        "dominant_brand_count": _candidate_dominant_brand_count_for_role(
            candidate,
            role or "",
        ),
        "dominant_brand_share": _candidate_dominant_brand_share_for_role(
            candidate,
            role or "",
        ),
        "package_values": _bundle_candidate_package_values(candidate),
        "threshold_policy": _bundle_brand_concentration_threshold_policy(),
    }
    if reasons:
        details["reasons"] = reasons
    if extra:
        details.update(extra)
    return details


def _validate_bundle_brand_concentration_row(
    segment: str,
    *,
    frames: dict[str, pl.DataFrame],
    bundle_records: list[_BundleLabelRecord],
    context_segment: str,
) -> dict[str, Any] | None:
    explicit_labels = _resolved_explicit_bundle_labels_from_segment(
        context_segment,
        bundle_records,
        frames,
    )
    fallback_labels = _matched_bundle_labels(context_segment, bundle_records)
    label_groups = [labels for labels in (explicit_labels, fallback_labels) if labels]
    if not label_groups:
        return None

    for matched_labels in label_groups:
        candidate_results: list[dict[str, Any]] = []
        for label in matched_labels:
            label_resolution = _resolve_bundle_label_targets(segment, label, frames)
            for target_label in label_resolution["labels"]:
                candidate = _best_bundle_brand_concentration_candidate(
                    target_label,
                    frames,
                    context_segment=context_segment,
                )
                if candidate is None:
                    continue
                observed_values = _extract_bundle_brand_concentration_evidence(segment)
                role = _candidate_primary_population_role(candidate)
                if role is None:
                    continue

                reasons: list[str] = []
                percent_mentions = _percent_mentions(segment)
                share_tolerance = (
                    percent_mentions[0].tolerance
                    if percent_mentions
                    else _PERCENT_TOLERANCE
                )
                expected_brand_span = _candidate_brand_span_for_role(candidate, role)
                if (
                    observed_values.get("brand_span") is not None
                    and expected_brand_span is not None
                    and expected_brand_span != observed_values["brand_span"]
                ):
                    reasons.append(
                        f"brand-span mismatch: expected {expected_brand_span}"
                    )

                observed_brand_name = observed_values.get("dominant_brand_name")
                expected_brand_name = _candidate_dominant_brand_for_role(
                    candidate, role
                )
                if observed_brand_name and expected_brand_name:
                    if not _brand_names_compatible(
                        observed_brand_name, expected_brand_name
                    ):
                        reasons.append(
                            f"dominant-brand mismatch: expected {expected_brand_name}"
                        )

                observed_share = observed_values.get("dominant_brand_share")
                expected_share = _candidate_dominant_brand_share_for_role(
                    candidate, role
                )
                if (
                    observed_share is not None
                    and expected_share is not None
                    and not _approx_equal(
                        observed_share,
                        expected_share,
                        share_tolerance,
                    )
                ):
                    reasons.append(
                        f"dominant-brand share mismatch: expected {expected_share:.1f}%"
                    )

                observed_count = observed_values.get("dominant_brand_count")
                expected_count = _candidate_dominant_brand_count_for_role(
                    candidate, role
                )
                if (
                    observed_count is not None
                    and expected_count is not None
                    and observed_count != expected_count
                ):
                    reasons.append(
                        f"dominant-brand count mismatch: expected {expected_count}"
                    )

                observed_bundle_count = observed_values.get("bundle_count")
                expected_bundle_count = _candidate_count_for_role(candidate, role)
                if (
                    observed_bundle_count is not None
                    and expected_bundle_count is not None
                    and observed_bundle_count != expected_bundle_count
                ):
                    reasons.append(
                        f"bundle-count mismatch: expected {expected_bundle_count}"
                    )

                ceiling = observed_values.get("dominant_brand_count_ceiling")
                if (
                    ceiling is not None
                    and expected_count is not None
                    and expected_count > ceiling
                ):
                    reasons.append(
                        "dominant-brand count exceeds ceiling: "
                        f"expected at most {ceiling}"
                    )

                non_collapse, non_collapse_reasons = (
                    _candidate_is_not_single_brand_artifact(candidate)
                )
                candidate_results.append(
                    {
                        "status": "pass" if not reasons else "fail",
                        "candidate": candidate,
                        "entity": target_label,
                        "observed_values": observed_values,
                        "reasons": reasons,
                        "non_collapse": non_collapse,
                        "non_collapse_reasons": non_collapse_reasons,
                    }
                )

        if not candidate_results:
            continue

        candidate_results.sort(
            key=lambda item: (
                item["status"] == "pass",
                _candidate_primary_population_role(item["candidate"]) == "top_seller",
                _candidate_bundle_part_count(item["candidate"]),
            ),
            reverse=True,
        )
        return candidate_results[0]
    return None


def _looks_like_contextual_single_brand_concentration_claim(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        "single brand" in lowered
        and ("concentrated" in lowered or "concentration" in lowered)
        and ("signal" in lowered or "bundle" in lowered or "lane" in lowered)
    )


def _bundle_review_brand_distribution(
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    review_df = frames.get("bundle_review_validation.csv")
    if (
        review_df is None
        or review_df.is_empty()
        or "bundle_label" not in review_df.columns
        or "brand" not in review_df.columns
    ):
        return None

    brand_counts: dict[str, int] = {}
    matched_count = 0
    matched_label = ""
    for row in review_df.select(["bundle_label", "brand"]).to_dicts():
        row_label = _normalize_text(row.get("bundle_label"))
        brand = _normalize_text(row.get("brand"))
        if not row_label or not brand:
            continue
        if not _bundle_label_matches(label, row_label):
            continue
        matched_count += 1
        matched_label = matched_label or row_label
        brand_counts[brand] = brand_counts.get(brand, 0) + 1

    if not brand_counts or matched_count <= 0:
        return None

    dominant_brand, dominant_count = max(
        brand_counts.items(),
        key=lambda item: (item[1], item[0].casefold()),
    )
    return {
        "bundle_label": matched_label or _normalize_text(label),
        "matched_review_product_count": matched_count,
        "brand_counts": brand_counts,
        "dominant_brand_name": dominant_brand,
        "dominant_brand_count": dominant_count,
        "dominant_brand_share": 100.0 * dominant_count / matched_count,
        "brand_span": len(brand_counts),
    }


def _validate_contextual_single_brand_concentration_segment(
    segment: str,
    *,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_contextual_single_brand_concentration_claim(segment):
        return None

    distribution = _bundle_review_brand_distribution(label, frames)
    if distribution is None:
        return {
            "status": "warning",
            "message": "bundle review brand distribution was not available",
            "bundle_label": _normalize_text(label),
        }

    reasons: list[str] = []
    percent_mentions = _percent_mentions(segment)
    observed_share = percent_mentions[0].value if percent_mentions else None
    expected_share = _float_or_none(distribution.get("dominant_brand_share"))
    share_tolerance = (
        percent_mentions[0].tolerance if percent_mentions else _PERCENT_TOLERANCE
    )
    if (
        observed_share is not None
        and expected_share is not None
        and not _approx_equal(observed_share, expected_share, share_tolerance)
    ):
        reasons.append(f"dominant-brand share mismatch: expected {expected_share:.1f}%")

    threshold = _BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT
    if expected_share is not None and expected_share < threshold:
        reasons.append(
            "dominant-brand share does not meet single-brand concentration threshold: "
            f"{expected_share:.1f}% < {threshold:.1f}%"
        )

    observed_values: dict[str, Any] = {}
    if observed_share is not None:
        observed_values["dominant_brand_share"] = observed_share

    return {
        "status": "pass" if not reasons else "fail",
        "observed_values": observed_values,
        "package_values": distribution,
        "source_file": "bundle_review_validation.csv",
        "matched_row_keys": {"bundle_label": distribution["bundle_label"]},
        "threshold_policy": _bundle_brand_concentration_threshold_policy(),
        "reasons": reasons,
    }


def _looks_like_contextual_top_seller_overindex_claim(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        re.search(
            r"\b(?:sharpest|strongest)\s+top[-\s]?seller\s+over[-\s]?index\b",
            lowered,
        )
    )


def _bundle_prevalence_ratio_rank(
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    target_part_count = max(1, len(_bundle_parts(label)))
    candidates = [
        candidate
        for candidate in _bundle_candidates(label, frames)
        if candidate.get("kind") == "bundle"
        and _normalize_text(candidate.get("file")).startswith("top_seller_")
        and _float_or_none(candidate.get("row", {}).get("prevalence_ratio")) is not None
    ]
    same_size_candidates = [
        candidate
        for candidate in candidates
        if _candidate_bundle_part_count(candidate) == target_part_count
    ]
    if same_size_candidates:
        candidates = same_size_candidates
    if not candidates:
        return None

    expected_file = (
        "top_seller_triples.csv" if target_part_count >= 3 else "top_seller_pairs.csv"
    )
    candidates.sort(
        key=lambda candidate: (
            _normalize_text(_candidate_primary_label(candidate)).casefold()
            == _normalize_text(label).casefold(),
            candidate["file"] == expected_file,
            _float_or_none(candidate["row"].get("prevalence_ratio")) or -1.0,
        ),
        reverse=True,
    )
    candidate = candidates[0]
    source_file = candidate["file"]
    source_df = frames[source_file]
    columns, _schema = get_schema_and_column_names(source_df)
    if source_df.is_empty() or "bundle_label" not in columns:
        return None

    peer_rows: list[dict[str, Any]] = []
    for row in source_df.to_dicts():
        ratio = _float_or_none(row.get("prevalence_ratio"))
        if ratio is None:
            continue
        row_label = _normalize_text(row.get("bundle_label"))
        if not row_label:
            continue
        row_part_count = _int_or_none(row.get("bundle_size")) or max(
            1,
            len(_bundle_parts(row_label)),
        )
        if row_part_count != target_part_count:
            continue
        peer_rows.append(row)
    if not peer_rows:
        return None

    peer_rows.sort(
        key=lambda row: (
            _float_or_none(row.get("prevalence_ratio")) or -1.0,
            _normalize_text(row.get("bundle_label")).casefold(),
        ),
        reverse=True,
    )
    candidate_key = _bundle_label_key(_candidate_primary_label(candidate))
    observed_rank = None
    for row_index, row in enumerate(peer_rows, start=1):
        if _bundle_label_key(_normalize_text(row.get("bundle_label"))) == candidate_key:
            observed_rank = row_index
            break
    if observed_rank is None:
        return None

    top_row = peer_rows[0]
    return {
        "candidate": candidate,
        "source_file": source_file,
        "observed_rank": observed_rank,
        "peer_count": len(peer_rows),
        "top_bundle_label": _normalize_text(top_row.get("bundle_label")),
        "top_prevalence_ratio": _float_or_none(top_row.get("prevalence_ratio")),
    }


def _validate_contextual_top_seller_overindex_segment(
    segment: str,
    *,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_contextual_top_seller_overindex_claim(segment):
        return None

    rank_result = _bundle_prevalence_ratio_rank(label, frames)
    if rank_result is None:
        return {
            "status": "warning",
            "message": "bundle prevalence-ratio rank was not available",
            "bundle_label": _normalize_text(label),
        }

    candidate = rank_result["candidate"]
    observed_rank = _int_or_none(rank_result.get("observed_rank"))
    reasons: list[str] = []
    if observed_rank != 1:
        reasons.append(
            "bundle is not the top-ranked top-seller over-index by prevalence ratio: "
            f"observed rank {observed_rank} of {rank_result['peer_count']}; "
            f"top bundle is {rank_result['top_bundle_label']}"
        )

    return {
        "status": "pass" if not reasons else "fail",
        "candidate": candidate,
        "source_file": rank_result["source_file"],
        "observed_values": {
            "descriptor": "sharpest_top_seller_overindex",
            "observed_rank": observed_rank,
        },
        "package_values": {
            **_bundle_candidate_package_values(candidate),
            "prevalence_ratio_rank": observed_rank,
            "peer_bundle_count": rank_result["peer_count"],
            "top_bundle_label": rank_result["top_bundle_label"],
            "top_prevalence_ratio": rank_result["top_prevalence_ratio"],
        },
        "matched_row_keys": _candidate_row_keys(candidate),
        "threshold_policy": {
            "descriptor_rule": "sharpest top-seller over-index requires rank 1 by prevalence_ratio within same-size top-seller bundle rows"
        },
        "reasons": reasons,
    }


def _bundle_percent_sides(segment: str) -> list[str | None]:
    matches = list(_BUNDLE_PERCENT_RE.finditer(segment))
    if len(matches) >= 2:
        return ["left", "right", *([None] * (len(matches) - 2))]
    if len(matches) != 1:
        return []
    match = matches[0]
    window = segment[max(0, match.start() - 45) : match.end() + 45].casefold()
    if re.search(r"\b(?:rest|others?|remaining)\b", window):
        return ["right"]
    if re.search(r"\b(?:recent|top[-\s]?sellers?|winners?|winning)\b", window):
        return ["left"]
    return [None]


def _bundle_part_position(segment: str, part: str) -> int:
    folded_segment = _fold_text(segment)
    folded_part = _fold_text(part)
    direct_position = folded_segment.find(folded_part)
    if direct_position != -1:
        return direct_position

    segment_tokens = [
        (match.group(0), match.start())
        for match in re.finditer(r"[a-z0-9]+", folded_segment)
    ]
    part_tokens = _bundle_part_tokens(part)
    if not part_tokens:
        return -1
    width = len(part_tokens)
    for index in range(0, len(segment_tokens) - width + 1):
        if [
            token for token, _position in segment_tokens[index : index + width]
        ] == part_tokens:
            return segment_tokens[index][1]
    for token, position in segment_tokens:
        if token in part_tokens:
            return position
    return -1


def _bundle_order_score(segment: str, candidate: dict[str, Any]) -> int:
    parts = _bundle_parts_in_order(_candidate_primary_label(candidate))
    if len(parts) < 2:
        return 0
    positions: list[int] = []
    for part in parts:
        position = _bundle_part_position(segment, part)
        if position == -1:
            return 0
        positions.append(position)
    if all(left < right for left, right in zip(positions, positions[1:])):
        return len(parts)
    return 0


def _bundle_candidates_agree_on_observed_percent_sides(
    segment: str,
    candidates: list[dict[str, Any]],
) -> bool:
    percent_matches = _percent_mentions(segment)
    sides = _bundle_percent_sides(segment)
    if not percent_matches or len(percent_matches) != len(sides):
        return False
    for percent_mention, side in zip(percent_matches, sides):
        if side is None:
            return False
        candidate_values = [
            _candidate_percent_for_side(candidate, side) for candidate in candidates
        ]
        if any(value is None for value in candidate_values):
            return False
        if not all(
            _percent_matches(percent_mention, value) for value in candidate_values
        ):
            return False
    return True


def _select_tied_bundle_candidate(
    segment: str,
    candidates: list[dict[str, Any]],
    *,
    label: str | None = None,
) -> dict[str, Any] | None:
    ordered_matches = [
        (_bundle_order_score(segment, candidate), candidate) for candidate in candidates
    ]
    best_order_score = max(score for score, _candidate in ordered_matches)
    if best_order_score > 0:
        best_order_matches = [
            candidate
            for score, candidate in ordered_matches
            if score == best_order_score
        ]
        if len(best_order_matches) == 1:
            return best_order_matches[0]

    normalized_label = _normalize_text(label).casefold() if label else ""
    if normalized_label:
        exact_label_matches = [
            candidate
            for candidate in candidates
            if _normalize_text(_candidate_primary_label(candidate)).casefold()
            == normalized_label
        ]
        if len(exact_label_matches) == 1:
            return exact_label_matches[0]

    if _bundle_candidates_agree_on_observed_percent_sides(segment, candidates):
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate["file"],
                _canonical_text(_candidate_primary_label(candidate)),
                _normalize_text(_candidate_primary_label(candidate)),
            ),
        )[0]

    support_signatures = {
        (
            candidate["file"],
            _candidate_source_cohort_basis(candidate),
            _candidate_count_for_role(candidate, "top_seller"),
            _candidate_count_for_role(candidate, "other"),
            _candidate_count_for_role(candidate, "recent"),
            _candidate_count_for_role(candidate, "rest"),
            _candidate_brand_span_for_role(candidate, "top_seller"),
            _candidate_brand_span_for_role(candidate, "other"),
            _candidate_brand_span_for_role(candidate, "recent"),
            _candidate_brand_span_for_role(candidate, "rest"),
            round(_candidate_percent_for_role(candidate, "top_seller") or -1.0, 4),
            round(_candidate_percent_for_role(candidate, "other") or -1.0, 4),
            round(_candidate_percent_for_role(candidate, "recent") or -1.0, 4),
            round(_candidate_percent_for_role(candidate, "rest") or -1.0, 4),
        )
        for candidate in candidates
    }
    if len(support_signatures) == 1:
        return sorted(
            candidates,
            key=lambda candidate: (
                normalized_label
                != _normalize_text(_candidate_primary_label(candidate)).casefold(),
                candidate["file"],
                _canonical_text(_candidate_primary_label(candidate)),
                _normalize_text(_candidate_primary_label(candidate)),
            ),
        )[0]
    return None


def _best_mixed_labeled_percent_bundle_candidate(
    segment: str,
    label: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    mentions = _percent_mentions(segment)
    roles = {mention.role for mention in mentions if mention.role is not None}
    if len(mentions) < 2 or len(roles) < 2:
        return None
    if roles <= {"top_seller", "other"} or roles <= {"recent", "rest"}:
        return None
    for candidate in candidates:
        supported_roles = _candidate_supported_cohort_roles(candidate)
        coerced_roles = {
            _coerce_percent_role_for_supported_source(role, supported_roles)
            for role in roles
        }
        coerced_roles.discard(None)
        if coerced_roles <= {"top_seller", "other"} or coerced_roles <= {
            "recent",
            "rest",
        }:
            return None
    return {
        "status": "warning",
        "label": label,
        "segment": segment,
        "message": (
            "text cohort labels span incompatible source bases; no single "
            "deterministic source row supports " + "/".join(sorted(roles))
        ),
        "candidates": candidates,
        "candidate_evaluations": [
            {
                "file": candidate["file"],
                "kind": candidate.get("kind"),
                "source_cohort_basis": _candidate_source_cohort_basis(candidate),
                "package_values": _bundle_candidate_package_values(candidate),
            }
            for candidate in candidates
        ],
    }


def _best_containing_bundle_candidate(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
    *,
    context_segment: str | None,
) -> dict[str, Any] | None:
    if not _contains_numeric_evidence(
        segment
    ) or not _allows_containing_bundle_fallback(segment):
        return None
    candidates = _containing_bundle_candidates(label, frames)
    if not candidates:
        return None

    valid: list[tuple[tuple[int, int], dict[str, Any]]] = []
    candidate_evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        ok, score, reasons, metric_summary = _score_bundle_candidate(
            segment,
            candidate,
            context_segment=context_segment,
        )
        candidate_evaluations.append(
            {
                "file": candidate["file"],
                "kind": candidate.get("kind"),
                "match_scope": candidate.get("match_scope"),
                "score": score,
                "source_cohort_basis": _candidate_source_cohort_basis(candidate),
                "package_values": _bundle_candidate_package_values(candidate),
                "reasons": reasons,
                "matched_metrics": metric_summary.get("matched_metrics", []),
                "mismatched_metrics": metric_summary.get("mismatched_metrics", []),
            }
        )
        if ok:
            valid.append(((score, _candidate_bundle_part_count(candidate)), candidate))

    if not valid:
        return None

    valid.sort(key=lambda item: item[0], reverse=True)
    best_rank, best_candidate = valid[0]
    equally_best = [candidate for rank, candidate in valid if rank == best_rank]
    if len(equally_best) > 1:
        selected_candidate = _select_tied_bundle_candidate(
            segment,
            equally_best,
            label=label,
        )
        if selected_candidate is not None:
            return {
                "status": "pass",
                "label": label,
                "segment": segment,
                "candidate": selected_candidate,
                "candidate_evaluations": candidate_evaluations,
            }
        return {
            "status": "warning",
            "label": label,
            "segment": segment,
            "message": "multiple matching containing bundle rows",
            "candidates": equally_best,
            "candidate_evaluations": candidate_evaluations,
        }
    return {
        "status": "pass",
        "label": label,
        "segment": segment,
        "candidate": best_candidate,
        "candidate_evaluations": candidate_evaluations,
    }


def _candidate_population_profile(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    if "top_seller_base" in row or "count_top_seller" in row:
        return {
            "cohort_kind": "top_seller",
            "left_label": "top_seller",
            "right_label": "other",
            "left_count": _int_or_none(row.get("count_top_seller")),
            "right_count": _int_or_none(row.get("count_other")),
            "left_base": _int_or_none(row.get("top_seller_base")),
            "right_base": _int_or_none(row.get("other_base")),
        }
    return {
        "cohort_kind": "recent",
        "left_label": "recent",
        "right_label": "rest",
        "left_count": _int_or_none(row.get("count_recent")),
        "right_count": _int_or_none(row.get("count_rest")),
        "left_base": _int_or_none(
            row.get("recent_base", row.get("recent_family_base"))
        ),
        "right_base": _int_or_none(row.get("rest_base", row.get("rest_family_base"))),
    }


def _package_full_cohort_bases(
    frames: dict[str, pl.DataFrame],
) -> dict[str, int | None]:
    def _collect_int_values(
        file_name: str,
        *column_names: str,
    ) -> list[int]:
        df = frames[file_name]
        if df.is_empty():
            return []
        values: list[int] = []
        for column_name in column_names:
            if column_name not in df.columns:
                continue
            for value in df.get_column(column_name).drop_nulls().to_list():
                coerced = _int_or_none(value)
                if coerced is not None:
                    values.append(coerced)
        return values

    recent_values: list[int] = []
    rest_values: list[int] = []
    top_seller_values: list[int] = []
    other_values: list[int] = []

    for file_name in (
        "innovation_pairs.csv",
        "innovation_triples.csv",
        "mapped_attribute_comparison.csv",
        "resolved_core_comparison.csv",
        "filter_comparison.csv",
    ):
        recent_values.extend(
            _collect_int_values(file_name, "recent_base", "recent_family_base")
        )
        rest_values.extend(
            _collect_int_values(file_name, "rest_base", "rest_family_base")
        )
    for file_name in (
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
        "top_seller_mapped_attribute_comparison.csv",
    ):
        top_seller_values.extend(_collect_int_values(file_name, "top_seller_base"))
        other_values.extend(_collect_int_values(file_name, "other_base"))

    recent_df = frames["recent_products.csv"]
    if not recent_df.is_empty():
        recent_values.append(int(get_row_count(recent_df)))
    top_seller_df = frames["top_seller_products.csv"]
    if not top_seller_df.is_empty():
        top_seller_values.append(int(get_row_count(top_seller_df)))
    product_df = frames["product_filter_matrix.csv"]
    if not product_df.is_empty():
        if "listing_status" in product_df.columns:
            listing_status = product_df.get_column("listing_status").cast(pl.String)
            recent_values.append(int((listing_status == "recent").sum()))
            rest_values.append(int((listing_status == "rest").sum()))
        if "top_seller_status" in product_df.columns:
            top_seller_status = product_df.get_column("top_seller_status").cast(
                pl.String
            )
            top_seller_values.append(int((top_seller_status == "top_seller").sum()))
            other_values.append(int((top_seller_status == "other").sum()))

    return {
        "recent": max(recent_values) if recent_values else None,
        "rest": max(rest_values) if rest_values else None,
        "top_seller": max(top_seller_values) if top_seller_values else None,
        "other": max(other_values) if other_values else None,
    }


def _normalize_scope_cohort(value: str) -> str:
    normalized = _normalize_text(value).casefold()
    if normalized.startswith("top"):
        return "top_seller"
    if normalized.startswith("other") or normalized.startswith("remaining"):
        return "other"
    return normalized


def _qualified_cohort_scopes(segment: str) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for match in _QUALIFIED_COHORT_SCOPE_RE.finditer(segment):
        qualifier = _normalize_text(match.group("qualifier"))
        qualifier_tokens = {
            token
            for token in _canonical_tokens(qualifier)
            if token not in _COHORT_SCOPE_STOPWORDS
        }
        if not qualifier_tokens:
            continue
        scopes.append(
            {
                "cohort": _normalize_scope_cohort(match.group("cohort")),
                "qualifier": qualifier,
                "qualifier_tokens": qualifier_tokens,
                "object": _normalize_text(match.group("object")),
            }
        )
    return scopes


def _has_broad_population_wording(segment: str, *, cohort_kind: str) -> bool:
    lowered = segment.casefold()
    if cohort_kind == "top_seller":
        return any(
            marker in lowered
            for marker in (
                "top sellers",
                "top seller",
                "others",
                "other products",
                "remaining products",
            )
        )
    return any(
        marker in lowered
        for marker in (
            " in recent",
            " of recent",
            " vs rest",
            " in the rest",
            " of the rest",
            " compared to the rest",
            " compared to rest",
            " remaining products",
        )
    )


def _assess_bundle_population_scope(
    segment: str,
    candidate: dict[str, Any],
    *,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    observed_values = _extract_numeric_claim_evidence(segment)
    profile = _candidate_population_profile(candidate)
    package_values = _bundle_candidate_package_values(candidate)
    full_bases = _package_full_cohort_bases(frames)
    left_full = full_bases.get(profile["left_label"])
    right_full = full_bases.get(profile["right_label"])
    left_base = profile["left_base"]
    right_base = profile["right_base"]
    label_tokens = _canonical_tokens(_candidate_primary_label(candidate))
    matched_count_pairs = {
        (int(item["count"]), int(item["base"]))
        for item in observed_values.get("count_pairs", [])
        if isinstance(item, dict)
        and _int_or_none(item.get("count")) is not None
        and _int_or_none(item.get("base")) is not None
    }
    explicit_matching_denominator = (
        profile["left_count"],
        left_base,
    ) in matched_count_pairs or (
        profile["right_count"],
        right_base,
    ) in matched_count_pairs

    for scope in _qualified_cohort_scopes(segment):
        if scope["cohort"] not in {profile["left_label"], profile["right_label"]}:
            continue
        if not (scope["qualifier_tokens"] & label_tokens):
            continue
        if (
            left_full is not None
            and right_full is not None
            and left_base == left_full
            and right_base == right_full
        ):
            return {
                "status": "contradicted",
                "reasons": [
                    (
                        f"qualified denominator wording refers to `{scope['cohort']} "
                        f"{scope['qualifier']} {scope['object']}`, but the package row "
                        f"uses the full {profile['left_label']}/{profile['right_label']} cohorts"
                    )
                ],
                "observed_values": observed_values,
                "package_values": package_values,
            }

    subset_base = (
        left_full is not None and left_base is not None and left_base != left_full
    ) or (
        right_full is not None and right_base is not None and right_base != right_full
    )
    if subset_base and not explicit_matching_denominator:
        if _has_broad_population_wording(segment, cohort_kind=profile["cohort_kind"]):
            return {
                "status": "partially_backed",
                "reasons": [
                    (
                        f"percentages match the package row, but the package denominator "
                        f"is subset-based ({left_base}/{right_base}) rather than the full "
                        f"{profile['left_label']}/{profile['right_label']} cohorts "
                        f"({left_full}/{right_full})"
                    )
                ],
                "observed_values": observed_values,
                "package_values": package_values,
            }
    return None


def _best_bundle_candidate(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
    *,
    context_segment: str | None = None,
) -> dict[str, Any] | None:
    candidates = _bundle_candidates(label, frames)
    if not candidates:
        candidates = _computed_bundle_candidates(label, frames)
    if not candidates:
        return _best_containing_bundle_candidate(
            segment,
            label,
            frames,
            context_segment=context_segment,
        )

    valid: list[tuple[int, dict[str, Any]]] = []
    candidate_evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        ok, score, reasons, metric_summary = _score_bundle_candidate(
            segment,
            candidate,
            context_segment=context_segment,
        )
        candidate_evaluations.append(
            {
                "file": candidate["file"],
                "kind": candidate.get("kind"),
                "match_scope": candidate.get("match_scope"),
                "score": score,
                "source_cohort_basis": _candidate_source_cohort_basis(candidate),
                "matched_row_keys": _candidate_row_keys(candidate),
                "package_values": _bundle_candidate_package_values(candidate),
                "reasons": reasons,
                "matched_metrics": metric_summary.get("matched_metrics", []),
                "mismatched_metrics": metric_summary.get("mismatched_metrics", []),
            }
        )
        if ok:
            valid.append((score, candidate))

    if not valid:
        mixed_result = _best_mixed_labeled_percent_bundle_candidate(
            segment,
            label,
            candidates,
        )
        if mixed_result is not None:
            return mixed_result
        containing_result = _best_containing_bundle_candidate(
            segment,
            label,
            frames,
            context_segment=context_segment,
        )
        if containing_result is not None:
            return containing_result
        return {
            "status": "fail",
            "label": label,
            "segment": segment,
            "candidates": candidates,
            "candidate_evaluations": candidate_evaluations,
        }

    valid.sort(key=lambda item: item[0], reverse=True)
    best_score, best_candidate = valid[0]
    equally_best = [candidate for score, candidate in valid if score == best_score]
    if len(equally_best) > 1:
        selected_candidate = _select_tied_bundle_candidate(
            segment,
            equally_best,
            label=label,
        )
        if selected_candidate is not None:
            return {
                "status": "pass",
                "label": label,
                "segment": segment,
                "candidate": selected_candidate,
                "tied_candidates": equally_best,
            }
        return {
            "status": "warning",
            "label": label,
            "segment": segment,
            "message": "multiple matching candidate rows",
            "candidates": equally_best,
        }
    return {
        "status": "pass",
        "label": label,
        "segment": segment,
        "candidate": best_candidate,
    }


def _candidate_evaluation_reasons(
    evaluation: dict[str, Any],
) -> list[str]:
    return [
        _normalize_text(reason)
        for reason in (
            evaluation.get("reasons")
            if isinstance(evaluation.get("reasons"), list)
            else []
        )
        if _normalize_text(reason)
    ]


def _candidate_evaluation_has_contradiction_evidence(
    evaluation: dict[str, Any],
) -> bool:
    package_values = evaluation.get("package_values")
    matched_row_keys = evaluation.get("matched_row_keys")
    reasons = _candidate_evaluation_reasons(evaluation)
    if not isinstance(package_values, dict) or not package_values:
        return False
    if not isinstance(matched_row_keys, dict) or not matched_row_keys:
        return False
    if not reasons:
        return False
    non_contradiction_reasons = (
        "cohort label mismatch",
        "candidate is missing",
        "percent unavailable",
        "comparable percent values",
        "source row supports",
        "source row is missing",
    )
    if all(
        any(marker in reason.casefold() for marker in non_contradiction_reasons)
        for reason in reasons
    ):
        return False
    return True


def _candidate_evaluation_numeric_distance(
    evaluation: dict[str, Any],
    segment: str,
) -> float:
    package_values = evaluation.get("package_values")
    if not isinstance(package_values, dict):
        return float("inf")
    observed_values = _extract_numeric_claim_evidence(segment)
    observed_percents = observed_values.get("percents")
    if not isinstance(observed_percents, list) or not observed_percents:
        return float("inf")

    percent_pairs = [
        ("pct_top_seller", "pct_other"),
        ("pct_recent", "pct_rest"),
    ]
    distances: list[float] = []
    for left_key, right_key in percent_pairs:
        left = _float_or_none(package_values.get(left_key))
        right = _float_or_none(package_values.get(right_key))
        if len(observed_percents) >= 2 and left is not None and right is not None:
            distances.append(
                abs(float(observed_percents[0]) - left)
                + abs(float(observed_percents[1]) - right)
            )
        elif len(observed_percents) == 1:
            comparable = [value for value in (left, right) if value is not None]
            if comparable:
                distances.append(
                    min(
                        abs(float(observed_percents[0]) - value) for value in comparable
                    )
                )
    return min(distances) if distances else float("inf")


def _candidate_evaluation_has_partial_metric_support(
    evaluation: dict[str, Any],
) -> bool:
    matched_metrics = evaluation.get("matched_metrics")
    mismatched_metrics = evaluation.get("mismatched_metrics")
    if not isinstance(matched_metrics, list) or not isinstance(
        mismatched_metrics, list
    ):
        return False
    if not matched_metrics or not mismatched_metrics:
        return False
    ignored_mismatches = {"cohort_basis"}
    concrete_mismatches = [
        str(metric)
        for metric in mismatched_metrics
        if str(metric) not in ignored_mismatches
    ]
    if not concrete_mismatches:
        return False
    secondary_metrics = {"brand_count"}
    primary_matches = [
        str(metric)
        for metric in matched_metrics
        if str(metric) not in secondary_metrics
    ]
    if primary_matches:
        return True
    primary_mismatches = [
        metric for metric in concrete_mismatches if metric not in secondary_metrics
    ]
    return not primary_mismatches


def _candidate_evaluation_selection_key(
    evaluation: dict[str, Any],
) -> tuple[str, str, str]:
    return (
        _normalize_text(evaluation.get("file")),
        json.dumps(
            evaluation.get("matched_row_keys", {}),
            sort_keys=True,
            default=str,
        ),
        json.dumps(
            evaluation.get("package_values", {}),
            sort_keys=True,
            default=str,
        ),
    )


def _numeric_basis_diagnostic_fields_for_evaluation(
    segment: str,
    evaluation: dict[str, Any],
    candidates: Any,
) -> dict[str, Any]:
    if not isinstance(candidates, list):
        return {}
    selected_key = _candidate_evaluation_selection_key(evaluation)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_key = _candidate_evaluation_selection_key(
            {
                "file": candidate.get("file"),
                "matched_row_keys": _candidate_row_keys(candidate),
                "package_values": _bundle_candidate_package_values(candidate),
            }
        )
        if candidate_key != selected_key:
            continue
        return _numeric_basis_diagnostic_fields(segment, candidate)
    return {}


def _candidate_evaluations_with_selected_first(
    candidate_evaluations: Any,
    selected_evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_key = _candidate_evaluation_selection_key(selected_evaluation)
    selected_items: list[dict[str, Any]] = []
    other_items: list[dict[str, Any]] = []
    for evaluation in (
        candidate_evaluations if isinstance(candidate_evaluations, list) else []
    ):
        if not isinstance(evaluation, dict):
            continue
        item = dict(evaluation)
        if (
            not selected_items
            and _candidate_evaluation_selection_key(item) == selected_key
        ):
            item["selected_candidate"] = True
            selected_items.append(item)
        else:
            item["selected_candidate"] = False
            other_items.append(item)
    if not selected_items:
        item = dict(selected_evaluation)
        item["selected_candidate"] = True
        selected_items.append(item)
    return selected_items + other_items


def _best_failed_bundle_candidate_evaluation(
    bundle_result: dict[str, Any],
) -> dict[str, Any] | None:
    segment = _normalize_text(bundle_result.get("segment"))
    evaluations = [
        evaluation
        for evaluation in (
            bundle_result.get("candidate_evaluations")
            if isinstance(bundle_result.get("candidate_evaluations"), list)
            else []
        )
        if isinstance(evaluation, dict)
        and _candidate_evaluation_has_contradiction_evidence(evaluation)
    ]
    if not evaluations:
        return None
    enriched_evaluations = []
    for evaluation in evaluations:
        enriched = dict(evaluation)
        enriched["numeric_distance_from_claim"] = (
            _candidate_evaluation_numeric_distance(
                evaluation,
                segment,
            )
        )
        enriched_evaluations.append(enriched)

    def _numeric_distance_key(evaluation: dict[str, Any]) -> float:
        distance = _float_or_none(evaluation.get("numeric_distance_from_claim"))
        return distance if distance is not None else float("inf")

    enriched_evaluations.sort(
        key=lambda evaluation: (
            -(_int_or_none(evaluation.get("score")) or 0),
            _numeric_distance_key(evaluation),
            len(_candidate_evaluation_reasons(evaluation)),
        )
    )
    return enriched_evaluations[0]


def _failed_bundle_expected_candidates(
    bundle_result: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "file": candidate["file"],
            "matched_row_keys": _candidate_row_keys(candidate),
            "package_values": _bundle_candidate_package_values(candidate),
        }
        for candidate in (
            bundle_result.get("candidates")
            if isinstance(bundle_result.get("candidates"), list)
            else []
        )
        if isinstance(candidate, dict)
    ]


def _brand_alias_tokens(brand_name: Any) -> tuple[str, ...]:
    return tuple(
        token
        for token in _token_list(brand_name)
        if token not in _BRAND_ALIAS_NOISE_TOKENS
        and token not in _BRAND_ALIAS_TOKEN_BLOCKLIST
        and len(token) >= 3
    )


def _brand_alias_span_for_segment(
    segment: str,
    brand_name: Any,
) -> tuple[int, int] | None:
    alias_tokens = _brand_alias_tokens(brand_name)
    if not alias_tokens:
        return None
    escaped_tokens = [re.escape(token) for token in alias_tokens]
    pattern = re.compile(
        r"(?<![A-Za-z0-9])" + r"\W+".join(escaped_tokens) + r"(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    match = pattern.search(segment)
    return match.span() if match is not None else None


def _brand_row_for_segment(
    segment: str, brand_df: pl.DataFrame
) -> dict[str, Any] | None:
    if brand_df.is_empty():
        return None
    segment_tokens = _canonical_tokens(segment, ignored_tokens=_BRAND_NOISE_TOKENS)
    matches: list[tuple[int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        brand_tokens = _canonical_tokens(brand, ignored_tokens=_BRAND_NOISE_TOKENS)
        if brand_tokens and brand_tokens.issubset(segment_tokens):
            matches.append((len(brand_tokens), row))
    if len(matches) == 1:
        return matches[0][1]
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = matches[0]
        if len(matches) == 1 or matches[1][0] < best_score:
            return best_row

    alias_matches: list[tuple[int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        alias_tokens = _brand_alias_tokens(brand)
        if alias_tokens and _brand_alias_span_for_segment(segment, brand) is not None:
            alias_matches.append((len(alias_tokens), row))
    if len(alias_matches) == 1:
        return alias_matches[0][1]
    if alias_matches:
        alias_matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = alias_matches[0]
        if len(alias_matches) == 1 or alias_matches[1][0] < best_score:
            return best_row
    return None


def _brand_row_for_entity(
    brand_name: str | None,
    brand_df: pl.DataFrame,
) -> dict[str, Any] | None:
    target = _canonical_text(brand_name)
    if brand_df.is_empty() or not target:
        return None
    target_tokens = _canonical_tokens(brand_name, ignored_tokens=_BRAND_NOISE_TOKENS)
    matches: list[tuple[int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        candidate_brand = _normalize_text(row.get("brand"))
        candidate = _canonical_text(candidate_brand)
        if not candidate:
            continue
        if candidate == target:
            return row
        candidate_tokens = _canonical_tokens(
            candidate_brand, ignored_tokens=_BRAND_NOISE_TOKENS
        )
        if not target_tokens or not candidate_tokens:
            continue
        if target_tokens == candidate_tokens:
            matches.append((100, row))
            continue
        if target_tokens.issubset(candidate_tokens):
            score = (
                80 + len(target_tokens) - (len(candidate_tokens) - len(target_tokens))
            )
            matches.append((score, row))
            continue
        if candidate_tokens.issubset(target_tokens):
            score = (
                70
                + len(candidate_tokens)
                - (len(target_tokens) - len(candidate_tokens))
            )
            matches.append((score, row))
    if len(matches) == 1:
        return matches[0][1]
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        best_score, best_row = matches[0]
        if len(matches) == 1 or matches[1][0] < best_score:
            return best_row
    return None


def _brand_rows_mentioned_in_segment(
    segment: str,
    brand_df: pl.DataFrame,
) -> list[dict[str, Any]]:
    if brand_df.is_empty() or "brand" not in brand_df.columns:
        return []

    matches: list[tuple[int, int, dict[str, Any]]] = []
    for row in brand_df.to_dicts():
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(brand)}(?![A-Za-z0-9])",
            flags=re.IGNORECASE,
        )
        for match in pattern.finditer(segment):
            matches.append((match.start(), match.end(), row))
        if pattern.search(segment) is not None:
            continue
        alias_span = _brand_alias_span_for_segment(segment, brand)
        if alias_span is not None:
            matches.append((alias_span[0], alias_span[1], row))

    if not matches:
        return []

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    rows: list[dict[str, Any]] = []
    occupied_until = -1
    seen_brands: set[str] = set()
    for start, end, row in matches:
        if start < occupied_until:
            continue
        brand_key = _canonical_text(row.get("brand"))
        if brand_key in seen_brands:
            continue
        seen_brands.add(brand_key)
        occupied_until = end
        rows.append(row)
    return rows


def _looks_like_brand_share_claim(segment: str) -> bool:
    lowered = segment.casefold()
    return any(marker in lowered for marker in _BRAND_SHARE_HINTS)


def _validate_brand_overindex_segment(
    segment: str,
    brand_df: pl.DataFrame,
) -> dict[str, Any] | None:
    if not _BRAND_OVERINDEX_RE.search(segment):
        return None
    rows = _brand_rows_mentioned_in_segment(segment, brand_df)
    if not rows:
        return None

    brand_support: list[dict[str, Any]] = []
    reasons: list[str] = []
    for row in rows:
        brand = _normalize_text(row.get("brand"))
        over_index = _float_or_none(row.get("over_index_vs_catalog_share"))
        top_seller_share = _percent_from_fraction(row.get("top_seller_share_of_cohort"))
        catalog_share = _percent_from_fraction(row.get("catalog_share"))
        support = {
            "brand": brand,
            "over_index_vs_catalog_share": over_index,
            "top_seller_share_of_cohort_pct": top_seller_share,
            "catalog_share_pct": catalog_share,
            "top_seller_count": _int_or_none(row.get("top_seller_count")),
            "catalog_count": _int_or_none(row.get("catalog_count")),
        }
        brand_support.append(support)
        if over_index is None:
            reasons.append(f"{brand} over-index value unavailable in package")
        elif over_index <= 1.0:
            reasons.append(f"{brand} is not over-indexed versus catalog share")

    has_intensity_qualifier = bool(_BRAND_OVERINDEX_INTENSITY_RE.search(segment))
    status = "fail" if reasons else "partial" if has_intensity_qualifier else "pass"
    return {
        "status": status,
        "segment": segment,
        "brands": [_normalize_text(row.get("brand")) for row in rows],
        "file": "top_seller_brand_comparison.csv",
        "observed_values": {
            "mentioned_brands": [_normalize_text(row.get("brand")) for row in rows],
            "over_index_claim": True,
            "intensity_qualifier_present": has_intensity_qualifier,
        },
        "package_values": {"brand_support": brand_support},
        "matched_row_keys": {
            "brands": [_normalize_text(row.get("brand")) for row in rows]
        },
        "comparison_policy": (
            "over-index means over_index_vs_catalog_share > 1.0; qualitative "
            "intensity modifiers are reported but not treated as deterministic "
            "magnitude claims without numeric evidence"
        ),
        "reasons": reasons,
    }


def _looks_like_category_brand_concentration_claim(text: str) -> bool:
    lowered = text.casefold()
    if lowered.startswith("winning now:") or (
        "validation:" in lowered and ("pdp" in lowered or "review" in lowered)
    ):
        return False
    return bool(
        _CATEGORY_NO_SINGLE_OWNER_RE.search(text)
        or _CATEGORY_BRAND_CONCENTRATION_SURVIVAL_RE.search(text)
        or (
            "clear over-indexing exists" in lowered
            and "no single" in lowered
            and "category" in lowered
        )
    )


def _category_brand_concentration_threshold_policy() -> dict[str, Any]:
    return {
        "single_brand_share_threshold_pct": (
            _BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT
        ),
        "over_index_threshold": 1.0,
        "source_file": "top_seller_brand_comparison.csv",
        "scope": "whole top-seller cohort, not bundle-specific signal rows",
    }


def _category_brand_concentration_summary(
    brand_df: pl.DataFrame,
) -> dict[str, Any] | None:
    required_columns = {
        "brand",
        "top_seller_share_of_cohort",
        "over_index_vs_catalog_share",
    }
    columns, _schema = get_schema_and_column_names(brand_df)
    if brand_df.is_empty() or not required_columns <= set(columns):
        return None

    rows = brand_df.to_dicts()
    share_rows = [
        row
        for row in rows
        if _float_or_none(row.get("top_seller_share_of_cohort")) is not None
    ]
    if not share_rows:
        return None

    dominant_row = max(
        share_rows,
        key=lambda row: _float_or_none(row.get("top_seller_share_of_cohort")) or 0.0,
    )
    over_indexed_rows = [
        row
        for row in rows
        if (_float_or_none(row.get("over_index_vs_catalog_share")) or 0.0) > 1.0
        and (_int_or_none(row.get("top_seller_count")) or 0) > 0
    ]
    top_seller_count_values = [
        _int_or_none(row.get("top_seller_count")) for row in rows
    ]
    total_top_seller_count = sum(
        value for value in top_seller_count_values if value is not None
    )
    dominant_share = _percent_from_fraction(
        dominant_row.get("top_seller_share_of_cohort")
    )
    return {
        "dominant_brand": _normalize_text(dominant_row.get("brand")),
        "dominant_brand_share_pct": dominant_share,
        "dominant_brand_count": _int_or_none(dominant_row.get("top_seller_count")),
        "total_top_seller_brand_count": total_top_seller_count,
        "over_indexed_brand_count": len(over_indexed_rows),
        "top_over_indexed_brands": [
            {
                "brand": _normalize_text(row.get("brand")),
                "top_seller_share_of_cohort_pct": _percent_from_fraction(
                    row.get("top_seller_share_of_cohort")
                ),
                "over_index_vs_catalog_share": _float_or_none(
                    row.get("over_index_vs_catalog_share")
                ),
            }
            for row in sorted(
                over_indexed_rows,
                key=lambda row: _float_or_none(row.get("over_index_vs_catalog_share"))
                or 0.0,
                reverse=True,
            )[:5]
        ],
    }


def _validate_category_brand_concentration_segment(
    segment: str,
    brand_df: pl.DataFrame,
) -> dict[str, Any] | None:
    if not _looks_like_category_brand_concentration_claim(segment):
        return None

    summary = _category_brand_concentration_summary(brand_df)
    if summary is None:
        return {
            "status": "warning",
            "message": (
                "category brand concentration needs top_seller_brand_comparison rows"
            ),
            "threshold_policy": _category_brand_concentration_threshold_policy(),
        }

    lowered = segment.casefold()
    reasons: list[str] = []
    if "over-index" in lowered and summary.get("over_indexed_brand_count", 0) <= 0:
        reasons.append("no over-indexed top-seller brands found in package")

    dominant_share = _float_or_none(summary.get("dominant_brand_share_pct"))
    single_owner_threshold = _BUNDLE_BRAND_CONCENTRATION_SHARE_THRESHOLD_PCT
    if _CATEGORY_NO_SINGLE_OWNER_RE.search(
        segment
    ) or _CATEGORY_BRAND_CONCENTRATION_SURVIVAL_RE.search(segment):
        if dominant_share is None:
            reasons.append("dominant top-seller brand share unavailable")
        elif dominant_share >= single_owner_threshold:
            reasons.append(
                "dominant top-seller brand share meets single-brand ownership threshold"
            )

    if reasons:
        status = "fail"
    elif _CATEGORY_BRAND_CONCENTRATION_SURVIVAL_RE.search(segment):
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "source_file": "top_seller_brand_comparison.csv",
        "package_values": summary,
        "matched_row_keys": {
            "dominant_brand": summary.get("dominant_brand"),
            "scope": "top_seller_brand_comparison",
        },
        "threshold_policy": _category_brand_concentration_threshold_policy(),
        "comparison_policy": (
            "no-single-owner claims require dominant top-seller brand share below "
            "the single-brand threshold; survival/artifact language is partial "
            "because it does not name bundle-level signal rows"
        ),
        "reasons": reasons,
    }


def _brand_span_for_segment(segment: str, brand_name: Any) -> tuple[int, int] | None:
    brand = _normalize_text(brand_name)
    if not brand:
        return None
    match = re.search(re.escape(brand), segment, flags=re.IGNORECASE)
    if match is not None:
        return match.span()
    brand_tokens = _canonical_tokens(brand, ignored_tokens=_BRAND_NOISE_TOKENS)
    if not brand_tokens:
        return None
    token_matches = [
        match
        for match in re.finditer(r"\b[a-z0-9][a-z0-9.'&-]*\b", segment, re.IGNORECASE)
        if _canonical_tokens(match.group(0), ignored_tokens=_BRAND_NOISE_TOKENS)
        & brand_tokens
    ]
    if not token_matches:
        return None
    return token_matches[0].start(), token_matches[-1].end()


def _span_distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    if left[1] < right[0]:
        return right[0] - left[1]
    if right[1] < left[0]:
        return left[0] - right[1]
    return 0


def _brand_numeric_evidence_is_adjacent(segment: str, brand_name: Any) -> bool:
    brand_span = _brand_span_for_segment(segment, brand_name)
    if brand_span is None:
        return False
    numeric_spans = [
        match.span()
        for pattern in (_BUNDLE_PERCENT_RE, _MULTIPLIER_RE, _COUNT_RATIO_RE)
        for match in pattern.finditer(segment)
    ]
    numeric_spans.extend(
        match.span() for match in _COHORT_COUNT_MENTION_RE.finditer(segment)
    )
    return any(
        _span_distance(brand_span, numeric_span) <= _BRAND_NUMERIC_WINDOW_CHARS
        for numeric_span in numeric_spans
    )


def _brand_top_seller_base(row: dict[str, Any]) -> int | None:
    count = _int_or_none(row.get("top_seller_count"))
    share = _float_or_none(row.get("top_seller_share_of_cohort"))
    if count is None or share is None or share <= 0:
        return None
    return int(round(count / share))


def _brand_share_roster_segments(
    segment: str,
    brand_df: pl.DataFrame,
) -> list[tuple[str, str]]:
    if brand_df.is_empty() or "brand" not in brand_df.columns:
        return []
    if not re.search(r"\btop[-\s]?sellers?\b", segment, flags=re.IGNORECASE):
        return []

    entries: list[tuple[int, int, str]] = []
    for row in brand_df.to_dicts():
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(brand)}\s*:",
            flags=re.IGNORECASE,
        )
        entries.extend(
            (match.start(), match.end(), brand) for match in pattern.finditer(segment)
        )

    if len(entries) < 2:
        return []

    entries.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    non_overlapping: list[tuple[int, int, str]] = []
    occupied_until = -1
    for entry in entries:
        if entry[0] < occupied_until:
            continue
        non_overlapping.append(entry)
        occupied_until = entry[1]

    if len(non_overlapping) < 2:
        return []

    segments: list[tuple[str, str]] = []
    for index, (start, _end, brand) in enumerate(non_overlapping):
        stop = (
            non_overlapping[index + 1][0]
            if index + 1 < len(non_overlapping)
            else len(segment)
        )
        roster_segment = _normalize_text(segment[start:stop].strip(" ;,"))
        if _contains_numeric_evidence(roster_segment):
            segments.append((roster_segment, brand))
    return segments if len(segments) >= 2 else []


def _validate_brand_roster_segments(
    segment: str,
    brand_df: pl.DataFrame,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for roster_segment, brand in _brand_share_roster_segments(segment, brand_df):
        result = _validate_brand_segment(
            roster_segment,
            brand_df,
            brand_name=brand,
            require_numeric_evidence=True,
        )
        if result is not None:
            results.append(result)
    return results


def _validate_brand_segment(
    segment: str,
    brand_df: pl.DataFrame,
    *,
    brand_name: str | None = None,
    require_numeric_evidence: bool = False,
) -> dict[str, Any] | None:
    row = _brand_row_for_entity(brand_name, brand_df) or _brand_row_for_segment(
        segment, brand_df
    )
    if row is None:
        return None

    percents = _percent_mentions(segment)
    ratios = [float(match) for match in _MULTIPLIER_RE.findall(segment)]
    count_pairs = [
        (int(left), int(right)) for left, right in _COUNT_RATIO_RE.findall(segment)
    ]
    expected_pcts = [
        _percent_from_fraction(row.get("top_seller_share_of_cohort")),
        _percent_from_fraction(row.get("catalog_share")),
    ]
    expected_ratio = _float_or_none(row.get("over_index_vs_catalog_share"))
    reasons: list[str] = []
    has_numeric_evidence = bool(percents or ratios or count_pairs)
    top_seller_context = bool(
        re.search(r"\btop[-\s]?sellers?\b", segment, flags=re.IGNORECASE)
        or any(mention.role == "top_seller" for mention in percents)
    )
    catalog_context = bool(
        re.search(r"\bcatalog(?:ue)?\b", segment, flags=re.IGNORECASE)
        or any("catalog" in _normalize_text(mention.role) for mention in percents)
    )
    if (
        require_numeric_evidence
        and has_numeric_evidence
        and not _brand_numeric_evidence_is_adjacent(segment, row.get("brand"))
    ):
        return {
            "status": "warning",
            "segment": segment,
            "brand": row["brand"],
            "file": "top_seller_brand_comparison.csv",
            "message": "numeric evidence is not local to the matched brand",
        }

    if len(percents) == 1:
        if top_seller_context and not catalog_context:
            comparable_pcts = [expected_pcts[0]]
        elif catalog_context and not top_seller_context:
            comparable_pcts = [expected_pcts[1]]
        else:
            comparable_pcts = expected_pcts
        if not any(
            _percent_matches(percents[0], expected_pct)
            for expected_pct in comparable_pcts
            if expected_pct is not None
        ):
            reasons.append(
                "brand single percent mismatch: expected "
                + " or ".join(
                    _format_optional_percent(expected_pct)
                    for expected_pct in comparable_pcts
                )
            )

    if len(percents) >= 2:
        if not (
            _percent_matches(percents[0], expected_pcts[0])
            and _percent_matches(percents[1], expected_pcts[1])
        ):
            reasons.append(
                f"brand percent mismatch: expected {expected_pcts[0]:.1f}% and {expected_pcts[1]:.1f}%"
            )
    if ratios and expected_ratio is not None:
        if not any(
            _approx_equal(value, expected_ratio, _MULTIPLIER_TOLERANCE)
            for value in ratios
        ):
            reasons.append(f"brand ratio mismatch: expected {expected_ratio:.2f}x")
    if count_pairs and top_seller_context:
        expected_count = _int_or_none(row.get("top_seller_count"))
        expected_base = _brand_top_seller_base(row)
        if expected_count is None:
            reasons.append("brand top-seller count unavailable in package")
        elif expected_base is None:
            if not any(count == expected_count for count, _base in count_pairs):
                reasons.append(
                    f"brand top-seller count mismatch: expected {expected_count}"
                )
        elif (expected_count, expected_base) not in count_pairs:
            reasons.append(
                f"brand top-seller count/base mismatch: expected {expected_count}/{expected_base}"
            )

    if require_numeric_evidence and not has_numeric_evidence:
        return {
            "status": "warning",
            "segment": segment,
            "brand": row["brand"],
            "file": "top_seller_brand_comparison.csv",
            "message": "brand claim missing numeric evidence to validate",
        }

    return {
        "status": "fail" if reasons else "pass",
        "segment": segment,
        "brand": row["brand"],
        "file": "top_seller_brand_comparison.csv",
        "expected": {
            "top_seller_share_of_cohort_pct": expected_pcts[0],
            "catalog_share_pct": expected_pcts[1],
            "top_seller_count": _int_or_none(row.get("top_seller_count")),
            "top_seller_base": _brand_top_seller_base(row),
            "over_index_vs_catalog_share": expected_ratio,
            "calculation_helper_id": row.get("calculation_helper_id"),
            "calculation_source": row.get("calculation_source"),
        },
        "reasons": reasons,
        "observed_values": _extract_numeric_claim_evidence(segment),
    }


def _find_product_row(
    product_name: str,
    frames: dict[str, pl.DataFrame],
    *,
    file_order: tuple[str, ...] = ("recent_products.csv", "top_seller_products.csv"),
    preferred_rank: int | None = None,
) -> dict[str, Any] | None:
    target = _canonical_text(product_name)
    target_tokens = _product_match_tokens(product_name)
    best_row: dict[str, Any] | None = None
    best_candidate_canonical = ""
    best_score = -1
    tied = False
    for file_name in file_order:
        df = frames[file_name]
        if df.is_empty() or "product_name" not in df.columns:
            continue
        for row in df.to_dicts():
            candidate_name = _normalize_text(row.get("product_name"))
            candidate_canonical = _canonical_text(candidate_name)
            if not candidate_canonical:
                continue
            if target == candidate_canonical:
                return {"file": file_name, "row": row}
            if target in candidate_canonical or candidate_canonical in target:
                score = 1000 + min(len(target), len(candidate_canonical))
                if (
                    preferred_rank is not None
                    and _int_or_none(row.get("pareto_rank")) == preferred_rank
                ):
                    score += 10000
                if score > best_score:
                    best_score = score
                    best_row = {"file": file_name, "row": row}
                    best_candidate_canonical = candidate_canonical
                    tied = False
                elif (
                    score == best_score
                    and best_row is not None
                    and candidate_canonical != best_candidate_canonical
                ):
                    tied = True
                continue
            candidate_tokens = _product_match_tokens(candidate_name)
            if not target_tokens or not candidate_tokens:
                continue
            if target_tokens.issubset(candidate_tokens):
                score = (
                    50
                    + len(target_tokens)
                    - (len(candidate_tokens) - len(target_tokens))
                )
            else:
                shared_tokens = target_tokens & candidate_tokens
                if len(shared_tokens) < 2:
                    continue
                coverage = len(shared_tokens) / len(target_tokens)
                if coverage < 0.75:
                    continue
                score = 30 + len(shared_tokens)
            if (
                preferred_rank is not None
                and _int_or_none(row.get("pareto_rank")) == preferred_rank
            ):
                score += 10000
            if score > best_score:
                best_score = score
                best_row = {"file": file_name, "row": row}
                best_candidate_canonical = candidate_canonical
                tied = False
            elif (
                score == best_score
                and best_row is not None
                and candidate_canonical != best_candidate_canonical
            ):
                tied = True
    if tied:
        return None
    return best_row


def _extract_product_rank_expectations(segment: str) -> tuple[int | None, str | None]:
    exact_match = _PRODUCT_RANK_RE.search(segment)
    if exact_match is not None:
        return int(exact_match.group("rank")), exact_match.group("bucket").upper()
    rank_match = _PRODUCT_RANK_NUMBER_RE.search(segment)
    bucket_match = _PRODUCT_BUCKET_RE.search(segment)
    expected_rank = int(rank_match.group(1)) if rank_match is not None else None
    expected_bucket = (
        bucket_match.group(1).upper() if bucket_match is not None else None
    )
    return expected_rank, expected_bucket


def _normalize_product_name_for_matching(product_name: str) -> str:
    normalized = _normalize_text(product_name)
    normalized = _normalize_text(
        _TRAILING_PRODUCT_RANK_ANNOTATION_RE.sub("", normalized)
    )
    normalized = re.sub(
        r"^(?:exemplified\s+by|represented\s+by|embodied\s+by|led\s+by|"
        r"including|such\s+as)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return _normalize_text(
        re.sub(r"^(?:and|or)\s+", "", normalized, flags=re.IGNORECASE)
    )


def _extract_product_rank_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in _PRODUCT_RANK_ITEM_RE.finditer(text):
        product_name = _normalize_product_name_for_matching(match.group("name"))
        if not product_name:
            continue
        entries.append(
            {
                "segment": _normalize_text(match.group(0)),
                "product_name": product_name,
                "expected_rank": int(match.group("rank")),
                "expected_bucket": (
                    match.group("bucket").upper() if match.group("bucket") else None
                ),
            }
        )
    for match in _NUMBER_ONE_TOP_SELLING_PRODUCT_RE.finditer(text):
        product_name = _normalize_product_name_for_matching(match.group("name"))
        if not product_name:
            continue
        entries.append(
            {
                "segment": _normalize_text(match.group(0)),
                "product_name": product_name,
                "expected_rank": 1,
                "expected_bucket": None,
            }
        )
    return entries


def _row_text_blob(row: dict[str, Any]) -> str:
    return _normalize_text(
        " ".join(str(value) for value in row.values() if isinstance(value, str))
    )


def _ranked_bundle_label_tokens(label: str) -> set[str]:
    tokens = _canonical_tokens(
        label,
        ignored_tokens={
            "a",
            "an",
            "and",
            "format",
            "formats",
            "in",
            "of",
            "product",
            "products",
            "the",
            "with",
        },
    )
    return {_PRODUCT_TOKEN_ALIASES.get(token, token) for token in tokens if token}


def _top_seller_row_supports_bundle_label(
    row: dict[str, Any],
    label_tokens: set[str],
) -> bool:
    row_tokens = _canonical_tokens(
        _row_text_blob(row),
        ignored_tokens=_PRODUCT_MATCH_NOISE_TOKENS,
    )
    return bool(label_tokens) and label_tokens.issubset(row_tokens)


def _validate_ranked_bundle_product_evidence_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    match = _BUNDLE_RANKED_PRODUCTS_RE.search(segment)
    if match is None:
        return None
    bundle_label = _normalize_text(match.group("label"))
    expected_ranks = [
        int(rank) for rank in re.findall(r"#\s*(\d+)", match.group("rank_text")) if rank
    ]
    label_tokens = _ranked_bundle_label_tokens(bundle_label)
    if not expected_ranks or not label_tokens:
        return {
            "status": "warning",
            "bundle_label": bundle_label,
            "expected_ranks": expected_ranks,
            "message": "ranked bundle evidence missing rank or bundle label",
        }

    df = frames["top_seller_products.csv"]
    if df.is_empty() or "pareto_rank" not in df.columns:
        return {
            "status": "warning",
            "bundle_label": bundle_label,
            "expected_ranks": expected_ranks,
            "message": "top-seller product rows unavailable",
        }

    support_rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    rank_rows_by_rank: dict[int, list[dict[str, Any]]] = {}
    for row in df.to_dicts():
        rank = _int_or_none(row.get("pareto_rank"))
        if rank in expected_ranks:
            rank_rows_by_rank.setdefault(rank, []).append(row)

    for expected_rank in expected_ranks:
        rank_rows = rank_rows_by_rank.get(expected_rank, [])
        if not rank_rows:
            reasons.append(f"rank #{expected_rank} not found in top-seller products")
            continue
        matching_rows = [
            row
            for row in rank_rows
            if _top_seller_row_supports_bundle_label(row, label_tokens)
        ]
        if not matching_rows:
            observed_names = [
                _normalize_text(row.get("product_name")) for row in rank_rows[:3]
            ]
            reasons.append(
                f"rank #{expected_rank} product does not match bundle label "
                f"{bundle_label!r}"
            )
            support_rows.append(
                {
                    "rank": expected_rank,
                    "matched": False,
                    "observed_product_names": observed_names,
                }
            )
            continue
        for row in matching_rows[:1]:
            support_rows.append(
                {
                    "rank": expected_rank,
                    "matched": True,
                    "product_name": _normalize_text(row.get("product_name")),
                    "food_texture": _normalize_text(
                        row.get("food texture") or row.get("food_texture")
                    ),
                    "packaging_type": _normalize_text(row.get("packaging type")),
                    "pareto_bucket": _normalize_text(row.get("pareto_bucket")),
                }
            )

    return {
        "status": "fail" if reasons else "pass",
        "bundle_label": bundle_label,
        "expected_ranks": expected_ranks,
        "label_tokens": sorted(label_tokens),
        "support_rows": support_rows,
        "source_file": "top_seller_products.csv",
        "reasons": reasons,
    }


def _validate_product_rank_entry(
    *,
    segment: str,
    product_name: str,
    expected_rank: int | None,
    expected_bucket: str | None,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    if expected_rank is None:
        return {
            "status": "warning",
            "segment": segment,
            "product_name": product_name,
            "message": "product-rank claim missing rank",
        }
    hit = _find_product_row(
        product_name,
        frames,
        file_order=("top_seller_products.csv", "recent_products.csv"),
        preferred_rank=expected_rank,
    )
    if hit is None:
        return {
            "status": "warning",
            "segment": segment,
            "product_name": product_name,
            "message": "product not matched in package",
        }
    row = hit["row"]
    actual_rank = _int_or_none(row.get("pareto_rank"))
    actual_bucket = _normalize_text(row.get("pareto_bucket")).upper()
    reasons: list[str] = []
    if actual_rank != expected_rank:
        reasons.append(f"rank mismatch: expected #{actual_rank}")
    if expected_bucket is not None and actual_bucket != expected_bucket:
        reasons.append(f"bucket mismatch: expected {actual_bucket}")
    return {
        "status": "fail" if reasons else "pass",
        "segment": segment,
        "product_name": row.get("product_name"),
        "file": hit["file"],
        "observed_rank": expected_rank,
        "observed_bucket": expected_bucket,
        "package_values": {
            "product_name": row.get("product_name"),
            "pareto_rank": actual_rank,
            "pareto_bucket": actual_bucket,
        },
        "reasons": reasons,
    }


def _validate_product_rank_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
    *,
    product_name: str | None = None,
) -> list[dict[str, Any]]:
    if product_name:
        extracted_entries = _extract_product_rank_entries(product_name)
        if len(extracted_entries) >= 2:
            return [
                _validate_product_rank_entry(
                    segment=entry["segment"],
                    product_name=entry["product_name"],
                    expected_rank=entry["expected_rank"],
                    expected_bucket=entry["expected_bucket"],
                    frames=frames,
                )
                for entry in extracted_entries
            ]
        expected_rank, expected_bucket = _extract_product_rank_expectations(segment)
        return [
            _validate_product_rank_entry(
                segment=segment,
                product_name=_normalize_product_name_for_matching(product_name),
                expected_rank=expected_rank,
                expected_bucket=expected_bucket,
                frames=frames,
            )
        ]
    return [
        _validate_product_rank_entry(
            segment=entry["segment"],
            product_name=entry["product_name"],
            expected_rank=entry["expected_rank"],
            expected_bucket=entry["expected_bucket"],
            frames=frames,
        )
        for entry in _extract_product_rank_entries(segment)
    ]


def _best_product_name_from_text(
    text: str,
    product_names: tuple[str, ...],
) -> str | None:
    text_canonical = _canonical_text(text)
    text_tokens = _product_match_tokens(text)
    if not text_canonical or not text_tokens:
        return None

    best_name: str | None = None
    best_score = -1
    tied = False
    for product_name in product_names:
        candidate = _normalize_text(product_name)
        if not candidate:
            continue
        candidate_canonical = _canonical_text(candidate)
        candidate_tokens = _product_match_tokens(candidate)
        if not candidate_tokens:
            continue
        if candidate_canonical and candidate_canonical in text_canonical:
            score = 1000 + len(candidate_canonical)
        else:
            shared_tokens = candidate_tokens & text_tokens
            if len(shared_tokens) < 2:
                continue
            coverage = len(shared_tokens) / len(candidate_tokens)
            if coverage < 0.75:
                continue
            score = (
                300
                + len(shared_tokens) * 10
                - (len(candidate_tokens) - len(shared_tokens))
            )
        if score > best_score:
            best_score = score
            best_name = candidate
            tied = False
        elif score == best_score and best_name is not None and candidate != best_name:
            tied = True
    if tied:
        return None
    return best_name


def _leading_product_phrase(text: str) -> str:
    leading = re.split(
        r"\(|\.|\bdirectly\b|\brepresents\b|\bvalidation of\b",
        _normalize_text(text),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    if ":" in leading:
        leading = leading.split(":", 1)[1]
    return _normalize_text(leading)


def _best_product_name_from_segment(
    segment: str,
    package: LaunchPackageData,
) -> str | None:
    leading_product = _leading_product_phrase(segment)
    if leading_product:
        hit = _find_product_row(leading_product, package.frames)
        if hit is not None:
            return _normalize_text(hit["row"].get("product_name"))
    return _best_product_name_from_text(segment, package.product_names)


def _matching_product_rows(
    product_name: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for file_name in (
        "product_filter_matrix.csv",
        "recent_product_pdp_extracts.csv",
        "recent_products.csv",
        "top_seller_products.csv",
    ):
        df = frames[file_name]
        if df.is_empty() or "product_name" not in df.columns:
            continue
        best_row: dict[str, Any] | None = None
        best_score = -1
        tied = False
        for row in df.to_dicts():
            candidate_name = _normalize_text(row.get("product_name"))
            if not candidate_name:
                continue
            score = 0
            candidate_canonical = _canonical_text(candidate_name)
            target_canonical = _canonical_text(product_name)
            if target_canonical and candidate_canonical == target_canonical:
                score = 1000 + len(candidate_canonical)
            else:
                candidate_tokens = _product_match_tokens(candidate_name)
                target_tokens = _product_match_tokens(product_name)
                shared_tokens = candidate_tokens & target_tokens
                if len(shared_tokens) < 2:
                    continue
                coverage = (
                    len(shared_tokens) / len(target_tokens) if target_tokens else 0
                )
                if coverage < 0.75:
                    continue
                score = (
                    300
                    + len(shared_tokens) * 10
                    - (len(candidate_tokens) - len(shared_tokens))
                )
            if score > best_score:
                best_score = score
                best_row = row
                tied = False
            elif score == best_score and best_row is not None:
                if _canonical_text(best_row.get("product_name")) != candidate_canonical:
                    tied = True
        if best_row is not None and not tied:
            matches.append({"file": file_name, "row": best_row})
    return matches


def _build_product_context(
    product_name: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    primary_hit = _find_product_row(product_name, frames)
    if primary_hit is None:
        return None

    matched_rows = _matching_product_rows(
        _normalize_text(primary_hit["row"].get("product_name")),
        frames,
    )
    if not matched_rows:
        matched_rows = [primary_hit]

    primary_row = primary_hit["row"]
    cohort_membership = _normalize_text(primary_row.get("top_seller_status"))
    if not cohort_membership:
        cohort_membership = (
            "recent" if primary_hit["file"] == "recent_products.csv" else "top_seller"
        )

    return {
        "normalized_product_name": _normalize_text(primary_row.get("product_name")),
        "product_id": _normalize_text(primary_row.get("parent_product_id")),
        "primary_file": primary_hit["file"],
        "primary_row": primary_row,
        "rows": matched_rows,
        "rank_value": _int_or_none(primary_row.get("pareto_rank")),
        "price_tier": _normalize_text(primary_row.get("price_band")),
        "cohort_membership": cohort_membership,
        "source_row_ids": [
            {
                "source_file": match["file"],
                "product_name": _normalize_text(match["row"].get("product_name")),
                "parent_product_id": _normalize_text(
                    match["row"].get("parent_product_id")
                ),
                "listing_identity": _normalize_text(
                    match["row"].get("listing_identity")
                ),
            }
            for match in matched_rows
        ],
    }


def _product_context_blob(product_context: dict[str, Any]) -> str:
    parts: list[str] = []
    for match in product_context.get("rows", []):
        row = match["row"]
        for column in (
            "benefits",
            "benefits/claims",
            "form",
            "form_children",
            "coverage",
            "wear claims",
            "packaging features",
            "resolved_finish",
            "resolved_coverage",
            "resolved_color",
            "resolved_form",
            # Legacy generated packages may still carry these names.
            "format",
            "format_children",
            "packaging type",
            "resolved_format",
            "summary",
            "description_excerpt",
        ):
            text = _normalize_text(row.get(column))
            if text:
                parts.append(text)
    return _fold_text(" ".join(parts))


def _product_context_color_tokens(product_context: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for match in product_context.get("rows", []):
        color_value = _normalize_text(match["row"].get("resolved_color"))
        if not color_value:
            continue
        for part in color_value.split("|"):
            token = _fold_text(part.strip())
            if token:
                tokens.add(token)
    return tokens


def _product_attribute_match(
    product_context: dict[str, Any],
    attribute_id: str,
) -> dict[str, Any]:
    blob = _product_context_blob(product_context)
    color_tokens = _product_context_color_tokens(product_context)
    price_tier = _normalize_text(product_context.get("price_tier"))

    matched = False
    evidence: dict[str, Any] = {}
    if attribute_id == "mainstream_shade_coverage":
        matched_values = sorted(color_tokens & {"beige", "pink", "red", "brown"})
        matched = len(matched_values) == 4
        evidence = {"matched_values": matched_values}
    elif attribute_id == "red_pink_wine_spectrum":
        matched_values = sorted(color_tokens & {"red", "pink", "wine"})
        matched = len(matched_values) == 3
        evidence = {"matched_values": matched_values}
    elif attribute_id == "full_coverage":
        matched = "full coverage" in blob
    elif attribute_id == "buildable_coverage":
        matched = (
            "buildable coverage" in blob
            or "buildable payoff" in blob
            or "buildable" in blob
        )
    elif attribute_id == "long_wear":
        matched = any(
            token in blob
            for token in (
                "long-wear",
                "long wear",
                "12 hour",
                "16 hour",
                "lasting",
                "lasts for",
            )
        )
    elif attribute_id == "matte":
        matched = "matte" in blob
    elif attribute_id == "high_shine":
        matched = "high-shine" in blob or "high shine" in blob
    elif attribute_id == "hydrating_language":
        matched = any(token in blob for token in ("hydrat", "moistur", "nourish"))
    elif attribute_id in {"stick_form", "stick_format"}:
        matched = "stick" in blob or "bullet lipstick" in blob
    elif attribute_id == "soft_focus_blur":
        matched = any(token in blob for token in ("soft-focus", "soft focus", "blur"))
    elif attribute_id == "tint_like":
        matched = any(token in blob for token in ("tint", "stain"))
    elif attribute_id == "multi_use_flexibility":
        matched = any(
            token in blob
            for token in (
                "multi-use",
                "multi use",
                "lip and cheek",
                "lip & cheek",
                "on cheeks",
                "even on cheeks",
            )
        )
    elif attribute_id == "multi_texture_compact":
        texture_tokens = {
            token
            for token in ("balm", "cream", "powder", "stick", "velvet")
            if token in blob
        }
        matched = len(texture_tokens) >= 2 and any(
            token in blob
            for token in (
                "compact",
                "duo",
                "palette",
                "pan",
                "three textures",
                "trio",
            )
        )
        evidence = {"matched_values": sorted(texture_tokens)}
    elif attribute_id == "cream_powder_duo":
        matched = (
            "cream" in blob
            and "powder" in blob
            and any(token in blob for token in ("compact", "duo", "pan", "two"))
        )
    elif attribute_id == "smooth_glide":
        matched = any(
            token in blob
            for token in (
                "blend",
                "blendable",
                "blends",
                "creamy",
                "glide",
                "glides",
                "smooth",
                "streak free",
                "streak-free",
                "without streaking",
            )
        )
    elif attribute_id == "creamy_texture":
        matched = "cream" in blob or "creamy" in blob
    elif attribute_id == "streak_free":
        matched = any(
            token in blob for token in ("streak free", "streak-free", "without streak")
        )
    elif attribute_id == "luminous_glow":
        matched = any(token in blob for token in ("glow", "luminous", "shimmer"))
    elif attribute_id == "natural_finish":
        matched = "natural" in blob
    elif attribute_id == "pressed_powder":
        matched = "pressed powder" in blob or "powder" in blob
    elif attribute_id == "multi_attribute_profile":
        profile_tokens = {
            token
            for token in (
                "buildable",
                "cream",
                "full",
                "light",
                "luminous",
                "matte",
                "medium",
                "natural",
                "powder",
            )
            if token in blob
        }
        matched = len(profile_tokens) >= 3
        evidence = {"matched_values": sorted(profile_tokens)}
    elif attribute_id == "premium_tier":
        matched = price_tier == "premium"
        evidence = {"matched_value": price_tier}
    elif attribute_id == "value_tier":
        matched = price_tier == "value"
        evidence = {"matched_value": price_tier}

    return {
        "attribute_id": attribute_id,
        "matched": matched,
        "evidence": evidence,
    }


def _product_exemplar_requirements(segment: str) -> dict[str, Any] | None:
    lowered = segment.casefold()
    if "strongest data bundle" in lowered or "core performance winner" in lowered:
        return {
            "rule_id": "product_exemplar_core_bundle_v1",
            "required_attributes": [
                "mainstream_shade_coverage",
                "full_coverage",
                "long_wear",
                "matte",
            ],
        }
    if "premium expression of this emerging lane" in lowered:
        return {
            "rule_id": "product_exemplar_premium_lane_v1",
            "required_attributes": [
                "premium_tier",
                "high_shine",
                "hydrating_language",
                "stick_form",
                "red_pink_wine_spectrum",
            ],
        }
    if any(
        marker in lowered
        for marker in (
            "buildable, blurred, tint-like long-wear system",
            "buildable, blurred, tint like long wear system",
            "buildable, blurred, tint-like",
        )
    ):
        return {
            "rule_id": "product_exemplar_buildable_blur_v1",
            "required_attributes": [
                "buildable_coverage",
                "soft_focus_blur",
                "tint_like",
                "long_wear",
            ],
        }
    if (
        "full-coverage base requirement" in lowered
        or "full coverage base requirement" in lowered
    ):
        return {
            "rule_id": "product_exemplar_core_bundle_v1",
            "required_attributes": ["full_coverage", "long_wear"],
        }
    return None


def _looks_like_product_exemplar_claim(
    text: str,
    package: LaunchPackageData,
) -> bool:
    normalized = _normalize_text(text)
    lowered = text.casefold()
    if (
        re.match(
            r"^exhibit\s+[a-z0-9]+\s*:\s*[^.]+$",
            normalized,
            flags=re.IGNORECASE,
        )
        and not _NON_CLAIM_PREDICATE_RE.search(normalized)
        and "validation" not in lowered
    ):
        return False
    if not any(
        marker in lowered
        for marker in ("embodies", "represents", "validation of", "exhibit ")
    ):
        return False
    return _best_product_name_from_segment(text, package) is not None


def _validate_product_exemplar_segment(
    segment: str,
    package: LaunchPackageData,
) -> dict[str, Any] | None:
    if not _looks_like_product_exemplar_claim(segment, package):
        return None

    matched_product_name = _best_product_name_from_segment(segment, package)
    if matched_product_name is None:
        return {
            "status": "warning",
            "message": "product exemplar did not resolve to a package product",
        }

    product_context = _build_product_context(matched_product_name, package.frames)
    if product_context is None:
        return {
            "status": "warning",
            "message": "product exemplar did not match a deterministic product row",
            "normalized_product_name": matched_product_name,
        }

    requirements = _product_exemplar_requirements(segment)
    if requirements is None:
        return {
            "status": "warning",
            "message": "product exemplar wording is missing a deterministic rule",
            "normalized_product_name": product_context["normalized_product_name"],
        }

    reasons: list[str] = []
    matched_attribute_flags: list[str] = []
    attribute_support: list[dict[str, Any]] = []
    for attribute_id in requirements["required_attributes"]:
        match = _product_attribute_match(product_context, attribute_id)
        attribute_support.append(match)
        if match["matched"]:
            matched_attribute_flags.append(attribute_id)
        else:
            reasons.append(
                f"product exemplar missing required attribute support: {attribute_id}"
            )

    expected_rank = None
    if "rank" in segment.casefold():
        rank_match = _PRODUCT_RANK_NUMBER_RE.search(segment)
        expected_rank = int(rank_match.group(1)) if rank_match is not None else None
        if expected_rank is None:
            reasons.append(
                "product exemplar names a rank but no numeric rank was parsed"
            )
        elif product_context.get("rank_value") != expected_rank:
            reasons.append(
                f"product rank mismatch: expected #{expected_rank}, observed #{product_context.get('rank_value')}"
            )
    if (
        "top seller" in segment.casefold()
        and product_context.get("cohort_membership") != "top_seller"
    ):
        reasons.append("product exemplar is not in the top-seller cohort")

    return {
        "status": "pass" if not reasons else "fail",
        "normalized_product_name": product_context["normalized_product_name"],
        "product_id": product_context.get("product_id"),
        "rank_value": product_context.get("rank_value"),
        "cohort_membership": product_context.get("cohort_membership"),
        "price_tier": product_context.get("price_tier"),
        "matched_attribute_flags": matched_attribute_flags,
        "source_row_ids": product_context.get("source_row_ids", []),
        "attribute_support": attribute_support,
        "aggregation_rule_id": requirements["rule_id"],
        "reasons": reasons,
    }


def _looks_like_product_attribute_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "attributes match",
            "compact confirms",
            "confirms the convergence",
            "it combines",
            "it sits squarely at the intersection",
            "explicitly promises",
            "pdp confirms",
            "pdp propositions",
            "primary bridge product",
            "two-pan compact",
            "two pan compact",
        )
    )


def _product_attribute_requirements(segment: str) -> list[str]:
    lowered = segment.casefold()
    required: list[str] = []
    if "mainstream shade coverage" in lowered:
        required.append("mainstream_shade_coverage")
    if "full coverage" in lowered:
        required.append("full_coverage")
    if "buildable payoff" in lowered or "buildable" in lowered:
        required.append("buildable_coverage")
    if "long-wear" in lowered or "long wear" in lowered:
        required.append("long_wear")
    if "matte" in lowered:
        required.append("matte")
    if "high-shine" in lowered or "high shine" in lowered:
        required.append("high_shine")
    if "hydrating language" in lowered or "hydrating" in lowered:
        required.append("hydrating_language")
    if "stick form" in lowered or "stick format" in lowered:
        required.append("stick_form")
    if "red/pink/wine" in lowered:
        required.append("red_pink_wine_spectrum")
    if "soft-focus" in lowered or "soft focus" in lowered or "blur" in lowered:
        required.append("soft_focus_blur")
    if "tint" in lowered:
        required.append("tint_like")
    if "multi-use" in lowered or "multi use" in lowered:
        required.append("multi_use_flexibility")
    if (
        "multi-texture" in lowered
        or "multi texture" in lowered
        or "pan delivery" in lowered
        or "within a compact" in lowered
    ):
        required.append("multi_texture_compact")
    if (
        "two-pan" in lowered
        or "two pan" in lowered
        or "cream and powder" in lowered
        or "cream/powder" in lowered
    ):
        required.append("cream_powder_duo")
    if "smooth" in lowered or "glide" in lowered or "blendability" in lowered:
        required.append("smooth_glide")
    if "creamy" in lowered:
        required.append("creamy_texture")
    if "streak-free" in lowered or "streak free" in lowered:
        required.append("streak_free")
    if "glow" in lowered or "luminous" in lowered:
        required.append("luminous_glow")
    if "natural finish" in lowered:
        required.append("natural_finish")
    if "powder attributes" in lowered or "powder attribute" in lowered:
        required.append("pressed_powder")
    if "multiple proven" in lowered or "bridge product" in lowered:
        required.append("multi_attribute_profile")
    return _unique_texts(required)


def _slide_product_anchor(
    claims: list[dict[str, Any]],
    slide_number: int | None,
) -> str | None:
    if slide_number is None:
        return None
    matching = [
        claim
        for claim in claims
        if claim.get("status") == "verified"
        and claim.get("claim_family") == "product_exemplar"
        and _int_or_none(claim.get("slide_number")) == slide_number
    ]
    if len(matching) != 1:
        return None
    details = (
        matching[0].get("details")
        if isinstance(matching[0].get("details"), dict)
        else {}
    )
    return _normalize_text(details.get("normalized_product_name"))


def _validate_product_attribute_segment(
    segment: str,
    *,
    product_name: str,
    package: LaunchPackageData,
) -> dict[str, Any] | None:
    if not _looks_like_product_attribute_claim(segment):
        return None
    product_context = _build_product_context(product_name, package.frames)
    if product_context is None:
        return {
            "status": "warning",
            "message": "product attribute claim did not resolve to a package product",
            "normalized_product_name": product_name,
        }

    required_attributes = _product_attribute_requirements(segment)
    if not required_attributes:
        return {
            "status": "warning",
            "message": "product attribute claim did not expose deterministic attributes",
            "normalized_product_name": product_context["normalized_product_name"],
        }

    reasons: list[str] = []
    matched_attribute_flags: list[str] = []
    attribute_support: list[dict[str, Any]] = []
    for attribute_id in required_attributes:
        match = _product_attribute_match(product_context, attribute_id)
        attribute_support.append(match)
        if match["matched"]:
            matched_attribute_flags.append(attribute_id)
        else:
            reasons.append(f"product attribute support missing for: {attribute_id}")

    return {
        "status": "pass" if not reasons else "fail",
        "normalized_product_name": product_context["normalized_product_name"],
        "product_id": product_context.get("product_id"),
        "price_tier": product_context.get("price_tier"),
        "matched_attribute_flags": matched_attribute_flags,
        "source_row_ids": product_context.get("source_row_ids", []),
        "attribute_support": attribute_support,
        "aggregation_rule_id": "product_attribute_profile_v1",
        "reasons": reasons,
    }


def _product_anchor_candidate_texts(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    candidates: list[str] = []
    product_match = re.search(
        r"\bProduct\s*:\s*(?P<name>.*?)(?:\s+Mapped\s+Attributes\b|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if product_match is not None:
        candidates.append(_normalize_text(product_match.group("name")))

    exhibit_match = re.search(
        r"\bExhibit\s+(?:[A-Z]|\d+|ID)\s*:\s*(?P<name>.*)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if exhibit_match is not None:
        candidates.append(_normalize_text(exhibit_match.group("name")))

    cleaned = re.sub(
        r"\bMapped\s+Attributes\b.*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:Physical\s+Evidence|Validation\s+Profile)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bExhibit\s+(?:[A-Z]|\d+|ID)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bProduct\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    candidates.append(_normalize_text(cleaned))
    candidates.append(normalized)
    return _unique_texts(candidate for candidate in candidates if candidate)


def _best_product_name_from_anchor_text(
    text: str,
    package: LaunchPackageData,
) -> str | None:
    for candidate_text in _product_anchor_candidate_texts(text):
        product_name = _best_product_name_from_segment(candidate_text, package)
        if product_name is not None:
            return product_name
        product_name = _best_product_name_from_text(
            candidate_text, package.product_names
        )
        if product_name is not None:
            return product_name

    best_name: str | None = None
    best_score = -1.0
    tied = False
    target_mentions_mini = "mini" in _product_match_tokens(text)
    for candidate_text in _product_anchor_candidate_texts(text):
        target_tokens = _product_match_tokens(candidate_text)
        if len(target_tokens) < 2:
            continue
        for product_name in package.product_names:
            candidate_tokens = _product_match_tokens(product_name)
            if not candidate_tokens:
                continue
            shared_tokens = target_tokens & candidate_tokens
            if len(shared_tokens) < 2:
                continue
            target_coverage = len(shared_tokens) / len(target_tokens)
            if target_coverage < 0.75:
                continue
            score = (
                target_coverage * 100
                + len(shared_tokens) * 3
                - max(0, len(candidate_tokens) - len(target_tokens))
            )
            candidate_mentions_mini = "mini" in candidate_tokens
            if target_mentions_mini != candidate_mentions_mini:
                score -= 10
            top_seller_hit = _find_product_row(
                product_name,
                package.frames,
                file_order=("top_seller_products.csv",),
            )
            if top_seller_hit is not None:
                score += 2
            if score > best_score:
                best_score = score
                best_name = _normalize_text(product_name)
                tied = False
            elif score == best_score and best_name != _normalize_text(product_name):
                tied = True

    return None if tied else best_name


def _prior_product_anchor_from_non_claims(
    item: dict[str, Any],
    non_claims: list[dict[str, Any]],
    package: LaunchPackageData,
) -> str | None:
    slide_number = _int_or_none(item.get("slide_number"))
    item_unit_index = _int_or_none(item.get("unit_index"))
    if slide_number is None or item_unit_index is None:
        return None

    candidates: list[tuple[int, int, str]] = []
    for non_claim_index, non_claim in enumerate(non_claims):
        if _int_or_none(non_claim.get("slide_number")) != slide_number:
            continue
        non_claim_unit_index = _int_or_none(non_claim.get("unit_index"))
        if non_claim_unit_index is None:
            continue
        distance = item_unit_index - non_claim_unit_index
        if distance <= 0 or distance > 8:
            continue
        product_name = _best_product_name_from_anchor_text(
            _normalize_text(non_claim.get("claim_text")),
            package,
        )
        if product_name is None:
            continue
        candidates.append((distance, non_claim_index, product_name))

    if not candidates:
        return None
    candidates.sort(key=lambda candidate: candidate[:2])
    return candidates[0][2]


def _looks_like_product_review_claim(text: str) -> bool:
    lowered = text.casefold()
    return bool(
        re.search(r"\b(?:friction|rating|review|reviewers|reviews)\b", lowered)
        or "consumer friction" in lowered
        or "validates perceived" in lowered
    )


def _product_review_rows(
    product_name: str,
    package: LaunchPackageData,
) -> list[dict[str, Any]]:
    product_context = _build_product_context(product_name, package.frames)
    if product_context is None:
        return []

    normalized_product_name = _normalize_text(
        product_context.get("normalized_product_name")
    )
    target_key = _canonical_text(normalized_product_name)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for match in product_context.get("rows", []):
        row = match["row"]
        source_file = _normalize_text(match.get("file"))
        key = (
            source_file,
            _canonical_text(row.get("product_name")),
            _canonical_text(row.get("bundle_label")),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append({"source_file": source_file, "row": row})

    for file_name in (
        "top_seller_review_validation.csv",
        "bundle_review_validation.csv",
    ):
        df = package.frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "product_name" not in columns:
            continue
        for row in df.to_dicts():
            if _canonical_text(row.get("product_name")) != target_key:
                continue
            key = (
                file_name,
                _canonical_text(row.get("product_name")),
                _canonical_text(row.get("bundle_label")),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append({"source_file": file_name, "row": row})

    return rows


def _product_review_row_text(
    row: dict[str, Any],
    columns: tuple[str, ...],
    *,
    include_descriptors: bool = False,
) -> str:
    descriptor_columns = (
        "benefits",
        "benefits/claims",
        "description_excerpt",
        "summary",
        "resolved_finish",
        "resolved_coverage",
        "resolved_form",
        "form",
        "coverage",
        "wear claims",
    )
    selected_columns = columns + descriptor_columns if include_descriptors else columns
    return _fold_text(
        " ".join(
            _normalize_text(row.get(column))
            for column in selected_columns
            if row.get(column)
        )
    )


def _requested_product_review_topics(
    segment: str,
    topic_keywords: dict[str, tuple[str, ...]],
) -> dict[str, tuple[str, ...]]:
    lowered = _fold_text(segment)
    requested: dict[str, tuple[str, ...]] = {}
    topic_triggers = {
        "texture_blend": ("blend", "blendability", "creamy", "smooth", "texture"),
        "color_payoff": ("color payoff", "payoff", "pigment"),
        "glow_finish": ("airbrush", "blur", "glow", "luminous"),
        "multi_use": ("ease of use", "multi-use", "multi use", "on the go"),
        "natural_finish": ("natural finish",),
        "shade_expectation": ("shade", "shade expectation"),
        "packaging": ("packag", "casing"),
        "limited_color_payoff": ("color payoff", "limited", "payoff", "pigment"),
        "application_fit": ("application", "application fit", "patchy"),
        "price_value": ("payoff-to-price", "price", "price ratio"),
        "product_identity": ("bronzer vs", "contour", "utility"),
        "wear_finish": ("finish", "longevity", "wear"),
    }
    for topic, keywords in topic_keywords.items():
        triggers = topic_triggers.get(topic, keywords)
        if any(trigger in lowered for trigger in triggers):
            requested[topic] = keywords
    return requested


def _product_review_topic_support(
    rows: list[dict[str, Any]],
    requested_topics: dict[str, tuple[str, ...]],
    *,
    columns: tuple[str, ...],
    include_descriptors: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    support: dict[str, list[dict[str, Any]]] = {topic: [] for topic in requested_topics}
    for row_record in rows:
        row = row_record["row"]
        blob = _product_review_row_text(
            row,
            columns,
            include_descriptors=include_descriptors,
        )
        if not blob:
            continue
        for topic, keywords in requested_topics.items():
            if not any(keyword in blob for keyword in keywords):
                continue
            support[topic].append(
                {
                    "source_file": row_record["source_file"],
                    "product_name": _normalize_text(row.get("product_name")),
                    "bundle_label": _normalize_text(row.get("bundle_label")),
                    "brand": _normalize_text(row.get("brand")),
                    "rating": _float_or_none(row.get("rating")),
                    "review_count": _int_or_none(row.get("review_count")),
                    "positive_headline": _normalize_text(
                        row.get("reviews_positive_headline")
                    ),
                    "negative_headline": _normalize_text(
                        row.get("reviews_negative_headline")
                    ),
                }
            )
    return support


_PRODUCT_REVIEW_RATING_RE = re.compile(
    r"\b(?P<rating>[1-5](?:\.\d+)?)\s*(?:star\s*)?rating\b",
    re.IGNORECASE,
)


def _product_review_rating_mentions(segment: str) -> list[float]:
    return [
        float(match.group("rating"))
        for match in _PRODUCT_REVIEW_RATING_RE.finditer(segment)
    ]


def _validate_product_review_segment(
    segment: str,
    *,
    product_name: str,
    package: LaunchPackageData,
) -> dict[str, Any] | None:
    if not _looks_like_product_review_claim(segment):
        return None

    rows = _product_review_rows(product_name, package)
    if not rows:
        return {
            "status": "warning",
            "message": "product review claim did not resolve to review rows",
            "normalized_product_name": product_name,
        }

    positive_topics = _requested_product_review_topics(
        segment,
        _PRODUCT_REVIEW_POSITIVE_TOPIC_KEYWORDS,
    )
    negative_topics = _requested_product_review_topics(
        segment,
        _PRODUCT_REVIEW_NEGATIVE_TOPIC_KEYWORDS,
    )
    rating_mentions = _product_review_rating_mentions(segment)
    if not positive_topics and not negative_topics and not rating_mentions:
        return {
            "status": "warning",
            "message": "product review wording is missing deterministic review topics",
            "normalized_product_name": product_name,
        }

    positive_support = _product_review_topic_support(
        rows,
        positive_topics,
        columns=_REVIEW_POSITIVE_TEXT_COLUMNS,
    )
    negative_support = _product_review_topic_support(
        rows,
        negative_topics,
        columns=_PRODUCT_REVIEW_NEGATIVE_TEXT_COLUMNS,
    )
    package_ratings = sorted(
        {
            rating
            for rating in (
                _float_or_none(row_record["row"].get("rating")) for row_record in rows
            )
            if rating is not None
        }
    )

    reasons: list[str] = []
    supported_topic_count = 0
    requested_topic_count = len(positive_topics) + len(negative_topics)
    for topic, support_rows in positive_support.items():
        if support_rows:
            supported_topic_count += 1
        else:
            reasons.append(f"product review lacks positive support for topic: {topic}")
    for topic, support_rows in negative_support.items():
        if support_rows:
            supported_topic_count += 1
        else:
            reasons.append(f"product review lacks friction support for topic: {topic}")

    rating_matches: list[dict[str, Any]] = []
    for rating in rating_mentions:
        matched_rating = next(
            (
                package_rating
                for package_rating in package_ratings
                if _approx_equal(rating, package_rating, 0.15)
            ),
            None,
        )
        if matched_rating is None:
            reasons.append(
                "rating mismatch: expected "
                + " or ".join(
                    f"{package_rating:.1f}" for package_rating in package_ratings
                )
            )
        else:
            rating_matches.append(
                {"claimed_rating": rating, "package_rating": matched_rating}
            )

    if not reasons:
        status = "pass"
    elif supported_topic_count or rating_matches:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "normalized_product_name": product_name,
        "row_support": [
            {
                "source_files": _unique_texts(
                    row_record["source_file"] for row_record in rows
                ),
                "positive_support": {
                    topic: support_rows[:5]
                    for topic, support_rows in positive_support.items()
                },
                "negative_support": {
                    topic: support_rows[:5]
                    for topic, support_rows in negative_support.items()
                },
                "rating_matches": rating_matches,
                "package_ratings": package_ratings,
            }
        ],
        "component_entities": [product_name],
        "aggregation_rule_id": "product_review_topics_v1",
        "cohort_basis": "product_review_rows",
        "threshold_policy": {
            "positive_topics": sorted(positive_topics),
            "friction_topics": sorted(negative_topics),
            "rating_tolerance": 0.15,
        },
        "ranking_basis": (
            "review text and PDP descriptor rows matching the adjacent product anchor"
        ),
        "reasons": reasons,
    }


def _looks_like_product_tier_span_claim(text: str) -> bool:
    lowered = text.casefold()
    return "pricing tier" in lowered and any(
        marker in lowered for marker in ("mass to prestige", "mass-market", "prestige")
    )


def _validate_product_tier_span_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_product_tier_span_claim(segment):
        return None
    df = frames["product_filter_matrix.csv"]
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "product_name" not in columns:
        return {
            "status": "warning",
            "message": "product tier span needs product_filter_matrix rows",
        }

    lowered = _fold_text(segment)
    story_hits: list[dict[str, Any]] = []
    for row in df.to_dicts():
        blob = _fold_text(
            " ".join(
                _normalize_text(row.get(column))
                for column in (
                    "benefits",
                    "coverage",
                    "resolved_coverage",
                    "summary",
                    "description_excerpt",
                )
                if row.get(column)
            )
        )
        if "buildable" in lowered and "buildable" not in blob:
            continue
        if "blur" in lowered and "blur" not in blob:
            continue
        story_hits.append(row)

    tier_to_rows: dict[str, list[dict[str, Any]]] = {}
    for row in story_hits:
        tier = _normalize_text(row.get("price_band"))
        if not tier:
            continue
        tier_to_rows.setdefault(tier, []).append(row)

    reasons: list[str] = []
    if "value" not in tier_to_rows:
        reasons.append("story lacks value-tier product support")
    if "premium" not in tier_to_rows:
        reasons.append("story lacks premium-tier product support")

    return {
        "status": "pass" if not reasons else "fail",
        "aggregation_rule_id": "product_tier_span_v1",
        "cohort_basis": "package_product_rows",
        "price_tiers": sorted(tier_to_rows),
        "row_support": [
            {
                "source_file": "product_filter_matrix.csv",
                "price_tier": tier,
                "product_names": _unique_texts(
                    _normalize_text(row.get("product_name")) for row in rows
                ),
            }
            for tier, rows in sorted(tier_to_rows.items())
        ],
        "reasons": reasons,
    }


_LOW_COUNT_NOVELTY_MAX_RECENT_COUNT = 5
_LOW_COUNT_NOVELTY_MAX_RECENT_SHARE = 0.12
_LOW_COUNT_NOVELTY_TEXT_COLUMNS = (
    "product_name",
    "product_name_norm",
    "form",
    "resolved_form",
    "finish",
    "resolved_finish",
    "coverage",
    "resolved_coverage",
    "benefits",
    "description",
    "description_excerpt",
    "summary",
)


def _looks_like_low_count_novelty_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "lacks mass",
            "product counts too low",
            "too low to indicate broad category shifts",
            "small-format novelty",
        )
    )


def _low_count_novelty_requested_groups(segment: str) -> list[dict[str, Any]]:
    lowered = segment.casefold()
    groups: list[dict[str, Any]] = []
    if "balm" in lowered:
        groups.append({"label": "balm", "tokens": {"balm"}})
    if "stain" in lowered:
        groups.append({"label": "tint/stain", "tokens": {"stain"}})
    if "sheer" in lowered and ("high-shine" in lowered or "high shine" in lowered):
        groups.append(
            {
                "label": "sheer/high-shine",
                "tokens": {"sheer", "high", "shine"},
            }
        )
    elif "high-shine" in lowered or "high shine" in lowered:
        groups.append({"label": "high-shine", "tokens": {"high", "shine"}})
    elif "sheer" in lowered:
        groups.append({"label": "sheer", "tokens": {"sheer"}})
    return groups


def _low_count_novelty_threshold_policy() -> dict[str, Any]:
    return {
        "maximum_recent_product_count": _LOW_COUNT_NOVELTY_MAX_RECENT_COUNT,
        "maximum_recent_product_share": _LOW_COUNT_NOVELTY_MAX_RECENT_SHARE,
        "source_files": [
            "mapped_attribute_comparison.csv",
            "product_filter_matrix.csv",
        ],
        "interpretation": (
            "small-format novelty claims are supported only when each named "
            "recent-product attribute group stays below both the recent count "
            "and recent share thresholds"
        ),
    }


def _row_product_identity(row: dict[str, Any]) -> tuple[str, str]:
    return (
        _normalize_text(row.get("parent_product_id"))
        or _normalize_text(row.get("listing_identity"))
        or _normalize_text(row.get("canonical_id_export"))
        or _normalize_text(row.get("canonical_id")),
        _canonical_text(row.get("product_name")),
    )


def _row_is_recent_product(row: dict[str, Any]) -> bool:
    listing_status = _normalize_text(row.get("listing_status")).casefold()
    if listing_status:
        return listing_status == "recent"
    return bool(row.get("has_new_badge"))


def _low_count_attribute_row_support(
    frames: dict[str, pl.DataFrame],
    *,
    label: str,
    tokens: set[str],
) -> list[dict[str, Any]]:
    df = frames.get("mapped_attribute_comparison.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "attribute_value" not in columns:
        return []

    support: list[dict[str, Any]] = []
    for row in df.to_dicts():
        value = _normalize_text(row.get("attribute_value"))
        if not tokens <= _canonical_tokens(value):
            continue
        count_recent = _int_or_none(row.get("count_recent"))
        recent_base = _int_or_none(row.get("recent_base"))
        pct_recent = _float_or_none(row.get("pct_recent"))
        if pct_recent is None and count_recent is not None and recent_base:
            pct_recent = count_recent / recent_base
        support.append(
            {
                "source_file": "mapped_attribute_comparison.csv",
                "matched_row_keys": {
                    "attribute_name": _normalize_text(row.get("attribute_name")),
                    "attribute_value": value,
                },
                "requested_group": label,
                "computed_values": {
                    "count_recent": count_recent,
                    "recent_base": recent_base,
                    "recent_share": pct_recent,
                    "count_rest": _int_or_none(row.get("count_rest")),
                    "rest_base": _int_or_none(row.get("rest_base")),
                    "rest_share": _float_or_none(row.get("pct_rest")),
                },
            }
        )
    return support


def _low_count_product_filter_row_blob(
    row: dict[str, Any],
    columns: set[str],
) -> str:
    return " ".join(
        _fold_text(row.get(column))
        for column in _LOW_COUNT_NOVELTY_TEXT_COLUMNS
        if column in columns and _normalize_text(row.get(column))
    )


def _low_count_product_filter_support(
    frames: dict[str, pl.DataFrame],
    *,
    label: str,
    tokens: set[str],
) -> dict[str, Any] | None:
    df = frames.get("product_filter_matrix.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty():
        return None

    column_set = set(columns)
    rows = df.to_dicts()
    recent_rows = [row for row in rows if _row_is_recent_product(row)]
    base_rows = recent_rows or rows
    matching_identities: set[tuple[str, str]] = set()
    examples: list[dict[str, str]] = []
    for row in base_rows:
        row_tokens = _canonical_tokens(
            _low_count_product_filter_row_blob(row, column_set)
        )
        if not tokens <= row_tokens:
            continue
        identity = _row_product_identity(row)
        if identity in matching_identities:
            continue
        matching_identities.add(identity)
        if len(examples) < 5:
            examples.append(
                {
                    "product_name": _normalize_text(row.get("product_name")),
                    "brand": _normalize_text(row.get("brand")),
                    "listing_status": _normalize_text(row.get("listing_status")),
                }
            )

    base_identities = {
        _row_product_identity(row)
        for row in base_rows
        if _row_product_identity(row) != ("", "")
    }
    base_count = len(base_identities) or get_row_count(df)
    count_recent = len(matching_identities)
    recent_share = count_recent / base_count if base_count else None
    return {
        "source_file": "product_filter_matrix.csv",
        "matched_row_keys": {
            "requested_group": label,
            "matched_tokens": sorted(tokens),
            "cohort": "recent_products" if recent_rows else "all_products",
        },
        "requested_group": label,
        "computed_values": {
            "count_recent": count_recent,
            "recent_base": base_count,
            "recent_share": recent_share,
        },
        "example_products": examples,
    }


def _low_count_support_passes_thresholds(
    support: dict[str, Any],
    threshold_policy: dict[str, Any],
) -> bool:
    values = support.get("computed_values")
    if not isinstance(values, dict):
        return False
    count_recent = _int_or_none(values.get("count_recent"))
    recent_share = _float_or_none(values.get("recent_share"))
    if count_recent is None or recent_share is None:
        return False
    return (
        count_recent <= threshold_policy["maximum_recent_product_count"]
        and recent_share <= threshold_policy["maximum_recent_product_share"]
    )


def _validate_low_count_novelty_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_low_count_novelty_claim(segment):
        return None

    requested_groups = _low_count_novelty_requested_groups(segment)
    if not requested_groups:
        return {
            "status": "warning",
            "message": "low-count novelty claim did not name a supported format group",
            "threshold_policy": _low_count_novelty_threshold_policy(),
        }

    threshold_policy = _low_count_novelty_threshold_policy()
    row_support: list[dict[str, Any]] = []
    supported_groups: list[str] = []
    contradicted_groups: list[str] = []
    missing_groups: list[str] = []
    reasons: list[str] = []

    for group in requested_groups:
        label = _normalize_text(group.get("label"))
        tokens = set(group.get("tokens", set()))
        attribute_support = _low_count_attribute_row_support(
            frames,
            label=label,
            tokens=tokens,
        )
        if attribute_support:
            row_support.extend(attribute_support)
            group_supported = all(
                _low_count_support_passes_thresholds(support, threshold_policy)
                for support in attribute_support
            )
        else:
            product_support = _low_count_product_filter_support(
                frames,
                label=label,
                tokens=tokens,
            )
            if product_support is None:
                missing_groups.append(label)
                reasons.append(f"{label} did not resolve to package rows")
                continue
            row_support.append(product_support)
            group_supported = _low_count_support_passes_thresholds(
                product_support,
                threshold_policy,
            )

        if group_supported:
            supported_groups.append(label)
        else:
            contradicted_groups.append(label)
            reasons.append(f"{label} exceeds the low-count novelty threshold")

    if missing_groups and not supported_groups and not contradicted_groups:
        status = "warning"
    elif contradicted_groups:
        status = "partial" if supported_groups else "fail"
    elif missing_groups:
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "row_support": row_support,
        "component_entities": _unique_texts(
            group["label"] for group in requested_groups
        ),
        "aggregation_rule_id": "low_count_novelty_format_v1",
        "cohort_basis": "recent_product_attribute_counts",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "recent product counts and shares for each named small-format group"
        ),
        "missing_components": missing_groups,
        "reasons": reasons,
    }


def _normalize_count_cohort_label(label: str) -> str | None:
    folded = _fold_text(label)
    if "recent" in folded:
        return "recent"
    if "top" in folded and ("seller" in folded or "selling" in folded):
        return "top_seller"
    return None


def _package_product_cohort_counts(frames: dict[str, pl.DataFrame]) -> dict[str, int]:
    return {
        "recent": int(get_row_count(frames["recent_products.csv"])),
        "top_seller": int(get_row_count(frames["top_seller_products.csv"])),
    }


def _extract_cohort_count_mentions(segment: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _COHORT_COUNT_MENTION_RE.finditer(segment):
        cohort = _normalize_count_cohort_label(match.group("label"))
        if cohort is None or cohort in seen:
            continue
        seen.add(cohort)
        mentions.append(
            {
                "cohort": cohort,
                "label": _normalize_text(match.group("label")),
                "count": int(match.group("count")),
                "text": _normalize_text(match.group(0)),
            }
        )
    return mentions


def _validate_cohort_count_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    mentions = _extract_cohort_count_mentions(segment)
    if len(mentions) < 2:
        return None

    package_counts = _package_product_cohort_counts(frames)
    observed_counts = {mention["cohort"]: mention["count"] for mention in mentions}
    expected_counts = {
        cohort: package_counts[cohort]
        for cohort in observed_counts
        if cohort in package_counts
    }
    missing_cohorts = [
        cohort for cohort in observed_counts if cohort not in expected_counts
    ]
    reasons = [
        f"{cohort} count mismatch: expected {expected_count}, observed {observed_counts[cohort]}"
        for cohort, expected_count in expected_counts.items()
        if observed_counts[cohort] != expected_count
    ]
    if missing_cohorts:
        reasons.append(
            "missing package cohort count(s): " + ", ".join(sorted(missing_cohorts))
        )

    return {
        "status": "fail" if reasons else "pass",
        "observed_counts": observed_counts,
        "package_counts": expected_counts,
        "mentions": mentions,
        "reasons": reasons,
    }


def _cohort_count_evidence_details(result: dict[str, Any]) -> dict[str, Any]:
    observed_counts = result.get("observed_counts", {})
    package_counts = result.get("package_counts", {})
    details: dict[str, Any] = {
        "cohort_labels": list(observed_counts.keys()),
        "count_values": observed_counts,
        "observed_values": {"cohort_counts": observed_counts},
        "package_values": {"cohort_counts": package_counts},
        "source_basis": {
            "recent": "recent_products.csv",
            "top_seller": "top_seller_products.csv",
        },
        "comparison_policy": "exact equality on deterministic product cohort row counts",
        "matched_row_keys": {
            cohort: {"source_file": source_file}
            for cohort, source_file in {
                "recent": "recent_products.csv",
                "top_seller": "top_seller_products.csv",
            }.items()
            if cohort in observed_counts
        },
    }
    if result.get("mentions"):
        details["parsed_mentions"] = result["mentions"]
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    return details


def _cohort_overlap_key_column(
    recent_df: pl.DataFrame,
    top_seller_df: pl.DataFrame,
) -> str | None:
    recent_columns, _recent_schema = get_schema_and_column_names(recent_df)
    top_seller_columns, _top_seller_schema = get_schema_and_column_names(top_seller_df)
    for column in _COHORT_PRODUCT_ID_COLUMNS:
        if column not in recent_columns or column not in top_seller_columns:
            continue
        recent_values = _cohort_product_key_values(recent_df, column)
        top_seller_values = _cohort_product_key_values(top_seller_df, column)
        if recent_values and top_seller_values:
            return column
    return None


def _cohort_product_key_values(df: pl.DataFrame, key_column: str) -> set[str]:
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or key_column not in columns:
        return set()
    return {
        value
        for value in (
            _normalize_text(row.get(key_column))
            for row in df.select(key_column).to_dicts()
        )
        if value
    }


def _top_seller_window_for_overlap(
    top_seller_df: pl.DataFrame,
    top_count: int,
) -> tuple[pl.DataFrame, str]:
    columns, _schema = get_schema_and_column_names(top_seller_df)
    if "pareto_rank" in columns:
        ranked = top_seller_df.filter(
            pl.col("pareto_rank").cast(pl.Int64, strict=False) <= top_count
        )
        if not ranked.is_empty():
            return ranked, "pareto_rank <= claimed top product count"
    return top_seller_df.head(top_count), "first claimed top product rows"


def _cohort_overlap_sample_rows(
    df: pl.DataFrame,
    *,
    key_column: str,
    overlap_keys: set[str],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    columns, _schema = get_schema_and_column_names(df)
    detail_columns = [
        column
        for column in ("pareto_rank", "brand", "product_name", key_column)
        if column in columns
    ]
    for row in df.select(detail_columns).to_dicts():
        key_value = _normalize_text(row.get(key_column))
        if key_value not in overlap_keys:
            continue
        samples.append(
            {
                "key": key_value,
                "pareto_rank": _int_or_none(row.get("pareto_rank")),
                "brand": _normalize_text(row.get("brand")),
                "product_name": _normalize_text(row.get("product_name")),
            }
        )
    return samples[:10]


def _validate_cohort_overlap_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    match = _COHORT_OVERLAP_TOP_WINDOW_RE.search(segment)
    if match is None:
        return None

    observed_overlap_count = int(match.group("overlap"))
    top_window_count = int(match.group("top_count"))
    recent_df = frames["recent_products.csv"]
    top_seller_df = frames["top_seller_products.csv"]
    if recent_df.is_empty() or top_seller_df.is_empty():
        return {
            "status": "warning",
            "message": "cohort overlap claim needs recent and top-seller product rows",
            "observed_values": {
                "overlap_count": observed_overlap_count,
                "top_window_count": top_window_count,
            },
        }

    key_column = _cohort_overlap_key_column(recent_df, top_seller_df)
    if key_column is None:
        return {
            "status": "warning",
            "message": "cohort overlap claim needs a shared product identity column",
            "observed_values": {
                "overlap_count": observed_overlap_count,
                "top_window_count": top_window_count,
            },
        }

    top_window_df, window_rule = _top_seller_window_for_overlap(
        top_seller_df,
        top_window_count,
    )
    recent_keys = _cohort_product_key_values(recent_df, key_column)
    top_window_keys = _cohort_product_key_values(top_window_df, key_column)
    overlap_keys = recent_keys & top_window_keys
    package_overlap_count = len(overlap_keys)
    reasons: list[str] = []
    if observed_overlap_count != package_overlap_count:
        reasons.append(
            "cohort overlap mismatch: "
            f"expected {package_overlap_count}, observed {observed_overlap_count}"
        )

    return {
        "status": "fail" if reasons else "pass",
        "observed_values": {
            "overlap_count": observed_overlap_count,
            "top_window_count": top_window_count,
        },
        "package_values": {
            "overlap_count": package_overlap_count,
            "recent_product_count": get_row_count(recent_df),
            "top_seller_product_count": get_row_count(top_seller_df),
            "top_window_product_count": get_row_count(top_window_df),
            "identity_column": key_column,
            "window_rule": window_rule,
            "overlap_products": _cohort_overlap_sample_rows(
                top_window_df,
                key_column=key_column,
                overlap_keys=overlap_keys,
            ),
        },
        "source_files": ["recent_products.csv", "top_seller_products.csv"],
        "matched_row_keys": {"identity_column": key_column},
        "comparison_policy": (
            "exact equality between claimed overlap count and package product "
            "identity intersection"
        ),
        "reasons": reasons,
    }


def _cohort_overlap_evidence_details(result: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {
        "observed_values": result.get("observed_values", {}),
        "package_values": result.get("package_values", {}),
        "source_basis": {
            "recent": "recent_products.csv",
            "top_seller": "top_seller_products.csv",
        },
        "matched_row_keys": result.get("matched_row_keys", {}),
        "comparison_policy": result.get("comparison_policy"),
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("source_files"):
        details["source_files"] = result["source_files"]
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    return details


def _validate_ranked_recent_top_seller_overlap_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    lowered = segment.casefold()
    if "recent" not in lowered or "top seller" not in lowered:
        return None
    match = _BRAND_RANKING_OVERLAP_RE.search(segment)
    if match is None:
        return None

    brand = _normalize_text(match.group("brand"))
    ranks = [int(value) for value in _HASH_RANK_RE.findall(match.group("ranks"))]
    if not brand or not ranks:
        return None

    df = frames.get("product_filter_matrix.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    required_columns = {"brand", "pareto_rank", "listing_status", "top_seller_status"}
    if df.is_empty() or not required_columns <= set(columns):
        return {
            "status": "warning",
            "message": "ranked overlap claim needs product_filter_matrix cohort columns",
            "observed_values": {"brand": brand, "ranks": ranks},
        }

    reasons: list[str] = []
    matched_rows: list[dict[str, Any]] = []
    for rank in ranks:
        rank_rows = df.filter(
            pl.col("pareto_rank").cast(pl.Int64, strict=False) == rank
        )
        brand_rows = [
            row
            for row in rank_rows.to_dicts()
            if _brand_names_compatible(brand, row.get("brand"))
        ]
        if not brand_rows:
            reasons.append(f"{brand} rank #{rank} not found in package")
            continue
        row = brand_rows[0]
        listing_status = _normalize_text(row.get("listing_status")).casefold()
        top_seller_status = _normalize_text(row.get("top_seller_status")).casefold()
        if listing_status != "recent":
            reasons.append(f"{brand} rank #{rank} is not in the recent cohort")
        if top_seller_status != "top_seller":
            reasons.append(f"{brand} rank #{rank} is not in the top-seller cohort")
        matched_rows.append(
            {
                "brand": _normalize_text(row.get("brand")),
                "product_name": _normalize_text(row.get("product_name")),
                "pareto_rank": rank,
                "listing_status": _normalize_text(row.get("listing_status")),
                "top_seller_status": _normalize_text(row.get("top_seller_status")),
                "canonical_id_export": _normalize_text(row.get("canonical_id_export")),
            }
        )

    return {
        "status": "fail" if reasons else "pass",
        "observed_values": {"brand": brand, "ranks": ranks},
        "package_values": {"matched_products": matched_rows},
        "source_files": ["product_filter_matrix.csv"],
        "matched_row_keys": {"brand": brand, "pareto_rank": ranks},
        "comparison_policy": (
            "exact rank lookup requiring listing_status=recent and "
            "top_seller_status=top_seller"
        ),
        "reasons": reasons,
    }


def _attribute_share_value_column(file_name: str) -> str:
    if file_name == "filter_comparison.csv":
        return "filter_value"
    return "attribute_value"


def _attribute_share_candidate_rows(
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name in (
        "top_seller_mapped_attribute_comparison.csv",
        "mapped_attribute_comparison.csv",
        "resolved_core_comparison.csv",
        "filter_comparison.csv",
    ):
        df = frames[file_name]
        value_column = _attribute_share_value_column(file_name)
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or value_column not in columns:
            continue
        for row in df.to_dicts():
            value = _normalize_text(row.get(value_column))
            if not value:
                continue
            candidates.append(
                {
                    "file": file_name,
                    "row": row,
                    "kind": "attribute_share",
                    "label": value,
                }
            )
    return candidates


def _looks_like_attribute_share_claim(
    text: str,
    unit: dict[str, Any],
) -> bool:
    folded = _fold_text(text)
    looks_like_brand_share = _looks_like_brand_share_claim(text)
    allows_attribute_over_index = "over-index" in folded or "over index" in folded
    if "+" in text or not _BUNDLE_PERCENT_RE.search(text):
        return False
    if looks_like_brand_share and not allows_attribute_over_index:
        return False
    roles = {mention.role for mention in _percent_mentions(text) if mention.role}
    if not roles:
        return False
    source_kind = _normalize_text(unit.get("source_kind"))
    return (
        source_kind == "table_row"
        or "overall" in folded
        or "prevalence" in folded
        or "share" in folded
        or "appears" in folded
        or "over-index" in folded
        or "over index" in folded
        or bool(re.search(r"\b(?:vs\.?|versus)\b", folded))
        or "compared to" in folded
    )


def _attribute_share_text_tokens(text: str) -> set[str]:
    return _canonical_tokens(text, ignored_tokens=_ATTRIBUTE_SHARE_TEXT_NOISE_TOKENS)


def _attribute_share_label_tokens(label: Any) -> set[str]:
    tokens = _canonical_tokens(
        label,
        ignored_tokens=_ATTRIBUTE_SHARE_LABEL_NOISE_TOKENS,
    )
    significant_tokens = {
        token for token in tokens if len(token) > 2 and not token.isdigit()
    }
    return significant_tokens or tokens


def _coerce_percent_role_for_supported_source(
    role: str | None,
    supported_roles: set[str],
) -> str | None:
    if role == "rest" and {"top_seller", "other"} <= supported_roles:
        return "other"
    if role == "other" and {"recent", "rest"} <= supported_roles:
        return "rest"
    return role


def _score_attribute_share_candidate(
    segment: str,
    candidate: dict[str, Any],
) -> tuple[bool, int, list[str], dict[str, Any]]:
    empty_metric_summary = {"matched_metrics": [], "mismatched_metrics": []}
    text_tokens = _attribute_share_text_tokens(segment)
    label = candidate.get("label")
    label_tokens = _attribute_share_label_tokens(label)
    overlap = text_tokens & label_tokens
    label_text = _normalize_text(label)
    minimum_overlap = (
        2
        if len(label_tokens) >= 3
        and "/" not in label_text
        and _canonical_text(label_text) not in _canonical_text(segment)
        else 1
    )
    if not overlap:
        return (
            False,
            0,
            ["attribute label tokens not found in text"],
            empty_metric_summary,
        )
    if len(overlap) < minimum_overlap:
        return (
            False,
            0,
            ["attribute label overlap is too weak for deterministic match"],
            empty_metric_summary,
        )

    score = len(overlap) * 10
    if label_tokens and label_tokens <= text_tokens:
        score += 25

    supported_roles = _candidate_supported_cohort_roles(candidate)
    mentions = [mention for mention in _percent_mentions(segment) if mention.role]
    mention_roles = [
        _coerce_percent_role_for_supported_source(mention.role, supported_roles)
        for mention in mentions
        if mention.role
    ]
    if len(mentions) >= 2 and len(set(role for role in mention_roles if role)) < 2:
        if _candidate_percent_for_role(candidate, "top_seller") is not None:
            mention_roles = ["top_seller", "other", *mention_roles[2:]]
        elif _candidate_percent_for_role(candidate, "recent") is not None:
            mention_roles = ["recent", "rest", *mention_roles[2:]]
    mentioned_roles = {role for role in mention_roles if role}
    if not mentioned_roles <= supported_roles:
        return (
            False,
            score,
            [
                "cohort label mismatch: text uses "
                + "/".join(sorted(mentioned_roles))
                + " but source row supports "
                + ("/".join(sorted(supported_roles)) or "unknown")
            ],
            {"matched_metrics": [], "mismatched_metrics": ["cohort_basis"]},
        )

    reasons: list[str] = []
    matched_metrics: list[str] = []
    mismatched_metrics: list[str] = []
    for mention, role in zip(mentions, mention_roles):
        metric_role = role or mention.role
        expected = _candidate_percent_for_role(candidate, metric_role or "")
        metric_name = f"{metric_role}_percent" if metric_role else "percent"
        if expected is None:
            reasons.append(
                f"{metric_role or mention.role} percent unavailable for source row"
            )
            mismatched_metrics.append(metric_name)
            continue
        if not _percent_matches(mention, expected):
            reasons.append(
                f"{metric_role or mention.role} percent mismatch: expected {_format_optional_percent(expected)}"
            )
            mismatched_metrics.append(metric_name)
        else:
            matched_metrics.append(metric_name)
            score += 1
    metric_summary = {
        "matched_metrics": matched_metrics,
        "mismatched_metrics": mismatched_metrics,
    }
    if reasons:
        return False, score, reasons, metric_summary
    return True, score, [], metric_summary


def _attribute_share_denominators(candidate: dict[str, Any]) -> dict[str, int | None]:
    row = candidate["row"]
    denominators: dict[str, int | None] = {}
    for role, column_name in (
        ("top_seller", "top_seller_base"),
        ("other", "other_base"),
        ("recent", "recent_base"),
        ("rest", "rest_base"),
    ):
        value = _int_or_none(row.get(column_name))
        if value is not None:
            denominators[role] = value
    return denominators


def _attribute_share_expected_values(
    candidate: dict[str, Any],
) -> dict[str, float | None]:
    return {
        role: round(value, 10)
        for role in ("top_seller", "other", "recent", "rest")
        if (value := _candidate_percent_for_role(candidate, role)) is not None
    }


def _attribute_share_candidate_evaluation(
    candidate: dict[str, Any],
    score: int,
    reasons: list[str],
    metric_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = metric_summary if isinstance(metric_summary, dict) else {}
    return {
        "file": candidate["file"],
        "score": score,
        "source_cohort_basis": _candidate_source_cohort_basis(candidate),
        "matched_row_keys": _candidate_row_keys(candidate),
        "package_values": _bundle_candidate_package_values(candidate),
        "denominators": _attribute_share_denominators(candidate),
        "reasons": reasons,
        "matched_metrics": metrics.get("matched_metrics", []),
        "mismatched_metrics": metrics.get("mismatched_metrics", []),
    }


def _validate_attribute_share_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    candidates = _attribute_share_candidate_rows(frames)
    passing: list[tuple[int, dict[str, Any]]] = []
    evaluations: list[dict[str, Any]] = []
    label_matches: list[tuple[int, dict[str, Any], list[str], dict[str, Any]]] = []
    for candidate in candidates:
        ok, score, reasons, metric_summary = _score_attribute_share_candidate(
            segment, candidate
        )
        if score <= 0:
            continue
        evaluations.append(
            _attribute_share_candidate_evaluation(
                candidate, score, reasons, metric_summary
            )
        )
        if ok:
            passing.append((score, candidate))
        else:
            label_matches.append((score, candidate, reasons, metric_summary))

    if passing:
        passing.sort(key=lambda item: item[0], reverse=True)
        best_score = passing[0][0]
        equally_best = [
            candidate for score, candidate in passing if score == best_score
        ]
        if len(equally_best) == 1:
            return {
                "status": "pass",
                "candidate": equally_best[0],
                "candidate_evaluations": evaluations,
            }
        return {
            "status": "warning",
            "message": "multiple matching attribute-share rows",
            "candidate_evaluations": evaluations,
        }

    if label_matches:

        def _label_match_sort_key(
            item: tuple[int, dict[str, Any], list[str], dict[str, Any]],
        ) -> tuple[bool, int, int]:
            score, _candidate, _reasons, metric_summary = item
            mismatched_metrics = (
                metric_summary.get("mismatched_metrics", [])
                if isinstance(metric_summary, dict)
                else []
            )
            matched_metrics = (
                metric_summary.get("matched_metrics", [])
                if isinstance(metric_summary, dict)
                else []
            )
            return (
                "cohort_basis" not in mismatched_metrics,
                len(matched_metrics),
                score,
            )

        label_matches.sort(key=_label_match_sort_key, reverse=True)
        best_score, best_candidate, best_reasons, best_metric_summary = label_matches[0]
        return {
            "status": (
                "partial"
                if _candidate_evaluation_has_partial_metric_support(best_metric_summary)
                else "fail"
            ),
            "candidate": best_candidate,
            "candidate_evaluations": evaluations,
            "reasons": best_reasons,
            "score": best_score,
            "matched_metrics": best_metric_summary.get("matched_metrics", []),
            "mismatched_metrics": best_metric_summary.get("mismatched_metrics", []),
        }

    return {
        "status": "warning",
        "message": "attribute share row not matched in package",
        "candidate_evaluations": evaluations,
    }


def _attribute_share_evidence_details(
    segment: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    candidate = result.get("candidate")
    details: dict[str, Any] = {
        "observed_text_values": _extract_numeric_claim_evidence(segment),
        "observed_values": _extract_numeric_claim_evidence(segment),
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    if not isinstance(candidate, dict):
        details["candidate_evaluations"] = result.get("candidate_evaluations", [])
        return details

    selected_evaluation = _attribute_share_candidate_evaluation(
        candidate,
        _int_or_none(result.get("score")) or 0,
        result.get("reasons", []),
        {
            "matched_metrics": result.get("matched_metrics", []),
            "mismatched_metrics": result.get("mismatched_metrics", []),
        },
    )
    details["candidate_evaluations"] = _candidate_evaluations_with_selected_first(
        result.get("candidate_evaluations", []),
        selected_evaluation,
    )
    selected_candidate_evaluation = (
        details["candidate_evaluations"][0]
        if details["candidate_evaluations"]
        and isinstance(details["candidate_evaluations"][0], dict)
        else {}
    )
    details.update(
        {
            "source_file": candidate["file"],
            "matched_row_keys": _candidate_row_keys(candidate),
            "rank_basis_or_share_basis": _candidate_source_cohort_basis(candidate),
            "expected_numeric_values": _attribute_share_expected_values(candidate),
            "package_values": _bundle_candidate_package_values(candidate),
            "denominators": _attribute_share_denominators(candidate),
            "tolerance_policy": _numeric_tolerance_policy(),
        }
    )
    if result.get("status") == "partial":
        details["partial_support_basis"] = (
            "at least one deterministic metric matched while another deterministic "
            "metric failed"
        )
    if selected_candidate_evaluation.get(
        "matched_metrics"
    ) or selected_candidate_evaluation.get("mismatched_metrics"):
        details["matched_metrics"] = selected_candidate_evaluation.get(
            "matched_metrics", []
        )
        details["mismatched_metrics"] = selected_candidate_evaluation.get(
            "mismatched_metrics", []
        )
    numeric_basis_diagnostics = _numeric_basis_diagnostics(segment, candidate)
    if numeric_basis_diagnostics:
        details["numeric_basis_diagnostics"] = numeric_basis_diagnostics
    return details


def _looks_like_directional_attribute_claim(text: str) -> bool:
    folded = _fold_text(text)
    if "+" in text and _contains_numeric_evidence(text):
        return False
    if not any(
        marker in folded
        for marker in (
            "away from",
            "leaning away",
            "moves away",
            "moving away",
            "pivot",
            "shift",
            "shifting",
            "flat",
            "do not form",
            "does not form",
            "toward",
            "towards",
            "under-index",
            "under index",
            "over-index",
            "over index",
        )
    ):
        return False
    return any(
        marker in folded
        for marker in (
            "emerging",
            "innovation",
            "recent",
            "rest",
            "top seller",
            "top sellers",
            "top-seller",
            "winner",
            "winners",
            "winning",
        )
    )


def _directional_attribute_source_files(segment: str) -> tuple[str, ...]:
    folded = _fold_text(segment)
    top_seller_cue = any(
        marker in folded
        for marker in (
            "top seller",
            "top sellers",
            "top-seller",
            "winner",
            "winners",
            "winning",
        )
    )
    recent_cue = any(
        marker in folded for marker in ("emerging", "innovation", "recent", "rest")
    )
    source_files: list[str] = []
    if top_seller_cue:
        source_files.append("top_seller_mapped_attribute_comparison.csv")
    if recent_cue or not source_files:
        source_files.extend(
            [
                "filter_comparison.csv",
                "mapped_attribute_comparison.csv",
                "resolved_core_comparison.csv",
            ]
        )
    return tuple(dict.fromkeys(source_files))


def _directional_attribute_candidate_rows(
    frames: dict[str, pl.DataFrame],
    *,
    source_files: tuple[str, ...],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name in source_files:
        df = frames[file_name]
        label_column = (
            "filter_value"
            if file_name == "filter_comparison.csv"
            else "attribute_value"
        )
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or label_column not in columns or "delta" not in columns:
            continue
        for row in df.to_dicts():
            if _bundle_single_attribute_row_is_excluded(row):
                continue
            label = _normalize_text(row.get(label_column))
            delta = _float_or_none(row.get("delta"))
            if not label or delta is None:
                continue
            candidates.append(
                {
                    "file": file_name,
                    "row": row,
                    "label": label,
                    "delta": delta,
                }
            )
    return candidates


def _directional_attribute_fragment_tokens(fragment: str) -> set[str]:
    return _canonical_tokens(
        fragment,
        ignored_tokens=_ATTRIBUTE_DIRECTION_FRAGMENT_NOISE_TOKENS,
    )


def _clean_directional_attribute_fragment(fragment: str) -> str:
    cleaned = _normalize_text(fragment.strip(" .;:,\"'“”‘’()[]"))
    cleaned = re.sub(
        r"^(?:and|or|but|while|with|the|a|an|current|recent|strictly)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:claims?|finishes?|formats?|forms?|delivery|appeal|"
        r"expressions?|structures?|products?)\b$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _normalize_text(cleaned.strip(" .;:,\"'“”‘’()[]"))


def _directional_attribute_fragment_is_generic(fragment: str) -> bool:
    tokens = _directional_attribute_fragment_tokens(fragment)
    return bool(tokens) and tokens <= {
        "current",
        "currently",
        "sharpest",
        "strongest",
        "seller",
        "sellers",
        "top",
    }


def _split_directional_attribute_fragments(fragment: str) -> list[str]:
    normalized = _normalize_text(fragment)
    if not normalized:
        return []
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    parts = re.split(r"\s*(?:,|/|\+|\band\b|\bor\b)\s*", normalized, flags=re.I)
    fragments = []
    for part in parts:
        cleaned = _clean_directional_attribute_fragment(part)
        if not cleaned:
            continue
        if not _directional_attribute_fragment_tokens(cleaned):
            continue
        if _directional_attribute_fragment_is_generic(cleaned):
            continue
        fragments.append(cleaned)
    return _unique_texts(fragments)


def _slice_directional_fragment_after(
    segment: str,
    marker: str,
    *,
    stop_markers: tuple[str, ...] = (),
) -> str:
    stop_markers = stop_markers or (".", ";")
    return _slice_after_marker(segment, marker, stop_markers=stop_markers)


def _directional_attribute_observations(segment: str) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    lowered = segment.casefold()

    for marker in (
        "leaning away from",
        "moves away from",
        "moving away from",
        "shift away from",
        "shifting emphasis away from",
        "shifting away from",
        "away from",
    ):
        if marker not in lowered:
            continue
        away_fragment = _slice_directional_fragment_after(
            segment,
            marker,
            stop_markers=(" toward ", " towards ", ".", ";"),
        )
        for fragment in _split_directional_attribute_fragments(away_fragment):
            observations.append({"fragment": fragment, "direction": "negative"})
        break

    if " toward " in lowered or " towards " in lowered:
        toward_marker = " toward " if " toward " in lowered else " towards "
        toward_fragment = _slice_directional_fragment_after(segment, toward_marker)
        for fragment in _split_directional_attribute_fragments(toward_fragment):
            observations.append({"fragment": fragment, "direction": "positive"})

    for clause in re.split(r"[.;]", segment):
        flat_clause = (clause.rsplit(":", 1)[-1] if ":" in clause else clause).strip()
        for match in _ATTRIBUTE_FLAT_RE.finditer(flat_clause):
            label = _clean_directional_attribute_fragment(match.group("label"))
            for fragment in _split_directional_attribute_fragments(label):
                observations.append({"fragment": fragment, "direction": "flat"})
        for match in _ATTRIBUTE_NOT_CENTRAL_BUNDLE_RE.finditer(flat_clause):
            label = _clean_directional_attribute_fragment(match.group("label"))
            for fragment in _split_directional_attribute_fragments(label):
                observations.append({"fragment": fragment, "direction": "flat"})

        for match in _ATTRIBUTE_DIRECTION_RE.finditer(clause):
            direction_text = _fold_text(match.group("direction"))
            direction = "negative" if "under" in direction_text else "positive"
            label = _clean_directional_attribute_fragment(match.group("label"))
            if ":" in clause[: match.start()] and any(
                token in _directional_attribute_fragment_tokens(label)
                for token in ("but", "individual", "level", "visible")
            ):
                label = _clean_directional_attribute_fragment(
                    clause[: match.start()].rsplit(":", 1)[0]
                )
            elif ":" in label:
                label = _clean_directional_attribute_fragment(label.rsplit(":", 1)[-1])
            label = re.sub(r"^(?:but|and|or|while)\s+", "", label, flags=re.I)
            for fragment in _split_directional_attribute_fragments(label):
                observations.append({"fragment": fragment, "direction": direction})

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for observation in observations:
        key = (observation["direction"], _canonical_text(observation["fragment"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(observation)
    return deduped


def _score_directional_attribute_candidate(
    fragment: str,
    candidate: dict[str, Any],
    *,
    source_files: tuple[str, ...],
) -> int:
    fragment_tokens = _directional_attribute_fragment_tokens(fragment)
    label_tokens = _directional_attribute_fragment_tokens(candidate.get("label"))
    overlap = fragment_tokens & label_tokens
    if not overlap:
        return 0

    score = len(overlap) * 10
    if label_tokens and label_tokens <= fragment_tokens:
        score += 25
    if fragment_tokens and fragment_tokens <= label_tokens:
        score += 10
    if _canonical_text(fragment) == _canonical_text(candidate.get("label")):
        score += 40
    if "|" in _normalize_text(candidate.get("label")):
        score -= 8

    file_name = _normalize_text(candidate.get("file"))
    try:
        score += max(0, len(source_files) - source_files.index(file_name))
    except ValueError:
        pass
    if file_name == "filter_comparison.csv":
        score += 4
    return score


def _best_directional_attribute_candidate(
    fragment: str,
    frames: dict[str, pl.DataFrame],
    *,
    source_files: tuple[str, ...],
) -> dict[str, Any] | None:
    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in _directional_attribute_candidate_rows(
        frames,
        source_files=source_files,
    ):
        score = _score_directional_attribute_candidate(
            fragment,
            candidate,
            source_files=source_files,
        )
        if score <= 0:
            continue
        scored.append((score, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    tied = [candidate for score, candidate in scored if score == best_score]
    if len(tied) == 1:
        return tied[0]
    exact_matches = [
        candidate
        for candidate in tied
        if _canonical_text(candidate.get("label")) == _canonical_text(fragment)
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    return None


def _directional_attribute_support_detail(
    *,
    fragment: str,
    direction: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    row = candidate["row"]
    left_role = "top_seller" if "pct_top_seller" in row else "recent"
    right_role = "other" if left_role == "top_seller" else "rest"
    return {
        "fragment_text": fragment,
        "claimed_direction": direction,
        "entity": _normalize_text(candidate.get("label")),
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "cohort_basis": _candidate_source_cohort_basis(candidate),
        "expected_numeric_values": {
            "delta": candidate["delta"],
            left_role: _candidate_percent_for_role(candidate, left_role),
            right_role: _candidate_percent_for_role(candidate, right_role),
        },
        "package_values": _bundle_candidate_package_values(candidate),
    }


def _validate_directional_attribute_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_directional_attribute_claim(segment):
        return None

    observations = _directional_attribute_observations(segment)
    if not observations:
        return None

    source_files = _directional_attribute_source_files(segment)
    threshold_policy = {
        "positive_delta_min": 0.0,
        "negative_delta_max": 0.0,
        "source_files": list(source_files),
        "comparison_rule": (
            "over/toward claims require positive delta; under/away claims "
            "require negative delta; flat/not-central claims require absolute "
            f"delta <= {_ATTRIBUTE_FLAT_DELTA_MAX:.2f}"
        ),
        "flat_delta_abs_max": _ATTRIBUTE_FLAT_DELTA_MAX,
    }
    reasons: list[str] = []
    attribute_support: list[dict[str, Any]] = []
    supported_count = 0
    opposite_count = 0

    for observation in observations:
        fragment = observation["fragment"]
        direction = observation["direction"]
        candidate = _best_directional_attribute_candidate(
            fragment,
            frames,
            source_files=source_files,
        )
        if candidate is None:
            reasons.append(
                f"attribute fragment did not resolve to a deterministic delta row: {fragment}"
            )
            continue
        detail = _directional_attribute_support_detail(
            fragment=fragment,
            direction=direction,
            candidate=candidate,
        )
        attribute_support.append(detail)
        delta = candidate["delta"]
        if direction == "positive" and delta > 0:
            supported_count += 1
        elif direction == "negative" and delta < 0:
            supported_count += 1
        elif direction == "flat" and abs(delta) <= _ATTRIBUTE_FLAT_DELTA_MAX:
            supported_count += 1
        else:
            opposite_count += 1
            reasons.append(
                f"{fragment} delta sign contradicts claimed {direction} direction"
            )

    if supported_count == len(observations):
        status = "pass"
    elif opposite_count:
        status = "fail"
    elif supported_count:
        status = "partial"
    else:
        status = "warning"

    return {
        "status": status,
        "attribute_support": attribute_support,
        "component_entities": [item["entity"] for item in attribute_support],
        "aggregation_rule_id": "attribute_direction_delta_v1",
        "cohort_basis": (
            "top_seller_vs_other"
            if "top_seller_mapped_attribute_comparison.csv" in source_files
            and len(source_files) == 1
            else "recent_vs_rest"
        ),
        "threshold_policy": threshold_policy,
        "ranking_basis": "single-attribute comparison rows with signed deltas",
        "observed_fragments": observations,
        "reasons": reasons,
    }


def _looks_like_attribute_rank_claim(text: str) -> bool:
    folded = _fold_text(text)
    return "recent core comparison" in folded and (
        "single biggest" in folded
        or "biggest statistical lift" in folded
        or "biggest lift" in folded
    )


def _attribute_rank_rows(
    frames: dict[str, pl.DataFrame],
    file_name: str,
) -> list[dict[str, Any]]:
    df = frames[file_name]
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "delta" not in columns or "attribute_value" not in columns:
        return []
    rows = [
        row
        for row in df.to_dicts()
        if _float_or_none(row.get("delta")) is not None
        and _normalize_text(row.get("attribute_value"))
    ]
    return sorted(
        rows, key=lambda row: _float_or_none(row.get("delta")) or 0, reverse=True
    )


def _ranked_attribute_row_for_text(
    segment: str,
    rows: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]] | None:
    text_tokens = _attribute_share_text_tokens(segment)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for index, row in enumerate(rows, start=1):
        label = _normalize_text(row.get("attribute_value"))
        label_tokens = _canonical_tokens(label)
        if not label_tokens:
            continue
        overlap = text_tokens & label_tokens
        if not overlap:
            continue
        score = len(overlap)
        if label_tokens <= text_tokens:
            score += 10
        matches.append((score, index, row))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    best_score, best_rank, best_row = matches[0]
    tied = [item for item in matches if item[0] == best_score]
    if len(tied) > 1:
        return None
    return best_rank, best_row


def _validate_attribute_rank_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    file_name = "resolved_core_comparison.csv"
    ranked_rows = _attribute_rank_rows(frames, file_name)
    match = _ranked_attribute_row_for_text(segment, ranked_rows)
    top_row = ranked_rows[0] if ranked_rows else None
    if match is None:
        return {
            "status": "warning",
            "message": "ranked attribute row not matched in recent core comparison",
            "source_file": file_name,
            "top_row": top_row,
        }

    rank, row = match
    return {
        "status": "pass" if rank == 1 else "fail",
        "source_file": file_name,
        "rank": rank,
        "row": row,
        "top_row": top_row,
        "reasons": (
            []
            if rank == 1
            else [
                (
                    "attribute is not the top-ranked delta in recent core comparison: "
                    f"rank {rank}"
                )
            ]
        ),
    }


def _attribute_rank_evidence_details(result: dict[str, Any]) -> dict[str, Any]:
    row = result.get("row")
    top_row = result.get("top_row")
    details: dict[str, Any] = {
        "source_file": result.get("source_file"),
        "rank_basis_or_share_basis": {
            "source_file": result.get("source_file"),
            "metric": "delta",
            "order": "descending",
            "claim_rank": result.get("rank"),
        },
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    if isinstance(row, dict):
        candidate = {"file": result.get("source_file"), "row": row}
        details.update(
            {
                "matched_row_keys": _candidate_row_keys(candidate),
                "expected_numeric_values": {
                    "delta": _float_or_none(row.get("delta")),
                    "pct_recent": _percent_from_fraction(row.get("pct_recent")),
                    "pct_rest": _percent_from_fraction(row.get("pct_rest")),
                },
                "package_values": _bundle_candidate_package_values(candidate),
                "denominators": _attribute_share_denominators(candidate),
            }
        )
    if isinstance(top_row, dict):
        details["top_ranked_row"] = _candidate_row_keys(
            {"file": result.get("source_file"), "row": top_row}
        )
        details["top_ranked_delta"] = _float_or_none(top_row.get("delta"))
    return details


def _bundle_absence_cohorts(segment: str) -> list[str]:
    folded = _fold_text(segment)
    if not re.search(r"\b(?:does not|do not|not|no|without)\b", folded):
        return []
    if not re.search(r"\b(?:recur|found|present|appear|appears|seen|show)\b", folded):
        return []

    cohorts: list[str] = []
    if re.search(
        r"\b(?:top[-\s]?seller|top[-\s]?sellers|top[-\s]?selling|winner|winners|winning)\b",
        folded,
    ):
        cohorts.append("top_seller")
    return _unique_texts(cohorts)


def _bundle_absence_source_files(cohort: str) -> tuple[str, ...]:
    if cohort == "top_seller":
        return (
            "top_seller_pairs.csv",
            "top_seller_triples.csv",
            "top_seller_mapped_attribute_comparison.csv",
        )
    if cohort == "recent":
        return (
            "innovation_pairs.csv",
            "innovation_triples.csv",
            "mapped_attribute_comparison.csv",
            "resolved_core_comparison.csv",
            "filter_comparison.csv",
        )
    return ()


def _candidate_occurs_in_cohort(
    candidate: dict[str, Any],
    cohort: str,
) -> bool | None:
    count = _candidate_count_for_role(candidate, cohort)
    if count is not None:
        return count > 0
    percent = _candidate_percent_for_role(candidate, cohort)
    if percent is not None:
        return percent > 0
    return None


def _evaluate_bundle_absence_claim(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    cohorts = _bundle_absence_cohorts(segment)
    if not cohorts:
        return None

    candidates = _bundle_candidates(label, frames)
    checks: list[dict[str, Any]] = []
    reasons: list[str] = []
    for cohort in cohorts:
        source_files = _bundle_absence_source_files(cohort)
        cohort_candidates = [
            candidate
            for candidate in candidates
            if candidate["file"] in source_files
            and cohort in _candidate_supported_cohort_roles(candidate)
        ]
        matched_rows: list[dict[str, Any]] = []
        unknown_rows: list[dict[str, Any]] = []
        for candidate in cohort_candidates:
            occurs = _candidate_occurs_in_cohort(candidate, cohort)
            row_details = {
                "source_file": candidate["file"],
                "matched_row_keys": _candidate_row_keys(candidate),
                "package_values": _bundle_candidate_package_values(candidate),
                "occurrence_count": _candidate_count_for_role(candidate, cohort),
                "occurrence_percent": _candidate_percent_for_role(candidate, cohort),
            }
            if occurs is None:
                unknown_rows.append(row_details)
            elif occurs:
                matched_rows.append(row_details)

        check = {
            "cohort": cohort,
            "source_files_checked": list(source_files),
            "passed": not matched_rows and not unknown_rows,
            "matched_rows": matched_rows,
            "unknown_rows": unknown_rows,
        }
        checks.append(check)
        if matched_rows:
            reasons.append(f"{cohort} absence failed: matching source row is non-zero")
        if unknown_rows:
            reasons.append(
                f"{cohort} absence unresolved: matching source row lacks occurrence fields"
            )

    return {
        "status": "fail" if reasons else "pass",
        "zero_occurrence_check": checks,
        "reasons": reasons,
    }


def discover_launch_packages(
    package_roots: Iterable[Path] | None = None,
) -> list[LaunchPackageRef]:
    """Return every launch package available under the known roots."""

    roots = tuple(package_roots or DEFAULT_LAUNCH_PACKAGE_ROOTS)
    packages: list[LaunchPackageRef] = []
    seen_dirs: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        package_dirs = {
            candidate.parent
            for file_name in _PACKAGE_REQUIRED_FILES
            for candidate in root.glob(f"**/{file_name}")
            if candidate.is_file()
        }
        for package_dir in sorted(package_dirs):
            resolved_package_dir = package_dir.resolve()
            if resolved_package_dir in seen_dirs:
                continue
            seen_dirs.add(resolved_package_dir)
            manifest = _read_optional_json(package_dir / "pack_manifest.json")
            summary = _read_optional_json(package_dir / "summary.json")
            try:
                relative_package_dir = package_dir.relative_to(root)
                path_retailer = (
                    relative_package_dir.parts[0]
                    if len(relative_package_dir.parts) > 1
                    else ""
                )
            except ValueError:
                path_retailer = ""
            packages.append(
                LaunchPackageRef(
                    package_dir=package_dir,
                    retailer=_normalize_text(manifest.get("retailer"))
                    or _normalize_text(summary.get("retailer"))
                    or _normalize_text(path_retailer),
                    category_key=_normalize_text(manifest.get("category_key"))
                    or package_dir.name,
                    category_label=_normalize_text(manifest.get("category_label"))
                    or _normalize_text(summary.get("category_label"))
                    or package_dir.name,
                )
            )
    return packages


def _split_report_retailer_suffix(report_key: str) -> tuple[str, str]:
    for suffix, retailer in _REPORT_RETAILER_SUFFIXES.items():
        if report_key.endswith(suffix):
            return report_key[: -len(suffix)], retailer
    return report_key, ""


def _normalized_category_key_from_name(value: Any) -> str:
    key = _normalize_text(value).casefold()
    base_key, _retailer_hint = _split_report_retailer_suffix(key)
    return _REPORT_PACKAGE_ALIASES.get(base_key, base_key)


def _category_name_match_score(raw_value: Any, normalized_key: str) -> int:
    candidate_key = _normalized_category_key_from_name(raw_value)
    if not candidate_key:
        return 0
    target_canonical = _canonical_text(normalized_key)
    candidate_canonical = _canonical_text(candidate_key)
    if not target_canonical or not candidate_canonical:
        return 0
    if candidate_canonical == target_canonical:
        return 6
    return 0


def _summary_report_key_for_pdf(pdf_path: Path) -> str | None:
    report_key = _normalize_text(pdf_path.stem).casefold()
    if report_key in _SUMMARY_REPORT_CHILD_BRIEFS:
        return report_key
    base_key, retailer_hint = _split_report_retailer_suffix(report_key)
    if retailer_hint == "ulta" and base_key in _SUMMARY_REPORT_CHILD_BRIEFS:
        return base_key
    return None


def _summary_report_brief_records(
    report_key: str,
    *,
    brief_roots: Iterable[Path] | None = None,
) -> list[dict[str, object]]:
    roots = tuple(brief_roots or DEFAULT_LAUNCH_BRIEF_ROOTS)
    child_refs = _SUMMARY_REPORT_CHILD_BRIEFS.get(report_key, ())
    records: list[dict[str, object]] = []
    for retailer, category_key in child_refs:
        candidate_paths = [root / retailer / f"{category_key}.md" for root in roots]
        selected_path = next(
            (path for path in candidate_paths if path.is_file()),
            candidate_paths[0] if candidate_paths else Path(f"{category_key}.md"),
        )
        records.append(
            {
                "retailer": retailer,
                "category_key": category_key,
                "path": str(selected_path.resolve()),
                "exists": selected_path.is_file(),
            }
        )
    return records


def _summary_report_resolver_details(
    pdf_path: Path,
    report_key: str,
    *,
    brief_roots: Iterable[Path] | None = None,
) -> dict[str, object]:
    child_briefs = _summary_report_brief_records(report_key, brief_roots=brief_roots)
    missing_count = sum(1 for brief in child_briefs if not brief["exists"])
    return {
        "status": "summary_report",
        "reason": "parent_summary_report",
        "pdf_path": str(pdf_path.resolve()),
        "report_key": report_key,
        "source_kind": "child_markdown_briefs",
        "child_briefs": child_briefs,
        "missing_brief_count": missing_count,
    }


def _summary_report_payload(
    pdf_path: Path,
    *,
    report_key: str,
    resolver_details: dict[str, object],
) -> dict[str, Any]:
    child_briefs = (
        resolver_details.get("child_briefs")
        if isinstance(resolver_details.get("child_briefs"), list)
        else []
    )
    unresolved = [
        {
            "status": "unresolved",
            "claim_family": "summary_report_validation",
            "claim_text": "",
            "details": {
                "message": (
                    "parent summary reports are generated from child markdown briefs; "
                    "summary-report validation cannot run until at least one child brief is available"
                )
            },
        }
    ]
    for brief in child_briefs:
        if not isinstance(brief, dict) or brief.get("exists"):
            continue
        unresolved.append(
            {
                "status": "unresolved",
                "claim_family": "summary_child_brief",
                "claim_text": "",
                "details": {
                    "message": "expected child markdown brief is missing",
                    "retailer": brief.get("retailer"),
                    "category_key": brief.get("category_key"),
                    "path": brief.get("path"),
                },
            }
        )

    return {
        "status": "not_validated",
        "report_type": "summary_report",
        "pdf_path": str(pdf_path.resolve()),
        "generated_at": datetime.now(UTC).isoformat(),
        "resolver": resolver_details,
        "summary_report": {
            "report_key": report_key,
            "source_kind": "child_markdown_briefs",
            "child_briefs": child_briefs,
        },
        "summary": {
            "verified_count": 0,
            "contradicted_count": 0,
            "partially_backed_count": 0,
            "weakly_backed_count": 0,
            "unresolved_count": len(unresolved),
            "claim_count": 0,
            "slide_count": 0,
        },
        "claims": [],
        "unresolved": unresolved,
        "reading_quality": {
            "status": "not_run",
            "summary": {
                "slide_count": 0,
                "ok_slide_count": 0,
                "warning_slide_count": 0,
                "poor_slide_count": 0,
            },
            "reasons": ["reading did not run because this is a parent summary report"],
            "flagged_slides": [],
        },
        "scope_note": (
            "This is a parent summary report. It is generated from child markdown briefs, "
            "not from one launch package, so package-level deterministic validation does "
            "not apply. Summary-report validation can run once child markdown inputs are present."
        ),
    }


def _summary_available_briefs(
    resolver_details: dict[str, object],
) -> list[dict[str, object]]:
    child_briefs = (
        resolver_details.get("child_briefs")
        if isinstance(resolver_details.get("child_briefs"), list)
        else []
    )
    return [
        brief
        for brief in child_briefs
        if isinstance(brief, dict) and bool(brief.get("exists"))
    ]


def _summary_numeric_facts(text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for match in _SUMMARY_NUMERIC_FACT_RE.finditer(_normalize_text(text)):
        kind = next(
            (name for name, value in match.groupdict().items() if value is not None),
            "",
        )
        raw = _normalize_text(match.group(0))
        if not kind or not raw:
            continue
        number_match = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
        value = (
            float(number_match.group(0).replace(",", ""))
            if number_match is not None
            else None
        )
        canonical = re.sub(r"\s+", "", raw.casefold().replace(",", ""))
        if kind == "percent" and value is not None:
            canonical = f"percent:{value:g}"
        elif kind == "multiplier" and value is not None:
            canonical = f"multiplier:{value:g}"
        elif kind in {"count", "rank", "currency"} and value is not None:
            canonical = f"{kind}:{value:g}"
        elif kind == "ratio":
            canonical = "ratio:" + re.sub(r"\s+", "", raw.replace(",", ""))
        facts.append(
            {
                "kind": kind,
                "raw": raw,
                "canonical": canonical,
                "value": value,
            }
        )
    unique: list[dict[str, object]] = []
    seen: set[str] = set()
    for fact in facts:
        key = str(fact["canonical"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(fact)
    return unique


def _summary_fact_matches(
    claim_fact: dict[str, object],
    evidence_fact: dict[str, object],
) -> bool:
    if claim_fact.get("canonical") == evidence_fact.get("canonical"):
        return True
    if claim_fact.get("kind") != evidence_fact.get("kind"):
        return False
    claim_value = _float_or_none(claim_fact.get("value"))
    evidence_value = _float_or_none(evidence_fact.get("value"))
    if claim_value is None or evidence_value is None:
        return False
    kind = _normalize_text(claim_fact.get("kind"))
    if kind == "percent":
        return abs(claim_value - evidence_value) <= 0.55
    if kind == "multiplier":
        return abs(claim_value - evidence_value) <= 0.05
    return abs(claim_value - evidence_value) < 0.00001


def _summary_content_tokens(text: str) -> set[str]:
    return {
        token
        for token in _token_list(text)
        if len(token) >= 3 and token not in _SUMMARY_TEXT_STOPWORDS
    }


def _summary_brief_evidence_units(
    child_briefs: list[dict[str, object]],
) -> list[dict[str, object]]:
    units: list[dict[str, object]] = []
    for brief in child_briefs:
        path = Path(str(brief.get("path") or ""))
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("Could not read summary child brief %s: %s", path, exc)
            continue
        line_index = 0
        for line in text.splitlines():
            cleaned = _normalize_text(re.sub(r"^[#*\-\s>`]+", "", line))
            if not cleaned:
                continue
            for segment in _split_text_units(cleaned):
                units.append(
                    {
                        "text": segment,
                        "retailer": brief.get("retailer"),
                        "category_key": brief.get("category_key"),
                        "path": brief.get("path"),
                        "line_index": line_index,
                        "tokens": _summary_content_tokens(segment),
                        "numeric_facts": _summary_numeric_facts(segment),
                    }
                )
                line_index += 1
    return units


def _best_summary_evidence(
    claim_text: str,
    evidence_units: list[dict[str, object]],
    *,
    claim_facts: list[dict[str, object]],
) -> dict[str, object] | None:
    claim_tokens = _summary_content_tokens(claim_text)
    best: tuple[float, dict[str, object]] | None = None
    for unit in evidence_units:
        unit_tokens = (
            unit.get("tokens") if isinstance(unit.get("tokens"), set) else set()
        )
        overlap_count = len(claim_tokens & unit_tokens)
        overlap_ratio = overlap_count / max(1, len(claim_tokens))
        unit_facts = (
            unit.get("numeric_facts")
            if isinstance(unit.get("numeric_facts"), list)
            else []
        )
        matched_fact_count = sum(
            1
            for claim_fact in claim_facts
            if any(
                isinstance(evidence_fact, dict)
                and _summary_fact_matches(claim_fact, evidence_fact)
                for evidence_fact in unit_facts
            )
        )
        score = overlap_ratio + (matched_fact_count * 0.5) + (overlap_count * 0.02)
        if best is None or score > best[0]:
            best = (score, unit)
    return best[1] if best is not None else None


def _summary_fact_support(
    claim_facts: list[dict[str, object]],
    evidence_units: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    matched: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    evidence_facts = [
        evidence_fact
        for unit in evidence_units
        for evidence_fact in (
            unit.get("numeric_facts")
            if isinstance(unit.get("numeric_facts"), list)
            else []
        )
        if isinstance(evidence_fact, dict)
    ]
    for claim_fact in claim_facts:
        if any(
            _summary_fact_matches(claim_fact, evidence_fact)
            for evidence_fact in evidence_facts
        ):
            matched.append(claim_fact)
        else:
            missing.append(claim_fact)
    return matched, missing


def _summary_evidence_details(
    evidence: dict[str, object] | None,
) -> dict[str, object]:
    if not evidence:
        return {}
    return {
        "supporting_brief": {
            "retailer": evidence.get("retailer"),
            "category_key": evidence.get("category_key"),
            "path": evidence.get("path"),
            "text": _truncate_text(evidence.get("text"), limit=220),
        }
    }


def _evaluate_summary_unit(
    *,
    slide: dict[str, Any],
    unit: dict[str, Any],
    evidence_units: list[dict[str, object]],
) -> dict[str, Any] | None:
    text = _normalize_text(unit.get("text"))
    if not text or not _looks_claim_like_text(text, block_type=unit.get("block_type")):
        return None

    claim_facts = _summary_numeric_facts(text)
    best_evidence = _best_summary_evidence(
        text,
        evidence_units,
        claim_facts=claim_facts,
    )
    evidence_details = _summary_evidence_details(best_evidence)
    if claim_facts:
        matched_facts, missing_facts = _summary_fact_support(
            claim_facts, evidence_units
        )
        details = {
            **evidence_details,
            "observed_values": {"numeric_facts": claim_facts},
            "matched_numeric_facts": matched_facts,
            "missing_numeric_facts": missing_facts,
        }
        if missing_facts:
            details["reasons"] = [
                "one or more numeric facts in the parent PDF were not found in child markdown briefs"
            ]
            return _claim_result(
                status="contradicted",
                claim_family="summary_numeric_claim",
                claim_text=text,
                slide=slide,
                unit=unit,
                details=details,
            )
        best_tokens = (
            best_evidence.get("tokens")
            if isinstance(best_evidence, dict)
            and isinstance(best_evidence.get("tokens"), set)
            else set()
        )
        overlap_count = len(_summary_content_tokens(text) & best_tokens)
        return _claim_result(
            status="verified" if overlap_count >= 2 else "weakly_backed",
            claim_family="summary_numeric_claim",
            claim_text=text,
            slide=slide,
            unit=unit,
            details=details,
        )

    claim_tokens = _summary_content_tokens(text)
    evidence_tokens = (
        best_evidence.get("tokens")
        if isinstance(best_evidence, dict)
        and isinstance(best_evidence.get("tokens"), set)
        else set()
    )
    overlap_count = len(claim_tokens & evidence_tokens)
    overlap_ratio = overlap_count / max(1, len(claim_tokens))
    if overlap_count >= 5 and overlap_ratio >= 0.35:
        return _claim_result(
            status="weakly_backed",
            claim_family="summary_qualitative_claim",
            claim_text=text,
            slide=slide,
            unit=unit,
            details={
                **evidence_details,
                "reasons": [
                    "qualitative parent claim has strong lexical support in a child markdown brief"
                ],
            },
        )
    return _claim_result(
        status="unresolved",
        claim_family="summary_qualitative_claim",
        claim_text=text,
        slide=slide,
        unit=unit,
        details={
            **evidence_details,
            "message": "qualitative parent claim was not deterministically matched to child markdown briefs",
        },
    )


def _validate_summary_report_pdf(
    pdf_path: Path,
    *,
    report_key: str,
    resolver_details: dict[str, object],
    lang: str,
    include_bboxes: bool,
    refresh_reading_cache: bool,
) -> dict[str, Any]:
    available_briefs = _summary_available_briefs(resolver_details)
    if not available_briefs:
        return _summary_report_payload(
            pdf_path,
            report_key=report_key,
            resolver_details=resolver_details,
        )

    reading_payload = build_pdf_reading_payload_for_validation(
        pdf_path,
        lang=lang,
        include_bboxes=include_bboxes,
        force=refresh_reading_cache,
    )
    reading_quality = _assess_reading_quality(reading_payload)
    evidence_units = _summary_brief_evidence_units(available_briefs)

    claims: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    non_claims: list[dict[str, Any]] = []
    mapping_issues: list[dict[str, Any]] = []
    image_regions: list[dict[str, Any]] = []
    child_briefs = (
        resolver_details.get("child_briefs")
        if isinstance(resolver_details.get("child_briefs"), list)
        else []
    )
    for brief in child_briefs:
        if not isinstance(brief, dict) or brief.get("exists"):
            continue
        unresolved.append(
            {
                "status": "unresolved",
                "claim_family": "summary_child_brief",
                "claim_text": "",
                "details": {
                    "message": "expected child markdown brief is missing",
                    "retailer": brief.get("retailer"),
                    "category_key": brief.get("category_key"),
                    "path": brief.get("path"),
                },
            }
        )

    if not evidence_units:
        unresolved.append(
            {
                "status": "unresolved",
                "claim_family": "summary_child_brief",
                "claim_text": "",
                "details": {
                    "message": "available child markdown briefs did not contain usable text"
                },
            }
        )

    slides = (
        reading_payload.get("slides")
        if isinstance(reading_payload.get("slides"), list)
        else []
    )
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        seen_unit_keys: set[tuple[str, str | None, str | None]] = set()
        for unit in _iter_slide_units(slide):
            unit_text = _normalize_text(unit.get("text"))
            unit_key = (
                _canonical_text(unit_text),
                _normalize_text(unit.get("block_id")) or None,
                _normalize_text(unit.get("source_kind")) or None,
            )
            if not unit_text or unit_key in seen_unit_keys:
                continue
            seen_unit_keys.add(unit_key)
            result = _evaluate_summary_unit(
                slide=slide,
                unit=unit,
                evidence_units=evidence_units,
            )
            if result is None:
                continue
            if result["status"] == "unresolved":
                unresolved.append(result)
            else:
                claims.append(result)

        figure_regions = (
            slide.get("figure_regions")
            if isinstance(slide.get("figure_regions"), list)
            else []
        )
        for region_index, _region in enumerate(figure_regions):
            image_regions.append(_image_region_result(slide, region_index))

    claims, unresolved = _resolve_deck_level_emerging_lane_summaries(
        claims,
        unresolved,
    )

    verified_count = sum(1 for claim in claims if claim["status"] == "verified")
    contradicted_count = sum(1 for claim in claims if claim["status"] == "contradicted")
    partially_backed_count = sum(
        1 for claim in claims if claim["status"] == "partially_backed"
    )
    weakly_backed_count = sum(
        1 for claim in claims if claim["status"] == "weakly_backed"
    )
    unresolved_count = len(unresolved)

    status = "pass"
    if contradicted_count:
        status = "fail"
    elif (
        unresolved_count
        or partially_backed_count
        or weakly_backed_count
        or reading_quality["status"] != "read_ok"
    ):
        status = "pass_with_warnings"

    return {
        "status": status,
        "report_type": "summary_report",
        "pdf_path": str(pdf_path.resolve()),
        "generated_at": datetime.now(UTC).isoformat(),
        "resolver": resolver_details,
        "summary_report": {
            "report_key": report_key,
            "source_kind": "child_markdown_briefs",
            "child_briefs": child_briefs,
            "available_brief_count": len(available_briefs),
            "evidence_unit_count": len(evidence_units),
        },
        "summary": {
            "verified_count": verified_count,
            "contradicted_count": contradicted_count,
            "partially_backed_count": partially_backed_count,
            "weakly_backed_count": weakly_backed_count,
            "unresolved_count": unresolved_count,
            "image_region_count": len(image_regions),
            "claim_count": len(claims),
            "slide_count": len(slides),
        },
        "reading_quality": reading_quality,
        "claims": claims,
        "unresolved": unresolved,
        "image_regions": image_regions,
        "scope_note": (
            "This validator checks parent summary-report claims against child markdown briefs "
            "using the same PDF layout, OCR, and merged slide-understanding pipeline as the "
            "slide editor. Numeric parent claims must trace to child brief numbers. "
            "Qualitative synthesis is marked weakly backed only when deterministic text overlap "
            "is strong; otherwise it is left unresolved. Image regions are exposed separately "
            "without OCR interpretation."
        ),
    }


def resolve_launch_package_for_pdf(
    pdf_path: Path,
    *,
    package_roots: Iterable[Path] | None = None,
) -> tuple[LaunchPackageRef | None, dict[str, Any]]:
    """Resolve one PDF deck to the best matching launch package."""

    roots = tuple(package_roots or DEFAULT_LAUNCH_PACKAGE_ROOTS)
    packages = discover_launch_packages(roots)
    report_key = _normalize_text(pdf_path.stem).casefold()
    base_key, retailer_hint = _split_report_retailer_suffix(report_key)
    normalized_key = _normalized_category_key_from_name(base_key)

    scored: list[tuple[int, LaunchPackageRef]] = []
    for package in packages:
        package_retailer = _canonical_text(package.retailer)
        if (
            retailer_hint
            and package_retailer
            and package_retailer != _canonical_text(retailer_hint)
        ):
            continue
        category_score = max(
            _category_name_match_score(package.category_key, normalized_key),
            _category_name_match_score(package.package_dir.name, normalized_key),
            _category_name_match_score(package.category_label, normalized_key),
        )
        if category_score == 0:
            continue
        score = category_score
        if retailer_hint and package_retailer == _canonical_text(retailer_hint):
            score += 3
        scored.append((score, package))

    if not scored:
        return None, {
            "status": "unresolved",
            "reason": "no_matching_package",
            "pdf_path": str(pdf_path.resolve()),
            "report_key": report_key,
            "normalized_key": normalized_key,
            "retailer_hint": retailer_hint or None,
            "package_roots": [
                {
                    "path": str(root.expanduser().resolve()),
                    "exists": root.expanduser().exists(),
                }
                for root in roots
            ],
            "discovered_package_count": len(packages),
            "discovered_packages": [
                {
                    "path": str(package.package_dir.resolve()),
                    "retailer": package.retailer,
                    "category_key": package.category_key,
                    "category_label": package.category_label,
                }
                for package in packages[:12]
            ],
        }

    scored.sort(
        key=lambda item: (
            item[0],
            str(item[1].package_dir.parent),
            str(item[1].package_dir),
        ),
        reverse=True,
    )
    best_score, best_package = scored[0]
    competing = [package for score, package in scored if score == best_score]
    return best_package, {
        "status": "matched" if len(competing) == 1 else "heuristic_match",
        "pdf_path": str(pdf_path.resolve()),
        "report_key": report_key,
        "normalized_key": normalized_key,
        "retailer_hint": retailer_hint or None,
        "package_dir": str(best_package.package_dir.resolve()),
        "package_retailer": best_package.retailer,
        "package_category_key": best_package.category_key,
        "package_category_label": best_package.category_label,
        "candidate_count": len(scored),
        "top_score": best_score,
    }


def load_launch_package_data(package_dir: Path) -> LaunchPackageData:
    """Load one launch package from disk."""

    manifest = _read_optional_json(package_dir / "pack_manifest.json")
    summary = _read_optional_json(package_dir / "summary.json")
    content_fingerprint = _package_content_fingerprint(package_dir)
    frames = _load_package_frames(package_dir)
    calculation_result = calculate_package_frames("launch", frames)
    frames = {
        **frames,
        **{
            file_name: calculated_frame
            for file_name, calculated_frame in calculation_result.frames.items()
            if frames.get(file_name) is None or frames[file_name].is_empty()
        },
    }

    bundle_labels: list[str] = []
    for file_name, column_name in (
        ("top_seller_pairs.csv", "bundle_label"),
        ("top_seller_triples.csv", "bundle_label"),
        ("innovation_pairs.csv", "bundle_label"),
        ("innovation_triples.csv", "bundle_label"),
        ("top_seller_mapped_attribute_comparison.csv", "attribute_value"),
        ("mapped_attribute_comparison.csv", "attribute_value"),
        ("resolved_core_comparison.csv", "attribute_value"),
        ("filter_comparison.csv", "filter_value"),
    ):
        df = frames[file_name]
        if df.is_empty() or column_name not in df.columns:
            continue
        bundle_labels.extend(
            _normalize_text(value)
            for value in df.get_column(column_name).drop_nulls().to_list()
            if _normalize_text(value)
        )

    deduped_bundle_labels: list[str] = []
    seen_bundle_keys: set[str] = set()
    for label in bundle_labels:
        key = _bundle_label_key(label)
        if key in seen_bundle_keys:
            continue
        seen_bundle_keys.add(key)
        deduped_bundle_labels.append(label)

    brand_names: list[str] = []
    brand_df = frames["top_seller_brand_comparison.csv"]
    if not brand_df.is_empty() and "brand" in brand_df.columns:
        brand_names = _unique_texts(brand_df.get_column("brand").drop_nulls().to_list())

    product_names: list[str] = []
    for file_name in ("recent_products.csv", "top_seller_products.csv"):
        df = frames[file_name]
        if df.is_empty() or "product_name" not in df.columns:
            continue
        product_names.extend(
            _normalize_text(value)
            for value in df.get_column("product_name").drop_nulls().to_list()
            if _normalize_text(value)
        )

    ref = LaunchPackageRef(
        package_dir=package_dir,
        retailer=_normalize_text(manifest.get("retailer"))
        or _normalize_text(summary.get("retailer")),
        category_key=_normalize_text(manifest.get("category_key")) or package_dir.name,
        category_label=_normalize_text(manifest.get("category_label"))
        or _normalize_text(summary.get("category_label"))
        or package_dir.name,
    )
    return LaunchPackageData(
        ref=ref,
        manifest=manifest,
        summary=summary,
        content_fingerprint=content_fingerprint,
        frames=frames,
        calculation_summary=calculation_result.summaries,
        bundle_labels=tuple(deduped_bundle_labels),
        brand_names=tuple(brand_names),
        product_names=tuple(_unique_texts(product_names)),
    )


def build_pdf_ocr_payload_for_validation(
    pdf_path: Path,
    *,
    lang: str = "eng",
    include_bboxes: bool = True,
    force: bool = False,
) -> dict[str, object]:
    """Backward-compatible alias for the full slide-editor reading payload."""

    return build_pdf_reading_payload_for_validation(
        pdf_path,
        lang=lang,
        include_bboxes=include_bboxes,
        force=force,
    )


def _canonicalize_analysis_block(block: dict[str, Any]) -> dict[str, Any]:
    canonical = {
        "block_id": _normalize_text(block.get("blockId") or block.get("block_id")),
        "type": _normalize_text(block.get("type") or block.get("detectedType"))
        or "unknown",
        "group_id": _normalize_text(block.get("groupId") or block.get("group_id")),
        "group_kind": _normalize_text(
            block.get("groupKind") or block.get("group_kind")
        ),
        "parent_id": _normalize_text(block.get("parentId") or block.get("parent_id")),
        "text": _normalize_text(block.get("text")),
        "items": [
            _normalize_text(item)
            for item in (
                block.get("items") if isinstance(block.get("items"), list) else []
            )
            if _normalize_text(item)
        ],
        "visual_items": [
            _normalize_text(item)
            for item in (
                block.get("visualItems")
                if isinstance(block.get("visualItems"), list)
                else (
                    block.get("visual_items")
                    if isinstance(block.get("visual_items"), list)
                    else []
                )
            )
            if _normalize_text(item)
        ],
        "visual_text": _normalize_text(
            block.get("visualText") or block.get("visual_text")
        ),
    }
    bbox = block.get("bbox")
    if isinstance(bbox, dict):
        canonical["bbox"] = bbox
    confidence = _float_or_none(block.get("confidence"))
    if confidence is not None:
        canonical["confidence"] = confidence
    audit_status = _normalize_text(
        block.get("auditStatus") or block.get("audit_status")
    )
    if audit_status:
        canonical["audit_status"] = audit_status.casefold()
    visual_status = _normalize_text(
        block.get("visualStatus") or block.get("visual_status")
    )
    if visual_status:
        canonical["visual_status"] = visual_status.casefold()
    visual_confidence = _float_or_none(
        block.get("visualConfidence") or block.get("visual_confidence")
    )
    if visual_confidence is not None:
        canonical["visual_confidence"] = visual_confidence
    table_model = block.get("tableModel")
    if not isinstance(table_model, dict):
        table_model = block.get("table_model")
    if isinstance(table_model, dict):
        canonical["table_model"] = table_model
    return canonical


def _canonicalize_analysis_slide(slide: dict[str, Any]) -> dict[str, Any]:
    blocks = [
        _canonicalize_analysis_block(block)
        for block in (
            slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
        )
        if isinstance(block, dict)
    ]
    title_text = _normalize_text(slide.get("titleText") or slide.get("title_text"))
    bullet_texts = [
        _normalize_text(item)
        for item in (
            slide.get("bulletTexts")
            if isinstance(slide.get("bulletTexts"), list)
            else (
                slide.get("bullet_texts")
                if isinstance(slide.get("bullet_texts"), list)
                else []
            )
        )
        if _normalize_text(item)
    ]
    figure_regions = [
        region
        for region in (
            slide.get("figureRegions")
            if isinstance(slide.get("figureRegions"), list)
            else (
                slide.get("figure_regions")
                if isinstance(slide.get("figure_regions"), list)
                else []
            )
        )
        if isinstance(region, dict)
    ]
    ocr_parts = [title_text, *bullet_texts]
    for block in blocks:
        if _normalize_text(block.get("text")):
            ocr_parts.append(_normalize_text(block["text"]))
        ocr_parts.extend(
            _normalize_text(item)
            for item in (
                block.get("items") if isinstance(block.get("items"), list) else []
            )
            if _normalize_text(item)
        )
    return {
        "slide_id": _normalize_text(slide.get("slideId") or slide.get("slide_id")),
        "slide_number": _int_or_none(
            slide.get("slideNumber") or slide.get("slide_number")
        ),
        "page_number": _int_or_none(
            slide.get("pageNumber") or slide.get("page_number")
        ),
        "title_text": title_text,
        "bullet_texts": bullet_texts,
        "figure_regions": figure_regions,
        "blocks": blocks,
        "ocr_text": _normalize_text(" ".join(part for part in ocr_parts if part)),
    }


def _canonicalize_analysis_payload(payload: dict[str, Any]) -> dict[str, object]:
    return {
        "deck_id": _normalize_text(payload.get("deckId") or payload.get("deck_id")),
        "lang": _normalize_text(payload.get("lang")) or "eng",
        "generated_at": _normalize_text(
            payload.get("generatedAt") or payload.get("generated_at")
        )
        or datetime.now(UTC).isoformat(),
        "slides": [
            _canonicalize_analysis_slide(slide)
            for slide in (
                payload.get("slides") if isinstance(payload.get("slides"), list) else []
            )
            if isinstance(slide, dict)
        ],
    }


def _slide_match_keys(slide: dict[str, Any], index: int) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    slide_id = _normalize_text(slide.get("slideId") or slide.get("slide_id"))
    if slide_id:
        keys.append(("id", slide_id))
    slide_number = _int_or_none(slide.get("slideNumber") or slide.get("slide_number"))
    if slide_number is not None:
        keys.append(("number", str(slide_number)))
    page_number = _int_or_none(slide.get("pageNumber") or slide.get("page_number"))
    if page_number is not None:
        keys.append(("page", str(page_number)))
    keys.append(("index", str(index)))
    return keys


def _stage_slide_lookup(
    payload: dict[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        for key in _slide_match_keys(slide, index):
            lookup.setdefault(key, slide)
    return lookup


def _matching_stage_slide(
    slide: dict[str, Any],
    index: int,
    lookup: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    for key in _slide_match_keys(slide, index):
        matched = lookup.get(key)
        if matched is not None:
            return matched
    return None


def _unique_normalized_texts(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    texts: list[str] = []
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        key = _canonical_text(text)
        if not key or key in seen:
            continue
        seen.add(key)
        texts.append(text)
    return texts


def _collect_text_values(value: Any, *, text_keys: set[str]) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_text(key).casefold()
            if normalized_key in text_keys:
                if isinstance(child, str):
                    texts.extend(child.splitlines())
                elif isinstance(child, list):
                    texts.extend(item for item in child if isinstance(item, str))
                continue
            if isinstance(child, (dict, list)):
                texts.extend(_collect_text_values(child, text_keys=text_keys))
    elif isinstance(value, list):
        for child in value:
            texts.extend(_collect_text_values(child, text_keys=text_keys))
    return texts


def _significant_reading_texts(values: Iterable[str]) -> list[str]:
    significant: list[str] = []
    for text in _unique_normalized_texts(values):
        tokens = _token_list(text)
        if (
            len(_canonical_text(text)) >= _READING_COMPLETENESS_MIN_CANONICAL_CHARS
            and len(tokens) >= _READING_COMPLETENESS_MIN_TOKENS
        ):
            significant.append(text)
    return significant


def _ocr_slide_texts(slide: dict[str, Any] | None) -> list[str]:
    if not isinstance(slide, dict):
        return []
    texts: list[str] = []
    lines = slide.get("lines") if isinstance(slide.get("lines"), list) else []
    for line in lines:
        if isinstance(line, dict):
            texts.append(_normalize_text(line.get("text")))
        elif isinstance(line, str):
            texts.append(line)
    blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    for block in blocks:
        if isinstance(block, dict):
            texts.extend(
                _collect_text_values(block, text_keys={"text", "ocrtext", "ocr_text"})
            )
    if not texts:
        texts.extend(
            _collect_text_values(slide, text_keys={"text", "ocrtext", "ocr_text"})
        )
    return _significant_reading_texts(texts)


def _analysis_slide_text(slide: dict[str, Any]) -> str:
    text_keys = {
        "text",
        "items",
        "visualtext",
        "visual_text",
        "visualitems",
        "visual_items",
        "titletext",
        "title_text",
        "bullettexts",
        "bullet_texts",
        "ocrtext",
        "ocr_text",
    }
    return _normalize_text(" ".join(_collect_text_values(slide, text_keys=text_keys)))


def _analysis_text_unit_count(slide: dict[str, Any]) -> int:
    units = _iter_slide_units(slide)
    return sum(1 for unit in units if _normalize_text(unit.get("text")))


def _layout_text_region_count(slide: dict[str, Any] | None) -> int:
    if not isinstance(slide, dict):
        return 0
    regions = _collect_text_values(
        slide,
        text_keys={
            "text",
            "titletext",
            "title_text",
            "bullettexts",
            "bullet_texts",
            "ocrtext",
            "ocr_text",
        },
    )
    return len(_significant_reading_texts(regions))


def _text_is_preserved(source_text: str, analysis_text: str) -> bool:
    source_canonical = _canonical_text(source_text)
    analysis_canonical = _canonical_text(analysis_text)
    if not source_canonical:
        return True
    if source_canonical in analysis_canonical:
        return True

    source_tokens = _token_list(source_text)
    if not source_tokens:
        return True
    analysis_tokens = set(_token_list(analysis_text))
    matched_count = sum(1 for token in source_tokens if token in analysis_tokens)
    token_ratio = matched_count / len(source_tokens)
    source_numbers = re.findall(r"\d[\d,]*(?:\.\d+)?%?", source_text)
    return token_ratio >= 0.80 and all(
        _canonical_text(number) in analysis_canonical for number in source_numbers
    )


def _slide_completeness_status(
    reasons: list[str], missing_count: int, total_count: int
) -> str:
    if not reasons:
        return "read_ok"
    missing_ratio = missing_count / total_count if total_count else 0.0
    if (
        missing_count >= _READING_COMPLETENESS_POOR_MISSING_COUNT
        and missing_ratio >= _READING_COMPLETENESS_POOR_MISSING_RATIO
    ):
        return "read_poor"
    return "read_warning"


def _build_reading_completeness_audit(
    *,
    layout_payload: dict[str, Any] | None,
    ocr_payload: dict[str, Any] | None,
    analysis_payload: dict[str, Any],
) -> dict[str, Any]:
    """Check whether layout/OCR evidence survived into slide analysis text."""

    slides = (
        analysis_payload.get("slides")
        if isinstance(analysis_payload.get("slides"), list)
        else []
    )
    if not isinstance(ocr_payload, dict):
        return {
            "status": "not_available",
            "summary": {
                "slide_count": len(slides),
                "flagged_slide_count": 0,
                "missing_ocr_line_count": 0,
                "layout_available": isinstance(layout_payload, dict),
                "ocr_available": False,
            },
            "reasons": ["OCR stage artifact was not available for completeness audit"],
            "flagged_slides": [],
        }

    stage_reasons: list[str] = []
    if not isinstance(layout_payload, dict):
        stage_reasons.append(
            "layout stage artifact was not available for completeness audit"
        )

    layout_lookup = _stage_slide_lookup(layout_payload)
    ocr_lookup = _stage_slide_lookup(ocr_payload)
    flagged_slides: list[dict[str, Any]] = []
    missing_ocr_line_count = 0
    layout_text_region_count = 0
    analysis_text_unit_count = 0
    ocr_line_count = 0

    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        ocr_slide = _matching_stage_slide(slide, index, ocr_lookup)
        layout_slide = _matching_stage_slide(slide, index, layout_lookup)
        ocr_texts = _ocr_slide_texts(ocr_slide)
        analysis_text = _analysis_slide_text(slide)
        layout_regions = _layout_text_region_count(layout_slide)
        analysis_units = _analysis_text_unit_count(slide)
        missing_texts = [
            text for text in ocr_texts if not _text_is_preserved(text, analysis_text)
        ]
        slide_reasons: list[str] = []

        if ocr_slide is None:
            slide_reasons.append("OCR stage did not contain a matching slide")
        elif not ocr_texts and layout_regions:
            slide_reasons.append(
                "layout detected text-like regions, but OCR yielded no significant text"
            )
        elif missing_texts:
            missing_ratio = len(missing_texts) / len(ocr_texts)
            if missing_ratio >= _READING_COMPLETENESS_WARNING_MISSING_RATIO:
                slide_reasons.append(
                    f"{len(missing_texts)} OCR text line(s) were not preserved "
                    "in slide analysis"
                )

        if layout_payload is not None and layout_slide is None:
            slide_reasons.append("layout stage did not contain a matching slide")

        status = _slide_completeness_status(
            slide_reasons,
            missing_count=len(missing_texts),
            total_count=len(ocr_texts),
        )
        if status != "read_ok":
            flagged_slides.append(
                {
                    "slide_number": slide.get("slide_number"),
                    "slide_id": slide.get("slide_id"),
                    "status": status,
                    "ocr_line_count": len(ocr_texts),
                    "missing_ocr_line_count": len(missing_texts),
                    "layout_text_region_count": layout_regions,
                    "analysis_text_unit_count": analysis_units,
                    "missing_ocr_samples": missing_texts[:3],
                    "reasons": slide_reasons,
                }
            )

        missing_ocr_line_count += len(missing_texts)
        layout_text_region_count += layout_regions
        analysis_text_unit_count += analysis_units
        ocr_line_count += len(ocr_texts)

    poor_slides = [
        slide for slide in flagged_slides if slide.get("status") == "read_poor"
    ]
    status = "read_ok"
    reasons = ["layout/OCR text was preserved in slide analysis"]
    if poor_slides:
        status = "read_poor"
        reasons = [f"{len(poor_slides)} slide(s) lost substantial OCR text"]
    elif flagged_slides:
        status = "read_warning"
        reasons = [f"{len(flagged_slides)} slide(s) showed stage-to-stage reading gaps"]
    elif stage_reasons:
        status = "read_warning"
        reasons = stage_reasons

    return {
        "status": status,
        "summary": {
            "slide_count": len(slides),
            "flagged_slide_count": len(flagged_slides),
            "missing_ocr_line_count": missing_ocr_line_count,
            "ocr_line_count": ocr_line_count,
            "layout_text_region_count": layout_text_region_count,
            "analysis_text_unit_count": analysis_text_unit_count,
            "layout_available": isinstance(layout_payload, dict),
            "ocr_available": True,
        },
        "reasons": reasons,
        "flagged_slides": flagged_slides,
    }


def _attach_reading_completeness_audit(
    analysis_payload: dict[str, object],
    *,
    layout_payload: dict[str, Any] | None,
    ocr_payload: dict[str, Any] | None,
) -> dict[str, object]:
    analysis_payload["reading_completeness"] = _build_reading_completeness_audit(
        layout_payload=layout_payload,
        ocr_payload=ocr_payload,
        analysis_payload=analysis_payload,
    )
    return analysis_payload


def _reading_cache_root_for_pdf(pdf_path: Path) -> Path:
    return pdf_path.resolve().parent / _READING_CACHE_DIRNAME


def _reading_cache_deck_id(pdf_path: Path) -> str:
    return pdf_path.stem.strip() or "launch-report"


def _reading_cache_deck_path(pdf_path: Path) -> Path:
    return _reading_cache_root_for_pdf(pdf_path) / _reading_cache_deck_id(pdf_path)


def _reading_cache_meta_path(pdf_path: Path) -> Path:
    return _reading_cache_deck_path(pdf_path) / _READING_CACHE_META_FILENAME


def _pdf_content_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _build_reading_cache_meta(
    pdf_path: Path,
    *,
    lang: str,
    include_bboxes: bool,
    source_sha256: str,
) -> dict[str, object]:
    stat_result = pdf_path.stat()
    return {
        "pipeline_version": _READING_CACHE_PIPELINE_VERSION,
        "source_pdf": str(pdf_path.resolve()),
        "source_size": int(stat_result.st_size),
        "source_mtime_ns": int(stat_result.st_mtime_ns),
        "source_sha256": source_sha256,
        "lang": lang,
        "include_bboxes": bool(include_bboxes),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _read_reading_cache_meta(pdf_path: Path) -> dict[str, object] | None:
    cache_meta_path = _reading_cache_meta_path(pdf_path)
    return _read_optional_json(cache_meta_path)


def _reading_cache_is_current(
    meta: dict[str, object] | None,
    pdf_path: Path,
    *,
    lang: str,
    include_bboxes: bool,
    source_sha256: str,
) -> bool:
    return (
        _reading_cache_stale_reason(
            meta,
            pdf_path,
            lang=lang,
            include_bboxes=include_bboxes,
            source_sha256=source_sha256,
        )
        is None
    )


def _reading_cache_stale_reason(
    meta: dict[str, object] | None,
    pdf_path: Path,
    *,
    lang: str,
    include_bboxes: bool,
    source_sha256: str,
) -> str | None:
    if not isinstance(meta, dict):
        return "missing_cache_meta"
    cached_hash = _normalize_text(meta.get("source_sha256"))
    if not cached_hash:
        return "missing_source_hash"
    if cached_hash != source_sha256:
        return "source_pdf_hash_changed"
    if _normalize_text(meta.get("lang")) != _normalize_text(lang):
        return "language_changed"
    if bool(meta.get("include_bboxes")) is not bool(include_bboxes):
        return "bbox_setting_changed"
    return None


def build_pdf_reading_payload_for_validation(
    pdf_path: Path,
    *,
    lang: str = "eng",
    include_bboxes: bool = True,
    force: bool = False,
) -> dict[str, object]:
    """Build the same layout-plus-understanding payload used by the slide editor."""

    from fastapi import HTTPException

    from modules.slides.api import (
        _build_slide_analysis_payload,
        _normalize_layout_payload,
        _render_pdf_deck,
    )
    from src.slides.layout_service import build_deck_layout_payload
    from src.slides.ocr_payload import normalize_ocr_payload
    from src.slides.ocr_service import build_deck_ocr_payload
    from src.slides.storage import DeckStorage

    deck_id = _reading_cache_deck_id(pdf_path)
    reader_started_at = time.perf_counter()
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Unable to read PDF {pdf_path}.") from exc
    source_sha256 = _pdf_content_sha256(pdf_bytes)

    cache_root = _reading_cache_root_for_pdf(pdf_path)
    cache_root.mkdir(parents=True, exist_ok=True)
    storage = DeckStorage(cache_root)
    deck_path = storage.root / deck_id
    cache_meta = _read_reading_cache_meta(pdf_path)
    cache_stale_reason = _reading_cache_stale_reason(
        cache_meta,
        pdf_path,
        lang=lang,
        include_bboxes=include_bboxes,
        source_sha256=source_sha256,
    )
    if force:
        LOGGER.info(
            "%s reading cache refresh requested; rebuilding mapped/OCR understanding",
            pdf_path.name,
        )
    elif cache_stale_reason is None:
        cached_analysis = storage.load_slide_analysis_payload(deck_id)
        if isinstance(cached_analysis, dict):
            cached_pipeline_version = _int_or_none(cache_meta.get("pipeline_version"))
            if cached_pipeline_version != _READING_CACHE_PIPELINE_VERSION:
                LOGGER.info(
                    "%s reading cache was built with pipeline version %s; reusing it "
                    "because the PDF content hash is unchanged. Use "
                    "--refresh-reading-cache to rebuild mapped/OCR understanding.",
                    pdf_path.name,
                    (
                        cached_pipeline_version
                        if cached_pipeline_version is not None
                        else "unknown"
                    ),
                )
            LOGGER.info(
                "Using cached PDF reading artifacts for %s; validation will run "
                "without rebuilding mapped/OCR understanding",
                pdf_path.name,
            )
            canonical_analysis = _canonicalize_analysis_payload(cached_analysis)
            return _attach_reading_completeness_audit(
                canonical_analysis,
                layout_payload=storage.load_layout_payload(deck_id),
                ocr_payload=storage.load_ocr_payload(deck_id),
            )
        LOGGER.info(
            "%s reading cache metadata matched, but cached slide analysis is missing; "
            "rebuilding mapped/OCR understanding",
            pdf_path.name,
        )
    else:
        LOGGER.info(
            "%s reading cache miss (%s); rebuilding mapped/OCR understanding",
            pdf_path.name,
            cache_stale_reason,
        )

    if deck_path.exists():
        shutil.rmtree(deck_path)

    LOGGER.info(
        "Building PDF reading artifacts for %s; cache=%s",
        pdf_path.name,
        deck_path,
    )
    render_started_at = time.perf_counter()
    try:
        _render_pdf_deck(
            deck_id,
            deck_path,
            pdf_bytes,
            storage,
            prompt_style="uniform",
            owner_email=None,
            shared_with=[],
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Invalid PDF."
        raise ValueError(detail) from exc
    LOGGER.info(
        "%s render finished in %.1fs",
        pdf_path.name,
        time.perf_counter() - render_started_at,
    )
    deck = storage.load_deck(deck_id)

    def _log_reading_progress(stage: str, done: int, total: int) -> None:
        LOGGER.info(
            "%s %s progress: %s/%s slide(s)",
            pdf_path.name,
            stage,
            done,
            total,
        )

    def _log_ocr_event(event: str, details: dict[str, object]) -> None:
        slide_number = details.get("slideNumber") or details.get("slide_number") or "?"
        source = details.get("source")
        elapsed_ms = details.get("elapsedMs")
        extra: list[str] = []
        if source:
            extra.append(f"source={source}")
        for key, label in (
            ("lineCount", "lines"),
            ("blockCount", "blocks"),
            ("figureRegionCount", "figures"),
            ("correctedBlockCount", "corrected"),
            ("auditedBlockCount", "audited"),
            ("modeledBlockCount", "tables"),
        ):
            value = details.get(key)
            if isinstance(value, int):
                extra.append(f"{label}={value}")
        if isinstance(elapsed_ms, (int, float)):
            extra.append(f"elapsed={float(elapsed_ms) / 1000.0:.1f}s")
        suffix = f" ({', '.join(extra)})" if extra else ""
        LOGGER.info(
            "%s OCR slide %s: %s%s",
            pdf_path.name,
            slide_number,
            event.replace("_", " "),
            suffix,
        )

    layout_started_at = time.perf_counter()
    LOGGER.info("%s layout extraction started", pdf_path.name)
    built_layout = build_deck_layout_payload(
        deck,
        deck_path,
        lang=lang,
        progress_callback=lambda done, total: _log_reading_progress(
            "layout", done, total
        ),
    )
    normalized_layout = _normalize_layout_payload(
        built_layout,
        deck_id=deck.deck_id,
        lang=lang,
    )
    storage.save_layout_payload(deck.deck_id, normalized_layout)
    LOGGER.info(
        "%s layout saved in %.1fs",
        pdf_path.name,
        time.perf_counter() - layout_started_at,
    )
    ocr_started_at = time.perf_counter()
    LOGGER.info("%s OCR extraction started", pdf_path.name)
    ocr_payload = build_deck_ocr_payload(
        deck,
        deck_path,
        lang=lang,
        include_bboxes=include_bboxes,
        layout_payload=normalized_layout,
        pdf_path=deck_path / "source.pdf",
        progress_callback=lambda done, total: _log_reading_progress("OCR", done, total),
        event_callback=_log_ocr_event,
    )
    normalized_ocr = normalize_ocr_payload(
        ocr_payload,
        deck_id=deck.deck_id,
        lang=lang,
    )
    storage.save_ocr_payload(deck.deck_id, normalized_ocr)
    LOGGER.info(
        "%s OCR saved in %.1fs",
        pdf_path.name,
        time.perf_counter() - ocr_started_at,
    )
    analysis_started_at = time.perf_counter()
    LOGGER.info("%s mapped slide analysis merge started", pdf_path.name)
    merged_analysis = _build_slide_analysis_payload(
        normalized_layout,
        normalized_ocr,
        deck_id=deck.deck_id,
        lang=lang,
    )
    if not isinstance(merged_analysis, dict):
        raise ValueError("Slide editor reading pipeline did not return analysis.")
    storage.save_slide_analysis_payload(deck.deck_id, merged_analysis)
    LOGGER.info(
        "%s mapped slide analysis saved in %.1fs",
        pdf_path.name,
        time.perf_counter() - analysis_started_at,
    )
    cache_meta_path = _reading_cache_meta_path(pdf_path)
    cache_meta_path.write_text(
        json.dumps(
            _build_reading_cache_meta(
                pdf_path,
                lang=lang,
                include_bboxes=include_bboxes,
                source_sha256=source_sha256,
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    LOGGER.info(
        "Cached PDF reading artifacts for %s under %s in %.1fs",
        pdf_path.name,
        deck_path,
        time.perf_counter() - reader_started_at,
    )
    canonical_analysis = _canonicalize_analysis_payload(merged_analysis)
    return _attach_reading_completeness_audit(
        canonical_analysis,
        layout_payload=normalized_layout,
        ocr_payload=normalized_ocr,
    )


def _bundle_records(bundle_labels: Iterable[str]) -> list[_BundleLabelRecord]:
    records: list[_BundleLabelRecord] = []
    for label in bundle_labels:
        normalized = _normalize_text(label)
        if not normalized:
            continue
        records.append(
            _BundleLabelRecord(
                label=normalized,
                tokens=frozenset(_canonical_tokens(normalized)),
                required_token_counts=tuple(
                    sorted(Counter(_token_list(normalized)).items())
                ),
                part_count=max(1, len(_bundle_parts(normalized))),
            )
        )
    return records


def _contains_numeric_evidence(text: str) -> bool:
    return bool(
        _BUNDLE_PERCENT_RE.search(text)
        or _COUNT_RATIO_RE.search(text)
        or _MULTIPLIER_RE.search(text)
        or _BRAND_COUNT_RE.search(text)
        or _BUNDLE_BRAND_SPAN_RE.search(text)
    )


def _looks_like_bundle_metric_claim(text: str) -> bool:
    lowered = text.casefold()
    if not _contains_numeric_evidence(text):
        return False
    return (
        any(marker in lowered for marker in _BUNDLE_COHORT_HINTS)
        or (
            "+" in text
            and bool(_BUNDLE_PERCENT_RE.search(text) or _MULTIPLIER_RE.search(text))
        )
        or "market signal" in lowered
    )


def _classify_non_claim_unit(
    text: str,
    unit: dict[str, Any],
) -> dict[str, str] | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    block_type = _normalize_text(unit.get("block_type")).casefold()
    if block_type == "title":
        return {
            "filter_rule_id": "NF01",
            "filter_reason": "slide title is structural and out of claim scope",
        }

    if re.match(
        r"^(?:an\s+)?objective\s+evaluation\s+of\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return {
            "filter_rule_id": "NF11",
            "filter_reason": "deck objective statement is framing text, not a claim",
        }

    if _contains_numeric_evidence(normalized):
        return None

    folded = _fold_text(normalized)
    canonical = _canonical_text(normalized)
    source_kind = _normalize_text(unit.get("source_kind"))
    word_count = len(normalized.split())

    if _PRODUCT_LABEL_TEXT_RE.match(normalized):
        return {
            "filter_rule_id": "NF12",
            "filter_reason": "product exhibit label with mapped attributes is not a standalone claim",
        }
    if (
        block_type != "exhibit_label"
        and _EXHIBIT_LABEL_TEXT_RE.match(normalized)
        and "validation" not in folded
        and (word_count <= 12 or not _NON_CLAIM_PREDICATE_RE.search(normalized))
    ):
        return {
            "filter_rule_id": "NF13",
            "filter_reason": "standalone exhibit label is not a report claim",
        }
    if re.match(r"^\s*[-•]\s+", normalized) and not (
        _looks_like_bundle_brand_concentration_row(normalized)
        or _looks_like_bundle_metric_claim(normalized)
    ):
        return {
            "filter_rule_id": "NF14",
            "filter_reason": "list fragment without numeric evidence is not a standalone claim",
        }
    if re.search(
        r"\bimages?\s+reinforce\s+the\s+data\s+read\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return {
            "filter_rule_id": "NF15",
            "filter_reason": "visual reference text is not a package-data claim",
        }
    if re.match(r"^confidence\s*&\s*limits\s*:", normalized, flags=re.IGNORECASE):
        return {
            "filter_rule_id": "NF17",
            "filter_reason": "confidence and limitations note is validation metadata",
        }
    if re.match(r"^evidence\s+anchors?\s*\|", normalized, flags=re.IGNORECASE):
        return {
            "filter_rule_id": "NF18",
            "filter_reason": "evidence-anchor note enumerates report context",
        }
    if (
        word_count <= _SHORT_FRAGMENT_NON_CLAIM_WORD_LIMIT
        and not _NON_CLAIM_PREDICATE_RE.search(normalized)
        and not re.search(
            r"\b(?:hero\s+)?product\b|#\s*\d+|\brank\b|\bpareto\b",
            normalized,
            flags=re.IGNORECASE,
        )
    ):
        return {
            "filter_rule_id": "NF16",
            "filter_reason": "short text fragment without a predicate is not a standalone claim",
        }

    if block_type in {"footer_meta", "subtitle"} or re.search(
        r"\b(?:data\s+scope|document\s+focus)\s*:",
        normalized,
        flags=re.IGNORECASE,
    ):
        return {
            "filter_rule_id": "NF08",
            "filter_reason": "scope or footer metadata is not a report claim",
        }
    if re.match(
        r"^(?:evidence\s+briefing|briefing\s+matrix)\s*:",
        normalized,
        flags=re.IGNORECASE,
    ):
        return {
            "filter_rule_id": "NF09",
            "filter_reason": "briefing subtitle enumerates report sections",
        }
    if (
        block_type == "group_label"
        or (block_type == "exhibit_label" and word_count <= 8)
    ) and not re.search(
        r"\b(?:is|are|appears?|over-index|under-index|spans|accounts|validates?|confirms?)\b",
        folded,
    ):
        return {
            "filter_rule_id": "NF10",
            "filter_reason": "group or exhibit label without predicate",
        }
    if (
        block_type == "exhibit_label"
        and re.match(
            r"^exhibit\s+[a-z0-9]+\s*:",
            normalized,
            flags=re.IGNORECASE,
        )
        and not _NON_CLAIM_PREDICATE_RE.search(normalized)
        and "validation" not in folded
    ):
        return {
            "filter_rule_id": "NF10",
            "filter_reason": "exhibit label without standalone claim content",
        }
    if folded in _NON_CLAIM_STRUCTURAL_LABELS:
        return {
            "filter_rule_id": "NF04",
            "filter_reason": "boilerplate dossier/briefing marker",
        }
    if _LAYER_MARKER_RE.match(normalized):
        return {
            "filter_rule_id": "NF05",
            "filter_reason": "ordinal layer marker inside a ranked table",
        }
    if _NON_CLAIM_META_PURPOSE_START_RE.match(normalized):
        return {
            "filter_rule_id": "NF02",
            "filter_reason": "meta-purpose bullet describing report scope",
        }
    if _NON_CLAIM_SETUP_LABEL_RE.search(normalized):
        return {
            "filter_rule_id": "NF06",
            "filter_reason": "target/methodology/status setup text is not a report claim",
        }
    if (
        source_kind in {"bullet", "block_text"}
        and "+" in normalized
        and word_count <= 8
        and not _NON_CLAIM_PREDICATE_RE.search(normalized)
    ):
        return {
            "filter_rule_id": "NF07",
            "filter_reason": "short group or bundle label without predicate",
        }
    if (
        block_type in {"title", "heading"}
        and word_count <= 12
        and (
            folded.startswith(_NON_CLAIM_SECTION_PREFIXES)
            or (
                "categoryanalysis" in canonical
                and ("emergingsignals" in canonical or "baseline" in canonical)
            )
        )
    ):
        return {
            "filter_rule_id": "NF01",
            "filter_reason": "standalone report/section navigation header",
        }
    if source_kind == "block_text" and block_type in {
        "table_title",
        "group_label",
    }:
        if folded in _NON_CLAIM_TABLE_HEADER_LABELS or _TABLE_HEADER_PERCENT_RE.match(
            normalized
        ):
            return {
                "filter_rule_id": "NF03",
                "filter_reason": "table axis or column header",
            }
        if not re.search(
            r"\b(?:is|are|remain|remains|represent|represents|confirms|signals|moves|reveals|survive|survives|collapses|under-indexes)\b",
            folded,
        ):
            return {
                "filter_rule_id": "NF03",
                "filter_reason": "table or matrix title without standalone claim content",
            }
    return None


def _classify_mapping_issue_unit(
    text: str,
    unit: dict[str, Any],
) -> dict[str, str] | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    folded = _fold_text(normalized)
    source_kind = _normalize_text(unit.get("source_kind"))
    block_type = _normalize_text(unit.get("block_type")).casefold()
    word_count = len(normalized.split())

    if _STANDALONE_VISIBILITY_METRIC_RE.match(normalized):
        context_text = _normalize_text(unit.get("context_text"))
        if context_text and "+" in context_text:
            return None
        return {
            "mapping_issue_type": "matrix_metric_cell_without_row_label",
            "mapping_issue_reason": (
                "standalone visibility metric cell lacks the row label needed "
                "for deterministic validation"
            ),
        }
    if (
        any(marker in folded for marker in _OCR_FUSED_WORD_MARKERS)
        or _OCR_STRAY_TOKEN_RE.search(folded) is not None
        or _OCR_LONG_DIGIT_TOKEN_RE.search(normalized) is not None
    ):
        return {
            "mapping_issue_type": "ocr_fused_or_stray_token_text",
            "mapping_issue_reason": (
                "OCR/layout fused adjacent words or emitted stray tokens inside "
                "the text unit"
            ),
        }

    if source_kind == "visual_item" and (
        word_count <= 2
        or bool(re.fullmatch(r"[A-Z0-9]{1,12}", normalized.replace(" ", "")))
    ):
        return {
            "mapping_issue_type": "figure_logo_ocr_fragment",
            "mapping_issue_reason": "isolated visual/logo OCR scrap is not body claim text",
        }
    if (
        source_kind == "bullet"
        and re.search(r"\bit$", folded)
        and not normalized.endswith((".", "!", "?"))
    ):
        return {
            "mapping_issue_type": "truncated_sentence_split_across_bullets",
            "mapping_issue_reason": "sentence fragment appears to continue in a following unit",
        }
    if source_kind == "block_text" and block_type == "table_title":
        if _contains_numeric_evidence(normalized) and re.search(
            r"\b(?:recent|rest|products?)\b", folded
        ):
            return {
                "mapping_issue_type": "matrix_row_fragmentation_and_cell_order_scramble",
                "mapping_issue_reason": "numeric matrix cell was emitted as a standalone text unit",
            }
        if (
            "+" in normalized
            and word_count <= 5
            and not _TABLE_HEADER_PERCENT_RE.match(normalized)
        ):
            return {
                "mapping_issue_type": "matrix_row_fragmentation_and_cell_order_scramble",
                "mapping_issue_reason": "matrix row label was emitted separately from adjacent cells",
            }
    return None


def _looks_claim_like_text(text: str, *, block_type: str | None = None) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    word_count = len(normalized.split())
    if block_type in {"title", "heading"} and word_count <= 6:
        return False
    if _contains_numeric_evidence(normalized):
        return True
    lowered = normalized.casefold()
    if word_count >= 5 and any(hint in lowered for hint in _CLAIM_TEXT_HINTS):
        return True
    return (
        word_count >= 6
        and _RESIDUAL_CLAIM_DOMAIN_RE.search(normalized) is not None
        and _RESIDUAL_CLAIM_PREDICATE_RE.search(normalized) is not None
    )


def _matched_bundle_labels(
    text: str,
    bundle_records: list[_BundleLabelRecord],
) -> list[str]:
    text_tokens = _canonical_tokens(text)
    text_token_counts = Counter(_token_list(text))
    matches: list[str] = []
    for record in bundle_records:
        if not record.tokens:
            continue
        span = _best_bundle_span(text, record.label)
        if span is None:
            continue
        strict_token_match = record.tokens.issubset(text_tokens) and all(
            text_token_counts[token] >= count
            for token, count in record.required_token_counts
        )
        if strict_token_match or _has_fused_bundle_part_match(text, record.label):
            matches.append(record.label)
    loose_matches: list[tuple[int, str]] = []
    for record in bundle_records:
        parts = _bundle_parts(record.label)
        if len(parts) < 2:
            continue
        matched_all_parts = True
        matched_token_count = 0
        loose_token_counts: Counter[str] = Counter()
        for part in parts:
            part_tokens = set(_bundle_part_tokens(part))
            if not part_tokens:
                matched_all_parts = False
                break
            overlap = part_tokens & text_tokens
            if not overlap:
                matched_all_parts = False
                break
            matched_token_count += len(overlap)
            loose_token_counts.update(overlap)
        if matched_all_parts and all(
            text_token_counts[token] >= count
            for token, count in loose_token_counts.items()
        ):
            loose_matches.append((matched_token_count, record.label))
    if loose_matches:
        best_overlap = max(score for score, _label in loose_matches)
        matches.extend(label for score, label in loose_matches if score == best_overlap)
    if not matches:
        return []
    matches = _unique_texts(matches)
    deduped_matches: list[str] = []
    seen_match_keys: set[str] = set()
    for label in matches:
        key = _bundle_label_key(label)
        if key in seen_match_keys:
            continue
        seen_match_keys.add(key)
        deduped_matches.append(label)
    matches = _prefer_explicit_longest_bundle_labels(text, deduped_matches)
    matches.sort(key=lambda label: len(_bundle_parts(label)), reverse=True)
    return matches[:8]


def _looks_like_truncated_numeric_comparison(segment: str) -> bool:
    normalized = _normalize_text(segment)
    if len(_BUNDLE_PERCENT_RE.findall(normalized)) != 1:
        return False
    return bool(re.search(r"\bvs\.?$", normalized, flags=re.IGNORECASE))


def _looks_like_ocr_fused_claim(segment: str) -> bool:
    normalized = _normalize_text(segment)
    return bool(
        re.search(r"\b[a-z]{18,}\b", normalized, flags=re.IGNORECASE)
        or re.search(r"[a-z]\"[a-z]|\"[a-z]+\"[a-z]", normalized, flags=re.IGNORECASE)
    )


def _prefer_bundle_labels_with_numeric_fit(
    segment: str,
    labels: list[str],
    frames: dict[str, pl.DataFrame],
    *,
    context_segment: str,
) -> list[str]:
    if not labels or _looks_like_multi_claim_bundle_sentence(segment):
        return labels
    passing_labels: list[tuple[str, str]] = []
    for label in labels:
        label_resolution = _resolve_bundle_label_targets(segment, label, frames)
        for target_label in label_resolution["labels"]:
            localized_segment = _localize_bundle_segment(segment, target_label)
            bundle_result = _best_bundle_candidate(
                localized_segment,
                target_label,
                frames,
                context_segment=context_segment,
            )
            if bundle_result is not None and bundle_result["status"] == "pass":
                candidate_label = _normalize_text(
                    _candidate_primary_label(bundle_result["candidate"])
                )
                candidate_key = (
                    _bundle_label_key(candidate_label)
                    if candidate_label
                    else _bundle_label_key(label)
                )
                passing_labels.append((label, candidate_key))
                break
    if not passing_labels:
        return labels

    selected_labels: list[str] = []
    seen_candidate_keys: set[str] = set()
    for _label, candidate_key in passing_labels:
        if candidate_key in seen_candidate_keys:
            continue
        same_candidate_labels = [
            label for label, key in passing_labels if key == candidate_key
        ]
        exact_labels = [
            label
            for label in same_candidate_labels
            if _bundle_label_key(label) == candidate_key
        ]
        preferred_label = (
            exact_labels[0]
            if exact_labels
            else max(same_candidate_labels, key=lambda value: len(_bundle_parts(value)))
        )
        selected_labels.append(preferred_label)
        seen_candidate_keys.add(candidate_key)
    return _unique_texts(selected_labels)


def _table_row_texts(table_model: dict[str, object]) -> list[str]:
    raw_rows = table_model.get("rows")
    if not isinstance(raw_rows, list):
        return []
    header_rows = (
        _int_or_none(table_model.get("header_rows") or table_model.get("headerRows"))
        or 0
    )
    rows: list[list[str]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        raw_cells = raw_row.get("cells")
        if not isinstance(raw_cells, list):
            continue
        rows.append(
            [
                _normalize_text(cell.get("text"))
                for cell in raw_cells
                if isinstance(cell, dict)
            ]
        )
    if not rows:
        return []
    headers = rows[:header_rows] if header_rows > 0 else []
    data_rows = rows[header_rows:] if header_rows > 0 else rows

    flattened_headers = (
        [" ".join(filter(None, header)).strip() for header in zip(*headers)]
        if headers
        else []
    )
    texts: list[str] = []
    for row in data_rows:
        nonempty = [cell for cell in row if _normalize_text(cell)]
        if not nonempty:
            continue
        if flattened_headers and len(flattened_headers) >= len(row):
            label = _normalize_text(row[0])
            value_bits = [
                f"{flattened_headers[index]} {_normalize_text(cell)}"
                for index, cell in enumerate(row[1:], start=1)
                if _normalize_text(cell) and _normalize_text(flattened_headers[index])
            ]
            combined = f"{label}: {'; '.join(value_bits)}" if value_bits else label
            texts.append(_normalize_text(combined))
            continue
        texts.append(" | ".join(nonempty))
    return texts


def _block_bbox(block: dict[str, Any]) -> dict[str, float] | None:
    bbox = block.get("bbox")
    if not isinstance(bbox, dict):
        return None
    x = _float_or_none(bbox.get("x"))
    y = _float_or_none(bbox.get("y"))
    w = _float_or_none(bbox.get("w"))
    h = _float_or_none(bbox.get("h"))
    if None in {x, y, w, h}:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _reconstructed_group_table_rows(
    blocks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    table_blocks_by_group: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        block_type = _normalize_text(block.get("type")).casefold()
        group_kind = _normalize_text(
            block.get("groupKind") or block.get("group_kind")
        ).casefold()
        group_id = _normalize_text(block.get("groupId") or block.get("group_id"))
        if block_type != "table_title" or group_kind != "table" or not group_id:
            continue
        table_blocks_by_group.setdefault(group_id, []).append(block)

    reconstructed_by_group: dict[str, list[dict[str, Any]]] = {}
    for group_id, group_blocks in table_blocks_by_group.items():
        cells: list[dict[str, Any]] = []
        for block in group_blocks:
            text = _normalize_text(block.get("text"))
            bbox = _block_bbox(block)
            if not text or bbox is None:
                continue
            if text.casefold() in {
                "briefing matrix",
                "attribute bundle",
                "recent (%)",
                "rest (%)",
            }:
                continue
            cells.append(
                {
                    "block_id": _normalize_text(
                        block.get("blockId") or block.get("block_id")
                    ),
                    "text": text,
                    "bbox": bbox,
                }
            )

        if len(cells) < 6:
            continue

        cells.sort(key=lambda cell: cell["bbox"]["y"])
        rows: list[list[dict[str, Any]]] = []
        current_row: list[dict[str, Any]] = []
        current_center_y: float | None = None
        for cell in cells:
            center_y = cell["bbox"]["y"] + (cell["bbox"]["h"] / 2.0)
            if current_center_y is None:
                current_row = [cell]
                current_center_y = center_y
                continue
            if abs(center_y - current_center_y) <= 40:
                current_row.append(cell)
                current_center_y = (
                    current_center_y * (len(current_row) - 1) + center_y
                ) / len(current_row)
                continue
            rows.append(current_row)
            current_row = [cell]
            current_center_y = center_y
        if current_row:
            rows.append(current_row)

        reconstructed_rows: list[dict[str, Any]] = []
        for row_index, row_cells in enumerate(rows):
            ordered_cells = sorted(row_cells, key=lambda cell: cell["bbox"]["x"])
            if len(ordered_cells) < 3:
                continue
            row_text = " | ".join(cell["text"] for cell in ordered_cells[:3])
            reconstructed_rows.append(
                {
                    "text": _normalize_text(row_text),
                    "source_kind": "table_row",
                    "block_id": group_id,
                    "block_type": "table",
                    "row_index": row_index,
                    "reconstructed_from_group_table_titles": True,
                    "source_block_ids": [
                        cell["block_id"]
                        for cell in ordered_cells[:3]
                        if cell["block_id"]
                    ],
                }
            )
        if reconstructed_rows:
            reconstructed_by_group[group_id] = reconstructed_rows

    return reconstructed_by_group


def _split_text_units(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized.split()) <= 18:
        return [normalized]
    return [
        _normalize_text(part)
        for part in _SENTENCE_SPLIT_RE.split(normalized)
        if _normalize_text(part)
    ]


def _block_text_for_context(block: dict[str, Any]) -> str:
    parts: list[str] = []
    text = _normalize_text(block.get("text"))
    if text:
        parts.append(text)
    items = block.get("items") if isinstance(block.get("items"), list) else []
    parts.extend(_normalize_text(item) for item in items if _normalize_text(item))
    return _normalize_text(" ".join(parts))


def _block_context_maps(
    blocks: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    context_by_id: dict[str, str] = {}
    context_by_group: dict[str, str] = {}
    for block in blocks:
        block_id = _normalize_text(block.get("block_id") or block.get("blockId"))
        block_type = _normalize_text(block.get("type")).casefold()
        context_text = _block_text_for_context(block)
        if not context_text:
            continue
        if block_id and block_type in {"group_label", "heading", "title"}:
            context_by_id[block_id] = context_text
        group_id = _normalize_text(block.get("group_id") or block.get("groupId"))
        if group_id and block_type in {"group_label", "heading", "title"}:
            context_by_group[group_id] = context_text
    return context_by_id, context_by_group


def _block_parent_context(
    block: dict[str, Any],
    *,
    context_by_id: dict[str, str],
    context_by_group: dict[str, str],
) -> str:
    parts: list[str] = []
    parent_id = _normalize_text(block.get("parent_id") or block.get("parentId"))
    if parent_id and context_by_id.get(parent_id):
        parts.append(context_by_id[parent_id])
    group_id = _normalize_text(block.get("group_id") or block.get("groupId"))
    if group_id and context_by_group.get(group_id):
        parts.append(context_by_group[group_id])
    return _normalize_text(" ".join(_unique_texts(parts)))


def _assign_slide_unit_indexes(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for unit_index, unit in enumerate(units):
        unit["unit_index"] = unit_index
    return units


def _iter_slide_units(slide: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    raw_blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    blocks = [block for block in raw_blocks if isinstance(block, dict)]
    context_by_id, context_by_group = _block_context_maps(blocks)
    reconstructed_group_rows = _reconstructed_group_table_rows(blocks)
    emitted_group_rows: set[str] = set()
    for block in blocks:
        block_id = (
            _normalize_text(block.get("block_id") or block.get("blockId")) or None
        )
        block_type = _normalize_text(block.get("type")) or "unknown"
        context_text = _block_parent_context(
            block,
            context_by_id=context_by_id,
            context_by_group=context_by_group,
        )
        group_id = _normalize_text(block.get("group_id") or block.get("groupId"))
        if (
            group_id
            and group_id in reconstructed_group_rows
            and group_id not in emitted_group_rows
        ):
            group_context = context_text
            if context_by_group.get(group_id):
                group_context = _normalize_text(
                    " ".join(
                        part
                        for part in (context_by_group.get(group_id), context_text)
                        if part
                    )
                )
            for reconstructed in reconstructed_group_rows[group_id]:
                units.append(
                    {
                        **reconstructed,
                        "context_text": group_context,
                    }
                )
            emitted_group_rows.add(group_id)

        if (
            group_id
            and group_id in reconstructed_group_rows
            and block_type.casefold() == "table_title"
        ):
            continue
        if isinstance(block.get("table_model"), dict):
            for row_index, row_text in enumerate(
                _table_row_texts(block["table_model"])
            ):
                units.append(
                    {
                        "text": row_text,
                        "source_kind": "table_row",
                        "block_id": block_id,
                        "block_type": block_type,
                        "context_text": context_text,
                        "row_index": row_index,
                    }
                )
            continue
        block_text = _normalize_text(block.get("text"))
        items = block.get("items") if isinstance(block.get("items"), list) else []
        if (
            items
            and block_text
            and block_type.casefold() in {"callout_banner", "implication_banner"}
        ):
            for text in _split_text_units(block_text):
                units.append(
                    {
                        "text": text,
                        "source_kind": "block_text",
                        "block_id": block_id,
                        "block_type": block_type,
                        "context_text": context_text,
                    }
                )
            continue
        if items:
            for item_index, item in enumerate(items):
                text = _normalize_text(item)
                if not text:
                    continue
                units.append(
                    {
                        "text": text,
                        "source_kind": "bullet",
                        "block_id": block_id,
                        "block_type": block_type,
                        "context_text": context_text,
                        "item_index": item_index,
                    }
                )
            continue
        for text in _split_text_units(block_text):
            units.append(
                {
                    "text": text,
                    "source_kind": "block_text",
                    "block_id": block_id,
                    "block_type": block_type,
                    "context_text": context_text,
                }
            )
    if units:
        return _assign_slide_unit_indexes(units)
    if blocks:
        return _assign_slide_unit_indexes(units)
    for text in _split_text_units(slide.get("ocr_text")):
        units.append(
            {
                "text": text,
                "source_kind": "slide_text",
                "block_id": None,
                "block_type": None,
            }
        )
    return _assign_slide_unit_indexes(units)


def _validate_bundle_brand_concentration_summary(
    *,
    segment: str,
    slide: dict[str, Any],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
) -> dict[str, Any] | None:
    row_evaluations: list[dict[str, Any]] = []
    for slide_unit in _iter_slide_units(slide):
        row_text = _normalize_text(slide_unit.get("text"))
        if not row_text or row_text == segment:
            continue
        slide_title = _normalize_text(slide.get("title_text"))
        context_text = _normalize_text(slide_unit.get("context_text"))
        context_segment = _normalize_text(
            " ".join(part for part in (slide_title, context_text, row_text) if part)
        )
        if _looks_like_bundle_brand_concentration_row(row_text):
            row_result = _validate_bundle_brand_concentration_row(
                row_text,
                frames=package.frames,
                bundle_records=bundle_records,
                context_segment=context_segment,
            )
            if row_result is not None:
                row_evaluations.append(row_result)
            continue

        if not _looks_like_bundle_metric_claim(row_text):
            continue
        row_matching_segment = (
            _normalize_text(" ".join(part for part in (context_text, row_text) if part))
            or row_text
        )
        matched_labels = _matched_bundle_labels(row_matching_segment, bundle_records)
        matched_labels = _prefer_bundle_labels_with_numeric_fit(
            row_text,
            matched_labels,
            package.frames,
            context_segment=row_matching_segment,
        )
        if not matched_labels:
            continue
        matched_candidate = None
        matched_entity = None
        for label in matched_labels:
            label_resolution = _resolve_bundle_label_targets(
                row_text,
                label,
                package.frames,
            )
            for target_label in label_resolution["labels"]:
                localized_segment = _localize_bundle_segment(row_text, target_label)
                bundle_result = _best_bundle_candidate(
                    localized_segment,
                    target_label,
                    package.frames,
                    context_segment=row_matching_segment,
                )
                if bundle_result is None or bundle_result.get("status") != "pass":
                    continue
                matched_candidate = bundle_result["candidate"]
                matched_entity = target_label
                break
            if matched_candidate is not None:
                break
        if matched_candidate is None or matched_entity is None:
            continue
        non_collapse, non_collapse_reasons = _candidate_is_not_single_brand_artifact(
            matched_candidate
        )
        row_evaluations.append(
            {
                "status": "pass",
                "candidate": matched_candidate,
                "entity": matched_entity,
                "observed_values": _extract_numeric_claim_evidence(row_text),
                "reasons": [],
                "non_collapse": non_collapse,
                "non_collapse_reasons": non_collapse_reasons,
            }
        )

    if not row_evaluations:
        return {
            "status": "warning",
            "message": "summary claim has no resolved bundle breadth rows on this slide",
        }

    row_support = [
        {
            "claim_text": evaluation["entity"],
            "source_file": evaluation["candidate"]["file"],
            "bundle_label": _candidate_primary_label(evaluation["candidate"]),
            "brand_span": _candidate_brand_span_for_role(
                evaluation["candidate"],
                _candidate_primary_population_role(evaluation["candidate"]) or "",
            ),
            "dominant_brand_name": _candidate_dominant_brand_for_role(
                evaluation["candidate"],
                _candidate_primary_population_role(evaluation["candidate"]) or "",
            ),
            "dominant_brand_share": _candidate_dominant_brand_share_for_role(
                evaluation["candidate"],
                _candidate_primary_population_role(evaluation["candidate"]) or "",
            ),
            "status": evaluation["status"],
            "non_collapse": evaluation["non_collapse"],
        }
        for evaluation in row_evaluations
    ]

    lowered = segment.casefold()
    non_collapse_failures = [
        evaluation
        for evaluation in row_evaluations
        if evaluation["status"] != "pass" or not evaluation["non_collapse"]
    ]

    slide_brand_claims: list[dict[str, Any]] = []
    for slide_unit in _iter_slide_units(slide):
        brand_text = _normalize_text(slide_unit.get("text"))
        if not brand_text or brand_text == segment:
            continue
        if not (
            _looks_like_brand_share_claim(brand_text)
            and _contains_numeric_evidence(brand_text)
        ):
            continue
        brand_result = _validate_brand_segment(
            brand_text,
            package.frames["top_seller_brand_comparison.csv"],
            require_numeric_evidence=True,
        )
        if brand_result is not None and brand_result["status"] == "pass":
            slide_brand_claims.append(brand_result)

    if "single-brand artifact" in lowered or "single-brand lock-in" in lowered:
        reasons = [
            reason
            for evaluation in non_collapse_failures
            for reason in (evaluation["reasons"] + evaluation["non_collapse_reasons"])
        ]
        return {
            "status": "pass" if not non_collapse_failures else "fail",
            "row_support": row_support,
            "threshold_policy": _bundle_brand_concentration_threshold_policy(),
            "reasons": reasons,
        }

    if "provides amplitude" in lowered or "direction itself" in lowered:
        mentioned_brand = _brand_row_for_segment(
            segment,
            package.frames["top_seller_brand_comparison.csv"],
        )
        if mentioned_brand is None:
            return {
                "status": "warning",
                "message": "summary claim mentions no brand resolved in package",
                "row_support": row_support,
            }
        mentioned_brand_name = _normalize_text(mentioned_brand.get("brand"))
        brand_support = [
            claim
            for claim in slide_brand_claims
            if _canonical_text(claim.get("brand"))
            == _canonical_text(mentioned_brand_name)
        ]
        row_brand_matches = [
            evaluation
            for evaluation in row_evaluations
            if _canonical_text(
                _candidate_dominant_brand_for_role(
                    evaluation["candidate"],
                    _candidate_primary_population_role(evaluation["candidate"]) or "",
                )
            )
            == _canonical_text(mentioned_brand_name)
        ]
        reasons: list[str] = []
        if not brand_support:
            reasons.append(
                "slide does not contain a verified cohort-level brand concentration claim"
            )
        if not row_brand_matches:
            reasons.append(
                "brand is not the dominant brand in any supporting bundle row"
            )
        reasons.extend(
            reason
            for evaluation in non_collapse_failures
            for reason in (evaluation["reasons"] + evaluation["non_collapse_reasons"])
        )
        return {
            "status": "pass" if not reasons else "fail",
            "row_support": row_support,
            "brand_support": [
                {
                    "brand_name": claim.get("brand"),
                    "source_file": claim.get("file"),
                    "observed_values": claim.get("observed_values"),
                    "package_values": claim.get("expected"),
                }
                for claim in brand_support
            ],
            "threshold_policy": _bundle_brand_concentration_threshold_policy(),
            "reasons": reasons,
        }

    if "multi-brand movement" in lowered:
        brand_spans = [
            support["brand_span"]
            for support in row_support
            if isinstance(support.get("brand_span"), int)
        ]
        reasons = [
            reason
            for evaluation in non_collapse_failures
            for reason in (evaluation["reasons"] + evaluation["non_collapse_reasons"])
        ]
        if not brand_spans:
            reasons.append("supporting bundle rows do not expose brand-span evidence")
        range_match = re.search(
            r"\bspanning\s+(\d+)\s+to\s+(\d+)\s+brands?\b",
            segment,
            flags=re.IGNORECASE,
        )
        if range_match is not None and brand_spans:
            expected_min = int(range_match.group(1))
            expected_max = int(range_match.group(2))
            actual_min = min(brand_spans)
            actual_max = max(brand_spans)
            if actual_min != expected_min or actual_max != expected_max:
                reasons.append(
                    "brand-span range mismatch: "
                    f"expected {expected_min} to {expected_max}, "
                    f"observed {actual_min} to {actual_max}"
                )
        return {
            "status": "pass" if not reasons else "fail",
            "row_support": row_support,
            "threshold_policy": _bundle_brand_concentration_threshold_policy(),
            "brand_span_range": {
                "minimum": min(brand_spans) if brand_spans else None,
                "maximum": max(brand_spans) if brand_spans else None,
            },
            "reasons": reasons,
        }

    return None


def _emerging_lane_threshold_policy() -> dict[str, Any]:
    return {
        "positive_recent_delta_min": 0.01,
        "negative_recent_delta_max": -0.01,
        "modest_lane_primary_recent_pct_max": 40.0,
        "lane_defining_rules": [
            "emerging_lane_profile_v1",
            "emerging_lane_shift_v1",
        ],
        "bundle_support_basis": "same-slide verified recent-vs-rest rows",
        "attribute_support_basis": (
            "recent-vs-rest delta rows from filter, mapped-attribute, and resolved-core tables"
        ),
    }


def _looks_like_emerging_lane_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "first lane centers on",
            "second innovation lane",
            "second lane",
            "this line successfully maintains",
            "adjacent lanes rather than a category reset",
            "modest emerging signal splitting",
        )
    )


def _resolved_slide_bundle_metric_support(
    *,
    slide: dict[str, Any],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
    exclude_segment: str,
) -> list[dict[str, Any]]:
    support_rows: list[dict[str, Any]] = []
    seen_support: set[tuple[str, str]] = set()
    for slide_unit in _iter_slide_units(slide):
        row_text = _normalize_text(slide_unit.get("text"))
        if not row_text or row_text == exclude_segment:
            continue
        if not _looks_like_bundle_metric_claim(row_text):
            continue
        context_text = _normalize_text(slide_unit.get("context_text"))
        row_matching_segment = (
            _normalize_text(" ".join(part for part in (context_text, row_text) if part))
            or row_text
        )
        matched_labels = _matched_bundle_labels(row_matching_segment, bundle_records)
        matched_labels = _prefer_bundle_labels_with_numeric_fit(
            row_text,
            matched_labels,
            package.frames,
            context_segment=row_matching_segment,
        )
        if not matched_labels:
            continue
        matched_candidate: dict[str, Any] | None = None
        matched_entity: str | None = None
        for label in matched_labels:
            label_resolution = _resolve_bundle_label_targets(
                row_text,
                label,
                package.frames,
            )
            for target_label in label_resolution["labels"]:
                localized_segment = _localize_bundle_segment(row_text, target_label)
                bundle_result = _best_bundle_candidate(
                    localized_segment,
                    target_label,
                    package.frames,
                    context_segment=row_matching_segment,
                )
                if bundle_result is None or bundle_result.get("status") != "pass":
                    continue
                matched_candidate = bundle_result["candidate"]
                matched_entity = target_label
                break
            if matched_candidate is not None:
                break
        if matched_candidate is None or matched_entity is None:
            continue
        support_key = (
            _normalize_text(matched_candidate.get("file")),
            _canonical_text(matched_entity),
        )
        if support_key in seen_support:
            continue
        seen_support.add(support_key)
        support_rows.append(
            {
                "claim_text": row_text,
                "entity": matched_entity,
                "candidate": matched_candidate,
                "source_file": matched_candidate["file"],
                "matched_row_keys": _candidate_row_keys(matched_candidate),
                "package_values": _bundle_candidate_package_values(matched_candidate),
            }
        )
    return support_rows


def _recent_delta_candidate_rows(
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name, label_column in (
        ("filter_comparison.csv", "filter_value"),
        ("mapped_attribute_comparison.csv", "attribute_value"),
        ("resolved_core_comparison.csv", "attribute_value"),
    ):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or label_column not in columns or "delta" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get(label_column))
            delta = _float_or_none(row.get("delta"))
            if not label or delta is None:
                continue
            candidates.append(
                {
                    "file": file_name,
                    "row": row,
                    "label": label,
                    "delta": delta,
                }
            )
    return candidates


def _score_recent_delta_candidate(
    fragment: str,
    candidate: dict[str, Any],
) -> int:
    fragment_tokens = _canonical_tokens(fragment)
    label_tokens = _canonical_tokens(candidate.get("label"))
    overlap = fragment_tokens & label_tokens
    if not overlap:
        return 0
    score = len(overlap) * 10
    if label_tokens and label_tokens <= fragment_tokens:
        score += 25
    return score


def _best_recent_delta_candidate(
    fragment: str,
    frames: dict[str, pl.DataFrame],
    *,
    direction: str,
) -> dict[str, Any] | None:
    threshold_policy = _emerging_lane_threshold_policy()
    signed_candidates: list[tuple[int, dict[str, Any]]] = []
    for candidate in _recent_delta_candidate_rows(frames):
        delta = candidate["delta"]
        if direction == "positive":
            if delta < threshold_policy["positive_recent_delta_min"]:
                continue
        elif direction == "negative":
            if delta > threshold_policy["negative_recent_delta_max"]:
                continue
        else:
            continue
        score = _score_recent_delta_candidate(fragment, candidate)
        if score <= 0:
            continue
        signed_candidates.append((score, candidate))

    if not signed_candidates:
        return None

    signed_candidates.sort(key=lambda item: item[0], reverse=True)
    best_score = signed_candidates[0][0]
    equally_best = [
        candidate for score, candidate in signed_candidates if score == best_score
    ]
    if len(equally_best) != 1:
        return None
    return equally_best[0]


def _exact_recent_delta_candidate(
    label: str,
    frames: dict[str, pl.DataFrame],
    *,
    direction: str,
) -> dict[str, Any] | None:
    target = _canonical_text(label)
    if not target:
        return None
    threshold_policy = _emerging_lane_threshold_policy()
    matches: list[dict[str, Any]] = []
    for candidate in _recent_delta_candidate_rows(frames):
        if _canonical_text(candidate.get("label")) != target:
            continue
        delta = candidate["delta"]
        if direction == "positive":
            if delta < threshold_policy["positive_recent_delta_min"]:
                continue
        elif direction == "negative":
            if delta > threshold_policy["negative_recent_delta_max"]:
                continue
        else:
            continue
        matches.append(candidate)
    if len(matches) != 1:
        return None
    return matches[0]


def _matching_lane_row_support(
    fragment: str,
    row_support: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fragment_tokens = _canonical_tokens(fragment)
    matches: list[tuple[int, dict[str, Any]]] = []
    for support in row_support:
        label_tokens = _canonical_tokens(support.get("entity"))
        overlap = fragment_tokens & label_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        if label_tokens and label_tokens <= fragment_tokens:
            score += 25
        matches.append((score, support))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [support for _score, support in matches]


def _recent_delta_support_details(
    candidate: dict[str, Any], *, concept: str
) -> dict[str, Any]:
    row = candidate["row"]
    details = {
        "concept": concept,
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(
            {"file": candidate["file"], "row": row}
        ),
        "expected_numeric_values": {
            "delta": candidate["delta"],
            "pct_recent": _percent_from_fraction(row.get("pct_recent")),
            "pct_rest": _percent_from_fraction(row.get("pct_rest")),
        },
        "package_values": _bundle_candidate_package_values(
            {"file": candidate["file"], "row": row}
        ),
    }
    return details


def _slice_after_marker(
    text: str,
    marker: str,
    *,
    stop_markers: tuple[str, ...] = (),
) -> str:
    lowered = text.casefold()
    marker_index = lowered.find(marker.casefold())
    if marker_index < 0:
        return ""
    start = marker_index + len(marker)
    end = len(text)
    lowered_tail = lowered[start:]
    for stop_marker in stop_markers:
        stop_index = lowered_tail.find(stop_marker.casefold())
        if stop_index >= 0:
            end = min(end, start + stop_index)
    return _normalize_text(text[start:end].strip(" .;,:"))


def _parenthetical_fragment(text: str) -> str:
    match = re.search(r"\(([^()]*)\)", text)
    return _normalize_text(match.group(1)) if match is not None else ""


def _validate_emerging_lane_summary(
    *,
    segment: str,
    slide: dict[str, Any],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
) -> dict[str, Any] | None:
    row_support = _resolved_slide_bundle_metric_support(
        slide=slide,
        package=package,
        bundle_records=bundle_records,
        exclude_segment=segment,
    )
    lowered = segment.casefold()
    threshold_policy = _emerging_lane_threshold_policy()
    reasons: list[str] = []
    matched_row_support: list[dict[str, Any]] = []
    attribute_support: list[dict[str, Any]] = []
    component_entities: list[str] = []
    aggregation_rule_id: str | None = None

    if "first lane centers on" in lowered:
        aggregation_rule_id = "emerging_lane_profile_v1"
        center_fragment = _slice_after_marker(
            segment,
            "centers on",
            stop_markers=(" accompanied by",),
        )
        matched_row_support = _matching_lane_row_support(center_fragment, row_support)
        if not matched_row_support:
            reasons.append(
                "lane center text did not resolve to supporting slide bundle rows"
            )
        if "care language" in lowered:
            care_candidate = _exact_recent_delta_candidate(
                "hydrating/moisturizing",
                package.frames,
                direction="positive",
            )
            if care_candidate is None:
                reasons.append(
                    "care-language support did not resolve to a positive recent delta row"
                )
            else:
                attribute_support.append(
                    _recent_delta_support_details(
                        care_candidate,
                        concept="care_language",
                    )
                )

    elif "moves away from" in lowered and (
        " toward " in lowered or " towards " in lowered
    ):
        aggregation_rule_id = "emerging_lane_shift_v1"
        stop_markers = (" toward ", " towards ")
        away_fragment = _slice_after_marker(
            segment,
            "moves away from",
            stop_markers=stop_markers,
        )
        toward_marker = " toward " if " toward " in lowered else " towards "
        toward_fragment = _slice_after_marker(segment, toward_marker)
        negative_candidate = _best_recent_delta_candidate(
            away_fragment,
            package.frames,
            direction="negative",
        )
        if negative_candidate is None:
            reasons.append(
                "away-from fragment did not resolve to a negative recent delta row"
            )
        else:
            attribute_support.append(
                _recent_delta_support_details(
                    negative_candidate,
                    concept="away_from_baseline",
                )
            )
        matched_row_support = _matching_lane_row_support(toward_fragment, row_support)
        if not matched_row_support:
            positive_candidate = _best_recent_delta_candidate(
                toward_fragment,
                package.frames,
                direction="positive",
            )
            if positive_candidate is None:
                reasons.append(
                    "toward-fragment did not resolve to positive recent-lift support"
                )
            else:
                attribute_support.append(
                    _recent_delta_support_details(
                        positive_candidate,
                        concept="toward_lane_profile",
                    )
                )
        if any(
            marker in lowered
            for marker in (
                "blurred",
                "soft-focus",
                "soft focus",
                "lower-drag",
                "lower drag",
                "softer-performance",
                "softer performance",
            )
        ):
            blur_candidate = _exact_recent_delta_candidate(
                "smoothing/blur",
                package.frames,
                direction="positive",
            ) or _exact_recent_delta_candidate(
                "buildable coverage",
                package.frames,
                direction="positive",
            )
            if blur_candidate is None:
                reasons.append(
                    "soft-focus / blurred support did not resolve to a positive recent delta row"
                )
            else:
                attribute_support.append(
                    _recent_delta_support_details(
                        blur_candidate,
                        concept="blurred_states",
                    )
                )

    elif "this line successfully maintains" in lowered:
        aggregation_rule_id = "emerging_lane_extension_v1"
        performance_fragment = _parenthetical_fragment(segment) or segment
        matched_row_support = _matching_lane_row_support(
            performance_fragment, row_support
        )
        if not matched_row_support:
            reasons.append(
                "performance fragment did not resolve to supporting bundle rows"
            )
        if (
            "soft-focus" in lowered
            or "soft focus" in lowered
            or "lower-drag" in lowered
            or "lower drag" in lowered
        ):
            blur_candidate = _exact_recent_delta_candidate(
                "smoothing/blur",
                package.frames,
                direction="positive",
            )
            if blur_candidate is None:
                reasons.append(
                    "soft-focus / lower-drag support did not resolve to a positive recent delta row"
                )
            else:
                attribute_support.append(
                    _recent_delta_support_details(
                        blur_candidate,
                        concept="blurred_states",
                    )
                )

    elif "adjacent lanes" in lowered or "category reset" in lowered:
        return {
            "status": "warning",
            "message": (
                "emerging-lane summary needs explicit cross-lane counting and ranking rules"
            ),
            "row_support": row_support,
            "threshold_policy": threshold_policy,
        }

    else:
        return None

    component_entities = _unique_texts(
        [support["entity"] for support in matched_row_support]
        + [
            item["matched_row_keys"].get("attribute_value", "")
            for item in attribute_support
        ]
        + [
            item["matched_row_keys"].get("filter_value", "")
            for item in attribute_support
        ]
    )
    return {
        "status": "pass" if not reasons else "fail",
        "row_support": [
            {
                "claim_text": support["claim_text"],
                "entity": support["entity"],
                "source_file": support["source_file"],
                "matched_row_keys": support["matched_row_keys"],
                "package_values": support["package_values"],
            }
            for support in matched_row_support
        ],
        "attribute_support": attribute_support,
        "component_entities": component_entities,
        "aggregation_rule_id": aggregation_rule_id,
        "cohort_basis": "recent_vs_rest",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "same-slide verified recent-vs-rest bundle rows plus recent-vs-rest delta rows"
        ),
        "reasons": reasons,
    }


def _expected_lane_count(segment: str) -> int | None:
    lowered = segment.casefold()
    match = re.search(
        r"\b(?P<count>\d+|one|two|three|four)\s+(?:adjacent\s+|modest\s+)?lanes?\b",
        lowered,
    )
    if match is None:
        return None
    raw_value = match.group("count")
    if raw_value.isdigit():
        return int(raw_value)
    return {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
    }.get(raw_value)


def _looks_like_cross_lane_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return (
        "adjacent lanes" in lowered
        or "category reset" in lowered
        or "introduce two modest lanes" in lowered
        or ("lanes:" in lowered and "emerging signal" in lowered)
        or "splitting into" in lowered
        and "lanes" in lowered
    )


def _lane_descriptor_tokens(text: str) -> set[str]:
    return _canonical_tokens(
        text,
        ignored_tokens={
            "lane",
            "lanes",
            "formula",
            "formulas",
            "recent",
            "launches",
            "introduce",
            "introduced",
            "emerging",
            "signal",
            "signals",
            "modest",
            "two",
            "one",
            "three",
            "and",
        },
    )


def _lane_descriptor_fragments(segment: str) -> list[str]:
    lowered = segment.casefold()
    marker_index = lowered.find("lanes:")
    if marker_index < 0:
        return []
    fragment_text = _normalize_text(segment[marker_index + len("lanes:") :])
    if not fragment_text:
        return []
    parts = re.split(r"\s+\band\b\s+", fragment_text, maxsplit=3, flags=re.IGNORECASE)
    return [
        _normalize_text(part.strip(" .;,:")) for part in parts if _normalize_text(part)
    ]


def _lane_primary_recent_pct_max(claim: dict[str, Any]) -> float | None:
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    row_support = (
        details.get("row_support")
        if isinstance(details.get("row_support"), list)
        else []
    )
    values: list[float] = []
    for support in row_support:
        if not isinstance(support, dict):
            continue
        package_values = (
            support.get("package_values")
            if isinstance(support.get("package_values"), dict)
            else {}
        )
        pct_recent = _float_or_none(package_values.get("pct_recent"))
        if pct_recent is not None:
            values.append(pct_recent)
    if not values:
        return None
    return max(values)


def _emerging_lane_component_entities(claim: dict[str, Any]) -> list[str]:
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    component_entities = (
        details.get("component_entities")
        if isinstance(details.get("component_entities"), list)
        else []
    )
    return [
        _normalize_text(item) for item in component_entities if _normalize_text(item)
    ]


def _deck_level_emerging_lane_claims(
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    threshold_policy = _emerging_lane_threshold_policy()
    allowed_rules = set(threshold_policy["lane_defining_rules"])
    lane_claims: list[dict[str, Any]] = []
    for claim in claims:
        if claim.get("status") != "verified":
            continue
        if claim.get("claim_family") != "emerging_lane_summary":
            continue
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        if _normalize_text(details.get("aggregation_rule_id")) not in allowed_rules:
            continue
        lane_claims.append(claim)
    lane_claims.sort(
        key=lambda item: (
            _int_or_none(item.get("slide_number")) or 0,
            _normalize_text(item.get("claim_text")),
        )
    )
    return lane_claims


def _verified_emerging_lane_groups(
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for claim in claims:
        if claim.get("status") != "verified":
            continue
        if claim.get("claim_family") != "emerging_lane_summary":
            continue
        slide_number = _int_or_none(claim.get("slide_number"))
        if slide_number is None:
            continue
        bucket = grouped.setdefault(
            slide_number,
            {
                "slide_number": slide_number,
                "claim_texts": [],
                "component_entities": [],
                "aggregation_rule_ids": [],
            },
        )
        bucket["claim_texts"].append(_normalize_text(claim.get("claim_text")))
        bucket["component_entities"].extend(_emerging_lane_component_entities(claim))
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        aggregation_rule_id = _normalize_text(details.get("aggregation_rule_id"))
        if aggregation_rule_id:
            bucket["aggregation_rule_ids"].append(aggregation_rule_id)

    groups: list[dict[str, Any]] = []
    for slide_number, bucket in sorted(grouped.items()):
        groups.append(
            {
                "slide_number": slide_number,
                "claim_texts": _unique_texts(bucket["claim_texts"]),
                "component_entities": _unique_texts(bucket["component_entities"]),
                "aggregation_rule_ids": _unique_texts(bucket["aggregation_rule_ids"]),
            }
        )
    return groups


def _best_lane_group_for_descriptor(
    descriptor: str,
    lane_groups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    descriptor_tokens = _lane_descriptor_tokens(descriptor)
    if not descriptor_tokens:
        return None

    scored_groups: list[tuple[int, dict[str, Any]]] = []
    for group in lane_groups:
        group_tokens = _lane_descriptor_tokens(
            " ".join(
                list(group.get("component_entities", []))
                + list(group.get("claim_texts", []))
            )
        )
        overlap = descriptor_tokens & group_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        if descriptor_tokens <= group_tokens:
            score += 25
        scored_groups.append((score, group))

    if not scored_groups:
        return None
    scored_groups.sort(key=lambda item: item[0], reverse=True)
    best_score = scored_groups[0][0]
    equally_best = [group for score, group in scored_groups if score == best_score]
    if len(equally_best) != 1:
        return None
    return equally_best[0]


def _validate_cross_lane_emerging_summary_from_claims(
    segment: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not _looks_like_cross_lane_summary_claim(segment):
        return None

    threshold_policy = _emerging_lane_threshold_policy()
    lane_claims = _deck_level_emerging_lane_claims(claims)
    if not lane_claims:
        return {
            "status": "warning",
            "message": "cross-lane summary has no verified lane-defining claims yet",
            "threshold_policy": threshold_policy,
            "component_claims": [],
        }

    expected_lane_count = _expected_lane_count(segment)
    observed_lane_count = len(lane_claims)
    reasons: list[str] = []
    if expected_lane_count is None:
        reasons.append("cross-lane summary does not state an explicit lane count")
    elif observed_lane_count != expected_lane_count:
        reasons.append(
            f"lane count mismatch: expected {expected_lane_count}, observed {observed_lane_count}"
        )

    modest_pct_max = _float_or_none(
        threshold_policy.get("modest_lane_primary_recent_pct_max")
    )
    component_claims: list[dict[str, Any]] = []
    component_entities: list[str] = []
    for claim in lane_claims:
        primary_recent_pct_max = _lane_primary_recent_pct_max(claim)
        component_claims.append(
            {
                "slide_number": claim.get("slide_number"),
                "claim_text": claim.get("claim_text"),
                "aggregation_rule_id": (
                    claim.get("details", {}).get("aggregation_rule_id")
                    if isinstance(claim.get("details"), dict)
                    else None
                ),
                "component_entities": _emerging_lane_component_entities(claim),
                "primary_recent_pct_max": primary_recent_pct_max,
            }
        )
        component_entities.extend(_emerging_lane_component_entities(claim))
        if (
            ("modest" in segment.casefold() or "category reset" in segment.casefold())
            and primary_recent_pct_max is not None
            and modest_pct_max is not None
            and primary_recent_pct_max > modest_pct_max
        ):
            reasons.append(
                "lane exceeds modest-support threshold: "
                f"{primary_recent_pct_max:.1f}% > {modest_pct_max:.1f}%"
            )

    descriptor_fragments = _lane_descriptor_fragments(segment)
    lane_groups = _verified_emerging_lane_groups(claims)
    descriptor_support: list[dict[str, Any]] = []
    matched_group_numbers: list[int] = []
    if descriptor_fragments:
        for descriptor in descriptor_fragments:
            matched_group = _best_lane_group_for_descriptor(descriptor, lane_groups)
            if matched_group is None:
                reasons.append(
                    f"lane descriptor did not resolve to a verified lane group: {descriptor}"
                )
                continue
            matched_group_numbers.append(matched_group["slide_number"])
            descriptor_support.append(
                {
                    "descriptor_text": descriptor,
                    "matched_slide_number": matched_group["slide_number"],
                    "matched_component_entities": matched_group["component_entities"],
                    "matched_claim_texts": matched_group["claim_texts"],
                }
            )
        if (
            expected_lane_count is not None
            and len(set(matched_group_numbers)) != expected_lane_count
        ):
            reasons.append(
                "lane descriptors did not map cleanly onto the expected number of lane groups"
            )

    aggregation_rule_id = (
        "emerging_lane_recap_v1" if descriptor_fragments else "emerging_lane_count_v1"
    )
    return {
        "status": "pass" if not reasons else "fail",
        "component_claims": component_claims,
        "component_entities": _unique_texts(component_entities),
        "descriptor_support": descriptor_support,
        "aggregation_rule_id": aggregation_rule_id,
        "cohort_basis": "recent_vs_rest",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "verified lane-defining summaries counted across the deck with primary recent-share ceiling"
        ),
        "expected_lane_count": expected_lane_count,
        "observed_lane_count": observed_lane_count,
        "reasons": reasons,
    }


def _resolve_deck_level_emerging_lane_summaries(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue
        lane_result = _validate_cross_lane_emerging_summary_from_claims(
            claim_text,
            updated_claims,
        )
        if lane_result is None:
            remaining_unresolved.append(item)
            continue
        if lane_result["status"] == "warning":
            details = dict(item.get("details") or {})
            details.update(
                {
                    "message": _normalize_text(lane_result.get("message")),
                    "threshold_policy": lane_result.get("threshold_policy"),
                    "component_claims": lane_result.get("component_claims", []),
                }
            )
            refreshed_item = dict(item)
            refreshed_item["claim_family"] = "emerging_lane_summary"
            refreshed_item["details"] = details
            remaining_unresolved.append(refreshed_item)
            continue

        updated_claims.append(
            {
                **item,
                "status": (
                    "verified" if lane_result["status"] == "pass" else "contradicted"
                ),
                "claim_family": "emerging_lane_summary",
                "details": {
                    "component_claims": lane_result.get("component_claims", []),
                    "component_entities": lane_result.get("component_entities", []),
                    "descriptor_support": lane_result.get("descriptor_support", []),
                    "aggregation_rule_id": lane_result.get("aggregation_rule_id"),
                    "cohort_basis": lane_result.get("cohort_basis"),
                    "threshold_policy": lane_result.get("threshold_policy"),
                    "ranking_basis": lane_result.get("ranking_basis"),
                    "expected_lane_count": lane_result.get("expected_lane_count"),
                    "observed_lane_count": lane_result.get("observed_lane_count"),
                    "comparison_outcome": lane_result["status"],
                    "reasons": lane_result.get("reasons", []),
                },
            }
        )

    return updated_claims, remaining_unresolved


def _stability_metric_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_prevalence_pct": 30.0,
        "max_abs_delta_pct_points": 15.0,
        "candidate_files": [
            "top_seller_mapped_attribute_comparison.csv",
            "mapped_attribute_comparison.csv",
            "resolved_core_comparison.csv",
            "filter_comparison.csv",
        ],
    }


def _looks_like_stability_metric_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "remain stable categories",
            "remain stable",
            "are ubiquitous",
            "weak discriminatory power",
            "table-stakes category grammar",
            "table stakes category grammar",
        )
    )


def _stability_fragment_tokens(fragment: str) -> set[str]:
    return _canonical_tokens(
        fragment,
        ignored_tokens={
            "categories",
            "category",
            "constant",
            "constants",
            "finish",
            "finishes",
            "form",
            "forms",
            "format",
            "formats",
            "stable",
        },
    )


def _stability_attribute_fragments(segment: str) -> list[str]:
    lowered = segment.casefold()
    base_text = segment
    for marker in (
        "remain stable categories",
        "remain stable",
        "are ubiquitous",
        "represent table-stakes",
        "represent table stakes",
    ):
        marker_index = lowered.find(marker)
        if marker_index >= 0:
            base_text = segment[:marker_index]
            break
    if ":" in base_text:
        base_text = base_text.split(":", 1)[1]
    base_text = _normalize_text(base_text)
    if not base_text:
        return []
    parts = re.split(r",|\band\b", base_text, flags=re.IGNORECASE)
    return [
        _normalize_text(part.strip(" .;:,-"))
        for part in parts
        if _stability_fragment_tokens(part)
    ]


def _stability_candidate_rows(
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    return _attribute_share_candidate_rows(frames)


def _candidate_delta_pct_points(candidate: dict[str, Any]) -> float | None:
    left = _candidate_percent_for_side(candidate, "left")
    right = _candidate_percent_for_side(candidate, "right")
    if left is not None and right is not None:
        return abs(left - right)
    delta = _float_or_none(candidate.get("row", {}).get("delta"))
    if delta is None:
        return None
    return abs(delta) * 100.0


def _best_stability_candidate(
    fragment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    fragment_tokens = _stability_fragment_tokens(fragment)
    if not fragment_tokens:
        return None
    canonical_fragment = _canonical_text(fragment)
    stripped_fragment = re.sub(
        r"\b(?:finish|finishes|form|forms|format|formats)\b",
        " ",
        _normalize_text(fragment),
        flags=re.IGNORECASE,
    )
    stripped_fragment_key = _canonical_text(stripped_fragment)

    scored: list[tuple[int, dict[str, Any]]] = []
    for candidate in _stability_candidate_rows(frames):
        label = _normalize_text(candidate.get("label"))
        label_tokens = _stability_fragment_tokens(label)
        overlap = fragment_tokens & label_tokens
        if not overlap:
            continue
        score = len(overlap) * 10
        if fragment_tokens <= label_tokens or label_tokens <= fragment_tokens:
            score += 25
        candidate_key = _canonical_text(label)
        if candidate_key == canonical_fragment:
            score += 30
        elif stripped_fragment_key and candidate_key == stripped_fragment_key:
            score += 28
        if candidate["file"] == "filter_comparison.csv":
            score += 7
        elif candidate["file"] == "resolved_core_comparison.csv":
            score += 4
        elif candidate["file"] in {
            "mapped_attribute_comparison.csv",
            "top_seller_mapped_attribute_comparison.csv",
        }:
            score -= 1
        score += _context_priority(fragment, candidate["file"])
        scored.append((score, candidate))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    tied = [candidate for score, candidate in scored if score == best_score]
    if len(tied) != 1:
        exact_matches = [
            candidate
            for candidate in tied
            if _canonical_text(candidate.get("label")) == _canonical_text(fragment)
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        return None
    return tied[0]


def _stability_support_details(
    *,
    fragment: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    left_role = "top_seller" if "pct_top_seller" in candidate["row"] else "recent"
    right_role = "other" if left_role == "top_seller" else "rest"
    return {
        "fragment_text": fragment,
        "entity": _normalize_text(candidate.get("label")),
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "cohort_basis": _candidate_source_cohort_basis(candidate),
        "cohort_rates": {
            left_role: _candidate_percent_for_role(candidate, left_role),
            right_role: _candidate_percent_for_role(candidate, right_role),
        },
        "delta_pct_points": _candidate_delta_pct_points(candidate),
        "package_values": _bundle_candidate_package_values(candidate),
    }


def _validate_stability_metric_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_stability_metric_claim(segment):
        return None

    fragments = _stability_attribute_fragments(segment)
    threshold_policy = _stability_metric_threshold_policy()
    if not fragments:
        return {
            "status": "warning",
            "message": "stability summary did not expose a deterministic attribute list",
            "threshold_policy": threshold_policy,
            "attribute_support": [],
        }

    reasons: list[str] = []
    supported_fragments = 0
    attribute_support: list[dict[str, Any]] = []
    for fragment in fragments:
        candidate = _best_stability_candidate(fragment, frames)
        if candidate is None:
            reasons.append(
                f"attribute fragment did not resolve to a deterministic prevalence row: {fragment}"
            )
            continue
        detail = _stability_support_details(fragment=fragment, candidate=candidate)
        attribute_support.append(detail)
        rates = [
            value
            for value in detail["cohort_rates"].values()
            if isinstance(value, (int, float))
        ]
        min_rate = min(rates) if rates else None
        delta_pp = _float_or_none(detail.get("delta_pct_points"))
        if min_rate is None:
            reasons.append(f"attribute prevalence is unavailable for: {fragment}")
            continue
        if min_rate < threshold_policy["minimum_prevalence_pct"]:
            reasons.append(
                f"attribute is not prevalent enough to count as stable: {fragment}"
            )
            continue
        if delta_pp is None or delta_pp > threshold_policy["max_abs_delta_pct_points"]:
            reasons.append(
                f"attribute delta exceeds weak-discrimination threshold: {fragment}"
            )
            continue
        supported_fragments += 1

    if supported_fragments == len(fragments):
        status = "pass"
    elif supported_fragments > 0 and supported_fragments >= len(fragments) - 1:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "attribute_support": attribute_support,
        "component_entities": [item["entity"] for item in attribute_support],
        "aggregation_rule_id": "stability_metric_list_v1",
        "threshold_policy": threshold_policy,
        "ranking_basis": "attribute prevalence rows with low cross-cohort deltas",
        "reasons": reasons,
    }


def _divergence_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_care_delta_pct_points": 8.0,
        "paired_bundle_requires_top_seller_absence": True,
        "care_attribute_labels": [
            "hydrating/moisturizing",
            "explicit hydrating language",
        ],
        "packaging_tokens": ["twist", "retractable"],
    }


def _looks_like_divergence_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "the divergence:",
            "primary difference between current winners and recent launches",
            "primary point of divergence",
            "primary identifier of recent movement",
            "explicit care framing",
            "hydration language",
        )
    )


def _exact_attribute_candidate_from_labels(
    labels: list[str],
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    targets = {_canonical_text(label) for label in labels if _canonical_text(label)}
    if not targets:
        return None
    matches = [
        candidate
        for candidate in _attribute_share_candidate_rows(frames)
        if _canonical_text(candidate.get("label")) in targets
    ]
    if len(matches) == 1:
        return matches[0]
    preferred = [
        candidate
        for candidate in matches
        if candidate["file"] == "top_seller_mapped_attribute_comparison.csv"
    ]
    if len(preferred) == 1:
        return preferred[0]
    return None


def _bundle_candidate_with_tokens(
    frames: dict[str, pl.DataFrame],
    *,
    required_tokens: set[str],
    file_prefix: str,
    segment: str = "",
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for file_name in (
        "innovation_pairs.csv",
        "innovation_triples.csv",
        "top_seller_pairs.csv",
        "top_seller_triples.csv",
    ):
        if not file_name.startswith(file_prefix):
            continue
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get("bundle_label"))
            if required_tokens <= _canonical_tokens(label):
                matches.append(
                    {
                        "file": file_name,
                        "row": row,
                        "label": label,
                    }
                )
    if matches:
        min_part_count = min(
            _candidate_bundle_part_count(candidate) for candidate in matches
        )
        matches = [
            candidate
            for candidate in matches
            if _candidate_bundle_part_count(candidate) == min_part_count
        ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return _select_tied_bundle_candidate(segment, matches)
    return None


def _validate_divergence_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_divergence_summary_claim(segment):
        return None

    lowered = segment.casefold()
    threshold_policy = _divergence_threshold_policy()
    reasons: list[str] = []
    component_entities: list[str] = []
    attribute_support: list[dict[str, Any]] = []
    row_support: list[dict[str, Any]] = []

    if any(
        marker in lowered
        for marker in (
            "care framing",
            "hydration language",
            "care language",
            "primary identifier of recent movement",
        )
    ):
        care_candidate = _exact_attribute_candidate_from_labels(
            threshold_policy["care_attribute_labels"],
            frames,
        )
        if care_candidate is None:
            reasons.append(
                "care-language divergence did not resolve to a deterministic attribute row"
            )
        else:
            delta_pp = _candidate_delta_pct_points(care_candidate)
            attribute_support.append(
                {
                    "concept": "care_language",
                    "source_file": care_candidate["file"],
                    "matched_row_keys": _candidate_row_keys(care_candidate),
                    "cohort_basis": _candidate_source_cohort_basis(care_candidate),
                    "expected_numeric_values": {
                        "delta_pct_points": delta_pp,
                        "top_seller": _candidate_percent_for_role(
                            care_candidate,
                            "top_seller",
                        ),
                        "other": _candidate_percent_for_role(care_candidate, "other"),
                        "recent": _candidate_percent_for_role(care_candidate, "recent"),
                        "rest": _candidate_percent_for_role(care_candidate, "rest"),
                    },
                    "package_values": _bundle_candidate_package_values(care_candidate),
                }
            )
            component_entities.append(_normalize_text(care_candidate.get("label")))
            if (
                delta_pp is None
                or delta_pp < threshold_policy["minimum_care_delta_pct_points"]
            ):
                reasons.append(
                    "care-language divergence is below the configured threshold"
                )

    if any(
        marker in lowered
        for marker in (
            "retractable",
            "twist-up",
            "twist up",
            "packaging",
        )
    ):
        pairing_candidate = _bundle_candidate_with_tokens(
            frames,
            required_tokens={"hydrating", "moisturizing", "twist", "retractable"},
            file_prefix="innovation_",
            segment=segment,
        ) or _bundle_candidate_with_tokens(
            frames,
            required_tokens={"hydrating", "moisturizing", "twist"},
            file_prefix="innovation_",
            segment=segment,
        )
        if pairing_candidate is None:
            reasons.append(
                "hydration-plus-packaging divergence did not resolve to an innovation bundle row"
            )
        else:
            component_entities.append(_normalize_text(pairing_candidate.get("label")))
            paired_detail = {
                "concept": "care_packaging_pair",
                "source_file": pairing_candidate["file"],
                "matched_row_keys": _candidate_row_keys(pairing_candidate),
                "package_values": _bundle_candidate_package_values(pairing_candidate),
                "zero_occurrence_check": [],
            }
            if threshold_policy["paired_bundle_requires_top_seller_absence"]:
                top_seller_match = _bundle_candidate_with_tokens(
                    frames,
                    required_tokens={"hydrating", "moisturizing", "twist"},
                    file_prefix="top_seller_",
                    segment=segment,
                )
                zero_check = {
                    "cohort": "top_seller",
                    "matched_row_keys": (
                        _candidate_row_keys(top_seller_match)
                        if top_seller_match is not None
                        else None
                    ),
                    "passed": top_seller_match is None,
                }
                paired_detail["zero_occurrence_check"].append(zero_check)
                if not zero_check["passed"]:
                    reasons.append(
                        "hydration-plus-packaging bundle still recurs in top-seller rows"
                    )
            row_support.append(paired_detail)

    supported_components = int(bool(attribute_support)) + int(bool(row_support))
    required_components = int(
        any(
            marker in lowered
            for marker in (
                "care framing",
                "hydration language",
                "care language",
                "primary identifier of recent movement",
            )
        )
    ) + int(
        any(
            marker in lowered
            for marker in (
                "retractable",
                "twist-up",
                "twist up",
                "packaging",
            )
        )
    )
    if supported_components == required_components and not reasons:
        status = "pass"
    elif supported_components > 0:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "attribute_support": attribute_support,
        "row_support": row_support,
        "component_entities": _unique_texts(component_entities),
        "aggregation_rule_id": "divergence_explicit_care_v1",
        "cohort_basis": "winner_vs_innovation",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "care-language delta rows plus innovation bundle absence against top-seller rows"
        ),
        "reasons": reasons,
    }


def _emerging_signal_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_recent_brand_count": 2,
        "minimum_count_recent": 2,
        "minimum_prevalence_ratio": 1.2,
        "requires_positive_recent_vs_rest_delta": True,
        "source_files": ["innovation_pairs.csv", "innovation_triples.csv"],
    }


def _looks_like_emerging_signal_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "credible emerging signal",
            "emerging layer",
            "emerging signal",
            "integration of",
            "recent product additions reinforce",
            "recent product introductions reinforce",
            "secondary layer",
            "secondary, thinner emerging lane",
            "strongest emerging signal",
        )
    )


def _innovation_bundle_label_tokens(frames: dict[str, pl.DataFrame]) -> set[str]:
    tokens: set[str] = set()
    for file_name in ("innovation_pairs.csv", "innovation_triples.csv"):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for label in df.get_column("bundle_label").drop_nulls().to_list():
            tokens.update(_summary_synthesis_support_tokens(label))
    return tokens


def _emerging_signal_requested_tokens(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> set[str]:
    package_tokens = _innovation_bundle_label_tokens(frames)
    if not package_tokens:
        return set()
    return _summary_synthesis_support_tokens(segment) & package_tokens


def _candidate_recent_over_rest_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    recent_pct = _percent_from_fraction(row.get("pct_recent"))
    rest_pct = _percent_from_fraction(row.get("pct_rest"))
    delta_pct_points = (
        recent_pct - rest_pct
        if recent_pct is not None and rest_pct is not None
        else None
    )
    prevalence_ratio = _float_or_none(row.get("prevalence_ratio"))
    if prevalence_ratio is None and recent_pct is not None and rest_pct is not None:
        if rest_pct > 0:
            prevalence_ratio = recent_pct / rest_pct
        elif recent_pct > 0:
            prevalence_ratio = float("inf")
    return {
        "pct_recent": recent_pct,
        "pct_rest": rest_pct,
        "delta_pct_points": delta_pct_points,
        "prevalence_ratio": prevalence_ratio,
        "count_recent": _int_or_none(row.get("count_recent")),
        "count_rest": _int_or_none(row.get("count_rest")),
        "recent_brand_count": _candidate_brand_span_for_role(candidate, "recent"),
        "rest_brand_count": _candidate_brand_span_for_role(candidate, "rest"),
        "insight_adjusted_signal_score": _float_or_none(
            row.get("insight_adjusted_signal_score")
        ),
    }


def _emerging_signal_candidate_passes_thresholds(
    candidate: dict[str, Any],
    threshold_policy: dict[str, Any],
) -> bool:
    metrics = _candidate_recent_over_rest_metrics(candidate)
    delta_pct_points = _float_or_none(metrics.get("delta_pct_points"))
    prevalence_ratio = _float_or_none(metrics.get("prevalence_ratio"))
    count_recent = _int_or_none(metrics.get("count_recent")) or 0
    recent_brand_count = _int_or_none(metrics.get("recent_brand_count")) or 0
    if threshold_policy["requires_positive_recent_vs_rest_delta"] and (
        delta_pct_points is None or delta_pct_points <= 0
    ):
        return False
    if (
        prevalence_ratio is None
        or prevalence_ratio < threshold_policy["minimum_prevalence_ratio"]
    ):
        return False
    return (
        count_recent >= threshold_policy["minimum_count_recent"]
        and recent_brand_count >= threshold_policy["minimum_recent_brand_count"]
    )


def _innovation_bundle_candidates_for_tokens(
    frames: dict[str, pl.DataFrame],
    requested_tokens: set[str],
) -> list[dict[str, Any]]:
    if not requested_tokens:
        return []

    candidates: list[dict[str, Any]] = []
    for file_name in ("innovation_pairs.csv", "innovation_triples.csv"):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get("bundle_label"))
            label_tokens = _summary_synthesis_support_tokens(label)
            overlap = requested_tokens & label_tokens
            if not overlap:
                continue
            candidate = {
                "file": file_name,
                "row": row,
                "kind": "bundle",
                "label": label,
                "matched_tokens": sorted(overlap),
            }
            metrics = _candidate_recent_over_rest_metrics(candidate)
            prevalence_ratio = _float_or_none(metrics.get("prevalence_ratio"))
            ratio_score = (
                min(prevalence_ratio, 100.0)
                if prevalence_ratio is not None and math.isfinite(prevalence_ratio)
                else 100.0
            )
            score = (
                len(overlap) * 10_000
                + (_float_or_none(metrics.get("insight_adjusted_signal_score")) or 0.0)
                + (_float_or_none(metrics.get("delta_pct_points")) or 0.0)
                + ratio_score
            )
            candidates.append({**candidate, "score": score})

    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            len(candidate["matched_tokens"]),
            _normalize_text(candidate["label"]),
        ),
        reverse=True,
    )
    return candidates


def _selected_emerging_signal_support_rows(
    candidates: list[dict[str, Any]],
    requested_tokens: set[str],
    *,
    threshold_policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    covered_tokens: set[str] = set()
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_tokens = set(candidate["matched_tokens"])
        if candidate_tokens <= covered_tokens:
            continue
        if not _emerging_signal_candidate_passes_thresholds(
            candidate,
            threshold_policy,
        ):
            continue
        selected.append(candidate)
        covered_tokens.update(candidate_tokens)
        if requested_tokens <= covered_tokens:
            break
    return selected, covered_tokens


def _emerging_signal_row_support(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = _candidate_recent_over_rest_metrics(candidate)
    return {
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "matched_tokens": candidate["matched_tokens"],
        "package_values": _bundle_candidate_package_values(candidate),
        "computed_values": {
            key: (
                round(value, 4)
                if isinstance(value, float) and math.isfinite(value)
                else value
            )
            for key, value in metrics.items()
        },
    }


def _validate_emerging_signal_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_emerging_signal_summary_claim(segment):
        return None

    threshold_policy = _emerging_signal_summary_threshold_policy()
    requested_tokens = _emerging_signal_requested_tokens(segment, frames)
    if not requested_tokens:
        return None

    candidates = _innovation_bundle_candidates_for_tokens(frames, requested_tokens)
    selected, covered_tokens = _selected_emerging_signal_support_rows(
        candidates,
        requested_tokens,
        threshold_policy=threshold_policy,
    )
    missing_tokens = sorted(requested_tokens - covered_tokens)
    row_support = [_emerging_signal_row_support(candidate) for candidate in selected]
    component_entities = _unique_texts(candidate["label"] for candidate in selected)

    reasons: list[str] = []
    if missing_tokens:
        reasons.append(
            "innovation package rows did not support all named emerging-signal tokens"
        )
    if not row_support:
        reasons.append(
            "named emerging signal lacks recent-over-rest innovation bundle support"
        )

    lowered = segment.casefold()
    if not row_support:
        status = "fail"
    elif missing_tokens or "most credible" in lowered or "strongest" in lowered:
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "row_support": row_support,
        "component_entities": component_entities,
        "aggregation_rule_id": "emerging_signal_summary_v1",
        "cohort_basis": "recent_vs_rest",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "innovation bundle rows with positive recent-over-rest delta, "
            "minimum recent count, minimum recent brand count, and minimum "
            "prevalence ratio"
        ),
        "missing_components": missing_tokens,
        "reasons": reasons,
    }


def _current_winner_format_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_top_seller_brand_count": 2,
        "minimum_count_top_seller": 3,
        "minimum_prevalence_ratio": 1.2,
        "requires_positive_top_seller_vs_other_delta": True,
        "source_files": ["top_seller_pairs.csv", "top_seller_triples.csv"],
    }


def _looks_like_current_winner_format_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "current market winners",
            "current top-seller architecture",
            "current winner format",
            "current winning format",
            "current winning formats",
            "dominant shelf signals",
            "top-seller architecture",
            "winning format",
            "winning formats",
        )
    )


def _top_seller_bundle_label_tokens(frames: dict[str, pl.DataFrame]) -> set[str]:
    tokens: set[str] = set()
    for file_name in ("top_seller_pairs.csv", "top_seller_triples.csv"):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for label in df.get_column("bundle_label").drop_nulls().to_list():
            tokens.update(_summary_synthesis_support_tokens(label))
    return tokens


def _current_winner_format_requested_tokens(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> set[str]:
    package_tokens = _top_seller_bundle_label_tokens(frames)
    if not package_tokens:
        return set()
    return _summary_synthesis_support_tokens(segment) & package_tokens


def _candidate_top_seller_vs_other_metrics(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    row = candidate["row"]
    top_seller_pct = _percent_from_fraction(row.get("pct_top_seller"))
    other_pct = _percent_from_fraction(row.get("pct_other"))
    delta_pct_points = (
        top_seller_pct - other_pct
        if top_seller_pct is not None and other_pct is not None
        else None
    )
    prevalence_ratio = _float_or_none(row.get("prevalence_ratio"))
    if (
        prevalence_ratio is None
        and top_seller_pct is not None
        and other_pct is not None
    ):
        if other_pct > 0:
            prevalence_ratio = top_seller_pct / other_pct
        elif top_seller_pct > 0:
            prevalence_ratio = float("inf")
    return {
        "pct_top_seller": top_seller_pct,
        "pct_other": other_pct,
        "delta_pct_points": delta_pct_points,
        "prevalence_ratio": prevalence_ratio,
        "count_top_seller": _int_or_none(row.get("count_top_seller")),
        "count_other": _int_or_none(row.get("count_other")),
        "top_seller_brand_count": _candidate_brand_span_for_role(
            candidate,
            "top_seller",
        ),
        "other_brand_count": _candidate_brand_span_for_role(candidate, "other"),
        "insight_adjusted_signal_score": _float_or_none(
            row.get("insight_adjusted_signal_score")
        ),
    }


def _current_winner_format_candidate_passes_thresholds(
    candidate: dict[str, Any],
    threshold_policy: dict[str, Any],
) -> bool:
    metrics = _candidate_top_seller_vs_other_metrics(candidate)
    delta_pct_points = _float_or_none(metrics.get("delta_pct_points"))
    prevalence_ratio = _float_or_none(metrics.get("prevalence_ratio"))
    count_top_seller = _int_or_none(metrics.get("count_top_seller")) or 0
    top_seller_brand_count = _int_or_none(metrics.get("top_seller_brand_count")) or 0
    if threshold_policy["requires_positive_top_seller_vs_other_delta"] and (
        delta_pct_points is None or delta_pct_points <= 0
    ):
        return False
    if (
        prevalence_ratio is None
        or prevalence_ratio < threshold_policy["minimum_prevalence_ratio"]
    ):
        return False
    return (
        count_top_seller >= threshold_policy["minimum_count_top_seller"]
        and top_seller_brand_count >= threshold_policy["minimum_top_seller_brand_count"]
    )


def _top_seller_bundle_candidates_for_tokens(
    frames: dict[str, pl.DataFrame],
    requested_tokens: set[str],
) -> list[dict[str, Any]]:
    if not requested_tokens:
        return []

    candidates: list[dict[str, Any]] = []
    for file_name in ("top_seller_pairs.csv", "top_seller_triples.csv"):
        df = frames[file_name]
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get("bundle_label"))
            label_tokens = _summary_synthesis_support_tokens(label)
            overlap = requested_tokens & label_tokens
            if not overlap:
                continue
            candidate = {
                "file": file_name,
                "row": row,
                "kind": "bundle",
                "label": label,
                "matched_tokens": sorted(overlap),
            }
            metrics = _candidate_top_seller_vs_other_metrics(candidate)
            prevalence_ratio = _float_or_none(metrics.get("prevalence_ratio"))
            ratio_score = (
                min(prevalence_ratio, 100.0)
                if prevalence_ratio is not None and math.isfinite(prevalence_ratio)
                else 100.0
            )
            score = (
                len(overlap) * 10_000
                + (_int_or_none(metrics.get("count_top_seller")) or 0)
                + (_int_or_none(metrics.get("top_seller_brand_count")) or 0)
                + (_float_or_none(metrics.get("delta_pct_points")) or 0.0)
                + ratio_score
            )
            candidates.append({**candidate, "score": score})

    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            len(candidate["matched_tokens"]),
            _normalize_text(candidate["label"]),
        ),
        reverse=True,
    )
    return candidates


def _selected_current_winner_format_support_rows(
    candidates: list[dict[str, Any]],
    requested_tokens: set[str],
    *,
    threshold_policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    covered_tokens: set[str] = set()
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_tokens = set(candidate["matched_tokens"])
        if candidate_tokens <= covered_tokens:
            continue
        if not _current_winner_format_candidate_passes_thresholds(
            candidate,
            threshold_policy,
        ):
            continue
        selected.append(candidate)
        covered_tokens.update(candidate_tokens)
        if requested_tokens <= covered_tokens:
            break
    return selected, covered_tokens


def _current_winner_format_row_support(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = _candidate_top_seller_vs_other_metrics(candidate)
    return {
        "source_file": candidate["file"],
        "matched_row_keys": _candidate_row_keys(candidate),
        "matched_tokens": candidate["matched_tokens"],
        "package_values": _bundle_candidate_package_values(candidate),
        "computed_values": {
            key: (
                round(value, 4)
                if isinstance(value, float) and math.isfinite(value)
                else value
            )
            for key, value in metrics.items()
        },
    }


def _validate_current_winner_format_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_current_winner_format_summary_claim(segment):
        return None

    threshold_policy = _current_winner_format_summary_threshold_policy()
    requested_tokens = _current_winner_format_requested_tokens(segment, frames)
    if not requested_tokens:
        return None

    candidates = _top_seller_bundle_candidates_for_tokens(frames, requested_tokens)
    selected, covered_tokens = _selected_current_winner_format_support_rows(
        candidates,
        requested_tokens,
        threshold_policy=threshold_policy,
    )
    missing_tokens = sorted(requested_tokens - covered_tokens)
    row_support = [
        _current_winner_format_row_support(candidate) for candidate in selected
    ]
    component_entities = _unique_texts(candidate["label"] for candidate in selected)

    reasons: list[str] = []
    if missing_tokens:
        reasons.append(
            "top-seller package rows did not support all named winner-format tokens"
        )
    if not row_support:
        reasons.append(
            "named winner format lacks top-seller bundle support above threshold"
        )

    requested_part_count = max(1, len(requested_tokens))
    broad_containing_support = any(
        _candidate_bundle_part_count(candidate) > requested_part_count
        for candidate in selected
    )
    lowered = segment.casefold()
    if not row_support:
        status = "fail"
    elif (
        missing_tokens
        or broad_containing_support
        or "cleanest" in lowered
        or "strongest" in lowered
    ):
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "row_support": row_support,
        "component_entities": component_entities,
        "aggregation_rule_id": "current_winner_format_summary_v1",
        "cohort_basis": "top_seller_vs_other",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "top-seller bundle rows with positive top-seller-over-other delta, "
            "minimum top-seller count, minimum top-seller brand count, and "
            "minimum prevalence ratio"
        ),
        "missing_components": missing_tokens,
        "reasons": reasons,
    }


def _pdp_descriptor_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_topic_match_count": 2,
        "minimum_topic_brand_count": 2,
        "source_files": ["top_seller_products.csv"],
        "context_source": "same-slide deterministic winner-format support",
    }


def _looks_like_pdp_descriptor_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    if not any(
        marker in lowered
        for marker in ("product detail pages", "pdp", "pdp text", "detail pages")
    ):
        return False
    return any(
        marker in lowered for marker in ("reinforce", "support", "validate", "confirm")
    )


def _pdp_descriptor_requested_topics(segment: str) -> list[str]:
    lowered = segment.casefold()
    requested: list[str] = []
    if "savory" in lowered and "gravy" in lowered:
        requested.append("savory_gravy")
    if "meat" in lowered and "aroma" in lowered:
        requested.append("meat_aroma")
    if any(token in lowered for token in ("hydration", "hydrating", "moisture")):
        requested.append("hydration")
    return requested


def _same_slide_component_labels(
    claims: list[dict[str, Any]],
    *,
    source_slide_number: int | None,
) -> list[str]:
    if source_slide_number is None:
        return []

    labels: list[str] = []
    for claim in claims:
        if _int_or_none(claim.get("slide_number")) != source_slide_number:
            continue
        if claim.get("status") not in {"verified", "partially_backed"}:
            continue
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        component_entities = (
            details.get("component_entities")
            if isinstance(details.get("component_entities"), list)
            else []
        )
        labels.extend(_normalize_text(entity) for entity in component_entities)
        row_support = (
            details.get("row_support")
            if isinstance(details.get("row_support"), list)
            else []
        )
        for support in row_support:
            if not isinstance(support, dict):
                continue
            matched_row_keys = (
                support.get("matched_row_keys")
                if isinstance(support.get("matched_row_keys"), dict)
                else {}
            )
            labels.append(_normalize_text(matched_row_keys.get("bundle_label")))
    return _unique_texts(label for label in labels if label)


def _pdp_descriptor_row_blob(row: dict[str, Any]) -> str:
    return _fold_text(
        " ".join(
            _normalize_text(row.get(column))
            for column in _PDP_DESCRIPTOR_TEXT_COLUMNS
            if row.get(column)
        )
    )


def _pdp_descriptor_row_tokens(row: dict[str, Any]) -> set[str]:
    return _canonical_tokens(
        " ".join(
            _normalize_text(row.get(column))
            for column in _PDP_DESCRIPTOR_TEXT_COLUMNS
            if row.get(column)
        )
    )


def _pdp_descriptor_row_has_label_token(
    *,
    token: str,
    row_tokens: set[str],
) -> bool:
    if token == "can":
        return bool({"can", "cans", "canned"} & row_tokens)
    if token == "tray":
        return bool({"tray", "trays"} & row_tokens)
    return token in row_tokens


def _pdp_descriptor_row_matches_label(
    row: dict[str, Any],
    label: str,
) -> bool:
    label_tokens = _summary_synthesis_support_tokens(label)
    if not label_tokens:
        return False
    row_tokens = _pdp_descriptor_row_tokens(row)
    return all(
        _pdp_descriptor_row_has_label_token(token=token, row_tokens=row_tokens)
        for token in label_tokens
    )


def _pdp_descriptor_matching_rows(
    frames: dict[str, pl.DataFrame],
    *,
    labels: list[str],
) -> list[dict[str, Any]]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "product_name" not in columns:
        return []

    rows: list[dict[str, Any]] = []
    seen_products: set[tuple[str, str]] = set()
    for row in df.to_dicts():
        matching_labels = [
            label for label in labels if _pdp_descriptor_row_matches_label(row, label)
        ]
        if not matching_labels:
            continue
        key = (
            _normalize_text(row.get("parent_product_id"))
            or _normalize_text(row.get("listing_identity")),
            _canonical_text(row.get("product_name")),
        )
        if key in seen_products:
            continue
        seen_products.add(key)
        rows.append(
            {
                "source_file": "top_seller_products.csv",
                "product_name": _normalize_text(row.get("product_name")),
                "brand": _normalize_text(row.get("brand")),
                "matched_labels": matching_labels,
                "row": row,
            }
        )
    return rows


def _pdp_descriptor_topic_matches(blob: str, topic: str) -> bool:
    keyword_groups = _PDP_DESCRIPTOR_TOPIC_KEYWORD_GROUPS.get(topic, ())
    return all(any(keyword in blob for keyword in group) for group in keyword_groups)


def _pdp_descriptor_topic_support(
    rows: list[dict[str, Any]],
    requested_topics: list[str],
) -> dict[str, list[dict[str, Any]]]:
    support: dict[str, list[dict[str, Any]]] = {topic: [] for topic in requested_topics}
    for row in rows:
        blob = _pdp_descriptor_row_blob(row["row"])
        if not blob:
            continue
        for topic in requested_topics:
            if not _pdp_descriptor_topic_matches(blob, topic):
                continue
            support[topic].append(
                {
                    "source_file": row["source_file"],
                    "product_name": row["product_name"],
                    "brand": row["brand"],
                    "matched_labels": row["matched_labels"],
                }
            )
    return support


def _pdp_descriptor_topic_counts(
    topic_support: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    return {
        topic: {
            "match_count": len(rows),
            "brand_count": len(
                {
                    _normalize_text(row.get("brand"))
                    for row in rows
                    if _normalize_text(row.get("brand"))
                }
            ),
        }
        for topic, rows in topic_support.items()
    }


def _validate_pdp_descriptor_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
    claims: list[dict[str, Any]],
    *,
    source_slide_number: int | None = None,
) -> dict[str, Any] | None:
    if not _looks_like_pdp_descriptor_summary_claim(segment):
        return None

    requested_topics = _pdp_descriptor_requested_topics(segment)
    if not requested_topics:
        return None

    context_labels = _same_slide_component_labels(
        claims,
        source_slide_number=source_slide_number,
    )
    threshold_policy = _pdp_descriptor_summary_threshold_policy()
    if not context_labels:
        return {
            "status": "warning",
            "message": "PDP descriptor summary has no same-slide deterministic winner context",
            "threshold_policy": threshold_policy,
        }

    rows = _pdp_descriptor_matching_rows(frames, labels=context_labels)
    topic_support = _pdp_descriptor_topic_support(rows, requested_topics)
    topic_counts = _pdp_descriptor_topic_counts(topic_support)

    reasons: list[str] = []
    supported_topics: list[str] = []
    for topic in requested_topics:
        counts = topic_counts.get(topic, {})
        if (
            counts.get("match_count", 0)
            >= threshold_policy["minimum_topic_match_count"]
            and counts.get("brand_count", 0)
            >= threshold_policy["minimum_topic_brand_count"]
        ):
            supported_topics.append(topic)
            continue
        reasons.append(f"PDP descriptor support below threshold for topic: {topic}")

    if len(supported_topics) == len(requested_topics):
        status = "pass"
    elif supported_topics:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "row_support": [
            {
                "source_file": "top_seller_products.csv",
                "context_labels": context_labels,
                "matched_product_count": len(rows),
                "matched_brand_count": len(
                    {
                        _normalize_text(row.get("brand"))
                        for row in rows
                        if _normalize_text(row.get("brand"))
                    }
                ),
                "topic_support": {
                    topic: support_rows[:8]
                    for topic, support_rows in topic_support.items()
                },
                "topic_counts": topic_counts,
            }
        ],
        "component_entities": context_labels,
        "aggregation_rule_id": "pdp_descriptor_summary_v1",
        "cohort_basis": "top_seller_product_detail_pages",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "top-seller product rows matching same-slide winner-format bundles; "
            "each requested PDP descriptor topic must meet product-count and "
            "brand-count thresholds"
        ),
        "missing_components": [
            topic for topic in requested_topics if topic not in supported_topics
        ],
        "reasons": reasons,
    }


def _format_constraint_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_product_count": 5,
        "minimum_brand_count": 2,
        "maximum_packaging_top_seller_share": 0.35,
        "minimum_top_brand_share_for_brand_constrained": 0.4,
        "minimum_top_three_brand_share_for_brand_constrained": 0.7,
        "source_files": ["top_seller_products.csv"],
    }


def _looks_like_format_constraint_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return (
        "winners" in lowered
        and any(marker in lowered for marker in ("product-real", "product real"))
        and "brand" in lowered
        and "constrained" in lowered
        and "packaging" in lowered
    )


def _format_constraint_candidate_product_columns(
    columns: list[str],
) -> list[str]:
    blocked_markers = (
        "id",
        "url",
        "image",
        "description",
        "name",
        "retailer",
        "category",
        "rank",
        "share",
        "price",
        "rating",
        "review",
        "sales",
        "status",
    )
    candidates: list[str] = []
    for column in columns:
        canonical_column = _canonical_text(column)
        if any(marker in canonical_column for marker in blocked_markers):
            continue
        candidates.append(column)
    return candidates


def _format_constraint_attribute_value_candidates(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty():
        return []

    segment_folded = _fold_text(segment)
    segment_tokens = _summary_synthesis_support_tokens(segment)
    candidates: list[dict[str, Any]] = []
    for column in _format_constraint_candidate_product_columns(columns):
        values = _unique_texts(
            _normalize_text(value)
            for value in df.get_column(column).drop_nulls().to_list()
            if _normalize_text(value)
        )
        values = [value for value in values if len(value) <= 80]
        if not values or len(values) > 80:
            continue
        for value in values:
            value_tokens = _summary_synthesis_support_tokens(value)
            if not value_tokens:
                continue
            exact_phrase_match = _fold_text(value) in segment_folded
            token_match = value_tokens <= segment_tokens
            if not exact_phrase_match and not token_match:
                continue
            row_count = sum(
                1
                for row in df.to_dicts()
                if _product_cell_matches_bundle_value(row.get(column), value)
            )
            candidates.append(
                {
                    "column": column,
                    "value": value,
                    "tokens": sorted(value_tokens),
                    "row_count": row_count,
                    "score": (
                        (1000 if exact_phrase_match else 0)
                        + len(value_tokens) * 100
                        + row_count
                    ),
                }
            )

    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            candidate["row_count"],
            _normalize_text(candidate["column"]),
            _normalize_text(candidate["value"]),
        ),
        reverse=True,
    )
    return candidates


def _format_constraint_product_rows(
    frames: dict[str, pl.DataFrame],
    *,
    column: str,
    value: str,
) -> list[dict[str, Any]]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or column not in columns:
        return []
    return [
        row
        for row in df.to_dicts()
        if _product_cell_matches_bundle_value(row.get(column), value)
    ]


def _format_constraint_brand_counts(
    rows: list[dict[str, Any]],
) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        brand = _normalize_text(row.get("brand"))
        if not brand:
            continue
        counts[brand] = counts.get(brand, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


def _format_constraint_summary_metrics(
    frames: dict[str, pl.DataFrame],
    *,
    column: str,
    value: str,
) -> dict[str, Any]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    rows = _format_constraint_product_rows(frames, column=column, value=value)
    brand_counts = _format_constraint_brand_counts(rows)
    product_count = len(rows)
    base_count = get_row_count(df) if not df.is_empty() else 0
    top_brand_count = brand_counts[0][1] if brand_counts else 0
    top_three_count = sum(count for _brand, count in brand_counts[:3])
    return {
        "product_count": product_count,
        "top_seller_base": base_count,
        "top_seller_share": product_count / base_count if base_count else None,
        "brand_count": len(brand_counts),
        "top_brand": brand_counts[0][0] if brand_counts else "",
        "top_brand_count": top_brand_count,
        "top_brand_share": top_brand_count / product_count if product_count else None,
        "top_three_brand_share": (
            top_three_count / product_count if product_count else None
        ),
        "top_brands": [
            {"brand": brand, "product_count": count}
            for brand, count in brand_counts[:5]
        ],
    }


def _validate_format_constraint_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_format_constraint_summary_claim(segment):
        return None

    candidates = _format_constraint_attribute_value_candidates(segment, frames)
    if not candidates:
        return None

    candidate = candidates[0]
    threshold_policy = _format_constraint_summary_threshold_policy()
    metrics = _format_constraint_summary_metrics(
        frames,
        column=candidate["column"],
        value=candidate["value"],
    )
    reasons: list[str] = []
    supported_components: list[str] = []

    product_count = _int_or_none(metrics.get("product_count")) or 0
    brand_count = _int_or_none(metrics.get("brand_count")) or 0
    top_seller_share = _float_or_none(metrics.get("top_seller_share"))
    top_brand_share = _float_or_none(metrics.get("top_brand_share"))
    top_three_brand_share = _float_or_none(metrics.get("top_three_brand_share"))

    if (
        product_count >= threshold_policy["minimum_product_count"]
        and brand_count >= threshold_policy["minimum_brand_count"]
    ):
        supported_components.append("product_real")
    else:
        reasons.append("named winner format has too few product rows or brands")

    packaging_column = "packaging" in _fold_text(candidate["column"])
    if (
        packaging_column
        and top_seller_share is not None
        and top_seller_share <= threshold_policy["maximum_packaging_top_seller_share"]
    ):
        supported_components.append("packaging_constrained")
    else:
        reasons.append(
            "named winner format is not a narrow packaging-type product cohort"
        )

    if (
        top_brand_share is not None
        and top_brand_share
        >= threshold_policy["minimum_top_brand_share_for_brand_constrained"]
    ) or (
        top_three_brand_share is not None
        and top_three_brand_share
        >= threshold_policy["minimum_top_three_brand_share_for_brand_constrained"]
    ):
        supported_components.append("brand_constrained")
    else:
        reasons.append("named winner format is not concentrated by brand")

    required_components = {
        "product_real",
        "packaging_constrained",
        "brand_constrained",
    }
    if required_components <= set(supported_components):
        status = "pass"
    elif supported_components:
        status = "partial"
    else:
        status = "fail"

    return {
        "status": status,
        "row_support": [
            {
                "source_file": "top_seller_products.csv",
                "matched_row_keys": {
                    "attribute_column": candidate["column"],
                    "attribute_value": candidate["value"],
                },
                "computed_values": {
                    key: (
                        round(value, 4)
                        if isinstance(value, float) and math.isfinite(value)
                        else value
                    )
                    for key, value in metrics.items()
                },
            }
        ],
        "component_entities": [candidate["value"]],
        "aggregation_rule_id": "format_constraint_summary_v1",
        "cohort_basis": "top_seller_products",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "top-seller product rows matching the named format; product-real "
            "requires product and brand support, packaging-constrained requires "
            "a narrow packaging-type cohort, and brand-constrained requires "
            "top-brand or top-three-brand concentration"
        ),
        "missing_components": sorted(required_components - set(supported_components)),
        "reasons": reasons,
    }


def _attribute_penetration_summary_threshold_policy() -> dict[str, Any]:
    return {
        "percent_tolerance_points": _PERCENT_TOLERANCE,
        "source_files": [
            "mapped_attribute_comparison.csv",
            "top_seller_mapped_attribute_comparison.csv",
        ],
    }


def _looks_like_attribute_penetration_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return "penetration" in lowered and bool(_percent_mentions(text))


def _attribute_penetration_row_percentages(row: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for role in ("recent", "rest", "top_seller", "other"):
        pct = _percent_from_fraction(row.get(f"pct_{role}"))
        if pct is not None:
            values[f"{role}_percent"] = pct

    recent_count = _int_or_none(row.get("count_recent"))
    rest_count = _int_or_none(row.get("count_rest"))
    recent_base = _int_or_none(row.get("recent_base"))
    rest_base = _int_or_none(row.get("rest_base"))
    if (
        recent_count is not None
        and rest_count is not None
        and recent_base is not None
        and rest_base is not None
        and recent_base + rest_base > 0
    ):
        values["combined_recent_rest_percent"] = (
            (recent_count + rest_count) / (recent_base + rest_base) * 100.0
        )

    top_seller_count = _int_or_none(row.get("count_top_seller"))
    other_count = _int_or_none(row.get("count_other"))
    top_seller_base = _int_or_none(row.get("top_seller_base"))
    other_base = _int_or_none(row.get("other_base"))
    if (
        top_seller_count is not None
        and other_count is not None
        and top_seller_base is not None
        and other_base is not None
        and top_seller_base + other_base > 0
    ):
        values["combined_top_seller_other_percent"] = (
            (top_seller_count + other_count) / (top_seller_base + other_base) * 100.0
        )
    return values


def _attribute_penetration_candidates(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    segment_folded = _fold_text(segment)
    segment_tokens = _summary_synthesis_support_tokens(segment)
    candidates: list[dict[str, Any]] = []
    for file_name in (
        "mapped_attribute_comparison.csv",
        "top_seller_mapped_attribute_comparison.csv",
    ):
        df = frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "attribute_value" not in columns:
            continue
        for row in df.to_dicts():
            attribute_value = _normalize_text(row.get("attribute_value"))
            if not attribute_value:
                continue
            value_tokens = _summary_synthesis_support_tokens(attribute_value)
            exact_match = _fold_text(attribute_value) in segment_folded
            token_match = bool(value_tokens) and value_tokens <= segment_tokens
            if not exact_match and not token_match:
                continue
            percentages = _attribute_penetration_row_percentages(row)
            if not percentages:
                continue
            candidates.append(
                {
                    "file": file_name,
                    "row": row,
                    "attribute_name": _normalize_text(row.get("attribute_name")),
                    "attribute_value": attribute_value,
                    "percentages": percentages,
                    "score": (
                        (1000 if exact_match else 0)
                        + len(value_tokens) * 100
                        + len(percentages)
                    ),
                }
            )
    candidates.sort(
        key=lambda candidate: (
            candidate["score"],
            _normalize_text(candidate["attribute_name"]),
            _normalize_text(candidate["attribute_value"]),
        ),
        reverse=True,
    )
    return candidates


def _attribute_penetration_expected_percentages_for_mention(
    mention: _PercentMention,
    percentages: dict[str, float],
) -> dict[str, float]:
    if mention.role:
        key = f"{mention.role}_percent"
        if key in percentages:
            return {key: percentages[key]}
    return percentages


def _attribute_penetration_row_support(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    return {
        "source_file": candidate["file"],
        "matched_row_keys": {
            "attribute_name": candidate["attribute_name"],
            "attribute_value": candidate["attribute_value"],
        },
        "package_values": {
            key: row.get(key)
            for key in (
                "count_recent",
                "count_rest",
                "recent_base",
                "rest_base",
                "count_top_seller",
                "count_other",
                "top_seller_base",
                "other_base",
            )
            if key in row
        },
        "computed_values": {
            key: round(value, 4)
            for key, value in candidate["percentages"].items()
            if math.isfinite(value)
        },
    }


def _validate_attribute_penetration_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_attribute_penetration_summary_claim(segment):
        return None

    mentions = _percent_mentions(segment)
    if not mentions:
        return None

    candidates = _attribute_penetration_candidates(segment, frames)
    if not candidates:
        return None

    matched = False
    reasons: list[str] = []
    for mention in mentions:
        expected_by_candidate: list[str] = []
        for candidate in candidates:
            expected_percentages = (
                _attribute_penetration_expected_percentages_for_mention(
                    mention,
                    candidate["percentages"],
                )
            )
            if any(
                _percent_matches(mention, expected)
                for expected in expected_percentages.values()
            ):
                matched = True
            expected_by_candidate.extend(
                _format_optional_percent(expected)
                for expected in expected_percentages.values()
            )
        if not matched:
            reasons.append(
                "penetration percent mismatch: expected one of "
                + ", ".join(_unique_texts(expected_by_candidate))
            )

    return {
        "status": "pass" if matched else "fail",
        "row_support": [
            _attribute_penetration_row_support(candidate)
            for candidate in candidates[:3]
        ],
        "component_entities": _unique_texts(
            candidate["attribute_value"] for candidate in candidates
        ),
        "aggregation_rule_id": "attribute_penetration_summary_v1",
        "cohort_basis": "mapped_attribute_comparison",
        "threshold_policy": _attribute_penetration_summary_threshold_policy(),
        "ranking_basis": (
            "mapped attribute rows matching the named modifier; stated "
            "penetration must match an explicit cohort percent or combined "
            "attribute penetration"
        ),
        "missing_components": [] if matched else ["penetration_percent"],
        "reasons": reasons,
    }


_MATERIAL_COMPOSITION_TEXT_COLUMNS = (
    "product_name",
    "product_name_norm",
    "material",
    "fabric",
    "description",
)


def _material_composition_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_cashmere_led_share": 0.8,
        "minimum_variant_product_count": 2,
        "minimum_variant_brand_count": 2,
        "source_files": ["top_seller_products.csv"],
    }


def _looks_like_material_composition_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return (
        "winning proposition" in lowered
        and "cashmere" in lowered
        and ("top-sellers" in lowered or "top sellers" in lowered)
        and any(marker in lowered for marker in ("wool/cashmere", "stretch", "blend"))
    )


def _material_composition_row_blob(row: dict[str, Any]) -> str:
    return _fold_text(
        " ".join(
            _normalize_text(row.get(column))
            for column in _MATERIAL_COMPOSITION_TEXT_COLUMNS
            if row.get(column)
        )
    )


def _material_variant_matches(blob: str) -> bool:
    return (
        ("wool" in blob and "cashmere" in blob) or "stretch" in blob or "blend" in blob
    )


def _material_composition_summary(
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "product_name" not in columns:
        return None

    rows = df.to_dicts()
    product_count = len(rows)
    cashmere_rows = [
        row for row in rows if "cashmere" in _material_composition_row_blob(row)
    ]
    variant_rows = [
        row
        for row in rows
        if _material_variant_matches(_material_composition_row_blob(row))
    ]
    variant_brands = {
        _normalize_text(row.get("brand"))
        for row in variant_rows
        if _normalize_text(row.get("brand"))
    }
    return {
        "product_count": product_count,
        "cashmere_product_count": len(cashmere_rows),
        "cashmere_product_share": (
            len(cashmere_rows) / product_count if product_count else None
        ),
        "variant_product_count": len(variant_rows),
        "variant_brand_count": len(variant_brands),
        "variant_products": [
            {
                "product_name": _normalize_text(row.get("product_name")),
                "brand": _normalize_text(row.get("brand")),
            }
            for row in variant_rows[:8]
        ],
    }


def _validate_material_composition_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_material_composition_summary_claim(segment):
        return None

    summary = _material_composition_summary(frames)
    if summary is None:
        return None

    threshold_policy = _material_composition_summary_threshold_policy()
    reasons: list[str] = []
    cashmere_share = _float_or_none(summary.get("cashmere_product_share"))
    if (
        cashmere_share is None
        or cashmere_share < threshold_policy["minimum_cashmere_led_share"]
    ):
        reasons.append("top-seller product text is not cashmere-led above threshold")
    if (_int_or_none(summary.get("variant_product_count")) or 0) < threshold_policy[
        "minimum_variant_product_count"
    ] or (_int_or_none(summary.get("variant_brand_count")) or 0) < threshold_policy[
        "minimum_variant_brand_count"
    ]:
        reasons.append(
            "wool/cashmere or stretch-blend variants are below product/brand thresholds"
        )

    return {
        "status": "pass" if not reasons else "fail",
        "row_support": [
            {
                "source_file": "top_seller_products.csv",
                "matched_row_keys": {
                    "cohort": "top_seller_products",
                    "material_terms": ["cashmere", "wool/cashmere", "stretch", "blend"],
                },
                "computed_values": {
                    "product_count": summary["product_count"],
                    "cashmere_product_count": summary["cashmere_product_count"],
                    "cashmere_product_share": (
                        round(summary["cashmere_product_share"], 4)
                        if summary["cashmere_product_share"] is not None
                        else None
                    ),
                    "variant_product_count": summary["variant_product_count"],
                    "variant_brand_count": summary["variant_brand_count"],
                },
                "variant_products": summary["variant_products"],
            }
        ],
        "component_entities": ["cashmere", "wool/cashmere", "stretch blend"],
        "aggregation_rule_id": "material_composition_summary_v1",
        "cohort_basis": "top_seller_product_text",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "top-seller product names and descriptions must be cashmere-led, "
            "with multiple products and brands supporting wool/cashmere, "
            "stretch, or blend variants"
        ),
        "missing_components": [] if not reasons else ["material_composition"],
        "reasons": reasons,
    }


def _contextual_product_brand_share_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_product_count": 3,
        "minimum_selector_count": 2,
        "approximate_whole_percent_tolerance_points": 3.0,
        "source_files": ["top_seller_products.csv"],
    }


def _looks_like_contextual_product_brand_share_claim(text: str) -> bool:
    lowered = text.casefold()
    return (
        "accounts for" in lowered
        and "matched top-seller set" in lowered
        and bool(_percent_mentions(text))
    )


def _contextual_product_selector_columns(columns: list[str]) -> list[str]:
    blocked_markers = (
        "also",
        "brand",
        "category",
        "children",
        "description",
        "id",
        "image",
        "inferred",
        "mapped",
        "name",
        "notintaxonomy",
        "other",
        "price",
        "rank",
        "rating",
        "retailer",
        "review",
        "sales",
        "secondary",
        "share",
        "status",
        "url",
        "unknown",
    )
    selectors: list[str] = []
    for column in columns:
        canonical_column = _canonical_text(column)
        if any(marker in canonical_column for marker in blocked_markers):
            continue
        selectors.append(column)
    return selectors


def _contextual_product_selector_candidates(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty():
        return []

    segment_folded = _fold_text(segment)
    segment_tokens = _summary_synthesis_support_tokens(segment)
    selectors: list[dict[str, Any]] = []
    for column in _contextual_product_selector_columns(columns):
        values = _unique_texts(
            _normalize_text(value)
            for value in df.get_column(column).drop_nulls().to_list()
            if _normalize_text(value)
        )
        values = [value for value in values if len(value) <= 80]
        if not values or len(values) > 120:
            continue
        for value in values:
            value_tokens = _summary_synthesis_support_tokens(value)
            if not value_tokens:
                continue
            exact_match = _fold_text(value) in segment_folded
            token_match = value_tokens <= segment_tokens
            if not exact_match and not token_match:
                continue
            selectors.append(
                {
                    "column": column,
                    "value": value,
                    "tokens": sorted(value_tokens),
                    "score": (1000 if exact_match else 0) + len(value_tokens) * 100,
                }
            )

    selectors.sort(
        key=lambda selector: (
            selector["score"],
            len(selector["tokens"]),
            _normalize_text(selector["column"]),
            _normalize_text(selector["value"]),
        ),
        reverse=True,
    )
    deduped: list[dict[str, Any]] = []
    used_columns: set[str] = set()
    for selector in selectors:
        column = _normalize_text(selector["column"])
        if column in used_columns:
            continue
        deduped.append(selector)
        used_columns.add(column)
    return deduped


def _contextual_product_rows_for_selectors(
    frames: dict[str, pl.DataFrame],
    selectors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    df = frames.get("top_seller_products.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty():
        return []
    rows: list[dict[str, Any]] = []
    for row in df.to_dicts():
        if all(
            selector["column"] in columns
            and _product_cell_matches_bundle_value(
                row.get(selector["column"]),
                selector["value"],
            )
            for selector in selectors
        ):
            rows.append(row)
    return rows


def _contextual_brand_share_percent_tolerance(
    segment: str,
    mention: _PercentMention,
) -> float:
    leading_context = segment[max(0, mention.span[0] - 12) : mention.span[0]]
    if re.search(r"(?:~|≈|about|approx\.?|around)\s*$", leading_context):
        return max(mention.tolerance, 3.0)
    if float(mention.value).is_integer():
        return max(mention.tolerance, 1.0)
    return mention.tolerance


def _validate_contextual_product_brand_share_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_contextual_product_brand_share_claim(segment):
        return None

    brand_name = _extract_accounts_for_brand_name(segment)
    if not brand_name:
        return None

    mentions = _percent_mentions(segment)
    if not mentions:
        return None
    mention = mentions[0]

    threshold_policy = _contextual_product_brand_share_threshold_policy()
    selectors = _contextual_product_selector_candidates(segment, frames)
    selectors = selectors[:4]
    if len(selectors) < threshold_policy["minimum_selector_count"]:
        return {
            "status": "warning",
            "message": "contextual brand-share claim has insufficient product selectors",
            "threshold_policy": threshold_policy,
        }

    rows = _contextual_product_rows_for_selectors(frames, selectors)
    brand_rows = [
        row
        for row in rows
        if _brand_names_compatible(brand_name, _normalize_text(row.get("brand")))
    ]
    product_count = len(rows)
    brand_count = len(brand_rows)
    observed_share = 100.0 * brand_count / product_count if product_count > 0 else None
    tolerance = _contextual_brand_share_percent_tolerance(segment, mention)
    reasons: list[str] = []
    if product_count < threshold_policy["minimum_product_count"]:
        reasons.append("matched product set is below minimum product count")
    if not _approx_equal(mention.value, observed_share, tolerance):
        reasons.append(
            "dominant-brand share mismatch: expected "
            f"{_format_optional_percent(observed_share)}"
        )

    return {
        "status": "pass" if not reasons else "fail",
        "row_support": [
            {
                "source_file": "top_seller_products.csv",
                "matched_row_keys": {
                    "brand": brand_name,
                    "selectors": [
                        {
                            "column": selector["column"],
                            "value": selector["value"],
                        }
                        for selector in selectors
                    ],
                },
                "computed_values": {
                    "matched_product_count": product_count,
                    "brand_product_count": brand_count,
                    "brand_share": (
                        round(observed_share, 4) if observed_share is not None else None
                    ),
                    "stated_brand_share": mention.value,
                    "share_tolerance": tolerance,
                },
                "top_products": [
                    {
                        "product_name": _normalize_text(row.get("product_name")),
                        "brand": _normalize_text(row.get("brand")),
                    }
                    for row in rows[:8]
                ],
            }
        ],
        "component_entities": [
            _normalize_text(selector["value"]) for selector in selectors
        ],
        "aggregation_rule_id": "contextual_product_brand_share_v1",
        "cohort_basis": "top_seller_products",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "top-seller product rows matching descriptor values named in the "
            "claim; stated brand share is compared with the brand's share of "
            "that matched product set"
        ),
        "missing_components": [] if not reasons else ["brand_share"],
        "reasons": reasons,
    }


def _sale_pressure_bundle_concentration_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_supporting_bundle_count": 2,
        "minimum_sale_pressure_count": 5,
        "minimum_delta_pct_points": 5.0,
        "source_files": ["sale_pressure_pairs.csv", "sale_pressure_triples.csv"],
    }


def _looks_like_sale_pressure_bundle_concentration_summary(text: str) -> bool:
    lowered = text.casefold()
    return (
        ("sale-pressure" in lowered or "sale pressure" in lowered)
        and "concentration" in lowered
        and ("bundle" in lowered or "specific" in lowered)
    )


def _sale_pressure_concentrated_bundle_rows(
    frames: dict[str, pl.DataFrame],
    threshold_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in ("sale_pressure_pairs.csv", "sale_pressure_triples.csv"):
        df = frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        required = {
            "bundle_label",
            "count_sale_pressure",
            "pct_sale_pressure",
            "pct_not_observed_sale_pressure",
        }
        if df.is_empty() or not required <= set(columns):
            continue
        for row in df.to_dicts():
            count_sale_pressure = _int_or_none(row.get("count_sale_pressure")) or 0
            pct_sale_pressure = _percent_from_fraction(row.get("pct_sale_pressure"))
            pct_not_observed = _percent_from_fraction(
                row.get("pct_not_observed_sale_pressure")
            )
            if pct_sale_pressure is None or pct_not_observed is None:
                continue
            delta_pct_points = pct_sale_pressure - pct_not_observed
            if (
                count_sale_pressure < threshold_policy["minimum_sale_pressure_count"]
                or delta_pct_points < threshold_policy["minimum_delta_pct_points"]
            ):
                continue
            rows.append(
                {
                    "source_file": file_name,
                    "bundle_label": _normalize_text(row.get("bundle_label")),
                    "matched_row_keys": _candidate_row_keys(
                        {"row": row, "file": file_name, "kind": "bundle"}
                    ),
                    "computed_values": {
                        "count_sale_pressure": count_sale_pressure,
                        "sale_pressure_base": _int_or_none(
                            row.get("sale_pressure_base")
                        ),
                        "pct_sale_pressure": round(pct_sale_pressure, 4),
                        "pct_not_observed_sale_pressure": round(pct_not_observed, 4),
                        "delta_pct_points": round(delta_pct_points, 4),
                        "sale_pressure_brand_count": _int_or_none(
                            row.get("sale_pressure_brand_count")
                        ),
                    },
                }
            )

    rows.sort(
        key=lambda row: (
            row["computed_values"]["delta_pct_points"],
            row["computed_values"]["count_sale_pressure"],
            row["bundle_label"],
        ),
        reverse=True,
    )
    return rows


def _validate_sale_pressure_bundle_concentration_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_sale_pressure_bundle_concentration_summary(segment):
        return None

    threshold_policy = _sale_pressure_bundle_concentration_summary_threshold_policy()
    support_rows = _sale_pressure_concentrated_bundle_rows(frames, threshold_policy)
    if len(support_rows) >= threshold_policy["minimum_supporting_bundle_count"]:
        status = "pass"
        reasons: list[str] = []
    else:
        status = "fail"
        reasons = ["sale-pressure package has too few concentrated bundle rows"]

    return {
        "status": status,
        "row_support": support_rows[:6],
        "component_entities": _unique_texts(
            row["bundle_label"] for row in support_rows[:6]
        ),
        "aggregation_rule_id": "sale_pressure_bundle_concentration_summary_v1",
        "cohort_basis": "sale_pressure_vs_not_observed_sale_pressure",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "sale-pressure bundle rows with enough exposed products and a "
            "positive sale-pressure-over-not-observed delta"
        ),
        "missing_components": [] if status == "pass" else ["supporting_bundles"],
        "reasons": reasons,
    }


def _core_bundle_brand_promotion_summary_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_core_bundle_rows": 3,
        "minimum_top_seller_count": 4,
        "minimum_top_seller_brand_count": 3,
        "minimum_top_seller_share_pct": 10.0,
        "minimum_brand_diversity_share": 0.6,
        "maximum_sale_pressure_exposure_pct": 35.0,
        "minimum_sale_pressure_measured_rows": 3,
        "minimum_low_sale_pressure_share": 0.6,
        "source_files": [
            "top_seller_pairs.csv",
            "top_seller_triples.csv",
            "top_seller_products.csv",
            "product_filter_matrix.csv",
        ],
    }


def _looks_like_core_bundle_brand_promotion_summary(text: str) -> bool:
    lowered = text.casefold()
    return (
        "bundle" in lowered
        and ("brand concentration" in lowered or "brand limits" in lowered)
        and (
            "promotional pressure" in lowered
            or "promotion pressure" in lowered
            or "sale pressure" in lowered
        )
        and (
            "core" in lowered
            or "primary signal" in lowered
            or "organic strength" in lowered
        )
    )


def _core_bundle_brand_promotion_support_rows(
    frames: dict[str, pl.DataFrame],
    threshold_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_by_label: dict[str, dict[str, Any]] = {}
    for file_name in ("top_seller_pairs.csv", "top_seller_triples.csv"):
        df = frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get("bundle_label"))
            top_seller_count = _int_or_none(row.get("count_top_seller")) or 0
            top_seller_brand_count = (
                _int_or_none(row.get("top_seller_brand_count")) or 0
            )
            top_seller_share_pct = _percent_from_fraction(row.get("pct_top_seller"))
            if (
                not label
                or top_seller_share_pct is None
                or top_seller_count < threshold_policy["minimum_top_seller_count"]
                or top_seller_brand_count
                < threshold_policy["minimum_top_seller_brand_count"]
                or top_seller_share_pct
                < threshold_policy["minimum_top_seller_share_pct"]
            ):
                continue
            brand_diversity_share = (
                top_seller_brand_count / top_seller_count
                if top_seller_count > 0
                else 0.0
            )
            if (
                brand_diversity_share
                < threshold_policy["minimum_brand_diversity_share"]
            ):
                continue

            exposure_candidates = _sale_pressure_exposure_candidates_for_label(
                label=label,
                cohort="top_seller",
                frames=frames,
            )
            exposure = exposure_candidates[0] if exposure_candidates else None
            exposure_pct = (
                _float_or_none(exposure.get("pct_sale_pressure_exposed"))
                if exposure
                else None
            )
            low_sale_pressure = (
                exposure_pct is not None
                and exposure_pct
                <= threshold_policy["maximum_sale_pressure_exposure_pct"]
            )
            support_row = {
                "source_file": file_name,
                "matched_row_keys": {"bundle_label": label},
                "computed_values": {
                    "count_top_seller": top_seller_count,
                    "top_seller_brand_count": top_seller_brand_count,
                    "top_seller_share_pct": round(top_seller_share_pct, 4),
                    "brand_diversity_share": round(brand_diversity_share, 4),
                    "sale_pressure_product_count": (
                        _int_or_none(exposure.get("product_count"))
                        if exposure
                        else None
                    ),
                    "sale_pressure_count": (
                        _int_or_none(exposure.get("sale_pressure_count"))
                        if exposure
                        else None
                    ),
                    "pct_sale_pressure_exposed": (
                        round(exposure_pct, 4) if exposure_pct is not None else None
                    ),
                    "low_sale_pressure_exposure": low_sale_pressure,
                },
            }
            if exposure:
                support_row["sale_pressure_selectors"] = exposure.get("selectors", [])

            label_key = _bundle_label_key(label)
            current = rows_by_label.get(label_key)
            if current is None:
                rows_by_label[label_key] = support_row
                continue
            current_values = current["computed_values"]
            current_score = (
                _int_or_none(current_values.get("count_top_seller")) or 0,
                _int_or_none(current_values.get("top_seller_brand_count")) or 0,
            )
            candidate_score = (top_seller_count, top_seller_brand_count)
            if candidate_score > current_score:
                rows_by_label[label_key] = support_row

    support_rows = list(rows_by_label.values())
    support_rows.sort(
        key=lambda item: (
            _int_or_none(item["computed_values"].get("count_top_seller")) or 0,
            _int_or_none(item["computed_values"].get("top_seller_brand_count")) or 0,
            _float_or_none(item["computed_values"].get("top_seller_share_pct")) or 0.0,
        ),
        reverse=True,
    )
    return support_rows


def _validate_core_bundle_brand_promotion_summary_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_core_bundle_brand_promotion_summary(segment):
        return None

    threshold_policy = _core_bundle_brand_promotion_summary_threshold_policy()
    support_rows = _core_bundle_brand_promotion_support_rows(
        frames,
        threshold_policy,
    )
    measured_rows = [
        row
        for row in support_rows
        if row["computed_values"].get("pct_sale_pressure_exposed") is not None
    ]
    low_sale_pressure_rows = [
        row
        for row in measured_rows
        if row["computed_values"].get("low_sale_pressure_exposure") is True
    ]
    low_sale_pressure_share = (
        len(low_sale_pressure_rows) / len(measured_rows) if measured_rows else None
    )

    reasons: list[str] = []
    if len(support_rows) < threshold_policy["minimum_core_bundle_rows"]:
        reasons.append("not enough broad top-seller core bundle rows")
    if len(measured_rows) < threshold_policy["minimum_sale_pressure_measured_rows"]:
        reasons.append("not enough core bundle rows have sale-pressure exposure data")
    if (
        low_sale_pressure_share is None
        or low_sale_pressure_share < threshold_policy["minimum_low_sale_pressure_share"]
    ):
        reasons.append(
            "core bundle rows are not mostly below the sale-pressure exposure threshold"
        )

    return {
        "status": "pass" if not reasons else "fail",
        "row_support": support_rows[:8],
        "component_entities": [
            _normalize_text(row["matched_row_keys"].get("bundle_label"))
            for row in support_rows[:8]
        ],
        "aggregation_rule_id": "core_bundle_brand_promotion_resilience_v1",
        "cohort_basis": "top_seller_core_bundles_with_sale_pressure_overlay",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "core top-seller bundle rows must be broad across brands, and most "
            "measurable rows must have low sale-pressure exposure"
        ),
        "missing_components": [] if not reasons else ["core_bundle_resilience"],
        "reasons": reasons,
        "summary_metrics": {
            "core_bundle_row_count": len(support_rows),
            "sale_pressure_measured_row_count": len(measured_rows),
            "low_sale_pressure_row_count": len(low_sale_pressure_rows),
            "low_sale_pressure_share": (
                round(low_sale_pressure_share, 4)
                if low_sale_pressure_share is not None
                else None
            ),
        },
    }


def _looks_like_review_validation_claim(text: str) -> bool:
    lowered = text.casefold()
    if lowered.startswith("winning now:"):
        return False
    return any(
        marker in lowered
        for marker in (
            "review evidence confirms",
            "reviews heavily reinforce",
            "pdp and review data validate",
            "reviewers validate",
            "corroborated by pdp review data",
        )
    )


def _looks_like_review_friction_claim(text: str) -> bool:
    lowered = text.casefold()
    if _looks_like_review_validation_claim(text) and not any(
        marker in lowered
        for marker in (
            "friction points",
            "shade accuracy",
            "formula consistency",
            "removal difficulty",
            "heavier feel",
            "price point",
            "difficulty opening",
            "opening the seal",
        )
    ):
        return False
    return any(
        marker in lowered
        for marker in (
            "friction points",
            "operational limits",
            "shade accuracy",
            "formula consistency",
            "removal difficulty",
            "heavier feel",
            "price point",
            "difficulty opening",
            "opening the seal",
        )
    )


def _review_validation_frame_name(segment: str) -> str:
    lowered = segment.casefold()
    if any(
        marker in lowered
        for marker in (
            "winner",
            "winning",
            "top seller",
            "top-seller",
            "current",
        )
    ):
        return "top_seller_review_validation.csv"
    return "bundle_review_validation.csv"


def _review_candidate_rows(
    frames: dict[str, pl.DataFrame],
    *,
    file_name: str,
) -> list[dict[str, Any]]:
    df = frames[file_name]
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "bundle_label" not in columns:
        return []
    return [
        {
            "file": file_name,
            "row": row,
            "label": _normalize_text(row.get("bundle_label")),
        }
        for row in df.to_dicts()
        if _normalize_text(row.get("bundle_label"))
    ]


def _review_row_text(
    row: dict[str, Any],
    columns: tuple[str, ...],
) -> str:
    return _fold_text(
        " ".join(
            _normalize_text(row.get(column)) for column in columns if row.get(column)
        )
    )


def _review_row_match_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    return {
        "bundle_label": _normalize_text(row.get("bundle_label")),
        "product_name": _normalize_text(row.get("product_name")),
        "source_file": candidate["file"],
        "matched_row_keys": {
            "bundle_label": _normalize_text(row.get("bundle_label")),
            "product_name": _normalize_text(row.get("product_name")),
        },
        "review_count": _int_or_none(row.get("review_count")),
        "rating": _float_or_none(row.get("rating")),
        "positive_headline": _normalize_text(row.get("reviews_positive_headline")),
        "negative_headline": _normalize_text(row.get("reviews_negative_headline")),
    }


_REVIEW_VALIDATION_ANCHOR_STOPWORDS = _SUMMARY_TEXT_STOPWORDS | {
    "category",
    "claim",
    "claims",
    "clear",
    "confirms",
    "consumer",
    "corroborated",
    "data",
    "eating",
    "evidence",
    "establish",
    "establishes",
    "food",
    "heavily",
    "limit",
    "limits",
    "operational",
    "pdp",
    "preference",
    "product",
    "products",
    "proposition",
    "propositions",
    "reinforce",
    "reinforces",
    "review",
    "reviews",
    "signal",
    "signals",
    "soft",
    "smooth",
    "texture",
    "textures",
    "validate",
    "validates",
    "validation",
    "winner",
    "winners",
    "winning",
}


def _review_validation_anchor_tokens(segment: str) -> set[str]:
    topic_tokens = {
        token
        for keywords in (
            tuple(_REVIEW_VALIDATION_TOPIC_KEYWORDS.values())
            + tuple(_REVIEW_FRICTION_TOPIC_KEYWORDS.values())
        )
        for keyword in keywords
        for token in _token_list(keyword)
    }
    ignored_tokens = _REVIEW_VALIDATION_ANCHOR_STOPWORDS | topic_tokens
    return {
        token
        for token in _canonical_tokens(segment, ignored_tokens=ignored_tokens)
        if len(token) >= 4
    }


def _review_row_anchor_tokens(row: dict[str, Any]) -> set[str]:
    anchor_columns = (
        "bundle_label",
        "product_name",
        "food texture",
        "food_texture",
        "packaging type",
        "packaging_type",
        "resolved_form",
        "resolved_finish",
        "resolved_coverage",
    )
    return _canonical_tokens(
        " ".join(_normalize_text(row.get(column)) for column in anchor_columns)
    )


def _review_validation_requested_topics(
    segment: str,
) -> dict[str, tuple[str, ...]]:
    lowered = _fold_text(segment)
    topic_triggers = {
        "texture": ("texture", "textures", "smooth", "velvety", "creamy", "pate"),
        "comfort": ("comfort", "comfortable", "soft", "hydrat", "moistur"),
        "glide": ("glide", "glides", "gliding", "easy application"),
        "coverage": ("coverage", "cover", "pigment", "pigmented", "color payoff"),
    }
    requested = {
        topic: _REVIEW_VALIDATION_TOPIC_KEYWORDS[topic]
        for topic, triggers in topic_triggers.items()
        if any(trigger in lowered for trigger in triggers)
    }
    return requested or dict(_REVIEW_VALIDATION_TOPIC_KEYWORDS)


def _review_topic_match_rows(
    frames: dict[str, pl.DataFrame],
    *,
    file_name: str,
    topic_keywords: dict[str, tuple[str, ...]],
    columns: tuple[str, ...],
    anchor_tokens: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    matches: dict[str, list[dict[str, Any]]] = {topic: [] for topic in topic_keywords}
    for candidate in _review_candidate_rows(frames, file_name=file_name):
        if anchor_tokens and not (
            anchor_tokens & _review_row_anchor_tokens(candidate["row"])
        ):
            continue
        blob = _review_row_text(candidate["row"], columns)
        if not blob:
            continue
        for topic, keywords in topic_keywords.items():
            if any(keyword in blob for keyword in keywords):
                matches[topic].append(_review_row_match_evidence(candidate))
    return matches


def _review_validation_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_positive_match_count": 2,
        "requires_negative_limit_signal": True,
    }


def _review_friction_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_topic_match_count": 1,
    }


def _validate_review_validation_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_review_validation_claim(segment):
        return None

    file_name = _review_validation_frame_name(segment)
    threshold_policy = _review_validation_threshold_policy()
    requested_positive_topics = _review_validation_requested_topics(segment)
    anchor_tokens = _review_validation_anchor_tokens(segment)
    positive_support = _review_topic_match_rows(
        frames,
        file_name=file_name,
        topic_keywords=requested_positive_topics,
        columns=_REVIEW_POSITIVE_TEXT_COLUMNS,
        anchor_tokens=anchor_tokens,
    )
    negative_support = _review_topic_match_rows(
        frames,
        file_name=file_name,
        topic_keywords=_REVIEW_FRICTION_TOPIC_KEYWORDS,
        columns=_REVIEW_NEGATIVE_TEXT_COLUMNS,
        anchor_tokens=anchor_tokens,
    )

    positive_match_count = sum(len(rows) for rows in positive_support.values())
    negative_match_count = sum(len(rows) for rows in negative_support.values())
    reasons: list[str] = []
    if positive_match_count < threshold_policy["minimum_positive_match_count"]:
        reasons.append("review validation lacks enough positive corroboration rows")
    lowered = segment.casefold()
    if (
        threshold_policy["requires_negative_limit_signal"]
        and "operational limits" in lowered
        and negative_match_count == 0
    ):
        reasons.append("review validation lacks negative operational-limit support")

    status = "pass" if not reasons else "fail"
    component_entities = _unique_texts(
        [row["bundle_label"] for rows in positive_support.values() for row in rows]
    )[:50]
    cohort_basis = (
        "top_seller_review_rows"
        if file_name == "top_seller_review_validation.csv"
        else "bundle_review_rows"
    )
    return {
        "status": status,
        "attribute_support": [],
        "row_support": [
            {
                "source_file": file_name,
                "positive_support": {
                    topic: rows[:20] for topic, rows in positive_support.items()
                },
                "negative_support": {
                    topic: rows[:20] for topic, rows in negative_support.items()
                },
                "positive_match_count": positive_match_count,
                "negative_match_count": negative_match_count,
                "anchor_tokens": sorted(anchor_tokens),
            }
        ],
        "component_entities": component_entities,
        "aggregation_rule_id": "review_validation_summary_v1",
        "cohort_basis": cohort_basis,
        "threshold_policy": threshold_policy,
        "ranking_basis": "positive review corroboration rows plus negative limit rows",
        "reasons": reasons,
    }


def _validate_review_friction_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_review_friction_claim(segment):
        return None

    lowered = segment.casefold()
    requested_topics: dict[str, tuple[str, ...]] = {}
    if "shade accuracy" in lowered:
        requested_topics["shade_accuracy"] = _REVIEW_FRICTION_TOPIC_KEYWORDS[
            "shade_accuracy"
        ]
    if "formula consistency" in lowered:
        requested_topics["formula_consistency"] = _REVIEW_FRICTION_TOPIC_KEYWORDS[
            "formula_consistency"
        ]
    if "removal difficulty" in lowered:
        requested_topics["removal_difficulty"] = _REVIEW_FRICTION_TOPIC_KEYWORDS[
            "removal_difficulty"
        ]
    if "heavier feel" in lowered:
        requested_topics["heavier_feel"] = _REVIEW_FRICTION_TOPIC_KEYWORDS[
            "heavier_feel"
        ]
    if "price point" in lowered:
        requested_topics["price_point"] = _REVIEW_FRICTION_TOPIC_KEYWORDS["price_point"]
    if "difficulty opening" in lowered or "opening the seal" in lowered:
        requested_topics["packaging_opening"] = _REVIEW_FRICTION_TOPIC_KEYWORDS[
            "packaging_opening"
        ]
    if not requested_topics and "operational limits" in lowered:
        requested_topics = {
            key: _REVIEW_FRICTION_TOPIC_KEYWORDS[key]
            for key in ("shade_accuracy", "formula_consistency")
        }

    threshold_policy = _review_friction_threshold_policy()
    negative_support = _review_topic_match_rows(
        frames,
        file_name="top_seller_review_validation.csv",
        topic_keywords=requested_topics,
        columns=_REVIEW_NEGATIVE_TEXT_COLUMNS,
    )
    reasons: list[str] = []
    for topic, rows in negative_support.items():
        if len(rows) < threshold_policy["minimum_topic_match_count"]:
            reasons.append(f"review friction lacks support for topic: {topic}")

    status = "pass" if not reasons else "fail"
    component_entities = _unique_texts(
        [row["bundle_label"] for rows in negative_support.values() for row in rows]
    )
    return {
        "status": status,
        "attribute_support": [],
        "row_support": [
            {
                "source_file": "top_seller_review_validation.csv",
                "negative_support": negative_support,
            }
        ],
        "component_entities": component_entities,
        "aggregation_rule_id": "review_friction_topics_v1",
        "cohort_basis": "top_seller_review_rows",
        "threshold_policy": threshold_policy,
        "ranking_basis": "negative review topic rows",
        "reasons": reasons,
    }


_SALE_PRESSURE_RE = re.compile(
    r"\b(?:sale[-\s]?pressure|sell[-\s]?pressure|promo(?:tional)?\s+assist|sale\s+exposed|sale\s+assisted)\b",
    re.IGNORECASE,
)
_SALE_PRESSURE_LOW_EXPOSURE_MAX_PCT = 20.0
_SALE_PRESSURE_LOW_EXPOSURE_RE = re.compile(
    r"\b(?:largely|mostly|remain(?:s)?|remained|stays?|stay)\s+"
    r"(?:unexposed|clean)\b"
    r"|\b(?:mostly|largely)\s+clean\s+of\b"
    r"|\b(?:zero|no)\s+sale[-\s]?pressure\s+exposure\b",
    re.IGNORECASE,
)
_SALE_PRESSURE_HIGHER_EXPOSURE_COMPARISON_RE = re.compile(
    r"\b(?:higher|greater|stronger|more)\s+"
    r"(?:(?:promo(?:tion(?:al)?)?|sale[-\s]?pressure)\s+)?exposure\b"
    r".*\bthan\b",
    re.IGNORECASE,
)
_SALE_PRESSURE_COMPARISON_MIN_DELTA_PCT = 5.0
_SALE_PRESSURE_EXPOSED_COUNT_RE = re.compile(
    r"\b(?P<count>\d+)\s+of\s+(?P<base>\d+)\s+"
    r"(?:items?|products?|skus?)\s+(?:are\s+)?"
    r"(?:sale[-\s]?pressure\s+)?exposed\b",
    re.IGNORECASE,
)
_SALE_PRESSURE_ZERO_EXPOSURE_RE = re.compile(
    r"\b(?:zero|no)\s+sale[-\s]?pressure\s+exposure\b",
    re.IGNORECASE,
)
_SALE_PRESSURE_ABSENCE_RE = re.compile(
    r"\b(?:no|neither)\b.*\bevidence\b.*\bdriven\b" r"|\bnot\s+driven\b",
    re.IGNORECASE,
)


def _looks_like_sale_pressure_claim(text: str) -> bool:
    lowered = text.casefold()
    if not _contains_numeric_evidence(text):
        return bool(
            (
                _SALE_PRESSURE_RE.search(text)
                and _SALE_PRESSURE_LOW_EXPOSURE_RE.search(text)
            )
            or (
                _SALE_PRESSURE_RE.search(text)
                and _SALE_PRESSURE_ABSENCE_RE.search(text)
            )
            or _SALE_PRESSURE_HIGHER_EXPOSURE_COMPARISON_RE.search(text)
        )
    return bool(
        _SALE_PRESSURE_RE.search(text)
        or "mostly clean" in lowered
        or "highly assisted" in lowered
        or "promo assist" in lowered
    )


def _sale_pressure_qualitative_threshold_policy() -> dict[str, Any]:
    return {
        "low_exposure_max_pct": _SALE_PRESSURE_LOW_EXPOSURE_MAX_PCT,
        "comparison_min_delta_pct": _SALE_PRESSURE_COMPARISON_MIN_DELTA_PCT,
        "qualitative_low_exposure_phrases": [
            "largely unexposed",
            "mostly unexposed",
            "mostly clean",
            "clean of sale pressure",
        ],
    }


def _sale_pressure_exposure_percent_mentions(segment: str) -> list[_PercentMention]:
    mentions: list[_PercentMention] = []
    for match in _BUNDLE_PERCENT_RE.finditer(segment):
        before = segment[max(0, match.start() - 45) : match.start()]
        after = segment[match.end() : min(len(segment), match.end() + 35)]
        local_context = f"{before} {after}".casefold()
        if not re.search(r"\b(?:exposed|exposure)\b", local_context):
            continue
        raw_value = match.group(1)
        mentions.append(
            _PercentMention(
                value=float(raw_value),
                tolerance=_percent_tolerance(raw_value),
                role=_percent_role(segment, match.span()),
                span=match.span(),
            )
        )
    return mentions


def _sale_pressure_exposure_count_pairs(segment: str) -> list[dict[str, int]]:
    return [
        {"count": int(match.group("count")), "base": int(match.group("base"))}
        for match in _SALE_PRESSURE_EXPOSED_COUNT_RE.finditer(segment)
        if int(match.group("base")) > 0
    ]


def _sale_pressure_exposure_observations(segment: str) -> dict[str, Any]:
    percent_mentions = _sale_pressure_exposure_percent_mentions(segment)
    count_pairs = _sale_pressure_exposure_count_pairs(segment)
    zero_exposure = bool(_SALE_PRESSURE_ZERO_EXPOSURE_RE.search(segment))
    low_exposure = bool(_SALE_PRESSURE_LOW_EXPOSURE_RE.search(segment))
    derived_mentions = [
        _PercentMention(
            value=100.0 * pair["count"] / pair["base"],
            tolerance=_PERCENT_TOLERANCE,
            role=None,
        )
        for pair in count_pairs
    ]
    return {
        "percent_mentions": [*percent_mentions, *derived_mentions],
        "count_pairs": count_pairs,
        "zero_exposure": zero_exposure,
        "observed_values": {
            **_extract_numeric_claim_evidence(segment),
            "sale_pressure_exposure_percents": [
                mention.value for mention in [*percent_mentions, *derived_mentions]
            ],
            "sale_pressure_exposure_count_pairs": count_pairs,
            "zero_sale_pressure_exposure": zero_exposure,
            "qualitative_low_sale_pressure_exposure": low_exposure,
        },
        "low_exposure": low_exposure,
    }


def _sale_pressure_label_is_explicit(segment: str, label: str) -> bool:
    lowered_segment = _normalize_text(segment).casefold()
    lowered_label = _normalize_text(label).casefold()
    if lowered_label and lowered_label in lowered_segment:
        return True
    parts = _bundle_parts_in_order(label)
    if len(parts) < 2:
        return False
    return all(
        bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(part.casefold())}(?![a-z0-9])",
                lowered_segment,
            )
        )
        for part in parts
    )


def _sale_pressure_explicit_bundle_labels_from_text(segment: str) -> list[str]:
    normalized = _normalize_text(segment)
    if ":" not in normalized:
        return []
    candidate = _normalize_text(normalized.split(":", 1)[0])
    candidate = re.sub(r"^\d+\s+", "", candidate).strip()
    if "+" not in candidate or len(candidate.split()) > 12:
        return []
    return [candidate]


def _bundle_key_parts(row: dict[str, Any]) -> list[tuple[str, str]]:
    bundle_key = _normalize_text(row.get("bundle_key"))
    if not bundle_key:
        return []
    parts: list[tuple[str, str]] = []
    for raw_part in bundle_key.split("+"):
        part = _normalize_text(raw_part)
        if "=" not in part:
            return []
        attribute_name, attribute_value = part.split("=", 1)
        attribute_name = _normalize_text(attribute_name)
        attribute_value = _normalize_text(attribute_value)
        if not attribute_name or not attribute_value:
            return []
        parts.append((attribute_name, attribute_value))
    return parts


def _infer_bundle_parts_from_product_frame(
    label: str,
    df: pl.DataFrame,
) -> list[tuple[str, str]]:
    parts = _bundle_parts_in_order(label)
    if len(parts) < 2 or df.is_empty():
        return []
    columns, _schema = get_schema_and_column_names(df)
    inferred_parts: list[tuple[str, str]] = []
    for part in parts:
        matching_columns: list[str] = []
        for column in columns:
            try:
                values = df.get_column(column).drop_nulls().unique().to_list()
            except (AttributeError, TypeError, ValueError):
                continue
            if any(_product_cell_matches_bundle_value(value, part) for value in values):
                matching_columns.append(column)
        if not matching_columns:
            return []
        matching_columns.sort(
            key=lambda column: (
                column.endswith("_mapped"),
                "_" in column,
                len(column),
            )
        )
        inferred_parts.append((matching_columns[0], part))
    return inferred_parts


def _product_cell_matches_bundle_value(value: Any, expected: str) -> bool:
    actual = _normalize_text(value)
    if not actual:
        return False
    expected_key = _canonical_text(expected)
    if not expected_key:
        return False
    if _canonical_text(actual) == expected_key:
        return True
    return any(
        _canonical_text(part) == expected_key
        for part in re.split(r"\s*(?:\||;|,)\s*", actual)
        if _normalize_text(part)
    )


def _product_row_matches_bundle_parts(
    row: dict[str, Any],
    column_lookup: dict[str, str],
    bundle_parts: list[tuple[str, str]],
) -> bool:
    for attribute_name, attribute_value in bundle_parts:
        column_name = column_lookup.get(_canonical_text(attribute_name))
        if column_name is None:
            return False
        if not _product_cell_matches_bundle_value(
            row.get(column_name), attribute_value
        ):
            return False
    return True


def _sale_pressure_status_is_exposed(value: Any) -> bool:
    return _canonical_text(value) == "salepressure"


def _sale_pressure_selector_quality(selector: dict[str, Any]) -> float:
    column_key = _canonical_text(selector.get("column"))
    score = 10.0 - min(len(column_key), 40) / 100.0
    if selector.get("selector_kind") == "boolean_indicator":
        score -= 0.5
    if column_key.endswith("mapped"):
        score -= 0.25
    return score


def _selector_from_bundle_part(
    attribute_name: str,
    attribute_value: str,
    column_lookup: dict[str, str],
) -> dict[str, Any] | None:
    column_name = column_lookup.get(_canonical_text(attribute_name))
    if column_name is None:
        return None
    return {
        "column": column_name,
        "value": attribute_value,
        "display_value": attribute_value,
        "selector_kind": "value_match",
    }


def _sale_pressure_selector_mask(
    product_df: pl.DataFrame,
    selector: dict[str, Any],
) -> pl.Series:
    column_name = _normalize_text(selector.get("column"))
    series = product_df.get_column(column_name)
    if series.dtype == pl.Boolean:
        return series.fill_null(False)
    expected = _normalize_text(selector.get("value"))
    return series.map_elements(
        lambda value: _product_cell_matches_bundle_value(value, expected),
        return_dtype=pl.Boolean,
    )


def _sale_pressure_exposure_candidates_for_label(
    *,
    label: str,
    cohort: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    product_sources: list[tuple[str, pl.DataFrame, str | None, str | None]] = []
    if cohort == "recent":
        product_sources.append(
            (
                "recent_products.csv",
                frames.get("recent_products.csv", pl.DataFrame()),
                None,
                None,
            )
        )
        product_sources.append(
            (
                "product_filter_matrix.csv",
                frames.get("product_filter_matrix.csv", pl.DataFrame()),
                "listing_status",
                "recent",
            )
        )
    elif cohort == "top_seller":
        product_sources.append(
            (
                "top_seller_products.csv",
                frames.get("top_seller_products.csv", pl.DataFrame()),
                None,
                None,
            )
        )
        product_sources.append(
            (
                "product_filter_matrix.csv",
                frames.get("product_filter_matrix.csv", pl.DataFrame()),
                "top_seller_status",
                "top_seller",
            )
        )
    else:
        product_sources.append(
            (
                "product_filter_matrix.csv",
                frames.get("product_filter_matrix.csv", pl.DataFrame()),
                None,
                None,
            )
        )

    seen: set[tuple[str, tuple[tuple[str, str], ...], str]] = set()
    for product_source_file, product_df, status_column, status_value in product_sources:
        columns, _schema = get_schema_and_column_names(product_df)
        if product_df.is_empty() or "sale_pressure_status" not in columns:
            continue
        if status_column is not None:
            if status_column not in columns:
                continue
            cohort_mask = (
                product_df.get_column(status_column).cast(pl.String) == status_value
            )
        else:
            cohort_mask = pl.Series([True] * get_row_count(product_df))

        column_lookup = {_canonical_text(column): column for column in columns}
        selector_groups: list[tuple[str, tuple[dict[str, Any], ...]]] = []
        for candidate in _bundle_candidates(label, frames):
            selectors: list[dict[str, Any]] = []
            for attribute_name, attribute_value in _bundle_key_parts(candidate["row"]):
                selector = _selector_from_bundle_part(
                    attribute_name,
                    attribute_value,
                    column_lookup,
                )
                if selector is None:
                    selectors = []
                    break
                selectors.append(selector)
            if selectors:
                selector_groups.append((candidate["file"], tuple(selectors)))

        if not selector_groups and "+" in label:
            inferred_selectors = [
                {
                    "column": column_name,
                    "value": attribute_value,
                    "display_value": attribute_value,
                    "selector_kind": "value_match",
                }
                for column_name, attribute_value in _infer_bundle_parts_from_product_frame(
                    label,
                    product_df,
                )
            ]
            if inferred_selectors:
                selector_groups.append(
                    ("inferred_product_columns", tuple(inferred_selectors))
                )

        if not selector_groups and "+" not in label:
            selector_groups.extend(
                ("inferred_product_columns", (selector,))
                for selector in _computed_bundle_selector_candidates(label, product_df)
            )

        for source_file, selectors in selector_groups:
            selector_key = tuple(
                (
                    _normalize_text(selector.get("column")),
                    _normalize_text(selector.get("display_value")),
                )
                for selector in selectors
            )
            dedupe_key = (product_source_file, selector_key, cohort)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            mask = pl.Series([True] * get_row_count(product_df))
            for selector in selectors:
                mask = mask & _sale_pressure_selector_mask(product_df, selector)
            final_mask = mask & cohort_mask
            product_count = int(final_mask.sum())
            if product_count <= 0:
                continue
            sale_pressure_count = int(
                product_df.filter(final_mask)
                .get_column("sale_pressure_status")
                .map_elements(
                    _sale_pressure_status_is_exposed,
                    return_dtype=pl.Boolean,
                )
                .sum()
            )
            pct_exposed = 100.0 * sale_pressure_count / product_count
            evaluations.append(
                {
                    "label": label,
                    "cohort": cohort,
                    "source_file": product_source_file,
                    "selector_source_file": source_file,
                    "selectors": [
                        {
                            "column": _normalize_text(selector.get("column")),
                            "value": _normalize_text(selector.get("display_value")),
                            "selector_kind": _normalize_text(
                                selector.get("selector_kind")
                            ),
                        }
                        for selector in selectors
                    ],
                    "product_count": product_count,
                    "sale_pressure_count": sale_pressure_count,
                    "pct_sale_pressure_exposed": pct_exposed,
                    "selector_quality": sum(
                        _sale_pressure_selector_quality(selector)
                        for selector in selectors
                    ),
                }
            )

    evaluations.sort(
        key=lambda item: (
            item["selector_quality"],
            item["product_count"],
            item["selector_source_file"] != "inferred_product_columns",
        ),
        reverse=True,
    )
    return evaluations


def _sale_pressure_comparison_label_specs(
    segment: str,
    bundle_records: list[_BundleLabelRecord],
) -> tuple[dict[str, str], dict[str, str]] | None:
    match = re.search(r"\bthan\b", segment, flags=re.IGNORECASE)
    if match is None:
        return None
    left_text = segment[: match.start()]
    right_text = segment[match.end() :]

    left_label = ""
    if re.search(r"\bmesh\b", left_text, flags=re.IGNORECASE):
        left_label = "mesh"
    if not left_label:
        return None

    right_labels = _matched_bundle_labels(right_text, bundle_records)
    if not right_labels:
        return None

    left_cohort = "recent" if re.search(r"\brecent\b", left_text, re.I) else "all"
    right_cohort = (
        "top_seller"
        if re.search(r"\b(?:core|winning|winners?|baseline)\b", right_text, re.I)
        else "all"
    )
    return (
        {"label": left_label, "cohort": left_cohort},
        {"label": right_labels[0], "cohort": right_cohort},
    )


def _validate_sale_pressure_comparison_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
    bundle_records: list[_BundleLabelRecord],
) -> dict[str, Any] | None:
    if _SALE_PRESSURE_HIGHER_EXPOSURE_COMPARISON_RE.search(segment) is None:
        return None
    specs = _sale_pressure_comparison_label_specs(segment, bundle_records)
    if specs is None:
        return {
            "status": "warning",
            "label": "sale_pressure_exposure_comparison",
            "source_file": "product_filter_matrix.csv",
            "message": "sale-pressure comparison did not resolve both compared labels",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    left_spec, right_spec = specs
    left_candidates = _sale_pressure_exposure_candidates_for_label(
        label=left_spec["label"],
        cohort=left_spec["cohort"],
        frames=frames,
    )
    right_candidates = _sale_pressure_exposure_candidates_for_label(
        label=right_spec["label"],
        cohort=right_spec["cohort"],
        frames=frames,
    )
    if not left_candidates or not right_candidates:
        return {
            "status": "warning",
            "label": "sale_pressure_exposure_comparison",
            "source_file": "product_filter_matrix.csv",
            "message": "sale-pressure comparison could not compute both exposure rates",
            "observed_values": _extract_numeric_claim_evidence(segment),
            "matched_row_keys": {"left": left_spec, "right": right_spec},
        }

    left = left_candidates[0]
    right = right_candidates[0]
    delta = left["pct_sale_pressure_exposed"] - right["pct_sale_pressure_exposed"]
    threshold = _SALE_PRESSURE_COMPARISON_MIN_DELTA_PCT
    reasons = []
    if delta < threshold:
        reasons.append(
            "sale-pressure exposure comparison delta below threshold: "
            f"expected at least {threshold:.1f} pp, observed {delta:.1f} pp"
        )
    return {
        "status": "pass" if not reasons else "fail",
        "label": "sale_pressure_exposure_comparison",
        "source_file": "product_filter_matrix.csv",
        "observed_values": _extract_numeric_claim_evidence(segment),
        "package_values": {
            "left": left,
            "right": right,
            "delta_pct_points": delta,
        },
        "matched_row_keys": {"left": left_spec, "right": right_spec},
        "tolerance_policy": _numeric_tolerance_policy(),
        "comparison_policy": (
            "higher exposure requires left sale-pressure exposure to exceed "
            f"right exposure by at least {threshold:.1f} percentage points"
        ),
        "candidate_evaluations": {
            "left": left_candidates[:3],
            "right": right_candidates[:3],
        },
        "reasons": reasons,
    }


def _sale_pressure_product_source_files(segment: str) -> list[tuple[str, str]]:
    lowered = segment.casefold()
    mentions_recent = bool(re.search(r"\brecent\b", lowered))
    mentions_top_seller = bool(
        re.search(r"\b(?:top[-\s]?sellers?|winners?|winning)\b", lowered)
    )
    if mentions_recent and not mentions_top_seller:
        return [("recent_products.csv", "recent")]
    if mentions_top_seller and not mentions_recent:
        return [("top_seller_products.csv", "top_seller")]
    if mentions_recent and mentions_top_seller:
        return [
            ("recent_products.csv", "recent"),
            ("top_seller_products.csv", "top_seller"),
        ]
    return [
        ("product_filter_matrix.csv", "all_products"),
        ("recent_products.csv", "recent"),
        ("top_seller_products.csv", "top_seller"),
    ]


def _sale_pressure_overlap_comparisons(segment: str) -> list[tuple[str, str]]:
    lowered = segment.casefold()
    if "overlap" not in lowered:
        return []
    mentions_recent = bool(re.search(r"\brecent\b", lowered))
    mentions_top_seller = bool(re.search(r"\btop[-\s]?sellers?\b", lowered))
    if mentions_recent and mentions_top_seller:
        return [
            ("sale_pressure_vs_recent", "recent"),
            ("sale_pressure_vs_top_seller", "top_seller"),
            ("sale_pressure_vs_recent_top_seller", "recent_and_top_seller"),
        ]
    if mentions_recent:
        return [("sale_pressure_vs_recent", "recent")]
    if mentions_top_seller:
        return [("sale_pressure_vs_top_seller", "top_seller")]
    return []


def _sale_pressure_overlap_package_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "comparison": _normalize_text(row.get("comparison")),
        "left_cohort": _normalize_text(row.get("left_cohort")),
        "right_cohort": _normalize_text(row.get("right_cohort")),
        "left_count": _int_or_none(row.get("left_count")),
        "right_count": _int_or_none(row.get("right_count")),
        "overlap_count": _int_or_none(row.get("overlap_count")),
        "pct_left": _percent_from_fraction(row.get("pct_left")),
        "pct_right": _percent_from_fraction(row.get("pct_right")),
    }


def _sale_pressure_overlap_percent_matches(
    mention: _PercentMention,
    expected: float | None,
) -> bool:
    if expected is None:
        return False
    if _percent_matches(mention, expected):
        return True
    return _approx_equal(mention.value, expected, max(mention.tolerance, 0.75))


def _validate_sale_pressure_overlap_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    comparisons = _sale_pressure_overlap_comparisons(segment)
    allow_any_overlap_comparison = False
    if not comparisons and "overlap" in segment.casefold():
        comparisons = [
            ("sale_pressure_vs_recent", "recent"),
            ("sale_pressure_vs_top_seller", "top_seller"),
            ("sale_pressure_vs_recent_top_seller", "recent_and_top_seller"),
        ]
        allow_any_overlap_comparison = True
    if not comparisons:
        return None
    percent_mentions = _percent_mentions(segment)
    if not percent_mentions:
        return {
            "status": "warning",
            "label": "sale_pressure_overlap",
            "source_file": "sale_pressure_overlap.csv",
            "message": "sale-pressure overlap claim has no parsed percentage",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }
    df = frames.get("sale_pressure_overlap.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "comparison" not in columns:
        return {
            "status": "warning",
            "label": "sale_pressure_overlap",
            "source_file": "sale_pressure_overlap.csv",
            "message": "sale-pressure overlap source table is not available",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    rows_by_comparison = {
        _normalize_text(row.get("comparison")): row for row in df.to_dicts()
    }
    evaluations: list[dict[str, Any]] = []
    reasons: list[str] = []
    for comparison, cohort_label in comparisons:
        row = rows_by_comparison.get(comparison)
        if row is None:
            reasons.append(f"sale-pressure overlap row missing for {cohort_label}")
            continue
        package_values = _sale_pressure_overlap_package_values(row)
        expected_pct = _float_or_none(package_values.get("pct_right"))
        row_reasons: list[str] = []
        if not any(
            _sale_pressure_overlap_percent_matches(mention, expected_pct)
            for mention in percent_mentions
        ):
            row_reasons.append(
                f"{cohort_label} overlap percent mismatch: expected "
                f"{_format_optional_percent(expected_pct)}"
            )
        evaluations.append(
            {
                "file": "sale_pressure_overlap.csv",
                "matched_row_keys": {"comparison": comparison},
                "package_values": package_values,
                "reasons": row_reasons,
            }
        )
        reasons.extend(row_reasons)

    if allow_any_overlap_comparison:
        matched_evaluations = [
            evaluation for evaluation in evaluations if not evaluation["reasons"]
        ]
        if matched_evaluations:
            return {
                "status": "pass",
                "label": "sale_pressure_overlap",
                "source_file": "sale_pressure_overlap.csv",
                "observed_values": _extract_numeric_claim_evidence(segment),
                "package_values": {
                    "comparisons": [
                        evaluation["package_values"]
                        for evaluation in matched_evaluations
                    ]
                },
                "matched_row_keys": {
                    "comparisons": [
                        evaluation["matched_row_keys"]["comparison"]
                        for evaluation in matched_evaluations
                    ]
                },
                "candidate_evaluations": evaluations,
                "tolerance_policy": _numeric_tolerance_policy(),
                "comparison_policy": (
                    "cohort-unspecified sale-pressure overlap claims must match "
                    "at least one overlap comparison row"
                ),
                "reasons": [],
            }
        if evaluations:
            return {
                "status": "fail",
                "label": "sale_pressure_overlap",
                "source_file": "sale_pressure_overlap.csv",
                "observed_values": _extract_numeric_claim_evidence(segment),
                "package_values": {
                    "comparisons": [
                        evaluation["package_values"] for evaluation in evaluations
                    ]
                },
                "matched_row_keys": {
                    "comparisons": [
                        evaluation["matched_row_keys"]["comparison"]
                        for evaluation in evaluations
                    ]
                },
                "candidate_evaluations": evaluations,
                "tolerance_policy": _numeric_tolerance_policy(),
                "comparison_policy": (
                    "cohort-unspecified sale-pressure overlap claims must match "
                    "at least one overlap comparison row"
                ),
                "reasons": reasons,
            }

    if evaluations and not reasons:
        return {
            "status": "pass",
            "label": "sale_pressure_overlap",
            "source_file": "sale_pressure_overlap.csv",
            "observed_values": _extract_numeric_claim_evidence(segment),
            "package_values": {
                "comparisons": [
                    evaluation["package_values"] for evaluation in evaluations
                ]
            },
            "matched_row_keys": {
                "comparisons": [
                    evaluation["matched_row_keys"]["comparison"]
                    for evaluation in evaluations
                ]
            },
            "candidate_evaluations": evaluations,
            "tolerance_policy": _numeric_tolerance_policy(),
            "reasons": [],
        }
    if evaluations:
        return {
            "status": "fail",
            "label": "sale_pressure_overlap",
            "source_file": "sale_pressure_overlap.csv",
            "observed_values": _extract_numeric_claim_evidence(segment),
            "package_values": {
                "comparisons": [
                    evaluation["package_values"] for evaluation in evaluations
                ]
            },
            "matched_row_keys": {
                "comparisons": [
                    evaluation["matched_row_keys"]["comparison"]
                    for evaluation in evaluations
                ]
            },
            "candidate_evaluations": evaluations,
            "tolerance_policy": _numeric_tolerance_policy(),
            "reasons": reasons,
        }
    return {
        "status": "warning",
        "label": "sale_pressure_overlap",
        "source_file": "sale_pressure_overlap.csv",
        "message": "sale-pressure overlap claim did not match source comparison rows",
        "observed_values": _extract_numeric_claim_evidence(segment),
    }


def _validate_sale_pressure_absence_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if _SALE_PRESSURE_ABSENCE_RE.search(segment) is None:
        return None
    df = frames.get("sale_pressure_overlap.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "comparison" not in columns:
        return {
            "status": "warning",
            "label": "sale_pressure_absence",
            "source_file": "sale_pressure_overlap.csv",
            "message": "sale-pressure overlap source table is not available",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    relevant_rows = [
        row
        for row in df.to_dicts()
        if _normalize_text(row.get("comparison"))
        in {
            "sale_pressure_vs_recent",
            "sale_pressure_vs_top_seller",
            "sale_pressure_vs_recent_top_seller",
        }
    ]
    if not relevant_rows:
        return {
            "status": "warning",
            "label": "sale_pressure_absence",
            "source_file": "sale_pressure_overlap.csv",
            "message": "sale-pressure absence claim did not match source comparison rows",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    package_values = [
        _sale_pressure_overlap_package_values(row) for row in relevant_rows
    ]
    nonzero_rows = [
        value
        for value in package_values
        if (_float_or_none(value.get("pct_right")) or 0.0) > 0.0
        or (_int_or_none(value.get("overlap_count")) or 0) > 0
    ]
    return {
        "status": "pass" if not nonzero_rows else "fail",
        "label": "sale_pressure_absence",
        "source_file": "sale_pressure_overlap.csv",
        "observed_values": _extract_numeric_claim_evidence(segment),
        "package_values": {"comparisons": package_values},
        "matched_row_keys": {
            "comparisons": [
                _normalize_text(value.get("comparison")) for value in package_values
            ]
        },
        "tolerance_policy": _numeric_tolerance_policy(),
        "comparison_policy": (
            "sale-pressure absence requires zero overlap in recent, top-seller, "
            "and recent-top-seller sale-pressure comparison rows"
        ),
        "reasons": (
            []
            if not nonzero_rows
            else [
                "sale-pressure overlap is nonzero for: "
                + ", ".join(
                    _normalize_text(row.get("comparison")) for row in nonzero_rows
                )
            ]
        ),
    }


def _sale_pressure_product_exposure_package_values(
    *,
    label: str,
    bundle_candidate: dict[str, Any],
    product_source_file: str,
    product_cohort: str,
    product_count: int,
    sale_pressure_count: int,
) -> dict[str, Any]:
    row = bundle_candidate["row"]
    pct_exposed = (
        100.0 * sale_pressure_count / product_count if product_count > 0 else None
    )
    return {
        "bundle_label": label,
        "bundle_key": _normalize_text(row.get("bundle_key")),
        "bundle_source_file": bundle_candidate.get("file"),
        "product_source_file": product_source_file,
        "product_cohort": product_cohort,
        "sale_pressure_count": sale_pressure_count,
        "product_count": product_count,
        "pct_sale_pressure_exposed": pct_exposed,
    }


def _score_sale_pressure_product_exposure(
    observations: dict[str, Any],
    package_values: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    expected_pct = _float_or_none(package_values.get("pct_sale_pressure_exposed"))
    percent_mentions = observations["percent_mentions"]
    if percent_mentions and not any(
        _percent_matches(mention, expected_pct) for mention in percent_mentions
    ):
        reasons.append(
            "sale-pressure exposure percent mismatch: expected "
            f"{_format_optional_percent(expected_pct)}"
        )
    count_pairs = observations["count_pairs"]
    sale_pressure_count = _int_or_none(package_values.get("sale_pressure_count"))
    product_count = _int_or_none(package_values.get("product_count"))
    if (
        count_pairs
        and {
            "count": sale_pressure_count,
            "base": product_count,
        }
        not in count_pairs
    ):
        reasons.append(
            "sale-pressure exposure count/base mismatch: expected "
            f"{sale_pressure_count}/{product_count}"
        )
    if observations["zero_exposure"] and sale_pressure_count != 0:
        reasons.append(
            "sale-pressure exposure count mismatch: expected 0 exposed products"
        )
    if observations["low_exposure"] and expected_pct is not None:
        threshold = _SALE_PRESSURE_LOW_EXPOSURE_MAX_PCT
        if expected_pct > threshold:
            reasons.append(
                "sale-pressure exposure is not low: expected at most "
                f"{threshold:.1f}%, observed {_format_optional_percent(expected_pct)}"
            )
    return reasons


def _best_sale_pressure_product_exposure_candidate(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    observations = _sale_pressure_exposure_observations(segment)
    if not (
        observations["percent_mentions"]
        or observations["count_pairs"]
        or observations["zero_exposure"]
        or observations["low_exposure"]
    ):
        return None

    bundle_candidates = _bundle_candidates(label, frames)

    evaluations: list[dict[str, Any]] = []
    seen_evaluation_keys: set[tuple[str, str, str]] = set()
    for product_source_file, product_cohort in _sale_pressure_product_source_files(
        segment
    ):
        df = frames.get(product_source_file, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "sale_pressure_status" not in columns:
            continue
        column_lookup = {_canonical_text(column): column for column in columns}
        product_bundle_candidates: list[
            tuple[dict[str, Any], list[tuple[str, str]]]
        ] = [
            (candidate, _bundle_key_parts(candidate["row"]))
            for candidate in bundle_candidates
            if _bundle_key_parts(candidate["row"])
        ]
        if not product_bundle_candidates:
            inferred_parts = _infer_bundle_parts_from_product_frame(label, df)
            if inferred_parts:
                inferred_bundle_key = " + ".join(
                    f"{column}={value}" for column, value in inferred_parts
                )
                product_bundle_candidates = [
                    (
                        {
                            "file": "inferred_product_columns",
                            "row": {
                                "bundle_label": label,
                                "bundle_key": inferred_bundle_key,
                            },
                        },
                        inferred_parts,
                    )
                ]
        for bundle_candidate, bundle_parts in product_bundle_candidates:
            evaluation_key = (
                product_source_file,
                _normalize_text(bundle_candidate["row"].get("bundle_key")),
                product_cohort,
            )
            if evaluation_key in seen_evaluation_keys:
                continue
            seen_evaluation_keys.add(evaluation_key)
            matching_rows = [
                row
                for row in df.to_dicts()
                if _product_row_matches_bundle_parts(row, column_lookup, bundle_parts)
            ]
            if not matching_rows:
                continue
            sale_pressure_count = sum(
                1
                for row in matching_rows
                if _sale_pressure_status_is_exposed(row.get("sale_pressure_status"))
            )
            package_values = _sale_pressure_product_exposure_package_values(
                label=label,
                bundle_candidate=bundle_candidate,
                product_source_file=product_source_file,
                product_cohort=product_cohort,
                product_count=len(matching_rows),
                sale_pressure_count=sale_pressure_count,
            )
            reasons = _score_sale_pressure_product_exposure(
                observations,
                package_values,
            )
            evaluation = {
                "file": product_source_file,
                "bundle_source_file": bundle_candidate["file"],
                "matched_row_keys": {
                    **_candidate_row_keys(bundle_candidate),
                    "bundle_key": _normalize_text(
                        bundle_candidate["row"].get("bundle_key")
                    ),
                    "product_cohort": product_cohort,
                },
                "package_values": package_values,
                "reasons": reasons,
            }
            evaluations.append(evaluation)
            if not reasons:
                return {
                    "status": "pass",
                    "label": label,
                    "source_file": product_source_file,
                    "observed_values": observations["observed_values"],
                    "package_values": package_values,
                    "matched_row_keys": evaluation["matched_row_keys"],
                    "tolerance_policy": _numeric_tolerance_policy(),
                    "candidate_evaluations": evaluations,
                    "reasons": [],
                }

    if not evaluations:
        return {
            "status": "warning",
            "message": (
                "sale-pressure exposure claim could not be computed from product rows"
            ),
            "label": label,
            "source_file": "recent_products.csv/top_seller_products.csv/product_filter_matrix.csv",
            "observed_values": observations["observed_values"],
        }
    evaluations.sort(key=lambda evaluation: len(evaluation["reasons"]))
    best = evaluations[0]
    return {
        "status": "fail",
        "label": label,
        "source_file": best["file"],
        "observed_values": observations["observed_values"],
        "package_values": best["package_values"],
        "matched_row_keys": best["matched_row_keys"],
        "candidate_evaluations": evaluations,
        "tolerance_policy": _numeric_tolerance_policy(),
        "reasons": best["reasons"],
    }


def _sale_pressure_candidates(
    label: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for file_name in ("sale_pressure_pairs.csv", "sale_pressure_triples.csv"):
        df = frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            row_label = _normalize_text(row.get("bundle_label"))
            if row_label and _bundle_label_matches(label, row_label):
                candidates.append(
                    {
                        "file": file_name,
                        "row": row,
                        "label": row_label,
                    }
                )
    return candidates


def _sale_pressure_package_values(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    return {
        "bundle_label": _normalize_text(row.get("bundle_label")),
        "count_sale_pressure": _int_or_none(row.get("count_sale_pressure")),
        "sale_pressure_base": _int_or_none(row.get("sale_pressure_base")),
        "pct_sale_pressure": _percent_from_fraction(row.get("pct_sale_pressure")),
        "count_not_observed_sale_pressure": _int_or_none(
            row.get("count_not_observed_sale_pressure")
        ),
        "not_observed_sale_pressure_base": _int_or_none(
            row.get("not_observed_sale_pressure_base")
        ),
        "pct_not_observed_sale_pressure": _percent_from_fraction(
            row.get("pct_not_observed_sale_pressure")
        ),
        "sale_pressure_brand_count": _int_or_none(row.get("sale_pressure_brand_count")),
        "prevalence_ratio": _float_or_none(row.get("prevalence_ratio")),
    }


def _best_sale_pressure_candidate(
    segment: str,
    label: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    product_exposure_result = _best_sale_pressure_product_exposure_candidate(
        segment,
        label,
        frames,
    )
    if product_exposure_result is not None:
        return product_exposure_result

    candidates = _sale_pressure_candidates(label, frames)
    if not candidates:
        return {
            "status": "warning",
            "message": "no matching sale-pressure package row found for label",
            "label": label,
            "source_file": "sale_pressure_pairs.csv/sale_pressure_triples.csv",
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    percent_mentions = _percent_mentions(segment)
    if not percent_mentions:
        return {
            "status": "warning",
            "message": "sale-pressure claim has no parsed percentage",
            "label": label,
            "candidates": candidates,
            "observed_values": _extract_numeric_claim_evidence(segment),
        }

    evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        package_values = _sale_pressure_package_values(candidate)
        expected_pct = _float_or_none(package_values.get("pct_sale_pressure"))
        reasons: list[str] = []
        if not any(
            _percent_matches(mention, expected_pct) for mention in percent_mentions
        ):
            reasons.append(
                "sale-pressure percent mismatch: expected "
                f"{_format_optional_percent(expected_pct)}"
            )
        evaluations.append(
            {
                "file": candidate["file"],
                "matched_row_keys": _candidate_row_keys(candidate),
                "package_values": package_values,
                "reasons": reasons,
            }
        )
        if not reasons:
            return {
                "status": "pass",
                "candidate": candidate,
                "source_file": candidate["file"],
                "observed_values": _extract_numeric_claim_evidence(segment),
                "package_values": package_values,
                "matched_row_keys": _candidate_row_keys(candidate),
                "tolerance_policy": _numeric_tolerance_policy(),
                "candidate_evaluations": evaluations,
                "reasons": [],
            }

    return {
        "status": "fail",
        "label": label,
        "source_file": candidates[0]["file"],
        "observed_values": _extract_numeric_claim_evidence(segment),
        "candidate_evaluations": evaluations,
        "reasons": evaluations[0]["reasons"] if evaluations else [],
    }


def _validate_sale_pressure_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
    bundle_records: list[_BundleLabelRecord],
) -> list[dict[str, Any]] | None:
    if not _looks_like_sale_pressure_claim(segment):
        return None

    overlap_result = _validate_sale_pressure_overlap_segment(segment, frames)
    if overlap_result is not None:
        return [overlap_result]

    comparison_result = _validate_sale_pressure_comparison_segment(
        segment,
        frames,
        bundle_records,
    )
    if comparison_result is not None:
        return [comparison_result]

    absence_result = _validate_sale_pressure_absence_segment(segment, frames)
    if absence_result is not None:
        return [absence_result]

    matched_labels = _matched_bundle_labels(segment, bundle_records)
    matched_labels = _prefer_explicit_longest_bundle_labels(segment, matched_labels)
    explicit_labels = [
        label
        for label in matched_labels
        if _sale_pressure_label_is_explicit(segment, label)
    ]
    text_labels = _sale_pressure_explicit_bundle_labels_from_text(segment)
    if text_labels:
        matched_labels = text_labels
    elif explicit_labels:
        matched_labels = explicit_labels
    if not matched_labels:
        return [
            {
                "status": "warning",
                "label": "sale_pressure_exposure",
                "source_file": "sale_pressure_pairs.csv/sale_pressure_triples.csv",
                "message": "sale-pressure claim was detected but no bundle label matched",
                "observed_values": _extract_numeric_claim_evidence(segment),
            }
        ]

    return [
        _best_sale_pressure_candidate(segment, label, frames)
        for label in matched_labels
    ]


def _sale_pressure_details(result: dict[str, Any]) -> dict[str, Any]:
    details = {
        "observed_values": result.get("observed_values", {}),
        "package_values": result.get("package_values", {}),
        "source_file": result.get("source_file"),
        "matched_row_keys": result.get("matched_row_keys", {}),
        "candidate_evaluations": result.get("candidate_evaluations", []),
        "tolerance_policy": result.get("tolerance_policy", _numeric_tolerance_policy()),
        "qualitative_threshold_policy": _sale_pressure_qualitative_threshold_policy(),
        "comparison_outcome": result.get("status"),
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("aggregation_rule_id"):
        details["aggregation_rule_id"] = _normalize_text(
            result.get("aggregation_rule_id")
        )
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    return details


_VISIBILITY_GROSS_RE = re.compile(
    r"\bgross\s+weight\s+(?:(?P<gross>\d+(?:\.\d+)?)%|(?P<present>present))",
    re.IGNORECASE,
)
_VISIBILITY_GROSS_SUFFIX_RE = re.compile(
    r"\b(?P<gross>\d+(?:\.\d+)?)%\s+gross\b",
    re.IGNORECASE,
)
_VISIBILITY_TOTAL_RE = re.compile(
    r"\b(?:total\s+)?visibility\s*\(?(?P<total>\d+(?:\.\d+)?)%\)?",
    re.IGNORECASE,
)
_VISIBILITY_INCREMENTAL_RE = re.compile(
    r"\bincremental\s+weight\s+(?P<incremental>\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
_VISIBILITY_INCREMENTAL_VISIBILITY_RE = re.compile(
    r"\bincremental\s+visibility\s*:?\s*(?P<incremental>\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
_VISIBILITY_CUMULATIVE_RE = re.compile(
    r"\bcumulative(?:\s+selected)?\s+weight\s+(?:to\s+)?(?P<cumulative>\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
_VISIBILITY_ALPHA_RE = re.compile(
    r"\b(?:central\s+)?alpha\s*(?:=|is)?\s*(?P<alpha>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _looks_like_rank_weighted_visibility_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "rank-weighted visibility",
            "gross weight",
            "incremental weight",
            "cumulative selected weight",
            "central alpha",
            "not incremental",
        )
    ) or bool(
        _VISIBILITY_GROSS_SUFFIX_RE.search(text)
        or _VISIBILITY_TOTAL_RE.search(text)
        or _VISIBILITY_INCREMENTAL_VISIBILITY_RE.search(text)
    )


def _visibility_observed_values(segment: str) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    gross_match = _VISIBILITY_GROSS_RE.search(segment)
    if gross_match is not None:
        if gross_match.group("gross") is not None:
            observed["gross_weight_share_pct"] = float(gross_match.group("gross"))
        elif gross_match.group("present") is not None:
            observed["gross_weight_present"] = True
    else:
        gross_suffix_match = _VISIBILITY_GROSS_SUFFIX_RE.search(segment)
        total_match = _VISIBILITY_TOTAL_RE.search(segment)
        if gross_suffix_match is not None:
            observed["gross_weight_share_pct"] = float(
                gross_suffix_match.group("gross")
            )
        elif total_match is not None:
            observed["gross_weight_share_pct"] = float(total_match.group("total"))

    incremental_match = _VISIBILITY_INCREMENTAL_RE.search(segment)
    if incremental_match is None:
        incremental_match = _VISIBILITY_INCREMENTAL_VISIBILITY_RE.search(segment)
    if incremental_match is not None:
        observed["incremental_weight_share_pct"] = float(
            incremental_match.group("incremental")
        )

    cumulative_match = _VISIBILITY_CUMULATIVE_RE.search(segment)
    if cumulative_match is not None:
        observed["cumulative_weight_share_pct"] = float(
            cumulative_match.group("cumulative")
        )

    alpha_match = _VISIBILITY_ALPHA_RE.search(segment)
    if alpha_match is not None:
        observed["alpha"] = float(alpha_match.group("alpha"))
    return observed


def _visibility_label_from_segment(segment: str) -> str:
    prefix = segment.split(":", 1)[0] if ":" in segment else segment
    prefix = prefix.split(";", 1)[0]
    metric_match = re.search(
        r"\b(?:gross\s+weight|incremental\s+weight|incremental\s+visibility|cumulative(?:\s+selected)?\s+weight|structural\s+refinements?|\d+(?:\.\d+)?%\s+gross|not\s+incremental|(?:total\s+)?visibility\s*\(?\d+(?:\.\d+)?%)\b",
        prefix,
        flags=re.IGNORECASE,
    )
    if metric_match is not None:
        prefix = prefix[: metric_match.start()]
    prefix = re.sub(
        r"\b(?:dominates|drives|captures|represents|accounts)\b.*$",
        "",
        prefix,
        flags=re.IGNORECASE,
    )
    prefix = re.sub(r"[\s|:/,-]+$", "", prefix)
    return _normalize_text(prefix)


def _visibility_candidate_rows(
    frames: dict[str, pl.DataFrame],
    *,
    source_file: str,
) -> list[dict[str, Any]]:
    df = frames.get(source_file, pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    if df.is_empty() or "bundle_key" not in columns:
        return []
    return [
        {
            "file": source_file,
            "row": row,
            "label": _normalize_text(row.get("bundle_key")),
        }
        for row in df.to_dicts()
        if _normalize_text(row.get("bundle_key"))
        and _normalize_text(row.get("bundle_key")) != "__residual__"
    ]


def _best_visibility_candidate(
    segment: str,
    frames: dict[str, pl.DataFrame],
    *,
    observed_alpha: float | None,
    source_file: str,
) -> dict[str, Any] | None:
    label = _visibility_label_from_segment(segment)
    if not label or "+" not in label:
        return None
    candidates = [
        candidate
        for candidate in _visibility_candidate_rows(frames, source_file=source_file)
        if _bundle_label_matches(label, candidate["label"])
    ]
    if not candidates:
        return None
    if observed_alpha is not None:
        alpha_matches = [
            candidate
            for candidate in candidates
            if _approx_equal(
                _float_or_none(candidate["row"].get("alpha")),
                observed_alpha,
                1e-9,
            )
        ]
        if alpha_matches:
            candidates = alpha_matches
    else:
        central_alpha_matches = [
            candidate
            for candidate in candidates
            if _approx_equal(_float_or_none(candidate["row"].get("alpha")), 1.0, 1e-9)
        ]
        if central_alpha_matches:
            candidates = central_alpha_matches
    candidates.sort(
        key=lambda candidate: (
            _float_or_none(candidate["row"].get("alpha")) or -1.0,
            -(_int_or_none(candidate["row"].get("shelf_rank")) or 9999),
        ),
        reverse=True,
    )
    return candidates[0]


def _visibility_package_values(candidate: dict[str, Any]) -> dict[str, Any]:
    row = candidate["row"]
    return {
        "alpha": _float_or_none(row.get("alpha")),
        "shelf_rank": _int_or_none(row.get("shelf_rank")),
        "bundle_key": _normalize_text(row.get("bundle_key")),
        "gross_weight_share_pct": _percent_from_fraction(row.get("gross_weight_share")),
        "incremental_weight_share_pct": _percent_from_fraction(
            row.get("incremental_weight_share")
        ),
        "cumulative_weight_share_pct": _percent_from_fraction(
            row.get("cumulative_weight_share")
        ),
        "gross_sku_count": _int_or_none(row.get("gross_sku_count")),
        "incremental_sku_count": _int_or_none(row.get("incremental_sku_count")),
        "gross_brand_count": _int_or_none(row.get("gross_brand_count")),
        "incremental_brand_count": _int_or_none(row.get("incremental_brand_count")),
        "density_index": _float_or_none(row.get("density_index")),
        "top_products": _normalize_text(row.get("top_products")),
        "top_brands": _normalize_text(row.get("top_brands")),
    }


def _component_value_mentioned(segment: str, value: str) -> bool:
    value_tokens = _canonical_tokens(value)
    if not value_tokens:
        return False
    return value_tokens <= _canonical_tokens(segment)


def _visibility_common_component_result(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    lowered = segment.casefold()
    if not (
        "common category spine" in lowered
        or "serves as the common" in lowered
        or "common category" in lowered
    ):
        return None

    matches_by_component: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    seen_rows: set[tuple[str, str, float | None]] = set()
    for source_file in (
        "web_shelf_selected_shelves.csv",
        "web_shelf_candidate_shelves.csv",
    ):
        for candidate in _visibility_candidate_rows(frames, source_file=source_file):
            row = candidate["row"]
            gross_weight = _float_or_none(row.get("gross_weight_share"))
            if gross_weight is None or gross_weight <= 0:
                continue
            bundle_key = _normalize_text(row.get("bundle_key"))
            alpha = _float_or_none(row.get("alpha"))
            row_key = (source_file, bundle_key, alpha)
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            parts = _bundle_key_parts(row)
            if len(parts) < 2:
                continue
            for attribute_name, attribute_value in parts:
                if not _component_value_mentioned(segment, attribute_value):
                    continue
                partner_values = [
                    value
                    for _other_attribute, value in parts
                    if _canonical_text(value) != _canonical_text(attribute_value)
                ]
                matches_by_component[(attribute_name, attribute_value)].append(
                    {
                        "source_file": source_file,
                        "bundle_key": bundle_key,
                        "alpha": alpha,
                        "gross_weight_share_pct": _percent_from_fraction(gross_weight),
                        "gross_sku_count": _int_or_none(row.get("gross_sku_count")),
                        "gross_brand_count": _int_or_none(row.get("gross_brand_count")),
                        "partner_values": _unique_texts(partner_values),
                    }
                )

    if not matches_by_component:
        return {
            "status": "warning",
            "message": "visibility common-component summary did not match package rows",
            "observed_values": {},
            "source_file": "web_shelf_selected_shelves.csv",
        }

    component_key, row_support = max(
        matches_by_component.items(),
        key=lambda item: (
            len(
                {
                    _canonical_text(partner)
                    for row in item[1]
                    for partner in row.get("partner_values", [])
                }
            ),
            len(item[1]),
        ),
    )
    partner_count = len(
        {
            _canonical_text(partner)
            for row in row_support
            for partner in row.get("partner_values", [])
        }
    )
    status = "pass" if len(row_support) >= 3 and partner_count >= 2 else "warning"
    source_files = sorted(
        {
            _normalize_text(row.get("source_file"))
            for row in row_support
            if _normalize_text(row.get("source_file"))
        }
    )
    return {
        "status": status,
        "message": (
            ""
            if status == "pass"
            else "visibility common-component summary has insufficient row support"
        ),
        "source_file": "+".join(source_files) or "web_shelf_selected_shelves.csv",
        "observed_values": {
            "claimed_common_component": component_key[1],
        },
        "package_values": {
            "matched_component": {
                "attribute_name": component_key[0],
                "attribute_value": component_key[1],
            },
            "supporting_row_count": len(row_support),
            "distinct_partner_count": partner_count,
            "row_support": row_support[:8],
        },
        "matched_row_keys": {
            "attribute_name": component_key[0],
            "attribute_value": component_key[1],
        },
        "tolerance_policy": _numeric_tolerance_policy(),
        "aggregation_rule_id": "visibility_common_component_spine_v1",
        "reasons": (
            []
            if status == "pass"
            else ["fewer than 3 rows or 2 partner components share the named spine"]
        ),
    }


def _validate_rank_weighted_visibility_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_rank_weighted_visibility_claim(segment):
        return None

    observed = _visibility_observed_values(segment)
    selected_df = frames.get("web_shelf_selected_shelves.csv", pl.DataFrame())
    candidate_df = frames.get("web_shelf_candidate_shelves.csv", pl.DataFrame())
    if selected_df.is_empty() and candidate_df.is_empty():
        return {
            "status": "warning",
            "message": "rank-weighted visibility source rows are missing",
            "observed_values": observed,
            "source_file": "web_shelf_selected_shelves.csv",
        }

    common_component_result = _visibility_common_component_result(segment, frames)
    if common_component_result is not None:
        return common_component_result

    if "alpha" in observed and "+" not in _visibility_label_from_segment(segment):
        alpha_source_df = selected_df
        alpha_source_file = "web_shelf_selected_shelves.csv"
        columns, _schema = get_schema_and_column_names(alpha_source_df)
        if alpha_source_df.is_empty() or "alpha" not in columns:
            alpha_source_df = candidate_df
            alpha_source_file = "web_shelf_candidate_shelves.csv"
            columns, _schema = get_schema_and_column_names(alpha_source_df)
        if alpha_source_df.is_empty() or "alpha" not in columns:
            return {
                "status": "warning",
                "message": "rank-weighted visibility alpha source rows are missing",
                "observed_values": observed,
                "source_file": alpha_source_file,
            }
        alpha_values = [
            _float_or_none(value)
            for value in alpha_source_df.get_column("alpha").drop_nulls().to_list()
            if _float_or_none(value) is not None
        ]
        alpha_found = any(
            _approx_equal(value, observed["alpha"], 1e-9)
            for value in alpha_values
            if value is not None
        )
        return {
            "status": "pass" if alpha_found else "fail",
            "source_file": alpha_source_file,
            "observed_values": observed,
            "package_values": {"available_alphas": sorted(set(alpha_values))},
            "reasons": (
                []
                if alpha_found
                else [f"alpha {observed['alpha']} is missing from selected shelves"]
            ),
        }

    candidate = _best_visibility_candidate(
        segment,
        frames,
        observed_alpha=_float_or_none(observed.get("alpha")),
        source_file="web_shelf_selected_shelves.csv",
    )
    source_file = "web_shelf_selected_shelves.csv"
    if candidate is None:
        candidate = _best_visibility_candidate(
            segment,
            frames,
            observed_alpha=_float_or_none(observed.get("alpha")),
            source_file="web_shelf_candidate_shelves.csv",
        )
        source_file = "web_shelf_candidate_shelves.csv"
    if candidate is None:
        return {
            "status": "warning",
            "message": "visibility bundle row was not matched",
            "observed_values": observed,
            "source_file": "web_shelf_selected_shelves.csv",
        }

    package_values = _visibility_package_values(candidate)
    tolerance = max(
        (mention.tolerance for mention in _percent_mentions(segment)),
        default=_VISIBILITY_PERCENT_TOLERANCE,
    )
    tolerance = max(tolerance, _VISIBILITY_PERCENT_TOLERANCE)
    reasons: list[str] = []
    for observed_key, package_key, label in (
        ("gross_weight_share_pct", "gross_weight_share_pct", "gross weight"),
        (
            "incremental_weight_share_pct",
            "incremental_weight_share_pct",
            "incremental weight",
        ),
        (
            "cumulative_weight_share_pct",
            "cumulative_weight_share_pct",
            "cumulative weight",
        ),
    ):
        if observed_key not in observed:
            continue
        expected = _float_or_none(package_values.get(package_key))
        if expected is None or not _approx_equal(
            _float_or_none(observed.get(observed_key)),
            expected,
            tolerance,
        ):
            reasons.append(
                f"{label} mismatch: expected {_format_optional_percent(expected)}"
            )

    if observed.get("gross_weight_present") is True:
        expected = _float_or_none(package_values.get("gross_weight_share_pct"))
        if expected is None or expected <= 0:
            reasons.append("gross weight was claimed present but package row is empty")

    return {
        "status": "fail" if reasons else "pass",
        "source_file": source_file,
        "candidate": candidate,
        "observed_values": observed,
        "package_values": package_values,
        "matched_row_keys": {
            "bundle_key": package_values.get("bundle_key"),
            "alpha": package_values.get("alpha"),
            "shelf_rank": package_values.get("shelf_rank"),
        },
        "tolerance_policy": _numeric_tolerance_policy(),
        "reasons": reasons,
    }


def _rank_weighted_visibility_details(result: dict[str, Any]) -> dict[str, Any]:
    details = {
        "observed_values": result.get("observed_values", {}),
        "package_values": result.get("package_values", {}),
        "source_file": result.get("source_file"),
        "matched_row_keys": result.get("matched_row_keys", {}),
        "tolerance_policy": result.get("tolerance_policy", _numeric_tolerance_policy()),
        "comparison_outcome": result.get("status"),
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("aggregation_rule_id"):
        details["aggregation_rule_id"] = _normalize_text(
            result.get("aggregation_rule_id")
        )
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    return details


def _baseline_visibility_recent_construction_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_baseline_presence_pct": 60.0,
        "minimum_visibility_gross_weight_share_pct": 40.0,
        "minimum_recent_decline_pct_points": 5.0,
        "source_files": [
            "filter_comparison.csv",
            "web_shelf_robustness_summary.csv",
            "web_shelf_selected_shelves.csv",
            "web_shelf_candidate_shelves.csv",
        ],
    }


def _looks_like_baseline_visibility_recent_construction_claim(text: str) -> bool:
    lowered = text.casefold()
    return (
        "baseline visibility" in lowered
        and "recent product construction" in lowered
        and ("lower" in lowered or "less" in lowered)
    )


def _web_shelf_row_matches_attribute(
    row: dict[str, Any],
    *,
    attribute_name: str,
    attribute_value: str,
) -> bool:
    target_attribute = _canonical_text(attribute_name)
    target_value = _canonical_text(attribute_value)
    if not target_attribute or not target_value:
        return False
    for row_attribute, row_value in _bundle_key_parts(row):
        if (
            _canonical_text(row_attribute) == target_attribute
            and _canonical_text(row_value) == target_value
        ):
            return True
    return False


def _baseline_visibility_web_shelf_support(
    *,
    attribute_name: str,
    attribute_value: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for source_file, weight_column, selected_count_column in (
        (
            "web_shelf_robustness_summary.csv",
            "average_gross_weight_share",
            "times_selected",
        ),
        ("web_shelf_selected_shelves.csv", "gross_weight_share", None),
        ("web_shelf_candidate_shelves.csv", "gross_weight_share", None),
    ):
        df = frames.get(source_file, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_key" not in columns or weight_column not in columns:
            continue
        for row in df.to_dicts():
            if not _web_shelf_row_matches_attribute(
                row,
                attribute_name=attribute_name,
                attribute_value=attribute_value,
            ):
                continue
            gross_weight_share_pct = _percent_from_fraction(row.get(weight_column))
            if gross_weight_share_pct is None:
                continue
            candidates.append(
                {
                    "source_file": source_file,
                    "matched_row_keys": {
                        "bundle_key": _normalize_text(row.get("bundle_key")),
                        "attribute_name": attribute_name,
                        "attribute_value": attribute_value,
                    },
                    "computed_values": {
                        "gross_weight_share_pct": round(gross_weight_share_pct, 4),
                        "selected_count": (
                            _int_or_none(row.get(selected_count_column))
                            if selected_count_column
                            else None
                        ),
                        "shelf_rank": _int_or_none(
                            row.get("best_shelf_rank", row.get("shelf_rank"))
                        ),
                        "gross_sku_count": _int_or_none(row.get("gross_sku_count")),
                        "gross_brand_count": _int_or_none(row.get("gross_brand_count")),
                    },
                }
            )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["source_file"] == "web_shelf_robustness_summary.csv",
            _int_or_none(item["computed_values"].get("selected_count")) or 0,
            _float_or_none(item["computed_values"].get("gross_weight_share_pct"))
            or 0.0,
            -(_int_or_none(item["computed_values"].get("shelf_rank")) or 9999),
        ),
        reverse=True,
    )
    return candidates[0]


def _baseline_visibility_recent_construction_candidates(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    df = frames.get("filter_comparison.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(df)
    required = {
        "filter_family",
        "filter_value",
        "count_recent",
        "count_rest",
        "recent_family_base",
        "rest_family_base",
        "pct_recent",
        "pct_rest",
    }
    if df.is_empty() or not required <= set(columns):
        return []

    candidates: list[dict[str, Any]] = []
    for row in df.to_dicts():
        filter_family = _normalize_text(row.get("filter_family"))
        filter_value = _normalize_text(row.get("filter_value"))
        if not filter_family or not _component_value_mentioned(segment, filter_value):
            continue
        recent_pct = _percent_from_fraction(row.get("pct_recent"))
        rest_pct = _percent_from_fraction(row.get("pct_rest"))
        if recent_pct is None or rest_pct is None:
            continue
        shelf_support = _baseline_visibility_web_shelf_support(
            attribute_name=filter_family,
            attribute_value=filter_value,
            frames=frames,
        )
        baseline_presence_pct = max(recent_pct, rest_pct)
        recent_decline_pct_points = rest_pct - recent_pct
        candidates.append(
            {
                "source_file": "filter_comparison.csv",
                "matched_row_keys": {
                    "filter_family": filter_family,
                    "filter_value": filter_value,
                },
                "computed_values": {
                    "recent_pct": round(recent_pct, 4),
                    "rest_pct": round(rest_pct, 4),
                    "baseline_presence_pct": round(baseline_presence_pct, 4),
                    "recent_decline_pct_points": round(
                        recent_decline_pct_points,
                        4,
                    ),
                    "count_recent": _int_or_none(row.get("count_recent")),
                    "count_rest": _int_or_none(row.get("count_rest")),
                    "recent_family_base": _int_or_none(row.get("recent_family_base")),
                    "rest_family_base": _int_or_none(row.get("rest_family_base")),
                },
                "visibility_support": shelf_support,
            }
        )

    candidates.sort(
        key=lambda item: (
            item["computed_values"]["recent_decline_pct_points"],
            item["computed_values"]["baseline_presence_pct"],
        ),
        reverse=True,
    )
    return candidates


def _validate_baseline_visibility_recent_construction_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_baseline_visibility_recent_construction_claim(segment):
        return None

    threshold_policy = _baseline_visibility_recent_construction_threshold_policy()
    candidates = _baseline_visibility_recent_construction_candidates(segment, frames)
    if not candidates:
        return None

    candidate = candidates[0]
    computed_values = candidate["computed_values"]
    visibility_support = candidate.get("visibility_support")
    visibility_weight_pct = (
        _float_or_none(
            visibility_support["computed_values"].get("gross_weight_share_pct")
        )
        if visibility_support
        else None
    )
    reasons: list[str] = []
    if (
        _float_or_none(computed_values.get("baseline_presence_pct")) or 0.0
    ) < threshold_policy["minimum_baseline_presence_pct"]:
        reasons.append("filter value is not broad enough to be baseline visibility")
    if (
        _float_or_none(computed_values.get("recent_decline_pct_points")) or 0.0
    ) < threshold_policy["minimum_recent_decline_pct_points"]:
        reasons.append("recent construction is not lower than rest by threshold")
    if (
        visibility_weight_pct is None
        or visibility_weight_pct
        < threshold_policy["minimum_visibility_gross_weight_share_pct"]
    ):
        reasons.append("web-shelf visibility support is missing or below threshold")

    row_support = [
        {key: value for key, value in candidate.items() if key != "visibility_support"}
    ]
    if visibility_support:
        row_support.append(visibility_support)

    return {
        "status": "pass" if not reasons else "fail",
        "row_support": row_support,
        "component_entities": [
            _normalize_text(candidate["matched_row_keys"].get("filter_value"))
        ],
        "aggregation_rule_id": "baseline_visibility_recent_construction_v1",
        "cohort_basis": "recent_vs_rest_filter_presence_with_web_shelf_visibility",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "named filter value must be broadly present, visibly represented in "
            "web-shelf rows, and lower in recent product construction than rest"
        ),
        "missing_components": [] if not reasons else ["baseline_visibility"],
        "reasons": reasons,
    }


def _money_tolerance(raw_amount: str) -> float:
    decimals = len(raw_amount.split(".", 1)[1]) if "." in raw_amount else 0
    return (0.5 * (10**-decimals)) + 1e-9


def _price_role(segment: str, span: tuple[int, int]) -> str | None:
    immediate_after = segment[span[1] : span[1] + 40].casefold()
    immediate_before = segment[max(0, span[0] - 45) : span[0]].casefold()
    role_patterns = (
        ("recent", r"\brecent\b"),
        ("rest", r"\b(?:rest|others?|other|remaining)\b"),
        ("all", r"\b(?:all|category|catalog|market)\b"),
    )
    for role, pattern in role_patterns:
        if re.match(rf"\s*(?:{pattern})\b", immediate_after):
            return role
    for role, pattern in role_patterns:
        if re.search(
            rf"(?:{pattern})\s*(?:entry\s+price|price)?\s*$", immediate_before
        ):
            return role
    return None


def _price_money_mentions(segment: str) -> list[_MoneyMention]:
    mentions: list[_MoneyMention] = []
    for match in _PRICE_MONEY_RE.finditer(segment):
        raw_amount = match.group("amount")
        amount = _float_or_none(raw_amount.replace(",", ""))
        if amount is None:
            continue
        mentions.append(
            _MoneyMention(
                value=amount,
                tolerance=_money_tolerance(raw_amount),
                role=_price_role(segment, match.span()),
                span=match.span(),
            )
        )
    if len(mentions) == 2 and re.search(
        r"\bvs\.?\b", segment[mentions[0].span[1] : mentions[1].span[0]], re.IGNORECASE
    ):
        first, second = mentions
        before_first = segment[: first.span[0]].casefold()
        if first.role == "recent" and second.role is None:
            mentions[1] = _MoneyMention(
                value=second.value,
                tolerance=second.tolerance,
                role="rest",
                span=second.span,
            )
        elif first.role is None and second.role == "rest":
            mentions[0] = _MoneyMention(
                value=first.value,
                tolerance=first.tolerance,
                role="recent",
                span=first.span,
            )
        elif (
            first.role is None
            and second.role is None
            and re.search(r"\brecent\b", before_first)
        ):
            mentions = [
                _MoneyMention(
                    value=first.value,
                    tolerance=first.tolerance,
                    role="recent",
                    span=first.span,
                ),
                _MoneyMention(
                    value=second.value,
                    tolerance=second.tolerance,
                    role="rest",
                    span=second.span,
                ),
            ]
    return mentions


def _looks_like_entry_price_comparison_claim(text: str) -> bool:
    lowered = text.casefold()
    if len(_price_money_mentions(text)) < 2:
        return False
    if "entry price" in lowered:
        return True
    return bool(
        re.search(
            r"\b(?:median|average|avg\.?|mean)\b.{0,40}\bprice\b|"
            r"\bprice\b.{0,40}\b(?:median|average|avg\.?|mean)\b",
            lowered,
        )
    )


def _price_metric_from_segment(segment: str) -> str | None:
    lowered = segment.casefold()
    if re.search(r"\bmedian\b", lowered):
        return "median"
    if re.search(r"\b(?:average|avg\.?|mean)\b", lowered):
        return "mean"
    return None


def _entry_price_key_column(
    recent_df: pl.DataFrame,
    all_df: pl.DataFrame,
) -> str | None:
    recent_columns, _recent_schema = get_schema_and_column_names(recent_df)
    all_columns, _all_schema = get_schema_and_column_names(all_df)
    for column in (
        "canonical_id_export",
        "canonical_id",
        "parent_product_id",
        "listing_identity",
        "pdp_url",
        "product_name_norm",
        "product_name",
    ):
        if column not in recent_columns or column not in all_columns:
            continue
        recent_values = [
            _normalize_text(row.get(column))
            for row in recent_df.select(column).to_dicts()
            if _normalize_text(row.get(column))
        ]
        all_values = {
            _normalize_text(row.get(column))
            for row in all_df.select(column).to_dicts()
            if _normalize_text(row.get(column))
        }
        if recent_values and any(value in all_values for value in recent_values):
            return column
    return None


def _entry_price_values(rows: Iterable[dict[str, Any]]) -> list[float]:
    prices: list[float] = []
    for row in rows:
        price = _float_or_none(row.get("entry_price"))
        if price is not None:
            prices.append(price)
    return prices


def _price_stat(values: list[float], metric: str) -> float | None:
    if not values:
        return None
    series = pl.Series(values)
    if metric == "median":
        return _float_or_none(series.median())
    return _float_or_none(series.mean())


def _format_optional_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def _entry_price_population_values(
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    recent_df = frames.get("recent_products.csv", pl.DataFrame())
    all_df = frames.get("product_filter_matrix.csv", pl.DataFrame())
    recent_columns, _recent_schema = get_schema_and_column_names(recent_df)
    all_columns, _all_schema = get_schema_and_column_names(all_df)
    if (
        recent_df.is_empty()
        or all_df.is_empty()
        or "entry_price" not in recent_columns
        or "entry_price" not in all_columns
    ):
        return None

    key_column = _entry_price_key_column(recent_df, all_df)
    if key_column is None:
        return None
    recent_keys = {
        _normalize_text(row.get(key_column))
        for row in recent_df.select(key_column).to_dicts()
        if _normalize_text(row.get(key_column))
    }
    all_rows = all_df.to_dicts()
    recent_rows = recent_df.to_dicts()
    rest_rows = [
        row
        for row in all_rows
        if _normalize_text(row.get(key_column)) not in recent_keys
    ]
    recent_prices = _entry_price_values(recent_rows)
    rest_prices = _entry_price_values(rest_rows)
    all_prices = _entry_price_values(all_rows)
    if not recent_prices or not rest_prices:
        return None
    return {
        "key_column": key_column,
        "cohorts": {
            "recent": {
                "entry_price_mean": _price_stat(recent_prices, "mean"),
                "entry_price_median": _price_stat(recent_prices, "median"),
                "priced_product_count": len(recent_prices),
                "source_file": "recent_products.csv",
            },
            "rest": {
                "entry_price_mean": _price_stat(rest_prices, "mean"),
                "entry_price_median": _price_stat(rest_prices, "median"),
                "priced_product_count": len(rest_prices),
                "source_file": "product_filter_matrix.csv",
            },
            "all": {
                "entry_price_mean": _price_stat(all_prices, "mean"),
                "entry_price_median": _price_stat(all_prices, "median"),
                "priced_product_count": len(all_prices),
                "source_file": "product_filter_matrix.csv",
            },
        },
        "denominator_rule": (
            "recent_products.csv is the recent cohort; rest excludes matching "
            f"{key_column} values from product_filter_matrix.csv"
        ),
    }


def _entry_price_observed_values(
    metric: str,
    mentions: list[_MoneyMention],
) -> dict[str, Any]:
    return {
        "metric": metric,
        "money_mentions": [
            {
                "value": mention.value,
                "role": mention.role,
                "tolerance": mention.tolerance,
            }
            for mention in mentions
        ],
    }


def _validate_entry_price_comparison_segment(
    segment: str,
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_entry_price_comparison_claim(segment):
        return None
    mentions = _price_money_mentions(segment)
    metric = _price_metric_from_segment(segment)
    if metric is None:
        return {
            "status": "warning",
            "message": "entry-price claim did not specify mean or median",
            "observed_values": _entry_price_observed_values("unknown", mentions),
            "source_file": "recent_products.csv+product_filter_matrix.csv",
        }

    population_values = _entry_price_population_values(frames)
    if population_values is None:
        return {
            "status": "warning",
            "message": "entry-price source rows are missing or cannot be joined",
            "observed_values": _entry_price_observed_values(metric, mentions),
            "source_file": "recent_products.csv+product_filter_matrix.csv",
        }

    observed_by_role: dict[str, _MoneyMention] = {}
    for mention in mentions:
        if (
            mention.role in {"recent", "rest", "all"}
            and mention.role not in observed_by_role
        ):
            observed_by_role[mention.role] = mention
    if "recent" not in observed_by_role or (
        "rest" not in observed_by_role and "all" not in observed_by_role
    ):
        return {
            "status": "warning",
            "message": "entry-price claim did not resolve compared cohorts",
            "observed_values": _entry_price_observed_values(metric, mentions),
            "package_values": population_values,
            "source_file": "recent_products.csv+product_filter_matrix.csv",
        }

    comparison_roles = ["recent", "rest" if "rest" in observed_by_role else "all"]
    reasons: list[str] = []
    for role in comparison_roles:
        mention = observed_by_role[role]
        expected = _float_or_none(
            population_values["cohorts"][role].get(f"entry_price_{metric}")
        )
        if not _approx_equal(mention.value, expected, mention.tolerance):
            reasons.append(
                f"{role} {metric} entry price mismatch: expected "
                f"{_format_optional_money(expected)}"
            )

    return {
        "status": "fail" if reasons else "pass",
        "source_file": "recent_products.csv+product_filter_matrix.csv",
        "observed_values": _entry_price_observed_values(metric, mentions),
        "package_values": population_values,
        "matched_row_keys": {
            "metric": metric,
            "comparison_roles": comparison_roles,
        },
        "tolerance_policy": {
            "money_tolerance": "half of the displayed dollar precision",
            "cohort_rule": population_values["denominator_rule"],
        },
        "reasons": reasons,
    }


def _entry_price_details(result: dict[str, Any]) -> dict[str, Any]:
    details = {
        "observed_values": result.get("observed_values", {}),
        "package_values": result.get("package_values", {}),
        "source_file": result.get("source_file"),
        "matched_row_keys": result.get("matched_row_keys", {}),
        "tolerance_policy": result.get("tolerance_policy", {}),
        "comparison_outcome": result.get("status"),
    }
    if result.get("message"):
        details["message"] = _normalize_text(result.get("message"))
    if result.get("reasons"):
        details["reasons"] = result["reasons"]
    return details


def _looks_like_summary_synthesis_claim(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "baseline is anchored",
            "broad baseline bundle",
            "category baseline",
            "category is anchored",
            "category is being won",
            "category signal is stable",
            "category volume is not driven",
            "category-level structural narrative",
            "clean break from the baseline",
            "consolidate into this single narrative",
            "conventional sneaker construction",
            "coverage/undertone",
            "core attribute bundles",
            "core category signal",
            "core top-seller architecture",
            "credible emerging signal",
            "current anchor:",
            "current top sellers",
            "current top-seller architecture",
            "current winning format",
            "directly embodies",
            "direct extensions of the current winner baseline",
            "does not constitute a clear current winner",
            "does not define",
            "does not dictate winning performance",
            "does not overturn the core architecture",
            "dominant baseline",
            "dominant format:",
            "dominant texture",
            "dominant white-leather core",
            "duplicate the attributes",
            "drivers of shelf success",
            "driven by classic",
            "emerging layer",
            "emerging movement",
            "emerging multicolor:",
            "emerging neckline",
            "emerging signal",
            "emerging technical:",
            "emerging vector:",
            "format-radical",
            "format resistance",
            "familiar knit architecture",
            "firmly anchored",
            "filter-layer artifact",
            "filter-layerartifact",
            "filter artifact",
            "fundamentally prioritizing",
            "functions meaningfully",
            "gross visibility is broad",
            "higher brand-concentration caveats",
            "health-need shift",
            "high-visibility innovation examples",
            "high incremental value",
            "highly discriminating signal",
            "integration of multicolor",
            "aligning with",
            "aligning perfectly",
            "analytical artifact",
            "architecture is familiar",
            "incremental visibility adds",
            "incremental visibility is narrow",
            "innovation layer is weaker",
            "new arrivals overwhelmingly duplicate",
            "main winning signals",
            "market signal",
            "market traction",
            "not a separate innovation story",
            "not defined by radical",
            "ongoing churn",
            "powder anchor",
            "overlapping metrics",
            "primary pillar",
            "product-real",
            "product detail pages",
            "promotion pressure",
            "qualifies parts of the read",
            "rank-weighted by",
            "recent product additions reinforce",
            "reinforce the baseline",
            "reviews support",
            "secondary lane",
            "secondary modifiers",
            "secondary signals",
            "secondary, thinner emerging lane",
            "stable core:",
            "specific bundle combinations",
            "specific texture formats",
            "strongest cross-product prevalence",
            "strongest current winner",
            "strongest emerging signal",
            "strongest recent bundles",
            "structurally narrower",
            "structural core",
            "structural reality",
            "shelf is definitely won",
            "shelf visibility is heavily defined",
            "single shelf logic",
            "top-selling baseline",
            "top-rank-driven pocket",
            "top-seller headlines",
            "top-seller architecture",
            "top-seller reality",
            "true incremental visibility",
            "winning baseline",
            "winning now:",
            "winning products",
            "winner by volume",
            "winning architecture",
            "anchored by broad",
            "shade architectures",
            "volume is driven primarily by",
            "visibility mechanics",
            "visually conventional",
            "web-shelf architecture",
            "cover this classic",
            "winning proposition",
            "brand concentration",
        )
    )


def _claim_component_search_tokens(claim: dict[str, Any]) -> set[str]:
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    values: list[str] = [
        _normalize_text(claim.get("claim_text")),
        _normalize_text(claim.get("entity")),
    ]
    component_entities = (
        details.get("component_entities")
        if isinstance(details.get("component_entities"), list)
        else []
    )
    values.extend(_normalize_text(item) for item in component_entities)
    return _canonical_tokens(" ".join(value for value in values if value))


def _matching_verified_claims(
    claims: list[dict[str, Any]],
    *,
    families: set[str],
    required_tokens: set[str],
    source_file_prefix: str | None = None,
    accepted_statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    statuses = accepted_statuses or {"verified"}
    matches: list[dict[str, Any]] = []
    for claim in claims:
        if claim.get("status") not in statuses:
            continue
        if claim.get("claim_family") not in families:
            continue
        if source_file_prefix is not None and not _normalize_text(
            claim.get("file")
        ).startswith(source_file_prefix):
            continue
        claim_tokens = _claim_component_search_tokens(claim)
        if not (required_tokens & claim_tokens):
            continue
        matches.append(claim)
    return matches


def _summary_synthesis_support_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    for token in _summary_content_tokens(_normalize_text(value)):
        if token in _SUMMARY_SYNTHESIS_SUPPORT_NOISE_TOKENS:
            continue
        tokens.add(token)
        for alias in _SUMMARY_SYNTHESIS_TOKEN_ALIASES.get(token, ()):
            if alias not in _SUMMARY_SYNTHESIS_SUPPORT_NOISE_TOKENS:
                tokens.add(alias)
    return tokens


def _claim_component_entity_tokens(claim: dict[str, Any]) -> set[str]:
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    values = [_normalize_text(claim.get("entity"))]
    component_entities = (
        details.get("component_entities")
        if isinstance(details.get("component_entities"), list)
        else []
    )
    values.extend(_normalize_text(item) for item in component_entities)
    return set().union(
        *(
            _summary_synthesis_support_tokens(value)
            for value in values
            if _normalize_text(value)
        )
    )


def _summary_specific_component_tokens(value: Any) -> set[str]:
    return (
        _summary_synthesis_support_tokens(value)
        - _SUMMARY_SYNTHESIS_COMPONENT_MATCH_NOISE_TOKENS
    )


def _claim_specific_component_tokens(claim: dict[str, Any]) -> set[str]:
    tokens = _claim_component_entity_tokens(claim)
    if not tokens:
        tokens = _summary_synthesis_support_tokens(
            " ".join(_claim_component_search_tokens(claim))
        )
    return tokens - _SUMMARY_SYNTHESIS_COMPONENT_MATCH_NOISE_TOKENS


def _summary_requires_component_entity_match(
    segment: str,
    claims: list[dict[str, Any]],
) -> bool:
    segment_tokens = _summary_specific_component_tokens(segment)
    if not segment_tokens:
        return False
    return any(
        segment_tokens & _claim_specific_component_tokens(claim) for claim in claims
    )


def _filter_summary_component_entity_matches(
    segment: str,
    matches: list[dict[str, Any]],
    *,
    candidate_claims: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates = candidate_claims if candidate_claims is not None else matches
    if not _summary_requires_component_entity_match(segment, candidates):
        return matches
    segment_tokens = _summary_specific_component_tokens(segment)
    return [
        claim
        for claim in matches
        if segment_tokens & _claim_specific_component_tokens(claim)
    ]


def _matching_summary_support_claims(
    segment: str,
    claims: list[dict[str, Any]],
    *,
    accepted_statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    segment_tokens = _summary_synthesis_support_tokens(segment)
    if not segment_tokens:
        return []

    lowered_segment = segment.casefold()
    allow_single_specific_component = "directly embodies" in lowered_segment
    statuses = accepted_statuses or {"verified", "partially_backed"}
    scored_matches: list[tuple[int, int, dict[str, Any]]] = []
    for index, claim in enumerate(claims):
        if claim.get("status") not in statuses:
            continue
        if claim.get("claim_family") not in _SUMMARY_SYNTHESIS_SUPPORT_FAMILIES:
            continue
        if claim.get("claim_family") in {"review_validation", "review_friction"}:
            if not any(
                marker in lowered_segment
                for marker in (
                    "consumer",
                    "friction",
                    "pdp",
                    "product detail",
                    "review",
                    "smooth",
                    "soft",
                    "texture",
                    "textures",
                    "validation",
                )
            ):
                continue
        claim_tokens = _summary_synthesis_support_tokens(
            " ".join(_claim_component_search_tokens(claim))
        )
        overlap = segment_tokens & claim_tokens
        entity_tokens = _claim_component_entity_tokens(claim)
        if entity_tokens:
            if not (overlap & entity_tokens):
                continue
            if len(overlap) < 2 and not allow_single_specific_component:
                continue
        elif len(overlap) < 3:
            continue
        scored_matches.append((len(overlap), -index, claim))

    scored_matches.sort(reverse=True, key=lambda item: item[:2])
    return [claim for _score, _index, claim in scored_matches[:6]]


def _summary_allows_same_slide_structural_support(segment: str) -> bool:
    lowered = segment.casefold()
    return any(
        marker in lowered
        for marker in (
            "baseline",
            "broad structural shift",
            "bundle",
            "bundles",
            "category",
            "category signal",
            "category volume",
            "category-level structural narrative",
            "conventional",
            "core architecture",
            "current winner",
            "current winning",
            "dominant layer",
            "dominant texture",
            "duplicate",
            "emerging layer",
            "familiar",
            "filter artifact",
            "format",
            "formats",
            "innovation story",
            "innovation layer",
            "market stories",
            "ongoing churn",
            "primary pillar",
            "powder anchor",
            "rank-weighted",
            "recent bundles",
            "reinforce the baseline",
            "shelf",
            "shelf success",
            "shelf visibility",
            "top-rank",
            "strongest recent",
            "structural",
            "texture",
            "textures",
            "visibility",
            "web-shelf",
            "winning architecture",
            "winning format",
            "winning proposition",
        )
    )


def _matching_same_slide_summary_support_claims(
    segment: str,
    claims: list[dict[str, Any]],
    *,
    source_slide_number: int | None,
    accepted_statuses: set[str],
) -> list[dict[str, Any]]:
    if source_slide_number is None:
        return []
    if not _summary_allows_same_slide_structural_support(segment):
        return []

    entity_candidate_claims: list[dict[str, Any]] = []
    candidate_claims: list[dict[str, Any]] = []
    segment_key = _canonical_text(segment)
    for claim in claims:
        if _int_or_none(claim.get("slide_number")) != source_slide_number:
            continue
        if claim.get("claim_family") not in _SUMMARY_SYNTHESIS_SUPPORT_FAMILIES:
            continue
        if _canonical_text(claim.get("claim_text")) == segment_key:
            continue
        entity_candidate_claims.append(claim)
        if claim.get("status") not in accepted_statuses:
            continue
        candidate_claims.append(claim)

    matches: list[dict[str, Any]] = []
    require_entity_match = _summary_requires_component_entity_match(
        segment,
        entity_candidate_claims,
    )
    segment_tokens = _summary_specific_component_tokens(segment)
    for claim in candidate_claims:
        if require_entity_match and not (
            segment_tokens & _claim_specific_component_tokens(claim)
        ):
            continue
        matches.append(claim)
    return matches[:8]


def _summary_component_claims(
    claims: list[dict[str, Any]],
    component_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for claim in claims:
        key = (
            claim.get("slide_number"),
            _normalize_text(claim.get("claim_family")),
            _normalize_text(claim.get("claim_text")),
        )
        if key in seen:
            continue
        seen.add(key)
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        component_claims.append(
            {
                "slide_number": claim.get("slide_number"),
                "status": claim.get("status"),
                "claim_text": claim.get("claim_text"),
                "claim_family": claim.get("claim_family"),
                "aggregation_rule_id": _normalize_text(
                    details.get("aggregation_rule_id")
                )
                or None,
                "component_entities": _unique_texts(
                    [_normalize_text(claim.get("entity"))]
                    + list(details.get("component_entities", []))
                ),
            }
        )
        deduped.append(claim)
    return deduped


def _validate_summary_synthesis_from_claims(
    segment: str,
    claims: list[dict[str, Any]],
    *,
    source_slide_number: int | None = None,
) -> dict[str, Any] | None:
    if not _looks_like_summary_synthesis_claim(segment):
        return None

    lowered = segment.casefold()
    reasons: list[str] = []
    missing_components: list[str] = []
    component_claims: list[dict[str, Any]] = []
    component_entities: list[str] = []
    threshold_policy = {
        "summary_components": {
            "palette_support": "top-seller bundle rows carrying the named shade territory",
            "performance_support": "top-seller bundle rows carrying the named performance overlay",
            "brand_concentration_support": "verified bundle_brand_concentration summaries",
            "review_validation_support": "verified review_validation or review_friction claims",
            "generic_structural_support": (
                "verified or partially backed deterministic component claims "
                "sharing at least two non-generic summary tokens"
            ),
        }
    }

    palette_tokens = {
        token
        for token in ("beige", "pink", "red", "brown", "nude")
        if token in _canonical_tokens(segment)
    }
    if palette_tokens:
        palette_matches = _matching_verified_claims(
            claims,
            families={"bundle_metric"},
            required_tokens=palette_tokens,
            source_file_prefix="top_seller_",
            accepted_statuses={"verified", "partially_backed"},
        )
        palette_matches = _summary_component_claims(palette_matches, component_claims)
        if not palette_matches:
            missing_components.append("palette_support")
            reasons.append(
                "shade-architecture summary lacks verified top-seller bundle support"
            )
        else:
            for claim in palette_matches:
                component_entities.extend(_emerging_lane_component_entities(claim))
                component_entities.append(_normalize_text(claim.get("entity")))

    performance_tokens = {
        token
        for token in ("long", "wear", "full", "coverage", "liquid", "applicator")
        if token in _canonical_tokens(segment)
    }
    if performance_tokens:
        performance_matches = _matching_verified_claims(
            claims,
            families={"bundle_metric"},
            required_tokens=performance_tokens,
            source_file_prefix="top_seller_",
            accepted_statuses={"verified", "partially_backed"},
        )
        performance_matches = _summary_component_claims(
            performance_matches,
            component_claims,
        )
        if not performance_matches:
            missing_components.append("performance_support")
            reasons.append(
                "performance-overlay summary lacks verified top-seller bundle support"
            )
        else:
            for claim in performance_matches:
                component_entities.extend(_emerging_lane_component_entities(claim))
                component_entities.append(_normalize_text(claim.get("entity")))

    if "brand concentration" in lowered or "survive" in lowered:
        brand_candidate_claims = [
            claim
            for claim in claims
            if claim.get("claim_family") == "bundle_brand_concentration"
        ]
        brand_matches = _matching_verified_claims(
            claims,
            families={"bundle_brand_concentration"},
            required_tokens={"concentration", "brand", "survive"},
            accepted_statuses={"verified", "partially_backed"},
        )
        brand_matches = _filter_summary_component_entity_matches(
            segment,
            brand_matches,
            candidate_claims=brand_candidate_claims,
        )
        brand_matches = _summary_component_claims(brand_matches, component_claims)
        if not brand_matches:
            missing_components.append("brand_concentration_support")
            reasons.append(
                "validation clause lacks verified brand-concentration support"
            )
        else:
            for claim in brand_matches:
                component_entities.extend(_emerging_lane_component_entities(claim))
                component_entities.append(_normalize_text(claim.get("entity")))

    if "review" in lowered or "pdp" in lowered:
        review_matches = _matching_verified_claims(
            claims,
            families={"review_validation", "review_friction"},
            required_tokens={"review", "pdp", "validated", "friction"},
            accepted_statuses={"verified", "partially_backed"},
        )
        review_matches = _summary_component_claims(review_matches, component_claims)
        if not review_matches:
            missing_components.append("review_validation_support")
            reasons.append(
                "validation clause still lacks deterministic PDP/review support"
            )
        else:
            for claim in review_matches:
                component_entities.extend(_emerging_lane_component_entities(claim))
                component_entities.append(_normalize_text(claim.get("entity")))

    has_specific_component_claims = bool(component_claims)
    generic_matches = _matching_summary_support_claims(segment, claims)
    generic_matches = _summary_component_claims(generic_matches, component_claims)
    for claim in generic_matches:
        component_entities.extend(_emerging_lane_component_entities(claim))
        component_entities.append(_normalize_text(claim.get("entity")))

    same_slide_positive_matches: list[dict[str, Any]] = []
    same_slide_contradicted_matches: list[dict[str, Any]] = []
    if not component_claims:
        same_slide_positive_matches = _matching_same_slide_summary_support_claims(
            segment,
            claims,
            source_slide_number=source_slide_number,
            accepted_statuses={"verified", "partially_backed"},
        )
        same_slide_contradicted_matches = _matching_same_slide_summary_support_claims(
            segment,
            claims,
            source_slide_number=source_slide_number,
            accepted_statuses={"contradicted"},
        )
        same_slide_matches = _summary_component_claims(
            same_slide_positive_matches + same_slide_contradicted_matches,
            component_claims,
        )
        for claim in same_slide_matches:
            component_entities.extend(_emerging_lane_component_entities(claim))
            component_entities.append(_normalize_text(claim.get("entity")))

    if not component_claims:
        return {
            "status": "warning",
            "message": "winning summary has no verified deterministic support components yet",
            "threshold_policy": threshold_policy,
            "component_claims": [],
        }

    if same_slide_contradicted_matches and not same_slide_positive_matches:
        reasons.append("same-slide deterministic support components are contradicted")
        return {
            "status": "fail",
            "component_claims": component_claims,
            "component_entities": _unique_texts(component_entities),
            "aggregation_rule_id": "winning_summary_synthesis_v1",
            "cohort_basis": "same_slide_component_claims",
            "threshold_policy": threshold_policy,
            "ranking_basis": (
                "same-slide deterministic component claims in the mapped report text"
            ),
            "missing_components": missing_components,
            "reasons": reasons,
        }

    core_missing = [
        item
        for item in missing_components
        if item in {"palette_support", "performance_support"}
    ]
    if not missing_components:
        status = (
            "partial"
            if any(
                claim.get("status") == "partially_backed" for claim in component_claims
            )
            or (generic_matches and not has_specific_component_claims)
            else "pass"
        )
    elif core_missing:
        status = "partial" if component_claims else "warning"
    elif component_claims:
        status = "partial"
    else:
        status = "fail"
    if same_slide_positive_matches:
        status = "partial" if status == "pass" else status
        if same_slide_contradicted_matches:
            reasons.append(
                "same-slide support includes contradicted deterministic components"
            )

    return {
        "status": status,
        "component_claims": component_claims,
        "component_entities": _unique_texts(component_entities),
        "aggregation_rule_id": "winning_summary_synthesis_v1",
        "cohort_basis": "top_seller_vs_other",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "verified winning-architecture bundle rows plus brand-concentration validation components"
        ),
        "missing_components": missing_components,
        "reasons": reasons,
    }


def _resolve_deck_level_report_summaries(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    package: LaunchPackageData,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue

        family = ""
        result = _validate_stability_metric_segment(claim_text, package.frames)
        if result is not None:
            family = "stability_metric"
        else:
            result = _validate_divergence_summary_segment(claim_text, package.frames)
            if result is not None:
                family = "divergence_summary"
            else:
                result = _validate_emerging_signal_summary_segment(
                    claim_text,
                    package.frames,
                )
                if result is not None:
                    family = "summary_synthesis"
                else:
                    result = _validate_current_winner_format_summary_segment(
                        claim_text,
                        package.frames,
                    )
                    if result is not None:
                        family = "summary_synthesis"
                    else:
                        result = (
                            _validate_baseline_visibility_recent_construction_segment(
                                claim_text,
                                package.frames,
                            )
                        )
                        if result is not None:
                            family = "attribute_direction"
                        else:
                            result = _validate_attribute_penetration_summary_segment(
                                claim_text,
                                package.frames,
                            )
                            if result is not None:
                                family = "summary_synthesis"
                            else:
                                result = _validate_material_composition_summary_segment(
                                    claim_text,
                                    package.frames,
                                )
                                if result is not None:
                                    family = "summary_synthesis"
                                else:
                                    result = _validate_contextual_product_brand_share_segment(
                                        claim_text,
                                        package.frames,
                                    )
                                    if result is not None:
                                        family = "bundle_brand_concentration"
                                    else:
                                        result = _validate_core_bundle_brand_promotion_summary_segment(
                                            claim_text,
                                            package.frames,
                                        )
                                        if result is not None:
                                            family = "bundle_brand_concentration"
                                        else:
                                            result = _validate_sale_pressure_bundle_concentration_summary_segment(
                                                claim_text, package.frames
                                            )
                                            if result is not None:
                                                family = "sale_pressure_exposure"
                                            else:
                                                result = _validate_pdp_descriptor_summary_segment(
                                                    claim_text,
                                                    package.frames,
                                                    updated_claims,
                                                    source_slide_number=_int_or_none(
                                                        item.get("slide_number")
                                                    ),
                                                )
                                                if result is not None:
                                                    family = "summary_synthesis"
                                                else:
                                                    result = _validate_format_constraint_summary_segment(
                                                        claim_text,
                                                        package.frames,
                                                    )
                                                    if result is not None:
                                                        family = "summary_synthesis"
                                                    else:
                                                        result = _validate_summary_synthesis_from_claims(
                                                            claim_text,
                                                            updated_claims,
                                                            source_slide_number=_int_or_none(
                                                                item.get("slide_number")
                                                            ),
                                                        )
                                                        if result is not None:
                                                            family = "summary_synthesis"

        if result is None:
            remaining_unresolved.append(item)
            continue
        if result["status"] == "warning":
            details = dict(item.get("details") or {})
            details.update(
                {
                    "message": _normalize_text(result.get("message")),
                    "threshold_policy": result.get("threshold_policy"),
                }
            )
            refreshed_item = dict(item)
            refreshed_item["claim_family"] = family
            refreshed_item["details"] = details
            remaining_unresolved.append(refreshed_item)
            continue

        claim_status = {
            "pass": "verified",
            "partial": "partially_backed",
            "fail": "contradicted",
        }[result["status"]]
        updated_claims.append(
            {
                **item,
                "status": claim_status,
                "claim_family": family,
                "details": {
                    "attribute_support": result.get("attribute_support", []),
                    "row_support": result.get("row_support", []),
                    "component_claims": result.get("component_claims", []),
                    "component_entities": result.get("component_entities", []),
                    "aggregation_rule_id": result.get("aggregation_rule_id"),
                    "cohort_basis": result.get("cohort_basis"),
                    "threshold_policy": result.get("threshold_policy"),
                    "ranking_basis": result.get("ranking_basis"),
                    "missing_components": result.get("missing_components", []),
                    "comparison_outcome": result["status"],
                    "reasons": result.get("reasons", []),
                    "summary_metrics": result.get("summary_metrics", {}),
                },
            }
        )

    return updated_claims, remaining_unresolved


def _prior_bundle_metric_context_claim(
    item: dict[str, Any],
    claims: list[dict[str, Any]],
) -> dict[str, Any] | None:
    slide_number = _int_or_none(item.get("slide_number"))
    item_unit_index = _int_or_none(item.get("unit_index"))
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for claim_index, claim in enumerate(claims):
        if claim.get("claim_family") != "bundle_metric":
            continue
        if _int_or_none(claim.get("slide_number")) != slide_number:
            continue
        if not _normalize_text(claim.get("entity")):
            continue
        claim_unit_index = _int_or_none(claim.get("unit_index"))
        if item_unit_index is not None and claim_unit_index is not None:
            distance = item_unit_index - claim_unit_index
            if distance <= 0 or distance > 4:
                continue
            candidates.append((distance, -claim_index, claim))
            continue
        candidates.append((9999, -claim_index, claim))

    if not candidates:
        return None
    candidates.sort(key=lambda item_: item_[:2])
    return candidates[0][2]


def _resolve_deck_level_contextual_brand_concentration_claims(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue
        if not _looks_like_contextual_single_brand_concentration_claim(claim_text):
            remaining_unresolved.append(item)
            continue

        matched_labels = _matched_bundle_labels(claim_text, bundle_records)
        context_claim = None
        label = matched_labels[0] if matched_labels else ""
        if not label:
            context_claim = _prior_bundle_metric_context_claim(item, updated_claims)
            label = (
                _normalize_text(context_claim.get("entity")) if context_claim else ""
            )
        if not label:
            refreshed = dict(item)
            details = dict(refreshed.get("details") or {})
            details["message"] = (
                "single-brand concentration claim has no adjacent bundle context"
            )
            refreshed["claim_family"] = "bundle_brand_concentration"
            refreshed["details"] = details
            remaining_unresolved.append(refreshed)
            continue

        result = _validate_contextual_single_brand_concentration_segment(
            claim_text,
            label=label,
            frames=package.frames,
        )
        if result is None:
            remaining_unresolved.append(item)
            continue
        if result["status"] == "warning":
            refreshed = dict(item)
            details = dict(refreshed.get("details") or {})
            details.update(
                {
                    "message": _normalize_text(result.get("message")),
                    "bundle_label": _normalize_text(result.get("bundle_label")),
                }
            )
            refreshed["claim_family"] = "bundle_brand_concentration"
            refreshed["details"] = details
            remaining_unresolved.append(refreshed)
            continue

        details = {
            "observed_values": result.get("observed_values", {}),
            "package_values": result.get("package_values", {}),
            "source_file": result.get("source_file"),
            "matched_row_keys": result.get("matched_row_keys", {}),
            "threshold_policy": result.get("threshold_policy", {}),
            "comparison_outcome": result["status"],
            "context_claim": {
                "claim_text": (
                    _normalize_text(context_claim.get("claim_text"))
                    if context_claim
                    else None
                ),
                "status": context_claim.get("status") if context_claim else None,
                "claim_family": (
                    context_claim.get("claim_family") if context_claim else None
                ),
                "entity": (
                    _normalize_text(context_claim.get("entity"))
                    if context_claim
                    else None
                ),
            },
        }
        if result.get("reasons"):
            details["reasons"] = result["reasons"]
        updated_claims.append(
            {
                **item,
                "status": (
                    "verified" if result["status"] == "pass" else "contradicted"
                ),
                "claim_family": "bundle_brand_concentration",
                "entity": label,
                "file": result.get("source_file"),
                "details": details,
            }
        )

    return updated_claims, remaining_unresolved


def _prior_bundle_label_context_from_non_claims(
    item: dict[str, Any],
    non_claims: list[dict[str, Any]],
    bundle_records: list[_BundleLabelRecord],
) -> str:
    slide_number = _int_or_none(item.get("slide_number"))
    item_unit_index = _int_or_none(item.get("unit_index"))
    if slide_number is None or item_unit_index is None:
        return ""

    candidates: list[tuple[int, int, str]] = []
    for non_claim_index, non_claim in enumerate(non_claims):
        if _int_or_none(non_claim.get("slide_number")) != slide_number:
            continue
        non_claim_unit_index = _int_or_none(non_claim.get("unit_index"))
        if non_claim_unit_index is None:
            continue
        distance = item_unit_index - non_claim_unit_index
        if distance <= 0 or distance > 2:
            continue
        labels = _matched_bundle_labels(
            _normalize_text(non_claim.get("claim_text")),
            bundle_records,
        )
        if not labels:
            continue
        candidates.append((distance, non_claim_index, labels[0]))

    if not candidates:
        return ""
    candidates.sort(key=lambda candidate: candidate[:2])
    return candidates[0][2]


def _resolve_deck_level_contextual_bundle_descriptor_claims(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    non_claims: list[dict[str, Any]],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue
        if not _looks_like_contextual_top_seller_overindex_claim(claim_text):
            remaining_unresolved.append(item)
            continue

        label = _prior_bundle_label_context_from_non_claims(
            item,
            non_claims,
            bundle_records,
        )
        if not label:
            refreshed = dict(item)
            details = dict(refreshed.get("details") or {})
            details["message"] = (
                "top-seller over-index descriptor has no adjacent bundle label context"
            )
            refreshed["claim_family"] = "bundle_metric"
            refreshed["details"] = details
            remaining_unresolved.append(refreshed)
            continue

        result = _validate_contextual_top_seller_overindex_segment(
            claim_text,
            label=label,
            frames=package.frames,
        )
        if result is None:
            remaining_unresolved.append(item)
            continue
        if result["status"] == "warning":
            refreshed = dict(item)
            details = dict(refreshed.get("details") or {})
            details.update(
                {
                    "message": _normalize_text(result.get("message")),
                    "bundle_label": _normalize_text(result.get("bundle_label")),
                }
            )
            refreshed["claim_family"] = "bundle_metric"
            refreshed["details"] = details
            remaining_unresolved.append(refreshed)
            continue

        details = {
            "observed_values": result.get("observed_values", {}),
            "package_values": result.get("package_values", {}),
            "source_file": result.get("source_file"),
            "matched_row_keys": result.get("matched_row_keys", {}),
            "threshold_policy": result.get("threshold_policy", {}),
            "comparison_outcome": result["status"],
            "aggregation_rule_id": "adjacent_bundle_top_seller_overindex_rank_v1",
        }
        if result.get("reasons"):
            details["reasons"] = result["reasons"]
        updated_claims.append(
            {
                **item,
                "status": (
                    "verified" if result["status"] == "pass" else "contradicted"
                ),
                "claim_family": "bundle_metric",
                "entity": label,
                "file": result.get("source_file"),
                "details": details,
            }
        )

    return updated_claims, remaining_unresolved


_EXHIBIT_EXAMPLE_NOISE_TOKENS = {
    "category",
    "construction",
    "example",
    "examples",
    "exhibit",
    "innovation",
    "representation",
    "signal",
    "silhouette",
    "technical",
    "tooling",
}


def _looks_like_exhibit_example_summary_claim(text: str) -> bool:
    lowered = text.casefold()
    return "high-visibility innovation examples" in lowered or (
        "these items" in lowered
        and "innovation examples" in lowered
        and "category" in lowered
    )


def _same_slide_exhibit_labels(
    item: dict[str, Any],
    non_claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    slide_number = _int_or_none(item.get("slide_number"))
    if slide_number is None:
        return []

    labels: list[dict[str, Any]] = []
    for non_claim in non_claims:
        if _int_or_none(non_claim.get("slide_number")) != slide_number:
            continue
        text = _normalize_text(non_claim.get("claim_text"))
        if not text.casefold().startswith("exhibit"):
            continue
        label = text.split(":", 1)[1] if ":" in text else text
        label = _normalize_text(label)
        if not label:
            continue
        labels.append(
            {
                "text": text,
                "label": label,
                "unit_index": _int_or_none(non_claim.get("unit_index")),
            }
        )
    return labels


def _exhibit_label_signal_tokens(label: str) -> set[str]:
    return {
        token
        for token in _summary_synthesis_support_tokens(label)
        if token not in _EXHIBIT_EXAMPLE_NOISE_TOKENS
    }


def _innovation_signal_candidate_rows(
    frames: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    differentiating_df = frames.get("differentiating_signals.csv", pl.DataFrame())
    columns, _schema = get_schema_and_column_names(differentiating_df)
    if not differentiating_df.is_empty() and "bundle_label" in columns:
        for row in differentiating_df.to_dicts():
            source_file = _normalize_text(row.get("source_file"))
            if source_file and not source_file.startswith("innovation_"):
                continue
            label = _normalize_text(row.get("bundle_label"))
            if label:
                rows.append(
                    {
                        "file": source_file or "differentiating_signals.csv",
                        "row": row,
                        "label": label,
                    }
                )
        if rows:
            return rows

    for file_name in ("innovation_pairs.csv", "innovation_triples.csv"):
        df = frames.get(file_name, pl.DataFrame())
        columns, _schema = get_schema_and_column_names(df)
        if df.is_empty() or "bundle_label" not in columns:
            continue
        for row in df.to_dicts():
            label = _normalize_text(row.get("bundle_label"))
            if label:
                rows.append({"file": file_name, "row": row, "label": label})
    return rows


def _innovation_signal_candidate_metrics(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    row = candidate["row"]
    recent_pct = _percent_from_fraction(row.get("pct_recent"))
    rest_pct = _percent_from_fraction(row.get("pct_rest"))
    delta_pct_points = (
        recent_pct - rest_pct
        if recent_pct is not None and rest_pct is not None
        else None
    )
    return {
        "count_recent": _int_or_none(row.get("count_recent")),
        "recent_brand_count": _int_or_none(row.get("recent_brand_count")),
        "pct_recent": recent_pct,
        "pct_rest": rest_pct,
        "delta_pct_points": delta_pct_points,
        "prevalence_ratio": _float_or_none(row.get("prevalence_ratio")),
        "insight_adjusted_signal_score": _float_or_none(
            row.get("insight_adjusted_signal_score")
        ),
        "rank_weighted_gross_visibility_share": _float_or_none(
            row.get("rank_weighted_gross_visibility_share")
        ),
        "rank_weighted_incremental_visibility_share": _float_or_none(
            row.get("rank_weighted_incremental_visibility_share")
        ),
    }


def _innovation_exhibit_threshold_policy() -> dict[str, Any]:
    return {
        "minimum_recent_product_count": 3,
        "minimum_recent_brand_count": 2,
        "minimum_signal_score_without_visibility": 5.0,
        "minimum_supported_exhibit_labels": 1,
        "source_files": [
            "differentiating_signals.csv",
            "innovation_pairs.csv",
            "innovation_triples.csv",
        ],
        "single_token_label_status": "partial",
    }


def _innovation_signal_candidate_passes(
    candidate: dict[str, Any],
    threshold_policy: dict[str, Any],
) -> bool:
    metrics = _innovation_signal_candidate_metrics(candidate)
    count_recent = _int_or_none(metrics.get("count_recent")) or 0
    recent_brand_count = _int_or_none(metrics.get("recent_brand_count")) or 0
    signal_score = _float_or_none(metrics.get("insight_adjusted_signal_score"))
    gross_visibility = _float_or_none(
        metrics.get("rank_weighted_gross_visibility_share")
    )
    incremental_visibility = _float_or_none(
        metrics.get("rank_weighted_incremental_visibility_share")
    )
    has_visibility = bool(gross_visibility or incremental_visibility)
    has_score = (
        signal_score is not None
        and signal_score >= threshold_policy["minimum_signal_score_without_visibility"]
    )
    return (
        count_recent >= threshold_policy["minimum_recent_product_count"]
        and recent_brand_count >= threshold_policy["minimum_recent_brand_count"]
        and (has_visibility or has_score)
    )


def _best_innovation_signal_candidate_for_exhibit(
    label: str,
    frames: dict[str, pl.DataFrame],
    threshold_policy: dict[str, Any],
) -> dict[str, Any] | None:
    label_tokens = _exhibit_label_signal_tokens(label)
    if not label_tokens:
        return None

    scored: list[tuple[float, dict[str, Any]]] = []
    for candidate in _innovation_signal_candidate_rows(frames):
        candidate_tokens = _summary_synthesis_support_tokens(candidate["label"])
        overlap = label_tokens & candidate_tokens
        if not overlap:
            continue
        metrics = _innovation_signal_candidate_metrics(candidate)
        score = (
            len(overlap) * 10_000
            + (_float_or_none(metrics.get("insight_adjusted_signal_score")) or 0.0)
            + (_float_or_none(metrics.get("delta_pct_points")) or 0.0)
            + (_int_or_none(metrics.get("count_recent")) or 0)
        )
        scored.append(
            (
                score,
                {
                    **candidate,
                    "matched_tokens": sorted(overlap),
                    "label_tokens": sorted(label_tokens),
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    for _score, candidate in scored:
        if _innovation_signal_candidate_passes(candidate, threshold_policy):
            return candidate
    return scored[0][1] if scored else None


def _validate_exhibit_example_summary_segment(
    segment: str,
    item: dict[str, Any],
    non_claims: list[dict[str, Any]],
    frames: dict[str, pl.DataFrame],
) -> dict[str, Any] | None:
    if not _looks_like_exhibit_example_summary_claim(segment):
        return None

    exhibit_labels = _same_slide_exhibit_labels(item, non_claims)
    if not exhibit_labels:
        return {
            "status": "warning",
            "message": "high-visibility example summary has no same-slide exhibit labels",
            "threshold_policy": _innovation_exhibit_threshold_policy(),
        }

    threshold_policy = _innovation_exhibit_threshold_policy()
    row_support: list[dict[str, Any]] = []
    missing_labels: list[str] = []
    broad_labels: list[str] = []
    unsupported_labels: list[str] = []
    for exhibit in exhibit_labels:
        candidate = _best_innovation_signal_candidate_for_exhibit(
            exhibit["label"],
            frames,
            threshold_policy,
        )
        if candidate is None:
            missing_labels.append(exhibit["label"])
            continue
        metrics = _innovation_signal_candidate_metrics(candidate)
        passes = _innovation_signal_candidate_passes(candidate, threshold_policy)
        if not passes:
            unsupported_labels.append(exhibit["label"])
        if len(candidate.get("matched_tokens", [])) < 2:
            broad_labels.append(exhibit["label"])
        row_support.append(
            {
                "source_file": candidate["file"],
                "exhibit_label": exhibit["label"],
                "matched_row_keys": {"bundle_label": candidate["label"]},
                "matched_tokens": candidate.get("matched_tokens", []),
                "label_tokens": candidate.get("label_tokens", []),
                "computed_values": {
                    key: (
                        round(value, 4)
                        if isinstance(value, float) and math.isfinite(value)
                        else value
                    )
                    for key, value in metrics.items()
                },
                "package_values": _bundle_candidate_package_values(candidate),
            }
        )

    supported_count = (
        len(exhibit_labels) - len(missing_labels) - len(unsupported_labels)
    )
    reasons: list[str] = []
    if missing_labels:
        reasons.append("some exhibit labels did not match innovation signal rows")
    if unsupported_labels:
        reasons.append("some exhibit labels matched rows below signal thresholds")
    if broad_labels:
        reasons.append(
            "some exhibit labels match package rows through a broad single token"
        )

    if supported_count < threshold_policy["minimum_supported_exhibit_labels"]:
        status = "warning"
    elif missing_labels or unsupported_labels or broad_labels:
        status = "partial"
    else:
        status = "pass"

    return {
        "status": status,
        "row_support": row_support,
        "component_entities": _unique_texts(
            exhibit["label"] for exhibit in exhibit_labels
        ),
        "aggregation_rule_id": "innovation_exhibit_example_support_v1",
        "cohort_basis": "same_slide_exhibit_labels_to_innovation_signal_rows",
        "threshold_policy": threshold_policy,
        "ranking_basis": (
            "same-slide exhibit labels matched to innovation signal rows with "
            "minimum recent product count, brand count, and either visibility "
            "or insight-adjusted signal score support"
        ),
        "missing_components": missing_labels + unsupported_labels,
        "reasons": reasons,
    }


def _resolve_deck_level_exhibit_example_summaries(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    non_claims: list[dict[str, Any]],
    package: LaunchPackageData,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue
        result = _validate_exhibit_example_summary_segment(
            claim_text,
            item,
            non_claims,
            package.frames,
        )
        if result is None:
            remaining_unresolved.append(item)
            continue
        if result["status"] == "warning":
            refreshed = dict(item)
            refreshed["claim_family"] = "summary_synthesis"
            details = dict(refreshed.get("details") or {})
            details.update(
                {
                    "message": _normalize_text(result.get("message")),
                    "threshold_policy": result.get("threshold_policy", {}),
                }
            )
            refreshed["details"] = details
            remaining_unresolved.append(refreshed)
            continue

        updated_claims.append(
            {
                **item,
                "status": (
                    "verified" if result["status"] == "pass" else "partially_backed"
                ),
                "claim_family": "summary_synthesis",
                "entity": "; ".join(result.get("component_entities", [])),
                "details": {
                    "row_support": result.get("row_support", []),
                    "component_entities": result.get("component_entities", []),
                    "aggregation_rule_id": result.get("aggregation_rule_id"),
                    "cohort_basis": result.get("cohort_basis"),
                    "threshold_policy": result.get("threshold_policy", {}),
                    "ranking_basis": result.get("ranking_basis"),
                    "missing_components": result.get("missing_components", []),
                    "comparison_outcome": result["status"],
                    "reasons": result.get("reasons", []),
                },
            }
        )

    return updated_claims, remaining_unresolved


def _looks_like_numeric_signal_reference_claim(text: str) -> bool:
    if not _percent_mentions(text):
        return False
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "aligns exactly",
            "aligns with",
            "credible bridge",
            "current winners",
            "emerging releases",
            "recent-product signal",
            "recent product signal",
            "top-seller lane",
            "validates the",
            "visually validates",
        )
    )


def _numeric_reference_matched_mentions(
    reference_mentions: list[_PercentMention],
    claim: dict[str, Any],
) -> list[dict[str, Any]]:
    claim_mentions = _percent_mentions(_normalize_text(claim.get("claim_text")))
    matches: list[dict[str, Any]] = []
    used_claim_indexes: set[int] = set()
    for reference in reference_mentions:
        for claim_index, claim_mention in enumerate(claim_mentions):
            if claim_index in used_claim_indexes:
                continue
            if not _percent_matches(reference, claim_mention.value):
                continue
            used_claim_indexes.add(claim_index)
            matches.append(
                {
                    "reference_value": reference.value,
                    "support_value": claim_mention.value,
                    "reference_role": reference.role,
                    "support_role": claim_mention.role,
                }
            )
            break
    return matches


def _numeric_reference_support_candidates(
    segment: str,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reference_mentions = _percent_mentions(segment)
    if not reference_mentions:
        return []

    segment_tokens = _summary_synthesis_support_tokens(segment)
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for claim_index, claim in enumerate(claims):
        if claim.get("claim_family") not in _SUMMARY_SYNTHESIS_SUPPORT_FAMILIES:
            continue
        claim_status = _normalize_text(claim.get("status"))
        if claim_status not in {"verified", "partially_backed", "contradicted"}:
            continue
        matched_mentions = _numeric_reference_matched_mentions(
            reference_mentions,
            claim,
        )
        if not matched_mentions:
            continue
        claim_tokens = _claim_component_search_tokens(claim)
        token_overlap = segment_tokens & claim_tokens
        if len(reference_mentions) == 1 and not token_overlap:
            continue
        if len(reference_mentions) > 1 and len(matched_mentions) < 2:
            continue
        support = {
            "claim": claim,
            "matched_mentions": matched_mentions,
            "token_overlap": sorted(token_overlap),
        }
        score = len(matched_mentions) * 100 + len(token_overlap)
        candidates.append((score, -claim_index, support))

    candidates.sort(key=lambda item: item[:2], reverse=True)
    selected: list[dict[str, Any]] = []
    covered_reference_values: set[float] = set()
    for _score, _claim_index, support in candidates:
        support_values = {
            round(_float_or_none(match.get("reference_value")) or 0.0, 3)
            for match in support["matched_mentions"]
        }
        if support_values and support_values <= covered_reference_values:
            continue
        selected.append(support)
        covered_reference_values.update(support_values)
        if len(covered_reference_values) >= len(reference_mentions):
            break
    return selected


def _numeric_reference_support_effective_status(claim: dict[str, Any]) -> str:
    status = _normalize_text(claim.get("status"))
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    reasons = details.get("reasons") if isinstance(details.get("reasons"), list) else []
    if status == "contradicted":
        return "contradicted"
    if any("percent mismatch" in _normalize_text(reason) for reason in reasons):
        return "contradicted"
    if status == "partially_backed":
        return "partially_backed"
    return "verified" if status == "verified" else status


def _numeric_reference_claim_family(
    claim_text: str,
    supports: list[dict[str, Any]],
    original_family: str,
) -> str:
    lowered = claim_text.casefold()
    if (
        "bridge" in lowered
        or "current winners" in lowered
        or "emerging releases" in lowered
    ):
        return "summary_synthesis"
    support_families = _unique_texts(
        _normalize_text(support["claim"].get("claim_family"))
        for support in supports
        if _normalize_text(support["claim"].get("claim_family"))
    )
    if len(support_families) == 1:
        return support_families[0]
    if original_family and original_family not in {"unclassified", "unknown"}:
        return original_family
    return "summary_synthesis"


def _numeric_reference_details(
    supports: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    support_claims: list[dict[str, Any]] = []
    effective_statuses: list[str] = []
    for support in supports:
        claim = support["claim"]
        effective_status = _numeric_reference_support_effective_status(claim)
        effective_statuses.append(effective_status)
        support_claims.append(
            {
                "claim_text": _normalize_text(claim.get("claim_text")),
                "status": claim.get("status"),
                "effective_status": effective_status,
                "claim_family": claim.get("claim_family"),
                "entity": _normalize_text(claim.get("entity")),
                "slide_number": _int_or_none(claim.get("slide_number")),
                "matched_percent_values": support["matched_mentions"],
                "token_overlap": support.get("token_overlap", []),
            }
        )

    reasons: list[str] = []
    if "contradicted" in effective_statuses:
        reasons.append("referenced deterministic numeric support is contradicted")
    elif "partially_backed" in effective_statuses:
        reasons.append("referenced deterministic numeric support is only partial")

    return {
        "support_claims": support_claims,
        "aggregation_rule_id": "deck_numeric_signal_reference_v1",
        "comparison_outcome": (
            "fail"
            if status == "contradicted"
            else "partial" if status == "partially_backed" else "pass"
        ),
        "threshold_policy": {
            "reference_rule": (
                "numeric signal references inherit the strictest deterministic "
                "outcome of previously parsed package-backed claims sharing the "
                "same displayed percent values"
            )
        },
        "reasons": reasons,
    }


def _resolve_deck_level_numeric_signal_references(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    processed_keys: set[tuple[int | None, int | None, str]] = set()
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        key = (
            _int_or_none(item.get("slide_number")),
            _int_or_none(item.get("unit_index")),
            _canonical_text(claim_text),
        )
        if key in processed_keys:
            continue
        if not claim_text or not _looks_like_numeric_signal_reference_claim(claim_text):
            remaining_unresolved.append(item)
            continue

        supports = _numeric_reference_support_candidates(claim_text, updated_claims)
        if not supports:
            remaining_unresolved.append(item)
            continue

        processed_keys.add(key)
        effective_statuses = [
            _numeric_reference_support_effective_status(support["claim"])
            for support in supports
        ]
        if "contradicted" in effective_statuses:
            status = "contradicted"
        elif "partially_backed" in effective_statuses:
            status = "partially_backed"
        else:
            status = "verified"

        entities = _unique_texts(
            _normalize_text(support["claim"].get("entity"))
            for support in supports
            if _normalize_text(support["claim"].get("entity"))
        )
        original_family = _normalize_text(item.get("claim_family"))
        updated_claims.append(
            {
                **item,
                "status": status,
                "claim_family": _numeric_reference_claim_family(
                    claim_text,
                    supports,
                    original_family,
                ),
                "entity": "; ".join(entities),
                "details": _numeric_reference_details(supports, status),
            }
        )

    return updated_claims, remaining_unresolved


def _resolve_deck_level_product_claims(
    claims: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    non_claims: list[dict[str, Any]],
    package: LaunchPackageData,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not unresolved:
        return claims, unresolved

    remaining_unresolved: list[dict[str, Any]] = []
    updated_claims = list(claims)
    for item in unresolved:
        claim_text = _normalize_text(item.get("claim_text"))
        if not claim_text:
            remaining_unresolved.append(item)
            continue

        result = None
        family = ""
        product_name = _best_product_name_from_text(claim_text, package.product_names)
        if product_name is None:
            product_name = _slide_product_anchor(
                updated_claims,
                _int_or_none(item.get("slide_number")),
            )
        if product_name is None:
            product_name = _prior_product_anchor_from_non_claims(
                item,
                non_claims,
                package,
            )

        if product_name is not None:
            result = _validate_product_review_segment(
                claim_text,
                product_name=product_name,
                package=package,
            )
            if result is not None:
                family = (
                    "review_friction"
                    if _requested_product_review_topics(
                        claim_text,
                        _PRODUCT_REVIEW_NEGATIVE_TOPIC_KEYWORDS,
                    )
                    and not _requested_product_review_topics(
                        claim_text,
                        _PRODUCT_REVIEW_POSITIVE_TOPIC_KEYWORDS,
                    )
                    else "review_validation"
                )

        if result is None and _looks_like_product_attribute_claim(claim_text):
            product_name = _best_product_name_from_text(
                claim_text, package.product_names
            )
            if product_name is None:
                product_name = _slide_product_anchor(
                    updated_claims,
                    _int_or_none(item.get("slide_number")),
                )
            if product_name is None:
                product_name = _prior_product_anchor_from_non_claims(
                    item,
                    non_claims,
                    package,
                )
            if product_name is not None:
                result = _validate_product_attribute_segment(
                    claim_text,
                    product_name=product_name,
                    package=package,
                )
                if result is not None:
                    family = "product_attribute"

        if result is None:
            remaining_unresolved.append(item)
            continue

        if result["status"] == "warning":
            refreshed = dict(item)
            refreshed["claim_family"] = family or "product_attribute"
            refreshed["details"] = {
                "message": _normalize_text(result.get("message")),
                "normalized_product_name": result.get("normalized_product_name"),
            }
            remaining_unresolved.append(refreshed)
            continue

        updated_claims.append(
            {
                **item,
                "status": (
                    "verified"
                    if result["status"] == "pass"
                    else (
                        "partially_backed"
                        if result["status"] == "partial"
                        else "contradicted"
                    )
                ),
                "claim_family": family or "product_attribute",
                "entity": result.get("normalized_product_name"),
                "details": {
                    "normalized_product_name": result.get("normalized_product_name"),
                    "product_id": result.get("product_id"),
                    "price_tier": result.get("price_tier"),
                    "matched_attribute_flags": result.get(
                        "matched_attribute_flags",
                        [],
                    ),
                    "source_row_ids": result.get("source_row_ids", []),
                    "attribute_support": result.get("attribute_support", []),
                    "aggregation_rule_id": result.get("aggregation_rule_id"),
                    "row_support": result.get("row_support", []),
                    "component_entities": result.get("component_entities", []),
                    "cohort_basis": result.get("cohort_basis"),
                    "threshold_policy": result.get("threshold_policy", {}),
                    "ranking_basis": result.get("ranking_basis"),
                    "comparison_outcome": result["status"],
                    "reasons": result.get("reasons", []),
                },
            }
        )

    return updated_claims, remaining_unresolved


def _table_model_confidence(table_model: dict[str, Any] | None) -> float | None:
    if not isinstance(table_model, dict):
        return None
    return _float_or_none(table_model.get("confidence"))


def _count_numeric_tokens(text: str) -> int:
    return len(re.findall(r"\b\d[\d,]*(?:\.\d+)?(?:%|x)?\b", _normalize_text(text)))


def _assess_slide_reading(slide: dict[str, Any]) -> dict[str, Any]:
    units = _iter_slide_units(slide)
    ocr_text = _normalize_text(slide.get("ocr_text"))
    if not ocr_text and units:
        ocr_text = _normalize_text(
            " ".join(_normalize_text(unit.get("text")) for unit in units)
        )
    blocks = slide.get("blocks") if isinstance(slide.get("blocks"), list) else []
    figure_regions = (
        slide.get("figure_regions")
        if isinstance(slide.get("figure_regions"), list)
        else []
    )
    suspicious_block_count = 0
    low_confidence_block_count = 0
    uncertain_visual_block_count = 0
    low_table_confidence_count = 0
    table_block_count = 0

    for block in blocks:
        if not isinstance(block, dict):
            continue
        if _normalize_text(block.get("audit_status")).casefold() == "suspicious":
            suspicious_block_count += 1
        confidence = _float_or_none(block.get("confidence"))
        if confidence is not None and confidence < _READING_BLOCK_CONFIDENCE_WARNING:
            low_confidence_block_count += 1
        visual_status = _normalize_text(block.get("visual_status")).casefold()
        visual_confidence = _float_or_none(block.get("visual_confidence"))
        if visual_status == "uncertain":
            uncertain_visual_block_count += 1
        elif (
            visual_status == "corrected"
            and visual_confidence is not None
            and visual_confidence < _READING_VISUAL_CONFIDENCE_WARNING
        ):
            uncertain_visual_block_count += 1
        table_model = block.get("table_model")
        if isinstance(table_model, dict):
            table_block_count += 1
            table_confidence = _table_model_confidence(table_model)
            if (
                table_confidence is not None
                and table_confidence < _READING_TABLE_CONFIDENCE_WARNING
            ):
                low_table_confidence_count += 1

    unit_count = len(units)
    text_length = len(ocr_text)
    numeric_token_count = _count_numeric_tokens(ocr_text)
    reasons: list[str] = []
    status = "read_ok"

    if text_length == 0 and unit_count == 0:
        status = "read_poor"
        reasons.append("no readable text was extracted from the slide")
    elif (
        text_length < _READING_SPARSE_TEXT_LIMIT
        and unit_count <= 1
        and (len(blocks) >= 2 or len(figure_regions) >= 1 or table_block_count >= 1)
    ):
        status = "read_warning"
        reasons.append("slide yielded unusually little readable text for its structure")

    if suspicious_block_count:
        status = "read_warning" if status == "read_ok" else status
        reasons.append(
            f"{suspicious_block_count} block(s) were flagged suspicious by OCR audit"
        )
    if low_confidence_block_count:
        status = "read_warning" if status == "read_ok" else status
        reasons.append(f"{low_confidence_block_count} block(s) had low OCR confidence")
    if uncertain_visual_block_count:
        status = "read_warning" if status == "read_ok" else status
        reasons.append(
            f"{uncertain_visual_block_count} block(s) had uncertain visual correction"
        )
    if low_table_confidence_count:
        status = "read_warning" if status == "read_ok" else status
        reasons.append(
            f"{low_table_confidence_count} table block(s) had low table confidence"
        )
    if (
        len(figure_regions) > 0
        and numeric_token_count == 0
        and text_length < _READING_SPARSE_TEXT_LIMIT
    ):
        status = "read_warning" if status == "read_ok" else status
        reasons.append(
            "figure-heavy slide yielded little readable text or numeric evidence"
        )

    return {
        "slide_number": slide.get("slide_number"),
        "slide_id": slide.get("slide_id"),
        "status": status,
        "unit_count": unit_count,
        "text_length": text_length,
        "numeric_token_count": numeric_token_count,
        "block_count": len(blocks),
        "figure_region_count": len(figure_regions),
        "table_block_count": table_block_count,
        "suspicious_block_count": suspicious_block_count,
        "low_confidence_block_count": low_confidence_block_count,
        "uncertain_visual_block_count": uncertain_visual_block_count,
        "low_table_confidence_count": low_table_confidence_count,
        "reasons": reasons,
    }


def _assess_reading_quality(reading_payload: dict[str, Any]) -> dict[str, Any]:
    slides = (
        reading_payload.get("slides")
        if isinstance(reading_payload.get("slides"), list)
        else []
    )
    if not slides:
        return {
            "status": "read_poor",
            "summary": {
                "slide_count": 0,
                "ok_slide_count": 0,
                "warning_slide_count": 0,
                "poor_slide_count": 0,
            },
            "reasons": ["reading payload did not contain any slides"],
            "flagged_slides": [],
        }

    slide_assessments = [
        _assess_slide_reading(slide) for slide in slides if isinstance(slide, dict)
    ]
    poor_slides = [
        assessment
        for assessment in slide_assessments
        if assessment["status"] == "read_poor"
    ]
    warning_slides = [
        assessment
        for assessment in slide_assessments
        if assessment["status"] == "read_warning"
    ]
    ok_slide_count = sum(
        1 for assessment in slide_assessments if assessment["status"] == "read_ok"
    )

    reasons: list[str] = []
    status = "read_ok"
    poor_threshold = max(
        1, (len(slide_assessments) + 4) // _READING_POOR_SLIDE_RATIO_DIVISOR
    )
    if len(poor_slides) >= poor_threshold:
        status = "read_poor"
        reasons.append(
            f"{len(poor_slides)} of {len(slide_assessments)} slides had poor extraction"
        )
    elif poor_slides or warning_slides:
        status = "read_warning"

    if warning_slides:
        reasons.append(f"{len(warning_slides)} slide(s) showed reading warning signals")
    completeness = (
        reading_payload.get("reading_completeness")
        if isinstance(reading_payload.get("reading_completeness"), dict)
        else None
    )
    completeness_status = _normalize_text(
        completeness.get("status") if completeness else ""
    )
    if completeness_status == "read_poor":
        status = "read_poor"
        reasons.append("reading completeness audit found substantial stage gaps")
    elif completeness_status in {"read_warning", "not_available"}:
        status = "read_warning" if status == "read_ok" else status
        if completeness_status == "not_available":
            reasons.append("reading completeness audit could not run")
        else:
            reasons.append("reading completeness audit found stage-to-stage gaps")
    if not reasons:
        reasons.append("no deterministic reading-quality issues were detected")

    payload = {
        "status": status,
        "summary": {
            "slide_count": len(slide_assessments),
            "ok_slide_count": ok_slide_count,
            "warning_slide_count": len(warning_slides),
            "poor_slide_count": len(poor_slides),
        },
        "reasons": reasons,
        "flagged_slides": [
            assessment
            for assessment in slide_assessments
            if assessment["status"] != "read_ok"
        ],
    }
    if completeness is not None:
        payload["completeness"] = completeness
        completeness_summary = (
            completeness.get("summary")
            if isinstance(completeness.get("summary"), dict)
            else {}
        )
        payload["summary"]["completeness_status"] = completeness_status
        payload["summary"]["completeness_flagged_slide_count"] = (
            _int_or_none(completeness_summary.get("flagged_slide_count")) or 0
        )
        payload["summary"]["missing_ocr_line_count"] = (
            _int_or_none(completeness_summary.get("missing_ocr_line_count")) or 0
        )
    return payload


def _claim_result(
    *,
    status: str,
    claim_family: str,
    claim_text: str,
    slide: dict[str, Any],
    unit: dict[str, Any],
    entity: str | None = None,
    file_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "claim_family": claim_family,
        "claim_text": claim_text,
        "slide_id": slide.get("slide_id"),
        "slide_number": slide.get("slide_number"),
        "page_number": slide.get("page_number"),
        "source_kind": unit.get("source_kind"),
        "block_id": unit.get("block_id"),
        "block_type": unit.get("block_type"),
    }
    unit_index = _int_or_none(unit.get("unit_index"))
    if unit_index is not None:
        payload["unit_index"] = unit_index
    context_text = _normalize_text(unit.get("context_text"))
    if context_text:
        payload["context_text"] = context_text
    if entity:
        payload["entity"] = entity
    if file_name:
        payload["file"] = file_name
    if details:
        payload["details"] = details
    return payload


def _image_region_result(slide: dict[str, Any], region_index: int) -> dict[str, Any]:
    return {
        "status": "image_region",
        "claim_family": "figure_region",
        "claim_text": "Image region",
        "slide_id": slide.get("slide_id"),
        "slide_number": slide.get("slide_number"),
        "page_number": slide.get("page_number"),
        "source_kind": "figure_region",
        "region_index": region_index,
        "details": {"message": "image region preserved without OCR interpretation"},
    }


def _dedupe_repeated_context_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    tokens = text.split()
    if len(tokens) % 2 != 0:
        return text
    midpoint = len(tokens) // 2
    if tokens[:midpoint] == tokens[midpoint:]:
        return " ".join(tokens[:midpoint])
    return text


def _details_reasons(details: dict[str, Any]) -> list[str]:
    return [
        _normalize_text(reason)
        for reason in (
            details.get("reasons") if isinstance(details.get("reasons"), list) else []
        )
        if _normalize_text(reason)
    ]


def _reason_is_source_mapping_or_missing_evidence(reason: str) -> bool:
    lowered = reason.casefold()
    return any(
        marker in lowered
        for marker in (
            "cohort label mismatch",
            "source row supports",
            "candidate is missing",
            "percent unavailable",
            "comparable percent values",
            "source row is missing",
        )
    )


def _contradiction_has_supported_evidence(result: dict[str, Any]) -> bool:
    if result.get("status") != "contradicted":
        return True
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    reasons = _details_reasons(details)
    if not reasons:
        return False
    if all(_reason_is_source_mapping_or_missing_evidence(reason) for reason in reasons):
        return False
    evidence_keys = (
        "package_values",
        "matched_row_keys",
        "row_support",
        "source_row_ids",
        "expected",
        "expected_values",
        "expected_candidates",
        "zero_occurrence_check",
    )
    return any(bool(details.get(key)) for key in evidence_keys)


def _downgrade_unsupported_contradictions(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    downgraded_results: list[dict[str, Any]] = []
    for result in results:
        if _contradiction_has_supported_evidence(result):
            downgraded_results.append(result)
            continue
        downgraded = dict(result)
        details = (
            dict(result.get("details"))
            if isinstance(result.get("details"), dict)
            else {}
        )
        details["downgraded_from"] = "contradicted"
        details["message"] = (
            "deterministic source routing did not produce a concrete package-row "
            "contradiction"
        )
        downgraded["status"] = "unresolved"
        downgraded["details"] = details
        downgraded_results.append(downgraded)
    return downgraded_results


def _evaluate_unit(
    *,
    slide: dict[str, Any],
    unit: dict[str, Any],
    package: LaunchPackageData,
    bundle_records: list[_BundleLabelRecord],
) -> tuple[list[dict[str, Any]], bool]:
    text = _normalize_text(unit.get("text"))
    if not text:
        return [], False

    mapping_issue = _classify_mapping_issue_unit(text, unit)
    if mapping_issue is not None:
        return [
            _claim_result(
                status="ocr_layout_mapping_issue",
                claim_family="ocr_layout_mapping_issue",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={
                    **mapping_issue,
                    "affected_block_id": unit.get("block_id"),
                    "suppressed_text": text,
                },
            )
        ], True

    non_claim = _classify_non_claim_unit(text, unit)
    if non_claim is not None:
        return [
            _claim_result(
                status="non_claim",
                claim_family="filter_non_claim",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={
                    **non_claim,
                    "source_kind": unit.get("source_kind"),
                    "block_type": unit.get("block_type"),
                },
            )
        ], True

    results: list[dict[str, Any]] = []
    recognized = False
    brand_df = package.frames["top_seller_brand_comparison.csv"]
    context_text = _dedupe_repeated_context_text(unit.get("context_text"))
    contextual_text = _normalize_text(
        f"{context_text} {text}" if context_text else text
    )

    cohort_count_result = _validate_cohort_count_segment(text, package.frames)
    if cohort_count_result is not None:
        recognized = True
        results.append(
            _claim_result(
                status=(
                    "verified"
                    if cohort_count_result["status"] == "pass"
                    else "contradicted"
                ),
                claim_family="cohort_count",
                claim_text=text,
                slide=slide,
                unit=unit,
                entity="product_cohort_counts",
                details=_cohort_count_evidence_details(cohort_count_result),
            )
        )

    cohort_overlap_result = _validate_cohort_overlap_segment(text, package.frames)
    if cohort_overlap_result is not None:
        recognized = True
        overlap_status = cohort_overlap_result["status"]
        results.append(
            _claim_result(
                status=(
                    "unresolved"
                    if overlap_status == "warning"
                    else "verified" if overlap_status == "pass" else "contradicted"
                ),
                claim_family="cohort_overlap",
                claim_text=text,
                slide=slide,
                unit=unit,
                entity="recent_top_seller_overlap",
                file_name="recent_products.csv+top_seller_products.csv",
                details=_cohort_overlap_evidence_details(cohort_overlap_result),
            )
        )

    ranked_overlap_result = _validate_ranked_recent_top_seller_overlap_segment(
        text,
        package.frames,
    )
    if ranked_overlap_result is not None:
        recognized = True
        ranked_overlap_status = ranked_overlap_result["status"]
        results.append(
            _claim_result(
                status=(
                    "unresolved"
                    if ranked_overlap_status == "warning"
                    else (
                        "verified"
                        if ranked_overlap_status == "pass"
                        else "contradicted"
                    )
                ),
                claim_family="cohort_overlap",
                claim_text=text,
                slide=slide,
                unit=unit,
                entity="ranked_recent_top_seller_overlap",
                file_name="product_filter_matrix.csv",
                details=_cohort_overlap_evidence_details(ranked_overlap_result),
            )
        )

    ranked_bundle_result = _validate_ranked_bundle_product_evidence_segment(
        text,
        package.frames,
    )
    if ranked_bundle_result is not None:
        recognized = True
        ranked_bundle_status = ranked_bundle_result["status"]
        results.append(
            _claim_result(
                status=(
                    "unresolved"
                    if ranked_bundle_status == "warning"
                    else (
                        "verified" if ranked_bundle_status == "pass" else "contradicted"
                    )
                ),
                claim_family="ranked_bundle_product_evidence",
                claim_text=text,
                slide=slide,
                unit=unit,
                entity=_normalize_text(ranked_bundle_result.get("bundle_label")),
                file_name=ranked_bundle_result.get("source_file"),
                details={
                    "observed_values": {
                        "claimed_ranks": ranked_bundle_result.get("expected_ranks", []),
                        "claimed_bundle_label": ranked_bundle_result.get(
                            "bundle_label"
                        ),
                    },
                    "package_values": {
                        "support_rows": ranked_bundle_result.get("support_rows", []),
                    },
                    "matched_row_keys": {
                        "bundle_label": ranked_bundle_result.get("bundle_label"),
                        "ranked_products": ranked_bundle_result.get(
                            "expected_ranks", []
                        ),
                    },
                    "tolerance_policy": (
                        "each claimed rank must exist in top_seller_products.csv "
                        "and carry all named bundle-label tokens"
                    ),
                    "reasons": ranked_bundle_result.get("reasons", []),
                    "message": _normalize_text(ranked_bundle_result.get("message")),
                },
            )
        )

    product_rank_results = (
        []
        if ranked_bundle_result is not None
        else _validate_product_rank_segment(text, package.frames)
    )
    if product_rank_results:
        recognized = True
        for item in product_rank_results:
            if item["status"] == "pass":
                results.append(
                    _claim_result(
                        status="verified",
                        claim_family="product_rank",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(item.get("product_name")),
                        file_name=item.get("file"),
                        details={
                            "observed_values": {
                                "claimed_rank": item.get("observed_rank"),
                                "claimed_bucket": item.get("observed_bucket"),
                            },
                            "package_values": item.get("package_values"),
                            "source_file": item.get("file"),
                            "matched_row_keys": {
                                "product_name": item.get("product_name")
                            },
                            "tolerance_policy": (
                                "exact rank match; Pareto bucket match when claimed"
                            ),
                        },
                    )
                )
            elif item["status"] == "fail":
                results.append(
                    _claim_result(
                        status="contradicted",
                        claim_family="product_rank",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(item.get("product_name")),
                        file_name=item.get("file"),
                        details={
                            "reasons": item.get("reasons", []),
                            "observed_values": {
                                "claimed_rank": item.get("observed_rank"),
                                "claimed_bucket": item.get("observed_bucket"),
                            },
                            "package_values": item.get("package_values"),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="product_rank",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(item.get("product_name")),
                        details={"message": _normalize_text(item.get("message"))},
                    )
                )

    product_exemplar_result = _validate_product_exemplar_segment(text, package)
    if product_exemplar_result is not None:
        recognized = True
        exemplar_status = product_exemplar_result["status"]
        if exemplar_status == "warning":
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="product_exemplar",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(
                        product_exemplar_result.get("normalized_product_name")
                    ),
                    details={
                        "message": _normalize_text(
                            product_exemplar_result.get("message")
                        ),
                    },
                )
            )
        else:
            results.append(
                _claim_result(
                    status="verified" if exemplar_status == "pass" else "contradicted",
                    claim_family="product_exemplar",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(
                        product_exemplar_result.get("normalized_product_name")
                    ),
                    file_name=_normalize_text(
                        product_exemplar_result.get("source_file")
                    )
                    or None,
                    details={
                        "normalized_product_name": product_exemplar_result.get(
                            "normalized_product_name"
                        ),
                        "product_id": product_exemplar_result.get("product_id"),
                        "rank_value": product_exemplar_result.get("rank_value"),
                        "cohort_membership": product_exemplar_result.get(
                            "cohort_membership"
                        ),
                        "price_tier": product_exemplar_result.get("price_tier"),
                        "matched_attribute_flags": product_exemplar_result.get(
                            "matched_attribute_flags",
                            [],
                        ),
                        "source_row_ids": product_exemplar_result.get(
                            "source_row_ids",
                            [],
                        ),
                        "attribute_support": product_exemplar_result.get(
                            "attribute_support",
                            [],
                        ),
                        "aggregation_rule_id": product_exemplar_result.get(
                            "aggregation_rule_id"
                        ),
                        "comparison_outcome": exemplar_status,
                        "reasons": product_exemplar_result.get("reasons", []),
                    },
                )
            )

    product_tier_span_result = _validate_product_tier_span_segment(text, package.frames)
    if product_tier_span_result is not None:
        recognized = True
        tier_status = product_tier_span_result["status"]
        if tier_status == "warning":
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="product_tier_span",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    details={
                        "message": _normalize_text(
                            product_tier_span_result.get("message")
                        ),
                    },
                )
            )
        else:
            results.append(
                _claim_result(
                    status="verified" if tier_status == "pass" else "contradicted",
                    claim_family="product_tier_span",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity="pricing_tier_span",
                    details={
                        "row_support": product_tier_span_result.get(
                            "row_support",
                            [],
                        ),
                        "price_tiers": product_tier_span_result.get("price_tiers", []),
                        "aggregation_rule_id": product_tier_span_result.get(
                            "aggregation_rule_id"
                        ),
                        "cohort_basis": product_tier_span_result.get("cohort_basis"),
                        "comparison_outcome": tier_status,
                        "reasons": product_tier_span_result.get("reasons", []),
                    },
                )
            )

    low_count_novelty_result = _validate_low_count_novelty_segment(
        text,
        package.frames,
    )
    if low_count_novelty_result is not None:
        recognized = True
        novelty_status = low_count_novelty_result["status"]
        if novelty_status == "warning":
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="low_count_novelty",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    details={
                        "message": _normalize_text(
                            low_count_novelty_result.get("message")
                        ),
                        "threshold_policy": low_count_novelty_result.get(
                            "threshold_policy",
                            {},
                        ),
                    },
                )
            )
        else:
            results.append(
                _claim_result(
                    status=(
                        "verified"
                        if novelty_status == "pass"
                        else (
                            "partially_backed"
                            if novelty_status == "partial"
                            else "contradicted"
                        )
                    ),
                    claim_family="low_count_novelty",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=", ".join(
                        low_count_novelty_result.get("component_entities", [])
                    ),
                    details={
                        "row_support": low_count_novelty_result.get(
                            "row_support",
                            [],
                        ),
                        "component_entities": low_count_novelty_result.get(
                            "component_entities",
                            [],
                        ),
                        "aggregation_rule_id": low_count_novelty_result.get(
                            "aggregation_rule_id"
                        ),
                        "cohort_basis": low_count_novelty_result.get("cohort_basis"),
                        "threshold_policy": low_count_novelty_result.get(
                            "threshold_policy",
                            {},
                        ),
                        "ranking_basis": low_count_novelty_result.get("ranking_basis"),
                        "missing_components": low_count_novelty_result.get(
                            "missing_components",
                            [],
                        ),
                        "comparison_outcome": novelty_status,
                        "reasons": low_count_novelty_result.get("reasons", []),
                    },
                )
            )

    entry_price_result = _validate_entry_price_comparison_segment(text, package.frames)
    if entry_price_result is not None:
        recognized = True
        price_status = entry_price_result["status"]
        results.append(
            _claim_result(
                status=(
                    "unresolved"
                    if price_status == "warning"
                    else "verified" if price_status == "pass" else "contradicted"
                ),
                claim_family="entry_price_comparison",
                claim_text=text,
                slide=slide,
                unit=unit,
                entity="entry_price",
                file_name=entry_price_result.get("source_file"),
                details=_entry_price_details(entry_price_result),
            )
        )

    sale_pressure_results = _validate_sale_pressure_segment(
        text,
        package.frames,
        bundle_records,
    )
    sale_pressure_routed = sale_pressure_results is not None
    if sale_pressure_results is not None:
        recognized = True
        for sale_pressure_result in sale_pressure_results:
            sale_pressure_status = sale_pressure_result["status"]
            sale_pressure_entity = (
                _normalize_text(
                    sale_pressure_result.get("package_values", {}).get("bundle_label")
                )
                or _normalize_text(sale_pressure_result.get("label"))
                or "sale_pressure_exposure"
            )
            results.append(
                _claim_result(
                    status=(
                        "unresolved"
                        if sale_pressure_status == "warning"
                        else (
                            "verified"
                            if sale_pressure_status == "pass"
                            else "contradicted"
                        )
                    ),
                    claim_family="sale_pressure_exposure",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=sale_pressure_entity,
                    file_name=sale_pressure_result.get("source_file"),
                    details=_sale_pressure_details(sale_pressure_result),
                )
            )

    visibility_segment = (
        contextual_text
        if context_text and _STANDALONE_VISIBILITY_METRIC_RE.match(text)
        else text
    )
    rank_weighted_visibility_result = _validate_rank_weighted_visibility_segment(
        visibility_segment,
        package.frames,
    )
    rank_weighted_visibility_routed = rank_weighted_visibility_result is not None
    if rank_weighted_visibility_result is not None:
        recognized = True
        visibility_status = rank_weighted_visibility_result["status"]
        visibility_entity = (
            _normalize_text(
                rank_weighted_visibility_result.get("package_values", {}).get(
                    "bundle_key"
                )
            )
            or "rank_weighted_visibility"
        )
        if visibility_status == "warning":
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="rank_weighted_visibility",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=visibility_entity,
                    file_name=rank_weighted_visibility_result.get("source_file"),
                    details=_rank_weighted_visibility_details(
                        rank_weighted_visibility_result
                    ),
                )
            )
        else:
            results.append(
                _claim_result(
                    status=(
                        "verified" if visibility_status == "pass" else "contradicted"
                    ),
                    claim_family="rank_weighted_visibility",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=visibility_entity,
                    file_name=rank_weighted_visibility_result.get("source_file"),
                    details=_rank_weighted_visibility_details(
                        rank_weighted_visibility_result
                    ),
                )
            )

    is_brand_concentration_claim = _looks_like_bundle_brand_concentration_claim(text)
    is_attribute_share_claim = _looks_like_attribute_share_claim(text, unit)
    attribute_share_result = None
    attribute_share_routed = False

    if is_attribute_share_claim and not is_brand_concentration_claim:
        attribute_share_result = _validate_attribute_share_segment(text, package.frames)
        attribute_share_routed = attribute_share_result["status"] != "warning" or bool(
            attribute_share_result.get("candidate_evaluations")
        )

    if attribute_share_routed and attribute_share_result is not None:
        recognized = True
        if attribute_share_result["status"] == "pass":
            candidate = attribute_share_result["candidate"]
            attribute_details = _attribute_share_evidence_details(
                text,
                attribute_share_result,
            )
            population_scope = _assess_bundle_population_scope(
                text,
                candidate,
                frames=package.frames,
            )
            attribute_status = "verified"
            if population_scope is not None:
                attribute_status = population_scope["status"]
                attribute_details["population_scope"] = {
                    "status": population_scope["status"],
                    "reasons": population_scope.get("reasons", []),
                }
                attribute_details["reasons"] = population_scope.get("reasons", [])
            results.append(
                _claim_result(
                    status=attribute_status,
                    claim_family="attribute_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(candidate.get("label")),
                    file_name=candidate.get("file"),
                    details=attribute_details,
                )
            )
        elif attribute_share_result["status"] in {"fail", "partial"}:
            candidate = attribute_share_result["candidate"]
            results.append(
                _claim_result(
                    status=(
                        "partially_backed"
                        if attribute_share_result["status"] == "partial"
                        else "contradicted"
                    ),
                    claim_family="attribute_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(candidate.get("label")),
                    file_name=candidate.get("file"),
                    details=_attribute_share_evidence_details(
                        text,
                        attribute_share_result,
                    ),
                )
            )
        else:
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="attribute_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    details=_attribute_share_evidence_details(
                        text,
                        attribute_share_result,
                    ),
                )
            )

    if _looks_like_attribute_rank_claim(text):
        recognized = True
        attribute_rank_result = _validate_attribute_rank_segment(text, package.frames)
        if attribute_rank_result["status"] == "pass":
            row = attribute_rank_result["row"]
            results.append(
                _claim_result(
                    status="verified",
                    claim_family="attribute_rank",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(row.get("attribute_value")),
                    file_name=attribute_rank_result.get("source_file"),
                    details=_attribute_rank_evidence_details(attribute_rank_result),
                )
            )
        elif attribute_rank_result["status"] == "fail":
            row = attribute_rank_result["row"]
            results.append(
                _claim_result(
                    status="contradicted",
                    claim_family="attribute_rank",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(row.get("attribute_value")),
                    file_name=attribute_rank_result.get("source_file"),
                    details=_attribute_rank_evidence_details(attribute_rank_result),
                )
            )
        else:
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="attribute_rank",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    details=_attribute_rank_evidence_details(attribute_rank_result),
                )
            )

    brand_share_routed = False
    roster_brand_results: list[dict[str, Any]] = []
    if (
        _contains_numeric_evidence(text)
        and not is_brand_concentration_claim
        and not attribute_share_routed
    ):
        roster_brand_results = _validate_brand_roster_segments(text, brand_df)

    if roster_brand_results:
        recognized = True
        brand_share_routed = True
        for brand_result in roster_brand_results:
            if brand_result["status"] == "pass":
                results.append(
                    _claim_result(
                        status="verified",
                        claim_family="brand_share",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(brand_result.get("brand")),
                        file_name=brand_result.get("file"),
                        details={
                            "observed_values": brand_result.get("observed_values"),
                            "observed_segment": _normalize_text(
                                brand_result.get("segment")
                            ),
                            "package_values": brand_result.get("expected"),
                            "source_file": brand_result.get("file"),
                            "brand_name": _normalize_text(brand_result.get("brand")),
                            "matched_row_keys": {
                                "brand": _normalize_text(brand_result.get("brand"))
                            },
                            "tolerance_policy": _numeric_tolerance_policy(),
                        },
                    )
                )
            elif brand_result["status"] == "fail":
                results.append(
                    _claim_result(
                        status="contradicted",
                        claim_family="brand_share",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(brand_result.get("brand")),
                        file_name=brand_result.get("file"),
                        details={
                            "reasons": brand_result.get("reasons", []),
                            "observed_values": brand_result.get("observed_values"),
                            "observed_segment": _normalize_text(
                                brand_result.get("segment")
                            ),
                            "package_values": brand_result.get("expected"),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="brand_share",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(brand_result.get("brand")),
                        file_name=brand_result.get("file"),
                        details={
                            "message": _normalize_text(brand_result.get("message")),
                            "observed_segment": _normalize_text(
                                brand_result.get("segment")
                            ),
                        },
                    )
                )

    if (
        not brand_share_routed
        and not is_brand_concentration_claim
        and not attribute_share_routed
    ):
        mentioned_brand_rows = _brand_rows_mentioned_in_segment(text, brand_df)
        brand_overindex_result = _validate_brand_overindex_segment(text, brand_df)
        if brand_overindex_result is not None and (
            len(mentioned_brand_rows) > 1 or not _contains_numeric_evidence(text)
        ):
            recognized = True
            brand_share_routed = True
            overindex_status = brand_overindex_result["status"]
            results.append(
                _claim_result(
                    status=(
                        "partially_backed"
                        if overindex_status == "partial"
                        else (
                            "verified" if overindex_status == "pass" else "contradicted"
                        )
                    ),
                    claim_family="brand_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=", ".join(brand_overindex_result.get("brands", [])),
                    file_name=brand_overindex_result.get("file"),
                    details={
                        "observed_values": brand_overindex_result.get(
                            "observed_values", {}
                        ),
                        "package_values": brand_overindex_result.get(
                            "package_values", {}
                        ),
                        "source_file": brand_overindex_result.get("file"),
                        "matched_row_keys": brand_overindex_result.get(
                            "matched_row_keys", {}
                        ),
                        "comparison_policy": brand_overindex_result.get(
                            "comparison_policy"
                        ),
                        "reasons": brand_overindex_result.get("reasons", []),
                    },
                )
            )

    if (
        not brand_share_routed
        and _looks_like_brand_share_claim(text)
        and _contains_numeric_evidence(text)
        and not is_brand_concentration_claim
        and not attribute_share_routed
    ):
        recognized = True
        brand_result = _validate_brand_segment(
            text,
            brand_df,
            require_numeric_evidence=True,
        )
        if brand_result is None:
            if not _looks_like_bundle_metric_claim(text):
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="brand_share",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={"message": "brand not matched in package"},
                    )
                )
        elif brand_result["status"] == "pass":
            brand_share_routed = True
            results.append(
                _claim_result(
                    status="verified",
                    claim_family="brand_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(brand_result.get("brand")),
                    file_name=brand_result.get("file"),
                    details={
                        "observed_values": brand_result.get("observed_values"),
                        "package_values": brand_result.get("expected"),
                        "source_file": brand_result.get("file"),
                        "brand_name": _normalize_text(brand_result.get("brand")),
                        "matched_row_keys": {
                            "brand": _normalize_text(brand_result.get("brand"))
                        },
                        "tolerance_policy": _numeric_tolerance_policy(),
                    },
                )
            )
        elif brand_result["status"] == "fail":
            brand_share_routed = True
            results.append(
                _claim_result(
                    status="contradicted",
                    claim_family="brand_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(brand_result.get("brand")),
                    file_name=brand_result.get("file"),
                    details={
                        "reasons": brand_result.get("reasons", []),
                        "observed_values": brand_result.get("observed_values"),
                        "package_values": brand_result.get("expected"),
                        "source_file": brand_result.get("file"),
                        "brand_name": _normalize_text(brand_result.get("brand")),
                        "matched_row_keys": {
                            "brand": _normalize_text(brand_result.get("brand"))
                        },
                    },
                )
            )
        else:
            brand_share_routed = True
            results.append(
                _claim_result(
                    status="unresolved",
                    claim_family="brand_share",
                    claim_text=text,
                    slide=slide,
                    unit=unit,
                    entity=_normalize_text(brand_result.get("brand")),
                    file_name=brand_result.get("file"),
                    details={"message": _normalize_text(brand_result.get("message"))},
                )
            )

    if (
        not brand_share_routed
        and not is_brand_concentration_claim
        and not attribute_share_routed
    ):
        category_brand_result = _validate_category_brand_concentration_segment(
            text,
            brand_df,
        )
        if category_brand_result is not None:
            recognized = True
            brand_share_routed = True
            category_brand_status = category_brand_result["status"]
            if category_brand_status == "warning":
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="category_brand_concentration",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        file_name=category_brand_result.get("source_file"),
                        details={
                            "message": _normalize_text(
                                category_brand_result.get("message")
                            ),
                            "threshold_policy": category_brand_result.get(
                                "threshold_policy",
                                {},
                            ),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status=(
                            "partially_backed"
                            if category_brand_status == "partial"
                            else (
                                "verified"
                                if category_brand_status == "pass"
                                else "contradicted"
                            )
                        ),
                        claim_family="category_brand_concentration",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=_normalize_text(
                            category_brand_result.get("package_values", {}).get(
                                "dominant_brand"
                            )
                        ),
                        file_name=category_brand_result.get("source_file"),
                        details={
                            "package_values": category_brand_result.get(
                                "package_values",
                                {},
                            ),
                            "source_file": category_brand_result.get("source_file"),
                            "matched_row_keys": category_brand_result.get(
                                "matched_row_keys",
                                {},
                            ),
                            "threshold_policy": category_brand_result.get(
                                "threshold_policy",
                                {},
                            ),
                            "comparison_policy": category_brand_result.get(
                                "comparison_policy"
                            ),
                            "comparison_outcome": category_brand_status,
                            "reasons": category_brand_result.get("reasons", []),
                        },
                    )
                )

    if (
        not brand_share_routed
        and not is_brand_concentration_claim
        and not attribute_share_routed
    ):
        directional_attribute_result = _validate_directional_attribute_segment(
            text,
            package.frames,
        )
        if directional_attribute_result is not None:
            recognized = True
            direction_status = directional_attribute_result["status"]
            if direction_status == "warning":
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="attribute_direction",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "message": "directional attribute claim did not resolve cleanly",
                            "attribute_support": directional_attribute_result.get(
                                "attribute_support",
                                [],
                            ),
                            "observed_fragments": directional_attribute_result.get(
                                "observed_fragments",
                                [],
                            ),
                            "threshold_policy": directional_attribute_result.get(
                                "threshold_policy",
                                {},
                            ),
                            "reasons": directional_attribute_result.get("reasons", []),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status=(
                            "verified"
                            if direction_status == "pass"
                            else (
                                "partially_backed"
                                if direction_status == "partial"
                                else "contradicted"
                            )
                        ),
                        claim_family="attribute_direction",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "attribute_support": directional_attribute_result.get(
                                "attribute_support",
                                [],
                            ),
                            "component_entities": directional_attribute_result.get(
                                "component_entities",
                                [],
                            ),
                            "aggregation_rule_id": directional_attribute_result.get(
                                "aggregation_rule_id"
                            ),
                            "cohort_basis": directional_attribute_result.get(
                                "cohort_basis"
                            ),
                            "threshold_policy": directional_attribute_result.get(
                                "threshold_policy",
                                {},
                            ),
                            "ranking_basis": directional_attribute_result.get(
                                "ranking_basis"
                            ),
                            "observed_fragments": directional_attribute_result.get(
                                "observed_fragments",
                                [],
                            ),
                            "comparison_outcome": direction_status,
                            "reasons": directional_attribute_result.get("reasons", []),
                        },
                    )
                )

    if is_brand_concentration_claim:
        slide_level_result = _validate_bundle_brand_concentration_summary(
            segment=text,
            slide=slide,
            package=package,
            bundle_records=bundle_records,
        )
        row_level_result = None
        if _looks_like_bundle_brand_concentration_row(text):
            row_level_result = _validate_bundle_brand_concentration_row(
                text,
                frames=package.frames,
                bundle_records=bundle_records,
                context_segment=contextual_text,
            )

        brand_concentration_result = row_level_result or slide_level_result
        if brand_concentration_result is not None:
            recognized = True
            if row_level_result is not None:
                candidate = row_level_result["candidate"]
                status = (
                    "verified"
                    if row_level_result["status"] == "pass"
                    else "contradicted"
                )
                results.append(
                    _claim_result(
                        status=status,
                        claim_family="bundle_brand_concentration",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=row_level_result["entity"],
                        file_name=candidate["file"],
                        details=_bundle_brand_concentration_details(
                            observed_values=row_level_result["observed_values"],
                            candidate=candidate,
                            reasons=row_level_result["reasons"],
                            extra={
                                "comparison_outcome": row_level_result["status"],
                                "non_collapse": row_level_result["non_collapse"],
                                "non_collapse_reasons": row_level_result[
                                    "non_collapse_reasons"
                                ],
                            },
                        ),
                    )
                )
            elif slide_level_result["status"] == "warning":
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="bundle_brand_concentration",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "message": _normalize_text(
                                slide_level_result.get("message")
                            ),
                            "row_support": slide_level_result.get("row_support", []),
                            "threshold_policy": _bundle_brand_concentration_threshold_policy(),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status=(
                            "verified"
                            if slide_level_result["status"] == "pass"
                            else "contradicted"
                        ),
                        claim_family="bundle_brand_concentration",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "row_support": slide_level_result.get("row_support", []),
                            "brand_support": slide_level_result.get(
                                "brand_support",
                                [],
                            ),
                            "brand_span_range": slide_level_result.get(
                                "brand_span_range"
                            ),
                            "threshold_policy": _bundle_brand_concentration_threshold_policy(),
                            "comparison_outcome": slide_level_result["status"],
                            "reasons": slide_level_result.get("reasons", []),
                        },
                    )
                )

    if _looks_like_emerging_lane_summary_claim(text):
        recognized = True
        lane_result = _validate_emerging_lane_summary(
            segment=text,
            slide=slide,
            package=package,
            bundle_records=bundle_records,
        )
        if lane_result is not None:
            if lane_result["status"] == "warning":
                results.append(
                    _claim_result(
                        status="unresolved",
                        claim_family="emerging_lane_summary",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "message": _normalize_text(lane_result.get("message")),
                            "row_support": lane_result.get("row_support", []),
                            "threshold_policy": lane_result.get(
                                "threshold_policy",
                                _emerging_lane_threshold_policy(),
                            ),
                        },
                    )
                )
            else:
                results.append(
                    _claim_result(
                        status=(
                            "verified"
                            if lane_result["status"] == "pass"
                            else "contradicted"
                        ),
                        claim_family="emerging_lane_summary",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        details={
                            "row_support": lane_result.get("row_support", []),
                            "attribute_support": lane_result.get(
                                "attribute_support",
                                [],
                            ),
                            "component_entities": lane_result.get(
                                "component_entities",
                                [],
                            ),
                            "aggregation_rule_id": lane_result.get(
                                "aggregation_rule_id"
                            ),
                            "cohort_basis": lane_result.get("cohort_basis"),
                            "threshold_policy": lane_result.get(
                                "threshold_policy",
                                _emerging_lane_threshold_policy(),
                            ),
                            "ranking_basis": lane_result.get("ranking_basis"),
                            "comparison_outcome": lane_result["status"],
                            "reasons": lane_result.get("reasons", []),
                        },
                    )
                )

    review_validation_result = _validate_review_validation_segment(text, package.frames)
    if review_validation_result is not None:
        recognized = True
        results.append(
            _claim_result(
                status=(
                    "verified"
                    if review_validation_result["status"] == "pass"
                    else "contradicted"
                ),
                claim_family="review_validation",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={
                    "row_support": review_validation_result.get("row_support", []),
                    "component_entities": review_validation_result.get(
                        "component_entities",
                        [],
                    ),
                    "aggregation_rule_id": review_validation_result.get(
                        "aggregation_rule_id"
                    ),
                    "cohort_basis": review_validation_result.get("cohort_basis"),
                    "threshold_policy": review_validation_result.get(
                        "threshold_policy",
                        _review_validation_threshold_policy(),
                    ),
                    "ranking_basis": review_validation_result.get("ranking_basis"),
                    "comparison_outcome": review_validation_result["status"],
                    "reasons": review_validation_result.get("reasons", []),
                },
            )
        )

    review_friction_result = _validate_review_friction_segment(text, package.frames)
    if review_friction_result is not None:
        recognized = True
        results.append(
            _claim_result(
                status=(
                    "verified"
                    if review_friction_result["status"] == "pass"
                    else "contradicted"
                ),
                claim_family="review_friction",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={
                    "row_support": review_friction_result.get("row_support", []),
                    "component_entities": review_friction_result.get(
                        "component_entities",
                        [],
                    ),
                    "aggregation_rule_id": review_friction_result.get(
                        "aggregation_rule_id"
                    ),
                    "cohort_basis": review_friction_result.get("cohort_basis"),
                    "threshold_policy": review_friction_result.get(
                        "threshold_policy",
                        _review_friction_threshold_policy(),
                    ),
                    "ranking_basis": review_friction_result.get("ranking_basis"),
                    "comparison_outcome": review_friction_result["status"],
                    "reasons": review_friction_result.get("reasons", []),
                },
            )
        )

    if (
        _looks_like_bundle_metric_claim(text)
        and not rank_weighted_visibility_routed
        and not sale_pressure_routed
        and not is_brand_concentration_claim
        and not attribute_share_routed
        and not brand_share_routed
    ):
        explicit_labels = _resolved_explicit_bundle_labels_from_segment(
            text,
            bundle_records,
            package.frames,
        )
        if explicit_labels:
            matched_labels = explicit_labels
        else:
            matched_labels = _matched_bundle_labels(contextual_text, bundle_records)
            matched_labels = _prefer_bundle_labels_with_numeric_fit(
                text,
                matched_labels,
                package.frames,
                context_segment=contextual_text,
            )
        if matched_labels:
            recognized = True
        for label in matched_labels:
            label_resolution = _resolve_bundle_label_targets(
                text, label, package.frames
            )
            for target_label in label_resolution["labels"]:
                localized_segment = _localize_bundle_segment(text, target_label)
                bundle_result = _best_bundle_candidate(
                    localized_segment,
                    target_label,
                    package.frames,
                    context_segment=contextual_text,
                )
                if bundle_result is None:
                    results.append(
                        _claim_result(
                            status="unresolved",
                            claim_family="bundle_metric",
                            claim_text=text,
                            slide=slide,
                            unit=unit,
                            entity=target_label,
                            details={
                                "message": "no matching package row found for label"
                            },
                        )
                    )
                    continue
                if bundle_result["status"] == "pass":
                    population_scope = _assess_bundle_population_scope(
                        localized_segment,
                        bundle_result["candidate"],
                        frames=package.frames,
                    )
                    if population_scope is not None:
                        results.append(
                            _claim_result(
                                status=population_scope["status"],
                                claim_family="bundle_metric",
                                claim_text=text,
                                slide=slide,
                                unit=unit,
                                entity=target_label,
                                file_name=bundle_result["candidate"]["file"],
                                details=_bundle_evidence_details(
                                    localized_segment,
                                    bundle_result["candidate"],
                                    reasons=population_scope["reasons"],
                                    extra={
                                        "observed_values": population_scope.get(
                                            "observed_values"
                                        ),
                                        "package_values": population_scope.get(
                                            "package_values"
                                        ),
                                    },
                                ),
                            )
                        )
                        continue
                    absence_result = _evaluate_bundle_absence_claim(
                        localized_segment,
                        target_label,
                        package.frames,
                    )
                    if (
                        absence_result is not None
                        and absence_result["status"] == "fail"
                    ):
                        results.append(
                            _claim_result(
                                status="contradicted",
                                claim_family="bundle_metric",
                                claim_text=text,
                                slide=slide,
                                unit=unit,
                                entity=target_label,
                                file_name=bundle_result["candidate"]["file"],
                                details=_bundle_evidence_details(
                                    localized_segment,
                                    bundle_result["candidate"],
                                    reasons=absence_result["reasons"],
                                    extra={
                                        "zero_occurrence_check": absence_result[
                                            "zero_occurrence_check"
                                        ],
                                    },
                                ),
                            )
                        )
                        continue
                    absence_extra = (
                        {
                            "zero_occurrence_check": absence_result[
                                "zero_occurrence_check"
                            ]
                        }
                        if absence_result is not None
                        else None
                    )
                    results.append(
                        _claim_result(
                            status="verified",
                            claim_family="bundle_metric",
                            claim_text=text,
                            slide=slide,
                            unit=unit,
                            entity=target_label,
                            file_name=bundle_result["candidate"]["file"],
                            details=_bundle_evidence_details(
                                localized_segment,
                                bundle_result["candidate"],
                                extra=absence_extra,
                            ),
                        )
                    )
                    continue
                if bundle_result["status"] == "warning":
                    results.append(
                        _claim_result(
                            status="unresolved",
                            claim_family="bundle_metric",
                            claim_text=text,
                            slide=slide,
                            unit=unit,
                            entity=target_label,
                            file_name=bundle_result["candidates"][0]["file"],
                            details={
                                "message": _normalize_text(
                                    bundle_result.get("message")
                                ),
                                "parsed_cohort_labels": _parsed_cohort_labels(
                                    localized_segment
                                ),
                                "candidate_evaluations": bundle_result.get(
                                    "candidate_evaluations", []
                                ),
                            },
                        )
                    )
                    continue
                if (
                    len(matched_labels) > 1
                    or _looks_like_multi_claim_bundle_sentence(text)
                    or _looks_like_truncated_numeric_comparison(text)
                    or _looks_like_ocr_fused_claim(text)
                ):
                    results.append(
                        _claim_result(
                            status="unresolved",
                            claim_family="bundle_metric",
                            claim_text=text,
                            slide=slide,
                            unit=unit,
                            entity=target_label,
                            details={
                                "message": "bundle metric could not be cleanly disambiguated"
                            },
                        )
                    )
                    continue
                expected_candidates = _failed_bundle_expected_candidates(bundle_result)
                failed_candidate_evidence = _best_failed_bundle_candidate_evaluation(
                    bundle_result
                )
                if failed_candidate_evidence is None:
                    candidate_evaluations = bundle_result.get(
                        "candidate_evaluations", []
                    )
                    results.append(
                        _claim_result(
                            status="unresolved",
                            claim_family="bundle_metric",
                            claim_text=text,
                            slide=slide,
                            unit=unit,
                            entity=target_label,
                            details={
                                "message": (
                                    "bundle metric could not be matched to a concrete "
                                    "package row contradiction"
                                ),
                                "observed_values": _extract_numeric_claim_evidence(
                                    text
                                ),
                                "candidate_evaluations": candidate_evaluations,
                                "expected_candidates": expected_candidates,
                            },
                        )
                    )
                    continue
                candidate_evaluations = _candidate_evaluations_with_selected_first(
                    bundle_result.get("candidate_evaluations", []),
                    failed_candidate_evidence,
                )
                reasons = _candidate_evaluation_reasons(failed_candidate_evidence)
                has_partial_metric_support = (
                    _candidate_evaluation_has_partial_metric_support(
                        failed_candidate_evidence
                    )
                )
                results.append(
                    _claim_result(
                        status=(
                            "partially_backed"
                            if has_partial_metric_support
                            else "contradicted"
                        ),
                        claim_family="bundle_metric",
                        claim_text=text,
                        slide=slide,
                        unit=unit,
                        entity=target_label,
                        file_name=_normalize_text(failed_candidate_evidence.get("file"))
                        or None,
                        details={
                            "observed_values": _extract_numeric_claim_evidence(text),
                            "source_file": failed_candidate_evidence.get("file"),
                            "matched_row_keys": failed_candidate_evidence.get(
                                "matched_row_keys", {}
                            ),
                            "package_values": failed_candidate_evidence.get(
                                "package_values", {}
                            ),
                            "numeric_distance_from_claim": failed_candidate_evidence.get(
                                "numeric_distance_from_claim"
                            ),
                            **_numeric_basis_diagnostic_fields_for_evaluation(
                                localized_segment,
                                failed_candidate_evidence,
                                bundle_result.get("candidates"),
                            ),
                            "reasons": reasons,
                            "partial_support_basis": (
                                "at least one deterministic metric matched while "
                                "another deterministic metric failed"
                                if has_partial_metric_support
                                else None
                            ),
                            "matched_metrics": failed_candidate_evidence.get(
                                "matched_metrics", []
                            ),
                            "mismatched_metrics": failed_candidate_evidence.get(
                                "mismatched_metrics", []
                            ),
                            "candidate_evaluations": candidate_evaluations,
                            "expected_candidates": expected_candidates,
                            "tolerance_policy": _numeric_tolerance_policy(),
                        },
                    )
                )

    if results:
        return _downgrade_unsupported_contradictions(results), recognized

    if _looks_like_summary_synthesis_claim(text):
        return [
            _claim_result(
                status="unresolved",
                claim_family="summary_synthesis",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={
                    "message": "winning summary has no verified deterministic support components yet"
                },
            )
        ], recognized

    if _looks_like_unanchored_rank_delta_claim(text):
        return [
            _claim_result(
                status="unresolved",
                claim_family="rank_delta_context_missing",
                claim_text=text,
                slide=slide,
                unit=unit,
                details=_unanchored_rank_delta_details(text),
            )
        ], recognized

    if _looks_claim_like_text(
        text,
        block_type=_normalize_text(unit.get("block_type")),
    ) or _looks_like_product_attribute_claim(text):
        return [
            _claim_result(
                status="unresolved",
                claim_family="unclassified",
                claim_text=text,
                slide=slide,
                unit=unit,
                details={"message": "claim-like text was not parsed deterministically"},
            )
        ], recognized
    return [], recognized


def _build_launch_validation_llm_wrapper() -> Any:
    from modules.llm.llm_call_wrapper import init_llm_wrapper
    from modules.utilities.session_context import SessionContext

    session = SessionContext.from_state({})
    init_llm_wrapper("", session=session)
    return session.state["llm_wrapper"]


def _query_launch_validation_llm(
    llm_wrapper: Any,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    from modules.llm.model_router import query_llm_return_json
    from modules.utilities.config import get_naming_params

    naming_params = get_naming_params()
    response = query_llm_return_json(
        llm_wrapper,
        naming_params["launchValidationReviewQuery"],
        system_prompt,
        user_prompt,
    )
    return response if isinstance(response, dict) else {}


def _llm_review_claim_payload(
    claim: dict[str, Any],
    *,
    source: str,
    source_index: int,
) -> dict[str, Any]:
    details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
    compact_details: dict[str, Any] = {}
    for key in (
        "message",
        "reasons",
        "observed_values",
        "package_values",
        "expected_candidates",
    ):
        value = details.get(key)
        if value:
            compact_details[key] = value
    return {
        "source": source,
        "source_index": source_index,
        "status": _normalize_text(claim.get("status")) or source,
        "claim_family": _normalize_text(claim.get("claim_family")) or "unknown",
        "slide_number": claim.get("slide_number"),
        "source_kind": _normalize_text(claim.get("source_kind")),
        "claim_text": _truncate_text(claim.get("claim_text"), limit=260),
        "entity": _normalize_text(claim.get("entity")),
        "details": compact_details,
    }


def _llm_review_candidates(
    payload: dict[str, Any],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source, claims in (
        (
            "contradicted",
            [
                claim
                for claim in payload.get("claims", [])
                if isinstance(claim, dict) and claim.get("status") == "contradicted"
            ],
        ),
        (
            "partially_backed",
            [
                claim
                for claim in payload.get("claims", [])
                if isinstance(claim, dict) and claim.get("status") == "partially_backed"
            ],
        ),
        (
            "weakly_backed",
            [
                claim
                for claim in payload.get("claims", [])
                if isinstance(claim, dict) and claim.get("status") == "weakly_backed"
            ],
        ),
        (
            "unresolved",
            [
                claim
                for claim in payload.get("unresolved", [])
                if isinstance(claim, dict)
            ],
        ),
    ):
        for source_index, claim in enumerate(claims):
            candidates.append(
                _llm_review_claim_payload(
                    claim,
                    source=source,
                    source_index=source_index,
                )
            )
            if len(candidates) >= max_items:
                return candidates
    return candidates


def _launch_validation_llm_system_prompt() -> str:
    return """
You are an advisory reviewer for a deterministic PDF validation pipeline.

Rules:
- Do not recalculate percentages, counts, ratios, ranks, or brand shares.
- Do not override deterministic validation statuses.
- Do not mark a deterministic contradiction as false just because it sounds plausible.
- Use the provided package/deterministic evidence only as context.
- Your job is to classify unresolved or warning items, identify likely missed claim families, and recommend whether future deterministic helpers are needed.
- If a claim is numeric, recommend a deterministic helper rather than validating it by opinion.
- Return JSON only.
""".strip()


def _launch_validation_llm_user_prompt(
    payload: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str:
    prompt_payload = {
        "report": Path(str(payload.get("pdf_path", "report.pdf"))).name,
        "status": payload.get("status"),
        "report_type": payload.get("report_type", "launch_report"),
        "package": payload.get("package", {}),
        "summary": payload.get("summary", {}),
        "reading_quality": payload.get("reading_quality", {}),
        "calculation_summary": payload.get("calculation_summary", []),
        "candidate_items": candidates,
    }
    return (
        "Review these deterministic validation leftovers and hard findings. "
        "Return JSON with keys: summary, items, missed_claim_candidates, "
        "helper_suggestions. Each item must include source, source_index, "
        "llm_category, priority, recommended_action, rationale, and "
        "suggested_helper_family. Allowed recommended_action values are "
        "add_deterministic_helper, fix_deck, inspect_package_link, improve_reader, "
        "leave_unresolved, or no_action.\n\n"
        + json.dumps(prompt_payload, ensure_ascii=False, indent=2)
    )


def _normalize_llm_review_items(
    raw_items: Any,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        items.append(
            {
                "source": _normalize_text(raw_item.get("source")) or "unknown",
                "source_index": _int_or_none(raw_item.get("source_index")),
                "slide_number": _int_or_none(raw_item.get("slide_number")),
                "claim_text": _truncate_text(raw_item.get("claim_text"), limit=260),
                "llm_category": _normalize_text(raw_item.get("llm_category"))
                or "unknown",
                "priority": _normalize_text(raw_item.get("priority")) or "medium",
                "recommended_action": _normalize_text(
                    raw_item.get("recommended_action")
                )
                or "leave_unresolved",
                "rationale": _truncate_text(raw_item.get("rationale"), limit=420),
                "suggested_helper_family": _normalize_text(
                    raw_item.get("suggested_helper_family")
                )
                or None,
            }
        )
        if len(items) >= limit:
            break
    return items


def _llm_review_summary_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key in (
            "overall_assessment",
            "summary",
            "recommendation",
            "next_step",
        ):
            text = _normalize_text(value.get(key))
            if text:
                parts.append(text)
        if parts:
            return _truncate_text(" ".join(parts), limit=700)
        return _truncate_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True), limit=700
        )
    return _truncate_text(value, limit=700)


def _normalize_llm_review_short_list(
    raw_items: Any,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        claim_text = _truncate_text(raw_item.get("claim_text"), limit=260)
        claim_family = _normalize_text(raw_item.get("claim_family"))
        rationale = _truncate_text(raw_item.get("rationale"), limit=420)
        recommended_action = (
            _normalize_text(raw_item.get("recommended_action")) or "leave_unresolved"
        )
        if not (claim_text or rationale):
            continue
        if not claim_family and recommended_action in {"leave_unresolved", "no_action"}:
            continue
        items.append(
            {
                "slide_number": _int_or_none(raw_item.get("slide_number")),
                "claim_text": claim_text,
                "claim_family": claim_family or "unknown",
                "recommended_action": recommended_action,
                "rationale": rationale,
            }
        )
        if len(items) >= limit:
            break
    return items


def _launch_validation_llm_review_skipped() -> dict[str, Any]:
    return {
        "status": "skipped",
        "mode": "llm_advisory",
        "effect_on_validation_status": "none",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": "No deterministic leftovers were available for LLM review.",
        "items": [],
        "missed_claim_candidates": [],
        "helper_suggestions": [],
    }


def _launch_validation_llm_review_error(error: object) -> dict[str, Any]:
    return {
        "status": "error",
        "mode": "llm_advisory",
        "effect_on_validation_status": "none",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": "LLM review failed; deterministic validation is unchanged.",
        "error": _truncate_text(str(error), limit=300),
        "items": [],
        "missed_claim_candidates": [],
        "helper_suggestions": [],
    }


def _launch_validation_llm_review_from_raw(
    raw_review: Any,
    *,
    max_items: int,
) -> dict[str, Any]:
    review = raw_review if isinstance(raw_review, dict) else {}
    return {
        "status": "reviewed",
        "mode": "llm_advisory",
        "effect_on_validation_status": "none",
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": _llm_review_summary_text(review.get("summary")),
        "items": _normalize_llm_review_items(
            review.get("items"),
            limit=max_items,
        ),
        "missed_claim_candidates": _normalize_llm_review_short_list(
            review.get("missed_claim_candidates"),
            limit=12,
        ),
        "helper_suggestions": _normalize_llm_review_short_list(
            review.get("helper_suggestions"),
            limit=12,
        ),
    }


def review_launch_report_validation_with_llm(
    payload: dict[str, Any],
    *,
    llm_wrapper: Any | None = None,
    max_items: int = 24,
) -> dict[str, Any]:
    """Attach a non-authoritative LLM review to a deterministic validation payload."""

    candidates = _llm_review_candidates(payload, max_items=max(1, max_items))
    if not candidates:
        return _launch_validation_llm_review_skipped()

    try:
        wrapper = (
            llm_wrapper
            if llm_wrapper is not None
            else _build_launch_validation_llm_wrapper()
        )
        raw_review = _query_launch_validation_llm(
            wrapper,
            _launch_validation_llm_system_prompt(),
            _launch_validation_llm_user_prompt(payload, candidates),
        )
    except Exception as exc:
        raise LaunchValidationOpenAIError(
            "OpenAI call failed during launch validation LLM review."
        ) from exc

    return _launch_validation_llm_review_from_raw(raw_review, max_items=max_items)


def _attach_batch_llm_reviews_if_requested(
    reports: list[dict[str, Any]],
    *,
    llm_review: bool,
    llm_wrapper: Any | None,
    llm_review_max_items: int,
) -> list[dict[str, Any]]:
    if not llm_review:
        return reports

    reviewed_reports = [dict(report) for report in reports]
    pending: list[tuple[int, str]] = []
    for index, report in enumerate(reviewed_reports):
        candidates = _llm_review_candidates(
            report,
            max_items=max(1, llm_review_max_items),
        )
        if not candidates:
            reviewed_reports[index][
                "llm_review"
            ] = _launch_validation_llm_review_skipped()
            continue
        pending.append(
            (
                index,
                _launch_validation_llm_user_prompt(report, candidates),
            )
        )

    if not pending:
        return reviewed_reports

    try:
        wrapper = (
            llm_wrapper
            if llm_wrapper is not None
            else _build_launch_validation_llm_wrapper()
        )
    except Exception as exc:
        raise LaunchValidationOpenAIError(
            "OpenAI wrapper initialization failed during batch launch validation LLM review."
        ) from exc

    system_prompt = _launch_validation_llm_system_prompt()
    if len(pending) == 1:
        index, user_prompt = pending[0]
        try:
            raw_review = _query_launch_validation_llm(
                wrapper, system_prompt, user_prompt
            )
            reviewed_reports[index]["llm_review"] = (
                _launch_validation_llm_review_from_raw(
                    raw_review,
                    max_items=llm_review_max_items,
                )
            )
        except Exception as exc:
            raise LaunchValidationOpenAIError(
                "OpenAI call failed during launch validation LLM review."
            ) from exc
        return reviewed_reports

    try:
        from modules.llm.batch_runner import run_step_json
        from modules.utilities.config import get_naming_params

        naming_params = get_naming_params()
        raw_reviews = run_step_json(
            wrapper,
            naming_params["launchValidationReviewQuery"],
            system_prompt,
            [user_prompt for _, user_prompt in pending],
        )
    except Exception as exc:
        raise LaunchValidationOpenAIError(
            "OpenAI call failed during batch launch validation LLM review."
        ) from exc

    for (index, _), raw_review in zip(pending, raw_reviews):
        reviewed_reports[index]["llm_review"] = _launch_validation_llm_review_from_raw(
            raw_review,
            max_items=llm_review_max_items,
        )
    if len(raw_reviews) < len(pending):
        for index, _ in pending[len(raw_reviews) :]:
            reviewed_reports[index]["llm_review"] = _launch_validation_llm_review_error(
                "Batch LLM review returned fewer results than requested."
            )
    return reviewed_reports


def _attach_llm_review_if_requested(
    payload: dict[str, Any],
    *,
    llm_review: bool,
    llm_wrapper: Any | None,
    llm_review_max_items: int,
) -> dict[str, Any]:
    if not llm_review:
        return payload
    reviewed_payload = dict(payload)
    reviewed_payload["llm_review"] = review_launch_report_validation_with_llm(
        payload,
        llm_wrapper=llm_wrapper,
        max_items=llm_review_max_items,
    )
    return reviewed_payload


def validate_launch_report_pdf(
    pdf_path: Path,
    *,
    package_dir: Path | None = None,
    package_roots: Iterable[Path] | None = None,
    brief_roots: Iterable[Path] | None = None,
    lang: str = "eng",
    include_bboxes: bool = True,
    llm_review: bool = False,
    llm_wrapper: Any | None = None,
    llm_review_max_items: int = 24,
    refresh_reading_cache: bool = False,
) -> dict[str, Any]:
    """Validate one launch-report PDF against its source package."""

    resolved_package_ref: LaunchPackageRef | None = None
    resolver_details: dict[str, Any]
    if package_dir is not None:
        resolved_package_ref = load_launch_package_data(package_dir).ref
        resolver_details = {
            "status": "manual",
            "pdf_path": str(pdf_path.resolve()),
            "package_dir": str(package_dir.resolve()),
        }
    else:
        summary_report_key = _summary_report_key_for_pdf(pdf_path)
        if summary_report_key is not None:
            summary_resolver_details = _summary_report_resolver_details(
                pdf_path,
                summary_report_key,
                brief_roots=brief_roots,
            )
            payload = _validate_summary_report_pdf(
                pdf_path,
                report_key=summary_report_key,
                resolver_details=summary_resolver_details,
                lang=lang,
                include_bboxes=include_bboxes,
                refresh_reading_cache=refresh_reading_cache,
            )
            return _attach_llm_review_if_requested(
                payload,
                llm_review=llm_review,
                llm_wrapper=llm_wrapper,
                llm_review_max_items=llm_review_max_items,
            )
        resolved_package_ref, resolver_details = resolve_launch_package_for_pdf(
            pdf_path,
            package_roots=package_roots,
        )

    if resolved_package_ref is None:
        package_count = resolver_details.get("discovered_package_count")
        package_root_count = len(
            resolver_details.get("package_roots")
            if isinstance(resolver_details.get("package_roots"), list)
            else []
        )
        resolver_message = (
            "No matching launch package was found for this report. "
            f"Expected category `{resolver_details.get('normalized_key', '')}`"
            f"{' for retailer `' + str(resolver_details.get('retailer_hint')) + '`' if resolver_details.get('retailer_hint') else ''}. "
            f"Discovered {package_count if isinstance(package_count, int) else 0} "
            f"package(s) across {package_root_count} configured root(s). "
            "PDF reading/OCR was not run because deterministic validation requires "
            "the source package first."
        )
        payload = {
            "status": "fail",
            "pdf_path": str(pdf_path.resolve()),
            "generated_at": datetime.now(UTC).isoformat(),
            "resolver": resolver_details,
            "summary": {
                "verified_count": 0,
                "contradicted_count": 0,
                "partially_backed_count": 0,
                "weakly_backed_count": 0,
                "unresolved_count": 1,
                "claim_count": 0,
                "slide_count": 0,
            },
            "claims": [],
            "unresolved": [
                {
                    "status": "unresolved",
                    "claim_family": "package_resolution",
                    "claim_text": "",
                    "details": {"message": resolver_message},
                }
            ],
            "reading_quality": {
                "status": "not_run",
                "summary": {
                    "slide_count": 0,
                    "ok_slide_count": 0,
                    "warning_slide_count": 0,
                    "poor_slide_count": 0,
                },
                "reasons": [
                    "reading did not run because no matching source package was found"
                ],
                "flagged_slides": [],
            },
            "scope_note": (
                "Validation stopped before PDF reading because no matching launch "
                "package could be resolved for the report."
            ),
        }
        return payload

    package = load_launch_package_data(resolved_package_ref.package_dir)
    generation_source = _launch_report_generation_source(
        pdf_path,
        current_package=package,
    )
    reading_payload = build_pdf_reading_payload_for_validation(
        pdf_path,
        lang=lang,
        include_bboxes=include_bboxes,
        force=refresh_reading_cache,
    )
    reading_quality = _assess_reading_quality(reading_payload)
    bundle_records = _bundle_records(package.bundle_labels)

    claims: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    non_claims: list[dict[str, Any]] = []
    mapping_issues: list[dict[str, Any]] = []
    image_regions: list[dict[str, Any]] = []
    slides = (
        reading_payload.get("slides")
        if isinstance(reading_payload.get("slides"), list)
        else []
    )
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        seen_unit_keys: set[tuple[str, str | None, str | None]] = set()
        for unit in _iter_slide_units(slide):
            unit_text = _normalize_text(unit.get("text"))
            unit_key = (
                _canonical_text(unit_text),
                _normalize_text(unit.get("block_id")) or None,
                _normalize_text(unit.get("source_kind")) or None,
            )
            if not unit_text or unit_key in seen_unit_keys:
                continue
            seen_unit_keys.add(unit_key)
            results, _recognized = _evaluate_unit(
                slide=slide,
                unit=unit,
                package=package,
                bundle_records=bundle_records,
            )
            for result in results:
                if result["status"] == "unresolved":
                    unresolved.append(result)
                elif result["status"] == "non_claim":
                    non_claims.append(result)
                elif result["status"] == "ocr_layout_mapping_issue":
                    mapping_issues.append(result)
                else:
                    claims.append(result)

        figure_regions = (
            slide.get("figure_regions")
            if isinstance(slide.get("figure_regions"), list)
            else []
        )
        for region_index, _region in enumerate(figure_regions):
            image_regions.append(_image_region_result(slide, region_index))

    claims, unresolved = _resolve_deck_level_emerging_lane_summaries(
        claims,
        unresolved,
    )
    claims, unresolved = _resolve_deck_level_report_summaries(
        claims,
        unresolved,
        package,
    )
    claims, unresolved = _resolve_deck_level_contextual_brand_concentration_claims(
        claims,
        unresolved,
        package,
        bundle_records,
    )
    claims, unresolved = _resolve_deck_level_contextual_bundle_descriptor_claims(
        claims,
        unresolved,
        non_claims,
        package,
        bundle_records,
    )
    claims, unresolved = _resolve_deck_level_numeric_signal_references(
        claims,
        unresolved,
    )
    claims, unresolved = _resolve_deck_level_product_claims(
        claims,
        unresolved,
        non_claims,
        package,
    )
    claims, unresolved = _resolve_deck_level_exhibit_example_summaries(
        claims,
        unresolved,
        non_claims,
        package,
    )
    claims, unresolved = _resolve_deck_level_report_summaries(
        claims,
        unresolved,
        package,
    )

    verified_count = sum(1 for claim in claims if claim["status"] == "verified")
    contradicted_count = sum(1 for claim in claims if claim["status"] == "contradicted")
    partially_backed_count = sum(
        1 for claim in claims if claim["status"] == "partially_backed"
    )
    weakly_backed_count = sum(
        1 for claim in claims if claim["status"] == "weakly_backed"
    )
    unresolved_count = len(unresolved)
    non_claim_count = len(non_claims)
    mapping_issue_count = len(mapping_issues)

    status = "pass"
    if contradicted_count:
        status = "fail"
    elif (
        unresolved_count
        or mapping_issue_count
        or partially_backed_count
        or weakly_backed_count
        or reading_quality["status"] != "read_ok"
    ):
        status = "pass_with_warnings"

    payload = {
        "status": status,
        "pdf_path": str(pdf_path.resolve()),
        "package_dir": str(package.ref.package_dir.resolve()),
        "generated_at": datetime.now(UTC).isoformat(),
        "resolver": resolver_details,
        "package": {
            "retailer": package.ref.retailer,
            "category_key": package.ref.category_key,
            "category_label": package.ref.category_label,
            "content_fingerprint": package.content_fingerprint,
        },
        "generation_source": generation_source,
        "calculation_summary": list(package.calculation_summary),
        "summary": {
            "verified_count": verified_count,
            "contradicted_count": contradicted_count,
            "partially_backed_count": partially_backed_count,
            "weakly_backed_count": weakly_backed_count,
            "unresolved_count": unresolved_count,
            "non_claim_count": non_claim_count,
            "mapping_issue_count": mapping_issue_count,
            "image_region_count": len(image_regions),
            "claim_count": len(claims),
            "slide_count": len(slides),
        },
        "reading_quality": reading_quality,
        "claims": claims,
        "unresolved": unresolved,
        "non_claims": non_claims,
        "mapping_issues": mapping_issues,
        "image_regions": image_regions,
        "scope_note": (
            "This validator checks deterministic launch-package claims against the final PDF "
            "using the same layout, OCR, and merged slide-understanding pipeline as the slide editor. "
            "Claim-like text not yet covered by deterministic parsers is left unresolved. "
            "Image regions are exposed separately without OCR interpretation."
        ),
    }
    return _attach_llm_review_if_requested(
        payload,
        llm_review=llm_review,
        llm_wrapper=llm_wrapper,
        llm_review_max_items=llm_review_max_items,
    )


def validate_launch_report_batch(
    pdf_paths: Iterable[Path],
    *,
    package_roots: Iterable[Path] | None = None,
    brief_roots: Iterable[Path] | None = None,
    lang: str = "eng",
    include_bboxes: bool = True,
    llm_review: bool = False,
    llm_wrapper: Any | None = None,
    llm_review_max_items: int = 24,
    refresh_reading_cache: bool = False,
) -> dict[str, Any]:
    """Validate a batch of launch-report PDFs."""

    resolved_pdf_paths = [Path(path) for path in pdf_paths]
    reports: list[dict[str, Any]] = []
    for report_index, pdf_path in enumerate(resolved_pdf_paths, start=1):
        report_started_at = time.perf_counter()
        LOGGER.info(
            "Validating launch report %s/%s: %s",
            report_index,
            len(resolved_pdf_paths),
            pdf_path.name,
        )
        report = validate_launch_report_pdf(
            pdf_path,
            package_roots=package_roots,
            brief_roots=brief_roots,
            lang=lang,
            include_bboxes=include_bboxes,
            llm_review=False,
            llm_wrapper=None,
            llm_review_max_items=llm_review_max_items,
            refresh_reading_cache=refresh_reading_cache,
        )
        reports.append(report)
        LOGGER.info(
            "Finished launch report %s/%s: %s -> %s in %.1fs",
            report_index,
            len(resolved_pdf_paths),
            pdf_path.name,
            report.get("status", "unknown"),
            time.perf_counter() - report_started_at,
        )
    if llm_review:
        LOGGER.info("Starting batch LLM advisory review for %s report(s)", len(reports))
        review_started_at = time.perf_counter()
    reports = _attach_batch_llm_reviews_if_requested(
        reports,
        llm_review=llm_review,
        llm_wrapper=llm_wrapper,
        llm_review_max_items=llm_review_max_items,
    )
    if llm_review:
        LOGGER.info(
            "Finished batch LLM advisory review in %.1fs",
            time.perf_counter() - review_started_at,
        )

    pass_count = sum(1 for report in reports if report["status"] == "pass")
    warning_count = sum(
        1 for report in reports if report["status"] == "pass_with_warnings"
    )
    fail_count = sum(1 for report in reports if report["status"] == "fail")
    not_validated_count = sum(
        1 for report in reports if report["status"] == "not_validated"
    )
    unresolved_package_count = sum(
        1
        for report in reports
        if report.get("resolver", {}).get("status") == "unresolved"
    )
    summary_report_count = sum(
        1 for report in reports if report.get("report_type") == "summary_report"
    )
    generation_package_mismatch_count = sum(
        1
        for report in reports
        if isinstance(report.get("generation_source"), dict)
        and report["generation_source"].get("status") == "package_mismatch"
    )
    image_region_count = sum(
        _int_or_none(report.get("summary", {}).get("image_region_count")) or 0
        for report in reports
        if isinstance(report.get("summary"), dict)
    )
    package_fingerprints: dict[str, dict[str, Any]] = {}
    for report in reports:
        package = (
            report.get("package") if isinstance(report.get("package"), dict) else {}
        )
        fingerprint = (
            package.get("content_fingerprint") if isinstance(package, dict) else None
        )
        package_dir = _normalize_text(report.get("package_dir"))
        if isinstance(fingerprint, dict) and package_dir:
            package_fingerprints[package_dir] = {
                "package_dir": package_dir,
                "retailer": package.get("retailer"),
                "category_key": package.get("category_key"),
                "category_label": package.get("category_label"),
                "content_sha256": fingerprint.get("content_sha256"),
                "file_count": fingerprint.get("file_count"),
            }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "report_count": len(reports),
            "pass_count": pass_count,
            "pass_with_warnings_count": warning_count,
            "fail_count": fail_count,
            "not_validated_count": not_validated_count,
            "unresolved_package_count": unresolved_package_count,
            "summary_report_count": summary_report_count,
            "generation_package_mismatch_count": generation_package_mismatch_count,
            "image_region_count": image_region_count,
        },
        "package_fingerprints": [
            package_fingerprints[package_dir]
            for package_dir in sorted(package_fingerprints)
        ],
        "reports": reports,
    }


def _launch_validation_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    scope_note = _normalize_text(payload.get("scope_note")) or (
        "This validator checks deterministic launch-package claims against the final PDF."
    )
    reading_quality = (
        payload.get("reading_quality")
        if isinstance(payload.get("reading_quality"), dict)
        else {}
    )
    reading_summary = (
        reading_quality.get("summary")
        if isinstance(reading_quality.get("summary"), dict)
        else {}
    )
    lines = [
        f"# Launch Report Validation: `{Path(payload['pdf_path']).name}`",
        "",
        f"Status: **{payload['status']}**",
        "",
        "## Summary",
        "",
        f"- Verified claims: `{summary.get('verified_count', 0)}`",
        f"- Contradicted claims: `{summary.get('contradicted_count', 0)}`",
        f"- Partially backed claims: `{summary.get('partially_backed_count', 0)}`",
        f"- Weakly backed claims: `{summary.get('weakly_backed_count', 0)}`",
        f"- Unresolved items: `{summary.get('unresolved_count', 0)}`",
        f"- Non-claim text units: `{summary.get('non_claim_count', 0)}`",
        f"- OCR/layout mapping issues: `{summary.get('mapping_issue_count', 0)}`",
        f"- Image regions: `{summary.get('image_region_count', 0)}`",
        f"- Slides visited: `{summary.get('slide_count', 0)}`",
        f"- Reading quality: `{reading_quality.get('status', 'unknown')}`",
        "",
        "## Resolver",
        "",
        f"- Package: `{payload.get('package_dir', 'N/A')}`",
        f"- Resolver status: `{payload['resolver'].get('status', 'unknown')}`",
        "",
    ]
    package = payload.get("package") if isinstance(payload.get("package"), dict) else {}
    fingerprint = (
        package.get("content_fingerprint") if isinstance(package, dict) else {}
    )
    if isinstance(fingerprint, dict) and fingerprint.get("content_sha256"):
        lines.extend(
            [
                "## Package Fingerprint",
                "",
                f"- Content SHA256: `{fingerprint.get('content_sha256')}`",
                f"- Files hashed: `{fingerprint.get('file_count', 0)}`",
                "",
            ]
        )
    generation_source = (
        payload.get("generation_source")
        if isinstance(payload.get("generation_source"), dict)
        else {}
    )
    if generation_source:
        lines.extend(
            [
                "## Report Generation Source",
                "",
                f"- Status: `{generation_source.get('status', 'unknown')}`",
            ]
        )
        sidecar_path = _normalize_text(generation_source.get("sidecar_path"))
        if sidecar_path:
            lines.append(f"- Sidecar: `{sidecar_path}`")
        generation_hash = _normalize_text(
            generation_source.get("generation_package_content_sha256")
        )
        current_hash = _normalize_text(
            generation_source.get("current_package_content_sha256")
        )
        if generation_hash:
            lines.append(f"- Generation package SHA256: `{generation_hash}`")
        if current_hash:
            lines.append(f"- Current package SHA256: `{current_hash}`")
        if generation_source.get("package_fingerprint_matches_current") is False:
            lines.append(
                "- Warning: generation package fingerprint differs from current package fingerprint."
            )
        lines.append("")

    calculation_summary = (
        payload.get("calculation_summary")
        if isinstance(payload.get("calculation_summary"), list)
        else []
    )
    if calculation_summary:
        lines.extend(["## Calculation Helpers", ""])
        for helper in calculation_summary:
            if not isinstance(helper, dict):
                continue
            helper_id = _normalize_text(helper.get("helper_id")) or "unknown"
            status = _normalize_text(helper.get("status")) or "unknown"
            row_count = helper.get("row_count", 0)
            lines.append(f"- `{helper_id}`: `{status}`, rows `{row_count}`")
            reason = _normalize_text(helper.get("reason"))
            if reason:
                lines.append(f"  Reason: {reason}")
        lines.append("")

    if reading_quality:
        lines.extend(
            [
                "## Reading Quality",
                "",
                f"- Status: `{reading_quality.get('status', 'unknown')}`",
                f"- Slides ok: `{reading_summary.get('ok_slide_count', 0)}`",
                f"- Slides with warnings: `{reading_summary.get('warning_slide_count', 0)}`",
                f"- Slides with poor extraction: `{reading_summary.get('poor_slide_count', 0)}`",
            ]
        )
        reasons = (
            reading_quality.get("reasons")
            if isinstance(reading_quality.get("reasons"), list)
            else []
        )
        for reason in reasons[:4]:
            lines.append(f"- Note: {reason}")
        flagged_slides = (
            reading_quality.get("flagged_slides")
            if isinstance(reading_quality.get("flagged_slides"), list)
            else []
        )
        for slide in flagged_slides[:8]:
            if not isinstance(slide, dict):
                continue
            slide_number = slide.get("slide_number", "?")
            lines.append(
                f"- Slide `{slide_number}`: `{slide.get('status', 'unknown')}`"
            )
            slide_reasons = (
                slide.get("reasons") if isinstance(slide.get("reasons"), list) else []
            )
            if slide_reasons:
                lines.append(
                    f"  Reasons: {'; '.join(str(reason) for reason in slide_reasons)}"
                )
        remaining_flagged = len(flagged_slides) - 8
        if remaining_flagged > 0:
            lines.append(f"- ... and `{remaining_flagged}` more flagged slides")
        lines.append("")

    llm_review = (
        payload.get("llm_review") if isinstance(payload.get("llm_review"), dict) else {}
    )
    if llm_review:
        lines.extend(
            [
                "## LLM Advisory Review",
                "",
                f"- Status: `{llm_review.get('status', 'unknown')}`",
                f"- Effect on deterministic status: `{llm_review.get('effect_on_validation_status', 'none')}`",
            ]
        )
        review_summary = _normalize_text(llm_review.get("summary"))
        if review_summary:
            lines.append(f"- Summary: {review_summary}")
        review_items = (
            llm_review.get("items") if isinstance(llm_review.get("items"), list) else []
        )
        for item in review_items[:8]:
            if not isinstance(item, dict):
                continue
            slide_number = item.get("slide_number")
            slide_prefix = f"Slide `{slide_number}` " if slide_number else ""
            lines.append(
                f"- {slide_prefix}`{item.get('llm_category', 'unknown')}` / `{item.get('recommended_action', 'unknown')}`: {_truncate_text(item.get('claim_text'), limit=160) or '(no text)'}"
            )
            rationale = _normalize_text(item.get("rationale"))
            if rationale:
                lines.append(f"  Rationale: {rationale}")
        helper_suggestions = (
            llm_review.get("helper_suggestions")
            if isinstance(llm_review.get("helper_suggestions"), list)
            else []
        )
        for suggestion in helper_suggestions[:6]:
            if not isinstance(suggestion, dict):
                continue
            lines.append(
                f"- Helper suggestion `{suggestion.get('claim_family', 'unknown')}`: {_truncate_text(suggestion.get('claim_text'), limit=160)}"
            )
        lines.append("")

    contradicted = [
        claim
        for claim in payload.get("claims", [])
        if claim["status"] == "contradicted"
    ]
    if contradicted:
        lines.extend(["## Contradictions", ""])
        for claim in contradicted[:12]:
            lines.append(
                f"- Slide `{claim.get('slide_number', '?')}` `{claim.get('claim_family', 'unknown')}`: {_truncate_text(claim.get('claim_text'), limit=180)}"
            )
            if claim.get("entity"):
                lines.append(f"  Entity: `{claim['entity']}`")
            details = claim.get("details") or {}
            reasons = details.get("reasons") if isinstance(details, dict) else None
            if reasons:
                lines.append(
                    f"  Reasons: {'; '.join(str(reason) for reason in reasons)}"
                )
            observed_values = (
                details.get("observed_values") if isinstance(details, dict) else None
            )
            if isinstance(observed_values, dict) and observed_values:
                lines.append(
                    f"  Observed: `{json.dumps(observed_values, ensure_ascii=False, sort_keys=True)}`"
                )
            package_values = (
                details.get("package_values") if isinstance(details, dict) else None
            )
            if isinstance(package_values, dict) and package_values:
                lines.append(
                    f"  Package: `{json.dumps(package_values, ensure_ascii=False, sort_keys=True)}`"
                )
            candidate_evaluations = (
                details.get("candidate_evaluations")
                if isinstance(details, dict)
                else None
            )
            if isinstance(candidate_evaluations, list) and candidate_evaluations:
                for candidate in candidate_evaluations[:2]:
                    if not isinstance(candidate, dict):
                        continue
                    candidate_file = _normalize_text(candidate.get("file")) or "unknown"
                    candidate_values = candidate.get("package_values")
                    candidate_reasons = candidate.get("reasons")
                    if isinstance(candidate_values, dict) and candidate_values:
                        lines.append(
                            f"  Candidate `{candidate_file}`: `{json.dumps(candidate_values, ensure_ascii=False, sort_keys=True)}`"
                        )
                    if isinstance(candidate_reasons, list) and candidate_reasons:
                        lines.append(
                            f"  Candidate reasons: {'; '.join(str(reason) for reason in candidate_reasons)}"
                        )
        remaining = len(contradicted) - 12
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")

    partially_backed = [
        claim
        for claim in payload.get("claims", [])
        if claim["status"] == "partially_backed"
    ]
    if partially_backed:
        lines.extend(["## Partial Support", ""])
        for claim in partially_backed[:12]:
            lines.append(
                f"- Slide `{claim.get('slide_number', '?')}` `{claim.get('claim_family', 'unknown')}`: {_truncate_text(claim.get('claim_text'), limit=180)}"
            )
            details = claim.get("details") or {}
            reasons = details.get("reasons") if isinstance(details, dict) else None
            if reasons:
                lines.append(
                    f"  Reasons: {'; '.join(str(reason) for reason in reasons)}"
                )
            package_values = (
                details.get("package_values") if isinstance(details, dict) else None
            )
            if isinstance(package_values, dict) and package_values:
                lines.append(
                    f"  Package: `{json.dumps(package_values, ensure_ascii=False, sort_keys=True)}`"
                )
        remaining = len(partially_backed) - 12
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")

    if payload.get("unresolved"):
        lines.extend(["## Unresolved", ""])
        for claim in payload["unresolved"][:16]:
            slide_number = claim.get("slide_number")
            prefix = f"Slide `{slide_number}` " if slide_number is not None else ""
            lines.append(
                f"- {prefix}`{claim.get('claim_family', 'unknown')}`: {_truncate_text(claim.get('claim_text'), limit=180) or '(no text)'}"
            )
            details = claim.get("details") or {}
            message = (
                _normalize_text(details.get("message"))
                if isinstance(details, dict)
                else ""
            )
            if message:
                lines.append(f"  Note: {message}")
        remaining = len(payload["unresolved"]) - 16
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")

    if payload.get("image_regions"):
        lines.extend(["## Image Regions", ""])
        for region in payload["image_regions"][:12]:
            slide_number = region.get("slide_number")
            prefix = f"Slide `{slide_number}` " if slide_number is not None else ""
            details = region.get("details") or {}
            message = (
                _normalize_text(details.get("message"))
                if isinstance(details, dict)
                else ""
            )
            lines.append(
                f"- {prefix}`figure_region`: {message or 'image region preserved without OCR interpretation'}"
            )
        remaining = len(payload["image_regions"]) - 12
        if remaining > 0:
            lines.append(f"- ... and `{remaining}` more")
        lines.append("")

    if payload.get("claims"):
        verified = [
            claim for claim in payload["claims"] if claim["status"] == "verified"
        ]
        verified_by_family: dict[str, int] = {}
        for claim in verified:
            family = _normalize_text(claim.get("claim_family")) or "unknown"
            verified_by_family[family] = verified_by_family.get(family, 0) + 1
        lines.extend(["## Verified Families", ""])
        for family, count in sorted(verified_by_family.items()):
            lines.append(f"- `{family}`: `{count}`")
        lines.append("")

    lines.extend(["## Scope", "", scope_note, ""])
    return "\n".join(lines)


def _launch_batch_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Launch Report Batch Validation",
        "",
        "## Summary",
        "",
        f"- Reports: `{summary['report_count']}`",
        f"- Pass: `{summary['pass_count']}`",
        f"- Pass with warnings: `{summary['pass_with_warnings_count']}`",
        f"- Fail: `{summary['fail_count']}`",
        f"- Not validated: `{summary.get('not_validated_count', 0)}`",
        f"- Missing package match: `{summary['unresolved_package_count']}`",
        f"- Summary reports: `{summary.get('summary_report_count', 0)}`",
        f"- Generation/current package mismatches: `{summary.get('generation_package_mismatch_count', 0)}`",
        f"- Image regions: `{summary.get('image_region_count', 0)}`",
        "",
        "## Reports",
        "",
    ]
    for report in payload["reports"]:
        lines.append(
            f"- `{Path(report['pdf_path']).name}`: `{report['status']}` "
            f"(verified `{report['summary']['verified_count']}`, contradicted `{report['summary']['contradicted_count']}`, unresolved `{report['summary']['unresolved_count']}`, images `{report['summary'].get('image_region_count', 0)}`)"
        )
    lines.append("")
    package_fingerprints = (
        payload.get("package_fingerprints")
        if isinstance(payload.get("package_fingerprints"), list)
        else []
    )
    if package_fingerprints:
        lines.extend(["## Package Fingerprints", ""])
        for item in package_fingerprints:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('category_key', 'unknown')}` / `{item.get('retailer', 'unknown')}`: "
                f"`{item.get('content_sha256', 'unknown')}`"
            )
        lines.append("")
    return "\n".join(lines)


def write_launch_report_validation_artifacts(
    *,
    payload: dict[str, Any],
    output_prefix: Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts for one validated report."""

    json_path = output_prefix.with_suffix(".validation.json")
    md_path = output_prefix.with_suffix(".validation.md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_launch_validation_markdown(payload), encoding="utf-8")
    return json_path, md_path


def write_launch_report_batch_artifacts(
    *,
    payload: dict[str, Any],
    output_prefix: Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts for a batch validation run."""

    json_path = output_prefix.with_suffix(".validation.json")
    md_path = output_prefix.with_suffix(".validation.md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_launch_batch_markdown(payload), encoding="utf-8")
    return json_path, md_path
