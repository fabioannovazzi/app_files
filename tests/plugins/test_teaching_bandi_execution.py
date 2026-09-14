"""Run fictional selected-call inputs through native dossier proposals/review.

Every model contribution and review decision here is explicitly a regression
fixture, not a fresh human/session approval. No legal eligibility is asserted.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins.test_bandi_agevolazioni_plugin import _scripts
from tests.plugins.test_teaching_kit_execution import _bound_case


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_fixture(scripts, args, task, collection, payloads, evidence):
    """Use the ordinary proposal/apply contract with labelled test decisions."""
    session = f"SYNTHETIC-REGRESSION-{task}"
    packet = scripts["intelligence"].create_intelligence_packet(
        **args, task=task, subject_ids=evidence, model_session_ref=session
    )
    field = scripts["intelligence_contract"].COLLECTION_ID_FIELDS[collection]
    contribution = {
        "summary_it": "Contributo sintetico di regressione; nessuna approvazione dell’utente.",
        "recommendations": [
            {
                "recommendation_id": f"REC-{index}",
                "action": "CREATE",
                "target_collection": collection,
                "target_id": payload[field],
                "proposed_payload": payload,
                "rationale": "Fixed interpretation of the explicitly fictional source, for native regression only.",
                "evidence_refs": evidence,
                "requested_evidence": [],
                "risk_flags": ["SYNTHETIC_REGRESSION"],
                "alternatives": [],
                "confidence_band": "MEDIUM",
            }
            for index, payload in enumerate(payloads)
        ],
    }
    result = scripts["intelligence"].record_intelligence(
        **args,
        model_output=contribution,
        expected_packet_sha256=scripts[
            "intelligence_contract"
        ].intelligence_packet_hash(packet),
        provider="synthetic-regression",
        model="fixed-source-interpretation",
        prompt_template_version="teaching-fixture-v1",
        recorded_by="synthetic-regression",
        idempotency_key=task,
        model_session_ref=session,
        task=task,
        subject_ids=evidence,
    )
    assert result["status"] == "MODEL_SUGGESTED"
    scripts["intelligence"].decide_intelligence(
        **args,
        intelligence_run_id=result["intelligence_run_id"],
        decision="accepted",
        reviewer_id="synthetic-review-fixture",
        reviewer_role="regression fixture",
        confirmed_by_user=True,
        notes="Synthetic test decision only; no actual user or professional approval.",
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_selected_call_kit_produces_native_review_dossier(
    tmp_path, monkeypatch, language, phase
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "bandi-agevolazioni",
        "bandi-agevolazioni",
        phase,
        language=language,
    )
    scripts = _scripts()
    output = Path(run["output_dir"])
    args = {"output_dir": output, "client_engagement": Path(run["context_path"])}
    scripts["initialize"].initialize_case(
        output,
        client_engagement=args["client_engagement"],
        reference_date="2026-09-14",
        client_reference="fictional-arco",
        language=language,
    )
    files = [
        path for path in Path(run["context"]["input_dir"]).rglob("*") if path.is_file()
    ]
    call = next(path for path in files if "avviso" in path.name)
    company = next(path for path in files if "progetto" in path.name)
    quote = next(path for path in files if path.suffix == ".csv")
    for source, identity, kind, authority in (
        (call, "SRC-CALL", "call", "primary"),
        (company, "SRC-COMPANY", "beneficiary_evidence", "evidentiary"),
        (quote, "SRC-QUOTE", "quotation", "evidentiary"),
    ):
        scripts["register"].register_source(
            **args,
            source=source,
            source_id=identity,
            source_type=kind,
            title=source.name,
            issuer="Fictional teaching source; no actual authority",
            authority_role=authority,
            selected_by="synthetic-regression",
        )
    case = _read(output / "case_intake.json")
    case["professional_question"] = (
        "Prepare a dossier from the selected fictional call and the company evidence."
    )
    case["application"].update(
        title=call.stem,
        issuing_authority="No real authority; simulated call",
        procedure_id="FICTIONAL-CALL",
    )
    case["applicant"]["legal_name"] = "Arco Servizi Srl — fictional"
    case["project"].update(
        title="Appointment booking", summary=company.read_text(), currency="EUR"
    )
    _write(output / "case_intake.json", case)
    excerpt = call.read_text().split("\n\n", 1)[1].strip()
    _apply_fixture(
        scripts,
        args,
        "REQUIREMENT_DRAFTING",
        "requirements",
        [
            {
                "requirement_id": "REQ-CALL",
                "category": "procedure",
                "statement": excerpt,
                "source_refs": [
                    {
                        "source_id": "SRC-CALL",
                        "locator": "complete simulated call paragraph",
                        "excerpt": excerpt,
                        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                    }
                ],
                "applicability": "Only the explicitly simulated case; no real funding or governing law.",
                "expected_evidence": [company.name, quote.name],
                "review_status": "proposed",
            }
        ],
        ["SRC-CALL"],
    )
    _apply_fixture(
        scripts,
        args,
        "EVIDENCE_MAPPING",
        "facts",
        [
            {
                "fact_id": "FACT-COMPANY",
                "field_code": "applicant.declared_project",
                "value": company.read_text(),
                "as_of": "2026-09-14",
                "source_ids": ["SRC-COMPANY"],
                "kind": "document_observation",
                "review_status": "proposed",
            }
        ],
        ["SRC-COMPANY", "REQ-CALL"],
    )
    _apply_fixture(
        scripts,
        args,
        "ASSESSMENT_REASONING",
        "assessments",
        [
            {
                "assessment_id": "ASM-CALL",
                "requirement_id": "REQ-CALL",
                "fact_ids": ["FACT-COMPANY"],
                "readiness": "verify",
                "outcome": "uncertain",
                "rationale": "The declared site, staffing and project match the simulated brief; all declarations and cost decisions remain subject to professional review.",
                "evaluation_method": "model_led",
                "deterministic_rule": None,
                "review_status": "proposed",
            }
        ],
        ["REQ-CALL", "FACT-COMPANY"],
    )
    with quote.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    _apply_fixture(
        scripts,
        args,
        "COST_CLASSIFICATION",
        "expenses",
        [
            {
                "expense_id": row["item_id"],
                "description": row["description"],
                "amount": row["amount_eur"],
                "currency": "EUR",
                "requirement_ids": ["REQ-CALL"],
                "source_ids": ["SRC-QUOTE"],
                "readiness": "verify",
                "outcome": "ineligible" if row["item_id"] == "Q-003" else "eligible",
                "rationale": "Model-proposed classification under the fictional call only: new software and related training are included; hardware is excluded. Review before any use.",
                "review_status": "proposed",
            }
            for row in rows
        ],
        ["REQ-CALL", "SRC-QUOTE"],
    )
    _apply_fixture(
        scripts,
        args,
        "MISSING_INFO_RED_FLAGS",
        "document_checklist",
        [
            {
                "document_id": "DOC-COMPANY",
                "title": company.name,
                "requirement_ids": ["REQ-CALL"],
                "material_source_ids": ["SRC-COMPANY", "SRC-QUOTE"],
                "readiness": "verify",
                "rationale": "Project declaration and quotation supplied; document presence is not professional verification.",
                "review_status": "proposed",
            }
        ],
        ["REQ-CALL", "FACT-COMPANY", "SRC-QUOTE"],
    )
    _apply_fixture(
        scripts,
        args,
        "NARRATIVE_DRAFTING",
        "narratives",
        [
            {
                "narrative_id": "NAR-PROJECT",
                "prompt": "Describe the project from the source",
                "draft": company.read_text(),
                "requirement_ids": ["REQ-CALL"],
                "fact_ids": ["FACT-COMPANY"],
                "readiness": "verify",
                "rationale": "Source-faithful draft of the fictional company's declared project; no new facts.",
                "review_status": "proposed",
            }
        ],
        ["REQ-CALL", "FACT-COMPANY"],
    )

    audit = scripts["validate"].validate_application(**args)
    assert audit["status"] == "passed", audit["issues"]
    result = scripts["package"].package_dossier(**args)

    manifest = _read(result["manifest"])
    dossier = result["dossier"].read_text()
    workbench = _read(output / "application_workbench.json")
    assert manifest["ready_to_file"] is False
    assert manifest["disposition"] == "review_required"
    assert manifest["submission_actions_performed"] is False
    assert manifest["portal_actions_performed"] is False
    assert ("8000.00" if phase == "practice" else "6000.00") in dossier
    assert workbench["expenses"][2]["outcome"] == "ineligible"
    assert len(workbench["requirements"]) == 1
    assert len(workbench["narratives"]) == 1
    assert _read(output / "review_log.json")["events"] == []
