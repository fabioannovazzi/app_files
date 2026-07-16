import copy
import math

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)


def move_labels_up(fig, chartDict, uniqueItems):
    namingParams = get_naming_params()
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    xAxisDimension = namingParams["xAxisDimension"]
    smallMultiplesWaterfall = namingParams["smallMultiplesWaterfall"]
    varianceAggregationOptionsArrayKey = namingParams["varianceAggregationOptionsArray"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    chosenChart = namingParams["chosenChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekko = namingParams["barmekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    moveLabels = False
    if (
        plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
        and chartDict[chosenChart] in [barmekko, marimekkoChart]
    ):
        moveLabels = True
        titleNames = uniqueItems
        if len(titleNames) <= 4:
            y_adjustment = 0.01
        else:
            y_adjustment = 0.003
    elif (
        plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
        and chartDict[chosenChart] in [stackedBarChart]
    ):
        moveLabels = True
        titleNames = uniqueItems
        if len(titleNames) <= 2:
            y_adjustment = 0.01
        else:
            y_adjustment = 0.02
    elif (
        selectDimensionsToPlot in chartDict
        and len(chartDict[selectDimensionsToPlot]) > 0
    ):
        if xAxisDimension in chartDict:
            titleNames = uniqueItems
        else:
            titleNames = chartDict[selectDimensionsToPlot]
        moveLabels = True
        if len(titleNames) <= 4:
            y_adjustment = 0.05
        else:
            y_adjustment = 0.03
    elif (
        smallMultiplesWaterfall in chartDict
        and len(chartDict[smallMultiplesWaterfall]) > 0
    ):
        moveLabels = True
        titleNames = chartDict[smallMultiplesWaterfall]
        if len(titleNames) <= 4:
            y_adjustment = 0.005
        else:
            y_adjustment = 0.005
    elif (
        varianceAggregationOptionsArrayKey in chartDict
        and len(chartDict[varianceAggregationOptionsArrayKey]) > 0
    ):
        moveLabels = True
        titleNames = chartDict[varianceAggregationOptionsArrayKey]
        if len(titleNames) <= 3:
            y_adjustment = 0.030
        else:
            y_adjustment = 0.030
    if moveLabels:
        new_annotations = []
        for i, ann in enumerate(fig.layout.annotations):
            if ann.text in titleNames:
                fig.layout.annotations[i].y += y_adjustment
                fig.layout.annotations[i].xanchor = "center"
                fig.layout.annotations[i].align = "center"
    return fig


def get_waterfall_plot_height_and_width(df, chartDict, numberOfRows, numberOfCols):
    """
    the more rows the more we want the plot to be high, to a limit
    """
    namingParams = get_naming_params()
    processingChoice = namingParams["processingChoice"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    varianceDifferentCalculations = namingParams["varianceDifferentCalculations"]
    maxStringLength = get_label_length(df)
    titleConstant = 120
    tileTitle = 35
    singleRowHeight = 25
    lowerMargin = 5
    if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
        height = titleConstant + (singleRowHeight * (df.height)) + lowerMargin
        width = (maxStringLength * 5) + 250
    elif (
        varianceDifferentCalculations in chartDict
        and chartDict[varianceDifferentCalculations]
    ) or (plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]):
        singleRowHeight = 20
        height = titleConstant + (
            (singleRowHeight * (df.height) + (lowerMargin + tileTitle)) * numberOfRows
        )
        width = (maxStringLength * 5) + (250 * numberOfCols)
    else:
        height = titleConstant + (singleRowHeight * (df.height)) + lowerMargin
        width = (maxStringLength * 5) + 250
    return height, width, maxStringLength


def get_label_length(df):
    """
    the more dimensions in the labels, the wider
    """
    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]
    # Use Polars string length in characters; cast to Utf8 to be safe
    maxLabelLength = int(
        df.get_column(workColumn).cast(pl.Utf8, strict=False).str.len_chars().max()
    )
    return maxLabelLength


def expand_width(numberOfColumns, chosenChart, chartDict):
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    addBlankColumn = namingParams["addBlankColumn"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    expandWith = notMetConditionValue
    if (
        smallMultiplesCharts in chartDict
        and chartDict[smallMultiplesCharts]
        and chosenChart in [marimekkoChart]
    ):
        widthExpander = 1.5
    elif (
        smallMultiplesCharts in chartDict
        and chartDict[smallMultiplesCharts]
        and chosenChart in [stackedBarChart]
    ):
        widthExpander = 1.5
    elif addBlankColumn in chartDict and chartDict[addBlankColumn]:
        if chosenChart in [stackedParetoChart, stackedColumnChart]:
            widthExpander = (numberOfColumns + 1) / numberOfColumns
        elif chosenChart in [stackedBarChart]:
            widthExpander = 1.3
    else:
        widthExpander = 1
    return widthExpander


def stacked_bar_height(df, height):
    namingParams = get_naming_params()
    numberOfBars = df.height - 1
    barHeightDict = {
        1: 260,
        2: 260,
        3: 290,
        4: 310,
        5: 330,
        6: 370,
        7: 400,
        8: 430,
        9: 450,
        10: 470,
        11: 510,
        12: 530,
        13: 530,
        14: 540,
        15: 560,
        16: 570,
        17: 580,
        18: 600,
        19: 610,
        20: 620,
        21: 660,
        22: 670,
        23: 675,
        24: 680,
        25: 690,
    }
    if numberOfBars in barHeightDict:
        height = barHeightDict[numberOfBars]
    return height


def set_bar_gap_offset(chartDict, namingParams, configParams, noSumMetricsArray):
    """
    Decide bargap, offset, and whether we should make columns thin
    based on user configuration and chart type.
    """
    # Unpack keys we need
    showLegend = namingParams["showLegend"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    datePeriodName = namingParams["datePeriodName"]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    yearName = namingParams["yearName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]

    noSum = chartDict.get(stackedColumnMetric) in noSumMetricsArray

    bargapDict = {
        yearName: 0.20,
        quarterName: 0.25,
        monthName: 0.30,
        weekName: 0.35,
    }
    offsetDict = {
        yearName: 0,
        quarterName: 0.005,
        monthName: 0.05,
        weekName: 0.1,
    }

    # Possibly override if "synthesisPlot" is present
    if (
        namingParams["synthesisPlot"] in chartDict
        and chartDict[namingParams["synthesisPlot"]]
    ):
        bargapDict = {
            yearName: 0.10,
            quarterName: 0.15,
            monthName: 0.20,
            weekName: 0.30,
        }
        offsetDict = {
            yearName: 0,
            quarterName: 0.005,
            monthName: 0.05,
            weekName: 0.1,
        }

    # Default values
    bargap = 0.1
    offset = 0
    makeColsThin = False

    # If it’s a no-sum metric and a small multiple
    if noSum:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            bargap = 0.5
            offset = 0.2
        else:
            makeColsThin = True

    # else if we have a left/right legend + known date period
    elif (
        chartDict.get(showLegend) == showLegendLeftOrRight
        and chartDict.get(datePeriodName) in bargapDict
    ):
        bargap = bargapDict[chartDict[datePeriodName]]
        offset = offsetDict[chartDict[datePeriodName]]

    return bargap, offset, makeColsThin


def reset_height(figure, frameArray, chosenChart, numberOfCols, chartDict, paramDict):
    sameNumberOfItems = True
    numberOfItemsArray = []
    maxLength = 0
    ordered = True
    count = 0
    for df in frameArray:
        numberOfItems = df.height
        numberOfItemsArray.append(str(numberOfItems))
        if count == 0:
            firstItemLen = numberOfItems
        elif firstItemLen < numberOfItems:
            ordered = False
        if numberOfItems > maxLength:
            maxLength = numberOfItems
        count = count + 1
    if len(list(set(numberOfItemsArray))) > 1 and maxLength > 2 and not ordered:
        for df in frameArray:
            height, width = set_width_and_height(
                df, chosenChart, numberOfCols, chartDict, paramDict
            )
        figure.update_layout(
            height=height,
        )
    return figure


def set_width_and_height(df, chosenChart, numberOfCols, chartDict, paramDict):
    configParams = get_config_params()
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegend = namingParams["showLegend"]
    goldenRatio = configParams[namingParams["goldenRatio"]]
    datePeriodName = namingParams["datePeriodName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    yearName = namingParams["yearName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]
    synthesisPlot = namingParams["synthesisPlot"]
    showCAGR = namingParams["showCAGR"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    numberOfRowsKey = namingParams["numberOfRows"]
    numberOfColsKey = namingParams["numberOfCols"]
    numberOfColsString = str(numberOfCols)
    widthDict = {
        "0": 190,
        "1": 230,
        "2": 270,
        "3": 300,
        "4": 330,
        "5": 380,
        "6": 400,
        "7": 550,
        "8": 45 * 8,
        "9": 45 * 9,
        "10": 54 * 10,  # 660
        "11": 54 * 11,
        "12": 54 * 12,
        "13": 50 * 13,
        "14": 50 * 14,
        "15": 50 * 15,
        "16": 50 * 16,
        "17": 50 * 17,
        "18": 50 * 18,
        "19": 50 * 19,
        "20": 50 * 20,
        "21": 50 * 21,
        "22": 50 * 22,
        "23": 50 * 23,
        "24": 50 * 24,
        "25": 50 * 25,
        "26": 50 * 26,
        "27": 50 * 27,
    }
    height = 500 * 1.3
    widthExpander = 1
    widthExpander = expand_width(numberOfCols, chosenChart, chartDict)
    if chosenChart in [stackedColumnChart] and numberOfCols > 10:
        # widthExpander=widthExpander*1.5
        width = 1051
    if chosenChart in [stackedBarChart]:
        height = stacked_bar_height(df, height)
        width = 1051
    elif synthesisPlot in chartDict and chartDict[synthesisPlot]:
        width = height * goldenRatio * widthExpander
    elif showLegend in chartDict and chartDict[showLegend] == showLegendLeftOrRight:
        if (
            numberOfColsString in widthDict
            and showCAGR in chartDict
            and chartDict[showCAGR]
            and chartDict[plotValuesAsChoice] == absolute
        ):
            width = widthDict[numberOfColsString]
        elif numberOfColsString in widthDict and chosenChart not in [
            stackedParetoChart
        ]:
            nnumberOfColsString = str(numberOfCols - 1)
            width = widthDict[numberOfColsString]
        elif numberOfColsString in widthDict and chosenChart in [stackedParetoChart]:
            numberOfColsString = str(numberOfCols)
            width = widthDict[numberOfColsString]
    else:
        width = height * goldenRatio * widthExpander
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if chosenChart in [stackedColumnChart]:
            width = width * 1.6
        elif chosenChart in [stackedBarChart]:
            height = height * 1.3
            width = width * widthExpander
            if numberOfRowsKey in paramDict and paramDict[numberOfRowsKey] > 1:
                constant = 0.65
                height = int(height * constant * paramDict[numberOfRowsKey])
        elif chosenChart in [marimekkoChart]:
            rows = (
                paramDict.get(numberOfRowsKey, 1) if isinstance(paramDict, dict) else 1
            )
            cols = (
                paramDict.get(numberOfColsKey, numberOfCols)
                if isinstance(paramDict, dict)
                else numberOfCols
            )
            height_factor = 1.4 if rows <= 2 else 1.25
            width_factor = 1.15 if cols <= 2 else 1.1
            height = height * height_factor
            width = width * widthExpander * width_factor
        else:
            pass
    width = round(width, 0)
    height = round(height, 0)
    return height, width


def get_y1_y0_values(
    numberOfCharts,
    isText,
    isArrow,
    count,
    isPeriodZero,
    lineColor,
    chartDict,
    countRows,
):
    """
    based on the total number of charts and the row of each chart, positioning of shapes is different
    """
    namingParams = get_naming_params()
    varianceAggregationOptionsArrayKey = namingParams["varianceAggregationOptionsArray"]
    yshift = 0
    y0Value = None
    y1Value = None
    if (
        numberOfCharts == 3
        and varianceAggregationOptionsArrayKey in chartDict
        and len(chartDict[varianceAggregationOptionsArrayKey]) > 0
    ):
        if isText:
            y0Value = -0.1
            y1Value = y0Value
        elif isArrow:
            y0Value = -0.05
            y1Value = -0.05
        elif isPeriodZero:
            y0Value = -0.05
            y1Value = 0.95
        else:
            y0Value = -0.05
            y1Value = 0.1
    elif numberOfCharts <= 3:
        if isArrow:
            y0Value = -0.05
            y1Value = -0.05
        elif isPeriodZero:
            y0Value = -0.4
            y1Value = 0.95
        else:
            y0Value = -0.4
            y1Value = 0.1
    elif numberOfCharts <= 6:
        if countRows == 1:
            if isText:
                y0Value = 0.55
                y1Value = y0Value
            elif isArrow:
                y0Value = 0.55
                y1Value = y0Value
            elif isPeriodZero:
                y0Value = 0.83
                y1Value = 0.55
            else:
                y0Value = 0.65
                y1Value = 0.55
        elif countRows == 2:
            if isText:
                y0Value = -0.08
                y1Value = y0Value
            elif isArrow:
                y0Value = -0.05
                y1Value = y0Value
            elif isPeriodZero:
                y0Value = -0.05
                y1Value = 0.35
            else:
                y0Value = 0.15
                y1Value = -0.05
    elif numberOfCharts <= 9:
        if countRows == 1:
            if isText:
                y0Value = 0.75
                y1Value = y0Value
            elif isArrow:
                y0Value = 0.72
                y1Value = y0Value
            elif isPeriodZero:
                y0Value = 0.93
                y1Value = 0.72
            else:
                y0Value = 0.8
                y1Value = 0.72
        elif countRows == 2:
            if isText:
                y0Value = 0.33
                y1Value = y0Value
            elif isArrow:
                y0Value = 0.355
                y1Value = y0Value
            elif isPeriodZero:
                y0Value = 0.61
                y1Value = 0.35
            else:
                y0Value = 0.41
                y1Value = 0.35
        elif countRows == 3:
            if isText:
                y0Value = -0.06
                y1Value = y0Value
            elif isArrow:
                y0Value = -0.04
                y1Value = y0Value
            elif isPeriodZero:
                y0Value = 0.21
                y1Value = -0.04
            else:
                y0Value = 0.1
                y1Value = -0.04
    if y0Value is None or y1Value is None:
        y0Value, y1Value = _get_many_panel_waterfall_y_values(
            numberOfCharts,
            isText,
            isArrow,
            isPeriodZero,
            countRows,
        )
    return y0Value, y1Value, yshift, lineColor


def _get_many_panel_waterfall_y_values(
    numberOfCharts,
    isText,
    isArrow,
    isPeriodZero,
    countRows,
):
    """
    General row-position fallback for waterfall small multiples beyond the old hardcoded layouts.
    """
    numberOfCols = 3
    numberOfRows = max(1, int(math.ceil(numberOfCharts / numberOfCols)))
    rowIndex = min(max(int(countRows), 1), numberOfRows)
    verticalSpacingDict = {1: 0, 2: 0.20, 3: 0.1, 4: 0.08, 5: 0.06, 6: 0.04}
    if numberOfRows in verticalSpacingDict:
        verticalSpacing = verticalSpacingDict[numberOfRows]
    else:
        verticalSpacing = verticalSpacingDict[len(verticalSpacingDict)]
    verticalSpacing = verticalSpacing * 1.2
    if numberOfRows > 1:
        maxVerticalSpacing = 0.8 / (numberOfRows - 1)
        verticalSpacing = min(verticalSpacing, maxVerticalSpacing)
    rowHeight = (1 - (verticalSpacing * (numberOfRows - 1))) / numberOfRows
    rowTop = 1 - ((rowIndex - 1) * (rowHeight + verticalSpacing))
    rowBottom = rowTop - rowHeight
    baseline = rowBottom - min(0.035, max(0.01, rowHeight * 0.18))
    if isText or isArrow:
        return baseline, baseline
    if isPeriodZero:
        return rowTop - min(0.06, max(0.01, rowHeight * 0.15)), baseline
    return rowBottom + (rowHeight * 0.35), baseline


def get_x_shift_for_data_column(numberOfCols, chartDict, position):
    """
    shift for right data column
    """
    numberOfCols = str(numberOfCols)
    namingParams = get_naming_params()
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegend = namingParams["showLegend"]
    if showLegend in chartDict and chartDict[showLegend] == showLegendLeftOrRight:
        xShiftDict = {
            "row": {
                "2": 2,
                "3": 2,
                "4": 2,
                "5": -0,
                "6": -0,
                "7": -1,
                "8": -1,
                "9": -1,
                "10": -1,
                "11": -1,
                "12": -1,
                "13": -1,
                "14": -1,
                "15": -1,
                "16": -1,
                "17": -1,
                "18": -5,
                "19": -5,
                "20": -0,
                "21": -0,
                "22": -5,
                "23": 0,
                "24": +5,
                "25": 0,
            },
            "title": {
                "2": 2,
                "3": 2,
                "4": 2,
                "5": -0,
                "6": -0,
                "7": -1,
                "8": -1,
                "9": -1,
                "10": -1,
                "11": -0,
                "12": -0,
                "13": -0,
                "14": -0,
                "15": -0,
                "16": -0,
                "17": -5,
                "18": -5,
                "19": -5,
                "20": -5,
                "21": -5,
                "22": -5,
                "23": -5,
                "24": -5,
                "25": -5,
            },
        }
        xShiftDictNotFound = {
            "row": -10,
            "title": -60,
        }
    else:
        xShiftDict = {
            "row": {
                "2": -440,
                "3": -270,
                "4": -190,
                "5": -140,
                "6": -110,
                "7": -90,
                "8": -65,
                "9": -60,
                "10": -45,
                "11": -35,
                "12": -30,
                "13": -25,
                "14": -20,
                "15": -15,
                "16": -15,
                "17": -10,
                "18": -5,
                "19": -5,
                "20": -0,
                "21": -0,
                "22": -5,
                "23": 0,
                "24": +5,
                "25": 0,
            },
            "title": {
                "2": -420,
                "3": -250,
                "4": -170,
                "5": -115,
                "6": -90,
                "7": -70,
                "8": -60,
                "9": -45,
                "10": -40,
                "11": -30,
                "12": -25,
                "13": -20,
                "14": -15,
                "15": -10,
                "16": -10,
                "17": -5,
                "18": -5,
                "19": -5,
                "20": -5,
                "21": -5,
                "22": -5,
                "23": -5,
                "24": -5,
                "25": -5,
            },
        }
        xShiftDictNotFound = {
            "row": -10,
            "title": -60,
        }
    if numberOfCols in xShiftDict[position]:
        xShift = xShiftDict[position][numberOfCols]
    else:
        xShift = xShiftDictNotFound[position]
    return xShift


def adjust_ax_by_number_of_columns(numberOfColumns, chartDict):
    """
    left legend distance from bar
    """
    namingParams = get_naming_params()
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegend = namingParams["showLegend"]
    numberOfColumns = str(numberOfColumns)
    if showLegend in chartDict and chartDict[showLegend] == showLegendLeftOrRight:
        xShiftDictNotFound = -0.07
        xShiftDict = {
            "2": -0.28,
            "3": -0.2,
            "4": -0.165,
            "5": -0.15,
            "6": -0.14,
            "7": -0.12,
            "8": -0.105,
            "9": -0.095,
            "10": -0.080,
            "11": -0.080,
            "12": -0.085,
            "13": -0.085,
            "14": -0.085,
            "15": -0.085,
            "16": -0.085,
            "17": -0.085,
            "18": -0.085,
            "19": -0.085,
            "20": -0.085,
            "21": -0.085,
            "22": -0.085,
            "23": -0.085,
            "24": -0.085,
            "25": -0.085,
        }
    else:
        xShiftDictNotFound = -0.07
        xShiftDict = {
            "2": -0.057,
            "3": -0.067,
            "4": -0.07,
            "5": -0.075,
            "6": -0.078,
            "7": -0.08,
            "8": -0.08,
            "9": -0.08,
            "10": -0.08,
            # "11":-35,
            # "12":-30,
            # "13":-25,
            # "14":-20,
            # "15":-15,
            # "16":-15,
            # "17":-10,
            # "18":-5,
            # "19":-5,
            # "20":-0,
            # "21":-0,
            # "22":-5,
            # "23":0,
            # "24":+5,
            # "25":0,
        }
    if numberOfColumns in xShiftDict:
        ax = xShiftDict[numberOfColumns]
    else:
        ax = xShiftDictNotFound
    return ax
