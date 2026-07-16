from __future__ import annotations

"""Helpers for computing rolling and period-to-date aggregations using Polars."""


import copy
import datetime as dt
import logging
from typing import Any, MutableMapping

import polars as pl
from modules.utilities.ui_notifier import ui
from dateutil.relativedelta import relativedelta

from modules.layout.memoization import check_collect
from modules.utilities.config import get_config_params, get_naming_params
from modules.utilities.error_messages import (
    add_app_message_to_paramdict,
    add_warning_message_in_period_options_tab,
)
from modules.utilities.session_context import SessionContext
from modules.utilities.helpers import (
    duplicate_dataframe,
    get_period_length,
    get_periods_array,
)
from modules.utilities.utils import unique_list_lazy
from src.date_helpers import start_of_month, start_of_quarter

__all__ = [
    "calculate_rolling_period",
    "calculate_period_to_date_same_year",
    "calculate_period_to_date_year_ago",
]


def _collect_unique_periods(df: pl.DataFrame | pl.LazyFrame, column: str) -> list[str]:
    """Return unique values from ``column`` sorted descending."""
    lf = df.lazy() if isinstance(df, pl.DataFrame) else df
    if hasattr(unique_list_lazy, "__call__"):
        periods = unique_list_lazy(column, lf.select(pl.col(column).unique()))
    else:  # pragma: no cover - utility fallback
        periods = (
            lf.select(pl.col(column).unique())
            .collect(engine="streaming")[column]
            .to_list()
        )
    periods.sort(reverse=True)
    return periods


def _count_periods(
    df: pl.LazyFrame | pl.DataFrame, chart_dict: dict, param_dict: dict
) -> tuple[int, dict]:
    """Return number of periods found without relying on UI modules."""
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


def calculate_rolling_period(
    df: pl.DataFrame | pl.LazyFrame,
    ty_ya_dates: list[str],
    param_dict: dict,
    chart_dict: dict,
) -> tuple[pl.DataFrame | pl.LazyFrame, dict, list[str], dict]:
    """Label each row with the appropriate rolling-year bucket."""
    was_lazy = isinstance(df, pl.LazyFrame)
    df = df.lazy() if not was_lazy else df

    params = copy.deepcopy(param_dict)
    chart = copy.deepcopy(chart_dict)

    naming = get_naming_params()
    config = get_config_params()

    weeks_in_year = config[naming["weeksInYear"]]
    current_year = naming["currentYearName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    year_before = naming["yearBeforeName"]
    compare_key = naming["compareWithYearBefore"]
    not_met = naming["notMetConditionValue"]
    met = naming["metConditionValue"]
    choice_key = naming["datePeriodName"]
    year_name = naming["yearName"]
    ptd_key = naming["periodToDate"]

    params, most_recent, least_recent, months = get_period_length(df, params, False)
    ty_ya_dates.append(str(most_recent))

    difference = most_recent - least_recent
    number_of_years = (difference.days / 7) / weeks_in_year

    if round(months) >= 24:
        number_of_years = int(number_of_years)
        labels = [current_year]
        first_week = weeks_in_year
        first_delta = most_recent - dt.timedelta(weeks=first_week)

        df = df.with_columns(
            pl.when(pl.col(date_col) >= pl.lit(first_delta))
            .then(pl.lit(current_year))
            .otherwise(pl.col(period_col))
            .alias(period_col)
        )

        for i in range(1, number_of_years):
            ty_ya_dates.append(str(first_delta))
            label = f"{year_before}{i}"
            labels.append(label)
            second_week = first_week + weeks_in_year
            second_delta = most_recent - dt.timedelta(weeks=second_week)
            df = df.with_columns(
                pl.when(
                    (pl.col(date_col) < pl.lit(first_delta))
                    & (pl.col(date_col) >= pl.lit(second_delta))
                )
                .then(pl.lit(label))
                .otherwise(pl.col(period_col))
                .alias(period_col)
            )
            first_week = second_week
            first_delta = most_recent - dt.timedelta(weeks=first_week)

        df = df.filter(pl.col(period_col).is_in(labels))
    elif params[choice_key] == year_name:
        if chart.get(compare_key):
            periods = get_periods_array(df)
            if len(periods) == 1 or months <= 2:
                msg = (
                    "Dataset contains less than 24 months of data. "
                    "Rolling 12 month vs 12 month comparison might be biased"
                )
                params = add_warning_message_in_period_options_tab(params, msg)
                msg = "Period comparison set to Year-to-Date"
                params = add_warning_message_in_period_options_tab(params, msg)
                chart[compare_key] = not_met
                chart[ptd_key] = met

    result = df if was_lazy else df.collect()
    return result, params, ty_ya_dates, chart


def calculate_period_to_date_same_year(
    df_copy: pl.DataFrame | pl.LazyFrame,
    param_dict: dict,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
) -> tuple[pl.LazyFrame, dict]:
    """Return month/quarter-to-date rows for the current year."""
    naming = get_naming_params()

    date_col_found = naming["dateColFound"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]
    choice_key = naming["datePeriodName"]
    to_date_name = naming["toDateName"]
    year_name = naming["yearName"]
    quarter_name = naming["quarterName"]
    month_name = naming["monthName"]
    warn_type = naming["warningMessageType"]
    tab_key = naming["setTimePeriodTab"]

    chosen = param_dict[choice_key]
    is_found = param_dict[date_col_found]

    params = copy.deepcopy(param_dict)
    df = duplicate_dataframe(df_copy)

    if is_found:
        params, most_recent, _least, _months = get_period_length(df, params, False)
        periods = _collect_unique_periods(df, period_col)
        check_collect("QAA", "descendingPeriods", periods, session_context=session_context)

        if chosen == quarter_name:
            df, to_date_name = calculate_quarter_to_date_same_year(
                df, most_recent, periods, params
            )
            df = df.filter(pl.col(period_col).str.contains(to_date_name))
        elif chosen == month_name:
            df, to_date_name = calculate_month_to_date_same_year(
                df, most_recent, periods, params
            )
            df = df.filter(pl.col(period_col).str.contains(to_date_name))
        else:
            msg = f"Not managed period: {chosen}"
            params = add_app_message_to_paramdict(
                msg,
                warn_type,
                tab_key,
                params,
                isMessage=True,
                isToast=True,
                colNumber=0,
            )
    return df.lazy() if isinstance(df, pl.DataFrame) else df, params


def calculate_quarter_to_date_same_year(
    df: pl.DataFrame | pl.LazyFrame,
    most_recent: dt.datetime,
    periods: list[str],
    param_dict: dict,
) -> tuple[pl.LazyFrame, str]:
    """Label rows with quarter-to-date buckets for the current year."""
    naming = get_naming_params()
    to_date_name = naming["quarterToDateName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]

    df = df.lazy() if isinstance(df, pl.DataFrame) else df
    q1_end = most_recent
    q1_start = start_of_quarter(q1_end)
    q0_end = q1_end - relativedelta(months=3)
    q0_start = start_of_quarter(q0_end)

    df = df.with_columns(pl.lit("").alias(period_col))
    count = 1
    for period in periods:
        if count <= 3:
            label = f"{to_date_name}{period.upper()}"
            expr = (
                pl.when(
                    (pl.col(date_col) >= pl.lit(q1_start))
                    & (pl.col(date_col) <= pl.lit(q1_end))
                )
                .then(pl.lit(label))
                .otherwise(pl.col(period_col))
            )
            df = df.with_columns(expr.alias(period_col))
            q1_start = q0_start
            q1_end = q0_end
            q0_end = q1_end - relativedelta(months=3)
            q0_start = start_of_quarter(q0_end)
        count += 1
    df = df.filter(pl.col(period_col) != "")
    return df, to_date_name


def calculate_month_to_date_same_year(
    df: pl.DataFrame | pl.LazyFrame,
    most_recent: dt.datetime,
    periods: list[str],
    param_dict: dict,
) -> tuple[pl.LazyFrame, str]:
    """Label rows with month-to-date buckets for the current year."""
    naming = get_naming_params()
    to_date_name = naming["monthToDateName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]

    df = df.lazy() if isinstance(df, pl.DataFrame) else df
    m1_end = most_recent
    m1_start = start_of_month(m1_end)
    m0_end = m1_end - relativedelta(months=1)
    m0_start = start_of_month(m0_end)

    df = df.with_columns(pl.lit("").alias(period_col))
    count = 1
    for period in periods:
        label = f"{to_date_name}{period.upper()}"
        expr = (
            pl.when(
                (pl.col(date_col) >= pl.lit(m1_start))
                & (pl.col(date_col) <= pl.lit(m1_end))
            )
            .then(pl.lit(label))
            .otherwise(pl.col(period_col))
        )
        df = df.with_columns(expr.alias(period_col))
        m1_start = m0_start
        m1_end = m0_end
        m0_end = m1_end - relativedelta(months=1)
        m0_start = start_of_month(m0_end)
        count += 1
    df = df.filter(pl.col(period_col) != "")
    return df, to_date_name


def calculate_quarter_to_date_year_ago(
    df: pl.LazyFrame | pl.DataFrame,
    most_recent: dt.datetime,
    periods: list[str],
    param_dict: dict,
) -> tuple[pl.LazyFrame, str]:
    """Label rows with quarter-to-date buckets compared to last year."""
    naming = get_naming_params()
    to_date_name = naming["quarterToDateName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]

    df = df.lazy() if isinstance(df, pl.DataFrame) else df
    q1_end = most_recent
    q1_start = start_of_quarter(q1_end)
    q0_end = q1_end - relativedelta(years=1)
    q0_start = start_of_quarter(q0_end)

    df = df.with_columns(pl.lit("").alias(period_col))
    count = 1
    for period in periods:
        if (count - 1) % 4 == 0:
            label = f"{to_date_name}{period.upper()}"
            expr = (
                pl.when(
                    (pl.col(date_col) >= pl.lit(q1_start))
                    & (pl.col(date_col) <= pl.lit(q1_end))
                )
                .then(pl.lit(label))
                .otherwise(pl.col(period_col))
            )
            df = df.with_columns(expr.alias(period_col))
            q1_end = q0_end
            q1_start = q0_start
            q0_end = q1_end - relativedelta(years=1)
            q0_start = start_of_quarter(q0_end)
        count += 1
    return df, to_date_name


def calculate_year_to_date_year_ago(
    df: pl.LazyFrame | pl.DataFrame,
    most_recent: dt.datetime,
    periods: list[str],
    param_dict: dict,
) -> tuple[pl.LazyFrame, str]:
    """Label rows with year-to-date buckets compared to last year."""
    naming = get_naming_params()
    to_date_name = naming["yearToDateName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]

    df = df.lazy() if isinstance(df, pl.DataFrame) else df
    y1_end = most_recent
    y1_start = dt.datetime(y1_end.year, 1, 1)
    y0_end = y1_end - relativedelta(years=1)
    y0_start = dt.datetime(y0_end.year, 1, 1)

    df = df.with_columns(pl.lit("").alias(period_col))
    for period in periods:
        label = f"{to_date_name}{period.upper()}"
        expr = (
            pl.when(
                (pl.col(date_col) >= pl.lit(y1_start))
                & (pl.col(date_col) <= pl.lit(y1_end))
            )
            .then(pl.lit(label))
            .otherwise(pl.col(period_col))
        )
        df = df.with_columns(expr.alias(period_col))
        y1_start = y0_start
        y1_end = y0_end
        y0_end = y1_end - relativedelta(years=1)
        y0_start = dt.datetime(y0_end.year, 1, 1)
    return df, to_date_name


def calculate_month_to_date_year_ago(
    df: pl.LazyFrame | pl.DataFrame,
    most_recent: dt.datetime,
    periods: list[str],
    param_dict: dict,
) -> tuple[pl.LazyFrame, str]:
    """Label rows with month-to-date buckets compared to last year."""
    naming = get_naming_params()
    to_date_name = naming["monthToDateName"]
    date_col = naming["dateName"]
    period_col = naming["periodName"]

    df = df.lazy() if isinstance(df, pl.DataFrame) else df
    m1_end = most_recent
    m1_start = start_of_month(m1_end)
    m0_end = m1_end - relativedelta(years=1)
    m0_start = start_of_month(m0_end)

    df = df.with_columns(pl.lit("").alias(period_col))
    count = 1
    for period in periods:
        if (count - 1) % 12 == 0:
            label = f"{to_date_name}{period.upper()}"
            expr = (
                pl.when(
                    (pl.col(date_col) >= pl.lit(m1_start))
                    & (pl.col(date_col) <= pl.lit(m1_end))
                )
                .then(pl.lit(label))
                .otherwise(pl.col(period_col))
            )
            df = df.with_columns(expr.alias(period_col))
            m1_start = m0_start
            m1_end = m0_end
            m0_end = m1_end - relativedelta(years=1)
            m0_start = start_of_month(m0_end)
        count += 1
    df = df.filter(pl.col(period_col) != "")
    return df, to_date_name


def calculate_period_to_date_year_ago(
    df: pl.DataFrame | pl.LazyFrame,
    param_dict: dict,
    session_context: SessionContext | MutableMapping[str, Any] | None = None,
) -> tuple[pl.LazyFrame, dict]:
    """Return period-to-date rows compared to the previous year."""
    df = df.lazy() if isinstance(df, pl.DataFrame) else df

    naming = get_naming_params()
    date_col_found = naming["dateColFound"]
    period_col = naming["periodName"]
    choice_key = naming["datePeriodName"]
    year_name = naming["yearName"]
    quarter_name = naming["quarterName"]
    month_name = naming["monthName"]

    chosen = param_dict[choice_key]
    is_found = param_dict[date_col_found]
    params = copy.deepcopy(param_dict)

    if is_found:
        params, most_recent, _least, months = get_period_length(df, params, False)
        periods = _collect_unique_periods(df, period_col)
        check_collect("RAA", "descendingPeriods", periods, session_context=session_context)

        if months > 1:
            if chosen == year_name:
                df, to_date = calculate_year_to_date_year_ago(
                    df, most_recent, periods, params
                )
            elif chosen == quarter_name:
                df, to_date = calculate_quarter_to_date_year_ago(
                    df, most_recent, periods, params
                )
            elif chosen == month_name:
                df, to_date = calculate_month_to_date_year_ago(
                    df, most_recent, periods, params
                )
                df = df.filter(pl.col(period_col).str.contains(to_date))
    return df, params
