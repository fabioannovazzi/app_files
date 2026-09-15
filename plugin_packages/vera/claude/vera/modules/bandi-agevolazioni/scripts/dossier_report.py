"""Present validated dossier records as a local, source-linked review report."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

__all__ = ["render_dossier_html"]

LABELS_PATH = Path(__file__).resolve().parents[1] / "assets" / "dossier-labels.json"
CSS = """
:root{color-scheme:light;--ink:#172b43;--muted:#526477;--blue:#125b94;--rule:#dce3ea}
*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:white;color:var(--ink);font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1100px;margin:auto;padding:44px 56px 72px}a{color:var(--blue);text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid #1889c9;outline-offset:4px}
header{border-top:5px solid var(--blue);padding-top:26px;margin-bottom:24px}.brand{font-weight:700;letter-spacing:.08em;font-size:13px;text-transform:uppercase;color:var(--blue)}h1{font-size:38px;line-height:1.15;letter-spacing:-.035em;margin:12px 0 20px}h2{font-size:24px;line-height:1.3;margin:0 0 16px}h3{font-size:18px;line-height:1.4;margin:10px 0}h4{font-size:16px;margin:16px 0 8px}p{margin:0 0 14px;overflow-wrap:anywhere}.subtitle{font-size:20px;max-width:850px}.notice,.muted{color:var(--muted)}.notice{font-size:14px}.status{font-weight:650;color:var(--blue);margin-top:16px}nav{display:flex;flex-wrap:wrap;gap:12px 25px;padding:17px 0;border-block:1px solid var(--rule);margin:24px 0 32px}nav a{text-decoration:none;font-size:14px;font-weight:600}
section{margin-top:36px;padding-top:30px;border-top:1px solid var(--rule)}section:first-of-type{padding-top:0;border-top:0}.lead{font-size:18px;max-width:900px}.scope{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,3fr);gap:10px 24px;margin:0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;table-layout:fixed}th{text-align:left;font-size:13px;color:var(--muted);font-weight:650;padding:12px 10px;border-bottom:2px solid var(--rule)}td{vertical-align:top;border-bottom:1px solid var(--rule);padding:15px 10px;overflow-wrap:anywhere}.cost-table th:first-child{width:36%}.cost-table th:nth-child(2){width:19%}.cost-table th:nth-child(3){width:25%}.amount{font-variant-numeric:tabular-nums;white-space:nowrap}.small{font-size:13px}details{border-bottom:1px solid var(--rule);padding:14px 0}summary{cursor:pointer;line-height:1.5;font-weight:600;overflow-wrap:anywhere}summary .code{font-weight:400;font-size:12px;color:var(--muted);display:block;margin:0 0 3px 17px}details>div{padding:14px 0 4px 20px}td details{border:0;padding:8px 0 0}td details>div{padding:10px 0 0}td summary{font-size:13px;font-weight:500}.record{margin:0 0 22px}.record:last-child{margin-bottom:0}.meta{display:flex;gap:8px 24px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:10px 0}.refs{font-size:13px;margin:8px 0 16px}.refs a{margin-right:12px}blockquote{margin:12px 0;padding:8px 18px;border-left:3px solid #aec7dc;background:#f7f9fb;white-space:pre-wrap;overflow-wrap:anywhere}.narrative{white-space:pre-wrap}code,pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}pre{padding:12px;background:#f7f9fb}ul{padding-left:20px}.sources article{padding:12px 0 22px}footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--rule);font-size:13px;color:var(--muted)}
@media(max-width:700px){main{padding:24px 20px 40px}h1{font-size:30px}.scope{grid-template-columns:1fr;gap:2px}dd{margin-bottom:12px}th,td{padding:10px 5px;font-size:13px}.amount{white-space:normal}.cost-table th:first-child{width:30%}.cost-table th:nth-child(2){width:22%}.cost-table th:nth-child(3){width:25%}}
@media print{main{max-width:none;padding:0;font-size:10pt}nav{display:none}h1{font-size:26pt}h2{font-size:16pt}section{margin-top:20px;padding-top:18px}details,article{break-inside:avoid}a{color:inherit}body{color:black}.notice{font-size:9pt}}
"""


def _text(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _e(value: object) -> str:
    return escape(_text(value), quote=True)


def _anchor(value: object) -> str:
    return "record-" + quote(str(value), safe="")


def _money(value: object, currency: object, language: str) -> str:
    if value in (None, ""):
        return "—"
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return _text(value)
        number = f"{amount:,.2f}"
    except InvalidOperation:
        return _text(value)
    if language in {"it", "de", "es"}:
        number = number.translate(str.maketrans({",": ".", ".": ","}))
    elif language == "fr":
        number = number.translate(str.maketrans({",": "\u202f", ".": ","}))
    return f"{number} {currency or ''}".strip()


def render_dossier_html(
    *,
    intake: dict[str, Any],
    sources: dict[str, Any],
    workbench: dict[str, Any],
    run_state: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    """Render recorded content without inferring eligibility or review decisions."""
    translations = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    requested_language = str(run_state.get("language", "it")).lower().split("-")[0]
    language = requested_language if requested_language in translations else "en"
    labels: dict[str, str] = translations[language]

    def label(value: object) -> str:
        return labels.get(str(value), _text(value))

    def refs(values: Iterable[object]) -> str:
        links = " ".join(
            f'<a href="#{_anchor(value)}">{_e(value)}</a>' for value in values
        )
        return f'<p class="refs">{links}</p>' if links else ""

    def paragraph(value: object, class_name: str = "") -> str:
        return f'<p class="{class_name}">{_e(value)}</p>'

    def metadata(item: dict[str, Any]) -> str:
        values = [
            f"{labels[heading]}: {label(item[key])}"
            for key, heading in (
                ("readiness", "readiness"),
                ("review_status", "review"),
            )
            if item.get(key)
        ]
        return (
            '<div class="meta">'
            + "".join(f"<span>{_e(v)}</span>" for v in values)
            + "</div>"
        )

    def section(key: str, body: str) -> str:
        return f'<section id="{key}"><h2>{_e(label(key))}</h2>{body}</section>'

    def detail(
        item: dict[str, Any], id_key: str, title: object, body: str, *, suffix: str = ""
    ) -> str:
        return (
            f'<details id="{_anchor(item[id_key])}{suffix}"><summary>'
            f'<span class="code">{_e(item[id_key])}</span>{_e(title)}</summary>'
            f"<div>{body}</div></details>"
        )

    def empty() -> str:
        return paragraph(labels["empty"], "muted")

    application, applicant, project = (
        intake[key] for key in ("application", "applicant", "project")
    )
    body = [
        '<header><p class="brand">Vera</p>',
        f'<h1>{_e(labels["title"])}</h1>',
        paragraph(application.get("title"), "subtitle"),
        paragraph(applicant.get("legal_name")),
        paragraph(labels["review_notice"], "notice"),
        paragraph(label(workbench["dossier"]["disposition"]), "status"),
        '</header><nav aria-label="Dossier">',
        *[
            f'<a href="#{key}">{_e(labels[key])}</a>'
            for key in (
                "summary",
                "costs",
                "documents",
                "requirements",
                "narratives",
                "sources",
            )
        ],
        "</nav>",
        section(
            "summary",
            paragraph(workbench.get("case_summary") or labels["not_provided"], "lead"),
        ),
    ]
    scope_rows = [
        ("question", intake.get("professional_question")),
        ("reference_date", intake.get("reference_date")),
        ("project", project.get("title")),
        (
            "requested_amount",
            _money(project.get("requested_amount"), project.get("currency"), language),
        ),
    ]
    scope = (
        '<dl class="scope">'
        + "".join(
            f"<dt>{_e(labels[key])}</dt><dd>{_e(value)}</dd>"
            for key, value in scope_rows
        )
        + "</dl>"
    )
    body.append(section("scope", scope))
    costs = []
    for item in workbench.get("expenses", []):
        cost_refs = refs(
            [*item.get("requirement_ids", []), *item.get("source_ids", [])]
        )
        costs.append(
            f'<tr id="{_anchor(item["expense_id"])}"><td>{_e(item.get("description"))}'
            f'<details><summary>{_e(labels["reason"])}</summary><div>'
            f'{paragraph(item.get("rationale"))}{cost_refs}</div></details></td>'
            f'<td class="amount">{_e(_money(item.get("amount"), item.get("currency"), language))}</td>'
            f'<td>{_e(label(item.get("outcome")))}</td>'
            f'<td>{_e(label(item.get("review_status")))}{paragraph(label(item.get("readiness")), "small muted")}</td></tr>'
        )
    cost_table = (
        '<table class="cost-table"><thead><tr>'
        + "".join(
            f'<th scope="col">{_e(labels[key])}</th>'
            for key in ("cost", "amount", "assessment", "review")
        )
        + "</tr></thead><tbody>"
        + "".join(costs)
        + "</tbody></table>"
    )
    body.append(
        section(
            "costs",
            paragraph(labels["proposed_note"], "muted")
            + (cost_table if costs else empty()),
        )
    )
    documents = [
        f'<article class="record" id="{_anchor(item["document_id"])}"><h3>{_e(item.get("title"))}</h3>'
        + metadata(item)
        + paragraph(item.get("rationale"))
        + refs([*item.get("requirement_ids", []), *item.get("material_source_ids", [])])
        + "</article>"
        for item in workbench.get("document_checklist", [])
    ]
    body.append(section("documents", "".join(documents) or empty()))
    requirements = []
    for requirement in workbench.get("requirements", []):
        comparisons = []
        for item in workbench.get("assessments", []):
            if item["requirement_id"] != requirement["requirement_id"]:
                continue
            comparisons.append(
                f'<article class="record" id="{_anchor(item["assessment_id"])}">'
                f'<h3>{_e(label(item["outcome"]))}</h3>{metadata(item)}'
                f'{paragraph(item.get("rationale"))}{refs(item.get("fact_ids", []))}</article>'
            )
        evidence = "".join(
            refs([ref["source_id"]])
            + paragraph(ref.get("locator"), "small")
            + f'<blockquote>{_e(ref.get("excerpt"))}</blockquote>'
            for ref in requirement.get("source_refs", [])
        )
        content = metadata(requirement)
        content += "".join(comparisons) or paragraph(labels["no_assessment"])
        content += f'<h4>{_e(labels["expected"])}</h4>'
        content += paragraph("; ".join(requirement.get("expected_evidence", [])))
        content += f'<h4>{_e(labels["excerpt"])}</h4>{evidence}'
        requirements.append(
            detail(requirement, "requirement_id", requirement.get("statement"), content)
        )
    body.append(section("requirements", "".join(requirements) or empty()))
    narratives = [
        f'<article class="record" id="{_anchor(item["narrative_id"])}"><h3>{_e(item.get("prompt"))}</h3>'
        + paragraph(item.get("draft"), "narrative")
        + metadata(item)
        + refs([*item.get("requirement_ids", []), *item.get("fact_ids", [])])
        + "</article>"
        for item in workbench.get("narratives", [])
    ]
    body.append(section("narratives", "".join(narratives) or empty()))
    consistency = [
        detail(
            item,
            "check_id",
            item.get("question"),
            paragraph(label(item.get("outcome")))
            + paragraph(item.get("rationale"))
            + metadata(item)
            + refs([*item.get("fact_ids", []), *item.get("source_ids", [])]),
        )
        for item in workbench.get("consistency_checks", [])
    ]
    body.append(section("consistency", "".join(consistency) or empty()))
    issues = [
        f'<article class="record" id="{_anchor(item["issue_id"])}">'
        + paragraph(item.get("detail"))
        + paragraph(label(item.get("status")), "muted")
        + metadata(item)
        + refs(item.get("related_ids", []))
        + "</article>"
        for item in workbench.get("issues", [])
    ]
    body.append(
        section("issues", "".join(issues) or paragraph(labels["no_issues"], "muted"))
    )
    sources_html = []
    for source in sources.get("sources", []):
        sources_html.append(
            f'<article id="{_anchor(source["source_id"])}"><h3>{_e(source.get("title"))}</h3>'
            + paragraph(source.get("issuer"), "muted")
            + f'<p><code>{_e(source.get("path"))}</code></p>'
            + detail(
                source,
                "source_id",
                labels["source_details"],
                f"<pre>{_e(source)}</pre>",
                suffix="-details",
            )
            + "</article>"
        )
    sources_body = "".join(sources_html)
    body.append(
        section(
            "sources", '<div class="sources">' + (sources_body or empty()) + "</div>"
        )
    )
    facts = "".join(
        detail(
            item,
            "fact_id",
            item.get("field_code"),
            f'<pre>{_e(item.get("value"))}</pre>'
            + metadata(item)
            + refs(item.get("source_ids", [])),
        )
        for item in workbench.get("facts", [])
    )
    forms = "".join(
        detail(
            item,
            "field_id",
            item.get("label"),
            paragraph(item.get("proposed_value"))
            + paragraph(item.get("rationale"))
            + metadata(item)
            + f"<pre>{_e(item)}</pre>",
        )
        for item in workbench.get("form_fields", [])
    )
    authority = workbench["authority_simulation"]
    authority_body = paragraph(label(authority.get("overall_outcome")))
    if authority.get("reviewer_perspective"):
        authority_body += paragraph(authority["reviewer_perspective"])
    authority_body += "".join(
        detail(
            item,
            "check_id",
            item.get("question"),
            paragraph(label(item.get("outcome")))
            + paragraph(item.get("rationale"))
            + metadata(item)
            + refs(item.get("related_ids", [])),
        )
        for item in authority.get("checks", [])
    )
    limits = [
        *workbench["dossier"].get("limitations", []),
        *audit.get("limitations", []),
    ]
    controls = paragraph(labels["technical_note"])
    controls += (
        "<ul>"
        + "".join(
            f'<li><a href="{filename}">{_e(filename)}</a></li>'
            for filename in (
                "review_dossier.md",
                "case_intake.json",
                "source_register.json",
                "application_workbench.json",
                "intelligence_register.json",
                "review_log.json",
                "validation_audit.json",
                "run_state.json",
            )
        )
        + "</ul>"
    )
    for key, content in (
        ("facts", facts or empty()),
        ("forms", forms or empty()),
        ("authority", authority_body),
        ("limitations", "".join(paragraph(value) for value in limits) or empty()),
    ):
        controls += f"<h3>{_e(labels[key])}</h3>{content}"
    body.append(
        section(
            "technical",
            f'<details><summary>{_e(labels["technical"])}</summary><div>{controls}</div></details>',
        )
    )
    action_rows = [
        (key, flag)
        for key, flag in (
            ("portal", "portal_actions_performed"),
            ("signature", "signature_actions_performed"),
            ("submission", "submission_actions_performed"),
        )
    ]
    actions = (
        '<dl class="scope">'
        + "".join(
            f'<dt>{_e(labels[key])}</dt><dd>{_e(labels["recorded" if run_state[flag] else "not_recorded"])}</dd>'
            for key, flag in action_rows
        )
        + "</dl>"
    )
    body.append(section("actions", actions))
    body.append(f'<footer>{_e(labels["review_notice"])}</footer>')
    return (
        f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
        f'<title>{_e(labels["title"])} · {_e(applicant.get("legal_name"))}</title><style>{CSS}</style>'
        "</head><body><main>" + "".join(body) + "</main></body></html>\n"
    )
