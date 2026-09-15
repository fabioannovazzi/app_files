"""Run the current Concordato pipeline on prepared first-use teaching files.

All semantic interpretations and confirmations below are test-only. They are
not shipped as course answers or evidence of learner/professional approval.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from tests.plugins._teaching_release import record_native_check
from tests.plugins.test_teaching_kit_execution import (
    ROOT,
    _bound_case,
    _complete_teaching_case,
    _read,
    _run,
    _write,
)

WORDS = {
    "it": [
        "Interpretazione della bozza fornita, soggetta a verifica professionale.",
        "Acquisire i documenti mancanti e verificare la versione con il professionista.",
        "Verificare impegno, condizioni, data di erogazione e rimborso della finanza, insieme al piano mensile di cassa.",
        "Verificare completezza, crediti, prelazioni, classi e voto con i documenti di supporto.",
        "La finanza è soltanto ipotizzata e mancano condizioni e tempistica.",
        "L’aggiornamento lascia un fabbisogno non coperto nel piano annuale.",
        "Professionista incaricato",
        "Proposta di continuità diretta, da verificare nel quadro applicabile alla data indicata.",
        "Flusso operativo netto previsto",
        "Finanza nuova ipotizzata",
        "Distribuzioni ai creditori",
        "Costi della procedura",
        "Pagamento dei creditori entro fine 2027",
    ],
    "en": [
        "Interpretation of the supplied draft, subject to professional review.",
        "Obtain missing documents and verify their version with the professional.",
        "Verify funding commitment, conditions, drawdown and repayment together with a monthly cash plan.",
        "Verify completeness, claims, priorities, classes and voting against supporting documents.",
        "Financing is assumed only; conditions and timing are missing.",
        "The update leaves an uncovered funding requirement in the annual plan.",
        "Engagement professional",
        "Proposed direct business continuity, to be reviewed under the framework applicable at the stated date.",
        "Planned net operating cash",
        "Assumed new financing",
        "Creditor distributions",
        "Procedure costs",
        "Creditor payment by the end of 2027",
    ],
    "fr": [
        "Interprétation du projet fourni, sous réserve de revue professionnelle.",
        "Obtenir les pièces manquantes et vérifier leur version avec le professionnel.",
        "Vérifier engagement, conditions, versement et remboursement du financement ainsi que le plan mensuel de trésorerie.",
        "Vérifier exhaustivité, créances, priorités, classes et vote avec les justificatifs.",
        "Le financement reste supposé ; conditions et calendrier manquent.",
        "L’actualisation laisse un besoin de financement non couvert dans le plan annuel.",
        "Professionnel responsable",
        "Continuité directe proposée, à vérifier dans le cadre applicable à la date indiquée.",
        "Flux opérationnel net prévu",
        "Financement nouveau supposé",
        "Distributions aux créanciers",
        "Coûts de procédure",
        "Paiement des créanciers avant fin 2027",
    ],
    "de": [
        "Interpretation des vorgelegten Entwurfs, fachliche Prüfung bleibt erforderlich.",
        "Fehlende Belege beschaffen und ihre Fassung mit der Fachperson prüfen.",
        "Finanzierungszusage, Bedingungen, Auszahlung und Rückzahlung zusammen mit einem Monatsliquiditätsplan prüfen.",
        "Vollständigkeit, Forderungen, Rang, Klassen und Stimmrechte anhand der Belege prüfen.",
        "Finanzierung ist nur angenommen; Bedingungen und Termine fehlen.",
        "Die Aktualisierung lässt im Jahresplan einen ungedeckten Finanzierungsbedarf.",
        "Zuständige Fachperson",
        "Vorgeschlagene direkte Fortführung, nach dem zum angegebenen Datum geltenden Rahmen zu prüfen.",
        "Geplanter operativer Nettozahlungsstrom",
        "Angenommene neue Finanzierung",
        "Gläubigerausschüttungen",
        "Verfahrenskosten",
        "Gläubigerzahlung bis Ende 2027",
    ],
    "es": [
        "Interpretación del borrador aportado, sujeta a revisión profesional.",
        "Obtener los documentos pendientes y verificar su versión con el profesional.",
        "Verificar compromiso, condiciones, desembolso y devolución de la financiación junto con el plan mensual de caja.",
        "Verificar integridad, créditos, prelaciones, clases y voto con los justificantes.",
        "La financiación es solo una hipótesis; faltan condiciones y calendario.",
        "La actualización deja una necesidad de financiación sin cubrir en el plan anual.",
        "Profesional responsable",
        "Continuidad directa propuesta, pendiente de revisión según el marco aplicable en la fecha indicada.",
        "Flujo operativo neto previsto",
        "Nueva financiación supuesta",
        "Distribuciones a acreedores",
        "Costes del procedimiento",
        "Pago de acreedores antes de fin de 2027",
    ],
}


def _model(inspection: Path, language: str, phase: str) -> dict:
    """Author this fixed fictional case, separate from the shipped source pack."""
    t = _read(ROOT / "scripts/course_materials/concordato_sources.json")[language]
    w = WORDS[language]
    c, r, p = t["tabs"]
    model = _read(inspection / "suggested_concordato_case_model.json")
    documents = {
        Path(row["relative_path"]).name: row
        for row in model["document_perimeter"]["documents"]
    }
    workbook_source = documents[f"{phase}-{language}.xlsx"]
    management_source = documents[f"management-{phase}-{language}.pdf"]
    source = workbook_source["source_artifact_ref"]
    support = management_source["source_artifact_ref"]
    authored = _read(ROOT / "tests/fixtures/teaching_reviews/concordato.json")[language]
    management = _read(ROOT / "scripts/course_materials/concordato_support.json")[
        language
    ]

    def evidence(locator):
        return [{"source_artifact_ref": source, "locator": locator}]

    def support_evidence(page):
        return [{"source_artifact_ref": support, "locator": f"p. {page}"}]

    # The official indexed statute was inspected during authoring. This fixed
    # fixture is not a new live legal review or an eligibility opinion.
    model["legal_framework"].update(
        {
            "as_of_date": "2026-09-14",
            "judgment_basis": w[7],
            "authority_refs": [
                {
                    "title": "D.Lgs. 12 gennaio 2019, n. 14 — Codice della crisi",
                    "url": "https://www.gazzettaufficiale.it/sommario/codici/codiceCrisi",
                    "provisions": ["art. 84", "art. 87"],
                }
            ],
        }
    )
    model["procedure"].update(
        {
            "identification_status": "partial",
            "debtor_name": "Officina Riva S.r.l.",
            "court": "",
            "procedure_reference": "",
            "stage": "draft",
            "plan_type": "continuity_direct",
            "judgment_basis": t["notes"][1],
        }
    )
    perimeter = model["document_perimeter"]
    perimeter.update({"status": "partial", "judgment_basis": t["notes"][4]})
    workbook_source.update(
        {
            "roles": [
                "proposal",
                "plan",
                "creditor_schedule",
                "financial_model",
                "liquidation_analysis",
            ],
            "authoritative_for": ["proposal", "plan", "creditor_schedule"],
            "version_date": "2026-09-14",
            "judgment_basis": t["notes"][3],
        }
    )
    management_source.update(
        {
            "roles": ["other_support", "financial_model", "liquidation_analysis"],
            "authoritative_for": ["financial_model", "liquidation_analysis"],
            "version_date": "2026-09-14",
            "judgment_basis": management["fiction"],
        }
    )
    model["creditor_population"].update(
        {
            "status": "partial",
            "cutoff_date": "2026-08-31",
            "judgment_basis": t["notes"][2],
        }
    )
    for i, (name, claim, proposed, liquidation) in enumerate(
        [
            ("Alba Componenti", "100000", "65000", "45000"),
            ("Borea Materiali", "60000", "39000", "27000"),
            ("Cima Trasporti", "40000", "26000", "18000"),
        ]
    ):
        model["creditor_population"]["creditors"].append(
            {
                "creditor_id": f"C-{i+1}",
                "creditor_name": name,
                "claim_amount": claim,
                "claim_status": "asserted",
                "priority": "unsecured",
                "class_id": "CL-1",
                "treatment_form": "cash",
                "proposed_cash_amount": proposed,
                "proposed_non_cash_amount": "0",
                "liquidation_recovery_amount": liquidation,
                "payment_start": "",
                "payment_end": "2027-12-31",
                "voting_treatment": "unclear",
                "evidence_refs": evidence(f"{r}!A{i+7}:D{i+7}") + support_evidence(1),
                "judgment_basis": t["notes"][2],
            }
        )
    funding = "50000" if phase == "demo" else "30000"
    model["sources_and_uses"].update(
        {"status": "partial", "judgment_basis": t["planNote"]}
    )
    for i, (side, amount, locator) in enumerate(
        [
            ("source", "100000", f"{p}!B6:B7"),
            ("source", funding, f"{p}!B8"),
            ("use", "130000", f"{p}!B10"),
            ("use", "20000", f"{p}!B9"),
        ]
    ):
        model["sources_and_uses"]["items"].append(
            {
                "item_id": f"SU-{i+1}",
                "side": side,
                "category": w[i + 8],
                "description": w[i + 8],
                "amount": amount,
                "period": "2027",
                "evidence_refs": evidence(locator),
                "judgment_basis": t["planNote"],
            }
        )
    closing = (
        ["5000", "80000", "105000", "0"]
        if phase == "demo"
        else ["5000", "60000", "85000", "-20000"]
    )
    model["liquidity"].update(
        {
            "status": "partial",
            "judgment_basis": authored["feasibility_liquidity"][0],
            "periods": [
                {
                    "period_id": f"2027-Q{i+1}",
                    "period": f"2027-Q{i+1}",
                    "opening_cash": opening,
                    "operating_inflows": "75000",
                    "other_inflows": "0",
                    "new_finance_inflows": funding if i == 1 else "0",
                    "operating_outflows": "50000",
                    "procedure_costs": "20000" if i == 0 else "0",
                    "creditor_distributions": "130000" if i == 3 else "0",
                    "financing_outflows": "0",
                    "other_outflows": "0",
                    "reported_closing_cash": closing[i],
                    "evidence_refs": support_evidence(2),
                    "judgment_basis": management["operations"],
                }
                for i, opening in enumerate(["0", *closing[:3]])
            ],
        }
    )
    model["milestones"] = [
        {
            "milestone_id": "payment-2027",
            "date_or_period": "2027-12-31",
            "description": w[12],
            "status": "planned",
            "evidence_refs": evidence(f"{c}!B12"),
            "judgment_basis": t["notes"][6],
        }
    ]
    locators = {
        "procedure_identity": evidence(f"{c}!B7:B8"),
        "proposal_plan_consistency": evidence(f"{r}!A6:D9") + support_evidence(2),
        "document_perimeter": support_evidence(2),
        "creditor_perimeter": evidence(f"{r}!A6:D9") + support_evidence(1),
        "creditor_treatment": support_evidence(1),
        "voting_homologation": evidence(f"{c}!B8") + support_evidence(1),
        "liquidation_alternative": support_evidence(1),
        "feasibility_liquidity": support_evidence(2),
        "attestation": support_evidence(2),
        "accounting_consistency": evidence(f"{p}!B6:B7") + support_evidence(2),
        "tax_social_security": support_evidence(2),
    }
    for q in model["review_questions"]:
        basis, follow_up = authored[q["area"]]
        if q["area"] == "feasibility_liquidity" and phase == "practice":
            basis = f"{w[5]} {basis}"
        q.update(
            {
                "assessment": (
                    "addressed" if q["area"] == "procedure_identity" else "gap"
                ),
                "evidence_refs": locators[q["area"]],
                "judgment_basis": basis,
                "follow_up": follow_up,
            }
        )
    model["assumptions"] = [
        {
            "assumption_id": "finance-availability",
            "area": "sources_and_uses",
            "statement": w[4],
            "status": "unsupported",
            "materiality": "high",
            "evidence_refs": evidence(f"{c}!B11"),
            "judgment_basis": w[0],
        }
    ]
    model["issues"] = [
        {
            "issue_id": "finance-review",
            "area": "feasibility_liquidity",
            "statement": w[4 if phase == "demo" else 5],
            "status": "open",
            "severity": "high",
            "evidence_refs": evidence(f"{p}!B8:B12"),
            "owner": w[6],
            "next_action": w[2],
            "judgment_basis": w[0],
        },
        {
            "issue_id": "documents-review",
            "area": "document_perimeter",
            "statement": t["notes"][4],
            "status": "open",
            "severity": "high",
            "evidence_refs": evidence(f"{c}!B10"),
            "owner": w[6],
            "next_action": w[1],
            "judgment_basis": w[0],
        },
    ]
    return model


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_concordato_kit_builds_current_review_from_fictional_plan(
    tmp_path, monkeypatch, language, phase, record_property
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "concordato-plan-review",
        "concordato-plan-review",
        "demo",
        language=language,
    )
    ledger = _execute_concordato_run(run, language, "demo", tmp_path / "case")
    results = [{"phase": "demo", "run": run}]
    if phase == "practice":
        from courseware.library import CourseLibrary

        original = {
            path: path.read_bytes()
            for path in Path(run["context"]["run_root"]).rglob("*")
            if path.is_file()
        }
        context = run["context"]
        kit = CourseLibrary(ROOT / "plugins/vera", {"concordato-plan-review"}).render(
            "concordato-plan-review", language, tmp_path / "practice-kit"
        )
        imports = [
            ledger.import_document(
                tmp_path / "case",
                context["client_id"],
                context["engagement_id"],
                Path(path),
                "source",
            )
            for path in kit["practice_files"]
        ]
        version = _read(ROOT / "plugins/vera/.codex-plugin/plugin.json")["version"]
        prepared = ledger.prepare_run(
            tmp_path / "case",
            context["client_id"],
            context["engagement_id"],
            "concordato-plan-review",
            version,
            input_ids=[item["receipt"]["input_id"] for item in imports],
            purpose="Review the updated fictional plan in the same teaching case",
        )
        updated = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        _execute_concordato_run(updated, language, "practice", tmp_path / "case")
        assert updated["context"]["engagement_id"] == context["engagement_id"]
        assert updated["context"]["run_id"] != context["run_id"]
        assert all(path.read_bytes() == content for path, content in original.items())
        results.append({"phase": "practice", "run": updated})
    _write(tmp_path / "execution.json", {"language": language, "results": results})
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="concordato-plan-review",
        language=language,
        phase=phase,
    )


def _execute_concordato_run(run, language, phase, client_root):
    """Execute and preserve one real native review from this authored test case."""
    output = Path(run["output_dir"])
    inputs = Path(run["context"]["run_root"]) / "inputs"
    inspection, result = output / "inspection", output / "review"
    args = [
        inputs,
        "--client-engagement",
        run["context_path"],
        "--reference-date",
        "2026-09-14",
        "--language",
        language,
        "--document-language",
        language,
    ]
    _run(
        "plugins/concordato-plan-review/scripts/run_concordato_review.py",
        *args,
        "--output-dir",
        inspection,
    )
    assert (
        _read(inspection / "concordato_case_model.json")["status"]
        == "needs_semantic_review"
    )
    inventory = _read(inspection / "inventory.json")
    assert len(inventory) == 2
    assert all(
        item["supported"] and item["capture_status"] == "captured" for item in inventory
    )
    model = _model(inspection, language, phase)
    model_path, recipe = (
        output / "test_case_interpretation.json",
        output / "test_semantic_recipe.json",
    )
    _write(model_path, model)
    _run(
        "plugins/concordato-plan-review/scripts/review_case_model.py",
        inspection / "inventory.json",
        model_path,
        "--output",
        recipe,
        "--client-engagement",
        run["context_path"],
        "--reviewer-ref",
        "synthetic-test-reviewer-not-learner",
        "--reviewed-on",
        "2026-09-14",
        "--reference-date",
        "2026-09-14",
    )
    _run(
        "plugins/concordato-plan-review/scripts/run_concordato_review.py",
        *args,
        "--output-dir",
        result,
        "--semantic-recipe",
        recipe,
    )
    case = _read(result / "concordato_case_model.json")
    assert case["status"] == "reviewed"
    assert case["case_model"]["document_perimeter"]["status"] == "partial"
    assert case["case_model"]["procedure"]["stage"] == "draft"
    with (result / "creditor_treatment.csv").open() as handle:
        creditors = list(csv.DictReader(handle))
    assert len(creditors) == 3
    with (result / "liquidity_schedule.csv").open() as handle:
        cash = list(csv.DictReader(handle))
    assert len(cash) == 4
    assert [Decimal(row["calculated_closing_cash"]) for row in cash] == (
        [Decimal(value) for value in ("5000", "80000", "105000", "0")]
        if phase == "demo"
        else [Decimal(value) for value in ("5000", "60000", "85000", "-20000")]
    )
    assert Decimal(cash[-1]["calculated_closing_cash"]) == (
        Decimal("0") if phase == "demo" else Decimal("-20000")
    )
    assert all(row["bridge_within_tolerance"] == "True" for row in cash)
    assert (result / "concordato_preventivo_review_summary.docx").is_file()
    assert (
        WORDS[language][4 if phase == "demo" else 5]
        in (result / "concordato_semantic_review.md").read_text()
    )
    workbook = openpyxl.load_workbook(
        result / "concordato_review_workpaper.xlsx", read_only=True, data_only=True
    )
    names = {
        "it": {"Riepilogo", "Creditori", "Liquidità"},
        "en": {"Overview", "Creditors", "Liquidity"},
        "fr": {"Synthèse", "Créanciers", "Trésorerie"},
        "de": {"Übersicht", "Gläubiger", "Liquidität"},
        "es": {"Resumen", "Acreedores", "Liquidez"},
    }
    assert names[language] <= set(workbook.sheetnames)
    workbook.close()
    return _complete_teaching_case(run, client_root)
