from __future__ import annotations

from typing import Mapping

__all__ = [
    "BLOCK_SORT_FALLBACK",
    "BULLET_BLOCK_TYPES",
    "GROUP_RENDER_MODES",
    "LAYOUT_SEMANTIC_TYPES",
    "LEGACY_LAYOUT_TYPE_ALIASES",
    "TEXT_BEARING_BLOCK_TYPES",
    "VISUAL_BLOCK_TYPES",
    "block_sort_key",
    "default_render_mode_for_type",
    "normalize_block_type",
    "normalize_group_kind",
    "normalize_list_level",
    "normalize_optional_string",
    "normalize_reading_order",
    "normalize_render_mode",
]

LAYOUT_SEMANTIC_TYPES = {
    "title",
    "body_text",
    "bullet_item",
    "group_label",
    "footer_meta",
    "implication_banner",
    "callout_banner",
    "table_title",
    "metric",
    "figure",
    "exhibit_label",
    "table",
    "decorative",
    "unknown",
}

LEGACY_LAYOUT_TYPE_ALIASES = {
    "text": "body_text",
    "list": "bullet_item",
}

TEXT_BEARING_BLOCK_TYPES = {
    "title",
    "body_text",
    "bullet_item",
    "group_label",
    "footer_meta",
    "implication_banner",
    "callout_banner",
    "table_title",
    "metric",
    "exhibit_label",
    "table",
}

BULLET_BLOCK_TYPES = {"bullet_item", "group_label"}
VISUAL_BLOCK_TYPES = {"figure", "table"}
GROUP_RENDER_MODES = {"native", "group_as_image", "ignore"}
BLOCK_SORT_FALLBACK = 10**9


def normalize_optional_string(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized if normalized else None


def normalize_block_type(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return "unknown"
    normalized = LEGACY_LAYOUT_TYPE_ALIASES.get(normalized, normalized)
    return normalized if normalized in LAYOUT_SEMANTIC_TYPES else "unknown"


def normalize_group_kind(value: object) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized if normalized else None


def normalize_render_mode(value: object) -> str | None:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return None
    if normalized == "group":
        normalized = "group_as_image"
    if normalized == "ignored":
        normalized = "ignore"
    return normalized if normalized in GROUP_RENDER_MODES else None


def default_render_mode_for_type(block_type: object) -> str:
    normalized_type = normalize_block_type(block_type)
    if normalized_type == "decorative":
        return "ignore"
    return "native"


def normalize_list_level(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return level if level >= 0 else None


def normalize_reading_order(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        reading_order = int(value)
    except (TypeError, ValueError):
        return None
    return reading_order if reading_order >= 0 else None


def block_sort_key(block: Mapping[str, object]) -> tuple[float, float]:
    bbox = block.get("bbox")
    if not isinstance(bbox, Mapping):
        return (float(BLOCK_SORT_FALLBACK), float(BLOCK_SORT_FALLBACK))
    x = bbox.get("x")
    y = bbox.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return (float(BLOCK_SORT_FALLBACK), float(BLOCK_SORT_FALLBACK))
    return (float(y), float(x))
