"""UI helpers used by data widgets.

This module belongs to the UI layer and may display warnings or
errors when invoked by the data-processing logic.
"""

import logging
from typing import Tuple

import polars as pl
from modules.layout.core.ui_adapter import ui

from modules.layout.memoization import (
    check_collect,
    get_hashed_key,
)
from modules.utilities.config import get_naming_params
from modules.utilities.error_messages import add_error_message_in_load_data_tab
from modules.utilities.helpers import insert_json_value


def count_periods(
    df: pl.LazyFrame | pl.DataFrame, chart_dict: dict, param_dict: dict
) -> Tuple[int, dict]:
    """Return number of periods found in ``df``.

    Parameters
    ----------
    df : LazyFrame or DataFrame
        Dataset containing period or date columns.
    chart_dict : dict
        Dictionary holding widget state, used to determine aggregation choice.
    param_dict : dict
        Parameter dictionary with column detection flags.
    """
    naming = get_naming_params()
    date_col_found = naming["dateColFound"]
    period_col_found = naming["periodColFound"]
    period_name = naming["periodName"]
    date_name = naming["dateName"]
    year_name = naming["yearName"]
    month_name = naming["monthName"]
    quarter_name = naming["quarterName"]
    period_choice = naming["periodChoice"]
    impossible = naming["impossibleToProcessFile"]
    met_val = naming["metConditionValue"]

    number_of_periods = 1
    if param_dict.get(date_col_found) and not param_dict.get(period_col_found):
        period = chart_dict[period_choice]
        if period == year_name:
            try:
                number_of_periods = (
                    df.select(pl.col(date_name).dt.year())
                    .filter(pl.col(date_name).is_not_null())
                    .unique()
                    .collect()
                    .height
                )
                check_collect("AAAA", "numberOfPeriods", number_of_periods)
            except Exception as e:
                logging.exception(e)
                ui.error(
                    "Something went wrong while determining the number of periods."
                )
                param_dict[impossible] = met_val
                message = "Check date column format."
                number_of_periods = 1
                param_dict = add_error_message_in_load_data_tab(param_dict, message)
        elif period == quarter_name:
            number_of_periods = 5
        else:
            number_of_periods = 14
    elif param_dict.get(period_col_found):
        if chart_dict[period_choice] == month_name:
            number_of_periods = 14
        elif chart_dict[period_choice] == quarter_name:
            number_of_periods = 5
        else:
            number_of_periods = (
                df.select(pl.col(period_name))
                .filter(pl.col(period_name).is_not_null())
                .unique()
                .collect()
                .height
            )
            check_collect("AAB", "numberOfPeriods", number_of_periods)
    else:
        message = "Unable to find period or date column"
        param_dict = add_error_message_in_load_data_tab(param_dict, message)
        param_dict[impossible] = met_val
    return number_of_periods, param_dict


def select_index_columns_to_drop(
    index_cols: list[str],
    period_name: str,
    column_hash: int,
    automate_dict: dict,
    select_all_label: str,
    multiselect_label: str,
    choose_key: str,
    processing_choice: str,
    run_variable_dimensional: str,
    col,
) -> list[str]:
    """Return columns selected for deletion via UI widgets."""

    index_cols_select = [c for c in index_cols if c != period_name]
    with col:
        container = ui.container()
        choice_key = f"{choose_key}Checkbox"
        hash_key = get_hashed_key(choice_key, column_hash)
        default_value = insert_json_value(
            "checkbox", False, automate_dict, None, choice_key, None
        )
        choose_all = ui.checkbox(
            label=select_all_label,
            value=default_value,
            key=hash_key,
            label_visibility="visible",
        )
        hash_delete = get_hashed_key("deleteIndexColsArray", column_hash)
        tooltip = "Select one or more columns that you do want to drop."
        if choose_all:
            value = insert_json_value(
                "array",
                index_cols_select,
                automate_dict,
                index_cols_select,
                choose_key,
                None,
            )
            selected = container.multiselect(
                multiselect_label,
                index_cols_select,
                help=tooltip,
                default=index_cols_select[1:],
                key=hash_delete,
                max_selections=None,
            )
        else:
            value = insert_json_value(
                "array", [], automate_dict, index_cols_select, choose_key, None
            )
            selected = container.multiselect(
                multiselect_label,
                index_cols_select,
                help=tooltip,
                default=value,
                key=hash_delete,
                max_selections=None,
            )
        if processing_choice == run_variable_dimensional:
            message = "✳️Drop columns from dataset to exclude ❌ non relevant dimensions and/or to improve perfomance."
        else:
            message = "✳️Variance is calculated botton up, combination by combination. Exclude non relevant combinations from the calculation."
        ui.caption(message)
    return list(selected)


def warn_high_memory_usage(percent: float) -> None:
    """Display a memory usage warning."""

    ui.warning(
        f"⚠️ High memory usage ({percent}%). Filtering suggestions are disabled. Please type filter terms manually."
    )


def report_filter_column_error(column: str, exc: Exception) -> None:
    """Display an error while processing a column."""

    ui.error(f"⚠️ Error processing column {column}: {exc}")
