import copy
import logging
from functools import reduce
from itertools import combinations

import polars as pl

from modules.data.common_data_utils import (
    complete_combination_with_all_parents,
    delete_hierarchical_parents,
)
from modules.layout.layout_data import collect_lazyframe
from modules.layout.set_up_widgets import submit_variance_charts
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_run_params,
    get_variance_aggregation_params,
)
from modules.utilities.helpers import (
    add_status_message_to_paramDict,
    check_if_duplicates_in_all_columns,
    drop_columns,
    duplicate_dataframe,
    get_data_sample,
    group_by_df_on_index_cols,
    measure_time,
    move_to_end,
    round_value_columns_to_dec,
    take_filtered_value_out_of_option_list,
    unique,
)
from modules.utilities.ui_notifier import ui
from modules.utilities.utils import (
    ensure_polars_df,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

try:
    from modules.utilities.utils import ensure_lazyframe
except ImportError:  # pragma: no cover

    def ensure_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
        if isinstance(obj, pl.LazyFrame):
            return obj
        if isinstance(obj, pl.DataFrame):
            return obj.lazy()
        return pl.DataFrame(obj).lazy()


from modules.variance.variance_formulas import (
    calculate_margin_mix_variance,
    calculate_sales_mix_variance,
    calculate_variance_in_percent,
)
from modules.variance.variance_utils import (
    add_random_key,
    change_nan_to_all,
    divide_back_if_multiplied,
    filter_by_number_of_nodes,
    insert_dates,
    make_divideArray,
    recalculate_price,
)


def build_variance_calculation_array(aggregationsToPlot, chartDict):
    namingParams = get_naming_params()
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = namingParams["priceAndVolumeAggregation"]
    mixAndUnitsAggregation = namingParams["mixAndUnitsAggregation"]
    mixAndVolumeAggregation = namingParams["mixAndVolumeAggregation"]
    costsUnitsAggregation = namingParams["costsUnitsAggregation"]
    costsVolumeAggregation = namingParams["costsVolumeAggregation"]
    costsUnitsMixAggregation = namingParams["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = namingParams["costsVolumeMixAggregation"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = namingParams["marginVolumeRateAggregation"]
    varianceArray = []
    aggregationsToPlotDict = {
        totalVarianceAggregation: ["Price & units & mix"],
        priceAndUnitsAggregation: ["Price", "Units & mix"],
        priceAndVolumeAggregation: ["Price", "Volume & mix"],
        mixAndUnitsAggregation: ["Price", "Units", "Mix"],
        mixAndVolumeAggregation: ["Price", "Volume", "Mix"],
        costsUnitsAggregation: [
            "Price on margin",
            "Units & mix on margin",
            "Cost",
            "Indirect Costs",
            "Balance",
        ],
        costsVolumeAggregation: [
            "Price on margin",
            "Volume & mix on margin",
            "Cost",
            "Indirect Costs",
            "Balance",
        ],
        costsUnitsMixAggregation: [
            "Price on margin",
            "Units on margin",
            "Mix on margin",
            "Cost",
            "Indirect Costs",
            "Balance",
        ],
        costsVolumeMixAggregation: [
            "Price on margin",
            "Volume on margin",
            "Mix on margin",
            "Cost",
            "Indirect Costs",
            "Balance",
        ],
        marginUnitsRateAggregation: [
            "Price on margin",
            "Units & mix on margin",
            "Margin rate",
            "Indirect Costs",
            "Balance",
        ],
        marginVolumeRateAggregation: [
            "Price on margin",
            "Volume & mix on margin",
            "Margin rate",
            "Indirect Costs",
            "Balance",
        ],
    }
    for element in aggregationsToPlot:
        if element in aggregationsToPlotDict:
            for item in aggregationsToPlotDict[element]:
                if item not in varianceArray:
                    varianceArray.append(item)
    varianceArray = move_to_end(varianceArray, "Balance")
    varianceArray = insert_dates(chartDict, varianceArray)
    return varianceArray


def select_variance_aggregations_to_plot(chartDict):
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
    varianceAggregationOptionsArrayKey = namingParams["varianceAggregationOptionsArray"]
    varianceAggregationKey = namingParams["varianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = namingParams["marginVolumeRateAggregation"]
    costsUnitsAggregation = namingParams["costsUnitsAggregation"]
    costsVolumeAggregation = namingParams["costsVolumeAggregation"]
    costsUnitsMixAggregation = namingParams["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = namingParams["costsVolumeMixAggregation"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    discountsAndUnitsAggregation = namingParams["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = namingParams["discountsAndVolumeAggregation"]
    discountsAggregation = namingParams["discountsAggregation"]
    cogsAggregation = namingParams["cogsAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = namingParams["priceAndVolumeAggregation"]
    unitPriceOnSalesAggregation = namingParams["unitPriceOnSalesAggregation"]
    volumePriceOnSalesAggregation = namingParams["volumePriceOnSalesAggregation"]
    unitsOnSalesAggregation = namingParams["unitsOnSalesAggregation"]
    volumeOnSalesAggregation = namingParams["volumeOnSalesAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
    newAndLostUnitsAggregation = namingParams["newAndLostUnitsAggregation"]
    newAndLostVolumeAggregation = namingParams["newAndLostVolumeAggregation"]
    newAndLostUnitsMixAggregation = namingParams["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = namingParams["newAndLostVolumeMixAggregation"]
    mixAndUnitsAggregation = namingParams["mixAndUnitsAggregation"]
    mixAndVolumeAggregation = namingParams["mixAndVolumeAggregation"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    varianceDifferentCalculations = namingParams["varianceDifferentCalculations"]
    salesAggregationsToPlot = [
        totalVarianceAggregation,
        priceAndUnitsAggregation,
        priceAndVolumeAggregation,
        mixAndUnitsAggregation,
        mixAndVolumeAggregation,
    ]
    marginAggregationsToPlot = [
        marginUnitsRateAggregation,
        costsUnitsAggregation,
        costsVolumeAggregation,
        costsUnitsMixAggregation,
        costsVolumeMixAggregation,
    ]
    aggregationsToPlot = []
    cogsAggregation = notMetConditionValue
    chartDict[varianceDifferentCalculations] = notMetConditionValue
    if varianceAggregationOptionsArrayKey in chartDict:
        varianceAggregationOptionsArray = chartDict[varianceAggregationOptionsArrayKey]
    if varianceAggregationKey in chartDict:
        varianceAggregation = chartDict[varianceAggregationKey]
        if varianceAggregation in salesAggregationArray:
            for element in varianceAggregationOptionsArray:
                if element in salesAggregationsToPlot:
                    aggregationsToPlot.append(element)
        elif varianceAggregation in cogsAggregationArray:
            cogsAggregation = metConditionValue
            for element in varianceAggregationOptionsArray:
                if element in marginAggregationsToPlot:
                    aggregationsToPlot.append(element)
    if len(aggregationsToPlot) > 1:
        chartDict[varianceDifferentCalculations] = metConditionValue
        chartDict[varianceAggregationOptionsArrayKey] = aggregationsToPlot
        if cogsAggregation:
            if marginUnitsRateAggregation in aggregationsToPlot:
                chartDict[varianceAggregationKey] = marginUnitsRateAggregation
            elif marginVolumeRateAggregation in aggregationsToPlot:
                chartDict[varianceAggregationKey] = marginVolumeRateAggregation
    return aggregationsToPlot, chartDict


def prepare_config_for_variance_plot():
    namingParams = get_naming_params()
    configParams = get_config_params()
    waterfallChart = namingParams["verticalWaterfallChart"]
    configPlotlyDict = configParams["configPlotlyDict"]
    configPlotlyDict = configPlotlyDict[waterfallChart]
    return configPlotlyDict


def set_up_different_variance_calculations_chart(columnArray, paramDict, chartDict):
    bridgeSubmit, chartDict = submit_variance_charts(columnArray, paramDict, chartDict)
    aggregationsToPlot, chartDict = select_variance_aggregations_to_plot(chartDict)
    varianceArray = build_variance_calculation_array(aggregationsToPlot, chartDict)
    configPlotlyDict = prepare_config_for_variance_plot()
    return bridgeSubmit, chartDict, aggregationsToPlot, varianceArray, configPlotlyDict


def find_unique_node_chains(dfCopy, indexCols, paramDict):
    """Return unique node chains keeping the entry with the most nodes."""
    namingParams = get_naming_params()
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    dataPreparation = namingParams["dataPreparationName"]
    randomKey = namingParams["randomKey"]
    dfNodes = duplicate_dataframe(dfCopy)
    dfNodes, paramDict = group_by_df_on_index_cols(
        dfNodes,
        [randomKey],
        [numberOfNodes, uniqueValuesInCombination],
        "max",
        paramDict,
        False,
    )

    joincols = [randomKey, numberOfNodes, uniqueValuesInCombination]
    # We don't need to set or reset indexes in Polars.
    # Just select the necessary columns from dfCopy:
    # Make sure joincols are included so that the join works correctly.
    dfCopy = dfCopy.select(joincols + indexCols)
    lfCopy = dfCopy.lazy()

    # Perform the join on the specified join columns
    # Note: By default, Polars uses a hash join which doesn't require sorting.
    dfNodes = dfNodes.join(lfCopy, on=joincols, how="left")
    lfNodes = dfNodes.lazy()

    group_byCols = [randomKey, numberOfNodes, uniqueValuesInCombination]

    # First: forward fill within groups
    # Sort by group_byCols so that forward fill happens in a defined order
    dfNodes = lfNodes.sort(group_byCols).with_columns(
        [pl.col(c).fill_null(strategy="forward").over(group_byCols) for c in indexCols]
    )

    # Second: backward fill within the same groups
    # We do another sort to ensure the order is correct for backward filling
    dfNodes = lfNodes.sort(group_byCols).with_columns(
        [pl.col(c).fill_null(strategy="backward").over(group_byCols) for c in indexCols]
    )

    # Drop duplicates
    dfNodes = dfNodes.unique(maintain_order=True)

    # Finally, sort by randomKey (no set_index, just sort)
    dfNodes = dfNodes.sort(randomKey)

    return dfNodes, paramDict


def get_metric_values_for_each_random_key(dfCopy, valueCols, paramDict):
    """Aggregate metric columns for each unique random key."""
    namingParams = get_naming_params()
    randomKey = namingParams["randomKey"]
    dfMetrics = duplicate_dataframe(dfCopy)
    metricCols = copy.deepcopy(valueCols)
    metricCols = take_filtered_value_out_of_option_list(metricCols, randomKey)
    dfMetrics, paramDict = group_by_df_on_index_cols(
        dfMetrics, metricCols, [randomKey], "max", paramDict, False
    )
    dfMetrics = dfMetrics.sort(randomKey)
    if isinstance(dfCopy, pl.LazyFrame) and isinstance(dfMetrics, pl.DataFrame):
        dfMetrics = dfMetrics.lazy()
    return dfMetrics, metricCols, paramDict


def delete_duplicate_nodes(dfCopy, indexCols, valueCols, paramDict):
    """Remove duplicate chains and merge the corresponding metrics."""
    namingParams = get_naming_params()
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    deletedDuplicateNodes = namingParams["deletedDuplicateNodesName"]
    dataPreparation = namingParams["dataPreparationName"]
    findUniqueNodeChains = namingParams["findUniqueNodeChainsName"]
    getMetricValues = namingParams["getMetricValuesName"]
    randomKey = namingParams["randomKey"]
    dfMetrics, metricCols, paramDict = get_metric_values_for_each_random_key(
        dfCopy, valueCols, paramDict
    )
    measure_time(dataPreparation, getMetricValues, False)
    dfNodes, paramDict = find_unique_node_chains(dfCopy, indexCols, paramDict)
    measure_time(dataPreparation, findUniqueNodeChains, False)
    dfResult = dfNodes.join(dfMetrics, on=randomKey, how="left")
    # Fill nulls in metric columns using Polars expressions
    dfResult = dfResult.with_columns(
        [pl.col(c).fill_null(0).alias(c) for c in metricCols]
    )
    # No index semantics in Polars; reset_index is a no-op here
    paramDict = check_if_duplicates_in_all_columns(
        dfResult, "dfResult in delete duplicate rows", paramDict
    )
    dfResult = dfResult.unique(subset=indexCols, keep="first", maintain_order=True)
    measure_time(dataPreparation, deletedDuplicateNodes, False)
    return dfResult, paramDict


def process_index_combinations(dfCopy, resultArray, indexCols, valueCols, paramDict):
    """
    we want to filter out the rows that represent marginal part of total
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    runParams = get_run_params()
    includeBaseDataframe = runParams["includeBaseDataframe"]
    filterOutPercent = namingParams["filterOutPercent"]
    dataPreparation = namingParams["dataPreparationName"]
    appliedMultiIndexName = namingParams["appliedMultiIndexName"]
    processIndexCombinationName = namingParams["processIndexCombinationName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    dfCopy, valueCols = add_random_key(dfCopy, valueCols, False)
    use_lazy = isinstance(dfCopy, pl.LazyFrame)
    if use_lazy:
        frameArray = []
    elif includeBaseDataframe:
        frameArray = [dfCopy]
    else:
        frameArray = [dfCopy[0:0]]
    for indexCol in resultArray:
        df = duplicate_dataframe(dfCopy)
        if is_valid_lazyframe(df):
            df, paramDict = group_by_df_on_index_cols(
                df, indexCol, valueCols, "sum", paramDict, False
            )
            if is_valid_lazyframe(df):
                if use_lazy:
                    df = df.lazy() if isinstance(df, pl.DataFrame) else df
                frameArray.append(df)
    measure_time(dataPreparation, processIndexCombinationName, False)
    if len(frameArray) > 0:
        contains_lazy = any(isinstance(f, pl.LazyFrame) for f in frameArray)
        if contains_lazy:
            frameArray = [
                f.lazy() if isinstance(f, pl.DataFrame) else f for f in frameArray
            ]
            dfResult = pl.concat(frameArray, how="diagonal", parallel=False)
        else:
            dfResult = pl.concat(frameArray, how="diagonal")
        paramDict = check_if_duplicates_in_all_columns(
            dfResult, "Process index combinations", paramDict
        )
        dfResult = dfResult.unique(subset=indexCols, maintain_order=True)
        statusMessage = "collect but not cached"
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 0)
        if not use_lazy and isinstance(dfResult, pl.LazyFrame):
            dfResult = dfResult.collect()
        dfResult, paramDict = recalculate_price(dfResult, paramDict)
        measure_time(dataPreparation, appliedMultiIndexName, False)
    else:
        dfResult = pl.DataFrame() if not use_lazy else pl.DataFrame().lazy()
    return dfResult, paramDict


def get_index_combinations(indexCols, nodeDict, paramDict):
    """
    returns all combinations of lenghts up to a given number
    """
    namingParams = get_naming_params()
    maxIndexArrayLength = paramDict[namingParams["maxIndexArrayLength"]]
    arrayLength = len(indexCols)
    if arrayLength > maxIndexArrayLength:
        arrayLength = maxIndexArrayLength
    resultArray = []
    for x in range(1, arrayLength + 1):
        resultArray = get_combinations_of_given_length(
            indexCols, x, nodeDict, resultArray
        )
    resultArray.sort()
    return resultArray, paramDict


def get_combinations_of_given_length(indexCols, length, indexDict, resultArray):
    """
    return the combinations of indexes of a given length
    having taken out the non informative hierarchical nodes from each array
    we filter out array with the same element repeated
    """
    runParams = get_run_params()
    deleteHierarchicalParents = runParams["deleteHierarchicalParents"]
    comb = combinations(indexCols, length)
    for i in list(comb):
        array = list(i)
        if deleteHierarchicalParents:
            array = delete_hierarchical_parents(array, indexDict)
        else:
            array = complete_combination_with_all_parents(array, indexDict)
        if array not in resultArray:
            if len(array) > 0:
                if len(array) == 1 or (array.count(array[0]) != len(array)):
                    noDuplicates = unique(array)
                    if noDuplicates not in resultArray:
                        resultArray.append(noDuplicates)
    return resultArray


def process_variance_calculation(dfDict, paramDict, chartDict, indexCols):
    namingParams = get_naming_params()
    varianceAmount = namingParams["varianceAmountName"]
    dfBaseKey = namingParams["dfBaseName"]
    mainDimension = namingParams["mainDimension"]
    varianceType = namingParams["varianceTypeName"]
    dfBase = dfDict[dfBaseKey]
    # Use project helper to duplicate Polars DataFrame/LazyFrame
    df = duplicate_dataframe(dfBase)
    group_byCols = [varianceType]
    if mainDimension in chartDict and len(chartDict[mainDimension]) > 0:
        group_byCols = chartDict[mainDimension] + group_byCols
    paramDict = get_data_sample(df, "before_mix_fix_dimension", False, paramDict)
    df = calculate_sales_mix_variance(df, paramDict, chartDict, indexCols)
    df, paramDict = calculate_margin_mix_variance(df, paramDict, chartDict, indexCols)
    paramDict = get_data_sample(df, "after_mix_fix_dimension", False, paramDict)
    df, paramDict = melt_data_on_variance_cols(df, paramDict, chartDict, indexCols)
    paramDict = get_data_sample(df, "after_melt_fix_dimension", False, paramDict)
    sumCols = [varianceAmount]
    return df, dfBase, paramDict, sumCols, group_byCols


def drop_zero_variance_rows(
    dfCopy, paramDict, chartDict, *, as_lazy: bool = False
) -> pl.DataFrame | pl.LazyFrame:
    """
    if a row has zero variance we drop it since it creates issues with driver variance calculation
    """
    namingParams = get_naming_params()
    totalVariance = namingParams["totalVariance"]
    cogsVariance = namingParams["COGSVariance"]
    discountVariance = namingParams["discountVariance"]
    driverAndUnitsAggregation = namingParams["driverAndUnitsAggregation"]
    driverAndVolumeAggregation = namingParams["driverAndVolumeAggregation"]
    mixUnitsDriverAggregation = namingParams["mixUnitsDriverAggregation"]
    mixVolumeDriverAggregation = namingParams["mixVolumeDriverAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    if varianceAggregation in chartDict and chartDict[varianceAggregation] in [
        driverAndUnitsAggregation,
        driverAndVolumeAggregation,
        mixUnitsDriverAggregation,
        mixVolumeDriverAggregation,
    ]:
        input_is_lazy = isinstance(dfCopy, pl.LazyFrame)
        df = dfCopy.lazy() if not input_is_lazy else dfCopy
        columns, _ = get_schema_and_column_names(df)
        sum_cols = [
            c for c in [totalVariance, cogsVariance, discountVariance] if c in columns
        ]
        if sum_cols:
            df = df.filter(pl.sum_horizontal(sum_cols) != 0)
        if as_lazy or input_is_lazy:
            return df
        return df.collect()
    else:
        return ensure_lazyframe(dfCopy) if as_lazy else dfCopy


def exclude_outliers_from_mix_variance(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict
) -> pl.DataFrame | pl.LazyFrame:
    """
    Eliminate "extreme" prices from our mix variance calculation by excluding
    rows outside specified quantile thresholds. This version uses a lazy
    Polars pipeline.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    separatorString = namingParams["separatorString"]
    quantiles = namingParams["quantiles"]
    excludeOutliers = namingParams["excludeOutliers"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    workColumn = namingParams["workColumn"]

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    if excludeOutliers in paramDict and paramDict[excludeOutliers]:
        pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
        pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]

        # Convert percentages into decimal quantiles
        min_quantile = paramDict[quantiles] / 100
        max_quantile = (100 - paramDict[quantiles]) / 100

        # 1) Add the work column (row-wise mean of the two prices)
        lf = lf.with_columns(
            ((pl.col(pricePeriodZero) + pl.col(pricePeriodOne)) / 2).alias(workColumn)
        )

        # 2) Compute the actual numerical cutoff values by selecting them into a separate LazyFrame
        q = lf.select(
            [
                pl.col(workColumn).quantile(min_quantile).alias("q_min"),
                pl.col(workColumn).quantile(max_quantile).alias("q_max"),
            ]
        )
        # (No computation happens yet; it's still lazy.)

        # 3) Cross join these values back to filter by them
        lf = (
            lf.join(q, how="cross")
            .filter(pl.col(workColumn).is_between(pl.col("q_min"), pl.col("q_max")))
            .drop([workColumn, "q_min", "q_max"])
        )
    return lf if use_lazy else lf.collect()


def count_number_of_nodes_in_index(
    df: pl.DataFrame | pl.LazyFrame, indexCols: list[str]
) -> pl.DataFrame | pl.LazyFrame:
    """
    since we can have equivalent rows (that filter the same things and that have the same number values)
    to choose the one to show we need to count the number of nodes in each row
    """
    namingParams = get_naming_params()
    numberOfNodes = namingParams["numberOfNodes"]
    maxNodes = len(indexCols)

    null_count = pl.sum_horizontal(
        [pl.col(col).is_null().cast(pl.Int64) for col in indexCols]
    )
    expr = (maxNodes - null_count).alias(numberOfNodes)

    return df.with_columns(expr)


def count_number_of_items_per_combination(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict, indexCols: list[str]
) -> pl.DataFrame | pl.LazyFrame:
    """
    we want to weigh more the combinations where columns contains more unique items (example product article) than those than contain less (example high medium low)
    """
    namingParams = get_naming_params()
    uniqueValuesInColumnDict = namingParams["uniqueValuesInColumnDict"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]

    columns, _ = get_schema_and_column_names(df)
    weight_exprs = [
        pl.when(pl.col(col).is_null())
        .then(0)
        .otherwise(paramDict[uniqueValuesInColumnDict][col])
        for col in indexCols
        if col in columns and col in paramDict[uniqueValuesInColumnDict]
    ]

    combo_expr = pl.sum_horizontal(weight_exprs) if weight_exprs else pl.lit(0)
    df = df.with_columns(combo_expr.alias(uniqueValuesInCombination))
    df = df.with_row_index("_idx").drop("_idx")
    return df


def make_parent_key_df(dfCopy, nodeDict, paramDict):
    """
    we need to add back the parent information on
    all the groupedby and concatenated dataframe
    we pull the information about parents from the base dataframe
    extracting a df with no duplicates and only data dimension columns
    """
    runParams = get_run_params()
    deleteHierarchicalParents = runParams["deleteHierarchicalParents"]
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    hierarchicalCols = []
    if deleteHierarchicalParents:
        if hierarchicalName in nodeDict and len(nodeDict[hierarchicalName]) > 0:
            df = ensure_polars_df(duplicate_dataframe(dfCopy))
            for element in nodeDict[hierarchicalName]:
                array = list(nodeDict[hierarchicalName][element].keys())
                hierarchicalCols = hierarchicalCols + array
            hierarchicalCols = unique(hierarchicalCols)
            # Project only the hierarchical columns using Polars select
            df = ensure_polars_df(df.select(hierarchicalCols))
            paramDict = check_if_duplicates_in_all_columns(df, "dfParents", paramDict)
            df = df.unique(maintain_order=True)
        else:
            df = pl.DataFrame()
    else:
        df = pl.DataFrame()
    return df, paramDict


def fill_parent_info(df, dfParentsCopy, nodeDict, paramDict):
    """Populate missing hierarchical parents using ``dfParentsCopy``."""

    runParams = get_run_params()
    deleteHierarchicalParents = runParams["deleteHierarchicalParents"]
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]

    if deleteHierarchicalParents:
        df = ensure_polars_df(df)
        dfParentsCopy = ensure_polars_df(dfParentsCopy)

        pairs = [
            (rev[i], rev[i + 1])
            for element in nodeDict.get(hierarchicalName, {})
            for rev in [list(nodeDict[hierarchicalName][element].keys())[::-1]]
            for i in range(len(rev) - 1)
        ]

        lookups = [
            (
                child,
                parent,
                dfParentsCopy.select([child, parent]).unique(maintain_order=True),
            )
            for child, parent in pairs
        ]

        def join_lookup(acc_df, info):
            child, parent, lookup = info
            joined = acc_df.join(lookup, on=child, how="left", suffix="_parent")
            return joined.with_columns(
                pl.coalesce(pl.col(parent), pl.col(f"{parent}_parent")).alias(parent)
            ).drop(f"{parent}_parent")

        df = reduce(join_lookup, lookups, df)

        paramDict = check_if_duplicates_in_all_columns(
            df, "Fill parent info", paramDict
        )

    return df, paramDict


def get_and_process_index_combinations(df, indexCols, valueCols, nodeDict, paramDict):
    """
    grouping function together for order
    """
    namingParams = get_naming_params()
    dataPreparation = namingParams["dataPreparationName"]
    getIndexCombinations = namingParams["getIndexCombinationsName"]
    resultArray, paramDict = get_index_combinations(indexCols, nodeDict, paramDict)
    measure_time(dataPreparation, getIndexCombinations, False)
    df, paramDict = process_index_combinations(
        df, resultArray, indexCols, valueCols, paramDict
    )
    return df, paramDict


def make_df_copy_for_subtractions(dfCopy, indexCols, paramDict, chartDict):
    """
    while we need to identify equivalent node chains, so we do not get
    duplicate results, we need to keep these duplicate chains in the dataset
    because otherwise we would no do the correct subtractions where the
    subtraction joins is about the duplicate chains
    Here we create a copy
    If the dataframe is very big, we skip this step
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    numberOfColumnsWeight = configParams[namingParams["numberOfColumnsWeight"]]
    highEstimatorValue = configParams[namingParams["highEstimatorValue"]]
    estimator = (len(indexCols) - 1) * numberOfColumnsWeight * dfCopy.height
    simplifiedProcessing = namingParams["simplifiedProcessing"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if estimator < highEstimatorValue:
        paramDict[simplifiedProcessing] = notMetConditionValue
        df = duplicate_dataframe(dfCopy)
        df, paramDict = melt_data_on_variance_cols(df, paramDict, chartDict, indexCols)
        df, paramDict = change_nan_to_all(df, indexCols, paramDict)
    else:
        paramDict[simplifiedProcessing] = metConditionValue
        df = pl.DataFrame()
    return df, paramDict


def output_df_with_combinations(
    indexCols, nodeDict, df, valueCols, paramDict, chartDict
):
    """
    grouping function together for order
    """
    namingParams = get_naming_params()
    dataPreparation = namingParams["dataPreparationName"]
    makeParentKey = namingParams["makeParentKeyName"]
    fillParentInfo = namingParams["fillParentInfoName"]
    countNumberOfNodes = namingParams["countNumberOfNodesName"]
    countNumberOfNodesPerCombination = namingParams[
        "countNumberOfNodesPerCombinationName"
    ]
    makeCopyForSubtraction = namingParams["makeCopyForSubtractionName"]
    paramDict = get_data_sample(df, "output_df_with_combinations", False, paramDict)
    if len(indexCols) > 1 and paramDict[namingParams["numberOfPeriodsFound"]] > 1:
        dfParents, paramDict = make_parent_key_df(df, nodeDict, paramDict)
        measure_time(dataPreparation, makeParentKey, False)
        df, paramDictCopy = get_and_process_index_combinations(
            df, indexCols, valueCols, nodeDict, paramDict
        )
        paramDict = get_data_sample(
            df, "get_and_process_index_combinations", False, paramDict
        )
        df, paramDict = fill_parent_info(df, dfParents, nodeDict, paramDict)
        measure_time(dataPreparation, fillParentInfo, False)
        df = count_number_of_nodes_in_index(df, indexCols)
        measure_time(dataPreparation, countNumberOfNodes, False)
        df = count_number_of_items_per_combination(df, paramDict, indexCols)
        measure_time(dataPreparation, countNumberOfNodesPerCombination, False)
        dfSubtract, paramDict = make_df_copy_for_subtractions(
            df, indexCols, paramDict, chartDict
        )
        measure_time(dataPreparation, makeCopyForSubtraction, False)
    else:
        dfSubtract = pl.DataFrame()
    return df, dfSubtract, indexCols, paramDict


def output_combinations_and_melt_results(
    indexCols, nodeDict, df, valueCols, paramDict, chartDict
):
    """
    grouping function together for order
    """
    df, dfSubtract, indexCols, paramDict = output_df_with_combinations(
        indexCols, nodeDict, df, valueCols, paramDict, chartDict
    )
    if len(indexCols) > 1:
        paramDict = get_data_sample(
            df, "output_df_with_combinations_df", False, paramDict
        )
        paramDict = get_data_sample(
            df, "output_df_with_combinations_dfSubtract", False, paramDict
        )
        df, paramDict = delete_duplicate_nodes_and_melt_result(
            df, dfSubtract, indexCols, valueCols, paramDict, chartDict
        )
        df = filter_by_number_of_nodes(df, paramDict)
    return df, indexCols, paramDict


def merge_dataframe_with_subtraction_df(df, dfSubtract, indexCols, paramDict):
    """
    we need to add back the "duplicate" rows we took off because otherwise some
    subtractions will not work. We need to tag these duplicates so we do not
    get them as results. So we look for the combinations that are not in the main
    dataframe, tag them and add them back
    """
    namingParams = get_naming_params()
    randomKey = namingParams["randomKey"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    workColumn = namingParams["workColumn"]
    simplifiedProcessing = namingParams["simplifiedProcessing"]
    simplifiedProcessingMessage = namingParams["simplifiedProcessingMessage"]
    if isinstance(df, pl.LazyFrame):
        row_count = df.select(pl.len()).collect()[0, 0]
    elif isinstance(df, pl.DataFrame):
        row_count = df.height
    else:
        row_count = df.height
    statusMessage = (
        "Dataset has **"
        + str("{:,.0f}".format(row_count))
        + "** combinations among which the results will be drawn. "
    )
    paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 0)
    if paramDict[simplifiedProcessing]:
        paramDict = add_status_message_to_paramDict(
            paramDict, simplifiedProcessingMessage, 0
        )
    else:
        use_lazy = isinstance(df, pl.LazyFrame)
        df_base = ensure_lazyframe(df)
        dfFilter = df_base.select(indexCols).with_columns(
            pl.lit(metConditionValue).alias(workColumn)
        )
        dfSubtract = ensure_lazyframe(dfSubtract).join(
            dfFilter, on=indexCols, how="left"
        )
        dfSubtract = dfSubtract.filter(pl.col(workColumn) != metConditionValue)
        dfSubtract = drop_columns(dfSubtract, [workColumn])
        dfSubtract = dfSubtract.with_columns(pl.lit(0).alias(randomKey))
        # Use helper to retrieve column names consistently (avoids pandas-style APIs)
        columns, _ = get_schema_and_column_names(dfSubtract)
        columns = take_filtered_value_out_of_option_list(columns, randomKey)
        try:
            dfSubtract, paramDict = group_by_df_on_index_cols(
                dfSubtract, columns, [randomKey], "sum", paramDict, False
            )
            dfSubtract = dfSubtract.with_columns(pl.lit(None).alias(randomKey))
            target_schema = df_base.collect_schema()
            subtract_columns, _ = get_schema_and_column_names(dfSubtract)
            dfSubtract = dfSubtract.select(
                [
                    (
                        pl.col(column).cast(dtype, strict=False).alias(column)
                        if column in subtract_columns
                        else pl.lit(None, dtype=dtype).alias(column)
                    )
                    for column, dtype in target_schema.items()
                ]
            )
            df_base = pl.concat([df_base, dfSubtract], how="diagonal_relaxed")
            df = df_base if use_lazy else df_base.collect()
        except Exception as e:  # group_by may fail; fallback on simplified processing
            logging.exception(e)
            ui.error("Something went wrong with merge_dataframe_with_subtraction_df.")
            paramDict[simplifiedProcessing] = metConditionValue
            paramDict = add_status_message_to_paramDict(
                paramDict, simplifiedProcessingMessage, 7
            )
    return df, paramDict


def delete_duplicate_nodes_and_melt_result(
    df, dfSubtract, indexCols, valueCols, paramDict, chartDict
):
    """
    grouping function together for order
    """
    namingParams = get_naming_params()
    if len(indexCols) > 1 and paramDict[namingParams["numberOfPeriodsFound"]] > 1:
        df, paramDict = delete_duplicate_nodes(df, indexCols, valueCols, paramDict)
        paramDict = get_data_sample(df, "before_melt_without_mix", False, paramDict)
        df = calculate_sales_mix_variance(df, paramDict, chartDict, indexCols)
        df, paramDict = calculate_margin_mix_variance(
            df, paramDict, chartDict, indexCols
        )
        paramDict = get_data_sample(
            df, "with_mix_variance_calculation", False, paramDict
        )
        df, paramDict = melt_data_on_variance_cols(df, paramDict, chartDict, indexCols)
        paramDict = get_data_sample(df, "melt_data_on_variance_cols", False, paramDict)
        df, paramDict = change_nan_to_all(df, indexCols, paramDict)
        df, paramDict = merge_dataframe_with_subtraction_df(
            df, dfSubtract, indexCols, paramDict
        )
    return df, paramDict


def drop_not_required_variance_columns(df, toRemoveCols, valueNameArray):
    """
    based on the choice of the type of variance detail, we delete the useless columns
    """
    df = drop_columns(df, toRemoveCols)
    for column in toRemoveCols:
        if column in valueNameArray:
            valueNameArray = take_filtered_value_out_of_option_list(
                valueNameArray, column
            )
    return df, valueNameArray


def melt_data_on_variance_cols(df, paramDict, chartDict, indexCols):
    """
    using the "parents" df we want to populate the missing parent information in the
    core dataframe. We build a series of two column dictionaries and use them to map each parent column
    based on the info of the child
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixSalesAggregationArray = varianceAggregationParams[
        namingParams["mixSalesAggregationArray"]
    ]
    mixMarginAggregationArray = varianceAggregationParams[
        namingParams["mixMarginAggregationArray"]
    ]
    driverAggregationArray = varianceAggregationParams[
        namingParams["driverAggregationArray"]
    ]
    discountName = namingParams["discountName"]
    priceVariance = namingParams["priceVariance"]
    volumeVariance = namingParams["volumeVariance"]
    changedVolumeVariance = namingParams["changedVolumeVarianceMixName"]
    lostVolumeVariance = namingParams["lostVolumeVarianceName"]
    newVolumeVariance = namingParams["newVolumeVarianceName"]
    discountVariance = namingParams["discountVariance"]
    COGSVariance = namingParams["COGSVariance"]
    totalVariance = namingParams["totalVariance"]
    mixVariance = namingParams["mixVariance"]
    varianceStemArray = configParams["varianceStemArray"]
    varianceTypeName = namingParams["varianceTypeName"]
    varianceAmountName = namingParams["varianceAmountName"]
    simplifiedProcessing = namingParams["simplifiedProcessing"]
    varianceAggregation = namingParams["varianceAggregation"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = namingParams["priceAndVolumeAggregation"]
    unitPriceOnSalesAggregation = namingParams["unitPriceOnSalesAggregation"]
    volumePriceOnSalesAggregation = namingParams["volumePriceOnSalesAggregation"]
    unitsOnSalesAggregation = namingParams["unitsOnSalesAggregation"]
    volumeOnSalesAggregation = namingParams["volumeOnSalesAggregation"]
    newAndLostUnitsAggregation = namingParams["newAndLostUnitsAggregation"]
    newAndLostVolumeAggregation = namingParams["newAndLostVolumeAggregation"]
    newAndLostUnitsMixAggregation = namingParams["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = namingParams["newAndLostVolumeMixAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
    newAggregation = namingParams["newAggregation"]
    lostAggregation = namingParams["lostAggregation"]
    changedAggregation = namingParams["changedAggregation"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = namingParams["marginVolumeRateAggregation"]
    costsUnitsAggregation = namingParams["costsUnitsAggregation"]
    costsVolumeAggregation = namingParams["costsVolumeAggregation"]
    costsUnitsMixAggregation = namingParams["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = namingParams["costsVolumeMixAggregation"]
    discountsAndUnitsAggregation = namingParams["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = namingParams["discountsAndVolumeAggregation"]
    discountsAggregation = namingParams["discountsAggregation"]
    cogsAggregation = namingParams["cogsAggregation"]
    driverAndUnitsAggregation = namingParams["driverAndUnitsAggregation"]
    driverAndVolumeAggregation = namingParams["driverAndVolumeAggregation"]
    driverAggregation = namingParams["driverAggregation"]
    mixAggregation = namingParams["mixAggregation"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    netOfDiscountVariance = namingParams["netOfDiscountVariance"]
    marginVariance = namingParams["marginVariance"]
    percentSuffix = namingParams["percentSuffix"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    marginRateVariance = namingParams["marginRateVariance"]
    pureVolumeVariance = namingParams["pureVolumeVarianceName"]
    costVariance = namingParams["costVariance"]
    workColumn = namingParams["workColumn"]
    varianceInPercent = namingParams["varianceInPercent"]
    percentSuffix = namingParams["percentSuffix"]
    pureVolumeVarianceName = namingParams["pureVolumeVarianceName"]
    mixUnitsDriverAggregation = namingParams["mixUnitsDriverAggregation"]
    mixVolumeDriverAggregation = namingParams["mixVolumeDriverAggregation"]
    categoryWeightedDistributionName = namingParams["categoryWeightedDistributionName"]
    volumePerPosVariance = namingParams["volumePerPosVariance"]
    mixVolumePerPosVariance = namingParams["mixVolumePerPosVariance"]
    averageTicketVariance = namingParams["averageTicketVariance"]
    mixAverageTicketVariance = namingParams["mixAverageTicketVariance"]
    marginVariancePercent = marginVariance + percentSuffix
    netOfDiscountVariancePercent = netOfDiscountVariance + percentSuffix
    cogsVariancePercent = COGSVariance + percentSuffix
    volumeVariancePercent = volumeVariance + percentSuffix
    priceVariancePercent = priceVariance + percentSuffix
    costVariancePercent = costVariance + percentSuffix
    marginRateVariancePercent = marginRateVariance + percentSuffix
    percentAggregations = [
        marginVariancePercent,
        netOfDiscountVariancePercent,
        cogsVariancePercent,
        volumeVariancePercent,
        priceVariancePercent,
        costVariancePercent,
        marginRateVariancePercent,
    ]
    idVarArray = []
    valueNameArray = []
    columns, schema = get_schema_and_column_names(df)
    for column in columns:
        isVariance = False
        if column in varianceStemArray:
            isVariance = True
        if isVariance:
            if column not in valueNameArray:
                valueNameArray.append(column)
        # elif percentSuffix not in column:
        elif column not in idVarArray:
            idVarArray.append(column)
    toRemoveCols = []
    if (
        chartDict[varianceAggregation]
        in [
            priceAndUnitsAggregation,
            priceAndVolumeAggregation,
            newAndLostUnitsAggregation,
            newAndLostVolumeAggregation,
            newAndLostUnitsMixAggregation,
            newAndLostVolumeMixAggregation,
            newAggregation,
            lostAggregation,
            changedAggregation,
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
            driverAggregation,
            unitPriceOnSalesAggregation,
            volumePriceOnSalesAggregation,
            unitsOnSalesAggregation,
            volumeOnSalesAggregation,
        ]
        + mixSalesAggregationArray
    ):
        toRemoveCols = [
            totalVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
            costVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
        if chartDict[varianceAggregation] in [
            unitPriceOnSalesAggregation,
            volumePriceOnSalesAggregation,
        ]:
            toRemoveCols = [volumeVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [
            unitsOnSalesAggregation,
            volumeOnSalesAggregation,
        ]:
            toRemoveCols = [priceVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [newAggregation]:
            toRemoveCols = [priceVariance, lostVolumeVariance, changedVolumeVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [lostAggregation]:
            toRemoveCols = [priceVariance, newVolumeVariance, changedVolumeVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [changedAggregation]:
            toRemoveCols = [priceVariance, lostVolumeVariance, newVolumeVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [driverAggregation]:
            toRemoveCols = [priceVariance, volumeVariance] + mixSalesAggregationArray
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [mixAggregation]:
            toRemoveCols = [priceVariance, pureVolumeVariance] + driverAggregationArray
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [
            driverAndUnitsAggregation,
            driverAndVolumeAggregation,
        ]:
            if categoryWeightedDistributionName in columns:
                df = df.rename({volumeVariance: mixVolumePerPosVariance})
            else:
                df = df.rename({volumeVariance: mixAverageTicketVariance})
        elif chartDict[varianceAggregation] in [
            mixUnitsDriverAggregation,
            mixVolumeDriverAggregation,
        ]:
            if categoryWeightedDistributionName in columns:
                df = df.rename({pureVolumeVariance: volumePerPosVariance})
            else:
                df = df.rename({pureVolumeVariance: averageTicketVariance})
    elif chartDict[varianceAggregation] in [
        totalVarianceAggregation,
    ]:
        toRemoveCols = [
            priceVariance,
            volumeVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
            costVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif chartDict[varianceAggregation] in [
        discountsUnitsCogsAggregation,
        discountsVolumeCogsAggregation,
        discountsAggregation,
        cogsAggregation,
        unitPriceOnMarginAggregation,
        volumePriceOnMarginAggregation,
        unitsOnMarginAggregation,
        volumeOnMarginAggregation,
    ]:
        toRemoveCols = [
            totalVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            marginRateVariance,
            costVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
        if chartDict[varianceAggregation] in [discountsAggregation]:
            toRemoveCols = [priceVariance, volumeVariance, COGSVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [cogsAggregation]:
            toRemoveCols = [priceVariance, volumeVariance, discountVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [
            unitPriceOnMarginAggregation,
            volumePriceOnMarginAggregation,
        ]:
            toRemoveCols = [COGSVariance, volumeVariance, discountVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
        elif chartDict[varianceAggregation] in [
            unitsOnMarginAggregation,
            volumeOnMarginAggregation,
        ]:
            toRemoveCols = [priceVariance, COGSVariance, discountVariance]
            df, valueNameArray = drop_not_required_variance_columns(
                df, toRemoveCols, valueNameArray
            )
    elif chartDict[varianceAggregation] in [
        discountsAndUnitsAggregation,
        discountsAndVolumeAggregation,
    ]:
        toRemoveCols = [
            totalVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            COGSVariance,
            marginRateVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif chartDict[varianceAggregation] in [
        marginUnitsRateAggregation,
        marginVolumeRateAggregation,
    ]:
        toRemoveCols = [
            totalVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            discountVariance,
            COGSVariance,
            costVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif chartDict[varianceAggregation] in [
        costsUnitsAggregation,
        costsVolumeAggregation,
    ]:
        toRemoveCols = [
            totalVariance,
            lostVolumeVariance,
            newVolumeVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
            mixVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif chartDict[varianceAggregation] in [
        costsUnitsMixAggregation,
        costsVolumeMixAggregation,
    ]:
        toRemoveCols = [
            totalVariance,
            lostVolumeVariance,
            newVolumeVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
        ]
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif chartDict[varianceAggregation] in [marginVarianceAggregation]:
        if chartDict[varianceInPercent] != metConditionValue:
            present_cols = [
                c
                for c in [totalVariance, discountVariance, COGSVariance]
                if c in columns
            ]
            if present_cols:
                df = df.with_columns(
                    pl.sum_horizontal([pl.col(c) for c in present_cols]).alias(
                        marginVariance
                    )
                )
        elif chartDict[varianceInPercent] == metConditionValue:
            toRemoveCols = [netOfDiscountVariancePercent]
            df, paramDict = calculate_variance_in_percent(
                df, paramDict, chartDict, False
            )
        toRemoveCols = [
            totalVariance,
            priceVariance,
            volumeVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
            costVariance,
        ] + toRemoveCols
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    elif (
        chartDict[varianceAggregation] in [netOfDiscountAggregation]
        and discountName in columns
    ):
        if chartDict[varianceInPercent] != metConditionValue:
            df = df.with_columns(
                (pl.col(totalVariance) + pl.col(discountVariance)).alias(
                    netOfDiscountVariance
                )
            )
        toRemoveCols = [
            totalVariance,
            priceVariance,
            volumeVariance,
            lostVolumeVariance,
            newVolumeVariance,
            mixVariance,
            discountVariance,
            COGSVariance,
            marginRateVariance,
            costVariance,
        ] + toRemoveCols
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    if chartDict[varianceInPercent] != metConditionValue:
        toRemoveCols = percentAggregations
        df, valueNameArray = drop_not_required_variance_columns(
            df, toRemoveCols, valueNameArray
        )
    df = df.unpivot(
        index=idVarArray,
        variable_name=varianceTypeName,
        value_name=varianceAmountName,
    )
    df = df.sort(by=varianceAmountName, descending=True)
    if simplifiedProcessing in paramDict and paramDict[simplifiedProcessing]:
        df = ensure_polars_df(df)
        df = df.filter(pl.col(varianceAmountName) != 0)
    df = df.sort(by=varianceAmountName, descending=True)
    df = round_value_columns_to_dec(df, [varianceAmountName])
    divideArray = make_divideArray(df, indexCols)
    df, paramDict = divide_back_if_multiplied(
        df, paramDict, chartDict, divideArray, False
    )
    return df, paramDict


def calculate_aggregated_price_volume_variance_value(
    df, paramDict, periodsArray, columns, chartDict
):
    """
    if a discount columns exist, calculates the total variance after discount
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    amountName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    totalVariance = namingParams["totalVariance"]
    varianceName = namingParams["varianceName"]
    selectedPeriods = namingParams["selectedPeriods"]
    periodName = namingParams["periodName"]
    totalVarianceValueKey = namingParams["totalVarianceValue"]
    totalAmountPeriodZeroKey = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOneKey = namingParams["totalAmountPeriodOne"]
    avgAmountPeriodsZeroOneKey = namingParams["avgAmountPeriodsZeroOne"]
    varianceOnTotal = namingParams["varianceOnTotal"]
    yoyPercentChange = namingParams["yoyPercentChange"]
    nothingThereString = namingParams["nothingThereString"]
    firstPeriodSales = namingParams["firstPeriodSales"]
    secondPeriodSales = namingParams["secondPeriodSales"]
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]
    varianceSum, periodZeroSum = 0, 0
    periodOneSum, periodZeroOneAverage = 0, 0
    if amountPeriodZero in columns:
        periodZeroSum = df[amountPeriodZero].sum()
        periodOneSum = df[amountPeriodOne].sum()
        if totalVariance in columns:
            varianceSum = df[totalVariance].sum()
        else:
            varianceSum = periodOneSum - periodZeroSum
    else:
        periods = chartDict[selectedPeriods]
        df_temp = ensure_polars_df(df)
        periodZeroSum = df_temp.filter(pl.col(periodName) == periods[0])[
            amountName
        ].sum()
        periodOneSum = df_temp.filter(pl.col(periodName) == periods[1])[
            amountName
        ].sum()
        varianceSum = periodOneSum - periodZeroSum
    periodZeroOneAverage = (periodOneSum + periodZeroSum) / 2
    periodZeroSum, periodOneSum = round(periodZeroSum, 2), round(periodOneSum, 2)
    periodZeroOneAverage, varianceSum = (
        round(periodZeroOneAverage, 2),
        round(varianceSum, 2),
    )
    if paramDict[namingParams["isColumnMultiplied"]]:
        varianceSum = round(varianceSum / multiplyConstant, 2)
        periodZeroOneAverage = round(periodZeroOneAverage / multiplyConstant, 2)
        periodZeroSum = round(periodZeroSum / multiplyConstant, 2)
        periodOneSum = round(periodOneSum / multiplyConstant, 2)
    paramDict[totalVarianceValueKey], paramDict[totalAmountPeriodZeroKey] = (
        varianceSum,
        periodZeroSum,
    )
    paramDict[totalAmountPeriodOneKey], paramDict[avgAmountPeriodsZeroOneKey] = (
        periodOneSum,
        periodZeroOneAverage,
    )
    if abs(varianceSum) > 100:
        varianceValue = str("{:,.0f}".format(round(varianceSum, 0)))
    else:
        varianceValue = str("{:,.1f}".format(round(varianceSum, 1)))
    if periodZeroOneAverage != 0:
        varianceOnTotalValue = round((varianceSum / periodZeroOneAverage) * 100, 1)
        if periodZeroSum != 0:
            yoy_delta = (periodOneSum * 100 / periodZeroSum) - 100
            if abs(yoy_delta) > 100:
                yoyPercentChangeValue = str("{:,.0f}".format(round(yoy_delta, 0)))
            else:
                yoyPercentChangeValue = str("{:,.1f}".format(round(yoy_delta, 1)))
        else:
            yoyPercentChangeValue = nothingThereString
        statusMessage = [
            totalVarianceValueKey + " " + varianceName,
            varianceValue,
            yoyPercentChangeValue,
        ]
        statusMessage = check_if_reverse_KPI_color(
            paramDict, statusMessage, amountName, periodZeroSum, periodOneSum
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 3)
        paramDict[yoyPercentChange] = yoyPercentChangeValue
        paramDict[varianceOnTotal] = varianceOnTotalValue
        # paramDict[varianceOnTotal]=yoyPercentChangeValue # to adjust parameters we could use either the change on the average market size or the change as % on the two periods
    if abs(periodZeroSum) > 100:
        printValue = str("{:,.0f}".format(round(periodZeroSum, 0)))
    else:
        printValue = str("{:,.1f}".format(round(periodZeroSum, 1)))
    statusMessage = "1st period: **" + printValue + "**."
    paramDict[firstPeriodSales] = statusMessage
    paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 4)
    if abs(periodOneSum) > 100:
        printValue = str("{:,.0f}".format(round(periodOneSum, 0)))
    else:
        printValue = str("{:,.1f}".format(round(periodOneSum, 1)))
    statusMessage = " 2nd period: **" + printValue + "**."
    paramDict[secondPeriodSales] = statusMessage
    paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 4)
    return paramDict


def check_if_reverse_KPI_color(
    paramDict, statusMessage, metric, valuePeriodZero, valuePeriodOne
):
    """
    checks if the color of the % change value in the ui.metric widget must be reversed from red to green to green to red
    """
    namingParams = get_naming_params()
    colorChoice = namingParams["colorChoice"]
    redToGreen = namingParams["redToGreen"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    deltaColor = namingParams["deltaColor"]
    reverseColorMetricsArray = [discountName, indirectCostsName, cogsName]
    deltaColorValue = 1
    if valuePeriodZero < 0 and valuePeriodOne < 0:
        deltaColorValue = deltaColorValue * -1
    if colorChoice in paramDict and paramDict[colorChoice] not in [redToGreen]:
        deltaColorValue = deltaColorValue * -1
    if metric in reverseColorMetricsArray:
        deltaColorValue = deltaColorValue * -1
    if deltaColorValue == 1:
        deltaColor = "normal"
    else:
        deltaColor = "inverse"
    statusMessage.append(deltaColor)
    return statusMessage


def calculate_aggregated_discount_variance_value(df, paramDict, periodsArray, columns):
    """
    if a discount columns exist, calculates the total variance after discount
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    discountVariance = namingParams["discountVariance"]
    netOfDiscount = namingParams["netOfDiscountName"]
    varianceName = namingParams["varianceName"]
    separatorString = namingParams["separatorString"]
    netOfDiscountVarianceKey = namingParams["netOfDiscountVariance"]
    totalAmountPeriodZero = paramDict[namingParams["totalAmountPeriodZero"]]
    totalAmountPeriodOne = paramDict[namingParams["totalAmountPeriodOne"]]
    totalNetOfDiscountPeriodZero = namingParams["totalNetOfDiscountPeriodZero"]
    totalNetOfDiscountPeriodOne = namingParams["totalNetOfDiscountPeriodOne"]
    avgNetOfDiscountPeriodsZeroOne = namingParams["avgNetOfDiscountPeriodsZeroOne"]
    totalNetOfDiscountPeriodZeroinPercentKey = namingParams[
        "totalNetOfDiscountPeriodZeroinPercent"
    ]
    totalNetOfDiscountPeriodOneinPercentKey = namingParams[
        "totalNetOfDiscountPeriodOneinPercent"
    ]
    firstPeriodDiscountsKey = namingParams["firstPeriodDiscounts"]
    secondPeriodDiscountsKey = namingParams["secondPeriodDiscounts"]
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    if discountVariance in columns:
        netOfDiscountPeriodZero = netOfDiscount + separatorString + periodsArray[0]
        netOfDiscountPeriodOne = netOfDiscount + separatorString + periodsArray[1]
        periodZeroNetOfDiscountSum = df[netOfDiscountPeriodZero].sum()
        periodOneNetOfDiscountSum = df[netOfDiscountPeriodOne].sum()
        firstPeriodDiscounts = totalAmountPeriodZero - periodZeroNetOfDiscountSum
        secondPeriodDiscounts = totalAmountPeriodOne - periodOneNetOfDiscountSum
        firstPeriodDiscounts = str("{:,.0f}".format(round(firstPeriodDiscounts, 0)))
        secondPeriodDiscounts = str("{:,.0f}".format(round(secondPeriodDiscounts, 0)))
        paramDict[firstPeriodDiscountsKey] = (
            " 1st period: **" + firstPeriodDiscounts + "**."
        )
        paramDict[secondPeriodDiscountsKey] = (
            " 2nd period: **" + secondPeriodDiscounts + "**."
        )
        averageNetDiscounts = (
            periodZeroNetOfDiscountSum + periodOneNetOfDiscountSum
        ) / 2
        discountVarianceSum = periodOneNetOfDiscountSum - periodZeroNetOfDiscountSum
        periodOnePercentMarginAfterDiscount, periodZeroPercentMarginAfterDiscount = 0, 0
        if paramDict[namingParams["isColumnMultiplied"]]:
            discountVarianceSum = discountVarianceSum / multiplyConstant
            averageNetDiscounts = averageNetDiscounts / multiplyConstant
            periodZeroNetOfDiscountSum = periodZeroNetOfDiscountSum / multiplyConstant
            periodOneNetOfDiscountSum = periodOneNetOfDiscountSum / multiplyConstant
        paramDict[netOfDiscountVarianceKey] = discountVarianceSum
        paramDict[avgNetOfDiscountPeriodsZeroOne] = averageNetDiscounts
        if totalAmountPeriodZero != 0:
            periodZeroPercentMarginAfterDiscount = (
                periodZeroNetOfDiscountSum / totalAmountPeriodZero * 100
            )
            paramDict[totalNetOfDiscountPeriodZeroinPercentKey] = (
                periodZeroPercentMarginAfterDiscount
            )
        if totalAmountPeriodOne != 0:
            periodOnePercentMarginAfterDiscount = (
                periodOneNetOfDiscountSum / totalAmountPeriodOne * 100
            )
            paramDict[totalNetOfDiscountPeriodOneinPercentKey] = (
                periodOnePercentMarginAfterDiscount
            )
        percentMarginAfterdiscountUnitChange = (
            periodOnePercentMarginAfterDiscount - periodZeroPercentMarginAfterDiscount
        )
        paramDict[namingParams["percentVarianceAfterDiscounts"]] = (
            percentMarginAfterdiscountUnitChange
        )
        (
            paramDict[totalNetOfDiscountPeriodZero],
            paramDict[totalNetOfDiscountPeriodOne],
        ) = (periodZeroNetOfDiscountSum, periodOneNetOfDiscountSum)
        if abs(discountVarianceSum) > 100:
            discountVarianceValue = str("{:,.0f}".format(round(discountVarianceSum, 0)))
        else:
            discountVarianceValue = str("{:,.1f}".format(round(discountVarianceSum, 1)))
        statusMessage = (
            netOfDiscountVarianceKey + ": **" + discountVarianceValue + "**. "
        )
        if periodZeroNetOfDiscountSum != 0:
            yoyPercentChangeDelta = (
                periodOneNetOfDiscountSum * 100 / periodZeroNetOfDiscountSum
            ) - 100
            if abs(discountVarianceSum) > 100:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(yoyPercentChangeDelta, 1))
                )
            else:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(percentMarginAfterdiscountUnitChange, 1))
                )
        else:
            yoyPercentChangeValue = nothingThereString
        statusMessage = [
            netOfDiscountVarianceKey + " " + varianceName,
            discountVarianceValue,
            yoyPercentChangeValue,
        ]
        statusMessage = check_if_reverse_KPI_color(
            paramDict,
            statusMessage,
            netOfDiscountVarianceKey,
            periodZeroNetOfDiscountSum,
            periodOneNetOfDiscountSum,
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 5)
        if abs(discountVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodZeroNetOfDiscountSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodZeroNetOfDiscountSum, 1)))
        statusMessage1stA = "1st period after discount: **" + printValue + "**. "
        if abs(discountVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodOneNetOfDiscountSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodOneNetOfDiscountSum, 1)))
        statusMessage2ndA = "2nd period after discount: **" + printValue + "**. "
        if abs(discountVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterDiscount, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterDiscount, 1))
            )
        statusMessage1stB = (
            "1st period after discount as % of revenues: **" + printValue + "%**. "
        )
        if abs(discountVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterDiscount, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterDiscount, 1))
            )
        statusMessage2ndB = (
            "2nd period after discount as % of revenues: **" + printValue + "%**. "
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage1stA + " " + statusMessage1stB, 6
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage2ndA + " " + statusMessage2ndB, 6
        )
    return paramDict


def calculate_aggregated_cogs_variance_value(df, paramDict, periodsArray, columns):
    """
    if a discount columns exist, calculates the total variance after discount
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    COGSVariance = namingParams["COGSVariance"]
    varianceName = namingParams["varianceName"]
    marginName = namingParams["marginName"]
    marginVarianceKey = namingParams["marginVariance"]
    separatorString = namingParams["separatorString"]
    percentVarianceAfterCogs = namingParams["percentVarianceAfterCogs"]
    totalAmountPeriodZero = paramDict[namingParams["totalAmountPeriodZero"]]
    totalAmountPeriodOne = paramDict[namingParams["totalAmountPeriodOne"]]
    totalMarginPeriodZeroKey = namingParams["totalMarginPeriodZero"]
    totalMarginPeriodOneKey = namingParams["totalMarginPeriodOne"]
    totalMarginPeriodZeroinPercent = namingParams["totalMarginPeriodZeroinPercent"]
    totalMarginPeriodOneinPercent = namingParams["totalMarginPeriodOneinPercent"]
    firstPeriodMargin = namingParams["firstPeriodMargin"]
    secondPeriodMargin = namingParams["secondPeriodMargin"]
    firstPeriodDiscounts = namingParams["firstPeriodDiscounts"]
    secondPeriodDiscounts = namingParams["secondPeriodDiscounts"]
    avgMarginPeriodsZeroOne = namingParams["avgMarginPeriodsZeroOne"]
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    periodOnePercentMarginAfterCOGS, periodZeroPercentMarginAfterCOGS = 0, 0
    if COGSVariance in columns:
        marginZero = marginName + separatorString + periodsArray[0]
        marginOne = marginName + separatorString + periodsArray[1]
        periodZeroMarginSum = df[marginZero].sum()
        periodOneMarginSum = df[marginOne].sum()
        averageMargin = (periodZeroMarginSum + periodOneMarginSum) / 2
        marginVarianceSum = periodOneMarginSum - periodZeroMarginSum
        if paramDict[namingParams["isColumnMultiplied"]]:
            marginVarianceSum = marginVarianceSum / multiplyConstant
            averageMargin = averageMargin / multiplyConstant
            periodZeroMarginSum = periodZeroMarginSum / multiplyConstant
            periodOneMarginSum = periodOneMarginSum / multiplyConstant
        if totalAmountPeriodZero != 0:
            periodZeroPercentMarginAfterCOGS = (
                periodZeroMarginSum / totalAmountPeriodZero * 100
            )
            paramDict[totalMarginPeriodZeroinPercent] = periodZeroPercentMarginAfterCOGS
        if totalAmountPeriodOne != 0:
            periodOnePercentMarginAfterCOGS = (
                periodOneMarginSum / totalAmountPeriodOne * 100
            )
            paramDict[totalMarginPeriodOneinPercent] = periodOnePercentMarginAfterCOGS
        percentMarginAftercogsUnitChange = (
            periodOnePercentMarginAfterCOGS - periodZeroPercentMarginAfterCOGS
        )
        paramDict[percentVarianceAfterCogs] = percentMarginAftercogsUnitChange
        paramDict[marginVarianceKey] = marginVarianceSum
        paramDict[avgMarginPeriodsZeroOne] = averageMargin
        paramDict[totalMarginPeriodZeroKey], paramDict[totalMarginPeriodOneKey] = (
            periodZeroMarginSum,
            periodOneMarginSum,
        )
        if abs(marginVarianceSum) > 100:
            marginVarianceValue = str("{:,.0f}".format(round(marginVarianceSum, 0)))
        else:
            marginVarianceValue = str("{:,.1f}".format(round(marginVarianceSum, 1)))
        if periodZeroMarginSum != 0:
            yoyPercentChangeDelta = (
                periodOneMarginSum * 100 / periodZeroMarginSum
            ) - 100
            if abs(marginVarianceSum) > 100:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(yoyPercentChangeDelta, 1))
                )
            else:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(yoyPercentChangeDelta, 1))
                )
        else:
            yoyPercentChangeValue = nothingThereString
        statusMessage = [
            marginVarianceKey + " " + varianceName,
            marginVarianceValue,
            yoyPercentChangeValue,
        ]
        statusMessage = check_if_reverse_KPI_color(
            paramDict,
            statusMessage,
            marginName,
            periodZeroMarginSum,
            periodOneMarginSum,
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 3)
        if abs(marginVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodZeroMarginSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodZeroMarginSum, 1)))
        statusMessage1stA = "1st period margin: **" + printValue + "**."
        paramDict[firstPeriodMargin] = "1st period: **" + printValue + "**."
        if abs(marginVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterCOGS, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterCOGS, 1))
            )
        statusMessage1stB = (
            " 1st period margin as % of revenues: **" + printValue + "%**."
        )
        if abs(marginVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodOneMarginSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodOneMarginSum, 1)))
        statusMessage2ndA = " 2nd period margin: **" + printValue + "**. "
        paramDict[secondPeriodMargin] = " 2nd period: **" + printValue + "**. "
        if abs(marginVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterCOGS, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterCOGS, 1))
            )
        statusMessage2ndB = (
            " 2nd period margin as % of revenues: **" + printValue + "%**. "
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage1stA + " " + statusMessage1stB, 8
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage2ndA + " " + statusMessage2ndB, 8
        )
    return paramDict


def calculate_aggregated_indirect_cost_variance_value(
    df, paramDict, periodsArray, columns
):
    """
    if a discount columns exist, calculates the total variance after discount
    """
    namingParams = get_naming_params()
    separatorString = namingParams["separatorString"]
    varianceName = namingParams["varianceName"]
    totalAmountPeriodZero = paramDict[namingParams["totalAmountPeriodZero"]]
    totalAmountPeriodOne = paramDict[namingParams["totalAmountPeriodOne"]]
    indirectCostsColFound = namingParams["indirectCostsColFound"]
    netMarginName = namingParams["netMarginName"]
    netMarginVariance = namingParams["netMarginVariance"]
    indirectCostsVariance = namingParams["indirectCostsVariance"]
    percentVarianceAfterIndCosts = namingParams["percentVarianceAfterIndCosts"]
    indirectCostsName = namingParams["indirectCostsName"]
    totalNetMarginPeriodZeroKey = namingParams["totalNetMarginPeriodZero"]
    totalNetMarginPeriodOneKey = namingParams["totalNetMarginPeriodOne"]
    totalNetMarginPeriodZeroinPercent = namingParams[
        "totalNetMarginPeriodZeroinPercent"
    ]
    totalNetMarginPeriodOneinPercent = namingParams["totalNetMarginPeriodOneinPercent"]
    if indirectCostsColFound in paramDict and paramDict[indirectCostsColFound]:
        periodOnePercentMarginAfterIndCosts, periodZeroPercentMarginAfterIndCosts = 0, 0
        netMarginZero = netMarginName + separatorString + periodsArray[0]
        netMarginOne = netMarginName + separatorString + periodsArray[1]
        statusMessage = "No net margin value in dataframe"
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 3)
        indirectCostsZero = indirectCostsName + separatorString + periodsArray[0]
        indirectCostsOne = indirectCostsName + separatorString + periodsArray[1]
        periodZeroNetMarginSum = df[netMarginZero].sum()
        periodOneNetMarginSum = df[netMarginOne].sum()
        periodZeroIndirectCostsSum = df[indirectCostsZero].sum()
        periodOneIndirectCostsSum = df[indirectCostsOne].sum()
        netMarginVarianceSum = periodOneNetMarginSum - periodZeroNetMarginSum
        indirectCostsVarianceSum = (
            periodOneIndirectCostsSum - periodZeroIndirectCostsSum
        )
        paramDict[indirectCostsVariance] = indirectCostsVarianceSum
        if totalAmountPeriodZero != 0:
            periodZeroPercentMarginAfterIndCosts = (
                periodZeroNetMarginSum / totalAmountPeriodZero * 100
            )
            paramDict[totalNetMarginPeriodZeroinPercent] = (
                periodZeroPercentMarginAfterIndCosts
            )
        if totalAmountPeriodOne != 0:
            periodOnePercentMarginAfterIndCosts = (
                periodOneNetMarginSum / totalAmountPeriodOne * 100
            )
            paramDict[totalNetMarginPeriodOneinPercent] = (
                periodOnePercentMarginAfterIndCosts
            )
        percentMarginAfterIndCostsChange = (
            periodOnePercentMarginAfterIndCosts - periodZeroPercentMarginAfterIndCosts
        )
        paramDict[percentVarianceAfterIndCosts] = percentMarginAfterIndCostsChange
        paramDict[netMarginVariance] = netMarginVarianceSum
        (
            paramDict[totalNetMarginPeriodZeroKey],
            paramDict[totalNetMarginPeriodOneKey],
        ) = (periodZeroNetMarginSum, periodOneNetMarginSum)
        if abs(netMarginVarianceSum) > 100:
            netMarginVarianceValue = str(
                "{:,.0f}".format(round(netMarginVarianceSum, 0))
            )
        else:
            netMarginVarianceValue = str(
                "{:,.1f}".format(round(netMarginVarianceSum, 1))
            )
        if periodZeroNetMarginSum != 0:
            yoyPercentChangeDelta = (
                periodOneNetMarginSum * 100 / periodZeroNetMarginSum
            ) - 100
            if abs(netMarginVarianceSum) > 100:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(yoyPercentChangeDelta, 1))
                )
            else:
                yoyPercentChangeValue = str(
                    "{:,.1f}".format(round(yoyPercentChangeDelta, 1))
                )
        else:
            yoyPercentChangeValue = nothingThereString

        statusMessage = [
            netMarginVariance + " " + varianceName,
            netMarginVarianceValue,
            yoyPercentChangeValue,
        ]
        statusMessage = check_if_reverse_KPI_color(
            paramDict,
            statusMessage,
            netMarginName,
            periodZeroNetMarginSum,
            periodOneNetMarginSum,
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 3)
        if abs(netMarginVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodZeroNetMarginSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodZeroNetMarginSum, 1)))
        statusMessage1stA = "1st period after indirect costs: **" + printValue + "**. "
        if abs(netMarginVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterIndCosts, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodZeroPercentMarginAfterIndCosts, 1))
            )
        statusMessage1stB = (
            "1st period after indirect costs as % of revenues: **"
            + printValue
            + "%**. "
        )
        if abs(netMarginVarianceSum) > 100:
            printValue = str("{:,.0f}".format(round(periodOneNetMarginSum, 0)))
        else:
            printValue = str("{:,.1f}".format(round(periodOneNetMarginSum, 1)))
        statusMessage2ndA = "2nd period after indirect costs: **" + printValue + "**. "
        if abs(netMarginVarianceSum) > 100:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterIndCosts, 1))
            )
        else:
            printValue = str(
                "{:,.1f}".format(round(periodOnePercentMarginAfterIndCosts, 1))
            )
        statusMessage2ndB = (
            "2nd period after indirect costs as % of revenues: **"
            + printValue
            + "%**. "
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage1stA + " " + statusMessage1stB, 10
        )
        paramDict = add_status_message_to_paramDict(
            paramDict, statusMessage2ndA + " " + statusMessage2ndB, 10
        )
    return paramDict


def calculate_total_amounts(df, paramDict, chartDict):
    """
    we write the total variance amount to a variable, as well as the period totals
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    columns, schema = get_schema_and_column_names(df)
    paramDict = calculate_aggregated_price_volume_variance_value(
        df, paramDict, periodsArray, columns, chartDict
    )
    paramDict = calculate_aggregated_discount_variance_value(
        df, paramDict, periodsArray, columns
    )
    paramDict = calculate_aggregated_cogs_variance_value(
        df, paramDict, periodsArray, columns
    )
    paramDict = calculate_aggregated_indirect_cost_variance_value(
        df, paramDict, periodsArray, columns
    )
    return paramDict
