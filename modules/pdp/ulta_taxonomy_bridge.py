from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _normalize_key(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").split())


@dataclass(frozen=True, slots=True)
class UltaTaxonomyBridge:
    """Describe how one Ulta category should map into our taxonomy."""

    category_key: str
    canonical_category: str
    filter_families: tuple[str, ...]
    claim_only_filter_families: tuple[str, ...] = ()
    filter_family_attribute_labels: Mapping[str, tuple[str, ...]] | None = None


ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES: tuple[str, ...] = (
    "finish",
    "form",
    "coverage",
    "color",
    "color lips",
    "color eyes",
    "concern",
    "preference",
    "benefit",
    "mascara type",
    "waterproof",
    "spf",
    "skin type",
)

ULTA_FILTER_FAMILY_TO_ATTRIBUTE_LABELS: dict[str, tuple[str, ...]] = {
    "finish": ("finish", "finish effect", "optical effect"),
    "form": (
        "form",
        "product type",
        "formula type",
        "treatment type",
        "applicator type",
    ),
    "coverage": ("coverage", "color payoff"),
    "color": (
        "color",
        "color family",
        "shade family",
        "color correction",
        "color-corrector shade",
    ),
    "color lips": ("color lips", "color family", "shade family"),
    "color eyes": ("color family", "shade family", "color-corrector shade"),
    "concern": (
        "concern",
        "skin concern",
        "performance benefits (care)",
        "benefits/claims",
    ),
    "preference": (
        "preference",
        "ethical/regulatory claims",
        "free from",
        "regulatory claims",
        "free-from claims",
        "ethical claims",
        "ethics claims",
        "conscious choices",
        "dermatology claims",
    ),
    "benefit": (
        "benefits",
        "key benefits",
        "benefits/claims",
        "performance benefits (control)",
        "performance benefits (care)",
        "treatment benefits",
        "benefits (claims)",
    ),
    "mascara type": ("product type", "formula type"),
    "waterproof": (
        "wear claims",
        "water resistance",
        "water/sweat/humidity resistance",
        "transfer/smudge resistance",
        "resistance claims",
        "resistance/transfer claims",
        "wear resistance",
        "durability claims",
        "performance claims",
    ),
    "spf": ("SPF", "spf", "sunscreen"),
    "skin type": (
        "skin type",
        "suitable skin type",
        "skin type suitability",
        "sensitive-skin compatible",
    ),
}


def _bridge(
    category_key: str,
    *,
    canonical_category: str | None = None,
    filter_families: tuple[str, ...],
    claim_only_filter_families: tuple[str, ...] = (),
    filter_family_attribute_labels: Mapping[str, tuple[str, ...]] | None = None,
) -> UltaTaxonomyBridge:
    normalized_category = _normalize_key(category_key).replace(" ", "_")
    normalized_canonical = (
        _normalize_key(canonical_category).replace(" ", "_")
        if canonical_category
        else normalized_category
    )
    normalized_families = tuple(
        _normalize_key(value) for value in filter_families if value
    )
    normalized_claim_only = tuple(
        _normalize_key(value) for value in claim_only_filter_families if value
    )
    normalized_overrides = (
        {
            _normalize_key(key): tuple(str(item) for item in values)
            for key, values in filter_family_attribute_labels.items()
        }
        if filter_family_attribute_labels
        else None
    )
    return UltaTaxonomyBridge(
        category_key=normalized_category,
        canonical_category=normalized_canonical,
        filter_families=normalized_families,
        claim_only_filter_families=normalized_claim_only,
        filter_family_attribute_labels=normalized_overrides,
    )


def canonicalize_ulta_category_key(category_key: str | None) -> str:
    """Return the canonical Ulta category key used throughout the repo."""

    normalized = _normalize_key(category_key).replace(" ", "_")
    return normalized


ULTA_TAXONOMY_BRIDGES: dict[str, UltaTaxonomyBridge] = {
    bridge.category_key: bridge
    for bridge in (
        _bridge(
            "lip_balms",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_gloss",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_liner",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_oil",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_plumpers",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_stain",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lip_treatments",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "lipstick",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "liquid_lipstick",
            filter_families=("finish", "form", "coverage", "color lips", "preference"),
        ),
        _bridge(
            "eyebrow",
            filter_families=("finish", "form", "color eyes", "waterproof"),
        ),
        _bridge(
            "eyeliner",
            filter_families=("finish", "form", "color eyes", "waterproof"),
        ),
        _bridge(
            "eyeshadow",
            filter_families=("finish", "form", "color eyes"),
        ),
        _bridge(
            "mascara",
            filter_families=("benefit", "mascara type", "waterproof", "color eyes"),
        ),
        _bridge(
            "foundation",
            filter_families=("finish", "form", "coverage", "skin type", "spf"),
        ),
        _bridge(
            "concealer",
            filter_families=("finish", "form", "coverage", "skin type"),
        ),
        _bridge(
            "color_correct",
            filter_families=(
                "finish",
                "form",
                "coverage",
                "skin type",
                "spf",
                "color",
            ),
        ),
        _bridge(
            "face_primer",
            filter_families=("finish", "form", "coverage", "skin type", "spf", "color"),
        ),
        _bridge(
            "bb_cc_creams",
            filter_families=("finish", "form", "coverage", "skin type", "spf", "color"),
        ),
        _bridge(
            "blush",
            filter_families=("finish", "form", "coverage", "color", "spf"),
        ),
        _bridge(
            "bronzer",
            filter_families=("finish", "form", "coverage", "spf"),
        ),
        _bridge(
            "contour",
            filter_families=("finish", "form"),
        ),
        _bridge(
            "highlighter",
            filter_families=("finish", "form"),
        ),
        _bridge(
            "setting_spray_powder",
            filter_families=("finish", "form", "coverage", "skin type", "spf"),
        ),
        _bridge(
            "tinted_moisturizer",
            filter_families=(
                "finish",
                "form",
                "coverage",
                "skin type",
                "concern",
                "spf",
                "color",
            ),
        ),
    )
}

ULTA_CATEGORY_FILTER_FAMILIES: dict[str, tuple[str, ...]] = {
    category_key: bridge.filter_families
    for category_key, bridge in ULTA_TAXONOMY_BRIDGES.items()
}


def get_ulta_taxonomy_bridge(category_key: str) -> UltaTaxonomyBridge | None:
    """Return the explicit Ulta bridge for one category."""

    normalized = canonicalize_ulta_category_key(category_key)
    if not normalized:
        return None
    bridge = ULTA_TAXONOMY_BRIDGES.get(normalized)
    if bridge is not None:
        return bridge
    for candidate in ULTA_TAXONOMY_BRIDGES.values():
        if candidate.canonical_category == normalized:
            return candidate
    return None


def bridged_ulta_category_keys(category_key: str) -> tuple[str, ...]:
    """Return the normalized category keys associated with one Ulta category."""

    normalized = canonicalize_ulta_category_key(category_key)
    if not normalized:
        return ()
    bridge = get_ulta_taxonomy_bridge(normalized)
    if bridge is None:
        return (normalized,)
    keys = [bridge.category_key]
    if bridge.canonical_category not in keys:
        keys.append(bridge.canonical_category)
    return tuple(keys)


def mapped_filter_families_for_category(category_key: str) -> tuple[str, ...]:
    """Return the Ulta filter families we intentionally track for one category."""

    bridge = get_ulta_taxonomy_bridge(category_key)
    if bridge is None:
        return ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES
    return bridge.filter_families or ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES


def claim_only_filter_families_for_category(category_key: str) -> tuple[str, ...]:
    """Return tracked Ulta filter families that should not count as taxonomy gaps."""

    bridge = get_ulta_taxonomy_bridge(category_key)
    if bridge is None:
        return ()
    return bridge.claim_only_filter_families


def attribute_labels_for_filter_family(
    filter_family: str,
    *,
    category_key: str | None = None,
) -> tuple[str, ...]:
    """Return candidate taxonomy labels for one Ulta filter family."""

    normalized_family = _normalize_key(filter_family)
    if not normalized_family:
        return ()
    bridge = get_ulta_taxonomy_bridge(category_key or "")
    if bridge and bridge.filter_family_attribute_labels:
        override = bridge.filter_family_attribute_labels.get(normalized_family)
        if override is not None:
            return override
    return ULTA_FILTER_FAMILY_TO_ATTRIBUTE_LABELS.get(normalized_family, ())


__all__ = [
    "ULTA_CATEGORY_FILTER_FAMILIES",
    "ULTA_DEFAULT_ATTRIBUTE_FILTER_FAMILIES",
    "ULTA_FILTER_FAMILY_TO_ATTRIBUTE_LABELS",
    "ULTA_TAXONOMY_BRIDGES",
    "UltaTaxonomyBridge",
    "attribute_labels_for_filter_family",
    "bridged_ulta_category_keys",
    "canonicalize_ulta_category_key",
    "claim_only_filter_families_for_category",
    "get_ulta_taxonomy_bridge",
    "mapped_filter_families_for_category",
]
