"""Present precomputed budget comparisons through the shared reporting renderer."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from reporting_table import render_reporting_table

__all__ = ["render_budget_comparisons"]

LINES = (
    ("revenue", "Ricavi", "Revenue"),
    ("cogs", "Costo del venduto", "Cost of sales"),
    ("gross_profit", "Margine lordo", "Gross profit"),
    ("operating_expense", "Costi operativi", "Operating expenses"),
    (
        "other_operating",
        "Altri proventi/oneri operativi",
        "Other operating income/expense",
    ),
    ("ebitda", "EBITDA", "EBITDA"),
    ("depreciation_amortization", "Ammortamenti", "Depreciation and amortization"),
    ("ebit", "EBIT", "EBIT"),
    ("interest", "Oneri finanziari", "Interest expense"),
    ("tax", "Imposte", "Tax"),
    ("other", "Altri proventi/oneri", "Other income/expense"),
    ("net_result", "Risultato netto", "Net result"),
)
COSTS = {"cogs", "operating_expense", "depreciation_amortization", "interest", "tax"}
TOTALS = {"gross_profit", "ebitda", "ebit", "net_result"}


def render_budget_comparisons(pack: Mapping[str, Any]) -> str:
    """Select compiled views without changing numbers, signs, units or scales."""
    section = pack["sections"]["budget_variance"]
    language = pack.get("language", "en")
    italian = language == "it"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in section.get("comparison_rows", []):
        grouped[row["view"]].append(row)
    if not grouped:
        return ""
    labels = {key: it if italian else en for key, it, en in LINES}
    rendered_rows: dict[str, list[dict[str, Any]]] = {}
    for view, values in grouped.items():
        by_metric = {row["metric"]: row for row in values}
        rows = []
        for key, _, _ in LINES:
            row = by_metric[key]
            multiplier = -1 if key in COSTS else 1
            rows.append(
                {
                    "row_label": labels[key],
                    "baseline_value": str(Decimal(row["baseline"]) * multiplier),
                    "comparison_value": str(Decimal(row["comparison"]) * multiplier),
                    "absolute_variance": str(Decimal(row["variance"]) * multiplier),
                    "relative_variance": row["variance_pct"],
                    "favorable_direction": "lower" if key in COSTS else "higher",
                    "row_type": "subtotal" if key in TOTALS else "detail",
                }
            )
        rendered_rows[view] = rows
    scale_rows = [row for rows in rendered_rows.values() for row in rows]
    views = sorted(
        grouped, key=lambda view: (view != "total", view == "forecast", view)
    )
    titles = {
        "total": (
            "Progressivo al " + pack["reporting_period"]["cutoff"]
            if italian
            else "Actuals to " + pack["reporting_period"]["cutoff"]
        ),
        "forecast": "Previsione a fine periodo" if italian else "Full-period forecast",
    }
    buttons = []
    figures = []
    for view in views:
        title = titles.get(view, view)
        scenario = grouped[view][0]["scenario"]
        buttons.append(
            f'<button type="button" data-budget-select="{escape(view)}" aria-controls="budget-{escape(view)}" aria-pressed="false">{escape(title)}</button>'
        )
        figure = render_reporting_table(
            row_header="Voce" if italian else "Line item",
            rows=rendered_rows[view],
            baseline_label="PL · Budget",
            comparison_label="FC · Forecast" if scenario == "FC" else "AC · Actual",
            entity_label=str(pack["entity"]),
            comparison_caption=title,
            metric=("Conto economico" if italian else "Profit and loss")
            + " · "
            + pack["currency"],
            source_label=(
                "Export e mappatura verificati"
                if italian
                else "Reviewed exports and mapping"
            ),
            language=language,
            fragment=True,
            row_label_width=260,
            scale_rows=scale_rows,
            value_scale=1,
            value_width=112,
        )
        figures.append(
            f'<div id="budget-{escape(view)}" data-budget-view="{escape(view)}">{figure}</div>'
        )
    note = (
        "Δ = scenario − budget. Costi esposti positivi; una riduzione è favorevole. Δ% = Δ / budget × 100; n/d con base zero o negativa. FC = consuntivi fino al cutoff + stime dei mesi successivi. Le selezioni mantengono unità e scale comuni."
        if italian
        else "Δ = scenario − budget. Costs are displayed positive; a reduction is favorable. Δ% = Δ / budget × 100; n/a for zero or negative bases. FC = actuals to cutoff + reviewed remaining-month estimates. Views share units and scales."
    )
    if "forecast" in grouped:
        note += " " + section["forecast_basis"]
    limitations = "".join(
        f"<li>{escape(reason)}</li>" for reason in section.get("limitations", [])
    )
    assets = Path(__file__).resolve().parent.parent / "assets"
    css = (assets / "budget-report.css").read_text(encoding="utf-8")
    script = (assets / "budget-report.js").read_text(encoding="utf-8")
    heading = (
        "Consuntivo, budget e forecast" if italian else "Actual, budget and forecast"
    )
    print_label = "Stampa / PDF" if italian else "Print / PDF"
    return f'<section class="budget-report"><style>{css}</style><p class="eyebrow">PL · AC · FC</p><h2>{heading}</h2><p>{escape(note)}</p><div class="budget-controls" hidden>{"".join(buttons)}<button type="button" data-budget-print>{print_label}</button></div>{"".join(figures)}<ul>{limitations}</ul><script>{script}</script></section>'
