import copy
import logging
import math

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_primitives import (
    get_color_dictionary,
    millify_dataframe,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import drop_columns, duplicate_dataframe, unique
from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names


def get_data_for_pareto_prompt(
    df,
    metric,
    ratioName,
    classArray,
    closestRankArray,
    closestIndexArray,
    col,
    chartDict,
):
    """Return arrays for Pareto chart annotations."""
    namingParams = get_naming_params()
    countRank = namingParams["countRank"]
    plotCommentText = namingParams["plotCommentText"]
    countColumn = namingParams["countColumn"]
    plotConcentrationText = namingParams["plotConcentrationText"]
    className = namingParams["className"]
    showRank = namingParams["showRank"]

    lf = ensure_lazyframe(df).sort(countRank, descending=True).with_row_index("row_nr")

    def _row_from_class(value: str, *, ascending: bool = False) -> pl.LazyFrame:
        return (
            lf.filter(pl.col(className) == value)
            .sort(ratioName, descending=not ascending)
            .select("row_nr", countRank, ratioName)
            .limit(1)
        )

    def _row_from_target(target: float) -> pl.LazyFrame:
        return (
            lf.with_columns((pl.col(ratioName) - target).abs().alias("diff"))
            .sort("diff")
            .select("row_nr", countRank, ratioName)
            .limit(1)
        )

    if col > 1 and closestRankArray:
        rows = [
            lf.filter(pl.col(countRank) == rank)
            .select("row_nr", countRank, ratioName)
            .limit(1)
            for rank in closestRankArray
        ]
    else:
        rows = [_row_from_target(t) for t in (0.8, 0.95, 1.0)]

    if len(rows) > 0:
        info = (
            pl.concat(rows)
            .select(
                pl.col("row_nr").cast(pl.Int64).implode().alias("row_nr"),
                pl.col(countRank).cast(pl.Int64).implode().alias("rank"),
                pl.col(ratioName).cast(pl.Float64).implode().alias("ratio"),
            )
            .collect(engine="streaming")
        )
        closestIndexArray = [int(v) for v in info["row_nr"][0]]
        closestRankArray = [int(v) for v in info["rank"][0]]
        ratios = [float(v) for v in info["ratio"][0]]
    else:
        ratios = []

    percentAMetric = int(ratios[0] * 100)
    percentBMetric = int(ratios[1] * 100)
    percentCMetric = int(ratios[2] * 100)
    percentAMetricString = str(percentAMetric) + "%"
    percentBMetricString = str(percentBMetric) + "%"
    percentCMetricString = str(percentCMetric) + "%"

    percentACount = (
        "(" + str(int((closestRankArray[0] / closestRankArray[2] * 100))) + "%)"
    )
    percentBCount = (
        "(" + str(int((closestRankArray[1] / closestRankArray[2] * 100))) + "%)"
    )
    percentCCount = (
        "(" + str(int((closestRankArray[2] / closestRankArray[2] * 100))) + "%)"
    )
    promptPercentACount = (
        "("
        + str(int((closestRankArray[0] / closestRankArray[2] * 100)))
        + "% of the total number of "
        + chartDict[countColumn]
        + "s )"
    )
    promptPercentBCount = (
        "("
        + str(int((closestRankArray[1] / closestRankArray[2] * 100)))
        + "% of the total number of "
        + chartDict[countColumn]
        + "s )"
    )
    promptPercentCCount = (
        "("
        + str(int((closestRankArray[2] / closestRankArray[2] * 100)))
        + "% of the total number of "
        + chartDict[countColumn]
        + "s )"
    )

    messageA = f"{closestRankArray[0]} {percentACount} {chartDict[countColumn]}s for {percentAMetricString} of {metric}"
    messageB = f"{closestRankArray[1]} {percentBCount} {chartDict[countColumn]}s for {percentBMetricString} of {metric}"
    messageC = f"{closestRankArray[2]} {chartDict[countColumn]}s for {percentCMetricString} of {metric}"
    messageArray = [messageA, messageB, messageC]
    percentArray = [0.80, 0.95, 1]
    promptMessageA = f"{closestRankArray[0]} {chartDict[countColumn]}s {promptPercentACount} make up {percentAMetricString} of total {metric}"
    promptMessageB = f"{closestRankArray[1]} {chartDict[countColumn]}s {promptPercentBCount} make up {percentBMetricString} of total {metric}"
    promptMessageC = f"{closestRankArray[2]} {chartDict[countColumn]}s {promptPercentCCount} make up {percentCMetricString} of {metric}"
    promptMessage = promptMessageA + ", " + promptMessageB + " and " + promptMessageC

    chartDict[plotCommentText].append(promptMessage)
    if col == 1:
        if int(closestRankArray[0] / closestRankArray[2] * 100) < 20:
            message = "'intense'."
        elif int(closestRankArray[0] / closestRankArray[2] * 100) < 30:
            message = "'typical'."
        elif int(closestRankArray[0] / closestRankArray[2] * 100) < 40:
            message = "'moderate'."
        else:
            message = "'weak'."
        message = """Consider this """ + metric + """ concentration """ + message
        chartDict[plotConcentrationText] = message

    return messageArray, closestRankArray, closestIndexArray, percentArray, chartDict


def add_annotations_to_pareto(
    fig,
    closestRankArray,
    closestIndexArray,
    messageArray,
    percentArray,
    classArray,
    col,
    chartDict,
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    paretoChart = namingParams["paretoChart"]
    showRank = namingParams["showRank"]
    offset = 0.02
    if showRank in chartDict and not chartDict[showRank]:
        closestRankArray = copy.deepcopy(closestIndexArray)
    fig.add_shape(
        type="line",
        x0=0,
        y0=closestRankArray[0],
        x1=percentArray[0],
        y1=closestRankArray[0],
        line=dict(color="Black", width=1, dash="dot"),
        xref="x",
        yref="y",
        row=1,
        col=col,
    )
    fig.add_shape(
        type="line",
        x0=0,
        y0=closestRankArray[1],
        x1=percentArray[1],
        y1=closestRankArray[1],
        line=dict(color="Black", width=1, dash="dot"),
        xref="x",
        yref="y",
        row=1,
        col=col,
    )
    fig.add_shape(
        type="line",
        x0=0,
        y0=closestRankArray[2],
        y1=closestRankArray[2],
        # y0="Labels",
        # y1="Labels",
        # y0=closestIndexArray[2],
        # y1=closestIndexArray[2],
        x1=percentArray[2],
        line=dict(color="Black", width=1, dash="dot"),
        xref="x",
        yref="y",
        row=1,
        col=col,
    )
    # Add annotation for the dashed line
    fig.add_annotation(
        x=percentArray[0] - offset,
        y=closestRankArray[0],
        text=messageArray[0],
        showarrow=False,  # Set to True if you want an arrow pointing to the line
        xref="x",
        yref="y",
        xanchor="right",
        yanchor="bottom",  # Anchor the text to the bottom of the label, center it horizontally
        font=dict(color="Black", size=fontSize),
        row=1,
        col=col,
    )
    fig.add_annotation(
        x=percentArray[1] - offset,
        y=closestRankArray[1],
        text=messageArray[1],
        showarrow=False,  # Set to True if you want an arrow pointing to the line
        xref="x",
        yref="y",
        xanchor="right",
        yanchor="bottom",  # Anchor the text to the bottom of the label, center it horizontally
        font=dict(color="Black", size=fontSize),
        row=1,
        col=col,
    )
    fig.add_annotation(
        x=percentArray[2] - offset,
        y=closestRankArray[2],
        text=messageArray[2],
        showarrow=False,  # Set to True if you want an arrow pointing to the line
        xref="x",
        yref="y",
        xanchor="right",
        yanchor="bottom",  # Anchor the text to the bottom of the label, center it horizontally
        font=dict(color="Black", size=fontSize),
        row=1,
        col=col,
    )
    if len(closestRankArray) == 4:
        fig.add_shape(
            type="line",
            x0=0,
            y0=closestRankArray[3],
            x1=percentArray[3],
            y1=closestRankArray[3],
            line=dict(color="Black", width=1, dash="dot"),
            xref="x",
            yref="y",
            row=1,
            col=col,
        )
        fig.add_annotation(
            x=percentArray[3] - offset,
            y=closestRankArray[3],
            text=messageArray[3],
            showarrow=False,  # Set to True if you want an arrow pointing to the line
            xref="x",
            yref="y",
            xanchor="right",
            yanchor="bottom",  # Anchor the text to the bottom of the label, center it horizontally
            font=dict(color="Black", size=fontSize),
            row=1,
            col=col,
        )
    return fig


def _should_render_pareto_threshold_annotations(
    df_height: int,
    pareto_chart_many_items: int,
    show_only_value: str,
    show_all_value: str,
) -> bool:
    """Return whether Pareto threshold labels should draw for the display mode."""

    return show_only_value == show_all_value


def _pareto_bar_color_list(
    df: pl.LazyFrame,
    *,
    metric: str,
    col: int,
    base_color_name: str,
    hyphen_name: str,
    fallback: list[str],
) -> list[str]:
    """Return row-level Pareto bar colors when the prepared color column exists."""

    color_column = (
        f"{base_color_name}{hyphen_name}{metric}" if col > 1 else base_color_name
    )
    columns, _ = get_schema_and_column_names(df)
    if color_column not in columns:
        return fallback
    return df.select(pl.col(color_column)).collect().get_column(color_column).to_list()


def _pareto_item_tick_axis_update(
    df: pl.LazyFrame,
    *,
    dimension_column: str | None,
    tick_values: list[object],
    df_height: int,
    max_visible_item_labels: int,
) -> dict[str, object]:
    """Return a y-axis tick update that avoids dense unreadable item labels."""

    columns, _ = get_schema_and_column_names(df)
    if dimension_column not in columns:
        return {}
    if df_height > max_visible_item_labels:
        return {"tickmode": "array", "tickvals": [], "ticktext": []}
    tick_text = (
        df.select(pl.col(dimension_column).cast(pl.Utf8))
        .collect()
        .get_column(dimension_column)
        .to_list()
    )
    return {"tickmode": "array", "tickvals": tick_values, "ticktext": tick_text}


def _pareto_class_trace_coordinates(
    df: pl.LazyFrame,
    *,
    ratio_column: str,
    class_column: str,
    class_value: str,
    y_values: list[object],
) -> tuple[list[object], list[object]]:
    """Return x/y coordinates for one Pareto class without connecting gaps."""

    columns, _ = get_schema_and_column_names(df)
    if ratio_column not in columns or class_column not in columns:
        return [], []

    rows = (
        df.select(
            pl.col(ratio_column).alias("__ratio"),
            pl.col(class_column).alias("__class"),
        )
        .with_row_index("__row_nr")
        .collect()
        .iter_rows(named=True)
    )
    trace_x: list[object] = []
    trace_y: list[object] = []
    previous_row: int | None = None
    for row in rows:
        row_number = int(row["__row_nr"])
        if row["__class"] != class_value:
            continue
        if row_number >= len(y_values):
            continue
        if previous_row is not None and row_number != previous_row + 1:
            trace_x.append(None)
            trace_y.append(None)
        trace_x.append(row["__ratio"])
        trace_y.append(y_values[row_number])
        previous_row = row_number
    return trace_x, trace_y


def adjust_negative_metrics_lazy(
    df: pl.LazyFrame,
    *,
    metric: str,
    ratio_name: str,
    class_name: str,
    hyphen_name: str,
    value_name: str,
    opposite_sign: str,
    loss_class_name: str,
    negative_class_name: str,
) -> pl.LazyFrame:
    """Adjust metrics when their total is negative.

    The transformation mirrors the in-line logic previously in
    ``draw_pareto_chart`` but is split out for readability.
    """

    df = df.with_columns(
        (pl.col(metric + hyphen_name + value_name) * pl.col(metric)).alias(
            opposite_sign
        )
    )

    df = df.with_columns(
        pl.when(pl.col(opposite_sign) < 0)
        .then(-pl.col(metric))
        .otherwise(pl.col(metric))
        .alias(metric)
    )

    df = df.with_columns(
        (pl.col(metric + hyphen_name + value_name) * pl.col(ratio_name)).alias(
            opposite_sign
        )
    )

    df = df.with_columns(
        pl.when((pl.col(opposite_sign) < 0) & (pl.col(class_name) != loss_class_name))
        .then(-pl.col(ratio_name))
        .otherwise(pl.col(ratio_name))
        .alias(ratio_name)
    )

    df = df.with_columns(
        pl.when((pl.col(ratio_name) < 0) & (pl.col(class_name) == loss_class_name))
        .then(-pl.col(ratio_name))
        .otherwise(pl.col(ratio_name))
        .alias(ratio_name)
    )

    df = df.with_columns(
        pl.when(
            (pl.col(opposite_sign) < 0) & (pl.col(class_name) != negative_class_name)
        )
        .then(-pl.col(ratio_name))
        .otherwise(pl.col(ratio_name))
        .alias(ratio_name)
    )

    df = df.with_columns(
        pl.when((pl.col(ratio_name) < 0) & (pl.col(class_name) == negative_class_name))
        .then(-pl.col(ratio_name))
        .otherwise(pl.col(ratio_name))
        .alias(ratio_name)
    )

    return drop_columns(df, [opposite_sign])


def draw_pareto_chart(
    dfCopy,
    dfFull,
    metric,
    colorList,
    classColorDict,
    closestRankArray,
    closestIndexArray,
    chartDict,
    paramDict,
    fig,
    col,
):
    """Return Pareto chart elements.

    Both ``dfCopy`` and ``dfFull`` must be provided as ``pl.LazyFrame`` objects.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    workColumn = namingParams["workColumn"]
    ratioName = namingParams["ratioName"]
    className = namingParams["className"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]
    showRank = namingParams["showRank"]
    countRank = namingParams["countRank"]
    valueName = namingParams["valueName"]
    lossClassName = namingParams["lossClassName"]
    negativeClassName = namingParams["negativeClassName"]
    oppositeSign = namingParams["oppositeSign"]
    countColumn = namingParams["countColumn"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    showOnly = namingParams["showOnly"]
    showAll = namingParams["showAll"]
    paretoChartManyItems = configParams["paretoChartManyItems"]
    colorDict = get_color_dictionary(chartDict)
    almostBlackColor = colorDict["almostBlackColor"]
    greyColor = colorDict["greyColor"]
    lightGreyColor = colorDict["lightGreyColor"]
    blueColor = colorDict["blueColor"]
    hyphenName = namingParams["hyphenName"]
    plotCommentText = namingParams["plotCommentText"]
    df = duplicate_dataframe(dfCopy).with_columns(
        pl.col(metric).alias(f"{metric}{hyphenName}{valueName}"),
        (pl.col(metric) / dfFull.select(pl.col(metric).sum()).collect().item()).alias(
            metric
        ),
    )
    dfFull = dfFull.with_columns((pl.col(metric) / pl.col(metric).sum()).alias(metric))
    if col == 1:
        if (
            df.select(pl.col(metric + hyphenName + valueName).sum()).collect().item()
            < 0
        ):
            df = adjust_negative_metrics_lazy(
                df,
                metric=metric,
                ratio_name=ratioName,
                class_name=className,
                hyphen_name=hyphenName,
                value_name=valueName,
                opposite_sign=oppositeSign,
                loss_class_name=lossClassName,
                negative_class_name=negativeClassName,
            )
    else:
        df = df.with_columns(
            (pl.col(metric + hyphenName + valueName) * pl.col(metric)).alias(
                oppositeSign
            )
        )
        df = df.with_columns(
            pl.when(pl.col(oppositeSign) < 0)
            .then(-pl.col(metric))
            .otherwise(pl.col(metric))
            .alias(metric)
        )
    df_height = df.select(pl.len()).collect().item()
    if df_height <= paretoChartManyItems:
        if not chartDict[showAbsoluteValues]:
            y = df.select(pl.col(metric)).collect().get_column(metric)
            df, chartDict = millify_dataframe(df, metric, None, labelName, chartDict)
            textposition = "outside"
        else:
            col_name = metric + hyphenName + valueName
            y = df.select(pl.col(col_name)).collect().get_column(col_name)
            df, chartDict = millify_dataframe(df, col_name, None, labelName, chartDict)
            textposition = "outside"
        negative_exists = df.select((pl.col(metric) < 0).any()).collect().item()
        if negative_exists:
            textposition = "auto"
        showYTicklabels = False
        df, chartDict = millify_dataframe(df, ratioName, None, workColumn, chartDict)
        textpositionPercent = "bottom left"
        modePercent = "text+lines"
        bargap = 0.3
        barText = df.select(pl.col(labelName)).collect().get_column(labelName)
        lineText = df.select(pl.col(workColumn)).collect().get_column(workColumn)
    else:
        if not chartDict[showAbsoluteValues]:
            y = df.select(pl.col(metric)).collect().get_column(metric)
        else:
            y = (
                df.select(pl.col(metric + hyphenName + valueName))
                .collect()
                .get_column(metric + hyphenName + valueName)
            )
        textposition = None
        showYTicklabels = True
        customdataPercent = None
        textpositionPercent = None
        modePercent = "lines"
        bargap = 0
        barText = None
        lineText = None
    if chartDict[showRank]:
        x = df.select(pl.col(countRank)).collect().get_column(countRank)
    else:
        x = (
            df.select(pl.int_range(0, pl.len()).alias("idx"))
            .collect()
            .get_column("idx")
        )
        y_axis_update = _pareto_item_tick_axis_update(
            df,
            dimension_column=chartDict.get(countColumn),
            tick_values=x.to_list(),
            df_height=df_height,
            max_visible_item_labels=paretoChartManyItems,
        )
        if y_axis_update:
            fig.update_yaxes(
                **y_axis_update,
                row=1,
                col=col,
            )
    colorList = _pareto_bar_color_list(
        df,
        metric=metric,
        col=col,
        base_color_name=colorName,
        hyphen_name=hyphenName,
        fallback=colorList,
    )
    fig.add_trace(
        go.Bar(
            y=x,
            x=y,
            xaxis="x1",
            orientation="h",
            marker={"color": colorList},
            name=metric,
            text=barText,
            textposition=textposition,
            cliponaxis=False,
        ),
        row=1,
        col=col,
    )
    if col == 1 and not chartDict[showAbsoluteValues]:
        fig.add_trace(
            go.Scatter(
                y=x,
                x=(df.select(pl.col(ratioName)).collect().get_column(ratioName)),
                xaxis="x2",
                orientation="h",
                name="cumulative ratio",
                hovertemplate="%{x:.1%}",
                text=lineText,
                marker={"color": "lightgrey"},
                textposition=textpositionPercent,
                mode=modePercent,
            ),
            row=1,
            col=col,
        )
    elif not chartDict[showAbsoluteValues]:
        if (
            df.select(pl.col(metric + hyphenName + valueName).sum()).collect().item()
            < 0
        ):
            df = df.sort(ratioName)
            new_ratio_col = ratioName + hyphenName + metric
            className = className + hyphenName + metric
            df = df.with_columns(pl.col(metric).cum_sum().alias(new_ratio_col))
            df = df.sort(countRank, descending=True)
            df = df.with_columns(
                (pl.col(metric + hyphenName + valueName) * pl.col(new_ratio_col)).alias(
                    oppositeSign
                )
            )
            df = drop_columns(df, [oppositeSign])
            ratioName = new_ratio_col
        else:
            df = df.sort(ratioName)
            new_ratio_col = ratioName + hyphenName + metric
            className = className + hyphenName + metric
            df = df.with_columns(pl.col(metric).cum_sum().alias(new_ratio_col))
            df = df.sort(countRank, descending=True)
            ratioName = new_ratio_col
        fig.add_trace(
            go.Scatter(
                y=x,
                x=(df.select(pl.col(ratioName)).collect().get_column(ratioName)),
                xaxis="x2",
                orientation="h",
                name="cumulative ratio",
                hovertext=lineText,
                marker={"color": "lightgrey"},
                text=lineText,
                textposition=textpositionPercent,
                mode=modePercent,
            ),
            row=1,
            col=col,
        )
    for element in classColorDict:
        if not chartDict[showAbsoluteValues]:
            trace_x, trace_y = _pareto_class_trace_coordinates(
                df,
                ratio_column=ratioName,
                class_column=className,
                class_value=element,
                y_values=x.to_list(),
            )
            if not trace_x:
                continue
            fig.add_trace(
                go.Scatter(
                    y=trace_y,
                    x=trace_x,
                    xaxis="x2",
                    name="",
                    line={"color": classColorDict[element]},
                    mode="lines",
                ),
                row=1,
                col=col,
            )
        fig.update_yaxes(
            # autorange="reversed",
            row=1,
            col=2,
        )
    if col:
        classArray = (
            df.select(pl.col(className).unique())
            .collect()
            .get_column(className)
            .to_list()
        )
        messageArray, closestRankArray, closestIndexArray, percentArray, chartDict = (
            get_data_for_pareto_prompt(
                df,
                metric,
                ratioName,
                classArray,
                closestRankArray,
                closestIndexArray,
                col,
                chartDict,
            )
        )
        if _should_render_pareto_threshold_annotations(
            df_height,
            paretoChartManyItems,
            chartDict[showOnly],
            showAll,
        ):
            fig = add_annotations_to_pareto(
                fig,
                closestRankArray,
                closestIndexArray,
                messageArray,
                percentArray,
                classArray,
                col,
                chartDict,
            )
    fig.update_annotations(font=dict(size=fontSize, family=font))
    return fig, showYTicklabels, bargap, closestRankArray, closestIndexArray, chartDict
