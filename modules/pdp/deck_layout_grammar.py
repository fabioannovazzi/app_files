from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "DECK_LAYOUT_GRAMMAR_VERSION",
    "SlideLayoutDecision",
    "SlideLayoutProfile",
    "apply_layout_grammar_to_deck",
    "build_slide_layout_profile",
    "select_slide_layout",
]

DECK_LAYOUT_GRAMMAR_VERSION = "deck_layout_grammar/v1"
_DENSITY_HINTS = {"light", "medium", "dense"}


@dataclass(frozen=True, slots=True)
class SlideLayoutProfile:
    """Normalized content signals used to choose a deterministic layout family."""

    kind: str
    title: str
    subtitle: str
    bullet_count: int
    body_count: int
    card_count: int
    metric_count: int
    example_count: int
    comparison_item_count: int
    has_chart: bool
    has_visual: bool
    visual_kind: str
    density: str


@dataclass(frozen=True, slots=True)
class SlideLayoutDecision:
    """Layout family selected for a semantic slide spec."""

    family: str
    density: str
    reasons: tuple[str, ...]
    split_recommended: bool = False


def build_slide_layout_profile(slide_payload: Mapping[str, Any]) -> SlideLayoutProfile:
    """Return a compact profile describing the slide's content shape."""

    kind = _read_text(slide_payload.get("kind")).lower()
    title = _read_text(slide_payload.get("title"))
    subtitle = _read_text(slide_payload.get("subtitle"))
    bullets = _read_text_list(slide_payload.get("bullets"))
    body_items = _read_body_items(slide_payload.get("body"))
    cards = _read_mapping_list(slide_payload.get("cards"))
    metrics = _read_mapping_list(slide_payload.get("metrics"))
    examples = _read_mapping_list(slide_payload.get("examples"))
    comparison = _read_mapping(slide_payload.get("comparison"))
    visual = _read_mapping(slide_payload.get("visual"))
    has_chart = _has_chart_reference(slide_payload)
    visual_kind = _read_text(visual.get("kind")).lower()
    has_visual = bool(
        visual_kind
        or _read_text(slide_payload.get("image_id"))
        or _read_text_list(slide_payload.get("image_ids"))
    )
    comparison_item_count = len(_read_text_list(comparison.get("left_items"))) + len(
        _read_text_list(comparison.get("right_items"))
    )
    explicit_density = _read_text(slide_payload.get("density")).lower()
    density = (
        explicit_density
        if explicit_density in _DENSITY_HINTS
        else _infer_density(
            bullet_count=len(bullets),
            body_count=len(body_items),
            card_count=len(cards),
            metric_count=len(metrics),
            example_count=len(examples),
            comparison_item_count=comparison_item_count,
            has_chart=has_chart,
        )
    )

    return SlideLayoutProfile(
        kind=kind,
        title=title,
        subtitle=subtitle,
        bullet_count=len(bullets),
        body_count=len(body_items),
        card_count=len(cards),
        metric_count=len(metrics),
        example_count=len(examples),
        comparison_item_count=comparison_item_count,
        has_chart=has_chart,
        has_visual=has_visual,
        visual_kind=visual_kind,
        density=density,
    )


def select_slide_layout(slide_payload: Mapping[str, Any]) -> SlideLayoutDecision:
    """Choose a deterministic layout family for ``slide_payload``."""

    profile = build_slide_layout_profile(slide_payload)

    if profile.kind in {"section_header", "sectionheader"}:
        return SlideLayoutDecision(
            family="section_header",
            density=profile.density,
            reasons=("Explicit section-header slide kind.",),
        )

    if (
        profile.has_visual
        and profile.visual_kind in {"product_collage", "moodboard", "hero_image"}
        and profile.bullet_count <= 2
        and profile.body_count <= 1
    ):
        return SlideLayoutDecision(
            family="hero_thesis",
            density=profile.density,
            reasons=("Hero-style visual with low copy load.",),
        )

    if profile.comparison_item_count > 0:
        return SlideLayoutDecision(
            family="comparison_two_column",
            density=profile.density,
            reasons=("Left/right comparison content is present.",),
            split_recommended=profile.comparison_item_count > 8,
        )

    if profile.card_count == 3:
        return SlideLayoutDecision(
            family="cards_3up",
            density=profile.density,
            reasons=("Three cards fit a balanced 3-up evidence grid.",),
        )

    if profile.card_count == 4:
        return SlideLayoutDecision(
            family="cards_2x2",
            density=profile.density,
            reasons=("Four cards fit a balanced 2x2 grid.",),
        )

    if profile.example_count in {3, 4}:
        return SlideLayoutDecision(
            family="example_grid",
            density=profile.density,
            reasons=(f"{profile.example_count} concrete examples are available.",),
            split_recommended=profile.density == "dense",
        )

    if profile.metric_count >= 2 and not profile.has_chart:
        return SlideLayoutDecision(
            family="metrics_comparison",
            density=profile.density,
            reasons=("Multiple named metrics can anchor the slide.",),
            split_recommended=profile.metric_count > 4,
        )

    if profile.has_chart:
        if (
            profile.bullet_count <= 2
            and profile.body_count <= 1
            and not profile.subtitle
            and profile.density != "dense"
        ):
            return SlideLayoutDecision(
                family="chart_focus",
                density=profile.density,
                reasons=("Chart is primary and supporting copy is light.",),
            )
        return SlideLayoutDecision(
            family="chart_sidebar",
            density=profile.density,
            reasons=("Chart is present and needs an adjacent interpretation block.",),
            split_recommended=profile.bullet_count > 4 or profile.body_count > 2,
        )

    if profile.kind == "summary" or profile.bullet_count >= 4:
        return SlideLayoutDecision(
            family="summary_bullets",
            density=profile.density,
            reasons=("Summary-style copy load fits a disciplined bullet layout.",),
            split_recommended=profile.bullet_count > 6,
        )

    return SlideLayoutDecision(
        family="text_statement",
        density=profile.density,
        reasons=("Short text-only content can use a statement layout.",),
        split_recommended=profile.bullet_count > 5 or profile.body_count > 3,
    )


def apply_layout_grammar_to_deck(deck_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Annotate every slide in ``deck_payload`` with a deterministic layout decision."""

    slides = deck_payload.get("slides")
    if not isinstance(slides, list):
        return {
            **dict(deck_payload),
            "layout_grammar_version": DECK_LAYOUT_GRAMMAR_VERSION,
            "slides": [],
        }

    enriched_slides: list[dict[str, Any]] = []
    for slide in slides:
        if not isinstance(slide, Mapping):
            continue
        decision = select_slide_layout(slide)
        enriched_slide = dict(slide)
        enriched_slide["layout_family"] = decision.family
        enriched_slide["layout_density"] = decision.density
        enriched_slide["layout_reasons"] = list(decision.reasons)
        enriched_slide["split_recommended"] = decision.split_recommended
        enriched_slides.append(enriched_slide)

    return {
        **dict(deck_payload),
        "layout_grammar_version": DECK_LAYOUT_GRAMMAR_VERSION,
        "slides": enriched_slides,
    }


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_read_text(item) for item in value) if text]


def _read_body_items(value: object) -> list[str]:
    if isinstance(value, list):
        return _read_text_list(value)
    text = _read_text(value)
    return [text] if text else []


def _read_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _read_mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _has_chart_reference(slide_payload: Mapping[str, Any]) -> bool:
    if _read_text(slide_payload.get("chart_id")):
        return True
    chart = _read_mapping(slide_payload.get("chart"))
    return bool(_read_text(chart.get("chart_id")) or _read_text(chart.get("asset_id")))


def _infer_density(
    *,
    bullet_count: int,
    body_count: int,
    card_count: int,
    metric_count: int,
    example_count: int,
    comparison_item_count: int,
    has_chart: bool,
) -> str:
    content_score = (
        bullet_count
        + body_count
        + card_count
        + metric_count
        + example_count
        + comparison_item_count
    )
    if has_chart:
        content_score += 1
    if content_score >= 8:
        return "dense"
    if content_score >= 4:
        return "medium"
    return "light"
