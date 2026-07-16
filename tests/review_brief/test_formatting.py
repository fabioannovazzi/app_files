from __future__ import annotations

from src.review_brief.formatting import format_brief_text_numbers
from src.review_brief.markdown import render_review_brief_markdown
from src.review_brief.models import ChartInterpretation, ChartPayload, DimensionSpec


def test_format_brief_text_numbers_rounds_shares_and_pp_deltas() -> None:
    text = "shimmer 92.04% → 38.17% (‑53.87 p.p.)"
    assert format_brief_text_numbers(text) == "shimmer 92.0% → 38.2% (down 54 pp)"


def test_format_brief_text_numbers_uses_lt_1_and_approx_pp() -> None:
    text = "0.86% → 7.99% (+7.13 p.p.)"
    assert format_brief_text_numbers(text) == "<1% → 8.0% (up ~7 pp)"


def test_format_brief_text_numbers_normalizes_plus_points_token() -> None:
    assert format_brief_text_numbers("(+71points)") == "(up 71 pp)"


def test_render_review_brief_markdown_omits_csv_rows_and_keeps_chart_metadata() -> None:
    chart = ChartPayload(
        chart_id="chart_demo_000000000000",
        definition_id="chart_demo_def_000000000000",
        chart_type="slope_share",
        title="Demo slope",
        subtitle="",
        normalization="share_of_category_total",
        category_key="demo",
        category_label="Demo",
        retailers=["ulta"],
        brands=[],
        universe="l4l",
        start_month="2024-01-01",
        end_month="2024-12-01",
        dimensions=[DimensionSpec(id="finish", label="Finish", column="finish")],
        facet=None,
        payload={
            "rows": [
                {
                    "segment": "dewy",
                    "start_share_pct": 0.86,
                    "end_share_pct": 7.99,
                    "delta_pp": 7.13,
                },
            ]
        },
    )
    markdown = render_review_brief_markdown(
        category_label="Demo",
        retailers=["ulta"],
        start_month="2024-01-01",
        end_month="2024-12-01",
        charts=[chart],
        interpretations={
            chart.chart_id: ChartInterpretation(
                chart_id=chart.chart_id,
                headline="Demo",
                bullets=[],
                relevance=80,
            )
        },
        narrative=None,
    )

    assert "**Chart**: Demo slope" in markdown
    assert "**Normalization**: share_of_category_total" in markdown
    assert "**Instance ID**: `chart_demo_000000000000`" in markdown
    assert "Data (CSV):" not in markdown
    assert "delta_pp" not in markdown
    assert "![Chart preview:" not in markdown


def test_render_review_brief_markdown_omits_chart_links_and_preview_urls() -> None:
    chart = ChartPayload(
        chart_id="chart_demo_111111111111",
        definition_id="chart_demo_def_111111111111",
        chart_type="stacked_share",
        title="Demo stacked",
        subtitle="",
        normalization="share_of_category_total",
        category_key="demo",
        category_label="Demo",
        retailers=["ulta"],
        brands=["example_brand"],
        universe="full",
        start_month="2024-01-01",
        end_month="2024-12-01",
        dimensions=[DimensionSpec(id="brand", label="Brand", column="brand")],
        facet=None,
        payload={"rows": [{"month": "2024-01-01", "segment": "A", "share_pct": 10.0}]},
    )
    markdown = render_review_brief_markdown(
        job_id="job_123",
        category_label="Demo",
        retailers=["ulta"],
        brands=["example_brand"],
        start_month="2024-01-01",
        end_month="2024-12-01",
        charts=[chart],
        interpretations={
            chart.chart_id: ChartInterpretation(
                chart_id=chart.chart_id, headline="Demo", bullets=[], relevance=80
            )
        },
        narrative=None,
    )

    assert "review/brief/charts/png?" not in markdown
    assert "![Chart preview:" not in markdown
    assert "**View**:" not in markdown
    assert "## NotebookLM usage rules" not in markdown
