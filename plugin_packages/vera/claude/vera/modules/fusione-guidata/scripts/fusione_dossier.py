"""Readable, escaped P1 workpapers and dossiers from scoped persisted case records."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

__all__ = ["write_workpapers"]

LABELS = {
    "BranchDecision": "Perimetro dell'incorporazione",
    "Valuation": "Valutazione e ponte all'equity",
    "ExchangeModel": "Concambio e assegnazioni",
    "BookBridge": "Ponte contabile e valori fiscali",
    "Deadline": "Calendario per eventi",
    "LegalDocument": "Dossier di revisione",
}


def cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "—" if value is None else str(value)


def render(value: Any, depth: int = 3) -> tuple[str, str]:
    """Render nested evidence without executing model-authored HTML or Markdown."""
    if isinstance(value, dict):
        md, markup = [], []
        for key, entry in value.items():
            title = key.replace("_", " ")
            inner_md, inner_html = render(entry, min(depth + 1, 6))
            md.extend(["#" * depth + " " + title, "", inner_md, ""])
            markup.append(f"<h{depth}>{html.escape(title)}</h{depth}>{inner_html}")
        return "\n".join(md), "".join(markup)
    if (
        isinstance(value, list)
        and value
        and all(isinstance(row, dict) for row in value)
    ):
        keys = list(dict.fromkeys(key for row in value for key in row))
        md = [
            "| " + " | ".join(keys) + " |",
            "| " + " | ".join("---" for _ in keys) + " |",
        ]
        rows = []
        for row in value:
            values = [cell(row.get(key)) for key in keys]
            md.append(
                "| "
                + " | ".join(v.replace("|", "\\|").replace("\n", " ") for v in values)
                + " |"
            )
            rows.append(
                "<tr>"
                + "".join("<td>" + html.escape(v) + "</td>" for v in values)
                + "</tr>"
            )
        table = (
            "<div class='table'><table><thead><tr>"
            + "".join("<th>" + html.escape(k.replace("_", " ")) + "</th>" for k in keys)
            + "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
        return "\n".join(md), table
    text = cell(value)
    return text, "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"


def write_workpapers(report: dict[str, Any], destination: Path) -> dict[str, str]:
    """Write both human-readable formats; never treat an exported draft as a filing."""
    items = [
        row
        for row in report["records"]
        if row["record"]["data"].get("engine_version") == "fusione.p1.v1"
    ]
    if not items:
        return {}
    title = "Fusione guidata · P1 — fascicolo di revisione"
    boundary = (
        "DATI INTERAMENTE SINTETICI"
        if report["synthetic"]
        else "Bozza per revisione professionale"
    )
    md = [
        "# " + title,
        "",
        boundary,
        "",
        "Le conferme valgono per la versione e l'ambito registrati. Nessuna firma, deposito o efficacia giuridica è attestata.",
        "",
    ]
    sections = []
    for item in items:
        row, status = item["record"], item["status"]
        heading = LABELS[row["kind"]] + " · " + row["id"]
        state = f"Versione {row['version']} · {status['review_state']}"
        issues = (
            "; ".join(status["issues"])
            or "Nessuna eccezione strutturale rilevata; revisione professionale secondo lo stato indicato."
        )
        body_md, body_html = render(
            row["data"]["result"]
            if row["data"]["result"] is not None
            else {"risultato": "Non calcolato", "problemi": row["data"]["issues"]}
        )
        md.extend(
            [
                "## " + heading,
                "",
                state,
                "",
                issues,
                "",
                body_md,
                "",
                "Riferimenti esatti: "
                + json.dumps(row["dependencies"], ensure_ascii=False),
                "",
            ]
        )
        sections.append(
            "<section><h2>"
            + html.escape(heading)
            + "</h2><p class='state'>"
            + html.escape(state)
            + "</p><p>"
            + html.escape(issues)
            + "</p>"
            + body_html
            + "<details><summary>Versioni e impronte delle fonti</summary><pre>"
            + html.escape(json.dumps(row["dependencies"], indent=2))
            + "</pre></details></section>"
        )
    disclosure = "Il runtime Claude o Cowork può leggere identità, documenti selezionati, saldi, valori, soci, bozze, fonti e conferme necessari al lavoro. Il programma non osserva il contesto del modello: per i casi reali l'esposizione resta non misurabile. Non è applicata anonimizzazione automatica. Il report dati locale è disponibile accanto al fascicolo."
    md += ["## Quali dati arrivano al modello", "", disclosure]
    markdown = destination / "p1-workpapers.md"
    markdown.write_text("\n".join(md) + "\n", encoding="utf-8")
    stylesheet = "body{font:17px/1.6 system-ui,sans-serif;color:#16233b;background:#fff;margin:0}main{max-width:1100px;margin:auto;padding:36px 24px}h1,h2{color:#002060;line-height:1.2}h1{font-size:36px}h2{font-size:27px}h3,h4,h5,h6{font-size:18px;margin:24px 0 8px}section{padding:28px 0;border-top:1px solid #dbe2ed}.state{color:#0070c0}p,td{overflow-wrap:anywhere}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #dbe2ed}th{color:#002060}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}details{margin-top:20px}a{color:#0070c0}@media print{main{max-width:none;padding:0}details{display:none}.table{overflow:visible}section{break-inside:auto}}"
    page = (
        "<!doctype html><html lang='it'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'none'\"><title>"
        + title
        + "</title><style>"
        + stylesheet
        + "</style><main><h1>"
        + title
        + "</h1><p>"
        + boundary
        + "</p><p>Le conferme valgono per la versione e l'ambito registrati. Nessuna firma, deposito o efficacia giuridica è attestata.</p>"
        + "".join(sections)
        + "<section><h2>Quali dati arrivano al modello</h2><p>"
        + disclosure
        + "</p><a href='model_data_report.md'>Report dati locale</a></section></main></html>"
    )
    target = destination / "p1-workpapers.html"
    target.write_text(page, encoding="utf-8")
    return {"workpapers": str(markdown), "review_html": str(target)}
