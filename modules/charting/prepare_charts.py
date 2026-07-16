import logging
import math
import re

import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_primitives import divide_by_value_prefix
from modules.charting.draw_charts_utils import get_polars_value_at_index
from modules.data.common_data_utils import check_value_column_exist
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    check_and_clean_columns,
    drop_columns,
)
from modules.utilities.utils import ensure_lazyframe, get_schema_and_column_names

try:  # pragma: no cover - fallback for tests that stub utils
    from modules.utilities.utils import get_row_count
except ImportError as e:  # pragma: no cover - minimal fallback
    try:
        from modules.utilities.ui_notifier import ui

        if hasattr(st, "write"):
            ui.write("get_row_count import error:", e)
    except Exception as e:  # pragma: no cover - UI not available
        logging.exception(e)
        st = None

    def get_row_count(df: pl.DataFrame | pl.LazyFrame) -> int:
        """Return the number of rows when ``utils.get_row_count`` is missing."""

        return (
            df.height
            if isinstance(df, pl.DataFrame)
            else df.select(pl.len()).collect().item()
        )


def map_resample_rule_to_polars(rule_str: str) -> str:
    """
    Convert the user's rule like '1ME' or '3ME' into Polars' group_by_dynamic 'every' param.
    You might parse the number and treat 'ME' as 'mo' if monthly.
    """
    # Simple approach: if rule_str ends with 'ME', treat it as monthly
    match = re.match(r"(\d+)ME", rule_str)
    if match:
        n = int(match.group(1))
        # e.g. '1ME' => '1mo'
        return f"{n}mo"
    # otherwise return as-is or adapt more cases (e.g. weekly, yearly, etc.)
    return rule_str


def perform_resample(
    df: pl.LazyFrame,
    time_col: str,
    group_by_cols: list[str],
    value_cols: list[str],
    rule_str: str,
    agg: str,
) -> pl.LazyFrame:
    """
    Perform a dynamic group_by for resampling in Polars lazy mode.
    - time_col is the datetime column to resample on
    - group_by_cols are additional columns to group by
    - rule_str is something like "1mo" for monthly
    - agg can be 'sum' or 'mean'
    """
    polars_rule = map_resample_rule_to_polars(rule_str)

    if agg == "sum":
        agg_exprs = [pl.col(v).sum().alias(v) for v in value_cols]
    else:  # default to mean
        agg_exprs = [pl.col(v).mean().alias(v) for v in value_cols]

    # group_by_dynamic aggregates produce _time by default (the start of the bin)
    # or you can label="right" for end of the bin.
    # Adjust closed/label as you see fit for "month-end" style data.
    df = df.group_by_dynamic(
        index_column=time_col,  # the datetime column
        every=polars_rule,
        closed="right",  # mimic "month-end" style
        group_by=group_by_cols,  # also group by these
        label="right",
    ).agg(agg_exprs)
    # Optionally rename _time back to your date column
    # (Polars sets it as _time by default, but that depends on Polars version)
    columns, schema = get_schema_and_column_names(df)
    if "_time" in columns:
        df = df.with_columns(pl.col("_time").alias(time_col)).drop(["_time"])
    return df


def add_totals_column(
    lf: pl.LazyFrame, indexCols: list[str]
) -> tuple[pl.LazyFrame, list[str]]:
    """
    We add a column that is the same string (totalName) for every row.
    Then ensure totalName is present at the start of indexCols.
    """
    namingParams = get_naming_params()
    totalName = namingParams["totalName"]

    # This creates/overwrites the `totalName` column with a constant string.
    lf = lf.with_columns(pl.lit(totalName).alias(totalName))

    # Insert totalName into indexCols if it's missing
    if totalName not in indexCols:
        indexCols.insert(0, totalName)

    return lf, indexCols


def resample_dates(
    df: pl.LazyFrame,
    xColumn: str,
    column: str,
    valueCols: list[str],
    chartDict: dict,
    agg: str,
    paramDict: dict,
) -> pl.LazyFrame:
    """
    Lazy Polars equivalent of the original ``resample_dates`` function.
    The input df is already a LazyFrame and we do not collect().
    """
    namingParams = get_naming_params()

    # All your naming variables:
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    timelineChart = namingParams["timelineChart"]
    chosenChartName = namingParams["chosenChart"]
    resampleDates = namingParams["resampleDates"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    motionChart = namingParams["motionChart"]
    areaChart = namingParams["areaChart"]
    acName = namingParams["acName"]
    countMetricsSumDict = namingParams["countMetricsSumDict"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]

    # Which chart is chosen?
    chosenChart = chartDict[chosenChartName]

    # Only do anything if xColumn == dateName
    if xColumn == dateName:
        group_byCols = [column]

        # If user wants to compare scenarios or periods, add periodName:
        if (
            compareScenariosOrPeriods in chartDict
            and chartDict[compareScenariosOrPeriods] == compareScenarios
        ):
            group_byCols.append(periodName)

        # Some chart types also require grouping by periodName:
        if chosenChart in [
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
        ]:
            if periodName not in group_byCols:
                group_byCols.append(periodName)

        # If there is a 'countMetricsSumDict', add the associated column:
        if (
            countMetricsSumDict in chartDict
            and len(chartDict[countMetricsSumDict]) > 0
            and chosenChart not in [motionChart]
        ):
            # for example: chartDict[countMetricsSumDict] might look like {"someKey":"countCol"}
            keyList = list(chartDict[countMetricsSumDict].keys())
            colKey = keyList[0]
            countColumn = chartDict[countMetricsSumDict][colKey]
            group_byCols.append(countColumn)

        # Deduplicate
        group_byCols = list(set(group_byCols))

        # Make sure the value cols exist
        valueCols = check_value_column_exist(df, valueCols)

        # Decide if we resample
        if (resampleDates in chartDict) and (chartDict[resampleDates] > 0):
            # Example: user says "2" => "2ME"
            rule = f"{chartDict[resampleDates]}ME"
            df = perform_resample(df, xColumn, group_byCols, valueCols, rule, agg)

        # Or if the chosenChart is in that list, do a default "1ME":
        elif chosenChart in [
            trendComparisonChart,
            multitierColumnChart,
            horizontalWaterfallChart,
        ]:
            rule = "1ME"
            df = perform_resample(df, xColumn, group_byCols, valueCols, rule, agg)

        # Filter if timeline or area chart with compare-scenarios
        if chosenChart in [timelineChart, areaChart]:
            if (
                compareScenariosOrPeriods in chartDict
                and chartDict[compareScenariosOrPeriods] == compareScenarios
            ):
                df = df.filter(pl.col(periodName) == acName)

    return df


def compute_group_sum(
    df: pl.LazyFrame, group_col: str, metric_col: str, sum_col: str
) -> pl.LazyFrame:
    """
    Create a new column with the group-wise sum of `metric_col`.
    """
    return df.with_columns(pl.col(metric_col).sum().over(group_col).alias(sum_col))


def compute_difference(
    df: pl.LazyFrame, sum_col: str, difference_col: str, target: float = 100
) -> pl.LazyFrame:
    """
    Create a new column with (target - group_sum).
    """
    return df.with_columns((pl.lit(target) - pl.col(sum_col)).alias(difference_col))


def compute_rank(
    df: pl.LazyFrame, group_col: str, metric_col: str, rank_col: str
) -> pl.LazyFrame:
    """
    Create a new column that ranks rows within each group by `metric_col` descending.
    Using `method="ordinal"` will assign distinct ranks per tie in their order of appearance.
    """
    return df.with_columns(
        pl.col(metric_col)
        .rank(
            method="ordinal", descending=True
        )  # 'ordinal' best matches the previous rank(method="first") behavior
        .over(group_col)
        .alias(rank_col)
    )


def adjust_metric(
    df: pl.LazyFrame, metric_col: str, difference_col: str, rank_col: str
) -> pl.LazyFrame:
    """
    For rows with rank == 1 and a non-zero difference, adjust the metric_col by the difference_col.
    """
    return df.with_columns(
        pl.when((pl.col(rank_col) == 1) & (pl.col(difference_col) != 0))
        .then(pl.col(metric_col) + pl.col(difference_col))
        .otherwise(pl.col(metric_col))
        .alias(metric_col)
    )


def adjust_metric_vectorized(
    df: pl.LazyFrame, group_col: str, metric_col: str, target: float = 100
) -> pl.LazyFrame:
    """
    Polars-Lazy equivalent of the original ``adjust_metric_vectorized`` function.

    1) Calculates group-wise sums of `metric_col`.
    2) Computes the difference from `target`.
    3) Ranks each group by descending `metric_col` (ties broken by first occurrence).
    4) Adjusts only the top-ranked rows where difference != 0.
    5) Drops intermediate columns.
    6) Returns a lazy frame (no .collect() is called).
    """
    # Example usage of your naming-params function (if desired)
    # Otherwise, just use string literals directly
    # sum_metric_col, difference_col, rank_col = get_naming_params(...)
    sum_metric_col = "sum_metric"
    difference_col = "difference"
    rank_col = "ranks"

    df = (
        df.pipe(compute_group_sum, group_col, metric_col, sum_metric_col)
        .pipe(compute_difference, sum_metric_col, difference_col, target)
        .pipe(compute_rank, group_col, metric_col, rank_col)
        .pipe(adjust_metric, metric_col, difference_col, rank_col)
        # Optionally drop the intermediate columns
        .drop([sum_metric_col, difference_col, rank_col])
    )
    return df

    # -------------------------------------------------------------
    # Decide how to build dfTotals (the total sums) based on chartDict logic
    # -------------------------------------------------------------


def build_df_totals() -> pl.LazyFrame:
    """
    Build the totals DF for the relevant grouping, as a lazy frame.
    Mirrors the original logic using Polars.
    """
    # Decide which df to use
    if (likeForLike in paramDict and paramDict[likeForLike]) and (
        chartDict[plotValuesAsChoice] in [percentOfTotalDataset, percentOfTotalFiltered]
    ):
        dfTotals = df  # same as df
    elif (
        filterName in dfDict and chartDict[plotValuesAsChoice] == percentOfTotalFiltered
    ):
        dfTotals = dfDict[filterName]  # from your dictionaries
    elif chartDict[datasetChoice] == periodName and chartDict[plotValuesAsChoice] in [
        percentOfTotalDataset,
        percentOfTotalFiltered,
    ]:
        dfTotals = dfDict[dfAllPeriodsName]
    elif chartDict[datasetChoice] == periodName:
        dfTotals = dfDict[dfPeriodsName]
    elif chartDict[datasetChoice] == dateName:
        dfTotals = dfDict[dfDatesName]
    else:
        # Fallback to empty lazyframe if no condition matches
        dfTotals = pl.LazyFrame()
    dfTotals = dfTotals.lazy()
    # Ensure columns exist
    val_cols_valid = check_value_column_exist(dfTotals, valueCols)

    # group_by-sum in polars lazy
    dfTotals = dfTotals.group_by(group_byCols).agg(
        [pl.col(vc).sum().alias(vc) for vc in val_cols_valid]  # or pl.sum(vc).alias(vc)
    )

    # If column != totalName, try to handle countMetrics (like in your code)
    if column != totalName:
        countMetricValueArray = []

        if (countMetricsSumArrayKey in chartDict) and (
            len(chartDict[countMetricsSumArrayKey]) > 0
        ):
            columnsDf, schema = get_schema_and_column_names(df)  # placeholders
            # We might just get columns from dfTotals as well
            # but in lazy form, you can store them or do dfTotals.describe_plan() etc.
            columns, schema = get_schema_and_column_names(dfTotals)
            for countMetric in chartDict[countMetricsSumArrayKey]:
                if countMetric in columnsDf:  # simplistic check
                    # Only append if not in dfTotals columns
                    if countMetric not in columns:
                        countMetricValueArray.append(countMetric)

            if len(countMetricValueArray) > 0:
                # Summation for these "count metrics"
                countMetricValueArray = check_value_column_exist(
                    df, countMetricValueArray
                )
                dfCountMetrics = df.group_by(group_byCols).agg(
                    [pl.sum(pl.col(cm)).alias(cm) for cm in countMetricValueArray]
                )

                # Join them in
                dfTotals = dfTotals.join(dfCountMetrics, on=group_byCols, how="left")

    # If `column` is not empty, do the resample logic
    if column:
        # Add a 'totalName' column to mimic your code
        dfTotals = dfTotals.with_columns([pl.lit(totalName).alias(totalName)])
        dfTotals = resample_dates(
            dfTotals, xColumn, totalName, valueCols, chartDict, agg, paramDict
        )
        # Then drop the 'totalName' column after resampling
        dfTotals = drop_columns(dfTotals, [totalName])

    return dfTotals


def compute_share_of_total(
    df: pl.LazyFrame,
    xColumn: str,
    column: str,
    valueCols: list,
    chartDict: dict,
    dfDict: dict,
    agg,
    paramDict: dict,
) -> pl.LazyFrame:
    """
    Transforms absolute values into % of total, using Polars Lazy operations.
    `df` is assumed to be a lazy frame already.
    """
    namingParams = get_naming_params()

    # Extract the naming parameters to local variables for readability
    percentOfTotalDataset = namingParams["percentOfTotalDataset"]
    percentOfTotalFiltered = namingParams["percentOfTotalFiltered"]
    percentOfResultRow = namingParams["percentOfResultRow"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]

    dfPeriodsName = namingParams["dfPeriodsName"]
    dfAllPeriodsName = namingParams["dfAllPeriodsName"]
    dfDatesName = namingParams["dfDatesName"]

    datasetChoice = namingParams["datasetChoice"]
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    filterName = namingParams["filterName"]

    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]

    acpyName = namingParams["acpyName"]
    totalName = namingParams["totalName"]
    countMetricsSumArrayKey = namingParams["countMetricsSumArray"]
    likeForLike = namingParams["likeForLikeName"]
    columnTotalKey = namingParams["columnTotal"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    chosenChart = chartDict[namingParams["chosenChart"]]

    # Prepare group_by columns
    group_byCols = [xColumn]
    if chosenChart in [trendComparisonByPeriodChart]:
        group_byCols.append(acpyName)

    dfTotals = None  # by default

    # Decide which kinds of chart options require building a dfTotals
    if chartDict[plotValuesAsChoice] in [percentOfTotalDataset, percentOfTotalFiltered]:
        dfTotals = build_df_totals()
        # Adjust valueCols in case they changed
        valueCols = check_value_column_exist(dfTotals, valueCols)

    elif chartDict[plotValuesAsChoice] in [percentOfResultRow]:
        # Just group from `df` itself
        valueCols = check_value_column_exist(df, valueCols)
        dfTotals = df.group_by(group_byCols).agg(
            [pl.sum(pl.col(vc)).alias(vc) for vc in valueCols]
        )

    # -------------------------------------------------------------
    # Merge dfTotals back to df and compute percentages
    # -------------------------------------------------------------
    if dfTotals is not None and chartDict[plotValuesAsChoice] in [
        percentOfResultRow,
        percentOfTotalDataset,
        percentOfTotalFiltered,
    ]:
        # We rename each relevant column in dfTotals to "<col>_totals"
        renameDict = {v: f"{v}_totals" for v in valueCols}
        toDrop = list(renameDict.values())  # columns to drop after % calculations

        # Apply rename in dfTotals
        dfTotals = dfTotals.rename(renameDict)

        # Left join on group_byCols
        df = df.join(dfTotals, on=group_byCols, how="left")

        # Compute new percentages and round them
        # Because we have multiple valueCols, we do it in a loop
        updated_exprs = []
        for orig_col in valueCols:
            totals_col = f"{orig_col}_totals"
            updated_exprs.append(
                ((pl.col(orig_col) / pl.col(totals_col) * 100).round(0).alias(orig_col))
            )

        # Add the updated columns in a single pass
        df = df.with_columns(updated_exprs)

        # Additional stacking logic if stackedColumnChart
        if (
            chosenChart in [stackedColumnChart]
            and (columnTotalKey not in chartDict)
            and len(chartDict[selectDimensionsToPlot]) <= 2
        ):
            # We might apply the same loop or a dedicated function. Example:
            for orig_col in valueCols:
                df = adjust_metric_vectorized(
                    df, group_col=periodName, metric_col=orig_col, target=100
                )

        # Finally drop the *_totals columns
        df = drop_columns(df, toDrop)

    # Return the final lazy dataframe
    return df


def resize_bars_and_recalculate_differences(
    df: pl.DataFrame | pl.LazyFrame, metric: str
) -> pl.LazyFrame:
    """Resize bars and compute difference/colour columns using Polars.

    The function always returns a lazy frame irrespective of the input type.
    """

    namingParams = get_naming_params()
    differenceInValue = namingParams["differenceInValue"]
    differenceInPercent = namingParams["differenceInPercent"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    plName = namingParams["plName"]
    workColumn = namingParams["workColumn"]
    colorName = namingParams["colorName"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]

    reverse_metrics = {discountName, indirectCostsName, cogsName}

    lf = ensure_lazyframe(df)

    lf = lf.with_columns(pl.col(acName).round(0).alias(workColumn))
    lf = lf.with_columns((pl.col(acName) + pl.col(fcName)).alias(acName))

    lf = lf.with_columns(
        [
            (pl.col(acName) - pl.col(plName)).alias(differenceInValue),
            ((pl.col(acName) - pl.col(plName)) / pl.col(acName) * 100)
            .round(0)
            .alias(differenceInPercent),
        ]
    )

    if metric not in reverse_metrics:
        colour_expr = pl.when(pl.col(acName) > pl.col(plName)).then(0).otherwise(1)
    else:
        colour_expr = pl.when(pl.col(acName) > pl.col(plName)).then(1).otherwise(0)

    lf = lf.with_columns(colour_expr.alias(colorName))

    return lf


def prepare_dataframe_for_forecast(
    df: pl.DataFrame | pl.LazyFrame,
) -> pl.LazyFrame:
    """Adjust forecast columns so they match the actuals format.

    Always returns a :class:`polars.LazyFrame`.
    """

    namingParams = get_naming_params()
    workColumnTwo = namingParams["workColumnTwo"]
    workColumn = namingParams["workColumn"]
    acName = namingParams["acName"]
    fcName = namingParams["fcName"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]

    lf = ensure_lazyframe(df)

    lf = lf.with_columns(pl.col(fcName).alias(workColumnTwo))
    lf = lf.with_columns(pl.col(acName).alias(fcName))
    lf = lf.with_columns((pl.col(acName) - pl.col(workColumnTwo)).alias(acName))
    lf = lf.with_columns(pl.col(fcName).alias(workColumn))

    return lf


def check_if_key_in_dict(firstKey, secondKey, dictionary):
    if firstKey in dictionary:
        key = firstKey
    else:
        key = secondKey
    return key


def group_by_dataset_for_stacked_bar(
    dfCopy, column, smallMultiplesColumnArray, valueCols, chartDict
):
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    totalName = namingParams["totalName"]
    periodName = namingParams["periodName"]
    smallMultiplesDimension = chartDict[smallMultiplesColumn]
    verticalDimension = chartDict[xAxisDimension]
    horizontalDimension = chartDict[yAxisDimension]
    group_byCols = smallMultiplesColumnArray + [periodName]
    if (
        horizontalDimension not in [nothingFilteredName, False, notMetConditionValue]
        and horizontalDimension not in group_byCols
    ):
        group_byCols = smallMultiplesColumnArray + [periodName, horizontalDimension]
    if (
        column != smallMultiplesDimension
        and smallMultiplesDimension != horizontalDimension
        and smallMultiplesDimension in group_byCols
    ):
        group_byCols.remove(smallMultiplesDimension)
    if column == smallMultiplesDimension and totalName in group_byCols:
        group_byCols.remove(totalName)
    if verticalDimension:
        if verticalDimension not in group_byCols:
            group_byCols.append(verticalDimension)
    if horizontalDimension != nothingFilteredName:
        if horizontalDimension not in group_byCols:
            group_byCols.append(horizontalDimension)

    lf = ensure_lazyframe(dfCopy)
    group_byCols, valueCols = check_and_clean_columns(lf, group_byCols, valueCols)
    lf = lf.group_by(group_byCols).agg([pl.col(col).sum() for col in valueCols])
    return lf, group_byCols


def group_by_dataset_for_bubble_plot(
    dfCopy, column, smallMultiplesColumnArray, xColumn, valueCols, chartDict
) -> tuple[pl.LazyFrame, list[str]]:
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    totalName = namingParams["totalName"]
    dotDimension = chartDict[xAxisDimension]
    colorDimension = chartDict[yAxisDimension]
    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    group_byCols = smallMultiplesColumnArray + [xColumn]
    if column == totalName:
        if (
            colorDimension not in [nothingFilteredName, False, notMetConditionValue]
            and colorDimension not in group_byCols
        ):
            group_byCols = [xColumn, dotDimension]
        elif (
            colorDimension not in [nothingFilteredName, False, notMetConditionValue]
            and colorDimension in group_byCols
        ):
            group_byCols = [xColumn, dotDimension]
        elif colorDimension in [nothingFilteredName, False, notMetConditionValue]:
            group_byCols = [xColumn, dotDimension]
        else:
            group_byCols = [xColumn, dotDimension]
    else:
        if (
            colorDimension not in [nothingFilteredName, False, notMetConditionValue]
            and colorDimension not in group_byCols
        ):
            group_byCols = [xColumn, dotDimension]
        elif (
            colorDimension not in [nothingFilteredName, False, notMetConditionValue]
            and colorDimension in group_byCols
        ):
            group_byCols = [xColumn, dotDimension]
        elif colorDimension in [nothingFilteredName, False, notMetConditionValue]:
            group_byCols = [xColumn, dotDimension]
        else:
            group_byCols = [xColumn, dotDimension]
        for element in [smallMultiplesColumn, colorDimension]:
            if element not in [nothingFilteredName, None, notMetConditionValue]:
                if element not in group_byCols:
                    group_byCols.append(element)
    group_byCols = list(set(group_byCols))
    lf = ensure_lazyframe(dfCopy)
    valueCols = check_value_column_exist(lf, valueCols)
    lf = lf.group_by(group_byCols).agg([pl.col(col).sum() for col in valueCols])
    return lf, group_byCols


def prepare_dataframe_for_total_bubble_colored(
    df: pl.DataFrame | pl.LazyFrame,
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    chosenDimension: str,
    bubbleColorDimension: str,
) -> pl.DataFrame | pl.LazyFrame:
    """Return ``df`` joined with bubble color information.

    The result is a :class:`LazyFrame` when color information is added, so
    callers can choose when to collect.
    """

    namingParams = get_naming_params()
    otherName = namingParams["otherName"]
    nothingFilteredName = namingParams["nothingFilteredName"]

    joinCols = [chosenDimension]
    dfColumns, _ = get_schema_and_column_names(df)
    dfCopyColumns, _ = get_schema_and_column_names(dfCopy)

    if chosenDimension != bubbleColorDimension:
        if (
            chosenDimension in dfColumns
            and bubbleColorDimension in dfColumns
            and chosenDimension in dfCopyColumns
            and bubbleColorDimension in dfCopyColumns
        ):
            joinCols = [chosenDimension, bubbleColorDimension]

    if bubbleColorDimension != nothingFilteredName:
        colorCols = list({chosenDimension, bubbleColorDimension})
        lf = ensure_lazyframe(df)
        lf_copy = ensure_lazyframe(dfCopy)

        dfColor = lf_copy.select(colorCols).unique(subset=colorCols, keep="first")

        lf = lf.join(dfColor, on=joinCols, how="left").with_columns(
            pl.col(bubbleColorDimension).fill_null(otherName)
        )

        # Return a LazyFrame so the caller can decide when to collect
        return lf

    return df


def group_by_dataset_for_scatter_plot(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    column: str,
    smallMultiplesColumnArray: list[str],
    xColumn: str,
    valueCols: list[str],
    chartDict: dict,
) -> tuple[pl.LazyFrame, list[str]]:
    """Return grouped dataset for scatter plots as a ``LazyFrame``.

    Parameters
    ----------
    dfCopy:
        Input data to group.
    column:
        Currently selected small multiples column.
    smallMultiplesColumnArray:
        Available small multiple columns.
    xColumn:
        Name of the x-axis column.
    valueCols:
        Value columns to aggregate when dots are present.
    chartDict:
        Chart configuration dictionary mapping naming parameters to columns.

    Returns
    -------
    tuple[pl.LazyFrame, list[str]]
        The grouped lazy data and the list of group-by columns.
    """
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    dotDimension = chartDict[xAxisDimension]
    colorDimension = chartDict[yAxisDimension]
    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    group_byCols = smallMultiplesColumnArray + [xColumn]
    if (
        colorDimension not in [nothingFilteredName, False, notMetConditionValue]
        and colorDimension not in group_byCols
    ):
        group_byCols = smallMultiplesColumnArray + [xColumn, colorDimension]
    if (
        column != smallMultiplesColumn
        and smallMultiplesColumn != colorDimension
        and smallMultiplesColumn in group_byCols
    ):
        group_byCols.remove(smallMultiplesColumn)
    if dotDimension == nothingFilteredName and colorDimension:
        if colorDimension not in group_byCols:
            group_byCols.append(colorDimension)
    if dotDimension != nothingFilteredName:
        if dotDimension not in group_byCols:
            group_byCols.append(dotDimension)

    group_byCols, valueCols = check_and_clean_columns(dfCopy, group_byCols, valueCols)

    lf = ensure_lazyframe(dfCopy)

    if dotDimension != nothingFilteredName:
        lf = lf.group_by(group_byCols).agg([pl.col(col).sum() for col in valueCols])
    else:
        lf = lf.select(group_byCols + valueCols)

    # Ensure a LazyFrame is always returned
    lf = lf.lazy() if isinstance(lf, pl.DataFrame) else lf

    return lf, group_byCols


def group_by_dataset_for_marimekko_and_barmekko(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    column: str,
    smallMultiplesColumnArray: list[str],
    valueCols: list[str],
    chartDict: dict,
) -> pl.LazyFrame:
    """Return grouped data for marimekko/barmekko charts.

    Parameters
    ----------
    dfCopy:
        Input dataset as either a :class:`DataFrame` or :class:`LazyFrame`.
    column:
        Current small multiples column being iterated.
    smallMultiplesColumnArray:
        List of available small-multiple columns.
    valueCols:
        Metric columns that will be aggregated with ``sum``.
    chartDict:
        Chart configuration mapping naming parameters to columns.

    Returns
    -------
    pl.LazyFrame
        The grouped lazy dataset.
    """

    lf = ensure_lazyframe(dfCopy)

    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    totalName = namingParams["totalName"]
    periodName = namingParams["periodName"]
    smallMultiplesDimension = chartDict[smallMultiplesColumn]
    verticalDimension = chartDict[xAxisDimension]
    horizontalDimension = chartDict[yAxisDimension]
    group_byCols = smallMultiplesColumnArray + [periodName]
    if (
        horizontalDimension not in [nothingFilteredName, False, notMetConditionValue]
        and horizontalDimension not in group_byCols
    ):
        group_byCols = smallMultiplesColumnArray + [periodName, horizontalDimension]
    if (
        column != smallMultiplesDimension
        and smallMultiplesDimension != horizontalDimension
        and smallMultiplesDimension in group_byCols
    ):
        group_byCols.remove(smallMultiplesDimension)
    if column == smallMultiplesDimension and totalName in group_byCols:
        group_byCols.remove(totalName)
    if verticalDimension:
        if verticalDimension not in group_byCols:
            group_byCols.append(verticalDimension)
    if horizontalDimension != nothingFilteredName:
        if horizontalDimension not in group_byCols:
            group_byCols.append(horizontalDimension)

    group_byCols, valueCols = check_and_clean_columns(lf, group_byCols, valueCols)

    lf = lf.select(group_byCols + valueCols)

    agg_exprs = [pl.col(col).sum().alias(col) for col in valueCols]
    return lf.group_by(group_byCols).agg(agg_exprs)


def add_total_variance_arrow_vertical(
    df: pl.DataFrame | pl.LazyFrame,
    fig,
    paramDict,
    chartDict,
    colorDict,
    run,
) -> any:
    """Add the red or green arrow total variance annotation.

    Parameters
    ----------
    df:
        Input data as either a :class:`polars.DataFrame` or :class:`polars.LazyFrame`.
        The dataframe remains lazy until small slices are collected for arrow
        calculations.
    """
    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    drilldownReportRunName = namingParams["drilldownReportRunName"]
    firstBarColor, lineWidth, lineColor = (
        colorDict["whiteColor"],
        0.5,
        colorDict["lightGreyColor"],
    )
    df_lazy = ensure_lazyframe(df)
    periodZeroValue = get_polars_value_at_index(df_lazy, varianceAmountName, 0)
    periodOneValue = get_polars_value_at_index(df_lazy, varianceAmountName, -1)
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    varianceAggregation = namingParams["varianceAggregation"]
    deltaName = namingParams["deltaName"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    initialAndFinalValuesCanBeShown = True
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
    if (
        showInitialAndFinalValues in chartDict
        and chartDict[showInitialAndFinalValues]
        and initialAndFinalValuesCanBeShown
    ):
        if periodOneValue >= periodZeroValue:
            arrowColor = colorDict["greenColor"]
        else:
            arrowColor = colorDict["redColor"]
        y1 = -0.015
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=lineWidth,
            line_color=lineColor,
            y0=y1,
            y1=0.95,
            yref="paper",
            x0=periodZeroValue,
            x1=periodZeroValue,
            xref="x",
            layer="below",
        )
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=lineWidth,
            line_color=lineColor,
            y0=y1,
            y1=0.1,
            yref="paper",
            x0=periodOneValue,
            x1=periodOneValue,
            xref="x",
        )
        y1 = -0.015
        fig.add_shape(
            type="line",
            opacity=1,
            line_width=2,
            line_color=arrowColor,
            y1=y1,
            y0=y1,
            yref="paper",
            x1=periodZeroValue,
            x0=periodOneValue,
            xref="x",
        )
        fig.add_annotation(
            showarrow=True,
            arrowcolor=arrowColor,
            arrowhead=5,
            arrowsize=1,
            ay=y1,
            y=y1,
            yref="paper",
            ax=periodZeroValue,
            x=periodOneValue,
            xref="x",
            axref="x",
        )
        if periodZeroValue != 0:
            percentChange = ((periodOneValue - periodZeroValue) / periodZeroValue) * 100
            difference = periodOneValue - periodZeroValue
            difference = divide_by_value_prefix(difference, chartDict, False)
            difference = deltaName + " " + str(difference)
            if not math.isnan(percentChange):
                percentChange = "<i>(" + str(int(round(percentChange, 0))) + "%)</i>"
            else:
                percentChange = ""
            changevalue = difference + " " + percentChange
        else:
            periodZeroValue = deltaName + " nan"
            percentChange = ""
            changevalue = periodOneValue
        fig.add_annotation(
            showarrow=False,
            text=changevalue,
            align="center",
            xshift=-32,
            yshift=-7,
            ay=-0.06,
            y=-0.06,
            yref="paper",
            ax=periodZeroValue,
            x=periodOneValue,
            xref="x",
            axref="x",
        )
    return fig


def make_smaller_sampled_dataframe(
    df: pl.DataFrame | pl.LazyFrame, chart: str
) -> tuple[pl.DataFrame | pl.LazyFrame, str]:
    """Sample the dataframe if it exceeds a configured size."""

    configParams = get_config_params()
    maxDataSetSizeDict = configParams["maxDataSetSizeDict"]
    sampleSizeDict = configParams["sampleSizeDict"]
    maxDataSetSize = maxDataSetSizeDict[chart]
    sampleSize = sampleSizeDict[chart]
    fileSize = get_row_count(df)
    message = ""
    if fileSize > maxDataSetSize:
        if isinstance(df, pl.DataFrame):
            df = df.sample(sampleSize)
        else:
            df = df.collect().sample(sampleSize).lazy()
        newFileSize = get_row_count(df)
        message = (
            f"Dataset sampled from  **{fileSize}** down to the **{newFileSize}** "
            "rows max limit to preserve performance."
        )
    return df, message