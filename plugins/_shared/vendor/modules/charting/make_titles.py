import copy
import datetime as dt
import logging
import math

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_helpers import (
    correct_prefix_if_two_metric,
    get_filter_text_or_company_name,
    make_like_for_like_title_suffix,
    set_break_row_tag,
)
from modules.charting.chart_primitives import change_metric_if_cost_analysis
from modules.llm.interpret_plots import (
    explain_metrics_for_barmekko_prompt,
    explain_metrics_for_stacked_column_prompt,
)
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import (
    get_currency_name,
    get_rolling_and_year_to_date_period,
)
from modules.utilities.ui_notifier import Notifier, NullNotifier
from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names


def _resolve_notifier(notifier: Notifier | None) -> Notifier:
    return notifier or NullNotifier()


def make_stacked_column_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    percentSuffix = namingParams["percentSuffix"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    metricsToPlot = namingParams["metricsToPlot"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    plotTitleText = namingParams["plotTitleText"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    if metricsToPlot in chartDict and (not dimension or dimension == totalName):
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            count = 0
            metric = ""
            for value in chartDict[metricsToPlot]:
                value = change_metric_if_cost_analysis(value, chartDict)
                separator = " "
                if count > 0:
                    separator = ", "
                metric = metric + separator + value
                count = count + 1
        else:
            metric = change_metric_if_cost_analysis(metric, chartDict)
    else:
        metric = change_metric_if_cost_analysis(metric, chartDict)
    if element:
        element = get_rolling_and_year_to_date_period(
            element, paramDict, chartDict, False
        )
        period = period1 + " to " + element
    else:
        period1 = get_rolling_and_year_to_date_period(
            period1, paramDict, chartDict, False
        )
        period = period1
    if dimension == totalName:
        dimension = ""
    elif dimension != totalName:
        dimension = " by " + dimension
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName
    overlayOne, overlayTwo = "", ""
    if (
        overlayChartMetricKey in chartDict
        and metricsToPlot in chartDict
        and len(chartDict[metricsToPlot]) > 1
    ):
        secondMetric = change_metric_if_cost_analysis(
            chartDict[metricsToPlot][1], chartDict
        )
        linecurrencyName, paramDict = get_currency_name(
            chartDict, paramDict, chartDict[metricsToPlot][1]
        )
        chartDict = explain_metrics_for_stacked_column_prompt(
            chartDict, currencyName, linecurrencyName, metric, secondMetric
        )
        if linecurrencyName:
            linecurrencyName = " in " + linecurrencyName
        overlayOne = "Bar chart: "
        overlayTwo = ". Line chart: " + "<b>" + secondMetric + "</b>" + linecurrencyName
    title = (
        companyName
        + breakTag
        + overlayOne
        + "<b>"
        + metric
        + "</b>"
        + currencyTag
        + overlayTwo
        + dimension
        + " "
        + likeForLikeMessage
        + breakTag
        + period
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_stacked_pareto_and_pareto_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    countColumn = namingParams["countColumn"]
    selectedPeriods = namingParams["selectedPeriods"]
    plotTitleText = namingParams["plotTitleText"]
    periodOrder = chartDict[selectedPeriods]
    rankingMetric = ""
    isPeriodZero = False
    if period1 == periodOrder[0]:
        isPeriodZero = True
    period1 = get_rolling_and_year_to_date_period(
        period1, paramDict, chartDict, isPeriodZero
    )
    if (
        aggregateUniquesByDimension in chartDict
        and chartDict[aggregateUniquesByDimension]
    ):
        rankingMetric = ", count by " + chartDict[countColumn]
    metric = change_metric_if_cost_analysis(metric, chartDict)
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + ""
    title = (
        companyName
        + breakTag
        + "ABC by sorted "
        + dimension
        + " "
        + metric
        + " "
        + currencyTag
        + rankingMetric
        + likeForLikeMessage
        + breakTag
        + period1
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_distribution_charts_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    distributionDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    plotTitleText = namingParams["plotTitleText"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    period1 = get_rolling_and_year_to_date_period(period1, paramDict, chartDict, True)
    element = get_rolling_and_year_to_date_period(element, paramDict, chartDict, False)
    metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    if (
        distributionDimension in chartDict
        and chartDict[distributionDimension] != nothingFilteredName
    ):
        distributionDimension = " aggregated by " + chartDict[distributionDimension]
    else:
        distributionDimension = " by observation"
    if dimension != "None" and dimension != totalName:
        dimension = " by " + dimension + " "
    else:
        dimension = ""
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + ", "
    title = (
        companyName
        + breakTag
        + "<b>"
        + metric
        + "</b> "
        + currencyTag
        + distributionDimension
        + dimension
        + " "
        + likeForLikeMessage
        + breakTag
        + period1
        + " vs "
        + element
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_slope_and_dot_chart_title(
    df,
    chosenChart,
    paramDict,
    dimension,
    metric,
    chartDict,
    period1,
    element,
    notifier: Notifier | None = None,
):
    notify = _resolve_notifier(notifier)
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    datePeriodName = namingParams["datePeriodName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]
    dotChart = namingParams["dotChart"]
    blackLabelChoice = namingParams["blackLabelChoice"]
    whiteLabelChoice = namingParams["whiteLabelChoice"]
    greyLabelChoice = namingParams["greyLabelChoice"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    metricsToPlot = namingParams["metricsToPlot"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    pyName = namingParams["pyName"]
    plotTitleText = namingParams["plotTitleText"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    period1 = get_rolling_and_year_to_date_period(period1, paramDict, chartDict, True)
    element = get_rolling_and_year_to_date_period(element, paramDict, chartDict, False)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    if metricsToPlot in chartDict and (not dimension or dimension == totalName):
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            count = 0
            metric = ""
            for value in chartDict[metricsToPlot]:
                value = change_metric_if_cost_analysis(value, chartDict)
                separator = " "
                if count > 0:
                    separator = ", "
                metric = metric + separator + value
                count = count + 1
        else:
            metric = change_metric_if_cost_analysis(metric, chartDict)
    else:
        metric = change_metric_if_cost_analysis(metric, chartDict)
    if datePeriodName in paramDict and paramDict[datePeriodName] in [
        quarterName,
        monthName,
        weekName,
    ]:
        try:
            period1 = period1.upper()
            element = element.upper()
        except Exception as e:
            logging.exception(e)
            notify.error("Something went wrong while uppercasing the period label.")
    if chosenChart == dotChart:
        if acName in period1:
            period1 = period1 + blackLabelChoice
            element = element + whiteLabelChoice
        elif plName in period1:
            period1 = period1 + whiteLabelChoice
            element = element + blackLabelChoice
        else:
            period1 = period1 + greyLabelChoice
            element = element + blackLabelChoice
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    if dimension == totalName:
        title = (
            companyName
            + breakTag
            + "<b>"
            + metric
            + "</b>"
            + currencyTag
            + likeForLikeMessage
            + breakTag
            + period1
            + " vs "
            + element
        )
    else:
        title = (
            companyName
            + breakTag
            + "<b>"
            + metric
            + "</b>"
            + currencyTag
            + likeForLikeMessage
            + " by "
            + dimension
            + " "
            + breakTag
            + period1
            + " vs "
            + element
        )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_marimekko_and_stacked_bar_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    dateRangeArray = namingParams["dateRangeArray"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    selectedPeriods = namingParams["selectedPeriods"]
    barmekkoChart = namingParams["barmekkoChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    plName = namingParams["plName"]
    acName = namingParams["acName"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    multipliedMetric = namingParams["multipliedMetric"]
    hyphenName = namingParams["hyphenName"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricArrayKey = namingParams["metricArrayKey"]
    plotTitleText = namingParams["plotTitleText"]
    metricsToPlot = namingParams["metricsToPlot"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    chartDict = correct_prefix_if_two_metric(chartDict, metric)
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    columns, schema = get_schema_and_column_names(df)
    if element:
        pass
    else:
        element = ""
    areaMetric = ""
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = (
            str(chartDict[dateRangeArray][0]).replace(hyphenName, "/")
            + "-"
            + str(chartDict[dateRangeArray][1]).replace(hyphenName, "/")
        )
    elif plName in columns or plName in chartDict[selectedPeriods]:
        duration = ""
    else:
        periodsArray = chartDict[selectedPeriods]
        duration = False
        if len(periodsArray) == 2:
            duration = periodsArray[1]
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = get_rolling_and_year_to_date_period(
            duration, paramDict, chartDict, False
        )
    elif duration == period1:
        duration = get_rolling_and_year_to_date_period(
            duration, paramDict, chartDict, False
        )
    else:
        duration = get_rolling_and_year_to_date_period(
            period1, paramDict, chartDict, True
        )
    separator = " and "
    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        separator, element = "", ""
    if chosenChart in [barmekkoChart]:
        separator = ". Bar width: "
        element = change_metric_if_cost_analysis(element, chartDict)
        secondCurrency, paramDict = get_currency_name(chartDict, paramDict, element)
        secondCurrencyTag = ""
        if secondCurrency:
            secondCurrencyTag = " in " + secondCurrency + ""
        areaMetric = ". Bar area: "
        multipliedMetric = change_metric_if_cost_analysis(
            chartDict[multipliedMetric], chartDict
        )
        thirdCurrency, paramDict = get_currency_name(
            chartDict, paramDict, multipliedMetric
        )
        thirdCurrencyTag = ""
        if thirdCurrency:
            thirdCurrencyTag = " in " + thirdCurrency + ""
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        period = duration + " " + period1
    elif duration and len(duration) > 0:
        period = duration
    else:
        period = period1
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + ""
    facet_suffix = ""
    if (
        plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
        and chosenChart in [barmekkoChart, marimekkoChart]
    ):
        facet_dimension = chartDict.get(smallMultiplesColumn, "")
        if facet_dimension:
            facet_suffix = " | faceted by " + str(facet_dimension)

    if chosenChart in [barmekkoChart]:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            dimension = chartDict[smallMultiplesColumn] + " and " + dimension
        chartDict = explain_metrics_for_barmekko_prompt(
            chartDict, currencyName, secondCurrency, thirdCurrency, metric, element
        )
        title = (
            companyName
            + breakTag
            + "Bar length: "
            + "<b>"
            + metric
            + "</b>"
            + currencyTag
            + likeForLikeMessage
            + " by "
            + dimension
            + separator
            + "<b>"
            + element
            + "</b>"
            + secondCurrencyTag
            + areaMetric
            + "<b>"
            + multipliedMetric
            + "</b>"
            + thirdCurrencyTag
            + facet_suffix
            + breakTag
            + period
        )
    else:
        if (
            chosenChart in [stackedBarChart, marimekkoChart, barmekkoChart]
            and plotSmallMultiplesKey in chartDict
            and chartDict[plotSmallMultiplesKey]
        ):
            if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
                nothingFilteredName
            ]:
                dimension = chartDict[smallMultiplesColumn] + " and " + dimension
            else:
                dimension = chartDict[smallMultiplesColumn] + ", " + dimension
        title = (
            companyName
            + "<b>"
            + breakTag
            + metric
            + "</b>"
            + currencyTag
            + likeForLikeMessage
            + " by "
            + dimension
            + separator
            + element
            + facet_suffix
            + " "
            + breakTag
            + period
        )
    if (
        overlayChartMetricKey in chartDict
        and metricsToPlot in chartDict
        and len(chartDict[metricsToPlot]) > 1
    ):
        secondMetric = change_metric_if_cost_analysis(
            chartDict[metricsToPlot][1], chartDict
        )
        linecurrencyName, paramDict = get_currency_name(
            chartDict, paramDict, chartDict[metricsToPlot][1]
        )
        chartDict = explain_metrics_for_stacked_column_prompt(
            chartDict, currencyName, linecurrencyName, metric, secondMetric
        )
        if linecurrencyName:
            linecurrencyName = " in " + linecurrencyName
        overlayOne = "Bar chart: "
        overlayTwo = ". Markers: " + "<b>" + secondMetric + "</b>" + linecurrencyName
        title = (
            companyName
            + breakTag
            + overlayOne
            + "<b>"
            + metric
            + "</b>"
            + currencyTag
            + overlayTwo
            + ". By "
            + dimension
            + "  "
            + likeForLikeMessage
            + breakTag
            + period
        )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_venn_and_upset_charts_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    selectedPeriods = namingParams["selectedPeriods"]
    periodOrder = chartDict[selectedPeriods]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    selectedPeriods = namingParams["selectedPeriods"]
    plName = namingParams["plName"]
    plotTitleText = namingParams["plotTitleText"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    titleBold = str(metric) + "\\,overlap\\,"
    overlap = r"$\bf{" + titleBold + "}$ "
    dimension = "by " + dimension
    isPeriodZero = False
    columns, schema = get_schema_and_column_names(df)
    if period1 == periodOrder[0]:
        isPeriodZero = True
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = (
            str(chartDict[dateRangeArray][0]).replace(hyphenName, "/")
            + "-"
            + str(chartDict[dateRangeArray][1]).replace(hyphenName, "/")
        )
    elif plName in columns or plName in chartDict[selectedPeriods]:
        duration = ""
    elif len(chartDict[selectedPeriods]) > 1:
        periodsArray = chartDict[selectedPeriods]
        duration = periodsArray[1]
    else:
        duration = ""
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = get_rolling_and_year_to_date_period(
            duration, paramDict, chartDict, False
        )
    elif duration == period1:
        duration = get_rolling_and_year_to_date_period(
            duration, paramDict, chartDict, False
        )
    else:
        duration = get_rolling_and_year_to_date_period(
            period1, paramDict, chartDict, True
        )
    period1 = get_rolling_and_year_to_date_period(
        period1, paramDict, chartDict, isPeriodZero
    )
    title = (
        companyName
        + breakTag
        + element
        + overlap
        + dimension
        + likeForLikeMessage
        + breakTag
        + period1
    )
    title = title.replace("  ", " ")
    title = title.replace("<br>", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_bubble_or_motion_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    dotDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    isolineMetric = namingParams["isolineMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    selectedPeriods = namingParams["selectedPeriods"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    plotTitleText = namingParams["plotTitleText"]
    periodOrder = chartDict[selectedPeriods]
    xDimension = chartDict[xAxisMetric]
    yDimension = chartDict[yAxisMetric]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    metric = change_metric_if_cost_analysis(metric, chartDict)
    yDimension = change_metric_if_cost_analysis(yDimension, chartDict)
    xDimension = change_metric_if_cost_analysis(xDimension, chartDict)
    element = change_metric_if_cost_analysis(element, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    if xDimension is not None and not isinstance(xDimension, bool):
        pass
    else:
        xDimension = ""
    if yDimension is not None and not isinstance(yDimension, bool):
        pass
    else:
        yDimension = ""
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    if chosenChart in [bubbleChart]:
        isPeriodZero = False
        if period1 == periodOrder[0]:
            isPeriodZero = True
        period1 = get_rolling_and_year_to_date_period(
            period1, paramDict, chartDict, isPeriodZero
        )
        if element == totalName:
            dimension = " by " + dimension
            title = (
                companyName
                + breakTag
                + "<b>"
                + yDimension
                + ", "
                + xDimension
                + ", "
                + metric
                + "</b>"
                + currencyTag
                + dimension
                + " "
                + likeForLikeMessage
                + breakTag
                + period1
            )
        else:
            dimension = " by " + dimension + " and " + chartDict[smallMultiplesColumn]
            title = (
                companyName
                + breakTag
                + "<b>"
                + yDimension
                + ", "
                + xDimension
                + ", "
                + metric
                + "</b>"
                + currencyTag
                + dimension
                + " "
                + likeForLikeMessage
                + breakTag
                + period1
            )
    elif chosenChart in [motionChart]:
        title = (
            companyName
            + breakTag
            + "<b>"
            + yDimension
            + ", "
            + xDimension
            + ", "
            + metric
            + "</b>"
            + currencyTag
            + " by "
            + dimension
            + " "
            + likeForLikeMessage
            + breakTag
            + period1[0]
            + " to "
            + period1[-1]
        )
    elif chosenChart in [scatterChart]:
        isolineMetricValue = ""
        if isolineMetric in chartDict and chartDict[isolineMetric]:
            isolineMetricValue = chartDict[isolineMetric]
            isolineMetricValue = change_metric_if_cost_analysis(
                isolineMetricValue, chartDict
            )
            currencyName, paramDict = get_currency_name(
                chartDict, paramDict, isolineMetricValue
            )
            isolineMetricValue = ", " + isolineMetricValue
            currencyTag = ""
            if currencyName:
                currencyTag = " in " + currencyName + " "
        if chartDict[dotDimension] != nothingFilteredName:
            dotDimension = " aggregated by " + chartDict[dotDimension]
        else:
            dotDimension = "by Observation"
        if len(period1) == 1:
            period1 = str(period1[0])
            isPeriodZero = False
            if period1 == periodOrder[0]:
                isPeriodZero = True
            period1 = get_rolling_and_year_to_date_period(
                period1, paramDict, chartDict, isPeriodZero
            )
        elif len(period1) == 2:
            period0 = get_rolling_and_year_to_date_period(
                period1[0], paramDict, chartDict, True
            )
            period1 = get_rolling_and_year_to_date_period(
                period1[1], paramDict, chartDict, False
            )
            period1 = str(period0) + ", " + str(period1)
        if dimension == totalName:
            title = (
                companyName
                + breakTag
                + "<b>"
                + metric
                + ", "
                + element
                + isolineMetricValue
                + " </b>"
                + currencyTag
                + " "
                + dotDimension
                + " "
                + likeForLikeMessage
                + breakTag
                + str(period1)
            )
        else:
            dimension = dotDimension + " and " + dimension
            title = (
                companyName
                + breakTag
                + "<b>"
                + metric
                + ", "
                + element
                + isolineMetricValue
                + " </b>"
                + currencyTag
                + " "
                + dimension
                + " "
                + likeForLikeMessage
                + breakTag
                + str(period1)
            )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_vertical_waterfall_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    selectedPeriods = namingParams["selectedPeriods"]
    varianceAggregation = namingParams["varianceAggregation"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    dateRangeArray = namingParams["dateRangeArray"]
    shareOfTotalMarket = namingParams["shareOfTotalMarket"]
    varianceInPercent = namingParams["varianceInPercent"]
    plotTitleText = namingParams["plotTitleText"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    percentSuffix = namingParams["percentSuffix"]
    hyphenName = namingParams["hyphenName"]
    varianceDifferentCalculations = namingParams["varianceDifferentCalculations"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = namingParams["priceAndVolumeAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    totalVariance = namingParams["totalVariance"]
    mixAndUnitsAggregation = namingParams["mixAndUnitsAggregation"]
    mixAndVolumeAggregation = namingParams["mixAndVolumeAggregation"]
    datasetTypeKey = namingParams["datasetTypeName"]
    companyExpenses = namingParams["companyExpenses"]
    columns, schema = get_schema_and_column_names(df)
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    varianceAggregation = chartDict[varianceAggregation].title()
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = (
            str(chartDict[dateRangeArray][0]).replace(hyphenName, "/")
            + "-"
            + str(chartDict[dateRangeArray][1]).replace(hyphenName, "/")
        )
    elif plName in columns or plName in chartDict[selectedPeriods]:
        duration = ""
    else:
        periodsArray = chartDict[selectedPeriods]
        duration = periodsArray[1]
    duration = get_rolling_and_year_to_date_period(
        duration, paramDict, chartDict, False
    )
    if fcName in columns:
        period = duration + " " + element + ", " + fcName + " vs " + period1
    else:
        period = duration + " " + element + " vs " + period1
    if dimension:
        dimension = " by " + dimension
    else:
        dimension = ""
    if (shareOfTotalMarket in chartDict and chartDict[shareOfTotalMarket]) or (
        varianceInPercent in chartDict and chartDict[varianceInPercent]
    ):
        varianceAggregation = varianceAggregation + percentSuffix
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    if (
        varianceDifferentCalculations in chartDict
        and chartDict[varianceDifferentCalculations]
    ):
        if varianceAggregation in [
            priceAndUnitsAggregation,
            priceAndVolumeAggregation,
            totalVarianceAggregation,
            totalVariance,
            mixAndUnitsAggregation,
            mixAndVolumeAggregation,
        ] or varianceAggregation in [
            priceAndUnitsAggregation.title(),
            priceAndVolumeAggregation.title(),
            totalVarianceAggregation.title(),
            totalVariance.title(),
            mixAndUnitsAggregation.title(),
            mixAndVolumeAggregation.title(),
        ]:
            if chartDict[datasetTypeKey] in [companyExpenses]:
                varianceAggregation = "Cost variance"
            else:
                varianceAggregation = "Sales variance"
        else:
            varianceAggregation = "Margin variance"
    title = (
        companyName
        + breakTag
        + "<b>"
        + varianceAggregation
        + " </b>"
        + currencyTag
        + dimension
        + likeForLikeMessage
        + breakTag
        + period
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_horizontal_waterfall_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    selectedPeriods = namingParams["selectedPeriods"]
    totalName = namingParams["totalName"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    plotTitleText = namingParams["plotTitleText"]
    metricsToPlot = namingParams["metricsToPlot"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    dateRangeArray = namingParams["dateRangeArray"]
    hyphenName = namingParams["hyphenName"]
    plotAsBaseline = namingParams["plotAsBaseline"]
    compareToAverageKey = namingParams["compareToAverage"]
    averageName = namingParams["averageName"]
    varianceName = namingParams["varianceName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    columns, schema = get_schema_and_column_names(df)
    if metricsToPlot in chartDict and (not dimension or dimension == totalName):
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            count = 0
            metric = ""
            for value in chartDict[metricsToPlot]:
                value = change_metric_if_cost_analysis(value, chartDict)
                separator = " "
                if count > 0:
                    separator = ", "
                metric = metric + separator + value
                count = count + 1
        else:
            metric = change_metric_if_cost_analysis(metric, chartDict)
    else:
        metric = change_metric_if_cost_analysis(metric, chartDict)
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = (
            str(chartDict[dateRangeArray][0]).replace(hyphenName, "/")
            + "-"
            + str(chartDict[dateRangeArray][1]).replace(hyphenName, "/")
        )
    elif plName in columns or plName in chartDict[selectedPeriods]:
        duration = ""
    else:
        periodsArray = chartDict[selectedPeriods]
        duration = periodsArray[1]
    duration = get_rolling_and_year_to_date_period(
        duration, paramDict, chartDict, False
    )
    if dimension and dimension != totalName:
        dimension = "by " + dimension + " "
    else:
        dimension = " "
    if metric:
        metric = metric + " "
    else:
        metric = ""
    if chosenChart in [trendComparisonByPeriodChart]:
        metric = "Weekly Average " + metric
    if plotAsBaseline in chartDict and chartDict[plotAsBaseline]:
        if compareToAverageKey in chartDict and chartDict[compareToAverageKey]:
            period1 = averageName
        else:
            period1 = period1 + " " + varianceName
    if fcName in columns:
        period = duration + " " + element + ", " + fcName + " vs " + period1
    else:
        period = duration + " " + element + " vs " + period1
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    title = (
        companyName
        + "<b>"
        + breakTag
        + metric
        + "</b>"
        + currencyTag
        + dimension
        + " "
        + likeForLikeMessage
        + breakTag
        + period
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_timeline_and_area_charts_title(
    dfCopy, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    dateName = namingParams["dateName"]
    plotTitleText = namingParams["plotTitleText"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    columns, schema = get_schema_and_column_names(dfCopy)
    df_lf = ensure_lazyframe(dfCopy)
    if dateName not in columns:
        df_lf = df_lf.with_row_index(name=dateName)
    min_max = df_lf.select(
        pl.col(dateName).min().alias("first"),
        pl.col(dateName).max().alias("last"),
    ).collect(engine="streaming")
    firstPeriod = str(min_max[0, "first"].strftime("%b-%Y"))
    lastPeriod = str(min_max[0, "last"].strftime("%b-%Y"))
    metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    if dimension == totalName or len(dimension) == 0:
        title = (
            companyName
            + breakTag
            + "<b>"
            + metric
            + " </b>"
            + currencyTag
            + likeForLikeMessage
            + breakTag
            + firstPeriod
            + " to "
            + lastPeriod
        )
    else:
        title = (
            companyName
            + breakTag
            + "<b>"
            + metric
            + " by "
            + dimension
            + " </b>"
            + currencyTag
            + likeForLikeMessage
            + breakTag
            + firstPeriod
            + " to "
            + lastPeriod
        )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict


def make_alternative_combinations_charts_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    rowToPlot = namingParams["rowToPlotName"]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    title = (
        companyName
        + breakTag
        + "<b>"
        + "Alternative combinations"
        + " </b>"
        + likeForLikeMessage
        + breakTag
        + chartDict[rowToPlot]
    )
    title = title.replace("  ", " ")
    return title, paramDict, chartDict


def make_multitier_bar_chart_title(
    df, chosenChart, paramDict, dimension, metric, chartDict, period1, element
):
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    pqName = namingParams["pqName"]
    pmName = namingParams["pmName"]
    pwName = namingParams["pwName"]
    yearName = namingParams["yearName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]
    periodChoiceKey = namingParams["periodChoice"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    metricsToPlot = namingParams["metricsToPlot"]
    selectedPeriods = namingParams["selectedPeriods"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    dateRangeArray = namingParams["dateRangeArray"]
    isYearBeforePy = namingParams["isYearBeforePy"]
    yearBeforePyName = namingParams["yearBeforePyName"]
    hyphenName = namingParams["hyphenName"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    xAxisDimension = namingParams["xAxisDimension"]
    plotTitleText = namingParams["plotTitleText"]
    dimensionDisplayLabels = chartDict.get("dimension_display_labels") or {}
    periodChoice = chartDict[periodChoiceKey]
    breakTag = set_break_row_tag(chartDict, chosenChart)
    companyName, paramDict, chartDict = get_filter_text_or_company_name(
        chartDict, paramDict
    )
    currencyName, paramDict = get_currency_name(chartDict, paramDict, metric)
    columns, schema = get_schema_and_column_names(df)
    if metricsToPlot in chartDict and (not dimension or dimension == totalName):
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            count = 0
            metric = ""
            for value in chartDict[metricsToPlot]:
                value = change_metric_if_cost_analysis(value, chartDict)
                separator = " "
                if count > 0:
                    separator = ", "
                metric = metric + separator + value
                count = count + 1
        else:
            metric = change_metric_if_cost_analysis(metric, chartDict)
    else:
        metric = change_metric_if_cost_analysis(metric, chartDict)
    likeForLikeMessage = make_like_for_like_title_suffix(chartDict, paramDict, metric)
    if plName in columns:
        period1 = plName
    elif isYearBeforePy in paramDict and paramDict[isYearBeforePy]:
        period1 = yearBeforePyName
    elif periodChoice == quarterName and (
        compareWithYearBefore not in chartDict or not chartDict[compareWithYearBefore]
    ):
        period1 = pqName
    elif periodChoice == monthName and (
        compareWithYearBefore not in chartDict or not chartDict[compareWithYearBefore]
    ):
        period1 = pmName
    elif periodChoice == weekName and (
        compareWithYearBefore not in chartDict or not chartDict[compareWithYearBefore]
    ):
        period1 = pwName
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        duration = (
            str(chartDict[dateRangeArray][0]).replace(hyphenName, "/")
            + "-"
            + str(chartDict[dateRangeArray][1]).replace(hyphenName, "/")
        )
    elif plName in columns or plName in chartDict[selectedPeriods]:
        duration = ""
    else:
        periodsArray = chartDict[selectedPeriods]
        duration = periodsArray[1]
    duration = get_rolling_and_year_to_date_period(
        duration, paramDict, chartDict, False
    )
    if dimension and dimension != totalName:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            if xAxisDimension in chartDict:
                secondDimension = chartDict[xAxisDimension]
                dimensionsToPlot = chartDict[selectDimensionsToPlot]
                if len(dimensionsToPlot) > 1:
                    panelDimension = dimensionsToPlot[1]
                else:
                    panelDimension = dimension
                if panelDimension == secondDimension and len(dimensionsToPlot) > 1:
                    panelDimension = dimensionsToPlot[0]
                secondDimension = dimensionDisplayLabels.get(
                    secondDimension, secondDimension
                )
                panelDimension = dimensionDisplayLabels.get(panelDimension, panelDimension)
                dimension = "by " + secondDimension + " and " + panelDimension + " "
            else:
                dimension = "by dimension"
        else:
            dimension = "by " + dimension + " "
    else:
        dimension = " "
    if metric:
        metric = metric + " "
    else:
        metric = ""
    if fcName in columns:
        period = duration + " " + element + ", " + fcName + " vs " + period1
    else:
        period = duration + " " + element + " vs " + period1
    currencyTag = ""
    if currencyName:
        currencyTag = " in " + currencyName + " "
    title = (
        companyName
        + "<b>"
        + breakTag
        + metric
        + "</b>"
        + currencyTag
        + likeForLikeMessage
        + dimension
        + breakTag
        + period
    )
    title = title.replace("  ", " ")
    chartDict[plotTitleText] = title
    return title, paramDict, chartDict
