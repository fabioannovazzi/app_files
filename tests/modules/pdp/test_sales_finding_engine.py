from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.pdp.sales_finding_engine import (
    build_analysis_scope,
    build_attribute_mix_candidates,
    build_attribute_mix_numeric_payloads,
    build_brand_shift_candidates,
    build_finding_engine_input,
    build_growth_size_candidates,
    build_price_value_capture_candidates,
    build_ranked_finding_shortlist,
    build_slope_numeric_payload,
    build_stacked_share_numeric_payload,
    build_total_combo_numeric_payload,
    get_finding_lens_spec,
    rank_and_deduplicate_findings,
    resolve_finding_evidence_plan,
    list_enabled_finding_claim_specs,
    list_initial_finding_claim_specs,
    list_initial_finding_lens_specs,
)


def test_list_initial_finding_lens_specs_includes_attribute_mix() -> None:
    specs = list_initial_finding_lens_specs()

    assert [spec.lens for spec in specs] == [
        "growth_size",
        "price_value_capture",
        "brand_shifts",
        "attribute_mix",
    ]
    assert get_finding_lens_spec("attribute_mix").preferred_chart_keys == (
        "stacked_share",
        "slope",
        "stacked_column",
        "pareto",
        "stacked_pareto",
    )


def test_build_total_combo_numeric_payload_reads_response_rows() -> None:
    response = SimpleNamespace(
        rows=[
            SimpleNamespace(month="2024-01", sales=10.0, units=2.0),
            SimpleNamespace(month="2024-02", sales=12.5, units=2.4),
        ]
    )

    payload = build_total_combo_numeric_payload(
        response, chart_id="combo-123", metric="sales", unit="mUSD", window_months=12
    )

    assert payload == {
        "chart_id": "combo-123",
        "metric": "sales",
        "unit": "mUSD",
        "window_months": 12,
        "monthly_series": [
            {"month": "2024-01", "sales": 10.0, "units": 2.0},
            {"month": "2024-02", "sales": 12.5, "units": 2.4},
        ],
    }


def test_build_stacked_share_numeric_payload_reads_dimension_header() -> None:
    response = SimpleNamespace(
        dimension_headers=["Coverage"],
        rows=[
            SimpleNamespace(
                month="2024-01",
                dimensions={"Coverage": "light"},
                sales_share=0.12,
            ),
            SimpleNamespace(
                month="2024-02",
                dimensions={"Coverage": "sheer"},
                sales_share=0.18,
            ),
        ],
    )

    payload = build_stacked_share_numeric_payload(
        response,
        chart_id="coverage-123",
        segment_key="coverage",
        dimension_label="Coverage",
    )

    assert payload == {
        "chart_id": "coverage-123",
        "segment_key": "coverage",
        "dimension_label": "Coverage",
        "rows": [
            {"month": "2024-01", "segment": "light", "share_pct": 12.0},
            {"month": "2024-02", "segment": "sheer", "share_pct": 18.0},
        ],
    }


def test_build_slope_numeric_payload_uses_first_and_last_month() -> None:
    response = SimpleNamespace(
        dimension_headers=["Brands"],
        rows=[
            SimpleNamespace(
                month="2024-01",
                dimensions={"Brands": "brand a"},
                sales_share=0.10,
            ),
            SimpleNamespace(
                month="2024-01",
                dimensions={"Brands": "brand b"},
                sales_share=0.20,
            ),
            SimpleNamespace(
                month="2025-01",
                dimensions={"Brands": "brand a"},
                sales_share=0.14,
            ),
            SimpleNamespace(
                month="2025-01",
                dimensions={"Brands": "brand b"},
                sales_share=0.16,
            ),
        ],
    )

    payload = build_slope_numeric_payload(
        response, chart_id="slope-123", segment_key="brand", dimension_label="Brands"
    )

    assert payload == {
        "chart_id": "slope-123",
        "segment_key": "brand",
        "dimension_label": "Brands",
        "rows": [
            {"segment": "brand a", "start_share_pct": 10.0, "end_share_pct": 14.0},
            {"segment": "brand b", "start_share_pct": 20.0, "end_share_pct": 16.0},
        ],
    }


def test_build_attribute_mix_numeric_payloads_builds_named_payload_map() -> None:
    payloads = build_attribute_mix_numeric_payloads(
        {
            "coverage": SimpleNamespace(
                dimension_headers=["Coverage"],
                rows=[
                    SimpleNamespace(
                        month="2024-01",
                        dimensions={"Coverage": "light"},
                        sales_share=0.12,
                    )
                ],
            )
        },
        chart_id_prefix="attr",
    )

    assert payloads == {
        "coverage": {
            "chart_id": "attr-coverage",
            "segment_key": "coverage",
            "dimension_label": "coverage",
            "rows": [
                {"month": "2024-01", "segment": "light", "share_pct": 12.0},
            ],
        }
    }


def test_build_finding_engine_input_filters_catalog_by_lens_and_scope() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={"dimsCount": 1, "periodMode": "single_month"},
    )

    chart_keys = [action.chart_key for action in engine_input.candidate_actions]

    assert chart_keys[:4] == [
        "stacked_share",
        "slope",
        "stacked_column",
        "pareto",
    ]
    assert {"bar", "stacked_pareto"} <= set(chart_keys)


def test_build_finding_engine_input_rejects_unsupported_scope() -> None:
    with pytest.raises(ValueError, match="does not support scope"):
        build_finding_engine_input(
            lens="attribute_mix",
            scope="cross_category",
            selection_context={},
        )


def test_build_analysis_scope_marks_brand_filter_as_brand_report() -> None:
    analysis_scope = build_analysis_scope(
        dataset="us_cosmetics",
        retailers=["ulta"],
        categories=["blush"],
        brands=["rare beauty"],
        price_bands=["mid"],
        pareto_classes=["A"],
        attribute_filters={"coverage": ["light", "sheer"]},
    )

    assert analysis_scope.report_mode == "brand_report"
    assert analysis_scope.dataset == "us_cosmetics"
    assert analysis_scope.retailers == ("ulta",)
    assert analysis_scope.categories == ("blush",)
    assert analysis_scope.brands == ("rare beauty",)
    assert analysis_scope.price_bands == ("mid",)
    assert analysis_scope.pareto_classes == ("A",)
    assert analysis_scope.attribute_filters == {
        "coverage": ("light", "sheer"),
    }


def test_growth_size_claim_specs_defer_variance_until_operator_is_ready() -> None:
    claim_specs = list_initial_finding_claim_specs("growth_size")

    assert [claim.claim_key for claim in claim_specs] == [
        "level_shift",
        "sustained_growth_or_decline",
        "volatility_or_spike",
        "units_price_variance",
    ]
    assert claim_specs[-1].method == "derived_trusted"
    assert claim_specs[-1].status == "deferred"


def test_build_finding_engine_input_keeps_only_enabled_claim_specs() -> None:
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
    )

    assert [claim.claim_key for claim in engine_input.claim_specs] == [
        "level_shift",
        "sustained_growth_or_decline",
        "volatility_or_spike",
    ]
    assert [
        claim.claim_key for claim in list_enabled_finding_claim_specs("growth_size")
    ] == [
        "level_shift",
        "sustained_growth_or_decline",
        "volatility_or_spike",
    ]


def test_build_finding_engine_input_growth_size_prefers_primary_growth_charts() -> None:
    analysis_scope = build_analysis_scope(
        retailers=["ulta"],
        categories=["blush"],
    )
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        analysis_scope=analysis_scope,
        selection_context={},
    )

    assert engine_input.analysis_scope.report_mode == "market_report"
    assert engine_input.analysis_scope.categories == ("blush",)
    assert [claim.claim_key for claim in engine_input.claim_specs] == [
        "level_shift",
        "sustained_growth_or_decline",
        "volatility_or_spike",
    ]
    assert [action.chart_key for action in engine_input.candidate_actions] == [
        "total_combo",
        "stacked_column",
        "area_absolute",
    ]


def test_build_growth_size_candidates_returns_level_shift_and_sustained_growth() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="growth_size",
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
                    {"month": "2024-02", "sales": 11.2},
                    {"month": "2024-03", "sales": 11.8},
                    {"month": "2024-04", "sales": 12.7},
                    {"month": "2024-05", "sales": 13.8},
                    {"month": "2024-06", "sales": 15.4},
                ],
            }
        },
    )

    candidates = build_growth_size_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "The slice grew materially from 2024-01 to 2024-06.",
        "The slice showed sustained growth across the observed rolling 12-month series.",
    ]
    assert all(candidate.chart_id == "combo-123" for candidate in candidates)
    assert candidates[0].chart_key == "total_combo"
    assert candidates[1].chart_key == "total_combo"


def test_build_growth_size_candidates_flags_spiky_series() -> None:
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo": {
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-01", "sales": 10.0},
                    {"month": "2024-02", "sales": 10.5},
                    {"month": "2024-03", "sales": 10.1},
                    {"month": "2024-04", "sales": 22.0},
                    {"month": "2024-05", "sales": 9.8},
                    {"month": "2024-06", "sales": 10.2},
                ],
            }
        },
    )

    candidates = build_growth_size_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "The slice showed a spiky or highly volatile monthly pattern.",
    ]
    assert candidates[0].metrics[2].key == "spike_ratio"


def test_build_growth_size_candidates_uses_rolling_for_structural_and_monthly_for_volatility() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo_rolling_12": {
                "chart_id": "rolling-123",
                "metric": "sales",
                "unit": "mUSD",
                "window_months": 12,
                "monthly_series": [
                    {"month": "2024-12", "sales": 100.0},
                    {"month": "2025-01", "sales": 108.0},
                    {"month": "2025-02", "sales": 116.0},
                    {"month": "2025-03", "sales": 124.0},
                ],
            },
            "total_combo_monthly": {
                "chart_id": "monthly-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-10", "sales": 10.0},
                    {"month": "2024-11", "sales": 10.5},
                    {"month": "2024-12", "sales": 10.1},
                    {"month": "2025-01", "sales": 22.0},
                    {"month": "2025-02", "sales": 9.8},
                    {"month": "2025-03", "sales": 10.2},
                ],
            },
        },
    )

    candidates = build_growth_size_candidates(engine_input)

    assert [candidate.claim_key for candidate in candidates] == [
        "level_shift",
        "sustained_growth_or_decline",
        "volatility_or_spike",
    ]
    assert [candidate.chart_id for candidate in candidates] == [
        "monthly-123",
        "monthly-123",
        "monthly-123",
    ]


def test_build_growth_size_candidates_skips_incomplete_rolling_prefix() -> None:
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo_rolling_12": {
                "chart_id": "rolling-123",
                "metric": "sales",
                "unit": "mUSD",
                "window_months": 12,
                "monthly_series": [
                    {"month": f"2024-{month:02d}", "sales": float(month)}
                    for month in range(1, 13)
                ]
                + [
                    {"month": "2025-01", "sales": 24.0},
                    {"month": "2025-02", "sales": 26.0},
                ],
            },
            "total_combo_monthly": {
                "chart_id": "monthly-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-09", "sales": 10.0},
                    {"month": "2024-10", "sales": 10.2},
                    {"month": "2024-11", "sales": 10.1},
                    {"month": "2024-12", "sales": 10.0},
                    {"month": "2025-01", "sales": 9.9},
                    {"month": "2025-02", "sales": 10.1},
                ],
            },
        },
    )

    candidates = build_growth_size_candidates(engine_input)

    level_shift = candidates[0]
    assert level_shift.claim == "The slice grew materially from 2024-12 to 2025-02."
    assert level_shift.metrics[0].value == 12.0


def test_build_growth_size_candidates_returns_empty_without_monthly_series() -> None:
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={"total_combo": {"metric": "sales", "unit": "mUSD"}},
    )

    assert build_growth_size_candidates(engine_input) == ()


def test_build_price_value_capture_candidates_detects_mid_shift() -> None:
    engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "chart_id": "stacked-456",
                "segment_key": "segment",
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 40.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 18.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 50.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 32.0},
                ],
            }
        },
    )

    candidates = build_price_value_capture_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Mid price band gained meaningful share from 2024-01 to 2025-01.",
        "The mix moved toward mid-priced bands over the period.",
    ]
    assert all(candidate.chart_id == "stacked-456" for candidate in candidates)
    assert candidates[0].chart_key == "stacked_share"


def test_build_price_value_capture_candidates_detects_premiumization() -> None:
    engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 35.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 45.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 26.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 36.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 38.0},
                ],
            }
        },
    )

    candidates = build_price_value_capture_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Premium price band gained meaningful share from 2024-01 to 2025-01.",
        "The mix premiumized over the period.",
    ]


def test_build_price_value_capture_candidates_returns_empty_without_rows() -> None:
    engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={"stacked_share": {"chart_id": "stacked-456"}},
    )

    assert build_price_value_capture_candidates(engine_input) == ()


def test_build_price_value_capture_candidates_prefers_namespaced_price_payload() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={
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
            }
        },
    )

    candidates = build_price_value_capture_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Premium price band gained meaningful share from 2024-01 to 2025-01.",
        "The mix premiumized over the period.",
    ]
    assert all(candidate.chart_id == "price-123" for candidate in candidates)


def test_build_brand_shift_candidates_detects_leader_change_and_redistribution() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="brand_shifts",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "slope": {
                "chart_id": "slope-789",
                "rows": [
                    {
                        "brand": "rare beauty",
                        "start_share_pct": 32.0,
                        "end_share_pct": 14.0,
                    },
                    {"brand": "rhode", "start_share_pct": 8.0, "end_share_pct": 24.0},
                    {"brand": "elf", "start_share_pct": 14.0, "end_share_pct": 18.0},
                ],
            }
        },
    )

    candidates = build_brand_shift_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Leadership shifted from rare beauty to rhode over the period.",
        "Elf gained meaningful share outside the leading position.",
        "Brand shares redistributed materially, with Rare beauty down and Rhode up.",
    ]
    assert all(candidate.chart_id == "slope-789" for candidate in candidates)
    assert [candidate.chart_key for candidate in candidates] == [
        "slope",
        "slope",
        "slope",
    ]


def test_build_brand_shift_candidates_detects_challenger_loss() -> None:
    engine_input = build_finding_engine_input(
        lens="brand_shifts",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "slope": {
                "rows": [
                    {
                        "brand": "rare beauty",
                        "start_share_pct": 30.0,
                        "end_share_pct": 29.0,
                    },
                    {"brand": "elf", "start_share_pct": 15.0, "end_share_pct": 8.0},
                    {"brand": "rhode", "start_share_pct": 6.0, "end_share_pct": 11.0},
                ],
            }
        },
    )

    candidates = build_brand_shift_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Elf lost meaningful share outside the leading position.",
    ]


def test_build_brand_shift_candidates_returns_empty_without_slope_rows() -> None:
    engine_input = build_finding_engine_input(
        lens="brand_shifts",
        scope="single_category",
        selection_context={},
        numeric_payloads={"slope": {"chart_id": "slope-789"}},
    )

    assert build_brand_shift_candidates(engine_input) == ()


def test_build_attribute_mix_candidates_detects_share_shift_and_emerging_pocket() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "chart_id": "attr-123",
                "rows": [
                    {"month": "2024-01", "segment": "cream", "share_pct": 45.0},
                    {"month": "2024-01", "segment": "powder", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "liquid", "share_pct": 7.0},
                    {"month": "2024-01", "segment": "stick", "share_pct": 8.0},
                    {"month": "2025-01", "segment": "cream", "share_pct": 52.0},
                    {"month": "2025-01", "segment": "powder", "share_pct": 28.0},
                    {"month": "2025-01", "segment": "liquid", "share_pct": 12.0},
                    {"month": "2025-01", "segment": "stick", "share_pct": 8.0},
                ],
            }
        },
    )

    candidates = build_attribute_mix_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Powder lost meaningful share from 2024-01 to 2025-01.",
        "Liquid emerged as a meaningful pocket within the mix.",
    ]
    assert all(candidate.chart_id == "attr-123" for candidate in candidates)
    assert candidates[0].chart_key == "stacked_share"


def test_build_attribute_mix_candidates_detects_polarization() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "rows": [
                    {"month": "2024-01", "segment": "cream", "share_pct": 35.0},
                    {"month": "2024-01", "segment": "powder", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "liquid", "share_pct": 10.0},
                    {"month": "2024-01", "segment": "stick", "share_pct": 15.0},
                    {"month": "2025-01", "segment": "cream", "share_pct": 39.0},
                    {"month": "2025-01", "segment": "powder", "share_pct": 29.0},
                    {"month": "2025-01", "segment": "liquid", "share_pct": 14.0},
                    {"month": "2025-01", "segment": "stick", "share_pct": 18.0},
                ],
            }
        },
    )

    candidates = build_attribute_mix_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Powder lost meaningful share from 2024-01 to 2025-01.",
        "The mix polarized, with Cream and Liquid gaining while Powder declined.",
    ]


def test_build_attribute_mix_candidates_returns_empty_without_rows() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={},
        numeric_payloads={"stacked_share": {"chart_id": "attr-123"}},
    )

    assert build_attribute_mix_candidates(engine_input) == ()


def test_build_attribute_mix_candidates_prefers_namespaced_attribute_payload() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share_attribute": {
                "chart_id": "attr-999",
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
            }
        },
    )

    candidates = build_attribute_mix_candidates(engine_input)

    assert [candidate.claim for candidate in candidates] == [
        "Coverage mix shifted as Buildable lost meaningful share from 2024-01 to 2025-01.",
        "Coverage mix polarized, with Light and Sheer gaining while Buildable declined.",
    ]
    assert all(candidate.chart_id == "attr-999" for candidate in candidates)


def test_build_attribute_mix_candidates_scans_multiple_attribute_payloads() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
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
    )

    candidates = build_attribute_mix_candidates(engine_input)

    assert {
        candidate.story_key
        for candidate in candidates
        if candidate.claim_key == "attribute_share_shift"
    } == {
        "attribute_mix:coverage:structure_shift",
        "attribute_mix:form:structure_shift",
    }
    assert {
        candidate.claim
        for candidate in candidates
        if candidate.claim_key == "attribute_share_shift"
    } == {
        "Coverage mix shifted as Buildable lost meaningful share from 2024-01 to 2025-01.",
        "Format mix shifted as Powder lost meaningful share from 2024-01 to 2025-01.",
    }
    assert {
        candidate.chart_key
        for candidate in candidates
        if candidate.claim_key == "emerging_attribute_pocket"
    } == {"stacked_share"}


def test_rank_and_deduplicate_findings_keeps_only_top_attribute_story_per_dimension() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
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
                "finish": {
                    "chart_id": "finish-123",
                    "segment_key": "finish",
                    "dimension_label": "Finish",
                    "rows": [
                        {"month": "2024-01", "segment": "natural", "share_pct": 73.5},
                        {"month": "2024-01", "segment": "luminous", "share_pct": 4.8},
                        {"month": "2024-01", "segment": "matte", "share_pct": 21.7},
                        {"month": "2025-01", "segment": "natural", "share_pct": 49.3},
                        {"month": "2025-01", "segment": "luminous", "share_pct": 12.3},
                        {"month": "2025-01", "segment": "matte", "share_pct": 38.4},
                    ],
                },
            }
        },
    )

    shortlisted = rank_and_deduplicate_findings(
        build_attribute_mix_candidates(engine_input),
        max_findings=4,
        max_per_lens=4,
    )

    assert [candidate.story_key for candidate in shortlisted] == [
        "attribute_mix:finish:structure_shift",
        "attribute_mix:coverage:polarization",
    ]


def test_rank_and_deduplicate_findings_collapses_overlapping_story_keys() -> None:
    growth_engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo": {
                "chart_id": "combo-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-01", "sales": 10.0},
                    {"month": "2024-02", "sales": 11.2},
                    {"month": "2024-03", "sales": 11.8},
                    {"month": "2024-04", "sales": 12.7},
                    {"month": "2024-05", "sales": 13.8},
                    {"month": "2024-06", "sales": 15.4},
                ],
            }
        },
    )
    price_engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 40.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 18.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 50.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 32.0},
                ],
            }
        },
    )

    candidates = (
        *build_growth_size_candidates(growth_engine_input),
        *build_price_value_capture_candidates(price_engine_input),
    )

    shortlisted = rank_and_deduplicate_findings(candidates)

    assert len(shortlisted) == 2
    assert {candidate.claim for candidate in shortlisted} == {
        "Mid price band gained meaningful share from 2024-01 to 2025-01.",
        "The slice grew materially from 2024-01 to 2024-06.",
    }


def test_rank_and_deduplicate_findings_keeps_distinct_story_keys_within_lens() -> None:
    growth_engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo": {
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
            }
        },
    )

    candidates = build_growth_size_candidates(growth_engine_input)
    shortlisted = rank_and_deduplicate_findings(
        candidates, max_findings=3, max_per_lens=2
    )

    assert [candidate.claim_key for candidate in shortlisted] == [
        "level_shift",
        "volatility_or_spike",
    ]


def test_build_ranked_finding_shortlist_runs_current_detectors() -> None:
    shortlisted = build_ranked_finding_shortlist(
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
                    {"month": "2024-02", "sales": 11.2},
                    {"month": "2024-03", "sales": 11.8},
                    {"month": "2024-04", "sales": 12.7},
                    {"month": "2024-05", "sales": 13.8},
                    {"month": "2024-06", "sales": 15.4},
                ],
            },
            "stacked_share": {
                "chart_id": "stacked-456",
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 40.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 18.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 50.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 32.0},
                ],
            },
        },
    )

    assert len(shortlisted) == 2
    assert {candidate.lens for candidate in shortlisted} == {
        "growth_size",
        "price_value_capture",
    }


def test_build_ranked_finding_shortlist_can_use_price_and_attribute_payload_aliases_together() -> (
    None
):
    shortlisted = build_ranked_finding_shortlist(
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
                    {"month": "2024-02", "sales": 10.2},
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
            "stacked_share_attribute": {
                "chart_id": "attr-999",
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
        },
        lenses=("growth_size", "price_value_capture", "attribute_mix"),
        max_findings=6,
        max_per_lens=2,
    )

    assert {candidate.lens for candidate in shortlisted} == {
        "growth_size",
        "price_value_capture",
        "attribute_mix",
    }


def test_build_ranked_finding_shortlist_ignores_lenses_without_detectors() -> None:
    shortlisted = build_ranked_finding_shortlist(
        scope="single_category",
        selection_context={},
        numeric_payloads={},
        lenses=("brand_shifts", "attribute_mix"),
    )

    assert shortlisted == ()


def test_resolve_finding_evidence_plan_prefers_claim_primary_chart_and_tracks_payloads() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo": {
                "chart_id": "combo-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-01", "sales": 10.0},
                    {"month": "2024-02", "sales": 11.2},
                    {"month": "2024-03", "sales": 11.8},
                    {"month": "2024-04", "sales": 12.7},
                    {"month": "2024-05", "sales": 13.8},
                    {"month": "2024-06", "sales": 15.4},
                ],
            }
        },
    )
    candidate = build_growth_size_candidates(engine_input)[0]

    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)

    assert evidence_plan.primary_option is not None
    assert evidence_plan.primary_option.chart_key == "total_combo"
    assert evidence_plan.primary_option.chart_id == "combo-123"
    assert evidence_plan.primary_option.has_payload is True
    assert [option.chart_key for option in evidence_plan.supporting_options] == [
        "area_absolute",
        "stacked_column",
    ]
    assert all(
        option.has_payload is False for option in evidence_plan.supporting_options
    )
    assert evidence_plan.missing_preferred_chart_keys == ()


def test_resolve_finding_evidence_plan_matches_growth_alias_by_chart_id() -> None:
    engine_input = build_finding_engine_input(
        lens="growth_size",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "total_combo_rolling_12": {
                "chart_id": "rolling-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-12", "sales": 100.0},
                    {"month": "2025-01", "sales": 108.0},
                    {"month": "2025-02", "sales": 116.0},
                    {"month": "2025-03", "sales": 124.0},
                ],
            },
            "total_combo_monthly": {
                "chart_id": "monthly-123",
                "metric": "sales",
                "unit": "mUSD",
                "monthly_series": [
                    {"month": "2024-10", "sales": 10.0},
                    {"month": "2024-11", "sales": 10.5},
                    {"month": "2024-12", "sales": 10.1},
                    {"month": "2025-01", "sales": 22.0},
                    {"month": "2025-02", "sales": 9.8},
                    {"month": "2025-03", "sales": 10.2},
                ],
            },
        },
    )
    candidate = build_growth_size_candidates(engine_input)[2]

    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)

    assert evidence_plan.primary_option is not None
    assert evidence_plan.primary_option.chart_key == "total_combo"
    assert evidence_plan.primary_option.chart_id == "monthly-123"
    assert evidence_plan.primary_option.has_payload is True


def test_resolve_finding_evidence_plan_marks_unavailable_preferred_chart_keys() -> None:
    engine_input = build_finding_engine_input(
        lens="price_value_capture",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share": {
                "rows": [
                    {"month": "2024-01", "segment": "premium", "share_pct": 20.0},
                    {"month": "2024-01", "segment": "mid", "share_pct": 40.0},
                    {"month": "2024-01", "segment": "value", "share_pct": 40.0},
                    {"month": "2025-01", "segment": "premium", "share_pct": 18.0},
                    {"month": "2025-01", "segment": "mid", "share_pct": 50.0},
                    {"month": "2025-01", "segment": "value", "share_pct": 32.0},
                ],
            }
        },
    )
    candidate = build_price_value_capture_candidates(engine_input)[1]

    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)

    assert evidence_plan.primary_option is not None
    assert evidence_plan.primary_option.chart_key == "stacked_share"
    assert [option.chart_key for option in evidence_plan.supporting_options] == [
        "slope",
        "stacked_column",
    ]
    assert evidence_plan.missing_preferred_chart_keys == ()


def test_resolve_finding_evidence_plan_uses_lens_specific_payload_alias() -> None:
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
        selection_context={},
        numeric_payloads={
            "stacked_share_attribute": {
                "chart_id": "attr-999",
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
        },
    )
    candidate = build_attribute_mix_candidates(engine_input)[0]

    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)

    assert evidence_plan.primary_option is not None
    assert evidence_plan.primary_option.chart_key == "stacked_share"
    assert evidence_plan.primary_option.chart_id == "attr-999"
    assert evidence_plan.primary_option.has_payload is True


def test_resolve_finding_evidence_plan_uses_matching_attribute_payload_from_multi_map() -> (
    None
):
    engine_input = build_finding_engine_input(
        lens="attribute_mix",
        scope="single_category",
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
    )
    candidates = build_attribute_mix_candidates(engine_input)
    candidate = next(
        current
        for current in candidates
        if current.story_key == "attribute_mix:coverage:structure_shift"
    )

    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)

    assert evidence_plan.primary_option is not None
    assert evidence_plan.primary_option.chart_key == "stacked_share"
    assert evidence_plan.primary_option.chart_id == "coverage-123"
    assert evidence_plan.primary_option.has_payload is True
