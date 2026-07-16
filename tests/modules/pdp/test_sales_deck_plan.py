from __future__ import annotations

from modules.pdp.sales_deck_plan import build_sales_deck_plan_payload


def _make_brief_payload() -> dict[str, object]:
    return {
        "title": "Market scan: ulta / blush",
        "scope": "single_category",
        "analysis_scope": {
            "report_mode": "market_report",
            "dataset": "us_cosmetics",
            "retailers": ["ulta"],
            "categories": ["blush"],
            "brands": [],
            "price_bands": [],
            "pareto_classes": [],
            "attribute_filters": {},
        },
        "attribute_dimensions": ["coverage", "form", "finish"],
        "highlights": [
            "Lead growth claim.",
            "Lead attribute claim.",
            "Lead brand claim.",
        ],
        "sections": [
            {
                "lens": "growth_size",
                "title": "Growth / Size",
                "findings": [
                    {
                        "rank": 1,
                        "claim": "Lead growth claim.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-total-combo-rolling-12",
                            "chart_key": "total_combo",
                            "chart_label": "Total combo",
                        },
                        "evidence_bullets": [
                            "sales moved from $117.4M to $209.9M",
                            "Absolute change was +$92.5M and relative change was +78.8%.",
                        ],
                    }
                ],
            },
            {
                "lens": "attribute_mix",
                "title": "Attribute Mix",
                "findings": [
                    {
                        "rank": 2,
                        "claim": "Lead attribute claim.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-attribute-finish",
                            "chart_key": "stacked_share",
                            "chart_label": "100% area",
                        },
                        "evidence_bullets": [
                            "Natural moved from 73.5% to 49.3%.",
                            "Change was -24.2 percentage points across the period.",
                        ],
                    },
                    {
                        "rank": 4,
                        "claim": "Second attribute claim.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-attribute-coverage",
                            "chart_key": "stacked_share",
                            "chart_label": "100% area",
                        },
                        "evidence_bullets": [
                            "Light changed by +10.9 pp and Sheer by +4.3 pp."
                        ],
                    },
                    {
                        "rank": 5,
                        "claim": "Third attribute claim.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-attribute-form",
                            "chart_key": "stacked_share",
                            "chart_label": "100% area",
                        },
                        "evidence_bullets": [
                            "Liquid rose from 9.0% to 20.0%."
                        ],
                    },
                ],
            },
        ],
    }


def test_build_sales_deck_plan_payload_creates_summary_and_insight_slides() -> None:
    payload = build_sales_deck_plan_payload(_make_brief_payload())

    assert payload["title"] == "Market scan: ulta / blush"
    assert payload["slide_count"] == 5
    assert payload["slides"][0] == {
        "rank": 1,
        "kind": "summary",
        "title": "Market scan: ulta / blush",
        "bullets": [
            "Lead growth claim.",
            "Lead attribute claim.",
            "Lead brand claim.",
        ],
    }
    assert payload["slides"][1]["title"] == "Lead growth claim."
    assert payload["slides"][1]["chart_id"] == "sales-brief-total-combo-rolling-12"
    assert payload["slides"][2]["title"] == "Lead attribute claim."
    assert payload["slides"][3]["title"] == "Second attribute claim."
    assert payload["slides"][3]["bullets"] == [
        "Light changed by +10.9 pp and Sheer by +4.3 pp.",
    ]
    assert payload["slides"][4]["title"] == "Third attribute claim."


def test_build_sales_deck_plan_payload_respects_max_slides() -> None:
    payload = build_sales_deck_plan_payload(_make_brief_payload(), max_slides=2)

    assert payload["slide_count"] == 2
    assert [slide["kind"] for slide in payload["slides"]] == ["summary", "insight"]
