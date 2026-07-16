import logging

import polars as pl
from modules.utilities.ui_notifier import ui

from modules.charting.chart_primitives import (
    change_array_of_metrics_if_cost_analysis,
    change_metric_if_cost_analysis,
)
from modules.utilities.config import (
    get_metric_array_params,
    get_naming_params,
)


def change_dict_of_metrics_if_cost_analysis(translateDict, chartDict):
    namingParams = get_naming_params()
    datasetTypeKey = namingParams["datasetTypeName"]
    companySales = namingParams["companySales"]
    scanMarketData = namingParams["scanMarketData"]
    companyExpenses = namingParams["companyExpenses"]
    costsName = namingParams["costsName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    costPerUnitName = namingParams["costPerUnitName"]
    costPerVolumeName = namingParams["costPerVolumeName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    costPerUnitNetDiscountName = namingParams["costPerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    costPerVolumeNetDiscountName = namingParams["costPerVolumeNetDiscountName"]
    netUnitsPriceChangeName = namingParams["netUnitsPriceChangeName"]
    netUnitsCostChangeName = namingParams["netUnitsCostChangeName"]
    netVolumeCostChangeName = namingParams["netVolumeCostChangeName"]
    netVolumePriceChangeName = namingParams["netVolumePriceChangeName"]
    metricDict = {
        amountName: costsName,
        pricePerUnitName: costPerUnitName,
        pricePerVolumeName: costPerVolumeName,
        pricePerUnitNetDiscountName: costPerUnitNetDiscountName,
        pricePerVolumeNetDiscountName: costPerVolumeNetDiscountName,
        netUnitsPriceChangeName: netUnitsCostChangeName,
        netVolumePriceChangeName: netVolumeCostChangeName,
    }
    newDict = {}
    if len(translateDict) > 0:
        if datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [
            companyExpenses
        ]:
            for metric in translateDict:
                try:
                    metric = metric.strip()
                except Exception as e:
                    logging.exception(e)
                    ui.error("Something went wrong while stripping metrics.")
                    pass
                if metric in metricDict:
                    translatedMetric = metricDict[metric]
                    newDict[translatedMetric] = translateDict[metric]
                elif amountName in metric:
                    translatedMetric = metric.replace(amountName, costsName)
                    newDict[translatedMetric] = translateDict[metric]
                else:
                    newDict[metric] = translateDict[metric]
            return newDict
        else:
            return translateDict
    else:
        return translateDict


def explain_metrics_for_stacked_column_prompt(
    chartDict, currencyName, secondCurrency, metric, element
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    metricTextKey = namingParams["metricText"]
    fullCurrencyName = namingParams["fullCurrencyName"]
    valuePrefixDictKey = namingParams["valuePrefixDict"]
    metricParamsKey = namingParams["metricParams"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricsToPlotKey = namingParams["metricsToPlot"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    notMonetaryArray = volumeMetricsArray + growthMetricArray + percentMetricsArray
    percentArray = growthMetricArray + percentMetricsArray
    notMonetaryArray = change_array_of_metrics_if_cost_analysis(
        notMonetaryArray, chartDict
    )
    notMonetaryArray = [
        item.lower() if isinstance(item, str) else item for item in notMonetaryArray
    ]
    percentArray = change_array_of_metrics_if_cost_analysis(percentArray, chartDict)
    percentArray = [
        item.lower() if isinstance(item, str) else item for item in percentArray
    ]
    metricsToPlot = chartDict[metricsToPlotKey]
    firstMultiplier = ""
    metric = change_metric_if_cost_analysis(metric, chartDict)
    element = change_metric_if_cost_analysis(element, chartDict)
    translatedDict = change_dict_of_metrics_if_cost_analysis(
        chartDict[valuePrefixDictKey], chartDict
    )
    abbreviationDict = {
        "": "number",
        "k": "thousand",
        "m": "million",
        "b": "billion",
        "t": "trillion",
    }
    if metric.lower() in percentArray:
        firstMultiplier = """**percent**"""
    elif len(currencyName) == 3:
        firstMultiplier = "**" + abbreviationDict[translatedDict[metric]] + "**"
    else:
        firstMultiplier = "**" + abbreviationDict[translatedDict[metric]] + "s**"
    secondMultiplier = ""
    if element.lower() in percentArray:
        secondMultiplier = """**percent**"""
    elif (
        len(secondCurrency) == 3
        and len(metricsToPlot) > 1
        and element in translatedDict
    ):
        secondMultiplier = "**" + abbreviationDict[translatedDict[element]] + "**"
    elif element in translatedDict:
        secondMultiplier = "**" + abbreviationDict[translatedDict[element]] + "s**"
    firstCurrencyText = " are in " + firstMultiplier
    secondCurrencyText = " are in " + secondMultiplier
    if (
        currencyName
        and len(currencyName) > 1
        and chartDict[fullCurrencyName] != nothingFilteredName
        and metric.lower() not in notMonetaryArray
    ):
        firstCurrencyText = (
            firstCurrencyText + " of **" + chartDict[fullCurrencyName] + "s**. "
        )
    elif currencyName and chartDict[fullCurrencyName] != nothingFilteredName:
        firstCurrencyText = (
            firstCurrencyText + """."""
        )  # +" of **"+chartDict[fullCurrencyName]+"s**. "
    else:
        firstCurrencyText = firstCurrencyText + ". "
    if (
        secondCurrency
        and len(secondCurrency) > 1
        and chartDict[fullCurrencyName] != nothingFilteredName
        and element.lower() not in notMonetaryArray
    ):
        secondCurrencyText = (
            secondCurrencyText + " of **" + chartDict[fullCurrencyName] + "s**. "
        )
    elif secondCurrency and chartDict[fullCurrencyName] != nothingFilteredName:
        secondCurrencyText = (
            secondCurrencyText + """."""
        )  # +" of **"+chartDict[fullCurrencyName]+"s**. "
    else:
        secondCurrencyText = secondCurrencyText + ". "
    firstMetric = " **" + metric + "**" + firstCurrencyText
    secondMetric = " **" + element + "**" + secondCurrencyText
    metricText = firstMetric + secondMetric
    chartDict[metricTextKey] = metricText
    chartDict[metricParamsKey] = translatedDict
    return chartDict


def explain_metrics_for_barmekko_prompt(
    chartDict, currencyName, secondCurrency, thirdCurrency, metric, element
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    metricTextKey = namingParams["metricText"]
    fullCurrencyName = namingParams["fullCurrencyName"]
    multipliedMetric = namingParams["multipliedMetric"]
    valuePrefixDictKey = namingParams["valuePrefixDict"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricParamsKey = namingParams["metricParams"]
    yAxisMetricKey = namingParams["yAxisMetric"]
    xAxisMetricKey = namingParams["xAxisMetric"]
    multipliedMetricKey = namingParams["multipliedMetric"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    yAxisMetric = chartDict[yAxisMetricKey]
    xAxisMetric = chartDict[xAxisMetricKey]
    multipliedMetric = chartDict[multipliedMetricKey]
    checkArray = [yAxisMetric, xAxisMetric, multipliedMetric]
    notMonetaryArray = volumeMetricsArray + growthMetricArray + percentMetricsArray
    notMonetaryArray = change_array_of_metrics_if_cost_analysis(
        notMonetaryArray, chartDict
    )
    notMonetaryArray = [
        item.lower() if isinstance(item, str) else item for item in notMonetaryArray
    ]
    percentArray = growthMetricArray + percentMetricsArray
    percentArray = change_array_of_metrics_if_cost_analysis(percentArray, chartDict)
    percentArray = [
        item.lower() if isinstance(item, str) else item for item in percentArray
    ]
    metric = change_metric_if_cost_analysis(metric, chartDict)
    element = change_metric_if_cost_analysis(element, chartDict)
    multipliedMetric = change_metric_if_cost_analysis(multipliedMetric, chartDict)
    for item in checkArray:
        if item not in chartDict[valuePrefixDictKey]:
            chartDict[valuePrefixDictKey][item] = ""
    translatedDict = change_dict_of_metrics_if_cost_analysis(
        chartDict[valuePrefixDictKey], chartDict
    )
    abbreviationDict = {
        "": "number",
        "k": "thousand",
        "m": "million",
        "b": "billion",
        "t": "trillion",
    }
    firstMultiplier = "**" + abbreviationDict[translatedDict[metric]] + "s**"
    secondMultiplier = "**" + abbreviationDict[translatedDict[element]] + "s**"
    thirdMultiplier = "**" + abbreviationDict[translatedDict[multipliedMetric]] + "s**"
    firstCurrencyText = " and are in " + firstMultiplier
    secondCurrencyText = " and are in " + secondMultiplier
    thirdCurrencyText = " and are in " + thirdMultiplier
    if metric.lower() in percentArray:
        firstCurrencyText = """ and are in **percent**. """
    elif (
        currencyName
        and chartDict[fullCurrencyName] != nothingFilteredName
        and metric.lower() not in notMonetaryArray
    ):
        firstCurrencyText = (
            firstCurrencyText + " of **" + chartDict[fullCurrencyName] + "s**. "
        )
    else:
        firstCurrencyText = firstCurrencyText + ". "
    if element.lower() in percentArray:
        secondCurrencyText = """ and are in **percent**. """
    elif (
        secondCurrency
        and chartDict[fullCurrencyName] != nothingFilteredName
        and element.lower() not in notMonetaryArray
    ):
        secondCurrencyText = (
            secondCurrencyText + " of **" + chartDict[fullCurrencyName] + "s**. "
        )
    else:
        secondCurrencyText = secondCurrencyText + ". "
    if (
        thirdCurrency
        and chartDict[fullCurrencyName] != nothingFilteredName
        and multipliedMetric not in notMonetaryArray
        and multipliedMetric.lower() not in notMonetaryArray
    ):
        thirdCurrencyText = (
            thirdCurrencyText + " of **" + chartDict[fullCurrencyName] + "s**. "
        )
    else:
        thirdCurrencyText = thirdCurrencyText + ". "
    firstMetric = "Bar length values represent **" + metric + "**" + firstCurrencyText
    secondMetric = "Bar width values represent **" + element + "**" + secondCurrencyText
    thirdMetric = (
        "Bar area values represent **" + multipliedMetric + "**" + thirdCurrencyText
    )
    metricText = firstMetric + secondMetric + thirdMetric
    chartDict[metricTextKey] = metricText
    chartDict[metricParamsKey] = translatedDict
    return chartDict
