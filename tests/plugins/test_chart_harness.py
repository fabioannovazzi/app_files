from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
SHARED_VENDOR = ROOT / "plugins" / "_shared" / "vendor"
HARNESS_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "chart_harness"
    / "artifacts.py"
)
PERIOD_DERIVATIONS_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "chart_harness"
    / "period_derivations.py"
)
RECIPE_FILTERS_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "chart_harness"
    / "recipe_filters.py"
)
ANALYSIS_CONTEXT_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "chart_harness"
    / "analysis_context.py"
)
PERIOD_CONTRACT_PATH = (
    ROOT
    / "plugins"
    / "_shared"
    / "vendor"
    / "modules"
    / "chart_harness"
    / "period_contract.py"
)


def load_harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "chart_harness_artifacts", HARNESS_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_period_derivations() -> Any:
    spec = importlib.util.spec_from_file_location(
        "chart_harness_period_derivations", PERIOD_DERIVATIONS_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_recipe_filters() -> Any:
    spec = importlib.util.spec_from_file_location(
        "chart_harness_recipe_filters", RECIPE_FILTERS_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_analysis_context() -> Any:
    shared_text = str(SHARED_VENDOR)
    if shared_text in sys.path:
        sys.path.remove(shared_text)
    sys.path.insert(0, shared_text)
    importlib.invalidate_caches()
    return importlib.import_module("modules.chart_harness.analysis_context")


def load_period_contract() -> Any:
    spec = importlib.util.spec_from_file_location(
        "chart_harness_period_contract", PERIOD_CONTRACT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_available_analysis_context_exposes_time_and_scenario_choices() -> None:
    analysis_context = load_analysis_context()
    frame = pl.DataFrame(
        {
            "Date": [
                "2026-01-04",
                "2026-01-11",
                "2026-01-18",
                "2026-01-25",
                "2026-02-01",
            ],
            "Scenario": ["AC", "PY", "PL", "FC", "AC"],
            "Sales": [10.0, 8.0, 9.0, 11.0, 12.0],
        }
    )

    context = analysis_context.available_analysis_context(frame)

    date_profile = context["time"]["date_columns"][0]
    scenario_profile = context["scenario"]["scenario_columns"][0]
    time_frames = {item["id"]: item for item in date_profile["available_time_frames"]}
    period_contract = context["time"]["period_contract"]

    assert context["time"]["default_date_column"] == "Date"
    assert period_contract["period_types"] == [
        "calendar",
        "to_date",
        "rolling",
        "fiscal",
        "custom",
    ]
    assert period_contract["period_grains"] == ["year", "quarter", "month", "week"]
    assert period_contract["comparison_modes"] == ["single", "two_period", "series"]
    assert date_profile["observed_grain"] == "weekly"
    assert date_profile["calendar_periods"]["weeks"]["count"] == 5
    assert time_frames["calendar_month"]["available"] is True
    assert time_frames["rolling_window"]["windows"][0] == {
        "id": "rolling_4_weeks",
        "available": True,
    }
    assert context["time"]["fiscal_calendar"]["available"] is False
    assert context["scenario"]["default_scenario_column"] == "Scenario"
    assert scenario_profile["recognized_roles"] == {
        "AC": ["AC"],
        "PY": ["PY"],
        "PL": ["PL"],
        "FC": ["FC"],
    }


def test_period_contract_detects_forecast_and_period_grains() -> None:
    period_contract = load_period_contract()

    baseline, comparison = period_contract.default_scenario_comparison_pair(
        ["AC", "FC"]
    )

    assert (baseline, comparison) == ("FC", "AC")
    assert period_contract.scenario_column_kind("Scenario", ["AC", "FC"]) == "scenario"
    assert (
        period_contract.scenario_column_kind("Period", ["AC", "PY"])
        == "comparison_period_labels"
    )
    assert period_contract.period_contract_options(
        {
            "period_comparison_mode": "year_to_date",
            "period_grain": "quarterly",
            "fiscal_start_month": 4,
        }
    ) == {
        "period_type": "to_date",
        "period_grain": "quarter",
        "fiscal_start_month": 4,
    }
    assert period_contract.period_contract_options(
        {
            "period_type": "calendar",
            "period_grain": "monthly",
            "fiscal_year_start_month": 7,
        }
    ) == {
        "period_type": "fiscal",
        "period_grain": "month",
        "fiscal_start_month": 7,
    }
    assert (
        period_contract.calendar_period_label(
            date(2026, 4, 1),
            period_grain="quarter",
            fiscal_start_month=4,
        )
        == "FY2027Q1"
    )


def test_write_prepared_data_manifest_records_deterministic_contract(
    tmp_path: Path,
) -> None:
    harness = load_harness()
    frame = pl.DataFrame({"Region": ["North", "South"], "Sales": [10.0, 15.0]})
    prepared_path = tmp_path / "canonical.csv"
    frame.write_csv(prepared_path)

    manifest_path = harness.write_prepared_data_manifest(
        output_dir=tmp_path,
        plugin="example-plugin",
        chart_family="example_family",
        source_file=Path("sales.csv"),
        prepared_path=prepared_path,
        frame=frame,
        recipe={
            "mappings": {"amount_column": "Sales"},
            "options": {"currency": "EUR"},
        },
        preparation_audit={"status": "prepared"},
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["producer"]["plugin"] == "example-plugin"
    assert payload["prepared_data"]["path"] == "canonical.csv"
    assert payload["prepared_data"]["row_count"] == 2
    assert payload["prepared_data"]["column_count"] == 2
    assert payload["mappings"]["amount_column"] == "Sales"
    assert (
        payload["interpretation_boundary"]["semantic_business_interpretation_owner"]
        == "reporting_consumer"
    )


def test_build_manifest_artifacts_uses_shared_kind_mapping(tmp_path: Path) -> None:
    harness = load_harness()
    chart_path = tmp_path / "chart.png"
    table_path = tmp_path / "table.csv"
    context_path = tmp_path / "context.json"
    chart_path.write_bytes(b"png")
    table_path.write_text("a\n1\n", encoding="utf-8")
    context_path.write_text("{}\n", encoding="utf-8")

    records = harness.build_manifest_artifacts(
        [chart_path, table_path, context_path, tmp_path / "missing.csv"],
        tmp_path,
    )

    assert [record["kind"] for record in records] == ["chart", "table", "context"]
    assert [record["artifact_id"] for record in records] == [
        "chart",
        "table",
        "context",
    ]


def test_recipe_filters_apply_include_exclude_and_audit_rows() -> None:
    filters = load_recipe_filters()
    frame = pl.DataFrame(
        {
            "Channel": ["Mexico City", "Monterrey", "Mexico City", "Guadalajara"],
            "Brand": ["Koleston", "Koleston", "Nutrisse", "Koleston"],
            "Sales": [10.0, 20.0, 30.0, 40.0],
        }
    )

    result, audit = filters.apply_recipe_filters(
        frame,
        {
            "filters": {
                "Channel": {"include": ["Mexico City", "Monterrey"]},
                "Brand": {"exclude": ["Nutrisse"]},
            }
        },
    )

    assert result.select("Sales").to_series().to_list() == [10.0, 20.0]
    assert audit["status"] == "written"
    assert audit["rows_before"] == 4
    assert audit["rows_after"] == 2
    assert audit["filters"][0]["removed_rows"] == 1
    assert audit["filters"][1]["removed_rows"] == 1


def test_recipe_filters_support_shorthand_and_numeric_zero() -> None:
    filters = load_recipe_filters()
    frame = pl.DataFrame(
        {
            "Promotion": [0, 1, 0],
            "Brand": ["A", "A", "B"],
        }
    )

    result, audit = filters.apply_recipe_filters(
        frame,
        {"filters": {"Promotion": 0, "Brand": "A"}},
    )

    assert result.to_dicts() == [{"Promotion": 0, "Brand": "A"}]
    assert audit["rows_after"] == 1


def test_recipe_filters_apply_comparisons_and_hidden_title_audit() -> None:
    filters = load_recipe_filters()
    frame = pl.DataFrame(
        {
            "Sales": [0.0, 10.0, 20.0, 30.0],
            "Brand": ["A", "A", "B", "C"],
        }
    )

    result, audit = filters.apply_recipe_filters(
        frame,
        {
            "filters": [
                {
                    "column": "Sales",
                    "gt": 0,
                    "lte": 20,
                    "show_in_title": False,
                }
            ]
        },
    )

    assert result.to_dicts() == [
        {"Sales": 10.0, "Brand": "A"},
        {"Sales": 20.0, "Brand": "B"},
    ]
    assert audit["rows_after"] == 2
    assert audit["filters"][0]["gt"] == 0.0
    assert audit["filters"][0]["lte"] == 20.0
    assert audit["filters"][0]["display_in_title"] is False


def test_recipe_filters_legacy_filter_dict_uses_legacy_keys() -> None:
    filters = load_recipe_filters()

    legacy_filter = filters.legacy_filter_dict_from_recipe(
        {
            "filters": {
                "Channel": {"include": ["Mexico City"]},
                "Brand": {"exclude": ["Nutrisse"]},
            }
        }
    )

    assert legacy_filter == {
        "Channel": {"toIncludeItems": ["Mexico City"]},
        "Brand": {"toExcludeItems": ["Nutrisse"]},
    }


def test_recipe_filters_attach_legacy_title_metadata() -> None:
    filters = load_recipe_filters()
    chart: dict[str, Any] = {}

    result = filters.apply_legacy_filter_title_metadata(
        chart,
        {
            "filterDictName": "filterDictName",
            "filterActiveName": "filterActiveName",
        },
        {"filters": {"Channel": "Mexico City"}},
    )

    assert result is chart
    assert chart["filterActiveName"] is True
    assert chart["filterDictName"] == {"Channel": {"toIncludeItems": ["Mexico City"]}}


def test_recipe_filters_preserve_root_and_options_filters() -> None:
    filters = load_recipe_filters()

    recipe = filters.preserve_recipe_filters(
        {"options": {"currency": "LC"}},
        {
            "filters": {"Channel": "Mexico City"},
            "options": {"filters": {"Brand": {"exclude": ["Nutrisse"]}}},
        },
    )

    assert recipe["filters"] == {"Channel": "Mexico City"}
    assert recipe["options"]["filters"] == {"Brand": {"exclude": ["Nutrisse"]}}
    assert recipe["options"]["currency"] == "LC"


def test_period_derivations_add_since_and_lost_columns() -> None:
    derivations = load_period_derivations()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "Brand": [
                "Established",
                "Established",
                "New",
                "Lost",
                "Zero PY",
                "Zero PY",
            ],
            "Sales": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
        }
    )

    result, audit = derivations.add_comparison_cohort_columns(
        frame,
        [
            {
                "source_dimension": "Brand",
                "name": "Brand_Since",
                "kind": "since",
            },
            {
                "source_dimension": "Brand",
                "name": "Brand_Lost",
                "kind": "lost",
            },
        ],
        period_column="Period",
        value_column="Sales",
    )

    labels = {
        row["Brand"]: (row["Brand_Since"], row["Brand_Lost"])
        for row in result.unique("Brand").sort("Brand").to_dicts()
    }
    assert labels == {
        "Established": ("Since PY", "Active"),
        "Lost": ("Since PY", "Lost after PY"),
        "New": ("Since AC", "Active"),
        "Zero PY": ("Since AC", "Active"),
    }
    assert audit["derived_dimensions"][0]["activity_rule"] == "Sales > 0.0"
    assert audit["derived_dimensions"][1]["output_column"] == "Brand_Lost"


def test_period_derivations_bucket_multi_year_since_and_lost_labels() -> None:
    derivations = load_period_derivations()
    frame = pl.DataFrame(
        {
            "Period": [
                "2013",
                "2017",
                "2015",
                "2017",
                "2016",
                "2017",
                "2017",
                "2016",
                "2014",
            ],
            "Brand": [
                "Established",
                "Established",
                "Since 2015",
                "Since 2015",
                "Since 2016",
                "Since 2016",
                "New",
                "Lost 2016",
                "Lost before",
            ],
            "Sales": [10.0, 12.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 3.0],
        }
    )

    result, audit = derivations.add_comparison_cohort_columns(
        frame,
        [
            {"source_dimension": "Brand", "name": "Brand_Since", "kind": "since"},
            {"source_dimension": "Brand", "name": "Brand_Lost", "kind": "lost"},
        ],
        period_column="Period",
        value_column="Sales",
        current_period="2017",
        previous_period="2016",
    )

    labels = {
        row["Brand"]: (row["Brand_Since"], row["Brand_Lost"])
        for row in result.unique("Brand").sort("Brand").to_dicts()
    }
    assert labels == {
        "Established": ("Before 2015", "Active"),
        "Lost 2016": ("Since 2016", "Lost after 2016"),
        "Lost before": ("Before 2015", "Lost before 2015"),
        "New": ("Since 2017", "Active"),
        "Since 2015": ("Since 2015", "Active"),
        "Since 2016": ("Since 2016", "Active"),
    }
    assert audit["derived_dimensions"][0]["visible_periods"] == [
        "2015",
        "2016",
        "2017",
    ]
    assert audit["derived_dimensions"][1]["older_period_bucket"] == "before 2015"


def test_period_derivations_all_active_lost_dimension_has_only_active_label() -> None:
    derivations = load_period_derivations()
    frame = pl.DataFrame(
        {
            "Period": ["2016", "2017", "2016", "2017"],
            "Brand": ["A", "A", "B", "B"],
            "Sales": [10.0, 12.0, 5.0, 6.0],
        }
    )

    result, _audit = derivations.add_comparison_cohort_columns(
        frame,
        [{"source_dimension": "Brand", "name": "Brand_Lost", "kind": "lost"}],
        period_column="Period",
        value_column="Sales",
        current_period="2017",
        previous_period="2016",
    )

    assert result.select("Brand_Lost").unique().to_series().to_list() == ["Active"]


def test_period_derivations_filter_like_for_like_positive_activity() -> None:
    derivations = load_period_derivations()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "Product": [
                "Common",
                "Common",
                "New",
                "Lost",
                "Zero PY",
                "Zero PY",
            ],
            "Sales": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
        }
    )

    result, audit = derivations.filter_like_for_like_entities(
        frame,
        {"source_dimension": "Product"},
        period_column="Period",
        value_column="Sales",
    )

    assert result.select("Product").unique().to_series().to_list() == ["Common"]
    assert audit["entity_count"] == 4
    assert audit["retained_entity_count"] == 1
    assert audit["removed_entity_count"] == 3


def test_recipe_cohorts_apply_like_for_like_and_store_effective_contract() -> None:
    derivations = load_period_derivations()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "SKU": ["Common", "Common", "New", "Lost", "Zero PY", "Zero PY"],
            "Sales": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
        }
    )
    recipe = {"options": {"like_for_like": {"source_dimension": "SKU"}}}

    result, audit = derivations.apply_recipe_cohorts(
        frame,
        recipe,
        period_column="Period",
        value_column="Sales",
        current_period="AC",
        previous_period="PY",
    )

    assert result.select("SKU").unique().to_series().to_list() == ["Common"]
    assert audit["status"] == "written"
    assert audit["cohort_definition"]["like_for_like"]["source_dimension"] == "SKU"
    assert audit["cohort_definition"]["like_for_like"]["cohort_mode"] == (
        "like_for_like"
    )
    assert audit["cohort_definition"]["periods"] == {
        "period_column": "Period",
        "value_column": "Sales",
        "current_period": "AC",
        "previous_period": "PY",
    }
    assert audit["cohort_definition"]["activity_rule"] == "Sales > 0.0"
    assert recipe["options"]["cohort_definition"] == audit["cohort_definition"]
