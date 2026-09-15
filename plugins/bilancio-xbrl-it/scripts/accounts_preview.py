"""Render reviewed accounts with localized navigation, without changing decisions."""

from __future__ import annotations

import html
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from accounts_preview_text import preview_check_message, preview_reason, preview_text

__all__ = ["render_accounts_preview"]

# Fixed interface text only. Source descriptions and reviewer prose stay intact.
_LABELS = {
    "title": ("Bozza di bilancio annuale", "Draft annual accounts"),
    "skip": ("Vai al contenuto principale", "Skip to main content"),
    "draft": ("Bozza da rivedere", "Draft for review"),
    "case": ("Caso", "Case"),
    "revision": ("revisione", "revision"),
    "form": ("forma", "form"),
    "period": ("Esercizio", "Financial year"),
    "presentation": (
        "Copertura dei prospetti civilistici",
        "Statutory statement coverage",
    ),
    "coverage": (
        "voci richieste {required} · decisioni esplicite {explicit} · decisioni mancanti {missing} · problemi aritmetici {issues}",
        "required items {required} · explicit decisions {explicit} · missing decisions {missing} · arithmetic issues {issues}",
    ),
    "coverage_pending": (
        "La copertura non è ancora stata calcolata. Rivedere la presentazione delle voci prima di completare il bilancio.",
        "Coverage has not yet been calculated. Review the statement presentation before completing the accounts.",
    ),
    "statements": ("Prospetti", "Statements"),
    "first_year": ("Valori del primo esercizio", "First financial year values"),
    "comparatives": ("Valori correnti e comparativi", "Current and comparative values"),
    "section": ("Sezione", "Section"),
    "item": ("Voce", "Item"),
    "current": ("Corrente", "Current"),
    "prior": ("Comparativo", "Comparative"),
    "currency": ("Valuta", "Currency"),
    "source": ("Riferimenti alle fonti", "Source references"),
    "no_statements": ("Nessuna voce calcolata.", "No statement items calculated."),
    "schedules": ("Prospetti di dettaglio", "Supporting schedules"),
    "schedule_caption": (
        "Stato delle riconciliazioni di dettaglio",
        "Supporting reconciliations",
    ),
    "no_schedules": (
        "Nessun prospetto di dettaglio acquisito.",
        "No supporting schedules recorded.",
    ),
    "type": ("Tipo", "Type"),
    "id": ("Riferimento", "Reference"),
    "status": ("Stato", "Status"),
    "issues": ("Problemi", "Issues"),
    "questions": ("Questionario", "Questions"),
    "question_caption": (
        "Informazioni da completare o rivedere",
        "Information to complete or review",
    ),
    "question": ("Domanda", "Question"),
    "reason": ("Motivo", "Reason"),
    "evidence": ("Informazioni richieste", "Information needed"),
    "no_questions": (
        "Nessuna domanda attiva registrata.",
        "No active questions recorded.",
    ),
    "notes": ("Nota integrativa", "Notes to the accounts"),
    "no_notes": ("Nessun testo di nota registrato.", "No note text recorded."),
    "micro": (
        "Informazioni in calce micro-imprese",
        "Micro-company statutory footnotes",
    ),
    "micro_caption": (
        "Informazioni statutarie in calce",
        "Statutory footnote disclosures",
    ),
    "no_micro": (
        "Nessuna informazione in calce registrata.",
        "No statutory footnote items recorded.",
    ),
    "content": ("Contenuto", "Content"),
    "taxonomy": ("Fatti tassonomici aggiuntivi", "Additional taxonomy facts"),
    "taxonomy_caption": (
        "Fatti aggiuntivi sottoposti a revisione",
        "Additional facts submitted for review",
    ),
    "no_taxonomy": (
        "Nessun fatto tassonomico aggiuntivo registrato.",
        "No additional taxonomy facts recorded.",
    ),
    "concept": ("Concetto", "Concept"),
    "fact_period": ("Periodo", "Period"),
    "value": ("Valore", "Value"),
    "dimensions": ("Dimensioni", "Dimensions"),
    "checks": ("Controlli", "Checks"),
    "checks_caption": ("Problemi e stato di revisione", "Issues and review status"),
    "severity": ("Gravità", "Severity"),
    "rule": ("Regola", "Rule"),
    "message": ("Messaggio", "Message"),
    "review": ("Revisione", "Review"),
    "no_validation": (
        "Controlli non ancora disponibili per questa anteprima.",
        "Checks are not yet available for this preview.",
    ),
    "no_issues": (
        "Nessun problema rilevato nei controlli mostrati.",
        "No issues found in the displayed checks.",
    ),
    "check_scope": (
        "Controlli del contenuto ricalcolati durante la generazione. La validazione finale verifica anche questa anteprima prima dell’approvazione.",
        "Content checks recalculated during generation. Final validation also verifies this preview before approval.",
    ),
    "balance_note": (
        "Importi esposti secondo il segno di presentazione rivisto per ogni voce. I saldi contabili originali sono nei riferimenti alle fonti. Classificazioni e presentazione restano da rivedere.",
        "Amounts use each item’s reviewed presentation sign. Original accounting balances remain in the source references. Classifications and presentation remain subject to review.",
    ),
    "boundary": (
        "Vera prepara una bozza rivedibile; non approva il bilancio, non firma e non deposita.",
        "Vera prepares a draft for review. Approval, signature and filing remain separate steps.",
    ),
    "technical": ("Dettaglio del controllo", "Check details"),
}

_TERMS = {
    "ASSETS": ("Attivo", "Assets"),
    "LIABILITIES_EQUITY": ("Passivo e patrimonio netto", "Liabilities and equity"),
    "INCOME_STATEMENT": ("Conto economico", "Income statement"),
    "INCOME_RESULT": ("Risultato del conto economico", "Income statement result"),
    "EQUITY_RESULT": ("Risultato nel patrimonio netto", "Result in equity"),
    "CASH_FLOW": ("Rendiconto finanziario", "Cash flow statement"),
    "MICRO": ("Micro-impresa", "Micro-company"),
    "ABBREVIATED": ("Abbreviata", "Abbreviated"),
    "ORDINARY": ("Ordinaria", "Ordinary"),
    "NON_REVISIONATA": ("Da rivedere", "Not reviewed"),
    "UNREVIEWED": ("Da rivedere", "Not reviewed"),
    "INCOMPLETE": ("Da completare", "Incomplete"),
    "COMPLETE": ("Completo", "Complete"),
    "CONFIRMED": ("Confermato", "Confirmed"),
    "OPEN": ("Da completare", "Open"),
    "ANSWERED": ("Risposta registrata", "Answer recorded"),
    "ACCEPTED": ("Accettato", "Accepted"),
    "REJECTED": ("Respinto", "Rejected"),
    "DRAFT": ("Bozza", "Draft"),
    "MODEL_SUGGESTED": ("Proposto da Vera", "Proposed by Vera"),
    "NOT_APPLICABLE_CONFIRMED": (
        "Non applicabile, confermato",
        "Confirmed not applicable",
    ),
    "ACKNOWLEDGED": ("Presa visione", "Acknowledged"),
    "OVERRIDDEN": ("Eccezione approvata", "Override approved"),
    "BLOCKER": ("Impedisce l’approvazione", "Blocks approval"),
    "HIGH": ("Alta", "High"),
    "MEDIUM": ("Media", "Medium"),
    "LOW": ("Bassa", "Low"),
    "INFO": ("Informazione", "Information"),
    "PASS": ("Superato", "Passed"),
    "FAIL": ("Da risolvere", "Unresolved"),
    "INTRODUCTION": ("Introduzione", "Introduction"),
    "POLICIES": ("Criteri di valutazione", "Accounting policies"),
    "COMMITMENTS_RELATED": (
        "Impegni e rapporti correlati",
        "Commitments and related matters",
    ),
    "POST_CLOSING_GOING_CONCERN": (
        "Fatti successivi e continuità aziendale",
        "Subsequent events and going concern",
    ),
    "ADDITIONAL": ("Ulteriori informazioni", "Additional information"),
    "CURRENT": ("Corrente", "Current"),
    "PRIOR": ("Comparativo", "Comparative"),
    "MONETARY": ("Importo", "Monetary"),
    "TEXT": ("Testo", "Text"),
    "BOOLEAN": ("Conferma", "Boolean"),
    "PRESENT": ("Presente", "Present"),
    "RECEIVABLES": ("Crediti", "Receivables"),
    "PAYABLES": ("Debiti", "Payables"),
    "EQUITY": ("Patrimonio netto", "Equity"),
    "TAXES": ("Imposte", "Taxes"),
    "guarantees_commitments_contingencies": (
        "Garanzie, impegni e passività potenziali",
        "Guarantees, commitments and contingent liabilities",
    ),
    "director_auditor_compensation": (
        "Compensi ad amministratori e revisori",
        "Director and auditor compensation",
    ),
    "own_and_parent_shares": (
        "Azioni proprie e della controllante",
        "Own and parent-company shares",
    ),
}


def _cell(value: Any) -> str:
    return html.escape("—" if value is None else str(value))


def _statement_value(fact: Mapping[str, Any], field: str) -> Any:
    """Apply only the recorded presentation sign, never infer it from a label."""
    value = fact.get(field)
    if value is None:
        return None
    multiplier = str(fact.get("xbrl_sign_multiplier", "1"))
    if multiplier not in {"1", "-1"}:
        return value
    try:
        return Decimal(str(value)) * Decimal(multiplier)
    except InvalidOperation:
        return value


def _amount(value: Any, language: str) -> str:
    if value is None:
        return "—"
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return _cell(value)
    if not number.is_finite():
        return _cell(value)
    formatted = f"{number:,.2f}"
    if language == "it":
        formatted = formatted.translate(str.maketrans(",.", ".,"))
    return formatted


def render_accounts_preview(case: Mapping[str, Any]) -> bytes:
    """Render native case values and review states; never infer missing evidence."""

    language = str(case.get("output_language", "it"))
    if language not in {"it", "en"}:
        raise ValueError("Accounts preview language must be it or en")
    locale = 0 if language == "it" else 1

    def label(key: str) -> str:
        return _LABELS[key][locale]

    def term(value: Any) -> str:
        pair = _TERMS.get(str(value))
        return _cell(pair[locale] if pair else value)

    def table(
        section: str,
        title: str,
        caption: str,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        empty: str,
    ) -> str:
        heading = f'<h2 id="{section}-heading">{_cell(title)}</h2>'
        if not rows:
            body = f'<p class="empty">{_cell(empty)}</p>'
        else:
            cells = "".join(
                "<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>"
                for row in rows
            )
            columns = "".join(f'<th scope="col">{_cell(h)}</th>' for h in headers)
            body = (
                f'<div class="table-scroll" role="region" aria-labelledby="{section}-heading" tabindex="0">'
                f"<table><caption>{_cell(caption)}</caption><thead><tr>{columns}</tr></thead>"
                f"<tbody>{cells}</tbody></table></div>"
            )
        return f'<section aria-labelledby="{section}-heading">{heading}{body}</section>'

    entity = case.get("entity") or {}
    anchors = {
        str(row["source_ref"]): row
        for row in (case.get("trial_balance") or {}).get("source_anchors", [])
    }
    documents = {
        str(row["document_id"]): row for row in case.get("source_documents", [])
    }

    def source_details(fact: Mapping[str, Any]) -> str:
        references = []
        for reference in fact.get("source_refs", []):
            anchor = anchors.get(str(reference))
            if anchor is None:
                references.append(_cell(reference))
                continue
            document = documents.get(str(anchor.get("document_id")), {})
            location = f'{anchor.get("column", "")}{anchor.get("row", "")}'
            references.append(
                f'{_cell(document.get("file_name") or anchor.get("document_id"))} · '
                f'{_cell(anchor.get("sheet"))}!{_cell(location)} · '
                f'{_cell(anchor.get("column_header"))}: {_cell(anchor.get("raw_value"))}'
            )
        if not references:
            return ""
        return (
            f'<details><summary>{_cell(label("source"))}</summary>'
            + "<br>".join(references)
            + "</details>"
        )

    first_year = entity.get("first_financial_year") is True
    statements = case.get("statements") or {}
    headers = [label("section"), label("item"), label("current")]
    if not first_year:
        headers.append(label("prior"))
    headers.append(label("currency"))
    rows = []
    for fact in statements.get("facts", []):
        row = [
            term(fact.get("statement_section")),
            _cell(fact.get("key")) + source_details(fact),
            _amount(_statement_value(fact, "current_value"), language),
        ]
        if not first_year:
            row.append(_amount(_statement_value(fact, "prior_value"), language))
        row.append(_cell(fact.get("currency")))
        rows.append(row)
    sections = [
        table(
            "statements",
            label("statements"),
            label("first_year" if first_year else "comparatives"),
            headers,
            rows,
            label("no_statements"),
        ),
        f'<p class="muted">{_cell(label("balance_note"))}</p>',
        table(
            "schedules",
            label("schedules"),
            label("schedule_caption"),
            [label("type"), label("id"), label("status"), label("issues")],
            [
                [
                    term(row.get("schedule_type")),
                    _cell(row.get("schedule_id")),
                    term(row.get("status")),
                    _cell(len(row.get("issues", []))),
                ]
                for row in case.get("schedules", [])
            ],
            label("no_schedules"),
        ),
    ]
    questions = [
        row
        for row in case.get("questionnaire", [])
        if row.get("state") != "NOT_TRIGGERED"
    ]
    question_headers = [label("question"), label("status"), label("evidence")]
    has_reasons = any(row.get("reason") for row in questions)
    if has_reasons:
        question_headers.append(label("reason"))
    question_rows = []
    for question in questions:
        row = [
            _cell(preview_text(question.get("title"), language)),
            term(question.get("state")),
            _cell(preview_text(question.get("evidence_requested"), language)),
        ]
        if has_reasons:
            row.append(_cell(preview_reason(question.get("reason"), language)))
        question_rows.append(row)
    sections.append(
        table(
            "questions",
            label("questions"),
            label("question_caption"),
            question_headers,
            question_rows,
            label("no_questions"),
        )
    )
    notes = "".join(
        f'<article lang="{_cell(block.get("language") or language)}">'
        f'<h3>{term(block.get("section_id"))}</h3><p>{_cell(block.get("text"))}</p>'
        f'<small>{term(block.get("status"))}</small></article>'
        for block in case.get("narrative_blocks", [])
    )
    if not notes:
        notes = f'<p class="empty">{_cell(label("no_notes"))}</p>'
    sections.append(
        f'<section aria-labelledby="notes-heading"><h2 id="notes-heading">{_cell(label("notes"))}</h2>{notes}</section>'
    )
    sections.append(
        table(
            "micro",
            label("micro"),
            label("micro_caption"),
            [label("item"), label("status"), label("content"), label("reason")],
            [
                [
                    term(row.get("key")),
                    term(row.get("status")),
                    _cell(row.get("value")),
                    _cell(row.get("reason")),
                ]
                for row in (case.get("micro_reporting") or {}).get("footer_items", [])
            ],
            label("no_micro"),
        )
    )
    sections.append(
        table(
            "taxonomy",
            label("taxonomy"),
            label("taxonomy_caption"),
            [
                label("concept"),
                label("type"),
                label("fact_period"),
                label("value"),
                label("dimensions"),
            ],
            [
                [
                    _cell(row.get("xbrl_concept")),
                    term(row.get("fact_type")),
                    term(row.get("period")),
                    _cell(row.get("value")),
                    _cell(row.get("dimensions")),
                ]
                for row in [
                    *case.get("taxonomy_facts", []),
                    *case.get("schedule_taxonomy_facts", []),
                ]
            ],
            label("no_taxonomy"),
        )
    )
    validation = case.get("validation")
    sections.append(
        table(
            "issues",
            label("checks"),
            label("checks_caption"),
            [label("severity"), label("message"), label("review")],
            [
                [
                    term(row.get("severity")),
                    _cell(preview_check_message(row, case, language))
                    + f'<details><summary>{_cell(label("technical"))}</summary><code>{_cell(row.get("rule_id"))}</code></details>',
                    term(row.get("review_status")),
                ]
                for row in (validation or {}).get("issues", [])
            ],
            label("no_validation" if validation is None else "no_issues"),
        )
    )
    if case.get("preview_checks_recalculated") is True:
        sections.append(f'<p class="muted">{_cell(label("check_scope"))}</p>')
    presentation = case.get("statutory_presentation") or {}
    summary = presentation.get("summary") or {}
    coverage = (
        label("coverage").format(
            required=summary.get("required_leaf_concepts", 0),
            explicit=summary.get("explicit_decisions", 0),
            missing=summary.get("missing_period_decisions", 0),
            issues=summary.get("issues", 0),
        )
        if summary
        else label("coverage_pending")
    )
    period = case.get("period") or {}
    document = f"""<!doctype html>
<html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">
<title>{_cell(label("title"))} · {_cell(entity.get("legal_name") or case.get("case_id"))}</title>
<style>
*{{box-sizing:border-box}}body{{font-family:Arial,sans-serif;max-width:1120px;margin:2rem auto;padding:0 1.25rem;color:#202a38;background:#fff;line-height:1.55}}
h1,h2,h3{{color:#173654}}h1{{font-size:2rem;line-height:1.2;margin:.5rem 0}}h2{{font-size:1.25rem}}header{{border-bottom:3px solid #173654;padding-bottom:1rem;margin-bottom:1.5rem}}
section{{margin:1.5rem 0}}p{{margin:.5rem 0}}.muted,.empty,small{{color:#526172}}.draft{{color:#173654;font-weight:700}}.skip-link{{position:absolute;left:-9999px}}
.skip-link:focus{{left:1rem;top:1rem;background:#fff;color:#173654;padding:.75rem;z-index:2}}:focus-visible{{outline:3px solid #0070c0;outline-offset:3px}}
.table-scroll{{overflow-x:auto;max-width:100%}}table{{border-collapse:collapse;width:100%}}caption{{text-align:left;color:#526172;padding:.4rem 0}}
th,td{{border-bottom:1px solid #dbe1e8;padding:.65rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#eef2f6;font-size:.9rem}}tbody tr:nth-child(even){{background:#fafbfd}}
article{{border-left:3px solid #5e7e9d;padding:.25rem 1rem;margin:1rem 0}}details{{font-size:.82rem;color:#526172;margin-top:.3rem}}summary{{cursor:pointer}}code{{overflow-wrap:anywhere}}footer{{border-top:1px solid #dbe1e8;padding-top:1rem;margin-top:2rem}}
@media(max-width:640px){{body{{margin:1rem auto;padding:0 .8rem}}h1{{font-size:1.6rem}}th,td{{padding:.45rem}}}}
@media print{{body{{max-width:none;font-size:10pt}}.skip-link{{display:none}}tr{{break-inside:avoid}}thead{{display:table-header-group}}h2,h3{{break-after:avoid}}.table-scroll{{overflow:visible}}}}
</style></head><body><a class="skip-link" href="#main-content">{_cell(label("skip"))}</a>
<main id="main-content" tabindex="-1" data-output-language="{language}"><header><p class="draft">{_cell(label("draft"))}</p><h1>{_cell(label("title"))}</h1>
<p><strong>{_cell(entity.get("legal_name") or case.get("case_id"))}</strong></p><p>{_cell(label("period"))}: {_cell(period.get("start"))} – {_cell(period.get("end"))}</p>
<p class="muted">{_cell(label("case"))} {_cell(case.get("case_id"))} · {_cell(label("revision"))} {_cell(case.get("revision_id"))} · {_cell(label("form"))}: {term(case.get("selected_form"))}</p></header>
<section aria-labelledby="presentation-heading"><h2 id="presentation-heading">{_cell(label("presentation"))}</h2><p><strong>{term(presentation.get("status", "UNREVIEWED"))}</strong></p><p>{_cell(coverage)}</p></section>
{"".join(sections)}<footer><p>{_cell(label("boundary"))}</p></footer></main></body></html>"""
    return document.encode("utf-8")
