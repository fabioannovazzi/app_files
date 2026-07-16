import copy

import numpy as np
import polars as pl
from polars.exceptions import ColumnNotFoundError

from modules.utilities.ui_notifier import ui
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_run_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import add_warning_message_in_load_data_tab

try:
    from modules.utilities.helpers import (
        add_running_total,
        add_status_message_to_paramDict,
        check_and_clean_columns,
        check_if_duplicates_in_all_columns,
        drop_columns,
        duplicate_dataframe,
        get_data_sample,
        get_dataset_specific_parameter,
        is_numeric_dtype,
        multi_index_df_polars,
        round_value_columns_to_dec,
        take_filtered_value_out_of_option_list,
        unstack_and_flatten_polars,
    )
except ImportError as e:  # pragma: no cover - allow partial stubs in tests
    import sys
    import types

    ui.write("variance_utils import error:", e)

    _helpers = sys.modules.get(
        "modules.utilities.helpers", types.ModuleType("modules.utilities.helpers")
    )

    add_running_total = getattr(_helpers, "add_running_total", lambda df: df)
    add_status_message_to_paramDict = getattr(
        _helpers, "add_status_message_to_paramDict", lambda pd, msg, n: pd
    )
    check_and_clean_columns = getattr(
        _helpers, "check_and_clean_columns", lambda df, cols, sums: (cols, sums)
    )
    check_if_duplicates_in_all_columns = getattr(
        _helpers, "check_if_duplicates_in_all_columns", lambda df, name, pd: pd
    )
    drop_columns = getattr(_helpers, "drop_columns", lambda df, cols: df)
    duplicate_dataframe = getattr(_helpers, "duplicate_dataframe", lambda df: df)
    get_data_sample = getattr(
        _helpers, "get_data_sample", lambda df, name, flag, pdict: pdict
    )
    get_dataset_specific_parameter = getattr(
        _helpers,
        "get_dataset_specific_parameter",
        lambda pd, key, default: (default, pd),
    )
    is_numeric_dtype = getattr(_helpers, "is_numeric_dtype", lambda dt: True)
    multi_index_df_polars = getattr(
        _helpers, "multi_index_df_polars", lambda df, idx: df
    )
    round_value_columns_to_dec = getattr(
        _helpers, "round_value_columns_to_dec", lambda df, cols: df
    )
    take_filtered_value_out_of_option_list = getattr(
        _helpers, "take_filtered_value_out_of_option_list", lambda arr, val: arr
    )
    unstack_and_flatten_polars = getattr(
        _helpers, "unstack_and_flatten_polars", lambda df: df
    )
from modules.utilities.utils import get_schema_and_column_names

try:
    from modules.utilities.utils import ensure_lazyframe, get_column_sum, get_row_count
except ImportError as e:  # pragma: no cover
    
    ui.write("variance_utils import error:", e)

    def ensure_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
        if isinstance(obj, pl.LazyFrame):
            return obj
        if isinstance(obj, pl.DataFrame):
            return obj.lazy()
        return pl.DataFrame(obj).lazy()

    def get_column_sum(lf: pl.LazyFrame, column: str) -> float:
        return lf.select(pl.col(column).sum()).collect().item()

    def get_row_count(df: pl.DataFrame | pl.LazyFrame) -> int:
        if isinstance(df, pl.LazyFrame):
            return df.select(pl.len()).collect().item()
        if isinstance(df, pl.DataFrame):
            return df.height
        return pl.DataFrame(df).height


def insert_dates(chartDict, second_array):
    namingParams = get_naming_params()
    selectedPeriods = namingParams["selectedPeriods"]

    first_array = chartDict[selectedPeriods]
    # Check if the first array has exactly 2 elements
    if len(first_array) != 2:
        raise ValueError("The first array must contain exactly 2 elements.")

    # Insert the first element of the first array at the first position of the second array
    second_array.insert(0, first_array[0])

    # Insert the second element of the first array at the last position of the second array
    second_array.append(first_array[1])

    return second_array


def make_divideArray(df, indexCols):
    """
    need to output an erray with the columns to divide back by multiply constant
    """
    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    amount = namingParams["monetaryLocalCurrencyName"]
    discount = namingParams["discountName"]
    cogs = namingParams["cogsName"]
    margin = namingParams["marginName"]
    price = namingParams["priceName"]
    percentSuffix = namingParams["percentSuffix"]
    volumeVariance = namingParams["volumeVariance"]
    costVariance = namingParams["costVariance"]
    stemArray = [amount, discount, cogs, margin, price, costVariance, volumeVariance]
    divideArray = []
    columns, schema = get_schema_and_column_names(df)
    for column in columns:
        if column not in indexCols:
            if column == varianceAmountName and column not in divideArray:
                divideArray.append(column)
            for stem in stemArray:
                if percentSuffix not in column:
                    if stem in column and column not in divideArray:
                        divideArray.append(column)
    return divideArray


def replace_all_with_blanc_or_nan(
    df: pl.DataFrame | pl.LazyFrame,
    fill_value: str,
    *,
    as_lazy: bool = False,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with ``nanFillValue`` replaced in string columns.

    Parameters
    ----------
    df:
        Input data as ``DataFrame`` or ``LazyFrame``.
    fill_value:
        Replacement value for occurrences of ``nanFillValue``.
    as_lazy:
        When ``True`` return a ``LazyFrame`` regardless of the input type.
    """

    from modules.utilities.config import get_run_params

    run_params = get_run_params()
    if not run_params["replaceAllWithBlanc"]:
        return df

    naming_params = get_naming_params()
    nan_fill = naming_params["nanFillValue"]

    use_lazy_input = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    schema = lf.collect_schema()
    string_cols = [
        name for name, dtype in schema.items() if dtype in (pl.String, pl.Categorical)
    ]

    exprs = [
        pl.when(pl.col(c) == nan_fill)
        .then(pl.lit(fill_value))
        .otherwise(pl.col(c))
        .alias(c)
        for c in string_cols
    ]
    lf = lf.with_columns(exprs)

    if as_lazy or use_lazy_input:
        return lf
    return lf.collect()


def add_insert_at_row_params_to_dict(paramDictCopy):
    """
    an already used dataset might have rules on having certains node rows in certain positions
    """
    try:
        from modules.utilities.config import get_insert_at_row_params
    except ImportError as e:  # pragma: no cover - optional dependency during testing
        
        ui.write("variance_utils insert_at_row import error:", e)

        def get_insert_at_row_params():
            return {}

    insertAtRowParams = get_insert_at_row_params()
    namingParams = get_naming_params()
    fileCodeName = namingParams["fileCodeName"]
    insertAtRowDictName = namingParams["insertAtRowDict"]
    paramDict = copy.deepcopy(paramDictCopy)
    if fileCodeName in paramDict:  # uploaded files have not filecodeName
        fileCode = paramDict[fileCodeName]
        insertAtRowDict = {}
        if fileCode in insertAtRowParams:
            if len(insertAtRowParams[fileCode]) > 0:
                insertAtRowDict = insertAtRowParams[fileCode]
                paramDict[insertAtRowDictName] = insertAtRowDict
    return paramDict


def set_parameters_on_scenario_option(paramDict):
    """
    sets options based on chosen scenario
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    scenarioParameterDict = configParams[namingParams["scenarioParameterDict"]]
    numberOfRowResults = namingParams["numberOfRowResults"]
    maxPercentOfTotalVariance = namingParams["maxPercentOfTotalVariance"]
    maxPercentOfTotalAmount = namingParams["maxPercentOfTotalAmount"]
    minPercentOfTotalVariance = namingParams["minPercentOfTotalVariance"]
    minPercentOfTotalAmount = namingParams["minPercentOfTotalAmount"]
    numberOfNodesWeight = namingParams["numberOfNodesWeight"]
    varianceAmountWeight = namingParams["varianceAmountWeight"]
    uniqueValuesInCombinationWeight = namingParams["uniqueValuesInCombinationWeight"]
    parameterSetting = namingParams["parameterSetting"]
    numberOfRowResultsDefault, paramDict = get_dataset_specific_parameter(
        paramDict, numberOfRowResults, False
    )
    maxPercentOfTotalVarianceDefault, paramDict = get_dataset_specific_parameter(
        paramDict, maxPercentOfTotalVariance, False
    )
    maxPercentOfTotalAmountDefault, paramDict = get_dataset_specific_parameter(
        paramDict, maxPercentOfTotalAmount, False
    )
    minPercentOfTotalVarianceDefault, paramDict = get_dataset_specific_parameter(
        paramDict, minPercentOfTotalVariance, False
    )
    minPercentOfTotalAmountDefault, paramDict = get_dataset_specific_parameter(
        paramDict, minPercentOfTotalAmount, False
    )
    varianceAmountWeightDefault, paramDict = get_dataset_specific_parameter(
        paramDict, varianceAmountWeight, False
    )
    numberOfNodesWeightDefault, paramDict = get_dataset_specific_parameter(
        paramDict, numberOfNodesWeight, False
    )
    uniqueValuesInCombinationWeightDefault, paramDict = get_dataset_specific_parameter(
        paramDict, uniqueValuesInCombinationWeight, False
    )
    scenarioParameterDict = scenarioParameterDict[paramDict[parameterSetting]]
    for element in scenarioParameterDict:
        paramDict[element] = scenarioParameterDict[element]
    return paramDict


def optimize_default_parameters(paramDict):
    """
    before running the thing we optimize parameters based on what we know of the dataset
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceOnTotal = namingParams["varianceOnTotal"]
    numberOfNodes = namingParams["numberOfNodes"]
    uniqueValuesInCombination = namingParams["uniqueValuesInCombination"]
    minPercentOfTotalAmountDict = configParams[
        namingParams["minPercentOfTotalAmountDict"]
    ]
    maxPercentOfTotalAmountDict = configParams[
        namingParams["maxPercentOfTotalAmountDict"]
    ]
    varianceAmountWeightDict = configParams[namingParams["varianceAmountWeightDict"]]
    numberOfNodesWeightDict = configParams[namingParams["numberOfNodesWeightDict"]]
    uniqueValuesInCombinationWeightDict = configParams[
        namingParams["uniqueValuesInCombinationWeightDict"]
    ]
    maxPercentChangeDict = configParams[namingParams["maxPercentChangeDict"]]
    paramDict[namingParams["minPercentOfTotalAmountDefault"]] = configParams[
        namingParams["minPercentOfTotalAmount"]
    ]
    paramDict[namingParams["maxPercentOfTotalVarianceDefault"]] = configParams[
        namingParams["maxPercentOfTotalVariance"]
    ]
    paramDict[namingParams["varianceAmountWeightDefault"]] = configParams[
        namingParams["varianceAmountWeight"]
    ]
    paramDict[namingParams["numberOfNodesWeightDefault"]] = configParams[
        namingParams["numberOfNodesWeight"]
    ]
    paramDict[namingParams["uniqueValuesInCombinationWeightDefault"]] = configParams[
        namingParams["uniqueValuesInCombinationWeight"]
    ]
    paramDict[namingParams["maxPercentChangeDefault"]] = configParams[
        namingParams["maxPercentChange"]
    ]
    if varianceOnTotal in paramDict:
        for element in minPercentOfTotalAmountDict:
            if (
                abs(paramDict[varianceOnTotal])
                >= minPercentOfTotalAmountDict[element][0]
                and abs(paramDict[varianceOnTotal])
                < minPercentOfTotalAmountDict[element][1]
            ):
                paramDict[namingParams["minPercentOfTotalAmount"]] = element
                paramDict[namingParams["minPercentOfTotalAmountDefault"]] = element
        for element in maxPercentOfTotalAmountDict:
            if (
                abs(paramDict[varianceOnTotal])
                >= maxPercentOfTotalAmountDict[element][0]
                and abs(paramDict[varianceOnTotal])
                < maxPercentOfTotalAmountDict[element][1]
            ):
                paramDict[namingParams["maxPercentOfTotalVariance"]] = element
                paramDict[namingParams["maxPercentOfTotalVarianceDefault"]] = element
        for element in varianceAmountWeightDict:
            if (
                abs(paramDict[varianceOnTotal]) >= varianceAmountWeightDict[element][0]
                and abs(paramDict[varianceOnTotal])
                < varianceAmountWeightDict[element][1]
            ):
                paramDict[namingParams["varianceAmountWeight"]] = element
                paramDict[namingParams["varianceAmountWeightDefault"]] = element
        for element in maxPercentChangeDict:
            if (
                abs(paramDict[varianceOnTotal]) >= maxPercentChangeDict[element][0]
                and abs(paramDict[varianceOnTotal]) < maxPercentChangeDict[element][1]
            ):
                paramDict[namingParams["maxPercentChange"]] = element
                paramDict[namingParams["maxPercentChangeDefault"]] = element
    if numberOfNodes in paramDict:
        for element in numberOfNodesWeightDict:
            if (
                abs(paramDict[numberOfNodes]) >= numberOfNodesWeightDict[element][0]
                and abs(paramDict[numberOfNodes]) < numberOfNodesWeightDict[element][1]
            ):
                paramDict[namingParams["numberOfNodesWeight"]] = element
                paramDict[namingParams["numberOfNodesWeightDefault"]] = element
                paramDict[namingParams["uniqueValuesInCombinationWeight"]] = element
                paramDict[namingParams["uniqueValuesInCombinationWeightDefault"]] = (
                    element
                )
    return paramDict


def group_by_and_sort_data_for_variance_calculation(
    df: pl.DataFrame | pl.LazyFrame, group_byCols, sumCols, as_lazy: bool = False
) -> tuple[pl.DataFrame | pl.LazyFrame, list[str], list[str]]:
    """Group ``df`` by ``group_byCols`` and sort by absolute variance."""

    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]
    varianceAmount = namingParams["varianceAmountName"]

    # always operate on a LazyFrame pipeline
    lf = ensure_lazyframe(df)

    group_byCols, sumCols = check_and_clean_columns(lf, group_byCols, sumCols)

    lf = lf.group_by(group_byCols).agg([pl.col(c).sum().alias(c) for c in sumCols])

    lf = lf.with_columns(pl.col(varianceAmount).abs().alias(workColumn))
    lf = lf.sort(pl.col(workColumn), descending=True)
    lf = add_running_total(lf)
    lf = drop_columns(lf, [workColumn])

    if as_lazy:
        return lf, group_byCols, sumCols
    if isinstance(df, pl.DataFrame):
        return lf.collect(), group_byCols, sumCols
    return lf, group_byCols, sumCols


def filter_by_number_of_nodes(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict, as_lazy: bool = False
) -> pl.DataFrame | pl.LazyFrame:
    """Filter rows where the number of nodes exceeds the configured maximum.

    Parameters
    ----------
    df:
        Input dataset to filter.
    paramDict:
        Parameter dictionary containing ``max_nodes`` configuration.
    as_lazy:
        If ``True``, return a ``LazyFrame`` even when ``df`` is a ``DataFrame``.
    """

    namingParams = get_naming_params()
    number_of_nodes = namingParams["numberOfNodes"]
    max_nodes_key = namingParams["maxNumberOfNodes"]

    max_nodes, paramDict = get_dataset_specific_parameter(
        paramDict, max_nodes_key, False
    )

    if max_nodes <= 0:
        return df

    use_lazy = as_lazy or isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf = lf.filter(pl.col(number_of_nodes) <= pl.lit(max_nodes))
    return lf if use_lazy else lf.collect()


def change_nan_to_all(df, indexCols, paramDict):
    """
    when it does the joining, it does not like empty values in the index columns. We exchange them with "All"
    we also set all index columns as category and reset the index
    """
    namingParams = get_naming_params()
    nanFillValue = namingParams["nanFillValue"]
    # use centralized column access helper
    columns, _ = get_schema_and_column_names(df)
    df = df.with_columns(
        [
            pl.col(c).fill_null(nanFillValue).cast(pl.Categorical)
            for c in indexCols
            if c in columns
        ]
    )
    paramDict = check_if_duplicates_in_all_columns(df, "change nan to all", paramDict)
    return df, paramDict


def tag_rows_with_index_number(
    df: pl.DataFrame | pl.LazyFrame, randomKey: str
) -> pl.LazyFrame:
    """Return ``df`` with a sequential index column named ``randomKey``."""

    lf = ensure_lazyframe(df)
    lf = drop_columns(lf, [randomKey])
    return lf.with_row_index(randomKey)


def add_random_key(
    df: pl.DataFrame | pl.LazyFrame,
    valueCols: list[str],
    loop: bool,
    *,
    as_lazy: bool = False,
) -> tuple[pl.DataFrame | pl.LazyFrame, list[str]]:
    """Append a shuffled random key column and return the updated DataFrame."""

    namingParams = get_naming_params()
    randomKey = namingParams["randomKey"]
    loopRandomKey = namingParams["loopRandomKey"]
    if loop:
        randomKey = loopRandomKey

    use_lazy = as_lazy or isinstance(df, pl.LazyFrame)
    lf = tag_rows_with_index_number(df, randomKey)
    lf = lf.with_columns(pl.int_range(0, pl.len()).shuffle().alias(randomKey))
    valueCols.append(randomKey)
    return (lf if use_lazy else lf.collect()), valueCols


def remove_scenario_from_index(indexColsCopy):
    """
    for a number of processing tasks, we do not want the period in the indexcolumn array
    """
    namingParams = get_naming_params()
    scenarioName = namingParams["scenarioName"]
    indexCols = copy.deepcopy(indexColsCopy)
    if scenarioName in indexCols:
        indexCols = take_filtered_value_out_of_option_list(indexCols, scenarioName)
    return indexCols


def add_change_column(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict, chartDict: dict
) -> pl.DataFrame | pl.LazyFrame:
    """Add a change column based on the configured variance aggregation."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    cogs_key = namingParams["cogsAggregationArray"]
    sales_key = namingParams["salesAggregationArray"]
    discounts_key = namingParams["discountsAggregationArray"]

    cogsAggregationArray = (
        cogs_key if isinstance(cogs_key, list) else varianceAggregationParams[cogs_key]
    )
    salesAggregationArray = (
        sales_key
        if isinstance(sales_key, list)
        else varianceAggregationParams[sales_key]
    )
    discountsAggregationArray = (
        discounts_key
        if isinstance(discounts_key, list)
        else varianceAggregationParams[discounts_key]
    )
    changeName = namingParams["changeName"]
    periodsArray = configParams["periodsArray"]
    separatorString = namingParams["separatorString"]
    valueName = namingParams["monetaryLocalCurrencyName"]
    marginName = namingParams["marginName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    periodName = namingParams["periodName"]
    varianceAggregation = namingParams["varianceAggregation"]
    use_lazy = as_lazy or isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    if (
        varianceAggregation in chartDict
        and chartDict[varianceAggregation] in cogsAggregationArray
    ):
        marginPeriodZero = marginName + separatorString + periodsArray[0]
        marginPeriodOne = marginName + separatorString + periodsArray[1]
        if marginPeriodOne in columns and marginPeriodZero in columns:
            lf = lf.with_columns(
                pl.col(marginPeriodOne).fill_null(0).alias(marginPeriodOne),
                pl.col(marginPeriodZero).fill_null(0).alias(marginPeriodZero),
            )
            lf = lf.with_columns(
                (pl.col(marginPeriodOne) - pl.col(marginPeriodZero)).alias(changeName)
            )
    elif (
        varianceAggregation in chartDict
        and chartDict[varianceAggregation] in discountsAggregationArray
    ):
        netOfDiscountPeriodZero = netOfDiscountName + separatorString + periodsArray[0]
        netOfDiscountPeriodOne = netOfDiscountName + separatorString + periodsArray[1]
        if netOfDiscountPeriodOne in columns and netOfDiscountPeriodZero in columns:
            lf = lf.with_columns(
                pl.col(netOfDiscountPeriodOne)
                .fill_null(0)
                .alias(netOfDiscountPeriodOne),
                pl.col(netOfDiscountPeriodZero)
                .fill_null(0)
                .alias(netOfDiscountPeriodZero),
            )
            lf = lf.with_columns(
                (
                    pl.col(netOfDiscountPeriodOne) - pl.col(netOfDiscountPeriodZero)
                ).alias(changeName)
            )
    else:
        amountPeriodZero = valueName + separatorString + periodsArray[0]
        amountPeriodOne = valueName + separatorString + periodsArray[1]
        if amountPeriodOne in columns and amountPeriodZero in columns:
            lf = lf.with_columns(
                pl.col(amountPeriodOne).fill_null(0).alias(amountPeriodOne),
                pl.col(amountPeriodZero).fill_null(0).alias(amountPeriodZero),
            )
            lf = lf.with_columns(
                (pl.col(amountPeriodOne) - pl.col(amountPeriodZero)).alias(changeName)
            )
    return lf if use_lazy else lf.collect()


def remove_period_from_index(indexColsCopy):
    """
    for a number of processing tasks, we do not want the period in the indexcolumn array
    """
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    indexCols = copy.deepcopy(indexColsCopy)
    if periodName in indexCols:
        indexCols = take_filtered_value_out_of_option_list(indexCols, periodName)
    return indexCols


def write_status_messages(df, paramDict, chartDict, sortedPeriods):
    namingParams = get_naming_params()
    allPeriodsListKey = namingParams["allPeriodsList"]
    periodPromptMessageKey = namingParams["periodPromptMessage"]
    writePeriods = (
        str(paramDict[allPeriodsListKey])
        .replace("[", "")
        .replace("]", "")
        .replace("'", "")
    )
    statusMessage = f"The dataset contains the following {len(paramDict[allPeriodsListKey])} periods: **{writePeriods}**. "
    paramDict[periodPromptMessageKey] = statusMessage
    paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 2)
    statusMessage = f"1st period: **{str(sortedPeriods[0])}**, 2nd period: **{str(sortedPeriods[1])}**."
    paramDict = add_status_message_to_paramDict(paramDict, statusMessage, 2)
    # Logic to handle date messages
    return paramDict


def should_reverse_sort(periods, chartDict, paramDict, reverseOrderperiodsArray):
    namingParams = get_naming_params()
    configParams = get_config_params()
    reverseSortPeriodsKey = namingParams["reverseSortPeriods"]
    currentYearName = namingParams["currentYearName"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    datePeriodName = namingParams["datePeriodName"]
    yearName = namingParams["yearName"]
    yearBeforeName = namingParams["yearBeforeName"]
    reverseOrderperiodsArray = configParams[namingParams["reverseOrderperiodsArray"]]

    reverseSort = False

    # Check conditions for reversing sort based on comparing year-before
    if compareWithYearBefore in chartDict and chartDict[compareWithYearBefore]:
        if datePeriodName in paramDict and paramDict[datePeriodName] == yearName:
            if currentYearName in periods or yearBeforeName in periods[0]:
                reverseSort = True

    # Check if periods match any set in reverseOrderperiodsArray
    periodsLower = [p.lower() for p in periods]
    for element in reverseOrderperiodsArray:
        if set(element) == set(periodsLower):
            reverseSort = True

    # Toggle reverse if chartDict says so
    if chartDict[reverseSortPeriodsKey]:
        reverseSort = not reverseSort

    return reverseSort


def sort_and_clean_periods(periods, reverseSort):
    namingParams = get_naming_params()
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    sortedPeriods = sorted(periods, reverse=reverseSort)
    from modules.data.common_data_utils import stripe_replace_and_clean

    cleanedPeriods = [stripe_replace_and_clean(p, False) for p in sortedPeriods]
    periodsUpper = [p.upper() for p in cleanedPeriods]
    return sortedPeriods, cleanedPeriods, periodsUpper


def apply_rename_dict(df, paramDict, cleanedPeriods, sortedPeriods):
    namingParams = get_naming_params()
    renameTitlesDict = namingParams["renameTitlesDict"]
    firstPeriodName = namingParams["firstPeriodName"]
    secondPeriodName = namingParams["secondPeriodName"]
    periodZeroName = namingParams["periodZeroName"]
    periodOneName = namingParams["periodOneName"]
    currentYearName = namingParams["currentYearName"]
    yearBeforeName = namingParams["yearBeforeName"]
    periodName = namingParams["periodName"]

    renameDict = {
        cleanedPeriods[0]: firstPeriodName,
        cleanedPeriods[1]: secondPeriodName,
    }
    # Update renameTitlesDict based on conditions
    # This is essentially the same logic as the original function
    paramDict[renameTitlesDict] = {
        periodZeroName: str(sortedPeriods[0]),
        periodOneName: str(sortedPeriods[1]),
    }

    # Apply rename dictionary using conditional logic for LazyFrame
    old_val_1, old_val_2 = list(renameDict.keys())
    new_val_1, new_val_2 = renameDict[old_val_1], renameDict[old_val_2]

    df = df.with_columns(
        pl.when(pl.col(periodName) == old_val_1)
        .then(pl.lit(new_val_1))
        .when(pl.col(periodName) == old_val_2)
        .then(pl.lit(new_val_2))
        .otherwise(pl.col(periodName))
        .alias(periodName)
    )
    return df, paramDict


def rename_periods(df, paramDict, chartDict, writeMessage):
    """
    after aggregating the rows, we want to rename the date periods to something like
    "P0" and "P1" so we do not have naming issues later
    we also check if we need to reverse the order of the periods
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    dateName = namingParams["dateName"]
    dateColFound = namingParams["dateColFound"]
    firstPeriodName = namingParams["firstPeriodName"]
    secondPeriodName = namingParams["secondPeriodName"]
    selectedPeriodsKey = namingParams["selectedPeriods"]
    reverseSortPeriodsKey = namingParams["reverseSortPeriods"]
    currentYearName = namingParams["currentYearName"]
    periodZeroName = namingParams["periodZeroName"]
    periodOneName = namingParams["periodOneName"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    datePeriodName = namingParams["datePeriodName"]
    yearName = namingParams["yearName"]
    tyYaDatesKey = namingParams["tyYaDates"]
    mostRecentPeriod = namingParams["mostRecentPeriod"]
    renameTitlesDict = namingParams["renameTitlesDict"]
    toTitleCaseKey = namingParams["toTitleCase"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    periodToDate = namingParams["periodToDate"]
    periodPromptMessage = namingParams["periodPromptMessage"]
    mostRecentDatePromptMessage = namingParams["mostRecentDatePromptMessage"]
    leastRecentDatePromptMessage = namingParams["leastRecentDatePromptMessage"]
    reverseOrderperiodsArray = configParams[namingParams["reverseOrderperiodsArray"]]
    periods = chartDict[selectedPeriodsKey]
    toTitleCase, paramDict = get_dataset_specific_parameter(
        paramDict, toTitleCaseKey, False
    )
    isReverseSortPeriods, paramDict = get_dataset_specific_parameter(
        paramDict, reverseSortPeriodsKey, False
    )
    reverseSort = should_reverse_sort(
        periods, chartDict, paramDict, reverseOrderperiodsArray
    )
    sortedPeriods, cleanedPeriods, periodsUpper = sort_and_clean_periods(
        periods, reverseSort
    )
    chartDict[selectedPeriodsKey] = (
        sortedPeriods
        if not any(p in periodsUpper for p in [acName, pyName, plName])
        else periodsUpper
    )
    df, paramDict = apply_rename_dict(df, paramDict, cleanedPeriods, sortedPeriods)
    if writeMessage:
        paramDict = write_status_messages(df, paramDict, chartDict, sortedPeriods)
        return df, paramDict
    else:
        return df, paramDict


def check_column_correlation_to_variance(
    df: pl.DataFrame | pl.LazyFrame,
    indexCols: list[str],
    paramDict: dict,
    chartDict: dict,
) -> tuple[list[str], dict]:
    """Return the index columns most correlated with the change metric."""

    namingParams = get_naming_params()
    configParams = get_config_params()

    changeName = namingParams["changeName"]
    styledCorrelations = namingParams["styledCorrelations"]
    maxNumberOfIndexCols = configParams[namingParams["maxNumberOfIndexCols"]]
    cutCorrelationNumber = configParams[namingParams["cutCorrelationNumber"]]

    dfCorr = duplicate_dataframe(df)
    dfCorr, paramDict = rename_periods(dfCorr, paramDict, chartDict, False)
    dfCorr = multi_index_df_polars(dfCorr, indexCols)
    dfCorr = dfCorr.sort(indexCols)
    dfCorr = unstack_and_flatten_polars(dfCorr)

    indexColsWithoutPeriod = remove_period_from_index(indexCols)
    indexColsWithoutPeriod = remove_scenario_from_index(indexColsWithoutPeriod)

    # use centralized schema accessor instead of direct `.schema`
    _, dfCorr_schema = get_schema_and_column_names(dfCorr)
    for element in indexColsWithoutPeriod:
        if not is_numeric_dtype(dfCorr_schema[element]):
            dfCorr = dfCorr.with_columns(
                pl.col(element).cast(pl.Categorical).to_physical().alias(element)
            )
        dfCorr = dfCorr.with_columns(
            pl.when(pl.col(element) % 2 != 0).then(1).otherwise(0).alias(element)
        )

    dfCorr = add_change_column(dfCorr, paramDict, chartDict)

    correlationCols = indexColsWithoutPeriod + [changeName]
    dfCorr = dfCorr.select([pl.col(c).fill_null(0).alias(c) for c in correlationCols])

    corr_dict: dict[str, float] = {}
    for col in indexColsWithoutPeriod:
        value = dfCorr.select(pl.corr(col, changeName)).item()
        if value is not None and not np.isnan(value):
            corr_dict[col] = abs(value)

    paramDict[styledCorrelations] = corr_dict

    ordered_cols = [
        col
        for col, val in sorted(corr_dict.items(), key=lambda x: x[1], reverse=True)
        if val >= cutCorrelationNumber
    ][:maxNumberOfIndexCols]

    return ordered_cols, paramDict


def delete_duplicate_variance_values(df, indexCols, paramDict, chartDict):
    """
    for the "mix variance" option we want to delete
    the results where volume variance corresponds
    to an identical negative mix variance since this is probably noise
    """
    namingParams = get_naming_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixSalesAggregationArray = varianceAggregationParams[
        namingParams["mixSalesAggregationArray"]
    ]
    mixMarginAggregationArray = varianceAggregationParams[
        namingParams["mixMarginAggregationArray"]
    ]
    varianceAggregation = namingParams["varianceAggregation"]
    mixVariance = namingParams["mixVariance"]
    workColumn = namingParams["workColumn"]
    varianceAmount = namingParams["varianceAmountName"]
    mixAggregations = mixSalesAggregationArray + mixMarginAggregationArray
    if chartDict[varianceAggregation] in mixAggregations:
        dropDuplicatesSubset = indexCols + [workColumn]

        use_lazy = isinstance(df, pl.LazyFrame)
        lf = ensure_lazyframe(df)

        lf = lf.with_row_index("__idx").drop("__idx")
        lf = lf.with_columns(pl.col(varianceAmount).round(0).alias(workColumn))
        lf = lf.with_columns(
            pl.when(pl.col(workColumn) < 0)
            .then(-pl.col(workColumn))
            .otherwise(pl.col(workColumn))
            .alias(workColumn)
        )
        lf = lf.unique(subset=dropDuplicatesSubset, keep=False)
        lf = drop_columns(lf, [workColumn])

        return lf if use_lazy else lf.collect()

    return df


def check_if_duplicate_variance_values(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict
) -> dict:
    """Check for duplicate variance rows lazily."""

    runParams = get_run_params()
    if not runParams["checkIfDuplicates"]:
        return paramDict

    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    varianceTypeName = namingParams["varianceTypeName"]

    lf = ensure_lazyframe(df)

    dup_lf = (
        lf.group_by([varianceAmountName, varianceTypeName])
        .agg(pl.len().alias("__cnt"))
        .filter(pl.col("__cnt") > 1)
        .with_columns((pl.col("__cnt") - 1).alias("__dup_cnt"))
    )

    dup_count = dup_lf.select(pl.col("__dup_cnt").sum()).collect().item() or 0
    total_len = lf.select(pl.len()).collect().item()

    if dup_count:
        message = (
            "Found "
            + str(int(dup_count))
            + " duplicate rows out of "
            + str(total_len)
            + " in dataset."
        )
        paramDict = add_warning_message_in_load_data_tab(paramDict, message)

    return paramDict


def get_cell_value_from_dataframe(
    df: pl.DataFrame | pl.LazyFrame, column: str, rowIndex: int, makeInt: bool
) -> int | float | str | None:
    """Return the value from ``df`` at ``rowIndex`` and ``column``."""

    if rowIndex < 0:
        return None

    if isinstance(df, pl.LazyFrame):
        try:
            slice_df = df.slice(rowIndex, 1).select(column).collect()
        except ColumnNotFoundError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None
        except KeyError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None
        except IndexError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None

        if get_row_count(slice_df) == 0:
            return None

        value = slice_df[column].item(0)
    else:
        if rowIndex >= get_row_count(df):
            return None

        try:
            value = df[column].item(rowIndex)
        except ColumnNotFoundError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None
        except KeyError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None
        except IndexError as e:
            
            ui.write("get_cell_value_from_dataframe error:", e)
            return None

    return int(value) if makeInt else value


def recalculate_price(
    df: pl.DataFrame | pl.LazyFrame, paramDict: dict
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Recompute unit prices after aggregation."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    unitsName = namingParams["unitsName"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    discountPerUnitName = namingParams["discountPerUnitName"]
    cogsPerUnitName = namingParams["cogsPerUnitName"]
    separatorString = namingParams["separatorString"]
    unitsColFound = namingParams["unitsColFound"]
    cogsColFound = namingParams["cogsColFound"]
    discountColFound = namingParams["discountColFound"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
    discountsAggregation = namingParams["discountsAggregation"]
    cogsAggregation = namingParams["cogsAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    isunitsColFound = paramDict[unitsColFound]
    isDiscountColFound = paramDict[discountColFound]
    isCogsColFound = paramDict[cogsColFound]
    periodsArray = configParams["periodsArray"]
    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
    discountPerUnitPeriodZero = discountPerUnitName + separatorString + periodsArray[0]
    discountPerUnitPeriodOne = discountPerUnitName + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    cogsPerUnitPeriodZero = cogsPerUnitName + separatorString + periodsArray[0]
    cogsPerUnitPeriodOne = cogsPerUnitName + separatorString + periodsArray[1]
    cogsPeriodZero = cogsName + separatorString + periodsArray[0]
    cogsPeriodOne = cogsName + separatorString + periodsArray[1]
    if isunitsColFound and unitsPeriodZero in columns:
        lf = lf.with_columns(
            pl.lit(0).alias(pricePeriodZero),
            pl.lit(0).alias(pricePeriodOne),
        )
        lf = round_value_columns_to_dec(
            lf, [amountPeriodZero, unitsPeriodZero, amountPeriodOne, unitsPeriodOne]
        )
        lf = lf.with_columns(
            pl.when(pl.col(unitsPeriodZero) > 0)
            .then(pl.col(amountPeriodZero) / pl.col(unitsPeriodZero))
            .otherwise(pl.col(pricePeriodZero))
            .alias(pricePeriodZero),
            pl.when(pl.col(unitsPeriodOne) > 0)
            .then(pl.col(amountPeriodOne) / pl.col(unitsPeriodOne))
            .otherwise(pl.col(pricePeriodOne))
            .alias(pricePeriodOne),
        )
        lf = round_value_columns_to_dec(lf, [pricePeriodZero, pricePeriodOne])
        if isDiscountColFound and discountPeriodZero in columns:
            lf = lf.with_columns(
                pl.lit(0).alias(discountPerUnitPeriodZero),
                pl.lit(0).alias(discountPerUnitPeriodOne),
            )
            lf = round_value_columns_to_dec(lf, [discountPeriodZero, discountPeriodOne])
            lf = lf.with_columns(
                pl.when(pl.col(unitsPeriodZero) > 0)
                .then(pl.col(discountPeriodZero) / pl.col(unitsPeriodZero))
                .otherwise(pl.col(discountPerUnitPeriodZero))
                .alias(discountPerUnitPeriodZero),
                pl.when(pl.col(unitsPeriodOne) > 0)
                .then(pl.col(discountPeriodOne) / pl.col(unitsPeriodOne))
                .otherwise(pl.col(discountPerUnitPeriodOne))
                .alias(discountPerUnitPeriodOne),
            )
            lf = round_value_columns_to_dec(
                lf, [discountPerUnitPeriodZero, discountPerUnitPeriodOne]
            )
        if isCogsColFound and cogsPeriodZero in columns:
            lf = lf.with_columns(
                pl.lit(0).alias(cogsPerUnitPeriodZero),
                pl.lit(0).alias(cogsPerUnitPeriodOne),
            )
            lf = round_value_columns_to_dec(lf, [cogsPeriodZero, cogsPeriodOne])

            lf = lf.with_columns(
                pl.when(pl.col(unitsPeriodZero) > 0)
                .then(pl.col(cogsPeriodZero) / pl.col(unitsPeriodZero))
                .otherwise(pl.col(cogsPerUnitPeriodZero))
                .alias(cogsPerUnitPeriodZero),
                pl.when(pl.col(unitsPeriodOne) > 0)
                .then(pl.col(cogsPeriodOne) / pl.col(unitsPeriodOne))
                .otherwise(pl.col(cogsPerUnitPeriodOne))
                .alias(cogsPerUnitPeriodOne),
            )
            lf = round_value_columns_to_dec(
                lf, [cogsPerUnitPeriodZero, cogsPerUnitPeriodOne]
            )
    return (lf if use_lazy else lf.collect()), paramDict


def divide_back_if_multiplied(df, paramDict, chartDict, divideCols, returnDictionary):
    """
    if the values have been multiplied by a constant in order to deal with
    decimal value calculations, we have to divide them back
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    isColumnMultiplied = namingParams["isColumnMultiplied"]
    varianceAmountName = namingParams["varianceAmountName"]
    runningTotalName = namingParams["runningTotalName"]
    varianceInPercent = namingParams["varianceInPercent"]
    varianceAggregation = namingParams["varianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    netMarginName = namingParams["netMarginName"]
    if isColumnMultiplied in paramDict and paramDict[isColumnMultiplied]:
        columns, schema = get_schema_and_column_names(df)
        for column in columns:
            if column in divideCols:
                if (
                    unitsName not in column
                    and volumeName not in column
                    and netMarginName not in column
                ):
                    if varianceInPercent in chartDict and chartDict[varianceInPercent]:
                        if chartDict[varianceAggregation] not in [
                            marginVarianceAggregation,
                            netOfDiscountAggregation,
                        ]:
                            if column != varianceAmountName:
                                df = df.with_columns(
                                    pl.when(pl.col(column) != 0)
                                    .then(pl.col(column) / multiplyConstant)
                                    .otherwise(pl.col(column))
                                    .alias(column)
                                )
                        else:
                            df = df.with_columns(
                                pl.when(pl.col(column) != 0)
                                .then(pl.col(column) / multiplyConstant)
                                .otherwise(pl.col(column))
                                .alias(column)
                            )
                    else:
                        df = df.with_columns(
                            pl.when(pl.col(column) != 0)
                            .then(pl.col(column) / multiplyConstant)
                            .otherwise(pl.col(column))
                            .alias(column)
                        )
        if returnDictionary:
            paramDict[isColumnMultiplied] = notMetConditionValue
    return df, paramDict


def get_year_totals(df, paramDict):
    """
    getting total revenue per year if not yet in paramdict
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    totalAmountPeriodZero = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOne = namingParams["totalAmountPeriodOne"]
    totalAmountPeriodZeroFilteredKey = namingParams["totalAmountPeriodZeroFiltered"]
    totalAmountPeriodOneFilteredKey = namingParams["totalAmountPeriodOneFiltered"]
    isFilteredKey = namingParams["isFilteredKey"]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]

    if totalAmountPeriodZero in paramDict:
        if isFilteredKey in paramDict and paramDict[isFilteredKey]:
            totalAmountPeriodZero = paramDict[
                namingParams["totalAmountPeriodZeroFiltered"]
            ]
        else:
            totalAmountPeriodZero = paramDict[namingParams["totalAmountPeriodZero"]]
    else:
        totalAmountPeriodZero = get_column_sum(df, amountPeriodZero)
    if totalAmountPeriodOne in paramDict:
        if isFilteredKey in paramDict and paramDict[isFilteredKey]:
            totalAmountPeriodOne = paramDict[
                namingParams["totalAmountPeriodOneFiltered"]
            ]
        else:
            totalAmountPeriodOne = paramDict[namingParams["totalAmountPeriodOne"]]
    else:
        totalAmountPeriodOne = get_column_sum(df, amountPeriodOne)
    return totalAmountPeriodZero, totalAmountPeriodOne


def calculate_change(
    df: pl.DataFrame | pl.LazyFrame,
    paramDict: dict,
    chartDict: dict,
    normalize: bool,
    *,
    as_lazy: bool = False,
) -> pl.DataFrame | pl.LazyFrame:
    """Compute normalized or percent change of the variance.

    Parameters
    ----------
    df:
        Data to operate on.
    paramDict:
        Parameter dictionary.
    chartDict:
        Dictionary describing chart options.
    normalize:
        When ``True`` compute normalized change, otherwise percent change.
    as_lazy:
        Return a ``LazyFrame`` when ``True`` regardless of input type.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    cogs_key = namingParams["cogsAggregationArray"]
    cogsAggregationArray = (
        cogs_key if isinstance(cogs_key, list) else varianceAggregationParams[cogs_key]
    )
    periodsArray = configParams["periodsArray"]
    varianceAmountName = namingParams["varianceAmountName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    marginName = namingParams["marginName"]
    varianceAggregation = namingParams["varianceAggregation"]
    separatorString = namingParams["separatorString"]
    variancePercentChange = namingParams["variancePercentChangeName"]
    varianceTypeName = namingParams["varianceTypeName"]
    totalVariance = namingParams["totalVariance"]
    if (
        varianceAggregation in chartDict
        and chartDict[varianceAggregation] in cogsAggregationArray
    ):
        marginPeriodZero = marginName + separatorString + periodsArray[0]
        marginPeriodOne = marginName + separatorString + periodsArray[1]
        periodZeroValue = marginPeriodZero
        periodOneValue = marginPeriodOne
    else:
        amountPeriodZero = monetaryName + separatorString + periodsArray[0]
        amountPeriodOne = monetaryName + separatorString + periodsArray[1]
        periodZeroValue = amountPeriodZero
        periodOneValue = amountPeriodOne
    maxPercentChange, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["maxPercentChange"], False
    )
    newVolumePercentChange, paramDict = get_dataset_specific_parameter(
        paramDict,
        namingParams["newVolumePercentChange"],
        False,
    )
    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf = lf.with_columns(pl.lit(np.nan).alias(variancePercentChange))
    lf = round_value_columns_to_dec(lf, [varianceAmountName, periodZeroValue])
    if normalize:
        lf = lf.with_columns(
            pl.when(pl.col(periodZeroValue) > 0)
            .then(
                (pl.col(periodOneValue) - pl.col(periodZeroValue)).abs()
                / ((pl.col(periodZeroValue) + pl.col(periodZeroValue)) / 2)
            )
            .otherwise(pl.col(variancePercentChange))
            .alias(variancePercentChange)
        )
        if maxPercentChange > 0:
            lf = lf.with_columns(
                pl.when(pl.col(variancePercentChange) > maxPercentChange)
                .then(maxPercentChange)
                .otherwise(pl.col(variancePercentChange))
                .alias(variancePercentChange)
            )
    else:
        lf = lf.with_columns(
            pl.when(pl.col(periodZeroValue) > 0)
            .then(
                (pl.col(periodOneValue) - pl.col(periodZeroValue))
                / pl.col(amountPeriodZero)
            )
            .when((pl.col(periodZeroValue) == 0) & (pl.col(periodOneValue) > 0))
            .then(0)
            .otherwise(pl.col(variancePercentChange))
            .alias(variancePercentChange)
        )
        lf = lf.with_columns(
            (pl.col(variancePercentChange) * 100).alias(variancePercentChange)
        )

    lf = lf.with_columns(
        pl.when(
            ~pl.col(varianceTypeName).is_in([totalVariance])
            & (pl.col(periodZeroValue) > 0)
        )
        .then(pl.col(varianceAmountName) / pl.col(periodZeroValue))
        .otherwise(pl.col(variancePercentChange))
        .alias(variancePercentChange)
    )
    lf = lf.with_columns(
        pl.when(pl.col(varianceAmountName) == 0)
        .then(0)
        .otherwise(pl.col(variancePercentChange))
        .alias(variancePercentChange)
    )
    return lf if use_lazy else lf.collect()


def check_if_duplicates_in_column_subset(
    df: pl.DataFrame | pl.LazyFrame, name: str, columns: list[str], paramDict: dict
) -> tuple[pl.DataFrame | pl.LazyFrame, dict]:
    """Return ``df`` unchanged while logging duplicate row warnings."""
    from modules.utilities.config import get_run_params

    runParams = get_run_params()
    if not runParams["checkIfDuplicates"]:
        return df, paramDict

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    # prefer helper to access available column names
    available_cols, _ = get_schema_and_column_names(lf)
    cols_to_abs = [c for c in columns if c in available_cols]
    if cols_to_abs:
        lf = lf.with_columns([pl.col(c).abs().alias(c) for c in cols_to_abs])

    stats_lf = (
        lf.group_by(columns).agg(pl.len().alias("__cnt")).filter(pl.col("__cnt") > 1)
    )

    duplicate_lf = lf.join(stats_lf.drop("__cnt"), on=columns, how="inner")

    dup_count = (
        stats_lf.with_columns((pl.col("__cnt") - 1).alias("__dup_cnt"))
        .select(pl.col("__dup_cnt").sum())
        .collect()
        .item()
    )
    df_len = lf.select(pl.len()).collect().item()

    if dup_count:
        paramDict = get_data_sample(duplicate_lf, name, False, paramDict)
        message = (
            "Found "
            + str(dup_count)
            + " duplicate rows out of "
            + str(df_len)
            + " in dataset."
        )
        paramDict = add_warning_message_in_load_data_tab(paramDict, message)

    return (df if not use_lazy else lf), paramDict
