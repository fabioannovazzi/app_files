from __future__ import annotations

from src.review_brief.generator import (
    _apply_model_highlights,
    _merge_suggested_flow,
    _merge_selected_charts_into_catalog,
    _resolve_chart_highlight_items,
)
from src.review_brief.charts import ChartCandidate
from src.review_brief.models import (
    ChartInterpretation,
    ChartPayload,
    DimensionSpec,
    SuggestedSlide,
)


def _base_chart(
    *, chart_type: str, payload_rows: list[dict[str, object]]
) -> ChartPayload:
    return ChartPayload(
        chart_id=f"{chart_type}_demo",
        definition_id=f"{chart_type}_def",
        chart_type=chart_type,  # type: ignore[arg-type]
        title="Demo",
        subtitle="",
        normalization="share_of_category_total",
        category_key="blush",
        category_label="Blush",
        retailers=["ulta"],
        brands=["all"],
        universe="full",
        start_month="2024-01-01",
        end_month="2024-02-01",
        dimensions=[DimensionSpec(id="form", label="Format", column="form")],
        facet=None,
        payload={"rows": payload_rows},
    )


def test_resolve_chart_highlight_items_stacked_share_matches_segment() -> None:
    chart = _base_chart(
        chart_type="stacked_share",
        payload_rows=[
            {"month": "2024-01-01", "segment": "matte", "share_pct": 40.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 60.0},
        ],
    )
    interpretation = ChartInterpretation(
        chart_id=chart.chart_id,
        headline="",
        bullets=[],
        relevance=90,
        highlight_item="Matte",
    )

    resolved = _resolve_chart_highlight_items(chart, interpretation)
    assert resolved == ["matte"]


def test_resolve_chart_highlight_items_slope_matches_attribute_token() -> None:
    chart = _base_chart(
        chart_type="slope_share",
        payload_rows=[
            {
                "brand": "brand_a",
                "attribute": "matte",
                "start_share_pct": 10.0,
                "end_share_pct": 20.0,
            },
            {
                "brand": "brand_b",
                "attribute": "dewy",
                "start_share_pct": 30.0,
                "end_share_pct": 35.0,
            },
        ],
    )
    interpretation = ChartInterpretation(
        chart_id=chart.chart_id,
        headline="",
        bullets=[],
        relevance=90,
        highlight_item="matte",
    )

    resolved = _resolve_chart_highlight_items(chart, interpretation)
    assert resolved == ["matte"]


def test_apply_model_highlights_stores_validated_items_in_payload() -> None:
    chart = _base_chart(
        chart_type="stacked_share",
        payload_rows=[
            {"month": "2024-01-01", "segment": "matte", "share_pct": 40.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 60.0},
        ],
    )
    interpretation = ChartInterpretation(
        chart_id=chart.chart_id,
        headline="",
        bullets=[],
        relevance=90,
        highlight_item="matte",
    )

    updated = _apply_model_highlights([chart], {chart.chart_id: interpretation})
    assert len(updated) == 1
    assert updated[0].payload.get("highlighted_dimension") == ["matte"]


def test_merge_selected_charts_into_catalog_preserves_highlight_payload() -> None:
    base_chart = _base_chart(
        chart_type="stacked_share",
        payload_rows=[
            {"month": "2024-01-01", "segment": "matte", "share_pct": 40.0},
            {"month": "2024-01-01", "segment": "dewy", "share_pct": 60.0},
        ],
    )
    highlighted_chart = ChartPayload(
        chart_id=base_chart.chart_id,
        definition_id=base_chart.definition_id,
        chart_type=base_chart.chart_type,
        title=base_chart.title,
        subtitle=base_chart.subtitle,
        normalization=base_chart.normalization,
        category_key=base_chart.category_key,
        category_label=base_chart.category_label,
        retailers=base_chart.retailers,
        brands=base_chart.brands,
        universe=base_chart.universe,
        start_month=base_chart.start_month,
        end_month=base_chart.end_month,
        dimensions=base_chart.dimensions,
        facet=base_chart.facet,
        payload={**base_chart.payload, "highlighted_dimension": ["matte"]},
    )
    candidates = [ChartCandidate(chart=base_chart, csv_rows=[])]

    merged = _merge_selected_charts_into_catalog(candidates, [highlighted_chart])

    assert len(merged) == 1
    assert merged[0].payload.get("highlighted_dimension") == ["matte"]


def test_merge_suggested_flow_preserves_model_arc_and_appends_missing_charts() -> None:
    primary = [
        SuggestedSlide(
            title="Open with the retailer divergence", chart_ids=["chart_b"]
        ),
        SuggestedSlide(title="Then explain the category shift", chart_ids=["chart_a"]),
    ]
    fallback = [
        SuggestedSlide(title="Category shift", chart_ids=["chart_a"]),
        SuggestedSlide(title="Retailer divergence", chart_ids=["chart_b"]),
        SuggestedSlide(title="Brand reset", chart_ids=["chart_c"]),
    ]

    merged = _merge_suggested_flow(primary, fallback)

    assert [slide.title for slide in merged] == [
        "Open with the retailer divergence",
        "Then explain the category shift",
        "Brand reset",
    ]
    assert [slide.chart_ids for slide in merged] == [
        ["chart_b"],
        ["chart_a"],
        ["chart_c"],
    ]
