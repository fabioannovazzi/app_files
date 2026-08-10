"""Input time/scenario availability discovery for chart-family plugins."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Iterable

import polars as pl

from modules.utilities.helpers import get_schema_and_column_names
from modules.utilities.utils import get_row_count
from modules.chart_harness.period_contract import (
    PERIOD_GRAIN_MONTH,
    PERIOD_GRAIN_QUARTER,
    PERIOD_GRAIN_WEEK,
    PERIOD_GRAIN_YEAR,
    PERIOD_TYPE_CALENDAR,
    PERIOD_TYPE_CUSTOM,
    PERIOD_TYPE_FISCAL,
    PERIOD_TYPE_ROLLING,
    PERIOD_TYPE_TO_DATE,
    scenario_column_kind,
    scenario_roles_for_values,
)

__all__ = ["available_analysis_context"]

SCHEMA_VERSION = "1.0"
MAX_DATE_PREVIEW = 12
MAX_LABEL_VALUES = 64
SCENARIO_NAME_HINTS = (
    "scenario",
    "version",
    "case",
    "plan",
    "budget",
    "forecast",
    "actual",
)
PERIOD_LABEL_NAME_HINTS = (
    "period",
    "time",
    "month",
    "quarter",
    "week",
    "year",
)
DATE_NAME_HINTS = ("date", "day")


def available_analysis_context(frame: pl.DataFrame) -> dict[str, Any]:
    """Return mechanically discoverable time frames and scenario labels.

    This is deterministic because it only exposes verifiable input facts: column
    names, dtypes, observed date ranges/grains, and low-cardinality period or
    scenario labels. Story selection remains model-led.
    """

    columns, schema = get_schema_and_column_names(frame)
    date_columns = [
        profile
        for column in columns
        if (profile := _date_column_profile(frame, column, schema[column])) is not None
    ]
    period_label_columns = [
        profile
        for column in columns
        if (
            profile := _period_or_scenario_column_profile(
                frame,
                column,
                schema[column],
                date_column_names={item["column"] for item in date_columns},
            )
        )
        is not None
    ]
    scenario_columns = [
        item
        for item in period_label_columns
        if item["semantic_kind"] in {"scenario", "comparison_period_labels"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "row_count": get_row_count(frame),
        "time": {
            "date_columns": date_columns,
            "default_date_column": date_columns[0]["column"] if date_columns else None,
            "status": "found" if date_columns else "not_found",
            "period_contract": {
                "period_types": [
                    PERIOD_TYPE_CALENDAR,
                    PERIOD_TYPE_TO_DATE,
                    PERIOD_TYPE_ROLLING,
                    PERIOD_TYPE_FISCAL,
                    PERIOD_TYPE_CUSTOM,
                ],
                "period_grains": [
                    PERIOD_GRAIN_YEAR,
                    PERIOD_GRAIN_QUARTER,
                    PERIOD_GRAIN_MONTH,
                    PERIOD_GRAIN_WEEK,
                ],
                "comparison_modes": ["single", "two_period", "series"],
            },
            "fiscal_calendar": {
                "status": "not_configured",
                "available": False,
                "requires": (
                    "fiscal_start_month, fiscal_year_start_month, "
                    "or fiscal_calendar mapping"
                ),
            },
        },
        "scenario": {
            "scenario_columns": scenario_columns,
            "default_scenario_column": (
                scenario_columns[0]["column"] if scenario_columns else None
            ),
            "recognized_roles": ["AC", "PY", "PL", "FC", "budget"],
            "status": "found" if scenario_columns else "not_found",
        },
        "period_label_columns": period_label_columns,
    }


def _date_column_profile(
    frame: pl.DataFrame, column: str, dtype: Any
) -> dict[str, Any] | None:
    """Return a date availability profile for a column when it is date-like."""

    if not _is_date_dtype(dtype) and not _looks_like_named_date(column):
        return None
    expression = _date_expression(column, dtype)
    date_frame = frame.select(expression.alias("_date")).drop_nulls()
    if get_row_count(date_frame) == 0:
        return None
    values = sorted({item for item in date_frame["_date"].to_list() if item})
    if not values:
        return None
    first, last = values[0], values[-1]
    span_days = (last - first).days if isinstance(first, date) else None
    years = sorted({item.year for item in values})
    quarters = sorted({f"{item.year}Q{((item.month - 1) // 3) + 1}" for item in values})
    months = sorted({f"{item.year}-{item.month:02d}" for item in values})
    weeks = sorted(
        {
            f"{iso.year}-W{iso.week:02d}"
            for item in values
            for iso in [item.isocalendar()]
        }
    )
    return {
        "column": column,
        "dtype": str(dtype),
        "non_null_count": get_row_count(date_frame),
        "unique_count": len(values),
        "min": str(first),
        "max": str(last),
        "earliest_values": [str(item) for item in values[:MAX_DATE_PREVIEW]],
        "latest_values": [str(item) for item in values[-MAX_DATE_PREVIEW:]],
        "observed_grain": _observed_grain(values),
        "span_days": span_days,
        "calendar_periods": {
            "years": years,
            "quarters": _bounded(quarters),
            "months": _bounded(months),
            "weeks": _bounded(weeks),
        },
        "available_time_frames": _available_time_frames(
            span_days=span_days or 0,
            year_count=len(years),
            quarter_count=len(quarters),
            month_count=len(months),
            week_count=len(weeks),
            exact_count=len(values),
        ),
    }


def _period_or_scenario_column_profile(
    frame: pl.DataFrame,
    column: str,
    dtype: Any,
    *,
    date_column_names: set[str],
) -> dict[str, Any] | None:
    """Return low-cardinality period/scenario labels for request planning."""

    if column in date_column_names or _is_date_dtype(dtype):
        return None
    normalized_column = _normalize(column)
    if not _has_any_hint(
        normalized_column, (*SCENARIO_NAME_HINTS, *PERIOD_LABEL_NAME_HINTS)
    ):
        return None
    values = _unique_text_values(frame, column, limit=MAX_LABEL_VALUES + 1)
    if not values or len(values) > MAX_LABEL_VALUES:
        return None
    roles = _semantic_label_roles(values)
    semantic_kind = _semantic_kind(normalized_column, roles)
    return {
        "column": column,
        "dtype": str(dtype),
        "unique_count": len(values),
        "values": values,
        "semantic_kind": semantic_kind,
        "recognized_roles": roles,
    }


def _is_date_dtype(dtype: Any) -> bool:
    dtype_text = str(dtype)
    return dtype_text == "Date" or dtype_text.startswith("Datetime")


def _looks_like_named_date(column: str) -> bool:
    normalized = _normalize(column)
    return _has_any_hint(normalized, DATE_NAME_HINTS)


def _date_expression(column: str, dtype: Any) -> pl.Expr:
    if _is_date_dtype(dtype):
        return pl.col(column).cast(pl.Date)
    return pl.col(column).cast(pl.Utf8).str.strptime(pl.Date, strict=False)


def _observed_grain(values: list[date]) -> str:
    if len(values) < 2:
        return "single_period"
    gaps = [
        (right - left).days for left, right in zip(values, values[1:]) if right > left
    ]
    if not gaps:
        return "single_period"
    mode_gap = Counter(gaps).most_common(1)[0][0]
    if mode_gap == 1:
        return "daily"
    if mode_gap == 7:
        return "weekly"
    if 28 <= mode_gap <= 31:
        return "monthly"
    if 89 <= mode_gap <= 92:
        return "quarterly"
    if 364 <= mode_gap <= 366:
        return "yearly"
    return "irregular"


def _available_time_frames(
    *,
    span_days: int,
    year_count: int,
    quarter_count: int,
    month_count: int,
    week_count: int,
    exact_count: int,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "exact_period",
            "available": exact_count > 0,
            "basis": "date_column_values",
            "value_count": exact_count,
        },
        {
            "id": "calendar_year",
            "available": year_count > 0,
            "basis": "date_column",
            "value_count": year_count,
        },
        {
            "id": "calendar_quarter",
            "available": quarter_count > 0,
            "basis": "date_column",
            "value_count": quarter_count,
        },
        {
            "id": "calendar_month",
            "available": month_count > 0,
            "basis": "date_column",
            "value_count": month_count,
        },
        {
            "id": "calendar_week",
            "available": week_count > 0,
            "basis": "date_column",
            "value_count": week_count,
        },
        {
            "id": "calendar_ytd",
            "available": year_count > 0,
            "basis": "date_column",
        },
        {
            "id": "rolling_window",
            "available": span_days >= 7,
            "basis": "date_column",
            "windows": [
                {"id": "rolling_4_weeks", "available": span_days >= 28},
                {"id": "rolling_13_weeks", "available": span_days >= 91},
                {"id": "rolling_52_weeks", "available": span_days >= 364},
            ],
        },
        {
            "id": "fiscal_year",
            "available": False,
            "basis": "requires_fiscal_calendar",
        },
    ]


def _unique_text_values(frame: pl.DataFrame, column: str, *, limit: int) -> list[str]:
    values = (
        frame.select(pl.col(column).cast(pl.Utf8).drop_nulls().unique().sort())
        .to_series()
        .head(limit)
        .to_list()
    )
    return [str(value) for value in values if value is not None]


def _semantic_label_roles(values: Iterable[str]) -> dict[str, list[str]]:
    return scenario_roles_for_values(values)


def _semantic_kind(column: str, roles: dict[str, list[str]]) -> str:
    values = [label for labels in roles.values() for label in labels]
    if values:
        return scenario_column_kind(column, values)
    return "scenario" if _has_any_hint(column, SCENARIO_NAME_HINTS) else "period_label"


def _bounded(values: list[Any]) -> dict[str, Any]:
    return {
        "count": len(values),
        "values": values[:MAX_DATE_PREVIEW],
        "latest_values": values[-MAX_DATE_PREVIEW:],
    }


def _has_any_hint(normalized: str, hints: Iterable[str]) -> bool:
    return any(_normalize(hint) in normalized for hint in hints)


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
