"""Client-ready root-cause variance report writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from ibcs_titles import build_ibcs_title, measure_line_segments
from PIL import Image, ImageDraw, ImageFont

__all__ = ["write_root_cause_client_report"]


MEASURE_COLUMNS = {
    "bridge_level",
    "bridge_dimensions",
    "variance_type",
    "variance_amount",
    "amount_baseline",
    "amount_comparison",
    "units_baseline",
    "units_comparison",
    "bridge_unique_value_weight",
}
TOTAL_VALUES = {"", "all", "__total", "total", "none", "null"}


def _language(recipe: dict[str, Any]) -> str:
    return str(recipe.get("language") or "en").lower()


def _currency_note(recipe: dict[str, Any], labels: dict[str, str]) -> str:
    """Return the report note for the effective currency assumption."""

    currency = str(recipe.get("options", {}).get("currency") or "").strip()
    if currency:
        return labels["currency_note"].format(currency=currency)
    return labels["source_units"]


def _comparison_metadata(recipe: dict[str, Any], language: str) -> dict[str, str]:
    """Return report wording for the effective comparison."""

    mappings = recipe.get("mappings") or {}
    options = recipe.get("options") or {}
    baseline = str(mappings.get("baseline_period") or "baseline")
    comparison = str(mappings.get("comparison_period") or "comparison")
    basis = str(options.get("comparison_basis") or "")
    mode = str(options.get("period_comparison_mode") or "")
    baseline_upper = baseline.upper()
    comparison_upper = comparison.upper()
    if basis == "period":
        if language == "it":
            comparison_name = "periodo corrente"
            baseline_name = (
                "anno precedente"
                if mode in {"rolling_period", "year_to_date"}
                else "periodo precedente"
            )
        else:
            comparison_name = "current period"
            baseline_name = (
                "prior-year period"
                if mode in {"rolling_period", "year_to_date"}
                else "prior period"
            )
    elif baseline_upper in {"PL", "PLAN"} and comparison_upper in {"AC", "ACTUAL"}:
        baseline_name = "Plan"
        comparison_name = "Actual"
    else:
        baseline_name = baseline
        comparison_name = comparison
    return {
        "baseline_label": baseline,
        "comparison_label": comparison,
        "baseline_name": baseline_name,
        "comparison_name": comparison_name,
        "comparison": f"{comparison_name} vs {baseline_name} ({comparison} vs {baseline})",
    }


def _text(language: str) -> dict[str, str]:
    if language == "it":
        return {
            "title": "Analisi delle cause della varianza vendite",
            "subtitle": "Actual vs Plan (AC vs PL)",
            "summary": "Sintesi",
            "source_data": "Dati di supporto principali",
            "reading_notes": "Note di lettura",
            "bridge_summary": "Bridge di sintesi",
            "product_line_drilldown": "Drilldown linea prodotto",
            "mixed_deep_dive": "Approfondimento misto",
            "chart_1": "Fonte 1 - Driver principale",
            "chart_2": "Fonte 2 - Dettaglio linea prodotto",
            "chart_3": "Fonte 3 - Approfondimento per area e product line",
            "chart_small_multiples": "Bridge standard per {dimension}",
            "chart_pvm_ladder": "Bridge Price / Units / Mix",
            "drilldown_findings": "Cosa emerge dai drilldown selezionati",
            "source_units": (
                "Gli importi sono in unità della sorgente: il file non "
                "fornisce una valuta esplicita."
            ),
            "currency_note": (
                "Gli importi sono presentati in {currency}; usare una valuta "
                "diversa solo se indicata dall'utente o dal file sorgente."
            ),
            "price_only": (
                "La varianza deriva solo dal prezzo: volume e mix sono pari a "
                "zero perché le unità {baseline_name} e {comparison_name} "
                "coincidono al livello di calcolo."
            ),
            "component_note": (
                "Il bridge standard è dominato da {dominant_type} "
                "({dominant_amount}); componenti principali: {components}."
            ),
            "residual_note": (
                "Le righe del bridge root-cause sono residuali: una riga "
                "successiva non va letta come totale assoluto della relativa "
                "dimensione."
            ),
            "source_caption": "Sintesi dei dati di supporto selezionati.",
            "drilldown_caption": (
                "Dettaglio dei contributi emersi dai drilldown selezionati."
            ),
            "chart_footer": (
                "Driver selezionati in sequenza; il saldo residuo è "
                "riconciliato in Other."
            ),
            "chart_summary_title": "Bridge di sintesi root-cause",
            "chart_summary_subtitle": (
                "{comparison}, driver selezionati dall'analisi root-cause"
            ),
            "chart_drilldown_title": "Drilldown: dettaglio di {label}",
            "chart_drilldown_subtitle": (
                "{comparison}, dettaglio della riga selezionata"
            ),
            "chart_mixed_title": "Approfondimento: bridge root-cause misto",
            "chart_mixed_subtitle": "{comparison}, sequenza con dimensioni diverse",
            "summary_intro": (
                "La differenza tra {comparison_name} e {baseline_name} è {delta}. "
                "Il bridge di sintesi riconcilia "
                "il movimento con {driver_count} driver selezionati ({items}) "
                "e un residuo di {residual}."
            ),
            "drilldown_intro": (
                "Il drilldown della riga principale dettaglia il contributo: "
                "{items}. Il contributo è quindi concentrato soprattutto su "
                "{top_label}."
            ),
            "mixed_intro": (
                "Una lettura più analitica conferma che il movimento non è "
                "distribuito in modo uniforme: emergono {items}. Questa vista "
                "resta un approfondimento perché lascia {residual} in residuo."
            ),
            "bridge_reading": (
                "Riconcilia il delta con la sequenza di driver selezionata."
            ),
            "drilldown_reading": "Scompone il driver principale.",
            "mixed_reading": "Individua dove il residuo aggiunge informazione.",
            "data_key": "Dato chiave",
            "reading": "Lettura",
            "residual": "residuo",
            "source_col": "Fonte",
            "analysis_area": "Area di analisi",
            "useful_reading": "Lettura utile",
            "chart_1_reading": (
                "La sequenza selezionata ({items}) riconcilia il movimento "
                "{comparison} con residuo finale {residual}."
            ),
            "chart_2_reading": (
                "Il driver principale è soprattutto {top_label}, seguito "
                "dagli altri contributi per linea prodotto."
            ),
            "chart_3_reading": (
                "Il secondo livello di analisi mostra che il residuo utile si "
                "concentra su {items}."
            ),
            "chart_small_multiples_reading": (
                "Il bridge standard per {dimension} mostra che la varianza si "
                "concentra soprattutto su {items}."
            ),
            "chart_pvm_ladder_reading": (
                "La stessa varianza è letta a tre livelli: totale combinato, "
                "Price separato da Units & Mix, e Price / Units / Mix. "
                "Componenti principali: {items}."
            ),
            "chart_1_caption": (
                "Il bridge riconcilia il movimento tra i due periodi/scenari e isola "
                "il driver principale."
            ),
            "chart_2_caption": (
                "Il dettaglio per linea prodotto traduce il driver principale in "
                "una lettura commerciale immediata."
            ),
            "chart_3_caption": (
                "Questa vista va letta come sequenza residuale: le righe "
                "successive sono al netto delle righe precedenti."
            ),
            "chart_small_multiples_caption": (
                "Ogni pannello ripete il bridge compatto Price / "
                "Units & Mix / Balance; la dimensione separa i pannelli."
            ),
            "chart_pvm_ladder_caption": (
                "La scala e i totali sono gli stessi in ogni pannello: cambia "
                "solo il livello di decomposizione della varianza."
            ),
            "pvm_ladder_source": "Lettura Price / Units / Mix",
            "pvm_ladder_reading": (
                "Confronta tre decomposizioni dello stesso movimento."
            ),
            "small_multiples_source": "Small multiples standard",
            "small_multiples_reading": (
                "Mostra lo stesso bridge standard per ciascun elemento della "
                "dimensione selezionata."
            ),
            "drilldown_balance": (
                "Il saldo include compensazioni fra contributi positivi e " "negativi."
            ),
            "drilldown_concentration": "Il contributo non dipende da un solo elemento.",
            "drilldown_composition": "Il residuo è concentrato su pochi contributi.",
            "top_contributions": "Principali contributi: {items}",
        }
    return {
        "title": "Sales Variance Root-Cause Analysis",
        "subtitle": "Actual vs Plan",
        "summary": "Summary",
        "source_data": "Key Source Data",
        "reading_notes": "Reading Notes",
        "bridge_summary": "Summary bridge",
        "product_line_drilldown": "Product-line drilldown",
        "mixed_deep_dive": "Mixed-dimension deep dive",
        "chart_1": "Source 1 - Main Driver",
        "chart_2": "Source 2 - Product-line Detail",
        "chart_3": "Source 3 - Area And Product-Line Detail",
        "chart_small_multiples": "Standard bridge by {dimension}",
        "chart_pvm_ladder": "Price / Units / Mix bridge",
        "drilldown_findings": "Selected Drilldown Findings",
        "source_units": (
            "Amounts are shown in source units because the workbook does not "
            "provide an explicit currency."
        ),
        "currency_note": (
            "Amounts are presented in {currency}; use another currency only "
            "when the user or source file states it."
        ),
        "price_only": (
            "The deterministic run is price-only: volume and mix are zero "
            "because {baseline_name} and {comparison_name} units match at the "
            "calculation grain."
        ),
        "component_note": (
            "The standard bridge is dominated by {dominant_type} "
            "({dominant_amount}); main components: {components}."
        ),
        "residual_note": (
            "Root-cause bridge rows are residual rows: a later row is not the "
            "standalone total for that dimension."
        ),
        "source_caption": "Summary of selected source data.",
        "drilldown_caption": "Detail of contributions from selected drilldowns.",
        "chart_footer": (
            "Selected drivers are shown in sequence; the residual balance is "
            "reconciled to Other."
        ),
        "chart_summary_title": "Summary bridge: {label}",
        "chart_summary_subtitle": "{comparison}, selected root-cause driver",
        "chart_drilldown_title": "Drilldown: {label}",
        "chart_drilldown_subtitle": "{comparison}, selected-row detail",
        "chart_mixed_title": "Mixed root-cause bridge",
        "chart_mixed_subtitle": "{comparison}, mixed-dimension sequence",
        "summary_intro": (
            "The difference between {comparison_name} and {baseline_name} is "
            "{delta}. The summary bridge reconciles "
            "the movement with {driver_count} selected drivers ({items}) and "
            "residual of {residual}."
        ),
        "drilldown_intro": (
            "The main-row drilldown details the contribution: {items}. The "
            "contribution is therefore concentrated mainly in {top_label}."
        ),
        "mixed_intro": (
            "A more analytical reading confirms that the movement is not "
            "evenly distributed: {items} stand out. This view remains a deep "
            "dive because it leaves {residual} in residual balance."
        ),
        "bridge_reading": "Reconciles the delta with the selected driver sequence.",
        "drilldown_reading": "Breaks the main driver into components.",
        "mixed_reading": "Identifies where residual detail adds information.",
        "data_key": "Key data",
        "reading": "Reading",
        "residual": "residual",
        "source_col": "Source",
        "analysis_area": "Analysis area",
        "useful_reading": "Useful reading",
        "chart_1_reading": (
            "The selected sequence ({items}) reconciles the {comparison} "
            "movement with final residual {residual}."
        ),
        "chart_2_reading": (
            "The main driver is mostly {top_label}, followed by other "
            "product-line contributions."
        ),
        "chart_3_reading": (
            "The second-level analysis shows that useful residual detail is "
            "concentrated in {items}."
        ),
        "chart_small_multiples_reading": (
            "The standard bridge by {dimension} shows that variance is "
            "concentrated mainly in {items}."
        ),
        "chart_pvm_ladder_reading": (
            "The same variance is read at three levels: combined total, Price "
            "separated from Units & Mix, and Price / Units / Mix. Main "
            "components: {items}."
        ),
        "chart_1_caption": (
            "The bridge reconciles the movement between the two periods/scenarios and "
            "isolates the main driver."
        ),
        "chart_2_caption": (
            "The product-line detail translates the main driver into a "
            "commercial reading."
        ),
        "chart_3_caption": (
            "This view should be read as a residual sequence: later rows are "
            "net of prior rows."
        ),
        "chart_small_multiples_caption": (
            "Each panel repeats the compact Price / Units & Mix / "
            "Balance bridge; the dimension separates the panels."
        ),
        "chart_pvm_ladder_caption": (
            "Scale and totals are the same in every panel: only the variance "
            "decomposition depth changes."
        ),
        "pvm_ladder_source": "Price / Units / Mix read",
        "pvm_ladder_reading": "Compares three decompositions of the same movement.",
        "small_multiples_source": "Standard small multiples",
        "small_multiples_reading": (
            "Shows the same standard bridge for each selected dimension member."
        ),
        "drilldown_balance": (
            "The balance includes offsets between positive and negative "
            "contributions."
        ),
        "drilldown_concentration": "The contribution is not dependent on one item.",
        "drilldown_composition": "The residual is concentrated in a few items.",
        "top_contributions": "Main contributions: {items}",
    }


def _is_total(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in TOTAL_VALUES


def _format_amount(value: Any) -> str:
    amount = float(value or 0.0)
    sign = "-" if amount < 0 else "+"
    magnitude = abs(amount)
    if magnitude >= 1_000_000:
        return f"{sign}{magnitude / 1_000_000:.2f}M"
    if magnitude >= 1_000:
        return f"{sign}{magnitude / 1_000:.1f}K"
    return f"{sign}{magnitude:.0f}"


def _format_delta(value: Any) -> str:
    magnitude = abs(float(value or 0.0))
    if magnitude >= 1_000_000:
        return f"{magnitude / 1_000_000:.2f}M"
    if magnitude >= 1_000:
        return f"{magnitude / 1_000:.1f}K"
    return f"{magnitude:.0f}"


def _format_residual(value: Any) -> str:
    return _format_amount(value)


def _summary_float(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _summary_bool(row: dict[str, Any], key: str) -> bool:
    return str(row.get(key)).strip().lower() == "true"


def _split_summary_values(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _collect_csv_scan(path: Path) -> pl.DataFrame:
    """Read generated CSV artifacts through a lazy scan and collect once."""

    lf = pl.scan_csv(path)
    try:
        return lf.collect(engine="streaming")
    except pl.exceptions.PolarsError:
        return lf.collect()


def _read_csv(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    return _collect_csv_scan(path)


def _row_label(row: dict[str, Any]) -> str:
    labels: list[str] = []
    for key, value in row.items():
        if key in MEASURE_COLUMNS or _is_total(value):
            continue
        labels.append(str(value))
    variance_type = row.get("variance_type")
    if variance_type and not _is_total(variance_type):
        labels.append(str(variance_type))
    return " / ".join(labels) if labels else "Total"


def _chart_path(output_dir: Path, value: Any) -> Path | None:
    raw = str(value or "")
    if not raw:
        return None
    path = Path(raw)
    if path.exists():
        return path
    candidate = output_dir / path.name
    return candidate if candidate.exists() else None


def _select_summary(summary_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not summary_rows:
        return None
    return min(
        summary_rows,
        key=lambda row: (
            abs(_summary_float(row, "other_residual")),
            int(row.get("row_count") or 999),
            int(row.get("alternative_result") or 999),
        ),
    )


def _first_dimensions(row: dict[str, Any]) -> list[str]:
    sequence = _split_summary_values(row.get("selected_sequence_bridge_dimensions"))
    if not sequence:
        return []
    return [item.strip() for item in sequence[0].split(",") if item.strip()]


def _select_mixed(summary_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    mixed = [
        row
        for row in summary_rows
        if _summary_bool(row, "selected_sequence_has_mixed_dimensions")
    ]
    if not mixed:
        return None
    readable = [row for row in mixed if len(_first_dimensions(row)) > 1]
    if readable:
        return min(readable, key=lambda row: int(row.get("alternative_result") or 999))
    return min(
        mixed,
        key=lambda row: (
            abs(_summary_float(row, "other_residual")),
            int(row.get("alternative_result") or 999),
        ),
    )


def _bridge_rows(output_dir: Path, alternative: int) -> list[dict[str, Any]]:
    frame = _read_csv(output_dir / f"root_cause_bridge_alt_{alternative}.csv")
    return frame.to_dicts() if not frame.is_empty() else []


def _drilldown_rows(
    output_dir: Path,
    alternative: int,
    selected_row: int,
) -> list[dict[str, Any]]:
    frame = _read_csv(
        output_dir
        / f"root_cause_bridge_alt_{alternative}_drilldown_row_{selected_row}.csv"
    )
    return frame.to_dicts() if not frame.is_empty() else []


def _selected_amounts(row: dict[str, Any]) -> list[float]:
    amounts: list[float] = []
    for item in _split_summary_values(row.get("selected_amounts")):
        try:
            amounts.append(float(item))
        except ValueError:
            continue
    return amounts


def _top_label_amounts(
    rows: list[dict[str, Any]], limit: int = 3
) -> list[tuple[str, float]]:
    sorted_rows = sorted(
        rows,
        key=lambda row: abs(float(row.get("variance_amount") or 0.0)),
        reverse=True,
    )
    return [
        (_row_label(row), float(row.get("variance_amount") or 0.0))
        for row in sorted_rows[:limit]
    ]


def _format_label_amounts(items: list[tuple[str, float]], *, limit: int = 3) -> str:
    return ", ".join(
        f"{label} {_format_amount(amount)}" for label, amount in items[:limit]
    )


def _best_product_line_items(
    output_dir: Path,
    alternative: int,
    row_index: int,
) -> list[tuple[str, float]]:
    rows = _drilldown_rows(output_dir, alternative, row_index)
    return _top_label_amounts(rows)


def _top_positive_and_negative(rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    positives = sorted(
        (
            (_row_label(row), float(row.get("variance_amount") or 0.0))
            for row in rows
            if float(row.get("variance_amount") or 0.0) > 0
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:2]
    negatives = sorted(
        (
            (_row_label(row), float(row.get("variance_amount") or 0.0))
            for row in rows
            if float(row.get("variance_amount") or 0.0) < 0
        ),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:1]
    return [*positives, *negatives]


def _drilldown_finding_rows(
    output_dir: Path,
    mixed_row: dict[str, Any] | None,
    labels: dict[str, str],
) -> list[list[str]]:
    if mixed_row is None:
        return []
    alternative = int(mixed_row.get("alternative_result") or 0)
    bridge_rows = _bridge_rows(output_dir, alternative)
    findings: list[list[str]] = []
    for index, parent_row in enumerate(bridge_rows[:3], start=1):
        drilldown_rows = _drilldown_rows(output_dir, alternative, index)
        if not drilldown_rows:
            continue
        top_items = _top_positive_and_negative(drilldown_rows)
        reading = (
            labels["drilldown_balance"]
            if any(amount < 0 for _, amount in top_items)
            else labels["drilldown_concentration"]
        )
        findings.append(
            [
                _row_label(parent_row),
                reading,
                labels["top_contributions"].format(
                    items=_format_label_amounts(top_items, limit=3)
                ),
            ]
        )
    return findings


def _small_multiples_info(
    output_dir: Path,
    labels: dict[str, str],
) -> dict[str, Any] | None:
    """Return client-report metadata for the standard small-multiples chart."""

    image_path = output_dir / "waterfall_small_multiples.png"
    context_path = output_dir / "waterfall_small_multiples_context.json"
    if not image_path.exists() or not context_path.exists():
        return None
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if context.get("status") != "written":
        return None
    dimension = str(context.get("dimension") or "dimension")
    panels = [
        panel
        for panel in context.get("panels", [])
        if isinstance(panel, dict) and panel.get("dimension_value") is not None
    ]
    items: list[tuple[str, float]] = []
    for panel in panels[:3]:
        dominant = panel.get("dominant_component") or {}
        variance_type = str(dominant.get("variance_type") or "").strip()
        label = str(panel.get("dimension_value") or "").strip()
        if variance_type:
            label = f"{label} / {variance_type}"
        try:
            amount = float(dominant.get("variance_amount") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        items.append((label, amount))
    item_text = _format_label_amounts(items) if items else dimension
    return {
        "dimension": dimension,
        "image_path": image_path,
        "item_text": item_text,
        "title": labels["chart_small_multiples"].format(dimension=dimension),
        "reading": labels["chart_small_multiples_reading"].format(
            dimension=dimension,
            items=item_text,
        ),
        "caption": labels["chart_small_multiples_caption"],
        "source_row": [
            labels["small_multiples_source"],
            labels["small_multiples_reading"],
            item_text,
        ],
    }


def _pvm_ladder_info(
    output_dir: Path,
    labels: dict[str, str],
) -> dict[str, Any] | None:
    """Return client-report metadata for the PVM decomposition ladder."""

    image_path = output_dir / "pvm_decomposition_ladder.png"
    context_path = output_dir / "pvm_decomposition_ladder_context.json"
    if not image_path.exists() or not context_path.exists():
        return None
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    level_three = next(
        (
            level
            for level in context.get("levels", [])
            if isinstance(level, dict) and int(level.get("level") or 0) == 3
        ),
        None,
    )
    components = []
    if isinstance(level_three, dict):
        components = [
            item for item in level_three.get("components", []) if isinstance(item, dict)
        ]
    ranked: list[tuple[str, float]] = []
    for component in components:
        try:
            amount = float(component.get("variance_amount") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if abs(amount) > 0:
            ranked.append((str(component.get("variance_type") or ""), amount))
    ranked.sort(key=lambda item: abs(item[1]), reverse=True)
    item_text = _format_label_amounts(ranked, limit=3) if ranked else ""
    return {
        "image_path": image_path,
        "item_text": item_text,
        "title": labels["chart_pvm_ladder"],
        "reading": labels["chart_pvm_ladder_reading"].format(items=item_text),
        "caption": labels["chart_pvm_ladder_caption"],
        "source_row": [
            labels["pvm_ladder_source"],
            labels["pvm_ladder_reading"],
            item_text,
        ],
    }


def _standard_component_note(
    output_dir: Path,
    labels: dict[str, str],
    comparison: dict[str, str],
) -> str | None:
    """Return a data-driven note about standard variance components."""

    context_path = output_dir / "waterfall_small_multiples_context.json"
    if not context_path.exists():
        return None
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    totals: dict[str, float] = {}
    for panel in context.get("panels", []):
        if not isinstance(panel, dict):
            continue
        for component in panel.get("components", []):
            if not isinstance(component, dict):
                continue
            variance_type = str(component.get("variance_type") or "").strip()
            if not variance_type:
                continue
            try:
                amount = float(component.get("variance_amount") or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            totals[variance_type] = totals.get(variance_type, 0.0) + amount
    if not totals:
        return None
    price_amount = totals.get("Price", 0.0)
    non_price_amount = sum(
        abs(amount)
        for variance_type, amount in totals.items()
        if variance_type not in {"Price", "Other"}
    )
    other_amount = abs(totals.get("Other", 0.0))
    if abs(price_amount) > 0.000001 and non_price_amount <= 0.000001:
        return labels["price_only"].format(**comparison)
    ordered_components = sorted(
        totals.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    dominant_type, dominant_amount = ordered_components[0]
    if other_amount <= 0.000001:
        ordered_components = [item for item in ordered_components if item[0] != "Other"]
    component_text = ", ".join(
        f"{variance_type} {_format_amount(amount)}"
        for variance_type, amount in ordered_components[:4]
    )
    return labels["component_note"].format(
        dominant_type=dominant_type,
        dominant_amount=_format_amount(dominant_amount),
        components=component_text,
    )


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        (
            "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Helvetica.ttf"
        ),
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _draw_segmented_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    segments: tuple[tuple[str, bool], ...],
    *,
    fill: tuple[int, int, int],
    regular_font: ImageFont.ImageFont,
    bold_font: ImageFont.ImageFont,
) -> None:
    """Draw one title line with per-segment emphasis."""

    x, y = xy
    for text, emphasized in segments:
        if not text:
            continue
        font = bold_font if emphasized else regular_font
        draw.text((x, y), text, fill=fill, font=font)
        bbox = draw.textbbox((x, y), text, font=font)
        x += bbox[2] - bbox[0]


def _write_localized_chart(
    source: Path | None,
    target: Path,
    title: str,
    subtitle: str,
    footer: str,
    *,
    title_lines: list[str] | None = None,
) -> Path | None:
    if source is None or not source.exists():
        return None
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, image.width, 128), fill="white")
    if title_lines:
        if title_lines:
            draw.text(
                (58, 24),
                title_lines[0],
                fill=(80, 85, 92),
                font=_load_font(18),
            )
        if len(title_lines) > 1:
            _draw_segmented_text(
                draw,
                (58, 49),
                measure_line_segments(title_lines[1]),
                fill=(34, 40, 49),
                regular_font=_load_font(18),
                bold_font=_load_font(18, bold=True),
            )
        if len(title_lines) > 2:
            draw.text(
                (58, 75),
                title_lines[2],
                fill=(80, 85, 92),
                font=_load_font(17),
            )
    else:
        draw.text((58, 40), title, fill=(34, 40, 49), font=_load_font(34, bold=True))
        draw.text((58, 82), subtitle, fill=(80, 85, 92), font=_load_font(19))
    note_top = image.height - 48
    draw.rectangle((0, note_top, image.width, image.height), fill="white")
    draw.text((58, note_top + 10), footer, fill=(105, 105, 105), font=_load_font(14))
    image.save(target)
    return target


def _set_cell_shading(cell: Any, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _add_docx_table(
    document: Document, headers: list[str], rows: list[list[str]]
) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        cell.text = header
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_shading(cell, "F2F4F7")
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cells[idx].text = value
            cells[idx].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _add_docx_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(9)
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(91, 101, 94)


def _add_docx_chart(
    document: Document,
    title: str,
    reading: str,
    image_path: Path | None,
    caption: str,
    reading_label: str,
    width_inches: float = 6.45,
) -> None:
    document.add_heading(title, level=1)
    paragraph = document.add_paragraph()
    paragraph.add_run(f"{reading_label}: ").bold = True
    paragraph.add_run(reading)
    if image_path is not None and image_path.exists():
        document.add_picture(str(image_path), width=Inches(width_inches))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_docx_caption(document, caption)


def _write_docx(
    output_path: Path,
    payload: dict[str, Any],
    labels: dict[str, str],
) -> None:
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for style_name, size in (("Heading 1", 16), ("Heading 2", 13)):
        style = document.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string("2E74B5")
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(6)
    title = document.add_paragraph()
    title_run = title.add_run(labels["title"])
    title_run.bold = True
    title_run.font.size = Pt(22)
    title_run.font.color.rgb = RGBColor(36, 48, 38)
    subtitle = document.add_paragraph(payload["subtitle"])
    subtitle.runs[0].font.color.rgb = RGBColor(91, 101, 94)
    document.add_heading(labels["summary"], level=1)
    for paragraph in payload["summary_paragraphs"]:
        document.add_paragraph(paragraph)
    document.add_heading(labels["source_data"], level=1)
    _add_docx_table(document, payload["source_headers"], payload["source_rows"])
    _add_docx_caption(document, labels["source_caption"])
    document.add_heading(labels["reading_notes"], level=2)
    for note in payload["notes"]:
        document.add_paragraph(note, style="List Bullet")
    if payload["chart_sections"]:
        document.add_section(WD_SECTION.NEW_PAGE)
    for index, chart_section in enumerate(payload["chart_sections"]):
        if index > 0 and chart_section["page_break_before"]:
            document.add_section(WD_SECTION.NEW_PAGE)
        _add_docx_chart(
            document,
            chart_section["title"],
            chart_section["reading"],
            chart_section["image_path"],
            chart_section["caption"],
            labels["reading"],
            float(chart_section.get("width_inches") or 6.45),
        )
    if payload["drilldown_findings"]:
        document.add_heading(labels["drilldown_findings"], level=1)
        _add_docx_table(
            document,
            [
                labels["analysis_area"],
                labels["useful_reading"],
                labels["source_col"],
            ],
            payload["drilldown_findings"],
        )
        _add_docx_caption(document, labels["drilldown_caption"])
    for section in document.sections:
        header = section.header.paragraphs[0]
        header.text = labels["title"]
        header.runs[0].font.size = Pt(9)
        header.runs[0].font.color.rgb = RGBColor(108, 118, 110)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)


def _write_markdown(
    output_path: Path,
    payload: dict[str, Any],
    labels: dict[str, str],
) -> None:
    lines = [
        f"# {labels['title']}",
        "",
        payload["subtitle"],
        "",
        f"## {labels['summary']}",
        "",
        *payload["summary_paragraphs"],
        "",
        f"## {labels['source_data']}",
        "",
        f"| {' | '.join(payload['source_headers'])} |",
        f"| {' | '.join(['---'] * len(payload['source_headers']))} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in payload["source_rows"])
    lines.extend(["", f"## {labels['reading_notes']}", ""])
    lines.extend(f"- {note}" for note in payload["notes"])
    for chart_section in payload["chart_sections"]:
        lines.extend(
            [
                "",
                f"## {chart_section['title']}",
                "",
                f"**{labels['reading']}**: {chart_section['reading']}",
                "",
            ]
        )
        image_path = chart_section["image_path"]
        if isinstance(image_path, Path) and image_path.exists():
            lines.append(f"![{chart_section['title']}]({image_path.name})")
            lines.append("")
        lines.append(chart_section["caption"])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_payload(
    summary_rows: list[dict[str, Any]],
    recipe: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any] | None:
    language = _language(recipe)
    labels = _text(language)
    comparison = _comparison_metadata(recipe, language)
    summary_row = _select_summary(summary_rows)
    if summary_row is None:
        return None
    pvm_ladder = _pvm_ladder_info(output_dir, labels)
    small_multiples = _small_multiples_info(output_dir, labels)
    summary_alt = int(summary_row.get("alternative_result") or 0)
    summary_labels = _split_summary_values(summary_row.get("selected_labels"))
    summary_label = summary_labels[0] if summary_labels else "Root-cause bridge"
    summary_amounts = _selected_amounts(summary_row)
    summary_amount = summary_amounts[0] if summary_amounts else 0.0
    selected_items = list(zip(summary_labels, summary_amounts))
    selected_text = _format_label_amounts(selected_items, limit=4)
    summary_key_text = (
        selected_text or f"{summary_label} {_format_amount(summary_amount)}"
    )
    driver_count = max(len(summary_labels), len(summary_amounts), 1)
    total_delta = sum(summary_amounts) + _summary_float(summary_row, "other_residual")
    product_items = _best_product_line_items(output_dir, summary_alt, 1)
    top_product = product_items[0][0] if product_items else summary_label
    product_text = _format_label_amounts(product_items)
    mixed_row = _select_mixed(summary_rows)
    mixed_items: list[str] = []
    mixed_chart: Path | None = None
    mixed_residual = 0.0
    if mixed_row is not None:
        mixed_alt = int(mixed_row.get("alternative_result") or 0)
        mixed_bridge_rows = _bridge_rows(output_dir, mixed_alt)
        mixed_items = [_row_label(row) for row in mixed_bridge_rows[:5]]
        mixed_residual = _summary_float(mixed_row, "other_residual")
        mixed_chart = _write_localized_chart(
            _chart_path(output_dir, mixed_row.get("chart_path")),
            output_dir / "root_cause_client_report_mixed_bridge.png",
            labels["chart_mixed_title"],
            labels["chart_mixed_subtitle"].format(**comparison),
            labels["chart_footer"],
            title_lines=build_ibcs_title(
                recipe,
                chart_kind="variable_root_cause",
            ).lines(),
        )
    summary_chart = _write_localized_chart(
        _chart_path(output_dir, summary_row.get("chart_path")),
        output_dir / "root_cause_client_report_summary_bridge.png",
        labels["chart_summary_title"].format(label=summary_label),
        labels["chart_summary_subtitle"].format(**comparison),
        labels["chart_footer"],
        title_lines=build_ibcs_title(
            recipe,
            chart_kind="root_cause",
        ).lines(),
    )
    drilldown_chart = _write_localized_chart(
        output_dir / f"root_cause_bridge_alt_{summary_alt}_drilldown_row_1.png",
        output_dir / "root_cause_client_report_drilldown.png",
        labels["chart_drilldown_title"].format(label=summary_label),
        labels["chart_drilldown_subtitle"].format(**comparison),
        labels["chart_footer"],
        title_lines=build_ibcs_title(
            recipe,
            chart_kind="root_cause_drilldown",
            selection_label=summary_label,
        ).lines(),
    )
    has_drilldown = bool(product_items) or drilldown_chart is not None
    mixed_text = ", ".join(mixed_items) if mixed_items else summary_label
    subtitle = (
        f"{Path(str(recipe.get('source_file') or '')).stem or 'Sales'} | "
        f"{comparison['comparison']}"
    )
    summary_paragraphs = [
        labels["summary_intro"].format(
            delta=_format_amount(total_delta),
            driver_count=driver_count,
            items=summary_key_text,
            residual=_format_residual(summary_row.get("other_residual")),
            **comparison,
        )
    ]
    if has_drilldown:
        summary_paragraphs.append(
            labels["drilldown_intro"].format(
                items=product_text or summary_label,
                top_label=top_product,
            )
        )
    if mixed_row is not None:
        summary_paragraphs.append(
            labels["mixed_intro"].format(
                items=mixed_text,
                residual=_format_residual(mixed_residual),
            )
        )
    source_rows = [
        [
            labels["bridge_summary"],
            labels["bridge_reading"],
            f"{summary_key_text}; {labels['residual']} "
            f"{_format_residual(summary_row.get('other_residual'))}",
        ]
    ]
    if pvm_ladder is not None:
        source_rows.append(pvm_ladder["source_row"])
    if small_multiples is not None:
        source_rows.append(small_multiples["source_row"])
    if has_drilldown:
        source_rows.append(
            [
                labels["product_line_drilldown"],
                labels["drilldown_reading"],
                product_text,
            ]
        )
    if mixed_row is not None:
        source_rows.append(
            [
                labels["mixed_deep_dive"],
                labels["mixed_reading"],
                mixed_text,
            ]
        )
    chart_sections = []
    if pvm_ladder is not None:
        chart_sections.append(
            {
                "title": pvm_ladder["title"],
                "reading": pvm_ladder["reading"],
                "image_path": pvm_ladder["image_path"],
                "caption": pvm_ladder["caption"],
                "page_break_before": False,
                "width_inches": 6.2,
            }
        )
    if small_multiples is not None:
        chart_sections.append(
            {
                "title": small_multiples["title"],
                "reading": small_multiples["reading"],
                "image_path": small_multiples["image_path"],
                "caption": small_multiples["caption"],
                "page_break_before": False,
                "width_inches": 5.9,
            }
        )
    chart_sections.append(
        {
            "title": labels["chart_1"],
            "reading": labels["chart_1_reading"].format(
                items=summary_key_text,
                residual=_format_residual(summary_row.get("other_residual")),
                **comparison,
            ),
            "image_path": summary_chart,
            "caption": labels["chart_1_caption"],
            "page_break_before": False,
        }
    )
    if has_drilldown:
        chart_sections.append(
            {
                "title": labels["chart_2"],
                "reading": labels["chart_2_reading"].format(top_label=top_product),
                "image_path": drilldown_chart,
                "caption": labels["chart_2_caption"],
                "page_break_before": False,
            }
        )
    if mixed_row is not None:
        chart_sections.append(
            {
                "title": labels["chart_3"],
                "reading": labels["chart_3_reading"].format(items=mixed_text),
                "image_path": mixed_chart,
                "caption": labels["chart_3_caption"],
                "page_break_before": True,
            }
        )
    component_note = _standard_component_note(output_dir, labels, comparison)
    notes = [_currency_note(recipe, labels)]
    if component_note:
        notes.append(component_note)
    notes.append(labels["residual_note"])
    payload = {
        "labels": labels,
        "subtitle": subtitle,
        "summary_paragraphs": summary_paragraphs,
        "source_headers": [
            labels["source_col"],
            labels["reading"],
            labels["data_key"],
        ],
        "source_rows": source_rows,
        "notes": notes,
        "chart_sections": chart_sections,
        "drilldown_findings": _drilldown_finding_rows(output_dir, mixed_row, labels),
    }
    return payload


def write_root_cause_client_report(
    *,
    summary_rows: list[dict[str, Any]],
    recipe: dict[str, Any],
    output_dir: Path,
) -> tuple[list[str], dict[str, Any]]:
    """Write client-ready Markdown and DOCX root-cause reports."""

    payload = _build_payload(summary_rows, recipe, output_dir)
    if payload is None:
        return [], {"status": "not_written_no_summary_rows"}
    labels = payload["labels"]
    md_path = output_dir / "root_cause_client_report.md"
    docx_path = output_dir / "root_cause_client_report.docx"
    _write_markdown(md_path, payload, labels)
    _write_docx(docx_path, payload, labels)
    paths = [str(md_path), str(docx_path)]
    for chart_section in payload["chart_sections"]:
        chart = chart_section["image_path"]
        if isinstance(chart, Path) and chart.exists():
            paths.append(str(chart))
    chart_artifacts = [
        Path(path).name
        for path in paths
        if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    return paths, {
        "status": "written",
        "markdown": md_path.name,
        "docx": docx_path.name,
        "selected_row_count": len(payload["source_rows"]),
        "drilldown_finding_count": len(payload["drilldown_findings"]),
        "chart_artifacts": chart_artifacts,
        "pvm_decomposition_ladder_chart_included": any(
            artifact == "pvm_decomposition_ladder.png" for artifact in chart_artifacts
        ),
        "small_multiples_chart_included": any(
            artifact == "waterfall_small_multiples.png" for artifact in chart_artifacts
        ),
    }
