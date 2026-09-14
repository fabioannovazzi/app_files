"""Model-authored interpretation of fictional kit inputs, for pipeline checks only.

These unapproved assessments are not shipped as teaching results or approvals.
The working agent must read the selected files and author its own current case.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


def planning_case(paths: list[Path], root: Path, language: str, previous=None):
    """Bind the actual source files and leave every professional review pending."""
    it = language == "it"
    review = {"status": "pending"}
    names = {p.name: p for p in paths}
    periods = ["2027-01", "2027-02", "2027-03"]
    sources, evidence, assumptions = [], [], []
    for index, path in enumerate(paths):
        sid = f"source-{index}"
        prior = path.name == "prior-plan.json"
        sources.append(
            dict(
                id=sid,
                path=path.relative_to(root).as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                version="kit-reading" if not prior else previous["case"]["cycle"]["id"],
                role="prior_plan" if prior else "user_statement",
                review_status="unverified",
                intended_audience=["internal"],
                confidentiality={
                    "classification": "fictional_tutorial",
                    "allowed_audiences": ["internal"],
                },
            )
        )
        record = dict(
            id=f"basis-{index}",
            kind="fact" if prior or "update-" in path.name else "hypothesis",
            description=(
                "Precedente piano effettivamente prodotto"
                if it and prior
                else (
                    "Actual preceding plan"
                    if prior
                    else path.read_text(encoding="utf-8").strip()
                )
            ),
            source_ids=[sid],
            **review,
        )
        if record["kind"] == "hypothesis":
            record.update(
                rationale=(
                    "Ipotesi del proponente da verificare"
                    if it
                    else "Promoter assumptions to verify"
                ),
                effective_periods=periods,
            )
            assumptions.append(record)
        else:
            evidence.append(record)
    refs = {p.name: f"basis-{i}" for i, p in enumerate(paths)}
    proposal = refs[f"proposal-{language}.md"]
    operations = refs[f"operations-{language}.md"]
    economics = [refs["pilot-economics.csv"], refs[f"economics-{language}.md"]]
    updated = refs.get(f"update-{language}.md")
    operating_basis = [operations] + ([updated] if updated else [])
    question = (
        (
            "Il servizio può funzionare il sabato?"
            if previous
            else "Come possiamo verificare se il servizio merita un test?"
        )
        if it
        else (
            "Could the service work on Saturdays?"
            if previous
            else "How can we establish whether the service merits a trial?"
        )
    )
    words = {
        "recommendation": (
            (
                "Prima di avviare il servizio, verificare se il sabato è accettabile per i clienti e ottenere un preventivo aggiornato. La precedente ipotesi pomeridiana non è più disponibile."
                if previous
                else "Preparare un piccolo test del servizio prima di impegnarsi in un avvio continuativo. L'interesse informale e i costi ipotizzati non dimostrano ancora ordini o capacità operativa."
            )
            if it
            else (
                "Before starting the service, check whether customers would accept Saturday and obtain an updated quote. The previous afternoon arrangement is no longer available."
                if previous
                else "Prepare a small service test before committing to regular operations. Informal interest and assumed costs do not yet demonstrate orders or operating capacity."
            )
        ),
        "depends": (
            "La proposta dipende da disponibilità del veicolo, finestre accettate dai clienti, ordini paganti e costi confermati."
            if it
            else "The proposal depends on vehicle availability, customer acceptance of collection windows, paid orders and confirmed costs."
        ),
        "change": (
            "Rivedere la proposta dopo riscontri dei clienti e un preventivo compatibile con gli orari effettivi."
            if it
            else "Revisit the proposal after customer feedback and a quote consistent with the actual operating windows."
        ),
        "business": (
            "Ciclo Arco propone ritiro e riconsegna delle biciclette per la riparazione. Il cliente pagherebbe per evitare il trasporto in officina; la riparazione è fatturata separatamente e resta fuori da questo servizio."
            if it
            else "Ciclo Arco proposes bicycle collection and return for repairs. Customers would pay to avoid transporting their bicycle to the workshop; repairs are billed separately and fall outside this service."
        ),
        "market": (
            "L'interesse informale riportato nella proposta suggerisce un problema da esplorare. Mancano ordini, accettazione del prezzo e ricerca di mercato: l'interesse non è una previsione di domanda."
            if it
            else "The informal interest reported in the proposal suggests a need to explore. Orders, price acceptance and market research are missing; interest is not a demand forecast."
        ),
        "operations": (
            (
                "Il fornitore non offre più i pomeriggi previsti. Il sabato è una possibilità ancora priva di preventivo e riscontro dei clienti. Occorre ridisegnare il test prima di fissare un calendario."
                if previous
                else "Il servizio prevede prenotazione telefonica, finestre concordate e un veicolo nei pomeriggi indicati. Percorsi, capacità e responsabilità operative devono essere verificati con un test; il responsabile proposto non equivale a personale assunto."
            )
            if it
            else (
                "The supplier no longer offers the planned afternoons. Saturday is an option without an updated quote or customer feedback. Redesign the test before committing to a schedule."
                if previous
                else "The service proposes phone bookings, agreed windows and a vehicle on the stated afternoons. Routes, capacity and operating responsibilities need a trial; a proposed owner does not establish that staff have been hired."
            )
        ),
        "economics": (
            (
                "La tabella applica le ipotesi di volume, prezzo e costo ricevute. Mostra il risultato entro quel perimetro, senza confermare la domanda o includere costi ancora sconosciuti."
                + (
                    " La revisione degli orari richiede nuovi riscontri prima di cambiare i numeri."
                    if previous
                    else ""
                )
            )
            if it
            else (
                "The table applies the supplied volume, price and cost assumptions. It shows the result within that scope, without validating demand or including unknown costs."
                + (
                    " Revised operating windows require new evidence before changing the figures."
                    if previous
                    else ""
                )
            )
        ),
        "cash": (
            "Non è disponibile un piano di cassa completo. Pagamenti, imposte, assicurazione, investimenti e fabbisogno finanziario restano da chiarire; un risultato operativo positivo non dimostra liquidità sufficiente."
            if it
            else "A complete cash plan is unavailable. Payment timing, tax, insurance, investment and funding needs remain unresolved; a positive operating result does not establish sufficient liquidity."
        ),
        "alternatives": (
            "Confrontare il test limitato con il rinvio del servizio e con l'attuale trasporto a cura del cliente. La scelta dipende dai riscontri ottenuti, senza presumere acquisti di veicoli o nuove assunzioni."
            if it
            else "Compare a limited trial with postponement and the current customer-arranged transport. The choice depends on evidence gathered, without assuming vehicle purchases or new hires."
        ),
        "next_actions": (
            "Il proponente raccolga disponibilità orarie e disponibilità a pagare dei clienti, chieda un preventivo aggiornato e provi un percorso. Rivedere poi capacità, costi e proposta prima di impegnarsi con i clienti."
            if it
            else "The promoter should collect customer availability and willingness to pay, obtain an updated quote and trial a route. Review capacity, costs and the proposal before committing to customers."
        ),
    }
    bindings = {
        "recommendation": [proposal, *operating_basis, *economics],
        "depends": [proposal, *operating_basis, *economics],
        "change": [proposal, *operating_basis],
        "business": [proposal],
        "market": [proposal],
        "operations": operating_basis,
        "economics": economics,
        "cash": economics,
        "alternatives": [proposal, operations],
        "next_actions": [proposal, *operating_basis],
    }
    narrative = [
        dict(
            id=key.replace("_", "-"),
            kind="finding",
            text=value,
            claims={},
            basis_ids=bindings[key],
            rubric_id=None,
            review=review.copy(),
        )
        for key, value in words.items()
    ]
    with names["pilot-economics.csv"].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    commercial = [
        dict(
            scenario=row["scenario"],
            period=row["period"],
            units=row["units"],
            net_price=row["net_price_eur"],
            variable_cost_per_unit=row["variable_cost_per_order_eur"],
            fixed_cost=row["fixed_cost_eur"],
            basis_ids=economics,
            cost_scope=(
                "Autista, carburante, prenotazioni, noleggio, coordinamento e promozione ipotizzati; assicurazione, imposte e investimenti non quantificati."
                if it
                else "Assumed driver, fuel, booking, rental, coordination and promotion costs; insurance, tax and investment not quantified."
            ),
        )
        for row in rows
    ]
    headers = (
        ["Mese", "Ordini ipotizzati", "Ricavi EUR", "Risultato parziale EUR"]
        if it
        else ["Month", "Assumed orders", "Revenue EUR", "Partial result EUR"]
    )
    expected = [("20", "900", "-260"), ("30", "1350", "10"), ("40", "1800", "280")]
    table_rows = []
    for period, values in zip(periods, expected, strict=True):
        table_rows.append(
            [
                {"text": period},
                *[
                    dict(
                        calculation_ids=[f"pilot/{period}/commercial_{metric}"],
                        operation="sum",
                        value=value,
                    )
                    for metric, value in zip(
                        ("units", "revenue", "operating_result"), values, strict=True
                    )
                ],
            ]
        )
    return dict(
        schema_version="mparanza.business_planning_case.v3",
        case_id="ciclo-arco-pilot",
        entity_name="Ciclo Arco",
        company_stage="Proposta di nuovo servizio" if it else "Proposed new service",
        planning_objective=(
            "Valutare se e come provare il servizio"
            if it
            else "Assess whether and how to test the service"
        ),
        audience="internal",
        reporting_currency="EUR",
        periods=periods,
        review=review.copy(),
        sources=sources,
        evidence=evidence,
        assumptions=assumptions,
        decisions=[],
        observations=[],
        resolutions=[],
        financial=None,
        narrative=narrative,
        limitations=[words["cash"]],
        required_sections=["business_analysis", "financial"],
        commercial=commercial,
        assessment=dict(
            decision="redesign" if previous else "test",
            recommendation=["recommendation"],
            depends_on=["depends"],
            would_change=["change"],
            sections={
                key: [key.replace("_", "-")]
                for key in (
                    "business",
                    "market",
                    "operations",
                    "economics",
                    "cash",
                    "alternatives",
                    "next_actions",
                )
            },
            charts=[],
        ),
        cycle=dict(
            id="revised" if previous else "initial",
            parent_source_id=next(
                (s["id"] for s in sources if s["role"] == "prior_plan"), None
            ),
            question=question,
            trigger_ids=[updated] if updated else [proposal],
            analysis_ids=["market", "operations", "economics", "cash"],
            decision_ids=["recommendation"],
            next_test_ids=["next-actions"],
            reopen_when_ids=["change"],
            reassessed_ids=[n["id"] for n in narrative] if previous else [],
        ),
        financing={"purpose": "internal", "assessments": []},
        presentation={
            "language": language,
            "source_notes": [
                dict(
                    source_id=s["id"],
                    claim=(
                        (
                            "Volumi, prezzi e costi ipotizzati"
                            if it
                            else "Assumed volumes, prices and costs"
                        )
                        if p.suffix == ".csv"
                        else (
                            "Perimetro e ipotesi riportati nel documento"
                            if it
                            else "Scope and assumptions stated in the document"
                        )
                    ),
                    locator=(
                        "CSV rows 2–4"
                        if p.suffix == ".csv"
                        else (
                            "Planning snapshot: case and planning_cycle"
                            if p.name == "prior-plan.json"
                            else "Complete short note"
                        )
                    ),
                )
                for p, s in zip(paths, sources, strict=True)
            ],
            "tables": [
                dict(
                    id="pilot-economics",
                    title=(
                        "Ipotesi economiche del test"
                        if it
                        else "Pilot economics assumptions"
                    ),
                    section="economics",
                    headers=headers,
                    rows=table_rows,
                    caption_id="economics",
                )
            ],
        },
    )
