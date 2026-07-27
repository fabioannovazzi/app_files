# Use Polars for dataframe operations
import copy
import logging
from itertools import combinations, product

import polars as pl

from modules.layout.layout_data import (
    collect_all_periods,
    collect_base,
)
from modules.layout.memoization import (
    check_collect,
    session_memoize_check_params,
)
from modules.layout.set_up_widgets import download_merged_file
from modules.plan.plan_dataset import prepare_plan_dataset
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_run_params,
)
from modules.utilities.error_messages import (
    add_error_message_in_load_data_tab,
    add_info_message_in_load_data_tab,
    add_warning_message_in_load_data_tab,
)
from modules.utilities.helpers import (
    add_price_to_value_cols,
    add_status_message_to_paramDict,
    calculate_cogs_per_units_and_volume,
    calculate_discount_per_units_and_volume,
    calculate_unit_and_volume_price,
    check_if_duplicates_in_all_columns,
    drop_columns,
    drop_rows_with_negative_values,
    duplicate_dataframe,
    get_data_sample,
    get_dataset_specific_parameter,
    get_gross_margin_metrics_for_bubble,
    get_growth_metrics_for_bubble,
    group_by_df_on_index_cols,
    measure_time,
    pivot_lazy_periods,
    take_filtered_value_out_of_option_list,
    unique,
)
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui

# ``get_column_sum`` may not be present when importing in a patched test
# environment. Attempt a normal import first and provide a fallback
# implementation if it fails.
try:
    from modules.utilities.utils import (
        ensure_lazyframe,
        get_column_sum,
        get_schema_and_column_names,
        is_valid_lazyframe,
    )
except ImportError as e:  # pragma: no cover - used only when tests monkeypatch utils

    ui.write("variance index_handling import error:", e)

    from modules.utilities.utils import (
        ensure_lazyframe,
        get_schema_and_column_names,
        is_valid_lazyframe,
    )

    def get_column_sum(obj: pl.DataFrame | pl.LazyFrame, column: str) -> float:
        """Return the sum of ``column`` from ``obj`` using Polars."""

        lf = ensure_lazyframe(obj)
        return lf.select(pl.col(column).sum()).collect().item()


from modules.variance.variance_formulas import (
    calculate_variance,
    calculate_variance_in_percent,
)
from modules.variance.variance_orchestrator import (
    calculate_total_amounts,
    delete_duplicate_nodes_and_melt_result,
    drop_zero_variance_rows,
    exclude_outliers_from_mix_variance,
    output_df_with_combinations,
)
from modules.variance.variance_utils import (
    check_column_correlation_to_variance,
    filter_by_number_of_nodes,
    recalculate_price,
    remove_period_from_index,
    remove_scenario_from_index,
    rename_periods,
)


def drop_columns_with_lower_correlation(
    df, indexCols, valueCols, correlations, paramDict, dropCols
):
    """
    if the dataset has a number of columns superior to the limit, we drop the columns with lower correlation with
    the target metric. We want at least two index columns
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    droppedLowCorrelationCols = namingParams["droppedLowCorrelationCols"]
    dropLowCorrelationCols = namingParams["dropLowCorrelationCols"]
    indexColsCorr = []
    columns, schema = get_schema_and_column_names(df)
    # Default behaviour drops low-correlation columns unless explicitly disabled.
    drop_enabled = paramDict.get(dropLowCorrelationCols, True)
    if drop_enabled:
        # Protect known attribute dimensions from being dropped.
        try:
            protected = set(session_state.get("attr_dimension_columns") or [])
        except Exception:
            protected = set()
        for element in columns:
            if element in indexCols:
                if element in correlations and element not in indexColsCorr:
                    indexColsCorr.append(element)
                elif (
                    element != periodName
                    and element not in dropCols
                    and element not in protected
                ):
                    dropCols.append(element)
        if periodName not in indexColsCorr:
            indexColsCorr.append(periodName)
        df = drop_columns(df, dropCols)
        df, paramDict = group_by_df_on_index_cols(
            df, indexColsCorr, valueCols, "sum", paramDict, False
        )
        paramDict[droppedLowCorrelationCols] = dropCols
        return df, indexColsCorr, paramDict, dropCols
    else:
        dropCols = []
        paramDict[droppedLowCorrelationCols] = dropCols
        return df, indexCols, paramDict, dropCols


def rank_high_cardinality_columns(
    df: pl.DataFrame | pl.LazyFrame, column: str, paramDict: dict
) -> pl.DataFrame | pl.LazyFrame:
    """Rank ``column`` by value share and annotate high-cardinality members."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    rank = namingParams["rankName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    aggregateLowerValueItems = configParams[namingParams["aggregateLowerValueItems"]]

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    dfRank = (
        lf.group_by(column, maintain_order=True)
        .agg(pl.col(monetaryName).sum().alias(monetaryName))
        .with_columns(
            (pl.col(monetaryName).rank(method="average") / pl.len()).alias(rank)
        )
        .sort(rank)
        .filter(pl.col(rank) >= aggregateLowerValueItems)
        .drop(monetaryName)
        .with_columns(pl.lit(notMetConditionValue).alias(rank))
    )

    lf = lf.join(dfRank, on=column, how="left").with_columns(
        pl.col(rank).fill_null(metConditionValue)
    )

    return lf if use_lazy else lf.collect()


def find_high_cardinality_columns(nodeDict):
    """
    returns a dictionary with the high granularity columns and their parent if it
    exists, so that we do not loose hierarchy
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    notHierarchical = namingParams["notHierarchicalName"]
    hierarchical = namingParams["hierarchicalName"]
    highCardinalityNumberOfUniques = configParams[
        namingParams["highCardinalityNumberOfUniques"]
    ]
    cardinalityDict = {}
    if notHierarchical in nodeDict:
        for column in nodeDict[notHierarchical]:
            if nodeDict[notHierarchical][column] >= highCardinalityNumberOfUniques:
                cardinalityDict[column] = []  # has no children
    if hierarchical in nodeDict:
        for hierarchy in nodeDict[hierarchical]:
            parentsArray = []
            fatherArray = []
            count = 0
            for column in nodeDict[hierarchical][hierarchy]:
                parentsArray.append(column)
                if (
                    nodeDict[hierarchical][hierarchy][column]
                    >= highCardinalityNumberOfUniques
                ):
                    if (
                        column in cardinalityDict and count == 0
                    ):  # has been already identified and is parent
                        pass
                    elif (
                        column in cardinalityDict and count > 0
                    ):  # has been already identified and is child
                        if parentsArray[count - 1] not in cardinalityDict[column]:
                            cardinalityDict[column].append(parentsArray[count - 1])
                    elif column not in cardinalityDict and count == 0:
                        cardinalityDict[column] = []  # has is parent
                    elif (
                        column not in cardinalityDict and count > 0
                    ):  # has not yet been identified and has parents
                        cardinalityDict[column] = [parentsArray[count - 1]]
                count = count + 1
    return cardinalityDict


def aggregate_high_cardinality_columns(
    dfCopy, nodeDict, indexCols, valueCols, paramDict, chartDict
):
    """
    we identify the columns with high cardinality (more than X distinct elements) and
    then replace "other" for the string for the elements that represent low value and therefore
    can be aggregated. If these are children of a hierarchy, we add the father name to other
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    rank = namingParams["rankName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    highCardinalityFill = namingParams["highCardinalityFill"]
    newAndLostUnitsAggregation = namingParams["newAndLostUnitsAggregation"]
    newAndLostVolumeAggregation = namingParams["newAndLostVolumeAggregation"]
    newAndLostUnitsMixAggregation = namingParams["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = namingParams["newAndLostVolumeMixAggregation"]
    newAggregation = namingParams["newAggregation"]
    lostAggregation = namingParams["lostAggregation"]
    changedAggregation = namingParams["changedAggregation"]
    workColumn = namingParams["workColumn"]
    noVarianceAnalysis = namingParams["noVarianceAnalysis"]
    processingChoiceKey = namingParams["processingChoice"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    varianceAggregationChoice, chartDict = get_dataset_specific_parameter(
        chartDict, namingParams["varianceAggregation"], False
    )
    if processingChoiceKey not in chartDict:
        chartDict[processingChoiceKey] = notMetConditionValue

    processingChoiceValue = chartDict[processingChoiceKey]

    if processingChoiceValue not in [
        noVarianceAnalysis,
        runOneDimensionalAnalysis,
    ] and varianceAggregationChoice not in [
        newAndLostUnitsAggregation,
        newAndLostVolumeAggregation,
        newAndLostUnitsMixAggregation,
        newAndLostVolumeMixAggregation,
        newAggregation,
        lostAggregation,
        changedAggregation,
    ]:
        cardinalityDict = {}
        cardinalityDict = find_high_cardinality_columns(nodeDict)
        renameDict = {}
        toDrop = []
        df = duplicate_dataframe(dfCopy)
        columnOrder, _ = get_schema_and_column_names(df)
        df = df.lazy() if isinstance(df, pl.DataFrame) else df
        for column in cardinalityDict:
            df = rank_high_cardinality_columns(df, column, paramDict)
            workColumnName = f"{column}_{workColumn}"
            renameDict[workColumnName] = column
            toDrop.append(column)

            parents = cardinalityDict[column]
            if len(parents) == 0:
                met_expr = pl.lit(highCardinalityFill)
            else:
                met_expr = pl.concat_str(
                    [pl.lit(highCardinalityFill)]
                    + [pl.col(p).cast(pl.Utf8) for p in parents],
                    separator="_",
                )

            df = df.with_columns(
                pl.when(pl.col(rank) == notMetConditionValue)
                .then(pl.col(column).cast(pl.Utf8))
                .otherwise(met_expr)
                .alias(workColumnName)
            ).drop(rank)

        df = drop_columns(df, toDrop)
        df = df.rename(renameDict)
        df = df.select(columnOrder)
        df, paramDict = group_by_df_on_index_cols(
            df, indexCols, valueCols, "sum", paramDict, False
        )
        return df, chartDict, paramDict
    else:
        return dfCopy, chartDict, paramDict


def check_correlation_and_drop_low_impact_cols(
    df, indexCols, valueCols, paramDict, chartDict
):
    """
    analyses dataframe to identify hierarchies and index columns
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    numberOfPeriodsFound = namingParams["numberOfPeriodsFound"]
    varianceAggregation = namingParams["varianceAggregation"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountVariance = namingParams["netOfDiscountVariance"]
    highEstimatorValue = configParams[namingParams["highEstimatorValue"]]
    numberOfColumnsWeight = configParams[namingParams["numberOfColumnsWeight"]]
    changeName = namingParams["changeName"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    # Force correlation-based dropping OFF globally
    dropLowCorrelationColsName = namingParams["dropLowCorrelationCols"]
    paramDict[dropLowCorrelationColsName] = False
    return df, indexCols, paramDict
    dropCols = []
    estimator = (len(indexCols) - 1) * numberOfColumnsWeight
    dropColumns = True
    count = 0
    try:
        if varianceAggregation in chartDict:
            if (
                numberOfPeriodsFound in paramDict
                and paramDict[numberOfPeriodsFound] > 1
            ):
                correlations, paramDict = check_column_correlation_to_variance(
                    df, indexCols, paramDict, chartDict
                )
                if processingChoice in chartDict and chartDict[
                    processingChoice
                ] not in [runOneDimensionalAnalysis]:
                    if estimator > highEstimatorValue:
                        if paramDict[fileUploadDisabled] == metConditionValue:
                            dropColumns = True
                        if paramDict[
                            fileUploadDisabled
                        ] == notMetConditionValue and chartDict[
                            varianceAggregation
                        ] not in [
                            totalVarianceAggregation,
                            marginVarianceAggregation,
                            netOfDiscountVariance,
                        ]:
                            dropColumns = False
                        if dropColumns:
                            df, indexCols, paramDict, dropCols = (
                                drop_columns_with_lower_correlation(
                                    df,
                                    indexCols,
                                    valueCols,
                                    correlations,
                                    paramDict,
                                    dropCols,
                                )
                            )
                            estimator = (len(indexCols) - 1) * df.height
                            while estimator > highEstimatorValue:
                                if len(indexCols) == 3:
                                    break
                                else:
                                    correlations = correlations[:-1]
                                    df, indexCols, paramDict, dropCols = (
                                        drop_columns_with_lower_correlation(
                                            df,
                                            indexCols,
                                            valueCols,
                                            correlations,
                                            paramDict,
                                            dropCols,
                                        )
                                    )
                                    estimator = (len(indexCols) - 1) * df.height
                        else:
                            message = "Processing time might be long due to the file's complexity and large number of generated combinations."
                            paramDict = add_warning_message_in_load_data_tab(
                                paramDict, message
                            )
                            message = (
                                "With the chosen '"
                                + chartDict[varianceAggregation]
                                + "'   show variance option it is not possible to drop columns to enhance performance."
                            )
                            paramDict = add_info_message_in_load_data_tab(
                                paramDict, message
                            )
                            message = (
                                "If performance is too slow, you might want to change the   show variance option to '"
                                + totalVarianceAggregation
                                + "' or to '"
                                + marginVarianceAggregation
                                + "' to allow automatic column drop."
                            )
                            paramDict = add_info_message_in_load_data_tab(
                                paramDict, message
                            )

    except Exception as e:  # nosec B110
        logging.exception(e)
        message = "Something went wrong handling indexes."
        paramDict = add_error_message_in_load_data_tab(paramDict, message)
    return df, indexCols, paramDict


def map_hierarchy_between_column_pairs(
    colPairs, df: pl.LazyFrame | pl.DataFrame, paramDict
):
    """Return a mapping describing relationships between column pairs."""

    namingParams = get_naming_params()
    responseName = namingParams["responseName"]
    parentName = namingParams["parentName"]
    childName = namingParams["childName"]
    correspondingName = namingParams["correspondingName"]
    hierarchicalName = namingParams["hierarchicalName"]
    notHierarchicalName = namingParams["notHierarchicalName"]
    uniqueValuesCol0Name = namingParams["uniqueValuesCol0Name"]
    uniqueValuesCol1Name = namingParams["uniqueValuesCol1Name"]

    df_lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    columns, _ = get_schema_and_column_names(df_lf)

    calc_exprs = [
        ((pl.col(col1).n_unique().over(col0) > 1).any().alias(f"{col0}-{col1}"))
        for col0, col1 in product(columns, repeat=2)
        if col1 != col0
    ]
    calculations_lazy = df_lf.select(calc_exprs)
    uniques_lazy = df_lf.select(pl.all().n_unique())
    calculations, uniques = pl.collect_all([calculations_lazy, uniques_lazy])
    check_collect("WAA", "calculations", calculations)
    check_collect("XAA", "uniques", uniques)

    calc_melt = (
        calculations.unpivot(variable_name="pair", value_name="calc")
        .with_columns(
            pl.col("pair").str.split("-").list.get(0).alias("col0"),
            pl.col("pair").str.split("-").list.get(1).alias("col1"),
        )
        .drop("pair")
    )
    unique_melt = uniques.unpivot(variable_name="column", value_name="unique")

    pairs_df = pl.DataFrame(colPairs, schema=["col0", "col1"], orient="row")
    pairs_enriched = (
        pairs_df.join(
            unique_melt.rename({"column": "col0", "unique": uniqueValuesCol0Name}),
            on="col0",
        )
        .join(
            unique_melt.rename({"column": "col1", "unique": uniqueValuesCol1Name}),
            on="col1",
        )
        .join(calc_melt.rename({"calc": "calc_ab"}), on=["col0", "col1"])
        .join(
            calc_melt.rename({"col0": "col1", "col1": "col0", "calc": "calc_ba"}),
            on=["col0", "col1"],
        )
    )

    pairs_result = (
        pairs_enriched.lazy()
        .with_columns(
            pl.when(~pl.col("calc_ab") & ~pl.col("calc_ba"))
            .then(pl.lit(correspondingName))
            .when(pl.col("calc_ab") & pl.col("calc_ba"))
            .then(pl.lit(notHierarchicalName))
            .otherwise(pl.lit(hierarchicalName))
            .alias(responseName),
            pl.when(pl.col("calc_ab") & ~pl.col("calc_ba"))
            .then(pl.col("col0"))
            .when(~pl.col("calc_ab") & pl.col("calc_ba"))
            .then(pl.col("col1"))
            .otherwise(pl.lit(None))
            .alias(parentName),
            pl.when(pl.col("calc_ab") & ~pl.col("calc_ba"))
            .then(pl.col("col1"))
            .when(~pl.col("calc_ab") & pl.col("calc_ba"))
            .then(pl.col("col0"))
            .otherwise(pl.lit(None))
            .alias(childName),
        )
        .collect()
    )

    pairs_dicts = pairs_result.drop(["calc_ab", "calc_ba"]).to_dicts()
    return {
        (row["col0"], row["col1"]): {
            responseName: row[responseName],
            parentName: row[parentName],
            childName: row[childName],
            uniqueValuesCol0Name: row[uniqueValuesCol0Name],
            uniqueValuesCol1Name: row[uniqueValuesCol1Name],
        }
        for row in pairs_dicts
    }


def get_pairs(source: list[str]) -> list[tuple[str, str]]:
    """Return all unique pairs of elements from ``source``."""

    return list(combinations(source, 2))


def update_nodeDict(toDrop, nodeDict):
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    toDelete = []
    if hierarchicalName in nodeDict:
        for element in nodeDict[hierarchicalName]:
            for column in nodeDict[hierarchicalName][element]:
                if column in toDrop:
                    toDelete.append((element, column))
    for element in toDelete:
        del nodeDict[hierarchicalName][element[0]][element[1]]
    return nodeDict


@session_memoize_check_params(check_diff=True)
def map_column_hierarchy(df, indexColsCopy, paramDictCopy):
    """
    we try to identify columns that have corresponding siblings example EAN code and product name
    and that therefore are in double and we try to identify the hierarchies between columns
    """
    namingParams = get_naming_params()
    runParams = get_run_params()
    parentName = namingParams["parentName"]
    childName = namingParams["childName"]
    periodName = namingParams["periodName"]
    indexCols = copy.deepcopy(indexColsCopy)
    paramDict = copy.deepcopy(paramDictCopy)
    indexCols = take_filtered_value_out_of_option_list(indexCols, periodName)
    df = df.select(indexCols)
    colPairs = get_pairs(indexCols)
    responseDict = map_hierarchy_between_column_pairs(colPairs, df, paramDict)
    return responseDict


def update_nodeDict_and_map_columns(
    df, indexCols, valueCols, paramDict, chartDict, toDrop
):
    """
    grouping function together for order
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    columns, schema = get_schema_and_column_names(df)
    if (
        len(indexCols) > 1
        and periodName in columns
        and selectedPeriods in paramDict
        and len(paramDict[selectedPeriods]) >= 1
    ):
        indexCols, nodeDict, df, valueCols, paramDict = map_dataframe_columns(
            df, indexCols, valueCols, paramDict, chartDict
        )
        paramDict = get_data_sample(df, "map_dataframe_columns", False, paramDict)
        nodeDict = update_nodeDict(toDrop, nodeDict)
    else:
        nodeDict = {}
    return df, indexCols, nodeDict, valueCols, paramDict


def get_max_index_array_length(nodeDict, paramDict):
    """
    we want the maximun length of the array to be eqaul to the number of
    dimensions (excluding parents) and also lower or equal to a safety limit
    set in the configuration parameters. The number can also be set lower for a
    specific dataset
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    notHierarchical = namingParams["notHierarchicalName"]
    hierarchical = namingParams["hierarchicalName"]
    maxIndexArrayLengthConfig = configParams[namingParams["maxIndexArrayLength"]]
    maxIndexArrayLength, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["maxIndexArrayLength"], False
    )
    maxIndexArrayLength = min([maxIndexArrayLength, maxIndexArrayLengthConfig])
    numberOfNonParentNodes = len(nodeDict[notHierarchical]) + len(
        nodeDict[hierarchical]
    )
    if numberOfNonParentNodes <= maxIndexArrayLength:
        maxIndexArrayLength = numberOfNonParentNodes
    paramDict[namingParams["maxIndexArrayLength"]] = maxIndexArrayLength
    return paramDict


def get_right_side_element_of_index(nodeDict):
    """
    the column that has the largest cardinality (highest number of uniques)
    should represent the information at the highest level of granularity
    and therefore needs to be "at the right" of our index array. We order the hierarchical and non hierarchical blocs
    """
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    notHierarchicalName = namingParams["notHierarchicalName"]
    dictionary = {}
    rightSideElementInIndex = []
    if notHierarchicalName in nodeDict and len(nodeDict[notHierarchicalName]) > 0:
        maxNotHierarchicalUniques = max(nodeDict[notHierarchicalName].values())
    else:
        maxNotHierarchicalUniques = 0
    if hierarchicalName in nodeDict and len(nodeDict[hierarchicalName]) > 0:
        for element in nodeDict[hierarchicalName]:
            dictionary[element] = max(nodeDict[hierarchicalName][element].values())
        maxHierarchicalKey = max(dictionary, key=dictionary.get)
    elif hierarchicalName in nodeDict and len(nodeDict[hierarchicalName]) == 0:
        del nodeDict[hierarchicalName]
    if (
        len(dictionary) == 0
        or maxNotHierarchicalUniques > dictionary[maxHierarchicalKey]
    ):
        if notHierarchicalName in nodeDict:
            rightSideElementInIndex = list(nodeDict[notHierarchicalName].keys())
            del nodeDict[notHierarchicalName]
    else:
        rightSideElementInIndex = list(
            nodeDict[hierarchicalName][maxHierarchicalKey].keys()
        )
        if maxHierarchicalKey in nodeDict[hierarchicalName]:
            del nodeDict[hierarchicalName][maxHierarchicalKey]
    return rightSideElementInIndex, nodeDict


def build_base_index_combination(nodeDictCopy, indexCols):
    """
    we build the most granular index combination with all dimensions in the right order
    """
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    notHierarchicalName = namingParams["notHierarchicalName"]
    nodeDict = copy.deepcopy(nodeDictCopy)
    builtIndex = []
    while len(nodeDict) > 0:
        rightSideElementInIndex, nodeDict = get_right_side_element_of_index(nodeDict)
        builtIndex = rightSideElementInIndex + builtIndex
    indexCols, missingArray = check_no_column_missing(indexCols, builtIndex)
    indexCols = unique(indexCols)
    if len(missingArray) > 0:
        for element in missingArray:
            nodeDictCopy[notHierarchicalName][element] = 2
    return indexCols, nodeDictCopy


def check_no_column_missing(indexCols, builtIndex):
    """
    we check that all columns are in the index we built
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    infoIcon = namingParams["infoIcon"]
    missingArray = []
    for element in indexCols:
        if element not in builtIndex and element != periodName:
            missingArray.append(element)
    if len(missingArray) == 0:
        pass
        return builtIndex, missingArray
    else:
        pass
        # message=str(missingArray)+' present in original index columns but missing in built index was added back to built index. Should be fine 🙂'
        # ui.info(message, icon="infoIcon")
        return indexCols, missingArray


def delete_column_in_pairs_of_corresponding_columns(
    responseDictCopy, df, indexCols, paramDict
):
    """
    when we have pairs of corresponding columns, where each element of one column corresponds
    to a specific element of the other column (example product description and product code)
    we want to keep only one column and change the index accordingly
    we take out from the dictionary all pairs in which at least one element is a corresponding column
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    responseName = namingParams["responseName"]
    correspondingName = namingParams["correspondingName"]
    droppedLowCorrelationCols = namingParams["droppedLowCorrelationCols"]
    chosenCohortSuffix = namingParams["chosenCohortSuffix"]
    lostAndDroppedSuffix = namingParams["lostAndDroppedSuffix"]
    cutCorrelationNumber = configParams[namingParams["cutCorrelationNumber"]]
    correspondingPairArray = []
    correspondingElementArray = []
    deletedColumnInMatchingPair, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["deletedColumnInMatchingPair"], False
    )
    responseDict = copy.deepcopy(responseDictCopy)
    toDrop = []
    # Avoid deleting protected dimensions (attributes/UI-offered)
    try:
        protected = set(session_state.get("protected_dims") or [])
    except Exception:
        protected = set()
    for colPair in responseDict:
        if responseDict[colPair][responseName] == correspondingName:
            if colPair[deletedColumnInMatchingPair] in indexCols:
                if (
                    chosenCohortSuffix not in colPair[deletedColumnInMatchingPair]
                    and lostAndDroppedSuffix not in colPair[deletedColumnInMatchingPair]
                ):
                    if colPair[deletedColumnInMatchingPair] not in protected:
                        indexCols = take_filtered_value_out_of_option_list(
                            indexCols, colPair[deletedColumnInMatchingPair]
                        )
                        if colPair not in correspondingPairArray:
                            correspondingPairArray.append(colPair)
                        if (
                            colPair[deletedColumnInMatchingPair]
                            not in correspondingElementArray
                        ):
                            correspondingElementArray.append(
                                colPair[deletedColumnInMatchingPair]
                            )
                        toDrop.append(colPair[deletedColumnInMatchingPair])
    df = drop_columns(df, toDrop)
    for colPair in responseDict:
        if (
            colPair[0] in correspondingElementArray
            or colPair[1] in correspondingElementArray
        ):
            if colPair not in correspondingPairArray:
                correspondingPairArray.append(colPair)
    for colPair in correspondingPairArray:
        if colPair in responseDict:
            del responseDict[colPair]
    if len(toDrop) > 0:
        deletedCols = str(toDrop).replace("[", "").replace("]", "")
        statusMessage = "Deleted **" + deletedCols + "** duplicate column/s. "
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
    if (
        droppedLowCorrelationCols in paramDict
        and len(paramDict[droppedLowCorrelationCols]) > 0
    ):
        droppedCols = (
            str(paramDict[droppedLowCorrelationCols]).replace("[", "").replace("]", "")
        )
        statusMessage = (
            "Dropped **"
            + droppedCols
            + "** column/s with low correlation with variance to preserve performance. "
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
    return df, indexCols, responseDict, paramDict


def add_number_of_uniques_to_nodes(array, responsDict):
    """
    we want to add to the name of the node the number of uniques
    so we can use it to buld the indexes for analysis
    """
    namingParams = get_naming_params()
    uniqueValuesCol0Name = namingParams["uniqueValuesCol0Name"]
    uniqueValuesCol1Name = namingParams["uniqueValuesCol1Name"]
    nodeDict = {}
    for node in array:
        for pair in responsDict:
            if node == pair[0]:
                nodeDict[node] = responsDict[pair][uniqueValuesCol0Name]
                break
            if node == pair[1]:
                nodeDict[node] = responsDict[pair][uniqueValuesCol1Name]
                break
    return nodeDict


def get_not_hierarchical_nodes(responseDict, indexCols, nodeDict):
    """
    we build an array with all the non hierarchical tuples
    and take them out of the dictionary
    """
    namingParams = get_naming_params()
    responseName = namingParams["responseName"]
    hierarchicalName = namingParams["hierarchicalName"]
    notHierarchicalName = namingParams["notHierarchicalName"]
    notHierarchicalnodeArray = copy.deepcopy(indexCols)
    notHierarchicalPairsArray = []
    for colPair in responseDict:
        if responseDict[colPair][responseName] == hierarchicalName:
            for element in colPair:
                if element in notHierarchicalnodeArray:
                    notHierarchicalnodeArray = take_filtered_value_out_of_option_list(
                        notHierarchicalnodeArray, element
                    )
    for colPair in responseDict:
        if (
            colPair[0] in notHierarchicalnodeArray
            or colPair[1] in notHierarchicalnodeArray
        ):
            notHierarchicalPairsArray.append(colPair)
    notHierarchicalnodeDict = add_number_of_uniques_to_nodes(
        notHierarchicalnodeArray, responseDict
    )
    for colPair in notHierarchicalPairsArray:
        if colPair in responseDict:
            del responseDict[colPair]
    nodeDict[notHierarchicalName] = notHierarchicalnodeDict
    return nodeDict, responseDict


def find_child(initialNode, pairArray, responseDict):
    """
    starting from the an "first ancestor" node we
    find its direct son among the different descendants
    """
    namingParams = get_naming_params()
    uniqueValuesCol1Name = namingParams["uniqueValuesCol1Name"]
    uniqueValuesCol0Name = namingParams["uniqueValuesCol0Name"]
    hierarchicalName = namingParams["hierarchicalName"]
    parentName = namingParams["parentName"]
    responseName = namingParams["responseName"]
    univaluesDict = {0: uniqueValuesCol1Name, 1: uniqueValuesCol0Name}
    numberOfUnique = float("inf")
    child = None
    foundChildrenArray = []
    for colPair in responseDict:
        if responseDict[colPair][responseName] == hierarchicalName and (
            colPair in pairArray or colPair[::-1] in pairArray
        ):
            if (
                initialNode == colPair[0]
                and colPair[0] == responseDict[colPair][parentName]
            ):
                if numberOfUnique > responseDict[colPair][uniqueValuesCol1Name]:
                    numberOfUnique = responseDict[colPair][uniqueValuesCol1Name]
                    if colPair[1] not in foundChildrenArray:
                        child = colPair[1]
                        foundChildrenArray.append((colPair[0], child))
            elif (
                initialNode == colPair[1]
                and colPair[1] == responseDict[colPair][parentName]
            ):
                if numberOfUnique > responseDict[colPair][uniqueValuesCol0Name]:
                    numberOfUnique = responseDict[colPair][uniqueValuesCol0Name]
                    if colPair[0] not in foundChildrenArray:
                        child = colPair[0]
                        foundChildrenArray.append((colPair[1], child))
    return child, foundChildrenArray


def build_hierarchical_path(
    count, initialNodeArray, nodeDict, responseDict, parentChildArray
):
    """
    for each initial note, we start to the hierarchy. We look for its child
    once we have found the child, we look for the child of the child. If the same father has
    more than one child, we add new hierarchies
    """
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    for fatherNode in initialNodeArray:
        newArray = []
        nodeDict[hierarchicalName][count] = [fatherNode]
        while len(parentChildArray) > 0 and fatherNode:
            childNode, foundChildrenArray = find_child(
                fatherNode, parentChildArray, responseDict
            )
            if len(foundChildrenArray) == 0:
                break
            elif len(foundChildrenArray) == 1:
                nodeDict[hierarchicalName][count].append(childNode)
            else:
                countElements = 0
                for colPair in foundChildrenArray:
                    if countElements > 0:
                        count = count + 1
                        nodeDict[hierarchicalName][count] = [fatherNode]
                    nodeDict[hierarchicalName][count].append(colPair[1])
                    countElements = countElements + 1
            for colPair in parentChildArray:
                if colPair[0] != fatherNode and colPair not in newArray:
                    newArray.append(colPair)
                elif colPair[1] != fatherNode and colPair not in newArray:
                    newArray.append(colPair)
            parentChildArray = copy.deepcopy(newArray)
            fatherNode = childNode
        count = count + 1
    return count, nodeDict, parentChildArray


def find_initial_nodes(parentChildArray):
    """
    we need to find the initial nodes of the hierarchies
    """
    initialNodeArray = []
    for pair in parentChildArray:
        possibleInitialNode = pair[0]
        if possibleInitialNode not in initialNodeArray:
            isInitialNode = True
            for pair in parentChildArray:
                if possibleInitialNode == pair[1]:
                    isInitialNode = False
            if isInitialNode == True:
                initialNodeArray.append(possibleInitialNode)
    return initialNodeArray


def check_for_nodes_with_multiple_chidren(
    count, nodeDict, responseDict, parentChildArray
):
    """
    we need to check for missing brances tied to nodes with multiple direct children
    """
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    mappedHierarchicalNodesArray = []
    notMappedParentChildArray = []
    if hierarchicalName in nodeDict:
        for element in nodeDict[hierarchicalName]:
            for subElement in nodeDict[hierarchicalName][element]:
                if subElement not in mappedHierarchicalNodesArray:
                    mappedHierarchicalNodesArray.append(subElement)
    for pair in parentChildArray:
        if (
            pair[0] not in mappedHierarchicalNodesArray
            or pair[1] not in mappedHierarchicalNodesArray
        ):
            notMappedParentChildArray.append(pair)
    initialNodeArray = find_initial_nodes(notMappedParentChildArray)
    count, nodeDict, parentChildArray = build_hierarchical_path(
        count, initialNodeArray, nodeDict, responseDict, notMappedParentChildArray
    )
    return count, nodeDict, parentChildArray


def get_hierarchical_tuples(responseDict):
    """
    we build an array with all the hierarchical tuples
    """
    namingParams = get_naming_params()
    responseName = namingParams["responseName"]
    hierarchicalName = namingParams["hierarchicalName"]
    parentName = namingParams["parentName"]
    parentChildArray = []
    for colPair in responseDict:
        if responseDict[colPair][responseName] == hierarchicalName:
            if responseDict[colPair][parentName] != colPair[0]:
                colPair = colPair[::-1]
            if colPair not in parentChildArray:
                parentChildArray.append(colPair)
    return parentChildArray


def find_hierarchical_paths(responseDict, nodeDict):
    """
    we build the hierarchical paths in order to have correct indexCols
    """
    namingParams = get_naming_params()
    hierarchicalName = namingParams["hierarchicalName"]
    parentChildArray = get_hierarchical_tuples(responseDict)
    nodeDict[hierarchicalName] = {}
    initialNodeArray = find_initial_nodes(parentChildArray)
    count = 0
    count, nodeDict, parentChildArray = build_hierarchical_path(
        count, initialNodeArray, nodeDict, responseDict, parentChildArray
    )
    count, nodeDict, parentChildArray = check_for_nodes_with_multiple_chidren(
        count, nodeDict, responseDict, parentChildArray
    )
    if hierarchicalName in nodeDict:
        for element in nodeDict[hierarchicalName]:
            nodeDict[hierarchicalName][element] = add_number_of_uniques_to_nodes(
                nodeDict[hierarchicalName][element], responseDict
            )
    return nodeDict


def map_dataframe_columns(df, indexCols, valueCols, paramDict, chartDict):
    """
    analyses dataframe to identify hierarchies and index columns
    """
    namingParams = get_naming_params()
    correlationChecked = namingParams["correlationCheckedName"]
    hierarchyMapped = namingParams["hierarchyMappedName"]
    dataPreparation = namingParams["dataPreparationName"]
    correspondingColumnsDeleted = namingParams["correspondingColumnsDeletedName"]
    highCardinalityColsAggregated = namingParams["highCardinalityColsAggregatedName"]
    deleteCorrespondingColumns = namingParams["deleteCorrespondingColumnsName"]
    processedBaseIndexDataframe = namingParams["processedBaseIndexDataframeName"]
    droppedRowsWithNegativeValues = namingParams["droppedRowsWithNegativeValuesName"]
    droppedZeroVarianceRows = namingParams["droppedZeroVarianceRowsName"]
    builtIndexCombination = namingParams["builtIndexCombinationName"]
    processingChoice = namingParams["processingChoice"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    nodeDict = {}
    # Promote joined attribute columns (when present) and UI-offered plot dims to plotting dimensions.
    # This ensures aggregated plotting frames include the enriched attributes.
    try:
        class_df = session_state.get("attr_classification")
        mapping = session_state.get("attr_inference_result", {}) or {}
        forced_from_ui = session_state.get("plot_forced_dims") or []
        join_keys = [
            k
            for k in [
                mapping.get("product_column"),
                (session_state.get("attr_group_choice", (None, None)))[1],
            ]
            if k
        ]
        df_cols, df_schema = get_schema_and_column_names(df)

        def _resolve_column(name: str | None) -> str | None:
            if not name:
                return None
            if name in df_cols:
                return name
            lowered = name.strip().lower()
            for col in df_cols:
                if col.lower() == lowered:
                    return col
            return None

        attr_dims: list[str] = []
        ui_dims: list[str] = []

        if isinstance(class_df, pl.DataFrame):
            class_cols, _ = get_schema_and_column_names(class_df)
            candidate_attrs = [c for c in class_cols if c not in join_keys]
            for col in candidate_attrs:
                resolved = _resolve_column(col)
                if (
                    resolved
                    and resolved not in attr_dims
                    and df_schema.get(resolved) in (pl.Utf8, pl.Categorical)
                ):
                    attr_dims.append(resolved)

        for col in forced_from_ui:
            resolved = _resolve_column(col)
            if (
                resolved
                and resolved not in attr_dims
                and resolved not in ui_dims
                and df_schema.get(resolved) in (pl.Utf8, pl.Categorical)
            ):
                ui_dims.append(resolved)

        forced_dims: list[str] = [*attr_dims, *ui_dims]

        if forced_dims:
            for c in forced_dims:
                if c not in indexCols:
                    indexCols.append(c)
            logging.getLogger(__name__).debug(
                "map-cols: forced=%s final_indexCols=%s", forced_dims, indexCols
            )
            # Track protected dims to avoid pruning later
            if attr_dims:
                try:
                    prot = set(session_state.get("attr_dimension_columns") or [])
                    prot.update(attr_dims)
                    session_state["protected_dims"] = list(prot)
                except Exception:
                    pass
    except Exception:
        pass
    df, indexCols, paramDict = check_correlation_and_drop_low_impact_cols(
        df, indexCols, valueCols, paramDict, chartDict
    )
    measure_time(dataPreparation, correlationChecked, False)
    responseDict = map_column_hierarchy(df, indexCols, paramDict)
    measure_time(dataPreparation, hierarchyMapped, False)
    df, indexCols, responseDictFiltered, paramDict = (
        delete_column_in_pairs_of_corresponding_columns(
            responseDict, df, indexCols, paramDict
        )
    )
    measure_time(dataPreparation, deleteCorrespondingColumns, False)
    df, paramDict = group_by_df_on_index_cols(
        df, indexCols, valueCols, "sum", paramDict, False
    )
    measure_time(dataPreparation, correspondingColumnsDeleted, False)
    indexColsWithoutPeriod = remove_period_from_index(indexCols)
    indexColsWithoutPeriod = remove_scenario_from_index(indexColsWithoutPeriod)
    nodeDict, responseDictFiltered = get_not_hierarchical_nodes(
        responseDictFiltered, indexColsWithoutPeriod, nodeDict
    )
    nodeDict = find_hierarchical_paths(responseDictFiltered, nodeDict)
    indexColsWithoutPeriod, nodeDict = build_base_index_combination(
        nodeDict, indexColsWithoutPeriod
    )
    paramDict = get_max_index_array_length(nodeDict, paramDict)
    measure_time(dataPreparation, builtIndexCombination, False)
    try:
        df, chartDict, paramDict = aggregate_high_cardinality_columns(
            df, nodeDict, indexCols, valueCols, paramDict, chartDict
        )
        measure_time(dataPreparation, highCardinalityColsAggregated, False)
    except Exception as e:
        logging.exception(e)
        message = "issue with aggregate high cardinality columns"
        paramDict = add_warning_message_in_load_data_tab(paramDict, message)
    df = drop_rows_with_negative_values(df, valueCols, paramDict)
    measure_time(dataPreparation, droppedRowsWithNegativeValues, False)
    if paramDict[namingParams["numberOfPeriodsFound"]] > 1:
        df, valueCols, paramDict = process_base_index_dataframe(
            df, indexCols, paramDict, chartDict
        )
        paramDict = get_data_sample(
            df, "process_base_index_dataframe", False, paramDict
        )
        paramDict = calculate_total_amounts(df, paramDict, chartDict)
        paramDict = check_if_duplicates_in_all_columns(df, "Prepared Data", paramDict)
        df = drop_zero_variance_rows(df, paramDict, chartDict)
        measure_time(dataPreparation, droppedZeroVarianceRows, False)
    return indexColsWithoutPeriod, nodeDict, df, valueCols, paramDict


def process_base_index_dataframe(df, indexCols, paramDict, chartDict):
    """
    we need to calculate the metrics at the most granular form
    on a dataframe grouped by with the full index
    """
    namingParams = get_naming_params()
    dataPreparation = namingParams["dataPreparationName"]
    calculateVarianceOneDimension = namingParams["calculateVarianceOneDimensionName"]
    processedBaseIndexDataframe = namingParams["processedBaseIndexDataframeName"]
    periodName = namingParams["periodName"]
    if paramDict[namingParams["numberOfPeriodsFound"]] > 1:
        df, paramDict = rename_periods(df, paramDict, chartDict, True)
        df = df.sort(indexCols)
        discount_col_found = namingParams["discountColFound"]
        if not paramDict.get(discount_col_found, False):
            message = "Discount column not detected. Net sales after discount may be inaccurate."
            paramDict = add_warning_message_in_load_data_tab(paramDict, message)
        df, paramDict, colArray = calculate_unit_and_volume_price(df, paramDict, [])
        df, paramDict = calculate_discount_per_units_and_volume(df, paramDict)
        df, paramDict = calculate_cogs_per_units_and_volume(df, paramDict)
        df = pivot_lazy_periods(df, index_cols=indexCols, agg_func="sum")
        df = collect_base(df, indexCols, paramDict)
        paramDict = get_data_sample(df, "unstack_and_flatten", False, paramDict)
        measure_time(dataPreparation, "collect polars base", False)
        df, paramDict = calculate_variance(df, paramDict, chartDict)
        paramDict = get_data_sample(df, "calculate_variance", False, paramDict)
        paramDict = check_if_duplicates_in_all_columns(
            df, "df process base index dataframe", paramDict
        )
        df = df.unique(maintain_order=True)
    columns, schema = get_schema_and_column_names(df)
    valueCols = []
    for column in columns:
        if column not in indexCols:
            valueCols.append(column)
    measure_time(dataPreparation, calculateVarianceOneDimension, False)
    return df, valueCols, paramDict


def make_intersection_df(df, dfDates, dfPeriods, dfAllPeriods, chartDict):
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    isLikeForLike = namingParams["isLikeForLike"]
    metConditionValue = namingParams["metConditionValue"]
    likeForLike = namingParams["likeForLikeName"]
    countMetricsSumDict = namingParams["countMetricsSumDict"]
    likeForLikeScope = namingParams["likeForLikeScope"]
    likeForLikeAll = namingParams["likeForLikeAll"]

    if likeForLike in chartDict and chartDict[likeForLike]:
        if (
            likeForLikeScope in chartDict
            and chartDict[likeForLikeScope] == likeForLikeAll
            and is_valid_lazyframe(dfAllPeriods)
        ):
            dfLikeForLikePeriod = dfAllPeriods
        else:
            dfLikeForLikePeriod = dfPeriods

        if countMetricsSumDict in chartDict and chartDict[countMetricsSumDict]:
            colKey = next(iter(chartDict[countMetricsSumDict]))
            column = chartDict[countMetricsSumDict][colKey]

            lf = (
                dfLikeForLikePeriod.lazy()
                if isinstance(dfLikeForLikePeriod, pl.DataFrame)
                else dfLikeForLikePeriod
            )
            num_periods = lf.select(pl.col(periodName).n_unique()).collect().item()

            lf_intersect = (
                lf.select(column, periodName)
                .unique(maintain_order=True)
                .group_by(column, maintain_order=True)
                .agg(pl.col(periodName).n_unique().alias("_n"))
                .filter(pl.col("_n") == num_periods)
                .select(column)
                .sort(column)
            )

            def _right_join(
                base: pl.DataFrame | pl.LazyFrame, other: pl.DataFrame | pl.LazyFrame
            ):
                if isinstance(base, pl.LazyFrame):
                    other_lf = (
                        other if isinstance(other, pl.LazyFrame) else other.lazy()
                    )
                    return base.join(other_lf, on=column, how="right")
                other_df = other.collect() if isinstance(other, pl.LazyFrame) else other
                return base.join(other_df, on=column, how="right")

            if is_valid_lazyframe(df):
                df = _right_join(df, lf_intersect)
            if is_valid_lazyframe(dfDates):
                dfDates = _right_join(dfDates, lf_intersect)
            if is_valid_lazyframe(dfPeriods):
                dfPeriods = _right_join(dfPeriods, lf_intersect)
            if is_valid_lazyframe(dfAllPeriods):
                dfAllPeriods = _right_join(dfAllPeriods, lf_intersect)

            chartDict[isLikeForLike] = metConditionValue

    return df, dfDates, dfPeriods, dfAllPeriods, chartDict


def calculate_aggregate_values(df, showError, paramDict, chartDict):
    """
    If filtering returns empty dataset we go back to original
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    amountName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    rank = namingParams["rankName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    filterOptionNumberName = namingParams["monetaryLocalCurrencyName"]
    totalVarianceValueKey = namingParams["totalVarianceValue"]
    timeColArray = [dateName, periodName]
    periodsArray = configParams["periodsArray"]
    avgAmountPeriodsZeroOneKey = namingParams["avgAmountPeriodsZeroOne"]
    indirectCostsColFound = namingParams["indirectCostsColFound"]
    indirectCostsName = namingParams["indirectCostsName"]
    indirectCostsVarianceKey = namingParams["indirectCostsVariance"]
    COGSVariance = namingParams["COGSVariance"]
    marginName = namingParams["marginName"]
    netMarginName = namingParams["netMarginName"]
    marginVarianceKey = namingParams["marginVariance"]
    percentVarianceAfterCogs = namingParams["percentVarianceAfterCogs"]
    percentVarianceAfterIndCosts = namingParams["percentVarianceAfterIndCosts"]
    percentVarianceAfterDiscountsKey = namingParams["percentVarianceAfterDiscounts"]
    varianceInPercent = namingParams["varianceInPercent"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    totalAmountPeriodZeroKey = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOneKey = namingParams["totalAmountPeriodOne"]
    totalAmountPeriodZeroFilteredKey = namingParams["totalAmountPeriodZeroFiltered"]
    totalAmountPeriodOneFilteredKey = namingParams["totalAmountPeriodOneFiltered"]
    totalMarginPeriodZeroFilteredKey = namingParams["totalMarginPeriodZeroFiltered"]
    totalMarginPeriodOneFilteredKey = namingParams["totalMarginPeriodOneFiltered"]
    totalMarginPeriodZeroinPercentFilteredKey = namingParams[
        "totalMarginPeriodZeroinPercentFiltered"
    ]
    totalMarginPeriodOneinPercentFilteredKey = namingParams[
        "totalMarginPeriodOneinPercentFiltered"
    ]
    totalNetMarginPeriodZeroFilteredKey = namingParams[
        "totalNetMarginPeriodZeroFiltered"
    ]
    totalNetMarginPeriodOneFilteredKey = namingParams["totalNetMarginPeriodOneFiltered"]
    totalNetMarginPeriodZeroinPercentFilteredKey = namingParams[
        "totalNetMarginPeriodZeroinPercentFiltered"
    ]
    totalNetMarginPeriodOneinPercentFilteredKey = namingParams[
        "totalNetMarginPeriodOneinPercentFiltered"
    ]
    totalNetOfDiscountPeriodZeroFilteredKey = namingParams[
        "totalNetOfDiscountPeriodZeroFiltered"
    ]
    totalNetOfDiscountPeriodOneFilteredKey = namingParams[
        "totalNetOfDiscountPeriodOneFiltered"
    ]
    totalNetOfDiscountPeriodZeroinPercentFilteredKey = namingParams[
        "totalNetOfDiscountPeriodZeroinPercentFiltered"
    ]
    totalNetOfDiscountPeriodOneinPercentFilteredKey = namingParams[
        "totalNetOfDiscountPeriodOneinPercentFiltered"
    ]
    netOfDiscountVarianceKey = namingParams["netOfDiscountVariance"]
    discountColFound = namingParams["discountColFound"]
    netOfDiscount = namingParams["netOfDiscountName"]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    isFilteredKey = namingParams["isFilteredKey"]
    isFiltered = notMetConditionValue
    if isFilteredKey in paramDict and paramDict[isFilteredKey]:
        isFiltered = metConditionValue
    if is_valid_lazyframe(df):
        if totalAmountPeriodZeroKey in paramDict:
            totalAmountPeriodZero = paramDict[totalAmountPeriodZeroKey]
            totalAmountPeriodOne = paramDict[totalAmountPeriodOneKey]
            if isFiltered and showError:
                periodZeroSum = get_column_sum(df, amountPeriodZero)
                periodOneSum = get_column_sum(df, amountPeriodOne)
                varianceSum = periodOneSum - periodZeroSum
                if paramDict[namingParams["isColumnMultiplied"]]:
                    varianceSum = varianceSum / multiplyConstant
                    if totalAmountPeriodZero != 0:
                        periodZeroSum = periodZeroSum / multiplyConstant
                    if totalAmountPeriodOne != 0:
                        periodOneSum = periodOneSum / multiplyConstant
                periodZeroOneAverage = (periodOneSum + periodZeroSum) / 2
                (
                    paramDict[totalVarianceValueKey],
                    paramDict[avgAmountPeriodsZeroOneKey],
                ) = (varianceSum, periodZeroOneAverage)
                (
                    paramDict[totalAmountPeriodZeroFilteredKey],
                    paramDict[totalAmountPeriodOneFilteredKey],
                ) = (periodZeroSum, periodOneSum)
                columns, schema = get_schema_and_column_names(df)
                if COGSVariance in columns:
                    marginZero = marginName + separatorString + periodsArray[0]
                    marginOne = marginName + separatorString + periodsArray[1]
                    periodZeroMarginSum = get_column_sum(df, marginZero)
                    periodOneMarginSum = get_column_sum(df, marginOne)
                    marginVarianceSum = periodOneMarginSum - periodZeroMarginSum
                    if paramDict[namingParams["isColumnMultiplied"]]:
                        marginVarianceSum = marginVarianceSum / multiplyConstant
                        if totalAmountPeriodZero != 0:
                            periodZeroMarginSum = periodZeroMarginSum / multiplyConstant
                        if totalAmountPeriodOne != 0:
                            periodOneMarginSum = periodOneMarginSum / multiplyConstant
                    if totalAmountPeriodZero != 0:
                        periodZeroPercentMarginAfterCOGS = (
                            periodZeroMarginSum / periodZeroSum * 100
                        )
                    if totalAmountPeriodOne != 0:
                        periodOnePercentMarginAfterCOGS = (
                            periodOneMarginSum / periodOneSum * 100
                        )
                    percentMarginAftercogsUnitChange = (
                        periodOnePercentMarginAfterCOGS
                        - periodZeroPercentMarginAfterCOGS
                    )
                    (
                        paramDict[totalMarginPeriodZeroFilteredKey],
                        paramDict[totalMarginPeriodOneFilteredKey],
                    ) = (periodZeroMarginSum, periodOneMarginSum)
                    paramDict[totalMarginPeriodZeroinPercentFilteredKey] = (
                        periodZeroPercentMarginAfterCOGS
                    )
                    paramDict[totalMarginPeriodOneinPercentFilteredKey] = (
                        periodOnePercentMarginAfterCOGS
                    )
                    paramDict[percentVarianceAfterCogs] = (
                        percentMarginAftercogsUnitChange
                    )
                    paramDict[marginVarianceKey] = marginVarianceSum
                if (
                    indirectCostsColFound in paramDict
                    and paramDict[indirectCostsColFound]
                ):
                    netMarginZero = netMarginName + separatorString + periodsArray[0]
                    netMarginOne = netMarginName + separatorString + periodsArray[1]
                    indirectCostsZero = (
                        indirectCostsName + separatorString + periodsArray[0]
                    )
                    indirectCostsOne = (
                        indirectCostsName + separatorString + periodsArray[1]
                    )
                    periodZeroNetMarginSum = get_column_sum(df, netMarginZero)
                    periodOneNetMarginSum = get_column_sum(df, netMarginOne)
                    periodZeroIndirectCostsSum = get_column_sum(df, indirectCostsZero)
                    periodOneIndirectCostsSum = get_column_sum(df, indirectCostsOne)
                    indirectCostsVarianceSum = (
                        periodOneIndirectCostsSum - periodZeroIndirectCostsSum
                    )
                    if totalAmountPeriodZero != 0:
                        periodZeroPercentMarginAfterIndCosts = (
                            periodZeroNetMarginSum / periodZeroSum * 100
                        )
                    if totalAmountPeriodOne != 0:
                        periodOnePercentMarginAfterIndCosts = (
                            periodOneNetMarginSum / periodOneSum * 100
                        )
                    percentMarginAfterIndCostsChange = (
                        periodOnePercentMarginAfterIndCosts
                        - periodZeroPercentMarginAfterIndCosts
                    )
                    (
                        paramDict[totalNetMarginPeriodZeroFilteredKey],
                        paramDict[totalNetMarginPeriodOneFilteredKey],
                    ) = (periodZeroNetMarginSum, periodOneNetMarginSum)
                    paramDict[totalNetMarginPeriodZeroinPercentFilteredKey] = (
                        periodZeroPercentMarginAfterIndCosts
                    )
                    paramDict[totalNetMarginPeriodOneinPercentFilteredKey] = (
                        periodOnePercentMarginAfterIndCosts
                    )
                    paramDict[percentVarianceAfterIndCosts] = (
                        percentMarginAfterIndCostsChange
                    )
                    paramDict[indirectCostsVarianceKey] = indirectCostsVarianceSum
                if discountColFound in paramDict and paramDict[discountColFound]:
                    netOfDiscountPeriodZero = (
                        netOfDiscount + separatorString + periodsArray[0]
                    )
                    netOfDiscountPeriodOne = (
                        netOfDiscount + separatorString + periodsArray[1]
                    )
                    periodZeroNetOfDiscountSum = get_column_sum(
                        df, netOfDiscountPeriodZero
                    )
                    periodOneNetOfDiscountSum = get_column_sum(
                        df, netOfDiscountPeriodOne
                    )
                    if paramDict[namingParams["isColumnMultiplied"]]:
                        if totalAmountPeriodZero != 0:
                            periodZeroNetOfDiscountSum = (
                                periodZeroNetOfDiscountSum / multiplyConstant
                            )
                        if totalAmountPeriodOne != 0:
                            periodOneNetOfDiscountSum = (
                                periodOneNetOfDiscountSum / multiplyConstant
                            )
                    netOfDiscountVarianceSum = (
                        periodOneNetOfDiscountSum - periodZeroNetOfDiscountSum
                    )
                    if totalAmountPeriodZero != 0:
                        periodZeroPercentMarginAfterDiscount = (
                            periodZeroNetOfDiscountSum / periodZeroSum * 100
                        )
                    if totalAmountPeriodOne != 0:
                        periodOnePercentMarginAfterDiscount = (
                            periodOneNetOfDiscountSum / periodOneSum * 100
                        )
                    percentMarginAfterMarginAfterdiscountUnitChange = (
                        periodOnePercentMarginAfterDiscount
                        - periodZeroPercentMarginAfterDiscount
                    )
                    (
                        paramDict[totalNetOfDiscountPeriodZeroFilteredKey],
                        paramDict[totalNetOfDiscountPeriodOneFilteredKey],
                    ) = (periodZeroNetOfDiscountSum, periodOneNetOfDiscountSum)
                    paramDict[totalNetOfDiscountPeriodZeroinPercentFilteredKey] = (
                        periodZeroPercentMarginAfterDiscount
                    )
                    paramDict[totalNetOfDiscountPeriodOneinPercentFilteredKey] = (
                        periodOnePercentMarginAfterDiscount
                    )
                    paramDict[percentVarianceAfterDiscountsKey] = (
                        percentMarginAfterMarginAfterdiscountUnitChange
                    )
                    paramDict[netOfDiscountVarianceKey] = netOfDiscountVarianceSum
                if (
                    varianceInPercent in chartDict
                    and chartDict[varianceInPercent] == metConditionValue
                ):
                    df, paramDict = calculate_variance_in_percent(
                        df, paramDict, chartDict, False
                    )
    return paramDict


def process_and_prepare_multidimensional_data(
    paramDict,
    dfDict,
    df,
    dfDates,
    dfPeriods,
    dfAllPeriods,
    dfPlan,
    indexCols,
    valueCols,
    chartDict,
    toDrop,
    originalValueColsCopy,
    colDict,
    tabDict,
    automateDict,
    planPlaybackDict,
    firstTime,
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    processingChoice = namingParams["processingChoice"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    varianceAmountName = namingParams["varianceAmountName"]
    periodName = namingParams["periodName"]
    dataPreparation = namingParams["dataPreparationName"]
    dfName = namingParams["dfName"]
    dfBase = namingParams["dfBaseName"]
    dfPeriodsName = namingParams["dfPeriodsName"]
    dfAllPeriodsName = namingParams["dfAllPeriodsName"]
    dfDatesName = namingParams["dfDatesName"]
    numberOfNodes = namingParams["numberOfNodes"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    isMergedFile = namingParams["isMergedFile"]
    planDataTabKey = namingParams["planDataTab"]
    onePeriodOnly = namingParams["onePeriodOnly"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    madeIntersectionDf = namingParams["madeIntersectionDfName"]
    duplicatedData = namingParams["duplicatedDataName"]
    foundColumnAndManageDates = namingParams["foundColumnAndManageDatesName"]
    dimensionsPromptMessage = namingParams["dimensionsPromptMessage"]
    columnCardinalityMessage = namingParams["columnCardinalityMessage"]
    valueColsArrayKey = namingParams["valueColsArray"]
    gptValueColsArrayKey = namingParams["gptValueColsArray"]
    pricePerUnit = namingParams["pricePerUnitName"]
    pricePerVolume = namingParams["pricePerVolumeName"]
    uniqueValuesInColumnDict = namingParams["uniqueValuesInColumnDict"]
    uniqueValuesInColumnList = namingParams["uniqueValuesInColumnList"]
    selectedPeriods = namingParams["selectedPeriods"]
    netMarginName = namingParams["netMarginName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    marginGrowthName = namingParams["marginGrowthName"]
    metricsArrayKey = namingParams["metricsArray"]
    cutCorrelationNumber = configParams[namingParams["cutCorrelationNumber"]]
    maxNumberOfIndexCols = configParams[namingParams["maxNumberOfIndexCols"]]

    if processingChoice not in chartDict:
        chartDict[processingChoice] = notMetConditionValue

    if is_valid_lazyframe(df) and not paramDict[impossibleToProcessFile]:
        df, dfDates, dfPeriods, dfAllPeriods, chartDict = make_intersection_df(
            df, dfDates, dfPeriods, dfAllPeriods, chartDict
        )
        measure_time(dataPreparation, madeIntersectionDf, False)
        dfCopy, indexColsCopy, nodeDictCopy, valueColsCopy, paramDictCopy = (
            update_nodeDict_and_map_columns(
                df, indexCols, valueCols, paramDict, chartDict, toDrop
            )
        )
        indexCols, nodeDict = copy.deepcopy(indexColsCopy), copy.deepcopy(nodeDictCopy)
        df = duplicate_dataframe(dfCopy)
        valueCols, paramDict, originalValueCols = (
            copy.deepcopy(valueColsCopy),
            copy.deepcopy(paramDictCopy),
            copy.deepcopy(originalValueColsCopy),
        )
        if isMergedFile in paramDict and paramDict[isMergedFile]:
            download_merged_file(dfDict, colDict, paramDict)
        if len(indexCols) > 1 or indexCols[0] != periodName:
            if periodName not in indexCols:
                if chartDict[processingChoice] in [
                    runVariableDimensionalAnalysis,
                    runOneDimensionalAnalysis,
                ]:
                    df = exclude_outliers_from_mix_variance(df, paramDict)
                paramDict = calculate_aggregate_values(df, True, paramDict, chartDict)
                measure_time(dataPreparation, duplicatedData, False)
                dfDict[dfBase] = df
                if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
                    dfCopy, dfSubtract, indexColsCopy, paramDictCopy = (
                        output_df_with_combinations(
                            indexCols, nodeDict, df, valueCols, paramDict, chartDict
                        )
                    )
                    if len(indexColsCopy) > 1:
                        paramDictCopy = get_data_sample(
                            dfCopy,
                            "output_df_with_combinations_df",
                            False,
                            paramDictCopy,
                        )
                        paramDictCopy = get_data_sample(
                            dfSubtract,
                            "output_df_with_combinations_dfSubtract",
                            False,
                            paramDictCopy,
                        )
                        dfCopy, paramDictCopy = delete_duplicate_nodes_and_melt_result(
                            dfCopy,
                            dfSubtract,
                            indexColsCopy,
                            valueCols,
                            paramDictCopy,
                            chartDict,
                        )
                        dfCopy = filter_by_number_of_nodes(dfCopy, paramDictCopy)
                    indexCols, paramDict = copy.deepcopy(indexColsCopy), copy.deepcopy(
                        paramDictCopy
                    )
                    df = duplicate_dataframe(dfCopy)
                    recalculate_price(df, paramDict)
                    paramDict = get_data_sample(df, "input", False, paramDict)
                paramDict[numberOfNodes] = len(indexCols)
                colList = (
                    str(indexCols).replace("[", "").replace("]", "").replace("'", "")
                )
                statusMessage = (
                    "Dataset has **"
                    + str(paramDict[numberOfNodes])
                    + "** dimension columns: **"
                    + colList
                    + "**. "
                )
                paramDict[dimensionsPromptMessage] = statusMessage
                uniqueValuesDict = {}
                paramDict[columnCardinalityMessage] = ""
                if uniqueValuesInColumnDict in paramDict:
                    uniqueValuesDict = paramDict[uniqueValuesInColumnDict]
                    uniqueValuesDict = dict(
                        sorted(uniqueValuesDict.items(), key=lambda item: item[1])
                    )
                    uniqueIndexValuesDict = {}
                    for element in uniqueValuesDict:
                        if element in colList:
                            uniqueIndexValuesDict[element] = uniqueValuesDict[element]
                    paramDict[uniqueValuesInColumnList] = list(
                        uniqueIndexValuesDict.keys()
                    )
                    response = "This is the number of unique items of each column: "
                    for element in uniqueIndexValuesDict:
                        info = (
                            element + ": " + str(uniqueIndexValuesDict[element]) + ", "
                        )
                        response = response + info
                    paramDict[columnCardinalityMessage] = response
                paramDict[dimensionsPromptMessage] = statusMessage
                paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
                paramDict = describe_col_hierarchy(nodeDict, paramDict)
                if firstTime:
                    prepare_plan_dataset(
                        dfPlan,
                        indexCols,
                        originalValueCols,
                        paramDict,
                        chartDict,
                        colDict[planDataTabKey],
                        tabDict[planDataTabKey],
                        planPlaybackDict,
                    )
                dfAllPeriods = collect_all_periods(
                    dfAllPeriods, indexCols, valueCols, paramDict
                )
                (
                    dfDict[dfName],
                    dfDict[dfPeriodsName],
                    dfDict[dfDatesName],
                    dfDict[dfAllPeriodsName],
                ) = (df, dfPeriods, dfDates, dfAllPeriods)
                paramDict[onePeriodOnly] = notMetConditionValue
                if len(chartDict[selectedPeriods]) == 1:
                    paramDict[onePeriodOnly] = metConditionValue
                notGptColumnsArray = [netMarginName, indirectCostsName, cogsName]
                gptOriginalValueCols = []
                for gptMetric in originalValueCols:
                    if gptMetric not in notGptColumnsArray:
                        gptOriginalValueCols.append(gptMetric)
                metricsArray = copy.deepcopy(gptOriginalValueCols)
                gptValColList = (
                    str(gptOriginalValueCols)
                    .replace("[", "")
                    .replace("]", "")
                    .replace("'", "")
                )
                valColList = (
                    str(originalValueCols)
                    .replace("[", "")
                    .replace("]", "")
                    .replace("'", "")
                )
                toDiscardArray, chartDict = get_growth_metrics_for_bubble(
                    chartDict, chartDict[selectedPeriods], originalValueCols
                )
                valueColsWithPriceSelect = add_price_to_value_cols(
                    originalValueCols, df
                )
                toDiscardArray, chartDict = get_gross_margin_metrics_for_bubble(
                    chartDict, originalValueCols, valueColsWithPriceSelect
                )
                if unitsName in originalValueCols:
                    valColList = valColList + ", " + pricePerUnit
                if volumeName in originalValueCols:
                    valColList = valColList + ", " + pricePerVolume
                if unitsName in gptOriginalValueCols:
                    metricsArray.append(pricePerUnit)
                    gptValColList = gptValColList + ", " + pricePerUnit
                if volumeName in gptOriginalValueCols:
                    gptValColList = gptValColList + ", " + pricePerVolume
                    metricsArray.append(pricePerVolume)
                paramDict[gptValueColsArrayKey] = gptValColList
                paramDict[valueColsArrayKey] = valColList
                paramDict[metricsArrayKey] = metricsArray
                return dfDict, indexCols, originalValueCols, paramDict, chartDict
            else:
                message = "Unable to detect more than one year data in dataset. Unable to plot variance charts and year-over-year charts."
                paramDict = add_warning_message_in_load_data_tab(paramDict, message)
                message = "If your dataset contains more than one year of data there might be a problem with parsing."
                paramDict = add_warning_message_in_load_data_tab(paramDict, message)
                if periodName in indexCols:
                    indexCols.remove(periodName)
                paramDict[numberOfNodes] = len(indexCols)
                colList = (
                    str(indexCols).replace("[", "").replace("]", "").replace("'", "")
                )
                statusMessage = (
                    "Dataset has **"
                    + str(paramDict[numberOfNodes])
                    + "** dimension columns: **"
                    + colList
                    + "**. "
                )
                paramDict[dimensionsPromptMessage] = statusMessage
                paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
                paramDict = describe_col_hierarchy(nodeDict, paramDict)
                (
                    dfDict[dfName],
                    dfDict[dfPeriodsName],
                    dfDict[dfDatesName],
                    dfDict[dfAllPeriodsName],
                ) = (df, dfPeriods, dfDates, dfAllPeriods)
                paramDict[onePeriodOnly] = metConditionValue
                return dfDict, indexCols, originalValueCols, paramDict, chartDict
        else:
            message = "Unable to detect dimension columns."
            paramDict = add_error_message_in_load_data_tab(paramDict, message)
            return dfDict, None, None, paramDict, chartDict
    else:
        dfDict[dfName], dfDict[dfPeriodsName], dfDict[dfDatesName] = (
            pl.LazyFrame(),
            dfPeriods,
            dfDates,
        )
        return dfDict, None, None, paramDict, None


def describe_col_hierarchy(nodeDict, paramDict):
    """
    read nodeDict to describe hierarchy
    """
    namingParams = get_naming_params()
    notHierarchical = namingParams["notHierarchicalName"]
    hierarchical = namingParams["hierarchicalName"]
    hierarchyPromptMessage = namingParams["hierarchyPromptMessage"]
    notHierarchicalPromptMessage = namingParams["notHierarchicalPromptMessage"]
    if notHierarchical in nodeDict and len(nodeDict[notHierarchical]) > 0:
        numberOfNotHierarchical = len(nodeDict[notHierarchical])
        notHierarchicalCols = []
        for element in nodeDict[notHierarchical]:
            notHierarchicalCols.append(element)
        colList = (
            str(notHierarchicalCols).replace("[", "").replace("]", "").replace("'", "")
        )
        statusMessage = (
            "Of these, **"
            + str(numberOfNotHierarchical)
            + "** are non-hierarchical: **"
            + colList
            + "**. "
        )
        paramDict[notHierarchicalPromptMessage] = statusMessage
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
    if hierarchical in nodeDict and len(nodeDict[hierarchical]) > 0:
        statusMessage = (
            "There are **"
            + str(len(nodeDict[hierarchical]))
            + "** column hierarchies: "
        )
        paramDict[hierarchyPromptMessage] = statusMessage
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
        count = 1
        statusMessage = ""
        numberofHierarchies = len(nodeDict[hierarchical])
        for hierarchy in nodeDict[hierarchical]:
            hierarchicalCols = []
            for element in nodeDict[hierarchical][hierarchy]:
                hierarchicalCols.append(element)
            colList = (
                str(hierarchicalCols).replace("[", "").replace("]", "").replace("'", "")
            )
            statusMessage = statusMessage + " " + str(count) + ": **" + colList + "**"
            if count < numberofHierarchies:
                statusMessage = statusMessage + ";"
            count = count + 1
        statusMessage = statusMessage + ". "
        paramDict[hierarchyPromptMessage] = (
            paramDict[hierarchyPromptMessage] + statusMessage
        )
        paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 1)
    if hierarchical in nodeDict:
        paramDict[hierarchical] = nodeDict[hierarchical]
    return paramDict
