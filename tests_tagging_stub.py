from __future__ import annotations

import sys
import types
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from bs4 import BeautifulSoup  # type: ignore[import]

from src.slides.models import Slide

__all__ = ["ensure_tagging_stub"]


@dataclass(slots=True)
class EnrichedSlide:
    slide_id: str
    html: str
    applied: bool
    issues: list[str]


@dataclass(slots=True)
class TaggedSlidesSummary:
    index: dict[str, EnrichedSlide]
    metric_duplicates: dict[str, list[str]]
    recommendation_duplicates: dict[str, list[str]]
    missing_recommendation_links: list[str]


def ensure_tagging_stub() -> None:
    """Install a minimal ``src.slides.tagging`` stub for self-contained tests."""

    if "src.slides.tagging" in sys.modules:
        return

    def _parse_container(html: str, slide_id: str) -> tuple[BeautifulSoup, object]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(".slide-container")
        if container is None:
            container = soup.new_tag("div")
            container["class"] = "slide-container"
            soup.append(container)
        container["data-slide-id"] = slide_id
        return soup, container

    def stamp_slide(slide: Slide) -> EnrichedSlide:
        html = slide.full_html or ""
        soup, container = _parse_container(html, slide.id)
        if not container.get("data-slide-kind"):
            container["data-slide-kind"] = (
                "exhibit" if container.select_one(".chart, img") else "insight"
            )

        title = container.find("h1")
        if title is not None:
            title["data-block"] = title.get("data-block") or "title"

        metric = container.select_one(".metric")
        if metric is not None:
            metric["data-block"] = metric.get("data-block") or "metric"
            metric["data-metric-label"] = metric.get("data-metric-label") or ""
            metric["data-metric-unit"] = metric.get("data-metric-unit") or ""

        exhibit = container.select_one(".chart")
        if exhibit is not None:
            exhibit["data-block"] = exhibit.get("data-block") or "exhibit"
            exhibit["data-source-ref"] = exhibit.get("data-source-ref") or "unknown"

        recommendation = container.select_one("li")
        if recommendation is not None:
            recommendation["data-block"] = (
                recommendation.get("data-block") or "recommendation"
            )
            recommendation["data-priority"] = recommendation.get("data-priority") or "1"

        notes = container.select_one("aside.slide-notes")
        if notes is not None:
            notes["data-block"] = notes.get("data-block") or "notes"

        sources = container.select_one("footer.slide-source")
        if sources is not None:
            sources["data-block"] = sources.get("data-block") or "sources"

        return EnrichedSlide(slide_id=slide.id, html=str(soup), applied=True, issues=[])

    def _apply_indexed_patch(
        elements: Iterable[object],
        patch_entries: Iterable[dict[str, object]],
        *,
        index_key: str,
        attribute_map: dict[str, str],
        issues: list[str],
    ) -> None:
        element_list = list(elements)
        for entry in patch_entries:
            index_value = entry.get(index_key)
            if (
                not isinstance(index_value, int)
                or index_value < 0
                or index_value >= len(element_list)
            ):
                issues.append(f"Invalid index {index_value} for {index_key}")
                continue
            element = element_list[index_value]
            for patch_key, attr_name in attribute_map.items():
                value = entry.get(patch_key)
                if value is None:
                    continue
                element[attr_name] = str(value)

    def apply_enrichment_patch(
        stamped: EnrichedSlide, patch: dict[str, object]
    ) -> EnrichedSlide:
        soup, container = _parse_container(stamped.html, stamped.slide_id)
        issues: list[str] = []

        slide_topic = patch.get("slide_topic")
        if isinstance(slide_topic, str) and slide_topic:
            container["data-slide-topic"] = slide_topic
        slide_kind = patch.get("slide_kind")
        if isinstance(slide_kind, str) and slide_kind:
            container["data-slide-kind"] = slide_kind

        _apply_indexed_patch(
            container.select('[data-block="metric"]'),
            patch.get("metrics", []) if isinstance(patch.get("metrics"), list) else [],
            index_key="index",
            attribute_map={
                "label": "data-metric-label",
                "unit": "data-metric-unit",
                "year": "data-metric-year",
                "canonical_slide": "data-metric-canonical",
            },
            issues=issues,
        )
        _apply_indexed_patch(
            container.select('[data-block="exhibit"]'),
            (
                patch.get("exhibits", [])
                if isinstance(patch.get("exhibits"), list)
                else []
            ),
            index_key="index",
            attribute_map={
                "source_ref": "data-source-ref",
                "source_asof": "data-source-asof",
                "canonical_slide": "data-exhibit-canonical",
            },
            issues=issues,
        )
        _apply_indexed_patch(
            container.select('[data-block="recommendation"]'),
            (
                patch.get("recommendations", [])
                if isinstance(patch.get("recommendations"), list)
                else []
            ),
            index_key="index",
            attribute_map={
                "priority": "data-priority",
                "owner": "data-owner",
                "impact": "data-impact",
                "relates_to": "data-relates-to",
                "canonical_slide": "data-reco-canonical",
            },
            issues=issues,
        )

        return EnrichedSlide(
            slide_id=stamped.slide_id, html=str(soup), applied=not issues, issues=issues
        )

    def summarize_tagged_slides(
        enriched_slides: Iterable[EnrichedSlide],
    ) -> TaggedSlidesSummary:
        index: dict[str, EnrichedSlide] = {}
        metric_duplicates: defaultdict[str, list[str]] = defaultdict(list)
        recommendation_duplicates: defaultdict[str, list[str]] = defaultdict(list)
        missing_recommendation_links: list[str] = []

        for enriched in enriched_slides:
            index[enriched.slide_id] = enriched
            soup = BeautifulSoup(enriched.html, "html.parser")
            container = soup.select_one(".slide-container") or soup
            for metric in container.select('[data-block="metric"]'):
                canonical = metric.get("data-metric-canonical")
                if canonical:
                    metric_duplicates[str(canonical)].append(enriched.slide_id)
            recommendations = container.select('[data-block="recommendation"]')
            for recommendation in recommendations:
                canonical = recommendation.get("data-reco-canonical")
                if canonical:
                    recommendation_duplicates[str(canonical)].append(enriched.slide_id)
                else:
                    missing_recommendation_links.append(enriched.slide_id)

        return TaggedSlidesSummary(
            index=index,
            metric_duplicates=dict(metric_duplicates),
            recommendation_duplicates=dict(recommendation_duplicates),
            missing_recommendation_links=missing_recommendation_links,
        )

    tagging_stub = types.ModuleType("src.slides.tagging")
    tagging_stub.EnrichedSlide = EnrichedSlide
    tagging_stub.TaggedSlidesSummary = TaggedSlidesSummary
    tagging_stub.apply_enrichment_patch = apply_enrichment_patch
    tagging_stub.stamp_slide = stamp_slide
    tagging_stub.summarize_tagged_slides = summarize_tagged_slides

    import src.slides as slides_pkg

    slides_pkg.tagging = tagging_stub
    sys.modules["src.slides.tagging"] = tagging_stub
