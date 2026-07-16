import copy
import json
import logging
from pathlib import Path
import logging

import polars as pl
from modules.utilities.ui_notifier import ui

NUMERIC_DTYPES = getattr(pl.selectors, "NUMERIC_DTYPES", pl.NUMERIC_DTYPES)

from modules.charting.chart_primitives import (
    change_array_of_metrics_if_cost_analysis,
    change_metric_if_cost_analysis,
)
from modules.data.common_data_utils import (
    check_if_other_in_columns,
    check_if_other_in_index,
    check_if_other_in_rows,
    rank_others_as_last,
)
from modules.llm.prompt_builders import (
    add_prompt_date,
    add_prompt_filter,
)
from modules.llm.prompt_helpers import (
    explain_currency_and_abbreviations,
    get_context,
    translate_first_and_last_period_symbols,
    traslate_ibcs_period_symbols,
)
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import (
    change_column_names_if_cost_analysis,
    change_index_names_if_cost_analysis,
    drop_columns,
    duplicate_dataframe,
    replace_ibcs_date_symbol,
    unique,
)
from modules.utilities.utils import get_schema_and_column_names, unique_values_lazy


def get_marimekko_prompt(dfCopy, chartDict):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    marimekkoChart = namingParams["marimekkoChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    singleMetric = namingParams["singleMetric"]
    totalName = namingParams["totalName"]
    showAverageValue = namingParams["showAverageValueName"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    numberOfTop = namingParams["numberOfTop"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    plotTitleText = namingParams["plotTitleText"]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    title = chartDict[plotTitleText]
    columnTotal = "Column " + totalName
    rowTotal = "Row " + totalName
    df = duplicate_dataframe(dfCopy)
    isOtherRank = check_if_other_in_index(df)
    isOtherColumnRank = check_if_other_in_columns(df)
    promptChart = ""
    promptOther = ""
    promptOtherColumn = ""
    if isOtherRank:
        otherRank = "x"
        if "X" in chartDict:
            otherRank = str(chartDict["X"][numberOfTop])
        promptOther = (
            """ The smaller vertical axis """
            + chartDict[xAxisDimension]
            + """ items are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherRank
            + """' element."""
        )
    if isOtherColumnRank:
        otherColumnRank = "x"
        if "W" in chartDict:
            otherColumnRank = str(chartDict["W"][numberOfTop])
        promptOtherColumn = (
            """ The smaller horizontal axis """
            + chartDict[yAxisDimension]
            + """ items are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherColumnRank
            + """' element."""
        )
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        frameArray = []
        frameArrayPercentRow = []
        frameArrayPercentCol = []
        smallMultiplesArray = unique_values_lazy(chartDict[smallMultiplesColumn], df)
        numberOfSmallMultiples = len(smallMultiplesArray)
        smallMultiplesList = str(smallMultiplesArray).replace("[", "").replace("]", "")
        columns, schema = get_schema_and_column_names(df)
        if chartDict[smallMultiplesColumn] in columns:
            columns.remove(chartDict[smallMultiplesColumn])
        df = df.with_columns(
            pl.sum_horizontal([pl.col(c) for c in columns]).alias(rowTotal)
        )
        for element in smallMultiplesArray:
            dfFiltered = df.filter(pl.col(chartDict[smallMultiplesColumn]) == element)
            if dfFiltered.height > 0:
                try:
                    dfFiltered = dfFiltered.sort(rowTotal, descending=True)
                    dfFiltered = rank_others_as_last(
                        dfFiltered, aggregateOtherItemsNameKey, 99
                    )
                    totals = dfFiltered.select(
                        [pl.sum(pl.col(c)).alias(c) for c in columns + [rowTotal]]
                    )
                    fcols, fschema = get_schema_and_column_names(dfFiltered)
                    totals = totals.with_columns(pl.lit(columnTotal).alias(fcols[0]))
                    dfFiltered = pl.concat([dfFiltered, totals], how="vertical")
                    dfFiltered = dfFiltered.with_columns(
                        pl.lit(element).alias(chartDict[smallMultiplesColumn])
                    )
                    dfPercentRow = duplicate_dataframe(dfFiltered)
                    dfPercentCol = duplicate_dataframe(dfFiltered)
                    dfPercentCol = dfPercentCol.fill_null(0)
                    dfPercentRow = dfPercentRow.fill_null(0)
                    cols = [
                        c
                        for c in get_schema_and_column_names(dfPercentCol)[0]
                        if dfPercentCol[c].null_count() < dfPercentCol.height
                    ]
                    dfPercentCol = dfPercentCol.select(cols)
                    cols = [
                        c
                        for c in get_schema_and_column_names(dfPercentRow)[0]
                        if dfPercentRow[c].fill_null(0).sum() != 0
                    ]
                    dfPercentRow = dfPercentRow.select(cols)
                    cols = [
                        c
                        for c in get_schema_and_column_names(dfPercentRow)[0]
                        if dfPercentRow[c].null_count() < dfPercentRow.height
                    ]
                    dfPercentRow = dfPercentRow.select(cols)
                    cols = [
                        c
                        for c in get_schema_and_column_names(dfPercentCol)[0]
                        if dfPercentCol[c].fill_null(0).sum() != 0
                    ]
                    dfPercentCol = dfPercentCol.select(cols)
                    percentColumns, schema = get_schema_and_column_names(dfPercentCol)
                    if chartDict[smallMultiplesColumn] in percentColumns:
                        percentColumns.remove(chartDict[smallMultiplesColumn])
                    dfPercentCol = dfPercentCol.with_columns(
                        [
                            (pl.col(col) / pl.col(col).last() * 100).round(0).alias(col)
                            for col in percentColumns
                        ]
                    )
                    if rowTotal in get_schema_and_column_names(dfPercentRow)[0]:
                        dfPercentRow = dfPercentRow.with_columns(
                            [
                                pl.when(pl.col(rowTotal) == 0)
                                .then(0)
                                .otherwise(pl.col(col) / pl.col(rowTotal) * 100)
                                .fill_null(0)
                                .round(0)
                                .alias(col)
                                for col in percentColumns
                            ]
                        )
                    else:
                        dfPercentRow = dfPercentRow.with_columns(
                            [pl.lit(0).alias(col) for col in percentColumns]
                        )
                    dfPercentCol = dfPercentCol.with_columns(
                        [pl.col(col).round(0).alias(col) for col in percentColumns]
                    )
                    if dfFiltered.height > 0:
                        frameArray.append(dfFiltered)
                    if dfPercentCol.height > 0:
                        frameArrayPercentCol.append(dfPercentCol)
                    if dfPercentRow.height > 0:
                        frameArrayPercentRow.append(dfPercentRow)
                except Exception as e:
                    e = print_error_details(e)
                    logging.exception(e)
                    ui.error("Something went wrong in get_marimekko_prompt.")
        if len(frameArray) > 0:
            df = pl.concat([pl.DataFrame(f) for f in frameArray])
        if len(frameArrayPercentCol) > 0:
            dfPercentCol = pl.concat([pl.DataFrame(f) for f in frameArrayPercentCol])
            percentColumns, schema = get_schema_and_column_names(dfPercentCol)
            newCols = [col for col in percentColumns if col != rowTotal] + [rowTotal]
            dfPercentCol = dfPercentCol.select(newCols)
        if len(frameArrayPercentRow) > 0:
            dfPercentRow = pl.concat([pl.DataFrame(f) for f in frameArrayPercentRow])
            percentColumns, schema = get_schema_and_column_names(dfPercentRow)
            newCols = [col for col in percentColumns if col != rowTotal] + [rowTotal]
            dfPercentRow = dfPercentRow.select(newCols)
        numberOfColumns = len(columns)
        columnNames = str(columns).replace("[", "").replace("]", "")
        promptContext, companyOrIndustry, contextMetric = get_context(
            chartDict, chartDict[singleMetric]
        )
        title = replace_ibcs_date_symbol(title, chartDict)
        promptContext, df = explain_currency_and_abbreviations(
            df, chartDict, promptContext, contextMetric
        )
        promptContext = add_prompt_date(promptContext, chartDict)
        promptFilter = add_prompt_filter(chartDict)
        promptDescription = (
            """ The provided small multiples **"""
            + marimekkoChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """
        The small multiples """
            + marimekkoChart
            + """ chart is plotted by """
            + chartDict[xAxisDimension]
            + """ and """
            + chartDict[smallMultiplesColumn]
            + """. It shows the largest items ranked by """
            + contextMetric
            + """.
        Each row is split by """
            + chartDict[yAxisDimension]
            + """ in its """
            + str(numberOfColumns)
            + """ components: """
            + columnNames
            + """. 
        The data contains """
            + str(numberOfSmallMultiples)
            + """ small multiples datasets by """
            + chartDict[smallMultiplesColumn]
            + """ stacked on top of each other: """
            + smallMultiplesList
            + """.
        You are also provide a stacked dataset with the percent values by row and a stacked dataset with the percent values by column."""
        )
        promptChart = promptDescription
    elif (
        yAxisDimension in chartDict and chartDict[yAxisDimension] != nothingFilteredName
    ):
        df = df.with_columns(
            pl.sum_horizontal(
                [pl.col(c) for c in get_schema_and_column_names(df)[0]]
            ).alias(rowTotal)
        )
        df = df.sort(rowTotal, descending=True)
        df = rank_others_as_last(df, aggregateOtherItemsNameKey, 99)
        totals = df.select(
            [pl.sum(pl.col(c)).alias(c) for c in get_schema_and_column_names(df)[0]]
        )
        df_cols, df_schema = get_schema_and_column_names(df)
        totals = totals.with_columns(pl.lit(columnTotal).alias(df_cols[0]))
        df = pl.concat([df, totals], how="vertical")
        columns, schema = get_schema_and_column_names(df)
        dfPercentRow = duplicate_dataframe(df)
        dfPercentCol = duplicate_dataframe(df)
        dfPercentCol = dfPercentCol.with_columns(
            [
                (pl.col(c) / pl.col(c).last() * 100).round(0).alias(c)
                for c in get_schema_and_column_names(dfPercentCol)[0]
            ]
        )
        dfPercentRow = dfPercentRow.with_columns(
            [
                pl.when(pl.col(rowTotal) == 0)
                .then(0)
                .otherwise(pl.col(col) / pl.col(rowTotal) * 100)
                .round(0)
                .alias(col)
                for col in columns
            ]
        )
        dfPercentCol = dfPercentCol.with_columns(
            [pl.col(col).round(0).alias(col) for col in columns]
        )
        if rowTotal in columns:
            columns.remove(rowTotal)
        numberOfColumns = len(columns)
        columnNames = str(columns).replace("[", "").replace("]", "")
        promptContext, companyOrIndustry, contextMetric = get_context(
            chartDict, chartDict[singleMetric]
        )
        title = replace_ibcs_date_symbol(title, chartDict)
        promptContext, df = explain_currency_and_abbreviations(
            df, chartDict, promptContext, contextMetric
        )
        promptContext = add_prompt_date(promptContext, chartDict)
        promptFilter = add_prompt_filter(chartDict)
        promptDescription = (
            """ The provided **"""
            + marimekkoChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """ 
        The """
            + marimekkoChart
            + """ chart is plotted by """
            + chartDict[xAxisDimension]
            + """ and shows the largest items ranked by """
            + contextMetric
            + """.
        Each row is split by """
            + chartDict[yAxisDimension]
            + """ in its """
            + str(numberOfColumns)
            + """ components: """
            + columnNames
            + """. 
        The """
            + rowTotal
            + """ column shows the totals by row, while the """
            + columnTotal
            + """ row shows the totals by column. 
        You are also provide a dataset with the percent values by row and a dataset with the percent values by column>"""
        )
        promptChart = promptDescription
    promptFact = """\n\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    promptDf = (
        """\n\nThe """
        + contextMetric
        + """ dataset, that contains absolute values, is as follows :\n{}""".format(df)
    )
    promptDfRows = (
        """\n\nThis dataset contains the percent values by row :\n{}""".format(
            dfPercentRow
        )
    )
    promptDfCols = (
        """\n\nThis dataset contains the percent values by column :\n{}""".format(
            dfPercentCol
        )
    )
    promptChart = (
        promptChart
        + promptOther
        + promptOtherColumn
        + promptDf
        + promptDfRows
        + promptDfCols
        + promptFact
    )
    return promptChart, df


def get_horizontal_waterfall_prompt(df, chartDict):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    showAverageValue = namingParams["showAverageValueName"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    metricsToPlot = namingParams["metricsToPlot"]
    numberOfTop = namingParams["numberOfTop"]
    selectedPeriods = namingParams["selectedPeriods"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    acName = namingParams["acName"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText = namingParams["plotTitleText"]
    title = chartDict[plotTitleText]
    metric = chartDict[metricsToPlot][0]
    isOtherRowRank = False
    promptDf = " The dataset is as follows :\n{}".format(df)
    dimension = ""
    promptOther = ""
    itemDetail = ""
    columns, schema = get_schema_and_column_names(df)
    if plName in columns:
        pyName = plName
    promptColumns = """The dataset shows the """
    promptContext, companyOrIndustry, contextMetric = get_context(chartDict, metric)
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    promptFilter = add_prompt_filter(chartDict)
    if (
        selectDimensionsToPlot in chartDict
        and len(chartDict[selectDimensionsToPlot]) > 1
    ):
        dimension = chartDict[selectDimensionsToPlot][1]
        isOtherRowRank = check_if_other_in_rows(df, dimension)
        smallMultiplesArray = unique_values_lazy(
            chartDict[selectDimensionsToPlot][1], df
        )
        numberOfSmallMultiples = len(smallMultiplesArray)
        smallMultiplesList = str(smallMultiplesArray).replace("[", "").replace("]", "")
        promptDescription = (
            """ The provided **"""
            + horizontalWaterfallChart
            + """** small multiples chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """ 
        The small multiples """
            + horizontalWaterfallChart
            + """ chart is plotted along each of the following items: """
            + smallMultiplesList
            + """ of the """
            + chartDict[selectDimensionsToPlot][1]
            + """ dimension. 
        The data contains """
            + str(numberOfSmallMultiples)
            + """ small multiples datasets by """
            + chartDict[selectDimensionsToPlot][1]
            + """ stacked on top of each other.
        Each dataset shows the total and monthly """
            + contextMetric
            + """ in the """
            + chartDict[selectedPeriods][0]
            + """ ("""
            + pyName
            + """) and in the """
            + chartDict[selectedPeriods][1]
            + """ ("""
            + acName
            + """) periods, as well as the variance in absolute and percent terms. """
        )
        if isOtherRowRank:
            otherRowRank = "x"
            if "X" in chartDict:
                otherRowRank = str(chartDict["X"][numberOfTop])
            promptOther = (
                """ The '"""
                + aggregateOtherItemsName
                + """ """
                + otherRowRank
                + """' element aggregates all the smaller items."""
            )
    else:
        promptDescription = (
            """ The provided **"""
            + horizontalWaterfallChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """ 
        The dataset shows the total and monthly """
            + contextMetric
            + """ in the """
            + chartDict[selectedPeriods][0]
            + """ ("""
            + pyName
            + """) and in the """
            + chartDict[selectedPeriods][1]
            + """ ("""
            + acName
            + """) periods, as well as the variance in absolute and percent terms. """
        )
    promptChart = promptDescription + promptOther
    promptFact = """ Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    promptChart = promptChart + promptDf + promptFact
    return promptChart, df


def get_multitier_bar_prompt(dfCopy, chartDict):
    namingParams = get_naming_params()
    dimensionName = namingParams["dimensionName"]
    itemName = namingParams["itemName"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    differenceInValue = namingParams["differenceInValue"]
    differenceInPercent = namingParams["differenceInPercent"]
    multitierBarChart = namingParams["multitierBarChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricsToPlot = namingParams["metricsToPlot"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    numberOfTop = namingParams["numberOfTop"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText = namingParams["plotTitleText"]
    longAverageName = namingParams["longAverageName"]
    colorName = namingParams["colorName"]
    title = chartDict[plotTitleText]
    df = duplicate_dataframe(dfCopy)
    df = drop_columns(df, [colorName])
    isOtherRowRank = False
    promptChart = ""
    promptOther = ""
    promptPrecision = ""
    promptContext, companyOrIndustry, contextMetric = get_context(
        chartDict, chartDict[metricsToPlot][0]
    )
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    firstPeriod, secondPeriod = traslate_ibcs_period_symbols(chartDict)
    promptFilter = add_prompt_filter(chartDict)
    promptDf = " The dataset is as follows :\n{}".format(df)
    if (plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]) and (
        selectDimensionsToPlot in chartDict and chartDict[selectDimensionsToPlot]
    ):
        if (
            xAxisDimension in chartDict
            and chartDict[xAxisDimension] != nothingFilteredName
        ):
            promptPrecision = (
                """ Do not use abbreviations for the names of """
                + chartDict[xAxisDimension]
                + """s and """
                + chartDict[selectDimensionsToPlot][1]
                + """s. Be sure to name the items in the """
                + chartDict[xAxisDimension]
                + """ column and in the """
                + chartDict[selectDimensionsToPlot][1]
                + """ column as they are named in the dataset. """
            )
            smallMultiplesArray = (
                df[chartDict[selectDimensionsToPlot][1]].unique().to_list()
            )
            numberOfSmallMultiples = len(smallMultiplesArray)
            smallMultiplesList = (
                str(smallMultiplesArray).replace("[", "").replace("]", "")
            )
            columns, schema = get_schema_and_column_names(df)
            isOtherRowRank = check_if_other_in_rows(df, itemName)
            numberOfColumns = len(columns)
            columnNames = str(columns).replace("[", "").replace("]", "")
            promptDescription = (
                """ The provided small multiples **"""
                + multitierBarChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """ 
            The small multiples """
                + multitierBarChart
                + """ chart is plotted along each of the following items: """
                + smallMultiplesList
                + """ of the """
                + chartDict[selectDimensionsToPlot][1]
                + """ dimension. 
            The data contains """
                + str(numberOfSmallMultiples)
                + """ small multiples datasets by """
                + chartDict[selectDimensionsToPlot][1]
                + """ stacked on top of each other.
            Each small multiple dataset shows the largest items of a given item of the """
                + chartDict[selectDimensionsToPlot][1]
                + """ dimension ranked by """
                + contextMetric
                + """.
            The """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ columns show """
                + contextMetric
                + """ in the """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ periods respectively. 
            The """
                + differenceInValue
                + """ and the """
                + differenceInPercent
                + """ columns show the variance in """
                + contextMetric
                + """ in the two periods in absolute value and in percent. """
            )
            promptChart = promptDescription
        else:
            smallMultiplesArray = unique_values_lazy(dimensionName, df)
            promptPrecision = (
                """ Call the items in the """
                + dimensionName
                + """ column and in the """
                + itemName
                + """ column exactly as they are called in the dataset. Never use abbreviations or make up names for the items of the """
                + dimensionName
                + """ and """
                + itemName
                + """ columns, such as '"""
                + smallMultiplesArray[0]
                + """ A', '"""
                + smallMultiplesArray[0]
                + """B', '"""
                + smallMultiplesArray[0]
                + """ C'. """
            )
            numberOfSmallMultiples = len(smallMultiplesArray)
            smallMultiplesList = (
                str(smallMultiplesArray).replace("[", "").replace("]", "")
            )
            columns, schema = get_schema_and_column_names(df)
            isOtherRowRank = check_if_other_in_rows(df, itemName)
            numberOfColumns = len(columns)
            columnNames = str(columns).replace("[", "").replace("]", "")
            promptDescription = (
                """ The provided small multiples **"""
                + multitierBarChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """ 
            The small multiples """
                + multitierBarChart
                + """ chart is plotted along each of the following dimensions: """
                + smallMultiplesList
                + """. 
            The data contains """
                + str(numberOfSmallMultiples)
                + """ small multiples datasets by Dimension stacked on top of each other.
            Each small multiple dataset shows the largest items of a given dimension ranked by """
                + contextMetric
                + """.
            The """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ columns show """
                + contextMetric
                + """ in the """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ periods respectively. 
            The """
                + differenceInValue
                + """ and the """
                + differenceInPercent
                + """ columns show the variance in """
                + contextMetric
                + """ in the two periods in absolute value and in percent. """
            )
            promptChart = promptDescription
    else:
        if dimensionName in chartDict and chartDict[dimensionName]:
            isOtherRowRank = check_if_other_in_rows(df, chartDict[dimensionName])
            promptDescription = (
                """ The provided **"""
                + multitierBarChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """
            The """
                + multitierBarChart
                + """ chart is plotted by """
                + chartDict[dimensionName]
                + """ and shows the largest items ranked by """
                + contextMetric
                + """. 
            The """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ columns show """
                + contextMetric
                + """ in the """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ periods respectively. 
            The """
                + differenceInValue
                + """ and the """
                + differenceInPercent
                + """ columns show the variance in """
                + contextMetric
                + """ in the two periods in absolute value and in percent. """
            )
            promptChart = promptDescription
        else:
            promptDescription = (
                """ The provided **"""
                + multitierBarChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """
            The """
                + multitierBarChart
                + """ chart shows total """
                + contextMetric
                + """. 
            The """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ columns show """
                + contextMetric
                + """ in the """
                + firstPeriod
                + """ and the """
                + secondPeriod
                + """ periods respectively. 
            The """
                + differenceInValue
                + """ and the """
                + differenceInPercent
                + """ columns show the variance in """
                + contextMetric
                + """ in the two periods in absolute value and in percent. """
            )
            promptChart = promptDescription
    if isOtherRowRank:
        otherRowRank = "x"
        if "X" in chartDict:
            otherRowRank = str(chartDict["X"][numberOfTop])
        promptOther = (
            """ The smaller items are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherRowRank
            + """' element."""
        )

    promptMaterial = (
        """ Ignore small, non material, """
        + contextMetric
        + """ values and small, non material, variance values. Very high % difference that correspond to very small, non material """
        + contextMetric
        + """ values should also be ignored."""
    )
    promptFact = (
        """\n\n Only provide fact-based evidences that can be derived from the data presented to you. """
        + promptMaterial
        + """Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
    )
    promptChart = promptChart + promptOther + promptDf + promptPrecision + promptFact
    return promptChart, df


def get_stacked_bar_prompt(dfCopy, chartDict):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    barChart = namingParams["barChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    metricsToPlot = namingParams["metricsToPlot"]
    showAverageValue = namingParams["showAverageValueName"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    numberOfTop = namingParams["numberOfTop"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText = namingParams["plotTitleText"]
    averageName = namingParams["averageName"]
    longAverageName = namingParams["longAverageName"]
    valueName = namingParams["valueName"]
    datasetTypeKey = namingParams["datasetTypeName"]
    companyExpenses = namingParams["companyExpenses"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    costsName = namingParams["costsName"]
    verticalDimensionArray = []
    title = chartDict[plotTitleText]
    df = duplicate_dataframe(dfCopy)
    df = drop_columns(df, [valueName])
    isOtherRank = check_if_other_in_index(df)
    isOtherColumnRank = check_if_other_in_columns(df)
    promptAverage = ""
    promptChart = ""
    promptOther = ""
    promptOtherColumn = ""
    promptNormalized = ""
    # Materialize index-like labels in Polars by using the first column
    if isinstance(df, pl.LazyFrame):
        df_cols, df_schema = get_schema_and_column_names(df)
        first_col = df_cols[0]
        uniqueIndexValues = (
            df.select(pl.col(first_col).unique()).collect().to_series().to_list()
        )
    elif isinstance(df, pl.DataFrame):
        df_cols, df_schema = get_schema_and_column_names(df)
        first_col = df_cols[0]
        uniqueIndexValues = df.select(pl.col(first_col).unique()).to_series().to_list()
    else:
        uniqueIndexValues = df.index.unique().to_list()
    for element in uniqueIndexValues:
        if element not in [longAverageName, averageName, "  "]:
            verticalDimensionArray.append(element)
    verticalDimensionArray = verticalDimensionArray[::-1]
    verticalDimensionItems = str(verticalDimensionArray)
    verticalDimensionItems = (
        verticalDimensionItems.replace("[", "").replace("]", "").replace("'", "")
    )
    promptItems = """ These items are: """ + verticalDimensionItems + """."""
    # if showAverageValue in chartDict and chartDict[showAverageValue]:
    #    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
    #        indexList=df.index.tolist()
    #        if averageName in indexList or longAverageName in indexList:
    #            secondRowLabel = df.index[1]
    #            df = df.drop(secondRowLabel)
    metric = chartDict[metricsToPlot][0]
    if len(chartDict[metricsToPlot]) > 1:
        metric = chartDict[metricsToPlot][0] + " and " + chartDict[metricsToPlot][1]
    promptContext, companyOrIndustry, contextMetric = get_context(chartDict, metric)
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    promptContext = add_prompt_date(promptContext, chartDict)
    promptFilter = add_prompt_filter(chartDict)
    if isOtherRank:
        otherRank = "x"
        if "X" in chartDict:
            otherRank = str(chartDict["X"][numberOfTop])
        promptOther = (
            """ The smaller items are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherRank
            + """' element."""
        )
    if isOtherColumnRank:
        otherColumnRank = "x"
        if "W" in chartDict:
            otherColumnRank = str(chartDict["W"][numberOfTop])
        promptOtherColumn = (
            """ The smaller items in the horizontal axis are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherColumnRank
            + """' element."""
        )
    df = change_column_names_if_cost_analysis(df, chartDict)
    promptDf = " The dataset is as follows :\n{}".format(df)
    if showAverageValue in chartDict and chartDict[showAverageValue]:
        # Retrieve row labels for Polars by taking the first column values
        if isinstance(df, pl.LazyFrame):
            df_cols, df_schema = get_schema_and_column_names(df)
            first_col = df_cols[0]
            indexList = df.select(pl.col(first_col)).collect().to_series().to_list()
        elif isinstance(df, pl.DataFrame):
            df_cols, df_schema = get_schema_and_column_names(df)
            first_col = df_cols[0]
            indexList = df.select(pl.col(first_col)).to_series().to_list()
        else:
            indexList = df.index.to_list()
        if averageName in indexList or longAverageName in indexList:
            promptAverage = """ The 'Average' row at the top of the dataset shows the average of all items and is followed by an empty row."""
    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] != absolute:
        promptNormalized = """ All values are normalized and shown in percent."""
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        smallMultiplesArray = unique_values_lazy(chartDict[smallMultiplesColumn], df)
        numberOfSmallMultiples = len(smallMultiplesArray)
        smallMultiplesList = str(smallMultiplesArray).replace("[", "").replace("]", "")
        if (
            yAxisDimension in chartDict
            and chartDict[yAxisDimension] == nothingFilteredName
        ):
            promptDescription = (
                """ The provided small multiples **"""
                + barChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """
            """
                + promptItems
                + """
            The small multiples """
                + barChart
                + """ chart is plotted by """
                + chartDict[xAxisDimension]
                + """ and """
                + chartDict[smallMultiplesColumn]
                + """. It shows the largest items ranked by """
                + contextMetric
                + """.
            """
                + promptItems
                + """
            The data contains """
                + str(numberOfSmallMultiples)
                + """ small multiples datasets by """
                + chartDict[smallMultiplesColumn]
                + """ stacked on top of each other: """
                + smallMultiplesList
                + """."""
            )
            promptChart = promptDescription
        else:
            columns, schema = get_schema_and_column_names(df)
            if chartDict[smallMultiplesColumn] in columns:
                columns.remove(chartDict[smallMultiplesColumn])
            numberOfColumns = len(columns)
            columnNames = str(columns).replace("[", "").replace("]", "")
            promptDescription = (
                """ The provided small multiples **"""
                + barChart
                + """** chart dataset has the following title: '"""
                + title
                + """'."""
                + promptContext
                + """"""
                + promptFilter
                + """
            The small multiples """
                + barChart
                + """ chart is plotted by """
                + chartDict[xAxisDimension]
                + """ and """
                + chartDict[smallMultiplesColumn]
                + """. It shows the largest items ranked by """
                + contextMetric
                + """.
            """
                + promptItems
                + """
            Each row is split by """
                + chartDict[yAxisDimension]
                + """ in its """
                + str(numberOfColumns)
                + """ components: """
                + columnNames
                + """. 
            The data contains """
                + str(numberOfSmallMultiples)
                + """ small multiples datasets by """
                + chartDict[smallMultiplesColumn]
                + """ stacked on top of each other: """
                + smallMultiplesList
                + """."""
            )
            promptChart = promptDescription
    elif (
        yAxisDimension in chartDict and chartDict[yAxisDimension] == nothingFilteredName
    ):
        promptDescription = (
            """ The provided **"""
            + barChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """
        The """
            + barChart
            + """ chart is plotted by """
            + chartDict[xAxisDimension]
            + """ and shows the largest items ranked by """
            + contextMetric
            + """."""
            + promptItems
        )
        promptChart = promptDescription
    elif (
        yAxisDimension in chartDict and chartDict[yAxisDimension] != nothingFilteredName
    ):
        columns, schema = get_schema_and_column_names(df)
        numberOfColumns = len(columns)
        columnNames = str(columns).replace("[", "").replace("]", "")
        promptDescription = (
            """ The provided **"""
            + barChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """
        The """
            + barChart
            + """ chart is plotted by """
            + chartDict[xAxisDimension]
            + """ and shows the largest items ranked by """
            + contextMetric
            + """.
        """
            + promptItems
            + """
        Each row is split by """
            + chartDict[yAxisDimension]
            + """ in its """
            + str(numberOfColumns)
            + """ components: """
            + columnNames
            + """."""
        )
        promptChart = promptDescription
    promptFact = """ Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    promptChart = (
        promptChart
        + promptOther
        + promptOtherColumn
        + promptNormalized
        + promptAverage
        + promptDf
        + promptFact
    )
    return promptChart, df


def get_timeline_chart_prompt(df, chartDict):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    timelineChart = namingParams["timelineChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    showAverageValue = namingParams["showAverageValueName"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    showValuesAs = namingParams["showValuesAs"]
    metricsToPlot = namingParams["metricsToPlot"]
    absolute = namingParams["absolute"]
    numberOfTop = namingParams["numberOfTop"]
    selectedPeriods = namingParams["selectedPeriods"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotTitleText = namingParams["plotTitleText"]
    title = chartDict[plotTitleText]
    promptDf = " The dataset is as follows :\n{}".format(df)
    dimension = ""
    promptOther = ""
    itemDetail = ""
    promptContext, companyOrIndustry, contextMetric = get_context(
        chartDict, chartDict[metricsToPlot][0]
    )
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    promptFilter = add_prompt_filter(chartDict)
    if (
        selectDimensionsToPlot in chartDict
        and len(chartDict[selectDimensionsToPlot]) > 1
    ):
        dimension = "by " + chartDict[selectDimensionsToPlot][1]
        columns, schema = get_schema_and_column_names(df)
        numberOfItems = len(columns)
        itemsList = str(columns)
        items = itemsLiui.replace("[", "").replace("]", " ")
        itemDetail = (
            """ The """
            + chartDict[selectDimensionsToPlot][1]
            + """ dimension is split into """
            + str(numberOfItems)
            + """ items: """
            + items
            + """."""
        )
        isOtherColumnRank = check_if_other_in_columns(df)
        if isOtherColumnRank:
            otherRank = "x"
            if "X" in chartDict:
                otherRank = str(chartDict["X"][numberOfTop])
                promptOther = (
                    """ The smaller """
                    + chartDict[selectDimensionsToPlot][1]
                    + """ items are aggregated together in a '"""
                    + aggregateOtherItemsName
                    + """ """
                    + otherRank
                    + """' element."""
                )
    promptDescription = (
        """ The provided **"""
        + timelineChart
        + """** chart dataset has the following title: '"""
        + title
        + """'."""
        + promptContext
        + """"""
        + promptFilter
        + """
    The **"""
        + timelineChart
        + """** chart shows the evolution of """
        + contextMetric
        + """ """
        + dimension
        + """ over time. """
        + itemDetail
        + """"""
    )
    promptChart = promptDescription + promptOther
    promptFact = """ Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    promptChart = promptChart + promptDf + promptFact
    return promptChart, df


def get_stacked_pareto_prompt(df, chartDict):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    singleMetric = namingParams["singleMetric"]
    showAverageValue = namingParams["showAverageValueName"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    showValuesAs = namingParams["showValuesAs"]
    absolute = namingParams["absolute"]
    plotTitleText = namingParams["plotTitleText"]
    countByColumnKey = namingParams["countByColumn"]
    countColumnKey = namingParams["countColumn"]
    metricsToPlotKey = namingParams["metricsToPlot"]
    workColumn = namingParams["workColumn"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]
    columns, schema = get_schema_and_column_names(df)
    columnNames = str(columns).replace("[", "").replace("]", "")
    countByColumn = chartDict[countByColumnKey]
    title = chartDict[plotTitleText]
    chartDict[metricsToPlotKey] = change_array_of_metrics_if_cost_analysis(
        chartDict[metricsToPlotKey], chartDict
    )
    metrics = str(chartDict[metricsToPlotKey]).replace("[", "").replace("]", "")
    df = change_index_names_if_cost_analysis(df, chartDict)
    if isinstance(df, pl.LazyFrame):
        pl_df = df.collect()
    elif isinstance(df, pl.DataFrame):
        pl_df = df.clone()
    else:
        index_name = getattr(getattr(df, "index", None), "name", None) or "None"
        df_dict = {index_name: list(getattr(df, "index", []))}
        for col in getattr(df, "columns", []):
            df_dict[col] = list(df[col])
        pl_df = pl.DataFrame(df_dict)
    pl_cols, pl_schema = get_schema_and_column_names(pl_df)
    index_col = pl_cols[0]
    mask = pl.col(index_col) != workColumn
    numeric_cols = [c for c, dt in pl_schema.items() if dt in NUMERIC_DTYPES]
    pl_df = pl_df.with_columns(
        [
            pl.when(mask).then(pl.col(c) * 100).otherwise(pl.col(c)).round(1).alias(c)
            for c in numeric_cols
        ]
    )
    df = pl_df
    promptDf = " The dataset is as follows :\n{}".format(df).replace("#", "number")
    promptOne = ""
    title = replace_ibcs_date_symbol(title, chartDict)
    firstIndexItem = df[index_col][0]
    if (
        aggregateUniquesByDimension in chartDict
        and chartDict[aggregateUniquesByDimension]
    ):
        promptContext = (
            """ The dataset shows the relative weight of each """
            + chartDict[aggregateUniquesDimension]
            + """ along the following metrics: """
            + metrics
            + """. 
        The """
            + chartDict[aggregateUniquesDimension]
            + """ columns of the dataset ("""
            + columnNames
            + """) are 
        sorted in descending order by """
            + firstIndexItem
            + """. The '"""
            + chartDict[countByColumnKey]
            + """' row of the dataset shows the percentage of """
            + chartDict[countColumnKey]
            + """s in each """
            + chartDict[aggregateUniquesDimension]
            + """.
        The '"""
            + workColumn
            + """' row of the dataset shows the number of """
            + chartDict[countColumnKey]
            + """s for each """
            + chartDict[aggregateUniquesDimension]
            + """. """
        )
        promptContext = add_prompt_date(promptContext, chartDict)
        promptFilter = add_prompt_filter(chartDict)
        promptOther = "The 'Other rank' column, if present, represents the aggregation of smaller items."
        promptSecondMetric = ""
        promptThirdMetric = ""
        promptDescription = (
            """ The provided **"""
            + stackedParetoChart
            + """** dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """ 
        """
            + promptOther
            + """"""
        )
        promptThirdMetric = ""
        promptFact = """\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
        promptChart = (
            promptOne
            + promptDescription
            + promptSecondMetric
            + promptThirdMetric
            + promptDf
            + promptFact
        )
    else:
        columns, schema = get_schema_and_column_names(df)
        promptContext = (
            """ The dataset shows - for the """
            + chartDict[toPlotPeriod]
            + """ period - the relative weight of the Pareto """
            + columnNames
            + """ classes along the following metrics: """
            + metrics
            + """. 
        The """
            + chartDict[countColumnKey]
            + """s in each Pareto class are sorted by descending """
            + firstIndexItem
            + """ by """
            + chartDict[countColumnKey]
            + """. 
        The '"""
            + chartDict[countByColumnKey]
            + """' row of the dataset shows the percentage of """
            + chartDict[countColumnKey]
            + """s for each Pareto class.
        The '"""
            + workColumn
            + """' row of the dataset shows the number of """
            + chartDict[countColumnKey]
            + """s for each Pareto class."""
        )
        promptContext = add_prompt_date(promptContext, chartDict)
        promptFilter = add_prompt_filter(chartDict)
        pl_df = df
        if "A" in columns:
            percentValue = int(
                pl_df.filter(pl.col(index_col) == chartDict[countByColumnKey])
                .select("A")
                .item()
            )
            if percentValue < 20:
                message = "'intense'."
            elif percentValue < 30:
                message = "'typical'."
            elif percentValue < 40:
                message = "'moderate'."
            else:
                message = "'weak'."
        elif "B" in columns:
            percentValue = int(
                pl_df.filter(pl.col(index_col) == chartDict[countByColumnKey])
                .select("B")
                .item()
            )
            if percentValue < 20:
                message = "'intense'."
            elif percentValue < 30:
                message = "'typical'."
            elif percentValue < 40:
                message = "'moderate'."
            else:
                message = "'weak'."
        else:
            percentValue = int(
                pl_df.filter(pl.col(index_col) == chartDict[countByColumnKey])
                .select("C")
                .item()
            )
            message = "'weak'."
        promptConcentration = (
            """ Since the percentage of """
            + chartDict[countColumnKey]
            + """s that makes up 80% of """
            + firstIndexItem
            + """ is equal to """
            + str(percentValue)
            + """% the 
        the """
            + chartDict[countColumnKey]
            + """ """
            + firstIndexItem
            + """  concentration should be considered '"""
            + message
            + """'"""
        )
        promptDescription = (
            """ The provided **"""
            + stackedParetoChart
            + """** dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """.     
        The """
            + chartDict[countColumnKey]
            + """s are split into three classes (A, B, C), where the first 'A' class makes up 80% of 
        """
            + firstIndexItem
            + """, the second 'B' class makes up a further 15% of """
            + firstIndexItem
            + """ and the third 'C' class 
        makes up the last 5% of """
            + firstIndexItem
            + """. If some """
            + chartDict[countColumnKey]
            + """s have 
        negative """
            + firstIndexItem
            + """ there will be a fourth class, 'Loss'. """
            + promptConcentration
            + """"""
        )
        promptSecondMetric = ""
        promptThirdMetric = ""
        promptFact = """\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart.\n\n"""
        promptChart = (
            promptOne
            + promptDescription
            + promptSecondMetric
            + promptThirdMetric
            + promptDf
            + promptFact
        )
    return promptChart, df


def get_stacked_column_prompt(df, metric, column, paramDict, chartDict):
    namingParams = get_naming_params()
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    periodName = namingParams["periodName"]
    periodChoice = namingParams["periodChoice"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    synthesisPlot = namingParams["synthesisPlot"]
    absolute = namingParams["absolute"]
    sinceName = namingParams["sinceName"]
    lostName = namingParams["lostName"]
    totalName = namingParams["totalName"]
    likeForLikeKey = namingParams["likeForLikeName"]
    chosenCohortColumn = namingParams["chosenCohortColumn"]
    CXGRData = namingParams["CXGRData"]
    CXGRTotal = namingParams["CXGRTotal"]
    showCAGR = namingParams["showCAGR"]
    numberOfName = namingParams["numberOfName"]
    metricsToPlotKey = namingParams["metricsToPlot"]
    plotTitleText = namingParams["plotTitleText"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    prompZero = " Ignore zero values, and items called 'unknown'. "
    prompSmall = " Ignore small and non material values. "
    promptOther = "'Other rank' items represent aggregations of smaller items.  "
    title = chartDict[plotTitleText]
    metric = metric.title()
    promptCagrValue = False
    promptCagrData = False
    chartDict[metricsToPlotKey] = change_array_of_metrics_if_cost_analysis(
        chartDict[metricsToPlotKey], chartDict
    )
    df = change_column_names_if_cost_analysis(df, chartDict)
    if len(chartDict[metricsToPlotKey]) > 1:
        metric = (
            chartDict[metricsToPlotKey][0].title()
            + "** and  **"
            + chartDict[metricsToPlotKey][1].title()
        )
    promptContext, companyOrIndustry, contextMetric = get_context(chartDict, metric)
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    promptFilter = add_prompt_filter(chartDict)
    promptDf = " **" + metric.title() + "** across the period were :\n{}".format(df)
    promptDescription = (
        """ The provided  **"""
        + stackedColumnChart
        + """** chart dataset has the following title: '"""
        + title
        + """'."""
        + promptContext
        + """"""
        + promptFilter
        + """"""
    )
    if len(chartDict[metricsToPlotKey]) > 1:
        promptDf = (
            " **"
            + chartDict[metricsToPlotKey][0].title()
            + "** and  **"
            + chartDict[metricsToPlotKey][1].title()
            + "** across the period were :\n{}".format(df)
        )
    if synthesisPlot in chartDict and chartDict[synthesisPlot]:
        firstPeriod = ""
        lastPeriod = ""
        # Use Polars transpose when applicable; fall back to pandas-style otherwise
        if isinstance(df, pl.LazyFrame):
            df = df.collect().transpose()
        elif isinstance(df, pl.DataFrame):
            df = df.transpose()
        else:
            df = df.T
        promptData = (
            "The dataset shows the most important items by "
            + metric
            + " for each dimension. Make sure you have read the values correctly. Validate the data: if the sum of the percentage values of a dimension does not add to around 100%, there is an error in the values, ignore and drop the dimension. "
        )
        promptDo = "Comment the mix across dimensions. "
        promptDo = ""
        prompt = promptData + prompZero + promptOther + promptDo
    else:
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            firstPeriod = df.select(pl.col(periodName).first()).item()
            lastPeriod = df.select(pl.col(periodName).last()).item()
        else:
            # If period column exists, use its first/last values; otherwise fall back to column names
            if periodName in get_schema_and_column_names(df)[0]:
                firstPeriod = df.select(pl.col(periodName).first()).item()
                lastPeriod = df.select(pl.col(periodName).last()).item()
            else:
                dcols, dschema = get_schema_and_column_names(df)
                firstPeriod = dcols[0] if df.width > 0 else ""
                lastPeriod = dcols[-1] if df.width > 0 else ""
        firstPeriod, lastPeriod = translate_first_and_last_period_symbols(
            firstPeriod, lastPeriod
        )
        period = periodName.lower()
        promptCagrTotal, promptCagrData = False, False
        if showCAGR in chartDict and chartDict[showCAGR]:
            if CXGRTotal in chartDict:
                columns, schema = get_schema_and_column_names(chartDict[CXGRTotal])
                if totalName in columns:
                    promptCagrValue = (
                        chartDict[CXGRTotal].select(pl.col(totalName).first()).item()
                    )
                    value = str(promptCagrValue)
                    promptCagrTotal = (
                        " The overall **"
                        + chartDict[metricsToPlotKey][0].title()
                        + "** CAGR across the period was "
                        + value
                        + ". "
                    )
            if CXGRData in chartDict:
                promptCagrData = ":\n{}".format(chartDict[CXGRData])
                promptCagrData = (
                    " By "
                    + column
                    + ", the **"
                    + metric
                    + "** CAGR across the period was "
                    + promptCagrData
                    + ". "
                )
        if chartDict[periodChoice]:
            period = chartDict[periodChoice].lower()
        promptAbsolute = " in percent of total. "
        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] == absolute
        ):
            promptAbsolute = " in absolute value. "
        if likeForLikeKey in chartDict and chartDict[likeForLikeKey]:
            promptDf = (
                " like-for-like **"
                + metric.title()
                + "** across the period were :\n{}".format(df)
            )
            promptLikeForLike = (
                """ In other words, the data shows the like-for-like """
                + chartDict[chosenCohortColumn]
                + """ **"""
                + metric
                + """** generated by the exact same set of """
                + chartDict[chosenCohortColumn]
                + """s across the """
                + firstPeriod
                + """ to """
                + lastPeriod
                + """ period.
             Since """
                + chartDict[chosenCohortColumn]
                + """s can change over time, like-for-like """
                + chartDict[chosenCohortColumn]
                + """ """
                + metric
                + """ generally are a subset of total """
                + companyOrIndustry
                + """ """
                + metric
                + """."""
            )
            promptDimension = ""
            if column != totalName:
                promptDimension = (
                    """ Like-for-like """
                    + chartDict[chosenCohortColumn]
                    + """ """
                    + metric
                    + """ are shown split by **"""
                    + column
                    + """**."""
                )
            promptLikeForLike = promptLikeForLike + "." + promptDimension
            if promptCagrTotal != False:
                promptCagrValue = (
                    chartDict[CXGRTotal].select(pl.col(totalName).first()).item()
                )
                promptCagrValue = str(promptCagrValue)
                if promptCagrValue:
                    promptCagrTotal = (
                        " The overall like-for-like **"
                        + metric
                        + "** CAGR across the period was "
                        + promptCagrValue
                        + "%. "
                    )
                    promptLikeForLike = promptLikeForLike + promptCagrTotal
            if promptCagrData != False:
                promptCagrData = ":\n{}".format(chartDict[CXGRData])
                if promptCagrData:
                    promptCagrData = (
                        " By "
                        + column
                        + ", the like-for-like **"
                        + metric
                        + "** CAGR across the period was "
                        + promptCagrData
                        + ". "
                    )
                    promptLikeForLike = promptLikeForLike + promptCagrData
            prompt = promptLikeForLike + "."
        else:
            if " by " in metric or " By " in metric:
                promptBy = (
                    "The dataset shows **Average "
                    + metric
                    + "** from "
                    + firstPeriod
                    + " to "
                    + lastPeriod
                    + ". "
                )
                if promptCagrValue:
                    promptCagrTotal = (
                        " The overall **Average "
                        + metric
                        + "** CAGR across the period was "
                        + str(promptCagrValue)
                        + ""
                    )
                promptDf = (
                    " **Average "
                    + metric.title()
                    + "** across the period were :\n{}".format(df)
                )
                if promptCagrTotal != False:
                    promptBy = promptBy + promptCagrTotal
                prompt = promptBy + "."
            elif numberOfName.lower() in metric.lower():
                if column == totalName:
                    promptNber = (
                        "The dataset shows the **"
                        + metric.title()
                        + "** metric from "
                        + firstPeriod
                        + " to "
                        + lastPeriod
                        + ". "
                    )
                elif (
                    plotValuesAsChoice in chartDict
                    and chartDict[plotValuesAsChoice] == absolute
                ):
                    promptNber = (
                        "For every period, the dataset shows the **"
                        + metric.title()
                        + " by "
                        + column
                        + "**. "
                    )
                else:
                    promptNber = (
                        "For every period, the dataset shows the percent mix of **"
                        + metric.title()
                        + " by "
                        + column
                        + "**. "
                    )
                if promptCagrTotal != False:
                    promptNber = promptNber + promptCagrTotal
                if promptCagrData != False:
                    promptNber = promptNber + promptCagrData
                prompt = promptNber
            elif sinceName in column:
                column = column.replace("_" + sinceName, "")
                if (
                    plotValuesAsChoice in chartDict
                    and chartDict[plotValuesAsChoice] == absolute
                ):
                    promptSince = (
                        prompSmall
                        + "For every period, the dataset shows the breakdown of "
                        + metric.lower()
                        + " by "
                        + column
                        + " cohort. A cohort is a group of "
                        + chartDict[chosenCohortColumn]
                        + "s that joined in a given period. Every column represents a "
                        + column
                        + " cohort and every row of the dataset shows, for a given period, the "
                        + metric.lower()
                        + " coming from each "
                        + column
                        + " cohort. "
                    )
                    promptNew = (
                        "Only focus on new cohorts that have material impact on  "
                        + metric.lower()
                        + " ."
                    )
                else:
                    promptSince = (
                        prompSmall
                        + "For every period, the dataset shows the percent mix of "
                        + metric.lower()
                        + " by "
                        + column
                        + " cohort. A cohort is a group of "
                        + chartDict[chosenCohortColumn]
                        + "s that joined in a given period. Every column represents a "
                        + column
                        + " cohort and every row of the dataset shows, for a given period, the percent of "
                        + metric.lower()
                        + " coming from each "
                        + column
                        + " cohort. "
                    )
                    promptNew = (
                        "Only focus on new cohorts that have material impact on  "
                        + metric.lower()
                        + " ."
                    )
                promptSince = promptSince + promptNew
                if promptCagrTotal != False:
                    promptSince = promptSince + promptCagrTotal
                if promptCagrData != False:
                    promptSince = promptSince + promptCagrData
                prompt = promptSince
            elif lostName in column:
                column = column.replace("_" + lostName, "")
                if (
                    plotValuesAsChoice in chartDict
                    and chartDict[plotValuesAsChoice] == absolute
                ):
                    promptSince = (
                        "The dataset shows the breakdown of "
                        + metric.lower()
                        + " by "
                        + column
                        + " loss cohort period. A cohort is a group of "
                        + chartDict[chosenCohortColumn]
                        + " that left in a given period. 'Still active' columns represents the  "
                        + column
                        + " that are still active. The other columns represent the subset of "
                        + column
                        + " lost in each period. Each row of the dataset shows the breakdown of "
                        + metric.lower()
                        + " coming from still active and from "
                        + column
                        + "s that have become inactive in each period. "
                    )
                    promptLost = (
                        "Only focus on lost cohorts that have material impact on  "
                        + metric.lower()
                        + " ."
                    )
                else:
                    promptSince = (
                        prompSmall
                        + "The dataset shows the percent of "
                        + metric.lower()
                        + " by "
                        + column
                        + " loss cohort period. A cohort is a group of "
                        + chartDict[chosenCohortColumn]
                        + " that left in a given period. 'Still active' columns represents the "
                        + column
                        + " that are still active. The other columns represent the subset of "
                        + column
                        + " lost in each period. Each row of the dataset shows the percent breakdown of "
                        + metric.lower()
                        + " coming from still active and from "
                        + column
                        + "s that have become inactive in each periods "
                    )
                    promptLost = (
                        "Only focus on lost cohorts that have material impact on  "
                        + metric.lower()
                        + " ."
                    )
                promptSince = promptSince + promptLost
                if promptCagrTotal != False:
                    promptSince = promptSince + promptCagrTotal
                if promptCagrData != False:
                    promptSince = promptSince + promptCagrData
                prompt = promptSince
            else:
                promptBy = (
                    "The dataset shows the **"
                    + metric.title()
                    + "** metric from "
                    + firstPeriod
                    + " to "
                    + lastPeriod
                    + ". "
                )
                if len(chartDict[metricsToPlotKey]) > 1:
                    promptBy = (
                        "The dataset shows the  **"
                        + chartDict[metricsToPlotKey][0].title()
                        + "** and  **"
                        + chartDict[metricsToPlotKey][1].title()
                        + "** metrics from "
                        + firstPeriod
                        + " to "
                        + lastPeriod
                        + ". "
                    )
                if promptCagrTotal != False:
                    promptBy = promptBy + promptCagrTotal
                if promptCagrData != False:
                    promptBy = promptBy + promptCagrData
                prompt = promptBy
    promptFact = """ Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    prompt = promptFact + promptDescription + prompt + promptDf
    prompt = prompt.replace(". .", ".").replace("..", ".")
    return prompt, firstPeriod, lastPeriod, df


def get_barmekko_prompt(dfCopy, chartDict):
    namingParams = get_naming_params()
    yAxisDimensionKey = namingParams["yAxisDimension"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    yAxisMetricKey = namingParams["yAxisMetric"]
    xAxisMetricKey = namingParams["xAxisMetric"]
    multipliedMetricKey = namingParams["multipliedMetric"]
    barmekkoChart = namingParams["barmekkoChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    singleMetric = namingParams["singleMetric"]
    totalName = namingParams["totalName"]
    showAverageValue = namingParams["showAverageValueName"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    numberOfTop = namingParams["numberOfTop"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    plotTitleText = namingParams["plotTitleText"]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    datasetTypeKey = namingParams["datasetTypeName"]
    companyExpenses = namingParams["companyExpenses"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    costsName = namingParams["costsName"]
    yAxisMetric = chartDict[yAxisMetricKey]
    xAxisMetric = chartDict[xAxisMetricKey]
    multipliedMetric = chartDict[multipliedMetricKey]
    xAxisDimension = chartDict[xAxisDimensionKey]
    title = chartDict[plotTitleText]
    if (
        plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
        and smallMultiplesCharts in chartDict
        and chartDict[smallMultiplesCharts]
    ):
        smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    if (
        yAxisDimensionKey in chartDict
        and chartDict[yAxisDimensionKey]
        and chartDict[yAxisDimensionKey] != nothingFilteredName
    ):
        yAxisDimension = chartDict[yAxisDimensionKey]
    df = duplicate_dataframe(dfCopy)
    df = df.with_columns(
        (pl.col(yAxisMetric) * pl.col(xAxisMetric)).alias(multipliedMetric)
    )
    multipliedMetric = change_metric_if_cost_analysis(multipliedMetric, chartDict)
    df = change_column_names_if_cost_analysis(df, chartDict)
    yAxisMetric = change_metric_if_cost_analysis(yAxisMetric, chartDict)
    xAxisMetric = change_metric_if_cost_analysis(xAxisMetric, chartDict)
    isOtherRank = check_if_other_in_index(df)
    columns, schema = get_schema_and_column_names(df)
    promptChart = ""
    promptOther = ""
    contextMetric = (
        xAxisMetric + "**, **" + yAxisMetric + "** and **" + multipliedMetric
    )
    promptContext, companyOrIndustry, contextMetric = get_context(
        chartDict, contextMetric
    )
    title = replace_ibcs_date_symbol(title, chartDict)
    promptContext, df = explain_currency_and_abbreviations(
        df, chartDict, promptContext, contextMetric
    )
    promptContext = add_prompt_date(promptContext, chartDict)
    promptFilter = add_prompt_filter(chartDict)
    if isOtherRank:
        otherRank = "x"
        if "X" in chartDict:
            otherRank = str(chartDict["X"][numberOfTop])
        promptOther = (
            """ The smaller """
            + xAxisDimension
            + """ items are aggregated in the '"""
            + aggregateOtherItemsName
            + """ """
            + otherRank
            + """' element."""
        )
    if (
        plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
        and smallMultiplesCharts in chartDict
        and chartDict[smallMultiplesCharts]
    ):
        frameArray = []
        smallMultiplesArray = unique_values_lazy(smallMultiplesColumn, df)
        numberOfSmallMultiples = len(smallMultiplesArray)
        smallMultiplesList = str(smallMultiplesArray).replace("[", "").replace("]", "")
        for element in smallMultiplesArray:
            dfFiltered = df.filter(pl.col(smallMultiplesColumn) == element)
            if dfFiltered.height > 0:
                dfFiltered = dfFiltered.sort(yAxisMetric, descending=True)
                dfFiltered = rank_others_as_last(
                    dfFiltered, aggregateOtherItemsNameKey, 99
                )
                frameArray.append(dfFiltered)
        df = pl.concat([pl.DataFrame(f) for f in frameArray])
        numberOfColumns = len(columns)
        columnNames = str(columns).replace("[", "").replace("]", "")
        promptDescription = (
            """ The provided small multiples **"""
            + barmekkoChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """  
        The **"""
            + barmekkoChart
            + """** chart, also called area bar chart, is a variable-width horizontal bar chart.
        The area of each bar maps to the """
            + multipliedMetric
            + """ metric and corresponds to the product of the """
            + yAxisMetric
            + """ metric 
        (which is mapped on the bar length) and of the  """
            + xAxisMetric
            + """ metric (which is mapped on the bar width).
        The """
            + barmekkoChart
            + """ chart is plotted by """
            + xAxisDimension
            + """."""
            + promptOther
            + """        
        The data contains """
            + str(numberOfSmallMultiples)
            + """ small multiples datasets by """
            + smallMultiplesColumn
            + """ stacked on top of each other: """
            + smallMultiplesList
            + """."""
        )
        promptChart = promptDescription
    else:
        df = df.sort(yAxisMetric, descending=True)
        df = rank_others_as_last(df, aggregateOtherItemsNameKey, 99)
        promptDescription = (
            """ The provided **"""
            + barmekkoChart
            + """** chart dataset has the following title: '"""
            + title
            + """'."""
            + promptContext
            + """"""
            + promptFilter
            + """ 
        The **"""
            + barmekkoChart
            + """** chart, also called area bar chart, is a variable-width horizontal bar chart.
        The area of each bar maps to the """
            + multipliedMetric
            + """ metric and corresponds to the product of the """
            + yAxisMetric
            + """ metric 
        (which is mapped on the bar length) and of the  """
            + xAxisMetric
            + """ metric (which is mapped on the bar width).
        The """
            + barmekkoChart
            + """ chart is plotted by """
            + xAxisDimension
            + """."""
            + promptOther
            + """ """
        )
        promptChart = promptDescription
    promptFact = """\n\n\n Only provide fact-based evidences that can be derived from the data presented to you. Do not make inferences or assumptions beyond the data presented in the chart."""
    promptDf = "\n\nThe dataset is as follows :\n{}".format(df)
    promptChart = promptChart + promptDf + promptFact
    return promptChart, df
