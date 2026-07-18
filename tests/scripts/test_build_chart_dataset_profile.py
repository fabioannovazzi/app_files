from __future__ import annotations

from datetime import date

import polars as pl

from scripts.build_chart_dataset_profile import _profile_frame


def _profile_for_test() -> dict:
    frame = pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)],
            "sales": [100.0, 120.0, 90.0],
            "units": [10, 12, 9],
            "sales_share": [0.4, 0.5, 0.3],
            "avg_price": [10.0, 10.0, 10.0],
            "price_raw": ["$10.00", "$12.00", "$9.00"],
            "discount": [1.0, 2.0, 3.0],
            "category": ["makeup", "skin", "hair"],
            "sku_id": ["a", "b", "c"],
        }
    )
    return _profile_frame(
        frame,
        dataset_id="test_dataset",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )


def test_profile_frame_classifies_core_chart_selection_roles() -> None:
    profile = _profile_for_test()
    columns = profile["columns"]

    assert columns["month"]["role"] == "period"
    assert columns["month"]["period_grain"] == "month"
    assert columns["month"]["period_parseability"]["is_parseable"] is True
    assert columns["month"]["period_parseability"]["parser"] == "native_temporal_dtype"
    assert columns["month"]["period_parseability"]["parse_success_ratio"] == 1.0
    assert columns["sales"]["metric_class"] == "additive_value"
    assert columns["sales"]["aggregation"] == "sum"
    assert columns["units"]["metric_class"] == "additive_volume"
    assert columns["category"]["role"] == "dimension"
    assert columns["sku_id"]["role"] == "identifier"


def test_profile_frame_does_not_mark_share_or_price_as_additive() -> None:
    profile = _profile_for_test()
    columns = profile["columns"]

    assert columns["sales_share"]["metric_class"] == "share"
    assert columns["sales_share"]["aggregation"] == "semantic_layer_defined"
    assert columns["avg_price"]["metric_class"] == "rate"
    assert columns["avg_price"]["aggregation"] == "semantic_layer_defined"
    assert columns["price_raw"]["metric_class"] == "rate"
    assert columns["price_raw"]["requires_cast"] is True
    assert columns["discount"]["metric_class"] == "additive_value"


def test_profile_frame_exposes_value_per_volume_derived_rate_candidates() -> None:
    profile = _profile_for_test()

    assert (
        profile["derived_metrics"]["sales_per_units"]["metric_class"] == "derived_rate"
    )
    assert profile["derived_metrics"]["sales_per_units"]["produced_from"] == [
        "sales",
        "units",
    ]
    assert "sales_per_units" in profile["metric_classes"]["derived_rate"]


def test_profile_frame_exposes_selector_profile_summary() -> None:
    profile = _profile_for_test()
    selector_profile = profile["selector_profile"]

    assert selector_profile["period_candidates"][0]["column"] == "month"
    assert selector_profile["period_candidates"][0]["grain"] == "month"
    assert (
        selector_profile["period_candidates"][0]["period_parseability"][
            "inferred_grain"
        ]
        == "month"
    )
    assert "sales" in [
        candidate["column"]
        for candidate in selector_profile["metric_candidates_by_class"][
            "additive_value"
        ]
    ]
    assert "sales_per_units" in [
        candidate["column"]
        for candidate in selector_profile["metric_candidates_by_class"]["derived_rate"]
    ]
    assert selector_profile["role_candidate_counts"]["direct_dimension"] == 1
    assert selector_profile["boundary"].startswith("Mechanical selector profile only")


def test_profile_frame_recognizes_common_period_labels_and_statement_roles() -> None:
    frame = pl.DataFrame(
        {
            "fiscal_quarter": ["2025-Q1", "2025-Q2", "2025-Q3"],
            "statement_line": ["Revenue", "Cost", "Profit"],
            "scenario": ["PL", "AC", "FC"],
            "statement_value": [100.0, 80.0, 20.0],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="statement_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    assert profile["columns"]["fiscal_quarter"]["role"] == "period"
    assert profile["columns"]["fiscal_quarter"]["period_grain"] == "quarter"
    assert profile["role_candidate_columns"]["statement_line_item"] == [
        "statement_line"
    ]
    assert profile["role_candidate_columns"]["statement_scenario"] == ["scenario"]


def test_profile_frame_does_not_treat_partially_parseable_labels_as_period() -> None:
    frame = pl.DataFrame(
        {
            "period_label": ["2025-01", "not a period", "also invalid", "2025-02"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="mixed_period_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    assert profile["columns"]["period_label"]["role"] == "dimension"
    assert (
        profile["columns"]["period_label"]["period_parseability"]["parse_success_ratio"]
        == 0.5
    )


def test_profile_frame_uses_full_period_column_for_bounds() -> None:
    frame = pl.DataFrame(
        {
            "month": [f"2025-{month:02d}-01" for month in range(1, 13)],
            "sales": [float(month) for month in range(1, 13)],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="full_period_bounds_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    evidence = profile["columns"]["month"]["period_parseability"]
    assert evidence["parsed_min"] == "2025-01-01"
    assert evidence["parsed_max"] == "2025-12-01"
    assert evidence["bounds_source"] == "full_column_distinct_values"
    assert evidence["parsed_distinct_count"] == 12


def test_profile_frame_ranks_explicit_funnel_stage_above_generic_stage() -> None:
    frame = pl.DataFrame(
        {
            "Stage": ["Lead", "Won", "Lead"],
            "funnel_stage": ["Visit", "Trial", "Purchase"],
            "stage_start_count": [100, 60, 20],
            "stage_pass_count": [60, 20, 10],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="funnel_stage_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    ordered = profile["role_candidates"]["ordered_stage"]
    assert [candidate["column"] for candidate in ordered] == [
        "funnel_stage",
        "Stage",
    ]
    assert ordered[0]["confidence"] == "high"


def test_profile_frame_ranks_explicit_set_column_above_generic_segment() -> None:
    frame = pl.DataFrame(
        {
            "ItemID": ["A", "A", "B", "B"],
            "SetName": ["Retailer A", "Retailer B", "Retailer A", "Retailer C"],
            "Segment": ["North", "North", "South", "South"],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="set_role_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    set_dimensions = profile["role_candidates"]["set_dimension"]
    assert profile["columns"]["ItemID"]["role"] == "identifier"
    assert set_dimensions[0]["column"] == "SetName"
    assert set_dimensions[0]["confidence"] == "high"


def test_profile_frame_splits_camel_case_metric_hints() -> None:
    frame = pl.DataFrame(
        {
            "MarginRate": [0.20, 0.25, 0.30],
            "NetSales": [100.0, 120.0, 140.0],
        }
    )

    profile = _profile_frame(
        frame,
        dataset_id="camel_case_fixture",
        source={"path": "memory", "format": "test", "sheet_name": None},
    )

    assert profile["columns"]["MarginRate"]["metric_class"] == "rate"
    assert profile["columns"]["NetSales"]["metric_class"] == "additive_value"
