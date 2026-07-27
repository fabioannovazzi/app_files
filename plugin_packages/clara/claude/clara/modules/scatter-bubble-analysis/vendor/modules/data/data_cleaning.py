import copy
import logging
from contextlib import nullcontext
from itertools import product

import polars as pl
import psutil
from ui.identify_columns_ui import show_input_data as ui_show_input_data

from modules.data.identify_columns import (
    build_initial_index_array,
    check_if_date_aggregation_is_year,
    filter_out_useless_periods,
    find_columns_and_manage_dates,
    find_date_and_period_columns,
    group_this_year_and_year_ago,
)
from modules.layout.filter_widgets import make_filter_dict
from modules.layout.manage_session import get_column_hash
from modules.layout.memoization import (
    check_collect,
    session_memoize_check_params,
)
from modules.layout.set_up_widgets import (
    set_up_date_parameters_widgets,
    set_up_main_report_widgets,
)
from modules.layout.widget_data_processing import (
    report_filter_column_error,
    select_index_columns_to_drop,
    warn_high_memory_usage,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import add_warning_message_in_period_options_tab
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    get_data_sample,
    group_by_df_on_index_cols,
    measure_time,
    round_value_columns_to_int,
    take_filtered_value_out_of_option_list,
    to_int,
    unique,
)
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui as notifier
from modules.utilities.utils import (
    ensure_lazyframe,
    get_row_count,
    get_schema_and_column_names,
    is_valid_lazyframe,
)


def use_volume_data_to_calculate_variance(df, paramDict, chartDict):
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    varianceAggregation = namingParams["varianceAggregation"]
    unitsColFound = namingParams["unitsColFound"]
    metConditionValue = namingParams["metConditionValue"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    if not paramDict[impossibleToProcessFile]:
        if (
            varianceAggregation in chartDict
            and volumeName.lower() in chartDict[varianceAggregation]
        ):
            columns, schema = get_schema_and_column_names(df)
            if volumeName in columns:
                # Polars-style assignment: replace/create `unitsName` from `volumeName`
                df = df.with_columns(pl.col(volumeName).alias(unitsName))
                paramDict[unitsColFound] = metConditionValue
    return df, paramDict


def delete_index_columns(
    df, indexCols, paramDict, chartDict, automateDict, valueCols, col
):
    """
    we delete the indexcolumns that the user has seletected for deletion
    """
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    correctPeriodAggregation = namingParams["correctPeriodAggregation"]
    chooseExcludeColumnsLabel = namingParams["chooseExcludeColumnsLabel"]
    chooseExcludeColumns = namingParams["chooseExcludeColumns"]
    hierarchicalName = namingParams["hierarchicalName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    selectAllLabel = namingParams["selectAllLabel"]
    periodName = namingParams["periodName"]
    varianceAggregationKey = namingParams["varianceAggregation"]
    processingChoiceKey = namingParams["processingChoice"]
    processingChoice = notMetConditionValue
    if processingChoiceKey in chartDict:
        processingChoice = chartDict[processingChoiceKey]
    if varianceAggregationKey in chartDict:
        varianceAggregation = chartDict[varianceAggregationKey]
    else:
        varianceAggregation = False
    toDrop = []
    if (
        varianceAggregation
        and paramDict[correctPeriodAggregation]
        and is_valid_lazyframe(df)
    ):
        if processingChoice == runVariableDimensionalAnalysis or (
            processingChoice == runOneDimensionalAnalysis
            and varianceAggregation
            not in [
                totalVarianceAggregation,
                marginVarianceAggregation,
                netOfDiscountAggregation,
            ]
        ):
            indexColsSelectBox = copy.deepcopy(indexCols)
            if periodName in indexColsSelectBox:
                indexColsSelectBox.remove(periodName)
                columnHash = paramDict[namingParams["columnHash"]]
                deleteIndexColsArray = select_index_columns_to_drop(
                    indexColsSelectBox,
                    periodName,
                    columnHash,
                    automateDict,
                    selectAllLabel,
                    chooseExcludeColumnsLabel,
                    chooseExcludeColumns,
                    processingChoice,
                    runVariableDimensionalAnalysis,
                    col,
                )
            if len(deleteIndexColsArray) > 0:
                for element in deleteIndexColsArray:
                    indexCols = take_filtered_value_out_of_option_list(
                        indexCols, element
                    )
                    toDrop.append(element)
                df = drop_columns(df, toDrop)
                df, paramDict = group_by_df_on_index_cols(
                    df, indexCols, valueCols, "sum", paramDict, False
                )
    else:
        pass
    return df, indexCols, toDrop, paramDict


def order_initial_columns(
    df: pl.DataFrame | pl.LazyFrame, var: list[str] | str
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with ``var`` columns first."""

    if isinstance(var, str):
        var = [var]

    columns, _schema = get_schema_and_column_names(df)
    varlist = [w for w in columns if w not in var]
    order = list(var) + varlist
    return df.select(order)


def set_order_for_output(
    df: pl.DataFrame | pl.LazyFrame, indexCols: list[str], paramDict: dict
) -> tuple[pl.LazyFrame, list[str]]:
    """Return ``df`` with output columns ordered for presentation."""

    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    runningTotalName = namingParams["runningTotalName"]
    varianceTypeName = namingParams["varianceTypeName"]
    variancePercentChange = namingParams["variancePercentChangeName"]

    df = ensure_lazyframe(df)

    df = df.with_columns(
        (pl.col(variancePercentChange) * 100).alias(variancePercentChange)
    )

    valueCols = [varianceAmountName, runningTotalName, variancePercentChange]
    orderedColumnArray = indexCols + [varianceTypeName] + valueCols
    df = order_initial_columns(df, orderedColumnArray)

    def _drop_all_null_columns(batch: pl.DataFrame) -> pl.DataFrame:
        null_counts = batch.null_count().row(0, named=True)
        row_cnt = get_row_count(batch)
        to_drop = [c for c, n in null_counts.items() if n == row_cnt]
        return batch.drop(to_drop) if to_drop else batch

    df = df.map_batches(_drop_all_null_columns, validate_output_schema=False)

    df = to_int(df, valueCols)
    return df, orderedColumnArray


def rename_columns_polars(df: pl.LazyFrame, mapping: dict[str, str]) -> pl.LazyFrame:
    """Return a LazyFrame with columns renamed according to the mapping."""

    return df.rename(mapping)


def clean_column_names_polars(df: pl.LazyFrame | pl.DataFrame) -> pl.LazyFrame:
    """Clean column names in a Polars LazyFrame."""

    if isinstance(df, pl.DataFrame):
        df = df.lazy()
    elif not isinstance(df, pl.LazyFrame):
        raise ValueError("Input must be a Polars LazyFrame")

    column_names, _ = get_schema_and_column_names(df)

    cleaned_names = [
        name.strip()
        .replace(",", "")
        .replace(".", "")
        .replace("'", "")
        .replace(" ", "_")
        .replace(":", "")
        .replace("-", "_")
        .replace("/", "_")
        .title()
        for name in column_names
    ]

    return rename_columns_polars(df, dict(zip(column_names, cleaned_names)))


def clean_dataset_polars(
    df: pl.LazyFrame | pl.DataFrame, paramDict: dict
) -> tuple[pl.LazyFrame, dict]:
    """Clean a dataset and return a LazyFrame along with ``paramDict``."""

    df = ensure_lazyframe(df)
    namingParams = get_naming_params()
    nothingThereString = namingParams["nothingThereString"]
    uniqueValuesInColumnDict = namingParams["uniqueValuesInColumnDict"]
    dropDuplicates = namingParams["dropDuplicates"]

    df = df.filter(~pl.all_horizontal(pl.all().is_null()))

    if paramDict.get(dropDuplicates):
        df = df.unique()

    df = df.with_columns(
        pl.col(pl.Utf8)
        .str.replace_all(r"\.|'|:", "")
        .str.strip_chars()
        .fill_null(nothingThereString)
    )

    column_names, _schema = get_schema_and_column_names(df)
    expressions = [pl.len().alias("_row_count")]
    expressions.extend(pl.col(c).null_count().alias(f"{c}_null") for c in column_names)
    expressions.extend(
        pl.col(c).drop_nulls().n_unique().alias(f"{c}_unique") for c in column_names
    )
    stats = df.select(expressions).collect().row(0, named=True)
    check_collect(
        "OAA" if paramDict.get(dropDuplicates) else "PAA", "column_stats", stats
    )

    row_count = stats.pop("_row_count")
    columns_to_keep = [
        c
        for c in column_names
        if stats[f"{c}_null"] < row_count and stats[f"{c}_unique"] > 1
    ]
    # Preserve joined attribute columns even if they currently have a single unique
    # value, so downstream charts can still reference them.
    attr_cols = session_state.get("attr_dimension_columns") or []
    if attr_cols:
        present = set(column_names)
        for c in attr_cols:
            if c in present and c not in columns_to_keep:
                columns_to_keep.append(c)
    df = df.select(columns_to_keep)

    paramDict[uniqueValuesInColumnDict] = {
        c: stats[f"{c}_unique"] for c in columns_to_keep
    }
    return df, paramDict


@session_memoize_check_params(check_diff=True)
def clean_dataset(df, paramDict, _cache_salt: str | None = None):
    """
    putting together two function to optimize session cache
    """
    df = clean_column_names_polars(df)
    try:  # one-time debug output to verify column cleaning
        logger = logging.getLogger(__name__)
        cols, _ = get_schema_and_column_names(df)
        logger.debug("data-cleaning: columns after clean_column_names_polars=%s", cols)
        flag = "_data_cleaning_logged"
        if logger.isEnabledFor(logging.DEBUG) and not session_state.get(flag):
            logger.debug(
                "data-cleaning debug – columns after cleaning: %s",
                cols,
            )
            session_state[flag] = True
    except Exception:
        logging.getLogger(__name__).exception(
            "data-cleaning: failed to record cleaned columns"
        )
    df, paramDict = clean_dataset_polars(df, paramDict)
    return df, paramDict


def _ensure_column_group(col_dict: dict, key: str, desired_len: int) -> list:
    cols = col_dict.get(key)
    if not isinstance(cols, list):
        cols = []
    while len(cols) < desired_len:
        cols.append(nullcontext())
    col_dict[key] = cols
    return cols


def prepare_and_process_data(
    paramDict,
    df,
    colDict,
    expanderDict,
    chartDict,
    automateDict,
    preserve_date_col: bool = False,
):
    """Clean dataset and compute period groupings.

    Parameters
    ----------
    preserve_date_col: bool, optional
        When ``True`` the original date column is preserved for downstream
        attribute-related workflows.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    dataPreparation = namingParams["dataPreparationName"]
    setTimePeriodTabKey = namingParams["setTimePeriodTab"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    foundDateAndPeriodCols = namingParams["foundDateAndPeriodColsName"]
    foundColumnAndManageDates = namingParams["foundColumnAndManageDatesName"]
    filterOutUselessPeriods = namingParams["filterOutUselessPeriodsName"]
    cleanedDfs = namingParams["cleanedDfsName"]
    loadDataTabKey = namingParams["loadDataTab"]
    joinDatasetTabKey = namingParams["joinDatasetTab"]
    colNumber = 0
    # Include attribute-dimension signature in the cache key for cleaning so
    # that joined Excel attributes or inferred dimensions invalidate stale
    # cached results that might have dropped these columns earlier.
    dims = session_state.get("attr_dimension_columns") or []
    # Stable, case-insensitive signature
    dims_sig = "|".join(sorted(str(c).lower() for c in dims)) if dims else ""
    dfCopy, paramDict = clean_dataset(df, paramDict, dims_sig)
    if "attr_merged_df_with_date" not in session_state:
        session_state["attr_merged_df_with_date"] = dfCopy.lazy()
    if "attr_merged_df" not in session_state:
        session_state["attr_merged_df"] = dfCopy.lazy()
    measure_time(dataPreparation, cleanedDfs, False)
    df = duplicate_dataframe(dfCopy)
    try:
        logging.getLogger(__name__).debug(
            "prep-data: columns after duplicate_dataframe=%s",
            get_schema_and_column_names(df)[0],
        )
    except Exception:
        pass
    paramDict = get_column_hash(df, paramDict)
    df, paramDict = find_date_and_period_columns(df, paramDict)
    try:
        logging.getLogger(__name__).debug(
            "prep-data: columns after find_date_and_period_columns=%s",
            get_schema_and_column_names(df)[0],
        )
    except Exception:
        pass
    measure_time(dataPreparation, foundDateAndPeriodCols, False)
    time_columns = _ensure_column_group(colDict, setTimePeriodTabKey, 4)
    chartDict, paramDict = set_up_date_parameters_widgets(
        df, paramDict, chartDict, automateDict, time_columns
    )

    measure_time(dataPreparation, "00450 - Set date parameter widgets", False)
    with time_columns[0]:
        (
            df,
            dfDates,
            paramDict,
            chartDict,
            periodLengthInMonths,
            mostRecentMonth,
            processDates,
        ) = find_columns_and_manage_dates(df, paramDict, chartDict)
        try:
            logging.getLogger(__name__).debug(
                "prep-data: columns after find_columns_and_manage_dates=%s",
                get_schema_and_column_names(df)[0],
            )
        except Exception:
            pass
        chartDict, paramDict = check_if_date_aggregation_is_year(
            df,
            chartDict,
            paramDict,
            periodLengthInMonths,
            mostRecentMonth,
            automateDict,
            processDates,
        )
        measure_time(dataPreparation, foundColumnAndManageDates, False)
        load_columns = _ensure_column_group(colDict, loadDataTabKey, 4)
        df, paramDict = ui_show_input_data(df, load_columns[3], paramDict)
        # df=df.lazy()
        df, dfPlan, paramDictCopy = group_this_year_and_year_ago(
            df,
            paramDict,
            chartDict,
            processDates,
            preserve_date_col=preserve_date_col,
        )
        try:
            logging.getLogger(__name__).debug(
                "prep-data: columns after group_this_year_and_year_ago=%s",
                get_schema_and_column_names(df)[0],
            )
        except Exception:
            pass
    measure_time(dataPreparation, "00550 - group this year and year ago", False)
    df, dfPeriods, dfAllPeriods, paramDictCopy, chartDict = filter_out_useless_periods(
        df, paramDictCopy, chartDict
    )
    try:
        logging.getLogger(__name__).debug(
            "prep-data: columns after filter_out_useless_periods=%s",
            get_schema_and_column_names(df)[0],
        )
    except Exception:
        pass
    measure_time(dataPreparation, filterOutUselessPeriods, False)
    variance_columns = _ensure_column_group(colDict, setVarianceOptionsTabKey, 3)
    paramDictCopy, chartDict = set_up_main_report_widgets(
        paramDictCopy,
        chartDict,
        automateDict,
        variance_columns,
        expanderDict[setVarianceOptionsTabKey],
    )
    df, paramDictCopy = use_volume_data_to_calculate_variance(
        df, paramDictCopy, chartDict
    )
    try:
        logging.getLogger(__name__).debug(
            "prep-data: columns before returning from prepare_and_process_data=%s",
            get_schema_and_column_names(df)[0],
        )
    except Exception:
        pass
    return df, dfDates, dfPeriods, dfAllPeriods, dfPlan, paramDictCopy, chartDict


def clean_and_group_by_data(paramDict, df):
    """
    opens  files and groups data
    """
    namingParams = get_naming_params()
    dataPreparation = namingParams["dataPreparationName"]
    dataGroupedOnIndexCols = namingParams["dataGroupedOnIndexColsName"]
    df, indexCols, valueCols, paramDict = build_initial_index_array(df, paramDict)
    try:
        logger = logging.getLogger(__name__)
        logger.debug(
            "data-cleaning: indexCols after build_initial_index_array=%s", indexCols
        )
    except Exception:
        pass
    if len(indexCols) > 0:
        df, paramDict = group_by_df_on_index_cols(
            df, indexCols, valueCols, "sum", paramDict, False
        )
        measure_time(dataPreparation, dataGroupedOnIndexCols, False)
        if is_valid_lazyframe(df):
            df, paramDict = multiply_decimal_values(df, valueCols, paramDict)
            measure_time(
                dataPreparation, "00920 Multiply_decimal_values - Converted", False
            )
            df = round_value_columns_to_int(df, valueCols)
            measure_time(
                dataPreparation, "00940 round_value_columns_to_int - Converted", False
            )
        else:
            # Return an empty Polars LazyFrame when grouping fails
            df = pl.LazyFrame()
    return df, indexCols, valueCols, paramDict


@session_memoize_check_params(check_diff=True)
def check_if_unit_and_amount_both_decimal(df, columns, paramDict):
    """
    if both the unit and the amount columns exist and have decimal values the multiplication of these two colums could
    create surprising results so we multiply. Otherwise no need to touch anything.
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    columns, schema = get_schema_and_column_names(df)
    # Validate logic condition (assuming this was the intended logic)
    if (unitsName in columns and monetaryName in columns) or (
        volumeName in columns and monetaryName in columns
    ):

        mustMultiply = True

        # Fill nulls for the involved columns first (if they exist)
        cols_to_check = [
            col for col in [unitsName, monetaryName, volumeName] if col in columns
        ]
        if cols_to_check:
            df = df.with_columns(
                [pl.col(col).fill_null(0).alias(col) for col in cols_to_check]
            )

            integrality_exprs = [
                pl.col(col).mod(1).eq(0).all() for col in cols_to_check
            ]
            any_integral_expr = pl.fold(
                pl.lit(False), lambda acc, x: acc | x, integrality_exprs
            )

            flag = df.select(any_integral_expr.alias("any_int")).collect().item()
            check_collect("ZAA", "any_int", flag)

            if flag:
                mustMultiply = False
    else:
        mustMultiply = False

    return mustMultiply, df


def multiply_decimal_values(df, valueCols, paramDict):
    """
    if a value column is not all ints, we multiply it by a large number so it can be converted to int
    we do it only for one column max
    we note that we have multiplied in paramdict so we can later divide
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    paramDict[namingParams["isColumnMultiplied"]] = False
    dataPreparation = namingParams["dataPreparationName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    cogsName = namingParams["cogsName"]
    marginName = namingParams["marginName"]
    columns, schema = get_schema_and_column_names(df)
    mustMultiply, df = check_if_unit_and_amount_both_decimal(df, columns, paramDict)
    measure_time(
        dataPreparation,
        "00910 - Check_if_unit_and_amount_both_decimal - Converted",
        False,
    )
    # Assuming `df` is a Polars LazyFrame and `columns` is a list of column names
    # Adjusted logic for lazy evaluation with Polars
    for column in [unitsName, monetaryName, volumeName]:
        if mustMultiply and column in columns:
            if not paramDict[namingParams["isColumnMultiplied"]]:
                if column == monetaryName:
                    # Multiply the monetaryName column
                    df = df.with_columns(
                        (pl.col(column) * multiplyConstant).alias(column)
                    )
                    # Update the parameter dictionary
                    paramDict[namingParams["isColumnMultiplied"]] = True

                    # Multiply additional columns if they exist
                    for element in [
                        discountName,
                        netOfDiscountName,
                        cogsName,
                        marginName,
                    ]:
                        if element in columns:
                            df = df.with_columns(
                                (pl.col(element) * multiplyConstant).alias(element)
                            )

    return df, paramDict


def check_date_aggregation(paramDict):
    """
    error if bad data aggregation
    """
    namingParams = get_naming_params()
    numberOfPeriodsFound = namingParams["numberOfPeriodsFound"]
    correctPeriodAggregation = namingParams["correctPeriodAggregation"]
    monthName = namingParams["monthName"]
    paramDict[correctPeriodAggregation] = True
    if numberOfPeriodsFound in paramDict and paramDict[numberOfPeriodsFound] == 1:
        message = """We identified a date column. However, the dataset contains data for only one year.
                    Year-over-year charts will not be plotted.
                    """
        paramDict = add_warning_message_in_period_options_tab(paramDict, message)
        paramDict[correctPeriodAggregation] = False
    return paramDict


def check_date_and_group_data(paramDict, df):
    """
    grouping function together for order
    """
    paramDict = check_date_aggregation(paramDict)
    df, indexCols, valueCols, paramDict = clean_and_group_by_data(paramDict, df)
    originalValueCols = copy.deepcopy(valueCols)
    paramDict = get_data_sample(df, "clean_and_group_by_data", False, paramDict)
    return df, indexCols, valueCols, paramDict, originalValueCols


@session_memoize_check_params(check_diff=True)
def get_top_hundred_items_per_column(
    df: pl.LazyFrame | pl.DataFrame | list[dict],
    indexCols: list[str],
    paramDict: dict,
) -> tuple[pl.LazyFrame, dict]:
    """Return ``df`` unchanged and update ``paramDict`` with a ``topWordDict`` entry.

    The function remains lazy throughout and materialises the result only once
    via ``collect(engine="streaming")`` to obtain the top 100 values per column. If
    the monetary column defined in the naming parameters is missing, the fallback
    strategy uses row counts instead of sums.
    """
    namingParams = get_naming_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    timeColArray = [dateName, periodName]
    topWordDictKey = namingParams["topWordDict"]

    # Ensure we operate on a lazy frame
    lf = ensure_lazyframe(df)

    # Check system memory usage
    mem = psutil.virtual_memory()
    used_memory_percent = mem.percent  # Percentage of RAM used

    # Set a threshold (e.g., 80%) to avoid crashes
    MEMORY_THRESHOLD = 25  # Adjust based on testing

    if used_memory_percent > MEMORY_THRESHOLD:
        warn_high_memory_usage(used_memory_percent)
        paramDict[topWordDictKey] = {
            col: [] for col in indexCols if col not in timeColArray
        }
        return lf, paramDict  # Return empty lists instead of crashing

    columns = [col for col in indexCols if col not in timeColArray]

    if not columns:
        paramDict[topWordDictKey] = {}
        return lf, paramDict

    try:
        all_columns, _schema = get_schema_and_column_names(lf)
        has_monetary = monetaryName in all_columns

        select_cols = columns + (
            [monetaryName] if has_monetary and monetaryName not in columns else []
        )

        if has_monetary:
            result = (
                lf.select(select_cols)
                .unpivot(
                    on=columns,
                    index=monetaryName,
                    variable_name="column",
                    value_name="value",
                )
                .group_by(["column", "value"])
                .agg(pl.col(monetaryName).sum().alias("sum"))
                .sort(["column", "sum"], descending=[False, True])
                .group_by("column")
                .agg(pl.col("value").head(100))
            )
        else:
            result = (
                lf.select(columns)
                .unpivot(variable_name="column", value_name="value")
                .group_by(["column", "value"])
                .agg(pl.len().alias("count"))
                .sort(["column", "count"], descending=[False, True])
                .group_by("column")
                .agg(pl.col("value").head(100))
            )

        collected = result.collect(engine="streaming")
        check_collect("AAD", "top 100", collected.head())

        topWordDict = dict(
            zip(collected["column"].to_list(), collected["value"].to_list())
        )
    except Exception as e:  # noqa: BLE001
        logging.exception(e)
        notifier.error("Something went wrong while extracting top words.")
        topWordDict = {}
        for column in columns:
            report_filter_column_error(column, e)
            topWordDict[column] = []

    paramDict[topWordDictKey] = topWordDict
    return lf, paramDict


def query_filter_dataframe_base(dfCopy, chartDict):
    """
    to make the cache work we duplicate the function
    """
    dfFiltered = query_filter_dataframe(dfCopy, chartDict)
    return dfFiltered


def query_filter_dataframe_periods(dfCopy, chartDict):
    """
    to make the cache work we duplicate the function
    """
    dfFiltered = query_filter_dataframe(dfCopy, chartDict)
    return dfFiltered


def query_filter_dataframe_dates(dfCopy, chartDict):
    """
    to make the cache work we duplicate the function
    """
    dfFiltered = query_filter_dataframe(dfCopy, chartDict)
    return dfFiltered


def query_filter_dataframe_all_periods(dfCopy, chartDict):
    """
    to make the cache work we duplicate the function
    """
    dfFiltered = query_filter_dataframe(dfCopy, chartDict)
    return dfFiltered


def query_filter_dataframe_plan(dfCopy, chartDict):
    """
    to make the cache work we duplicate the function
    """
    dfFiltered = query_filter_dataframe(dfCopy, chartDict)
    return dfFiltered


def query_filter_dataframe(df: pl.DataFrame, filter_dict: dict) -> pl.LazyFrame:
    """
    Filter strings in a Polars LazyFrame according to 'include' or 'exclude' lists
    in specified columns.

    Parameters
    ----------
    df : pl.DataFrame
        The input dataframe (will be converted to lazy).
    filter_dict : dict
        A dictionary defining which columns to filter on and what strings to include/exclude.
        Example:
            {
                "colA": {
                    "include": ["orange", "apple"],
                    "exclude": ["melon"]
                },
                "colB": {
                    "include": ["car"],
                    # no 'exclude' for colB
                }
            }

    Returns
    -------
    lf : pl.LazyFrame
        A Polars LazyFrame with all the specified filters applied. The function
        always returns a :class:`polars.LazyFrame` regardless of the input type.
    """
    df = ensure_lazyframe(df)
    namingParams = get_naming_params()
    numberFilterDictName = namingParams["numberFilterDictName"]
    toIncludeItems = namingParams["toIncludeItems"]
    toExcludeItems = namingParams["toExcludeItems"]
    columns, schema = get_schema_and_column_names(df)
    # Loop through each column in the filter_dict
    for col, rules in filter_dict.items():
        # If that column exists in df, apply the relevant filters
        if col in columns:
            # Include items
            if toIncludeItems in rules and rules[toIncludeItems]:
                df = df.filter(pl.col(col).is_in(rules[toIncludeItems]))
            # Exclude items
            if toExcludeItems in rules and rules[toExcludeItems]:
                df = df.filter(~pl.col(col).is_in(rules[toExcludeItems]))
    return df


def manage_filtering(
    df,
    indexCols,
    paramDict,
    chartDict,
    automateDict,
    valueCols,
    filterColArray,
    varianceColArray,
):
    namingParams = get_naming_params()
    dataPreparation = namingParams["dataPreparationName"]
    df, indexCols, toDrop, paramDict = delete_index_columns(
        df,
        indexCols,
        paramDict,
        chartDict,
        automateDict,
        valueCols,
        varianceColArray[1],
    )
    measure_time(dataPreparation, "01610 - Delete_index_columns - Converted", False)
    df, paramDict = get_top_hundred_items_per_column(df, indexCols, paramDict)
    measure_time(
        dataPreparation,
        "01620 - get_top_hundred_items_per_column - Converted",
        False,
    )
    paramDict, chartDict = make_filter_dict(
        df, indexCols, paramDict, chartDict, automateDict, filterColArray
    )
    df = query_filter_dataframe_base(df, chartDict[namingParams["filterDictName"]])
    measure_time(
        dataPreparation, "01640 - query_filter_dataframe_base - Converted", False
    )
    return df, indexCols, toDrop, paramDict, chartDict


def get_count_metric_names(chartDict, valueCols):
    namingParams = get_naming_params()
    countMetricsColumn = namingParams["countMetricsColumn"]
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    countMetricsSumArray = namingParams["countMetricsSumArray"]
    countMetricsSumDict = namingParams["countMetricsSumDict"]
    countMetricsAvgDict = namingParams["countMetricsAvgDict"]
    monetaryLocalCurrencyName = namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    marginName = namingParams["marginName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    numberOfName = namingParams["numberOfName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    if countMetricsColumn in chartDict:
        chartDict[countMetricsAvgArray] = []
        chartDict[countMetricsSumArray] = []
        chartDict[countMetricsSumDict] = {}
        chartDict[countMetricsAvgDict] = {}
        column = chartDict[countMetricsColumn]
        if column and column not in [None, nothingFilteredName]:
            chartDict[countMetricsSumArray].append(numberOfName + " " + column)
            chartDict[countMetricsSumDict][numberOfName + " " + column] = column
            if monetaryLocalCurrencyName in valueCols:
                chartDict[countMetricsAvgArray].append(
                    monetaryLocalCurrencyName + " by " + column
                )
                chartDict[countMetricsAvgDict][
                    monetaryLocalCurrencyName + " by " + column
                ] = monetaryLocalCurrencyName
            if unitsName in valueCols:
                chartDict[countMetricsAvgArray].append(unitsName + " by " + column)
                chartDict[countMetricsAvgDict][unitsName + " by " + column] = unitsName
            if volumeName in valueCols:
                chartDict[countMetricsAvgArray].append(volumeName + " by " + column)
                chartDict[countMetricsAvgDict][
                    volumeName + " by " + column
                ] = volumeName
            if netOfDiscountName in valueCols:
                metricName = netOfDiscountName + " by " + column
                chartDict[countMetricsAvgArray].append(metricName)
                chartDict[countMetricsAvgDict][metricName] = netOfDiscountName
            if marginName in valueCols:
                metricName = marginName + " by " + column
                chartDict[countMetricsAvgArray].append(metricName)
                chartDict[countMetricsAvgDict][metricName] = marginName
    return chartDict
