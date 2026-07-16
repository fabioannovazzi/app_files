import copy
import math
import logging

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.adjust_position import get_y1_y0_values
from modules.charting.chart_helpers import check_if_values_too_close
from modules.charting.chart_primitives import (
    divide_by_value_prefix,
    get_max_and_min_value,
    set_other_color_to_grey,
)
from modules.charting.draw_charts_utils import get_polars_value_at_index
from modules.charting.draw_waterfall import set_semantic_bar_color
from modules.data.common_data_utils import transform_lazy_df
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    flatten_cols_polars,
    get_dataset_specific_parameter,
    unique,
)
from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names


def check_if_two_periods_in_distribution_chart(periodsArray):
    if len(periodsArray) > 1:
        period0, period1 = periodsArray[0], periodsArray[1]
    else:
        period0, period1 = periodsArray[0], ""
    return period0, period1


def check_if_negative_bubble_size_values(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict, paramDict: dict
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Remove rows with negative bubble size values.

    Supports both eager and lazy Polars data structures without collecting.
    """

    namingParams = get_naming_params()
    warningMessageType = namingParams["warningMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    bubbleSizeKey = namingParams["bubbleSize"]
    bubbleSizeDimension = chartDict[bubbleSizeKey]

    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    has_negative = lf.select((pl.col(bubbleSizeDimension) < 0).any()).collect(
        engine="streaming"
    )[0, 0]

    if has_negative:
        message = (
            f"{bubbleSizeDimension} bubble size column contains negative values."
            " Correspondent rows have been excluded for plotting."
        )
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            plotChartsTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=0,
        )
        lf = lf.filter(pl.col(bubbleSizeDimension) > 0)

    result = lf.collect() if isinstance(df, pl.DataFrame) else lf
    return result, paramDict


def calculate_percentage_data_column_metric(
    df: pl.DataFrame,
    numeratorMetric: str,
    denominatorMetric: str,
    percentMetric: str,
    numberOfMetrics: int,
    sumColsArray: list[str],
    chartDict: dict,
) -> tuple[pl.DataFrame, dict, list[str], int, list[str]]:
    """Create a percentage metric using Polars operations."""

    namingParams = get_naming_params()
    averageTotalValue = namingParams["averageTotalValue"]
    dataColMetricName = namingParams["dataColMetricName"]

    totalAverageValue = df[numeratorMetric].sum() / df[denominatorMetric].sum() * 100
    df = df.with_columns(
        (pl.col(numeratorMetric) / pl.col(denominatorMetric) * 100)
        .fill_null(0)
        .alias(percentMetric)
    )

    chartDict[averageTotalValue][percentMetric] = totalAverageValue
    chartDict[dataColMetricName][percentMetric] = percentMetric
    sumColsArray.append(percentMetric)
    numberOfMetrics += 1
    return df, chartDict, sumColsArray, numberOfMetrics, sumColsArray


def calculate_price_data_column_metric(
    df: pl.DataFrame,
    numeratorMetric: str,
    denominatorMetric: str,
    priceMetric: str,
    numberOfMetrics: int,
    sumColsArray: list[str],
    chartDict: dict,
) -> tuple[pl.DataFrame, dict, list[str], int, list[str]]:
    """Create an average price metric using Polars."""

    namingParams = get_naming_params()
    averageTotalValue = namingParams["averageTotalValue"]
    dataColMetricName = namingParams["dataColMetricName"]

    totalAverageValue = df[numeratorMetric].sum() / df[denominatorMetric].sum()
    df = df.with_columns(
        (pl.col(numeratorMetric) / pl.col(denominatorMetric))
        .fill_null(0)
        .alias(priceMetric)
    )

    chartDict[averageTotalValue][priceMetric] = totalAverageValue
    chartDict[dataColMetricName][priceMetric] = priceMetric
    sumColsArray.append(priceMetric)
    numberOfMetrics += 1
    return df, chartDict, sumColsArray, numberOfMetrics, sumColsArray


def calculate_average_data_column_metric(
    df: pl.DataFrame,
    metric: str,
    averageMetric: str,
    countName: str,
    numberOfMetrics: int,
    sumColsArray: list[str],
    chartDict: dict,
) -> tuple[pl.DataFrame, dict, list[str], int, list[str]]:
    """Create an average metric by dividing ``metric`` by ``countName``."""

    namingParams = get_naming_params()
    averageTotalValue = namingParams["averageTotalValue"]
    dataColMetricName = namingParams["dataColMetricName"]

    totalAverageValue = df[metric].sum() / df[countName].sum()
    df = df.with_columns((pl.col(metric) / pl.col(countName)).alias(averageMetric))

    chartDict[averageTotalValue][averageMetric] = totalAverageValue
    chartDict[dataColMetricName][averageMetric] = averageMetric
    sumColsArray.append(averageMetric)
    numberOfMetrics += 1
    return df, chartDict, sumColsArray, numberOfMetrics, sumColsArray


def purge_other_runs_from_chartdict(chartDictCopy, run):
    namingParams = get_naming_params()
    configParams = get_config_params()
    drilldownParamsDictName = namingParams["drilldownParamsDictName"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    chartDict = copy.deepcopy(chartDictCopy)
    invertedEmojiNumberDict = configParams[namingParams["invertedEmojiNumberDict"]]
    if drilldownParamsDictName in chartDict:
        emojiNumber = run.replace(drilldownReportRunName + " ", "")
        emojiNumber = emojiNumber.strip()
        if emojiNumber in invertedEmojiNumberDict:
            chosenRow = invertedEmojiNumberDict[emojiNumber]
            if chosenRow in chartDict[drilldownParamsDictName]:
                chartDict[drilldownParamsDictName] = {}
                chartDict[drilldownParamsDictName][chosenRow] = chartDictCopy[
                    drilldownParamsDictName
                ][chosenRow]
            elif str(chosenRow) in chartDict[drilldownParamsDictName]:
                chartDict[drilldownParamsDictName] = {}
                chartDict[drilldownParamsDictName][str(chosenRow)] = chartDictCopy[
                    drilldownParamsDictName
                ][str(chosenRow)]
    return chartDict


def make_syn_plot_comment_dataset(inputFrameArray, chartDict):
    """
    Convert a list of Polars LazyFrames into a final Polars LazyFrame
    consistent with the logic of the original Pandas-based code.
    """
    namingParams = get_naming_params()
    itemName = namingParams["itemName"]
    dimensionName = namingParams["dimensionName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    percentName = namingParams["percentName"]
    valueName = namingParams["valueName"]

    outputFrameArray = []
    for lazy_df in inputFrameArray:
        # Transform each lazy DF individually
        transformed_df = transform_lazy_df(
            lazy_df,
            chartDict,
            dimensionName,
            itemName,
            plotValuesAsChoice,
            absolute,
            percentName,
            valueName,
        )
        outputFrameArray.append(transformed_df)

    # Concatenate all transformed lazy DFs vertically. This remains lazy.
    final_df = pl.concat(outputFrameArray, how="vertical")

    # Ensure dimensionName is string-typed in the final result
    final_df = final_df.with_columns(pl.col(dimensionName).cast(pl.Utf8))

    return final_df


def aggregate_syn_plot_data(
    chartDict,
    metric,
    frameArray,
    synColumnArray,
    aggregateOtherItemsName,
    synColorArray,
    mostRecentPeriod,
    paramDict,
):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    synthesisPlot = namingParams["synthesisPlot"]
    chartDict[synthesisPlot] = metConditionValue
    synColumnArray = list(dict.fromkeys(synColumnArray))
    df = pl.concat(frameArray, how="vertical")
    df = df.fill_nan(0)
    colorArray = set_other_color_to_grey(
        synColumnArray, aggregateOtherItemsName, synColorArray, chartDict, 0
    )
    return df, colorArray, chartDict, synColumnArray


def make_dic_to_color_first_bar(df, paramDict, chartDict, colorDict, run, count, array):
    """
    if small multiples, must make array with dictionaries
    to colors first bar based on if planned or previous data
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    planStemArray = configParams[namingParams["planStemArray"]]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    varianceAmountName = namingParams["varianceAmountName"]
    workColumn = namingParams["workColumn"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    isYearBeforePy = namingParams["isYearBeforePy"]
    newArray = []
    isExpectedData = False
    firstLabel = df[workColumn][0].lower()
    for element in planStemArray:
        if element in firstLabel:
            isExpectedData = True
    initialAndFinalValuesCanBeShown = True
    if varianceAggregation in chartDict:
        if (
            chartDict[varianceAggregation]
            not in [totalVarianceAggregation, marginVarianceAggregation]
            and drilldownReportRunName in run
        ):
            initialAndFinalValuesCanBeShown = False
    if (
        showInitialAndFinalValues in chartDict
        and chartDict[showInitialAndFinalValues]
        and initialAndFinalValuesCanBeShown
    ):
        firstBarColor, lineWidth, lineColor = set_semantic_bar_color(
            isExpectedData, colorDict, paramDict
        )
        xrefValue, yrefValue, x1Value = (
            "x" + str(count),
            "y" + str(count),
            df[varianceAmountName][0],
        )
        newArray = [
            {
                "type": "rect",
                "fillcolor": firstBarColor,
                "opacity": 1,
                "line_width": lineWidth,
                "line_color": lineColor,
                "xref": xrefValue,
                "yref": yrefValue,
                "y0": -0.4,
                "y1": 0.4,
                "x0": 0,
                "x1": x1Value,
            }
        ]
    array = array + newArray

    return array


def reverse_waterfall_y_range(fig):
    """
    get the waterfall items in the right order on the y axis
    """
    fig.update_yaxes(autorange="reversed")
    return fig


def make_dic_to_add_line(
    df,
    paramDict,
    chartDict,
    colorDict,
    run,
    count,
    shapeArray,
    x0Value,
    x1Value,
    numberOfCharts,
    isArrow,
    isPeriodZero,
    countRows,
):
    """
    in case of small multiples, we build the dictionary to add the line shapes
    """
    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    selectedPeriods = namingParams["selectedPeriods"]
    workColumn = namingParams["workColumn"]
    initialAndFinalValuesCanBeShown = True
    if varianceAggregation in chartDict:
        if (
            chartDict[varianceAggregation]
            not in [totalVarianceAggregation, marginVarianceAggregation]
            and drilldownReportRunName in run
        ):
            initialAndFinalValuesCanBeShown = False
    newShapeArray = []
    if (
        showInitialAndFinalValues in chartDict
        and chartDict[showInitialAndFinalValues]
        and initialAndFinalValuesCanBeShown
    ):
        firstBarColor, lineWidth, lineColor = (
            colorDict["whiteColor"],
            1,
            colorDict["lightGreyColor"],
        )
        xrefValue, yrefValue = "x" + str(count), "y" + str(count)
        df_lazy = ensure_lazyframe(df)
        periodOneValue = get_polars_value_at_index(
            df_lazy.filter(pl.col(workColumn) == chartDict[selectedPeriods][1]),
            varianceAmountName,
            0,
        )
        periodZeroValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
        if isArrow:
            lineWidth = 2
            if periodOneValue >= periodZeroValue:
                lineColor = colorDict["greenColor"]
            else:
                lineColor = colorDict["redColor"]
        y0Value, y1Value, yshift, lineColor = get_y1_y0_values(
            numberOfCharts,
            False,
            isArrow,
            count,
            isPeriodZero,
            lineColor,
            chartDict,
            countRows,
        )
        layerPlacement = "below"
        newShapeArray = [
            {
                "type": "line",
                "opacity": 1,
                "line_width": lineWidth,
                "line_color": lineColor,
                "yref": "paper",
                "xref": xrefValue,
                "y0": y0Value,
                "y1": y1Value,
                "x0": x0Value,
                "x1": x1Value,
                "layer": layerPlacement,
            },
        ]
    shapeArray = shapeArray + newShapeArray
    return shapeArray


def make_dic_to_add_annotation(
    df,
    paramDict,
    chartDict,
    colorDict,
    run,
    count,
    shapeArray,
    numberOfCharts,
    isText,
    isArrow,
    countRows,
):
    """
    in case of small multiples, we build the dictionary to add the annotations (arrow and text)
    """
    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVariance"]
    deltaName = namingParams["deltaName"]
    varianceAggregation = namingParams["varianceAggregation"]
    selectedPeriods = namingParams["selectedPeriods"]
    workColumn = namingParams["workColumn"]
    initialAndFinalValuesCanBeShown = True
    if varianceAggregation in chartDict:
        if (
            chartDict[varianceAggregation]
            not in [totalVarianceAggregation, marginVarianceAggregation]
            and drilldownReportRunName in run
        ):
            initialAndFinalValuesCanBeShown = False
    newShapeArray = []
    if (
        showInitialAndFinalValues in chartDict
        and chartDict[showInitialAndFinalValues]
        and initialAndFinalValuesCanBeShown
    ):
        df_lazy = ensure_lazyframe(df)
        periodOneValue = get_polars_value_at_index(
            df_lazy.filter(pl.col(workColumn) == chartDict[selectedPeriods][1]),
            varianceAmountName,
            0,
        )
        periodZeroValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
        xrefValue, yrefValue = "x" + str(count), "y" + str(count)
        if periodOneValue >= periodZeroValue:
            arrowColor = colorDict["greenColor"]
        else:
            arrowColor = colorDict["redColor"]
        y0Value, y1Value, yshift, lineColor = get_y1_y0_values(
            numberOfCharts,
            isText,
            isArrow,
            count,
            True,
            arrowColor,
            chartDict,
            countRows,
        )
        if periodZeroValue != 0:
            difference = periodOneValue - periodZeroValue
            difference = divide_by_value_prefix(difference, chartDict, False)
            difference = deltaName + " " + str(difference)
            percentChange = ((periodOneValue - periodZeroValue) / periodZeroValue) * 100
            if math.isnan(percentChange):
                percentChange = deltaName + " nan"
            else:
                percentChange = "<i>(" + str(int(round(percentChange, 0))) + "%)</i>"
            changevalue = difference + " " + percentChange
        else:
            percentChange = deltaName + " nan"
            changevalue = percentChange
        if isArrow:
            arrowHead, arrowSize = 5, 1
            text = None
            xshift = 0
        else:
            arrowHead, arrowSize = 5, 1
            text = changevalue
            xshift = 30
        periodValue = max(periodZeroValue, periodZeroValue)
        newShapeArray = [
            {
                "showarrow": isArrow,
                "arrowcolor": arrowColor,
                "text": text,
                "xshift": xshift,
                "yshift": yshift,
                "arrowhead": arrowHead,
                "arrowsize": arrowSize,
                "ay": y0Value,
                "y": y0Value,
                "yref": "paper",
                "ax": periodValue,
                "x": periodValue,
                "xref": xrefValue,
                "axref": xrefValue,
            },
        ]
    shapeArray = shapeArray + newShapeArray
    return shapeArray


def _get_max_and_min_value_pl(
    df: pl.LazyFrame,
    metric: str,
    chartDict: dict,
    periodsArray: list[str],
) -> pl.LazyFrame:
    """Return a LazyFrame with min/max columns and a color flag."""

    namingParams = get_naming_params()
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    colorName = namingParams["colorName"]
    chosenChartKey = namingParams["chosenChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    discountName = namingParams["discountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]

    chosenChart = chartDict[chosenChartKey]
    reverseColorMetricsArray = [
        discountName,
        discountInPercentName,
        indirectCostsName,
        cogsName,
    ]
    columns, schema = get_schema_and_column_names(df)
    for column in periodsArray:
        if column not in columns:
            df = df.with_columns(pl.lit(None).alias(column))

    if chosenChart not in [multitierColumnChart, horizontalWaterfallChart]:
        df = df.with_columns(
            pl.min_horizontal([pl.col(p) for p in periodsArray]).alias(minValue),
            pl.max_horizontal([pl.col(p) for p in periodsArray]).alias(maxValue),
        )

    if metric not in reverseColorMetricsArray:
        color_expr = (pl.col(periodsArray[0]) > pl.col(periodsArray[1])).cast(pl.Int8)
    else:
        color_expr = (pl.col(periodsArray[0]) <= pl.col(periodsArray[1])).cast(pl.Int8)

    df = df.with_columns(color_expr.alias(colorName))
    return df


def _check_if_values_too_close_pl(
    df: pl.DataFrame, chartDict: dict, metric: str, periodOrder: list[str]
) -> tuple[pl.DataFrame, str]:
    """Polars version of ``check_if_values_too_close``."""

    namingParams = get_naming_params()
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    workColumn = namingParams["workColumn"]
    hideLabel = namingParams["hideLabel"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    labelToHide = namingParams["labelToHide"]
    pricePerUnitName = namingParams["pricePerUnitName"]

    if chartDict[plotValuesAsChoice] == absolute and metric != pricePerUnitName:
        chartFormat = ",.3s"
        hideLabelLimit = 5
    elif chartDict[plotValuesAsChoice] == absolute and metric == pricePerUnitName:
        chartFormat = ",.2s"
        hideLabelLimit = 1
    elif metric == pricePerUnitName:
        chartFormat = ",.1f"
        hideLabelLimit = 1
    else:
        chartFormat = ",.0f"
        hideLabelLimit = 1

    total_max = df[maxValue].sum()

    df = df.with_columns(
        pl.lit(periodOrder[0]).alias(labelToHide),
        ((pl.col(maxValue) - pl.col(minValue)) / total_max * 100).alias(workColumn),
    )
    df = df.with_columns(
        pl.when(pl.col(periodOrder[1]).is_null())
        .then(periodOrder[1])
        .otherwise(pl.col(labelToHide))
        .alias(labelToHide)
    )
    df = df.with_columns(
        pl.when((pl.col(periodOrder[0]).is_null()) | (pl.col(periodOrder[1]).is_null()))
        .then(hideLabelLimit)
        .otherwise(pl.col(workColumn))
        .alias(workColumn)
    )
    df = df.with_columns(
        pl.when(pl.col(workColumn) < hideLabelLimit)
        .then(1)
        .otherwise(0)
        .alias(hideLabel)
    )
    df = df.drop(workColumn)
    return df, chartFormat


def tag_if_increasing_or_decreasing(
    dfCopy: pl.DataFrame,
    metric: str,
    chosenDimension: str,
    paramDict: dict,
    chartDict: dict,
) -> tuple[pl.DataFrame, str, dict]:
    """Prepare dumbbell chart data tagging increases/decreases."""
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    separatorString = namingParams["separatorString"]
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]
    periodName = namingParams["periodName"]
    hideLabel = namingParams["hideLabel"]
    labelToHide = namingParams["labelToHide"]
    periodOrder = chartDict[selectedPeriods]
    df_lazy = duplicate_dataframe(dfCopy)
    checkedPeriodOrder = []
    if isinstance(dfCopy, pl.LazyFrame):
        periodValues = (
            dfCopy.select(pl.col(periodName).unique())
            .collect(engine="streaming")
            .get_column(periodName)
            .to_list()
        )
    else:
        periodValues = dfCopy[periodName].unique().to_list()
    for period in periodOrder:
        periodLower = period.lower()
        periodUpper = period.upper()
        if period in periodValues:
            checkedPeriodOrder.append(period)
        elif periodLower in periodValues:
            checkedPeriodOrder.append(periodLower)
        elif periodUpper in periodValues:
            checkedPeriodOrder.append(periodUpper)
    chartDict[selectedPeriods] = checkedPeriodOrder
    df_lazy = (
        df_lazy.group_by([chosenDimension, periodName])
        .agg(pl.col(metric).sum())
        .pivot(periodName, index=chosenDimension, values=metric)
    )
    df_lazy = flatten_cols_polars(df_lazy, separatorString)
    df_lazy = _get_max_and_min_value_pl(df_lazy, metric, chartDict, checkedPeriodOrder)
    pl_df = df_lazy.collect()
    pl_df, chartFormat = _check_if_values_too_close_pl(
        pl_df, chartDict, metric, checkedPeriodOrder
    )

    pl_df = pl_df.unpivot(
        index=[
            chosenDimension,
            minValue,
            maxValue,
            colorName,
            hideLabel,
            "labelToHide",
        ],
        variable_name=periodName,
        value_name=metric,
    )
    pl_df = pl_df.with_columns(
        pl.when(
            (pl.col(hideLabel) == 1) & (pl.col(periodName) == pl.col("labelToHide"))
        )
        .then(None)
        .otherwise(pl.col(metric))
        .alias(labelName)
    )
    pl_df = drop_columns(pl_df, ["labelToHide", hideLabel])
    return pl_df, chartFormat, chartDict


def make_df_counts_unique_values(
    dfCopy: pl.DataFrame, countName: str, chartDict: dict
) -> pl.DataFrame:
    """Aggregate counts of unique values using Polars."""

    namingParams = get_naming_params()
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    countColumn = namingParams["countColumn"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]

    dfCounts = duplicate_dataframe(dfCopy)

    if chartDict[aggregateUniquesByDimension]:
        dim_col = chartDict[aggregateUniquesDimension]
        dfCounts = (
            dfCounts.select([chartDict[countColumn], dim_col])
            .with_columns(pl.lit(1).alias(countName))
            .with_columns(pl.col(dim_col).str.to_titlecase())
            .unique()
            .group_by(dim_col)
            .agg(pl.col(countName).sum())
        )
    else:
        dim_col = chartDict[countColumn]
        dfCounts = (
            dfCounts.select([dim_col])
            .with_columns(pl.lit(1).alias(countName))
            .with_columns(pl.col(dim_col).str.to_titlecase())
            .unique()
            .group_by(dim_col)
            .agg(pl.col(countName).sum())
        )

    return dfCounts


def make_df_for_pareto_classes(df, dfCounts):
    namingParams = get_naming_params()
    className = namingParams["className"]
    group_byCols = [className]
    indexColumn = className
    df = df.join(dfCounts, on=className, how="left")
    return df, group_byCols, indexColumn


def make_df_for_pareto_items(
    df: pl.DataFrame | pl.LazyFrame,
    dfCounts: pl.DataFrame | pl.LazyFrame,
    countName: str,
    chartDict: dict,
) -> tuple[pl.LazyFrame, list[str], str]:
    """Return ``df`` joined with counts for Pareto charts as a LazyFrame."""

    namingParams = get_naming_params()
    metricsToPlot = namingParams["metricsToPlot"]
    countColumn = namingParams["countColumn"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]

    metricsToPlot = chartDict[metricsToPlot]
    group_byCols = [chartDict[aggregateUniquesDimension]]
    indexColumn = chartDict[aggregateUniquesDimension]

    lf_items = ensure_lazyframe(df)
    lf_counts = ensure_lazyframe(dfCounts)

    dfItems = lf_items.select([chartDict[aggregateUniquesDimension], metricsToPlot[0]])
    lf_counts = lf_counts.join(
        dfItems, on=chartDict[aggregateUniquesDimension], how="full"
    )

    otherRank = lf_counts.filter(
        pl.col(countName).is_null() & pl.col(metricsToPlot[0]).is_not_null()
    )
    has_other = otherRank.select(pl.len()).collect().item() > 0

    if has_other:
        other_value = (
            otherRank.select(pl.col(chartDict[aggregateUniquesDimension]).first())
            .collect()
            .item()
        )
        lf_counts = lf_counts.with_columns(
            pl.when(pl.col(metricsToPlot[0]).is_null())
            .then(pl.lit(other_value))
            .otherwise(pl.col(chartDict[countColumn]))
            .alias(chartDict[countColumn])
        )
        lf_counts = (
            lf_counts.select([chartDict[aggregateUniquesDimension], countName])
            .drop_nulls()
            .group_by(chartDict[aggregateUniquesDimension])
            .agg(pl.col(countName).sum())
        )

    lf_counts = drop_columns(lf_counts, [metricsToPlot[0]])
    lf_result = lf_items.join(
        lf_counts, on=chartDict[aggregateUniquesDimension], how="left"
    )
    return lf_result, group_byCols, indexColumn


def get_pareto_axis(fig, metricsToPlot, chartDict):
    namingParams = get_naming_params()
    fixedScaleChoice = namingParams["fixedParetoScaleChoice"]
    scaleOne, scaleTwo, scaleThree, scaleFour, scaleFive, scaleSix = (
        False,
        False,
        False,
        False,
        False,
        False,
    )
    if (
        len(metricsToPlot) > 1
        and fixedScaleChoice in chartDict
        and chartDict[fixedScaleChoice]
    ):
        fullFig = fig.full_figure_for_development(warn=False)
        scaleOne = fullFig.layout.xaxis.range[1]
        if "xaxis2" in fullFig.layout:
            scaleTwo = fullFig.layout.xaxis2.range[1]
        if len(metricsToPlot) > 2 and "xaxis3" in fullFig.layout:
            scaleThree = fullFig.layout.xaxis3.range[1]
        if len(metricsToPlot) > 3 and "xaxis4" in fullFig.layout:
            scaleFour = fullFig.layout.xaxis4.range[1]
        if len(metricsToPlot) > 4 and "xaxis5" in fullFig.layout:
            scaleFive = fullFig.layout.xaxis5.range[1]
        if len(metricsToPlot) > 5 and "xaxis6" in fullFig.layout:
            scaleSix = fullFig.layout.xaxis6.range[1]
        scaleArray = [scaleOne, scaleTwo, scaleThree, scaleFour, scaleFive, scaleSix]
        maxScale = max(scaleArray)
        fig.update_layout(xaxis_range=[fullFig.layout.xaxis.range[0], maxScale])
        if "xaxis2" in fullFig.layout:
            fig.update_layout(xaxis2_range=[fullFig.layout.xaxis2.range[0], maxScale])
        if len(metricsToPlot) > 2 and "xaxis3" in fullFig.layout:
            fig.update_layout(xaxis3_range=[fullFig.layout.xaxis3.range[0], maxScale])
        if len(metricsToPlot) > 3 and "xaxis4" in fullFig.layout:
            fig.update_layout(xaxis4_range=[fullFig.layout.xaxis4.range[0], maxScale])
        if len(metricsToPlot) > 4 and "xaxis5" in fullFig.layout:
            fig.update_layout(xaxis5_range=[fullFig.layout.xaxis5.range[0], maxScale])
        if len(metricsToPlot) > 5 and "xaxis6" in fullFig.layout:
            fig.update_layout(xaxis6_range=[fullFig.layout.xaxis6.range[0], maxScale])
    return fig


def join_metric_dataframes(
    dfDict: dict[str, pl.LazyFrame | pl.DataFrame], metricsToPlot: list[str]
) -> pl.LazyFrame:
    """Left join metric frames using Polars lazily."""

    base_key = metricsToPlot[0]
    base_df = ensure_lazyframe(dfDict[base_key]).clone()
    columns, _ = get_schema_and_column_names(base_df)
    join_col = columns[0]
    for key in metricsToPlot[1:]:
        other_df = ensure_lazyframe(dfDict[key]).clone()
        columns, _ = get_schema_and_column_names(other_df)
        other_df = other_df.rename({columns[0]: join_col})
        base_df = base_df.join(other_df, on=join_col, how="left")

    return base_df


def calculate_metrics_for_data_column(df, chartDict, sumColsArray, countName):
    """
    calculate metrics for Pareto stacked bar plot data column
    """
    namingParams = get_naming_params()
    countColumn = namingParams["countColumn"]
    dataColMetricName = namingParams["dataColMetricName"]
    averageTotalValue = namingParams["averageTotalValue"]
    rankingMetric = namingParams["rankingMetric"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    metricsToShowInDataColumn = namingParams["metricsToShowInDataColumn"]
    monetaryLocalCurrencyName = namingParams["monetaryLocalCurrencyName"]
    averageAmount = namingParams["averageAmount"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    averageUnits = namingParams["averageUnits"]
    averageVolume = namingParams["averageVolume"]
    discountName = namingParams["discountName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    discountInPercentName = namingParams["discountInPercentName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    averageAmountAfterDiscount = namingParams["averageAmountAfterDiscount"]
    marginName = namingParams["marginName"]
    averageMargin = namingParams["averageMargin"]
    nothingThereString = namingParams["nothingThereString"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    averageTotalValue = namingParams["averageTotalValue"]
    dataColMetricName = namingParams["dataColMetricName"]
    numberOfMetrics = 0
    columns, schema = get_schema_and_column_names(df)
    numberOfColsAtStart = len(columns)
    chartDict = drop_choices_over_max(chartDict)
    chartDict[averageTotalValue] = {}
    chartDict[dataColMetricName] = {}
    if showMetricsInDataColumn in chartDict and chartDict[showMetricsInDataColumn]:
        if averageAmount in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_average_data_column_metric(
                    df,
                    monetaryLocalCurrencyName,
                    averageAmount,
                    countName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if averageUnits in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_average_data_column_metric(
                    df,
                    unitsName,
                    averageUnits,
                    countName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if averageVolume in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_average_data_column_metric(
                    df,
                    volumeName,
                    averageVolume,
                    countName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if pricePerUnitName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_price_data_column_metric(
                    df,
                    monetaryLocalCurrencyName,
                    unitsName,
                    pricePerUnitName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if pricePerVolumeName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_price_data_column_metric(
                    df,
                    monetaryLocalCurrencyName,
                    volumeName,
                    pricePerVolumeName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if pricePerUnitNetDiscountName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_price_data_column_metric(
                    df,
                    netOfDiscountName,
                    unitsName,
                    pricePerUnitNetDiscountName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if pricePerVolumeNetDiscountName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_price_data_column_metric(
                    df,
                    netOfDiscountName,
                    volumeName,
                    pricePerVolumeNetDiscountName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if discountInPercentName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_percentage_data_column_metric(
                    df,
                    discountName,
                    monetaryLocalCurrencyName,
                    discountInPercentName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if averageAmountAfterDiscount in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_average_data_column_metric(
                    df,
                    netOfDiscountName,
                    averageAmountAfterDiscount,
                    countName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if averageMargin in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_average_data_column_metric(
                    df,
                    marginName,
                    averageMargin,
                    countName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if marginInPercentName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_percentage_data_column_metric(
                    df,
                    marginName,
                    monetaryLocalCurrencyName,
                    marginInPercentName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
        if marginInPercentOfNetSalesName in chartDict[metricsToShowInDataColumn]:
            df, chartDict, sumColsArray, numberOfMetrics, sumColsArray = (
                calculate_percentage_data_column_metric(
                    df,
                    netOfDiscountName,
                    monetaryLocalCurrencyName,
                    marginInPercentOfNetSalesName,
                    numberOfMetrics,
                    sumColsArray,
                    chartDict,
                )
            )
    columns, schema = get_schema_and_column_names(df)
    numberOfColsAtEnd = len(columns)
    df = df.filter(pl.col(columns[0]) != nothingThereString)
    return df, chartDict, sumColsArray


def calculate_actual_vs_previous_year_index_change(
    df: pl.DataFrame, column: str | None, valueCols: list[str], paramDict: dict
) -> pl.DataFrame:
    """Calculate year-over-year index change using Polars."""

    namingParams = get_naming_params()
    acpyName = namingParams["acpyName"]
    periodName = namingParams["periodName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    yoyChangeName = namingParams["yoyChangeName"]

    divideIndex = [periodName, acpyName]
    if column:
        divideIndex.append(column)

    dfTy = df.filter(pl.col(acpyName) == acName).with_columns(
        pl.lit(yoyChangeName).alias(acpyName)
    )
    dfYa = df.filter(pl.col(acpyName) == pyName).with_columns(
        pl.lit(yoyChangeName).alias(acpyName)
    )

    joined = dfTy.join(dfYa, on=divideIndex, how="inner", suffix="_ya")

    for col_name in valueCols:
        joined = joined.with_columns(
            pl.when(pl.col(f"{col_name}_ya") != 0)
            .then((pl.col(col_name) / pl.col(f"{col_name}_ya") * 100).round(0))
            .otherwise(0)
            .alias(col_name)
        )

    result_cols = divideIndex + valueCols
    return joined.select(result_cols)


def get_mins_and_maxes(dataArray, chartDict):
    namingParams = get_naming_params()
    startAxesFromZero = namingParams["startAxesFromZero"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    minXDimensionKey = namingParams["minXDimension"]
    maxXDimensionKey = namingParams["maxXDimension"]
    minYDimensionKey = namingParams["minYDimension"]
    maxYDimensionKey = namingParams["maxYDimension"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    if startAxesFromZero in chartDict and chartDict[startAxesFromZero]:
        chartDict[minXDimensionKey], chartDict[maxXDimensionKey] = (
            notMetConditionValue,
            notMetConditionValue,
        )
        chartDict[minYDimensionKey], chartDict[maxYDimensionKey] = (
            notMetConditionValue,
            notMetConditionValue,
        )
    else:
        chartDict[minXDimensionKey], chartDict[maxXDimensionKey] = (
            99999999999999,
            -99999999999999,
        )
        chartDict[minYDimensionKey], chartDict[maxYDimensionKey] = (
            99999999999999,
            -99999999999999,
        )
        for df in dataArray:
            minXDimension = min(df[xDimension])
            maxXDimension = max(df[xDimension])
            minYDimension = min(df[yDimension])
            maxYDimension = max(df[yDimension])
            if minXDimension < chartDict[minXDimensionKey]:
                chartDict[minXDimensionKey] = minXDimension
            if maxXDimension > chartDict[maxXDimensionKey]:
                chartDict[maxXDimensionKey] = maxXDimension
            if minYDimension < chartDict[minYDimensionKey]:
                chartDict[minYDimensionKey] = minYDimension
            if maxYDimension > chartDict[maxYDimensionKey]:
                chartDict[maxYDimensionKey] = maxYDimension
    return chartDict


def drop_choices_over_max(chartDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    numberOfMetricsInDataColumnKey = namingParams["numberOfMetricsInDataColumn"]
    metricsToShowInDataColumn = namingParams["metricsToShowInDataColumn"]
    maxNumberOfDataColMetrics = configParams[namingParams["maxNumberOfDataColMetrics"]]
    numberOfMetricsInDataColumn = len(chartDict[metricsToShowInDataColumn])
    if numberOfMetricsInDataColumn > maxNumberOfDataColMetrics:
        chartDict[metricsToShowInDataColumn] = chartDict[metricsToShowInDataColumn][
            0:maxNumberOfDataColMetrics
        ]
        numberOfMetricsInDataColumn = len(chartDict[metricsToShowInDataColumn])
    chartDict[numberOfMetricsInDataColumnKey] = numberOfMetricsInDataColumn
    return chartDict


def make_integer_date_dict(uniqueDates):
    dateToIntDict = {}
    intToDateDict = {}
    orderedList = list(range(1, len(uniqueDates) + 1))
    count = 0
    for date in uniqueDates:
        intToDateDict[orderedList[count]] = date
        dateToIntDict[date] = [orderedList[count]]
        count = count + 1
    return orderedList, intToDateDict, dateToIntDict


def delete_black_vertical_lines(fig):
    fig.update_layout(
        yaxis=dict(
            showline=False,  # Hides the vertical axis line but keeps the labels
            showticklabels=True,  # Ensures tick labels like "PL", "Price" remain
        )
    )
    fig.update_yaxes(showline=False)

    fig.update_yaxes(
        zeroline=True,  # Ensures the zero line is visible
        zerolinecolor="black",  # Changes the color of the zero line to black
        zerolinewidth=2,  # Optionally, you can adjust the thickness of the zero line
    )
    return fig


def set_axes_to_log(fig, chartDict):
    namingParams = get_naming_params()
    logXAxis = namingParams["logXAxis"]
    logYAxis = namingParams["logYAxis"]
    if logXAxis in chartDict and chartDict[logXAxis]:
        fig.update_xaxes(type="log")

    if logYAxis in chartDict and chartDict[logYAxis]:
        fig.update_yaxes(type="log")
    return fig


def set_number_of_cols_for_bubble_and_scatter_chart(smallMultipleUniqueItems):
    numberOfCols = 2
    if len(smallMultipleUniqueItems) <= 4:
        numberOfCols = 2
    elif len(smallMultipleUniqueItems) <= 6:
        numberOfCols = 3
    else:
        numberOfCols = 4
    return numberOfCols


def extract_values_from_dictionary(valueDict):
    paramDict = valueDict["1"]
    df = valueDict["2"]
    dfDates = valueDict["3"]
    dfPeriods = valueDict["4"]
    dfAllPeriods = valueDict["5"]
    dfPlan = valueDict["6"]
    indexCols = valueDict["7"]
    valueCols = valueDict["8"]
    chartDict = valueDict["9"]
    toDrop = valueDict["10"]
    originalValueCols = valueDict["11"]
    colDict = valueDict["12"]
    tabDict = valueDict["13"]
    automateDict = valueDict["14"]
    planPlaybackDict = valueDict["15"]
    return (
        paramDict,
        df,
        dfDates,
        dfPeriods,
        dfAllPeriods,
        dfPlan,
        indexCols,
        valueCols,
        chartDict,
        toDrop,
        originalValueCols,
        colDict,
        tabDict,
        automateDict,
        planPlaybackDict,
    )
