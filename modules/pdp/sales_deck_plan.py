from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from modules.pdp.sales_brief_config import (
    DEFAULT_DECK_PLAN_MAX_SLIDES,
    DECK_PLAN_MAX_BULLETS_PER_SLIDE,
    DECK_PLAN_MAX_SUMMARY_BULLETS,
)

__all__ = [
    "SalesDeckPlanArtifact",
    "SalesDeckPlanSlide",
    "build_sales_deck_plan_artifact",
    "build_sales_deck_plan_payload",
]


@dataclass(frozen=True, slots=True)
class SalesDeckPlanSlide:
    rank: int
    kind: str
    title: str
    subtitle: str | None
    bullets: tuple[str, ...]
    chart_id: str | None = None
    chart_key: str | None = None
    chart_label: str | None = None
    chart_request: Mapping[str, Any] | None = None
    lens: str | None = None


@dataclass(frozen=True, slots=True)
class SalesDeckPlanArtifact:
    title: str
    scope: str
    analysis_scope: Mapping[str, Any]
    attribute_dimensions: tuple[str, ...]
    slide_count: int
    slides: tuple[SalesDeckPlanSlide, ...]


def _read_text(value: object) -> str:
    return str(value or "").strip()


def _read_text_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_read_text(item) for item in value if _read_text(item))


def _read_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _read_sections(brief_payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    sections = brief_payload.get("sections")
    if not isinstance(sections, list):
        return ()
    return tuple(section for section in sections if isinstance(section, Mapping))


def _build_summary_slide(
    brief_payload: Mapping[str, Any],
) -> SalesDeckPlanSlide:
    highlights = _read_text_list(brief_payload.get("highlights"))
    brief_title = _read_text(brief_payload.get("title")) or "Market scan"
    title = brief_title
    subtitle = None
    bullets = highlights[:DECK_PLAN_MAX_SUMMARY_BULLETS]
    return SalesDeckPlanSlide(
        rank=1,
        kind="summary",
        title=title,
        subtitle=subtitle,
        bullets=tuple(bullets),
    )


def _flatten_ranked_findings(
    brief_payload: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], str], ...]:
    flattened: list[tuple[Mapping[str, Any], str]] = []
    for section in _read_sections(brief_payload):
        section_title = _read_text(section.get("title"))
        findings_obj = section.get("findings")
        if not isinstance(findings_obj, list):
            continue
        for finding in findings_obj:
            if isinstance(finding, Mapping):
                flattened.append((finding, section_title))
    return tuple(
        sorted(
            flattened,
            key=lambda item: (
                int(item[0].get("rank") or 999),
                _read_text(item[0].get("lens")),
                _read_text(item[0].get("claim")),
            ),
        )
    )


def _select_deck_plan_findings(
    brief_payload: Mapping[str, Any],
    *,
    max_content_slides: int,
) -> tuple[tuple[Mapping[str, Any], str], ...]:
    ranked_findings = _flatten_ranked_findings(brief_payload)
    if max_content_slides <= 0 or not ranked_findings:
        return ()

    selected: list[tuple[Mapping[str, Any], str]] = []
    seen_lenses: set[str] = set()
    remaining: list[tuple[Mapping[str, Any], str]] = []

    for finding, section_title in ranked_findings:
        lens = _read_text(finding.get("lens"))
        if lens and lens not in seen_lenses and len(selected) < max_content_slides:
            selected.append((finding, section_title))
            seen_lenses.add(lens)
            continue
        remaining.append((finding, section_title))

    for finding, section_title in remaining:
        if len(selected) >= max_content_slides:
            break
        selected.append((finding, section_title))
    return tuple(selected)


def _build_finding_slide(
    *,
    rank: int,
    finding: Mapping[str, Any],
    section_title: str,
) -> SalesDeckPlanSlide | None:
    lead_claim = _read_text(finding.get("claim"))
    if not lead_claim:
        return None
    lead_evidence = _read_mapping(finding.get("primary_evidence"))
    lead_bullets = list(_read_text_list(finding.get("evidence_bullets")))
    slide_bullets = lead_bullets[:DECK_PLAN_MAX_BULLETS_PER_SLIDE]
    chart_id = _read_text(lead_evidence.get("chart_id")) or None
    chart_key = _read_text(lead_evidence.get("chart_key")) or None
    chart_label = _read_text(lead_evidence.get("chart_label")) or None
    chart_request = (
        lead_evidence.get("chart_request")
        if isinstance(lead_evidence.get("chart_request"), Mapping)
        else None
    )
    lens = _read_text(finding.get("lens")) or None
    return SalesDeckPlanSlide(
        rank=rank,
        kind="insight",
        title=lead_claim,
        subtitle=section_title or None,
        bullets=tuple(slide_bullets),
        chart_id=chart_id,
        chart_key=chart_key,
        chart_label=chart_label,
        chart_request=dict(chart_request) if chart_request is not None else None,
        lens=lens,
    )


def build_sales_deck_plan_artifact(
    brief_payload: Mapping[str, Any],
    *,
    max_slides: int = DEFAULT_DECK_PLAN_MAX_SLIDES,
) -> SalesDeckPlanArtifact:
    summary_slide = _build_summary_slide(brief_payload)
    max_content_slides = max(0, int(max_slides) - 1)
    slides: list[SalesDeckPlanSlide] = [summary_slide]
    for finding, section_title in _select_deck_plan_findings(
        brief_payload,
        max_content_slides=max_content_slides,
    ):
        slide = _build_finding_slide(
            rank=len(slides) + 1,
            finding=finding,
            section_title=section_title,
        )
        if slide is not None:
            slides.append(slide)

    return SalesDeckPlanArtifact(
        title=_read_text(brief_payload.get("title")) or "Market scan",
        scope=_read_text(brief_payload.get("scope")) or "single_category",
        analysis_scope=_read_mapping(brief_payload.get("analysis_scope")),
        attribute_dimensions=_read_text_list(brief_payload.get("attribute_dimensions")),
        slide_count=len(slides),
        slides=tuple(slides),
    )


def build_sales_deck_plan_payload(
    brief_payload: Mapping[str, Any],
    *,
    max_slides: int = DEFAULT_DECK_PLAN_MAX_SLIDES,
) -> dict[str, Any]:
    artifact = build_sales_deck_plan_artifact(brief_payload, max_slides=max_slides)
    return {
        "title": artifact.title,
        "scope": artifact.scope,
        "analysis_scope": dict(artifact.analysis_scope),
        "attribute_dimensions": list(artifact.attribute_dimensions),
        "slide_count": artifact.slide_count,
        "slides": [
            {
                **{
                    "rank": slide.rank,
                    "kind": slide.kind,
                    "title": slide.title,
                    "bullets": list(slide.bullets),
                },
                **({"subtitle": slide.subtitle} if slide.subtitle is not None else {}),
                **({"chart_id": slide.chart_id} if slide.chart_id is not None else {}),
                **({"chart_key": slide.chart_key} if slide.chart_key is not None else {}),
                **(
                    {"chart_label": slide.chart_label}
                    if slide.chart_label is not None
                    else {}
                ),
                **(
                    {"chart_request": dict(slide.chart_request)}
                    if slide.chart_request is not None
                    else {}
                ),
                **({"lens": slide.lens} if slide.lens is not None else {}),
            }
            for slide in artifact.slides
        ],
    }
