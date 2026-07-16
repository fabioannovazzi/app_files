"""Headless-compatible legacy chart orchestration entrypoints.

This module intentionally exposes selected ``plot_charts.*`` functions in the
variance-compatible vendor tree. The functions keep the legacy orchestration
shape and finish through ``set_up_tab_for_show_or_download_chart`` so callers can
capture Plotly figures and chart-ready data through ``HeadlessChartCapture``.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

import polars as pl

from modules.charting.adjust_position import move_labels_up
from modules.charting.chart_helpers import (
    make_one_dimensional_variance_subplots,
    set_up_tab_for_show_or_download_chart,
)
from modules.charting.chart_primitives import (
    add_message_as_annotation,
    add_title_as_annotation,
    enable_draw_shapes,
    get_user_message,
)
from modules.charting.draw_charts_utils import (
    get_chart_scale,
    get_polars_value_at_index,
)
from modules.charting.draw_waterfall import (
    _delete_black_vertical_lines,
    _legacy_color_first_bar_shape,
    _legacy_delta_annotation,
    _legacy_line_shape,
    _order_legacy_small_multiple_rows,
    _prefix_legacy_small_multiple_axis_labels,
    _replace_legacy_period_labels,
)
from modules.charting.legacy_draw_waterfall import (
    color_first_bar_vertical,
    draw_vertical_waterfall_chart,
)
from modules.charting.make_titles import make_vertical_waterfall_chart_title
from modules.charting.prepare_charts import add_total_variance_arrow_vertical
from modules.charting.update_layouts import (
    update_waterfall_layout_small_multiples,
    update_waterfall_layout_variable_dimension,
)
from modules.data.common_data_utils import (
    drop_columns_with_all_blancs,
    get_number_of_multiples,
)
from modules.data.waterfall_data_prep import prepare_data_for_waterfall
from modules.utilities.config import get_config_params, get_naming_params
from modules.utilities.helpers import duplicate_dataframe
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

__all__ = ["plot_root_cause_variable_waterfall", "plot_waterfall_small_multiples"]

LOGGER = logging.getLogger(__name__)


def _reverse_waterfall_y_range(fig: Any) -> Any:
    """Apply the legacy reversed y-axis orientation."""

    fig.update_yaxes(autorange="reversed")
    return fig


def _collect_if_lazy(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Return an eager frame for legacy Plotly calls."""

    return frame.collect() if isinstance(frame, pl.LazyFrame) else frame


def plot_root_cause_variable_waterfall(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    paramDict: dict[str, Any],
    chartDict: dict[str, Any],
    colorDict: dict[str, str],
    run: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the legacy variable-dimension waterfall orchestration headlessly."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    waterfallChart = namingParams["verticalWaterfallChart"]
    configPlotlyDict = configParams["configPlotlyDict"][waterfallChart]
    varianceName = namingParams["varianceName"]
    varianceAnalysisChart = namingParams["varianceAnalysisChart"]
    fixedVarianceScaleChoice = namingParams["fixedVarianceScaleChoice"]
    varianceTypeName = namingParams["varianceTypeName"]
    measureName = namingParams["measureName"]
    varianceAmountName = namingParams["varianceAmountName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    totalAmountPeriodZero = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOne = namingParams["totalAmountPeriodOne"]
    variancePercentChangeName = namingParams["variancePercentChangeName"]
    yearBeforePyName = namingParams["yearBeforePyName"]
    isYearBeforePy = namingParams["isYearBeforePy"]
    periodsArray = configParams["periodsArray"]

    df = _collect_if_lazy(duplicate_dataframe(dfCopy))
    if not is_valid_lazyframe(df):
        LOGGER.warning("No root-cause variable waterfall rows were rendered.")
        return paramDict, chartDict

    df, _dfFiltered, paramDict = prepare_data_for_waterfall(
        df,
        indexCols,
        paramDict,
        chartDict,
        run,
        None,
        None,
        None,
        None,
    )
    if not is_valid_lazyframe(df):
        LOGGER.warning("Root-cause variable waterfall prep returned no rows.")
        return paramDict, chartDict

    paramDict[namingParams["columnHash"]] = paramDict.get(
        namingParams["columnHash"],
        {},
    )
    df, indexCols = drop_columns_with_all_blancs(
        df,
        indexCols,
        indexCols,
        [varianceTypeName],
    )
    df = _collect_if_lazy(df)
    if (
        totalAmountPeriodZero in paramDict
        and totalAmountPeriodOne in paramDict
        and measureName in df.columns
    ):
        period_zero_value = float(paramDict[totalAmountPeriodZero] or 0.0)
        period_one_value = float(paramDict[totalAmountPeriodOne] or 0.0)
        period_zero_column = monetaryName + separatorString + periodsArray[0]
        period_one_column = monetaryName + separatorString + periodsArray[1]
        last_index = pl.len() - 1
        expressions = [
            pl.when((pl.col(measureName) == "absolute") & (pl.col("_idx") == 0))
            .then(pl.lit(period_zero_value))
            .when((pl.col(measureName) == "absolute") & (pl.col("_idx") == last_index))
            .then(pl.lit(period_one_value))
            .otherwise(pl.col(varianceAmountName))
            .alias(varianceAmountName),
        ]
        if workColumnTwo in df.columns:
            expressions.append(
                pl.when((pl.col(measureName) == "absolute") & (pl.col("_idx") == 0))
                .then(pl.lit(period_zero_value))
                .when(
                    (pl.col(measureName) == "absolute") & (pl.col("_idx") == last_index)
                )
                .then(pl.lit(period_one_value))
                .otherwise(pl.col(workColumnTwo))
                .alias(workColumnTwo)
            )
        if period_zero_column in df.columns:
            expressions.append(
                pl.when((pl.col(measureName) == "absolute") & (pl.col("_idx") == 0))
                .then(pl.lit(period_zero_value))
                .when(
                    (pl.col(measureName) == "absolute") & (pl.col("_idx") == last_index)
                )
                .then(None)
                .otherwise(pl.col(period_zero_column))
                .alias(period_zero_column)
            )
        if period_one_column in df.columns:
            expressions.append(
                pl.when((pl.col(measureName) == "absolute") & (pl.col("_idx") == 0))
                .then(None)
                .when(
                    (pl.col(measureName) == "absolute") & (pl.col("_idx") == last_index)
                )
                .then(pl.lit(period_one_value))
                .otherwise(pl.col(period_one_column))
                .alias(period_one_column)
            )
        if variancePercentChangeName in df.columns:
            expressions.append(
                pl.when(pl.col(measureName) == "absolute")
                .then(None)
                .otherwise(pl.col(variancePercentChangeName))
                .alias(variancePercentChangeName)
            )
        df = df.with_row_index("_idx").with_columns(expressions).drop("_idx")
    fig, _numberFormat, chartDict = draw_vertical_waterfall_chart(
        df,
        colorDict,
        paramDict,
        chartDict,
        run,
    )
    fig = add_total_variance_arrow_vertical(
        df,
        fig,
        paramDict,
        chartDict,
        colorDict,
        run,
    )
    fig = color_first_bar_vertical(df, fig, paramDict, chartDict, colorDict, run)
    if plName == get_polars_value_at_index(df, workColumn, 0):
        pyName = plName
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
        pyName = yearBeforePyName
    title, paramDict, chartDict = make_vertical_waterfall_chart_title(
        df,
        waterfallChart,
        paramDict,
        None,
        monetaryName,
        chartDict,
        pyName,
        acName,
    )
    fig = update_waterfall_layout_variable_dimension(df, fig, chartDict)
    fig, paramDict = get_chart_scale(
        fig,
        chartDict,
        paramDict,
        "X",
        varianceName,
        varianceAnalysisChart,
        fixedVarianceScaleChoice,
    )
    fig = _reverse_waterfall_y_range(fig)
    fig, message = get_user_message(
        fig,
        waterfallChart,
        "",
        str(run),
        paramDict,
        chartDict,
        df,
        None,
        None,
    )
    fig = add_message_as_annotation(
        fig,
        message,
        None,
        waterfallChart,
        chartDict,
        paramDict,
    )
    fig = add_title_as_annotation(fig, title, waterfallChart, chartDict)
    fig = enable_draw_shapes(fig)
    fig = _delete_black_vertical_lines(fig)
    paramDict = set_up_tab_for_show_or_download_chart(
        df,
        fig,
        configPlotlyDict,
        chartDict,
        "",
        True,
        run,
        None,
        paramDict,
    )
    return paramDict, chartDict


def plot_waterfall_small_multiples(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    dfBaseCopy: pl.DataFrame | pl.LazyFrame,
    indexColsCopy: list[str],
    paramDict: dict[str, Any],
    chartDict: dict[str, Any],
    colorDict: dict[str, str],
    run: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the legacy variance waterfall small-multiple orchestration."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    waterfallChart = namingParams["verticalWaterfallChart"]
    configPlotlyDict = configParams["configPlotlyDict"][waterfallChart]
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    workColumn = namingParams["workColumn"]
    varianceAmountName = namingParams["varianceAmountName"]
    varianceTypeName = namingParams["varianceTypeName"]
    mainDimensionKey = namingParams["mainDimension"]
    smallMultiplesWaterfall = namingParams["smallMultiplesWaterfall"]
    numberOfPlots = namingParams["numberOfPlots"]
    nothingThereString = namingParams["nothingThereString"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    yearBeforePyName = namingParams["yearBeforePyName"]
    isYearBeforePy = namingParams["isYearBeforePy"]
    selectedPeriods = namingParams["selectedPeriods"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    varianceAggregation = namingParams["varianceAggregation"]

    mainDimension = chartDict[mainDimensionKey][0]
    usesUnits = chartDict[varianceAggregation] in {
        namingParams["priceAndUnitsAggregation"],
        namingParams["mixAndUnitsAggregation"],
    }
    panelRecipe = {
        "mappings": {
            "baseline_period": chartDict[selectedPeriods][0],
            "comparison_period": chartDict[selectedPeriods][1],
            "units_column": usesUnits,
        }
    }
    showItems = [
        str(item) for item in chartDict.get(smallMultiplesWaterfall, []) if str(item)
    ]
    if not showItems:
        showItems = get_number_of_multiples(dfCopy, mainDimension, chartDict)
    if not is_valid_lazyframe(dfCopy):
        return paramDict, chartDict

    chartDict[smallMultiplesWaterfall] = showItems
    (
        fig,
        countRows,
        countCols,
        count,
        numberOfCols,
        numberOfRows,
    ) = make_one_dimensional_variance_subplots(showItems, numberOfCols=3)
    panelTitleAnnotations = list(fig.layout.annotations or ())
    df = _collect_if_lazy(duplicate_dataframe(dfCopy))
    shapeArray: list[dict[str, Any]] = []
    periodZeroLineArray: list[dict[str, Any]] = []
    periodOneLineArray: list[dict[str, Any]] = []
    arrowArray: list[dict[str, Any]] = []
    annotationArrowArray: list[dict[str, Any]] = []
    annotationTextArray: list[dict[str, Any]] = []
    numberOfCharts = len(showItems)
    paramDict[numberOfPlots] = numberOfCharts
    frameArray: list[pl.DataFrame] = []
    lastFiltered: pl.DataFrame | None = None

    for element in showItems:
        panelGrouped = df.filter(pl.col(mainDimension) == element)
        if panelGrouped.is_empty() or element == nothingThereString:
            continue
        dfFiltered = panelGrouped.drop(mainDimension)
        dfBase = _collect_if_lazy(duplicate_dataframe(dfBaseCopy))

        dfFiltered, dfBase, paramDict = prepare_data_for_waterfall(
            dfFiltered,
            [],
            paramDict,
            chartDict,
            run,
            mainDimension,
            element,
            dfBase,
            count,
        )
        dfFiltered = _replace_legacy_period_labels(
            dfFiltered, panelRecipe, namingParams
        )
        dfFiltered = _order_legacy_small_multiple_rows(
            dfFiltered,
            panelRecipe,
            namingParams,
            chartDict[varianceAggregation],
        )
        dfFiltered, labelMap, tickValues, tickText = (
            _prefix_legacy_small_multiple_axis_labels(
                dfFiltered,
                panelRecipe,
                namingParams,
                chartDict[varianceAggregation],
            )
        )
        dfFiltered = _collect_if_lazy(dfFiltered)
        lastFiltered = dfFiltered
        panelChart = copy.deepcopy(chartDict)
        panelChart[selectedPeriods] = [
            labelMap.get(chartDict[selectedPeriods][0], chartDict[selectedPeriods][0]),
            labelMap.get(chartDict[selectedPeriods][1], chartDict[selectedPeriods][1]),
        ]
        figDet, _numberFormat, _panelChart = draw_vertical_waterfall_chart(
            dfFiltered, colorDict, paramDict, panelChart, run
        )
        fig.add_trace(figDet["data"][0], row=countRows, col=countCols)
        fig.update_yaxes(
            tickmode="array",
            tickvals=tickValues,
            ticktext=tickText,
            categoryorder="array",
            categoryarray=tickValues,
            row=countRows,
            col=countCols,
        )
        fig.update_annotations(font={"size": fontSize, "family": font})
        fig = move_labels_up(fig, panelChart, showItems)
        shapeArray = _legacy_color_first_bar_shape(
            dfFiltered, paramDict, panelChart, colorDict, run, count, shapeArray
        )
        dfLazyFiltered = ensure_lazyframe(dfFiltered)
        periodOneValue = get_polars_value_at_index(
            dfLazyFiltered.filter(pl.col(workColumn) == panelChart[selectedPeriods][1]),
            varianceAmountName,
            0,
        )
        periodZeroValue = get_polars_value_at_index(
            dfLazyFiltered,
            varianceAmountName,
            0,
        )
        periodZeroLineArray = _legacy_line_shape(
            dfFiltered,
            paramDict,
            panelChart,
            colorDict,
            run,
            count,
            periodZeroLineArray,
            periodZeroValue,
            periodZeroValue,
            numberOfCharts,
            is_arrow=False,
            is_period_zero=True,
            count_rows=countRows,
        )
        periodOneLineArray = _legacy_line_shape(
            dfFiltered,
            paramDict,
            panelChart,
            colorDict,
            run,
            count,
            periodOneLineArray,
            periodOneValue,
            periodOneValue,
            numberOfCharts,
            is_arrow=False,
            is_period_zero=False,
            count_rows=countRows,
        )
        arrowArray = _legacy_line_shape(
            dfFiltered,
            paramDict,
            panelChart,
            colorDict,
            run,
            count,
            arrowArray,
            periodZeroValue,
            periodOneValue,
            numberOfCharts,
            is_arrow=True,
            is_period_zero=False,
            count_rows=countRows,
        )
        annotationArrowArray = _legacy_delta_annotation(
            dfFiltered,
            paramDict,
            panelChart,
            colorDict,
            run,
            count,
            annotationArrowArray,
            numberOfCharts,
            is_text=False,
            is_arrow=True,
            count_rows=countRows,
        )
        annotationTextArray = _legacy_delta_annotation(
            dfFiltered,
            paramDict,
            panelChart,
            colorDict,
            run,
            count,
            annotationTextArray,
            numberOfCharts,
            is_text=True,
            is_arrow=False,
            count_rows=countRows,
        )
        dfDim = dfFiltered.with_columns(pl.lit(element).alias(mainDimension))
        cols, _schema = get_schema_and_column_names(dfDim)
        dfDim = dfDim.select(
            [mainDimension] + [col for col in cols if col != mainDimension]
        )
        frameArray.append(dfDim)
        if countCols < numberOfCols:
            countCols += 1
        else:
            countCols = 1
            countRows += 1
        count += 1

    if not frameArray or lastFiltered is None:
        LOGGER.warning("No waterfall small-multiple panels were rendered.")
        return paramDict, chartDict

    dfExport = pl.concat(frameArray, how="diagonal_relaxed")
    fig.update_layout(
        shapes=shapeArray + periodZeroLineArray + periodOneLineArray + arrowArray,
        annotations=panelTitleAnnotations + annotationArrowArray + annotationTextArray,
    )
    if plName == get_polars_value_at_index(lastFiltered, workColumn, 0):
        pyName = plName
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
        pyName = yearBeforePyName
    title, paramDict, chartDict = make_vertical_waterfall_chart_title(
        lastFiltered,
        waterfallChart,
        paramDict,
        mainDimension,
        monetaryName,
        chartDict,
        pyName,
        acName,
    )
    fig, width = update_waterfall_layout_small_multiples(
        lastFiltered, fig, chartDict, numberOfRows, numberOfCols
    )
    fig = _reverse_waterfall_y_range(fig)
    fig, message = get_user_message(
        fig,
        waterfallChart,
        "",
        plotSmallMultiples,
        paramDict,
        chartDict,
        lastFiltered,
        width,
        None,
    )
    fig = add_message_as_annotation(
        fig, message, None, waterfallChart, chartDict, paramDict
    )
    fig = add_title_as_annotation(fig, title, waterfallChart, chartDict)
    fig = enable_draw_shapes(fig)
    fig = _delete_black_vertical_lines(fig)
    paramDict = set_up_tab_for_show_or_download_chart(
        dfExport, fig, configPlotlyDict, chartDict, title, True, run, None, paramDict
    )
    return paramDict, chartDict
