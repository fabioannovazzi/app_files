"""Shared period and scenario contract helpers for chart plugins."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Sequence

import polars as pl

__all__ = [
    "ACTUAL_LABELS",
    "BUDGET_LABELS",
    "COMPARISON_CURRENT_LABELS",
    "COMPARISON_PREVIOUS_LABELS",
    "FORECAST_LABELS",
    "PERIOD_GRAIN_MONTH",
    "PERIOD_GRAIN_QUARTER",
    "PERIOD_GRAIN_WEEK",
    "PERIOD_GRAIN_YEAR",
    "PERIOD_GRAINS",
    "PERIOD_TYPE_CALENDAR",
    "PERIOD_TYPE_CUSTOM",
    "PERIOD_TYPE_FISCAL",
    "PERIOD_TYPE_ROLLING",
    "PERIOD_TYPE_TO_DATE",
    "PERIOD_TYPES",
    "PLAN_LABELS",
    "calendar_period_label",
    "default_scenario_comparison_pair",
    "fiscal_start_month_from_options",
    "normalize_period_grain",
    "normalize_period_type",
    "normalize_scenario_label",
    "period_contract_options",
    "period_label_expression",
    "period_type_from_comparison_mode",
    "scenario_column_kind",
    "scenario_roles_for_values",
]

PERIOD_TYPE_CALENDAR = "calendar"
PERIOD_TYPE_TO_DATE = "to_date"
PERIOD_TYPE_ROLLING = "rolling"
PERIOD_TYPE_FISCAL = "fiscal"
PERIOD_TYPE_CUSTOM = "custom"
PERIOD_TYPES = {
    PERIOD_TYPE_CALENDAR,
    PERIOD_TYPE_TO_DATE,
    PERIOD_TYPE_ROLLING,
    PERIOD_TYPE_FISCAL,
    PERIOD_TYPE_CUSTOM,
}

PERIOD_GRAIN_YEAR = "year"
PERIOD_GRAIN_QUARTER = "quarter"
PERIOD_GRAIN_MONTH = "month"
PERIOD_GRAIN_WEEK = "week"
PERIOD_GRAINS = {
    PERIOD_GRAIN_YEAR,
    PERIOD_GRAIN_QUARTER,
    PERIOD_GRAIN_MONTH,
    PERIOD_GRAIN_WEEK,
}

ACTUAL_LABELS = {"ac", "actual", "act"}
COMPARISON_CURRENT_LABELS = {"current", "currentperiod", "periodone"}
COMPARISON_PREVIOUS_LABELS = {"py", "previous", "prior", "lastyear", "periodzero"}
PLAN_LABELS = {"pl", "plan", "planned"}
BUDGET_LABELS = {"budget", "bud"}
FORECAST_LABELS = {"fc", "forecast", "fcst"}

_SCENARIO_ROLE_LABELS = {
    "AC": ACTUAL_LABELS,
    "current": COMPARISON_CURRENT_LABELS,
    "PY": COMPARISON_PREVIOUS_LABELS,
    "PL": PLAN_LABELS,
    "budget": BUDGET_LABELS,
    "FC": FORECAST_LABELS,
}
_PLAN_LIKE_ROLES = ("PL", "FC", "budget")
_DEFAULT_SCENARIO_BASELINE_PRECEDENCE = ("PL", "FC", "budget")


def normalize_scenario_label(value: Any) -> str:
    """Return a compact comparison label for exact role matching."""

    return "".join(character for character in str(value).lower() if character.isalnum())


def scenario_roles_for_values(values: Iterable[Any]) -> dict[str, list[str]]:
    """Return recognized scenario/period roles, preserving observed labels.

    The rule is deterministic because IBCS-style labels are closed-form input
    codes. Ambiguous chart intent is still handled outside this helper.
    """

    roles: dict[str, list[str]] = {role: [] for role in _SCENARIO_ROLE_LABELS}
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        normalized = normalize_scenario_label(text)
        for role, labels in _SCENARIO_ROLE_LABELS.items():
            if normalized in labels and text not in roles[role]:
                roles[role].append(text)
    return {role: labels for role, labels in roles.items() if labels}


def scenario_column_kind(column_name: str, values: Iterable[Any]) -> str:
    """Classify a low-cardinality period/scenario column from exact roles."""

    roles = scenario_roles_for_values(values)
    normalized_column = normalize_scenario_label(column_name)
    if "AC" in roles and any(role in roles for role in _PLAN_LIKE_ROLES):
        return "scenario"
    if any(role in roles for role in _PLAN_LIKE_ROLES):
        return "scenario"
    if ("AC" in roles or "current" in roles) and "PY" in roles:
        return "comparison_period_labels"
    if any(
        hint in normalized_column
        for hint in ("scenario", "version", "case", "plan", "budget", "forecast")
    ):
        return "scenario"
    return "period_label"


def default_scenario_comparison_pair(
    values: Iterable[Any],
    *,
    baseline_precedence: Sequence[str] = _DEFAULT_SCENARIO_BASELINE_PRECEDENCE,
) -> tuple[str | None, str | None]:
    """Return a default plan-like baseline and actual comparison pair."""

    roles = scenario_roles_for_values(values)
    actual = roles.get("AC", [None])[0]
    if actual is None:
        return None, None
    for role in baseline_precedence:
        labels = roles.get(role) or []
        if labels and labels[0] != actual:
            return labels[0], actual
    return None, None


def normalize_period_type(value: Any, *, default: str = PERIOD_TYPE_CALENDAR) -> str:
    """Return a canonical period type."""

    if value is None or value == "":
        return default
    normalized = normalize_scenario_label(value)
    if normalized in {
        "calendar",
        "calendarperiod",
        "calendarperiods",
        "calendaryear",
        "calendaryears",
        "completecalendaryear",
        "completecalendaryears",
        "previousyear",
    }:
        return PERIOD_TYPE_CALENDAR
    if normalized in {
        "todate",
        "periodtodate",
        "yeartodate",
        "ytd",
        "fiscalyeartodate",
        "fytd",
    }:
        return PERIOD_TYPE_TO_DATE
    if normalized in {"rolling", "rollingperiod", "rollingwindow", "r12m", "l12m"}:
        return PERIOD_TYPE_ROLLING
    if normalized in {"fiscal", "fiscalyear", "fiscalperiod", "fiscalcalendar"}:
        return PERIOD_TYPE_FISCAL
    if normalized in {"custom", "explicit", "sourceperiod"}:
        return PERIOD_TYPE_CUSTOM
    return default


def period_type_from_comparison_mode(value: Any) -> str:
    """Return period type implied by legacy comparison-mode option names."""

    return normalize_period_type(value, default=PERIOD_TYPE_CALENDAR)


def normalize_period_grain(value: Any, *, default: str = PERIOD_GRAIN_YEAR) -> str:
    """Return a canonical period grain."""

    if value is None or value == "":
        return default
    normalized = normalize_scenario_label(value)
    if normalized in {"year", "years", "annual", "annually", "yearly"}:
        return PERIOD_GRAIN_YEAR
    if normalized in {"quarter", "quarters", "quarterly", "qtr", "q"}:
        return PERIOD_GRAIN_QUARTER
    if normalized in {"month", "months", "monthly", "m"}:
        return PERIOD_GRAIN_MONTH
    if normalized in {"week", "weeks", "weekly", "wk", "w"}:
        return PERIOD_GRAIN_WEEK
    return default


def period_contract_options(
    options: dict[str, Any],
    *,
    default_type: str = PERIOD_TYPE_CALENDAR,
    default_grain: str = PERIOD_GRAIN_YEAR,
) -> dict[str, Any]:
    """Return normalized period options while preserving legacy option names."""

    period_type = normalize_period_type(
        options.get("period_type") or options.get("period_comparison_mode"),
        default=default_type,
    )
    fiscal_start_month = fiscal_start_month_from_options(options)
    if (
        _has_fiscal_start_option(options)
        and fiscal_start_month != 1
        and period_type == PERIOD_TYPE_CALENDAR
    ):
        period_type = PERIOD_TYPE_FISCAL
    return {
        "period_type": period_type,
        "period_grain": normalize_period_grain(
            options.get("period_grain"), default=default_grain
        ),
        "fiscal_start_month": fiscal_start_month,
    }


def calendar_period_label(
    value: date | datetime,
    *,
    period_grain: str = PERIOD_GRAIN_YEAR,
    fiscal_start_month: int = 1,
) -> str:
    """Return a calendar/fiscal period label for one date."""

    current = value.date() if isinstance(value, datetime) else value
    grain = normalize_period_grain(period_grain)
    fiscal_month_index = ((current.month - fiscal_start_month) % 12) + 1
    fiscal_year = current.year + (1 if current.month >= fiscal_start_month else 0)
    if fiscal_start_month == 1:
        fiscal_year = current.year
        fiscal_month_index = current.month
    if grain == PERIOD_GRAIN_YEAR:
        return str(fiscal_year) if fiscal_start_month == 1 else f"FY{fiscal_year}"
    if grain == PERIOD_GRAIN_QUARTER:
        quarter = ((fiscal_month_index - 1) // 3) + 1
        prefix = str(fiscal_year) if fiscal_start_month == 1 else f"FY{fiscal_year}"
        return f"{prefix}Q{quarter}"
    if grain == PERIOD_GRAIN_MONTH:
        if fiscal_start_month == 1:
            return f"{current.year}-{current.month:02d}"
        return f"FY{fiscal_year}-M{fiscal_month_index:02d}"
    iso = current.isocalendar()
    if fiscal_start_month == 1:
        return f"{iso.year}-W{iso.week:02d}"
    return f"FY{fiscal_year}-W{iso.week:02d}"


def period_label_expression(
    date_expression: pl.Expr,
    *,
    period_grain: str = PERIOD_GRAIN_YEAR,
    fiscal_start_month: int = 1,
) -> pl.Expr:
    """Return a Polars expression for calendar/fiscal period labels."""

    grain = normalize_period_grain(period_grain)
    fiscal_start = _bounded_month(fiscal_start_month)
    month_number = date_expression.dt.month()
    year_number = date_expression.dt.year()
    if fiscal_start == 1:
        fiscal_year = year_number
        fiscal_month_index = month_number
        year_prefix = fiscal_year.cast(pl.Utf8)
    else:
        fiscal_year = (
            pl.when(month_number >= fiscal_start)
            .then(year_number + 1)
            .otherwise(year_number)
        )
        fiscal_month_index = ((month_number - fiscal_start + 12) % 12) + 1
        year_prefix = pl.concat_str([pl.lit("FY"), fiscal_year.cast(pl.Utf8)])

    if grain == PERIOD_GRAIN_YEAR:
        return year_prefix
    if grain == PERIOD_GRAIN_QUARTER:
        fiscal_quarter = (((fiscal_month_index - 1) // 3) + 1).cast(pl.Utf8)
        return pl.concat_str([year_prefix, pl.lit("Q"), fiscal_quarter])
    if grain == PERIOD_GRAIN_MONTH and fiscal_start == 1:
        return date_expression.dt.strftime("%Y-%m")
    if grain == PERIOD_GRAIN_MONTH:
        fiscal_month = fiscal_month_index.cast(pl.Utf8).str.zfill(2)
        return pl.concat_str([year_prefix, pl.lit("-M"), fiscal_month])
    if fiscal_start == 1:
        return date_expression.dt.strftime("%G-W%V")
    return pl.concat_str([year_prefix, pl.lit("-W"), date_expression.dt.strftime("%V")])


def fiscal_start_month_from_options(options: dict[str, Any]) -> int:
    """Return fiscal year start month from supported option aliases."""

    for key in (
        "fiscal_start_month",
        "fiscal_year_start_month",
        "fiscal_year_start",
        "fiscal_calendar_start_month",
    ):
        if options.get(key) not in {None, ""}:
            return _bounded_month(options.get(key))
    return 1


def _has_fiscal_start_option(options: dict[str, Any]) -> bool:
    return any(
        options.get(key) not in {None, ""}
        for key in (
            "fiscal_start_month",
            "fiscal_year_start_month",
            "fiscal_year_start",
            "fiscal_calendar_start_month",
        )
    )


def _bounded_month(value: Any) -> int:
    try:
        month = int(value)
    except (TypeError, ValueError):
        return 1
    return month if 1 <= month <= 12 else 1
