"""UI widgets used for dataset filtering."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

import polars as pl

try:
    from polars.selectors import NUMERIC_DTYPES
except (ImportError, AttributeError):  # pragma: no cover - fallback for older Polars
    from polars import NUMERIC_DTYPES  # type: ignore[attr-defined]
from modules.layout.core.ui_adapter import ui
from modules.utilities.session_context import session_state

from modules.layout.memoization import get_hashed_key
from modules.layout.set_up_widgets import make_slider_for_filter
from modules.layout.widgets import searchable_selectbox_with_state
from modules.utilities.config import get_naming_params
from modules.utilities.helpers import (
    insert_json_value,
    take_filtered_value_out_of_option_list,
)
from modules.utilities.utils import get_schema_and_column_names


def get_items_to_filter(
    df: pl.DataFrame | pl.LazyFrame,
    index_cols: List[str],
    param_dict: Dict[str, Any],
    filter_dict: Dict[str, Dict[str, List[str]]],
    number_filter_dict: Dict[str, Dict[str, Any]],
    number: int,
    col_array: List[Any],
    automate_dict: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, Dict[str, Any]], bool, List[str]]:
    """Return filter selections for a specific column.

    Parameters
    ----------
    df : DataFrame or LazyFrame
        Dataset used to determine slider ranges.
    index_cols : list[str]
        Candidate columns for filtering.
    param_dict : dict
        Application parameters and session data.
    filter_dict : dict
        Dictionary of include/exclude selections.
    number_filter_dict : dict
        Numeric range selections.
    number : int
        Filter widget number (1–4).
    col_array : list[Any]
        UI column objects for layout.
    automate_dict : dict
        Automation parameters loaded from JSON.
    """

    naming = get_naming_params()
    choose_column_label = naming["chooseFilterColumnLabel"]
    choose_to_include_items_label = naming["chooseToIncludeItemsLabel"]
    choose_to_exclude_items_label = naming["chooseToExcludeItemsLabel"]
    nothing_filtered_name = naming["nothingFilteredName"]
    to_include_items = naming["toIncludeItems"]
    to_exclude_items = naming["toExcludeItems"]
    top_word_dict_key = naming["topWordDict"]
    filter_dict_name = naming["filterDictName"]
    number_filter_dict_name = naming["numberFilterDictName"]
    choose_column_label = f"{choose_column_label} #{number}"
    column_hash = param_dict[naming["columnHash"]]
    top_word_dict = param_dict[top_word_dict_key]

    excel_columns: list[str] = session_state.get("attr_excel_columns", []) or []
    excel_column_values: dict[str, list[str]] = session_state.get(
        "attr_excel_column_values", {}
    )
    if excel_columns:
        columns_in_df, _ = get_schema_and_column_names(df)
        available = set(index_cols)
        for col in excel_columns:
            if col in columns_in_df and col not in available:
                index_cols.append(col)
                available.add(col)
        for col in excel_columns:
            if col in columns_in_df:
                values = excel_column_values.get(col, [])
                if values:
                    top_word_dict[col] = values
    param_dict[top_word_dict_key] = top_word_dict

    with col_array[0]:
        tooltip = "Select a column you want to filter on."
        hash_key = get_hashed_key(f"filterColumn{number}", column_hash)
        index = insert_json_value(
            "index",
            0,
            automate_dict,
            index_cols,
            filter_dict_name,
            number,
        )
        filter_column = searchable_selectbox_with_state(
            choose_column_label,
            index_cols,
            key=hash_key,
            index=index,
            help=tooltip,
            disabled=False,
            label_visibility="visible",
        )
        if filter_column not in index_cols:
            filter_column = nothing_filtered_name
        ui.caption(
            "\u2733\ufe0fFilter the items to keep and the items to exclude (4 filters max)."
        )

    to_filter = False
    if filter_column != nothing_filtered_name:
        filtered_index_cols = take_filtered_value_out_of_option_list(
            index_cols, filter_column
        )
        filter_dict[filter_column] = {}
        filter_items = top_word_dict[filter_column]
        to_exclude_items_list = copy.deepcopy(filter_items)
        columns, schema = get_schema_and_column_names(df)
        is_numeric_dtype = schema.get(filter_column) in NUMERIC_DTYPES
        is_number_column = False
        is_numeric_filter = False
        with col_array[1]:
            tooltip = "Select the items you want to include in the analysis."
            hash_key = get_hashed_key(f"{to_include_items}{number}", column_hash)
            validated_include: List[str] = []
            min_max_values = insert_json_value(
                f"{to_include_items}Slider",
                [],
                automate_dict,
                None,
                number_filter_dict_name,
                number,
            )
            filter_values = None
            if is_numeric_dtype:
                is_numeric_filter, is_number_column, filter_values = (
                    make_slider_for_filter(
                        df,
                        filter_column,
                        is_numeric_filter,
                        is_number_column,
                        tooltip,
                        hash_key,
                        "include",
                        min_max_values,
                    )
                )
            number_filter_dict[filter_column] = {}
            if filter_values:
                number_filter_dict[filter_column][to_include_items] = filter_values
            if not is_number_column:
                value = insert_json_value(
                    to_include_items,
                    None,
                    automate_dict,
                    filter_items,
                    filter_dict_name,
                    number,
                )
                include_array = ui.multiselect(
                    label=choose_to_include_items_label,
                    options=filter_items,
                    help=tooltip,
                    key=hash_key,
                    max_selections=None,
                    default=value,
                    label_visibility="visible",
                )
                validated_include = [
                    element for element in include_array if element in filter_items
                ]
                ui.caption(
                    "\u2733\ufe0fSelect the items you want to include in the analysis."
                )
                filter_dict[filter_column][to_include_items] = validated_include
            if len(validated_include) > 0:
                for element in validated_include:
                    if element in to_exclude_items_list:
                        to_exclude_items_list = take_filtered_value_out_of_option_list(
                            to_exclude_items_list, element
                        )
        with col_array[2]:
            tooltip = "Select the items you want to exclude ❌ from the analysis."
            hash_key = get_hashed_key(f"{to_exclude_items}{number}", column_hash)
            validated_exclude: List[str] = []
            min_max_values = insert_json_value(
                f"{to_exclude_items}Slider",
                [],
                automate_dict,
                None,
                number_filter_dict_name,
                number,
            )
            filter_values = None
            if is_numeric_dtype:
                is_numeric_filter, is_number_column, filter_values = (
                    make_slider_for_filter(
                        df,
                        filter_column,
                        is_numeric_filter,
                        is_number_column,
                        tooltip,
                        hash_key,
                        "exclude",
                        min_max_values,
                    )
                )
            if filter_values:
                number_filter_dict[filter_column][to_exclude_items] = filter_values
            if not is_number_column:
                value = insert_json_value(
                    to_exclude_items,
                    None,
                    automate_dict,
                    to_exclude_items_list,
                    filter_dict_name,
                    number,
                )
                exclude_array = ui.multiselect(
                    label=choose_to_exclude_items_label,
                    options=to_exclude_items_list,
                    help=tooltip,
                    key=hash_key,
                    max_selections=None,
                    default=value,
                    label_visibility="visible",
                )
                validated_exclude = [
                    element for element in exclude_array if element in filter_items
                ]
                ui.caption(
                    "\u2733\ufe0fSelect the items you want to exclude ❌ from the analysis."
                )
                filter_dict[filter_column][to_exclude_items] = validated_exclude
        if validated_include or validated_exclude or is_numeric_filter:
            to_filter = True
    else:
        validated_include = []
        include_array = []
        validated_exclude = []
        to_exclude_items_list = []
        filtered_index_cols = copy.deepcopy(index_cols)
    if not to_filter:
        filter_dict.pop(filter_column, None)
    return filter_dict, number_filter_dict, to_filter, filtered_index_cols


def make_filter_dict(
    df: pl.DataFrame | pl.LazyFrame,
    index_cols: List[str],
    param_dict: Dict[str, Any],
    chart_dict: Dict[str, Any],
    automate_dict: Dict[str, Any],
    col_array: List[Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Create UI widgets to build filtering dictionaries."""

    naming = get_naming_params()
    nothing_filtered_name = naming["nothingFilteredName"]
    filter_dict_name = naming["filterDictName"]
    number_filter_dict_name = naming["numberFilterDictName"]
    processing_choice = naming["processingChoice"]
    correct_period_aggregation = naming["correctPeriodAggregation"]
    period_name = naming["periodName"]
    prepare_filtered_key = naming["prepareFilteredFileForDownload"]
    prepare_filtered_label = naming["prepareFilteredFileForDownloadLabel"]
    not_met = naming["notMetConditionValue"]
    met = naming["metConditionValue"]
    is_filtered_key = naming["isFilteredKey"]
    param_dict[is_filtered_key] = not_met
    boolean_options = [met, not_met]

    filter_dict: Dict[str, Dict[str, List[str]]] = {}
    number_filter_dict: Dict[str, Dict[str, Any]] = {}

    if param_dict.get(correct_period_aggregation) or True:
        if index_cols and processing_choice in chart_dict:
            index_cols_select_box = copy.deepcopy(index_cols)
            if period_name in index_cols_select_box:
                index_cols_select_box.remove(period_name)
            index_cols_select_box.insert(0, nothing_filtered_name)
            number = 1
            filter_dict, number_filter_dict, to_filter, index_cols_select_box = (
                get_items_to_filter(
                    df,
                    index_cols_select_box,
                    param_dict,
                    filter_dict,
                    number_filter_dict,
                    number,
                    col_array,
                    automate_dict,
                )
            )
            if to_filter and number == 1:
                number = 2
                filter_dict, number_filter_dict, to_filter, index_cols_select_box = (
                    get_items_to_filter(
                        df,
                        index_cols_select_box,
                        param_dict,
                        filter_dict,
                        number_filter_dict,
                        number,
                        col_array,
                        automate_dict,
                    )
                )
            if to_filter and number == 2:
                number = 3
                filter_dict, number_filter_dict, to_filter, index_cols_select_box = (
                    get_items_to_filter(
                        df,
                        index_cols_select_box,
                        param_dict,
                        filter_dict,
                        number_filter_dict,
                        number,
                        col_array,
                        automate_dict,
                    )
                )
            if to_filter and number == 3:
                number = 4
                filter_dict, number_filter_dict, to_filter, index_cols_select_box = (
                    get_items_to_filter(
                        df,
                        index_cols_select_box,
                        param_dict,
                        filter_dict,
                        number_filter_dict,
                        number,
                        col_array,
                        automate_dict,
                    )
                )
            if filter_dict or number_filter_dict:
                with col_array[3]:
                    param_dict[prepare_filtered_key] = ui.radio(
                        label=prepare_filtered_label,
                        options=boolean_options,
                        index=1,
                        key="prepareFilteredFileForDownload",
                        horizontal=True,
                        label_visibility="visible",
                    )
                    ui.caption(
                        "\u2733\ufe0fif True, the system will prepare a parquet file (CSV optional) to download the filtered dataset. This might take a while."
                    )
    chart_dict[filter_dict_name] = filter_dict
    chart_dict[number_filter_dict_name] = number_filter_dict
    if filter_dict:
        param_dict[is_filtered_key] = met
    return param_dict, chart_dict
