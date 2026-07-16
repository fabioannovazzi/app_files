"""Root-cause bridge chart rendering from legacy variable-dimension output."""

from __future__ import annotations

import copy
import importlib
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from ibcs_titles import build_ibcs_title, ibcs_title_html, measure_line_segments
from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "RootCauseBridgeChartExport",
    "build_root_cause_bridge_chart_rows",
    "write_root_cause_bridge_png",
]

TOLERANCE = 0.000001
MAX_DRIVER_ROWS = 8
METRIC_COLUMNS = {
    "bridge_level",
    "bridge_dimensions",
    "variance_type",
    "variance_amount",
    "amount_baseline",
    "amount_comparison",
    "units_baseline",
    "units_comparison",
    "bridge_unique_value_weight",
}
COLORS = {
    "actual": "#1F1F1F",
    "baseline_period": "#A6A6A6",
    "connector": "#C8C8C8",
    "grid": "#EDEDED",
    "negative": "#FF2F2F",
    "positive": "#67C40F",
    "text": "#1F2328",
    "muted": "#666666",
    "white": "#FFFFFF",
}

LEGACY_ROOT_CAUSE_RENDERER = (
    "modules.charting.plot_charts.plot_root_cause_variable_waterfall"
)
LEGACY_ROOT_CAUSE_SOURCE_FUNCTIONS = [
    "modules.variance.variance_decomposition.process_node_combinations",
    LEGACY_ROOT_CAUSE_RENDERER,
    "modules.data.waterfall_data_prep.prepare_data_for_waterfall",
    "modules.charting.legacy_draw_waterfall.draw_vertical_waterfall_chart",
    "modules.charting.chart_helpers.set_up_tab_for_show_or_download_chart",
    "modules.utilities.ui_notifier.HeadlessChartCapture",
]


@dataclass(frozen=True)
class RootCauseBridgeChartExport:
    """Root-cause bridge chart export paths and audit metadata."""

    paths: list[str]
    audit: dict[str, Any]


def _sum_column(df: pl.DataFrame, column: str) -> float:
    """Return the numeric sum for ``column`` or zero when missing."""

    if column not in df.schema or df.is_empty():
        return 0.0
    value = df.select(pl.col(column).sum()).item()
    return float(value or 0.0)


def _periods(recipe: dict[str, Any]) -> tuple[str, str]:
    """Return baseline and comparison labels from the recipe."""

    mappings = recipe["mappings"]
    return str(mappings["baseline_period"]), str(mappings["comparison_period"])


def _is_plan_label(label: str) -> bool:
    """Return whether ``label`` represents a plan-like scenario."""

    normalized = label.strip().upper()
    return normalized in {"PL", "PLAN", "BUDGET", "BDG", "FORECAST", "FC"}


def _is_period_comparison(recipe: dict[str, Any]) -> bool:
    """Return whether the recipe compares periods rather than scenarios."""

    options = recipe.get("options") or {}
    return options.get("comparison_basis") == "period"


def _format_number(value: float, *, signed: bool = True) -> str:
    """Return compact chart text with K/M/B suffixes."""

    if not math.isfinite(value):
        return ""
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        text = f"{abs_value / 1_000_000_000:,.1f}B"
    elif abs_value >= 1_000_000:
        text = f"{abs_value / 1_000_000:,.1f}M"
    elif abs_value >= 1_000:
        text = f"{abs_value / 1_000:,.1f}K"
    else:
        text = f"{abs_value:,.0f}"
    return f"{sign}{text}"


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Return a finite float for chart calculations."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _driver_percent_delta(value: float, amount_baseline: float) -> float | None:
    """Return row-level percent change for a root-cause driver."""

    if abs(amount_baseline) <= TOLERANCE:
        return None
    percent = (value / amount_baseline) * 100
    return percent if math.isfinite(percent) else None


def _format_percent_marker(value: float | None) -> str:
    """Return compact percent text for the legacy delta side panel."""

    if value is None or not math.isfinite(value):
        return ""
    abs_value = abs(value)
    if abs_value >= 10:
        body = f"{abs_value:.0f}"
    else:
        body = f"{abs_value:.1f}"
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{body}"


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Return a readable font while staying robust in headless runs."""

    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_segmented_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    segments: tuple[tuple[str, bool], ...],
    *,
    fill: str,
    regular_font: ImageFont.ImageFont,
    bold_font: ImageFont.ImageFont,
) -> None:
    """Draw one title line with per-segment emphasis."""

    x, y = xy
    for text, emphasized in segments:
        if not text:
            continue
        font = bold_font if emphasized else regular_font
        draw.text((x, y), text, fill=fill, font=font)
        bbox = draw.textbbox((x, y), text, font=font)
        x += bbox[2] - bbox[0]


def _active_dimensions(bridge_dimensions: str) -> list[str]:
    """Return active dimension names from a legacy bridge-dimension string."""

    if not bridge_dimensions or bridge_dimensions == "total":
        return []
    return [item.strip() for item in bridge_dimensions.split(",") if item.strip()]


def _dimension_columns(bridge: pl.DataFrame) -> list[str]:
    """Return dimension columns emitted by the legacy bridge output."""

    return [column for column in bridge.columns if column not in METRIC_COLUMNS]


def _active_filter(
    row: dict[str, Any], dimensions: list[str]
) -> tuple[tuple[str, str], ...]:
    """Return active dimension-value filters for a legacy bridge row."""

    return tuple(
        (dimension, str(row[dimension]))
        for dimension in dimensions
        if row.get(dimension) not in (None, "All")
    )


def _filter_label(filters: tuple[tuple[str, str], ...]) -> str:
    """Return a compact chart label for active filters."""

    return " / ".join(value for _dimension, value in filters) or "Total"


def _sequence_label(
    row: dict[str, Any],
    filters: tuple[tuple[str, str], ...],
    *,
    include_variance_type: bool,
) -> str:
    """Return the chart label for one legacy sequence row."""

    label = _filter_label(filters)
    variance_type = str(row.get("variance_type") or "").strip()
    if (
        include_variance_type
        and variance_type
        and variance_type.lower() not in {"total", "none"}
    ):
        return f"{label} - {variance_type}"
    return label


def _legacy_sequence_driver_rows(
    bridge: pl.DataFrame,
    total_delta: float,
    max_drivers: int = MAX_DRIVER_ROWS,
    *,
    include_variance_type: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return driver rows directly from ``process_node_combinations`` output."""

    dimensions = _dimension_columns(bridge)
    all_selected_rows: list[dict[str, Any]] = []
    for row in bridge.to_dicts():
        value = _safe_float(row.get("variance_amount"))
        if abs(value) <= TOLERANCE:
            continue
        filters = _active_filter(row, dimensions)
        bridge_dimensions = _active_dimensions(str(row.get("bridge_dimensions") or ""))
        amount_baseline = _safe_float(row.get("amount_baseline"))
        amount_comparison = _safe_float(row.get("amount_comparison"))
        row_number = len(all_selected_rows) + 1
        all_selected_rows.append(
            {
                "label": _sequence_label(
                    row,
                    filters,
                    include_variance_type=include_variance_type,
                ),
                "kind": "driver",
                "value": value,
                "source_value": value,
                "row_number": row_number,
                "amount_baseline": amount_baseline,
                "amount_comparison": amount_comparison,
                "percent_delta": _driver_percent_delta(value, amount_baseline),
                "filters": filters,
                "bridge_dimensions": bridge_dimensions,
                "bridge_level": int(row.get("bridge_level") or len(filters)),
                "variance_types": [str(row.get("variance_type") or "")],
            }
        )

    if not all_selected_rows:
        raise ValueError("Legacy process_node_combinations returned no chart rows.")

    requested_driver_count = len(all_selected_rows)
    display_limit = max(0, int(max_drivers))
    selected_rows = all_selected_rows[:display_limit]
    selected_sum = sum(float(row["value"]) for row in selected_rows)
    residual = total_delta - selected_sum
    if abs(residual) > TOLERANCE:
        selected_rows.append(
            {
                "label": "Other",
                "kind": "driver",
                "value": residual,
                "source_value": residual,
                "row_number": None,
                "amount_baseline": 0.0,
                "amount_comparison": residual,
                "percent_delta": None,
                "filters": tuple(),
                "bridge_dimensions": ["residual"],
                "bridge_level": 0,
                "variance_types": ["Residual"],
            }
        )

    active_dimension_labels = [
        ",".join(row["bridge_dimensions"])
        for row in selected_rows
        if row["label"] != "Other"
    ]
    unique_active_dimension_labels = list(dict.fromkeys(active_dimension_labels))
    audit = {
        "candidate_count": bridge.height,
        "selected_driver_count": requested_driver_count,
        "displayed_legacy_driver_count": len(
            [row for row in selected_rows if row["label"] != "Other"]
        ),
        "selected_driver_filters": [
            " / ".join(f"{dimension}={value}" for dimension, value in row["filters"])
            for row in selected_rows
            if row["label"] != "Other"
        ],
        "selected_driver_bridge_dimensions": [
            [",".join(row["bridge_dimensions"])]
            for row in selected_rows
            if row["label"] != "Other"
        ],
        "selected_driver_active_dimensions": [
            row["bridge_dimensions"] for row in selected_rows if row["label"] != "Other"
        ],
        "selected_bridge_levels": [
            row["bridge_level"] for row in selected_rows if row["label"] != "Other"
        ],
        "selected_sequence_unique_bridge_dimensions": unique_active_dimension_labels,
        "selected_sequence_has_mixed_dimensions": len(unique_active_dimension_labels)
        > 1,
        "other_included": any(row["label"] == "Other" for row in selected_rows),
        "selection_strategy": "legacy_process_node_combinations",
        "selection_truncated": requested_driver_count > display_limit,
    }
    return selected_rows, audit


def build_root_cause_bridge_chart_rows(
    bridge: pl.DataFrame,
    result: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    max_drivers: int = MAX_DRIVER_ROWS,
    include_variance_type: bool = True,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Build a readable bridge table from legacy root-cause output.

    The legacy runtime owns the variable-dimension decomposition. This function
    renders the ordered rows returned by ``process_node_combinations`` and only
    adds ``Other`` for the mathematical residual.
    """

    baseline_label, comparison_label = _periods(recipe)
    baseline_total = _sum_column(result, "amount_baseline")
    comparison_total = _sum_column(result, "amount_comparison")
    total_delta = comparison_total - baseline_total
    driver_rows, selection_audit = _legacy_sequence_driver_rows(
        bridge,
        total_delta,
        max_drivers=max_drivers,
        include_variance_type=include_variance_type,
    )
    rows = [
        {
            "label": baseline_label,
            "kind": "baseline",
            "value": baseline_total,
            "row_number": None,
            "amount_baseline": baseline_total,
            "amount_comparison": None,
            "percent_delta": None,
            "percent_label": "",
        },
        *[
            {
                "label": str(row["label"]),
                "kind": "driver",
                "value": float(row["value"]),
                "row_number": row.get("row_number"),
                "amount_baseline": float(row.get("amount_baseline") or 0.0),
                "amount_comparison": float(row.get("amount_comparison") or 0.0),
                "percent_delta": row.get("percent_delta"),
                "percent_label": _format_percent_marker(row.get("percent_delta")),
            }
            for row in driver_rows
        ],
        {
            "label": comparison_label,
            "kind": "comparison",
            "value": comparison_total,
            "row_number": None,
            "amount_baseline": None,
            "amount_comparison": comparison_total,
            "percent_delta": _driver_percent_delta(total_delta, baseline_total),
            "percent_label": _format_percent_marker(
                _driver_percent_delta(total_delta, baseline_total)
            ),
        },
    ]
    frame = pl.DataFrame(rows)
    audit = {
        "displayed_driver_count": len(driver_rows),
        "max_driver_count": max_drivers,
        "total_delta": total_delta,
        "displayed_driver_sum": sum(float(row["value"]) for row in driver_rows),
        "selected_bridge_dimensions": "legacy_sequence",
        "selected_bridge_summary": "sequential residual driver sequence",
        **selection_audit,
    }
    audit["chart_reconciliation_delta"] = (
        float(audit["displayed_driver_sum"]) - total_delta
    )
    return frame, audit


def _x_position(value: float, low: float, high: float, left: int, width: int) -> int:
    """Map a value to a horizontal pixel position."""

    if abs(high - low) < TOLERANCE:
        high = low + 1.0
    return int(left + ((value - low) / (high - low)) * width)


def _draw_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    """Draw a rounded bar, using outline only when supplied."""

    draw.rounded_rectangle(box, radius=4, fill=fill, outline=outline, width=width)


def _bar_box_from_zero(
    zero_x: int,
    value_x: int,
    y0: int,
    y1: int,
) -> tuple[int, int, int, int]:
    """Return a horizontal bar box that is valid on either side of zero."""

    x0 = min(zero_x, value_x)
    x1 = max(zero_x, value_x)
    return (x0, y0, max(x1, x0 + 3), y1)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    """Return text truncated to fit a fixed pixel width."""

    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    ellipsis = "..."
    low = 0
    high = len(text)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = f"{text[:mid].rstrip()}{ellipsis}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            low = mid
        else:
            high = mid - 1
    return f"{text[:low].rstrip()}{ellipsis}"


def _chart_kind(audit: dict[str, Any]) -> str:
    """Return the IBCS title kind for the selected bridge sequence."""

    artifact = str(audit.get("artifact") or "")
    variance_mode = str(audit.get("root_cause_variance_mode") or "")
    has_mixed_dimensions = bool(audit.get("selected_sequence_has_mixed_dimensions"))
    if "drilldown" in artifact:
        return "root_cause_drilldown"
    if variance_mode == "component_variance":
        return "root_cause_component"
    if variance_mode == "total_variance":
        return (
            "variable_root_cause_total" if has_mixed_dimensions else "root_cause_total"
        )
    if has_mixed_dimensions:
        return "variable_root_cause"
    return "root_cause"


def _collect_if_lazy(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Return an eager Polars frame."""

    return frame.collect() if isinstance(frame, pl.LazyFrame) else frame


def _legacy_run_name(artifact_name: str, names: dict[str, str]) -> str:
    """Return the legacy report run name matching the chart artifact."""

    if "drilldown" in artifact_name:
        return names["drilldownReportRunName"]
    return names["mainReportRunName"]


def _legacy_chart_audit(
    captured_output: Any,
    capture: Any,
    *,
    renderer: str,
    plotly_export_error: str | None,
) -> dict[str, Any]:
    """Return audit data proving the legacy Plotly path was executed."""

    frame = _collect_if_lazy(captured_output.frame)
    layout_json = captured_output.figure.layout.to_plotly_json()
    trace_types = [
        str(getattr(trace, "type", "unknown")) for trace in captured_output.figure.data
    ]
    percent_trace_count = sum(
        1
        for trace in captured_output.figure.data
        if str(getattr(trace, "xaxis", "")) == "x2"
        or str(getattr(trace, "yaxis", "")) == "y2"
    )
    measure_column = next(
        (column for column in frame.columns if column.lower() == "measure"),
        None,
    )
    measure_values = (
        frame.get_column(measure_column).to_list() if measure_column else []
    )
    audit = {
        "renderer": renderer,
        "legacy_reference_function": LEGACY_ROOT_CAUSE_RENDERER,
        "legacy_reference_function_call_mode": "executed_headless",
        "source_functions": LEGACY_ROOT_CAUSE_SOURCE_FUNCTIONS,
        "captured_chart_output_count": len(capture.chart_outputs),
        "captured_plotly_chart_count": len(capture.plotly_charts),
        "legacy_chart_ready_row_count": frame.height,
        "legacy_chart_ready_columns": frame.columns,
        "legacy_trace_types": trace_types,
        "legacy_percent_side_panel": "xaxis2" in layout_json or percent_trace_count > 0,
        "legacy_initial_final_values": (
            len(measure_values) >= 2
            and str(measure_values[0]) == "absolute"
            and str(measure_values[-1]) == "absolute"
        ),
    }
    if plotly_export_error:
        audit["plotly_export_error"] = plotly_export_error
    return audit


def _legacy_root_cause_canvas(row_count: int) -> tuple[int, int]:
    """Return a readable export canvas for variable root-cause bridges."""

    width = 1280
    height = max(650, 160 + max(row_count, 7) * 72)
    return width, height


def _screenshot_plotly_html(
    html_path: Path,
    output_path: Path,
    *,
    width: int,
    height: int,
) -> str | None:
    """Screenshot a standalone legacy Plotly HTML file when a browser is available."""

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return str(exc)

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    channel="chrome",
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
            except PlaywrightError:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.locator(".plotly-graph-div").first.wait_for(
                state="visible",
                timeout=10_000,
            )
            page.wait_for_timeout(500)
            page.screenshot(path=str(output_path), full_page=True)
            browser.close()
    except (OSError, RuntimeError, ValueError, PlaywrightError) as exc:
        return str(exc)
    return None


def _write_legacy_root_cause_png(
    legacy_frame: pl.DataFrame | pl.LazyFrame,
    recipe: dict[str, Any],
    audit: dict[str, Any],
    output_path: Path,
    *,
    legacy_param: dict[str, Any],
    legacy_chart: dict[str, Any],
    legacy_index_cols: list[str],
    baseline_total: float,
    comparison_total: float,
) -> dict[str, Any]:
    """Render the root-cause bridge through the legacy Plotly waterfall path."""

    from legacy_adapter import _ensure_legacy_import_path

    _ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = importlib.import_module("modules.utilities.config")
        chart_primitives = importlib.import_module("modules.charting.chart_primitives")
        plot_charts = importlib.import_module("modules.charting.plot_charts")
        ui_notifier = importlib.import_module("modules.utilities.ui_notifier")

    names = config.get_naming_params()
    param = copy.deepcopy(legacy_param)
    chart = copy.deepcopy(legacy_chart)
    legacy_source = _collect_if_lazy(legacy_frame)
    available_index_cols = [
        column for column in legacy_index_cols if column in legacy_source.columns
    ]
    if available_index_cols:
        legacy_source = legacy_source.with_columns(
            [
                pl.when(pl.col(column).cast(pl.Utf8) == "All")
                .then(pl.lit(""))
                .otherwise(pl.col(column).cast(pl.Utf8))
                .alias(column)
                for column in available_index_cols
            ]
        )
    chart[names["processingChoice"]] = names["runVariableDimensionalAnalysis"]
    chart[names["varianceAggregation"]] = names["totalVarianceAggregation"]
    chart[names["showInitialAndFinalValues"]] = True
    chart[names["varianceInPercent"]] = False
    chart[names["shareOfTotalMarket"]] = False
    chart[names["plotSmallMultiplesWaterfall"]] = False
    chart[names["mainDimension"]] = list(available_index_cols)
    param[names["columnHash"]] = param.get(names["columnHash"], {})
    param[names["totalAmountPeriodZero"]] = baseline_total
    param[names["totalAmountPeriodOne"]] = comparison_total
    param[names["totalVarianceValue"]] = comparison_total - baseline_total
    param[names["periodZeroSum"]] = baseline_total
    param[names["periodOneSum"]] = comparison_total

    color_dict = chart_primitives.get_color_dictionary(chart)
    capture = ui_notifier.HeadlessChartCapture()
    run = _legacy_run_name(str(audit.get("artifact") or ""), names)
    with ui_notifier.use_ui_notifier(capture):
        plot_charts.plot_root_cause_variable_waterfall(
            legacy_source,
            list(available_index_cols),
            param,
            chart,
            color_dict,
            run,
        )
    captured_output = capture.last_chart_output()
    fig = captured_output.figure
    captured_frame = _collect_if_lazy(captured_output.frame)
    export_width, export_height = _legacy_root_cause_canvas(captured_frame.height)
    ibcs_title = build_ibcs_title(recipe, chart_kind=str(audit["chart_kind"]))
    fig.update_layout(
        width=export_width,
        height=export_height,
        autosize=False,
        title={
            "text": ibcs_title_html(ibcs_title),
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 18},
        },
    )
    margin = dict(fig.layout.margin.to_plotly_json()) if fig.layout.margin else {}
    margin["l"] = max(int(margin.get("l") or 0), 360)
    margin["r"] = max(int(margin.get("r") or 0), 135)
    margin["t"] = max(int(margin.get("t") or 0), 145)
    margin["b"] = max(int(margin.get("b") or 0), 70)
    fig.update_layout(margin=margin)

    renderer = "legacy_plotly+kaleido"
    plotly_export_error: str | None = None
    html_path: Path | None = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fig.write_image(str(output_path), format="png")
    except (OSError, RuntimeError, ValueError) as exc:
        plotly_export_error = str(exc)
        html_path = output_path.with_suffix(".html")
        fig.write_html(str(html_path), include_plotlyjs=True)
        screenshot_error = _screenshot_plotly_html(
            html_path,
            output_path,
            width=export_width,
            height=export_height,
        )
        if screenshot_error is None and output_path.exists():
            renderer = "legacy_plotly+browser_screenshot"
        else:
            renderer = "legacy_plotly+html"
            output_path = html_path

    legacy_audit = _legacy_chart_audit(
        captured_output,
        capture,
        renderer=renderer,
        plotly_export_error=plotly_export_error,
    )
    legacy_audit.update(
        {
            "path": str(output_path),
            "bytes": output_path.stat().st_size,
            "legacy_variance_aggregation": chart[names["varianceAggregation"]],
            "legacy_processing_choice": chart[names["processingChoice"]],
            "legacy_report_run": run,
            "legacy_requested_index_cols": legacy_index_cols,
            "legacy_rendered_index_cols": available_index_cols,
            "export_width": export_width,
            "export_height": export_height,
        }
    )
    if html_path is not None:
        legacy_audit["legacy_plotly_html_path"] = str(html_path)
        legacy_audit["legacy_plotly_html_bytes"] = html_path.stat().st_size
    if renderer == "legacy_plotly+html" and html_path is not None:
        legacy_audit["browser_screenshot_error"] = screenshot_error
    return legacy_audit


def _draw_ibcs_title(
    draw: ImageDraw.ImageDraw,
    recipe: dict[str, Any],
    audit: dict[str, Any],
) -> None:
    """Draw the standard three-row IBCS title."""

    who_font = _font(18)
    title_font = _font(18)
    title_subject_font = _font(18, bold=True)
    subtitle_font = _font(17)
    title_lines = audit.get("chart_title_lines")
    if not isinstance(title_lines, list) or not title_lines:
        title_lines = build_ibcs_title(
            recipe,
            chart_kind=_chart_kind(audit),
        ).lines()
    if title_lines:
        draw.text((58, 26), str(title_lines[0]), fill=COLORS["muted"], font=who_font)
    if len(title_lines) > 1:
        _draw_segmented_text(
            draw,
            (58, 51),
            measure_line_segments(str(title_lines[1])),
            fill=COLORS["text"],
            regular_font=title_font,
            bold_font=title_subject_font,
        )
    if len(title_lines) > 2:
        draw.text(
            (58, 77),
            str(title_lines[2]),
            fill=COLORS["muted"],
            font=subtitle_font,
        )


def _write_total_variance_png(
    rows: pl.DataFrame,
    recipe: dict[str, Any],
    audit: dict[str, Any],
    output_path: Path,
) -> None:
    """Render total root-cause rows as overlaid initial/final value bars."""

    baseline_label, comparison_label = _periods(recipe)
    period_mode = _is_period_comparison(recipe)
    row_count = rows.height
    width = 1280
    row_height = 74
    top = 142
    bottom = 46
    height = max(560, top + row_height * row_count + bottom)
    left = 430
    right = 230
    plot_width = width - left - right
    bar_height = 16
    row_overlay_offset = 7
    label_x = 58
    delta_panel_left = width - right + 42
    delta_panel_width = right - 78
    delta_value_x = delta_panel_left - 88
    label_font = _font(18)
    value_font = _font(16, bold=True)
    small_font = _font(14)
    subtitle_font = _font(17)

    value_candidates: list[float] = []
    for row in rows.to_dicts():
        if row["kind"] in {"baseline", "comparison"}:
            value_candidates.append(float(row["value"]))
        else:
            value_candidates.extend(
                [
                    float(row.get("amount_baseline") or 0.0),
                    float(row.get("amount_comparison") or 0.0),
                ]
            )
    low = min(0.0, *value_candidates)
    high = max(0.0, *value_candidates)
    padding = max((high - low) * 0.04, 1.0)
    low -= padding
    high += padding

    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    _draw_ibcs_title(draw, recipe, audit)

    zero_x = _x_position(0.0, low, high, left, plot_width)
    draw.line(
        (zero_x, top - 18, zero_x, height - bottom + 12),
        fill=COLORS["grid"],
        width=1,
    )
    percent_values = [
        float(row["percent_delta"])
        for row in rows.to_dicts()[1:-1]
        if row.get("percent_delta") is not None
        and math.isfinite(float(row["percent_delta"]))
    ]
    if percent_values:
        pct_low = min(0.0, min(percent_values))
        pct_high = max(0.0, max(percent_values))
        pct_padding = max((pct_high - pct_low) * 0.18, 1.0)
        pct_low -= pct_padding
        pct_high += pct_padding
        pct_zero_x = _x_position(
            0.0,
            pct_low,
            pct_high,
            delta_panel_left,
            delta_panel_width,
        )
        draw.text(
            (delta_panel_left, top - 54),
            "\u0394%",
            fill=COLORS["text"],
            font=subtitle_font,
        )
        draw.line(
            (pct_zero_x, top - 18, pct_zero_x, height - bottom + 12),
            fill=COLORS["grid"],
            width=1,
        )
    else:
        pct_low = pct_high = 0.0
        pct_zero_x = delta_panel_left

    for index, row in enumerate(rows.to_dicts()):
        y = top + index * row_height
        kind = str(row["kind"])
        text_x = label_x
        label = _fit_text(
            draw,
            str(row["label"]),
            label_font,
            max_width=left - text_x - 20,
        )
        draw.text((text_x, y + 10), label, fill=COLORS["text"], font=label_font)

        if kind in {"baseline", "comparison"}:
            value = float(row["value"])
            x1 = _x_position(value, low, high, left, plot_width)
            color = COLORS["actual"] if kind == "comparison" else COLORS["white"]
            outline = COLORS["actual"] if kind == "baseline" else None
            if (
                kind == "baseline"
                and period_mode
                and not _is_plan_label(baseline_label)
            ):
                color = COLORS["baseline_period"]
                outline = None
            _draw_bar(
                draw,
                _bar_box_from_zero(zero_x, x1, y + 8, y + 8 + bar_height),
                fill=color,
                outline=outline,
                width=2 if outline else 1,
            )
            draw.text(
                (x1 + 10, y + 7),
                _format_number(value, signed=False),
                fill=COLORS["text"],
                font=value_font,
            )
            continue

        baseline_value = float(row.get("amount_baseline") or 0.0)
        comparison_value = float(row.get("amount_comparison") or 0.0)
        delta_value = comparison_value - baseline_value
        baseline_x = _x_position(baseline_value, low, high, left, plot_width)
        comparison_x = _x_position(comparison_value, low, high, left, plot_width)
        baseline_top = y + 12
        comparison_top = baseline_top + row_overlay_offset
        _draw_bar(
            draw,
            _bar_box_from_zero(
                zero_x,
                baseline_x,
                baseline_top,
                baseline_top + bar_height,
            ),
            fill=COLORS["baseline_period"],
        )
        _draw_bar(
            draw,
            _bar_box_from_zero(
                zero_x,
                comparison_x,
                comparison_top,
                comparison_top + bar_height,
            ),
            fill=COLORS["actual"],
        )
        baseline_label_y = baseline_top - 12
        comparison_label_y = comparison_top + bar_height - 2
        draw.text(
            (baseline_x + 8, baseline_label_y),
            _format_number(baseline_value, signed=False),
            fill=COLORS["muted"],
            font=small_font,
        )
        draw.text(
            (comparison_x + 8, comparison_label_y),
            _format_number(comparison_value, signed=False),
            fill=COLORS["text"],
            font=small_font,
        )
        delta_label = _format_number(delta_value)
        delta_color = COLORS["positive"] if delta_value >= 0 else COLORS["negative"]
        draw.text(
            (delta_value_x, comparison_top - 5),
            delta_label,
            fill=delta_color,
            font=value_font,
        )
        percent_delta = row.get("percent_delta")
        percent_label = str(row.get("percent_label") or "")
        if (
            percent_label
            and percent_delta is not None
            and math.isfinite(float(percent_delta))
        ):
            center_y = comparison_top + (bar_height // 2)
            pct_x = _x_position(
                float(percent_delta),
                pct_low,
                pct_high,
                delta_panel_left,
                delta_panel_width,
            )
            line_color = (
                COLORS["positive"] if float(percent_delta) >= 0 else COLORS["negative"]
            )
            draw.line(
                (min(pct_zero_x, pct_x), center_y, max(pct_zero_x, pct_x), center_y),
                fill=line_color,
                width=2,
            )
            marker_box = (pct_x - 4, center_y - 4, pct_x + 4, center_y + 4)
            draw.rectangle(marker_box, fill=COLORS["actual"])
            label_box = draw.textbbox((0, 0), percent_label, font=value_font)
            label_width = label_box[2] - label_box[0]
            percent_label_y = comparison_top - 5
            if pct_x >= pct_zero_x:
                draw.text(
                    (pct_x + 8, percent_label_y),
                    percent_label,
                    fill=COLORS["text"],
                    font=value_font,
                )
            else:
                draw.text(
                    (pct_x - label_width - 8, percent_label_y),
                    percent_label,
                    fill=COLORS["text"],
                    font=value_font,
                )

    image.save(output_path)


def _write_png(
    rows: pl.DataFrame,
    recipe: dict[str, Any],
    audit: dict[str, Any],
    output_path: Path,
) -> None:
    """Render a legacy-style root-cause bridge PNG with Pillow."""

    baseline_label, comparison_label = _periods(recipe)
    period_mode = _is_period_comparison(recipe)
    row_count = rows.height
    width = 1280
    row_height = 62
    top = 142
    bottom = 46
    height = max(520, top + row_height * row_count + bottom)
    left = 430
    right = 230
    plot_width = width - left - right
    bar_height = 24
    label_x = 58
    delta_panel_left = width - right + 42
    delta_panel_width = right - 78
    values = rows["value"].to_list()
    baseline_total = float(values[0])
    comparison_total = float(values[-1])
    cumulative = baseline_total
    low = min(0.0, baseline_total, comparison_total)
    high = max(baseline_total, comparison_total)
    for row in rows.to_dicts()[1:-1]:
        next_value = cumulative + float(row["value"])
        low = min(low, cumulative, next_value)
        high = max(high, cumulative, next_value)
        cumulative = next_value
    padding = max((high - low) * 0.04, 1.0)
    low -= padding
    high += padding

    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    subtitle_font = _font(17)
    label_font = _font(18)
    value_font = _font(16, bold=True)
    small_font = _font(14)
    _draw_ibcs_title(draw, recipe, audit)

    zero_x = _x_position(0.0, low, high, left, plot_width)
    draw.line(
        (zero_x, top - 18, zero_x, height - bottom + 12),
        fill=COLORS["grid"],
        width=1,
    )
    percent_values = [
        float(row["percent_delta"])
        for row in rows.to_dicts()[1:-1]
        if row.get("percent_delta") is not None
        and math.isfinite(float(row["percent_delta"]))
    ]
    if percent_values:
        pct_low = min(0.0, min(percent_values))
        pct_high = max(0.0, max(percent_values))
        pct_padding = max((pct_high - pct_low) * 0.18, 1.0)
        pct_low -= pct_padding
        pct_high += pct_padding
        pct_zero_x = _x_position(
            0.0,
            pct_low,
            pct_high,
            delta_panel_left,
            delta_panel_width,
        )
        draw.text(
            (delta_panel_left, top - 54),
            "\u0394%",
            fill=COLORS["text"],
            font=subtitle_font,
        )
        draw.line(
            (pct_zero_x, top - 18, pct_zero_x, height - bottom + 12),
            fill=COLORS["grid"],
            width=1,
        )
    else:
        pct_low = pct_high = 0.0
        pct_zero_x = delta_panel_left

    cumulative = baseline_total
    previous_x: int | None = None
    previous_y: int | None = None
    for index, row in enumerate(rows.to_dicts()):
        y = top + index * row_height
        center_y = y + bar_height // 2
        kind = str(row["kind"])
        text_x = label_x
        label = _fit_text(
            draw,
            str(row["label"]),
            label_font,
            max_width=left - text_x - 20,
        )
        value = float(row["value"])
        draw.text((text_x, y + 1), label, fill=COLORS["text"], font=label_font)
        if kind in {"baseline", "comparison"}:
            x0 = _x_position(0.0, low, high, left, plot_width)
            x1 = _x_position(value, low, high, left, plot_width)
            if kind == "baseline":
                if period_mode and not _is_plan_label(baseline_label):
                    _draw_bar(
                        draw,
                        (x0, y, x1, y + bar_height),
                        fill=COLORS["baseline_period"],
                    )
                else:
                    _draw_bar(
                        draw,
                        (x0, y, x1, y + bar_height),
                        fill=COLORS["white"],
                        outline=COLORS["actual"],
                        width=2,
                    )
            else:
                _draw_bar(draw, (x0, y, x1, y + bar_height), fill=COLORS["actual"])
            draw.text(
                (x1 + 10, y + 1),
                _format_number(value, signed=False),
                fill=COLORS["text"],
                font=value_font,
            )
            previous_x = x1
            previous_y = center_y
            if kind == "baseline":
                cumulative = value
            continue

        start = cumulative
        end = cumulative + value
        x0 = _x_position(min(start, end), low, high, left, plot_width)
        x1 = _x_position(max(start, end), low, high, left, plot_width)
        connector_target = x0 if value >= 0 else x1
        if previous_x is not None and previous_y is not None:
            draw.line(
                (previous_x, previous_y, previous_x, center_y),
                fill=COLORS["connector"],
                width=1,
            )
            draw.line(
                (previous_x, center_y, connector_target, center_y),
                fill=COLORS["connector"],
                width=1,
            )
        color = COLORS["positive"] if value >= 0 else COLORS["negative"]
        _draw_bar(draw, (x0, y, max(x1, x0 + 3), y + bar_height), fill=color)
        text = _format_number(value)
        if value >= 0:
            draw.text((x1 + 10, y + 1), text, fill=COLORS["text"], font=value_font)
            previous_x = x1
        else:
            text_box = draw.textbbox((0, 0), text, font=value_font)
            draw.text(
                (x0 - (text_box[2] - text_box[0]) - 10, y + 1),
                text,
                fill=COLORS["text"],
                font=value_font,
            )
            previous_x = x0
        previous_y = center_y
        percent_delta = row.get("percent_delta")
        percent_label = str(row.get("percent_label") or "")
        if (
            percent_label
            and percent_delta is not None
            and math.isfinite(float(percent_delta))
        ):
            pct_x = _x_position(
                float(percent_delta),
                pct_low,
                pct_high,
                delta_panel_left,
                delta_panel_width,
            )
            line_color = (
                COLORS["positive"] if float(percent_delta) >= 0 else COLORS["negative"]
            )
            draw.line(
                (min(pct_zero_x, pct_x), center_y, max(pct_zero_x, pct_x), center_y),
                fill=line_color,
                width=2,
            )
            marker_box = (pct_x - 4, center_y - 4, pct_x + 4, center_y + 4)
            draw.rectangle(marker_box, fill=COLORS["actual"])
            label_box = draw.textbbox((0, 0), percent_label, font=value_font)
            label_width = label_box[2] - label_box[0]
            if pct_x >= pct_zero_x:
                draw.text(
                    (pct_x + 8, y + 1),
                    percent_label,
                    fill=COLORS["text"],
                    font=value_font,
                )
            else:
                draw.text(
                    (pct_x - label_width - 8, y + 1),
                    percent_label,
                    fill=COLORS["text"],
                    font=value_font,
                )
        cumulative = end
    image.save(output_path)


def write_root_cause_bridge_png(
    bridge: pl.DataFrame,
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    artifact_name: str = "root_cause_bridge.png",
    variance_mode: str = "component_variance",
    legacy_frame: pl.DataFrame | pl.LazyFrame | None = None,
    legacy_param: dict[str, Any] | None = None,
    legacy_chart: dict[str, Any] | None = None,
    legacy_index_cols: list[str] | None = None,
    legacy_plotly_renderer: bool = False,
) -> RootCauseBridgeChartExport:
    """Write an IBCS-style PNG from legacy root-cause bridge output."""

    uses_legacy_sequence = legacy_frame is not None
    normalized_variance_mode = (
        "total_variance" if variance_mode == "total_variance" else "component_variance"
    )
    audit: dict[str, Any] = {
        "enabled": True,
        "artifact": artifact_name,
        "format": "png",
        "root_cause_variance_mode": normalized_variance_mode,
        "renderer": (
            "pillow_from_legacy_root_cause_sequence"
            if uses_legacy_sequence
            else "pillow_root_cause_sequence"
        ),
    }
    if uses_legacy_sequence:
        renderer_function = (
            "root_cause_bridge_chart._write_total_variance_png"
            if normalized_variance_mode == "total_variance"
            else "root_cause_bridge_chart._write_png"
        )
        audit.update(
            {
                "legacy_reference_function": (
                    "modules.variance.variance_decomposition."
                    "process_node_combinations"
                ),
                "legacy_reference_function_call_mode": "sequence_already_materialized",
                "source_functions": [
                    (
                        "modules.variance.variance_decomposition."
                        "process_node_combinations"
                    ),
                    f"plugins.variance-analysis.scripts.{renderer_function}",
                ],
            }
        )
    rows, row_audit = build_root_cause_bridge_chart_rows(
        bridge,
        result,
        recipe,
        include_variance_type=normalized_variance_mode == "component_variance",
    )
    audit.update(row_audit)
    chart_kind = _chart_kind(audit)
    ibcs_title = build_ibcs_title(recipe, chart_kind=chart_kind)
    audit["chart_title"] = " / ".join(ibcs_title.lines())
    audit["chart_title_lines"] = ibcs_title.lines()
    audit["chart_kind"] = chart_kind
    chart_path = output_dir / artifact_name
    if (
        legacy_frame is not None
        and legacy_param is not None
        and legacy_chart is not None
        and legacy_index_cols is not None
        and legacy_plotly_renderer
    ):
        audit.update(
            _write_legacy_root_cause_png(
                legacy_frame,
                recipe,
                audit,
                chart_path,
                legacy_param=legacy_param,
                legacy_chart=legacy_chart,
                legacy_index_cols=legacy_index_cols,
                baseline_total=_sum_column(result, "amount_baseline"),
                comparison_total=_sum_column(result, "amount_comparison"),
            )
        )
        path = Path(str(audit["path"]))
        audit.update(
            {
                "status": "written",
                "format": path.suffix.lstrip(".") or "png",
                "bytes": path.stat().st_size,
            }
        )
        return RootCauseBridgeChartExport(paths=[str(path)], audit=audit)

    if normalized_variance_mode == "total_variance":
        _write_total_variance_png(rows, recipe, audit, chart_path)
        renderer_version = "root_cause_total_initial_final_overlay_v2"
    else:
        _write_png(rows, recipe, audit, chart_path)
        renderer_version = "root_cause_component_contribution_v1"
    audit.update(
        {
            "status": "written",
            "path": str(chart_path),
            "bytes": chart_path.stat().st_size,
            "pillow_renderer_version": renderer_version,
            "row_number_markers": False,
            "delta_percent_side_panel": True,
            "delta_percent_basis": "driver_variance_amount_over_driver_baseline",
            "initial_final_value_bars": normalized_variance_mode == "total_variance",
        }
    )
    return RootCauseBridgeChartExport(paths=[str(chart_path)], audit=audit)
