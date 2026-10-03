"""Render source-backed anomaly records and an unsent, per-client review draft.

This is a mechanical presentation of supplied facts and reviewed proposals.
It neither diagnoses a discrepancy nor chooses a tax remedy or filing deadline.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from lipe_core import money

__all__ = ["write_review_documents"]

STATES = {
    "OPEN": "Da decidere",
    "STALE_DECISION": "Decisione non più riferita ai dati correnti",
    "RESOLUTION_RECORDED": "Decisione professionale registrata (identità non autenticata)",
}
RESOLUTIONS = {
    "NO_CHANGE": "Dati confermati senza modifiche",
    "INPUTS_REVISED": "Revisore dichiara gli input aggiornati",
}


def _text(value: str | None) -> str:
    # Prevent embedded Markdown/HTML from turning source text into remote content.
    plain = "non disponibile" if value is None else " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", html.escape(plain, quote=False))


def _euros(value: str | None) -> str:
    return (
        "non determinato"
        if value is None
        else f"{money(value):,.2f}".translate(str.maketrans(",.", ".,")) + " €"
    )


def _sentence(value: str) -> str:
    return value if value.endswith((".", "!", "?")) else value + "."


def _source(ref: dict | None, case: dict) -> str:
    if ref is None:
        return "fonte non disponibile"
    filename = next(
        item["path"]
        for item in case["sources"]
        if item["source_id"] == ref["source_id"]
    )
    return f"{_text(filename)}, p. {ref['page']}"


def _sources(refs: list[dict], case: dict) -> str:
    return (
        "; ".join(dict.fromkeys(_source(ref, case) for ref in refs))
        or "fonti da completare"
    )


def _document(document: dict, case: dict) -> str:
    when = (
        date.fromisoformat(document["date"]).strftime("%d/%m/%Y")
        if document["date"]
        else "non disponibile"
    )
    return (
        f"Protocollo {_text(document['protocol'])}; fattura {_text(document['invoice_number'])}; "
        f"data {when}; controparte {_text(document['counterparty'])}; "
        f"importo {_euros(document['amount'])} ({_text(document['amount_basis'])}). "
        f"Fonte: {_source(document['evidence'], case)}."
    )


def _effect(observation: dict) -> str:
    return (
        "; ".join(
            f"periodo {effect['period']}: {_euros(effect['amount'])} — {_text(effect['basis'])}"
            for effect in observation["vp6_effect"]
        )
        or "non determinato"
    )


def _comparison(item: dict, case: dict) -> str:
    refs = list(item["register_evidence"])
    if item["liquidation_evidence"]:
        refs.append(item["liquidation_evidence"])
    sides = {"SALES": "vendite", "PURCHASES": "acquisti", "INTEGRATION": "integrazioni"}
    bases = {
        "REGISTRATION": "registrazione",
        "CHARGEABILITY": "esigibilità",
        "DEDUCTION": "detrazione",
    }
    taxes = {
        "RECORDED": "IVA registrata",
        "OUTPUT": "IVA esigibile",
        "DEDUCTIBLE": "IVA detraibile",
    }
    return (
        f"Periodo {item['period']}, codice {_text(item['code'])} ({sides[item['side']]}): "
        f"base registro {_euros(item['register_base'])}, base liquidazione {_euros(item['liquidation_base'])}, "
        f"scarto {_euros(item['base_difference'])}; IVA registro {_euros(item['register_tax'])}, "
        f"IVA liquidazione {_euros(item['liquidation_tax'])}, scarto {_euros(item['tax_difference'])}. "
        f"Criteri: {bases[item['base_basis']]} / {taxes[item['tax_basis']]}. "
        f"Fonti: {_sources(refs, case)}. Verificare la completezza e la comparabilità delle righe; "
        "la causa non è ricavata automaticamente dagli importi."
    )


def _questions(
    case: dict, result: dict, include_observations: bool = True
) -> list[str]:
    resolved = [
        item
        for item in result["observations"]
        if item["state"] == "RESOLUTION_RECORDED"
    ]
    comparisons_resolved = {
        key for item in resolved for key in item["related_comparisons"]
    }
    findings_resolved = {key for item in resolved for key in item["related_findings"]}
    questions = []
    for item in result["observations"]:
        if not include_observations or item["state"] == "RESOLUTION_RECORDED":
            continue
        docs = " ".join(_document(document, case) for document in item["documents"])
        questions.append(
            f"{_text(item['observation_id'])} — {_sentence(_text(item['title']))} "
            f"Valutazione proposta: {_sentence(_text(item['assessment']))} {docs} "
            f"Effetto proposto su VP6, non applicato automaticamente: {_sentence(_effect(item))} "
            f"Azione proposta: {_sentence(_text(item['proposed_action']))} "
            f"Fonti: {_sources(item['evidence'], case)}. Stato: {STATES[item['state']]}."
        )
    for item in result["reconciliation"]:
        if (
            item["status"] != "MATCH"
            and item["comparison_id"] not in comparisons_resolved
        ):
            questions.append(_comparison(item, case))
    for item in result["findings"]:
        if item["finding_id"] in findings_resolved:
            continue
        module = next(
            module for module in case["modules"] if module["period"] == item["period"]
        )
        ref = _source(module["evidence"], case)
        if item["code"] == "PAYMENT_DIFFERENCE":
            questions.append(
                f"Periodo {item['period']}: VP14 dovuto {_euros(item['due'])}, capitale F24 documentato "
                f"{_euros(item['paid'])}. Verificare ricevuta, tributo e periodo di riferimento. "
                f"Fonte versamento: {ref}; composizione del dovuto in workpaper.xlsx e result.json. "
                "Lo scarto non dimostra da solo omissione o ritardo e non determina il rimedio fiscale."
            )
        elif item["code"] == "REGISTER_LIQUIDATION_DIFFERENCE":
            questions.append(
                f"Periodo {item['period']}: IVA netta dai registri {_euros(item['register_net_vat'])}, "
                f"IVA netta della liquidazione {_euros(item['reported_liquidation'])}. "
                f"Fonte liquidazione: {ref}; verificare la differenza prima di concludere sulla causa."
            )
    return questions


def _dossier(case: dict, result: dict) -> str:
    lines = [
        "# LIPE — dossier anomalie per revisione",
        "",
        f"Cliente: {_text(case['client_id'])} · {case['tax_year']} · trimestre {case['quarter']}",
        "",
        "Le categorie e gli effetti fiscali sono valutazioni proposte. Le decisioni locali sono attribuite al revisore dichiarato, senza autenticarne l'identità.",
        "",
        f"Risultato: `{result['result_hash']}`",
        "",
    ]
    if case["data_origin"] == "SYNTHETIC":
        lines += [
            "**DATI SINTETICI — nessun caso o giudizio professionale reale.**",
            "",
        ]
    for item in result["observations"]:
        lines += [
            f"## {_text(item['observation_id'])} · {_text(item['title'])}",
            "",
            f"Categoria proposta: {_text(item['category'])}. Stato: {STATES[item['state']]}.",
            "",
            f"Valutazione: {_text(item['assessment'])}",
            "",
            *[_document(document, case) + "\n" for document in item["documents"]],
            f"Effetto proposto su VP6 (non applicato automaticamente): {_sentence(_effect(item))}",
            "",
            f"Azione proposta: {_text(item['proposed_action'])}",
            "",
            f"Fonti: {_sources(item['evidence'], case)}.",
            "",
        ]
        if item["decision"]:
            decision = item["decision"]
            lines += [
                f"Decisione dichiarata: {RESOLUTIONS[decision['resolution']]}. Revisore: {_text(decision['review']['reviewer'])}; data: {decision['review']['reviewed_on']}.",
                "",
                f"Motivazione: {_text(decision['review']['reason'])}",
                "",
            ]
    if not result["observations"]:
        lines += [
            "Nessuna anomalia semantica registrata. Questo non prova l'assenza di errori fiscali.",
            "",
        ]
    lines += ["## Scarti meccanici e punti aperti", ""]
    questions = _questions(case, result, include_observations=False)
    lines += [
        f"{index}. {question}\n" for index, question in enumerate(questions, 1)
    ] or ["Nessuno scarto meccanico irrisolto registrato.", ""]
    if result["blockers"]:
        lines += [
            "## Condizioni che bloccano il calcolo",
            "",
            *[f"- {_text(blocker)}" for blocker in result["blockers"]],
            "",
        ]
    lines += [
        "Riferimenti completi, proposte, decisioni e impronte di revisione: [anomalies.json](anomalies.json).",
        "",
    ]
    return "\n".join(lines)


def _letter(case: dict, result: dict) -> str:
    correspondence = case["correspondence"]
    client = correspondence["client_label"] if correspondence else case["client_id"]
    recipient = correspondence["recipient"] if correspondence else None
    lines = [
        "# Bozza di mail al collega adempimenti fiscali — non inviata",
        "",
        f"Oggetto: LIPE {_text(client)} — {case['tax_year']}, trimestre {case['quarter']}",
        "",
        f"Destinatario: {_text(recipient) if recipient else 'collega responsabile, da identificare'}",
        "",
    ]
    if case["data_origin"] == "SYNTHETIC":
        lines += [
            "**Esempio con dati sintetici: non inviare né usare per una dichiarazione.**",
            "",
        ]
    lines += [
        "Ho predisposto il controllo dei registri, delle liquidazioni e dei versamenti disponibili. Il ricalcolo usa i registri con le attribuzioni confermate; la liquidazione del gestionale serve come confronto. Di seguito riporto l'esito e gli eventuali blocchi. Nessuna comunicazione è stata compilata o inviata dal programma.",
        "",
    ]
    if result["status"] == "DRAFT_FOR_REVIEW":
        lines += [
            "Importi ricalcolati per la bozza, da sottoporre a revisione:",
            "",
            "| Periodo | VP2 | VP3 | VP4 | VP5 | VP14 debito | VP14 credito | Fonti |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for module in result["modules"]:
            period = module["period"]
            refs = [
                item["evidence"]
                for item in result["composition"]
                if any(part["period"] == period for part in item["contributions"])
            ]
            refs += [module["evidence"], case["opening"]["evidence"]]
            values = [
                (
                    "non compilato"
                    if module["rows"][key] is None
                    else _euros(module["rows"][key])
                )
                for key in ("vp2", "vp3", "vp4", "vp5", "vp14_debit", "vp14_credit")
            ]
            lines.append(
                f"| {period} | " + " | ".join(values) + f" | {_sources(refs, case)} |"
            )
        lines += [
            "",
            "Formule, rettifiche, riporto dei saldi precedenti e composizione per riga/codice: [workpaper Excel](workpaper.xlsx) e [risultato con fonti](result.json).",
            "",
        ]
    else:
        lines += [
            "Il calcolo è bloccato dalle condizioni seguenti; non sono disponibili righi da inserire:",
            "",
            *[f"- {_text(blocker)}" for blocker in result["blockers"]],
            "",
        ]
    questions = _questions(case, result)
    lines += ["Punti da chiarire sulle stampe e con il cliente:", ""]
    lines += [
        f"{index}. {question}\n" for index, question in enumerate(questions, 1)
    ] or [
        "Nessuno scarto meccanico irrisolto registrato. Confermare la completezza delle stampe definitive e la revisione fiscale del fascicolo.",
        "",
    ]
    for item in result["observations"]:
        if item["state"] == "RESOLUTION_RECORDED":
            lines += [
                f"Decisione già registrata per {_text(item['observation_id'])}: {RESOLUTIONS[item['decision']['resolution']]}. {_text(item['decision']['review']['reason'])}",
                "",
            ]
    lines += [
        "Se i chiarimenti comportano correzioni, occorrono le stampe definitive corrette e un nuovo ricalcolo prima della revisione conclusiva.",
        "",
    ]
    deadline = correspondence["filing_deadline"] if correspondence else None
    if deadline:
        when = date.fromisoformat(deadline["date"]).strftime("%d/%m/%Y")
        label = (
            "Scadenza registrata dal revisore"
            if deadline["review"]["status"] == "CONFIRMED"
            else "Scadenza proposta, da verificare"
        )
        lines += [f"{label}: {when}. Fonte: {_source(deadline['evidence'], case)}.", ""]
    else:
        lines += [
            "Scadenza della comunicazione: da verificare su una fonte ufficiale corrente e registrare nel fascicolo. Nessuna data è stata assunta automaticamente.",
            "",
        ]
    lines += [
        "Allegati da rivedere: [workpaper](workpaper.md), [Excel](workpaper.xlsx), [dossier anomalie](anomalies.md), [sintesi PDF](summary.pdf).",
        "",
    ]
    return "\n".join(lines)


def write_review_documents(case: dict, result: dict, folder: Path) -> None:
    """Persist a bound dossier and unsent draft; never invent missing case facts."""
    payload = {
        "pipeline": "LIPE",
        "input_hash": result["input_hash"],
        "result_hash": result["result_hash"],
        "status": result["status"],
        "anomaly_review": case["anomaly_review"],
        "observations": result["observations"],
        "mechanical_findings": result["findings"],
        "reconciliation": result["reconciliation"],
        "professional_identity_authenticated": False,
        "proposed_effects_applied_automatically": False,
    }
    outputs = {
        "anomalies.json": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        "anomalies.md": _dossier(case, result),
        "review-request.md": _letter(case, result),
    }
    for name, content in outputs.items():
        with (folder / name).open("x", encoding="utf-8") as stream:
            (folder / name).chmod(0o600)
            stream.write(content)
