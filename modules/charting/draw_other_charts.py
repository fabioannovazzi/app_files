import copy
import datetime as dt
import math
from typing import Any

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_helpers import set_up_tab_for_show_or_download_chart
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    enable_draw_shapes,
    get_color_array,
    get_color_dictionary,
    get_max_and_min_value,
    get_number_prefix,
    get_user_message,
    insert_highlight_color,
    millify_dataframe,
    reset_row_and_column_counters,
    set_other_color_to_grey,
)
from modules.charting.draw_charts_utils import (
    add_cumulated_legends,
    add_labels_to_area_chart,
    get_labels_for_trend_comparison,
    prepare_value_labels_for_timeline,
)
from modules.charting.draw_timeline import add_labels_to_timeline_chart
from modules.charting.make_titles import make_horizontal_waterfall_chart_title
from modules.charting.polars_helpers import to_lists
from modules.charting.setup_fig import (
    add_integrated_legends_to_trend_plot,
    setup_fig_for_actual_vs_previous_year_charts,
)
from modules.charting.update_layouts import update_cy_ac_layout
from modules.data.common_data_utils import (
    clean_column_labels_after_flatten,
    get_cum_sum_dataframe,
    get_month_name,
    order_dataframe_by_month,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import (
    add_empty_dataset_error_message_in_plot_charts_tab,
    add_error_message_in_plot_charts_tab,
)
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    flatten_cols_polars,
    get_periods_array,
    unique,
)
from modules.utilities.utils import (
    ensure_polars_df,
    get_schema_and_column_names,
    is_valid_lazyframe,
)


def adjust_ac_py_plot(
    fig, df, key, metric, title, height, width, paramDict, chartDict, plotWithPins
):
    namingParams = get_naming_params()
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    fig = update_cy_ac_layout(fig, height, width, paramDict, chartDict, plotWithPins)
    fig, message = get_user_message(
        fig, chosenChart, metric, key, paramDict, chartDict, df, width, None
    )
    fig = add_message_as_annotation(
        fig, message, None, chosenChart, chartDict, paramDict
    )
    fig = add_title_as_annotation(fig, title, chosenChart, chartDict)
    fig = enable_draw_shapes(fig)
    return fig


# custom function to set fill color
def fillcol(label, chartDict):
    colorDict = get_color_dictionary(chartDict)
    if label >= 1:
        return colorDict["greenColor"]
    else:
        return colorDict["redColor"]


def draw_cy_ac_plotly(
    fig, df, paramDict, title, countRows, countCols, yArray, chartDict
):
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    labelName = namingParams["labelName"]
    otherLabelName = namingParams["otherLabelName"]
    colorName = namingParams["colorName"]
    timelineChart = namingParams["timelineChart"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    showValueLabelsKey = namingParams["showValueLabels"]
    chosenChart = namingParams["chosenChart"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    plotAsBaselineKey = namingParams["plotAsBaseline"]
    pyName = namingParams["pyName"]
    labelPosition = namingParams["labelPosition"]
    maxValueKey = namingParams["maxValue"]
    minValueKey = namingParams["minValue"]
    plotAsBaseline = notMetConditionValue
    if plotAsBaselineKey in chartDict and chartDict[plotAsBaselineKey]:
        plotAsBaseline = metConditionValue
    chosenChart = chartDict[chosenChart]
    colorDict = get_color_dictionary(chartDict)
    columns, schema = get_schema_and_column_names(df)
    df1 = ensure_polars_df(duplicate_dataframe(df))
    if chosenChart in [trendComparisonByPeriodChart]:
        df1, chartDict = millify_dataframe(df1, maxValueKey, None, labelName, chartDict)
    PYtext = None
    acMode, acMarkerSize, acLineWidth = "markers+lines+text", 10, 2
    showLegend = False
    barWidth = 0.035
    if chosenChart in [trendComparisonChart]:
        acMode, acMarkerSize, acLineWidth = "markers+lines+text", 10, 2
        PYtext = df1[otherLabelName]
        barWidth = 0.1
    df1 = df1.with_columns(pl.lit("top center").alias(labelPosition))
    if plotAsBaseline:
        df1 = df1.with_columns(
            pl.when(pl.col(colorName) == 0)
            .then("bottom center")
            .otherwise(pl.col(labelPosition))
            .alias(labelPosition)
        )

    df_temp = ensure_polars_df(df).with_columns(
        pl.arange(0, pl.len()).alias("__idx"),
        (
            pl.col(colorName).shift().ne(pl.col(colorName)).fill_null(True).cum_sum()
        ).alias("group"),
    )
    dfs = [
        g.sort("__idx").drop("group")
        for _, g in df_temp.group_by("group", maintain_order=True)
    ]
    idx_vals = list(range(df1.height))
    count = 0
    numberOfCicles = dfs.__len__()
    for df in dfs:
        if not plotAsBaseline:
            fig.add_trace(
                go.Scatter(
                    x=idx_vals,
                    y=df1[minValueKey],
                    fill="tozeroy",
                    fillcolor=colorDict["whiteColor"],
                    line=dict(width=0),
                    marker=dict(size=0),
                    mode="none",
                    showlegend=False,
                ),
                row=countRows,
                col=countCols,
            )
        if count == numberOfCicles - 1:
            fig.add_trace(
                go.Scatter(
                    x=idx_vals,
                    y=df1[yArray[0]],
                    line=dict(color=colorDict["almostBlackColor"], width=acLineWidth),
                    marker=dict(
                        size=acMarkerSize,
                        symbol="square",
                        color=colorDict["almostBlackColor"],
                        line=dict(color=colorDict["almostBlackColor"], width=2),
                    ),
                    text=df1[labelName],
                    textposition=df1[labelPosition],
                    # textposition='bottom center',
                    mode=acMode,
                    name=yArray[0],
                    showlegend=showLegend,
                ),
                row=countRows,
                col=countCols,
            )
            pyLineColor = colorDict["almostBlackColor"]
            pyMarkerColor = colorDict["whiteColor"]
            if pyName in columns:
                pyMarkerColor = colorDict["lightGreyColor"]
                pyLineColor = colorDict["lightGreyColor"]
            fig.add_trace(
                go.Scatter(
                    x=idx_vals,
                    y=df1[yArray[1]],
                    line=dict(color=colorDict["greyColor"], dash="dash", width=1),
                    marker=dict(
                        size=acMarkerSize,
                        symbol="square",
                        color=pyMarkerColor,
                        line=dict(color=pyLineColor, width=2),
                    ),
                    text=PYtext,
                    textposition="top center",
                    mode=acMode,
                    name=yArray[1],
                    showlegend=showLegend,
                ),
                row=countRows,
                col=countCols,
            )
        fig.add_trace(
            go.Scatter(
                x=df["__idx"],
                y=df[yArray[0]],
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
            ),
            row=countRows,
            col=countCols,
        )
        fig.add_trace(
            go.Bar(
                x=df["__idx"],
                y=df[minValueKey],
                marker=dict(
                    color=colorDict["whiteColor"],
                ),
                showlegend=False,
                width=barWidth,
            ),
            row=countRows,
            col=countCols,
        )
        fig.add_trace(
            go.Bar(
                x=df["__idx"],
                y=df[maxValueKey] - df[minValueKey],
                marker=dict(color=fillcol(df[colorName][0], chartDict)),
                showlegend=False,
                width=barWidth,
            ),
            row=countRows,
            col=countCols,
        )
        count = count + 1
        showLegend = False
    fig.update_layout(barmode="stack")
    return fig, chartDict


def draw_area_chart(
    dfCopy,
    paramDict,
    chosenDimension,
    metric,
    xColumn,
    chartDict,
    count,
    uniqueItems,
    aggregateOtherItemsName,
):
    """Draw an area chart with aggregation and pivoting handled in Polars."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    labelName = namingParams["labelName"]
    yShiftName = namingParams["yShiftName"]
    xShiftName = namingParams["xShiftName"]
    separatorString = namingParams["separatorString"]
    chosenChart = namingParams["chosenChart"]
    totalName = namingParams["totalName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    showValueLabelsKey = namingParams["showValueLabels"]
    absolute = namingParams["absolute"]
    periodOrder = [False]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    chosenChart = chartDict[chosenChart]
    if len(uniqueItems) > 1:
        dfCopy = dfCopy.with_columns(pl.col(chosenDimension).cast(pl.Categorical)).sort(
            by=[chosenDimension, xColumn]
        )
        colorArray = set_other_color_to_grey(
            uniqueItems, aggregateOtherItemsName, colorArray, chartDict, 0
        )
        colorArray = insert_highlight_color(
            chosenDimension, uniqueItems, colorArray, paramDict, chartDict
        )
    df = duplicate_dataframe(dfCopy)
    numberOfRows = 1
    numberOfCols = 1
    sharedXaxes = "all"
    sharedYaxes = None
    verticalSpacing = 0
    horizontalSpacing = 0
    countRows = 1
    countCols = 1
    subplotTitles = []
    labelArray = []
    yShiftArray = []
    xShiftArray = []
    show_value_labels = True
    if showValueLabelsKey in chartDict:
        show_value_labels = bool(chartDict[showValueLabelsKey])
    hovertemplate = "{text:,.3s}"
    if is_valid_lazyframe(df):
        value_cols = [metric]
        group_cols = [xColumn, chosenDimension]
        df = (
            (df.lazy() if isinstance(df, pl.DataFrame) else df)
            .group_by(group_cols)
            .agg([pl.col(col).sum() for col in value_cols])
            .collect()
            .pivot(
                chosenDimension,
                index=xColumn,
                values=value_cols,
                aggregate_function="sum",
            )
            .sort(xColumn)
        )
        df = flatten_cols_polars(df, "")
        df, newCols = clean_column_labels_after_flatten(df, [metric])
        if uniqueItems:
            max_df = df.select(
                pl.max_horizontal([pl.col(col) for col in uniqueItems])
                .max()
                .alias("maxValue")
            )
            prefix, chartDict, decimals = get_number_prefix(
                max_df.lazy(), "maxValue", chartDict, None
            )
        dropCols = [col for col in uniqueItems if abs(float(df[col].sum())) < 0.0001]
        if dropCols:
            df = drop_columns(df, dropCols)
            uniqueItems = [u for u in uniqueItems if u not in dropCols]
        count = 0
        fig = make_subplots(
            rows=numberOfRows,
            cols=numberOfCols,
            shared_xaxes=sharedXaxes,
            shared_yaxes=sharedYaxes,
            vertical_spacing=verticalSpacing,
            horizontal_spacing=horizontalSpacing,
            subplot_titles=subplotTitles,
        )
        groupnorm = ""
        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] != absolute
        ):
            groupnorm = "percent"
            row_sum = pl.sum_horizontal([pl.col(c) for c in uniqueItems])
            df = df.with_columns(
                [(pl.col(c) / row_sum * 100).round(1).alias(c) for c in uniqueItems]
            )
        dfCumSum = None
        dfNegative = None
        message = None
        if show_value_labels:
            dfCumSum, dfNegative, message = get_cum_sum_dataframe(
                df, chosenChart, [None], ""
            )
        for element in uniqueItems:
            labelArray.append(element + separatorString + labelName)
            yShiftArray.append(element + separatorString + yShiftName)
            xShiftArray.append(element + separatorString + xShiftName)
            fig.add_trace(
                go.Scatter(
                    x=df[xColumn],
                    y=df[uniqueItems[count]].round(1),
                    line=dict(color=colorArray[count]),
                    showlegend=False,
                    mode="lines",
                    hovertext=element,
                    groupnorm=groupnorm,
                    stackgroup="one",
                ),
                row=countRows,
                col=countCols,
            )
            count = count + 1
        if show_value_labels:
            count = 0
            for column in uniqueItems:
                df = prepare_value_labels_for_timeline(
                    df,
                    chosenChart,
                    column,
                    labelArray,
                    yShiftArray,
                    xShiftArray,
                    chartDict,
                    count,
                )
                count = count + 1
            df = df.with_columns(
                pl.sum_horizontal([pl.col(c) for c in uniqueItems]).alias(totalName)
            )
            totalLabelArray = [totalName + separatorString + labelName]
            totalYShiftArray = [totalName + separatorString + yShiftName]
            totalXShiftArray = [totalName + separatorString + xShiftName]
            df = prepare_value_labels_for_timeline(
                df,
                chosenChart,
                totalName,
                totalLabelArray,
                totalYShiftArray,
                totalXShiftArray,
                chartDict,
                0,
            )
            if groupnorm == "percent":
                last_idx = df.height - 1
                df = (
                    df.with_columns(
                        pl.lit(100).alias(totalName),
                        pl.lit("").alias(totalLabelArray[0]),
                        pl.lit(0).alias(totalYShiftArray[0]),
                    )
                    .with_row_index("__idx")
                    .with_columns(
                        pl.when(pl.col("__idx") == last_idx)
                        .then(pl.lit("100%"))
                        .otherwise(pl.col(totalLabelArray[0]))
                        .alias(totalLabelArray[0]),
                        pl.when(pl.col("__idx") == last_idx)
                        .then(0)
                        .otherwise(pl.col(totalYShiftArray[0]))
                        .alias(totalYShiftArray[0]),
                    )
                    .drop("__idx")
                )
            cols, schema = get_schema_and_column_names(df)
            lists = to_lists(df.lazy(), cols)
            fig = add_labels_to_timeline_chart(
                fig,
                df.lazy(),
                element,
                chosenChart,
                totalName,
                lists.get(totalLabelArray[0], []),
                lists.get(totalYShiftArray[0], []),
                lists.get(
                    totalXShiftArray[0], [0] * len(lists.get(totalLabelArray[0], []))
                ),
                countRows,
                countCols,
            )
            count = 0
            for element in labelArray:
                if len(uniqueItems) > 1:
                    fig = add_cumulated_legends(
                        fig,
                        df,
                        dfCumSum,
                        numberOfCols,
                        value_cols,
                        uniqueItems,
                        count,
                        chartDict,
                    )
                    fig = add_labels_to_area_chart(
                        fig,
                        df,
                        dfCumSum,
                        element,
                        uniqueItems,
                        labelArray,
                        yShiftArray,
                        xShiftArray,
                        count,
                        countRows,
                        countCols,
                    )
                count = count + 1
    else:
        paramDict = add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return fig, df


def modify_labels_for_baseline(df, yArray, chartDict):
    namingParams = get_naming_params()
    plotAsBaselineKey = namingParams["plotAsBaseline"]
    hyphenName = namingParams["hyphenName"]
    deltaName = namingParams["deltaName"]
    averageName = namingParams["averageName"]
    compareToAverageKey = namingParams["compareToAverage"]
    if plotAsBaselineKey in chartDict and chartDict[plotAsBaselineKey]:
        if compareToAverageKey in chartDict and chartDict[compareToAverageKey]:
            referencePeriodName = deltaName + averageName
            otherPeriodName = averageName
        # referencePeriodName=yArray[0]+hyphenName+yArray[1]
        else:
            referencePeriodName = deltaName + yArray[1]
            otherPeriodName = yArray[1]
        # Polars: rename with mapping only (no axis argument)
        df = df.rename({yArray[0]: referencePeriodName, yArray[1]: otherPeriodName})
        yArray[0] = referencePeriodName
        yArray[1] = otherPeriodName
    return df, yArray


def modify_dataframe_for_baseline(
    df: pl.DataFrame | pl.LazyFrame,
    yArray: list[str],
    metric: str,
    chartDict: dict[str, Any],
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` modified for baseline comparison."""

    namingParams = get_naming_params()
    plotAsBaselineKey = namingParams["plotAsBaseline"]
    separatorString = namingParams["separatorString"]
    compareToAverageKey = namingParams["compareToAverage"]

    if plotAsBaselineKey in chartDict and chartDict[plotAsBaselineKey]:
        columns, _ = get_schema_and_column_names(df)
        basePeriodName = metric + separatorString + yArray[0]
        otherPeriodName = metric + separatorString + yArray[1]

        use_lazy = isinstance(df, pl.LazyFrame)
        lf = df

        if compareToAverageKey in chartDict and chartDict[compareToAverageKey]:
            lf = lf.with_columns(
                (pl.col(basePeriodName) - pl.col(basePeriodName).mean()).alias(
                    basePeriodName
                ),
                pl.lit(0).alias(otherPeriodName),
            )
        else:
            if basePeriodName in columns and otherPeriodName in columns:
                lf = lf.with_columns(
                    (pl.col(basePeriodName) - pl.col(otherPeriodName)).alias(
                        basePeriodName
                    ),
                    pl.lit(0).alias(otherPeriodName),
                )

        df = lf

    return df


def make_ac_py_difference_dataframe(df, element, chartDict, paramDict):
    """
    we need to make a dataframe in which the values are side by side so we can compute the difference
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    dateName = namingParams["dateName"]
    acpyName = namingParams["acpyName"]
    separatorString = namingParams["separatorString"]
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    labelName = namingParams["labelName"]
    otherLabelName = namingParams["otherLabelName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    colorName = namingParams["colorName"]
    filterDates = namingParams["filterDates"]
    timelineChart = namingParams["timelineChart"]
    areaChart = namingParams["areaChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    differenceInValue = namingParams["differenceInValue"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    renameDict = {
        "Last 52": "Year",
        "Last 26": "Semester",
        "Last 13": "Quarter",
        "Last 4": "Month",
    }
    periodOrder = ["Year", "Semester", "Quarter", "Month"]
    yArray = []
    keepCols, colorMetric, indexMetric = (
        [periodName, acpyName, element],
        acpyName,
        periodName,
    )
    if chosenChart in [trendComparisonChart, multitierColumnChart]:
        keepCols, colorMetric, indexMetric = (
            [dateName, periodName, element],
            periodName,
            dateName,
        )
        df = get_month_name(df)
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    frame = (
        lf.select(keepCols)
        .group_by([indexMetric, colorMetric])
        .agg(pl.col(element).sum())
    )
    pivot_values = [acName, pyName, plName]
    exprs = [
        pl.when(pl.col(colorMetric) == val)
        .then(pl.col(element))
        .otherwise(0)
        .sum()
        .alias(f"{element}_{val}")
        for val in pivot_values
    ]
    frame = frame.group_by(indexMetric).agg(exprs)

    df = frame
    if chosenChart in [
        trendComparisonChart
    ]:  # and filterDates in chartDict and chartDict[filterDates]:
        if filterDates in chartDict and chartDict[filterDates]:
            yArray = [acName, plName]
        else:
            yArray = [acName, pyName]
        df = modify_dataframe_for_baseline(df, yArray, element, chartDict)
        df, periodsArray = get_max_and_min_value(
            df, element, chartDict, paramDict, yArray
        )
        df = df.sort(dateName)
        df = order_dataframe_by_month(df, paramDict, True, yArray)
        df, chartDict = get_labels_for_trend_comparison(df, yArray, element, chartDict)
        keepCols = yArray + [minValue, maxValue, labelName, otherLabelName, colorName]
        df = df.select(keepCols)
    else:
        yArray = [acName, pyName]
        columns, schema = get_schema_and_column_names(df)
        df, periodsArray = get_max_and_min_value(
            df, element, chartDict, paramDict, yArray
        )
        df = df.with_columns(
            pl.col(acName).cast(pl.Utf8).alias(labelName),
            pl.col(periodName).replace(renameDict).alias(periodName),
        )
        order_map = {val: idx for idx, val in enumerate(periodOrder)}
        # Polars: use replace with mapping, then cast to integer for ordering
        df = (
            df.with_columns(
                pl.col(periodName).replace(order_map).cast(pl.Int32).alias("_order")
            )
            .sort("_order")
            .drop("_order")
        )
        keepCols = yArray + [minValue, maxValue, labelName, colorName]
        df = df.select(keepCols)

    if isinstance(df, pl.LazyFrame):
        df = df.collect(engine="streaming")
    return df, yArray, chartDict


def make_difference_dataframe_and_draw_plot(
    dfCopy,
    element,
    fig,
    paramDict,
    count,
    countCols,
    countRows,
    numberOfCols,
    numberOfRows,
    height,
    chartDict,
    uniqueItems,
    metricArray,
):
    """
    putting functions together
    """
    namingParams = get_naming_params()
    trendComparisonChart = namingParams["trendComparisonChart"]
    dateName = namingParams["dateName"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    chosenChart = namingParams["chosenChart"]
    periodName = namingParams["periodName"]
    chosenChart = chartDict[chosenChart]
    df = duplicate_dataframe(dfCopy)
    df, yArray, chartDict = make_ac_py_difference_dataframe(
        df, element, chartDict, paramDict
    )
    if chosenChart in [trendComparisonChart, trendComparisonByPeriodChart]:
        df, yArray = modify_labels_for_baseline(df, yArray, chartDict)
        fig, chartDict = draw_cy_ac_plotly(
            fig, df, paramDict, element, countRows, countCols, yArray, chartDict
        )
        fig = add_integrated_legends_to_trend_plot(
            fig, df, countRows, countCols, yArray
        )
    totalHeight = height * (countRows)
    count, countRows, countCols, chartDict = reset_row_and_column_counters(
        count, countCols, countRows, numberOfCols, numberOfRows, chartDict
    )
    return fig, count, countRows, countCols, totalHeight, chartDict, df


def draw_actual_vs_previous_year_chart(
    dfCopy, chosenDimension, metricArray, repeatArray, paramDict, chartDict
):
    """
    in order to show green where it goes better and red where worse, e need to build a dataframe
    with the differences
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    numberOfPlots = namingParams["numberOfPlots"]
    chosenChart = namingParams["chosenChart"]
    periodName = namingParams["periodName"]
    plName = namingParams["plName"]
    pyName = namingParams["pyName"]
    acName = namingParams["acName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    canPlotYearToYearKey = namingParams["canPlotYearToYear"]
    setTimePeriodTabLabel = namingParams["setTimePeriodTabLabel"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    chosenChart = chartDict[chosenChart]
    configPlotlyDict = configParams["configPlotlyDict"]
    configPlotlyDict = configPlotlyDict[chosenChart]
    exportDataArray = []
    key = None
    canPlotYearToYear = True
    plotWithPins = False
    numberOfMetrics = len(metricArray)
    if chosenDimension == None and numberOfMetrics == 1:
        plotWithPins = True
    if canPlotYearToYearKey in chartDict:
        canPlotYearToYear = chartDict[canPlotYearToYearKey]
    if is_valid_lazyframe(dfCopy) and canPlotYearToYear:
        repeatArrayToPlot = []
        for element in repeatArray:
            repeatArrayToPlot.append(element)
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            fig, height, width, numberOfCols, numberOfRows = (
                setup_fig_for_actual_vs_previous_year_charts(
                    repeatArrayToPlot,
                    chosenDimension,
                    paramDict,
                    chartDict,
                    plotWithPins,
                )
            )
        count, countRows, countCols = 1, 1, 1
        columns, schema = get_schema_and_column_names(dfCopy)
        if chosenDimension in columns:
            paramDict[numberOfPlots] = len(repeatArray)
            # fullFig=False
            # metricType=False
            # same scale does not work here because Other Rank > is plotted as last
            for column in repeatArray:
                df = duplicate_dataframe(dfCopy)
                periodsArray = get_periods_array(df)
                df = df.filter(pl.col(chosenDimension) == column)
                if plName in periodsArray:
                    pyName = plName
                df = drop_columns(df, [chosenDimension])
                for metric in metricArray:
                    if (
                        plotSmallMultiplesKey not in chartDict
                        or not chartDict[plotSmallMultiplesKey]
                    ):
                        fig, height, width, numberOfCols, numberOfRows = (
                            setup_fig_for_actual_vs_previous_year_charts(
                                repeatArrayToPlot,
                                chosenDimension,
                                paramDict,
                                chartDict,
                                plotWithPins,
                            )
                        )
                    fig, count, countRows, countCols, totalHeight, chartDict, df = (
                        make_difference_dataframe_and_draw_plot(
                            df,
                            metric,
                            fig,
                            paramDict,
                            count,
                            countCols,
                            countRows,
                            numberOfCols,
                            numberOfRows,
                            height,
                            chartDict,
                            repeatArray,
                            metricArray,
                        )
                    )
                    exportDataArray.append(df)
                    fig.update_annotations(font=dict(size=fontSize, family=font))
                    if (
                        plotSmallMultiplesKey not in chartDict
                        or not chartDict[plotSmallMultiplesKey]
                    ):
                        key = chosenDimension + column
                        titleColumn = chosenDimension + ": " + column
                        title, paramDict, chartDict = (
                            make_horizontal_waterfall_chart_title(
                                df,
                                chosenChart,
                                paramDict,
                                titleColumn,
                                metric,
                                chartDict,
                                pyName,
                                acName,
                            )
                        )
                        # fig,fullFig,metricType=keep_same_scale_for_all_plots(fig,metric,metricType,fullFig,"Y")
                        # same scale does not work here because Other Rank > is plotted as last
                        fig = adjust_ac_py_plot(
                            fig,
                            dfCopy,
                            key,
                            metric,
                            title,
                            height,
                            width,
                            paramDict,
                            chartDict,
                            plotWithPins,
                        )
                        paramDict = set_up_tab_for_show_or_download_chart(
                            df,
                            fig,
                            configPlotlyDict,
                            chartDict,
                            chosenDimension + metric,
                            False,
                            None,
                            chosenDimension,
                            paramDict,
                        )
        else:
            paramDict[numberOfPlots] = len(metricArray)
            periodsArray = dfCopy[periodName].unique().to_list()
            if plName in periodsArray:
                pyName = plName
            for metric in metricArray:
                df = duplicate_dataframe(dfCopy)
                if (
                    plotSmallMultiplesKey not in chartDict
                    or not chartDict[plotSmallMultiplesKey]
                ):
                    fig, height, width, numberOfCols, numberOfRows = (
                        setup_fig_for_actual_vs_previous_year_charts(
                            repeatArrayToPlot,
                            chosenDimension,
                            paramDict,
                            chartDict,
                            plotWithPins,
                        )
                    )
                fig, count, countRows, countCols, totalHeight, chartDict, df = (
                    make_difference_dataframe_and_draw_plot(
                        df,
                        metric,
                        fig,
                        paramDict,
                        count,
                        countCols,
                        countRows,
                        numberOfCols,
                        numberOfRows,
                        height,
                        chartDict,
                        repeatArrayToPlot,
                        metricArray,
                    )
                )
                fig.update_annotations(font=dict(size=fontSize, family=font))
                if (
                    plotSmallMultiplesKey not in chartDict
                    or not chartDict[plotSmallMultiplesKey]
                ):
                    title, paramDict, chartDict = make_horizontal_waterfall_chart_title(
                        df,
                        chosenChart,
                        paramDict,
                        "",
                        metric,
                        chartDict,
                        pyName,
                        acName,
                    )
                    fig = adjust_ac_py_plot(
                        fig,
                        df,
                        key,
                        metric,
                        title,
                        height,
                        width,
                        paramDict,
                        chartDict,
                        plotWithPins,
                    )
                    key = metric
                    if chosenDimension:
                        key = chosenDimension + metric
                    paramDict = set_up_tab_for_show_or_download_chart(
                        df,
                        fig,
                        configPlotlyDict,
                        chartDict,
                        key,
                        False,
                        None,
                        chosenDimension,
                        paramDict,
                    )
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            key = chosenDimension
            title, paramDict, chartDict = make_horizontal_waterfall_chart_title(
                dfCopy, chosenChart, paramDict, key, metric, chartDict, pyName, acName
            )
            fig = adjust_ac_py_plot(
                fig,
                dfCopy,
                key,
                metric,
                title,
                height,
                width,
                paramDict,
                chartDict,
                plotWithPins,
            )
            key = metric
            if chosenDimension:
                key = chosenDimension + metric
                chartDict[selectDimensionsToPlot] = chosenDimension
                if len(exportDataArray) > 1:
                    df = pl.concat(exportDataArray, how="vertical")
            paramDict = set_up_tab_for_show_or_download_chart(
                df,
                fig,
                configPlotlyDict,
                chartDict,
                key,
                False,
                None,
                chosenDimension,
                paramDict,
            )
    elif not canPlotYearToYear:
        message = (
            chosenChart
            + " must be plotted over 12 months and the most recent month in dataset is not December. Set 'Compare with period to date' to 'False' and 'Compare with rolling period' to 'True' in the "
            + setTimePeriodTabLabel
            + " tab."
        )
        paramDict = add_error_message_in_plot_charts_tab(paramDict, message)
    else:
        paramDict = add_empty_dataset_error_message_in_plot_charts_tab(paramDict)
    return paramDict


def draw_alternative_combination_chart_plotly(df, paramDict, chartDict):
    """
    actually draws bubble chart
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    font = configParams[namingParams["fontChoice"]]
    fontSize = configParams[namingParams["fontSizeText"]]
    varianceAmount = namingParams["varianceAmountName"]
    dimension = namingParams["dimensionName"]
    filterName = namingParams["filterName"]
    annotationDict = configParams[namingParams["annotationDict"]]
    colorDict = get_color_dictionary(chartDict)
    chartFormat = ",.0f"
    textColor = colorDict["blackColor"]
    maxLabelLength = 22
    df = ensure_polars_df(df)
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    fig = make_subplots()
    fig.add_trace(
        go.Scatter(
            x=df[varianceAmount],
            y=df[dimension],
            text=df[filterName],
            marker=dict(
                color=colorDict["veryLightGreyColor"],
                size=60,
                line=dict(
                    width=0.5,
                    color=colorDict["lightGreyColor"],
                ),
                opacity=0.8,
            ),
            mode="markers",
        )
    )
    cols, schema = get_schema_and_column_names(df)
    var_idx = cols.index(varianceAmount)
    dim_idx = cols.index(dimension)
    filter_idx = cols.index(filterName)

    xValue = df.row(0)[var_idx]
    fig.add_vline(
        x=xValue,
        layer="below",
        opacity=1,
        line_width=0.5,
        line_color="lightgrey",
        xref="x",
    )
    for idx in range(df.height):
        row = df.row(idx)
        text = row[filter_idx][:maxLabelLength]
        text = text.replace(" ", "<br>")
        text = text.replace("/", "<br>")
        fig.add_annotation(
            text=text,
            showarrow=False,
            align="center",
            yshift=0,
            x=row[var_idx],
            yref="y",
            y=row[dim_idx],
            ax=0,
            xshift=0,
            xref="x",
            font=dict(
                color=textColor,
            ),
        )
    return fig
