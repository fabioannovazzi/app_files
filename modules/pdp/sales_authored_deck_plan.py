from __future__ import annotations

import re
from typing import Any, Mapping

from modules.pdp.deck_layout_grammar import apply_layout_grammar_to_deck
from modules.pdp.sales_brief_config import DEFAULT_DECK_PLAN_MAX_SLIDES
from modules.pdp.sales_deck_plan import build_sales_deck_plan_payload

__all__ = [
    "build_sales_authored_deck_plan_payload",
]


_BRAND_REDISTRIBUTION_PATTERN = re.compile(
    r"Brand shares redistributed materially, with (?P<down>.+?) down and (?P<up>.+?) up\.$"
)
_BRAND_LEADERSHIP_SHIFT_PATTERN = re.compile(
    r"^Leadership shifted from (?P<from_brand>.+?) to (?P<to_brand>.+?)(?P<tail>.*)\.$"
)
_GROWTH_SLICE_PATTERN = re.compile(
    r"^The slice (?P<rest>.+)$"
)
_ATTRIBUTE_LOSS_PATTERN = re.compile(
    r"^(?P<dimension>[A-Za-z/ ]+) mix shifted as (?P<value>.+?) lost meaningful share(?P<tail>.*)\.$"
)
_PRICE_GAIN_PATTERN = re.compile(
    r"^(?P<band>.+?) price band gained meaningful share(?P<tail>.*)\.$"
)
_CHALLENGER_GAIN_PATTERN = re.compile(
    r"^(?P<brand>.+?) gained meaningful share outside the leading position\.$"
)
_EMERGING_POCKET_PATTERN = re.compile(
    r"^Within (?P<dimension>.+?), (?P<value>.+?) emerged as a meaningful pocket\.$"
)


def _normalize_entity_name(value: str) -> str:
    return " ".join(part for part in str(value).strip().title().split())


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_read_text(item) for item in value if _read_text(item)]


def _read_slide_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [slide for slide in value if isinstance(slide, Mapping)]


def _build_scope_label(analysis_scope: Mapping[str, Any]) -> str:
    retailers = _read_text_list(analysis_scope.get("retailers"))
    categories = _read_text_list(analysis_scope.get("categories"))
    brands = _read_text_list(analysis_scope.get("brands"))

    parts: list[str] = []
    if retailers:
        parts.append(" / ".join(_normalize_entity_name(value) for value in retailers))
    if categories:
        parts.append(" / ".join(value.lower() for value in categories))
    if brands:
        parts.append(" / ".join(_normalize_entity_name(value) for value in brands))
    return " ".join(part for part in parts if part).strip()


def _tighten_bullet(text: str) -> str:
    updated = text.strip()
    if not updated:
        return updated
    updated = updated.replace("percentage points", "pp")
    updated = updated.replace("across the period.", ".")
    updated = updated.replace("pp .", "pp.")
    updated = updated[0].upper() + updated[1:]
    return updated


def _author_title(title: str, *, lens: str | None, scope_label: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        return cleaned

    brand_match = _BRAND_REDISTRIBUTION_PATTERN.match(cleaned)
    if brand_match:
        down = _normalize_entity_name(brand_match.group("down"))
        up = _normalize_entity_name(brand_match.group("up"))
        return f"{down} lost share while {up} gained."

    leadership_match = _BRAND_LEADERSHIP_SHIFT_PATTERN.match(cleaned)
    if leadership_match:
        from_brand = _normalize_entity_name(leadership_match.group("from_brand"))
        to_brand = _normalize_entity_name(leadership_match.group("to_brand"))
        tail = leadership_match.group("tail")
        return f"Leadership shifted from {from_brand} to {to_brand}{tail}."

    growth_match = _GROWTH_SLICE_PATTERN.match(cleaned)
    if growth_match and scope_label:
        return f"{scope_label} {growth_match.group('rest')}"

    attribute_match = _ATTRIBUTE_LOSS_PATTERN.match(cleaned)
    if attribute_match:
        dimension = attribute_match.group("dimension").strip().lower()
        value = _normalize_entity_name(attribute_match.group("value"))
        tail = attribute_match.group("tail")
        return f"{value} lost share in {dimension} mix{tail}."

    price_match = _PRICE_GAIN_PATTERN.match(cleaned)
    if price_match:
        band = _normalize_entity_name(price_match.group("band"))
        tail = price_match.group("tail")
        return f"{band} gained share in price mix{tail}."

    challenger_match = _CHALLENGER_GAIN_PATTERN.match(cleaned)
    if challenger_match:
        brand = _normalize_entity_name(challenger_match.group("brand"))
        return f"{brand} gained share as a challenger."

    emerging_match = _EMERGING_POCKET_PATTERN.match(cleaned)
    if emerging_match:
        dimension = emerging_match.group("dimension").strip().lower()
        value = _normalize_entity_name(emerging_match.group("value"))
        return f"{value} emerged within {dimension}."

    if lens == "attribute_mix":
        return cleaned.replace(" meaningful ", " ")
    return cleaned


def _author_slide(
    slide: Mapping[str, Any],
    *,
    scope_label: str,
) -> dict[str, Any]:
    title = _read_text(slide.get("title"))
    subtitle = slide.get("subtitle")
    lens = _read_text(slide.get("lens")) or None
    authored_bullets = [
        _tighten_bullet(_author_title(bullet, lens=lens, scope_label=scope_label))
        for bullet in _read_text_list(slide.get("bullets"))
    ]

    payload: dict[str, Any] = {
        "rank": int(slide.get("rank") or 0),
        "kind": _read_text(slide.get("kind")),
        "title": _author_title(title, lens=lens, scope_label=scope_label),
        "bullets": authored_bullets,
    }
    if subtitle is not None:
        payload["subtitle"] = subtitle
    for key in ("chart_id", "chart_key", "chart_label", "lens", "chart_request"):
        if slide.get(key) is not None:
            payload[key] = slide.get(key)
    return payload


def build_sales_authored_deck_plan_payload(
    brief_payload: Mapping[str, Any],
    *,
    max_slides: int = DEFAULT_DECK_PLAN_MAX_SLIDES,
) -> dict[str, Any]:
    deck_plan = build_sales_deck_plan_payload(brief_payload, max_slides=max_slides)
    analysis_scope = deck_plan.get("analysis_scope")
    scope_label = (
        _build_scope_label(analysis_scope)
        if isinstance(analysis_scope, Mapping)
        else ""
    )
    payload = {
        "title": _read_text(deck_plan.get("title")) or "Market scan",
        "scope": _read_text(deck_plan.get("scope")) or "single_category",
        "analysis_scope": dict(analysis_scope) if isinstance(analysis_scope, Mapping) else {},
        "attribute_dimensions": _read_text_list(deck_plan.get("attribute_dimensions")),
        "slide_count": int(deck_plan.get("slide_count") or 0),
        "slides": [
            _author_slide(slide, scope_label=scope_label)
            for slide in _read_slide_list(deck_plan.get("slides"))
        ],
    }
    return apply_layout_grammar_to_deck(payload)
