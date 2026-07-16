import logging
import copy
from itertools import product
from modules.utilities.ui_notifier import ui as notifier

import polars as pl
import psutil

from modules.data.data_cleaning import (
    check_date_and_group_data,
    get_count_metric_names,
    manage_filtering,
    query_filter_dataframe_all_periods,
    query_filter_dataframe_dates,
    query_filter_dataframe_periods,
    query_filter_dataframe_plan,
)
from modules.layout.set_up_widgets import (
    download_filtered_file,
    set_up_cohort_column_widget,
    set_up_count_metrics_widget,
)
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_app_message_to_paramdict
from modules.utilities.helpers import (
    measure_time,
    unique,
)
from modules.utilities.utils import (
    ensure_lazyframe,
    get_row_count,
    get_schema_and_column_names,
    is_valid_lazyframe,
)


def prepare_cohort_and_period_data_for_analysis(
    paramDictCopy,
    df,
    dfDates,
    dfPeriods,
    dfAllPeriods,
    dfPlan,
    dfDict,
    colDict,
    tabDict,
    chartDict,
    automateDict,
    planPlaybackDict,
):
    namingParams = get_naming_params()
    errorMessageType = namingParams["errorMessageType"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    processingChoice = namingParams["processingChoice"]
    dataPreparation = namingParams["dataPreparationName"]
    loadDataTabKey = namingParams["loadDataTab"]
    plotChartsTabKey = namingParams["plotChartsTab"]
    columnOrder = namingParams["columnOrderName"]
    filterDataTabKey = namingParams["filterDataTab"]
    setVarianceOptionsTabKey = namingParams["setVarianceOptionsTab"]
    checkedDates = namingParams["checkedDatesName"]
    addedLostDroppedCols = namingParams["addedLostDroppedColsName"]
    queriedData = namingParams["queriedDataName"]
    colNumber = 0
    if paramDictCopy[impossibleToProcessFile] and processingChoice in chartDict:

        try:
            columns, _schema = get_schema_and_column_names(df)
        except Exception as e:
            logging.exception(e)
            notifier.error(f"Cohort schema error: {e}")
            columns = []
        try:
            row_count = get_row_count(df)
        except Exception as e:
            logging.exception(e)
            notifier.error(f"Cohort row-count error: {e}")
            row_count = 0
        columns_str = ", ".join(columns) if columns else "None"
        parse_msg = paramDictCopy.get("fileParseError", "")

        if not is_valid_lazyframe(df):
            message = (parse_msg + " ") if parse_msg else ""
            message += (
                "Empty or not processable dataset "
                f"(columns={columns_str}, rows={row_count}). "
                "Click on 🔍Detected columns to see which metric columns have been mapped."
            )
            paramDict = add_app_message_to_paramdict(
                message,
                errorMessageType,
                loadDataTabKey,
                paramDictCopy,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
        else:
            message = (parse_msg + " ") if parse_msg else ""
            message += (
                "Unable to detect required columns in dataset "
                f"(columns={columns_str}, rows={row_count}). "
                "Click on 🔍Detected columns to see which metric columns have been mapped."
            )
            paramDict = add_app_message_to_paramdict(
                message,
                errorMessageType,
                loadDataTabKey,
                paramDictCopy,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
        return None, None, None, None, None, None, None, paramDictCopy, None, None, None
    elif is_valid_lazyframe(df) and not paramDictCopy[impossibleToProcessFile]:
        paramDict = copy.deepcopy(paramDictCopy)
        df, indexCols, valueCols, paramDict, originalValueColsCopy = (
            check_date_and_group_data(paramDict, df)
        )
        measure_time(dataPreparation, checkedDates, False)
        chartDict = set_up_cohort_column_widget(
            dfAllPeriods,
            paramDict,
            chartDict,
            automateDict,
            indexCols,
            colDict[plotChartsTabKey],
        )
        df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols = add_cohort_column(
            df,
            dfDates,
            dfPeriods,
            dfAllPeriods,
            dfPlan,
            indexCols,
            paramDict,
            chartDict,
        )
        df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols = (
            add_lost_and_dropped_column(
                df,
                dfDates,
                dfPeriods,
                dfAllPeriods,
                dfPlan,
                indexCols,
                paramDict,
                chartDict,
            )
        )
        columns, schema = get_schema_and_column_names(dfPlan)
        paramDict[columnOrder] = columns
        measure_time(dataPreparation, addedLostDroppedCols, False)
        df, indexCols, toDrop, paramDict, chartDict = manage_filtering(
            df,
            indexCols,
            paramDict,
            chartDict,
            automateDict,
            valueCols,
            colDict[filterDataTabKey],
            colDict[setVarianceOptionsTabKey],
        )
        dfDates = query_filter_dataframe_dates(
            dfDates, chartDict[namingParams["filterDictName"]]
        )
        measure_time(
            dataPreparation, "0167 - query_filter_dataframe_dates - Converted", False
        )
        dfPeriods = query_filter_dataframe_periods(
            dfPeriods, chartDict[namingParams["filterDictName"]]
        )
        measure_time(
            dataPreparation, "0168 - query_filter_dataframe_period - Converted", False
        )
        dfAllPeriods = query_filter_dataframe_all_periods(
            dfAllPeriods, chartDict[namingParams["filterDictName"]]
        )
        measure_time(
            dataPreparation,
            "0169 - query_filter_dataframe_all_periods - Converted",
            False,
        )
        dfPlan = query_filter_dataframe_plan(
            dfPlan, chartDict[namingParams["filterDictName"]]
        )
        measure_time(
            dataPreparation, "0170 - query_filter_dataframe_plan - Converted", False
        )
        download_filtered_file(df, dfDates, valueCols, colDict, paramDict)
        chartDict = set_up_count_metrics_widget(
            paramDict, chartDict, automateDict, indexCols, colDict[plotChartsTabKey]
        )
        chartDict = get_count_metric_names(chartDict, valueCols)
    try:
        logger = logging.getLogger(__name__)
        columns_main, _ = get_schema_and_column_names(df)
        column_lookup = {c.lower(): c for c in columns_main}
        normalised_indexCols: list[str] = []
        for col in indexCols:
            resolved = column_lookup.get(col.lower(), col)
            if resolved != col:
                logger.debug(
                    "cohort-processing: normalising index column '%s' -> '%s'",
                    col,
                    resolved,
                )
            normalised_indexCols.append(resolved)
        indexCols = normalised_indexCols
        logger.debug(
            "cohort-processing: final indexCols=%s valueCols=%s",
            indexCols,
            valueCols,
        )
    except Exception:
        pass
    return (
        df,
        dfDates,
        dfPeriods,
        dfAllPeriods,
        dfPlan,
        indexCols,
        valueCols,
        paramDict,
        chartDict,
        toDrop,
        originalValueColsCopy,
    )


def add_lost_and_dropped_column(
    df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols, paramDict, chartDict
):
    namingParams = get_naming_params()
    lostAndDroppedColumnKey = namingParams["lostAndDroppedColumn"]
    periodName = namingParams["periodName"]
    allPeriodsList = namingParams["allPeriodsList"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    workColumn = namingParams["workColumn"]
    lostAndDroppedSuffix = namingParams["lostAndDroppedSuffix"]
    lostName = namingParams["lostName"]
    activeName = namingParams["activeName"]
    if lostAndDroppedColumnKey in chartDict and chartDict[lostAndDroppedColumnKey]:
        if chartDict[lostAndDroppedColumnKey] != nothingFilteredName:
            lostAndDroppedColumn = chartDict[lostAndDroppedColumnKey]
            orderedPeriods = paramDict[allPeriodsList]
            lostAndDroppedColumnName = lostAndDroppedColumn + lostAndDroppedSuffix
            # Start from lazy
            dfLostAndDropped = (
                dfAllPeriods.select([pl.col(lostAndDroppedColumn), pl.col(periodName)])
                .unique()
                .with_columns(pl.lit(1).alias(lostAndDroppedColumnName))
            )
            indexCols.append(lostAndDroppedColumnName)
            # Create one column per period indicating the presence (1) or absence (null)
            dfLostAndDropped = dfLostAndDropped.with_columns(
                [
                    pl.when(pl.col(periodName) == p)
                    .then(pl.col(lostAndDroppedColumnName))
                    .otherwise(None)
                    .alias(p)
                    for p in orderedPeriods
                ]
            )
            # Now aggregate to create the wide format (similar to pivot)
            dfLostAndDropped = dfLostAndDropped.group_by(lostAndDroppedColumn).agg(
                [pl.col(p).max().alias(p) for p in orderedPeriods]
            )
            # Filtering and concatenating
            count = 0
            frameArray = []
            for period in orderedPeriods[:-1]:
                dfPeriod = (
                    dfLostAndDropped.filter(
                        (pl.col(orderedPeriods[count]) == 1)
                        & (pl.col(orderedPeriods[count + 1]).is_null())
                    )
                    .with_columns(
                        pl.lit(lostName + "<br>" + period).alias(
                            lostAndDroppedColumnName
                        )
                    )
                    .drop(orderedPeriods)
                )
                frameArray.append(dfPeriod)
                count += 1

            dfLostAndDropped = pl.concat(frameArray, how="vertical")
            if isinstance(dfLostAndDropped, pl.LazyFrame):
                dfLostAndDropped_lazy = dfLostAndDropped.sort(lostAndDroppedColumn)
                dfLostAndDropped_eager = dfLostAndDropped_lazy.collect()
            else:
                dfLostAndDropped = dfLostAndDropped.sort(lostAndDroppedColumn)
                dfLostAndDropped_lazy = dfLostAndDropped.lazy()
                dfLostAndDropped_eager = dfLostAndDropped

            def _augment(frame):
                if not is_valid_lazyframe(frame):
                    return frame
                if isinstance(frame, pl.LazyFrame):
                    return (
                        frame.sort(lostAndDroppedColumn)
                        .join(
                            dfLostAndDropped_lazy,
                            on=lostAndDroppedColumn,
                            how="left",
                        )
                        .with_columns(
                            pl.col(lostAndDroppedColumnName).fill_null(activeName)
                        )
                    )
                if isinstance(frame, pl.DataFrame):
                    return (
                        frame.sort(lostAndDroppedColumn)
                        .join(
                            dfLostAndDropped_eager,
                            on=lostAndDroppedColumn,
                            how="left",
                        )
                        .with_columns(
                            pl.col(lostAndDroppedColumnName).fill_null(activeName)
                        )
                    )
                return frame

            df = _augment(df)
            dfDates = _augment(dfDates)
            dfPeriods = _augment(dfPeriods)
            dfAllPeriods = _augment(dfAllPeriods)
            dfPlan = _augment(dfPlan)
    return df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols


def add_cohort_column(
    df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols, paramDict, chartDict
):
    namingParams = get_naming_params()
    chosenCohortColumnKey = namingParams["chosenCohortColumn"]
    periodName = namingParams["periodName"]
    allPeriodsList = namingParams["allPeriodsList"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    chosenCohortSuffix = namingParams["chosenCohortSuffix"]
    sinceName = namingParams["sinceName"]

    def is_lazyframe(lf):
        return lf is not None and isinstance(lf, pl.LazyFrame)

    if chosenCohortColumnKey in chartDict and chartDict[chosenCohortColumnKey]:
        if chartDict[chosenCohortColumnKey] != nothingFilteredName:
            chosenCohortColumn = chartDict[chosenCohortColumnKey]
            orderedPeriods = paramDict[allPeriodsList]
            cohortColumnName = chosenCohortColumn + chosenCohortSuffix

            # 1) Map period -> rank
            period2rank = pl.DataFrame(
                {periodName: orderedPeriods, "period_rank": range(len(orderedPeriods))}
            ).lazy()

            # 2) Build dfCohorts
            dfCohorts = (
                dfAllPeriods.select([chosenCohortColumn, periodName])
                .unique()
                .join(period2rank, on=periodName, how="left")
                .group_by(chosenCohortColumn)
                .agg(
                    [
                        # Pick earliest period by sorting on period_rank
                        pl.col(periodName)
                        .sort_by(pl.col("period_rank"))
                        .first()
                        .alias("earliest_period")
                    ]
                )
                .with_columns(
                    (
                        pl.lit(sinceName) + pl.lit("<br>") + pl.col("earliest_period")
                    ).alias(cohortColumnName)
                )
                .drop(["earliest_period"])
            )

            dfCohorts_lazy = ensure_lazyframe(dfCohorts)

            def join_with_cohort_labels(
                target: pl.DataFrame | pl.LazyFrame,
            ) -> pl.DataFrame | pl.LazyFrame:
                """Attach cohort labels to ``target`` preserving its original type."""

                if not is_valid_lazyframe(target):
                    return target

                column_names, _schema = get_schema_and_column_names(target)
                if chosenCohortColumn not in column_names:
                    return target

                target_is_lazy = isinstance(target, pl.LazyFrame)
                joined_lazy = ensure_lazyframe(target).join(
                    dfCohorts_lazy,
                    on=chosenCohortColumn,
                    how="left",
                )
                return joined_lazy if target_is_lazy else joined_lazy.collect()

            # 3) Join that single-col label to each table
            indexCols.append(cohortColumnName)

            if is_valid_lazyframe(df):
                df = join_with_cohort_labels(df)

            columns, schema = get_schema_and_column_names(dfDates)
            if is_valid_lazyframe(dfDates) and chosenCohortColumn in columns:
                dfDates = join_with_cohort_labels(dfDates)

            columns, schema = get_schema_and_column_names(dfPeriods)
            if is_valid_lazyframe(dfPeriods) and chosenCohortColumn in columns:
                dfPeriods = join_with_cohort_labels(dfPeriods)

            columns, schema = get_schema_and_column_names(dfAllPeriods)
            if is_valid_lazyframe(dfAllPeriods) and chosenCohortColumn in columns:
                dfAllPeriods = join_with_cohort_labels(dfAllPeriods)

            columns, schema = get_schema_and_column_names(dfPlan)
            if is_valid_lazyframe(dfPlan) and chosenCohortColumn in columns:
                dfPlan = join_with_cohort_labels(dfPlan)

    return df, dfDates, dfPeriods, dfAllPeriods, dfPlan, indexCols
