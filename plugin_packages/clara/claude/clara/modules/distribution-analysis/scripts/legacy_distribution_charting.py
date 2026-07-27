"""Headless adapters for vendored legacy distribution charts."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import polars as pl

__all__ = [
    "CANONICAL_DATE",
    "CANONICAL_PERIOD",
    "CURRENT_PERIOD",
    "LegacyDistributionChartExport",
    "LegacyPreparedDataCache",
    "cleanup_legacy_imports",
    "ensure_legacy_import_path",
    "write_legacy_distribution_chart",
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
from modules.chart_harness import reporting_entity_label_from_recipe  # noqa: E402
from modules.charting.static_export import (  # noqa: E402
    normalize_plotly_figure_for_static_export,
)

CANONICAL_DATE = "Date"
CANONICAL_PERIOD = "Period"
CURRENT_PERIOD = "AC"
HEADLESS_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


@dataclass(frozen=True)
class LegacyDistributionChartExport:
    """Exported paths and audit information for one legacy chart attempt."""

    paths: list[str]
    audit: dict[str, Any]
    chart_context: dict[str, Any] | None = None


@dataclass
class LegacyPreparedDataCache:
    """Prepared data reused by legacy distribution render calls."""

    stage_frames: dict[tuple[Any, ...], pl.DataFrame]
    stage_payloads: dict[tuple[Any, ...], Any]
    hits: int = 0
    misses: int = 0
    aggregate_hits: int = 0
    aggregate_misses: int = 0
    topn_hits: int = 0
    topn_misses: int = 0

    @classmethod
    def empty(cls) -> "LegacyPreparedDataCache":
        """Return an empty cache for one plugin run."""

        return cls(stage_frames={}, stage_payloads={})

    def snapshot(self) -> tuple[int, int, int, int, int, int]:
        """Return current cache hit/miss counters."""

        return (
            self.hits,
            self.misses,
            self.aggregate_hits,
            self.aggregate_misses,
            self.topn_hits,
            self.topn_misses,
        )

    def audit_delta(self, start: tuple[int, int, int, int, int, int]) -> dict[str, Any]:
        """Return cache activity since ``start``."""

        (
            start_hits,
            start_misses,
            start_aggregate_hits,
            start_aggregate_misses,
            start_topn_hits,
            start_topn_misses,
        ) = start
        return {
            "prepared_data_cache": {
                "enabled": True,
                "scope": "legacy_distribution_prepared_data",
                "hits": self.hits - start_hits,
                "misses": self.misses - start_misses,
                "aggregate_hits": self.aggregate_hits - start_aggregate_hits,
                "aggregate_misses": self.aggregate_misses - start_aggregate_misses,
                "topn_hits": self.topn_hits - start_topn_hits,
                "topn_misses": self.topn_misses - start_topn_misses,
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

    def get_distribution_aggregate(
        self,
        names: dict[str, str],
        original: Callable[..., pl.LazyFrame],
        df_copy: pl.DataFrame | pl.LazyFrame,
        element: str,
        value_cols: list[str],
        chart_dict: dict[str, Any],
    ) -> pl.LazyFrame:
        """Return cached legacy distribution aggregation output."""

        cache_key = (
            self._frame_signature(df_copy),
            element,
            tuple(value_cols),
            chart_dict[names["xAxisDimension"]],
        )
        cached = self.stage_frames.get(("distribution_aggregate", *cache_key))
        if cached is not None:
            self.hits += 1
            self.aggregate_hits += 1
            return cached.lazy()
        frame = original(df_copy, element, value_cols, chart_dict)
        collected = self._collect_frame(frame)
        self.stage_frames[("distribution_aggregate", *cache_key)] = collected
        self.misses += 1
        self.aggregate_misses += 1
        return collected.lazy()

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
        """Return cached legacy top-N/Other-bucket preparation output."""

        axis_config = chart_dict[key]
        cache_key = (
            self._frame_signature(df_copy),
            column,
            second_column,
            time_column,
            tuple(value_cols),
            key,
            axis_config[names["numberOfTop"]],
            axis_config[names["aggregateOtherItems"]],
        )
        cached = self.stage_payloads.get(("show_only_largest", *cache_key))
        if cached is not None:
            self.hits += 1
            self.topn_hits += 1
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
        self.topn_misses += 1
        return (
            collected.lazy(),
            list(unique_items),
            aggregate_other,
            list(prepared_value_cols),
        )


def ensure_legacy_import_path() -> None:
    """Make the shared or packaged legacy modules importable."""

    _activate_legacy_import_parent()
    _install_polars_headless_compat()


def _install_polars_headless_compat() -> None:
    """Install compatibility shims used by the vendored chart code."""

    if not hasattr(pl.LazyFrame, "get_column"):

        def _get_column(self: pl.LazyFrame, column: str) -> pl.Series:
            return (
                self.select(pl.col(column))
                .collect(engine="streaming")
                .get_column(column)
            )

        pl.LazyFrame.get_column = _get_column  # type: ignore[attr-defined]


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


@contextlib.contextmanager
def _capture_legacy_ui() -> Any:
    ensure_legacy_import_path()
    from modules.utilities.ui_notifier import HeadlessChartCapture, use_ui_notifier

    notifier = HeadlessChartCapture()
    with use_ui_notifier(notifier):
        yield notifier


def _legacy_chart_dict(
    names: dict[str, str],
    spec: dict[str, Any],
    *,
    metric: str,
    currency: str,
) -> dict[str, Any]:
    """Return a legacy chart dictionary for one distribution spec."""

    max_items = int(spec.get("max_items") or 8)
    small_multiples_dimension = spec.get("small_multiples_dimension")
    small_multiples_count = 0
    if small_multiples_dimension:
        small_multiples_count = max(
            2, int(spec.get("small_multiples_max_panels") or min(max_items, 6))
        )
        panel_number_of_top = max(small_multiples_count - 1, 1)
    else:
        panel_number_of_top = max_items
    aggregate_other_items = bool(spec.get("aggregate_other_items", True))
    selected_periods = [
        str(item) for item in spec.get("selected_periods") or [CURRENT_PERIOD] if item
    ]
    nothing = names["nothingFilteredName"]
    met = names["metConditionValue"]
    not_met = names["notMetConditionValue"]
    x_axis = {
        names["numberOfTop"]: panel_number_of_top,
        names["aggregateOtherItems"]: aggregate_other_items,
    }
    y_axis = {
        names["numberOfTop"]: panel_number_of_top,
        names["aggregateOtherItems"]: aggregate_other_items,
    }
    w_axis = {
        names["numberOfTop"]: panel_number_of_top,
        names["aggregateOtherItems"]: aggregate_other_items,
    }
    chart = {
        names["chosenChart"]: names[str(spec["legacy_chart_key"])],
        names["selectedPeriods"]: selected_periods,
        names["toPlotPeriod"]: selected_periods[-1],
        names["plotSmallMultiplesOtherCharts"]: (
            met if small_multiples_dimension else False
        ),
        names["smallMultiplesColumn"]: small_multiples_dimension or nothing,
        names["numberOfPlottedSmallMultiples"]: small_multiples_count,
        names["rowToPlotName"]: names["entireDatasetName"],
        names["metricsToPlot"]: [metric],
        names["singleMetric"]: metric,
        names["xAxisMetric"]: metric,
        names["yAxisMetric"]: metric,
        names["xAxisDimension"]: spec.get("distribution_dimension") or nothing,
        names["yAxisDimension"]: nothing,
        names["selectDimensionsToPlot"]: (
            [small_multiples_dimension] if small_multiples_dimension else []
        ),
        names["mainDimension"]: [],
        names["colorChoice"]: names["redToGreen"],
        names["colorpalette"]: names["IBCSColorpalette"],
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["filterDates"]: False,
        names["periodChoice"]: names["monthName"],
        names["plotValuesAsChoice"]: names["absolute"],
        names["showValuesAs"]: names["absolute"],
        names["shareOfTotalMarket"]: False,
        names["varianceInPercent"]: False,
        names["showOnly"]: names["showTop"],
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
        names["varianceAnalysisChart"]: not_met,
        names["cumulativeHistogram"]: bool(spec.get("cumulative_histogram", False)),
        names["reversedEcdf"]: bool(spec.get("reversed_ecdf", False)),
        names["showOutliers"]: bool(spec.get("show_outliers", True)),
        names["logXAxis"]: bool(spec.get("log_x_axis", False)),
        names["showTopForEachItem"]: False,
        names["fatherAndChildDimensions"]: False,
        "X": x_axis,
        "Y": y_axis,
        "W": w_axis,
    }
    return chart


def _legacy_param_dict(
    names: dict[str, str],
    *,
    selected_periods: list[str],
    period_totals: dict[str, float],
    columns: list[str],
    date_bounds: tuple[date, date] | None = None,
) -> dict[str, Any]:
    """Return the minimum legacy parameter dictionary distribution plots need."""

    not_met = names["notMetConditionValue"]
    period_zero = selected_periods[0] if selected_periods else CURRENT_PERIOD
    period_one = selected_periods[-1] if selected_periods else CURRENT_PERIOD
    period_zero_total = period_totals.get(period_zero, 0.0)
    period_one_total = period_totals.get(period_one, 0.0)
    least_recent_date, most_recent_date = (
        date_bounds if date_bounds is not None else (date.today(), date.today())
    )
    param = {
        names["columnHash"]: {},
        names["mostRecentDate"]: most_recent_date,
        names["leastRecentDate"]: least_recent_date,
        names["periodLengthInMonths"]: 12,
        names["fileUploadDisabled"]: True,
        names["renameTitlesDict"]: {},
        names["isFilteredKey"]: not_met,
        names["numberOfPeriodsFound"]: len(selected_periods) or 1,
        names["impossibleToProcessFile"]: False,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["allPeriodsList"]: selected_periods or [CURRENT_PERIOD],
        names["selectedPeriods"]: selected_periods or [CURRENT_PERIOD],
        names["totalAmountPeriodZero"]: period_zero_total,
        names["totalAmountPeriodOne"]: period_one_total,
        names["totalVarianceValue"]: period_one_total - period_zero_total,
        names["totalAmountPeriodZeroFiltered"]: period_zero_total,
        names["totalAmountPeriodOneFiltered"]: period_one_total,
        names["periodZeroSum"]: period_zero_total,
        names["periodOneSum"]: period_one_total,
        names["datePeriodName"]: names["monthName"],
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
        param[names[flag]] = names[column_key] in columns
    return param


def _coerce_date(value: Any) -> date | None:
    """Return ``value`` as a date when the canonical date column is usable."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _canonical_date_bounds(canonical: pl.DataFrame) -> tuple[date, date] | None:
    """Return min/max canonical dates used by legacy rolling-period titles."""

    if CANONICAL_DATE not in canonical.collect_schema().names():
        return None
    dates = [
        parsed
        for value in canonical.get_column(CANONICAL_DATE).drop_nulls().to_list()
        if (parsed := _coerce_date(value)) is not None
    ]
    if not dates:
        return None
    return min(dates), max(dates)


def _legacy_source_functions(spec: dict[str, Any]) -> list[str]:
    """Return the legacy function path expected for one distribution spec."""

    plotter = str(spec["plotter"])
    draw_by_plotter = {
        "plot_histogram_charts": [
            "modules.charting.draw_distribution.draw_histogram_chart",
            "modules.charting.update_layouts.update_histogram_layout",
        ],
        "plot_boxplot_charts": [
            "modules.charting.draw_distribution.draw_boxplot_chart",
            "modules.charting.update_layouts.update_boxplot_layout",
        ],
        "plot_stripplot_charts": [
            "modules.charting.draw_distribution.draw_stripplot_chart",
            "modules.charting.update_layouts.update_stripplot_layout",
        ],
        "plot_ecdf_charts": [
            "modules.charting.draw_distribution.draw_ecdf_chart",
            "modules.charting.update_layouts.update_ecdf_layout",
        ],
        "plot_kernel_density_charts": [
            "modules.charting.draw_distribution.draw_kernel_density_chart",
            "modules.charting.update_layouts.update_kernel_density_layout",
        ],
    }
    return [
        f"modules.charting.plot_charts.{plotter}",
        "modules.data.common_data_utils.show_only_largest",
        "modules.data.misc_charts_data_prep.aggregate_values_in_distribution_plots",
        "modules.charting.plotting_utilities.check_if_two_periods_in_distribution_chart",
        "modules.charting.make_titles.make_distribution_charts_title",
        *draw_by_plotter[plotter],
        "modules.charting.chart_helpers.set_up_tab_for_show_or_download_chart",
    ]


def _collect_lazyframe(frame: pl.LazyFrame) -> pl.DataFrame:
    try:
        return frame.collect(engine="streaming")
    except (TypeError, ValueError, RuntimeError, pl.exceptions.PolarsError):
        return frame.collect()


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
        return {
            "type": type(frame).__name__,
            "columns": [],
            "row_count": None,
            "rows": [],
            "repr": str(frame)[:1000],
        }
    return {
        "type": type(frame).__name__,
        "columns": collected.collect_schema().names(),
        "row_count": collected.height,
        "rows": _json_safe(collected.to_dicts()),
    }


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return [value]


def _figure_payload(fig: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": type(fig).__name__, "traces": []}
    layout = getattr(fig, "layout", None)
    annotations = list(getattr(layout, "annotations", []) or []) if layout else []
    payload["annotations"] = [
        {
            "text": str(getattr(annotation, "text", "") or ""),
            "x": _json_safe(getattr(annotation, "x", None)),
            "y": _json_safe(getattr(annotation, "y", None)),
        }
        for annotation in annotations
    ]
    for trace in list(getattr(fig, "data", []) or []):
        marker = getattr(trace, "marker", None)
        payload["traces"].append(
            {
                "type": str(getattr(trace, "type", "") or ""),
                "name": str(getattr(trace, "name", "") or ""),
                "x": _json_safe(_sequence(getattr(trace, "x", None))),
                "y": _json_safe(_sequence(getattr(trace, "y", None))),
                "text": _json_safe(_sequence(getattr(trace, "text", None))),
                "marker_color": _json_safe(
                    getattr(marker, "color", None) if marker is not None else None
                ),
            }
        )
    return payload


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


def _write_legacy_figure(fig: Any, path: Path) -> tuple[list[Path], dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    export_fig, normalization_audit = normalize_plotly_figure_for_static_export(fig)
    width = int(getattr(getattr(export_fig, "layout", None), "width", 0) or 1400)
    height = int(getattr(getattr(export_fig, "layout", None), "height", 0) or 900)
    width = max(width, 1400)
    height = max(height, 900)
    export_fig.update_layout(
        width=width,
        height=height,
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            export_fig.write_image(
                str(path), format="png", width=width, height=height, scale=2
            )
        return [path], {
            "artifact": path.name,
            "renderer": "legacy_plotly+kaleido",
            "plotly_export_error": None,
            "html_artifact": None,
            "screenshot_error": None,
            "export_width": width,
            "export_height": height,
            "figure_export_normalization": normalization_audit,
        }
    except (OSError, RuntimeError, ValueError) as exc:
        html_path = _write_plotly_html(export_fig, path, width, height)
        screenshot_error = _screenshot_plotly_html(html_path, path, width, height)
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
            "export_width": width,
            "export_height": height,
            "figure_export_normalization": normalization_audit,
        }


def _select_outputs(outputs: list[Any], policy: str) -> list[Any]:
    if policy == "first" and outputs:
        return outputs[:1]
    if policy == "last" and outputs:
        return outputs[-1:]
    return outputs


def _write_captured_outputs(
    outputs: list[Any],
    output_dir: Path,
    artifact_name: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    paths: list[str] = []
    exports: list[dict[str, Any]] = []
    for index, output in enumerate(outputs, start=1):
        path = output_dir / artifact_name
        if len(outputs) > 1:
            path = path.with_name(f"{path.stem}_{index}{path.suffix}")
        export_figure, capture_normalization_audit = (
            normalize_plotly_figure_for_static_export(output.figure)
        )
        written_paths, export = _write_legacy_figure(export_figure, path)
        export["captured_figure_normalization"] = capture_normalization_audit
        paths.extend(str(written_path) for written_path in written_paths)
        exports.append(export)
    return paths, exports


def _capture_context_payload(
    *,
    spec: dict[str, Any],
    outputs: list[Any],
    exports: list[dict[str, Any]],
    source_functions: list[str],
) -> dict[str, Any] | None:
    if not spec.get("capture_chart_data"):
        return None
    primary_output = outputs[-1] if outputs else None
    return {
        "schema_version": "1.0",
        "chart": spec["name"],
        "legacy_chart": (
            primary_output.chart_dict.get("chosenChart") if primary_output else None
        ),
        "capture_policy": spec.get("capture_figure") or "all",
        "chart_data_source": "legacy set_up_tab_for_show_or_download_chart input dataframe",
        "metric": spec.get("metric"),
        "distribution_dimension": spec.get("distribution_dimension"),
        "small_multiples_dimension": spec.get("small_multiples_dimension"),
        "selected_periods": spec.get("selected_periods") or [],
        "source_functions": source_functions,
        "data_frame": _frame_payload(primary_output.frame) if primary_output else None,
        "captured_calls": [
            {
                "call_index": index,
                "key": _json_safe(output.key),
                "chosen_dimension": _json_safe(output.chosen_dimension),
                "legacy_chart": output.chart_dict.get("chosenChart"),
                "data_frame": _frame_payload(output.frame),
            }
            for index, output in enumerate(outputs, start=1)
        ],
        "plotly_figures": [_figure_payload(output.figure) for output in outputs],
        "exports": exports,
    }


def write_legacy_distribution_chart(
    canonical: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    spec: dict[str, Any],
    prepared_data_cache: LegacyPreparedDataCache | None = None,
    *,
    render: bool = True,
) -> LegacyDistributionChartExport:
    """Run one vendored legacy distribution chart and export captured figures."""

    ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from modules.chart_harness import apply_legacy_filter_title_metadata
        from modules.charting import plot_charts as plot_charts_module
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        cache_start = (
            prepared_data_cache.snapshot() if prepared_data_cache is not None else None
        )

        def cache_audit() -> dict[str, Any]:
            if prepared_data_cache is None or cache_start is None:
                return {"prepared_data_cache": {"enabled": False}}
            return prepared_data_cache.audit_delta(cache_start)

        metric = str(recipe["mappings"]["metric_column"])
        currency = str((recipe.get("options") or {}).get("currency") or "EUR")
        chart = _legacy_chart_dict(names, spec, metric=metric, currency=currency)
        reporting_entity = reporting_entity_label_from_recipe(recipe)
        if reporting_entity:
            chart[names["companyName"]] = reporting_entity
        chart = apply_legacy_filter_title_metadata(chart, names, recipe)
        selected_periods = [str(item) for item in chart[names["selectedPeriods"]]]
        period_totals = {
            str(row[CANONICAL_PERIOD]): float(row[metric] or 0.0)
            for row in canonical.group_by(CANONICAL_PERIOD)
            .agg(pl.col(metric).sum().alias(metric))
            .iter_rows(named=True)
        }
        param = _legacy_param_dict(
            names,
            selected_periods=selected_periods,
            period_totals=period_totals,
            columns=canonical.collect_schema().names(),
            date_bounds=_canonical_date_bounds(canonical),
        )
        value_cols = [metric]
        index_cols = [
            str(item)
            for item in spec.get("index_cols") or []
            if item and str(item) in canonical.collect_schema().names()
        ]
        source_functions = _legacy_source_functions(spec)
        price_name = str(names["priceName"])
        metric_topn_alias = "__distribution_metric_topn"

        def legacy_topn_value_cols(
            df_copy: pl.DataFrame | pl.LazyFrame,
            requested_value_cols: list[str],
        ) -> tuple[pl.DataFrame | pl.LazyFrame, list[str], str | None]:
            if requested_value_cols and all(
                price_name in column for column in requested_value_cols
            ):
                return (
                    df_copy.with_columns(pl.col(metric).alias(metric_topn_alias)),
                    [metric_topn_alias],
                    metric_topn_alias,
                )
            return df_copy, requested_value_cols, None

        def restore_metric_column(
            frame: pl.DataFrame | pl.LazyFrame,
            alias: str | None,
        ) -> pl.DataFrame | pl.LazyFrame:
            if alias is None:
                return frame
            columns = frame.collect_schema().names()
            if alias in columns and metric not in columns:
                return frame.with_columns(pl.col(alias).alias(metric))
            return frame

        def restore_small_multiple_observations(
            source_frame: pl.DataFrame | pl.LazyFrame,
            ranked_frame: pl.DataFrame | pl.LazyFrame,
            *,
            column: str,
            unique_items: list[Any],
            aggregate_other: Any,
        ) -> pl.DataFrame | pl.LazyFrame:
            if not spec.get("small_multiples_dimension") or column != spec.get(
                "small_multiples_dimension"
            ):
                return ranked_frame
            source_columns = source_frame.collect_schema().names()
            if column not in source_columns:
                return ranked_frame
            top_items = [item for item in unique_items if item != aggregate_other]
            if aggregate_other in unique_items and top_items:
                return source_frame.with_columns(
                    pl.when(pl.col(column).is_in(top_items))
                    .then(pl.col(column))
                    .otherwise(pl.lit(aggregate_other))
                    .alias(column)
                )
            if top_items:
                return source_frame.filter(pl.col(column).is_in(top_items))
            return source_frame

        with _capture_legacy_ui() as notifier:
            original_setup = plot_charts_module.set_up_tab_for_show_or_download_chart
            original_aggregate = (
                plot_charts_module.aggregate_values_in_distribution_plots
            )
            original_show_only_largest = plot_charts_module.show_only_largest
            had_st = hasattr(plot_charts_module, "st")
            original_st = getattr(plot_charts_module, "st", None)

            def cached_aggregate(
                df_copy: pl.DataFrame | pl.LazyFrame,
                element: str,
                aggregate_value_cols: list[str],
                chart_dict: dict[str, Any],
            ) -> pl.LazyFrame:
                if prepared_data_cache is None:
                    return original_aggregate(
                        df_copy, element, aggregate_value_cols, chart_dict
                    )
                return prepared_data_cache.get_distribution_aggregate(
                    names,
                    original_aggregate,
                    df_copy,
                    element,
                    aggregate_value_cols,
                    chart_dict,
                )

            def cached_show_only_largest(
                df_copy: pl.DataFrame | pl.LazyFrame,
                column: str,
                second_column: str | None,
                time_column: str,
                top_value_cols: list[str],
                chart_dict: dict[str, Any],
                param_dict: dict[str, Any],
                key: str,
            ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
                selected_value_cols = top_value_cols or [metric]
                prepared_df, prepared_value_cols, alias = legacy_topn_value_cols(
                    df_copy,
                    selected_value_cols,
                )

                def call_original_show_only_largest(
                    original_df_copy: pl.DataFrame | pl.LazyFrame,
                    original_column: str,
                    original_second_column: str | None,
                    original_time_column: str,
                    original_value_cols: list[str],
                    original_chart_dict: dict[str, Any],
                    original_param_dict: dict[str, Any],
                    original_key: str,
                ) -> tuple[pl.LazyFrame, list[Any], Any, list[str]]:
                    (
                        frame,
                        unique_items,
                        aggregate_other,
                        _prepared_value_cols,
                    ) = original_show_only_largest(
                        original_df_copy,
                        original_column,
                        original_second_column,
                        original_time_column,
                        original_value_cols,
                        original_chart_dict,
                        original_param_dict,
                        original_key,
                    )
                    frame = restore_small_multiple_observations(
                        original_df_copy,
                        frame,
                        column=original_column,
                        unique_items=unique_items,
                        aggregate_other=aggregate_other,
                    )
                    return (
                        restore_metric_column(frame, alias),
                        unique_items,
                        aggregate_other,
                        selected_value_cols,
                    )

                if prepared_data_cache is None:
                    return call_original_show_only_largest(
                        prepared_df,
                        column,
                        second_column,
                        time_column,
                        prepared_value_cols,
                        chart_dict,
                        param_dict,
                        key,
                    )
                return prepared_data_cache.get_show_only_largest(
                    names,
                    call_original_show_only_largest,
                    prepared_df,
                    column,
                    second_column,
                    time_column,
                    prepared_value_cols,
                    chart_dict,
                    param_dict,
                    key,
                )

            plot_charts_module.aggregate_values_in_distribution_plots = cached_aggregate
            plot_charts_module.show_only_largest = cached_show_only_largest
            plot_charts_module.st = notifier
            try:
                plotter = getattr(plot_charts_module, str(spec["plotter"]))
                plotter(canonical, index_cols, value_cols, chart, None, param)
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
                return LegacyDistributionChartExport(
                    paths=[],
                    audit={
                        "status": "failed_legacy",
                        "chart": spec["name"],
                        "legacy_chart": chart[names["chosenChart"]],
                        "legacy_reference_function": (
                            f"modules.charting.plot_charts.{spec['plotter']}"
                        ),
                        "legacy_reference_function_call_mode": "executed_headless",
                        "metric": metric,
                        "distribution_dimension": spec.get("distribution_dimension"),
                        "small_multiples_dimension": spec.get(
                            "small_multiples_dimension"
                        ),
                        **cache_audit(),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "events": notifier.events,
                        "source_functions": source_functions,
                    },
                )
            finally:
                plot_charts_module.set_up_tab_for_show_or_download_chart = (
                    original_setup
                )
                plot_charts_module.aggregate_values_in_distribution_plots = (
                    original_aggregate
                )
                plot_charts_module.show_only_largest = original_show_only_largest
                if had_st:
                    plot_charts_module.st = original_st
                else:
                    delattr(plot_charts_module, "st")

        error_events = [
            event
            for event in notifier.events
            if event.get("level") == "error" or event.get("method") == "error"
        ]
        if error_events:
            return LegacyDistributionChartExport(
                paths=[],
                audit={
                    "status": "failed_legacy_caught",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "legacy_reference_function": (
                        f"modules.charting.plot_charts.{spec['plotter']}"
                    ),
                    "legacy_reference_function_call_mode": "executed_headless",
                    "metric": metric,
                    "distribution_dimension": spec.get("distribution_dimension"),
                    "small_multiples_dimension": spec.get("small_multiples_dimension"),
                    **cache_audit(),
                    "error_events": error_events,
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )

        outputs = _select_outputs(
            list(notifier.chart_outputs), str(spec.get("capture_figure") or "all")
        )
        paths: list[str] = []
        exports: list[dict[str, Any]] = []
        if render:
            paths, exports = _write_captured_outputs(
                outputs,
                output_dir,
                str(spec["artifact_name"]),
            )
        if render and not paths:
            return LegacyDistributionChartExport(
                paths=[],
                audit={
                    "status": "not_written_legacy_no_figure",
                    "chart": spec["name"],
                    "legacy_chart": chart[names["chosenChart"]],
                    "legacy_reference_function": (
                        f"modules.charting.plot_charts.{spec['plotter']}"
                    ),
                    "legacy_reference_function_call_mode": "executed_headless",
                    "metric": metric,
                    "distribution_dimension": spec.get("distribution_dimension"),
                    "small_multiples_dimension": spec.get("small_multiples_dimension"),
                    **cache_audit(),
                    "error_events": [],
                    "events": notifier.events,
                    "source_functions": source_functions,
                },
            )
        context = _capture_context_payload(
            spec=spec,
            outputs=outputs,
            exports=exports,
            source_functions=source_functions,
        )
        return LegacyDistributionChartExport(
            paths=paths,
            audit={
                "status": "written_legacy" if render else "data_written",
                "chart": spec["name"],
                "legacy_chart": chart[names["chosenChart"]],
                "legacy_reference_function": (
                    f"modules.charting.plot_charts.{spec['plotter']}"
                ),
                "legacy_reference_function_call_mode": "executed_headless",
                "legacy_draw_function": next(
                    item
                    for item in source_functions
                    if item.startswith("modules.charting.draw_distribution.")
                ),
                "metric": metric,
                "distribution_dimension": spec.get("distribution_dimension"),
                "small_multiples_dimension": spec.get("small_multiples_dimension"),
                "selected_periods": selected_periods,
                "artifact_paths": paths,
                "exported_figures": len(exports),
                "captures": len(outputs),
                "rendered": render,
                **cache_audit(),
                "exports": exports,
                "events": notifier.events,
                "source_functions": source_functions,
            },
            chart_context=context,
        )
