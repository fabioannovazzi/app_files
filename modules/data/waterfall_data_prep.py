import logging
import colorsys
import copy
import math
import random

import numpy as np
import polars as pl
from modules.utilities.ui_notifier import ui as notifier

from modules.data.common_data_utils import (
    add_row_to_dataframe,
    clean_column_labels_after_flatten_df,
    get_month_name,
    get_subtotals,
    insert_unit_and_volume_price_column,
    order_dataframe_by_month,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    drop_columns,
    duplicate_dataframe,
    flatten_cols_polars,
    print_error_details,
)

logger = logging.getLogger(__name__)

try:
    from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names
except Exception as e:  # pragma: no cover - fallback for tests
    logging.exception(e)
    notifier.error(f"ensure_lazyframe import error: {e}")
    from modules.utilities.utils import get_schema_and_column_names

    def ensure_lazyframe(df):
        return df.lazy() if isinstance(df, pl.DataFrame) else df


def get_totals_for_discount_variance_aggregations(
    paramDict, chartDict, mainDimension, element, dfBase, count, run
):
    namingParams = get_naming_params()
    totalNetOfDiscountPeriodZeroKey = namingParams["totalNetOfDiscountPeriodZero"]
    totalNetOfDiscountPeriodOneKey = namingParams["totalNetOfDiscountPeriodOne"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    isFilteredKey = namingParams["isFilteredKey"]
    discountName = namingParams["discountName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    netOfDiscountVarianceKey = namingParams["netOfDiscountVariance"]
    varianceInPercent = namingParams["varianceInPercent"]
    totalNetOfDiscountPeriodZeroinPercentKey = namingParams[
        "totalNetOfDiscountPeriodZeroinPercent"
    ]
    totalNetOfDiscountPeriodOneinPercentKey = namingParams[
        "totalNetOfDiscountPeriodOneinPercent"
    ]
    percentVarianceAfterDiscountsKey = namingParams["percentVarianceAfterDiscounts"]
    totalNetOfDiscountPeriodZeroinPercentFilteredKey = namingParams[
        "totalNetOfDiscountPeriodZeroinPercentFiltered"
    ]
    totalNetOfDiscountPeriodOneinPercentFilteredKey = namingParams[
        "totalNetOfDiscountPeriodOneinPercentFiltered"
    ]
    totalNetOfDiscountPeriodZeroFilteredKey = namingParams[
        "totalNetOfDiscountPeriodZeroFiltered"
    ]
    totalNetOfDiscountPeriodOneFilteredKey = namingParams[
        "totalNetOfDiscountPeriodOneFiltered"
    ]
    totalPeriodZeroLabel = totalNetOfDiscountPeriodZeroKey
    totalPeriodOneLabel = totalNetOfDiscountPeriodOneKey
    if (
        plotSmallMultiples in chartDict
        and chartDict[plotSmallMultiples]
        and dfBase is not None
    ):
        totalPeriodZeroValue, totalPeriodOneValue, totalVarianceValue, dfFiltered = (
            get_subtotals(
                paramDict,
                chartDict,
                dfBase,
                mainDimension,
                element,
                count,
                discountName,
            )
        )
    else:
        if paramDict[isFilteredKey] == notMetConditionValue:
            totalPeriodZeroValue = paramDict[totalNetOfDiscountPeriodZeroKey]
            totalPeriodOneValue = paramDict[totalNetOfDiscountPeriodOneKey]
            totalVarianceValue = paramDict[netOfDiscountVarianceKey]
        else:
            totalPeriodZeroValue = paramDict[totalNetOfDiscountPeriodZeroFilteredKey]
            totalPeriodOneValue = paramDict[totalNetOfDiscountPeriodOneFilteredKey]
            totalVarianceValue = paramDict[netOfDiscountVarianceKey]
        dfFiltered = pl.LazyFrame()
    if (
        varianceInPercent in chartDict
        and chartDict[varianceInPercent] == metConditionValue
    ):
        totalPeriodZeroLabel = totalNetOfDiscountPeriodZeroinPercentKey
        totalPeriodOneLabel = totalNetOfDiscountPeriodOneinPercentKey
        if (
            plotSmallMultiples in chartDict
            and chartDict[plotSmallMultiples]
            and dfBase is not None
        ):
            (
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalVarianceValue,
                dfFiltered,
            ) = get_subtotals(
                paramDict,
                chartDict,
                dfBase,
                mainDimension,
                element,
                count,
                discountName,
            )
        else:
            if paramDict[isFilteredKey] == notMetConditionValue:
                totalPeriodZeroValue = paramDict[
                    totalNetOfDiscountPeriodZeroinPercentKey
                ]
                totalPeriodOneValue = paramDict[totalNetOfDiscountPeriodOneinPercentKey]
                totalVarianceValue = paramDict[percentVarianceAfterDiscountsKey]
            else:
                totalPeriodZeroValue = paramDict[
                    totalNetOfDiscountPeriodZeroinPercentFilteredKey
                ]
                totalPeriodOneValue = paramDict[
                    totalNetOfDiscountPeriodOneinPercentFilteredKey
                ]
                totalVarianceValue = paramDict[percentVarianceAfterDiscountsKey]
    return (
        totalVarianceValue,
        totalPeriodZeroValue,
        totalPeriodOneValue,
        totalPeriodZeroLabel,
        totalPeriodOneLabel,
        dfFiltered,
    )


def get_totals_for_margin_variance_aggregations(
    paramDict, chartDict, mainDimension, element, dfBase, count, run
):
    namingParams = get_naming_params()
    indirectCostsVariance = namingParams["indirectCostsVariance"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    marginName = namingParams["marginName"]
    isFilteredKey = namingParams["isFilteredKey"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    marginVarianceKey = namingParams["marginVariance"]
    totalNetMarginPeriodZeroFilteredKey = namingParams[
        "totalNetMarginPeriodZeroFiltered"
    ]
    totalNetMarginPeriodOneFilteredKey = namingParams["totalNetMarginPeriodOneFiltered"]
    varianceInPercent = namingParams["varianceInPercent"]
    totalMarginPeriodZeroKey = namingParams["totalMarginPeriodZero"]
    totalMarginPeriodOneKey = namingParams["totalMarginPeriodOne"]
    totalMarginPeriodZeroinPercent = namingParams["totalMarginPeriodZeroinPercent"]
    totalMarginPeriodOneinPercent = namingParams["totalMarginPeriodOneinPercent"]
    totalMarginPeriodZeroFilteredKey = namingParams["totalMarginPeriodZeroFiltered"]
    totalMarginPeriodOneFilteredKey = namingParams["totalMarginPeriodOneFiltered"]
    totalMarginPeriodZeroinPercentFilteredKey = namingParams[
        "totalMarginPeriodZeroinPercentFiltered"
    ]
    totalMarginPeriodOneinPercentFilteredKey = namingParams[
        "totalMarginPeriodOneinPercentFiltered"
    ]
    totalNetMarginPeriodZeroinPercentKey = namingParams[
        "totalNetMarginPeriodZeroinPercent"
    ]
    totalNetMarginPeriodOneinPercentKey = namingParams[
        "totalNetMarginPeriodOneinPercent"
    ]
    percentVarianceAfterCogs = namingParams["percentVarianceAfterCogs"]
    totalNetMarginPeriodZeroKey = namingParams["totalNetMarginPeriodZero"]
    totalNetMarginPeriodOneKey = namingParams["totalNetMarginPeriodOne"]
    totalNetMarginPeriodZeroinPercentFilteredKey = namingParams[
        "totalNetMarginPeriodZeroinPercentFiltered"
    ]
    totalNetMarginPeriodOneinPercentFilteredKey = namingParams[
        "totalNetMarginPeriodOneinPercentFiltered"
    ]
    if indirectCostsVariance in paramDict:
        if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
            totalPeriodZeroLabel = totalMarginPeriodZeroKey
            totalPeriodOneLabel = totalMarginPeriodOneKey
            (
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalVarianceValue,
                dfFiltered,
            ) = get_subtotals(
                paramDict, chartDict, dfBase, mainDimension, element, count, marginName
            )
        else:
            if paramDict[isFilteredKey] == notMetConditionValue:
                totalVarianceValue = paramDict[marginVarianceKey]
                totalPeriodZeroValue = paramDict[totalNetMarginPeriodZeroKey]
                totalPeriodOneValue = paramDict[totalNetMarginPeriodOneKey]
            else:
                totalVarianceValue = paramDict[marginVarianceKey]
                totalPeriodZeroValue = paramDict[totalNetMarginPeriodZeroFilteredKey]
                totalPeriodOneValue = paramDict[totalNetMarginPeriodOneFilteredKey]
            totalPeriodZeroLabel = totalNetMarginPeriodZeroKey
            totalPeriodOneLabel = totalNetMarginPeriodOneKey
            dfFiltered = pl.LazyFrame()
        if (
            varianceInPercent in chartDict
            and chartDict[varianceInPercent] == metConditionValue
        ):
            if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
                (
                    totalPeriodZeroValue,
                    totalPeriodOneValue,
                    totalVarianceValue,
                    dfFiltered,
                ) = get_subtotals(
                    paramDict,
                    chartDict,
                    dfBase,
                    mainDimension,
                    element,
                    count,
                    marginName,
                )
                totalPeriodZeroLabel = totalMarginPeriodZeroinPercent
                totalPeriodOneLabel = totalMarginPeriodOneinPercent
            else:
                if paramDict[isFilteredKey] == notMetConditionValue:
                    totalPeriodZeroValue = paramDict[
                        totalNetMarginPeriodZeroinPercentKey
                    ]
                    totalPeriodOneValue = paramDict[totalNetMarginPeriodOneinPercentKey]
                    totalVarianceValue = paramDict[percentVarianceAfterCogs]
                else:
                    totalPeriodZeroValue = paramDict[
                        totalNetMarginPeriodZeroinPercentFilteredKey
                    ]
                    totalPeriodOneValue = paramDict[
                        totalNetMarginPeriodOneinPercentFilteredKey
                    ]
                    totalVarianceValue = paramDict[percentVarianceAfterCogs]
                totalPeriodZeroLabel = totalNetMarginPeriodZeroinPercentKey
                totalPeriodOneLabel = totalNetMarginPeriodOneinPercentKey
    else:
        totalPeriodZeroLabel = totalMarginPeriodZeroKey
        totalPeriodOneLabel = totalMarginPeriodOneKey
        if (
            plotSmallMultiples in chartDict
            and chartDict[plotSmallMultiples]
            and dfBase is not None
        ):
            (
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalVarianceValue,
                dfFiltered,
            ) = get_subtotals(
                paramDict, chartDict, dfBase, mainDimension, element, count, marginName
            )
        else:
            if paramDict[isFilteredKey] == notMetConditionValue:
                totalPeriodZeroValue = paramDict[totalMarginPeriodZeroKey]
                totalPeriodOneValue = paramDict[totalMarginPeriodOneKey]
                totalVarianceValue = paramDict[marginVarianceKey]
            else:
                totalPeriodZeroValue = paramDict[totalMarginPeriodZeroFilteredKey]
                totalPeriodOneValue = paramDict[totalMarginPeriodOneFilteredKey]
                totalVarianceValue = paramDict[marginVarianceKey]
            dfFiltered = pl.LazyFrame()
        if (
            varianceInPercent in chartDict
            and chartDict[varianceInPercent] == metConditionValue
        ):
            totalPeriodZeroLabel = totalMarginPeriodZeroinPercent
            totalPeriodOneLabel = totalMarginPeriodOneinPercent
            if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
                (
                    totalPeriodZeroValue,
                    totalPeriodOneValue,
                    totalVarianceValue,
                    dfFiltered,
                ) = get_subtotals(
                    paramDict,
                    chartDict,
                    dfBase,
                    mainDimension,
                    element,
                    count,
                    marginName,
                )
            else:
                if paramDict[isFilteredKey] == notMetConditionValue:
                    totalPeriodZeroValue = paramDict[totalMarginPeriodZeroinPercent]
                    totalPeriodOneValue = paramDict[totalMarginPeriodOneinPercent]
                    totalVarianceValue = paramDict[percentVarianceAfterCogs]
                else:
                    totalPeriodZeroValue = paramDict[
                        totalMarginPeriodZeroinPercentFilteredKey
                    ]
                    totalPeriodOneValue = paramDict[
                        totalMarginPeriodOneinPercentFilteredKey
                    ]
                    totalVarianceValue = paramDict[percentVarianceAfterCogs]
    return (
        totalVarianceValue,
        totalPeriodZeroValue,
        totalPeriodOneValue,
        totalPeriodZeroLabel,
        totalPeriodOneLabel,
        dfFiltered,
    )


def get_waterfall_number_format(
    df: pl.DataFrame | pl.LazyFrame, run: str
) -> tuple[str, float]:
    """Return the number formatting string based on the variance size."""

    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]

    variance_sum = (
        df.lazy()
        .select(pl.col(varianceAmountName).abs().sum().alias("sum"))
        .collect(engine="streaming")
        .item()
    )
    absolute_variance = float(abs(variance_sum))

    if run == horizontalWaterfallChart:
        if absolute_variance < 0.1:
            numberFormat = "{y:,.2f}"
        elif absolute_variance < 1:
            numberFormat = "{y:,.2f}"
        elif absolute_variance < 10:
            numberFormat = "{y:,.1f}"
        elif absolute_variance < 100:
            numberFormat = "{y:,.1f}"
        elif absolute_variance < 1000:
            numberFormat = "{y:,.0f}"
        else:
            numberFormat = "{y:,.3s}"
    else:
        if absolute_variance < 0.1:
            numberFormat = "{x:,.2f}"
        elif absolute_variance < 1:
            numberFormat = "{x:,.2f}"
        elif absolute_variance < 10:
            numberFormat = "{x:,.1f}"
        elif absolute_variance < 100:
            numberFormat = "{x:,.1f}"
        elif absolute_variance < 1000:
            numberFormat = "{x:,.0f}"
        else:
            numberFormat = "{x:,.3s}"

    return numberFormat, float(variance_sum)


def add_index_to_label(df: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
    """Prefix each label with an emoji number using Polars."""

    naming_params = get_naming_params()
    config_params = get_config_params()
    emoji_number_dict = config_params[naming_params["emojiNumberDict"]]
    work_column = naming_params["workColumn"]

    lf = ensure_lazyframe(df)
    emoji_map = {str(k): v for k, v in emoji_number_dict.items()}

    return (
        lf.with_row_index("_row", offset=1)
        .with_columns(
            (
                pl.col("_row")
                .cast(str)
                .replace(emoji_map)
                .str.concat(pl.col(work_column).str.slice(2))
                .alias(work_column)
            )
        )
        .drop("_row")
    )


def change_variance_tags_to_units(df, chartDict):
    namingParams = get_naming_params()
    varianceTypeName = namingParams["varianceTypeName"]
    varianceAggregation = namingParams["varianceAggregation"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    columns, schema = get_schema_and_column_names(df)
    if varianceAggregation in chartDict and varianceTypeName in columns:
        if (
            unitsName.lower() in chartDict[varianceAggregation]
            or unitsName.title() in chartDict[varianceAggregation]
        ):
            if isinstance(df, pl.LazyFrame):
                df = df.with_columns(
                    pl.col(varianceTypeName)
                    .str.replace(volumeName, unitsName)
                    .str.replace(volumeName.lower(), unitsName.lower())
                    .alias(varianceTypeName)
                )
            elif isinstance(df, pl.DataFrame):
                df = df.with_columns(
                    pl.col(varianceTypeName)
                    .str.replace(volumeName, unitsName)
                    .str.replace(volumeName.lower(), unitsName.lower())
                    .alias(varianceTypeName)
                )
    return df


def build_composite_y_labels(
    df: pl.LazyFrame, indexCols: list[str], paramDict: dict, run: str
) -> pl.LazyFrame:
    """Combine dimension values to form waterfall y-axis labels."""

    namingParams = get_naming_params()
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    workColumn = namingParams["workColumn"]
    dateName = namingParams["dateName"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]

    pl_df = df.with_columns(pl.lit(" ").alias(workColumn))

    if run == horizontalWaterfallChart:
        pl_df = pl_df.with_columns(pl.col(dateName).alias(workColumn))

    count = 1
    for element in indexCols:
        if run == runOneDimensionalAnalysis:
            if len(indexCols) == 1:
                separator = ""
            elif count == 1:
                separator = " "
            else:
                separator = " - "
            pl_df = pl_df.with_columns(
                (pl.col(workColumn) + pl.lit(separator) + pl.col(element)).alias(
                    workColumn
                )
            )
        elif run == horizontalWaterfallChart:
            pass
        else:
            separator = " - "
            pl_df = pl_df.with_columns(
                pl.when(pl.col(element) != "")
                .then(pl.col(workColumn) + pl.lit(separator) + pl.col(element))
                .otherwise(pl.col(workColumn))
                .alias(workColumn)
            )
        count += 1

    if run not in [runOneDimensionalAnalysis, horizontalWaterfallChart]:
        pl_df = add_index_to_label(pl_df)

    return pl_df


def add_indirect_cost_variance(
    paramDict, chartDict, df, workArray, totalVarianceValue, showInitialAndFinalValues
):
    """
    if the variance type is on the margin and if we have indirect cost, we need to add the total variance cost variance as an item to the chart and change the residual
    """
    namingParams = get_naming_params()
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = namingParams["marginVolumeRateAggregation"]
    costsUnitsAggregation = namingParams["costsUnitsAggregation"]
    costsVolumeAggregation = namingParams["costsVolumeAggregation"]
    costsUnitsMixAggregation = namingParams["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = namingParams["costsVolumeMixAggregation"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    indirectCostsVariance = namingParams["indirectCostsVariance"]
    indirectCostsName = namingParams["indirectCostsName"]
    varianceInPercent = namingParams["varianceInPercent"]
    percentVarianceAfterIndCosts = namingParams["percentVarianceAfterIndCosts"]
    percentVarianceAfterCogs = namingParams["percentVarianceAfterCogs"]
    metConditionValue = namingParams["metConditionValue"]
    netTotal = namingParams["netTotal"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    marginAggregationArray = [
        marginVarianceAggregation,
        marginUnitsRateAggregation,
        marginVolumeRateAggregation,
        costsUnitsAggregation,
        costsVolumeAggregation,
        costsUnitsMixAggregation,
        costsVolumeMixAggregation,
        discountsUnitsCogsAggregation,
        discountsVolumeCogsAggregation,
    ]
    if (
        varianceAggregation in chartDict
        and chartDict[varianceAggregation] in marginAggregationArray
    ):
        if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
            pass
        else:
            if indirectCostsVariance in paramDict:
                if (
                    varianceInPercent in chartDict
                    and chartDict[varianceInPercent] == metConditionValue
                ):
                    indirectCostsVarianceSum = (
                        paramDict[percentVarianceAfterCogs]
                        - paramDict[percentVarianceAfterIndCosts]
                    )
                    totalNetMargin = paramDict[percentVarianceAfterIndCosts]
                else:
                    indirectCostsVarianceSum = paramDict[indirectCostsVariance]
                    totalNetMargin = totalVarianceValue - indirectCostsVarianceSum
                if indirectCostsVarianceSum != 0:
                    rowArray, endArray = workArray + [-indirectCostsVarianceSum, 0], [
                        "relative",
                        indirectCostsName,
                    ]
                    df = add_row_to_dataframe(df, rowArray, endArray, "tail")
                    if not showInitialAndFinalValues:
                        rowArray, endArray = workArray + [totalNetMargin, 0], [
                            "absolute",
                            netTotal,
                        ]
                        df = add_row_to_dataframe(df, rowArray, endArray, "tail")
    return df


def get_totals(paramDict, chartDict, mainDimension, element, dfBase, count, run):
    """
    in the case in which we are not displaying small multiples, we want to get the pre-calculated totals for our waterfall charts
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
    varianceAggregation = namingParams["varianceAggregation"]
    varianceInPercent = namingParams["varianceInPercent"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    errorMessageType = namingParams["errorMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    clearCacheLabel = namingParams["clearCacheLabel"]
    colNumber = 0
    try:
        if (
            varianceAggregation in chartDict
            and chartDict[varianceAggregation] in cogsAggregationArray
        ):
            (
                totalVarianceValue,
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalPeriodZeroLabel,
                totalPeriodOneLabel,
                dfFiltered,
            ) = get_totals_for_margin_variance_aggregations(
                paramDict, chartDict, mainDimension, element, dfBase, count, run
            )
        elif (
            varianceAggregation in chartDict
            and chartDict[varianceAggregation] in discountsAggregationArray
        ):
            (
                totalVarianceValue,
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalPeriodZeroLabel,
                totalPeriodOneLabel,
                dfFiltered,
            ) = get_totals_for_discount_variance_aggregations(
                paramDict, chartDict, mainDimension, element, dfBase, count, run
            )
        else:
            (
                totalVarianceValue,
                totalPeriodZeroValue,
                totalPeriodOneValue,
                totalPeriodZeroLabel,
                totalPeriodOneLabel,
                dfFiltered,
            ) = get_totals_for_sales_variance_aggregations(
                paramDict, chartDict, mainDimension, element, dfBase, count, run
            )
    except Exception as e:
        logging.exception(e)
        notifier.error(f"sales variance totals error: {e}")
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
        (
            totalVarianceValue,
            totalPeriodZeroValue,
            totalPeriodOneValue,
            totalPeriodZeroLabel,
            totalPeriodOneLabel,
            dfFiltered,
        ) = (0, 0, 0, " ", " ", pl.LazyFrame())
    if varianceInPercent in chartDict and chartDict[varianceInPercent]:
        totalPeriodZeroLabel, totalPeriodOneLabel = (
            totalPeriodZeroLabel[-16:],
            totalPeriodOneLabel[-15:],
        )
    else:
        totalPeriodZeroLabel, totalPeriodOneLabel = (
            totalPeriodZeroLabel[-11:],
            totalPeriodOneLabel[-10:],
        )
    return (
        totalVarianceValue,
        totalPeriodZeroValue,
        totalPeriodOneValue,
        totalPeriodZeroLabel,
        totalPeriodOneLabel,
        dfFiltered,
        paramDict,
    )


def get_totals_for_sales_variance_aggregations(
    paramDict, chartDict, mainDimension, element, dfBase, count, run
):
    namingParams = get_naming_params()
    totalAmountPeriodZeroKey = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOneKey = namingParams["totalAmountPeriodOne"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    totalVarianceValueKey = namingParams["totalVarianceValue"]
    totalAmountPeriodZeroFilteredKey = namingParams["totalAmountPeriodZeroFiltered"]
    totalAmountPeriodOneFilteredKey = namingParams["totalAmountPeriodOneFiltered"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    isFilteredKey = namingParams["isFilteredKey"]
    totalPeriodZeroLabel = totalAmountPeriodZeroKey
    totalPeriodOneLabel = totalAmountPeriodOneKey
    if (
        plotSmallMultiples in chartDict
        and chartDict[plotSmallMultiples]
        and run != horizontalWaterfallChart
    ):
        totalPeriodZeroValue, totalPeriodOneValue, totalVarianceValue, dfFiltered = (
            get_subtotals(
                paramDict, chartDict, dfBase, mainDimension, element, count, amountName
            )
        )
    else:
        if paramDict[isFilteredKey] == notMetConditionValue:
            totalPeriodZeroValue = paramDict[totalAmountPeriodZeroKey]
            totalPeriodOneValue = paramDict[totalAmountPeriodOneKey]
            totalVarianceValue = paramDict[totalVarianceValueKey]
        else:
            totalPeriodZeroValue = paramDict[totalAmountPeriodZeroFilteredKey]
            totalPeriodOneValue = paramDict[totalAmountPeriodOneFilteredKey]
            totalVarianceValue = paramDict[totalVarianceValueKey]
        dfFiltered = pl.LazyFrame()
    return (
        totalVarianceValue,
        totalPeriodZeroValue,
        totalPeriodOneValue,
        totalPeriodZeroLabel,
        totalPeriodOneLabel,
        dfFiltered,
    )


def prepare_data_for_horizontal_waterfall_plot(
    dfCopy, xColumn, metric, paramDict, chartDict
):
    """need to unpivot dataframe by period
    percentChange="\u0394"+""+str(int(round(percentChange,0)))+"%"
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    varianceAmountName = namingParams["varianceAmountName"]
    selectedPeriods = namingParams["selectedPeriods"]
    colorName = namingParams["colorName"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    runningTotalName = namingParams["runningTotalName"]
    filterDates = namingParams["filterDates"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    periodOrder = chartDict[selectedPeriods]
    keepCols = [metric, dateName, periodName]
    metricsToPlot = [metric]
    df_lazy = ensure_lazyframe(duplicate_dataframe(dfCopy))
    df_lazy = get_month_name(df_lazy)
    df_lazy = insert_unit_and_volume_price_column(df_lazy)
    df_lazy = df_lazy.select(keepCols)

    from modules.data.common_data_utils import pivot_lazy

    df_lazy = pivot_lazy(
        lf=df_lazy,
        index_col=dateName,
        pivot_col=periodName,
        value_col=metric,
        agg_func="sum",
    )
    df_lazy = flatten_cols_polars(df_lazy, "")
    df_lazy, newCols = clean_column_labels_after_flatten_df(df_lazy, metricsToPlot)
    if filterDates in chartDict and chartDict[filterDates]:
        if fcName in newCols:
            yArray = [acName, plName, fcName]
        else:
            yArray = [acName, plName]
    else:
        yArray = [acName, pyName]
    columns, schema = get_schema_and_column_names(df_lazy)
    periodsArray = []
    for element in yArray:
        if element in columns:
            periodsArray.append(element)
    group_byCols = [dateName]
    df_lazy = df_lazy.group_by(group_byCols).agg(
        [pl.col(col).sum() for col in periodsArray]
    )
    columns, schema = get_schema_and_column_names(df_lazy)
    if len(periodsArray) == 3:
        if (
            compareScenariosOrPeriods in chartDict
            and chartDict[compareScenariosOrPeriods] == compareScenarios
        ):
            df_lazy = df_lazy.with_columns(
                (
                    pl.col(periodsArray[0])
                    + pl.col(periodsArray[2])
                    - pl.col(periodsArray[1])
                ).alias(varianceAmountName)
            )
        else:
            df_lazy = df_lazy.with_columns(
                (pl.col(periodsArray[0]) - pl.col(periodsArray[1])).alias(
                    varianceAmountName
                )
            )
    elif len(periodsArray) == 2:
        df_lazy = df_lazy.with_columns(
            (pl.col(periodsArray[0]) - pl.col(periodsArray[1])).alias(
                varianceAmountName
            )
        )
    elif yArray[0] in periodsArray:
        df_lazy = df_lazy.with_columns(
            [
                pl.col(periodsArray[0]).alias(varianceAmountName),
                pl.lit(0).alias(yArray[1]),
            ]
        )
    else:
        df_lazy = df_lazy.with_columns(
            [
                (-pl.col(periodsArray[0])).alias(varianceAmountName),
                pl.lit(0).alias(yArray[0]),
            ]
        )
    df_lazy = order_dataframe_by_month(df_lazy, paramDict, False, periodsArray)
    df_lazy = df_lazy.with_columns(pl.lit(np.nan).alias(runningTotalName))
    indexCols = [dateName]
    columnOrder = [dateName, varianceAmountName, yArray[1], yArray[0], runningTotalName]
    dropNanCols = [varianceAmountName, yArray[1], yArray[0]]
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        if fcName in columns:
            columnOrder = [
                dateName,
                varianceAmountName,
                yArray[1],
                yArray[0],
                fcName,
                runningTotalName,
            ]
            dropNanCols = [varianceAmountName, yArray[1], yArray[0], fcName]
    df_lazy = df_lazy.select(columnOrder)
    df_lazy = df_lazy.drop_nulls(dropNanCols)

    df_lazy, dfFiltered, paramDict = prepare_data_for_waterfall(
        df_lazy,
        indexCols,
        paramDict,
        chartDict,
        horizontalWaterfallChart,
        None,
        metric,
        None,
        None,
    )
    return df_lazy, paramDict


def transform_into_share_of_total_market(
    dfCopy,
    paramDict,
    chartDict,
    workArray,
    numberFormat,
    showInitialAndFinalValues,
    run,
):
    """
    change values in share or total market if requested
    """
    namingParams = get_naming_params()
    shareOfTotalMarket = namingParams["shareOfTotalMarket"]
    isFilteredKey = namingParams["isFilteredKey"]
    sharePeriodZero = namingParams["sharePeriodZero"]
    sharePeriodOne = namingParams["sharePeriodOne"]
    indexPeriodZero = namingParams["indexPeriodZero"]
    indexPeriodOne = namingParams["indexPeriodOne"]
    workColumn = namingParams["workColumn"]
    varianceAmount = namingParams["varianceAmountName"]
    totalAmountPeriodZeroKey = namingParams["totalAmountPeriodZero"]
    totalAmountPeriodOneKey = namingParams["totalAmountPeriodOne"]
    marketChangeImpact = namingParams["marketChangeImpact"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    runningTotalName = namingParams["runningTotalName"]
    initialAndFinalValuesCanBeShown = True
    if varianceAggregation in chartDict:
        if (
            chartDict[varianceAggregation]
            not in [totalVarianceAggregation, marginVarianceAggregation]
            and drilldownReportRunName in run
        ):
            initialAndFinalValuesCanBeShown = False
    lf = ensure_lazyframe(duplicate_dataframe(dfCopy))

    if (
        shareOfTotalMarket in chartDict
        and chartDict[shareOfTotalMarket]
        and isFilteredKey in paramDict
        and paramDict[isFilteredKey]
    ):
        totalAmountPeriodZero = paramDict[totalAmountPeriodZeroKey]
        totalAmountPeriodOne = paramDict[totalAmountPeriodOneKey]
        last_row_idx = pl.len() - 1

        if showInitialAndFinalValues:
            lf = (
                lf.with_row_index("_idx")
                .with_columns(
                    pl.when(pl.col("_idx") == 0)
                    .then(pl.lit(sharePeriodZero))
                    .when(pl.col("_idx") == last_row_idx)
                    .then(pl.lit(sharePeriodOne))
                    .otherwise(pl.col(workColumn))
                    .alias(workColumn)
                )
                .drop("_idx")
            )

        lf = (
            lf.with_row_index("_idx")
            .with_columns(
                pl.when(pl.col("_idx") != last_row_idx)
                .then(pl.col(varianceAmount) / totalAmountPeriodZero * 100)
                .otherwise(pl.col(varianceAmount) / totalAmountPeriodOne * 100)
                .alias(varianceAmount)
            )
            .drop("_idx")
        )

        stats = (
            lf.with_row_index("_i")
            .select(
                pl.when(pl.col("_i") == last_row_idx)
                .then(pl.col(varianceAmount))
                .otherwise(0)
                .sum()
                .alias("last_val"),
                pl.when(pl.col("_i") != last_row_idx)
                .then(pl.col(varianceAmount))
                .otherwise(0)
                .sum()
                .alias("others_sum"),
            )
            .collect()
        )
        last_val, others_sum = stats.row(0)
        difference = last_val - others_sum
        if abs(difference) > 0.001:
            rowArray = workArray + [difference, 0]
            endArray = ["relative", marketChangeImpact]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "beforeLast")

        lf = lf.with_columns(pl.col(varianceAmount).cum_sum().alias(runningTotalName))
        numberFormat, _ = get_waterfall_number_format(lf, run)
        return lf, numberFormat
    elif shareOfTotalMarket in chartDict and chartDict[shareOfTotalMarket]:
        totalAmountPeriodZero = paramDict[totalAmountPeriodZeroKey]
        totalAmountPeriodOne = paramDict[totalAmountPeriodOneKey]
        last_row_idx = pl.len() - 1

        if showInitialAndFinalValues and initialAndFinalValuesCanBeShown:
            lf = (
                lf.with_row_index("_idx")
                .with_columns(
                    pl.when(pl.col("_idx") == 0)
                    .then(pl.lit(indexPeriodZero))
                    .when(pl.col("_idx") == last_row_idx)
                    .then(pl.lit(indexPeriodOne))
                    .otherwise(pl.col(workColumn))
                    .alias(workColumn)
                )
                .drop("_idx")
            )

        lf = (
            lf.with_row_index("_idx")
            .with_columns(
                pl.when(pl.col("_idx") != last_row_idx)
                .then(pl.col(varianceAmount) / totalAmountPeriodZero * 100)
                .otherwise(pl.col(varianceAmount) / totalAmountPeriodZero * 100)
                .alias(varianceAmount)
            )
            .drop("_idx")
        )

        stats = (
            lf.with_row_index("_i")
            .select(
                pl.when(pl.col("_i") == last_row_idx)
                .then(pl.col(varianceAmount))
                .otherwise(0)
                .sum()
                .alias("last_val"),
                pl.when(pl.col("_i") != last_row_idx)
                .then(pl.col(varianceAmount))
                .otherwise(0)
                .sum()
                .alias("others_sum"),
            )
            .collect()
        )
        last_val, others_sum = stats.row(0)
        difference = last_val - others_sum
        if abs(difference) > 0.001:
            rowArray = workArray + [difference, 0]
            endArray = ["relative", marketChangeImpact]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "beforeLast")

        lf = lf.with_columns(pl.col(varianceAmount).cum_sum().alias(runningTotalName))
        numberFormat, _ = get_waterfall_number_format(lf, run)
        return lf, numberFormat
    else:
        return ensure_lazyframe(dfCopy), numberFormat


def prepare_data_for_waterfall(
    dfCopy,
    indexCols,
    paramDict,
    chartDict,
    run,
    mainDimension,
    element,
    dfBase,
    count,
) -> tuple[pl.LazyFrame, pl.DataFrame, dict]:
    """prepare columns to display in waterfall"""
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    varianceAmountName = namingParams["varianceAmountName"]
    measureName = namingParams["measureName"]
    totalName = namingParams["totalName"]
    runningTotalName = namingParams["runningTotalName"]
    varianceTypeName = namingParams["varianceTypeName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    netMarginVariance = namingParams["netMarginVariance"]
    residualName = namingParams["residualName"]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    varianceAmountName = namingParams["varianceAmountName"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    mainDimensionKey = namingParams["mainDimension"]
    nothingThereString = namingParams["nothingThereString"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    marginVariance = namingParams["marginVariance"]
    varianceAggregation = namingParams["varianceAggregation"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    marginName = namingParams["marginName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    separatorString = namingParams["separatorString"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    periodZeroSumKey = namingParams["periodZeroSum"]
    periodOneSumKey = namingParams["periodOneSum"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    renameTitlesDictKey = namingParams["renameTitlesDict"]
    renameTitlesDict = paramDict[renameTitlesDictKey]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    marginPeriodZero = marginName + separatorString + periodsArray[0]
    marginPeriodOne = marginName + separatorString + periodsArray[1]
    netOfDiscountPeriodZero = netOfDiscountName + separatorString + periodsArray[0]
    netOfDiscountPeriodOne = netOfDiscountName + separatorString + periodsArray[1]

    lf = ensure_lazyframe(duplicate_dataframe(dfCopy))
    (
        totalVarianceValue,
        totalPeriodZeroValue,
        totalPeriodOneValue,
        totalPeriodZeroLabel,
        totalPeriodOneLabel,
        dfFiltered,
        paramDict,
    ) = get_totals(paramDict, chartDict, mainDimension, element, dfBase, count, run)
    lf = change_variance_tags_to_units(lf, chartDict)

    columns, _ = get_schema_and_column_names(lf)
    totals_exprs = [
        pl.col(varianceAmountName).sum().alias("_var_sum"),
        pl.len().alias("_len"),
    ]
    if acName in columns:
        totals_exprs.append(pl.col(acName).sum().alias("_ac_sum"))
    if pyName in columns:
        totals_exprs.append(pl.col(pyName).sum().alias("_py_sum"))
    if plName in columns:
        totals_exprs.append(pl.col(plName).sum().alias("_pl_sum"))
    if fcName in columns:
        totals_exprs.append(pl.col(fcName).sum().alias("_fc_sum"))
    if amountPeriodZero in columns:
        totals_exprs.append(pl.col(amountPeriodZero).sum().alias("_ap0_sum"))
    if amountPeriodOne in columns:
        totals_exprs.append(pl.col(amountPeriodOne).sum().alias("_ap1_sum"))
    if marginPeriodZero in columns:
        totals_exprs.append(pl.col(marginPeriodZero).sum().alias("_mp0_sum"))
    if marginPeriodOne in columns:
        totals_exprs.append(pl.col(marginPeriodOne).sum().alias("_mp1_sum"))
    if netOfDiscountPeriodZero in columns:
        totals_exprs.append(pl.col(netOfDiscountPeriodZero).sum().alias("_ndp0_sum"))
    if netOfDiscountPeriodOne in columns:
        totals_exprs.append(pl.col(netOfDiscountPeriodOne).sum().alias("_ndp1_sum"))

    totals_lf = lf.select(totals_exprs)
    row_count = int(totals_lf.select(pl.col("_len")).collect(engine="streaming")[0, 0])

    if row_count > 0:
        lf = lf.join(totals_lf, how="cross")
        totals_df = totals_lf.collect(engine="streaming")
        totals_cols, _ = get_schema_and_column_names(totals_df)

        if run in [horizontalWaterfallChart]:
            totalPeriodOneValue = (
                totals_df["_ac_sum"][0] if "_ac_sum" in totals_cols else 0
            )
            if pyName in columns:
                totalPeriodZeroValue = (
                    totals_df["_py_sum"][0] if "_py_sum" in totals_cols else 0
                )
            elif plName in columns:
                totalPeriodZeroValue = (
                    totals_df["_pl_sum"][0] if "_pl_sum" in totals_cols else 0
                )
            else:
                totalPeriodZeroValue = 0
        showInitialAndFinalValues = True
        if showInitialAndFinalValues in chartDict:
            showInitialAndFinalValues = chartDict[showInitialAndFinalValues]
        lf = lf.with_columns(pl.lit("relative").alias(measureName))
        runningTotalSum = totals_df["_var_sum"][0] if "_var_sum" in totals_cols else 0
        workArray: list[str] = []
        chartingCols = copy.deepcopy(indexCols)
        if varianceTypeName not in chartingCols and run not in [
            horizontalWaterfallChart
        ]:
            chartingCols.append(varianceTypeName)
        lf = build_composite_y_labels(lf, chartingCols, paramDict, run)
        workArray.extend(["" for _ in chartingCols])
        remainderValue = totalVarianceValue - runningTotalSum
        numberFormat, varianceSum = get_waterfall_number_format(lf, run)
        initialAndFinalValuesCanBeShown = True
        if varianceAggregation in chartDict:
            if (
                chartDict[varianceAggregation]
                not in [
                    totalVarianceAggregation,
                    netOfDiscountAggregation,
                    marginVarianceAggregation,
                ]
                and drilldownReportRunName in run
            ):
                initialAndFinalValuesCanBeShown = False
            elif (
                chartDict[varianceAggregation] in [totalVarianceAggregation]
                and drilldownReportRunName in run
            ):
                if periodZeroSumKey in paramDict:
                    totalPeriodZeroValue, totalPeriodOneValue = (
                        paramDict[periodZeroSumKey],
                        paramDict[periodOneSumKey],
                    )
                else:
                    totalPeriodZeroValue = (
                        totals_df["_ap0_sum"][0] if "_ap0_sum" in totals_cols else 0
                    )
                    totalPeriodOneValue = (
                        totals_df["_ap1_sum"][0] if "_ap1_sum" in totals_cols else 0
                    )
            elif (
                chartDict[varianceAggregation] in [marginVarianceAggregation]
                and drilldownReportRunName in run
            ):
                if periodZeroSumKey in paramDict:
                    totalPeriodZeroValue, totalPeriodOneValue = (
                        paramDict[periodZeroSumKey],
                        paramDict[periodOneSumKey],
                    )
                else:
                    totalPeriodZeroValue = (
                        totals_df["_mp0_sum"][0] if "_mp0_sum" in totals_cols else 0
                    )
                    totalPeriodOneValue = (
                        totals_df["_mp1_sum"][0] if "_mp1_sum" in totals_cols else 0
                    )
            elif (
                chartDict[varianceAggregation] in [netOfDiscountAggregation]
                and drilldownReportRunName in run
            ):
                if periodZeroSumKey in paramDict:
                    totalPeriodZeroValue, totalPeriodOneValue = (
                        paramDict[periodZeroSumKey],
                        paramDict[periodOneSumKey],
                    )
                else:
                    totalPeriodZeroValue = (
                        totals_df["_ndp0_sum"][0] if "_ndp0_sum" in totals_cols else 0
                    ) + remainderValue
                    totalPeriodOneValue = (
                        totals_df["_ndp1_sum"][0] if "_ndp1_sum" in totals_cols else 0
                    ) + remainderValue
        if showInitialAndFinalValues and initialAndFinalValuesCanBeShown:
            rowArray, endArray = workArray + [
                totalPeriodZeroValue,
                totalPeriodZeroValue,
            ], ["absolute", totalPeriodZeroLabel]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "head")
        if abs(remainderValue) > abs(varianceSum / 20) and run not in [
            horizontalWaterfallChart
        ]:
            rowArray, endArray = workArray + [remainderValue, 0], [
                "relative",
                residualName,
            ]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "tail")
        if not showInitialAndFinalValues or (
            drilldownReportRunName in run and not initialAndFinalValuesCanBeShown
        ):
            rowArray, endArray = workArray + [totalVarianceValue, 0], [
                "total",
                totalName,
            ]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "tail")
        lf = add_indirect_cost_variance(
            paramDict,
            chartDict,
            lf,
            workArray,
            totalVarianceValue,
            showInitialAndFinalValues,
        )
        if showInitialAndFinalValues and initialAndFinalValuesCanBeShown:
            rowArray, endArray = workArray + [
                totalPeriodOneValue,
                totalPeriodOneValue,
            ], ["absolute", totalPeriodOneLabel]
            lf = add_row_to_dataframe(lf, rowArray, endArray, "tail")
            columns, _ = get_schema_and_column_names(lf)
            if fcName in columns:
                if (
                    compareScenariosOrPeriods in chartDict
                    and chartDict[compareScenariosOrPeriods] == compareScenarios
                ):
                    lf = (
                        lf.with_row_index("_idx")
                        .with_columns(
                            pl.when(pl.col("_idx") == pl.col("_len") - 1)
                            .then(pl.col("_fc_sum"))
                            .otherwise(pl.col(fcName))
                            .alias(fcName)
                        )
                        .drop("_idx")
                    )
        lf, numberFormat = transform_into_share_of_total_market(
            lf,
            paramDict,
            chartDict,
            workArray,
            numberFormat,
            showInitialAndFinalValues,
            run,
        )
        columns, _ = get_schema_and_column_names(lf)
        drop_cols = [
            c
            for c in [
                "_var_sum",
                "_len",
                "_ac_sum",
                "_py_sum",
                "_pl_sum",
                "_fc_sum",
                "_ap0_sum",
                "_ap1_sum",
                "_mp0_sum",
                "_mp1_sum",
                "_ndp0_sum",
                "_ndp1_sum",
            ]
            if c in columns
        ]
        if drop_cols:
            lf = lf.drop(drop_cols)
        if plotSmallMultiples in chartDict and chartDict[plotSmallMultiples]:
            pass
        else:
            lf = lf.filter(
                (pl.col(varianceAmountName) != 0) | (pl.col(measureName) == "absolute")
            )
        lf = lf.with_columns(pl.col(varianceAmountName).alias(workColumnTwo))
        for element in renameTitlesDict:
            lf = lf.with_columns(
                pl.col(workColumn)
                .str.replace(element, renameTitlesDict[element])
                .alias(workColumn)
            )
        columns, _ = get_schema_and_column_names(lf)
        if mainDimensionKey in chartDict and chartDict[mainDimensionKey][0] in columns:
            lf = lf.filter(pl.col(chartDict[mainDimensionKey][0]) != nothingThereString)
    else:
        varianceSum = 0
        avgAmount = 0
        lf = lf.head(0)

    return lf, dfFiltered, paramDict


def prepare_horizontal_waterfall_data_for_openAi(
    dfCopy: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> pl.LazyFrame:
    """Transform a DataFrame for OpenAI horizontal waterfall output."""

    namingParams = get_naming_params()
    runningTotalName = namingParams["runningTotalName"]
    measureName = namingParams["measureName"]
    dateName = namingParams["dateName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    varianceAmountName = namingParams["varianceAmountName"]
    selectedPeriods = namingParams["selectedPeriods"]
    varianceInPercent = namingParams["varianceInPercent"]
    plName = namingParams["plName"]
    pyName = namingParams["pyName"]
    acName = namingParams["acName"]

    lf = ensure_lazyframe(duplicate_dataframe(dfCopy))

    to_drop = [runningTotalName, measureName, workColumn, workColumnTwo]
    lf = lf.with_columns(pl.col(workColumn).alias(dateName))
    lf = drop_columns(lf, to_drop)

    df_columns, _ = get_schema_and_column_names(lf)
    columns = [c for c in df_columns if c != varianceAmountName]
    columns.append(varianceAmountName)
    lf = lf.select(columns)

    periods = chartDict[selectedPeriods]
    final_period = periods[1]

    lf = lf.with_columns(
        pl.when(pl.col(dateName).is_in(periods))
        .then(pl.lit(None))
        .otherwise(pl.col(varianceAmountName))
        .alias(varianceAmountName)
    )

    lf = lf.with_columns(
        pl.col(acName).round(0),
        pl.col(varianceAmountName).round(0),
    )

    lf = lf.with_columns(
        pl.when(pl.col(dateName) == final_period)
        .then(pl.col(acName).sum().over(pl.lit(1)))
        .otherwise(pl.col(acName))
        .alias(acName),
        pl.when(pl.col(dateName) == final_period)
        .then(pl.col(varianceAmountName).sum().over(pl.lit(1)))
        .otherwise(pl.col(varianceAmountName))
        .alias(varianceAmountName),
    )

    if pyName in df_columns:
        lf = lf.with_columns(pl.col(pyName).round(0))
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.lit(None))
            .otherwise(pl.col(pyName))
            .alias(pyName)
        )
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.col(pyName).sum().over(pl.lit(1)) * 0.5)
            .otherwise(pl.col(pyName))
            .alias(pyName)
        )
        lf = lf.with_columns(
            (pl.col(varianceAmountName) / pl.col(pyName) * 100).alias(varianceInPercent)
        )
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.lit(None))
            .otherwise(pl.col(pyName))
            .alias(pyName)
        )
    elif plName in df_columns:
        lf = lf.with_columns(pl.col(plName).round(0))
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.lit(None))
            .otherwise(pl.col(plName))
            .alias(plName)
        )
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.col(plName).sum().over(pl.lit(1)) * 0.5)
            .otherwise(pl.col(plName))
            .alias(plName)
        )
        lf = lf.with_columns(
            (pl.col(varianceAmountName) / pl.col(plName) * 100).alias(varianceInPercent)
        )
        lf = lf.with_columns(
            pl.when(pl.col(dateName) == final_period)
            .then(pl.lit(None))
            .otherwise(pl.col(plName))
            .alias(plName)
        )

    lf = lf.with_columns(pl.col(varianceInPercent).round(0))

    return lf
