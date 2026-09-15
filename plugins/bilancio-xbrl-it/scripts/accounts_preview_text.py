"""Translate fixed workflow wording without rewriting case-specific judgments."""

from __future__ import annotations

import re
from typing import Any, Mapping

__all__ = ["preview_text", "preview_check_message", "preview_reason"]

# Exact source strings make a changed rule-pack question visible to the release
# check. This is UI localization, not a classifier or a substitute for review.
_ITALIAN = {
    "Accounting policies applied": "Criteri di valutazione applicati",
    "Current approved accounting-policy schedule": "Prospetto corrente dei criteri di valutazione approvati",
    "Allocation of profit or coverage of loss": "Destinazione dell’utile o copertura della perdita",
    "Resolution or proposed allocation": "Delibera o proposta di destinazione del risultato",
    "Basis and form of preparation": "Criteri generali e forma del bilancio",
    "Approved form decision and accounting-policy evidence": "Scelta della forma approvata e documentazione dei criteri di valutazione",
    "Changes in accounting policies": "Cambiamenti nei criteri di valutazione",
    "Explicit annual confirmation and policy-change evidence where applicable": "Conferma annuale esplicita e documentazione degli eventuali cambiamenti nei criteri",
    "Contingent liabilities": "Passività potenziali",
    "Legal claims register or explicit annual confirmation": "Prospetto dei contenziosi o conferma annuale esplicita",
    "Corrections of material prior-period errors": "Correzioni di errori rilevanti di esercizi precedenti",
    "Explicit annual confirmation and correction schedule where applicable": "Conferma annuale esplicita e prospetto delle eventuali correzioni",
    "Current and deferred taxes": "Imposte correnti, anticipate e differite",
    "Tax computation": "Calcolo delle imposte",
    "Debts by maturity and security": "Debiti per scadenza e garanzie",
    "Loan plans or payable maturity schedule": "Piani di rimborso o scadenziario dei debiti",
    "December 2025 OIC amendments review": "Revisione degli emendamenti OIC di dicembre 2025",
    "Professional applicability assessment for each amended standard, or an explicit not-applicable reason": "Valutazione professionale dell’applicabilità di ogni principio modificato o motivazione esplicita della non applicabilità",
    "Derivatives and fair-value reserve": "Derivati e riserva di fair value",
    "Contracts, valuations, or explicit annual confirmation": "Contratti, valutazioni o conferma annuale esplicita",
    "Employees and corporate bodies": "Dipendenti e organi sociali",
    "Payroll and compensation schedules": "Prospetti del personale e dei compensi",
    "Finance leases": "Leasing finanziari",
    "Lease contracts and schedules": "Contratti e prospetti dei leasing",
    "Fixed-asset movements and impairment": "Movimenti e perdite durevoli di valore delle immobilizzazioni",
    "Fixed-asset register and ledger detail": "Registro dei cespiti e dettaglio contabile",
    "Going-concern uncertainties": "Incertezze sulla continuità aziendale",
    "Explicit annual confirmation and assessment where triggered": "Conferma annuale esplicita e valutazione quando richiesta dal caso",
    "Group and participation information": "Informazioni su gruppo e partecipazioni",
    "Participation and group schedule": "Prospetto delle partecipazioni e del gruppo",
    "Guarantees and commitments": "Garanzie e impegni",
    "Register or explicit annual confirmation": "Registro o conferma annuale esplicita",
    "Inventory movements and valuation evidence": "Movimenti delle rimanenze e documentazione della valutazione",
    "Inventory ledger, count or alternative procedures, costing records, net-realisable-value and obsolescence assessments, and pledge evidence": "Contabilità di magazzino, inventario fisico o procedure alternative, calcolo dei costi, valutazioni del valore netto di realizzo e dell’obsolescenza, documentazione dei pegni",
    "Material post-closing events": "Fatti rilevanti successivi alla chiusura",
    "Explicit annual confirmation": "Conferma annuale esplicita",
    "OIC 34 revenue-recognition review": "Revisione della rilevazione dei ricavi secondo OIC 34",
    "Professional OIC 34 assessment and material contract review, or an explicit not-applicable reason": "Valutazione professionale OIC 34 e revisione dei contratti rilevanti o motivazione esplicita della non applicabilità",
    "Off-balance-sheet arrangements": "Accordi non risultanti dallo stato patrimoniale",
    "Contract register or explicit annual confirmation": "Registro dei contratti o conferma annuale esplicita",
    "Other triggered statutory disclosures": "Altre informazioni civilistiche richieste dal caso",
    "Topic-specific supporting schedules": "Prospetti di supporto relativi alla materia",
    "Provisions and TFR movements": "Movimenti dei fondi e del TFR",
    "Provisions and payroll/TFR schedules": "Prospetti dei fondi, del personale e del TFR",
    "Receivable maturity and geography": "Scadenze e distribuzione geografica dei crediti",
    "Receivable aging or maturity schedule": "Scadenziario o analisi dell’anzianità dei crediti",
    "Related-party transactions": "Operazioni con parti correlate",
    "Related-party schedule and explicit confirmation": "Prospetto delle parti correlate e conferma esplicita",
    "Revenue and significant income-statement details": "Ricavi e dettagli rilevanti del conto economico",
    "Revenue and ledger analysis": "Analisi dei ricavi e dei mastri contabili",
    "Substantive taxonomy representation differences": "Differenze sostanziali nella rappresentazione tassonomica",
    "Explicit annual confirmation and differences analysis where applicable": "Conferma annuale esplicita e analisi delle eventuali differenze",
    "Transactions not concluded on market terms": "Operazioni non concluse a condizioni di mercato",
    "Explicit annual confirmation and transaction schedule where applicable": "Conferma annuale esplicita e prospetto delle eventuali operazioni",
    "The micro footer-versus-notes treatment is not confirmed": "La scelta tra informazioni in calce e nota integrativa per la micro-impresa non è confermata",
    "Current assets do not equal liabilities and equity": "Per l’esercizio corrente, l’attivo non coincide con il passivo e il patrimonio netto",
    "Comparative assets do not equal liabilities and equity": "Per l’esercizio comparativo, l’attivo non coincide con il passivo e il patrimonio netto",
    "Primary statutory taxonomy presentation coverage has not been reviewed": "La copertura delle voci dei prospetti civilistici non è stata rivista",
    "An effective-dated disclosure rule pack has not been activated": "Non è stato attivato il pacchetto delle informazioni richieste valido per l’esercizio",
    "The prior filed XBRL is not attached for comparative and opening checks": "Il precedente XBRL depositato non è allegato per i controlli comparativi e sui saldi iniziali",
    "The debit/credit convention is not confirmed": "La convenzione Dare/Avere non è confermata",
    "Statements have not been computed": "I prospetti non sono stati calcolati",
    "A trial balance is required": "È necessaria una situazione contabile",
}

_FLAGS = {
    "EMPLOYEES_OR_BODIES_PRESENT": (
        "dipendenti o organi sociali",
        "employees or corporate bodies",
    ),
    "FINANCE_LEASES_PRESENT": ("leasing finanziari", "finance leases"),
    "GROUP_OR_PARTICIPATIONS_PRESENT": (
        "gruppo o partecipazioni",
        "group or participations",
    ),
    "OTHER_STATUTORY_DISCLOSURES_REQUIRED": (
        "altre informazioni civilistiche",
        "other statutory disclosures",
    ),
    "REVENUE_OR_EXCEPTIONAL_DETAIL_REQUIRED": (
        "ricavi o componenti eccezionali",
        "revenue or exceptional items",
    ),
}

_SECTIONS = {
    "INTRODUCTION": ("introduzione alla nota", "introduction to the notes"),
    "POLICIES": ("criteri di valutazione", "accounting policies"),
    "COMMITMENTS_RELATED": (
        "impegni e rapporti correlati",
        "commitments and related matters",
    ),
    "POST_CLOSING_GOING_CONCERN": (
        "fatti successivi e continuità aziendale",
        "subsequent events and going concern",
    ),
    "ADDITIONAL": ("ulteriori informazioni", "additional information"),
}


def preview_text(value: Any, language: str) -> str:
    """Translate only an exact fixed string; retain unknown and authored text."""
    text = "—" if value is None else str(value)
    return _ITALIAN.get(text, text) if language == "it" else text


def preview_reason(value: Any, language: str) -> str:
    """Localize the disclosure engine's exact reason formats, retaining prose."""
    reason = "—" if value is None else str(value)
    locale = 0 if language == "it" else 1
    schedules = {
        "FIXED_ASSETS": ("immobilizzazioni", "fixed assets"),
        "INVENTORIES": ("rimanenze", "inventories"),
        "RECEIVABLES": ("crediti", "receivables"),
        "PAYABLES": ("debiti", "payables"),
        "EQUITY": ("patrimonio netto", "equity"),
        "PROVISIONS": ("fondi", "provisions"),
        "TFR": ("trattamento di fine rapporto", "severance pay"),
        "TAXES": ("imposte", "taxes"),
        "GUARANTEES_COMMITMENTS": ("garanzie e impegni", "guarantees and commitments"),
        "CASH_FLOW": ("rendiconto finanziario", "cash flow"),
    }
    translated = []
    for part in reason.split("; "):
        if part == "always applicable for the selected form":
            translated.append(
                (
                    "Richiesto per la forma di bilancio scelta",
                    "Required for the selected statutory form",
                )[locale]
            )
            continue
        schedule = re.fullmatch(
            r"schedule (\w+) is present or reviewer-triggered", part
        )
        if schedule and schedule[1] in schedules:
            subject = schedules[schedule[1]][locale]
            translated.append(
                (
                    f"Prospetto presente o richiesto dal revisore: {subject}"
                    if locale == 0
                    else f"Schedule present or requested by the reviewer: {subject}"
                )
            )
            continue
        flag = re.fullmatch(r"reviewer trigger (\w+)", part)
        if flag and flag[1] in _FLAGS:
            subject = _FLAGS[flag[1]][locale]
            translated.append(
                (
                    f"Informazione richiesta dal revisore: {subject}"
                    if locale == 0
                    else f"Disclosure requested by the reviewer: {subject}"
                )
            )
            continue
        line = re.fullmatch(r"statement line (.+) is non-zero", part)
        if line:
            translated.append(
                (
                    f"La voce {line[1]} ha un importo diverso da zero"
                    if locale == 0
                    else f"Statement item {line[1]} has a non-zero amount"
                )
            )
            continue
        return reason
    return "; ".join(translated)


def preview_check_message(
    issue: Mapping[str, Any], case: Mapping[str, Any], language: str
) -> str:
    """Display known native message formats with their exact declared subjects."""
    message = str(issue.get("message") or "")
    locale = 0 if language == "it" else 1
    count = re.fullmatch(r"(\d+) annual negative confirmations are missing", message)
    if count:
        return (
            f"Mancano {count[1]} conferme annuali sull’assenza delle fattispecie richieste"
            if language == "it"
            else f"{count[1]} annual confirmations of absence are missing"
        )
    manual_prefix = "Disclosure applicability requires professional decisions for: "
    if message.startswith(manual_prefix):
        flags = message[len(manual_prefix) :].split(", ")
        subjects = [_FLAGS.get(flag, (flag, flag))[locale] for flag in flags]
        prefix = (
            "Occorre una decisione professionale sulle informazioni applicabili a: "
            if language == "it"
            else "Professional decisions are needed on disclosures for: "
        )
        return prefix + "; ".join(subjects)
    missing_prefix = "Triggered disclosure is incomplete: "
    if message.startswith(missing_prefix):
        answers = {
            str(q.get("answer_key")): str(q.get("title"))
            for q in case.get("questionnaire", [])
            if q.get("answer_key") and q.get("title")
        }
        subjects = []
        for item in message[len(missing_prefix) :].split(", "):
            kind, separator, key = item.partition(":")
            if separator and kind == "ANSWER" and key in answers:
                subjects.append(preview_text(answers[key], language))
            elif separator and kind == "NARRATIVE_SECTION" and key in _SECTIONS:
                subjects.append(_SECTIONS[key][locale])
            else:
                subjects.append(item)
        prefix = "Da completare: " if language == "it" else "To complete: "
        return prefix + "; ".join(subjects)
    return preview_text(message, language)
