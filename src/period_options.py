from __future__ import annotations

"""Logic for building time period selection options."""

import logging

import polars as pl
from modules.utilities.ui_notifier import ui

from modules.utilities.config import get_naming_params


def get_time_period_layout() -> tuple[list[int], list[int]]:
    """Return layout configuration for the time period tab."""

    col_widths = [1, 1, 1, 1]
    expander_order = [1, 2, 3, 4]
    return col_widths, expander_order


__all__ = [
    "determine_most_recent_period_options",
    "get_time_period_layout",
]


def _count_periods(
    df: pl.LazyFrame | pl.DataFrame, chart_dict: dict, param_dict: dict
) -> tuple[int, dict]:
    """Return number of periods available without depending on UI."""
    naming = get_naming_params()
    date_found = naming["dateColFound"]
    period_found = naming["periodColFound"]
    period_name = naming["periodName"]
    date_name = naming["dateName"]
    year_name = naming["yearName"]
    month_name = naming["monthName"]
    quarter_name = naming["quarterName"]
    choice_key = naming["periodChoice"]

    number = 1
    if param_dict.get(date_found) and not param_dict.get(period_found):
        period = chart_dict.get(choice_key)
        if period == year_name:
            try:
                number = (
                    df.select(pl.col(date_name).dt.year())
                    .filter(pl.col(date_name).is_not_null())
                    .unique()
                    .collect()
                    .height
                )
            except Exception as e:  # pragma: no cover - defensive
                logging.exception(e)
                ui.error("Something went wrong while counting periods.")
                number = 1
        elif period == quarter_name:
            number = 5
        else:
            number = 14
    elif param_dict.get(period_found):
        if chart_dict.get(choice_key) == month_name:
            number = 14
        elif chart_dict.get(choice_key) == quarter_name:
            number = 5
        else:
            number = (
                df.select(pl.col(period_name))
                .filter(pl.col(period_name).is_not_null())
                .unique()
                .collect()
                .height
            )
    return number, param_dict


def determine_most_recent_period_options(
    df: pl.DataFrame | pl.LazyFrame,
    param_dict: dict,
    chart_dict: dict,
) -> tuple[list[str], dict[str, int], int, bool, dict]:
    """Return slider options for selecting the most recent period."""
    number_of_periods, param_dict = _count_periods(df, chart_dict, param_dict)

    naming = get_naming_params()
    period_to_date = naming["periodToDate"]
    compare_key = naming["compareWithYearBefore"]
    filter_dates = naming["filterDates"]

    if param_dict.get(naming["impossibleToProcessFile"], False):
        return [], {}, -1, False, param_dict

    base_choices = [
        "n-13",
        "n-12",
        "n-11",
        "n-10",
        "n-9",
        "n-8",
        "n-7",
        "n-6",
        "n-5",
        "n-4",
        "n-3",
        "n-2",
        "n-1",
        "n",
    ]
    mapping = {label: -14 + idx for idx, label in enumerate(base_choices)}

    num_choices = number_of_periods - 1
    options = base_choices[-num_choices:]
    default_index = min(num_choices - 1, len(options) - 1)

    show = True
    if chart_dict.get(period_to_date) and not chart_dict.get(compare_key, True):
        show = False

    if chart_dict.get(filter_dates):
        mapping = {}
        default_index = -1
        show = False

    options_mapping = {label: mapping[label] for label in options if label in mapping}
    return options, options_mapping, default_index, show, param_dict
