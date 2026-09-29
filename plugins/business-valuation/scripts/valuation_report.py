"""Render the same validated valuation register into local reviewable workpapers."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from valuation_case import build_valuation, require
from valuation_engine import decimal

__all__ = ["write_package", "report_sections", "write_workbook", "compile_html"]

NOTICE = "Carte di lavoro per revisione professionale. Non costituiscono perizia firmata, attestazione di conformità PIV o qualificazione della finalità legale."
STATUS = {
    "partial": "Incompleto",
    "blocked": "Bloccato",
    "ready_for_professional_review": "Da rivedere",
    "accepted_workpaper": "Revisione registrata",
    "excluded": "Escluso",
    "draft": "Bozza",
}
METHOD_LABELS = {
    "DCF_FCFF": "DCF sui flussi dell’impresa",
    "DCF_FCFE": "DCF sui flussi dei soci",
    "INCOME_EQUITY": "Metodo reddituale",
    "INCOME_EQUITY_FINITE": "Metodo reddituale a durata finita",
    "NAV": "Patrimoniale rettificato",
    "MIXED_EQUITY": "Metodo misto",
    "MULTIPLE": "Multipli",
    "APV": "Valore attuale rettificato (APV)",
}
DETAIL_LABELS = {
    "terminal_value": "Valore terminale",
    "pv_terminal": "Valore attuale del valore terminale",
    "terminal_share": "Incidenza del valore terminale sul risultato del metodo",
    "income_pv": "Valore attuale dei redditi espliciti",
    "residual_value": "Valore residuo del capitale proprio alla scadenza",
    "pv_residual": "Valore attuale del residuo",
    "residual_share": "Rapporto fra valore attuale del residuo e risultato",
}
TIMING_LABELS = {
    "end_period": "flussi a fine periodo",
    "mid_period": "flussi a metà periodo",
    "flat": "tasso costante",
    "spot_curve": "tassi spot per scadenza",
    "forward_curve": "tassi forward per intervallo",
    "effective_annual": "capitalizzazione annua effettiva",
    "continuous": "capitalizzazione continua",
}
CLAIM_LABELS = {
    "fact": "Fatto dichiarato",
    "assumption": "Assunzione",
    "hypothesis": "Ipotesi",
    "opinion": "Giudizio",
}
MANDATE_LABELS = {
    "subject_type": "Oggetto dell'incarico",
    "engagement_date": "Data dell'incarico",
    "report_date": "Data della relazione",
    "commissioning_party": "Soggetto conferente",
    "expert_activity": "Attività richiesta all'esperto",
    "participant_perspective": "Prospettiva del partecipante",
    "recipients": "Destinatari dichiarati",
    "use_restrictions": "Limitazioni d'uso",
    "competencies": "Competenze dichiarate e verifiche",
    "conflicts": "Interessi e conflitti dichiarati",
    "description": "Strumento o classe",
    "ownership_basis": "Base della percentuale o motivo di non applicabilità",
    "economic_rights": "Diritti patrimoniali",
    "administrative_rights": "Diritti amministrativi",
    "statutes": "Statuto",
    "agreements": "Patti",
    "restrictions": "Vincoli",
    "thresholds": "Soglie",
}
SUBJECT_LABELS = {
    "enterprise": "Azienda",
    "business_unit": "Ramo d'azienda",
    "equity_interest": "Partecipazione",
    "specific_right": "Diritto specifico",
}


def display(value: str, places: int = 2) -> str:
    """Round only the reader-facing display; retain original decimal strings."""
    return f"{decimal(value):,.{places}f}".translate(str.maketrans(",.", ".,"))


def _method_label(kind: str) -> str:
    """Keep unsupported methods visible in partial reports."""
    return METHOD_LABELS.get(kind, f"Metodo non supportato: {kind}")


def _mandate_rows(report: dict) -> list[tuple[str, str, str, str, str]]:
    """Keep the same evidence-linked mandate fields in prose and workbook."""
    details = report["mandate_assessment"]["details"]
    if details is None:
        return [("Scheda dell'incarico", "Da acquisire", "Incompleta", "", "")]
    rows = []
    for key, item in details.items():
        if key in {"review", "interests"}:
            continue
        value = item["value"]
        if key == "subject_type" and value is not None:
            value = SUBJECT_LABELS[value]
        rows.append(
            (
                MANDATE_LABELS[key],
                value if value is not None else "Da acquisire",
                "Confermato" if item["status"] == "confirmed" else "Da confermare",
                ", ".join(item["source_ids"]),
                item["locator"] or "Posizione da acquisire",
            )
        )
    inputs = {row["id"]: row for row in report["case"]["inputs"]}
    for item in details["interests"]:
        status = "Confermato" if item["status"] == "confirmed" else "Da confermare"
        refs, locator = (
            ", ".join(item["source_ids"]),
            item["locator"] or "Posizione da acquisire",
        )
        for key in (
            "description",
            "ownership_basis",
            "economic_rights",
            "administrative_rights",
            "statutes",
            "agreements",
            "restrictions",
            "thresholds",
        ):
            rows.append(
                (
                    f"{item['id']} · {MANDATE_LABELS[key]}",
                    item[key] if item[key] is not None else "Da acquisire",
                    status,
                    refs,
                    locator,
                )
            )
        ref = item["ownership_input_id"]
        if ref is not None:
            amount = inputs[ref]
            shown = (
                "Da acquisire"
                if amount["value"] is None
                else f"{display(str(decimal(amount['value']) * 100))}% [{ref}]"
            )
            rows.append(
                (
                    f"{item['id']} · Percentuale",
                    shown,
                    (
                        "Confermato"
                        if amount["status"] == "confirmed"
                        else "Da confermare"
                    ),
                    ", ".join(amount["source_ids"]),
                    amount["locator"],
                )
            )
    return rows


def _statement_issues(statement: dict, inputs: list[dict]) -> list[str]:
    """Localize fixed check diagnostics without judging source prose."""
    messages = {
        "Assets do not equal liabilities plus equity": "L'attivo non coincide con passività più patrimonio netto.",
        "Statement period is reversed": "La fine del periodo precede l'inizio.",
        "Statement period exceeds the information cutoff": "Il periodo supera il limite temporale delle informazioni utilizzabili.",
        "Prior statement must precede the current period": "Il bilancio precedente non precede il periodo corrente.",
        "Prior statement must close immediately before this period": "La data di chiusura precedente non coincide con il giorno prima dell'inizio del periodo.",
        "Continuity requires the same explicit perimeter and accounting basis": "Il confronto richiede lo stesso perimetro dichiarato e la stessa base contabile.",
        "Prior statement is unreconciled": "Il bilancio precedente presenta una quadratura non risolta.",
    }
    for row in statement["rollforwards"]:
        messages[
            f"Roll-forward {row['id']}: opening plus movements differs from closing"
        ] = f"{row['description']}: apertura più movimenti diversa dalla chiusura."
        messages[f"Roll-forward {row['id']}: opening differs from prior closing"] = (
            f"{row['description']}: apertura diversa dalla chiusura precedente."
        )
    for row in inputs:
        messages[f"Missing input: {row['id']}"] = (
            f"Importo non disponibile: {row['id']}."
        )
    return [messages.get(issue, issue) for issue in statement["issues"]]


def _readable_issues(report: dict) -> list[str]:
    """Translate the fixed mandate diagnostics without interpreting supplied prose."""
    translated = {
        "Structured mandate details have not been collected": "Scheda dell'incarico non ancora acquisita.",
        "Selected subject requires an explicit rights record": "L'oggetto selezionato richiede una scheda dei diritti.",
        "Mandate source review pending": "Le fonti dell'incarico richiedono ancora revisione.",
    }
    for key, label in MANDATE_LABELS.items():
        translated[f"Mandate {key}: evidence or confirmation pending"] = (
            f"{label}: evidenza o conferma da acquisire."
        )
    reasons = {
        "evidence or confirmation pending": "evidenza o conferma da acquisire",
        "ownership ratio missing": "percentuale di partecipazione da acquisire",
        "ownership evidence pending": "evidenza sulla percentuale da confermare",
        "ownership ratio outside zero to one": "percentuale fuori dall'intervallo tra 0% e 100%",
    }
    details = report["mandate_assessment"]["details"]
    for item in (details or {}).get("interests", []):
        for reason, shown in reasons.items():
            translated[f"Rights {item['id']}: {reason}"] = (
                f"Diritti {item['id']}: {shown}."
            )
    for statement in report["statements"]:
        translated[
            f"Statement {statement['id']}: {'; '.join(statement['issues']) or 'review pending'}"
        ] = f"Prospetto {statement['id']}: " + (
            " ".join(_statement_issues(statement, report["case"]["inputs"]))
            or "revisione da acquisire."
        )
    return [translated.get(issue, issue) for issue in report["issues"]]


def report_sections(report: dict) -> list[tuple[str, list[str]]]:
    """Produce one reader-facing outline shared by every document format."""
    case = report["case"]
    mandate = case["mandate"]
    amounts = {row["id"]: row for row in report["calculations"]}
    sections = [
        (
            "Incarico e perimetro",
            [
                f"{case['entity_name']} · {mandate['subject']}",
                f"Finalità: {mandate['purpose']}",
                f"Data valutativa: {mandate['valuation_date']} · Limite informativo: {mandate['information_cutoff']}",
                f"Configurazione: {mandate['basis_of_value']} · Premessa: {mandate['premise']}",
                f"Diritti e perimetro della quota: {mandate['rights']}",
                f"Destinatari: {case['audience']} · Valuta: {case['currency']}",
                f"Stato: {STATUS[report['status']]}",
                (
                    "Dati sintetici di prova."
                    if case["synthetic"]
                    else "Dati del caso selezionato."
                ),
                NOTICE,
            ],
        )
    ]
    assessment = report["mandate_assessment"]
    mandate_rows = [f"Revisione dell'incarico: {STATUS[assessment['status']]}"]
    for label, value, state, refs, locator in _mandate_rows(report):
        mandate_rows.append(f"{label}: {value} · {state}")
        if refs or locator:
            mandate_rows.append(f"Fonti: {refs or 'da acquisire'} · {locator}")
    if assessment["stale_review"]:
        mandate_rows.append(
            "La precedente revisione dell'incarico non vale per queste dipendenze."
        )
    mandate_rows.append(
        "Competenze, indipendenza, idoneità dell'incarico e significato dei diritti richiedono giudizio professionale. Le percentuali registrate non moltiplicano automaticamente il valore e non determinano premi o sconti."
    )
    sections.append(("Scheda dell'incarico", mandate_rows))
    purpose = report["purpose_coverage"]
    profile = purpose["profile"]
    sections.append(
        (
            "Finalità e disponibilità professionale",
            [
                (
                    f"Profilo: {profile['label']}"
                    if profile
                    else "Profilo non ancora selezionato."
                ),
                (
                    profile["intake_focus"]
                    if profile
                    else "Chiarire la finalità concreta con il professionista."
                ),
                (purpose["selection"] or {}).get("selection_reason", ""),
                "Sono disponibili il nucleo comune di calcolo e le carte di lavoro in sviluppo. La verifica PIV e la revisione specialistica del profilo non sono completate; nessun profilo è abilitato all'uso professionale.",
                "Una revisione registrata sui calcoli del caso non abilita il profilo e non certifica la conformità della relazione.",
            ],
        )
    )
    inputs = {item["id"]: item for item in case["inputs"]}
    plan = report["plan_bridge"]
    if plan:
        periods = plan["selected_periods"]
        frequency = "mensili" if plan["flow_frequency"] == "monthly" else "annuali"
        rows = [
            f"Scenario {plan['scenario_id']} · Periodi selezionati: {periods[0]} — {periods[-1]} · Flussi valutativi {frequency}.",
            "Il piano originale è stato ricalcolato. Le imposte operative per cassa e il capitale circolante iniziale sono ipotesi separate da verificare; il piano non approva la finalità valutativa.",
            plan["binding"]["operating_classification"],
        ]
        for row in plan["monthly"]:
            rows.append(
                f"{row['period']}: EBIT {display(row['ebit'])}; imposte operative {display(row['cash_operating_taxes'])}; ammortamenti {display(row['depreciation_amortization'])}; investimenti {display(row['capital_expenditure'])}; variazione CCN {display(row['delta_nwc'])}; FCFF {display(row['fcff'])} {case['currency']}. CCN: {display(row['opening_nwc'])} → {display(row['ending_nwc'])}."
            )
        rows.append(
            "I mesi mantengono i propri importi e le proprie scadenze. Il flusso terminale annuo è un'ipotesi distinta: non deriva dalla moltiplicazione automatica di un mese o di un periodo parziale."
        )
        sections.append(("Raccordo dal piano", rows))
    if not report["statements"]:
        sections.append(
            (
                "Quadrature e continuità",
                [
                    "Non sono stati forniti prospetti per verificare quadratura patrimoniale, movimenti e continuità dei saldi."
                ],
            )
        )
    for statement in report["statements"]:
        coverage = (
            "Sola quadratura patrimoniale; movimenti e continuità non verificati."
            if statement["coverage"] == "balance_only"
            else "Quadratura patrimoniale e movimenti di tutte le voci dichiarate."
        )
        rows = [
            f"{statement['title']} · {statement['period_start']} – {statement['period_end']} · {STATUS[statement['status']]}",
            f"Perimetro {statement['perimeter_id']}: {statement['perimeter_description']}",
            f"Base: {'riportata' if statement['basis'] == 'reported' else 'rettificata'}. {coverage}",
            f"Fonti: {', '.join(statement['source_ids'])} · {statement['locator']}",
            f"Input valutativi collegati: {', '.join(statement['bound_input_ids'])}.",
        ]
        for check in statement.get("checks", []):
            rows.append(
                f"{check['label']}: atteso {display(amounts[check['expected_id']]['value'])}, riscontrato {display(amounts[check['actual_id']]['value'])}, differenza {display(amounts[check['difference_id']]['value'])} {case['currency']} [{check['difference_id']}]."
            )
        for movement in statement["rollforwards"]:
            rows.append(
                f"{movement['description']}: apertura [{movement['opening_input']}], movimenti con segno [{', '.join(movement['movement_inputs'])}], chiusura [{movement['closing_input']}]. {movement['comparison_basis']}"
            )
            if movement["prior_statement_id"] is None:
                rows.append(
                    "Saldo iniziale da fonte autonoma; confronto con un bilancio precedente non eseguito."
                )
        rows.extend(_statement_issues(statement, case["inputs"]))
        rows.extend(statement["limitations"])
        rows.append(
            "La quadratura verifica gli importi dichiarati. Completezza delle voci, classificazione e significato economico richiedono revisione professionale."
        )
        sections.append((f"Quadrature e continuità · {statement['id']}", rows))
    for group in report["normalizations"]:
        rows = [
            f"Anno {group['year']} · {group['line']} · Stato: {STATUS[group['status']]}"
        ]
        for label, ref in (
            ("Riportato", group["reported_input"]),
            ("Rettificato dichiarato", group["adjusted_input"]),
        ):
            value = inputs[ref]["value"]
            shown = (
                "non disponibile"
                if value is None
                else f"{display(value)} {case['currency']}"
            )
            rows.append(f"{label}: {shown} [{ref}]")
        if "value_id" in group:
            rows.append(
                f"Rettificato calcolato: {display(amounts[group['value_id']]['value'])} {case['currency']} [{group['value_id']}]. Differenza: {display(amounts[group['difference_id']]['value'])}."
            )
        if "reason" in group:
            rows.append(group["reason"])
        for adjustment in group["adjustments"]:
            ref = adjustment["amount_input"]
            value = inputs[ref]["value"]
            shown = (
                "non disponibile"
                if value is None
                else f"{display(value)} {case['currency']}"
            )
            rows.extend(
                [
                    f"Rettifica {adjustment['id']}: {shown} [{ref}] · {STATUS[adjustment['status']]} · {adjustment['reason']}",
                    f"Quadratura contabile: {adjustment['accounting_check']}",
                    f"Sostanza economica: {adjustment['economic_rationale']}",
                    f"Trattamento fiscale: {adjustment['tax_treatment']}",
                    f"Reversibilità: {adjustment['reversibility']}",
                    f"Fonti: {', '.join(adjustment['source_ids'])} · {adjustment['locator']}",
                    f"Revisore dichiarato: {(adjustment.get('review') or {}).get('reviewer', 'non ancora registrato')}",
                ]
            )
            if adjustment["stale_review"]:
                rows.append(
                    "La precedente revisione della rettifica non vale per queste dipendenze."
                )
        rows.append(
            "Il trattamento fiscale e la reversibilità sono scelte documentate da rivedere; il calcolo non li deduce. Eventuali effetti fiscali su altre voci richiedono rettifiche separate."
        )
        sections.append((f"Rettifiche · {group['line']}", rows))
    for method in report["methods"]:
        rows = [
            f"Stato: {STATUS[method['status']]}",
            method.get("rationale", method.get("reason", "")),
        ]
        if "value_id" in method:
            value = amounts[method["value_id"]]
            basis = (
                "Valore operativo"
                if method["value_type"] == "operating_enterprise"
                else "Valore del capitale proprio"
            )
            rows.append(
                f"{basis}: {display(value['value'])} {case['currency']} [{value['id']}]"
            )
            if method["equity_id"] and method["equity_id"] != method["value_id"]:
                equity = amounts[method["equity_id"]]
                rows.append(
                    f"Capitale proprio dopo raccordo: {display(equity['value'])} {case['currency']} [{equity['id']}]"
                )
            elif method["equity_id"] is None:
                rows.append(
                    "Raccordo al capitale proprio non fornito; il valore operativo non è il valore della quota."
                )
            for label, ref in method["detail_ids"].items():
                detail = amounts[ref]
                shown = (
                    f"{display(str(decimal(detail['value']) * 100))}%"
                    if detail["unit"] == "ratio"
                    else f"{display(detail['value'])} {detail['unit']}"
                )
                rows.append(f"{DETAIL_LABELS[label]}: {shown} [{ref}]")
            rows.extend(method["limitations"])
            income_basis = method.get("income_basis")
            if income_basis:
                rows.extend(
                    [
                        "Il calcolo attualizza redditi dichiarati e un residuo fornito separatamente. Non converte il reddito in cassa, non stima una perpetuità e non deduce nuovamente il debito.",
                        f"Base reddituale: {'Confermata' if income_basis['status'] == 'confirmed' else 'Da confermare'}",
                        f"Mantenimento del capitale: {income_basis['capital_maintenance']}",
                        f"Reinvestimenti: {income_basis['reinvestment']}",
                        f"Distribuzioni e disponibilità: {income_basis['distributions']}",
                        f"Base del residuo e assenza di duplicazioni: {income_basis['residual_basis']}",
                        f"Fonti della base reddituale: {', '.join(income_basis['source_ids'])} · {income_basis['locator']}",
                        "La coerenza tra redditi, mantenimento della capacità, reinvestimenti, distribuzioni e residuo richiede revisione professionale; la compilazione dei campi non la dimostra.",
                    ]
                )
            timing = method.get("timing")
            if timing:
                rows.extend(
                    [
                        f"Tempi espliciti dalla data {timing['valuation_date']}: {timing['day_count']}; {TIMING_LABELS[timing['cash_flow_timing']].replace('flussi', 'redditi') if income_basis else TIMING_LABELS[timing['cash_flow_timing']]}; {TIMING_LABELS[timing['rate_model']]}; {TIMING_LABELS[timing['rate_compounding']]}.",
                        timing["rationale"],
                        (
                            "Il residuo equity è un importo autonomo alla fine dell'ultimo periodo e resta a quella scadenza anche se i redditi sono collocati a metà periodo. Non è derivato dall'ultimo reddito né da una formula di crescita perpetua."
                            if income_basis
                            else "Il valore terminale è una perpetuità annuale a fine periodo, stimata all'ultima data del piano. Il flusso terminale è annuale e distinto dagli eventuali flussi mensili; il tasso terminale e la crescita sono annui effettivi."
                        ),
                    ]
                )
                rows.extend(
                    f"Periodo {period['start_date']} → {period['end_date']}: tempo {display(amounts[period['cash_time_id']]['value'], 6)} anni [{period['cash_time_id']}]; divisore {display(amounts[period['discount_factor_id']]['value'], 6)} [{period['discount_factor_id']}]."
                    for period in timing["schedule"]
                )
            if method["stale_review"]:
                rows.append(
                    "La revisione precedente non è valida per queste dipendenze."
                )
        sections.append((_method_label(method["kind"]), rows))
    if report["sensitivity"]:
        rows = []
        for scenario in report["sensitivity"]:
            if scenario["status"] == "blocked":
                rows.append(f"{scenario['id']}: non calcolabile — {scenario['reason']}")
            else:
                row = amounts[scenario["equity_id"] or scenario["value_id"]]
                rows.append(
                    f"{scenario['id']}: {display(row['value'])} {case['currency']} [{row['id']}]"
                )
        sections.append(
            (
                "Sensitività delle ipotesi",
                [
                    "Risultati condizionati alle ipotesi dichiarate; non sono intervalli statistici.",
                    *rows,
                ],
            )
        )
    if report["claims"]:
        rows = [
            "I collegamenti verificano identità, importi e versioni. La corrispondenza fra testo e significato delle fonti richiede revisione professionale."
        ]
        for claim in report["claims"]:
            rows.extend(
                [
                    f"{claim['id']} · {CLAIM_LABELS[claim['kind']]} · {STATUS[claim['status']]} · {claim['location']}",
                    claim["text"],
                    f"Base dichiarata: {claim['basis']}",
                    f"Fonti: {', '.join(claim['resolved_source_ids'])}; input: {', '.join(claim['resolved_input_ids'])}; calcoli citati: {', '.join(claim['calculation_ids'])}.",
                ]
            )
            for value in claim["resolved_values"]:
                rows.append(
                    f"Importo verificato nel registro: {display(value['value'])} {value['unit']} [{value['calculation_id']}]; importo dichiarato nell'affermazione: {value['asserted_value']} {value['asserted_unit']}."
                )
            rows.extend(claim["limitations"])
            rows.extend(claim["issues"])
            if claim["scenario_ids"]:
                rows.append(
                    f"Risultati condizionati degli scenari: {', '.join(claim['scenario_ids'])}; non sono intervalli statistici."
                )
            if claim["stale_review"]:
                rows.append(
                    "La precedente revisione dell'affermazione non vale per queste dipendenze."
                )
            if not claim["review_dependencies_ready"]:
                rows.append(
                    "Le evidenze o i metodi collegati richiedono ancora revisione."
                )
        sections.append(("Affermazioni e riscontri", rows))
    conclusion = report["conclusion"]
    sections.append(
        (
            "Confronto e conclusione",
            [
                (
                    f"{STATUS[conclusion['status']]}: {conclusion['text']}"
                    if conclusion
                    else "Conclusione professionale non ancora registrata. I risultati dei metodi rimangono separati; non è applicata una media automatica."
                )
            ]
            + (
                [
                    (
                        f"Affermazioni collegate: {', '.join(conclusion.get('claim_ids', []))}."
                        if conclusion.get("claim_ids")
                        else "La conclusione non contiene collegamenti strutturati al registro delle affermazioni."
                    )
                ]
                if conclusion
                else []
            ),
        )
    )
    sections.append(
        (
            "Limiti e verifiche aperte",
            [
                mandate["professional_limitations"],
                *case["limitations"],
                *_readable_issues(report),
                "Il DCF usa anni interi a fine anno salvo calendario esplicito del metodo. Gli importi dei periodi parziali o mensili devono essere forniti: non sono riproporzionati automaticamente. Il metodo misto resta annuale.",
                "La registrazione del revisore è una dichiarazione locale, non autenticazione dell'identità o firma professionale.",
            ],
        )
    )
    sections.append(
        (
            "Fonti e ipotesi",
            [
                f"{row['id']} · {row['description']} · {row['path']} · SHA-256 {row['sha256']}"
                for row in case["sources"]
            ]
            + [
                f"{row['id']}: {row['description']} · {row['value'] if row['value'] is not None else 'mancante'} {row['unit']} · {row['kind']} / {row['status']} · fonte {', '.join(row['source_ids'])} · {row['locator']}"
                for row in case["inputs"]
            ],
        )
    )
    sections.append(
        (
            "Quali dati arrivano al modello",
            [
                "Il modello può leggere i documenti selezionati, gli estratti di bilancio e piano, le ipotesi, le fonti benchmark, le rettifiche e le decisioni del professionista. Questi materiali possono contenere dati reali di clienti e persone; non vengono anonimizzati automaticamente.",
                "Il motore locale calcola i metodi e produce il registro e le esportazioni senza chiamare servizi esterni. La scelta e l'interpretazione dei dati restano nel contesto del modello del servizio utilizzato. Le fonti pubbliche sono ricercate dal modello usando solo quesiti pubblici. L'acquisizione opzionale dei benchmark NYU o BCE invia gli URL pubblici selezionati e metadati di connessione ai rispettivi siti, e conserva fonte e condizioni d'uso nel fascicolo. Il resoconto dei dati effettivamente letti è consegnato separatamente nel report privacy del run.",
            ],
        )
    )
    return sections


def compile_html(report: dict) -> str:
    """Escape every authored field; the report loads no remote assets or code."""
    escape = html.escape
    parts = [
        "<!doctype html><html lang='it'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Valutazione d’impresa</title><style>body{font:17px/1.6 Arial,sans-serif;color:#15253a;margin:0;background:#fff}main{max-width:920px;margin:60px auto;padding:0 28px}h1{font-size:40px;line-height:1.15}h2{font-size:24px;color:#002060;margin-top:40px}p{overflow-wrap:anywhere}section{border-top:1px solid #dce2e8;margin-top:32px}small{color:#526171}summary{cursor:pointer}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}code{font-size:12px}@media print{main{margin:0}section{break-inside:auto}h2{break-after:avoid}}</style><main>",
        f"<small>VERA · {escape(STATUS[report['status']])}</small><h1>Valutazione d’impresa</h1>",
    ]
    for heading, paragraphs in report_sections(report):
        parts.append(f"<section><h2>{escape(heading)}</h2>")
        parts.extend(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        parts.append("</section>")
    parts.append("</main></html>")
    return "".join(parts)


def _literal(cell: object, value: str) -> None:
    cell.value = value
    cell.data_type = "s"


def _write_plan_bridge(workbook: Any, report: dict, input_rows: dict[str, int]) -> None:
    """Expose the exact reconciled bridge and link its flows into the formula graph."""
    plan = report["plan_bridge"]
    if not plan:
        return
    sheet = workbook.create_sheet("Piano FCFF")
    sheet.append(
        [
            "Periodo",
            "EBIT",
            "Imposte operative per cassa",
            "Ammortamenti",
            "Investimenti",
            "CCN apertura",
            "CCN chiusura",
            "Variazione CCN",
            "FCFF",
            "FCFF esatto",
            "Calcoli del piano",
        ]
    )
    for index, row in enumerate(plan["monthly"], 2):
        opening = (
            f"='Dati'!C{input_rows[plan['binding']['opening_operating_nwc']]}"
            if index == 2
            else f"=G{index-1}"
        )
        sheet.append(
            [
                row["period"],
                float(decimal(row["ebit"])),
                f"='Dati'!C{input_rows[row['tax_input_id']]}",
                float(decimal(row["depreciation_amortization"])),
                float(decimal(row["capital_expenditure"])),
                opening,
                float(decimal(row["ending_nwc"])),
                f"=G{index}-F{index}",
                f"=B{index}-C{index}+D{index}-E{index}-H{index}",
                row["fcff"],
                ", ".join(row["plan_calculation_ids"]),
            ]
        )
        for column in (1, 10, 11):
            _literal(sheet.cell(index, column), str(sheet.cell(index, column).value))
    for index, ref in enumerate(plan["flow_input_ids"]):
        if plan["flow_frequency"] == "monthly":
            formula = f"='Piano FCFF'!I{index+2}"
        else:
            formula = f"=SUM('Piano FCFF'!I{index*12+2}:I{index*12+13})"
        workbook["Dati"].cell(input_rows[ref], 3, formula)


def write_workbook(path: Path, report: dict) -> None:
    """Link input cells and formula nodes; prevent formula injection from labels."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Sintesi"
    inputs = workbook.create_sheet("Dati")
    calculations = workbook.create_sheet("Calcoli")
    sources = workbook.create_sheet("Fonti")
    mandate_sheet = workbook.create_sheet("Incarico")
    mandate_sheet.append(["Campo", "Valore", "Stato", "Fonti", "Posizione"])
    mandate_sheet.append(
        ["Revisione dell'incarico", STATUS[report["mandate_assessment"]["status"]]]
    )
    for row in _mandate_rows(report):
        mandate_sheet.append(row)
    for row in mandate_sheet:
        for cell in row:
            if cell.value is not None:
                _literal(cell, str(cell.value))
    finite_methods = [
        method for method in report["methods"] if "income_basis" in method
    ]
    if finite_methods:
        income_sheet = workbook.create_sheet("Base reddituale")
        income_sheet.append(
            ["Metodo", "Campo", "Descrizione", "Stato", "Fonti", "Posizione"]
        )
        for method in finite_methods:
            basis = method["income_basis"]
            for key, label in (
                ("capital_maintenance", "Mantenimento del capitale"),
                ("reinvestment", "Reinvestimenti"),
                ("distributions", "Distribuzioni e disponibilità"),
                ("residual_basis", "Residuo e duplicazioni"),
            ):
                income_sheet.append(
                    [
                        method["method_id"],
                        label,
                        basis[key],
                        (
                            "Confermata"
                            if basis["status"] == "confirmed"
                            else "Da confermare"
                        ),
                        ", ".join(basis["source_ids"]),
                        basis["locator"],
                    ]
                )
        for row in income_sheet:
            for cell in row:
                _literal(cell, str(cell.value))
    summary.append(["Valutazione d'impresa", report["case"]["entity_name"]])
    summary.append(["Stato", STATUS[report["status"]]])
    summary.append(["Uso", NOTICE])
    summary.append(["Metodo", "Base", "Valore", "Capitale proprio", "Stato"])
    inputs.append(
        [
            "ID",
            "Descrizione",
            "Valore",
            "Unità",
            "Tipo",
            "Revisione",
            "Fonti",
            "Posizione",
            "Valore esatto",
        ]
    )
    input_rows = {}
    for index, item in enumerate(report["case"]["inputs"], 2):
        input_rows[item["id"]] = index
        inputs.append(
            [
                item["id"],
                item["description"],
                float(decimal(item["value"])) if item["value"] is not None else None,
                item["unit"],
                item["kind"],
                item["status"],
                ", ".join(item["source_ids"]),
                item["locator"],
                item["value"],
            ]
        )
        for column in (1, 2, 4, 5, 6, 7, 8, 9):
            _literal(
                inputs.cell(index, column), str(inputs.cell(index, column).value or "")
            )
    _write_plan_bridge(workbook, report, input_rows)
    calculations.append(
        [
            "Calculation ID",
            "Formula",
            "Unità",
            "Valore esatto motore",
            "Input ID",
            "Source ID",
        ]
    )
    row_ids = {}
    for index, row in enumerate(report["calculations"], 2):
        args = [f"B{row_ids[ref]}" for ref in row["arguments"]]
        if row["op"] == "input":
            formula = f"='Dati'!C{input_rows[row['input_ids'][0]]}"
        elif row["op"] == "constant":
            formula = float(decimal(row["value"]))
        elif row["op"] == "sum":
            formula = f"=SUM({','.join(args)})" if args else "=0"
        elif row["op"] == "exp":
            formula = f"=EXP({args[0]})"
        else:
            symbol = {"subtract": "-", "multiply": "*", "divide": "/", "power": "^"}[
                row["op"]
            ]
            formula = f"={args[0]}{symbol}{args[1]}"
        calculations.append(
            [
                row["id"],
                formula,
                row["unit"],
                row["value"],
                ", ".join(row["input_ids"]),
                ", ".join(row["source_ids"]),
            ]
        )
        row_ids[row["id"]] = index
        for column in (1, 3, 4, 5, 6):
            _literal(
                calculations.cell(index, column),
                str(calculations.cell(index, column).value or ""),
            )
    if report["statements"]:
        statement_sheet = workbook.create_sheet("Quadrature")
        statement_sheet.append(
            [
                "Bilancio",
                "Periodo",
                "Perimetro",
                "Controllo",
                "Atteso",
                "Riscontrato",
                "Differenza",
                "Stato",
                "Fonti",
            ]
        )
        for statement in report["statements"]:
            for check in statement.get("checks", []) or [
                {"label": "; ".join(statement["issues"])}
            ]:
                statement_sheet.append(
                    [
                        statement["id"],
                        f"{statement['period_start']} – {statement['period_end']}",
                        statement["perimeter_description"],
                        check["label"],
                        *[
                            (
                                f"='Calcoli'!B{row_ids[check[key]]}"
                                if key in check
                                else None
                            )
                            for key in ("expected_id", "actual_id", "difference_id")
                        ],
                        STATUS[statement["status"]],
                        ", ".join(statement["source_ids"]),
                    ]
                )
                for column in (1, 2, 3, 4, 8, 9):
                    _literal(
                        statement_sheet.cell(statement_sheet.max_row, column),
                        str(
                            statement_sheet.cell(statement_sheet.max_row, column).value
                        ),
                    )
    for method in report["methods"]:
        value = (
            f"='Calcoli'!B{row_ids[method['value_id']]}"
            if "value_id" in method
            else None
        )
        equity = (
            f"='Calcoli'!B{row_ids[method['equity_id']]}"
            if method.get("equity_id")
            else None
        )
        summary.append(
            [
                _method_label(method["kind"]),
                {
                    "operating_enterprise": "Valore operativo",
                    "equity": "Capitale proprio",
                }.get(method.get("value_type"), ""),
                value,
                equity,
                STATUS[method["status"]],
            ]
        )
    sources.append(["ID", "Descrizione", "Percorso", "SHA-256", "Revisione"])
    for index, source in enumerate(report["case"]["sources"], 2):
        for column, key in enumerate(
            ("id", "description", "path", "sha256", "status"), 1
        ):
            _literal(sources.cell(index, column), source[key])
    if report["normalizations"]:
        journal = workbook.create_sheet("Rettifiche")
        journal.append(
            [
                "ID",
                "Voce",
                "Anno",
                "Tipo",
                "Importo",
                "Motivo e trattamento",
                "Stato",
                "Fonti e posizione",
                "Revisore",
            ]
        )
        for group in report["normalizations"]:
            journal.append(
                [
                    group["id"],
                    group["line"],
                    group["year"],
                    "Rettificato calcolato",
                    (
                        f"='Calcoli'!B{row_ids[group['value_id']]}"
                        if "value_id" in group
                        else None
                    ),
                    f"Riportato: {group['reported_input']}; rettificato dichiarato: {group['adjusted_input']}. {group.get('reason', '')}",
                    STATUS[group["status"]],
                    ", ".join(group["source_ids"]),
                    "",
                ]
            )
            for entry in group["adjustments"]:
                journal.append(
                    [
                        entry["id"],
                        group["line"],
                        group["year"],
                        "Rettifica con segno",
                        (
                            f"='Dati'!C{input_rows[entry['amount_input']]}"
                            if next(
                                item
                                for item in report["case"]["inputs"]
                                if item["id"] == entry["amount_input"]
                            )["value"]
                            is not None
                            else None
                        ),
                        f"{entry['reason']}\nQuadratura: {entry['accounting_check']}\nSostanza: {entry['economic_rationale']}\nImposte: {entry['tax_treatment']}\nReversibilità: {entry['reversibility']}",
                        STATUS[entry["status"]],
                        f"{', '.join(entry['source_ids'])} · {entry['locator']}",
                        (entry.get("review") or {}).get("reviewer", "Non registrato"),
                    ]
                )
        for row in journal.iter_rows(min_row=2):
            for column in (0, 1, 3, 5, 6, 7, 8):
                _literal(row[column], str(row[column].value or ""))
    if report["claims"]:
        claims = workbook.create_sheet("Affermazioni")
        claims.append(
            [
                "ID",
                "Testo / dato",
                "Tipo",
                "Stato",
                "Valore dal registro",
                "Base e limiti",
                "Calcoli / input",
                "Fonti",
                "Revisore",
            ]
        )
        for claim in report["claims"]:
            claims.append(
                [
                    claim["id"],
                    claim["text"],
                    CLAIM_LABELS[claim["kind"]],
                    STATUS[claim["status"]],
                    None,
                    "\n".join(
                        [claim["basis"], *claim["limitations"], *claim["issues"]]
                    ),
                    ", ".join(
                        [*claim["calculation_ids"], *claim["resolved_input_ids"]]
                    ),
                    ", ".join(claim["resolved_source_ids"]),
                    (claim.get("review") or {}).get("reviewer", "Non registrato"),
                ]
            )
            for value in claim["resolved_values"]:
                claims.append(
                    [
                        claim["id"],
                        value["calculation_id"],
                        value["unit"],
                        STATUS[claim["status"]],
                        f"='Calcoli'!B{row_ids[value['calculation_id']]}",
                        f"Dichiarato: {value['asserted_value']} {value['asserted_unit']}",
                        value["calculation_id"],
                        "",
                        "",
                    ]
                )
        for row in claims.iter_rows(min_row=2):
            for column in (0, 1, 2, 3, 5, 6, 7, 8):
                _literal(row[column], str(row[column].value or ""))
    _literal(summary["B1"], report["case"]["entity_name"])
    summary.merge_cells("B3:E3")
    summary.row_dimensions[3].height = 42
    summary.row_dimensions[1].height = 30
    for sheet in workbook:
        sheet.freeze_panes = "C5" if sheet == summary else "C2"
        sheet.sheet_view.showGridLines = False
        sheet.auto_filter.ref = (
            sheet.dimensions if sheet != summary else f"A4:E{sheet.max_row}"
        )
        for row in sheet:
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.font = Font(
                    name="Arial",
                    size=10,
                    color="002060" if cell.data_type == "f" else "172737",
                )
                if cell.data_type == "n" or cell.data_type == "f":
                    cell.number_format = '#,##0.00;[Red](#,##0.00);"–"'
        for cell in sheet[4 if sheet == summary else 1]:
            cell.fill = PatternFill("solid", fgColor="002060")
            cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
        for column in "ABCDEFGHI":
            sheet.column_dimensions[column].width = 24 if column not in "AB" else 40
        sheet.print_options.horizontalCentered = True
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
    if report["normalizations"]:
        journal.column_dimensions["F"].width = 70
        for cell in journal["C"][1:]:
            cell.number_format = "0"
    if report["plan_bridge"]:
        workbook["Piano FCFF"].column_dimensions["A"].width = 14
        workbook["Piano FCFF"].column_dimensions["B"].width = 24
        workbook["Piano FCFF"].column_dimensions["J"].width = 28
        workbook["Piano FCFF"].column_dimensions["K"].width = 54
    mandate_sheet.column_dimensions["B"].width = 80
    mandate_sheet.column_dimensions["E"].width = 60
    workbook.save(path)


def _write_workpapers(directory: Path, report: dict) -> None:
    """Export named contract artifacts from the same canonical result, not copies of guesses."""
    case = report["case"]
    workpapers = {
        "mandate": {
            "mandate": case["mandate"],
            "assessment": report["mandate_assessment"],
            "purpose_coverage": report["purpose_coverage"],
        },
        "evidence": {
            "sources": case["sources"],
            "inputs": case["inputs"],
            "statements": report["statements"],
        },
        "normalizations": report["normalizations"],
        "forecast_binding": report["plan_bridge"],
        "method_decisions": report["methods"],
        "benchmark_observations": [
            {
                "input_id": row["id"],
                "value": row["value"],
                "unit": row["unit"],
                "source_ids": row["source_ids"],
                "benchmark": row["benchmark"],
            }
            for row in case["inputs"]
            if "benchmark" in row
        ],
        "calculations": report["calculations"],
        "sensitivity": report["sensitivity"],
        "valuation_conclusion": report["conclusion"],
        "claim_registry": report["claims"],
        "professional_review": {
            "status": report["status"],
            "identity": report["review_identity"],
            "mandate": report["mandate_assessment"],
            "statements": report["statements"],
            "methods": [
                {
                    "method_id": row["method_id"],
                    "status": row["status"],
                    "review": row.get("review"),
                    "dependency_sha256": row.get("dependency_sha256"),
                }
                for row in report["methods"]
            ],
            "adjustments": [
                {"normalization_id": group["id"], "adjustments": group["adjustments"]}
                for group in report["normalizations"]
            ],
            "claims": report["claims"],
            "conclusion": report["conclusion"],
        },
    }
    for name, data in workpapers.items():
        payload = {
            "schema_version": "vera.business_valuation.workpaper.v1",
            "kind": name,
            "case_sha256": report["case_sha256"],
            "report_sha256": report["report_sha256"],
            "data": data,
        }
        (directory / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _write_documents(directory: Path, report: dict) -> None:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    document = Document()
    document.sections[0].top_margin = Inches(0.75)
    document.sections[0].bottom_margin = Inches(0.75)
    for name in ("Normal", "Title", "Heading 1"):
        document.styles[name].font.name = "Arial"
        document.styles[name].font.color.rgb = RGBColor.from_string(
            "000000"
            if name == "Title"
            else "002060" if name == "Heading 1" else "172737"
        )
    document.styles["Normal"].font.size = Pt(10)
    for border in document.styles["Title"].element.xpath("./w:pPr/w:pBdr"):
        border.getparent().remove(border)
    document.add_paragraph("Valutazione d’impresa", "Title")
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 14
    styles["Normal"].alignment = TA_LEFT
    styles["Heading2"].keepWithNext = True
    content = [Paragraph("Valutazione d’impresa", styles["Title"]), Spacer(1, 12)]
    for heading, paragraphs in report_sections(report):
        document.add_heading(heading, level=1)
        group = [Paragraph(html.escape(heading), styles["Heading2"])]
        method_section = heading in METHOD_LABELS.values()
        for index, paragraph in enumerate(paragraphs):
            item = document.add_paragraph(paragraph)
            if method_section and index < len(paragraphs) - 1:
                item.paragraph_format.keep_with_next = True
            group.extend(
                [Paragraph(html.escape(paragraph), styles["Normal"]), Spacer(1, 7)]
            )
        content.extend([KeepTogether(group)] if method_section else group)
    document.save(directory / "valuation_report.docx")

    def footer(canvas: object, doc: object) -> None:
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            42, 24, f"Vera · {STATUS[report['status']]} · Carte di lavoro"
        )
        canvas.drawRightString(A4[0] - 42, 24, str(doc.page))

    SimpleDocTemplate(
        str(directory / "valuation_report.pdf"),
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    ).build(content, onFirstPage=footer, onLaterPages=footer)


def write_package(
    report: dict, source_root: Path, output: Path, *, replay_parent: Path | None = None
) -> list[dict]:
    """Replay before exporting, never overwrite a previous valuation revision."""
    require(
        report
        == build_valuation(report["case"], source_root, replay_parent=replay_parent),
        "Valuation differs from canonical replay",
    )
    require(
        not output.exists(),
        "Use a new revision directory; previous outputs are immutable",
    )
    output.mkdir(parents=True)
    (output / "valuation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_workpapers(output, report)
    (output / "valuation_report.html").write_text(
        compile_html(report), encoding="utf-8"
    )
    (output / "valuation_report.md").write_text(
        "# Valutazione d’impresa\n\n"
        + "\n\n".join(
            f"## {heading}\n\n" + "\n\n".join(rows)
            for heading, rows in report_sections(report)
        ),
        encoding="utf-8",
    )
    with (output / "calculations.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "value", "unit", "op", "arguments", "input_ids", "source_ids"]
        )
        for row in report["calculations"]:
            writer.writerow(
                [
                    row["id"],
                    row["value"],
                    row["unit"],
                    row["op"],
                    " | ".join(row["arguments"]),
                    " | ".join(row["input_ids"]),
                    " | ".join(row["source_ids"]),
                ]
            )
    write_workbook(output / "valuation_workbook.xlsx", report)
    _write_documents(output, report)
    artifacts = [
        {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(output.iterdir())
        if path.is_file()
    ]
    (output / "artifacts.json").write_text(
        json.dumps(artifacts, indent=2) + "\n", encoding="utf-8"
    )
    return artifacts
