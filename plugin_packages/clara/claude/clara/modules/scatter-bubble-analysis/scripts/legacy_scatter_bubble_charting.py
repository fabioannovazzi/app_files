"""Headless adapters for vendored legacy scatter and bubble charts."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import sys
import traceback
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import polars as pl

__all__ = [
    "LegacyPreparedDataCache",
    "LegacyScatterBubbleChartExport",
    "cleanup_legacy_imports",
    "ensure_legacy_import_path",
    "write_legacy_scatter_bubble_chart",
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
VALUE_PREFIX_DIVISORS = {
    "t": 1_000_000_000_000,
    "b": 1_000_000_000,
    "m": 1_000_000,
    "k": 1_000,
    "": 1,
}
METRIC_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
HEADLESS_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


@dataclass(frozen=True)
class LegacyScatterBubbleChartExport:
    """Exported paths and audit information for one legacy chart attempt."""

    paths: list[str]
    audit: dict[str, Any]
    chart_context: dict[str, Any] | None = None


@dataclass
class LegacyPreparedDataCache:
    """Prepared grouped data reused by legacy scatter/bubble render calls."""

    stage_frames: dict[tuple[Any, ...], pl.DataFrame]
    stage_payloads: dict[tuple[Any, ...], Any]
    hits: int = 0
    misses: int = 0
    stage_hits: int = 0
    stage_misses: int = 0

    @classmethod
    def empty(cls) -> "LegacyPreparedDataCache":
        """Return an empty cache for one plugin run."""

        return cls(stage_frames={}, stage_payloads={})

    def snapshot(self) -> tuple[int, int, int, int]:
        """Return current cache hit/miss counters."""

        return self.hits, self.misses, self.stage_hits, self.stage_misses

    def audit_delta(self, start: tuple[int, int, int, int]) -> dict[str, Any]:
        """Return cache activity since ``start``."""

        start_hits, start_misses, start_stage_hits, start_stage_misses = start
        return {
            "prepared_data_cache": {
                "enabled": True,
                "scope": "legacy_scatter_bubble_prepared_data",
                "hits": self.hits - start_hits,
                "misses": self.misses - start_misses,
                "stage_hits": self.stage_hits - start_stage_hits,
                "stage_misses": self.stage_misses - start_stage_misses,
                "stored_stage_frames": len(self.stage_frames),
                "stored_stage_payloads": len(self.stage_payloads),
            }
        }

    @staticmethod
    def _columns(frame: pl.DataFrame | pl.LazyFrame) -> list[str]:
        if isinstance(frame, pl.DataFrame):
            return frame.collect_schema().names()
        return frame.collect_schema().names()

    @staticmethod
    def _frame_signature(frame: pl.DataFrame | pl.LazyFrame) -> tuple[Any, ...]:
        columns = tuple(LegacyPreparedDataCache._columns(frame))
        if isinstance(frame, pl.DataFrame):
            return ("df", columns, frame.height)
        try:
            return ("lf", columns, frame.explain(optimized=True))
        except (pl.exceptions.PolarsError, TypeError, ValueError):
            return ("lf", columns, id(frame))

    @staticmethod
    def _collect_frame(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
        if isinstance(frame, pl.DataFrame):
            return frame
        try:
            return frame.collect(engine="streaming")
        except (pl.exceptions.PolarsError, TypeError, ValueError, RuntimeError):
            return frame.collect()

    def get_frame_payload(
        self,
        stage: str,
        key_parts: tuple[Any, ...],
        builder: Callable[[], tuple[pl.DataFrame | pl.LazyFrame, list[str]]],
    ) -> tuple[pl.LazyFrame, list[str]]:
        """Return a cached grouped frame payload."""

        key = (stage, *key_parts)
        cached = self.stage_payloads.get(key)
        if cached is not None:
            self.hits += 1
            self.stage_hits += 1
            frame, group_cols = cached
            return frame.lazy(), list(group_cols)
        frame, group_cols = builder()
        collected = self._collect_frame(frame)
        self.stage_payloads[key] = (collected, list(group_cols))
        self.misses += 1
        self.stage_misses += 1
        return collected.lazy(), list(group_cols)

    def get_show_only_largest(
        self,
        names: dict[str, str],
        original: Callable[..., Any],
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        second_column: str | None,
        time_column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
        param_dict: dict[str, Any],
        key: str,
    ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
        """Cache legacy top-N/other-bucket preparation."""

        axis_config = chart_dict[key]
        cache_key = (
            self._frame_signature(df_copy),
            chart_dict[names["chosenChart"]],
            column,
            second_column,
            time_column,
            tuple(value_cols),
            key,
            axis_config[names["numberOfTop"]],
            axis_config[names["aggregateOtherItems"]],
            tuple(sorted(dict(chart_dict.get(names["valuePrefixDict"], {})).items())),
        )
        cached = self.stage_payloads.get(("show_only_largest", *cache_key))
        if cached is not None:
            self.hits += 1
            self.stage_hits += 1
            frame, unique_items, aggregate_other, prepared_value_cols = cached
            return (
                frame.lazy(),
                list(unique_items),
                aggregate_other,
                list(prepared_value_cols),
            )

        frame, unique_items, aggregate_other, prepared_value_cols = original(
            df_copy,
            column,
            second_column,
            time_column,
            value_cols,
            chart_dict,
            param_dict,
            key,
        )
        collected = self._collect_frame(frame)
        self.stage_payloads[("show_only_largest", *cache_key)] = (
            collected,
            list(unique_items),
            aggregate_other,
            list(prepared_value_cols),
        )
        self.misses += 1
        self.stage_misses += 1
        return (
            collected.lazy(),
            list(unique_items),
            aggregate_other,
            list(prepared_value_cols),
        )


def ensure_legacy_import_path() -> None:
    """Make the vendored legacy modules importable for repo and ZIP runs."""

    _activate_legacy_import_parent()


def cleanup_legacy_imports() -> None:
    """Clear legacy ``modules`` imports so another plugin can load its vendor tree."""

    module_roots = [
        (SHARED_VENDOR_ROOT / "modules").resolve(),
        (VENDOR_ROOT / "modules").resolve(),
    ]
    for name, module in list(sys.modules.items()):
        if name == "modules" or name.startswith("modules."):
            module_file = getattr(module, "__file__", None)
            module_path = Path(module_file).resolve() if module_file else None
            if module_path and any(
                module_path.is_relative_to(root) for root in module_roots
            ):
                del sys.modules[name]
    for vendor in (str(SHARED_VENDOR_ROOT), str(VENDOR_ROOT)):
        while vendor in sys.path:
            sys.path.remove(vendor)


def _put_if_key(
    target: dict[str, Any], names: dict[str, str], key: str, value: Any
) -> None:
    if key in names:
        target[names[key]] = value


def _legacy_source_functions(spec: dict[str, Any]) -> list[str]:
    plotter = str(spec["plotter"])
    if plotter == "plot_scatter_charts":
        functions = [
            "modules.charting.plot_charts.plot_scatter_charts",
            "modules.charting.prepare_charts.group_by_dataset_for_scatter_plot",
            "modules.charting.plot_charts.plot_scatter_chart_datashader",
            "modules.charting.draw_scatter.draw_scatter_chart",
        ]
        if spec.get("show_iso_line"):
            functions.extend(
                [
                    "modules.charting.draw_scatter.add_isolines",
                    "modules.charting.draw_scatter.get_isoline_data",
                ]
            )
        return functions
    return [
        "modules.charting.plot_charts.plot_bubble_charts",
        "modules.charting.prepare_charts.group_by_dataset_for_bubble_plot",
        "modules.charting.prepare_charts.prepare_dataframe_for_total_bubble_colored",
        "modules.charting.draw_bubble.draw_bubble_chart",
    ]


def _legacy_optional_dimension(
    names: dict[str, str], value: Any, *, use_false_sentinel: bool = False
) -> Any:
    """Return legacy's no-dimension sentinel without stringifying it."""

    if value in (None, "", False):
        if use_false_sentinel:
            return False
        return names["nothingFilteredName"]
    return str(value)


def _legacy_chart_dict(
    names: dict[str, str],
    spec: dict[str, Any],
    *,
    currency: str,
) -> dict[str, Any]:
    color_palette = str(spec["color_palette"]).strip().lower()
    color_palette_name = {
        "bain": names["bainColorpalette"],
        "ibcs": names["IBCSColorpalette"],
        "occ": names["occColorpalette"],
        "mckinsey": names["mckinseyColorpalette"],
        "bcg": names["bcgColorpalette"],
        "deloitte": names["deloitteColorpalette"],
        "tableau": names["tableauColorpalette"],
        "powerbi": names["powerbiColorpalette"],
        "symphony": names["symphonyColorpalette"],
        "greys": names["greysColorpalette"],
        "blues": names["bluesColorpalette"],
        "oranges": names["orangesColorpalette"],
        "purples": names["purplesColorpalette"],
        "browns": names["brownsColorpalette"],
    }.get(color_palette, str(spec["color_palette"]))
    max_items = int(spec["max_items"])
    small_multiples_dimension = spec.get("small_multiples_dimension")
    small_multiples_panel_count = 0
    if small_multiples_dimension:
        small_multiples_panel_count = max(2, int(spec["small_multiples_max_panels"]))
    aggregate_other_items = bool(spec["aggregate_other_items"])
    use_scatter_no_dimension = spec["legacy_chart_key"] == "scatterChart"
    dot_dimension = _legacy_optional_dimension(names, spec.get("dot_dimension"))
    color_dimension = _legacy_optional_dimension(
        names,
        spec.get("color_dimension"),
        use_false_sentinel=use_scatter_no_dimension,
    )
    top_axis = {
        names["numberOfTop"]: max_items,
        names["aggregateOtherItems"]: aggregate_other_items,
    }
    panel_axis = dict(top_axis)
    if small_multiples_dimension:
        panel_axis[names["numberOfTop"]] = max(small_multiples_panel_count - 1, 1)
        panel_axis[names["aggregateOtherItems"]] = True
    value_prefixes = {
        str(metric): str(prefix)
        for metric, prefix in dict(spec.get("display_value_prefixes") or {}).items()
        if str(prefix) in VALUE_PREFIX_DIVISORS and str(prefix)
    }
    value_prefix_metric = str(
        spec.get("display_value_prefix_metric") or spec.get("bubble_size_metric") or ""
    )
    value_prefix = value_prefixes.get(value_prefix_metric, "")
    chart = {
        names["chosenChart"]: names[str(spec["legacy_chart_key"])],
        names["selectedPeriods"]: [str(item) for item in spec["selected_periods"]],
        names["toPlotPeriod"]: str(spec["to_plot_period"]),
        names["plotSmallMultiplesOtherCharts"]: bool(small_multiples_dimension),
        names["smallMultiplesColumn"]: small_multiples_dimension or names["totalName"],
        names["numberOfPlottedSmallMultiples"]: small_multiples_panel_count,
        names["colorChoice"]: names["redToGreen"],
        names["colorpalette"]: color_palette_name,
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["filterDates"]: False,
        names["shareOfTotalMarket"]: False,
        names["varianceInPercent"]: False,
        names["plotAsBaseline"]: False,
        names["plotValuesAsChoice"]: names["absolute"],
        names["showValuesAs"]: names["absolute"],
        names["rowToPlotName"]: names["entireDatasetName"],
        names["metricsToPlot"]: list(spec["metrics"]),
        names["singleMetric"]: str(spec["y_metric"]),
        names["xAxisMetric"]: str(spec["x_metric"]),
        names["yAxisMetric"]: str(spec["y_metric"]),
        names["bubbleSize"]: str(spec.get("bubble_size_metric") or spec["y_metric"]),
        names["sortAxis"]: names["yAxisSort"],
        names["xAxisDimension"]: dot_dimension,
        names["yAxisDimension"]: color_dimension,
        names["selectDimensionsToPlot"]: [str(item) for item in spec["dimensions"]],
        names["mainDimension"]: [str(dot_dimension)],
        names["countColumn"]: str(dot_dimension),
        names["countByColumn"]: str(dot_dimension),
        names["aggregateUniquesByDimension"]: bool(spec.get("color_dimension")),
        names["aggregateUniquesDimension"]: str(color_dimension or dot_dimension),
        names["showOnly"]: names["showTop"],
        names["periodChoice"]: names["monthName"],
        names["canPlotYearToYear"]: True,
        names["setTimePeriodTabLabel"]: names["comparePeriods"],
        names["processingChoice"]: names["runOneDimensionalAnalysis"],
        names["varianceAnalysisChart"]: names["notMetConditionValue"],
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
        names["plotAsHeatmap"]: bool(spec.get("plot_as_heatmap", False)),
        names["startAxesFromZero"]: bool(spec.get("start_axes_from_zero", False)),
        names["minXDimension"]: 0,
        names["maxXDimension"]: 0,
        names["minYDimension"]: 0,
        names["maxYDimension"]: 0,
        names["highlightedDimension"]: [],
        names["valuePrefixName"]: value_prefix,
        names["valuePrefixMetric"]: value_prefix_metric,
        names["valuePrefixDict"]: dict(value_prefixes),
        names["IBCSdecimalName"]: int(spec.get("ibcs_decimal", -1)),
        names["logXAxis"]: bool(spec.get("log_x_axis", False)),
        names["logYAxis"]: bool(spec.get("log_y_axis", False)),
        names["showTrendLine"]: bool(spec.get("show_trend_line", False)),
        names["showIsoLine"]: bool(spec.get("show_iso_line", False)),
        names["showScatterLabels"]: bool(spec.get("show_scatter_labels", True)),
        names["positionLegends"]: names["legendsAtRight"],
        names["setFactorParameter"]: 1.0,
        names["isolineMetric"]: spec.get("isoline_metric"),
        names["plotTotalBubble"]: bool(spec.get("plot_total_bubble", False)),
        names["adjustBubbleLabels"]: bool(spec.get("adjust_bubble_labels", False)),
        names["showBubbleLabel"]: names["showBoth"],
        "X": dict(top_axis),
        "Y": dict(panel_axis if small_multiples_dimension else top_axis),
        "W": dict(top_axis),
    }
    _put_if_key(chart, names, "datePeriodName", names["monthName"])
    _put_if_key(chart, names, "periodToDate", False)
    _put_if_key(chart, names, "prepareFileForDownload", False)
    _put_if_key(chart, names, "plotSmallMultiplesWaterfall", False)
    _put_if_key(chart, names, "showInitialAndFinalValues", True)
    _put_if_key(chart, names, "countMetricsAvgArray", [])
    _put_if_key(chart, names, "countMetricsSumArray", [])
    _put_if_key(chart, names, "showMetricsInDataColumn", False)
    _put_if_key(chart, names, "metricsToShowInDataColumn", list(spec["metrics"]))
    _put_if_key(chart, names, "numberOfMetricsInDataColumn", len(spec["metrics"]))
    _put_if_key(chart, names, "showLegend", names["showLegendLeftOrRight"])
    _put_if_key(chart, names, "showAbsoluteValues", True)
    _put_if_key(chart, names, "showRank", True)
    _put_if_key(chart, names, "fatherAndChildDimensions", False)
    _put_if_key(chart, names, "showTopForEachItem", False)
    _put_if_key(chart, names, "excludeOutliers", False)
    if small_multiples_dimension:
        chart[names["plotSmallMultiplesOtherCharts"]] = names["metConditionValue"]
    return chart


def _legacy_param_dict(
    names: dict[str, str],
    *,
    selected_periods: list[str],
    period_totals: dict[str, float],
    columns: list[str],
    least_recent_date: date,
    most_recent_date: date,
) -> dict[str, Any]:
    period_zero = selected_periods[0]
    period_one = selected_periods[-1]
    period_zero_total = period_totals[period_zero]
    period_one_total = period_totals[period_one]
    param = {
        names["columnHash"]: {},
        names["mostRecentDate"]: most_recent_date,
        names["leastRecentDate"]: least_recent_date,
        names["periodLengthInMonths"]: 12,
        names["fileUploadDisabled"]: True,
        names["renameTitlesDict"]: {},
        names["isFilteredKey"]: names["notMetConditionValue"],
        names["numberOfPeriodsFound"]: len(selected_periods),
        names["impossibleToProcessFile"]: False,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["allPeriodsList"]: selected_periods,
        names["selectedPeriods"]: selected_periods,
        names["totalAmountPeriodZero"]: period_zero_total,
        names["totalAmountPeriodOne"]: period_one_total,
        names["totalVarianceValue"]: period_one_total - period_zero_total,
        names["totalAmountPeriodZeroFiltered"]: period_zero_total,
        names["totalAmountPeriodOneFiltered"]: period_one_total,
        names["periodZeroSum"]: period_zero_total,
        names["periodOneSum"]: period_one_total,
    }
    flag_columns = {
        "unitsColFound": "unitsName",
        "volumeColFound": "volumeName",
        "discountColFound": "discountName",
        "marginColFound": "marginName",
        "cogsColFound": "cogsName",
        "monetaryLocalCurrencyColFound": "monetaryLocalCurrencyName",
    }
    for flag, column_key in flag_columns.items():
        _put_if_key(param, names, flag, names[column_key] in columns)
    _put_if_key(param, names, "datePeriodName", names["monthName"])
    return param


def _coerce_date_bound(value: Any, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return fallback


def _canonical_date_bounds(frame: pl.DataFrame) -> tuple[date, date]:
    today = date.today()
    if CANONICAL_DATE not in frame.collect_schema().names():
        return today, today
    bounds = frame.select(
        pl.col(CANONICAL_DATE).min().alias("least"),
        pl.col(CANONICAL_DATE).max().alias("most"),
    ).row(0, named=True)
    return (
        _coerce_date_bound(bounds["least"], today),
        _coerce_date_bound(bounds["most"], today),
    )


def _legacy_df_dict(
    names: dict[str, str], frame: pl.DataFrame
) -> dict[str, pl.DataFrame]:
    return {
        names["dfDatesName"]: frame,
        names["dfPeriodsName"]: frame,
        names["dfAllPeriodsName"]: frame,
        names["dfSnapshotName"]: frame,
        names["dfName"]: frame,
    }


def _collect_lazyframe(frame: pl.LazyFrame) -> pl.DataFrame:
    try:
        return frame.collect(engine="streaming")
    except (TypeError, ValueError, RuntimeError, pl.exceptions.PolarsError):
        return frame.collect()


def _metric_tokens(metric: str) -> set[str]:
    """Return normalized tokens for metric-name semantic checks."""

    return set(METRIC_TOKEN_PATTERN.findall(metric.lower()))


def _metric_name_suggests_value(metric: str) -> bool:
    tokens = _metric_tokens(metric)
    return bool(tokens & {"sales", "revenue", "amount", "value", "turnover"})


def _metric_name_suggests_units(metric: str) -> bool:
    tokens = _metric_tokens(metric)
    if tokens & {"price", "rate", "cost"}:
        return False
    return bool(tokens & {"unit", "units", "volume", "qty", "quantity"})


def _metric_name_suggests_ratio(metric: str) -> bool:
    tokens = _metric_tokens(metric)
    if tokens & {"growth", "change", "variance"}:
        return False
    return bool(tokens & {"price", "rate", "avg", "average"})


def _weighted_x_metric_operands(
    x_metric: str, y_metric: str, bubble_size_metric: str | None
) -> tuple[str, str] | None:
    """Return numerator and denominator for weighted x-axis rollups."""

    if not bubble_size_metric or not _metric_name_suggests_ratio(x_metric):
        return None
    if _metric_name_suggests_value(y_metric) and _metric_name_suggests_units(
        bubble_size_metric
    ):
        return y_metric, bubble_size_metric
    if _metric_name_suggests_value(bubble_size_metric) and _metric_name_suggests_units(
        y_metric
    ):
        return bubble_size_metric, y_metric
    return None


def _with_weighted_x_metric(
    frame: pl.DataFrame | pl.LazyFrame,
    names: dict[str, str],
    chart_dict: dict[str, Any],
) -> pl.LazyFrame:
    """Replace grouped price/rate x metrics with numerator / denominator."""

    x_metric = str(chart_dict[names["xAxisMetric"]])
    y_metric = str(chart_dict[names["yAxisMetric"]])
    bubble_metric = chart_dict.get(names["bubbleSize"])
    operands = _weighted_x_metric_operands(
        x_metric,
        y_metric,
        str(bubble_metric) if bubble_metric else None,
    )
    lf = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    if operands is None:
        return lf
    numerator, denominator = operands
    columns = lf.collect_schema().names()
    if numerator not in columns or denominator not in columns:
        return lf
    return lf.with_columns(
        pl.when(pl.col(denominator).abs() > 0)
        .then(pl.col(numerator) / pl.col(denominator))
        .otherwise(0.0)
        .alias(x_metric)
    )


def _display_value_prefixes(spec: dict[str, Any]) -> dict[str, str]:
    return {
        str(metric): str(prefix)
        for metric, prefix in dict(spec.get("display_value_prefixes") or {}).items()
        if str(prefix) in VALUE_PREFIX_DIVISORS and str(prefix)
    }


def _is_generated_other_label(value: Any, names: dict[str, str]) -> bool:
    if not isinstance(value, str):
        return False
    label = value.strip().lower()
    aggregate_prefix = str(names["aggregateOtherItemsName"]).strip().lower()
    return (
        label.startswith(aggregate_prefix)
        or label.startswith("other rank >")
        or label.startswith("others rank >")
    )


def _generated_other_expr(column: str, names: dict[str, str]) -> pl.Expr:
    text = pl.col(column).cast(pl.Utf8)
    lowered = text.str.to_lowercase()
    return (
        text.str.starts_with(str(names["aggregateOtherItemsName"])).fill_null(False)
        | lowered.str.starts_with("other rank >").fill_null(False)
        | lowered.str.starts_with("others rank >").fill_null(False)
    )


def _with_display_value_prefixes(
    frame: pl.DataFrame | pl.LazyFrame, spec: dict[str, Any]
) -> pl.LazyFrame:
    """Apply legacy value-prefix scaling to bubble display metrics."""

    lf = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    if spec["legacy_chart_key"] != "bubbleChart":
        return lf
    value_prefixes = _display_value_prefixes(spec)
    if not value_prefixes:
        return lf
    columns = lf.collect_schema().names()
    expressions = []
    for metric, prefix in value_prefixes.items():
        divisor = VALUE_PREFIX_DIVISORS[prefix]
        if metric in columns and divisor != 1:
            expressions.append((pl.col(metric) / divisor).alias(metric))
    if not expressions:
        return lf
    return lf.with_columns(expressions)


def _has_generated_other_rows(
    frame: pl.DataFrame | pl.LazyFrame,
    names: dict[str, str],
    chart_dict: dict[str, Any],
) -> bool:
    if chart_dict.get(names["chosenChart"]) != names["bubbleChart"]:
        return False
    chosen_dimension = chart_dict.get(names["xAxisDimension"])
    if not isinstance(chosen_dimension, str) or not chosen_dimension:
        return False
    lf = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    if chosen_dimension not in lf.collect_schema().names():
        return False
    result = _collect_lazyframe(
        lf.select(
            _generated_other_expr(chosen_dimension, names)
            .any()
            .alias("__has_generated_other")
        )
    )
    return bool(result.item())


def _is_generated_other_color_item(item: Any, names: dict[str, str]) -> bool:
    other_name = str(names["otherName"])
    return isinstance(item, str) and (
        item == other_name or _is_generated_other_label(item, names)
    )


def _with_generated_other_color_bucket(
    frame: pl.DataFrame | pl.LazyFrame,
    names: dict[str, str],
    chart_dict: dict[str, Any],
) -> pl.LazyFrame:
    chosen_dimension = chart_dict.get(names["xAxisDimension"])
    color_dimension = chart_dict.get(names["yAxisDimension"])
    if not isinstance(chosen_dimension, str) or not isinstance(color_dimension, str):
        return frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    lf = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    columns = set(lf.collect_schema().names())
    if chosen_dimension not in columns or color_dimension not in columns:
        return lf
    return lf.with_columns(
        pl.when(_generated_other_expr(chosen_dimension, names))
        .then(pl.lit(str(names["otherName"])))
        .otherwise(pl.col(color_dimension))
        .alias(color_dimension)
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, pl.LazyFrame):
        return {"type": "LazyFrame", "columns": value.collect_schema().names()}
    if isinstance(value, pl.DataFrame):
        return {
            "type": "DataFrame",
            "columns": value.collect_schema().names(),
            "row_count": value.height,
        }
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, TypeError, ValueError):
            return str(value)
    return value


def _frame_payload(frame: Any) -> dict[str, Any]:
    if isinstance(frame, pl.LazyFrame):
        collected = _collect_lazyframe(frame)
    elif isinstance(frame, pl.DataFrame):
        collected = frame
    else:
        return {"type": type(frame).__name__, "rows": []}
    return {
        "type": "DataFrame",
        "columns": collected.collect_schema().names(),
        "row_count": collected.height,
        "rows": collected.head(250).to_dicts(),
    }


def _figure_payload(fig: Any) -> dict[str, Any]:
    if fig is None or not hasattr(fig, "to_plotly_json"):
        return {"type": type(fig).__name__}
    payload = fig.to_plotly_json()
    return {
        "trace_count": len(payload.get("data", [])),
        "layout_keys": sorted(payload.get("layout", {}).keys()),
    }


def _capture_context_payload(
    *,
    spec: dict[str, Any],
    chart_output: Any | None,
    figures: list[Any],
    exports: list[dict[str, Any]],
    source_functions: list[str],
    draw_invocations: list[str],
) -> dict[str, Any] | None:
    if not spec.get("capture_chart_data"):
        return None
    frame = getattr(chart_output, "frame", None)
    chart_dict = getattr(chart_output, "chart_dict", {})
    return {
        "schema_version": "1.0",
        "chart": spec["name"],
        "legacy_chart": spec["legacy_chart_key"],
        "chart_data_source": "legacy set_up_tab_for_show_or_download_chart input dataframe",
        "dimensions": list(spec["dimensions"]),
        "dot_dimension": spec["dot_dimension"],
        "color_dimension": spec.get("color_dimension"),
        "x_metric": spec["x_metric"],
        "y_metric": spec["y_metric"],
        "bubble_size_metric": spec.get("bubble_size_metric"),
        "display_value_prefixes": _display_value_prefixes(spec),
        "selected_periods": list(spec["selected_periods"]),
        "show_iso_line": bool(spec.get("show_iso_line")),
        "isoline_metric": spec.get("isoline_metric"),
        "source_functions": source_functions,
        "legacy_draw_function_invocations": draw_invocations,
        "data_frame": _frame_payload(frame),
        "chart_dict": _json_safe(chart_dict),
        "plotly_figures": [_figure_payload(fig) for fig in figures],
        "exports": exports,
    }


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


def _subplot_grid_size(fig: Any) -> tuple[int, int]:
    layout = getattr(fig, "layout", None)
    columns = max(len(_axis_domains(layout, "x")), 1)
    rows = max(len(_axis_domains(layout, "y")), 1)
    return columns, rows


def _legacy_export_size(fig: Any) -> tuple[int, int]:
    layout = getattr(fig, "layout", None)
    layout_width = int(getattr(layout, "width", 0) or 0)
    layout_height = int(getattr(layout, "height", 0) or 0)
    columns, rows = _subplot_grid_size(fig)
    if columns * rows > 1:
        width = max(layout_width, 420 + columns * 780)
        height = max(layout_height, 260 + rows * 520)
        return min(width, 2600), min(height, 2400)
    return max(layout_width, 1200), max(layout_height, 900)


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
    fig: Any,
    path: Path,
) -> tuple[list[Path], dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    export_fig, normalization_audit = normalize_plotly_figure_for_static_export(fig)
    export_width, export_height = _legacy_export_size(export_fig)
    title_lines = plotly_title_lines(getattr(export_fig.layout.title, "text", ""))
    export_fig.update_layout(
        width=export_width,
        height=export_height,
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    try:
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
    return [line for line in candidates if plain_plotly_title_text(line)]


def _apply_scatter_title_contract(fig: Any, recipe: dict[str, Any]) -> list[str]:
    """Normalize scatter/bubble figures to the three-row title contract."""

    subject = reporting_entity_label_from_recipe(recipe) or "Scatter analysis"
    legacy_lines = _legacy_visible_title_lines(fig, subject)
    what = legacy_lines[1] if len(legacy_lines) >= 2 else "Relationship view"
    when = reporting_period_line_from_recipe(
        recipe,
        current_label=CURRENT_PERIOD,
        previous_label="PY",
    )
    return apply_three_row_plotly_title(
        fig,
        ReportingTitleContract(who=subject, what=what, when=when),
    )


def _write_captured_figures(
    figures: list[Any],
    output_dir: Path,
    artifact_name: str,
    recipe: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    if not figures:
        return [], []
    paths: list[str] = []
    exports: list[dict[str, Any]] = []
    for index, fig in enumerate(figures, start=1):
        path = output_dir / artifact_name
        if len(figures) > 1:
            path = path.with_name(f"{path.stem}_{index}{path.suffix}")
        export_fig, capture_normalization_audit = (
            normalize_plotly_figure_for_static_export(fig)
        )
        _apply_scatter_title_contract(export_fig, recipe)
        written_paths, export = _write_legacy_figure(export_fig, path)
        export["captured_figure_normalization"] = capture_normalization_audit
        paths.extend(str(written_path) for written_path in written_paths)
        exports.append(export)
    return paths, exports


def _chart_group_key(
    cache: LegacyPreparedDataCache,
    names: dict[str, str],
    df_copy: pl.DataFrame | pl.LazyFrame,
    column: str,
    small_multiples_column_array: list[str],
    x_column: str,
    value_cols: list[str],
    chart_dict: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        cache._frame_signature(df_copy),
        chart_dict[names["chosenChart"]],
        column,
        tuple(small_multiples_column_array),
        x_column,
        tuple(value_cols),
        chart_dict[names["xAxisDimension"]],
        chart_dict[names["yAxisDimension"]],
        chart_dict[names["smallMultiplesColumn"]],
        chart_dict[names["xAxisMetric"]],
        chart_dict[names["yAxisMetric"]],
        chart_dict.get(names["bubbleSize"]),
        tuple(sorted(dict(chart_dict.get(names["valuePrefixDict"], {})).items())),
    )


@contextlib.contextmanager
def _patched_legacy_preparation(
    *,
    plot_charts_module: Any,
    prepare_charts_module: Any,
    draw_bubble_module: Any,
    prepared_data_cache: LegacyPreparedDataCache | None,
    names: dict[str, str],
    spec: dict[str, Any],
    draw_invocations: list[str],
):
    original_scatter_group = plot_charts_module.group_by_dataset_for_scatter_plot
    original_prepare_scatter_group = (
        prepare_charts_module.group_by_dataset_for_scatter_plot
    )
    original_bubble_group = plot_charts_module.group_by_dataset_for_bubble_plot
    original_prepare_bubble_group = (
        prepare_charts_module.group_by_dataset_for_bubble_plot
    )
    original_prepare_bubble_sum = (
        plot_charts_module.prepare_sum_dataframe_for_bubble_plot
    )
    original_show_only_largest = plot_charts_module.show_only_largest
    original_draw_scatter = plot_charts_module.draw_scatter_chart
    original_draw_bubble = plot_charts_module.draw_bubble_chart
    original_scatter_datashader = plot_charts_module.plot_scatter_chart_datashader
    original_add_bubbles_to_bubble_chart = (
        draw_bubble_module.add_bubbles_to_bubble_chart
    )
    original_setup_chart_output = (
        plot_charts_module.set_up_tab_for_show_or_download_chart
    )
    original_get_mins_and_maxes = plot_charts_module.get_mins_and_maxes

    def _preserve_scatter_small_multiple_rows(
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
        key: str,
    ) -> tuple[pl.LazyFrame, list[Any], str, list[str]] | None:
        is_scatter = chart_dict[names["chosenChart"]] == names["scatterChart"]
        is_small_multiple_axis = column == chart_dict[names["smallMultiplesColumn"]]
        if not is_scatter or key != "Y" or not is_small_multiple_axis:
            return None
        dot_dimension = chart_dict[names["xAxisDimension"]]
        if dot_dimension in [
            names["nothingFilteredName"],
            False,
            names["notMetConditionValue"],
        ]:
            return None
        frame = LegacyPreparedDataCache._collect_frame(df_copy)
        columns = frame.collect_schema().names()
        ranking_metric = next(
            (metric for metric in reversed(value_cols) if metric in columns),
            None,
        )
        if (
            column not in columns
            or dot_dimension not in columns
            or ranking_metric is None
        ):
            return None
        panel_limit = max(int(chart_dict[key][names["numberOfTop"]]), 1)
        top_panels = (
            frame.group_by(column)
            .agg(pl.col(ranking_metric).sum().alias("__scatter_panel_rank"))
            .sort("__scatter_panel_rank", descending=True)
            .head(panel_limit)
            .get_column(column)
            .to_list()
        )
        if not top_panels:
            return None
        filtered = frame.filter(pl.col(column).is_in(top_panels))
        return filtered.lazy(), top_panels, "", value_cols

    def _cached_scatter_group(
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        small_multiples_column_array: list[str],
        x_column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
    ) -> tuple[pl.LazyFrame, list[str]]:
        def build_group() -> tuple[pl.LazyFrame, list[str]]:
            frame, group_cols = original_scatter_group(
                df_copy,
                column,
                small_multiples_column_array,
                x_column,
                value_cols,
                chart_dict,
            )
            return _with_weighted_x_metric(frame, names, chart_dict), group_cols

        if prepared_data_cache is None:
            return build_group()
        return prepared_data_cache.get_frame_payload(
            "scatter_grouped",
            _chart_group_key(
                prepared_data_cache,
                names,
                df_copy,
                column,
                small_multiples_column_array,
                x_column,
                value_cols,
                chart_dict,
            ),
            build_group,
        )

    def _cached_bubble_group(
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        small_multiples_column_array: list[str],
        x_column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
    ) -> tuple[pl.LazyFrame, list[str]]:
        def build_group() -> tuple[pl.LazyFrame, list[str]]:
            frame, group_cols = original_bubble_group(
                df_copy,
                column,
                small_multiples_column_array,
                x_column,
                value_cols,
                chart_dict,
            )
            return _with_weighted_x_metric(frame, names, chart_dict), group_cols

        if prepared_data_cache is None:
            return build_group()
        return prepared_data_cache.get_frame_payload(
            "bubble_grouped",
            _chart_group_key(
                prepared_data_cache,
                names,
                df_copy,
                column,
                small_multiples_column_array,
                x_column,
                value_cols,
                chart_dict,
            ),
            build_group,
        )

    def _cached_show_only_largest(
        df_copy: pl.DataFrame | pl.LazyFrame,
        column: str,
        second_column: str | None,
        time_column: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
        param_dict: dict[str, Any],
        key: str,
    ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
        preserved = _preserve_scatter_small_multiple_rows(
            df_copy,
            column,
            value_cols,
            chart_dict,
            key,
        )
        if preserved is not None:
            frame, unique_items, aggregate_other, prepared_value_cols = preserved
            return (
                _with_weighted_x_metric(frame, names, chart_dict),
                unique_items,
                aggregate_other,
                prepared_value_cols,
            )

        def build_show_only() -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
            frame, unique_items, aggregate_other, prepared_value_cols = (
                original_show_only_largest(
                    df_copy,
                    column,
                    second_column,
                    time_column,
                    value_cols,
                    chart_dict,
                    param_dict,
                    key,
                )
            )
            return (
                _with_weighted_x_metric(frame, names, chart_dict),
                unique_items,
                aggregate_other,
                prepared_value_cols,
            )

        if prepared_data_cache is None:
            return build_show_only()
        return prepared_data_cache.get_show_only_largest(
            names,
            lambda *args: build_show_only(),
            df_copy,
            column,
            second_column,
            time_column,
            value_cols,
            chart_dict,
            param_dict,
            key,
        )

    def _tracked_draw_scatter(*args: Any, **kwargs: Any) -> Any:
        draw_invocations.append("modules.charting.draw_scatter.draw_scatter_chart")
        return original_draw_scatter(*args, **kwargs)

    def _scaled_display_frame(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
        return _collect_lazyframe(_with_display_value_prefixes(frame, spec))

    def _tracked_draw_bubble(*args: Any, **kwargs: Any) -> Any:
        draw_invocations.append("modules.charting.draw_bubble.draw_bubble_chart")
        draw_args = list(args)
        if len(draw_args) > 1:
            draw_args[1] = _scaled_display_frame(draw_args[1])
        if len(draw_args) > 7:
            draw_args[7] = _scaled_display_frame(draw_args[7])
        return original_draw_bubble(*draw_args, **kwargs)

    def _get_mins_and_maxes_with_eager_frames(
        data_array: list[pl.DataFrame | pl.LazyFrame],
        chart_dict: dict[str, Any],
    ) -> dict[str, Any]:
        frames = [
            _collect_lazyframe(frame) if isinstance(frame, pl.LazyFrame) else frame
            for frame in data_array
        ]
        return original_get_mins_and_maxes(frames, chart_dict)

    def _add_bubbles_without_generated_other_legend(*args: Any, **kwargs: Any) -> Any:
        if len(args) < 9:
            return original_add_bubbles_to_bubble_chart(*args, **kwargs)
        (
            fig,
            frame,
            plot_legend,
            chart_dict,
            color_array,
            color_dimension_array,
            size_ref,
            count_rows,
            count_cols,
        ) = args[:9]
        has_generated_other = _has_generated_other_rows(frame, names, chart_dict)
        if not plot_legend or not has_generated_other or not color_dimension_array:
            return original_add_bubbles_to_bubble_chart(*args, **kwargs)

        frame = _with_generated_other_color_bucket(frame, names, chart_dict)
        colors = list(color_array or [])
        color_items = list(color_dimension_array)
        other_item = str(names["otherName"])
        if not any(_is_generated_other_color_item(item, names) for item in color_items):
            color_items.append(other_item)
            colors.append("#D9D9D9")

        legend_items: list[Any] = []
        legend_colors: list[str] = []
        generated_other_items: list[Any] = []
        generated_other_colors: list[str] = []
        fallback_color = colors[-1] if colors else "#D9D9D9"
        for index, item in enumerate(color_items):
            color = colors[index] if index < len(colors) else fallback_color
            if _is_generated_other_color_item(item, names):
                generated_other_items.append(item)
                generated_other_colors.append("#D9D9D9")
            else:
                legend_items.append(item)
                legend_colors.append(color)

        if not generated_other_items:
            return original_add_bubbles_to_bubble_chart(*args, **kwargs)

        output_fig = fig
        if legend_items:
            output_fig = original_add_bubbles_to_bubble_chart(
                output_fig,
                frame,
                plot_legend,
                chart_dict,
                legend_colors,
                legend_items,
                size_ref,
                count_rows,
                count_cols,
            )
        trace_start = len(output_fig.data)
        output_fig = original_add_bubbles_to_bubble_chart(
            output_fig,
            frame,
            False,
            chart_dict,
            generated_other_colors,
            generated_other_items,
            size_ref,
            count_rows,
            count_cols,
        )
        for trace in output_fig.data[trace_start:]:
            trace.showlegend = False
            trace.name = None
        return output_fig

    def _scaled_setup_chart_output(*args: Any, **kwargs: Any) -> Any:
        setup_args = list(args)
        if setup_args:
            setup_args[0] = _scaled_display_frame(setup_args[0])
        return original_setup_chart_output(*setup_args, **kwargs)

    def _tracked_scatter_datashader(*args: Any, **kwargs: Any) -> Any:
        draw_invocations.append(
            "modules.charting.plot_charts.plot_scatter_chart_datashader"
        )
        return original_scatter_datashader(*args, **kwargs)

    def _weighted_prepare_bubble_sum(*args: Any, **kwargs: Any) -> Any:
        frame = original_prepare_bubble_sum(*args, **kwargs)
        chart_dict = args[4] if len(args) > 4 else kwargs["chartDict"]
        return _with_weighted_x_metric(frame, names, chart_dict)

    plot_charts_module.group_by_dataset_for_scatter_plot = _cached_scatter_group
    prepare_charts_module.group_by_dataset_for_scatter_plot = _cached_scatter_group
    plot_charts_module.group_by_dataset_for_bubble_plot = _cached_bubble_group
    prepare_charts_module.group_by_dataset_for_bubble_plot = _cached_bubble_group
    plot_charts_module.prepare_sum_dataframe_for_bubble_plot = (
        _weighted_prepare_bubble_sum
    )
    plot_charts_module.show_only_largest = _cached_show_only_largest
    plot_charts_module.draw_scatter_chart = _tracked_draw_scatter
    plot_charts_module.draw_bubble_chart = _tracked_draw_bubble
    plot_charts_module.plot_scatter_chart_datashader = _tracked_scatter_datashader
    plot_charts_module.get_mins_and_maxes = _get_mins_and_maxes_with_eager_frames
    draw_bubble_module.add_bubbles_to_bubble_chart = (
        _add_bubbles_without_generated_other_legend
    )
    plot_charts_module.set_up_tab_for_show_or_download_chart = (
        _scaled_setup_chart_output
    )
    try:
        yield
    finally:
        plot_charts_module.group_by_dataset_for_scatter_plot = original_scatter_group
        prepare_charts_module.group_by_dataset_for_scatter_plot = (
            original_prepare_scatter_group
        )
        plot_charts_module.group_by_dataset_for_bubble_plot = original_bubble_group
        prepare_charts_module.group_by_dataset_for_bubble_plot = (
            original_prepare_bubble_group
        )
        plot_charts_module.prepare_sum_dataframe_for_bubble_plot = (
            original_prepare_bubble_sum
        )
        plot_charts_module.show_only_largest = original_show_only_largest
        plot_charts_module.draw_scatter_chart = original_draw_scatter
        plot_charts_module.draw_bubble_chart = original_draw_bubble
        plot_charts_module.plot_scatter_chart_datashader = original_scatter_datashader
        plot_charts_module.get_mins_and_maxes = original_get_mins_and_maxes
        draw_bubble_module.add_bubbles_to_bubble_chart = (
            original_add_bubbles_to_bubble_chart
        )
        plot_charts_module.set_up_tab_for_show_or_download_chart = (
            original_setup_chart_output
        )


def write_legacy_scatter_bubble_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    prepared_data_cache: LegacyPreparedDataCache | None = None,
    *,
    render: bool = True,
) -> LegacyScatterBubbleChartExport:
    """Run one vendored legacy scatter/bubble chart attempt and export figures."""

    ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from modules.chart_harness import apply_legacy_filter_title_metadata
        from modules.charting import draw_bubble as draw_bubble_module
        from modules.charting import plot_charts as plot_charts_module
        from modules.charting import prepare_charts as prepare_charts_module
        from modules.utilities.config import get_naming_params
        from modules.utilities.ui_notifier import HeadlessChartCapture, use_ui_notifier

        names = get_naming_params()
        cache_start = (
            prepared_data_cache.snapshot() if prepared_data_cache is not None else None
        )

        def _cache_audit() -> dict[str, Any]:
            if prepared_data_cache is None or cache_start is None:
                return {"prepared_data_cache": {"enabled": False}}
            return prepared_data_cache.audit_delta(cache_start)

        currency = str((recipe["options"])["currency"])
        chart = _legacy_chart_dict(names, spec, currency=currency)
        reporting_entity = reporting_entity_label_from_recipe(recipe)
        if reporting_entity:
            chart[names["companyName"]] = reporting_entity
        chart = apply_legacy_filter_title_metadata(chart, names, recipe)
        selected_periods = [str(item) for item in chart[names["selectedPeriods"]]]
        canonical_columns = canonical.collect_schema().names()
        period_total_metric = next(
            (
                metric
                for metric in [
                    str(spec.get("bubble_size_metric") or ""),
                    str(spec.get("y_metric") or ""),
                    str(spec.get("x_metric") or ""),
                ]
                if metric in canonical_columns
            ),
            None,
        )
        period_totals = {period: 0.0 for period in selected_periods}
        if period_total_metric:
            period_totals.update(
                {
                    str(row[CANONICAL_PERIOD]): float(row[period_total_metric] or 0.0)
                    for row in canonical.group_by(CANONICAL_PERIOD)
                    .agg(pl.col(period_total_metric).sum().alias(period_total_metric))
                    .iter_rows(named=True)
                }
            )
        for period in selected_periods:
            period_totals.setdefault(period, 0.0)
        least_recent_date, most_recent_date = _canonical_date_bounds(canonical)
        param = _legacy_param_dict(
            names,
            selected_periods=selected_periods,
            period_totals=period_totals,
            columns=canonical_columns,
            least_recent_date=least_recent_date,
            most_recent_date=most_recent_date,
        )
        df_dict = _legacy_df_dict(names, canonical)
        value_cols = list(dict.fromkeys(str(item) for item in spec["metrics"]))
        source_functions = _legacy_source_functions(spec)
        draw_invocations: list[str] = []
        notifier = HeadlessChartCapture()
        with use_ui_notifier(notifier):
            try:
                with _patched_legacy_preparation(
                    plot_charts_module=plot_charts_module,
                    prepare_charts_module=prepare_charts_module,
                    draw_bubble_module=draw_bubble_module,
                    prepared_data_cache=prepared_data_cache,
                    names=names,
                    spec=spec,
                    draw_invocations=draw_invocations,
                ):
                    if spec["plotter"] == "plot_scatter_charts":
                        plot_charts_module.plot_scatter_charts(
                            canonical.lazy(),
                            list(spec["dimensions"]),
                            value_cols,
                            chart,
                            value_cols,
                            CANONICAL_PERIOD,
                            param,
                            df_dict,
                        )
                    else:
                        plot_charts_module.plot_bubble_charts(
                            canonical.lazy(),
                            list(spec["dimensions"]),
                            value_cols,
                            chart,
                            CANONICAL_PERIOD,
                            param,
                            df_dict,
                        )
            except (
                AttributeError,
                ImportError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                pl.exceptions.PolarsError,
            ) as exc:
                return LegacyScatterBubbleChartExport(
                    paths=[],
                    audit={
                        "status": "failed_legacy",
                        "chart": spec["name"],
                        "legacy_chart": chart[names["chosenChart"]],
                        "legacy_reference_function": (
                            f"modules.charting.plot_charts.{spec['plotter']}"
                        ),
                        "legacy_reference_function_call_mode": "executed_headless",
                        "legacy_draw_function_invocations": draw_invocations,
                        "metrics_to_plot": chart[names["metricsToPlot"]],
                        "value_cols": value_cols,
                        "x_metric": chart[names["xAxisMetric"]],
                        "y_metric": chart[names["yAxisMetric"]],
                        "bubble_size_metric": chart.get(names["bubbleSize"]),
                        "show_iso_line": chart.get(names["showIsoLine"]),
                        "isoline_metric": chart.get(names["isolineMetric"]),
                        "dot_dimension": chart[names["xAxisDimension"]],
                        "color_dimension": chart[names["yAxisDimension"]],
                        **_cache_audit(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "error_traceback": traceback.format_exc(),
                        "events": notifier.events,
                        "source_functions": source_functions,
                    },
                )

        error_events = [
            event for event in notifier.events if event.get("level") == "error"
        ]
        if error_events:
            return LegacyScatterBubbleChartExport(
                paths=[],
                audit={
                    "status": "failed_legacy_caught",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "legacy_reference_function": (
                        f"modules.charting.plot_charts.{spec['plotter']}"
                    ),
                    "legacy_reference_function_call_mode": "executed_headless",
                    "legacy_draw_function_invocations": draw_invocations,
                    "metrics_to_plot": chart[names["metricsToPlot"]],
                    "value_cols": value_cols,
                    "x_metric": chart[names["xAxisMetric"]],
                    "y_metric": chart[names["yAxisMetric"]],
                    "bubble_size_metric": chart.get(names["bubbleSize"]),
                    "show_iso_line": chart.get(names["showIsoLine"]),
                    "isoline_metric": chart.get(names["isolineMetric"]),
                    "dot_dimension": chart[names["xAxisDimension"]],
                    "color_dimension": chart[names["yAxisDimension"]],
                    **_cache_audit(),
                    "error_events": error_events,
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )

        chart_outputs = notifier.chart_outputs
        figures = [output.figure for output in chart_outputs]
        if spec.get("capture_figure") == "last" and figures:
            figures = figures[-1:]
            chart_outputs = chart_outputs[-1:]
        elif spec.get("capture_figure") == "first" and figures:
            figures = figures[:1]
            chart_outputs = chart_outputs[:1]
        paths: list[str] = []
        exports: list[dict[str, Any]] = []
        if render:
            paths, exports = _write_captured_figures(
                figures,
                output_dir,
                str(spec["artifact_name"]),
                recipe,
            )
        if render and not paths:
            return LegacyScatterBubbleChartExport(
                paths=[],
                audit={
                    "status": "not_written_legacy_no_figure",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "legacy_reference_function": (
                        f"modules.charting.plot_charts.{spec['plotter']}"
                    ),
                    "legacy_reference_function_call_mode": "executed_headless",
                    "legacy_draw_function_invocations": draw_invocations,
                    "metrics_to_plot": chart[names["metricsToPlot"]],
                    "value_cols": value_cols,
                    "x_metric": chart[names["xAxisMetric"]],
                    "y_metric": chart[names["yAxisMetric"]],
                    "bubble_size_metric": chart.get(names["bubbleSize"]),
                    "show_iso_line": chart.get(names["showIsoLine"]),
                    "isoline_metric": chart.get(names["isolineMetric"]),
                    "dot_dimension": chart[names["xAxisDimension"]],
                    "color_dimension": chart[names["yAxisDimension"]],
                    **_cache_audit(),
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )

    chart_context = _capture_context_payload(
        spec=spec,
        chart_output=chart_outputs[-1] if chart_outputs else None,
        figures=figures,
        exports=exports,
        source_functions=source_functions,
        draw_invocations=draw_invocations,
    )
    return LegacyScatterBubbleChartExport(
        paths=paths,
        audit={
            "status": "written" if render else "data_written",
            "chart": spec["name"],
            "legacy_chart": chart[names["chosenChart"]],
            "legacy_reference_function": f"modules.charting.plot_charts.{spec['plotter']}",
            "legacy_reference_function_call_mode": "executed_headless",
            "legacy_draw_function_invocations": draw_invocations,
            "metrics_to_plot": chart[names["metricsToPlot"]],
            "value_cols": value_cols,
            "x_metric": chart[names["xAxisMetric"]],
            "y_metric": chart[names["yAxisMetric"]],
            "bubble_size_metric": chart.get(names["bubbleSize"]),
            "display_value_prefixes": _display_value_prefixes(spec),
            "show_iso_line": chart.get(names["showIsoLine"]),
            "isoline_metric": chart.get(names["isolineMetric"]),
            "dot_dimension": chart[names["xAxisDimension"]],
            "color_dimension": chart[names["yAxisDimension"]],
            "colorpalette": chart[names["colorpalette"]],
            **_cache_audit(),
            "exports": exports,
            "dimensions": spec["dimensions"],
            "small_multiples_dimension": spec.get("small_multiples_dimension"),
            "dimension_selection": spec.get("dimension_selection"),
            "rendered": render,
            "events": notifier.events,
            "source_functions": source_functions,
        },
        chart_context=chart_context,
    )
