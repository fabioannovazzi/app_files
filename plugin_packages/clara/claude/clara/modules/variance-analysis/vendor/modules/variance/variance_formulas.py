"""Polars-based variance formulas."""

import copy
from itertools import combinations
from typing import Any

import numpy as np
import polars as pl

from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_run_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import add_warning_message_in_variance_options_tab
from modules.utilities.helpers import (
    check_and_clean_columns,
    drop_columns,
    duplicate_dataframe,
    fill_null_zero,
    get_data_sample,
    get_dataset_specific_parameter,
)


def _assign_column(
    df: pl.DataFrame | pl.LazyFrame,
    name: str,
    expr: pl.Expr | Any,
) -> pl.DataFrame | pl.LazyFrame:
    """Assign ``expr`` to ``name`` in a Polars frame."""

    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        raise TypeError("df must be a Polars DataFrame or LazyFrame")

    if not isinstance(expr, pl.Expr):
        expr = pl.lit(expr)
    return df.with_columns(expr.alias(name))


def _assign_where(
    df: pl.DataFrame | pl.LazyFrame,
    mask: pl.Expr,
    name: str,
    expr: pl.Expr | Any,
) -> pl.DataFrame | pl.LazyFrame:
    """Assign ``expr`` to ``name`` where ``mask`` is true in a Polars frame."""

    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        raise TypeError("df must be a Polars DataFrame or LazyFrame")
    if not isinstance(mask, pl.Expr):
        raise ValueError("mask must be a Polars expression")
    if not isinstance(expr, pl.Expr):
        expr = pl.lit(expr)
    return df.with_columns(pl.when(mask).then(expr).otherwise(pl.col(name)).alias(name))


from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
)
from modules.variance.variance_utils import (
    divide_back_if_multiplied,
    get_year_totals,
    make_divideArray,
    recalculate_price,
)


def set_volume_and_price_variance_if_one_period_no_sales(
    df, newOrLost, varianceMetric, paramDict
):
    """
    if zero value in one year set variace as other year value
    """
    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        raise TypeError("df must be a polars DataFrame or LazyFrame")
    configParams = get_config_params()
    namingParams = get_naming_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    lostVolumeVarianceName = namingParams["lostVolumeVarianceName"]
    newVolumeVarianceName = namingParams["newVolumeVarianceName"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    if varianceMetric == "onGrossSales":
        volumeVariance = namingParams["volumeVariance"]
        priceVariance = namingParams["priceVariance"]
    elif varianceMetric == "onMargin":
        volumeVariance = namingParams["volumeVarianceOnMargin"]
        priceVariance = namingParams["priceVarianceOnMargin"]
    elif varianceMetric == "onNetSales":
        volumeVariance = namingParams["volumeVarianceOnNetSales"]
        priceVariance = namingParams["priceVarianceOnNetSales"]
    elif varianceMetric == "WeightedDistribution":
        volumeVariance = namingParams["categoryWeightedDistributionName"]
        priceVariance = namingParams["priceVariance"]
    if newOrLost:
        df = _assign_column(df, newVolumeVarianceName, 0)
        df = _assign_column(df, lostVolumeVarianceName, 0)
        df = _assign_where(
            df,
            pl.col(amountPeriodZero) == 0,
            newVolumeVarianceName,
            pl.col(amountPeriodOne),
        )
        df = _assign_where(
            df,
            pl.col(amountPeriodOne) == 0,
            lostVolumeVarianceName,
            -pl.col(amountPeriodZero),
        )
        df = _assign_where(df, pl.col(amountPeriodZero) == 0, volumeVariance, 0)
        df = _assign_where(df, pl.col(amountPeriodOne) == 0, volumeVariance, 0)
    else:
        paramDict = get_data_sample(
            df, "before_volume_and_price_variance_no_sales", False, paramDict
        )
        df = _assign_where(
            df, pl.col(amountPeriodZero) == 0, volumeVariance, pl.col(amountPeriodOne)
        )
        df = _assign_where(
            df, pl.col(amountPeriodOne) == 0, volumeVariance, -pl.col(amountPeriodZero)
        )
        paramDict = get_data_sample(
            df, "after_volume_and_price_variance_no_sales", False, paramDict
        )
    df = _assign_where(df, pl.col(amountPeriodZero) == 0, priceVariance, 0)
    df = _assign_where(df, pl.col(amountPeriodOne) == 0, priceVariance, 0)
    return df, paramDict


def set_variance_if_one_period_no_sales_and_cogs(
    df, costvariance, varianceMetric, paramDict
):
    """
    if zero value in one year set variance as other year value if no discount col
    """
    if not isinstance(df, (pl.DataFrame, pl.LazyFrame)):
        raise TypeError("df must be a polars DataFrame or LazyFrame")
    paramDict = get_data_sample(df, "before_one_period_no_sales", False, paramDict)
    configParams = get_config_params()
    namingParams = get_naming_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    cogsName = namingParams["cogsName"]
    if varianceMetric == "onGrossSales":
        volumeVariance = namingParams["volumeVariance"]
    elif varianceMetric == "onMargin":
        volumeVariance = namingParams["volumeVarianceOnMargin"]
    elif varianceMetric == "onNetSales":
        volumeVariance = namingParams["volumeVarianceOnNetSales"]
    elif varianceMetric == "WeightedDistribution":
        volumeVariance = namingParams["categoryWeightedDistributionName"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    cogsPeriodZero = cogsName + separatorString + periodsArray[0]
    cogsPeriodOne = cogsName + separatorString + periodsArray[1]
    df = _assign_where(
        df,
        pl.col(amountPeriodZero) == 0,
        volumeVariance,
        pl.col(volumeVariance) - pl.col(cogsPeriodOne),
    )
    df = _assign_where(
        df,
        pl.col(amountPeriodOne) == 0,
        volumeVariance,
        pl.col(volumeVariance) + pl.col(cogsPeriodZero),
    )
    df = _assign_where(df, pl.col(amountPeriodZero) == 0, costvariance, 0)
    df = _assign_where(df, pl.col(amountPeriodOne) == 0, costvariance, 0)
    paramDict = get_data_sample(df, "after_one_period_no_sales", False, paramDict)
    return df, paramDict


def set_variance_if_one_period_no_sales_and_discount(df, variance):
    """
    if zero value in one year set variance as other year value if no discount col
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    discountName = namingParams["discountName"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    df = _assign_where(
        df, pl.col(amountPeriodZero) == 0, variance, -pl.col(discountPeriodOne)
    )
    df = _assign_where(
        df, pl.col(amountPeriodOne) == 0, variance, pl.col(discountPeriodZero)
    )
    return df


def set_variance_if_one_period_no_sales_and_discount_and_cogs(
    df, costvariance, varianceMetric
):
    """
    if zero value in one year set variance as other year value if no discount col
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    if varianceMetric == "onGrossSales":
        volumeVariance = namingParams["volumeVariance"]
    elif varianceMetric == "onMargin":
        volumeVariance = namingParams["volumeVarianceOnMargin"]
    elif varianceMetric == "onNetSales":
        volumeVariance = namingParams["volumeVarianceOnNetSales"]
    elif varianceMetric == "WeightedDistribution":
        volumeVariance = namingParams["categoryWeightedDistributionName"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    cogsPeriodZero = cogsName + separatorString + periodsArray[0]
    cogsPeriodOne = cogsName + separatorString + periodsArray[1]
    df = _assign_where(
        df,
        pl.col(amountPeriodZero) == 0,
        volumeVariance,
        pl.col(volumeVariance) - pl.col(cogsPeriodOne) - pl.col(discountPeriodOne),
    )
    df = _assign_where(
        df,
        pl.col(amountPeriodOne) == 0,
        volumeVariance,
        pl.col(volumeVariance) + pl.col(cogsPeriodZero) + pl.col(discountPeriodZero),
    )
    df = _assign_where(df, pl.col(amountPeriodZero) == 0, costvariance, 0)
    df = _assign_where(df, pl.col(amountPeriodOne) == 0, costvariance, 0)
    return df


def get_driver_variance_names(driverArray):
    """
    we build the names of the base variance driver columns
    """
    namingParams = get_naming_params()
    varianceName = namingParams["varianceName"]
    array = []
    for element in driverArray:
        driverVariance = element  # +" "+varianceName
        if driverVariance not in array:
            array.append(driverVariance)
    return array


def clean_out_improbable_mix_variance_results(df, pureVolumeVariance, volumeVariance):
    """
    for some unclear mathematical issue from time to time you get mix variance values
    that make so sense. For instance a huge positive mix variance value balance by a huge
    negative, but equally unlikely negative volume variance value. We pull them out and set the difference
    to volume variance. The parameters used to cut are made up with common sense.
    """
    namingParams = get_naming_params()
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    workColumnThree = namingParams["workColumnThree"]
    mixVariance = namingParams["mixVariance"]
    mixOnVarianceMax = 300
    diffOnVolumeMin = 10
    # difference between mix and volume variance
    df = _assign_column(
        df, workColumn, pl.col(mixVariance) + pl.col(pureVolumeVariance)
    )
    # ratio of difference on volume variance
    df = _assign_column(
        df,
        workColumnTwo,
        (pl.col(workColumn).abs() / pl.col(pureVolumeVariance).abs() * 100),
    )
    # ratio of mix variance on total volume & mix variance
    df = _assign_column(
        df,
        workColumnThree,
        (pl.col(mixVariance).abs() / pl.col(volumeVariance).abs() * 100),
    )
    df = _assign_where(
        df,
        pl.col(workColumnThree) > mixOnVarianceMax,
        mixVariance,
        0,
    )
    df = _assign_where(
        df,
        pl.col(workColumnThree) > mixOnVarianceMax,
        pureVolumeVariance,
        pl.col(workColumn),
    )
    df = _assign_where(
        df,
        (pl.col(mixVariance) != 0) & (pl.col(workColumnTwo) < diffOnVolumeMin),
        mixVariance,
        0,
    )
    df = _assign_where(
        df,
        (pl.col(mixVariance) != 0) & (pl.col(workColumnTwo) < diffOnVolumeMin),
        pureVolumeVariance,
        pl.col(workColumn),
    )
    df = drop_columns(df, [workColumn, workColumnTwo, workColumnThree])
    return df


def recalculate_variance_for_mix_calculation(df, pureVolumeVariance, volumeVariance):
    """
    we recalculate the variance at the high level to be able to calculate the mix variance as difference.
    if the price is the same in the two periods we cannot make the calculation so we set mix variance to zero
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    workColumn = namingParams["workColumn"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    separatorString = namingParams["separatorString"]
    varianceAggregation = namingParams["varianceAggregation"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    changedVolumeVarianceName = namingParams["changedVolumeVarianceName"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
    df = _assign_column(
        df,
        workColumn,
        pl.col(pricePeriodZero) * (pl.col(unitsPeriodOne) - pl.col(unitsPeriodZero)),
    )
    df = _assign_column(df, pureVolumeVariance, pl.col(volumeVariance))
    df = _assign_column(
        df,
        workColumn,
        pl.col(workColumn)
        + (
            (pl.col(pricePeriodOne) - pl.col(pricePeriodZero))
            * (pl.col(unitsPeriodOne) - pl.col(unitsPeriodZero))
        )
        / 2,
    )
    df = _assign_where(
        df,
        (pl.col(unitsPeriodOne) - pl.col(unitsPeriodZero)) != 0,
        pureVolumeVariance,
        pl.col(workColumn),
    )
    df = drop_columns(df, [workColumn])
    return df


def calculate_sales_mix_variance(df, paramDict, chartDict, indexCols):
    """
    mix variance on sales is the variance due to change of product mix and it is calculated, at some aggregated level,
    as the difference between the variance calculated as a granular sum, and the variance calculated at the granular level
    we recalculate the volume variance and set the difference between the recalculated variance and the volume variance as mix variance
    we check that we are not dealing with new volumes and we are not dealing with lost volumes
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixSalesAggregationArray = varianceAggregationParams[
        namingParams["mixSalesAggregationArray"]
    ]
    periodsArray = configParams["periodsArray"]
    totalVariance = namingParams["totalVariance"]
    priceVariance = namingParams["priceVariance"]
    volumeVariance = namingParams["volumeVariance"]
    driverVariance = namingParams["driverVariance"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    varianceAggregation = namingParams["varianceAggregation"]
    mixVariance = namingParams["mixVariance"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    separatorString = namingParams["separatorString"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    pureVolumeVariance = namingParams["pureVolumeVarianceName"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    mainDimension = namingParams["mainDimension"]
    newAndLostUnitsMixAggregation = namingParams["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = namingParams["newAndLostVolumeMixAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    changedVolumeVarianceName = namingParams["changedVolumeVarianceName"]
    if chartDict[varianceAggregation] in mixSalesAggregationArray:
        amountPeriodZero = monetaryName + separatorString + periodsArray[0]
        amountPeriodOne = monetaryName + separatorString + periodsArray[1]
        unitsPeriodZero = unitsName + separatorString + periodsArray[0]
        unitsPeriodOne = unitsName + separatorString + periodsArray[1]
        volumePeriodZero = volumeName + separatorString + periodsArray[0]
        volumePeriodOne = volumeName + separatorString + periodsArray[1]
        pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
        pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
        columns, schema = get_schema_and_column_names(df)
        if (
            unitsPeriodZero in columns or volumePeriodZero in columns
        ) and amountPeriodZero in columns:
            if chartDict[varianceAggregation] in [
                newAndLostUnitsMixAggregation,
                newAndLostVolumeMixAggregation,
            ]:
                volumeVariance = changedVolumeVarianceMixName
                pureVolumeVariance = changedVolumeVarianceName
            df = _assign_column(df, mixVariance, 0)
            dfNewAndLost = duplicate_dataframe(df)
            dfChanged = duplicate_dataframe(df)
            dfNewAndLost = dfNewAndLost.filter(
                (pl.col(amountPeriodZero) == 0) | (pl.col(amountPeriodOne) == 0)
            )
            dfChanged = dfChanged.filter(
                (pl.col(amountPeriodZero) > 0) & (pl.col(amountPeriodOne) > 0)
            )
            if processingChoice in chartDict and chartDict[processingChoice] in [
                runOneDimensionalAnalysis
            ]:
                group_byCols = [mixVariance]
                if mainDimension in chartDict and len(chartDict[mainDimension]) > 0:
                    group_byCols = chartDict[mainDimension] + group_byCols
                sumColsArray = [
                    amountPeriodZero,
                    amountPeriodOne,
                    unitsPeriodZero,
                    unitsPeriodOne,
                    pricePeriodZero,
                    pricePeriodOne,
                    totalVariance,
                    priceVariance,
                    volumeVariance,
                ]
                if paramDict[namingParams["calculateDriverVariance"]]:
                    driverVarianceArray = get_driver_variance_names(
                        paramDict[namingParams["driverArray"]]
                    )
                    sumColsArray = sumColsArray + driverVarianceArray
                paramDict = get_data_sample(
                    dfChanged, "before_melt_group_by", False, paramDict
                )
                group_byCols, sumColsArray = check_and_clean_columns(
                    dfChanged, group_byCols, sumColsArray
                )
                dfChanged = dfChanged.group_by(group_byCols, maintain_order=True).agg(
                    [pl.col(c).sum() for c in sumColsArray]
                )
                dfChanged, paramDict = recalculate_price(dfChanged, paramDict)
                paramDict = get_data_sample(
                    dfChanged, "after_melt_group_by", False, paramDict
                )
            dfChanged = recalculate_variance_for_mix_calculation(
                dfChanged, pureVolumeVariance, volumeVariance
            )
            if paramDict[namingParams["calculateDriverVariance"]]:
                driverVarianceArray = get_driver_variance_names(
                    paramDict[namingParams["driverArray"]]
                )
                driver_sum = pl.sum_horizontal([pl.col(c) for c in driverVarianceArray])
                dfChanged = dfChanged.with_columns(
                    (pl.col(pureVolumeVariance) - driver_sum).alias(pureVolumeVariance),
                    (
                        pl.col(totalVariance)
                        - pl.col(priceVariance)
                        - pl.col(pureVolumeVariance)
                        - driver_sum
                    ).alias(mixVariance),
                )
            else:
                dfChanged = _assign_column(
                    dfChanged,
                    mixVariance,
                    pl.col(volumeVariance) - pl.col(pureVolumeVariance),
                )
                dfChanged = clean_out_improbable_mix_variance_results(
                    dfChanged, pureVolumeVariance, volumeVariance
                )
            dfChanged = drop_columns(dfChanged, [volumeVariance])
            dfNewAndLost = dfNewAndLost.rename({volumeVariance: pureVolumeVariance})
            dfNewAndLost = dfNewAndLost.with_columns(
                pl.col(mixVariance).cast(pl.Float64)
            )
            columns, schema = get_schema_and_column_names(dfChanged)
            dfNewAndLost = dfNewAndLost.select(columns)
            df = pl.concat([dfChanged, dfNewAndLost])
    return df


def calculate_margin_mix_variance(dfCopy, paramDict, chartDict, indexCols):
    """
    mix variance on margin is the variance due to change of product mix and it is calculated, at some aggregated level,
    as the difference between the variance calculated as a granular sum, and the variance calculated at the granular level
    we recalculate the volume variance and set the difference between the recalculated variance and the volume variance as mix variance
    we check that we are not dealing with new volumes and we are not dealing with lost volumes
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixMarginAggregationArray = varianceAggregationParams[
        namingParams["mixMarginAggregationArray"]
    ]
    periodsArray = configParams["periodsArray"]
    workColumn = namingParams["workColumn"]
    totalVariance = namingParams["totalVariance"]
    priceVariance = namingParams["priceVarianceOnMargin"]
    volumeVariance = namingParams["volumeVarianceOnMargin"]
    driverVariance = namingParams["driverVariance"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    varianceAggregation = namingParams["varianceAggregation"]
    mixVariance = namingParams["mixVarianceOnMargin"]
    unitsName = namingParams["unitsName"]
    discountName = namingParams["discountName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    separatorString = namingParams["separatorString"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    pureVolumeVariance = namingParams["pureVolumeOnMarginVarianceName"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    mainDimension = namingParams["mainDimension"]
    varianceAggregation = namingParams["varianceAggregation"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    changedVolumeVarianceName = namingParams["changedVolumeVarianceName"]
    cogsName = namingParams["cogsName"]
    costVariance = namingParams["costVariance"]
    varianceInPercent = namingParams["varianceInPercent"]
    marginName = namingParams["marginName"]
    percentSuffix = namingParams["percentSuffix"]
    varianceAggregation = namingParams["varianceAggregation"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    if chartDict[varianceAggregation] in mixMarginAggregationArray:
        amountPeriodZero = monetaryName + separatorString + periodsArray[0]
        amountPeriodOne = monetaryName + separatorString + periodsArray[1]
        unitsPeriodZero = unitsName + separatorString + periodsArray[0]
        unitsPeriodOne = unitsName + separatorString + periodsArray[1]
        pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
        pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
        cogsPeriodZero = cogsName + separatorString + periodsArray[0]
        cogsPeriodOne = cogsName + separatorString + periodsArray[1]
        discountPeriodZero = discountName + separatorString + periodsArray[0]
        discountPeriodOne = discountName + separatorString + periodsArray[1]
        marginPeriodZero = marginName + separatorString + periodsArray[0]
        marginPeriodOne = marginName + separatorString + periodsArray[1]
        volumeVariancePercent = volumeVariance + percentSuffix
        pureVolumeVariancePercent = pureVolumeVariance + percentSuffix
        priceVariancePercent = priceVariance + percentSuffix
        costVariancePercent = costVariance + percentSuffix
        mixVariancePercent = mixVariance + percentSuffix
        df = duplicate_dataframe(dfCopy)
        columns, schema = get_schema_and_column_names(df)
        if unitsPeriodZero in columns and amountPeriodZero in columns:
            if chartDict[varianceInPercent] == metConditionValue:
                divideArray = make_divideArray(df, indexCols)
                df, paramDict = divide_back_if_multiplied(
                    df, paramDict, chartDict, divideArray, True
                )
            dfNewAndLost = duplicate_dataframe(df)
            dfChanged = duplicate_dataframe(df)
            dfNewAndLost = dfNewAndLost.filter(
                (pl.col(amountPeriodZero) == 0) | (pl.col(amountPeriodOne) == 0)
            )
            dfChanged = dfChanged.filter(
                (pl.col(amountPeriodZero) > 0) & (pl.col(amountPeriodOne) > 0)
            )
            paramDict = get_data_sample(
                dfChanged, "dfChanged_with_unit_cost_before", False, paramDict
            )
            if processingChoice in chartDict and chartDict[processingChoice] in [
                runOneDimensionalAnalysis
            ]:
                sumColsArray = [
                    amountPeriodZero,
                    amountPeriodOne,
                    unitsPeriodZero,
                    unitsPeriodOne,
                    pricePeriodZero,
                    pricePeriodOne,
                    cogsPeriodZero,
                    cogsPeriodOne,
                    costVariance,
                    discountPeriodZero,
                    discountPeriodOne,
                    totalVariance,
                    priceVariance,
                    volumeVariance,
                ]
                group_byCols = [mixVariance]
                dfChanged = _assign_column(dfChanged, mixVariance, 0)
                if mainDimension in chartDict and len(chartDict[mainDimension]) > 0:
                    group_byCols = chartDict[mainDimension] + group_byCols
                paramDict = get_data_sample(
                    dfChanged, "before_melt_group_by_fix_dimension", False, paramDict
                )
                group_byCols, sumColsArray = check_and_clean_columns(
                    dfChanged, group_byCols, sumColsArray
                )
                dfChanged = dfChanged.group_by(group_byCols, maintain_order=True).agg(
                    [pl.col(c).sum() for c in sumColsArray]
                )
                paramDict = get_data_sample(
                    dfChanged, "after_melt_group_by_fix_dimension", False, paramDict
                )
            if dfChanged.height > 0:
                dfChanged, paramDict = recalculate_price(dfChanged, paramDict)
                dfChanged = calculate_unit_cost(dfChanged, paramDict, chartDict)
                dfChanged = _assign_column(
                    dfChanged,
                    unitsChange,
                    pl.col(unitsPeriodOne) - pl.col(unitsPeriodZero),
                )
                dfChanged = _assign_column(
                    dfChanged,
                    priceChange,
                    pl.col(pricePeriodOne) - pl.col(pricePeriodZero),
                )
                dfChanged = calculate_volume_variance_with_unit_cost(
                    dfChanged, pureVolumeVariance, paramDict
                )
                dfChanged = _assign_column(
                    dfChanged,
                    mixVariance,
                    pl.col(volumeVariance) - pl.col(pureVolumeVariance),
                )
                paramDict = get_data_sample(
                    dfChanged, "dfChanged_with_unit_cost_after", False, paramDict
                )
            dfChanged = drop_columns(dfChanged, [volumeVariance])
            dfNewAndLost = dfNewAndLost.rename({volumeVariance: pureVolumeVariance})
            dfNewAndLost = _assign_column(dfNewAndLost, mixVariance, 0)
            df = pl.concat([dfChanged, dfNewAndLost])
            if chartDict[varianceInPercent] != metConditionValue:
                df = delete_useless_columns_after_unit_cost(df, paramDict)
        return df, paramDict
    else:
        return dfCopy, paramDict


def calculate_variance_in_percent_one_element(
    df, percentVariance, variance, dropCols, paramDict, metric
):
    """
    in the case that we want only one type of variance
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    separatorString = namingParams["separatorString"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    marginName = namingParams["marginName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    marginPeriodZero = marginName + separatorString + periodsArray[0]
    marginPeriodOne = marginName + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    netOfDiscountPeriodZero = netOfDiscountName + separatorString + periodsArray[0]
    netOfDiscountPeriodOne = netOfDiscountName + separatorString + periodsArray[1]
    totalAmountPeriodZero, totalAmountPeriodOne = get_year_totals(df, paramDict)
    columns, schema = get_schema_and_column_names(df)
    df = _assign_column(df, workColumn, np.nan)
    df = _assign_column(df, workColumnTwo, np.nan)
    if metric == discountName and discountPeriodZero in columns:
        df = fill_null_zero(df, [netOfDiscountPeriodZero, netOfDiscountPeriodOne])
        if totalAmountPeriodZero > 0:
            df = _assign_column(
                df,
                workColumn,
                pl.col(netOfDiscountPeriodZero) / totalAmountPeriodZero * 100,
            )
        if totalAmountPeriodOne > 0:
            df = _assign_column(
                df,
                workColumnTwo,
                pl.col(netOfDiscountPeriodOne) / totalAmountPeriodOne * 100,
            )
    elif metric == marginName and marginPeriodZero in columns:
        df = fill_null_zero(df, [marginPeriodZero, marginPeriodOne])
        if totalAmountPeriodZero > 0:
            df = _assign_column(
                df,
                workColumn,
                pl.col(marginPeriodZero) / totalAmountPeriodZero * 100,
            )
        if totalAmountPeriodOne > 0:
            df = _assign_column(
                df,
                workColumnTwo,
                pl.col(marginPeriodOne) / totalAmountPeriodOne * 100,
            )
    else:
        message = "could not find metric"
        paramDict = add_warning_message_in_variance_options_tab(paramDict, message)
    columns, schema = get_schema_and_column_names(df)
    if workColumn in columns:
        df = _assign_column(
            df, percentVariance, pl.col(workColumnTwo) - pl.col(workColumn)
        )
    dropCols.append(variance)
    return df, dropCols


def calculate_variance_in_percent(
    df, paramDict, chartDict, calculateOnlyVolumeVariance
):
    """
    we calculate the margin and discount variance in percent,
    """
    namingParams = get_naming_params()
    marginName = namingParams["marginName"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    percentSuffix = namingParams["percentSuffix"]
    varianceAggregation = namingParams["varianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    marginVariance = namingParams["marginVariance"]
    mainDimension = namingParams["mainDimension"]
    nothingThereString = namingParams["nothingThereString"]
    marginVariancePercent = marginVariance + percentSuffix
    dropCols = [workColumnTwo, workColumn]
    if chartDict[varianceAggregation] in [marginVarianceAggregation]:
        df, dropCols = calculate_variance_in_percent_one_element(
            df, marginVariancePercent, marginVariance, dropCols, paramDict, marginName
        )
        if mainDimension in chartDict:
            mainDimension = chartDict[mainDimension][0]
            df = df.filter(pl.col(mainDimension) != nothingThereString)
    paramDict = get_data_sample(df, "before_melt_percent", False, paramDict)
    df = drop_columns(df, dropCols)
    return df, paramDict


def calculate_driver_variance(df, paramDict, chartDict):
    """
    if a driver column exits we calculate driver variance
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    driverColsArray = configParams[namingParams["driverColsArray"]]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    driverName = namingParams["driverName"]
    driverAndUnitsAggregation = namingParams["driverAndUnitsAggregation"]
    driverAndVolumeAggregation = namingParams["driverAndVolumeAggregation"]
    driverAggregation = namingParams["driverAggregation"]
    mixUnitsDriverAggregation = namingParams["mixUnitsDriverAggregation"]
    mixVolumeDriverAggregation = namingParams["mixVolumeDriverAggregation"]
    mixAggregation = namingParams["mixAggregation"]
    unitsChange = namingParams["unitsChange"]
    changeName = namingParams["changeName"]
    varianceAggregation = namingParams["varianceAggregation"]
    calculateDriverVariance = namingParams["calculateDriverVariance"]
    baseVarianceName = namingParams["baseVarianceName"]
    baseVarianceUnits = namingParams["baseVarianceUnits"]
    separatorString = namingParams["separatorString"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    totalVariance = namingParams["totalVariance"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    baseVarianceDriverArray = namingParams["baseVarianceDriverArray"]
    driverArray = namingParams["driverArray"]
    columns, schema = get_schema_and_column_names(df)
    toDrop = []
    paramDict[calculateDriverVariance] = notMetConditionValue
    if varianceAggregation in chartDict and chartDict[varianceAggregation] in [
        driverAndUnitsAggregation,
        driverAndVolumeAggregation,
        driverAggregation,
        mixUnitsDriverAggregation,
        mixVolumeDriverAggregation,
        mixAggregation,
    ]:
        paramDict[driverArray] = []
        for column in driverColsArray:
            if column + separatorString + periodsArray[0] in columns:
                paramDict[calculateDriverVariance] = metConditionValue
                if column not in paramDict[driverArray]:
                    paramDict[driverArray].append(column)
    if paramDict[calculateDriverVariance]:
        paramDict[baseVarianceDriverArray] = []
        for driver in paramDict[driverArray]:
            driverPeriodZero = driver + separatorString + periodsArray[0]
            driverPeriodOne = driver + separatorString + periodsArray[1]
            driverChange = driver + " " + changeName
            baseVarianceDriver = baseVarianceName + " " + driver
            if baseVarianceDriver not in paramDict[baseVarianceDriverArray]:
                paramDict[baseVarianceDriverArray].append(baseVarianceDriver)
            df = _assign_where(
                df,
                pl.col(driverPeriodZero) != 0,
                driverChange,
                (pl.col(driverPeriodOne) - pl.col(driverPeriodZero))
                / pl.col(driverPeriodZero),
            )
            if paramDict[namingParams["unitsColFound"]]:
                df = _assign_column(
                    df,
                    baseVarianceDriver,
                    pl.col(unitsPeriodZero)
                    * pl.col(pricePeriodZero)
                    * pl.col(driverChange),
                )
            else:
                df = _assign_column(
                    df,
                    baseVarianceDriver,
                    pl.col(amountPeriodZero) * pl.col(driverChange),
                )
            df = fill_null_zero(df, [baseVarianceDriver, driverChange])
            toDrop.append(driverChange)
    df = drop_columns(df, toDrop)
    paramDict = get_data_sample(df, "calculate_driver_variance", False, paramDict)
    df = calculate_driver_columns_base_variance(df, paramDict)
    paramDict = get_data_sample(
        df, "calculate_driver_columns_base_variance", False, paramDict
    )
    return df, paramDict


def calculate_driver_columns_base_variance(df, paramDict):
    """
    since the driver columns can be more than one,
    we need to compute the base variance differently
    """
    namingParams = get_naming_params()
    baseVarianceDriverArray = namingParams["baseVarianceDriverArray"]
    baseVarianceUnits = namingParams["baseVarianceUnits"]
    if baseVarianceDriverArray in paramDict:
        baseVarianceDriverArray = paramDict[baseVarianceDriverArray]
        df = _assign_where(
            df,
            pl.sum_horizontal([pl.col(c) for c in baseVarianceDriverArray]) != 0,
            baseVarianceUnits,
            pl.col(baseVarianceUnits)
            - pl.sum_horizontal([pl.col(c) for c in baseVarianceDriverArray]),
        )
    df = fill_null_zero(df, baseVarianceUnits)
    return df


def calculate_residual_variance(df, paramDict, chartDict):
    """
    we simply attribute the residual, un accounted for, variance
    proportionally to the value of the price and volume variance
    """
    namingParams = get_naming_params()
    driverName = namingParams["driverName"]
    varianceName = namingParams["varianceName"]
    priceVariance = namingParams["priceVariance"]
    volumeVariance = namingParams["volumeVariance"]
    priceVarianceOnMargin = namingParams["priceVarianceOnMargin"]
    volumeVarianceOnMargin = namingParams["volumeVarianceOnMargin"]
    driverVariance = namingParams["driverVariance"]
    residualVariance = namingParams["residualVariance"]
    residualVariancePrice = namingParams["residualVariancePrice"]
    residualVarianceVolume = namingParams["residualVarianceVolume"]
    totalVariance = namingParams["totalVariance"]
    baseVariancePrice = namingParams["baseVariancePrice"]
    baseVarianceUnits = namingParams["baseVarianceUnits"]
    baseVarianceDriver = namingParams["baseVarianceDriver"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    isRevenueChanged = namingParams["isRevenueChanged"]
    varianceAggregation = namingParams["varianceAggregation"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
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
    workColumn = namingParams["workColumn"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    varianceInPercent = namingParams["varianceInPercent"]
    metConditionValue = namingParams["metConditionValue"]
    columns, _ = get_schema_and_column_names(df)
    if volumeVariance not in columns:
        df = _assign_column(df, volumeVariance, 0)
    if priceVariance not in columns:
        df = _assign_column(df, priceVariance, 0)
    notDriverAggregations = [
        discountsUnitsCogsAggregation,
        discountsVolumeCogsAggregation,
        discountsAggregation,
        cogsAggregation,
        unitsOnMarginAggregation,
        volumeOnMarginAggregation,
        unitPriceOnMarginAggregation,
        volumePriceOnMarginAggregation,
        marginUnitsRateAggregation,
        marginVolumeRateAggregation,
        costsUnitsAggregation,
        costsVolumeAggregation,
        costsUnitsMixAggregation,
        costsVolumeMixAggregation,
        discountsAndUnitsAggregation,
        discountsAndVolumeAggregation,
    ]
    if paramDict[namingParams["unitsColFound"]]:
        if (
            varianceAggregation in chartDict
            and not paramDict[namingParams["calculateDriverVariance"]]
        ):
            if (
                varianceAggregation in chartDict
                and chartDict[varianceAggregation] not in notDriverAggregations
            ):
                df = _assign_column(df, residualVariance, 0)
                mask_zero = pl.col(baseVarianceUnits) + pl.col(baseVariancePrice) == 0
                df = _assign_where(
                    df, mask_zero, isRevenueChanged, notMetConditionValue
                )
                mask_rev = pl.col(isRevenueChanged) == metConditionValue
                df = _assign_where(
                    df,
                    mask_rev,
                    volumeVariance,
                    pl.col(baseVarianceUnits)
                    + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
                )
                df = _assign_where(
                    df,
                    mask_rev,
                    priceVariance,
                    pl.col(baseVariancePrice)
                    + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
                )
            elif varianceAggregation in chartDict and chartDict[
                varianceAggregation
            ] in [
                discountsUnitsCogsAggregation,
                discountsVolumeCogsAggregation,
            ]:
                df = df.with_columns(
                    [
                        pl.col(baseVarianceUnits).alias(volumeVarianceOnMargin),
                        pl.col(baseVariancePrice).alias(priceVarianceOnMargin),
                    ]
                )
            elif varianceAggregation in chartDict and chartDict[
                varianceAggregation
            ] in [
                discountsAggregation,
                cogsAggregation,
                unitsOnMarginAggregation,
                volumeOnMarginAggregation,
                unitPriceOnMarginAggregation,
                volumePriceOnMarginAggregation,
            ]:
                df = df.with_columns(
                    [
                        pl.col(baseVarianceUnits).alias(volumeVariance),
                        pl.col(baseVariancePrice).alias(priceVariance),
                    ]
                )
            elif chartDict[varianceInPercent] == metConditionValue:
                df = _assign_column(df, residualVariance, 0)
                mask_zero = pl.col(baseVarianceUnits) + pl.col(baseVariancePrice) == 0
                df = _assign_where(
                    df, mask_zero, isRevenueChanged, notMetConditionValue
                )
                mask_rev = pl.col(isRevenueChanged) == metConditionValue
                df = _assign_where(
                    df,
                    mask_rev,
                    volumeVariance,
                    pl.col(baseVarianceUnits)
                    + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
                )
                df = _assign_where(
                    df,
                    mask_rev,
                    priceVariance,
                    pl.col(baseVariancePrice)
                    + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
                )

        elif paramDict[namingParams["calculateDriverVariance"]]:
            mask_zero = pl.col(baseVarianceUnits) + pl.col(baseVariancePrice) == 0
            df = _assign_where(df, mask_zero, isRevenueChanged, notMetConditionValue)
            mask_rev = pl.col(isRevenueChanged) == metConditionValue
            df = _assign_where(
                df,
                mask_rev,
                volumeVariance,
                pl.col(baseVarianceUnits)
                + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
            )
            df = _assign_where(
                df,
                mask_rev,
                priceVariance,
                pl.col(baseVariancePrice)
                + (pl.col(priceChange) * pl.col(unitsChange)) / 2,
            )
            count = 0
            renameDict = {}
            for baseElement in paramDict[namingParams["baseVarianceDriverArray"]]:
                element = paramDict[namingParams["driverArray"]][count]
                renameDict[baseElement] = element
                count = count + 1
    elif not paramDict[namingParams["calculateDriverVariance"]]:
        if varianceAggregation in chartDict and chartDict[varianceAggregation] in [
            discountsUnitsCogsAggregation,
            discountsVolumeCogsAggregation,
        ]:
            df = _assign_column(df, volumeVarianceOnMargin, pl.col(baseVarianceUnits))
        else:
            df = _assign_column(df, volumeVariance, pl.col(baseVarianceUnits))
    elif paramDict[namingParams["calculateDriverVariance"]]:
        df = df.with_columns(
            [
                pl.col(baseVarianceUnits).alias(volumeVariance),
                pl.col(baseVarianceDriver).alias(driverVariance),
            ]
        )
    if paramDict[namingParams["calculateDriverVariance"]]:
        df = df.rename(renameDict)
    toDrop = [isRevenueChanged]
    df = drop_columns(df, toDrop)
    return df, paramDict


def calculate_base_variance(df, paramDict, chartDict):
    """
    the base component of the volume variance is the difference in pieces between period 1 and period zero volumes times period 0 price
    the base component of the price variance is the difference in pieces between period 1 and period zero prices times period 1 volume
    total variance is the actual difference between sales in period 1 and sales in period 0
    """
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    isRevenueChanged = namingParams["isRevenueChanged"]
    totalVariance = namingParams["totalVariance"]
    df = calculate_total_variance(df)
    df, paramDict = calculate_volume_and_price_variance(df, paramDict, chartDict)
    paramDict = get_data_sample(
        df, "calculate_volume_and_price_variance", False, paramDict
    )
    df, paramDict = calculate_driver_variance(df, paramDict, chartDict)
    df = _assign_column(df, isRevenueChanged, metConditionValue)
    mask = pl.col(totalVariance) == 0
    df = _assign_where(df, mask, isRevenueChanged, notMetConditionValue)
    return df, paramDict


def calculate_margin_rate_variance(df, paramDict):
    """
    if a driver column exits we calculate cogs and discount variance (together)
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    separatorString = namingParams["separatorString"]
    marginRateVariance = namingParams["marginRateVariance"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    marginRateChange = namingParams["marginRateChange"]
    marginRate = namingParams["marginRate"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    workColumnThree = namingParams["workColumnThree"]
    workColumnFour = namingParams["workColumnFour"]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    marginRatePeriodZero = marginRate + separatorString + periodsArray[0]
    df = df.with_columns(
        [
            (pl.col(pricePeriodZero) * pl.col(unitsPeriodZero)).alias(workColumn),
            ((pl.col(priceChange) * pl.col(unitsPeriodZero)) / 2).alias(workColumnTwo),
            ((pl.col(unitsChange) * pl.col(pricePeriodZero)) / 2).alias(
                workColumnThree
            ),
            ((pl.col(priceChange) * pl.col(unitsChange)) / 3).alias(workColumnFour),
        ]
    )
    df = _assign_column(
        df,
        marginRateVariance,
        pl.col(marginRateChange)
        * (
            pl.col(workColumn)
            + pl.col(workColumnTwo)
            + pl.col(workColumnThree)
            + pl.col(workColumnFour)
        ),
    )
    toDrop = [workColumn, workColumnTwo, workColumnThree, workColumnFour]
    df = drop_columns(df, toDrop)
    return df


def calculate_volume_variance_with_margin_rate(df, paramDict):
    """
    if a driver column exits we calculate driver variance
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    separatorString = namingParams["separatorString"]
    volumeVariance = namingParams["volumeVarianceOnMargin"]
    marginRateVariance = namingParams["marginRateVariance"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    marginRateChange = namingParams["marginRateChange"]
    marginRate = namingParams["marginRate"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    workColumnThree = namingParams["workColumnThree"]
    workColumnFour = namingParams["workColumnFour"]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    marginRatePeriodZero = marginRate + separatorString + periodsArray[0]
    df = _assign_column(
        df, workColumn, pl.col(pricePeriodZero) * pl.col(marginRatePeriodZero)
    )
    df = _assign_column(
        df, workColumnTwo, (pl.col(priceChange) * pl.col(marginRatePeriodZero)) / 2
    )
    df = _assign_column(
        df, workColumnThree, pl.col(marginRateChange) * pl.col(pricePeriodZero) / 2
    )
    df = _assign_column(
        df, workColumnFour, pl.col(priceChange) * pl.col(marginRateChange) / 3
    )
    df = _assign_column(
        df,
        volumeVariance,
        pl.col(unitsChange)
        * (
            pl.col(workColumn)
            + pl.col(workColumnTwo)
            + pl.col(workColumnThree)
            + pl.col(workColumnFour)
        ),
    )
    toDrop = [workColumn, workColumnTwo, workColumnThree, workColumnFour]
    df = drop_columns(df, toDrop)
    return df


def clean_nan_from_cols(df, arrayNumber):
    """
    fill nan with 0
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    volumeVariance = namingParams["volumeVariance"]
    priceVariance = namingParams["priceVariance"]
    discountVariance = namingParams["discountVariance"]
    cogsVariance = namingParams["COGSVariance"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    pureVolumeVarianceName = namingParams["pureVolumeVarianceName"]
    newVolumeVarianceName = namingParams["newVolumeVarianceName"]
    lostVolumeVarianceName = namingParams["lostVolumeVarianceName"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    cogsPeriodZero = cogsName + separatorString + periodsArray[0]
    cogsPeriodOne = cogsName + separatorString + periodsArray[1]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    arrayOne = [
        priceVariance,
        volumeVariance,
        discountVariance,
        cogsVariance,
        amountPeriodZero,
        amountPeriodOne,
        unitsPeriodZero,
        unitsPeriodOne,
        cogsPeriodZero,
        discountPeriodZero,
        cogsPeriodOne,
        discountPeriodOne,
    ]
    arrayTwo = [
        priceVariance,
        volumeVariance,
        pureVolumeVarianceName,
        changedVolumeVarianceMixName,
        newVolumeVarianceName,
        lostVolumeVarianceName,
    ]
    if arrayNumber == 1:
        toCleanArray = arrayOne
    else:
        toCleanArray = arrayTwo
    columns, schema = get_schema_and_column_names(df)
    for toCleancol in toCleanArray:
        if toCleancol in columns:
            df = fill_null_zero(df, toCleancol)
    return df


def calculate_variance_if_one_period_no_sales(df, paramDict):
    """
    if there are no sales in the period 0 or period 1
    the variance is considered all volume variance
    """
    namingParams = get_naming_params()
    volumeVariance = namingParams["volumeVariance"]
    priceVariance = namingParams["priceVariance"]
    discountVariance = namingParams["discountVariance"]
    cogsVariance = namingParams["COGSVariance"]
    marginRateVariance = namingParams["marginRateVariance"]
    costVariance = namingParams["costVariance"]
    changedVolumeVarianceMixName = namingParams["changedVolumeVarianceMixName"]
    newAndLostUnitsAggregation = namingParams["newAndLostUnitsAggregation"]
    newAndLostVolumeAggregation = namingParams["newAndLostVolumeAggregation"]
    newAndLostUnitsMixAggregation = namingParams["newAndLostUnitsMixAggregation"]
    newAndLostVolumeMixAggregation = namingParams["newAndLostVolumeMixAggregation"]
    newAggregation = namingParams["newAggregation"]
    lostAggregation = namingParams["lostAggregation"]
    changedAggregation = namingParams["changedAggregation"]
    workColumn = namingParams["workColumn"]
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
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
    varianceAggregationKey = namingParams["varianceAggregation"]
    isdiscountColFound = paramDict[namingParams["discountColFound"]]
    isCogsColFound = paramDict[namingParams["cogsColFound"]]
    varianceInPercent = namingParams["varianceInPercent"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    isFilteredKey = namingParams["isFilteredKey"]
    driverAggregation = namingParams["driverAggregation"]
    categoryWeightedDistributionName = namingParams["categoryWeightedDistributionName"]
    baseVarianceDriverArray = namingParams["baseVarianceDriverArray"]
    df = clean_nan_from_cols(df, 1)
    if varianceAggregationKey in paramDict:
        varianceAggregation = paramDict[varianceAggregationKey]
    else:
        varianceAggregation = False
    if varianceAggregation:
        if varianceAggregation not in [
            newAndLostUnitsAggregation,
            newAndLostVolumeAggregation,
            newAndLostUnitsMixAggregation,
            newAndLostVolumeMixAggregation,
            newAggregation,
            lostAggregation,
            changedAggregation,
            marginUnitsRateAggregation,
            marginVolumeRateAggregation,
            costsUnitsAggregation,
            costsVolumeAggregation,
            costsUnitsMixAggregation,
            costsVolumeMixAggregation,
            discountsAndUnitsAggregation,
            discountsAndVolumeAggregation,
            discountsUnitsCogsAggregation,
            discountsVolumeCogsAggregation,
            discountsAggregation,
            cogsAggregation,
            unitPriceOnMarginAggregation,
            volumePriceOnMarginAggregation,
            unitsOnMarginAggregation,
            volumeOnMarginAggregation,
        ]:
            if driverAggregation in varianceAggregation:
                if (
                    baseVarianceDriverArray in paramDict
                    and categoryWeightedDistributionName
                    in paramDict[baseVarianceDriverArray][0]
                ):
                    newOrLost, varianceMetric = False, "WeightedDistribution"
                    # if new product we count variance as distribution variance
                else:
                    newOrLost, varianceMetric = False, "onGrossSales"
            else:
                newOrLost, varianceMetric = False, "onGrossSales"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
        elif varianceAggregation in [
            marginUnitsRateAggregation,
            marginVolumeRateAggregation,
        ]:
            newOrLost, varianceMetric = False, "onMargin"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
            if isdiscountColFound and isCogsColFound:
                df = set_variance_if_one_period_no_sales_and_discount_and_cogs(
                    df, marginRateVariance, varianceMetric
                )
            elif isdiscountColFound:
                df = set_variance_if_one_period_no_sales_and_discount(
                    df, marginRateVariance
                )
            elif isCogsColFound:
                df, paramDict = set_variance_if_one_period_no_sales_and_cogs(
                    df, marginRateVariance, varianceMetric, paramDict
                )
        elif varianceAggregation in [
            discountsUnitsCogsAggregation,
            discountsVolumeCogsAggregation,
            discountsAggregation,
            cogsAggregation,
            unitPriceOnMarginAggregation,
            volumePriceOnMarginAggregation,
            unitsOnMarginAggregation,
            volumeOnMarginAggregation,
        ]:
            newOrLost, varianceMetric = False, "onMargin"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
            if isdiscountColFound:
                df = set_variance_if_one_period_no_sales_and_discount(
                    df, discountVariance
                )
            if isCogsColFound:
                df, paramDict = set_variance_if_one_period_no_sales_and_cogs(
                    df, cogsVariance, varianceMetric, paramDict
                )
        elif varianceAggregation in [
            costsUnitsAggregation,
            costsVolumeAggregation,
            costsUnitsMixAggregation,
            costsVolumeMixAggregation,
        ]:
            newOrLost, varianceMetric = False, "onMargin"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
            if isdiscountColFound and isCogsColFound:
                df = set_variance_if_one_period_no_sales_and_discount_and_cogs(
                    df, costVariance, varianceMetric
                )
            elif isdiscountColFound:
                df = set_variance_if_one_period_no_sales_and_discount(df, costVariance)
            elif isCogsColFound:
                df, paramDict = set_variance_if_one_period_no_sales_and_cogs(
                    df, costVariance, varianceMetric, paramDict
                )
        elif varianceAggregation in [
            discountsAndUnitsAggregation,
            discountsAndVolumeAggregation,
        ]:
            newOrLost, varianceMetric = False, "onNetSales"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
            paramDict = get_data_sample(df, "dopo_1", False, paramDict)
            if isdiscountColFound:
                df = set_variance_if_one_period_no_sales_and_discount(
                    df, discountVariance
                )
                paramDict = get_data_sample(df, "dopo_2", False, paramDict)
        elif varianceAggregation in [
            newAndLostUnitsAggregation,
            newAndLostVolumeAggregation,
            newAndLostUnitsMixAggregation,
            newAndLostVolumeMixAggregation,
            newAggregation,
            lostAggregation,
            changedAggregation,
        ]:
            newOrLost, varianceMetric = True, "onGrossSales"
            df, paramDict = set_volume_and_price_variance_if_one_period_no_sales(
                df, newOrLost, varianceMetric, paramDict
            )
            df = df.rename({volumeVariance: changedVolumeVarianceMixName})
        df = clean_nan_from_cols(df, 2)
    else:
        df = pl.DataFrame()
    return df, paramDict


def check_variance(df):
    """
    for testing variance we need have columns to keep track of calculations
    if not testing we drop them
    """
    runParams = get_run_params()
    checkVariance = runParams["checkVariance"]
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    separatorString = namingParams["separatorString"]
    residualVariance = namingParams["residualVariance"]
    residualVariancePrice = namingParams["residualVariancePrice"]
    residualVarianceVolume = namingParams["residualVarianceVolume"]
    baseVariancePrice = namingParams["baseVariancePrice"]
    baseVarianceUnits = namingParams["baseVarianceUnits"]
    baseVarianceDriver = namingParams["baseVarianceDriver"]
    totalVariance = namingParams["totalVariance"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    driverChange = namingParams["driverChange"]
    amountPeriodZero = monetaryName + separatorString + periodsArray[0]
    amountPeriodOne = monetaryName + separatorString + periodsArray[1]
    if checkVariance:
        df = _assign_where(
            df,
            pl.col(amountPeriodZero) == 0,
            totalVariance,
            pl.col(amountPeriodOne),
        )
        df = _assign_where(
            df,
            pl.col(amountPeriodOne) == 0,
            totalVariance,
            -pl.col(amountPeriodZero),
        )
        df = _assign_where(df, pl.col(amountPeriodZero) == 0, residualVariance, 0)
        df = _assign_where(df, pl.col(amountPeriodOne) == 0, residualVariance, 0)
    else:
        toDrop = [
            residualVariance,
            residualVarianceVolume,
            residualVariancePrice,
            baseVariancePrice,
            baseVarianceUnits,
            baseVarianceDriver,
            priceChange,
            unitsChange,
            driverChange,
        ]
        df = drop_columns(df, toDrop)
    return df


def calculate_variance(df, paramDict, chartDict):
    """
    we calculate the variance in price and in volume Whatever is left must be mix
    """
    namingParams = get_naming_params()
    varianceAggregation = namingParams["varianceAggregation"]
    varianceAggregationValue, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["varianceAggregation"], False
    )
    if is_valid_lazyframe(df):
        df, paramDict = calculate_base_variance(df, paramDict, chartDict)
        paramDict = get_data_sample(df, "calculate_base_variance", False, paramDict)
        df, paramDict = calculate_residual_variance(df, paramDict, chartDict)
        paramDict = get_data_sample(df, "calculate_residual_variance", False, paramDict)
        df, paramDict = calculate_variance_if_one_period_no_sales(df, paramDict)
        paramDict = get_data_sample(
            df, "calculate_variance_if_one_period_no_sales", False, paramDict
        )
        df = check_variance(df)
    return df, paramDict


def calculate_total_variance(df):
    """
    calculate difference between period one and period 0 values at the different levels
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    cogsName = namingParams["cogsName"]
    marginName = namingParams["marginName"]
    totalVariance = namingParams["totalVariance"]
    discountVariance = namingParams["discountVariance"]
    COGSVariance = namingParams["COGSVariance"]
    separatorString = namingParams["separatorString"]
    amountColsDict = {
        monetaryName: totalVariance,
        discountName: discountVariance,
        cogsName: COGSVariance,
    }
    changeSignArray = [discountVariance, COGSVariance]
    columns, schema = get_schema_and_column_names(df)
    for valueColumn, varianceCol in amountColsDict.items():
        amountPeriodZero = valueColumn + separatorString + periodsArray[0]
        amountPeriodOne = valueColumn + separatorString + periodsArray[1]
        if amountPeriodZero in columns and amountPeriodOne in columns:
            columnArray = [amountPeriodZero, amountPeriodOne]
            df = fill_null_zero(df, columnArray)
            df = df.with_columns(
                (pl.col(amountPeriodOne) - pl.col(amountPeriodZero)).alias(varianceCol)
            )
            df = fill_null_zero(df, varianceCol)
    columns, schema = get_schema_and_column_names(df)
    exprs = [
        (-pl.col(column)).alias(column)
        for column in changeSignArray
        if column in columns
    ]
    if exprs:
        df = df.with_columns(exprs)
    return df


def delete_useless_columns_after_margin_rate(df, paramDict):
    """
    taking out the columns we do not need anymore after calculting variance with allocation
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    marginRateChange = namingParams["marginRateChange"]
    separatorString = namingParams["separatorString"]
    discountsCogsName = namingParams["discountsCogsName"]
    marginRate = namingParams["marginRate"]
    discountsCogsPeriodZero = discountsCogsName + separatorString + periodsArray[0]
    discountsCogsPeriodOne = discountsCogsName + separatorString + periodsArray[1]
    marginRatePeriodZero = marginRate + separatorString + periodsArray[0]
    marginRatePeriodOne = marginRate + separatorString + periodsArray[1]
    toDrop = [
        marginRateChange,
        discountsCogsPeriodZero,
        discountsCogsPeriodOne,
        marginRatePeriodZero,
        marginRatePeriodOne,
    ]
    df = drop_columns(df, toDrop)
    columns, schema = get_schema_and_column_names(df)
    return df


def delete_useless_columns_after_unit_cost(df, paramDict):
    """
    taking out the columns we do not need anymore after calculting variance with allocation
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixMarginAggregationArray = varianceAggregationParams[
        namingParams["mixMarginAggregationArray"]
    ]
    periodsArray = configParams["periodsArray"]
    marginRateChange = namingParams["marginRateChange"]
    separatorString = namingParams["separatorString"]
    discountsCogsName = namingParams["discountsCogsName"]
    marginRate = namingParams["marginRate"]
    costPerUnitChange = namingParams["costPerUnitChange"]
    costPerUnitName = namingParams["costPerUnitName"]
    varianceAggregation = namingParams["varianceAggregation"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    costPerUnitPeriodZero = costPerUnitName + separatorString + periodsArray[0]
    costPerUnitPeriodOne = costPerUnitName + separatorString + periodsArray[1]
    toDrop = [
        costPerUnitChange,
        costPerUnitPeriodZero,
        costPerUnitPeriodOne,
        priceChange,
        unitsChange,
    ]
    df = drop_columns(df, toDrop)
    return df


def calculate_volume_and_price_variance(df, paramDict, chartDict):
    """
    if a units columns exits, both volume and price variance can be calculated.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    volumeVariance = namingParams["volumeVariance"]
    volumeVarianceOnMargin = namingParams["volumeVarianceOnMargin"]
    volumeVarianceOnNetSales = namingParams["volumeVarianceOnNetSales"]
    priceVariance = namingParams["priceVariance"]
    priceVarianceOnMargin = namingParams["priceVarianceOnMargin"]
    priceVarianceOnNetSales = namingParams["priceVarianceOnNetSales"]
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    marginName = namingParams["marginName"]
    marginChange = namingParams["marginChange"]
    discountPerUnitName = namingParams["discountPerUnitName"]
    cogsPerUnitName = namingParams["cogsPerUnitName"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    discountUnitChange = namingParams["discountUnitChange"]
    cogsUnitChange = namingParams["cogsUnitChange"]
    netPriceChange = namingParams["netPriceChange"]
    baseVariancePrice = namingParams["baseVariancePrice"]
    baseVarianceUnits = namingParams["baseVarianceUnits"]
    discountVariance = namingParams["discountVariance"]
    cogsVariance = namingParams["COGSVariance"]
    separatorString = namingParams["separatorString"]
    varianceAggregation = namingParams["varianceAggregation"]
    discountsUnitsCogsAggregation = namingParams["discountsUnitsCogsAggregation"]
    discountsVolumeCogsAggregation = namingParams["discountsVolumeCogsAggregation"]
    unitPriceOnMarginAggregation = namingParams["unitPriceOnMarginAggregation"]
    volumePriceOnMarginAggregation = namingParams["volumePriceOnMarginAggregation"]
    unitsOnMarginAggregation = namingParams["unitsOnMarginAggregation"]
    volumeOnMarginAggregation = namingParams["volumeOnMarginAggregation"]
    discountsAndUnitsAggregation = namingParams["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = namingParams["discountsAndVolumeAggregation"]
    discountsAggregation = namingParams["discountsAggregation"]
    cogsAggregation = namingParams["cogsAggregation"]
    marginUnitsRateAggregation = namingParams["marginUnitsRateAggregation"]
    marginVolumeRateAggregation = namingParams["marginVolumeRateAggregation"]
    costsUnitsAggregation = namingParams["costsUnitsAggregation"]
    costsVolumeAggregation = namingParams["costsVolumeAggregation"]
    costsUnitsMixAggregation = namingParams["costsUnitsMixAggregation"]
    costsVolumeMixAggregation = namingParams["costsVolumeMixAggregation"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    metConditionValue = namingParams["metConditionValue"]
    varianceInPercent = namingParams["varianceInPercent"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    pricePeriodOne = pricePerUnitName + separatorString + periodsArray[1]
    discountPerUnitPeriodZero = discountPerUnitName + separatorString + periodsArray[0]
    discountPerUnitPeriodOne = discountPerUnitName + separatorString + periodsArray[1]
    cogsPerUnitPeriodZero = cogsPerUnitName + separatorString + periodsArray[0]
    cogsPerUnitPeriodOne = cogsPerUnitName + separatorString + periodsArray[1]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    unitsPeriodOne = unitsName + separatorString + periodsArray[1]
    marginPeriodZero = marginName + separatorString + periodsArray[0]
    marginPeriodOne = marginName + separatorString + periodsArray[1]
    totalVariance = namingParams["totalVariance"]
    isunitsColFound = paramDict[namingParams["unitsColFound"]]
    isdiscountColFound = paramDict[namingParams["discountColFound"]]
    isCogsColFound = paramDict[namingParams["cogsColFound"]]
    columns, schema = get_schema_and_column_names(df)
    if volumeVariance not in columns:
        df = _assign_column(df, volumeVariance, 0)
    if (
        varianceAggregation in chartDict
        and isunitsColFound
        and unitsPeriodZero in columns
    ):
        df = _assign_column(
            df,
            unitsChange,
            pl.col(unitsPeriodOne) - pl.col(unitsPeriodZero),
        )
        df = _assign_column(
            df,
            priceChange,
            pl.col(pricePeriodOne) - pl.col(pricePeriodZero),
        )
        df = _assign_column(
            df,
            baseVarianceUnits,
            pl.col(pricePeriodZero) * pl.col(unitsChange),
        )
        df = _assign_column(
            df,
            baseVariancePrice,
            pl.col(unitsPeriodZero) * pl.col(priceChange),
        )
        df = fill_null_zero(df, baseVariancePrice)
        unitCostAggregationArray = [
            costsUnitsAggregation,
            costsVolumeAggregation,
            costsUnitsMixAggregation,
            costsVolumeMixAggregation,
            discountsAndUnitsAggregation,
            discountsAndVolumeAggregation,
        ]
        if isCogsColFound and chartDict[varianceAggregation] in [
            discountsUnitsCogsAggregation,
            discountsVolumeCogsAggregation,
            discountsAggregation,
            cogsAggregation,
            unitsOnMarginAggregation,
            volumeOnMarginAggregation,
            unitPriceOnMarginAggregation,
            volumePriceOnMarginAggregation,
        ]:
            if isdiscountColFound:
                df = _assign_column(
                    df,
                    discountUnitChange,
                    pl.col(discountPerUnitPeriodOne)
                    - pl.col(discountPerUnitPeriodZero),
                )
                df = _assign_column(
                    df,
                    discountVariance,
                    -pl.col(unitsPeriodZero) * pl.col(discountUnitChange),
                )
                df = _assign_column(
                    df,
                    netPriceChange,
                    pl.col(pricePeriodOne)
                    - (pl.col(discountPerUnitPeriodOne) + pl.col(cogsPerUnitPeriodOne)),
                )
            else:
                df = _assign_column(
                    df,
                    netPriceChange,
                    pl.col(pricePeriodOne) - pl.col(cogsPerUnitPeriodOne),
                )

            df = _assign_column(
                df,
                cogsUnitChange,
                pl.col(cogsPerUnitPeriodOne) - pl.col(cogsPerUnitPeriodZero),
            )
            df = _assign_column(
                df,
                cogsVariance,
                -pl.col(unitsPeriodZero) * pl.col(cogsUnitChange),
            )
            df = _assign_column(
                df, baseVarianceUnits, pl.col(netPriceChange) * pl.col(unitsChange)
            )
            df = _assign_column(
                df,
                marginChange,
                pl.col(marginPeriodOne) - pl.col(marginPeriodZero),
            )
            if isdiscountColFound:
                expr = (
                    pl.col(baseVarianceUnits)
                    + pl.col(baseVariancePrice)
                    + pl.col(discountVariance)
                    + pl.col(cogsVariance)
                )
            else:
                expr = (
                    pl.col(baseVarianceUnits)
                    + pl.col(baseVariancePrice)
                    + pl.col(cogsVariance)
                )
            df = _assign_column(df, workColumn, expr)
            df = _assign_column(
                df, workColumnTwo, pl.col(marginChange) - pl.col(workColumn)
            )
            df = _assign_column(
                df, baseVarianceUnits, pl.col(baseVarianceUnits) + pl.col(workColumnTwo)
            )
            df = drop_columns(
                df,
                [
                    workColumn,
                    workColumnTwo,
                    discountUnitChange,
                    marginChange,
                    netPriceChange,
                    cogsUnitChange,
                ],
            )
        elif (
            varianceAggregation in chartDict
            and chartDict[varianceAggregation]
            in [marginUnitsRateAggregation, marginVolumeRateAggregation]
            and (isdiscountColFound or isCogsColFound)
        ):
            df = calculate_margin_rate(df, paramDict)
            df = calculate_price_variance_with_margin_rate(df, paramDict)
            df = calculate_volume_variance_with_margin_rate(df, paramDict)
            df = calculate_margin_rate_variance(df, paramDict)
            df = delete_useless_columns_after_margin_rate(df, paramDict)
        elif (
            varianceAggregation in chartDict
            and chartDict[varianceAggregation] in unitCostAggregationArray
            and (isdiscountColFound or isCogsColFound)
        ):
            if varianceAggregation in chartDict and chartDict[varianceAggregation] in [
                discountsAndUnitsAggregation,
                discountsAndVolumeAggregation,
            ]:
                volumeVariance, priceVariance = (
                    volumeVarianceOnNetSales,
                    priceVarianceOnNetSales,
                )
            else:
                volumeVariance, priceVariance = (
                    volumeVarianceOnMargin,
                    priceVarianceOnMargin,
                )
            df = calculate_unit_cost(df, paramDict, chartDict)
            df = calculate_price_variance_with_unit_cost(df, priceVariance, paramDict)
            df = calculate_volume_variance_with_unit_cost(df, volumeVariance, paramDict)
            df = calculate_cost_variance_with_unit_cost(df, paramDict, chartDict)
            if chartDict[varianceInPercent] != metConditionValue:
                df = delete_useless_columns_after_unit_cost(df, paramDict)
    else:
        df = _assign_column(df, baseVarianceUnits, pl.col(totalVariance))
        df = _assign_column(df, volumeVariance, 0)
    df = fill_null_zero(df, baseVarianceUnits)
    return df, paramDict


def calculate_price_variance_with_unit_cost(df, priceVariance, paramDict):
    """
    we need to calculate the price variance with the simplified allocation formula
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    separatorString = namingParams["separatorString"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    workColumn = namingParams["workColumn"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    df = _assign_column(
        df,
        workColumn,
        pl.col(unitsPeriodZero) + (pl.col(unitsChange) / 2),
    )
    df = _assign_column(df, priceVariance, pl.col(priceChange) * pl.col(workColumn))
    toDrop = [workColumn]
    df = drop_columns(df, toDrop)
    return df


def calculate_volume_variance_with_unit_cost(df, volumeVariance, paramDict):
    """
    we need to calculate the volume variance with the simplified allocation formula
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    costPerUnitName = namingParams["costPerUnitName"]
    separatorString = namingParams["separatorString"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    costPerUnitChange = namingParams["costPerUnitChange"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    workColumnThree = namingParams["workColumnThree"]
    pricePeriodZero = pricePerUnitName + separatorString + periodsArray[0]
    costPerUnitPeriodZero = costPerUnitName + separatorString + periodsArray[0]
    df = _assign_column(
        df,
        workColumn,
        pl.col(pricePeriodZero) - pl.col(costPerUnitPeriodZero),
    )
    df = _assign_column(df, workColumnTwo, pl.col(priceChange) / 2)
    df = _assign_column(df, workColumnThree, -pl.col(costPerUnitChange) / 2)
    df = _assign_column(
        df,
        volumeVariance,
        pl.col(unitsChange)
        * (pl.col(workColumn) + pl.col(workColumnTwo) + pl.col(workColumnThree)),
    )
    toDrop = [workColumn, workColumnTwo, workColumnThree]
    df = drop_columns(df, toDrop)
    return df


def calculate_cost_variance_with_unit_cost(df, paramDict, chartDict):
    """
    we need to calculate the cost variance with the simplified allocation formula
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    discountName = namingParams["discountName"]
    separatorString = namingParams["separatorString"]
    costVariance = namingParams["costVariance"]
    discountVariance = namingParams["discountVariance"]
    costPerUnitChange = namingParams["costPerUnitChange"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    workColumn = namingParams["workColumn"]
    varianceAggregation = namingParams["varianceAggregation"]
    discountsAndUnitsAggregation = namingParams["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = namingParams["discountsAndVolumeAggregation"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    df = _assign_column(
        df,
        workColumn,
        pl.col(unitsPeriodZero) + (pl.col(unitsChange) / 2),
    )
    df = _assign_column(
        df, costVariance, -pl.col(costPerUnitChange) * pl.col(workColumn)
    )
    toDrop = [workColumn]
    df = drop_columns(df, toDrop)
    if varianceAggregation in chartDict and chartDict[varianceAggregation] in [
        discountsAndUnitsAggregation,
        discountsAndVolumeAggregation,
    ]:
        df = drop_columns(df, [discountName])
        df = df.rename({costVariance: discountVariance})
    return df


def calculate_unit_cost(df, paramDict, chartDict):
    """
    we need to calculate the unit cost based on which cost columns we have
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    cogsPerUnitName = namingParams["cogsPerUnitName"]
    discountPerUnitName = namingParams["discountPerUnitName"]
    costPerUnitName = namingParams["costPerUnitName"]
    isdiscountColFound = paramDict[namingParams["discountColFound"]]
    isCogsColFound = paramDict[namingParams["cogsColFound"]]
    separatorString = namingParams["separatorString"]
    costPerUnitChange = namingParams["costPerUnitChange"]
    varianceAggregation = namingParams["varianceAggregation"]
    discountsAndUnitsAggregation = namingParams["discountsAndUnitsAggregation"]
    discountsAndVolumeAggregation = namingParams["discountsAndVolumeAggregation"]
    costPerUnitPeriodZero = costPerUnitName + separatorString + periodsArray[0]
    costPerUnitPeriodOne = costPerUnitName + separatorString + periodsArray[1]
    discountPerUnitPeriodZero = discountPerUnitName + separatorString + periodsArray[0]
    discountPerUnitPeriodOne = discountPerUnitName + separatorString + periodsArray[1]
    cogsPerUnitPeriodZero = cogsPerUnitName + separatorString + periodsArray[0]
    cogsPerUnitPeriodOne = cogsPerUnitName + separatorString + periodsArray[1]
    if (
        isdiscountColFound
        and isCogsColFound
        and chartDict[varianceAggregation]
        not in [discountsAndUnitsAggregation, discountsAndVolumeAggregation]
    ):
        df = _assign_column(
            df,
            costPerUnitPeriodZero,
            pl.col(discountPerUnitPeriodZero) + pl.col(cogsPerUnitPeriodZero),
        )
        df = _assign_column(
            df,
            costPerUnitPeriodOne,
            pl.col(discountPerUnitPeriodOne) + pl.col(cogsPerUnitPeriodOne),
        )
    elif isdiscountColFound:
        df = _assign_column(
            df, costPerUnitPeriodZero, pl.col(discountPerUnitPeriodZero)
        )
        df = _assign_column(df, costPerUnitPeriodOne, pl.col(discountPerUnitPeriodOne))
    elif isCogsColFound:
        df = _assign_column(df, costPerUnitPeriodZero, pl.col(cogsPerUnitPeriodZero))
        df = _assign_column(df, costPerUnitPeriodOne, pl.col(cogsPerUnitPeriodOne))
    df = _assign_column(
        df,
        costPerUnitChange,
        pl.col(costPerUnitPeriodOne) - pl.col(costPerUnitPeriodZero),
    )
    toDrop = [
        discountPerUnitPeriodZero,
        cogsPerUnitPeriodZero,
        discountPerUnitPeriodOne,
        cogsPerUnitPeriodOne,
    ]
    df = drop_columns(df, toDrop)
    return df


def calculate_margin_rate(df, paramDict):
    """
    if choice is cogs/discount variance with allocation we calculate the margin rate
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    separatorString = namingParams["separatorString"]
    discountName = namingParams["discountName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    isdiscountColFound = paramDict[namingParams["discountColFound"]]
    isCogsColFound = paramDict[namingParams["cogsColFound"]]
    marginRate = namingParams["marginRate"]
    discountsCogsName = namingParams["discountsCogsName"]
    cogsName = namingParams["cogsName"]
    marginRateChange = namingParams["marginRateChange"]
    amountPeriodZero = amountName + separatorString + periodsArray[0]
    amountPeriodOne = amountName + separatorString + periodsArray[1]
    marginRatePeriodZero = marginRate + separatorString + periodsArray[0]
    marginRatePeriodOne = marginRate + separatorString + periodsArray[1]
    discountPeriodZero = discountName + separatorString + periodsArray[0]
    discountPeriodOne = discountName + separatorString + periodsArray[1]
    discountsCogsPeriodZero = discountsCogsName + separatorString + periodsArray[0]
    discountsCogsPeriodOne = discountsCogsName + separatorString + periodsArray[1]
    cogsPeriodZero = cogsName + separatorString + periodsArray[0]
    cogsPeriodOne = cogsName + separatorString + periodsArray[1]
    if isdiscountColFound and isCogsColFound:
        df = _assign_column(
            df,
            discountsCogsPeriodZero,
            pl.col(discountPeriodZero) + pl.col(cogsPeriodZero),
        )
        df = _assign_column(
            df,
            discountsCogsPeriodOne,
            pl.col(discountPeriodOne) + pl.col(cogsPeriodOne),
        )
    elif isdiscountColFound:
        df = _assign_column(df, discountsCogsPeriodZero, pl.col(discountPeriodZero))
        df = _assign_column(df, discountsCogsPeriodOne, pl.col(discountPeriodOne))
    else:
        df = _assign_column(df, discountsCogsPeriodZero, pl.col(cogsPeriodZero))
        df = _assign_column(df, discountsCogsPeriodOne, pl.col(cogsPeriodOne))
    df = _assign_column(df, marginRatePeriodZero, 0)
    df = _assign_column(df, marginRatePeriodOne, 0)
    df = _assign_where(
        df,
        pl.col(amountPeriodZero) != 0,
        marginRatePeriodZero,
        1 - (pl.col(discountsCogsPeriodZero) / pl.col(amountPeriodZero)),
    )
    df = _assign_where(
        df,
        pl.col(amountPeriodOne) != 0,
        marginRatePeriodOne,
        1 - (pl.col(discountsCogsPeriodOne) / pl.col(amountPeriodOne)),
    )
    df = _assign_column(
        df, marginRateChange, pl.col(marginRatePeriodOne) - pl.col(marginRatePeriodZero)
    )
    return df


def calculate_price_variance_with_margin_rate(df, paramDict):
    """
    if a driver column exits we calculate driver variance
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodsArray = configParams["periodsArray"]
    unitsName = namingParams["unitsName"]
    separatorString = namingParams["separatorString"]
    priceVariance = namingParams["priceVarianceOnMargin"]
    marginRateVariance = namingParams["marginRateVariance"]
    priceChange = namingParams["priceChange"]
    unitsChange = namingParams["unitsChange"]
    marginRateChange = namingParams["marginRateChange"]
    marginRate = namingParams["marginRate"]
    workColumn = namingParams["workColumn"]
    workColumnTwo = namingParams["workColumnTwo"]
    workColumnThree = namingParams["workColumnThree"]
    workColumnFour = namingParams["workColumnFour"]
    unitsPeriodZero = unitsName + separatorString + periodsArray[0]
    marginRatePeriodZero = marginRate + separatorString + periodsArray[0]
    df = _assign_column(
        df, workColumn, pl.col(unitsPeriodZero) * pl.col(marginRatePeriodZero)
    )
    df = _assign_column(
        df, workColumnTwo, (pl.col(unitsChange) * pl.col(marginRatePeriodZero)) / 2
    )
    df = _assign_column(
        df, workColumnThree, pl.col(marginRateChange) * pl.col(unitsPeriodZero) / 2
    )
    df = _assign_column(
        df, workColumnFour, pl.col(unitsChange) * pl.col(marginRateChange) / 3
    )
    df = _assign_column(
        df,
        priceVariance,
        pl.col(priceChange)
        * (
            pl.col(workColumn)
            + pl.col(workColumnTwo)
            + pl.col(workColumnThree)
            + pl.col(workColumnFour)
        ),
    )
    toDrop = [workColumn, workColumnTwo, workColumnThree, workColumnFour]
    df = drop_columns(df, toDrop)
    return df
