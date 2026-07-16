from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "distribution-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


def _clear_non_shared_modules() -> None:
    for name in list(sys.modules):
        if name != "modules" and not name.startswith("modules."):
            continue
        del sys.modules[name]


def load_plugin_module(module_name: str, filename: str) -> Any:
    _clear_non_shared_modules()
    shared_vendor = ROOT / "plugins" / "_shared" / "vendor"
    shared_text = str(shared_vendor)
    while shared_text in sys.path:
        sys.path.remove(shared_text)
    sys.path.insert(0, shared_text)
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        while str(SCRIPT_DIR) in sys.path:
            sys.path.remove(str(SCRIPT_DIR))
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Distribution MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def sample_distribution_frame() -> pl.DataFrame:
    rows = []
    brands = ["Nice N Easy", "Nutrisse", "Casting", "Excellence"]
    channels = ["Retail", "Online"]
    for period_index, period in enumerate(["PY", "AC"]):
        for brand_index, brand in enumerate(brands):
            for channel_index, channel in enumerate(channels):
                for item_index in range(4):
                    rows.append(
                        {
                            "Period": period,
                            "Brand": brand,
                            "Channel": channel,
                            "Sales": float(
                                10
                                + brand_index * 2
                                + channel_index
                                + item_index
                                + period_index * 1.5
                            ),
                        }
                    )
    return pl.DataFrame(rows)


def sample_date_only_distribution_frame() -> pl.DataFrame:
    """Return data with dates but no explicit period/scenario column."""

    return pl.DataFrame(
        {
            "Date": [
                date(2015, 9, 6),
                date(2016, 8, 21),
                date(2016, 9, 4),
                date(2017, 8, 27),
            ],
            "Brand": ["A", "B", "A", "B"],
            "Channel": ["Retail", "Retail", "Online", "Online"],
            "Sales": [10.0, 12.0, 14.0, 16.0],
        }
    )


def fake_legacy_figure_writer(
    _fig: Any, path: Path
) -> tuple[list[Path], dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("legacy plotly artifact\n", encoding="utf-8")
    return [path], {
        "artifact": path.name,
        "renderer": "legacy_plotly+test_stub",
        "plotly_export_error": None,
        "html_artifact": None,
        "screenshot_error": None,
        "export_width": 1400,
        "export_height": 900,
    }


def fake_distribution_chart_writer(
    _canonical: Any,
    _recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    **kwargs: Any,
) -> Any:
    render = bool(kwargs.get("render", True))
    artifact_path = output_dir / str(spec["artifact_name"])
    if render:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("legacy plotly artifact\n", encoding="utf-8")
    chart_context = {
        "schema_version": "1.0",
        "chart": spec["name"],
        "legacy_chart": spec["legacy_chart_key"],
        "chart_data_source": (
            "legacy set_up_tab_for_show_or_download_chart input dataframe"
        ),
        "metric": spec.get("metric"),
        "distribution_dimension": spec.get("distribution_dimension"),
        "small_multiples_dimension": spec.get("small_multiples_dimension"),
        "selected_periods": spec.get("selected_periods") or [],
        "source_functions": [
            f"modules.charting.plot_charts.{spec['plotter']}",
            "modules.charting.draw_distribution.draw_histogram_chart",
        ],
        "data_frame": {
            "columns": ["Period", "Value"],
            "row_count": 1,
            "rows": [{"Period": "AC", "Value": 12.0}],
        },
        "plotly_figures": [{"data": []}],
        "exports": [{"artifact": artifact_path.name}],
    }
    return SimpleNamespace(
        paths=[str(artifact_path)] if render else [],
        audit={
            "status": "written_legacy" if render else "data_written",
            "chart": spec["name"],
            "legacy_chart": spec["legacy_chart_key"],
            "legacy_reference_function": (
                f"modules.charting.plot_charts.{spec['plotter']}"
            ),
            "legacy_draw_function": "modules.charting.draw_distribution.draw_histogram_chart",
            "metric": spec.get("metric"),
            "distribution_dimension": spec.get("distribution_dimension"),
            "small_multiples_dimension": spec.get("small_multiples_dimension"),
            "selected_periods": spec.get("selected_periods") or [],
            "artifact_paths": [str(artifact_path)] if render else [],
            "rendered": render,
            "source_functions": chart_context["source_functions"],
        },
        chart_context=chart_context,
    )


def test_build_chart_specs_includes_standard_and_small_multiples() -> None:
    distribution_core = load_plugin_module(
        "distribution_core_specs", "distribution_core.py"
    )
    frame = sample_distribution_frame()
    recipe = distribution_core.build_recipe(Path("sales.csv"), frame)
    recipe["options"]["reporting_entity_label"] = "Mexico hair color"

    specs = distribution_core.build_chart_specs(recipe)

    assert [spec["name"] for spec in specs] == [
        "histogram",
        "histogram_small_multiples",
        "boxplot",
        "boxplot_small_multiples",
        "stripplot",
        "stripplot_small_multiples",
        "ecdf",
        "ecdf_small_multiples",
        "kernel_density",
        "kernel_density_small_multiples",
    ]
    assert {spec["plotter"] for spec in specs} == {
        "plot_histogram_charts",
        "plot_boxplot_charts",
        "plot_stripplot_charts",
        "plot_ecdf_charts",
        "plot_kernel_density_charts",
    }
    assert all(spec["reporting_entity_label"] == "Mexico hair color" for spec in specs)
    assert all(spec["capture_chart_data"] for spec in specs)


def test_build_recipe_resolves_redundant_small_multiples_dimension() -> None:
    distribution_core = load_plugin_module(
        "distribution_core_redundant_small_multiples", "distribution_core.py"
    )
    frame = sample_distribution_frame()

    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Brand",
                "period_column": "Period",
            },
            "options": {
                "charts": ["boxplot"],
                "small_multiples": True,
                "reporting_entity_label": "Mexico hair color",
            },
        },
    )
    specs = distribution_core.build_chart_specs(recipe)

    assert recipe["options"]["reporting_entity_label"] == "Mexico hair color"
    assert recipe["mappings"]["small_multiples_dimension"] == "Channel"
    assert (
        recipe["options"]["small_multiples_dimension_audit"][
            "requested_small_multiples_dimension"
        ]
        == "Brand"
    )
    assert (
        recipe["options"]["small_multiples_dimension_audit"][
            "resolved_small_multiples_dimension"
        ]
        == "Channel"
    )
    assert recipe["options"]["small_multiples_dimension_audit"]["status"] == (
        "resolved_alternative_dimension"
    )
    assert [spec["name"] for spec in specs] == [
        "boxplot",
        "boxplot_small_multiples",
    ]
    small_multiple_spec = next(
        spec for spec in specs if spec["name"] == "boxplot_small_multiples"
    )
    assert small_multiple_spec["index_cols"] == ["Channel", "Brand"]


def test_build_recipe_derives_two_rolling_periods_from_dates_without_period_column() -> (
    None
):
    distribution_core = load_plugin_module(
        "distribution_core_date_periods", "distribution_core.py"
    )
    frame = sample_date_only_distribution_frame()

    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Channel",
                "date_column": "Date",
                "period_column": None,
            },
            "options": {
                "charts": ["histogram", "kernel_density"],
                "selected_periods": ["AC"],
                "small_multiples": True,
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)
    specs = distribution_core.build_chart_specs(recipe)

    assert recipe["options"]["selected_periods"] == ["~Aug-2016", "~Aug-2017"]
    assert recipe["options"]["period_bucketing_audit"]["status"] == "applied"
    assert (
        recipe["options"]["period_bucketing_audit"]["period_comparison_mode"]
        == "rolling_period"
    )
    assert recipe["options"]["period_bucketing_audit"]["baseline"]["date_count"] == 2
    assert recipe["options"]["period_bucketing_audit"]["comparison"]["date_count"] == 2
    assert set(canonical.get_column("Period").to_list()) == {
        "~Aug-2016",
        "~Aug-2017",
    }
    assert all(spec["selected_periods"] == ["~Aug-2016", "~Aug-2017"] for spec in specs)


def test_build_recipe_can_derive_fiscal_quarters_from_dates_without_period_column() -> (
    None
):
    distribution_core = load_plugin_module(
        "distribution_core_fiscal_periods", "distribution_core.py"
    )
    frame = sample_date_only_distribution_frame()

    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Channel",
                "date_column": "Date",
                "period_column": None,
            },
            "options": {
                "period_type": "fiscal",
                "period_grain": "quarter",
                "fiscal_start_month": 4,
                "selected_periods": ["FY2017Q2", "FY2018Q2"],
                "charts": ["histogram"],
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)

    assert recipe["options"]["period_type"] == "fiscal"
    assert recipe["options"]["period_grain"] == "quarter"
    assert recipe["options"]["selected_periods"] == ["FY2017Q2", "FY2018Q2"]
    assert recipe["options"]["period_bucketing_audit"]["available_periods"] == [
        "FY2016Q2",
        "FY2017Q2",
        "FY2018Q2",
    ]
    assert set(canonical.get_column("Period").to_list()) == {"FY2017Q2", "FY2018Q2"}


def test_build_recipe_can_derive_calendar_months_from_dates_without_period_column() -> (
    None
):
    distribution_core = load_plugin_module(
        "distribution_core_calendar_periods", "distribution_core.py"
    )
    frame = pl.DataFrame(
        {
            "Date": [
                date(2024, 3, 1),
                date(2024, 3, 15),
                date(2024, 3, 31),
                date(2025, 3, 1),
                date(2025, 3, 15),
                date(2025, 3, 31),
                date(2025, 2, 28),
            ],
            "Brand": ["A", "B", "C", "A", "B", "C", "D"],
            "Channel": [
                "Retail",
                "Retail",
                "Online",
                "Retail",
                "Retail",
                "Online",
                "Online",
            ],
            "Sales": [10.0, 11.0, 12.0, 14.0, 15.0, 16.0, 99.0],
        }
    )

    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Channel",
                "date_column": "Date",
                "period_column": None,
            },
            "options": {
                "period_type": "calendar",
                "period_grain": "month",
                "selected_periods": ["2024-03", "2025-03"],
                "charts": ["histogram"],
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)

    assert recipe["options"]["period_type"] == "calendar"
    assert recipe["options"]["period_grain"] == "month"
    assert recipe["options"]["selected_periods"] == ["2024-03", "2025-03"]
    assert sorted(recipe["options"]["period_bucketing_audit"]["available_periods"]) == [
        "2024-03",
        "2025-02",
        "2025-03",
    ]
    assert set(canonical.get_column("Period").to_list()) == {"2024-03", "2025-03"}


def test_build_recipe_can_derive_to_date_periods_from_dates_without_period_column() -> (
    None
):
    distribution_core = load_plugin_module(
        "distribution_core_to_date_periods", "distribution_core.py"
    )
    frame = pl.DataFrame(
        {
            "Date": [
                date(2024, 1, 31),
                date(2024, 2, 29),
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2025, 1, 31),
                date(2025, 2, 28),
                date(2025, 3, 31),
            ],
            "Brand": ["A", "B", "C", "D", "A", "B", "C"],
            "Channel": [
                "Retail",
                "Retail",
                "Online",
                "Online",
                "Retail",
                "Retail",
                "Online",
            ],
            "Sales": [10.0, 11.0, 12.0, 99.0, 14.0, 15.0, 16.0],
        }
    )

    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Channel",
                "date_column": "Date",
                "period_column": None,
            },
            "options": {
                "period_type": "to_date",
                "period_grain": "month",
                "charts": ["histogram"],
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)

    assert recipe["options"]["period_type"] == "to_date"
    assert (
        recipe["options"]["period_bucketing_audit"]["comparison"]["start_date"]
        == "2025-01-01"
    )
    assert (
        recipe["options"]["period_bucketing_audit"]["baseline"]["start_date"]
        == "2024-01-01"
    )
    assert recipe["options"]["selected_periods"] == ["_Mar-2024", "_Mar-2025"]
    assert set(canonical.get_column("Period").to_list()) == {"_Mar-2024", "_Mar-2025"}


def test_legacy_distribution_rolling_titles_use_canonical_dates(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    legacy = load_plugin_module(
        "legacy_distribution_charting_date_titles", "legacy_distribution_charting.py"
    )
    distribution_core = load_plugin_module(
        "distribution_core_date_titles", "distribution_core.py"
    )
    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_legacy_figure_writer)
    monkeypatch.setattr(
        sys.modules["legacy_distribution_charting"],
        "_write_legacy_figure",
        fake_legacy_figure_writer,
    )
    frame = sample_date_only_distribution_frame()
    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": "Brand",
                "small_multiples_dimension": "Channel",
                "date_column": "Date",
                "period_column": None,
            },
            "options": {
                "charts": ["kernel_density"],
                "selected_periods": ["AC"],
                "small_multiples": False,
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)
    specs = distribution_core.build_chart_specs(recipe)

    export = legacy.write_legacy_distribution_chart(
        canonical,
        recipe,
        tmp_path,
        specs[0],
    )

    title_text = " ".join(
        annotation["text"]
        for figure in export.chart_context["plotly_figures"]
        for annotation in figure["annotations"]
    )
    assert "~AUG-2016 vs ~AUG-2017" in title_text
    assert "~JUN-2025" not in title_text
    assert "~JUN-2026" not in title_text


def test_legacy_distribution_charts_route_through_legacy_plotters(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    legacy = load_plugin_module(
        "legacy_distribution_charting_route", "legacy_distribution_charting.py"
    )
    distribution_core = load_plugin_module(
        "distribution_core_route", "distribution_core.py"
    )
    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_legacy_figure_writer)
    monkeypatch.setattr(
        sys.modules["legacy_distribution_charting"],
        "_write_legacy_figure",
        fake_legacy_figure_writer,
    )
    frame = sample_distribution_frame()
    recipe = distribution_core.build_recipe(Path("sales.csv"), frame)
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)
    specs = distribution_core.build_chart_specs(recipe)
    cache = legacy.LegacyPreparedDataCache.empty()

    audits = []
    for spec in specs:
        export = legacy.write_legacy_distribution_chart(
            canonical,
            recipe,
            tmp_path,
            spec,
            prepared_data_cache=cache,
        )
        audits.append(export.audit)

    assert len(audits) == 10
    assert all(audit["status"] == "written_legacy" for audit in audits)
    assert all(
        audit["legacy_reference_function"].startswith(
            "modules.charting.plot_charts.plot_"
        )
        for audit in audits
    )
    assert all(
        audit["legacy_draw_function"].startswith(
            "modules.charting.draw_distribution.draw_"
        )
        for audit in audits
    )
    assert any(
        audit["prepared_data_cache"]["aggregate_hits"] > 0 for audit in audits[1:]
    )
    assert any(audit["small_multiples_dimension"] == "Brand" for audit in audits)


def test_legacy_distribution_small_multiples_preserve_observations(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    legacy = load_plugin_module(
        "legacy_distribution_charting_observations",
        "legacy_distribution_charting.py",
    )
    distribution_core = load_plugin_module(
        "distribution_core_observations", "distribution_core.py"
    )
    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_legacy_figure_writer)
    monkeypatch.setattr(
        sys.modules["legacy_distribution_charting"],
        "_write_legacy_figure",
        fake_legacy_figure_writer,
    )
    frame = sample_distribution_frame()
    recipe = distribution_core.build_recipe(
        Path("sales.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Sales",
                "distribution_dimension": None,
                "small_multiples_dimension": "Channel",
                "period_column": "Period",
                "dimensions": ["Brand", "Channel"],
            },
            "options": {
                "charts": ["boxplot"],
                "selected_periods": ["PY", "AC"],
                "small_multiples": True,
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)
    small_multiples_spec = next(
        spec
        for spec in distribution_core.build_chart_specs(recipe)
        if spec["name"] == "boxplot_small_multiples"
    )

    export = legacy.write_legacy_distribution_chart(
        canonical,
        recipe,
        tmp_path,
        small_multiples_spec,
    )

    assert export.audit["status"] == "written_legacy"
    assert export.chart_context["data_frame"]["row_count"] == frame.height
    observed_counts = (
        pl.DataFrame(export.chart_context["data_frame"]["rows"])
        .group_by(["Channel", "Period"])
        .len()
        .with_columns(pl.col("len").cast(pl.Int64))
        .sort(["Channel", "Period"])
    )
    expected_counts = pl.DataFrame(
        {
            "Channel": ["Online", "Online", "Retail", "Retail"],
            "Period": ["AC", "PY", "AC", "PY"],
            "len": [16, 16, 16, 16],
        }
    )
    assert_frame_equal(observed_counts, expected_counts)


def test_legacy_distribution_price_metric_preserves_topn_value_columns(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    legacy = load_plugin_module(
        "legacy_distribution_charting_price", "legacy_distribution_charting.py"
    )
    distribution_core = load_plugin_module(
        "distribution_core_price", "distribution_core.py"
    )
    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_legacy_figure_writer)
    monkeypatch.setattr(
        sys.modules["legacy_distribution_charting"],
        "_write_legacy_figure",
        fake_legacy_figure_writer,
    )
    frame = pl.DataFrame(
        {
            "Period": ["PY", "PY", "PY", "AC", "AC", "AC"],
            "Type": ["Permanent", "Semi", "Root", "Permanent", "Semi", "Root"],
            "Unit_Price_CHF": [11.2, 8.4, 5.1, 12.1, 8.7, 5.6],
        }
    )
    recipe = distribution_core.build_recipe(
        Path("prices.csv"),
        frame,
        existing_recipe={
            "mappings": {
                "metric_column": "Unit_Price_CHF",
                "distribution_dimension": "Type",
                "small_multiples_dimension": "Type",
                "period_column": "Period",
                "dimensions": ["Type"],
            },
            "options": {
                "charts": ["kernel_density"],
                "selected_periods": ["AC", "PY"],
                "small_multiples": True,
            },
        },
    )
    canonical = distribution_core.prepare_canonical_frame(frame, recipe)
    specs = distribution_core.build_chart_specs(recipe)

    export = legacy.write_legacy_distribution_chart(
        canonical,
        recipe,
        tmp_path,
        specs[0],
    )

    assert [spec["name"] for spec in specs] == ["kernel_density"]
    assert recipe["mappings"]["small_multiples_dimension"] is None
    assert recipe["options"]["small_multiples_dimension_audit"]["status"] == (
        "disabled_no_alternative_dimension"
    )
    assert export.audit["status"] == "written_legacy"
    assert export.audit["legacy_reference_function"].endswith(
        "plot_kernel_density_charts"
    )


def test_write_chart_context_artifacts_handles_late_string_values(
    tmp_path: Path,
) -> None:
    distribution_core = load_plugin_module(
        "distribution_core_mixed_context_rows", "distribution_core.py"
    )
    chart_context = {
        "chart_data_source": "test",
        "data_frame": {
            "columns": ["sales", "price_band"],
            "rows": [
                {"sales": 10.0, "price_band": None},
                {"sales": 12.0, "price_band": None},
                {"sales": 14.0, "price_band": "mid"},
            ],
        },
    }

    paths, audit = distribution_core.write_chart_context_artifacts(
        "histogram", chart_context, tmp_path
    )

    table_path = tmp_path / "histogram_chart_data.csv"
    written = pl.read_csv(table_path)
    assert str(table_path) in paths
    assert audit["table_status"] == "written"
    assert written.get_column("price_band").to_list() == [None, None, "mid"]
    assert written.get_column("sales").to_list() == [10.0, 12.0, 14.0]


def test_run_distribution_applies_like_for_like_recipe_cohort(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    legacy = load_plugin_module(
        "legacy_distribution_charting_cohorts", "legacy_distribution_charting.py"
    )
    distribution_core = load_plugin_module(
        "distribution_core_cohorts", "distribution_core.py"
    )
    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_legacy_figure_writer)
    monkeypatch.setattr(
        sys.modules["legacy_distribution_charting"],
        "_write_legacy_figure",
        fake_legacy_figure_writer,
    )
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "distribution"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "Product": ["Common", "Common", "New", "Lost", "Zero PY", "Zero PY"],
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
                    "metric_column": "Sales",
                    "distribution_dimension": "Product",
                    "small_multiples_dimension": None,
                    "period_column": "Period",
                    "dimensions": ["Product"],
                },
                "options": {
                    "charts": ["histogram"],
                    "selected_periods": ["PY", "AC"],
                    "small_multiples": False,
                    "like_for_like": {"source_dimension": "Product"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = distribution_core.run_distribution(input_path, output_dir, recipe_path)

    used_recipe = distribution_core.read_json(output_dir / "used_recipe.json")
    retained_products = set(
        result.canonical_frame.select("Product").unique().to_series().to_list()
    )
    cohort_audit = used_recipe["options"]["recipe_cohort_audit"]
    assert retained_products == {"Common"}
    assert cohort_audit["like_for_like"]["retained_entity_count"] == 1
    assert cohort_audit["like_for_like"]["removed_entity_count"] == 3
    assert used_recipe["options"]["cohort_definition"]["activity_rule"] == "Sales > 0.0"
