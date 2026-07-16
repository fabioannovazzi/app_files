import copy
import datetime as dt
import logging
import math

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
from modules.utilities.ui_notifier import ui
from modules.utilities.session_context import session_state
from plotly.subplots import make_subplots

from modules.charting.chart_primitives import add_sign_to_labels
from modules.data.common_data_utils import (
    assemble_query_string_elements,
    build_equal_to_query_string_element,
    check_value_column_exist,
    show_only_largest,
)
from modules.llm.confirm_plots import (
    get_comments_from_data,
    get_comments_from_data_fragment,
    get_comments_from_images,
)
from modules.utilities.config import (
    get_config_params,
    get_naming_params,
)
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    clean_chartDict,
    convert_df,
    drop_columns,
    duplicate_dataframe,
    get_image_name_hash,
    get_period_length,
    take_filtered_value_out_of_option_list,
    unique,
)
from modules.utilities.utils import (
    ensure_polars_df,
    get_schema_and_column_names,
    is_valid_lazyframe,
)

try:  # pragma: no cover - fallback for older test stubs
    from modules.utilities.utils import ensure_lazyframe
except Exception as e:  # pragma: no cover
    logging.exception(e)
    ui.error("Something went wrong while importing ensure_lazyframe for chart helpers.")

    def ensure_lazyframe(obj):
        if isinstance(obj, pl.LazyFrame):
            return obj
        if isinstance(obj, pl.DataFrame):
            return obj.lazy()
        return pl.DataFrame(obj).lazy()


def download_chart_dataframe(chartDict, dfCharts, expander):
    namingParams = get_naming_params()
    rowToPlot = namingParams["rowToPlotName"]
    entireDatasetName = namingParams["entireDatasetName"]
    prepareFileForDownload = namingParams["prepareFileForDownload"]
    with expander:
        if chartDict[rowToPlot] != entireDatasetName:
            message = "report row #" + str(chartDict[rowToPlot]) + ""
            chartDict[rowToPlot] = message
            if (
                prepareFileForDownload in chartDict
                and chartDict[prepareFileForDownload]
            ):
                ui.caption(
                    """The charts plot the data of the """
                    + message
                    + """. Click on the link below to download ⬇️ all the data of the plotted row.    
                            """
                )
                csv = convert_df(dfCharts)
                label = ("Press to Download ",)
                download_text_data(csv, label, fileName)
    return None


def get_highlighted_items(
    dfAllPeriodsCopy,
    dfPeriodsCopy,
    valueCols,
    chosenChart,
    chartDict,
    automateDict,
    paramDict,
):
    dfAllPeriodsCopy = ensure_lazyframe(dfAllPeriodsCopy)
    dfPeriodsCopy = ensure_lazyframe(dfPeriodsCopy)
    namingParams = get_naming_params()
    selectDimensionsToPlotKey = namingParams["selectDimensionsToPlot"]
    selectDimensionsToPlotLabel = namingParams["selectDimensionsToPlotLabel"]
    numberOfTopKey = namingParams["numberOfTop"]
    periodName = namingParams["periodName"]
    greysColorpalette = namingParams["greysColorpalette"]
    highlightedDimension = namingParams["highlightedDimension"]
    colorpalette = namingParams["colorpalette"]
    marimekkoChart = namingParams["marimekkoChart"]
    slopeChart = namingParams["slopeChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    timelineChart = namingParams["timelineChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    areaChart = namingParams["areaChart"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    metricsToPlot = namingParams["metricsToPlot"]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    aClassName = namingParams["aClassName"]
    bClassName = namingParams["bClassName"]
    cClassName = namingParams["cClassName"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    selectedDimensionsArray = []
    showHighlightWidget = False
    showTop = True
    if selectDimensionsToPlotKey in chartDict:
        selectedDimensionsArray = chartDict[selectDimensionsToPlotKey]
    dimensionsOK = True
    if chosenChart in [slopeChart, timelineChart, areaChart, stackedColumnChart]:
        if (
            selectDimensionsToPlotKey not in chartDict
            or len(chartDict[selectDimensionsToPlotKey]) == 0
        ):
            dimensionsOK = False
    if chosenChart in [bubbleChart, motionChart]:
        if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
            nothingFilteredName,
            periodName,
        ]:
            dimensionsOK = False
    if dimensionsOK:
        if chosenChart in [vennChart, upsetChart]:
            df = duplicate_dataframe(dfPeriodsCopy)
            chosenDimension = chartDict[xAxisDimension]
            dimension = "X"
            showHighlightWidget = True
        elif len(selectedDimensionsArray) == 1 and chosenChart in [stackedColumnChart]:
            df = duplicate_dataframe(dfAllPeriodsCopy)
            chosenDimension = selectedDimensionsArray[0]
            dimension = "X"
            showHighlightWidget = True
        elif chosenChart in [marimekkoChart]:
            df = duplicate_dataframe(dfPeriodsCopy)
            chosenDimension = chartDict[yAxisDimension]
            dimension = "Y"
            showHighlightWidget = True
        elif chosenChart in [slopeChart, timelineChart, areaChart]:
            if (
                plotSmallMultiplesKey not in chartDict
                or not chartDict[plotSmallMultiplesKey]
            ):
                df = duplicate_dataframe(dfPeriodsCopy)
                if len(selectedDimensionsArray) > 0:
                    chosenDimension = selectedDimensionsArray[0]
                else:
                    chosenDimension = False
                dimension = "X"
                showHighlightWidget = True
        elif chosenChart in [stackedBarChart] and chartDict[yAxisDimension] not in [
            nothingFilteredName,
            notMetConditionValue,
        ]:
            df = duplicate_dataframe(dfPeriodsCopy)
            chosenDimension = chartDict[yAxisDimension]
            dimension = "W"
            showHighlightWidget = True
        elif chosenChart in [bubbleChart, motionChart]:
            if plotSmallMultiplesKey not in chartDict:
                df = duplicate_dataframe(dfPeriodsCopy)
                chosenDimension = chartDict[yAxisDimension]
                dimension = "X"
                showHighlightWidget = True
        elif chosenChart in [scatterChart] and chartDict[yAxisDimension] not in [
            nothingFilteredName,
            periodName,
        ]:
            if plotSmallMultiplesKey not in chartDict and not chartDict[plotAsHeatmap]:
                df = duplicate_dataframe(dfPeriodsCopy)
                chosenDimension = chartDict[yAxisDimension]
                dimension = "Y"
                showHighlightWidget = True
        elif chosenChart in [stackedParetoChart]:
            chosenDimension = ""
            showHighlightWidget = True
            if (
                aggregateUniquesByDimension in chartDict
                and not chartDict[aggregateUniquesByDimension]
            ):
                uniqueItems = [cClassName, bClassName, aClassName]
                showTop = False
            else:
                df = duplicate_dataframe(dfPeriodsCopy)
                chosenDimension = chartDict[smallMultiplesColumn]
                dimension = "X"
        if showHighlightWidget:
            if chosenDimension not in [False, notMetConditionValue]:
                try:
                    # Use the selected dimension as-is; if missing, skip without altering selection
                    cols, _ = get_schema_and_column_names(df)
                    if showTop:
                        numberOfTop = chartDict[dimension][numberOfTopKey]
                        if chosenDimension not in cols:
                            return chartDict
                        dfDiscard, uniqueItems, aggregateOtherItemsName, valueCols = show_only_largest(
                            ensure_polars_df(df),
                            chosenDimension,
                            None,
                            periodName,
                            valueCols,
                            chartDict,
                            paramDict,
                            dimension,
                        )
                    if chosenChart in [scatterChart]:
                        ydim = chartDict[yAxisDimension]
                        if ydim not in cols:
                            return chartDict
                        uniqueItems = ensure_polars_df(df)[ydim].unique().to_list()
                    from modules.layout import set_up_widgets as suw

                    suw.uniqueItems = uniqueItems
                    columnHash = paramDict[namingParams["columnHash"]]
                    chartDict = suw.show_highlighted_items_widget(
                        chartDict, automateDict, columnHash, paramDict
                    )
                except Exception as e:  # nosec B110
                    logging.exception(e)
                    ui.write("highlighted-items widget error:", e)
                    pass
    return chartDict


def _chart_domain_right_edge(fig) -> float:
    layout = fig.to_plotly_json().get("layout", {})
    domain_edges: list[float] = []
    for key, value in layout.items():
        if not str(key).startswith("xaxis") or not isinstance(value, dict):
            continue
        domain = value.get("domain")
        if not isinstance(domain, list | tuple) or len(domain) != 2:
            continue
        try:
            domain_edges.append(float(domain[1]))
        except (TypeError, ValueError):
            continue
    return max(domain_edges) if domain_edges else 1.0


def show_total_percent(fig, df, dfFiltered, period, metricToPlot, chartDict):
    """Annotate ``fig`` with the share of ``metricToPlot`` for ``period``."""

    namingParams = get_naming_params()
    periodName = namingParams["periodName"]
    valueName = namingParams["valueName"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]

    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        return fig

    lf_filtered = ensure_lazyframe(dfFiltered)
    lf_full = ensure_lazyframe(df)
    percentShown = 100
    columns, schema = get_schema_and_column_names(lf_filtered)
    if valueName in columns:
        metrics_lf = lf_filtered.select(
            pl.col(valueName).sum().alias("totalShown")
        ).join(
            lf_full.filter(pl.col(periodName) == period).select(
                pl.col(metricToPlot).sum().alias("totalPeriod")
            ),
            how="cross",
        )
        metrics = metrics_lf.collect(engine="streaming")

        if metrics.height > 0:
            totalShown = metrics["totalShown"][0]
            totalPeriod = metrics["totalPeriod"][0]
            if totalPeriod != 0:
                percentShown = round(totalShown / totalPeriod * 100)

    chart_right_edge = _chart_domain_right_edge(fig)
    fig.add_annotation(
        text=f"{percentShown}%",
        showarrow=True,
        arrowcolor="black",
        arrowhead=2,
        arrowsize=1,
        arrowwidth=2,
        x=chart_right_edge,
        y=1,
        ax=chart_right_edge,
        ay=0.9,
        xref="paper",
        yref="paper",
        axref="paper",
        ayref="paper",
        align="center",
        yshift=0,
        xshift=0,
    )
    return fig


def check_if_negative_values_in_mekko(
    df: pl.DataFrame | pl.LazyFrame, valueCol: str
) -> tuple[pl.LazyFrame, pl.LazyFrame, str]:
    """Return LazyFrames without negative ``valueCol`` rows and a warning.

    ``valueCol`` is cast to ``Float64`` to avoid type comparison errors.
    """

    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]

    lf = (
        ensure_lazyframe(df)
        .clone()
        .with_columns(pl.col(valueCol).cast(pl.Float64, strict=False))
    )
    dfNegative = ensure_lazyframe(lf.filter(pl.col(valueCol) < 0))
    dfPositive = ensure_lazyframe(lf.filter(pl.col(valueCol) > 0))

    from modules.utilities.utils import get_row_count

    if get_row_count(dfNegative) > 0:
        message = "The following rows have been deleted from the chart above. Mekko charts cannot not plot negative values on the x axis. Try exchanging the axes"
    else:
        message = notMetConditionValue

    return dfPositive, dfNegative, message


def check_if_values_too_close(
    df: pl.DataFrame | pl.LazyFrame,
    chartDict: dict,
    metric: str,
    periodOrder: list[str],
) -> tuple[pl.DataFrame, str]:
    """Flag chart labels that would overlap due to close values."""
    namingParams = get_naming_params()
    minValue = namingParams["minValue"]
    maxValue = namingParams["maxValue"]
    workColumn = namingParams["workColumn"]
    hideLabel = namingParams["hideLabel"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    absolute = namingParams["absolute"]
    labelToHide = namingParams["labelToHide"]
    pricePerUnitName = namingParams["pricePerUnitName"]

    if chartDict[plotValuesAsChoice] == absolute and metric != pricePerUnitName:
        chartFormat = ",.3s"
        hideLabelLimit = 5
    elif chartDict[plotValuesAsChoice] == absolute and metric == pricePerUnitName:
        chartFormat = ",.2s"
        hideLabelLimit = 1
    elif metric == pricePerUnitName:
        chartFormat = ",.1f"
        hideLabelLimit = 1
    else:
        chartFormat = ",.0f"
        hideLabelLimit = 1

    pl_df = ensure_polars_df(df)
    total_max = pl_df[maxValue].sum()

    pl_df = pl_df.with_columns(
        (
            pl.when(pl.col(periodOrder[1]).is_null())
            .then(pl.lit(periodOrder[1]))
            .otherwise(pl.lit(periodOrder[0]))
            .alias(labelToHide)
        ),
        ((pl.col(maxValue) - pl.col(minValue)) / total_max * 100).alias(workColumn),
    )

    pl_df = pl_df.with_columns(
        pl.when((pl.col(periodOrder[0]).is_null()) | (pl.col(periodOrder[1]).is_null()))
        .then(hideLabelLimit)
        .otherwise(pl.col(workColumn))
        .alias(workColumn)
    )

    pl_df = pl_df.with_columns(
        pl.when(pl.col(workColumn) < hideLabelLimit)
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias(hideLabel)
    )

    pl_df = drop_columns(pl_df, [workColumn])
    return pl_df, chartFormat


def exclude_outliers_from_chart(
    df: pl.DataFrame | pl.LazyFrame, chartDict: dict
) -> pl.LazyFrame:
    """Return LazyFrame with outliers removed for the chosen metrics."""

    namingParams = get_naming_params()
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    stdDeviations = namingParams["stdDeviations"]
    chartMetrics = namingParams["chartMetrics"]
    excludeOutliers = namingParams["excludeOutliers"]

    lf = ensure_lazyframe(df)
    if chartDict.get(excludeOutliers):
        if xAxisMetric in chartDict and yAxisMetric in chartDict:
            metrics = [chartDict[yAxisMetric], chartDict[xAxisMetric]]
        elif chartMetrics in chartDict:
            metrics = chartDict[chartMetrics]
        else:
            metrics = [chartDict[xAxisMetric]]

        std_devs = chartDict[stdDeviations]
        columns, _ = get_schema_and_column_names(lf)

        for metric in metrics:
            if metric in columns:
                z_col = f"__z_{metric}"
                lf = (
                    lf.with_columns(
                        (
                            (pl.col(metric) - pl.col(metric).mean())
                            / pl.col(metric).std()
                        ).alias(z_col)
                    )
                    .filter(pl.col(z_col).abs() < std_devs)
                    .drop(z_col)
                )
    return lf


def get_pinhead_outliers(df, chartDict):
    """Return ``df`` with outlier percent markers removed as a ``LazyFrame``.

    The returned lazy frame has the same columns as ``df`` with outlier rows
    replaced by ``None`` for the percentage column.  ``largestArray`` and
    ``smallestArray`` contain the row index, value and color for the filtered
    positive and negative outliers respectively.
    """

    namingParams = get_naming_params()
    differenceInPercent = namingParams["differenceInPercent"]
    colorName = namingParams["colorName"]
    labelName = namingParams["labelName"]

    largestArray: list[int | float | str] = []
    smallestArray: list[int | float | str] = []
    maxDifference = 0.35
    minPercent = 70

    lf, chartDict = add_sign_to_labels(
        df, None, differenceInPercent, 0, True, chartDict
    )
    lf = ensure_lazyframe(lf).with_row_index("__row_nr")

    lf_pos = lf.filter(pl.col(differenceInPercent) > 0)
    pos_count = lf_pos.select(pl.len()).collect(engine="streaming").item()
    if pos_count >= 2:
        largest_df = (
            lf_pos.sort(differenceInPercent, descending=True)
            .select("__row_nr", colorName, differenceInPercent)
            .limit(2)
            .collect(engine="streaming")
        )
        largest = largest_df[differenceInPercent][0]
        if largest > minPercent:
            rowLargest = largest_df["__row_nr"][0]
            colorLargest = largest_df[colorName][0]
            secondLargest = (
                largest_df[differenceInPercent][1] if largest_df.height > 1 else largest
            )
            difference = secondLargest / largest
            if difference < maxDifference:
                lf = lf.with_columns(
                    pl.when(pl.col("__row_nr") == rowLargest)
                    .then(pl.lit(None))
                    .otherwise(pl.col(differenceInPercent))
                    .alias(differenceInPercent)
                )
                largestArray = [int(rowLargest), float(largest), colorLargest]

    lf_neg = lf.filter(pl.col(differenceInPercent) < 0)
    neg_count = lf_neg.select(pl.len()).collect(engine="streaming").item()
    if neg_count >= 2:
        smallest_df = (
            lf_neg.sort(differenceInPercent)
            .select("__row_nr", colorName, differenceInPercent)
            .limit(2)
            .collect(engine="streaming")
        )
        smallest = smallest_df[differenceInPercent][0]
        if smallest < -minPercent:
            rowSmallest = smallest_df["__row_nr"][0]
            colorSmallest = smallest_df[colorName][0]
            secondSmallest = (
                smallest_df[differenceInPercent][1]
                if smallest_df.height > 1
                else smallest
            )
            difference = secondSmallest / smallest
            if difference < maxDifference:
                lf = lf.with_columns(
                    pl.when(pl.col("__row_nr") == rowSmallest)
                    .then(pl.lit(None))
                    .otherwise(pl.col(differenceInPercent))
                    .alias(differenceInPercent)
                )
                smallestArray = [int(rowSmallest), float(smallest), colorSmallest]

    lf = lf.drop("__row_nr").with_columns(
        pl.when(pl.col(differenceInPercent).is_null())
        .then(pl.lit(""))
        .otherwise(pl.col(labelName))
        .alias(labelName)
    )

    return lf, largestArray, smallestArray, chartDict


def correct_prefix_if_two_metric(chartDict, metric):
    namingParams = get_naming_params()
    chosenChartKey = namingParams["chosenChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    metricsToPlot = namingParams["metricsToPlot"]
    valueName = namingParams["valueName"]
    valuePrefixDict = namingParams["valuePrefixDict"]
    chosenChart = chartDict[chosenChartKey]
    if chosenChart in [stackedBarChart]:
        if metricsToPlot in chartDict and len(chartDict[metricsToPlot]) == 2:
            if valuePrefixDict in chartDict and valueName in chartDict[valuePrefixDict]:
                if metric not in chartDict[valuePrefixDict]:
                    chartDict[valuePrefixDict][metric] = chartDict[valuePrefixDict][
                        valueName
                    ]
                    del chartDict[valuePrefixDict][valueName]
    return chartDict


def get_query_string_from_indexCols(filterDict, indexCols):
    """
    we have a list with the index colum names and a dictionary with the same names and the the keys and we want to build
    a query string we can use to select the right row and change its level of priority
    this function, given the dictionary, returns the query string
    """
    count = 0
    fullQueryString = ""
    for colName in indexCols:
        queryStringElement = build_equal_to_query_string_element(
            colName, filterDict[colName]
        )
        fullQueryString = assemble_query_string_elements(
            queryStringElement, fullQueryString, count
        )
        count = count + 1
    return fullQueryString


def improve_text_position(x):
    """it is more efficient if the x values are sorted"""
    # fix indentation
    positions = [15, 0, -15]
    # you can add more: left center ...
    return [positions[i % len(positions)] for i in range(len(x))]


def adjust_annotation_positions(fig: go.Figure, count: int) -> go.Figure:
    """Shift facet annotations vertically for small multiple charts."""

    if count <= 0:
        return fig

    for idx, annotation in enumerate(fig.layout.annotations):
        step = 1 / (count * 2)
        position = (idx * (step * 2)) + step
        top_position = position + (step * 0.8)
        annotation.y = top_position
        annotation.yshift = (-15 / count) * (count - idx)
        annotation.x = 1
        annotation.textangle = 0
        annotation.xanchor = "right"

    return fig


def filter_alternate_results(dfCopy, dfTopCopy, indexCols):
    """
    we want to get the top alternate results for each dimension column
    """
    namingParams = get_naming_params()
    varianceAmountName = namingParams["varianceAmountName"]
    avgAmountPeriodsZeroOne = namingParams["avgAmountPeriodsZeroOne"]
    dimension = namingParams["dimensionName"]
    filterName = namingParams["filterName"]
    varianceTypeName = namingParams["varianceTypeName"]
    frameArray = []
    numberOfAlternates = 10
    dfTop = ensure_polars_df(dfTopCopy).clone()
    values = dfTop.select(indexCols).row(0)
    varianceTypeValue = dfTop.select(varianceTypeName).item()
    dfCopy = ensure_polars_df(dfCopy).filter(
        pl.col(varianceTypeName) == varianceTypeValue
    )
    dfTop = dfTop.head(1)
    filterDict = {k: v[0] for k, v in dfTop.to_dict(as_series=False).items()}
    dfCopy = dfCopy.with_columns(pl.lit("").alias(dimension))
    for element in indexCols:
        dfFilter = ensure_polars_df(dfCopy)
        indexCopy = copy.deepcopy(indexCols)
        indexCopy = take_filtered_value_out_of_option_list(indexCopy, element)
        # Build a boolean mask across all index columns using Polars only
        expr = pl.all_horizontal([pl.col(col) == filterDict[col] for col in indexCopy])
        dfFilter = dfFilter.filter(expr)
        dfFilter = dfFilter.filter(pl.col(varianceAmountName) != 0)
        dfFilter = dfFilter.head(numberOfAlternates)
        dfFilter = dfFilter.with_columns(pl.lit(element).alias(dimension))
        dfFilter = dfFilter.rename({element: filterName})
        dfFilter = dfFilter.select(
            dimension,
            filterName,
            varianceTypeName,
            varianceAmountName,
            avgAmountPeriodsZeroOne,
        )
        if dfFilter.height > 0:
            frameArray.append(dfFilter)
    if frameArray:
        dfResult = pl.concat(frameArray)
    else:
        dfResult = pl.DataFrame()
    return dfResult


def filter_loop_data(dfDict, dfCopy, chartDict, errorMessage):
    """
    from the snapshot df we get only the rows of the selected row result
    """
    namingParams = get_naming_params()
    rowToPlot = namingParams["rowToPlotName"]
    dfSnapshotName = namingParams["dfSnapshotName"]
    loopNumber = namingParams["loopNumberName"]
    plotOriginalData = namingParams["plotOriginalData"]
    dfDictSnapshotDrilledName = namingParams["dfDictSnapshotDrilledName"]
    drillDownDatasetNumber = namingParams["drillDownDatasetNumber"]
    mainReportRunName = namingParams["mainReportRunName"]
    if (
        drillDownDatasetNumber in chartDict
        and chartDict[drillDownDatasetNumber] != mainReportRunName
    ):
        dfCopy = dfDict[dfDictSnapshotDrilledName][chartDict[drillDownDatasetNumber]]
    columns, schema = get_schema_and_column_names(dfCopy)
    if (
        chartDict[rowToPlot] != namingParams["entireDatasetName"]
        and loopNumber in columns
    ):
        chosenRow = chartDict[rowToPlot]
        dfTop = duplicate_dataframe(dfCopy)
        loops = dfTop[loopNumber].unique().to_list()
        if chosenRow not in loops:
            chosenRow = loops[-1]
            chartDict[rowToPlot] = chosenRow
        dfTop = dfTop.filter(pl.col(loopNumber) == chosenRow)
        if chartDict[plotOriginalData]:
            dfSnapshot = duplicate_dataframe(dfCopy)
            dfSnapshot = dfSnapshot.filter(pl.col(loopNumber) == 1)
        else:
            dfSnapshot = dfTop.clone()
    else:
        dfSnapshot = pl.DataFrame()
        dfTop = pl.DataFrame()
        errorMessage = "Entire dataset option not compatible with this plot. Select a report row to plot."
    return dfSnapshot, dfTop, errorMessage, chartDict


def prepare_actual_vs_year_ago_dataframe(
    dfCopy, chosenChart, valueCols, indexCols, chartDict, paramDict
):
    """
    We need to prepare a dataset with the this year and year ago information
    for different time number of months/weeks
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    weeksInYear = configParams[namingParams["weeksInYear"]]
    weeksInSemester = configParams[namingParams["weeksInSemester"]]
    weeksInQuarter = configParams[namingParams["weeksInQuarter"]]
    weeksInMonth = configParams[namingParams["weeksInMonth"]]
    acpyName = namingParams["acpyName"]
    acName = namingParams["acName"]
    pyName = namingParams["pyName"]
    dateName = namingParams["dateName"]
    periodName = namingParams["periodName"]
    monthName = namingParams["monthName"]
    lastName = namingParams["lastName"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    frameArray = []
    if chosenChart == trendComparisonByPeriodChart:
        periodsArray = [weeksInYear, weeksInSemester, weeksInQuarter, weeksInMonth]
    else:
        periodsArray = [weeksInYear]

    paramDict, mostRecentDate, leastRecentDate, periodLengthInMonths = (
        get_period_length(dfCopy, paramDict, False)
    )

    df_lazy = duplicate_dataframe(dfCopy)
    if not isinstance(df_lazy, pl.LazyFrame):
        df_lazy = pl.DataFrame(df_lazy).lazy()

    oneYearAgoDelta = pl.lit(mostRecentDate - dt.timedelta(weeks=weeksInYear))

    if chosenChart == trendComparisonByPeriodChart:
        group_byCols = indexCols + [acpyName, periodName]
    else:
        group_byCols = indexCols + [dateName, periodName]

    for element in periodsArray:
        firstDelta = pl.lit(mostRecentDate - dt.timedelta(weeks=element))
        secondDelta = pl.lit(mostRecentDate - dt.timedelta(weeks=element + weeksInYear))

        df_ty = df_lazy.filter(pl.col(dateName).dt.date() >= firstDelta).with_columns(
            [
                (
                    pl.lit(lastName + str(element))
                    if chosenChart == trendComparisonByPeriodChart
                    else pl.lit(acName)
                ).alias(periodName),
                (
                    pl.lit(acName)
                    if chosenChart == trendComparisonByPeriodChart
                    else pl.lit(np.nan)
                ).alias(acpyName),
            ]
        )

        value_cols = check_value_column_exist(df_ty, valueCols)
        df_ty = df_ty.group_by(group_byCols).agg(
            [pl.col(c).sum().alias(c) for c in value_cols]
        )

        df_ya = df_lazy.filter(
            (pl.col(dateName).dt.date() < oneYearAgoDelta)
            & (pl.col(dateName).dt.date() >= secondDelta)
        ).with_columns(
            [
                (
                    pl.lit(lastName + str(element))
                    if chosenChart == trendComparisonByPeriodChart
                    else pl.lit(pyName)
                ).alias(periodName),
                (
                    pl.lit(pyName)
                    if chosenChart == trendComparisonByPeriodChart
                    else pl.lit(np.nan)
                ).alias(acpyName),
            ]
        )

        value_cols = check_value_column_exist(df_ya, valueCols)
        df_ya = df_ya.group_by(group_byCols).agg(
            [pl.col(c).sum().alias(c) for c in value_cols]
        )

        df_res = pl.concat([df_ty, df_ya])
        if chosenChart == trendComparisonByPeriodChart:
            df_res = df_res.with_columns([pl.col(c) / element for c in value_cols])

        frameArray.append(df_res)

    df_final = pl.concat(frameArray).collect()
    return df_final, paramDict


def make_one_dimensional_variance_subplots(aggregationsToPlot, numberOfCols):
    verticalSpacingDict = {1: 0, 2: 0.20, 3: 0.1, 4: 0.08, 5: 0.06, 6: 0.04}
    horizontalSpacing = 0.1
    numberOfItems = len(aggregationsToPlot)
    numberOfRows = int(math.ceil(numberOfItems / numberOfCols))
    if numberOfRows in verticalSpacingDict:
        verticalSpacing = verticalSpacingDict[numberOfRows]
    else:
        verticalSpacing = verticalSpacingDict[len(verticalSpacingDict)]
    verticalSpacing = verticalSpacing * 1.2
    fig = make_subplots(
        rows=numberOfRows,
        cols=numberOfCols,
        shared_xaxes="all",
        shared_yaxes="all",
        vertical_spacing=verticalSpacing,
        horizontal_spacing=horizontalSpacing,
        subplot_titles=aggregationsToPlot,
    )
    countRows = 1
    countCols = 1
    count = 1
    return fig, countRows, countCols, count, numberOfCols, numberOfRows


def set_break_row_tag(chartDict, chosenChart):
    namingParams = get_naming_params()
    upsetChart = namingParams["upsetChart"]
    vennChart = namingParams["vennChart"]
    breakTag = ""
    if chosenChart in [vennChart, upsetChart]:
        breakTag = "\n"
    else:
        breakTag = "<BR>"
    return breakTag


def get_filter_text_or_company_name(chartDict, paramDict):
    namingParams = get_naming_params()
    companyNameKey = namingParams["companyName"]
    filterDictName = namingParams["filterDictName"]
    includefullQueryString = namingParams["includefullQueryString"]
    excludefullQueryString = namingParams["excludefullQueryString"]
    toIncludeItems = namingParams["toIncludeItems"]
    toExcludeItems = namingParams["toExcludeItems"]
    numberFilterDictName = namingParams["numberFilterDictName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    addCompanyNameLabel = namingParams["addCompanyNameLabel"]
    loadDataTabLabel = namingParams["loadDataTabLabel"]
    loadDataTabKey = namingParams["loadDataTab"]
    infoMessageType = namingParams["infoMessageType"]
    filterStringKey = namingParams["filterString"]
    companyName = ""
    isNumberFiltered = False
    includeNumberFilterSting, excludeNumberFilterSting, numberFilterString = "", "", ""
    chartDict[filterStringKey] = ""
    if numberFilterDictName in chartDict:
        if len(chartDict[numberFilterDictName]) > 0:
            for column in chartDict[numberFilterDictName]:
                if len(chartDict[numberFilterDictName][column]) > 0:
                    isNumberFiltered = True
                    if toIncludeItems in chartDict[numberFilterDictName][column]:
                        valueArray = chartDict[numberFilterDictName][column][
                            toIncludeItems
                        ]
                        includeNumberFilterSting = (
                            column
                            + " ≥"
                            + str(valueArray[0])
                            + " & "
                            + " ≤"
                            + str(valueArray[1])
                        )
                    if toExcludeItems in chartDict[numberFilterDictName][column]:
                        valueArray = chartDict[numberFilterDictName][column][
                            toExcludeItems
                        ]
                        excludeNumberFilterSting = (
                            column
                            + " ≤"
                            + str(valueArray[0])
                            + " & "
                            + " ≥"
                            + str(valueArray[1])
                        )
                if isNumberFiltered == True:
                    separator = ""
                    if (
                        len(includeNumberFilterSting) > 0
                        and len(excludeNumberFilterSting) > 0
                    ):
                        separator = " "
                    numberFilterString = (
                        includeNumberFilterSting + separator + excludeNumberFilterSting
                    )
    isFiltered = False
    (
        excludeFilterString,
        includeFilterString,
        excludeFilterItem,
        includeFilter,
        filterString,
    ) = (
        "",
        "",
        "",
        "",
        "",
    )
    if filterDictName in chartDict and len(chartDict[filterDictName]) > 0:
        countInclude = 0
        countExclude = 0
        for element in chartDict[filterDictName]:
            if toIncludeItems in chartDict[filterDictName][element]:
                if len(chartDict[filterDictName][element][toIncludeItems]) > 0:
                    includeFilterItem = chartDict[filterDictName][element][
                        toIncludeItems
                    ]
                    includeFilterItem = (
                        str(includeFilterItem)
                        .replace("[", "")
                        .replace("]", "")
                        .replace('"', "")
                        .replace("'", "")
                        .replace(",", " &")
                    )
                    includeFilterItem = element + "=" + includeFilterItem
                    isFiltered = True
                    if countInclude == 0:
                        includeFilterString = includeFilterItem
                    else:
                        includeFilterString = (
                            includeFilterString + "; " + includeFilterItem
                        )
                    countInclude = countInclude + 1
            if toExcludeItems in chartDict[filterDictName][element]:
                if len(chartDict[filterDictName][element][toExcludeItems]) > 0:
                    excludeFilterItem = chartDict[filterDictName][element][
                        toExcludeItems
                    ]
                    excludeFilterItem = (
                        str(excludeFilterItem)
                        .replace("[", "")
                        .replace("]", "")
                        .replace('"', "")
                        .replace("'", "")
                    )
                    excludeFilterItem = element + "≠" + excludeFilterItem
                    isFiltered = True
                    if countExclude == 0:
                        excludeFilterString = excludeFilterItem
                    else:
                        excludeFilterString = (
                            excludeFilterString + "; " + excludeFilterItem
                        )
                    countExclude = countExclude + 1
    if isFiltered:
        separator = ""
        if len(includeFilterString) > 0 and len(excludeFilterString) > 0:
            separator = "; "
        filterString = includeFilterString + separator + excludeFilterString
        filterString = filterString + " " + numberFilterString
        chartDict[filterStringKey] = filterString
    else:
        filterString = numberFilterString
    if isFiltered or isNumberFiltered:
        companyName = filterString + " "
    elif companyNameKey in chartDict and chartDict[companyNameKey]:
        companyName = chartDict[companyNameKey].title() + " "
    companyName = companyName.replace("<br>", "")
    if companyNameKey in chartDict and chartDict[companyNameKey] == "":
        message = (
            "Reporting entity not specified. Use the '"
            + addCompanyNameLabel
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
    return companyName, paramDict, chartDict


def make_like_for_like_title_suffix(chartDict, paramDict, metric):
    namingParams = get_naming_params()
    likeForLikeSuffix = namingParams["likeForLikeSuffix"]
    isLikeForLike = namingParams["isLikeForLike"]
    countMetricsColumnKey = namingParams["countMetricsColumn"]
    likeForLikeScope = namingParams["likeForLikeScope"]
    likeForLikeTwo = namingParams["likeForLikeTwo"]
    likeForLikeAll = namingParams["likeForLikeAll"]
    allPeriodsList = namingParams["allPeriodsList"]
    selectedPeriods = namingParams["selectedPeriods"]
    likeForLikeMessage = ""
    if isLikeForLike in chartDict and chartDict[isLikeForLike]:
        if countMetricsColumnKey in chartDict and chartDict[countMetricsColumnKey]:
            likeForLikePeriod = ""
            if likeForLikeScope in chartDict:
                if chartDict[likeForLikeScope] == likeForLikeTwo:
                    if (
                        selectedPeriods in chartDict
                        and len(chartDict[selectedPeriods]) > 1
                    ):
                        likeForLikePeriod = (
                            chartDict[selectedPeriods][0]
                            + " to "
                            + chartDict[selectedPeriods][-1]
                        )
                elif chartDict[likeForLikeScope] == likeForLikeAll:
                    if (
                        allPeriodsList in paramDict
                        and len(paramDict[allPeriodsList]) > 1
                    ):
                        likeForLikePeriod = (
                            paramDict[allPeriodsList][0]
                            + " to "
                            + paramDict[allPeriodsList][-1]
                        )
            # if metric and chartDict[countMetricsColumnKey] not in metric:
            #    likeForLikeSuffix=likeForLikeSuffix+" "+chartDict[countMetricsColumnKey]
        likeForLikeMessage = " " + likeForLikeSuffix + " " + likeForLikePeriod + " "
        if metric and chartDict[countMetricsColumnKey] not in metric:
            likeForLikeMessage = (
                likeForLikeMessage + " " + chartDict[countMetricsColumnKey]
            )
    return likeForLikeMessage


def set_up_tab_for_show_or_download_chart(
    df,
    fig,
    configPlotlyDict,
    chartDict,
    string,
    varianceAnalysisChart,
    run,
    chosenDimension,
    paramDict,
):
    namingParams = get_naming_params()
    columnHash = paramDict[namingParams["columnHash"]]
    chosenChart = namingParams["chosenChart"]
    exportData = namingParams["exportData"]
    areaChart = namingParams["areaChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    bubbleChart = namingParams["bubbleChart"]
    boxplotChart = namingParams["boxplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    histogramChart = namingParams["histogramChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    kernelDensityChart = namingParams["kernelDensityChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    stripplotChart = namingParams["stripplotChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    paretoChart = namingParams["paretoChart"]
    plotlyFileName = namingParams["plotlyFileName"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    showChart = namingParams["showChart"]
    showDataframe = namingParams["showDataframe"]
    slopeChart = namingParams["slopeChart"]
    scatterChart = namingParams["scatterChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    timelineChart = namingParams["timelineChart"]
    totalName = namingParams["totalName"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    varianceAnalysisChartKey = namingParams["varianceAnalysisChart"]
    processingChoice = namingParams["processingChoice"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    plotSmallMultiplesWaterfall = namingParams["plotSmallMultiplesWaterfall"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    infoIcon = namingParams["infoIcon"]
    errorInFragment = namingParams["errorInFragment"]
    smallMultiplesCharts = namingParams["plotSmallMultiplesOtherCharts"]
    fileName = configPlotlyDict["toImageButtonOptions"][plotlyFileName]
    if len(chartDict) > 1:
        if chosenChart in chartDict and chartDict[chosenChart] in [
            horizontalWaterfallChart,
            multitierBarChart,
            multitierColumnChart,
            trendComparisonChart,
            trendComparisonByPeriodChart,
            timelineChart,
            slopeChart,
            stackedColumnChart,
        ]:
            if (
                chosenDimension in [None, totalName]
                and selectDimensionsToPlot in chartDict
            ):
                del chartDict[selectDimensionsToPlot]
        hashDict = clean_chartDict(chartDict, True, varianceAnalysisChart, run)
        # ui.write(hashDict)
        hashkey, paramDict = get_image_name_hash(hashDict, string, paramDict)
        if len(hashkey) > 1:
            fileName = fileName + "__" + str(hashkey)
            configPlotlyDict["toImageButtonOptions"][plotlyFileName] = fileName
    showChartTab, exportDataTab, showDataTab = ui.tabs(
        [showChart, exportData, showDataframe]
    )
    with showChartTab:
        ui.plotly_chart(
            fig, width="content", config=configPlotlyDict, theme=None
        )
        if fileUploadDisabled not in paramDict or paramDict[fileUploadDisabled]:
            ui.info(
                "To enable GPT plot comments, enter your activation token in the Load Dataset tab.",
                icon=infoIcon,
            )
        else:
            if chosenChart in chartDict and chartDict[chosenChart] in [
                areaChart,
                boxplotChart,
                ecdfChart,
                histogramChart,
                kernelDensityChart,
                multitierColumnChart,
                paretoChart,
                scatterChart,
                stripplotChart,
            ]:
                paramDict = get_comments_from_images(
                    fig, df, chartDict, paramDict, fileName
                )
            elif chosenChart in chartDict and chartDict[chosenChart] in [
                barmekkoChart,
                bubbleChart,
                marimekkoChart,
                horizontalWaterfallChart,
                multitierBarChart,
                stackedBarChart,
                stackedColumnChart,
                stackedParetoChart,
                timelineChart,
            ]:
                if 1 == 3:
                    get_comments_from_data(
                        fig, df, chosenDimension, chartDict, paramDict, fileName
                    )
                elif chartDict[chosenChart] in [
                    barmekkoChart,
                    bubbleChart,
                    marimekkoChart,
                    horizontalWaterfallChart,
                    multitierBarChart,
                    stackedBarChart,
                    stackedColumnChart,
                    stackedParetoChart,
                    timelineChart,
                ]:
                    pass
                    get_comments_from_data_fragment(
                        fig, df, chosenDimension, chartDict, paramDict, fileName
                    )
            elif (
                varianceAnalysisChartKey in chartDict
                and chartDict[varianceAnalysisChartKey]
                and chartDict[processingChoice]
                in [runVariableDimensionalAnalysis, runOneDimensionalAnalysis]
            ):
                get_comments_from_data_fragment(
                    fig, df, chosenDimension, chartDict, paramDict, fileName
                )

    with exportDataTab:
        try:
            if df.height > 10000:
                ui.caption("Download limited to first 10000 rows.")
            key = fileName
            from modules.layout.set_up_widgets import download_plot_file

            download_plot_file(df.head(10000), fileName)
        except Exception as e:  # nosec B110
            logging.exception(e)
            ui.write("download data error:", e)
            ui.error("cannot download data. duplicated widget problem")
    with showDataTab:
        try:
            if df.height > 50:
                ui.caption("Showing first 50 rows.")
                ui.dataframe(df.head(50))
            else:
                ui.dataframe(df)
        except Exception as e:  # nosec B110
            logging.exception(e)
            ui.write("show dataframe error:", e)
            ui.error("cannot show dataframe.")
    if errorInFragment in session_state and session_state[errorInFragment]:
        ui.write(session_state[errorInFragment])
    return paramDict
