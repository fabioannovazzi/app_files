import base64
import colorsys
import copy
import io
import json

# All data manipulation should rely on polars
import logging
import math
import random
import sys
from io import BytesIO
from typing import Any, Dict, List

import numpy as np
import polars as pl

from modules.layout.memoization import check_collect
from modules.utils.polars_excel_writer import write_polars_excel

if "modules.utilities.utils" in sys.modules:
    utils_mod = sys.modules["modules.utilities.utils"]
else:
    import modules.utilities.utils as utils_mod

from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.ui_notifier import ui as notifier

try:
    from modules.utilities.helpers import (
        add_running_total,
        check_and_clean_columns,
        check_and_group_by_cols,
        check_if_periods_in_columns,
        drop_columns,
        duplicate_dataframe,
        flatten_cols_polars,
        get_period_length,
        get_periods_array,
        take_filtered_value_out_of_option_list,
        unique,
    )
except ImportError as e:  # pragma: no cover - allow partial stubs in tests
    import types

    logging.getLogger(__name__).warning("common_data_utils helpers import error: %s", e)

    _helpers = sys.modules.get(
        "modules.utilities.helpers", types.ModuleType("modules.utilities.helpers")
    )

    add_running_total = getattr(_helpers, "add_running_total", lambda df: df)
    check_and_clean_columns = getattr(
        _helpers,
        "check_and_clean_columns",
        lambda df, group_cols, value_cols: (group_cols, value_cols),
    )
    check_and_group_by_cols = getattr(
        _helpers,
        "check_and_group_by_cols",
        lambda df, group_cols, value_cols: (df, group_cols, value_cols),
    )
    check_if_periods_in_columns = getattr(
        _helpers, "check_if_periods_in_columns", lambda *a, **k: False
    )
    drop_columns = getattr(_helpers, "drop_columns", lambda df, cols: df)
    duplicate_dataframe = getattr(_helpers, "duplicate_dataframe", lambda df: df)
    flatten_cols_polars = getattr(
        _helpers, "flatten_cols_polars", lambda df, delim="": df
    )
    get_period_length = getattr(_helpers, "get_period_length", lambda *a, **k: 0)
    get_periods_array = getattr(_helpers, "get_periods_array", lambda *a, **k: [])
    take_filtered_value_out_of_option_list = getattr(
        _helpers,
        "take_filtered_value_out_of_option_list",
        lambda arr, val: arr,
    )
    unique = getattr(_helpers, "unique", lambda arr: list(dict.fromkeys(arr)))

ensure_lazyframe = utils_mod.ensure_lazyframe
get_schema_and_column_names = utils_mod.get_schema_and_column_names
is_valid_lazyframe = getattr(
    utils_mod, "is_valid_lazyframe", lambda df: isinstance(df, pl.LazyFrame)
)
get_row_count = getattr(
    utils_mod,
    "get_row_count",
    lambda df: (
        df.select(pl.len()).collect(engine="streaming")[0, 0]
        if isinstance(df, pl.LazyFrame)
        else df.height
    ),
)

logger = logging.getLogger(__name__)


def check_value_column_exist(
    df: pl.DataFrame | pl.LazyFrame, valueCols: List[str]
) -> list[str]:
    """Return value columns present in ``df``."""
    checkedValueCols: list[str] = []
    columns, schema = get_schema_and_column_names(df)
    for column in valueCols:
        if column in columns:
            checkedValueCols.append(column)
    return checkedValueCols


def build_equal_to_query_string_element(colName: str, keyString: str) -> str:
    """Return a query fragment of the form ``col == 'value'``."""
    leftSideElement = "" + colName + " == "
    cleanedValue = str(keyString)
    cleanedValue = cleanedValue.replace("'", "")
    rightSideElement = "'" + cleanedValue + "'"
    queryStringElement = leftSideElement + rightSideElement
    return queryStringElement


def get_query_string_from_dict(filterDict: Dict[str, str]) -> str:
    """Build a boolean query string from a mapping of column to value."""
    count = 0
    fullQueryString = ""
    for colName in filterDict:
        queryStringElement = build_equal_to_query_string_element(
            colName, filterDict[colName]
        )
        fullQueryString = assemble_query_string_elements(
            queryStringElement, fullQueryString, count
        )
        count = count + 1
    return fullQueryString


def take_price_out_of_valueCols(metricArray: List[str]) -> list[str]:
    """Return ``metricArray`` without any elements containing the price name."""
    namingParams = get_naming_params()
    priceName = namingParams["priceName"]
    valueCols: list[str] = []
    for element in metricArray:
        if priceName not in element:
            valueCols.append(element)
    return valueCols


def assemble_query_string_elements(
    queryStringElement: str, fullQueryString: str, count: int
) -> str:
    """Concatenate query fragments with ``and`` separators."""
    if count == 0:
        fullQueryString = queryStringElement
    else:
        fullQueryString = fullQueryString + " and " + queryStringElement
    return fullQueryString


def complete_combination_with_all_parents(
    testArray: list[str], indexDict: Dict[str, Any]
) -> list[str]:
    """Add missing hierarchical parents to ``testArray``."""
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    indexDict = indexDict[hierarchicalName]
    for element in indexDict:
        testArray = insert_missing_parents(testArray, indexDict[element])
    testArray.sort()
    return testArray


def delete_hierarchical_parents(
    testArray: list[str], indexDict: Dict[str, Any]
) -> list[str]:
    """Remove duplicate hierarchy parents from ``testArray``."""
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    indexDict = indexDict[hierarchicalName]
    for element in indexDict:
        testArray = check_if_more_than_one_in_common(testArray, indexDict[element])
    return testArray


def _reindex_by_period(df: pl.LazyFrame, period_order: list) -> pl.LazyFrame:
    """
    Reindex a Polars LazyFrame by a specified period order.
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    lookup = pl.DataFrame(
        {periodName: period_order, "sort_order": range(len(period_order))}
    ).lazy()
    return (
        df.join(lookup, on=periodName, how="left").sort("sort_order").drop("sort_order")
    )


def sort_periods_polars(
    df: pl.LazyFrame, chartDict: dict, paramDict: dict
) -> pl.LazyFrame:
    """Sort periods using the historical ordering logic implemented with Polars."""
    namingParams = get_naming_params()
    yearName = namingParams["yearName"]
    periodName = namingParams["periodName"]
    periodChoice = namingParams["periodChoice"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    selectedPeriods = namingParams["selectedPeriods"]
    chosenChart = namingParams["chosenChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    changedTimeAggregation = namingParams["changedTimeAggregation"]
    chosenChart = chartDict[chosenChart]
    periodChoice = chartDict[periodChoice]
    periodOrder = chartDict[selectedPeriods]

    df_count = df.select(pl.len()).collect(engine="streaming")[0, 0]
    index_order = (
        df.select(pl.col(periodName)).collect().get_column(periodName).to_list()
    )
    check_collect("ACA", "df_count", df_count)
    check_collect("ADA", "indexOrder", index_order)

    if (
        periodChoice == yearName
        and compareWithYearBefore in chartDict
        and (
            changedTimeAggregation not in paramDict
            or not paramDict[changedTimeAggregation]
        )
    ):
        if df_count == 2:
            df = _reindex_by_period(df, periodOrder)
        elif chartDict[compareWithYearBefore]:
            df = df.sort(periodName, descending=True)
        else:
            df = df.sort(periodName, descending=False)

    elif index_order != periodOrder:
        if set(index_order) == set(periodOrder):
            df = _reindex_by_period(df, periodOrder)
        else:
            df = df.sort(periodName, descending=False)

    return df


def transform_lazy_df(
    lazy_df,
    chartDict,
    dimensionName,
    itemName,
    plotValuesAsChoice,
    absolute,
    percentName,
    valueName,
):
    """
    Applies the per-DataFrame transformations in lazy Polars:
      1. Drop the existing valueName column if present
      2. Create or ensure dimensionName is a string column
      3. Melt either into (dimensionName, itemName, valueName) or
         (dimensionName, itemName, percentName)
      4. Compute the total-based percentage or multiply by the 'most recent'
         absolute value if needed.
    """
    columns, _ = get_schema_and_column_names(lazy_df)  # Adapt this helper for Polars

    # If the column to drop exists, drop it
    if valueName in columns:
        lazy_df = lazy_df.drop(valueName)

    # In Pandas code, we reset the index named dimensionName into a column.
    # Polars doesn't have an index concept, so adapt as needed:
    # If dimensionName doesn't exist, you might do a row_count or similar.
    if dimensionName not in columns:
        lazy_df = lazy_df.with_row_index(name=dimensionName)

    # Cast dimensionName to string
    lazy_df = lazy_df.with_columns(pl.col(dimensionName).cast(pl.Utf8))
    if plotValuesAsChoice in chartDict and chartDict[plotValuesAsChoice] == absolute:
        lazy_cols, lazy_schema = get_schema_and_column_names(lazy_df)
        cols_to_unpivot = [
            col
            for col in lazy_cols
            if col != dimensionName
            and lazy_schema
            and col in lazy_schema
            and lazy_schema[col].is_numeric()
        ]
        df_melted = lazy_df.unpivot(
            index=[dimensionName],
            on=cols_to_unpivot,
            variable_name=itemName,
            value_name=valueName,
        )
        # We need total of valueName to compute percentage:
        total_df = df_melted.select(pl.col(valueName).sum().alias("totalValue"))
        # Cross join total back in to avoid collecting:
        df_melted = (
            df_melted.join(total_df, how="cross")
            .with_columns(
                ((pl.col(valueName) / pl.col("totalValue")) * 100)
                .round(0)
                .alias(percentName)
            )
            .drop("totalValue")
        )

        return df_melted

    else:
        lazy_cols, lazy_schema = get_schema_and_column_names(lazy_df)
        cols_to_unpivot = [
            col
            for col in lazy_cols
            if col != dimensionName
            and lazy_schema
            and col in lazy_schema
            and lazy_schema[col].is_numeric()
        ]
        df_melted = lazy_df.unpivot(
            index=[dimensionName],
            on=cols_to_unpivot,
            variable_name=itemName,
            value_name=percentName,
        )
        # If "most recent" is from chartDict[absolute], we need its last row’s value:
        # Assume chartDict[absolute] is also a lazy Polars frame that yields a single row in .tail(1).
        df_most_recent = chartDict[absolute].tail(1)

        # We must know which column in df_most_recent we want to multiply with.
        # Suppose it has a single column called "most_recent_value".
        # Or rename that column for clarity:
        # e.g., rename the existing single column to "most_recent_value":
        old_cols, _ = get_schema_and_column_names(df_most_recent)
        if len(old_cols) == 1:
            df_most_recent = df_most_recent.rename({old_cols[0]: "most_recent_value"})
        else:
            # If there's more than one column, adapt or select the right one
            # Example: assume the first column is the numeric value:
            df_most_recent = df_most_recent.rename(
                {old_cols[0]: "most_recent_value"}
            ).select("most_recent_value")

        # Cross join so every row can multiply the percent by the single "most_recent_value"
        df_joined = df_melted.join(df_most_recent, how="cross")

        df_joined = df_joined.with_columns(
            (pl.col(percentName) * pl.col("most_recent_value")).alias(valueName)
        ).drop("most_recent_value")

        return df_joined


def build_is_in_query_string_element(colName, array, operator):
    """
    builds "must be equal to" query string
    """
    leftSideElement = "" + colName + operator
    cleanedValue = str(array)
    cleanedValue = cleanedValue.replace("'", '"')
    rightSideElement = "" + cleanedValue + ""
    queryStringElement = leftSideElement + rightSideElement
    return queryStringElement


def clean_array_values(array):
    """
    replaces blances with underscores in array elements
    """
    newArray = []
    for element in array:
        element = stripe_replace_and_clean(element, True)
        newArray.append(element)
    return newArray


def stripe_replace_and_clean(element, replacehyphen):
    """
    to clean everything in the same way
    """
    element = element.strip()
    element = element.replace(",", "")
    element = element.replace(".", "")
    element = element.replace("'", "")
    element = element.replace(" ", "_")
    element = element.replace(":", "")
    if replacehyphen:
        element = element.replace("-", "_")
        element = element.replace("/", "_")
    return element


def filter_out_found_and_not_found_dataframe(
    df_lazy: pl.LazyFrame,  # equivalent to dfCopy in your original code
    CXGRName: str,
    foundArray: list,
    frameArray: list,
    chosenDimension: str,  # unused in the snippet, but kept for signature compatibility
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """
    Split a LazyFrame using idiomatic Polars filters:
      - ``dfFound``: rows where ``chosenDimension`` is in ``foundArray``
      - ``dfNotFound``: rows where it is not, then drop ``CXGRName``
    """
    # 1) Clone if you truly want a separate pipeline (mimicking 'duplicate_dataframe'):
    # df_lazy = df_lazy.with_row_index("index_col")
    df_clone = df_lazy.clone()

    # 2) Filter rows where "index_col" is in foundArray
    dfFound = df_clone.filter(pl.col(chosenDimension).is_in(foundArray))

    # 3) Filter rows where "index_col" is NOT in foundArray
    dfNotFound = df_clone.filter(~pl.col(chosenDimension).is_in(foundArray))

    # 4) Drop the CXGRName column from dfNotFound
    dfNotFound = dfNotFound.drop(CXGRName)

    return dfNotFound, dfFound


def drop_AC_and_PY_month(df, column, valueCols, chartDict):
    """
    if most recent date is at the middle of a month the resulting AC PY dataset can have a common/extra months that
    makes calculations wrong and that we need to eliminate
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    acPyArray = get_periods_array(df)

    if plName not in acPyArray:
        df = df.with_columns(pl.col(dateName).dt.strftime("%Y-%m").alias(workColumn))
        group_byCols = [dateName, periodName, column]
        for element in acPyArray:
            if element != acName:
                pyName = element

        dfAc = df.filter(pl.col(periodName) == acName)
        acDateArray = (
            dfAc.select(pl.col(workColumn).unique()).collect()[workColumn].to_list()
        )
        dfPy = df.filter(pl.col(periodName) == pyName)
        pyDateArray = (
            dfPy.select(pl.col(workColumn).unique()).collect()[workColumn].to_list()
        )
        commonDates = set(acDateArray) & set(pyDateArray)
        if commonDates:
            df = df.with_columns(
                pl.when(
                    (pl.col(workColumn).is_in(list(commonDates)))
                    & (pl.col(periodName) == acName)
                )
                .then(pl.lit(pyName))
                .otherwise(pl.col(periodName))
                .alias(periodName)
            )
            df = drop_columns(df, [workColumn])
            valueCols = check_value_column_exist(df, valueCols)
            df = df.group_by(group_byCols).agg([pl.col(col).sum() for col in valueCols])
            df = df.with_columns(
                pl.col(dateName).dt.strftime("%Y-%m").alias(workColumn)
            )
            dfAc = df.filter(pl.col(periodName) == acName)
            acDateArray = (
                dfAc.select(pl.col(workColumn).unique()).collect()[workColumn].to_list()
            )
            dfPy = df.filter(pl.col(periodName) == pyName)
            pyDateArray = (
                dfPy.select(pl.col(workColumn).unique()).collect()[workColumn].to_list()
            )
            pyDateArray.sort()
            numberOfPyDates = len(pyDateArray)
            if numberOfPyDates > 12:
                dropDatesArray = pyDateArray[0 : numberOfPyDates - 12]
                df = df.with_columns(
                    pl.when(
                        (pl.col(workColumn).is_in(dropDatesArray))
                        & (pl.col(periodName) == pyName)
                    )
                    .then(1)
                    .otherwise(None)
                    .alias(workColumnTwo)
                )
                df = df.filter(pl.col(workColumnTwo) != 1)
                df = drop_columns(df, [workColumn, workColumnTwo])
    return df


def get_number_of_multiples(df, mainDimension, chartDict):
    """
    we compare the number of existing dimensions to those that the user wants to see. If too many, we return a smaller array of items
    """
    namingParams = get_naming_params()
    aggregateOtherWaterfalls = namingParams["aggregateOtherWaterfalls"]
    aggregateOtherWaterfallsName = namingParams["aggregateOtherWaterfallsName"]
    numberOfSmallMultiples = namingParams["numberOfSmallMultiplesWaterfall"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    nothingThereString = namingParams["nothingThereString"]
    numberOfSmallMultiples = chartDict[numberOfSmallMultiples]
    aggregateOtherWaterfalls = chartDict[aggregateOtherWaterfalls]
    # Use Polars to retrieve unique values, supporting LazyFrame/DataFrame
    uniqueItems = (
        ensure_lazyframe(df)
        .select(pl.col(mainDimension).unique())
        .collect()
        .get_column(mainDimension)
        .to_list()
    )
    showItems = []
    possibleItems = []
    count = 1
    for element in uniqueItems:
        if len(element) > 0 and element not in [
            nothingFilteredName,
            nothingThereString,
        ]:
            possibleItems.append(element)
            if count <= numberOfSmallMultiples:
                showItems.append(element)
                count = count + 1
    if aggregateOtherWaterfalls and len(possibleItems) > len(showItems):
        showItems.append(aggregateOtherWaterfallsName)
    return showItems


def make_filtered_small_multiple_dataframe(
    df, mainDimension, element, indexCols, chartDict, count
):
    """
    we filter the dataframe on the item we need for a specific small multiple and take that item out of indexCols and of the dataframe
    """
    df = aggregate_smaller_items(df, element, mainDimension, chartDict, count, False)
    dfFiltered = df.filter(pl.col(mainDimension) == element)
    df = df.filter(pl.col(mainDimension) != element)
    dfFiltered = drop_columns(dfFiltered, [mainDimension])
    if mainDimension in indexCols:
        indexCols = take_filtered_value_out_of_option_list(indexCols, mainDimension)
    return dfFiltered, df, indexCols


def aggregate_smaller_items(df, element, mainDimension, chartDict, count, filterDfBase):
    """
    check if we need to aggregate all the remaining items
    """
    namingParams = get_naming_params()
    aggregateOtherWaterfalls = namingParams["aggregateOtherWaterfalls"]
    aggregateOtherWaterfallsName = namingParams["aggregateOtherWaterfallsName"]
    numberOfSmallMultiples = namingParams["numberOfSmallMultiplesWaterfall"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    workColumn = namingParams["workColumn"]
    varianceAmount = namingParams["varianceAmountName"]
    varianceTypeName = namingParams["varianceTypeName"]
    numberOfSmallMultiples = chartDict[numberOfSmallMultiples]
    aggregateOtherWaterfalls = chartDict[aggregateOtherWaterfalls]
    group_byCols = [varianceTypeName, mainDimension]
    aggregationCols = [varianceAmount]
    if (
        aggregateOtherWaterfalls
        and count == numberOfSmallMultiples + 1
        and element == aggregateOtherWaterfallsName
    ):
        df = df.with_columns(pl.lit(aggregateOtherWaterfallsName).alias(mainDimension))
        if not filterDfBase:
            group_byCols, aggregationCols = check_and_clean_columns(
                df, group_byCols, aggregationCols
            )
            df = df.group_by(group_byCols).agg(
                [pl.col(col).sum() for col in aggregationCols]
            )
            df = df.with_columns(pl.col(varianceAmount).abs().alias(workColumn))
            df = df.sort(workColumn, descending=True)
            df = add_running_total(df)
            df = drop_columns(df, [workColumn])
    return df


def get_subtotals(paramDict, chartDict, dfCopy, mainDimension, element, count, metric):
    """
    we need to get the relevant initial and final subtotal for each small multiple plot
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    isColumnMultiplied = namingParams["isColumnMultiplied"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    netOfDiscount = namingParams["netOfDiscountName"]
    marginName = namingParams["marginName"]
    separatorString = namingParams["separatorString"]
    periodsArray = configParams["periodsArray"]
    varianceInPercent = namingParams["varianceInPercent"]
    totalAmountPeriodZeroKey = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOneKey = namingParams["totalAmountPeriodOne"]
    isFilteredKey = namingParams["isFilteredKey"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    marginName = namingParams["marginName"]
    df = aggregate_smaller_items(dfCopy, element, mainDimension, chartDict, count, True)
    df = dfCopy.filter(pl.col(mainDimension) == element)
    dfFiltered = dfCopy.filter(pl.col(mainDimension) != element)
    columns, schema = get_schema_and_column_names(df)
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]
    totalPeriodZeroAmountNotFiltered = paramDict[totalAmountPeriodZeroKey]
    totalPeriodOneAmountNotFiltered = paramDict[totalAmountPeriodOneKey]
    if metric == amountName:
        if amountPeriodZero in columns:
            totalPeriodZeroValue = df.select(pl.col(amountPeriodZero).sum()).item()
            totalPeriodOneValue = df.select(pl.col(amountPeriodOne).sum()).item()
            if paramDict[isColumnMultiplied]:
                totalPeriodZeroValue = totalPeriodZeroValue / multiplyConstant
                totalPeriodOneValue = totalPeriodOneValue / multiplyConstant
    elif metric == discountName:
        netOfDiscountPeriodZero = netOfDiscount + separatorString + periodsArray[0]
        netOfDiscountPeriodOne = netOfDiscount + separatorString + periodsArray[1]
        if netOfDiscountPeriodZero in columns:
            totalPeriodZeroValue = df.select(
                pl.col(netOfDiscountPeriodZero).sum()
            ).item()
            totalPeriodOneValue = df.select(pl.col(netOfDiscountPeriodOne).sum()).item()
            if paramDict[isColumnMultiplied]:
                totalPeriodZeroValue = totalPeriodZeroValue / multiplyConstant
                totalPeriodOneValue = totalPeriodOneValue / multiplyConstant
            if chartDict[varianceInPercent]:
                totalPeriodZeroValue = (
                    totalPeriodZeroValue / totalPeriodZeroAmountNotFiltered * 100
                )
                totalPeriodOneValue = (
                    totalPeriodOneValue / totalPeriodOneAmountNotFiltered * 100
                )
    elif metric == marginName:
        marginZero = marginName + separatorString + periodsArray[0]
        marginOne = marginName + separatorString + periodsArray[1]
        if marginZero in columns:
            totalPeriodZeroValue = df.select(pl.col(marginZero).sum()).item()
            totalPeriodOneValue = df.select(pl.col(marginOne).sum()).item()
            if paramDict[isColumnMultiplied]:
                totalPeriodZeroValue = totalPeriodZeroValue / multiplyConstant
                totalPeriodOneValue = totalPeriodOneValue / multiplyConstant
            if chartDict[varianceInPercent]:
                totalPeriodZeroValue = (
                    totalPeriodZeroValue / totalPeriodZeroAmountNotFiltered * 100
                )
                totalPeriodOneValue = (
                    totalPeriodOneValue / totalPeriodOneAmountNotFiltered * 100
                )
    totalVarianceValue = totalPeriodOneValue - totalPeriodZeroValue
    return totalPeriodZeroValue, totalPeriodOneValue, totalVarianceValue, dfFiltered


def drop_columns_with_all_blancs(df, outputIndexCols, toColorColumns, excludeArray):
    """
    if a columns has all blancs in each row we need to drop it
    """
    cleanedToColorColsArray = []
    dropCols = []
    for column in outputIndexCols:
        if column not in excludeArray:
            uniqueValues = (
                ensure_lazyframe(df)
                .select(pl.col(column).unique())
                .collect()
                .get_column(column)
                .to_list()
            )
            if len(uniqueValues) == 1 and uniqueValues[0] == "":
                dropCols.append(column)
    for column in toColorColumns:
        if column not in dropCols:
            cleanedToColorColsArray.append(column)
    df = drop_columns(df, dropCols)
    return df, cleanedToColorColsArray


def add_missing_elements(
    df: pl.DataFrame | pl.LazyFrame, elements: list[str]
) -> pl.LazyFrame:
    """Return ``df`` with all ``elements`` present and sorted by their order."""

    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]

    lazy_df = df.lazy() if isinstance(df, pl.DataFrame) else df

    lookup = (
        pl.DataFrame({workColumn: elements}).with_row_index(name="sort_order").lazy()
    )

    missing_df = lookup.select(workColumn).join(
        lazy_df.select(workColumn), on=workColumn, how="anti"
    )

    combined = pl.concat([lazy_df, missing_df], how="vertical")

    result = (
        combined.with_row_index(name="orig_order")
        .join(lookup, on=workColumn, how="left")
        .with_columns(pl.col("sort_order").fill_null(len(elements)))
        .sort(["sort_order", "orig_order"])
        .drop(["sort_order", "orig_order"])
    )

    return result


def concat_lazy_frames(frames: list[pl.LazyFrame]) -> pl.LazyFrame:
    """
    Concatenate a list of Polars LazyFrames vertically and return
    a single Polars LazyFrame.
    """
    # If no frames are provided, return an empty LazyFrame
    if not frames:
        return pl.LazyFrame()  # Optionally specify a schema if needed
    return pl.concat(frames, how="vertical")


def concatenate_dfFound_and_dfNotFound_dataframes(
    df: pl.LazyFrame, frameArray: list[pl.LazyFrame]
) -> pl.LazyFrame:
    """
    If frameArray is non-empty, concatenate its contents (LazyFrames)
    and return the result. Otherwise, just return df.
    """
    if frameArray:
        df = concat_lazy_frames(frameArray)
    return df


def append_dfFound_and_dfNotFound_to_array(
    dfFound: pl.LazyFrame, dfNotFound: pl.LazyFrame, element: int, frameArray: list
):
    """
    Appends dfFound and dfNotFound to frameArray with a 'periodsMissing'
    boolean column based on the provided naming parameters.
    """
    namingParams = get_naming_params()
    periodsMissing = namingParams["periodsMissing"]

    # If element == 0, set dfFound[periodsMissing] = False
    # and append it to frameArray
    if element == 0:
        dfFound = set_periods_missing_column(dfFound, periodsMissing, False)
        frameArray.append(dfFound)

    # For dfNotFound, set dfNotFound[periodsMissing] = True
    # and append it to frameArray
    dfNotFound = set_periods_missing_column(dfNotFound, periodsMissing, True)
    frameArray.append(dfNotFound)

    return frameArray, dfFound, dfNotFound


def set_CAGX_names(periodLengthInMonths, chartDict, paramDict):
    namingParams = get_naming_params()
    selectedPeriods = namingParams["selectedPeriods"]
    periodChoice = namingParams["periodChoice"]
    plName = namingParams["plName"]
    deltaName = namingParams["deltaName"]
    yearName = namingParams["yearName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]
    CAGRName = namingParams["CAGRName"]
    CQGRName = namingParams["CQGRName"]
    CMGRName = namingParams["CMGRName"]
    CWGRName = namingParams["CWGRName"]
    selectedPeriods = chartDict[selectedPeriods]
    periodChoice = chartDict[periodChoice]
    if selectedPeriods[0] == plName or not periodChoice:
        CXGRName = deltaName
    else:
        periodDatesLengthInMonths = int(round(periodLengthInMonths, 0))
        if periodChoice == yearName and periodDatesLengthInMonths >= 24:
            CXGRName = CAGRName
        elif periodChoice == yearName and periodDatesLengthInMonths <= 13:
            CXGRName = CMGRName
        elif periodChoice == yearName and periodDatesLengthInMonths < 24:
            CXGRName = CQGRName
        elif periodChoice == quarterName:
            CXGRName = CQGRName
        elif periodChoice == monthName:
            CXGRName = CMGRName
        elif periodChoice == weekName:
            CXGRName = CWGRName
    return CXGRName


def add_row_to_dataframe(
    df: pl.DataFrame | pl.LazyFrame,
    rowArray: list[Any],
    endArray: list[Any],
    position: str,
) -> pl.LazyFrame:
    """Append ``rowArray`` to ``df`` and return a ``LazyFrame``."""

    df_lf = ensure_lazyframe(df)
    columns, schema = get_schema_and_column_names(df_lf)
    lengthDiff = len(columns) - (len(rowArray) + len(endArray))
    if lengthDiff > 1:
        rowArray = rowArray + [None] * lengthDiff

    rowArray = rowArray + endArray
    row_values = dict(zip(columns, rowArray))
    if schema:
        new_row = pl.DataFrame([row_values], schema=schema, strict=False).lazy()
    else:
        new_row = pl.DataFrame([rowArray], schema=columns, orient="row").lazy()

    if position == "head":
        return pl.concat([new_row, df_lf], how="vertical")
    if position == "beforeLast":
        insert_idx = get_row_count(df_lf) - 1
        head = df_lf.slice(0, insert_idx)
        tail = df_lf.slice(insert_idx, None)
        return pl.concat([head, new_row, tail], how="vertical")
    return pl.concat([df_lf, new_row], how="vertical")


def horizontal_cumsum(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Imitate axis=1 cumsum in Polars by iterating columns in order.
    For each column:
       running_sum = previous_sum + current_column
    """
    columns, _ = get_schema_and_column_names(lf)
    exprs = []

    running_sum = pl.lit(0)
    for col in columns:
        running_sum = running_sum + pl.col(col)
        exprs.append(running_sum.alias(col))

    return lf.select(exprs)


def get_cum_sum_dataframe(
    lf: pl.DataFrame | pl.LazyFrame,
    chosenChart: str,
    dfNegative,
    message: str,
) -> pl.LazyFrame:
    """Return a cumulative-sum ``LazyFrame`` for chart rendering using Polars.

    ``lf`` may be either a :class:`~polars.DataFrame` or :class:`~polars.LazyFrame`.
    """
    namingParams = get_naming_params()
    valueName = namingParams["valueName"]
    marimekkoChart = namingParams["marimekkoChart"]

    lf_result = lf.lazy() if isinstance(lf, pl.DataFrame) else lf

    # 1) Fill NaN with 0
    lf_result = lf_result.fill_nan(0)

    # 2) Select only numeric columns (float or integer types)
    lf_result = lf_result.select(pl.selectors.numeric())

    # 3) If chosenChart is "marimekko", drop the `valueName` column
    if chosenChart == marimekkoChart:
        lf_result = lf_result.drop(valueName)

    # 4) Apply horizontal cumsum (simulating cumsum(axis=1))
    lf_result = horizontal_cumsum(lf_result)

    # 5) Handle dfNegative and message logic
    #    ``dfNegative`` can be a Polars frame or another sequence-like object.
    #    Use ``get_row_count`` when available to avoid ``len`` errors on LazyFrames.
    try:
        negative_count = (
            get_row_count(dfNegative)
            if isinstance(dfNegative, (pl.DataFrame, pl.LazyFrame))
            else dfNegative.__len__()
        )
    except Exception as e:
        logging.exception(e)
        notifier.error("Something went wrong while computing the negative count.")
        negative_count = 0
    if negative_count == 0:
        message = ""

    return lf_result, dfNegative, message


def set_periods_missing_column(
    df: pl.LazyFrame, column_name: str, value: bool
) -> pl.LazyFrame:
    """
    Helper function to set a boolean column on a Polars LazyFrame.
    """
    return df.with_columns(pl.lit(value).alias(column_name))


def concat_df_to_dfMerged(
    df: pl.DataFrame | pl.LazyFrame, dfMerged: pl.DataFrame, dropCols
) -> pl.DataFrame:
    """Horizontally concatenate ``df`` onto ``dfMerged`` using Polars."""

    df = ensure_polars_df(df).drop(dropCols)
    return pl.concat([dfMerged, df], how="horizontal")


def sort_small_multiples(
    df: pl.DataFrame | pl.LazyFrame, count: int, sortArray: list[str]
) -> tuple[pl.LazyFrame, list[str]]:
    """Return ``df`` lazily sorted by ``workColumn``."""

    df_lf = ensure_lazyframe(df)
    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]

    if count == 1:
        sortArray = (
            df_lf.select(pl.col(workColumn).unique())
            .collect()
            .get_column(workColumn)
            .to_list()
        )
    else:
        current = (
            df_lf.select(pl.col(workColumn).unique())
            .collect()
            .get_column(workColumn)
            .to_list()
        )
        sort_order = sortArray + [c for c in current if c not in sortArray]
        df_lf = reindex_polars(df_lf, workColumn, sort_order)

    return df_lf, sortArray


def calculate_total_cagr(
    df_lazy: pl.LazyFrame, metric: str, CXGRName: str, periodOrder: list, count: int
) -> pl.LazyFrame:
    """
    Polars-lazy equivalent pipeline:
      1) Group by ``periodName`` and sum ``metric``
      2) Add a literal ``totalName`` column
      3) Compute CAGR with window expressions
      4) Clean the CAGR column
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]  # e.g. "period"
    totalName = namingParams["totalName"]  # e.g. "total"

    # 1) Group by `periodName` and sum `metric`
    df_lazy = df_lazy.group_by(periodName).agg(pl.col(metric).sum().alias(metric))

    # 2) Add a column `totalName` with literal value = totalName
    df_lazy = df_lazy.with_columns(pl.lit(totalName).alias(totalName))

    # 3) Compute CAGR using a Polars-lazy window expression approach
    df_lazy = compute_cagr_rate(
        df_lazy=df_lazy,
        CXGRName=CXGRName,
        chosenDimension=totalName,  # we group over the "total" dimension
        periodOrder=periodOrder,
        count=count,
        metric_col=metric,
    )

    # 4) Clean the CAGR column (must also be a Polars-lazy function)
    df_lazy = clean_cagr_column(df_lazy, CXGRName, periodOrder)

    return df_lazy


def check_if_must_not_calculate_cagr(chartDict, paramDict):
    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    showCAGRKey = namingParams["showCAGR"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    onePeriodOnly = namingParams["onePeriodOnly"]
    showCAGR = notMetConditionValue
    if chartDict[plotValuesAsChoice] != absolute:
        chartDict[showCAGRKey] = notMetConditionValue
    if onePeriodOnly in paramDict and paramDict[onePeriodOnly]:
        chartDict[showCAGRKey] = notMetConditionValue
    if showCAGRKey in chartDict:
        showCAGR = chartDict[showCAGRKey]
    return showCAGR


def add_count_metrics_to_cagr_array(CAGRArray, chartDict):
    namingParams = get_naming_params()
    countMetricsSumArrayKey = namingParams["countMetricsSumArray"]
    countMetricsAvgArrayKey = namingParams["countMetricsAvgArray"]
    if (
        countMetricsSumArrayKey in chartDict
        and len(chartDict[countMetricsSumArrayKey]) > 0
    ):
        CAGRArray = CAGRArray + chartDict[countMetricsSumArrayKey]
    if (
        countMetricsAvgArrayKey in chartDict
        and len(chartDict[countMetricsAvgArrayKey]) > 0
    ):
        CAGRArray = CAGRArray + chartDict[countMetricsAvgArrayKey]
    return CAGRArray


def sort_index_and_periods_for_cagr(
    df_lazy: pl.LazyFrame,
    chosenDimension: str,
    xColumn: str,
    metric: str,
    chartDict: dict,
    paramDict: dict,
) -> tuple[pl.LazyFrame, list]:
    """Return a tuple of ``(lazy_frame, periodOrder_list)`` computed with Polars."""

    # 1) Fetch parameter dictionaries (like in your original code)
    namingParams = get_naming_params()
    configParams = get_config_params()

    maxPeriodsForBarChart_key = namingParams["maxPeriodsForBarChart"]
    periodChoice_key = namingParams["periodChoice"]
    compareWithYearBefore_key = namingParams["compareWithYearBefore"]
    yearName = namingParams["yearName"]
    selectedPeriods_key = namingParams["selectedPeriods"]
    plName = namingParams["plName"]

    # 2) Extract dynamic values from chartDict and configParams
    maxPeriodsForBarChart = configParams[maxPeriodsForBarChart_key]
    periodChoice = chartDict[namingParams["periodChoice"]]
    selectedPeriods = chartDict[namingParams["selectedPeriods"]]

    # 3) Select only [chosenDimension, xColumn, metric]
    df_lazy = df_lazy.select([chosenDimension, xColumn, metric])

    # 4) Compute periodOrder lazily
    if hasattr(utils_mod, "unique_list_lazy"):
        periodOrder = utils_mod.unique_list_lazy(xColumn, df_lazy)
    else:
        periodOrder = (
            df_lazy.select(pl.col(xColumn).unique())
            .collect(engine="streaming")[xColumn]
            .to_list()
        )
    check_collect("AAF", "periodOrder", periodOrder)
    # 5) Decide sort order (ascending vs descending)
    #    This logic replicates:
    #        if periodChoice == yearName and compareWithYearBefore in chartDict and chartDict[compareWithYearBefore]:
    #            descending = True
    #        elif selectedPeriods[0] == plName:
    #            descending = True
    #        else:
    #            descending = False

    if (
        periodChoice == yearName
        and compareWithYearBefore_key in chartDict
        and chartDict[compareWithYearBefore_key]
    ):
        descending = True
    elif selectedPeriods and selectedPeriods[0] == plName:
        descending = True
    else:
        descending = False
    # 6) Sort by [chosenDimension, xColumn] in ascending or descending order
    #    This simulates "df.set_index([chosenDimension, xColumn])" + "df.sort_index()"
    df_lazy = df_lazy.sort(by=[chosenDimension, xColumn], descending=descending)

    # 7) Sort periodOrder the same way you did in Pandas
    #    (Note that in the original code, we only reversed periodOrder if descending)

    periodOrder.sort(reverse=descending)

    # 8) Slice the last N items from periodOrder
    periodOrder = periodOrder[-maxPeriodsForBarChart:]

    # 9) Return the LAZY frame and the pruned periodOrder list

    return df_lazy, periodOrder


def pivot_cagr_dataframe(
    df_lazy: pl.LazyFrame,
    CXGRName: str,
    xColumn: str,
    chosenDimension: str,
    agg_fn: str = "first",  # or "sum", "mean", etc.
) -> pl.LazyFrame:
    """
    Simulate a pivot in Polars lazy:
      - index = xColumn
      - columns = unique values in chosenDimension
      - values = CXGRName
      - aggregator = agg_fn (default "first")
    """

    # 1) Collect unique values of `chosenDimension` into a Python list
    dimension_values = (
        df_lazy.select(pl.col(chosenDimension).unique())
        .collect()  # materialize to get the list
        .get_column(chosenDimension)
        .to_list()
    )
    check_collect("AAL", "dimension_values", dimension_values)
    # 2) Build a list of aggregator expressions
    #    For each unique dimension value, we filter and apply the aggregator.
    if agg_fn == "sum":
        agg_exprs = [
            pl.col(CXGRName).filter(pl.col(chosenDimension) == dv).sum().alias(str(dv))
            for dv in dimension_values
        ]
    elif agg_fn == "mean":
        agg_exprs = [
            pl.col(CXGRName).filter(pl.col(chosenDimension) == dv).mean().alias(str(dv))
            for dv in dimension_values
        ]
    else:  # default "first"
        agg_exprs = [
            pl.col(CXGRName)
            .filter(pl.col(chosenDimension) == dv)
            .first()
            .alias(str(dv))
            for dv in dimension_values
        ]

    # 3) Perform a group_by on xColumn and aggregate
    df_pivoted_lazy = df_lazy.group_by(xColumn).agg(agg_exprs)

    # Now `df_pivoted_lazy` is in wide form: one row per xColumn, columns for each dimension
    return df_pivoted_lazy


def manage_missing_periods_for_cagr(
    df: pl.LazyFrame, chosenDimension: str, xColumn: str, periodOrder: list[str]
) -> pl.LazyFrame:
    """Handle missing periods for CAGR calculations using Polars.

    The pivot is performed lazily using :func:`pivot_lazy`.
    ``periodOrder`` is used only for debug logging via ``check_collect``.
    """

    # Example external calls: adjust these to your actual code
    namingParams = get_naming_params()  # same as in your Pandas code
    periodsMissing = namingParams["periodsMissing"]  # column name for "periodsMissing"

    columns, schema = get_schema_and_column_names(df)
    # ^ your function that extracts column names, etc.

    # Only do grouping/pivot if 'periodsMissing' is a known column
    if periodsMissing in columns:
        # Group by chosenDimension and xColumn, sum the periodsMissing
        df_agg = df.group_by([chosenDimension, xColumn]).agg(
            pl.col(periodsMissing).sum()
        )

        check_collect("AAAB", "missing periods", periodOrder)

        # Perform the pivot lazily without collecting
        df_pivot = pivot_lazy(
            lf=df_agg,
            index_col=xColumn,
            pivot_col=chosenDimension,
            value_col=periodsMissing,
            agg_func="first",
        )

        return df_pivot

    else:
        # Return an empty Polars DataFrame if the column is missing
        return pl.LazyFrame()


def load_cagr_data_into_chartdict(
    dfCAGR, dfPeriodsMissing, chosenDimension, CXGRName, chartDict
):
    namingParams = get_naming_params()
    CXGRMetric = namingParams["CXGRMetricName"]
    CXGRData = namingParams["CXGRData"]
    CXGRTotal = namingParams["CXGRTotal"]
    totalName = namingParams["totalName"]
    periodsMissing = namingParams["periodsMissing"]
    chartDict[CXGRMetric] = CXGRName
    chartDict[periodsMissing] = dfPeriodsMissing
    if chosenDimension == totalName:
        chartDict[CXGRTotal] = dfCAGR
    else:
        chartDict[CXGRData] = dfCAGR
    return chartDict


def calculate_cagr(dfCopy, chosenDimension, xColumn, metric, paramDict, chartDict):
    """
    adds CAGR calculation
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    CAGRArray = configParams[namingParams["CAGRArray"]]
    showCAGRKey = namingParams["showCAGR"]
    selectedPeriods = namingParams["selectedPeriods"]
    totalName = namingParams["totalName"]
    periodName = namingParams["periodName"]
    CXGRMetric = namingParams["CXGRMetricName"]
    periodsMissing = namingParams["periodsMissing"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    selectedPeriods = chartDict[selectedPeriods]
    frameArray = []
    stop = False
    showCAGR = check_if_must_not_calculate_cagr(chartDict, paramDict)
    CAGRArray = add_count_metrics_to_cagr_array(CAGRArray, chartDict)
    if metric in CAGRArray and is_valid_lazyframe(dfCopy) and showCAGR:
        df = duplicate_dataframe(dfCopy)
        paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = (
            get_period_length(df, paramDict, False)
        )
        CXGRName = set_CAGX_names(periodLengthInMonths, chartDict, paramDict)
        df, periodOrder = sort_index_and_periods_for_cagr(
            df, chosenDimension, xColumn, metric, chartDict, paramDict
        )
        count = 1
        if len(selectedPeriods) > 1:
            dfCXGRTotal = pl.LazyFrame()
            df = compute_cagr_rate(
                df, CXGRName, chosenDimension, periodOrder, count, metric
            )
            if chosenDimension != totalName:
                dfCAGR = duplicate_dataframe(df)
                dfCXGRTotal = duplicate_dataframe(df)
                dfCXGRTotal = calculate_total_cagr(
                    dfCXGRTotal, metric, CXGRName, periodOrder, count
                )
                for element in range(100):
                    if not stop and is_valid_lazyframe(dfCAGR):
                        count = count + 1
                        foundArray = extract_found_cagr_rates(
                            dfCAGR, CXGRName, chosenDimension
                        )
                        dfNotFound, dfFound = filter_out_found_and_not_found_dataframe(
                            dfCAGR, CXGRName, foundArray, frameArray, chosenDimension
                        )
                        numberOfPeriods = (
                            dfNotFound.select(
                                pl.col(periodName).n_unique()
                            )  # expression for distinct count
                            .collect()  # materialize
                            .item()  # get the integer
                        )
                        check_collect("AAH", "numberOfPeriods", numberOfPeriods)
                        numberOfItems = (
                            dfNotFound.select(pl.col(chosenDimension).n_unique())
                            .collect()
                            .item()
                        )
                        check_collect("AAI", "numberOfItems", numberOfItems)
                        if (
                            is_valid_lazyframe(dfNotFound)
                            and numberOfPeriods > 1
                            and numberOfItems < get_row_count(dfNotFound)
                        ):
                            cxgrPeriods = len(periodOrder) - count
                            dfNotFound = compute_cagr_rate(
                                dfNotFound,
                                CXGRName,
                                chosenDimension,
                                periodOrder,
                                count,
                                metric,
                            )
                            dfCAGR = duplicate_dataframe(dfNotFound)
                            frameArray, dfFound, dfNotFound = (
                                append_dfFound_and_dfNotFound_to_array(
                                    dfFound, dfNotFound, element, frameArray
                                )
                            )
                        else:
                            stop = True
                            break
            else:
                pass
        df = concatenate_dfFound_and_dfNotFound_dataframes(df, frameArray)
        df = clean_cagr_column(df, CXGRName, periodOrder)
        dfCAGR = pivot_cagr_dataframe(df, CXGRName, xColumn, chosenDimension)
        dfPeriodsMissing = manage_missing_periods_for_cagr(
            df, chosenDimension, xColumn, periodOrder
        )
        chartDict = load_cagr_data_into_chartdict(
            dfCAGR, dfPeriodsMissing, chosenDimension, CXGRName, chartDict
        )
        if is_valid_lazyframe(dfCXGRTotal):
            dfCXGRTotal = pivot_cagr_dataframe(
                dfCXGRTotal, CXGRName, xColumn, totalName
            )
            chartDict = load_cagr_data_into_chartdict(
                dfCXGRTotal, dfPeriodsMissing, totalName, CXGRName, chartDict
            )
    else:
        chartDict[CXGRMetric] = notMetConditionValue
        chartDict[showCAGRKey] = False
    return chartDict, paramDict


def compute_cagr_rate(
    df_lazy: pl.LazyFrame,
    CXGRName: str,
    chosenDimension: str,
    periodOrder: list,
    count: int,
    metric_col: str,
) -> pl.LazyFrame:
    """
    Compute CAGR per ``chosenDimension`` using Polars window expressions
    (no pandas ``.apply``). Returns the LazyFrame with ``CXGRName`` appended.

    - ``periodOrder`` and ``count`` determine the shift distance.
    - ``metric_col`` is the numeric column used for CAGR.
    """

    namingParams = get_naming_params()
    periodsMissing = namingParams["periodsMissing"]

    # 1) Calculate how many periods to shift for the CAGR
    cxgrPeriods = len(periodOrder) - count

    # 2) Drop 'periodsMissing' column if it exists
    # df_lazy = df_lazy.drop(periodsMissing)  # safe if column exists; else Polars may raise an error

    # 3) Construct the window expression that mimics
    #    ((pct_change + 1) ** (1 / cxgrPeriods)) - 1 per group.
    #    NOTE: pct_change returns nulls for the first cxgrPeriods rows per group.
    cagr_expr = (
        (
            (pl.col(metric_col).pct_change(n=cxgrPeriods).over(chosenDimension) + 1)
            ** (1 / cxgrPeriods)
        )
        - 1
    ).alias(CXGRName)

    # 4) Add the new column to the DataFrame
    df_lazy = df_lazy.with_columns(cagr_expr)

    return df_lazy


def clean_cagr_column(
    df: pl.LazyFrame, CXGRName: str, periodOrder: list
) -> pl.LazyFrame:
    """
    1) Fill nulls with 0
    2) Multiply by 100
    3) Round to 1 decimal
    4) If not the last period OR value == 0.0 => set null
    5) Filter out null rows
    6) Cast final values to string
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]

    # Step 1-3: fill & round
    df = df.with_columns((pl.col(CXGRName).fill_null(0) * 100).round(1).alias(CXGRName))

    # Step 4: keep only the last period's non-zero values, else null
    last_period = periodOrder[-1]
    df = df.with_columns(
        pl.when(
            (pl.col(periodName).cast(pl.Utf8).str.strip_chars() == last_period)
            & (pl.col(CXGRName) != 0)
        )
        .then(pl.col(CXGRName))
        .otherwise(None)
        .alias(CXGRName)
    )

    # Step 5: filter out null
    df = df.filter(pl.col(CXGRName).is_not_null())

    # Step 6: cast to string for final display if desired
    df = df.with_columns(pl.col(CXGRName).cast(pl.Utf8).alias(CXGRName))

    return df


def extract_found_cagr_rates(
    df_lazy: pl.LazyFrame, CXGRName: str, chosenDimension: str
) -> list:
    """Return unique values from ``chosenDimension`` using Polars lazy steps.

    Steps:
      1) Duplicate the DataFrame if needed.
      2) Filter rows where ``CXGRName`` is not null using ``filter``.
      3) Select unique values of ``chosenDimension`` with ``unique``.
      4) ``collect`` the result and convert the column to a list.
    """

    # (Optional) If you truly need a second lazy pipeline to transform separately:
    # df_lazy = df_lazy.clone()

    # 1) Filter out rows where CXGRName is null
    df_filtered = df_lazy.filter(pl.col(CXGRName).is_not_null())

    # 2) Collect the unique values of chosenDimension into a Python list
    foundArray = (
        df_filtered.select(pl.col(chosenDimension).unique())
        .collect()  # materialize
        .get_column(chosenDimension)  # extract Series
        .to_list()  # convert to Python list
    )
    check_collect("AAG", "foundArray", foundArray)
    return foundArray


def reindex_polars(
    lf: pl.LazyFrame, xColumn: str, new_order_list: list
) -> pl.LazyFrame:
    """
    Polars-lazy "reindex" equivalent:
      1) build a small DataFrame with the desired order
      2) join the main lazy frame on xColumn (how="left")
      3) sort by that order's row count
      4) drop the helper column
    """
    order_df = (
        pl.DataFrame({xColumn: new_order_list})
        .with_row_index(name="temp_order", offset=0)
        .lazy()
    )

    return (
        order_df.join(lf, on=xColumn, how="left")  # keep the order from order_df
        .sort("temp_order")
        .drop("temp_order")
    )


def pivot_lazy(
    lf: pl.LazyFrame | pl.DataFrame,
    index_col: str,
    pivot_col: str,
    value_col: str,
    agg_func: str = "sum",
) -> pl.LazyFrame:
    """Pivot ``lf`` on ``pivot_col`` using Polars.

    Older versions of Polars do not expose ``LazyFrame.pivot``. In that case the
    input is collected to a ``DataFrame`` and pivoted eagerly before returning a
    lazy frame again.
    """

    lf = ensure_lazyframe(lf)

    def _pivot_df(df: pl.DataFrame, agg_key: str) -> pl.DataFrame:
        agg_kwargs = {agg_key: agg_func}
        attempts = [
            (
                (),
                {
                    "columns": pivot_col,
                    "index": index_col,
                    "values": value_col,
                    **agg_kwargs,
                },
            ),
            (
                (),
                {
                    "on": pivot_col,
                    "index": index_col,
                    "values": value_col,
                    **agg_kwargs,
                },
            ),
            ((pivot_col,), {"index": index_col, "values": value_col, **agg_kwargs}),
            ((pivot_col, index_col, value_col, agg_func), {}),
            ((pivot_col, index_col, value_col), agg_kwargs),
        ]
        for args, kwargs in attempts:
            try:
                return df.pivot(*args, **kwargs)
            except TypeError:
                continue
        return df.pivot(pivot_col, index_col, value_col, agg_func)

    df = lf.collect()
    try:
        df_pivot = _pivot_df(df, "aggregate_function")
    except TypeError:
        df_pivot = _pivot_df(df, "aggregate_fn")
    df_pivot = df_pivot.lazy()

    columns, schema = get_schema_and_column_names(df_pivot)
    rename_map = {c: f"{value_col}_{c}" for c in columns if c != index_col}
    return df_pivot.rename(rename_map)


def clean_column_labels_after_flatten(
    df: pl.LazyFrame, metricsToPlot: list[str]
) -> tuple[pl.LazyFrame, list]:
    """Remove metric prefixes from column labels produced by Polars pivots."""
    # Example: rename columns that start with '<metric>_' for a single metric
    columns, schema = get_schema_and_column_names(df)
    # Just do a small rename if needed
    rename_map = {}
    for c in columns:
        # e.g. remove "<metric>_" if single metric
        for m in metricsToPlot:
            prefix = f"{m}_"
            if c.startswith(prefix) and len(metricsToPlot) == 1:
                new_c = c.replace(prefix, "")
                rename_map[c] = new_c

    df = df.rename(rename_map) if rename_map else df
    return df, columns


def clean_column_labels_after_flatten_polars(
    df: pl.DataFrame | pl.LazyFrame, metricsToPlot
):
    """Remove metric prefixes from column names when flattened."""

    columns, _ = get_schema_and_column_names(df)
    newCols = []
    for idx, column in enumerate(columns):
        new_col = column
        if idx != 0:
            for metric in metricsToPlot:
                metric_prefix = f"{metric}_"
                if new_col.startswith(metric_prefix):
                    new_col = new_col[len(metric_prefix) :]
                else:
                    new_col = new_col.replace(metric, "").lstrip("_")
        newCols.append(new_col)

    rename_map = {old: new for old, new in zip(columns, newCols) if old != new}
    df = df.rename(rename_map) if rename_map else df
    return df, newCols


# Backwards compatibility alias
clean_column_labels_after_flatten_df = clean_column_labels_after_flatten_polars


def check_if_value_columns_in_df(df, metricArray):
    columns, schema = get_schema_and_column_names(df)
    valueCols = []
    for element in metricArray:
        if element in columns:
            valueCols.append(element)
    return valueCols


def drop_indirect_costs_rows(
    df: pl.DataFrame | pl.LazyFrame, valueCols: list[str]
) -> pl.LazyFrame:
    """Remove rows where non-indirect metrics sum to ``<= 1``."""

    namingParams = get_naming_params()
    indirectCostsName = namingParams["indirectCostsName"]
    workColumn = namingParams["workColumn"]
    netMarginName = namingParams["netMarginName"]
    indirectColsArray = [indirectCostsName, netMarginName]

    valueColsWithoutIndirect = [
        col for col in valueCols if col not in indirectColsArray
    ]

    lf = ensure_lazyframe(df)

    if indirectCostsName not in valueCols:
        return lf

    lf = lf.with_columns(
        pl.sum_horizontal([pl.col(c) for c in valueColsWithoutIndirect]).alias(
            workColumn
        )
    ).filter(pl.col(workColumn) > 1)

    lf = drop_columns(lf, [workColumn])
    return lf


def get_unique_dimensions(df: pl.DataFrame | pl.LazyFrame, column: str) -> int:
    """Return the number of unique values for ``column`` without eager collect."""

    lf = ensure_lazyframe(df)
    number_of_unique_dimension = lf.select(pl.col(column).n_unique()).collect(
        engine="streaming"
    )[0, 0]
    check_collect("AAN", "numberOfUniqueDimension", number_of_unique_dimension)
    return int(number_of_unique_dimension)


def rank_dataframe(df: pl.DataFrame, column: str):
    """
    Ranks the dataframe based on the sum of a monetary column, grouped by a specified column.

    Args:
        df (pl.DataFrame): The input dataframe.
        column (str): The column to group by.

    Returns:
        Tuple[pl.DataFrame, bool]: The ranked dataframe with a rank column and a boolean flag.
    """
    namingParams = get_naming_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    rank = namingParams["rankName"]

    dfRank = duplicate_dataframe(
        df
    )  # Ensure no modifications to the original dataframe

    dfRank = (
        dfRank.lazy()
        .group_by(column)
        .agg([pl.col(monetaryName).sum().alias(monetaryName)])
        .with_columns(
            pl.col(monetaryName).rank(method="average", descending=True).alias(rank)
        )
        .drop(monetaryName)
        .sort(by=[rank, column], descending=[False, False])
    )

    sortByGlobalItems = True  # This can be removed if not needed

    return dfRank, sortByGlobalItems


def initialize_rank_boolean(df_lazy: pl.LazyFrame) -> pl.LazyFrame:
    """Initialize the ``rank_boolean`` column with ``not_met_condition_value``."""
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    rankBoolean = namingParams["rankBoolean"]
    updated_df = df_lazy.with_columns(pl.lit(notMetConditionValue).alias(rankBoolean))
    return updated_df


def scenario_top_condition(
    df_lazy: pl.LazyFrame,
    number_of_top: int,
) -> pl.LazyFrame:
    """
    When rank <= number_of_top, set rank_boolean = met_condition_value,
    otherwise set it to not_met_condition_value.
    """
    # First pass: assign met_condition_value if rank <= number_of_top
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    rankBoolean = namingParams["rankBoolean"]
    rank = namingParams["rankName"]
    updated_df = df_lazy.with_columns(
        pl.when(pl.col(rank) <= number_of_top)
        .then(metConditionValue)
        .otherwise(pl.col(rankBoolean))  # leave existing value if condition not met
        .alias(rankBoolean)
    )

    # Second pass: assign not_met_condition_value if not already met_condition_value
    updated_df = updated_df.with_columns(
        pl.when(pl.col(rankBoolean) != metConditionValue)
        .then(notMetConditionValue)
        .otherwise(pl.col(rankBoolean))
        .alias(rankBoolean)
    )
    return updated_df


def scenario_global_items(
    df_lazy: pl.LazyFrame,
    column: str,
    paramDict: dict,
) -> pl.LazyFrame:
    """
    If column is in paramDict[globalUniqueItemsArrayKey],
    set rank_boolean = met_condition_value,
    else set it to not_met_condition_value.
    """
    # First pass: set to met_condition_value if the column is in the global items array
    namingParams = get_naming_params()
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    rankBoolean = namingParams["rankBoolean"]
    rank = namingParams["rankName"]

    updated_df = df_lazy.with_columns(
        pl.when(pl.col(column).is_in(paramDict[globalUniqueItemsArrayKey]))
        .then(metConditionValue)
        .otherwise(pl.col(rankBoolean))  # leave existing value if condition not met
        .alias(rankBoolean)
    )

    # Second pass: set to not_met_condition_value if not already met_condition_value
    updated_df = updated_df.with_columns(
        pl.when(pl.col(rankBoolean) != metConditionValue)
        .then(notMetConditionValue)
        .otherwise(pl.col(rankBoolean))
        .alias(rankBoolean)
    )

    return updated_df


def scenario_filter_top(
    df_lazy: pl.LazyFrame,
    number_of_top: int,
) -> pl.LazyFrame:
    """
    Filter rows where rank_col <= number_of_top,
    then set rank_boolean = met_condition_value.
    """
    namingParams = get_naming_params()
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    rankBoolean = namingParams["rankBoolean"]
    rank = namingParams["rankName"]

    filtered_df = df_lazy.filter(pl.col(rank) <= number_of_top)
    updated_df = filtered_df.with_columns(pl.lit(metConditionValue).alias(rankBoolean))
    return updated_df


def get_top_unique_items(df: pl.DataFrame, column: str, number_of_top: int) -> list:
    """
    Returns the top N unique items in `df[column]`.
    """
    # Create a lazy frame
    # Select the column and get unique values
    unique_lazy = df.select(pl.col(column)).unique(maintain_order=True)
    # Collect as a DataFrame
    unique_df = unique_lazy.collect()
    check_collect("AAO", "unique_df", unique_df[:5])
    # Convert to list and slice
    unique_items = unique_df.get_column(column).to_list()[:number_of_top]
    return unique_items


def process_df_rank(df, column, chartDict, paramDict, key):
    namingParams = get_naming_params()
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    aggregateOtherItems = chartDict[key][namingParams["aggregateOtherItems"]]
    numberOfTop = chartDict[key][namingParams["numberOfTop"]]
    dfRank, sortByGlobalItems = rank_dataframe(df, column)
    if (
        fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]
    ) or (showTopForEachItem in chartDict and chartDict[showTopForEachItem]):
        sortByGlobalItems = False
    dfRank = initialize_rank_boolean(dfRank)
    if (
        key == "W"
        and chosenChart in [marimekkoChart, stackedBarChart]
        and plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
    ):
        dfRank = scenario_top_condition(dfRank, numberOfTop)
    elif (
        globalUniqueItemsArrayKey in paramDict
        and paramDict[globalUniqueItemsArrayKey]
        and sortByGlobalItems
    ):
        dfRank = scenario_global_items(dfRank, column, paramDict)
    elif aggregateOtherItems:
        dfRank = scenario_top_condition(dfRank, numberOfTop)
    else:
        dfRank = scenario_filter_top(dfRank, numberOfTop)
    uniqueItems = get_top_unique_items(dfRank, column, numberOfTop)
    return dfRank, uniqueItems


def tag_small_label_gaps(
    dfCopy, element: str, column: str, chartDict: dict, minGap: float, filterPeriod: str
) -> pl.LazyFrame:
    """Tag labels that are too close to each other using Polars expressions."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]

    lf = ensure_lazyframe(dfCopy).select([column, element, periodName])
    lf = lf.filter(pl.col(periodName) == filterPeriod).sort(element)
    lf = (
        lf.with_columns(
            (pl.col(element) - pl.col(element).shift(-1)).abs().alias(workColumn)
        )
        .with_columns(
            pl.when(pl.col(workColumn) <= minGap)
            .then(0)
            .otherwise(1)
            .alias(workColumnTwo)
        )
        .drop([workColumn, element])
    )

    return lf


def add_yearly_average(
    df: pl.DataFrame | pl.LazyFrame, y_array: list[str], chartDict: dict
) -> pl.LazyFrame:
    """Return ``df`` with an appended row of yearly averages as a ``LazyFrame``."""
    namingParams = get_naming_params()
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    averageName = namingParams["averageName"]
    dateName = namingParams["dateName"]
    fcName = namingParams["fcName"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]

    lf = ensure_lazyframe(duplicate_dataframe(df))

    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
        and fcName in y_array
        and plName in y_array
    ):
        lf = lf.with_columns((pl.col(acName) + pl.col(fcName)).alias(fcName))

    avg_row = (
        lf.select([pl.col(col).mean().alias(col) for col in y_array])
        .with_columns(pl.lit(averageName).alias(dateName))
        .select([dateName] + y_array)
    )

    df_lf = ensure_lazyframe(df).with_columns(
        [pl.col(col).cast(pl.Float64) for col in y_array]
    )

    empty_row = pl.LazyFrame({col: [None] for col in [dateName] + y_array})

    result_lf = pl.concat([df_lf, avg_row, empty_row])

    return result_lf


def rank_others_as_last(
    df: pl.DataFrame | pl.LazyFrame, aggregate_other_items_name: str, rank_value: int
) -> pl.LazyFrame:
    """Rank rows containing ``aggregate_other_items_name`` at the end.

    The function always returns a :class:`polars.LazyFrame` regardless of the
    input type and never evaluates the lazy computation.
    """

    namingParams = get_naming_params()
    rank = namingParams["rankName"]

    lf = ensure_lazyframe(df)

    lf_cols, _ = get_schema_and_column_names(lf)
    index_col = lf_cols[0]
    label = pl.col(index_col).cast(pl.Utf8).str.to_lowercase()
    is_other_label = (
        label.eq("other")
        | label.eq("other (aggregated)")
        | label.str.starts_with("other ")
    )
    if aggregate_other_items_name:
        is_other_label = is_other_label | label.str.contains(
            aggregate_other_items_name.lower(), literal=True
        )
    lf = lf.with_row_index(rank).with_columns(
        pl.when(is_other_label).then(rank_value).otherwise(pl.col(rank) + 1).alias(rank)
    )
    lf = lf.sort(rank).drop(rank)

    return lf


def get_month_name(df):
    """
    change month numbers to months three letter abbreviations
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    dateName = namingParams["dateName"]
    monthDict = configParams[namingParams["monthDict"]]
    monthDict = {int(key): value for key, value in monthDict.items()}
    df = df.with_columns(
        pl.col(dateName)
        .dt.month()
        .replace_strict(monthDict, return_dtype=pl.Utf8)
        .alias(dateName)
    )
    return df


def order_dataframe_by_month(
    df: pl.DataFrame | pl.LazyFrame,
    paramDict: dict,
    indexSort: bool,
    yArray: list[str],
) -> pl.DataFrame | pl.LazyFrame:
    """Reorder the rows of ``df`` according to calendar months.

    The returned object preserves the input type (``DataFrame`` or ``LazyFrame``).
    When the most recent month is not December the ordering is shifted so the
    output always covers the latest 12 months in chronological order. A blank
    row and an average row are appended when ``indexSort`` is ``False``.
    """

    namingParams = get_naming_params()
    configParams = get_config_params()

    dateName = namingParams["dateName"]
    averageName = namingParams["averageName"]
    workColumn = namingParams["workColumn"]

    monthDict = configParams[namingParams["monthDictInt"]]

    paramDict, mostRecentDate, _, _ = get_period_length(df, paramDict, False)

    mostRecentMonth = mostRecentDate.month
    monthArray = list(monthDict.values())

    if mostRecentMonth == 12:
        reorderedArray = monthArray.copy()
    else:
        thisYearArray = monthArray[:mostRecentMonth]
        lastYearArray = monthArray[mostRecentMonth:]
        reorderedArray = lastYearArray + thisYearArray

    is_lazy = isinstance(df, pl.LazyFrame)
    lf = df if is_lazy else df.lazy()

    lookup = pl.DataFrame(
        {dateName: reorderedArray, "_sort": range(len(reorderedArray))}
    ).lazy()

    if indexSort:
        lf = lf.join(lookup, on=dateName, how="inner").sort("_sort").drop("_sort")
        lf_cols, _ = get_schema_and_column_names(lf)
        value_cols = [c for c in lf_cols if c != dateName]
        lf = (
            lf.with_columns(
                pl.all_horizontal([pl.col(c).is_not_null() for c in value_cols]).alias(
                    "__keep__"
                )
            )
            .filter(pl.col("__keep__"))
            .drop("__keep__")
        )
    else:
        reorderedArray += ["", averageName]
        lookup = pl.DataFrame(
            {dateName: reorderedArray, "_sort": range(len(reorderedArray))}
        ).lazy()
        lf = lf.join(lookup, on=dateName, how="full")
        right_date_name = f"{dateName}_right"
        lf_columns, _ = get_schema_and_column_names(lf)
        if right_date_name in lf_columns:
            lf = lf.with_columns(
                pl.coalesce([pl.col(dateName), pl.col(right_date_name)]).alias(dateName)
            ).drop(right_date_name)
        lf = lf.with_columns(pl.col("_sort").fill_null(len(reorderedArray)))
        cond = pl.all_horizontal([pl.col(col).is_null() for col in yArray]) & (
            pl.col(dateName).fill_null("") != ""
        )
        lf = (
            lf.sort("_sort")
            .with_columns(pl.when(cond).then(1).otherwise(None).alias(workColumn))
            .filter(pl.col(workColumn).is_null())
            .drop(["_sort", workColumn])
        )

    return lf if is_lazy else lf.collect()


def identify_close_value_labels(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    metric: str,
    column: str,
    paramDict: dict,
    chartDict: dict,
) -> pl.LazyFrame:
    """Tag values that are too close to one another using Polars lazy APIs."""

    namingParams = get_naming_params()
    labelName = namingParams["labelName"]
    workColumnTwo = namingParams["workColumnTwo"]
    periodName = namingParams["periodName"]
    periodChoice = namingParams["periodChoice"]
    weekName = namingParams["weekName"]
    quarterName = namingParams["quarterName"]
    selectedPeriods = namingParams["selectedPeriods"]

    periodOrder = chartDict[selectedPeriods]

    lf = ensure_lazyframe(duplicate_dataframe(dfCopy)).with_columns(
        pl.col(metric).alias(labelName)
    )

    max_value = ensure_lazyframe(dfCopy).select(pl.col(metric).max()).collect().item()
    min_gap = max_value / 20

    if periodChoice in chartDict and chartDict[periodChoice] in [weekName, quarterName]:
        try:
            lf = lf.with_columns(
                pl.col(periodName).str.to_uppercase().alias(periodName)
            )
        except Exception as e:  # noqa: BLE001  # nosec B110
            logging.exception(e)
            notifier.error("Something went wrong while uppercasing periods.")

    lf, periodOrder[0] = check_if_periods_in_columns(lf, periodOrder[0])
    dfPeriodZero = tag_small_label_gaps(
        lf, metric, column, chartDict, min_gap, periodOrder[0]
    )

    lf, periodOrder[1] = check_if_periods_in_columns(lf, periodOrder[1])
    dfPeriodOne = tag_small_label_gaps(
        lf, metric, column, chartDict, min_gap, periodOrder[1]
    )

    dfGaps = pl.concat([dfPeriodZero, dfPeriodOne])

    lf = (
        lf.join(dfGaps, on=[column, periodName], how="left")
        .sort([column, periodName])
        .with_columns(
            pl.when(pl.col(workColumnTwo) == 0)
            .then(None)
            .otherwise(pl.col(labelName))
            .alias(labelName)
        )
    )

    return lf


def compute_average_metrics(
    df: pl.LazyFrame, chartDict: dict, countMetricsAvgDict: str, divisor_metric: str
) -> pl.LazyFrame:
    """
    For each mapping ``new_col -> sum_col`` in ``chartDict[countMetricsAvgDict]``,
    add ``new_col`` via ``with_columns((col(sum_col) / col(divisor_metric)).alias(new_col))``.
    """
    # Nothing to do if countMetricsAvgDict is not in chartDict or is empty
    if countMetricsAvgDict not in chartDict or len(chartDict[countMetricsAvgDict]) == 0:
        return df

    df_out = df
    for new_col, sum_col in chartDict[countMetricsAvgDict].items():
        df_out = df_out.with_columns(
            (pl.col(sum_col) / pl.col(divisor_metric)).alias(new_col)
        )

    return df_out


def get_unique_counts(df, group_byCols, chartDict, countMetricsSumDict):
    """
    Get unique counts for a given column and return the result as a lazy dataframe.
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    dfCounts = pl.LazyFrame()  # Default empty dataframe
    if countMetricsSumDict in chartDict and len(chartDict[countMetricsSumDict]) > 0:
        keyList = [*chartDict[countMetricsSumDict]]
        colKey = keyList[0]
        column = chartDict[countMetricsSumDict][colKey]

        # Lazy operation to calculate unique counts

        dfCounts = df.group_by(group_byCols).agg(
            pl.col(column).n_unique().alias(colKey)
        )
        dfCounts = dfCounts.sort(
            periodName
        )  # Assuming 'periodName' is the sorting criterion
    return dfCounts


def adjust_group_by_columns(
    chosenChart: str, group_byCols: list, yColumn: str, timeColumn: str, dateName: str
) -> list:
    """Adjust the columns used for group_by based on chart type and time column."""
    namingParams = get_naming_params()
    trendComparisonChart = namingParams["trendComparisonChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    timelineChart = namingParams["timelineChart"]
    periodName = namingParams["periodName"]
    if timeColumn == dateName:
        if chosenChart in [
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
        ]:
            group_byCols = [periodName, yColumn, timeColumn]
        elif chosenChart in [timelineChart]:
            group_byCols = [yColumn, timeColumn]
        else:
            group_byCols = [yColumn, timeColumn]
    return group_byCols


def get_number_of_uniques(dfCopy, yColumn, timeColumn, chartDict):
    namingParams = get_naming_params()
    countMetricsSumDict = namingParams["countMetricsSumDict"]
    countMetricsSumArray = namingParams["countMetricsSumArray"]
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    timelineChart = namingParams["timelineChart"]
    areaChart = namingParams["areaChart"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]

    df = duplicate_dataframe(
        dfCopy
    )  # Assuming this function makes the dataframe copy correctly
    group_byCols = [periodName, yColumn]

    # Adjust the group_byCols based on the timeColumn and chart
    group_byCols = adjust_group_by_columns(
        chosenChart, group_byCols, yColumn, timeColumn, dateName
    )

    dfCounts = get_unique_counts(df, group_byCols, chartDict, countMetricsSumDict)
    return dfCounts, chartDict


def fill_other_items_for_metric(
    df: pl.LazyFrame,
    dfCounts: pl.LazyFrame,
    metric: str,
    yColumn: str,
    aggregateOtherItemsName: str,
    groupCols: list,
) -> pl.LazyFrame:
    """
    Given df and dfCounts (both lazy), compute the total for `metric` from dfCounts
    grouped by groupCols, and the sum of `metric` from df (excluding the 'Other' row),
    then fill the 'Other' row with (total - sum_of_non_other).
    """

    # Sum of counts for every group
    total_df = dfCounts.group_by(groupCols).agg(
        pl.col(metric).sum().alias("total_metric")
    )

    # Sum of metric for all non-"Other" rows in df
    sum_non_others_df = (
        df.filter(pl.col(yColumn) != aggregateOtherItemsName)
        .group_by(groupCols)
        .agg(pl.col(metric).sum().alias("joined_metric"))
    )

    # Join those aggregates back onto df so we can compute (total - joined)
    df_out = (
        df
        # Bring in the sum of non-others
        .join(sum_non_others_df, on=groupCols, how="left")
        # Bring in the total from dfCounts
        .join(total_df, on=groupCols, how="left")
        # Conditionally fill the "Other" row with (total - joined), else keep original metric
        .with_columns(
            pl.when(pl.col(yColumn) == aggregateOtherItemsName)
            .then(pl.col("total_metric") - pl.col("joined_metric"))
            .otherwise(pl.col(metric))
            .alias(metric)
        )
        # Clean up any possible nulls if needed, or do fill_null(0) – depends on your use case
        # .with_column(pl.col(metric).fill_null(0))
        .drop(["joined_metric", "total_metric"])  # remove helper columns
    )
    return df_out


def join_unique_metric_to_df(
    df: pl.LazyFrame,  # already Lazy
    dfCounts: pl.LazyFrame,  # assume also Lazy
    yColumn: str,
    timeColumn: str,
    aggregateOtherItemsName: str,
    chartDict: dict,
) -> pl.LazyFrame:
    """Join metrics lazily using Polars.

    This relies on ``get_naming_params()`` to obtain column names and mappings.
    """

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    totalName = namingParams["totalName"]
    countMetricsAvgDict = namingParams["countMetricsAvgDict"]
    countMetricsSumDict = namingParams["countMetricsSumDict"]

    # If dfCounts is None or truly empty, just return df
    # (We cannot lazily check the number of rows without collecting,
    #  so we skip that or do a "dfCounts is not None" check.)
    if dfCounts is None:
        return df

    # If there are no sum metrics to process, just return df
    if countMetricsSumDict not in chartDict or len(chartDict[countMetricsSumDict]) == 0:
        return df

    # Figure out which columns exist
    df_columns, _ = get_schema_and_column_names(df)
    group_byCols = [periodName, yColumn]  # default

    # If timeColumn == dateName, adapt group_byCols
    if timeColumn == dateName:
        if periodName in df_columns:
            group_byCols = [periodName, yColumn, timeColumn]
        else:
            group_byCols = [yColumn, timeColumn]

    # Remove duplicates in case periodName == yColumn or similar
    group_byCols = list(set(group_byCols))

    # 1) Join df and dfCounts on group_byCols so we have the columns from dfCounts
    #    (In your original code, you did a separate join per-metric, but we can
    #     do a single join once, because Polars can carry all columns.)
    df_joined = df.join(dfCounts, on=group_byCols, how="left")

    # 2) For each SUM metric, fill the "Other" row with (total - sum_of_non_other).
    #    Only do that if yColumn != totalName, matching your original condition.
    df_out = df_joined
    if totalName not in [None, ""]:
        # If the grouping column is not the "total" dimension, handle the difference logic
        df_columns_joined, _ = get_schema_and_column_names(df_joined)  # after the join
        if yColumn != totalName:
            for metric in chartDict[countMetricsSumDict]:
                # Only fill other items if metric is actually in dfCounts (joined)
                if metric in df_columns_joined:
                    # fill "Other" row difference
                    # We pass group_byCols that do *not* include yColumn in the grouping
                    # if we want the sum of all categories except "Other."
                    # However, your original code lumps yColumn into the index.
                    # We'll replicate your logic with a separate function:
                    #   fill_other_items_for_metric(…)
                    #
                    # If your original pivot logic expects grouping only by [periodName]
                    # or [dateName], you can adapt. For now, we use the same group_byCols
                    # (minus yColumn check inside the function).
                    df_out = fill_other_items_for_metric(
                        df=df_out,
                        dfCounts=dfCounts,
                        metric=metric,
                        yColumn=yColumn,
                        aggregateOtherItemsName=aggregateOtherItemsName,
                        groupCols=[
                            c for c in group_byCols if c != yColumn
                        ],  # replicate "all except the actual y cat"
                    )

    # 3) If we have average metrics, compute them
    #    df[element] = df[ chartDict[countMetricsAvgDict][element] ] / df[ metric ]
    #    Notice that in your code, you used 'metric' from the sum loop, but effectively
    #    you do a second loop. We'll do a simpler approach: if there's anything
    #    in countMetricsAvgDict, you presumably want to divide by each sum metric.
    #    If your logic always divides by the *same* metric, adapt as needed.
    if (countMetricsAvgDict in chartDict) and len(chartDict[countMetricsAvgDict]) > 0:
        # Your original code suggests we do the division using the last 'metric' in the sum loop
        # or all sum metrics. That part is ambiguous. We'll assume you want it per sum metric.
        # If you truly only want "the sum metric" from the sum loop, pick the relevant one.
        # We'll demonstrate dividing by the *first* sum metric (like your code).
        first_sum_metric = list(chartDict[countMetricsSumDict])[0]
        df_out = compute_average_metrics(
            df_out, chartDict, countMetricsAvgDict, first_sum_metric
        )

    return df_out


def sort_by_column(lazy_df: pl.LazyFrame, column: str) -> pl.LazyFrame:
    """
    Returns a new LazyFrame sorted by `column`.
    """
    return lazy_df.sort(column)


def left_join_on_column(
    lazy_left: pl.LazyFrame, lazy_right: pl.LazyFrame, on: str
) -> pl.LazyFrame:
    """
    Left-joins two Polars LazyFrames on `on`.
    """
    return lazy_left.join(lazy_right, on=on, how="left")


def sort_and_left_join(
    df: pl.LazyFrame,
    df_rank: pl.LazyFrame,
    column: str,
) -> (pl.LazyFrame, list):
    """Sort two frames, then left join them in Polars lazy mode."""

    # 2) Sort df_rank by column
    lazy_df_rank = sort_by_column(df_rank, column)

    # 3) Sort df by column
    lazy_df = sort_by_column(df, column)

    # 4) Left join
    joined = left_join_on_column(lazy_df, lazy_df_rank, column)

    # 5) Optional: mimic reset_index by adding a row count.
    #    If you don't want this, just leave it out.
    # joined = joined.with_row_index(name="index")

    return joined


def process_dataframe_based_on_chart_more_unique_dimensions(
    df,
    column,
    secondColumn,
    timeColumn,
    valueCols,
    uniqueItems,
    aggregateOtherItemsName,
    chartDict,
):
    namingParams = get_naming_params()
    rankBoolean = namingParams["rankBoolean"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    rank = namingParams["rankName"]
    timelineChart = namingParams["timelineChart"]
    dotChart = namingParams["dotChart"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    areaChart = namingParams["areaChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    periodName = namingParams["periodName"]
    acpyName = namingParams["acpyName"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    yAxisDimension = namingParams["yAxisDimension"]
    df = df.with_columns(
        pl.when(pl.col(rankBoolean) != metConditionValue)
        .then(pl.lit(aggregateOtherItemsName))
        .otherwise(pl.col(column))
        .alias(column)
    )
    uniqueItems.append(aggregateOtherItemsName)
    df = drop_columns(df, [rank])
    columns, schema = get_schema_and_column_names(df)
    if chosenChart in [
        trendComparisonChart,
        multitierColumnChart,
        horizontalWaterfallChart,
    ]:
        group_byCols = [column, timeColumn, periodName]
    elif chosenChart in [timelineChart, areaChart]:
        group_byCols = [column, timeColumn]
    elif chosenChart in [trendComparisonByPeriodChart]:
        group_byCols = [column, timeColumn, acpyName]
    elif chosenChart in [
        marimekkoChart,
        vennChart,
        upsetChart,
        stackedBarChart,
        bubbleChart,
    ]:
        group_byCols = []
        for element in [column, timeColumn, secondColumn]:
            if element in columns and element not in group_byCols:
                group_byCols.append(element)
            if (
                chosenChart in [upsetChart, vennChart]
                and plotSmallMultiplesKey in chartDict
                and chartDict[plotSmallMultiplesKey]
            ):
                if yAxisDimension in chartDict:
                    yAxisDimension = chartDict[yAxisDimension]
                    if yAxisDimension in columns and yAxisDimension not in group_byCols:
                        group_byCols.append(yAxisDimension)
    elif chosenChart in [barmekkoChart]:
        group_byCols = [column, timeColumn]
    elif chosenChart not in [
        scatterChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
    ]:
        group_byCols = [column, timeColumn]
    else:
        group_byCols = [column, timeColumn]
    df, group_byCols, valueCols = check_and_group_by_cols(df, group_byCols, valueCols)
    return df, group_byCols, valueCols, uniqueItems


def process_dataframe_based_on_chart_less_unique_dimensions(
    df, column, secondColumn, timeColumn, valueCols, uniqueItems, chartDict
):
    namingParams = get_naming_params()
    timelineChart = namingParams["timelineChart"]
    dotChart = namingParams["dotChart"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    areaChart = namingParams["areaChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    periodName = namingParams["periodName"]
    acpyName = namingParams["acpyName"]
    chosenChart = namingParams["chosenChart"]
    chosenChart = chartDict[chosenChart]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    columns, schema = get_schema_and_column_names(df)
    if chosenChart in [
        trendComparisonChart,
        multitierColumnChart,
        horizontalWaterfallChart,
    ]:
        group_byCols = [column, timeColumn, periodName]
    elif chosenChart in [timelineChart, areaChart]:
        group_byCols = [column, timeColumn]
    elif chosenChart in [trendComparisonByPeriodChart]:
        group_byCols = [column, timeColumn, acpyName]
    elif chosenChart in [marimekkoChart, vennChart, upsetChart, stackedBarChart]:
        if secondColumn not in [nothingFilteredName] and secondColumn != None:
            group_byCols = [column, timeColumn, secondColumn]
            if (
                chosenChart in [upsetChart, vennChart]
                and plotSmallMultiplesKey in chartDict
                and chartDict[plotSmallMultiplesKey]
            ):
                if yAxisDimension in chartDict:
                    yAxisDimension = chartDict[yAxisDimension]
                    if yAxisDimension in columns and yAxisDimension not in group_byCols:
                        group_byCols.append(yAxisDimension)
        else:
            group_byCols = [column, timeColumn]
    elif chosenChart in [barmekkoChart]:
        group_byCols = [column, timeColumn]
    elif chosenChart not in [
        scatterChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
    ]:
        group_byCols = [column, timeColumn]
    else:
        group_byCols = [column, timeColumn]
    df, group_byCols, valueCols = check_and_group_by_cols(df, group_byCols, valueCols)
    df = df.sort(
        by=valueCols[0],  # the column to sort by
        descending=True,  # ascending=False in Pandas => reverse=True in Polars
    )
    uniqueItems = (
        df.select(  # ensure we're in lazy mode
            pl.col(column).unique()
        )  # pick the column and get its unique values
        .collect()[  # materialize the lazy query
            column
        ]  # extract the column from the DataFrame
        .to_list()  # convert to a Python list
    )
    check_collect("AAM", "uniqueItems", uniqueItems)
    return df, group_byCols, valueCols, uniqueItems


def show_only_largest(
    dfCopy, column, secondColumn, timeColumn, valueColsCopy, chartDict, paramDict, key
):
    """
    we just want to keep the top items
    """
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    rank = namingParams["rankName"]
    rankBoolean = namingParams["rankBoolean"]
    numberOfTop = chartDict[key][namingParams["numberOfTop"]]
    aggregateOtherItems = chartDict[key][namingParams["aggregateOtherItems"]]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    nothingThereString = namingParams["nothingThereString"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    WnumberOfTop = namingParams["WnumberOfTop"]
    cleanedUniqueItems = []
    uniqueItems = []
    aggregateOtherItemsName = aggregateOtherItemsNameKey + str(numberOfTop)
    df = duplicate_dataframe(dfCopy)
    valueColsCopy = check_if_value_columns_in_df(df, valueColsCopy)
    valueCols = take_price_out_of_valueCols(valueColsCopy)
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    columns, _ = get_schema_and_column_names(df)
    if monetaryName not in columns and valueCols:
        df = df.with_columns(pl.col(valueCols[0]).alias(monetaryName))
    df = drop_indirect_costs_rows(df, valueCols)
    numberOfUniqueDimension = get_unique_dimensions(df, column)
    if numberOfUniqueDimension > numberOfTop:
        dfRank, uniqueItems = process_df_rank(df, column, chartDict, paramDict, key)
        df = sort_and_left_join(df, dfRank, column)
        if aggregateOtherItems:
            df, group_byCols, valueCols, uniqueItems = (
                process_dataframe_based_on_chart_more_unique_dimensions(
                    df,
                    column,
                    secondColumn,
                    timeColumn,
                    valueCols,
                    uniqueItems,
                    aggregateOtherItemsName,
                    chartDict,
                )
            )
        else:
            df = df.filter(pl.col(rankBoolean) == metConditionValue)
            df = drop_columns(df, [rank, rankBoolean])
    else:
        df, group_byCols, valueCols, uniqueItems = (
            process_dataframe_based_on_chart_less_unique_dimensions(
                df, column, secondColumn, timeColumn, valueCols, uniqueItems, chartDict
            )
        )
    for element in uniqueItems:
        if element != nothingThereString:
            cleanedUniqueItems.append(element)
    return df, cleanedUniqueItems, aggregateOtherItemsName, valueCols


def calculate_year_to_year_change(df, growthMetric, periodOrder):
    df = df.with_columns(pl.lit(None).alias(growthMetric))
    columns, schema = get_schema_and_column_names(df)
    checkedPeriods = []
    for period in periodOrder:
        if period not in columns:
            period = period.lower()
        checkedPeriods.append(period)
    columns, schema = get_schema_and_column_names(df)
    if checkedPeriods[0] in columns and checkedPeriods[1] in columns:
        df = df.with_columns(
            pl.when(pl.col(checkedPeriods[0]) != 0)
            .then(
                (
                    (pl.col(checkedPeriods[1]) - pl.col(checkedPeriods[0]))
                    / pl.col(checkedPeriods[0])
                    * 100
                ).round(0)
            )
            .otherwise(None)
            .alias(growthMetric)
        )
        df = df.with_columns(
            pl.when((pl.col(checkedPeriods[1]) < 0) & (pl.col(checkedPeriods[0]) < 0))
            .then(pl.col(growthMetric) * -1)
            .otherwise(pl.col(growthMetric))
            .alias(growthMetric)
        )
        df = df.with_columns(
            pl.when(pl.col(growthMetric) > 999)
            .then(999)
            .otherwise(pl.col(growthMetric))
            .alias(growthMetric)
        )
    else:
        df = df.with_columns(pl.lit(None).alias(growthMetric))
    return df, checkedPeriods


def insert_unit_and_volume_price_column(df_lazy: pl.LazyFrame) -> pl.LazyFrame:
    """Add pricing columns using Polars' lazy API."""

    # --- 1) Get naming parameters (same as in your code) ---
    naming_params = get_naming_params()
    units_name = naming_params["unitsName"]
    price_per_unit_name = naming_params["pricePerUnitName"]
    volume_name = naming_params["volumeName"]
    price_per_volume_name = naming_params["pricePerVolumeName"]
    amount_name = naming_params["monetaryLocalCurrencyName"]
    discount_name = naming_params["discountName"]
    net_of_discount_name = naming_params["netOfDiscountName"]
    price_per_unit_net_discount_name = naming_params["pricePerUnitNetDiscountName"]
    price_per_volume_net_discount_name = naming_params["pricePerVolumeNetDiscountName"]
    discount_in_percent_name = naming_params["discountInPercentName"]
    margin_in_percent_name = naming_params["marginInPercentName"]
    margin_in_percent_of_net_sales_name = naming_params["marginInPercentOfNetSalesName"]
    margin_name = naming_params["marginName"]

    # --- 2) Get the column names from the LazyFrame schema ---

    columns, schema = get_schema_and_column_names(df_lazy)
    existing_columns = set(schema.keys())  # or df_lazy.columns for Polars >= 0.17.4

    # We'll build a list of Polars expressions applied in a single ``with_columns`` call.
    # Each block implements the conditional logic from the original pandas version.

    new_columns = []

    # ============== BLOCK A ==============
    # When both unit and amount columns exist, use Polars to compute
    # ``pricePerUnitName`` as ``amountName / unitsName`` only when
    # ``unitsName`` is non-zero.
    if {units_name, amount_name}.issubset(existing_columns):
        expr_price_per_unit = (
            pl.when(pl.col(units_name) != 0)
            .then(pl.col(amount_name) / pl.col(units_name))
            .otherwise(0)
            .alias(price_per_unit_name)
            .cast(pl.Float64)
        )
        new_columns.append(expr_price_per_unit)

    # ============== BLOCK B ==============
    # With ``volumeName`` and ``amountName`` present, compute
    # ``pricePerVolumeName`` using ``amountName / volumeName`` when
    # ``volumeName`` is non-zero.
    if {volume_name, amount_name}.issubset(existing_columns):
        expr_price_per_volume = (
            pl.when(pl.col(volume_name) != 0)
            .then(pl.col(amount_name) / pl.col(volume_name))
            .otherwise(0)
            .alias(price_per_volume_name)
            .cast(pl.Float64)
        )
        new_columns.append(expr_price_per_volume)

    # ============== BLOCK C ==============
    # Using Polars expressions, combine ``unitsName``, ``discountName`` and
    # ``netOfDiscountName`` to create ``pricePerUnitNetDiscountName`` as
    # ``netOfDiscountName / unitsName`` when ``unitsName`` is non-zero and
    # compute ``discountInPercentName`` from ``discountName / amountName`` when
    # ``amountName`` is non-zero.
    if {units_name, discount_name, net_of_discount_name}.issubset(existing_columns):
        expr_price_per_unit_net = (
            pl.when(pl.col(units_name) != 0)
            .then(pl.col(net_of_discount_name) / pl.col(units_name))
            .otherwise(0)
            .alias(price_per_unit_net_discount_name)
            .cast(pl.Float64)
        )
        expr_discount_percent = (
            pl.when(pl.col(amount_name) != 0)
            .then(pl.col(discount_name) / pl.col(amount_name))
            .otherwise(0)
            .alias(discount_in_percent_name)
            .cast(pl.Float64)
        )
        new_columns.extend([expr_price_per_unit_net, expr_discount_percent])

    # ============== BLOCK D ==============
    # Using Polars, derive ``pricePerVolumeNetDiscountName`` as
    # ``netOfDiscountName / volumeName`` when ``volumeName`` is non-zero and
    # compute ``discountInPercentName`` from ``discountName / amountName``
    # when ``amountName`` is non-zero.
    if {volume_name, discount_name, net_of_discount_name}.issubset(existing_columns):
        expr_price_per_volume_net = (
            pl.when(pl.col(volume_name) != 0)
            .then(pl.col(net_of_discount_name) / pl.col(volume_name))
            .otherwise(0)
            .alias(price_per_volume_net_discount_name)
            .cast(pl.Float64)
        )
        expr_discount_percent_2 = (
            pl.when(pl.col(amount_name) != 0)
            .then(pl.col(discount_name) / pl.col(amount_name))
            .otherwise(0)
            .alias(discount_in_percent_name)
            .cast(pl.Float64)
        )
        new_columns.extend([expr_price_per_volume_net, expr_discount_percent_2])
        # NOTE: The above will override `discountInPercentName` if it was created in BLOCK C.
        #       If you do NOT want to override, remove or modify this line.

    # ============== BLOCK E ==============
    # If both margin and amount columns exist, generate ``marginInPercentName``
    # using ``marginName / amountName`` when ``amountName`` is non-zero.
    if {margin_name, amount_name}.issubset(existing_columns):
        expr_margin_in_percent = (
            pl.when(pl.col(amount_name) != 0)
            .then(pl.col(margin_name) / pl.col(amount_name))
            .otherwise(0)
            .alias(margin_in_percent_name)
            .cast(pl.Float64)
        )
        new_columns.append(expr_margin_in_percent)

    # ============== BLOCK F ==============
    # With ``marginName`` and ``netOfDiscountName`` available, compute
    # ``marginInPercentOfNetSalesName`` as ``marginName / netOfDiscountName``
    # whenever ``netOfDiscountName`` is non-zero.
    if {margin_name, net_of_discount_name}.issubset(existing_columns):
        expr_margin_in_percent_of_net = (
            pl.when(pl.col(net_of_discount_name) != 0)
            .then(pl.col(margin_name) / pl.col(net_of_discount_name))
            .otherwise(0)
            .alias(margin_in_percent_of_net_sales_name)
            .cast(pl.Float64)
        )
        new_columns.append(expr_margin_in_percent_of_net)

    # --- 3) Apply the transformations if there are any ---
    if new_columns:
        df_lazy = df_lazy.with_columns(new_columns)

    # --- 4) Return the updated lazy frame (nothing is executed yet) ---
    return df_lazy


def get_average_growth_rate(
    df, metricToPlot, paramDict, chartDict, valueCols, overlayMetric
) -> pl.LazyFrame:
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    periodName = namingParams["periodName"]
    totalName = namingParams["totalName"]
    selectedPeriods = namingParams["selectedPeriods"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    toPlotPeriod = chartDict[toPlotPeriod]
    periodOrder = chartDict[selectedPeriods]

    df_lazy = ensure_lazyframe(df)

    if metricToPlot in growthMetricArray:
        gb = df_lazy.group_by(periodName)
        if hasattr(gb, "agg"):
            dfSum = gb.agg([pl.col(col).sum().alias(col) for col in valueCols])
        else:  # compatibility with test wrappers
            dfSum = gb[valueCols].sum()
        dfSum = dfSum.with_columns(pl.lit(totalName).alias(totalName))
        dfSum = get_growth_rate(
            dfSum, totalName, periodOrder, paramDict, chartDict, overlayMetric
        )
        dfSum = dfSum.filter(pl.col(periodName) == toPlotPeriod)
    elif metricToPlot in percentMetricsArray + priceMetricsArray:
        gb = df_lazy.group_by(periodName)
        if hasattr(gb, "agg"):
            dfSum = gb.agg([pl.col(col).sum().alias(col) for col in valueCols])
        else:
            dfSum = gb[valueCols].sum()
        dfSum = dfSum.filter(pl.col(periodName) == toPlotPeriod)
        dfSum = insert_unit_and_volume_price_column(dfSum)
    else:
        dfSum = pl.LazyFrame()

    return ensure_lazyframe(dfSum)


def get_period_values(dfCopy, chosenDimension, salesMetric):
    """Return period pivoted values as a ``LazyFrame``."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]

    df_lazy = ensure_lazyframe(duplicate_dataframe(dfCopy))
    valueCols = [salesMetric]
    valueCols = check_value_column_exist(df_lazy, valueCols)
    if not valueCols:
        return pl.LazyFrame()

    unique_dims = None
    if logger.isEnabledFor(logging.DEBUG):
        unique_dims = (
            df_lazy.select(pl.col(chosenDimension).unique())
            .collect(engine="streaming")
            .get_column(chosenDimension)
            .to_list()
        )
    check_collect("APV", "unique_dims", unique_dims)

    grouped = df_lazy.group_by([chosenDimension, periodName]).agg(
        pl.col(salesMetric).sum().alias(salesMetric)
    )
    df_lazy = pivot_lazy(
        lf=grouped,
        index_col=chosenDimension,
        pivot_col=periodName,
        value_col=salesMetric,
        agg_func="first",
    )
    df_lazy = flatten_cols_polars(df_lazy, "")
    df_lazy, newCols = clean_column_labels_after_flatten_df(df_lazy, valueCols)
    return df_lazy


def join_period_values(
    df: pl.DataFrame | pl.LazyFrame,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    checkedPeriods: list[str],
    chosenDimension: str,
) -> pl.LazyFrame:
    """Join period-based values back to ``dfCopy`` lazily using Polars."""

    lf_base = ensure_lazyframe(dfCopy).sort(chosenDimension)
    lf_to_join = (
        ensure_lazyframe(df).pipe(drop_columns, checkedPeriods).sort(chosenDimension)
    )

    return lf_base.join(lf_to_join, on=chosenDimension, how="left")


def calculate_sales_growth(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    periodOrder: list[str],
    salesMetric: str,
    growthMetric: str,
) -> pl.LazyFrame:
    """Calculate year-to-year sales growth lazily using Polars."""

    lf = ensure_lazyframe(dfCopy)

    df_lazy = get_period_values(lf, chosenDimension, salesMetric)

    columns, _ = get_schema_and_column_names(df_lazy)
    checkedPeriods = []
    for p in periodOrder:
        if p in columns:
            checkedPeriods.append(p)
        elif p.lower() in columns:
            checkedPeriods.append(p.lower())
        elif f"_{p}" in columns:
            checkedPeriods.append(f"_{p}")
        elif f"_{p.lower()}" in columns:
            checkedPeriods.append(f"_{p.lower()}")
        else:
            checkedPeriods.append(p)

    growth_expr = (
        (pl.col(checkedPeriods[1]) - pl.col(checkedPeriods[0]))
        / pl.col(checkedPeriods[0])
        * 100
    ).round(0)

    df_lazy = (
        df_lazy.with_columns(
            pl.when(pl.col(checkedPeriods[0]) != 0)
            .then(growth_expr)
            .otherwise(None)
            .alias(growthMetric)
        )
        .with_columns(
            pl.when((pl.col(checkedPeriods[1]) < 0) & (pl.col(checkedPeriods[0]) < 0))
            .then(pl.col(growthMetric) * -1)
            .otherwise(pl.col(growthMetric))
            .alias(growthMetric)
        )
        .with_columns(
            pl.when(pl.col(growthMetric) > 999)
            .then(pl.lit(999))
            .otherwise(pl.col(growthMetric))
            .alias(growthMetric)
        )
    )

    toKeep = checkedPeriods + [growthMetric, chosenDimension]
    toDrop = [c for c in columns if c not in toKeep]
    df_lazy = drop_columns(df_lazy, toDrop)

    df_growth = drop_columns(df_lazy, checkedPeriods)

    result = lf.join(df_growth, on=chosenDimension, how="left")
    return result


def calculate_price_change(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    amountMetric: str,
    quantityMetric: str,
    priceMetric: str,
    periodOrder: list[str],
) -> pl.LazyFrame:
    """Compute price change across periods using Polars lazily."""

    lf = ensure_lazyframe(dfCopy)

    df_amount = get_period_values(lf, chosenDimension, amountMetric)
    df_quantity = get_period_values(lf, chosenDimension, quantityMetric)

    df_price = df_amount.join(
        df_quantity, on=chosenDimension, how="inner", suffix="_qty"
    )

    amount_cols, _ = get_schema_and_column_names(df_amount)
    period_cols = [c for c in amount_cols if c != chosenDimension]
    new_exprs = []
    for col in period_cols:
        qty_col = f"{col}_qty"
        new_exprs.append((pl.col(col) / pl.col(qty_col)).alias(col))
    df_price = df_price.with_columns(new_exprs)
    df_price = drop_columns(df_price, [f"{c}_qty" for c in period_cols])

    columns, _ = get_schema_and_column_names(df_price)
    checkedPeriods = []
    for p in periodOrder:
        if p in columns:
            checkedPeriods.append(p)
        elif p.lower() in columns:
            checkedPeriods.append(p.lower())
        elif f"_{p}" in columns:
            checkedPeriods.append(f"_{p}")
        elif f"_{p.lower()}" in columns:
            checkedPeriods.append(f"_{p.lower()}")
        else:
            checkedPeriods.append(p)

    growth_expr = (
        (pl.col(checkedPeriods[1]) - pl.col(checkedPeriods[0]))
        / pl.col(checkedPeriods[0])
        * 100
    ).round(0)

    df_price = df_price.with_columns(
        pl.when(pl.col(checkedPeriods[0]) != 0)
        .then(growth_expr)
        .otherwise(None)
        .alias(priceMetric)
    )

    df_price = df_price.with_columns(
        pl.when((pl.col(checkedPeriods[1]) < 0) & (pl.col(checkedPeriods[0]) < 0))
        .then(pl.col(priceMetric) * -1)
        .otherwise(pl.col(priceMetric))
        .alias(priceMetric)
    )

    df_price = df_price.with_columns(
        pl.when(pl.col(priceMetric) > 999)
        .then(pl.lit(999))
        .otherwise(pl.col(priceMetric))
        .alias(priceMetric)
    )

    result = join_period_values(df_price, lf, checkedPeriods, chosenDimension)
    return result


def get_growth_rate(
    dfCopy, chosenDimension, periodOrder, paramDict, chartDict, overlayMetric
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    amountName = namingParams["monetaryLocalCurrencyName"]
    volumeName = namingParams["volumeName"]
    marginName = namingParams["marginName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    unitsName = namingParams["unitsName"]
    onePeriodOnly = namingParams["onePeriodOnly"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    singleMetric = namingParams["singleMetric"]
    metricsToPlot = namingParams["metricsToPlot"]
    volumePriceChangeName = namingParams["volumePriceChangeName"]
    netVolumePriceChangeName = namingParams["netVolumePriceChangeName"]
    unitsPriceChangeName = namingParams["unitsPriceChangeName"]
    netUnitsPriceChangeName = namingParams["netUnitsPriceChangeName"]
    salesGrowthName = namingParams["salesGrowthName"]
    netSalesGrowthName = namingParams["netSalesGrowthName"]
    unitsGrowthName = namingParams["unitsGrowthName"]
    volumeGrowthName = namingParams["volumeGrowthName"]
    marginGrowthName = namingParams["marginGrowthName"]
    chosenChart = namingParams["chosenChart"]
    calculateGrowth = notMetConditionValue
    if xAxisMetric in chartDict and yAxisMetric in chartDict:
        xAxisMetric = chartDict[xAxisMetric]
        yAxisMetric = chartDict[yAxisMetric]
        calculateGrowth = metConditionValue
    elif singleMetric in chartDict:
        xAxisMetric = chartDict[singleMetric]
        yAxisMetric = chartDict[singleMetric]
        calculateGrowth = metConditionValue
    elif metricsToPlot in chartDict and len(chartDict[metricsToPlot]) > 0:
        xAxisMetric = chartDict[metricsToPlot][overlayMetric]
        yAxisMetric = chartDict[metricsToPlot][overlayMetric]
        calculateGrowth = metConditionValue
    if calculateGrowth:
        if onePeriodOnly in paramDict and paramDict[onePeriodOnly]:
            pass
        elif chosenDimension in [nothingFilteredName, None]:
            pass
        elif get_row_count(dfCopy) == 0:
            pass
        elif xAxisMetric in growthMetricArray or yAxisMetric in growthMetricArray:
            if xAxisMetric == salesGrowthName or yAxisMetric == salesGrowthName:
                dfCopy = calculate_sales_growth(
                    dfCopy, chosenDimension, periodOrder, amountName, salesGrowthName
                )
            if xAxisMetric == netSalesGrowthName or yAxisMetric == netSalesGrowthName:
                dfCopy = calculate_sales_growth(
                    dfCopy,
                    chosenDimension,
                    periodOrder,
                    netOfDiscountName,
                    netSalesGrowthName,
                )
            if xAxisMetric == unitsGrowthName or yAxisMetric == unitsGrowthName:
                dfCopy = calculate_sales_growth(
                    dfCopy, chosenDimension, periodOrder, unitsName, unitsGrowthName
                )
            if xAxisMetric == volumeGrowthName or yAxisMetric == volumeGrowthName:
                dfCopy = calculate_sales_growth(
                    dfCopy, chosenDimension, periodOrder, volumeName, volumeGrowthName
                )
            if xAxisMetric == marginGrowthName or yAxisMetric == marginGrowthName:
                dfCopy = calculate_sales_growth(
                    dfCopy, chosenDimension, periodOrder, marginName, marginGrowthName
                )
            if (
                xAxisMetric == unitsPriceChangeName
                or yAxisMetric == unitsPriceChangeName
            ):
                dfCopy = calculate_price_change(
                    dfCopy,
                    chosenDimension,
                    amountName,
                    unitsName,
                    unitsPriceChangeName,
                    periodOrder,
                )
            if (
                xAxisMetric == netUnitsPriceChangeName
                or yAxisMetric == netUnitsPriceChangeName
            ):
                dfCopy = calculate_price_change(
                    dfCopy,
                    chosenDimension,
                    netOfDiscountName,
                    unitsName,
                    netUnitsPriceChangeName,
                    periodOrder,
                )
            if (
                xAxisMetric == volumePriceChangeName
                or yAxisMetric == volumePriceChangeName
            ):
                dfCopy = calculate_price_change(
                    dfCopy,
                    chosenDimension,
                    amountName,
                    volumeName,
                    volumePriceChangeName,
                    periodOrder,
                )
            if (
                xAxisMetric == netVolumePriceChangeName
                or yAxisMetric == netVolumePriceChangeName
            ):
                dfCopy = calculate_price_change(
                    dfCopy,
                    chosenDimension,
                    netOfDiscountName,
                    volumeName,
                    netVolumePriceChangeName,
                    periodOrder,
                )
    return dfCopy


def multiply_percent_metrics_by_hundred(df):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    columns, schema = get_schema_and_column_names(df)
    # Use Polars expressions to avoid pandas-style direct assignment
    exprs = []
    for metric in percentMetricsArray:
        if metric in columns:
            exprs.append(((pl.col(metric) * 100).round(1)).alias(metric))
    if exprs:
        return df.with_columns(exprs)
    return df


def adjust_percentages_dynamic(
    df: pl.DataFrame | pl.LazyFrame,
) -> pl.DataFrame | pl.LazyFrame:
    """
    For each row:
      1) Keep the leftmost_col unchanged (often a text label).
      2) For each numeric column (excluding leftmost_col, total_col),
         compute an integer %: int(round((col_i / row[total_col]) * 100)).
      3) Sum these integer %'s; leftover = 100 - that sum.
      4) Add leftover to the single largest column in that row (may be + or -).
      5) Overwrite 'total_col' with 100.

    Returns a new Polars DataFrame with integer percentages that sum to 100.
    """
    namingParams = get_naming_params()
    leftmost_col = namingParams["periodName"]
    total_col = namingParams["valueName"]
    numeric_types = {
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    }
    skip_cols = {leftmost_col, total_col}
    schema = get_schema_and_column_names(df)[1]
    numeric_cols = [
        name
        for name, dtype in schema.items()
        if name not in skip_cols and dtype in numeric_types
    ]

    if not numeric_cols:
        return df.with_columns(pl.lit(100).alias(total_col))

    frame = df

    percent_exprs = [
        pl.when(pl.col(total_col) == 0)
        .then(0)
        .otherwise((pl.col(col) / pl.col(total_col) * 100).round(0))
        .cast(pl.Int64)
        .alias(col)
        for col in numeric_cols
    ]
    frame = frame.with_columns(percent_exprs)

    sum_expr = pl.fold(
        pl.lit(0), lambda acc, e: acc + e, [pl.col(c) for c in numeric_cols]
    ).alias("__sum__")
    frame = frame.with_columns(sum_expr)

    diff_expr = (
        pl.when(pl.col(total_col) == 0)
        .then(0)
        .otherwise(100 - pl.col("__sum__"))
        .alias("__diff__")
    )
    frame = frame.with_columns(diff_expr)

    frame = frame.with_columns(
        pl.concat_list([pl.col(c) for c in numeric_cols]).alias("__list__")
    )
    frame = frame.with_columns(pl.col("__list__").list.arg_max().alias("__argmax__"))

    updates = [
        pl.when(pl.col("__argmax__") == idx)
        .then(pl.col(col) + pl.col("__diff__"))
        .otherwise(pl.col(col))
        .alias(col)
        for idx, col in enumerate(numeric_cols)
    ]
    frame = frame.with_columns(updates)

    frame = frame.with_columns(pl.lit(100).alias(total_col))

    return frame.drop(["__sum__", "__diff__", "__list__", "__argmax__"])


def replace_NA_with_blanc(lf, column):
    lf = lf.with_columns(
        pl.col(column)
        .str.replace(r"^(N/A|NaN|)$", None)  # Match and replace
        .alias(column)
    )
    return lf


def lookup_dates_polars(lf: pl.LazyFrame, col: str) -> pl.LazyFrame:
    """Parse unique date strings once and cast the column."""

    try:
        unique_dates = (
            lf.select(pl.col(col).drop_nulls().unique()).collect()[col].to_list()
        )
        check_collect("TAA", "unique_dates", unique_dates)

        lf = replace_NA_with_blanc(lf, col)
        parse_expr = (
            pl.col(col)
            .str.to_datetime(strict=False)
            .dt.date()
            .fill_null(pl.col(col).str.strptime(pl.Date, "%Y-%m-%d", strict=False))
            .fill_null(pl.col(col).str.strptime(pl.Date, "%Y/%m/%d", strict=False))
            .fill_null(pl.col(col).str.strptime(pl.Date, "%d-%m-%Y", strict=False))
            .fill_null(pl.col(col).str.strptime(pl.Date, "%b %d %Y", strict=False))
        )
        lf = lf.with_columns(parse_expr.alias(col))
    except Exception as e:  # pragma: no cover - unforeseen date formats
        logging.exception(e)
        logger.exception("Parsing failed for column '%s'", col)
        raise ValueError(f"Failed to parse dates in column '{col}'") from e

    return lf


def check_no_duplicates(array):
    newArray = []
    for element in array:
        if element not in newArray:
            newArray.append(element)
    return newArray


def check_if_more_than_one_in_common(findInArray, findFromArray):
    """
    if there are more than one hierarchical node of a same hierarchy
    we only want to keep the most detailed node
    """
    both = set(findInArray).intersection(findFromArray)
    indices_findInArray = [findInArray.index(x) for x in both]
    indices_findInArray.sort()
    if len(indices_findInArray) > 0:
        indices_findInArray.pop()
        count = 0
        for element in indices_findInArray:
            element = element - count
            findInArray.pop(element)
            count = count + 1
    return findInArray


def insert_missing_parents(findInArray, findFromArray):
    """
    in this alternative method we complete the array with all their parents
    """
    findFromArray = list(findFromArray.keys())
    both = set(findInArray).intersection(findFromArray)
    indices_findFromArray = [findFromArray.index(x) for x in both]
    indices_findFromArray.sort()
    if len(indices_findFromArray) > 0:
        maxHierarchyIndex = indices_findFromArray[-1]
        fullHierarchicalIndexes = findFromArray[: maxHierarchyIndex + 1]
        findInArray = findInArray + fullHierarchicalIndexes
        findInArray = list(set(findInArray))
    return findInArray


def add_bold(string):
    string = "**" + string + "**"
    return string


def add_bold_and_carrier_return(string):
    string = "**" + string + "**" + "\n"
    return string


def to_excel(df: pl.DataFrame | pl.LazyFrame) -> bytes:
    """Return an Excel representation of ``df`` using Polars.

    Complex objects like ``dict`` or ``list`` are serialized to JSON strings so
    cells remain readable when opened in Excel.
    """

    if isinstance(df, pl.LazyFrame):
        df_pl = df.collect()
    else:
        df_pl = df

    def _convert(val: Any) -> str:
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    exprs = []
    df_pl_cols, _ = get_schema_and_column_names(df_pl)
    for col, dtype in zip(df_pl_cols, df_pl.dtypes):
        if dtype in (pl.Object, pl.Struct) or isinstance(dtype, pl.List):
            exprs.append(
                pl.col(col).map_elements(_convert, return_dtype=pl.Utf8).alias(col)
            )
        else:
            exprs.append(pl.col(col))

    df_pl = df_pl.select(exprs)

    output = BytesIO()
    write_polars_excel(df_pl, output)
    return output.getvalue()


def get_table_download_link(data, name, fileFormat):
    """Return a download link for ``data``.

    ``data`` may be a :class:`polars.DataFrame` or :class:`polars.LazyFrame`.
    """
    if fileFormat == "Excel":
        val = to_excel(data)
        b64 = base64.b64encode(val)
        return (
            f'<a href="data:application/octet-stream;base64,{b64.decode()}" '
            f'download="{name}.xlsx">Download "{name}" Excel file.</a>'
        )
    elif fileFormat == "csv":
        df_pl = data.collect() if isinstance(data, pl.LazyFrame) else data
        val = df_pl.write_csv()
        b64 = base64.b64encode(val.encode()).decode()
        return (
            f'<a href="data:file/csv;base64,{b64}" '
            f'download="{name}.csv">Download "{name}" csv file</a>'
        )
    elif fileFormat == "profile":
        with open(data, "rb") as f:
            val = f.read()
        b64 = base64.b64encode(val).decode()
        return (
            f'<a href="data:file/csv;base64,{b64}" download="'
            + name
            + '.html">Download "'
            + name
            + '" html file</a>'
        )  # decode b'abc' => abc
        return href


def get_table_number_format(df, colArray):
    """
    the smaller the number the more decimal positions we want
    """
    namingParams = get_naming_params()
    columns, schema = get_schema_and_column_names(df)
    numberFormatDict = {}
    numberFormatDict["{:,.0f}"] = []
    numberFormatDict["{:,.1f}"] = []
    numberFormatDict["{:,.2f}"] = []
    numberFormatDict["{:,.3f}"] = []
    for column in colArray:
        if column in columns:
            # Sum of first 5 rows for this column (pandas-like head().sum())
            columnSum = (
                ensure_lazyframe(df)
                .select(pl.col(column))
                .head(5)
                .select(pl.col(column).sum())
                .collect()
                .item()
            )
            absoluteSum = math.fabs(columnSum)
            if absoluteSum < 0.1:
                numberFormatDict["{:,.2f}"].append(column)
            elif absoluteSum < 1:
                numberFormatDict["{:,.2f}"].append(column)
            elif absoluteSum < 10:
                numberFormatDict["{:,.1f}"].append(column)
            elif absoluteSum < 100:
                numberFormatDict["{:,.1f}"].append(column)
            else:
                numberFormatDict["{:,.0f}"].append(column)
    return numberFormatDict


def get_row_data_from_original_df(dfDict, dfCopy, chartDict, indexCols):
    """
    based on the plotting choice of the user we want to return a dataframe
    with the elements corresponding to that report row
    """
    namingParams = get_naming_params()
    dfMainReportName = namingParams["dfMainReportName"]
    rowToPlot = namingParams["rowToPlotName"]
    nanFillValue = namingParams["nanFillValue"]
    workColumn = namingParams["workColumn"]
    varianceType = namingParams["varianceTypeName"]
    plotOriginalData = namingParams["plotOriginalData"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    dfDictListDrilledName = namingParams["dfDictListDrilledName"]
    drillDownDatasetNumber = namingParams["drillDownDatasetNumber"]
    mainReportRunName = namingParams["mainReportRunName"]
    chosenRow = chartDict[rowToPlot] - 1
    if (
        drillDownDatasetNumber in chartDict
        and chartDict[drillDownDatasetNumber] != mainReportRunName
    ):
        dfListCopy = dfDict[dfDictListDrilledName][chartDict[drillDownDatasetNumber]]
    else:
        dfListCopy = dfDict[dfMainReportName]
    dfList = duplicate_dataframe(dfListCopy)
    filterDict: dict[str, list] = {}
    if is_valid_lazyframe(dfList):
        columns, _ = get_schema_and_column_names(dfList)
        filterCols = indexCols + [varianceType]
        foundFilterCols = [c for c in filterCols if c in columns]
        lf_list = (
            ensure_lazyframe(dfList)
            .select(foundFilterCols)
            .drop_nulls()
            .limit(chosenRow + 1)
        )
        df_temp = lf_list.collect()
        df_temp_cols, _ = get_schema_and_column_names(df_temp)
        filterDict = {col: df_temp[col].to_list() for col in df_temp_cols}
        if chosenRow + 1 > df_temp.height:
            chosenRow = df_temp.height - 1
            chartDict[rowToPlot] = chosenRow + 1

    rowVarianceType = filterDict.get(varianceType, [None] * (chosenRow + 1))[
        chartDict[rowToPlot] - 1
    ]

    df = ensure_lazyframe(duplicate_dataframe(dfCopy))
    df = df.with_columns(pl.lit(rowVarianceType).alias(varianceType))

    for row in range(chosenRow + 1):
        exprs = []
        for column, values in filterDict.items():
            value = values[row]
            if value != nanFillValue:
                exprs.append(pl.col(column).is_in([value]))
        if exprs:
            condition = exprs[0]
            for e in exprs[1:]:
                condition &= e
            if row == chosenRow:
                df = df.filter(condition)
            elif (
                plotOriginalData in chartDict
                and chartDict[plotOriginalData] == notMetConditionValue
            ):
                df = df.filter(~condition)

    return df, len(filterDict), chartDict


def check_if_other_in_x_dimension(df, chartDict):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    xAxisDimension = namingParams["xAxisDimension"]
    isOtherRank = False
    itemArray = (
        ensure_lazyframe(df)
        .select(pl.col(chartDict[xAxisDimension]).cast(pl.Utf8).unique())
        .collect()
        .get_column(chartDict[xAxisDimension])
        .to_list()
    )
    for element in itemArray:
        if aggregateOtherItemsName in element:
            isOtherRank = True
    return isOtherRank


def check_if_other_in_index(df):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    # Polars has no implicit index; treat the first column as the "index-like" label.
    columns, _ = get_schema_and_column_names(df)
    if not columns:
        return False
    first_col = columns[0]
    try:
        items = (
            ensure_lazyframe(df)
            .select(pl.col(first_col).cast(pl.Utf8).unique())
            .collect()
            .get_column(first_col)
            .to_list()
        )
    except Exception as e:
        logging.exception(e)
        # Fallback for eager DataFrame
        if isinstance(df, pl.DataFrame):
            items = df.get_column(first_col).cast(pl.Utf8).unique().to_list()
        else:
            items = []
    for element in items:
        if element is not None and aggregateOtherItemsName in element:
            return True
    return False


def check_if_other_in_columns(df):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    isOtherRank = False
    columns, schema = get_schema_and_column_names(df)
    for element in columns:
        if aggregateOtherItemsName in element:
            isOtherRank = True
    return isOtherRank


def check_if_other_in_rows(df, column):
    namingParams = get_naming_params()
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    xAxisDimension = namingParams["xAxisDimension"]
    isOtherRank = False
    columns, schema = get_schema_and_column_names(df)
    if column in columns:
        itemArray = (
            ensure_lazyframe(df)
            .select(pl.col(column).cast(pl.Utf8).unique())
            .collect()
            .get_column(column)
            .to_list()
        )
        for element in itemArray:
            if aggregateOtherItemsName in element:
                isOtherRank = True
    return isOtherRank
