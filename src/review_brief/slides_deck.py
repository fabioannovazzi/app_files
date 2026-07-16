from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Literal, Mapping, Sequence

from src.slides.models import Deck, Slide
from src.slides.notebooklm_style import (
    build_notebooklm_css_variables,
    load_notebooklm_style,
    resolve_prompt_style_key,
)
from src.slides.service import generate_slide_filename

__all__ = [
    "ReviewBriefDeckSlide",
    "ReviewBriefDeckSpec",
    "build_review_brief_deck",
    "build_review_brief_deck_spec",
]

ReviewBriefDeckSlideKind = Literal["summary", "chart"]


@dataclass(frozen=True, slots=True)
class ReviewBriefDeckSlide:
    """Structured slide definition derived from a review brief payload."""

    kind: ReviewBriefDeckSlideKind
    title: str
    body: str = ""
    bullets: list[str] = field(default_factory=list)
    chart_id: str | None = None
    chart_alt: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewBriefDeckSpec:
    """Deck-level shape extracted from the current review brief JSON."""

    prompt_style: str
    slides: list[ReviewBriefDeckSlide]

    def chart_ids(self) -> list[str]:
        """Return chart identifiers referenced by chart slides in order."""

        ordered: list[str] = []
        seen: set[str] = set()
        for slide in self.slides:
            chart_id = str(slide.chart_id or "").strip()
            if not chart_id or chart_id in seen:
                continue
            seen.add(chart_id)
            ordered.append(chart_id)
        return ordered


def build_review_brief_deck_spec(
    payload: Mapping[str, object],
) -> ReviewBriefDeckSpec:
    """Convert the current review-brief JSON into a simple slide plan."""

    prompt_style = resolve_prompt_style_key(
        _read_text(payload.get("prompt_style")) or None
    )
    category_label = _read_text(payload.get("category")) or _read_text(
        _read_mapping(payload.get("requested_scope")).get("category_label")
    )
    if not category_label:
        category_label = "Category review"
    retailers = _read_text_list(payload.get("retailers"))
    start_month = _read_text(payload.get("start_month"))
    end_month = _read_text(payload.get("end_month"))

    charts = payload.get("charts")
    chart_rows = charts if isinstance(charts, list) else []
    chart_by_id = {
        chart_id: item
        for item in chart_rows
        if isinstance(item, Mapping)
        for chart_id in [_read_text(item.get("chart_id"))]
        if chart_id
    }
    interpretations = _read_mapping(payload.get("interpretations"))
    narrative = _read_mapping(payload.get("narrative"))
    flow_rows = (
        narrative.get("suggested_flow")
        if isinstance(narrative.get("suggested_flow"), list)
        else []
    )
    selected_ids = _read_text_list(payload.get("selected"))

    summary_body = _build_summary_body(
        executive_narrative=_read_text(narrative.get("executive_narrative")),
        retailers=retailers,
        start_month=start_month,
        end_month=end_month,
    )
    summary_bullets = _read_text_list(narrative.get("key_takeaways"))[:5]
    slides: list[ReviewBriefDeckSlide] = [
        ReviewBriefDeckSlide(
            kind="summary",
            title=_build_summary_title(category_label, retailers),
            body=summary_body,
            bullets=summary_bullets,
        )
    ]

    if flow_rows:
        flow_chart_ids: list[str] = []
        for row in flow_rows:
            if not isinstance(row, Mapping):
                continue
            title = _read_text(row.get("title"))
            chart_id = _first_chart_id(
                row.get("chart_ids"), valid_chart_ids=chart_by_id
            )
            if not chart_id:
                continue
            flow_chart_ids.append(chart_id)
            slides.append(
                _build_chart_slide(
                    chart_id=chart_id,
                    title=title,
                    chart_by_id=chart_by_id,
                    interpretations=interpretations,
                )
            )
        for chart_id in selected_ids:
            if chart_id in flow_chart_ids or chart_id not in chart_by_id:
                continue
            slides.append(
                _build_chart_slide(
                    chart_id=chart_id,
                    title="",
                    chart_by_id=chart_by_id,
                    interpretations=interpretations,
                )
            )
    else:
        ordered_chart_ids = selected_ids or list(chart_by_id)
        for chart_id in ordered_chart_ids:
            if chart_id not in chart_by_id:
                continue
            slides.append(
                _build_chart_slide(
                    chart_id=chart_id,
                    title="",
                    chart_by_id=chart_by_id,
                    interpretations=interpretations,
                )
            )

    return ReviewBriefDeckSpec(prompt_style=prompt_style, slides=slides)


def build_review_brief_deck(
    deck_id: str,
    spec: ReviewBriefDeckSpec,
    *,
    chart_image_urls: Mapping[str, str] | None = None,
) -> Deck:
    """Build a slides deck using the shared prompt-style tokens."""

    image_urls = chart_image_urls or {}
    style = load_notebooklm_style(spec.prompt_style)
    slide_shell = _build_slide_shell(style)
    slides: list[Slide] = []
    existing_ids: list[str] = []
    for slide_spec in spec.slides:
        slide_id = generate_slide_filename(existing_ids)
        existing_ids.append(slide_id)
        slides.append(
            Slide(
                id=slide_id,
                title_html=escape(slide_spec.title),
                body_html=_render_body_html(slide_spec, image_urls),
                full_html=slide_shell,
            )
        )
    return Deck(deck_id=deck_id, prompt_style=spec.prompt_style, slides=slides)


def _build_chart_slide(
    *,
    chart_id: str,
    title: str,
    chart_by_id: Mapping[str, Mapping[str, object]],
    interpretations: Mapping[str, object],
) -> ReviewBriefDeckSlide:
    chart_payload = chart_by_id.get(chart_id, {})
    interpretation = _read_mapping(interpretations.get(chart_id))
    chart_title = _read_text(chart_payload.get("title")) or chart_id
    slide_title = (
        title or _read_text(interpretation.get("headline")) or chart_title or chart_id
    )
    body = _read_text(interpretation.get("headline"))
    bullets = _read_text_list(interpretation.get("bullets"))[:4]
    if not bullets:
        subtitle = _read_text(chart_payload.get("subtitle"))
        normalization = _read_text(chart_payload.get("normalization"))
        if subtitle:
            bullets.append(subtitle)
        if normalization:
            bullets.append(f"Normalization: {normalization}")
    return ReviewBriefDeckSlide(
        kind="chart",
        title=slide_title,
        body=body,
        bullets=bullets,
        chart_id=chart_id,
        chart_alt=chart_title,
    )


def _build_summary_title(category_label: str, retailers: Sequence[str]) -> str:
    if retailers:
        joined = ", ".join(retailers[:3])
        return f"{category_label} review: {joined}"
    return f"{category_label} review"


def _build_summary_body(
    *,
    executive_narrative: str,
    retailers: Sequence[str],
    start_month: str,
    end_month: str,
) -> str:
    parts: list[str] = []
    if executive_narrative:
        parts.append(executive_narrative)
    if retailers:
        scope_bits = [f"Retailers: {', '.join(retailers)}."]
        if start_month and end_month:
            scope_bits.append(f"Period: {start_month} to {end_month}.")
        parts.append(" ".join(scope_bits))
    elif start_month and end_month:
        parts.append(f"Period: {start_month} to {end_month}.")
    return " ".join(part for part in parts if part).strip()


def _first_chart_id(
    value: object,
    *,
    valid_chart_ids: Mapping[str, Mapping[str, object]],
) -> str:
    for chart_id in _read_text_list(value):
        if chart_id in valid_chart_ids:
            return chart_id
    return ""


def _read_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _read_text(value: object) -> str:
    text = str(value or "").strip()
    return text


def _read_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_read_text(raw) for raw in value) if item]


def _render_body_html(
    slide: ReviewBriefDeckSlide,
    chart_image_urls: Mapping[str, str],
) -> str:
    if slide.kind == "summary":
        parts = ['<section class="review-brief review-brief--summary">']
        if slide.body:
            parts.append(
                '<p class="review-brief__copy review-brief__copy--lead">'
                f"{escape(slide.body)}</p>"
            )
        if slide.bullets:
            parts.append(_render_bullet_list(slide.bullets))
        parts.append("</section>")
        return "".join(parts)

    chart_id = str(slide.chart_id or "").strip()
    image_url = str(chart_image_urls.get(chart_id) or "").strip()
    parts = ['<section class="review-brief review-brief--chart">']
    parts.append('<div class="review-brief__panel review-brief__panel--copy">')
    if slide.body:
        parts.append(
            '<p class="review-brief__copy review-brief__copy--kicker">'
            f"{escape(slide.body)}</p>"
        )
    if slide.bullets:
        parts.append(_render_bullet_list(slide.bullets))
    parts.append("</div>")
    parts.append('<div class="review-brief__panel review-brief__panel--visual">')
    if image_url:
        alt_text = escape(_read_text(slide.chart_alt) or chart_id or "Chart")
        parts.append(
            '<div class="review-brief__chart-frame">'
            f'<img class="review-brief__chart-image" src="{escape(image_url, quote=True)}" '
            f'alt="{alt_text}" />'
            "</div>"
        )
    else:
        parts.append(
            '<div class="review-brief__chart-frame review-brief__chart-frame--missing">'
            "<p>Chart preview unavailable.</p>"
            "</div>"
        )
    parts.append("</div>")
    parts.append("</section>")
    return "".join(parts)


def _render_bullet_list(bullets: Sequence[str]) -> str:
    items = "".join(
        f'<li class="review-brief__bullet">{escape(item)}</li>'
        for item in bullets
        if _read_text(item)
    )
    if not items:
        return ""
    return f'<ul class="review-brief__bullets">{items}</ul>'


def _build_slide_shell(style) -> str:
    css_vars = build_notebooklm_css_variables(style)
    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
        "<style>"
        f"{css_vars}"
        "html, body { margin: 0; padding: 0; width: 100%; height: 100%; }"
        "body { background: var(--notebooklm-bg-color); color: var(--notebooklm-text-color); }"
        ".slide-container {"
        " width: 1280px;"
        " height: 720px;"
        " box-sizing: border-box;"
        " padding: 56px 64px;"
        " display: flex;"
        " flex-direction: column;"
        " gap: 28px;"
        " font-family: var(--notebooklm-font-stack);"
        " background: var(--notebooklm-bg-color);"
        " color: var(--notebooklm-text-color);"
        "}"
        ".slide-title {"
        " margin: 0;"
        " font-size: var(--notebooklm-title-size-px);"
        " line-height: 1.1;"
        " font-weight: 700;"
        " max-width: 1080px;"
        "}"
        ".slide-body {"
        " flex: 1;"
        " min-height: 0;"
        " display: flex;"
        " flex-direction: column;"
        "}"
        ".review-brief {"
        " flex: 1;"
        " min-height: 0;"
        " display: flex;"
        "}"
        ".review-brief--summary {"
        " max-width: 960px;"
        " flex-direction: column;"
        " gap: 20px;"
        " justify-content: flex-start;"
        "}"
        ".review-brief--chart {"
        " display: grid;"
        " grid-template-columns: minmax(320px, 0.38fr) minmax(0, 0.62fr);"
        " gap: 32px;"
        " align-items: start;"
        "}"
        ".review-brief__panel { min-width: 0; }"
        ".review-brief__panel--copy {"
        " display: flex;"
        " flex-direction: column;"
        " gap: 18px;"
        " justify-content: flex-start;"
        "}"
        ".review-brief__copy {"
        " margin: 0;"
        " font-size: calc(var(--notebooklm-body-size-px) * 0.98);"
        " line-height: var(--notebooklm-line-height);"
        " opacity: 0.84;"
        "}"
        ".review-brief__copy--lead { font-size: calc(var(--notebooklm-body-size-px) * 1.04); }"
        ".review-brief__copy--kicker { font-weight: 600; opacity: 1; }"
        ".review-brief__bullets {"
        " margin: 0;"
        " padding-left: 1.15em;"
        " display: grid;"
        " gap: 12px;"
        " font-size: var(--notebooklm-body-size-px);"
        " line-height: var(--notebooklm-line-height);"
        "}"
        ".review-brief__bullet { margin: 0; }"
        ".review-brief__chart-frame {"
        " width: 100%;"
        " height: 100%;"
        " min-height: 440px;"
        " padding: 14px;"
        " box-sizing: border-box;"
        " display: flex;"
        " align-items: center;"
        " justify-content: center;"
        " border: 1px solid rgba(15, 23, 42, 0.12);"
        " border-radius: 16px;"
        " background: rgba(255, 255, 255, 0.88);"
        " overflow: hidden;"
        "}"
        ".review-brief__chart-frame--missing { opacity: 0.7; }"
        ".review-brief__chart-frame--missing p {"
        " margin: 0;"
        " font-size: var(--notebooklm-body-size-px);"
        "}"
        ".review-brief__chart-image {"
        " display: block;"
        " width: 100%;"
        " height: auto;"
        " max-height: 100%;"
        " object-fit: contain;"
        "}"
        ".slide-notes, .slide-source { display: none; }"
        "</style>"
        "</head>"
        "<body>"
        '<div class="slide-container"></div>'
        "</body>"
        "</html>"
    )
