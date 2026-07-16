import logging
import numpy as np
import polars as pl
from modules.utilities.ui_notifier import ui as notifier

from modules.charting.chart_primitives import get_color_dictionary
from modules.charting.polars_helpers import unique_values_lazy
from modules.charting.upset_helpers import build_upset_matrix
from modules.data.common_data_utils import (
    add_yearly_average,
    check_value_column_exist,
    clean_column_labels_after_flatten_df,
    concat_df_to_dfMerged,
    get_growth_rate,
    get_month_name,
    get_number_of_uniques,
    insert_unit_and_volume_price_column,
    join_unique_metric_to_df,
    multiply_percent_metrics_by_hundred,
    order_dataframe_by_month,
    pivot_lazy,
    show_only_largest,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_variance_aggregation_params,
)
from modules.utilities.helpers import (
    duplicate_dataframe,
    flatten_cols_polars,
    unique,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_schema_and_column_names,
)


def aggregate_values_in_distribution_plots(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    element: str,
    valueCols: list[str],
    chartDict: dict,
) -> pl.LazyFrame:
    """Return aggregated LazyFrame for distribution charts."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]

    distributionDimension = chartDict[xAxisDimension]

    lf = ensure_lazyframe(duplicate_dataframe(dfCopy))

    group_cols = [periodName]
    if element != nothingFilteredName:
        group_cols.append(element)
    if (
        distributionDimension != nothingFilteredName
        and distributionDimension not in group_cols
    ):
        group_cols.append(distributionDimension)

    if distributionDimension != nothingFilteredName:
        valueCols = check_value_column_exist(lf, valueCols)
        lf = lf.group_by(group_cols).agg([pl.col(col).sum() for col in valueCols])

    lf = insert_unit_and_volume_price_column(lf)

    return ensure_lazyframe(lf)


def prepare_sum_dataframe_for_bubble_plot(
    dfCopy, valueCols, periodOrder, toPlotPeriod, chartDict, paramDict
):
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    totalName = namingParams["totalName"]
    plotTotalBubble = namingParams["plotTotalBubble"]
    if plotTotalBubble in chartDict and chartDict[plotTotalBubble]:
        df = ensure_lazyframe(duplicate_dataframe(dfCopy))
        valueCols = check_value_column_exist(df, valueCols)
        dfSum = df.group_by(periodName).agg(
            [pl.col(col).sum().alias(col) for col in valueCols]
        )
        dfSum = insert_unit_and_volume_price_column(dfSum)
        try:
            from modules.utilities.config import get_metric_array_params
        except Exception as e:  # pragma: no cover - optional import
            logging.exception(e)
            notifier.error(
                "Something went wrong while importing misc_charts_data_prep."
            )
            metricArrayParams = {}
        else:
            metricArrayParams = get_metric_array_params()
        percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
        existing_cols, _ = get_schema_and_column_names(dfSum)
        percent_cols = [c for c in percentMetricsArray if c in existing_cols]
        if percent_cols:
            dfSum = dfSum.with_columns(
                [pl.col(c).mul(100).round(1).alias(c) for c in percent_cols]
            )
        dfSum = dfSum.with_columns(pl.lit(totalName).alias(totalName))
        dfSum = get_growth_rate(
            dfSum, totalName, periodOrder, paramDict, chartDict, False
        )
        dfSum = dfSum.filter(pl.col(periodName) == toPlotPeriod)
    else:
        dfSum = pl.LazyFrame()
    return dfSum


def color_pareto_classes(
    df: pl.LazyFrame,
    metric: str,
    chartDict: dict,
    paramDict: dict,
    colorName: str,
    ratioName: str,
    className: str,
) -> tuple[pl.LazyFrame, dict]:
    """Return LazyFrame with Pareto class colors and mapping."""
    classColorDict: dict[str, dict[str, str]] = {metric: {}}
    namingParams = get_naming_params()
    colorpalette = namingParams["colorpalette"]
    aClassName = namingParams["aClassName"]
    bClassName = namingParams["bClassName"]
    cClassName = namingParams["cClassName"]
    lossClassName = namingParams["lossClassName"]
    negativeClassName = namingParams["negativeClassName"]
    marginName = namingParams["marginName"]
    colorDict = get_color_dictionary(chartDict)
    colorArray = list(colorDict[chartDict[colorpalette]])
    while len(colorArray) < 4:
        colorArray.append(colorArray[-1] if colorArray else "#818284")
    classColorArray = {
        aClassName: colorArray[0],
        bClassName: colorArray[3],
        cClassName: colorArray[1],
    }
    classRules = [(0.80, aClassName), (0.95, bClassName), (200, cClassName)]
    df = df.lazy().with_columns(
        pl.lit(None).cast(pl.Utf8).alias(colorName),
        pl.lit(None).cast(pl.Utf8).alias(className),
    )

    classColorDict[metric] = {}

    negative_expr = pl.col(metric) < 0
    color_expr = pl.when(negative_expr).then(pl.lit(colorDict["redColor"]))
    class_expr = pl.when(negative_expr).then(
        pl.lit(lossClassName if metric == marginName else negativeClassName)
    )
    classColorDict[metric][
        lossClassName if metric == marginName else negativeClassName
    ] = colorDict["redColor"]

    non_negative_metric = pl.col(metric) >= 0
    for limit, cls_name in classRules:
        condition = (pl.col(ratioName) <= limit) & non_negative_metric
        color_expr = color_expr.when(condition).then(pl.lit(classColorArray[cls_name]))
        class_expr = class_expr.when(condition).then(pl.lit(cls_name))
        classColorDict[metric][cls_name] = classColorArray[cls_name]

    color_expr = color_expr.otherwise(pl.col(colorName))
    class_expr = class_expr.otherwise(pl.col(className))

    df = df.with_columns(color_expr.alias(colorName), class_expr.alias(className))

    color_list = unique_values_lazy(colorName, df)

    # Keep the LazyFrame lazy; caller will collect when needed
    return df, classColorDict, color_list


def prepare_data_for_pareto(
    dfCopy,
    period,
    metric,
    chartDict,
    paramDict,
    colorListDict,
    classColorDict,
    count,
) -> tuple[pl.LazyFrame, list[str], dict, str, str]:
    """Prepare Pareto chart data using Polars ``LazyFrame`` operations."""

    namingParams = get_naming_params()

    ratioName = namingParams["ratioName"]
    countName = namingParams["countName"]
    countRank = namingParams["countRank"]
    colorName = namingParams["colorName"]
    className = namingParams["className"]
    countColumn = namingParams["countColumn"]
    nothingThereString = namingParams["nothingThereString"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    hyphenName = namingParams["hyphenName"]

    df = ensure_lazyframe(duplicate_dataframe(dfCopy))

    column = chartDict[countColumn]
    if (
        aggregateUniquesByDimension in chartDict
        and chartDict[aggregateUniquesByDimension]
    ):
        column = chartDict[aggregateUniquesDimension]

    df = df.with_columns(pl.col(column).cast(pl.Utf8)).filter(
        pl.col(column) != nothingThereString
    )

    if count != 0:
        colorName, ratioName, countRank, className = (
            colorName + hyphenName + metric,
            ratioName + hyphenName + metric,
            countRank + hyphenName + metric,
            className + hyphenName + metric,
        )

    if metric != countName:
        grouped = (
            df.group_by(column)
            .agg(pl.col(metric).sum().alias(metric))
            .sort(metric, descending=True)
            .with_columns(pl.col(metric).cum_sum().alias("_cs"))
            .with_columns((pl.col("_cs") / pl.col(metric).sum()).alias(ratioName))
            .drop("_cs")
            .sort([metric, ratioName], descending=[False, True])
        )
    else:
        grouped = (
            df.group_by(column)
            .agg(pl.len().alias(countName))
            .sort(countName, descending=True)
            .with_columns(pl.col(countName).cum_sum().alias("_cs"))
            .with_columns((pl.col("_cs") / pl.col(countName).sum()).alias(ratioName))
            .drop("_cs")
        )

    grouped = (
        grouped.with_columns(pl.col(ratioName).round(3))
        .with_row_index("__idx")
        .with_columns((pl.len() - pl.col("__idx")).alias(countRank))
        .drop("__idx")
    )

    grouped, color_mapping, color_list = color_pareto_classes(
        grouped,
        metric,
        chartDict,
        paramDict,
        colorName,
        ratioName,
        className,
    )
    classColorDict.update(color_mapping)

    return grouped, color_list, classColorDict, metric, ratioName


def prepare_data_for_venn_plot(df, yColumn, xColumn, uniqueItems):
    """Return mapping of ``yColumn`` values to unique ``xColumn`` sets."""

    get_naming_params()  # trigger config initialization if needed
    out = (
        ensure_lazyframe(df)
        .select([yColumn, xColumn])
        .filter(pl.col(yColumn).is_in(uniqueItems))
        .unique()
        .group_by(yColumn)
        .agg(pl.col(xColumn).unique())
        .collect(engine="streaming")
    )

    setDict = {row[yColumn]: set(row[xColumn]) for row in out.rows(named=True)}
    for element in uniqueItems:
        setDict.setdefault(element, set())
    return setDict


def prepare_data_for_upset_plot(
    dfCopy: pl.LazyFrame | pl.DataFrame,
    yColumn: str,
    xColumn: str,
    period: str,
    uniqueItems: list[str],
) -> pl.LazyFrame:
    """Return a lazy boolean membership matrix for UpSet charts."""
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    nothingThereString = namingParams["nothingThereString"]

    if not xColumn or not uniqueItems:
        return pl.LazyFrame()

    lf = (
        ensure_lazyframe(duplicate_dataframe(dfCopy))
        .filter(pl.col(periodName) == period)
        .filter(pl.col(yColumn) != nothingThereString)
    )

    sets = sorted(unique(uniqueItems))
    mapping = lf.select(pl.col(xColumn).alias("Name"), pl.col(yColumn).alias("set"))
    membership = build_upset_matrix(mapping, sets)

    dropCols = [yColumn, xColumn, periodName]
    return ensure_lazyframe(
        membership.with_row_index(name="_idx")
        .join(lf.drop(dropCols).with_row_index(name="_idx"), on="_idx", how="left")
        .drop("_idx")
    )


def calculate_difference_in_percent(
    df: pl.LazyFrame, periodZero: str, periodOne: str
) -> pl.LazyFrame:
    """
    Polars-lazy equivalent of calculate_difference_in_percent.

    differenceInPercent = NaN initially
    if both periodZero & periodOne exist:
       - where periodZero != 0 => round((periodOne - periodZero)/periodZero * 100, 0)
       - where both periodOne < 0 & periodZero < 0 => flip sign
    """

    namingParams = get_naming_params()
    differenceInPercent = namingParams["differenceInPercent"]

    # 1) Initialize differenceInPercent to None (Polars uses None instead of np.nan)
    df = df.with_columns(pl.lit(None).alias(differenceInPercent))

    # 2) Check if columns exist (small metadata collect for a lazy DF):
    columns, schema = get_schema_and_column_names(df)
    if periodZero in columns and periodOne in columns:
        # (a) Where periodZero != 0 => compute difference, else keep existing
        df = df.with_columns(
            pl.when(pl.col(periodZero) != 0)
            .then(
                (
                    (pl.col(periodOne) - pl.col(periodZero)) / pl.col(periodZero) * 100
                ).round(0)
            )
            .otherwise(pl.col(differenceInPercent))
            .alias(differenceInPercent)
        )

        # (b) Where (periodOne < 0) & (periodZero < 0), flip sign
        df = df.with_columns(
            pl.when((pl.col(periodOne) < 0) & (pl.col(periodZero) < 0))
            .then(pl.col(differenceInPercent) * -1)
            .otherwise(pl.col(differenceInPercent))
            .alias(differenceInPercent)
        )

    return df


def prepare_data_for_multitier_column_plot(
    dfCopy, xColumn, metric, chartDict, paramDict
):
    """Return a ``LazyFrame`` for multi-tier column charts without eager calls."""
    namingParams = get_naming_params()
    configParams = get_config_params()
    monthDict = configParams[namingParams["monthDict"]]
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    workColumn = namingParams["workColumn"]
    differenceInValue = namingParams["differenceInValue"]
    differenceInPercent = namingParams["differenceInPercent"]
    selectedPeriods = namingParams["selectedPeriods"]
    colorName = namingParams["colorName"]
    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    labelName = namingParams["labelName"]
    periodChoice = namingParams["periodChoice"]
    weekName = namingParams["weekName"]
    numberOfTop = namingParams["numberOfTop"]
    nothingThereString = namingParams["nothingThereString"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    averageName = namingParams["averageName"]
    filterDates = namingParams["filterDates"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    reverseColorMetricsArray = [discountName, indirectCostsName, cogsName]
    periodOrder = chartDict[selectedPeriods]
    keepCols = [metric, dateName, periodName]
    metricsToPlot = [metric]
    df = ensure_lazyframe(duplicate_dataframe(dfCopy))
    df = get_month_name(df)
    df = insert_unit_and_volume_price_column(df)
    df = df.select(keepCols)
    group_byCols = [dateName, periodName]
    df = df.group_by(group_byCols).agg([pl.col(col).sum() for col in metricsToPlot])
    df = pivot_lazy(
        lf=df,
        index_col=dateName,
        pivot_col=periodName,
        value_col=metric,
        agg_func="sum",
    )
    df = flatten_cols_polars(df, "")
    df, _ = clean_column_labels_after_flatten_df(df, metricsToPlot)
    cols_after_pivot, _ = get_schema_and_column_names(df)
    yArray: list[str] = []
    if filterDates in chartDict and chartDict[filterDates]:
        if fcName in cols_after_pivot:
            for element in [acName, plName, fcName]:
                if element in cols_after_pivot:
                    yArray.append(element)
        else:
            for element in [acName, plName]:
                if element in cols_after_pivot:
                    yArray.append(element)
    else:
        for element in [acName, pyName]:
            if element in cols_after_pivot:
                yArray.append(element)
    group_byCols = [dateName]
    df = df.group_by(group_byCols).agg([pl.col(col).sum() for col in yArray])
    df = add_yearly_average(df, yArray, chartDict)
    df = ensure_lazyframe(df)
    columns, schema = get_schema_and_column_names(df)
    if len(yArray) > 1:
        df = df.with_columns(
            (pl.col(yArray[0]) - pl.col(yArray[1])).alias(differenceInValue)
        )
        color_expr = pl.when(pl.col(yArray[1]) > pl.col(yArray[0]))
        if metric not in reverseColorMetricsArray:
            color_expr = color_expr.then(pl.lit(1)).otherwise(pl.lit(0))
        else:
            color_expr = color_expr.then(pl.lit(0)).otherwise(pl.lit(1))
        df = df.with_columns(color_expr.alias(colorName))
    else:
        df = df.with_columns(
            [pl.lit(None).alias(differenceInValue), pl.lit(0).alias(colorName)]
        )
    if yArray:
        df = df.with_columns(
            [
                pl.when(pl.col(col).is_null() | pl.col(col).is_nan())
                .then(pl.lit(0))
                .otherwise(pl.col(col))
                .alias(col)
                for col in yArray
            ]
        )
    if len(yArray) > 1:
        df = calculate_difference_in_percent(df, yArray[1], yArray[0])
    else:
        df = df.with_columns(pl.lit(None).alias(differenceInPercent))
    if (
        compareScenariosOrPeriods in chartDict
        and chartDict[compareScenariosOrPeriods] == compareScenarios
    ):
        if fcName in columns:
            df = df.with_columns(
                pl.when(pl.col(fcName) != 0)
                .then(pl.col(fcName) - pl.col(plName))
                .otherwise(pl.col(differenceInValue))
                .alias(differenceInValue)
            )
            df = df.with_columns(
                pl.when((pl.col(fcName) != 0) & (pl.col(differenceInValue) >= 0))
                .then(pl.lit(0))
                .otherwise(pl.col(colorName))
                .alias(colorName)
            )
            df = df.with_columns(
                pl.when((pl.col(fcName) != 0) & (pl.col(differenceInValue) < 0))
                .then(pl.lit(1))
                .otherwise(pl.col(colorName))
                .alias(colorName)
            )
            df = df.with_columns(
                pl.when((pl.col(fcName) != 0) & (pl.col(differenceInValue) != 0))
                .then(((pl.col(differenceInValue) / pl.col(plName)) * 100).round(0))
                .otherwise(pl.col(differenceInPercent))
                .alias(differenceInPercent)
            )
    df = order_dataframe_by_month(df, paramDict, False, yArray)
    return ensure_lazyframe(df)


def create_color_column(
    df: pl.LazyFrame,
    metric: str,
    periodOrder: list[str],
    chosenChart: str,
    paramDict: dict,
    chartDict: dict,
) -> pl.LazyFrame:
    """Create the color column using Polars."""

    # -- 1) Get naming params & read needed config
    namingParams = get_naming_params()
    configParams = get_config_params()
    varianceAggregationParams = get_variance_aggregation_params()

    cogsAggregationArray = varianceAggregationParams[
        namingParams["cogsAggregationArray"]
    ]
    discountsAggregationArray = varianceAggregationParams[
        namingParams["discountsAggregationArray"]
    ]
    periodsArray = configParams["periodsArray"]

    discountName = namingParams["discountName"]
    indirectCostsName = namingParams["indirectCostsName"]
    cogsName = namingParams["cogsName"]
    colorName = namingParams["colorName"]
    multitierBarChart = namingParams["multitierBarChart"]
    verticalWaterfallChart = namingParams["verticalWaterfallChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    variancePercentChangeName = namingParams["variancePercentChangeName"]
    separatorString = namingParams["separatorString"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    varianceAggregation = namingParams["varianceAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation = namingParams["netOfDiscountAggregation"]
    marginName = namingParams["marginName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    differenceInPercent = namingParams["differenceInPercent"]
    varianceAmountName = namingParams["varianceAmountName"]
    varianceTypeName = namingParams["varianceTypeName"]
    mainDimension = namingParams["mainDimension"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    discountVariance = namingParams["discountVariance"]
    differenceInValue = namingParams["differenceInValue"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]

    acName = namingParams["acName"]
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]

    reverseColorMetricsArray = [discountName, indirectCostsName, cogsName]

    # Grab current list of columns if you need them for "if col in columns" checks.
    # This triggers a small metadata collect for a LazyFrame, which is often OK.
    columns, schema = get_schema_and_column_names(df)

    # --------------------------------------------------------------------------
    # 2) Start replicating your logic:
    #    if chosenChart in [multitierBarChart, horizontalWaterfallChart]: ...
    # --------------------------------------------------------------------------
    if chosenChart in [multitierBarChart, horizontalWaterfallChart]:
        # (a) If the metric is NOT in the reversed array
        if metric not in reverseColorMetricsArray:
            # i) If 3 periods & fcName in columns
            if len(periodOrder) == 3 and fcName in columns:
                # colorName = 1 if col(periodOrder[0]) > col(periodOrder[1]) + col(periodOrder[2]) else 0
                df = df.with_columns(
                    pl.when(
                        pl.col(periodOrder[0])
                        > (pl.col(periodOrder[1]) + pl.col(periodOrder[2]))
                    )
                    .then(pl.lit(1))
                    .otherwise(pl.lit(0))
                    .alias(colorName)
                )
            # ii) If we have at least 2 columns in periodOrder
            elif len(periodOrder) >= 2 and (
                periodOrder[0] in columns and periodOrder[1] in columns
            ):
                df = df.with_columns(
                    pl.when(pl.col(periodOrder[0]) > pl.col(periodOrder[1]))
                    .then(pl.lit(1))
                    .otherwise(pl.lit(0))
                    .alias(colorName)
                )
            # iii) If only periodOrder[0] in columns
            elif len(periodOrder) >= 1 and periodOrder[0] in columns:
                df = df.with_columns(pl.lit(1).alias(colorName))
            else:
                df = df.with_columns(pl.lit(0).alias(colorName))

        # (b) If the metric IS in the reversed array
        else:
            if len(periodOrder) == 3 and fcName in columns:
                df = df.with_columns(
                    pl.when(
                        pl.col(periodOrder[0])
                        > (pl.col(periodOrder[1]) + pl.col(periodOrder[2]))
                    )
                    .then(pl.lit(0))
                    .otherwise(pl.lit(1))
                    .alias(colorName)
                )
            elif len(periodOrder) >= 2 and (
                periodOrder[0] in columns and periodOrder[1] in columns
            ):
                df = df.with_columns(
                    pl.when(pl.col(periodOrder[0]) > pl.col(periodOrder[1]))
                    .then(pl.lit(0))
                    .otherwise(pl.lit(1))
                    .alias(colorName)
                )
            elif len(periodOrder) >= 1 and periodOrder[0] in columns:
                df = df.with_columns(pl.lit(0).alias(colorName))
            else:
                df = df.with_columns(pl.lit(1).alias(colorName))

        # (c) differenceInPercent logic
        if (
            varianceAggregation in chartDict
            and chartDict[varianceAggregation] in [totalVarianceAggregation]
        ) or variancePercentChangeName not in columns:
            # Use a lazy version of calculate_difference_in_percent
            df = calculate_difference_in_percent(df, periodOrder[0], periodOrder[1])
        else:
            # differenceInPercent = np.nan for everyone
            df = df.with_columns(pl.lit(None).alias(differenceInPercent))
            # Then fill only where (df[periodZeroValue] != 0) with rounded variancePercentChangeName
            periodZeroValue = periodOrder[0]
            df = df.with_columns(
                pl.when(pl.col(periodZeroValue) != 0)
                .then(pl.col(variancePercentChangeName).round(0))
                .otherwise(pl.col(differenceInPercent))
                .alias(differenceInPercent)
            )
        # (d) if fcName in columns and we are comparing scenarios
        if fcName in columns:
            if (
                compareScenariosOrPeriods in chartDict
                and chartDict[compareScenariosOrPeriods] == compareScenarios
            ):
                # differenceInValue = (AC + FC) - PL
                df = df.with_columns(
                    (pl.col(acName) + pl.col(fcName) - pl.col(plName)).alias(
                        differenceInValue
                    )
                )
                # differenceInPercent = round(differenceInValue / PL * 100)
                df = df.with_columns(
                    pl.when(pl.col(plName) != 0)
                    .then(((pl.col(differenceInValue) / pl.col(plName)) * 100).round(0))
                    .otherwise(pl.col(differenceInPercent))  # keep old or None
                    .alias(differenceInPercent)
                )

    # --------------------------------------------------------------------------
    # 3) If chosenChart in [verticalWaterfallChart] ...
    # --------------------------------------------------------------------------
    elif chosenChart in [verticalWaterfallChart]:
        if (
            mainDimension not in paramDict
            and chartDict[processingChoice] in [runOneDimensionalAnalysis]
            and not periodOrder
            and chartDict[varianceAggregation]
            not in [totalVarianceAggregation, marginVarianceAggregation]
        ):
            # We replicate your original logic:
            #   periodZeroValue = df[varianceAmountName][0]
            # In polars-lazy, "df[varianceAmountName][0]" is not direct. You might have to collect a small value or handle differently.
            # If you truly want the first row's value from that column, you'll need a small collect:
            local_first_val = (
                df.select(pl.col(varianceAmountName).first()).collect().item()
            )
            # differenceInPercent = np.nan for everyone
            df = df.with_columns(pl.lit(None).alias(differenceInPercent))
            # Then only fill for rows where varianceAmountName != 0
            df = df.with_columns(
                pl.when(
                    (pl.col(varianceAmountName) != 0) & (pl.col(varianceTypeName) != "")
                )
                .then(
                    (
                        (pl.col(varianceAmountName) / pl.lit(local_first_val)) * 100
                    ).round(0)
                )
                .otherwise(pl.col(differenceInPercent))
                .alias(differenceInPercent)
            )
            # colorName = np.where(differenceInPercent > 0, 0, 1)
            df = df.with_columns(
                pl.when(pl.col(differenceInPercent) > 0)
                .then(pl.lit(0))
                .otherwise(pl.lit(1))
                .alias(colorName)
            )

        else:
            # cogs vs discount logic
            if chartDict[varianceAggregation] in cogsAggregationArray:
                periodZeroValue = marginName + separatorString + periodsArray[0]
                periodOneValue = marginName + separatorString + periodsArray[1]
            elif chartDict[varianceAggregation] in discountsAggregationArray:
                periodZeroValue = netOfDiscountName + separatorString + periodsArray[0]
                periodOneValue = netOfDiscountName + separatorString + periodsArray[1]
            else:
                periodZeroValue = amountName + separatorString + periodsArray[0]
                periodOneValue = amountName + separatorString + periodsArray[1]

            # colorName = np.where(periodZeroValue > periodOneValue, 1, 0)
            df = df.with_columns(
                pl.when(pl.col(periodZeroValue) > pl.col(periodOneValue))
                .then(pl.lit(1))
                .otherwise(pl.lit(0))
                .alias(colorName)
            )
            # Then discountVariance override
            df = df.with_columns(
                pl.when(
                    (pl.col(varianceTypeName).is_in([discountVariance]))
                    & (pl.col(periodZeroValue) > pl.col(periodOneValue))
                )
                .then(pl.lit(0))
                .otherwise(pl.col(colorName))
                .alias(colorName)
            )
            df = df.with_columns(
                pl.when(
                    (pl.col(varianceTypeName).is_in([discountVariance]))
                    & (pl.col(periodZeroValue) < pl.col(periodOneValue))
                )
                .then(pl.lit(1))
                .otherwise(pl.col(colorName))
                .alias(colorName)
            )

            # differenceInPercent logic
            if chartDict[varianceAggregation] in [
                totalVarianceAggregation,
                netOfDiscountAggregation,
                marginVarianceAggregation,
            ]:
                df = calculate_difference_in_percent(
                    df, periodZeroValue, periodOneValue
                )
            elif variancePercentChangeName not in columns:
                # differenceInPercent = NaN
                df = df.with_columns(pl.lit(None).alias(differenceInPercent))

                # fill rows: if periodZeroValue != 0 & varianceTypeName != ""
                df = df.with_columns(
                    pl.when(
                        (pl.col(periodZeroValue) != 0)
                        & (pl.col(varianceTypeName) != "")
                    )
                    .then(
                        (
                            (pl.col(varianceAmountName) / pl.col(periodZeroValue)) * 100
                        ).round(0)
                    )
                    .otherwise(pl.col(differenceInPercent))
                    .alias(differenceInPercent)
                )
            else:
                df = df.with_columns(pl.lit(None).alias(differenceInPercent))
                # fill using variancePercentChangeName if periodZeroValue != 0
                df = df.with_columns(
                    pl.when(pl.col(periodZeroValue) != 0)
                    .then(pl.col(variancePercentChangeName).round(0))
                    .otherwise(pl.col(differenceInPercent))
                    .alias(differenceInPercent)
                )
                # Reset colorName if it is 1 and differenceInPercent is positive
                df = df.with_columns(
                    pl.when(
                        (pl.col(colorName) == 1) & (pl.col(differenceInPercent) > 0)
                    )
                    .then(pl.lit(0))
                    .otherwise(pl.col(colorName))
                    .alias(colorName)
                )

    return df


def rename_pivoted_columns_if_single_metric(
    df: pl.LazyFrame, yColumn: str, xColumn: str, metric: str
) -> pl.LazyFrame:
    """
    If pivot_lazy named columns as f"{metric}_{pivot_val}",
    and we only have one metric, rename them to just pivot_val.
    """
    # First, we need the actual pivot values that were used.
    # pivot_lazy partially collects them inside itself, but
    # if you'd like to do it externally:
    #     pivot_values = df.select(pl.col(xColumn).unique()).collect()...
    #
    # Because pivot_lazy's final DF won't have xColumn anymore
    # (it pivoted everything), we might store pivot_values earlier,
    # or do something like the 'checkedPeriodOrder' list to rename.
    #
    # Minimal, safe rename: if columns are like f"{metric}_<pivot>",
    # rename them to just "<pivot>". Avoid relying on an external list.
    columns, _ = get_schema_and_column_names(df)
    prefix = f"{metric}_"
    rename_map = {
        col: col[len(prefix) :]
        for col in columns
        if col.startswith(prefix) and col != prefix
    }

    if rename_map:
        df = df.rename(rename_map)

    return df


def set_reversed_categorical_order(
    df: pl.LazyFrame, yColumn: str, uniqueItems: list, workColumn: str
) -> pl.LazyFrame:
    # 1) Build the reversed_map
    reversed_map = {val: i for i, val in enumerate(uniqueItems[::-1])}

    # 2) Create a small DataFrame containing (category, rank).
    #    Convert it to a LazyFrame for the join.
    rank_df = pl.DataFrame(
        {yColumn: list(reversed_map.keys()), workColumn: list(reversed_map.values())}
    ).lazy()

    # 3) Left-join the main df with rank_df
    df = (
        df.join(rank_df, on=yColumn, how="left")
        # 4) fill any null ranks with a default (len(reversed_map)) if category was not found
        .with_columns(pl.col(workColumn).fill_null(len(reversed_map)))
        # 5) sort by that new rank column
        .sort(workColumn)
    )

    return df


def ensure_period_columns_exist(
    df: pl.LazyFrame, periodOrder: list, paramDict: dict, chartDict: dict
) -> tuple[pl.LazyFrame, list]:
    """
    Checks that each period in periodOrder is actually a column in df.
    If missing, you might create it as 0, etc. Then fill null with 0.
    Returns (df, checkedPeriodOrder) with updated period list
    that definitely exist in df now.
    """
    columns, schema = get_schema_and_column_names(df)
    existing_periods = []
    ops = []
    for period in periodOrder:
        if period not in columns:
            # Add a 0 column
            ops.append(pl.lit(0).alias(period))
        existing_periods.append(period)

    if ops:
        df = df.with_columns(ops)

    # fill nulls with 0 in each period column
    fill_exprs = []
    for period in existing_periods:
        fill_exprs.append(pl.col(period).fill_null(0).alias(period))

    df = df.with_columns(fill_exprs)

    return df, existing_periods


def compute_difference_in_value(
    df: pl.LazyFrame, differenceInValue: str, periodOrder: list
) -> pl.LazyFrame:
    """
    Replicates the logic:
      df[differenceInValue] = df[period2] - df[period1]
    Handling missing columns gracefully, if needed.
    """
    if len(periodOrder) < 2:
        raise ValueError(
            "Multitier bar comparison requires at least two selected periods."
        )
    # You can check columns first:
    columns, schema = get_schema_and_column_names(df)
    firstP, secondP = periodOrder[0], periodOrder[1]

    # Because we forced them to exist in ensure_period_columns_exist,
    # we can rely on them now:
    df = df.with_columns((pl.col(secondP) - pl.col(firstP)).alias(differenceInValue))

    return df


def prepare_data_for_multitier_bar_plot(
    dfCopy: pl.LazyFrame,
    yColumn: str,
    xColumn: str,
    metric: str,
    valueCols: list,
    chartDict: dict,
    paramDict: dict,
    axis: str,
) -> tuple[pl.LazyFrame, list, dict]:
    """Prepare data for a multi-tier bar plot using Polars and ``pivot_lazy``."""
    # -- 1. Retrieve naming/config params
    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    workColumn = namingParams["workColumn"]
    differenceInValue = namingParams["differenceInValue"]
    selectedPeriods = namingParams["selectedPeriods"]
    labelName = namingParams["labelName"]
    weekName = namingParams["weekName"]
    numberOfTop = namingParams["numberOfTop"]
    nothingThereString = namingParams["nothingThereString"]
    chosenChartParam = namingParams["chosenChart"]

    chosenChart = chartDict[chosenChartParam]
    periodOrder = chartDict[selectedPeriods]

    # -- 2. Duplicate df
    df = duplicate_dataframe(dfCopy)

    # -- 3. Get number of unique items if needed (placeholder logic)
    dfCounts, chartDict = get_number_of_uniques(df, yColumn, xColumn, chartDict)

    # -- 4. Possibly limit to "largest" categories
    df, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
        df, yColumn, None, periodName, valueCols, chartDict, paramDict, axis
    )

    # -- 5. Join extra metrics if needed (placeholder logic)
    df = join_unique_metric_to_df(
        df, dfCounts, yColumn, xColumn, aggregateOtherItemsName, chartDict
    )

    # -- 6. Insert custom columns (e.g. unit, volume, price)
    df = insert_unit_and_volume_price_column(df)

    # -- 7. Keep only the relevant columns
    keepCols = [metric, yColumn, xColumn]
    df = df.select(keepCols)

    #    No need for a separate group_by(...).sum() step here, because your
    #    pivot_lazy call below *already* does a group-by on yColumn with
    #    conditional aggregation by xColumn.

    # -- 8. **Pivot** using your existing lazy pivot function
    #    aggregator is "sum" to mimic pivot_table(..., aggfunc="sum").
    df = pivot_lazy(
        lf=df, index_col=yColumn, pivot_col=xColumn, value_col=metric, agg_func="sum"
    )

    # -- 9. (Optional) "Clean" or rename pivoted columns if needed
    #    pivot_lazy will name them like:  f"{value_col}_{pivot_val}"
    #    If you prefer them to be just the pivot_val (e.g. "2022"),
    #    you can rename here:
    df = rename_pivoted_columns_if_single_metric(df, yColumn, xColumn, metric)

    # -- 10. Re-create an order on yColumn if needed
    df = set_reversed_categorical_order(df, yColumn, uniqueItems, workColumn)
    df = df.drop([workColumn])

    # -- 11. Ensure we have columns for each period in periodOrder, fill with 0 if missing
    df, checkedPeriodOrder = ensure_period_columns_exist(
        df, periodOrder, paramDict, chartDict
    )

    # -- 12. Compute the difference in value between the second and first period
    df = compute_difference_in_value(df, differenceInValue, checkedPeriodOrder)

    # -- 13. Create color column
    df = create_color_column(
        df, metric, checkedPeriodOrder, chosenChart, paramDict, chartDict
    )

    # -- 14. Remove rows where yColumn == nothingThereString
    df = df.filter(pl.col(yColumn) != nothingThereString)

    # -- 15. Convert yColumn to string
    df = df.with_columns(pl.col(yColumn).cast(pl.Utf8))

    return ensure_lazyframe(df), uniqueItems, paramDict
