"""Headless adapters for the vendored legacy period-comparison charts."""

from __future__ import annotations

import calendar
import contextlib
import copy
import math
import os
import re
import shutil
import subprocess
import sys
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import polars as pl

__all__ = [
    "LegacyChartExport",
    "write_legacy_actual_vs_previous_year_chart",
    "write_legacy_dot_chart",
    "write_legacy_horizontal_waterfall_chart",
    "write_legacy_multitier_column_chart",
    "write_legacy_slope_chart",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PLUGIN_ROOT / "vendor"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"


def _legacy_import_parent() -> Path:
    """Return shared modules in the repo or this component's packaged vendor."""

    if (SHARED_VENDOR_ROOT / "modules" / "__init__.py").exists():
        return SHARED_VENDOR_ROOT
    return VENDOR_ROOT


def _activate_legacy_import_parent() -> Path:
    """Prioritize the selected vendor and evict incompatible ``modules`` imports."""

    legacy_parent = _legacy_import_parent()
    legacy_text = str(legacy_parent)
    while legacy_text in sys.path:
        sys.path.remove(legacy_text)
    sys.path.insert(0, legacy_text)
    module_root = (legacy_parent / "modules").resolve()
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            if not module_file or not Path(module_file).resolve().is_relative_to(
                module_root
            ):
                del sys.modules[name]
    return legacy_parent


_activate_legacy_import_parent()
from modules.chart_harness import (  # noqa: E402
    ReportingTitleContract,
    apply_three_row_plotly_title,
    plain_plotly_title_text,
    plotly_title_lines,
    reporting_entity_label_from_recipe,
    reporting_period_line_from_recipe,
)
from modules.charting.static_export import (  # noqa: E402
    normalize_plotly_figure_for_static_export,
)

CANONICAL_DATE = "Date"
CANONICAL_PERIOD = "Period"
CURRENT_PERIOD = "AC"
PREVIOUS_PERIOD = "PY"
TOLERANCE = 1e-9
YTD_AVERAGE_SUFFIX = "Æ"
HEADLESS_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
SLOPE_SINGLE_EXPORT_WIDTH = 760
SLOPE_SINGLE_EXPORT_HEIGHT = 620
SLOPE_SMALL_MULTIPLE_BASE_WIDTH = 160
SLOPE_SMALL_MULTIPLE_PANEL_WIDTH = 300
SLOPE_SMALL_MULTIPLE_EXPORT_HEIGHT = 560
SLOPE_SMALL_MULTIPLE_MAX_WIDTH = 1800


@dataclass(frozen=True)
class LegacyChartExport:
    """Exported paths and audit information for one legacy chart."""

    paths: list[str]
    audit: dict[str, Any]


class _DummyTab:
    def __enter__(self) -> "_DummyTab":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _LegacyCaptureNotifier:
    """Capture figures that the legacy UI code sends to Streamlit."""

    def __init__(self) -> None:
        self.figures: list[Any] = []
        self.events: list[dict[str, Any]] = []

    def tabs(self, labels: list[str]) -> list[_DummyTab]:
        self.events.append({"method": "tabs", "labels": list(labels)})
        return [_DummyTab() for _label in labels]

    def plotly_chart(self, fig: Any, **_kwargs: Any) -> None:
        self.figures.append(fig)

    def dataframe(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def notify(
        self,
        level: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "method": "notify",
                "level": level,
                "message": message,
                "context": context or {},
            }
        )

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def _noop(*args: Any, **_kwargs: Any) -> str:
            self.events.append({"method": name, "args": [str(arg) for arg in args[:3]]})
            return ""

        return _noop


def _ensure_legacy_import_path() -> None:
    _activate_legacy_import_parent()


@contextlib.contextmanager
def _capture_legacy_ui() -> Any:
    _ensure_legacy_import_path()
    from modules.utilities.ui_notifier import use_ui_notifier

    notifier = _LegacyCaptureNotifier()
    with use_ui_notifier(notifier):
        yield notifier


def _period_window(recipe: dict[str, Any]) -> tuple[date, date]:
    window = (recipe.get("options") or {}).get("period_window") or {}
    current = window.get("current") or {}
    previous = window.get("previous") or {}
    current_end = current.get("end_date")
    previous_start = previous.get("start_date")
    if current_end:
        most_recent = date.fromisoformat(str(current_end))
    else:
        current_year = int(current.get("year"))
        month_cutoff = int(current.get("month_cutoff"))
        most_recent = date(
            current_year,
            month_cutoff,
            calendar.monthrange(current_year, month_cutoff)[1],
        )
    least_recent = (
        date.fromisoformat(str(previous_start))
        if previous_start
        else date(int(previous.get("year")), 1, 1)
    )
    return (
        most_recent,
        least_recent,
    )


def _period_totals(canonical: pl.DataFrame, metric: str) -> tuple[float, float]:
    grouped = canonical.group_by(CANONICAL_PERIOD).agg(
        pl.col(metric).sum().alias("value")
    )
    values = {
        row[CANONICAL_PERIOD]: float(row["value"] or 0.0) for row in grouped.to_dicts()
    }
    previous = values.get(PREVIOUS_PERIOD, 0.0)
    current = values.get(CURRENT_PERIOD, 0.0)
    return previous, current


def _reporting_metric_label(recipe: dict[str, Any], metric: str) -> str:
    """Return the business-facing label for source metric names."""

    options = recipe.get("options") or {}
    for key in (
        "reporting_metric_label",
        "metric_label",
        "measure_label",
        "value_label",
    ):
        label = str(options.get(key) or "").strip()
        if label:
            return label

    normalized = "".join(ch for ch in metric.casefold() if ch.isalnum())
    sales_names = {
        "amount",
        "sales",
        "salesamount",
        "salesvalue",
        "netsales",
        "netrevenue",
        "revenue",
        "turnover",
        "valuelc",
        "valueusd",
        "valueeur",
    }
    unit_names = {"unit", "units", "quantity", "qty", "volume"}
    if normalized in sales_names or (
        normalized.startswith("value")
        and any(token in normalized for token in ("lc", "usd", "eur", "gbp"))
    ):
        return "Sales"
    if normalized in unit_names:
        return "Units"
    return metric.replace("_", " ").replace("-", " ").strip().title() or "Value"


def _reporting_entity(recipe: dict[str, Any]) -> str | None:
    return reporting_entity_label_from_recipe(recipe) or None


def _period_to_date_average_label(recipe: dict[str, Any]) -> str:
    options = recipe.get("options") or {}
    window = options.get("period_window") or {}
    current = window.get("current") or {}
    cutoff = int(current.get("month_cutoff") or date.today().month)
    month = date(2000, cutoff, 1).strftime("%b")
    return f"_{month}{YTD_AVERAGE_SUFFIX}"


def _current_period_month_labels(canonical: pl.DataFrame) -> list[str]:
    current_months = (
        canonical.filter(pl.col(CANONICAL_PERIOD) == CURRENT_PERIOD)
        .select(
            pl.col(CANONICAL_DATE).dt.month().alias("_month"),
            pl.col(CANONICAL_DATE)
            .min()
            .over(pl.col(CANONICAL_DATE).dt.month())
            .alias("_first_date"),
        )
        .unique("_month")
        .sort("_first_date")
    )
    return [
        date(2000, int(row["_month"]), 1).strftime("%b")
        for row in current_months.to_dicts()
    ]


def _by_period_labels() -> list[str]:
    return ["52w", "26w", "13w", "4w"]


def _legacy_chart_dict(
    names: dict[str, str],
    chosen_chart: str,
    *,
    metric: str,
    currency: str,
    reporting_entity: str | None = None,
    small_multiples: bool = False,
    selected_dimension: str | None = None,
    variance_chart: bool = False,
) -> dict[str, Any]:
    max_items = 12
    top_axis = {
        names["numberOfTop"]: max_items,
        names["aggregateOtherItems"]: True,
    }
    chart = {
        names["chosenChart"]: chosen_chart,
        names["selectedPeriods"]: [PREVIOUS_PERIOD, CURRENT_PERIOD],
        names["plotSmallMultiplesOtherCharts"]: small_multiples,
        names["plotSmallMultiplesWaterfall"]: small_multiples,
        names["smallMultiplesColumn"]: selected_dimension,
        names["numberOfPlottedSmallMultiples"]: max_items if selected_dimension else 0,
        names["showInitialAndFinalValues"]: True,
        names["colorChoice"]: names["redToGreen"],
        names["colorpalette"]: names["IBCSColorpalette"],
        names["varianceAggregation"]: names["totalVarianceAggregation"],
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["filterDates"]: False,
        names["shareOfTotalMarket"]: False,
        names["varianceInPercent"]: False,
        names["plotAsBaseline"]: False,
        names["plotValuesAsChoice"]: names["absolute"],
        names["rowToPlotName"]: names["entireDatasetName"],
        names["metricsToPlot"]: [metric],
        names["singleMetric"]: metric,
        names["selectDimensionsToPlot"]: (
            [selected_dimension] if selected_dimension else []
        ),
        names["canPlotYearToYear"]: True,
        names["setTimePeriodTabLabel"]: names["comparePeriods"],
        names["processingChoice"]: names["runOneDimensionalAnalysis"],
        names["varianceAnalysisChart"]: variance_chart,
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
        "X": dict(top_axis),
        "Y": dict(top_axis),
        "W": dict(top_axis),
    }
    if reporting_entity:
        chart[names["companyName"]] = reporting_entity
    if selected_dimension:
        chart[names["mainDimension"]] = [selected_dimension]
    return chart


def _monthly_metric_frame(canonical: pl.DataFrame, metric: str) -> pl.DataFrame:
    if metric not in canonical.schema:
        return pl.DataFrame({metric: [0.0]})
    return canonical.group_by([CANONICAL_DATE, CANONICAL_PERIOD]).agg(
        pl.col(metric).sum().alias(metric)
    )


def _legacy_param_dict(
    names: dict[str, str],
    recipe: dict[str, Any],
    *,
    previous_total: float,
    current_total: float,
) -> dict[str, Any]:
    most_recent, least_recent = _period_window(recipe)
    not_met = names["notMetConditionValue"]
    param = {
        names["columnHash"]: {},
        names["mostRecentDate"]: most_recent,
        names["leastRecentDate"]: least_recent,
        names["periodLengthInMonths"]: 12,
        names["fileUploadDisabled"]: True,
        names["renameTitlesDict"]: {},
        names["isFilteredKey"]: not_met,
        names["numberOfPeriodsFound"]: 2,
        names["impossibleToProcessFile"]: False,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["allPeriodsList"]: [PREVIOUS_PERIOD, CURRENT_PERIOD],
        names["selectedPeriods"]: [PREVIOUS_PERIOD, CURRENT_PERIOD],
        names["datePeriodName"]: names["monthName"],
        names["totalAmountPeriodZero"]: previous_total,
        names["totalAmountPeriodOne"]: current_total,
        names["totalVarianceValue"]: current_total - previous_total,
        names["totalAmountPeriodZeroFiltered"]: previous_total,
        names["totalAmountPeriodOneFiltered"]: current_total,
        names["periodZeroSum"]: previous_total,
        names["periodOneSum"]: current_total,
    }
    return param


def _legacy_ready_frame(canonical: pl.DataFrame) -> pl.DataFrame:
    if CANONICAL_DATE not in canonical.schema:
        return canonical
    return canonical.with_columns(pl.col(CANONICAL_DATE).cast(pl.Datetime))


def _legacy_index_columns(recipe: dict[str, Any]) -> list[str]:
    return [str(item) for item in recipe["mappings"].get("dimensions") or []]


def _legacy_df_dict(
    names: dict[str, str], frame: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    return {
        names["dfDatesName"]: frame,
        names["dfPeriodsName"]: frame,
        names["dfAllPeriodsName"]: frame,
        names["dfSnapshotName"]: frame,
    }


def _legacy_source_functions(plotter_name: str) -> list[str]:
    draw_functions = {
        "plot_actual_vs_previous_year_charts": (
            "modules.charting.draw_other_charts.draw_actual_vs_previous_year_chart"
        ),
        "plot_horizontal_waterfall_chart": (
            "modules.charting.draw_waterfall.draw_horizontal_waterfall_chart"
        ),
        "plot_multitier_column_chart": (
            "modules.charting.draw_multitier.draw_multitier_column_chart"
        ),
        "plot_dot_chart": "modules.charting.draw_timeline.draw_dot_chart",
        "plot_slope_charts": "modules.charting.draw_timeline.draw_slope_chart",
        "plot_trend_comparison_charts": (
            "modules.charting.draw_other_charts.draw_actual_vs_previous_year_chart"
        ),
    }
    functions = [
        "modules.charting.run_charting.run_charting",
        f"modules.charting.plot_charts.{plotter_name}",
        draw_functions[plotter_name],
    ]
    if plotter_name in {
        "plot_actual_vs_previous_year_charts",
        "plot_horizontal_waterfall_chart",
        "plot_multitier_column_chart",
        "plot_trend_comparison_charts",
    }:
        functions.insert(
            1, "modules.charting.chart_helpers.prepare_actual_vs_year_ago_dataframe"
        )
    if plotter_name == "plot_slope_charts":
        functions.insert(
            1, "modules.data.time_series_data_prep.prepare_data_for_slope_plot"
        )
    return functions


def _legacy_dimension(
    recipe: dict[str, Any], selected_dimension: str | None = None
) -> str | None:
    if selected_dimension:
        return selected_dimension
    configured = (recipe.get("options") or {}).get("small_multiples_dimension")
    if configured:
        return str(configured)
    dimensions = [str(item) for item in recipe["mappings"].get("dimensions") or []]
    return dimensions[0] if dimensions else None


def _prepare_legacy_year_over_year_frame(
    canonical: pl.DataFrame,
    names: dict[str, str],
    recipe: dict[str, Any],
    chart: dict[str, Any],
    param: dict[str, Any],
    chosen_chart: str,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    from modules.charting.chart_helpers import prepare_actual_vs_year_ago_dataframe

    metric = str(recipe["mappings"]["amount_column"])
    prepared, param = prepare_actual_vs_year_ago_dataframe(
        _legacy_ready_frame(canonical),
        chosen_chart,
        [metric],
        _legacy_index_columns(recipe),
        chart,
        param,
    )
    if isinstance(prepared, pl.LazyFrame):
        prepared = prepared.collect(engine="streaming")
    sort_columns = [
        column
        for column in [CANONICAL_DATE, CANONICAL_PERIOD]
        if column in prepared.columns
    ]
    sort_columns.extend(
        column for column in _legacy_index_columns(recipe) if column in prepared.columns
    )
    if sort_columns:
        prepared = prepared.sort(sort_columns)
    return prepared, param


def _write_full_legacy_plot(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str,
    chosen_chart_name: str,
    plotter_name: str,
    small_multiples_dimension: str | None = None,
    variance_chart: bool = False,
    prepare_year_over_year: bool = True,
    selected_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    fig, chosen_chart = _capture_full_legacy_plot(
        canonical,
        recipe,
        artifact_name=artifact_name,
        chosen_chart_name=chosen_chart_name,
        small_multiples_dimension=small_multiples_dimension,
        variance_chart=variance_chart,
        prepare_year_over_year=prepare_year_over_year,
        selected_dimension=selected_dimension,
        repeat_values=repeat_values,
    )
    if not render:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "data_written",
                "artifact": artifact_name,
                "rendered": False,
                "dimension": small_multiples_dimension or selected_dimension,
                "source_functions": _legacy_source_functions(plotter_name),
            },
        )
    path = output_dir / artifact_name
    export_fig, capture_normalization_audit = normalize_plotly_figure_for_static_export(
        fig
    )
    _prepare_period_export_title(export_fig, recipe, path.name)
    written_paths, export_audit = _write_legacy_figure(
        export_fig, path, f"Legacy {chosen_chart}"
    )
    export_audit["captured_figure_normalization"] = capture_normalization_audit
    return LegacyChartExport(
        paths=[str(written_path) for written_path in written_paths],
        audit={
            "status": "written",
            **export_audit,
            "dimension": small_multiples_dimension or selected_dimension,
            "source_functions": _legacy_source_functions(plotter_name),
        },
    )


def _capture_full_legacy_plot(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    artifact_name: str,
    chosen_chart_name: str,
    small_multiples_dimension: str | None = None,
    variance_chart: bool = False,
    prepare_year_over_year: bool = True,
    selected_dimension: str | None = None,
    repeat_values: list[str] | None = None,
) -> tuple[Any, str]:
    _ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from modules.chart_harness import apply_legacy_filter_title_metadata
        from modules.charting.chart_primitives import get_number_prefix
        from modules.charting.run_charting import run_charting
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        metric = str(recipe["mappings"]["amount_column"])
        previous, current = _period_totals(canonical, metric)
        chosen_chart = names[chosen_chart_name]
        requested_dimension = small_multiples_dimension or selected_dimension
        dimension = (
            _legacy_dimension(recipe, requested_dimension)
            if requested_dimension
            else None
        )
        chart = _legacy_chart_dict(
            names,
            chosen_chart,
            metric=metric,
            currency=str((recipe.get("options") or {}).get("currency") or "EUR"),
            reporting_entity=_reporting_entity(recipe),
            small_multiples=bool(small_multiples_dimension),
            selected_dimension=dimension,
            variance_chart=variance_chart,
        )
        chart = apply_legacy_filter_title_metadata(chart, names, recipe)
        prefix, chart, decimals = get_number_prefix(
            _monthly_metric_frame(canonical, metric), metric, chart, 1, metric
        )
        chart[names["IBCSdecimalName"]] = decimals
        value_prefix_dict = chart.setdefault(names["valuePrefixDict"], {})
        for period_metric in (
            names["acName"],
            names["pyName"],
            names["plName"],
            names["fcName"],
            names["differenceInValue"],
            names["varianceAmountName"],
        ):
            value_prefix_dict.setdefault(period_metric, prefix)
        param = _legacy_param_dict(
            names, recipe, previous_total=previous, current_total=current
        )
        del prepare_year_over_year
        prepared = _legacy_ready_frame(canonical)
        index_cols = _legacy_index_columns(recipe)
        value_cols = [metric]
        df_dict = _legacy_df_dict(names, prepared)
        with _capture_legacy_ui() as notifier:
            run_charting(
                df_dict,
                index_cols,
                value_cols,
                param,
                chart,
                _DummyTab(),
                notifier=notifier,
            )
        fig = _captured_figure(notifier, artifact_name)
        display_metric = _reporting_metric_label(recipe, metric)
        _apply_legacy_display_metric_label(fig, metric, display_metric)
        month_labels = _current_period_month_labels(canonical)
        if chosen_chart_name == "multitierColumnChart":
            _label_period_to_date_average(fig, recipe)
        elif chosen_chart_name == "slopeChart":
            _set_numeric_x_axis_labels(fig, [PREVIOUS_PERIOD, CURRENT_PERIOD])
        elif chosen_chart_name == "trendComparisonChart":
            _set_numeric_x_axis_labels(fig, month_labels)
        elif chosen_chart_name == "trendComparisonByPeriodChart":
            _set_numeric_x_axis_labels(fig, _by_period_labels())
            _label_by_period_chart_as_recency_window(fig)
        elif chosen_chart_name == "horizontalWaterfallChart":
            _normalize_waterfall_x_axis(fig, month_labels)
            _normalize_waterfall_absolute_labels(fig)
        if small_multiples_dimension and repeat_values:
            _order_small_multiple_panels(fig, repeat_values)
        if chosen_chart_name == "multitierColumnChart" and small_multiples_dimension:
            _apply_column_small_multiple_shared_axes(fig)
        if chosen_chart_name == "slopeChart" and small_multiples_dimension:
            _apply_slope_small_multiple_indexed_y_ranges(fig)
        if small_multiples_dimension:
            _polish_legacy_small_multiples(fig)
    return fig, str(chosen_chart)


def _find_headless_chrome() -> str | None:
    configured = (
        os.environ.get("PLOTLY_CHROME_PATH")
        or os.environ.get("BROWSER_PATH")
        or os.environ.get("CHROME_PATH")
    )
    candidates = [
        configured,
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
        *HEADLESS_CHROME_CANDIDATES,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _axis_domains(layout: Any, prefix: str) -> set[tuple[float, float]]:
    """Return unique Plotly subplot domains for one axis family."""

    if layout is None or not hasattr(layout, "to_plotly_json"):
        return set()
    layout_json = layout.to_plotly_json()
    domains: set[tuple[float, float]] = set()
    for key, axis in layout_json.items():
        if not key.startswith(f"{prefix}axis") or not isinstance(axis, dict):
            continue
        domain = axis.get("domain")
        if not isinstance(domain, list) or len(domain) != 2:
            continue
        domains.add((round(float(domain[0]), 6), round(float(domain[1]), 6)))
    return domains


def _axis_ref_from_layout_key(key: str, prefix: str) -> str:
    suffix = key.removeprefix(f"{prefix}axis")
    return prefix if not suffix else f"{prefix}{suffix}"


def _subplot_axis_refs_by_grid(layout: Any) -> list[tuple[str, str]]:
    """Return Plotly subplot axis refs in row-major visual order."""

    if layout is None or not hasattr(layout, "to_plotly_json"):
        return []
    layout_json = layout.to_plotly_json()
    refs: list[tuple[float, float, str, str]] = []
    for key, axis in layout_json.items():
        if not key.startswith("xaxis") or not isinstance(axis, dict):
            continue
        x_domain = axis.get("domain")
        if not isinstance(x_domain, list) or len(x_domain) != 2:
            continue
        x_ref = _axis_ref_from_layout_key(key, "x")
        y_ref = axis.get("anchor")
        if not isinstance(y_ref, str) or not y_ref.startswith("y"):
            suffix = x_ref.removeprefix("x")
            y_ref = "y" if not suffix else f"y{suffix}"
        y_axis = layout_json.get(_layout_axis_key(y_ref, "y"), {})
        y_domain = y_axis.get("domain") if isinstance(y_axis, dict) else None
        y_start = float(y_domain[0]) if isinstance(y_domain, list) else 0.0
        refs.append((round(-y_start, 6), round(float(x_domain[0]), 6), x_ref, y_ref))
    refs.sort()
    return [(x_ref, y_ref) for _y, _x, x_ref, y_ref in refs]


def _subplot_grid_size(fig: Any) -> tuple[int, int]:
    """Infer the Plotly subplot grid size without changing legacy chart code."""

    layout = getattr(fig, "layout", None)
    columns = max(len(_axis_domains(layout, "x")), 1)
    rows = max(len(_axis_domains(layout, "y")), 1)
    return columns, rows


def _legacy_export_size(fig: Any, artifact_name: str | None = None) -> tuple[int, int]:
    """Choose a readable export canvas for captured legacy Plotly figures."""

    layout = getattr(fig, "layout", None)
    layout_width = int(getattr(layout, "width", 0) or 0)
    layout_height = int(getattr(layout, "height", 0) or 0)
    columns, rows = _subplot_grid_size(fig)
    if artifact_name and artifact_name.startswith("year_over_year_slope"):
        if columns > 1:
            width = (
                SLOPE_SMALL_MULTIPLE_BASE_WIDTH
                + columns * SLOPE_SMALL_MULTIPLE_PANEL_WIDTH
            )
            height = max(
                SLOPE_SMALL_MULTIPLE_EXPORT_HEIGHT,
                220 + rows * 260,
            )
            return min(width, SLOPE_SMALL_MULTIPLE_MAX_WIDTH), min(height, 1200)
        return SLOPE_SINGLE_EXPORT_WIDTH, SLOPE_SINGLE_EXPORT_HEIGHT
    if columns > 1 or rows > 3:
        width = max(layout_width, 420 + columns * 900)
        height = max(layout_height, 260 + rows * 520)
        return min(width, 2600), min(height, 2400)
    return max(layout_width, 1400), max(layout_height, 900)


def _write_plotly_html(fig: Any, path: Path, width: int, height: int) -> Path:
    html_path = path.with_suffix(".html")
    fig.write_html(
        str(html_path),
        include_plotlyjs=True,
        full_html=True,
        default_width=f"{width}px",
        default_height=f"{height}px",
    )
    return html_path


def _screenshot_plotly_html(
    html_path: Path, png_path: Path, width: int, height: int
) -> str | None:
    chrome = _find_headless_chrome()
    if chrome is None:
        return "Headless Chrome executable was not found."
    resolved_html_path = html_path.resolve()
    resolved_png_path = png_path.resolve()
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={resolved_png_path}",
        resolved_html_path.as_uri(),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if result.returncode != 0:
        details = "\n".join(
            part for part in (result.stderr.strip(), result.stdout.strip()) if part
        )
        return details or f"Headless Chrome exited with status {result.returncode}."
    if not png_path.exists() or png_path.stat().st_size == 0:
        return "Headless Chrome did not write a PNG screenshot."
    return None


def _write_legacy_figure(
    fig: Any, path: Path, title: str
) -> tuple[list[Path], dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    del title
    export_fig, normalization_audit = normalize_plotly_figure_for_static_export(fig)
    export_width, export_height = _legacy_export_size(export_fig, path.name)
    title_lines = plotly_title_lines(getattr(export_fig.layout.title, "text", ""))
    try:
        export_fig.update_layout(
            width=export_width,
            height=export_height,
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            export_fig.write_image(
                str(path),
                format="png",
                width=export_width,
                height=export_height,
                scale=2,
            )
        return [path], {
            "artifact": path.name,
            "renderer": "legacy_plotly+kaleido",
            "plotly_export_error": None,
            "html_artifact": None,
            "screenshot_error": None,
            "export_width": export_width,
            "export_height": export_height,
            "chart_title_lines": title_lines,
            "chart_title": " / ".join(title_lines),
            "figure_export_normalization": normalization_audit,
        }
    except (OSError, RuntimeError, ValueError) as exc:
        html_path = _write_plotly_html(export_fig, path, export_width, export_height)
        screenshot_error = _screenshot_plotly_html(
            html_path, path, export_width, export_height
        )
        renderer = (
            "legacy_plotly+html_chrome_screenshot"
            if screenshot_error is None
            else "legacy_plotly+html_only"
        )
        paths = [html_path]
        if screenshot_error is None:
            paths.append(path)
        return paths, {
            "artifact": path.name if screenshot_error is None else html_path.name,
            "renderer": renderer,
            "plotly_export_error": str(exc),
            "html_artifact": html_path.name,
            "screenshot_error": screenshot_error,
            "export_width": export_width,
            "export_height": export_height,
            "chart_title_lines": title_lines,
            "chart_title": " / ".join(title_lines),
            "figure_export_normalization": normalization_audit,
        }


def _legacy_visible_title_lines(fig: Any, subject: str) -> list[str]:
    """Return title rows currently visible in a captured legacy Plotly figure."""

    candidates: list[str] = []
    title = getattr(fig.layout, "title", None)
    if title is not None and getattr(title, "text", None):
        candidates.extend(plotly_title_lines(title.text))
    for annotation in fig.layout.annotations or []:
        text = getattr(annotation, "text", None)
        if not isinstance(text, str):
            continue
        cleaned = plain_plotly_title_text(text)
        if subject and subject in cleaned:
            candidates.extend(plotly_title_lines(text))
            continue
        if " vs " in cleaned and ("Sales" in cleaned or "Weekly Average" in cleaned):
            candidates.extend(plotly_title_lines(text))
    return [line for line in candidates if plain_plotly_title_text(line)]


def _prepare_period_export_title(
    fig: Any, recipe: dict[str, Any], artifact_name: str
) -> list[str]:
    """Normalize a period figure title before writing it."""

    _normalize_legacy_period_title(fig)
    _hide_duplicate_paper_text_annotations(fig)
    title_lines = _apply_period_title_contract(fig, recipe)
    if artifact_name.startswith("year_over_year_slope_small_multiples"):
        _append_slope_index_note(fig)
    return title_lines


def _fallback_what_line(recipe: dict[str, Any]) -> str:
    metric = _reporting_metric_label(
        recipe, str(recipe.get("mappings", {}).get("amount_column") or "Value")
    )
    currency = str((recipe.get("options") or {}).get("currency") or "").strip()
    unit = "m" + currency if currency else ""
    return f"{metric} in {unit}".strip()


def _apply_period_title_contract(fig: Any, recipe: dict[str, Any]) -> list[str]:
    """Normalize period-comparison figures to the three-row title contract."""

    subject = _reporting_entity(recipe) or "Period comparison"
    legacy_lines = _legacy_visible_title_lines(fig, subject)
    what = legacy_lines[1] if len(legacy_lines) >= 2 else _fallback_what_line(recipe)
    when = reporting_period_line_from_recipe(
        recipe, current_label=CURRENT_PERIOD, previous_label=PREVIOUS_PERIOD
    )
    title_lines = apply_three_row_plotly_title(
        fig,
        ReportingTitleContract(who=subject, what=what, when=when),
    )
    _set_period_title_annotation_mirror(fig)
    return title_lines


def _is_period_title_annotation_mirror(annotation: Any) -> bool:
    """Return whether an annotation is the hidden structured title mirror."""

    try:
        x_value = float(getattr(annotation, "x", 1.0))
    except (TypeError, ValueError):
        x_value = 1.0
    return (
        getattr(annotation, "visible", None) is False
        and getattr(annotation, "xref", None) == "paper"
        and getattr(annotation, "yref", None) == "paper"
        and getattr(annotation, "xanchor", None) == "left"
        and getattr(annotation, "yanchor", None) == "top"
        and abs(x_value) <= TOLERANCE
    )


def _set_period_title_annotation_mirror(fig: Any) -> None:
    """Mirror the normalized title in annotations without rendering it twice."""

    title = getattr(fig.layout, "title", None)
    title_text = getattr(title, "text", None) if title is not None else None
    if not title_text:
        return
    annotations = [
        annotation
        for annotation in list(getattr(fig.layout, "annotations", ()) or [])
        if not _is_period_title_annotation_mirror(annotation)
    ]
    annotations.append(
        {
            "text": title_text,
            "xref": "paper",
            "yref": "paper",
            "x": 0.0,
            "y": 0.99,
            "xanchor": "left",
            "yanchor": "top",
            "showarrow": False,
            "visible": False,
        }
    )
    fig.layout.annotations = tuple(annotations)


def _hide_duplicate_paper_text_annotations(fig: Any) -> None:
    """Hide repeated paper annotations with the same text at the same position."""

    seen: set[tuple[str, float, float]] = set()
    for annotation in fig.layout.annotations or []:
        text = getattr(annotation, "text", None)
        if not text:
            continue
        if (
            getattr(annotation, "xref", None) != "paper"
            or getattr(annotation, "yref", None) != "paper"
        ):
            continue
        try:
            key = (
                str(text),
                round(float(getattr(annotation, "x", 0.0)), 6),
                round(float(getattr(annotation, "y", 0.0)), 6),
            )
        except (TypeError, ValueError):
            continue
        if key in seen:
            annotation.text = ""
            annotation.visible = False
            continue
        seen.add(key)


def _normalize_legacy_period_title(fig: Any) -> None:
    """Remove duplicated period labels produced by the legacy period title path."""

    replacements = {
        f"{CURRENT_PERIOD} {CURRENT_PERIOD} vs {PREVIOUS_PERIOD}": (
            f"{CURRENT_PERIOD} vs {PREVIOUS_PERIOD}"
        ),
        f"{PREVIOUS_PERIOD} {PREVIOUS_PERIOD} vs {CURRENT_PERIOD}": (
            f"{PREVIOUS_PERIOD} vs {CURRENT_PERIOD}"
        ),
        "period zero": PREVIOUS_PERIOD,
        "period one": CURRENT_PERIOD,
    }

    def clean(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    title = getattr(fig.layout, "title", None)
    if title is not None and getattr(title, "text", None):
        fig.update_layout(title={"text": clean(title.text)})
    for annotation in fig.layout.annotations or []:
        if getattr(annotation, "text", None):
            annotation.text = clean(annotation.text)


def _replace_text(value: Any, old: str, new: str) -> Any:
    if not isinstance(value, str) or old == new:
        return value
    return value.replace(old, new)


def _apply_legacy_display_metric_label(
    fig: Any, source_metric: str, display_metric: str
) -> None:
    """Use business-facing metric labels in legacy visual titles."""

    if not source_metric or not display_metric or source_metric == display_metric:
        return
    title = getattr(fig.layout, "title", None)
    if title is not None and getattr(title, "text", None):
        fig.update_layout(
            title={"text": _replace_text(title.text, source_metric, display_metric)}
        )
    for annotation in fig.layout.annotations or []:
        if getattr(annotation, "text", None):
            annotation.text = _replace_text(
                annotation.text, source_metric, display_metric
            )


def _axis_ref_at_position(prefix: str, index: int) -> str:
    return prefix if index == 0 else f"{prefix}{index + 1}"


def _axis_sort_key(axis_ref: str, prefix: str) -> int:
    suffix = axis_ref.removeprefix(prefix)
    if not suffix:
        return 1
    try:
        return int(suffix)
    except ValueError:
        return 0


def _figure_axis_refs(fig: Any, prefix: str) -> list[str]:
    axis_refs = {
        str(getattr(trace, f"{prefix}axis", None) or prefix) for trace in fig.data
    }
    layout_prefix = f"{prefix}axis"
    for key in fig.layout.to_plotly_json():
        if key == layout_prefix:
            axis_refs.add(prefix)
            continue
        if key.startswith(layout_prefix):
            suffix = key.removeprefix(layout_prefix)
            if suffix.isdigit():
                axis_refs.add(f"{prefix}{suffix}")
    return sorted(axis_refs, key=lambda axis_ref: _axis_sort_key(axis_ref, prefix))


def _layout_axis_key(axis_ref: str, prefix: str) -> str:
    suffix = axis_ref.removeprefix(prefix)
    return f"{prefix}axis{suffix}"


def _numeric_plot_values(values: Any) -> list[float]:
    if values is None:
        return []
    numeric_values: list[float] = []
    for value in values:
        try:
            numeric_values.append(float(value))
        except (TypeError, ValueError):
            continue
    return numeric_values


def _scaled_slope_value(value: Any, baseline: float) -> float | None:
    """Return the indexed slope value for a non-zero panel baseline."""

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if abs(baseline) <= TOLERANCE:
        return None
    return numeric_value / baseline * 100.0


def _slope_axis_range(values: list[float]) -> tuple[float, float]:
    """Return a padded range that keeps slope small multiples comparable."""

    if not values:
        return (95.0, 105.0)
    minimum = min([100.0, *values])
    maximum = max([100.0, *values])
    span = maximum - minimum
    if span <= TOLERANCE:
        span = max(abs(maximum), 1.0) * 0.08
    lower = minimum - span * 0.18
    upper = maximum + span * 0.22
    return lower, upper


def _apply_slope_small_multiple_shared_y_ranges(
    fig: Any, values_by_yaxis: dict[str, list[float]]
) -> None:
    """Keep slope small multiples on one absolute y-scale when indexing is unsafe."""

    all_values = [
        value for values in values_by_yaxis.values() for value in values if values
    ]
    if not all_values:
        return
    lower, upper = _slope_axis_range(all_values)
    for axis_ref in values_by_yaxis:
        fig.update_layout(
            {
                _layout_axis_key(axis_ref, "y"): {
                    "range": [lower, upper],
                    "autorange": False,
                    "matches": None if axis_ref == "y" else "y",
                }
            }
        )


def _append_slope_index_note(fig: Any) -> None:
    """State that slope positions are indexed while labels remain actual values."""

    note = "Index: PY=100"
    title = getattr(fig.layout, "title", None)
    title_text = getattr(title, "text", None) if title is not None else None
    if isinstance(title_text, str) and note not in title_text:
        fig.update_layout(title={"text": f"{title_text}<BR>{note}"})
    for annotation in fig.layout.annotations or []:
        text = getattr(annotation, "text", None)
        try:
            x_value = float(getattr(annotation, "x", None))
        except (TypeError, ValueError):
            x_value = None
        is_left_title = (
            getattr(annotation, "xanchor", None) == "left"
            and x_value is not None
            and abs(x_value) <= TOLERANCE
        )
        is_period_title = isinstance(text, str) and "PY vs AC" in text
        if (
            isinstance(text, str)
            and note not in text
            and getattr(annotation, "xref", None) == "paper"
            and getattr(annotation, "yref", None) == "paper"
            and (is_left_title or is_period_title)
        ):
            annotation.text = f"{text}<BR>{note}"


def _apply_slope_small_multiple_indexed_y_ranges(fig: Any) -> None:
    """Index slope small multiples to PY=100 so panel slopes share one scale."""

    values_by_yaxis: dict[str, list[float]] = {}
    for trace in fig.data:
        mode = str(getattr(trace, "mode", "") or "")
        if "lines" not in mode:
            continue
        values = _numeric_plot_values(getattr(trace, "y", None))
        if not values:
            continue
        axis_ref = str(getattr(trace, "yaxis", None) or "y")
        values_by_yaxis.setdefault(axis_ref, []).extend(values)
    if len(values_by_yaxis) < 2:
        return

    baselines = {
        axis_ref: values[0]
        for axis_ref, values in values_by_yaxis.items()
        if values and abs(values[0]) > TOLERANCE
    }
    if set(baselines) != set(values_by_yaxis):
        _apply_slope_small_multiple_shared_y_ranges(fig, values_by_yaxis)
        return

    indexed_values_by_yaxis: dict[str, list[float]] = {}
    for trace in fig.data:
        mode = str(getattr(trace, "mode", "") or "")
        if "lines" not in mode:
            continue
        axis_ref = str(getattr(trace, "yaxis", None) or "y")
        baseline = baselines.get(axis_ref)
        if baseline is None:
            continue
        indexed_values: list[float] = []
        transformed_y: list[Any] = []
        for value in getattr(trace, "y", None) or []:
            scaled = _scaled_slope_value(value, baseline)
            transformed_y.append(value if scaled is None else scaled)
            if scaled is not None:
                indexed_values.append(scaled)
        if indexed_values:
            trace.y = transformed_y
            indexed_values_by_yaxis.setdefault(axis_ref, []).extend(indexed_values)

    for annotation in fig.layout.annotations or []:
        axis_ref = str(getattr(annotation, "yref", "") or "")
        baseline = baselines.get(axis_ref)
        if baseline is None:
            continue
        scaled = _scaled_slope_value(getattr(annotation, "y", None), baseline)
        if scaled is not None:
            annotation.y = scaled

    all_indexed_values = [
        value
        for values in indexed_values_by_yaxis.values()
        for value in values
        if values
    ]
    lower, upper = _slope_axis_range(all_indexed_values)
    for axis_ref in values_by_yaxis:
        fig.update_layout(
            {
                _layout_axis_key(axis_ref, "y"): {
                    "range": [lower, upper],
                    "autorange": False,
                    "matches": None if axis_ref == "y" else "y",
                    "tickformat": ".0f",
                }
            }
        )
    _append_slope_index_note(fig)


def _panel_title_annotations(fig: Any, ordered_panels: list[str]) -> list[Any]:
    panel_set = set(ordered_panels)
    annotations = [
        annotation
        for annotation in fig.layout.annotations or []
        if str(getattr(annotation, "text", "")) in panel_set
        and getattr(annotation, "xref", None) == "paper"
        and getattr(annotation, "yref", None) == "paper"
    ]
    return sorted(
        annotations,
        key=lambda annotation: (
            -float(getattr(annotation, "y", None) or 0.0),
            float(getattr(annotation, "x", None) or 0.0),
        ),
    )


def _dedupe_panel_title_annotations(annotations: list[Any]) -> list[Any]:
    """Hide duplicated legacy subplot titles that occupy the same paper position."""

    deduped: list[Any] = []
    seen_positions: set[tuple[float, float]] = set()
    for annotation in annotations:
        try:
            position = (
                round(float(getattr(annotation, "x", 0.0)), 6),
                round(float(getattr(annotation, "y", 0.0)), 6),
            )
        except (TypeError, ValueError):
            deduped.append(annotation)
            continue
        if position in seen_positions:
            annotation.text = ""
            annotation.visible = False
            continue
        seen_positions.add(position)
        deduped.append(annotation)
    return deduped


def _order_small_multiple_panels(fig: Any, ordered_panels: list[str]) -> None:
    """Align captured subplot order with period_core's ranked panel order."""

    desired_order = [str(panel) for panel in ordered_panels]
    title_annotations = _dedupe_panel_title_annotations(
        _panel_title_annotations(fig, desired_order)
    )
    if len(title_annotations) < 2:
        return
    current_order = [str(annotation.text) for annotation in title_annotations]
    desired_order = [panel for panel in desired_order if panel in current_order]
    desired_order.extend(panel for panel in current_order if panel not in desired_order)
    if current_order == desired_order:
        return

    axis_refs = _subplot_axis_refs_by_grid(fig.layout)
    if len(axis_refs) < len(current_order):
        axis_refs = [
            (
                _axis_ref_at_position("x", index),
                _axis_ref_at_position("y", index),
            )
            for index in range(len(current_order))
        ]
    source_axes_by_panel = {
        panel: axis_refs[index]
        for index, panel in enumerate(current_order)
        if index < len(axis_refs)
    }
    target_axes_by_panel = {
        panel: axis_refs[index]
        for index, panel in enumerate(desired_order)
        if index < len(axis_refs)
    }
    source_panel_by_axes = {axes: panel for panel, axes in source_axes_by_panel.items()}

    for trace in fig.data:
        old_axes = (
            str(getattr(trace, "xaxis", None) or "x"),
            str(getattr(trace, "yaxis", None) or "y"),
        )
        panel = source_panel_by_axes.get(old_axes)
        if panel is None or panel not in target_axes_by_panel:
            continue
        trace.xaxis, trace.yaxis = target_axes_by_panel[panel]

    for annotation in fig.layout.annotations or []:
        old_axes = (
            getattr(annotation, "xref", None),
            getattr(annotation, "yref", None),
        )
        panel = source_panel_by_axes.get(old_axes)
        if panel is None or panel not in target_axes_by_panel:
            continue
        annotation.xref, annotation.yref = target_axes_by_panel[panel]

    for shape in getattr(fig.layout, "shapes", None) or []:
        old_axes = (
            getattr(shape, "xref", None),
            getattr(shape, "yref", None),
        )
        panel = source_panel_by_axes.get(old_axes)
        if panel is None or panel not in target_axes_by_panel:
            continue
        shape.xref, shape.yref = target_axes_by_panel[panel]

    for index, annotation in enumerate(title_annotations):
        if index < len(desired_order):
            annotation.text = desired_order[index]


def _order_slope_small_multiple_panels(fig: Any, ordered_panels: list[str]) -> None:
    """Align captured slope subplot order with period_core's ranked panel order."""

    _order_small_multiple_panels(fig, ordered_panels)


def _label_period_to_date_average(fig: Any, recipe: dict[str, Any]) -> None:
    """Use IBCS notation for the legacy average column appended after periods."""

    average_label = _period_to_date_average_label(recipe)

    def relabel(value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "Ø":
            return value.replace("Ø", average_label)
        return value

    for trace in fig.data:
        x_values = getattr(trace, "x", None)
        if x_values is None:
            continue
        trace.x = [relabel(value) for value in x_values]


def _set_numeric_x_axis_labels(fig: Any, labels: list[str]) -> None:
    """Expose period labels for legacy trend charts that use numeric x positions."""

    if not labels:
        return
    fig.update_xaxes(
        tickmode="array",
        tickvals=list(range(len(labels))),
        ticktext=labels,
        zeroline=False,
    )


def _label_by_period_chart_as_recency_window(fig: Any) -> None:
    """Clarify that by-period points are overlapping recency windows."""

    title_pattern = re.compile(r"(Weekly Average\b.*?)(\s*</b>)")

    def relabel(text: Any) -> Any:
        if not isinstance(text, str) or "Weekly Average" not in text:
            return text
        if "Recency Window" in text:
            return text
        return title_pattern.sub(r"\1 by Recency Window\2", text, count=1)

    title = getattr(fig.layout, "title", None)
    if title is not None and getattr(title, "text", None):
        fig.update_layout(title={"text": relabel(title.text)})
    for annotation in fig.layout.annotations or []:
        if getattr(annotation, "text", None):
            annotation.text = relabel(annotation.text)


def _normalize_waterfall_x_axis(fig: Any, month_labels: list[str]) -> None:
    """Use PY/AC endpoints and chronological month order on legacy waterfalls."""

    categories = [PREVIOUS_PERIOD, *month_labels, CURRENT_PERIOD]
    category_ranks = {label: index for index, label in enumerate(categories)}

    def clean_x(value: Any, index: int, last_index: int) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped.lower() == "period zero":
            return PREVIOUS_PERIOD
        if stripped.lower() == "period one":
            return CURRENT_PERIOD
        if stripped == "" and index == 0:
            return PREVIOUS_PERIOD
        if stripped == "" and index == last_index:
            return CURRENT_PERIOD
        if stripped in category_ranks:
            return stripped
        return stripped

    def order_for(cleaned_x: list[Any]) -> list[int]:
        return sorted(
            (idx for idx, value in enumerate(cleaned_x) if value in category_ranks),
            key=lambda idx: (category_ranks[cleaned_x[idx]], idx),
        )

    def reorder(value: Any, order: list[int], expected_len: int) -> Any:
        if value is None or isinstance(value, str):
            return value
        try:
            items = list(value)
        except TypeError:
            return value
        if len(items) != expected_len:
            return value
        return [items[idx] for idx in order]

    for trace in fig.data:
        x_values = getattr(trace, "x", None)
        if x_values is None:
            continue
        original_x = list(x_values)
        if not original_x:
            continue
        cleaned_x = [
            clean_x(value, index, len(original_x) - 1)
            for index, value in enumerate(original_x)
        ]
        order = order_for(cleaned_x)
        if not order:
            continue
        trace.x = [cleaned_x[idx] for idx in order]
        for attr in ("y", "text", "hovertext", "customdata", "base", "measure"):
            if hasattr(trace, attr):
                setattr(
                    trace, attr, reorder(getattr(trace, attr), order, len(original_x))
                )
        marker = getattr(trace, "marker", None)
        if marker is not None and getattr(marker, "color", None) is not None:
            marker.color = reorder(marker.color, order, len(original_x))

    fig.update_xaxes(
        categoryorder="array",
        categoryarray=categories,
        tickmode="array",
        tickvals=categories,
        ticktext=categories,
    )


def _normalize_waterfall_absolute_labels(fig: Any) -> None:
    """Keep absolute bar labels aligned with the legacy k-unit title."""

    def clean_label(value: Any) -> Any:
        if value is None:
            return value
        try:
            numeric = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return value
        if abs(numeric) < 10_000:
            return value
        return f"{numeric / 1_000:.0f}"

    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        if getattr(trace, "name", None) != CURRENT_PERIOD:
            continue
        text = getattr(trace, "text", None)
        if text is None or isinstance(text, str):
            continue
        trace.text = [clean_label(value) for value in text]


def _captured_figure(notifier: _LegacyCaptureNotifier, chart_name: str) -> Any:
    if not notifier.figures:
        raise RuntimeError(f"Legacy chart did not emit a Plotly figure: {chart_name}")
    return notifier.figures[-1]


def write_legacy_multitier_column_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str = "year_over_year_column.png",
    small_multiples_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    """Export the original legacy multitier-column chart."""
    return _write_full_legacy_plot(
        canonical,
        recipe,
        output_dir,
        artifact_name=artifact_name,
        chosen_chart_name="multitierColumnChart",
        plotter_name="plot_multitier_column_chart",
        small_multiples_dimension=small_multiples_dimension,
        repeat_values=repeat_values,
        render=render,
    )


def _polish_legacy_small_multiples(fig: Any) -> None:
    """Keep legacy small-multiple labels visible in headless PNG export."""

    current_margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    current_margin["b"] = max(int(current_margin.get("b") or 0), 110)
    fig.update_layout(margin=current_margin)
    fig.update_xaxes(automargin=True)


def _apply_column_small_multiple_shared_axes(fig: Any) -> None:
    """Use shared scales for period column small multiples."""

    for prefix in ("x", "y"):
        axis_refs = _figure_axis_refs(fig, prefix)
        if len(axis_refs) < 2:
            continue
        base_axis_ref = prefix if prefix in axis_refs else axis_refs[0]
        for axis_ref in axis_refs:
            fig.update_layout(
                {
                    _layout_axis_key(axis_ref, prefix): {
                        "matches": None if axis_ref == base_axis_ref else base_axis_ref,
                        "range": None,
                        "autorange": True,
                    }
                }
            )


def write_legacy_actual_vs_previous_year_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str,
    by_period: bool,
    small_multiples_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    """Export the original legacy actual-vs-previous-year chart."""
    return _write_full_legacy_plot(
        canonical,
        recipe,
        output_dir,
        artifact_name=artifact_name,
        chosen_chart_name=(
            "trendComparisonByPeriodChart" if by_period else "trendComparisonChart"
        ),
        plotter_name=(
            "plot_actual_vs_previous_year_charts"
            if by_period
            else "plot_trend_comparison_charts"
        ),
        small_multiples_dimension=small_multiples_dimension,
        repeat_values=repeat_values,
        render=render,
    )


def write_legacy_slope_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str = "year_over_year_slope.png",
    dimension: str | None = None,
    small_multiples_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    """Export the original legacy slope chart."""
    selected_dimension = _legacy_dimension(
        recipe, small_multiples_dimension or dimension
    )
    if not selected_dimension:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "not_written_no_dimension",
                "artifact": artifact_name,
                "dimension": None,
                "source_functions": _legacy_source_functions("plot_slope_charts"),
            },
        )
    return _write_full_legacy_plot(
        canonical,
        recipe,
        output_dir,
        artifact_name=artifact_name,
        chosen_chart_name="slopeChart",
        plotter_name="plot_slope_charts",
        small_multiples_dimension=small_multiples_dimension,
        prepare_year_over_year=False,
        selected_dimension=selected_dimension,
        repeat_values=repeat_values,
        render=render,
    )


def write_legacy_dot_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str = "year_over_year_dot.png",
    dimension: str | None = None,
    small_multiples_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    """Export the original legacy dot chart."""
    selected_dimension = _legacy_dimension(recipe, dimension)
    if not selected_dimension:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "not_written_no_dimension",
                "artifact": artifact_name,
                "dimension": None,
                "source_functions": _legacy_source_functions("plot_dot_chart"),
            },
        )
    if small_multiples_dimension:
        return _write_legacy_dot_small_multiples_chart(
            canonical,
            recipe,
            output_dir,
            artifact_name=artifact_name,
            selected_dimension=selected_dimension,
            small_multiples_dimension=small_multiples_dimension,
            repeat_values=repeat_values,
            render=render,
        )
    del repeat_values
    return _write_full_legacy_plot(
        canonical,
        recipe,
        output_dir,
        artifact_name=artifact_name,
        chosen_chart_name="dotChart",
        plotter_name="plot_dot_chart",
        prepare_year_over_year=False,
        selected_dimension=selected_dimension,
        render=render,
    )


def _dot_small_multiples_grid_size(panel_count: int) -> tuple[int, int]:
    """Return a compact row-major grid for dot small multiples."""

    columns = min(max(panel_count, 1), 4)
    rows = max(math.ceil(panel_count / columns), 1)
    return rows, columns


def _dot_small_multiples_title(
    panel_fig: Any,
    *,
    selected_dimension: str,
    small_multiples_dimension: str,
) -> str:
    """Build a parent title from the captured legacy single-panel dot title."""

    annotations = list(getattr(panel_fig.layout, "annotations", ()) or ())
    for annotation in annotations:
        text = str(getattr(annotation, "text", "") or "")
        marker = f" by {selected_dimension} "
        if marker in text:
            return text.replace(
                marker,
                f" by {selected_dimension} and {small_multiples_dimension} ",
                1,
            )
    return f"PY vs AC by {selected_dimension} and {small_multiples_dimension}"


def _compose_dot_small_multiples_figure(
    panel_figures: list[tuple[str, Any]],
    *,
    selected_dimension: str,
    small_multiples_dimension: str,
) -> Any:
    """Compose captured legacy dot figures into a small-multiples figure."""

    from plotly.subplots import make_subplots

    rows, columns = _dot_small_multiples_grid_size(len(panel_figures))
    subplot_titles = [panel for panel, _fig in panel_figures]
    fig = make_subplots(
        rows=rows,
        cols=columns,
        subplot_titles=subplot_titles,
        horizontal_spacing=0.07,
        vertical_spacing=0.18 if rows > 1 else 0.08,
    )

    for index, (_panel, panel_fig) in enumerate(panel_figures):
        row = index // columns + 1
        col = index % columns + 1
        for trace in panel_fig.data:
            trace_copy = copy.deepcopy(trace)
            trace_copy.showlegend = index == 0
            if getattr(trace_copy, "name", None):
                trace_copy.legendgroup = str(trace_copy.name)
            fig.add_trace(trace_copy, row=row, col=col)
        for shape in getattr(panel_fig.layout, "shapes", ()) or ():
            shape_dict = shape.to_plotly_json()
            shape_dict.pop("xref", None)
            shape_dict.pop("yref", None)
            fig.add_shape(shape_dict, row=row, col=col)
        yaxis = getattr(panel_fig.layout, "yaxis", None)
        categoryarray = getattr(yaxis, "categoryarray", None)
        if categoryarray:
            fig.update_yaxes(
                categoryorder="array",
                categoryarray=list(categoryarray),
                row=row,
                col=col,
            )

    title = _dot_small_multiples_title(
        panel_figures[0][1],
        selected_dimension=selected_dimension,
        small_multiples_dimension=small_multiples_dimension,
    )
    fig.add_annotation(
        text=title,
        x=0,
        y=1.16 if rows > 1 else 1.2,
        xref="paper",
        yref="paper",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        align="left",
    )
    fig.update_layout(
        margin={"l": 90, "r": 50, "t": 125, "b": 110},
        legend={"orientation": "h", "y": -0.08, "x": 0},
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    fig.update_xaxes(
        showgrid=False,
        showticklabels=False,
        ticks="",
        zeroline=True,
        zerolinecolor="lightgrey",
    )
    fig.update_yaxes(showgrid=False, ticks="", automargin=True)
    _polish_legacy_small_multiples(fig)
    return fig


def _write_legacy_dot_small_multiples_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str,
    selected_dimension: str,
    small_multiples_dimension: str,
    repeat_values: list[str] | None,
    render: bool = True,
) -> LegacyChartExport:
    """Export dot small multiples by composing captured legacy dot charts."""

    panel_dimension = _legacy_dimension(recipe, small_multiples_dimension)
    if not panel_dimension:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "not_written_no_dimension",
                "artifact": artifact_name,
                "dimension": None,
                "source_functions": _legacy_source_functions("plot_dot_chart"),
            },
        )
    panel_values = repeat_values
    if not panel_values:
        panel_values = [
            str(row[panel_dimension])
            for row in canonical.select(pl.col(panel_dimension).cast(pl.Utf8))
            .unique(maintain_order=True)
            .to_dicts()
        ]
    panel_figures: list[tuple[str, Any]] = []
    for panel_value in panel_values:
        panel_label = str(panel_value)
        panel_frame = canonical.filter(
            pl.col(panel_dimension).cast(pl.Utf8) == panel_label
        )
        if panel_frame.is_empty():
            continue
        panel_fig, _chosen_chart = _capture_full_legacy_plot(
            panel_frame,
            recipe,
            artifact_name=artifact_name,
            chosen_chart_name="dotChart",
            prepare_year_over_year=False,
            selected_dimension=selected_dimension,
        )
        panel_figures.append((panel_label, panel_fig))
    if not panel_figures:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "not_written_no_data",
                "artifact": artifact_name,
                "dimension": panel_dimension,
                "source_functions": _legacy_source_functions("plot_dot_chart"),
            },
        )
    if not render:
        return LegacyChartExport(
            paths=[],
            audit={
                "status": "data_written",
                "artifact": artifact_name,
                "rendered": False,
                "dimension": panel_dimension,
                "dot_dimension": selected_dimension,
                "panel_count": len(panel_figures),
                "source_functions": _legacy_source_functions("plot_dot_chart"),
            },
        )
    fig = _compose_dot_small_multiples_figure(
        panel_figures,
        selected_dimension=selected_dimension,
        small_multiples_dimension=panel_dimension,
    )
    path = output_dir / artifact_name
    export_fig, capture_normalization_audit = normalize_plotly_figure_for_static_export(
        fig
    )
    _prepare_period_export_title(export_fig, recipe, path.name)
    written_paths, export_audit = _write_legacy_figure(
        export_fig,
        path,
        "Legacy dotChart small multiples",
    )
    export_audit["captured_figure_normalization"] = capture_normalization_audit
    return LegacyChartExport(
        paths=[str(written_path) for written_path in written_paths],
        audit={
            "status": "written",
            **export_audit,
            "dimension": panel_dimension,
            "dot_dimension": selected_dimension,
            "panel_count": len(panel_figures),
            "source_functions": _legacy_source_functions("plot_dot_chart"),
        },
    )


def write_legacy_horizontal_waterfall_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str = "year_over_year_waterfall.png",
    small_multiples_dimension: str | None = None,
    repeat_values: list[str] | None = None,
    render: bool = True,
) -> LegacyChartExport:
    """Export the original legacy horizontal waterfall chart."""
    return _write_full_legacy_plot(
        canonical,
        recipe,
        output_dir,
        artifact_name=artifact_name,
        chosen_chart_name="horizontalWaterfallChart",
        plotter_name="plot_horizontal_waterfall_chart",
        small_multiples_dimension=small_multiples_dimension,
        variance_chart=True,
        repeat_values=repeat_values,
        render=render,
    )
