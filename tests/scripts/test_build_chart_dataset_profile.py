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
