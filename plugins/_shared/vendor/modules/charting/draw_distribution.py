from __future__ import annotations

import datetime as dt

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from modules.charting.chart_helpers import adjust_annotation_positions
from modules.charting.chart_primitives import (
    check_if_plan_or_py,
    get_color_dictionary,
    get_color_sequence,
)
from modules.charting.polars_helpers import to_lists
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.helpers import (
    check_if_periods_in_columns,
    place_other_rank_at_end,
    unique,
)
from modules.utilities.utils import ensure_lazyframe


def order_and_categorize_period_column_polars(
    df: pl.DataFrame | pl.LazyFrame,
    cleanedPeriodOrder: list[str],
) -> pl.LazyFrame:
    """Categorize and sort ``df``'s period column without collecting."""

    return order_and_categorize_period_column(df, cleanedPeriodOrder)


def order_and_categorize_period_column(df, cleanedPeriodOrder):
    """Return a ``LazyFrame`` sorted by ``cleanedPeriodOrder`` with a categorical
    period column."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]

    lf = ensure_lazyframe(df)
    cat_map = {val: idx for idx, val in enumerate(cleanedPeriodOrder)}

    return (
        lf.with_columns(pl.col(periodName).cast(pl.Utf8))
        .with_columns(pl.col(periodName).replace(cat_map).alias(f"{periodName}_order"))
        .sort(f"{periodName}_order")
        .drop(f"{periodName}_order")
        .with_columns(pl.col(periodName).cast(pl.Categorical))
    )


def draw_histogram_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    metric: str,
    colChoice: bool,
    paramDict: dict,
    chartDict: dict,
    uniqueItems: list[str],
) -> tuple["go.Figure", int, list[str], pl.LazyFrame]:
    """Draw histogram chart collecting data only once.

    Parameters
    ----------
    dfCopy:
        Input data as ``DataFrame`` or ``LazyFrame``.
    chosenDimension:
        Column used for grouping when ``colChoice`` is ``True``.
    metric:
        Name of the numeric column to plot.
    colChoice:
        Whether to facet by ``chosenDimension``.
    paramDict:
        Dictionary of additional chart parameters.
    chartDict:
        Chart configuration dictionary.
    uniqueItems:
        List of unique ``chosenDimension`` values.

    Returns
    -------
    tuple
        ``(figure, numberOfItemsInCol, cleanedPeriodOrder, lf)`` where ``lf``
        is the lazy representation of the input.
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    cumulativeHistogram = namingParams["cumulativeHistogram"]
    logXAxis = namingParams["logXAxis"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if logXAxis in chartDict:
        logXAxis = chartDict[logXAxis]
    else:
        logXAxis = notMetConditionValue

    # Convert to a lazy frame and drop nulls only once at the start
    lf = ensure_lazyframe(dfCopy).drop_nulls(subset=[metric])
    colorDict = get_color_dictionary(chartDict)
    periodOrder = chartDict[selectedPeriods]
    isExpectedData, planName = check_if_plan_or_py(periodOrder)
    colorSequenceArray, lineWidth = get_color_sequence(lf, paramDict, chartDict)
    cleanedPeriodOrder = []
    for period in periodOrder:
        lf, period = check_if_periods_in_columns(lf, period)
        cleanedPeriodOrder.append(period)
    lf = order_and_categorize_period_column(lf, cleanedPeriodOrder)
    marginal = None
    opacity = 0.8
    barnorm = "fraction"
    histnorm = "probability density"
    cumulative = chartDict[cumulativeHistogram]
    facet_col_wrap = 1
    if colChoice:
        lf = place_other_rank_at_end(
            lf, chosenDimension, uniqueItems, cleanedPeriodOrder
        )

    cols = [metric, periodName]
    if colChoice:
        cols.append(chosenDimension)

    # Collect required columns once for plotting
    df_eager = lf.select(pl.col(cols)).collect(engine="streaming")
    out = lf

    numberOfItemsInCol = df_eager[chosenDimension].n_unique() if colChoice else 1

    collected_lists = to_lists(df_eager, cols)

    if not colChoice:
        fig = px.histogram(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            opacity=opacity,
            marginal=marginal,
            histnorm=histnorm,
            barnorm=barnorm,
            cumulative=cumulative,
            log_x=logXAxis,
        ).update_layout(barmode="overlay")
    else:
        fig = px.histogram(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            opacity=opacity,
            marginal=marginal,
            histnorm=histnorm,
            barnorm=barnorm,
            cumulative=cumulative,
            facet_col=collected_lists[chosenDimension],
            facet_col_wrap=facet_col_wrap,
            log_x=logXAxis,
        ).update_layout(barmode="overlay")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    adjust_annotation_positions(fig, numberOfItemsInCol)
    fig.update_annotations(font_size=fontSize)
    return fig, numberOfItemsInCol, cleanedPeriodOrder, out


def draw_boxplot_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    metric: str,
    colChoice: bool,
    paramDict: dict,
    chartDict: dict,
    uniqueItems: list[str],
) -> tuple["go.Figure", int, list[str], pl.LazyFrame]:
    """Draw price distribution chart collecting data only once."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    showOutliers = namingParams["showOutliers"]
    logXAxis = chartDict.get(
        namingParams["logXAxis"], namingParams["notMetConditionValue"]
    )

    lf = ensure_lazyframe(dfCopy).drop_nulls(subset=[metric])
    periodOrder = chartDict[selectedPeriods]
    _isExpectedData, _planName = check_if_plan_or_py(periodOrder)
    colorSequenceArray, _lineWidth = get_color_sequence(lf, paramDict, chartDict)

    cleanedPeriodOrder: list[str] = []
    for period in periodOrder:
        lf, period = check_if_periods_in_columns(lf, period)
        cleanedPeriodOrder.append(period)
    lf = order_and_categorize_period_column(lf, cleanedPeriodOrder)

    if colChoice:
        lf = place_other_rank_at_end(
            lf, chosenDimension, uniqueItems, cleanedPeriodOrder
        )

    points = "outliers" if chartDict.get(showOutliers) else False

    cols = [metric, periodName]
    if colChoice:
        cols.append(chosenDimension)

    df_eager = lf.select(pl.col(cols)).collect(engine="streaming")
    out = lf

    numberOfItemsInCol = df_eager[chosenDimension].n_unique() if colChoice else 1
    collected_lists = to_lists(df_eager, cols)

    if colChoice:
        fig = px.box(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            points=points,
            notched=True,
            orientation="h",
            category_orders={chosenDimension: uniqueItems},
            facet_col=collected_lists[chosenDimension],
            facet_col_wrap=1,
            log_x=logXAxis,
        ).update_layout()
    else:
        fig = px.box(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            points=points,
            notched=True,
            orientation="h",
            log_x=logXAxis,
        ).update_layout()

    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    adjust_annotation_positions(fig, numberOfItemsInCol)
    fig.update_annotations(font_size=fontSize)

    return fig, numberOfItemsInCol, cleanedPeriodOrder, out


def draw_stripplot_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    metric: str,
    colChoice: bool,
    paramDict: dict,
    chartDict: dict,
    uniqueItems: list[str],
) -> tuple["go.Figure", int, list[str], pl.LazyFrame]:
    """Draw price distribution chart collecting data only once."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    logXAxis = chartDict.get(
        namingParams["logXAxis"], namingParams["notMetConditionValue"]
    )

    lf = ensure_lazyframe(dfCopy).drop_nulls(subset=[metric])
    periodOrder = chartDict[selectedPeriods]
    _isExpectedData, _planName = check_if_plan_or_py(periodOrder)
    colorSequenceArray, _lineWidth = get_color_sequence(lf, paramDict, chartDict)

    cleanedPeriodOrder: list[str] = []
    for period in periodOrder:
        lf, period = check_if_periods_in_columns(lf, period)
        cleanedPeriodOrder.append(period)
    lf = order_and_categorize_period_column(lf, cleanedPeriodOrder)

    if colChoice:
        lf = place_other_rank_at_end(
            lf, chosenDimension, uniqueItems, cleanedPeriodOrder
        )

    cols = [metric, periodName]
    if colChoice:
        cols.append(chosenDimension)

    df_eager = lf.select(pl.col(cols)).collect(engine="streaming")
    out = lf

    numberOfItemsInCol = df_eager[chosenDimension].n_unique() if colChoice else 1
    collected_lists = to_lists(df_eager, cols)

    orientation = "h"
    facet_col_wrap = 1
    if colChoice:
        fig = px.strip(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            orientation=orientation,
            log_x=logXAxis,
            facet_col=collected_lists[chosenDimension],
            facet_col_wrap=facet_col_wrap,
        ).update_layout()
    else:
        fig = px.strip(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            orientation=orientation,
            log_x=logXAxis,
        ).update_layout()

    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    adjust_annotation_positions(fig, numberOfItemsInCol)
    fig.update_annotations(font_size=fontSize)
    return fig, numberOfItemsInCol, cleanedPeriodOrder, out


def draw_ecdf_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    metric: str,
    colChoice: bool,
    paramDict: dict,
    chartDict: dict,
    uniqueItems: list[str],
) -> tuple["go.Figure", int, list[str], pl.LazyFrame]:
    """Draw price distribution chart collecting data only once."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    fontSize = configParams[namingParams["fontSizeText"]]
    font = configParams[namingParams["fontChoice"]]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    reversedEcdf = namingParams["reversedEcdf"]
    reversedMode = namingParams["reversedMode"]
    standardMode = namingParams["standardMode"]
    logXAxis = namingParams["logXAxis"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if logXAxis in chartDict:
        logXAxis = chartDict[logXAxis]
    else:
        logXAxis = notMetConditionValue

    lf = ensure_lazyframe(dfCopy).drop_nulls(subset=[metric])

    colorDict = get_color_dictionary(chartDict)
    periodOrder = chartDict[selectedPeriods]
    _isExpectedData, _planName = check_if_plan_or_py(periodOrder)
    colorSequenceArray, _lineWidth = get_color_sequence(lf, paramDict, chartDict)

    cleanedPeriodOrder: list[str] = []
    for period in periodOrder:
        lf, period = check_if_periods_in_columns(lf, period)
        cleanedPeriodOrder.append(period)
    lf = order_and_categorize_period_column(lf, cleanedPeriodOrder)

    ecdfmode = reversedMode if chartDict[reversedEcdf] else standardMode
    facet_col_wrap = 1

    if colChoice:
        lf = place_other_rank_at_end(
            lf, chosenDimension, uniqueItems, cleanedPeriodOrder
        )

    cols = [metric, periodName]
    if colChoice:
        cols.append(chosenDimension)

    df_eager = lf.select(pl.col(cols)).collect(engine="streaming")
    out = lf

    numberOfItemsInCol = df_eager[chosenDimension].n_unique() if colChoice else 1
    collected_lists = to_lists(df_eager, cols)

    if colChoice:
        fig = px.ecdf(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            marginal=None,
            ecdfnorm="percent",
            ecdfmode=ecdfmode,
            log_x=logXAxis,
            facet_col=collected_lists[chosenDimension],
            facet_col_wrap=facet_col_wrap,
        )
    else:
        fig = px.ecdf(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            marginal=None,
            ecdfnorm="percent",
            ecdfmode=ecdfmode,
            log_x=logXAxis,
        )
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    adjust_annotation_positions(fig, numberOfItemsInCol)
    fig.update_annotations(font_size=fontSize)
    return fig, numberOfItemsInCol, cleanedPeriodOrder, out


def draw_kernel_density_chart(
    dfCopy: pl.DataFrame | pl.LazyFrame,
    chosenDimension: str,
    metric: str,
    colChoice: bool,
    paramDict: dict,
    chartDict: dict,
    uniqueItems: list[str],
) -> tuple["go.Figure", int, list[str], pl.LazyFrame]:
    """Draw price distribution chart collecting data only once."""

    namingParams = get_naming_params()
    configParams = get_config_params()
    font = configParams[namingParams["fontChoice"]]
    fontSize = configParams[namingParams["fontSizeText"]]
    periodName = namingParams["periodName"]
    selectedPeriods = namingParams["selectedPeriods"]
    logXAxis = namingParams["logXAxis"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    if logXAxis in chartDict:
        logXAxis = chartDict[logXAxis]
    else:
        logXAxis = notMetConditionValue
    lf = ensure_lazyframe(dfCopy).drop_nulls(subset=[metric])
    periodOrder = chartDict[selectedPeriods]
    _is_expected, _plan_name = check_if_plan_or_py(periodOrder)
    colorSequenceArray, _lineWidth = get_color_sequence(lf, paramDict, chartDict)
    cleanedPeriodOrder = []
    for period in periodOrder:
        lf, period = check_if_periods_in_columns(lf, period)
        cleanedPeriodOrder.append(period)
    lf = order_and_categorize_period_column(lf, cleanedPeriodOrder)
    box = False
    points = False
    facet_col_wrap = 1
    if colChoice:
        lf = place_other_rank_at_end(
            lf, chosenDimension, uniqueItems, cleanedPeriodOrder
        )

    cols = [metric, periodName]
    if colChoice:
        cols.append(chosenDimension)

    df_eager = lf.select(pl.col(cols)).collect(engine="streaming")
    out = lf

    numberOfItemsInCol = df_eager[chosenDimension].n_unique() if colChoice else 1
    collected_lists = to_lists(df_eager, cols)

    if not colChoice:
        fig = px.violin(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            orientation="h",
            violinmode="overlay",
            box=box,
            points=points,
            log_x=logXAxis,
        ).update_traces(side="positive", width=1.9)
    else:
        fig = px.violin(
            x=collected_lists[metric],
            color=collected_lists[periodName],
            # y=collected[chosenDimension].to_list(),
            color_discrete_sequence=colorSequenceArray,
            labels={"x": metric},
            orientation="h",
            violinmode="overlay",
            box=box,
            points=points,
            log_x=logXAxis,
            facet_col=collected_lists[chosenDimension],
            facet_col_wrap=facet_col_wrap,
        ).update_traces(side="positive", width=1.9)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    adjust_annotation_positions(fig, numberOfItemsInCol)
    fig.update_annotations(font_size=fontSize)
    return fig, numberOfItemsInCol, cleanedPeriodOrder, out
