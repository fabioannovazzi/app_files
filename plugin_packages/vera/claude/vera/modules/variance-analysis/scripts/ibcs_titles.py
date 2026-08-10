"""IBCS-style chart titles for variance-analysis outputs."""

from __future__ import annotations

import html
import re
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

    raw_language = str(recipe.get("language") or "en").lower().replace("_", "-")
    return raw_language.split("-", maxsplit=1)[0]


def _clean_text(value: Any) -> str:
    """Return a single-line display string."""

    return clean_reporting_text(value)


def _format_entity_name(value: str) -> str:
    """Return a readable entity name from a source file stem or option."""

    return format_reporting_entity_name(value) or "Sales"


def _entity_name(recipe: dict[str, Any]) -> str:
    """Return the chart subject."""

    subject = reporting_subject_label_from_recipe(recipe)
    if subject:
        return subject
    return {
        "it": "Vendite",
        "es": "Ventas",
        "fr": "Ventes",
        "de": "Umsatz",
    }.get(_language(recipe), "Sales")


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
    language = _language(recipe)
    baseline_default = {
        "it": "base",
        "es": "base",
        "fr": "référence",
        "de": "Basis",
    }.get(language, "baseline")
    comparison_default = {
        "it": "confronto",
        "es": "comparación",
        "fr": "comparaison",
        "de": "Vergleich",
    }.get(language, "comparison")
    baseline = _clean_text(mappings.get("baseline_period")) or baseline_default
    comparison = _clean_text(mappings.get("comparison_period")) or comparison_default
    text = f"{comparison} vs {baseline}"
    if options.get("comparison_basis") != "period":
        return text
    period_text = reporting_period_line_from_recipe(
        recipe,
        current_label=comparison,
        previous_label=baseline,
    )
    return _localized_period_text(period_text, language)


def _localized_period_text(text: str, language: str) -> str:
    """Translate stable framework period suffixes for supported languages."""

    if language == "es":
        return _spanish_period_text(text)
    translations = {
        "it": {
            ", calendar period": ", periodo di calendario",
            ", rolling period": ", periodo mobile",
            ", year to date": ", progressivo anno",
            ", period to date": ", progressivo periodo",
            ", custom": ", confronto personalizzato",
            ", not applicable": ", non applicabile",
        },
        "fr": {
            ", calendar period": ", période calendaire",
            ", rolling period": ", période glissante",
            ", year to date": ", cumul annuel",
            ", period to date": ", cumul de période",
            ", custom": ", comparaison personnalisée",
            ", not applicable": ", non applicable",
        },
        "de": {
            ", calendar period": ", Kalenderperiode",
            ", rolling period": ", rollierende Periode",
            ", year to date": ", seit Jahresbeginn",
            ", period to date": ", seit Periodenbeginn",
            ", custom": ", benutzerdefinierter Vergleich",
            ", not applicable": ", nicht anwendbar",
        },
    }.get(language, {})
    localized = text
    replacements = {
        "it": (
            (", through ", ", fino al "),
            (", rolling through ", ", mobile fino al "),
        ),
        "fr": (
            (", through ", ", jusqu’au "),
            (", rolling through ", ", glissant jusqu’au "),
        ),
        "de": ((", through ", ", bis "), (", rolling through ", ", rollierend bis ")),
    }.get(language, ())
    for source, target in replacements:
        localized = localized.replace(source, target)
    for source, target in translations.items():
        if localized.endswith(source):
            return f"{localized[: -len(source)]}{target}"
    return localized


def _spanish_period_text(text: str) -> str:
    """Translate framework wording in a shared reporting-period label."""

    localized = text.replace(", YTD through ", ", acumulado del año hasta ")
    localized = localized.replace(", rolling through ", ", periodo móvil hasta ")
    localized = localized.replace(", through ", ", hasta ")
    localized = re.sub(
        r", rolling (\d+) months$",
        r", periodo móvil de \1 meses",
        localized,
    )
    suffixes = {
        ", rolling period": ", periodo móvil",
        ", calendar period": ", periodo natural",
        ", year to date": ", acumulado del año",
        ", period to date": ", acumulado del periodo",
        ", latest rolling year vs prior year": (
            ", último año móvil frente al año anterior"
        ),
        ", custom": ", comparación personalizada",
        ", not applicable": ", no aplicable",
    }
    for english_suffix, spanish_suffix in suffixes.items():
        if localized.endswith(english_suffix):
            return f"{localized[: -len(english_suffix)]}{spanish_suffix}"
    return localized


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
    dimension_text = _localized_dimension_text(dimension, language)
    selection_text = _clean_text(selection_label)
    if language == "it":
        base = {
            "standard_variance": "Varianza vendite",
            "pvm_decomposition_ladder": "Varianza vendite: prezzo, unità, mix",
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
            "root_cause": "Varianza vendite per cause",
            "root_cause_total": "Varianza totale vendite per cause",
            "variable_root_cause_total": (
                "Varianza totale vendite per cause a dimensione variabile"
            ),
            "root_cause_component": "Varianza componenti vendite per cause",
            "variable_root_cause": "Varianza vendite per cause a dimensione variabile",
            "root_cause_drilldown": (
                f"Dettaglio delle cause della varianza vendite: {selection_text}"
                if selection_text
                else "Dettaglio delle cause della varianza vendite"
            ),
        }.get(chart_kind, "Varianza vendite")
    elif language == "es":
        base = {
            "standard_variance": "Varianza de ventas",
            "pvm_decomposition_ladder": ("Varianza de ventas: precio, unidades y mix"),
            "standard_small_multiples": (
                f"Varianza de ventas por {dimension_text}"
                if dimension_text
                else "Varianza de ventas por dimensión"
            ),
            "total_by_dimension": (
                f"Varianza total de ventas por {dimension_text}"
                if dimension_text
                else "Varianza total de ventas por dimensión"
            ),
            "root_cause": "Varianza de ventas por causa raíz",
            "root_cause_total": "Varianza total de ventas por causa raíz",
            "variable_root_cause_total": (
                "Varianza total de ventas por causa raíz y dimensión variable"
            ),
            "root_cause_component": (
                "Varianza de componentes de ventas por causa raíz"
            ),
            "variable_root_cause": (
                "Varianza de ventas por causa raíz y dimensión variable"
            ),
            "root_cause_drilldown": (
                f"Desglose de causa raíz de ventas: {selection_text}"
                if selection_text
                else "Desglose de causa raíz de ventas"
            ),
        }.get(chart_kind, "Varianza de ventas")
    elif language == "fr":
        base = {
            "standard_variance": "Écart de ventes",
            "pvm_decomposition_ladder": "Écart de ventes : prix, unités, mix",
            "standard_small_multiples": (
                f"Écart de ventes par {dimension_text}"
                if dimension_text
                else "Écart de ventes par dimension"
            ),
            "total_by_dimension": "Écart total de ventes par dimension",
            "root_cause": "Écart de ventes — causes",
            "root_cause_total": "Écart total de ventes — causes",
            "variable_root_cause_total": "Écart total de ventes à dimensions variables",
            "root_cause_component": "Écart des composantes de ventes — causes",
            "variable_root_cause": "Écart de ventes à dimensions variables",
            "root_cause_drilldown": (
                f"Détail de l’écart de ventes : {selection_text}"
                if selection_text
                else "Détail de l’écart de ventes"
            ),
        }.get(chart_kind, "Écart de ventes")
    elif language == "de":
        base = {
            "standard_variance": "Umsatzabweichung",
            "pvm_decomposition_ladder": "Umsatzabweichung: Preis, Menge, Mix",
            "standard_small_multiples": (
                f"Umsatzabweichung nach {dimension_text}"
                if dimension_text
                else "Umsatzabweichung nach Dimension"
            ),
            "total_by_dimension": "Gesamte Umsatzabweichung nach Dimension",
            "root_cause": "Umsatzabweichung — Ursachen",
            "root_cause_total": "Gesamte Umsatzabweichung — Ursachen",
            "variable_root_cause_total": "Gesamte Umsatzabweichung mit variablen Dimensionen",
            "root_cause_component": "Komponenten der Umsatzabweichung — Ursachen",
            "variable_root_cause": "Umsatzabweichung mit variablen Dimensionen",
            "root_cause_drilldown": (
                f"Detail der Umsatzabweichung: {selection_text}"
                if selection_text
                else "Detail der Umsatzabweichung"
            ),
        }.get(chart_kind, "Umsatzabweichung")
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


def _localized_dimension_text(value: Any, language: str) -> str:
    """Translate common dimension names for display-only chart titles."""

    raw_value = _clean_text(value)
    translations = {
        "it": {
            "product": "prodotto",
            "region": "area",
            "subregion": "sottoarea",
            "customer": "cliente",
            "channel": "canale",
        },
        "es": {
            "product": "producto",
            "region": "región",
            "subregion": "subregión",
            "customer": "cliente",
            "channel": "canal",
        },
        "fr": {
            "product": "produit",
            "region": "région",
            "subregion": "sous-région",
            "customer": "client",
            "channel": "canal",
        },
        "de": {
            "product": "Produkt",
            "region": "Region",
            "subregion": "Teilregion",
            "customer": "Kunde",
            "channel": "Kanal",
        },
    }.get(language, {})
    return translations.get(raw_value.casefold(), raw_value)


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
    for subject in ("Sales", "Vendite", "Ventas", "Ventes", "Umsatz"):
        index = cleaned.casefold().find(subject.casefold())
        if index < 0:
            continue
        end = index + len(subject)
        before_ok = index == 0 or not cleaned[index - 1].isalnum()
        after_ok = end == len(cleaned) or not cleaned[end].isalnum()
        if before_ok and after_ok:
            return tuple(
                segment
                for segment in (
                    (cleaned[:index], False),
                    (cleaned[index:end], True),
                    (cleaned[end:], False),
                )
                if segment[0]
            )
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
