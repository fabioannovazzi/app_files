from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bandi-agevolazioni"
SCRIPTS_ROOT = PLUGIN_ROOT / "scripts"
ARCHIVE_CORE_PATH = ROOT / "plugins" / "studio-archive" / "scripts" / "archive_core.py"


def _module_from_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _scripts() -> dict[str, ModuleType]:
    dependency_names = (
        "case_core",
        "record_review",
        "schema_validation",
        "deterministic_rules",
    )
    previous = {name: sys.modules.get(name) for name in dependency_names}
    core = _module_from_path("bandi_test_case_core", SCRIPTS_ROOT / "case_core.py")
    sys.modules["case_core"] = core
    try:
        schema_validation = _module_from_path(
            "bandi_test_schema_validation", SCRIPTS_ROOT / "schema_validation.py"
        )
        deterministic_rules = _module_from_path(
            "bandi_test_deterministic_rules", SCRIPTS_ROOT / "deterministic_rules.py"
        )
        sys.modules["schema_validation"] = schema_validation
        sys.modules["deterministic_rules"] = deterministic_rules
        review = _module_from_path(
            "bandi_test_record_review", SCRIPTS_ROOT / "record_review.py"
        )
        sys.modules["record_review"] = review
        return {
            "core": core,
            "initialize": _module_from_path(
                "bandi_test_initialize", SCRIPTS_ROOT / "initialize_case.py"
            ),
            "register": _module_from_path(
                "bandi_test_register", SCRIPTS_ROOT / "register_source.py"
            ),
            "link": _module_from_path(
                "bandi_test_link", SCRIPTS_ROOT / "link_sources.py"
            ),
            "review": review,
            "validate": _module_from_path(
                "bandi_test_validate", SCRIPTS_ROOT / "validate_application.py"
            ),
            "package": _module_from_path(
                "bandi_test_package", SCRIPTS_ROOT / "package_dossier.py"
            ),
        }
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _running_workspace(tmp_path: Path) -> dict[str, object]:
    archive = _module_from_path("bandi_test_archive_core", ARCHIVE_CORE_PATH)
    archive_root = tmp_path / "Studio"
    client_root = archive_root / "Impresa Demo SPA"
    client_root.mkdir(parents=True)
    state_dir = tmp_path / "private-state"
    configured = archive.configure_archive(archive_root, state_dir=state_dir)
    scope_id = next(
        item["scope_id"]
        for item in configured["scopes"]
        if item["display_name"] == "Impresa Demo SPA"
    )
    client = archive.set_studio_client_identity(
        scope_id,
        legal_names=["Impresa Demo SPA"],
        tax_identifiers=["01234567890"],
        state_dir=state_dir,
    )["client"]
    engagement = archive.create_studio_client_engagement(
        client["client_id"],
        "Bando regionale 2026",
        state_dir=state_dir,
    )["engagement"]
    evidence = tmp_path / "bando.txt"
    evidence.write_text("Bando sintetico selezionato per il test.\n", encoding="utf-8")
    imported = archive.import_studio_client_document(
        client["client_id"],
        evidence,
        "source",
        engagement_id=engagement["engagement_id"],
        state_dir=state_dir,
    )
    prepared = archive.prepare_studio_client_workflow(
        engagement["engagement_id"],
        "bandi-agevolazioni",
        input_ids=[imported["input_id"]],
        label="Dossier bando regionale",
        purpose="Prepare a source-backed grant application dossier.",
        idempotency_key="bandi-test-stage",
        state_dir=state_dir,
    )
    run_id = prepared["run"]["run_id"]
    archive.start_studio_client_workflow(
        client["client_id"],
        engagement["engagement_id"],
        run_id,
        state_dir=state_dir,
    )
    listed = archive.list_studio_client_engagements(
        client["client_id"], state_dir=state_dir
    )
    run = next(
        item
        for item in listed["engagements"][0]["workflow_runs"]
        if item["run_id"] == run_id
    )
    context = run["client_engagement"]
    source = next(
        path for path in Path(context["input_dir"]).rglob("*") if path.is_file()
    )
    return {
        "context_path": Path(run["client_engagement_path"]),
        "output_dir": Path(context["output_dir"]),
        "source": source,
        "run_id": run_id,
    }


def _initialized_case(
    tmp_path: Path,
) -> tuple[dict[str, ModuleType], dict[str, object]]:
    scripts = _scripts()
    workspace = _running_workspace(tmp_path)
    scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )
    scripts["register"].register_source(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        source=workspace["source"],
        source_id="SRC-CALL-001",
        source_type="call",
        title="Bando regionale sintetico",
        issuer="Ente regionale sintetico",
        authority_role="primary",
        selected_by="reviewer-001",
        publication_date="2026-07-01",
        effective_from="2026-07-01",
    )
    return scripts, workspace


def _reviewable_workbench(output_dir: Path) -> None:
    intake_path = output_dir / "case_intake.json"
    intake = _read(intake_path)
    intake["application"].update(  # type: ignore[union-attr]
        {
            "title": "Bando regionale sintetico",
            "issuing_authority": "Ente regionale sintetico",
            "procedure_id": "CALL-2026-001",
            "submission_deadline": "2026-09-30T12:00:00+00:00",
            "status": "confirmed",
        }
    )
    intake["applicant"].update(  # type: ignore[union-attr]
        {
            "legal_name": "Impresa Demo SPA",
            "tax_code": "01234567890",
            "vat_number": "01234567890",
            "confirmation_status": "confirmed",
        }
    )
    intake["project"].update(  # type: ignore[union-attr]
        {
            "title": "Progetto demo",
            "summary": "Progetto sintetico per la prova del workflow.",
            "requested_amount": "1000.00",
            "currency": "EUR",
            "confirmation_status": "confirmed",
        }
    )
    intake["professional_question"] = "Il dossier è completo e coerente?"
    _write(intake_path, intake)
    source_path = output_dir / "source_register.json"
    sources = _read(source_path)
    sources["sources"][0]["review_status"] = "reviewed"  # type: ignore[index]
    _write(source_path, sources)
    workbench_path = output_dir / "application_workbench.json"
    workbench = _read(workbench_path)
    excerpt = "Requisito sintetico selezionato esclusivamente per il test."
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    workbench.update(
        {
            "case_summary": "Dossier sintetico per verifica del workflow.",
            "requirements": [
                {
                    "requirement_id": "REQ-001",
                    "category": "eligibility",
                    "statement": "Requisito sintetico, non riutilizzabile come regola legale.",
                    "source_refs": [
                        {
                            "source_id": "SRC-CALL-001",
                            "locator": "paragrafo 1",
                            "excerpt": excerpt,
                            "excerpt_sha256": excerpt_hash,
                        }
                    ],
                    "applicability": "Da verificare sul caso.",
                    "expected_evidence": ["Visura aggiornata"],
                    "review_status": "confirmed",
                }
            ],
            "facts": [
                {
                    "fact_id": "FACT-001",
                    "field_code": "applicant.legal_name",
                    "value": "Impresa Demo SPA",
                    "as_of": "2026-08-07",
                    "source_ids": ["SRC-CALL-001"],
                    "kind": "document_observation",
                    "review_status": "confirmed",
                }
            ],
            "assessments": [
                {
                    "assessment_id": "ASM-001",
                    "requirement_id": "REQ-001",
                    "fact_ids": ["FACT-001"],
                    "readiness": "ready",
                    "outcome": "satisfied",
                    "rationale": "Giudizio professionale sintetico per il test.",
                    "evaluation_method": "model_led",
                    "deterministic_rule": None,
                    "review_status": "confirmed",
                }
            ],
            "document_checklist": [
                {
                    "document_id": "DOC-001",
                    "title": "Visura aggiornata",
                    "requirement_ids": ["REQ-001"],
                    "material_source_ids": ["SRC-CALL-001"],
                    "readiness": "ready",
                    "rationale": "Documento presente nel fascicolo sintetico.",
                    "review_status": "confirmed",
                }
            ],
            "expenses": [
                {
                    "expense_id": "EXP-001",
                    "description": "Preventivo sintetico",
                    "amount": "1000.00",
                    "currency": "EUR",
                    "requirement_ids": ["REQ-001"],
                    "source_ids": ["SRC-CALL-001"],
                    "readiness": "ready",
                    "outcome": "eligible",
                    "rationale": "Valutazione professionale sintetica per il test.",
                    "review_status": "confirmed",
                }
            ],
            "form_fields": [
                {
                    "field_id": "FIELD-LEGAL-NAME",
                    "label": "Denominazione",
                    "requirement_ids": ["REQ-001"],
                    "fact_ids": ["FACT-001"],
                    "proposed_value": "Impresa Demo SPA",
                    "readiness": "ready",
                    "rationale": "Valore proposto dal fatto confermato.",
                    "manual_only": False,
                    "declaration_control": False,
                    "signature_control": False,
                    "submission_control": False,
                    "review_status": "confirmed",
                },
                {
                    "field_id": "FIELD-SIGNATURE",
                    "label": "Firma",
                    "requirement_ids": [],
                    "fact_ids": [],
                    "proposed_value": None,
                    "readiness": "ready",
                    "rationale": "La firma resta alla persona autorizzata.",
                    "manual_only": True,
                    "declaration_control": False,
                    "signature_control": True,
                    "submission_control": False,
                    "review_status": "confirmed",
                },
            ],
            "narratives": [
                {
                    "narrative_id": "NAR-001",
                    "prompt": "Descrivere il progetto",
                    "draft": "Bozza narrativa sintetica.",
                    "requirement_ids": ["REQ-001"],
                    "fact_ids": ["FACT-001"],
                    "readiness": "ready",
                    "rationale": "Bozza supportata dal fatto confermato.",
                    "review_status": "confirmed",
                }
            ],
            "consistency_checks": [
                {
                    "check_id": "CONS-001",
                    "question": "La denominazione coincide tra le evidenze?",
                    "fact_ids": ["FACT-001"],
                    "source_ids": ["SRC-CALL-001"],
                    "outcome": "consistent",
                    "rationale": "La denominazione è coerente nel fascicolo sintetico.",
                    "review_status": "confirmed",
                }
            ],
            "issues": [],
            "authority_simulation": {
                "status": "reviewed",
                "reviewer_perspective": "Controllo formale sintetico dell'ente.",
                "overall_outcome": "pass",
                "checks": [
                    {
                        "check_id": "AUTH-001",
                        "question": "Il requisito ha evidenza e valutazione?",
                        "related_ids": [
                            "REQ-001",
                            "FACT-001",
                            "ASM-001",
                            "DOC-001",
                            "EXP-001",
                            "FIELD-LEGAL-NAME",
                            "FIELD-SIGNATURE",
                            "NAR-001",
                            "CONS-001",
                        ],
                        "outcome": "pass",
                        "rationale": "Requisito, fatto e documento sono collegati.",
                        "review_status": "confirmed",
                    }
                ],
            },
            "dossier": {
                "disposition": "ready_for_authorized_review",
                "ready_to_file": False,
                "limitations": ["Bozza non firmata e non inviata."],
            },
        }
    )
    _write(workbench_path, workbench)


def _accept_all_reviews(
    scripts: dict[str, ModuleType], workspace: dict[str, object]
) -> None:
    for scope in ("source_baseline", "requirements", "assessments", "dossier"):
        scripts["review"].record_review(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            scope=scope,
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=True,
        )


def test_component_contract_and_vera_wrapper_are_present() -> None:
    manifest = _read(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    skill = (PLUGIN_ROOT / "skills" / "bandi-agevolazioni" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    wrapper = (
        ROOT / "plugins" / "vera" / "skills" / "bandi-agevolazioni" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert manifest["name"] == "bandi-agevolazioni"
    assert "Never invent" in skill
    assert "never authenticates, signs, or files" in skill
    assert "modules/bandi-agevolazioni" in wrapper


def test_initialized_artifacts_validate_against_public_schemas(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    _, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    mapping = {
        "case_intake.schema.json": "case_intake.json",
        "source_register.schema.json": "source_register.json",
        "application_workbench.schema.json": "application_workbench.json",
        "review_log.schema.json": "review_log.json",
        "run_state.schema.json": "run_state.json",
    }
    for schema_name, artifact_name in mapping.items():
        schema = _read(PLUGIN_ROOT / "schemas" / schema_name)
        jsonschema.Draft202012Validator(schema).validate(
            _read(output_dir / artifact_name)
        )


def test_source_registration_is_idempotent_after_professional_review(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    register_path = workspace["output_dir"] / "source_register.json"
    register = _read(register_path)
    register["sources"][0]["review_status"] = "reviewed"  # type: ignore[index]
    _write(register_path, register)

    repeated = scripts["register"].register_source(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        source=workspace["source"],
        source_id="SRC-CALL-001",
        source_type="call",
        title="Bando regionale sintetico",
        issuer="Ente regionale sintetico",
        authority_role="primary",
        selected_by="reviewer-001",
        publication_date="2026-07-01",
        effective_from="2026-07-01",
    )

    assert repeated["review_status"] == "reviewed"
    assert _read(register_path)["source_set_revision"] == 1


def test_protected_portal_control_cannot_be_prefilled(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["form_fields"][1]["proposed_value"] = "signed"  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "protected_field_must_be_empty" in {
        issue["code"] for issue in audit["issues"]
    }


def test_reviewed_dossier_packages_without_filing_claims(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    _reviewable_workbench(output_dir)
    for scope in ("source_baseline", "requirements", "assessments", "dossier"):
        scripts["review"].record_review(
            output_dir=output_dir,
            client_engagement=workspace["context_path"],
            scope=scope,
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=True,
        )

    audit = scripts["validate"].validate_application(
        output_dir=output_dir,
        client_engagement=workspace["context_path"],
    )
    packaged = scripts["package"].package_dossier(
        output_dir=output_dir,
        client_engagement=workspace["context_path"],
    )
    manifest = _read(packaged["manifest"])
    dossier = packaged["dossier"].read_text(encoding="utf-8")

    assert audit["status"] == "passed"
    assert manifest["ready_to_file"] is False
    assert manifest["signature_actions_performed"] is False
    assert manifest["submission_actions_performed"] is False
    assert "NON FIRMATA E NON INVIATA" in dossier
    assert "1000.00" in dossier
    assert "Bozza narrativa sintetica." in dossier
    assert "Impresa Demo SPA" in dossier
    assert "excerpt=" in dossier
    assert "reviewer-001" in dossier
    assert "asserted_not_authenticated" in dossier
    assert "CALL-2026-001" in dossier
    assert "01234567890" in dossier
    assert "Progetto sintetico per la prova del workflow." in dossier
    assert "Il dossier è completo e coerente?" in dossier
    assert "ASM-001" in dossier
    assert "FACT-001" in dossier
    assert "model_led" in dossier
    assert {item["artifact_id"] for item in manifest["artifacts"]} >= {
        "evidence.case_intake",
        "evidence.source_register",
        "evidence.application_workbench",
        "evidence.review_log",
        "evidence.run_state",
    }


def test_source_change_makes_existing_reviews_stale(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    _reviewable_workbench(output_dir)
    for scope in ("source_baseline", "requirements", "assessments", "dossier"):
        scripts["review"].record_review(
            output_dir=output_dir,
            client_engagement=workspace["context_path"],
            scope=scope,
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=True,
        )
    register_path = output_dir / "source_register.json"
    register = _read(register_path)
    register["sources"][0]["relationships"] = [  # type: ignore[index]
        {"kind": "clarifies", "target_source_id": "SRC-CALL-001"}
    ]
    _write(register_path, register)

    audit = scripts["validate"].validate_application(
        output_dir=output_dir,
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert set(audit["review_states"].values()) == {"stale_or_missing"}
    assert "ready_disposition_has_stale_reviews" in {
        issue["code"] for issue in audit["issues"]
    }


def test_intake_change_invalidates_dependent_reviews(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    _reviewable_workbench(output_dir)
    _accept_all_reviews(scripts, workspace)
    intake_path = output_dir / "case_intake.json"
    intake = _read(intake_path)
    intake["applicant"]["legal_name"] = "Changed after review"  # type: ignore[index]
    _write(intake_path, intake)

    audit = scripts["validate"].validate_application(
        output_dir=output_dir,
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert audit["review_states"] == {
        "source_baseline": "accepted",
        "requirements": "stale_or_missing",
        "assessments": "stale_or_missing",
        "dossier": "stale_or_missing",
    }


def test_empty_workbench_cannot_be_ready(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["dossier"]["disposition"] = "ready_for_authorized_review"  # type: ignore[index]
    _write(workbench_path, workbench)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "ready_disposition_incomplete_dossier" in {
        issue["code"] for issue in audit["issues"]
    }


def test_runtime_validator_rejects_schema_invalid_populated_workbench(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["requirements"][0]["category"] = "invented"  # type: ignore[index]
    workbench["expenses"][0]["amount"] = "not-a-decimal"  # type: ignore[index]
    workbench["expenses"][0]["outcome"] = "invented"  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "schema_violation" in {issue["code"] for issue in audit["issues"]}


@pytest.mark.parametrize(
    "secret_key",
    [
        "session_cookie",
        "one_time_code",
        "auth_token",
        "api_key",
        "digital_signature",
    ],
)
def test_runtime_validator_rejects_normalized_secret_keys(
    tmp_path: Path,
    secret_key: str,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["facts"][0]["value"] = {secret_key: "must-not-persist"}  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "secret_or_session_material_forbidden" in {
        issue["code"] for issue in audit["issues"]
    }


def test_schema_valid_not_applicable_narrative_passes(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["dossier"]["disposition"] = "review_required"  # type: ignore[index]
    narrative = workbench["narratives"][0]  # type: ignore[index]
    narrative["readiness"] = "not_applicable"
    narrative["rationale"] = "Il bando sintetico non richiede questo campo."
    narrative["review_status"] = "confirmed"
    _write(workbench_path, workbench)
    schema = _read(PLUGIN_ROOT / "schemas" / "application_workbench.schema.json")
    jsonschema.Draft202012Validator(schema).validate(workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "passed"


def test_contradictory_deterministic_result_is_rejected(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    assessment = workbench["assessments"][0]  # type: ignore[index]
    assessment["evaluation_method"] = "deterministic"
    assessment["deterministic_rule"] = {
        "rule_id": "exact_decimal_compare",
        "version": "1",
        "reason": "Exact confirmed threshold comparison.",
        "inputs": {"left": "10", "operator": ">=", "right": "5"},
        "result": False,
        "outcome_map": {"true": "satisfied", "false": "not_satisfied"},
    }
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "deterministic_rule_not_reproducible" in {
        issue["code"] for issue in audit["issues"]
    }


def test_reproduced_deterministic_rule_can_pass(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    assessment = workbench["assessments"][0]  # type: ignore[index]
    assessment["evaluation_method"] = "deterministic"
    assessment["deterministic_rule"] = {
        "rule_id": "exact_decimal_compare",
        "version": "1",
        "reason": "Exact confirmed threshold comparison.",
        "inputs": {"left": "10", "operator": ">=", "right": "5"},
        "result": True,
        "outcome_map": {"true": "satisfied", "false": "not_satisfied"},
    }
    _write(workbench_path, workbench)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "passed"


def test_ready_assessment_rejects_unconfirmed_fact(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["facts"][0]["review_status"] = "proposed"  # type: ignore[index]
    _write(workbench_path, workbench)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "ready_assessment_uses_unconfirmed_fact" in {
        issue["code"] for issue in audit["issues"]
    }


def test_package_manifest_hashes_rendered_artifacts(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    _accept_all_reviews(scripts, workspace)
    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )
    assert audit["status"] == "passed"
    packaged = scripts["package"].package_dossier(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )
    manifest = _read(packaged["manifest"])
    by_id = {item["artifact_id"]: item for item in manifest["artifacts"]}

    assert by_id["deliverable.review_dossier"]["sha256"] == scripts[
        "package"
    ].sha256_file(packaged["dossier"])
    assert by_id["control.validation_audit"]["sha256"] == scripts[
        "package"
    ].sha256_file(workspace["output_dir"] / "validation_audit.json")


def test_ready_dossier_rejects_missing_traceability_and_authority_coverage(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["expenses"][0]["requirement_ids"] = []  # type: ignore[index]
    workbench["form_fields"][0]["fact_ids"] = []  # type: ignore[index]
    workbench["narratives"][0]["fact_ids"] = []  # type: ignore[index]
    workbench["authority_simulation"]["checks"][0]["related_ids"] = [  # type: ignore[index]
        "REQ-001"
    ]
    _write(workbench_path, workbench)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    codes = {issue["code"] for issue in audit["issues"]}
    assert audit["status"] == "failed"
    assert "ready_item_missing_traceability" in codes
    assert "authority_simulation_coverage_gap" in codes


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda workbench: workbench["form_fields"][0].update(
                {"proposed_value": None}
            ),
            "ready_form_field_missing_value",
        ),
        (
            lambda workbench: workbench["narratives"][0].update({"draft": ""}),
            "ready_narrative_missing_draft",
        ),
        (
            lambda workbench: workbench["expenses"][0].update(
                {
                    "readiness": "not_applicable",
                    "outcome": "ineligible",
                    "rationale": "Synthetic reviewed N/A.",
                }
            ),
            "expense_not_applicable_outcome_mismatch",
        ),
        (
            lambda workbench: workbench.update({"case_summary": ""}),
            "ready_disposition_has_unconfirmed_intake",
        ),
        (
            lambda workbench: workbench["facts"][0].update({"value": None}),
            "ready_disposition_has_empty_facts",
        ),
    ],
)
def test_ready_dossier_rejects_materially_empty_or_contradictory_content(
    tmp_path: Path,
    mutation,
    expected_code: str,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    mutation(workbench)
    _write(workbench_path, workbench)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert expected_code in {issue["code"] for issue in audit["issues"]}


def test_ready_dossier_requires_governing_call_dates_and_relationships(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    source_path = workspace["output_dir"] / "source_register.json"
    sources = _read(source_path)
    sources["sources"][0].update(  # type: ignore[index]
        {
            "source_type": "official_faq",
            "authority_role": "clarifying",
            "publication_date": None,
            "effective_from": None,
            "relationships": [],
        }
    )
    _write(source_path, sources)
    _accept_all_reviews(scripts, workspace)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    codes = {issue["code"] for issue in audit["issues"]}
    assert {
        "ready_disposition_missing_governing_call",
        "ready_disposition_has_undated_official_sources",
        "ready_disposition_has_unbound_dependent_sources",
    } <= codes


def test_requirement_contract_and_rationales_must_be_nonempty(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["requirements"][0]["applicability"] = ""  # type: ignore[index]
    workbench["requirements"][0]["expected_evidence"] = []  # type: ignore[index]
    workbench["assessments"][0]["rationale"] = ""  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "schema_violation" in {issue["code"] for issue in audit["issues"]}


def test_exact_excerpt_hash_must_match_stored_excerpt(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["requirements"][0]["source_refs"][0]["excerpt_sha256"] = "a" * 64  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert "excerpt_sha256_mismatch" in {issue["code"] for issue in audit["issues"]}


def test_material_issue_closure_requires_confirmed_review(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["issues"] = [
        {
            "issue_id": "ISSUE-001",
            "category": "document",
            "severity": "blocking",
            "detail": "Synthetic issue for closure review.",
            "related_ids": ["DOC-001"],
            "status": "resolved",
            "review_status": "proposed",
        }
    ]
    workbench["authority_simulation"]["checks"][0]["related_ids"].append(  # type: ignore[index]
        "ISSUE-001"
    )
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert "material_issue_closure_requires_confirmed_review" in {
        issue["code"] for issue in audit["issues"]
    }


def test_cross_type_id_collision_is_rejected(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["facts"][0]["fact_id"] = "REQ-001"  # type: ignore[index]
    _write(workbench_path, workbench)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert "cross_type_duplicate_id" in {issue["code"] for issue in audit["issues"]}


def test_malformed_relationship_returns_failed_audit_instead_of_crashing(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    register_path = workspace["output_dir"] / "source_register.json"
    register = _read(register_path)
    register["sources"][0]["relationships"] = [  # type: ignore[index]
        {"kind": ["clarifies"], "target_source_id": {"bad": "shape"}}
    ]
    _write(register_path, register)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert audit["status"] == "failed"
    assert "schema_violation" in {issue["code"] for issue in audit["issues"]}


def test_run_state_change_after_validation_blocks_packaging(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    _reviewable_workbench(workspace["output_dir"])
    _accept_all_reviews(scripts, workspace)
    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )
    assert audit["status"] == "passed"
    state_path = workspace["output_dir"] / "run_state.json"
    state = _read(state_path)
    state["portal_actions_performed"] = True
    _write(state_path, state)

    with pytest.raises(ValueError, match="validated artifacts changed"):
        scripts["package"].package_dossier(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
        )


def test_concurrent_case_change_during_render_blocks_packaging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    _reviewable_workbench(output_dir)
    _accept_all_reviews(scripts, workspace)
    audit = scripts["validate"].validate_application(
        output_dir=output_dir,
        client_engagement=workspace["context_path"],
    )
    assert audit["status"] == "passed"
    package_module = scripts["package"]
    original_write = package_module.write_private_text

    def mutate_after_render(path: Path, text: str) -> Path:
        rendered = original_write(path, text)
        if path.name == "review_dossier.md":
            workbench_path = output_dir / "application_workbench.json"
            workbench = _read(workbench_path)
            workbench["dossier"]["limitations"].append(  # type: ignore[index]
                "Changed during packaging."
            )
            _write(workbench_path, workbench)
        return rendered

    monkeypatch.setattr(package_module, "write_private_text", mutate_after_render)

    with pytest.raises(ValueError, match="changed during packaging"):
        package_module.package_dossier(
            output_dir=output_dir,
            client_engagement=workspace["context_path"],
        )
    assert not (output_dir / "dossier_manifest.json").exists()


def test_source_revision_mismatch_fails_validation(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    state_path = workspace["output_dir"] / "run_state.json"
    state = _read(state_path)
    state["source_set_revision"] = 0
    _write(state_path, state)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert "source_set_revision_mismatch" in {
        issue["code"] for issue in audit["issues"]
    }


def test_initialization_is_idempotent_and_recovers_stale_lock_file(
    tmp_path: Path,
) -> None:
    scripts = _scripts()
    workspace = _running_workspace(tmp_path)
    lock_path = workspace["output_dir"] / ".bandi-agevolazioni.lock"
    lock_path.write_text("stale owner metadata", encoding="utf-8")
    first = scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )
    second = scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )
    second["run_state"].unlink()
    recovered = scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )

    assert first == second
    assert recovered == second
    assert all(path.exists() for path in recovered.values())


def test_active_case_lock_rejects_a_concurrent_writer(tmp_path: Path) -> None:
    scripts = _scripts()
    workspace = _running_workspace(tmp_path)

    with scripts["initialize"].case_lock(workspace["output_dir"]):
        with pytest.raises(RuntimeError, match="mutation is in progress"):
            with scripts["initialize"].case_lock(workspace["output_dir"]):
                pytest.fail("a concurrent writer acquired the active case lock")


def test_case_lock_uses_windows_locking_backend_when_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts = _scripts()
    workspace = _running_workspace(tmp_path)
    core = scripts["core"]
    calls: list[int] = []

    class FakeMsvcrt:
        LK_NBLCK = 1
        LK_UNLCK = 2

        @staticmethod
        def locking(_descriptor: int, mode: int, _byte_count: int) -> None:
            calls.append(mode)

    original_import = core.importlib.import_module

    def import_backend(name: str):
        return FakeMsvcrt if name == "msvcrt" else original_import(name)

    monkeypatch.setattr(core.os, "name", "nt")
    monkeypatch.delattr(core.os, "fchmod", raising=False)
    monkeypatch.setattr(core.importlib, "import_module", import_backend)

    with core.case_lock(workspace["output_dir"]):
        assert calls == [FakeMsvcrt.LK_NBLCK]

    assert calls == [FakeMsvcrt.LK_NBLCK, FakeMsvcrt.LK_UNLCK]


def test_review_record_requires_explicit_user_confirmation(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)

    with pytest.raises(ValueError, match="explicit user confirmation"):
        scripts["review"].record_review(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            scope="source_baseline",
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=False,
        )


def test_review_record_discloses_asserted_identity_boundary(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)

    event = scripts["review"].record_review(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        scope="source_baseline",
        decision="accepted",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
    )

    assert event["confirmation_basis"] == "explicit_user_confirmation"
    assert event["identity_assurance"] == "asserted_not_authenticated"


def test_source_relationship_rejects_self_link(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)

    with pytest.raises(ValueError, match="cannot relate to itself"):
        scripts["link"].link_sources(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            source_id="SRC-CALL-001",
            kind="clarifies",
            target_source_id="SRC-CALL-001",
        )


def test_workflow_acceptance_cases_include_real_exemplar_without_rules() -> None:
    fixture = _read(PLUGIN_ROOT / "evals" / "workflow_acceptance_cases.json")
    cases = fixture["cases"]
    veneto = next(
        case
        for case in cases  # type: ignore[union-attr]
        if case["case_id"] == "regione-veneto-idatto-13223-intake"
    )

    assert veneto["procedure_reference"] == {
        "issuer": "Regione Veneto",
        "id_atto": "13223",
    }
    assert "must be supplied" in veneto["fixture_limit"]
    assert "eligibility_rules" not in veneto
    synthetic = next(
        case
        for case in cases  # type: ignore[union-attr]
        if case["case_id"] == "synthetic-reviewed-dossier-regression"
    )
    assert "contains no reusable eligibility or cost rule" in synthetic["fixture_limit"]
    assert (
        "a complete traceable state validates and packages"
        in synthetic["expected_public_behavior"]
    )
