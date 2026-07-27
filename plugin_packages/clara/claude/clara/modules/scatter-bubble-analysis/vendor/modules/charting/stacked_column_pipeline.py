from __future__ import annotations

"""Build stacked-column figures through the legacy charting stack."""

import math
import re
from datetime import datetime

import plotly.graph_objects as go
import polars as pl

from modules.charting.chart_primitives import (
    BAIN_HIGHLIGHT_COLOR,
    get_color_array,
    get_color_dictionary,
)
from modules.charting.draw_width_and_stacked_plots import stacked_bar_width_plot
from modules.charting.mekko_pipeline import _AUTO_MAX_KEEP_X, _auto_top_count
from modules.utilities.config import get_naming_params
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_schema_and_column_names,
)

__all__ = ["build_pipeline_stacked_column", "build_pipeline_stacked_column_overlay"]


def _select_top_items(
    lf: pl.LazyFrame,
    dimension: str,
    metric_column: str,
    *,
    max_keep: int,
) -> list[str]:
    cols, _ = get_schema_and_column_names(lf)
    if dimension not in cols or metric_column not in cols:
        return []
    top_n = _auto_top_count(lf, dimension, metric_column, max_keep=max_keep)
    if top_n <= 0:
        top_n = int(lf.select(pl.col(dimension).n_unique()).collect().item())
    totals = (
        lf.group_by(dimension)
        .agg(pl.col(metric_column).sum().alias("__total"))
        .collect()
    )
    if totals.is_empty():
        return []
    return [
        str(val)
        for val in totals.sort("__total", descending=True)
        .select(dimension)
        .head(top_n)
        .to_series()
        .to_list()
        if val is not None and str(val).strip()
    ]


def _normalize_palette_name(palette: str | None, naming: dict[str, str]) -> str | None:
    if not palette:
        return None
    raw = str(palette).strip()
    if not raw:
        return None
    known_values = {
        naming["cirqueColorpalette"],
        naming["modernColorpalette"],
        naming["blueAndGreenColorpalette"],
        naming["khakiAndDenimColorpalette"],
        naming["poloColorpalette"],
        naming["heatingUpColorpalette"],
        naming["tableauColorpalette"],
        naming["thinkcellColorpalette"],
        naming["IBCSColorpalette"],
        naming["bainColorpalette"],
        naming["mckinseyColorpalette"],
        naming["bcgColorpalette"],
        naming["occColorpalette"],
        naming["deloitteColorpalette"],
        naming["powerbiColorpalette"],
        naming["symphonyColorpalette"],
        naming["greysColorpalette"],
        naming["bluesColorpalette"],
        naming["orangesColorpalette"],
        naming["purplesColorpalette"],
        naming["brownsColorpalette"],
    }
    if raw in known_values:
        return raw

    key = re.sub(r"[^a-z0-9]+", "", raw.lower())
    mapped = {
        "pastel": "pastel",
        "bold": "bold",
        "muted": "muted",
        "cirque": naming["cirqueColorpalette"],
        "modern": naming["modernColorpalette"],
        "bluegreen": naming["blueAndGreenColorpalette"],
        "khakidenim": naming["khakiAndDenimColorpalette"],
        "polo": naming["poloColorpalette"],
        "heatingup": naming["heatingUpColorpalette"],
        "tableau": naming["tableauColorpalette"],
        "thinkcell": naming["thinkcellColorpalette"],
        "ibcs": naming["IBCSColorpalette"],
        "bain": naming["bainColorpalette"],
        "mckinsey": naming["mckinseyColorpalette"],
        "bcg": naming["bcgColorpalette"],
        "occ": naming["occColorpalette"],
        "deloitte": naming["deloitteColorpalette"],
        "powerbi": naming["powerbiColorpalette"],
        "symphony": naming["symphonyColorpalette"],
        "greys": naming["greysColorpalette"],
        "blues": naming["bluesColorpalette"],
        "oranges": naming["orangesColorpalette"],
        "purples": naming["purplesColorpalette"],
        "browns": naming["brownsColorpalette"],
    }
    return mapped.get(key)


def _compact_number(value: float) -> str:
    number = float(value or 0.0)
    abs_number = abs(number)
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs_number >= 1_000:
        return f"{number / 1_000:.1f}K"
    if math.isclose(number, round(number), rel_tol=0, abs_tol=1e-9):
        return f"{int(round(number))}"
    return f"{number:.1f}"


def _format_number_for_display(value: float, *, in_millions: bool) -> str:
    number = float(value or 0.0)
    if in_millions:
        return f"{number / 1_000_000:.1f}"
    if math.isclose(number, round(number), rel_tol=0, abs_tol=1e-9):
        return f"{int(round(number)):,}"
    return f"{number:,.1f}"


def _format_line_value(value: float, *, in_millions: bool = False) -> str:
    number = float(value or 0.0)
    if in_millions:
        return _format_number_for_display(number, in_millions=True)
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _compute_sparse_month_ticks(
    tickvals: list[object],
    ticktext: list[object],
) -> tuple[list[object], list[str]]:
    if not tickvals or not ticktext or len(tickvals) != len(ticktext):
        return tickvals, [str(text) for text in ticktext]

    sparse_vals: list[object] = []
    sparse_text: list[str] = []
    for x_val, raw_text in zip(tickvals, ticktext):
        label = str(raw_text)
        parsed: datetime | None = None
        try:
            parsed = datetime.fromisoformat(label[:10])
        except ValueError:
            parsed = None
        if parsed is None:
            continue
        if parsed.month in {1, 7}:
            sparse_vals.append(x_val)
            sparse_text.append(parsed.strftime("%b %Y"))

    if len(sparse_vals) >= 2:
        return sparse_vals, sparse_text
    return tickvals, [str(text) for text in ticktext]


def _style_integrated_labels(
    figure: go.Figure,
    *,
    min_share_for_inside_label: float = 0.07,
    side: str = "right",
    display_in_millions: bool = False,
) -> go.Figure:
    if not isinstance(figure, go.Figure):
        return figure
    traces = list(figure.data or [])
    if not traces:
        return figure

    xaxis = figure.layout.xaxis if figure.layout and figure.layout.xaxis else None
    tickvals = list(getattr(xaxis, "tickvals", []) or [])
    ticktext = list(getattr(xaxis, "ticktext", []) or [])
    if not tickvals:
        first_trace_x = list(getattr(traces[0], "x", []) or [])
        tickvals = list(range(1, len(first_trace_x) + 1))
    sparse_tickvals, sparse_ticktext = _compute_sparse_month_ticks(tickvals, ticktext)
    period_count = len(tickvals)
    if period_count == 0:
        return figure

    series_values: list[list[float]] = []
    for trace in traces:
        ys = [float(v or 0.0) for v in (list(getattr(trace, "y", []) or []))]
        if len(ys) < period_count:
            ys = ys + [0.0] * (period_count - len(ys))
        else:
            ys = ys[:period_count]
        series_values.append(ys)

    totals = [
        sum(series[idx] for series in series_values) for idx in range(period_count)
    ]
    non_zero_counts = [
        sum(1 for series in series_values if series[idx] > 0)
        for idx in range(period_count)
    ]
    max_total = max(totals) if totals else 0.0
    if max_total <= 0:
        return figure
    # Keep labels suffix-free on large charts by showing values in millions.
    use_million_display = max_total >= 1_000_000
    label_font_size = 9
    label_font_family = "Arial, sans-serif"

    # Keep only readable numeric values inside each segment.
    for trace, ys in zip(traces, series_values):
        text_values: list[str] = []
        for idx, value in enumerate(ys):
            total = totals[idx] if idx < len(totals) else 0.0
            share = (value / total) if total > 0 else 0.0
            single_visible_category = (
                idx < len(non_zero_counts) and non_zero_counts[idx] <= 1
            )
            if (
                value <= 0
                or share < min_share_for_inside_label
                or single_visible_category
            ):
                text_values.append("")
            else:
                text_values.append(
                    _format_number_for_display(
                        value,
                        in_millions=use_million_display,
                    )
                )
        trace.text = text_values
        trace.textposition = "inside"
        trace.insidetextanchor = "middle"
        trace.textangle = 0
        trace.constraintext = "none"
        current_textfont = getattr(trace, "textfont", None)
        current_color = (
            getattr(current_textfont, "color", None)
            if current_textfont is not None
            else None
        )
        trace.textfont = (
            {
                "size": label_font_size,
                "family": label_font_family,
                "color": current_color,
            }
            if current_color
            else {"size": label_font_size, "family": label_font_family}
        )
        trace.hovertemplate = f"{trace.name}<br>%{{x}}<br>%{{y:,.2f}}<extra></extra>"

    figure.data = tuple(traces)
    existing_uniformtext = (
        figure.layout.uniformtext.to_plotly_json()
        if getattr(figure.layout, "uniformtext", None)
        else {}
    )
    figure.update_layout(
        showlegend=False,
        uniformtext={
            **existing_uniformtext,
            "mode": "hide",
            "minsize": label_font_size,
        },
    )

    # Remove legacy labels and rebuild clean integrated labels.
    figure.layout.annotations = ()
    annotations: list[dict[str, object]] = []

    # Totals on top of each stacked column.
    y_offset = max_total * 0.02
    for idx, x_value in enumerate(tickvals):
        total = totals[idx]
        annotations.append(
            {
                "x": x_value,
                "y": total + y_offset,
                "xref": "x",
                "yref": "y",
                "text": _format_number_for_display(
                    total,
                    in_millions=use_million_display,
                ),
                "showarrow": False,
                "font": {
                    "size": label_font_size,
                    "family": label_font_family,
                    "color": "#4b5563",
                },
            }
        )

    # External segment labels, anchored to the last period stack.
    last_index = period_count - 1
    running = 0.0
    centers: list[tuple[str, float]] = []
    for trace, ys in zip(traces, series_values):
        value = ys[last_index]
        if value <= 0:
            continue
        center = running + (value / 2.0)
        centers.append((str(trace.name or ""), center))
        running += value

    if centers:
        side = str(side or "right").lower()
        x_anchor = "left" if side == "right" else "right"
        x_paper = 1.0 if side == "right" else 0.0
        x_shift = 5 if side == "right" else -5
        for label, center in centers:
            annotations.append(
                {
                    "x": x_paper,
                    "y": center,
                    "xref": "paper",
                    "yref": "y",
                    "text": label,
                    "showarrow": False,
                    "xanchor": x_anchor,
                    "xshift": x_shift,
                    "align": x_anchor,
                    "font": {
                        "size": label_font_size,
                        "family": label_font_family,
                        "color": "#374151",
                    },
                }
            )

    figure.update_layout(annotations=annotations)
    current_margin = figure.layout.margin or {}
    right_margin = max(int(getattr(current_margin, "r", 0) or 0), 120)
    left_margin = max(int(getattr(current_margin, "l", 0) or 0), 80)
    current_width = int(getattr(figure.layout, "width", 0) or 0)
    min_width_by_periods = left_margin + right_margin + (period_count * 28)
    target_width = max(current_width, min_width_by_periods, 1000)
    figure.update_layout(
        margin={**current_margin.to_plotly_json(), "r": right_margin, "l": left_margin},
        width=target_width,
    )
    figure.update_xaxes(
        tickmode="array",
        tickvals=sparse_tickvals,
        ticktext=sparse_ticktext,
        tickangle=0,
        automargin=True,
    )
    return figure


def _style_combo_labels(figure: go.Figure, *, line_color: str = "#2563eb") -> go.Figure:
    if not isinstance(figure, go.Figure):
        return figure
    traces = list(figure.data or [])
    if not traces:
        return figure
    bar_traces = [trace for trace in traces if getattr(trace, "type", None) == "bar"]
    if not bar_traces:
        return figure

    bar_max = 0.0
    line_max = 0.0
    use_million_display = False
    bar_label_size = 9
    line_label_size = bar_label_size

    # Keep bars dark and line color style-specific (default blue).
    for trace in traces:
        if getattr(trace, "type", None) == "bar":
            y_values = [float(v or 0.0) for v in (list(getattr(trace, "y", []) or []))]
            if y_values:
                bar_max = max(bar_max, max(y_values))
            use_million_display = bar_max >= 1_000_000
            trace.text = [
                (
                    _format_number_for_display(value, in_millions=use_million_display)
                    if value > 0
                    else ""
                )
                for value in y_values
            ]
            trace.marker = {
                **(trace.marker.to_plotly_json() if trace.marker else {}),
                "color": "#343434",
                "line": {"color": "#343434", "width": 0},
            }
            trace.opacity = 1.0
            trace.textposition = "outside"
            trace.cliponaxis = False
            trace.textangle = 0
            trace.textfont = {
                **(trace.textfont.to_plotly_json() if trace.textfont else {}),
                "size": bar_label_size,
                "family": "Arial, sans-serif",
                "color": "#111827",
            }
        elif getattr(trace, "type", None) == "scatter":
            y_values = [float(v or 0.0) for v in (list(getattr(trace, "y", []) or []))]
            if y_values:
                line_max = max(line_max, max(y_values))
            line_use_million_display = line_max >= 1_000_000
            value_count = len(y_values)
            if value_count > 24:
                max_idx = max(range(value_count), key=lambda idx: y_values[idx])
                min_idx = min(range(value_count), key=lambda idx: y_values[idx])
                shown_indices = set(range(0, value_count, 6))
                shown_indices.update({0, value_count - 1, max_idx, min_idx})
                trace.text = [
                    (
                        _format_line_value(
                            value,
                            in_millions=line_use_million_display,
                        )
                        if idx in shown_indices
                        else ""
                    )
                    for idx, value in enumerate(y_values)
                ]
            else:
                trace.text = [
                    _format_line_value(
                        value,
                        in_millions=line_use_million_display,
                    )
                    for value in y_values
                ]
            trace.mode = "lines+markers+text"
            trace.line = {
                **(trace.line.to_plotly_json() if trace.line else {}),
                "color": line_color,
                "width": 2,
            }
            trace.marker = {
                "color": line_color,
                "size": 6,
                "symbol": "circle",
                "line": {"color": line_color, "width": 0},
            }
            trace.textposition = "top center"
            trace.cliponaxis = False
            trace.textfont = {
                **(trace.textfont.to_plotly_json() if trace.textfont else {}),
                "size": line_label_size,
                "family": "Arial, sans-serif",
                "color": line_color,
            }

    xaxis = figure.layout.xaxis if figure.layout and figure.layout.xaxis else None
    tickvals = list(getattr(xaxis, "tickvals", []) or [])
    ticktext = list(getattr(xaxis, "ticktext", []) or [])
    sparse_tickvals, sparse_ticktext = _compute_sparse_month_ticks(tickvals, ticktext)

    current_margin = figure.layout.margin or {}
    margin_dict = (
        current_margin.to_plotly_json()
        if hasattr(current_margin, "to_plotly_json")
        else {}
    )
    figure.update_layout(
        showlegend=False,
        bargap=0.12,
        uniformtext={"mode": "hide", "minsize": bar_label_size},
        margin={**margin_dict, "t": max(int(getattr(current_margin, "t", 0) or 0), 70)},
    )
    yaxis_range = [0.0, bar_max * 1.08] if bar_max > 0 else None
    yaxis2_range = [0.0, line_max * 1.12] if line_max > 0 else None
    figure.update_layout(
        yaxis={
            **(
                figure.layout.yaxis.to_plotly_json()
                if figure.layout.yaxis is not None
                else {}
            ),
            "visible": False,
            "showticklabels": False,
            "showgrid": False,
            "rangemode": "tozero",
            "range": yaxis_range,
        },
        yaxis2={
            **(
                figure.layout.yaxis2.to_plotly_json()
                if figure.layout.yaxis2 is not None
                else {}
            ),
            "overlaying": "y",
            "side": "right",
            "visible": False,
            "showticklabels": False,
            "showgrid": False,
            "rangemode": "tozero",
            "range": yaxis2_range,
        },
    )
    figure.update_xaxes(
        tickmode="array",
        tickvals=sparse_tickvals,
        ticktext=sparse_ticktext,
        tickangle=0,
        automargin=True,
    )
    period_count = max(
        len(tickvals),
        len(list(getattr(bar_traces[0], "x", []) or [])),
    )
    current_width = int(getattr(figure.layout, "width", 0) or 0)
    left_margin = max(int(getattr(current_margin, "l", 0) or 0), 80)
    right_margin = max(int(getattr(current_margin, "r", 0) or 0), 120)
    min_width_by_periods = left_margin + right_margin + (period_count * 28)
    target_width = max(current_width, min_width_by_periods, 1000)
    figure.update_layout(
        margin={**margin_dict, "r": right_margin, "l": left_margin},
        width=target_width,
    )
    return figure


def build_pipeline_stacked_column(
    df: pl.DataFrame,
    dimension: str,
    metric_column: str,
    period_column: str,
    *,
    palette: str | None = None,
) -> go.Figure:
    """Build a stacked-column chart using the legacy charting module."""
    naming = get_naming_params()
    if df.is_empty():
        raise ValueError("No data to plot.")

    lf = ensure_lazyframe(df)
    cols, _ = get_schema_and_column_names(lf)
    for required in (dimension, metric_column, period_column):
        if required not in cols:
            raise ValueError(
                f"Missing required column for stacked column chart: {required}"
            )

    top_items = _select_top_items(
        lf,
        dimension,
        metric_column,
        max_keep=_AUTO_MAX_KEEP_X,
    )
    if not top_items:
        raise ValueError("No data to plot.")

    top_set = set(top_items)
    df_plot = ensure_polars_df(lf).with_columns(
        [
            pl.col(dimension).cast(pl.Utf8).fill_null("N/A").alias(dimension),
            pl.col(period_column).cast(pl.Utf8).alias(period_column),
            pl.col(metric_column).cast(pl.Float64).fill_null(0.0).alias(metric_column),
        ]
    )

    unique_count = int(df_plot.select(pl.col(dimension).n_unique()).item())
    aggregate_other = unique_count > len(top_items)
    if aggregate_other:
        other_label = "Other"
        has_existing_other = any(
            str(item).strip().lower() == "other" for item in top_items
        )
        if has_existing_other:
            other_label = "Other (aggregated)"
        df_plot = (
            df_plot.with_columns(
                pl.when(pl.col(dimension).is_in(list(top_set)))
                .then(pl.col(dimension))
                .otherwise(pl.lit(other_label))
                .alias(dimension)
            )
            .group_by([period_column, dimension])
            .agg(pl.col(metric_column).sum().alias(metric_column))
        )
        value_columns = [*top_items, other_label]
    else:
        value_columns = top_items

    deduped_value_columns: list[str] = []
    seen_value_columns: set[str] = set()
    for value in value_columns:
        label = str(value).strip()
        if not label:
            continue
        key = label.lower()
        if key in seen_value_columns:
            continue
        seen_value_columns.add(key)
        deduped_value_columns.append(label)
    value_columns = deduped_value_columns

    periods = (
        df_plot.select(pl.col(period_column).drop_nulls().unique().sort())
        .to_series()
        .to_list()
    )
    if not periods:
        raise ValueError("No periods to plot.")

    df_wide = (
        df_plot.group_by([period_column, dimension])
        .agg(pl.col(metric_column).sum().alias(metric_column))
        .pivot(
            values=metric_column,
            index=period_column,
            on=dimension,
            aggregate_function="sum",
        )
        .sort(period_column)
        .fill_null(0.0)
        .rename({period_column: naming["periodName"]})
    )
    if df_wide.is_empty():
        raise ValueError("No data to plot.")

    present_cols = set(df_wide.columns)
    value_cols = [col for col in value_columns if col in present_cols]
    if not value_cols:
        raise ValueError("No data to plot.")

    chart_dict = {
        naming["chosenChart"]: naming["stackedColumnChart"],
        naming["selectedPeriods"]: [str(period) for period in periods],
        naming["plotValuesAsChoice"]: naming["absolute"],
        naming["showLegend"]: naming["showLegendOnTop"],
        naming["xAxisDimension"]: naming["periodName"],
        naming["yAxisDimension"]: dimension,
        naming["singleMetric"]: metric_column,
        naming["xAxisMetric"]: metric_column,
        naming["yAxisMetric"]: metric_column,
        naming["stackedColumnMetric"]: metric_column,
        naming["plotSmallMultiplesOtherCharts"]: False,
        naming["datePeriodName"]: naming["monthName"],
        naming["showCAGR"]: False,
        naming["showMetricsInDataColumn"]: False,
    }
    normalized_palette = _normalize_palette_name(palette, naming)
    if normalized_palette:
        chart_dict[naming["colorpalette"]] = normalized_palette
    color_dict = get_color_dictionary(chart_dict)
    colors = list(get_color_array(color_dict, chart_dict))
    if len(colors) < len(value_cols):
        repeats = (len(value_cols) + len(colors) - 1) // len(colors)
        colors = (colors * repeats)[: len(value_cols)]

    figure, _negative_df, _message, _chart_dict = stacked_bar_width_plot(
        ensure_lazyframe(df_wide),
        chart_dict,
        {},
        value_cols,
        width_col=None,
        colors=colors,
    )
    if not isinstance(figure, go.Figure):
        raise ValueError("No data to plot.")
    return _style_integrated_labels(
        figure,
        display_in_millions=(metric_column == "sales"),
    )


def build_pipeline_stacked_column_overlay(
    df: pl.DataFrame,
    bar_metric_column: str,
    line_metric_column: str,
    period_column: str,
    *,
    palette: str | None = None,
) -> go.Figure:
    """Build a total stacked-column chart with an overlaid line metric."""
    naming = get_naming_params()
    if df.is_empty():
        raise ValueError("No data to plot.")

    lf = ensure_lazyframe(df)
    cols, _ = get_schema_and_column_names(lf)
    for required in (bar_metric_column, line_metric_column, period_column):
        if required not in cols:
            raise ValueError(
                f"Missing required column for stacked column chart: {required}"
            )

    period_name = naming["periodName"]
    total_name = naming["totalName"]
    count_name = naming["countName"]
    df_plot = (
        ensure_polars_df(lf)
        .with_columns(
            [
                pl.col(period_column).cast(pl.Utf8).alias(period_name),
                pl.col(bar_metric_column)
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(total_name),
                pl.col(line_metric_column)
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(line_metric_column),
            ]
        )
        .group_by(period_name)
        .agg(
            [
                pl.col(total_name).sum().alias(total_name),
                pl.col(line_metric_column).sum().alias(line_metric_column),
            ]
        )
        .sort(period_name)
    )
    if df_plot.is_empty():
        raise ValueError("No data to plot.")

    periods = df_plot.get_column(period_name).to_list()
    overlay_df = df_plot.select([period_name, line_metric_column]).lazy()
    df_main = df_plot.select([period_name, total_name]).with_columns(
        pl.lit(1.0).alias(count_name)
    )
    chart_dict = {
        naming["chosenChart"]: naming["stackedColumnChart"],
        naming["selectedPeriods"]: [str(period) for period in periods],
        naming["plotValuesAsChoice"]: naming["absolute"],
        naming["showLegend"]: naming["showLegendOnTop"],
        naming["xAxisDimension"]: period_name,
        naming["yAxisDimension"]: total_name,
        naming["singleMetric"]: bar_metric_column,
        naming["xAxisMetric"]: bar_metric_column,
        naming["yAxisMetric"]: bar_metric_column,
        naming["stackedColumnMetric"]: bar_metric_column,
        naming["plotSmallMultiplesOtherCharts"]: False,
        naming["datePeriodName"]: naming["monthName"],
        naming["showCAGR"]: False,
        naming["showMetricsInDataColumn"]: False,
        naming["metricsToPlot"]: [bar_metric_column, line_metric_column],
        naming["overlayChartMetric"]: line_metric_column,
        naming["overlayChartDf"]: overlay_df,
    }
    normalized_palette = _normalize_palette_name(palette, naming)
    if normalized_palette:
        chart_dict[naming["colorpalette"]] = normalized_palette
    color_dict = get_color_dictionary(chart_dict)
    colors = list(get_color_array(color_dict, chart_dict))
    if not colors:
        colors = ["#343434", "#2563eb"]
    line_color = (
        BAIN_HIGHLIGHT_COLOR
        if normalized_palette == naming["bainColorpalette"]
        else "#2563eb"
    )

    figure, _negative_df, _message, _chart_dict = stacked_bar_width_plot(
        ensure_lazyframe(df_main),
        chart_dict,
        {},
        [total_name],
        width_col=None,
        colors=colors,
    )
    if not isinstance(figure, go.Figure):
        raise ValueError("No data to plot.")
    return _style_combo_labels(figure, line_color=line_color)
