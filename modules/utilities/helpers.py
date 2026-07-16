import copy
import hashlib
import json
import logging
import re
import time
import traceback
from datetime import timedelta
from io import StringIO

import numpy as np
import polars as pl
import psutil
from dateutil.relativedelta import relativedelta

from modules.layout.memoization import (
    check_collect,
    session_memoize_check_params,
)
from modules.utilities.config import (
    get_config_params,
    get_file_params,
    get_image_params,
    get_naming_params,
    get_run_params,
)
from modules.utilities.notifier import Notifier, get_notifier

try:
    from modules.utilities.error_messages import (
        add_app_message_to_paramdict,
        add_warning_message_in_load_data_tab,
    )
except Exception as e:
    logging.exception(e)
    logging.error("Failed to import error message utilities")

    def add_app_message_to_paramdict(*_a, **_k):
        return {}

    def add_warning_message_in_load_data_tab(*_a, **_k):
        return {}


try:
    from modules.utilities.utils import (
        ensure_lazyframe,
        ensure_polars_df,
        get_schema_and_column_names,
        is_valid_lazyframe,
    )
except Exception as e:
    logging.exception(e)
    logging.error("Failed to import utility helpers")
    from modules.utilities.utils import (
        ensure_lazyframe,
        ensure_polars_df,
        get_schema_and_column_names,
    )

    def is_valid_lazyframe(obj: pl.DataFrame | pl.LazyFrame) -> bool:
        return isinstance(obj, (pl.DataFrame, pl.LazyFrame))


def is_numeric_dtype(dt: pl.DataType) -> bool:
    """Return ``True`` if ``dt`` is a numeric Polars data type."""
    if hasattr(pl.datatypes, "is_numeric_dtype"):
        return pl.datatypes.is_numeric_dtype(dt)  # type: ignore[attr-defined]
    return dt.is_numeric()


def hashForHelper(data):
    # Prepare the project id hash
    hashId = hashlib.md5()
    hashId.update(repr(data).encode("utf-8"))
    return hashId.hexdigest()


def show_error(label: str, exc: Exception) -> tuple[str, str]:
    """Format error details for UI display and log them."""
    message = f"💥 {label} crashed"
    details = print_error_details(exc)
    logging.info(message)
    logging.info(details)
    return message, details


def group_by_df_on_index_cols(
    df, indexCols, valueCols, operator, paramDict, convertBack
):
    """
    we group_by the df in order to avoid
    duplicate index. We index the dataframe on the multiindex
    """
    namingParams = get_naming_params()
    nothingThereString = namingParams["nothingThereString"]
    warningMessageType = namingParams["warningMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    try:
        if operator == "sum":
            df = (
                df.with_columns(pl.col(indexCols).fill_null(nothingThereString))
                .group_by(indexCols)
                .agg(pl.col(valueCols).sum())
                .filter(~pl.all_horizontal(pl.all().is_null()))
            )
        elif operator == "max":
            df = (
                df.with_columns(pl.col(indexCols).fill_null(0))
                .group_by(indexCols)
                .agg(pl.col(valueCols).max())
                .filter(~pl.all_horizontal(pl.all().is_null()))
            )
    except Exception as e:
        logging.exception(e)
        e = print_error_details(e)
        paramDict = add_app_message_to_paramdict(
            e,
            warningMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
        message = (
            "Unable to group_by on dimension columns "
            + str(indexCols)
            + ". Value cols are "
            + str(valueCols)
        )
        paramDict = add_app_message_to_paramdict(
            message,
            warningMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
    return df, paramDict


def start_index_at_one(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with a 1-based ``index`` column using Polars."""

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)
    lf = lf.with_row_index(name="index", offset=1)
    return lf if use_lazy else lf.collect()


def unique(items: list[str]) -> list[str]:
    """Return ordered unique values from ``items`` using Polars."""

    return pl.Series(items).unique().to_list()


def fill_null_zero(df, columns):
    """Return ``df`` with ``columns`` nulls replaced by zero using Polars."""

    if not isinstance(columns, list):
        columns = [columns]

    df_pl = ensure_polars_df(df)
    pl_columns, schema = get_schema_and_column_names(df_pl)
    exprs = [pl.col(c).fill_null(0).alias(c) for c in columns if c in pl_columns]
    if exprs:
        df_pl = df_pl.with_columns(exprs)
    return df_pl


def coerce_numeric_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Return *df* with:

    1. Columns that contain only numeric strings or ``None`` cast to ``Float64``.
    2. All numeric columns (existing or newly cast) having their nulls filled with 0.
    """
    df_pl = ensure_polars_df(df)
    columns, schema = get_schema_and_column_names(df_pl)
    exprs: list[pl.Expr] = []

    def _can_cast_to_float(col: str) -> bool:
        dt = schema[col]
        if is_numeric_dtype(dt):
            return False
        if dt not in {pl.Utf8, pl.Categorical}:
            return False
        try:
            sample = (
                df_pl.select(pl.col(col)).head(50).to_series()  # type: ignore[arg-type]
            )
        except Exception:  # pragma: no cover - defensive
            return False
        pattern = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
        for value in sample:
            if value is None:
                continue
            if isinstance(value, (int, float)):
                continue
            if isinstance(value, str) and pattern.match(value.strip()):
                continue
            return False
        return True

    # ── Cast any numeric‑string columns to Float64 ────────────────────────────────
    for col in columns:
        if _can_cast_to_float(col):
            exprs.append(pl.col(col).cast(pl.Float64).alias(col))

    if exprs:
        df_pl = df_pl.with_columns(exprs)

    # ── Fill nulls in *all* numeric columns (including the newly cast ones) ──────
    df_pl = df_pl.with_columns(
        pl.selectors.numeric().fill_null(0)  # only touches numeric dtypes
    )

    return df_pl


def replace_ibcs_date_symbol(title, chartDict):
    namingParams = get_naming_params()
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    periodToDate = namingParams["periodToDate"]
    chosenCohortColumn = namingParams["chosenCohortColumn"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    rollingPeriodSymbol = namingParams["rollingPeriodSymbol"]
    selectedPeriods = namingParams["selectedPeriods"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    pyName = namingParams["pyName"]
    fcName = namingParams["fcName"]
    toDateSymbol = namingParams["toDateSymbol"]
    if (
        rollingPeriodSymbol in title
        and compareWithYearBefore
        and chartDict[compareWithYearBefore]
    ):
        if (
            chosenCohortColumn in chartDict
            and chartDict[chosenCohortColumn] != nothingFilteredName
        ):
            title = replace_character(
                title,
                chartDict[chosenCohortColumn],
                rollingPeriodSymbol,
                "**12 rolling months** ",
            )
        else:
            title = title.replace(rollingPeriodSymbol, "**12 rolling months** ")
    elif (
        toDateSymbol in chartDict[selectedPeriods][0]
        and periodToDate
        and chartDict[periodToDate]
    ):
        if (
            chosenCohortColumn in chartDict
            and chartDict[chosenCohortColumn] != nothingFilteredName
        ):
            title = replace_character(
                title, chartDict[chosenCohortColumn], toDateSymbol, "**Year to Date** "
            )
        else:
            title = title.replace(toDateSymbol, "**Year to Date** ")
    elif (
        selectedPeriods in chartDict
        and acName in chartDict[selectedPeriods]
        and (
            plName in chartDict[selectedPeriods] or pyName in chartDict[selectedPeriods]
        )
    ):
        if acName in title:
            title = replace_character(
                title, chartDict[chosenCohortColumn], acName, "**Actual** "
            )
        if pyName in title:
            title = replace_character(
                title, chartDict[chosenCohortColumn], pyName, "**Previous Year** "
            )
        if plName in title:
            title = replace_character(
                title, chartDict[chosenCohortColumn], plName, "**Plan** "
            )
        if fcName in title:
            title = replace_character(
                title, chartDict[chosenCohortColumn], fcName, "**Forecast** "
            )
    elif acName + " vs " + pyName in title:
        title = replace_character(
            title,
            chartDict[chosenCohortColumn],
            acName + " vs " + pyName,
            "**Actual vs Previous Year** ",
        )
    elif acName + " vs " + plName in title:
        title = replace_character(
            title,
            chartDict[chosenCohortColumn],
            acName + " vs " + plName,
            "**Actual vs Plan** ",
        )
    title = (
        title.replace("<BR>", " ")
        .replace("<b>", " ")
        .replace("</b>", " ")
        .replace("  ", " ")
    )
    title = title.lstrip()
    return title


def replace_character(s, word, target_char, replace_char):
    # Define a regex pattern to match the target_char except when it follows the specified word
    pattern = re.compile(rf"(?<!{word}){re.escape(target_char)}")

    # Replace the matched target_char with replace_char
    result = pattern.sub(replace_char, s)

    return result


def list_drilldown_rows(drillDowndict):
    """
    we want a list of the select drilldown rows
    """
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    chosenDrilldownRow = namingParams["chosenDrilldownRow"]
    mainReportRunName = namingParams["mainReportRunName"]
    reportDict = {mainReportRunName: mainReportRunName}
    drillDownRowsArray = [mainReportRunName]
    for element in drillDowndict:
        if len(drillDowndict[element]) > 1:
            if chosenDrilldownRow in drillDowndict[element]:
                if drillDowndict[element][chosenDrilldownRow] not in drillDownRowsArray:
                    reportDict[drillDowndict[element][chosenDrilldownRow]] = element
                    drillDownRowsArray.append(
                        drillDowndict[element][chosenDrilldownRow]
                    )
    return reportDict, drillDownRowsArray


def place_other_rank_at_end(df, dimension, uniqueItems, cleanedPeriodOrder):
    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    periodName = namingParams["periodName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]

    lf = ensure_lazyframe(df)

    if dimension not in [nothingFilteredName, notMetConditionValue]:
        # Build ordered expressions for dimension and period columns
        dim_expr = pl.when(pl.col(dimension) == uniqueItems[0]).then(0)
        for idx, item in enumerate(uniqueItems[1:], start=1):
            dim_expr = dim_expr.when(pl.col(dimension) == item).then(idx)
        dim_expr = dim_expr.otherwise(len(uniqueItems))

        period_order = cleanedPeriodOrder[::-1]
        period_expr = pl.when(pl.col(periodName) == period_order[0]).then(0)
        for idx, item in enumerate(period_order[1:], start=1):
            period_expr = period_expr.when(pl.col(periodName) == item).then(idx)
        period_expr = period_expr.otherwise(len(period_order))

        lf = (
            lf.with_columns(
                [
                    dim_expr.alias(workColumn),
                    period_expr.alias(workColumnTwo),
                ]
            )
            .sort([workColumnTwo, workColumn])
            .drop([workColumn, workColumnTwo])
        )

    return lf


def change_column_names_if_cost_analysis(df, chartDict):
    namingParams = get_naming_params()
    datasetTypeKey = namingParams["datasetTypeName"]
    companySales = namingParams["companySales"]
    scanMarketData = namingParams["scanMarketData"]
    companyExpenses = namingParams["companyExpenses"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    costsName = namingParams["costsName"]
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
        monetaryName: costsName,
        pricePerUnitName: costPerUnitName,
        pricePerVolumeName: costPerVolumeName,
        pricePerUnitNetDiscountName: costPerUnitNetDiscountName,
        pricePerVolumeNetDiscountName: costPerVolumeNetDiscountName,
        netUnitsPriceChangeName: netUnitsCostChangeName,
        netVolumePriceChangeName: netVolumeCostChangeName,
    }
    if datasetTypeKey in chartDict and chartDict[datasetTypeKey] in [companyExpenses]:
        columns, schema = get_schema_and_column_names(df)
        renameDict = {}
        for column in columns:
            if monetaryName in column:
                newColumn = column.replace(monetaryName, costsName)
                renameDict[column] = newColumn

        if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
            df = pl.DataFrame(df)
        df = df.rename(renameDict)
        df = df.rename(metricDict)
    return df


def process_if_promo_data(df, paramDict, priceArray):
    """
    if file contains promo and no promo data columns we calculate the price in order
    to be able to plot stuff
    """
    namingParams = get_naming_params()
    unitPromoColFound = namingParams["unitPromoColFound"]
    monetaryPromoLocalCurrencyColFound = namingParams[
        "monetaryPromoLocalCurrencyColFound"
    ]
    unitNoPromoColFound = namingParams["unitNoPromoColFound"]
    monetaryNoPromoLocalCurrencyColFound = namingParams[
        "monetaryNoPromoLocalCurrencyColFound"
    ]
    monetaryPromoLocalCurrencyName = namingParams["monetaryPromoLocalCurrencyName"]
    monetaryNoPromoLocalCurrencyName = namingParams["monetaryNoPromoLocalCurrencyName"]
    unitsPromoName = namingParams["unitsPromoName"]
    unitsNoPromoName = namingParams["unitsNoPromoName"]
    promopricePerUnitName = namingParams["promopricePerUnitName"]
    noPromopricePerUnitName = namingParams["noPromopricePerUnitName"]
    foundPriceArray = copy.deepcopy(priceArray)
    if unitPromoColFound in paramDict and paramDict[unitPromoColFound]:
        if (
            monetaryPromoLocalCurrencyColFound in paramDict
            and paramDict[monetaryPromoLocalCurrencyColFound]
        ):
            df, foundPriceArray = calculate_unit_price_promo(
                df,
                monetaryPromoLocalCurrencyName,
                unitsPromoName,
                promopricePerUnitName,
                foundPriceArray,
            )
    if unitNoPromoColFound in paramDict and paramDict[unitNoPromoColFound]:
        if (
            monetaryNoPromoLocalCurrencyColFound in paramDict
            and paramDict[monetaryNoPromoLocalCurrencyColFound]
        ):
            df, foundPriceArray = calculate_unit_price_promo(
                df,
                monetaryNoPromoLocalCurrencyName,
                unitsNoPromoName,
                noPromopricePerUnitName,
                foundPriceArray,
            )
    return df, paramDict, foundPriceArray


def enable_draw_shapes(fig):
    fig.update_layout(
        dragmode="drawrect",
        # style of new shapes
        newshape=dict(
            line_color="#1E90FF",
            line_width=3,
        ),
    )
    return fig


def flatten_cols_polars(df: pl.DataFrame | pl.LazyFrame, delim: str = ""):
    """Flatten multiple column levels of the DataFrame into a single level.

    Parameters
    ----------
    df : pl.DataFrame or pl.LazyFrame
        DataFrame whose columns should be flattened.
    delim : str
        Delimiter used between the original column levels.

    Returns
    -------
    pl.DataFrame or pl.LazyFrame
        DataFrame with flattened column names.
    """

    new_cols = []
    columns, schema = get_schema_and_column_names(df)
    for col in columns:
        if isinstance(col, tuple):
            new_cols.append(delim.join(str(c) for c in col if c))
        else:
            new_cols.append(str(col))

    rename_map = dict(zip(columns, new_cols))
    return df.rename(rename_map)


def unstack_and_flatten_polars(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    """Unstack the period column and flatten the resulting DataFrame."""

    namingParams = get_naming_params()
    period_name = namingParams["periodName"]
    separator = namingParams["separatorString"]
    columns, schema = get_schema_and_column_names(df)
    value_cols = [c for c, dt in schema.items() if is_numeric_dtype(dt)]
    index_cols = [c for c in columns if c not in value_cols + [period_name]]

    df = df.pivot(period_name, index=index_cols, values=value_cols)
    df = flatten_cols_polars(df, separator)
    return df


def multi_index_df_polars(df: pl.DataFrame | pl.LazyFrame, index_cols):
    """Sort the DataFrame by the given columns."""

    return df.sort(index_cols)


def check_if_duplicates_in_all_columns(df, name, paramDict):
    runParams = get_run_params()
    checkIfDuplicates = runParams["checkIfDuplicates"]
    if checkIfDuplicates:
        from modules.utilities.utils import get_row_count

        dfCopy = duplicate_dataframe(df)
        dfLen = get_row_count(df)
        # Pandas-style duplicate filtering → idiomatic Polars
        if isinstance(df, pl.DataFrame):
            duplicateRowsDF = df.filter(df.is_duplicated())
        else:
            # LazyFrame or other: compute duplicates lazily, excluding first occurrence
            lf = ensure_lazyframe(df)
            columns, _ = get_schema_and_column_names(lf)
            lf_ord = lf.with_row_index("__ord")
            dup_keys = (
                lf_ord.group_by(columns)
                .agg([pl.len().alias("__cnt"), pl.col("__ord").min().alias("__first")])
                .filter(pl.col("__cnt") > 1)
                .drop(["__cnt"])
            )
            duplicateRowsDF = (
                lf_ord.join(dup_keys, on=columns, how="inner")
                .filter(pl.col("__ord") != pl.col("__first"))
                .drop(["__ord", "__first"])
            )
        nbrOfDuplicates = get_row_count(duplicateRowsDF)
        if nbrOfDuplicates != 0:
            paramDict = get_data_sample(duplicateRowsDF, name, False, paramDict)
            message = (
                "Found  "
                + str(nbrOfDuplicates)
                + " duplicate rows out of "
                + str(dfLen)
                + " in dataset."
            )
            paramDict = add_warning_message_in_load_data_tab(paramDict, message)
    return paramDict


def rename_columns_lazy(df, rename_dict):
    """
    Safely rename columns in a Polars DataFrame (lazy).
    Only rename if rename_dict is not empty.
    """
    if rename_dict:
        # Polars does not accept axis=1, just pass in the dict
        df = df.rename(rename_dict)
    return df


def determine_new_period_if_in_values(df, period):
    """
    If the given period only exists in period values with different casing,
    adjust the period accordingly to match what is found in the data.
    """
    period_values = get_periods_array(df)  # Should also be lazy-friendly
    period_lower = period.lower()
    period_upper = period.upper()

    if period in period_values:
        return period  # already correct
    elif period_lower in period_values:
        return period_lower
    elif period_upper in period_values:
        return period_upper
    return period


def maybe_build_rename_dict(columns, period):
    """
    Check if period exists in columns under a different case
    and build a rename dict if needed.
    """
    rename_dict = {}
    period_lower = period.lower()
    period_upper = period.upper()

    # If the lower or upper version exists in columns, rename to the original `period` case
    if period_lower in columns:
        rename_dict[period_lower] = period
    elif period_upper in columns:
        rename_dict[period_upper] = period

    return rename_dict


def check_if_periods_in_columns(df, period):
    """
    Ensures that the `period` column/values match the desired `period` case.
    1. If `period` or periodName is already a column, do nothing or only adjust the actual period value.
    2. Otherwise, if the same column is present in different case, rename it.
    """
    naming_params = get_naming_params()  # e.g., {"periodName": "some_period"}
    period_name = naming_params["periodName"]

    # Obtain columns and schema in whatever manner you prefer
    columns, schema = get_schema_and_column_names(df)

    # 1. If `period` is already a column, do nothing
    if period in columns:
        pass

    # 2. Else if `periodName` is a column, then check the data values
    elif period_name in columns:
        # Adjust the period if needed (e.g. if only period.lower() or period.upper() exist in values)
        period = determine_new_period_if_in_values(df, period)

    # 3. Otherwise, see if we should rename an existing column
    #    (like foo.lower() -> foo or foo.upper() -> foo)
    else:
        rename_dict = maybe_build_rename_dict(columns, period)
        df = rename_columns_lazy(df, rename_dict)

    return df, period


def add_running_total(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` with a running-total column added lazily."""

    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    runningTotalName = namingParams["runningTotalName"]
    normalizedStem = namingParams["normalizedStem"]

    use_lazy = isinstance(df, pl.LazyFrame)
    lf = ensure_lazyframe(df)

    columns, _ = get_schema_and_column_names(lf)
    normalizedCols = find_columns_by_stem(lf, normalizedStem, [], [])
    subset = [c for c in columns if c not in normalizedCols]

    lf = lf.unique(subset=subset)
    lf = lf.with_columns(pl.col(varianceAmountName).cum_sum().alias(runningTotalName))

    return lf if use_lazy else lf.collect()


def check_and_clean_columns(df, group_byCols, valueCols):
    """
    Deduplicate and verify that the columns in 'group_byCols' and 'valueCols'
    actually exist in the DataFrame, then return the cleaned lists.
    """
    columns, schema = get_schema_and_column_names(df)

    # Deduplicate while preserving order
    group_byCols = list(dict.fromkeys(group_byCols))
    valueCols = list(dict.fromkeys(valueCols))

    # Filter only the columns that actually exist in the DataFrame
    cleanedgroup_byCols = [col for col in group_byCols if col in columns]
    cleanedValueCols = [col for col in valueCols if col in columns]

    return cleanedgroup_byCols, cleanedValueCols


def check_and_group_by_cols(df, group_byCols, valueCols):
    group_byCols, valueCols = check_and_clean_columns(df, group_byCols, valueCols)
    df = df.group_by(group_byCols).agg(  # group_by columns
        [pl.col(col).sum() for col in valueCols]
    )  # aggregate
    return df, group_byCols, valueCols


def take_filtered_value_out_of_option_list(inputArray, filterColumn):
    """
    to take out the already filtered options from the option list not possible to use remove, need to create new array
    """
    newArray = []
    selectionArray = copy.deepcopy(inputArray)
    for element in selectionArray:
        if element != filterColumn:
            newArray.append(element)
    return newArray


def rank_columns_by_number_of_uniques(
    df: pl.LazyFrame, indexCols: list[str]
) -> tuple[list[str], list[str]]:
    """
    Return ``indexCols`` ranked by unique value count.

    Any columns missing from ``df`` are skipped. Two lists are returned: one
    sorted descending by unique count and the other ascending.
    """

    columns, _ = get_schema_and_column_names(df)
    valid_cols = [col for col in indexCols if col in columns]
    if not valid_cols:
        return [], []

    lf = ensure_lazyframe(df)
    unique_counts_lf = lf.select(
        [pl.col(col).n_unique().alias(col) for col in valid_cols]
    )

    unique_counts_dict = unique_counts_lf.collect().to_dicts()[0]
    check_collect("AFA", "unique_counts_dict", unique_counts_dict)

    sorted_desc = sorted(unique_counts_dict.items(), key=lambda x: x[1], reverse=True)

    descending_cols = [col for col, _ in sorted_desc]
    ascending_cols = list(reversed(descending_cols))

    return descending_cols, ascending_cols


def convert_df(df):
    """Return a CSV-encoded bytes representation of ``df``."""

    if isinstance(df, pl.LazyFrame):
        df = df.collect()

    if not isinstance(df, pl.DataFrame):
        raise ValueError(f"Unsupported data type for df: {type(df)}")

    buffer = StringIO()
    df.write_csv(buffer)
    return buffer.getvalue().encode("utf-8")


def simplify_chart_dictionary_keys(originalDict):
    simplifiedDict = {}
    keyMappingDict = {}
    count = 1
    if isinstance(originalDict, dict):
        for key in originalDict:
            simplifiedDict[str(count)] = originalDict[key]
            keyMappingDict[str(count)] = key
            count = count + 1
        return simplifiedDict, keyMappingDict
    else:
        return originalDict, originalDict


def insert_json_value(
    approach,
    defaultValue,
    automateDict,
    choiceArray,
    choiceKey,
    number,
    *,
    return_warning: bool = False,
):
    namingParams = get_naming_params()
    toIncludeItems = namingParams["toIncludeItems"]
    toExcludeItems = namingParams["toExcludeItems"]
    errorIcon = namingParams["errorIcon"]
    warningIcon = namingParams["warningIcon"]
    infoIcon = namingParams["infoIcon"]
    warning_message = None
    if approach == "index":
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                if automateDict[choiceKey] in choiceArray:
                    value = choiceArray.index(automateDict[choiceKey])
                elif (
                    isinstance(automateDict[choiceKey], list)
                    and automateDict[choiceKey][0] in choiceArray
                ):
                    value = choiceArray.index(automateDict[choiceKey][0])
                elif (
                    len(choiceArray) > 0
                    and isinstance(choiceArray[0], bool)
                    and choiceKey in automateDict
                    and choiceKey in automateDict
                    and isinstance(automateDict[choiceKey], str)
                ):
                    if automateDict[choiceKey] in ["true", "True"]:
                        automateDict[choiceKey] = True
                    elif automateDict[choiceKey] in ["false", "False"]:
                        automateDict[choiceKey] = False
                    if automateDict[choiceKey] in choiceArray:
                        value = choiceArray.index(automateDict[choiceKey])
                else:
                    warning_message = "Possible issues with chosen dimensions."
    elif approach == "numberInput":
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                value = automateDict[choiceKey]
        elif len(choiceArray) > 0 and len(choiceArray) > choiceKey:
            value = choiceArray[choiceKey]
    elif approach == "slider":
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                if len(choiceArray) > abs(automateDict[choiceKey]):
                    value = choiceArray[automateDict[choiceKey]]
    elif approach == "sliderStartOne":
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                if len(choiceArray) > abs(automateDict[choiceKey]):
                    value = choiceArray[automateDict[choiceKey] - 1]
    elif approach == "value":
        value = choiceArray[defaultValue]
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                if automateDict[choiceKey] in choiceArray:
                    value = automateDict[choiceKey]
                else:
                    value = choiceArray[0]
    elif approach == "input":
        value = choiceArray
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                value = automateDict[choiceKey]
    elif approach in ["checkbox"]:
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                value = automateDict[choiceKey]
    elif approach in ["array"]:
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                toTestValue = automateDict[choiceKey]
                if set(toTestValue).issubset(choiceArray):
                    value = toTestValue
    elif approach in ["condition"]:
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict:
                toTestValue = automateDict[choiceKey]
            else:
                toTestValue = automateDict
            if set(toTestValue).issubset(choiceArray):
                value = toTestValue
            else:
                value = None
    elif approach in ["filterColumn", toIncludeItems, toExcludeItems]:
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict and len(automateDict[choiceKey]) > 0:
                keyArray = list(automateDict[choiceKey].keys())
                if len(keyArray) > 0 and len(keyArray) >= number:
                    chosenKey = keyArray[number - 1]
                    if chosenKey in choiceArray and approach == "filterColumn":
                        value = choiceArray.index(chosenKey)
                    elif approach == toIncludeItems:
                        if toIncludeItems in automateDict[choiceKey][chosenKey]:
                            toTestValue = automateDict[choiceKey][chosenKey][
                                toIncludeItems
                            ]
                            if set(toTestValue).issubset(choiceArray):
                                value = toTestValue
                    elif approach == toExcludeItems:
                        if toExcludeItems in automateDict[choiceKey][chosenKey]:
                            toTestValue = automateDict[choiceKey][chosenKey][
                                toExcludeItems
                            ]
                            if set(toTestValue).issubset(choiceArray):
                                value = toTestValue
    elif approach in [toIncludeItems + "Slider", toExcludeItems + "Slider"]:
        value = defaultValue
        if len(automateDict) > 0:
            if choiceKey in automateDict and len(automateDict[choiceKey]) > 0:
                keyArray = list(automateDict[choiceKey].keys())
                if len(keyArray) > 0 and len(keyArray) >= number:
                    chosenKey = keyArray[number - 1]
                    if approach == toIncludeItems + "Slider":
                        if toIncludeItems in automateDict[choiceKey][chosenKey]:
                            value = automateDict[choiceKey][chosenKey][toIncludeItems]
                    elif approach == toExcludeItems + "Slider":
                        if toExcludeItems in automateDict[choiceKey][chosenKey]:
                            value = automateDict[choiceKey][chosenKey][toExcludeItems]
    if return_warning:
        return value, warning_message
    return value


def get_image_name_hash(dictionaryCopy, value, paramDict):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    hashValueKey = namingParams["hashValueName"]
    if len(dictionaryCopy) > 0 or len(str(value)) > 0:
        dictionary = copy.deepcopy(dictionaryCopy)
        if value is not None and value != "" and value is not False:
            dictionary[hashValueKey] = value
        hashValue = hashForHelper(dictionary)
    else:
        hashValue = ""
        message = "Could not generate image name hash."
        paramDict = add_warning_message_in_plot_charts_tab(paramDict, message)
    return hashValue, paramDict


def get_automate_dict(playback_dict, run_number):
    """Return the automation dictionary for ``run_number``.

    Parameters
    ----------
    playback_dict : dict
        Dictionary loaded from the playback JSON file.
    run_number : int | str
        Selected run number.

    Returns
    -------
    dict
        The dictionary of parameters for the chosen run or an empty
        dictionary if the run doesn't exist.
    """

    if not playback_dict:
        return {}

    key = str(run_number)
    return playback_dict.get(key, {})


def get_file_error_message(fileType):
    errorMessageDict = {"main": "file", "dimension": "dimension table"}
    messageDict = {
        "main": "The column separator must be either comma or semicolon. To specify the separator,click on the + sign under the upload widget.",
        "dimension": "The column separator must be either comma or semicolon, and must be the same used in your main file.",
    }
    errorMessage = (
        "There is something wrong with the format of the "
        + errorMessageDict[fileType]
        + " you are trying to upload. Make sure it in Excel or CSV (comma or semicolon delimited) format with UFT-8 or ANSI (ISO-8859-1) encoding."
    )
    message = (
        """Your uploaded file needs be in Excel or CSV format, with UTF 8 or ANSI (ISO-8859-1) encoding."""
        + messageDict[fileType]
        + """
            \nThe file name should not contain the "." (dot) character. For instance, if you file is called "test_07.01.2021.xlsx", rename it as something like "test_07_01_2021.xlsx."

           \nThe date column, if it exists, must be in "YYYY-MM-DD" format.
           \nThere are three ways to save your Excel file as a CSV with UTF-8 encoding:
            \n(1) With Excel:
            - Open your file in Excel and save as "CSV UTF-8 (Comma or Semicolon delimited)".
            \n(2) If this option is not available, still with Excel:
            - Open your file in Excel and save as CSV (Comma or Semicolon delimited). 
            - Scroll down and choose **Tools**. 
            - Choose **Web Options** from the **Tools** drop-down menu. 
            - Select the **Encoding** tab
            - Choose UTF-8 from the **Save this document as**: drop down menu
            - Select **OK**. 
            \n(3) If the above does not work, with Notepad:
            - Open the file with Notepad
            - File => Save As
            - Encoding choose "UTF-8"
            - Save
            Now your file is saved as a UTF-8 encoded CSV file :smile:.
            """
    )
    return message, errorMessage


def change_index_names_if_cost_analysis(df, chartDict):
    """Rename index-like string values to cost terminology using Polars.

    If ``df`` is a Polars ``DataFrame``/``LazyFrame``, this replaces occurrences
    of revenue-related metric names inside string columns with their cost
    counterparts. If a pandas-like object is passed (duck-typed via the presence
    of an ``index`` attribute), fall back to renaming index values via the
    object's ``rename(index=...)`` if available.
    """
    namingParams = get_naming_params()
    datasetTypeKey = namingParams["datasetTypeName"]
    companyExpenses = namingParams["companyExpenses"]

    if datasetTypeKey not in chartDict or chartDict[datasetTypeKey] not in [
        companyExpenses
    ]:
        return df

    monetaryName = namingParams["monetaryLocalCurrencyName"]
    costsName = namingParams["costsName"]
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

    replace_map = {
        monetaryName: costsName,
        pricePerUnitName: costPerUnitName,
        pricePerVolumeName: costPerVolumeName,
        pricePerUnitNetDiscountName: costPerUnitNetDiscountName,
        pricePerVolumeNetDiscountName: costPerVolumeNetDiscountName,
        netUnitsPriceChangeName: netUnitsCostChangeName,
        netVolumePriceChangeName: netVolumeCostChangeName,
    }

    # Polars path: replace in all string-like columns
    if isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        columns, schema = get_schema_and_column_names(df)
        string_cols = [c for c, dt in schema.items() if dt == pl.Utf8]
        if not string_cols:
            return df
        exprs: list[pl.Expr] = []
        for c in string_cols:
            expr = pl.col(c)
            for old, new in replace_map.items():
                expr = expr.str.replace_all(old, new)
            exprs.append(expr.alias(c))
        return df.with_columns(exprs)

    # Duck-typed pandas fallback (no pandas import)
    try:
        index_vals = getattr(getattr(df, "index", None), "to_list", lambda: None)()
        if index_vals is not None and hasattr(df, "rename"):
            rename_dict = {}
            for val in index_vals:
                new_val = val
                for old, new in replace_map.items():
                    if isinstance(new_val, str) and old in new_val:
                        new_val = new_val.replace(old, new)
                if new_val != val:
                    rename_dict[val] = new_val
            if rename_dict:
                # inplace to keep type/semantics
                df.rename(index=rename_dict, inplace=True)
                df.rename(index=replace_map, inplace=True)
            return df
    except Exception as e:
        logging.exception(e)
        pass

    return df


def add_promo_metric_to_valuecols(df, paramDict, valueColsCopy):
    """
    if file contains promo and no promo data columns add these metric to an array so we can plot them
    """
    namingParams = get_naming_params()
    unitPromoColFound = namingParams["unitPromoColFound"]
    monetaryPromoLocalCurrencyColFound = namingParams[
        "monetaryPromoLocalCurrencyColFound"
    ]
    unitNoPromoColFound = namingParams["unitNoPromoColFound"]
    monetaryNoPromoLocalCurrencyColFound = namingParams[
        "monetaryNoPromoLocalCurrencyColFound"
    ]
    monetaryPromoLocalCurrencyName = namingParams["monetaryPromoLocalCurrencyName"]
    monetaryNoPromoLocalCurrencyName = namingParams["monetaryNoPromoLocalCurrencyName"]
    unitsPromoName = namingParams["unitsPromoName"]
    unitsNoPromoName = namingParams["unitsNoPromoName"]
    valueCols = copy.deepcopy(valueColsCopy)
    if unitPromoColFound in paramDict and paramDict[unitPromoColFound]:
        if unitsPromoName not in valueCols:
            valueCols.append(unitsPromoName)
    if (
        monetaryPromoLocalCurrencyColFound in paramDict
        and paramDict[monetaryPromoLocalCurrencyColFound]
    ):
        if monetaryPromoLocalCurrencyName not in valueCols:
            valueCols.append(monetaryPromoLocalCurrencyName)
    if unitNoPromoColFound in paramDict and paramDict[unitNoPromoColFound]:
        if unitsNoPromoName not in valueCols:
            valueCols.append(unitsNoPromoName)
    if (
        monetaryNoPromoLocalCurrencyColFound in paramDict
        and paramDict[monetaryNoPromoLocalCurrencyColFound]
    ):
        if monetaryNoPromoLocalCurrencyName not in valueCols:
            valueCols.append(monetaryNoPromoLocalCurrencyName)
    return valueCols


def drop_rows_with_negative_values(df, colsArray, paramDict):
    """
    in some datasets negative amounts might not have sense and need to be set to zero
    """
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    dropZero = namingParams["dropZero"]
    dropNegative = namingParams["dropNegative"]
    dropZeroAndNegative = namingParams["dropZeroAndNegative"]
    monetaryLocalCurrencyName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    metConditionValue = namingParams["metConditionValue"]
    metricsArray = [unitsName, monetaryLocalCurrencyName]
    filterArray = []
    dropRowsWithNegativeValues, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["dropRowsWithNegativeValues"], False
    )
    columns, schema = get_schema_and_column_names(df)
    if dropRowsWithNegativeValues != nothingFilteredName:
        for column in colsArray:
            if column in metricsArray and column in columns:
                if column not in filterArray:
                    filterArray.append(column)

        is_lazy = isinstance(df, pl.LazyFrame)
        if is_lazy:
            lf = df
        else:
            lf = pl.DataFrame(df).lazy()

        for column in filterArray:
            if dropRowsWithNegativeValues == dropZero:
                condition = pl.col(column) != 0
            elif dropRowsWithNegativeValues == dropZeroAndNegative:
                condition = pl.col(column) > 0
            elif dropRowsWithNegativeValues == dropNegative:
                condition = pl.col(column) >= 0
            else:
                condition = None
            if condition is not None:
                lf = lf.filter(condition)

        df = lf if is_lazy else lf.collect()

    return df


def add_status_message_to_paramDict(paramDict, string, row):
    """
    check if key exists and add message
    """
    namingParams = get_naming_params()
    statusMessageArray = namingParams["statusMessageArray"]
    if statusMessageArray in paramDict:
        if string not in paramDict[statusMessageArray]:
            if isinstance(string, list):
                paramDict[statusMessageArray].append(string)
            elif len(paramDict[statusMessageArray]) > row:
                if string not in paramDict[statusMessageArray][row] and not isinstance(
                    paramDict[statusMessageArray][row], list
                ):
                    paramDict[statusMessageArray][row] = (
                        paramDict[statusMessageArray][row] + string
                    )
                elif string not in paramDict[statusMessageArray]:
                    paramDict[statusMessageArray].append(string)
    return paramDict


def get_period_length(df, paramDict, recalculate):
    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = (
        get_period_length_polars(df, paramDict, recalculate)
    )
    return paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths


def get_period_length_polars(df, paramDict, recalculate):
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    mostRecentDateKey = namingParams["mostRecentDate"]
    leastRecentDateKey = namingParams["leastRecentDate"]
    periodLengthInMonthsKey = namingParams["periodLengthInMonths"]
    columns, schema = get_schema_and_column_names(df)
    mostRecentDate, leastRecentDate, periodLengthInMonths = None, None, None
    if mostRecentDateKey in paramDict and not recalculate:
        mostRecentDate, leastRecentDate, periodLengthInMonths = (
            paramDict[mostRecentDateKey],
            paramDict[leastRecentDateKey],
            paramDict[periodLengthInMonthsKey],
        )
    elif dateName in columns:
        result = df.select(
            [
                pl.col(dateName).max().alias("most_recent_date"),
                pl.col(dateName).min().alias("least_recent_date"),
            ]
        ).collect()
        check_collect("SAA", "result", result)
        mostRecentDate = result[0, "most_recent_date"]
        leastRecentDate = result[0, "least_recent_date"]

        # Compute the timedelta as a Python `timedelta` object
        delta = mostRecentDate - leastRecentDate

        # `delta.days` gives you the integer number of days,
        # and `delta.total_seconds()` would give a more granular value if needed.
        delta_days = delta.days + (delta.seconds / 86400.0)

        # Approximate months by dividing by ~30.44 days/month
        periodLengthInMonths = delta_days / 30.44
        (
            paramDict[mostRecentDateKey],
            paramDict[leastRecentDateKey],
            paramDict[periodLengthInMonthsKey],
        ) = (mostRecentDate, leastRecentDate, periodLengthInMonths)
    return paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths


def get_periods_array(df: pl.DataFrame | pl.LazyFrame) -> list[str]:
    """Return unique period values if available."""

    naming_params = get_naming_params()
    period_name = naming_params["periodName"]
    columns, schema = get_schema_and_column_names(df)
    if period_name not in columns:
        return []

    expr = pl.col(period_name).unique().sort()
    if isinstance(df, pl.LazyFrame):
        periods_array = (
            df.select(expr)
            .collect(engine="streaming")
            .get_column(period_name)
            .to_list()
        )
        check_collect("AAE", "periodsArray", periods_array)
    else:
        periods_array = df.select(expr).get_column(period_name).to_list()

    return periods_array


def duplicate_dataframe(dfCopy: pl.DataFrame | pl.LazyFrame | object) -> pl.LazyFrame:
    """Return a duplicate of ``dfCopy`` converted to ``LazyFrame`` when possible.

    The function guarantees that ``pl.DataFrame`` inputs are cloned and returned
    as ``pl.LazyFrame`` instances.

    Parameters
    ----------
    dfCopy:
        Data to duplicate. Accepted types include ``LazyFrame`` and
        ``DataFrame``. Other sequence-like objects are converted via
        ``pl.DataFrame``.

    Returns
    -------
    pl.LazyFrame
        A lazy copy of ``dfCopy``.
    """

    if isinstance(dfCopy, pl.LazyFrame):
        return dfCopy
    if isinstance(dfCopy, pl.DataFrame):
        return dfCopy.clone().lazy()
    try:
        return pl.DataFrame(dfCopy).lazy()
    except Exception as e:  # noqa: BLE001
        logging.exception(e)
        raise TypeError(f"Unsupported object type: {type(dfCopy)!r}") from e


def get_date_columns_from_schema(schema):
    dateColumns1 = [
        col for col, dtype in schema.items() if isinstance(dtype, pl.Datetime)
    ]
    dateColumns2 = [col for col, dtype in schema.items() if dtype == pl.Date]
    dateColumns = dateColumns1 + dateColumns2
    return dateColumns


def drop_columns(df, to_drop):
    """Drop ``to_drop`` columns from a Polars ``DataFrame`` or ``LazyFrame``."""
    columns, schema = get_schema_and_column_names(df)
    if isinstance(df, pl.LazyFrame):
        existing = [c for c in to_drop if c in columns]
        return df.drop(existing)

    if not isinstance(df, pl.DataFrame):
        df = pl.DataFrame(df)

    existing = [c for c in to_drop if c in columns]
    return df.drop(existing)


def check_if_metrics_in_dataset(toCheckArray, promptDict):
    namingParams = get_naming_params()
    metricsArrayKey = namingParams["metricsArray"]
    checkedArray = []
    for element in toCheckArray:
        if element in promptDict[metricsArrayKey]:
            checkedArray.append(element)
    checkedArray = str(checkedArray).replace("[", "").replace("]", "").replace("'", "")
    return checkedArray


def print_error_details(error):
    runParams = get_run_params()
    printErrorDetails = runParams["printErrorDetails"]
    if printErrorDetails:
        error = traceback.format_exc()
    return error


def _save_recalculation_steps(
    dfCopy,
    name,
    count,
    numberOfRows,
    resetIndex,
    run,
    save,
    paramDict,
    notifier: Notifier | None = None,
):
    """
    for testing purposes we might want to save the content of the files for each loop
    """
    runParams = get_run_params()
    saveRecalculationSteps = runParams["saveRecalculationSteps"]
    namingParams = get_naming_params()
    loopNumber = namingParams["loopNumberName"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    colNumber = 0
    if saveRecalculationSteps or save:
        df = duplicate_dataframe(dfCopy)
        df.insert(0, loopNumber, count)
        if resetIndex:
            df = df.reset_index()
        if numberOfRows:
            df = df.head(numberOfRows)
        if count == 1 or count == None:
            firstTime = True
        else:
            firstTime = False
        try:
            paramDict = save_result(
                df, run + "_" + name, firstTime, "csv", False, paramDict
            )
        except Exception as e:  # noqa: BLE001
            logging.exception(e)
            get_notifier(notifier).error("Failed to save recalculation steps")
            e = print_error_details(e)
            paramDict = add_app_message_to_paramdict(
                e,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
    return paramDict


def save_result(df, fileName, firstTime, fileFormat, index, paramDict):
    """
    saves generated dataframe in output folder
    if problems, shows error message
    """
    fileParams = get_file_params()
    namingParams = get_naming_params()
    folderName = fileParams["folderName"]
    encodingUTF8 = fileParams["encodingUTF8"]
    infoMessageType = namingParams["infoMessageType"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    saveModeDict = {False: "a", True: "w"}
    path = folderName + "/" + fileName
    colNumber = 0

    if isinstance(df, pl.LazyFrame):
        df = df.collect()

    if not isinstance(df, pl.DataFrame):
        message = "Error saving file"
        return add_app_message_to_paramdict(
            message,
            errorMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )

    if fileFormat == "csv":
        try:
            mode = saveModeDict[firstTime]
            with open(path + ".csv", mode, encoding=encodingUTF8) as f:
                df.write_csv(f, include_header=firstTime)
            message = "Output file " + str(fileName) + ".csv saved"
            paramDict = add_app_message_to_paramdict(
                message,
                infoMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
        except Exception as e:
            logging.exception(e)
            e = print_error_details(e)
            paramDict = add_app_message_to_paramdict(
                e,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
            message = "Error saving " + str(fileName) + ".csv file"
            paramDict = add_app_message_to_paramdict(
                message,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
    else:
        message = "Error saving file"
        paramDict = add_app_message_to_paramdict(
            message,
            errorMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
    return paramDict


def get_data_sample(
    df, name, save, paramDict, notifier: Notifier | None = None
):
    """
    saves data sample to check data processed
    """
    runParams = get_run_params()
    saveDatasetSteps = runParams["saveDatasetSteps"]
    if saveDatasetSteps or save:
        dftest = duplicate_dataframe(df)
        size = 6000000
        try:
            dftest = dftest.head(size)
        except Exception as e:
            logging.exception(e)
            get_notifier(notifier).error("Failed to retrieve data sample")
        paramDict = save_result(dftest, name, True, "csv", False, paramDict)
    return paramDict


_timer_state = {"time": None, "start": None}


def log_memory() -> float:
    """Return the current system memory usage percentage."""
    mem = psutil.virtual_memory()
    return mem.percent


def measure_time(step, description, final):
    """Return timing and memory usage data for a processing step."""
    runParams = get_run_params()
    trackProcessingTime = runParams["trackProcessingTime"]
    trackMemoryUsage = runParams["trackMemoryUsage"]

    result = {"step": str(step), "description": description}

    if trackProcessingTime:
        current = time.time()
        if step == "start":
            _timer_state["time"] = current
            _timer_state["start"] = current
            result["time_delta"] = 0.0
        else:
            if _timer_state["time"] is None:
                _timer_state["time"] = current
                _timer_state["start"] = current
            result["time_delta"] = current - _timer_state["time"]
            _timer_state["time"] = current
            if final:
                result["total_time"] = current - _timer_state["start"]

    if trackMemoryUsage:
        result["memory_percent"] = log_memory()

    return result


def get_dataset_specific_parameter(paramDict, firstKey, secondKey):
    """
    if a dataset has a specific parameter we take it otherwise we use the default
    if the specific parameter is an array, we combine the two array, otherwise we substitute
    """
    configParams = get_config_params()
    if firstKey in paramDict and not secondKey:
        parameterValue = paramDict[firstKey]
    elif firstKey in paramDict and secondKey and secondKey in paramDict[firstKey]:
        copyDict = copy.deepcopy(configParams[firstKey][secondKey])
        for element in paramDict[firstKey][secondKey]:
            if isinstance(paramDict[firstKey][secondKey][element], list):
                copyDict[element] = (
                    copyDict[element] + paramDict[firstKey][secondKey][element]
                )
                copyDict[element] = list(set(copyDict[element]))
            else:
                copyDict[element] = paramDict[firstKey][secondKey][element]
        parameterValue = copyDict
    else:
        if not secondKey:
            parameterValue = configParams[firstKey]
            paramDict[firstKey] = parameterValue
        elif secondKey:
            parameterValue = configParams[firstKey][secondKey]
            if firstKey not in paramDict:
                paramDict[firstKey] = {}
            paramDict[firstKey][secondKey] = parameterValue
    return parameterValue, paramDict


def to_int(
    df: pl.DataFrame | pl.LazyFrame, array: list[str]
) -> pl.DataFrame | pl.LazyFrame:
    """Fill null values with zero and optionally round columns."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    roundValues = configParams[namingParams["roundValues"]]

    use_lazy = isinstance(df, pl.LazyFrame)
    df_pl = ensure_lazyframe(df) if use_lazy else ensure_polars_df(df)

    exprs: list[pl.Expr] = []
    columns, schema = get_schema_and_column_names(df_pl)
    for element in array:
        if element in columns:
            expr = pl.col(element).fill_null(0)
            if roundValues:
                expr = expr.round(2)
            exprs.append(expr.alias(element))

    if exprs:
        df_pl = df_pl.with_columns(exprs)

    return df_pl


def to_round(
    df: pl.DataFrame | pl.LazyFrame, array: list[str]
) -> pl.DataFrame | pl.LazyFrame:
    """Fill null values with zero and optionally round columns."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    roundValues = configParams[namingParams["roundValues"]]

    use_lazy = isinstance(df, pl.LazyFrame)
    df_pl = ensure_lazyframe(df) if use_lazy else ensure_polars_df(df)

    exprs: list[pl.Expr] = []
    columns, schema = get_schema_and_column_names(df_pl)
    for element in array:
        if element in columns:
            expr = pl.col(element).fill_null(0)
            if roundValues:
                expr = expr.round(2)
            exprs.append(expr.alias(element))

    if exprs:
        df_pl = df_pl.with_columns(exprs)

    return df_pl


def find_columns_by_stem(df, stem, array, excludeArray):
    columns, schema = get_schema_and_column_names(df)
    for column in columns:
        if stem in column and column not in excludeArray:
            array.append(column)
    return array


def check_value_column_exist(df, valueCols):
    checkedValueCols = []
    columns = get_column_names(df)
    for column in valueCols:
        if column in columns:
            checkedValueCols.append(column)
    return checkedValueCols


def round_other_columns(df, orderedColumnArray):
    """
    we round the other columns as required
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    marginName = namingParams["marginName"]
    netMarginName = namingParams["netMarginName"]
    cwdName = namingParams["categoryWeightedDistributionName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    indirectCostsName = namingParams["indirectCostsName"]
    visitsName = namingParams["visitsName"]
    checkoutsName = namingParams["checkoutsName"]
    volumeColsArray, monetaryColsArray, discountColsArray, cogsColsArray = (
        [],
        [],
        [],
        [],
    )
    marginColsArray, priceColsArray, cwdColsArray, visitsColsArray = [], [], [], []
    indirectCostArray, checkoutsColsArray, netMarginColsArray = [], [], []
    volumeColsArray = find_columns_by_stem(
        df, unitsName, volumeColsArray, orderedColumnArray
    )
    monetaryColsArray = find_columns_by_stem(
        df, monetaryName, monetaryColsArray, orderedColumnArray
    )
    discountColsArray = find_columns_by_stem(
        df, discountName, discountColsArray, orderedColumnArray
    )
    cogsColsArray = find_columns_by_stem(
        df, cogsName, cogsColsArray, orderedColumnArray
    )
    marginColsArray = find_columns_by_stem(
        df, marginName, marginColsArray, orderedColumnArray
    )
    netMarginColsArray = find_columns_by_stem(
        df, netMarginName, netMarginColsArray, orderedColumnArray
    )
    priceColsArray = find_columns_by_stem(
        df, pricePerUnitName, priceColsArray, orderedColumnArray
    )
    cwdColsArray = find_columns_by_stem(df, cwdName, cwdColsArray, orderedColumnArray)
    visitsColsArray = find_columns_by_stem(
        df, visitsName, visitsColsArray, orderedColumnArray
    )
    checkoutsColsArray = find_columns_by_stem(
        df, checkoutsName, checkoutsColsArray, orderedColumnArray
    )
    indirectCostArray = find_columns_by_stem(
        df, indirectCostsName, indirectCostArray, orderedColumnArray
    )
    otherNumericCols = (
        volumeColsArray + monetaryColsArray + discountColsArray + cogsColsArray
    )
    otherNumericCols = (
        otherNumericCols
        + marginColsArray
        + cwdColsArray
        + visitsColsArray
        + checkoutsColsArray
    )
    otherNumericCols = otherNumericCols + netMarginColsArray + indirectCostArray
    df = to_int(df, otherNumericCols)
    df = to_round(df, priceColsArray)
    return df, otherNumericCols, priceColsArray


def round_value_columns_to_int(df, array):
    """
    to avoid issues, we at the moment we only consider datasets with integer (no decimal) values
    """
    df = round_value_columns(df, array, 0)
    return df


def round_value_columns_to_dec(df, array):
    """
    to avoid issues, we at the moment we only consider datasets with integer (no decimal)
    """
    df = round_value_columns(df, array, 2)
    return df


def round_value_columns(df, array, rounding):
    """
    all rounding in one place
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    roundValues = configParams[namingParams["roundValues"]]
    columns, schema = get_schema_and_column_names(df)
    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        df_pl = pl.DataFrame(df)
    else:
        df_pl = df
    if roundValues:
        df_pl = df_pl.with_columns(
            [
                pl.col(col).fill_null(0).round(rounding)
                for col in array
                if col in columns
            ]
        )
    else:
        df_pl = df_pl.with_columns(
            [pl.col(col).fill_null(0) for col in array if col in columns]
        )
    df = df_pl
    return df


def calculate_unit_and_volume_price_polars(df, paramDict, array):
    """
    if we do not have it already, we calculare the unit price
    """
    namingParams = get_naming_params()
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    unitsColFound = namingParams["unitsColFound"]
    volumeName = namingParams["volumeName"]
    monetaryColFound = namingParams["monetaryLocalCurrencyColFound"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    volumeColFound = namingParams["volumeColFound"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    discountColFound = namingParams["discountColFound"]
    marginName = namingParams["marginName"]
    marginColFound = namingParams["marginColFound"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    isVolumeColFound = paramDict[volumeColFound]
    isUnitsColFound = paramDict[unitsColFound]
    isDiscountColFound = paramDict[discountColFound]
    isMarginColFound = paramDict[marginColFound]
    isMonetaryColFound = paramDict[monetaryColFound]
    columns, schema = get_schema_and_column_names(
        df
    )  # Assuming this returns column names and schema info

    # If round_value_columns_to_dec is a custom function, ensure it returns a LazyFrame:
    # def round_value_columns_to_dec(lf: pl.LazyFrame, cols: list[str]) -> pl.LazyFrame:
    #     # Example: rounding to 2 decimals
    #     return lf.with_columns([pl.col(c).round(2).alias(c) for c in cols])

    if isUnitsColFound and unitsName in columns:
        # Round monetaryName and unitsName
        df = round_value_columns_to_dec(df, [monetaryName, unitsName])
        # Replace 0 with None in unitsName
        df = df.with_columns(
            pl.when(pl.col(unitsName) == 0)
            .then(None)
            .otherwise(pl.col(unitsName))
            .alias(unitsName)
        )
        # Compute pricePerUnitName = monetaryName / unitsName
        df = df.with_columns(
            (pl.col(monetaryName) / pl.col(unitsName)).alias(pricePerUnitName)
        )
        if pricePerUnitName not in array:
            array.append(pricePerUnitName)

    if isVolumeColFound and volumeName in columns:
        # Round monetaryName and volumeName
        df = round_value_columns_to_dec(df, [monetaryName, volumeName])
        # Replace 0 with None in volumeName
        df = df.with_columns(
            pl.when(pl.col(volumeName) == 0)
            .then(None)
            .otherwise(pl.col(volumeName))
            .alias(volumeName)
        )
        # Compute pricePerVolumeName = monetaryName / volumeName
        df = df.with_columns(
            (pl.col(monetaryName) / pl.col(volumeName)).alias(pricePerVolumeName)
        )
        if pricePerVolumeName not in array:
            array.append(pricePerVolumeName)

    if isDiscountColFound and isUnitsColFound and unitsName in columns:
        # Round netOfDiscountName and unitsName
        df = round_value_columns_to_dec(df, [netOfDiscountName, unitsName])
        # Replace 0 with None in unitsName
        df = df.with_columns(
            pl.when(pl.col(unitsName) == 0)
            .then(None)
            .otherwise(pl.col(unitsName))
            .alias(unitsName)
        )
        # pricePerUnitNetDiscountName = netOfDiscountName / unitsName
        df = df.with_columns(
            (pl.col(netOfDiscountName) / pl.col(unitsName)).alias(
                pricePerUnitNetDiscountName
            )
        )
        if pricePerUnitNetDiscountName not in array:
            array.append(pricePerUnitNetDiscountName)

        # Replace 0 with None in amountName
        df = df.with_columns(
            pl.when(pl.col(amountName) == 0)
            .then(None)
            .otherwise(pl.col(amountName))
            .alias(amountName)
        )
        # discountInPercentName = discountName / amountName
        df = df.with_columns(
            (pl.col(discountName) / pl.col(amountName)).alias(discountInPercentName)
        )
        if discountInPercentName not in array:
            array.append(discountInPercentName)

    if isDiscountColFound and isVolumeColFound and volumeName in columns:
        # Round netOfDiscountName and volumeName
        df = round_value_columns_to_dec(df, [netOfDiscountName, volumeName])
        # Replace 0 with None in volumeName
        df = df.with_columns(
            pl.when(pl.col(volumeName) == 0)
            .then(None)
            .otherwise(pl.col(volumeName))
            .alias(volumeName)
        )
        # pricePerVolumeNetDiscountName = netOfDiscountName / volumeName
        df = df.with_columns(
            (pl.col(netOfDiscountName) / pl.col(volumeName)).alias(
                pricePerVolumeNetDiscountName
            )
        )
        if pricePerVolumeNetDiscountName not in array:
            array.append(pricePerVolumeNetDiscountName)

        # discountInPercentName = discountName / amountName
        df = df.with_columns(
            (pl.col(discountName) / pl.col(amountName)).alias(discountInPercentName)
        )
        if discountInPercentName not in array:
            array.append(discountInPercentName)

    if marginName in columns and amountName in columns:
        # Round marginName and amountName
        df = round_value_columns_to_dec(df, [marginName, amountName])
        # Replace 0 with None in amountName
        df = df.with_columns(
            pl.when(pl.col(amountName) == 0)
            .then(None)
            .otherwise(pl.col(amountName))
            .alias(amountName)
        )
        # marginInPercentName = marginName / amountName
        df = df.with_columns(
            (pl.col(marginName) / pl.col(amountName)).alias(marginInPercentName)
        )
        if marginInPercentName not in array:
            array.append(marginInPercentName)

    if marginName in columns and amountName in columns and netOfDiscountName in columns:
        # Round marginName and amountName
        df = round_value_columns_to_dec(df, [marginName, amountName])
        # Replace 0 with None in netOfDiscountName
        df = df.with_columns(
            pl.when(pl.col(netOfDiscountName) == 0)
            .then(None)
            .otherwise(pl.col(netOfDiscountName))
            .alias(netOfDiscountName)
        )
        # marginInPercentOfNetSalesName = marginName / netOfDiscountName
        df = df.with_columns(
            (pl.col(marginName) / pl.col(netOfDiscountName)).alias(
                marginInPercentOfNetSalesName
            )
        )
        if marginInPercentOfNetSalesName not in array:
            array.append(marginInPercentOfNetSalesName)

    array.sort()
    return df, paramDict, array


def calculate_unit_and_volume_price(df, paramDict, array):
    """Calculate unit and volume prices using Polars."""
    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        df_pl = pl.DataFrame(df)
    else:
        df_pl = df

    df_pl, paramDict, array = calculate_unit_and_volume_price_polars(
        df_pl, paramDict, array
    )

    df = df_pl
    return df, paramDict, array


def calculate_discount_per_units_and_volume(df, paramDict):
    """
    if we do not have it already, we calculare discount per unit
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    discountPerUnitName = namingParams["discountPerUnitName"]
    discountName = namingParams["discountName"]
    discountColFound = namingParams["discountColFound"]
    unitsColFound = namingParams["unitsColFound"]
    volumeName = namingParams["volumeName"]
    discountPerVolumeName = namingParams["discountPerVolumeName"]
    volumeColFound = namingParams["volumeColFound"]
    columns, schema = get_schema_and_column_names(df)
    isVolumeColFound = paramDict[volumeColFound]
    isUnitsColFound = paramDict[unitsColFound]
    isDiscountColFound = paramDict[discountColFound]
    if isDiscountColFound and isUnitsColFound:
        df = round_value_columns_to_dec(df, [discountName])
        df = df.with_columns(
            (pl.col(discountName) / pl.col(unitsName)).alias(discountPerUnitName)
        )

    if isDiscountColFound and isVolumeColFound:
        df = round_value_columns_to_dec(df, [discountName])
        df = df.with_columns(
            (pl.col(discountName) / pl.col(volumeName)).alias(discountPerVolumeName)
        )
    return df, paramDict


def calculate_cogs_per_units_and_volume(df, paramDict):
    """
    if we do not have it already, we calculare cogs per unit
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    cogsPerUnitName = namingParams["cogsPerUnitName"]
    cogsName = namingParams["cogsName"]
    cogsColFound = namingParams["cogsColFound"]
    unitsColFound = namingParams["unitsColFound"]
    volumeName = namingParams["volumeName"]
    cogsPerVolumeName = namingParams["cogsPerVolumeName"]
    volumeColFound = namingParams["volumeColFound"]
    columns, schema = get_schema_and_column_names(df)
    isVolumeColFound = paramDict[volumeColFound]
    isUnitsColFound = paramDict[unitsColFound]
    isCogsColFound = paramDict[cogsColFound]
    if isCogsColFound and isUnitsColFound and unitsName in columns:
        df = round_value_columns_to_dec(df, [cogsName])
        df = df.with_columns(
            (pl.col(cogsName) / pl.col(unitsName)).alias(cogsPerUnitName)
        )

    if isCogsColFound and isVolumeColFound and volumeName in columns:
        df = round_value_columns_to_dec(df, [cogsName])
        df = df.with_columns(
            (pl.col(cogsName) / pl.col(volumeName)).alias(cogsPerVolumeName)
        )
    return df, paramDict


def pivot_lazy_periods(
    df_lazy: pl.LazyFrame,
    index_cols: list[str],
    agg_func: str = "first",  # or "sum", "mean", etc.
) -> pl.DataFrame:
    """
    Encapsulate the entire lazy pivot logic and return a final DataFrame.
    """
    # 1) Map the agg_func name to a polars expression function
    #    Expand this dictionary if you have more aggregates you need to support.
    configParams = get_config_params()
    known_pivot_values = configParams["periodsArray"]
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    pivot_col = periodName
    value_cols = []
    columns, schema = get_schema_and_column_names(df_lazy)
    for col in columns:
        if col not in index_cols:
            value_cols.append(col)
    if pivot_col in index_cols:
        index_cols.remove(pivot_col)
    agg_map = {
        "first": lambda col: col.first(),
        "sum": lambda col: col.sum(),
        "mean": lambda col: col.mean(),
        "count": lambda col: col.count(),
    }
    aggregator = agg_map[agg_func]

    # 2) Construct the lazy pivot using group_by and conditional aggregates.
    pivoted_lazy = df_lazy.group_by(index_cols).agg(
        [
            aggregator(pl.col(val).filter(pl.col(pivot_col) == pivot_val)).alias(
                f"{val}_{pivot_val}"
            )
            for val in value_cols
            for pivot_val in known_pivot_values
        ]
    )

    # 3) Collect (materialize) and return a final DataFrame
    return pivoted_lazy


def add_price_to_value_cols(valueCols, df):
    """
    add price to index cols array
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    volumeName = namingParams["volumeName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    marginName = namingParams["marginName"]
    columns, schema = get_schema_and_column_names(df)
    valueColsWithPrice = copy.deepcopy(valueCols)
    if unitsName in columns and amountName in columns:
        if pricePerUnitName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, pricePerUnitName)
    if volumeName in columns and amountName in columns:
        if pricePerVolumeName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, pricePerVolumeName)
    if (
        unitsName in columns
        and discountName in columns
        and netOfDiscountName in columns
    ):
        if pricePerUnitNetDiscountName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, pricePerUnitNetDiscountName)
        if discountInPercentName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, discountInPercentName)
    if (
        volumeName in columns
        and discountName in columns
        and netOfDiscountName in columns
    ):
        if pricePerVolumeNetDiscountName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, pricePerVolumeNetDiscountName)
        if discountInPercentName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, discountInPercentName)
    if marginName in columns and amountName in columns:
        if marginInPercentName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, marginInPercentName)
    if marginName in columns and netOfDiscountName in columns:
        if marginInPercentOfNetSalesName not in valueColsWithPrice:
            valueColsWithPrice.insert(0, marginInPercentOfNetSalesName)
    valueColsWithPrice = list(set(valueColsWithPrice))
    return valueColsWithPrice


def get_growth_metrics_for_bubble(chartDict, periodOrder, valueCols):
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    marginName = namingParams["marginName"]
    volumeName = namingParams["volumeName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    otherMetricsArrayKey = namingParams["otherMetricsArray"]
    marginGrowthName = namingParams["marginGrowthName"]
    volumePriceChangeName = namingParams["volumePriceChangeName"]
    netVolumePriceChangeName = namingParams["netVolumePriceChangeName"]
    unitsPriceChangeName = namingParams["unitsPriceChangeName"]
    netUnitsPriceChangeName = namingParams["netUnitsPriceChangeName"]
    salesGrowthName = namingParams["salesGrowthName"]
    netSalesGrowthName = namingParams["netSalesGrowthName"]
    unitsGrowthName = namingParams["unitsGrowthName"]
    volumeGrowthName = namingParams["volumeGrowthName"]
    otherMetricsArray = []
    chartDict[otherMetricsArrayKey] = otherMetricsArray
    if len(periodOrder) > 1:
        if marginGrowthName not in valueCols and marginName in valueCols:
            otherMetricsArray.insert(0, marginGrowthName)
        if volumePriceChangeName not in valueCols and volumeName in valueCols:
            otherMetricsArray.insert(0, volumePriceChangeName)
        if (
            netVolumePriceChangeName not in valueCols
            and volumeName in valueCols
            and netOfDiscountName in valueCols
        ):
            otherMetricsArray.insert(0, netVolumePriceChangeName)
        if unitsPriceChangeName not in valueCols and unitsName in valueCols:
            otherMetricsArray.insert(0, unitsPriceChangeName)
        if (
            netUnitsPriceChangeName not in valueCols
            and unitsName in valueCols
            and netOfDiscountName in valueCols
        ):
            otherMetricsArray.insert(0, netUnitsPriceChangeName)
        if unitsGrowthName not in valueCols and unitsName in valueCols:
            otherMetricsArray.insert(0, unitsGrowthName)
        if volumeGrowthName not in valueCols and volumeName in valueCols:
            otherMetricsArray.insert(0, volumeGrowthName)
        if netSalesGrowthName not in valueCols and netOfDiscountName in valueCols:
            otherMetricsArray.insert(0, netSalesGrowthName)
        if salesGrowthName not in valueCols:
            otherMetricsArray.insert(0, salesGrowthName)
        if len(otherMetricsArray) > 0:
            valueCols = valueCols + otherMetricsArray
            chartDict[otherMetricsArrayKey] = otherMetricsArray
    return valueCols, chartDict


def get_gross_margin_metrics_for_bubble(chartDict, valueCols, valueColsWithPrice):
    namingParams = get_naming_params()
    marginName = namingParams["marginName"]
    marginInPercentName = namingParams["marginInPercentName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    otherMetricsArrayKey = namingParams["otherMetricsArray"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    if marginName in valueColsWithPrice and marginInPercentName not in valueCols:
        valueCols.insert(0, marginInPercentName)
        chartDict[otherMetricsArrayKey].append(marginInPercentName)
    if (
        marginName in valueColsWithPrice
        and netOfDiscountName in valueColsWithPrice
        and marginInPercentOfNetSalesName not in valueCols
    ):
        valueCols.insert(0, marginInPercentOfNetSalesName)
        chartDict[otherMetricsArrayKey].append(marginInPercentOfNetSalesName)
    return valueCols, chartDict


def get_chart_image_info(chart_name: str) -> tuple[str, str]:
    """Return the image path and caption for ``chart_name``."""

    file_params = get_file_params()
    naming_params = get_naming_params()
    image_params = get_image_params()

    image_folder = file_params["imageFolderName"]
    doclink_dict = image_params[naming_params["doclinkDict"]]

    normalized_name = chart_name.lower().replace(" ", "_")
    image_path = f"{image_folder}/{normalized_name}.png"
    label = normalized_name.replace("_", " ")
    key = f"{label} plot"
    caption = label.capitalize() if key in doclink_dict else ""

    return image_path, caption


def move_to_end(array, element):
    if element in array:
        array.remove(element)
        array.append(element)
    return array


def clean_chartDict(chartDict, generateHash, varianceAnalysisChart, run):
    configParams = get_config_params()
    namingParams = get_naming_params()
    invertedEmojiNumberDict = configParams[namingParams["invertedEmojiNumberDict"]]
    absolute = namingParams["absolute"]
    addBlankColumn = namingParams["addBlankColumn"]
    adjustBubbleLabels = namingParams["adjustBubbleLabels"]
    addNewRunName = namingParams["addNewRunName"]
    aggregateOtherWaterfalls = namingParams["aggregateOtherWaterfalls"]
    plotTotalBubble = namingParams["plotTotalBubble"]
    alternativeResult = namingParams["alternativeResult"]
    averageTotalValue = namingParams["averageTotalValue"]
    chartMetrics = namingParams["chartMetrics"]
    chooseExcludeColumnsCheckbox = namingParams["chooseExcludeColumnsCheckbox"]
    chosenChart = namingParams["chosenChart"]
    chosenCohortColumn = namingParams["chosenCohortColumn"]
    chooseExcludeColumnsCheckbox = namingParams["chooseExcludeColumnsCheckbox"]
    colorItems = namingParams["colorItems"]
    colorpalette = namingParams["colorpalette"]
    colorChoice = namingParams["colorChoice"]
    columnHash = namingParams["columnHash"]
    columnName = namingParams["columnName"]
    columnTotalKey = namingParams["columnTotal"]
    companyDescriptionKey = namingParams["companyDescription"]
    companyExpenses = namingParams["companyExpenses"]
    companyNameKey = namingParams["companyName"]
    companySales = namingParams["companySales"]
    companyUrlKey = namingParams["companyUrl"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    countByColumn = namingParams["countByColumn"]
    countMetricsColumn = namingParams["countMetricsColumn"]
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    countMetricsSumArray = namingParams["countMetricsSumArray"]
    countMetricsSumDict = namingParams["countMetricsSumDict"]
    countMetricsAvgDict = namingParams["countMetricsAvgDict"]
    currencyChoice = namingParams["currencyChoice"]
    CXGRMetric = namingParams["CXGRMetricName"]
    CXGRData = namingParams["CXGRData"]
    CXGRTotal = namingParams["CXGRTotal"]
    dataColMetricName = namingParams["dataColMetricName"]
    datePeriodName = namingParams["datePeriodName"]
    dateRangeArray = namingParams["dateRangeArray"]
    datasetChoice = namingParams["datasetChoice"]
    datasetTypeName = namingParams["datasetTypeName"]
    deleteRunName = namingParams["deleteRunName"]
    drilldownParamsDictName = namingParams["drilldownParamsDictName"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    excludefullQueryString = namingParams["excludefullQueryString"]
    excludeOutliers = namingParams["excludeOutliers"]
    filterActiveName = namingParams["filterActiveName"]
    filterDictName = namingParams["filterDictName"]
    fixedParetoScaleChoice = namingParams["fixedParetoScaleChoice"]
    fixedScaleChoice = namingParams["fixedScaleChoice"]
    fixedVarianceScaleChoice = namingParams["fixedVarianceScaleChoice"]
    fullCurrencyNameKey = namingParams["fullCurrencyName"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    highlightedDimension = namingParams["highlightedDimension"]
    highlightOverlayChart = namingParams["highlightOverlayChart"]
    IBCSdecimalName = namingParams["IBCSdecimalName"]
    includefullQueryString = namingParams["includefullQueryString"]
    indexOrderKey = namingParams["indexOrder"]
    industryKey = namingParams["industry"]
    isLikeForLike = namingParams["isLikeForLike"]
    isolineMetric = namingParams["isolineMetric"]
    labelColor = namingParams["labelColor"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    likeForLike = namingParams["likeForLikeName"]
    logXAxis = namingParams["logXAxis"]
    logYAxis = namingParams["logYAxis"]
    lostAndDroppedColumn = namingParams["lostAndDroppedColumn"]
    loopParamsDictName = namingParams["loopParamsDictName"]
    mainReportRunName = namingParams["mainReportRunName"]
    mainDimension = namingParams["mainDimension"]
    maxNumberOfNodes = namingParams["maxNumberOfNodes"]
    metricParamsKey = namingParams["metricParams"]
    metricTextKey = namingParams["metricText"]
    metricsToPlot = namingParams["metricsToPlot"]
    metricsToPlotCheckbox = namingParams["metricsToPlotCheckbox"]
    metricsToShowInDataColumn = namingParams["metricsToShowInDataColumn"]
    scalingFactorKey = namingParams["scalingFactor"]
    nextRunName = namingParams["nextRunName"]
    noVarianceAnalysis = namingParams["noVarianceAnalysis"]
    numberFilterDictName = namingParams["numberFilterDictName"]
    numberOfMetricsInDataColumn = namingParams["numberOfMetricsInDataColumn"]
    numberOfPlottedSmallMultiplesKey = namingParams["numberOfPlottedSmallMultiples"]
    numberOfSmallMultiples = namingParams["numberOfSmallMultiples"]
    numberOfSmallMultiplesWaterfall = namingParams["numberOfSmallMultiplesWaterfall"]
    offsetKey = namingParams["offset"]
    otherMetricsArray = namingParams["otherMetricsArray"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    overlayChartFullDfKey = namingParams["overlayChartFullDf"]
    overlayChartDimensionKey = namingParams["overlayChartDimension"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    previousRunName = namingParams["previousRunName"]
    parameterSetting = namingParams["parameterSetting"]
    periodsMissing = namingParams["periodsMissing"]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    plotCommentText = namingParams["plotCommentText"]
    plotConcentrationText = namingParams["plotConcentrationText"]
    plotTitleText = namingParams["plotTitleText"]
    plotOverlayChart = namingParams["plotOverlayChart"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    plotSmallMultiplesWaterfall = namingParams["plotSmallMultiplesWaterfall"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    positionLegends = namingParams["positionLegends"]
    pricePerUnitTotalName = namingParams["pricePerUnitTotalName"]
    processingChoice = namingParams["processingChoice"]
    recordRunName = namingParams["recordRunName"]
    resampleDates = namingParams["resampleDates"]
    rowName = namingParams["rowName"]
    rowToPlot = namingParams["rowToPlotName"]
    runNumber = namingParams["runNumberName"]
    scanMarketData = namingParams["scanMarketData"]
    selectDimensionsToPlotCheckbox = namingParams["selectDimensionsToPlotCheckbox"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    selectedPeriods = namingParams["selectedPeriods"]
    setFactorParameter = namingParams["setFactorParameter"]
    shareOfTotalMarket = namingParams["shareOfTotalMarket"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    showAverageValue = namingParams["showAverageValueName"]
    showBubbleLabel = namingParams["showBubbleLabel"]
    showCAGR = namingParams["showCAGR"]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    showIsoLine = namingParams["showIsoLine"]
    showLegend = namingParams["showLegend"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    showOutliers = namingParams["showOutliers"]
    showScatterLabels = namingParams["showScatterLabels"]
    showTrendLine = namingParams["showTrendLine"]
    showValuesAs = namingParams["showValuesAs"]
    smallMultiplesDimension = namingParams["smallMultiplesDimension"]
    smallMultiplesWaterfall = namingParams["smallMultiplesWaterfall"]
    stackedColumnMetric = namingParams["stackedColumnMetric"]
    startAxesFromZero = namingParams["startAxesFromZero"]
    submitPlotName = namingParams["submitPlotName"]
    subplotTitlesKey = namingParams["subplotTitles"]
    totalName = namingParams["totalName"]
    updateCurrentRunKey = namingParams["updateCurrentRunName"]
    valuePrefixDict = namingParams["valuePrefixDict"]
    valuePrefixMetric = namingParams["valuePrefixMetric"]
    valuePrefixName = namingParams["valuePrefixName"]
    varianceAggregation = namingParams["varianceAggregation"]
    varianceAnalysisChartKey = namingParams["varianceAnalysisChart"]
    varianceAggregationOptionsArray = namingParams["varianceAggregationOptionsArray"]
    varianceInPercent = namingParams["varianceInPercent"]
    XnumberOfTop = namingParams["XnumberOfTop"]
    YnumberOfTop = namingParams["YnumberOfTop"]
    WnumberOfTop = namingParams["WnumberOfTop"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    toDrop = [
        -1,
        -2,
        -3,
        -4,
        -5,
        -6,
        -7,
        -8,
        -9,
        absolute,
        addBlankColumn,
        addNewRunName,
        aggregateOtherWaterfalls,
        averageTotalValue,
        colorChoice,
        colorItems,
        columnHash,
        columnName,
        columnTotalKey,
        companyExpenses,
        companyDescriptionKey,
        companyNameKey,
        companySales,
        companyUrlKey,
        countByColumn,
        countMetricsAvgArray,
        countMetricsColumn,
        countMetricsSumArray,
        countMetricsSumDict,
        countMetricsAvgDict,
        currencyChoice,
        CXGRData,
        CXGRMetric,
        CXGRTotal,
        datePeriodName,
        datasetChoice,
        dateRangeArray,
        datasetTypeName,
        deleteRunName,
        filterActiveName,
        fullCurrencyNameKey,
        hideTopItemsSlider,
        indexOrderKey,
        industryKey,
        IBCSdecimalName,
        isLikeForLike,
        metricParamsKey,
        metricTextKey,
        nextRunName,
        numberOfMetricsInDataColumn,
        offsetKey,
        otherMetricsArray,
        overlayChartDfKey,
        overlayChartDimensionKey,
        overlayChartFullDfKey,
        overlayChartMetricKey,
        plotOverlayChart,
        plotCommentText,
        plotConcentrationText,
        plotTitleText,
        previousRunName,
        periodsMissing,
        pricePerUnitTotalName,
        recordRunName,
        rowName,
        runNumber,
        scalingFactorKey,
        scanMarketData,
        selectedPeriods,
        smallMultiplesDimension,
        smallMultiplesWaterfall,
        stackedColumnMetric,
        submitPlotName,
        subplotTitlesKey,
        updateCurrentRunKey,
        valuePrefixName,
        valuePrefixDict,
        valuePrefixMetric,
        varianceAggregationOptionsArray,
        "X",
        "Y",
        "W",
    ]
    toDropPlus = [
        adjustBubbleLabels,
        chartMetrics,
        chosenCohortColumn,
        colorpalette,
        compareWithYearBefore,
        dataColMetricName,
        excludeOutliers,
        fixedParetoScaleChoice,
        fixedScaleChoice,
        fixedVarianceScaleChoice,
        highlightedDimension,
        highlightOverlayChart,
        isolineMetric,
        labelColor,
        likeForLike,
        logXAxis,
        logYAxis,
        lostAndDroppedColumn,
        metricsToPlotCheckbox,
        metricsToShowInDataColumn,
        numberOfPlottedSmallMultiplesKey,
        numberOfSmallMultiples,
        plotAsHeatmap,
        plotTotalBubble,
        positionLegends,
        selectDimensionsToPlotCheckbox,
        setFactorParameter,
        showAbsoluteValues,
        showAverageValue,
        showBubbleLabel,
        showCAGR,
        showIsoLine,
        showLegend,
        showMetricsInDataColumn,
        showScatterLabels,
        showOutliers,
        showTrendLine,
        showValuesAs,
        startAxesFromZero,
        XnumberOfTop,
        YnumberOfTop,
        WnumberOfTop,
    ]
    toDropNotVarianceAnalysis = [
        alternativeResult,
        chooseExcludeColumnsCheckbox,
        drilldownParamsDictName,
        letMeChooseOption,
        loopParamsDictName,
        mainDimension,
        maxNumberOfNodes,
        numberOfSmallMultiplesWaterfall,
        parameterSetting,
        plotSmallMultiplesWaterfall,
        processingChoice,
        shareOfTotalMarket,
        showInitialAndFinalValues,
        varianceAggregation,
        varianceAnalysisChartKey,
        varianceInPercent,
    ]
    toDropVarianceAnalysis = [
        chosenChart,
        metricsToPlot,
        metricsToPlotCheckbox,
        numberOfSmallMultiplesWaterfall,
        plotSmallMultiplesKey,
        plotValuesAsChoice,
        resampleDates,
        rowToPlot,
        selectDimensionsToPlot,
        selectDimensionsToPlotCheckbox,
        valuePrefixDict,
        valuePrefixMetric,
    ]
    toDropdrillDown = [
        alternativeResult,
        letMeChooseOption,
        maxNumberOfNodes,
        parameterSetting,
    ]
    cleanDict = {}
    if chartDict and len(chartDict) > 0:
        cleanDict = copy.deepcopy(chartDict)
    if generateHash:
        toDrop = toDrop + toDropPlus
        if not varianceAnalysisChart:
            toDrop = toDrop + toDropNotVarianceAnalysis
        if varianceAnalysisChart:
            toDrop = toDrop + toDropVarianceAnalysis
    if smallMultiplesCharts not in chartDict or not chartDict[smallMultiplesCharts]:
        toDrop.append(smallMultiplesColumn)
    if processingChoice not in chartDict or chartDict[processingChoice] in [
        noVarianceAnalysis
    ]:
        toDrop = toDrop + toDropNotVarianceAnalysis
    if varianceAnalysisChart and run == mainReportRunName:
        toDrop.append(drilldownParamsDictName)
    elif varianceAnalysisChart and drilldownReportRunName in run:
        toDrop = toDrop + toDropdrillDown
        toDrop.append(loopParamsDictName)
        if drilldownParamsDictName in cleanDict:
            for element in chartDict[drilldownParamsDictName]:
                emojiNumber = run.replace(drilldownReportRunName + " ", "")
                if emojiNumber in invertedEmojiNumberDict:
                    emojiKey = invertedEmojiNumberDict[emojiNumber]
                    if element != emojiKey:
                        cleanDict[drilldownParamsDictName].pop(element)
    for element in toDrop:
        if element in cleanDict:
            cleanDict.pop(element)
    if selectDimensionsToPlot in cleanDict:
        if totalName in cleanDict[selectDimensionsToPlot]:
            cleanDict[selectDimensionsToPlot].remove(totalName)
    if includefullQueryString in cleanDict:
        cleanDict.pop(includefullQueryString)
    if excludefullQueryString in cleanDict:
        cleanDict.pop(excludefullQueryString)
    return cleanDict


def get_currency_name(chartDict, paramDict, metric):
    namingParams = get_naming_params()
    currencyChoiceKey = namingParams["currencyChoice"]
    currencyChoiceLabel = namingParams["currencyChoiceLabel"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    loadDataTabLabel = namingParams["loadDataTabLabel"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    chosenChart = namingParams["chosenChart"]
    areaChart = namingParams["areaChart"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    costsName = namingParams["costsName"]
    marginName = namingParams["marginName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    discountInPercentName = namingParams["discountInPercentName"]
    netMarginName = namingParams["netMarginName"]
    indirectCostsName = namingParams["indirectCostsName"]
    monetaryPromoLocalCurrencyName = namingParams["monetaryPromoLocalCurrencyName"]
    monetaryNoPromoLocalCurrencyName = namingParams["monetaryNoPromoLocalCurrencyName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    valuePrefixName = namingParams["valuePrefixName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    valuePrefixDict = namingParams["valuePrefixDict"]
    infoMessageType = namingParams["infoMessageType"]
    unitsGrowthName = namingParams["unitsGrowthName"]
    volumeGrowthName = namingParams["volumeGrowthName"]
    netSalesGrowthName = namingParams["netSalesGrowthName"]
    salesGrowthName = namingParams["salesGrowthName"]
    marginGrowthName = namingParams["marginGrowthName"]
    unitsPriceChangeName = namingParams["unitsPriceChangeName"]
    netUnitsPriceChangeName = namingParams["netUnitsPriceChangeName"]
    volumePriceChangeName = namingParams["volumePriceChangeName"]
    netVolumePriceChangeName = namingParams["netVolumePriceChangeName"]
    loadDataTabKey = namingParams["loadDataTab"]
    monetaryColsArray = [
        monetaryName,
        discountName,
        cogsName,
        costsName,
        marginName,
        netMarginName,
        indirectCostsName,
        monetaryPromoLocalCurrencyName,
        monetaryNoPromoLocalCurrencyName,
        netOfDiscountName,
        pricePerVolumeName,
        pricePerUnitName,
    ]
    notMonetaryColsArray = [
        marginInPercentName,
        marginInPercentOfNetSalesName,
        discountInPercentName,
        unitsGrowthName,
        volumeGrowthName,
        netSalesGrowthName,
        salesGrowthName,
        unitsPriceChangeName,
        netUnitsPriceChangeName,
        volumePriceChangeName,
        netVolumePriceChangeName,
        marginGrowthName,
    ]
    currencyChoice = ""
    if (
        currencyChoiceKey in chartDict
        and chartDict[currencyChoiceKey] != nothingFilteredName
    ):
        if metric in monetaryColsArray:
            currencyChoice = chartDict[currencyChoiceKey]
        elif metric in notMonetaryColsArray:
            currencyChoice = ""
        else:
            for column in monetaryColsArray:
                if column in metric:
                    if metric not in notMonetaryColsArray:
                        currencyChoice = chartDict[currencyChoiceKey]
    elif (
        currencyChoiceKey in chartDict
        and chartDict[currencyChoiceKey] == nothingFilteredName
    ):
        if metric in monetaryColsArray:
            message = (
                "Currency not specified. Use the '"
                + currencyChoiceLabel
                + "' widget in the "
                + loadDataTabLabel
                + " tab."
            )
            paramDict = add_app_message_to_paramdict(
                message,
                infoMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=0,
            )
        else:
            for column in monetaryColsArray:
                if metric and column in metric:
                    message = (
                        "Currency not specified. Use the '"
                        + currencyChoiceLabel
                        + "' widget in the "
                        + loadDataTabLabel
                        + " tab."
                    )
                    paramDict = add_app_message_to_paramdict(
                        message,
                        infoMessageType,
                        loadDataTabKey,
                        paramDict,
                        isMessage=True,
                        isToast=True,
                        colNumber=0,
                    )
                    break
    if valuePrefixName in chartDict and metric not in notMonetaryColsArray:
        if valuePrefixDict in chartDict:
            if metric in chartDict[valuePrefixDict]:
                valuePrefixName = chartDict[valuePrefixDict][metric]
            else:
                valuePrefixName = chartDict[valuePrefixName]
        else:
            valuePrefixName = chartDict[valuePrefixName]
        if valuePrefixName != notMetConditionValue:
            currencyChoice = valuePrefixName + currencyChoice
    if chosenChart in chartDict and chartDict[chosenChart] == areaChart:
        if (
            plotValuesAsChoice in chartDict
            and chartDict[plotValuesAsChoice] != absolute
        ):
            currencyChoice = " %"
    return currencyChoice, paramDict


def get_rolling_and_year_to_date_period(
    duration,
    paramDict,
    chartDict,
    periodZero,
    notifier: Notifier | None = None,
):
    namingParams = get_naming_params()
    mostRecentPeriodKey = namingParams["mostRecentPeriod"]
    rollingPeriodSymbol = namingParams["rollingPeriodSymbol"]
    toDateSymbol = namingParams["toDateSymbol"]
    currentYearName = namingParams["currentYearName"]
    mostRecentDateKey = namingParams["mostRecentDate"]
    datePeriodName = namingParams["datePeriodName"]
    quarterName = namingParams["quarterName"]
    monthName = namingParams["monthName"]
    weekName = namingParams["weekName"]
    mostRecentPeriod = 0
    if mostRecentPeriodKey in chartDict:
        mostRecentPeriod = chartDict[mostRecentPeriodKey]
        mostRecentPeriod = mostRecentPeriod + 1
    if mostRecentDateKey in paramDict and len(duration) > 0:
        mostRecentDate = paramDict[mostRecentDateKey]
        if periodZero:
            mostRecentDate = mostRecentDate - relativedelta(years=1)
        if mostRecentPeriod != 0:
            mostRecentDate = mostRecentDate - relativedelta(years=abs(mostRecentPeriod))
        dateString = str(mostRecentDate.strftime("%b-%Y"))
        if rollingPeriodSymbol in duration:
            duration = rollingPeriodSymbol + dateString
        elif toDateSymbol in duration:
            duration = toDateSymbol + dateString
    if datePeriodName in paramDict and paramDict[datePeriodName] in [
        quarterName,
        monthName,
        weekName,
    ]:
        try:
            duration = duration.upper()
        except Exception as e:
            logging.exception(e)
            get_notifier(notifier).error("Failed to normalize duration")
        if paramDict[datePeriodName] in [quarterName, monthName, weekName]:
            if "-" not in duration:
                duration = duration.replace("M", "-M")
    return duration


def calculate_unit_price_promo(
    lf: pl.LazyFrame,
    amountMetric: str,
    unitsMetric: str,
    priceMetric: str,
    foundPriceArray: list,
) -> tuple[pl.LazyFrame, list]:
    """
    If we do not have it already, we calculate the unit price.
    Returns a tuple of (updated_lazyframe, updated_foundPriceArray).
    """

    # 1) Round the specified columns
    lf = lf.with_columns(
        [
            pl.col(amountMetric).round(2).alias(amountMetric),
            pl.col(unitsMetric).round(2).alias(unitsMetric),
        ]
    )

    # 2) Replace 0 with null (None) in the unitsMetric column
    lf = lf.with_columns(pl.col(unitsMetric).replace(0, None).alias(unitsMetric))

    # 3) Compute the price = amountMetric / unitsMetric
    lf = lf.with_columns(
        (pl.col(amountMetric) / pl.col(unitsMetric)).alias(priceMetric)
    )

    # 4) Fill null (None) values with 0 in the computed priceMetric
    lf = lf.with_columns(pl.col(priceMetric).fill_null(0).alias(priceMetric))

    # 5) Track the new priceMetric if it isn't already in foundPriceArray
    if priceMetric not in foundPriceArray:
        foundPriceArray.append(priceMetric)

    # Return both the modified lazy frame and the updated array
    return lf, foundPriceArray
