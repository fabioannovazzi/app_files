"""Shared helpers for reporting chart title metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .period_label_policy import is_scenario_label, looks_like_resolved_period_label
from .recipe_filters import extract_recipe_filters

__all__ = [
    "clean_reporting_text",
    "format_reporting_entity_name",
    "ReportingTitleContract",
    "apply_three_row_plotly_title",
    "plotly_title_lines",
    "plain_plotly_title_text",
    "reporting_entity_label_from_recipe",
    "reporting_filter_label_from_recipe",
    "reporting_period_line_from_recipe",
    "reporting_subject_label_from_recipe",
    "reporting_title_html",
    "three_row_title_html",
]

MAX_FILTER_CLAUSES = 4
MAX_FILTER_VALUES = 3


@dataclass(frozen=True)
class ReportingTitleContract:
    """Three-row title contract: who/scope, what/grain, when/window."""

    who: str
    what: str
    when: str

    def lines(self) -> list[str]:
        """Return non-empty title rows in display order."""

        return [line for line in (self.who, self.what, self.when) if line]

    def html(self) -> str:
        """Return Plotly-compatible HTML for the three title rows."""

        return three_row_title_html(*self.lines())


def clean_reporting_text(value: Any) -> str:
    """Return a compact single-line reporting label."""

    return re.sub(r"\s+", " ", str(value or "").strip())


def format_reporting_entity_name(value: Any) -> str:
    """Return a readable reporting entity from an option value or source stem."""

    cleaned = clean_reporting_text(value).replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    parts = cleaned.split()
    if len(parts) > 1 and re.fullmatch(r"(?i)[ivxlcdm]+", parts[-1]):
        cleaned = " ".join(parts[:-1]).strip()
    compact = re.sub(r"[^A-Za-z0-9]", "", cleaned).lower()
    known_names = {"adventureworks": "AdventureWorks"}
    if compact in known_names:
        return known_names[compact]
    if cleaned.islower() or cleaned.isupper():
        return cleaned.title()
    return cleaned


def _option_text(options: Mapping[str, Any], key: str) -> str:
    return clean_reporting_text(options.get(key))


def reporting_entity_label_from_recipe(recipe: Mapping[str, Any]) -> str:
    """Return the reporting entity label for a chart recipe."""

    options = recipe.get("options")
    if not isinstance(options, Mapping):
        options = {}
    for key in (
        "reporting_entity_label",
        "reporting_entity",
        "company_name",
        "entity_name",
        "business_name",
        "dataset_name",
    ):
        value = _option_text(options, key)
        if value:
            return format_reporting_entity_name(value)
    market = _option_text(options, "market")
    category = _option_text(options, "category")
    if market and category:
        return format_reporting_entity_name(f"{market} {category}")
    source_file = clean_reporting_text(recipe.get("source_file"))
    if source_file:
        return format_reporting_entity_name(Path(source_file).stem)
    return ""


def reporting_filter_label_from_recipe(recipe: Mapping[str, Any]) -> str:
    """Return a compact visible label for active recipe filters."""

    options = recipe.get("options")
    if not isinstance(options, Mapping):
        options = {}
    filters = _audited_filters(options) or extract_recipe_filters(recipe)
    clauses: list[str] = []
    for item in filters:
        if not isinstance(item, Mapping):
            continue
        column = clean_reporting_text(item.get("column"))
        if not column:
            continue
        if item.get("display_in_title") is False:
            continue
        clauses.extend(_filter_clauses(column, item))
        if len(clauses) >= MAX_FILTER_CLAUSES:
            break
    return "; ".join(clauses[:MAX_FILTER_CLAUSES])


def reporting_subject_label_from_recipe(recipe: Mapping[str, Any]) -> str:
    """Return the visible reporting subject, including active filters."""

    entity = reporting_entity_label_from_recipe(recipe)
    filter_label = reporting_filter_label_from_recipe(recipe)
    return " | ".join(part for part in (entity, filter_label) if part)


def _audited_filters(options: Mapping[str, Any]) -> list[Any]:
    audit = options.get("recipe_filter_audit")
    if not isinstance(audit, Mapping) or audit.get("status") != "written":
        return []
    filters = audit.get("filters")
    if not isinstance(filters, list) or not filters:
        return []
    return filters


def _filter_clauses(column: str, item: Mapping[str, Any]) -> list[str]:
    clauses: list[str] = []
    include = _filter_values(item.get("include"))
    exclude = _filter_values(item.get("exclude"))
    if include:
        clauses.append(f"{column} = {', '.join(include)}")
    if exclude:
        clauses.append(f"{column} != {', '.join(exclude)}")
    comparisons = (
        ("gt", ">"),
        ("gte", ">="),
        ("lt", "<"),
        ("lte", "<="),
    )
    for key, operator in comparisons:
        value = _clean_filter_value(item.get(key))
        if value:
            clauses.append(f"{column} {operator} {value}")
    return clauses


def _filter_values(value: Any) -> list[str]:
    if value is None or value is False or value == []:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, tuple):
        values = list(value)
    elif isinstance(value, set):
        values = sorted(value)
    else:
        values = [value]
    return [
        cleaned for cleaned in (_clean_filter_value(item) for item in values) if cleaned
    ][:MAX_FILTER_VALUES]


def _clean_filter_value(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def plotly_title_lines(text: Any) -> list[str]:
    """Return non-empty Plotly title lines split on HTML line breaks."""

    return [
        line.strip()
        for line in re.split(r"<br\s*/?>", str(text or ""), flags=re.IGNORECASE)
        if line.strip()
    ]


def plain_plotly_title_text(text: Any) -> str:
    """Return title text with simple Plotly HTML stripped."""

    return re.sub(r"<[^>]+>", "", str(text or "")).strip()


def reporting_title_html(entity: str, measure_line: str, period_line: str) -> str:
    """Return the standard three-line reporting title HTML."""

    lines = [
        entity,
        measure_line,
        period_line,
    ]
    return "<br>".join(line for line in lines if clean_reporting_text(line))


def three_row_title_html(*lines: Any) -> str:
    """Return compact HTML for non-empty title rows."""

    return "<br>".join(
        clean_reporting_text(line) for line in lines if clean_reporting_text(line)
    )


def _month_name(month: Any) -> str:
    try:
        return date(2000, int(month), 1).strftime("%b")
    except (TypeError, ValueError):
        return ""


def _period_window_from_recipe(recipe: Mapping[str, Any]) -> Mapping[str, Any]:
    options = recipe.get("options")
    if not isinstance(options, Mapping):
        return {}
    window = options.get("period_window")
    return window if isinstance(window, Mapping) else {}


def _period_window_entry(
    window: Mapping[str, Any], keys: tuple[str, ...]
) -> Mapping[str, Any]:
    for key in keys:
        value = window.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _period_entry_end_date(entry: Mapping[str, Any]) -> str:
    return clean_reporting_text(entry.get("end_date") or entry.get("date"))


def _period_entry_label(entry: Mapping[str, Any]) -> str:
    for key in ("display_label", "period_label", "period", "period_value", "label"):
        value = clean_reporting_text(entry.get(key))
        if (
            value
            and not is_scenario_label(value)
            and looks_like_resolved_period_label(value)
        ):
            return value
    start_date = clean_reporting_text(entry.get("start_date"))
    end_date = _period_entry_end_date(entry)
    if start_date and end_date:
        compact = _compact_period_range_label(start_date, end_date)
        if compact:
            return compact
        return f"{start_date} to {end_date}"
    if end_date:
        return end_date
    year = entry.get("year")
    month = entry.get("month") or entry.get("month_cutoff")
    if year and month:
        try:
            return f"{int(year):04d}-{int(month):02d}"
        except (TypeError, ValueError):
            return ""
    if year:
        try:
            return f"{int(year):04d}"
        except (TypeError, ValueError):
            return ""
    return ""


def _compact_period_range_label(start_date: str, end_date: str) -> str:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return ""
    if start.year == end.year and start.month == end.month:
        return f"{end.year:04d}-{end.month:02d}"
    if start.month == 1 and start.day == 1 and end.month == 12:
        return f"{end.year:04d}"
    return ""


def _period_window_entries(
    recipe: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    window = _period_window_from_recipe(recipe)
    current = _period_window_entry(window, ("current", "comparison"))
    previous = _period_window_entry(window, ("previous", "baseline"))
    return current, previous


def _scenario_period_context_suffix(
    recipe: Mapping[str, Any],
    *,
    current_label: str,
    previous_label: str,
) -> str:
    if not (is_scenario_label(current_label) or is_scenario_label(previous_label)):
        return ""
    current_entry, previous_entry = _period_window_entries(recipe)
    current_period = _period_entry_label(current_entry)
    previous_period = _period_entry_label(previous_entry)
    if current_period and previous_period and previous_label:
        return f"{current_period} vs {previous_period}"
    if current_period:
        return current_period
    return ""


def _period_end_date_from_recipe(recipe: Mapping[str, Any]) -> str:
    current, _previous = _period_window_entries(recipe)
    if current:
        end_date = _period_entry_end_date(current)
        if end_date:
            return end_date
        year = current.get("year")
        month = current.get("month") or current.get("month_cutoff")
        if year and month:
            try:
                return f"{int(year):04d}-{int(month):02d}-28"
            except (TypeError, ValueError):
                pass
    comparison = recipe.get("comparison")
    if isinstance(comparison, Mapping):
        current = comparison.get("current") or comparison.get("comparison")
        if isinstance(current, Mapping):
            end_date = clean_reporting_text(current.get("end_date"))
            if end_date:
                return end_date
    return ""


def reporting_period_line_from_recipe(
    recipe: Mapping[str, Any],
    *,
    current_label: str = "AC",
    previous_label: str | None = "PY",
    end_date: Any = None,
) -> str:
    """Return a standard comparison/window row for report titles."""

    options = recipe.get("options")
    if not isinstance(options, Mapping):
        options = {}
    current = clean_reporting_text(current_label)
    previous = clean_reporting_text(previous_label)
    comparison = f"{current} vs {previous}" if previous else current
    explicit_end_date = clean_reporting_text(end_date) or _period_end_date_from_recipe(
        recipe
    )
    scenario_context = _scenario_period_context_suffix(
        recipe, current_label=current, previous_label=previous
    )
    period_window = options.get("period_window")
    period_window_mode = None
    if isinstance(period_window, Mapping):
        period_window_mode = (
            period_window.get("mode")
            or period_window.get("period_comparison_mode")
            or period_window.get("period_type")
        )
    mode = clean_reporting_text(
        period_window_mode
        or options.get("period_comparison_mode")
        or options.get("period_type")
    )
    derivation = options.get("period_derivation")
    if isinstance(derivation, Mapping):
        derivation_type = clean_reporting_text(derivation.get("type"))
        if derivation_type:
            mode = mode or derivation_type
    if scenario_context and not previous and is_scenario_label(current):
        return scenario_context
    if scenario_context and not _mode_prefers_cutoff_label(mode):
        return f"{comparison}, {scenario_context}" if comparison else scenario_context
    if explicit_end_date:
        if mode in {
            "year_to_date",
            "period_to_date",
            "to_date",
            "latest_rolling_year_vs_prior_year",
        }:
            return f"{comparison}, YTD through {explicit_end_date}"
        if "rolling" in mode:
            return f"{comparison}, rolling through {explicit_end_date}"
        return f"{comparison}, through {explicit_end_date}"
    if scenario_context:
        return f"{comparison}, {scenario_context}" if comparison else scenario_context
    if "rolling" in mode:
        months = _rolling_window_months(recipe)
        if months:
            return f"{comparison}, rolling {months} months"
        return f"{comparison}, rolling period"
    if mode:
        return f"{comparison}, {mode.replace('_', ' ')}"
    return comparison


def _rolling_window_months(recipe: Mapping[str, Any]) -> str:
    options = recipe.get("options")
    if not isinstance(options, Mapping):
        return ""
    window = options.get("period_window")
    months = options.get("rolling_window_months")
    if not months and isinstance(window, Mapping):
        months = window.get("rolling_window_months")
    return clean_reporting_text(months)


def _mode_prefers_cutoff_label(mode: str) -> bool:
    normalized = mode.strip().lower()
    return (
        normalized in {"year_to_date", "latest_rolling_year_vs_prior_year"}
        or "rolling" in normalized
        or "to_date" in normalized
    )


def _is_legacy_title_annotation(annotation: Any, subject: str) -> bool:
    text = clean_reporting_text(getattr(annotation, "text", ""))
    if not text:
        return False
    if subject and subject in text:
        return True
    try:
        x_value = float(getattr(annotation, "x", 1.0))
        y_value = float(getattr(annotation, "y", 0.0))
    except (TypeError, ValueError):
        return False
    return (
        getattr(annotation, "xref", None) == "paper"
        and getattr(annotation, "yref", None) == "paper"
        and x_value <= 0.05
        and y_value >= 0.90
        and ("<br" in str(getattr(annotation, "text", "")).lower() or " vs " in text)
    )


def apply_three_row_plotly_title(
    fig: Any,
    title: ReportingTitleContract,
    *,
    top_margin: int = 105,
) -> list[str]:
    """Apply the standard three-row title to a Plotly figure."""

    lines = title.lines()
    title_html = three_row_title_html(*lines)
    if not title_html:
        return []
    subject = lines[0] if lines else ""
    annotations = [
        annotation
        for annotation in (list(getattr(fig.layout, "annotations", ()) or []))
        if not _is_legacy_title_annotation(annotation, subject)
    ]
    fig.update_layout(
        title={
            "text": title_html,
            "x": 0.01,
            "xanchor": "left",
            "y": 0.99,
            "yanchor": "top",
        },
    )
    fig.layout.annotations = tuple(annotations)
    margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    margin["t"] = max(int(margin.get("t") or 0), top_margin)
    fig.update_layout(margin=margin)
    return lines
