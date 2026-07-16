import copy
import logging
import math

import numpy as np
import plotly.express as px
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_helpers import (
    download_chart_dataframe,
    exclude_outliers_from_chart,
    filter_alternate_results,
    filter_loop_data,
    prepare_actual_vs_year_ago_dataframe,
)
from modules.charting.plot_charts import (
    plot_actual_vs_previous_year_charts,
    plot_alternative_combinations_plotly,
    plot_area_charts,
    plot_boxplot_charts,
    plot_bubble_charts,
    plot_dot_chart,
    plot_ecdf_charts,
    plot_histogram_charts,
    plot_horizontal_waterfall_chart,
    plot_kernel_density_charts,
    plot_mekko_charts,
    plot_motion_charts,
    plot_multitier_bar_chart,
    plot_multitier_column_chart,
    plot_pareto_chart,
    plot_scatter_charts,
    plot_slope_charts,
    plot_stacked_bar_charts,
    plot_stacked_column_charts,
    plot_stacked_pareto_chart,
    plot_stripplot_charts,
    plot_timeline_charts,
    plot_trend_comparison_charts,
    plot_upset_chart,
    plot_venn_chart,
)
from modules.charting.prepare_charts import make_smaller_sampled_dataframe
from modules.data.common_data_utils import get_row_data_from_original_df
from modules.layout.performance import display_performance_metrics
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    add_price_to_value_cols,
    add_promo_metric_to_valuecols,
    calculate_unit_and_volume_price,
    drop_rows_with_negative_values,
    duplicate_dataframe,
    measure_time,
    print_error_details,
    process_if_promo_data,
)
from modules.utilities.ui_notifier import Notifier, NullNotifier
from modules.utilities.utils import get_row_count, is_valid_lazyframe


def _resolve_notifier(notifier: Notifier | None) -> Notifier:
    return notifier or NullNotifier()


def run_charting(
    dfDict,
    indexCols,
    valueCols,
    paramDict,
    chartDict,
    _expander,
    notifier: Notifier | None = None,
) -> tuple[dict, str]:
    """Structure data and produce charts.

    Returns the (possibly updated) ``paramDict`` and a sampling message.
    The message is empty when no sampling was required.
    """
    notify = _resolve_notifier(notifier)
    namingParams = get_naming_params()
    rowToPlot = namingParams["rowToPlotName"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    dotChart = namingParams["dotChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    areaChart = namingParams["areaChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    chosenChart = namingParams["chosenChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    alternativeCombinationsChart = namingParams["alternativeCombinationsChart"]
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    dfName = namingParams["dfName"]
    dfMainReportName = namingParams["dfMainReportName"]
    dfPeriodsName = namingParams["dfPeriodsName"]
    dfAllPeriodsName = namingParams["dfAllPeriodsName"]
    dfDatesName = namingParams["dfDatesName"]
    dfSnapshotName = namingParams["dfSnapshotName"]
    entireDatasetName = namingParams["entireDatasetName"]
    chartMetrics = namingParams["chartMetrics"]
    datasetChoice = namingParams["datasetChoice"]
    filterName = namingParams["filterName"]
    selectedPeriods = namingParams["selectedPeriods"]
    filterDates = namingParams["filterDates"]
    datePeriodName = namingParams["datePeriodName"]
    isFilteredKey = namingParams["isFilteredKey"]
    varianceAnalysisChart = namingParams["varianceAnalysisChart"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    charting = namingParams["chartingName"]
    chartingEnd = namingParams["chartingEndName"]
    endAll = namingParams["endAllName"]
    errorMessageType = namingParams["errorMessageType"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    sample_message = ""
    if selectedPeriods in chartDict:
        chartDict[datePeriodName] = paramDict[datePeriodName]
    if chosenChart in chartDict:
        chosenChart = chartDict[chosenChart]
    else:
        chosenChart = None
    chartDict[varianceAnalysisChart] = notMetConditionValue
    errorMessage = "No rows to plot in dataset"
    if chosenChart in [
        trendComparisonByPeriodChart,
        areaChart,
        bubbleChart,
        motionChart,
        dotChart,
        multitierBarChart,
        multitierColumnChart,
        horizontalWaterfallChart,
        scatterChart,
        slopeChart,
        stackedColumnChart,
        stackedBarChart,
        timelineChart,
        trendComparisonChart,
    ]:
        valueColsWithPrice = add_price_to_value_cols(valueCols, dfDict[dfPeriodsName])
    if (
        chosenChart
        in [
            areaChart,
            trendComparisonByPeriodChart,
            motionChart,
            timelineChart,
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
        ]
        and get_row_count(dfDict[dfDatesName]) > 0
    ):
        dfCharts = duplicate_dataframe(dfDict[dfDatesName])
        dfCharts = drop_rows_with_negative_values(dfCharts, valueCols, paramDict)
        if chosenChart in [
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
            trendComparisonByPeriodChart,
        ]:
            if filterDates not in chartDict or not chartDict[filterDates]:
                valueCols = add_promo_metric_to_valuecols(
                    dfCharts, paramDict, valueCols
                )
                dfCharts, paramDict = prepare_actual_vs_year_ago_dataframe(
                    dfCharts, chosenChart, valueCols, indexCols, chartDict, paramDict
                )
            else:
                valueCols = add_promo_metric_to_valuecols(
                    dfCharts, paramDict, valueCols
                )
            dfDict[dfDatesName] = dfCharts
        if isFilteredKey in paramDict and paramDict[isFilteredKey]:
            dfDict[filterName] = dfCharts
        chartTimeFormat, chartDict[datasetChoice] = dateName, dateName
    elif chosenChart in [
        barmekkoChart,
        bubbleChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
        dotChart,
        marimekkoChart,
        multitierBarChart,
        scatterChart,
        slopeChart,
        stackedColumnChart,
        stackedBarChart,
    ] and is_valid_lazyframe(dfDict[dfPeriodsName]):
        if chosenChart in [stackedColumnChart, stackedBarChart]:
            dfCharts = duplicate_dataframe(dfDict[dfAllPeriodsName])
            dfCharts = dfCharts.lazy()
        else:
            dfCharts = duplicate_dataframe(dfDict[dfPeriodsName])
        dfCharts = drop_rows_with_negative_values(dfCharts, valueCols, paramDict)
        if isFilteredKey in paramDict and paramDict[isFilteredKey]:
            dfDict[filterName] = dfCharts
        chartTimeFormat, chartDict[datasetChoice] = periodName, periodName
    elif (
        chosenChart in [alternativeCombinationsChart]
        and get_row_count(dfDict[dfSnapshotName]) > 0
    ):
        dfCharts = dfDict[dfSnapshotName]
        dfCharts, dfTop, errorMessage, chartDict = filter_loop_data(
            dfDict, dfCharts, chartDict, errorMessage
        )
        chartTimeFormat, chartDict[datasetChoice] = None, None
    elif chosenChart in [
        barmekkoChart,
        marimekkoChart,
    ]:
        dfCharts = duplicate_dataframe(dfDict[dfPeriodsName])
    elif chosenChart in [vennChart]:
        chartTimeFormat, chartDict[datasetChoice] = periodName, periodName
        dfCharts = duplicate_dataframe(dfDict[dfPeriodsName])
        paramDict = plot_venn_chart(dfCharts, valueCols, chartDict, paramDict)
    elif chosenChart in [upsetChart]:
        chartTimeFormat, chartDict[datasetChoice] = periodName, periodName
        dfCharts = duplicate_dataframe(dfDict[dfPeriodsName])
        paramDict = plot_upset_chart(dfCharts, valueCols, chartDict, paramDict)
    elif chosenChart in [paretoChart, stackedParetoChart]:
        chartTimeFormat, chartDict[datasetChoice] = periodName, periodName
        dfCharts = duplicate_dataframe(dfDict[dfPeriodsName])
        if chosenChart in [paretoChart]:
            paramDict = plot_pareto_chart(dfCharts, chartDict, paramDict)
        if chosenChart in [stackedParetoChart]:
            paramDict = plot_stacked_pareto_chart(dfCharts, chartDict, paramDict)
    else:
        dfCharts = pl.DataFrame()
    numberOfResults = 0
    if is_valid_lazyframe(dfCharts):
        if chartDict[rowToPlot] != entireDatasetName and chartTimeFormat in [
            dateName,
            periodName,
        ]:
            try:
                dfCharts, numberOfResults, chartDict = get_row_data_from_original_df(
                    dfDict, dfCharts, chartDict, indexCols
                )
            except Exception as e:
                logging.exception(e)
                errorMessage = "Error in get_row_data_from_original_df function."
                e = print_error_details(e)
                notify.error("Something went wrong while preparing the row to plot.")
                paramDict = add_app_message_to_paramdict(
                    e,
                    errorMessageType,
                    plotChartsTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=False,
                    colNumber=colNumber,
                )
                paramDict = add_app_message_to_paramdict(
                    errorMessage,
                    errorMessageType,
                    plotChartsTabKey,
                    paramDict,
                    isMessage=True,
                    isToast=True,
                    colNumber=colNumber,
                )
        message = ""
        if chartDict[rowToPlot] == entireDatasetName:
            message = "entire dataset"
        else:
            message = "report row #" + str(chartDict[rowToPlot]) + ""
        chartDict[rowToPlot] = message
        if chosenChart in [
            areaChart,
            multitierBarChart,
            slopeChart,
            stackedColumnChart,
            stackedBarChart,
            timelineChart,
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
        ]:
            valueColsWithPrice = add_promo_metric_to_valuecols(
                dfCharts, paramDict, valueColsWithPrice
            )
            valueCols = add_promo_metric_to_valuecols(dfCharts, paramDict, valueCols)
            if chosenChart in [timelineChart]:
                try:
                    paramDict = plot_timeline_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [trendComparisonChart]:
                try:
                    paramDict = plot_trend_comparison_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [areaChart]:
                try:
                    paramDict = plot_area_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [slopeChart]:
                try:
                    paramDict = plot_slope_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [stackedColumnChart]:
                try:
                    paramDict = plot_stacked_column_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [stackedBarChart]:
                try:
                    paramDict = plot_stacked_bar_charts(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [multitierBarChart]:
                try:
                    paramDict = plot_multitier_bar_chart(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [multitierColumnChart]:
                try:
                    paramDict = plot_multitier_column_chart(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
            elif chosenChart in [horizontalWaterfallChart]:
                try:
                    paramDict = plot_horizontal_waterfall_chart(
                        dfCharts,
                        indexCols,
                        valueCols,
                        chartDict,
                        valueColsWithPrice,
                        chartTimeFormat,
                        paramDict,
                        dfDict,
                    )
                except Exception as e:
                    logging.exception(e)
                    notify.error(
                        "Something went wrong while plotting.",
                        chart=chosenChart,
                    )
                    return paramDict, None
        if chosenChart in [dotChart]:
            try:
                valueColsWithPrice = add_promo_metric_to_valuecols(
                    dfCharts, paramDict, valueColsWithPrice
                )
                valueCols = add_promo_metric_to_valuecols(
                    dfCharts, paramDict, valueCols
                )
                paramDict = plot_dot_chart(
                    dfCharts,
                    indexCols,
                    valueCols,
                    chartDict,
                    valueColsWithPrice,
                    chartTimeFormat,
                    paramDict,
                    dfDict,
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        elif chosenChart in [marimekkoChart, barmekkoChart]:
            try:
                paramDict = plot_mekko_charts(
                    dfCharts, valueCols, chartDict, chartTimeFormat, paramDict
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        elif chosenChart in [
            kernelDensity,
            histogramChart,
            boxplotChart,
            ecdfChart,
            stripplotChart,
        ]:
            dfCharts, sample_message = make_smaller_sampled_dataframe(
                dfCharts, kernelDensity
            )
            dfCharts, paramDict, valueCols = calculate_unit_and_volume_price(
                dfCharts, paramDict, valueCols
            )
            if chosenChart in [kernelDensity, histogramChart]:
                dfCharts = exclude_outliers_from_chart(dfCharts, chartDict).collect()
            if get_row_count(dfCharts) > 2:
                if chosenChart in [kernelDensity]:
                    try:
                        paramDict = plot_kernel_density_charts(
                            dfCharts,
                            indexCols,
                            valueCols,
                            chartDict,
                            chartTimeFormat,
                            paramDict,
                        )
                    except Exception as e:
                        logging.exception(e)
                        notify.error(
                            "Something went wrong while plotting.",
                            chart=chosenChart,
                        )
                        return paramDict, None
                elif chosenChart in [histogramChart]:
                    try:
                        paramDict = plot_histogram_charts(
                            dfCharts,
                            indexCols,
                            valueCols,
                            chartDict,
                            chartTimeFormat,
                            paramDict,
                        )
                    except Exception as e:
                        logging.exception(e)
                        notify.error(
                            "Something went wrong while plotting.",
                            chart=chosenChart,
                        )
                        return paramDict, None
                elif chosenChart in [ecdfChart]:
                    try:
                        paramDict = plot_ecdf_charts(
                            dfCharts,
                            indexCols,
                            valueCols,
                            chartDict,
                            chartTimeFormat,
                            paramDict,
                        )
                    except Exception as e:
                        logging.exception(e)
                        notify.error(
                            "Something went wrong while plotting.",
                            chart=chosenChart,
                        )
                        return paramDict, None
                elif chosenChart in [boxplotChart]:
                    try:
                        paramDict = plot_boxplot_charts(
                            dfCharts,
                            indexCols,
                            valueCols,
                            chartDict,
                            chartTimeFormat,
                            paramDict,
                        )
                    except Exception as e:
                        logging.exception(e)
                        notify.error(
                            "Something went wrong while plotting.",
                            chart=chosenChart,
                        )
                        return paramDict, None
                elif chosenChart in [stripplotChart]:
                    try:
                        paramDict = plot_stripplot_charts(
                            dfCharts,
                            indexCols,
                            valueCols,
                            chartDict,
                            chartTimeFormat,
                            paramDict,
                        )
                    except Exception as e:
                        logging.exception(e)
                        notify.error(
                            "Something went wrong while plotting.",
                            chart=chosenChart,
                        )
                        return paramDict, None
            else:
                errorMessage = "Not enough rows to plot chart."
                notify.notify(
                    "info",
                    errorMessage,
                    {"format": "markdown"},
                )
        elif chosenChart in [bubbleChart]:
            valueColsWithPrice = add_promo_metric_to_valuecols(
                dfCharts, paramDict, valueColsWithPrice
            )
            valueCols = add_promo_metric_to_valuecols(dfCharts, paramDict, valueCols)
            dfCharts, paramDict, valueColsWithPrice = process_if_promo_data(
                dfCharts, paramDict, valueColsWithPrice
            )
            try:
                paramDict = plot_bubble_charts(
                    dfCharts,
                    indexCols,
                    valueCols,
                    chartDict,
                    chartTimeFormat,
                    paramDict,
                    dfDict,
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        elif chosenChart in [motionChart]:
            valueColsWithPrice = add_promo_metric_to_valuecols(
                dfCharts, paramDict, valueColsWithPrice
            )
            valueCols = add_promo_metric_to_valuecols(dfCharts, paramDict, valueCols)
            dfCharts, paramDict, valueColsWithPrice = process_if_promo_data(
                dfCharts, paramDict, valueColsWithPrice
            )
            try:
                paramDict = plot_motion_charts(
                    dfCharts,
                    indexCols,
                    valueCols,
                    chartDict,
                    chartTimeFormat,
                    paramDict,
                    dfDict,
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        elif chosenChart in [alternativeCombinationsChart]:
            dfResult = filter_alternate_results(dfCharts, dfTop, indexCols)
            paramDict = plot_alternative_combinations_plotly(
                dfResult, chartDict, paramDict
            )
        elif chosenChart in [scatterChart]:
            valueColsWithPrice = add_promo_metric_to_valuecols(
                dfCharts, paramDict, valueColsWithPrice
            )
            valueCols = add_promo_metric_to_valuecols(dfCharts, paramDict, valueCols)
            dfCharts, paramDict, chartDict[chartMetrics] = process_if_promo_data(
                dfCharts, paramDict, valueColsWithPrice
            )
            try:
                paramDict = plot_scatter_charts(
                    dfCharts,
                    indexCols,
                    valueCols,
                    chartDict,
                    valueColsWithPrice,
                    chartTimeFormat,
                    paramDict,
                    dfDict,
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        elif chosenChart in [trendComparisonByPeriodChart]:
            valueColsWithPrice = add_promo_metric_to_valuecols(
                dfCharts, paramDict, valueColsWithPrice
            )
            valueCols = add_promo_metric_to_valuecols(dfCharts, paramDict, valueCols)
            try:
                paramDict, chartDict = plot_actual_vs_previous_year_charts(
                    dfCharts,
                    indexCols,
                    valueCols,
                    chartDict,
                    valueColsWithPrice,
                    paramDict,
                    dfDict,
                )
            except Exception as e:
                logging.exception(e)
                notify.error(
                    "Something went wrong while plotting.",
                    chart=chosenChart,
                )
                return paramDict, None
        download_chart_dataframe(chartDict, dfCharts, _expander)
        perf = measure_time(charting, chartingEnd, False)
        display_performance_metrics(perf, notifier=notify)
        perf = measure_time(endAll, endAll, True)
        display_performance_metrics(perf, notifier=notify)
    else:
        notify.notify(
            "info",
            errorMessage,
            {"format": "markdown"},
        )
    return paramDict, sample_message
