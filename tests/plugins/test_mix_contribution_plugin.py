from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "mix-contribution-analysis"
SCRIPT_DIR = PLUGIN_ROOT / "scripts"
CORE_PATH = SCRIPT_DIR / "mix_core.py"
DEPENDENCY_CHECKER_PATH = SCRIPT_DIR / "check_dependencies.py"
LEGACY_CHARTING_PATH = SCRIPT_DIR / "legacy_mix_charting.py"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"
VENDOR_CHART_HELPERS_PATH = ROOT.joinpath(
    "plugins", "_shared", "vendor", "modules", "charting", "chart_helpers.py"
)


def load_core() -> Any:
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("mix_core", CORE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_dependency_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "mix_check_dependencies", DEPENDENCY_CHECKER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_legacy_charting() -> Any:
    spec = importlib.util.spec_from_file_location(
        "mix_legacy_charting_test", LEGACY_CHARTING_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_vendor_chart_helpers() -> Any:
    spec = importlib.util.spec_from_file_location(
        "mix_vendor_chart_helpers_test", VENDOR_CHART_HELPERS_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the Mix Contribution MCP server.")
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_mix_fixture(path: Path) -> None:
    rows = [
        {
            "Scenario": scenario,
            "Orderdate": f"2025-0{month}-28",
            "Productline": productline,
            "Category": category,
            "Region": region,
            "Salesamount": value,
            "Units": int(10 * multiplier * month),
        }
        for scenario, multiplier in (("AC", 1.0), ("PY", 0.8))
        for month in (1, 2, 3)
        for productline, category, region, value in (
            ("Bikes", "Road", "Australia", 100.0 * multiplier * month),
            ("Bikes", "Mountain", "United States", 80.0 * multiplier * month),
            ("Accessories", "Helmets", "Australia", 35.0 * multiplier * month),
        )
    ]
    pl.DataFrame(rows).write_csv(path)


def _write_png(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(path, format="PNG")


def test_legacy_mix_context_captures_generated_three_row_title() -> None:
    legacy_charting = load_legacy_charting()

    class FakeMargin:
        def __init__(self) -> None:
            self.payload = {"t": 10}

        def to_plotly_json(self) -> dict[str, int]:
            return dict(self.payload)

    class FakeFigure:
        def __init__(self) -> None:
            self.layout = SimpleNamespace(
                title=SimpleNamespace(text=""),
                margin=FakeMargin(),
                annotations=[],
                width=1200,
                height=700,
            )
            self.data: list[Any] = []

        def update_layout(self, **kwargs: Any) -> None:
            if "title" in kwargs:
                self.layout.title.text = kwargs["title"]["text"]
            if "margin" in kwargs:
                self.layout.margin.payload = kwargs["margin"]

    figure = FakeFigure()
    spec = {
        "name": "stacked_bar",
        "capture_chart_data": True,
        "reporting_entity_label": "Mexico hair color",
        "metrics": ["Sales"],
        "metric": "Sales",
        "dimensions": ["Company", "Channel"],
        "selected_periods": ["AC"],
    }

    legacy_charting._apply_reporting_title_structure(
        [figure],
        spec,
        {"status": "skipped"},
    )
    context = legacy_charting._capture_context_payload(
        spec=spec,
        chart={},
        calls=[{"legacy_chart": "stacked bar"}],
        figures=[figure],
        exports=[],
        source_functions=[],
    )

    assert context["chart_title_lines"] == [
        "Mexico hair color",
        "Sales in mEUR by Company and Channel",
        "AC",
    ]
    assert context["title_contract"] == {
        "who": "Mexico hair color",
        "what": "Sales in mEUR by Company and Channel",
        "when": "AC",
    }


def _fake_legacy_writer(
    _canonical: Any,
    _recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    **_kwargs: Any,
) -> Any:
    path = output_dir / str(spec["artifact_name"])
    render = bool(_kwargs.get("render", True))
    if render:
        _write_png(path)
    chart_context = None
    if spec["name"] == "stacked_column_synthesis":
        chart_context = {
            "schema_version": "1.0",
            "chart": "stacked_column_synthesis",
            "legacy_chart": "stacked column",
            "chart_data_source": (
                "legacy set_up_tab_for_show_or_download_chart input dataframe"
            ),
            "source_functions": [
                "modules.charting.run_charting.run_charting",
                "modules.charting.plot_charts.plot_stacked_column_charts",
                "modules.data.multidimensional_charts_prep.prepare_data_for_syn_plot",
            ],
            "data_frame": {
                "columns": ["Dimension", "Bikes", "Accessories"],
                "row_count": 1,
                "rows": [
                    {
                        "Dimension": "Productline",
                        "Bikes": 100.0,
                        "Accessories": 35.0,
                    }
                ],
            },
        }
    elif spec.get("capture_chart_data"):
        chart_context = {
            "schema_version": "1.0",
            "chart": spec["name"],
            "legacy_chart": spec["legacy_chart_key"],
            "chart_data_source": (
                "legacy set_up_tab_for_show_or_download_chart input dataframe"
            ),
            "dimensions": spec.get("dimensions") or [],
            "x_dimension": spec.get("x_dimension"),
            "y_dimension": spec.get("y_dimension"),
            "metric": spec.get("metric"),
            "selected_periods": spec.get("selected_periods") or [],
            "data_frame": {
                "columns": ["Dimension", "Value"],
                "row_count": 1,
                "rows": [{"Dimension": spec["name"], "Value": 1.0}],
            },
        }
    return SimpleNamespace(
        paths=[str(path)] if render else [],
        audit={
            "status": "written" if render else "data_written",
            "chart": spec["name"],
            "rendered": render,
            "dimensions": spec.get("dimensions") or [],
            "x_dimension": spec.get("x_dimension"),
            "y_dimension": spec.get("y_dimension"),
            "small_multiples_dimension": spec.get("small_multiples_dimension"),
            "selected_periods": spec.get("selected_periods") or [],
            "dimension_selection": spec.get("dimension_selection"),
            "focus_item": spec.get("focus_item"),
            "focus_dimension": spec.get("focus_dimension"),
            "focus_status": spec.get("focus_status"),
            "focus_reason": spec.get("focus_reason"),
            "source_functions": [
                "modules.charting.run_charting.run_charting",
                f"modules.charting.plot_charts.{spec['plotter']}",
            ],
        },
        chart_context=chart_context,
    )


def test_legacy_small_multiple_panels_are_ranked_with_other_last() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.data.common_data_utils import show_only_largest
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "marimekkoChart",
            "x_dimension": "Product",
            "y_dimension": "Region",
            "small_multiples_dimension": "Region",
            "small_multiples_panel_axis": "Y",
            "small_multiples_max_panels": 4,
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC", "AC", "AC"],
            "Product": ["A", "A", "A", "A", "A"],
            "Region": ["Small", "Largest", "Medium", "Second", "Tie"],
            "Sales": [10.0, 100.0, 50.0, 75.0, 50.0],
        }
    )

    _filtered, panel_items, _other_name, _value_cols = show_only_largest(
        frame,
        "Region",
        "Product",
        "Period",
        ["Sales"],
        chart,
        {},
        "Y",
    )

    assert panel_items == ["Largest", "Second", "Medium", "Others rank >3"]


def test_legacy_show_only_largest_non_aggregated_keeps_top_n_items() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.data.common_data_utils import show_only_largest
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC"] * 6,
            "Brand": [
                "Koleston",
                "Koleston",
                "Nutrisse",
                "Nutrisse",
                "Excellence",
                "Excellence",
                "Casting",
                "Casting",
                "Preference",
                "Preference",
                "Colorsilk",
                "Colorsilk",
            ],
            "Sales": [
                40.0,
                100.0,
                30.0,
                80.0,
                20.0,
                60.0,
                10.0,
                50.0,
                5.0,
                40.0,
                3.0,
                30.0,
            ],
        }
    )
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Brand"],
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
            "max_items": 4,
            "aggregate_other_items": False,
        },
        metric="Sales",
        currency="EUR",
    )

    filtered, unique_items, _other_name, _value_cols = show_only_largest(
        frame.lazy(),
        "Brand",
        None,
        "Period",
        ["Sales"],
        chart,
        {},
        "X",
    )

    assert unique_items == ["Koleston", "Nutrisse", "Excellence", "Casting"]
    assert filtered.collect()["Brand"].to_list() == [
        "Koleston",
        "Koleston",
        "Nutrisse",
        "Nutrisse",
        "Excellence",
        "Excellence",
        "Casting",
        "Casting",
    ]


def test_legacy_mekko_subplot_titles_are_spread_across_panel_domains() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_width_and_stacked_plots import _center_subplot_titles

    fig = make_subplots(rows=1, cols=2, subplot_titles=["M", "F"])
    for annotation in fig.layout.annotations:
        annotation.x = 0.22
        annotation.xref = "paper"

    _center_subplot_titles(fig, ["M", "F"])
    title_positions = [
        round(float(annotation.x), 2) for annotation in fig.layout.annotations
    ]

    assert title_positions == [0.23, 0.78]


def test_legacy_mekko_subplot_titles_repeat_by_row() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_width_and_stacked_plots import _center_subplot_titles

    fig = make_subplots(rows=2, cols=2, subplot_titles=["A", "B", "C", "D"])
    for annotation in fig.layout.annotations:
        annotation.x = 0.22
        annotation.xref = "paper"

    _center_subplot_titles(fig, ["A", "B", "C", "D"])
    title_positions = [
        round(float(annotation.x), 2) for annotation in fig.layout.annotations
    ]

    assert title_positions == [0.23, 0.78, 0.23, 0.78]


def test_legacy_mekko_subplot_titles_align_lower_row_to_panel_top() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_width_and_stacked_plots import _center_subplot_titles

    lower_row_top = 0.47
    title_gap = 0.008
    expected_lower_title_y = lower_row_top + title_gap
    fig = make_subplots(
        rows=2,
        cols=2,
        vertical_spacing=0.06,
        horizontal_spacing=0.12,
        subplot_titles=["Permanent", "Male", "Root", "Semi-Permanent"],
    )
    for annotation in fig.layout.annotations:
        annotation.x = 0.22
        annotation.y = min(float(annotation.y) + 0.04, 1.0)
        annotation.xref = "paper"
        annotation.yref = "paper"

    _center_subplot_titles(fig, ["Permanent", "Male", "Root", "Semi-Permanent"])
    title_positions = [
        (round(float(annotation.x), 3), round(float(annotation.y), 3))
        for annotation in fig.layout.annotations
    ]

    assert title_positions == [
        (0.22, 1.0),
        (0.78, 1.0),
        (0.22, expected_lower_title_y),
        (0.78, expected_lower_title_y),
    ]


def test_legacy_mekko_small_multiples_use_local_axis_scale() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_width_and_stacked_plots import (
        _update_small_multiple_mekko_axes,
    )

    fig = make_subplots(rows=1, cols=2)

    _update_small_multiple_mekko_axes(fig, "marimekko", "barmekko", 100.0)

    assert fig.layout.xaxis.autorange is True
    assert fig.layout.xaxis.range is None
    assert fig.layout.xaxis2.autorange is True
    assert fig.layout.xaxis2.range is None
    assert fig.layout.xaxis.matches is None
    assert fig.layout.xaxis2.matches is None
    assert fig.layout.yaxis.autorange is True
    assert fig.layout.yaxis.range is None
    assert fig.layout.yaxis2.autorange is True
    assert fig.layout.yaxis2.range is None
    assert fig.layout.yaxis.matches is None
    assert fig.layout.yaxis2.matches is None


def test_legacy_barmekko_small_multiples_use_panel_total_header() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_first_row_annotations_for_barmekko,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["barmekkoChart"],
        names["xAxisMetric"]: names["unitsName"],
        names["yAxisMetric"]: names["pricePerUnitName"],
        names["multipliedMetric"]: "Sales",
        names["plotSmallMultiplesOtherCharts"]: True,
    }

    add_first_row_annotations_for_barmekko(
        pl.DataFrame(),
        fig,
        totalYaxisNumber=40.0,
        totalXaxisNumber=50.0,
        totalAreaNumber=2.2,
        chartDict=chart,
        row=1,
        col=1,
    )

    annotations = list(fig.layout.annotations or [])
    assert [annotation.text for annotation in annotations] == ["Total<br><b>2.2</b>"]
    annotation = annotations[0]
    assert annotation.xref == "x domain"
    assert annotation.yref == "y domain"
    assert annotation.x == 1
    assert annotation.ax == 1
    assert annotation.y == 1
    assert annotation.xanchor == "left"
    assert annotation.xshift == 6


def test_legacy_stacked_bar_small_multiple_rows_use_local_sort() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    assert legacy_charting._uses_local_stacked_bar_small_multiple_row_order(
        {"name": "related_metrics_bar_small_multiples"}
    )
    assert legacy_charting._uses_local_stacked_bar_small_multiple_row_order(
        {"name": "bar_small_multiples"}
    )
    chart = {names["xAxisDimension"]: "Company"}
    frame = pl.DataFrame(
        {
            "Company": ["Large", "Small", "Padded", "Beta", "Alpha"],
            "Mexico City": [4.0, 1.0, None, 2.0, 2.0],
            "Monterrey": [1.0, 0.5, None, 0.5, 0.5],
            names["valueName"]: [5.0, 1.5, None, 2.5, 2.5],
        }
    )

    ordered = legacy_charting._locally_order_stacked_bar_small_multiple_rows(
        frame.lazy(),
        chart,
        names,
    ).collect()

    assert ordered.get_column("Company").to_list() == [
        "Small",
        "Alpha",
        "Beta",
        "Large",
    ]


def test_legacy_stacked_bar_small_multiple_rows_pin_other_bucket_bottom() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {names["xAxisDimension"]: "Company"}
    frame = pl.DataFrame(
        {
            "Company": ["Small", "Others rank >2", "Large"],
            "Mexico City": [1.0, 3.0, 5.0],
            names["valueName"]: [1.0, 3.0, 5.0],
        }
    )

    ordered = legacy_charting._locally_order_stacked_bar_small_multiple_rows(
        frame.lazy(),
        chart,
        names,
    ).collect()

    assert ordered.get_column("Company").to_list() == [
        "Others rank >2",
        "Small",
        "Large",
    ]


def test_legacy_stacked_bar_small_multiples_keep_readable_canvas() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    first_panel_labels = [f"Company {index}" for index in range(12)]
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=["Permanent", "Male", "Root", "Semi-Permanent"],
    )
    fig.add_trace(
        go.Bar(
            x=list(range(12)),
            y=first_panel_labels,
            orientation="h",
            width=0.9,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(x=[1, 2], y=["Coty", "L'Oreal"], orientation="h", width=0.9),
        row=2,
        col=1,
    )
    fig.update_layout(width=1576, height=439)

    legacy_charting._apply_stacked_bar_small_multiple_readable_canvas(
        [fig],
        {"name": "stacked_bar_small_multiples"},
    )

    assert fig.layout.width == 2220
    assert fig.layout.height == 1300
    assert fig.data[0].width == 0.9
    assert fig.data[1].width == 0.9
    assert fig.data[2].name == "__mix_axis_spacer__"
    assert fig.data[2].y == tuple(" " * (index + 1) for index in range(10))
    assert fig.layout.yaxis3.matches is None
    assert len(fig.layout.yaxis3.categoryarray) == 12
    assert fig.layout.yaxis3.tickvals == ("Coty", "L'Oreal")


def test_legacy_stacked_bar_small_multiples_use_fixed_minimum_row_slots() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=["Permanent", "Male", "Root", "Semi-Permanent"],
    )
    fig.add_trace(
        go.Bar(x=[1, 2], y=["Coty", "L'Oreal"], orientation="h", width=0.9),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(x=[1], y=["Combe"], orientation="h", width=0.9),
        row=2,
        col=1,
    )
    fig.update_layout(width=1576, height=439)

    legacy_charting._apply_stacked_bar_small_multiple_readable_canvas(
        [fig],
        {"name": "stacked_bar_small_multiples"},
    )

    assert fig.layout.height == 1300
    assert len(fig.layout.yaxis.categoryarray) == 12
    assert len(fig.layout.yaxis3.categoryarray) == 12
    assert fig.layout.yaxis.tickvals == ("Coty", "L'Oreal")
    assert fig.layout.yaxis3.tickvals == ("Combe",)


def test_legacy_marimekko_small_multiples_use_panel_right_total_header() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_first_row_annotations_for_marimekko_and_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["singleMetric"]: "Sales",
        names["plotSmallMultiplesOtherCharts"]: True,
    }

    add_first_row_annotations_for_marimekko_and_stacked_bar(
        fig,
        totalYaxisNumber=2031,
        chartDict=chart,
        row=1,
        col=1,
    )

    annotation = list(fig.layout.annotations or [])[0]
    assert annotation.text == "Total<br><b>2031</b>"
    assert annotation.xref == "x domain"
    assert annotation.yref == "y domain"
    assert annotation.x == 1
    assert annotation.ax == 1
    assert annotation.xanchor == "left"
    assert annotation.align == "left"
    assert annotation.xshift == 6


def test_legacy_stacked_bar_small_multiples_lift_panel_total_header() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_first_row_annotations_for_marimekko_and_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["stackedBarChart"],
        names["metricsToPlot"]: ["Sales"],
        names["plotSmallMultiplesOtherCharts"]: True,
    }

    add_first_row_annotations_for_marimekko_and_stacked_bar(
        fig,
        totalYaxisNumber=547,
        chartDict=chart,
        row=1,
        col=1,
    )

    annotation = list(fig.layout.annotations or [])[0]
    assert annotation.text == "Total<br><b>547</b>"
    assert annotation.xref == "x domain"
    assert annotation.yref == "y domain"
    assert annotation.x == 1
    assert annotation.ax == 1
    assert annotation.y == 1
    assert annotation.yshift == 20


def test_legacy_barmekko_small_multiples_order_by_area_total() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_width_and_stacked_plots import (
        _small_multiple_total_metric_column,
    )
    from modules.charting.small_multiples_ordering import (
        order_small_multiple_facets_by_total,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Type": ["Large", "Small", "Other rank >2"],
            "Unit Price": [1.0, 100.0, 999.0],
            "Units": [100.0, 1.0, 50.0],
            "Sales": [100.0, 1.0, 50.0],
        }
    )
    chart = {names["multipliedMetric"]: "Sales"}

    metric = _small_multiple_total_metric_column(
        frame.lazy(), ["Unit Price", "Units", "Sales"], chart
    )
    ordered = order_small_multiple_facets_by_total(
        frame.lazy(),
        "Type",
        metric,
        ["Small", "Other rank >2", "Large"],
        "Other rank",
    )

    assert metric == "Sales"
    assert ordered == ["Large", "Small", "Other rank >2"]


def test_legacy_barmekko_rows_are_sorted_by_area_metric() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import prepare_data_for_barmekko
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    canonical = pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC"],
            "Company": ["High price tiny", "Large area", "Middle area"],
            "Channel": ["Retail", "Retail", "Retail"],
            "Sales": [10.0, 100.0, 50.0],
            "Units": [1.0, 100.0, 10.0],
            "Unit Price": [10.0, 1.0, 5.0],
            "Units x Unit Price": [10.0, 100.0, 50.0],
        }
    )
    barmekko_spec = {
        "name": "barmekko",
        "legacy_chart_key": "barmekkoChart",
        "dimensions": ["Company", "Channel"],
        "x_dimension": "Company",
        "y_dimension": "Channel",
        "x_metric": "Units",
        "y_metric": "Unit Price",
        "multiplied_metric": "Units x Unit Price",
        "metrics": ["Unit Price", "Units"],
        "value_cols": ["Sales", "Units", "Units x Unit Price"],
        "selected_periods": ["AC"],
        "max_items": 12,
    }

    chart = legacy_charting._legacy_chart_dict(
        names,
        barmekko_spec,
        metric="Sales",
        currency="EUR",
    )
    param_dict = {
        names["monetaryLocalCurrencyColFound"]: True,
        names["unitsColFound"]: True,
        names["volumeColFound"]: False,
        names["discountColFound"]: False,
        names["marginColFound"]: False,
    }

    prepared, _metric, _chart, _colors, _items = prepare_data_for_barmekko(
        canonical.lazy(),
        barmekko_spec["value_cols"],
        chart,
        param_dict,
        [],
    )
    companies = prepared.collect()["Company"].to_list()

    assert companies == ["Large area", "Middle area", "High price tiny"]


def test_legacy_barmekko_area_sort_controls_render_order() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_width_and_stacked_plots import mekko_plot
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "name": "barmekko",
            "legacy_chart_key": "barmekkoChart",
            "dimensions": ["Company", "Channel"],
            "x_dimension": "Company",
            "y_dimension": "Channel",
            "x_metric": "Units",
            "y_metric": "Unit Price",
            "multiplied_metric": "Units x Unit Price",
            "metrics": ["Unit Price", "Units"],
            "value_cols": ["Sales", "Units", "Units x Unit Price"],
            "selected_periods": ["AC"],
            "max_items": 12,
        },
        metric="Sales",
        currency="EUR",
    )
    chart[names["pricePerUnitTotalName"]] = 160.0 / 111.0
    frame = pl.DataFrame(
        {
            "Company": ["High price tiny", "Large area", "Middle area"],
            "Unit Price": [10.0, 1.0, 5.0],
            "Units": [1.0, 100.0, 10.0],
        }
    )

    fig, _negative, _message, _chart = mekko_plot(
        frame,
        chart,
        {},
        unit_name=names["valueName"],
        colors=["#245f58"],
    )
    trace = fig.data[0]

    assert chart[names["sortAxis"]] == names["areaSort"]
    assert list(trace.x) == [10.0, 5.0, 1.0]
    assert list(trace.y) == [0.0, 1.0, 11.0]
    assert list(trace.width) == [1.0, 10.0, 100.0]


def test_legacy_mekko_small_multiples_pin_readable_shared_prefix() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_width_and_stacked_plots import (
        _pin_small_multiple_metric_prefixes,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Type": ["Permanent", "Male", "Semi-Permanent"],
            "Sales": [2_030_897_847.0, 121_483_266.0, 13_427_153.0],
        }
    )
    chart: dict[str, Any] = {
        names["xAxisMetric"]: "Units",
        names["yAxisMetric"]: "Unit Price",
        names["multipliedMetric"]: "Units x Unit Price",
    }

    _pin_small_multiple_metric_prefixes(frame.lazy(), "Type", ["Sales"], chart)

    assert chart[names["valuePrefixDict"]]["Sales"] == "m"
    assert chart[names["valuePrefixDict"]]["Units x Unit Price"] == "m"
    assert chart[names["valuePrefixDict"]][names["valueName"]] == "m"


def test_legacy_marimekko_small_multiples_pin_value_prefix_from_metric() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_width_and_stacked_plots import (
        _pin_small_multiple_metric_prefixes,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Type": ["Permanent", "Male", "Semi-Permanent"],
            "Sales": [2_030_897_847.0, 121_483_266.0, 13_427_153.0],
        }
    )
    chart: dict[str, Any] = {
        names["xAxisMetric"]: "Sales",
        names["yAxisMetric"]: "Sales",
        names["multipliedMetric"]: "Sales x Sales",
    }

    _pin_small_multiple_metric_prefixes(frame.lazy(), "Type", ["Sales"], chart)

    assert chart[names["valuePrefixDict"]]["Sales"] == "m"
    assert chart[names["valuePrefixDict"]][names["valueName"]] == "m"
    assert chart[names["valuePrefixDict"]]["Sales x Sales"] == "m"


def test_legacy_barmekko_panel_total_uses_pinned_area_prefix() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_first_row_annotations_for_barmekko,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["barmekkoChart"],
        names["xAxisMetric"]: names["unitsName"],
        names["yAxisMetric"]: names["pricePerUnitName"],
        names["multipliedMetric"]: "Sales",
        names["plotSmallMultiplesOtherCharts"]: True,
        names["valuePrefixDict"]: {"Sales": "m"},
    }

    add_first_row_annotations_for_barmekko(
        pl.DataFrame(),
        fig,
        totalYaxisNumber=40.0,
        totalXaxisNumber=50.0,
        totalAreaNumber=2_030_897_847.0,
        chartDict=chart,
        row=1,
        col=1,
    )

    annotations = list(fig.layout.annotations or [])
    assert [annotation.text for annotation in annotations] == ["Total<br><b>2031</b>"]


def test_legacy_barmekko_panel_total_reconciles_synthetic_area_prefix() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_first_row_annotations_for_barmekko,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["barmekkoChart"],
        names["xAxisMetric"]: "Units",
        names["yAxisMetric"]: "Unit Price",
        names["multipliedMetric"]: "Units x Unit Price",
        names["plotSmallMultiplesOtherCharts"]: True,
        names["valuePrefixDict"]: {
            "Units": "m",
            "Unit Price": "",
            "Sales": "m",
            "Units x Unit Price": "b",
        },
    }

    add_first_row_annotations_for_barmekko(
        pl.DataFrame(),
        fig,
        totalYaxisNumber=40.0,
        totalXaxisNumber=50.0,
        totalAreaNumber=2_030_897_847.0,
        chartDict=chart,
        row=1,
        col=1,
    )

    annotations = list(fig.layout.annotations or [])
    assert [annotation.text for annotation in annotations] == ["Total<br><b>2031</b>"]


def test_legacy_barmekko_small_multiples_skip_tiny_row_annotations() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_total_annotations_for_barmekko
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["barmekkoChart"],
        names["xAxisMetric"]: names["unitsName"],
        names["yAxisMetric"]: names["pricePerUnitName"],
        names["multipliedMetric"]: "Sales",
        names["plotSmallMultiplesOtherCharts"]: True,
    }
    frame = pl.DataFrame(
        {
            "Company": ["Tiny", "Large"],
            names["unitsName"]: [1.0, 99.0],
            names["pricePerUnitName"]: [10.0, 10.0],
        }
    )
    half_column = pl.DataFrame(
        {"Company": ["Tiny", "Large"], "halfColumn": [0.5, 50.5]}
    ).lazy()
    width = frame.select(["Company", names["unitsName"]]).lazy()

    add_total_annotations_for_barmekko(
        fig,
        frame.lazy(),
        "Tiny",
        half_column,
        width,
        chart,
        row=1,
        col=1,
    )

    assert list(fig.layout.annotations or []) == []


def test_legacy_marimekko_small_multiples_skip_tiny_row_annotations() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_total_annotations_for_marimekko
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    fig = make_subplots(rows=1, cols=1)
    chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["valuePrefixName"]: "",
        names["plotSmallMultiplesOtherCharts"]: True,
    }
    width = pl.DataFrame(
        {
            "Company": ["Tiny", "Large"],
            names["valueName"]: [1.0, 99.0],
        }
    ).lazy()
    half_column = pl.DataFrame(
        {"Company": ["Tiny", "Large"], "halfColumn": [0.5, 50.5]}
    ).lazy()

    add_total_annotations_for_marimekko(
        fig,
        category="Tiny",
        halfColumn_lazy=half_column,
        width_lazy=width,
        chartDict=chart,
        row=1,
        col=1,
        category_col="Company",
        width_col=names["valueName"],
    )

    assert list(fig.layout.annotations or []) == []


def test_legacy_area_labels_use_date_axis_values_when_available() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_labels_to_area_chart

    first_date = date(2019, 1, 31)
    frame = pl.DataFrame(
        {
            "Date": [first_date],
            "Road": [10.0],
            "Road__label": ["10.0"],
            "Road__yShift": [0],
            "Road__xShift": [0],
        }
    )
    fig = make_subplots(rows=1, cols=1)

    add_labels_to_area_chart(
        fig,
        frame,
        frame,
        "Road__label",
        ["Road"],
        ["Road__label"],
        ["Road__yShift"],
        ["Road__xShift"],
        0,
        1,
        1,
    )

    assert fig.layout.annotations[0].x == first_date


def test_legacy_area_value_labels_use_plotted_stack_order_for_y_position() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_labels_to_area_chart

    first_date = date(2019, 1, 31)
    frame = pl.DataFrame(
        {
            "Date": [first_date],
            "Small": [10.0],
            "Large": [100.0],
            "Small__label": ["10.0"],
            "Small__yShift": [0],
            "Small__xShift": [0],
        }
    )
    stale_cumsum = pl.DataFrame({"Large": [999.0]})
    fig = make_subplots(rows=1, cols=1)

    add_labels_to_area_chart(
        fig,
        frame,
        stale_cumsum,
        "Small__label",
        ["Large", "Small"],
        ["Large__label", "Small__label"],
        ["Large__yShift", "Small__yShift"],
        ["Large__xShift", "Small__xShift"],
        1,
        1,
        1,
    )

    assert fig.layout.annotations[0].x == first_date
    assert fig.layout.annotations[0].y == 105.0


def test_legacy_area_value_labels_mark_peak_and_right_edge() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_charts_utils import prepare_value_labels_for_timeline
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    first_date = date(2019, 1, 31)
    middle_date = date(2019, 2, 28)
    last_date = date(2019, 3, 31)
    frame = pl.DataFrame(
        {
            "Date": [first_date, middle_date, last_date],
            "Road": [10.0, 20.0, 15.0],
        }
    )

    labelled = prepare_value_labels_for_timeline(
        frame,
        names["areaChart"],
        "Road",
        ["Road__label"],
        ["Road__yShift"],
        ["Road__xShift"],
        {names["plotValuesAsChoice"]: names["absolute"]},
        0,
    )

    assert labelled["Road__label"].to_list() == ["", "20.0", "15.0"]


def test_legacy_area_legends_use_date_axis_values_when_available() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_cumulated_legends

    last_date = date(2019, 6, 30)
    frame = pl.DataFrame(
        {
            "Date": [date(2019, 5, 31), last_date],
            "Road": [10.0, 12.0],
        }
    )
    fig = make_subplots(rows=1, cols=1)

    add_cumulated_legends(fig, frame, frame, 1, ["Road"], ["Road"], 0, {})

    assert fig.layout.annotations[0].x == last_date


def test_legacy_area_legends_use_plotted_stack_order_for_y_position() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_cumulated_legends

    last_date = date(2019, 6, 30)
    frame = pl.DataFrame(
        {
            "Date": [date(2019, 5, 31), last_date],
            "Small": [8.0, 10.0],
            "Large": [90.0, 100.0],
        }
    )
    stale_cumsum = pl.DataFrame({"Large": [999.0, 999.0]})
    fig = make_subplots(rows=1, cols=1)

    add_cumulated_legends(
        fig,
        frame,
        stale_cumsum,
        1,
        ["Sales"],
        ["Large", "Small"],
        1,
        {},
    )

    assert fig.layout.annotations[0].x == last_date
    assert fig.layout.annotations[0].y == 105.0


def test_legacy_stacked_column_legends_tolerate_missing_cumulative_value() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_legends_on_left_or_right
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"Current": [10.0, 20.0]})
    stale_cumsum = pl.DataFrame({"Previous": [None, None]})
    fig = go.Figure()

    add_legends_on_left_or_right(
        fig,
        frame.lazy(),
        stale_cumsum.lazy(),
        2,
        ["Previous", "Current"],
        "Current",
        1,
        {names["showLegend"]: names["showLegendLeftOrRight"]},
    )

    assert fig.layout.annotations[0].y == 5.0


def test_legacy_stacked_column_right_legends_use_rendered_column_edge() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_legends_on_left_or_right
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"Current": [10.0, 20.0, None]})
    cumsum = pl.DataFrame({"Current": [10.0, 20.0, None]})
    fig = go.Figure()
    fig.add_bar(
        x=[0, 1, 2],
        y=[10.0, 20.0, None],
        width=[0.8, 0.8, 0.8],
        offset=0,
    )

    add_legends_on_left_or_right(
        fig,
        frame.lazy(),
        cumsum.lazy(),
        2,
        ["Current"],
        "Current",
        0,
        {
            names["showLegend"]: names["showLegendLeftOrRight"],
            names["positionLegends"]: names["legendsAtRight"],
        },
    )

    annotation = fig.layout.annotations[0]
    assert annotation.x == pytest.approx(1.8)
    assert annotation.xref == "x"
    assert annotation.xshift == 10
    assert annotation.xanchor == "left"
    assert annotation.y == pytest.approx(10.0)


def test_legacy_stacked_pareto_dimension_legends_use_rendered_left_edge() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_legends_on_left
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"L'Oreal": [0.5, 0.4]})
    cumsum = pl.DataFrame({"L'Oreal": [0.5, 0.4]})
    fig = go.Figure()
    fig.add_bar(
        x=[0, 1, 2],
        y=[0.5, 0.4, 0.2],
        width=[0.9, 0.9, 0.9],
        offset=0,
    )

    add_legends_on_left(
        fig,
        frame,
        cumsum,
        3,
        ["L'Oreal"],
        "L'Oreal",
        0,
        {
            names["chosenChart"]: names["stackedParetoChart"],
            names["showLegend"]: names["showLegendLeftOrRight"],
            names["aggregateUniquesByDimension"]: True,
        },
    )

    annotation = fig.layout.annotations[0]
    assert annotation.x == pytest.approx(0.0)
    assert annotation.xref == "x"
    assert annotation.xshift == -10
    assert annotation.xanchor == "right"
    assert annotation.align == "right"
    assert annotation.y == pytest.approx(0.25)


def test_legacy_stacked_pareto_dimension_legends_skip_tiny_segments() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_legends_on_left
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"Tiny": [0.01, 0.02]})
    cumsum = pl.DataFrame({"Tiny": [0.01, 0.02]})
    fig = go.Figure()
    fig.add_bar(
        x=[0, 1, 2],
        y=[0.01, 0.02, 0.03],
        width=[0.9, 0.9, 0.9],
        offset=0,
    )

    add_legends_on_left(
        fig,
        frame,
        cumsum,
        3,
        ["Tiny"],
        "Tiny",
        0,
        {
            names["chosenChart"]: names["stackedParetoChart"],
            names["showLegend"]: names["showLegendLeftOrRight"],
            names["aggregateUniquesByDimension"]: True,
        },
    )

    assert list(fig.layout.annotations or []) == []


def test_legacy_stacked_column_cxgr_uses_rendered_column_edge() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_cxgr_on_right
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"Current": [10.0, 20.0, None]})
    cumsum = pl.DataFrame({"Current": [10.0, 20.0, None]})
    fig = go.Figure()
    fig.add_bar(
        x=[0, 1, 2],
        y=[10.0, 20.0, None],
        width=[0.8, 0.8, 0.8],
        offset=0,
    )

    add_cxgr_on_right(
        fig,
        frame.lazy(),
        cumsum.lazy(),
        "Current",
        2,
        ["Current"],
        0,
        {
            names["showLegend"]: names["showLegendLeftOrRight"],
            names["positionLegends"]: names["legendsAtRight"],
            names["CXGRMetricName"]: "CAGR",
            names["CXGRData"]: pl.DataFrame({"Current": [12.3]}).lazy(),
            names["periodsMissing"]: pl.DataFrame({"Current": [0.0]}).lazy(),
        },
    )

    annotation = fig.layout.annotations[0]
    assert annotation.x == pytest.approx(1.8)
    assert annotation.xref == "x"
    assert annotation.xshift == 120
    assert annotation.xanchor == "left"
    assert annotation.align == "left"
    assert annotation.y == pytest.approx(10.0)


def test_legacy_adapter_applies_spec_period_grain() -> None:
    legacy_charting = load_legacy_charting()
    frame = pl.DataFrame(
        {
            "Date": [date(2024, 1, 5), date(2025, 1, 5)],
            "Period": ["2024-01-05", "2025-01-05"],
            "Sales": [10.0, 30.0],
        }
    )

    grained = legacy_charting._frame_for_spec_period_grain(
        frame,
        {"period_grain": "year"},
    )

    assert grained.get_column("Period").to_list() == ["2024", "2025"]


def test_legacy_adapter_uses_ytd_for_incomplete_latest_year() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    previous_year_dates = [
        date(2016, 1, 3) + timedelta(weeks=index) for index in range(52)
    ]
    current_year_dates = [
        date(2017, 1, 1) + timedelta(weeks=index) for index in range(35)
    ]
    all_dates = [*previous_year_dates, *current_year_dates]
    frame = pl.DataFrame(
        {
            "Date": all_dates,
            "Period": [value.isoformat() for value in all_dates],
            "Sales": [1.0] * len(all_dates),
        }
    )
    spec = {
        "legacy_chart_key": "multitierBarChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2016-12-25", "2017-08-27"],
        "period_grain": "year",
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_selection": "explicit_comparison_periods"}},
            ["2016-12-25", "2017-08-27"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_comparison_mode"] == "year_to_date"
    assert selected_periods == ["_Aug-2016", "_Aug-2017"]
    assert chart[names["selectedPeriods"]] == ["_Aug-2016", "_Aug-2017"]
    assert chart[names["periodToDate"]] is True
    assert chart[names["compareWithYearBefore"]] is False
    assert audit["row_counts"] == {"_Aug-2016": 35, "_Aug-2017": 35}
    assert periodized.get_column("Date").max() == date(2017, 8, 27)
    assert periodized.filter(pl.col("Period") == "_Aug-2016").get_column(
        "Date"
    ).max() == date(2016, 8, 28)
    assert (
        periodized.filter(pl.col("Period") == "_Aug-2016")
        .select(pl.col("Sales").sum())
        .item()
        == 35.0
    )


def test_legacy_adapter_defaults_inferred_raw_dates_to_year_selection() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Date": [date(2024, 1, 5), date(2024, 7, 5), date(2025, 1, 5)],
            "Period": ["2024-01-05", "2024-07-05", "2025-01-05"],
            "Sales": [10.0, 20.0, 30.0],
        }
    )
    spec = {
        "legacy_chart_key": "multitierBarChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2024-07-05", "2025-01-05"],
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    _periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_selection": "infer_current_or_all"}},
            ["2024-07-05", "2025-01-05"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_grain"] == "year"
    assert audit["period_comparison_mode"] == "year_to_date"
    assert selected_periods == ["_Jan-2024", "_Jan-2025"]
    assert chart[names["datePeriodName"]] == names["yearName"]


def test_legacy_adapter_uses_date_column_when_period_is_actual_label() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    previous_year_dates = [
        date(2016, 1, 3) + timedelta(weeks=index) for index in range(35)
    ]
    current_year_dates = [
        date(2017, 1, 1) + timedelta(weeks=index) for index in range(35)
    ]
    frame = pl.DataFrame(
        {
            "Date": [*previous_year_dates, *current_year_dates],
            "Period": ["AC"] * 70,
            "Sales": [1.0] * 70,
        }
    )
    spec = {
        "legacy_chart_key": "stackedColumnChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2015", "2016", "2017"],
        "period_grain": "year",
        "show_cagr": True,
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_selection": "infer_current_or_all"}},
            ["2015", "2016", "2017"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_comparison_mode"] == "year_to_date"
    assert selected_periods == ["_Aug-2016", "_Aug-2017"]
    assert chart[names["selectedPeriods"]] == ["_Aug-2016", "_Aug-2017"]
    assert chart[names["periodToDate"]] is True
    assert periodized.get_column("Period").unique().sort().to_list() == [
        "_Aug-2016",
        "_Aug-2017",
    ]


def test_legacy_adapter_keeps_quarter_grain_out_of_year_window() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    dates = [date(year, month, 1) for year in (2024, 2025) for month in range(1, 7)]
    frame = pl.DataFrame(
        {
            "Date": dates,
            "Period": [value.isoformat() for value in dates],
            "Sales": [1.0] * len(dates),
        }
    )
    spec = {
        "legacy_chart_key": "multitierBarChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2024-06-01", "2025-06-01"],
        "period_grain": "quarter",
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    _periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_selection": "infer_current_or_all"}},
            ["2024-06-01", "2025-06-01"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_grain"] == "quarter"
    assert "period_comparison_mode" not in audit
    assert chart[names["datePeriodName"]] == names["quarterName"]
    assert any("-Q" in str(period) for period in selected_periods)
    assert all(not str(period).startswith("_") for period in selected_periods)
    assert chart[names["selectedPeriods"]] == selected_periods
    assert chart[names["toPlotPeriod"]] == selected_periods[-1]


def test_legacy_adapter_uses_latest_date_for_current_week_grain() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    dates = [date(2016, 12, 25), date(2017, 8, 20), date(2017, 8, 27)]
    frame = pl.DataFrame(
        {
            "Date": dates,
            "Period": [value.isoformat() for value in dates],
            "Sales": [1.0] * len(dates),
        }
    )
    spec = {
        "legacy_chart_key": "stackedBarChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2017-08-27"],
        "period_grain": "week",
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    _periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_selection": "infer_current_or_all"}},
            ["2017-08-27"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_grain"] == "week"
    assert selected_periods == ["’17-W34"]
    assert chart[names["selectedPeriods"]] == selected_periods
    assert chart[names["toPlotPeriod"]] == "’17-W34"


def test_legacy_adapter_calendar_mode_excludes_partial_latest_year() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    complete_dates = [
        date(year, month, 1) for year in (2023, 2024) for month in range(1, 13)
    ]
    partial_dates = [date(2025, month, 1) for month in range(1, 4)]
    all_dates = [*complete_dates, *partial_dates]
    frame = pl.DataFrame(
        {
            "Date": all_dates,
            "Period": [value.isoformat() for value in all_dates],
            "Sales": [1.0] * len(all_dates),
        }
    )
    spec = {
        "legacy_chart_key": "stackedColumnChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2024", "2025"],
        "period_grain": "year",
        "period_comparison_mode": "calendar_period",
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {"options": {"period_comparison_mode": "calendar_period"}},
            ["2024", "2025"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_comparison_mode"] == "calendar_period"
    assert audit["complete_years_only"] is True
    assert audit["selected_years"] == [2023, 2024]
    assert selected_periods == ["’23", "’24"]
    assert chart[names["selectedPeriods"]] == ["’23", "’24"]
    assert set(periodized.get_column("Period").to_list()) == {"’23", "’24"}
    assert periodized.get_column("Date").max() == date(2024, 12, 1)


def test_legacy_adapter_rolling_mode_uses_labelled_equal_windows() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    all_dates = [
        date(2022 + (month_index // 12), (month_index % 12) + 1, 1)
        for month_index in range(8, 32)
    ]
    frame = pl.DataFrame(
        {
            "Date": all_dates,
            "Period": [value.isoformat() for value in all_dates],
            "Sales": [1.0] * len(all_dates),
        }
    )
    spec = {
        "legacy_chart_key": "multitierBarChart",
        "dimensions": ["Company"],
        "metrics": ["Sales"],
        "selected_periods": ["2023-08-01", "2024-08-01"],
        "period_grain": "year",
        "period_comparison_mode": "rolling_period",
    }
    chart = legacy_charting._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    periodized, selected_periods, chart, audit = (
        legacy_charting._apply_legacy_period_grain_selection(
            frame,
            names,
            chart,
            spec,
            {
                "options": {
                    "period_comparison_mode": "rolling_period",
                    "rolling_window_months": 12,
                }
            },
            ["2023-08-01", "2024-08-01"],
        )
    )

    assert audit["status"] == "applied"
    assert audit["period_comparison_mode"] == "rolling_period"
    assert selected_periods == ["~Aug-2023", "~Aug-2024"]
    assert chart[names["compareWithYearBefore"]] is True
    assert chart[names["periodToDate"]] is False
    assert audit["row_counts"] == {"~Aug-2023": 12, "~Aug-2024": 12}
    assert set(periodized.get_column("Period").to_list()) == {
        "~Aug-2023",
        "~Aug-2024",
    }


def test_legacy_adapter_adds_period_comparison_context_to_title() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(text="<b>Sales</b><br>_Aug-2017 AC vs PY")

    legacy_charting._apply_period_window_title_context(
        [figure],
        {
            "period_comparison_mode": "year_to_date",
            "title_period_context": "YTD through 2017-08-27",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
    )

    assert figure.layout.annotations[0].text.endswith(
        "_Aug-2017 vs _Aug-2016, YTD through 2017-08-27"
    )


def test_legacy_adapter_does_not_add_period_context_to_total_annotation() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(text="Total<br><b>677</b>")
    figure.add_annotation(text="<b>Sales</b> in mEUR by Type<br>_Aug-2017")

    legacy_charting._apply_period_window_title_context(
        [figure],
        {
            "period_comparison_mode": "year_to_date",
            "title_period_context": "YTD through 2017-08-27",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
    )

    assert figure.layout.annotations[0].text == "Total<br><b>677</b>"
    assert figure.layout.annotations[1].text.endswith(
        "_Aug-2017<br>YTD through 2017-08-27"
    )


def test_legacy_period_window_axis_labels_show_year_only() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.update_xaxes(
        tickvals=[0.4, 1.4, 2.4],
        ticktext=["_Aug-2016", "_Aug-2017", "     "],
    )

    legacy_charting._apply_period_window_axis_labels(
        [figure],
        {"period_comparison_mode": "year_to_date"},
    )

    assert list(figure.layout.xaxis.ticktext) == ["2016", "2017", "     "]
    assert figure.layout.xaxis.tickangle == 0


def test_legacy_reporting_title_structure_uses_three_lines() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(
        text="<b>Sales</b> in mEUR by Type, Company and Channel"
        "<br>_Aug-2017<br>YTD through 2017-08-27"
    )

    legacy_charting._apply_reporting_title_structure(
        [figure],
        {
            "name": "stacked_bar_small_multiples",
            "reporting_entity_label": "Haircolor in Mexico",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
        {
            "period_comparison_mode": "year_to_date",
            "title_period_context": "YTD through 2017-08-27",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
    )

    assert figure.layout.annotations[0].text == (
        "Haircolor in Mexico"
        "<br><b>Sales</b> in mEUR by Type, Company and Channel"
        "<br>YTD through 2017-08-27"
    )


def test_legacy_reporting_title_structure_repairs_split_bold_measure_line() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(
        text="Legacy entity <b><br>Sales</b> in mEUR by Brand"
        "<br>YTD through 2017-08-27"
    )

    legacy_charting._apply_reporting_title_structure(
        [figure],
        {
            "name": "bar",
            "reporting_entity_label": "Mexico hair color",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
        {
            "period_comparison_mode": "year_to_date",
            "title_period_context": "YTD through 2017-08-27",
            "selected_periods": ["_Aug-2016", "_Aug-2017"],
        },
    )

    assert figure.layout.annotations[0].text == (
        "Mexico hair color"
        "<br><b>Sales</b> in mEUR by Brand"
        "<br>YTD through 2017-08-27"
    )


def test_legacy_reporting_title_structure_recognizes_pareto_annotation() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(
        text="<BR>ABC by sorted Brand Sales in EUR<BR>AC",
        xref="paper",
        yref="paper",
    )

    legacy_charting._apply_reporting_title_structure(
        [figure],
        {
            "name": "stacked_pareto_abc",
            "reporting_entity_label": "Mexico hair color",
            "selected_periods": ["AC"],
        },
        {},
    )

    assert figure.layout.annotations[0].text == (
        "Mexico hair color<br>ABC by sorted Brand Sales in EUR<br>AC"
    )


def test_static_reporting_title_lines_use_one_plain_font() -> None:
    legacy_charting = load_legacy_charting()
    calls: list[dict[str, object]] = []

    class RecordingDraw:
        def text(
            self,
            xy: tuple[int, int],
            text: str,
            *,
            fill: str,
            font: object,
        ) -> None:
            calls.append({"xy": xy, "text": text, "fill": fill, "font": font})

    title_font = object()

    legacy_charting._draw_static_title_lines(
        RecordingDraw(),
        ["Mexico hair color", "Sales in mEUR by Brand", "YTD through 2017-08-27"],
        x=10,
        y=20,
        line_height=12,
        font=title_font,
    )

    assert [call["text"] for call in calls] == [
        "Mexico hair color",
        "Sales in mEUR by Brand",
        "YTD through 2017-08-27",
    ]
    assert [call["font"] for call in calls] == [title_font, title_font, title_font]


def test_chart_specs_apply_reporting_entity_label_to_every_mix_chart() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date(2025, 1, 5),
                "Period": period,
                "Sales": sales,
                "Units": units,
                "Company": company,
                "Brand": brand,
                "Channel": channel,
            }
            for period, sales, units in (("PY", 10.0, 5.0), ("AC", 14.0, 7.0))
            for company, brand, channel in (
                ("A", "Alpha", "Mexico City"),
                ("B", "Beta", "Monterrey"),
            )
        ]
    )
    recipe = {
        "source_file": "/tmp/hair_color_IV.xlsx",
        "mappings": {
            "date_column": "Date",
            "period_column": "Period",
            "amount_column": "Sales",
            "width_metric_column": "Units",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Company", "Brand", "Channel"],
        },
        "options": {
            "current_period_label": "AC",
            "period_selection": "infer_current_or_all",
            "charts": ["bar", "stacked_column"],
            "small_multiples": False,
            "max_chart_items": 4,
        },
    }

    specs = core.build_chart_specs(canonical, recipe)

    assert {spec["name"] for spec in specs} >= {"bar", "stacked_column"}
    assert all(spec["reporting_entity_label"] == "Hair Color" for spec in specs)


def test_legacy_param_dict_preserves_chart_period_choice() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    params = legacy_charting._legacy_param_dict(
        names,
        total=30.0,
        selected_periods=["2024", "2025"],
        period_totals={"2024": 10.0, "2025": 30.0},
        columns=["Period", "Sales"],
        date_period_choice=names["yearName"],
    )

    assert params[names["datePeriodName"]] == names["yearName"]


def test_legacy_timeline_labels_use_date_axis_values_when_available() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_timeline import add_labels_to_timeline_chart

    first_date = date(2019, 1, 31)
    frame = pl.DataFrame({"Date": [first_date], "Sales": [10.0]})
    fig = make_subplots(rows=1, cols=1)

    add_labels_to_timeline_chart(
        fig,
        frame,
        "Sales__label",
        "area",
        "Sales",
        ["10.0"],
        [0],
        [0],
        1,
        1,
    )

    assert fig.layout.annotations[0].x == first_date


def test_legacy_timeline_traces_use_sorted_date_axis_values() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_timeline import add_annotations_to_timeline
    from modules.data.time_series_data_prep import prepare_data_for_timeline_plot
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    first_date = date(2019, 1, 31)
    middle_date = date(2019, 2, 28)
    last_date = date(2019, 3, 31)
    frame = pl.DataFrame(
        {
            "Date": [last_date, first_date, middle_date],
            "Company": ["Total", "Total", "Total"],
            "Sales": [30.0, 10.0, 20.0],
        }
    )
    prepared = prepare_data_for_timeline_plot(
        frame,
        "Company",
        "Sales",
        ["Total"],
        {names["chosenChart"]: names["timelineChart"]},
    )
    fig = make_subplots(rows=1, cols=1)

    add_annotations_to_timeline(
        prepared,
        fig,
        ["Total"],
        ["#343434"],
        {
            names["chosenChart"]: names["timelineChart"],
            names["plotValuesAsChoice"]: names["absolute"],
        },
        1,
        1,
    )

    assert list(fig.data[0].x) == [first_date, middle_date, last_date]
    assert fig.layout.xaxis.type == "date"
    labels_by_date = {annotation.x: annotation for annotation in fig.layout.annotations}
    assert labels_by_date[first_date].xshift == 18
    assert labels_by_date[last_date].xshift == -18


def test_legacy_stacked_column_width_uses_root_legacy_column_gaps() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.adjust_position import set_bar_gap_offset
    from modules.charting.draw_charts_utils import compute_positions
    from modules.utilities.config import get_config_params, get_naming_params

    names = get_naming_params()
    config = get_config_params()

    def calculated_width(bargap: float, make_thin: bool) -> float:
        frame = pl.DataFrame({"Dimension": ["A"]}).lazy()
        result = compute_positions(
            frame,
            names["countName"],
            bargap,
            make_thin,
        ).select("width_col")
        return result.collect().get_column("width_col").item()

    base_chart = {
        names["showLegend"]: names["showLegendLeftOrRight"],
        names["datePeriodName"]: names["yearName"],
        names["stackedColumnMetric"]: "Sales",
    }

    bargap, offset, make_thin = set_bar_gap_offset(
        base_chart,
        names,
        config,
        ["Price"],
    )
    assert bargap == pytest.approx(0.20)
    assert offset == 0
    assert make_thin is False
    normal_width = calculated_width(bargap, make_thin)
    assert normal_width == pytest.approx(0.80)

    no_sum_chart = {**base_chart, names["stackedColumnMetric"]: "Price"}
    no_sum_bargap, _offset, no_sum_make_thin = set_bar_gap_offset(
        no_sum_chart,
        names,
        config,
        ["Price"],
    )
    no_sum_width = calculated_width(no_sum_bargap, no_sum_make_thin)
    assert no_sum_bargap == pytest.approx(0.10)
    assert no_sum_width == pytest.approx(0.45)
    assert no_sum_width < normal_width
    assert no_sum_make_thin is True

    no_sum_small_multiple_chart = {
        **no_sum_chart,
        names["plotSmallMultiplesOtherCharts"]: True,
    }
    (
        no_sum_small_bargap,
        no_sum_small_offset,
        no_sum_small_make_thin,
    ) = set_bar_gap_offset(
        no_sum_small_multiple_chart,
        names,
        config,
        ["Price"],
    )
    assert no_sum_small_offset == pytest.approx(0.2)
    assert calculated_width(no_sum_small_bargap, no_sum_small_make_thin) == (
        pytest.approx(0.50)
    )
    assert no_sum_small_make_thin is False

    synthesis_chart = {**base_chart, names["synthesisPlot"]: True}
    synthesis_bargap, _offset, synthesis_make_thin = set_bar_gap_offset(
        synthesis_chart,
        names,
        config,
        ["Price"],
    )
    assert synthesis_bargap == pytest.approx(0.10)
    assert calculated_width(synthesis_bargap, synthesis_make_thin) == pytest.approx(
        0.90
    )
    assert synthesis_make_thin is False


def test_plugin_chart_dict_keeps_thin_width_for_non_additive_columns() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        set_stacked_column_params_and_add_trace,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    price_metric = names["pricePerUnitName"]
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Total View"],
            "x_dimension": "Total View",
            "y_dimension": "Total View",
            "metrics": [price_metric],
            "selected_periods": ["2016", "2017"],
            "period_grain": "year",
        },
        metric=price_metric,
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Period": ["2016", "2017"],
            price_metric: [4.2, 4.8],
            "Value": [4.2, 4.8],
        }
    ).lazy()

    (
        figure,
        _half_column,
        _ticktext,
        _tickformat,
        _range_array,
        _visible,
        _showticklabels,
        _tickvals,
        _tickrange,
        _barmode,
        bargap,
        _max_label_length,
        chart,
    ) = set_stacked_column_params_and_add_trace(
        go.Figure(),
        {},
        frame,
        price_metric,
        "#343434",
        chart,
        ["2016", "2017"],
        2,
        0,
    )

    assert chart[names["stackedColumnMetric"]] == price_metric
    assert bargap == pytest.approx(0.10)
    assert list(figure.data[0].width) == pytest.approx([0.45, 0.45])


def test_plugin_chart_dict_keeps_thin_width_for_non_additive_bars() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        set_stacked_bar_params_and_add_trace,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    price_metric = names["pricePerUnitName"]
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Company"],
            "x_dimension": "Company",
            "y_dimension": None,
            "metrics": [price_metric],
            "selected_periods": ["AC"],
        },
        metric=price_metric,
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Company": ["A", "B"],
            price_metric: [4.2, 4.8],
            "Value": [4.2, 4.8],
        }
    ).lazy()

    (
        figure,
        _half_column,
        _ticktext,
        _tickformat,
        _range_array,
        _visible,
        _showticklabels,
        _tickvals,
        _tickrange,
        _barmode,
        bargap,
        chart,
        _row,
        _col,
        _half_column_lazy,
    ) = set_stacked_bar_params_and_add_trace(
        go.Figure(),
        {},
        frame,
        price_metric,
        "#343434",
        None,
        chart,
        ["A", "B"],
        2,
    )

    assert chart[names["stackedColumnMetric"]] == price_metric
    assert bargap == pytest.approx(0.25)
    assert list(figure.data[0].width) == pytest.approx([0.75, 0.75])


def test_legacy_stacked_column_centers_ticks_and_totals_on_rendered_columns() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        set_stacked_column_params_and_add_trace,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Brand_Lost"],
            "x_dimension": "Brand_Lost",
            "y_dimension": "Brand_Lost",
            "metrics": ["Sales"],
            "selected_periods": ["2016", "2017"],
            "period_grain": "year",
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Period": ["2016", "2017"],
            "Still active": [1087800550.0, 735535385.0],
            "Value": [1087800550.0, 735535385.0],
        }
    ).lazy()

    (
        figure,
        half_column,
        _ticktext,
        _tickformat,
        _range_array,
        _visible,
        _showticklabels,
        tickvals,
        _tickrange,
        _barmode,
        _bargap,
        _max_label_length,
        _chart,
    ) = set_stacked_column_params_and_add_trace(
        go.Figure(),
        {},
        frame,
        "Still active",
        "#343434",
        chart,
        ["2016", "2017"],
        2,
        0,
    )

    assert list(figure.data[0].x) == [0, 1]
    assert list(figure.data[0].width) == pytest.approx([0.8, 0.8])
    assert list(figure.data[0].text) == ["", ""]
    assert tickvals == pytest.approx([0.4, 1.4])
    assert half_column.collect()["halfColumn"].to_list() == pytest.approx([0.4, 1.4])


def test_legacy_stacked_column_keeps_segment_labels_for_stacked_columns() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        set_stacked_column_params_and_add_trace,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Brand"],
            "x_dimension": "Brand",
            "y_dimension": "Brand",
            "metrics": ["Sales"],
            "selected_periods": ["2016", "2017"],
            "period_grain": "year",
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Period": ["2016", "2017"],
            "Brand A": [10.0, 20.0],
            "Brand B": [30.0, 40.0],
            "Value": [40.0, 60.0],
        }
    ).lazy()

    (
        figure,
        _half_column,
        _ticktext,
        _tickformat,
        _range_array,
        _visible,
        _showticklabels,
        _tickvals,
        _tickrange,
        _barmode,
        _bargap,
        _max_label_length,
        _chart,
    ) = set_stacked_column_params_and_add_trace(
        go.Figure(),
        {},
        frame,
        "Brand A",
        "#343434",
        chart,
        ["2016", "2017"],
        2,
        0,
    )

    assert any(str(text).strip() for text in figure.data[0].text)


def test_legacy_context_records_synthesis_trace_width_from_bargap() -> None:
    legacy_charting = load_legacy_charting()

    figure = SimpleNamespace(
        data=[SimpleNamespace(type="bar", name="A", width=None, x=[], y=[], text=[])],
        layout=SimpleNamespace(
            bargap=0.2,
            annotations=[],
            title=SimpleNamespace(text=""),
        ),
    )

    payload = legacy_charting._capture_context_payload(
        spec={
            "name": "stacked_column_synthesis",
            "capture_chart_data": True,
            "capture_figure": "last",
            "synthesis_plot": True,
            "dimensions": ["Company", "Brand"],
            "metric": "Sales",
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
        },
        chart={},
        calls=[{"legacy_chart": "stacked column", "data_frame": {}}],
        figures=[figure],
        exports=[],
        source_functions=[],
    )

    assert payload is not None
    assert payload["trace_widths"] == [0.8]
    assert payload["plotly_figures"][0]["layout_width"] is None
    assert payload["plotly_figures"][0]["layout_height"] is None


def test_legacy_export_size_adds_annotation_lane_for_narrow_columns() -> None:
    legacy_charting = load_legacy_charting()

    figure = SimpleNamespace(
        data=[SimpleNamespace(type="bar", orientation=None)],
        layout=SimpleNamespace(
            width=270,
            height=650,
        ),
    )

    assert legacy_charting._legacy_export_size(figure) == (450, 650)


def test_legacy_export_size_preserves_non_bar_single_panel_dimensions() -> None:
    legacy_charting = load_legacy_charting()

    figure = SimpleNamespace(
        data=[SimpleNamespace(type="scatter", orientation=None)],
        layout=SimpleNamespace(
            width=270,
            height=650,
        ),
    )

    assert legacy_charting._legacy_export_size(figure) == (270, 650)


def test_legacy_column_export_padding_preserves_plot_domain_width() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    figure = go.Figure(data=[go.Bar(x=[0, 1], y=[10, 20])])

    legacy_charting._preserve_legacy_single_panel_plot_width(
        figure,
        original_width=270,
        export_width=450,
    )

    assert list(figure.layout.xaxis.domain) == pytest.approx([0.0, 0.6])


def test_legacy_export_size_expands_real_subplot_grids() -> None:
    legacy_charting = load_legacy_charting()

    class SubplotLayout:
        width = 500
        height = 400

        def to_plotly_json(self) -> dict[str, dict[str, list[float]]]:
            return {
                "xaxis": {"domain": [0.0, 0.45]},
                "xaxis2": {"domain": [0.55, 1.0]},
                "yaxis": {"domain": [0.0, 0.45]},
                "yaxis2": {"domain": [0.55, 1.0]},
            }

    figure = SimpleNamespace(layout=SubplotLayout())

    assert legacy_charting._legacy_export_size(figure) == (2220, 1300)


def test_legacy_context_helpers_accept_numpy_plotly_arrays() -> None:
    legacy_charting = load_legacy_charting()

    import numpy as np

    marker = SimpleNamespace(color=np.array(["#111111", "#222222"]))
    trace = SimpleNamespace(
        type="bar",
        name="by Active",
        x=np.array([0, 0]),
        y=np.array([10.0, 5.0]),
        text=np.array(["10.0", "5.0"]),
        width=np.array([0.25, 0.25]),
        marker=marker,
    )
    figure = SimpleNamespace(
        data=np.array([trace], dtype=object),
        layout=SimpleNamespace(
            title=SimpleNamespace(text="Title"),
            annotations=np.array([], dtype=object),
            xaxis=SimpleNamespace(
                tickvals=np.array([0.0]),
                ticktext=np.array(["Company"]),
            ),
        ),
    )

    figure_payload = legacy_charting._figure_payload(figure)
    rows = legacy_charting._series_rows_by_dimension([figure], ["Fallback"])
    widths = legacy_charting._context_trace_widths(
        [figure],
        {"synthesis_plot": False},
    )

    assert figure_payload["traces"][0]["x"] == [0, 0]
    assert figure_payload["traces"][0]["y"] == [10.0, 5.0]
    assert figure_payload["traces"][0]["text"] == ["10.0", "5.0"]
    assert figure_payload["traces"][0]["width"] == [0.25, 0.25]
    assert rows[0]["dimension"] == "Company"
    assert rows[0]["item"] == "Active"
    assert widths == [0.25]


def test_legacy_waterfall_context_rows_are_panel_labeled() -> None:
    legacy_charting = load_legacy_charting()

    def trace(trace_type: str, name: str, value: float) -> SimpleNamespace:
        return SimpleNamespace(
            type=trace_type,
            name=name,
            x=["period zero", "Aug", "period one"],
            y=[0.0, value, value],
            text=["0.0", str(value), str(value)],
        )

    figure = SimpleNamespace(
        data=[
            trace("waterfall", "", 10.0),
            trace("bar", "PY", 8.0),
            trace("bar", "AC", 10.0),
            trace("waterfall", "", 5.0),
            trace("bar", "PY", 6.0),
            trace("bar", "AC", 5.0),
        ],
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="Right panel", x=0.75, y=1.0),
                SimpleNamespace(text="Left panel", x=0.25, y=1.0),
                SimpleNamespace(
                    text="Date=2024 <b><BR>Sales</b>",
                    x=0,
                    y=1,
                ),
            ],
        ),
    )

    rows = legacy_charting._waterfall_rows_from_figures([figure])

    assert rows[0]["panel"] == "Left panel"
    assert rows[3]["panel"] == "Left panel"
    assert rows[9]["panel"] == "Right panel"
    assert rows[9]["trace_type"] == "waterfall"
    assert rows[10]["step"] == "Aug"
    assert rows[10]["value"] == 5.0


def test_mix_chart_context_artifacts_write_waterfall_rows_csv(
    tmp_path: Path,
) -> None:
    core = load_core()
    chart_context = {
        "chart_data_source": "plotly figure traces",
        "waterfall_rows": [
            {
                "panel": "A",
                "trace_type": "waterfall",
                "step": "Aug",
                "value": 10.0,
            }
        ],
    }

    paths, audit = core.write_chart_context_artifacts(
        "horizontal_waterfall_small_multiples",
        chart_context,
        tmp_path,
    )

    assert audit["table_status"] == "written"
    assert audit["table_path"] == "horizontal_waterfall_small_multiples_chart_data.csv"
    assert (
        str(tmp_path / "horizontal_waterfall_small_multiples_chart_data.csv") in paths
    )
    written = pl.read_csv(
        tmp_path / "horizontal_waterfall_small_multiples_chart_data.csv"
    )
    assert written.to_dicts() == [
        {
            "panel": "A",
            "trace_type": "waterfall",
            "step": "Aug",
            "value": 10.0,
        }
    ]


def test_legacy_series_context_uses_axis_labels_for_stacked_columns() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_bar(
        name="Active",
        x=[0, 1, 2],
        y=[10.0, 20.0, 30.0],
        text=["10", "20", "30"],
    )
    figure.update_xaxes(tickvals=[0.5, 1.5, 2.5], ticktext=["2015", "2016", "2017"])

    rows = legacy_charting._series_rows_by_dimension(
        [figure],
        ["Barcode_Lost"],
    )

    assert [row["dimension"] for row in rows] == ["2015", "2016", "2017"]
    assert [row["axis_label"] for row in rows] == ["2015", "2016", "2017"]
    assert {row["source_dimension"] for row in rows} == {"Barcode_Lost"}


def test_legacy_multitier_outlier_pins_accept_python_floats() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_multitier import (
        add_negative_outlier_pins_to_bar,
        add_positive_outlier_pins_to_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({names["differenceInPercent"]: [12.4, -3.2]})
    colors = {"greenColor": "#008000", "redColor": "#c00000"}
    fig = make_subplots(rows=1, cols=3)

    add_positive_outlier_pins_to_bar(fig, frame, [0.5, 12.4, 0], colors, 3)
    add_negative_outlier_pins_to_bar(fig, frame, [0.5, -3.2, 1], colors, 3)

    annotation_texts = [annotation.text for annotation in fig.layout.annotations]
    assert "<i>+12%</i>" in annotation_texts
    assert "<i>-3%</i>" in annotation_texts


def test_legacy_multitier_small_multiple_y_slots_pack_items_at_top() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_multitier import _lock_multitier_small_multiple_y_slots
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    placeholder = names["invisibleCharacter"]
    chart = {names["plotSmallMultiplesOtherCharts"]: True}
    frame = pl.DataFrame({"Company": ["Largest", "Second", placeholder]})
    fig = make_subplots(rows=1, cols=1)

    _lock_multitier_small_multiple_y_slots(fig, frame, "Company", 1, 1, chart)

    assert fig.layout.yaxis.categoryarray == ("Largest", "Second", placeholder)
    assert fig.layout.yaxis.range == (1.5, -0.9)
    assert fig.layout.yaxis.domain == pytest.approx((1 / 3, 1.0))


def test_legacy_multitier_small_multiple_panels_rank_by_total_with_other_last() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_multitier import _rank_repeat_array_by_size

    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "PY", "AC", "PY", "AC", "AC"],
            "Type": ["Small", "Small", "Large", "Large", "Medium", "Medium", "Hidden"],
            "Sales": [200.0, 10.0, 50.0, 80.0, 100.0, 45.0, 5.0],
        }
    )

    ranked = _rank_repeat_array_by_size(
        frame,
        ["Small", "Others rank >3", "Large", "Medium"],
        "Type",
        ["Sales"],
        "Period",
        ["PY", "AC"],
    )

    assert ranked == ["Large", "Medium", "Small", "Others rank >3"]


def test_legacy_multitier_two_dimension_panels_rank_by_visible_current_values() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_multitier import (
        _rank_multitier_bar_panels_by_plotted_current_period,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "PY", "AC", "PY", "AC"],
            "Type": ["Root", "Root", "Male", "Male", "Semi", "Semi"],
            "Brand": ["Top", "Top", "Hidden", "Hidden", "Top", "Top"],
            "Sales": [10.0, 50.0, 1.0, 120.0, 8.0, 20.0],
        }
    )
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Type", "Brand"],
            "multitier_bar_two_dimension": True,
            "small_multiples_dimension": "Type",
            "multitier_bar_panel_dimension": "Type",
            "multitier_bar_item_dimension": "Brand",
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
            "multitier_bar_item_max_items": 1,
        },
        metric="Sales",
        currency="EUR",
    )
    param = legacy_charting._legacy_param_dict(
        names,
        total=0.0,
        selected_periods=["PY", "AC"],
        period_totals={},
        columns=frame.columns,
        date_period_choice=chart[names["datePeriodName"]],
    )

    ranked = _rank_multitier_bar_panels_by_plotted_current_period(
        frame.lazy(),
        ["Male", "Root", "Semi", "Others rank >3"],
        "Type",
        "Brand",
        "Period",
        "Sales",
        ["Sales"],
        chart,
        param,
        ["PY", "AC"],
        ["Top"],
    )

    assert ranked == ["Root", "Semi", "Male", "Others rank >3"]


def test_legacy_multitier_small_multiple_title_is_lifted_above_panels() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_multitier import _lift_multitier_small_multiple_title
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["chosenChart"]: names["multitierBarChart"],
        names["plotSmallMultiplesOtherCharts"]: True,
    }
    fig = make_subplots(rows=1, cols=1, subplot_titles=["Panel"])
    title = "Sales by Brand and Type<br>_Aug-2017 AC vs PY"
    fig.add_annotation(text=title, x=0, y=1.04, showarrow=False)

    _lift_multitier_small_multiple_title(fig, title, chart)

    lifted = fig.layout.annotations[-1]
    assert lifted.y == pytest.approx(1.11)
    assert lifted.yanchor == "bottom"
    assert fig.layout.margin.t >= 95


def test_legacy_multitier_small_multiple_rows_sort_by_current_period() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_multitier import _sort_multitier_small_multiple_rows
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    placeholder = names["invisibleCharacter"]
    chart = {
        names["chosenChart"]: names["multitierBarChart"],
        names["plotSmallMultiplesOtherCharts"]: True,
    }
    frame = pl.DataFrame(
        {
            "Type": ["Root", "Male", "Permanent", placeholder],
            "PY": [1.0, 2.0, 8.0, None],
            "AC": [1.3, 1.1, 14.5, None],
        }
    )

    sorted_frame = _sort_multitier_small_multiple_rows(
        frame,
        "Type",
        ["PY", "AC"],
        chart,
    ).collect()

    assert sorted_frame["Type"].to_list() == ["Permanent", "Root", "Male", placeholder]


def test_legacy_multitier_export_frames_cast_numeric_columns_for_concat() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.charting.draw_multitier import _normalize_multitier_export_frame

    left = pl.LazyFrame(
        {
            "Type": ["Permanent"],
            "Brand": ["Koleston"],
            "PY": [1.2],
            "AC": [2.3],
        }
    )
    right = pl.LazyFrame(
        {
            "Type": ["Root"],
            "Brand": ["Koleston"],
            "PY": [0],
            "AC": [0],
        }
    )

    combined = pl.concat(
        [
            _normalize_multitier_export_frame(left, ["Type", "Brand"]),
            _normalize_multitier_export_frame(right, ["Type", "Brand"]),
        ],
        how="vertical",
    ).collect()

    assert combined.schema["PY"] == pl.Float64
    assert combined.schema["AC"] == pl.Float64
    assert combined["Type"].to_list() == ["Permanent", "Root"]


def test_legacy_export_size_expands_plotly_small_multiple_canvas() -> None:
    legacy_charting = load_legacy_charting()

    from plotly.subplots import make_subplots

    fig = make_subplots(rows=3, cols=2)
    fig.update_layout(width=569, height=812)

    assert legacy_charting._subplot_grid_size(fig) == (2, 3)
    assert legacy_charting._legacy_export_size(fig) == (2220, 1820)


def test_legacy_export_size_preserves_horizontal_bar_grid_canvas() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=3, cols=2)
    fig.add_trace(go.Bar(x=[1], y=["A"], orientation="h"), row=1, col=1)
    fig.update_layout(width=1299, height=734)

    assert legacy_charting._subplot_grid_size(fig) == (2, 3)
    assert legacy_charting._legacy_export_size(fig) == (1299, 734)


def test_legacy_barmekko_small_multiples_reserve_right_label_canvas() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=2)
    fig.add_trace(go.Bar(x=[100], y=["A"], orientation="h"), row=1, col=1)
    fig.update_layout(width=1052, height=650, margin={"r": 20})

    legacy_charting._apply_barmekko_small_multiple_label_canvas(
        [fig], {"name": "barmekko_small_multiples"}
    )

    assert fig.layout.width == 1500
    assert fig.layout.height == 650
    assert fig.layout.margin.r == 130
    assert fig.layout.xaxis.range[0] == 0
    assert fig.layout.xaxis.range[1] == pytest.approx(115.0)
    assert fig.layout.xaxis.autorange is False


def test_legacy_barmekko_small_multiples_export_size_expands_canvas() -> None:
    legacy_charting = load_legacy_charting()

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=2)
    fig.add_trace(go.Bar(x=[100], y=["A"], orientation="h"), row=1, col=1)
    fig.update_layout(width=1052, height=650)

    assert legacy_charting._legacy_export_size(fig) == (1052, 650)
    assert legacy_charting._legacy_export_size(fig, "barmekko_small_multiples.png") == (
        1500,
        650,
    )


def test_mekko_specs_avoid_observed_hierarchical_dimension_pairs_and_bad_facets() -> (
    None
):
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Units": 2,
                "Productline": productline,
                "Category": category,
                "Region": region,
            }
            for productline, categories in {
                "Bikes": ["Road", "Mountain"],
                "Accessories": ["Helmets"],
            }.items()
            for category in categories
            for region in ["North", "South"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Category", "Region"],
        },
        "options": {"small_multiples": True, "small_multiples_max_panels": 6},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["marimekko"]["x_dimension"] == "Productline"
    assert specs["marimekko"]["y_dimension"] == "Region"
    assert specs["barmekko"]["x_dimension"] == "Productline"
    assert specs["barmekko"]["y_dimension"] == "Region"
    assert "marimekko_small_multiples" not in specs
    assert "barmekko_small_multiples" not in specs


def test_mekko_specs_use_legacy_renderer_and_label_defaults() -> None:
    core = load_core()
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Units": 2,
                "Productline": productline,
                "Category": category,
                "Region": region,
            }
            for productline, categories in {
                "Bikes": ["Road", "Mountain"],
                "Accessories": ["Helmets"],
            }.items()
            for category in categories
            for region in ["North", "South"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Category", "Region"],
        },
        "options": {"small_multiples": False},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    marimekko_spec = specs["marimekko"]
    barmekko_spec = specs["barmekko"]
    stacked_bar_spec = specs["stacked_bar"]
    source_functions = legacy_charting._legacy_source_functions(marimekko_spec)
    names = get_naming_params()
    marimekko_chart = legacy_charting._legacy_chart_dict(
        names,
        marimekko_spec,
        metric="Sales",
        currency="EUR",
    )
    barmekko_chart = legacy_charting._legacy_chart_dict(
        names,
        barmekko_spec,
        metric="Sales",
        currency="EUR",
    )
    stacked_bar_chart = legacy_charting._legacy_chart_dict(
        names,
        stacked_bar_spec,
        metric="Sales",
        currency="EUR",
    )

    assert marimekko_spec["plotter"] == "plot_mekko_charts"
    assert marimekko_spec["legacy_chart_key"] == "marimekkoChart"
    assert marimekko_spec["show_legend_mode"] == "inside"
    assert marimekko_spec["value_label_mode"] == "absolute"
    assert barmekko_spec["plotter"] == "plot_mekko_charts"
    assert barmekko_spec["legacy_chart_key"] == "barmekkoChart"
    assert barmekko_spec["show_legend_mode"] == "inside"
    assert barmekko_spec["value_label_mode"] == "absolute"
    assert stacked_bar_spec["show_legend_mode"] == "inside"
    assert "modules.charting.run_charting.run_charting" in source_functions
    assert "modules.charting.plot_charts.plot_mekko_charts" in source_functions
    assert (
        "modules.charting.prepare_charts."
        "group_by_dataset_for_marimekko_and_barmekko" in source_functions
    )
    assert (
        "modules.charting.draw_width_and_stacked_plots.draw_mekko_chart"
        in source_functions
    )
    assert marimekko_chart[names["chosenChart"]] == names["marimekkoChart"]
    assert marimekko_chart[names["showValuesAs"]] == names["absolute"]
    assert marimekko_chart[names["showLegend"]] == names["showLegendInBars"]
    assert marimekko_chart[names["colorpalette"]] == names["bainColorpalette"]
    assert barmekko_chart[names["chosenChart"]] == names["barmekkoChart"]
    assert barmekko_chart[names["showValuesAs"]] == names["absolute"]
    assert barmekko_chart[names["showLegend"]] == names["showLegendInBars"]
    assert barmekko_chart[names["sortAxis"]] == names["areaSort"]
    assert barmekko_chart[names["colorpalette"]] == names["bainColorpalette"]
    assert stacked_bar_chart[names["chosenChart"]] == names["stackedBarChart"]
    assert stacked_bar_chart[names["showLegend"]] == names["showLegendInBars"]
    assert stacked_bar_chart[names["colorpalette"]] == names["bainColorpalette"]


def test_mekko_specs_set_axis_limits_from_contribution_share() -> None:
    core = load_core()
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": sales,
                "Units": 1.0,
                "Company": company,
                "Channel": channel,
            }
            for company, sales in [
                ("Leader", 70.0),
                ("Runner-up", 29.0),
                ("Tail 1", 0.4),
                ("Tail 2", 0.3),
                ("Tail 3", 0.2),
                ("Tail 4", 0.1),
            ]
            for channel in ["Retail", "Online"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Company", "Channel"],
        },
        "options": {"max_chart_items": 12, "small_multiples": False},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    marimekko_spec = specs["marimekko"]
    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        marimekko_spec,
        metric="Sales",
        currency="EUR",
    )

    assert marimekko_spec["x_max_items"] == 2
    assert marimekko_spec["w_max_items"] == 2
    assert chart["X"][names["numberOfTop"]] == 2
    assert chart["W"][names["numberOfTop"]] == 2
    assert chart["X"][names["aggregateOtherItems"]] is True
    assert chart["W"][names["aggregateOtherItems"]] is True


def test_legacy_chart_dict_honors_axis_specific_top_counts() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy_charting._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "marimekkoChart",
            "x_dimension": "Company",
            "y_dimension": "Channel",
            "x_max_items": 3,
            "w_max_items": 2,
            "max_items": 12,
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
        },
        metric="Sales",
        currency="EUR",
    )

    assert chart["X"][names["numberOfTop"]] == 3
    assert chart["W"][names["numberOfTop"]] == 2
    assert chart["Y"][names["numberOfTop"]] == 12


def test_legacy_mekko_prepared_data_cache_reuses_grouped_frame() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["xAxisDimension"]: "Productline",
        names["yAxisDimension"]: "Region",
        names["smallMultiplesColumn"]: names["totalName"],
    }
    source = pl.DataFrame({"Productline": ["Bikes"], "Sales": [10.0]}).lazy()
    cache = legacy_charting.LegacyPreparedDataCache.empty()
    builder_calls = 0

    def builder(
        _df_copy: pl.DataFrame | pl.LazyFrame,
        _column: str,
        _small_multiples_column_array: list[str],
        _value_cols: list[str],
        _chart_dict: dict[str, Any],
    ) -> pl.LazyFrame:
        nonlocal builder_calls
        builder_calls += 1
        return source

    first = cache.get_mekko_grouped_frame(
        names,
        names["totalName"],
        [names["totalName"]],
        ["Sales"],
        chart,
        builder,
        source,
    )
    second = cache.get_mekko_grouped_frame(
        names,
        names["totalName"],
        [names["totalName"]],
        ["Sales"],
        chart,
        builder,
        source,
    )

    assert builder_calls == 0
    assert cache.misses == 1
    assert cache.hits == 1
    assert cache.base_misses == 1
    assert first.collect().equals(second.collect())


def test_legacy_mekko_prepared_data_cache_reuses_base_for_related_charts() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    total_name = names["totalName"]
    source = pl.DataFrame(
        {
            names["periodName"]: ["AC", "AC", "AC", "AC"],
            total_name: [total_name, total_name, total_name, total_name],
            "Productline": ["Bikes", "Bikes", "Accessories", "Accessories"],
            "Region": ["North", "South", "North", "South"],
            "Channel": ["Online", "Retail", "Online", "Retail"],
            "Sales": [10.0, 20.0, 30.0, 40.0],
        }
    ).lazy()
    normal_chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["xAxisDimension"]: "Productline",
        names["yAxisDimension"]: "Region",
        names["smallMultiplesColumn"]: total_name,
    }
    small_multiple_chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["xAxisDimension"]: "Productline",
        names["yAxisDimension"]: "Region",
        names["smallMultiplesColumn"]: "Channel",
    }
    cache = legacy_charting.LegacyPreparedDataCache.empty()

    def fallback_builder(*_args: Any, **_kwargs: Any) -> pl.LazyFrame:
        raise AssertionError("cache should derive grouped data from the shared base")

    normal = cache.get_mekko_grouped_frame(
        names,
        total_name,
        [total_name],
        ["Sales"],
        normal_chart,
        fallback_builder,
        source,
        ["Productline", "Region", "Channel"],
    )
    small_multiple = cache.get_mekko_grouped_frame(
        names,
        "Channel",
        ["Channel"],
        ["Sales"],
        small_multiple_chart,
        fallback_builder,
        source,
        ["Productline", "Region", "Channel"],
    )

    assert normal.collect().height == 4
    assert small_multiple.collect().height == 4
    assert cache.base_misses == 1
    assert cache.base_hits == 1
    assert cache.misses == 2
    assert cache.hits == 0


def test_legacy_marimekko_annotations_match_pdf_layout() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()
    chart_helpers = load_vendor_chart_helpers()

    import plotly.graph_objects as go

    from modules.charting.draw_charts_utils import add_totals_below
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["yAxisDimension"]: "Color",
        names["plotValuesAsChoice"]: names["absolute"],
        names["valuePrefixName"]: "",
    }
    frame = pl.DataFrame(
        {
            names["periodName"]: ["AC", "AC"],
            names["valueName"]: [30.0, 30.0],
            "Sales": [30.0, 30.0],
            "Permanent": [2.0 / 3.0, 2.0 / 3.0],
            "Tone On Tone": [1.0 / 3.0, 1.0 / 3.0],
        }
    )
    cumulative = pl.DataFrame({"Permanent": [20.0], "Tone On Tone": [25.0]})

    figure = add_totals_below(
        go.Figure(),
        names["marimekkoChart"],
        frame,
        cumulative,
        ["Permanent", "Tone On Tone"],
        "Permanent",
        0,
        60,
        chart,
        None,
        None,
    )
    total_annotation = figure.layout.annotations[-1]

    assert "Permanent" not in total_annotation.text
    assert total_annotation.text == "40.0<BR>(67%)"

    figure = chart_helpers.show_total_percent(
        figure, frame, frame, "AC", "Sales", chart
    )
    percent_annotation = figure.layout.annotations[-1]

    assert percent_annotation.text == "100%"
    assert percent_annotation.x == 1
    assert percent_annotation.y == 1
    assert percent_annotation.xref == "x"
    assert percent_annotation.yref == "paper"
    assert percent_annotation.ax == 0
    assert percent_annotation.ay == -40
    assert percent_annotation.axref == "pixel"
    assert percent_annotation.ayref == "pixel"


def test_legacy_total_percent_marker_uses_mekko_data_right_edge() -> None:
    chart_helpers = load_vendor_chart_helpers()

    import plotly.graph_objects as go

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    figure = go.Figure()
    figure.update_layout(xaxis={"domain": [0.12, 0.82]})
    chart = {
        names["yAxisDimension"]: "Company",
        names["nothingFilteredName"]: names["nothingFilteredName"],
    }
    frame = pl.DataFrame(
        {
            "Period": ["AC"],
            "Company": ["A"],
            "Sales": [10.0],
            names["valueName"]: [10.0],
        }
    )

    figure = chart_helpers.show_total_percent(
        figure, frame, frame, "AC", "Sales", chart
    )

    percent_annotation = figure.layout.annotations[-1]
    assert percent_annotation.text == "100%"
    assert percent_annotation.x == 1
    assert percent_annotation.xref == "x"
    assert percent_annotation.yref == "paper"
    assert percent_annotation.axref == "pixel"
    assert percent_annotation.ayref == "pixel"


def test_legacy_marimekko_inside_labels_use_line_break() -> None:
    legacy_charting = load_legacy_charting()
    legacy_charting._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        set_marimekko_params_and_add_trace,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    figure = go.Figure()
    chart = {
        names["chosenChart"]: names["marimekkoChart"],
        names["showLegend"]: names["showLegendInBars"],
        names["plotSmallMultiplesOtherCharts"]: False,
        names["valuePrefixName"]: "",
    }
    frame = pl.DataFrame(
        {
            "Company": ["Leader"],
            names["valueName"]: [100.0],
            "Mexico City": [80.0],
        }
    )

    set_marimekko_params_and_add_trace(
        figure,
        {},
        frame,
        "Mexico City",
        "#123456",
        names["valueName"],
        chart,
        names["absolute"],
        ["Leader"],
    )

    assert str(figure.data[0].text[0]).startswith("Mexico City<br>")


def test_mekko_small_multiple_specs_require_pairwise_independent_dimension_triple() -> (
    None
):
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Units": 2,
                "Productline": productline,
                "Category": category,
                "Region": region,
                "Channel": channel,
            }
            for productline, categories in {
                "Bikes": ["Road", "Mountain"],
                "Accessories": ["Helmets", "Bottles"],
            }.items()
            for category in categories
            for region in ["North", "South"]
            for channel in ["Online", "Retail"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Category", "Region", "Channel"],
        },
        "options": {"small_multiples": True, "small_multiples_max_panels": 6},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["marimekko"]["x_dimension"] == "Productline"
    assert specs["marimekko"]["y_dimension"] == "Region"
    assert specs["marimekko_small_multiples"]["x_dimension"] == "Productline"
    assert specs["marimekko_small_multiples"]["y_dimension"] == "Region"
    assert specs["marimekko_small_multiples"]["small_multiples_dimension"] == "Channel"


def test_stacked_bar_small_multiple_specs_keep_balanced_panel_facets() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Productline": productline,
                "Region": region,
                "Channel": channel,
            }
            for productline in ["Bikes", "Accessories"]
            for region in ["North", "South"]
            for channel in ["Online", "Retail"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Region", "Channel"],
        },
        "options": {"small_multiples": True, "small_multiples_max_panels": 4},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "stacked_bar_small_multiples" in specs
    assert (
        specs["stacked_bar_small_multiples"]["small_multiples_dimension"] == "Channel"
    )


def test_stacked_bar_small_multiple_specs_reject_nested_one_row_facets() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": sales,
                "Channel": channel,
                "Company": company,
                "Brand": brand,
            }
            for company, brands in {
                "L'Oreal": ["Excellence", "Nutrisse"],
                "Coty": ["Koleston", "Miss Clairol"],
            }.items()
            for brand in brands
            for channel, sales in [("Mexico City", 10.0), ("Monterrey", 4.0)]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Company", "Channel", "Brand"],
        },
        "options": {
            "small_multiples": True,
            "small_multiples_dimension": "Brand",
            "small_multiples_max_panels": 4,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "stacked_bar" in specs
    assert "stacked_bar_small_multiples" not in specs


def test_stacked_bar_small_multiple_specs_allow_dominant_panel_facets() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": scale,
                "Company": company,
                "Channel": channel,
                "Type": type_name,
            }
            for type_name, scale in [
                ("Permanent", 1_000.0),
                ("Tone On Tone", 40.0),
                ("Semi-Permanent", 20.0),
            ]
            for company in ["L'Oreal", "Coty"]
            for channel in ["Mexico City", "Monterrey"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Company", "Channel", "Type"],
        },
        "options": {
            "small_multiples": True,
            "small_multiples_dimension": "Type",
            "small_multiples_max_panels": 4,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    small_spec = specs["stacked_bar_small_multiples"]
    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        small_spec,
        metric="Sales",
        currency="EUR",
    )

    assert "stacked_bar" in specs
    assert "stacked_bar_small_multiples" in specs
    assert small_spec["small_multiples_dimension"] == "Type"
    assert small_spec["capture_figure"] == "last"
    assert small_spec["show_top_for_each_item"] is True
    assert chart[names["showTopForEachItem"]] is True


def test_pareto_specs_use_additive_metrics_and_child_parent_dimensions() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Units": 2.0,
                "Productline": productline,
                "Category": category,
                "Region": region,
            }
            for productline, categories in {
                "Bikes": ["Road", "Mountain"],
                "Accessories": ["Helmets"],
            }.items()
            for category in categories
            for region in ["North", "South"]
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Category", "Region"],
        },
        "options": {"small_multiples": False},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["pareto"]["x_dimension"] == "Category"
    assert specs["pareto"]["y_dimension"] is None
    assert specs["pareto"]["metrics"] == ["Sales", "Units"]
    assert specs["pareto"]["show_absolute_values"] is False
    assert specs["pareto"]["show_rank"] is True
    assert specs["pareto"]["show_only"] == "All"
    assert specs["stacked_pareto_abc"]["x_dimension"] == "Category"
    assert specs["stacked_pareto_abc"]["y_dimension"] is None
    assert specs["stacked_pareto_abc"]["count_dimension"] == "Category"
    assert specs["stacked_pareto_abc"]["aggregate_uniques_by_dimension"] is False
    assert specs["stacked_pareto_abc"]["stacked_pareto_mode"] == "abc_classes"
    assert specs["stacked_pareto_abc"]["metrics"] == ["Sales", "Units"]
    assert specs["stacked_pareto_by_dimension"]["x_dimension"] == "Category"
    assert specs["stacked_pareto_by_dimension"]["y_dimension"] == "Productline"
    assert specs["stacked_pareto_by_dimension"]["count_dimension"] == "Category"
    assert (
        specs["stacked_pareto_by_dimension"]["aggregate_uniques_dimension"]
        == "Productline"
    )
    assert (
        specs["stacked_pareto_by_dimension"]["aggregate_uniques_by_dimension"] is True
    )
    assert specs["stacked_pareto_by_dimension"]["aggregate_other_items"] is True
    assert (
        specs["stacked_pareto_by_dimension"]["stacked_pareto_mode"]
        == "aggregate_by_dimension"
    )
    assert specs["stacked_pareto_by_dimension"]["metrics"] == ["Sales", "Units"]
    assert specs["stacked_pareto_by_dimension"]["dimension_selection"] == (
        "bounded_observed_child_parent_dimension_pair"
    )
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names, specs["pareto"], metric="Sales", currency="EUR"
    )

    assert chart[names["metricsToPlot"]] == ["Sales", "Units"]
    assert chart[names["countColumn"]] == "Category"
    assert chart[names["aggregateUniquesByDimension"]] is False
    assert chart[names["showAbsoluteValues"]] is False
    assert chart[names["showRank"]] is True
    assert chart[names["showOnly"]] == names["showAll"]
    abc_chart = legacy._legacy_chart_dict(
        names, specs["stacked_pareto_abc"], metric="Sales", currency="EUR"
    )
    by_dimension_chart = legacy._legacy_chart_dict(
        names, specs["stacked_pareto_by_dimension"], metric="Sales", currency="EUR"
    )

    assert abc_chart[names["countColumn"]] == "Category"
    assert abc_chart[names["yAxisDimension"]] == "Category"
    assert abc_chart[names["aggregateUniquesByDimension"]] is False
    assert by_dimension_chart[names["countColumn"]] == "Category"
    assert by_dimension_chart[names["aggregateUniquesByDimension"]] is True
    assert by_dimension_chart[names["aggregateUniquesDimension"]] == "Productline"


def test_pareto_show_only_option_supports_top_items_mode() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": sales,
                "Units": units,
                "Product": product,
                "Company": company,
            }
            for product, company, sales, units in (
                ("A", "One", 10.0, 1.0),
                ("B", "One", 5.0, 1.0),
                ("C", "Two", 3.0, 1.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Product", "Company"],
        },
        "options": {"pareto_show_only": "top"},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["pareto"]["show_only"] == "Top"
    assert specs["pareto"]["show_rank"] is False

    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names, specs["pareto"], metric="Sales", currency="EUR"
    )

    assert chart[names["showOnly"]] == names["showTop"]
    assert chart[names["showRank"]] is False


def test_stacked_pareto_prefers_bounded_hierarchy_over_granular_pareto() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": 10.0,
                "Units": 2.0,
                "Company": f"Company {brand_index % 3}",
                "Brand": f"Brand {brand_index}",
                "Product": f"Product {brand_index}-{product_index}",
            }
            for brand_index in range(12)
            for product_index in range(10)
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Company", "Brand", "Product"],
        },
        "options": {"small_multiples": False},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["pareto"]["x_dimension"] == "Product"
    assert specs["stacked_pareto_abc"]["x_dimension"] == "Brand"
    assert specs["stacked_pareto_by_dimension"]["x_dimension"] == "Brand"
    assert specs["stacked_pareto_by_dimension"]["y_dimension"] == "Company"
    assert specs["stacked_pareto_by_dimension"]["count_dimension"] == "Brand"


def test_area_specs_aggregate_fragmented_population_more_aggressively() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    canonical = pl.DataFrame(
        [
            {
                "Date": date(2025, 1 + (index % 2), 28),
                "Period": "AC",
                "Sales": float(100 - index),
                "Company": f"Company {index}",
                "Channel": channel,
            }
            for index in range(10)
            for channel in ("Retail", "Online")
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Channel"],
        },
        "options": {"max_chart_items": 12, "small_multiples": False},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    names = get_naming_params()
    area_chart = legacy._legacy_chart_dict(
        names,
        specs["area_absolute"],
        metric="Sales",
        currency="EUR",
    )

    assert specs["stacked_bar"]["max_items"] == 12
    assert specs["stacked_column"]["max_items"] == 6
    assert specs["area_absolute"]["max_items"] == 6
    assert specs["area_share"]["max_items"] == 6
    assert specs["area_absolute"]["dimension_selection"] == (
        "ranked_area_with_fragmentation_other"
    )
    assert area_chart["X"][names["numberOfTop"]] == 6
    assert area_chart["X"][names["aggregateOtherItems"]] is True


def test_time_chart_specs_use_full_date_window_for_date_periods() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date.fromisoformat(period),
                "Period": period,
                "Sales": value,
                "Company": company,
            }
            for period, value in (
                ("2025-01-05", 10.0),
                ("2025-02-02", 20.0),
                ("2025-03-02", 30.0),
            )
            for company in ("A", "B")
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company"],
        },
        "options": {
            "current_period_label": "2025-03-02",
            "charts": ["area_absolute", "line"],
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["area_absolute"]["selected_periods"] == [
        "2025-01-05",
        "2025-02-02",
        "2025-03-02",
    ]
    assert specs["line"]["selected_periods"] == [
        "2025-01-05",
        "2025-02-02",
        "2025-03-02",
    ]


def test_time_chart_specs_are_rejected_when_resolved_to_one_date() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date(2025, 3, 2),
                "Period": "AC",
                "Sales": value,
                "Company": company,
            }
            for value, company in ((10.0, "A"), (20.0, "B"))
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Period",
            "amount_column": "Sales",
            "dimensions": ["Company"],
        },
        "options": {"charts": ["area_absolute", "area_share", "line"]},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "area_absolute" not in specs
    assert "area_share" not in specs
    assert "line" not in specs


def test_related_metrics_bar_specs_use_legacy_overlay_charting() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value,
                "Units": units,
                "Productline": productline,
                "Region": region,
                "Channel": channel,
            }
            for period, period_scale in (("PY", 0.8), ("AC", 1.0))
            for productline, value, units in (
                ("Bikes", 100.0 * period_scale, 10.0 * period_scale),
                ("Accessories", 40.0 * period_scale, 5.0 * period_scale),
            )
            for region in ("North", "South")
            for channel in ("Online", "Retail")
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Region", "Channel"],
        },
        "options": {
            "small_multiples": True,
            "small_multiples_max_panels": 4,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    bar_spec = specs["bar"]
    bar_small_spec = specs["bar_small_multiples"]
    spec = specs["related_metrics_bar"]
    small_spec = specs["related_metrics_bar_small_multiples"]
    bar_small_source_functions = legacy._legacy_source_functions(bar_small_spec)
    source_functions = legacy._legacy_source_functions(small_spec)
    names = get_naming_params()
    bar_chart = legacy._legacy_chart_dict(
        names,
        bar_spec,
        metric="Sales",
        currency="EUR",
    )
    bar_small_chart = legacy._legacy_chart_dict(
        names,
        bar_small_spec,
        metric="Sales",
        currency="EUR",
    )
    chart = legacy._legacy_chart_dict(
        names,
        spec,
        metric="Sales",
        currency="EUR",
    )

    assert bar_spec["plotter"] == "plot_stacked_bar_charts"
    assert bar_spec["legacy_chart_key"] == "stackedBarChart"
    assert bar_spec["metrics"] == ["Sales"]
    assert bar_spec["dimensions"] == ["Productline"]
    assert bar_spec["x_dimension"] == "Productline"
    assert bar_spec["y_dimension"] is None
    assert bar_spec["selected_periods"] == ["PY", "AC"]
    assert bar_spec["capture_chart_data"] is True
    assert bar_spec["show_average_value"] is True
    assert "plot_overlay_chart" not in bar_spec
    assert bar_chart[names["metricsToPlot"]] == ["Sales"]
    assert bar_chart[names["plotOverlayChart"]] is False
    assert bar_chart[names["showAverageValueName"]] is True
    assert bar_chart[names["xAxisDimension"]] == "Productline"
    assert bar_chart[names["yAxisDimension"]] == names["nothingFilteredName"]
    assert bar_small_spec["base_chart"] == "bar"
    assert bar_small_spec["metrics"] == ["Sales"]
    assert bar_small_spec["dimensions"] == ["Productline", "Region"]
    assert bar_small_spec["x_dimension"] == "Productline"
    assert bar_small_spec["y_dimension"] is None
    assert bar_small_spec["small_multiples_dimension"] == "Region"
    assert bar_small_spec["capture_figure"] == "last"
    assert "plot_overlay_chart" not in bar_small_spec
    assert bar_small_chart[names["metricsToPlot"]] == ["Sales"]
    assert bar_small_chart[names["plotOverlayChart"]] is False
    assert bar_small_chart[names["smallMultiplesColumn"]] == "Region"
    assert spec["plotter"] == "plot_stacked_bar_charts"
    assert spec["legacy_chart_key"] == "stackedBarChart"
    assert spec["metrics"] == ["Sales", "Sales Growth Rate"]
    assert spec["value_cols"] == ["Sales"]
    assert spec["plot_overlay_chart"] is True
    assert spec["show_average_value"] is True
    assert small_spec["base_chart"] == "related_metrics_bar"
    assert small_spec["small_multiples_dimension"] == "Region"
    assert small_spec["plot_overlay_chart"] is True
    assert small_spec["capture_figure"] == "last"
    assert chart[names["metricsToPlot"]] == ["Sales", "Sales Growth Rate"]
    assert chart[names["plotOverlayChart"]] is True
    assert chart[names["showAverageValueName"]] is True
    assert names["xAxisMetric"] not in chart
    assert names["yAxisMetric"] not in chart
    assert names["singleMetric"] not in chart
    assert chart[names["xAxisDimension"]] == "Productline"
    assert chart[names["yAxisDimension"]] == names["nothingFilteredName"]
    assert (
        "modules.charting.draw_width_and_stacked_plots."
        "draw_stacked_bar_small_multiples" in bar_small_source_functions
    )
    assert (
        "modules.data.multidimensional_charts_prep."
        "prepare_small_multiples_dataframe_for_stacked_bar"
        in bar_small_source_functions
    )
    assert (
        "modules.data.multidimensional_charts_prep."
        "prepare_overlay_data_for_stacked_bar" in source_functions
    )
    assert "modules.charting.draw_charts_utils.add_overlay_trace" in source_functions
    assert (
        "modules.charting.draw_width_and_stacked_plots."
        "draw_stacked_bar_small_multiples" in source_functions
    )


def test_related_metrics_bar_can_use_explicit_marker_metric() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-02-28"],
            "Comparison": ["~Yn-1", "~Y"],
            "Distribution_m": [7.85, 5.12],
            "Sales_mCHF": [162.0, 165.0],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Distribution_m",
            "related_marker_metric_column": "Sales_mCHF",
            "dimensions": ["Comparison"],
        },
        "options": {"small_multiples": False},
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, audit = core.prepare_canonical_frame(frame, validated)
    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    canonical_columns, _schema = core.get_schema_and_column_names(canonical)

    assert audit["related_marker_metric_column"] == "Sales_mCHF"
    assert canonical_columns == ["Date", "Period", "Sales", "Sales_mCHF", "Comparison"]
    assert specs["related_metrics_bar"]["metrics"] == ["Sales", "Sales_mCHF"]
    assert specs["related_metrics_bar"]["value_cols"] == ["Sales", "Sales_mCHF"]


def test_mix_recipe_infers_margin_metrics_as_measures_not_dimensions() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-02-28"],
            "Scenario": ["AC", "AC"],
            "Salesamount": [100.0, 120.0],
            "Units": [10.0, 12.0],
            "Gross Margin": [30.0, 36.0],
            "Margin %": [30.0, 30.0],
            "Brand": ["A", "B"],
        }
    )

    recipe = core.build_recipe(Path("sales.csv"), frame, language="en")
    mappings = recipe["mappings"]

    assert mappings["amount_column"] == "Salesamount"
    assert mappings["width_metric_column"] == "Units"
    assert mappings["margin_column"] == "Gross Margin"
    assert mappings["margin_percent_column"] == "Margin %"
    assert "Gross Margin" not in mappings["dimensions"]
    assert "Margin %" not in mappings["dimensions"]
    assert "Brand" in mappings["dimensions"]


def test_prepare_canonical_frame_derives_price_and_margin_percent() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-02-28"],
            "Scenario": ["AC", "AC"],
            "Salesamount": [100.0, 120.0],
            "Units": [10.0, 12.0],
            "Gross Margin": [30.0, 24.0],
            "Brand": ["A", "B"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Scenario",
            "amount_column": "Salesamount",
            "width_metric_column": "Units",
            "margin_column": "Gross Margin",
            "dimensions": ["Brand"],
        },
        "options": {"current_period_label": "AC", "small_multiples": False},
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, audit = core.prepare_canonical_frame(frame, validated)

    assert audit["legacy_metric_columns"] == [
        "Sales",
        "Units",
        "Unit Price",
        "Units x Unit Price",
        "Margin",
        "Margin in %",
    ]
    assert audit["source_margin_column"] == "Gross Margin"
    assert audit["legacy_margin_column"] == "Margin"
    assert audit["legacy_margin_percent_column"] == "Margin in %"
    assert canonical.select("Unit Price").to_series().to_list() == [10.0, 10.0]
    assert canonical.select("Margin").to_series().to_list() == [30.0, 24.0]
    assert canonical.select("Margin in %").to_series().to_list() == [0.3, 0.2]


def test_prepare_canonical_frame_normalizes_existing_margin_percent() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-02-28"],
            "Scenario": ["AC", "AC"],
            "Salesamount": [100.0, 120.0],
            "Margin %": [30.0, 0.2],
            "Brand": ["A", "B"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Scenario",
            "amount_column": "Salesamount",
            "margin_percent_column": "Margin %",
            "dimensions": ["Brand"],
        },
        "options": {"current_period_label": "AC", "small_multiples": False},
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, audit = core.prepare_canonical_frame(frame, validated)

    assert audit["source_margin_percent_column"] == "Margin %"
    assert audit["legacy_margin_percent_column"] == "Margin in %"
    assert canonical.select("Margin in %").to_series().to_list() == [0.3, 0.2]


def test_related_metrics_default_to_derived_unit_price_for_single_period() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-01-31"],
            "Scenario": ["AC", "AC"],
            "Salesamount": [100.0, 80.0],
            "Units": [10.0, 20.0],
            "Brand": ["A", "B"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Scenario",
            "amount_column": "Salesamount",
            "width_metric_column": "Units",
            "dimensions": ["Brand"],
        },
        "options": {
            "charts": ["related_metrics_bar"],
            "current_period_label": "AC",
            "small_multiples": False,
        },
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, _audit = core.prepare_canonical_frame(frame, validated)
    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["related_metrics_bar"]["metrics"] == ["Sales", "Unit Price"]
    assert specs["related_metrics_bar"]["value_cols"] == ["Sales", "Units"]


def test_related_metrics_default_to_margin_percent_when_price_is_unavailable() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2025-01-31", "2025-01-31"],
            "Scenario": ["AC", "AC"],
            "Salesamount": [100.0, 80.0],
            "Gross Margin": [25.0, 16.0],
            "Brand": ["A", "B"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Scenario",
            "amount_column": "Salesamount",
            "margin_column": "Gross Margin",
            "dimensions": ["Brand"],
        },
        "options": {
            "charts": ["related_metrics_bar"],
            "current_period_label": "AC",
            "small_multiples": False,
        },
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, _audit = core.prepare_canonical_frame(frame, validated)
    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["related_metrics_bar"]["metrics"] == ["Sales", "Margin in %"]
    assert specs["related_metrics_bar"]["value_cols"] == ["Sales", "Margin"]


def test_legacy_stacked_bar_average_row_uses_existing_other_guard() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        prepare_data_for_stacked_bar_one_dimension,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC", "PY", "PY", "PY"],
            "Brand": ["A", "B", "C", "A", "B", "C"],
            "Sales": [12.0, 24.0, 36.0, 10.0, 20.0, 30.0],
        }
    )

    def prepared_frame(max_items: int) -> tuple[dict[str, Any], pl.DataFrame]:
        chart = legacy._legacy_chart_dict(
            names,
            {
                "legacy_chart_key": "stackedBarChart",
                "dimensions": ["Brand"],
                "x_dimension": "Brand",
                "y_dimension": None,
                "metrics": ["Sales"],
                "selected_periods": ["PY", "AC"],
                "max_items": max_items,
                "show_average_value": True,
            },
            metric="Sales",
            currency="EUR",
        )
        output, _metric, _colors, _used_colors, _unique_items = (
            prepare_data_for_stacked_bar_one_dimension(
                frame,
                names["totalName"],
                ["Sales"],
                chart,
                {},
                {},
                [],
                names["stackedBarChart"],
            )
        )
        return chart, output.collect()

    chart, no_other = prepared_frame(max_items=12)
    other_chart, with_other = prepared_frame(max_items=2)

    no_other_labels = no_other.get_column("Brand").to_list()
    with_other_labels = with_other.get_column("Brand").to_list()

    assert chart[names["showAverageValueName"]] is True
    assert no_other_labels[:2] == ["Average", None]
    assert no_other.row(0, named=True)["Sales"] == pytest.approx(24.0)
    assert other_chart[names["showAverageValueName"]] is False
    assert "Average" not in with_other_labels
    assert "Others rank >2" in with_other_labels


def test_mix_recipe_rejects_same_current_and_comparison_period_labels() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Scenario": ["AC", "PY"],
            "Salesamount": [100.0, 80.0],
            "Productline": ["Bikes", "Bikes"],
        }
    )
    recipe = {
        "mappings": {
            "period_column": "Scenario",
            "amount_column": "Salesamount",
            "dimensions": ["Productline"],
        },
        "options": {
            "current_period_label": "AC",
            "previous_period_label": "AC",
        },
    }

    with pytest.raises(ValueError, match="requires distinct current and comparison"):
        core.validate_recipe(frame, recipe)


def test_column_family_specs_use_legacy_stacked_column_renderer() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value * scale,
                "Company": company,
                "Brand": brand,
            }
            for period, scale in (("PY", 0.9), ("AC", 1.0))
            for company, brand, value in (
                ("A", "Main", 100.0),
                ("B", "Other", 40.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Company", "Brand"],
        },
        "options": {
            "charts": [
                "column_total",
                "stacked_column",
                "stacked_column_with_cagr",
                "stacked_column_synthesis",
            ],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": False,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    for chart_name in ("column_total", "stacked_column", "stacked_column_synthesis"):
        assert specs[chart_name]["plotter"] == "plot_stacked_column_charts"
        assert specs[chart_name]["legacy_chart_key"] == "stackedColumnChart"
    assert specs["column_total"]["dimensions"] == ["Total View"]
    assert specs["column_total"]["x_dimension"] == "Total View"
    assert specs["column_total"]["total_column_label"] == "Total"
    assert specs["column_total"]["show_cagr"] is True
    assert specs["stacked_column"]["dimensions"] == ["Company"]
    assert specs["stacked_column"]["x_dimension"] == "Company"
    assert specs["stacked_column"]["max_items"] == 6
    assert specs["stacked_column"]["show_cagr"] is True
    assert specs["stacked_column"]["show_total_cagr"] is True
    assert specs["stacked_column"]["suppress_stacked_percentage_annotations"] is True
    assert specs["stacked_column"]["format_stacked_value_labels_like_totals"] is True
    assert "stacked_column_with_cagr" not in specs
    assert specs["stacked_column_synthesis"]["synthesis_plot"] is True


def test_default_recipe_uses_canonical_stacked_column_render_variant() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2024-01-31", "2025-01-31"],
            "Sales": [100.0, 110.0],
            "Company": ["A", "A"],
            "Brand": ["Main", "Main"],
        }
    )

    recipe = core.build_recipe(Path("sales.csv"), frame, language="en")

    assert "stacked_column" in recipe["options"]["charts"]
    assert "stacked_column_with_cagr" not in recipe["options"]["charts"]


def test_cagr_annotation_is_not_enabled_for_rate_metrics() -> None:
    core = load_core()

    assert core._metric_supports_cagr("Sales") is True
    assert core._metric_supports_cagr("Units") is True
    assert core._metric_supports_cagr("Unit Price") is False
    assert core._metric_supports_cagr("Sales Growth Rate") is False
    assert core._metric_supports_cagr("CWD") is False


def test_cagr_annotation_is_not_enabled_for_single_period_columns() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": value,
                "Units": units,
                "Company": company,
            }
            for company, value, units in (
                ("A", 100.0, 10.0),
                ("B", 40.0, 4.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "related_marker_metric_column": "Units",
            "dimensions": ["Company"],
        },
        "options": {
            "charts": [
                "column_total",
                "column_total_with_overlay",
                "stacked_column",
            ],
            "current_period_label": "AC",
            "small_multiples": False,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["column_total"]["selected_periods"] == ["AC"]
    assert specs["column_total"]["show_cagr"] is False
    assert specs["column_total_with_overlay"]["show_cagr"] is False
    assert specs["stacked_column"]["show_cagr"] is False


def test_actual_only_column_specs_use_date_year_axis() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Date": [
                date(2015, 8, 30),
                date(2016, 8, 28),
                date(2017, 8, 27),
            ],
            "Period": ["AC", "AC", "AC"],
            "Sales": [40.0, 100.0, 70.0],
            "Units": [4.0, 10.0, 7.0],
            "Company": ["A", "A", "A"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Period",
            "amount_column": "Sales",
            "related_marker_metric_column": "Units",
            "dimensions": ["Company"],
        },
        "options": {
            "charts": [
                "column_total",
                "column_total_with_overlay",
                "stacked_column",
            ],
            "current_period_label": "AC",
            "small_multiples": False,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    for chart_name in (
        "column_total",
        "column_total_with_overlay",
        "stacked_column",
    ):
        assert specs[chart_name]["period_grain"] == "year"
        assert specs[chart_name]["period_selection_mode"] == "all_periods_at_grain"
        assert specs[chart_name]["selected_periods"] == ["2015", "2016", "2017"]
        assert specs[chart_name]["show_cagr"] is True


def test_multitier_bar_specs_require_comparison_periods() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": "AC",
                "Sales": value,
                "Company": company,
                "Brand": brand,
                "Channel": channel,
            }
            for company, brand, channel, value in (
                ("A", "Main", "Retail", 100.0),
                ("B", "Second", "Online", 40.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Company", "Brand", "Channel"],
        },
        "options": {
            "charts": ["multitier_bar", "multitier_bar_dimension_panels"],
            "current_period_label": "AC",
            "small_multiples": True,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "multitier_bar" not in specs
    assert "multitier_bar_dimension_panels" not in specs


def test_multitier_bar_specs_keep_quarter_to_date_option() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value,
                "Company": company,
                "Brand": brand,
                "Channel": channel,
            }
            for period, scale in (("PY", 0.9), ("AC", 1.0))
            for company, brand, channel, value in (
                ("A", "Main", "Retail", 100.0 * scale),
                ("B", "Second", "Online", 40.0 * scale),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Company", "Brand", "Channel"],
        },
        "options": {
            "charts": ["multitier_bar"],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "period_grain": "quarter",
            "period_to_date": True,
            "small_multiples": True,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["multitier_bar"]["period_grain"] == "quarter"
    assert specs["multitier_bar"]["period_to_date"] is True
    assert specs["multitier_bar_dimension_panels"]["period_grain"] == "quarter"
    assert specs["multitier_bar_dimension_panels"]["period_to_date"] is True


def test_multitier_dimension_panels_can_enable_other_bucket() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value * scale,
                "Company": company,
                "Brand": brand,
                "Channel": channel,
            }
            for period, scale in (("PY", 0.9), ("AC", 1.0))
            for company, brand, channel, value in (
                ("A", "Main", "Retail", 100.0),
                ("B", "Second", "Online", 80.0),
                ("C", "Third", "Salon", 60.0),
                ("D", "Fourth", "Retail", 40.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Company", "Brand", "Channel"],
        },
        "options": {
            "charts": ["multitier_bar"],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": True,
            "dimension_panel_max_items": 3,
            "dimension_panel_aggregate_other_items": True,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    dimension_panel_spec = specs["multitier_bar_dimension_panels"]
    assert dimension_panel_spec["x_max_items"] == 3
    assert dimension_panel_spec["aggregate_other_items"] is True


def test_multitier_bar_two_dimension_spec_uses_panel_and_item_dimensions() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value * scale,
                "Type": item_type,
                "Brand": brand,
                "Channel": channel,
            }
            for period, scale in (("PY", 0.9), ("AC", 1.0))
            for item_type, brand, channel, value in (
                ("Permanent", "Koleston", "Mexico City", 100.0),
                ("Permanent", "Nutrisse", "Monterrey", 80.0),
                ("Root", "Koleston", "Mexico City", 60.0),
                ("Root", "Excellence", "Guadalajara", 40.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Type", "Brand", "Channel"],
        },
        "options": {
            "charts": ["multitier_bar_two_dimension"],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": True,
            "multitier_bar_panel_dimension": "Type",
            "multitier_bar_item_dimension": "Brand",
            "multitier_bar_item_max_items": 4,
            "dimension_display_labels": {"Channel": "City"},
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    spec = specs["multitier_bar_two_dimension"]
    assert spec["dimensions"] == ["Type", "Brand"]
    assert spec["x_dimension"] == "Brand"
    assert spec["y_dimension"] is None
    assert spec["small_multiples_dimension"] == "Type"
    assert spec["x_max_items"] == 4
    assert spec["dimension_display_labels"] == {"Channel": "City"}
    assert spec["dimension_selection"] == (
        "panel_dimension_item_dimension_multitier_bar"
    )


def test_legacy_multitier_two_dimension_chart_dict_sets_panel_and_item_axes() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Type", "Brand"],
            "x_dimension": "Brand",
            "small_multiples_dimension": "Type",
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
        },
        metric="Sales",
        currency="EUR",
    )

    assert chart[names["plotSmallMultiplesOtherCharts"]] is True
    assert chart[names["smallMultiplesColumn"]] == "Type"
    assert chart[names["xAxisDimension"]] == "Brand"
    assert chart[names["selectDimensionsToPlot"]] == ["Type", "Brand"]


def test_legacy_multitier_two_dimension_index_order_honors_panel_dimension() -> None:
    legacy = load_legacy_charting()
    recipe = {"mappings": {"dimensions": ["Company", "Brand", "Channel"]}}
    spec = {
        "dimensions": ["Channel", "Brand"],
        "x_dimension": "Brand",
        "small_multiples_dimension": "Channel",
        "dimension_selection": "panel_dimension_item_dimension_multitier_bar",
    }

    dimensions = legacy._legacy_index_dimensions(recipe, spec)

    assert dimensions[:3] == ["Channel", "Brand", "Company"]


def test_legacy_multitier_two_dimension_title_lists_item_then_panel() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.make_titles import make_multitier_bar_chart_title
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Type", "Brand"],
            "x_dimension": "Brand",
            "small_multiples_dimension": "Type",
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame({"Brand": ["Koleston"], "PY": [90.0], "AC": [100.0]})

    title, _param, chart = make_multitier_bar_chart_title(
        frame,
        chart[names["chosenChart"]],
        {},
        "Brand",
        "Sales",
        chart,
        "PY",
        "AC",
    )

    assert "by Brand and Type" in title
    assert "Type by Brand" not in title
    assert chart[names["plotTitleText"]] == title


def test_legacy_multitier_two_dimension_title_uses_dimension_display_labels() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.make_titles import make_multitier_bar_chart_title
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Channel", "Brand"],
            "x_dimension": "Brand",
            "small_multiples_dimension": "Channel",
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
            "dimension_display_labels": {"Channel": "City"},
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame({"Brand": ["Koleston"], "PY": [90.0], "AC": [100.0]})

    title, _param, chart = make_multitier_bar_chart_title(
        frame,
        chart[names["chosenChart"]],
        {},
        "Brand",
        "Sales",
        chart,
        "PY",
        "AC",
    )

    assert "by Brand and City" in title
    assert "Channel by Brand" not in title
    assert chart[names["plotTitleText"]] == title


def test_column_overlay_specs_use_legacy_stacked_column_renderer() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value * scale,
                "Units": units * scale,
                "Company": company,
            }
            for period, scale in (("PY", 0.9), ("AC", 1.0))
            for company, value, units in (
                ("A", 100.0, 10.0),
                ("B", 40.0, 4.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "related_marker_metric_column": "Units",
            "dimensions": ["Company"],
        },
        "options": {
            "charts": [
                "column_total_with_overlay",
                "stacked_column_with_overlay",
            ],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": False,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    spec = specs["column_total_with_overlay"]
    assert spec["plotter"] == "plot_stacked_column_charts"
    assert spec["legacy_chart_key"] == "stackedColumnChart"
    assert spec["base_chart"] == "column_total"
    assert spec["metrics"] == ["Sales", "Units"]
    assert spec["value_cols"] == ["Sales", "Units"]
    assert spec["plot_overlay_chart"] is True
    assert spec["highlight_overlay_chart"] is True
    assert spec["show_cagr"] is True
    assert "stacked_column_with_overlay" not in specs


def test_column_aliases_resolve_to_legacy_total_column_specs() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["PY", "AC"],
            "Sales": [10.0, 12.0],
            "Units": [5.0, 6.0],
            "Company": ["A", "A"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "related_marker_metric_column": "Units",
            "dimensions": ["Company"],
        },
        "options": {
            "charts": [
                "simple_column",
                "column",
                "column_plus_marker",
                "column_with_marker",
            ],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": False,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert list(specs) == ["column_total", "column_total_with_overlay"]
    assert specs["column_total"]["plotter"] == "plot_stacked_column_charts"
    assert specs["column_total"]["legacy_chart_key"] == "stackedColumnChart"
    assert specs["column_total"]["dimensions"] == ["Total View"]
    assert specs["column_total_with_overlay"]["plotter"] == "plot_stacked_column_charts"
    assert (
        specs["column_total_with_overlay"]["legacy_chart_key"] == "stackedColumnChart"
    )
    assert specs["column_total_with_overlay"]["base_chart"] == "column_total"
    assert specs["column_total_with_overlay"]["plot_overlay_chart"] is True
    assert specs["column_total_with_overlay"]["highlight_overlay_chart"] is True


def test_like_for_like_column_specs_use_population_prepared_column_grammar() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY"],
            "Sales": [10.0, 12.0, 5.0, 7.0],
            "Productline": ["Common", "Common", "New", "Lost"],
            "Company": ["A", "A", "A", "A"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Productline", "Company"],
        },
        "options": {
            "charts": [
                "like_for_like_column_total",
                "like_for_like_stacked_column",
            ],
            "current_period_label": "AC",
            "previous_period_label": "PY",
            "small_multiples": False,
            "like_for_like": {"source_dimension": "Productline"},
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert set(specs) == {
        "like_for_like_column_total",
        "like_for_like_stacked_column",
    }
    for chart_name, base_chart in (
        ("like_for_like_column_total", "column_total"),
        ("like_for_like_stacked_column", "stacked_column"),
    ):
        assert specs[chart_name]["plotter"] == "plot_stacked_column_charts"
        assert specs[chart_name]["legacy_chart_key"] == "stackedColumnChart"
        assert specs[chart_name]["base_chart"] == base_chart
        assert specs[chart_name]["population_mode"] == "like_for_like"
        assert specs[chart_name]["population_dimension"] == "Productline"
    assert specs["like_for_like_column_total"]["show_cagr"] is True
    assert specs["like_for_like_stacked_column"]["show_cagr"] is True
    assert (
        specs["like_for_like_stacked_column"]["suppress_stacked_percentage_annotations"]
        is True
    )
    assert specs["like_for_like_stacked_column"]["max_items"] == 6


def test_like_for_like_reporting_title_uses_separate_population_line() -> None:
    legacy = load_legacy_charting()

    note = legacy._population_title_note(
        {"population_mode": "like_for_like", "population_dimension": "Barcode"}
    )

    assert note == "Like-for-like Barcode population"


def test_total_overlay_reporting_title_drops_redundant_total_view_suffix() -> None:
    legacy = load_legacy_charting()

    measure_line = legacy._compact_total_overlay_measure_line(
        "Bar chart: <b>Sales</b> in mEUR. Line chart: <b>Units</b> in m by Total View",
        {
            "plot_overlay_chart": True,
            "dimensions": ["Total View"],
        },
    )

    assert measure_line == (
        "Bar chart: <b>Sales</b> in mEUR. Line chart: <b>Units</b> in m"
    )


def test_like_for_like_stacked_column_uses_recent_three_year_window() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["2015", "2016", "2017", "2015", "2016", "2017"],
            "Sales": [8.0, 10.0, 12.0, 4.0, 5.0, 6.0],
            "Company": ["A", "A", "A", "B", "B", "B"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Company"],
        },
        "options": {
            "charts": [
                "like_for_like_column_total",
                "like_for_like_stacked_column",
            ],
            "current_period_label": "2017",
            "previous_period_label": "2016",
            "small_multiples": False,
            "like_for_like": {"source_dimension": "Company"},
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["like_for_like_column_total"]["selected_periods"] == ["2016", "2017"]
    assert specs["like_for_like_stacked_column"]["selected_periods"] == [
        "2015",
        "2016",
        "2017",
    ]
    assert specs["like_for_like_stacked_column"]["show_total_cagr"] is True


def test_prepare_canonical_frame_can_use_yearly_period_grain() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2024-01-05", "2024-07-05", "2025-01-05"],
            "Value": [10.0, 20.0, 30.0],
            "Barcode": ["A", "B", "A"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Value",
            "dimensions": ["Barcode"],
        },
        "options": {
            "period_grain": "year",
            "cohort_current_period": "2025-01-05",
            "cohort_previous_period": "2024-01-05",
            "cohort_definition": {
                "derived_dimensions": [
                    {
                        "source_dimension": "Barcode",
                        "name": "Barcode_Since",
                        "kind": "since",
                    },
                ],
                "periods": {
                    "period_column": "Period",
                    "value_column": "Sales",
                    "current_period": "2025-01-05",
                    "previous_period": "2024-01-05",
                },
            },
        },
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, audit = core.prepare_canonical_frame(frame, validated)
    periods = canonical.select("Period").unique().sort("Period").to_series().to_list()

    assert periods == ["2024", "2025"]
    assert audit["period_grain"] == "year"
    assert audit["period_source_column"] == "Date"
    assert validated["options"]["cohort_current_period"] == "2025"
    assert validated["options"]["cohort_previous_period"] == "2024"
    assert (
        validated["options"]["cohort_definition"]["periods"]["current_period"] == "2025"
    )
    assert (
        validated["options"]["cohort_definition"]["periods"]["previous_period"]
        == "2024"
    )


def test_prepare_canonical_frame_keeps_raw_dates_for_year_window_modes() -> None:
    core = load_core()
    frame = pl.DataFrame(
        {
            "Date": ["2024-01-05", "2024-07-05", "2025-01-05"],
            "Value": [10.0, 20.0, 30.0],
            "Barcode": ["A", "B", "A"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Value",
            "dimensions": ["Barcode"],
        },
        "options": {
            "period_grain": "year",
            "period_comparison_mode": "year_to_date",
        },
    }

    validated = core.validate_recipe(frame, recipe)
    canonical, audit = core.prepare_canonical_frame(frame, validated)
    periods = canonical.select("Period").unique().sort("Period").to_series().to_list()

    assert periods == ["2024-01-05", "2024-07-05", "2025-01-05"]
    assert audit["period_grain"] == "year"
    assert audit["period_source_column"] == "Date"


def test_related_metrics_bar_prefers_detailed_ranking_dimension() -> None:
    core = load_core()

    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value * period_scale,
                "Productline": "Hair",
                "Type": type_name,
                "Brand": brand,
            }
            for period, period_scale in (("PY", 0.8), ("AC", 1.0))
            for type_name in ("Permanent", "Temporary")
            for brand, value in (
                ("A", 100.0),
                ("B", 90.0),
                ("C", 80.0),
                ("D", 70.0),
                ("E", 60.0),
                ("F", 50.0),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Type", "Brand"],
        },
        "options": {"small_multiples": True},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["related_metrics_bar"]["x_dimension"] == "Brand"
    assert specs["related_metrics_bar"]["dimensions"] == ["Brand"]
    assert (
        specs["related_metrics_bar_small_multiples"]["small_multiples_dimension"]
        == "Type"
    )


def test_line_specs_use_legacy_timeline_charting() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    canonical = pl.DataFrame(
        [
            {
                "Date": date(2024, month, 1),
                "Period": "AC",
                "Sales": float(month * multiplier),
                "Productline": productline,
                "Region": region,
            }
            for month in range(1, 5)
            for productline, multiplier in (("Bikes", 10), ("Accessories", 4))
            for region in ("North", "South")
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Region"],
        },
        "options": {
            "small_multiples": True,
            "small_multiples_dimension": "Region",
            "small_multiples_max_panels": 4,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    line_spec = specs["line"]
    small_spec = specs["line_small_multiples"]
    source_functions = legacy._legacy_source_functions(small_spec)

    assert line_spec["plotter"] == "plot_timeline_charts"
    assert line_spec["legacy_chart_key"] == "timelineChart"
    assert line_spec["dimensions"] == []
    assert small_spec["base_chart"] == "line"
    assert small_spec["plotter"] == "plot_timeline_charts"
    assert small_spec["legacy_chart_key"] == "timelineChart"
    assert small_spec["dimensions"] == ["Productline"]
    assert small_spec["small_multiples_dimension"] == "Productline"
    assert small_spec["small_multiples_panel_axis"] == "X"
    assert small_spec["capture_figure"] == "last"
    assert "modules.charting.plot_charts.plot_timeline_charts" in source_functions
    assert "modules.charting.draw_timeline.draw_timeline_chart" in source_functions
    assert (
        "modules.data.time_series_data_prep.prepare_data_for_timeline_plot"
        in source_functions
    )


def _focus_mix_canonical() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "Date": date(2024, month, 1),
                "Period": f"2024-0{month}-01",
                "Sales": float(month * value),
                "Units": float(month * unit_value),
                "Productline": productline,
                "Region": region,
            }
            for month in range(1, 4)
            for productline, value, unit_value in (
                ("Bikes", 100.0, 10.0),
                ("Accessories", 40.0, 4.0),
            )
            for region in ("North", "South")
        ]
    )


@pytest.mark.parametrize(
    ("chart_name", "focus_item", "focus_dimension"),
    [
        ("stacked_bar", "North", "Region"),
        ("stacked_column", "Bikes", "Productline"),
        ("marimekko", "North", "Region"),
        ("area_absolute", "Bikes", "Productline"),
        ("line", "Bikes", "Productline"),
    ],
)
def test_focus_item_reaches_legacy_highlighted_dimension_for_supported_mix_specs(
    chart_name: str,
    focus_item: str,
    focus_dimension: str,
) -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Region"],
        },
        "options": {
            "charts": [chart_name],
            "focus_item": focus_item,
            "focus_dimension": focus_dimension,
        },
    }

    specs = {
        spec["name"]: spec
        for spec in core.build_chart_specs(_focus_mix_canonical(), recipe)
    }
    spec = specs[chart_name]
    names = get_naming_params()
    chart = legacy._legacy_chart_dict(names, spec, metric="Sales", currency="EUR")

    assert spec["focus_status"] == "resolved"
    assert spec["focus_item"] == focus_item
    assert spec["focus_dimension"] == focus_dimension
    assert spec["focus_reason"] == "matched_exact"
    assert chart[names["highlightedDimension"]] == [focus_item]
    if chart_name == "line":
        assert chart[names["selectDimensionsToPlot"]] == [focus_dimension]


def test_focus_item_reports_unsupported_for_barmekko_without_legacy_highlight() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "legacy_width_metric_column": "Units",
            "dimensions": ["Productline", "Region"],
        },
        "options": {
            "charts": ["barmekko"],
            "focus_item": "North",
            "focus_dimension": "Region",
        },
    }

    specs = {
        spec["name"]: spec
        for spec in core.build_chart_specs(_focus_mix_canonical(), recipe)
    }
    spec = specs["barmekko"]
    names = get_naming_params()
    chart = legacy._legacy_chart_dict(names, spec, metric="Sales", currency="EUR")

    assert spec["focus_status"] == "unsupported"
    assert spec["focus_reason"] == "legacy_chart_has_no_focus_highlight"
    assert spec["focus_item"] == "North"
    assert spec["focus_dimension"] == "Region"
    assert names["highlightedDimension"] not in chart


def test_focus_item_caps_multiple_requests_and_uses_unambiguous_case_fallback() -> None:
    core = load_core()
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Productline", "Region"],
        },
        "options": {
            "charts": ["stacked_column"],
            "focus_item": ["bikes", "Accessories"],
            "focus_dimension": "Productline",
        },
    }

    specs = {
        spec["name"]: spec
        for spec in core.build_chart_specs(_focus_mix_canonical(), recipe)
    }
    spec = specs["stacked_column"]
    names = get_naming_params()
    chart = legacy._legacy_chart_dict(names, spec, metric="Sales", currency="EUR")

    assert spec["focus_status"] == "resolved"
    assert spec["focus_item"] == "Bikes"
    assert spec["focus_reason"] == "matched_case_insensitive"
    assert chart[names["highlightedDimension"]] == ["Bikes"]


def test_mix_horizontal_waterfall_specs_are_retired() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date(2024, month, 1),
                "Period": period,
                "Sales": float(month * multiplier),
                "Productline": productline,
                "Region": region,
            }
            for period, period_multiplier in (("PY", 0.8), ("AC", 1.0))
            for month in range(1, 5)
            for productline, multiplier in (
                ("Bikes", 10 * period_multiplier),
                ("Accessories", 4 * period_multiplier),
            )
            for region in ("North", "South")
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Region"],
        },
        "options": {
            "charts": [
                "horizontal_waterfall",
                "horizontal_waterfall_small_multiples",
            ],
            "small_multiples": True,
            "small_multiples_dimension": "Region",
            "small_multiples_max_panels": 4,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "horizontal_waterfall" not in specs
    assert "horizontal_waterfall_small_multiples" not in specs


def test_related_metrics_context_exports_legacy_figure_rows(
    tmp_path: Path,
) -> None:
    core = load_core()
    legacy = load_legacy_charting()

    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="North"),
                SimpleNamespace(text="Total<br><b>160</b>"),
            ]
        ),
        data=[
            SimpleNamespace(
                type="bar",
                yaxis="y",
                x=[100.0, 20.0, 5.0],
                y=["A", "B", "Other rank >2"],
                text=["100.0 (80%)", "20.0 (16%)", "5.0 (4%)"],
            ),
            SimpleNamespace(
                type="scatter",
                mode="markers+text",
                yaxis="y",
                x=[-5.0, 10.0, 30.0],
                y=["A", "B", "Other rank >2"],
                text=["-5%", "+10%", "+30%"],
            ),
        ],
    )
    spec = {
        "name": "related_metrics_bar",
        "metrics": ["Sales", "Sales Growth Rate"],
        "metric": "Sales",
        "dimensions": ["Productline"],
        "x_dimension": "Productline",
        "selected_periods": ["PY", "AC"],
        "capture_chart_data": True,
        "related_metrics_bar": True,
    }

    payload = legacy._capture_context_payload(
        spec=spec,
        chart={},
        calls=[
            {
                "legacy_chart": "stacked bar",
                "data_frame": {"columns": ["Productline", "Sales"], "rows": []},
            }
        ],
        figures=[figure],
        exports=[],
        source_functions=["modules.charting.plot_charts.plot_stacked_bar_charts"],
    )
    assert payload is not None

    paths, audit = core.write_chart_context_artifacts(
        "related_metrics_bar",
        payload,
        tmp_path,
    )

    rows = payload["related_metric_rows"]
    assert rows[0]["panel"] == "North"
    assert rows[0]["item"] == "A"
    assert rows[0]["rank_by_primary_metric"] == 1
    assert rows[0]["marker_metric"] == "Sales Growth Rate"
    assert payload["other_bucket_rows"][0]["item"] == "Other rank >2"
    assert payload["notable_mismatches"][0]["pattern"] == "large_declining_item"
    assert audit["table_status"] == "written"
    assert str(tmp_path / "related_metrics_bar_chart_data.csv") in paths
    written_rows = pl.read_csv(tmp_path / "related_metrics_bar_chart_data.csv")
    assert written_rows.columns == [
        "figure_index",
        "panel",
        "axis",
        "item",
        "primary_metric",
        "primary_value",
        "primary_label",
        "share_of_panel_total",
        "marker_metric",
        "marker_value",
        "marker_label",
        "is_other_bucket",
        "rank_by_primary_metric",
    ]


def test_related_metrics_single_panel_uses_total_panel_label() -> None:
    legacy = load_legacy_charting()

    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(
                    text="<BR>Bar chart: <b>Sales</b> in mEUR. Markers: "
                    "<b>Units</b> in k. By Brand <BR>2017-08-27"
                ),
                SimpleNamespace(text="4.4 (26%)"),
            ]
        ),
        data=[
            SimpleNamespace(
                type="bar",
                yaxis="y",
                x=[None, 100.0],
                y=[None, "A"],
                text=[],
            ),
            SimpleNamespace(
                type="scatter",
                mode="markers+text",
                yaxis="y",
                x=[None, 12.0],
                y=[None, "A"],
                text=["0", "12"],
            ),
        ],
    )
    spec = {
        "name": "related_metrics_bar",
        "metrics": ["Sales", "Units"],
        "metric": "Sales",
        "related_metrics_bar": True,
    }

    rows, notable = legacy._related_metric_rows_from_figures([figure], spec)

    assert notable[0]["pattern"] == "large_growing_item"
    assert rows == [
        {
            "figure_index": 1,
            "panel": "Total",
            "axis": "y",
            "item": "A",
            "primary_metric": "Sales",
            "primary_value": 100.0,
            "primary_label": None,
            "share_of_panel_total": 1.0,
            "marker_metric": "Units",
            "marker_value": 12.0,
            "marker_label": "12",
            "is_other_bucket": False,
            "rank_by_primary_metric": 1,
        }
    ]


def test_legacy_index_dimensions_include_spec_owned_cohort_dimensions() -> None:
    legacy = load_legacy_charting()
    recipe = {"mappings": {"dimensions": ["Company", "Brand"]}}
    spec = {
        "dimensions": ["Barcode_Since"],
        "x_dimension": "Barcode_Since",
        "y_dimension": None,
        "cohort_dimension": "Barcode_Since",
        "cohort_source_dimension": "Barcode",
    }

    dimensions = legacy._legacy_index_dimensions(recipe, spec)

    assert dimensions == ["Company", "Brand", "Barcode_Since", "Barcode"]


def test_legacy_related_metrics_overlay_keeps_polars_rename_compatibility() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        prepare_overlay_data_for_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline"],
            "x_dimension": "Productline",
            "y_dimension": None,
            "metrics": ["Sales", "Sales Growth Rate"],
            "selected_periods": ["PY", "AC"],
            "plot_overlay_chart": True,
            "related_metrics_bar": True,
        },
        metric="Sales",
        currency="EUR",
    )
    params = legacy._legacy_param_dict(
        names,
        total=160.0,
        selected_periods=["PY", "AC"],
        period_totals={"PY": 150.0, "AC": 160.0},
        columns=["Period", "Productline", "Sales"],
    )
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC", "PY", "AC"],
            "Productline": ["A", "A", "B", "B"],
            "Sales": [100.0, 120.0, 50.0, 40.0],
        }
    )

    chart = prepare_overlay_data_for_stacked_bar(
        frame.lazy(),
        pl.DataFrame(),
        names["totalName"],
        "Productline",
        "Other rank >2",
        ["Sales"],
        chart,
        params,
    )

    overlay = chart[names["overlayChartDf"]].collect().sort("Productline")
    assert overlay.columns == ["Productline", "Sales Growth Rate"]
    assert overlay.get_column("Sales Growth Rate").to_list() == [20.0, -20.0]


def test_legacy_related_metrics_overlay_calculates_unit_price() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        prepare_overlay_data_for_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline"],
            "x_dimension": "Productline",
            "y_dimension": None,
            "metrics": ["Sales", "Unit Price"],
            "selected_periods": ["AC"],
            "plot_overlay_chart": True,
            "related_metrics_bar": True,
        },
        metric="Sales",
        currency="EUR",
    )
    params = legacy._legacy_param_dict(
        names,
        total=160.0,
        selected_periods=["AC"],
        period_totals={"AC": 160.0},
        columns=["Period", "Productline", "Sales", "Units"],
    )
    frame = pl.DataFrame(
        {
            "Period": ["AC", "AC"],
            "Productline": ["A", "B"],
            "Sales": [120.0, 40.0],
            "Units": [10.0, 20.0],
        }
    )

    chart = prepare_overlay_data_for_stacked_bar(
        frame.lazy(),
        pl.DataFrame(),
        names["totalName"],
        "Productline",
        "Other rank >2",
        ["Sales", "Units"],
        chart,
        params,
    )

    overlay = chart[names["overlayChartDf"]].collect().sort("Productline")
    assert overlay.columns == ["Productline", "Unit Price"]
    assert overlay.get_column("Unit Price").to_list() == [12.0, 2.0]


def test_legacy_related_metrics_overlay_calculates_margin_percent() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        prepare_overlay_data_for_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline"],
            "x_dimension": "Productline",
            "y_dimension": None,
            "metrics": ["Sales", "Margin in %"],
            "selected_periods": ["AC"],
            "plot_overlay_chart": True,
            "related_metrics_bar": True,
        },
        metric="Sales",
        currency="EUR",
    )
    params = legacy._legacy_param_dict(
        names,
        total=160.0,
        selected_periods=["AC"],
        period_totals={"AC": 160.0},
        columns=["Period", "Productline", "Sales", "Margin"],
    )
    frame = pl.DataFrame(
        {
            "Period": ["AC", "AC"],
            "Productline": ["A", "B"],
            "Sales": [120.0, 40.0],
            "Margin": [30.0, 4.0],
        }
    )

    chart = prepare_overlay_data_for_stacked_bar(
        frame.lazy(),
        pl.DataFrame(),
        names["totalName"],
        "Productline",
        "Other rank >2",
        ["Sales", "Margin"],
        chart,
        params,
    )

    overlay = chart[names["overlayChartDf"]].collect().sort("Productline")
    assert overlay.columns == ["Productline", "Margin in %"]
    assert overlay.get_column("Margin in %").to_list() == [25.0, 10.0]


def test_legacy_overlay_scaling_keeps_nulls_without_fill_null_noop() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.chart_primitives import multiply_other_metric_for_scale
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["scalingFactor"]: 2,
        names["offset"]: 1,
    }
    frame = pl.DataFrame({"Sales Growth Rate": [None, 2.4]})

    scaled = multiply_other_metric_for_scale(
        frame,
        "Sales Growth Rate",
        chart,
        1,
        1,
    )

    assert scaled.get_column("Sales Growth Rate").to_list() == [None, 6.0]


def test_legacy_stacked_pareto_millify_handles_nan_label_values() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.chart_primitives import millify_dataframe
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["chosenChart"]: names["stackedParetoChart"],
        names["metricsToPlot"]: ["Sales"],
        names["showValuesAs"]: names["absolute"],
        names["showAbsoluteValues"]: True,
    }
    frame = pl.DataFrame({"Sales": [float("nan")]}).lazy()

    labelled, _chart = millify_dataframe(
        frame,
        "Sales",
        None,
        names["labelName"],
        chart,
    )

    assert labelled.collect().get_column(names["labelName"]).to_list() == ["0"]


def test_legacy_small_multiple_total_message_is_warning_event() -> None:
    legacy = load_legacy_charting()
    small_multiple_spec = {"small_multiples_dimension": "Kiko Lane"}

    assert legacy._is_small_multiple_total_warning(
        {
            "method": "error",
            "args": ["Small multiples values and total values differ by 4.5%"],
        },
        small_multiple_spec,
    )
    assert legacy._is_small_multiple_total_warning(
        {"method": "error", "args": ["Small multiples total is  115922988.125"]},
        small_multiple_spec,
    )
    assert legacy._is_small_multiple_total_warning(
        {"method": "error", "args": ["Total is  121154397.58999999"]},
        small_multiple_spec,
    )
    assert not legacy._is_small_multiple_total_warning(
        {"method": "error", "args": ["Unexpected legacy chart failure"]},
        small_multiple_spec,
    )
    assert not legacy._is_small_multiple_total_warning(
        {
            "method": "error",
            "args": ["Small multiples values and total values differ by 4.5%"],
        },
        {},
    )


def test_legacy_stacked_bar_overlay_uses_category_y_values() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_overlay_trace
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline"],
            "x_dimension": "Productline",
            "y_dimension": None,
            "metrics": ["Sales", "Sales Growth Rate"],
            "selected_periods": ["PY", "AC"],
            "plot_overlay_chart": True,
            "related_metrics_bar": True,
        },
        metric="Sales",
        currency="EUR",
    )
    chart[names["overlayChartMetric"]] = "Sales Growth Rate"
    chart[names["overlayChartDf"]] = pl.DataFrame(
        {
            "Productline": ["A", "B"],
            "Sales Growth Rate": [10.0, -5.0],
        }
    )
    frame = pl.DataFrame({"Productline": ["A", "B"], "Value": [100.0, 50.0]})

    figure, _chart = add_overlay_trace(
        make_subplots(rows=1, cols=1),
        frame,
        ["#111111", "#888888"],
        chart,
        1,
        1,
    )

    assert set(figure.data[0].y) == {"A", "B"}
    assert figure.data[0].marker.color == "#FF0000"
    assert figure.data[0].marker.size == 28
    assert figure.layout.xaxis2.overlaying == "x"
    assert figure.layout.xaxis2.showline is False


def test_legacy_related_metric_markers_use_one_color() -> None:
    legacy = load_legacy_charting()

    import plotly.graph_objects as go

    assert legacy.FOCUS_ITEM_HIGHLIGHT_COLOR == "#0065FF"
    assert legacy.FOCUS_ITEM_HIGHLIGHT_MAX_ITEMS == 1
    assert legacy.RELATED_METRIC_MARKER_COLOR == legacy.FOCUS_ITEM_HIGHLIGHT_COLOR

    figure = go.Figure(
        data=[
            go.Bar(x=[10.0], y=["A"]),
            go.Scatter(
                x=[5.0],
                y=[0],
                mode="markers+text",
                marker={"color": "#888888", "line": {"color": "#888888"}, "size": 28},
            ),
        ]
    )

    legacy._apply_related_metric_marker_color([figure])

    marker = figure.data[1].marker
    assert marker.color == legacy.RELATED_METRIC_MARKER_COLOR
    assert marker.line.color == legacy.RELATED_METRIC_MARKER_COLOR
    assert marker.size == legacy.RELATED_METRIC_MARKER_SIZE


def test_legacy_focus_item_highlight_token_is_single_item() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.chart_primitives import (
        FOCUS_ITEM_HIGHLIGHT_COLOR,
        FOCUS_ITEM_HIGHLIGHT_MAX_ITEMS,
        insert_highlight_color,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    base_colors = ["#111111", "#222222", "#333333"]
    chart = {names["highlightedDimension"]: ["Second", "Third"]}

    result = insert_highlight_color(
        "Brand",
        ["First", "Second", "Third"],
        base_colors.copy(),
        {},
        chart,
    )
    bain_palette_result = insert_highlight_color(
        "Brand",
        ["First", "Second", "Third"],
        base_colors.copy(),
        {},
        {
            names["highlightedDimension"]: ["Second"],
            names["colorpalette"]: names["bainColorpalette"],
        },
    )

    assert FOCUS_ITEM_HIGHLIGHT_COLOR == "#0065FF"
    assert FOCUS_ITEM_HIGHLIGHT_MAX_ITEMS == 1
    assert result == ["#111111", FOCUS_ITEM_HIGHLIGHT_COLOR, "#333333"]
    assert bain_palette_result == ["#111111", FOCUS_ITEM_HIGHLIGHT_COLOR, "#333333"]


def test_legacy_column_overlay_uses_rendered_column_centers() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import add_overlay_trace
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Total View"],
            "x_dimension": "Total View",
            "y_dimension": "Total View",
            "metrics": ["Sales", "Units"],
            "selected_periods": ["2015", "2016", "2017"],
            "plot_overlay_chart": True,
            "highlight_overlay_chart": True,
            "show_cagr": True,
        },
        metric="Sales",
        currency="EUR",
    )
    chart[names["overlayChartMetric"]] = "Units"
    chart[names["overlayChartDf"]] = pl.DataFrame(
        {
            "Period": ["2015", "2016", "2017"],
            "Units": [8.4, 25.7, 18.1],
        }
    )
    frame = pl.DataFrame(
        {
            "Period": ["2015", "2016", "2017", None],
            "Total": [362.0, 1088.0, 736.0, None],
            "Value": [362.0, 1088.0, 736.0, None],
        }
    )
    figure = make_subplots(rows=1, cols=1)
    figure.add_bar(
        x=[0, 1, 2, 3],
        y=[362.0, 1088.0, 736.0, None],
        width=[0.8, 0.8, 0.8, 0.8],
        offset=0,
        name="Total",
        row=1,
        col=1,
    )

    figure, _chart = add_overlay_trace(
        figure,
        frame,
        ["#111111", "#888888"],
        chart,
        1,
        1,
    )

    overlay_trace = figure.data[-1]
    assert legacy.FOCUS_ITEM_HIGHLIGHT_COLOR == "#0065FF"
    assert list(overlay_trace.x) == pytest.approx([0.4, 1.4, 2.4])
    assert list(overlay_trace.y) == [8.4, 25.7, 18.1]
    assert list(overlay_trace.text) == ["8.4", "25.7", "18.1"]
    assert overlay_trace.marker.color == legacy.FOCUS_ITEM_HIGHLIGHT_COLOR
    assert overlay_trace.marker.line.color == legacy.FOCUS_ITEM_HIGHLIGHT_COLOR
    assert overlay_trace.textfont.color == legacy.FOCUS_ITEM_HIGHLIGHT_COLOR
    assert figure.layout.yaxis2.overlaying == "y"
    assert figure.layout.yaxis2.showline is False


def test_total_column_export_clears_bar_text_but_keeps_overlay_text() -> None:
    legacy = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_bar(
        x=[0, 1, 2],
        y=[362.0, 1088.0, 736.0],
        text=["0.36", "1.09", "0.74"],
        name="Total",
    )
    figure.add_scatter(
        x=[0.4, 1.4, 2.4],
        y=[8.4, 25.7, 18.1],
        text=["8.4", "25.7", "18.1"],
        name="Units",
    )

    legacy._clear_total_column_bar_text(
        [figure],
        {"total_column_dimension": "Total View"},
    )

    assert list(figure.data[0].text) == ["", "", ""]
    assert figure.data[0].texttemplate is None
    assert list(figure.data[1].text) == ["8.4", "25.7", "18.1"]


def test_legacy_stacked_column_total_segment_can_show_cagr() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    import plotly.graph_objects as go

    from modules.charting.draw_width_and_stacked_plots import (
        add_first_row_annotations_for_stacked_column,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Total View"],
            "x_dimension": "Total View",
            "y_dimension": "Total View",
            "metrics": ["Sales"],
            "selected_periods": ["2015", "2016", "2017"],
            "show_cagr": True,
        },
        metric="Sales",
        currency="EUR",
    )
    chart[names["CXGRMetricName"]] = "CAGR"
    chart[names["CXGRTotal"]] = pl.DataFrame({"Total": [42.0]}).lazy()
    chart[names["periodsMissing"]] = pl.DataFrame({"Total": [0.0]}).lazy()
    figure = go.Figure()

    legacy._apply_total_column_cagr_annotation(
        [figure],
        chart,
        names,
        add_first_row_annotations_for_stacked_column,
    )

    assert [annotation.text for annotation in figure.layout.annotations] == [
        "CAGR<br> 42.0%"
    ]


def test_legacy_total_cagr_ignores_stacked_column_spacer_period() -> None:
    legacy = load_legacy_charting()

    total_cagr = legacy._total_cagr_from_period_totals(
        {"_Aug-2016": 740.0, "_Aug-2017": 736.0},
        ["_Aug-2016", "_Aug-2017", "     "],
    )

    assert total_cagr == pytest.approx(-0.5405405405405406)


def test_legacy_total_cagr_aligns_with_right_lane_values() -> None:
    legacy = load_legacy_charting()

    import plotly.graph_objects as go

    figure = go.Figure()
    figure.add_annotation(
        text="-7.5%",
        x=1.8,
        xref="x",
        xanchor="left",
        xshift=120,
        align="left",
        showarrow=False,
        font={"size": 12},
        y=100,
    )

    legacy._apply_stacked_total_cagr_annotation(
        [figure],
        {"show_total_cagr": True},
        {"_Aug-2016": 740.0, "_Aug-2017": 736.0},
        ["_Aug-2016", "_Aug-2017", "     "],
    )

    annotation = figure.layout.annotations[-1]
    assert annotation.text == "CAGR<br>-0.5%"
    assert annotation.x == 1.8
    assert annotation.xref == "x"
    assert annotation.xanchor == "left"
    assert annotation.xshift == 120
    assert annotation.font.size == 12


def test_stacked_column_spec_uses_single_dimension_stack() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value,
                "Productline": productline,
                "Category": category,
            }
            for period, value in (("PL", 10.0), ("AC", 12.0))
            for productline, category in (
                ("Bikes", "Road"),
                ("Accessories", "Helmets"),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Category"],
        },
        "options": {},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column"]["dimensions"] == ["Productline"]
    assert specs["stacked_column"]["x_dimension"] == "Productline"
    assert specs["stacked_column"]["y_dimension"] == "Productline"
    assert specs["stacked_column"]["capture_chart_data"] is True


def test_stacked_column_small_multiples_spec_uses_primary_dimension_panels() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["PY", "AC", "PY", "AC"],
            "Sales": [10.0, 12.0, 20.0, 24.0],
            "Productline": ["Bikes", "Bikes", "Accessories", "Accessories"],
            "Category": ["Road", "Road", "Helmets", "Helmets"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Productline", "Category"],
        },
        "options": {
            "charts": ["stacked_column_small_multiples"],
            "small_multiples": True,
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    spec = specs["stacked_column_small_multiples"]
    assert spec["base_chart"] == "stacked_column"
    assert spec["plotter"] == "plot_stacked_column_charts"
    assert spec["legacy_chart_key"] == "stackedColumnChart"
    assert spec["dimensions"] == ["Productline"]
    assert spec["small_multiples_dimension"] == "Productline"
    assert spec["small_multiples_panel_axis"] == "X"
    assert spec["capture_chart_data"] is True
    assert spec["capture_figure"] == "last"


def test_stacked_column_spec_uses_forecast_comparison_period() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value,
                "Productline": productline,
                "Category": category,
            }
            for period, value in (("FC", 10.0), ("AC", 12.0))
            for productline, category in (
                ("Bikes", "Road"),
                ("Accessories", "Helmets"),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Category"],
        },
        "options": {},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column"]["selected_periods"] == ["FC", "AC"]
    assert specs["stacked_column"]["period_selection_mode"] == "comparison_periods"


def test_stacked_column_raw_date_periods_default_to_year_axis() -> None:
    core = load_core()
    raw_periods = [
        "2024-01-07",
        "2024-02-04",
        "2024-03-03",
        "2024-03-31",
        "2024-04-28",
        "2024-05-26",
        "2024-06-23",
        "2024-07-21",
        "2024-08-18",
        "2024-09-15",
        "2024-10-13",
        "2024-11-10",
        "2025-01-05",
    ]
    canonical = pl.DataFrame(
        {
            "Date": [date.fromisoformat(value) for value in raw_periods],
            "Period": raw_periods,
            "Sales": [10.0] * len(raw_periods),
            "Company": ["A"] * len(raw_periods),
            "Brand": ["B"] * len(raw_periods),
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {"charts": ["stacked_column"]},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column"]["period_grain"] == "year"
    assert specs["stacked_column"]["selected_periods"] == ["2024", "2025"]
    assert specs["stacked_column"]["period_selection_mode"] == "all_periods_at_grain"
    assert (
        specs["stacked_column"]["dimension_selection"]
        == "primary_dimension_period_axis_at_grain"
    )


def test_stacked_column_synthesis_uses_grained_period_selection() -> None:
    core = load_core()
    raw_periods = [
        "2024-01-07",
        "2024-02-04",
        "2024-03-03",
        "2024-03-31",
        "2024-04-28",
        "2024-05-26",
        "2024-06-23",
        "2024-07-21",
        "2024-08-18",
        "2024-09-15",
        "2024-10-13",
        "2024-11-10",
        "2025-01-05",
    ]
    canonical = pl.DataFrame(
        {
            "Date": [date.fromisoformat(value) for value in raw_periods],
            "Period": raw_periods,
            "Sales": [10.0] * len(raw_periods),
            "Company": ["A"] * len(raw_periods),
            "Brand": ["B"] * len(raw_periods),
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {"charts": ["stacked_column_synthesis"]},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column_synthesis"]["period_grain"] == "year"
    assert specs["stacked_column_synthesis"]["selected_periods"] == ["2024", "2025"]
    assert (
        specs["stacked_column_synthesis"]["period_selection_mode"]
        == "all_periods_at_grain"
    )


def test_stacked_column_synthesis_blocks_single_raw_date_label() -> None:
    core = load_core()
    raw_period = "2024-01-07"
    canonical = pl.DataFrame(
        {
            "Date": [date.fromisoformat(raw_period), date.fromisoformat(raw_period)],
            "Period": [raw_period, raw_period],
            "Sales": [10.0, 15.0],
            "Company": ["A", "B"],
            "Brand": ["Main", "Other"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {"charts": ["stacked_column_synthesis"]},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column_synthesis"]["period_grain"] == "year"
    assert specs["stacked_column_synthesis"]["selected_periods"] == ["2024"]
    assert (
        specs["stacked_column_synthesis"]["period_selection_mode"]
        == "all_periods_at_grain"
    )


def test_actual_date_range_period_label_replaces_bare_ac_context() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Date": [
                date.fromisoformat("2024-01-07"),
                date.fromisoformat("2024-03-31"),
            ],
            "Period": ["AC", "AC"],
            "Sales": [10.0, 15.0],
            "Company": ["A", "B"],
            "Brand": ["Main", "Other"],
        }
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {"charts": ["stacked_column_synthesis"]},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column_synthesis"]["period_display_label"] == (
        "AC, 2024-01-07 to 2024-03-31"
    )


def test_stacked_column_specs_keep_explicit_year_pair_with_year_grain() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date.fromisoformat(period),
                "Period": period,
                "Sales": value,
                "Company": company,
                "Brand": brand,
            }
            for period, value in (
                ("2024-01-05", 10.0),
                ("2025-01-05", 20.0),
                ("2026-01-05", 30.0),
            )
            for company, brand in (("A", "Main"), ("B", "Other"))
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {
            "charts": ["stacked_column"],
            "current_period_label": "2025",
            "previous_period_label": "2024",
            "period_grain": "year",
            "period_selection": "explicit_comparison_periods",
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column"]["period_grain"] == "year"
    assert specs["stacked_column"]["selected_periods"] == ["2024", "2025"]
    assert specs["stacked_column"]["period_selection_mode"] == "comparison_periods"
    assert (
        specs["stacked_column"]["dimension_selection"]
        == "primary_dimension_comparison_period_axis_at_grain"
    )


def test_chart_specs_coarsen_raw_current_and_previous_periods_by_default() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date.fromisoformat(period),
                "Period": period,
                "Sales": value,
                "Company": company,
                "Brand": brand,
            }
            for period, value in (
                ("2025-01-05", 10.0),
                ("2025-02-02", 20.0),
                ("2025-03-02", 30.0),
            )
            for company, brand in (("A", "Main"), ("B", "Other"))
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {
            "current_period_label": "2025-03-02",
            "previous_period_label": "2025-02-02",
            "charts": ["line", "stacked_column"],
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["line"]["selected_periods"] == [
        "2025-01-05",
        "2025-02-02",
        "2025-03-02",
    ]
    assert specs["stacked_column"]["period_grain"] == "year"
    assert specs["stacked_column"]["selected_periods"] == ["2025"]
    assert specs["stacked_column"]["period_selection_mode"] == "all_periods_at_grain"


def test_stacked_column_specs_allow_explicit_week_grain() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Date": date.fromisoformat(period),
                "Period": period,
                "Sales": value,
                "Company": company,
                "Brand": brand,
            }
            for period, value in (
                ("2025-01-05", 10.0),
                ("2025-02-02", 20.0),
                ("2025-03-02", 30.0),
            )
            for company, brand in (("A", "Main"), ("B", "Other"))
        ]
    )
    recipe = {
        "mappings": {
            "date_column": "Date",
            "period_column": "Date",
            "amount_column": "Sales",
            "dimensions": ["Company", "Brand"],
        },
        "options": {
            "current_period_label": "2025-03-02",
            "previous_period_label": "2025-02-02",
            "charts": ["stacked_column"],
            "period_grain": "week",
            "period_selection": "explicit_comparison_periods",
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column"]["period_grain"] == "week"
    assert specs["stacked_column"]["selected_periods"] == [
        "2025-02-02",
        "2025-03-02",
    ]
    assert specs["stacked_column"]["period_selection_mode"] == "comparison_periods"


def test_cohort_since_and_lost_specs_use_legacy_stacked_column_grammar() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["PY", "AC", "AC", "PY"],
            "Sales": [10.0, 12.0, 5.0, 7.0],
            "Brand": ["Common", "Common", "New", "Lost"],
            "Brand_Since": [
                "Since PY",
                "Since PY",
                "Since AC",
                "Since PY",
            ],
            "Brand_Lost": ["Active", "Active", "Active", "Lost after PY"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Brand_Since", "Brand_Lost", "Brand"],
        },
        "options": {
            "charts": [
                "cohort_since_stacked_column",
                "cohort_lost_stacked_column",
            ],
            "cohort_definition": {
                "derived_dimensions": [
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
                "periods": {
                    "period_column": "Period",
                    "value_column": "Sales",
                    "current_period": "AC",
                    "previous_period": "PY",
                },
            },
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert set(specs) == {
        "cohort_since_stacked_column",
        "cohort_lost_stacked_column",
    }
    assert (
        specs["cohort_since_stacked_column"]["legacy_chart_key"] == "stackedColumnChart"
    )
    assert specs["cohort_since_stacked_column"]["plotter"] == (
        "plot_stacked_column_charts"
    )
    assert specs["cohort_since_stacked_column"]["dimensions"] == ["Brand_Since"]
    assert specs["cohort_since_stacked_column"]["x_dimension"] == "Period"
    assert specs["cohort_since_stacked_column"]["y_dimension"] == "Brand_Since"
    assert specs["cohort_since_stacked_column"]["selected_periods"] == ["PY", "AC"]
    assert specs["cohort_since_stacked_column"]["period_grain"] is None
    assert specs["cohort_since_stacked_column"]["cohort_reference_period"] == "AC"
    assert specs["cohort_since_stacked_column"]["cohort_activity_metric"] == "Sales"
    assert specs["cohort_since_stacked_column"]["chosen_cohort_column"] == "Brand"
    assert (
        specs["cohort_since_stacked_column"]["suppress_zero_rounded_stacked_labels"]
        is False
    )
    assert specs["cohort_lost_stacked_column"]["dimensions"] == ["Brand_Lost"]
    assert specs["cohort_lost_stacked_column"]["x_dimension"] == "Period"
    assert specs["cohort_lost_stacked_column"]["y_dimension"] == "Brand_Lost"
    assert specs["cohort_lost_stacked_column"]["selected_periods"] == ["PY", "AC"]
    assert specs["cohort_lost_stacked_column"]["period_grain"] is None
    assert specs["cohort_lost_stacked_column"]["cohort_reference_period"] == "PY"
    assert specs["cohort_lost_stacked_column"]["cohort_activity_metric"] == "Sales"
    assert specs["cohort_lost_stacked_column"]["chosen_cohort_column"] is None
    assert specs["cohort_lost_stacked_column"]["lost_and_dropped_column"] == "Brand"
    assert (
        specs["cohort_lost_stacked_column"]["suppress_zero_rounded_stacked_labels"]
        is True
    )


def test_cohort_specs_use_recent_period_window_with_before_bucket() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        {
            "Period": ["2013", "2014", "2015", "2016", "2017"],
            "Sales": [3.0, 4.0, 5.0, 6.0, 7.0],
            "Brand": ["A", "B", "C", "D", "E"],
        }
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "period_column": "Period",
            "dimensions": ["Brand"],
        },
        "options": {
            "charts": ["cohort_since_stacked_column"],
            "cohort_current_period": "2017",
            "cohort_previous_period": "2016",
            "cohort_definition": {
                "derived_dimensions": [
                    {
                        "source_dimension": "Brand",
                        "name": "Brand_Since",
                        "kind": "since",
                    }
                ],
                "periods": {
                    "period_column": "Period",
                    "value_column": "Sales",
                    "current_period": "2017",
                    "previous_period": "2016",
                },
            },
        },
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}
    spec = specs["cohort_since_stacked_column"]

    assert spec["selected_periods"] == ["Before 2015", "2015", "2016", "2017"]
    assert spec["cohort_visible_periods"] == ["2015", "2016", "2017"]
    assert spec["cohort_before_period_label"] == "Before 2015"
    assert spec["period_selection_mode"] == "cohort_recent_periods_with_before_bucket"


def test_cohort_stacked_column_chartdict_preserves_legacy_stack_dimension() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Brand_Lost"],
            "x_dimension": "Period",
            "y_dimension": "Brand_Lost",
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
            "period_grain": "year",
        },
        metric="Sales",
        currency="EUR",
    )

    assert chart[names["selectedPeriods"]] == ["PY", "AC"]
    assert chart[names["selectDimensionsToPlot"]] == ["Brand_Lost"]
    assert chart[names["xAxisDimension"]] == "Period"
    assert chart[names["yAxisDimension"]] == "Brand_Lost"
    assert chart[names["yAxisDimension"]] != names["nothingFilteredName"]
    assert chart[names["datePeriodName"]] == names["yearName"]


def test_cohort_period_bucket_groups_older_rows_before_visible_window() -> None:
    legacy = load_legacy_charting()
    frame = pl.DataFrame(
        {
            "Period": ["2013", "2014", "2015", "2016", "2017"],
            "Brand": ["A", "B", "C", "D", "E"],
            "Sales": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )

    result = legacy._apply_cohort_period_bucket(
        frame,
        {
            "cohort_visible_periods": ["2015", "2016", "2017"],
            "cohort_before_period_label": "Before 2015",
        },
    )

    assert result.select("Period").to_series().to_list() == [
        "Before 2015",
        "Before 2015",
        "2015",
        "2016",
        "2017",
    ]


def test_cohort_stacked_column_adapter_uses_legacy_multi_period_labels() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["2014", "2017", "2015", "2016", "2017", "2016", "2014"],
            "Brand": ["Ancient", "Ancient", "Old", "Old", "Old", "New", "Gone"],
            "Sales": [1.0, 7.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    params = legacy._legacy_param_dict(
        names,
        total=28.0,
        selected_periods=["2015", "2016", "2017"],
        period_totals={"2015": 2.0, "2016": 8.0, "2017": 11.0},
        columns=frame.columns,
        date_period_choice=names["yearName"],
    )
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedColumnChart",
            "dimensions": ["Brand_Since"],
            "x_dimension": "Period",
            "y_dimension": "Brand_Since",
            "metrics": ["Sales"],
            "selected_periods": ["2015", "2016", "2017"],
            "period_grain": "year",
            "chosen_cohort_column": "Brand",
        },
        metric="Sales",
        currency="EUR",
    )

    since_frame = legacy._apply_legacy_cohort_columns(
        frame,
        names,
        params,
        chart,
        {"chosen_cohort_column": "Brand"},
    )
    since_labels = {
        row["Brand"]: row["Brand_Since"]
        for row in since_frame.select(["Brand", "Brand_Since"]).unique().to_dicts()
    }

    assert since_labels == {
        "Ancient": "Before 2015",
        "Gone": "Before 2015",
        "Old": "Since 2015",
        "New": "Since 2016",
    }

    lost_frame = legacy._apply_legacy_cohort_columns(
        frame,
        names,
        params,
        chart,
        {"lost_and_dropped_column": "Brand"},
    )
    lost_labels = {
        row["Brand"]: row["Brand_Lost"]
        for row in lost_frame.select(["Brand", "Brand_Lost"]).unique().to_dicts()
    }

    assert lost_labels == {
        "Ancient": names["activeName"],
        "Gone": "Lost before 2015",
        "Old": names["activeName"],
        "New": "Lost after 2016",
    }


def test_cohort_stacked_column_adapter_preserves_prepared_activity_labels() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "PY", "AC", "AC"],
            "Sales": [10.0, 2.0, 11.0, 0.0],
            "Brand": ["Common", "Lost", "Common", "Lost"],
            "Brand_Lost": [
                "Active",
                "Lost after PY",
                "Active",
                "Lost after PY",
            ],
        }
    )
    params = legacy._legacy_param_dict(
        names,
        total=11.0,
        selected_periods=["PY", "AC"],
        period_totals={"PY": 12.0, "AC": 11.0},
        columns=frame.columns,
        date_period_choice=names["yearName"],
    )

    result = legacy._apply_legacy_cohort_columns(
        frame,
        names,
        params,
        {},
        {
            "lost_and_dropped_column": "Brand",
            "cohort_dimension": "Brand_Lost",
            "cohort_activity_metric": "Sales",
        },
    )

    assert result.select("Brand_Lost").to_series().to_list() == [
        "Active",
        "Lost after PY",
        "Active",
        "Lost after PY",
    ]


def test_cohort_stacked_column_adapter_uses_metric_activity_for_fallback() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "PY", "AC", "AC"],
            "Sales": [10.0, 2.0, 11.0, 0.0],
            "Brand": ["Common", "Lost", "Common", "Lost"],
        }
    )
    params = legacy._legacy_param_dict(
        names,
        total=11.0,
        selected_periods=["PY", "AC"],
        period_totals={"PY": 12.0, "AC": 11.0},
        columns=frame.columns,
        date_period_choice=names["yearName"],
    )

    result = legacy._apply_legacy_cohort_columns(
        frame,
        names,
        params,
        {},
        {
            "lost_and_dropped_column": "Brand",
            "cohort_dimension": "Brand_Lost",
            "cohort_activity_metric": "Sales",
        },
    )
    labels = {
        row["Brand"]: row["Brand_Lost"]
        for row in result.filter(pl.col("Period") == "PY").iter_rows(named=True)
    }

    assert labels == {"Common": names["activeName"], "Lost": "Lost after PY"}



def test_all_mode_pareto_threshold_annotations_are_rendered() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import (
        _should_render_pareto_threshold_annotations,
    )

    assert _should_render_pareto_threshold_annotations(30, 30, "All", "All") is True
    assert _should_render_pareto_threshold_annotations(31, 30, "All", "All") is True
    assert _should_render_pareto_threshold_annotations(30, 30, "Top", "All") is False


def test_pareto_bar_colors_use_row_level_prepared_colors() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import _pareto_bar_color_list

    frame = pl.DataFrame(
        {
            "Product": ["A", "B", "C"],
            "Color": ["#111111", "#222222", "#333333"],
            "Color-Sales": ["#aaaaaa", "#bbbbbb", "#cccccc"],
        }
    ).lazy()

    assert _pareto_bar_color_list(
        frame,
        metric="Sales",
        col=1,
        base_color_name="Color",
        hyphen_name="-",
        fallback=["#ff0000"],
    ) == ["#111111", "#222222", "#333333"]
    assert _pareto_bar_color_list(
        frame,
        metric="Sales",
        col=2,
        base_color_name="Color",
        hyphen_name="-",
        fallback=["#ff0000"],
    ) == ["#aaaaaa", "#bbbbbb", "#cccccc"]


def test_pareto_zero_values_are_not_colored_negative() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.data.misc_charts_data_prep import color_pareto_classes
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Sales": [10.0, 0.0, -1.0],
            names["ratioName"]: [0.7, 1.0, 1.0],
        }
    ).lazy()
    chart = {names["colorpalette"]: names["bainColorpalette"]}

    classified, _class_colors, _color_list = color_pareto_classes(
        frame,
        "Sales",
        chart,
        {},
        names["colorName"],
        names["ratioName"],
        names["className"],
    )

    rows = classified.collect().to_dicts()

    assert rows[1][names["className"]] == names["cClassName"]
    assert rows[1][names["colorName"]] == "#999A9A"
    assert rows[2][names["className"]] == names["negativeClassName"]
    assert rows[2][names["colorName"]] == "#FF0000"


def test_pareto_bain_abc_colors_are_visually_separated() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.data.misc_charts_data_prep import color_pareto_classes
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Sales": [10.0, 5.0, 1.0],
            names["ratioName"]: [0.70, 0.90, 0.99],
        }
    ).lazy()
    chart = {names["colorpalette"]: names["bainColorpalette"]}

    classified, _class_colors, _color_list = color_pareto_classes(
        frame,
        "Sales",
        chart,
        {},
        names["colorName"],
        names["ratioName"],
        names["className"],
    )

    rows = classified.collect().to_dicts()

    assert [row[names["className"]] for row in rows] == [
        names["aClassName"],
        names["bClassName"],
        names["cClassName"],
    ]
    assert [row[names["colorName"]] for row in rows] == [
        "#343434",
        "#58585A",
        "#999A9A",
    ]


def test_dense_pareto_item_tick_labels_are_suppressed() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import _pareto_item_tick_axis_update

    frame = pl.DataFrame({"Product": ["A", "B", "C"]}).lazy()

    assert _pareto_item_tick_axis_update(
        frame,
        dimension_column="Product",
        tick_values=[0, 1, 2],
        df_height=3,
        max_visible_item_labels=3,
    ) == {
        "tickmode": "array",
        "tickvals": [0, 1, 2],
        "ticktext": ["A", "B", "C"],
    }
    assert _pareto_item_tick_axis_update(
        frame,
        dimension_column="Product",
        tick_values=[0, 1, 2],
        df_height=4,
        max_visible_item_labels=3,
    ) == {"tickmode": "array", "tickvals": [], "ticktext": []}


def test_pareto_class_trace_coordinates_do_not_connect_gaps() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import _pareto_class_trace_coordinates

    frame = pl.DataFrame(
        {
            "Ratio": [0.1, 0.2, 0.3, 0.4],
            "Class": ["A", "B", "A", "A"],
        }
    ).lazy()

    assert _pareto_class_trace_coordinates(
        frame,
        ratio_column="Ratio",
        class_column="Class",
        class_value="A",
        y_values=[10, 20, 30, 40],
    ) == ([0.1, None, 0.3, 0.4], [10, None, 30, 40])


def test_pareto_prompt_uses_standard_thresholds_with_negative_tail() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import get_data_for_pareto_prompt
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            names["countRank"]: [1, 2, 3, 4, 5],
            names["ratioName"]: [0.5, 0.8, 0.95, 1.0, 1.0],
            names["className"]: ["A", "B", "C", "Negative", "Negative"],
        }
    ).lazy()
    chart = {
        names["countColumn"]: "Product",
        names["plotCommentText"]: [],
    }

    messages, ranks, _indices, percents, _chart = get_data_for_pareto_prompt(
        frame,
        "Sales",
        names["ratioName"],
        ["A", "B", "C", "Negative"],
        [],
        [],
        1,
        chart,
    )

    assert ranks == [2, 3, 5]
    assert percents == [0.80, 0.95, 1]
    assert "458%" not in " ".join(messages)
    assert messages == [
        "2 (40%) Products for 80% of Sales",
        "3 (60%) Products for 95% of Sales",
        "5 Products for 100% of Sales",
    ]


def test_pareto_secondary_metric_uses_primary_metric_rank_breaks() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.charting.draw_pareto import get_data_for_pareto_prompt
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            names["countRank"]: [1, 2, 3, 4],
            "Ratio-Units": [0.2, 0.7, 0.9, 1.0],
            names["className"]: ["A", "A", "B", "C"],
        }
    ).lazy()
    chart = {
        names["countColumn"]: "Product",
        names["plotCommentText"]: [],
    }

    messages, ranks, _indices, percents, _chart = get_data_for_pareto_prompt(
        frame,
        "Units",
        "Ratio-Units",
        ["A", "B", "C"],
        [2, 3, 4],
        [1, 2, 3],
        2,
        chart,
    )

    assert ranks == [2, 3, 4]
    assert percents == [0.80, 0.95, 1]
    assert messages == [
        "2 (50%) Products for 70% of Units",
        "3 (75%) Products for 90% of Units",
        "4 Products for 100% of Units",
    ]







def test_stacked_column_synthesis_spec_uses_multiple_dimensions() -> None:
    core = load_core()
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": value,
                "Productline": productline,
                "Category": category,
                "Region": region,
            }
            for period, value in (("PL", 10.0), ("AC", 12.0))
            for productline, category, region in (
                ("Bikes", "Road", "Australia"),
                ("Accessories", "Helmets", "Canada"),
            )
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": ["Productline", "Category", "Region"],
        },
        "options": {},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert specs["stacked_column_synthesis"]["dimensions"] == [
        "Productline",
        "Category",
        "Region",
    ]
    assert specs["stacked_column_synthesis"]["synthesis_plot"] is True
    assert specs["stacked_column_synthesis"]["capture_figure"] == "last"
    assert specs["stacked_column_synthesis"]["synthesis_uniform_palette"] is True
    assert specs["stacked_column_synthesis"]["selected_periods"] == ["AC"]


def test_multitier_bar_dimension_panels_are_not_named_small_multiples() -> None:
    core = load_core()
    dimensions = [
        "Productline",
        "Category",
        "Region",
        "Channel",
        "Brand",
        "Customer",
    ]
    canonical = pl.DataFrame(
        [
            {
                "Period": period,
                "Sales": float(index + 1),
                "Productline": f"Line {index}",
                "Category": f"Category {index}",
                "Region": f"Region {index}",
                "Channel": f"Channel {index}",
                "Brand": f"Brand {index}",
                "Customer": f"Customer {index}",
            }
            for period in ("PY", "AC")
            for index in range(2)
        ]
    )
    recipe = {
        "mappings": {
            "amount_column": "Sales",
            "dimensions": dimensions,
        },
        "options": {"small_multiples": True, "small_multiples_max_panels": 6},
    }

    specs = {spec["name"]: spec for spec in core.build_chart_specs(canonical, recipe)}

    assert "multitier_bar_small_multiples" not in specs
    multitier_spec = specs["multitier_bar_dimension_panels"]
    assert multitier_spec["dimensions"] == dimensions
    assert multitier_spec["x_dimension"] is None
    assert multitier_spec["y_dimension"] is None
    assert multitier_spec["small_multiples_dimension"] is None
    assert multitier_spec["capture_figure"] == "last"
    assert multitier_spec["dimension_panel_chart"] is True


def test_legacy_multitier_dimension_panel_chart_omits_axis_dimension_key() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Productline", "Category", "Region"],
            "dimension_panel_chart": True,
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
        },
        metric="Sales",
        currency="EUR",
    )

    assert names["xAxisDimension"] not in chart
    assert names["yAxisDimension"] not in chart
    assert chart[names["selectDimensionsToPlot"]] == [
        "Productline",
        "Category",
        "Region",
    ]
    assert chart[names["plotSmallMultiplesOtherCharts"]] == names["metConditionValue"]


def test_legacy_multitier_dimension_panel_items_rank_independently() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.charting.draw_multitier import _dimension_panel_param_dict
    from modules.data.misc_charts_data_prep import prepare_data_for_multitier_bar_plot
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame(
        {
            "Period": ["PY", "AC"] * 6,
            "Company": ["L", "L", "C", "C", "R", "R", "H", "H", "B", "B", "P", "P"],
            "Brand": [
                "Koleston",
                "Koleston",
                "Nutrisse",
                "Nutrisse",
                "Excellence",
                "Excellence",
                "Casting",
                "Casting",
                "Preference",
                "Preference",
                "Colorsilk",
                "Colorsilk",
            ],
            "Sales": [
                40.0,
                100.0,
                30.0,
                80.0,
                20.0,
                60.0,
                10.0,
                50.0,
                5.0,
                40.0,
                3.0,
                30.0,
            ],
        }
    )
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "multitierBarChart",
            "dimensions": ["Company", "Brand"],
            "dimension_panel_chart": True,
            "metrics": ["Sales"],
            "selected_periods": ["PY", "AC"],
            "max_items": 4,
            "aggregate_other_items": False,
        },
        metric="Sales",
        currency="EUR",
    )
    param = legacy._legacy_param_dict(
        names,
        total=0.0,
        selected_periods=["PY", "AC"],
        period_totals={},
        columns=frame.columns,
        date_period_choice=chart[names["datePeriodName"]],
    )
    param[names["globalUniqueItemsArray"]] = ["L", "C", "R", "H"]

    panel_param = _dimension_panel_param_dict(param)
    prepared, unique_items, _panel_param = prepare_data_for_multitier_bar_plot(
        frame.lazy(),
        "Brand",
        "Period",
        "Sales",
        ["Sales"],
        chart,
        panel_param,
        "X",
    )

    assert param[names["globalUniqueItemsArray"]] == ["L", "C", "R", "H"]
    assert panel_param[names["globalUniqueItemsArray"]] == []
    assert unique_items == ["Koleston", "Nutrisse", "Excellence", "Casting"]
    assert prepared.collect()["Brand"].to_list() == [
        "Casting",
        "Excellence",
        "Nutrisse",
        "Koleston",
    ]


def test_synthesis_dimension_label_cleanup_uses_dimension_headers() -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def __init__(self) -> None:
            self.layout = SimpleNamespace(
                annotations=[
                    SimpleNamespace(text="Total<br><b>31.4</b>"),
                    SimpleNamespace(text="<b>Sales</b> in mEUR by dimension<br>AC"),
                ]
            )
            self.data = [
                SimpleNamespace(
                    name="by Bikes",
                    x=[0, 1],
                    y=[70.0, None],
                    text=["by Bikes 0.0", "by Bikes 0.0"],
                    marker=SimpleNamespace(color="#343434"),
                ),
                SimpleNamespace(
                    name="by Australia",
                    x=[0, 1],
                    y=[None, 40.0],
                    text=["by Australia 0.0", "by Australia 0.0"],
                    marker=SimpleNamespace(color="#808080"),
                ),
            ]
            self.xaxes: dict[str, Any] = {}

        def update_xaxes(self, **kwargs: Any) -> None:
            self.xaxes.update(kwargs)

        def add_annotation(self, **kwargs: Any) -> None:
            self.layout.annotations.append(SimpleNamespace(**kwargs))

    figure = FakeFigure()

    legacy._apply_synthesis_dimension_labels([figure], ["Productline", "Region"])

    assert figure.xaxes["tickvals"] == [0.5, 1.5]
    assert figure.xaxes["ticktext"] == ["Productline", "Region"]
    assert figure.xaxes["side"] == "bottom"
    assert [annotation.text for annotation in figure.layout.annotations] == [
        "Total<br><b>31.4</b>",
        "<b>Sales</b> in mEUR by dimension<br>AC",
        "100%",
        "100%",
    ]
    assert [
        (annotation.x, annotation.y, annotation.xref, annotation.yref)
        for annotation in figure.layout.annotations[-2:]
    ] == [
        (0.5, 1.0, "x", "paper"),
        (1.5, 1.0, "x", "paper"),
    ]
    assert [annotation.yshift for annotation in figure.layout.annotations[-2:]] == [
        -14,
        -14,
    ]
    assert [
        annotation.font["size"] for annotation in figure.layout.annotations[-2:]
    ] == [
        12,
        12,
    ]
    assert figure.data[0].name == "Bikes"
    assert figure.data[0].text == ["Bikes 70%", ""]
    assert figure.data[1].name == "Australia"
    assert figure.data[1].text == ["", "Australia 40%"]


def test_period_display_label_replaces_bare_ac_title_line() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            title=SimpleNamespace(text="<b>Sales</b> in bEUR by dimension<br>AC"),
            annotations=[
                SimpleNamespace(text="<b>Sales</b> in bEUR by dimension<br>AC")
            ],
        )
    )

    legacy._apply_period_display_label_to_titles(
        [figure],
        {
            "selected_periods": ["AC"],
            "period_display_label": "AC, 2024-01-07 to 2024-03-31",
        },
    )

    assert figure.layout.title.text == (
        "<b>Sales</b> in bEUR by dimension<br>" "AC, 2024-01-07 to 2024-03-31"
    )
    assert figure.layout.annotations[0].text == figure.layout.title.text


def test_legacy_stacked_column_cleanup_formats_values_and_removes_growth() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(
                    text="<b>Sales</b> in mEUR by Brand_Lost<br>2015 to 2017"
                ),
                SimpleNamespace(text="-35.3%"),
                SimpleNamespace(text="CAGR<br>-17.8%"),
            ]
        ),
        data=[
            SimpleNamespace(
                type="bar",
                name="Active",
                text=["1.09", "0.74", "-35.3%"],
                y=[1.09, 0.74, None],
            )
        ],
    )

    legacy._apply_display_dimension_label(
        [figure],
        {
            "display_dimension_label": "Last active year",
            "cohort_dimension": "Brand_Lost",
        },
    )
    legacy._suppress_stacked_percentage_labels(
        [figure],
        {
            "suppress_stacked_percentage_annotations": True,
            "format_stacked_value_labels_like_totals": True,
        },
    )

    assert [annotation.text for annotation in figure.layout.annotations] == [
        "<b>Sales</b> in mEUR by Last active year<br>2015 to 2017",
        "CAGR<br>-17.8%",
    ]
    assert figure.data[0].text == ["", "", ""]


def test_legacy_percentage_cleanup_keeps_right_lane_cagr_labels() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="38.7%", xref="x", xanchor="left", xshift=120),
                SimpleNamespace(text="-35.3%", xref="x", xanchor="center", xshift=0),
            ]
        ),
        data=[],
    )

    legacy._suppress_stacked_percentage_labels(
        [figure],
        {"suppress_stacked_percentage_annotations": True},
    )

    assert [annotation.text for annotation in figure.layout.annotations] == ["38.7%"]


def test_legacy_stacked_value_labels_follow_total_precision_and_stay_horizontal() -> (
    None
):
    legacy = load_legacy_charting()
    periods = ["2015", "2016", "2017"]
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="361"),
                SimpleNamespace(text="1086"),
                SimpleNamespace(text="727"),
                SimpleNamespace(text="CAGR<br>+41.9%"),
            ]
        ),
        data=[
            SimpleNamespace(
                type="bar",
                name="Coty",
                x=periods,
                text=["114.6", "295.6", "216.7"],
                y=[114.6, 295.6, 216.7],
                textangle=90,
            ),
            SimpleNamespace(
                type="bar",
                name="Henkel",
                x=periods,
                text=["21.5", "66.5", "42.6"],
                y=[21.5, 66.5, 42.6],
                textangle=90,
            ),
        ],
    )

    legacy._suppress_stacked_percentage_labels(
        [figure],
        {"format_stacked_value_labels_like_totals": True},
    )

    assert figure.data[0].text == ["115", "296", "217"]
    assert figure.data[1].text == ["22", "67", "43"]
    assert figure.data[0].textangle == 0
    assert figure.data[1].textangle == 0


def test_legacy_lost_cohort_cleanup_suppresses_zero_rounded_labels() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="Active"),
                SimpleNamespace(text="Lost after 2016"),
            ]
        ),
        data=[
            SimpleNamespace(
                type="bar",
                name="Active",
                text=["0.36", "1.09"],
                y=[0.36, 1.09],
            ),
            SimpleNamespace(
                type="bar",
                name="Lost after 2016",
                text=["0.0", "0.04"],
                y=[0.0, 0.04],
            ),
        ],
    )

    legacy._suppress_stacked_percentage_labels(
        [figure],
        {
            "format_stacked_value_labels_like_totals": True,
            "suppress_zero_rounded_stacked_labels": True,
        },
    )

    assert [annotation.text for annotation in figure.layout.annotations] == ["Active"]
    assert figure.data[0].text == ["", ""]
    assert figure.data[1].text == ["", ""]


def test_legacy_since_cohort_cleanup_suppresses_single_segment_column_labels() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(annotations=[]),
        data=[
            SimpleNamespace(
                type="bar",
                name="Since 2015",
                text=["0.36", "1.09", "0.74"],
                y=[0.36, 1.09, 0.74],
            ),
            SimpleNamespace(
                type="bar",
                name="Since 2016",
                text=["0.0", "0.04", "0.03"],
                y=[None, 0.04, 0.03],
            ),
            SimpleNamespace(
                type="bar",
                name="Since 2017",
                text=["0.0", "0.0", "0.01"],
                y=[None, None, 0.01],
            ),
        ],
    )

    legacy._suppress_stacked_percentage_labels(
        [figure],
        {
            "format_stacked_value_labels_like_totals": True,
        },
    )

    assert figure.data[0].text == ["", "1.1", "0.7"]
    assert figure.data[1].text == ["0.0", "0.0", "0.0"]
    assert figure.data[2].text == ["0.0", "0.0", "0.0"]


def test_legacy_cohort_label_cleanup_unwraps_legacy_annotation_breaks() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="Lost after <BR>2016", hovertext="old"),
                SimpleNamespace(text="<b>Sales</b> in mEUR<br>2015 to 2017"),
            ]
        )
    )

    legacy._unwrap_cohort_label_annotations(
        [figure],
        {"cohort_kind": "lost"},
    )

    assert figure.layout.annotations[0].text == "Lost after 2016"
    assert figure.layout.annotations[0].hovertext == "Lost after 2016"
    assert figure.layout.annotations[1].text == ("<b>Sales</b> in mEUR<br>2015 to 2017")


def test_legacy_since_cohort_cleanup_spreads_overlapping_item_labels() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="Since 2015", x=2.4, y=0.35, xref="x", yref="y"),
                SimpleNamespace(text="Since 2016", x=2.4, y=0.715, xref="x", yref="y"),
                SimpleNamespace(text="Since 2017", x=2.4, y=0.72, xref="x", yref="y"),
                SimpleNamespace(text="0.7", x=2.0, y=0.74, xref="x", yref="y"),
            ]
        ),
        data=[
            SimpleNamespace(type="bar", name="Since 2015", y=[0.36, 1.07, 0.7]),
            SimpleNamespace(type="bar", name="Since 2016", y=[0.01, 0.02]),
            SimpleNamespace(type="bar", name="Since 2017", y=[0.01]),
        ],
    )

    legacy._spread_cohort_label_annotations(
        [figure],
        {"cohort_kind": "since"},
    )

    assert figure.layout.annotations[0].y == 0.35
    assert figure.layout.annotations[1].y == 0.715
    assert figure.layout.annotations[2].y > 0.75
    assert figure.layout.annotations[3].y == 0.74


def test_legacy_lost_cohort_cleanup_suppresses_single_active_value_labels() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(annotations=[SimpleNamespace(text="Active")]),
        data=[
            SimpleNamespace(
                type="bar",
                name="Active",
                text=None,
                texttemplate="%{y:.2f}",
                y=[1.09, 0.74],
            )
        ],
    )

    legacy._suppress_stacked_percentage_labels(
        [figure],
        {
            "format_stacked_value_labels_like_totals": True,
            "suppress_zero_rounded_stacked_labels": True,
            "suppress_single_active_value_label": True,
        },
    )

    assert [annotation.text for annotation in figure.layout.annotations] == ["Active"]
    assert figure.data[0].text == ["", ""]
    assert figure.data[0].texttemplate is None


def test_legacy_stacked_bar_two_dimension_keeps_category_axis() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        prepare_data_for_stacked_bar_two_dimensions,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline", "Category"],
            "x_dimension": "Productline",
            "y_dimension": "Category",
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
            "max_items": 5,
        },
        metric="Sales",
        currency="EUR",
    )
    frame = pl.DataFrame(
        {
            "Period": ["AC", "AC", "AC", "AC"],
            "Productline": ["A", "A", "B", "B"],
            "Category": ["Road", "Mountain", "Road", "Mountain"],
            "Sales": [10.0, 5.0, 3.0, 2.0],
        }
    )

    prepared, _metric, _colors, _used, _items = (
        prepare_data_for_stacked_bar_two_dimensions(
            frame,
            names["totalName"],
            ["Sales"],
            chart,
            {},
            {},
            ["#111111", "#888888", "#cccccc"],
            chart[names["chosenChart"]],
        )
    )

    assert prepared.collect_schema().names() == [
        "Productline",
        "Road",
        "Mountain",
        names["valueName"],
    ]


def test_legacy_stacked_bar_total_annotation_skips_missing_panel_total() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.draw_charts_utils import (
        add_total_annotations_for_stacked_bar,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline", "Region", "Category"],
            "x_dimension": "Productline",
            "y_dimension": "Region",
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
        },
        metric="Sales",
        currency="EUR",
    )
    width = pl.DataFrame(
        {"Productline": ["A"], names["valueName"]: [None]},
        schema={"Productline": pl.Utf8, names["valueName"]: pl.Float64},
    )
    half = pl.DataFrame({"Productline": ["A"], "halfColumn": [0.5]})

    figure = add_total_annotations_for_stacked_bar(
        make_subplots(rows=1, cols=1),
        "A",
        half.lazy(),
        width.lazy(),
        chart,
        1,
        1,
    )

    assert figure.layout.annotations[0].text == ""
    assert figure.layout.annotations[0].y == "A"


def test_legacy_stacked_bar_horizontal_axis_hides_scale_labels() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from plotly.subplots import make_subplots

    from modules.charting.update_layouts import update_xaxes_bar_width_plot_horizontal
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = legacy._legacy_chart_dict(
        names,
        {
            "legacy_chart_key": "stackedBarChart",
            "dimensions": ["Productline"],
            "x_dimension": "Productline",
            "y_dimension": None,
            "metrics": ["Sales"],
            "selected_periods": ["AC"],
        },
        metric="Sales",
        currency="EUR",
    )

    figure = update_xaxes_bar_width_plot_horizontal(
        make_subplots(rows=1, cols=1),
        [0, 1],
        ["0", "1"],
        [0, 1],
        {},
        chart,
    )

    assert figure.layout.xaxis.showticklabels is False






def test_mix_contribution_applies_like_for_like_recipe_cohort(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "mix_contribution"
    recipe_path = tmp_path / "recipe.json"
    pl.DataFrame(
        {
            "Scenario": ["PY", "AC", "AC", "PY", "AC", "PY"],
            "Orderdate": [
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
                "2025-01-31",
            ],
            "Productline": ["Common", "Common", "New", "Lost", "Zero PY", "Zero PY"],
            "Category": ["Core", "Core", "Core", "Core", "Core", "Core"],
            "Region": ["North", "North", "North", "North", "North", "North"],
            "Salesamount": [10.0, 12.0, 5.0, 7.0, 3.0, 0.0],
            "Units": [10, 12, 5, 7, 3, 1],
        }
    ).write_csv(input_path)
    recipe_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_file": str(input_path),
                "language": "en",
                "mappings": {
                    "period_column": "Scenario",
                    "date_column": "Orderdate",
                    "amount_column": "Salesamount",
                    "width_metric_column": "Units",
                    "dimensions": ["Productline"],
                },
                "options": {
                    "charts": ["stacked_bar"],
                    "period_grain": "raw",
                    "small_multiples": False,
                    "like_for_like": {"source_dimension": "Productline"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(core, "write_legacy_mix_chart", _fake_legacy_writer)

    result = core.run_mix_contribution(
        input_path,
        output_dir,
        recipe_path,
        language="en",
    )

    used_recipe = json.loads((output_dir / "used_recipe.json").read_text())
    retained_productlines = set(
        result.canonical_frame.select("Productline").unique().to_series().to_list()
    )
    cohort_audit = used_recipe["options"]["recipe_cohort_audit"]
    assert retained_productlines == {"Common"}
    assert cohort_audit["like_for_like"]["retained_entity_count"] == 1
    assert cohort_audit["like_for_like"]["removed_entity_count"] == 3
    assert used_recipe["options"]["cohort_definition"]["activity_rule"] == "Sales > 0.0"




def test_mix_contribution_keeps_legacy_failures_without_substitute(
    tmp_path: Path, monkeypatch: Any
) -> None:
    core = load_core()
    input_path = tmp_path / "sales.csv"
    output_dir = tmp_path / "mix_contribution"
    _write_mix_fixture(input_path)

    def fake_writer(
        _canonical: Any,
        _recipe: dict[str, Any],
        out_dir: Path,
        spec: dict[str, Any],
        **_kwargs: Any,
    ) -> Any:
        if spec["name"] == "marimekko":
            return SimpleNamespace(
                paths=[],
                audit={
                    "status": "failed_legacy",
                    "chart": "marimekko",
                    "error": "legacy failed",
                    "source_functions": ["modules.charting.run_charting.run_charting"],
                },
            )
        return _fake_legacy_writer(_canonical, _recipe, out_dir, spec)

    monkeypatch.setattr(core, "write_legacy_mix_chart", fake_writer)

    result = core.run_mix_contribution(input_path, output_dir, language="en")
    audit = result.audit

    assert audit["legacy_runtime"]["chart_audits"]["marimekko"]["status"] == (
        "failed_legacy"
    )
    assert audit["checks"]["legacy_chart_attempt_count"] == 17
    assert audit["checks"]["legacy_chart_written_count"] == 16
    assert not (output_dir / "marimekko.png").exists()


def test_mix_contribution_dependency_checker_lists_required_modules() -> None:
    checker = load_dependency_checker()

    assert {"polars", "plotly", "docx"}.issubset(set(checker.REQUIRED_MODULES))


def test_captured_figures_keep_base_name_for_first_artifact(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()
    requested_paths: list[Path] = []

    def fake_write_legacy_figure(
        _fig: Any, path: Path
    ) -> tuple[list[Path], dict[str, Any]]:
        requested_paths.append(path)
        return [path], {"artifact": path.name}

    monkeypatch.setattr(legacy, "_write_legacy_figure", fake_write_legacy_figure)
    notifier = SimpleNamespace(figures=[object(), object(), object()])

    paths, exports = legacy._write_captured_figures(
        notifier,
        tmp_path,
        "multitier_bar.png",
    )

    assert requested_paths == [
        tmp_path / "multitier_bar.png",
        tmp_path / "multitier_bar_2.png",
        tmp_path / "multitier_bar_3.png",
    ]
    assert paths == [
        str(tmp_path / "multitier_bar.png"),
        str(tmp_path / "multitier_bar_2.png"),
        str(tmp_path / "multitier_bar_3.png"),
    ]
    assert [export["artifact"] for export in exports] == [
        "multitier_bar.png",
        "multitier_bar_2.png",
        "multitier_bar_3.png",
    ]


def test_legacy_plotly_export_writes_html_when_png_export_is_unavailable(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("chrome unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>legacy plotly</html>", encoding="utf-8")

    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html",
        lambda *_args: "Headless Chrome executable was not found.",
    )
    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html_with_playwright",
        lambda *_args: "Playwright unavailable.",
    )

    paths, audit = legacy._write_legacy_figure(FakeFigure(), tmp_path / "chart.png")

    assert paths == [tmp_path / "chart.html"]
    assert (tmp_path / "chart.html").read_text(encoding="utf-8") == (
        "<html>legacy plotly</html>"
    )
    assert not (tmp_path / "chart.png").exists()
    assert audit["renderer"] == "legacy_plotly+html_only"
    assert audit["artifact"] == "chart.html"
    assert audit["plotly_export_error"] == "chrome unavailable"
    assert audit["screenshot_error"] == (
        "Chrome screenshot failed: Headless Chrome executable was not found.; "
        "Playwright screenshot failed: Playwright unavailable."
    )
    assert audit["chrome_screenshot_error"] == (
        "Headless Chrome executable was not found."
    )
    assert audit["playwright_screenshot_error"] == "Playwright unavailable."
    assert audit["export_width"] == 1400
    assert audit["export_height"] == 900


def test_legacy_plotly_export_does_not_use_static_png_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        layout = SimpleNamespace(
            width=900,
            height=650,
            title=SimpleNamespace(text="Sales<br>2016 to 2017"),
        )
        data = [
            SimpleNamespace(
                type="bar",
                orientation="v",
                x=["2016", "2017"],
                y=[100.0, 75.0],
                name="L'Oreal",
                marker=SimpleNamespace(color="#333333"),
            ),
            SimpleNamespace(
                type="bar",
                orientation="v",
                x=["2016", "2017"],
                y=[40.0, 25.0],
                name="Coty",
                marker=SimpleNamespace(color="#9E9E9E"),
            ),
        ]

        def update_layout(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self.layout, key, value)

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kaleido unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>legacy plotly</html>", encoding="utf-8")

    monkeypatch.setattr(legacy, "_screenshot_plotly_html", lambda *_args: "no chrome")
    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html_with_playwright",
        lambda *_args: "no playwright",
    )
    monkeypatch.setattr(
        legacy,
        "_write_static_column_png",
        lambda *_args: pytest.fail("static column fallback must not be called"),
    )
    monkeypatch.setattr(
        legacy,
        "_write_static_horizontal_bar_png",
        lambda *_args: pytest.fail("static horizontal fallback must not be called"),
    )

    paths, audit = legacy._write_legacy_figure(FakeFigure(), tmp_path / "chart.png")

    assert paths == [tmp_path / "chart.html"]
    assert not (tmp_path / "chart.png").exists()
    assert audit["renderer"] == "legacy_plotly+html_only"
    assert audit["artifact"] == "chart.html"
    assert audit["html_artifact"] == "chart.html"
    assert audit["plotly_export_error"] == "kaleido unavailable"
    assert audit["screenshot_error"] == (
        "Chrome screenshot failed: no chrome; "
        "Playwright screenshot failed: no playwright"
    )
    assert audit["chrome_screenshot_error"] == "no chrome"
    assert audit["playwright_screenshot_error"] == "no playwright"
    assert audit["static_fallback_policy"] == "disabled"


def test_static_total_labels_use_stacked_pareto_paper_annotations() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(
            annotations=[
                SimpleNamespace(text="A", xref="x", yref="paper", x=-0.2, y=0.38),
                SimpleNamespace(text="2.2", xref="x", yref="paper", x=0, y=1),
                SimpleNamespace(text="52.2", xref="x", yref="paper", x=1, y=1),
                SimpleNamespace(text="39", xref="x", yref="paper", x=2, y=1),
                SimpleNamespace(
                    text="<BR>ABC by sorted Brand Sales in EUR<BR>AC",
                    xref="paper",
                    yref="paper",
                    x=0,
                    y=1.012,
                ),
            ]
        )
    )
    categories = [
        {"key": "sales", "coord": 0.45},
        {"key": "units", "coord": 1.45},
        {"key": "count", "coord": 2.45},
    ]

    assert legacy._static_total_labels(figure, categories) == {
        "sales": "2.2",
        "units": "52.2",
        "count": "39",
    }


def test_stacked_pareto_total_labels_include_magnitude_suffixes() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["currencyChoice"]: "EUR",
        names["fullCurrencyName"]: "EUR",
        names["countColumn"]: "Brand",
    }

    assert (
        legacy._format_stacked_pareto_total_label(
            2_185_561_898,
            "Sales",
            chart,
            names,
            "# of Brand",
        )
        == "2.2bn"
    )
    assert (
        legacy._format_stacked_pareto_total_label(
            52_186_518,
            names["unitsName"],
            chart,
            names,
            "# of Brand",
        )
        == "52.2m"
    )
    assert (
        legacy._format_stacked_pareto_total_label(
            39,
            "# of Brand",
            chart,
            names,
            "# of Brand",
        )
        == "39"
    )


def test_stacked_pareto_axis_labels_include_metric_units() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["currencyChoice"]: "EUR",
        names["fullCurrencyName"]: "EUR",
        names["countColumn"]: "Brand",
    }

    assert legacy._stacked_pareto_axis_labels(
        ["Sales", names["unitsName"]],
        "# of Brand",
        chart,
        names,
    ) == ["Sales<br>EUR", "Units", "# of<br>Brand"]


def test_stacked_pareto_metric_order_keeps_data_metrics_before_work_column() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["metricsToPlot"]: ["Sales", names["unitsName"]],
        names["countColumn"]: "Brand",
        names["countByColumn"]: "# of Brand",
        names["showMetricsInDataColumn"]: True,
        names["metricsToShowInDataColumn"]: [names["pricePerUnitName"]],
    }

    assert legacy._stacked_pareto_metric_order(chart, names) == [
        "Sales",
        names["unitsName"],
        "# of Brand",
        names["pricePerUnitName"],
        names["workColumn"],
    ]


def test_stacked_pareto_side_metric_annotations_show_unit_price() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    chart = {
        names["metricsToPlot"]: ["Sales", names["unitsName"]],
        names["countColumn"]: "Brand",
        names["countByColumn"]: "# of Brand",
    }
    frame = pl.DataFrame(
        {
            "__stacked_pareto_metric": ["Sales", names["unitsName"], "# of Brand"],
            "A": [0.5, 0.25, 0.2],
            "B": [0.3, 0.5, 0.3],
            "C": [0.2, 0.25, 0.5],
            names["valueName"]: [100.0, None, None],
            names["unitsName"]: [10.0, None, None],
            "# of Brand": [3.0, None, None],
            names["workColumn"]: [0.0, None, None],
        }
    )

    payload = legacy._stacked_pareto_unit_price_payload(frame, chart, names)

    assert payload["metric"] == names["pricePerUnitName"]
    assert payload["total_text"] == "10"
    assert [segment["text"] for segment in payload["segments"]] == ["20", "6", "8"]

    class Figure:
        def __init__(self) -> None:
            self.data = [
                SimpleNamespace(x=[0, 1, 2], width=[0.9, 0.9, 0.9], offset=0),
            ]
            self.annotations: list[dict[str, Any]] = []

        def add_annotation(self, **kwargs: Any) -> None:
            self.annotations.append(kwargs)

    figure = Figure()

    legacy._add_stacked_pareto_side_metric_annotations(figure, frame, chart, names)

    assert [annotation["text"] for annotation in figure.annotations] == [
        "Unit Price<br>10",
        "20",
        "6",
        "8",
    ]


def test_stacked_pareto_total_positions_use_tick_centers() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(
        layout=SimpleNamespace(xaxis=SimpleNamespace(tickvals=[0.5, 1.5, 2.5]))
    )

    assert legacy._stacked_pareto_total_x_positions(figure, 3) == [0.5, 1.5, 2.5]


def test_stacked_pareto_total_positions_fallback_to_bar_centers() -> None:
    legacy = load_legacy_charting()
    figure = SimpleNamespace(layout=SimpleNamespace(xaxis=SimpleNamespace()))

    assert legacy._stacked_pareto_total_x_positions(figure, 3) == [0.5, 1.5, 2.5]


def test_legacy_plotly_export_removes_stale_png_when_export_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kaleido unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>fresh legacy plotly</html>", encoding="utf-8")

    stale_png = tmp_path / "chart.png"
    stale_png.write_bytes(b"stale png")
    monkeypatch.setattr(legacy, "_screenshot_plotly_html", lambda *_args: "no chrome")
    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html_with_playwright",
        lambda *_args: "no playwright",
    )

    paths, audit = legacy._write_legacy_figure(FakeFigure(), stale_png)

    assert paths == [tmp_path / "chart.html"]
    assert not stale_png.exists()
    assert (tmp_path / "chart.html").read_text(encoding="utf-8") == (
        "<html>fresh legacy plotly</html>"
    )
    assert audit["renderer"] == "legacy_plotly+html_only"
    assert audit["artifact"] == "chart.html"


def test_legacy_plotly_export_removes_stale_html_after_png_success(
    tmp_path: Path,
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, path: str, *_args: Any, **_kwargs: Any) -> None:
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\nlegacy")

    stale_html = tmp_path / "chart.html"
    stale_html.write_text("<html>stale</html>", encoding="utf-8")

    paths, audit = legacy._write_legacy_figure(FakeFigure(), tmp_path / "chart.png")

    assert paths == [tmp_path / "chart.png"]
    assert (tmp_path / "chart.png").read_bytes().startswith(b"\x89PNG")
    assert not stale_html.exists()
    assert audit["renderer"] == "legacy_plotly+kaleido"
    assert audit["html_artifact"] is None


def test_legacy_plotly_export_replaces_stale_png_with_screenshot(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kaleido unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>legacy plotly</html>", encoding="utf-8")

    target_png = tmp_path / "chart.png"
    target_png.write_bytes(b"stale png")

    def fake_screenshot(
        _html_path: Path, png_path: Path, _width: int, _height: int
    ) -> None:
        assert not png_path.exists()
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfresh screenshot")
        return None

    monkeypatch.setattr(legacy, "_screenshot_plotly_html", fake_screenshot)

    paths, audit = legacy._write_legacy_figure(FakeFigure(), target_png)

    assert paths == [tmp_path / "chart.html", target_png]
    assert target_png.read_bytes().endswith(b"fresh screenshot")
    assert audit["renderer"] == "legacy_plotly+html_chrome_screenshot"
    assert audit["artifact"] == "chart.png"


def test_legacy_plotly_export_records_chrome_screenshot_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kaleido unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>legacy plotly</html>", encoding="utf-8")

    def fake_screenshot(
        html_path: Path, png_path: Path, width: int, height: int
    ) -> None:
        assert html_path == tmp_path / "chart.html"
        assert width == 1400
        assert height == 900
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nlegacy")
        return None

    monkeypatch.setattr(legacy, "_screenshot_plotly_html", fake_screenshot)

    paths, audit = legacy._write_legacy_figure(FakeFigure(), tmp_path / "chart.png")

    assert paths == [tmp_path / "chart.html", tmp_path / "chart.png"]
    assert (tmp_path / "chart.png").read_bytes().startswith(b"\x89PNG")
    assert audit["renderer"] == "legacy_plotly+html_chrome_screenshot"
    assert audit["artifact"] == "chart.png"
    assert audit["html_artifact"] == "chart.html"
    assert audit["plotly_export_error"] == "kaleido unavailable"
    assert audit["screenshot_error"] is None
    assert audit["chrome_screenshot_error"] is None
    assert audit["playwright_screenshot_error"] is None


def test_legacy_plotly_export_records_playwright_screenshot_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    legacy = load_legacy_charting()

    class FakeFigure:
        def update_layout(self, **_kwargs: Any) -> None:
            return None

        def write_image(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("kaleido unavailable")

        def write_html(self, path: str, **_kwargs: Any) -> None:
            Path(path).write_text("<html>legacy plotly</html>", encoding="utf-8")

    def fake_playwright_screenshot(
        html_path: Path, png_path: Path, width: int, height: int
    ) -> None:
        assert html_path == tmp_path / "chart.html"
        assert width == 1400
        assert height == 900
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nlegacy")
        return None

    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html",
        lambda *_args: "chrome failed",
    )
    monkeypatch.setattr(
        legacy,
        "_screenshot_plotly_html_with_playwright",
        fake_playwright_screenshot,
    )

    paths, audit = legacy._write_legacy_figure(FakeFigure(), tmp_path / "chart.png")

    assert paths == [tmp_path / "chart.html", tmp_path / "chart.png"]
    assert (tmp_path / "chart.png").read_bytes().startswith(b"\x89PNG")
    assert audit["renderer"] == "legacy_plotly+html_playwright_screenshot"
    assert audit["artifact"] == "chart.png"
    assert audit["html_artifact"] == "chart.html"
    assert audit["plotly_export_error"] == "kaleido unavailable"
    assert audit["screenshot_error"] is None
    assert audit["chrome_screenshot_error"] == "chrome failed"
    assert audit["playwright_screenshot_error"] is None


def test_legacy_lazyframe_get_column_compatibility_shim() -> None:
    legacy = load_legacy_charting()

    legacy._install_polars_headless_compat()

    values = pl.DataFrame({"value": [1, 2]}).lazy().get_column("value").to_list()
    assert values == [1, 2]


def test_legacy_transpose_chart_frame_replaces_pandas_transpose() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.utils import transpose_chart_frame

    frame = pl.DataFrame(
        {
            "Item": ["Road", "Mountain"],
            "Sales": [10.0, 20.0],
            "Units": [1.0, 2.0],
        }
    ).lazy()

    transposed = transpose_chart_frame(
        frame, header_name="Value", column_names="Item"
    ).collect()

    assert transposed.columns == ["Value", "Road", "Mountain"]
    assert transposed.get_column("Value").to_list() == ["Sales", "Units"]


def test_legacy_empty_rows_do_not_coerce_numeric_columns_to_text() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.data.multidimensional_charts_prep import (
        add_empty_rows_if_not_hierarchical,
    )
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    frame = pl.DataFrame({"F": [1.0], "M": [2.0], "Value": [3.0]}).lazy()

    result = add_empty_rows_if_not_hierarchical(
        frame,
        {names["showTopForEachItem"]: False},
        "Productline",
        ["Road Bikes", "Mountain Bikes"],
        ["Road Bikes"],
        ["Road Bikes", "Mountain Bikes"],
    ).collect()

    assert result.schema["F"] == pl.Float64
    assert result.schema["M"] == pl.Float64
    assert result.schema["Value"] == pl.Float64
    assert result.schema["Productline"] == pl.String
    assert "Mountain Bikes" in result.get_column("Productline").to_list()


def test_legacy_utf8_sort_replaces_removed_categorical_set_ordering() -> None:
    legacy = load_legacy_charting()
    legacy._ensure_legacy_import_path()

    from modules.utilities.utils import sort_utf8_lazy

    frame = pl.DataFrame({"item": ["B", None, "A"], "value": [2, 0, 1]}).lazy()

    sorted_frame = sort_utf8_lazy(frame, "item").collect()

    assert sorted_frame.get_column("item").to_list() == ["", "A", "B"]
