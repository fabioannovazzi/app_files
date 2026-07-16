"""Headless legacy-style Plotly waterfall rendering for variance outputs.

This module intentionally keeps the plotting surface small: it ports the legacy
vertical waterfall chart style into a non-UI renderer that can be packaged with
the Codex plugin.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go
import polars as pl
from PIL import Image, ImageDraw, ImageFont
from plotly.subplots import make_subplots

__all__ = [
    "LegacyWaterfallFigure",
    "draw_pvm_decomposition_ladder",
    "draw_vertical_waterfall_chart",
    "make_vertical_waterfall_chart_title",
    "write_waterfall_fallback_png",
]

LEGACY_SOURCE_FUNCTIONS = (
    "modules.charting.draw_waterfall.draw_vertical_waterfall_chart",
    "modules.charting.make_titles.make_vertical_waterfall_chart_title",
    "modules.charting.update_layouts.update_waterfall_layout_one_dimension",
    "modules.charting.update_layouts.update_waterfall_layout_small_multiples",
)
MAX_SMALL_MULTIPLES = 12
TOLERANCE = 0.000001
COLORS = {
    "red": "#FF0000",
    "green": "#7ACA00",
    "grey": "#A6A6A6",
    "light_grey": "#D9D9D9",
    "black": "#343434",
    "white": "#FFFFFF",
}
ORDER_PREFIX_SEPARATOR = "||"
PLAN_TOTAL_LABELS = {"PL", "PLAN", "BUDGET", "BDG", "FORECAST", "FC"}
ACTUAL_TOTAL_LABELS = {"AC", "ACTUAL", "ACT"}


@dataclass(frozen=True)
class LegacyWaterfallFigure:
    """Plotly figure plus audit metadata for a rendered waterfall."""

    figure: go.Figure
    audit: dict[str, Any]


def _sum_column(df: pl.DataFrame, column: str) -> float:
    """Return the numeric sum for ``column`` or zero when missing."""

    if column not in df.schema or df.is_empty():
        return 0.0
    value = df.select(pl.col(column).sum()).item()
    return float(value or 0.0)


def _format_number(value: float) -> str:
    """Return compact chart text with legacy-style signs."""

    if not math.isfinite(value):
        return ""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        text = f"{value / 1_000_000_000:,.1f}B"
    elif abs_value >= 1_000_000:
        text = f"{value / 1_000_000:,.1f}M"
    elif abs_value >= 1_000:
        text = f"{value / 1_000:,.1f}K"
    else:
        text = f"{value:,.0f}"
    if value > 0 and not text.startswith("+"):
        return f"+{text}"
    return text


def _periods(recipe: dict[str, Any]) -> tuple[str, str]:
    """Return baseline and comparison labels from the recipe."""

    mappings = recipe["mappings"]
    return str(mappings["baseline_period"]), str(mappings["comparison_period"])


def _normalized_total_label(label: str) -> str:
    """Normalize a total label for semantic IBCS-style total bar coloring."""

    text = _strip_order_prefix(_clean_html(str(label))).strip()
    for suffix in (" total", " Total", " TOTAL"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.strip().upper()


def _ordered_axis_label(index: int, label: str) -> str:
    """Return a category label prefixed for stable Plotly waterfall ordering."""

    return f"{index:02d}{ORDER_PREFIX_SEPARATOR}{label}"


def _strip_order_prefix(label: str) -> str:
    """Remove an internal category-order prefix from a display label."""

    text = str(label)
    if ORDER_PREFIX_SEPARATOR in text:
        prefix, value = text.split(ORDER_PREFIX_SEPARATOR, 1)
        if prefix.isdigit():
            return value
    return text


def _is_plan_total_label(label: str) -> bool:
    """Return whether a total label is plan, budget, or forecast."""

    return _normalized_total_label(label) in PLAN_TOTAL_LABELS


def _is_actual_total_label(label: str) -> bool:
    """Return whether a total label is actual."""

    return _normalized_total_label(label) in ACTUAL_TOTAL_LABELS


def _fallback_total_bar_style(label: str, measure: str) -> dict[str, Any]:
    """Return fallback PNG fill/outline colors for IBCS-style total bars."""

    if measure == "total" or _is_actual_total_label(label):
        return {"fill": COLORS["black"], "outline": COLORS["black"], "width": 1}
    if measure == "absolute" and _is_plan_total_label(label):
        return {"fill": COLORS["white"], "outline": COLORS["black"], "width": 2}
    return {"fill": COLORS["grey"], "outline": COLORS["grey"], "width": 1}


def _component_rows(df: pl.DataFrame) -> list[tuple[str, float]]:
    """Return variance components in the legacy chart order."""

    components = [
        ("Price", _sum_column(df, "price_variance")),
        ("Volume", _sum_column(df, "volume_variance")),
        ("Mix", _sum_column(df, "mix_variance")),
    ]
    visible = [(label, value) for label, value in components if abs(value) > TOLERANCE]
    total_delta = _sum_column(df, "total_delta")
    residual = total_delta - sum(value for _label, value in visible)
    if abs(residual) > TOLERANCE:
        visible.append(("Other", residual))
    if not visible:
        visible.append(("Variance", total_delta))
    return visible


def _aggregate_component_frame(df: pl.DataFrame) -> pl.DataFrame:
    """Return one result row containing summed standard-variance components."""

    numeric_columns = [
        "amount_baseline",
        "amount_comparison",
        "amount_delta",
        "total_delta",
        "amount_pct_change",
        "price_baseline",
        "price_comparison",
        "price_variance",
        "volume_variance",
        "mix_variance",
        "component_reconciliation_delta",
        "units_baseline",
        "units_comparison",
        "units_delta",
        "calculated_price_baseline",
        "calculated_price_comparison",
        "net_baseline",
        "net_comparison",
        "net_delta",
        "discount_baseline",
        "discount_comparison",
        "discount_delta",
        "cogs_baseline",
        "cogs_comparison",
        "cogs_delta",
        "margin_baseline",
        "margin_comparison",
        "margin_delta",
        "margin_price_variance",
        "margin_volume_variance",
        "margin_mix_variance",
        "margin_component_reconciliation_delta",
    ]
    row = {
        column: _sum_column(df, column)
        for column in numeric_columns
        if column in df.schema
    }
    return pl.DataFrame([row])


def _component_only_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the recipe with no row dimensions for component bridges."""

    component_recipe = dict(recipe)
    mappings = dict(recipe.get("mappings") or {})
    mappings["dimensions"] = []
    component_recipe["mappings"] = mappings
    return component_recipe


def _pvm_ladder_aggregations(
    names: dict[str, str], recipe: dict[str, Any]
) -> list[str]:
    """Return legacy aggregation names for the decomposition ladder."""

    if recipe["mappings"].get("units_column"):
        return [
            names["totalVarianceAggregation"],
            names["priceAndUnitsAggregation"],
            names["mixAndUnitsAggregation"],
        ]
    return [
        names["totalVarianceAggregation"],
        names["priceAndVolumeAggregation"],
        names["mixAndVolumeAggregation"],
    ]


def _pvm_ladder_panel_titles(recipe: dict[str, Any]) -> list[str]:
    """Return business-readable panel titles for the PVM ladder."""

    unit_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
    return [
        "Total variance",
        f"Price + {unit_label} & Mix",
        f"Price + {unit_label} + Mix",
    ]


def _delta_percent_label(
    baseline_total: float,
    comparison_total: float,
    names: dict[str, str],
) -> str:
    """Return the legacy-style total movement percent label."""

    if abs(baseline_total) <= TOLERANCE:
        return ""
    percent_change = ((comparison_total - baseline_total) / baseline_total) * 100
    if not math.isfinite(percent_change):
        return ""
    return f"{names['deltaName']}{int(round(percent_change, 0))}%"


def _pvm_ladder_components(
    aggregation: str,
    df: pl.DataFrame,
    names: dict[str, str],
    recipe: dict[str, Any],
) -> list[tuple[str, float]]:
    """Return the component split for one legacy PVM ladder aggregation."""

    total_delta = _sum_column(df, "total_delta")
    price = _sum_column(df, "price_variance")
    volume = _sum_column(df, "volume_variance")
    mix = _sum_column(df, "mix_variance")
    residual = total_delta - price - volume - mix
    unit_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
    if aggregation == names["totalVarianceAggregation"]:
        return [(f"Price & {unit_label.lower()} & mix", total_delta)]
    if aggregation in {
        names["priceAndUnitsAggregation"],
        names["priceAndVolumeAggregation"],
    }:
        return [
            ("Price", price),
            (f"{unit_label} & mix", total_delta - price),
        ]
    components = [
        ("Price", price),
        (unit_label, volume),
        ("Mix", mix),
    ]
    if abs(residual) > TOLERANCE:
        components.append(("Other", residual))
    return components


def _pvm_ladder_chart_frame(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
    config: dict[str, Any],
    aggregation: str,
    variance_array: list[str],
) -> pl.DataFrame:
    """Build a legacy waterfall frame for one PVM ladder panel."""

    baseline, comparison = _periods(recipe)
    periods = config["periodsArray"]
    separator = names["separatorString"]
    sales_p0 = names["monetaryLocalCurrencyName"] + separator + periods[0]
    sales_p1 = names["monetaryLocalCurrencyName"] + separator + periods[1]
    measure = names["measureName"]
    work_column = names["workColumn"]
    work_column_two = names["workColumnTwo"]
    variance_amount = names["varianceAmountName"]
    variance_type = names["varianceTypeName"]
    label = names["labelName"]
    baseline_total = _sum_column(df, "amount_baseline")
    comparison_total = _sum_column(df, "amount_comparison")
    component_map = {
        component_label: value
        for component_label, value in _pvm_ladder_components(
            aggregation, df, names, recipe
        )
    }
    component_labels = [
        str(item)
        for item in variance_array
        if str(item) not in {baseline, comparison, names["pyName"], names["acName"]}
    ]
    rows: list[dict[str, Any]] = [
        {
            measure: "absolute",
            work_column: baseline,
            work_column_two: baseline_total,
            variance_amount: baseline_total,
            variance_type: "",
            label: _format_number(baseline_total),
            sales_p0: baseline_total,
            sales_p1: comparison_total,
        }
    ]
    for component_label in component_labels:
        value = float(component_map.get(component_label, 0.0) or 0.0)
        rows.append(
            {
                measure: "relative",
                work_column: component_label,
                work_column_two: value,
                variance_amount: value,
                variance_type: component_label,
                label: _format_number(value) if abs(value) > TOLERANCE else "",
                sales_p0: baseline_total,
                sales_p1: comparison_total,
            }
        )
    rows.append(
        {
            measure: "total",
            work_column: comparison,
            work_column_two: comparison_total,
            variance_amount: comparison_total,
            variance_type: "",
            label: _format_number(comparison_total),
            sales_p0: baseline_total,
            sales_p1: comparison_total,
        }
    )
    return pl.DataFrame(rows).with_columns(
        pl.col(variance_amount).cast(pl.Float64, strict=False),
        pl.col(work_column_two).cast(pl.Float64, strict=False),
        pl.col(sales_p0).cast(pl.Float64, strict=False),
        pl.col(sales_p1).cast(pl.Float64, strict=False),
    )


def draw_pvm_decomposition_ladder(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    legacy_frame: pl.DataFrame | None = None,
) -> LegacyWaterfallFigure:
    """Draw the legacy PVM decomposition ladder used for variance explanation."""

    if df.is_empty():
        raise ValueError("Cannot render PVM decomposition ladder for an empty result.")

    from modules.charting import legacy_draw_waterfall
    from modules.charting.adjust_position import move_labels_up
    from modules.charting.chart_helpers import make_one_dimensional_variance_subplots
    from modules.charting.chart_primitives import get_color_dictionary
    from modules.charting.update_layouts import update_waterfall_layout_small_multiples
    from modules.variance.variance_orchestrator import build_variance_calculation_array

    component_recipe = _component_only_recipe(recipe)
    names, config, param, chart = _legacy_context(component_recipe)
    aggregations = _pvm_ladder_aggregations(names, component_recipe)
    chart[names["varianceAggregationOptionsArray"]] = aggregations
    chart[names["varianceAggregation"]] = aggregations[-1]
    chart[names["varianceDifferentCalculations"]] = True
    chart[names["showInitialAndFinalValues"]] = True

    variance_array = build_variance_calculation_array(aggregations, chart)
    panel_titles = _pvm_ladder_panel_titles(component_recipe)
    fig, count_rows, count_cols, _count, number_of_cols, number_of_rows = (
        make_one_dimensional_variance_subplots(panel_titles, numberOfCols=3)
    )
    baseline_total = _sum_column(df, "amount_baseline")
    comparison_total = _sum_column(df, "amount_comparison")
    delta_percent_label = _delta_percent_label(
        baseline_total,
        comparison_total,
        names,
    )
    for key in (
        names["totalAmountPeriodZero"],
        names["totalAmountPeriodZeroFiltered"],
        names["periodZeroSum"],
    ):
        param[key] = baseline_total
    for key in (
        names["totalAmountPeriodOne"],
        names["totalAmountPeriodOneFiltered"],
        names["periodOneSum"],
    ):
        param[key] = comparison_total
    param[names["totalVarianceValue"]] = comparison_total - baseline_total

    color_dict = get_color_dictionary(chart)
    run = names["runOneDimensionalAnalysis"]
    frames: list[pl.DataFrame] = []
    number_format = ""
    for aggregation in aggregations:
        panel_chart = dict(chart)
        panel_chart[names["varianceAggregation"]] = aggregation
        panel_df = _pvm_ladder_chart_frame(
            df,
            component_recipe,
            names,
            config,
            aggregation,
            variance_array,
        )
        frames.append(panel_df)
        fig_det, number_format, _panel_chart = (
            legacy_draw_waterfall.draw_vertical_waterfall_chart(
                panel_df,
                color_dict,
                dict(param),
                panel_chart,
                run,
            )
        )
        if fig_det.data:
            fig_det.data[0].showlegend = False
            fig.add_trace(fig_det.data[0], row=count_rows, col=count_cols)
        if count_cols < number_of_cols:
            count_cols += 1
        else:
            count_cols = 1
            count_rows += 1
    layout_df = pl.concat(frames) if frames else df
    fig, _width = update_waterfall_layout_small_multiples(
        layout_df,
        fig,
        chart,
        number_of_rows,
        number_of_cols,
    )
    traces = list(fig.data)
    if traces:
        global_range = _combined_trace_extent(traces)
        fig.update_xaxes(range=list(global_range), matches="x")
    fig = move_labels_up(fig, chart, panel_titles)
    fig.update_yaxes(autorange="reversed", ticks="")
    if delta_percent_label:
        _baseline_label, comparison_label = _periods(component_recipe)
        for index in range(len(aggregations)):
            fig.add_annotation(
                text=delta_percent_label,
                x=comparison_total,
                y=comparison_label,
                showarrow=False,
                xshift=42,
                yshift=-18,
                font={"size": 11, "color": COLORS["grey"]},
                row=1,
                col=index + 1,
            )
    fig.update_layout(
        title={
            "text": make_vertical_waterfall_chart_title(df, component_recipe),
            "x": 0.01,
            "xanchor": "left",
        },
        meta={"pvm_delta_percent_label": delta_percent_label},
    )
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "legacy_pvm_decomposition_ladder",
            "title": make_vertical_waterfall_chart_title(df, component_recipe),
            "aggregation_count": len(aggregations),
            "aggregations": aggregations,
            "panel_titles": panel_titles,
            "delta_percent_label": delta_percent_label,
            "variance_array": variance_array,
            "row_count": df.height,
            "legacy_source_row_count": (
                legacy_frame.height if legacy_frame is not None else None
            ),
            "legacy_reference_function": (
                "modules.charting.plot_charts."
                "plot_one_dimensional_variance_chart_different_calculations"
            ),
            "source_functions": [
                "modules.variance.variance_orchestrator.build_variance_calculation_array",
                "modules.charting.chart_helpers.make_one_dimensional_variance_subplots",
                "modules.charting.legacy_draw_waterfall.draw_vertical_waterfall_chart",
                "modules.charting.update_layouts.update_waterfall_layout_small_multiples",
                "modules.charting.adjust_position.move_labels_up",
            ],
            "number_format": number_format,
        },
    )


def _waterfall_arrays(
    df: pl.DataFrame, recipe: dict[str, Any]
) -> tuple[list[str], list[str], list[float], list[str]]:
    """Return labels, Plotly measures, values and text for one waterfall."""

    baseline, comparison = _periods(recipe)
    labels = [baseline]
    measures = ["absolute"]
    values = [_sum_column(df, "amount_baseline")]
    for label, value in _component_rows(df):
        labels.append(label)
        measures.append("relative")
        values.append(value)
    labels.append(comparison)
    measures.append("total")
    values.append(_sum_column(df, "amount_comparison"))
    text = [_format_number(value) for value in values]
    return labels, measures, values, text


def _component_columns(recipe: dict[str, Any]) -> list[tuple[str, str]]:
    """Return plugin result columns in legacy display order."""

    volume_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
    return [
        ("Price", "price_variance"),
        (volume_label, "volume_variance"),
        ("Mix", "mix_variance"),
    ]


def make_vertical_waterfall_chart_title(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    dimension: str | None = None,
    dimension_value: str | None = None,
) -> str:
    """Return a legacy-style waterfall title."""

    baseline, comparison = _periods(recipe)
    dimension_text = f" by {dimension}" if dimension else ""
    if dimension and dimension_value:
        dimension_text = f" by {dimension}: {dimension_value}"
    return f"<b>Sales variance</b>{dimension_text}<br>{comparison} vs {baseline}"


def _add_waterfall_trace(
    fig: go.Figure,
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    row: int,
    col: int,
    show_labels: bool = True,
) -> None:
    """Add one horizontal waterfall trace to ``fig``."""

    labels, measures, values, text = _waterfall_arrays(df, recipe)
    fig.add_trace(
        go.Waterfall(
            orientation="h",
            measure=measures,
            y=labels,
            x=values,
            text=text if show_labels else None,
            textinfo="text" if show_labels else "none",
            textposition="outside",
            cliponaxis=False,
            increasing={"marker": {"color": COLORS["green"]}},
            decreasing={"marker": {"color": COLORS["red"]}},
            totals={"marker": {"color": COLORS["black"]}},
            connector={
                "mode": "between",
                "line": {"width": 1, "color": "rgb(169,169,169)", "dash": "solid"},
            },
        ),
        row=row,
        col=col,
    )


def _update_layout(fig: go.Figure, *, title: str, height: int, width: int) -> None:
    """Apply legacy waterfall layout defaults."""

    fig.update_layout(
        template="simple_white",
        title={"text": title, "x": 0.01, "xanchor": "left"},
        width=width,
        height=height,
        margin={"r": 40, "l": 20, "b": 35, "t": 95, "pad": 20},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size": 12, "family": "Arial"},
    )
    fig.update_xaxes(
        automargin=True,
        zeroline=True,
        zerolinecolor="black",
        zerolinewidth=1,
        showticklabels=False,
        ticks="",
    )
    fig.update_yaxes(autorange="reversed", ticks="", showticklabels=True)


def _clean_html(text: Any) -> str:
    """Return readable plain text from simple Plotly HTML labels."""

    cleaned = (
        str(text or "")
        .replace("<b>", "")
        .replace("</b>", "")
        .replace("<br>", " ")
        .replace("<BR>", " ")
    )
    return html.unescape(cleaned)


def _clean_html_lines(text: Any) -> list[str]:
    """Return readable title lines from simple Plotly HTML labels."""

    raw = str(text or "").replace("<b>", "").replace("</b>", "").replace("<BR>", "<br>")
    lines = []
    for line in raw.split("<br>"):
        cleaned = _clean_html(line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _font(size: int) -> ImageFont.ImageFont:
    """Return a readable default font."""

    try:
        return ImageFont.truetype("Arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _trace_extent(trace: Any) -> tuple[float, float]:
    """Return min/max x extent for a waterfall trace."""

    current = 0.0
    low = 0.0
    high = 0.0
    for measure, value in zip(trace.measure, trace.x, strict=False):
        value = float(value or 0.0)
        if measure == "absolute":
            start, end = 0.0, value
            current = value
        elif measure == "total":
            start, end = 0.0, value
            current = value
        else:
            start, end = current, current + value
            current = end
        low = min(low, start, end)
        high = max(high, start, end)
    if abs(high - low) < TOLERANCE:
        high = low + 1.0
    padding = (high - low) * 0.12
    return low - padding, high + padding


def _combined_trace_extent(traces: list[Any]) -> tuple[float, float]:
    """Return one x extent shared by every waterfall trace."""

    extents = [_trace_extent(trace) for trace in traces]
    low = min(extent[0] for extent in extents)
    high = max(extent[1] for extent in extents)
    if abs(high - low) < TOLERANCE:
        high = low + 1.0
    return low, high


def _draw_fallback_trace(
    draw: ImageDraw.ImageDraw,
    trace: Any,
    *,
    top: int,
    left: int,
    right: int,
    title: str,
    extent: tuple[float, float] | None = None,
    delta_percent_label: str = "",
) -> int:
    """Draw one waterfall trace with Pillow and return the next y position."""

    title_font = _font(18)
    body_font = _font(13)
    label_font = _font(12)
    row_height = 34
    bar_height = 20
    labels = [_strip_order_prefix(_clean_html(label)) for label in trace.y]
    measures = list(trace.measure)
    values = [float(value or 0.0) for value in trace.x]
    low, high = extent or _trace_extent(trace)

    def x_pos(value: float) -> int:
        return int(left + ((value - low) / (high - low)) * (right - left))

    if title:
        draw.text((left, top), title, fill=COLORS["black"], font=title_font)
    axis_y = top + 38 + len(labels) * row_height
    zero_x = x_pos(0.0)
    draw.line((zero_x, top + 28, zero_x, axis_y), fill=COLORS["light_grey"], width=1)

    current = 0.0
    for index, (label, measure, value) in enumerate(
        zip(labels, measures, values, strict=False)
    ):
        y_mid = top + 42 + index * row_height
        if measure == "absolute":
            start, end = 0.0, value
            current = value
            style = _fallback_total_bar_style(label, measure)
        elif measure == "total":
            start, end = 0.0, value
            current = value
            style = _fallback_total_bar_style(label, measure)
        else:
            start, end = current, current + value
            current = end
            style = {
                "fill": COLORS["green"] if value >= 0 else COLORS["red"],
                "outline": None,
                "width": 1,
            }
        x0, x1 = sorted((x_pos(start), x_pos(end)))
        if x0 == x1:
            x1 = x0 + 1
        draw.text((left - 140, y_mid - 8), label, fill=COLORS["black"], font=body_font)
        draw.rounded_rectangle(
            (x0, y_mid - bar_height // 2, x1, y_mid + bar_height // 2),
            radius=3,
            fill=style["fill"],
            outline=style["outline"],
            width=style["width"],
        )
        text = _format_number(value)
        text_x = x1 + 6 if value >= 0 else x0 - 64
        draw.text((text_x, y_mid - 7), text, fill=COLORS["black"], font=label_font)
        if measure == "total" and delta_percent_label:
            draw.text(
                (text_x, y_mid + 9),
                delta_percent_label,
                fill=COLORS["grey"],
                font=label_font,
            )
    return axis_y + 28


def write_waterfall_fallback_png(fig: go.Figure, path: str) -> None:
    """Write a deterministic PNG fallback when Kaleido/Chrome is unavailable."""

    traces = list(fig.data)
    if not traces:
        raise ValueError("No waterfall traces are available for fallback rendering.")
    title_lines = _clean_html_lines(getattr(fig.layout.title, "text", "Sales variance"))
    panel_heights = [86 + len(getattr(trace, "y", [])) * 34 for trace in traces]
    annotations = [
        _clean_html(getattr(annotation, "text", ""))
        for annotation in getattr(fig.layout, "annotations", [])
    ]
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    delta_percent_label = str(meta.get("pvm_delta_percent_label") or "")
    small_multiples_grid = meta.get("waterfall_small_multiples_grid")
    delta_percent_labels = [
        str(label or "") for label in (meta.get("waterfall_delta_percent_labels") or [])
    ]
    panel_titles = [
        str(title or "") for title in (meta.get("waterfall_panel_titles") or [])
    ]
    if isinstance(small_multiples_grid, dict) and len(traces) > 1:
        cols = max(1, int(small_multiples_grid.get("cols") or 1))
        rows = max(
            1, int(small_multiples_grid.get("rows") or math.ceil(len(traces) / cols))
        )
        panel_width = 480
        panel_height = max(250, max(panel_heights))
        width = max(int(fig.layout.width or 0), 70 + panel_width * cols)
        top = 40 + max(len(title_lines), 1) * 28
        height = max(int(fig.layout.height or 0), top + panel_height * rows + 35)
        image = Image.new("RGB", (width, height), COLORS["white"])
        draw = ImageDraw.Draw(image)
        title_font = _font(22)
        for index, line in enumerate(title_lines):
            draw.text(
                (36, 24 + index * 28),
                line,
                fill=COLORS["black"],
                font=title_font,
            )
        shared_extent = _combined_trace_extent(traces)
        for index, trace in enumerate(traces):
            row = index // cols
            col = index % cols
            panel_left = 40 + col * panel_width
            panel_top = top + row * panel_height
            title = panel_titles[index] if index < len(panel_titles) else ""
            delta_label = (
                delta_percent_labels[index] if index < len(delta_percent_labels) else ""
            )
            _draw_fallback_trace(
                draw,
                trace,
                top=panel_top,
                left=panel_left + 165,
                right=panel_left + panel_width - 20,
                title=title,
                extent=shared_extent,
                delta_percent_label=delta_label,
            )
        image.save(path, format="PNG")
        return
    if 1 < len(traces) <= 3:
        panel_width = 520
        width = max(int(fig.layout.width or 0), 80 + panel_width * len(traces))
        top = 40 + max(len(title_lines), 1) * 28
        height = max(int(fig.layout.height or 0), top + max(panel_heights) + 50)
        image = Image.new("RGB", (width, height), COLORS["white"])
        draw = ImageDraw.Draw(image)
        title_font = _font(22)
        for index, line in enumerate(title_lines):
            draw.text(
                (36, 24 + index * 28),
                line,
                fill=COLORS["black"],
                font=title_font,
            )
        shared_extent = _combined_trace_extent(traces)
        for index, trace in enumerate(traces):
            panel_left = 40 + index * panel_width
            panel_title = annotations[index] if index < len(annotations) else ""
            _draw_fallback_trace(
                draw,
                trace,
                top=top,
                left=panel_left + 165,
                right=panel_left + panel_width - 22,
                title=panel_title,
                extent=shared_extent,
                delta_percent_label=delta_percent_label,
            )
        image.save(path, format="PNG")
        return

    width = max(1000, int(fig.layout.width or 1200))
    height = max(
        int(fig.layout.height or 0),
        48 + max(len(title_lines), 1) * 28 + sum(panel_heights),
    )
    image = Image.new("RGB", (width, height), COLORS["white"])
    draw = ImageDraw.Draw(image)
    title_font = _font(22)
    line_height = 28
    for index, line in enumerate(title_lines):
        draw.text(
            (36, 24 + index * line_height),
            line,
            fill=COLORS["black"],
            font=title_font,
        )
    top = 40 + max(len(title_lines), 1) * line_height
    left = 210
    right = width - 80
    shared_extent = _combined_trace_extent(traces) if len(traces) > 1 else None
    for index, trace in enumerate(traces):
        panel_title = annotations[index] if index < len(annotations) else ""
        top = _draw_fallback_trace(
            draw,
            trace,
            top=top,
            left=left,
            right=right,
            title=panel_title,
            extent=shared_extent,
            delta_percent_label=delta_percent_label,
        )
    image.save(path, format="PNG")


def _legacy_context(
    recipe: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the legacy state dictionaries needed by original chart functions."""

    from modules.utilities.config import get_config_params, get_naming_params

    names = get_naming_params()
    config = get_config_params()
    mappings = recipe["mappings"]
    not_met = names["notMetConditionValue"]
    report_dimensions = list(mappings.get("dimensions") or [])
    has_units = bool(mappings.get("units_column"))
    variance_choice = (
        names["mixAndUnitsAggregation"]
        if has_units
        else names["totalVarianceAggregation"]
    )
    param = {
        names["numberOfPeriodsFound"]: 2,
        names["unitsColFound"]: has_units,
        names["volumeColFound"]: False,
        names["discountColFound"]: bool(mappings.get("discount_column")),
        names["cogsColFound"]: bool(mappings.get("cogs_column")),
        names["marginColFound"]: bool(mappings.get("cogs_column")),
        names["monetaryLocalCurrencyColFound"]: True,
        names["calculateDriverVariance"]: False,
        names["driverArray"]: [],
        names["isFilteredKey"]: not_met,
        names["selectedPeriods"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["allPeriodsList"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["impossibleToProcessFile"]: False,
        names["fileUploadDisabled"]: not_met,
        names["dropLowCorrelationCols"]: False,
        names["toTitleCase"]: False,
        names["reverseSortPeriods"]: False,
        names["isColumnMultiplied"]: False,
        names["renameTitlesDict"]: {},
    }
    total_baseline = 0.0
    total_comparison = 0.0
    currency = str(recipe.get("options", {}).get("currency") or "EUR")
    chart = {
        names["selectedPeriods"]: [
            str(mappings["baseline_period"]),
            str(mappings["comparison_period"]),
        ],
        names["varianceAggregation"]: variance_choice,
        names["processingChoice"]: names["runOneDimensionalAnalysis"],
        names["mainDimension"]: report_dimensions,
        names["reverseSortPeriods"]: False,
        names["showInitialAndFinalValues"]: False,
        names["varianceInPercent"]: False,
        names["shareOfTotalMarket"]: False,
        names["plotSmallMultiplesWaterfall"]: False,
        names["filterDates"]: False,
        names["compareScenariosOrPeriods"]: names["comparePeriods"],
        names["chosenChart"]: names["verticalWaterfallChart"],
        names["varianceAnalysisChart"]: True,
        names["currencyChoice"]: currency,
        names["fullCurrencyName"]: currency,
    }
    for key in (
        names["totalAmountPeriodZero"],
        names["totalAmountPeriodZeroFiltered"],
        names["periodZeroSum"],
    ):
        param[key] = total_baseline
    for key in (
        names["totalAmountPeriodOne"],
        names["totalAmountPeriodOneFiltered"],
        names["periodOneSum"],
    ):
        param[key] = total_comparison
    param[names["totalVarianceValue"]] = total_comparison - total_baseline
    return names, config, param, chart


def _legacy_chart_frame(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
    config: dict[str, Any],
    *,
    include_zero_components: bool = False,
) -> pl.DataFrame:
    """Convert plugin result rows into the original waterfall input schema."""

    baseline, comparison = _periods(recipe)
    periods = config["periodsArray"]
    separator = names["separatorString"]
    sales_p0 = names["monetaryLocalCurrencyName"] + separator + periods[0]
    sales_p1 = names["monetaryLocalCurrencyName"] + separator + periods[1]
    measure = names["measureName"]
    work_column = names["workColumn"]
    work_column_two = names["workColumnTwo"]
    variance_amount = names["varianceAmountName"]
    variance_type = names["varianceTypeName"]
    label = names["labelName"]
    report_dimensions = [
        dimension
        for dimension in recipe["mappings"].get("dimensions", [])
        if dimension in df.schema
    ]
    baseline_total = _sum_column(df, "amount_baseline")
    comparison_total = _sum_column(df, "amount_comparison")
    rows: list[dict[str, Any]] = [
        {
            measure: "absolute",
            work_column: baseline,
            work_column_two: baseline_total,
            variance_amount: baseline_total,
            variance_type: "",
            label: _format_number(baseline_total),
            sales_p0: baseline_total,
            sales_p1: comparison_total,
        }
    ]
    for source_row in df.to_dicts():
        dimension_values = [
            str(source_row.get(dimension))
            for dimension in report_dimensions
            if source_row.get(dimension) not in (None, "")
        ]
        prefix = " - ".join(dimension_values)
        for component_label, column in _component_columns(recipe):
            value = float(source_row.get(column) or 0.0)
            if abs(value) <= TOLERANCE and not include_zero_components:
                continue
            display_label = (
                f"  {prefix} - {component_label}" if prefix else component_label
            )
            rows.append(
                {
                    measure: "relative",
                    work_column: display_label,
                    work_column_two: value,
                    variance_amount: value,
                    variance_type: component_label,
                    label: _format_number(value),
                    sales_p0: float(source_row.get("amount_baseline") or 0.0),
                    sales_p1: float(source_row.get("amount_comparison") or 0.0),
                }
            )
        residual = float(source_row.get("component_reconciliation_delta") or 0.0)
        if abs(residual) > TOLERANCE:
            display_label = f"  {prefix} - Other" if prefix else "Other"
            rows.append(
                {
                    measure: "relative",
                    work_column: display_label,
                    work_column_two: residual,
                    variance_amount: residual,
                    variance_type: "Other",
                    label: _format_number(residual),
                    sales_p0: float(source_row.get("amount_baseline") or 0.0),
                    sales_p1: float(source_row.get("amount_comparison") or 0.0),
                }
            )
    rows.append(
        {
            measure: "total",
            work_column: comparison,
            work_column_two: comparison_total,
            variance_amount: comparison_total,
            variance_type: "",
            label: _format_number(comparison_total),
            sales_p0: baseline_total,
            sales_p1: comparison_total,
        }
    )
    return pl.DataFrame(rows).with_columns(
        pl.col(variance_amount).cast(pl.Float64, strict=False),
        pl.col(work_column_two).cast(pl.Float64, strict=False),
        pl.col(sales_p0).cast(pl.Float64, strict=False),
        pl.col(sales_p1).cast(pl.Float64, strict=False),
    )


def _legacy_small_multiples_aggregation(
    names: dict[str, str],
    recipe: dict[str, Any],
    legacy_frame: pl.DataFrame,
) -> str:
    """Return the legacy compact variance aggregation for dimension panels."""

    schema = legacy_frame.schema
    if (
        recipe["mappings"].get("units_column")
        and names["priceVariance"] in schema
        and names["volumeVariance"] in schema
    ):
        return names["priceAndUnitsAggregation"]
    if names["totalVariance"] in schema:
        return names["totalVarianceAggregation"]
    return names["mixAndUnitsAggregation"]


def _legacy_small_multiples_variance_types(
    aggregation: str,
    names: dict[str, str],
) -> list[str]:
    """Return source variance columns shown by a legacy small-multiple panel."""

    if aggregation in {
        names["priceAndUnitsAggregation"],
        names["priceAndVolumeAggregation"],
    }:
        return [names["priceVariance"], names["volumeVariance"]]
    if aggregation == names["totalVarianceAggregation"]:
        return [names["totalVariance"]]
    if aggregation in {
        names["mixAndUnitsAggregation"],
        names["mixAndVolumeAggregation"],
    }:
        return [
            names["priceVariance"],
            names["pureVolumeVarianceName"],
            names["mixVariance"],
        ]
    return []


def _legacy_small_multiples_other_label() -> str:
    """Return the legacy label for the aggregated residual member panel."""

    try:
        from modules.utilities.config import get_naming_params

        return str(get_naming_params()["aggregateOtherWaterfallsName"])
    except (ImportError, KeyError):
        return "Others aggregated"


def _legacy_frame_with_panel_bucket(
    legacy_frame: pl.DataFrame,
    dimension: str,
    selected_values: list[str],
    *,
    other_label: str,
    include_other: bool,
) -> pl.DataFrame:
    """Return a legacy frame with non-selected members bucketed as Other."""

    frame = legacy_frame.with_columns(
        pl.col(dimension).cast(pl.Utf8).fill_null("").alias(dimension)
    )
    if not include_other:
        return frame
    return frame.with_columns(
        pl.when(pl.col(dimension).is_in(selected_values))
        .then(pl.col(dimension))
        .otherwise(pl.lit(other_label))
        .alias(dimension)
    )


def _replace_legacy_period_labels(
    frame: pl.DataFrame | pl.LazyFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
) -> pl.DataFrame:
    """Replace legacy Period Zero/One row labels with recipe labels."""

    df = frame.collect() if isinstance(frame, pl.LazyFrame) else frame
    if df.height < 2:
        return df
    baseline, comparison = _periods(recipe)
    work_column = names["workColumn"]
    measure = names["measureName"]
    return (
        df.with_row_index("__row_nr")
        .with_columns(
            pl.when(pl.col("__row_nr") == 0)
            .then(pl.lit(baseline))
            .when(pl.col("__row_nr") == df.height - 1)
            .then(pl.lit(comparison))
            .otherwise(pl.col(work_column))
            .alias(work_column),
            pl.when(pl.col("__row_nr") == df.height - 1)
            .then(pl.lit("total"))
            .otherwise(pl.col(measure))
            .alias(measure),
        )
        .drop("__row_nr")
    )


def _legacy_small_multiples_display_types(
    aggregation: str,
    names: dict[str, str],
    recipe: dict[str, Any],
) -> list[str]:
    """Return row labels expected inside one compact variance panel."""

    if aggregation in {
        names["priceAndUnitsAggregation"],
        names["priceAndVolumeAggregation"],
    }:
        volume_label = (
            "Units & mix" if recipe["mappings"].get("units_column") else "Volume & mix"
        )
        return [names["priceVariance"], volume_label]
    if aggregation == names["totalVarianceAggregation"]:
        unit_word = "units" if recipe["mappings"].get("units_column") else "volume"
        return [f"Price & {unit_word} & mix"]
    if aggregation in {
        names["mixAndUnitsAggregation"],
        names["mixAndVolumeAggregation"],
    }:
        volume_label = "Units" if recipe["mappings"].get("units_column") else "Volume"
        return [names["priceVariance"], volume_label, names["mixVariance"]]
    return []


def _order_legacy_small_multiple_rows(
    frame: pl.DataFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
    aggregation: str,
) -> pl.DataFrame:
    """Keep all small-multiple panels in the same waterfall row order."""

    baseline, comparison = _periods(recipe)
    ordered_labels = [
        baseline,
        *_legacy_small_multiples_display_types(aggregation, names, recipe),
        names["residualName"],
        comparison,
    ]
    work_column = names["workColumn"]
    label_key = pl.col(work_column).cast(pl.Utf8).str.strip_chars()
    order_expr = pl.lit(len(ordered_labels))
    for index, label in reversed(list(enumerate(ordered_labels))):
        order_expr = (
            pl.when(label_key == label).then(pl.lit(index)).otherwise(order_expr)
        )
    return (
        frame.with_row_index("__row_nr")
        .with_columns(order_expr.alias("__order"))
        .sort(["__order", "__row_nr"])
        .drop(["__order", "__row_nr"])
    )


def _prefix_legacy_small_multiple_axis_labels(
    frame: pl.DataFrame,
    recipe: dict[str, Any],
    names: dict[str, str],
    aggregation: str,
) -> tuple[pl.DataFrame, dict[str, str], list[str], list[str]]:
    """Prefix category labels while returning visible tick labels."""

    baseline, comparison = _periods(recipe)
    visible_order = [
        baseline,
        *_legacy_small_multiples_display_types(aggregation, names, recipe),
        names["residualName"],
        comparison,
    ]
    present_labels = {
        str(value).strip() for value in frame[names["workColumn"]].to_list()
    }
    visible_order = [label for label in visible_order if label in present_labels]
    label_map = {
        label: _ordered_axis_label(index, label)
        for index, label in enumerate(visible_order, start=1)
    }
    expr = pl.col(names["workColumn"])
    for visible_label, prefixed_label in label_map.items():
        label_key = pl.col(names["workColumn"]).cast(pl.Utf8).str.strip_chars()
        expr = (
            pl.when(label_key == visible_label)
            .then(pl.lit(prefixed_label))
            .otherwise(expr)
        )
    return (
        frame.with_columns(expr.alias(names["workColumn"])),
        label_map,
        [label_map[label] for label in visible_order],
        visible_order,
    )


def _panel_period_totals(
    frame: pl.DataFrame,
    dimension: str,
    value: str,
    names: dict[str, str],
    config: dict[str, Any],
) -> tuple[float, float]:
    """Return baseline and comparison totals for one small-multiple panel."""

    periods = config["periodsArray"]
    separator = names["separatorString"]
    sales_p0 = names["monetaryLocalCurrencyName"] + separator + periods[0]
    sales_p1 = names["monetaryLocalCurrencyName"] + separator + periods[1]
    panel = frame.filter(pl.col(dimension) == value)
    return _sum_column(panel, sales_p0), _sum_column(panel, sales_p1)


def _legacy_color_first_bar_shape(
    df: pl.DataFrame,
    param: dict[str, Any],
    chart: dict[str, Any],
    color_dict: dict[str, str],
    run: str,
    count: int,
    shapes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return legacy shape metadata that colors the first total bar."""

    from modules.charting.legacy_draw_waterfall import set_semantic_bar_color
    from modules.utilities.config import get_config_params, get_naming_params

    names = get_naming_params()
    config = get_config_params()
    work_column = names["workColumn"]
    variance_amount = names["varianceAmountName"]
    first_label = str(df[work_column][0]).lower()
    is_expected_data = any(
        element in first_label for element in config[names["planStemArray"]]
    )
    can_show_initial_and_final = True
    if names["varianceAggregation"] in chart:
        if (
            chart[names["varianceAggregation"]]
            not in [
                names["totalVarianceAggregation"],
                names["marginVarianceAggregation"],
            ]
            and names["drilldownReportRunName"] in run
        ):
            can_show_initial_and_final = False
    if (
        names["showInitialAndFinalValues"] in chart
        and chart[names["showInitialAndFinalValues"]]
        and can_show_initial_and_final
    ):
        first_bar_color, line_width, line_color = set_semantic_bar_color(
            is_expected_data,
            color_dict,
            param,
        )
        shapes.append(
            {
                "type": "rect",
                "fillcolor": first_bar_color,
                "opacity": 1,
                "line_width": line_width,
                "line_color": line_color,
                "xref": f"x{count}",
                "yref": f"y{count}",
                "y0": -0.4,
                "y1": 0.4,
                "x0": 0,
                "x1": df[variance_amount][0],
            }
        )
    return shapes


def _legacy_line_shape(
    df: pl.DataFrame,
    param: dict[str, Any],
    chart: dict[str, Any],
    color_dict: dict[str, str],
    run: str,
    count: int,
    shapes: list[dict[str, Any]],
    x0_value: float,
    x1_value: float,
    number_of_charts: int,
    *,
    is_arrow: bool,
    is_period_zero: bool,
    count_rows: int,
) -> list[dict[str, Any]]:
    """Return legacy line/arrow shape metadata for small-multiple totals."""

    from modules.charting.adjust_position import get_y1_y0_values
    from modules.charting.draw_charts_utils import get_polars_value_at_index
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    can_show_initial_and_final = True
    if names["varianceAggregation"] in chart:
        if (
            chart[names["varianceAggregation"]]
            not in [
                names["totalVarianceAggregation"],
                names["marginVarianceAggregation"],
            ]
            and names["drilldownReportRunName"] in run
        ):
            can_show_initial_and_final = False
    if not (
        names["showInitialAndFinalValues"] in chart
        and chart[names["showInitialAndFinalValues"]]
        and can_show_initial_and_final
    ):
        return shapes
    line_width = 1
    line_color = color_dict["lightGreyColor"]
    panel_lazy = df.lazy()
    period_one_value = get_polars_value_at_index(
        panel_lazy.filter(
            pl.col(names["workColumn"]) == chart[names["selectedPeriods"]][1]
        ),
        names["varianceAmountName"],
        0,
    )
    period_zero_value = get_polars_value_at_index(
        panel_lazy,
        names["varianceAmountName"],
        0,
    )
    if is_arrow:
        line_width = 2
        line_color = (
            color_dict["greenColor"]
            if period_one_value >= period_zero_value
            else color_dict["redColor"]
        )
    y0_value, y1_value, _yshift, line_color = get_y1_y0_values(
        number_of_charts,
        False,
        is_arrow,
        count,
        is_period_zero,
        line_color,
        chart,
        count_rows,
    )
    shapes.append(
        {
            "type": "line",
            "opacity": 1,
            "line_width": line_width,
            "line_color": line_color,
            "yref": "paper",
            "xref": f"x{count}",
            "y0": y0_value,
            "y1": y1_value,
            "x0": x0_value,
            "x1": x1_value,
            "layer": "below",
        }
    )
    return shapes


def _legacy_delta_annotation(
    df: pl.DataFrame,
    param: dict[str, Any],
    chart: dict[str, Any],
    color_dict: dict[str, str],
    run: str,
    count: int,
    annotations: list[dict[str, Any]],
    number_of_charts: int,
    *,
    is_text: bool,
    is_arrow: bool,
    count_rows: int,
) -> list[dict[str, Any]]:
    """Return legacy annotation metadata for total change arrows and labels."""

    from modules.charting.adjust_position import get_y1_y0_values
    from modules.charting.chart_primitives import divide_by_value_prefix
    from modules.charting.draw_charts_utils import get_polars_value_at_index
    from modules.utilities.config import get_naming_params

    names = get_naming_params()
    can_show_initial_and_final = True
    if names["varianceAggregation"] in chart:
        if (
            chart[names["varianceAggregation"]]
            not in [
                names["totalVarianceAggregation"],
                names["marginVariance"],
            ]
            and names["drilldownReportRunName"] in run
        ):
            can_show_initial_and_final = False
    if not (
        names["showInitialAndFinalValues"] in chart
        and chart[names["showInitialAndFinalValues"]]
        and can_show_initial_and_final
    ):
        return annotations
    panel_lazy = df.lazy()
    period_one_value = get_polars_value_at_index(
        panel_lazy.filter(
            pl.col(names["workColumn"]) == chart[names["selectedPeriods"]][1]
        ),
        names["varianceAmountName"],
        0,
    )
    period_zero_value = get_polars_value_at_index(
        panel_lazy,
        names["varianceAmountName"],
        0,
    )
    arrow_color = (
        color_dict["greenColor"]
        if period_one_value >= period_zero_value
        else color_dict["redColor"]
    )
    y0_value, _y1_value, yshift, _line_color = get_y1_y0_values(
        number_of_charts,
        is_text,
        is_arrow,
        count,
        True,
        arrow_color,
        chart,
        count_rows,
    )
    if period_zero_value:
        difference = divide_by_value_prefix(
            period_one_value - period_zero_value,
            chart,
            False,
        )
        percent_change = (
            (period_one_value - period_zero_value) / period_zero_value
        ) * 100
        percent_text = (
            f"<i>({int(round(percent_change, 0))}%)</i>"
            if math.isfinite(percent_change)
            else "<i>(nan)</i>"
        )
        change_value = f"{names['deltaName']} {difference} {percent_text}"
    else:
        change_value = f"{names['deltaName']} nan"
    annotations.append(
        {
            "showarrow": is_arrow,
            "arrowcolor": arrow_color,
            "text": None if is_arrow else change_value,
            "xshift": 0 if is_arrow else 30,
            "yshift": yshift,
            "arrowhead": 5,
            "arrowsize": 1,
            "ay": y0_value,
            "y": y0_value,
            "yref": "paper",
            "ax": period_zero_value,
            "x": period_zero_value,
            "xref": f"x{count}",
            "axref": f"x{count}",
        }
    )
    return annotations


def _delete_black_vertical_lines(fig: go.Figure) -> go.Figure:
    """Apply the legacy axis cleanup used by small-multiple waterfalls."""

    fig.update_layout(
        yaxis={
            "showline": False,
            "showticklabels": True,
        }
    )
    fig.update_yaxes(showline=False)
    fig.update_yaxes(zeroline=True, zerolinecolor="black", zerolinewidth=2)
    return fig


def _draw_with_legacy_runtime(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    legacy_frame: pl.DataFrame,
    include_zero_components: bool = False,
) -> LegacyWaterfallFigure:
    """Draw the standard waterfall through the original legacy chart functions."""

    from modules.charting import legacy_draw_waterfall
    from modules.charting.chart_primitives import (
        add_title_as_annotation,
        get_color_dictionary,
    )
    from modules.charting.make_titles import make_vertical_waterfall_chart_title
    from modules.charting.update_layouts import update_waterfall_layout_one_dimension

    names, config, param, chart = _legacy_context(recipe)
    chart_df = _legacy_chart_frame(
        df,
        recipe,
        names,
        config,
        include_zero_components=include_zero_components,
    )
    baseline_total = _sum_column(df, "amount_baseline")
    comparison_total = _sum_column(df, "amount_comparison")
    for key in (
        names["totalAmountPeriodZero"],
        names["totalAmountPeriodZeroFiltered"],
        names["periodZeroSum"],
    ):
        param[key] = baseline_total
    for key in (
        names["totalAmountPeriodOne"],
        names["totalAmountPeriodOneFiltered"],
        names["periodOneSum"],
    ):
        param[key] = comparison_total
    param[names["totalVarianceValue"]] = comparison_total - baseline_total

    color_dict = get_color_dictionary(chart)
    run = names["runOneDimensionalAnalysis"]
    fig, number_format, chart = legacy_draw_waterfall.draw_vertical_waterfall_chart(
        chart_df,
        color_dict,
        param,
        chart,
        run,
    )
    layout_chart = dict(chart)
    layout_chart.pop(names["varianceDifferentCalculations"], None)
    fig = update_waterfall_layout_one_dimension(chart_df, fig, layout_chart)
    fig.update_yaxes(autorange="reversed", ticks="")

    title_chart = dict(chart)
    if names["companySales"] in names.values():
        title_chart[names["datasetTypeName"]] = names["companySales"]
    title_chart[names["varianceDifferentCalculations"]] = True
    title, param, title_chart = make_vertical_waterfall_chart_title(
        chart_df,
        names["verticalWaterfallChart"],
        param,
        None,
        names["monetaryLocalCurrencyName"],
        title_chart,
        names["pyName"],
        names["acName"],
    )
    fig = add_title_as_annotation(
        fig,
        title,
        names["verticalWaterfallChart"],
        title_chart,
    )
    baseline_label, comparison_label = _periods(recipe)
    title = title.replace(
        f"{names['acName']} vs {names['pyName']}",
        f"{comparison_label} vs {baseline_label}",
    )
    fig.layout.annotations[-1].text = title
    layout_title = _clean_html(getattr(fig.layout.title, "text", ""))
    if layout_title:
        fig.update_layout(
            title={
                "text": str(fig.layout.title.text).replace(
                    f"{names['acName']} vs {names['pyName']}",
                    f"{comparison_label} vs {baseline_label}",
                )
            }
        )
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "legacy_single",
            "title": title,
            "number_format": number_format,
            "row_count": df.height,
            "legacy_chart_row_count": chart_df.height,
            "legacy_source_row_count": legacy_frame.height,
            "source_functions": [
                "modules.charting.draw_waterfall.draw_vertical_waterfall_chart",
                "modules.charting.legacy_draw_waterfall.draw_vertical_waterfall_chart",
                "modules.charting.update_layouts.update_waterfall_layout_one_dimension",
                "modules.charting.make_titles.make_vertical_waterfall_chart_title",
                "modules.charting.chart_primitives.add_title_as_annotation",
            ],
        },
    )


def _draw_component_with_legacy_runtime(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    legacy_frame: pl.DataFrame,
) -> LegacyWaterfallFigure:
    """Draw the aggregate standard component bridge through legacy code."""

    rendered = _draw_with_legacy_runtime(
        _aggregate_component_frame(df),
        _component_only_recipe(recipe),
        legacy_frame=legacy_frame,
        include_zero_components=True,
    )
    audit = dict(rendered.audit)
    audit.update(
        {
            "mode": "legacy_component_single",
            "panel_bridge": "standard_variance_components",
            "source_row_count": df.height,
        }
    )
    return LegacyWaterfallFigure(figure=rendered.figure, audit=audit)


def _legacy_small_multiples_figure(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    dimension: str,
    *,
    legacy_frame: pl.DataFrame,
) -> LegacyWaterfallFigure:
    """Build legacy fixed-dimension variance small multiples."""

    from modules.charting import legacy_draw_waterfall
    from modules.charting.adjust_position import move_labels_up
    from modules.charting.chart_helpers import make_one_dimensional_variance_subplots
    from modules.charting.chart_primitives import get_color_dictionary
    from modules.charting.draw_charts_utils import get_polars_value_at_index
    from modules.charting.plot_charts import plot_waterfall_small_multiples
    from modules.charting.update_layouts import update_waterfall_layout_small_multiples
    from modules.data.waterfall_data_prep import prepare_data_for_waterfall
    from modules.utilities.ui_notifier import HeadlessChartCapture, use_ui_notifier
    from modules.variance.variance_orchestrator import melt_data_on_variance_cols
    from modules.variance.variance_utils import (
        group_by_and_sort_data_for_variance_calculation,
    )

    slices = _small_multiple_values(df, dimension)
    if not slices:
        return _draw_with_legacy_runtime(df, recipe, legacy_frame=legacy_frame)

    names, config, param, chart = _legacy_context(recipe)
    aggregation = _legacy_small_multiples_aggregation(names, recipe, legacy_frame)
    other_label = _legacy_small_multiples_other_label()
    selected_values = [value for value, _slice in slices if value != other_label]
    include_other = any(value == other_label for value, _slice in slices)
    panel_values = [
        other_label if value == other_label else value for value, _ in slices
    ]
    legacy_panel_frame = _legacy_frame_with_panel_bucket(
        legacy_frame,
        dimension,
        selected_values,
        other_label=other_label,
        include_other=include_other,
    )
    for key in (
        names["totalAmountPeriodZero"],
        names["totalAmountPeriodZeroFiltered"],
        names["periodZeroSum"],
    ):
        param[key] = _sum_column(
            legacy_panel_frame,
            names["monetaryLocalCurrencyName"]
            + names["separatorString"]
            + config["periodsArray"][0],
        )
    for key in (
        names["totalAmountPeriodOne"],
        names["totalAmountPeriodOneFiltered"],
        names["periodOneSum"],
    ):
        param[key] = _sum_column(
            legacy_panel_frame,
            names["monetaryLocalCurrencyName"]
            + names["separatorString"]
            + config["periodsArray"][1],
        )
    param[names["totalVarianceValue"]] = (
        param[names["totalAmountPeriodOne"]] - param[names["totalAmountPeriodZero"]]
    )

    chart[names["mainDimension"]] = [dimension]
    chart[names["varianceAggregation"]] = aggregation
    chart[names["plotSmallMultiplesWaterfall"]] = True
    chart[names["aggregateOtherWaterfalls"]] = include_other
    chart[names["numberOfSmallMultiplesWaterfall"]] = max(1, len(selected_values))
    chart[names["showInitialAndFinalValues"]] = True
    chart[names["varianceAggregationOptionsArray"]] = [aggregation]
    chart[names["smallMultiplesWaterfall"]] = panel_values

    melted, param = melt_data_on_variance_cols(
        legacy_panel_frame,
        param,
        chart,
        [dimension],
    )
    variance_type = names["varianceTypeName"]
    variance_amount = names["varianceAmountName"]
    source_variance_types = _legacy_small_multiples_variance_types(aggregation, names)
    if source_variance_types:
        melted = melted.filter(pl.col(variance_type).is_in(source_variance_types))
    grouped, _group_by_cols, _sum_cols = (
        group_by_and_sort_data_for_variance_calculation(
            melted,
            [dimension, variance_type],
            [variance_amount],
        )
    )
    grouped = grouped.collect() if isinstance(grouped, pl.LazyFrame) else grouped

    color_dict = get_color_dictionary(chart)
    run = names["runOneDimensionalAnalysis"]
    param[names["columnHash"]] = param.get(names["columnHash"], {})
    capture = HeadlessChartCapture()
    with use_ui_notifier(capture):
        param, chart = plot_waterfall_small_multiples(
            grouped,
            legacy_panel_frame,
            [dimension, variance_type],
            param,
            chart,
            color_dict,
            run,
        )
    captured_output = capture.last_chart_output()
    fig = captured_output.figure
    export_frame = captured_output.frame
    panel_values = [
        str(value)
        for value in chart.get(names["smallMultiplesWaterfall"], panel_values)
    ]
    delta_labels = [
        _delta_percent_label(
            *_panel_period_totals(legacy_panel_frame, dimension, value, names, config),
            names,
        )
        for value in panel_values
    ]
    title = make_vertical_waterfall_chart_title(df, recipe, dimension=dimension)
    annotations = []
    for annotation in fig.layout.annotations or ():
        if "Sales variance" in _clean_html(getattr(annotation, "text", "")):
            continue
        annotations.append(annotation)
    fig.layout.annotations = tuple(annotations)
    traces = list(fig.data)
    if traces:
        global_range = _combined_trace_extent(traces)
        fig.update_xaxes(range=list(global_range), matches="x")
    number_of_cols = min(3, max(1, len(panel_values)))
    number_of_rows = math.ceil(max(1, len(panel_values)) / number_of_cols)
    fig.update_yaxes(autorange="reversed", ticks="")
    fig.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        meta={
            "waterfall_small_multiples_grid": {
                "rows": number_of_rows,
                "cols": number_of_cols,
            },
            "waterfall_panel_titles": panel_values,
            "waterfall_delta_percent_labels": delta_labels,
        },
    )
    export_row_count = (
        export_frame.height if isinstance(export_frame, pl.DataFrame) else None
    )
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "legacy_variance_small_multiples",
            "title": title,
            "small_multiples_dimension": dimension,
            "small_multiples_panel_bridge": "legacy_price_units_mix",
            "small_multiples_aggregation": aggregation,
            "small_multiples_count": len(panel_values),
            "small_multiples_limit": MAX_SMALL_MULTIPLES,
            "row_count": df.height,
            "legacy_source_row_count": legacy_frame.height,
            "legacy_reference_function": (
                "modules.charting.plot_charts.plot_waterfall_small_multiples"
            ),
            "legacy_reference_function_call_mode": "executed_headless",
            "source_functions": [
                "modules.variance.variance_orchestrator.melt_data_on_variance_cols",
                "modules.variance.variance_utils.group_by_and_sort_data_for_variance_calculation",
                "modules.charting.plot_charts.plot_waterfall_small_multiples",
                "modules.data.waterfall_data_prep.prepare_data_for_waterfall",
                "modules.charting.legacy_draw_waterfall.draw_vertical_waterfall_chart",
                "modules.charting.chart_helpers.set_up_tab_for_show_or_download_chart",
                "modules.utilities.ui_notifier.HeadlessChartCapture",
            ],
            "captured_chart_output_count": len(capture.chart_outputs),
            "captured_plotly_chart_count": len(capture.plotly_charts),
            "delta_percent_labels": delta_labels,
            "number_format": "",
            "export_row_count": export_row_count,
        },
    )

    cols = min(3, len(panel_values))
    (
        fig,
        count_rows,
        count_cols,
        count,
        number_of_cols,
        number_of_rows,
    ) = make_one_dimensional_variance_subplots(panel_values, numberOfCols=cols)
    panel_title_annotations = list(fig.layout.annotations or ())
    color_dict = get_color_dictionary(chart)
    run = names["runOneDimensionalAnalysis"]
    shape_array: list[dict[str, Any]] = []
    period_zero_line_array: list[dict[str, Any]] = []
    period_one_line_array: list[dict[str, Any]] = []
    arrow_array: list[dict[str, Any]] = []
    annotation_arrow_array: list[dict[str, Any]] = []
    annotation_text_array: list[dict[str, Any]] = []
    layout_frames: list[pl.DataFrame] = []
    export_frames: list[pl.DataFrame] = []
    delta_labels: list[str] = []
    number_format = ""
    baseline_label, comparison_label = _periods(recipe)

    for panel_value in panel_values:
        panel_grouped = grouped.filter(pl.col(dimension) == panel_value).drop(dimension)
        if panel_grouped.is_empty():
            continue
        panel_df, _df_filtered, param = prepare_data_for_waterfall(
            panel_grouped,
            [],
            param,
            chart,
            run,
            dimension,
            panel_value,
            legacy_panel_frame,
            count,
        )
        panel_df = _replace_legacy_period_labels(panel_df, recipe, names)
        panel_df = _order_legacy_small_multiple_rows(
            panel_df,
            recipe,
            names,
            aggregation,
        )
        panel_df, label_map, tick_values, tick_text = (
            _prefix_legacy_small_multiple_axis_labels(
                panel_df,
                recipe,
                names,
                aggregation,
            )
        )
        panel_df = (
            panel_df.collect() if isinstance(panel_df, pl.LazyFrame) else panel_df
        )
        layout_frames.append(panel_df)
        panel_period_zero, panel_period_one = _panel_period_totals(
            legacy_panel_frame,
            dimension,
            panel_value,
            names,
            config,
        )
        delta_labels.append(
            _delta_percent_label(panel_period_zero, panel_period_one, names)
        )
        panel_chart = dict(chart)
        panel_chart[names["selectedPeriods"]] = [
            label_map.get(baseline_label, baseline_label),
            label_map.get(comparison_label, comparison_label),
        ]
        fig_det, number_format, _panel_chart = (
            legacy_draw_waterfall.draw_vertical_waterfall_chart(
                panel_df,
                color_dict,
                param,
                panel_chart,
                run,
            )
        )
        if fig_det.data:
            fig_det.data[0].showlegend = False
            fig.add_trace(fig_det.data[0], row=count_rows, col=count_cols)
            fig.update_yaxes(
                tickmode="array",
                tickvals=tick_values,
                ticktext=tick_text,
                categoryorder="array",
                categoryarray=tick_values,
                row=count_rows,
                col=count_cols,
            )
        fig.update_annotations()
        fig = move_labels_up(fig, chart, panel_values)
        shape_array = _legacy_color_first_bar_shape(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            shape_array,
        )
        panel_lazy = panel_df.lazy()
        period_one_value = get_polars_value_at_index(
            panel_lazy.filter(
                pl.col(names["workColumn"])
                == label_map.get(comparison_label, comparison_label)
            ),
            variance_amount,
            0,
        )
        period_zero_value = get_polars_value_at_index(
            panel_lazy.filter(
                pl.col(names["workColumn"])
                == label_map.get(baseline_label, baseline_label)
            ),
            variance_amount,
            0,
        )
        number_of_charts = len(panel_values)
        period_zero_line_array = _legacy_line_shape(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            period_zero_line_array,
            period_zero_value,
            period_zero_value,
            number_of_charts,
            is_arrow=False,
            is_period_zero=True,
            count_rows=count_rows,
        )
        period_one_line_array = _legacy_line_shape(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            period_one_line_array,
            period_one_value,
            period_one_value,
            number_of_charts,
            is_arrow=False,
            is_period_zero=False,
            count_rows=count_rows,
        )
        arrow_array = _legacy_line_shape(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            arrow_array,
            period_zero_value,
            period_one_value,
            number_of_charts,
            is_arrow=True,
            is_period_zero=False,
            count_rows=count_rows,
        )
        annotation_arrow_array = _legacy_delta_annotation(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            annotation_arrow_array,
            number_of_charts,
            is_text=False,
            is_arrow=True,
            count_rows=count_rows,
        )
        annotation_text_array = _legacy_delta_annotation(
            panel_df,
            param,
            panel_chart,
            color_dict,
            run,
            count,
            annotation_text_array,
            number_of_charts,
            is_text=True,
            is_arrow=False,
            count_rows=count_rows,
        )
        export_frames.append(
            panel_df.with_columns(pl.lit(panel_value).alias(dimension))
        )
        if count_cols < number_of_cols:
            count_cols += 1
        else:
            count_cols = 1
            count_rows += 1
        count += 1

    if layout_frames:
        fig.update_layout(
            shapes=shape_array
            + period_zero_line_array
            + period_one_line_array
            + arrow_array,
            annotations=panel_title_annotations
            + annotation_arrow_array
            + annotation_text_array,
        )
        layout_df = pl.concat(layout_frames, how="diagonal_relaxed")
        fig, _width = update_waterfall_layout_small_multiples(
            layout_df,
            fig,
            chart,
            number_of_rows,
            number_of_cols,
        )
    traces = list(fig.data)
    if traces:
        global_range = _combined_trace_extent(traces)
        fig.update_xaxes(range=list(global_range), matches="x")
    fig.update_yaxes(autorange="reversed")
    fig = _delete_black_vertical_lines(fig)
    title = make_vertical_waterfall_chart_title(df, recipe, dimension=dimension)
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left"},
        meta={
            "waterfall_small_multiples_grid": {
                "rows": number_of_rows,
                "cols": number_of_cols,
            },
            "waterfall_panel_titles": panel_values,
            "waterfall_delta_percent_labels": delta_labels,
        },
    )
    fig.update_yaxes(autorange="reversed", ticks="")
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "legacy_variance_small_multiples",
            "title": title,
            "small_multiples_dimension": dimension,
            "small_multiples_panel_bridge": "legacy_price_units_mix",
            "small_multiples_aggregation": aggregation,
            "small_multiples_count": len(panel_values),
            "small_multiples_limit": MAX_SMALL_MULTIPLES,
            "row_count": df.height,
            "legacy_source_row_count": legacy_frame.height,
            "legacy_reference_function": (
                "modules.charting.plot_charts.plot_waterfall_small_multiples"
            ),
            "legacy_reference_function_call_mode": "headless_vendored_equivalent",
            "source_functions": [
                "modules.variance.variance_orchestrator.melt_data_on_variance_cols",
                "modules.variance.variance_utils.group_by_and_sort_data_for_variance_calculation",
                "modules.data.waterfall_data_prep.prepare_data_for_waterfall",
                "modules.charting.legacy_draw_waterfall.draw_vertical_waterfall_chart",
                "modules.charting.update_layouts.update_waterfall_layout_small_multiples",
                "modules.charting.adjust_position.move_labels_up",
            ],
            "delta_percent_labels": delta_labels,
            "number_format": number_format,
            "export_row_count": (
                pl.concat(export_frames, how="diagonal_relaxed").height
                if export_frames
                else 0
            ),
        },
    )


def _single_figure(df: pl.DataFrame, recipe: dict[str, Any]) -> LegacyWaterfallFigure:
    """Build a single legacy-style waterfall figure."""

    labels, _measures, _values, _text = _waterfall_arrays(df, recipe)
    height = max(520, 90 * len(labels) + 210)
    fig = make_subplots(rows=1, cols=1, specs=[[{"type": "waterfall"}]])
    _add_waterfall_trace(fig, df, recipe, row=1, col=1)
    title = make_vertical_waterfall_chart_title(df, recipe)
    _update_layout(fig, title=title, height=height, width=1200)
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "single",
            "title": title,
            "row_count": df.height,
            "source_functions": list(LEGACY_SOURCE_FUNCTIONS),
        },
    )


def _small_multiple_values(
    df: pl.DataFrame, dimension: str
) -> list[tuple[str, pl.DataFrame]]:
    """Return top dimension slices for small-multiple waterfalls."""

    try:
        from modules.utilities.config import get_naming_params

        names = get_naming_params()
        other_label = names["aggregateOtherWaterfallsName"]
    except (ImportError, KeyError):
        other_label = "Other"
    limit = MAX_SMALL_MULTIPLES
    ranked = (
        df.group_by(dimension)
        .agg(pl.col("total_delta").abs().sum().alias("_abs_delta"))
        .sort("_abs_delta", descending=True)
    )
    all_values = [str(value) for value in ranked[dimension].to_list()]
    selected_values = all_values[:limit]
    include_other = len(all_values) > limit
    if include_other:
        selected_values = all_values[: max(1, limit - 1)]
    slices = [
        (
            value,
            df.filter(pl.col(dimension).cast(pl.Utf8) == value),
        )
        for value in selected_values
    ]
    if include_other:
        slices.append(
            (
                other_label,
                df.filter(~pl.col(dimension).cast(pl.Utf8).is_in(selected_values)),
            )
        )
    return slices


def _small_multiples_figure(
    df: pl.DataFrame, recipe: dict[str, Any], dimension: str
) -> LegacyWaterfallFigure:
    """Build a small-multiple legacy-style waterfall figure."""

    slices = _small_multiple_values(df, dimension)
    if not slices:
        return _single_figure(df, recipe)
    cols = min(3, len(slices))
    rows = math.ceil(len(slices) / cols)
    fig = make_subplots(
        rows=rows,
        cols=cols,
        specs=[[{"type": "waterfall"} for _ in range(cols)] for _ in range(rows)],
        subplot_titles=[value for value, _slice in slices],
        horizontal_spacing=0.12,
        vertical_spacing=0.18,
    )
    for index, (_value, slice_df) in enumerate(slices):
        row = index // cols + 1
        col = index % cols + 1
        _add_waterfall_trace(fig, slice_df, recipe, row=row, col=col, show_labels=False)
    title = make_vertical_waterfall_chart_title(df, recipe, dimension=dimension)
    _update_layout(fig, title=title, height=max(520, rows * 360), width=1500)
    return LegacyWaterfallFigure(
        figure=fig,
        audit={
            "mode": "small_multiples",
            "title": title,
            "small_multiples_dimension": dimension,
            "small_multiples_count": len(slices),
            "small_multiples_limit": MAX_SMALL_MULTIPLES,
            "row_count": df.height,
            "source_functions": list(LEGACY_SOURCE_FUNCTIONS),
        },
    )


def draw_vertical_waterfall_chart(
    df: pl.DataFrame,
    recipe: dict[str, Any],
    *,
    small_multiples: bool = False,
    small_multiples_dimension: str | None = None,
    legacy_frame: pl.DataFrame | None = None,
) -> LegacyWaterfallFigure:
    """Build a legacy-style vertical waterfall chart for plugin output."""

    if df.is_empty():
        raise ValueError("Cannot render waterfall chart for an empty variance result.")
    if small_multiples:
        dimension = small_multiples_dimension or next(
            (
                column
                for column in recipe["mappings"].get("dimensions", [])
                if column in df.schema
            ),
            None,
        )
        if legacy_frame is not None and dimension and dimension in df.schema:
            return _legacy_small_multiples_figure(
                df,
                recipe,
                dimension,
                legacy_frame=legacy_frame,
            )
        if dimension and dimension in df.schema:
            return _small_multiples_figure(df, recipe, dimension)
    if legacy_frame is not None:
        return _draw_component_with_legacy_runtime(
            df,
            recipe,
            legacy_frame=legacy_frame,
        )
    return _single_figure(df, recipe)
