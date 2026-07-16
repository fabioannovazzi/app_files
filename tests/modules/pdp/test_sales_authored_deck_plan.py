from __future__ import annotations

from modules.pdp.sales_authored_deck_plan import (
    build_sales_authored_deck_plan_payload,
)


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
            "The slice grew materially from 2022 to 2025.",
            "Finish mix shifted as Natural lost meaningful share from 2022 to 2025.",
            "Brand shares redistributed materially, with e.l.f. cosmetics down and dibs beauty up.",
        ],
        "sections": [
            {
                "lens": "growth_size",
                "title": "Growth / Size",
                "findings": [
                    {
                        "rank": 1,
                        "claim": "The slice grew materially from 2022 to 2025.",
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
                        "claim": "Finish mix shifted as Natural lost meaningful share from 2022 to 2025.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-attribute-finish",
                            "chart_key": "stacked_share",
                            "chart_label": "100% area",
                        },
                        "evidence_bullets": [
                            "Natural moved from 73.5% to 49.3%.",
                            "Change was -24.2 percentage points across the period.",
                        ],
                    }
                ],
            },
            {
                "lens": "brand_shifts",
                "title": "Brand Shifts",
                "findings": [
                    {
                        "rank": 3,
                        "claim": "Brand shares redistributed materially, with e.l.f. cosmetics down and dibs beauty up.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-brand-slope",
                            "chart_key": "slope",
                            "chart_label": "Slope",
                        },
                        "evidence_bullets": [
                            "Total share redistribution across brands was 37.3 percentage points.",
                        ],
                    }
                ],
            },
            {
                "lens": "price_value_capture",
                "title": "Price / Value Capture",
                "findings": [
                    {
                        "rank": 4,
                        "claim": "Premium price band gained meaningful share from 2022 to 2025.",
                        "primary_evidence": {
                            "chart_id": "sales-brief-price-band-share",
                            "chart_key": "stacked_share",
                            "chart_label": "100% area",
                        },
                        "evidence_bullets": [
                            "Premium moved from 6.0% to 13.5%.",
                            "Change was +7.5 percentage points across the period.",
                        ],
                    }
                ],
            },
        ],
    }


def test_build_sales_authored_deck_plan_payload_rewrites_slide_language() -> None:
    payload = build_sales_authored_deck_plan_payload(_make_brief_payload())

    assert payload["layout_grammar_version"] == "deck_layout_grammar/v1"
    assert payload["slide_count"] == 5
    assert payload["slides"][0]["title"] == "Market scan: ulta / blush"
    assert payload["slides"][0]["layout_family"] == "summary_bullets"
    assert payload["slides"][0]["bullets"][0] == "Ulta blush grew materially from 2022 to 2025."
    assert payload["slides"][1]["title"] == "Ulta blush grew materially from 2022 to 2025."
    assert payload["slides"][1]["layout_family"] == "chart_sidebar"
    assert payload["slides"][2]["title"] == "Natural lost share in finish mix from 2022 to 2025."
    assert payload["slides"][2]["layout_family"] == "chart_sidebar"
    assert payload["slides"][3]["title"] == "E.L.F. Cosmetics lost share while Dibs Beauty gained."
    assert payload["slides"][3]["layout_family"] == "chart_sidebar"
    assert payload["slides"][4]["title"] == "Premium gained share in price mix from 2022 to 2025."
    assert payload["slides"][4]["layout_family"] == "chart_sidebar"
    assert payload["slides"][4]["bullets"][1] == "Change was +7.5 pp."
