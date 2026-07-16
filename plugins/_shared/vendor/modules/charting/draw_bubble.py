import copy
import logging
import math
import re

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from modules.charting.chart_primitives import (
    get_color_array,
    get_color_dictionary,
    get_hightlight_color,
    millify,
)
from modules.charting.draw_charts_utils import get_polars_value_at_index
from modules.charting.polars_helpers import unique_values_lazy
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    duplicate_dataframe,
    unique,
)
from modules.utilities.ui_notifier import ui
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_schema_and_column_names,
)


def add_split_lines(fig):
    fig.add_hline(
        y=0.5,
        opacity=1,
        line_width=0.5,
        line_color="lightgrey",
        yref="y domain",
    )
    fig.add_vline(
        x=0.5,
        opacity=1,
        line_width=0.5,
        line_color="lightgrey",
        xref="x domain",
    )
    return fig


def _safe_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _bubble_axis_range(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        padding = max(abs(minimum) * 0.1, 1.0)
        return minimum - padding, maximum + padding
    minimum_multiplier = 1.1 if minimum < 0 else 0.9
    maximum_multiplier = 1.1
    return minimum * minimum_multiplier, maximum * maximum_multiplier


def _estimate_text_box(text: str, font_size: int | float) -> tuple[float, float]:
    label = str(text or "")
    longest_line = max(label.split("<br>") or [""], key=len)
    width = max(24.0, len(longest_line) * float(font_size) * 0.58)
    height = max(14.0, (label.count("<br>") + 1) * float(font_size) * 1.25)
    return width, height


def _boxes_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    padding: float = 3.0,
) -> bool:
    return not (
        left[2] + padding <= right[0]
        or right[2] + padding <= left[0]
        or left[3] + padding <= right[1]
        or right[3] + padding <= left[1]
    )


def _bubble_text_box(
    x_px: float,
    y_px: float,
    x_shift: float,
    y_shift: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    center_x = x_px + x_shift
    center_y = y_px + y_shift
    return (
        center_x - (width / 2),
        center_y - (height / 2),
        center_x + (width / 2),
        center_y + (height / 2),
    )


def _bubble_label_candidates(
    label_width: float,
    radius_px: float,
) -> list[tuple[int, int]]:
    gap = max(radius_px + 10.0, 14.0)
    side_gap = max(radius_px + (label_width / 2) + 8.0, 28.0)
    return [
        (0, int(round(gap))),
        (-int(round(label_width * 0.35)), int(round(gap + 10))),
        (int(round(label_width * 0.35)), int(round(gap + 10))),
        (-int(round(side_gap)), 0),
        (int(round(side_gap)), 0),
        (0, -int(round(gap))),
        (-int(round(label_width * 0.35)), -int(round(gap + 10))),
        (int(round(label_width * 0.35)), -int(round(gap + 10))),
    ]


def _is_aggregate_other_label(value: object) -> bool:
    label = str(value or "").strip().lower()
    return label.startswith("other rank >") or label.startswith("others rank >")


def _metric_tokens(metric: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(metric or "").lower()))


def _configured_non_summable_metrics() -> set[str]:
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    metric_groups = [
        namingParams["noSumMetricsArray"],
        namingParams["growthMetricArray"],
        namingParams["percentMetricsArray"],
        namingParams["priceMetricsArray"],
    ]
    return {
        str(metric).strip().lower()
        for group in metric_groups
        for metric in metricArrayParams[group]
    }


def _axis_metric_is_non_summable(metric: object, chartDict: dict) -> bool:
    # Total bubble coordinates are averages, so the marker is only meaningful
    # when both plotted axes are non-additive metrics.
    metric_label = str(metric or "").strip().lower()
    if metric_label in _configured_non_summable_metrics():
        return True
    namingParams = get_naming_params()
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    if metric_label in {
        str(item).strip().lower() for item in chartDict.get(countMetricsAvgArray, [])
    }:
        return True
    tokens = _metric_tokens(metric)
    return bool(
        tokens
        & {
            "avg",
            "average",
            "change",
            "coverage",
            "cwd",
            "distribution",
            "growth",
            "index",
            "pct",
            "percent",
            "percentage",
            "price",
            "rate",
            "ratio",
            "share",
            "variance",
        }
    )


def _can_plot_total_bubble(chartDict: dict) -> bool:
    namingParams = get_naming_params()
    plotTotalBubble = namingParams["plotTotalBubble"]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    if not chartDict.get(plotTotalBubble, False):
        return False
    return _axis_metric_is_non_summable(
        chartDict[xAxisMetric], chartDict
    ) and _axis_metric_is_non_summable(chartDict[yAxisMetric], chartDict)


def _select_bubble_label_positions(
    rows: list[dict[str, object]],
    *,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    size_ref: float | bool | None,
    font_size: int | float,
    show_label: bool,
    show_value: bool,
    plot_width: int = 900,
    plot_height: int = 600,
    collision_padding: float = 3.0,
    allowed_edge_overflow: float = 24.0,
) -> dict[int, tuple[int, int]]:
    """Select readable bubble labels using mechanically verifiable box overlap."""

    x_span = max(x_range[1] - x_range[0], 1.0)
    y_span = max(y_range[1] - y_range[0], 1.0)
    numeric_size_ref = (
        float(size_ref)
        if isinstance(size_ref, (int, float)) and math.isfinite(float(size_ref))
        else 0.0
    )
    size_values = [
        row["size_float"]
        for row in rows
        if isinstance(row.get("size_float"), (int, float))
    ]
    size_min = min(size_values) if size_values else 0.0
    size_span = max((max(size_values) - size_min) if size_values else 0.0, 1.0)

    scored_rows: list[tuple[float, int, dict[str, object]]] = []
    for order, row in enumerate(rows):
        x_float = row.get("x_float")
        y_float = row.get("y_float")
        size_float = row.get("size_float")
        if not isinstance(x_float, (int, float)) or not isinstance(
            y_float, (int, float)
        ):
            continue
        x_norm = (float(x_float) - x_range[0]) / x_span
        y_norm = (float(y_float) - y_range[0]) / y_span
        size_norm = (
            (float(size_float) - size_min) / size_span
            if isinstance(size_float, (int, float))
            else 0.0
        )
        edge_score = abs(x_norm - 0.5) + abs(y_norm - 0.5)
        aggregate_other_bonus = (
            4.0 if _is_aggregate_other_label(row.get("label")) else 0.0
        )
        score = (size_norm * 2.0) + (edge_score * 0.65) + aggregate_other_bonus
        scored_rows.append((score, -order, row))

    occupied: list[tuple[float, float, float, float]] = []
    selected: dict[int, tuple[int, int]] = {}
    for _score, _order, row in sorted(scored_rows, reverse=True):
        label_text = str(row.get("label", ""))
        value_text = str(row.get("value", ""))
        primary_text = label_text if show_label else value_text
        if not primary_text:
            continue

        x_float = float(row["x_float"])
        y_float = float(row["y_float"])
        x_px = ((x_float - x_range[0]) / x_span) * plot_width
        y_px = ((y_float - y_range[0]) / y_span) * plot_height
        label_width, label_height = _estimate_text_box(primary_text, font_size)
        value_width, value_height = _estimate_text_box(value_text, font_size)
        size_float = row.get("size_float")
        radius_px = 0.0
        if numeric_size_ref > 0 and isinstance(size_float, (int, float)):
            radius_px = max(
                2.0, math.sqrt(max(float(size_float), 0.0) / numeric_size_ref) / 2.0
            )

        if show_label:
            candidates = _bubble_label_candidates(label_width, radius_px)
        else:
            candidates = [(0, 0)]

        for x_shift, y_shift in candidates:
            candidate_boxes: list[tuple[float, float, float, float]] = []
            if show_value and value_text:
                candidate_boxes.append(
                    _bubble_text_box(x_px, y_px, 0, 0, value_width, value_height)
                )
            if show_label and label_text:
                candidate_boxes.append(
                    _bubble_text_box(
                        x_px,
                        y_px,
                        x_shift,
                        y_shift,
                        label_width,
                        label_height,
                    )
                )
            if not candidate_boxes:
                continue
            if any(
                box[0] < -allowed_edge_overflow
                or box[1] < -allowed_edge_overflow
                or box[2] > plot_width + allowed_edge_overflow
                or box[3] > plot_height + allowed_edge_overflow
                for box in candidate_boxes
            ):
                continue
            if any(
                _boxes_overlap(
                    candidate_box,
                    placed_box,
                    padding=collision_padding,
                )
                for candidate_box in candidate_boxes
                for placed_box in occupied
            ):
                continue
            row_index = row.get("row_index")
            if isinstance(row_index, int):
                selected[row_index] = (x_shift, y_shift)
                occupied.extend(candidate_boxes)
            break

    return selected


def _bubble_axis_average(
    df: pl.DataFrame | pl.LazyFrame,
    x_dimension: str,
    y_dimension: str,
) -> tuple[float | None, float | None]:
    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    if x_dimension not in columns or y_dimension not in columns:
        return None, None
    rows = (
        lf.select(
            pl.col(x_dimension).cast(pl.Float64, strict=False).mean().alias("x_avg"),
            pl.col(y_dimension).cast(pl.Float64, strict=False).mean().alias("y_avg"),
        )
        .collect(engine="streaming")
        .to_dicts()
    )
    if not rows:
        return None, None
    return _safe_float(rows[0]["x_avg"]), _safe_float(rows[0]["y_avg"])


def start_bubble_axes_from_zero(
    fig: go.Figure,
    df: pl.DataFrame | pl.LazyFrame,
    column: str,
    chartDict: dict,
    countRows: int,
    countCols: int,
) -> go.Figure:
    """Adjust axis ranges for bubble charts with LazyFrame support."""
    namingParams = get_naming_params()
    startAxesFromZero = namingParams["startAxesFromZero"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    totalName = namingParams["totalName"]
    minXDimensionKey = namingParams["minXDimension"]
    maxXDimensionKey = namingParams["maxXDimension"]
    minYDimensionKey = namingParams["minYDimension"]
    maxYDimensionKey = namingParams["maxYDimension"]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    yTitleText = None
    xTitleText = None
    if countRows == 1 and countCols == 1:
        yTitleText = yDimension
        xTitleText = xDimension
    if startAxesFromZero in chartDict and chartDict[startAxesFromZero]:
        row_arg = countRows if getattr(fig, "_grid_ref", None) is not None else None
        col_arg = countCols if getattr(fig, "_grid_ref", None) is not None else None
        fig.update_xaxes(
            title_text=xTitleText, rangemode="tozero", row=row_arg, col=col_arg
        )
        fig.update_yaxes(
            title_text=yTitleText, rangemode="tozero", row=row_arg, col=col_arg
        )
    else:
        lf = ensure_lazyframe(df)
        min_max = (
            lf.select(
                pl.col(xDimension).min().alias("min_x"),
                pl.col(xDimension).max().alias("max_x"),
                pl.col(yDimension).min().alias("min_y"),
                pl.col(yDimension).max().alias("max_y"),
            )
            .collect(engine="streaming")
            .to_dicts()[0]
        )
        minXDimension = min_max["min_x"]
        maxXDimension = min_max["max_x"]
        minYDimension = min_max["min_y"]
        maxYDimension = min_max["max_y"]
        if minXDimension is None:
            minXDimension = chartDict.get(minXDimensionKey, 0)
        if maxXDimension is None:
            maxXDimension = chartDict.get(maxXDimensionKey, 0)
        if minYDimension is None:
            minYDimension = chartDict.get(minYDimensionKey, 0)
        if maxYDimension is None:
            maxYDimension = chartDict.get(maxYDimensionKey, 0)
        minXMultiplier, maxXMultiplier = 0.9, 1.1
        minYMultiplier, maxYMultiplier = 0.9, 1.1
        if minXDimension < 0:
            minXMultiplier = 1.1
        if minYDimension < 0:
            minYMultiplier = 1.1
        if maxXDimension < 0:
            maxXMultiplier = 1.1
        if maxYDimension < 0:
            maxYMultiplier = 1.1
        row_arg = countRows if getattr(fig, "_grid_ref", None) is not None else None
        col_arg = countCols if getattr(fig, "_grid_ref", None) is not None else None
        fig.update_xaxes(
            title_text=xTitleText,
            range=[minXDimension * minXMultiplier, maxXDimension * maxXMultiplier],
            rangemode="normal",
            row=row_arg,
            col=col_arg,
        )
        fig.update_yaxes(
            title_text=yTitleText,
            range=[minYDimension * minYMultiplier, maxYDimension * maxYMultiplier],
            rangemode="normal",
            row=row_arg,
            col=col_arg,
        )
    return fig


def draw_motion_chart(df, paramDict, periodOrder, chartDict):
    """Actually draw a motion chart.

    Accepts both :class:`polars.DataFrame` and :class:`polars.LazyFrame` and
    performs most operations lazily, collecting only when necessary.
    """
    df_lazy = ensure_lazyframe(df)
    namingParams = get_naming_params()
    configParams = get_config_params()
    font = configParams[namingParams["fontChoice"]]
    fontSize = configParams[namingParams["fontSizeText"]]
    annotationDict = configParams[namingParams["annotationDict"]]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    xAxisDimension = namingParams["xAxisDimension"]
    yAxisDimension = namingParams["yAxisDimension"]
    bubbleSize = namingParams["bubbleSize"]
    totalName = namingParams["totalName"]
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    selectedPeriods = namingParams["selectedPeriods"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    chosenChart = namingParams["chosenChart"]
    labelColor = namingParams["labelColor"]
    blackLabelChoice = namingParams["blackLabelChoice"]
    whiteLabelChoice = namingParams["whiteLabelChoice"]
    greyLabelChoice = namingParams["greyLabelChoice"]
    showBubbleLabel = namingParams["showBubbleLabel"]
    showBoth = namingParams["showBoth"]
    showLabelsOnly = namingParams["showLabelsOnly"]
    showNothing = namingParams["showNothing"]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    chosenChart = chartDict[chosenChart]
    periodOrder = chartDict[selectedPeriods]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    bubbleSizeDimension = chartDict[bubbleSize]
    chosenDimension = chartDict[xAxisDimension]
    bubbleColorDimension = chartDict[yAxisDimension]
    if chartDict[plotValuesAsChoice] == absolute:
        chartFormat = ",.3s"
    else:
        chartFormat = ",.0f"

    for element in [bubbleSizeDimension, xDimension, yDimension]:
        df_lazy = df_lazy.with_columns(
            pl.when(pl.col(element) <= 0)
            .then(0)
            .otherwise(pl.col(element))
            .alias(element)
        )

    other_name = namingParams["otherName"]
    undefined_name = namingParams["undefinedName"]
    highlighted_dimension = namingParams["highlightedDimension"]
    highlight_color = get_hightlight_color(chartDict, colorDict)

    unique_colors = unique_values_lazy(bubbleColorDimension, df_lazy)

    for i, val in enumerate(unique_colors):
        if val in [other_name, undefined_name] or (
            isinstance(val, str) and other_name.lower() in val.lower()
        ):
            if i < len(colorArray):
                colorArray[i] = colorDict["veryLightGreyColor"]
        elif (
            highlighted_dimension in chartDict
            and val in chartDict[highlighted_dimension]
        ):
            if i < len(colorArray):
                colorArray[i] = highlight_color

    min_max = (
        df_lazy.select(
            pl.col(xDimension).min().alias("min_x"),
            pl.col(xDimension).max().alias("max_x"),
            pl.col(yDimension).min().alias("min_y"),
            pl.col(yDimension).max().alias("max_y"),
        )
        .collect(engine="streaming")
        .to_dicts()[0]
    )
    min_x, max_x, min_y, max_y = (
        min_max["min_x"],
        min_max["max_x"],
        min_max["min_y"],
        min_max["max_y"],
    )
    rangeX = [min_x * 0.8, max_x * 1.2]
    rangeY = [min_y * 0.8, max_y * 1.2]

    unique_dates = unique_values_lazy(dateName, df_lazy)

    color_map = {
        val: colorArray[i % len(colorArray)] for i, val in enumerate(unique_colors)
    }

    max_size = (
        df_lazy.select(pl.col(bubbleSizeDimension).max())
        .collect(engine="streaming")
        .item()
    )

    mode = "markers+text" if chartDict[showBubbleLabel] != showNothing else "markers"

    frames = []
    for date in unique_dates:
        df_frame = (
            df_lazy.filter(pl.col(dateName) == date)
            .select(
                xDimension,
                yDimension,
                bubbleSizeDimension,
                chosenDimension,
                bubbleColorDimension,
            )
            .collect(engine="streaming")
        )
        frames.append(
            go.Frame(
                data=[
                    go.Scatter(
                        x=df_frame[xDimension].to_list(),
                        y=df_frame[yDimension].to_list(),
                        mode=mode,
                        text=(
                            df_frame[chosenDimension].to_list()
                            if chartDict[showBubbleLabel] != showNothing
                            else None
                        ),
                        marker=dict(
                            size=df_frame[bubbleSizeDimension].to_list(),
                            color=[
                                color_map[val]
                                for val in df_frame[bubbleColorDimension].to_list()
                            ],
                            sizemode="area",
                            sizeref=2.0 * max_size / (70.0**2),
                            sizemin=4,
                            opacity=0.8,
                        ),
                        hovertext=df_frame[chosenDimension].to_list(),
                        showlegend=False,
                    )
                ],
                name=str(date),
            )
        )

    fig = go.Figure(data=frames[0].data if frames else [], frames=frames)
    fig.update_xaxes(range=rangeX)
    fig.update_yaxes(range=rangeY)
    fig.for_each_trace(
        lambda t: t.update(
            textfont_color=colorDict["blackColor"], textposition="top center"
        )
    )
    df_full = df_lazy.collect()
    rangeArray = range(df_full.height)
    fig = add_split_lines(fig)
    if chartDict[showBubbleLabel] != showNothing:
        for element in rangeArray:
            if bubbleColorDimension == periodName:
                if df_full[bubbleColorDimension][element] in [plName, fcName]:
                    color = colorDict["blackColor"]
                elif df_full[bubbleColorDimension][element] == periodOrder[0]:
                    color = colorDict["blackColor"]
                else:
                    color = colorDict["whiteColor"]
            text = df_full[chosenDimension][element]
            bubbleValue = millify(df_full[bubbleSizeDimension][element], 1)
            bubbleLabel = str(df_full[chosenDimension][element])
            if chartDict[showBubbleLabel] == showLabelsOnly:
                bubbleText = bubbleLabel
            elif chartDict[showBubbleLabel] == showValuesOnly:
                bubbleText = bubbleValue
            else:
                bubbleText = bubbleLabel + "<br>" + bubbleValue
    return fig


def add_labels_and_values_to_bubbles(
    fig, df, chartDict, colorDict, sizeRef, countRows, countCols
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    font = configParams[namingParams["fontChoice"]]
    fontSize = configParams[namingParams["fontSizeText"]]
    bubbleSize = namingParams["bubbleSize"]
    adjustBubbleLabels = namingParams["adjustBubbleLabels"]
    showBoth = namingParams["showBoth"]
    showLabelsOnly = namingParams["showLabelsOnly"]
    showValuesOnly = namingParams["showValuesOnly"]
    showNothing = namingParams["showNothing"]
    showBubbleLabel = namingParams["showBubbleLabel"]
    xAxisDimension = namingParams["xAxisDimension"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    scaledSize = namingParams["scaledSizeName"]
    bubbleSizeDimension = chartDict[bubbleSize]
    chosenDimension = chartDict[xAxisDimension]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    label_mode = chartDict[showBubbleLabel]
    if label_mode == showNothing:
        return fig
    show_label = label_mode in [showBoth, showLabelsOnly]
    show_value = label_mode in [showBoth, showValuesOnly]
    lf = (
        ensure_lazyframe(df)
        .sort(xDimension, descending=True)
        .with_row_index("_idx")
        .with_columns(
            ((pl.col(bubbleSizeDimension) / sizeRef / 100) + 100).alias(scaledSize)
        )
        .with_columns((pl.col(scaledSize) / 100).alias(scaledSize))
        .with_columns(((pl.len() < 6).cast(pl.Int64)).alias("__round"))
        .select(
            pl.col("_idx"),
            pl.col(xDimension).alias("__x"),
            pl.col(yDimension).alias("__y"),
            pl.col(scaledSize).alias("__scale"),
            pl.col(bubbleSizeDimension).alias("__size"),
            pl.struct([pl.col(bubbleSizeDimension), pl.col("__round")])
            .map_elements(
                lambda s: millify(s[bubbleSizeDimension], s["__round"]),
                return_dtype=pl.Utf8,
            )
            .alias("__value"),
            pl.col(chosenDimension).cast(pl.Utf8).alias("__label"),
        )
    )

    ann_df = lf.collect(engine="streaming")

    rows: list[dict[str, object]] = []
    x_values: list[float] = []
    y_values: list[float] = []
    for row in ann_df.iter_rows(named=True):
        x_float = _safe_float(row["__x"])
        y_float = _safe_float(row["__y"])
        size_float = _safe_float(row["__size"])
        if x_float is not None:
            x_values.append(x_float)
        if y_float is not None:
            y_values.append(y_float)
        rows.append(
            {
                "row_index": int(row["_idx"]),
                "value": row["__value"],
                "label": row["__label"],
                "x": row["__x"],
                "y": row["__y"],
                "scale": row["__scale"],
                "x_float": x_float,
                "y_float": y_float,
                "size_float": size_float,
            }
        )

    if chartDict[adjustBubbleLabels]:
        selected_positions = _select_bubble_label_positions(
            rows,
            x_range=_bubble_axis_range(x_values),
            y_range=_bubble_axis_range(y_values),
            size_ref=sizeRef,
            font_size=fontSize,
            show_label=show_label,
            show_value=show_value,
        )
    else:
        selected_positions = {
            row["row_index"]: (0, 0)
            for row in rows
            if isinstance(row.get("row_index"), int)
        }

    for row in rows:
        row_index = row["row_index"]
        if not isinstance(row_index, int) or row_index not in selected_positions:
            continue
        if show_value:
            fig.add_annotation(
                text=row["value"],
                showarrow=False,
                align="center",
                yshift=0,
                y=row["y"],
                yref="y",
                x=row["x"],
                ax=0,
                xref="x",
                font=dict(size=fontSize, color=colorDict["blackColor"], family=font),
                row=countRows,
                col=countCols,
            )
        if show_label and chartDict[adjustBubbleLabels]:
            x_shift, y_shift = selected_positions[row_index]
            fig.add_annotation(
                text=row["label"],
                showarrow=False,
                align="center",
                yshift=y_shift,
                xshift=x_shift,
                y=row["y"],
                yref="y",
                x=row["x"],
                ax=0,
                xref="x",
                font=dict(size=fontSize, color=colorDict["blackColor"], family=font),
                row=countRows,
                col=countCols,
            )
    return fig


def add_legend_title_to_bubble_chart(
    fig, plotLegend, chartDict, colorDict, countRows, countCols
):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    bubbleColorDimension = chartDict[yAxisDimension]
    if plotLegend:
        fig.add_annotation(
            text=bubbleColorDimension,
            showarrow=False,
            x=1.1,
            y=1.03,
            xref="paper",
            yref="paper",
            font=dict(
                color=colorDict["blackColor"],
            ),
        )
    return fig


def get_colors_for_bubble(
    fig,
    df,
    column,
    chartDict,
    colorDimensionArray,
    countCols,
    countRows,
    aggregateOtherItemsName,
    colorArray,
):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    totalName = namingParams["totalName"]
    notMetConditionValue = namingParams["notMetConditionValue"]

    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    chosenDimension = chartDict[xAxisDimension]
    bubbleColorDimension = chartDict[yAxisDimension]

    lf = ensure_lazyframe(df)

    plotLegend = True
    if column == totalName:
        if bubbleColorDimension in [None, nothingFilteredName, notMetConditionValue]:
            colorDimensionArray = [0]
            lf = lf.with_columns(pl.lit(0).alias(bubbleColorDimension))
            plotLegend = False
        elif chosenDimension == bubbleColorDimension:
            colorDimensionArray = unique_values_lazy(bubbleColorDimension, lf)
            plotLegend = False
        else:
            colorDimensionArray = unique_values_lazy(bubbleColorDimension, lf)
    else:
        if bubbleColorDimension in [None, nothingFilteredName]:
            lf = lf.with_columns(pl.lit(0).alias(bubbleColorDimension))
            plotLegend = False
        elif (
            chosenDimension == bubbleColorDimension
            and chosenDimension != smallMultiplesColumn
        ):
            plotLegend = False
            if countCols == 1 and countRows == 1:
                plotLegend = True
        elif bubbleColorDimension == smallMultiplesColumn:
            chartDict[yAxisDimension] = nothingFilteredName
            colorDimensionArray = [0]
            lf = lf.with_columns(pl.lit(0).alias(chartDict[yAxisDimension]))
            plotLegend = False
        elif bubbleColorDimension != smallMultiplesColumn:
            plotLegend = False
            if countCols == 1 and countRows == 1:
                plotLegend = True
        else:
            pass

    if bubbleColorDimension in [None, nothingFilteredName]:
        lf = lf.with_columns(
            pl.when(pl.col(chosenDimension) == aggregateOtherItemsName)
            .then(1)
            .otherwise(pl.col(bubbleColorDimension))
            .alias(bubbleColorDimension)
        )
        plotLegend = False
        if len(colorDimensionArray) == 1:
            colorDimensionArray.append(1)
            colorDict = get_color_dictionary(chartDict)
            colorArray.insert(1, colorDict["veryLightGreyColor"])

    df_out = ensure_polars_df(lf)
    return df_out, colorDimensionArray, plotLegend, colorArray, chartDict


def color_other_bubbles_in_grey(
    df: pl.DataFrame | pl.LazyFrame,
    colorArray: list[str],
    bubbleColorDimension: str,
    colorDict: dict,
    chartDict: dict,
) -> list[str]:
    """Update ``colorArray`` for special bubble colors lazily."""
    namingParams = get_naming_params()
    otherName = namingParams["otherName"]
    undefinedName = namingParams["undefinedName"]
    highlightedDimension = namingParams["highlightedDimension"]
    highlightColor = get_hightlight_color(chartDict, colorDict)
    columns, _ = get_schema_and_column_names(df)
    if bubbleColorDimension in columns:
        lf = ensure_lazyframe(df)
        bubbleColorArray = unique_values_lazy(bubbleColorDimension, lf)
        count = 0
        for element in bubbleColorArray:
            if element in [otherName, undefinedName] or (
                isinstance(element, str) and otherName.lower() in element.lower()
            ):
                colorArray[count] = colorDict["veryLightGreyColor"]
            elif (
                highlightedDimension in chartDict
                and element in chartDict[highlightedDimension]
            ):
                colorArray[count] = highlightColor
            count += 1
    return colorArray


def add_total_bubble_to_bubble_chart(
    fig, df, chartDict, dfTotals, sizeRef, countRows, countCols
):
    namingParams = get_naming_params()
    plotTotalBubble = namingParams["plotTotalBubble"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    bubbleSize = namingParams["bubbleSize"]
    totalName = namingParams["totalName"]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    bubbleSizeDimension = chartDict[bubbleSize]
    df_lazy_totals = ensure_lazyframe(dfTotals)
    totals_columns, _ = get_schema_and_column_names(df_lazy_totals)
    has_totals = bubbleSizeDimension in totals_columns and (
        df_lazy_totals.select([bubbleSizeDimension])
        .head(1)
        .collect(engine="streaming")
        .height
        > 0
    )
    if _can_plot_total_bubble(chartDict) and has_totals:
        xTotal, yTotal = _bubble_axis_average(df, xDimension, yDimension)
        if xTotal is None and xDimension in totals_columns:
            xTotal = get_polars_value_at_index(df_lazy_totals, xDimension, 0)
        if yTotal is None and yDimension in totals_columns:
            yTotal = get_polars_value_at_index(df_lazy_totals, yDimension, 0)
        sizeTotal = get_polars_value_at_index(df_lazy_totals, bubbleSizeDimension, 0)
        if xTotal is None or yTotal is None or _safe_float(sizeTotal) is None:
            return fig
        fig.add_trace(
            go.Scatter(
                x=[xTotal],
                y=[yTotal],
                mode="markers",
                marker=dict(
                    size=[sizeTotal],
                    color="rgba(0,0,0,0)",
                    line=dict(
                        color="Red",
                        width=1,
                    ),
                    sizemode="area",
                    sizeref=sizeRef,
                    sizemin=4,
                    opacity=1,
                ),
                showlegend=False,  # do not show this in the legend
            ),
            row=countRows,
            col=countCols,
        )
        totalBubbleValue = millify(sizeTotal, 1)
        fig.add_annotation(
            text=totalName + ": " + str(totalBubbleValue),
            showarrow=False,
            align="center",
            yshift=0,
            y=yTotal,
            yref="y",
            x=xTotal,
            ax=0,
            xref="x",
            font=dict(
                size=10,
                color="Red",
            ),
            row=countRows,
            col=countCols,
        )
    return fig


def add_bubbles_to_bubble_chart(
    fig,
    df,
    plotLegend,
    chartDict,
    colorArray,
    colorDimensionArray,
    sizeRef,
    countRows,
    countCols,
):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    bubbleSize = namingParams["bubbleSize"]
    xAxisDimension = namingParams["xAxisDimension"]
    adjustBubbleLabels = namingParams["adjustBubbleLabels"]
    bubbleSizeDimension = chartDict[bubbleSize]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    chosenDimension = chartDict[xAxisDimension]
    bubbleColorDimension = chartDict[yAxisDimension]
    countColors = 0
    for item in colorDimensionArray:
        if (
            xDimension is not None
            and not isinstance(xDimension, bool)
            and yDimension is not None
            and not isinstance(yDimension, bool)
        ):
            # Polars-style row filtering; ensure eager DataFrame for plotting
            dfFiltered = ensure_lazyframe(df).filter(
                pl.col(bubbleColorDimension) == item
            )
            dfFiltered = ensure_polars_df(dfFiltered)
            bubbleLabel = dfFiltered[chosenDimension]
            mode = "markers+text"
            if chartDict[adjustBubbleLabels]:
                bubbleLabel = False
                mode = "markers"
            fig.add_trace(
                go.Scatter(
                    x=dfFiltered[xDimension],
                    y=dfFiltered[yDimension],
                    mode=mode,
                    textposition="top center",
                    marker=dict(
                        size=dfFiltered[bubbleSizeDimension],
                        color=colorArray[countColors],
                        sizemode="area",
                        sizeref=sizeRef,
                        sizemin=4,
                        opacity=0.1,
                    ),
                    text=bubbleLabel,  # this will appear when you hover over a point
                    showlegend=False,  # do not show this in the legend
                ),
                row=countRows,
                col=countCols,
            )
            dfCopy = duplicate_dataframe(dfFiltered)
            dfCopy_df = ensure_polars_df(dfCopy)
            if dfCopy_df.height == 0 and plotLegend:
                empty_df = pl.DataFrame(
                    {
                        xDimension: [None],
                        yDimension: [None],
                        bubbleSizeDimension: [1],
                    }
                )
                dfCopy = pl.concat([ensure_lazyframe(dfCopy), empty_df.lazy()])
                dfCopy_df = empty_df
            else:
                dfCopy = ensure_lazyframe(dfCopy)
            fig.add_trace(
                go.Scatter(
                    x=dfCopy_df[xDimension],
                    y=dfCopy_df[yDimension],
                    mode="markers",
                    marker=dict(
                        size=dfCopy_df[bubbleSizeDimension],
                        color="rgba(0,0,0,0)",  # transparent color
                        line=dict(color=colorArray[countColors], width=2.5),
                        sizemode="area",
                        sizeref=sizeRef,
                        sizemin=4,
                    ),
                    name=item,
                    showlegend=plotLegend,
                ),
                row=countRows,
                col=countCols,
            )
            countColors = countColors + 1
    return fig


def get_size_def_for_bubbles(df, sizeRef, chartDict, column, count):
    namingParams = get_naming_params()
    bubbleSize = namingParams["bubbleSize"]
    totalName = namingParams["totalName"]
    bubbleSizeDimension = chartDict[bubbleSize]
    lf = ensure_lazyframe(df)
    try:
        max_size = (
            lf.select(pl.col(bubbleSizeDimension).max())
            .collect(engine="streaming")
            .item()
        )
    except Exception as e:
        logging.exception(e)
        ui.error("Something went wrong while computing bubble max size.")
        max_size = None
    if max_size is None:
        return False
    if column == totalName:
        return 2.0 * max_size / (40.0**2)
    return 2 * max_size / (40.0**2)


def draw_bubble_chart(
    fig,
    df,
    colorDimensionArray,
    plotLegend,
    chartDict,
    colorDict,
    colorArray,
    dfTotals,
    column,
    count,
    countRows,
    countCols,
    sizeRef,
):
    """
    actually draws bubble chart
    """
    sizeRef = get_size_def_for_bubbles(df, sizeRef, chartDict, column, count)
    fig = add_bubbles_to_bubble_chart(
        fig,
        df,
        plotLegend,
        chartDict,
        colorArray,
        colorDimensionArray,
        sizeRef,
        countRows,
        countCols,
    )
    fig = add_total_bubble_to_bubble_chart(
        fig, df, chartDict, dfTotals, sizeRef, countRows, countCols
    )
    fig = add_labels_and_values_to_bubbles(
        fig, df, chartDict, colorDict, sizeRef, countRows, countCols
    )
    fig = add_legend_title_to_bubble_chart(
        fig, plotLegend, chartDict, colorDict, countRows, countCols
    )
    fig = start_bubble_axes_from_zero(fig, df, column, chartDict, countRows, countCols)
    fig = add_split_lines(fig)
    return fig, sizeRef
