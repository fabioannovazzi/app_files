"""Exercise the current grant dossier with authored, fictional interpretations.

Semantic proposals and asserted reviews are regression fixtures, never evidence
of a live model session, learner participation or professional approval.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_bandi_agevolazioni_plugin import _scripts
from tests.plugins.test_bandi_dossier_report import assert_local_report_links
from tests.plugins.test_teaching_kit_execution import (
    _bound_case,
    _complete_teaching_case,
)

ROOT = Path(__file__).resolve().parents[2]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _apply_fixture(scripts, args, task, collection, payloads, prose, session_prefix):
    """Record exact packet-bound proposals and separately apply test decisions."""
    evidence = sorted({ref for payload in payloads for ref in payload["_evidence"]})
    session = f"{session_prefix}-{task}"
    packet = scripts["intelligence"].create_intelligence_packet(
        **args, task=task, subject_ids=evidence, model_session_ref=session
    )
    field = scripts["intelligence_contract"].COLLECTION_ID_FIELDS[collection]
    contribution = {
        "summary_it": prose["fixture"],
        "recommendations": [
            {
                "recommendation_id": f"REC-{index}",
                "action": "CREATE",
                "target_collection": collection,
                "target_id": payload[field],
                "proposed_payload": {
                    key: value for key, value in payload.items() if key != "_evidence"
                },
                "rationale": payload.get("rationale", prose["fixture"]),
                "evidence_refs": payload["_evidence"],
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
        model="authored-source-interpretation-not-live-model",
        prompt_template_version="bandi-teaching-fixture-v2",
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
        notes=prose["fixture"],
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
@prepared_kit("vera/bandi-agevolazioni")
def test_selected_call_kit_produces_native_review_dossier(
    tmp_path, monkeypatch, language, phase, record_property
):
    run = _bound_case(
        tmp_path,
        monkeypatch,
        "bandi-agevolazioni",
        "bandi-agevolazioni",
        "demo",
        language=language,
    )
    scripts = _scripts()
    _execute_dossier(run, scripts, language, "demo")
    ledger = _complete_teaching_case(run, tmp_path / "case")
    results = [{"phase": "demo", "run": run}]
    if phase == "practice":
        from courseware.library import CourseLibrary

        context = run["context"]
        original = {
            path: path.read_bytes()
            for path in Path(context["run_root"]).rglob("*")
            if path.is_file()
        }
        kit = CourseLibrary(ROOT / "plugins/vera", {"bandi-agevolazioni"}).render(
            "bandi-agevolazioni", language, tmp_path / "practice-kit"
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
            "bandi-agevolazioni",
            version,
            input_ids=[item["receipt"]["input_id"] for item in imports],
            purpose="Reassess the fictional selected call with the replacement quotation",
        )
        updated = ledger.start_run(
            tmp_path / "case", context["engagement_id"], prepared["run"]["run_id"]
        )
        _execute_dossier(updated, scripts, language, "practice")
        _complete_teaching_case(updated, tmp_path / "case")
        assert updated["context"]["engagement_id"] == context["engagement_id"]
        assert updated["context"]["run_id"] != context["run_id"]
        assert all(path.read_bytes() == value for path, value in original.items())
        results.append({"phase": "practice", "run": updated})
    _write(tmp_path / "execution.json", {"language": language, "results": results})
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="bandi-agevolazioni",
        language=language,
        phase=phase,
    )


def _execute_dossier(run, scripts, language, phase):
    prose = _read(ROOT / "tests/fixtures/teaching_bandi" / f"{language}.json")
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
    original_inputs = {path: path.read_bytes() for path in (call, company, quote)}
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
            issuer=prose["fictional"],
            authority_role=authority,
            selected_by="synthetic-regression",
        )
    # These are authored expected proposals for this source only. The ordinary
    # workflow records caller reasoning; it does not implement a universal grant
    # calculator or infer eligible costs from quotation labels.
    budget = (
        {"total": "11000", "eligible": "8000", "grant": "4000"}
        if phase == "demo"
        else {"total": "13000", "eligible": "10000", "grant": "5000"}
    )
    case = _read(output / "case_intake.json")
    case["professional_question"] = prose["question"]
    case["application"].update(
        title=call.read_text().splitlines()[0].removeprefix("# "),
        issuing_authority=prose["fictional"],
        procedure_id="FICTIONAL-CALL",
        submission_deadline="2026-09-30",
    )
    case["applicant"]["legal_name"] = "Arco Servizi Srl"
    case["project"].update(
        title=prose["title"],
        summary=prose["project"],
        currency="EUR",
        requested_amount=budget["grant"],
    )
    _write(output / "case_intake.json", case)
    scripts["review"].record_review(
        **args,
        scope="source_baseline",
        decision="accepted",
        reviewer_id="synthetic-review-fixture",
        reviewer_role="regression fixture",
        confirmed_by_user=True,
        notes=prose["fixture"],
    )
    prefix = f"SYNTHETIC-{language}-{phase}"
    categories = [
        "eligibility",
        "eligibility",
        "eligibility",
        "cost",
        "cost",
        "cost",
        "procedure",
        "procedure",
        "document",
        "document",
        "document",
        "deadline",
        "exclusion",
    ]
    clauses = call.read_text().split("## ")[1:]
    assert len(clauses) == 13
    requirements = []
    for index, (clause, category) in enumerate(
        zip(clauses, categories, strict=True), 1
    ):
        locator, body = clause.split("\n\n", 1)
        excerpt = body.split("\n\n", 1)[0].strip()
        requirements.append(
            {
                "requirement_id": f"REQ-{index:02d}",
                "category": category,
                "statement": excerpt,
                "source_refs": [
                    {
                        "source_id": "SRC-CALL",
                        "locator": locator,
                        "excerpt": excerpt,
                        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
                    }
                ],
                "applicability": prose["fictional"],
                "expected_evidence": [prose["requirement_evidence"]],
                "review_status": "proposed",
                "_evidence": ["SRC-CALL"],
            }
        )
    _apply_fixture(
        scripts,
        args,
        "REQUIREMENT_DRAFTING",
        "requirements",
        requirements,
        prose,
        prefix,
    )
    with quote.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["item_id"] for row in rows] == ["Q-001", "Q-002", "Q-003"]
    facts = []
    for identity, field, value, source in [
        ("FACT-SITE", "applicant.operating_site", prose["site"], "SRC-COMPANY"),
        ("FACT-STAFF", "applicant.staff", 4, "SRC-COMPANY"),
        ("FACT-PROJECT", "project.description", prose["project"], "SRC-COMPANY"),
        (
            "FACT-COMMITMENT",
            "project.spending_commitment",
            prose["commitment"],
            "SRC-COMPANY",
        ),
        *[
            (
                f"FACT-{row['item_id']}",
                "quotation.line",
                {
                    "description": row["description"],
                    "amount_eur": row["amount_eur"],
                    "accepted": False,
                },
                "SRC-QUOTE",
            )
            for row in rows
        ],
    ]:
        facts.append(
            {
                "fact_id": identity,
                "field_code": field,
                "value": value,
                "as_of": "2026-09-14",
                "source_ids": [source],
                "kind": "document_observation",
                "review_status": "proposed",
                "_evidence": [source],
            }
        )
    _apply_fixture(scripts, args, "EVIDENCE_MAPPING", "facts", facts, prose, prefix)
    links = [
        ["FACT-SITE"],
        ["FACT-STAFF"],
        ["FACT-PROJECT"],
        ["FACT-Q-001"],
        ["FACT-Q-002"],
        ["FACT-Q-003"],
        ["FACT-Q-001", "FACT-Q-002"],
        ["FACT-Q-001", "FACT-Q-002"],
        ["FACT-PROJECT"],
        ["FACT-SITE", "FACT-STAFF"],
        ["FACT-Q-001", "FACT-Q-002", "FACT-Q-003"],
        [],
        ["FACT-COMMITMENT"],
    ]
    assessments = [
        {
            "assessment_id": f"ASM-{index:02d}",
            "requirement_id": f"REQ-{index:02d}",
            "fact_ids": related,
            "readiness": "verify",
            "outcome": "satisfied",
            "rationale": prose["clauses"][index - 1].format(**budget),
            "evaluation_method": "model_led",
            "deterministic_rule": None,
            "review_status": "proposed",
            "_evidence": [f"REQ-{index:02d}", *related],
        }
        for index, related in enumerate(links, 1)
    ]
    _apply_fixture(
        scripts, args, "ASSESSMENT_REASONING", "assessments", assessments, prose, prefix
    )
    expenses = [
        {
            "expense_id": row["item_id"],
            "description": row["description"],
            "amount": row["amount_eur"],
            "currency": "EUR",
            "requirement_ids": [f"REQ-{index + 4:02d}"],
            "source_ids": ["SRC-QUOTE"],
            "readiness": "verify",
            "outcome": "ineligible" if index == 2 else "eligible",
            "rationale": prose["clauses"][index + 3],
            "review_status": "proposed",
            "_evidence": [f"REQ-{index + 4:02d}", f"FACT-{row['item_id']}"],
        }
        for index, row in enumerate(rows)
    ]
    _apply_fixture(
        scripts, args, "COST_CLASSIFICATION", "expenses", expenses, prose, prefix
    )
    documents = [
        {
            "document_id": f"DOC-{index + 1}",
            "title": prose["documents"][index],
            "requirement_ids": [f"REQ-{index + 9:02d}"],
            "material_source_ids": ["SRC-COMPANY" if index < 2 else "SRC-QUOTE"],
            "readiness": "verify",
            "rationale": prose["document_reason"],
            "review_status": "proposed",
            "_evidence": [
                f"REQ-{index + 9:02d}",
                "SRC-COMPANY" if index < 2 else "SRC-QUOTE",
            ],
        }
        for index in range(3)
    ]
    _apply_fixture(
        scripts,
        args,
        "MISSING_INFO_RED_FLAGS",
        "document_checklist",
        documents,
        prose,
        prefix,
    )
    narrative = {
        "narrative_id": "NAR-PROJECT",
        "prompt": prose["documents"][0],
        "draft": prose["narrative"] + "\n\n" + prose["budget"].format(**budget),
        "requirement_ids": [f"REQ-{i:02d}" for i in (3, 4, 5, 6, 7, 8, 9)],
        "fact_ids": [fact["fact_id"] for fact in facts],
        "readiness": "verify",
        "rationale": prose["fixture"],
        "review_status": "proposed",
        "_evidence": [f"REQ-{i:02d}" for i in (3, 4, 5, 6, 7, 8, 9)]
        + [fact["fact_id"] for fact in facts],
    }
    _apply_fixture(
        scripts, args, "NARRATIVE_DRAFTING", "narratives", [narrative], prose, prefix
    )
    consistency = {
        "check_id": "CHECK-BUDGET",
        "question": prose["consistency"],
        "fact_ids": [f"FACT-{row['item_id']}" for row in rows],
        "source_ids": ["SRC-QUOTE"],
        "outcome": "consistent",
        "rationale": prose["budget"].format(**budget),
        "review_status": "proposed",
        "_evidence": [f"FACT-{row['item_id']}" for row in rows]
        + [f"REQ-{i:02d}" for i in (4, 5, 6, 7, 8)],
    }
    _apply_fixture(
        scripts,
        args,
        "CONSISTENCY_REVIEW",
        "consistency_checks",
        [consistency],
        prose,
        prefix,
    )
    workbench = _read(output / "application_workbench.json")
    workbench["case_summary"] = prose["summary"] + " " + prose["issue"]
    _write(output / "application_workbench.json", workbench)
    audit = scripts["validate"].validate_application(**args)
    assert audit["status"] == "passed", audit["issues"]
    result = scripts["package"].package_dossier(**args)
    manifest = _read(result["manifest"])
    dossier = result["dossier"].read_text()
    report = result["report"].read_text()
    assert f'<html lang="{language}">' in report
    assert_local_report_links(report)
    assert len(workbench["requirements"]) == report.count('<details id="record-REQ-')
    assert len(workbench["assessments"]) == report.count(
        '<article class="record" id="record-ASM-'
    )
    assert prose["budget"].format(**budget) in report
    assert hashlib.sha256(result["report"].read_bytes()).hexdigest() == next(
        item["sha256"]
        for item in manifest["artifacts"]
        if item["artifact_id"] == "deliverable.review_report"
    )
    assert manifest["ready_to_file"] is False
    assert manifest["disposition"] == "review_required"
    assert manifest["submission_actions_performed"] is False
    assert manifest["portal_actions_performed"] is False
    assert len(workbench["requirements"]) == 13
    assert len(workbench["assessments"]) == 13
    assert len(workbench["facts"]) == 7
    assert len(workbench["document_checklist"]) == 3
    assert len(workbench["consistency_checks"]) == 1
    assert workbench["expenses"][2]["outcome"] == "ineligible"
    assert {item["review_status"] for item in workbench["assessments"]} == {"proposed"}
    assert prose["budget"].format(**budget) in dossier
    assert all(path.read_bytes() == value for path, value in original_inputs.items())
    return result
