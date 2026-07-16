from __future__ import annotations

from modules.pdp.sales_brief import build_sales_brief_artifact
from modules.pdp.sales_finding_engine import build_analysis_scope


def test_build_sales_brief_artifact_groups_ranked_findings_into_sections() -> None:
    brief = build_sales_brief_artifact(
        scope="single_category",
        analysis_scope=build_analysis_scope(retailers=["ulta"], categories=["blush"]),
        selection_context={},
        numeric_payloads={
            "total_combo": {
                "chart_id": "combo-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-01", "sales": 10.0},
                    {"month": "2024-02", "sales": 10.5},
                    {"month": "2024-03", "sales": 10.1},
                    {"month": "2024-04", "sales": 22.0},
                    {"month": "2024-05", "sales": 9.8},
                    {"month": "2024-06", "sales": 14.5},
                ],
            },
            "stacked_share_price_band": {
                "chart_id": "price-123",
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 35.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 45.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 26.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 36.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 38.0},
                ],
            },
        },
        lenses=("growth_size", "price_value_capture"),
        max_findings=4,
        max_per_lens=2,
        highlight_count=2,
    )

    assert brief.title == "Market scan: ulta / blush"
    assert brief.highlights == (
        "The slice grew materially from 2024-01 to 2024-06.",
        "Premium price band gained meaningful share from 2024-01 to 2025-01.",
    )
    assert [section.lens for section in brief.sections] == [
        "growth_size",
        "price_value_capture",
    ]
    assert all("volatile" not in finding.claim.lower() for finding in brief.findings)
    assert brief.findings[0].primary_evidence is not None
    assert brief.findings[0].primary_evidence.chart_id == "combo-123"
    price_finding = next(
        finding for finding in brief.findings if finding.lens == "price_value_capture"
    )
    assert price_finding.primary_evidence is not None
    assert price_finding.primary_evidence.chart_id == "price-123"


def test_build_sales_brief_artifact_resolves_attribute_evidence_from_multi_payload_map() -> (
    None
):
    brief = build_sales_brief_artifact(
        scope="single_category",
        analysis_scope=build_analysis_scope(retailers=["ulta"], categories=["blush"]),
        selection_context={},
        numeric_payloads={
            "stacked_share_attribute_payloads": {
                "coverage": {
                    "chart_id": "coverage-123",
                    "segment_key": "coverage",
                    "dimension_label": "Coverage",
                    "rows": [
                        {"month": "2024-01", "segment": "buildable", "share_pct": 40.0},
                        {"month": "2024-01", "segment": "light", "share_pct": 20.0},
                        {"month": "2024-01", "segment": "sheer", "share_pct": 10.0},
                        {"month": "2024-01", "segment": "medium", "share_pct": 30.0},
                        {"month": "2025-01", "segment": "buildable", "share_pct": 26.0},
                        {"month": "2025-01", "segment": "light", "share_pct": 31.0},
                        {"month": "2025-01", "segment": "sheer", "share_pct": 15.0},
                        {"month": "2025-01", "segment": "medium", "share_pct": 28.0},
                    ],
                },
                "form": {
                    "chart_id": "form-123",
                    "segment_key": "form",
                    "dimension_label": "Format",
                    "rows": [
                        {"month": "2024-01", "segment": "cream", "share_pct": 40.0},
                        {"month": "2024-01", "segment": "powder", "share_pct": 38.0},
                        {"month": "2024-01", "segment": "liquid", "share_pct": 8.0},
                        {"month": "2024-01", "segment": "stick", "share_pct": 14.0},
                        {"month": "2025-01", "segment": "cream", "share_pct": 43.0},
                        {"month": "2025-01", "segment": "powder", "share_pct": 26.0},
                        {"month": "2025-01", "segment": "liquid", "share_pct": 18.0},
                        {"month": "2025-01", "segment": "stick", "share_pct": 13.0},
                    ],
                },
            }
        },
        lenses=("attribute_mix",),
        max_findings=3,
        max_per_lens=3,
    )

    assert brief.title == "Market scan: ulta / blush"
    assert [finding.claim for finding in brief.findings] == [
        "Coverage mix polarized, with Light and Sheer gaining while Buildable declined.",
        "Within format, Liquid emerged as a meaningful pocket.",
    ]
    assert brief.findings[0].primary_evidence is not None
    assert brief.findings[0].primary_evidence.chart_id == "coverage-123"
    assert brief.findings[1].primary_evidence is not None
    assert brief.findings[1].primary_evidence.chart_id == "form-123"
