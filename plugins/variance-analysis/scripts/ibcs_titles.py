"""IBCS-style chart titles for variance-analysis outputs."""

from __future__ import annotations

import html
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PLUGIN_ROOT / "vendor"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_VENDOR_ROOT = REPO_ROOT / "plugins" / "_shared" / "vendor"
TITLE_VENDOR_ROOT = (
    SHARED_VENDOR_ROOT
    if (SHARED_VENDOR_ROOT / "modules" / "__init__.py").exists()
    else VENDOR_ROOT
)
title_vendor_text = str(TITLE_VENDOR_ROOT)
if title_vendor_text in sys.path:
    sys.path.remove(title_vendor_text)
sys.path.insert(0, title_vendor_text)
from modules.chart_harness import (  # noqa: E402
    clean_reporting_text,
    format_reporting_entity_name,
    reporting_period_line_from_recipe,
    reporting_subject_label_from_recipe,
)

__all__ = [
    "IBCSTitle",
    "build_ibcs_title",
    "ibcs_title_html",
    "measure_line_segments",
]


@dataclass(frozen=True)
class IBCSTitle:
    """Three-line title that keeps who, what, and when explicit."""

    who: str
    what: str
    when: str

    def lines(self) -> list[str]:
        """Return non-empty title lines in display order."""

        return [line for line in (self.who, self.what, self.when) if line]


def _language(recipe: dict[str, Any]) -> str:
    """Return the recipe language code."""

    return str(recipe.get("language") or "en").lower()


def _clean_text(value: Any) -> str:
    """Return a single-line display string."""

    return clean_reporting_text(value)


def _format_entity_name(value: str) -> str:
    """Return a readable entity name from a source file stem or option."""

    return format_reporting_entity_name(value) or "Sales"


def _entity_name(recipe: dict[str, Any]) -> str:
    """Return the chart subject."""

    return reporting_subject_label_from_recipe(recipe) or "Sales"


def _currency_unit(recipe: dict[str, Any]) -> str:
    """Return the currency/unit suffix for chart titles."""

    options = recipe.get("options") or {}
    explicit_unit = _clean_text(options.get("chart_unit") or options.get("value_unit"))
    if explicit_unit:
        return explicit_unit
    return _clean_text(options.get("currency")) or "EUR"


def _comparison_text(recipe: dict[str, Any]) -> str:
    """Return the comparison period/scenario text."""

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    baseline = _clean_text(mappings.get("baseline_period")) or "baseline"
    comparison = _clean_text(mappings.get("comparison_period")) or "comparison"
    text = f"{comparison} vs {baseline}"
    if options.get("comparison_basis") != "period":
        return text
    return reporting_period_line_from_recipe(
        recipe,
        current_label=comparison,
        previous_label=baseline,
    )


def _what_text(
    recipe: dict[str, Any],
    *,
    chart_kind: str,
    dimension: str | None,
    selection_label: str | None,
) -> str:
    """Return the chart measure and analysis type."""

    language = _language(recipe)
    unit = _currency_unit(recipe)
    dimension_text = _clean_text(dimension)
    selection_text = _clean_text(selection_label)
    if language == "it":
        base = {
            "standard_variance": "Varianza vendite",
            "pvm_decomposition_ladder": "Varianza vendite: price, units, mix",
            "standard_small_multiples": (
                f"Varianza vendite per {dimension_text}"
                if dimension_text
                else "Varianza vendite per dimensione"
            ),
            "total_by_dimension": (
                f"Varianza totale vendite per {dimension_text}"
                if dimension_text
                else "Varianza totale vendite per dimensione"
            ),
            "root_cause": "Varianza root-cause vendite",
            "root_cause_total": "Varianza root-cause totale vendite",
            "variable_root_cause_total": (
                "Varianza root-cause totale vendite a dimensione variabile"
            ),
            "root_cause_component": "Varianza root-cause componenti vendite",
            "variable_root_cause": "Varianza root-cause vendite a dimensione variabile",
            "root_cause_drilldown": (
                f"Drilldown root-cause vendite: {selection_text}"
                if selection_text
                else "Drilldown root-cause vendite"
            ),
        }.get(chart_kind, "Varianza vendite")
    else:
        base = {
            "standard_variance": "Sales variance",
            "pvm_decomposition_ladder": "Sales variance: price, units, mix",
            "standard_small_multiples": (
                f"Sales variance by {dimension_text}"
                if dimension_text
                else "Sales variance by dimension"
            ),
            "total_by_dimension": (
                f"Sales total variance by {dimension_text}"
                if dimension_text
                else "Sales total variance by dimension"
            ),
            "root_cause": "Sales root-cause variance",
            "root_cause_total": "Sales root-cause total variance",
            "variable_root_cause_total": (
                "Sales variable-dimension root-cause total variance"
            ),
            "root_cause_component": "Sales root-cause component variance",
            "variable_root_cause": "Sales variable-dimension root-cause variance",
            "root_cause_drilldown": (
                f"Sales root-cause drilldown: {selection_text}"
                if selection_text
                else "Sales root-cause drilldown"
            ),
        }.get(chart_kind, "Sales variance")
    return f"{base} | {unit}" if unit else base


def build_ibcs_title(
    recipe: dict[str, Any],
    *,
    chart_kind: str,
    dimension: str | None = None,
    selection_label: str | None = None,
) -> IBCSTitle:
    """Build a neutral who/what/when chart title."""

    return IBCSTitle(
        who=_entity_name(recipe),
        what=_what_text(
            recipe,
            chart_kind=chart_kind,
            dimension=dimension,
            selection_label=selection_label,
        ),
        when=_comparison_text(recipe),
    )


def measure_line_segments(text: str) -> tuple[tuple[str, bool], ...]:
    """Return title measure text split into plain and emphasized segments."""

    cleaned = _clean_text(text)
    if not cleaned:
        return ()
    if cleaned == "Sales":
        return (("Sales", True),)
    if cleaned.startswith("Sales "):
        return (("Sales", True), (cleaned[len("Sales") :], False))
    return ((cleaned, False),)


def _segments_html(segments: tuple[tuple[str, bool], ...]) -> str:
    return "".join(
        f"<b>{html.escape(text)}</b>" if emphasized else html.escape(text)
        for text, emphasized in segments
        if text
    )


def ibcs_title_html(title: IBCSTitle) -> str:
    """Return a Plotly-compatible HTML title."""

    lines = title.lines()
    if not lines:
        return ""
    if len(lines) == 1:
        return html.escape(lines[0])
    first_line = html.escape(lines[0])
    measure_line = _segments_html(measure_line_segments(lines[1]))
    if len(lines) == 2:
        return f"{first_line}<br>{measure_line}"
    return f"{first_line}<br>{measure_line}<br>{html.escape(lines[2])}"
