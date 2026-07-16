from __future__ import annotations

import base64
import copy
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest
from plotly import graph_objects as go
from plotly.subplots import make_subplots

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "period-comparison"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
CORE_PATH = SCRIPT_DIR / "period_core.py"
DEPENDENCY_CHECKER_PATH = SCRIPT_DIR / "check_dependencies.py"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


@pytest.fixture(autouse=True)
def clear_preexisting_matplotlib_modules() -> None:
    """Keep legacy-renderer import assertions isolated from prior tests."""

    for name in list(sys.modules):
        if name == "matplotlib" or name.startswith("matplotlib."):
            sys.modules.pop(name, None)


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("period_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dependency_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "period_check_dependencies", DEPENDENCY_CHECKER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_legacy_charting() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location(
        "period_legacy_charting", SCRIPT_DIR / "legacy_charting.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Period Comparison MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_period_fixture(path: Path) -> None:
    rows: list[dict[str, object]] = []
    for year, values in (
        (2024, [100.0, 120.0, 130.0, 140.0]),
        (2025, [130.0, 150.0, 160.0, 190.0]),
    ):
        for month, value in enumerate(values, start=1):
            rows.append(
                {
                    "Orderdate": f"{year}-{month:02d}-28",
                    "Productline": "Road" if month % 2 else "Mountain",
                    "Region": "Australia" if month <= 2 else "United States",
                    "Salesamount": value,
                }
            )
    pl.DataFrame(rows).write_csv(path)


def _legacy_metric_fixture() -> tuple[pl.DataFrame, dict[str, Any]]:
    months = range(1, 5)
    rows = [
        {
            "Date": f"{year}-{month:02d}-28",
            "Period": period,
            "Productline": "Road",
            "Salesamount": value,
        }
        for year, period, values in (
            (2024, "PY", [670_000.0, 700_000.0, 750_000.0, 800_000.0]),
            (2025, "AC", [720_000.0, 730_000.0, 810_000.0, 1_020_000.0]),
        )
        for month, value in zip(months, values)
    ]
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Salesamount",
            "dimensions": ["Productline"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "AdventureWorks",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    return canonical, recipe


def test_prepare_canonical_frame_uses_fiscal_to_date_window() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": [
                "2024-03-31",
                "2024-04-30",
                "2024-05-31",
                "2025-03-31",
                "2025-04-30",
                "2025-05-31",
            ],
            "Salesamount": [999.0, 100.0, 120.0, 888.0, 150.0, 180.0],
            "Productline": ["Road"] * 6,
        }
    )
    recipe = core.build_recipe(
        Path("sales.csv"),
        frame,
        language="en",
        existing_recipe={
            "mappings": {
                "date_column": "Date",
                "amount_column": "Salesamount",
                "dimensions": ["Productline"],
            },
            "options": {
                "period_type": "fiscal",
                "period_grain": "month",
                "fiscal_start_month": 4,
            },
        },
    )

    canonical, period_window = core.prepare_canonical_frame(frame, recipe)

    totals = core.period_totals(canonical, "Salesamount")
    assert recipe["options"]["period_type"] == "fiscal"
    assert period_window["current"]["start_date"] == "2025-04-01"
    assert period_window["previous"]["start_date"] == "2024-04-01"
    assert period_window["previous"]["end_date"] == "2024-05-31"
    assert totals["current"] == 330.0
    assert totals["previous"] == 220.0


def test_prepare_canonical_frame_uses_calendar_month_window() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": [
                "2024-01-31",
                "2024-02-29",
                "2024-03-31",
                "2025-01-31",
                "2025-02-28",
                "2025-03-31",
            ],
            "Salesamount": [999.0, 888.0, 100.0, 777.0, 666.0, 150.0],
            "Productline": ["Road"] * 6,
        }
    )
    recipe = core.build_recipe(
        Path("sales.csv"),
        frame,
        language="en",
        existing_recipe={
            "mappings": {
                "date_column": "Date",
                "amount_column": "Salesamount",
                "dimensions": ["Productline"],
            },
            "options": {
                "period_type": "calendar",
                "period_grain": "month",
            },
        },
    )

    canonical, period_window = core.prepare_canonical_frame(frame, recipe)

    totals = core.period_totals(canonical, "Salesamount")
    assert recipe["options"]["period_type"] == "calendar"
    assert period_window["current"]["start_date"] == "2025-03-01"
    assert period_window["current"]["end_date"] == "2025-03-31"
    assert period_window["previous"]["start_date"] == "2024-03-01"
    assert period_window["previous"]["end_date"] == "2024-03-31"
    assert totals["current"] == 150.0
    assert totals["previous"] == 100.0


def test_prepare_canonical_frame_derives_rolling_quarter_window() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": [
                "2024-03-31",
                "2024-04-30",
                "2024-05-31",
                "2024-06-30",
                "2025-03-31",
                "2025-04-30",
                "2025-05-31",
                "2025-06-30",
            ],
            "Salesamount": [999.0, 100.0, 110.0, 120.0, 888.0, 150.0, 160.0, 170.0],
            "Productline": ["Road"] * 8,
        }
    )
    recipe = core.build_recipe(
        Path("sales.csv"),
        frame,
        language="en",
        existing_recipe={
            "mappings": {
                "date_column": "Date",
                "amount_column": "Salesamount",
                "dimensions": ["Productline"],
            },
            "options": {
                "period_type": "rolling",
                "period_grain": "quarter",
            },
        },
    )

    canonical, period_window = core.prepare_canonical_frame(frame, recipe)

    totals = core.period_totals(canonical, "Salesamount")
    assert recipe["options"]["period_type"] == "rolling"
    assert recipe["options"]["rolling_window_months"] == 3
    assert period_window["current"]["start_date"] == "2025-04-01"
    assert period_window["current"]["end_date"] == "2025-06-30"
    assert period_window["previous"]["start_date"] == "2024-04-01"
    assert period_window["previous"]["end_date"] == "2024-06-30"
    assert totals["current"] == 480.0
    assert totals["previous"] == 330.0


def _capture_legacy_figure(legacy: Any, monkeypatch: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def capture_figure(
        fig: Any, _path: Path, _title: str
    ) -> tuple[list[Path], dict[str, Any]]:
        legacy._normalize_legacy_period_title(fig)
        captured["fig"] = fig
        return [_path], {
            "artifact": _path.name,
            "renderer": "captured",
            "plotly_export_error": None,
            "html_artifact": None,
            "screenshot_error": None,
            "export_width": 1400,
            "export_height": 900,
        }

    monkeypatch.setattr(legacy, "_write_legacy_figure", capture_figure)
    return captured


def _plotly_numeric_trace_values(values: Any) -> tuple[float, ...]:
    """Decode either ordinary or Plotly 6 binary numeric trace values."""

    if not isinstance(values, dict):
        return tuple(float(value) for value in values)
    dtype = str(values["dtype"])
    format_code = {"f4": "f", "f8": "d"}[dtype]
    raw = base64.b64decode(values["bdata"])
    item_size = struct.calcsize(format_code)
    return tuple(struct.unpack(f"<{len(raw) // item_size}{format_code}", raw))


def _fake_period_chart_writer(
    _table: pl.DataFrame,
    _canonical: pl.DataFrame,
    _recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    artifact_path = output_dir / artifact_name
    if render:
        from PIL import Image

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), "white").save(artifact_path, format="PNG")
    return (
        [str(artifact_path)] if render else [],
        {
            "status": "written" if render else "data_written",
            "artifact": artifact_name,
            "rendered": render,
            "source_functions": ["modules.charting.plot_charts.test_stub"],
        },
    )


def _fake_column_chart(
    monthly: pl.DataFrame,
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    return _fake_period_chart_writer(
        monthly,
        canonical,
        recipe,
        output_dir,
        artifact_name="year_over_year_column.png",
        render=render,
    )


def _fake_line_chart(
    monthly: pl.DataFrame,
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    render: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    return _fake_period_chart_writer(
        monthly,
        canonical,
        recipe,
        output_dir,
        artifact_name="year_over_year_line.png",
        render=render,
    )


def _small_multiple_titles_in_reading_order(
    fig: Any, expected_titles: list[str]
) -> list[str]:
    title_annotations = [
        annotation
        for annotation in fig.layout.annotations or []
        if str(getattr(annotation, "text", "")) in set(expected_titles)
        and getattr(annotation, "xref", None) == "paper"
        and getattr(annotation, "yref", None) == "paper"
    ]
    return [
        str(annotation.text)
        for annotation in sorted(
            title_annotations,
            key=lambda annotation: (
                -float(getattr(annotation, "y", None) or 0.0),
                float(getattr(annotation, "x", None) or 0.0),
            ),
        )
    ]


def test_period_recipe_rejects_same_current_and_previous_period_labels() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Orderdate": ["2025-01-01", "2024-01-01"],
            "Salesamount": [100.0, 80.0],
            "Productline": ["Bikes", "Bikes"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Orderdate",
            "amount_column": "Salesamount",
            "dimensions": ["Productline"],
        },
        "options": {
            "current_period_label": "AC",
            "previous_period_label": "AC",
        },
    }

    with pytest.raises(ValueError, match="requires distinct current and previous"):
        core.validate_recipe(frame, recipe)


def test_period_reporting_metric_label_uses_business_names() -> None:
    core = load_core()

    assert core._reporting_metric_label({"options": {}}, "Value_LC") == "Sales"
    assert core._reporting_metric_label({"options": {}}, "Salesamount") == "Sales"
    assert core._reporting_metric_label({"options": {}}, "Units") == "Units"
    assert (
        core._reporting_metric_label(
            {"options": {"reporting_metric_label": "Net sales"}},
            "Value_LC",
        )
        == "Net sales"
    )


def test_native_reporting_table_title_includes_recipe_filter(tmp_path: Path) -> None:
    core = load_core()
    monthly = pl.DataFrame(
        {
            "Date": ["2025-01-28"],
            "PY": [100.0],
            "AC": [120.0],
        }
    )
    by_period = pl.DataFrame(
        {
            "window": ["YTD"],
            "previous": [100.0],
            "current": [120.0],
        }
    )
    recipe = {
        "source_file": "/tmp/sales.csv",
        "mappings": {"amount_column": "Salesamount", "dimensions": ["Productline"]},
        "options": {
            "currency": "EUR",
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "reporting_entity_label": "Mexico hair color",
            "recipe_filter_audit": {
                "status": "written",
                "filters": [
                    {"column": "Company", "include": ["All Other Manufacturers"]}
                ],
            },
        },
    }

    core.write_native_reporting_tables(monthly, by_period, recipe, tmp_path)

    comparison_table_html = (tmp_path / "comparison_table.html").read_text(
        encoding="utf-8"
    )
    assert (
        '<p class="title-line">Mexico hair color | Company = '
        "All Other Manufacturers</p>"
    ) in comparison_table_html
    comparison_context = json.loads(
        (tmp_path / "comparison_table_chart_context.json").read_text(encoding="utf-8")
    )
    assert comparison_context["chart_title_lines"][0] == (
        "Mexico hair color | Company = All Other Manufacturers"
    )
    assert comparison_context["chart_title_lines"][1] == (
        comparison_context["title_contract"]["what"]
    )
    assert comparison_context["chart_title_lines"][2] == "AC vs PY"


def test_legacy_slope_title_uses_business_metric_label(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    canonical = canonical.rename({"Salesamount": "Value_LC"})
    recipe = copy.deepcopy(recipe)
    recipe["mappings"]["amount_column"] = "Value_LC"
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_slope_chart(canonical, recipe, tmp_path)

    title_text = "\n".join(
        str(annotation.text) for annotation in captured["fig"].layout.annotations or []
    )
    assert "Sales" in title_text
    assert "Value_LC" not in title_text


def test_legacy_column_chart_uses_consistent_metric_prefix(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_multitier_column_chart(canonical, recipe, tmp_path)

    fig = captured["fig"]
    title_text = "\n".join(
        str(annotation.text) for annotation in fig.layout.annotations or []
    )
    assert "AdventureWorks" in title_text
    assert "in mEUR" in title_text
    assert "AC AC vs PY" not in title_text
    assert "AC vs PY" in title_text
    ac_trace = next(trace for trace in fig.data if trace.name == "AC")
    delta_trace = next(
        trace for trace in fig.data if trace.name == "difference in value"
    )
    assert "  _AprÆ" in list(ac_trace.x)
    assert "1.02" in list(ac_trace.text)
    assert "+0.05" in list(delta_trace.text)
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_column_small_multiples_use_shared_axes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    canonical = canonical.with_columns(
        pl.when(pl.col("Date").dt.month() == 1)
        .then(pl.lit("Retail"))
        .when(pl.col("Date").dt.month() == 2)
        .then(pl.lit("Wholesale"))
        .otherwise(pl.lit("Online"))
        .alias("Channel")
    )
    recipe = copy.deepcopy(recipe)
    recipe["mappings"]["dimensions"] = ["Channel"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_multitier_column_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_column_small_multiples.png",
        small_multiples_dimension="Channel",
    )

    layout = captured["fig"].layout.to_plotly_json()
    assert layout["xaxis"].get("matches") is None
    assert layout["yaxis"].get("matches") is None
    assert layout["xaxis2"].get("matches") == "x"
    assert layout["yaxis2"].get("matches") == "y"
    assert layout["xaxis3"].get("matches") == "x"
    assert layout["yaxis3"].get("matches") == "y"
    assert layout["xaxis4"].get("matches") == "x"
    assert layout["yaxis4"].get("matches") == "y"
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_slope_small_multiples_show_endpoint_labels(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    canonical = canonical.with_columns(
        pl.when(pl.col("Date").dt.month() <= 2)
        .then(pl.lit("Retail"))
        .otherwise(pl.lit("Wholesale"))
        .alias("Channel")
    )
    recipe = copy.deepcopy(recipe)
    recipe["mappings"]["dimensions"] = ["Channel"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_slope_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_slope_small_multiples.png",
        small_multiples_dimension="Channel",
    )

    slope_traces = [
        trace
        for trace in captured["fig"].data
        if getattr(trace, "mode", "") == "lines+markers"
    ]
    value_annotations = [
        annotation
        for annotation in captured["fig"].layout.annotations or []
        if str(getattr(annotation, "yref", "")).startswith("y")
        and any(
            character.isdigit() for character in str(getattr(annotation, "text", ""))
        )
    ]
    assert slope_traces
    assert value_annotations
    assert all(annotation.yshift == 14 for annotation in value_annotations)
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_slope_small_multiples_follow_ranked_panel_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Permanent": {"PY": 400.0, "AC": 600.0},
        "Male": {"PY": 120.0, "AC": 100.0},
        "Root": {"PY": 40.0, "AC": 80.0},
        "Semi-Permanent": {"PY": 20.0, "AC": 28.0},
    }
    for panel, values in panel_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Type": panel,
                    "Value_LC": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    ranked_panels = ["Permanent", "Male", "Root", "Semi-Permanent"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_slope_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_slope_small_multiples.png",
        small_multiples_dimension="Type",
        repeat_values=ranked_panels,
    )

    traces_by_xaxis = {
        str(getattr(trace, "xaxis", None) or "x"): tuple(getattr(trace, "y", ()) or ())
        for trace in captured["fig"].data
        if getattr(trace, "mode", "") == "lines+markers"
    }
    assert _small_multiple_titles_in_reading_order(captured["fig"], ranked_panels) == (
        ranked_panels
    )
    assert traces_by_xaxis["x"] == pytest.approx((100.0, 150.0))
    assert traces_by_xaxis["x2"] == pytest.approx((100.0, 83.3333333333))


def test_legacy_by_period_small_multiples_follow_ranked_panel_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Root": {"PY": 40.0, "AC": 80.0},
        "Permanent": {"PY": 400.0, "AC": 600.0},
        "Semi-Permanent": {"PY": 20.0, "AC": 28.0},
        "Male": {"PY": 120.0, "AC": 100.0},
    }
    for panel, values in panel_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Type": panel,
                    "Value_LC": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    ranked_panels = ["Permanent", "Male", "Root", "Semi-Permanent"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_actual_vs_previous_year_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_by_period_small_multiples.png",
        by_period=True,
        small_multiples_dimension="Type",
        repeat_values=ranked_panels,
    )

    assert _small_multiple_titles_in_reading_order(captured["fig"], ranked_panels) == (
        ranked_panels
    )
    title_text = "\n".join(
        str(annotation.text) for annotation in captured["fig"].layout.annotations or []
    )
    assert "Weekly Average Sales by Recency Window" in title_text


def test_legacy_dot_small_multiples_follow_ranked_panel_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Root": {"North": {"PY": 18.0, "AC": 22.0}},
        "Permanent": {
            "North": {"PY": 260.0, "AC": 360.0},
            "South": {"PY": 140.0, "AC": 240.0},
        },
        "Semi-Permanent": {"North": {"PY": 10.0, "AC": 18.0}},
        "Male": {"North": {"PY": 90.0, "AC": 80.0}},
    }
    for panel, companies in panel_values.items():
        for company, values in companies.items():
            for period, value in values.items():
                year = 2025 if period == "AC" else 2024
                rows.append(
                    {
                        "Date": f"{year}-04-28",
                        "Period": period,
                        "Type": panel,
                        "Company": company,
                        "Value_LC": value,
                    }
                )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Company", "Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    ranked_panels = ["Permanent", "Male", "Root", "Semi-Permanent"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    export = legacy.write_legacy_dot_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_dot_small_multiples.png",
        dimension="Company",
        small_multiples_dimension="Type",
        repeat_values=ranked_panels,
    )

    assert export.audit["status"] == "written"
    assert export.audit["dimension"] == "Type"
    assert export.audit["dot_dimension"] == "Company"
    assert _small_multiple_titles_in_reading_order(captured["fig"], ranked_panels) == (
        ranked_panels
    )
    title_text = "\n".join(
        str(annotation.text) for annotation in captured["fig"].layout.annotations or []
    )
    assert "by Company and Type" in title_text


def test_legacy_waterfall_small_multiples_follow_ranked_panel_order(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Root": {"PY": 40.0, "AC": 80.0},
        "Permanent": {"PY": 400.0, "AC": 600.0},
        "Semi-Permanent": {"PY": 20.0, "AC": 28.0},
        "Male": {"PY": 120.0, "AC": 100.0},
    }
    for panel, values in panel_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Type": panel,
                    "Value_LC": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    ranked_panels = ["Permanent", "Male", "Root", "Semi-Permanent"]
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_horizontal_waterfall_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_waterfall_small_multiples.png",
        small_multiples_dimension="Type",
        repeat_values=ranked_panels,
    )

    assert _small_multiple_titles_in_reading_order(captured["fig"], ranked_panels) == (
        ranked_panels
    )


def test_small_multiples_table_orders_panels_by_size() -> None:
    core = load_core()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Permanent": {"PY": 400.0, "AC": 600.0},
        "Male": {"PY": 120.0, "AC": 100.0},
        "Root": {"PY": 40.0, "AC": 80.0},
        "Semi-Permanent": {"PY": 20.0, "AC": 28.0},
    }
    for panel, values in panel_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Type": panel,
                    "Value_LC": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }

    table = core.small_multiples_table(
        canonical,
        recipe,
        {"dimension": "Type"},
    )

    assert table["Type"].to_list() == [
        "Permanent",
        "Male",
        "Root",
        "Semi-Permanent",
    ]


def test_legacy_slope_small_multiples_use_indexed_shared_y_ranges(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    panel_values = {
        "Permanent": {"PY": 400.0, "AC": 600.0},
        "Male": {"PY": 120.0, "AC": 100.0},
        "Root": {"PY": 40.0, "AC": 80.0},
        "Semi-Permanent": {"PY": 20.0, "AC": 28.0},
    }
    for panel, values in panel_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Type": panel,
                    "Value_LC": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Value_LC",
            "dimensions": ["Type"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "Hair Color",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_slope_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_slope_small_multiples.png",
        small_multiples_dimension="Type",
        repeat_values=["Permanent", "Male", "Root", "Semi-Permanent"],
    )

    layout = captured["fig"].layout.to_plotly_json()
    slope_traces = [
        trace
        for trace in captured["fig"].data
        if getattr(trace, "mode", "") == "lines+markers"
    ]
    traces_by_xaxis = {
        str(getattr(trace, "xaxis", None) or "x"): tuple(getattr(trace, "y", ()) or ())
        for trace in slope_traces
    }

    assert layout["yaxis"].get("matches") is None
    assert layout["yaxis2"].get("matches") == "y"
    assert layout["yaxis3"].get("matches") == "y"
    assert layout["yaxis4"].get("matches") == "y"
    assert layout["yaxis"]["range"] == layout["yaxis2"]["range"]
    assert layout["yaxis"]["range"][0] < 83.4
    assert layout["yaxis"]["range"][1] > 200
    assert traces_by_xaxis["x"] == pytest.approx((100.0, 150.0))
    assert traces_by_xaxis["x2"] == pytest.approx((100.0, 83.3333333333))
    assert traces_by_xaxis["x3"] == pytest.approx((100.0, 200.0))
    assert any(
        "Index: PY=100" in str(getattr(annotation, "text", ""))
        for annotation in captured["fig"].layout.annotations or []
    )


def test_legacy_line_chart_uses_month_labels_on_x_axis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_actual_vs_previous_year_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_line.png",
        by_period=False,
    )

    xaxis = captured["fig"].layout.xaxis
    assert tuple(xaxis.tickvals) == (0, 1, 2, 3)
    assert tuple(xaxis.ticktext) == ("Jan", "Feb", "Mar", "Apr")
    assert xaxis.zeroline is False
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_line_chart_keeps_month_end_current_and_previous_values_separate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    current_values = [198.0, 215.0, 231.0, 248.0, 270.0, 345.0]
    previous_values = [180.0, 195.0, 210.0, 225.0, 240.0, 255.0]
    month_ends = [31, 28, 31, 30, 31, 30]
    rows = [
        {
            "Date": f"{year}-{month:02d}-{month_ends[month - 1]:02d}",
            "Period": period,
            "Sales": value,
        }
        for year, period, values in (
            (2025, "PY", previous_values),
            (2026, "AC", current_values),
        )
        for month, value in enumerate(values, start=1)
    ]
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Sales",
            "dimensions": [],
        },
        "options": {
            "currency": "EUR",
            "period_window": {
                "current": {
                    "year": 2026,
                    "month_cutoff": 6,
                    "start_date": "2026-01-01",
                    "end_date": "2026-06-30",
                },
                "previous": {
                    "year": 2025,
                    "month_cutoff": 6,
                    "start_date": "2025-01-01",
                    "end_date": "2025-06-30",
                },
            },
        },
    }
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_actual_vs_previous_year_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_line.png",
        by_period=False,
    )

    ac_trace = next(trace for trace in captured["fig"].data if trace.name == "AC")
    py_trace = next(trace for trace in captured["fig"].data if trace.name == "PY")
    assert _plotly_numeric_trace_values(ac_trace.y) == pytest.approx(
        tuple(current_values)
    )
    assert _plotly_numeric_trace_values(py_trace.y) == pytest.approx(
        tuple(previous_values)
    )


def test_legacy_by_period_chart_uses_window_labels_on_x_axis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_actual_vs_previous_year_chart(
        canonical,
        recipe,
        tmp_path,
        artifact_name="year_over_year_by_period.png",
        by_period=True,
    )

    xaxis = captured["fig"].layout.xaxis
    assert tuple(xaxis.tickvals) == (0, 1, 2, 3)
    assert tuple(xaxis.ticktext) == ("52w", "26w", "13w", "4w")
    assert xaxis.zeroline is False
    title_text = "\n".join(
        str(annotation.text) for annotation in captured["fig"].layout.annotations or []
    )
    assert "Weekly Average Sales by Recency Window" in title_text
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_waterfall_chart_uses_period_and_month_labels_on_x_axis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_horizontal_waterfall_chart(canonical, recipe, tmp_path)

    expected_labels = ("PY", "Jan", "Feb", "Mar", "Apr", "AC")
    xaxis = captured["fig"].layout.xaxis
    assert tuple(xaxis.categoryarray) == expected_labels
    assert tuple(xaxis.ticktext) == expected_labels
    for trace in captured["fig"].data:
        x_values = tuple(getattr(trace, "x", ()) or ())
        if x_values:
            assert x_values == expected_labels
            assert "period zero" not in x_values
            assert "period one" not in x_values
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_legacy_slope_export_size_uses_narrower_canvas() -> None:
    legacy = load_legacy_charting()
    single_panel = go.Figure()
    single_panel.update_layout(width=500, height=400)
    small_multiples = make_subplots(rows=1, cols=4)

    assert legacy._legacy_export_size(single_panel) == (1400, 900)
    assert legacy._legacy_export_size(single_panel, "year_over_year_slope.png") == (
        760,
        620,
    )
    assert legacy._legacy_export_size(
        small_multiples, "year_over_year_slope_small_multiples.png"
    ) == (1360, 560)


def test_legacy_slope_and_dot_charts_use_legacy_timeline_renderers(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    canonical, recipe = _legacy_metric_fixture()
    captured = _capture_legacy_figure(legacy, monkeypatch)

    slope_export = legacy.write_legacy_slope_chart(canonical, recipe, tmp_path)
    slope_fig = captured["fig"]
    dot_export = legacy.write_legacy_dot_chart(canonical, recipe, tmp_path)
    dot_fig = captured["fig"]

    assert slope_export.audit["status"] == "written"
    assert dot_export.audit["status"] == "written"
    assert slope_export.audit["dimension"] == "Productline"
    assert dot_export.audit["dimension"] == "Productline"
    assert (
        "modules.charting.plot_charts.plot_slope_charts"
        in slope_export.audit["source_functions"]
    )
    assert (
        "modules.charting.draw_timeline.draw_slope_chart"
        in slope_export.audit["source_functions"]
    )
    assert (
        "modules.charting.plot_charts.plot_dot_chart"
        in dot_export.audit["source_functions"]
    )
    assert (
        "modules.charting.draw_timeline.draw_dot_chart"
        in dot_export.audit["source_functions"]
    )
    assert slope_fig.data
    assert dot_fig.data
    assert not any(
        name == "matplotlib" or name.startswith("matplotlib.") for name in sys.modules
    )


def test_dot_chart_uses_primary_dimension_not_small_multiple_dimension(
    tmp_path: Path, monkeypatch: Any
) -> None:
    core = load_core()
    canonical, recipe = _legacy_metric_fixture()
    recipe = copy.deepcopy(recipe)
    recipe["mappings"]["dimensions"] = ["Productline", "Region"]
    recipe["options"]["small_multiples_dimension"] = "Region"
    captured: dict[str, object] = {}

    def fake_write_legacy_dot_chart(
        _canonical: pl.DataFrame,
        _recipe: dict[str, Any],
        _output_dir: Path,
        *,
        artifact_name: str,
        dimension: str | None = None,
        repeat_values: list[str] | None = None,
        render: bool = True,
    ) -> SimpleNamespace:
        del artifact_name, repeat_values, render
        captured["dimension"] = dimension
        return SimpleNamespace(
            paths=[str(tmp_path / "year_over_year_dot.html")],
            audit={"status": "written", "dimension": dimension},
        )

    monkeypatch.setattr(core, "write_legacy_dot_chart", fake_write_legacy_dot_chart)

    _paths, audit = core.write_dot_chart(pl.DataFrame(), canonical, recipe, tmp_path)

    assert captured["dimension"] == "Productline"
    assert audit["dimension"] == "Productline"


def test_legacy_dot_chart_places_largest_item_on_top(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    rows: list[dict[str, object]] = []
    period_values = {
        "Road": {"PY": 200.0, "AC": 220.0},
        "Mountain": {"PY": 80.0, "AC": 90.0},
        "Accessories": {"PY": 25.0, "AC": 30.0},
    }
    for productline, values in period_values.items():
        for period, value in values.items():
            year = 2025 if period == "AC" else 2024
            rows.append(
                {
                    "Date": f"{year}-04-28",
                    "Period": period,
                    "Productline": productline,
                    "Salesamount": value,
                }
            )
    canonical = pl.DataFrame(rows).with_columns(pl.col("Date").str.to_date())
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Salesamount",
            "dimensions": ["Productline"],
        },
        "options": {
            "currency": "EUR",
            "reporting_entity": "AdventureWorks",
            "period_window": {
                "current": {"year": 2025, "month_cutoff": 4},
                "previous": {"year": 2024, "month_cutoff": 4},
            },
        },
    }
    captured = _capture_legacy_figure(legacy, monkeypatch)

    legacy.write_legacy_dot_chart(canonical, recipe, tmp_path)

    yaxis = captured["fig"].layout.yaxis
    assert tuple(yaxis.categoryarray) == ("Accessories", "Mountain", "Road")


def test_period_comparison_rejects_input_without_previous_year(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    pl.DataFrame(
        {
            "Orderdate": ["2025-01-31", "2025-02-28"],
            "Salesamount": [100.0, 120.0],
        }
    ).write_csv(input_path)

    try:
        core.run_period_comparison(input_path, tmp_path / "out", language="en")
    except ValueError as exc:
        assert "No rows found for previous year" in str(exc)
    else:
        raise AssertionError("Expected missing previous year to raise ValueError")


def test_period_comparison_accepts_derived_cohort_dimension(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "out"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "Orderdate": [
                "2024-01-31",
                "2025-01-31",
                "2025-02-28",
                "2024-02-28",
                "2024-03-31",
                "2025-03-31",
            ],
            "Brand": [
                "Established",
                "Established",
                "New",
                "Lost",
                "Zero PY",
                "Zero PY",
            ],
            "Salesamount": [10.0, 12.0, 5.0, 7.0, 0.0, 3.0],
        }
    ).write_csv(input_path)
    recipe = {
        "schema_version": "1.0",
        "source_file": str(input_path),
        "language": "en",
        "mappings": {
            "date_column": "Orderdate",
            "amount_column": "Salesamount",
            "dimensions": ["Brand_Since"],
        },
        "options": {
            "currency": "EUR",
            "charts": [],
            "small_multiples": False,
            "derived_dimensions": [
                {
                    "source_dimension": "Brand",
                    "name": "Brand_Since",
                    "kind": "since",
                }
            ],
        },
    }
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    result = core.run_period_comparison(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    canonical = pl.read_csv(output_dir / "period_comparison_canonical.csv")
    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    labels = set(canonical.select("Brand_Since").unique().to_series().to_list())
    assert labels == {"Since PY", "Since AC"}
    assert used_recipe["mappings"]["dimensions"] == ["Brand_Since"]
    derivation_audit = used_recipe["options"]["period_derivation_audit"]
    assert (
        derivation_audit["cohort_columns"]["derived_dimensions"][0]["output_column"]
        == "Brand_Since"
    )
    assert result.audit["checks"]["canonical_row_count"] == 6


def test_period_comparison_cleans_up_vendored_module_imports(tmp_path: Path) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    _write_period_fixture(input_path)

    core.run_period_comparison(input_path, tmp_path / "out", language="en")

    vendor_root = PLUGIN_ROOT / "vendor"
    shared_root = ROOT / "plugins" / "_shared" / "vendor"
    assert str(vendor_root) not in sys.path
    assert str(shared_root) not in sys.path
    vendored_modules = [
        name
        for name, module in sys.modules.items()
        if (name == "modules" or name.startswith("modules."))
        and getattr(module, "__file__", "")
        and (
            Path(getattr(module, "__file__"))
            .resolve()
            .is_relative_to(vendor_root.resolve())
            or Path(getattr(module, "__file__"))
            .resolve()
            .is_relative_to(shared_root.resolve())
        )
    ]
    assert vendored_modules == []


def test_period_comparison_dependency_checker_collects_import_warnings(
    monkeypatch: Any,
) -> None:
    checker = load_dependency_checker()

    def fake_import_module(_module_name: str) -> object:
        import warnings

        warnings.warn("dependency pins are inconsistent", RuntimeWarning, stacklevel=2)
        return object()

    monkeypatch.setattr(checker.importlib, "import_module", fake_import_module)

    assert checker.collect_import_warnings("plotly") == [
        "RuntimeWarning: dependency pins are inconsistent"
    ]
