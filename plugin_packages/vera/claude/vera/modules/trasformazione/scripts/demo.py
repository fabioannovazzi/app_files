"""Build a complete synthetic case and demonstrate selective stale approvals."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from transform_case import CaseStore

__all__ = ["run_demo", "main"]


def run_demo(root: Path) -> dict[str, str]:
    """Persist every stage, including the dossier before and after changed evidence."""
    store = CaseStore(root)
    store.initialize(
        "DEMO-TR-001",
        "Operatore sintetico",
        "Prova del dossier di trasformazione; nessuna pratica reale",
    )
    source_dir = root / "synthetic-inputs"
    store.update_case(
        {
            "initial_form": "SNC (ipotesi sintetica)",
            "final_form": "SRL (ipotesi sintetica)",
            "proposed_date": "2026-10-31",
        },
        "Operatore sintetico",
    )
    source_dir.mkdir()
    valuation = source_dir / "stima.txt"
    valuation.write_text(
        "CASO SINTETICO. Attivi 700000; passivi 250000; capitale proposto 100000.\n",
        encoding="utf-8",
    )
    creditors = source_dir / "creditori.txt"
    creditors.write_text(
        "CASO SINTETICO. Creditore Alfa, debito 25000; ricevuta e liberazione ignote.\n",
        encoding="utf-8",
    )
    source = source_dir / "fonte-dimostrativa.txt"
    source.write_text(
        "Fonte inventata per collaudare il versionamento; non è una norma.\n",
        encoding="utf-8",
    )
    store.import_evidence(
        "creditors", creditors, "Documento sintetico", "riga 1", "Operatore sintetico"
    )
    store.import_evidence(
        "law", source, "Fonte sintetica non normativa", "riga 1", "Operatore sintetico"
    )
    store.put(
        "source",
        {
            "id": "S01",
            "title": "Fonte sintetica di prova, non normativa",
            "url": None,
            "article": None,
            "publication_date": None,
            "effective_from": None,
            "applicability_from": None,
            "applicability_until": None,
            "transitional_conditions": "Nessuna applicabilità giuridica",
            "retrieved_at": "2026-09-29",
            "verification_status": "unverified",
            "reviewer": None,
            "snapshot": "evidence:law",
            "dependencies": ["evidence:law"],
        },
        "Operatore sintetico",
    )
    store.put(
        "calculation",
        {
            "id": "coverage",
            "operation": "capital_coverage",
            "args": {"assets": "700000", "liabilities": "250000", "capital": "100000"},
            "dependencies": ["evidence:valuation"],
        },
        "Operatore sintetico",
    )
    store.put(
        "reserve",
        {
            "id": "R1",
            "amount": "120000",
            "origin": "Utili: origine fiscale da verificare",
            "year": "2025",
            "regime": None,
            "restrictions": None,
            "balance_sheet": "Situazione sintetica",
            "uses": "Distribuzione solo ipotizzata: 30000",
            "prior_taxation": None,
            "dependencies": ["evidence:valuation"],
        },
        "Operatore sintetico",
    )
    store.put(
        "asset",
        {
            "id": "A1",
            "description": "Impianto sintetico",
            "book_value": "100000",
            "estimated_value": "150000",
            "tax_value": None,
            "business_destination": "Aziendale, da verificare",
            "accounting_decision": None,
            "tax_decision": None,
            "dependencies": ["evidence:valuation"],
        },
        "Operatore sintetico",
    )
    store.put(
        "deadline",
        {
            "id": "D1",
            "source_version": None,
            "trigger": None,
            "method": None,
            "extensions": None,
            "territory": "IT",
            "proposed_date": None,
            "approved_date": None,
            "receipt": None,
            "dependencies": ["source:S01"],
        },
        "Operatore sintetico",
    )
    store.put(
        "issue",
        {
            "id": "I1",
            "question": "Quali fonti correnti e dati sostengono il trattamento fiscale?",
            "source_needed": "Testi ufficiali applicabili e basi fiscali documentate",
            "owner": "Fiscalista, ruolo sintetico",
            "blocks": True,
            "closure_criterion": "Acquisizione e revisione professionale, fuori da questa demo",
            "resolution": None,
            "dependencies": ["source:S01"],
        },
        "Operatore sintetico",
    )
    store.branch(
        "tax",
        "Contabilità e fiscalità da qualificare",
        "Fiscalista, ruolo sintetico",
        "Acquisire basi fiscali e fonti applicabili",
        ["issue:I1", "reserve:R1", "asset:A1#tax_value", "deadline:D1"],
        "Operatore sintetico",
    )
    store.put(
        "calculation",
        {
            "id": "shares",
            "operation": "allocation",
            "args": {"capital": "100000", "shares": ["3/5", "2/5"]},
            "dependencies": ["evidence:valuation"],
        },
        "Operatore sintetico",
    )
    for record_id, capital, vote, profit in (
        ("P1", "3/5", "1/2", "7/10"),
        ("P2", "2/5", "1/2", "3/10"),
    ):
        store.put(
            "participant",
            {
                "id": record_id,
                "name": f"Socio sintetico {record_id}",
                "capital_share": capital,
                "vote_share": vote,
                "profit_share": profit,
                "title": "Titolo sintetico senza vincoli",
                "work_share": {
                    "not_applicable": "Nessun socio d'opera nel caso sintetico"
                },
                "consent": None,
                "dependencies": ["evidence:valuation"],
            },
            "Operatore sintetico",
        )
    store.put(
        "creditor",
        {
            "id": "C1",
            "name": "Creditore sintetico Alfa",
            "debt": "25000",
            "origin_date": None,
            "guarantee": None,
            "consent": None,
            "receipt": None,
            "receipt_date": None,
            "release_assessment": "Da verificare; nessuna liberazione presunta",
            "opposition_assessment": "Analisi distinta, da verificare",
            "dependencies": ["evidence:creditors"],
        },
        "Operatore sintetico",
    )
    for record_id, statement, dependencies in (
        (
            "capital",
            "Il margine aritmetico proposto è 350000; non prova la distribuibilità.",
            ["calculation:coverage", "source:S01"],
        ),
        (
            "creditors",
            "L'elenco può essere raccolto mentre la stima manca; le ricevute restano da acquisire.",
            ["evidence:creditors", "source:S01"],
        ),
    ):
        store.put(
            "finding",
            {
                "id": record_id,
                "statement": statement,
                "category": "interpretation",
                "rationale": "Proposta dimostrativa soggetta a revisione; nessun effetto giuridico.",
                "alternatives": ["Integrare i documenti e riesaminare"],
                "confidence": "synthetic_only",
                "dependencies": dependencies,
            },
            "Operatore sintetico",
        )
    store.branch(
        "capital",
        "Capitale e diritti",
        "Revisore sintetico",
        "Verificare stima e titoli",
        ["finding:capital", "calculation:shares", "participant:P1", "participant:P2"],
        "Operatore sintetico",
    )
    store.branch(
        "creditors",
        "Raccolta creditori",
        "Revisore sintetico",
        "Acquisire ricevute prima di analizzare termini",
        ["finding:creditors", "creditor:C1"],
        "Operatore sintetico",
    )
    missing = store.export()
    store.submit("creditors", "Operatore sintetico")
    digest = store.load()["branches"]["creditors"]["proposal_digest"]
    store.review(
        "creditors",
        digest,
        "Revisore sintetico",
        "approve",
        "Approvazione simulata della sola raccolta, non della liberazione",
    )
    store.import_evidence(
        "valuation", valuation, "Stima sintetica", "riga 1", "Operatore sintetico"
    )
    store.submit("capital", "Operatore sintetico")
    digest = store.load()["branches"]["capital"]["proposal_digest"]
    store.review(
        "capital",
        digest,
        "Revisore sintetico",
        "approve",
        "Approvazione simulata per preparazione; nessun capitale professionalmente approvato",
    )
    approved = store.export()
    valuation.write_text(
        "CASO SINTETICO REVISIONATO. Passività ulteriori da quantificare: aggiornare i calcoli e riesaminare.\n",
        encoding="utf-8",
    )
    store.import_evidence(
        "valuation",
        valuation,
        "Stima sintetica revisionata",
        "riga 1",
        "Operatore sintetico",
    )
    stale = store.export()
    return {
        "missing_valuation": str(missing / "dossier.md"),
        "approved_synthetic": str(approved / "dossier.md"),
        "stale_capital": str(stale / "dossier.md"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.info("%s", json.dumps(run_demo(args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
