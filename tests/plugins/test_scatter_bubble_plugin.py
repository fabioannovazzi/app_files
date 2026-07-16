from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "scatter-bubble-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import legacy_scatter_bubble_charting as legacy_charting
import scatter_bubble_core as core


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Scatter Bubble MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def sample_sales_frame() -> pl.DataFrame:
    """Return a compact frame that exercises normal and small-multiple charts."""

    return pl.DataFrame(
        {
            "Date": [
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
                "2026-01-01",
            ],
            "Period": ["AC", "AC", "AC", "AC", "AC", "AC", "AC", "AC"],
            "Brand": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "Retailer": [
                "North",
                "South",
                "East",
                "West",
                "North",
                "South",
                "East",
                "West",
            ],
            "Type": [
                "Permanent",
                "Permanent",
                "Tone",
                "Tone",
                "Other",
                "Other",
                "Male",
                "Male",
            ],
            "Unit Price": [3.5, 3.9, 4.2, 4.8, 5.1, 5.5, 6.0, 6.4],
            "Units": [40, 47, 52, 61, 68, 75, 84, 91],
            "Sales": [140.0, 183.3, 218.4, 292.8, 346.8, 412.5, 504.0, 582.4],
        }
    )


def weighted_price_frame() -> pl.DataFrame:
    """Return repeated brand rows that require weighted price aggregation."""

    return pl.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-01", "2026-01-01", "2025-01-01"],
            "Period": ["AC", "AC", "AC", "PY"],
            "Brand": ["A", "A", "B", "A"],
            "Company": ["X", "X", "Y", "X"],
            "Channel": ["North", "South", "North", "North"],
            "Unit Price": [10.0, 20.0, 8.0, 100.0],
            "Units": [10.0, 20.0, 5.0, 10.0],
            "Sales": [100.0, 400.0, 40.0, 1000.0],
        }
    )


def large_sales_weighted_price_frame() -> pl.DataFrame:
    """Return weighted price data with absolute sales requiring a value prefix."""

    return weighted_price_frame().with_columns(
        (pl.col("Sales") * 1_000_000).alias("Sales")
    )


def weighted_price_recipe(input_path: Path) -> dict[str, Any]:
    """Return an explicit scatter recipe for weighted price checks."""

    return {
        "schema_version": "1.0",
        "source_file": str(input_path),
        "language": "en",
        "mappings": {
            "x_metric_column": "Unit Price",
            "y_metric_column": "Units",
            "bubble_size_metric_column": "Sales",
            "dimensions": ["Brand", "Company", "Channel"],
            "dot_dimension": "Brand",
            "color_dimension": "Company",
            "small_multiples_dimension": "Channel",
            "period_column": "Period",
            "date_column": "Date",
        },
        "options": {
            "currency": "LC",
            "charts": ["scatter"],
            "small_multiples": False,
            "max_chart_items": 12,
            "small_multiples_max_panels": 6,
        },
    }


def legacy_derived_metric_frame() -> pl.DataFrame:
    """Return input where legacy must derive price and sales growth metrics."""

    return pl.DataFrame(
        {
            "Date": ["2024-12-29", "2026-01-04", "2024-12-29", "2026-01-04"],
            "Company": ["A", "A", "B", "B"],
            "Channel": ["Retail", "Retail", "Online", "Online"],
            "Value_LC": [100.0, 120.0, 200.0, 250.0],
            "Units": [10.0, 10.0, 20.0, 25.0],
        }
    )


def legacy_derived_metric_recipe(input_path: Path) -> dict[str, Any]:
    """Return a recipe that lets legacy derive bubble axis metrics."""

    return {
        "schema_version": "1.0",
        "source_file": str(input_path),
        "language": "en",
        "mappings": {
            "x_metric_column": "Unit Price",
            "y_metric_column": "Sales Growth Rate",
            "bubble_size_metric_column": "Sales",
            "dimensions": ["Company", "Channel"],
            "dot_dimension": "Company",
            "color_dimension": "Channel",
            "small_multiples_dimension": "Channel",
            "period_column": None,
            "date_column": "Date",
        },
        "options": {
            "currency": "LC",
            "charts": ["bubble"],
            "small_multiples": False,
            "max_chart_items": 12,
            "small_multiples_max_panels": 6,
            "metric_aliases": {"Sales": "Value_LC"},
            "period_derivation": {
                "type": "latest_rolling_year_vs_prior_year",
                "date_column": "Date",
                "current_period": "AC",
                "previous_period": "PY",
            },
        },
    }


def patch_plotly_export(monkeypatch: Any) -> None:
    """Avoid browser/Kaleido work while keeping real legacy Plotly figures."""

    def fake_write_legacy_figure(
        fig: Any, path: Path
    ) -> tuple[list[Path], dict[str, Any]]:
        html_path = path.with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(
            "<html><body>legacy plotly figure</body></html>", encoding="utf-8"
        )
        return [html_path], {
            "artifact": html_path.name,
            "renderer": "legacy_plotly+test_stub",
            "plotly_export_error": None,
            "html_artifact": html_path.name,
            "screenshot_error": None,
            "export_width": 1200,
            "export_height": 900,
        }

    monkeypatch.setattr(
        legacy_charting, "_write_legacy_figure", fake_write_legacy_figure
    )


def fake_scatter_bubble_writer(
    _canonical: Any,
    _recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    **kwargs: Any,
) -> Any:
    render = bool(kwargs.get("render", True))
    artifact_path = output_dir / str(spec["artifact_name"])
    if render:
        from PIL import Image

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), "white").save(artifact_path, format="PNG")
    chart_context = {
        "schema_version": "1.0",
        "chart": spec["name"],
        "legacy_chart": spec["legacy_chart_key"],
        "chart_data_source": (
            "legacy set_up_tab_for_show_or_download_chart input dataframe"
        ),
        "source_functions": [
            f"modules.charting.plot_charts.{spec['plotter']}",
            "modules.charting.draw_scatter.draw_scatter_chart",
        ],
        "data_frame": {
            "columns": ["Brand", "Sales"],
            "row_count": 1,
            "rows": [{"Brand": "A", "Sales": 140.0}],
        },
        "plotly_figures": [{"data": []}],
        "exports": [{"artifact": artifact_path.name}],
    }
    return SimpleNamespace(
        paths=[str(artifact_path)] if render else [],
        audit={
            "status": "written" if render else "data_written",
            "chart": spec["name"],
            "legacy_chart": spec["legacy_chart_key"],
            "legacy_reference_function": (
                f"modules.charting.plot_charts.{spec['plotter']}"
            ),
            "metrics_to_plot": spec["metrics"],
            "x_metric": spec["x_metric"],
            "y_metric": spec["y_metric"],
            "bubble_size_metric": spec.get("bubble_size_metric"),
            "dot_dimension": spec["dot_dimension"],
            "color_dimension": spec.get("color_dimension"),
            "dimensions": spec["dimensions"],
            "small_multiples_dimension": spec.get("small_multiples_dimension"),
            "dimension_selection": spec.get("dimension_selection"),
            "rendered": render,
            "source_functions": chart_context["source_functions"],
        },
        chart_context=chart_context,
    )


def test_build_chart_specs_defaults_to_legacy_scatter_and_bubble() -> None:
    frame = sample_sales_frame()
    recipe = core.build_recipe(Path("sales.csv"), frame)
    recipe["options"]["reporting_entity_label"] = "Mexico hair color"
    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)

    specs = core.build_chart_specs(canonical, recipe)

    assert preparation_audit["status"] == "prepared"
    assert [spec["name"] for spec in specs] == [
        "scatter",
        "scatter_small_multiples",
        "bubble",
        "bubble_small_multiples",
    ]
    assert specs[0]["plotter"] == "plot_scatter_charts"
    assert specs[2]["plotter"] == "plot_bubble_charts"
    assert specs[0]["legacy_chart_key"] == "scatterChart"
    assert specs[2]["legacy_chart_key"] == "bubbleChart"
    assert specs[0]["show_iso_line"] is True
    assert specs[0]["isoline_metric"] == "Sales"
    assert specs[1]["show_iso_line"] is True
    assert specs[0]["adjust_bubble_labels"] is True
    assert specs[1]["adjust_bubble_labels"] is True
    assert specs[2]["adjust_bubble_labels"] is True
    assert specs[3]["adjust_bubble_labels"] is True
    assert specs[1]["dot_dimension"] == specs[0]["dot_dimension"]
    assert specs[3]["dot_dimension"] == specs[0]["dot_dimension"]
    assert specs[2]["color_dimension"] is None
    assert specs[3]["color_dimension"] is None
    assert specs[2]["capture_figure"] == "last"
    assert specs[2]["plot_total_bubble"] is True
    assert specs[2]["aggregate_other_items"] is True
    assert all(spec["reporting_entity_label"] == "Mexico hair color" for spec in specs)
    assert "show_iso_line" not in specs[2]


def test_build_chart_specs_keeps_hierarchical_bubble_color() -> None:
    frame = pl.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-01", "2026-01-01"],
            "Period": ["AC", "AC", "AC"],
            "Brand": ["A", "B", "C"],
            "Company": ["X", "Y", "Y"],
            "Channel": ["Retail", "Retail", "Retail"],
            "Unit Price": [10.0, 20.0, 30.0],
            "Sales": [100.0, 200.0, 300.0],
        }
    )
    recipe = weighted_price_recipe(Path("hierarchical.csv"))
    recipe["mappings"].update(
        {
            "x_metric_column": "Unit Price",
            "y_metric_column": "Sales",
            "bubble_size_metric_column": "Sales",
            "dimensions": ["Brand", "Company", "Channel"],
            "dot_dimension": "Brand",
            "color_dimension": "Company",
            "small_multiples_dimension": None,
        }
    )
    recipe["options"]["charts"] = ["bubble"]
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)

    bubble_spec = core.build_chart_specs(canonical, recipe)[0]

    assert bubble_spec["name"] == "bubble"
    assert bubble_spec["color_dimension"] == "Company"


def test_build_chart_specs_suppresses_non_hierarchical_bubble_color() -> None:
    frame = pl.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-01", "2026-01-01"],
            "Period": ["AC", "AC", "AC"],
            "Brand": ["A", "A", "B"],
            "Company": ["X", "Y", "Y"],
            "Channel": ["Retail", "Retail", "Retail"],
            "Unit Price": [10.0, 20.0, 30.0],
            "Sales": [100.0, 200.0, 300.0],
        }
    )
    recipe = weighted_price_recipe(Path("non_hierarchical.csv"))
    recipe["mappings"].update(
        {
            "x_metric_column": "Unit Price",
            "y_metric_column": "Sales",
            "bubble_size_metric_column": "Sales",
            "dimensions": ["Brand", "Company", "Channel"],
            "dot_dimension": "Brand",
            "color_dimension": "Company",
            "small_multiples_dimension": None,
        }
    )
    recipe["options"]["charts"] = ["bubble"]
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)

    bubble_spec = core.build_chart_specs(canonical, recipe)[0]

    assert bubble_spec["name"] == "bubble"
    assert bubble_spec["color_dimension"] is None


def test_build_chart_specs_does_not_infer_sales_isoline_for_growth_rate() -> None:
    frame = pl.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-01"],
            "Period": ["AC", "AC"],
            "Company": ["A", "B"],
            "Type": ["Permanent", "Root"],
            "Sales Growth Rate (%)": [10.0, -5.0],
            "Unit Price": [3.0, 4.0],
            "Sales": [300.0, 200.0],
        }
    )
    recipe = weighted_price_recipe(Path("growth.csv"))
    recipe["mappings"].update(
        {
            "x_metric_column": "Sales Growth Rate (%)",
            "y_metric_column": "Unit Price",
            "bubble_size_metric_column": "Sales",
            "dimensions": ["Company", "Type"],
            "dot_dimension": "Company",
            "color_dimension": "Type",
            "small_multiples_dimension": None,
        }
    )
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)

    scatter_spec = core.build_chart_specs(canonical, recipe)[0]

    assert scatter_spec["show_iso_line"] is False
    assert scatter_spec["isoline_metric"] is None


def test_scatter_label_offsets_stagger_nearby_labels() -> None:
    legacy_charting.ensure_legacy_import_path()
    from modules.charting import draw_scatter

    offsets = draw_scatter._scatter_label_offsets(
        [0.0, 50.0, 50.1, 50.2, 100.0],
        [0.0, 50.0, 50.1, 50.2, 500.0],
    )

    assert offsets[1:4] == [(0, 12), (-24, 22), (24, 22)]
    assert offsets[4] == (-24, -14)


def test_scatter_label_limiter_keeps_spread_out_subset() -> None:
    legacy_charting.ensure_legacy_import_path()
    from modules.charting import draw_scatter

    frame = pl.DataFrame(
        {
            "Brand": [f"Brand {index}" for index in range(20)],
            "Unit Price": [float(index) for index in range(20)],
            "Units": [float(index * index) for index in range(20)],
        }
    )

    limited = draw_scatter._limit_scatter_label_rows(
        frame.lazy(),
        "Unit Price",
        "Units",
        max_labels=6,
    ).collect()

    assert limited.height == 6
    assert "Brand 19" in limited.get_column("Brand").to_list()


def test_build_chart_specs_sets_bubble_value_prefix_for_large_values() -> None:
    frame = large_sales_weighted_price_frame()
    recipe = weighted_price_recipe(Path("sales.csv"))
    recipe["options"]["charts"] = ["bubble"]
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)

    specs = core.build_chart_specs(canonical, recipe)

    bubble_spec = next(spec for spec in specs if spec["name"] == "bubble")
    assert bubble_spec["display_value_prefix_metric"] == "Sales"
    assert bubble_spec["display_value_prefixes"] == {"Sales": "m"}


def test_build_recipe_preserves_reporting_entity_label() -> None:
    frame = sample_sales_frame()
    explicit = weighted_price_recipe(Path("sales.csv"))
    explicit["options"]["reporting_entity_label"] = "Mexico hair color"
    explicit["options"]["metric_aliases"] = {"Sales": "Value_LC"}
    explicit["options"]["period_derivation"] = {
        "type": "latest_rolling_year_vs_prior_year",
        "date_column": "Date",
    }

    recipe = core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe=explicit,
    )

    assert recipe["options"]["reporting_entity_label"] == "Mexico hair color"
    assert recipe["options"]["metric_aliases"] == {"Sales": "Value_LC"}
    assert recipe["options"]["period_derivation"] == {
        "type": "latest_rolling_year_vs_prior_year",
        "date_column": "Date",
    }


def test_legacy_derived_metrics_keep_derivation_in_legacy_inputs() -> None:
    frame = legacy_derived_metric_frame()
    recipe = legacy_derived_metric_recipe(Path("growth.csv"))

    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)
    specs = core.build_chart_specs(canonical, recipe)

    canonical_columns = set(canonical.collect_schema().names())
    bubble_spec = next(spec for spec in specs if spec["name"] == "bubble")
    assert {"Sales", "Units"} <= canonical_columns
    assert "Unit Price" not in canonical_columns
    assert "Sales Growth Rate" not in canonical_columns
    assert set(canonical.get_column("Period").to_list()) == {"AC", "PY"}
    assert preparation_audit["metric_sources"]["Sales"] == "Value_LC"
    assert preparation_audit["legacy_derived_metrics"] == [
        "Unit Price",
        "Sales Growth Rate",
    ]
    assert preparation_audit["period_derivation"]["type"] == (
        "latest_rolling_year_vs_prior_year"
    )
    assert bubble_spec["metrics"] == [
        "Unit Price",
        "Sales Growth Rate",
        "Sales",
        "Units",
    ]
    assert bubble_spec["selected_periods"] == ["PY", "AC"]
    assert bubble_spec["to_plot_period"] == "AC"


def test_prepare_canonical_frame_can_derive_fiscal_quarter_periods() -> None:
    frame = pl.DataFrame(
        {
            "Date": ["2025-03-31", "2025-04-01", "2026-04-01"],
            "Brand": ["A", "B", "C"],
            "Company": ["X", "X", "Y"],
            "Channel": ["Retail", "Retail", "Online"],
            "Unit Price": [10.0, 12.0, 14.0],
            "Units": [4.0, 5.0, 6.0],
            "Sales": [40.0, 60.0, 84.0],
        }
    )
    recipe = weighted_price_recipe(Path("sales.csv"))
    recipe["mappings"]["period_column"] = None
    recipe["options"]["period_type"] = "fiscal"
    recipe["options"]["period_grain"] = "quarter"
    recipe["options"]["fiscal_start_month"] = 4

    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)
    specs = core.build_chart_specs(canonical, recipe)

    scatter_spec = next(spec for spec in specs if spec["name"] == "scatter")
    assert set(canonical.get_column("Period").to_list()) == {
        "FY2025Q4",
        "FY2026Q1",
        "FY2027Q1",
    }
    assert preparation_audit["period_derivation"]["period_type"] == "fiscal"
    assert preparation_audit["period_derivation"]["period_grain"] == "quarter"
    assert scatter_spec["selected_periods"] == ["FY2027Q1"]
    assert scatter_spec["to_plot_period"] == "FY2027Q1"


def test_prepare_canonical_frame_can_derive_calendar_month_periods() -> None:
    frame = pl.DataFrame(
        {
            "Date": ["2025-02-28", "2025-03-01", "2025-03-31"],
            "Brand": ["A", "B", "C"],
            "Company": ["X", "X", "Y"],
            "Channel": ["Retail", "Retail", "Online"],
            "Unit Price": [10.0, 12.0, 14.0],
            "Units": [4.0, 5.0, 6.0],
            "Sales": [40.0, 60.0, 84.0],
        }
    )
    recipe = weighted_price_recipe(Path("sales.csv"))
    recipe["mappings"]["period_column"] = None
    recipe["options"]["period_type"] = "calendar"
    recipe["options"]["period_grain"] = "month"

    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)
    specs = core.build_chart_specs(canonical, recipe)

    scatter_spec = next(spec for spec in specs if spec["name"] == "scatter")
    assert set(canonical.get_column("Period").to_list()) == {"2025-02", "2025-03"}
    assert preparation_audit["period_derivation"]["period_type"] == "calendar"
    assert preparation_audit["period_derivation"]["period_grain"] == "month"
    assert scatter_spec["selected_periods"] == ["2025-03"]
    assert scatter_spec["to_plot_period"] == "2025-03"


def test_prepare_canonical_frame_can_derive_to_date_periods() -> None:
    frame = pl.DataFrame(
        {
            "Date": [
                "2024-01-31",
                "2024-02-29",
                "2024-03-31",
                "2024-04-30",
                "2025-01-31",
                "2025-02-28",
                "2025-03-31",
            ],
            "Brand": ["A", "B", "C", "D", "A", "B", "C"],
            "Company": ["X", "X", "Y", "Y", "X", "X", "Y"],
            "Channel": [
                "Retail",
                "Retail",
                "Online",
                "Online",
                "Retail",
                "Retail",
                "Online",
            ],
            "Unit Price": [10.0, 12.0, 14.0, 99.0, 15.0, 16.0, 18.0],
            "Units": [4.0, 5.0, 6.0, 99.0, 7.0, 8.0, 9.0],
            "Sales": [40.0, 60.0, 84.0, 999.0, 105.0, 128.0, 162.0],
        }
    )
    recipe = weighted_price_recipe(Path("sales.csv"))
    recipe["mappings"]["period_column"] = None
    recipe["options"]["period_type"] = "to_date"
    recipe["options"]["period_grain"] = "month"

    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)
    specs = core.build_chart_specs(canonical, recipe)

    scatter_spec = next(spec for spec in specs if spec["name"] == "scatter")
    assert set(canonical.get_column("Period").to_list()) == {"PY", "AC"}
    assert preparation_audit["period_derivation"]["period_type"] == "to_date"
    assert preparation_audit["period_derivation"]["current_start"] == "2025-01-01"
    assert preparation_audit["period_derivation"]["previous_end"] == "2024-03-31"
    assert scatter_spec["selected_periods"] == ["AC"]
    assert scatter_spec["to_plot_period"] == "AC"


def test_prepare_canonical_frame_can_derive_rolling_week_periods() -> None:
    frame = pl.DataFrame(
        {
            "Date": [
                "2023-12-24",
                "2023-12-25",
                "2023-12-31",
                "2024-01-01",
                "2024-01-07",
            ],
            "Brand": ["Outside PY", "A", "B", "C", "D"],
            "Company": ["X", "X", "Y", "Y", "X"],
            "Channel": ["Retail", "Retail", "Online", "Online", "Retail"],
            "Unit Price": [99.0, 10.0, 12.0, 14.0, 16.0],
            "Units": [99.0, 4.0, 5.0, 6.0, 7.0],
            "Sales": [999.0, 40.0, 60.0, 84.0, 112.0],
        }
    )
    recipe = weighted_price_recipe(Path("sales.csv"))
    recipe["mappings"]["period_column"] = None
    recipe["options"]["period_type"] = "rolling"
    recipe["options"]["period_grain"] = "week"

    canonical, preparation_audit = core.prepare_canonical_frame(frame, recipe)
    specs = core.build_chart_specs(canonical, recipe)

    scatter_spec = next(spec for spec in specs if spec["name"] == "scatter")
    assert set(canonical.get_column("Brand").to_list()) == {"A", "B", "C", "D"}
    assert set(canonical.get_column("Period").to_list()) == {"PY", "AC"}
    assert preparation_audit["period_derivation"]["period_type"] == "rolling"
    assert preparation_audit["period_derivation"]["period_grain"] == "week"
    assert preparation_audit["period_derivation"]["current_start"] == "2024-01-01"
    assert preparation_audit["period_derivation"]["previous_start"] == "2023-12-25"
    assert scatter_spec["selected_periods"] == ["AC"]
    assert scatter_spec["to_plot_period"] == "AC"


def test_generated_other_bubble_rows_use_dedicated_other_color_bucket() -> None:
    legacy_charting.ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart_dict = {
        names["chosenChart"]: names["bubbleChart"],
        names["xAxisDimension"]: "Brand",
        names["yAxisDimension"]: "Company",
    }
    frame = pl.DataFrame(
        {
            "Brand": ["Brand A", "Others rank >3"],
            "Company": ["Company X", "Company X"],
        }
    )

    normalized = legacy_charting._with_generated_other_color_bucket(
        frame,
        names,
        chart_dict,
    ).collect()
    other_company = normalized.filter(pl.col("Brand") == "Others rank >3").item(
        0,
        "Company",
    )

    assert other_company == names["otherName"]
    assert legacy_charting._is_generated_other_color_item(names["otherName"], names)
    assert legacy_charting._is_generated_other_color_item("Other rank >3", names)
    assert legacy_charting._is_generated_other_color_item("Others rank >3", names)


def test_relationship_summary_weights_price_metric() -> None:
    frame = weighted_price_frame()
    recipe = weighted_price_recipe(Path("weighted.csv"))
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)

    summary = core.build_relationship_summary(canonical, recipe)

    brand_a = summary.filter(pl.col("Brand") == "A").row(0, named=True)
    assert brand_a["Sales"] == 500.0
    assert brand_a["Units"] == 30.0
    assert brand_a["Unit Price"] == 500.0 / 30.0


def test_scatter_bubble_applies_like_for_like_recipe_cohort(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    patch_plotly_export(monkeypatch)
    monkeypatch.setenv("LOKY_MAX_CPU_COUNT", "1")
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "out"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "Date": [
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
            ],
            "Period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "Brand": ["Common", "Common", "New", "Lost", "Zero PY", "Zero PY"],
            "Company": ["A", "A", "A", "A", "A", "A"],
            "Channel": ["Retail", "Retail", "Retail", "Retail", "Retail", "Retail"],
            "Unit Price": [10.0, 12.0, 5.0, 7.0, 3.0, 1.0],
            "Units": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            "Sales": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_file": str(input_path),
                "language": "en",
                "mappings": {
                    "x_metric_column": "Unit Price",
                    "y_metric_column": "Units",
                    "bubble_size_metric_column": "Sales",
                    "dimensions": ["Brand", "Company", "Channel"],
                    "dot_dimension": "Brand",
                    "color_dimension": "Company",
                    "small_multiples_dimension": "Channel",
                    "period_column": "Period",
                    "date_column": "Date",
                },
                "options": {
                    "charts": ["scatter"],
                    "small_multiples": False,
                    "like_for_like": {"source_dimension": "Brand"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = core.run_scatter_bubble(input_path, output_dir, recipe_path)

    used_recipe = core.read_json(output_dir / "used_recipe.json")
    retained_brands = set(
        result.canonical_frame.select("Brand").unique().to_series().to_list()
    )
    cohort_audit = used_recipe["options"]["recipe_cohort_audit"]
    assert retained_brands == {"Common"}
    assert cohort_audit["like_for_like"]["retained_entity_count"] == 1
    assert cohort_audit["like_for_like"]["removed_entity_count"] == 3
    assert used_recipe["options"]["cohort_definition"]["activity_rule"] == "Sales > 0.0"


def test_legacy_scatter_context_weights_grouped_price(
    tmp_path: Path, monkeypatch: Any
) -> None:
    patch_plotly_export(monkeypatch)
    frame = weighted_price_frame()
    recipe = weighted_price_recipe(Path("weighted.csv"))
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)
    spec = core.build_chart_specs(canonical, recipe)[0]

    export = legacy_charting.write_legacy_scatter_bubble_chart(
        canonical,
        recipe,
        tmp_path,
        spec,
        prepared_data_cache=legacy_charting.LegacyPreparedDataCache.empty(),
    )

    assert export.audit["status"] == "written"
    assert export.chart_context is not None
    rows = export.chart_context["data_frame"]["rows"]
    brand_a = next(row for row in rows if row["Brand"] == "A")
    assert brand_a["Units"] == 30.0
    assert brand_a["Unit Price"] == 500.0 / 30.0


def test_legacy_bubble_context_uses_existing_total_other_and_prefix_parameters(
    tmp_path: Path, monkeypatch: Any
) -> None:
    patch_plotly_export(monkeypatch)
    frame = large_sales_weighted_price_frame().rename({"Unit Price": "CWD"})
    recipe = weighted_price_recipe(Path("large.csv"))
    recipe["mappings"]["x_metric_column"] = "CWD"
    recipe["options"]["charts"] = ["bubble"]
    recipe["options"]["max_chart_items"] = 1
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)
    spec = next(
        spec
        for spec in core.build_chart_specs(canonical, recipe)
        if spec["name"] == "bubble"
    )

    export = legacy_charting.write_legacy_scatter_bubble_chart(
        canonical,
        recipe,
        tmp_path,
        spec,
        prepared_data_cache=legacy_charting.LegacyPreparedDataCache.empty(),
    )

    assert export.audit["status"] == "written"
    assert export.chart_context is not None
    chart_dict = export.chart_context["chart_dict"]
    assert chart_dict["plotTotalBubble"] is True
    assert chart_dict["adjustBubbleLabels"] is True
    assert chart_dict["X"]["aggregateOtherItems"] is True
    assert chart_dict["valuePrefixDict"] == {"Sales": "m"}
    rows = export.chart_context["data_frame"]["rows"]
    assert max(float(row["Sales"]) for row in rows) == 500.0
    assert [row for row in rows if str(row["Brand"]).startswith("Others rank >")]


def test_legacy_bubble_renders_generated_other_without_color_legend(
    tmp_path: Path, monkeypatch: Any
) -> None:
    figures: list[Any] = []

    def fake_write_legacy_figure(
        fig: Any, path: Path
    ) -> tuple[list[Path], dict[str, Any]]:
        figures.append(fig)
        html_path = path.with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html><body>legacy plotly figure</body></html>")
        return [html_path], {
            "artifact": html_path.name,
            "renderer": "legacy_plotly+test_stub",
            "plotly_export_error": None,
            "html_artifact": html_path.name,
            "screenshot_error": None,
            "export_width": 1200,
            "export_height": 900,
        }

    monkeypatch.setattr(
        legacy_charting, "_write_legacy_figure", fake_write_legacy_figure
    )
    frame = large_sales_weighted_price_frame().rename({"Unit Price": "CWD"})
    recipe = weighted_price_recipe(Path("large.csv"))
    recipe["mappings"]["x_metric_column"] = "CWD"
    recipe["options"]["charts"] = ["bubble"]
    recipe["options"]["max_chart_items"] = 1
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)
    spec = next(
        spec
        for spec in core.build_chart_specs(canonical, recipe)
        if spec["name"] == "bubble"
    )

    export = legacy_charting.write_legacy_scatter_bubble_chart(
        canonical,
        recipe,
        tmp_path,
        spec,
        prepared_data_cache=legacy_charting.LegacyPreparedDataCache.empty(),
    )

    assert export.audit["status"] == "written"
    assert figures
    figure_payload = figures[-1].to_plotly_json()
    legend_names = {
        trace.get("name")
        for trace in figure_payload["data"]
        if trace.get("showlegend") is True
    }
    assert "Other" not in legend_names
    annotations = [
        str(annotation.get("text", ""))
        for annotation in figure_payload["layout"].get("annotations", [])
    ]
    assert any(text.startswith("Others rank >") for text in annotations)
    grey_traces = [
        trace
        for trace in figure_payload["data"]
        if trace.get("showlegend") is False
        and trace.get("marker", {}).get("color") == "#D9D9D9"
    ]
    assert grey_traces


def test_shared_extract_scalar_handles_multi_column_single_row_without_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    legacy_charting.ensure_legacy_import_path()
    from modules.utilities.utils import extract_scalar

    frame = pl.DataFrame({"first": [10.0], "second": [20.0], "third": [30.0]})

    with caplog.at_level(logging.ERROR):
        value = extract_scalar(frame)

    assert value == 10.0
    assert not caplog.records


def test_prepared_cache_reuses_preparation_for_similar_specs(
    tmp_path: Path, monkeypatch: Any
) -> None:
    patch_plotly_export(monkeypatch)
    frame = sample_sales_frame()
    recipe = core.build_recipe(Path("sales.csv"), frame)
    canonical, _preparation_audit = core.prepare_canonical_frame(frame, recipe)
    spec = core.build_chart_specs(canonical, recipe)[0]
    cache = legacy_charting.LegacyPreparedDataCache.empty()

    first = legacy_charting.write_legacy_scatter_bubble_chart(
        canonical, recipe, tmp_path, spec, prepared_data_cache=cache
    )
    similar_spec = {
        **spec,
        "name": "scatter_same_prep_different_artifact",
        "artifact_name": "scatter_same_prep_different_artifact.png",
    }
    second = legacy_charting.write_legacy_scatter_bubble_chart(
        canonical, recipe, tmp_path, similar_spec, prepared_data_cache=cache
    )

    assert first.audit["status"] == "written"
    assert second.audit["status"] == "written"
    assert first.audit["prepared_data_cache"]["misses"] > 0
    assert second.audit["prepared_data_cache"]["hits"] > 0


def test_package_config_injects_legacy_scatter_bubble_modules() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_codex_plugin_zip", BUILD_SCRIPT
    )
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = builder
    spec.loader.exec_module(builder)
    package = next(item for item in builder.load_packages() if item.plugin == "clara")

    entries = builder.expected_zip_entries(package)

    for path in (
        "scripts/legacy_scatter_bubble_charting.py",
        "scripts/scatter_bubble_core.py",
        "vendor/modules/charting/plot_charts.py",
        "vendor/modules/charting/draw_scatter.py",
        "vendor/modules/charting/draw_bubble.py",
        "vendor/modules/charting/prepare_charts.py",
        "vendor/modules/utilities/ui_notifier.py",
    ):
        assert (
            f"{package.package_root}/plugins/clara/modules/"
            f"scatter-bubble-analysis/{path}" in entries
        )
