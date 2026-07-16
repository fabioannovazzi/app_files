import logging
import polars as pl
from modules.layout.core.ui_adapter import ui
from modules.utilities.session_context import session_state
import datetime as dt
import copy
import logging
from typing import IO, Optional, Tuple, BinaryIO, Sequence, TypeVar
from pathlib import Path
import re
from io import StringIO
import datetime
import json

from src.load_sales_logic import parse_dimension_datasets

from modules.utilities.config import (
    get_config_params,
    get_naming_params,
    get_file_params,
    get_currency_params,
    get_metric_array_params,
    get_variance_aggregation_params,
)
from modules.utilities.error_messages import (
    add_error_message_in_plan_dataset_tab,
    add_warning_message_in_plan_dataset_tab,
    add_error_message_in_plot_charts_tab,
    add_error_message_in_variance_options_tab,
    add_info_message_in_conversation_tab,
    add_info_message_in_load_data_tab,
    add_error_message_in_load_data_tab,
    add_warning_message_in_period_options_tab,
)

from modules.utilities.helpers import (
    check_and_clean_columns,
    convert_df,
    drop_columns,
    duplicate_dataframe,
    insert_json_value,
    take_filtered_value_out_of_option_list,
    unique,
    get_file_error_message,
    add_price_to_value_cols,
    get_periods_array,
    rank_columns_by_number_of_uniques,
    add_promo_metric_to_valuecols,
    process_if_promo_data,
    get_growth_metrics_for_bubble,
    get_gross_margin_metrics_for_bubble,
    get_image_name_hash,
)
from src.io_utils import convert_df_csv, convert_df_parquet
from modules.layout.layout_helpers import (
    make_five_col_width_array,
    make_four_col_width_array,
    make_six_col_width_array,
    make_three_col_width_array,
    make_two_col_width_array,
    show_warning_ui,
    show_chart_image,
)
from modules.auth.session_state import get_authenticated_user

from modules.layout.memoization import (
    check_collect,
)

from modules.utilities.utils import (
    get_schema_and_column_names,
    is_valid_lazyframe,
    get_row_count,
)
from modules.charting.polars_helpers import n_unique_lazy

from modules.charting.chart_primitives import (
    get_color_dictionary,
    get_parents_of_dimension,
    get_colors_for_observations,
    find_possible_data_column_metrics,
)

from modules.charting.chart_helpers import (
    get_highlighted_items,
)

from modules.layout.core.variance_options import (
    select_possible_aggregation_options,
    check_if_options_compatible_with_one_dimensional,
)
from modules.layout.widgets import searchable_selectbox_with_state

logger = logging.getLogger(__name__)
from src.period_options import determine_most_recent_period_options


def set_up_join_dataset_widgets(paramDict, dataPrepWidgetDict, col1Array):
    """
    set up second block of widgets
    """
    namingParams = get_naming_params()
    isdataset = namingParams["isdataset"]
    isDataUploaded = namingParams["isDataUploaded"]
    dataPrepWidgetDict = set_up_negative_values_to_zero_widget(
        paramDict, dataPrepWidgetDict, col1Array[0]
    )
    dataPrepWidgetDict = set_up_drop_duplicates_widget(
        paramDict, dataPrepWidgetDict, col1Array[0]
    )
    if isdataset in paramDict and paramDict[isdataset]:
        if isDataUploaded in paramDict and paramDict[isDataUploaded]:
            paramDict = set_up_add_dimensions_widget(paramDict, col1Array[0])
            paramDict = parse_dimension_datasets(paramDict)
    return paramDict, dataPrepWidgetDict


def get_hashed_key_for_widgets(key, columnHash):
    if columnHash:
        key = key + "_" + str(columnHash)
    return key


T = TypeVar("T")


def selectbox_with_state(
    name: str,
    column_hash: int | str,
    *,
    label: str,
    options: Sequence[T],
    index: int = 0,
    **kwargs,
) -> T:
    """Render a compact, searchable selectbox with persistent state."""
    key = get_hashed_key_for_widgets(name, column_hash)
    return searchable_selectbox_with_state(
        label=label, options=options, key=key, index=index, **kwargs
    )


def radio_with_state(
    name: str,
    column_hash: int | str,
    *,
    label: str,
    options: Sequence[T],
    index: int = 0,
    horizontal: bool = False,
    **kwargs,
) -> T:
    """Render a radio group persisting its value in session state."""
    key = get_hashed_key_for_widgets(name, column_hash)
    session_state.setdefault(key, options[index])
    default = session_state[key]
    if default in options:
        index = options.index(default)
    ui.radio(
        label=label,
        options=options,
        index=index,
        key=key,
        horizontal=horizontal,
        **kwargs,
    )
    return session_state[key]


def show_disclaimer():
    ui.markdown("""
    > **This document has been revised based on AI-generated suggestions. All proposed changes were subject to your review, and you have accepted, rejected, or modified them.**  
    >
    > **None of your actions have been recorded or stored by the application.**  
    >
    > **The resulting text may contain legal interpretations or implications. It is not certified legal advice and has not been reviewed by a qualified lawyer. Use of this document remains under your sole responsibility.**
    """)
    return None


def download_word_file(data, label, fileName):
    ui.download_button(
        label=label,
        data=data,
        file_name=fileName,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    return None


def download_text_data(data, label, fileName):
    ui.download_button(
        label=label,
        data=data,
        file_name=fileName + ".csv",
        mime="text/csv",
    )
    return None


def download_image_data(img_buffer, label, fileName):
    ui.download_button(
        label=label,
        data=img_buffer,
        file_name=fileName + ".png",
        mime="image/png",
    )
    return None


def download_json_data(data, label, fileName):
    ui.download_button(
        label=label, data=data, file_name=fileName + ".zip", mime="application/zip"
    )
    return None


def show_highlighted_items_widget(chartDict, automateDict, columnHash, paramDict):
    namingParams = get_naming_params()
    colorItems = namingParams["colorItems"]
    highlightedDimension = namingParams["highlightedDimension"]
    highlightedDimensionLabel = namingParams["highlightedDimensionLabel"]
    columnHash = paramDict[namingParams["columnHash"]]
    hashHighlightedDimension = get_hashed_key_for_widgets(
        highlightedDimension, columnHash
    )
    chartDict[highlightedDimension] = []
    chartDict[colorItems] = uniqueItems
    tooltip = """Select one or more items to highlight."""
    message = """✳️Items to highlight in plot."""
    value = None
    value = insert_json_value(
        "array", value, automateDict, uniqueItems, highlightedDimension, None
    )
    chartDict[highlightedDimension] = ui.multiselect(
        label=highlightedDimensionLabel,
        options=uniqueItems,
        default=value,
        help=tooltip,
        key=hashHighlightedDimension,
        max_selections=None,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def show_submit_button(paramDict, chartDict):
    namingParams = get_naming_params()
    submitPlotLabel = namingParams["submitPlotLabel"]
    submitPlotName = namingParams["submitPlotName"]
    submitCommentName = namingParams["submitCommentName"]
    chartDictNotChangedName = namingParams["chartDictNotChangedName"]
    columnHash = paramDict[namingParams["columnHash"]]
    hashKey = get_hashed_key_for_widgets(submitPlotName, columnHash)
    submitted = False
    colArray = make_three_col_width_array()
    if submitPlotName not in session_state:
        session_state[submitPlotName] = False
    if submitCommentName not in session_state:
        session_state[submitCommentName] = False
    with colArray[0]:
        tooltip = """Plot."""
        message = """✳️Plot chart."""
        bridgeSubmit = ui.button(
            label=submitPlotLabel, help=None, key=hashKey, type="primary"
        )
        ui.caption(message)
        chartDict[submitPlotName] = bridgeSubmit
    if bridgeSubmit or (
        submitPlotName in session_state
        and session_state[submitPlotName]
        and chartDictNotChangedName in session_state
        and session_state[chartDictNotChangedName]
    ):
        submitted = bridgeSubmit
    if bridgeSubmit or (
        submitPlotName in session_state
        and session_state[submitPlotName]
        and chartDictNotChangedName in session_state
        and session_state[chartDictNotChangedName]
    ):
        session_state[submitPlotName] = True
        if submitCommentName in session_state:
            session_state[submitCommentName] = False
    return submitted, chartDict


def download_json(saveDict, paramDict, colArray, plotOrPlan):
    namingParams = get_naming_params()
    plotPlaybackName = namingParams["plotPlaybackName"]
    planPlaybackName = namingParams["planPlaybackName"]
    uploadedFileName = namingParams["uploadedFileName"]
    queryOpenAi = namingParams["queryOpenAi"]
    columnHash = namingParams["columnHash"]
    columnHash = plotOrPlan
    if columnHash in paramDict:
        columnHash = paramDict[columnHash]
    fileName = ""
    hashKey, paramDict = get_image_name_hash(saveDict, False, paramDict)
    if uploadedFileName in paramDict and paramDict[uploadedFileName]:
        fileName = paramDict[uploadedFileName]
    if plotOrPlan == plotPlaybackName:
        fileName = "plots_"
        fileName = fileName + hashKey
        message = "Download the json playback file to 🔁rerun the plots of your report. All data will be discarded🚮when you close your session."
        label = "Download plot playback file"
        column = 0
    elif plotOrPlan == queryOpenAi:
        fileName = queryOpenAi
        fileName = fileName + hashKey
        message = "Download the json playback file to 🔁run the plots  chosen by GPT. All data will be discarded🚮when you close your session."
        label = "Download plot playback file"
        column = 0
    else:
        fileName = "plan_"
        fileName = fileName + hashKey
        message = "Download the json playback file to 🔁rerun your plan dataset. All data will be discarded🚮when you close your session."
        label = "Download plan playback file"
        column = 0
    with colArray[column]:
        if len(saveDict) > 0:
            if isinstance(saveDict, dict):
                saveDict = json.dumps(saveDict)
            else:
                saveDict = clean_response_from_triple_quotes(saveDict)
            download_json_data(saveDict, label, fileName)
            ui.caption(message)
    return None


def download_filtered_file(df, dfDates, valueCols, colDict, paramDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    multiplyConstant = configParams[namingParams["multiplyConstant"]]
    prepareFilteredFileForDownload = namingParams["prepareFilteredFileForDownload"]
    dfFilteredName = namingParams["dfFilteredName"]
    filterDataTabKey = namingParams["filterDataTab"]
    isColumnMultiplied = namingParams["isColumnMultiplied"]
    volumeName = namingParams["volumeName"]
    unitsName = namingParams["unitsName"]
    netMarginName = namingParams["netMarginName"]
    if (
        prepareFilteredFileForDownload in paramDict
        and paramDict[prepareFilteredFileForDownload]
    ):
        with colDict[filterDataTabKey][0]:
            downloadExpander = ui.expander("➕Download filtered dataset")
            if is_valid_lazyframe(dfDates):
                df = dfDates
            divide = False  # dividing here is wrong. Has already been divided
            if (
                divide
                and isColumnMultiplied in paramDict
                and paramDict[isColumnMultiplied]
            ):
                columns, schema = get_schema_and_column_names(df)
                exprs = []
                for column in valueCols:
                    if (
                        column in columns
                        and unitsName not in column
                        and volumeName not in column
                        and netMarginName not in column
                    ):
                        exprs.append((pl.col(column) / multiplyConstant).alias(column))
                if exprs:
                    df = df.with_columns(exprs)
            with downloadExpander:
                ui.caption(
                    """To download the filtered dataset hit the button below.     
                                    """
                )
                csv = convert_df(df)
                label = "Press to Download"
                download_text_data(csv, label, dfFilteredName)
    return None


def download_plot_file(dfCopy, fileName):
    namingParams = get_naming_params()
    dfPlanName = namingParams["dfPlanName"]
    df = duplicate_dataframe(dfCopy)
    # materialize a 0-based index column named "index" (pandas reset_index equivalent)
    df = df.with_row_count(name="index", offset=0)
    ui.caption("""To download the plot dataset hit the button below.     
                                    """)
    csv = convert_df(df)
    label = "Press to Download "
    download_text_data(csv, label, fileName)
    return None


def download_merged_file(dfDict, colDict, paramDict):
    namingParams = get_naming_params()
    prepareMergedFileForDownload = namingParams["prepareMergedFileForDownload"]
    dfMergedName = namingParams["dfMergedName"]
    loadDataTabKey = namingParams["loadDataTab"]
    if (
        prepareMergedFileForDownload in paramDict
        and paramDict[prepareMergedFileForDownload]
    ):
        if dfMergedName in dfDict:
            with colDict[loadDataTabKey][2]:
                downloadExpander = ui.expander("➕Download merged dataset")
                with downloadExpander:
                    ui.caption(
                        """To download the merged dataset hit the button below."""
                    )
                    pq_bytes = convert_df_parquet(dfDict[dfMergedName])
                    ui.download_button(
                        label="Download Parquet",
                        data=pq_bytes,
                        file_name=f"{dfMergedName}.parquet",
                        mime="application/x-parquet",
                        key="merged_pq_dl",
                    )
                    csv_bytes = convert_df_csv(dfDict[dfMergedName])
                    ui.download_button(
                        label="Download CSV",
                        data=csv_bytes,
                        file_name=f"{dfMergedName}.csv",
                        mime="text/csv",
                        key="merged_csv_dl",
                    )
    return None


def set_up_cohort_column_widget(
    df, paramDict, chartDict, automateDict, indexCols, colArray
):
    """
    chose columns where unique item count to be used as metric
    """

    namingParams = get_naming_params()
    cohortColumnLabel = namingParams["cohortColumnLabel"]
    chosenCohortColumn = namingParams["chosenCohortColumn"]
    lostAndDroppedColumn = namingParams["lostAndDroppedColumn"]
    periodName = namingParams["periodName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    allPeriodsList = namingParams["allPeriodsList"]
    selectedPeriods = namingParams["selectedPeriods"]
    countMetricsColumnKey = namingParams["countMetricsColumn"]
    columnHash = paramDict[namingParams["columnHash"]]
    indexColsSelectBox = copy.deepcopy(indexCols)
    if periodName in indexColsSelectBox:
        indexColsSelectBox.remove(periodName)
    indexColsSelectBox.insert(0, nothingFilteredName)
    columns, schema = get_schema_and_column_names(df)
    chartDict[chosenCohortColumn] = notMetConditionValue
    chartDict[lostAndDroppedColumn] = notMetConditionValue
    chartDict[countMetricsColumnKey] = notMetConditionValue
    okPeriods = False
    if periodName in columns:
        minLength = 1
        if (
            allPeriodsList in paramDict
            and len(paramDict[allPeriodsList]) > minLength
            and selectedPeriods in paramDict
            and len(paramDict[selectedPeriods]) > minLength
        ):
            okPeriods = True
        if okPeriods:
            with colArray[0]:
                container = ui.container()
                hashKey = get_hashed_key_for_widgets(chosenCohortColumn, columnHash)
                tooltip = """Dimension to analyse time-span cohorts 
                    """
                index, warn = insert_json_value(
                    "index",
                    0,
                    automateDict,
                    indexColsSelectBox,
                    chosenCohortColumn,
                    None,
                    return_warning=True,
                )
                chartDict[chosenCohortColumn] = container.selectbox(
                    cohortColumnLabel,
                    indexColsSelectBox,
                    help=tooltip,
                    index=index,
                    key=hashKey,
                )
                if warn:
                    show_warning_ui(warn)
                ui.caption(
                    """✳️Dimension to analyse time-span cohorts, lost items, unique items, and like for like. 
                                    """
                )
                if chartDict[chosenCohortColumn] not in [nothingFilteredName]:
                    chartDict[lostAndDroppedColumn] = chartDict[chosenCohortColumn]
                    chartDict[countMetricsColumnKey] = chartDict[chosenCohortColumn]
    return chartDict


def make_slider_for_filter(
    df,
    column,
    isNumericFilter,
    isNumberColumn,
    tooltip,
    hashKey,
    filterType,
    autoValues,
):
    namingParams = get_naming_params()
    chooseToIncludeItemsLabel = namingParams["chooseToIncludeItemsLabel"]
    chooseToExcludeItemsLabel = namingParams["chooseToExcludeItemsLabel"]
    filterValues = None
    try:
        if isinstance(df, pl.DataFrame):
            df = df.with_columns(pl.col(column).cast(pl.Int64))
            isNumberColumn = True
            _min = int(df[column].min())
            _max = int(df[column].max())
        elif isinstance(df, pl.LazyFrame):
            df = df.with_columns(pl.col(column).cast(pl.Int64))
            isNumberColumn = True
            stats = df.select(
                [
                    pl.col(column).min().alias("min"),
                    pl.col(column).max().alias("max"),
                ]
            ).collect()
            _min = int(stats["min"][0])
            _max = int(stats["max"][0])
        else:
            # Fallback: coerce via Polars and compute bounds
            df = pl.DataFrame(df).with_columns(pl.col(column).cast(pl.Int64))
            isNumberColumn = True
            _min = int(df[column].min())
            _max = int(df[column].max())
        if len(autoValues) == 2:
            _low, _high = _min, _max
            if autoValues[0] >= _min:
                _low = autoValues[0]
            if autoValues[1] <= _max:
                _high = autoValues[1]
            initialValue = (_low, _high)
        elif filterType == "include":
            initialValue = (_min, _max)
        elif filterType == "exclude":
            initialValue = (_min, _min)
        if filterType == "include":
            label = chooseToIncludeItemsLabel
            message = """✳️Select the value range you want to include in the analysis.
                            """
            tooltip = """Select the value range you want to include in the analysis.
                    """
        else:
            label = chooseToExcludeItemsLabel
            message = """✳️Select the value range you want to exclude from the analysis.
                            """
            tooltip = """Select the value range you want to exclude from the analysis.
                            """
        userNumInput = ui.slider(
            label=label,
            min_value=_min,
            max_value=_max,
            value=initialValue,
            help=tooltip,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        if userNumInput[0] != _min or userNumInput[1] != _max:
            if filterType == "include":
                if userNumInput[1] != _min:
                    filterValues = userNumInput
                    isNumericFilter = True
            else:
                if userNumInput[0] != _min or userNumInput[1] != _min:
                    filterValues = userNumInput
                    isNumericFilter = True
    except Exception as e:  # nosec B110
        logging.exception(e)
        ui.error("Something went wrong while setting up the numeric filter slider.")
    return isNumericFilter, isNumberColumn, filterValues


def add_checkbox(
    hashKey, checkType, firstKey, secondKey, col, disabled, planPlaybackDict, planDict
):
    label = "New " + checkType.lower()
    choiceKey = "item" + firstKey + secondKey
    choiceKey = checkType + firstKey + secondKey
    hashKey = hashKey + choiceKey
    with col:
        value = False
        value = insert_json_value(
            "checkbox", value, planPlaybackDict, None, choiceKey, None
        )
        modify = ui.checkbox(
            label=label,
            key=hashKey,
            value=value,
            disabled=disabled,
            label_visibility="visible",
        )
        planDict[choiceKey] = modify
    return modify, planDict


def prepare_variance_chart_images(chartDict, columnArray, paramDict):
    namingParams = get_naming_params()
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    mainDimension = namingParams["mainDimension"]
    plotSmallMultiplesWaterfall = namingParams["plotSmallMultiplesWaterfall"]
    if processingChoice in chartDict and chartDict[processingChoice] in [
        runVariableDimensionalAnalysis,
        runOneDimensionalAnalysis,
    ]:
        if chartDict[processingChoice] == runVariableDimensionalAnalysis:
            chartName = "vertical_waterfall_variable_dimension"
        elif chartDict[processingChoice] == runOneDimensionalAnalysis:
            if mainDimension not in chartDict:
                chartName = "vertical_waterfall"
            elif (
                plotSmallMultiplesWaterfall in chartDict
                and chartDict[plotSmallMultiplesWaterfall]
            ):
                chartName = "vertical_waterfall_small_multiples"
            else:
                chartName = "vertical_waterfall_fix_dimension"
        paramDict = show_chart_image(chartName, columnArray[2], paramDict)
    return paramDict


def show_record_button(paramDict, chartDict, colArray):
    """Display buttons to record and navigate plots."""
    if chartDict is None:
        chartDict = {}
    namingParams = get_naming_params()
    recordRunLabel = namingParams["recordRunLabel"]
    updateCurrentRunLabel = namingParams["updateCurrentRunLabel"]
    nextRunLabel = namingParams["nextRunLabel"]
    addNewRunLabel = namingParams["addNewRunLabel"]
    addNewRunKey = namingParams["addNewRunName"]
    deleteRunLabel = namingParams["deleteRunLabel"]
    deleteRunKey = namingParams["deleteRunName"]
    previousRunLabel = namingParams["previousRunLabel"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    recordRunKey = namingParams["recordRunName"]
    nextRunKey = namingParams["nextRunName"]
    previousRunKey = namingParams["previousRunName"]
    updateCurrentRunKey = namingParams["updateCurrentRunName"]
    runNumber = namingParams["runNumberName"]
    totalRunsKey = namingParams["totalNberOfRunsName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    columnHash = namingParams["columnHash"]
    if columnHash in paramDict:
        columnHash = paramDict[namingParams["columnHash"]]
        chartDict[deleteRunKey] = notMetConditionValue
        chartDict[addNewRunKey] = notMetConditionValue
        chartDict[recordRunKey] = notMetConditionValue
        chartDict[nextRunKey] = notMetConditionValue
        chartDict[previousRunKey] = notMetConditionValue
        chartDict[updateCurrentRunKey] = notMetConditionValue
        submit = notMetConditionValue
        if totalRunsKey in session_state and runNumber in session_state:
            if session_state[totalRunsKey] > session_state[runNumber]:
                with colArray[2]:
                    hashKey = get_hashed_key_for_widgets(nextRunKey, columnHash)
                    message = """✳️Next plot."""
                    chartDict[nextRunKey] = ui.button(
                        label=nextRunLabel, help=None, key=hashKey, type="secondary"
                    )
                    ui.caption(message)
                with colArray[1]:
                    if session_state[runNumber] > 1:
                        hashKey = get_hashed_key_for_widgets(previousRunKey, columnHash)
                        message = """✳️Previous plot."""
                        chartDict[previousRunKey] = ui.button(
                            label=previousRunLabel,
                            help=None,
                            key=hashKey,
                            type="secondary",
                        )
                        ui.caption(message)
                colArray = make_three_col_width_array()
                with colArray[0]:
                    hashKey = get_hashed_key_for_widgets(
                        updateCurrentRunKey, columnHash
                    )
                    message = """✳️Update plot in playback file."""
                    chartDict[updateCurrentRunKey] = ui.button(
                        label=updateCurrentRunLabel,
                        help=None,
                        key=hashKey,
                        type="secondary",
                    )
                    ui.caption(message)
                with colArray[1]:
                    hashKey = get_hashed_key_for_widgets(addNewRunKey, columnHash)
                    message = """✳️Add new plot to playback file."""
                    chartDict[addNewRunKey] = ui.button(
                        label=addNewRunLabel, help=None, key=hashKey, type="secondary"
                    )
                    ui.caption(message)
                with colArray[2]:
                    hashKey = get_hashed_key_for_widgets(deleteRunKey, columnHash)
                    message = """✳️Drop plot from playback file."""
                    chartDict[deleteRunKey] = ui.button(
                        label=deleteRunLabel, help=None, key=hashKey, type="secondary"
                    )
                    ui.caption(message)
            elif session_state[totalRunsKey] == session_state[runNumber]:
                with colArray[2]:
                    if session_state[runNumber] > 1:
                        hashKey = get_hashed_key_for_widgets(previousRunKey, columnHash)
                        message = """✳️Previous plot."""
                        chartDict[previousRunKey] = ui.button(
                            label=previousRunLabel,
                            help=None,
                            key=hashKey,
                            type="secondary",
                        )
                        ui.caption(message)
                colArray = make_three_col_width_array()
                with colArray[0]:
                    hashKey = get_hashed_key_for_widgets(
                        updateCurrentRunKey, columnHash
                    )
                    message = """✳️Update plot in playback file."""
                    chartDict[updateCurrentRunKey] = ui.button(
                        label=updateCurrentRunLabel,
                        help=None,
                        key=hashKey,
                        type="secondary",
                    )
                    ui.caption(message)
                with colArray[1]:
                    hashKey = get_hashed_key_for_widgets(addNewRunKey, columnHash)
                    message = """✳️Add plot to playback file."""
                    chartDict[addNewRunKey] = ui.button(
                        label=addNewRunLabel, help=None, key=hashKey, type="secondary"
                    )
                    ui.caption(message)
                with colArray[2]:
                    hashKey = get_hashed_key_for_widgets(deleteRunKey, columnHash)
                    message = """✳️Drop plot from playback file."""
                    chartDict[deleteRunKey] = ui.button(
                        label=deleteRunLabel, help=None, key=hashKey, type="secondary"
                    )
                    ui.caption(message)
        else:
            with colArray[1]:
                message = """✳️Add plot to playback file."""
                hashKey = get_hashed_key_for_widgets(recordRunKey, columnHash)
                chartDict[recordRunKey] = ui.button(
                    label=recordRunLabel, help=None, key=hashKey, type="secondary"
                )
                ui.caption(message)
    return chartDict


def submit_variance_charts(colArray, paramDict, chartDict):
    with colArray[0]:
        bridgeSubmit, chartDict = show_submit_button(paramDict, chartDict)
    return bridgeSubmit, chartDict


def set_up_move_row_to_main_report_widgets(
    drilldownParamsDict, loopWidgetDict, automateDict, number, col2, expander
):
    """
    setting up widgets to identify drill down row to move to main report
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    emojiNumberDict = configParams[namingParams["emojiNumberDict"]]
    invertedEmojiNumberDict = configParams[namingParams["invertedEmojiNumberDict"]]
    notMetConditionValue = namingParams["notMetConditionValue"]
    chosenDrilldownRow = namingParams["chosenDrilldownRow"]
    toMoveDrilldownRowsIndexLabel = namingParams["toMoveDrilldownRowsIndexLabel"]
    toMoveDrilldownRowsIndexName = namingParams["toMoveDrilldownRowsIndexName"]
    numberOfRowResults = namingParams["numberOfRowResults"]
    # toMoveDrilldownRowsIndexLabel=toMoveDrilldownRowsIndexLabel+" #"+str(number)
    if drilldownParamsDict[number][chosenDrilldownRow] != 0:
        drillDownRowsList = list(
            range(1, drilldownParamsDict[number][numberOfRowResults] + 1)
        )
        emojiDrillDownRowsList = []
        for element in drillDownRowsList:
            emojiDrillDownRowsLiui.append(emojiNumberDict[element])
        with col2:
            with expander:
                tooltip = """Select one or more rows of the drill down report you want to move back to 
                        the main report
            """
                value = None
                value = insert_json_value(
                    "filterColumn",
                    value,
                    automateDict,
                    emojiDrillDownRowsList,
                    toMoveDrilldownRowsIndexLabel,
                    number,
                )
                drilldownParamsDict[number][toMoveDrilldownRowsIndexLabel] = value
                chosenEmojiArray = ui.multiselect(
                    label=toMoveDrilldownRowsIndexLabel,
                    options=emojiDrillDownRowsList,
                    default=value,
                    help=tooltip,
                    key="toMoveDrilldownRowsIndex" + str(number),
                    max_selections=None,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️Select the rows of the drill down report you want to move back to 
                        the main report. A new report will be generated in which the selected rows are inserted at the position of the corresponding drilled down row.  
                        """
                )
                if len(chosenEmojiArray) > 0:
                    drillDownRowsArray = []
                    for element in chosenEmojiArray:
                        drillDownRowsArray.append(
                            invertedEmojiNumberDict[element.strip()]
                        )
                    drilldownParamsDict[number][
                        toMoveDrilldownRowsIndexName
                    ] = drillDownRowsArray
    return drilldownParamsDict


def set_max_nodes(paramDict, drillDownSuffix, automateDict):
    """
    putting widgets together to be able to easily turn them off and on
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    maxNumberOfNodesLabel = namingParams["maxNumberOfNodesLabel"]
    maxNumberOfNodes = namingParams["maxNumberOfNodes"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    parameterSettingLabel = namingParams["parameterSettingLabel"]
    parameterSetting = namingParams["parameterSetting"]
    largestCombinationOption = namingParams["largestCombinationOption"]
    limitFirstResultSizeOption = namingParams["limitFirstResultSizeOption"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    moreNodesOption = namingParams["moreNodesOption"]
    moreGrowthOption = namingParams["moreGrowthOption"]
    parameterSettingKey = "parameterSetting" + drillDownSuffix
    radioOptions = [
        largestCombinationOption,
        limitFirstResultSizeOption,
        moreNodesOption,
        moreGrowthOption,
    ]
    valueMaxNodes = 0
    valueParamSetting = 0
    if paramDict[letMeChooseOption]:
        valueMaxNodes = insert_json_value(
            "slider", valueMaxNodes, automateDict, [], maxNumberOfNodes, None
        )
        paramDict[maxNumberOfNodes] = ui.slider(
            label=maxNumberOfNodesLabel,
            min_value=0,
            max_value=8,
            value=valueMaxNodes,
            step=1,
            format=None,
            key="maxNumberOfNodes" + drillDownSuffix,
            label_visibility="visible",
        )
        ui.caption("""✳️Sets max number of nodes in result rows.""")
    else:
        paramDict[maxNumberOfNodes] = valueMaxNodes
    return paramDict


def set_up_bridge_analysis_widgets(
    paramDict, chartDict, automateDict, colArray, expander1Array
):
    """
    set up all widgets to run bridge analysis
    """
    namingParams = get_naming_params()
    chosenDrilldownRow = namingParams["chosenDrilldownRow"]
    processingChoice = namingParams["processingChoice"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    isdataset = namingParams["isdataset"]
    drilldownParamsDictName = namingParams["drilldownParamsDictName"]
    loopParamsDictName = namingParams["loopParamsDictName"]
    colWidthArray = [1, 1, 1, 1]
    drilldownParamsDict = {}
    loopParamsDict = {}
    if isdataset in paramDict and paramDict[isdataset]:
        if (
            processingChoice in chartDict
            and chartDict[processingChoice] == runVariableDimensionalAnalysis
        ):
            # paramDict,expander1Array[3]=set_max_change_widget(paramDict,col1Array[3],expander1Array[3])
            chartDict = select_drilldown_all_results(
                paramDict, chartDict, automateDict, colArray
            )
            chartDict, paramDict = get_fix_scales_variance(
                paramDict, chartDict, automateDict, colArray
            )
            loopParamsDict, expander1Array = set_up_loop_widgets(
                paramDict, automateDict, colArray[2], expander1Array
            )
            drilldownParamsDict[1], drilldownParamsDict[2] = {}, {}
            drilldownParamsDict[3], drilldownParamsDict[4], drilldownParamsDict[5] = (
                {},
                {},
                {},
            )
            drillDownNumber = 1

            if (
                drilldownParamsDictName in automateDict
                and str(drillDownNumber) in automateDict[drilldownParamsDictName]
            ):
                autoDrillDict = automateDict[drilldownParamsDictName][
                    str(drillDownNumber)
                ]
            else:
                autoDrillDict = copy.deepcopy(automateDict)
            drilldownParamsDict, expander = set_up_drilldown_widgets(
                drilldownParamsDict,
                loopParamsDict,
                paramDict,
                chartDict,
                autoDrillDict,
                drillDownNumber,
                colArray[0],
            )
            drilldownParamsDict = set_up_move_row_to_main_report_widgets(
                drilldownParamsDict,
                loopParamsDict,
                automateDict,
                drillDownNumber,
                colArray[0],
                expander,
            )
            if drilldownParamsDict[drillDownNumber][chosenDrilldownRow] > 0:
                drillDownNumber = 2
                if (
                    drilldownParamsDictName in automateDict
                    and str(drillDownNumber) in automateDict[drilldownParamsDictName]
                ):
                    autoDrillDict = automateDict[drilldownParamsDictName][
                        str(drillDownNumber)
                    ]
                drilldownParamsDict, expander = set_up_drilldown_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    paramDict,
                    chartDict,
                    autoDrillDict,
                    drillDownNumber,
                    colArray[0],
                )
                drilldownParamsDict = set_up_move_row_to_main_report_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    automateDict,
                    drillDownNumber,
                    colArray[0],
                    expander,
                )
            if drilldownParamsDict[drillDownNumber][chosenDrilldownRow] > 0:
                drillDownNumber = 3
                if (
                    drilldownParamsDictName in automateDict
                    and str(drillDownNumber) in automateDict[drilldownParamsDictName]
                ):
                    autoDrillDict = automateDict[drilldownParamsDictName][
                        str(drillDownNumber)
                    ]
                drilldownParamsDict, expander = set_up_drilldown_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    paramDict,
                    chartDict,
                    autoDrillDict,
                    drillDownNumber,
                    colArray[0],
                )
                drilldownParamsDict = set_up_move_row_to_main_report_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    automateDict,
                    drillDownNumber,
                    colArray[0],
                    expander,
                )
            if drilldownParamsDict[drillDownNumber][chosenDrilldownRow] > 0:
                drillDownNumber = 4
                if (
                    drilldownParamsDictName in automateDict
                    and str(drillDownNumber) in automateDict[drilldownParamsDictName]
                ):
                    autoDrillDict = automateDict[drilldownParamsDictName][
                        str(drillDownNumber)
                    ]
                drilldownParamsDict, expander = set_up_drilldown_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    paramDict,
                    chartDict,
                    autoDrillDict,
                    drillDownNumber,
                    colArray[0],
                )
                drilldownParamsDict = set_up_move_row_to_main_report_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    automateDict,
                    drillDownNumber,
                    colArray[0],
                    expander,
                )
            if drilldownParamsDict[drillDownNumber][chosenDrilldownRow] > 0:
                drillDownNumber = 5
                if (
                    drilldownParamsDictName in automateDict
                    and str(drillDownNumber) in automateDict[drilldownParamsDictName]
                ):
                    autoDrillDict = automateDict[drilldownParamsDictName][
                        str(drillDownNumber)
                    ]
                drilldownParamsDict, expander = set_up_drilldown_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    paramDict,
                    chartDict,
                    autoDrillDict,
                    drillDownNumber,
                    colArray[0],
                )
                drilldownParamsDict = set_up_move_row_to_main_report_widgets(
                    drilldownParamsDict,
                    loopParamsDict,
                    automateDict,
                    drillDownNumber,
                    colArray[0],
                    expander,
                )
        chartDict[loopParamsDictName] = loopParamsDict
        chartDict[drilldownParamsDictName] = drilldownParamsDict
        return paramDict, chartDict
    else:
        return paramDict, chartDict


def get_report_builder_widgets() -> Tuple[
    str,  # ente
    int,  # year
    Optional[BinaryIO],  # zip_file (None se non è zip)
    Optional[BinaryIO],  # excel_file (None se non è excel)
]:
    """
    Widget di input:
      • Denominazione ente
      • Esercizio
      • Upload ZIP *o* Excel
    Ritorna:
      ente, year, zip_file, excel_file
    (uno dei due file è None a seconda del tipo caricato)
    """
    ente = ui.text_input("Reporting entity name", "")
    year = ui.number_input("Accounting period", 2020, 2030, 2024, step=1)

    uploaded = ui.file_uploader(
        "Upload a ZIP file with the table or a single Excel file with one table per sheet.",
        type=["zip", "xlsx"],
    )

    zip_file = excel_file = None
    if uploaded:
        ext = Path(uploaded.name).suffix.lower()
        if ext == ".zip":
            zip_file = uploaded
        elif ext in {".xlsx"}:
            excel_file = uploaded
        else:
            ui.error(
                "Unrecognized format. Only .zip, .xlsx, or .xls files are accepted."
            )

    return ente, year, zip_file, excel_file


# ------------------------------------------------------------------
# your widget – now with dual input
# ------------------------------------------------------------------
def show_research_upload_widget(paramDict, col1Array):
    namingParams = get_naming_params()
    col2Array = make_three_col_width_array()

    with col1Array[0]:
        ui.markdown(
            """
            <div style="
                font-size:0.813rem;      /* = 13 px on UI’s base 16 px */
                font-weight:600;
                margin:0 0 4px 0;">      <!-- 4 px gap above the widget -->
            Select All ⇒ Copy ⇒ Paste the Deep-Research text.<br/>
            <em>Do NOT</em> use the ChatGPT copy icon (it loses links). If links
            are missing, upload the HTML/Markdown export instead…
            </div>
            """,
            unsafe_allow_html=True,
        )
        pasted = ui.text_area(
            "Paste deep-research text",
            height=200,
            key="dpaste",
            label_visibility="collapsed",
        )

    with col2Array[0]:
        # ❶ File uploader (optional)
        uploaded = ui.file_uploader(
            "..or upload the Deep-Research PDF/HTML/Markdown export.",
            type=["pdf", "html", "htm", "md", "markdown", "txt"],
            key="deepresearch_uploader",
            accept_multiple_files=False,
        )

    return uploaded, pasted


# ------------------------------------------------------------------
# 2)  Contact details (auto-captured from the authenticated session)
# ------------------------------------------------------------------


def capture_contacts(uploaded, pasted, key):
    """
    Return (email, phone) for notification purposes. No inputs are rendered
    because the authenticated e-mail already exists.
    """
    need_contact = bool(uploaded) or bool(pasted and pasted.strip())
    if not need_contact:
        return "", ""

    session_user = get_authenticated_user()
    session_email = (session_user.email or "").strip() if session_user else ""
    if session_email:
        ui.caption(f"Notifications will be sent to **{session_email}**.")
    else:
        ui.warning(
            "Notifications cannot be sent because no signed-in account was found."
        )

    return session_email, ""


def show_drilldown_widgets(
    drilldownParamsDict, paramDict, chartDict, automateDict, number, expander
):
    """
    shows widgets widgets for drilldown processing
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    numberOfRowResults = namingParams["numberOfRowResults"]
    numberOfRowResultsLabel = namingParams["numberOfRowResultsLabel"]
    maxPercentOfTotalVarianceLabel = namingParams["maxPercentOfTotalVarianceLabel"]
    maxPercentOfTotalVariance = namingParams["maxPercentOfTotalVariance"]
    minPercentOfTotalAmountLabel = namingParams["minPercentOfTotalAmountLabel"]
    minPercentOfTotalAmount = namingParams["minPercentOfTotalAmount"]
    varianceAmountWeight = namingParams["varianceAmountWeight"]
    varianceAmountWeightLabel = namingParams["varianceAmountWeightLabel"]
    numberOfNodesWeight = namingParams["numberOfNodesWeight"]
    numberOfNodesWeightLabel = namingParams["numberOfNodesWeightLabel"]
    uniqueValuesInCombinationWeight = namingParams["uniqueValuesInCombinationWeight"]
    uniqueValuesInCombinationWeightLabel = namingParams[
        "uniqueValuesInCombinationWeightLabel"
    ]
    prepareFileForDownloadLabel = namingParams["prepareFileForDownloadLabel"]
    prepareFileForDownload = namingParams["prepareFileForDownload"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    parameterSetting = namingParams["parameterSetting"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    largestCombinationOption = namingParams["largestCombinationOption"]
    moreNodesOption = namingParams["moreNodesOption"]
    moreGrowthOption = namingParams["moreGrowthOption"]
    minPercentOfTotalVariance = namingParams["minPercentOfTotalVariance"]
    drilldownParamsDictName = namingParams["drilldownParamsDictName"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if (
        drilldownParamsDictName in automateDict
        and str(drillDownNumber) in automateDict[drilldownParamsDictName]
    ):
        autoDrillDict = automateDict[drilldownParamsDictName][str(drillDownNumber)]
    else:
        autoDrillDict = copy.deepcopy(automateDict)

    drilldownParamsDict[number] = set_up_parameter_setting_widget(
        drilldownParamsDict[number],
        chartDict,
        autoDrillDict,
        expander,
        "drilldown" + str(number),
    )
    drilldownParamsDict[number] = set_parameters_on_scenario_option(
        drilldownParamsDict[number]
    )
    with expander:
        defaultNumberOfResults = 5
        if (
            letMeChooseOption in drilldownParamsDict[number]
            and drilldownParamsDict[number][letMeChooseOption] == metConditionValue
        ):
            hashKey = get_hashed_key_for_widgets(
                "numberOfRowsDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][numberOfRowResults] = ui.slider(
                label=numberOfRowResultsLabel,
                min_value=1,
                max_value=10,
                value=defaultNumberOfResults,
                step=1,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
        else:
            drilldownParamsDict[number][numberOfRowResults] = defaultNumberOfResults
        if (
            letMeChooseOption in drilldownParamsDict[number]
            and drilldownParamsDict[number][letMeChooseOption] == metConditionValue
        ):
            hashKey = get_hashed_key_for_widgets(
                "maxPercentDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][maxPercentOfTotalVariance] = ui.slider(
                label=maxPercentOfTotalVarianceLabel,
                min_value=0.2,
                max_value=2.0,
                value=drilldownParamsDict[number][maxPercentOfTotalVariance],
                step=0.1,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
            hashKey = get_hashed_key_for_widgets(
                "minPercentDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][minPercentOfTotalAmount] = ui.slider(
                label=minPercentOfTotalAmountLabel,
                min_value=0.0,
                max_value=1.0,
                value=drilldownParamsDict[number][minPercentOfTotalAmount],
                step=0.001,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
            hashKey = get_hashed_key_for_widgets(
                "varianceAmountWeightDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][varianceAmountWeight] = ui.slider(
                label=varianceAmountWeightLabel,
                min_value=0.2,
                max_value=1.0,
                value=drilldownParamsDict[number][varianceAmountWeight],
                step=0.1,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
            hashKey = get_hashed_key_for_widgets(
                "numberOfNodesWeightDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][numberOfNodesWeight] = ui.slider(
                label=numberOfNodesWeightLabel,
                min_value=0,
                max_value=10,
                value=drilldownParamsDict[number][numberOfNodesWeight],
                step=1,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
            hashKey = get_hashed_key_for_widgets(
                "uniqueValuesInCombinationWeightDrilldownRow" + str(number), columnHash
            )
            drilldownParamsDict[number][uniqueValuesInCombinationWeight] = ui.slider(
                label=uniqueValuesInCombinationWeightLabel,
                min_value=0,
                max_value=10,
                value=drilldownParamsDict[number][uniqueValuesInCombinationWeight],
                step=1,
                format=None,
                key=hashKey,
                label_visibility="visible",
            )
        hashKey = get_hashed_key_for_widgets(
            "prepareFileForDownload" + str(number), columnHash
        )
        drilldownParamsDict[number][prepareFileForDownload] = ui.radio(
            label=prepareFileForDownloadLabel,
            options=booleanRadioOptions,
            index=1,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(
            """✳️If True, the system will prepare a parquet file (CSV optional) for download with 
                        all the children combinations of the drilldown row.
                                    """
        )
    return drilldownParamsDict


def set_up_drilldown_widgets(
    drilldownParamsDict, loopWidgetDict, paramDict, chartDict, automateDict, number, col
):
    """
    setting up widgets for drilldown processing
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    emojiNumberDict = configParams[namingParams["emojiNumberDict"]]
    invertedEmojiNumberDict = configParams[namingParams["invertedEmojiNumberDict"]]
    emojiArrayZeroToTen = configParams[namingParams["emojiArrayZeroToTen"]]
    notMetConditionValue = namingParams["notMetConditionValue"]
    selectDrilldownRowLabel = namingParams["selectDrilldownRowLabel"]
    chosenDrilldownRow = namingParams["chosenDrilldownRow"]
    chosenDrilldownRowLabel = namingParams["chosenDrilldownRowLabel"]
    numberOfRowResults = namingParams["numberOfRowResults"]
    drilldownAllResults = namingParams["drilldownAllResults"]
    columnHash = paramDict[namingParams["columnHash"]]
    drilldownAllResults = chartDict[drilldownAllResults]
    chosenNumberOfRowResults = loopWidgetDict[numberOfRowResults]
    value = 0
    if drilldownAllResults:
        value = number
    with col:
        tooltip = """Select the row you want to drilldown on.
      """
        hashKey = get_hashed_key_for_widgets(
            "chosenDrilldownRow" + str(number), columnHash
        )
        # drilldownParamsDict[number][chosenDrilldownRow]=ui.slider(label=chosenDrilldownRowLabel, min_value=1, max_value=chosenNumberOfRowResults,help=tooltip,
        #                                             value=value, step=1, format=None, key=hashKey,label_visibility="visible")
        emojiOptions = emojiArrayZeroToTen[: chosenNumberOfRowResults + 1]
        value = insert_json_value(
            "slider",
            emojiOptions[value],
            automateDict,
            emojiOptions,
            chosenDrilldownRow,
            number,
        )
        chosenEmoji = ui.select_slider(
            label=chosenDrilldownRowLabel,
            options=emojiOptions,
            value=value,
            key=hashKey,
            label_visibility="visible",
        )
        drilldownParamsDict[number][chosenDrilldownRow] = invertedEmojiNumberDict[
            chosenEmoji.strip()
        ]
        ui.caption("""✳️Select the row you would like to drilldown on. 
                        """)
        expander = ui.expander(
            """➕ Row """ + chosenEmoji + """ drilldown variance options"""
        )
        if drilldownParamsDict[number][chosenDrilldownRow] == 0:
            drilldownParamsDict[number][chosenDrilldownRow] = notMetConditionValue
        else:
            drilldownParamsDict = show_drilldown_widgets(
                drilldownParamsDict,
                paramDict,
                chartDict,
                automateDict,
                number,
                expander,
            )
    return drilldownParamsDict, expander


def set_up_loop_widgets(paramDict, automateDict, col, expander):
    """
    we set up the sliders that control how the loops work
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    numberOfRowResultsLabel = namingParams["numberOfRowResultsLabel"]
    maxPercentOfTotalVarianceLabel = namingParams["maxPercentOfTotalVarianceLabel"]
    maxPercentOfTotalVariance = namingParams["maxPercentOfTotalVariance"]
    maxPercentOfTotalAmounteLabel = namingParams["maxPercentOfTotalAmountLabel"]
    minPercentOfTotalAmountLabel = namingParams["minPercentOfTotalAmountLabel"]
    minPercentOfTotalAmount = namingParams["minPercentOfTotalAmount"]
    numberOfRowResults = namingParams["numberOfRowResults"]
    varianceAmountWeight = namingParams["varianceAmountWeight"]
    varianceAmountWeightLabel = namingParams["varianceAmountWeightLabel"]
    numberOfNodesWeight = namingParams["numberOfNodesWeight"]
    uniqueValuesInCombinationWeight = namingParams["uniqueValuesInCombinationWeight"]
    numberOfNodesWeightLabel = namingParams["numberOfNodesWeightLabel"]
    uniqueValuesInCombinationWeightLabel = namingParams[
        "uniqueValuesInCombinationWeightLabel"
    ]
    minPercentOfTotalVariance = namingParams["minPercentOfTotalVariance"]
    parameterSetting = namingParams["parameterSetting"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    metConditionValue = namingParams["metConditionValue"]
    largestCombinationOption = namingParams["largestCombinationOption"]
    limitFirstResultSizeOption = namingParams["moreGrowthOption"]
    moreNodesOption = namingParams["moreNodesOption"]
    moreGrowthOption = namingParams["moreGrowthOption"]
    aggregationChoiceLabel = namingParams["aggregationChoiceLabel"]
    aggregationChoice = namingParams["aggregationChoice"]
    aggregationChoiceArray = namingParams["aggregationChoiceArray"]
    aggregationChoiceArray = configParams[aggregationChoiceArray]
    loopWidgetDict = {}
    paramDict = set_parameters_on_scenario_option(paramDict)
    with col:
        with expander:
            defaultAggregationIndex = 0
            if (
                letMeChooseOption in paramDict
                and paramDict[letMeChooseOption] == metConditionValue
            ):
                defaultAggregationIndex = insert_json_value(
                    "index",
                    defaultAggregationIndex,
                    automateDict,
                    aggregationChoiceArray,
                    aggregationChoice,
                    None,
                )
                loopWidgetDict[aggregationChoice] = ui.radio(
                    label=aggregationChoiceLabel,
                    options=aggregationChoiceArray,
                    index=defaultAggregationIndex,
                    key=aggregationChoice,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️The different parameters (variance value, variance % change, number of nodes,...) need to be aggregated in some way
                  so the results can be ranked. This can be done with different normalization approaches. Use the default or try if another fits 
                  your data better. 
                  """
                )
            else:
                loopWidgetDict[aggregationChoice] = aggregationChoiceArray[
                    defaultAggregationIndex
                ]
            defaultNumberOfResults = 5
            if (
                letMeChooseOption in paramDict
                and paramDict[letMeChooseOption] == metConditionValue
            ):
                minValue, maxValue = 1, 10
                choiceArray = list(range(minValue, maxValue + 1))
                value = insert_json_value(
                    "slider",
                    paramDict[numberOfRowResults],
                    automateDict,
                    choiceArray,
                    numberOfRowResults,
                    None,
                )
                loopWidgetDict[numberOfRowResults] = ui.slider(
                    label=numberOfRowResultsLabel,
                    min_value=minValue,
                    max_value=maxValue,
                    value=value,
                    step=1,
                    format=None,
                    key="numberOfRows",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️Sets the number of rows in the returned result dataset."""
                )
            else:
                loopWidgetDict[numberOfRowResults] = defaultNumberOfResults
            if (
                letMeChooseOption in paramDict
                and paramDict[letMeChooseOption] == metConditionValue
            ):
                value = insert_json_value(
                    "slider",
                    paramDict[maxPercentOfTotalVariance],
                    automateDict,
                    [],
                    maxPercentOfTotalVariance,
                    None,
                )
                loopWidgetDict[maxPercentOfTotalVariance] = ui.slider(
                    label=maxPercentOfTotalVarianceLabel,
                    min_value=0.2,
                    max_value=2.0,
                    value=value,
                    step=0.2,
                    format=None,
                    key="maxPercent",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️Sets the maximum "size" of each item in the returned result dataset. 
                  """
                )
                value = insert_json_value(
                    "slider",
                    paramDict[minPercentOfTotalAmount],
                    automateDict,
                    [],
                    minPercentOfTotalAmount,
                    None,
                )
                loopWidgetDict[minPercentOfTotalAmount] = ui.slider(
                    label=minPercentOfTotalAmountLabel,
                    min_value=0.0,
                    max_value=0.1,
                    value=value,
                    step=0.01,
                    format=None,
                    key="minPercent",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️Sets the minimum "size" of each item in the returned result dataset. 
                  """
                )
                value = insert_json_value(
                    "slider",
                    paramDict[varianceAmountWeight],
                    automateDict,
                    [],
                    varianceAmountWeight,
                    None,
                )
                loopWidgetDict[varianceAmountWeight] = ui.slider(
                    label=varianceAmountWeightLabel,
                    min_value=0.2,
                    max_value=1.0,
                    value=value,
                    step=0.1,
                    format=None,
                    key="varianceAmountWeight",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️If set to 1, result items are weighted in proportion to their absolute 
                        variance value. Otherwise weight will also be given to the item's % change.  
                  """
                )
                value = insert_json_value(
                    "slider",
                    paramDict[numberOfNodesWeight],
                    automateDict,
                    [],
                    numberOfNodesWeight,
                    None,
                )
                loopWidgetDict[numberOfNodesWeight] = ui.slider(
                    label=numberOfNodesWeightLabel,
                    min_value=0,
                    max_value=10,
                    value=value,
                    step=1,
                    format=None,
                    key="numberOfNodesWeight",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️If set to 0, the app will not give weight to the number of nodes of a given potential result row. 
                        Otherwise, results with more nodes will be weighted more. 
                  """
                )
                value = insert_json_value(
                    "slider",
                    paramDict[uniqueValuesInCombinationWeight],
                    automateDict,
                    [],
                    uniqueValuesInCombinationWeight,
                    None,
                )
                loopWidgetDict[uniqueValuesInCombinationWeight] = ui.slider(
                    label=uniqueValuesInCombinationWeightLabel,
                    min_value=0,
                    max_value=10,
                    value=value,
                    step=1,
                    format=None,
                    key="uniqueValuesInCombinationWeight",
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️If set to 0, the app will not give weight to the number of total items contained in the columns of a given result row. 
                        Otherwise results chosen out of sets of columns with more items will be weighted more.
                  """
                )
    return loopWidgetDict, expander


def select_drilldown_all_results(paramDict, chartDict, automateDict, colArray):
    """
    choice if dimensions need to be object
    """
    namingParams = get_naming_params()
    drilldownAllResultsLabel = namingParams["drilldownAllResultsLabel"]
    drilldownAllResults = namingParams["drilldownAllResults"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    with colArray[0]:
        tooltip = """True if you want the app to attemp to built a drilldown report for each result row."""
        hashKey = get_hashed_key_for_widgets(drilldownAllResults, columnHash)
        index = 1
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, drilldownAllResults, None
        )
        index = 1
        chartDict[drilldownAllResults] = ui.radio(
            label=drilldownAllResultsLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            help=tooltip,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(
            """✳️If True, the app will build a drilldown report for each result row. Alternatively, you can select the rows to drilldown below."""
        )
    return chartDict


def get_other_metrics(df, chartDict, automateDict, paramDict, valueCols):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    nonMetricNumericColumns = namingParams["nonMetricNumericColumns"]
    xAxisMetric = namingParams["xAxisMetric"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    xAxisLabel = namingParams["xAxisLabel"]
    columnHash = paramDict[namingParams["columnHash"]]
    columns, schema = get_schema_and_column_names(df)
    choiceArray = valueCols
    if unitsName in columns:
        if pricePerUnitName not in choiceArray:
            choiceArray.append(pricePerUnitName)
    if volumeName in columns:
        if pricePerVolumeName not in choiceArray:
            choiceArray.append(pricePerVolumeName)
    if (
        unitsName in columns
        and discountName in columns
        and netOfDiscountName in columns
    ):
        if pricePerUnitNetDiscountName not in choiceArray:
            choiceArray.append(pricePerUnitNetDiscountName)
    if (
        volumeName in columns
        and discountName in columns
        and netOfDiscountName in columns
    ):
        if pricePerVolumeNetDiscountName not in choiceArray:
            choiceArray.append(pricePerVolumeNetDiscountName)
    colsSelectBox = choiceArray + paramDict[nonMetricNumericColumns]
    chartDict[xAxisMetric] = notMetConditionValue
    if len(colsSelectBox) > 1:
        message = """✳️Select the metric to plot on the X axis of the plot."""
        tooltip = """Select the metric to plot on the X axis of the plot."""
        hashKey = get_hashed_key_for_widgets("xAxisMetric", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, colsSelectBox, xAxisMetric, None
        )
        chartDict[xAxisMetric] = ui.selectbox(
            label=xAxisLabel,
            options=colsSelectBox,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    elif len(colsSelectBox) == 1:
        chartDict[xAxisMetric] = colsSelectBox[0]
    return chartDict


def get_sorting_axis(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    sortAxis = namingParams["sortAxis"]
    sortAxisLabel = namingParams["sortAxisLabel"]
    xAxisSort = namingParams["xAxisSort"]
    yAxisSort = namingParams["yAxisSort"]
    sortOptions = [yAxisSort, xAxisSort]
    columnHash = paramDict[namingParams["columnHash"]]
    message = """✳️Select axis metric to sort on."""
    tooltip = """Select axis metric to sort on."""
    hashKey = get_hashed_key_for_widgets("sortAxis", columnHash)
    index = 0
    index = insert_json_value("index", index, automateDict, sortOptions, sortAxis, None)
    chartDict[sortAxis] = ui.radio(
        label=sortAxisLabel,
        options=sortOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def get_multiplied_dimension(chartDict):
    namingParams = get_naming_params()
    multipliedMetric = namingParams["multipliedMetric"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    costPerUnitName = namingParams["costPerUnitName"]
    costPerVolumeName = namingParams["costPerVolumeName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    discountName = namingParams["discountName"]
    marginName = namingParams["marginName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metricsToChose = []
    chosenDimensionArray = []
    chartDict[multipliedMetric] = notMetConditionValue
    if (
        yAxisMetric in chartDict
        and chartDict[yAxisMetric]
        and chartDict[yAxisMetric] != None
    ):
        if (
            xAxisMetric in chartDict
            and chartDict[xAxisMetric]
            and chartDict[xAxisMetric] != None
        ):
            chosenDimensionArray = [chartDict[xAxisMetric], chartDict[yAxisMetric]]
            if (
                pricePerUnitName in chosenDimensionArray
                and unitsName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = monetaryName
            elif (
                costPerUnitName in chosenDimensionArray
                and unitsName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = monetaryName
            elif (
                pricePerUnitNetDiscountName in chosenDimensionArray
                and unitsName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = netOfDiscountName
            elif (
                pricePerVolumeName in chosenDimensionArray
                and volumeName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = monetaryName
            elif (
                costPerVolumeName in chosenDimensionArray
                and volumeName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = monetaryName
            elif (
                pricePerVolumeNetDiscountName in chosenDimensionArray
                and volumeName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = netOfDiscountName
            elif (
                discountInPercentName in chosenDimensionArray
                and monetaryName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = discountName
            elif (
                marginInPercentName in chosenDimensionArray
                and monetaryName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = marginName
            elif (
                marginInPercentOfNetSalesName in chosenDimensionArray
                and netOfDiscountName in chosenDimensionArray
            ):
                chartDict[multipliedMetric] = marginName
    return chartDict


def get_compatible_metrics_for_barmekko(chosenMetric, metricArray):
    namingParams = get_naming_params()
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    costPerUnitName = namingParams["costPerUnitName"]
    costPerVolumeName = namingParams["costPerVolumeName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    discountInPercentName = namingParams["discountInPercentName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    monetaryName = namingParams["monetaryLocalCurrencyName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    metricsToChose = []
    possibilityDict = {
        pricePerUnitName: [unitsName],
        costPerUnitName: [unitsName],
        pricePerUnitNetDiscountName: [unitsName],
        pricePerVolumeName: [volumeName],
        costPerVolumeName: [volumeName],
        pricePerVolumeNetDiscountName: [volumeName],
        discountInPercentName: [monetaryName],
        marginInPercentName: [monetaryName],
        marginInPercentOfNetSalesName: [netOfDiscountName],
    }
    inversePossibilityDict = {
        unitsName: [pricePerUnitName, costPerUnitName, pricePerUnitNetDiscountName],
        volumeName: [
            pricePerVolumeName,
            costPerVolumeName,
            pricePerVolumeNetDiscountName,
        ],
        monetaryName: [discountInPercentName, marginInPercentName],
        netOfDiscountName: [marginInPercentOfNetSalesName],
    }

    allPossibilityDict = possibilityDict | inversePossibilityDict
    if chosenMetric and chosenMetric in allPossibilityDict:
        possibleMetrics = allPossibilityDict[chosenMetric]
        for metric in possibleMetrics:
            if metric in metricArray:
                metricsToChose.append(metric)
    else:
        for metric in metricArray:
            if (
                metric in allPossibilityDict
                and len(list(set(metricArray) & set(allPossibilityDict[metric]))) > 0
            ):
                metricsToChose.append(metric)
    return metricsToChose


def get_show_value_labels_as_choice(chartDict, automateDict, paramDict, chosenChart):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    showValuesAsLabel = namingParams["showValuesAsLabel"]
    showValuesAs = namingParams["showValuesAs"]
    absolute = namingParams["absolute"]
    percentOfTotal = namingParams["percentOfTotal"]
    percentOfRowTotal = namingParams["percentOfRowTotal"]
    percentOfColumnTotal = namingParams["percentOfColumnTotal"]
    columnHash = paramDict[namingParams["columnHash"]]
    plotValuesAsOptions = [
        absolute,
        percentOfTotal,
        percentOfRowTotal,
        percentOfColumnTotal,
    ]
    hashKey = get_hashed_key_for_widgets("showValuesAs", columnHash)
    index = 0
    index = insert_json_value(
        "index", index, automateDict, plotValuesAsOptions, showValuesAs, None
    )
    chartDict[showValuesAs] = ui.radio(
        label=showValuesAsLabel,
        options=plotValuesAsOptions,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption("""✳️Show value labels as: (i) absolute numbers, (ii) percent of total,
                        (iii) percent of row total. (iii) percent of column total.
                        """)
    return chartDict


def get_plot_reversed_ecdf_choice(chartDict, automateDict, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    reversedEcdfLabel = namingParams["reversedEcdfLabel"]
    reversedEcdf = namingParams["reversedEcdf"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[reversedEcdf] = notMetConditionValue
    hashKey = get_hashed_key_for_widgets("reversedEcdf", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, reversedEcdf, None
    )
    chartDict[reversedEcdf] = ui.radio(
        label=reversedEcdfLabel,
        options=booleanRadioOptions,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(
        """✳️Set to True if you want the plot reversed (right-most point is at 1, left-most at 0)
                        """
    )
    return chartDict


def get_plot_cumulative_histogram_choice(chartDict, automateDict, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    cumulativeHistogramLabel = namingParams["cumulativeHistogramLabel"]
    cumulativeHistogram = namingParams["cumulativeHistogram"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[cumulativeHistogram] = notMetConditionValue
    hashKey = get_hashed_key_for_widgets("cumulativeHistogram", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, cumulativeHistogram, None
    )
    chartDict[cumulativeHistogram] = ui.radio(
        label=cumulativeHistogramLabel,
        options=booleanRadioOptions,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(
        """✳️Set to True if you want each follow-up bar to cumulate the values of all the preceding bars
                        """
    )
    return chartDict


def get_exclude_outlier_choice_for_charts(
    chosenChart, chartDict, automateDict, paramDict
):
    """
    sets up widget to allow user to choose whether to exclude outliers
    """
    namingParams = get_naming_params()
    scatterChart = namingParams["scatterChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    excludeOutliersLabel = namingParams["excludeOutliersLabel"]
    excludeOutliers = namingParams["excludeOutliers"]
    stdDeviationsLabel = namingParams["stdDeviationsLabel"]
    stdDeviations = namingParams["stdDeviations"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if chosenChart in [scatterChart]:
        choiceIndex = 1
        stdDeviationsChoice = 3
    elif chosenChart in [kernelDensity, histogramChart]:
        choiceIndex = 1
        stdDeviationsChoice = 3
    else:
        choiceIndex = 1
        stdDeviationsChoice = 3
    hashKey = get_hashed_key_for_widgets("excludeOutliersForCharts", columnHash)
    choiceIndex = insert_json_value(
        "index", choiceIndex, automateDict, booleanRadioOptions, excludeOutliers, None
    )
    chartDict[excludeOutliers] = ui.radio(
        label=excludeOutliersLabel,
        options=booleanRadioOptions,
        index=choiceIndex,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption("""✳️If True, drops outliers from plot.""")
    if excludeOutliers in chartDict and chartDict[excludeOutliers]:
        hashKey = get_hashed_key_for_widgets("stdDeviationsForCharts", columnHash)
        stdDeviationsChoice = insert_json_value(
            "slider", stdDeviationsChoice, automateDict, [], stdDeviations, None
        )
        chartDict[stdDeviations] = ui.slider(
            label=stdDeviationsLabel,
            min_value=1,
            max_value=3,
            value=stdDeviationsChoice,
            step=1,
            format=None,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption("""✳️Sets number of standard deviations to identify outliers.""")
    return chartDict


def clear_input_widget():
    namingParams = get_naming_params()
    submittedQuestion = namingParams["submittedQuestion"]
    currentQuestion = namingParams["currentQuestion"]
    session_state[submittedQuestion] = session_state[currentQuestion]
    # Clear the input field
    session_state[currentQuestion] = ""
    return None


def get_user_input(col):
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    submittedQuestion = namingParams["submittedQuestion"]
    currentQuestion = namingParams["currentQuestion"]
    userInput = notMetConditionValue
    if submittedQuestion not in session_state:
        session_state[submittedQuestion] = ""
    with col:
        explainationLabel = "Select a suggested question (Enter, then press Ctrl+Enter to apply) or ask your own (type text, then press Enter to apply). Custom responses may take a few moments."
        userInput = ui.text_input(
            label=explainationLabel, key=currentQuestion, on_change=clear_input_widget
        )
    return None


def set_max_change_widget(paramDict, col, expander):
    """
    putting widgets together to be able to easily turn them offand on
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    maxPercentChangeLabel = namingParams["maxPercentChangeLabel"]
    maxPercentChange = namingParams["maxPercentChange"]
    maxPercentChangeDefault, paramDict = get_dataset_specific_parameter(
        paramDict, namingParams["maxPercentChange"], False
    )
    with col:
        with expander:
            paramDict[maxPercentChange] = ui.slider(
                label=maxPercentChangeLabel,
                min_value=0,
                max_value=8,
                value=maxPercentChangeDefault,
                step=1,
                format=None,
                key="maxPercentChange",
                label_visibility="visible",
            )

            ui.caption(
                """✳️Limits the percent change value used to weight results. Example: two items have the same increase 
                        n absolute value, but the first grew 200%, the other grew 2000%. 
                        If the Max Percent Change parameter is set to 2, the two items will be weighted as 
                        if they had the exact same growth rate. If there is zero amount in the first period and 
                        positive amount in the second, the percentage increase is conventionally set to 200%.
                        """
            )
    return paramDict, expander


def show_alternative_result_widget(dataPrepWidgetDict, drillDownSuffix, automateDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    invertedEmojiNumberDict = configParams[namingParams["invertedEmojiNumberDict"]]
    emojiArrayOneToTen = configParams[namingParams["emojiArrayOneToTen"]]
    alternativeResult = namingParams["alternativeResult"]
    alternativeResultLabel = namingParams["alternativeResultLabel"]
    alternativeResultKey = "alternativeResult" + drillDownSuffix
    value = insert_json_value(
        "sliderStartOne",
        emojiArrayOneToTen[4],
        automateDict,
        emojiArrayOneToTen,
        alternativeResult,
        None,
    )
    chosenEmoji = ui.select_slider(
        label=alternativeResultLabel,
        options=emojiArrayOneToTen,
        value=value,
        key=alternativeResultKey,
        label_visibility="visible",
    )
    dataPrepWidgetDict[alternativeResult] = invertedEmojiNumberDict[chosenEmoji.strip()]
    ui.caption("""✳️Returns one of ten possible alternative results.""")
    return dataPrepWidgetDict


def set_up_parameter_setting_widget(
    dataPrepWidgetDict, chartDict, automateDict, col24, drillDownSuffix
):
    """
    we set up the sliders that control how the data preparation  work
    """
    namingParams = get_naming_params()
    processingChoice = namingParams["processingChoice"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    with col24:
        if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
            dataPrepWidgetDict = show_alternative_result_widget(
                dataPrepWidgetDict, drillDownSuffix, automateDict
            )
            dataPrepWidgetDict = set_up_fine_tune_params(
                dataPrepWidgetDict, chartDict, automateDict, col24, drillDownSuffix
            )
    return dataPrepWidgetDict


def set_up_show_initial_and_final_values_widget(
    dataPrepWidgetDict, chartDict, automateDict, col24
):
    """
    we set up the sliders that control whether to show the initial and final totals of the waterfall charts
    """
    namingParams = get_naming_params()
    showInitialAndFinalValues = namingParams["showInitialAndFinalValues"]
    showInitialAndFinalValuesLabel = namingParams["showInitialAndFinalValuesLabel"]
    processingChoice = namingParams["processingChoice"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    radioOptions = [metConditionValue, notMetConditionValue]
    chartDict[showInitialAndFinalValues] = metConditionValue
    showWidget = False
    with col24:
        if (
            processingChoice in chartDict
            and chartDict[processingChoice]
            in [runOneDimensionalAnalysis, runVariableDimensionalAnalysis]
            and showWidget
        ):
            index = 0
            index = insert_json_value(
                "index", 1, automateDict, radioOptions, showInitialAndFinalValues, None
            )
            chartDict[showInitialAndFinalValues] = ui.radio(
                label=showInitialAndFinalValuesLabel,
                options=radioOptions,
                index=index,
                key="showTotals",
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️True shows initial & final total amounts. False shows variance elements only.    
                        """
            )
    return chartDict


def select_processing_type(chartDict, dataPrepWidgetDict, automateDict, col):
    """
    if there is a date column the user can choose the time
    period to aggregate data
    """
    namingParams = get_naming_params()
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    noVarianceAnalysis = namingParams["noVarianceAnalysis"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    processingChoice = namingParams["processingChoice"]
    chooseProcessingLabel = namingParams["chooseProcessingLabel"]
    varianceAnalysisChart = namingParams["varianceAnalysisChart"]
    with col:
        chartDict[varianceAnalysisChart] = metConditionValue
        disabled = False
        message = """✳️**Fix dimension variance analysis** returns a variance break-up along one dimension.
            **Root cause bridge analysis** returns a break-up along a variable set of dimensions."""
        tooltip = """Choose whether you want the app to run a 'fix dimension variance' or a 'root cause bridge' analysis. 
            """
        chooseProcessingOptions = [
            noVarianceAnalysis,
            runOneDimensionalAnalysis,
            runVariableDimensionalAnalysis,
        ]
        # chooseProcessingOptions=[noVarianceAnalysis,runOneDimensionalAnalysis,]
        index = 0
        index = insert_json_value(
            "index",
            index,
            automateDict,
            chooseProcessingOptions,
            processingChoice,
            None,
        )
        chosenProcessing = ui.radio(
            label=chooseProcessingLabel,
            options=chooseProcessingOptions,
            help=tooltip,
            disabled=disabled,
            index=index,
            key=processingChoice,
            label_visibility="visible",
        )
        ui.caption(message)
        if chosenProcessing == noVarianceAnalysis:
            chartDict[varianceAnalysisChart] = notMetConditionValue
        chartDict[processingChoice] = chosenProcessing
    return chartDict, dataPrepWidgetDict


def show_variance_options_expander(chartDict, col):
    namingParams = get_naming_params()
    processingChoice = namingParams["processingChoice"]
    chosenProcessing = chartDict[processingChoice]
    with col:
        expander = ui.expander("➕ Other variance   options")
    return expander


def set_up_variance_calculation_parameter_widgets(
    paramDict, chartDict, col1Array, dataPrepWidgetDict, expander1Array, automateDict
):
    """
    set up second block of widgets
    """
    namingParams = get_naming_params()
    isdataset = namingParams["isdataset"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    processingChoiceKey = namingParams["processingChoice"]
    expander = ""
    varianceDict = {}
    chartDict[processingChoiceKey] = notMetConditionValue
    if isdataset in paramDict and paramDict[isdataset]:
        chartDict, dataPrepWidgetDict = select_processing_type(
            chartDict, dataPrepWidgetDict, automateDict, col1Array[0]
        )
        chartDict = set_up_show_initial_and_final_values_widget(
            dataPrepWidgetDict, chartDict, automateDict, col1Array[0]
        )
        varianceDict = set_up_parameter_setting_widget(
            varianceDict, chartDict, automateDict, col1Array[0], ""
        )
        expander = show_variance_options_expander(chartDict, col1Array[0])
    return chartDict, dataPrepWidgetDict, varianceDict, expander


def set_up_color_palette_widget(chartDict, automateDict, col):
    """
    user selects if red to green or green to red
    """
    namingParams = get_naming_params()
    cirqueColorpalette = namingParams["cirqueColorpalette"]
    modernColorpalette = namingParams["modernColorpalette"]
    blueAndGreenColorpalette = namingParams["blueAndGreenColorpalette"]
    khakiAndDenimColorpalette = namingParams["khakiAndDenimColorpalette"]
    poloColorpalette = namingParams["poloColorpalette"]
    heatingUpColorpalette = namingParams["heatingUpColorpalette"]
    tableauColorpalette = namingParams["tableauColorpalette"]
    thinkcellColorpalette = namingParams["thinkcellColorpalette"]
    bainColorpalette = namingParams["bainColorpalette"]
    mckinseyColorpalette = namingParams["mckinseyColorpalette"]
    bcgColorpalette = namingParams["bcgColorpalette"]
    occColorpalette = namingParams["occColorpalette"]
    deloitteColorpalette = namingParams["deloitteColorpalette"]
    powerbiColorpalette = namingParams["powerbiColorpalette"]
    symphonyColorpalette = namingParams["symphonyColorpalette"]
    IBCSColorpalette = namingParams["IBCSColorpalette"]
    greysColorpalette = namingParams["greysColorpalette"]
    bluesColorpalette = namingParams["bluesColorpalette"]
    orangesColorpalette = namingParams["orangesColorpalette"]
    purplesColorpalette = namingParams["purplesColorpalette"]
    brownsColorpalette = namingParams["brownsColorpalette"]
    colorpaletteLabel = namingParams["colorpaletteLabel"]
    colorpalette = namingParams["colorpalette"]
    with col:
        colorArray = [
            greysColorpalette,
            bluesColorpalette,
            orangesColorpalette,
            purplesColorpalette,
            brownsColorpalette,
            IBCSColorpalette,
            modernColorpalette,
            cirqueColorpalette,
            blueAndGreenColorpalette,
            khakiAndDenimColorpalette,
            poloColorpalette,
            heatingUpColorpalette,
            symphonyColorpalette,
            tableauColorpalette,
            powerbiColorpalette,
            mckinseyColorpalette,
            bcgColorpalette,
            bainColorpalette,
            thinkcellColorpalette,
            occColorpalette,
            deloitteColorpalette,
        ]
        index = 17
        value = colorArray[index]
        hashKey = get_hashed_key_for_widgets(colorpalette, colorpalette)
        message = """✳️Color palette."""
        tooltip = """Contact us to add your color palette to the liui."""
        value = insert_json_value(
            "array", index, automateDict, colorArray, colorpalette, None
        )
        chartDict[colorpalette] = ui.selectbox(
            label=colorpaletteLabel,
            options=colorArray,
            help=tooltip,
            index=value,
            key=hashKey,
            label_visibility="visible",
        )
        colorDict = get_color_dictionary(chartDict)
        palette = colorDict[chartDict[colorpalette]]
        paletteSize = len(palette)
        columns = ui.columns(paletteSize)
        for i, col in enumerate(columns):
            with col:
                ui.color_picker(
                    label="colors",
                    value=palette[i],
                    key=f"pal_{i}",
                    disabled=False,
                    label_visibility="collapsed",
                )
        ui.caption(message)
    return chartDict


def get_full_currency_name(currency_string):
    # Split the string by the hyphen
    parts = currency_string.split("-")
    # The first part is the currency name
    currency_name = parts[0]
    return currency_name


def set_up_currency_choice_widget(chartDict, automateDict, col):
    """
    user selects currency
    """
    namingParams = get_naming_params()
    currencyParams = get_currency_params()
    currencyDict = currencyParams[namingParams["currencyDict"]]
    currencyChoiceLabel = namingParams["currencyChoiceLabel"]
    currencyChoiceKey = namingParams["currencyChoice"]
    fullCurrencyNameKey = namingParams["fullCurrencyName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    hashKey = get_hashed_key_for_widgets(currencyChoiceKey, currencyChoiceKey)
    currencyOptions = list(currencyDict.keys())
    currencyValues = list(currencyDict.values())
    currencyOptions.insert(0, nothingFilteredName)
    currencyValues.insert(0, nothingFilteredName)
    index = insert_json_value(
        "index", 0, automateDict, currencyValues, currencyChoiceKey, None
    )
    if hashKey in session_state:
        message = session_state[hashKey]
    else:
        message = False
    value = ""
    with col:
        helpMessage = "Choose currency. ISO 4217 abbreviations are used."
        selection = ui.selectbox(
            label=currencyChoiceLabel,
            options=currencyOptions,
            help=helpMessage,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        if selection == nothingFilteredName:
            message = nothingFilteredName
        else:
            message = currencyDict[selection]
        chartDict[currencyChoiceKey] = message
        chartDict[fullCurrencyNameKey] = get_full_currency_name(selection)
        ui.caption("""✳️Currency for chart title.
                                """)
    return chartDict


def show_dataset_type_widget(chartDict, paramDict, col):
    namingParams = get_naming_params()
    datasetTypeLabel = namingParams["datasetTypeLabel"]
    datasetTypeKey = namingParams["datasetTypeName"]
    companySales = namingParams["companySales"]
    scanMarketData = namingParams["scanMarketData"]
    companyExpenses = namingParams["companyExpenses"]
    columnHash = namingParams["columnHash"]
    if columnHash in paramDict:
        columnHash = paramDict[columnHash]
    choiceArray = [companySales, scanMarketData, companyExpenses]
    hashKey = get_hashed_key_for_widgets(datasetTypeKey, columnHash)
    with col:
        message = (
            """✳️Company sales, company expenses, Nielsen/IRI syndicated scan data."""
        )
        tooltip = """Type of analysis and dataset."""
        value = 0
        disabled = False
        chartDict[datasetTypeKey] = choiceArray[0]
        chartDict[datasetTypeKey] = ui.selectbox(
            label=datasetTypeLabel,
            options=choiceArray,
            help=tooltip,
            index=value,
            disabled=disabled,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    if hashKey != datasetTypeKey:
        session_state[datasetTypeKey] = chartDict[datasetTypeKey]
    return chartDict


def get_json_plan_playback_file(df, paramDict, container):
    namingParams = get_naming_params()
    uploadJsonFileLabel = namingParams["uploadPlanJsonFileLabel"]
    planPlaybackName = namingParams["planPlaybackName"]
    preparePlanParams = namingParams["preparePlanParams"]
    playbackDict = {}
    uploadedFile = False
    with container:
        colArray = make_four_col_width_array()
        with colArray[0]:
            if is_valid_lazyframe(df):
                tooltip = """Upload a playback json file to 🔁rerun your plan file.
                          """
                uploadedFile = ui.file_uploader(
                    label=uploadJsonFileLabel,
                    type="json",
                    accept_multiple_files=False,
                    key=planPlaybackName,
                    help=None,
                    on_change=uploader_callback,
                    args=None,
                    disabled=False,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️Upload a plan playback json file to 🔁rerun your plan file. 
                                 """
                )
                if uploadedFile:
                    playbackDict = json.load(uploadedFile)
                    if preparePlanParams not in playbackDict:
                        playbackDict = {}
                        message = "Unable to process plan playback json file. Playback file will be ignored."
                        paramDict = add_error_message_in_plan_dataset_tab(
                            paramDict, message
                        )
    return playbackDict, paramDict


def set_up_color_choice_widget(chartDict, automateDict, col):
    """
    user selects if red to green or green to red
    """
    namingParams = get_naming_params()
    redToGreen = namingParams["redToGreen"]
    blueToOrange = namingParams["blueToOrange"]
    greenToRed = namingParams["greenToRed"]
    colorChoice = namingParams["colorChoice"]
    colorChoiceLabel = namingParams["colorChoiceLabel"]
    companySales = namingParams["companySales"]
    scanMarketData = namingParams["scanMarketData"]
    companyExpenses = namingParams["companyExpenses"]
    datasetTypeKey = namingParams["datasetTypeName"]
    colorArray = [
        redToGreen,
        greenToRed,
        blueToOrange,
    ]
    value = insert_json_value("value", 0, automateDict, colorArray, colorChoice, None)
    if chartDict[datasetTypeKey] in [companySales, scanMarketData]:
        chartDict[colorChoice] = redToGreen
        value = redToGreen
    else:
        chartDict[colorChoice] = greenToRed
        value = greenToRed
    with col:
        if 1 == 3:
            chartDict[colorChoice] = ui.select_slider(
                label=colorChoiceLabel,
                options=colorArray,
                value=value,
                key="colorChoice",
                label_visibility="visible",
            )
            ui.caption(
                """✳️Show: (i) "🔴-🟢+" (negative variance = bad), (ii)  "🟢-🔴+" (positive variance = bad)
                      or (iii) "🔵-🟠+" (no bad or good connotation).  
                """
            )
    return chartDict


def uploader_callback():
    namingParams = get_naming_params()
    runsDict = namingParams["runsDict"]
    hashkeyArray = namingParams["hashkeyArrayName"]
    runNumber = namingParams["runNumberName"]
    totalRunsKey = namingParams["totalNberOfRunsName"]
    toPopArray = [
        runsDict,
        hashkeyArray,
        totalRunsKey,
        runNumber,
    ]
    for element in toPopArray:
        if element in session_state:
            session_state.pop(element)
    return None


def get_json_plot_playback_file(df, paramDict, colArray):
    namingParams = get_naming_params()
    uploadJsonFileLabel = namingParams["uploadPlotJsonFileLabel"]
    plotPlaybackName = namingParams["plotPlaybackName"]
    showPlotExamplesKey = namingParams["showPlotExamples"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    paramDict[showPlotExamplesKey] = notMetConditionValue
    playbackDict = {}
    uploadedFile = False
    with colArray[0]:
        if is_valid_lazyframe(df):
            tooltip = """Upload a playback json file to 🔁rerun your plots.
                      """
            uploadedFile = ui.file_uploader(
                label=uploadJsonFileLabel,
                type="json",
                accept_multiple_files=False,
                key=plotPlaybackName,
                help=tooltip,
                on_change=uploader_callback,
                args=None,
                disabled=False,
                label_visibility="visible",
            )
            ui.caption("""✳️Upload a plot playback json file to 🔁rerun your plots. 
                             """)
            if uploadedFile:
                playbackDict = json.load(uploadedFile)
                paramDict[showPlotExamplesKey] = notMetConditionValue
    return playbackDict, paramDict


def set_up_negative_values_to_zero_widget(paramDict, dataPrepWidgetDict, col):
    """
    we set up the sliders that control how the data preparation  work
    """
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    dropZero = namingParams["dropZero"]
    dropNegative = namingParams["dropNegative"]
    dropZeroAndNegative = namingParams["dropZeroAndNegative"]
    dropRowsWithNegativeValues = namingParams["dropRowsWithNegativeValues"]
    dropRowsWithNegativeValuesLabel = namingParams["dropRowsWithNegativeValuesLabel"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    indexValue = 0
    dropRadioOptions = [
        nothingFilteredName,
        dropZero,
        dropNegative,
        dropZeroAndNegative,
    ]
    dataPrepWidgetDict[dropRowsWithNegativeValues] = dropRadioOptions[indexValue]
    if not paramDict[fileUploadDisabled]:
        with col:
            dataPrepWidgetDict[dropRowsWithNegativeValues] = ui.radio(
                label=dropRowsWithNegativeValuesLabel,
                options=dropRadioOptions,
                index=indexValue,
                key="dropRowsWithNegativeValues",
                label_visibility="visible",
            )
            ui.caption(
                """✳️Drops rows that have zero or/and negative value in the cost/revenue or in the unit columns. 
                           Rows with zeros in both the cost/revenue and the unit columns are dropped automatically, as are rows in which the cost/revenue and in the unit columns have opposite sign. 
                            """
            )
    dataPrepWidgetDict["dropDuplicates"] = False
    return dataPrepWidgetDict


def set_up_add_dimensions_widget(paramDict, col1):
    """
    to avoid doing lookups in excel, the user can upload files with dimension info that we join to the main file
    """
    namingParams = get_naming_params()
    fileParams = get_file_params()
    encodingISO = fileParams["encodingISO"]
    encodingUTF8 = fileParams["encodingUTF8"]
    multipleFileUploadLabel = namingParams["multipleFileUploadLabel"]
    multipleFileUploadArray = namingParams["multipleFileUploadArray"]
    prepareMergedFileForDownload = namingParams["prepareMergedFileForDownload"]
    prepareMergedFileForDownloadLabel = namingParams[
        "prepareMergedFileForDownloadLabel"
    ]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    errorMessageType = namingParams["errorMessageType"]
    captionMessageType = namingParams["captionMessageType"]
    loadDataTabKey = namingParams["loadDataTab"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    message, errorMessage = get_file_error_message("dimension")
    colNumber = 1
    resultArray = []
    uploadedFileArray = []
    try:
        with col1:
            uploadedFileArray = ui.file_uploader(
                label=multipleFileUploadLabel,
                type=["csv"],
                accept_multiple_files=True,
                key="multipleFileUploader",
                label_visibility="visible",
            )
            ui.caption(
                """✳️ To add dimension columns to your file, upload one or more csv files with the dimensions you want to add and the app will do the join. 
                        The key columns in the dimension files must be named in the same way as in the main file.
                        """
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
            isToast=False,
            colNumber=colNumber,
        )
        paramDict = add_app_message_to_paramdict(
            errorMessage,
            errorMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=True,
            colNumber=colNumber,
        )
        paramDict = add_app_message_to_paramdict(
            message,
            captionMessageType,
            loadDataTabKey,
            paramDict,
            isMessage=True,
            isToast=False,
            colNumber=colNumber,
        )
    if len(uploadedFileArray) > 0:
        useBytesIO = False
        try:
            for uploadedFile in uploadedFileArray:
                try:
                    bytesData = uploadedFile.getvalue()
                    encoding = encodingUTF8
                    s = str(bytesData, encoding)
                    result = StringIO(s)
                except Exception as e:
                    logging.exception(e)
                    ui.error("Something went wrong while decoding the dimension file.")
                    bytesData = uploadedFile.getvalue()
                    encoding = encodingISO
                    s = str(bytesData, encoding)
                    result = StringIO(s)
                resultArray.append(result)
            paramDict[namingParams["encoding"]] = encoding
            paramDict[multipleFileUploadArray] = resultArray
        except Exception as e:
            logging.exception(e)
            e = print_error_details(e)
            paramDict = add_app_message_to_paramdict(
                e,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=False,
                colNumber=colNumber,
            )
            paramDict = add_app_message_to_paramdict(
                errorMessage,
                errorMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=True,
                colNumber=colNumber,
            )
            paramDict = add_app_message_to_paramdict(
                message,
                captionMessageType,
                loadDataTabKey,
                paramDict,
                isMessage=True,
                isToast=False,
                colNumber=colNumber,
            )
            resultArray = []
            paramDict[multipleFileUploadArray] = resultArray
    if len(resultArray) > 0:
        with col1:
            paramDict[prepareMergedFileForDownload] = ui.radio(
                label=prepareMergedFileForDownloadLabel,
                options=booleanRadioOptions,
                index=1,
                key="prepareMergedFileForDownload",
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️if True, the system will prepare a parquet file (CSV optional) to download the merged dataset.
                                  This might take a while."""
            )
    return paramDict


def set_up_fine_tune_params(
    dataPrepWidgetDict, chartDict, automateDict, col24, drillDownSuffix
):
    namingParams = get_naming_params()
    configParams = get_config_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    letMeChooseOptionLabel = namingParams["letMeChooseOptionLabel"]
    metConditionValue = namingParams["metConditionValue"]
    aggregationChoiceLabel = namingParams["aggregationChoiceLabel"]
    aggregationChoice = namingParams["aggregationChoice"]
    aggregationChoiceArray = namingParams["aggregationChoiceArray"]
    parameterSettingLabel = namingParams["parameterSettingLabel"]
    parameterSetting = namingParams["parameterSetting"]
    largestCombinationOption = namingParams["largestCombinationOption"]
    limitFirstResultSizeOption = namingParams["limitFirstResultSizeOption"]
    letMeChooseOption = namingParams["letMeChooseOption"]
    moreNodesOption = namingParams["moreNodesOption"]
    moreGrowthOption = namingParams["moreGrowthOption"]
    aggregationChoiceArray = configParams[aggregationChoiceArray]
    bouleanOptions = [metConditionValue, notMetConditionValue]
    letMeChooseOptionKey = "letMeChooseOption" + drillDownSuffix
    aggregationChoiceKey = "aggregationChoice" + drillDownSuffix
    parameterSettingKey = "parameterSetting" + drillDownSuffix
    radioOptions = [
        largestCombinationOption,
        limitFirstResultSizeOption,
        moreNodesOption,
        moreGrowthOption,
    ]
    dataPrepWidgetDict[letMeChooseOption] = notMetConditionValue
    finetuneParams = False
    if finetuneParams:
        index = 1
        index = insert_json_value(
            "index", 1, automateDict, bouleanOptions, letMeChooseOption, None
        )
        dataPrepWidgetDict[letMeChooseOption] = ui.radio(
            label=letMeChooseOptionLabel,
            options=bouleanOptions,
            index=index,
            key=letMeChooseOptionKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️If True, gives access to parameters to fine tune settings""")
        dataPrepWidgetDict = set_max_nodes(
            dataPrepWidgetDict, drillDownSuffix, automateDict
        )
    if dataPrepWidgetDict[letMeChooseOption]:
        index = 0
        index = insert_json_value(
            "index", index, automateDict, radioOptions, parameterSetting, None
        )
        dataPrepWidgetDict[parameterSetting] = ui.radio(
            label=parameterSettingLabel,
            options=radioOptions,
            index=index,
            key=parameterSettingKey,
            label_visibility="visible",
        )
        ui.caption(
            """✳️Select parameter settings. The first option returns the largest combinations with no weighing.
                              The second option limits the max size of the top result. The third option privileges results with many nodes. 
                              The forth option will try to surface results with higher rate of growth."""
        )
    else:
        dataPrepWidgetDict[parameterSetting] = radioOptions[0]
    return dataPrepWidgetDict


def select_drop_low_correlation_columns(dataPrepWidgetDict, colExpander):
    """
    choice if drop low correlation columns
    """
    namingParams = get_naming_params()
    dropLowCorrelationColsLabel = namingParams["dropLowCorrelationColsLabel"]
    dropLowCorrelationCols = namingParams["dropLowCorrelationCols"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    with colExpander:
        dataPrepWidgetDict[dropLowCorrelationCols] = ui.radio(
            label=dropLowCorrelationColsLabel,
            options=booleanRadioOptions,
            index=0,
            key="dropLowCorrelationCols",
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(
            """✳️If True, the tool will automatically drop columns with low correlation with variance amount, to enhance performance.
                        If False, the tool will keep all columns, which in might result in high response times."""
        )
    return dataPrepWidgetDict


def set_up_drop_duplicates_widget(paramDict, dataPrepWidgetDict, col):
    """
    ask the user whether to drop duplicates
    """
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    dropDuplicates = namingParams["dropDuplicates"]
    dropDuplicatesLabel = namingParams["dropDuplicatesLabel"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    indexValue = 1
    radioOptions = [metConditionValue, notMetConditionValue]
    dataPrepWidgetDict[dropDuplicates] = radioOptions[indexValue]
    if not paramDict[fileUploadDisabled]:
        with col:
            dataPrepWidgetDict[dropDuplicates] = ui.radio(
                label=dropDuplicatesLabel,
                options=radioOptions,
                index=indexValue,
                key="dropDuplicates",
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️True drops duplicate rows from dataset.  False leaves duplicate rows in dataset.
                                  """
            )
    return dataPrepWidgetDict


def set_up_dataset_widgets(paramDict, col1Array, expander0Array):
    """
    set up second block of widgets
    """
    namingParams = get_naming_params()
    isdataset = namingParams["isdataset"]
    isDataUploaded = namingParams["isDataUploaded"]
    dataPrepWidgetDict = {}
    datasetParametersWidgetDict = {}
    # datasetParametersWidgetDict=select_drop_low_correlation_columns(datasetParametersWidgetDict,expander1Array[0])
    datasetParametersWidgetDict = select_all_dimensions_string(
        paramDict, datasetParametersWidgetDict, col1Array[1]
    )
    return paramDict, datasetParametersWidgetDict, dataPrepWidgetDict, expander0Array


def select_all_dimensions_string(paramDict, dataPrepWidgetDict, col):
    """
    choice if dimensions need to be object
    """
    namingParams = get_naming_params()
    allDimensionsStringLabel = namingParams["allDimensionsStringLabel"]
    allDimensionsString = namingParams["allDimensionsString"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    fileUploadDisabled = namingParams["fileUploadDisabled"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    dataPrepWidgetDict[allDimensionsString] = metConditionValue
    if not paramDict[fileUploadDisabled]:
        with col:
            index = 0
            dataPrepWidgetDict[allDimensionsString] = ui.radio(
                label=allDimensionsStringLabel,
                options=booleanRadioOptions,
                index=index,
                key="allDimensionsString",
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️If True, all dimensions (the columns you use to "slice" your dataset, 
                things like Country, Channel, Product Type) must be expressed in string format and not as numbers or codes."""
            )
    return dataPrepWidgetDict


def get_conversation_going(col, commentDict):
    namingParams = get_naming_params()
    submitSummaryName = namingParams["submitSummaryName"]
    submitConversationLabel = namingParams["submitConversationLabel"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    chartDataPromptDict = namingParams["chartDataPromptDict"]
    chartImagePromptDict = namingParams["chartImagePromptDict"]
    startConversationSubmittedKey = namingParams["startConversationSubmitted"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    hashKey = get_hashed_key_for_widgets(submitSummaryName, submitSummaryName)
    submitted = notMetConditionValue
    if startConversationSubmittedKey not in session_state:
        session_state[startConversationSubmittedKey] = notMetConditionValue
    if commentDict is not None and len(commentDict) > 0:
        with col:
            tooltip = """Start conversation."""
            message = """✳️Start conversation with report."""
            submitted = ui.button(
                label=submitConversationLabel, help=None, key=hashKey, type="primary"
            )
            ui.caption(message)
            if submitted:
                session_state[startConversationSubmittedKey] = metConditionValue
    return submitted


def get_submit_for_plot_selection():
    namingParams = get_naming_params()
    queryOpenAi = namingParams["queryOpenAi"]
    submitQuery = False
    submitPromptLabel = namingParams["submitPromptLabel"]
    hashKey = get_hashed_key_for_widgets(queryOpenAi, "78r251dfgs")
    tooltip = """Submit prompt to GPT."""
    submitQuery = ui.button(
        label=submitPromptLabel, help=tooltip, key=hashKey, type="primary"
    )
    ui.caption("""✳️Let GPT select the charts of your report. """)
    return submitQuery


def set_up_label_color_widget(chartDict, automateDict, paramDict):
    """
    choose color of bubble labels
    """
    namingParams = get_naming_params()
    labelColorLabel = namingParams["labelColorLabel"]
    labelColor = namingParams["labelColor"]
    blackLabelChoice = namingParams["blackLabelChoice"]
    whiteLabelChoice = namingParams["whiteLabelChoice"]
    greyLabelChoice = namingParams["greyLabelChoice"]
    colorOptions = [
        whiteLabelChoice,
        greyLabelChoice,
        blackLabelChoice,
    ]
    columnHash = paramDict[namingParams["columnHash"]]
    message = """✳️Select bubble label color."""
    tooltip = """Select bubble label color."""
    hashKey = get_hashed_key_for_widgets("labelColor", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, colorOptions, labelColor, None
    )
    chartDict[labelColor] = ui.radio(
        label=labelColorLabel,
        options=colorOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def show_plot_variance_charts(promptDict, columnHash):
    namingParams = get_naming_params()
    plotVarianceCharts = namingParams["plotVarianceCharts"]
    plotVarianceChartsLabel = namingParams["plotVarianceChartsLabel"]
    choiceKey = plotVarianceCharts + "Toogle"
    message = """✳️Include variance analysis plots in report."""
    tooltip = """Include variance analysis plots (not chosen by GPT) in report"""
    hashKey = get_hashed_key_for_widgets(choiceKey, columnHash)
    value = True
    promptDict[plotVarianceCharts] = ui.toggle(
        plotVarianceChartsLabel,
        value=value,
        key=hashKey,
        help=tooltip,
        disabled=False,
        label_visibility="visible",
    )
    ui.caption(message)
    return promptDict


def set_up_add_total_bubble_widget(chartDict, automateDict, paramDict):
    """
    choose color of bubble labels
    """
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    plotTotalBubbleLabel = namingParams["plotTotalBubbleLabel"]
    plotTotalBubble = namingParams["plotTotalBubble"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    columnHash = paramDict[namingParams["columnHash"]]
    message = """✳️Add total bubble."""
    tooltip = """Add total bubble (plotted in red)."""
    index = 0
    if (
        chartDict[yAxisMetric] in valueMetricsArray + volumeMetricsArray
        or chartDict[xAxisMetric] in valueMetricsArray + volumeMetricsArray
    ):
        index = 1
    hashKey = get_hashed_key_for_widgets(plotTotalBubble, columnHash)
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, plotTotalBubble, None
    )
    chartDict[plotTotalBubble] = ui.radio(
        label=plotTotalBubbleLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def set_up_start_axes_from_zero_widget(chartDict, automateDict, paramDict):
    """
    choose color of bubble labels
    """
    namingParams = get_naming_params()
    startAxesFromZeroLabel = namingParams["startAxesFromZeroLabel"]
    startAxesFromZero = namingParams["startAxesFromZero"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    columnHash = paramDict[namingParams["columnHash"]]
    message = """✳️Plot axes from zero."""
    tooltip = """Plot axes from zero."""
    hashKey = get_hashed_key_for_widgets(startAxesFromZero, columnHash)
    index = 0
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, startAxesFromZero, None
    )
    chartDict[startAxesFromZero] = ui.radio(
        label=startAxesFromZeroLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def set_up_label_content_widget(chartDict, automateDict, chosenChart, paramDict):
    """
    choose color of bubble labels
    """
    namingParams = get_naming_params()
    showBubbleLabelLabel = namingParams["showBubbleLabelLabel"]
    showBubbleLabel = namingParams["showBubbleLabel"]
    showBoth = namingParams["showBoth"]
    showLabelsOnly = namingParams["showLabelsOnly"]
    showValuesOnly = namingParams["showValuesOnly"]
    showNothing = namingParams["showNothing"]
    motionChart = namingParams["motionChart"]
    columnHash = paramDict[namingParams["columnHash"]]
    index = 0
    showOptions = [showLabelsOnly, showValuesOnly, showBoth, showNothing]
    if chosenChart == motionChart:
        colorOptions = [showLabelsOnly, showNothing]
        index = 0
    message = """✳️Select bubble labels as:(i) labels only, (ii) labels and values, (iii) values only, (iv) no labels."""
    tooltip = """Select bubble labels as:(i) labels only, (ii) labels and values, (iii) values only, (iv) no labels."""
    hashKey = get_hashed_key_for_widgets("showBubbleLabel", columnHash)
    index = insert_json_value(
        "index", index, automateDict, showOptions, showBubbleLabel, None
    )
    chartDict[showBubbleLabel] = ui.radio(
        label=showBubbleLabelLabel,
        options=showOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def check_if_father_and_child(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    hierarchical = namingParams["hierarchicalName"]
    xAxisDimension = namingParams["xAxisDimension"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    fatherAndChildDimensions = namingParams["fatherAndChildDimensions"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    showTopForEachItem = namingParams["showTopForEachItem"]
    showTopForEachItemLabel = namingParams["showTopForEachItemLabel"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    yAxisDimension = namingParams["yAxisDimension"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    parentArray = []
    chartDict[fatherAndChildDimensions] = notMetConditionValue
    if selectDimensionsToPlot in chartDict:
        childDimension = xAxisDimension
    elif yAxisDimension not in chartDict or chartDict[yAxisDimension] in [
        nothingFilteredName,
        "None",
        notMetConditionValue,
    ]:
        childDimension = xAxisDimension
    else:
        childDimension = yAxisDimension
    if hierarchical in paramDict:
        for hierarchy in paramDict[hierarchical]:
            if chartDict[childDimension] in paramDict[hierarchical][hierarchy]:
                childIndex = list(paramDict[hierarchical][hierarchy]).index(
                    chartDict[childDimension]
                )
                if childIndex > 0 and len(paramDict[hierarchical][hierarchy]) > 1:
                    parentArray = (
                        parentArray
                        + list(paramDict[hierarchical][hierarchy])[:childIndex]
                    )
    if selectDimensionsToPlot in chartDict:
        if chartDict[selectDimensionsToPlot][0] in parentArray:
            chartDict[fatherAndChildDimensions] = metConditionValue
    elif yAxisDimension in chartDict and chartDict[yAxisDimension] not in [
        nothingFilteredName,
        "None",
        notMetConditionValue,
    ]:
        if chartDict[xAxisDimension] in parentArray:
            chartDict[fatherAndChildDimensions] = metConditionValue
    elif (
        smallMultiplesColumn in chartDict
        and chartDict[smallMultiplesColumn] in parentArray
    ):
        chartDict[fatherAndChildDimensions] = metConditionValue
    if not chartDict[fatherAndChildDimensions]:
        index = 1
        hashKey = get_hashed_key_for_widgets(showTopForEachItem, columnHash)
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, showTopForEachItem, None
        )
        chartDict[showTopForEachItem] = ui.radio(
            label=showTopForEachItemLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(
            """✳️If True will plot top items in each sub plot, if False will plot global top items.  
                                        """
        )
    return chartDict


def get_x_and_y_dimensions_choice(
    df, chartDict, automateDict, indexCols, chosenChart, paramDict
):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    selectVerticalDimensionLabel = namingParams["selectVerticalDimensionLabel"]
    selectHorizontalDimensionLabel = namingParams["selectHorizontalDimensionLabel"]
    selectsmallMultiplesColumnAsCircles = namingParams["selectDimensionAsCirclesLabel"]
    selectsmallMultiplesColumnAsSets = namingParams["selectDimensionAsSets"]
    selectsmallMultiplesColumnAsBubbles = namingParams["selectDimensionAsBubbles"]
    selectsmallMultiplesColumnAsDots = namingParams["selectDimensionAsDots"]
    selectsmallMultiplesColumnDistribution = namingParams["selectDistributionDimension"]
    selectsmallMultiplesColumnYAxisSmallMultiples = namingParams[
        "selectYAxisSmallMultiplesDimension"
    ]
    selectcolumnToColorBubbles = namingParams["selectcolumnToColorBubbles"]
    selectcolumnToColorDots = namingParams["selectcolumnToColorDots"]
    selectcolumnToCountCommunality = namingParams["selectcolumnToCountCommunality"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    bubbleChart = namingParams["bubbleChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    motionChart = namingParams["motionChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    scatterChart = namingParams["scatterChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    ecdfChart = namingParams["ecdfChart"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    yAxisDimension = namingParams["yAxisDimension"]
    xAxisDimension = namingParams["xAxisDimension"]
    showBoth = namingParams["showBoth"]
    minIntersectionSizeLabel = namingParams["minIntersectionSizeLabel"]
    minIntersectionSize = namingParams["minIntersectionSize"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    indirectCostsName = namingParams["indirectCostsName"]
    netMarginName = namingParams["netMarginName"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    salesGrowthName = namingParams["salesGrowthName"]
    numberOfTop = namingParams["numberOfTop"]
    metricsToPlot = namingParams["metricsToPlot"]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    countMetricsSumArray = namingParams["countMetricsSumArray"]
    columnHash = paramDict[namingParams["columnHash"]]
    indexColsSelectBox = copy.deepcopy(indexCols)
    showWidget = True
    oneDimensionAndMultitierBar = False
    if chosenChart in [multitierBarChart]:
        showWidget = False
        if (
            plotSmallMultiplesKey not in chartDict
            or not chartDict[plotSmallMultiplesKey]
        ):
            showWidget = False
        elif (
            selectDimensionsToPlot in chartDict
            and len(chartDict[selectDimensionsToPlot]) == 1
        ):
            showWidget = True
            oneDimensionAndMultitierBar = True
    if chosenChart in [stackedBarChart]:
        oneDimensionAndMultitierBar = True
    if showWidget:
        if (
            smallMultiplesColumn in chartDict
            and chartDict[smallMultiplesColumn] in indexColsSelectBox
        ):
            indexColsSelectBox.remove(chartDict[smallMultiplesColumn])
        if chosenChart in [marimekkoChart, barmekkoChart]:
            label = selectVerticalDimensionLabel
            tooltip = """Dimension to plot on the vertical axis of the chart."""
            message = """✳️Dimension to plot on the vertical axis of the chart."""
        elif chosenChart in [stackedBarChart]:
            label = selectVerticalDimensionLabel
            tooltip = """Dimension to plot on the vertical axis of the chart."""
            message = """✳️Dimension to plot on the vertical axis of the chart."""
        elif chosenChart in [vennChart]:
            label = selectsmallMultiplesColumnAsCircles
            tooltip = """Dimension to plot as circles of the Venn diagram."""
            message = """✳️Dimension to plot as circles of the Venn diagram."""
        elif chosenChart in [upsetChart]:
            label = selectsmallMultiplesColumnAsSets
            tooltip = """Dimension to plot as sets of the UpSet plot."""
            message = """✳️Dimension to plot as sets of the UpSet plot."""
        elif chosenChart in [motionChart]:
            label = selectsmallMultiplesColumnAsBubbles
            tooltip = """Dimension to plot the bubble chart on."""
            message = """✳️Dimension to plot the bubble chart on."""
        elif chosenChart in [bubbleChart]:
            label = selectsmallMultiplesColumnAsBubbles
            tooltip = """Dimension to plot the bubble chart on."""
            message = """✳️Dimension to plot the bubble chart on."""
        elif chosenChart in [scatterChart]:
            label = selectsmallMultiplesColumnAsDots
            tooltip = """Dimension to plot as dots. If None is chosen, each dataset row is a dot."""
            message = """✳️Dimension to plot as dots. If None is chosen, each dataset row is a dot."""
            if (
                chartDict[yAxisMetric] != salesGrowthName
                and chartDict[xAxisMetric] != salesGrowthName
            ):
                indexColsSelectBox.insert(0, nothingFilteredName)
            else:
                pass
        elif chosenChart in [
            kernelDensity,
            histogramChart,
            boxplotChart,
            stripplotChart,
            ecdfChart,
        ]:
            label = selectsmallMultiplesColumnDistribution
            tooltip = """Dimension to use to analyse distribution. If None is chosen, each dataset row is an observation."""
            message = """✳️Dimension to use to analyse distribution. If None is chosen, each dataset row is an observation."""
            indexColsSelectBox.insert(0, nothingFilteredName)
        elif chosenChart in [multitierBarChart]:
            label = selectsmallMultiplesColumnYAxisSmallMultiples
            tooltip = """Dimension to plot on the vertical axis of each chart."""
            message = """✳️Dimension to plot on the Y axis of the plots."""
            if (
                selectDimensionsToPlot in chartDict
                and len(chartDict[selectDimensionsToPlot]) == 1
                and chartDict[selectDimensionsToPlot][0] in indexColsSelectBox
            ):
                indexColsSelectBox.remove(chartDict[selectDimensionsToPlot][0])
        index = 0
        index = insert_json_value(
            "index", index, automateDict, indexColsSelectBox, xAxisDimension, None
        )
        hashKey = get_hashed_key_for_widgets(xAxisDimension, columnHash)
        chartDict[xAxisDimension] = ui.selectbox(
            label=label,
            options=indexColsSelectBox,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        indexColsFilteredArray = take_filtered_value_out_of_option_list(
            indexColsSelectBox, chartDict[xAxisDimension]
        )
        choiceArray = notMetConditionValue
        if chosenChart not in [
            scatterChart,
            kernelDensity,
            histogramChart,
            boxplotChart,
            stripplotChart,
            ecdfChart,
        ]:
            chartDict = get_top_items_choice(
                chartDict, automateDict, chosenChart, "X", paramDict
            )
        if chosenChart in [marimekkoChart]:
            label = selectHorizontalDimensionLabel
            tooltip = """Dimension to plot on the horizontal axis of the chart"""
            message = """✳️Dimension to plot on the horizontal axis."""
            choiceArray = copy.deepcopy(indexColsFilteredArray)
        elif chosenChart in [stackedBarChart]:
            label = selectHorizontalDimensionLabel
            tooltip = """Dimension to plot on the horizontal axis of the chart. "None" for simple (not stacked) bar chart."""
            message = """✳️Dimension to plot on the horizontal axis. "None" for simple (not stacked) bar chart."""
            choiceArray = copy.deepcopy(indexColsFilteredArray)
            if nothingFilteredName not in choiceArray:
                choiceArray.insert(0, nothingFilteredName)
        elif chosenChart in [vennChart]:
            label = selectcolumnToCountCommunality
            tooltip = """Hierarchical dimension will be excluded automatically."""
            message = """✳️Dimension- you want to use to count intersection."""
            choiceArray = copy.deepcopy(indexColsFilteredArray)
        elif chosenChart in [upsetChart]:
            label = selectcolumnToCountCommunality
            tooltip = """Hierarchical dimension will be excluded automatically."""
            message = """✳️Dimension you want to use to count intersection."""
            choiceArray = copy.deepcopy(indexColsFilteredArray)
        elif chosenChart in [motionChart]:
            label = selectcolumnToColorBubbles
            tooltip = """Dimension you want to plot to color bubbles."""
            message = """✳️Dimension you want to plot to color bubbles."""
            choiceArray = get_parents_of_dimension(
                chartDict, chosenChart, indexColsFilteredArray, paramDict, False
            )
        elif chosenChart in [scatterChart, bubbleChart]:
            if chosenChart in [scatterChart]:
                label = selectcolumnToColorDots
                tooltip = """Dimension to color dots."""
                message = """✳️Dimension to color dots."""
            elif chosenChart in [bubbleChart]:
                label = selectcolumnToColorBubbles
                tooltip = """Dimension to color bubbles."""
                message = """✳️Dimension to color bubbles."""
        if chosenChart in [scatterChart, bubbleChart]:
            choiceArray = get_parents_of_dimension(
                chartDict, chosenChart, indexColsFilteredArray, paramDict, False
            )
            choiceArray = get_colors_for_observations(
                choiceArray, chartDict, paramDict, chosenChart
            )
        if chosenChart in [vennChart, upsetChart]:
            choiceArray = get_parents_of_dimension(
                chartDict, chosenChart, choiceArray, paramDict, False
            )
        hashKey = get_hashed_key_for_widgets("yAxisDimension", columnHash)
        if (
            chosenChart in [stackedBarChart]
            and metricsToPlot in chartDict
            and len(chartDict[metricsToPlot]) > 0
            and chartDict[metricsToPlot][0]
            in [indirectCostsName, netMarginName]
            + percentMetricsArray
            + priceMetricsArray
            + growthMetricArray
        ):
            chartDict[yAxisDimension] = nothingFilteredName
        elif (
            chosenChart in [stackedBarChart]
            and metricsToPlot in chartDict
            and len(chartDict[metricsToPlot]) > 0
            and countMetricsAvgArray in chartDict
            and chartDict[metricsToPlot][0] in chartDict[countMetricsAvgArray]
        ):
            chartDict[yAxisDimension] = nothingFilteredName
        elif (
            chosenChart in [stackedBarChart]
            and metricsToPlot in chartDict
            and len(chartDict[metricsToPlot]) > 0
            and countMetricsSumArray in chartDict
            and chartDict[metricsToPlot][0] in chartDict[countMetricsSumArray]
        ):
            chartDict[yAxisDimension] = nothingFilteredName
        elif (
            chosenChart in [stackedBarChart]
            and metricsToPlot in chartDict
            and len(chartDict[metricsToPlot]) > 1
        ):
            chartDict[yAxisDimension] = nothingFilteredName
        elif choiceArray and len(choiceArray) > 0:
            if (
                chosenChart not in [bubbleChart]
                or chosenChart in [bubbleChart]
                and "X" in chartDict
                and chartDict["X"][numberOfTop] <= 10
            ):
                index = 0
                index = insert_json_value(
                    "index", index, automateDict, choiceArray, yAxisDimension, None
                )
                chartDict[yAxisDimension] = ui.selectbox(
                    label=label,
                    options=choiceArray,
                    help=tooltip,
                    index=index,
                    key=hashKey,
                    label_visibility="visible",
                )
                ui.caption(message)
                if chartDict[yAxisDimension] in [
                    nothingFilteredName
                ] and chosenChart in [scatterChart]:
                    chartDict[yAxisDimension] = notMetConditionValue
            else:
                chartDict[yAxisDimension] = notMetConditionValue
        else:
            chartDict[yAxisDimension] = notMetConditionValue
        if (
            chosenChart in [stackedBarChart, marimekkoChart]
            and chartDict[yAxisDimension] != nothingFilteredName
        ):
            chartDict = get_top_items_choice(
                chartDict, automateDict, chosenChart, "W", paramDict
            )
        if chosenChart in [upsetChart]:
            tooltip = (
                """Select the minimum intersection size to be shown in the plot."""
            )
            message = (
                """✳️Select the minimum intersection size to be shown in the plot."""
            )
            hashKey = get_hashed_key_for_widgets("minIntersectionSize", columnHash)
            value = 1
            value = insert_json_value(
                "slider", value, automateDict, [], minIntersectionSize, None
            )
            chartDict[minIntersectionSize] = ui.number_input(
                label=minIntersectionSizeLabel,
                min_value=1,
                max_value=None,
                value=value,
                step=None,
                format=None,
                key=hashKey,
                help=tooltip,
                label_visibility="visible",
            )
            ui.caption(message)
        if oneDimensionAndMultitierBar:
            chartDict = check_if_father_and_child(chartDict, automateDict, paramDict)
    return chartDict


def make_month_widget(
    monthNumber, paramDict, colArray, expectedTotal, planPlaybackDict
):
    namingParams = get_naming_params()
    timeProfileValues = namingParams["timeProfileValues"]
    columnHash = paramDict[namingParams["columnHash"]]
    monthIndex = monthNumber - 1
    col = monthIndex
    if monthNumber > 6:
        col = monthNumber - 7
    monthNumber = str(monthNumber)
    hashKey = get_hashed_key_for_widgets(timeProfileValues + monthNumber, columnHash)
    disabled = False
    minValue, maxValue, startValue = 0, 300, int(expectedTotal / 12)
    tooltip = "Month " + monthNumber
    label = "Month " + monthNumber
    with colArray[col]:
        if (
            timeProfileValues in planPlaybackDict
            and planPlaybackDict[timeProfileValues]
        ):
            valueArray = planPlaybackDict[timeProfileValues]
            startValue = insert_json_value(
                "numberInput", startValue, {}, valueArray, monthIndex, None
            )
        monthValue = ui.number_input(
            label=label,
            min_value=minValue,
            max_value=maxValue,
            value=startValue,
            step=None,
            format=None,
            key=hashKey,
            help=tooltip,
            disabled=disabled,
            label_visibility="visible",
        )
    return monthValue


def show_number_of_additional_plots_widget(promptDict, columnHash):
    namingParams = get_naming_params()
    nbrOfFollowUpPlotsKey = namingParams["nbrOfFollowUpPlots"]
    nbrOfFollowUpPlotsLabel = namingParams["nbrOfFollowUpPlotsLabel"]
    hashKey = get_hashed_key_for_widgets(nbrOfFollowUpPlotsKey, columnHash)
    tooltipNumber = "Number of additional plots"
    messageNumber = "✳️Number of additional plots"
    value = 20
    minValue = 5
    promptDict[nbrOfFollowUpPlotsKey] = ui.slider(
        label=nbrOfFollowUpPlotsLabel,
        min_value=minValue,
        max_value=20,
        help=tooltipNumber,
        value=value,
        step=1,
        format=None,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(messageNumber)
    return promptDict


def show_metric_to_focus_widget(promptDict, columnHash, valueCols):
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    followUpMetricKey = namingParams["followUpMetric"]
    followUpMetricLabel = namingParams["followUpMetricLabel"]
    valueColsSelectBox = copy.deepcopy(valueCols)
    if unitsName in valueColsSelectBox:
        if pricePerUnitName not in valueColsSelectBox:
            valueColsSelectBox.append(pricePerUnitName)
    if volumeName in valueColsSelectBox:
        if pricePerVolumeName not in valueColsSelectBox:
            valueColsSelectBox.append(pricePerVolumeName)
    valueColsSelectBox.insert(0, nothingFilteredName)
    tooltip = "Metric to focus on"
    message = "✳️Metric to focus on (if any)"
    value = 0
    hashKey = get_hashed_key_for_widgets(followUpMetricKey, columnHash)
    promptDict[followUpMetricKey] = ui.selectbox(
        label=followUpMetricLabel,
        options=valueColsSelectBox,
        help=tooltip,
        index=value,
        disabled=False,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return promptDict


def show_dimension_to_focus_widget(promptDict, columnHash, indexCols):
    namingParams = get_naming_params()
    nothingFilteredName = namingParams["nothingFilteredName"]
    followUpDimensionKey = namingParams["followUpDimension"]
    followUpDimensionLabel = namingParams["followUpDimensionLabel"]
    indexColsSelectBox = copy.deepcopy(indexCols)
    indexColsSelectBox.insert(0, nothingFilteredName)
    tooltip = "Dimension to focus the analysis on"
    message = "✳️Dimension to focus the analysis on (if any)"
    value = 0
    hashKey = get_hashed_key_for_widgets(followUpDimensionKey, columnHash)
    promptDict[followUpDimensionKey] = ui.selectbox(
        label=followUpDimensionLabel,
        options=indexColsSelectBox,
        help=tooltip,
        index=value,
        disabled=False,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    return promptDict


def show_distribution_plot_widget(promptDict, columnHash):
    namingParams = get_naming_params()
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    audienceDistributionChartKey = namingParams["audienceDistributionChartName"]
    distributionChartLabel = namingParams["distributionChartLabel"]
    choiceArray = [
        boxplotChart,
        kernelDensity,
        ecdfChart,
        histogramChart,
        stripplotChart,
    ]
    hashKey = get_hashed_key_for_widgets(audienceDistributionChartKey, columnHash)
    message = """✳️Distribution plot to use."""
    tooltip = """Preferred plot among possible alternatives"""
    value = 1
    disabled = False
    promptDict[audienceDistributionChartKey] = ui.selectbox(
        label=distributionChartLabel,
        options=choiceArray,
        help=tooltip,
        disabled=disabled,
        index=value,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    session_state[audienceDistributionChartKey] = promptDict[
        audienceDistributionChartKey
    ]
    return promptDict


def show_timeline_plot_widget(promptDict, paramDict, columnHash):
    namingParams = get_naming_params()
    timelineChart = namingParams["timelineChart"]
    areaChart = namingParams["areaChart"]
    audienceTimelineChartKey = namingParams["audienceTimelineChartName"]
    timelineChartLabel = namingParams["timelineChartLabel"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    dateColFound = namingParams["dateColFound"]
    choiceArray = [timelineChart, areaChart]
    promptDict[audienceTimelineChartKey], session_state[audienceTimelineChartKey] = (
        notMetConditionValue,
        notMetConditionValue,
    )
    if dateColFound in paramDict and paramDict[dateColFound]:
        hashKey = get_hashed_key_for_widgets(audienceTimelineChartKey, columnHash)
        message = """✳️Temporal development plot to use."""
        tooltip = """Preferred plot among possible alternatives"""
        value = 0
        disabled = True
        promptDict[audienceTimelineChartKey] = ui.selectbox(
            label=timelineChartLabel,
            options=choiceArray,
            help=tooltip,
            disabled=disabled,
            index=value,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        session_state[audienceTimelineChartKey] = promptDict[audienceTimelineChartKey]
    return promptDict


def show_correspondence_plot_widget(promptDict, columnHash):
    namingParams = get_naming_params()
    upsetChart = namingParams["upsetChart"]
    vennChart = namingParams["vennChart"]
    audienceCorrespondenceChartKey = namingParams["audienceCorrespondenceChartName"]
    correspondenceChartLabel = namingParams["correspondenceChartLabel"]
    choiceArray = [upsetChart, vennChart]
    hashKey = get_hashed_key_for_widgets(audienceCorrespondenceChartKey, columnHash)
    message = """✳️Intersection analysis plot to use."""
    tooltip = """Preferred plot among possible alternatives"""
    value = 0
    disabled = True
    promptDict[audienceCorrespondenceChartKey] = ui.selectbox(
        label=correspondenceChartLabel,
        options=choiceArray,
        help=tooltip,
        disabled=disabled,
        index=value,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    session_state[audienceCorrespondenceChartKey] = promptDict[
        audienceCorrespondenceChartKey
    ]
    return promptDict


def show_monthly_variance_widget(promptDict, chartDict, paramDict, columnHash):
    namingParams = get_naming_params()
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    audienceVarianceChartKey = namingParams["audienceVarianceChartName"]
    audienceVarianceChartLabel = namingParams["audienceVarianceChartLabel"]
    dateColFound = namingParams["dateColFound"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    plotChoiceArray = [
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
    ]
    promptDict[audienceVarianceChartKey], session_state[audienceVarianceChartKey] = (
        notMetConditionValue,
        notMetConditionValue,
    )
    if dateColFound in paramDict and paramDict[dateColFound]:
        hashKey = get_hashed_key_for_widgets(audienceVarianceChartKey, columnHash)
        message = """✳️Monthly variance plot to use."""
        tooltip = """Preferred plot among possible alternatives"""
        value = 0
        disabled = True
        promptDict[audienceVarianceChartKey] = ui.selectbox(
            label=audienceVarianceChartLabel,
            options=plotChoiceArray,
            help=tooltip,
            disabled=disabled,
            index=value,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        session_state[audienceVarianceChartKey] = promptDict[audienceVarianceChartKey]
    return promptDict


def show_number_of_plots_widget(valueCols, promptDict, columnHash):
    namingParams = get_naming_params()
    nbrOfPlotsKey = namingParams["nbrOfPlots"]
    nbrOfPlotsLabel = namingParams["nbrOfPlotsLabel"]
    marginName = namingParams["marginName"]
    plotVarianceCharts = namingParams["plotVarianceCharts"]
    hashKey = get_hashed_key_for_widgets(nbrOfPlotsKey, columnHash)
    tooltip = "The LLM will return (more or less) the required number of plots"
    message = "✳️How many plots you would like."
    autoPlots = 0
    if plotVarianceCharts in promptDict and promptDict[plotVarianceCharts]:
        autoPlots = 5
    minOpenAiPlots = 10
    maxOpenAiPlots = 50
    maxValue = autoPlots + maxOpenAiPlots
    minValue = autoPlots + minOpenAiPlots
    startValue = maxValue
    if marginName in valueCols:
        if plotVarianceCharts in promptDict and promptDict[plotVarianceCharts]:
            autoPlots = 10
        minOpenAiPlots = 10
        maxOpenAiPlots = 50
        maxValue = autoPlots + maxOpenAiPlots
        minValue = autoPlots + minOpenAiPlots
        startValue = maxValue
    nbrOfPlots = ui.slider(
        label=nbrOfPlotsLabel,
        min_value=minValue,
        max_value=maxValue,
        help=tooltip,
        value=startValue,
        step=5,
        format=None,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    promptDict[nbrOfPlotsKey] = nbrOfPlots - autoPlots
    return promptDict


def prepare_chart_images(chartDict, columnArray, paramDict):
    namingParams = get_naming_params()
    chosenChartKey = namingParams["chosenChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    plotAsBaseline = namingParams["plotAsBaseline"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    percentOfTotalDataset = namingParams["percentOfTotalDataset"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    absolute = namingParams["absolute"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    multitierBarChart = namingParams["multitierBarChart"]
    areaChart = namingParams["areaChart"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    paretoChart = namingParams["paretoChart"]
    chosenChart = False
    if chosenChartKey in chartDict:
        chosenChart = chartDict[chosenChartKey]
    if chosenChart:
        if chosenChart in [paretoChart] and chartDict[showAbsoluteValues]:
            chosenChart = chosenChart + "_" + absolute
        if chosenChart in [trendComparisonChart] and chartDict[plotAsBaseline]:
            chosenChart = "baseline"
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            chartName = chosenChart + "_" + "small_Multiples"
        else:
            chartName = chosenChart
        chartName = chartName.lower().replace(" ", "_")
        if (
            plotSmallMultiplesKey not in chartDict
            or not chartDict[plotSmallMultiplesKey]
        ):
            if chosenChart in [stackedColumnChart]:
                if chartDict[plotValuesAsChoice] in [absolute]:
                    chartName = chartName + "_" + absolute
                else:
                    chartName = "normalized" + "_" + chartName
            if chosenChart in [areaChart]:
                if chartDict[plotValuesAsChoice] in [absolute]:
                    chartName = chartName + "_" + absolute
                else:
                    chartName = "normalized" + "_" + chartName
            if chosenChart in [stackedBarChart]:
                if chartDict[plotValuesAsChoice] in [absolute]:
                    paramDict = show_chart_image("bar", columnArray[2], paramDict)
                    chartName = chartName + "_" + absolute
                else:
                    chartName = "normalized" + "_" + chartName
            if (
                chosenChart in [stackedParetoChart]
                and chartDict[aggregateUniquesByDimension]
            ):
                chartName = chartName + "_by_dimension"
        if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
            if chosenChart in [multitierBarChart]:
                if len(chartDict[selectDimensionsToPlot]) == 1:
                    chartName = chartName + "_by_single_dimension"
        paramDict = show_chart_image(chartName, columnArray[1], paramDict)
        if chosenChart in [stackedColumnChart] and chartDict[plotValuesAsChoice] in [
            percentOfTotalDataset
        ]:
            paramDict = show_chart_image(
                "summary_stacked_column_percent", columnArray[1], paramDict
            )
        if chosenChart in [stackedColumnChart] and chartDict[
            plotValuesAsChoice
        ] not in [percentOfTotalDataset]:
            paramDict = show_chart_image(
                "summary_stacked_column_absolute", columnArray[1], paramDict
            )
    return paramDict


def select_compare_scenarios_or_periods(paramDict, chartDict, automateDict):
    """
    choice compare vs plan or vs past
    """
    namingParams = get_naming_params()
    compareScenariosOrPeriodsLabel = namingParams["compareScenariosOrPeriodsLabel"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    comparePeriods = namingParams["comparePeriods"]
    columnHash = paramDict[namingParams["columnHash"]]
    compareOptions = [comparePeriods, compareScenarios]
    tooltip = """Run variance by comparing scenarios or periods"""
    hashKey = get_hashed_key_for_widgets(compareScenariosOrPeriods, columnHash)
    index = 0
    index = insert_json_value(
        "index", index, automateDict, compareOptions, compareScenariosOrPeriods, None
    )
    chartDict[compareScenariosOrPeriods] = ui.radio(
        label=compareScenariosOrPeriodsLabel,
        options=compareOptions,
        index=index,
        key=hashKey,
        help=tooltip,
        label_visibility="visible",
    )
    ui.caption(
        """✳️Compare periods (ex. Actual vs Previous Year) or scenarios (ex. Actual vs Plan)"""
    )
    return chartDict


def make_date_filters(df, paramDict, chartDict):
    """
    Set up date filters using Polars to compute min/max and Python datetime for ranges.
    """
    namingParams = get_naming_params()
    dateName = namingParams["dateName"]
    startDateLabel = namingParams["startDateLabel"]
    endDateLabel = namingParams["endDateLabel"]
    dateRangeArray = namingParams["dateRangeArray"]
    columnHash = paramDict[namingParams["columnHash"]]

    # Compute min/max date via Polars (works for DataFrame and LazyFrame)
    if isinstance(df, pl.LazyFrame):
        stats = df.select(
            [
                pl.col(dateName).min().alias("min_date"),
                pl.col(dateName).max().alias("max_date"),
            ]
        ).collect()
        minDate = stats["min_date"][0]
        maxDate = stats["max_date"][0]
    elif isinstance(df, pl.DataFrame):
        stats = df.select(
            [
                pl.col(dateName).min().alias("min_date"),
                pl.col(dateName).max().alias("max_date"),
            ]
        )
        minDate = stats["min_date"][0]
        maxDate = stats["max_date"][0]
    else:
        # Fallback: coerce to Polars then compute
        pdf = pl.DataFrame(df)
        stats = pdf.select(
            [
                pl.col(dateName).min().alias("min_date"),
                pl.col(dateName).max().alias("max_date"),
            ]
        )
        minDate = stats["min_date"][0]
        maxDate = stats["max_date"][0]

    # Convert to date if needed
    if isinstance(minDate, datetime.datetime):
        min_dt = minDate.date()
    else:
        min_dt = minDate
    if isinstance(maxDate, datetime.datetime):
        max_dt = maxDate.date()
    else:
        max_dt = maxDate

    # Use approx month length to decide initial window
    diff_days = (max_dt - min_dt).days
    if diff_days > 365:
        min_dt = max_dt - datetime.timedelta(days=364)

    tooltipMin = "Choose the start date to filter the dataset. The interval should not be greater than 12 months."
    tooltipMax = "Choose the end date to filter the dataset. The interval should not be greater than 12 months."
    hashKey = get_hashed_key_for_widgets("minDate", columnHash)
    minDateChoice = ui.date_input(
        label=startDateLabel,
        value=min_dt,
        help=tooltipMin,
        key=hashKey,
        label_visibility="visible",
    )
    hashKey = get_hashed_key_for_widgets("maxDate", columnHash)
    maxDateChoice = ui.date_input(
        label=endDateLabel,
        value=max_dt,
        help=tooltipMax,
        key=hashKey,
        label_visibility="visible",
    )

    if minDateChoice > maxDateChoice:
        message = "Could not filter by date. Start date greater than end date"
        paramDict = add_warning_message_in_period_options_tab(paramDict, message)

    selected_days = (maxDateChoice - minDateChoice).days
    if selected_days > 366:
        message = "Filtered period should not be greater than 12 months"
        paramDict = add_warning_message_in_period_options_tab(paramDict, message)

    chartDict[dateRangeArray] = [minDateChoice, maxDateChoice]
    return chartDict


def select_date_aggregation(df, paramDict, chartDict, automateDict, col):
    """
    if there is a date column the user can choose the time
    period to aggregate data
    """
    namingParams = get_naming_params()
    weekName = namingParams["weekName"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    yearName = namingParams["yearName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    aggregateDateLabel = namingParams["aggregateDateLabel"]
    periodChoice = namingParams["periodChoice"]
    dateColFound = namingParams["dateColFound"]
    periodColFound = namingParams["periodColFound"]
    filterDates = namingParams["filterDates"]
    compareScenarios = namingParams["compareScenarios"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    columnHash = paramDict[namingParams["columnHash"]]
    choiceArray = [yearName, quarterName, monthName, weekName]
    chartDict[filterDates] = notMetConditionValue
    with col:
        if (
            periodColFound in paramDict
            and paramDict[periodColFound]
            and not paramDict[dateColFound]
        ):
            chosenPeriod = notMetConditionValue
        elif (
            periodColFound in paramDict
            and paramDict[periodColFound]
            and paramDict[dateColFound]
        ):
            chosenPeriod = notMetConditionValue
            chartDict = select_compare_scenarios_or_periods(
                paramDict, chartDict, automateDict
            )
            if (
                compareScenariosOrPeriods in chartDict
                and chartDict[compareScenariosOrPeriods] == compareScenarios
            ):
                chartDict = make_date_filters(df, paramDict, chartDict)
                chartDict[filterDates] = metConditionValue
                ui.caption(
                    """✳️Choose the start and the end date to filter the dataset. 
                                    """
                )
            else:
                tooltip = """Choose whether to aggregate - and compare - data by year, month or week.
                        """
                hashKey = get_hashed_key_for_widgets("chosenPeriod", columnHash)
                value = insert_json_value(
                    "value", 0, automateDict, choiceArray, periodChoice, None
                )
                chosenPeriod = ui.select_slider(
                    label=aggregateDateLabel,
                    options=choiceArray,
                    value=value,
                    key=hashKey,
                    label_visibility="visible",
                )

                ui.caption("""✳️Choose whether to aggregate your date column 
                                    by week, month, quarter or year. If nothing is specified, it will default to year: the
                                    most recent 12 month will be compared to the preceding 12 months. If the dataset contains less than 
                                    24 months, the aggregation will default to month or quarter. 
                                    """)
        elif dateColFound in paramDict and paramDict[dateColFound]:
            tooltip = """Choose whether to aggregate - and compare - data by year, month or week.
                        """
            hashKey = get_hashed_key_for_widgets("chosenPeriod", columnHash)
            value = insert_json_value(
                "value", 0, automateDict, choiceArray, periodChoice, None
            )
            chosenPeriod = ui.select_slider(
                label=aggregateDateLabel,
                options=choiceArray,
                value=value,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption("""✳️Choose whether to aggregate your date column 
                                    by week, month, quarter or year. If nothing is specified, it will default to year: the
                                    most recent 12 month will be compared to the preceding 12 months. If the dataset contains less than 
                                    24 months, the aggregation will default to month or quarter. 
                                    """)
        else:
            chosenPeriod = notMetConditionValue
        chartDict[periodChoice] = chosenPeriod
    return chartDict


def select_by_fiscal_year(paramDict, chartDict, automateDict, col):
    """
    if you choose quarter, month or week you can compare with the correspondent period of the year before
    """
    namingParams = get_naming_params()
    weekName = namingParams["weekName"]
    fiscalYear = namingParams["fiscalYear"]
    fiscalStartMonth = namingParams["fiscalStartMonth"]
    fiscalStartMonthLabel = namingParams["fiscalStartMonthLabel"]
    fiscalYearLabel = namingParams["fiscalYearLabel"]
    monthTranslateDict = namingParams["monthTranslateDict"]
    periodChoice = namingParams["periodChoice"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if chartDict[periodChoice] not in [notMetConditionValue]:
        with col:
            if chartDict[periodChoice] != weekName:
                tooltip = "If True, dates are aggregated by fiscal year."
                index = insert_json_value(
                    "index", 1, automateDict, booleanRadioOptions, fiscalYear, None
                )
                chartDict[fiscalYear] = ui.radio(
                    label=fiscalYearLabel,
                    options=booleanRadioOptions,
                    help=tooltip,
                    index=index,
                    key="fiscalYear",
                    horizontal=True,
                    label_visibility="visible",
                )
                ui.caption("""✳️If True, dates are analysed by fiscal year  
                            """)
            else:
                chartDict[fiscalYear] = notMetConditionValue
            if chartDict[fiscalYear]:
                chartDict[fiscalStartMonth] = ui.selectbox(
                    label=fiscalStartMonthLabel,
                    options=list(range(1, 13)),
                    format_func=lambda x: dt.datetime(2000, x, 1).strftime("%B"),
                    key=fiscalStartMonth,
                )
                # chartDict[monthTranslateDict] = {dt.datetime(2000, i, 1).strftime('%B'): dt.datetime(2000, i, 1).strftime('%b') for i in range(1, 13)}
            else:
                chartDict[fiscalStartMonth]: None
    return chartDict


def select_if_year_before(paramDict, chartDict, automateDict, col):
    """
    if you choose quarter, month or week you can compare with the correspondent period of the year before
    """
    namingParams = get_naming_params()
    yearName = namingParams["yearName"]
    weekName = namingParams["weekName"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    compareWithYearBeforeLabel = namingParams["compareWithYearBeforeLabel"]
    periodToDate = namingParams["periodToDate"]
    periodToDateLabel = namingParams["periodToDateLabel"]
    fiscalYear = namingParams["fiscalYear"]
    periodChoice = namingParams["periodChoice"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if chartDict[periodChoice] not in [notMetConditionValue]:
        with col:
            if chartDict[periodChoice] != weekName:
                tooltip = "If True, compares period start date to most recent date to corresponding previous period."
                index = insert_json_value(
                    "index", 1, automateDict, booleanRadioOptions, periodToDate, None
                )
                chartDict[periodToDate] = ui.radio(
                    label=periodToDateLabel,
                    options=booleanRadioOptions,
                    help=tooltip,
                    index=index,
                    key="periodToDate",
                    horizontal=True,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️If True, compares period start date to most recent available date with corresponding previous period. If False compares full period  
                 """
                )
            else:
                chartDict[periodToDate] = notMetConditionValue
            chartDict[compareWithYearBefore] = notMetConditionValue
            if (
                not chartDict[periodToDate]
                and not chartDict[fiscalYear]
                and chartDict[periodChoice] == yearName
            ):
                tooltip = "If True, compares with rolling period year before."
                index = 0
                index = insert_json_value(
                    "index",
                    index,
                    automateDict,
                    booleanRadioOptions,
                    compareWithYearBefore,
                    None,
                )
                chartDict[compareWithYearBefore] = ui.radio(
                    label=compareWithYearBeforeLabel,
                    options=booleanRadioOptions,
                    help=tooltip,
                    index=index,
                    key="compareWithYearBefore",
                    horizontal=True,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️If True, compares 12 month rolling periods. If False compares calendar years.
                            """
                )
    return chartDict


def select_most_recent_period(df, paramDict, chartDict, automateDict, col):
    """
    if there is a date column the user can choose the time
    period to aggregate data
    """
    namingParams = get_naming_params()
    mostRecentPeriod = namingParams["mostRecentPeriod"]
    mostRecentPeriodLabel = namingParams["mostRecentPeriodLabel"]
    dateColFound = namingParams["dateColFound"]
    periodColFound = namingParams["periodColFound"]
    periodName = namingParams["periodName"]
    dateName = namingParams["dateName"]
    yearName = namingParams["yearName"]
    selectedPeriods = namingParams["selectedPeriods"]
    monthName = namingParams["monthName"]
    quarterName = namingParams["quarterName"]
    periodChoice = namingParams["periodChoice"]
    filterDates = namingParams["filterDates"]
    periodToDate = namingParams["periodToDate"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    compareWithYearBeforeKey = namingParams["compareWithYearBefore"]
    message = """✳️If your period column has more than two periods (say 2005, 2006, 2007 and 2008)
                        you can choose the most recent period the app must use for its calculations.
                        If the slider is set to "n", the app will compare 2008 to 2007, if it is set to n-1,
                        the app will compare 2007 to 2006, if it is set to n-2,the app will compare 2006 to 2005.
                              """

    (
        choiceArray,
        choiceDict,
        choiceIndex,
        showPeriodChoices,
        paramDict,
    ) = determine_most_recent_period_options(df, paramDict, chartDict)
    if len(choiceArray) > 1 and showPeriodChoices:
        with col:
            disabled = False
            if len(choiceArray) < 5:
                value = insert_json_value(
                    "slider",
                    choiceArray[choiceIndex],
                    automateDict,
                    choiceArray,
                    mostRecentPeriod,
                    None,
                )
                mostRecentPeriodChoice = ui.select_slider(
                    label=mostRecentPeriodLabel,
                    options=choiceArray,
                    value=value,
                    key="mostRecentPeriod",
                    disabled=disabled,
                    label_visibility="visible",
                )
            else:
                index = insert_json_value(
                    "index",
                    choiceIndex,
                    automateDict,
                    choiceArray,
                    mostRecentPeriod,
                    None,
                )
                mostRecentPeriodChoice = ui.selectbox(
                    label=mostRecentPeriodLabel,
                    options=choiceArray,
                    index=choiceIndex,
                    key="mostRecentPeriod",
                    disabled=disabled,
                    label_visibility="visible",
                )
            ui.caption(message)
        mostRecentPeriodChoice = choiceDict[mostRecentPeriodChoice]
        chartDict[mostRecentPeriod] = mostRecentPeriodChoice
        return chartDict, paramDict
    if filterDates in chartDict and chartDict[filterDates]:
        chartDict[mostRecentPeriod] = False
        return chartDict, paramDict
    else:
        mostRecentPeriodChoice = -1
        chartDict[mostRecentPeriod] = mostRecentPeriodChoice
        return chartDict, paramDict


def select_period_order(chartDict, automateDict, paramDict, col):
    """
    if there is a date column the user can choose the time
    period to aggregate data
    """
    namingParams = get_naming_params()
    ascendingPeriodSortMessage = namingParams["ascendingPeriodSortMessage"]
    reversePeriodSortMessage = namingParams["reversePeriodSortMessage"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    periodOrderLabel = namingParams["periodOrderLabel"]
    reverseSortPeriods = namingParams["reverseSortPeriods"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    periodToDate = namingParams["periodToDate"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    compareScenarios = namingParams["compareScenarios"]
    impossibleToProcessFile = namingParams["impossibleToProcessFile"]
    isReverseSortPeriods = notMetConditionValue
    choiceArray = [metConditionValue, notMetConditionValue]
    isReverseSortPeriods = notMetConditionValue
    message = """✳️The app tries to guess the correct period/scenario order. Set to True to reverse it.
                                    """
    tooltip = """The app tries to guess the correct period/scenario. Set to True to reverse it.
                  """
    if impossibleToProcessFile in paramDict and paramDict[impossibleToProcessFile]:
        pass
    else:
        with col:
            if (
                compareWithYearBefore not in chartDict
                or chartDict[compareWithYearBefore] == notMetConditionValue
            ):
                if periodToDate not in chartDict:
                    value = insert_json_value(
                        "index", 1, automateDict, choiceArray, reverseSortPeriods, None
                    )
                    periodOrder = ui.radio(
                        label=periodOrderLabel,
                        options=choiceArray,
                        index=value,
                        help=tooltip,
                        key="periodOrder",
                        label_visibility="visible",
                    )
                    ui.caption(message)
                    if periodOrder:
                        isReverseSortPeriods = metConditionValue
        chartDict[reverseSortPeriods] = isReverseSortPeriods
    return chartDict


def set_up_date_parameters_widgets(
    df, paramDict, chartDict, automateDict, colArray: Sequence
) -> tuple[dict, dict]:
    """Set up date-related parameter widgets.

    If fewer than three columns are supplied, a warning is shown and the
    function returns without modifying the dictionaries.
    """
    namingParams = get_naming_params()
    datasetParametersLabel = namingParams["datasetParametersLabel"]
    if len(colArray) < 3:
        show_warning_ui("Not enough columns to display date-parameter widgets.")
        return chartDict, paramDict
    if is_valid_lazyframe(df):
        chartDict = select_date_aggregation(
            df, paramDict, chartDict, automateDict, colArray[0]
        )
        chartDict = select_by_fiscal_year(
            paramDict, chartDict, automateDict, colArray[1]
        )
        chartDict = select_if_year_before(
            paramDict, chartDict, automateDict, colArray[1]
        )
        chartDict, paramDict = select_most_recent_period(
            df, paramDict, chartDict, automateDict, colArray[2]
        )
        chartDict = select_period_order(chartDict, automateDict, paramDict, colArray[0])
    return chartDict, paramDict


def get_period_aggregation_change_choice(chartDict, newAggregationPeriod, automateDict):
    namingParams = get_naming_params()
    changeAggregationPeriodLabel = namingParams["changeAggregationPeriodLabel"]
    changeAggregationPeriodLabel = (
        changeAggregationPeriodLabel + " " + newAggregationPeriod
    )
    changeAggregationPeriod = namingParams["changeAggregationPeriod"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    tooltip = (
        "If True, changes aggregation period from Year to " + newAggregationPeriod + "."
    )
    index = 0
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, changeAggregationPeriod, None
    )
    chartDict[changeAggregationPeriod] = ui.radio(
        label=changeAggregationPeriodLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key="changeAggregationPeriod",
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(
        """✳️If True, changes aggregation period from Year to """
        + newAggregationPeriod
        + """ if dataset contains data for only one year.
                                """
    )
    return chartDict


def get_exclude_outlier_choice_for_mix_variance(paramDict, chartDict):
    """
    sets up widget to allow user to choose whether to exclude outliers
    """
    namingParams = get_naming_params()
    varianceAggregationParams = get_variance_aggregation_params()
    mixSalesAggregationArray = varianceAggregationParams[
        namingParams["mixSalesAggregationArray"]
    ]
    excludeOutliersLabel = namingParams["excludeOutliersFromMixVarianceLabel"]
    excludeOutliers = namingParams["excludeOutliers"]
    quantileLabel = namingParams["quantileLabel"]
    quantiles = namingParams["quantiles"]
    varianceAggregation = namingParams["varianceAggregation"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    quantilesChoice = 10
    if chartDict[varianceAggregation] in mixSalesAggregationArray:
        chartDict[excludeOutliers] = ui.radio(
            label=excludeOutliersLabel,
            options=booleanRadioOptions,
            index=1,
            key="excludeOutliersForMixVariance",
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(
            """✳️If True, excludes price outliers from mix variance calculation."""
        )
        if excludeOutliers in chartDict and chartDict[excludeOutliers]:
            hashKey = get_hashed_key_for_widgets("quantilesChoice", columnHash)
            chartDict[quantiles] = ui.slider(
                label=quantileLabel,
                min_value=1,
                max_value=15,
                value=quantilesChoice,
                step=1,
                format=None,
                key="hashKey",
                label_visibility="visible",
            )
            ui.caption(
                """✳️Sets price quantile range to drop price outliers from mix variance calculation."""
            )
    return chartDict


def set_up_data_aggregation_widget(paramDict, chartDict, automateDict, col):
    """
    setting up widgets to identify drill down row to move to main report
    """
    namingParams = get_naming_params()
    varianceAggregationParams = get_variance_aggregation_params()
    cogsAggregationArray = varianceAggregationParams[
        namingParams["cogsAggregationArray"]
    ]
    discountsAggregationArray = varianceAggregationParams[
        namingParams["discountsAggregationArray"]
    ]
    varianceAggregation = namingParams["varianceAggregation"]
    varianceAggregationLabel = namingParams["varianceAggregationLabel"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    priceAndUnitsAggregation = namingParams["priceAndUnitsAggregation"]
    priceAndVolumeAggregation = namingParams["priceAndVolumeAggregation"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    varianceInPercentLabel = namingParams["varianceInPercentLabel"]
    varianceInPercent = namingParams["varianceInPercent"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    filterVarianceLabel = namingParams["filterVarianceLabel"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    shareOfTotalMarket = namingParams["shareOfTotalMarket"]
    shareOfTotalMarketLabel = namingParams["shareOfTotalMarketLabel"]
    varianceAggregationOptionsArrayKey = namingParams["varianceAggregationOptionsArray"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    varianceAggregationOptions, percentAggregationsArray, expandedChoiceDict = (
        select_possible_aggregation_options(paramDict)
    )
    varianceAggregationOptions = check_if_options_compatible_with_one_dimensional(
        varianceAggregationOptions, chartDict
    )
    nonIndexOptionsArray = cogsAggregationArray + discountsAggregationArray
    if (
        priceAndUnitsAggregation in varianceAggregationOptions
        and processingChoice in chartDict
        and chartDict[processingChoice] in [runOneDimensionalAnalysis]
    ):
        choice = varianceAggregationOptions.index(priceAndUnitsAggregation)
    elif (
        priceAndVolumeAggregation in varianceAggregationOptions
        and processingChoice in chartDict
        and chartDict[processingChoice] in [runOneDimensionalAnalysis]
    ):
        choice = varianceAggregationOptions.index(priceAndVolumeAggregation)
    else:
        choice = varianceAggregationOptions.index(totalVarianceAggregation)
    chartDict[varianceInPercent] = notMetConditionValue
    chartDict[shareOfTotalMarket] = notMetConditionValue
    with col:
        tooltip = """Choose the type of variance calculation that best answers your question among the possible options.
                    """
        hashKey = get_hashed_key_for_widgets("varianceAggregation", columnHash)
        choice = insert_json_value(
            "index",
            choice,
            automateDict,
            varianceAggregationOptions,
            varianceAggregation,
            None,
        )
        chartDict[varianceAggregation] = ui.selectbox(
            label=varianceAggregationLabel,
            options=varianceAggregationOptions,
            help=tooltip,
            index=choice,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(
            """✳️Choose a variance calculation among the options that can be returned given the columns of your dataset.
                        """
        )
        if 1 == 1:
            chartDict = get_exclude_outlier_choice_for_mix_variance(
                paramDict, chartDict
            )
            if chartDict[varianceAggregation] in percentAggregationsArray:
                hashKey = get_hashed_key_for_widgets(varianceInPercent, columnHash)
                index = 1
                index = insert_json_value(
                    "index",
                    index,
                    automateDict,
                    booleanRadioOptions,
                    varianceInPercent,
                    None,
                )
                chartDict[varianceInPercent] = ui.radio(
                    label=varianceInPercentLabel,
                    options=booleanRadioOptions,
                    index=index,
                    key=hashKey,
                    horizontal=True,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️False for impact on variance in absolute terms, True for impact on variance
                              as % of revenues
                        """
                )
            elif chartDict[varianceAggregation] not in nonIndexOptionsArray:
                hashKey = get_hashed_key_for_widgets(shareOfTotalMarket, columnHash)
                index = 1
                index = insert_json_value(
                    "index",
                    index,
                    automateDict,
                    booleanRadioOptions,
                    shareOfTotalMarket,
                    None,
                )
                chartDict[shareOfTotalMarket] = ui.radio(
                    label=shareOfTotalMarketLabel,
                    options=booleanRadioOptions,
                    index=index,
                    key=hashKey,
                    horizontal=True,
                    label_visibility="visible",
                )
                ui.caption(
                    """✳️To compute the values as share of total, set the widget to True and filter the dataset to the subset you want to analyse.
                        """
                )
            filterOptionArray = []
            if chartDict[varianceAggregation] in expandedChoiceDict:
                filterOptionArray = expandedChoiceDict[chartDict[varianceAggregation]]
            if (
                len(filterOptionArray) > 0
                and chartDict[varianceInPercent] == notMetConditionValue
            ):
                if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
                    filterOptionArray.insert(0, nothingFilteredName)
                    hashKey = get_hashed_key_for_widgets("filterVariance", columnHash)
                    filterVariance = ui.selectbox(
                        label=filterVarianceLabel,
                        options=filterOptionArray,
                        index=0,
                        key=hashKey,
                        label_visibility="visible",
                    )
                    ui.caption(
                        """✳️Filter specific variance types. For price and volume variance
                                    impact on margin or on sales will be returned depending on variance choice.
                                    """
                    )
                    if filterVariance != nothingFilteredName:
                        chartDict[varianceAggregation] = filterVariance
    if chartDict[varianceAggregation] == None:
        paramDict[namingParams["impossibleToProcessFile"]] = True
    chartDict[varianceAggregationOptionsArrayKey] = varianceAggregationOptions
    return paramDict, chartDict


def set_up_main_report_widgets(
    paramDict, chartDict, automateDict, col1Array, col14Expander
):
    """
    setting up widgets for main (not drilldown) processing
    """
    namingParams = get_naming_params()
    processingChoice = namingParams["processingChoice"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    if processingChoice in chartDict and chartDict[processingChoice] in [
        runVariableDimensionalAnalysis,
        runOneDimensionalAnalysis,
    ]:
        paramDict, chartDict = set_up_data_aggregation_widget(
            paramDict, chartDict, automateDict, col1Array[1]
        )
    return paramDict, chartDict


def set_up_count_metrics_widget(
    paramDict, chartDict, automateDict, indexCols, colArray
):
    """
    choose columns where unique item count to be used as metric
    """
    namingParams = get_naming_params()
    countMetricsColumnKey = namingParams["countMetricsColumn"]
    chosenCohortColumnKey = namingParams["chosenCohortColumn"]
    periodName = namingParams["periodName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    likeForLikeLabel = namingParams["likeForLikeLabel"]
    likeForLike = namingParams["likeForLikeName"]
    likeForLikeScopeLabel = namingParams["likeForLikeScopeLabel"]
    likeForLikeScope = namingParams["likeForLikeScope"]
    likeForLikeTwo = namingParams["likeForLikeTwo"]
    likeForLikeAll = namingParams["likeForLikeAll"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    scopeChoiceArray = [likeForLikeAll, likeForLikeTwo]
    columnHash = paramDict[namingParams["columnHash"]]
    indexColsSelectBox = copy.deepcopy(indexCols)
    if periodName in indexColsSelectBox:
        indexColsSelectBox.remove(periodName)
    indexColsSelectBox.insert(0, nothingFilteredName)
    chartDict[likeForLike] = notMetConditionValue
    with colArray[0]:
        container = ui.container()
        if chartDict[chosenCohortColumnKey] != nothingFilteredName:
            hashKey = get_hashed_key_for_widgets(likeForLike, columnHash)
            tooltip = """Select whether you want to perform a like-for-like analysis on the selected column 
            """
            index = insert_json_value(
                "index", 1, automateDict, booleanRadioOptions, likeForLike, None
            )
            chartDict[likeForLike] = container.radio(
                likeForLikeLabel,
                booleanRadioOptions,
                help=tooltip,
                index=index,
                key=hashKey,
                horizontal=True,
            )
            if chartDict[likeForLike]:
                tooltip = """Select the time interval across which you want the like-to-like items to be tracked
                """
                hashKey = get_hashed_key_for_widgets(likeForLikeScope, columnHash)
                index = insert_json_value(
                    "index", 0, automateDict, scopeChoiceArray, likeForLikeScope, None
                )
                chartDict[likeForLikeScope] = container.radio(
                    likeForLikeScopeLabel,
                    scopeChoiceArray,
                    help=tooltip,
                    index=index,
                    key=hashKey,
                    horizontal=True,
                )
    return chartDict


def set_plan_or_forecast_widget(planDict, col, planPlaybackDict):
    namingParams = get_naming_params()
    plName = namingParams["plName"]
    fcName = namingParams["fcName"]
    planOrForecast = namingParams["planOrForecast"]
    planOrForecastLabel = namingParams["planOrForecastLabel"]
    planningOptions = [plName, fcName]
    planDict[planOrForecast] = plName
    with col:
        tooltip = "Build Plan or Forecast dataset."
        index = 0
        index = insert_json_value(
            "index", index, planPlaybackDict, planningOptions, planOrForecast, None
        )
        planDict[planOrForecast] = ui.radio(
            label=planOrForecastLabel,
            options=planningOptions,
            help=tooltip,
            index=index,
            key=planOrForecast,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Build Plan or Forecast dataset.""")
    return planDict


def set_time_profile_widget(planDict, col, planPlaybackDict):
    namingParams = get_naming_params()
    likeBaseYear = namingParams["likeBaseYear"]
    flat = namingParams["flat"]
    custom = namingParams["custom"]
    timeProfile = namingParams["timeProfile"]
    timeProfileLabel = namingParams["timeProfileLabel"]
    timeProfileOptions = [likeBaseYear, flat, custom]
    planDict[timeProfile] = likeBaseYear
    with col:
        tooltip = "Monthly Plan values can be proportional to base year seasonality, flat, or set by user."
        index = 0
        index = insert_json_value(
            "index", index, planPlaybackDict, timeProfileOptions, timeProfile, None
        )
        planDict[timeProfile] = ui.radio(
            label=timeProfileLabel,
            options=timeProfileOptions,
            help=tooltip,
            index=index,
            key=timeProfile,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Seasonality algorithm.""")
    return planDict


def change_discount_and_cogs_in_proportion_to_sales(
    planDict, valueCols, planPlaybackDict
):
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    discountName = namingParams["discountName"]
    cogsName = namingParams["cogsName"]
    changeInProportionToSales = namingParams["changeInProportionToSales"]
    changeInProportionToSalesLabel = namingParams["changeInProportionToSalesLabel"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    planDict[changeInProportionToSales] = notMetConditionValue
    message = changeInProportionToSalesLabel
    disabled = True
    if discountName in valueCols and cogsName in valueCols:
        message = "Forecast discounts and/or COGS."
        disabled = False
    elif discountName in valueCols:
        message = "Forecast discounts."
        disabled = False
    elif cogsName in valueCols:
        message = "Forecast COGS."
        disabled = False
    tooltip = "Forecast other metric of assume change equal to Amount % change."
    message = """✳️""" + message
    index = 1
    index = insert_json_value(
        "index",
        index,
        planPlaybackDict,
        booleanRadioOptions,
        changeInProportionToSales,
        None,
    )
    planDict[changeInProportionToSales] = ui.radio(
        label=changeInProportionToSalesLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=changeInProportionToSales,
        horizontal=True,
        disabled=disabled,
        label_visibility="visible",
    )
    return planDict


def show_percentage_change_widget(
    forecastKey,
    label,
    message,
    tooltip,
    planDict,
    paramDict,
    col,
    forecastType,
    showMessage,
    disabled,
    dimensionNbr,
    itemNbr,
    planPlaybackDict,
):
    namingParams = get_naming_params()
    defaultForecast = namingParams["defaultForecastName"]
    notDefaultForecastName = namingParams["notDefaultForecastName"]
    preparePlanParams = namingParams["preparePlanParams"]
    forecastValueKey = namingParams["forecastValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    hashKey = get_hashed_key_for_widgets(
        forecastKey + forecastType + str(dimensionNbr) + str(itemNbr), columnHash
    )
    minValue, maxValue, startValue = 0, None, 100
    if forecastType == defaultForecast:
        minValue, maxValue, startValue = -100, None, 0
    if preparePlanParams not in planDict:
        planDict[preparePlanParams] = {}
    if preparePlanParams in planDict:
        if forecastType == defaultForecast:
            if defaultForecast not in planDict[preparePlanParams]:
                planDict[preparePlanParams][defaultForecast] = {}
        elif notDefaultForecastName not in planDict[preparePlanParams]:
            planDict[preparePlanParams][notDefaultForecastName] = {}
            if dimensionNbr not in planDict[preparePlanParams][notDefaultForecastName]:
                planDict[preparePlanParams][notDefaultForecastName][dimensionNbr] = {}
    with col:
        valueDict = planPlaybackDict
        key = defaultForecast
        if len(planPlaybackDict) > 0 and forecastType == defaultForecast:
            valueDict = planPlaybackDict[preparePlanParams][defaultForecast]
            key = forecastKey
        elif (
            len(planPlaybackDict) > 0
            and notDefaultForecastName in planPlaybackDict[preparePlanParams]
        ):
            valueDict = planPlaybackDict[preparePlanParams][notDefaultForecastName]
            if str(dimensionNbr) in valueDict:
                valueDict = valueDict[str(dimensionNbr)]
                if forecastValueKey in valueDict:
                    valueDict = valueDict[forecastValueKey]
                    if str(itemNbr) in valueDict:
                        valueDict = valueDict[str(itemNbr)]
                        key = forecastKey
        startValue = insert_json_value(
            "numberInput", startValue, valueDict, [], key, None
        )
        forecastValue = ui.number_input(
            label=label,
            min_value=minValue,
            max_value=maxValue,
            value=startValue,
            step=None,
            format=None,
            key=hashKey,
            help=tooltip,
            disabled=disabled,
            label_visibility="visible",
        )
        if not disabled:
            if forecastType == defaultForecast:
                planDict[preparePlanParams][defaultForecast][
                    forecastKey
                ] = forecastValue
            else:
                if (
                    forecastValueKey
                    not in planDict[preparePlanParams][notDefaultForecastName][
                        dimensionNbr
                    ]
                ):
                    planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][
                        forecastValueKey
                    ] = {}
                if (
                    itemNbr
                    not in planDict[preparePlanParams][notDefaultForecastName][
                        dimensionNbr
                    ][forecastValueKey]
                ):
                    planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][
                        forecastValueKey
                    ][itemNbr] = {}
                planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][
                    forecastValueKey
                ][itemNbr][forecastKey] = forecastValue
        if showMessage:
            ui.caption(message)
    return planDict


def set_collision_choice_widget(planDict, col, planPlaybackDict):
    namingParams = get_naming_params()
    firstChoice = namingParams["firstChoice"]
    allChoice = namingParams["allChoice"]
    collisionChoiceLabel = namingParams["collisionChoiceLabel"]
    collisionChoiceName = namingParams["collisionChoiceName"]
    collisionRadioOptions = [allChoice, firstChoice]
    planDict[collisionChoiceName] = allChoice
    with col:
        tooltip = "How to calculate forecast in case of multiple dimensions with different forecasts."
        index = 0
        index = insert_json_value(
            "index",
            index,
            planPlaybackDict,
            collisionRadioOptions,
            collisionChoiceName,
            None,
        )
        planDict[collisionChoiceName] = ui.radio(
            label=collisionChoiceLabel,
            options=collisionRadioOptions,
            help=tooltip,
            index=index,
            key="collisionChoiceName",
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Multiply all factors or use firui.""")
    return planDict


def add_new_dimension(
    indexCols, dimensionNbr, colArray, hashKey, planDict, planPlaybackDict
):
    namingParams = get_naming_params()
    dimensionLabel = namingParams["dimensionLabel"]
    dimensionKeyName = namingParams["dimensionName"]
    preparePlanParams = namingParams["preparePlanParams"]
    notDefaultForecastName = namingParams["notDefaultForecastName"]
    newDimension = False
    value = None
    valueDict = planPlaybackDict
    if preparePlanParams in planPlaybackDict:
        if notDefaultForecastName in planPlaybackDict[preparePlanParams]:
            valueDict = planPlaybackDict[preparePlanParams][notDefaultForecastName][
                str(dimensionNbr)
            ]
    value = insert_json_value(
        "array", value, valueDict, indexCols, dimensionKeyName, dimensionNbr
    )
    toForecastColumns = colArray[dimensionNbr].multiselect(
        dimensionLabel,
        indexCols,
        key=hashKey + str(dimensionNbr),
        max_selections=3,
        default=value,
    )
    planDict[preparePlanParams][notDefaultForecastName][dimensionNbr][
        dimensionKeyName
    ] = toForecastColumns
    return toForecastColumns, newDimension, planDict


def submit_plan_dataset(paramDict, col):
    namingParams = get_naming_params()
    submitLabel = namingParams["submitLabel"]
    planDataTabLabel = namingParams["planDataTabLabel"]
    columnHash = paramDict[namingParams["columnHash"]]
    tooltip = """Generate """ + planDataTabLabel
    planSubmit = False
    with col:
        hashKey = get_hashed_key_for_widgets("planSubmit", columnHash)
        planSubmit = ui.button(
            label=submitLabel, help=tooltip, key=hashKey, type="primary"
        )
        ui.caption(
            """✳️Hit 🚀Submit to see the result of the simulation and generate the """
            + planDataTabLabel
            + """ and the playback file."""
        )
    return planSubmit


def order_charts(plotArray, orderedChartArray, onePeriodOnlyChartArray, paramDict):
    namingParams = get_naming_params()
    onePeriodOnly = namingParams["onePeriodOnly"]
    outArray = []
    for element in orderedChartArray:
        if onePeriodOnly in paramDict and paramDict[onePeriodOnly]:
            if element in plotArray and element in onePeriodOnlyChartArray:
                outArray.append(element)
        else:
            if element in plotArray:
                outArray.append(element)
    return outArray


def make_available_plots_list(dfPeriods, dfDates, paramDict, chartDict):
    """
    we check if the dataset has the right columns required for the different charts
    """
    namingParams = get_naming_params()
    unitsName = namingParams["unitsName"]
    volumeName = namingParams["volumeName"]
    marginName = namingParams["marginName"]
    timelineChart = namingParams["timelineChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    areaChart = namingParams["areaChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    dotChart = namingParams["dotChart"]
    scatterChart = namingParams["scatterChart"]
    yearName = namingParams["yearName"]
    filterDates = namingParams["filterDates"]
    alternativeCombinationsChart = namingParams["alternativeCombinationsChart"]
    compareWithYearBefore = namingParams["compareWithYearBefore"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    twentyfourMonthsInDataset = namingParams["twentyfourMonthsInDataset"]
    compareScenariosOrPeriods = namingParams["compareScenariosOrPeriods"]
    comparePeriods = namingParams["comparePeriods"]
    compareScenarios = namingParams["compareScenarios"]
    noVarianceAnalysis = namingParams["noVarianceAnalysis"]
    periodChoice = namingParams["periodChoice"]
    onlyMultiDimensionalPlots = [alternativeCombinationsChart]
    periodChoice = chartDict[periodChoice]
    dfPeriodCols, schema = get_schema_and_column_names(dfPeriods)
    dfDatesCols, schema = get_schema_and_column_names(dfDates)
    chartArray = [
        multitierBarChart,
        stackedColumnChart,
        stackedBarChart,
        marimekkoChart,
        dotChart,
        slopeChart,
        stackedParetoChart,
        paretoChart,
        vennChart,
        upsetChart,
        alternativeCombinationsChart,
    ]
    orderedChartArray = [
        stackedColumnChart,
        marimekkoChart,
        stackedBarChart,
        barmekkoChart,
        bubbleChart,
        motionChart,
        scatterChart,
        stackedParetoChart,
        paretoChart,
        boxplotChart,
        ecdfChart,
        histogramChart,
        kernelDensity,
        stripplotChart,
        upsetChart,
        timelineChart,
        multitierBarChart,
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        areaChart,
        dotChart,
        slopeChart,
        vennChart,
        alternativeCombinationsChart,
    ]
    onePeriodOnlyChartArray = [
        stackedColumnChart,
        stackedBarChart,
        marimekkoChart,
        barmekkoChart,
        bubbleChart,
        scatterChart,
        stackedParetoChart,
        paretoChart,
        boxplotChart,
        upsetChart,
        vennChart,
        kernelDensity,
        histogramChart,
        ecdfChart,
        stripplotChart,
    ]
    if is_valid_lazyframe(dfPeriods):
        if (
            marginName in dfPeriodCols
            or unitsName in dfPeriodCols
            or volumeName in dfPeriodCols
        ):
            chartArray = chartArray + [barmekkoChart]
    if is_valid_lazyframe(dfDates):
        chartArray = chartArray + [areaChart]
        if unitsName in dfDatesCols:
            chartArray = chartArray + [motionChart]
        if (
            twentyfourMonthsInDataset in paramDict
            and paramDict[twentyfourMonthsInDataset]
        ):
            if (
                compareScenariosOrPeriods in chartDict
                and chartDict[compareScenariosOrPeriods] == compareScenarios
            ):
                chartArray = chartArray + [
                    timelineChart,
                    multitierColumnChart,
                    horizontalWaterfallChart,
                    trendComparisonChart,
                ]
            else:
                chartArray = chartArray + [
                    timelineChart,
                    multitierColumnChart,
                    horizontalWaterfallChart,
                    trendComparisonChart,
                    trendComparisonByPeriodChart,
                ]
        elif filterDates in chartDict and chartDict[filterDates]:
            chartArray = chartArray + [
                timelineChart,
                trendComparisonChart,
                multitierColumnChart,
                horizontalWaterfallChart,
            ]
        else:
            chartArray = chartArray + [timelineChart]
    if 1 == 1 or unitsName in dfPeriodCols:
        chartArray = chartArray + [bubbleChart]
        if (
            1 == 1
            or compareScenariosOrPeriods in chartDict
            and chartDict[compareScenariosOrPeriods] == comparePeriods
        ):
            chartArray = chartArray + [
                kernelDensity,
                histogramChart,
                ecdfChart,
                boxplotChart,
                stripplotChart,
            ]
    if 1 == 1 or unitsName in dfPeriodCols + dfDatesCols:
        chartArray = chartArray + [scatterChart]
    if chartDict[processingChoice] in [runOneDimensionalAnalysis, noVarianceAnalysis]:
        oneDimensionalChartArray = []
        for element in chartArray:
            if element not in onlyMultiDimensionalPlots:
                oneDimensionalChartArray.append(element)
        chartArray = order_charts(
            oneDimensionalChartArray,
            orderedChartArray,
            onePeriodOnlyChartArray,
            paramDict,
        )
        return chartArray
    else:
        chartArray = order_charts(
            chartArray, orderedChartArray, onePeriodOnlyChartArray, paramDict
        )
        return chartArray


def explain_chart(chartDict, paramDict):
    """
    Display short explanation of plot type
    """
    namingParams = get_naming_params()
    alternativeCombinationsChart = namingParams["alternativeCombinationsChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    areaChart = namingParams["areaChart"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    dotChart = namingParams["dotChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    chosenChart = namingParams["chosenChart"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    message = "✳️To plot, hit " + submitPlotLabel + ". "
    if chosenChart in chartDict:
        if chartDict[chosenChart] == alternativeCombinationsChart:
            ui.caption(
                message
                + """✳️The **"""
                + alternativeCombinationsChart
                + """** chart shows, for each dimension of a given row result, the variance value that results 
                   by changing the filter on that specific dimension.        
                              """
            )
        elif chartDict[chosenChart] == areaChart:
            ui.caption(
                """✳️The **"""
                + areaChart
                + """** chart shows the evolution of the available metrics over time in absolute value or as % of the total.
                   A set of plots is generated for each dimension.
                   Click on the ➕ expander below for more options.                      
                              """
            )
        elif chartDict[chosenChart] == barmekkoChart:
            ui.caption(
                """✳️The **"""
                + barmekkoChart
                + """**, also called area bar chart, is a variable width horizontal bar chart.
                    The area of each bar corresponds to the product of the metrics mapped on the bar length and on the bar width.
                    Click on the ➕ expander below for more options.  
                        """
            )
        elif chartDict[chosenChart] == boxplotChart:
            ui.caption(
                """✳️The **"""
                + boxplotChart
                + """** chart is a statistical representation of the distribution of a variable through its quartiles.
                   The ends of the box represent the lower and upper quartiles, while the median (second quartile) is marked by a line inside 
                   the box. 
                   Click on the ➕ expander below for more options.  
                   """
            )
        elif chartDict[chosenChart] == bubbleChart:
            ui.caption(
                """✳️The **"""
                + bubbleChart
                + """** chart shows three metrics (for instance price, units sales and revenues) face-to-face in period 1 and period 2.
                  A pair of plots is generated for each dimension. 
                  Click on the ➕ expander below for more options.  
                  """
            )
        elif chartDict[chosenChart] == dotChart:
            ui.caption(
                """✳️The **"""
                + dotChart
                + """** chart is a composite chart with circles and lines. 
                   It is ideal for illustrating change while retaining the information about the absolute values. 
                   Click on the ➕ expander below for more options.                    
                              """
            )
        elif chartDict[chosenChart] == ecdfChart:
            ui.caption(
                """✳️The **"""
                + ecdfChart
                + """** chart is a representation of the distribution of numerical data 
                    (for example prices): it shows, at any specified point of the measured variable, the fraction of 
                    observations of the measured variable that are less than or equal to the specified value. 
                    Click on the ➕ expander below for more options.  
                    """
            )
        elif chartDict[chosenChart] == histogramChart:
            ui.caption(
                """✳️The **"""
                + histogramChart
                + """** chart is a representation of the distribution of numerical data 
                    (for example prices), where the data are binned and the count for each bin is represented by the height of each column.
                    Click on the ➕ expander below for more options.   
                    """
            )
        elif chartDict[chosenChart] == horizontalWaterfallChart:
            ui.caption(
                """✳️The **"""
                + horizontalWaterfallChart
                + """** chart compares two scenarios or periods over time
                    along with the absolute and relative variance.
                    Click on the ➕ expander below for more options.                    
                              """
            )
        elif chartDict[chosenChart] == kernelDensity:
            ui.caption(
                """✳️The **"""
                + kernelDensity
                + """** chart shows the distribution of a metric (for example price) in period 1 and in period 2. 
                Click on the ➕ expander below for more options.  
                """
            )
        elif chartDict[chosenChart] == marimekkoChart:
            ui.caption(
                """✳️The **"""
                + marimekkoChart
                + """** chart is used to visualise categorical data over a pair of variables. 
                                In a Marimekko Chart, both axes are variable with a percentage scale, that determines both 
                                the width and height of each segment.
                                Click on the ➕ expander below for more options.  
                                """
            )
        elif chartDict[chosenChart] == motionChart:
            ui.caption(
                """✳️The **"""
                + motionChart
                + """** chart shows three metrics (for instance price, units sales and revenues) over time in a Gapminder-like graph. 
                              A plot is generated for each dimension.
                               Click on the ➕ expander below for more options.  
                               """
            )
        elif chartDict[chosenChart] == multitierBarChart:
            ui.caption(
                """✳️The **"""
                + multitierBarChart
                + """** chart compares two scenarios across categories 
                    along with the absolute and relative variance. 
                    Click on the ➕ expander below for more options.                 
                              """
            )
        elif chartDict[chosenChart] == multitierColumnChart:
            ui.caption(
                """✳️The **"""
                + multitierColumnChart
                + """** chart compares two scenarios or periods over time
                    along with the absolute and relative variance.  
                    Click on the ➕ expander below for more options.                 
                              """
            )
        elif chartDict[chosenChart] == paretoChart:
            ui.caption(
                """✳️The **"""
                + paretoChart
                + """** plot is a type of chart that contains both bars and a line graph, 
                    where individual values are represented in descending order by bars, and the cumulative total is represented by the line.
                    Click on the ➕ expander below for more options.                    
                              """
            )
        elif chartDict[chosenChart] == scatterChart:
            ui.caption(
                """✳️The **"""
                + scatterChart
                + """** chart shows the relationship among two metrics. 
                              To better visualise large datasets, you can plot the scatter as a datashader heatmap.
                              Click on the ➕ expander below for more options.   
                              """
            )
        elif chartDict[chosenChart] == slopeChart:
            ui.caption(
                message
                + """✳️The **"""
                + slopeChart
                + """** chart shows the value of the available metrics in t0 and t1 in absolute value or as % of the total.
                   A set of plots is generated for each dimension.
                  Click on the ➕ expander below for more options.                      
                              """
            )
        elif chartDict[chosenChart] == stackedBarChart:
            ui.caption(
                """✳️The **"""
                + stackedBarChart
                + """** chart shows the ranking of the biggest absolute numbers or the % of the total.
                    Click below for more options.  
                    """
            )
        elif chartDict[chosenChart] == stackedColumnChart:
            ui.caption(
                """✳️The **"""
                + stackedColumnChart
                + """** chart shows the value of the available metrics over time in absolute value or as % of the total.
                   A set of plots is generated for each dimension.
                   Click on the ➕ expander below for more options.  
                     """
            )
        elif chartDict[chosenChart] == stackedParetoChart:
            ui.caption(
                """✳️The **"""
                + stackedParetoChart
                + """** plot is a type of chart that shows the pareto ABC classes with a horizontal stacked bar.  
                  Click on the ➕ expander below for more options.                   
                              """
            )
        elif chartDict[chosenChart] == stripplotChart:
            ui.caption(
                """✳️The **"""
                + stripplotChart
                + """** chart is a scatter plot where the x axis represents a categorical variable. 
                    A small random jitter value is applied to each data point such that the separation between points becomes clearer.
                    Click on the ➕ expander below for more options.    
                    """
            )

        elif chartDict[chosenChart] == timelineChart:
            ui.caption(
                """✳️The **"""
                + timelineChart
                + """** chart shows the evolution of the available metrics over time in absolute value or as % of the total.
                   A set of plots is generated for each dimension.
                   Click on the ➕ expander below for more options.                  
                              """
            )
        elif chartDict[chosenChart] == trendComparisonChart:
            ui.caption(
                """✳️The **"""
                + trendComparisonChart
                + """** plot compares two timelines showing the differences with red and green areas. 
                  Click on the ➕ expander below for more options.                    
                              """
            )
        elif chartDict[chosenChart] == trendComparisonByPeriodChart:
            ui.caption(
                """✳️The **"""
                + trendComparisonByPeriodChart
                + """** chart shows this year vs previous year 
                              performance along different time spans.
                              Click on the ➕ expander below for more options.   """
            )
        elif chartDict[chosenChart] == upsetChart:
            ui.caption(
                """✳️The **"""
                + upsetChart
                + """** plot provides an efficient way to visualize intersections of multiple sets 
                    compared to the traditional approaches, i.e. the Venn Diagram.
                    Click on the ➕ expander below for more options.                      
                              """
            )
        elif chartDict[chosenChart] == vennChart:
            ui.caption(
                """✳️The **"""
                + vennChart
                + """** plot uses circles to show the relationships among things. 
                    Circles that overlap have a commonality while circles that do not overlap do not share those traits. 
                    Click on the ➕ expander below for more options.                    
                              """
            )
    return None


def get_plot_small_multiples_widget(chartDict, automateDict, paramDict, chosenChart):
    namingParams = get_naming_params()
    plotSmallMultiplesLabel = namingParams["plotSmallMultiplesLabel"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    timelineChart = namingParams["timelineChart"]
    slopeChart = namingParams["slopeChart"]
    upsetChart = namingParams["upsetChart"]
    vennChart = namingParams["vennChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 0
    if chosenChart in [
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        upsetChart,
        vennChart,
        stackedBarChart,
    ]:
        chartDict[plotSmallMultiplesKey] = metConditionValue
        index = 0
    else:
        if chosenChart in [
            stackedColumnChart,
            slopeChart,
        ]:
            index = 1
        hashKey = get_hashed_key_for_widgets(
            "plotSmallMultiplesOtherCharts", columnHash
        )
        index = insert_json_value(
            "index",
            index,
            automateDict,
            booleanRadioOptions,
            plotSmallMultiplesKey,
            None,
        )
        chartDict[plotSmallMultiplesKey] = ui.radio(
            label=plotSmallMultiplesLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Plot as small multiples.  
                                            """)
    return chartDict


def delete_fixed_scale_value(chartDict, chartName, key, paramDict):
    namingParams = get_naming_params()
    fixedScaleValueKey = namingParams["fixedScaleValue"]
    if key and key in chartDict:
        if not chartDict[key]:
            sessionKey = fixedScaleValueKey + "_" + chartName
            if sessionKey in session_state:
                del session_state[sessionKey]
                message = "Fix chart scale   value deleted"
                paramDict = add_info_message_in_plot_charts_tab(paramDict, message)
    return paramDict


def get_fix_scales(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fixedScaleChoiceLabel = namingParams["fixedScaleChoiceLabel"]
    fixedScaleChoice = namingParams["fixedScaleChoice"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    chosenChart = namingParams["chosenChart"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 1
    if plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]:
        hashKey = get_hashed_key_for_widgets(fixedScaleChoice, columnHash)
        helpMessage = "Fix chart scale across multiple plots ."
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, fixedScaleChoice, None
        )
        chartDict[fixedScaleChoice] = ui.radio(
            label=fixedScaleChoiceLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Fix chart scale across multiple plots.""")
        chosenChart = chartDict[chosenChart]
        paramDict = delete_fixed_scale_value(
            chartDict, chosenChart, fixedScaleChoice, paramDict
        )
    return chartDict, paramDict


def get_metric_choice(df, chosenChart, paramDict, chartDict, automateDict, valueCols):
    """
    sets up widget to allow user to choose metrics for plots
    """
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    areaChart = namingParams["areaChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    selectMetricsToPlotLabel = namingParams["selectMetricsToPlotLabel"]
    selectSingleMetricLabel = namingParams["selectSingleMetricLabel"]
    singleMetric = namingParams["singleMetric"]
    metricsToPlot = namingParams["metricsToPlot"]
    dotChart = namingParams["dotChart"]
    slopeChart = namingParams["slopeChart"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    unitsName = namingParams["unitsName"]
    bubbleSizeLabel = namingParams["bubbleSizeLabel"]
    yAxisLabel = namingParams["yAxisLabel"]
    xAxisLabel = namingParams["xAxisLabel"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    bubbleSize = namingParams["bubbleSize"]
    nanFillValue = namingParams["nanFillValue"]
    indirectCostsName = namingParams["indirectCostsName"]
    netMarginName = namingParams["netMarginName"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginName = namingParams["marginName"]
    selectedPeriods = namingParams["selectedPeriods"]
    cogsName = namingParams["cogsName"]
    pricePerUnitName = namingParams["pricePerUnitName"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    countMetricsAvgArray = namingParams["countMetricsAvgArray"]
    countMetricsSumArray = namingParams["countMetricsSumArray"]
    selectAllLabel = namingParams["selectAllLabel"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    workColumn = namingParams["workColumn"]
    periodOrder = chartDict[selectedPeriods]
    countMetricCharts = [
        multitierBarChart,
        stackedBarChart,
        dotChart,
        slopeChart,
        stackedColumnChart,
        trendComparisonChart,
        multitierColumnChart,
    ]
    countMetricSmallMultipleCharts = [timelineChart]
    columnHash = paramDict[namingParams["columnHash"]]
    smallMultiples = False
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        smallMultiples = True
    if countMetricsAvgArray in chartDict and len(chartDict[countMetricsAvgArray]) > 0:
        if chosenChart in countMetricCharts or (
            chosenChart in countMetricSmallMultipleCharts and smallMultiples
        ):
            valueCols = valueCols + chartDict[countMetricsAvgArray]
            valueCols = list(set(valueCols))
    if countMetricsSumArray in chartDict and len(chartDict[countMetricsSumArray]) > 0:
        if chosenChart in countMetricCharts or (
            chosenChart in countMetricSmallMultipleCharts
            and plotSmallMultiplesKey in chartDict
            and chartDict[plotSmallMultiplesKey]
        ):
            valueCols = valueCols + chartDict[countMetricsSumArray]
            valueCols = list(set(valueCols))
    if chosenChart in [
        marimekkoChart,
        barmekkoChart,
        areaChart,
        horizontalWaterfallChart,
        stackedColumnChart,
        stackedBarChart,
        paretoChart,
        stackedParetoChart,
    ]:
        valueColsWithPrice = copy.deepcopy(valueCols)
        if chosenChart in [
            marimekkoChart,
            areaChart,
            stackedBarChart,
            paretoChart,
            stackedParetoChart,
        ]:
            if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
                nothingFilteredName
            ]:
                valueColsWithPrice = add_price_to_value_cols(valueCols, df)
                metricsToRemove = [indirectCostsName, netMarginName]
            elif chosenChart in [stackedBarChart]:
                valueColsWithPrice = add_price_to_value_cols(valueCols, df)
                metricsToRemove = [
                    indirectCostsName,
                    netMarginName,
                ]
            else:
                metricsToRemove = (
                    priceMetricsArray
                    + [indirectCostsName, netMarginName]
                    + percentMetricsArray
                )
        elif chosenChart in [barmekkoChart]:
            metricsToRemove = [indirectCostsName, netMarginName]
            valueColsWithPrice = add_price_to_value_cols(valueCols, df)
        elif chosenChart in [
            stackedColumnChart,
        ]:
            metricsToRemove = [indirectCostsName, netMarginName]
            valueColsWithPrice = add_price_to_value_cols(valueCols, df)
        elif chosenChart in [horizontalWaterfallChart]:
            metricsToRemove = (
                priceMetricsArray + [indirectCostsName] + percentMetricsArray
            )
        for metric in metricsToRemove:
            if metric in valueColsWithPrice:
                valueColsWithPrice = take_filtered_value_out_of_option_list(
                    valueColsWithPrice, metric
                )
    else:
        metricsToRemove = []
        if (
            chosenChart in [multitierBarChart, multitierColumnChart]
            and not smallMultiples
        ):
            metricsToRemove = percentMetricsArray
        valueColsWithPrice = add_price_to_value_cols(valueCols, df)
        valueColsWithPrice = add_promo_metric_to_valuecols(
            df, paramDict, valueColsWithPrice
        )
        for metric in metricsToRemove:
            if metric in valueColsWithPrice:
                valueColsWithPrice = take_filtered_value_out_of_option_list(
                    valueColsWithPrice, metric
                )
        df, paramDict, valueColsWithPrice = process_if_promo_data(
            df, paramDict, valueColsWithPrice
        )
    valueColsWithPrice.sort()
    valueColsWithPriceSelect = copy.deepcopy(valueColsWithPrice)
    valueColsTwo = copy.deepcopy(valueColsWithPrice)
    acVsPlTimeline = False
    if chosenChart in [trendComparisonChart]:
        acVsPlTimeline = True
    if chosenChart in [stackedBarChart]:
        valueColsWithPriceSelect, chartDict = get_growth_metrics_for_bubble(
            chartDict, periodOrder, valueColsWithPriceSelect
        )
        valueColsTwo = copy.deepcopy(valueColsWithPriceSelect)
    if chosenChart in [marimekkoChart, dotChart]:
        tooltip = """✳️Metric to map in chart."""
        message = """✳️Metric to map in chart."""
        hashKey = get_hashed_key_for_widgets(singleMetric, columnHash)
        try:
            value = valueColsWithPriceSelect.index(amountName)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while computing the metric index.")
            value = len(valueColsWithPriceSelect) - 1
        value = insert_json_value(
            "index", value, automateDict, valueColsWithPriceSelect, singleMetric, None
        )
        chartDict[singleMetric] = ui.selectbox(
            label=selectSingleMetricLabel,
            options=valueColsWithPriceSelect,
            index=value,
            help=tooltip,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    elif chosenChart in [barmekkoChart]:
        if (
            marginName in valueColsWithPriceSelect
            and marginInPercentName not in valueColsWithPriceSelect
        ):
            valueColsWithPriceSelect.insert(0, marginInPercentName)
        if (
            marginName in valueColsWithPriceSelect
            and netOfDiscountName in valueColsWithPriceSelect
            and marginInPercentOfNetSalesName not in valueColsWithPriceSelect
        ):
            valueColsWithPriceSelect.insert(0, marginInPercentOfNetSalesName)
        verticalAxisMetricArray = copy.deepcopy(valueColsWithPriceSelect)
        verticalAxisMetricArray = get_compatible_metrics_for_barmekko(
            None, verticalAxisMetricArray
        )
        tooltip = """✳️Metric mapped as vertical y-axis"""
        message = """✳️Metric to map as vertical y-axis."""
        hashKey = get_hashed_key_for_widgets("yAxisMetric", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, verticalAxisMetricArray, yAxisMetric, None
        )
        chartDict[yAxisMetric] = ui.selectbox(
            label=yAxisLabel,
            options=verticalAxisMetricArray,
            index=index,
            help=tooltip,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        horizontalAxisMetricArray = get_compatible_metrics_for_barmekko(
            chartDict[yAxisMetric], valueColsWithPriceSelect
        )
        tooltip = """✳️Metric mapped as horizontal x-axis"""
        message = """✳️Metric to map as horizontal x-axis. Only metrics that multiplied by first metric return a valid third 'area' metric can be chosen."""
        index = 0
        index = insert_json_value(
            "index", index, automateDict, horizontalAxisMetricArray, xAxisMetric, None
        )

        hashKey = get_hashed_key_for_widgets("xAxisMetric", columnHash)
        chartDict[xAxisMetric] = ui.selectbox(
            label=xAxisLabel,
            options=horizontalAxisMetricArray,
            index=index,
            help=tooltip,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        chartDict = get_multiplied_dimension(chartDict)
    elif (
        chosenChart
        in [
            multitierBarChart,
            slopeChart,
            timelineChart,
            areaChart,
            paretoChart,
            stackedParetoChart,
            stackedColumnChart,
            stackedBarChart,
            horizontalWaterfallChart,
            trendComparisonByPeriodChart,
            multitierColumnChart,
        ]
        or acVsPlTimeline
    ):
        # valueColsTwo.insert(0, nanFillValue)
        maxSelections = None
        if chosenChart in [
            # stackedColumnChart,
            areaChart
        ]:
            for element in priceMetricsArray:
                if element in valueColsTwo:
                    valueColsTwo.remove(element)
        tooltip = """Select the metrics you want to plot. To plot by dimension, choose one metric only.
                        """
        message = """✳️Select the metrics to plot. To plot by dimension, choose one metric only."""
        try:
            value = valueColsTwo.index(amountName)
        except Exception as e:
            logging.exception(e)
            ui.error("Something went wrong while computing the metric index.")
            value = 0
        checkboxValue = False
        maxSelections = None
        defaultValue = valueColsTwo[value]
        if chosenChart in [stackedColumnChart, stackedBarChart]:
            tooltip = """Metrics to plot.
                        """
            message = """✳️Select two metrics to plot an overlay chart.
                    """
            maxSelections = 2
        elif chosenChart in [slopeChart]:
            tooltip = """Metrics to plot.  
                        """
            message = """✳️Metrics to plot."""
        elif chosenChart in [paretoChart, stackedParetoChart]:
            tooltip = """Select the ranking metric for the pareto chart, then add other metrics for comparison. 
                        """
            message = """✳️The ranking metric must be selected as firui. Add the other metrics you want to compare on the pareto plot. 
            """
            checkboxValue = False
            defaultValue = valueColsTwo[:3]
        container = ui.container()
        choiceKey = metricsToPlot + "Checkbox"
        checkboxValue = insert_json_value(
            "checkbox", checkboxValue, automateDict, None, choiceKey, None
        )
        hashKey = get_hashed_key_for_widgets("Selectallmetrics", columnHash)
        chooseAll = ui.checkbox(
            label=selectAllLabel,
            key=hashKey,
            value=checkboxValue,
            label_visibility="visible",
        )
        chartDict[choiceKey] = chooseAll

        hashKey = get_hashed_key_for_widgets("metricsToPlot", columnHash)
        if chooseAll:
            defaultValue = insert_json_value(
                "array", valueColsTwo, automateDict, valueColsTwo, metricsToPlot, None
            )
            metricsChoiceArray = container.multiselect(
                label=selectMetricsToPlotLabel,
                options=valueColsTwo,
                default=defaultValue,
                help=tooltip,
                key=hashKey,
                max_selections=maxSelections,
            )
        else:
            defaultValue = insert_json_value(
                "array", defaultValue, automateDict, valueColsTwo, metricsToPlot, None
            )
            metricsChoiceArray = container.multiselect(
                label=selectMetricsToPlotLabel,
                options=valueColsTwo,
                default=defaultValue,
                help=tooltip,
                key=hashKey,
                max_selections=maxSelections,
            )
        ui.caption(message)
        if len(metricsChoiceArray) == 0 or (
            metricsChoiceArray and nanFillValue in metricsChoiceArray
        ):
            chartDict[metricsToPlot] = [valueColsTwo[value]]
        elif metricsChoiceArray and nanFillValue not in metricsChoiceArray:
            chartDict[metricsToPlot] = metricsChoiceArray
        else:
            chartDict[metricsToPlot] = [valueColsWithPrice[0]]
    else:
        if chosenChart in [bubbleChart, motionChart]:
            bubbleSizeMetricArray = []
            for element in valueColsWithPrice:
                if element in valueMetricsArray + volumeMetricsArray:
                    bubbleSizeMetricArray.append(element)
            if amountName in valueColsWithPrice:
                bubbleIndex = bubbleSizeMetricArray.index(amountName)
            else:
                bubbleIndex = 0
            hashKey = get_hashed_key_for_widgets("bubbleSize", columnHash)
            bubbleIndex = insert_json_value(
                "index",
                bubbleIndex,
                automateDict,
                bubbleSizeMetricArray,
                bubbleSize,
                None,
            )
            chartDict[bubbleSize] = ui.selectbox(
                label=bubbleSizeLabel,
                options=bubbleSizeMetricArray,
                index=bubbleIndex,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption("""✳️Metric mapped as chart bubble size""")
            valueColsTwo = take_filtered_value_out_of_option_list(
                valueColsTwo, chartDict[namingParams["bubbleSize"]]
            )
        if (
            chosenChart in [bubbleChart, motionChart, scatterChart]
            and not acVsPlTimeline
        ):
            nonMetricNumericColumns = namingParams["nonMetricNumericColumns"]
            if chosenChart in [scatterChart] and nonMetricNumericColumns in paramDict:
                valueColsTwo = valueColsTwo + paramDict[nonMetricNumericColumns]
            if chosenChart in [bubbleChart, scatterChart]:
                valueColsTwo, chartDict = get_growth_metrics_for_bubble(
                    chartDict, periodOrder, valueColsTwo
                )
            if chosenChart in [bubbleChart, motionChart, scatterChart]:
                valueColsTwo, chartDict = get_gross_margin_metrics_for_bubble(
                    chartDict, valueColsTwo, valueColsWithPriceSelect
                )
            if unitsName in valueColsTwo:
                yIndex = valueColsTwo.index(unitsName)
            else:
                yIndex = 0
            if workColumn in valueColsTwo:
                valueColsTwo.remove(workColumn)
            hashKey = get_hashed_key_for_widgets("yAxisMetric", columnHash)
            yIndex = insert_json_value(
                "index", yIndex, automateDict, valueColsTwo, yAxisMetric, None
            )
            chartDict[yAxisMetric] = ui.selectbox(
                label=yAxisLabel,
                options=valueColsTwo,
                index=yIndex,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption("""✳️Metric mapped as chart vertical y-axis.""")
            valueColsThree = copy.deepcopy(valueColsTwo)
            valueColsThree = take_filtered_value_out_of_option_list(
                valueColsThree, chartDict[yAxisMetric]
            )
            if pricePerUnitName in valueColsThree:
                xIndex = valueColsThree.index(pricePerUnitName)
            else:
                xIndex = 0
        if chosenChart in [bubbleChart, motionChart, scatterChart]:
            hashKey = get_hashed_key_for_widgets("xAxisMetric", columnHash)
            xIndex = insert_json_value(
                "index", xIndex, automateDict, valueColsThree, xAxisMetric, None
            )
            chartDict[xAxisMetric] = ui.selectbox(
                label=xAxisLabel,
                options=valueColsThree,
                index=xIndex,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption("""✳️Metric mapped as chart horizontal x-axis.""")
    return chartDict


def get_overlay_chart_choice(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    plotOverlayChartLabel = namingParams["plotOverlayChartLabel"]
    plotOverlayChart = namingParams["plotOverlayChart"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metricsToPlotKey = namingParams["metricsToPlot"]
    chosenChart = namingParams["chosenChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[plotOverlayChart] = notMetConditionValue
    metricsToPlot = chartDict[metricsToPlotKey]
    if len(metricsToPlot) == 2 and chartDict[chosenChart] in [stackedBarChart]:
        chartDict[plotOverlayChart] = metConditionValue
    elif len(metricsToPlot) == 2 and (
        plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]
    ):
        index = 0
        hashKey = get_hashed_key_for_widgets(plotOverlayChart, columnHash)
        helpMessage = "True to plot overlay column chart."
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, plotOverlayChart, None
        )
        chartDict[plotOverlayChart] = ui.radio(
            label=plotOverlayChartLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            help=helpMessage,
            label_visibility="visible",
        )
        ui.caption("""✳️True to plot overlay column chart with two metrics.""")
    return chartDict


def get_dimensions_to_plot(chartDict, automateDict, chosenChart, indexCols, paramDict):
    """
    we delete the indexcolumns that the user has seletected for deletion
    """
    namingParams = get_naming_params()
    selectDimensionsToPlotLabel = namingParams["selectDimensionsToPlotLabel"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    multitierBarChart = namingParams["multitierBarChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    timelineChart = namingParams["timelineChart"]
    areaChart = namingParams["areaChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    dotChart = namingParams["dotChart"]
    slopeChart = namingParams["slopeChart"]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    selectAllLabel = namingParams["selectAllLabel"]
    metricsToPlot = namingParams["metricsToPlot"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    chosenCohortColumn = namingParams["chosenCohortColumn"]
    columnHash = paramDict[namingParams["columnHash"]]
    container = ui.container()
    tooltip = """Select one or more columns to plot.
            """
    message = """✳️Select one or more columns that should be plotted.
                  """
    if chosenChart in [stackedColumnChart]:
        tooltip = """Select one or more columns to plot.
            """
        message = """✳️Select columns to plot. If more than one column is selected a summary stacked column plot will be plotted.
                  """
    valueArray = None
    checkboxValue = False
    chartDict[hideTopItemsSlider] = notMetConditionValue
    indexColsSelectBox = copy.deepcopy(indexCols)
    valueArray = copy.deepcopy(indexCols)
    if len(valueArray) > 1:
        valueArray = valueArray[1:]
    else:
        valueArray = copy.deepcopy(indexCols)
    disabled = False
    if metricsToPlot in chartDict and chosenChart in [
        stackedColumnChart,
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        timelineChart,
        areaChart,
        slopeChart,
    ]:
        if len(chartDict[metricsToPlot]) == 1:
            checkboxValue = False
        else:
            disabled = True
            checkboxValue = False
            chartDict[hideTopItemsSlider] = metConditionValue
    hashKey = get_hashed_key_for_widgets("SelectAllDimensionsToPlot", columnHash)
    if plotSmallMultiplesKey in chartDict and chartDict[plotSmallMultiplesKey]:
        if chosenChart in [multitierBarChart]:
            checkboxValue = True
            message = """✳️Select one or more columns that should be plotted. If you select **only one dimension**, the items of that dimension will be plotted **against another chosen dimension**.
                  """
    state_key = f"plot_dims_{chosenChart}"
    saved_selection = session_state.get(state_key)
    # Guard against stale defaults: filter any saved selections not in current options
    valid_options_set = set(indexColsSelectBox)

    def _sanitize_default(default):
        if default is None:
            return None
        # Allow both scalar and iterable defaults; always return a list
        if isinstance(default, str):
            return [default] if default in valid_options_set else []
        try:
            return [x for x in default if x in valid_options_set]
        except Exception:
            return []

    saved_selection = _sanitize_default(saved_selection)

    if disabled:
        chartDict[selectDimensionsToPlot] = []
        session_state[state_key] = []
    else:
        choiceKey = selectDimensionsToPlot + "Checkbox"
        value = insert_json_value(
            "checkbox", checkboxValue, automateDict, None, choiceKey, None
        )
        chooseAll = ui.checkbox(
            label=selectAllLabel, value=value, key=hashKey, label_visibility="visible"
        )
        chartDict[choiceKey] = chooseAll
        hashKeyDimensionsToPlot = get_hashed_key_for_widgets(
            "selectDimensionsToPlot", columnHash
        )
        if chooseAll:
            value = indexColsSelectBox
            value = insert_json_value(
                "array",
                value,
                automateDict,
                indexColsSelectBox,
                selectDimensionsToPlot,
                None,
            )
            # Ensure default only contains valid options; fall back to current value when empty
            default_value = (
                saved_selection
                or _sanitize_default(chartDict.get(selectDimensionsToPlot))
                or value
            )
            chartDict[selectDimensionsToPlot] = container.multiselect(
                label=selectDimensionsToPlotLabel,
                options=indexColsSelectBox,
                default=default_value,
                help=tooltip,
                key=hashKeyDimensionsToPlot,
                max_selections=None,
                disabled=disabled,
            )
        else:
            value = indexColsSelectBox[0]
            if (
                chosenCohortColumn in chartDict
                and chartDict[chosenCohortColumn]
                and metricsToPlot in chartDict
                and len(chartDict[metricsToPlot]) > 0
                and "by " + chartDict[chosenCohortColumn] in chartDict[metricsToPlot][0]
            ):
                disabled = True
                value = None
            value = insert_json_value(
                "array",
                value,
                automateDict,
                indexColsSelectBox,
                selectDimensionsToPlot,
                None,
            )
            # Ensure default only contains valid options; fall back to current value when empty
            default_value = (
                saved_selection
                or _sanitize_default(chartDict.get(selectDimensionsToPlot))
                or value
            )
            chartDict[selectDimensionsToPlot] = container.multiselect(
                label=selectDimensionsToPlotLabel,
                options=indexColsSelectBox,
                default=default_value,
                help=tooltip,
                key=hashKeyDimensionsToPlot,
                max_selections=None,
                disabled=disabled,
            )
        session_state[state_key] = chartDict.get(selectDimensionsToPlot, [])
        ui.caption(message)
    return chartDict


def get_highlight_overlay_chart(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    plotOverlayChart = namingParams["plotOverlayChart"]
    highlightOverlayChartLabel = namingParams["highlightOverlayChartLabel"]
    highlightOverlayChart = namingParams["highlightOverlayChart"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metricsToPlot = namingParams["metricsToPlot"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[highlightOverlayChart] = notMetConditionValue
    if plotOverlayChart in chartDict and chartDict[plotOverlayChart]:
        index = 0
        hashKey = get_hashed_key_for_widgets(highlightOverlayChart, columnHash)
        helpMessage = "True to highlight overlay line."
        index = insert_json_value(
            "index",
            index,
            automateDict,
            booleanRadioOptions,
            highlightOverlayChart,
            None,
        )
        chartDict[highlightOverlayChart] = ui.radio(
            label=highlightOverlayChartLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            help=helpMessage,
            label_visibility="visible",
        )
        ui.caption("""✳️True to highlight overlay line.""")
    return chartDict


def get_top_items_choice(chartDict, automateDict, chosenChart, key, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    numberOfTop = namingParams["numberOfTop"]
    numberOfTopLabel = namingParams["numberOfTopLabel"]
    aggregateOtherItemsLabel = namingParams["aggregateOtherItemsLabel"]
    aggregateOtherItems = namingParams["aggregateOtherItems"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    dotChart = namingParams["dotChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    timelineChart = namingParams["timelineChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    areaChart = namingParams["areaChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    paretoChart = namingParams["paretoChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    scatterChart = namingParams["scatterChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    slopeChart = namingParams["slopeChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    columnHash = paramDict[namingParams["columnHash"]]
    chartDict[key] = {}
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    message = """✳️Number of top items to be shown in each plot."""
    max_value, value, maxIncludesOther, minValue = 10, 3, False, 1
    if (
        chosenChart in [horizontalWaterfallChart, multitierColumnChart]
        and plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
    ):
        max_value, value, maxIncludesOther, minValue = 10, 1, False, 1
    elif (
        chosenChart
        in [
            stackedBarChart,
            marimekkoChart,
            barmekkoChart,
            stackedParetoChart,
            paretoChart,
        ]
        and key == "Y"
    ):
        max_value, value, maxIncludesOther, minValue = 7, 3, True, 1
        message = """✳️Number of small multiple charts to plot."""
    elif chosenChart in [stackedBarChart, marimekkoChart] and key == "W":
        max_value, value, maxIncludesOther, minValue = 8, 4, True, 1
        message = """✳️Number of items on horizontal plot axis."""
    elif chosenChart in [marimekkoChart, barmekkoChart] and key == "X":
        max_value, value, maxIncludesOther, minValue = 15, 10, False, 1
        message = """✳️Number of items on vertical plot axis."""
    elif chosenChart in [stackedBarChart] and key == "X":
        alternativeMax = 9
        message = """✳️Number of items on vertical plot axis."""
        if "Y" in chartDict:
            alternativeMax = int(10 * 7 / chartDict["Y"][numberOfTop])
        elif selectDimensionsToPlot in chartDict:
            if len(chartDict[selectDimensionsToPlot]) > 0:
                alternativeMax = int(10 * 7 / len(chartDict[selectDimensionsToPlot]))
        max_value, value, maxIncludesOther, minValue = (
            min(10, alternativeMax),
            8,
            False,
            1,
        )
    elif (
        chosenChart in [multitierBarChart]
        and key == "Y"
        and plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
    ):
        max_value, value, maxIncludesOther, minValue = 10, 3, False, 1
    elif (
        chosenChart in [multitierBarChart]
        and key == "X"
        and plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
    ):
        alternativeMax = 9
        if "Y" in chartDict:
            alternativeMax = int(10 * 7 / chartDict["Y"][numberOfTop])
        elif selectDimensionsToPlot in chartDict:
            if len(chartDict[selectDimensionsToPlot]) > 0:
                alternativeMax = int(10 * 7 / len(chartDict[selectDimensionsToPlot]))
        max_value, value, maxIncludesOther, minValue = (
            min(8, alternativeMax),
            6,
            False,
            1,
        )
    elif chosenChart in [multitierBarChart] and key == "Y":
        max_value, value, maxIncludesOther, minValue = 10, 4, False, 1
    elif chosenChart in [multitierBarChart]:
        max_value, value, maxIncludesOther, minValue = 10, 4, False, 1
    elif (
        chosenChart in [timelineChart]
        and plotSmallMultiplesKey in chartDict
        and chartDict[plotSmallMultiplesKey]
    ):
        max_value, value, maxIncludesOther, minValue = 10, 3, True, 1
    elif chosenChart in [trendComparisonByPeriodChart]:
        max_value, value, maxIncludesOther, minValue = 10, 3, False, 1
    elif chosenChart in [dotChart]:
        max_value, value, maxIncludesOther, minValue = 20, 10, False, 1
    elif chosenChart in [horizontalWaterfallChart, multitierColumnChart]:
        max_value, value, maxIncludesOther, minValue = 10, 1, False, 1
    elif chosenChart in [vennChart]:
        max_value, value, maxIncludesOther, minValue = 3, 3, True, 1
        if key == "Y":
            max_value, value, maxIncludesOther, minValue = 6, 2, True, 1
    elif chosenChart in [upsetChart]:
        max_value, value, maxIncludesOther, minValue = 20, 5, False, 1
        if key == "Y":
            max_value, value, maxIncludesOther, minValue = 10, 2, False, 1
    elif chosenChart in [stackedParetoChart] and key == "X":
        max_value, value, maxIncludesOther, minValue = 10, 7, True, 1
    elif chosenChart in [stackedColumnChart]:
        if (
            selectDimensionsToPlot in chartDict
            and len(chartDict[selectDimensionsToPlot]) > 0
        ):
            max_value, value, maxIncludesOther, minValue = 10, 8, True, 1
        else:
            max_value, value, maxIncludesOther, minValue = 10, 4, True, 1
    elif chosenChart in [slopeChart]:
        max_value, value, maxIncludesOther, minValue = 7, 4, True, 1
    elif chosenChart in [timelineChart]:
        max_value, value, maxIncludesOther, minValue = 5, 3, True, 1
    elif chosenChart in [areaChart]:
        max_value, value, maxIncludesOther, minValue = 5, 3, True, 1
    elif chosenChart in [scatterChart]:
        message = """✳️Number of small multiple charts to plot."""
    elif chosenChart in [motionChart]:
        max_value, value, maxIncludesOther, minValue = 30, 15, False, 1
    elif chosenChart in [bubbleChart] and key == "X":
        max_value, value, maxIncludesOther, minValue = 30, 10, False, 1
    elif chosenChart in [bubbleChart] and key == "Y":
        message = """✳️Number of small multiple charts to plot."""
        max_value, value, maxIncludesOther, minValue = 10, 3, False, 1
    elif chosenChart in [
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
    ]:
        max_value, value, maxIncludesOther, minValue = 10, 2, False, 1
    chartDict[key][aggregateOtherItems] = notMetConditionValue
    hashKey = get_hashed_key_for_widgets("numberOfTop" + key, columnHash)
    chartDict[key][aggregateOtherItems] = metConditionValue
    choiceArray = list(range(minValue, max_value + 1))
    chartDict[key][numberOfTop] = value
    if hideTopItemsSlider not in chartDict or not chartDict[hideTopItemsSlider]:
        choiceKey = key + str(numberOfTop)
        value = insert_json_value(
            "slider", value, automateDict, choiceArray, choiceKey, None
        )
        chartDict[key][numberOfTop] = ui.slider(
            label=numberOfTopLabel,
            min_value=minValue,
            max_value=max_value,
            value=value,
            step=1,
            format=None,
            key=hashKey,
            label_visibility="visible",
        )
        chartDict[choiceKey] = chartDict[key][numberOfTop] - 1
        ui.caption(message)
        chartDict[key][aggregateOtherItems] = metConditionValue
        if chartDict[key][numberOfTop] == 1:
            chartDict[key][aggregateOtherItems] = metConditionValue
        elif (
            1 == 2
            and chosenChart in [upsetChart, vennChart]
            and (not maxIncludesOther or chartDict[key][numberOfTop] < max_value)
        ):
            hashKey = get_hashed_key_for_widgets(
                "aggregateOtherItems" + key, columnHash
            )
            chartDict[key][aggregateOtherItems] = ui.radio(
                label=aggregateOtherItemsLabel,
                options=booleanRadioOptions,
                index=0,
                key=hashKey,
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️If True, aggregates non-top items together. If False, only plots top items.
                            """
            )
    return chartDict


def get_trendline_choice(df, chartDict, automateDict, chosenChart, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    datashaderLimit = configParams[namingParams["datashaderLimit"]]
    showTrendLine = namingParams["showTrendLine"]
    showTrendLineLabel = namingParams["showTrendLineLabel"]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    showIsoLine = namingParams["showIsoLine"]
    logXAxis = namingParams["logXAxis"]
    logYAxis = namingParams["logYAxis"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 1
    if chartDict[showIsoLine]:
        index = 1
    if not chartDict[logXAxis] and not chartDict[logYAxis]:
        if not chartDict[plotAsHeatmap]:
            hashKey = get_hashed_key_for_widgets("showTrendLine", columnHash)
            index = insert_json_value(
                "index", index, automateDict, booleanRadioOptions, showTrendLine, None
            )
            chartDict[showTrendLine] = ui.radio(
                label=showTrendLineLabel,
                options=booleanRadioOptions,
                index=index,
                key=hashKey,
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption("""✳️If True shows linear regression trendline""")
        else:
            chartDict[showTrendLine] = notMetConditionValue
    else:
        chartDict[showTrendLine] = notMetConditionValue
    return chartDict


def get_isoline_choice(chartDict, automateDict, chosenChart, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    datashaderLimit = configParams[namingParams["datashaderLimit"]]
    pricePerUnitName = namingParams["pricePerUnitName"]
    unitsName = namingParams["unitsName"]
    pricePerVolumeName = namingParams["pricePerVolumeName"]
    pricePerVolumeNetDiscountName = namingParams["pricePerVolumeNetDiscountName"]
    pricePerUnitNetDiscountName = namingParams["pricePerUnitNetDiscountName"]
    volumeName = namingParams["volumeName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    discountInPercentName = namingParams["discountInPercentName"]
    margin = namingParams["marginName"]
    amountName = namingParams["monetaryLocalCurrencyName"]
    discountName = namingParams["discountName"]
    netOfDiscountName = namingParams["netOfDiscountName"]
    yAxisMetric = namingParams["yAxisMetric"]
    xAxisMetric = namingParams["xAxisMetric"]
    logXAxis = namingParams["logXAxis"]
    logYAxis = namingParams["logYAxis"]
    yAxisMetric = chartDict[yAxisMetric]
    xAxisMetric = chartDict[xAxisMetric]
    showIsoLine = namingParams["showIsoLine"]
    showIsoLineLabel = namingParams["showIsoLineLabel"]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    isolineMetric = namingParams["isolineMetric"]
    discountName = namingParams["discountName"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    metricArray = set([yAxisMetric.title(), xAxisMetric.title()])
    unitsPrice = set([pricePerUnitName.title(), unitsName.title()])
    volumePrice = set([pricePerVolumeName.title(), volumeName.title()])
    unitsPriceNetDiscount = set(
        [pricePerUnitNetDiscountName.title(), unitsName.title()]
    )
    volumePriceNetDiscount = set(
        [pricePerVolumeNetDiscountName.title(), volumeName.title()]
    )
    salesMargin = set([marginInPercentName.title(), amountName.title()])
    salesMarginAfterDiscounts = set(
        [marginInPercentOfNetSalesName.title(), netOfDiscountName.title()]
    )
    salesDiscount = set([discountInPercentName.title(), amountName.title()])
    setArray = [
        unitsPrice,
        volumePrice,
        unitsPriceNetDiscount,
        volumePriceNetDiscount,
        salesMargin,
        salesMarginAfterDiscounts,
        salesDiscount,
    ]
    isolineMetricArray = [
        amountName,
        amountName,
        netOfDiscountName,
        netOfDiscountName,
        margin,
        margin,
        discountName,
        discountName,
    ]
    canAddIsolines = notMetConditionValue
    isolineMetricValue = notMetConditionValue
    if not chartDict[logXAxis] and not chartDict[logYAxis]:
        count = 0
        for element in setArray:
            if metricArray == element:
                canAddIsolines = True
                isolineMetricValue = isolineMetricArray[count]
            count = count + 1
        if canAddIsolines and not chartDict[plotAsHeatmap]:
            hashKey = get_hashed_key_for_widgets("showIsoLine", columnHash)
            chartDict[isolineMetric] = isolineMetricValue
            index = 0
            index = insert_json_value(
                "index", index, automateDict, booleanRadioOptions, showIsoLine, None
            )
            chartDict[showIsoLine] = ui.radio(
                label=showIsoLineLabel,
                options=booleanRadioOptions,
                index=index,
                key=hashKey,
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption("""✳️If True adds isolines""")
        else:
            chartDict[isolineMetric] = notMetConditionValue
            chartDict[showIsoLine] = notMetConditionValue
    else:
        chartDict[isolineMetric] = notMetConditionValue
        chartDict[showIsoLine] = notMetConditionValue
    return chartDict


def get_datashader_choice(df, chartDict, automateDict, chosenChart, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    datashaderLimit = configParams[namingParams["datashaderLimit"]]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    plotAsHeatmapLabel = namingParams["plotAsHeatmapLabel"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[plotAsHeatmap] = notMetConditionValue
    if get_row_count(df) <= datashaderLimit:
        hashKey = get_hashed_key_for_widgets("plotAsHeatmap", columnHash)
        index = 1
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, plotAsHeatmap, None
        )
        chartDict[plotAsHeatmap] = ui.radio(
            label=plotAsHeatmapLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️If True plots scatter as a datashader heatmap""")
    return chartDict


def get_aggregate_by_dimension_choice(
    chartDict, chosenChart, indexCols, automateDict, paramDict
):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    aggregateUniquesByDimensionLabel = namingParams["aggregateUniquesByDimensionLabel"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    columnHash = paramDict[namingParams["columnHash"]]
    bouleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[aggregateUniquesByDimension] = notMetConditionValue
    message = """✳️Aggregate unique items by dimension.
                        """
    tooltip = "The aggregating dimension must be a hierarchical parent to the count items dimension."
    indexCols = get_parents_of_dimension(
        chartDict, chosenChart, indexCols, paramDict, False
    )
    if len(indexCols) > 0:
        hashKey = get_hashed_key_for_widgets(aggregateUniquesByDimension, columnHash)
        index = 0
        index = insert_json_value(
            "index",
            index,
            automateDict,
            bouleanRadioOptions,
            aggregateUniquesByDimension,
            None,
        )
        chartDict[aggregateUniquesByDimension] = ui.radio(
            label=aggregateUniquesByDimensionLabel,
            options=bouleanRadioOptions,
            index=index,
            help=tooltip,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    return chartDict, indexCols


def get_plot_values_as_choice(chartDict, automateDict, paramDict, chosenChart):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    plotValuesAsLabel = namingParams["plotValuesAsLabel"]
    percentOfTotalDataset = namingParams["percentOfTotalDataset"]
    percentOfTotalFiltered = namingParams["percentOfTotalFiltered"]
    percentOfResultRow = namingParams["percentOfResultRow"]
    absolute = namingParams["absolute"]
    areaChart = namingParams["areaChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    columnHash = paramDict[namingParams["columnHash"]]
    plotValuesAsOptions = [
        absolute,
        percentOfTotalDataset,
        percentOfTotalFiltered,
        percentOfResultRow,
    ]
    index = 0
    if hideTopItemsSlider not in chartDict or not chartDict[hideTopItemsSlider]:
        if chosenChart in [multitierColumnChart, horizontalWaterfallChart]:
            chartDict[plotValuesAsChoice] = plotValuesAsOptions[0]
        if chosenChart in [stackedBarChart] and chartDict[yAxisDimension] in [
            nothingFilteredName
        ]:
            chartDict[plotValuesAsChoice] = plotValuesAsOptions[0]
        elif chosenChart in [stackedBarChart] or (
            plotSmallMultiplesKey not in chartDict
            or not chartDict[plotSmallMultiplesKey]
        ):
            if (
                chosenChart in [stackedBarChart]
                and yAxisDimension in chartDict
                and chartDict[yAxisDimension] not in [nothingFilteredName]
            ):
                pass
                # index=1
            if chosenChart in [areaChart]:
                index = 1
            hashKey = get_hashed_key_for_widgets("plotValuesAsChoice", columnHash)
            index = insert_json_value(
                "index",
                index,
                automateDict,
                plotValuesAsOptions,
                plotValuesAsChoice,
                None,
            )
            chartDict[plotValuesAsChoice] = ui.radio(
                label=plotValuesAsLabel,
                options=plotValuesAsOptions,
                index=index,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption(
                """✳️Plots chart with: (i) absolute numbers, (ii) percentages of the total dataset value,
                            (iii) percentages of the total dataset value after the applied filters.
                            """
            )
        else:
            chartDict[plotValuesAsChoice] = plotValuesAsOptions[0]
    else:
        chartDict[plotValuesAsChoice] = plotValuesAsOptions[0]
    return chartDict


def get_date_resampling_choice(chartDict, automateDict, chosenChart, paramDict):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    resampleDatesLabel = namingParams["resampleDatesLabel"]
    resampleDates = namingParams["resampleDates"]
    columnHash = paramDict[namingParams["columnHash"]]
    hashKey = get_hashed_key_for_widgets("resampleDates", columnHash)
    value = 1
    value = insert_json_value("slider", value, automateDict, [], resampleDates, None)
    chartDict[resampleDates] = ui.slider(
        label=resampleDatesLabel,
        min_value=1,
        max_value=12,
        value=value,
        step=1,
        format=None,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption("""✳️Resamples values by chosen number of months""")
    return chartDict


def get_count_unique_items_dimension(
    chartDict, automateDict, paramDict, indexCols, chosenChart
):
    namingParams = get_naming_params()
    selectCountUniquesDimensionLabel = namingParams["selectCountUniquesDimensionLabel"]
    countColumn = namingParams["countColumn"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    columnHash = paramDict[namingParams["columnHash"]]
    indexColsSelectBox = copy.deepcopy(indexCols)
    tooltip = """Dimension - the column - on which to count unique items."""
    message = """✳️Dimension on which to count unique items.
                        """
    hashKey = get_hashed_key_for_widgets("countColumn", columnHash)
    index = 0
    index = insert_json_value(
        "index", index, automateDict, indexColsSelectBox, countColumn, None
    )
    chartDict[countColumn] = ui.selectbox(
        label=selectCountUniquesDimensionLabel,
        options=indexColsSelectBox,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )

    ui.caption(message)
    return chartDict


def get_stacked_pareto_parameters(
    chartDict, automateDict, paramDict, chosenChart, df, indexCols
):
    """
    putting together similar widgets
    """
    namingParams = get_naming_params()
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]
    countColumn = namingParams["countColumn"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    selectMetricsToShowInDataColumnLabel = namingParams[
        "selectMetricsToShowInDataColumnLabel"
    ]
    metricsToShowInDataColumn = namingParams["metricsToShowInDataColumn"]
    showMetricsInDataColumn = namingParams["showMetricsInDataColumn"]
    metricsToPlot = namingParams["metricsToPlot"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    columnHash = paramDict[namingParams["columnHash"]]
    bouleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[showMetricsInDataColumn] = notMetConditionValue
    tooltip = """Calculated metrics to plot on the data column at right."""
    message = """✳️Calculated metrics to plot on the data column at right.
                        """
    hashKey = get_hashed_key_for_widgets("metricsToShowInDataColumn", columnHash)
    if metricsToPlot in chartDict:
        metricsToShowInDataColumnArray = find_possible_data_column_metrics(chartDict)
        if len(metricsToShowInDataColumnArray) > 1:
            value = metricsToShowInDataColumnArray[1]
            value = insert_json_value(
                "array",
                value,
                automateDict,
                metricsToShowInDataColumnArray,
                metricsToShowInDataColumn,
                None,
            )
            chartDict[metricsToShowInDataColumn] = ui.multiselect(
                label=selectMetricsToShowInDataColumnLabel,
                options=metricsToShowInDataColumnArray,
                default=value,
                help=tooltip,
                key=hashKey,
                max_selections=None,
                label_visibility="visible",
            )
            ui.caption(message)
        else:
            chartDict[metricsToShowInDataColumn] = metricsToShowInDataColumnArray
    if nothingFilteredName in chartDict[metricsToShowInDataColumn]:
        chartDict[metricsToShowInDataColumn].remove(nothingFilteredName)
    if len(chartDict[metricsToShowInDataColumn]) > 0:
        chartDict[showMetricsInDataColumn] = metConditionValue
    return chartDict


def get_catplot_choice(df, chartDict, automateDict, valueCols, chosenChart, paramDict):
    namingParams = get_naming_params()
    addCatPlotTypeLabel = namingParams["addCatPlotTypeLabel"]
    addCatPlotMetricLabel = namingParams["addCatPlotMetricLabel"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    indirectCostsName = namingParams["indirectCostsName"]
    netMarginName = namingParams["netMarginName"]
    catPlotType = namingParams["catPlotType"]
    catPlotMetric = namingParams["catPlotMetric"]
    columnHash = paramDict[namingParams["columnHash"]]
    hashKey = get_hashed_key_for_widgets("catPlotType", columnHash)
    catPlotArray = [
        nothingFilteredName,
        "strip",
        "box",
        "violin",
    ]
    message = """✳️Plot distribution of variables in UpSet plot"""
    tooltip = """Select plot type to plot distribution of variables"""
    chartDict[catPlotType] = nothingFilteredName
    index = 0
    index = insert_json_value(
        "index", index, automateDict, catPlotArray, catPlotType, None
    )
    chartDict[catPlotType] = ui.selectbox(
        label=addCatPlotTypeLabel,
        options=catPlotArray,
        help=tooltip,
        index=index,
        key=hashKey,
        label_visibility="visible",
    )
    ui.caption(message)
    if chartDict[catPlotType] != nothingFilteredName:
        valueColsSelectBox = []
        for element in valueCols:
            if element not in [indirectCostsName, netMarginName]:
                valueColsSelectBox.append(element)
        message = """✳️Metric to show in distribution plots"""
        tooltip = """Select metric to show in distribution plots"""
        hashKey = get_hashed_key_for_widgets("catPlotMetric", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, valueColsSelectBox, catPlotMetric, None
        )
        chartDict[catPlotMetric] = ui.selectbox(
            label=addCatPlotMetricLabel,
            options=valueColsSelectBox,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
    return chartDict


def get_show_label_choice(df, chosenChart, chartDict, automateDict, paramDict):
    """
    show label or not
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    maxPeriodsForLabels = namingParams["maxPeriodsForLabels"]
    maxPeriodsForLabels = configParams[maxPeriodsForLabels]
    maxPeriodsForBarChart = namingParams["maxPeriodsForBarChart"]
    maxPeriodsForBarChart = configParams[maxPeriodsForBarChart]
    showLegendLabel = namingParams["showLegendLabel"]
    showBoth = namingParams["showBoth"]
    periodName = namingParams["periodName"]
    showLegendLeftOrRight = namingParams["showLegendLeftOrRight"]
    showLegendOnTop = namingParams["showLegendOnTop"]
    showLegend = namingParams["showLegend"]
    showLegendInBars = namingParams["showLegendInBars"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    yAxisDimension = namingParams["yAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    showOptions = [showBoth, showLegendLeftOrRight, showLegendInBars]
    columnHash = paramDict[namingParams["columnHash"]]
    if chosenChart in [stackedBarChart, marimekkoChart]:
        message = """✳️Show legend labels inside the bars, on top, or both."""
        tooltip = """Show legend labels inside the bars, on top, or both."""
        showOptions = [showBoth, showLegendOnTop, showLegendInBars]
    else:
        message = """✳️Show legend labels inside the columns, on the left, or both."""
        tooltip = """Show legend labels inside the columns, on the left, or both."""
        showOptions = [showBoth, showLegendLeftOrRight, showLegendInBars]
    hashKey = get_hashed_key_for_widgets("showLegend", columnHash)
    chartDict[showLegend] = showLegendLeftOrRight
    indexChoice = 0
    showWidget = False
    if is_valid_lazyframe(df):
        showWidget = True
    if showWidget and (
        hideTopItemsSlider not in chartDict or not chartDict[hideTopItemsSlider]
    ):
        periodsArray = get_periods_array(df)
        periodsToPlot = min(maxPeriodsForBarChart, len(periodsArray))
        if chosenChart in [stackedBarChart] and chartDict[yAxisDimension] in [
            nothingFilteredName
        ]:
            chartDict[showLegend] = showLegendOnTop
            showWidget = False
        if chosenChart in [stackedParetoChart]:
            if not chartDict[aggregateUniquesByDimension]:
                showWidget = False
        if chosenChart in [
            stackedColumnChart,
            stackedBarChart,
            marimekkoChart,
            stackedParetoChart,
        ]:
            indexChoice = 1
            if chosenChart in [stackedBarChart, marimekkoChart]:
                betterInBars = get_parents_of_dimension(
                    chartDict, chosenChart, [], paramDict, False
                )
                if betterInBars:
                    indexChoice = 2
        if (
            showWidget
            or (
                chosenChart in [stackedColumnChart]
                and periodsToPlot <= maxPeriodsForLabels
            )
            or (chosenChart in [marimekkoChart] and showWidget)
        ):
            indexChoice = insert_json_value(
                "index", indexChoice, automateDict, showOptions, showLegend, None
            )
            chartDict[showLegend] = ui.radio(
                label=showLegendLabel,
                options=showOptions,
                help=tooltip,
                index=indexChoice,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption(message)
    return chartDict


def get_show_CAGR_choice(df, chosenChart, chartDict, automateDict, paramDict):
    """
    show label or not
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    periodName = namingParams["periodName"]
    showCAGR = namingParams["showCAGR"]
    showCAGRLabel = namingParams["showCAGRLabel"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    absolute = namingParams["absolute"]
    plotValuesAsChoice = namingParams["plotValuesAsChoice"]
    numberOfPeriods = 0
    if is_valid_lazyframe(df) or isinstance(df, pl.DataFrame):
        periodsArray = get_periods_array(df)
        numberOfPeriods = len(periodsArray)
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    columnHash = paramDict[namingParams["columnHash"]]
    if (
        numberOfPeriods > 1
        and plotValuesAsChoice in chartDict
        and chartDict[plotValuesAsChoice] == absolute
    ):
        index = 0
        message = """✳️True to show CAGR values in data column. False to plot chart without CAGR."""
        tooltip = """True to show CAGR values in data column. False to plot chart without CAGR."""
        hashKey = get_hashed_key_for_widgets("showCAGR", columnHash)
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, showCAGR, None
        )
        chartDict[showCAGR] = ui.radio(
            label=showCAGRLabel,
            options=booleanRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(message)
    else:
        chartDict[showCAGR] = notMetConditionValue
    return chartDict


def get_rank_label_choice(df, chartDict, automateDict, paramDict):
    """
    can show rank instead of label on pareto chart
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    showRank = namingParams["showRank"]
    showRankLabel = namingParams["showRankLabel"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    showAbsoluteValuesLabel = namingParams["showAbsoluteValuesLabel"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metConditionValue = namingParams["metConditionValue"]
    countColumn = namingParams["countColumn"]
    showOnly = namingParams["showOnly"]
    showOnlyLabel = namingParams["showOnlyLabel"]
    showAll = namingParams["showAll"]
    showTop = namingParams["showTop"]
    showBottom = namingParams["showBottom"]
    paretoChartManyItems = configParams["paretoChartManyItems"]
    showRadioOptions = [showAll, showTop, showBottom]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    columnHash = paramDict[namingParams["columnHash"]]
    numberOfItems = n_unique_lazy(chartDict[countColumn], df)
    chartDict[showRank] = notMetConditionValue
    chartDict[showOnly] = showAll
    chartDict[showAbsoluteValues] = notMetConditionValue
    message = """✳️True if you want to plot the chart in absolute values and not in %"""
    tooltip = """True absolute values, False % values."""
    hashKey = get_hashed_key_for_widgets("showAbsoluteValues", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, showAbsoluteValues, None
    )
    chartDict[showAbsoluteValues] = ui.radio(
        label=showAbsoluteValuesLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    if numberOfItems > paretoChartManyItems and not chartDict[showAbsoluteValues]:
        message = """✳️True if you want to see ranks as X labels"""
        tooltip = """True: X labels => ranking, False: X labels => labels."""
        hashKey = get_hashed_key_for_widgets("showRank", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, showRank, None
        )
        chartDict[showRank] = ui.radio(
            label=showRankLabel,
            options=booleanRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(message)
    if not chartDict[showRank] and numberOfItems > paretoChartManyItems:
        message = (
            """✳️True to see only top """
            + str(paretoChartManyItems)
            + """ items in the Pareto Chart."""
        )
        tooltip = (
            """True if you want to see only top """
            + str(paretoChartManyItems)
            + """ items."""
        )
        hashKey = get_hashed_key_for_widgets("showOnly", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, showRadioOptions, showOnly, None
        )
        chartDict[showOnly] = ui.radio(
            label=showOnlyLabel,
            options=showRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    return chartDict


def set_up_label_position_widget(chartDict, automateDict, chosenChart, paramDict):
    """
    choose color of bubble labels
    """
    namingParams = get_naming_params()
    positionLegends = namingParams["positionLegends"]
    legendsAtRight = namingParams["legendsAtRight"]
    legendsAtLeft = namingParams["legendsAtLeft"]
    positionLegendLabel = namingParams["positionLegendLabel"]
    positionLabelLabel = namingParams["positionLabelLabel"]
    areaChart = namingParams["areaChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    scatterChart = namingParams["scatterChart"]
    hideTopItemsSlider = namingParams["hideTopItemsSlider"]
    plotAsHeatmap = namingParams["plotAsHeatmap"]
    columnHash = paramDict[namingParams["columnHash"]]
    positionOptions = [legendsAtLeft, legendsAtRight]
    message = """✳️Show legends: at right of chart or at left of chart."""
    tooltip = """Show legends: at right of chart or at left of chart. Click on the legends to adjust their position"""
    label = positionLegendLabel
    chartDict[positionLegends] = legendsAtLeft
    plotWidget = False
    disabled = False
    if chosenChart in [stackedParetoChart] and 1 == 3:
        disabled = True
    if hideTopItemsSlider not in chartDict or not chartDict[hideTopItemsSlider]:
        index = 0
        if chosenChart in [
            stackedColumnChart,
            stackedParetoChart,
            timelineChart,
            areaChart,
        ]:
            index = 0
            plotWidget = True
        if chosenChart in [scatterChart] and not chartDict[plotAsHeatmap]:
            message = """✳️Show isoline labels: at right or at left ."""
            tooltip = """Show isoline labels: at right or at left . Click on the labels to adjust their position"""
            label = positionLabelLabel
            plotWidget = False
            chartDict[positionLegends] = legendsAtRight
        if plotWidget:
            hashKey = get_hashed_key_for_widgets("positionLegends", columnHash)
            index = insert_json_value(
                "index", index, automateDict, positionOptions, positionLegends, None
            )
            chartDict[positionLegends] = ui.radio(
                label=label,
                options=positionOptions,
                help=tooltip,
                horizontal=True,
                index=index,
                key=hashKey,
                label_visibility="visible",
                disabled=disabled,
            )
            ui.caption(message)
    return chartDict


def get_show_outliers(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    showOutliers = namingParams["showOutliers"]
    showOutliersLabel = namingParams["showOutliersLabel"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    message = """✳️Show outliers in boxplot."""
    tooltip = """True to show outliers in boxplot."""
    hashKey = get_hashed_key_for_widgets("showOutliers", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, showOutliers, None
    )
    chartDict[showOutliers] = ui.radio(
        label=showOutliersLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def get_log_X_axis(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    logXAxis = namingParams["logXAxis"]
    logXAxisLabel = namingParams["logXAxisLabel"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    message = """✳️Plot log X-axis."""
    tooltip = """Set X-axis to logarithmic scale."""
    hashKey = get_hashed_key_for_widgets("logXAxis", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, logXAxis, None
    )
    chartDict[logXAxis] = ui.radio(
        label=logXAxisLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def get_show_average_value(chartDict, automateDict, paramDict):
    """ """
    namingParams = get_naming_params()
    metricArrayParams = get_metric_array_params()
    priceMetricsArray = metricArrayParams[namingParams["priceMetricsArray"]]
    percentMetricsArray = metricArrayParams[namingParams["percentMetricsArray"]]
    growthMetricArray = metricArrayParams[namingParams["growthMetricArray"]]
    valueMetricsArray = metricArrayParams[namingParams["valueMetricsArray"]]
    volumeMetricsArray = metricArrayParams[namingParams["volumeMetricsArray"]]
    noSumMetricsArray = metricArrayParams[namingParams["noSumMetricsArray"]]
    yAxisDimension = namingParams["yAxisDimension"]
    metricsToPlot = namingParams["metricsToPlot"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    discountInPercentName = namingParams["discountInPercentName"]
    marginInPercentName = namingParams["marginInPercentName"]
    marginInPercentOfNetSalesName = namingParams["marginInPercentOfNetSalesName"]
    showAverageValueLabel = namingParams["showAverageValueLabel"]
    showAverageValue = namingParams["showAverageValueName"]
    averageName = namingParams["averageName"]
    aggregateOtherItemsName = namingParams["aggregateOtherItemsName"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    defaultAverageShownArray = priceMetricsArray + percentMetricsArray
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    # message="""✳️Show average ("""+averageName+""") value."""
    message = """✳️Show average value."""
    tooltip = (
        """Average value will not be shown if there is an '"""
        + aggregateOtherItemsName
        + """n' aggregated position among the plotted items."""
    )
    hashKey = get_hashed_key_for_widgets("logXAxis", columnHash)
    chartDict[showAverageValue] = notMetConditionValue
    if yAxisDimension in chartDict and chartDict[yAxisDimension] in [
        nothingFilteredName
    ]:
        index = 0
        if (
            metricsToPlot in chartDict
            and len(chartDict[metricsToPlot]) > 0
            and chartDict[metricsToPlot][0] in defaultAverageShownArray
        ):
            index = 0
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, showAverageValue, None
        )
        chartDict[showAverageValue] = ui.radio(
            label=showAverageValueLabel,
            options=booleanRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(message)
    return chartDict


def get_adjust_bubble_label_position(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    adjustBubbleLabels = namingParams["adjustBubbleLabels"]
    adjustBubbleLabelsLabel = namingParams["adjustBubbleLabelsLabel"]
    metConditionValue = namingParams["metConditionValue"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    xAxisDimension = chartDict[xAxisDimension]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if xAxisDimension not in [nothingFilteredName]:
        message = """✳️Manually adjust bubble label position."""
        tooltip = """Adjust bubble label position or let the app do it automatically."""
        hashKey = get_hashed_key_for_widgets("adjustBubbleLabels", columnHash)
        index = 1
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, adjustBubbleLabels, None
        )
        chartDict[adjustBubbleLabels] = ui.radio(
            label=adjustBubbleLabelsLabel,
            options=booleanRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(message)
    return chartDict


def get_show_scatter_labels(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    showScatterLabels = namingParams["showScatterLabels"]
    showScatterLabelsLabel = namingParams["showScatterLabelsLabel"]
    setFactorLabel = namingParams["setFactorLabel"]
    setFactorParameter = namingParams["setFactorParameter"]
    metConditionValue = namingParams["metConditionValue"]
    xAxisDimension = namingParams["xAxisDimension"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    xAxisDimension = chartDict[xAxisDimension]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if 1 == 1 or xAxisDimension not in [nothingFilteredName]:
        message = """✳️Show labels on scatter chart dots."""
        tooltip = """Use mouse to move around and edit labels."""
        hashKey = get_hashed_key_for_widgets("showScatterLabels", columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, showScatterLabels, None
        )
        chartDict[showScatterLabels] = ui.radio(
            label=showScatterLabelsLabel,
            options=booleanRadioOptions,
            help=tooltip,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption(message)

        message = """✳️Lower = 'Show more', Higher = 'Show less'."""
        tooltip = """Lower = 'Show more', Higher = 'Show less'."""
        hashKey = get_hashed_key_for_widgets("setFactorParameter", columnHash)
        value = 3
        chartDict[setFactorParameter] = ui.slider(
            label=setFactorLabel,
            min_value=1.0,
            max_value=10.0,
            value=3.0,
            step=0.5,
            key=hashKey,
            help=tooltip,
            label_visibility="visible",
        )

        ui.caption(message)
    return chartDict


def get_log_Y_axis(chartDict, automateDict, paramDict):
    """
    if bar mekko choose axis to sort on
    """
    namingParams = get_naming_params()
    logYAxis = namingParams["logYAxis"]
    logYAxisLabel = namingParams["logYAxisLabel"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    message = """✳️Plot log Y-axis."""
    tooltip = """Set Y-axis to logarithmic scale."""
    hashKey = get_hashed_key_for_widgets("logYAxis", columnHash)
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, logYAxis, None
    )
    chartDict[logYAxis] = ui.radio(
        label=logYAxisLabel,
        options=booleanRadioOptions,
        help=tooltip,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(message)
    return chartDict


def get_small_multiples_dimension_choice(
    df, chosenChart, chartDict, automateDict, indexCols, paramDict
):
    """
    putting together similar widgets
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    selectsmallMultiplesColumnAsSmallMultiplesLabel = namingParams[
        "selectsmallMultiplesColumnAsSmallMultiplesLabel"
    ]
    smallMultiplesColumn = namingParams["smallMultiplesColumn"]
    marimekkoChart = namingParams["marimekkoChart"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    columnHash = paramDict[namingParams["columnHash"]]
    if len(indexCols) < 3 and chosenChart in [marimekkoChart]:
        chartDict[smallMultiplesColumn] = nothingFilteredName
    else:
        indexColsSelectBox = copy.deepcopy(indexCols)
        message = """✳️Dimension to plot as small multiples."""
        tooltip = """Dimension plot as small multiples."""
        hashKey = get_hashed_key_for_widgets(smallMultiplesColumn, columnHash)
        index = 0
        index = insert_json_value(
            "index", index, automateDict, indexColsSelectBox, smallMultiplesColumn, None
        )
        chartDict[smallMultiplesColumn] = ui.selectbox(
            label=selectsmallMultiplesColumnAsSmallMultiplesLabel,
            options=indexColsSelectBox,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
        chartDict = get_top_items_choice(
            chartDict, automateDict, chosenChart, "Y", paramDict
        )
        indexCols.remove(chartDict[smallMultiplesColumn])
    return chartDict, indexCols


def select_main_column(dfDict, indexCols, col, paramDict, chartDict, automateDict):
    namingParams = get_naming_params()
    nanFillValue = namingParams["nanFillValue"]
    dfName = namingParams["dfName"]
    nothingFilteredName = namingParams["nothingFilteredName"]
    mainDimensionLabel = namingParams["mainDimensionLabel"]
    mainDimension = namingParams["mainDimension"]
    selectMainDimensionLabel = namingParams["selectMainDimensionLabel"]
    selectSmallMultiplesDimensionLabel = namingParams[
        "selectSmallMultiplesDimensionLabel"
    ]
    runVariableDimensionalAnalysis = namingParams["runVariableDimensionalAnalysis"]
    runOneDimensionalAnalysis = namingParams["runOneDimensionalAnalysis"]
    processingChoice = namingParams["processingChoice"]
    plotSmallMultiplesLabel = namingParams["plotSmallMultiplesLabel"]
    plotSmallMultiples = namingParams["plotSmallMultiplesWaterfall"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    numberOfSmallMultiplesLabel = namingParams["numberOfSmallMultiplesLabel"]
    numberOfSmallMultiples = namingParams["numberOfSmallMultiplesWaterfall"]
    aggregateOtherWaterfalls = namingParams["aggregateOtherWaterfalls"]
    aggregateOtherWaterfallsLabel = namingParams["aggregateOtherWaterfallsLabel"]
    varianceInPercent = namingParams["varianceInPercent"]
    varianceAggregation = namingParams["varianceAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    netOfDiscountAggregation = namingParams["marginVarianceAggregation"]
    varianceDifferentCalculations = namingParams["varianceDifferentCalculations"]
    varianceAggregationOptionsArrayKey = namingParams["varianceAggregationOptionsArray"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    indexColsSelectBox = copy.deepcopy(indexCols)
    indexColsSelectBox.insert(0, nothingFilteredName)
    with col:
        if chartDict[processingChoice] in [
            runVariableDimensionalAnalysis,
            runOneDimensionalAnalysis,
        ]:
            if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
                label = selectMainDimensionLabel
                tooltip = """Select the dimensions - the columns - you want to see in every result row.
                  """

            elif chartDict[processingChoice] in [runOneDimensionalAnalysis]:
                label = selectSmallMultiplesDimensionLabel
                tooltip = """Select the dimension - the column - along which you want to slice variance.
                  """
            hashKey = get_hashed_key_for_widgets("mainDimension", columnHash)
            if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
                message = """✳️You can select one (or more) columns as 
                              the dimensions you want see in every row of your bridge.  
                              """
                value = None
                value = insert_json_value(
                    "filterColumn",
                    value,
                    automateDict,
                    indexColsSelectBox,
                    mainDimension,
                    None,
                )
                mainDimensionArray = ui.multiselect(
                    label=label,
                    options=indexColsSelectBox,
                    help=tooltip,
                    key=hashKey,
                    max_selections=None,
                    default=value,
                    label_visibility="visible",
                )
            else:
                message = """✳️Select one dimension along which you want to split variance.  
                              """
                index = 0
                index = insert_json_value(
                    "index",
                    index,
                    automateDict,
                    indexColsSelectBox,
                    mainDimension,
                    None,
                )
                dimensionChoice = ui.selectbox(
                    label=label,
                    options=indexColsSelectBox,
                    index=index,
                    help=tooltip,
                    key=hashKey,
                    label_visibility="visible",
                )
                mainDimensionArray = [dimensionChoice]
            ui.caption(message)
            if chartDict[processingChoice] in [runVariableDimensionalAnalysis]:
                if (
                    len(mainDimensionArray) > 0
                    and nothingFilteredName not in mainDimensionArray
                ):
                    df = dfDict[dfName]
                    df = df.filter(
                        pl.all_horizontal(
                            [pl.col(col) != nanFillValue for col in mainDimensionArray]
                        )
                    )
                    dfDict[dfName] = df
            elif (
                len(mainDimensionArray) > 0
                and nothingFilteredName not in mainDimensionArray
            ):
                chartDict[mainDimension] = mainDimensionArray
            if (
                len(mainDimensionArray) == 1
                and nothingFilteredName not in mainDimensionArray
            ):
                colExpander = ui.expander("➕ Plot variance options")
                if 1 == 1:
                    if chartDict[processingChoice] in [runOneDimensionalAnalysis]:
                        if (
                            len(mainDimensionArray) == 1
                            and nothingFilteredName not in mainDimensionArray
                        ):
                            index = 0
                            if chartDict[varianceAggregation] in [
                                totalVarianceAggregation,
                                netOfDiscountAggregation,
                                marginVarianceAggregation,
                            ]:
                                index = 1
                            hashKey = get_hashed_key_for_widgets(
                                "plotSmallMultiplesWaterfall", columnHash
                            )
                            index = insert_json_value(
                                "index",
                                index,
                                automateDict,
                                booleanRadioOptions,
                                plotSmallMultiples,
                                None,
                            )
                            chartDict[plotSmallMultiples] = ui.radio(
                                label=plotSmallMultiplesLabel,
                                options=booleanRadioOptions,
                                index=index,
                                key=hashKey,
                                horizontal=True,
                                label_visibility="visible",
                            )
                            ui.caption(
                                """✳️You can plot variance as a single chart or as a collection of small multiples.  
                                        """
                            )
                            if chartDict[varianceInPercent] == metConditionValue:
                                chartDict[plotSmallMultiples] = notMetConditionValue
                            if chartDict[plotSmallMultiples]:
                                message = """✳️Number of small multiples charts to be plotted"""
                                maxValue = 9
                                minValue = 1
                                value = 5
                            else:
                                message = """✳️Number of items to plot"""
                                maxValue = 10
                                minValue = 4
                                value = 4
                            chartDict[numberOfSmallMultiples] = value
                            hashKey = get_hashed_key_for_widgets(
                                "numberOfSmallMultiples", columnHash
                            )
                            value = insert_json_value(
                                "slider",
                                value,
                                automateDict,
                                [],
                                numberOfSmallMultiples,
                                None,
                            )
                            chartDict[numberOfSmallMultiples] = ui.slider(
                                label=numberOfSmallMultiplesLabel,
                                min_value=minValue,
                                max_value=maxValue,
                                value=value,
                                step=1,
                                format=None,
                                key=hashKey,
                                label_visibility="visible",
                            )
                            ui.caption(message)
                            chartDict[aggregateOtherWaterfalls] = metConditionValue
    return dfDict, chartDict


def get_plot_as_baseline_chart_widget(chartDict, automateDict, paramDict, chosenChart):
    namingParams = get_naming_params()
    plotAsBaselineLabel = namingParams["plotAsBaselineLabel"]
    plotAsBaseline = namingParams["plotAsBaseline"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    compareToAverageLabel = namingParams["compareToAverageLabel"]
    compareToAverage = namingParams["compareToAverage"]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 1
    index = insert_json_value(
        "index", index, automateDict, booleanRadioOptions, plotAsBaseline, None
    )
    hashKey = get_hashed_key_for_widgets("plotAsBaseline", columnHash)
    chartDict[plotAsBaseline] = ui.radio(
        label=plotAsBaselineLabel,
        options=booleanRadioOptions,
        index=index,
        key=hashKey,
        horizontal=True,
        label_visibility="visible",
    )
    ui.caption(
        """✳️Plot as baseline chart showing difference relative to other period/scenario."""
    )
    if chartDict[plotAsBaseline]:
        index = 1
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, compareToAverage, None
        )
        hashKey = get_hashed_key_for_widgets("compareToAverage", columnHash)
        chartDict[compareToAverage] = ui.radio(
            label=compareToAverageLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            label_visibility="visible",
        )
        ui.caption("""✳️Show difference relative to average.""")
    return chartDict


def get_overlay_chart_choice(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    plotOverlayChartLabel = namingParams["plotOverlayChartLabel"]
    plotOverlayChart = namingParams["plotOverlayChart"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    metricsToPlotKey = namingParams["metricsToPlot"]
    chosenChart = namingParams["chosenChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    chartDict[plotOverlayChart] = notMetConditionValue
    metricsToPlot = chartDict[metricsToPlotKey]
    if len(metricsToPlot) == 2 and chartDict[chosenChart] in [stackedBarChart]:
        chartDict[plotOverlayChart] = metConditionValue
    elif len(metricsToPlot) == 2 and (
        plotSmallMultiplesKey not in chartDict or not chartDict[plotSmallMultiplesKey]
    ):
        index = 0
        hashKey = get_hashed_key_for_widgets(plotOverlayChart, columnHash)
        helpMessage = "True to plot overlay column chart."
        index = insert_json_value(
            "index", index, automateDict, booleanRadioOptions, plotOverlayChart, None
        )
        chartDict[plotOverlayChart] = ui.radio(
            label=plotOverlayChartLabel,
            options=booleanRadioOptions,
            index=index,
            key=hashKey,
            horizontal=True,
            help=helpMessage,
            label_visibility="visible",
        )
        ui.caption("""✳️True to plot overlay column chart with two metrics.""")
    return chartDict


def get_fix_scales_variance(paramDict, chartDict, automateDict, colArray):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fixedVarianceScaleChoiceLabel = namingParams["fixedVarianceScaleChoiceLabel"]
    fixedVarianceScaleChoice = namingParams["fixedVarianceScaleChoice"]
    varianceName = namingParams["varianceName"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    drilldownAllResults = namingParams["drilldownAllResults"]
    varianceAnalysisChart = namingParams["varianceAnalysisChart"]
    varianceAggregation = namingParams["varianceAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    marginVarianceAggregation = namingParams["marginVarianceAggregation"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 1
    chartDict[fixedVarianceScaleChoice] = notMetConditionValue
    if (
        drilldownAllResults in chartDict
        and chartDict[drilldownAllResults]
        and chartDict[varianceAggregation]
        in [totalVarianceAggregation, marginVarianceAggregation]
    ):
        with colArray[0]:
            hashKey = get_hashed_key_for_widgets(fixedVarianceScaleChoice, columnHash)
            helpMessage = "Fix chart scale across multiple plots."
            index = insert_json_value(
                "index",
                index,
                automateDict,
                booleanRadioOptions,
                fixedVarianceScaleChoice,
                None,
            )
            chartDict[fixedVarianceScaleChoice] = ui.radio(
                label=fixedVarianceScaleChoiceLabel,
                options=booleanRadioOptions,
                index=index,
                key=hashKey,
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption(
                """✳️True to fix chart scale across main & drilldown plots. False to delete fix chart scale value."""
            )
            paramDict = delete_fixed_scale_value(
                chartDict, varianceAnalysisChart, fixedVarianceScaleChoice, paramDict
            )
    return chartDict, paramDict


def get_fix_pareto_scales(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    configParams = get_config_params()
    fixedScaleChoiceLabel = namingParams["fixedParetoScaleChoiceLabel"]
    fixedScaleChoice = namingParams["fixedParetoScaleChoice"]
    columnHash = paramDict[namingParams["columnHash"]]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    metricsToPlot = namingParams["metricsToPlot"]
    showAbsoluteValues = namingParams["showAbsoluteValues"]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    index = 1
    if metricsToPlot in chartDict and len(chartDict[metricsToPlot]) > 1:
        if showAbsoluteValues in chartDict and chartDict[showAbsoluteValues]:
            hashKey = get_hashed_key_for_widgets(fixedScaleChoice, columnHash)
            helpMessage = "Fix chart scale across pareto plots."
            chartDict[fixedScaleChoice] = ui.radio(
                label=fixedScaleChoiceLabel,
                options=booleanRadioOptions,
                index=index,
                key=hashKey,
                horizontal=True,
                label_visibility="visible",
            )
            ui.caption("""✳️Fix chart scale across pareto plots
                                        """)
    return chartDict


def get_period_to_plot(chartDict, automateDict, paramDict):
    namingParams = get_naming_params()
    selectedPeriods = namingParams["selectedPeriods"]
    toPlotPeriod = namingParams["toPlotPeriod"]
    toPlotPeriodsLabel = namingParams["toPlotPeriodsLabel"]
    columnHash = paramDict[namingParams["columnHash"]]
    periodOrder = chartDict[selectedPeriods]
    if len(periodOrder) > 0:
        hashKey = get_hashed_key_for_widgets("toPlotPeriod", columnHash)
        tooltip = """Select the period to plot."""
        message = """✳️Period to plot."""
        index = len(periodOrder) - 1
        index = insert_json_value(
            "index", index, automateDict, periodOrder, toPlotPeriod, None
        )
        chartDict[toPlotPeriod] = ui.selectbox(
            label=toPlotPeriodsLabel,
            options=periodOrder,
            help=tooltip,
            index=index,
            key=hashKey,
            label_visibility="visible",
        )
        ui.caption(message)
    return chartDict


def get_aggregate_dimension(
    df, chosenChart, chartDict, automateDict, indexCols, paramDict
):
    """
    putting together similar widgets
    """
    configParams = get_config_params()
    namingParams = get_naming_params()
    maxSizePlotAllDimensionsDict = configParams["maxSizePlotAllDimensionsDict"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    aggregateUniquesByDimension = namingParams["aggregateUniquesByDimension"]
    aggregateUniquesDimension = namingParams["aggregateUniquesDimension"]
    selectAggregateUniquesDimensionLabel = namingParams[
        "selectAggregateUniquesDimensionLabel"
    ]
    columnHash = paramDict[namingParams["columnHash"]]
    indexColsSelectBox = copy.deepcopy(indexCols)
    message = """✳️Parent dimension to aggregate unique items."""
    tooltip = """Parent dimension to aggregate unique items."""
    if chartDict[aggregateUniquesByDimension]:
        if (
            1 == 1
            or maxSizePlotAllDimensions
            or get_row_count(df) > maxSizePlotAllDimensions
        ):
            hashKey = get_hashed_key_for_widgets(aggregateUniquesDimension, columnHash)
            index = 0
            index = insert_json_value(
                "index",
                index,
                automateDict,
                indexColsSelectBox,
                aggregateUniquesDimension,
                None,
            )
            chartDict[aggregateUniquesDimension] = ui.selectbox(
                label=selectAggregateUniquesDimensionLabel,
                options=indexColsSelectBox,
                help=tooltip,
                index=index,
                key=hashKey,
                label_visibility="visible",
            )
            ui.caption(message)
            chartDict = get_top_items_choice(
                chartDict, automateDict, chosenChart, "X", paramDict
            )
    return chartDict


def get_plot_params(
    chartDict,
    automateDict,
    chosenChart,
    dfDates,
    dfPeriods,
    dfAllPeriods,
    indexCols,
    valueCols,
    paramDict,
):
    """
    get params for charts
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    datashaderLimit = configParams[namingParams["datashaderLimit"]]
    timelineChart = namingParams["timelineChart"]
    slopeChart = namingParams["slopeChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    dotChart = namingParams["dotChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    alternativeCombinationsChart = namingParams["alternativeCombinationsChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    areaChart = namingParams["areaChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    plotSmallMultiplesKey = namingParams["plotSmallMultiplesOtherCharts"]
    selectDimensionsToPlot = namingParams["selectDimensionsToPlot"]
    if chosenChart in [
        upsetChart,
        vennChart,
        stackedColumnChart,
        stackedBarChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        timelineChart,
        slopeChart,
        horizontalWaterfallChart,
        multitierColumnChart,
        multitierBarChart,
    ]:
        chartDict = get_plot_small_multiples_widget(
            chartDict, automateDict, paramDict, chosenChart
        )
    if chosenChart in [stackedColumnChart]:
        chartDict, paramDict = get_fix_scales(chartDict, automateDict, paramDict)
    if chosenChart in [
        areaChart,
        barmekkoChart,
        bubbleChart,
        motionChart,
        dotChart,
        marimekkoChart,
        multitierBarChart,
        scatterChart,
        slopeChart,
        stackedBarChart,
        stackedColumnChart,
        timelineChart,
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        paretoChart,
        stackedParetoChart,
    ]:
        chartDict = get_metric_choice(
            dfPeriods, chosenChart, paramDict, chartDict, automateDict, valueCols
        )
    if chosenChart in [stackedColumnChart, stackedBarChart]:
        chartDict = get_overlay_chart_choice(chartDict, automateDict, paramDict)
        chartDict = get_highlight_overlay_chart(chartDict, automateDict, paramDict)
    if chosenChart in [
        kernelDensity,
        histogramChart,
        boxplotChart,
        ecdfChart,
        stripplotChart,
    ]:
        chartDict = get_other_metrics(
            dfPeriods, chartDict, automateDict, paramDict, valueCols
        )
    if chosenChart in [
        paretoChart,
        stackedParetoChart,
        stackedBarChart,
        marimekkoChart,
        barmekkoChart,
        scatterChart,
        bubbleChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
        upsetChart,
        vennChart,
    ]:
        ascendingIndexCols, indexCols = rank_columns_by_number_of_uniques(
            dfPeriods, indexCols
        )
        chartDict, indexCols = get_small_multiples_dimension_choice(
            dfPeriods, chosenChart, chartDict, automateDict, indexCols, paramDict
        )
    if chosenChart in [paretoChart, stackedParetoChart]:
        indexCols, reverseIndexCols = rank_columns_by_number_of_uniques(
            dfPeriods, indexCols
        )
        chartDict = get_count_unique_items_dimension(
            chartDict, automateDict, paramDict, indexCols, chosenChart
        )
    if chosenChart in [stackedParetoChart]:
        indexCols = get_parents_of_dimension(
            chartDict, chosenChart, indexCols, paramDict, False
        )
        chartDict, indexCols = get_aggregate_by_dimension_choice(
            chartDict, chosenChart, indexCols, automateDict, paramDict
        )
        chartDict = get_aggregate_dimension(
            dfPeriods, chosenChart, chartDict, automateDict, indexCols, paramDict
        )
    if chosenChart in [
        stackedColumnChart,
        multitierBarChart,
        dotChart,
        slopeChart,
        horizontalWaterfallChart,
        multitierColumnChart,
        trendComparisonChart,
        trendComparisonByPeriodChart,
        timelineChart,
        areaChart,
    ]:
        chartDict = get_dimensions_to_plot(
            chartDict, automateDict, chosenChart, indexCols, paramDict
        )
    if chosenChart in [
        trendComparisonByPeriodChart,
        areaChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
        dotChart,
        multitierBarChart,
        multitierColumnChart,
        horizontalWaterfallChart,
        slopeChart,
        stackedColumnChart,
        timelineChart,
        trendComparisonChart,
    ]:
        axisChoice = "X"
        if chosenChart in [multitierBarChart]:
            if plotSmallMultiplesKey in chartDict or chartDict[plotSmallMultiplesKey]:
                if (
                    selectDimensionsToPlot in chartDict
                    and len(chartDict[selectDimensionsToPlot]) == 1
                ):
                    axisChoice = "Y"
        chartDict = get_top_items_choice(
            chartDict, automateDict, chosenChart, axisChoice, paramDict
        )
    if chosenChart in [
        marimekkoChart,
        barmekkoChart,
        vennChart,
        upsetChart,
        stackedBarChart,
        bubbleChart,
        scatterChart,
        motionChart,
        kernelDensity,
        histogramChart,
        boxplotChart,
        stripplotChart,
        ecdfChart,
        multitierBarChart,
    ]:
        chartDict = get_x_and_y_dimensions_choice(
            dfPeriods, chartDict, automateDict, indexCols, chosenChart, paramDict
        )
    if chosenChart in [
        scatterChart,
        bubbleChart,
        upsetChart,
        vennChart,
        stackedBarChart,
        marimekkoChart,
        barmekkoChart,
        paretoChart,
        stackedParetoChart,
    ]:
        chartDict = get_period_to_plot(chartDict, automateDict, paramDict)
    if chosenChart in [stackedParetoChart]:
        chartDict = get_stacked_pareto_parameters(
            chartDict, automateDict, paramDict, chosenChart, dfPeriods, indexCols
        )
    if chosenChart in [upsetChart]:
        chartDict = get_catplot_choice(
            dfPeriods, chartDict, automateDict, valueCols, chosenChart, paramDict
        )
    if chosenChart in [stackedBarChart]:
        chartDict = get_show_average_value(chartDict, automateDict, paramDict)
    if chosenChart in [barmekkoChart]:
        chartDict = get_sorting_axis(chartDict, automateDict, paramDict)
    if chosenChart in [trendComparisonChart]:
        chartDict = get_plot_as_baseline_chart_widget(
            chartDict, automateDict, paramDict, chosenChart
        )
    if chosenChart in [
        areaChart,
        bubbleChart,
        motionChart,
        dotChart,
        slopeChart,
        stackedColumnChart,
        stackedBarChart,
    ]:
        chartDict = get_plot_values_as_choice(
            chartDict, automateDict, paramDict, chosenChart
        )
    if chosenChart in [paretoChart]:
        chartDict = get_rank_label_choice(dfPeriods, chartDict, automateDict, paramDict)
    if chosenChart in [paretoChart]:
        chartDict = get_fix_pareto_scales(chartDict, automateDict, paramDict)
    if chosenChart in [marimekkoChart]:
        chartDict = get_show_value_labels_as_choice(
            chartDict, automateDict, paramDict, chosenChart
        )
    if chosenChart in [
        stackedColumnChart,
        stackedBarChart,
        stackedParetoChart,
        marimekkoChart,
    ]:
        chartDict = get_show_label_choice(
            dfAllPeriods, chosenChart, chartDict, automateDict, paramDict
        )
    if chosenChart in [stackedColumnChart]:
        chartDict = get_show_CAGR_choice(
            dfAllPeriods, chosenChart, chartDict, automateDict, paramDict
        )
    if chosenChart in [boxplotChart]:
        chartDict = get_show_outliers(chartDict, automateDict, paramDict)
    if chosenChart in [bubbleChart]:
        chartDict = get_adjust_bubble_label_position(chartDict, automateDict, paramDict)
    if chosenChart in [scatterChart]:
        chartDict = get_show_scatter_labels(chartDict, automateDict, paramDict)
        chartDict = get_log_Y_axis(chartDict, automateDict, paramDict)
    if chosenChart in [
        boxplotChart,
        kernelDensity,
        histogramChart,
        stripplotChart,
        ecdfChart,
        scatterChart,
    ]:
        chartDict = get_log_X_axis(chartDict, automateDict, paramDict)
    if chosenChart in [areaChart, motionChart, timelineChart, trendComparisonChart]:
        chartDict = get_date_resampling_choice(
            chartDict, automateDict, chosenChart, paramDict
        )
    if chosenChart in [kernelDensity, scatterChart, histogramChart]:
        chartDict = get_exclude_outlier_choice_for_charts(
            chosenChart, chartDict, automateDict, paramDict
        )
    if chosenChart in [histogramChart]:
        chartDict = get_plot_cumulative_histogram_choice(
            chartDict, automateDict, paramDict
        )
    if chosenChart in [ecdfChart]:
        chartDict = get_plot_reversed_ecdf_choice(chartDict, automateDict, paramDict)
    if chosenChart in [scatterChart]:
        chartDict = get_datashader_choice(
            dfPeriods, chartDict, automateDict, chosenChart, paramDict
        )
        chartDict = get_isoline_choice(chartDict, automateDict, chosenChart, paramDict)
        chartDict = set_up_label_position_widget(
            chartDict, automateDict, chosenChart, paramDict
        )
        chartDict = get_trendline_choice(
            dfPeriods, chartDict, automateDict, chosenChart, paramDict
        )
    if chosenChart in [bubbleChart]:
        chartDict = set_up_start_axes_from_zero_widget(
            chartDict, automateDict, paramDict
        )
        chartDict = set_up_add_total_bubble_widget(chartDict, automateDict, paramDict)
    if chosenChart in [motionChart]:
        chartDict = set_up_label_content_widget(
            chartDict, automateDict, chosenChart, paramDict
        )
    if chosenChart in [
        timelineChart,
        slopeChart,
        areaChart,
        stackedColumnChart,
        stackedParetoChart,
    ]:
        chartDict = set_up_label_position_widget(
            chartDict, automateDict, chosenChart, paramDict
        )
    if chosenChart in [
        stackedColumnChart,
        marimekkoChart,
        stackedBarChart,
        slopeChart,
        timelineChart,
        areaChart,
        bubbleChart,
        motionChart,
        scatterChart,
        stackedParetoChart,
        vennChart,
        upsetChart,
    ]:
        chartDict = get_highlighted_items(
            dfAllPeriods,
            dfPeriods,
            valueCols,
            chosenChart,
            chartDict,
            automateDict,
            paramDict,
        )
    return chartDict


def get_chart_widgets(
    dfDict,
    indexCols,
    valueCols,
    paramDict,
    runOneDimensionalAnalysis,
    colArray,
    chartDict,
    automateDict,
):
    """
    showing charging widgets
    """
    namingParams = get_naming_params()
    configParams = get_config_params()
    emojiNumberDict = configParams[namingParams["emojiNumberDict"]]
    choosePlotLabel = namingParams["choosePlotLabel"]
    chooseRowToPlotLabel = namingParams["chooseRowToPlotLabel"]
    plotOriginalDataLabel = namingParams["plotOriginalDataLabel"]
    prepareFileForDownloadLabel = namingParams["prepareFileForDownloadLabel"]
    prepareFileForDownload = namingParams["prepareFileForDownload"]
    plotOriginalData = namingParams["plotOriginalData"]
    dotChart = namingParams["dotChart"]
    timelineChart = namingParams["timelineChart"]
    stackedColumnChart = namingParams["stackedColumnChart"]
    stackedBarChart = namingParams["stackedBarChart"]
    multitierBarChart = namingParams["multitierBarChart"]
    multitierColumnChart = namingParams["multitierColumnChart"]
    horizontalWaterfallChart = namingParams["horizontalWaterfallChart"]
    areaChart = namingParams["areaChart"]
    paretoChart = namingParams["paretoChart"]
    stackedParetoChart = namingParams["stackedParetoChart"]
    vennChart = namingParams["vennChart"]
    upsetChart = namingParams["upsetChart"]
    slopeChart = namingParams["slopeChart"]
    kernelDensity = namingParams["kernelDensityChart"]
    histogramChart = namingParams["histogramChart"]
    boxplotChart = namingParams["boxplotChart"]
    stripplotChart = namingParams["stripplotChart"]
    ecdfChart = namingParams["ecdfChart"]
    bubbleChart = namingParams["bubbleChart"]
    motionChart = namingParams["motionChart"]
    scatterChart = namingParams["scatterChart"]
    marimekkoChart = namingParams["marimekkoChart"]
    barmekkoChart = namingParams["barmekkoChart"]
    trendComparisonChart = namingParams["trendComparisonChart"]
    trendComparisonByPeriodChart = namingParams["trendComparisonByPeriodChart"]
    alternativeCombinationsChart = namingParams["alternativeCombinationsChart"]
    numberOfRowResults = namingParams["numberOfRowResults"]
    rowName = namingParams["rowName"]
    dfDatesName = namingParams["dfDatesName"]
    dfPeriodsName = namingParams["dfPeriodsName"]
    dfAllPeriodsName = namingParams["dfAllPeriodsName"]
    doNotPlotName = namingParams["doNotPlotName"]
    entireDatasetName = namingParams["entireDatasetName"]
    chosenChart = namingParams["chosenChart"]
    rowToPlot = namingParams["rowToPlotName"]
    varianceAggregation = namingParams["varianceAggregation"]
    totalVarianceAggregation = namingParams["totalVarianceAggregation"]
    metConditionValue = namingParams["metConditionValue"]
    notMetConditionValue = namingParams["notMetConditionValue"]
    mainReportRunName = namingParams["mainReportRunName"]
    drillDownDatasetNumber = namingParams["drillDownDatasetNumber"]
    drillDownRowToPlotLabel = namingParams["drillDownRowToPlotLabel"]
    mainDimension = namingParams["mainDimension"]
    companyName = namingParams["companyName"]
    currencyChoice = namingParams["currencyChoice"]
    filterDictName = namingParams["filterDictName"]
    colorChoice = namingParams["colorChoice"]
    submitPlotLabel = namingParams["submitPlotLabel"]
    loopParamsDictName = namingParams["loopParamsDictName"]
    processingChoiceKey = namingParams["processingChoice"]
    drilldownParamsDictName = namingParams["drilldownParamsDictName"]
    noVarianceAnalysis = namingParams["noVarianceAnalysis"]
    processingChoice = chartDict[processingChoiceKey]
    columnHash = paramDict[namingParams["columnHash"]]
    booleanRadioOptions = [metConditionValue, notMetConditionValue]
    if (
        loopParamsDictName in chartDict
        and numberOfRowResults in chartDict[loopParamsDictName]
    ):
        numberOfRowResults = chartDict[loopParamsDictName][numberOfRowResults]
    else:
        numberOfRowResults = 20
    if drilldownParamsDictName in chartDict:
        drilldownParamsDict = chartDict[drilldownParamsDictName]
    else:
        drilldownParamsDict = {}
    dfDates, dfPeriods, dfAllPeriods = (
        dfDict[dfDatesName],
        dfDict[dfPeriodsName],
        dfDict[dfAllPeriodsName],
    )
    # Only present dimensions should be displayed to the user.
    # Use the main dataframe to mirror the filter widget behaviour.
    try:
        dfName = namingParams["dfName"]
        dfMain = dfDict.get(dfName, dfAllPeriods)
        cols_main, schema_main = get_schema_and_column_names(dfMain)
        # Offer all text-like columns from the joined main dataframe
        offered = [
            c for c in cols_main if schema_main.get(c) in (pl.Utf8, pl.Categorical)
        ]
        last_logged = session_state.get("_plot_dims_logged")
        current_key = (tuple(cols_main), tuple(offered))
        if last_logged != current_key:
            # Reduce verbosity: only emit at DEBUG and suppress UI writes
            logger.debug("plot-dims: main_cols=%s, offered=%s", cols_main, offered)
            if logger.isEnabledFor(logging.DEBUG):
                try:
                    ui.write("🔎 Plot debug – dataframe columns:", cols_main)
                    ui.write(
                        "🔎 Plot debug – text columns offered to widgets:", offered
                    )
                except Exception:
                    logger.exception("Failed to emit plot debug columns")
            session_state["_plot_dims_logged"] = current_key
        valid_indexCols = offered
        # Persist the offered dimensions so the prep layer preserves them
        try:
            session_state["plot_forced_dims"] = list(valid_indexCols)
        except Exception:
            pass
    except Exception as e:
        logging.getLogger(__name__).exception("plot-dims: validation failed: %s", e)
        valid_indexCols = indexCols
    rowResultArray = []
    for element in range(numberOfRowResults):
        if element + 1 in emojiNumberDict:
            rowEmoji = emojiNumberDict[element + 1].strip()
            rowEmoji = rowName + rowEmoji
            rowResultArray.append(rowEmoji)
    with colArray[0]:
        if mainDimension in chartDict and len(chartDict[mainDimension]) > 0:
            rowToPlotArray = [doNotPlotName, entireDatasetName] + rowResultArray
        elif not runOneDimensionalAnalysis:
            rowToPlotArray = [doNotPlotName, entireDatasetName] + rowResultArray
        else:
            rowToPlotArray = [doNotPlotName, entireDatasetName]
        tooltip = """Choose whether you want to plot the entire dataset or if you want the app to filter the
      data corresponding to a specific report row result, and plot it.
      """
        if processingChoice == noVarianceAnalysis:
            chartDict[rowToPlot] = entireDatasetName
        else:
            choice = 0
            choice = insert_json_value(
                "index", choice, automateDict, rowToPlotArray, rowToPlot, None
            )
            chartDict[rowToPlot] = selectbox_with_state(
                rowToPlot,
                columnHash,
                label=chooseRowToPlotLabel,
                options=rowToPlotArray,
                index=choice,
                help=tooltip,
                label_visibility="visible",
            )
            message = """✳️Data to plot. You can plot the entire dataset, or  
          plot the data corresponding to a specific row of the report. If you have drilled down one or more rows of
          the main report, you can also plot the data of a specific row of a drilldown report."""
            if runOneDimensionalAnalysis:
                message = """✳️Data to plot. You can plot the entire dataset, or you 
                plot the data corresponding to a specific row of the variance report."""
            ui.caption(message)
            if (
                chartDict[rowToPlot] != doNotPlotName
                and chartDict[rowToPlot] != entireDatasetName
            ):
                if not runOneDimensionalAnalysis:
                    chartDict[plotOriginalData] = radio_with_state(
                        plotOriginalData,
                        columnHash,
                        label=plotOriginalDataLabel,
                        options=booleanRadioOptions,
                        index=1,
                        horizontal=True,
                        label_visibility="visible",
                    )
                    ui.caption(
                        """✳️If you choose to filter just the data corresponding to a specific report row,
                               you can choose whether to plot the original value of that combination or the value
                               of that combination after the rows before that combination have been filtered out."""
                    )
                    reportDict, drillDownRowsArray = list_drilldown_rows(
                        drilldownParamsDict
                    )
                    if len(reportDict) > 1:
                        drillDownRow = selectbox_with_state(
                            "drillDownRowToPlot",
                            columnHash,
                            label=drillDownRowToPlotLabel,
                            options=drillDownRowsArray,
                            index=0,
                            label_visibility="visible",
                        )
                        drillDownDataset = reportDict[drillDownRow]
                        chartDict[drillDownDatasetNumber] = drillDownDataset
                        ui.caption(
                            """✳️If you want to plot the values of a drilldown row, select the drilldown row. Otherwise leave
                                    "Main Report" selected"""
                        )
                    chartDict[prepareFileForDownload] = radio_with_state(
                        prepareFileForDownload,
                        columnHash,
                        label=prepareFileForDownloadLabel,
                        options=booleanRadioOptions,
                        index=1,
                        horizontal=True,
                        label_visibility="visible",
                    )
                    ui.caption(
                        """✳️If True, the system will prepare a parquet file (CSV optional) for download with the data used for plotting.
                              This might take a while."""
                    )
        if chartDict[rowToPlot] != doNotPlotName:
            with colArray[1]:
                chartArray = make_available_plots_list(
                    dfPeriods, dfDates, paramDict, chartDict
                )
                tooltip = """Choose the plot you want to see. Click Plot to apply settings and render the chart."""
                index = 0
                index = insert_json_value(
                    "index", index, automateDict, chartArray, chosenChart, None
                )
                selectedChart = selectbox_with_state(
                    "choosePlot",
                    columnHash,
                    label=choosePlotLabel,
                    options=chartArray,
                    index=index,
                    help=tooltip,
                    label_visibility="visible",
                )
                previousChart = session_state.get("_prev_chosen_chart")
                chart_changed = (
                    previousChart is not None and previousChart != selectedChart
                )
                session_state["_prev_chosen_chart"] = selectedChart
                chartDict[chosenChart] = selectedChart
                if chart_changed:
                    try:
                        chartNotChanged = namingParams["chartDictNotChangedName"]
                        session_state[chartNotChanged] = False
                    except Exception:
                        pass
                apply_clicked = False
                with ui.form("chart_params"):
                    if chosenChart in chartDict and chartDict[chosenChart] in [
                        trendComparisonByPeriodChart,
                        alternativeCombinationsChart,
                        areaChart,
                        barmekkoChart,
                        bubbleChart,
                        motionChart,
                        kernelDensity,
                        histogramChart,
                        boxplotChart,
                        stripplotChart,
                        ecdfChart,
                        dotChart,
                        marimekkoChart,
                        multitierBarChart,
                        multitierColumnChart,
                        horizontalWaterfallChart,
                        scatterChart,
                        slopeChart,
                        stackedColumnChart,
                        stackedBarChart,
                        vennChart,
                        upsetChart,
                        timelineChart,
                        paretoChart,
                        stackedParetoChart,
                        trendComparisonChart,
                    ]:
                        explain_chart(chartDict, paramDict)
                        colExpander2 = ui.expander("➕ Plot options")
                        with colExpander2:
                            chartDict = get_plot_params(
                                chartDict,
                                automateDict,
                                chartDict[chosenChart],
                                dfDates,
                                dfPeriods,
                                dfAllPeriods,
                                valid_indexCols,
                                valueCols,
                                paramDict,
                            )
                    apply_clicked = ui.form_submit_button("Plot")
                if apply_clicked:
                    paramDict = prepare_chart_images(chartDict, colArray, paramDict)
                    # Trigger plotting immediately after applying settings
                    try:
                        submitPlotName = namingParams["submitPlotName"]
                        chartNotChanged = namingParams["chartDictNotChangedName"]
                        session_state[submitPlotName] = True
                        session_state[chartNotChanged] = True
                        session_state["chart_apply_plot"] = True
                    except Exception:
                        session_state["chart_apply_plot"] = True
    return chartDict, paramDict
