from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from modules.llm.batch_runner import run_step_json
from modules.llm.model_router import query_llm_return_json
from modules.pdp.review_units import canonical_review_units_from_payload
from modules.utilities.config import get_naming_params

__all__ = [
    "REVIEW_THEME_PIPELINE_VERSION",
    "ProductReviewContext",
    "ReviewRecord",
    "ReviewTheme",
    "ReviewThemeTag",
    "build_review_records_from_contexts",
    "discover_review_theme_codebook",
    "ensure_review_theme_schema",
    "fetch_parent_review_context_rows",
    "persist_review_theme_run",
    "sample_reviews_by_stratum",
    "sanitize_codebook_response",
    "sanitize_tag_response",
    "tag_reviews_with_codebook",
]

LOGGER = logging.getLogger(__name__)

REVIEW_THEME_PIPELINE_VERSION = "review_theme_codebook_v1"
REVIEW_THEME_DISCOVERY_PROMPT_VERSION = "review_theme_discovery_v1"
REVIEW_THEME_TAG_PROMPT_VERSION = "review_theme_tag_v1"

LOW_RATING_THRESHOLD = 2.0
MAX_REVIEW_TEXT_CHARS = 1400
MAX_EVIDENCE_CHARS = 320

_VALID_POLARITIES = {"positive", "negative", "mixed"}
_DEFAULT_ACTORS = {
    "buyer",
    "customer",
    "owner",
    "cat",
    "dog",
    "pet",
    "wearer",
    "user",
    "recipient",
    "unspecified",
}
_DEFAULT_TARGETS = {
    "product",
    "food",
    "packaging",
    "shipping",
    "price",
    "brand",
    "seller",
    "variant",
    "unspecified",
}
_ID_STOPWORDS = {
    "and",
    "but",
    "for",
    "from",
    "into",
    "of",
    "the",
    "this",
    "to",
    "with",
}
_DEFAULT_DISCOVERY_STRATA = (
    "top_sellers",
    "non_top_sellers",
    "new_products",
    "successful_new_products",
    "weak_low_rated",
)
_NEUTRAL_BATCH_LABELS = tuple(f"Batch {chr(ord('A') + index)}" for index in range(26))


@dataclass(frozen=True)
class ProductReviewContext:
    retailer: str
    category_key: str
    parent_product_id: str
    product_name: str | None
    brand: str | None
    pdp_url: str | None
    extras: Mapping[str, Any]
    is_top_seller: bool = False
    is_new_launch: bool = False


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    retailer: str
    category_key: str
    parent_product_id: str
    product_name: str | None
    brand: str | None
    pdp_url: str | None
    review_hash: str
    review_unit_index: int
    source: str
    headline: str | None
    comment: str | None
    text: str
    rating: float | None
    review_created_date: str | None
    is_top_seller: bool
    is_new_launch: bool


@dataclass(frozen=True)
class ReviewTheme:
    theme_id: str
    theme_label: str
    theme_family: str
    description: str
    inclusion_notes: str | None = None
    exclusion_notes: str | None = None
    example_phrases: tuple[str, ...] = ()
    sort_order: int = 0


@dataclass(frozen=True)
class ReviewThemeTag:
    tag_id: str
    review_id: str
    parent_product_id: str
    theme_id: str
    theme_label: str
    polarity: str
    evidence_span: str
    target: str
    actor: str
    confidence: float | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.replace("\x00", " ").split())
    return text or None


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_json_text(value: object | None) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _add_column_if_missing(
    conn: Any,
    *,
    table: str,
    column: str,
    definition: str,
) -> None:
    conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")


def _hash_text(*parts: object) -> str:
    return hashlib.sha256(_json_dumps(parts).encode("utf-8")).hexdigest()


def _coerce_float(value: object | None) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _normalize_category_key(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    return "_".join(text.casefold().replace("-", "_").split())


def _normalize_brand(value: str | None) -> str | None:
    text = _clean_text(value)
    return text.casefold() if text else None


def _brand_matches_focus(
    brand: str | None,
    focus_brand_keys: set[str],
) -> bool:
    brand_key = _normalize_brand(brand)
    if not brand_key:
        return False
    for focus_key in focus_brand_keys:
        if brand_key == focus_key:
            return True
        if brand_key.startswith(f"{focus_key} "):
            return True
        if brand_key.endswith(f" {focus_key}"):
            return True
        if f" {focus_key} " in brand_key:
            return True
    return False


def _category_from_extras(extras: Mapping[str, Any]) -> str | None:
    direct = _clean_text(extras.get("category_key"))
    if direct:
        return direct
    category_path = extras.get("category_path")
    if isinstance(category_path, str):
        try:
            category_path = json.loads(category_path)
        except json.JSONDecodeError:
            return category_path
    if isinstance(category_path, Sequence) and not isinstance(
        category_path, (str, bytes, bytearray)
    ):
        parts = [_clean_text(part) for part in category_path]
        parts = [part for part in parts if part]
        return parts[-1] if parts else None
    return None


def _review_context_categories_by_parent(
    conn: Any,
    *,
    retailer: str,
    category_keys: set[str],
    parent_ids: Sequence[str] | None,
) -> dict[str, set[str]]:
    clauses = ["retailer = ?"]
    params: list[object] = [retailer]
    if category_keys:
        placeholders = ",".join("?" for _ in category_keys)
        clauses.append(f"category_key IN ({placeholders})")
        params.extend(sorted(category_keys))
    if parent_ids:
        placeholders = ",".join("?" for _ in parent_ids)
        clauses.append(f"parent_product_id IN ({placeholders})")
        params.extend(parent_ids)
    rows = conn.execute(
        f"""
        SELECT DISTINCT parent_product_id, category_key
        FROM retailer_listing_observations
        WHERE {' AND '.join(clauses)}
          AND parent_product_id IS NOT NULL
          AND category_key IS NOT NULL
        """,
        tuple(params),
    ).fetchall()
    by_parent: dict[str, set[str]] = {}
    for parent_id, raw_category_key in rows:
        category_key = _normalize_category_key(str(raw_category_key))
        if not category_key:
            continue
        by_parent.setdefault(str(parent_id), set()).add(category_key)
    return by_parent


def _slug(value: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token and token not in _ID_STOPWORDS
    ]
    slug = "_".join(tokens[:8])
    return slug or "review_theme"


def _review_text(headline: str | None, comment: str | None) -> str | None:
    text = ". ".join(part for part in (headline, comment) if part)
    text = _clean_text(text)
    if not text:
        return None
    if len(text) <= MAX_REVIEW_TEXT_CHARS:
        return text
    return text[:MAX_REVIEW_TEXT_CHARS].rsplit(" ", 1)[0].strip()


def fetch_parent_review_context_rows(
    conn: Any,
    *,
    retailer: str,
    category_keys: Sequence[str] | None = None,
    parent_ids: Sequence[str] | None = None,
) -> tuple[ProductReviewContext, ...]:
    """Fetch parent products with raw reviews from the PDP store."""

    clauses = ["retailer = ?"]
    params: list[object] = [retailer]
    if parent_ids:
        placeholders = ",".join("?" for _ in parent_ids)
        clauses.append(f"parent_product_id IN ({placeholders})")
        params.extend(parent_ids)
    query = f"""
        SELECT parent_product_id, title_raw, brand_raw, pdp_url, extras
        FROM parent_products
        WHERE {' AND '.join(clauses)}
    """
    normalized_categories = {
        key
        for key in (_normalize_category_key(value) for value in category_keys or ())
        if key
    }
    listing_categories_by_parent = _review_context_categories_by_parent(
        conn,
        retailer=retailer,
        category_keys=normalized_categories,
        parent_ids=parent_ids,
    )
    contexts: list[ProductReviewContext] = []
    for parent_id, title_raw, brand_raw, pdp_url, extras_raw in conn.execute(
        query,
        tuple(params),
    ).fetchall():
        extras = _parse_json_text(extras_raw)
        review_units = canonical_review_units_from_payload(extras)
        if not review_units:
            continue
        parent_key = str(parent_id)
        categories = set(listing_categories_by_parent.get(parent_key, set()))
        extras_category = _normalize_category_key(_category_from_extras(extras))
        if extras_category:
            categories.add(extras_category)
        if normalized_categories:
            categories &= normalized_categories
        if not categories:
            continue
        brand = _clean_text(brand_raw)
        for category_key in sorted(categories):
            contexts.append(
                ProductReviewContext(
                    retailer=retailer,
                    category_key=category_key,
                    parent_product_id=parent_key,
                    product_name=_clean_text(title_raw),
                    brand=brand,
                    pdp_url=_clean_text(pdp_url),
                    extras=extras,
                )
            )
    return tuple(contexts)


def build_review_records_from_contexts(
    contexts: Sequence[ProductReviewContext],
) -> tuple[ReviewRecord, ...]:
    """Build deduplicated review records from parent product contexts."""

    records: list[ReviewRecord] = []
    seen: set[str] = set()
    for context in contexts:
        for index, unit in enumerate(
            canonical_review_units_from_payload(context.extras),
            start=1,
        ):
            headline = _clean_text(unit.get("headline"))
            comment = _clean_text(unit.get("comment"))
            text = _review_text(headline, comment)
            if not text:
                continue
            rating = _coerce_float(unit.get("rating"))
            review_created_date = _clean_text(unit.get("created_date"))
            review_hash = _hash_text(
                context.retailer,
                context.category_key,
                context.parent_product_id,
                unit.get("source"),
                headline,
                comment,
                rating,
                review_created_date,
            )
            review_id = _hash_text(
                REVIEW_THEME_PIPELINE_VERSION,
                context.retailer,
                context.category_key,
                context.parent_product_id,
                review_hash,
            )
            if review_id in seen:
                continue
            seen.add(review_id)
            records.append(
                ReviewRecord(
                    review_id=review_id,
                    retailer=context.retailer,
                    category_key=context.category_key,
                    parent_product_id=context.parent_product_id,
                    product_name=context.product_name,
                    brand=context.brand,
                    pdp_url=context.pdp_url,
                    review_hash=review_hash,
                    review_unit_index=index,
                    source=str(unit.get("source") or "review"),
                    headline=headline,
                    comment=comment,
                    text=text,
                    rating=rating,
                    review_created_date=review_created_date,
                    is_top_seller=context.is_top_seller,
                    is_new_launch=context.is_new_launch,
                )
            )
    return tuple(records)


def sample_reviews_by_stratum(
    records: Sequence[ReviewRecord],
    *,
    reviews_per_stratum: int = 50,
    seed: int = 42,
    stratum_names: Sequence[str] | None = None,
    focus_brands: Sequence[str] | None = None,
) -> dict[str, tuple[ReviewRecord, ...]]:
    """Sample reviews by discovery stratum while limiting product dominance."""

    rng = random.Random(seed)
    focus_brand_keys = {
        key for key in (_normalize_brand(value) for value in focus_brands or ()) if key
    }
    all_strata: dict[str, Callable[[ReviewRecord], bool]] = {
        "top_sellers": lambda row: row.is_top_seller,
        "non_top_sellers": lambda row: not row.is_top_seller,
        "new_products": lambda row: row.is_new_launch,
        "successful_new_products": lambda row: row.is_new_launch and row.is_top_seller,
        "target_brand": lambda row: bool(focus_brand_keys)
        and _brand_matches_focus(row.brand, focus_brand_keys),
        "weak_low_rated": (
            lambda row: row.rating is not None and row.rating <= LOW_RATING_THRESHOLD
        ),
        "general_random": lambda row: True,
    }
    selected = tuple(stratum_names or _default_discovery_strata(focus_brand_keys))
    sampled: dict[str, tuple[ReviewRecord, ...]] = {}
    globally_seen: set[str] = set()
    for stratum_name in selected:
        predicate = all_strata[stratum_name]
        candidates = [record for record in records if predicate(record)]
        picked = _sample_product_first(
            candidates,
            limit=reviews_per_stratum,
            rng=rng,
            excluded_review_ids=globally_seen,
        )
        if not picked and globally_seen:
            picked = _sample_product_first(
                candidates,
                limit=reviews_per_stratum,
                rng=rng,
                excluded_review_ids=set(),
            )
        sampled[stratum_name] = tuple(picked)
        globally_seen.update(record.review_id for record in picked)
    return sampled


def _default_discovery_strata(focus_brand_keys: set[str]) -> tuple[str, ...]:
    if not focus_brand_keys:
        return _DEFAULT_DISCOVERY_STRATA
    return (
        "top_sellers",
        "non_top_sellers",
        "new_products",
        "successful_new_products",
        "target_brand",
        "weak_low_rated",
    )


def _sample_product_first(
    records: Sequence[ReviewRecord],
    *,
    limit: int,
    rng: random.Random,
    excluded_review_ids: set[str],
) -> list[ReviewRecord]:
    if limit <= 0:
        return []
    by_product: dict[str, list[ReviewRecord]] = {}
    for record in records:
        if record.review_id in excluded_review_ids:
            continue
        by_product.setdefault(record.parent_product_id, []).append(record)
    product_ids = list(by_product)
    rng.shuffle(product_ids)
    for product_records in by_product.values():
        rng.shuffle(product_records)
    picked: list[ReviewRecord] = []
    while product_ids and len(picked) < limit:
        next_product_ids: list[str] = []
        for product_id in product_ids:
            product_records = by_product[product_id]
            if not product_records:
                continue
            picked.append(product_records.pop())
            if len(picked) >= limit:
                break
            if product_records:
                next_product_ids.append(product_id)
        product_ids = next_product_ids
        rng.shuffle(product_ids)
    return picked


def discover_review_theme_codebook(
    llm_wrapper: object,
    *,
    retailer: str,
    category_key: str,
    sampled_records_by_stratum: Mapping[str, Sequence[ReviewRecord]],
    max_themes: int = 15,
    max_parent_themes: int = 10,
    service_tier: str | None = None,
) -> tuple[ReviewTheme, ...]:
    """Use neutralized stratified batches to create a frozen theme codebook."""

    naming = get_naming_params()
    query_step = naming["pdpReviewThemeDiscoveryQuery"]
    non_empty_batches = [
        (stratum, tuple(records))
        for stratum, records in sampled_records_by_stratum.items()
        if records
    ]
    if not non_empty_batches:
        raise ValueError("Review theme discovery received no sampled reviews.")
    candidate_prompts: list[str] = []
    batch_labels: list[str] = []
    for index, (_stratum, records) in enumerate(non_empty_batches):
        batch_label = _neutral_batch_label(index)
        batch_labels.append(batch_label)
        candidate_prompts.append(
            _theme_candidate_user_prompt(
                retailer=retailer,
                category_key=category_key,
                batch_label=batch_label,
                records=records,
                max_themes=max_themes,
                max_parent_themes=max_parent_themes,
            )
        )
    candidate_responses = run_step_json(
        llm_wrapper,
        query_step,
        _theme_candidate_system_prompt(
            max_themes=max_themes,
            max_parent_themes=max_parent_themes,
        ),
        candidate_prompts,
        service_tier=service_tier,
        reasoning_effort="high",
    )
    candidate_batches = _candidate_batches_from_responses(
        batch_labels=batch_labels,
        responses=candidate_responses,
        max_themes=max_themes,
    )
    if not candidate_batches:
        raise ValueError("Review theme discovery returned no candidate themes.")
    response = run_step_json(
        llm_wrapper,
        query_step,
        _theme_merge_system_prompt(
            max_themes=max_themes,
            max_parent_themes=max_parent_themes,
        ),
        _theme_merge_user_prompt(
            retailer=retailer,
            category_key=category_key,
            candidate_batches=candidate_batches,
            max_themes=max_themes,
            max_parent_themes=max_parent_themes,
        ),
        service_tier=service_tier,
        reasoning_effort="high",
    )[0]
    themes = sanitize_codebook_response(response, max_themes=max_themes)
    if not themes:
        raise ValueError("Review theme discovery returned no usable themes.")
    return themes


def _neutral_batch_label(index: int) -> str:
    if index < len(_NEUTRAL_BATCH_LABELS):
        return _NEUTRAL_BATCH_LABELS[index]
    return f"Batch {index + 1}"


def _theme_candidate_system_prompt(
    *,
    max_themes: int,
    max_parent_themes: int,
) -> str:
    return (
        "You extract candidate review-theme codebook entries from one neutral batch. "
        "Return json only. Do not tag every review. Do not infer what the batch means. "
        "Batch labels are arbitrary and carry no commercial meaning. Do not create "
        "product-specific, nutrition-fact, price-history, or anecdotal themes. "
        "Themes must be broad post-purchase experience concepts that can be measured "
        "across products. "
        f"Return at most {max_parent_themes} parent themes and at most {max_themes} total subthemes. "
        "These are hard budgets: if there "
        "are more candidate ideas, merge narrower ideas into broader measurable "
        "parent themes or subthemes rather than creating extra entries."
    )


def _theme_candidate_user_prompt(
    *,
    retailer: str,
    category_key: str,
    batch_label: str,
    records: Sequence[ReviewRecord],
    max_themes: int,
    max_parent_themes: int,
) -> str:
    payload: dict[str, Any] = {
        "retailer": retailer,
        "category_key": category_key,
        "batch_label": batch_label,
        "task": (
            "Infer candidate reusable review themes from this neutral batch. "
            "This is not the final codebook. Another step will merge candidates "
            "from all batches."
        ),
        "rules": [
            "The batch label is neutral; do not infer cohort findings, commercial differences, rank status, or brand meaning.",
            "Use parent themes such as cat acceptance / refusal, texture / moisture, digestive tolerance, owner sensory reaction, packaging / delivery condition, value / price, portion / pack size, repeat purchase / loyalty, ingredient / health perception.",
            "Use subthemes only for distinctions that can plausibly matter commercially.",
            f"Never exceed {max_parent_themes} parent themes or {max_themes} total subthemes. Merge narrow candidates into broader themes when needed.",
            "Do not create themes that can only apply to one product, one review, one SKU, one nutrition panel, or one shipping anecdote.",
            "Use plain English parent_label and subtheme_label values. IDs may be snake_case but are internal only.",
            "Return json with key parent_themes.",
        ],
        "output_schema": {
            "parent_themes": [
                {
                    "parent_id": "stable_parent_id",
                    "parent_label": "plain English parent theme",
                    "subthemes": [
                        {
                            "subtheme_id": "stable_subtheme_id",
                            "subtheme_label": "plain English subtheme",
                            "description": "what to tag",
                            "inclusion_notes": "optional",
                            "exclusion_notes": "optional",
                            "example_phrases": ["optional short examples"],
                        }
                    ],
                }
            ]
        },
        "max_themes": max_themes,
        "max_parent_themes": max_parent_themes,
        "reviews": [
            {
                "review_id": record.review_id,
                "rating": record.rating,
                "text": record.text,
            }
            for record in records
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _theme_merge_system_prompt(
    *,
    max_themes: int,
    max_parent_themes: int,
) -> str:
    return (
        "You merge candidate review themes into one fixed two-level codebook. "
        "Return json only. Do not tag reviews. Do not infer cohort findings, "
        "sales explanations, or business conclusions from batch membership. "
        "Batch labels are arbitrary and carry no commercial meaning. Merge aggressively: "
        "synonyms and narrow phrases should collapse into broad measurable themes. "
        f"Return at most {max_parent_themes} parent themes and at most {max_themes} total subthemes."
    )


def _theme_merge_user_prompt(
    *,
    retailer: str,
    category_key: str,
    candidate_batches: Sequence[Mapping[str, object]],
    max_themes: int,
    max_parent_themes: int,
) -> str:
    payload: dict[str, Any] = {
        "retailer": retailer,
        "category_key": category_key,
        "task": (
            "Merge these neutral-batch candidate themes into the final frozen "
            "review-theme codebook used to tag the full corpus."
        ),
        "rules": [
            "Batch labels are neutral; do not infer cohort findings or commercial meaning from them.",
            "Keep only reusable post-purchase experience themes.",
            "Merge aggressively across batches: cat likes it, eats it, loves it, and cleans bowl should usually be one acceptance theme unless a narrower subtheme is clearly distinct and measurable.",
            "Do not create product-specific, SKU-specific, formula-table, or anecdotal themes.",
            "Preserve polarity for tagging later; do not encode polarity into the theme label unless the experience is inherently a complaint or praise type.",
            f"Never exceed {max_parent_themes} parent themes or {max_themes} total subthemes.",
            "Return json with key parent_themes.",
        ],
        "output_schema": {
            "parent_themes": [
                {
                    "parent_id": "stable_parent_id",
                    "parent_label": "plain English parent theme",
                    "subthemes": [
                        {
                            "subtheme_id": "stable_subtheme_id",
                            "subtheme_label": "plain English subtheme",
                            "description": "what to tag",
                            "inclusion_notes": "optional",
                            "exclusion_notes": "optional",
                            "example_phrases": ["optional short examples"],
                        }
                    ],
                }
            ]
        },
        "max_themes": max_themes,
        "max_parent_themes": max_parent_themes,
        "candidate_batches": list(candidate_batches),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _candidate_batches_from_responses(
    *,
    batch_labels: Sequence[str],
    responses: Sequence[Mapping[str, Any]],
    max_themes: int,
) -> tuple[dict[str, object], ...]:
    candidate_batches: list[dict[str, object]] = []
    for batch_label, response in zip(batch_labels, responses):
        themes = sanitize_codebook_response(
            response if isinstance(response, Mapping) else {},
            max_themes=max_themes,
        )
        if not themes:
            continue
        candidate_batches.append(
            {
                "batch_label": batch_label,
                "candidate_parent_themes": _themes_to_parent_payload(themes),
            }
        )
    return tuple(candidate_batches)


def _themes_to_parent_payload(themes: Sequence[ReviewTheme]) -> list[dict[str, object]]:
    grouped: dict[str, list[ReviewTheme]] = {}
    for theme in themes:
        grouped.setdefault(theme.theme_family, []).append(theme)
    out: list[dict[str, object]] = []
    for parent_label, parent_themes in grouped.items():
        out.append(
            {
                "parent_label": parent_label,
                "subthemes": [
                    {
                        "subtheme_label": theme.theme_label,
                        "description": theme.description,
                        "inclusion_notes": theme.inclusion_notes,
                        "exclusion_notes": theme.exclusion_notes,
                        "example_phrases": list(theme.example_phrases),
                    }
                    for theme in parent_themes
                ],
            }
        )
    return out


def sanitize_codebook_response(
    response: Mapping[str, Any],
    *,
    max_themes: int,
) -> tuple[ReviewTheme, ...]:
    themes: list[ReviewTheme] = []
    seen_ids: set[str] = set()
    raw_parent_themes = response.get("parent_themes")
    if isinstance(raw_parent_themes, Sequence) and not isinstance(
        raw_parent_themes, (str, bytes, bytearray)
    ):
        for raw_parent in raw_parent_themes:
            if not isinstance(raw_parent, Mapping):
                continue
            parent_label = _clean_text(
                raw_parent.get("parent_label")
                or raw_parent.get("theme_family")
                or raw_parent.get("label")
            )
            if not parent_label or not _theme_label_is_allowed(parent_label):
                continue
            parent_id = _slug(str(raw_parent.get("parent_id") or parent_label))
            raw_subthemes = raw_parent.get("subthemes")
            if not isinstance(raw_subthemes, Sequence) or isinstance(
                raw_subthemes,
                (str, bytes, bytearray),
            ):
                continue
            for raw_subtheme in raw_subthemes:
                if not isinstance(raw_subtheme, Mapping):
                    continue
                label = _clean_text(
                    raw_subtheme.get("subtheme_label")
                    or raw_subtheme.get("theme_label")
                    or raw_subtheme.get("label")
                    or raw_subtheme.get("theme")
                )
                if not label or not _theme_label_is_allowed(label):
                    continue
                subtheme_id = _slug(str(raw_subtheme.get("subtheme_id") or label))
                theme_id = f"{parent_id}__{subtheme_id}"
                if theme_id in seen_ids:
                    continue
                seen_ids.add(theme_id)
                examples = raw_subtheme.get("example_phrases")
                example_phrases = _clean_example_phrases(examples)
                themes.append(
                    ReviewTheme(
                        theme_id=theme_id,
                        theme_label=label,
                        theme_family=parent_label,
                        description=_clean_text(raw_subtheme.get("description"))
                        or label,
                        inclusion_notes=_clean_text(
                            raw_subtheme.get("inclusion_notes")
                        ),
                        exclusion_notes=_clean_text(
                            raw_subtheme.get("exclusion_notes")
                        ),
                        example_phrases=example_phrases,
                        sort_order=len(themes) + 1,
                    )
                )
                if len(themes) >= max_themes:
                    return tuple(themes)
        if themes:
            return tuple(themes)

    raw_themes = response.get("themes")
    if not isinstance(raw_themes, Sequence) or isinstance(
        raw_themes, (str, bytes, bytearray)
    ):
        return ()
    for raw in raw_themes:
        if not isinstance(raw, Mapping):
            continue
        label = _clean_text(
            raw.get("theme_label") or raw.get("label") or raw.get("theme")
        )
        if not label or not _theme_label_is_allowed(label):
            continue
        raw_id = _clean_text(raw.get("theme_id"))
        theme_id = _slug(raw_id or label)
        if theme_id in {"other", "unmapped", "misc", "miscellaneous"}:
            continue
        if theme_id in seen_ids:
            continue
        seen_ids.add(theme_id)
        example_phrases = _clean_example_phrases(raw.get("example_phrases"))
        themes.append(
            ReviewTheme(
                theme_id=theme_id,
                theme_label=label,
                theme_family=_clean_text(raw.get("theme_family")) or "experience",
                description=_clean_text(raw.get("description")) or label,
                inclusion_notes=_clean_text(raw.get("inclusion_notes")),
                exclusion_notes=_clean_text(raw.get("exclusion_notes")),
                example_phrases=example_phrases,
                sort_order=len(themes) + 1,
            )
        )
        if len(themes) >= max_themes:
            break
    return tuple(themes)


def _clean_example_phrases(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(phrase for phrase in (_clean_text(item) for item in value) if phrase)[
        :6
    ]


def _theme_label_is_allowed(label: str) -> bool:
    if len(label) > 70:
        return False
    if len(label.split()) > 8:
        return False
    if len(re.findall(r"\d", label)) > 0:
        return False
    return True


def tag_reviews_with_codebook(
    llm_wrapper: object,
    *,
    records: Sequence[ReviewRecord],
    themes: Sequence[ReviewTheme],
    service_tier: str | None = None,
    retry_missing: int | bool = 1,
    force_sequential: bool = False,
    tag_batch_size: int = 25,
) -> tuple[ReviewThemeTag, ...]:
    """Tag reviews against a frozen codebook. Unknown themes are rejected."""

    if not records or not themes:
        return ()
    naming = get_naming_params()
    query_step = naming["pdpReviewThemeTagQuery"]
    system_prompt = _tag_review_system_prompt()
    theme_by_id = {theme.theme_id: theme for theme in themes}
    record_batches = _chunk_sequence(records, max(1, tag_batch_size))
    batch_prompts = [
        _tag_review_batch_prompt(record_batch, themes)
        for record_batch in record_batches
    ]
    if force_sequential:
        batch_responses = [
            query_llm_return_json(
                llm_wrapper,
                query_step,
                system_prompt,
                prompt,
                service_tier=service_tier,
                reasoning_effort="none",
            )
            for prompt in batch_prompts
        ]
    else:
        batch_responses = run_step_json(
            llm_wrapper,
            query_step,
            system_prompt,
            batch_prompts,
            service_tier=service_tier,
            retry_missing=retry_missing,
        )
    tags: list[ReviewThemeTag] = []
    for record_batch, response in zip(record_batches, batch_responses):
        records_by_id = {record.review_id: record for record in record_batch}
        for record, record_response in _iter_batch_tag_responses(
            response if isinstance(response, Mapping) else {},
            records_by_id=records_by_id,
        ):
            tags.extend(
                sanitize_tag_response(
                    record_response,
                    record=record,
                    theme_by_id=theme_by_id,
                )
            )
    return _dedupe_review_theme_tags(tags)


def _chunk_sequence(
    records: Sequence[ReviewRecord],
    chunk_size: int,
) -> tuple[tuple[ReviewRecord, ...], ...]:
    return tuple(
        tuple(records[index : index + chunk_size])
        for index in range(0, len(records), chunk_size)
    )


def _iter_batch_tag_responses(
    response: Mapping[str, Any],
    *,
    records_by_id: Mapping[str, ReviewRecord],
) -> tuple[tuple[ReviewRecord, Mapping[str, Any]], ...]:
    raw_reviews = response.get("reviews")
    if not isinstance(raw_reviews, Sequence) or isinstance(
        raw_reviews,
        (str, bytes, bytearray),
    ):
        return ()
    out: list[tuple[ReviewRecord, Mapping[str, Any]]] = []
    for raw_review in raw_reviews:
        if not isinstance(raw_review, Mapping):
            continue
        review_id = _clean_text(raw_review.get("review_id"))
        if not review_id:
            continue
        record = records_by_id.get(review_id)
        if record is None:
            continue
        out.append((record, {"themes": raw_review.get("themes") or []}))
    return tuple(out)


def _tag_review_batch_prompt(
    records: Sequence[ReviewRecord],
    themes: Sequence[ReviewTheme],
) -> str:
    payload = {
        "reviews": [
            {
                "review_id": record.review_id,
                "product_name": record.product_name,
                "brand": record.brand,
                "rating": record.rating,
                "text": record.text,
            }
            for record in records
        ],
        "allowed_themes": _allowed_theme_payload(themes),
        "rules": _tagging_rules(),
        "output_schema": {
            "reviews": [
                {
                    "review_id": "one_input_review_id",
                    "themes": [
                        {
                            "theme_id": "one_allowed_theme_id",
                            "polarity": "positive | negative | mixed",
                            "evidence_span": "short quote",
                            "target": "product | food | packaging | shipping | price | variant | unspecified",
                            "actor": "cat | dog | pet | buyer | wearer | user | unspecified",
                            "confidence": 0.0,
                        }
                    ],
                }
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _allowed_theme_payload(themes: Sequence[ReviewTheme]) -> list[dict[str, object]]:
    return [
        {
            "theme_id": theme.theme_id,
            "parent_theme": theme.theme_family,
            "subtheme": theme.theme_label,
            "description": theme.description,
            "inclusion_notes": theme.inclusion_notes,
            "exclusion_notes": theme.exclusion_notes,
        }
        for theme in themes
    ]


def _tagging_rules() -> list[str]:
    return [
        "Return zero or more themes from allowed_themes.",
        "Do not create new themes, buckets, or labels.",
        "If no allowed theme fits a review, return that review with an empty themes array.",
        "Each theme must include polarity: positive, negative, or mixed.",
        "Keep parent/subtheme separate from polarity. A review can mention a subtheme negatively.",
        "Use a short evidence_span from the review text.",
        "Use actor and target when clear; otherwise use unspecified.",
    ]


def _tag_review_system_prompt() -> str:
    return (
        "Tag reviews against a frozen review-theme codebook. Return json only. "
        "Use only the provided theme_id values in allowed_themes. Do not invent "
        "new theme_id values. If no theme fits a review, return an empty themes array."
    )


def _tag_review_prompt(record: ReviewRecord, themes: Sequence[ReviewTheme]) -> str:
    payload = {
        "review": {
            "review_id": record.review_id,
            "product_name": record.product_name,
            "brand": record.brand,
            "rating": record.rating,
            "text": record.text,
        },
        "allowed_themes": _allowed_theme_payload(themes),
        "rules": _tagging_rules(),
        "output_schema": {
            "review_id": record.review_id,
            "themes": [
                {
                    "theme_id": "one_allowed_theme_id",
                    "polarity": "positive | negative | mixed",
                    "evidence_span": "short quote",
                    "target": "product | food | packaging | shipping | price | variant | unspecified",
                    "actor": "cat | dog | pet | buyer | wearer | user | unspecified",
                    "confidence": 0.0,
                }
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def sanitize_tag_response(
    response: Mapping[str, Any],
    *,
    record: ReviewRecord,
    theme_by_id: Mapping[str, ReviewTheme],
) -> tuple[ReviewThemeTag, ...]:
    tags: list[ReviewThemeTag] = []
    seen_tag_ids: set[str] = set()
    raw_tags = response.get("themes") or response.get("tags") or []
    if isinstance(raw_tags, Sequence) and not isinstance(
        raw_tags, (str, bytes, bytearray)
    ):
        for raw in raw_tags:
            if not isinstance(raw, Mapping):
                continue
            raw_theme_id = _clean_text(raw.get("theme_id") or raw.get("theme"))
            if not raw_theme_id:
                continue
            theme_id = raw_theme_id
            theme = theme_by_id.get(theme_id)
            if theme is None:
                theme_id = _slug(raw_theme_id)
                theme = theme_by_id.get(theme_id)
            if theme is None:
                continue
            evidence = _clean_evidence(raw.get("evidence_span") or raw.get("evidence"))
            if not evidence:
                continue
            polarity = _clean_polarity(raw.get("polarity"))
            target = _clean_taxon(raw.get("target"), _DEFAULT_TARGETS)
            actor = _clean_taxon(raw.get("actor"), _DEFAULT_ACTORS)
            confidence = _clean_confidence(raw.get("confidence"))
            tag_id = _hash_text(
                REVIEW_THEME_PIPELINE_VERSION,
                record.review_id,
                theme.theme_id,
                polarity,
                evidence.casefold(),
            )
            if tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            tags.append(
                ReviewThemeTag(
                    tag_id=tag_id,
                    review_id=record.review_id,
                    parent_product_id=record.parent_product_id,
                    theme_id=theme.theme_id,
                    theme_label=theme.theme_label,
                    polarity=polarity,
                    evidence_span=evidence,
                    target=target,
                    actor=actor,
                    confidence=confidence,
                )
            )
    return tuple(tags)


def _dedupe_review_theme_tags(
    tags: Sequence[ReviewThemeTag],
) -> tuple[ReviewThemeTag, ...]:
    deduped: list[ReviewThemeTag] = []
    seen_tag_ids: set[str] = set()
    for tag in tags:
        if tag.tag_id in seen_tag_ids:
            continue
        seen_tag_ids.add(tag.tag_id)
        deduped.append(tag)
    return tuple(deduped)


def _clean_polarity(value: object | None) -> str:
    text = _clean_text(value)
    if not text:
        return "mixed"
    normalized = text.casefold()
    if normalized in {"neutral", "unclear"}:
        return "mixed"
    return normalized if normalized in _VALID_POLARITIES else "mixed"


def _clean_taxon(value: object | None, allowed: set[str]) -> str:
    text = _clean_text(value)
    if not text:
        return "unspecified"
    normalized = _slug(text)
    return normalized if normalized in allowed else "unspecified"


def _clean_confidence(value: object | None) -> float | None:
    parsed = _coerce_float(value)
    if parsed is None:
        return None
    return max(0.0, min(1.0, parsed))


def _clean_evidence(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    return text[:MAX_EVIDENCE_CHARS].rsplit(" ", 1)[0].strip()


def _safe_rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _polarity_counts(tags: Sequence[ReviewThemeTag]) -> dict[str, int]:
    counts = {"positive": 0, "negative": 0, "mixed": 0}
    for tag in tags:
        counts[tag.polarity if tag.polarity in counts else "mixed"] += 1
    return counts


def _representative_evidence(
    tags: Sequence[ReviewThemeTag],
    records_by_id: Mapping[str, ReviewRecord],
    *,
    limit: int = 5,
) -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    seen: set[str] = set()
    for tag in sorted(
        tags,
        key=lambda item: (
            item.polarity != "negative",
            -(item.confidence or 0.0),
            item.evidence_span,
        ),
    ):
        key = tag.evidence_span.casefold()
        if key in seen:
            continue
        seen.add(key)
        record = records_by_id.get(tag.review_id)
        examples.append(
            {
                "evidence": tag.evidence_span,
                "polarity": tag.polarity,
                "actor": tag.actor,
                "target": tag.target,
                "brand": record.brand if record else None,
                "product_name": record.product_name if record else None,
                "rating": record.rating if record else None,
            }
        )
        if len(examples) >= limit:
            break
    return examples


def _build_product_theme_rollups(
    *,
    records: Sequence[ReviewRecord],
    themes: Sequence[ReviewTheme],
    tags: Sequence[ReviewThemeTag],
) -> list[dict[str, object]]:
    records_by_id = {record.review_id: record for record in records}
    reviews_by_product: dict[str, set[str]] = {}
    for record in records:
        reviews_by_product.setdefault(record.parent_product_id, set()).add(
            record.review_id
        )
    theme_by_id = {theme.theme_id: theme for theme in themes}
    tags_by_product_theme: dict[tuple[str, str], list[ReviewThemeTag]] = {}
    for tag in tags:
        if tag.review_id not in records_by_id or tag.theme_id not in theme_by_id:
            continue
        tags_by_product_theme.setdefault(
            (tag.parent_product_id, tag.theme_id), []
        ).append(tag)
    rollups: list[dict[str, object]] = []
    for (parent_product_id, theme_id), product_theme_tags in sorted(
        tags_by_product_theme.items()
    ):
        theme = theme_by_id[theme_id]
        product_reviews = reviews_by_product.get(parent_product_id, set())
        reviews_with_theme = {tag.review_id for tag in product_theme_tags}
        counts = _polarity_counts(product_theme_tags)
        record = next(
            (
                records_by_id[tag.review_id]
                for tag in product_theme_tags
                if tag.review_id in records_by_id
            ),
            None,
        )
        if record is None:
            continue
        rollups.append(
            {
                "retailer": record.retailer,
                "category_key": record.category_key,
                "parent_product_id": parent_product_id,
                "theme_id": theme.theme_id,
                "theme_label": theme.theme_label,
                "theme_family": theme.theme_family,
                "reviewed_product_reviews": len(product_reviews),
                "reviews_with_theme": len(reviews_with_theme),
                "positive_tags": counts["positive"],
                "negative_tags": counts["negative"],
                "mixed_tags": counts["mixed"],
                "mention_rate": _safe_rate(
                    len(reviews_with_theme), len(product_reviews)
                ),
                "evidence_json": _json_dumps(
                    _representative_evidence(
                        product_theme_tags,
                        records_by_id,
                        limit=3,
                    )
                ),
            }
        )
    return rollups


def ensure_review_theme_schema(conn: Any) -> None:
    """Create the review-theme codebook tables."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_runs (
            run_id TEXT PRIMARY KEY,
            retailer TEXT NOT NULL,
            category_key TEXT NOT NULL,
            pipeline_version TEXT NOT NULL,
            discovery_prompt_version TEXT NOT NULL,
            tag_prompt_version TEXT NOT NULL,
            sample_seed INTEGER NOT NULL,
            reviews_per_stratum INTEGER NOT NULL,
            max_themes INTEGER NOT NULL,
            run_scope TEXT NOT NULL DEFAULT 'full',
            package_eligible INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)
    _add_column_if_missing(
        conn,
        table="pdp_review_theme_runs",
        column="run_scope",
        definition="TEXT NOT NULL DEFAULT 'full'",
    )
    _add_column_if_missing(
        conn,
        table="pdp_review_theme_runs",
        column="package_eligible",
        definition="INTEGER NOT NULL DEFAULT 0",
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_reviews (
            run_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            retailer TEXT NOT NULL,
            category_key TEXT NOT NULL,
            parent_product_id TEXT NOT NULL,
            product_name TEXT,
            brand TEXT,
            pdp_url TEXT,
            review_hash TEXT NOT NULL,
            review_unit_index INTEGER NOT NULL,
            source TEXT NOT NULL,
            headline TEXT,
            comment TEXT,
            review_text TEXT NOT NULL,
            rating REAL,
            review_created_date TEXT,
            is_top_seller INTEGER NOT NULL,
            is_new_launch INTEGER NOT NULL,
            is_focus_brand INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            PRIMARY KEY (run_id, review_id)
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_sample_reviews (
            run_id TEXT NOT NULL,
            stratum TEXT NOT NULL,
            review_id TEXT NOT NULL,
            PRIMARY KEY (run_id, stratum, review_id)
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_codebook (
            run_id TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            theme_label TEXT NOT NULL,
            theme_family TEXT NOT NULL,
            description TEXT NOT NULL,
            inclusion_notes TEXT,
            exclusion_notes TEXT,
            example_phrases_json TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            PRIMARY KEY (run_id, theme_id)
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_tags (
            tag_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            parent_product_id TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            theme_label TEXT NOT NULL,
            polarity TEXT NOT NULL,
            evidence_span TEXT NOT NULL,
            target TEXT NOT NULL,
            actor TEXT NOT NULL,
            confidence REAL,
            tagged_at TEXT NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdp_review_theme_product_rollups (
            run_id TEXT NOT NULL,
            retailer TEXT NOT NULL,
            category_key TEXT NOT NULL,
            parent_product_id TEXT NOT NULL,
            theme_id TEXT NOT NULL,
            theme_label TEXT NOT NULL,
            theme_family TEXT NOT NULL,
            reviewed_product_reviews INTEGER NOT NULL,
            reviews_with_theme INTEGER NOT NULL,
            positive_tags INTEGER NOT NULL,
            negative_tags INTEGER NOT NULL,
            mixed_tags INTEGER NOT NULL,
            mention_rate REAL NOT NULL,
            evidence_json TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (run_id, parent_product_id, theme_id)
        )
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pdp_review_theme_runs_scope
        ON pdp_review_theme_runs (retailer, category_key, run_scope, created_at)
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pdp_review_theme_product_rollups_scope
        ON pdp_review_theme_product_rollups (
            run_id,
            parent_product_id,
            theme_id
        )
        """)


def persist_review_theme_run(
    conn: Any,
    *,
    retailer: str,
    category_key: str,
    records: Sequence[ReviewRecord],
    sampled_records_by_stratum: Mapping[str, Sequence[ReviewRecord]],
    themes: Sequence[ReviewTheme],
    tags: Sequence[ReviewThemeTag],
    sample_seed: int,
    reviews_per_stratum: int,
    max_themes: int,
    run_scope: str = "full",
    replace_scope: bool = True,
) -> str:
    """Persist one frozen-codebook review theme run."""

    ensure_review_theme_schema(conn)
    deduped_tags = _dedupe_review_theme_tags(tags)
    run_id = _hash_text(
        REVIEW_THEME_PIPELINE_VERSION,
        retailer,
        category_key,
        run_scope,
        _now_iso(),
        sample_seed,
        reviews_per_stratum,
    )
    timestamp = _now_iso()
    if replace_scope:
        _delete_existing_theme_scope(
            conn,
            retailer=retailer,
            category_key=category_key,
            run_scope=run_scope,
        )
    conn.execute(
        """
        INSERT INTO pdp_review_theme_runs (
            run_id,
            retailer,
            category_key,
            pipeline_version,
            discovery_prompt_version,
            tag_prompt_version,
            sample_seed,
            reviews_per_stratum,
            max_themes,
            run_scope,
            package_eligible,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            retailer,
            category_key,
            REVIEW_THEME_PIPELINE_VERSION,
            REVIEW_THEME_DISCOVERY_PROMPT_VERSION,
            REVIEW_THEME_TAG_PROMPT_VERSION,
            sample_seed,
            reviews_per_stratum,
            max_themes,
            run_scope,
            1 if run_scope == "full" else 0,
            timestamp,
        ),
    )
    conn.executemany(
        """
        INSERT INTO pdp_review_theme_reviews (
            run_id,
            review_id,
            retailer,
            category_key,
            parent_product_id,
            product_name,
            brand,
            pdp_url,
            review_hash,
            review_unit_index,
            source,
            headline,
            comment,
            review_text,
            rating,
            review_created_date,
            is_top_seller,
            is_new_launch,
            is_focus_brand,
            observed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                record.review_id,
                record.retailer,
                record.category_key,
                record.parent_product_id,
                record.product_name,
                record.brand,
                record.pdp_url,
                record.review_hash,
                record.review_unit_index,
                record.source,
                record.headline,
                record.comment,
                record.text,
                record.rating,
                record.review_created_date,
                1 if record.is_top_seller else 0,
                1 if record.is_new_launch else 0,
                0,
                timestamp,
            )
            for record in records
        ],
    )
    conn.executemany(
        """
        INSERT INTO pdp_review_theme_sample_reviews (run_id, stratum, review_id)
        VALUES (?, ?, ?)
        """,
        [
            (run_id, stratum, record.review_id)
            for stratum, stratum_records in sampled_records_by_stratum.items()
            for record in stratum_records
        ],
    )
    conn.executemany(
        """
        INSERT INTO pdp_review_theme_codebook (
            run_id,
            theme_id,
            theme_label,
            theme_family,
            description,
            inclusion_notes,
            exclusion_notes,
            example_phrases_json,
            sort_order
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                theme.theme_id,
                theme.theme_label,
                theme.theme_family,
                theme.description,
                theme.inclusion_notes,
                theme.exclusion_notes,
                _json_dumps(list(theme.example_phrases)),
                theme.sort_order,
            )
            for theme in themes
        ],
    )
    conn.executemany(
        """
        INSERT INTO pdp_review_theme_tags (
            tag_id,
            run_id,
            review_id,
            parent_product_id,
            theme_id,
            theme_label,
            polarity,
            evidence_span,
            target,
            actor,
            confidence,
            tagged_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                _hash_text(run_id, tag.tag_id),
                run_id,
                tag.review_id,
                tag.parent_product_id,
                tag.theme_id,
                tag.theme_label,
                tag.polarity,
                tag.evidence_span,
                tag.target,
                tag.actor,
                tag.confidence,
                timestamp,
            )
            for tag in deduped_tags
        ],
    )
    rollups = _build_product_theme_rollups(
        records=records,
        themes=themes,
        tags=deduped_tags,
    )
    conn.executemany(
        """
        INSERT INTO pdp_review_theme_product_rollups (
            run_id,
            retailer,
            category_key,
            parent_product_id,
            theme_id,
            theme_label,
            theme_family,
            reviewed_product_reviews,
            reviews_with_theme,
            positive_tags,
            negative_tags,
            mixed_tags,
            mention_rate,
            evidence_json,
            computed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                rollup["retailer"],
                rollup["category_key"],
                rollup["parent_product_id"],
                rollup["theme_id"],
                rollup["theme_label"],
                rollup["theme_family"],
                rollup["reviewed_product_reviews"],
                rollup["reviews_with_theme"],
                rollup["positive_tags"],
                rollup["negative_tags"],
                rollup["mixed_tags"],
                rollup["mention_rate"],
                rollup["evidence_json"],
                timestamp,
            )
            for rollup in rollups
        ],
    )
    return run_id


def _delete_existing_theme_scope(
    conn: Any,
    *,
    retailer: str,
    category_key: str,
    run_scope: str,
) -> None:
    params = (retailer, category_key, run_scope)
    run_subquery = (
        "SELECT run_id FROM pdp_review_theme_runs "
        "WHERE retailer = ? AND category_key = ? AND run_scope = ?"
    )
    for table in (
        "pdp_review_theme_product_rollups",
        "pdp_review_theme_tags",
        "pdp_review_theme_codebook",
        "pdp_review_theme_sample_reviews",
        "pdp_review_theme_reviews",
    ):
        conn.execute(
            f"DELETE FROM {table} WHERE run_id IN ({run_subquery})",
            params,
        )
    conn.execute(
        "DELETE FROM pdp_review_theme_runs "
        "WHERE retailer = ? AND category_key = ? AND run_scope = ?",
        params,
    )
