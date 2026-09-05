"""Shared report presentation with mechanically checked figure/source bindings.

Authors choose useful comparisons and decision criteria. Code only checks their
references and arithmetic and renders the same material in HTML and PDF.
"""

from __future__ import annotations

import html
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlsplit

from planning_workflow import indexed, number, require

__all__ = [
    "language",
    "label",
    "format_number",
    "validate_presentation",
    "render_tables",
    "render_actions",
    "render_sources",
]

ITALIAN = {
    "Business plan": "Business plan",
    "Audience": "Destinatari",
    "internal": "Uso interno",
    "Recommendation": "Raccomandazione",
    "Proceed": "Procedere",
    "Test": "Testare prima del lancio",
    "Redesign": "Riprogettare",
    "Stop": "Fermarsi",
    "What this judgment depends on": "Condizioni per proseguire",
    "What would change the recommendation": "Quali prove cambierebbero la decisione",
    "The business and its customers": "Prodotto e clienti",
    "Demand and route to market": "Domanda e canali di vendita",
    "How the business would operate": "Produzione, persone e operazioni",
    "Prices, costs and sustainable sales": "Prezzi, costi e redditività",
    "Cash, investment and financing": "Cassa e finanziamento",
    "Alternatives worth considering": "Alternative realistiche",
    "What to do next": "Prossimi passi e responsabilità",
    "Material uncertainties and limitations": "Incertezze rilevanti per la decisione",
    "Provisional assessment. Material evidence or review remains open; this is not a finalized business plan.": "Valutazione provvisoria per discussione: restano dati o verifiche aperte. Non è un piano approvato per investire o richiedere credito.",
    "Basis and review": "Fonti e stato di revisione",
    "Provisional interpretation — professional review pending": "Interpretazione provvisoria; revisione professionale da acquisire",
    "Reviewed interpretation": "Interpretazione revisionata",
    "Sources and calculation references": "Fonti e riferimenti ai calcoli",
    "Source": "Fonte",
    "Reference": "Riferimento",
    "Claim / use": "Affermazione / utilizzo",
    "Location": "Pagina o celle",
    "Not specified": "Non specificato",
    "Action": "Azione",
    "Owner": "Responsabile",
    "When": "Quando",
    "Evidence / decision criterion": "Prova / criterio di decisione",
    "Supporting evidence, calculations and review record": "Appendice tecnica: evidenze, calcoli e verifiche",
    "Chart data and calculation lineage": "Dati del grafico e riferimenti ai calcoli",
    "Month": "Mese",
    "Series": "Serie",
    "Calculation ID": "Riferimento di calcolo",
    "Before new financing": "Prima dei nuovi fondi",
    "After scheduled financing": "Dopo i fondi ipotizzati",
    "EBITDA by scenario": "EBITDA mensile per scenario",
    "Monthly cash": "Cassa mensile",
    "Calculation": "Calcolo",
    "Source observation": "Dato riportato dalla fonte",
    "Sum": "Somma",
    "Ratio": "Rapporto",
    "Draft for discussion": "Bozza per discussione",
    "Page": "Pagina",
}


def language(case: dict[str, Any]) -> str:
    """Use an explicit presentation language, never infer locale from client data."""
    return case.get("presentation", {}).get("language", "en")


def label(text: str, lang: str) -> str:
    return ITALIAN.get(text, text) if lang == "it" else text


def format_number(
    value: Any, lang: str, decimals: int = 0, style: str = "number"
) -> str:
    amount = number(format(Decimal(str(value)), "f")) * (
        100 if style == "percent" else 1
    )
    rendered = f"{amount:,.{decimals}f}"
    if lang == "it":
        rendered = rendered.translate(str.maketrans({",": ".", ".": ","}))
    return rendered + ("%" if style == "percent" else "")


def _cell_value(cell: dict[str, Any], plan: dict[str, Any]) -> tuple[Decimal, str]:
    """Check exact proposed values against canonical figures or source observations."""
    if "observation_id" in cell:
        observations = {r["id"]: r for r in plan["case"]["observations"]}
        require(cell["observation_id"] in observations, "Unknown table observation")
        require(
            "operation" not in cell, "Observation cells cannot specify an operation"
        )
        row = observations[cell["observation_id"]]
        return number(row["value"]), row["unit"]
    ids = cell.get("calculation_ids", [])
    require(
        isinstance(ids, list) and bool(ids) and len(ids) == len(set(ids)),
        "Table calculation IDs must be unique and nonempty",
    )
    calcs = plan["calculations"]
    require(
        all(i in calcs and calcs[i]["value"] is not None for i in ids),
        "Table calculation unavailable",
    )
    rows = [calcs[i] for i in ids]
    require(len({r["unit"] for r in rows}) == 1, "Table calculation units differ")
    operation = cell.get("operation", "value")
    require(
        operation in {"value", "sum", "ratio", "difference"}, "Unknown table operation"
    )
    require(operation != "value" or len(rows) == 1, "Value cell needs one calculation")
    if operation == "ratio":
        require(
            len(rows) == 2 and number(rows[1]["value"]) != 0,
            "Ratio needs two values and a nonzero denominator",
        )
        return number(rows[0]["value"]) / number(rows[1]["value"]), "ratio"
    if operation == "difference":
        require(len(rows) >= 2, "Difference needs at least two values")
        return (
            number(rows[0]["value"])
            - sum((number(r["value"]) for r in rows[1:]), Decimal(0)),
            rows[0]["unit"],
        )
    return sum((number(r["value"]) for r in rows), Decimal(0)), rows[0]["unit"]


def validate_presentation(plan: dict[str, Any]) -> None:
    """Reject broken bindings and unsafe links, not provisional business judgment."""
    p = plan["case"].get("presentation", {})
    require(
        isinstance(p, dict)
        and set(p) <= {"language", "tables", "actions", "source_notes"},
        "Unexpected presentation fields",
    )
    require(language(plan["case"]) in {"en", "it"}, "Unsupported report language")
    from planning_assessment import SECTIONS

    narrative = {n["id"] for n in plan["accepted_narrative"]}
    tables = indexed(p.get("tables", []), "presentation table")
    for table in tables.values():
        require(
            set(table) <= {"id", "title", "section", "headers", "rows", "caption_id"},
            "Unexpected table fields",
        )
        require(
            table.get("section") in SECTIONS and bool(table.get("title")),
            "Table needs a title and business section",
        )
        headers = table.get("headers")
        require(
            isinstance(headers, list)
            and 1 <= len(headers) <= 8
            and all(isinstance(h, str) and h for h in headers),
            "Table requires readable column headings",
        )
        require(
            isinstance(table.get("rows"), list) and bool(table["rows"]),
            "Table requires rows",
        )
        require(
            table.get("caption_id") in narrative,
            "Table needs an available narrative explaining scope and assumptions",
        )
        for row in table["rows"]:
            require(
                isinstance(row, list) and len(row) == len(headers),
                "Table row width differs",
            )
            for cell in row:
                require(isinstance(cell, dict), "Table cells must be typed")
                if "text" in cell:
                    require(
                        set(cell) == {"text"} and isinstance(cell["text"], str),
                        "Text cells contain labels only",
                    )
                    continue
                require(
                    set(cell)
                    <= {
                        "observation_id",
                        "calculation_ids",
                        "operation",
                        "value",
                        "decimals",
                        "style",
                    },
                    "Unexpected numeric cell fields",
                )
                require(
                    ("observation_id" in cell) != ("calculation_ids" in cell),
                    "Choose one table figure source",
                )
                require(
                    isinstance(cell.get("decimals", 0), int)
                    and 0 <= cell.get("decimals", 0) <= 4,
                    "Invalid table precision",
                )
                require(
                    cell.get("style", "number") in {"number", "percent"},
                    "Unknown number style",
                )
                amount, unit = _cell_value(cell, plan)
                require(
                    "value" in cell and amount == number(cell["value"]),
                    "Table figure disagrees with its source calculations",
                )
                require(
                    cell.get("style") != "percent" or unit == "ratio",
                    "Percent formatting requires a ratio",
                )
    require(isinstance(p.get("actions", []), list), "Actions must be a list")
    for action in p.get("actions", []):
        require(isinstance(action, dict), "Action must be an object")
        require(
            set(action) == {"action_id", "owner", "when", "criterion_id"},
            "Unexpected action fields",
        )
        require(
            action["action_id"] in narrative and action["criterion_id"] in narrative,
            "Action references unavailable narrative",
        )
        require(
            all(
                isinstance(action[k], str) and action[k].strip()
                for k in ("owner", "when")
            ),
            "Action needs a responsible role and timing",
        )
    sources = {s["id"] for s in plan["case"]["sources"]}
    require(isinstance(p.get("source_notes", []), list), "Source notes must be a list")
    for note in p.get("source_notes", []):
        require(isinstance(note, dict), "Source note must be an object")
        require(
            set(note) <= {"source_id", "claim", "locator", "url"},
            "Unexpected source note fields",
        )
        require(note.get("source_id") in sources, "Unknown cited source")
        require(
            all(
                isinstance(note.get(k), str) and note[k].strip()
                for k in ("claim", "locator")
            ),
            "Source note needs a claim and locator",
        )
        if "url" in note:
            require(isinstance(note["url"], str), "Source URL must be text")
            url = urlsplit(note["url"])
            require(
                url.scheme in {"https", "http"}
                and bool(url.hostname)
                and not url.username
                and not url.password,
                "Source URL must be an HTTP(S) reference without credentials",
            )


def render_tables(
    plan: dict[str, Any], section: str, render_paragraph: Callable[[str], str]
) -> str:
    """Render author-selected comparisons without a case-specific HTML wrapper."""
    from planning_report import _table

    lang = language(plan["case"])
    output = []
    for table in plan["case"].get("presentation", {}).get("tables", []):
        if table["section"] != section:
            continue
        rows = []
        for row in table["rows"]:
            cells = []
            for cell in row:
                if "text" in cell:
                    cells.append(cell["text"])
                else:
                    amount, _ = _cell_value(cell, plan)
                    cells.append(
                        format_number(
                            str(amount),
                            lang,
                            cell.get("decimals", 0),
                            cell.get("style", "number"),
                        )
                    )
            rows.append(cells)
        output.append(
            f'<div class="decision-table" id="table-{html.escape(table["id"])}"><h3>{html.escape(table["title"])}</h3>{_table(table["headers"], rows)}{render_paragraph(table["caption_id"])}</div>'
        )
    return "".join(output)


def render_actions(plan: dict[str, Any], render_paragraph: Callable[[str], str]) -> str:
    lang = language(plan["case"])
    actions = plan["case"].get("presentation", {}).get("actions", [])
    if not actions:
        return ""
    heads = ["Action", "Owner", "When", "Evidence / decision criterion"]
    output = [
        '<div class="action-table"><table><thead><tr>'
        + "".join(f"<th>{label(h, lang)}</th>" for h in heads)
        + "</tr></thead><tbody>"
    ]
    for a in actions:
        output.append(
            f'<tr><td>{render_paragraph(a["action_id"])}</td><td>{html.escape(a["owner"])}</td><td>{html.escape(a["when"])}</td><td>{render_paragraph(a["criterion_id"])}</td></tr>'
        )
    return "".join(output) + "</tbody></table></div>"


def render_sources(plan: dict[str, Any]) -> str:
    """Keep filenames, locators and used figure methods readable in standalone PDF."""
    from planning_report import _table

    case = plan["case"]
    lang = language(case)
    e = html.escape
    sources = {s["id"]: s for s in case["sources"]}
    notes = case.get("presentation", {}).get("source_notes", [])
    rows = []
    for source in sources.values():
        matching = [n for n in notes if n["source_id"] == source["id"]]
        if not matching:
            matching = [
                {
                    "claim": label("Not specified", lang),
                    "locator": label("Not specified", lang),
                }
            ]
        for note in matching:
            rows.append(
                [
                    source["id"]
                    + ": "
                    + source["path"].replace("\\", "/").rsplit("/", 1)[-1]
                    + " — "
                    + source["version"],
                    note["claim"],
                    note["locator"],
                ]
            )
    output = [
        f'<section id="reader-sources"><h2>{label("Sources and calculation references", lang)}</h2>',
        _table([label(h, lang) for h in ("Source", "Claim / use", "Location")], rows),
    ]
    for note in notes:
        if note.get("url"):
            output.append(
                f'<p><a href="{e(note["url"], quote=True)}">{e(note["claim"])}</a><br><span class="source-url">{e(note["url"])}</span></p>'
            )
    used: dict[str, dict[str, Any]] = {}
    for entry in plan["accepted_narrative"]:
        for claim in entry["claims"].values():
            if "calculation_id" in claim:
                used[claim["calculation_id"]] = plan["calculations"][
                    claim["calculation_id"]
                ]
    for table in case.get("presentation", {}).get("tables", []):
        for row in table["rows"]:
            for cell in row:
                for cid in cell.get("calculation_ids", []):
                    used[cid] = plan["calculations"][cid]
    bindings = []
    observations = {o["id"]: o for o in case["observations"]}
    for table in case.get("presentation", {}).get("tables", []):
        for index, row in enumerate(table["rows"], 1):
            for header, cell in zip(table["headers"], row):
                if "text" in cell:
                    continue
                if "observation_id" in cell:
                    obs = observations[cell["observation_id"]]
                    reference = (
                        label("Source observation", lang)
                        + ": "
                        + obs["id"]
                        + " ("
                        + obs["basis"]
                        + ")"
                    )
                else:
                    ids = cell["calculation_ids"]
                    reference = cell.get("operation", "value") + ": " + "; ".join(ids)
                    if len(ids) > 2 and cell.get("operation") == "sum":
                        reference = (
                            label("Sum", lang)
                            + ": "
                            + ids[0]
                            + " … "
                            + ids[-1]
                            + " ("
                            + str(len(ids))
                            + ")"
                        )
                bindings.append(
                    [
                        table["title"] + " / " + str(index) + " / " + header,
                        format_number(
                            cell["value"],
                            lang,
                            cell.get("decimals", 0),
                            cell.get("style", "number"),
                        ),
                        reference,
                    ]
                )
    if bindings:
        output.append(
            _table(
                [
                    label("Reference", lang),
                    case["reporting_currency"] or "Value",
                    label("Calculation", lang),
                ],
                bindings,
            )
        )
    if used:
        # One method per metric, sharing scenario/period coverage rather than
        # repeating the same filenames and formula for every scenario.
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for c in used.values():
            key = (c["metric"], c["formula"], ", ".join(c["source_ids"]))
            groups.setdefault(key, []).append(c)
        methods = []
        for (metric, formula, ids), values in groups.items():
            periods = sorted({v["period"] for v in values})
            scenarios = ", ".join(sorted({v["scenario"] for v in values}))
            methods.append(
                [
                    metric + " / " + scenarios,
                    periods[0] + " — " + periods[-1],
                    formula,
                    ids,
                ]
            )
        output.append(
            _table(
                [
                    label("Calculation", lang),
                    label("When", lang),
                    label("Reference", lang),
                    label("Source", lang),
                ],
                methods,
            )
        )
    return "".join(output) + "</section>"
