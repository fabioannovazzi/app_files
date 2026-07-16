from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import ChartInterpretation, ChartPayload, ReviewBriefNarrative

__all__ = ["MarkdownSection", "render_review_brief_markdown"]


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    heading: str
    body: str


def render_review_brief_markdown(
    *,
    job_id: str | None = None,
    chart_view_base_url: str | None = None,
    category_key: str | None = None,
    category_label: str,
    retailers: list[str],
    brands: list[str] | None = None,
    start_month: str,
    end_month: str,
    charts: list[ChartPayload],
    interpretations: dict[str, ChartInterpretation],
    narrative: ReviewBriefNarrative | None = None,
) -> str:
    del job_id, chart_view_base_url

    lines: list[str] = []
    lines.append(f"# NotebookLM Brief — {category_label}")
    lines.append("")

    if narrative is not None:
        exec_text = narrative.executive_narrative.strip()
        takeaways = [t.strip() for t in narrative.key_takeaways if t and t.strip()]
        flow = narrative.suggested_flow
        if exec_text or takeaways or flow:
            if exec_text:
                lines.append("## Executive narrative")
                lines.append(exec_text)
                lines.append("")

            if takeaways:
                lines.append("## Key takeaways")
                for item in takeaways[:6]:
                    lines.append(f"- {item}")
                lines.append("")

            if flow:
                lines.append("## Suggested flow")
                for idx, slide in enumerate(flow[:20], start=1):
                    title = slide.title.strip()
                    if not title:
                        continue
                    if slide.chart_ids:
                        lines.append(
                            f"{idx}. {title} (charts: {', '.join(slide.chart_ids)})"
                        )
                    else:
                        lines.append(f"{idx}. {title}")
                lines.append("")

    lines.append("## Scope")
    lines.append(f"- Category: {category_label}")
    if category_key:
        lines.append(f"- Category key: {category_key}")
    lines.append(f"- Retailers: {', '.join(retailers)}")
    if brands:
        lines.append(f"- Brands filter: {', '.join(brands)}")
    lines.append(f"- Period: {start_month} → {end_month}")
    lines.append(
        "- Metric: sales share (%). Denominator is the full category total for non-attribute charts; "
        "for attribute charts it is the like-for-like subset (only SKUs with PDP-derived attributes)."
    )
    lines.append(
        "- Note: attribute-based insights reflect the like-for-like universe and can be coverage-biased."
    )
    lines.append("")
    lines.append("## Charts")
    lines.append("")

    for chart in charts:
        interp = interpretations.get(chart.chart_id)
        heading = interp.headline if interp and interp.headline.strip() else chart.title
        lines.append(f"### {heading}")
        lines.append("")
        lines.append(f"**Chart**: {chart.title}")
        if chart.subtitle:
            lines.append(f"**Notes**: {chart.subtitle}")
        lines.append(f"**Normalization**: {chart.normalization}")
        lines.append(f"**Instance ID**: `{chart.chart_id}`")
        lines.append(f"**Definition ID**: `{chart.definition_id}`")
        lines.append("")
        if interp and interp.bullets:
            for bullet in interp.bullets[:5]:
                cleaned = str(bullet).strip()
                if cleaned:
                    lines.append(f"- {cleaned}")
        lines.append("")
        lines.append(f"<!-- chart_id: {chart.chart_id} -->")
        lines.append(f"<!-- definition_id: {chart.definition_id} -->")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
