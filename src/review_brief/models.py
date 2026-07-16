from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChartType = Literal[
    "area",
    "slope",
    "stacked_column",
    "stacked_share",
    "stacked_share_facets",
    "stacked_column_absolute",
    "combo_total_absolute",
    "slope_share",
    "slope_share_facets",
]

ChartUniverse = Literal["full", "l4l"]


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    id: str
    label: str
    column: str


@dataclass(frozen=True, slots=True)
class ChartPayload:
    """A fully materialized chart + metadata for NotebookLM briefs.

    Notes:
      - `chart_id` is the *instance id* used for citations (includes time window + filters).
      - `definition_id` is a stable identifier for the chart template/concept (excludes time window).
    """

    chart_id: str
    definition_id: str
    chart_type: ChartType
    title: str
    subtitle: str
    normalization: str
    category_key: str
    category_label: str
    retailers: list[str]
    brands: list[str]
    universe: ChartUniverse
    start_month: str
    end_month: str
    dimensions: list[DimensionSpec]
    facet: DimensionSpec | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class ChartInterpretation:
    chart_id: str
    headline: str
    bullets: list[str]
    relevance: int
    highlight_item: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewBriefResult:
    markdown: str
    output_path: str
    charts_json_path: str
    total_charts: int
    selected_charts: int


@dataclass(frozen=True, slots=True)
class SuggestedSlide:
    title: str
    chart_ids: list[str]


@dataclass(frozen=True, slots=True)
class ReviewBriefNarrative:
    executive_narrative: str
    key_takeaways: list[str]
    suggested_flow: list[SuggestedSlide]


__all__ = [
    "ChartInterpretation",
    "ChartPayload",
    "ChartType",
    "ChartUniverse",
    "DimensionSpec",
    "ReviewBriefNarrative",
    "ReviewBriefResult",
    "SuggestedSlide",
]
