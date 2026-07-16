from __future__ import annotations

import copy
import logging
from itertools import combinations

import numpy as np
import polars as pl

import modules.utilities.helpers as helpers
from modules.data.common_data_utils import (
    assemble_query_string_elements,
    build_equal_to_query_string_element,
    clean_array_values,
    get_query_string_from_dict,
)
from modules.utilities.config import (
    get_config_params,
    get_drilldown_params,
    get_naming_params,
    get_run_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_error_message_in_variance_options_tab,
    add_warning_message_in_variance_options_tab,
    add_write_message_in_variance_options_tab,
)
from modules.utilities.helpers import (
    _save_recalculation_steps,
    check_if_duplicates_in_all_columns,
    drop_columns,
    get_dataset_specific_parameter,
    measure_time,
    print_error_details,
    round_value_columns_to_dec,
)
from modules.utilities.ui_notifier import ui
from modules.utilities.utils import (
    ensure_lazyframe,
    ensure_polars_df,
    get_schema_and_column_names,
    is_valid_lazyframe,
)
from modules.variance.variance_utils import (
    calculate_change,
    check_if_duplicate_variance_values,
    delete_duplicate_variance_values,
    get_cell_value_from_dataframe,
    tag_rows_with_index_number,
)

__all__ = [
    "process_move_rows_report",
    "process_node_combinations",
]


def duplicate_dataframe(dfCopy: pl.DataFrame | pl.LazyFrame | object) -> pl.DataFrame:
    """Return an eager frame, matching the original pandas loop semantics."""

    if isinstance(dfCopy, pl.DataFrame):
        return dfCopy.clone()
    if isinstance(dfCopy, pl.LazyFrame):
        return dfCopy.collect()
    return pl.DataFrame(dfCopy)


def _existing(columns: list[str], frame: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return columns that exist in ``frame`` while preserving order."""

    frame_columns, _schema = get_schema_and_column_names(frame)
    return [column for column in columns if column in frame_columns]


def _cast_join_columns(
    frame: pl.DataFrame | pl.LazyFrame,
    columns: list[str],
) -> pl.DataFrame:
    """Cast join-key columns to strings to avoid categorical/string mismatches."""

    df = duplicate_dataframe(frame)
    existing = _existing(columns, df)
    if not existing:
        return df
    return df.with_columns(
        pl.col(column).cast(pl.Utf8).alias(column) for column in existing
    )


def _sort_by_column(
    frame: pl.DataFrame | pl.LazyFrame,
    column: str,
    *,
    nulls_last: bool = True,
) -> pl.DataFrame:
    """Sort by ``column`` when it exists."""

    df = duplicate_dataframe(frame)
    if column not in df.columns:
        return df
    return df.sort(column, nulls_last=nulls_last)


def add_drill_down_params_to_dict(paramDictCopy):
    """
    drill down can be run using different parameters relative to the main run.
    """
    drilldownParams = get_drilldown_params()
    namingParams = get_naming_params()
    fileCodeName = namingParams["fileCodeName"]
    paramDict = copy.deepcopy(paramDictCopy)
    if fileCodeName in paramDict:  # uploaded files have no fileCode
        fileCode = paramDict[fileCodeName]
        drilldownDict = {}
        if fileCode in drilldownParams:
            drilldownDict = drilldownParams[fileCode]
        for element in drilldownDict:
            paramDict[element] = drilldownDict[element]
    return paramDict


def process_move_rows_report(df, indexCols, paramDict, chartDict, run):
    """
    wrapping function in order to be able to use cache
    """
    namingParams = get_naming_params()
    insertAtRowDictName = namingParams["insertAtRowDict"]
    if insertAtRowDictName in paramDict and len(paramDict[insertAtRowDictName]) > 0:
        dfList, dfDetails, dfSnapshot, paramDict = process_node_combinations(
            df, indexCols, paramDict, chartDict, run
        )
    else:
        dfList, dfDetails, dfSnapshot = pl.DataFrame(), pl.DataFrame(), pl.DataFrame()
    return (
        ensure_polars_df(dfList),
        ensure_polars_df(dfDetails),
        ensure_polars_df(dfSnapshot),
        paramDict,
    )


def process_node_combinations(dfCopy, indexCols, paramDict, chartDict, run):
    """
    runs the loop for the top nodes, in descending order,  re-ajusts the value of the top nodes, and re-sorts them
    """
    namingParams = get_naming_params()
    runningTotalName = namingParams["runningTotalName"]
    rowResultsUntilStop = namingParams["rowResultsUntilStop"]
    rowsFoundToSubtract = namingParams["rowsFoundToSubtract"]
    numberOfRowResults = namingParams["numberOfRowResults"]
    noMoreRowsWithRandomKey = namingParams["noMoreRowsWithRandomKey"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    randomKey = namingParams["randomKey"]
    varianceTypeName = namingParams["varianceTypeName"]
    insertAtRowDictName = namingParams["insertAtRowDict"]
    forcedValue = namingParams["forcedValue"]
    rowProcessing = namingParams["rowProcessingName"]
    expectedRowResults, paramDict = get_dataset_specific_parameter(
        paramDict, numberOfRowResults, False
    )
    if insertAtRowDictName in paramDict:
        expectedRowResults = (
            expectedRowResults + len(paramDict[insertAtRowDictName]) - 1
        )
    count = 1
    df = _cast_join_columns(dfCopy, indexCols + [varianceTypeName])
    dfArray = []
    detailsDfArray = []
    inbondsDfArray = []
    paramDict[runningTotalName] = 0
    paramDict[noMoreRowsWithRandomKey] = notMetConditionValue
    paramDict[rowsFoundToSubtract] = 1
    if forcedValue in paramDict and paramDict[forcedValue] == metConditionValue:
        pass
    else:
        pass
    for index in range(0, expectedRowResults):
        if paramDict[rowsFoundToSubtract] > 0 and is_valid_lazyframe(df):
            first_key = df.get_column(randomKey)[0]
            if (
                not paramDict[noMoreRowsWithRandomKey]
                and first_key is not None
                and first_key == first_key
            ):
                df, dfArray, detailsDfArray, inbondsDfArray, paramDict = (
                    recalculate_node_values(
                        df,
                        indexCols,
                        dfArray,
                        detailsDfArray,
                        inbondsDfArray,
                        paramDict,
                        chartDict,
                        count,
                        run,
                    )
                )
                paramDict[rowResultsUntilStop] = count
                count = count + 1
            if forcedValue in paramDict and paramDict[forcedValue] == metConditionValue:
                pass
            else:
                pass

    if dfArray.__len__() > 0:
        df_list_concat = pl.concat([duplicate_dataframe(f) for f in dfArray])
        df_list_concat = delete_duplicate_variance_values(
            df_list_concat, indexCols, paramDict, chartDict
        )
        paramDict = check_if_duplicate_variance_values(df_list_concat, paramDict)
    else:
        df_list_concat = pl.DataFrame()

    if len(detailsDfArray) >= 1:
        df_details_concat = pl.concat([duplicate_dataframe(f) for f in detailsDfArray])
    else:
        df_details_concat = pl.DataFrame()

    if len(inbondsDfArray) >= 1:
        df_snapshot_concat = pl.concat([duplicate_dataframe(f) for f in inbondsDfArray])
    else:
        df_snapshot_concat = pl.DataFrame()

    return df_list_concat, df_details_concat, df_snapshot_concat, paramDict


def get_single_row_details(dfCopy, indexColsCopy, frameArray, count):
    """
    for each selected row, we want to store all the details, and use the random key as an index
    this function gets the details of a single row
    """
    runParams = get_run_params()
    namingParams = get_naming_params()
    numberOfRowsDetailed = runParams["numberOfRowsDetailed"]
    maxDfLengthForDetails = runParams["maxDfLengthForDetails"]
    drilldownKey = namingParams["drilldownKey"]
    randomKey = namingParams["randomKey"]
    loopRandomKey = namingParams["loopRandomKey"]
    nanFillValue = namingParams["nanFillValue"]
    varianceTypeName = namingParams["varianceTypeName"]
    if isinstance(dfCopy, pl.LazyFrame):
        row_count = dfCopy.select(pl.len()).collect(engine="streaming")[0, 0]
    else:
        dfCopy = ensure_polars_df(dfCopy)
        row_count = dfCopy.height
    if count <= numberOfRowsDetailed and row_count < maxDfLengthForDetails:
        use_lazy = isinstance(dfCopy, pl.LazyFrame)
        df = ensure_lazyframe(dfCopy) if use_lazy else ensure_polars_df(dfCopy)
        df = df.filter(pl.col(randomKey).is_not_null())
        if is_valid_lazyframe(df):
            indexCols = copy.deepcopy(indexColsCopy)
            indexCols.append(varianceTypeName)
            indexCols = clean_array_values(indexCols)

            first_row_df = df.select(indexCols + [randomKey]).head(1)
            first_row = (
                first_row_df.collect().row(0) if use_lazy else first_row_df.row(0)
            )
            values = first_row[: len(indexCols)]
            rowKey = first_row[len(indexCols)]

            expr = pl.lit(True)
            for col_name, value in zip(indexCols, values):
                if (
                    value != nanFillValue
                    and value not in ["Nan", "nan", np.nan]
                    and value == value
                ):
                    expr = expr & (pl.col(col_name) == value)

            df = df.filter(expr)
            df = drop_columns(df, [drilldownKey, loopRandomKey])
            df = df.with_columns(pl.lit(rowKey).alias(drilldownKey))
            df = df.slice(1)  # do not take the "father" row, just the children
            frameArray.append(df)
    return frameArray


def make_filtering_dataframe(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    count: int,
    run: str,
    paramDict: dict,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Create a dataframe used to filter rows."""

    namingParams = get_naming_params()
    loopRandomKey = namingParams["loopRandomKey"]
    nanFillValue = namingParams["nanFillValue"]
    varianceTypeName = namingParams["varianceTypeName"]

    use_lazy = isinstance(dfCopy, pl.LazyFrame)
    df_pl = _cast_join_columns(dfCopy, indexCols + [varianceTypeName])

    df_pl = df_pl.select(indexCols + [loopRandomKey, varianceTypeName])

    first_vals = df_pl.select(
        pl.col(col).first().alias(col) for col in indexCols
    ).limit(1)
    first_values = {
        col: first_vals[col][0] if first_vals.height > 0 else None for col in indexCols
    }

    for column in indexCols:
        filter_value = first_values[column]
        if (
            filter_value is not None and filter_value == filter_value
        ) or filter_value != nanFillValue:
            df_pl = df_pl.with_columns(
                pl.when(pl.col(column).is_null() | (pl.col(column) == nanFillValue))
                .then(pl.lit(filter_value))
                .otherwise(pl.col(column))
                .alias(column)
            )

    columns = indexCols + [varianceTypeName]
    paramDict = check_if_duplicates_in_all_columns(df_pl, "filtering df", paramDict)
    df_pl = df_pl.sort(columns)

    return (df_pl.lazy() if use_lazy else df_pl), paramDict


def check_units_in_both_period_positive(df, count, run, paramDict):
    """
    period zero and period one units should both be positive for the chosen result otherwise the result makes no sense
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    separatorString = namingParams["separatorString"]
    unitsName = namingParams["unitsName"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    columns, _ = get_schema_and_column_names(df)
    if unitsPeriodZero in columns:
        message = ""
        lf = ensure_lazyframe(df)
        units_zero, units_one = (
            lf.select(
                pl.first(unitsPeriodZero),
                pl.first(unitsPeriodOne),
            )
            .collect()
            .row(0)
        )
        if units_zero < 0 or units_one < 0:
            message = (
                "Processing error in loop "
                + str(count)
                + " in "
                + run
                + ". Negative units values"
            )
        elif units_zero == 0 and units_one == 0:
            message = (
                "Processing error in loop "
                + str(count)
                + " in "
                + run
                + ". Zero units values"
            )
        if len(message) > 1:
            paramDict = add_warning_message_in_variance_options_tab(paramDict, message)
    return df, paramDict


def build_query_string_element_with_variable(
    colName, variableName, operator, queryArray
):
    """
    builds "must be equal to" query string
    """
    leftSideElement = "(" + colName + operator
    variableName = "@" + variableName + ")"
    rightSideElement = variableName
    queryStringElement = leftSideElement + rightSideElement
    queryArray.append(queryStringElement)
    return queryArray


def connect_query_strings(queryArray, operator):
    aggregatedString = ""
    count = 1
    numberOfElements = len(queryArray)
    for element in queryArray:
        if count < numberOfElements:
            element = element + operator
        aggregatedString = aggregatedString + element
        count = count + 1
    return aggregatedString


def filter_in_bond_rows_matrix(
    df: pl.DataFrame | pl.LazyFrame,
    minValueVar: float,
    minValueTot: float,
    maxValueVar: float,
    maxValueTot: float,
    paramDict: dict,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Filter ``df`` for rows within the variance bounds."""

    namingParams = get_naming_params()
    randomKey = namingParams["randomKey"]
    varianceAmount = namingParams["varianceAmountName"]
    noMoreRowsWithRandomKey = namingParams["noMoreRowsWithRandomKey"]
    metConditionValue = namingParams["metConditionValue"]

    minPercentOfTotalVariance = paramDict["minPercentOfTotalVariance"]
    minPercentOfTotalAmount = paramDict["minPercentOfTotalAmount"]
    maxPercentOfTotalVariance = paramDict["maxPercentOfTotalVariance"]
    maxPercentOfTotalAmount = paramDict["maxPercentOfTotalAmount"]

    cond = pl.lit(True)
    if minPercentOfTotalVariance > 0:
        cond &= pl.col(varianceAmount).abs() > pl.lit(minValueVar)
    if minPercentOfTotalAmount > 0:
        cond &= pl.col(varianceAmount).abs() > pl.lit(minValueTot)
    if maxPercentOfTotalVariance < 1:
        cond &= pl.col(varianceAmount).abs() < pl.lit(maxValueVar)
    if maxPercentOfTotalAmount < 1:
        cond &= pl.col(varianceAmount).abs() < pl.lit(maxValueTot)

    df_lf = ensure_lazyframe(df).with_row_index("__idx")
    dfQuery = df_lf.select(["__idx", randomKey, varianceAmount]).filter(cond)
    dfQuery_first = dfQuery.select(
        pl.first(randomKey).alias(randomKey),
        pl.first("__idx").alias("__idx"),
    ).collect(engine="streaming")

    if dfQuery_first.height > 0:
        randomkeyValue = dfQuery_first[randomKey][0]
        if randomkeyValue is not None and randomkeyValue == randomkeyValue:
            indexValue = int(dfQuery_first["__idx"][0])
            df_lf = df_lf.drop("__idx").slice(indexValue)
        else:
            paramDict[noMoreRowsWithRandomKey] = metConditionValue
            df_lf = pl.LazyFrame()
    else:
        paramDict[noMoreRowsWithRandomKey] = metConditionValue
        df_lf = pl.LazyFrame()

    if isinstance(df, pl.DataFrame):
        return ensure_polars_df(df_lf), paramDict
    return df_lf, paramDict


def check_if_top_variance_in_bonds(df, paramDict, chartDict, run):
    """
    we only consider the result (total variance of top row) if it is between the bonds
    """
    namingParams = get_naming_params()
    varianceAggregationParams = get_variance_aggregation_params()
    cogsAggregationArray = varianceAggregationParams[
        namingParams["cogsAggregationArray"]
    ]
    salesAggregationArray = varianceAggregationParams[
        namingParams["salesAggregationArray"]
    ]
    discountsAggregationArray = varianceAggregationParams[
        namingParams["discountsAggregationArray"]
    ]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    varianceTypeName = namingParams["varianceTypeName"]
    varianceAmountName = namingParams["varianceAmountName"]
    varianceAggregation = namingParams["varianceAggregation"]
    randomKey = namingParams["randomKey"]
    totalVarianceValueKey = namingParams["totalVarianceValue"]
    avgAmountPeriodsZeroOneKey = namingParams["avgAmountPeriodsZeroOne"]
    noMoreRowsWithRandomKey = namingParams["noMoreRowsWithRandomKey"]
    metConditionValue = namingParams["metConditionValue"]
    percentVarianceAfterCogs = namingParams["percentVarianceAfterCogs"]
    percentVarianceAfterDiscounts = namingParams["percentVarianceAfterDiscounts"]
    varianceInPercent = namingParams["varianceInPercent"]
    metConditionValue = namingParams["metConditionValue"]
    netOfDiscountVarianceKey = namingParams["netOfDiscountVariance"]
    avgNetOfDiscountPeriodsZeroOne = namingParams["avgNetOfDiscountPeriodsZeroOne"]
    marginVarianceKey = namingParams["marginVariance"]
    avgMarginPeriodsZeroOneKey = namingParams["avgMarginPeriodsZeroOne"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    clearCacheLabel = namingParams["clearCacheLabel"]
    colNumber = 0
    try:
        if chartDict[varianceAggregation] in salesAggregationArray:
            varianceSum = paramDict[totalVarianceValueKey]
            avgAmount = paramDict[avgAmountPeriodsZeroOneKey]
        elif chartDict[varianceAggregation] in discountsAggregationArray:
            varianceSum = paramDict[netOfDiscountVarianceKey]
            avgAmount = paramDict[avgNetOfDiscountPeriodsZeroOne]
        elif chartDict[varianceAggregation] in cogsAggregationArray:
            varianceSum = paramDict[marginVarianceKey]
            avgAmount = paramDict[avgMarginPeriodsZeroOneKey]
        else:
            errorMessage = "Variance aggregation not found."
            paramDict = add_app_message_to_paramdict(
                errorMessage,
                errorMessageType,
                plotChartsTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
            varianceSum = paramDict[totalVarianceValueKey]
            avgAmount = paramDict[avgAmountPeriodsZeroOneKey]
    except Exception as e:
        logging.exception(e)
        errorMessage = (
            "Unable to correctly load file. Clear cache and run again. To clear the cache hit the "
            + clearCacheLabel
            + " button in the "
            + loadDataTabKey
            + " tab."
        )
        e = print_error_details(e)
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
        varianceSum = 0
        avgAmount = 0
        df = df.head(0)
    varianceAmountWeight, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["varianceAmountWeight"], False
    )
    minPercentOfTotalVariance, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["minPercentOfTotalVariance"], False
    )
    maxPercentOfTotalVariance, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["maxPercentOfTotalVariance"], False
    )
    minPercentOfTotalAmount, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["minPercentOfTotalAmount"], False
    )
    maxPercentOfTotalAmount, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["maxPercentOfTotalAmount"], False
    )
    minPercentConstraint = True
    maxPercentConstraint = True
    if chartDict[varianceInPercent] == metConditionValue:
        if chartDict[varianceAggregation] in cogsAggregationArray:
            varianceSum, avgAmount = paramDict[percentVarianceAfterCogs], 100
        else:
            message = "variance aggregation not found"
            paramDict = add_warning_message_in_variance_options_tab(paramDict, message)
        if run == drilldownReportRunName:
            avgAmount = 10
    if minPercentOfTotalVariance == 0 and minPercentOfTotalAmount == 0:
        minPercentConstraint = False
    if maxPercentOfTotalVariance == 1 and maxPercentOfTotalAmount == 1:
        maxPercentConstraint = False
    if minPercentConstraint or maxPercentConstraint:
        minValueVar = np.abs(minPercentOfTotalVariance * varianceSum)
        maxValueVar = np.abs(maxPercentOfTotalVariance * varianceSum)
        minValueTot = np.abs(minPercentOfTotalAmount * avgAmount)
        maxValueTot = np.abs(maxPercentOfTotalAmount * avgAmount)
        df, paramDict = filter_in_bond_rows_matrix(
            df, minValueVar, minValueTot, maxValueVar, maxValueTot, paramDict
        )
    return df, paramDict


def check_if_to_move_row_found(
    df: pl.DataFrame | pl.LazyFrame,
    filter_dict: dict[str, str],
    count: int,
    run: str,
    paramDict: dict,
) -> dict:
    """Verify that the row defined by ``filter_dict`` exists in ``df``."""

    runParams = get_run_params()
    namingParams = get_naming_params()
    checkIfMoveRowsFound = runParams["checkIfMoveRowsFound"]
    insertAtRowDictName = namingParams["insertAtRowDict"]

    if checkIfMoveRowsFound:
        df_pl = ensure_polars_df(df)
        expr = pl.lit(True)
        for col_name, value in filter_dict.items():
            expr &= pl.col(col_name) == value
        dfQuery = df_pl.filter(expr)

        if dfQuery.height == 0:
            message = "The following row was not found"
            paramDict = add_error_message_in_variance_options_tab(paramDict, message)
            message = (str(count), str(run), str(dfQuery.height))
            paramDict = add_write_message_in_variance_options_tab(paramDict, message)
            message = paramDict[insertAtRowDictName][count - 1]
            paramDict = add_write_message_in_variance_options_tab(paramDict, message)
            message = get_query_string_from_dict(filter_dict)
            paramDict = add_write_message_in_variance_options_tab(paramDict, message)
    return paramDict


def insert_drilldown_row_in_main_report(df, paramDict, count, run):
    """
    we want to be able to inject back into the main report a node combination "found"
    during drill down. Given the randomKey value of the combination we want to inject,
    and given the loop number and the variance type, we simply need, in the right loop, to alter the normalize value
    of the row we want to insert so that it becomes the top row
    """
    namingParams = get_naming_params()
    moveRowReportRunName = namingParams["moveRowReportRunName"]
    randomKey = namingParams["randomKey"]
    varianceType = namingParams["varianceTypeName"]
    normalizedValue = namingParams["aggregatedNormalizedValue"]
    insertAtRowDictName = namingParams["insertAtRowDict"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if insertAtRowDictName in paramDict:
        if count - 1 in paramDict[insertAtRowDictName] and run == moveRowReportRunName:
            filter_dict = paramDict[insertAtRowDictName][count - 1]
            fullQueryString = get_query_string_from_dict(filter_dict)
            paramDict = _save_recalculation_steps(
                df, "insertRow_", count, False, True, run, False, paramDict
            )
            paramDict = check_if_to_move_row_found(
                df, filter_dict, count, run, paramDict
            )
            df_pl = ensure_polars_df(df)
            expr = pl.lit(True)
            for col_name, value in filter_dict.items():
                expr &= pl.col(col_name) == value
            df_pl = df_pl.with_columns(
                pl.when(expr)
                .then(pl.lit(99999))
                .otherwise(pl.col(normalizedValue))
                .alias(normalizedValue)
            ).sort(normalizedValue, descending=True)
            df = df_pl
            paramDict = _save_recalculation_steps(
                df, "insertDrill_", count, False, False, run, False, paramDict
            )
    return df, paramDict


def get_to_subtract_from_rows(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    count: int,
    run: str,
    paramDict: dict,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Return rows to subtract using lazy Polars filtering."""

    namingParams = get_naming_params()
    nanFillValue = namingParams["nanFillValue"]
    varianceTypeName = namingParams["varianceTypeName"]

    df_pl = _cast_join_columns(dfCopy, indexCols).select(indexCols)

    first_row = df_pl.head(1)
    first_values = (
        {c: first_row[c][0] for c in indexCols}
        if first_row.height > 0
        else {c: None for c in indexCols}
    )

    for column in indexCols:
        value = first_values[column]
        if value is not None and value == value and value != nanFillValue:
            if column != varianceTypeName:
                df_pl = df_pl.filter(
                    (pl.col(column) == value) | (pl.col(column) == nanFillValue)
                )
            else:
                df_pl = df_pl.filter(pl.col(column) == value)

    paramDict = helpers._save_recalculation_steps(
        df_pl, "to_subtract_from_", count, False, False, run, False, paramDict
    )

    return df_pl, paramDict


def set_aside_dataframe_snapshot(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    inbondsFrameArray: list[pl.DataFrame | pl.LazyFrame],
    count: int,
    *,
    as_lazy: bool = False,
) -> list[pl.DataFrame | pl.LazyFrame]:
    """Return ``inbondsFrameArray`` with a snapshot of ``dfCopy`` added.

    A :class:`polars.LazyFrame` is returned when ``dfCopy`` is lazy or
    ``as_lazy`` is ``True``.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    randomKey = namingParams["randomKey"]
    loopNumber = namingParams["loopNumberName"]
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    varianceTypeName = namingParams["varianceTypeName"]
    varianceAmountName = namingParams["varianceAmountName"]
    aggregatedNormalizedValue = namingParams["aggregatedNormalizedValue"]
    avgAmountPeriodsZeroOne = namingParams["avgAmountPeriodsZeroOne"]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]
    keepCols = indexCols + [
        aggregatedNormalizedValue,
        varianceTypeName,
        varianceAmountName,
        avgAmountPeriodsZeroOne,
    ]
    use_lazy = isinstance(dfCopy, pl.LazyFrame) or as_lazy

    df_pl = dfCopy.clone() if isinstance(dfCopy, pl.DataFrame) else dfCopy
    if use_lazy and isinstance(df_pl, pl.DataFrame):
        df_pl = df_pl.lazy()

    df_pl = (
        df_pl.drop_nulls([randomKey])
        .with_columns(
            ((pl.col(amountPeriodZero) + pl.col(amountPeriodOne)) / 2)
            .round(0)
            .alias(avgAmountPeriodsZeroOne),
            pl.lit(count).alias(loopNumber),
        )
        .select([c for c in keepCols + [loopNumber]])
    )

    inbondsFrameArray.append(df_pl)
    return inbondsFrameArray


def find_missing_to_subtract_rows(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    dfToSubtractCopy: pl.DataFrame | pl.LazyFrame,
    indexColsCopy: list[str],
    count: int,
    run: str,
    paramDict: dict,
) -> tuple[pl.LazyFrame, dict]:
    """
    we need to see it, in our to_subtract dataset, there are no rows missing.
    If a row is missing, the subtraction will not be possible.
    We start building a dataset will all the  rows we want to subtract from.
    All these rows should be present in the to_subtract dataset
    """
    namingParams = get_naming_params()
    varianceTypeName = namingParams["varianceTypeName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    varianceAmountName = namingParams["varianceAmountName"]
    rowMissingInToSubtract = namingParams["rowMissingInToSubtract"]
    randomKey = namingParams["randomKey"]

    indexCols = copy.deepcopy(indexColsCopy)
    indexCols.append(varianceTypeName)

    df = _cast_join_columns(dfCopy, indexCols)
    df_to_subtract = _cast_join_columns(dfToSubtractCopy, indexCols)

    df = df.filter(pl.col(randomKey).is_not_null() & (pl.col(varianceAmountName) != 0))

    df, paramDict = get_to_subtract_from_rows(df, indexCols, count, run, paramDict)
    df_missing = df_to_subtract.with_columns(
        pl.lit(notMetConditionValue).alias(rowMissingInToSubtract)
    ).select(indexCols + [rowMissingInToSubtract])
    df = df.join(df_missing, on=indexCols, how="left")
    df = (
        df.filter(pl.col(rowMissingInToSubtract).is_null())
        .select(indexCols)
        .with_columns(pl.lit(metConditionValue).alias(rowMissingInToSubtract))
    )

    return df, paramDict


def filter_subtract_rows(
    df: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    *,
    as_lazy: bool = False,
) -> tuple[pl.DataFrame | pl.LazyFrame, list[str]]:
    """
    we filter a dataframe in which, given a filtering row, for every column, if the cell value
    cell is different from All and equal to the filtering string, we keep the rows otherwise we drop them
    in order to to end with the values we need to subtract. When ``as_lazy`` is ``True`` the
    filtered result is returned as a :class:`polars.LazyFrame` regardless of input type.
    """
    namingParams = get_naming_params()
    nanFillValue = namingParams["nanFillValue"]
    varianceTypeName = namingParams["varianceTypeName"]

    use_lazy = as_lazy or isinstance(df, pl.LazyFrame)
    df_pl = _cast_join_columns(df, indexCols)

    filterCols = []

    first_row = df_pl.select(pl.col(c).first().alias(c) for c in indexCols).limit(1)
    first_values = {
        c: first_row[c][0] if first_row.height > 0 else None for c in indexCols
    }

    for column in indexCols:
        value = first_values[column]
        if value is not None and value == value and value != nanFillValue:
            df_pl = df_pl.filter(pl.col(column) == value)
            if column != varianceTypeName:
                filterCols.append(column)

    if use_lazy:
        return df_pl.lazy(), filterCols
    return df_pl, filterCols


def duplicate_filter_rows_with_all(
    dfCopy: pl.DataFrame | pl.LazyFrame, filterCols: list[str]
) -> pl.DataFrame | pl.LazyFrame:
    """Duplicate filter rows to account for ``All`` placeholders."""

    namingParams = get_naming_params()
    nanFillValue = namingParams["nanFillValue"]

    use_lazy = isinstance(dfCopy, pl.LazyFrame)
    df_pl = _cast_join_columns(dfCopy, filterCols)

    arrayLength = len(filterCols)
    frames = [
        df_pl.with_columns(pl.lit(nanFillValue).alias(c) for c in combo)
        for length in range(1, arrayLength + 1)
        for combo in combinations(filterCols, length)
    ]
    frames.insert(0, df_pl)
    result = pl.concat(frames, how="diagonal_relaxed")

    return result.lazy() if use_lazy else ensure_polars_df(result)


def get_rows_to_subtract(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    count: int,
    run: str,
    paramDict: dict,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Return the rows that need to be subtracted for a given node combination."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    nanFillValue = namingParams["nanFillValue"]
    varianceTypeName = namingParams["varianceTypeName"]
    normalizedPercentName = namingParams["normalizedPercentName"]
    normalizedAmountName = namingParams["normalizedAmountName"]
    normalizeNumberOfNodesName = namingParams["normalizeNumberOfNodesName"]
    normalizedUniqueValuesInCombination = namingParams[
        "normalizedUniqueValuesInCombination"
    ]
    aggregatedNormalizedValue = namingParams["aggregatedNormalizedValue"]
    variancePercentChangeName = namingParams["variancePercentChangeName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    numberOfNodes = namingParams["numberOfNodes"]
    separatorString = namingParams["separatorString"]
    drilldownKey = namingParams["drilldownKey"]
    randomKey = namingParams["randomKey"]
    nothingThereString = namingParams["nothingThereString"]
    periodsArray = configParams["periodsArray"]
    discountPerUnitName = namingParams["discountPerUnitName"]
    cogsPerUnitName = namingParams["cogsPerUnitName"]
    discountPerUnitPeriodZero = discountPerUnitName + separatorString + periodsArray[0]
    discountPerUnitPeriodOne = discountPerUnitName + separatorString + periodsArray[1]
    cogsPerUnitPeriodZero = cogsPerUnitName + separatorString + periodsArray[0]
    cogsPerUnitPeriodOne = cogsPerUnitName + separatorString + periodsArray[1]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
    toDrop = [
        variancePercentChangeName,
        normalizedPercentName,
        normalizedAmountName,
        aggregatedNormalizedValue,
        normalizeNumberOfNodesName,
        normalizedUniqueValuesInCombination,
        pricePeriodZero,
        pricePeriodOne,
        randomKey,
        numberOfNodes,
        uniqueValuesInCombination,
        drilldownKey,
        discountPerUnitPeriodZero,
        discountPerUnitPeriodOne,
        cogsPerUnitPeriodZero,
        cogsPerUnitPeriodOne,
    ]
    use_lazy = isinstance(dfCopy, pl.LazyFrame)
    lf = duplicate_dataframe(dfCopy)
    lf = drop_columns(lf, toDrop)
    indexCols = indexCols + [varianceTypeName]
    lf = _cast_join_columns(lf, indexCols)
    lf, filterCols = filter_subtract_rows(lf, indexCols)
    lf = duplicate_filter_rows_with_all(lf, filterCols)
    paramDict = check_if_duplicates_in_all_columns(
        lf, "df in get rows to subtract", paramDict
    )
    lf = lf.unique(maintain_order=True)
    paramDict = _save_recalculation_steps(
        lf, "toSubtract_", count, False, False, run, False, paramDict
    )
    lf = lf.filter(~pl.all_horizontal(pl.all().is_null()))
    lf = lf.sort(indexCols)

    if use_lazy:
        return lf.lazy() if isinstance(lf, pl.DataFrame) else lf, paramDict
    return duplicate_dataframe(lf), paramDict


def join_filtering_dataframe_and_rows_to_subtract(df, dfToSubtract, indexCols):
    """
    we join the dataframe with the rows that need to be subtracted and the dataframe
    with the key in order to have, per row, the values to subtract. We rename the columns
    and drop the colums we do not want for the next join to the base dataframe
    """
    namingParams = get_naming_params()
    varianceTypeName = namingParams["varianceTypeName"]
    loopRandomKey = namingParams["loopRandomKey"]
    drilldownKey = namingParams["drilldownKey"]
    randomKey = namingParams["randomKey"]
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    toSubtractStem = namingParams["toSubtractStem"]
    join_cols = indexCols + [varianceTypeName]
    df = _cast_join_columns(df, join_cols)
    dfToSubtract = _cast_join_columns(dfToSubtract, join_cols)
    columns_to_subtract, _ = get_schema_and_column_names(dfToSubtract)
    value_cols = [
        c for c in columns_to_subtract if c not in indexCols + [varianceTypeName]
    ]
    dfToSubtract = dfToSubtract.rename({c: c + toSubtractStem for c in value_cols})
    joined = df.join(dfToSubtract, on=join_cols, how="inner")
    joined_cols, _ = get_schema_and_column_names(joined)
    df = joined.drop([c for c in joined_cols if c.endswith("_right")]).unique(
        maintain_order=True
    )
    toDrop = indexCols + [varianceTypeName, numberOfNodes, uniqueValuesInCombination]
    df = drop_columns(df, toDrop)
    columns, schema = get_schema_and_column_names(df)
    notSubtractCols = [
        loopRandomKey,
        numberOfNodes,
        uniqueValuesInCombination,
        randomKey,
        drilldownKey,
    ]
    renameDict = {}
    colNames = []
    for column in columns:
        if column not in notSubtractCols and not column.endswith(toSubtractStem):
            newName = column + toSubtractStem
            renameDict[column] = newName
            colNames.append(newName)
        elif column not in notSubtractCols:
            colNames.append(column)
    df = (
        df.rename(renameDict)
        .filter(pl.all_horizontal([pl.col(col).is_not_null() for col in colNames]))
        .filter(pl.any_horizontal([pl.col(col) != 0 for col in colNames]))
        .sort(loopRandomKey)
    )
    return df


def check_rows_for_negative(df: pl.DataFrame | pl.LazyFrame):
    """Remove rows where units or amounts are non-positive."""

    namingParams = get_naming_params()
    configParams = get_config_params()

    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    separatorString = namingParams["separatorString"]

    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]

    df_pl = ensure_polars_df(df)
    columns, _ = get_schema_and_column_names(df_pl)

    if unitsPeriodZero in columns:
        df_pl = df_pl.filter(
            (pl.col(unitsPeriodZero) >= 0) & (pl.col(unitsPeriodOne) >= 0)
        ).filter((pl.col(unitsPeriodZero) > 0) | (pl.col(unitsPeriodOne) > 0))

    if amountPeriodZero in columns:
        df_pl = df_pl.filter(
            (pl.col(amountPeriodZero) >= 0) & (pl.col(amountPeriodOne) >= 0)
        ).filter((pl.col(amountPeriodZero) > 0) | (pl.col(amountPeriodOne) > 0))

    if isinstance(df, pl.LazyFrame):
        return df_pl.lazy()
    return df_pl


def join_rows_to_subtract_to_main_df(df, dfFilter, paramDict):
    """
    we can now join the dataframe with the rows with the values to subtract
    to the main dataframe on the random/index key column
    we do not want to consider the first to delete row
    """
    namingParams = get_naming_params()
    loopRandomKey = namingParams["loopRandomKey"]
    paramDict = check_if_duplicates_in_all_columns(
        df, "df in df join dffilter", paramDict
    )
    df = duplicate_dataframe(df).unique(maintain_order=True)
    paramDict = check_if_duplicates_in_all_columns(
        df, "dfFilter in df join dffilter", paramDict
    )
    dfFilter = duplicate_dataframe(dfFilter).unique(maintain_order=True)
    df = (
        df.join(dfFilter, on=loopRandomKey, how="left")
        .unique(maintain_order=True)
        .sort(loopRandomKey, nulls_last=True)
    )
    return df, paramDict


def subtract_values(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict, count: int, run: str
) -> tuple[pl.DataFrame, pl.DataFrame | pl.LazyFrame, dict]:
    """
    we perform the actual subtraction from corresponding columns. In order to understand
    which column corresponds to which to subtract column we match their names
    if after subtraction result value is negative we set it back to 0
    """
    namingParams = get_naming_params()
    toSubtractStem = namingParams["toSubtractStem"]
    loopRandomKey = namingParams["loopRandomKey"]
    randomKey = namingParams["randomKey"]
    workColumn = namingParams["workColumn"]

    use_lazy = isinstance(df, pl.LazyFrame)
    df_pl = ensure_polars_df(df)

    columns, _ = get_schema_and_column_names(df_pl)
    exprs = []
    drop_cols: list[str] = []
    for col in columns:
        if toSubtractStem in col:
            base = col.split(toSubtractStem)[0]
            exprs.append(
                pl.when(pl.col(loopRandomKey) != 0)
                .then(pl.col(base) - pl.col(col).fill_null(0))
                .otherwise(pl.col(base))
                .alias(base)
            )
            drop_cols.append(col)

    if exprs:
        df_pl = df_pl.with_columns(exprs)

    df_pl = df_pl.with_columns(pl.lit(0).alias(workColumn))

    paramDict = _save_recalculation_steps(
        df_pl, "subtraction_", count, False, False, run, False, paramDict
    )

    df_pl = drop_columns(df_pl, drop_cols + [workColumn])
    df_pl = check_rows_for_negative(df_pl)

    df_first = df_pl.head(1)
    df_rest = df_pl.slice(1).sort(randomKey, nulls_last=True)
    if use_lazy:
        df_rest = df_rest.lazy()

    return df_first, df_rest, paramDict


def tag_missing_rows(df, dfMissing, indexColsCopy):
    """
    one we have selected a "to show" node combination, we need to make sure that the
    other node combinations stay consistent, in other words are netted from the
    values, where appropriate, of the selected node combination
    """
    namingParams = get_naming_params()
    varianceTypeName = namingParams["varianceTypeName"]
    rowMissingInToSubtract = namingParams["rowMissingInToSubtract"]
    randomKey = namingParams["randomKey"]
    loopRandomKey = namingParams["loopRandomKey"]
    if dfMissing.height > 0:
        indexCols = copy.deepcopy(indexColsCopy)
        indexCols.append(varianceTypeName)
        df = _cast_join_columns(df, indexCols)
        dfMissing = _cast_join_columns(dfMissing, indexCols)
        columns, schema = get_schema_and_column_names(df)
        null_random_key = pl.lit(None).cast(schema[randomKey])
        df = df.join(dfMissing, on=indexCols, how="left").with_columns(
            pl.when(pl.col(rowMissingInToSubtract).is_not_null())
            .then(null_random_key)
            .otherwise(pl.col(randomKey))
            .alias(randomKey)
        )
        df = drop_columns(df, [rowMissingInToSubtract])
        df = df.select(columns)
        df = df.sort(loopRandomKey, nulls_last=True)
    return df


def recalculate_node_values(
    df,
    indexCols,
    frameArray,
    detailsFrameArray,
    inbondsFrameArray,
    paramDict,
    chartDict,
    count,
    run,
):
    """
    one we have selected a "to show" node combination, we need to make sure that the
    other node combinations stay consistent, in other words are netted from the
    values, where appropriate, of the selected node combination
    """
    namingParams = get_naming_params()
    loopRandomKey = namingParams["loopRandomKey"]
    randomKey = namingParams["randomKey"]
    drilldownKey = namingParams["drilldownKey"]
    varianceAmountName = namingParams["varianceAmountName"]
    runningTotalName = namingParams["runningTotalName"]
    rowsFoundToSubtract = namingParams["rowsFoundToSubtract"]
    noMoreRowsWithRandomKey = namingParams["noMoreRowsWithRandomKey"]
    rowProcessing = namingParams["rowProcessingName"]
    calculateChange = namingParams["calculateChangeName"]
    normalizeDifferences = namingParams["normalizeDifferencesName"]
    checkIfInBonds = namingParams["checkIfInBondsName"]
    checkIfInBothPeriodsPositive = namingParams["checkIfInBothPeriodsPositiveName"]
    findRowsToSubtract = namingParams["findRowsToSubtractName"]
    tagMissingRows = namingParams["tagMissingRowsName"]
    makeFilteringDataframe = namingParams["makeFilteringDataframeName"]
    saveRecalculationSteps = namingParams["saveRecalculationStepsName"]
    subtractValues = namingParams["subtractValuesName"]
    getCellValueFromDataframe = namingParams["getCellValueFromDataframe"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    colNumber = 0
    df = calculate_change(df, paramDict, chartDict, True)
    paramDict = _save_recalculation_steps(
        df, "diff_", count, False, False, run, False, paramDict
    )
    measure_time(rowProcessing, calculateChange, False)
    df, paramDict = normalize_differences(df, indexCols, paramDict, count)
    measure_time(rowProcessing, normalizeDifferences, False)
    paramDict = _save_recalculation_steps(
        df, "norm_", count, False, True, run, False, paramDict
    )
    df, paramDict = insert_drilldown_row_in_main_report(df, paramDict, count, run)
    df, paramDict = check_if_top_variance_in_bonds(df, paramDict, chartDict, run)
    measure_time(rowProcessing, checkIfInBonds, False)
    paramDict = _save_recalculation_steps(
        df, "inbonds_", count, False, True, run, False, paramDict
    )
    df, paramDict = check_units_in_both_period_positive(df, count, run, paramDict)
    measure_time(rowProcessing, checkIfInBothPeriodsPositive, False)
    paramDict = _save_recalculation_steps(
        df, "check_", count, False, True, run, False, paramDict
    )
    if (
        not paramDict[noMoreRowsWithRandomKey]
        and is_valid_lazyframe(df)
        and not (
            df.get_column(randomKey)[0] is None
            or df.get_column(randomKey)[0] != df.get_column(randomKey)[0]
        )
    ):
        inbondsFrameArray = set_aside_dataframe_snapshot(
            df, indexCols, inbondsFrameArray, count
        )
        dfToSubtract, paramDict = get_rows_to_subtract(
            df, indexCols, count, run, paramDict
        )
        dfMissing, paramDict = find_missing_to_subtract_rows(
            df, dfToSubtract, indexCols, count, run, paramDict
        )
        measure_time(rowProcessing, findRowsToSubtract, False)
        paramDict = _save_recalculation_steps(
            dfMissing, "missing_", count, False, True, run, False, paramDict
        )
        df = tag_rows_with_index_number(df, loopRandomKey)
        df = tag_missing_rows(df, dfMissing, indexCols)
        paramDict = _save_recalculation_steps(
            df, "index_", count, False, False, run, False, paramDict
        )
        measure_time(rowProcessing, tagMissingRows, False)
        try:
            detailsFrameArray = get_single_row_details(
                df, indexCols, detailsFrameArray, count
            )
        except Exception as e:
            logging.exception(e)
            errorMessage = "Error in get_single_row_details function. Variance values might be wrong."
            e = print_error_details(e)
            ui.error("Something went wrong.")
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
            pass
        dfFilter, paramDict = make_filtering_dataframe(
            df, indexCols, count, run, paramDict
        )
        measure_time(rowProcessing, makeFilteringDataframe, False)
        paramDict = _save_recalculation_steps(
            dfFilter, "filtering_", count, False, False, run, False, paramDict
        )
        dfFilter = join_filtering_dataframe_and_rows_to_subtract(
            dfFilter, dfToSubtract, indexCols
        )
        paramDict = _save_recalculation_steps(
            dfFilter, "filter_", count, False, True, run, False, paramDict
        )
        measure_time(rowProcessing, saveRecalculationSteps, False)
        df, paramDict = join_rows_to_subtract_to_main_df(df, dfFilter, paramDict)
        dfResult, df, paramDict = subtract_values(df, paramDict, count, run)
        measure_time(rowProcessing, subtractValues, False)
        paramDict = _save_recalculation_steps(
            df, "out_", count, False, False, run, False, paramDict
        )
        dfResult = drop_columns(dfResult, [loopRandomKey])
        varianceAmount = get_cell_value_from_dataframe(
            dfResult, varianceAmountName, 0, True
        )
        paramDict[runningTotalName] = paramDict[runningTotalName] + varianceAmount
        df = drop_columns(df, [loopRandomKey])
        paramDict[rowsFoundToSubtract] = dfToSubtract.height
        frameArray.append(dfResult)
        measure_time(rowProcessing, getCellValueFromDataframe, False)
    return df, frameArray, detailsFrameArray, inbondsFrameArray, paramDict


def set_duplicate_rows_to_nan(df, normalizedCols):
    """
    we do not want to calculate the normalized values of the "duplicate" rows (node combinations equivalent
    to other combinations), that we need just for subtractions. So we set their normalize value to nan
    """
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    randomKey = namingParams["randomKey"]

    use_lazy = isinstance(df, pl.LazyFrame)
    df_pl = ensure_lazyframe(df) if use_lazy else ensure_polars_df(df)

    columns, _ = get_schema_and_column_names(df_pl)
    exprs = [
        pl.when(pl.col(randomKey).is_null())
        .then(np.nan)
        .otherwise(pl.col(col))
        .alias(col)
        for col in normalizedCols
        if col in columns
    ]

    df_pl = df_pl.with_columns(exprs)

    return df_pl


def lazy_column_stats(
    df: pl.DataFrame | pl.LazyFrame, col: str, stats: list[str]
) -> pl.LazyFrame:
    """Return requested column statistics as a ``LazyFrame``.

    Parameters
    ----------
    df:
        Frame from which to compute the statistics.
    col:
        Column to aggregate.
    stats:
        List of statistics to calculate. Supported values are
        ``"max"``, ``"min"``, ``"mean"``, ``"std"``, and ``"len"``.
    """

    lf = ensure_lazyframe(df)

    exprs: list[pl.Expr] = []
    if "max" in stats:
        exprs.append(pl.col(col).abs().max().alias("max"))
    if "min" in stats:
        exprs.append(pl.col(col).abs().min().alias("min"))
    if "mean" in stats:
        exprs.append(pl.col(col).abs().mean().alias("mean"))
    if "std" in stats:
        exprs.append(pl.col(col).abs().std().alias("std"))
    if "len" in stats:
        exprs.append(pl.len().alias("len"))

    return lf.select(exprs)


def calculate_min_max(
    df: pl.DataFrame | pl.LazyFrame,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    inputCol: str,
    normalizedCol: str,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with ``normalizedCol`` computed using the min-max formula."""

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf_copy = ensure_lazyframe(dfCopy)

    stats_lf = lazy_column_stats(lf_copy, inputCol, ["max", "min"])
    lf = lf.join(stats_lf, how="cross")

    expr = (
        pl.when((pl.col("max") - pl.col("min")) != 0)
        .then(
            (pl.col(inputCol).abs() - pl.col("min")) / (pl.col("max") - pl.col("min"))
        )
        .otherwise(0)
    )

    lf = lf.with_columns(expr.alias(normalizedCol)).drop(["max", "min"])

    return lf if use_lazy else lf.collect()


def calculate_normalized_mean(
    df: pl.DataFrame | pl.LazyFrame,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    inputCol: str,
    normalizedCol: str,
    resultRow: int,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with ``normalizedCol`` computed as a z-score."""

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf_copy = ensure_lazyframe(dfCopy)

    stats_lf = lazy_column_stats(lf_copy, inputCol, ["std", "mean"])
    lf = lf.join(stats_lf, how="cross")

    expr = (
        pl.when(pl.col("std") != 0)
        .then(((pl.col(inputCol).abs() - pl.col("mean")) / pl.col("std")).round(2))
        .otherwise(0)
    )

    lf = lf.with_columns(expr.alias(normalizedCol)).drop(["std", "mean"])

    return lf if use_lazy else lf.collect()


def calculate_percent_rank(
    df: pl.DataFrame | pl.LazyFrame,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    inputCol: str,
    normalizedCol: str,
    resultRow: int,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with ``normalizedCol`` computed as a percent rank."""

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf_copy = ensure_lazyframe(dfCopy)

    stats_lf = lazy_column_stats(lf_copy, inputCol, ["max", "min", "len"])
    lf = lf.join(stats_lf, how="cross")

    expr = (
        pl.when(((pl.col("max") - pl.col("min")) != 0) & (pl.col("len") > 0))
        .then(pl.col(inputCol).abs().rank("min") / pl.col("len"))
        .otherwise(0)
    )

    lf = lf.with_columns(expr.alias(normalizedCol)).drop(["max", "min", "len"])

    return lf if use_lazy else lf.collect()


def normalize_values(
    normalizedCols: list[str],
    inputCols: list[str],
    dfCopy: pl.DataFrame | pl.LazyFrame,
    paramDict: dict,
    resultRow: int,
) -> pl.DataFrame | pl.LazyFrame:
    """Normalize ``dfCopy`` and return an updated frame of the same type."""

    runParams = get_run_params()
    normalizeMean = runParams["normalizeMean"]
    namingParams = get_naming_params()
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    normalizedPercentName = namingParams["normalizedPercentName"]
    allZscore = namingParams["allZscore"]
    allRank = namingParams["allRank"]
    allMinMax = namingParams["allMinMax"]
    amountZscoreOtherMinMax = namingParams["amountZscoreOtherMinMax"]
    amountZscoreOtherRank = namingParams["amountZscoreOtherRank"]
    aggregationChoice = paramDict[namingParams["aggregationChoice"]]

    use_lazy = isinstance(dfCopy, pl.LazyFrame)
    lf = ensure_lazyframe(dfCopy)

    newAndLostVolumeDict = {True: 1, False: 0.5}

    for inputCol, normCol in zip(inputCols, normalizedCols):
        if aggregationChoice == allZscore:
            lf = calculate_normalized_mean(lf, dfCopy, inputCol, normCol, resultRow)
        elif aggregationChoice == allRank:
            lf = calculate_percent_rank(lf, dfCopy, inputCol, normCol, resultRow)
        elif aggregationChoice == allMinMax:
            lf = calculate_percent_rank(lf, dfCopy, inputCol, normCol, resultRow)
        elif aggregationChoice == amountZscoreOtherMinMax:
            if inputCol in [numberOfNodes, uniqueValuesInCombination]:
                lf = calculate_min_max(lf, dfCopy, inputCol, normCol)
            else:
                lf = calculate_normalized_mean(lf, dfCopy, inputCol, normCol, resultRow)
        elif aggregationChoice == amountZscoreOtherRank:
            if inputCol in [numberOfNodes, uniqueValuesInCombination]:
                lf = calculate_percent_rank(lf, dfCopy, inputCol, normCol, resultRow)
            else:
                lf = calculate_normalized_mean(lf, dfCopy, inputCol, normCol, resultRow)

        lf = lf.with_columns(pl.col(normCol).abs())
        lf = round_value_columns_to_dec(lf, [normCol])

    lf = lf.with_columns(
        pl.when(pl.col(normalizedPercentName).is_null())
        .then(newAndLostVolumeDict[normalizeMean])
        .otherwise(pl.col(normalizedPercentName))
        .alias(normalizedPercentName)
    )

    return lf if use_lazy else lf.collect()


def normalize_differences(
    df: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    paramDict: dict,
    count: int,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Normalize variance metrics and sort by the aggregated value."""
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    variancePercentChangeName = namingParams["variancePercentChangeName"]
    varianceAmountName = namingParams["varianceAmountName"]
    normalizedPercentName = namingParams["normalizedPercentName"]
    normalizedAmountName = namingParams["normalizedAmountName"]
    normalizeNumberOfNodesName = namingParams["normalizeNumberOfNodesName"]
    normalizedUniqueValuesInCombination = namingParams[
        "normalizedUniqueValuesInCombination"
    ]
    aggregatedNormalizedValue = namingParams["aggregatedNormalizedValue"]
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    alternativeResult = namingParams["alternativeResult"]
    randomKey = namingParams["randomKey"]
    normalizedCols = [
        normalizeNumberOfNodesName,
        normalizedUniqueValuesInCombination,
        normalizedAmountName,
        normalizedPercentName,
    ]
    inputCols = [
        numberOfNodes,
        uniqueValuesInCombination,
        varianceAmountName,
        variancePercentChangeName,
    ]
    df = normalize_values(normalizedCols, inputCols, df, paramDict, count)
    df = set_duplicate_rows_to_nan(df, normalizedCols)
    df, paramDict = aggregate_normalization_coefficients(df, paramDict, count)

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    lf = lf.sort(
        [
            pl.col(randomKey).is_not_null(),
            pl.col(aggregatedNormalizedValue)
            .fill_nan(float("-inf"))
            .fill_null(float("-inf")),
            pl.col(randomKey),
        ],
        descending=[True, True, False],
        nulls_last=True,
    )

    chosenRow = paramDict[alternativeResult] - 1
    if count == 1 and chosenRow != 0:
        lf = (
            lf.with_row_index("__idx")
            .filter(pl.col("__idx") >= chosenRow)
            .drop("__idx")
        )

    lf = lf.with_row_index("__idx").drop("__idx")

    return (lf if use_lazy else lf.collect()), paramDict


def aggregate_normalization_coefficients(
    df: pl.DataFrame | pl.LazyFrame,
    paramDict: dict,
    resultRow: int,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Compute and order the aggregated normalization coefficient."""
    namingParams = get_naming_params()
    normalizedPercent = namingParams["normalizedPercentName"]
    normalizedAmount = namingParams["normalizedAmountName"]
    normalizeNumberOfNodesName = namingParams["normalizeNumberOfNodesName"]
    normalizedUniqueValuesInCombination = namingParams[
        "normalizedUniqueValuesInCombination"
    ]
    aggregatedNormalizedValue = namingParams["aggregatedNormalizedValue"]
    varianceAmountWeight, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["varianceAmountWeight"], False
    )
    numberOfNodesWeight, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["numberOfNodesWeight"], False
    )
    uniqueValuesInCombinationWeight, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["uniqueValuesInCombinationWeight"], False
    )
    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    expr = (
        pl.col(normalizedPercent) * (1 - varianceAmountWeight)
        + pl.col(normalizedAmount) * varianceAmountWeight
    )
    if numberOfNodesWeight != 0:
        expr += pl.col(normalizeNumberOfNodesName) * numberOfNodesWeight
    if uniqueValuesInCombinationWeight != 0:
        expr += (
            pl.col(normalizedUniqueValuesInCombination)
            * uniqueValuesInCombinationWeight
        )

    lf = lf.with_columns(expr.alias(aggregatedNormalizedValue))
    lf = round_value_columns_to_dec(lf, [aggregatedNormalizedValue])
    lf = lf.sort(aggregatedNormalizedValue, descending=True)

    return (lf if use_lazy else lf.collect()), paramDict
