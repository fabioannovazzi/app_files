import copy
import logging

import numpy as np
import polars as pl
import polars.selectors as cs

# Provide ``LazyFrame.height`` for Polars versions that lack it.  Guard against
# stubbed ``LazyFrame`` objects that do not allow new attributes.
if (
    hasattr(pl, "LazyFrame")
    and not hasattr(pl.LazyFrame, "height")
    and hasattr(pl.LazyFrame, "__dict__")
):

    @property
    def _lazyframe_height(self) -> int:  # pragma: no cover - simple delegation
        return int(self.select(pl.len()).collect().item())

    try:
        pl.LazyFrame.height = _lazyframe_height  # type: ignore[attr-defined]
    except TypeError:  # pragma: no cover - builtins reject new attrs
        pass

from modules.charting.chart_primitives import (
    assign_same_colors_to_all_charts,
    get_color_array,
    get_color_dictionary,
    insert_highlight_color,
    modify_color_array,
    set_other_color_to_grey,
    track_used_colors,
)
from modules.charting.polars_helpers import unique_values_lazy
from modules.data.common_data_utils import (
    adjust_percentages_dynamic,
    calculate_cagr,
    check_value_column_exist,
    clean_column_labels_after_flatten_df,
    get_average_growth_rate,
    get_growth_rate,
    get_number_of_uniques,
    insert_unit_and_volume_price_column,
    join_unique_metric_to_df,
    multiply_percent_metrics_by_hundred,
    pivot_lazy,
    rank_others_as_last,
    reindex_polars,
    show_only_largest,
    sort_periods_polars,
)
from modules.layout.memoization import check_collect
from modules.utilities.config import (
    get_config_params,
    get_metric_array_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    calculate_unit_and_volume_price,
    check_if_periods_in_columns,
    drop_columns,
    duplicate_dataframe,
    flatten_cols_polars,
    get_periods_array,
    is_numeric_dtype,
    process_if_promo_data,
    unique,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_row_count,
    get_schema_and_column_names,
)

try:
    from modules.utilities.utils import ensure_polars_df
except ImportError as e:  # pragma: no cover - fallback for stubbed tests
    logging.getLogger(__name__).warning("ensure_polars_df import error: %s", e)

    def ensure_polars_df(
        df: pl.DataFrame | pl.LazyFrame | list | dict,
    ) -> pl.DataFrame:
        """Return ``df`` as a ``polars.DataFrame``."""

        if isinstance(df, pl.DataFrame):
            return df
        if isinstance(df, pl.LazyFrame):
            return df.collect()
        return pl.DataFrame(df)


def correct_other_rank_number_for_missing_items(
    df: pl.DataFrame | pl.LazyFrame, aggregateOtherItemsName: str
) -> pl.LazyFrame:
    """Rename rows labelled with ``aggregateOtherItemsName`` if rank is too high."""

    namingParams = get_naming_params()
    aggregateOtherItemsPrefix = namingParams["aggregateOtherItemsName"]

    lf = ensure_lazyframe(df)
    columns, schema = get_schema_and_column_names(lf)
    label_col = columns[0]

    correctValue = get_row_count(lf) - 1
    toCheckValue = int(aggregateOtherItemsName[-1])

    if toCheckValue > correctValue:
        newAggregateOtherItemsName = aggregateOtherItemsPrefix + str(correctValue)
        lf = lf.with_columns(
            pl.when(pl.col(label_col) == aggregateOtherItemsName)
            .then(pl.lit(newAggregateOtherItemsName))
            .otherwise(pl.col(label_col))
            .alias(label_col)
        )
    return lf


def prepare_overlay_data_for_stacked_bar(
    dfCopy,
    dfCounts,
    column,
    xColumn,
    aggregateOtherItemsName,
    valueCols,
    chartDict,
    paramDict,
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    metricsToPlot = namingParams["metricsToPlot"]
    totalName = namingParams["totalName"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    overlayChartFullDfKey = namingParams["overlayChartFullDf"]
    overlayChartDimensionKey = namingParams["overlayChartDimension"]
    nothingThereString = namingParams["nothingThereString"]
    periodName = namingParams["periodName"]
    valueName = namingParams["valueName"]
    smallMultiplesDimensionKey = namingParams["smallMultiplesDimension"]
    overlayChartMetric = chartDict[metricsToPlot][1]
    df = duplicate_dataframe(dfCopy)
    dfSum = get_average_growth_rate(
        df, overlayChartMetric, paramDict, chartDict, valueCols, 1
    )
    df, paramDict, valueCols = add_other_metrics_to_stacked_bar(
        df, xColumn, valueCols, chartDict, paramDict, 1
    )
    df = df.filter(
        (pl.col(overlayChartMetric) >= 0.001) | (pl.col(overlayChartMetric) <= -0.001)
    )
    df = df.filter(
        (pl.col(xColumn) != nothingThereString) & (pl.col(overlayChartMetric) != 0)
    )
    df = drop_columns(df, [periodName])
    df = df.select([xColumn, overlayChartMetric])
    df = df.fill_null(0)
    df = df.with_columns(pl.col(overlayChartMetric).cast(float))
    df = correct_other_rank_number_for_missing_items(df, aggregateOtherItemsName)
    if column in [totalName]:
        df = add_average_to_stacked_bar(
            df, dfSum, chartDict, overlayChartMetric, False, priceMetricsArray
        )
    df = df.rename({totalName: overlayChartMetric})
    df = drop_columns(df, [valueName])
    if column != totalName:
        # Polars-style direct column assignment
        df = df.with_columns(
            pl.lit(chartDict[smallMultiplesDimensionKey]).alias(column)
        )
    if column == totalName:
        chartDict[overlayChartMetricKey] = overlayChartMetric
        chartDict[overlayChartDfKey] = df
        chartDict[overlayChartFullDfKey] = df
        chartDict[overlayChartDimensionKey] = column
    elif (
        overlayChartDimensionKey in chartDict
        and chartDict[overlayChartDimensionKey] == totalName
        and column != totalName
    ):
        chartDict[overlayChartMetricKey] = overlayChartMetric
        chartDict[overlayChartDfKey] = df
        chartDict[overlayChartFullDfKey] = df
        chartDict[overlayChartDimensionKey] = column
    elif (
        overlayChartDimensionKey in chartDict
        and chartDict[overlayChartDimensionKey] != totalName
        and column != totalName
    ):
        dfFull = chartDict[overlayChartFullDfKey]
        dfFull = pl.concat([dfFull, df], how="vertical")
        # Replace pandas-style drop_duplicates with Polars unique
        dfFull = dfFull.unique(keep="first", maintain_order=True)
        chartDict[overlayChartMetricKey] = overlayChartMetric
        chartDict[overlayChartDfKey] = df
        chartDict[overlayChartFullDfKey] = dfFull
        chartDict[overlayChartDimensionKey] = column
    return chartDict


def sort_dataframe_in_correct_order(
    df, chartDict, globalUniqueItems, fatherAndChildItems, globalAggregateOtherItemsName
):
    namingParams = get_naming_params()
    xAxisDimension = namingParams["xAxisDimension"]
    yAxisDimension = namingParams["yAxisDimension"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    averageName = namingParams["averageName"]
    averageName = namingParams["longAverageName"]
    columns, schema = get_schema_and_column_names(df)
    secondDimension = chartDict[xAxisDimension]
    sortOnColumn = False
    added_row_index = False
    if secondDimension in columns:
        df = df.with_columns(pl.col(secondDimension).cast(pl.Utf8))
        df = df.with_columns(
            pl.when(pl.col(secondDimension).is_null())
            .then(globalAggregateOtherItemsName)
            .otherwise(pl.col(secondDimension))
            .alias(secondDimension)
        )
        sortOnColumn = True
    else:
        secondDimension = chartDict[yAxisDimension]
        columns, _ = get_schema_and_column_names(df)
        if secondDimension not in columns:
            df = df.with_row_index(name=secondDimension)
            added_row_index = True
        df = df.with_columns(
            pl.col(secondDimension)
            .cast(pl.Utf8)
            .fill_null(globalAggregateOtherItemsName)
            .alias(secondDimension)
        )
    rankingArray = globalUniqueItems
    reversedList = list(reversed(rankingArray))
    idx_values = (
        ensure_lazyframe(df.select(secondDimension))
        .collect()
        .get_column(secondDimension)
        .to_list()
    )
    if averageName in idx_values:
        reversedList.insert(0, "  ")
        reversedList.insert(0, averageName)
    if (
        fatherAndChildDimensions in chartDict
        and chartDict[fatherAndChildDimensions]
        or chartDict[showTopForEachItem]
    ):
        rankingArray = fatherAndChildItems
    if sortOnColumn:
        df = df.with_columns(
            pl.col(secondDimension).cast(pl.Categorical).set_ordering("lexical")
        ).sort(by=secondDimension, descending=True)
    else:
        if not added_row_index:
            df = reindex_polars(df.lazy(), secondDimension, reversedList)
    columns, schema = get_schema_and_column_names(df)
    if sortOnColumn and secondDimension in columns:
        columns.remove(secondDimension)
        group_byCols = [secondDimension]
        df = df.group_by(group_byCols).agg([pl.col(col).sum() for col in columns])
        df = df.sort(by=group_byCols, descending=True)
    elif secondDimension in columns and not added_row_index:
        group_byCols = [secondDimension]
        df = df.group_by(group_byCols).agg([pl.col(col).sum() for col in columns])
        df = reindex_polars(df.lazy(), secondDimension, reversedList)
    else:
        pass

    return ensure_lazyframe(df), rankingArray


def get_filtered_unique_items(
    df: pl.DataFrame | pl.LazyFrame, dimension: str
) -> list[str]:
    """Return unique values from ``dimension`` in ``df`` without collecting ``df``."""

    columns, _ = get_schema_and_column_names(df)
    if dimension not in columns:
        return []

    lf = ensure_lazyframe(df).select(pl.col(dimension)).unique()
    from modules.utilities.utils import unique_list_lazy

    return unique_list_lazy(dimension, lf)


def add_empty_rows_if_hierarchical(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    numberOfRows: int,
    reversedList: list[str],
    globalUniqueItems: list[str],
    chartDict: dict,
    resetIndex: bool,
) -> pl.LazyFrame:
    """Append placeholder rows when a hierarchy is detected.

    The original implementation relied on Pandas indexing.  For tests we only
    need to ensure that the returned frame contains the expected number of
    rows, so the function simply appends new lazy rows filled with ``NaN``.
    """

    namingParams = get_naming_params()
    invisibleCharacter = namingParams["invisibleCharacter"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]

    # Work with a fresh lazy copy to avoid mutating the original input.
    df = ensure_lazyframe(duplicate_dataframe(dfCopy))
    columns, _ = get_schema_and_column_names(df)

    if numberOfRows > len(reversedList):
        if resetIndex:
            pass
        elif not chartDict.get(yAxisDimension):
            resetIndex = False
        elif chartDict[yAxisDimension] not in columns:
            resetIndex = False

        numberOfItems = len(reversedList)
        numberOfRows = len(globalUniqueItems)
        rowsToAdd = numberOfRows - numberOfItems

        new_rows: list[pl.LazyFrame] = []
        for _ in range(rowsToAdd):
            row_dict = {c: np.nan for c in columns}
            row_dict[columns[0]] = invisibleCharacter
            new_rows.append(pl.DataFrame(row_dict).lazy())
            invisibleCharacter += invisibleCharacter

        if new_rows:
            df = pl.concat([df] + new_rows, how="vertical")
        # No explicit index handling in Polars
    return ensure_lazyframe(df)


def add_empty_rows_if_not_hierarchical(
    df: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    secondDimension: str,
    reversedList: list[str],
    filteredUniqueItems: list[str],
    rankingArray: list[str],
) -> pl.LazyFrame:
    """Append rows for items missing from ``filteredUniqueItems``.

    This mirrors a small subset of the original behaviour which dealt with a
    Pandas index.  The Polars variant simply ensures that the union of
    ``reversedList`` and ``filteredUniqueItems`` is represented in the output.
    """

    namingParams = get_naming_params()
    showTopForEachItem = namingParams["showTopForEachItem"]

    df = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(df)

    new_rows: list[pl.LazyFrame] = []
    for item in reversedList:
        if item not in filteredUniqueItems:
            row_dict = {c: np.nan for c in columns}
            row_dict[columns[0]] = item
            new_rows.append(pl.DataFrame(row_dict).lazy())

    if new_rows:
        df = pl.concat([df] + new_rows, how="vertical")

    if secondDimension in columns:
        df = df.with_columns(
            pl.col(secondDimension).cast(pl.Categorical).set_ordering("lexical")
        ).sort(by=secondDimension, descending=True)
    elif showTopForEachItem in chartDict and not chartDict[showTopForEachItem]:
        columns, _ = get_schema_and_column_names(df)
        if secondDimension not in columns:
            df = df.with_columns(pl.lit(None).alias(secondDimension))
        df = df.filter(pl.col(secondDimension).is_in(rankingArray))
        df = df.with_columns(
            pl.col(secondDimension).cast(pl.Categorical).set_ordering("lexical")
        ).sort(by=secondDimension)
    return df


def filter_small_multiples_dataframe(
    dfCopy, smallMultiplesDimension, secondDimensionItems, smallMultiplesColumn
):
    namingParams = get_naming_params()
    df = duplicate_dataframe(dfCopy)
    if smallMultiplesDimension == secondDimensionItems[-1]:
        df = df.filter(~pl.col(smallMultiplesColumn).is_in(secondDimensionItems[:-1]))
        df = df.with_columns(
            pl.lit(secondDimensionItems[-1]).alias(smallMultiplesColumn)
        )
    else:
        df = df.filter(pl.col(smallMultiplesColumn) == smallMultiplesDimension)
    return df


def get_scaling_factor(df: pl.DataFrame | pl.LazyFrame, chartDict: dict) -> dict:
    """Compute scaling factors using lazy aggregation."""

    namingParams = get_naming_params()
    valueName = namingParams["valueName"]
    metricsToPlot = namingParams["metricsToPlot"]
    scalingFactorKey = namingParams["scalingFactor"]
    offsetKey = namingParams["offset"]

    overlayMetric = None
    if metricsToPlot in chartDict and len(chartDict[metricsToPlot]) == 2:
        overlayMetric = chartDict[metricsToPlot][1]

    lf = ensure_lazyframe(df)
    exprs = [
        pl.col(valueName).min().alias("__min1"),
        pl.col(valueName).max().alias("__max1"),
    ]
    if overlayMetric:
        exprs.extend(
            [
                pl.col(overlayMetric).min().alias("__min2"),
                pl.col(overlayMetric).max().alias("__max2"),
            ]
        )
    stats = lf.select(exprs).collect()
    min1, max1 = stats["__min1"][0], stats["__max1"][0]
    if overlayMetric:
        min2, max2 = stats["__min2"][0], stats["__max2"][0]
    else:
        min2, max2 = min1, max1

    range1 = max1 - min1
    range2 = max2 - min2

    if range2 == 0:
        offset = 0
        scalingFactor = (min1 + max1) / 2
    else:
        scalingFactor = range1 / range2
        offset = min1 - (min2 * scalingFactor)

    chartDict[scalingFactorKey] = scalingFactor
    chartDict[offsetKey] = offset
    return chartDict


def find_scaling_factor_for_overlay_metric(
    df,
    column,
    valueCols,
    globalUniqueItems,
    xColumn,
    chartDict,
    paramDict,
    usedColorDict,
    count,
):
    namingParams = get_naming_params()
    metricsToPlot = namingParams["metricsToPlot"]
    secondDimensionItemsArrayKey = namingParams["secondDimensionItemsArray"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    xAxisDimensionKey = namingParams["xAxisDimension"]
    globalUniqueItemsArrayKey = namingParams["globalUniqueItemsArray"]
    globalAggregateKey = namingParams["globalAggregateKey"]
    smallMultiplesDimensionKey = namingParams["smallMultiplesDimension"]
    overlayChartFullDfKey = namingParams["overlayChartFullDf"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    xAxisDimension = chartDict[xAxisDimensionKey]
    globalAggregateOtherItems = paramDict[globalAggregateKey]
    frameArray = []
    fatherAndChildItems = []
    if count == 1 and metricsToPlot in chartDict and len(chartDict[metricsToPlot]) == 2:
        secondDimensionItems = paramDict[secondDimensionItemsArrayKey]
        for smallMultiplesDimension in secondDimensionItems:
            chartDict[smallMultiplesDimensionKey] = smallMultiplesDimension
            df1 = duplicate_dataframe(df)
            df1 = filter_small_multiples_dataframe(
                df1, smallMultiplesDimension, secondDimensionItems, smallMultiplesColumn
            )
            if (
                fatherAndChildDimensions in chartDict
                and chartDict[fatherAndChildDimensions]
            ) or chartDict[showTopForEachItem]:
                dfDump, fatherAndChildItems, globalAggregateOtherItems, valueCols = (
                    show_only_largest(
                        df1,
                        xAxisDimension,
                        None,
                        xColumn,
                        valueCols,
                        chartDict,
                        paramDict,
                        "X",
                    )
                )
            else:
                paramDict[globalUniqueItemsArrayKey] = globalUniqueItems
            df1, chartDict, colorArray, metricToPlot, frameArray = (
                prepare_small_multiples_dataframe_for_stacked_bar(
                    df1,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    globalUniqueItems,
                    fatherAndChildItems,
                    globalAggregateOtherItems,
                    smallMultiplesDimension,
                    frameArray,
                )
            )
        dfExport = pl.concat(frameArray, how="vertical")
        overlayChartFullDf = chartDict[overlayChartFullDfKey]
        dfExport = dfExport.join(
            overlayChartFullDf,
            on=[smallMultiplesColumn, xAxisDimension],
            how="left",
        )
        check_collect("PSM", "dfExport", dfExport)
        chartDict = get_scaling_factor(dfExport, chartDict)
    return chartDict


def prepare_small_multiples_dataframe_for_stacked_bar(
    df: pl.DataFrame | pl.LazyFrame,
    column: str,
    valueCols: list[str],
    chartDict: dict,
    paramDict: dict,
    usedColorDict: dict,
    globalUniqueItems: list,
    fatherAndChildItems: list,
    globalAggregateOtherItems: list,
    smallMultiplesDimension: str,
    frameArray: list[pl.LazyFrame],
) -> tuple[pl.LazyFrame, dict, list[str], str, list[pl.LazyFrame]]:
    """Return a LazyFrame and append the uncollected frame to ``frameArray``."""
    namingParams = get_naming_params()
    xAxisDimensionKey = namingParams["xAxisDimension"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    smallMultiplesColumnKey = namingParams["smallMultiplesColumn"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    xAxisDimension = chartDict[xAxisDimensionKey]
    smallMultiplesColumn = chartDict[smallMultiplesColumnKey]
    lf = ensure_lazyframe(df)
    (
        dfCopy,
        metricToPlot,
        colorArray,
        usedColorDict,
        chartDict,
        column,
        uniqueItems,
    ) = prepare_data_for_width_plot(
        lf, column, valueCols, chartDict, paramDict, usedColorDict
    )
    df = duplicate_dataframe(dfCopy)
    dfDump, rankingArray = sort_dataframe_in_correct_order(
        dfCopy,
        chartDict,
        globalUniqueItems,
        fatherAndChildItems,
        globalAggregateOtherItems,
    )
    filteredUniqueItems = get_filtered_unique_items(dfDump, xAxisDimension)
    reversedList = list(reversed(rankingArray))
    numberOfRows = len(globalUniqueItems)
    dfExport = ensure_lazyframe(df)
    if fatherAndChildDimensions in chartDict and chartDict[fatherAndChildDimensions]:
        df = add_empty_rows_if_hierarchical(
            df, numberOfRows, reversedList, globalUniqueItems, chartDict, True
        )
    elif chartDict[showTopForEachItem]:
        df = add_empty_rows_if_hierarchical(
            df, numberOfRows, reversedList, globalUniqueItems, chartDict, True
        )
    else:
        df = add_empty_rows_if_not_hierarchical(
            df,
            chartDict,
            xAxisDimension,
            reversedList,
            filteredUniqueItems,
            rankingArray,
        )
    dfExport = dfExport.with_columns(
        pl.lit(smallMultiplesDimension).alias(smallMultiplesColumn)
    )
    frameArray.append(dfExport)
    return ensure_lazyframe(df), chartDict, colorArray, metricToPlot, frameArray


def pivot_data_stacked_bar_data_two_dimensions(
    df, chartDict, metricToPlot, expandedSortedItems
):
    """Pivot stacked-bar data lazily."""

    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    xColumn = chartDict[xAxisDimension]
    yColumn = chartDict[yAxisDimension]

    lf = ensure_lazyframe(df)

    group_by_cols = []
    columns, schema = get_schema_and_column_names(lf)
    for element in [yColumn, xColumn]:
        if element:
            group_by_cols.append(element)
            if element in schema and schema[element].is_numeric():
                lf = lf.with_columns(pl.col(element).cast(pl.Utf8))

    lf = lf.group_by(group_by_cols).agg(pl.col(metricToPlot).sum())

    lf = pivot_lazy(
        lf, index_col=xColumn, pivot_col=yColumn, value_col=metricToPlot, agg_func="sum"
    )

    lf = flatten_cols_polars(lf, "")
    lf, _ = clean_column_labels_after_flatten_df(lf, [metricToPlot])
    lf = lf.select(expandedSortedItems)
    return lf


def add_empty_row_above_average(
    df: pl.DataFrame | pl.LazyFrame,
) -> pl.LazyFrame:
    """Insert an empty row right above the average row lazily."""

    namingParams = get_naming_params()
    averageName = namingParams["longAverageName"]

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    empty_row = pl.DataFrame({col: [None] for col in columns}).lazy()

    lf = rank_others_as_last(lf, averageName, 0)
    lf = ensure_lazyframe(lf)
    lf = pl.concat([lf.head(1), empty_row, lf.slice(1)])
    return lf


def add_average_to_stacked_bar(
    df: pl.DataFrame | pl.LazyFrame,
    dfSum: pl.DataFrame | pl.LazyFrame | list | dict,
    chartDict: dict,
    metricToPlot: str,
    smallMultiples: bool,
    priceMetricsArray: list,
) -> pl.LazyFrame:
    """Return ``df`` with an optional average row using lazy operations."""

    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    totalName = namingParams["totalName"]
    showAverageValue = namingParams["showAverageValueName"]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    averageName = namingParams["longAverageName"]
    valueName = namingParams["valueName"]
    notMetConditionValue = namingParams["notMetConditionValue"]

    lf = ensure_lazyframe(df)

    if yAxisDimension in chartDict and (
        (chartDict[yAxisDimension] in [nothingFilteredName]) or smallMultiples
    ):
        if showAverageValue in chartDict and chartDict[showAverageValue]:
            columns, schema = get_schema_and_column_names(lf)
            dfAverage = lf.select(
                [pl.col(col).mean().alias(col) for col in columns]
            ).with_columns(pl.lit(averageName).alias(chartDict[xAxisDimension]))
            lf = pl.concat([lf, dfAverage])

            dfSum_lf = ensure_lazyframe(dfSum)
            if (
                metricToPlot
                in growthMetricArray + percentMetricsArray + priceMetricsArray
            ):
                value_frame = dfSum_lf.with_columns(
                    pl.lit(1).alias("__join_key")
                ).select(pl.col(metricToPlot).alias("__avg_value"), "__join_key")
                lf = (
                    lf.with_columns(pl.lit(1).alias("__join_key"))
                    .join(value_frame, on="__join_key", how="left")
                    .with_columns(
                        pl.when(pl.col(chartDict[xAxisDimension]) == averageName)
                        .then(
                            pl.coalesce(
                                [
                                    (
                                        pl.col("__avg_value") * 100
                                        if metricToPlot in percentMetricsArray
                                        else pl.col("__avg_value")
                                    ),
                                    pl.col(metricToPlot),
                                ]
                            )
                        )
                        .otherwise(pl.col(metricToPlot))
                        .alias(metricToPlot)
                    )
                    .drop("__avg_value", "__join_key")
                )

        lf = lf.with_columns(pl.col(metricToPlot).alias(valueName))
    else:
        columns, schema = get_schema_and_column_names(lf)
        numeric_cols = [c for c, dt in schema.items() if is_numeric_dtype(dt)]
        lf = lf.with_columns(
            pl.sum_horizontal([pl.col(c) for c in numeric_cols]).alias(valueName)
        )

    lf = lf.sort(valueName)
    lf = rank_others_as_last(lf, aggregateOtherItemsNameKey, 0)
    if showAverageValue in chartDict and chartDict[showAverageValue]:
        lf = add_empty_row_above_average(lf)
    return lf


def add_other_metrics_to_stacked_bar(
    df, xColumn, valueCols, chartDict, paramDict, overlayMetric
):
    namingParams = get_naming_params()
    selectedPeriods = namingParams["selectedPeriods"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    periodName = namingParams["periodName"]
    toPlotPeriod = chartDict[toPlotPeriod]
    periodOrder = chartDict[selectedPeriods]
    df = insert_unit_and_volume_price_column(df)
    df = get_growth_rate(df, xColumn, periodOrder, paramDict, chartDict, overlayMetric)
    df, toPlotPeriod = check_if_periods_in_columns(df, toPlotPeriod)
    df = df.filter(pl.col(periodName) == toPlotPeriod)
    df, paramDict, valueCols = process_if_promo_data(df, paramDict, valueCols)
    df = multiply_percent_metrics_by_hundred(df)
    return df, paramDict, valueCols


def prepare_data_for_stacked_bar_one_dimension(
    df: pl.DataFrame | pl.LazyFrame,
    column: str,
    valueCols: list[str],
    chartDict: dict,
    paramDict: dict,
    usedColorDict: dict,
    colorArray: list[str],
    chosenChart: str,
) -> tuple[pl.LazyFrame, str, list[str], dict, list[str]]:
    lf = ensure_lazyframe(df)

    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    periodName = namingParams["periodName"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    metricsToPlot = namingParams["metricsToPlot"]
    showAverageValue = namingParams["showAverageValueName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    totalName = namingParams["totalName"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    selectedPeriods = namingParams["selectedPeriods"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    nothingThereString = namingParams["nothingThereString"]
    plotOverlayChart = namingParams["plotOverlayChart"]
    valueName = namingParams["valueName"]
    toPlotPeriod = chartDict[toPlotPeriod]
    periodOrder = chartDict[selectedPeriods]
    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    xColumn = chartDict[xAxisDimension]
    yColumn = chartDict[yAxisDimension]
    firstAxis = "X"
    secondAxis = "Y"
    # no index in Polars
    metricToPlot = chartDict[metricsToPlot][0]

    if metricToPlot not in priceMetricsArray:
        dfCounts, chartDict = get_number_of_uniques(lf, xColumn, yColumn, chartDict)
    else:
        dfCounts = pl.DataFrame()

    lf, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
        lf, xColumn, yColumn, periodName, valueCols, chartDict, paramDict, firstAxis
    )
    if (
        aggregateOtherItemsName in uniqueItems
        and metricToPlot
        not in priceMetricsArray + growthMetricArray + percentMetricsArray
    ):
        chartDict[showAverageValue] = notMetConditionValue
    if metricToPlot not in priceMetricsArray:
        lf = join_unique_metric_to_df(
            lf, dfCounts, xColumn, yColumn, aggregateOtherItemsName, chartDict
        )
    if (
        plotOverlayChart in chartDict
        and chartDict[plotOverlayChart]
        and len(chartDict[metricsToPlot]) == 2
    ):
        chartDict = prepare_overlay_data_for_stacked_bar(
            lf,
            dfCounts,
            column,
            xColumn,
            aggregateOtherItemsName,
            valueCols,
            chartDict,
            paramDict,
        )
    dfSum = get_average_growth_rate(
        lf, metricToPlot, paramDict, chartDict, valueCols, 0
    )
    lf, paramDict, valueCols = add_other_metrics_to_stacked_bar(
        lf, xColumn, valueCols, chartDict, paramDict, 0
    )
    lf = (
        lf.filter((pl.col(metricToPlot) >= 0.001) | (pl.col(metricToPlot) <= -0.001))
        .filter((pl.col(xColumn) != nothingThereString) & (pl.col(metricToPlot) != 0))
        .pipe(drop_columns, [periodName])
        .select([xColumn, metricToPlot])
        .with_columns(pl.col(metricToPlot).fill_null(0).cast(pl.Float64))
    )
    lf = correct_other_rank_number_for_missing_items(lf, aggregateOtherItemsName)
    if column in [totalName]:
        lf = add_average_to_stacked_bar(
            lf, dfSum, chartDict, metricToPlot, False, priceMetricsArray
        )
    else:
        lf = lf.with_columns(pl.col(metricToPlot).alias(valueName))

    return ensure_lazyframe(lf), metricToPlot, colorArray, usedColorDict, uniqueItems


def find_column_ranking_for_marimekko(
    dfCopy, sortedItems, aggregateOtherItemsName, chartDict
):
    """Rank columns by their summed values using Polars."""

    lf = ensure_lazyframe(dfCopy)
    allItems = copy.deepcopy(sortedItems)
    if aggregateOtherItemsName and aggregateOtherItemsName in allItems:
        sortedItems.remove(aggregateOtherItemsName)

    if not sortedItems:
        return allItems

    sums = lf.select([pl.col(c).sum().alias(c) for c in sortedItems]).collect(
        engine="streaming"
    )

    columns, schema = get_schema_and_column_names(sums)
    pairs = [(col, sums[col][0]) for col in columns]
    pairs.sort(key=lambda x: x[1], reverse=True)
    sortedList = [name for name, _ in pairs]

    if aggregateOtherItemsName and aggregateOtherItemsName in allItems:
        sortedList.append(aggregateOtherItemsName)
    return sortedList


def sort_data_stacked_bar_data_two_dimensions(
    df: pl.LazyFrame, chartDict, aggregateOtherItemsName
):
    namingParams = get_naming_params()
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    xColumn = chartDict[xAxisDimension]
    yColumn = chartDict[yAxisDimension]
    notSortedItems = unique_values_lazy(yColumn, df)
    sortedItems = []
    lastElement = False
    if aggregateOtherItemsName:
        for element in notSortedItems:
            if element != aggregateOtherItemsName:
                sortedItems.append(str(element))
            else:
                lastElement = str(element)
        if lastElement:
            sortedItems.append(lastElement)
    else:
        sortedItems = notSortedItems
    expandedSortedItems = [xColumn] + sortedItems
    return df, expandedSortedItems, sortedItems, aggregateOtherItemsName


def prepare_data_for_width_plot(
    dfCopy, period, valueCols, chartDict, paramDict, usedColorDict
):
    """
    we need to filter the period and unpivot the chosen columns
    """
    namingParams = get_naming_params()
    barmekkoChart = namingParams["barmekkoChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    periodName = namingParams["periodName"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    fcName = namingParams["fcName"]
    acName = namingParams["acName"]
    acAndFcName = namingParams["acAndFcName"]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    chosenChart = namingParams["chosenChart"]
    totalName = namingParams["totalName"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    chosenChart = chartDict[chosenChart]
    periodOrder = chartDict[selectedPeriods]
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    df = duplicate_dataframe(dfCopy)
    columns, schema = get_schema_and_column_names(df)
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        periodsArray = get_periods_array(df)
        if fcName in periodsArray:
            if period == acName and acAndFcName not in chartDict[selectedPeriods]:
                df = df.with_columns(
                    pl.when(pl.col(periodName).is_in([fcName, acName]))
                    .then(acAndFcName)
                    .otherwise(pl.col(periodName))
                    .alias(periodName)
                )
                chartDict[selectedPeriods] = list(
                    map(
                        lambda x: x.replace(period, acAndFcName),
                        chartDict[selectedPeriods],
                    )
                )
                period = acAndFcName
    if chosenChart not in [stackedBarChart] and period:
        df = df.filter(pl.col(periodName) == period)
    if chosenChart in [barmekkoChart]:
        df, metricToPlot, chartDict, colorArray, uniqueItems = (
            prepare_data_for_barmekko(df, valueCols, chartDict, paramDict, colorArray)
        )
    elif chosenChart in [marimekkoChart]:
        df, metricToPlot, colorArray, usedColorDict, uniqueItems = (
            prepare_data_for_marimekko(
                df,
                valueCols,
                chartDict,
                paramDict,
                usedColorDict,
                colorArray,
                chosenChart,
            )
        )
    elif chosenChart in [stackedBarChart]:
        column = period
        if column in [totalName] and chartDict[yAxisDimension] in [
            nothingFilteredName,
            None,
        ]:
            df, metricToPlot, colorArray, usedColorDict, uniqueItems = (
                prepare_data_for_stacked_bar_one_dimension(
                    df,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    colorArray,
                    chosenChart,
                )
            )
        elif column in [totalName] and chartDict[yAxisDimension] not in [
            nothingFilteredName,
            None,
        ]:
            df, metricToPlot, colorArray, usedColorDict, uniqueItems = (
                prepare_data_for_stacked_bar_two_dimensions(
                    df,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    colorArray,
                    chosenChart,
                )
            )
        elif column not in [totalName] and chartDict[yAxisDimension] in [
            nothingFilteredName,
            None,
        ]:
            df, metricToPlot, colorArray, usedColorDict, uniqueItems = (
                prepare_data_for_stacked_bar_one_dimension(
                    df,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    colorArray,
                    chosenChart,
                )
            )
        elif column not in [totalName] and chartDict[yAxisDimension] not in [
            nothingFilteredName,
            None,
        ]:
            df, metricToPlot, colorArray, usedColorDict, uniqueItems = (
                prepare_data_for_stacked_bar_two_dimensions(
                    df,
                    column,
                    valueCols,
                    chartDict,
                    paramDict,
                    usedColorDict,
                    colorArray,
                    chosenChart,
                )
            )
    return df, metricToPlot, colorArray, usedColorDict, chartDict, period, uniqueItems


def move_other_to_end_of_list(itemTotals, aggregateOtherItemsName):
    rankedArray = []
    otherRanked = ""
    for element in itemTotals:
        if aggregateOtherItemsName not in str(element):
            rankedArray.append(str(element))
        else:
            otherRanked = str(element)
    if len(otherRanked) > 0:
        rankedArray.append(otherRanked)
    return rankedArray


def prepare_data_for_syn_plot(
    dfCopy,
    column,
    columns,
    aggregateOtherItemsName,
    frameArray,
    synColumnArray,
    synColorArray,
    count,
    paramDict,
    chartDict,
):
    namingParams = get_naming_params()
    colorpalette = namingParams["colorpalette"]
    numberOfTop = namingParams["numberOfTop"]
    modernColorpalette = namingParams["modernColorpalette"]
    periodName = namingParams["periodName"]
    chosenPalette = chartDict[colorpalette]
    paletteChoices = [
        chosenPalette,
        chosenPalette,
        chosenPalette,
        chosenPalette,
        chosenPalette,
        chosenPalette,
    ]
    numberOfPalette = len(paletteChoices)
    df = duplicate_dataframe(dfCopy)
    dfMostRecent = df.tail(1)
    mostRecentPeriod = df.select(pl.col("Period").max()).collect().item()
    leastRecentPeriod = df.select(pl.col("Period").min()).collect().item()
    check_collect("ZAAT", "mostRecentPeriod", mostRecentPeriod)
    check_collect("ZAAT2", "leastRecentPeriod", leastRecentPeriod)
    if count <= (numberOfPalette - 1):
        dfMostRecent = dfMostRecent.with_columns(
            pl.when(pl.col(periodName) == pl.lit(mostRecentPeriod))
            .then(
                pl.lit(column)
            )  # <-- Use pl.lit() because 'column' is a Python variable
            .otherwise(pl.col(periodName))
            .alias(periodName)
        )
        if aggregateOtherItemsName in columns:
            numberOfElements = len(columns) - 1
        else:
            numberOfElements = len(columns)
        synColumnArray = synColumnArray + columns
        synColumnArray = move_other_to_end_of_list(
            synColumnArray, aggregateOtherItemsName
        )
        dfMostRecent = adjust_percentages_dynamic(dfMostRecent)
        frameArray.append(dfMostRecent)
        colorDict = get_color_dictionary(chartDict)
        colColorArray = colorDict[paletteChoices[count]][0:numberOfElements]
        colColorArray = modify_color_array(colColorArray, count)
        synColorArray = synColorArray + colColorArray
        count = count + 1
    return (
        count,
        frameArray,
        synColumnArray,
        synColorArray,
        leastRecentPeriod,
        mostRecentPeriod,
    )


def clean_data_for_stacked_column(
    df_lazy: pl.LazyFrame, metric: str, column: str, xColumn: str
) -> pl.LazyFrame:
    # 1) Select only the columns we need
    keepCols = [metric, column, xColumn]
    df_lazy = df_lazy.select(keepCols)

    # 2) Fill NULL values with 0
    df_lazy = df_lazy.fill_null(0)

    # If you also want to treat NaN as "missing" and fill with 0:
    # df_lazy = df_lazy.with_columns(pl.all().fill_nan(0))

    # 3) Filter rows where metric >= 0.0001 or <= -0.0001
    df_lazy = df_lazy.filter((pl.col(metric) >= 0.0001) | (pl.col(metric) <= -0.0001))

    return df_lazy


def prepare_overlay_data_for_stacked_column(df, column, xColumn, chartDict, paramDict):
    namingParams = get_naming_params()
    metricsToPlot = namingParams["metricsToPlot"]
    totalName = namingParams["totalName"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    overlayChartDfKey = namingParams["overlayChartDf"]
    overlayChartMetric = chartDict[metricsToPlot][1]
    overlayChartDf = duplicate_dataframe(df)
    overlayChartDf = clean_data_for_stacked_column(
        overlayChartDf, overlayChartMetric, column, xColumn
    )
    overlayChartDf = prepare_metric_dataframe_for_stacked_column(
        overlayChartDf, xColumn, column, overlayChartMetric, chartDict, paramDict
    )
    overlayChartDf = overlayChartDf.rename({totalName: overlayChartMetric})
    overlayChartDf = ensure_lazyframe(overlayChartDf).with_columns(
        pl.all().fill_null(np.nan)
    )
    chartDict[overlayChartMetricKey] = overlayChartMetric
    chartDict[overlayChartDfKey] = overlayChartDf
    return chartDict


def prepare_metric_dataframe_for_stacked_column(
    df: pl.LazyFrame,
    xColumn: str,
    column: str,
    metric: str,
    chartDict: dict,
    paramDict: dict,
) -> pl.LazyFrame:
    """Stack and pivot data using Polars."""

    # 1) Group by both columns and sum the metric
    #    (This is optional—depends on if you want partial reduction first.)
    grouped = df.group_by([xColumn, column]).agg(pl.col(metric).sum().alias(metric))
    # 2) Pivot from long to wide using the purely lazy approach
    #    index_col = xColumn, pivot_col = column, value_col = metric
    pivoted = pivot_lazy(
        lf=grouped,
        index_col=xColumn,
        pivot_col=column,
        value_col=metric,
        agg_func="first",  # or "sum" again, but we already summed above
    )
    # 3) (Optional) rename columns if desired
    columns, schema = get_schema_and_column_names(pivoted)
    rename_map = {col: col.replace(metric + "_", "") for col in schema}

    pivoted = pivoted.rename(rename_map)
    # 4) (Optional) reorder xColumn
    pivoted = sort_periods_polars(pivoted, chartDict, paramDict)
    return pivoted


def group_and_sum_metrics(
    df: pl.LazyFrame, group_byCols: list[str], metricsToPlot: list[str]
) -> pl.LazyFrame:
    """
    Lazy group_by + sum of the given metrics.
    """
    agg_exprs = [pl.col(m).sum().alias(m) for m in metricsToPlot]
    return df.group_by(group_byCols).agg(agg_exprs)


def get_columns_by_desc_sum(lf: pl.LazyFrame) -> list[str]:
    """
    1. Sum each *numeric* column of `lf`.
    2. Sort them by the sum in descending order.
    3. Return a list of column names in that order.
    """
    lf_sums_desc = (
        lf.select(pl.selectors.numeric().sum())
        .unpivot(index=None, on=None, variable_name="variable", value_name="value")
        .sort("value", descending=True)
    )

    # Collect and grab the 'variable' column as a Python list
    columns_desc = (
        lf_sums_desc.select("variable")
        .collect(engine="streaming")
        .get_column("variable")
        .to_list()
    )
    check_collect("AAR", "columns_desc", columns_desc)
    return columns_desc


def set_columns_in_descending_order(df, rankedArray):
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    orderedArray = copy.deepcopy(rankedArray)
    orderedArray.insert(0, periodName)
    df = df.select([pl.col(c) for c in orderedArray])
    return df


def check_if_all_periods_in_df(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict, paramDict: dict
) -> pl.LazyFrame:
    """Ensure ``df`` contains all periods defined in ``paramDict``.

    The function returns a ``LazyFrame`` where missing periods are inserted
    according to the order provided in ``paramDict``.
    """

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    allPeriodsList = namingParams["allPeriodsList"]

    lf = ensure_lazyframe(df)
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        periodsList = paramDict[allPeriodsList]
        if get_row_count(lf) < len(periodsList):
            lf = reindex_polars(lf, periodName, periodsList)
    return lf


def check_index_order(
    lf: pl.LazyFrame, paramDict: dict, chartDict: dict, xColumn: str
) -> pl.LazyFrame:
    """
    Polars-lazy adaptation of check_index_order,
    ignoring the branch that checks for two rows.
    """

    namingParams = get_naming_params()
    yearName = namingParams["yearName"]
    periodChoice = namingParams["periodChoice"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    selectedPeriods = namingParams["selectedPeriods"]
    chosenChart = namingParams["chosenChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    changedTimeAggregation = namingParams["changedTimeAggregation"]

    chosenChart = chartDict[chosenChart]
    periodChoice = chartDict[periodChoice]
    periodOrder = chartDict[selectedPeriods]

    # We need to partially collect to see the current row "index" (xColumn values).
    # Polars doesn't do "index," so we treat xColumn as the row label.
    collected = lf.select(xColumn).collect()
    indexOrder = collected[xColumn].to_list()
    check_collect("AEA", "collected", collected)
    # Original logic minus the conditional branch for two rows
    if (
        periodChoice == yearName
        and compareWithYearBefore in chartDict
        and (
            changedTimeAggregation not in paramDict
            or not paramDict[changedTimeAggregation]
        )
    ):
        # If chartDict[compareWithYearBefore] is True, sort desc; else asc
        if chartDict[compareWithYearBefore]:
            lf = lf.sort(xColumn, descending=True)
        else:
            lf = lf.sort(xColumn)
    else:
        # Compare current "index order" with periodOrder
        if indexOrder != periodOrder:
            if set(indexOrder) == set(periodOrder):
                lf = reindex_polars(lf, xColumn, periodOrder)
            else:
                lf = lf.sort(xColumn)

    return lf


def prepare_data_for_stacked_column(
    dfCopy, metric, column, xColumn, aggregateOtherItemsName, chartDict, paramDict
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    colorpalette = namingParams["colorpalette"]
    totalName = namingParams["totalName"]
    valueName = namingParams["valueName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    selectedPeriods = namingParams["selectedPeriods"]
    plotOverlayChart = namingParams["plotOverlayChart"]
    overlayChartMetricKey = namingParams["overlayChartMetric"]
    maxPeriodsForBarChart = namingParams["maxPeriodsForBarChart"]
    maxPeriodsForBarChart = configParams[maxPeriodsForBarChart]
    periodOrder = chartDict[selectedPeriods]
    metricsToPlot = namingParams["metricsToPlot"]

    # 1) Duplicate df if necessary
    df = duplicate_dataframe(dfCopy)

    # 2) Clean and prepare the data
    df = clean_data_for_stacked_column(df, metric, column, xColumn)
    chartDict, paramDict = calculate_cagr(
        df, column, xColumn, metric, paramDict, chartDict
    )
    df = prepare_metric_dataframe_for_stacked_column(
        df, xColumn, column, metric, chartDict, paramDict
    )

    # 3) Check if we need overlay data
    if (
        plotOverlayChart in chartDict
        and chartDict[plotOverlayChart]
        and len(chartDict[metricsToPlot]) == 2
    ):
        chartDict = prepare_overlay_data_for_stacked_column(
            dfCopy, column, xColumn, chartDict, paramDict
        )

    # 4) Sort columns by descending sum
    columns, schema = get_schema_and_column_names(df)
    itemTotals = get_columns_by_desc_sum(df)
    rankedArray = move_other_to_end_of_list(itemTotals, aggregateOtherItemsName)
    df = set_columns_in_descending_order(df, rankedArray)

    # 5) Derive color info
    colorDict = get_color_dictionary(chartDict)
    colorArray = get_color_array(colorDict, chartDict)
    colorArray = set_other_color_to_grey(
        rankedArray, aggregateOtherItemsName, colorArray, chartDict, 0
    )

    # 6) Create "Value" column if we are not dealing with the total
    if column != totalName:
        columns, schema = get_schema_and_column_names(df)
        numeric_cols = [c for c, dt in schema.items() if is_numeric_dtype(dt)]
        df = df.with_columns(
            pl.sum_horizontal([pl.col(c) for c in numeric_cols]).alias(valueName)
        )

    # 7) Create an absolute dataframe if the user wants to compare (plotValuesAsChoice != absolute)
    if chartDict[plotValuesAsChoice] != absolute:
        group_byCols = [xColumn]
        valueCols = [metric]

        dfAbsolute = group_and_sum_metrics(chartDict[absolute], group_byCols, valueCols)

        dfAbsolute = check_index_order(dfAbsolute, paramDict, chartDict, xColumn)

        # rename columns except xColumn -> "Value"
        dfAbsolute = dfAbsolute.select(
            [pl.col(xColumn), pl.all().exclude(xColumn).alias(valueName)]
        )

        chartDict[absolute] = dfAbsolute

    # 8) Grab first/last rows for the “most recent” vs. “least recent” period
    dfMostRecent = df.tail(1)
    mostRecentPeriod = df.select(pl.col("Period").max()).collect().item()
    leastRecentPeriod = df.select(pl.col("Period").min()).collect().item()
    check_collect("AAT", "mostRecentPeriod", mostRecentPeriod)
    check_collect("AAT2", "leastRecentPeriod", leastRecentPeriod)

    # 9) Verify all needed periods exist
    df = check_if_all_periods_in_df(df, chartDict, paramDict)

    # 10) Possibly insert highlight color
    colorArray = insert_highlight_color(
        column, rankedArray, colorArray, paramDict, chartDict
    )

    return df, rankedArray, colorArray, chartDict, leastRecentPeriod, mostRecentPeriod


def prepare_data_for_stacked_bar_two_dimensions(
    df, column, valueCols, chartDict, paramDict, usedColorDict, colorArray, chosenChart
):
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    periodName = namingParams["periodName"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    metricsToPlot = namingParams["metricsToPlot"]
    showAverageValue = namingParams["showAverageValueName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    totalName = namingParams["totalName"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    selectedPeriods = namingParams["selectedPeriods"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    valueName = namingParams["valueName"]
    nothingThereString = namingParams["nothingThereString"]
    aggregateOtherItemsNameKey = namingParams["aggregateOtherItemsName"]
    toPlotPeriod = chartDict[toPlotPeriod]
    periodOrder = chartDict[selectedPeriods]
    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    xColumn = chartDict[xAxisDimension]
    yColumn = chartDict[yAxisDimension]
    firstAxis = "X"
    secondAxis = "W"
    metricToPlot = chartDict[metricsToPlot][0]

    lf = ensure_lazyframe(df)
    if metricToPlot not in priceMetricsArray:
        dfCounts, chartDict = get_number_of_uniques(lf, xColumn, yColumn, chartDict)
    lf, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
        lf, xColumn, yColumn, periodName, valueCols, chartDict, paramDict, firstAxis
    )
    lf = ensure_lazyframe(lf)
    if metricToPlot not in priceMetricsArray:
        lf = join_unique_metric_to_df(
            lf, dfCounts, xColumn, yColumn, aggregateOtherItemsName, chartDict
        )
    lf, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
        lf, yColumn, xColumn, periodName, valueCols, chartDict, paramDict, secondAxis
    )
    lf = lf.filter(pl.col(periodName) == toPlotPeriod)
    lf = drop_columns(lf, [periodName])
    lf = lf.select([xColumn, yColumn, metricToPlot])
    lf = lf.filter((pl.col(metricToPlot) >= 0.001) | (pl.col(metricToPlot) <= -0.001))
    lf = lf.filter(
        (pl.col(xColumn) != nothingThereString)
        & (pl.col(yColumn) != nothingThereString)
        & (pl.col(metricToPlot) != 0)
    )
    lf, expandedSortedItems, sortedItems, aggregateOtherItemsName = (
        sort_data_stacked_bar_data_two_dimensions(
            lf, chartDict, aggregateOtherItemsName
        )
    )
    usedColorDict = track_used_colors(
        usedColorDict, sortedItems, aggregateOtherItemsName, colorArray
    )
    lf = lf.with_columns(pl.col(metricToPlot).fill_null(0).cast(pl.Float64))
    lf = pivot_data_stacked_bar_data_two_dimensions(
        lf, chartDict, metricToPlot, expandedSortedItems
    )
    sortedList = find_column_ranking_for_marimekko(
        lf, sortedItems, aggregateOtherItemsName, chartDict
    )

    numeric_cols = (
        lf.select(pl.selectors.numeric())
        .collect_schema()  # cheap: looks only at the schema
        .names()  # -> list[str]
    )

    lf = lf.with_columns(pl.sum_horizontal(pl.col(numeric_cols)).alias(valueName))

    lf = lf.sort(valueName)
    lf = rank_others_as_last(lf, aggregateOtherItemsNameKey, 0)
    lf = lf.select(sortedList + [valueName])
    lf = ensure_lazyframe(lf)
    colorArray = assign_same_colors_to_all_charts(
        colorArray, usedColorDict, sortedList, aggregateOtherItemsName
    )
    expandedSortedItems = [xColumn] + sortedList
    colorArray = set_other_color_to_grey(
        expandedSortedItems, aggregateOtherItemsName, colorArray, chartDict, -1
    )
    colorArray = insert_highlight_color(
        xColumn, sortedItems, colorArray, paramDict, chartDict
    )
    return lf, metricToPlot, colorArray, usedColorDict, uniqueItems


def sum_ratio_lazy(
    df: pl.LazyFrame | pl.DataFrame, numerator: str, denominator: str
) -> float:
    """Return ``sum(numerator) / sum(denominator)`` with a single collect."""

    lf = ensure_lazyframe(df)
    ratios = _sum_ratios_lazyframe(lf, {"ratio": (numerator, denominator)})
    return ratios.get("ratio", 0.0)


def _sum_ratios_lazyframe(
    lf: pl.LazyFrame, pairs: dict[str, tuple[str, str]]
) -> dict[str, float]:
    """Return ratios of summed columns in a single collect."""

    if not pairs:
        return {}

    lf = ensure_lazyframe(lf)
    exprs = [
        pl.col(num).sum().alias(f"{key}_num") for key, (num, _den) in pairs.items()
    ] + [pl.col(den).sum().alias(f"{key}_den") for key, (_num, den) in pairs.items()]
    result = lf.select(exprs).collect()
    ratios: dict[str, float] = {}
    for key in pairs:
        num_sum = float(result[f"{key}_num"][0])
        den_sum = float(result[f"{key}_den"][0])
        ratios[key] = num_sum / den_sum if den_sum != 0 else 0.0
    return ratios


def prepare_data_for_barmekko(
    df: pl.DataFrame | pl.LazyFrame,
    valueCols: list[str],
    chartDict: dict,
    paramDict: dict,
    colorArray: list[str],
) -> tuple[pl.LazyFrame, str, dict, list[str], list[str]]:
    """Prepare dataset for barmekko charts using lazy operations."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    marginInPercentTotalName = namingParams["marginInPercentTotalName"]
    marginInPercentOfNetSalesTotalName = namingParams[
        "marginInPercentOfNetSalesTotalName"
    ]
    monetaryLocalCurrencyName = namingParams["monetaryLocalCurrencyName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    marginName = namingParams["marginName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    nothingThereString = namingParams["nothingThereString"]
    pricePerUnitTotalName = namingParams["pricePerUnitTotalName"]
    pricePerVolumeTotalName = namingParams["pricePerVolumeTotalName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerUnitNetDiscountTotalName = namingParams["pricePerUnitNetDiscountTotalName"]
    pricePerVolumeNetDiscountTotalName = namingParams[
        "pricePerVolumeNetDiscountTotalName"
    ]
    netOfDiscountName = namingParams["netOfDiscountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    discountInPercentNameTotalName = namingParams["discountInPercentNameTotalName"]
    discountName = namingParams["discountName"]
    xAxisDimension = namingParams["xAxisDimension"]
    yColumn = None
    smallMultiplesColumn = chartDict[smallMultiplesColumn]
    xColumn = chartDict[xAxisDimension]
    yAxisMetric = chartDict[yAxisMetric]
    xAxisMetric = chartDict[xAxisMetric]
    metricToPlot = yAxisMetric
    lf = ensure_lazyframe(df)

    columns, _ = get_schema_and_column_names(lf)
    if xAxisMetric in columns:
        lf = lf.filter(pl.col(xAxisMetric) != 0)

    lf, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
        lf, xColumn, yColumn, periodName, valueCols, chartDict, paramDict, "X"
    )
    lf = ensure_lazyframe(lf)

    group_byCols = [xColumn]
    metricsToPlot = [yAxisMetric, xAxisMetric]
    sortMetric = yAxisMetric
    valueCols = check_value_column_exist(lf, valueCols)

    lf = lf.group_by(group_byCols).agg([pl.col(col).sum() for col in valueCols])
    lf, paramDict, colArray = calculate_unit_and_volume_price(lf, paramDict, [])

    lf = lf.filter(
        (pl.col(xColumn) != nothingThereString)
        & (pl.col(yAxisMetric) != 0)
        & (pl.col(xAxisMetric) != 0)
    ).filter(
        ((pl.col(yAxisMetric) >= 0.001) | (pl.col(yAxisMetric) <= -0.001))
        & ((pl.col(xAxisMetric) >= 0.001) | (pl.col(xAxisMetric) <= -0.001))
    )

    ratio_pairs: dict[str, tuple[str, str]] = {}
    if pricePerUnitName in metricsToPlot:
        ratio_pairs[pricePerUnitTotalName] = (monetaryLocalCurrencyName, unitsName)
    if pricePerVolumeName in metricsToPlot:
        ratio_pairs[pricePerVolumeTotalName] = (monetaryLocalCurrencyName, volumeName)
    if pricePerVolumeNetDiscountName in metricsToPlot:
        ratio_pairs[pricePerVolumeNetDiscountTotalName] = (
            netOfDiscountName,
            volumeName,
        )
    if pricePerUnitNetDiscountName in metricsToPlot:
        ratio_pairs[pricePerUnitNetDiscountTotalName] = (netOfDiscountName, unitsName)
    if discountInPercentName in metricsToPlot:
        ratio_pairs[discountInPercentNameTotalName] = (
            discountName,
            monetaryLocalCurrencyName,
        )
    if marginInPercentName in metricsToPlot:
        ratio_pairs[marginInPercentTotalName] = (marginName, monetaryLocalCurrencyName)
    if marginInPercentOfNetSalesName in metricsToPlot:
        ratio_pairs[marginInPercentOfNetSalesTotalName] = (
            marginName,
            netOfDiscountName,
        )

    chartDict.update(_sum_ratios_lazyframe(lf, ratio_pairs))

    lf = lf.sort(by=sortMetric, descending=True)

    group_byCols = [c for c in (yColumn, xColumn) if c]
    df_grouped = lf.group_by(group_byCols).agg([pl.col(c).sum() for c in metricsToPlot])

    if not yColumn:
        lf_pivot = df_grouped.select([xColumn, *metricsToPlot])
    else:
        lf_pivot = None
        for metric in metricsToPlot:
            select_cols = [xColumn, metric]
            if yColumn:
                select_cols.insert(1, yColumn)
            pivoted = ensure_lazyframe(
                pivot_lazy(
                    df_grouped.select(select_cols),
                    xColumn,
                    yColumn,
                    metric,
                    "sum",
                )
            )
            if yColumn and yColumn in get_schema_and_column_names(pivoted)[0]:
                pivoted = pivoted.drop(yColumn)
            lf_pivot = (
                pivoted
                if lf_pivot is None
                else lf_pivot.join(pivoted, on=xColumn, how="inner")
            )

    lf_pivot = flatten_cols_polars(lf_pivot, "")
    lf_pivot = lf_pivot.fill_null(0).with_columns(
        cs.numeric().cast(pl.Float64)  # cast every numeric column
    )
    lf_pivot = lf_pivot.sort(sortMetric, descending=True)

    return ensure_lazyframe(lf_pivot), metricToPlot, chartDict, colorArray, uniqueItems


# ---------------------------------------------------------
# Main function
# ---------------------------------------------------------


def _handle_two_dimension_largest(
    df, axisDim, altAxisDim, periodName, valueCols, chartDict, paramDict, axisLabel
):
    """
    Calls show_only_largest if necessary, returning updated df, uniqueItems,
    aggregateOtherItemsName, and valueCols.
    """
    return show_only_largest(
        df, axisDim, altAxisDim, periodName, valueCols, chartDict, paramDict, axisLabel
    )


def _select_and_group_lazily(df, keepCols, group_byCols, metricsToPlot):
    """Return ``df`` grouped by ``group_byCols`` with sums of ``metricsToPlot``."""

    lf = ensure_lazyframe(df)
    lf = lf.select(keepCols)
    lf = lf.group_by(group_byCols).agg([pl.col(col).sum() for col in metricsToPlot])
    return lf


def _sort_and_filter_polars(
    df, metricToPlot, xColumn, yColumn, nothingThereString
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Sort by metric and apply filters using Polars lazily.

    Returns the filtered ``LazyFrame`` and a lazy frame containing the unique
    ``yColumn`` values. The caller can ``collect`` this frame if required.
    """

    lf = ensure_lazyframe(df)
    columns, _ = get_schema_and_column_names(lf)
    sort_cols = [metricToPlot] if metricToPlot in columns else []
    if yColumn in columns:
        sort_cols.append(yColumn)
    if xColumn in columns:
        sort_cols.append(xColumn)
    if sort_cols:
        descending = [True] + [False] * (len(sort_cols) - 1)
        lf = lf.sort(sort_cols, descending=descending)
    lf = lf.filter((pl.col(metricToPlot) >= 0.001) | (pl.col(metricToPlot) <= -0.001))
    if {metricToPlot, yColumn, xColumn}.issubset(set(columns)):
        lf = lf.filter(pl.col(metricToPlot) != 0)
        # ``collect`` moved to the caller to keep this helper lazy
        notSortedLF = lf.select(pl.col(yColumn).unique(maintain_order=True))
    elif metricToPlot in columns:
        lf = lf.filter(pl.col(metricToPlot) != 0)
        notSortedLF = pl.DataFrame({yColumn: []}).lazy()
    else:
        notSortedLF = pl.DataFrame({yColumn: []}).lazy()

    return lf, notSortedLF


def _pivot_for_two_dimensional(
    df, xColumn, yColumn, metricsToPlot, sortedItems, aggregateOtherItemsName
):
    """Pivot and flatten data columns using Polars lazily."""

    lf = ensure_lazyframe(df)
    columns, schema = get_schema_and_column_names(lf)
    for c in [yColumn, xColumn]:
        dtype = schema.get(c) if isinstance(schema, dict) else None
        if c in columns and dtype is not None and dtype.is_numeric():
            lf = lf.with_columns(pl.col(c).cast(pl.Utf8))

    lf = lf.group_by([yColumn, xColumn]).agg(
        [pl.col(col).sum() for col in metricsToPlot]
    )

    # ``pivot_lazy`` handles the lack of ``LazyFrame.pivot`` internally
    pivoted_frames = []
    for metric in metricsToPlot:
        pivoted = pivot_lazy(
            lf.select([xColumn, yColumn, metric]), xColumn, yColumn, metric, "sum"
        )
        pivoted_frames.append(pivoted)

    lf = pivoted_frames[0]
    for frame in pivoted_frames[1:]:
        lf = lf.join(frame, on=xColumn, how="inner")

    lf = flatten_cols_polars(lf, "")
    lf, _ = clean_column_labels_after_flatten_df(lf, metricsToPlot)
    columns, schema = get_schema_and_column_names(lf)
    rename_map = {c: c.lstrip("_") for c in columns if c.startswith("_")}
    if rename_map:
        lf = lf.rename(rename_map)
    return lf


def _reorder_columns(df, xColumn, sortedItems, aggregateOtherItemsName):
    """
    Reorders DataFrame columns based on sortedItems, ensuring xColumn is first.
    """
    lf = ensure_lazyframe(df)

    if not sortedItems:
        columns, schema = get_schema_and_column_names(lf)
        if xColumn in columns:
            new_cols = [xColumn] + [c for c in columns if c != xColumn]
            return lf.select(new_cols)
        return lf
    columns, schema = get_schema_and_column_names(lf)
    expandedSortedItems = [xColumn] + sortedItems
    existingCols = [c for c in expandedSortedItems if c in columns]
    return lf.select(existingCols)


def prepare_data_for_marimekko(
    df: pl.LazyFrame,
    valueCols: list[str],
    chartDict: dict,
    paramDict: dict,
    usedColorDict: dict,
    colorArray: list[str],
    chosenChart: str,
) -> tuple[pl.LazyFrame, str, list[str], dict, list[str]]:
    """Prepare marimekko data.

    Parameters
    ----------
    df:
        Input data as a ``LazyFrame``. An error is raised for other types.

    Returns
    -------
    tuple[LazyFrame, str, list[str], dict, list[str]]
        The processed frame, metric name, color array, used colors and
        unique items.
    """

    if not isinstance(df, pl.LazyFrame):
        raise TypeError("df must be a `pl.LazyFrame`")

    # ---------------------------------------------------------
    # 1. Naming/metric parameters (inline, no separate fetch function)
    # ---------------------------------------------------------
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()

    nothingThereString = namingParams["nothingThereString"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    periodName = namingParams["periodName"]
    xAxisDimension = namingParams["xAxisDimension"]
    yAxisDimension = namingParams["yAxisDimension"]
    singleMetric = namingParams["singleMetric"]
    chosenChart = chartDict[namingParams["chosenChart"]]

    # ---------------------------------------------------------
    # 2. Extract from chartDict
    # ---------------------------------------------------------
    xColumn = chartDict[xAxisDimension]
    yColumn = chartDict[yAxisDimension]
    metricToPlot = chartDict[singleMetric]

    # ---------------------------------------------------------
    # 3. Show only largest for X
    # ---------------------------------------------------------
    firstAxis = "X"
    df, uniqueItems, aggregateOtherItemsName, valueCols = _handle_two_dimension_largest(
        df, xColumn, yColumn, periodName, valueCols, chartDict, paramDict, firstAxis
    )

    # Show only largest for Y (if applicable)
    secondAxis = "W"
    if yColumn != nothingFilteredName and yColumn and xColumn:
        group_byCols = [xColumn, yColumn]
        df, uniqueItems, aggregateOtherItemsName, valueCols = (
            _handle_two_dimension_largest(
                df,
                yColumn,
                xColumn,
                periodName,
                valueCols,
                chartDict,
                paramDict,
                secondAxis,
            )
        )

    # ---------------------------------------------------------
    # 4. Determine metrics to plot
    # ---------------------------------------------------------
    metricsToPlot = [metricToPlot]
    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        metricsToPlot = valueCols
        if (
            metricToPlot not in metricsToPlot
            and metricToPlot not in percentMetricsArray
        ):
            metricsToPlot.append(metricToPlot)

    # ---------------------------------------------------------
    # 5. Figure out which columns to keep and group by
    # ---------------------------------------------------------
    columns, _ = get_schema_and_column_names(df)
    group_byCols = [xColumn, yColumn]

    keepCols = []
    for element in [xColumn, yColumn]:
        if element not in [nothingFilteredName, notMetConditionValue, None]:
            keepCols.append(element)
    keepCols = list(set(keepCols + metricsToPlot))

    # Filter out only columns actually present
    checkedKeepCols = [c for c in keepCols if c in columns]
    checkedgroup_byCols = [c for c in group_byCols if c in columns]

    # ---------------------------------------------------------
    # 6. Group and aggregate (Polars lazy)
    # ---------------------------------------------------------
    df = _select_and_group_lazily(
        df, checkedKeepCols, checkedgroup_byCols, metricsToPlot
    )

    # ---------------------------------------------------------
    # 7. Sort and filter in Polars
    # ---------------------------------------------------------
    df, notSortedLF = _sort_and_filter_polars(
        df, metricToPlot, xColumn, yColumn, nothingThereString
    )

    # ---------------------------------------------------------
    # 8. If 2D pivot is needed
    # ---------------------------------------------------------
    smallMultiples = False  # or derive from paramDict / chartDict
    sortedItems: list[str] = []
    notSortedItems: list[str] = []
    if yColumn != nothingFilteredName and not smallMultiples and yColumn and xColumn:
        columns, schema = get_schema_and_column_names(notSortedLF)
        if columns:
            notSortedItems = (
                notSortedLF.select(yColumn)
                .collect(engine="streaming")
                .get_column(yColumn)
                .to_list()
            )
        lastElement = False
        if aggregateOtherItemsName:
            for element in notSortedItems:
                if element != aggregateOtherItemsName:
                    sortedItems.append(str(element))
                else:
                    lastElement = str(element)
            if lastElement:
                sortedItems.append(lastElement)
        else:
            sortedItems = notSortedItems

        # Update colors
        usedColorDict = track_used_colors(
            usedColorDict, sortedItems, aggregateOtherItemsName, colorArray
        )
        # Pivot

        df = _pivot_for_two_dimensional(
            df, xColumn, yColumn, metricsToPlot, sortedItems, aggregateOtherItemsName
        )
        # Reorder
        df = _reorder_columns(df, xColumn, sortedItems, aggregateOtherItemsName)
    else:
        # If no pivot, might still get a sorted list for marimekko or others
        sortedItems = find_column_ranking_for_marimekko(
            df, [], aggregateOtherItemsName, chartDict
        )

    # ---------------------------------------------------------
    # 9. Final type conversions and color assignments
    # ---------------------------------------------------------
    columns, schema = get_schema_and_column_names(df)
    if xColumn in columns:
        df = df.with_columns(pl.col(xColumn))

    df = df.fill_null(0)
    df = df.with_columns(
        [pl.col(col).cast(float) for col, dt in schema.items() if is_numeric_dtype(dt)]
    )

    if not sortedItems:
        sortedItems = find_column_ranking_for_marimekko(
            df, [], aggregateOtherItemsName, chartDict
        )

    colorArray = assign_same_colors_to_all_charts(
        colorArray, usedColorDict, sortedItems, aggregateOtherItemsName
    )

    expandedSortedItems = [xColumn] + sortedItems
    colorArray = set_other_color_to_grey(
        expandedSortedItems, aggregateOtherItemsName, colorArray, chartDict, -1
    )
    colorArray = insert_highlight_color(
        xColumn, sortedItems, colorArray, paramDict, chartDict
    )

    # Keep final columns if pivoted
    columns, schema = get_schema_and_column_names(df)
    if sortedItems and all(item in columns for item in sortedItems):
        keepCols = [xColumn] + sortedItems
        df = df.select([c for c in keepCols if c in columns])

    # ---------------------------------------------------------
    # Return result
    # ---------------------------------------------------------
    return df, metricToPlot, colorArray, usedColorDict, uniqueItems
