from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, NamedTuple, Sequence

from .models import (
    BatchParseResult,
    FilterObservation,
    FilterSurface,
    ListingObservation,
    SitemapObservation,
)
from .postgres_compat import PostgresCompatConnection, require_pdp_postgres_url

SCHEMA_VERSION = 16

PARENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS parent_products (
    retailer TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    pdp_url TEXT,
    brand_raw TEXT,
    brand_normalized TEXT,
    title_raw TEXT,
    title_normalized TEXT,
    series_label_raw TEXT,
    category_path TEXT,
    has_color_selector INTEGER NOT NULL,
    qa_flags TEXT,
    extras TEXT,
    batch_generated_at TEXT NOT NULL,
    discovered_at TEXT,
    last_seen_at TEXT,
    discontinued_at TEXT,
    PRIMARY KEY (retailer, parent_product_id)
)
"""

VARIANT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS variants (
    retailer TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    shade_name_raw TEXT,
    shade_name_normalized TEXT,
    size_text_raw TEXT,
    price_raw TEXT,
    price REAL,
    currency TEXT,
    barcode TEXT,
    swatch_image_url TEXT,
    hero_image_url TEXT,
    availability TEXT,
    source_index INTEGER,
    qa_flags TEXT,
    extras TEXT,
    batch_generated_at TEXT NOT NULL,
    PRIMARY KEY (retailer, variant_id),
    FOREIGN KEY (retailer, parent_product_id) REFERENCES parent_products(retailer, parent_product_id)
)
"""

RUN_LOGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS run_logs (
    run_id TEXT PRIMARY KEY,
    retailer TEXT NOT NULL,
    profile TEXT NOT NULL,
    parsed_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    summary_json TEXT
)
"""

FAILURES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_failures (
    run_id TEXT NOT NULL,
    retailer TEXT NOT NULL,
    profile TEXT NOT NULL,
    pdp_url TEXT NOT NULL,
    status_code INTEGER,
    message TEXT,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (run_id, retailer, pdp_url)
)
"""

ATTRIBUTE_VALUES_TABLE_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table_name} (
    retailer TEXT NOT NULL,
    row_type TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL DEFAULT '',
    category_key TEXT NOT NULL DEFAULT '',
    attribute_id TEXT NOT NULL,
    attribute_label TEXT,
    value TEXT,
    oov_candidate TEXT,
    note TEXT,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (
        retailer,
        row_type,
        parent_product_id,
        variant_id,
        category_key,
        attribute_id,
        source
    )
)
"""
ATTRIBUTE_VALUES_TABLE_SQL = ATTRIBUTE_VALUES_TABLE_TEMPLATE.format(
    table_name="pdp_attribute_values"
)
FILTER_ATTRIBUTE_SOURCE = "retailer_filter"
ATTRIBUTE_MULTI_VALUE_SEPARATOR = " | "
_GENERIC_FLAVOR_TOKENS = frozenset(
    {
        "flavor_variety",
        "meat",
        "poultry",
        "fish",
        "seafood",
        "fruits_vegetables",
        "herbs_spices",
    }
)
_SPECIFIC_POULTRY_FLAVOR_TOKENS = frozenset(
    {"chicken", "turkey", "duck", "quail", "guinea_fowl", "goose", "pheasant"}
)
_SPECIFIC_FISH_FLAVOR_TOKENS = frozenset(
    {
        "anchovies",
        "basa",
        "cod",
        "crab",
        "mackerel",
        "ocean_fish",
        "pollock",
        "saba",
        "salmon",
        "sardine",
        "sea_bass",
        "shrimp",
        "tilapia",
        "trout",
        "tuna",
        "whitefish",
    }
)
_SPECIFIC_PRODUCE_FLAVOR_TOKENS = frozenset({"pumpkin", "sweet_potato", "carrot"})
_SPECIFIC_HERB_SPICE_FLAVOR_TOKENS = frozenset({"catnip"})
_FILTER_ATTRIBUTE_FAMILY_ALIASES = {
    "age_range_description": "lifestage",
    "allergen_information": "special_diet",
    "animal_food_diet_type": "special_diet",
    "brand": "brand",
    "brands": "brand",
    "container_type": "packaging_type",
    "count": "package_count",
    "diet_type": "special_diet",
    "flavor": "flavor",
    "flavors": "flavor",
    "flavour": "flavor",
    "flavours": "flavor",
    "food_texture": "food_texture",
    "food_textures": "food_texture",
    "health_feature": "health_feature",
    "health_features": "health_feature",
    "item_form": "food_texture",
    "life_stage": "lifestage",
    "life_stages": "lifestage",
    "lifestage": "lifestage",
    "nutrient_claims": "special_diet",
    "package": "package_count",
    "package_count": "package_count",
    "package_type": "packaging_type",
    "packaging": "packaging_type",
    "packaging_type": "packaging_type",
    "pet_type": "pet type",
    "special_diet": "special_diet",
    "special_diets": "special_diet",
}
_FILTER_VALUE_ALIASES_BY_FAMILY = {
    "flavor": {
        "fish": "seafood_fish",
        "seafood": "seafood_fish",
        "seafood_and_fish": "seafood_fish",
        "seafood_fish": "seafood_fish",
        "fruits_and_vegetables": "fruits_vegetables",
        "herbs_and_spices": "herbs_spices",
    },
    "food_texture": {
        "chunk": "chunks_in_gravy",
        "chunks": "chunks_in_gravy",
        "chunks_cuts": "chunks_in_gravy",
        "cut": "chunks_in_gravy",
        "cuts": "chunks_in_gravy",
        "cuts_in_gravy": "chunks_in_gravy",
        "gravy": "chunks_in_gravy",
        "pate": "pate",
        "pat": "pate",
        "paté": "pate",
        "shred": "shredded",
        "shredded": "shredded",
        "shreds": "shredded",
        "flaked": "flaked",
        "minced": "minced",
    },
    "packaging_type": {
        "bags": "bag",
        "cans": "can",
        "carton": "box",
        "cartons": "box",
        "cups": "cup",
        "pouches": "pouch",
        "trays": "tray",
        "tubs": "tub",
    },
    "lifestage": {
        "all_life_stage": "all_lifestages",
        "all_life_stages": "all_lifestages",
        "all_lifestage": "all_lifestages",
        "all_lifestages": "all_lifestages",
        "all_stages": "all_lifestages",
        "baby": "kitten",
    },
    "special_diet": {
        "allergen_free": "allergen_free",
        "corn_free": "corn_free",
        "dairy_free": "dairy_free",
        "grain_free": "grain_free",
        "gluten_free": "gluten_free",
        "high_protein": "high_protein",
        "limited_ingredient": "limited_ingredient_diet",
        "limited_ingredient_diet": "limited_ingredient_diet",
        "no_corn_no_wheat_no_soy": "no_corn_no_wheat_no_soy",
        "non_gmo": "non_gmo",
        "veterinary_diet": "veterinary_diet",
    },
    "health_feature": {
        "sensitive_digestion": "sensitive_digestion",
        "pet_skin_and_coat_health": "skin_coat",
        "skin_and_coat": "skin_coat",
        "skin_coat": "skin_coat_health",
        "skin_coat_health": "skin_coat_health",
    },
}
_FILTER_VALUE_FAMILY_OVERRIDES_BY_CATEGORY = {
    "wet_cat_food": {
        "flavor": {
            "chunk": "food_texture",
            "chunks": "food_texture",
            "cut": "food_texture",
            "cuts": "food_texture",
        },
    },
}
_FILTER_VALUE_SKIP_TOKENS_BY_CATEGORY = {
    "wet_cat_food": {
        "flavor": {
            "dry",
            "dry_food",
            "dry_kibble",
            "kibble",
        },
    },
}
_FILTER_FAMILY_SKIP_BY_RETAILER_CATEGORY = {
    ("amazon", "wet_cat_food"): {"package_count"},
}


@lru_cache(maxsize=64)
def _taxonomy_attribute_lookup(
    category_key: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str]]]:
    normalized_category = _canonical_filter_token(category_key)
    if not normalized_category:
        return {}, {}, {}
    path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "attribute_taxonomy"
        / "categories"
        / f"{normalized_category}.json"
    )
    if not path.is_file():
        return {}, {}, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}, {}

    attr_aliases: dict[str, str] = {}
    attr_labels: dict[str, str] = {}
    value_aliases_by_attr: dict[str, dict[str, str]] = {}
    attributes = payload.get("attributes", []) if isinstance(payload, dict) else []
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        attr_id = str(attribute.get("id") or "").strip()
        if not attr_id:
            continue
        attr_label = str(attribute.get("label") or attr_id).strip() or attr_id
        attr_labels[attr_id] = attr_label
        for alias in (attr_id, attr_label):
            token = _canonical_filter_token(alias)
            if token:
                attr_aliases[token] = attr_id

        value_aliases: dict[str, str] = {}
        for node in attribute.get("nodes", []) or []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            if not node_id or node_id in {"unknown", "other"}:
                continue
            for alias in (
                node_id,
                node.get("label"),
                *(node.get("synonyms") or []),
            ):
                token = _canonical_filter_token(alias)
                if token:
                    value_aliases[token] = node_id
        if value_aliases:
            value_aliases_by_attr[attr_id] = value_aliases
    return attr_aliases, attr_labels, value_aliases_by_attr


def _canonical_filter_token(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _canonical_filter_attribute_family(
    filter_family: str,
    *,
    category_key: str | None = None,
    retailer: str | None = None,
) -> str:
    key = _canonical_filter_token(filter_family)
    if str(retailer or "").strip().casefold() == "amazon" and key == "health_feature":
        return "special_diet"
    attr_aliases, _, _ = _taxonomy_attribute_lookup(str(category_key or ""))
    return attr_aliases.get(key) or _FILTER_ATTRIBUTE_FAMILY_ALIASES.get(key, key)


def _filter_attribute_label(attribute_id: str, category_key: str | None = None) -> str:
    _, attr_labels, _ = _taxonomy_attribute_lookup(str(category_key or ""))
    return attr_labels.get(attribute_id, attribute_id.replace("_", " "))


def _filter_attribute_group_values(
    filter_family: str,
    filter_value: str,
    *,
    category_key: str | None = None,
    retailer: str | None = None,
) -> list[tuple[str, str]]:
    category_token = _canonical_filter_token(category_key)
    base_family = _canonical_filter_attribute_family(
        filter_family,
        category_key=category_key,
        retailer=retailer,
    )
    retailer_token = _canonical_filter_token(retailer)
    if base_family in _FILTER_FAMILY_SKIP_BY_RETAILER_CATEGORY.get(
        (retailer_token, category_token), set()
    ):
        return []
    family_overrides = _FILTER_VALUE_FAMILY_OVERRIDES_BY_CATEGORY.get(
        category_token, {}
    ).get(base_family, {})
    skip_tokens = _FILTER_VALUE_SKIP_TOKENS_BY_CATEGORY.get(category_token, {}).get(
        base_family, set()
    )
    grouped: list[tuple[str, str]] = []
    for raw_part in str(filter_value or "").split(ATTRIBUTE_MULTI_VALUE_SEPARATOR):
        raw_value = raw_part.strip()
        value_token = _canonical_filter_token(raw_value)
        if not raw_value or not value_token or value_token in skip_tokens:
            continue
        grouped.append((family_overrides.get(value_token, base_family), raw_value))
    return grouped


def _canonical_filter_attribute_value(
    filter_family: str,
    value: str,
    *,
    category_key: str | None = None,
) -> str:
    key = _canonical_filter_token(value)
    if not key:
        return ""
    if filter_family == "package_count":
        number_match = re.search(r"\d+", key)
        if number_match:
            count_value = int(number_match.group(0))
            if count_value <= 6:
                return "count_6_or_less"
            if count_value <= 12:
                return "count_7_12"
            if count_value <= 24:
                return "count_13_24"
            return "count_25_plus"
    family_aliases = _FILTER_VALUE_ALIASES_BY_FAMILY.get(filter_family, {})
    alias_value = family_aliases.get(key, key)
    _, _, taxonomy_value_aliases = _taxonomy_attribute_lookup(str(category_key or ""))
    value_aliases = taxonomy_value_aliases.get(filter_family, {})
    return value_aliases.get(alias_value) or value_aliases.get(key) or alias_value


def _normalize_filter_attribute_values(
    filter_family: str,
    values: Iterable[str],
    *,
    category_key: str | None = None,
    retailer: str | None = None,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    canonical_family = _canonical_filter_attribute_family(
        filter_family,
        category_key=category_key,
        retailer=retailer,
    )
    for raw_value in values:
        raw_parts = str(raw_value or "").split(ATTRIBUTE_MULTI_VALUE_SEPARATOR)
        for raw_part in raw_parts:
            value = _canonical_filter_attribute_value(
                canonical_family,
                raw_part,
                category_key=category_key,
            )
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
    if canonical_family != "flavor" or not normalized:
        return normalized

    value_set = set(normalized)
    has_specific = any(value not in _GENERIC_FLAVOR_TOKENS for value in value_set)
    drop_values: set[str] = set()
    if "flavor_variety" in value_set and has_specific:
        drop_values.add("flavor_variety")
    if "meat" in value_set and has_specific:
        drop_values.add("meat")
    if "poultry" in value_set and value_set & _SPECIFIC_POULTRY_FLAVOR_TOKENS:
        drop_values.add("poultry")
    if "seafood" in value_set and value_set & _SPECIFIC_FISH_FLAVOR_TOKENS:
        drop_values.add("seafood")
    if "fish" in value_set and value_set & _SPECIFIC_FISH_FLAVOR_TOKENS:
        drop_values.add("fish")
    if "fruits_vegetables" in value_set and value_set & _SPECIFIC_PRODUCE_FLAVOR_TOKENS:
        drop_values.add("fruits_vegetables")
    if "herbs_spices" in value_set and value_set & _SPECIFIC_HERB_SPICE_FLAVOR_TOKENS:
        drop_values.add("herbs_spices")

    cleaned = [value for value in normalized if value not in drop_values]
    return cleaned or normalized


ATTRIBUTE_VALUE_COVERAGE_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS pdp_attribute_value_coverage AS
SELECT
    retailer,
    row_type,
    COALESCE(category_key, '') AS category_key,
    source,
    COUNT(*) AS decision_rows,
    SUM(
        CASE
            WHEN value IS NULL
              OR TRIM(value) = ''
              OR LOWER(TRIM(value)) IN (
                  'n/a',
                  'na',
                  'none',
                  'unknown',
                  'n/a (not stated)',
                  'not stated'
              )
            THEN 1 ELSE 0
        END
    ) AS no_value_rows,
    SUM(
        CASE
            WHEN LOWER(TRIM(COALESCE(value, ''))) = 'not in taxonomy'
            THEN 1 ELSE 0
        END
    ) AS taxonomy_miss_rows,
    SUM(
        CASE
            WHEN value IS NOT NULL
              AND TRIM(value) <> ''
              AND LOWER(TRIM(value)) NOT IN (
                  'n/a',
                  'na',
                  'none',
                  'unknown',
                  'n/a (not stated)',
                  'not stated',
                  'not in taxonomy'
              )
            THEN 1 ELSE 0
        END
    ) AS valued_rows
FROM pdp_attribute_values
GROUP BY
    retailer,
    row_type,
    COALESCE(category_key, ''),
    source
"""

CANONICAL_PRODUCTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS canonical_products (
    canonical_id TEXT PRIMARY KEY,
    brand_normalized TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    retailer TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    captured_at TEXT NOT NULL
)
"""

ATTRIBUTE_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_attribute_cache (
    name TEXT PRIMARY KEY,
    payload BLOB NOT NULL,
    generated_at TEXT NOT NULL
)
"""

ATTRIBUTE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_attribute_audit (
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    row_type TEXT,
    retailer TEXT,
    parent_product_id TEXT,
    variant_id TEXT,
    attribute_id TEXT,
    value TEXT,
    decision_rule TEXT,
    evidence_json TEXT,
    category_key TEXT
)
"""

ATTRIBUTE_RESOLUTION_LEDGER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_attribute_resolution_ledger (
    row_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    recorded_at TEXT,
    step TEXT,
    source TEXT,
    decision_rule TEXT,
    row_type TEXT,
    retailer TEXT,
    parent_product_id TEXT,
    variant_id TEXT,
    canonical_id TEXT,
    category_key TEXT,
    attribute_id TEXT,
    value TEXT,
    confidence REAL,
    evidence_url TEXT
)
"""

ATTRIBUTE_RESOLUTION_CONSENSUS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_attribute_resolution_consensus (
    row_type TEXT NOT NULL,
    retailer TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    category_key TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    consensus_value TEXT,
    support_runs INTEGER,
    total_runs INTEGER,
    agreement_rate REAL,
    step_count INTEGER,
    supporting_steps_json TEXT,
    certainty_class TEXT,
    max_confidence REAL,
    last_seen_at TEXT,
    last_recorded_at TEXT,
    PRIMARY KEY (
        row_type,
        retailer,
        parent_product_id,
        variant_id,
        canonical_id,
        category_key,
        attribute_id
    )
)
"""

RETAILER_LISTING_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retailer_listing_observations (
    crawl_ts TEXT NOT NULL,
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    sort_mode TEXT NOT NULL,
    page INTEGER NOT NULL,
    position INTEGER NOT NULL,
    pdp_url TEXT NOT NULL,
    parent_product_id TEXT,
    product_name TEXT,
    brand TEXT,
    has_new_badge INTEGER NOT NULL DEFAULT 0,
    listing_url TEXT,
    PRIMARY KEY (
        crawl_ts,
        retailer,
        category_key,
        source_surface,
        sort_mode,
        page,
        position,
        pdp_url
    )
)
"""

RETAILER_FILTER_SURFACES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retailer_filter_surfaces (
    crawl_ts TEXT NOT NULL,
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    filter_family TEXT NOT NULL,
    filter_value TEXT NOT NULL,
    filter_url TEXT NOT NULL,
    filter_label TEXT,
    PRIMARY KEY (
        crawl_ts,
        retailer,
        category_key,
        filter_family,
        filter_value,
        filter_url
    )
)
"""

RETAILER_FILTER_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retailer_filter_observations (
    crawl_ts TEXT NOT NULL,
    retailer TEXT NOT NULL,
    category_key TEXT NOT NULL,
    filter_family TEXT NOT NULL,
    filter_value TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    pdp_url TEXT NOT NULL,
    parent_product_id TEXT,
    page INTEGER NOT NULL,
    position INTEGER NOT NULL,
    listing_url TEXT,
    PRIMARY KEY (
        crawl_ts,
        retailer,
        category_key,
        filter_family,
        filter_value,
        pdp_url,
        page,
        position
    )
)
"""

RETAILER_SITEMAP_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retailer_sitemap_observations (
    crawl_ts TEXT NOT NULL,
    retailer TEXT NOT NULL,
    sitemap_source TEXT NOT NULL,
    url TEXT NOT NULL,
    lastmod TEXT,
    url_type TEXT NOT NULL,
    PRIMARY KEY (
        crawl_ts,
        retailer,
        sitemap_source,
        url
    )
)
"""

EXPLICIT_RULE_CANDIDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_explicit_rule_candidates (
    candidate_id TEXT PRIMARY KEY,
    category_key TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    proposed_value TEXT NOT NULL,
    pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    sample_snippets_json TEXT NOT NULL DEFAULT '[]',
    estimated_conflict_rate REAL,
    reviewed_samples INTEGER,
    precision_estimate REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_note TEXT,
    rejection_reason TEXT,
    reviewer TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

EXPLICIT_RULE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_explicit_rules_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    candidate_id TEXT,
    rule_id TEXT,
    actor TEXT,
    details_json TEXT
)
"""

EXPLICIT_RULE_CONFIG_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_explicit_rule_config_versions (
    version TEXT PRIMARY KEY,
    published_at TEXT NOT NULL,
    actor TEXT,
    note TEXT,
    config_json TEXT NOT NULL,
    diff_summary_json TEXT
)
"""

TAXONOMY_GOVERNANCE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_taxonomy_governance_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    category_key TEXT,
    attribute_id TEXT,
    leaf_id TEXT,
    details_json TEXT
)
"""

TAXONOMY_CONFIG_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_taxonomy_config_versions (
    version TEXT PRIMARY KEY,
    published_at TEXT NOT NULL,
    actor TEXT,
    note TEXT,
    config_json TEXT NOT NULL,
    diff_summary_json TEXT
)
"""

TAXONOMY_DRAFTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_taxonomy_drafts (
    draft_name TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT,
    last_queue_item_id TEXT
)
"""

DETERMINISTIC_POLICY_DRAFTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_deterministic_policy_drafts (
    draft_name TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT
)
"""

DETERMINISTIC_POLICY_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_deterministic_policy_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    details_json TEXT
)
"""

DETERMINISTIC_POLICY_CONFIG_VERSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_deterministic_policy_config_versions (
    version TEXT PRIMARY KEY,
    published_at TEXT NOT NULL,
    actor TEXT,
    note TEXT,
    config_json TEXT NOT NULL,
    diff_summary_json TEXT
)
"""

REVIEW_QUEUE_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS review_queue_items (
    queue_item_id TEXT PRIMARY KEY,
    candidate_domain TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    aggregated_row_ref TEXT,
    run_id TEXT,
    evidence_signature TEXT,
    origin TEXT NOT NULL,
    status TEXT NOT NULL,
    category_key TEXT,
    attribute_id TEXT,
    value_id TEXT,
    title TEXT NOT NULL,
    short_reason TEXT,
    priority_score REAL,
    confidence_level TEXT,
    decision_ease TEXT,
    support_product_count INTEGER,
    support_retailer_count INTEGER,
    reviewer TEXT,
    decision_reason TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

EXPLICIT_PRECISION_METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pdp_explicit_precision_metrics (
    run_id TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    category_key TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    explicit_positive_count INTEGER NOT NULL,
    deterministic_match_on_explicit INTEGER NOT NULL,
    llm_match_on_explicit INTEGER NOT NULL,
    deterministic_precision_proxy REAL NOT NULL,
    llm_precision_proxy REAL NOT NULL,
    PRIMARY KEY (run_id, category_key, attribute_id)
)
"""

STAGE_ATTRIBUTE_TABLE_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table_name} (
    retailer TEXT NOT NULL,
    row_type TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL DEFAULT '',
    category_key TEXT NOT NULL DEFAULT '',
    attribute_id TEXT NOT NULL,
    attribute_label TEXT,
    value TEXT,
    oov_candidate TEXT,
    note TEXT,
    updated_at TEXT NOT NULL,
    extras_json TEXT,
    PRIMARY KEY (
        retailer,
        row_type,
        parent_product_id,
        variant_id,
        category_key,
        attribute_id
    )
)
"""

ATTR_STAGE_TABLES: dict[str, str] = {
    "deterministic_explicit": "pdp_attributes_deterministic_explicit",
    "deterministic": "pdp_attributes_deterministic",
    "llm": "pdp_attributes_llm",
}

_STATUS_RE = re.compile(r"http_status=(\d{3})")


@dataclass(slots=True)
class FailureRecord:
    url: str
    status_code: int | None
    message: str | None


@dataclass(slots=True)
class AttributeValueRecord:
    retailer: str
    row_type: str
    parent_product_id: str
    variant_id: str
    attribute_id: str
    attribute_label: str | None
    value: str | None
    oov_candidate: str | None
    note: str | None
    source: str
    updated_at: str
    category_key: str = ""


@dataclass(slots=True)
class AttributeAuditRecord:
    timestamp: str
    source: str
    row_type: str | None
    retailer: str | None
    parent_product_id: str | None
    variant_id: str | None
    attribute_id: str | None
    value: str | None
    decision_rule: str | None
    evidence_json: str | None
    category_key: str | None


class AttributeMappingIdentity(NamedTuple):
    """Exact database identity for one logical source mapping."""

    source: str
    retailer: str
    row_type: str
    parent_product_id: str
    variant_id: str
    category_key: str
    base_attribute_id: str


class AttributeMappingStateRow(NamedTuple):
    """One persisted row in a mapping compare-and-swap state."""

    attribute_id: str
    attribute_label: str | None
    value: str | None
    oov_candidate: str | None
    note: str | None
    updated_at: str


class AttributeMappingOperationResult(NamedTuple):
    """Durable result of one idempotent mapping database operation."""

    applied: bool
    committed_at: str
    operation_evidence_json: str


class AttributeMappingConflictError(ValueError):
    """Raised when a pinned unresolved mapping was accepted by another writer."""


_UNRESOLVED_MAPPING_NOTES = {
    "no_value",
    "oov_candidate",
    "unable_to_determine",
}
_UNRESOLVED_MAPPING_VALUES = {
    "",
    "n/a",
    "n/a (not stated)",
    "not in taxonomy",
    "unknown",
}


def _like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _existing_mapping_row_is_unresolved(value: Any, note: Any) -> bool:
    note_token = str(note or "").strip().casefold()
    if note_token in _UNRESOLVED_MAPPING_NOTES:
        return True
    return value is None or str(value).strip().casefold() in _UNRESOLVED_MAPPING_VALUES


@dataclass(slots=True)
class CanonicalProductRecord:
    canonical_id: str
    brand_normalized: str
    name_normalized: str
    retailer: str
    parent_product_id: str
    captured_at: str


def _json_dumps(value) -> str:
    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Path):
            return str(obj)
        return str(obj)

    return json.dumps(value, ensure_ascii=False, default=default)


def _parse_failure_detail(detail: str) -> FailureRecord:
    trimmed = detail.strip()
    url = trimmed
    message: str | None = None
    status_code: int | None = None

    if " (" in trimmed and trimmed.endswith(")"):
        url_part, meta = trimmed.rsplit(" (", 1)
        url = url_part.strip()
        meta = meta[:-1].strip()  # drop trailing ")"
        message = meta or None
        status_match = _STATUS_RE.search(meta)
        if status_match:
            status_code = int(status_match.group(1))
    else:
        url = trimmed

    return FailureRecord(url=url, status_code=status_code, message=message)


_logger = logging.getLogger(__name__)


def _cursor_rowcount(cursor: Any) -> int:
    """Return a non-negative rowcount from DB-API-compatible cursors."""
    try:
        return max(int(getattr(cursor, "rowcount", 0) or 0), 0)
    except (TypeError, ValueError):
        return 0


class PDPStore:
    """Persist parent and variant rows to the configured PDP store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._postgres_url = require_pdp_postgres_url()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @contextmanager
    def _read_connection(
        self,
    ) -> Iterator[PostgresCompatConnection]:
        with PostgresCompatConnection(self._postgres_url) as conn:
            yield conn

    @contextmanager
    def _write_connection(self, owner: str) -> Iterator[PostgresCompatConnection]:
        with PostgresCompatConnection(self._postgres_url) as conn:
            yield conn

    def _ensure_schema(self) -> None:
        return

    def _apply_migrations(self, conn: PostgresCompatConnection) -> None:
        current_version = conn.execute("PRAGMA user_version;").fetchone()[0]

        self._add_column_if_missing(conn, "parent_products", "discovered_at", "TEXT")
        self._add_column_if_missing(conn, "parent_products", "last_seen_at", "TEXT")
        self._add_column_if_missing(conn, "parent_products", "discontinued_at", "TEXT")
        self._add_column_if_missing(
            conn, "parent_products", "batch_generated_at", "TEXT"
        )
        self._add_column_if_missing(conn, "variants", "batch_generated_at", "TEXT")
        self._backfill_parent_timestamps(conn)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_review_queue_candidate_unique
            ON review_queue_items (candidate_domain, candidate_type, candidate_key)
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_queue_status_priority
            ON review_queue_items (status, priority_score DESC)
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_review_queue_category_attribute
            ON review_queue_items (category_key, attribute_id)
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retailer_listing_observations_identity
            ON retailer_listing_observations (retailer, parent_product_id, pdp_url, crawl_ts)
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retailer_listing_observations_category_sort
            ON retailer_listing_observations (
                retailer,
                category_key,
                sort_mode,
                crawl_ts,
                page,
                position
            )
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retailer_filter_surfaces_lookup
            ON retailer_filter_surfaces (
                retailer,
                category_key,
                filter_family,
                filter_value,
                crawl_ts
            )
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retailer_filter_observations_lookup
            ON retailer_filter_observations (
                retailer,
                category_key,
                filter_family,
                filter_value,
                parent_product_id,
                pdp_url,
                crawl_ts
            )
            """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_retailer_sitemap_observations_lookup
            ON retailer_sitemap_observations (
                retailer,
                url_type,
                url,
                crawl_ts
            )
            """)

        if current_version < 5:
            for table in ATTR_STAGE_TABLES.values():
                conn.execute(STAGE_ATTRIBUTE_TABLE_TEMPLATE.format(table_name=table))
            migration_sql = """
                INSERT INTO {table_name} (
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id,
                    attribute_label,
                    value,
                    oov_candidate,
                    note,
                    updated_at,
                    extras_json
                )
                SELECT
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    '',
                    attribute_id,
                    attribute_label,
                    value,
                    oov_candidate,
                    note,
                    updated_at,
                    NULL
                FROM pdp_attribute_values
                WHERE source = ?
                ON CONFLICT(
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id
                )
                DO UPDATE SET
                    attribute_label = excluded.attribute_label,
                    value = excluded.value,
                    oov_candidate = excluded.oov_candidate,
                    note = excluded.note,
                    updated_at = excluded.updated_at
            """
            conn.execute(
                migration_sql.format(table_name=ATTR_STAGE_TABLES["deterministic"]),
                ("deterministic",),
            )
            conn.execute(
                migration_sql.format(table_name=ATTR_STAGE_TABLES["llm"]), ("llm",)
            )

        if current_version < 6:
            migration_sql = """
                INSERT INTO {table_name} (
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id,
                    attribute_label,
                    value,
                    oov_candidate,
                    note,
                    updated_at,
                    extras_json
                )
                SELECT
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    '',
                    attribute_id,
                    attribute_label,
                    value,
                    oov_candidate,
                    note,
                    updated_at,
                    NULL
                FROM pdp_attribute_values
                WHERE source = ?
                ON CONFLICT(
                    retailer,
                    row_type,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id
                )
                DO UPDATE SET
                    attribute_label = excluded.attribute_label,
                    value = excluded.value,
                    oov_candidate = excluded.oov_candidate,
                    note = excluded.note,
                    updated_at = excluded.updated_at
            """
            conn.execute(
                migration_sql.format(
                    table_name=ATTR_STAGE_TABLES["deterministic_explicit"]
                ),
                ("deterministic_explicit",),
            )

        self._rebuild_attribute_value_table_with_category_key(conn)
        for table in ATTR_STAGE_TABLES.values():
            self._rebuild_stage_attribute_table_with_category_key(conn, table)
        self._migrate_legacy_ulta_observation_tables(conn)

        if current_version < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")

    @staticmethod
    def _rebuild_table_with_category_key(
        conn: PostgresCompatConnection,
        *,
        table_name: str,
        create_sql: str,
        target_columns: Sequence[str],
        expected_pk: Sequence[str],
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table_name});").fetchall()
        if not rows:
            conn.execute(create_sql)
            return

        existing_columns = [str(row[1]) for row in rows]
        existing_pk = [
            str(row[1])
            for row in sorted(rows, key=lambda item: int(item[5] or 0))
            if int(row[5] or 0) > 0
        ]
        if "category_key" in existing_columns and existing_pk == list(expected_pk):
            return

        temp_name = f"{table_name}__category_key_tmp"
        conn.execute(f"DROP TABLE IF EXISTS {temp_name}")
        conn.execute(
            create_sql.replace(
                f"CREATE TABLE IF NOT EXISTS {table_name}",
                f"CREATE TABLE {temp_name}",
                1,
            )
        )

        select_exprs: list[str] = []
        for column in target_columns:
            if column in existing_columns:
                select_exprs.append(column)
            elif column == "category_key":
                select_exprs.append("'' AS category_key")
            elif column == "variant_id":
                select_exprs.append("'' AS variant_id")
            else:
                select_exprs.append(f"NULL AS {column}")

        conn.execute(f"""
            INSERT INTO {temp_name} ({', '.join(target_columns)})
            SELECT {', '.join(select_exprs)}
            FROM {table_name}
            """)
        conn.execute(f"DROP TABLE {table_name}")
        conn.execute(f"ALTER TABLE {temp_name} RENAME TO {table_name}")

    def _rebuild_attribute_value_table_with_category_key(
        self,
        conn: PostgresCompatConnection,
    ) -> None:
        self._rebuild_table_with_category_key(
            conn,
            table_name="pdp_attribute_values",
            create_sql=ATTRIBUTE_VALUES_TABLE_TEMPLATE.format(
                table_name="pdp_attribute_values"
            ),
            target_columns=(
                "retailer",
                "row_type",
                "parent_product_id",
                "variant_id",
                "category_key",
                "attribute_id",
                "attribute_label",
                "value",
                "oov_candidate",
                "note",
                "source",
                "updated_at",
            ),
            expected_pk=(
                "retailer",
                "row_type",
                "parent_product_id",
                "variant_id",
                "category_key",
                "attribute_id",
                "source",
            ),
        )

    def _rebuild_stage_attribute_table_with_category_key(
        self,
        conn: PostgresCompatConnection,
        table_name: str,
    ) -> None:
        self._rebuild_table_with_category_key(
            conn,
            table_name=table_name,
            create_sql=STAGE_ATTRIBUTE_TABLE_TEMPLATE.format(table_name=table_name),
            target_columns=(
                "retailer",
                "row_type",
                "parent_product_id",
                "variant_id",
                "category_key",
                "attribute_id",
                "attribute_label",
                "value",
                "oov_candidate",
                "note",
                "updated_at",
                "extras_json",
            ),
            expected_pk=(
                "retailer",
                "row_type",
                "parent_product_id",
                "variant_id",
                "category_key",
                "attribute_id",
            ),
        )

    @staticmethod
    def _add_column_if_missing(
        conn: PostgresCompatConnection, table: str, column: str, definition: str
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
        if not any(row[1] == column for row in rows):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")

    @staticmethod
    def _backfill_parent_timestamps(conn: PostgresCompatConnection) -> None:
        conn.execute("""
            UPDATE parent_products
            SET discovered_at = COALESCE(discovered_at, batch_generated_at),
                last_seen_at = COALESCE(last_seen_at, batch_generated_at)
            WHERE discovered_at IS NULL
               OR last_seen_at IS NULL
            """)

    @staticmethod
    def _table_exists(conn: PostgresCompatConnection, table_name: str) -> bool:
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @classmethod
    def _migrate_legacy_ulta_observation_tables(
        cls, conn: PostgresCompatConnection
    ) -> None:
        if cls._table_exists(conn, "ulta_listing_observations"):
            cls._add_column_if_missing(
                conn,
                "ulta_listing_observations",
                "has_new_badge",
                "INTEGER NOT NULL DEFAULT 0",
            )
            conn.execute("""
                INSERT OR IGNORE INTO retailer_listing_observations (
                    crawl_ts,
                    retailer,
                    category_key,
                    source_surface,
                    sort_mode,
                    page,
                    position,
                    pdp_url,
                    parent_product_id,
                    product_name,
                    brand,
                    has_new_badge,
                    listing_url
                )
                SELECT
                    crawl_ts,
                    retailer,
                    category_key,
                    source_surface,
                    sort_mode,
                    page,
                    position,
                    pdp_url,
                    parent_product_id,
                    product_name,
                    brand,
                    has_new_badge,
                    listing_url
                FROM ulta_listing_observations
                """)
            conn.execute("DROP TABLE ulta_listing_observations")

        if cls._table_exists(conn, "ulta_filter_observations"):
            conn.execute("""
                INSERT OR IGNORE INTO retailer_filter_observations (
                    crawl_ts,
                    retailer,
                    category_key,
                    filter_family,
                    filter_value,
                    source_surface,
                    pdp_url,
                    parent_product_id,
                    page,
                    position,
                    listing_url
                )
                SELECT
                    crawl_ts,
                    retailer,
                    category_key,
                    filter_family,
                    filter_value,
                    source_surface,
                    pdp_url,
                    parent_product_id,
                    page,
                    position,
                    listing_url
                FROM ulta_filter_observations
                """)
            conn.execute("DROP TABLE ulta_filter_observations")

        if cls._table_exists(conn, "ulta_sitemap_observations"):
            conn.execute("""
                INSERT OR IGNORE INTO retailer_sitemap_observations (
                    crawl_ts,
                    retailer,
                    sitemap_source,
                    url,
                    lastmod,
                    url_type
                )
                SELECT
                    crawl_ts,
                    retailer,
                    sitemap_source,
                    url,
                    lastmod,
                    url_type
                FROM ulta_sitemap_observations
                """)
            conn.execute("DROP TABLE ulta_sitemap_observations")

    @staticmethod
    def _attribute_stage_table(stage: str) -> str:
        try:
            return ATTR_STAGE_TABLES[stage]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Unknown attribute stage '{stage}'") from exc

    def clear_stage_attribute_values(
        self,
        stage: str,
        *,
        retailers: Sequence[str] | None = None,
    ) -> None:
        table = self._attribute_stage_table(stage)
        conditions: list[str] = []
        params: list[str] = []
        if retailers:
            placeholders = ",".join("?" for _ in retailers)
            conditions.append(f"retailer IN ({placeholders})")
            params.extend(retailers)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._write_connection("clear_stage_attribute_values") as conn:
            conn.execute(f"DELETE FROM {table}{where_clause}", params)
            conn.commit()

    def clear_stage_attribute_values_for_parents(
        self,
        stage: str,
        parent_ids: Sequence[str],
        *,
        retailers: Sequence[str] | None = None,
        category_keys: Sequence[str] | None = None,
    ) -> None:
        """Remove stage values for specific parents, optionally scoped to retailers."""
        table = self._attribute_stage_table(stage)
        parent_ids = [pid for pid in parent_ids if str(pid).strip()]
        if not parent_ids:
            return

        def _chunks(seq: Sequence[str], size: int = 400) -> Iterable[Sequence[str]]:
            for i in range(0, len(seq), size):
                yield seq[i : i + size]

        base_conditions: list[str] = []
        base_params: list[str] = []
        if retailers:
            placeholders = ",".join("?" for _ in retailers)
            base_conditions.append(f"retailer IN ({placeholders})")
            base_params.extend(retailers)
        if category_keys:
            placeholders = ",".join("?" for _ in category_keys)
            base_conditions.append(f"COALESCE(category_key, '') IN ({placeholders})")
            base_params.extend(category_keys)

        with self._write_connection("clear_stage_attribute_values_for_parents") as conn:
            for chunk in _chunks(parent_ids):
                conditions = list(base_conditions)
                params = list(base_params)
                placeholders = ",".join("?" for _ in chunk)
                conditions.append(f"parent_product_id IN ({placeholders})")
                params.extend(chunk)
                where_clause = (
                    f" WHERE {' AND '.join(conditions)}" if conditions else ""
                )
                conn.execute(f"DELETE FROM {table}{where_clause}", params)
            conn.commit()

    def write_stage_attribute_values(
        self,
        stage: str,
        records: Iterable[AttributeValueRecord],
    ) -> None:
        table = self._attribute_stage_table(stage)
        rows: list[tuple[Any, ...]] = []
        for record in records:
            if record.source and record.source != stage:
                raise ValueError(
                    f"Record source '{record.source}' does not match target stage '{stage}'."
                )
            extras_json = getattr(record, "extras_json", None)
            rows.append(
                (
                    record.retailer,
                    record.row_type,
                    record.parent_product_id,
                    record.variant_id or "",
                    record.category_key or "",
                    record.attribute_id,
                    record.attribute_label,
                    record.value,
                    record.oov_candidate,
                    record.note,
                    record.updated_at,
                    extras_json,
                )
            )
        if not rows:
            return
        sql = f"""
            INSERT INTO {table} (
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id,
                attribute_label,
                value,
                oov_candidate,
                note,
                updated_at,
                extras_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id
            )
            DO UPDATE SET
                attribute_label = excluded.attribute_label,
                value = excluded.value,
                oov_candidate = excluded.oov_candidate,
                note = excluded.note,
                updated_at = excluded.updated_at,
                extras_json = excluded.extras_json
        """
        with self._write_connection("write_stage_attribute_values") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def append_attribute_audit(
        self,
        records: Iterable[AttributeAuditRecord],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        for record in records:
            rows.append(
                (
                    record.timestamp,
                    record.source,
                    record.row_type,
                    record.retailer,
                    record.parent_product_id,
                    record.variant_id,
                    record.attribute_id,
                    record.value,
                    record.decision_rule,
                    record.evidence_json,
                    record.category_key,
                )
            )
        if not rows:
            return
        sql = """
            INSERT INTO pdp_attribute_audit (
                timestamp,
                source,
                row_type,
                retailer,
                parent_product_id,
                variant_id,
                attribute_id,
                value,
                decision_rule,
                evidence_json,
                category_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_connection("append_attribute_audit") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def fetch_attribute_audit_rows(
        self,
        *,
        attribute_id: str,
        row_type: str,
        keys: Sequence[tuple[str, str, str]],
    ) -> list[dict[str, Any]]:
        if not attribute_id or not row_type or not keys:
            return []
        normalized_keys: list[tuple[str, str, str]] = []
        for retailer, parent_id, variant_id in keys:
            parent_text = str(parent_id or "").strip()
            if not parent_text:
                continue
            normalized_keys.append(
                (
                    str(retailer or "").strip(),
                    parent_text,
                    str(variant_id or "").strip(),
                )
            )
        if not normalized_keys:
            return []
        conditions: list[str] = []
        params: list[str] = [attribute_id, row_type]
        for retailer, parent_id, variant_id in normalized_keys:
            conditions.append(
                "(COALESCE(retailer, '') = ? AND parent_product_id = ? AND COALESCE(variant_id, '') = ?)"
            )
            params.extend([retailer, parent_id, variant_id])
        columns = [
            "timestamp",
            "source",
            "row_type",
            "retailer",
            "parent_product_id",
            "variant_id",
            "attribute_id",
            "value",
            "decision_rule",
            "evidence_json",
            "category_key",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_attribute_audit "
            "WHERE attribute_id = ? AND row_type = ? AND ("
            + " OR ".join(conditions)
            + ") ORDER BY timestamp DESC"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{key: value for key, value in zip(columns, row)} for row in rows]

    def fetch_attribute_stage_rows(
        self,
        *,
        attribute_id: str,
        row_type: str,
        keys: Sequence[tuple[str, str, str]],
        sources: Sequence[str] = ("llm", "deterministic"),
    ) -> list[dict[str, Any]]:
        if not attribute_id or not row_type or not keys or not sources:
            return []
        source_values = [
            str(source).strip() for source in sources if str(source).strip()
        ]
        if not source_values:
            return []

        normalized_keys: list[tuple[str, str, str]] = []
        for retailer, parent_id, variant_id in keys:
            parent_text = str(parent_id or "").strip()
            if not parent_text:
                continue
            normalized_keys.append(
                (
                    str(retailer or "").strip(),
                    parent_text,
                    str(variant_id or "").strip(),
                )
            )
        if not normalized_keys:
            return []

        key_conditions: list[str] = []
        params: list[str] = [attribute_id, row_type, *source_values]
        for retailer, parent_id, variant_id in normalized_keys:
            key_conditions.append(
                "(retailer = ? AND parent_product_id = ? AND COALESCE(variant_id, '') = ?)"
            )
            params.extend([retailer, parent_id, variant_id])

        source_placeholders = ",".join("?" for _ in source_values)
        columns = [
            "source",
            "row_type",
            "retailer",
            "parent_product_id",
            "variant_id",
            "category_key",
            "attribute_id",
            "value",
            "updated_at",
        ]
        query = (
            "SELECT source, row_type, retailer, parent_product_id, "
            "COALESCE(variant_id, '') AS variant_id, "
            "COALESCE(category_key, '') AS category_key, "
            "attribute_id, value, updated_at "
            "FROM pdp_attribute_values "
            "WHERE attribute_id = ? AND row_type = ? "
            f"AND source IN ({source_placeholders}) AND ("
            + " OR ".join(key_conditions)
            + ") ORDER BY updated_at DESC"
        )

        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{key: value for key, value in zip(columns, row)} for row in rows]

    def fetch_attribute_value_coverage(
        self,
        *,
        retailer: str | None = None,
        category_key: str | None = None,
        row_type: str | None = None,
        sources: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return value/no-value counts from the canonical attribute table."""
        conditions: list[str] = []
        params: list[str] = []
        if retailer:
            conditions.append("retailer = ?")
            params.append(str(retailer).strip())
        if category_key:
            conditions.append("category_key = ?")
            params.append(str(category_key).strip())
        if row_type:
            conditions.append("row_type = ?")
            params.append(str(row_type).strip())
        if sources:
            source_values = [
                str(source).strip() for source in sources if str(source).strip()
            ]
            if source_values:
                placeholders = ",".join("?" for _ in source_values)
                conditions.append(f"source IN ({placeholders})")
                params.extend(source_values)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
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
        query = (
            f"SELECT {', '.join(columns)} "
            "FROM pdp_attribute_value_coverage"
            f"{where_clause} "
            "ORDER BY retailer, category_key, row_type, source"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{key: value for key, value in zip(columns, row)} for row in rows]

    def read_stage_attribute_values(
        self,
        stage: str,
        *,
        retailers: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        table = self._attribute_stage_table(stage)
        columns = [
            "retailer",
            "row_type",
            "parent_product_id",
            "variant_id",
            "category_key",
            "attribute_id",
            "attribute_label",
            "value",
            "oov_candidate",
            "note",
            "updated_at",
            "extras_json",
        ]
        query = f"SELECT {', '.join(columns)} FROM {table}"
        params: list[str] = []
        if retailers:
            placeholders = ",".join("?" for _ in retailers)
            query += f" WHERE retailer IN ({placeholders})"
            params.extend(retailers)
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        results: list[dict[str, Any]] = [
            {key: value for key, value in zip(columns, row)} for row in rows
        ]
        for entry in results:
            entry["source"] = stage
        return results

    def upsert_explicit_rule_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            category_key = str(candidate.get("category_key") or "").strip().lower()
            attribute_id = str(candidate.get("attribute_id") or "").strip()
            proposed_value = str(candidate.get("proposed_value") or "").strip()
            pattern = str(candidate.get("pattern") or "").strip()
            pattern_type = (
                str(candidate.get("pattern_type") or "phrase").strip().lower()
            )
            sample_count = int(candidate.get("sample_count") or 0)
            snippets = candidate.get("sample_snippets", [])
            if isinstance(snippets, Sequence) and not isinstance(
                snippets, (str, bytes)
            ):
                sample_snippets_json = _json_dumps(
                    [str(item) for item in snippets if str(item).strip()]
                )
            else:
                sample_snippets_json = "[]"
            estimated_conflict_rate = candidate.get("estimated_conflict_rate")
            reviewed_samples = candidate.get("reviewed_samples")
            precision_estimate = candidate.get("precision_estimate")
            status = (
                str(candidate.get("status") or "pending").strip().lower() or "pending"
            )
            reviewer_note = candidate.get("reviewer_note")
            rejection_reason = candidate.get("rejection_reason")
            reviewer = candidate.get("reviewer")
            created_at = str(candidate.get("created_at") or "").strip()
            updated_at = str(candidate.get("updated_at") or "").strip()
            if (
                not candidate_id
                or not category_key
                or not attribute_id
                or not proposed_value
            ):
                continue
            if not pattern or pattern_type not in {"phrase", "regex"}:
                continue
            if not created_at:
                created_at = updated_at
            if not created_at:
                continue
            if not updated_at:
                updated_at = created_at
            rows.append(
                (
                    candidate_id,
                    category_key,
                    attribute_id,
                    proposed_value,
                    pattern,
                    pattern_type,
                    sample_count,
                    sample_snippets_json,
                    estimated_conflict_rate,
                    reviewed_samples,
                    precision_estimate,
                    status,
                    reviewer_note,
                    rejection_reason,
                    reviewer,
                    created_at,
                    updated_at,
                )
            )
        if not rows:
            return 0
        sql = """
            INSERT INTO pdp_explicit_rule_candidates (
                candidate_id,
                category_key,
                attribute_id,
                proposed_value,
                pattern,
                pattern_type,
                sample_count,
                sample_snippets_json,
                estimated_conflict_rate,
                reviewed_samples,
                precision_estimate,
                status,
                reviewer_note,
                rejection_reason,
                reviewer,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id)
            DO UPDATE SET
                category_key = excluded.category_key,
                attribute_id = excluded.attribute_id,
                proposed_value = excluded.proposed_value,
                pattern = excluded.pattern,
                pattern_type = excluded.pattern_type,
                sample_count = excluded.sample_count,
                sample_snippets_json = excluded.sample_snippets_json,
                estimated_conflict_rate = excluded.estimated_conflict_rate,
                reviewed_samples = excluded.reviewed_samples,
                precision_estimate = excluded.precision_estimate,
                status = excluded.status,
                reviewer_note = excluded.reviewer_note,
                rejection_reason = excluded.rejection_reason,
                reviewer = excluded.reviewer,
                created_at = COALESCE(pdp_explicit_rule_candidates.created_at, excluded.created_at),
                updated_at = excluded.updated_at
        """
        with self._write_connection("upsert_explicit_rule_candidates") as conn:
            cursor = conn.executemany(sql, rows)
            changes = _cursor_rowcount(cursor)
            conn.commit()
        return changes

    def list_explicit_rule_candidates(
        self,
        *,
        status: str | None = None,
        category_key: str | None = None,
        attribute_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                candidate_id,
                category_key,
                attribute_id,
                proposed_value,
                pattern,
                pattern_type,
                sample_count,
                sample_snippets_json,
                estimated_conflict_rate,
                reviewed_samples,
                precision_estimate,
                status,
                reviewer_note,
                rejection_reason,
                reviewer,
                created_at,
                updated_at
            FROM pdp_explicit_rule_candidates
        """
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(str(status).strip().lower())
        if category_key:
            conditions.append("category_key = ?")
            params.append(str(category_key).strip().lower())
        if attribute_id:
            conditions.append("attribute_id = ?")
            params.append(str(attribute_id).strip())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC, candidate_id ASC LIMIT ?"
        params.append(max(1, int(limit)))

        columns = [
            "candidate_id",
            "category_key",
            "attribute_id",
            "proposed_value",
            "pattern",
            "pattern_type",
            "sample_count",
            "sample_snippets_json",
            "estimated_conflict_rate",
            "reviewed_samples",
            "precision_estimate",
            "status",
            "reviewer_note",
            "rejection_reason",
            "reviewer",
            "created_at",
            "updated_at",
        ]
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            snippets_raw = item.pop("sample_snippets_json", "[]")
            try:
                item["sample_snippets"] = json.loads(snippets_raw or "[]")
            except (TypeError, json.JSONDecodeError):
                item["sample_snippets"] = []
            payload.append(item)
        return payload

    def update_explicit_rule_candidate(
        self,
        *,
        candidate_id: str,
        status: str,
        updated_at: str,
        pattern: str | None = None,
        reviewer_note: str | None = None,
        rejection_reason: str | None = None,
        reviewer: str | None = None,
        reviewed_samples: int | None = None,
        precision_estimate: float | None = None,
    ) -> dict[str, Any] | None:
        normalized_candidate = str(candidate_id or "").strip()
        normalized_status = str(status or "").strip().lower()
        if not normalized_candidate or not normalized_status:
            return None
        assignments = ["status = ?", "updated_at = ?"]
        params: list[Any] = [normalized_status, updated_at]
        if pattern is not None:
            assignments.append("pattern = ?")
            params.append(str(pattern).strip())
        if reviewer_note is not None:
            assignments.append("reviewer_note = ?")
            params.append(str(reviewer_note))
        if rejection_reason is not None:
            assignments.append("rejection_reason = ?")
            params.append(str(rejection_reason))
        if reviewer is not None:
            assignments.append("reviewer = ?")
            params.append(str(reviewer))
        if reviewed_samples is not None:
            assignments.append("reviewed_samples = ?")
            params.append(int(reviewed_samples))
        if precision_estimate is not None:
            assignments.append("precision_estimate = ?")
            params.append(float(precision_estimate))

        params.append(normalized_candidate)
        query = (
            "UPDATE pdp_explicit_rule_candidates SET "
            + ", ".join(assignments)
            + " WHERE candidate_id = ?"
        )
        with self._write_connection("update_explicit_rule_candidate") as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            if not cursor.rowcount:
                return None
            row = conn.execute(
                """
                SELECT
                    candidate_id,
                    category_key,
                    attribute_id,
                    proposed_value,
                    pattern,
                    pattern_type,
                    sample_count,
                    sample_snippets_json,
                    estimated_conflict_rate,
                    reviewed_samples,
                    precision_estimate,
                    status,
                    reviewer_note,
                    rejection_reason,
                    reviewer,
                    created_at,
                    updated_at
                FROM pdp_explicit_rule_candidates
                WHERE candidate_id = ?
                """,
                (normalized_candidate,),
            ).fetchone()
        if row is None:
            return None
        keys = [
            "candidate_id",
            "category_key",
            "attribute_id",
            "proposed_value",
            "pattern",
            "pattern_type",
            "sample_count",
            "sample_snippets_json",
            "estimated_conflict_rate",
            "reviewed_samples",
            "precision_estimate",
            "status",
            "reviewer_note",
            "rejection_reason",
            "reviewer",
            "created_at",
            "updated_at",
        ]
        payload = {key: value for key, value in zip(keys, row)}
        snippets_raw = payload.pop("sample_snippets_json", "[]")
        try:
            payload["sample_snippets"] = json.loads(snippets_raw or "[]")
        except (TypeError, json.JSONDecodeError):
            payload["sample_snippets"] = []
        return payload

    def append_explicit_rules_audit(
        self,
        *,
        timestamp: str,
        action: str,
        actor: str | None = None,
        candidate_id: str | None = None,
        rule_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(timestamp or "").strip() or not str(action or "").strip():
            return
        details_json = _json_dumps(details or {})
        with self._write_connection("append_explicit_rules_audit") as conn:
            conn.execute(
                """
                INSERT INTO pdp_explicit_rules_audit (
                    timestamp,
                    action,
                    candidate_id,
                    rule_id,
                    actor,
                    details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(timestamp).strip(),
                    str(action).strip(),
                    str(candidate_id).strip() if candidate_id else None,
                    str(rule_id).strip() if rule_id else None,
                    str(actor).strip() if actor else None,
                    details_json,
                ),
            )
            conn.commit()

    def list_explicit_rules_audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        columns = [
            "id",
            "timestamp",
            "action",
            "candidate_id",
            "rule_id",
            "actor",
            "details_json",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_explicit_rules_audit "
            "ORDER BY id DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, (max(1, int(limit)),)).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            details_raw = item.pop("details_json", "{}")
            try:
                item["details"] = json.loads(details_raw or "{}")
            except (TypeError, json.JSONDecodeError):
                item["details"] = {}
            payload.append(item)
        return payload

    def append_explicit_rules_config_version(
        self,
        *,
        version: str,
        published_at: str,
        config: Mapping[str, Any],
        actor: str | None = None,
        note: str | None = None,
        diff_summary: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(version or "").strip():
            raise ValueError("version is required for explicit rule config publish.")
        config_json = _json_dumps(config)
        diff_summary_json = _json_dumps(diff_summary or {})
        with self._write_connection("append_explicit_rules_config_version") as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pdp_explicit_rule_config_versions (
                    version,
                    published_at,
                    actor,
                    note,
                    config_json,
                    diff_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(version).strip(),
                    str(published_at).strip(),
                    str(actor).strip() if actor else None,
                    str(note) if note is not None else None,
                    config_json,
                    diff_summary_json,
                ),
            )
            conn.commit()

    def list_explicit_rules_config_versions(
        self,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        columns = [
            "version",
            "published_at",
            "actor",
            "note",
            "config_json",
            "diff_summary_json",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_explicit_rule_config_versions "
            "ORDER BY published_at DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, (max(1, int(limit)),)).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            for key in ("config_json", "diff_summary_json"):
                raw = item.pop(key, "{}")
                try:
                    item[key.replace("_json", "")] = json.loads(raw or "{}")
                except (TypeError, json.JSONDecodeError):
                    item[key.replace("_json", "")] = {}
            payload.append(item)
        return payload

    def append_taxonomy_governance_audit(
        self,
        *,
        timestamp: str,
        action: str,
        actor: str | None = None,
        category_key: str | None = None,
        attribute_id: str | None = None,
        leaf_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(timestamp or "").strip() or not str(action or "").strip():
            return
        details_json = _json_dumps(details or {})
        with self._write_connection("append_taxonomy_governance_audit") as conn:
            conn.execute(
                """
                INSERT INTO pdp_taxonomy_governance_audit (
                    timestamp,
                    action,
                    actor,
                    category_key,
                    attribute_id,
                    leaf_id,
                    details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(timestamp).strip(),
                    str(action).strip(),
                    str(actor).strip() if actor else None,
                    str(category_key).strip() if category_key else None,
                    str(attribute_id).strip() if attribute_id else None,
                    str(leaf_id).strip() if leaf_id else None,
                    details_json,
                ),
            )
            conn.commit()

    def list_taxonomy_governance_audit(
        self, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        columns = [
            "id",
            "timestamp",
            "action",
            "actor",
            "category_key",
            "attribute_id",
            "leaf_id",
            "details_json",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_taxonomy_governance_audit "
            "ORDER BY id DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, (max(1, int(limit)),)).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            details_raw = item.pop("details_json", "{}")
            try:
                item["details"] = json.loads(details_raw or "{}")
            except (TypeError, json.JSONDecodeError):
                item["details"] = {}
            payload.append(item)
        return payload

    def append_taxonomy_config_version(
        self,
        *,
        version: str,
        published_at: str,
        config: Mapping[str, Any],
        actor: str | None = None,
        note: str | None = None,
        diff_summary: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(version or "").strip():
            raise ValueError("version is required for taxonomy config publish.")
        config_json = _json_dumps(config)
        diff_summary_json = _json_dumps(diff_summary or {})
        with self._write_connection("append_taxonomy_config_version") as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pdp_taxonomy_config_versions (
                    version,
                    published_at,
                    actor,
                    note,
                    config_json,
                    diff_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(version).strip(),
                    str(published_at).strip(),
                    str(actor).strip() if actor else None,
                    str(note) if note is not None else None,
                    config_json,
                    diff_summary_json,
                ),
            )
            conn.commit()

    def list_taxonomy_config_versions(
        self,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        columns = [
            "version",
            "published_at",
            "actor",
            "note",
            "config_json",
            "diff_summary_json",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_taxonomy_config_versions "
            "ORDER BY published_at DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, (max(1, int(limit)),)).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            for key in ("config_json", "diff_summary_json"):
                raw = item.pop(key, "{}")
                try:
                    item[key.replace("_json", "")] = json.loads(raw or "{}")
                except (TypeError, json.JSONDecodeError):
                    item[key.replace("_json", "")] = {}
            payload.append(item)
        return payload

    def get_taxonomy_draft(
        self,
        *,
        draft_name: str = "current",
    ) -> dict[str, Any] | None:
        columns = [
            "draft_name",
            "config_json",
            "updated_at",
            "updated_by",
            "last_queue_item_id",
        ]
        with self._read_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {', '.join(columns)}
                FROM pdp_taxonomy_drafts
                WHERE draft_name = ?
                """,
                (str(draft_name).strip(),),
            ).fetchone()
        if row is None:
            return None
        item = {key: value for key, value in zip(columns, row)}
        raw = item.pop("config_json", "{}")
        try:
            item["config"] = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            item["config"] = {}
        return item

    def upsert_taxonomy_draft(
        self,
        *,
        config: Mapping[str, Any],
        updated_at: str,
        updated_by: str | None = None,
        last_queue_item_id: str | None = None,
        draft_name: str = "current",
    ) -> None:
        with self._write_connection("upsert_taxonomy_draft") as conn:
            conn.execute(
                """
                INSERT INTO pdp_taxonomy_drafts (
                    draft_name,
                    config_json,
                    updated_at,
                    updated_by,
                    last_queue_item_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(draft_name)
                DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by,
                    last_queue_item_id = excluded.last_queue_item_id
                """,
                (
                    str(draft_name).strip(),
                    _json_dumps(config),
                    str(updated_at).strip(),
                    str(updated_by).strip() if updated_by else None,
                    str(last_queue_item_id).strip() if last_queue_item_id else None,
                ),
            )
            conn.commit()

    def delete_taxonomy_draft(
        self,
        *,
        draft_name: str = "current",
    ) -> None:
        with self._write_connection("delete_taxonomy_draft") as conn:
            conn.execute(
                "DELETE FROM pdp_taxonomy_drafts WHERE draft_name = ?",
                (str(draft_name).strip(),),
            )
            conn.commit()

    def get_deterministic_policy_draft(
        self,
        *,
        draft_name: str = "current",
    ) -> dict[str, Any] | None:
        columns = [
            "draft_name",
            "config_json",
            "updated_at",
            "updated_by",
        ]
        with self._read_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {', '.join(columns)}
                FROM pdp_deterministic_policy_drafts
                WHERE draft_name = ?
                """,
                (str(draft_name).strip(),),
            ).fetchone()
        if row is None:
            return None
        item = {key: value for key, value in zip(columns, row)}
        raw = item.pop("config_json", "{}")
        try:
            item["config"] = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            item["config"] = {}
        return item

    def upsert_deterministic_policy_draft(
        self,
        *,
        config: Mapping[str, Any],
        updated_at: str,
        updated_by: str | None = None,
        draft_name: str = "current",
    ) -> None:
        with self._write_connection("upsert_deterministic_policy_draft") as conn:
            conn.execute(
                """
                INSERT INTO pdp_deterministic_policy_drafts (
                    draft_name,
                    config_json,
                    updated_at,
                    updated_by
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(draft_name)
                DO UPDATE SET
                    config_json = excluded.config_json,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    str(draft_name).strip(),
                    _json_dumps(config),
                    str(updated_at).strip(),
                    str(updated_by).strip() if updated_by else None,
                ),
            )
            conn.commit()

    def delete_deterministic_policy_draft(
        self,
        *,
        draft_name: str = "current",
    ) -> None:
        with self._write_connection("delete_deterministic_policy_draft") as conn:
            conn.execute(
                "DELETE FROM pdp_deterministic_policy_drafts WHERE draft_name = ?",
                (str(draft_name).strip(),),
            )
            conn.commit()

    def append_deterministic_policy_config_version(
        self,
        *,
        version: str,
        published_at: str,
        config: Mapping[str, Any],
        actor: str | None = None,
        note: str | None = None,
        diff_summary: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(version or "").strip():
            raise ValueError("version is required for deterministic policy publish.")
        config_json = _json_dumps(config)
        diff_summary_json = _json_dumps(diff_summary or {})
        with self._write_connection(
            "append_deterministic_policy_config_version"
        ) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pdp_deterministic_policy_config_versions (
                    version,
                    published_at,
                    actor,
                    note,
                    config_json,
                    diff_summary_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(version).strip(),
                    str(published_at).strip(),
                    str(actor).strip() if actor else None,
                    str(note) if note is not None else None,
                    config_json,
                    diff_summary_json,
                ),
            )
            conn.commit()

    def list_deterministic_policy_config_versions(
        self,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        columns = [
            "version",
            "published_at",
            "actor",
            "note",
            "config_json",
            "diff_summary_json",
        ]
        query = (
            f"SELECT {', '.join(columns)} FROM pdp_deterministic_policy_config_versions "
            "ORDER BY published_at DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, (max(1, int(limit)),)).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            for key in ("config_json", "diff_summary_json"):
                raw = item.pop(key, "{}")
                try:
                    item[key.replace("_json", "")] = json.loads(raw or "{}")
                except (TypeError, json.JSONDecodeError):
                    item[key.replace("_json", "")] = {}
            payload.append(item)
        return payload

    def append_deterministic_policy_audit(
        self,
        *,
        timestamp: str,
        action: str,
        actor: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        with self._write_connection("append_deterministic_policy_audit") as conn:
            conn.execute(
                """
                INSERT INTO pdp_deterministic_policy_audit (
                    timestamp,
                    action,
                    actor,
                    details_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(timestamp).strip(),
                    str(action).strip(),
                    str(actor).strip() if actor else None,
                    _json_dumps(details or {}),
                ),
            )
            conn.commit()

    def upsert_review_queue_items(
        self,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        payloads: list[tuple[Any, ...]] = []
        for row in rows:
            queue_item_id = str(row.get("queue_item_id") or "").strip()
            candidate_domain = str(row.get("candidate_domain") or "").strip()
            candidate_type = str(row.get("candidate_type") or "").strip()
            candidate_key = str(row.get("candidate_key") or "").strip()
            origin = str(row.get("origin") or "").strip()
            status = str(row.get("status") or "").strip()
            title = str(row.get("title") or "").strip()
            created_at = str(row.get("created_at") or "").strip()
            updated_at = str(row.get("updated_at") or "").strip()
            if not (
                queue_item_id
                and candidate_domain
                and candidate_type
                and candidate_key
                and origin
                and status
                and title
                and created_at
                and updated_at
            ):
                continue
            payload_json = row.get("payload_json")
            payloads.append(
                (
                    queue_item_id,
                    candidate_domain,
                    candidate_type,
                    candidate_key,
                    str(row.get("aggregated_row_ref") or "").strip() or None,
                    str(row.get("run_id") or "").strip() or None,
                    str(row.get("evidence_signature") or "").strip() or None,
                    origin,
                    status,
                    str(row.get("category_key") or "").strip() or None,
                    str(row.get("attribute_id") or "").strip() or None,
                    str(row.get("value_id") or "").strip() or None,
                    title,
                    str(row.get("short_reason") or "").strip() or None,
                    row.get("priority_score"),
                    str(row.get("confidence_level") or "").strip() or None,
                    str(row.get("decision_ease") or "").strip() or None,
                    row.get("support_product_count"),
                    row.get("support_retailer_count"),
                    str(row.get("reviewer") or "").strip() or None,
                    str(row.get("decision_reason") or "").strip() or None,
                    _json_dumps(payload_json) if payload_json is not None else None,
                    created_at,
                    updated_at,
                )
            )
        if not payloads:
            return
        with self._write_connection("upsert_review_queue_items") as conn:
            conn.executemany(
                """
                INSERT INTO review_queue_items (
                    queue_item_id,
                    candidate_domain,
                    candidate_type,
                    candidate_key,
                    aggregated_row_ref,
                    run_id,
                    evidence_signature,
                    origin,
                    status,
                    category_key,
                    attribute_id,
                    value_id,
                    title,
                    short_reason,
                    priority_score,
                    confidence_level,
                    decision_ease,
                    support_product_count,
                    support_retailer_count,
                    reviewer,
                    decision_reason,
                    payload_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_domain, candidate_type, candidate_key)
                DO UPDATE SET
                    aggregated_row_ref = excluded.aggregated_row_ref,
                    run_id = excluded.run_id,
                    evidence_signature = excluded.evidence_signature,
                    origin = excluded.origin,
                    status = excluded.status,
                    category_key = excluded.category_key,
                    attribute_id = excluded.attribute_id,
                    value_id = excluded.value_id,
                    title = excluded.title,
                    short_reason = excluded.short_reason,
                    priority_score = excluded.priority_score,
                    confidence_level = excluded.confidence_level,
                    decision_ease = excluded.decision_ease,
                    support_product_count = excluded.support_product_count,
                    support_retailer_count = excluded.support_retailer_count,
                    reviewer = excluded.reviewer,
                    decision_reason = excluded.decision_reason,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                payloads,
            )
            conn.commit()

    def list_review_queue_items(
        self,
        *,
        status: str | None = None,
        candidate_domain: str | None = None,
        candidate_type: str | None = None,
        category_key: str | None = None,
        attribute_id: str | None = None,
        origin: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        columns = [
            "queue_item_id",
            "candidate_domain",
            "candidate_type",
            "candidate_key",
            "aggregated_row_ref",
            "run_id",
            "evidence_signature",
            "origin",
            "status",
            "category_key",
            "attribute_id",
            "value_id",
            "title",
            "short_reason",
            "priority_score",
            "confidence_level",
            "decision_ease",
            "support_product_count",
            "support_retailer_count",
            "reviewer",
            "decision_reason",
            "payload_json",
            "created_at",
            "updated_at",
        ]
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if candidate_domain:
            conditions.append("candidate_domain = ?")
            params.append(candidate_domain)
        if candidate_type:
            conditions.append("candidate_type = ?")
            params.append(candidate_type)
        if category_key:
            conditions.append("category_key = ?")
            params.append(category_key)
        if attribute_id:
            conditions.append("attribute_id = ?")
            params.append(attribute_id)
        if origin:
            conditions.append("origin = ?")
            params.append(origin)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(max(1, int(limit)))
        query = (
            f"SELECT {', '.join(columns)} FROM review_queue_items {where_clause} "
            "ORDER BY CASE status "
            "WHEN 'open' THEN 0 "
            "WHEN 'approved' THEN 1 "
            "WHEN 'rejected' THEN 2 "
            "WHEN 'applied' THEN 3 "
            "ELSE 4 END, priority_score DESC, updated_at DESC LIMIT ?"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = {key: value for key, value in zip(columns, row)}
            payload_raw = item.get("payload_json")
            if isinstance(payload_raw, str) and payload_raw.strip():
                try:
                    item["payload_json"] = json.loads(payload_raw)
                except json.JSONDecodeError:
                    pass
            payload.append(item)
        return payload

    def get_review_queue_item(self, queue_item_id: str) -> dict[str, Any] | None:
        columns = [
            "queue_item_id",
            "candidate_domain",
            "candidate_type",
            "candidate_key",
            "aggregated_row_ref",
            "run_id",
            "evidence_signature",
            "origin",
            "status",
            "category_key",
            "attribute_id",
            "value_id",
            "title",
            "short_reason",
            "priority_score",
            "confidence_level",
            "decision_ease",
            "support_product_count",
            "support_retailer_count",
            "reviewer",
            "decision_reason",
            "payload_json",
            "created_at",
            "updated_at",
        ]
        with self._read_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {', '.join(columns)}
                FROM review_queue_items
                WHERE queue_item_id = ?
                """,
                (queue_item_id,),
            ).fetchone()
        if row is None:
            return None
        item = {key: value for key, value in zip(columns, row)}
        payload_raw = item.get("payload_json")
        if isinstance(payload_raw, str) and payload_raw.strip():
            try:
                item["payload_json"] = json.loads(payload_raw)
            except json.JSONDecodeError:
                pass
        return item

    def get_review_queue_item_by_candidate(
        self,
        *,
        candidate_domain: str,
        candidate_type: str,
        candidate_key: str,
    ) -> dict[str, Any] | None:
        columns = [
            "queue_item_id",
            "candidate_domain",
            "candidate_type",
            "candidate_key",
            "aggregated_row_ref",
            "run_id",
            "evidence_signature",
            "origin",
            "status",
            "category_key",
            "attribute_id",
            "value_id",
            "title",
            "short_reason",
            "priority_score",
            "confidence_level",
            "decision_ease",
            "support_product_count",
            "support_retailer_count",
            "reviewer",
            "decision_reason",
            "payload_json",
            "created_at",
            "updated_at",
        ]
        with self._read_connection() as conn:
            row = conn.execute(
                f"""
                SELECT {', '.join(columns)}
                FROM review_queue_items
                WHERE candidate_domain = ?
                  AND candidate_type = ?
                  AND candidate_key = ?
                """,
                (candidate_domain, candidate_type, candidate_key),
            ).fetchone()
        if row is None:
            return None
        item = {key: value for key, value in zip(columns, row)}
        payload_raw = item.get("payload_json")
        if isinstance(payload_raw, str) and payload_raw.strip():
            try:
                item["payload_json"] = json.loads(payload_raw)
            except json.JSONDecodeError:
                pass
        return item

    def update_review_queue_item_status(
        self,
        queue_item_id: str,
        *,
        status: str,
        reviewer: str | None = None,
        decision_reason: str | None = None,
        updated_at: str,
    ) -> dict[str, Any] | None:
        with self._write_connection("update_review_queue_item_status") as conn:
            conn.execute(
                """
                UPDATE review_queue_items
                SET status = ?,
                    reviewer = ?,
                    decision_reason = ?,
                    updated_at = ?
                WHERE queue_item_id = ?
                """,
                (status, reviewer, decision_reason, updated_at, queue_item_id),
            )
            conn.commit()
        return self.get_review_queue_item(queue_item_id)

    def delete_review_queue_items(self, queue_item_ids: list[str]) -> int:
        """Delete queue items by id and return the number of deleted rows."""

        normalized_ids = [
            str(item_id).strip() for item_id in queue_item_ids if str(item_id).strip()
        ]
        if not normalized_ids:
            return 0
        placeholders = ", ".join("?" for _ in normalized_ids)
        with self._write_connection("delete_review_queue_items") as conn:
            cursor = conn.execute(
                f"""
                DELETE FROM review_queue_items
                WHERE queue_item_id IN ({placeholders})
                """,
                normalized_ids,
            )
            conn.commit()
        return int(cursor.rowcount or 0)

    def upsert_explicit_precision_metrics(
        self,
        metrics: Iterable[Mapping[str, Any]],
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for metric in metrics:
            run_id = str(metric.get("run_id") or "").strip()
            computed_at = str(metric.get("computed_at") or "").strip()
            category_key = str(metric.get("category_key") or "").strip().lower()
            attribute_id = str(metric.get("attribute_id") or "").strip()
            if not run_id or not computed_at or not category_key or not attribute_id:
                continue
            rows.append(
                (
                    run_id,
                    computed_at,
                    category_key,
                    attribute_id,
                    int(metric.get("explicit_positive_count") or 0),
                    int(metric.get("deterministic_match_on_explicit") or 0),
                    int(metric.get("llm_match_on_explicit") or 0),
                    float(metric.get("deterministic_precision_proxy") or 0.0),
                    float(metric.get("llm_precision_proxy") or 0.0),
                )
            )
        if not rows:
            return 0
        query = """
            INSERT INTO pdp_explicit_precision_metrics (
                run_id,
                computed_at,
                category_key,
                attribute_id,
                explicit_positive_count,
                deterministic_match_on_explicit,
                llm_match_on_explicit,
                deterministic_precision_proxy,
                llm_precision_proxy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, category_key, attribute_id)
            DO UPDATE SET
                computed_at = excluded.computed_at,
                explicit_positive_count = excluded.explicit_positive_count,
                deterministic_match_on_explicit = excluded.deterministic_match_on_explicit,
                llm_match_on_explicit = excluded.llm_match_on_explicit,
                deterministic_precision_proxy = excluded.deterministic_precision_proxy,
                llm_precision_proxy = excluded.llm_precision_proxy
        """
        with self._write_connection("upsert_explicit_precision_metrics") as conn:
            cursor = conn.executemany(query, rows)
            changes = _cursor_rowcount(cursor)
            conn.commit()
        return changes

    def fetch_explicit_precision_metrics(
        self,
        *,
        run_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        columns = [
            "run_id",
            "computed_at",
            "category_key",
            "attribute_id",
            "explicit_positive_count",
            "deterministic_match_on_explicit",
            "llm_match_on_explicit",
            "deterministic_precision_proxy",
            "llm_precision_proxy",
        ]
        query = f"SELECT {', '.join(columns)} FROM pdp_explicit_precision_metrics"
        params: list[Any] = []
        if run_id:
            query += " WHERE run_id = ?"
            params.append(str(run_id).strip())
        query += (
            " ORDER BY computed_at DESC, category_key ASC, attribute_id ASC LIMIT ?"
        )
        params.append(max(1, int(limit)))
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{key: value for key, value in zip(columns, row)} for row in rows]

    def clear_attribute_values(
        self,
        *,
        retailers: Sequence[str] | None = None,
        sources: Sequence[str] | None = None,
    ) -> None:
        conditions: list[str] = []
        params: list[str] = []
        if retailers:
            placeholders = ",".join("?" for _ in retailers)
            conditions.append(f"retailer IN ({placeholders})")
            params.extend(retailers)
        if sources:
            placeholders = ",".join("?" for _ in sources)
            conditions.append(f"source IN ({placeholders})")
            params.extend(sources)
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._write_connection("clear_attribute_values") as conn:
            conn.execute(f"DELETE FROM pdp_attribute_values{where_clause}", params)
            conn.commit()

    def clear_attribute_values_for_parents(
        self,
        parent_ids: Sequence[str],
        *,
        retailers: Sequence[str] | None = None,
        sources: Sequence[str] | None = None,
        category_keys: Sequence[str] | None = None,
    ) -> None:
        """Remove attribute values for specific parents, optionally scoped to retailers/sources."""
        parent_ids = [pid for pid in parent_ids if str(pid).strip()]
        if not parent_ids:
            return

        def _chunks(seq: Sequence[str], size: int = 400) -> Iterable[Sequence[str]]:
            for i in range(0, len(seq), size):
                yield seq[i : i + size]

        base_conditions: list[str] = []
        base_params: list[str] = []
        if retailers:
            placeholders = ",".join("?" for _ in retailers)
            base_conditions.append(f"retailer IN ({placeholders})")
            base_params.extend(retailers)
        if sources:
            placeholders = ",".join("?" for _ in sources)
            base_conditions.append(f"source IN ({placeholders})")
            base_params.extend(sources)
        if category_keys:
            placeholders = ",".join("?" for _ in category_keys)
            base_conditions.append(f"COALESCE(category_key, '') IN ({placeholders})")
            base_params.extend(category_keys)

        with self._write_connection("clear_attribute_values_for_parents") as conn:
            for chunk in _chunks(parent_ids):
                conditions = list(base_conditions)
                params = list(base_params)
                placeholders = ",".join("?" for _ in chunk)
                conditions.append(f"parent_product_id IN ({placeholders})")
                params.extend(chunk)
                where_clause = (
                    f" WHERE {' AND '.join(conditions)}" if conditions else ""
                )
                conn.execute(f"DELETE FROM pdp_attribute_values{where_clause}", params)
            conn.commit()

    def backfill_attribute_audit_from_values(
        self,
        *,
        sources: Sequence[str] = ("deterministic", "llm"),
        retailers: Sequence[str] | None = None,
        parent_ids: Sequence[str] | None = None,
    ) -> int:
        """Seed missing audit rows from persisted stage snapshots.

        This is a one-way backfill used to recover historical stage values that were
        persisted before explicit audit logging existed. Existing audit rows are
        left untouched, and repeated calls are idempotent.
        """

        source_values = [
            str(source).strip() for source in sources if str(source).strip()
        ]
        if not source_values:
            return 0

        retailer_values = [
            str(retailer).strip()
            for retailer in (retailers or [])
            if str(retailer).strip()
        ]
        parent_values = [
            str(parent).strip() for parent in (parent_ids or []) if str(parent).strip()
        ]

        def _chunks(seq: Sequence[str], size: int = 400) -> Iterable[Sequence[str]]:
            for i in range(0, len(seq), size):
                yield seq[i : i + size]

        def _insert_for_chunk(
            conn: PostgresCompatConnection, parent_chunk: Sequence[str] | None
        ) -> int:
            conditions: list[str] = []
            params: list[str] = []

            source_placeholders = ",".join("?" for _ in source_values)
            conditions.append(f"v.source IN ({source_placeholders})")
            params.extend(source_values)

            if retailer_values:
                retailer_placeholders = ",".join("?" for _ in retailer_values)
                conditions.append(f"v.retailer IN ({retailer_placeholders})")
                params.extend(retailer_values)

            if parent_chunk is not None:
                parent_placeholders = ",".join("?" for _ in parent_chunk)
                conditions.append(f"v.parent_product_id IN ({parent_placeholders})")
                params.extend(parent_chunk)

            where_clause = " AND ".join(conditions)
            query = f"""
                INSERT INTO pdp_attribute_audit (
                    timestamp,
                    source,
                    row_type,
                    retailer,
                    parent_product_id,
                    variant_id,
                    attribute_id,
                    value,
                    decision_rule,
                    evidence_json,
                    category_key
                )
                SELECT
                    v.updated_at,
                    v.source,
                    v.row_type,
                    v.retailer,
                    v.parent_product_id,
                    v.variant_id,
                    v.attribute_id,
                    v.value,
                    CASE
                        WHEN v.source = 'llm' THEN 'llm_stage_value'
                        WHEN v.source = 'deterministic' THEN 'deterministic_stage_value'
                        ELSE v.source || '_stage_value'
                    END,
                    '{{"provenance":"attribute_values_backfill"}}',
                    v.category_key
                FROM pdp_attribute_values v
                WHERE {where_clause}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM pdp_attribute_audit a
                      WHERE COALESCE(a.source, '') = COALESCE(v.source, '')
                        AND COALESCE(a.row_type, '') = COALESCE(v.row_type, '')
                        AND COALESCE(a.retailer, '') = COALESCE(v.retailer, '')
                        AND COALESCE(a.parent_product_id, '') = COALESCE(v.parent_product_id, '')
                        AND COALESCE(a.variant_id, '') = COALESCE(v.variant_id, '')
                        AND COALESCE(a.category_key, '') = COALESCE(v.category_key, '')
                        AND COALESCE(a.attribute_id, '') = COALESCE(v.attribute_id, '')
                        AND COALESCE(a.timestamp, '') = COALESCE(v.updated_at, '')
                        AND COALESCE(a.value, '') = COALESCE(v.value, '')
                  )
            """
            cursor = conn.execute(query, params)
            return _cursor_rowcount(cursor)

        inserted = 0
        with self._write_connection("backfill_attribute_audit_from_values") as conn:
            if parent_values:
                for chunk in _chunks(parent_values):
                    inserted += _insert_for_chunk(conn, chunk)
            else:
                inserted += _insert_for_chunk(conn, None)
            conn.commit()
        return inserted

    def upsert_attribute_values(
        self,
        records: Iterable[AttributeValueRecord],
    ) -> None:
        rows = [
            (
                record.retailer,
                record.row_type,
                record.parent_product_id,
                record.variant_id or "",
                record.category_key or "",
                record.attribute_id,
                record.attribute_label,
                record.value,
                record.oov_candidate,
                record.note,
                record.source,
                record.updated_at,
            )
            for record in records
        ]
        if not rows:
            return
        sql = """
            INSERT INTO pdp_attribute_values (
                retailer, row_type, parent_product_id, variant_id, category_key, attribute_id,
                attribute_label, value, oov_candidate, note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id,
                source
            )
            DO UPDATE SET
                attribute_label = excluded.attribute_label,
                value = excluded.value,
                oov_candidate = excluded.oov_candidate,
                note = excluded.note,
                updated_at = excluded.updated_at
        """
        with self._write_connection("upsert_attribute_values") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def read_attribute_mapping_states(
        self,
        *,
        retailer: str,
        category_key: str,
        source: str = "codex",
    ) -> dict[AttributeMappingIdentity, tuple[AttributeMappingStateRow, ...]]:
        """Return exact current states for source mappings in one category.

        Rows are grouped by the base attribute identity used by correction
        locking. The stable row ordering and ``updated_at`` field make the
        result suitable as a mechanically verifiable compare-and-swap token.
        """

        normalized_retailer = str(retailer or "").strip()
        normalized_category = str(category_key or "").strip()
        normalized_source = str(source or "").strip()
        if not normalized_retailer or not normalized_category or not normalized_source:
            raise ValueError(
                "Attribute mapping state scope requires retailer, category, and source"
            )

        with self._read_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    row_type,
                    parent_product_id,
                    variant_id,
                    attribute_id,
                    attribute_label,
                    value,
                    oov_candidate,
                    note,
                    updated_at
                FROM pdp_attribute_values
                WHERE retailer = ?
                  AND category_key = ?
                  AND source = ?
                ORDER BY
                    row_type,
                    parent_product_id,
                    variant_id,
                    attribute_id
                """,
                (normalized_retailer, normalized_category, normalized_source),
            ).fetchall()

        grouped: dict[AttributeMappingIdentity, list[AttributeMappingStateRow]] = {}
        for (
            row_type,
            parent_product_id,
            variant_id,
            attribute_id,
            attribute_label,
            value,
            oov_candidate,
            note,
            updated_at,
        ) in rows:
            normalized_attribute_id = str(attribute_id)
            identity = AttributeMappingIdentity(
                source=normalized_source,
                retailer=normalized_retailer,
                row_type=str(row_type),
                parent_product_id=str(parent_product_id),
                variant_id=str(variant_id or ""),
                category_key=normalized_category,
                base_attribute_id=normalized_attribute_id.split("__", 1)[0],
            )
            grouped.setdefault(identity, []).append(
                AttributeMappingStateRow(
                    attribute_id=normalized_attribute_id,
                    attribute_label=(
                        None if attribute_label is None else str(attribute_label)
                    ),
                    value=None if value is None else str(value),
                    oov_candidate=(
                        None if oov_candidate is None else str(oov_candidate)
                    ),
                    note=None if note is None else str(note),
                    updated_at=str(updated_at),
                )
            )
        return {identity: tuple(state) for identity, state in grouped.items()}

    def upsert_attribute_values_with_audit(
        self,
        value_records: Iterable[AttributeValueRecord],
        audit_records: Iterable[AttributeAuditRecord],
        *,
        operation_id: str | None = None,
        reject_existing_source_values: bool = False,
        replace_existing_source_values: bool = False,
        expected_existing_source_states: (
            Mapping[AttributeMappingIdentity, Sequence[AttributeMappingStateRow]] | None
        ) = None,
        operation_evidence: Mapping[str, object] | None = None,
        return_operation_result: bool = False,
    ) -> bool | AttributeMappingOperationResult:
        """Write paired values and audits once in one transaction.

        ``reject_existing_source_values`` is used for worksets issued only for
        unresolved cells. ``replace_existing_source_values`` is reserved for
        an explicit, independently reviewed correction workset. Exact database
        identity locks serialize either policy and keep replacement auditable.
        Replacement additionally requires the exact state read when the
        correction workset was built, preventing stale and ABA overwrites.
        """

        value_records = list(value_records)
        audit_records = list(audit_records)
        value_identities = sorted(
            (
                record.source,
                record.row_type,
                record.retailer,
                record.parent_product_id,
                record.variant_id or "",
                record.category_key or "",
                record.attribute_id,
                record.value or "",
            )
            for record in value_records
        )
        audit_identities = sorted(
            (
                record.source,
                record.row_type or "",
                record.retailer or "",
                record.parent_product_id or "",
                record.variant_id or "",
                record.category_key or "",
                record.attribute_id or "",
                record.value or "",
            )
            for record in audit_records
        )
        if value_identities != audit_identities:
            raise ValueError(
                "Atomic attribute writes require one matching audit row per value"
            )
        if operation_id is not None and not re.fullmatch(r"[0-9a-f]{64}", operation_id):
            raise ValueError("Attribute mapping operation_id must be a SHA-256 value")
        if return_operation_result and operation_id is None:
            raise ValueError(
                "A durable attribute mapping operation result requires operation_id"
            )
        if operation_evidence is not None and operation_id is None:
            raise ValueError(
                "Attribute mapping operation evidence requires operation_id"
            )
        marker_evidence_json = _json_dumps(
            {
                "operation_id": operation_id,
                "operation_evidence": dict(operation_evidence or {}),
            }
        )
        if len(marker_evidence_json.encode("utf-8")) > 64 * 1024:
            raise ValueError("Attribute mapping operation evidence exceeds 64 KiB")
        if reject_existing_source_values and replace_existing_source_values:
            raise ValueError(
                "Attribute mapping cannot reject and replace existing values"
            )
        mapping_identities = sorted(
            {
                AttributeMappingIdentity(
                    source=record.source,
                    retailer=record.retailer,
                    row_type=record.row_type,
                    parent_product_id=record.parent_product_id,
                    variant_id=record.variant_id or "",
                    category_key=record.category_key or "",
                    base_attribute_id=record.attribute_id.split("__", 1)[0],
                )
                for record in value_records
            }
        )
        if (
            expected_existing_source_states is not None
            and not replace_existing_source_values
        ):
            raise ValueError(
                "Expected attribute mapping states are only valid for replacement"
            )
        normalized_expected_states: dict[
            AttributeMappingIdentity, tuple[AttributeMappingStateRow, ...]
        ] = {}
        if replace_existing_source_values:
            if expected_existing_source_states is None:
                raise ValueError(
                    "Attribute mapping replacement requires exact expected source states"
                )
            try:
                for raw_identity, raw_states in expected_existing_source_states.items():
                    identity = AttributeMappingIdentity(*raw_identity)
                    states = tuple(
                        sorted(
                            (AttributeMappingStateRow(*row) for row in raw_states),
                            key=lambda row: row.attribute_id,
                        )
                    )
                    normalized_expected_states[identity] = states
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Expected attribute mapping states have an invalid shape"
                ) from exc
            if set(normalized_expected_states) != set(mapping_identities):
                raise ValueError(
                    "Attribute mapping replacement requires one exact expected state "
                    "for every written base identity"
                )
        record_sources = {record.source for record in [*value_records, *audit_records]}
        if operation_id is not None and len(record_sources) > 1:
            raise ValueError("One attribute mapping operation cannot mix sources")
        value_rows = [
            (
                record.retailer,
                record.row_type,
                record.parent_product_id,
                record.variant_id or "",
                record.category_key or "",
                record.attribute_id,
                record.attribute_label,
                record.value,
                record.oov_candidate,
                record.note,
                record.source,
                record.updated_at,
            )
            for record in value_records
        ]
        audit_rows = [
            (
                record.timestamp,
                record.source,
                record.row_type,
                record.retailer,
                record.parent_product_id,
                record.variant_id,
                record.attribute_id,
                record.value,
                record.decision_rule,
                record.evidence_json,
                record.category_key,
            )
            for record in audit_records
        ]
        if not value_rows and not audit_rows and operation_id is None:
            return False
        value_sql = """
            INSERT INTO pdp_attribute_values (
                retailer, row_type, parent_product_id, variant_id, category_key, attribute_id,
                attribute_label, value, oov_candidate, note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id,
                source
            )
            DO UPDATE SET
                attribute_label = excluded.attribute_label,
                value = excluded.value,
                oov_candidate = excluded.oov_candidate,
                note = excluded.note,
                updated_at = excluded.updated_at
        """
        audit_sql = """
            INSERT INTO pdp_attribute_audit (
                timestamp,
                source,
                row_type,
                retailer,
                parent_product_id,
                variant_id,
                attribute_id,
                value,
                decision_rule,
                evidence_json,
                category_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_connection("upsert_attribute_values_with_audit") as conn:
            # This operation implements its own idempotency boundary. Transparent
            # DML replay could bypass the advisory lock and marker recheck after a
            # connection loss, so callers must retry the whole operation instead.
            conn.disable_transaction_replay()
            operation_source = (
                audit_records[0].source
                if audit_records
                else value_records[0].source if value_records else "codex"
            )
            if operation_id is not None:
                conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(?))",
                    (operation_id,),
                )
                already_applied = conn.execute(
                    """
                    SELECT timestamp, evidence_json
                    FROM pdp_attribute_audit
                    WHERE decision_rule = 'codex_mapping_batch'
                      AND value = ?
                    LIMIT 1
                    """,
                    (operation_id,),
                ).fetchone()
                if already_applied is not None:
                    committed_at = str(already_applied[0])
                    if return_operation_result:
                        committed_evidence_json = str(already_applied[1] or "")
                        return AttributeMappingOperationResult(
                            applied=False,
                            committed_at=committed_at,
                            operation_evidence_json=committed_evidence_json,
                        )
                    return False
            if reject_existing_source_values or replace_existing_source_values:
                for identity in mapping_identities:
                    (
                        source,
                        retailer,
                        row_type,
                        parent_id,
                        variant_id,
                        category,
                        base_attribute_id,
                    ) = identity
                    lock_key = ":".join(("attribute-mapping", *identity))
                    conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(?))",
                        (lock_key,),
                    )
                    escaped_base = _like_literal(base_attribute_id)
                    existing_rows = conn.execute(
                        """
                        SELECT
                            attribute_id,
                            attribute_label,
                            value,
                            oov_candidate,
                            note,
                            updated_at
                        FROM pdp_attribute_values
                        WHERE source = ?
                          AND retailer = ?
                          AND row_type = ?
                          AND parent_product_id = ?
                          AND variant_id = ?
                          AND category_key = ?
                          AND (
                              attribute_id = ?
                              OR attribute_id LIKE ? ESCAPE '\\'
                          )
                        ORDER BY attribute_id
                        """,
                        (
                            source,
                            retailer,
                            row_type,
                            parent_id,
                            variant_id,
                            category,
                            base_attribute_id,
                            f"{escaped_base}\\_\\_%",
                        ),
                    ).fetchall()
                    existing_state = tuple(
                        AttributeMappingStateRow(
                            attribute_id=str(attribute_id),
                            attribute_label=(
                                None
                                if attribute_label is None
                                else str(attribute_label)
                            ),
                            value=None if value is None else str(value),
                            oov_candidate=(
                                None if oov_candidate is None else str(oov_candidate)
                            ),
                            note=None if note is None else str(note),
                            updated_at=str(updated_at),
                        )
                        for (
                            attribute_id,
                            attribute_label,
                            value,
                            oov_candidate,
                            note,
                            updated_at,
                        ) in existing_rows
                    )
                    if (
                        replace_existing_source_values
                        and existing_state != normalized_expected_states[identity]
                    ):
                        raise AttributeMappingConflictError(
                            "The accepted mapping changed after the correction "
                            "workset was built for "
                            f"{retailer}/{row_type}/{parent_id}/{variant_id or '-'}"
                            f"/{category}/{base_attribute_id}; rebuild the workset."
                        )
                    existing_rows_are_unresolved = existing_rows and all(
                        _existing_mapping_row_is_unresolved(row.value, row.note)
                        for row in existing_state
                    )
                    if (
                        reject_existing_source_values
                        and existing_rows
                        and not existing_rows_are_unresolved
                    ):
                        raise AttributeMappingConflictError(
                            "An accepted mapping now exists for "
                            f"{retailer}/{row_type}/{parent_id}/{variant_id or '-'}"
                            f"/{category}/{base_attribute_id}; rebuild the workset."
                        )
                    if existing_rows and (
                        replace_existing_source_values or existing_rows_are_unresolved
                    ):
                        conn.execute(
                            """
                            DELETE FROM pdp_attribute_values
                            WHERE source = ?
                              AND retailer = ?
                              AND row_type = ?
                              AND parent_product_id = ?
                              AND variant_id = ?
                              AND category_key = ?
                              AND (
                                  attribute_id = ?
                                  OR attribute_id LIKE ? ESCAPE '\\'
                              )
                            """,
                            (
                                source,
                                retailer,
                                row_type,
                                parent_id,
                                variant_id,
                                category,
                                base_attribute_id,
                                f"{escaped_base}\\_\\_%",
                            ),
                        )
            entity_keys = {
                (
                    record.retailer,
                    record.row_type,
                    record.parent_product_id,
                    record.variant_id or "",
                )
                for record in value_records
            }
            for retailer, row_type, parent_product_id, variant_id in entity_keys:
                parent_exists = conn.execute(
                    """
                    SELECT 1
                    FROM parent_products
                    WHERE retailer = ? AND parent_product_id = ?
                    LIMIT 1
                    """,
                    (retailer, parent_product_id),
                ).fetchone()
                if parent_exists is None:
                    raise ValueError(
                        "Attribute mapping target parent does not exist: "
                        f"{retailer}/{parent_product_id}"
                    )
                if row_type == "variant":
                    variant_exists = conn.execute(
                        """
                        SELECT 1
                        FROM variants
                        WHERE retailer = ? AND parent_product_id = ? AND variant_id = ?
                        LIMIT 1
                        """,
                        (retailer, parent_product_id, variant_id),
                    ).fetchone()
                    if variant_exists is None:
                        raise ValueError(
                            "Attribute mapping target variant does not exist: "
                            f"{retailer}/{parent_product_id}/{variant_id}"
                        )
            if value_rows:
                conn.executemany(value_sql, value_rows)
            if audit_rows:
                conn.executemany(audit_sql, audit_rows)
            if operation_id is not None:
                operation_timestamp = (
                    audit_records[0].timestamp
                    if audit_records
                    else value_records[0].updated_at if value_records else ""
                )
                conn.execute(
                    audit_sql,
                    (
                        operation_timestamp,
                        operation_source,
                        None,
                        None,
                        None,
                        None,
                        None,
                        operation_id,
                        "codex_mapping_batch",
                        marker_evidence_json,
                        None,
                    ),
                )
            conn.commit()
        if return_operation_result:
            return AttributeMappingOperationResult(
                applied=True,
                committed_at=operation_timestamp,
                operation_evidence_json=marker_evidence_json,
            )
        return True

    def write_attribute_cache_entries(
        self,
        entries: dict[str, bytes],
        *,
        generated_at: str,
    ) -> None:
        if not entries:
            return
        rows = [(name, payload, generated_at) for name, payload in entries.items()]
        sql = """
            INSERT INTO pdp_attribute_cache (name, payload, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                payload = excluded.payload,
                generated_at = excluded.generated_at
        """
        with self._write_connection("write_attribute_cache_entries") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def read_attribute_cache_entries(self) -> dict[str, tuple[bytes, str]]:
        with self._read_connection() as conn:
            rows = conn.execute(
                "SELECT name, payload, generated_at FROM pdp_attribute_cache"
            ).fetchall()
        return {name: (payload, generated_at) for name, payload, generated_at in rows}

    def clear_attribute_cache(self, *, names: Sequence[str] | None = None) -> None:
        if names:
            placeholders = ",".join("?" for _ in names)
            query = f"DELETE FROM pdp_attribute_cache WHERE name IN ({placeholders})"
            params: Sequence[str] = list(names)
        else:
            query = "DELETE FROM pdp_attribute_cache"
            params = ()
        with self._write_connection("clear_attribute_cache") as conn:
            conn.execute(query, params)
            conn.commit()

    def _ensure_attribute_resolution_tables(self) -> None:
        with self._write_connection("ensure_attribute_resolution_tables") as conn:
            conn.execute(ATTRIBUTE_RESOLUTION_LEDGER_TABLE_SQL)
            conn.execute(ATTRIBUTE_RESOLUTION_CONSENSUS_TABLE_SQL)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pdp_attribute_resolution_ledger_lookup
                ON pdp_attribute_resolution_ledger (
                    row_type,
                    retailer,
                    parent_product_id,
                    variant_id,
                    category_key,
                    attribute_id,
                    recorded_at
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pdp_attribute_resolution_ledger_run
                ON pdp_attribute_resolution_ledger (run_id)
            """)
            conn.commit()

    def append_attribute_resolution_ledger_rows(
        self,
        rows: Sequence[dict[str, object]],
    ) -> None:
        if not rows:
            return
        self._ensure_attribute_resolution_tables()
        prepared = [
            (
                uuid.uuid4().hex,
                str(row.get("run_id") or ""),
                row.get("recorded_at"),
                row.get("step"),
                row.get("source"),
                row.get("decision_rule"),
                row.get("row_type"),
                row.get("retailer"),
                row.get("parent_product_id"),
                row.get("variant_id"),
                row.get("canonical_id"),
                row.get("category_key"),
                row.get("attribute_id"),
                row.get("value"),
                row.get("confidence"),
                row.get("evidence_url"),
            )
            for row in rows
        ]
        sql = """
            INSERT INTO pdp_attribute_resolution_ledger (
                row_id,
                run_id,
                recorded_at,
                step,
                source,
                decision_rule,
                row_type,
                retailer,
                parent_product_id,
                variant_id,
                canonical_id,
                category_key,
                attribute_id,
                value,
                confidence,
                evidence_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_id) DO NOTHING
        """
        with self._write_connection("append_attribute_resolution_ledger_rows") as conn:
            conn.executemany(sql, prepared)
            conn.commit()

    def read_attribute_resolution_ledger_rows(self) -> list[dict[str, object]]:
        self._ensure_attribute_resolution_tables()
        columns = [
            "run_id",
            "recorded_at",
            "step",
            "source",
            "decision_rule",
            "row_type",
            "retailer",
            "parent_product_id",
            "variant_id",
            "canonical_id",
            "category_key",
            "attribute_id",
            "value",
            "confidence",
            "evidence_url",
        ]
        with self._read_connection() as conn:
            rows = conn.execute("""
                SELECT
                    run_id,
                    recorded_at,
                    step,
                    source,
                    decision_rule,
                    row_type,
                    retailer,
                    parent_product_id,
                    variant_id,
                    canonical_id,
                    category_key,
                    attribute_id,
                    value,
                    confidence,
                    evidence_url
                FROM pdp_attribute_resolution_ledger
                ORDER BY recorded_at, run_id
                """).fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def write_attribute_resolution_consensus_rows(
        self,
        rows: Sequence[dict[str, object]],
    ) -> None:
        self._ensure_attribute_resolution_tables()
        prepared = [
            (
                str(row.get("row_type") or ""),
                str(row.get("retailer") or ""),
                str(row.get("parent_product_id") or ""),
                str(row.get("variant_id") or ""),
                str(row.get("canonical_id") or ""),
                str(row.get("category_key") or ""),
                str(row.get("attribute_id") or ""),
                row.get("consensus_value"),
                row.get("support_runs"),
                row.get("total_runs"),
                row.get("agreement_rate"),
                row.get("step_count"),
                _json_dumps(row.get("supporting_steps") or []),
                row.get("certainty_class"),
                row.get("max_confidence"),
                row.get("last_seen_at"),
                row.get("last_recorded_at"),
            )
            for row in rows
        ]
        sql = """
            INSERT INTO pdp_attribute_resolution_consensus (
                row_type,
                retailer,
                parent_product_id,
                variant_id,
                canonical_id,
                category_key,
                attribute_id,
                consensus_value,
                support_runs,
                total_runs,
                agreement_rate,
                step_count,
                supporting_steps_json,
                certainty_class,
                max_confidence,
                last_seen_at,
                last_recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                row_type,
                retailer,
                parent_product_id,
                variant_id,
                canonical_id,
                category_key,
                attribute_id
            )
            DO UPDATE SET
                consensus_value = excluded.consensus_value,
                support_runs = excluded.support_runs,
                total_runs = excluded.total_runs,
                agreement_rate = excluded.agreement_rate,
                step_count = excluded.step_count,
                supporting_steps_json = excluded.supporting_steps_json,
                certainty_class = excluded.certainty_class,
                max_confidence = excluded.max_confidence,
                last_seen_at = excluded.last_seen_at,
                last_recorded_at = excluded.last_recorded_at
        """
        with self._write_connection(
            "write_attribute_resolution_consensus_rows"
        ) as conn:
            conn.execute("DELETE FROM pdp_attribute_resolution_consensus")
            if prepared:
                conn.executemany(sql, prepared)
            conn.commit()

    def read_attribute_resolution_consensus_rows(self) -> list[dict[str, object]]:
        self._ensure_attribute_resolution_tables()
        columns = [
            "row_type",
            "retailer",
            "parent_product_id",
            "variant_id",
            "canonical_id",
            "category_key",
            "attribute_id",
            "consensus_value",
            "support_runs",
            "total_runs",
            "agreement_rate",
            "step_count",
            "supporting_steps_json",
            "certainty_class",
            "max_confidence",
            "last_seen_at",
            "last_recorded_at",
        ]
        with self._read_connection() as conn:
            rows = conn.execute("""
                SELECT
                    row_type,
                    retailer,
                    parent_product_id,
                    variant_id,
                    canonical_id,
                    category_key,
                    attribute_id,
                    consensus_value,
                    support_runs,
                    total_runs,
                    agreement_rate,
                    step_count,
                    supporting_steps_json,
                    certainty_class,
                    max_confidence,
                    last_seen_at,
                    last_recorded_at
                FROM pdp_attribute_resolution_consensus
                """).fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            item = dict(zip(columns, row))
            raw_steps = item.pop("supporting_steps_json", None)
            try:
                supporting_steps = json.loads(str(raw_steps or "[]"))
            except json.JSONDecodeError:
                supporting_steps = []
            item["supporting_steps"] = (
                supporting_steps if isinstance(supporting_steps, list) else []
            )
            result.append(item)
        return result

    def get_canonical_owners(self, canonical_ids: Iterable[str]) -> dict[str, str]:
        ids = [cid for cid in canonical_ids if cid]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        query = (
            f"SELECT canonical_id, retailer FROM canonical_products "
            f"WHERE canonical_id IN ({placeholders})"
        )
        with self._read_connection() as conn:
            rows = conn.execute(query, ids).fetchall()
        return {row[0]: row[1] for row in rows}

    def claim_canonical_products(
        self,
        records: Iterable[CanonicalProductRecord],
    ) -> None:
        rows = [
            (
                record.canonical_id,
                record.brand_normalized,
                record.name_normalized,
                record.retailer,
                record.parent_product_id,
                record.captured_at,
            )
            for record in records
        ]
        if not rows:
            return
        sql = """
            INSERT INTO canonical_products (
                canonical_id,
                brand_normalized,
                name_normalized,
                retailer,
                parent_product_id,
                captured_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_id) DO UPDATE SET
                parent_product_id = excluded.parent_product_id,
                captured_at = excluded.captured_at
            WHERE canonical_products.retailer = excluded.retailer
        """
        with self._write_connection("claim_canonical_products") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def existing_parent_ids(self, retailer: str) -> set[str]:
        with self._read_connection() as conn:
            rows = conn.execute(
                "SELECT parent_product_id FROM parent_products WHERE retailer = ?",
                (retailer,),
            ).fetchall()
        return {row[0] for row in rows}

    def existing_pdp_urls(self, retailer: str) -> set[str]:
        with self._read_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT pdp_url
                FROM parent_products
                WHERE retailer = ? AND COALESCE(TRIM(pdp_url), '') != ''
                """,
                (retailer,),
            ).fetchall()
        return {str(row[0]) for row in rows if row and row[0]}

    def _append_listing_observations(
        self,
        *,
        owner: str,
        crawl_ts: str,
        observations: Iterable[ListingObservation],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        for observation in observations:
            rows.append(
                (
                    crawl_ts,
                    observation.retailer,
                    observation.category_key,
                    observation.source_surface,
                    observation.sort_mode,
                    int(observation.page),
                    int(observation.position),
                    observation.pdp_url,
                    observation.parent_product_id,
                    observation.product_name,
                    observation.brand,
                    int(observation.has_new_badge),
                    observation.listing_url,
                )
            )
        if not rows:
            return
        sql = """
            INSERT OR REPLACE INTO retailer_listing_observations (
                crawl_ts,
                retailer,
                category_key,
                source_surface,
                sort_mode,
                page,
                position,
                pdp_url,
                parent_product_id,
                product_name,
                brand,
                has_new_badge,
                listing_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_connection(owner) as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def _append_filter_observations(
        self,
        *,
        owner: str,
        crawl_ts: str,
        observations: Iterable[FilterObservation],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        attribute_values: dict[tuple[str, str, str, str], set[str]] = {}
        for observation in observations:
            parent_id = str(observation.parent_product_id or "").strip()
            filter_family = str(observation.filter_family or "").strip()
            filter_value = str(observation.filter_value or "").strip()
            rows.append(
                (
                    crawl_ts,
                    observation.retailer,
                    observation.category_key,
                    filter_family,
                    filter_value,
                    observation.source_surface,
                    observation.pdp_url,
                    observation.parent_product_id,
                    int(observation.page),
                    int(observation.position),
                    observation.listing_url,
                )
            )
            if parent_id and filter_family and filter_value:
                filter_groups = _filter_attribute_group_values(
                    filter_family,
                    filter_value,
                    category_key=observation.category_key,
                    retailer=observation.retailer,
                )
                for canonical_filter_family, grouped_value in filter_groups:
                    key = (
                        str(observation.retailer or "").strip(),
                        parent_id,
                        str(observation.category_key or "").strip(),
                        canonical_filter_family,
                    )
                    attribute_values.setdefault(key, set()).add(grouped_value)
        if not rows:
            return
        sql = """
            INSERT OR REPLACE INTO retailer_filter_observations (
                crawl_ts,
                retailer,
                category_key,
                filter_family,
                filter_value,
                source_surface,
                pdp_url,
                parent_product_id,
                page,
                position,
                listing_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        attribute_rows = [
            (
                retailer,
                "parent",
                parent_id,
                "",
                category_key,
                filter_family,
                _filter_attribute_label(filter_family, category_key),
                ATTRIBUTE_MULTI_VALUE_SEPARATOR.join(
                    _normalize_filter_attribute_values(
                        filter_family,
                        sorted(values),
                        category_key=category_key,
                        retailer=retailer,
                    )
                ),
                None,
                "materialized from retailer_filter_observations",
                FILTER_ATTRIBUTE_SOURCE,
                crawl_ts,
            )
            for (
                retailer,
                parent_id,
                category_key,
                filter_family,
            ), values in sorted(attribute_values.items())
        ]
        attribute_sql = """
            INSERT INTO pdp_attribute_values (
                retailer, row_type, parent_product_id, variant_id, category_key, attribute_id,
                attribute_label, value, oov_candidate, note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id,
                source
            )
            DO UPDATE SET
                attribute_label = excluded.attribute_label,
                value = excluded.value,
                oov_candidate = excluded.oov_candidate,
                note = excluded.note,
                updated_at = excluded.updated_at
        """
        with self._write_connection(owner) as conn:
            conn.executemany(sql, rows)
            if attribute_rows:
                conn.executemany(attribute_sql, attribute_rows)
            conn.commit()

    def materialize_retailer_filter_attributes(
        self,
        *,
        retailer: str | None = None,
        category_key: str | None = None,
        crawl_ts: str | None = None,
        replace_existing: bool = False,
    ) -> int:
        """Materialize existing retailer filter observations as attribute values."""
        conditions = [
            "parent_product_id IS NOT NULL",
            "TRIM(parent_product_id) <> ''",
            "TRIM(filter_family) <> ''",
            "TRIM(filter_value) <> ''",
        ]
        params: list[str] = []
        if retailer:
            conditions.append("retailer = ?")
            params.append(str(retailer).strip())
        if category_key:
            conditions.append("category_key = ?")
            params.append(str(category_key).strip())
        if crawl_ts:
            conditions.append("crawl_ts = ?")
            params.append(str(crawl_ts).strip())
        query = """
            SELECT
                retailer,
                parent_product_id,
                category_key,
                filter_family,
                filter_value,
                MAX(crawl_ts) AS updated_at
            FROM retailer_filter_observations
            WHERE """
        query += " AND ".join(conditions)
        query += """
            GROUP BY
                retailer,
                parent_product_id,
                category_key,
                filter_family,
                filter_value
        """
        grouped_values: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        for (
            row_retailer,
            parent_id,
            row_category_key,
            filter_family,
            filter_value,
            updated_at,
        ) in rows:
            filter_groups = _filter_attribute_group_values(
                str(filter_family or ""),
                str(filter_value or ""),
                category_key=str(row_category_key or ""),
                retailer=str(row_retailer or ""),
            )
            for canonical_filter_family, grouped_value in filter_groups:
                key = (
                    str(row_retailer or "").strip(),
                    str(parent_id or "").strip(),
                    str(row_category_key or "").strip(),
                    canonical_filter_family,
                )
                if not all(key):
                    continue
                payload = grouped_values.setdefault(
                    key,
                    {"values": set(), "updated_at": str(updated_at or "")},
                )
                payload["values"].add(grouped_value)
                if str(updated_at or "") > str(payload["updated_at"] or ""):
                    payload["updated_at"] = str(updated_at or "")

        attribute_rows = [
            (
                row_retailer,
                "parent",
                parent_id,
                "",
                row_category_key,
                filter_family,
                _filter_attribute_label(filter_family, row_category_key),
                ATTRIBUTE_MULTI_VALUE_SEPARATOR.join(
                    _normalize_filter_attribute_values(
                        filter_family,
                        sorted(payload["values"]),
                        category_key=row_category_key,
                        retailer=row_retailer,
                    )
                ),
                None,
                "materialized from retailer_filter_observations",
                FILTER_ATTRIBUTE_SOURCE,
                payload["updated_at"],
            )
            for (
                row_retailer,
                parent_id,
                row_category_key,
                filter_family,
            ), payload in sorted(grouped_values.items())
        ]
        if not attribute_rows:
            return 0
        sql = """
            INSERT INTO pdp_attribute_values (
                retailer, row_type, parent_product_id, variant_id, category_key, attribute_id,
                attribute_label, value, oov_candidate, note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                retailer,
                row_type,
                parent_product_id,
                variant_id,
                category_key,
                attribute_id,
                source
            )
            DO UPDATE SET
                attribute_label = excluded.attribute_label,
                value = excluded.value,
                oov_candidate = excluded.oov_candidate,
                note = excluded.note,
                updated_at = excluded.updated_at
        """
        with self._write_connection("materialize_retailer_filter_attributes") as conn:
            if replace_existing:
                delete_conditions = ["source = ?"]
                delete_params: list[str] = [FILTER_ATTRIBUTE_SOURCE]
                if retailer:
                    delete_conditions.append("retailer = ?")
                    delete_params.append(str(retailer).strip())
                if category_key:
                    delete_conditions.append("category_key = ?")
                    delete_params.append(str(category_key).strip())
                conn.execute(
                    "DELETE FROM pdp_attribute_values WHERE "
                    + " AND ".join(delete_conditions),
                    delete_params,
                )
            conn.executemany(sql, attribute_rows)
            conn.commit()
        return len(attribute_rows)

    def retailer_filter_normalization_gaps(
        self,
        *,
        retailer: str,
        category_key: str,
    ) -> list[dict[str, Any]]:
        """Return materialized retailer-filter values outside the category taxonomy."""
        _, attr_labels, value_aliases_by_attr = _taxonomy_attribute_lookup(category_key)
        valid_values_by_attr = {
            attr_id: set(value_aliases.values())
            for attr_id, value_aliases in value_aliases_by_attr.items()
        }
        with self._read_connection() as conn:
            rows = conn.execute(
                """
                SELECT attribute_id, value, COUNT(*) AS row_count
                FROM pdp_attribute_values
                WHERE retailer = ?
                  AND category_key = ?
                  AND source = ?
                GROUP BY attribute_id, value
                ORDER BY attribute_id, value
                """,
                (retailer, category_key, FILTER_ATTRIBUTE_SOURCE),
            ).fetchall()

        gaps: list[dict[str, Any]] = []
        for attribute_id, raw_value, row_count in rows:
            attr_id = str(attribute_id or "").strip()
            if not attr_id or attr_id == "brand":
                continue
            if attr_id not in attr_labels:
                gaps.append(
                    {
                        "attribute_id": attr_id,
                        "value": str(raw_value or ""),
                        "row_count": int(row_count or 0),
                        "reason": "unknown_attribute",
                    }
                )
                continue
            valid_values = valid_values_by_attr.get(attr_id, set())
            if not valid_values:
                continue
            for value in str(raw_value or "").split(ATTRIBUTE_MULTI_VALUE_SEPARATOR):
                normalized_value = value.strip()
                if not normalized_value or normalized_value in {
                    "N/A",
                    "not in taxonomy",
                }:
                    continue
                if normalized_value in valid_values:
                    continue
                gaps.append(
                    {
                        "attribute_id": attr_id,
                        "value": normalized_value,
                        "row_count": int(row_count or 0),
                        "reason": "unknown_value",
                    }
                )
        return gaps

    def append_retailer_listing_observations(
        self,
        *,
        crawl_ts: str,
        observations: Iterable[ListingObservation],
    ) -> None:
        self._append_listing_observations(
            owner="append_retailer_listing_observations",
            crawl_ts=crawl_ts,
            observations=observations,
        )

    def append_retailer_filter_surfaces(
        self,
        *,
        crawl_ts: str,
        surfaces: Iterable[FilterSurface],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        for surface in surfaces:
            rows.append(
                (
                    crawl_ts,
                    surface.retailer,
                    surface.category_key,
                    surface.filter_family,
                    surface.filter_value,
                    surface.filter_url,
                    surface.filter_label,
                )
            )
        if not rows:
            return
        sql = """
            INSERT OR REPLACE INTO retailer_filter_surfaces (
                crawl_ts,
                retailer,
                category_key,
                filter_family,
                filter_value,
                filter_url,
                filter_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self._write_connection("append_retailer_filter_surfaces") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def append_retailer_filter_observations(
        self,
        *,
        crawl_ts: str,
        observations: Iterable[FilterObservation],
    ) -> None:
        self._append_filter_observations(
            owner="append_retailer_filter_observations",
            crawl_ts=crawl_ts,
            observations=observations,
        )

    def append_retailer_sitemap_observations(
        self,
        *,
        crawl_ts: str,
        observations: Iterable[SitemapObservation],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        for observation in observations:
            rows.append(
                (
                    crawl_ts,
                    observation.retailer,
                    observation.sitemap_source,
                    observation.url,
                    observation.lastmod,
                    observation.url_type,
                )
            )
        if not rows:
            return
        sql = """
            INSERT OR REPLACE INTO retailer_sitemap_observations (
                crawl_ts,
                retailer,
                sitemap_source,
                url,
                lastmod,
                url_type
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._write_connection("append_retailer_sitemap_observations") as conn:
            conn.executemany(sql, rows)
            conn.commit()

    def fetch_retailer_seen_listing_identities(
        self,
        *,
        retailer: str,
        before_crawl_ts: str | None = None,
    ) -> set[str]:
        query = """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(parent_product_id), ''), pdp_url)
            FROM retailer_listing_observations
            WHERE retailer = ?
        """
        params: tuple[str, ...] = (retailer,)
        if before_crawl_ts:
            query += " AND crawl_ts < ?"
            params = (retailer, before_crawl_ts)
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return {str(row[0]) for row in rows if row and row[0]}

    def count_parents(self, retailer: str | None = None) -> int:
        return self._count_rows("parent_products", retailer)

    def count_variants(self, retailer: str | None = None) -> int:
        return self._count_rows("variants", retailer)

    def _count_rows(self, table: str, retailer: str | None = None) -> int:
        query = f"SELECT COUNT(*) FROM {table}"
        params: tuple[()] | tuple[str] = ()
        if retailer:
            query += " WHERE retailer = ?"
            params = (retailer,)
        with self._read_connection() as conn:
            result = conn.execute(query, params).fetchone()
        return int(result[0]) if result and result[0] is not None else 0

    def delete_parent_with_variants(self, retailer: str, parent_product_id: str) -> int:
        parent_key = str(parent_product_id or "").strip()
        retailer_key = str(retailer or "").strip()
        if not retailer_key or not parent_key:
            return 0
        with self._write_connection("delete_parent_with_variants") as conn:
            conn.execute(
                "DELETE FROM variants WHERE retailer = ? AND parent_product_id = ?",
                (retailer_key, parent_key),
            )
            cursor = conn.execute(
                "DELETE FROM parent_products WHERE retailer = ? AND parent_product_id = ?",
                (retailer_key, parent_key),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def parent_ids_for_variant_ids(
        self, retailer: str, variant_ids: Sequence[str]
    ) -> dict[str, str]:
        retailer_key = str(retailer or "").strip()
        normalized_variant_ids = [
            str(variant_id).strip()
            for variant_id in variant_ids
            if str(variant_id).strip()
        ]
        if not retailer_key or not normalized_variant_ids:
            return {}
        deduped_variant_ids = list(dict.fromkeys(normalized_variant_ids))

        def _chunks(values: Sequence[str], size: int = 400) -> Iterable[Sequence[str]]:
            for idx in range(0, len(values), size):
                yield values[idx : idx + size]

        rows: list[tuple[str, str]] = []
        with self._read_connection() as conn:
            for chunk in _chunks(deduped_variant_ids):
                placeholders = ",".join("?" for _ in chunk)
                cursor = conn.execute(
                    f"""
                    SELECT variant_id, parent_product_id
                    FROM variants
                    WHERE retailer = ? AND variant_id IN ({placeholders})
                    """,
                    (retailer_key, *chunk),
                )
                rows.extend(
                    (str(variant_id), str(parent_product_id))
                    for variant_id, parent_product_id in cursor.fetchall()
                    if variant_id and parent_product_id
                )

        mapping: dict[str, str] = {}
        for variant_id, parent_product_id in rows:
            mapping.setdefault(variant_id, parent_product_id)
        return mapping

    def write_batch(
        self,
        batch: BatchParseResult,
        summary: dict[str, object] | None = None,
        *,
        overwrite: bool = False,
    ) -> dict[str, int]:
        parents = list(batch.parents())
        variants = list(batch.variants())
        run_id = batch.generated_at.isoformat()

        metrics = {
            "logged_failures": 0,
            "newly_discontinued": 0,
            "reactivated": 0,
        }

        with self._write_connection("write_batch") as conn:
            existing_variant_images: dict[
                tuple[str, str], tuple[str | None, str | None]
            ] = {}
            if overwrite and parents:
                parent_ids = [parent.parent_product_id for parent in parents]
                if parent_ids:
                    placeholders = ",".join("?" for _ in parent_ids)
                    cur = conn.cursor()
                    cur.execute(
                        f"""
                        SELECT parent_product_id, variant_id, hero_image_url, swatch_image_url
                        FROM variants
                        WHERE retailer = ? AND parent_product_id IN ({placeholders})
                        """,
                        (batch.retailer, *parent_ids),
                    )
                    for pid, vid, hero, swatch in cur.fetchall():
                        if pid and vid:
                            existing_variant_images[(str(pid), str(vid))] = (
                                hero,
                                swatch,
                            )

                parent_ids = [
                    (parent.retailer, parent.parent_product_id) for parent in parents
                ]
                conn.executemany(
                    "DELETE FROM variants WHERE retailer = ? AND parent_product_id = ?",
                    parent_ids,
                )
                conn.executemany(
                    "DELETE FROM parent_products WHERE retailer = ? AND parent_product_id = ?",
                    parent_ids,
                )

            parent_rows = [
                (
                    parent.retailer,
                    parent.parent_product_id,
                    parent.pdp_url,
                    parent.brand_raw,
                    parent.brand_normalized,
                    parent.title_raw,
                    parent.title_normalized,
                    parent.series_label_raw,
                    _json_dumps(list(parent.category_path)),
                    1 if parent.has_color_selector else 0,
                    _json_dumps(list(parent.qa_flags)),
                    _json_dumps(parent.extras),
                    run_id,
                    run_id,
                    run_id,
                    None,
                )
                for parent in parents
            ]
            if parent_rows:
                insert_parent_sql = (
                    """
                    INSERT OR REPLACE INTO parent_products (
                        retailer, parent_product_id, pdp_url, brand_raw, brand_normalized,
                        title_raw, title_normalized, series_label_raw, category_path,
                        has_color_selector, qa_flags, extras, batch_generated_at,
                        discovered_at, last_seen_at, discontinued_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    if overwrite
                    else """
                    INSERT OR IGNORE INTO parent_products (
                        retailer, parent_product_id, pdp_url, brand_raw, brand_normalized,
                        title_raw, title_normalized, series_label_raw, category_path,
                        has_color_selector, qa_flags, extras, batch_generated_at,
                        discovered_at, last_seen_at, discontinued_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                )
                conn.executemany(insert_parent_sql, parent_rows)

            reactivated = self._refresh_last_seen(
                conn,
                [(parent.retailer, parent.parent_product_id) for parent in parents],
                run_id,
            )
            metrics["reactivated"] = reactivated

            variant_rows = [
                (
                    variant.retailer,
                    variant.variant_id,
                    variant.parent_product_id,
                    variant.shade_name_raw,
                    variant.shade_name_normalized,
                    variant.size_text_raw,
                    variant.price_raw,
                    (
                        float(variant.price)
                        if isinstance(variant.price, Decimal)
                        else variant.price
                    ),
                    variant.currency,
                    variant.barcode,
                    variant.swatch_image_url
                    or existing_variant_images.get(
                        (variant.parent_product_id, variant.variant_id), (None, None)
                    )[1],
                    variant.hero_image_url
                    or existing_variant_images.get(
                        (variant.parent_product_id, variant.variant_id), (None, None)
                    )[0],
                    variant.availability,
                    variant.source_index,
                    _json_dumps(list(variant.qa_flags)),
                    _json_dumps(variant.extras),
                    run_id,
                )
                for variant in variants
            ]
            if variant_rows:
                insert_variant_sql = (
                    """
                    INSERT OR REPLACE INTO variants (
                        retailer, variant_id, parent_product_id, shade_name_raw,
                        shade_name_normalized, size_text_raw, price_raw, price,
                        currency, barcode, swatch_image_url, hero_image_url,
                        availability, source_index, qa_flags, extras, batch_generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    if overwrite
                    else """
                    INSERT OR IGNORE INTO variants (
                        retailer, variant_id, parent_product_id, shade_name_raw,
                        shade_name_normalized, size_text_raw, price_raw, price,
                        currency, barcode, swatch_image_url, hero_image_url,
                        availability, source_index, qa_flags, extras, batch_generated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                )
                conn.executemany(insert_variant_sql, variant_rows)

            failure_records = self._record_failures(conn, batch, run_id)
            metrics["logged_failures"] = len(failure_records)
            if failure_records:
                metrics["newly_discontinued"] = self._update_discontinued_status(
                    conn,
                    batch.retailer,
                    failure_records,
                    run_id,
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO run_logs (
                    run_id, retailer, profile, parsed_count, failed_count, generated_at, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    batch.retailer,
                    batch.profile_name,
                    len(parents),
                    len(batch.failures),
                    run_id,
                    _json_dumps(summary or {}),
                ),
            )
            conn.commit()
        return metrics

    def _refresh_last_seen(
        self,
        conn: PostgresCompatConnection,
        retailers_and_ids: Sequence[tuple[str, str]],
        run_id: str,
    ) -> int:
        reactivated = 0
        if not retailers_and_ids:
            return reactivated
        select_sql = """
            SELECT discontinued_at FROM parent_products
            WHERE retailer = ? AND parent_product_id = ?
        """
        update_sql = """
            UPDATE parent_products
            SET last_seen_at = ?, discontinued_at = NULL
            WHERE retailer = ? AND parent_product_id = ?
        """
        for retailer, parent_id in retailers_and_ids:
            row = conn.execute(
                select_sql,
                (retailer, parent_id),
            ).fetchone()
            if row is None:
                continue
            if row[0] is not None:
                reactivated += 1
            conn.execute(
                update_sql,
                (run_id, retailer, parent_id),
            )
        return reactivated

    def _record_failures(
        self,
        conn: PostgresCompatConnection,
        batch: BatchParseResult,
        run_id: str,
    ) -> list[FailureRecord]:
        if not batch.failures:
            return []
        records = [_parse_failure_detail(detail) for detail in batch.failures]
        params = [
            (
                run_id,
                batch.retailer,
                batch.profile_name,
                record.url,
                record.status_code,
                record.message,
                run_id,
            )
            for record in records
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO pdp_failures (
                run_id, retailer, profile, pdp_url, status_code, message, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        return records

    def _update_discontinued_status(
        self,
        conn: PostgresCompatConnection,
        retailer: str,
        failures: Iterable[FailureRecord],
        run_id: str,
    ) -> int:
        discontinued = 0
        for failure in failures:
            if failure.status_code not in (404, 410):
                continue
            row = conn.execute(
                """
                SELECT parent_product_id, last_seen_at, discontinued_at
                FROM parent_products
                WHERE retailer = ? AND pdp_url = ?
                """,
                (retailer, failure.url),
            ).fetchone()
            if row is None:
                continue
            parent_id, last_seen_at, discontinued_at = row
            if discontinued_at:
                continue
            since = last_seen_at or ""
            count_row = conn.execute(
                """
                SELECT COUNT(*) FROM pdp_failures
                WHERE retailer = ?
                  AND pdp_url = ?
                  AND status_code IN (404, 410)
                  AND recorded_at >= ?
                """,
                (retailer, failure.url, since),
            ).fetchone()
            consecutive = count_row[0] if count_row else 0
            if consecutive >= 2:
                conn.execute(
                    """
                    UPDATE parent_products
                    SET discontinued_at = ?
                    WHERE retailer = ? AND parent_product_id = ?
                    """,
                    (run_id, retailer, parent_id),
                )
                discontinued += 1
        return discontinued

    def update_parent_reviews(
        self,
        batch: BatchParseResult,
        summary: dict[str, object] | None = None,
    ) -> dict[str, int]:
        parents = list(batch.parents())
        run_id = batch.generated_at.isoformat()

        metrics = {
            "logged_failures": 0,
            "newly_discontinued": 0,
            "reactivated": 0,
        }

        if not parents and not batch.failures:
            return metrics

        with self._write_connection("update_parent_reviews") as conn:

            update_sql = """
                UPDATE parent_products
                SET pdp_url = ?, brand_raw = ?, brand_normalized = ?, title_raw = ?, title_normalized = ?,
                    series_label_raw = ?, category_path = ?, has_color_selector = ?, qa_flags = ?, extras = ?,
                    batch_generated_at = ?
                WHERE retailer = ? AND parent_product_id = ?
            """
            updated_ids: list[tuple[str, str]] = []
            for parent in parents:
                category_json = _json_dumps(list(parent.category_path))
                qa_json = _json_dumps(list(parent.qa_flags))
                extras_json = _json_dumps(parent.extras)

                params = (
                    parent.pdp_url,
                    parent.brand_raw,
                    parent.brand_normalized,
                    parent.title_raw,
                    parent.title_normalized,
                    parent.series_label_raw,
                    category_json,
                    1 if parent.has_color_selector else 0,
                    qa_json,
                    extras_json,
                    run_id,
                    parent.retailer,
                    parent.parent_product_id,
                )
                cursor = conn.execute(update_sql, params)
                if cursor.rowcount == 0:
                    _logger.warning(
                        "Skipping reviews refresh for missing parent (retailer=%s, parent_product_id=%s, url=%s)",
                        parent.retailer,
                        parent.parent_product_id,
                        parent.pdp_url,
                    )
                    continue
                updated_ids.append((parent.retailer, parent.parent_product_id))

            if updated_ids:
                reactivated = self._refresh_last_seen(conn, updated_ids, run_id)
                metrics["reactivated"] = reactivated

            failure_records = self._record_failures(conn, batch, run_id)
            metrics["logged_failures"] = len(failure_records)
            if failure_records:
                metrics["newly_discontinued"] = self._update_discontinued_status(
                    conn,
                    batch.retailer,
                    failure_records,
                    run_id,
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO run_logs (
                    run_id, retailer, profile, parsed_count, failed_count, generated_at, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    batch.retailer,
                    batch.profile_name,
                    len(updated_ids),
                    len(batch.failures),
                    run_id,
                    _json_dumps(summary or {}),
                ),
            )
            conn.commit()
        return metrics
