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
        "intelligence_contract",
        "record_review",
        "schema_validation",
        "deterministic_rules",
        "opportunity_radar",
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
        opportunity_radar = _module_from_path(
            "bandi_test_opportunity_radar",
            SCRIPTS_ROOT / "opportunity_radar.py",
        )
        sys.modules["opportunity_radar"] = opportunity_radar
        intelligence_contract = _module_from_path(
            "bandi_test_intelligence_contract",
            SCRIPTS_ROOT / "intelligence_contract.py",
        )
        sys.modules["intelligence_contract"] = intelligence_contract
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
            "opportunity_radar": opportunity_radar,
            "link": _module_from_path(
                "bandi_test_link", SCRIPTS_ROOT / "link_sources.py"
            ),
            "review": review,
            "intelligence_contract": intelligence_contract,
            "intelligence": _module_from_path(
                "bandi_test_intelligence_workflow",
                SCRIPTS_ROOT / "intelligence_workflow.py",
            ),
            "evaluate_intelligence": _module_from_path(
                "bandi_test_evaluate_intelligence",
                SCRIPTS_ROOT / "evaluate_intelligence.py",
            ),
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


def _running_workspace(
    tmp_path: Path, *, selected_source: Path | None = None
) -> dict[str, object]:
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
    evidence = selected_source or tmp_path / "bando.txt"
    if selected_source is None:
        evidence.write_text(
            "Bando sintetico selezionato per il test.\n", encoding="utf-8"
        )
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


def _recommendation(
    *,
    action: str = "GUIDANCE",
    collection: str | None = None,
    target_id: str | None = None,
    payload: dict[str, object] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "recommendation_id": "REC-001",
        "action": action,
        "target_collection": collection,
        "target_id": target_id,
        "proposed_payload": payload,
        "rationale": "Proposta semantica da sottoporre a revisione professionale.",
        "evidence_refs": evidence_refs or [],
        "requested_evidence": [],
        "risk_flags": [],
        "alternatives": [],
        "confidence_band": "MEDIUM",
    }


def _model_output(recommendation: dict[str, object]) -> dict[str, object]:
    return {
        "summary_it": "Contributo non autoritativo per la revisione professionale.",
        "recommendations": [recommendation],
    }


def _orchestration_state(
    stage: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    intake: dict[str, object] = {
        "reference_date": "2026-08-07",
        "application": {},
        "project": {},
        "professional_question": "Synthetic workflow question.",
    }
    sources: dict[str, object] = {
        "source_set_revision": 1,
        "sources": [
            {
                "source_id": "SRC-001",
                "review_status": "new" if stage == "source" else "reviewed",
            }
        ],
    }
    workbench: dict[str, object] = {
        "requirements": [],
        "facts": [],
        "assessments": [],
        "document_checklist": [],
        "expenses": [],
        "form_fields": [],
        "narratives": [],
        "consistency_checks": [],
        "issues": [],
        "authority_simulation": {"status": "not_run", "checks": []},
        "dossier": {"disposition": "review_required"},
    }
    if stage in {"source", "requirements"}:
        return intake, sources, workbench
    category = {
        "cost": "cost",
        "form": "form",
        "narrative": "narrative",
    }.get(stage, "eligibility")
    workbench["requirements"] = [
        {
            "requirement_id": "REQ-001",
            "category": category,
            "review_status": (
                "proposed" if stage == "requirement_review" else "confirmed"
            ),
        }
    ]
    if stage in {"requirement_review", "evidence"}:
        return intake, sources, workbench
    workbench["facts"] = [{"fact_id": "FACT-001"}]
    workbench["document_checklist"] = [{"document_id": "DOC-001", "readiness": "ready"}]
    if stage == "assessment":
        return intake, sources, workbench
    workbench["assessments"] = [
        {
            "assessment_id": "ASM-001",
            "requirement_id": "REQ-001",
            "readiness": "missing" if stage == "missing" else "ready",
        }
    ]
    if stage in {"cost", "form", "narrative"}:
        return intake, sources, workbench
    workbench["consistency_checks"] = (
        [] if stage == "consistency" else [{"check_id": "CONS-001"}]
    )
    if stage == "complete":
        workbench["authority_simulation"] = {
            "status": "proposed",
            "checks": [{"check_id": "AUTH-001"}],
        }
    return intake, sources, workbench


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
    assert "Never contact a matched client automatically" in skill
    assert "without contacting clients, authenticating, signing, or filing" in wrapper
    assert "modules/bandi-agevolazioni" in wrapper


def test_initialized_artifacts_validate_against_public_schemas(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    _, workspace = _initialized_case(tmp_path)
    output_dir = workspace["output_dir"]
    mapping = {
        "case_intake.schema.json": "case_intake.json",
        "source_register.schema.json": "source_register.json",
        "application_workbench.schema.json": "application_workbench.json",
        "intelligence_register.schema.json": "intelligence_register.json",
        "review_log.schema.json": "review_log.json",
        "run_state.schema.json": "run_state.json",
    }
    for schema_name, artifact_name in mapping.items():
        schema = _read(PLUGIN_ROOT / "schemas" / schema_name)
        jsonschema.Draft202012Validator(schema).validate(
            _read(output_dir / artifact_name)
        )


def test_next_intelligence_packet_is_minimized_and_state_aware(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)

    packet = scripts["intelligence"].create_intelligence_packet(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert packet["task"] == "SOURCE_INTERPRETATION"
    assert packet["policy"]["evidence_is_untrusted_content"] is True
    assert packet["policy"]["automatic_anonymization"] is False
    assert packet["policy"]["reviewed_facts_or_excerpts_may_identify_applicant"] is True
    assert "applicant" not in packet["case_context"]
    assert "path" not in packet["untrusted_evidence"]["sources"][0]
    source_register = _read(workspace["output_dir"] / "source_register.json")
    source_register["sources"][0]["review_status"] = "reviewed"  # type: ignore[index]
    _write(workspace["output_dir"] / "source_register.json", source_register)

    next_packet = scripts["intelligence"].create_intelligence_packet(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert next_packet["task"] == "REQUIREMENT_DRAFTING"
    assert next_packet["orchestration"]["selected_automatically"] is True


@pytest.mark.parametrize(
    ("stage", "expected_task"),
    [
        ("source", "SOURCE_INTERPRETATION"),
        ("requirements", "REQUIREMENT_DRAFTING"),
        ("requirement_review", "WORKFLOW_GUIDANCE"),
        ("evidence", "EVIDENCE_MAPPING"),
        ("assessment", "ASSESSMENT_REASONING"),
        ("cost", "COST_CLASSIFICATION"),
        ("form", "FORM_PORTAL_GUIDANCE"),
        ("narrative", "NARRATIVE_DRAFTING"),
        ("consistency", "CONSISTENCY_REVIEW"),
        ("missing", "MISSING_INFO_RED_FLAGS"),
        ("authority", "AUTHORITY_SIMULATION"),
        ("complete", "WORKFLOW_GUIDANCE"),
    ],
)
def test_intelligence_orchestration_uses_only_mechanical_case_state(
    stage: str, expected_task: str
) -> None:
    scripts = _scripts()
    intake, sources, workbench = _orchestration_state(stage)

    packet = scripts["intelligence_contract"].build_next_intelligence_packet(
        intake, sources, workbench
    )

    assert packet["task"] == expected_task
    assert packet["orchestration"]["selected_automatically"] is True


def test_intelligence_output_rejects_evidence_outside_packet(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    packet = scripts["intelligence"].create_intelligence_packet(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        task="SOURCE_INTERPRETATION",
        subject_ids=["SRC-CALL-001"],
    )
    output = _model_output(
        _recommendation(
            action="CREATE",
            collection="issues",
            target_id="ISSUE-001",
            payload={
                "issue_id": "ISSUE-001",
                "category": "source_conflict",
                "severity": "review_required",
                "detail": "Verificare il rapporto tra le fonti.",
                "related_ids": ["SRC-NOT-IN-PACKET"],
                "status": "open",
                "review_status": "proposed",
            },
            evidence_refs=["SRC-NOT-IN-PACKET"],
        )
    )

    with pytest.raises(ValueError, match="outside its packet"):
        scripts["intelligence_contract"].validate_intelligence_output(packet, output)


def test_intelligence_output_requires_real_array_fields(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    packet = scripts["intelligence"].create_intelligence_packet(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )
    output = _model_output(_recommendation(evidence_refs=["SRC-CALL-001"]))
    output["recommendations"][0]["risk_flags"] = "not-an-array"  # type: ignore[index]

    with pytest.raises(ValueError, match="risk_flag must be a list"):
        scripts["intelligence_contract"].validate_intelligence_output(packet, output)


def test_recorded_intelligence_is_nonauthoritative_and_exactly_attributed(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    workbench_before = _read(workspace["output_dir"] / "application_workbench.json")
    output = _model_output(_recommendation(evidence_refs=["SRC-CALL-001"]))

    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=output,
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )
    repeated = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=output,
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )

    assert recorded["status"] == "MODEL_SUGGESTED"
    assert repeated == recorded
    assert (
        len(_read(workspace["output_dir"] / "intelligence_register.json")["runs"]) == 1
    )
    conflicting_output = dict(output)
    conflicting_output["summary_it"] = "Different response under the same key."
    with pytest.raises(ValueError, match="already used for another response"):
        scripts["intelligence"].record_intelligence(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            model_output=conflicting_output,
            provider="openai",
            model="gpt-test-pinned",
            prompt_template_version="bandi-v1",
            recorded_by="codex-local",
            idempotency_key="request-001",
            task="WORKFLOW_GUIDANCE",
            subject_ids=["SRC-CALL-001"],
        )
    assert recorded["requires_review"] is True
    assert recorded["model_metadata"] == {
        "provider": "openai",
        "model": "gpt-test-pinned",
        "prompt_template_version": "bandi-v1",
    }
    assert (
        _read(workspace["output_dir"] / "application_workbench.json")
        == workbench_before
    )


def test_intelligence_refuses_secret_or_session_fields_before_recording(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output = _model_output(_recommendation(evidence_refs=["SRC-CALL-001"]))
    output["api_key"] = "synthetic-secret-must-not-be-stored"

    with pytest.raises(ValueError, match="prohibited secret/session fields"):
        scripts["intelligence"].record_intelligence(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            model_output=output,
            provider="openai",
            model="gpt-test-pinned",
            prompt_template_version="bandi-v1",
            recorded_by="codex-local",
            idempotency_key="request-001",
            task="WORKFLOW_GUIDANCE",
            subject_ids=["SRC-CALL-001"],
        )

    assert _read(workspace["output_dir"] / "intelligence_register.json")["runs"] == []


def test_professional_accept_applies_only_as_proposed(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    sources_path = workspace["output_dir"] / "source_register.json"
    sources = _read(sources_path)
    sources["sources"][0]["review_status"] = "reviewed"  # type: ignore[index]
    _write(sources_path, sources)
    excerpt = "Requisito sintetico creato solo per il test del contratto."
    payload = {
        "requirement_id": "REQ-MODEL-001",
        "category": "eligibility",
        "statement": "Interpretazione proposta, non una regola legale riutilizzabile.",
        "source_refs": [
            {
                "source_id": "SRC-CALL-001",
                "locator": "sezione test",
                "excerpt": excerpt,
                "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
            }
        ],
        "applicability": "Da confermare sul caso concreto.",
        "expected_evidence": ["Evidenza da confermare"],
        "review_status": "confirmed",
    }
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=_model_output(
            _recommendation(
                action="CREATE",
                collection="requirements",
                target_id="REQ-MODEL-001",
                payload=payload,
                evidence_refs=["SRC-CALL-001"],
            )
        ),
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="REQUIREMENT_DRAFTING",
        subject_ids=["SRC-CALL-001"],
    )

    decided = scripts["intelligence"].decide_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        intelligence_run_id=recorded["intelligence_run_id"],
        decision="accepted",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
    )

    requirement = _read(workspace["output_dir"] / "application_workbench.json")[
        "requirements"
    ][0]
    assert decided["status"] == "ACCEPTED"
    assert decided["decision"]["confirmation_basis"] == "explicit_user_confirmation"
    assert requirement["review_status"] == "proposed"


def test_reject_does_not_mutate_workbench_and_repeated_decision_is_idempotent(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    output = _model_output(_recommendation(evidence_refs=["SRC-CALL-001"]))
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=output,
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )
    before = _read(workspace["output_dir"] / "application_workbench.json")
    kwargs = {
        "output_dir": workspace["output_dir"],
        "client_engagement": workspace["context_path"],
        "intelligence_run_id": recorded["intelligence_run_id"],
        "decision": "rejected",
        "reviewer_id": "reviewer-001",
        "reviewer_role": "commercialista",
        "confirmed_by_user": True,
    }

    first = scripts["intelligence"].decide_intelligence(**kwargs)
    repeated = scripts["intelligence"].decide_intelligence(**kwargs)

    assert first == repeated
    assert first["status"] == "REJECTED"
    assert _read(workspace["output_dir"] / "application_workbench.json") == before


def test_changed_case_marks_pending_intelligence_stale(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=_model_output(_recommendation(evidence_refs=["SRC-CALL-001"])),
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )
    workbench_path = workspace["output_dir"] / "application_workbench.json"
    workbench = _read(workbench_path)
    workbench["case_summary"] = "Nuovo contesto professionale."
    _write(workbench_path, workbench)

    with pytest.raises(ValueError, match="marked STALE"):
        scripts["intelligence"].decide_intelligence(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            intelligence_run_id=recorded["intelligence_run_id"],
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=True,
        )

    register = _read(workspace["output_dir"] / "intelligence_register.json")
    assert register["runs"][0]["status"] == "STALE"


def test_validation_fails_closed_during_interrupted_intelligence_apply(
    tmp_path: Path,
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=_model_output(_recommendation(evidence_refs=["SRC-CALL-001"])),
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )
    register_path = workspace["output_dir"] / "intelligence_register.json"
    register = _read(register_path)
    register["runs"][0]["status"] = "APPLYING"  # type: ignore[index]
    register["runs"][0]["decision"] = {  # type: ignore[index]
        "decision": "accepted",
        "reviewer_id": "reviewer-001",
        "reviewer_role": "commercialista",
        "confirmation_basis": "explicit_user_confirmation",
        "identity_assurance": "asserted_not_authenticated",
        "decided_at": "2026-08-07T12:00:00+00:00",
        "notes": "",
        "candidate_workbench_sha256": scripts["core"].canonical_json_sha256(
            _read(workspace["output_dir"] / "application_workbench.json")
        ),
    }
    _write(register_path, register)

    audit = scripts["validate"].validate_application(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
    )

    assert recorded["status"] == "MODEL_SUGGESTED"
    assert audit["status"] == "failed"
    assert "intelligence_application_incomplete" in {
        issue["code"] for issue in audit["issues"]
    }


def test_interrupted_acceptance_resumes_without_duplicate_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    payload = {
        "issue_id": "ISSUE-MODEL-RECOVERY",
        "category": "missing_information",
        "severity": "review_required",
        "detail": "Synthetic missing evidence for recovery testing.",
        "related_ids": ["SRC-CALL-001"],
        "status": "resolved",
        "review_status": "confirmed",
    }
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=_model_output(
            _recommendation(
                action="CREATE",
                collection="issues",
                target_id="ISSUE-MODEL-RECOVERY",
                payload=payload,
                evidence_refs=["SRC-CALL-001"],
            )
        ),
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="request-001",
        task="SOURCE_INTERPRETATION",
        subject_ids=["SRC-CALL-001"],
    )
    original_writer = scripts["intelligence"].write_private_json

    def fail_before_workbench(path: Path, payload: dict[str, object]) -> Path:
        if path.name == "application_workbench.json":
            raise RuntimeError("synthetic crash before workbench commit")
        return original_writer(path, payload)

    monkeypatch.setattr(
        scripts["intelligence"], "write_private_json", fail_before_workbench
    )
    decision = {
        "output_dir": workspace["output_dir"],
        "client_engagement": workspace["context_path"],
        "intelligence_run_id": recorded["intelligence_run_id"],
        "decision": "accepted",
        "reviewer_id": "reviewer-001",
        "reviewer_role": "commercialista",
        "confirmed_by_user": True,
    }

    with pytest.raises(RuntimeError, match="synthetic crash"):
        scripts["intelligence"].decide_intelligence(**decision)

    assert (
        _read(workspace["output_dir"] / "intelligence_register.json")["runs"][0][
            "status"
        ]
        == "APPLYING"
    )
    monkeypatch.setattr(scripts["intelligence"], "write_private_json", original_writer)

    recovered = scripts["intelligence"].decide_intelligence(**decision)
    issues = _read(workspace["output_dir"] / "application_workbench.json")["issues"]

    assert recovered["status"] == "ACCEPTED"
    assert [item["issue_id"] for item in issues] == ["ISSUE-MODEL-RECOVERY"]
    assert issues[0]["status"] == "open"
    assert issues[0]["review_status"] == "proposed"


def test_model_cannot_prefill_protected_portal_control(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    packet = scripts["intelligence"].create_intelligence_packet(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        task="FORM_PORTAL_GUIDANCE",
        subject_ids=[],
    )
    payload = {
        "field_id": "FIELD-SIGNATURE-MODEL",
        "label": "Firma",
        "requirement_ids": [],
        "fact_ids": [],
        "proposed_value": "firmato",
        "readiness": "verify",
        "rationale": "Controllo protetto.",
        "manual_only": False,
        "declaration_control": False,
        "signature_control": True,
        "submission_control": False,
        "review_status": "proposed",
    }

    with pytest.raises(ValueError, match="protected portal controls"):
        scripts["intelligence_contract"].validate_intelligence_output(
            packet,
            _model_output(
                _recommendation(
                    action="CREATE",
                    collection="form_fields",
                    target_id="FIELD-SIGNATURE-MODEL",
                    payload=payload,
                )
            ),
        )


def test_offline_intelligence_evaluation_matrix_passes() -> None:
    scripts = _scripts()
    cases = _read(PLUGIN_ROOT / "evals" / "intelligence_quality_cases.json")

    report = scripts["evaluate_intelligence"].evaluate_cases(cases)

    assert report["status"] == "passed"
    assert report["pass_rate"] == 1.0
    assert report["scope"] == "offline_contract_not_legal_accuracy"


def test_intelligence_packet_cli_uses_bound_case(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)

    result = scripts["intelligence"].main(
        [
            "--output-dir",
            str(workspace["output_dir"]),
            "--client-engagement",
            str(workspace["context_path"]),
            "packet",
        ]
    )

    assert result == 0


def test_intelligence_record_cli_seals_response(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    response_path = tmp_path / "model-output.json"
    _write(
        response_path,
        _model_output(_recommendation(evidence_refs=["SRC-CALL-001"])),
    )

    result = scripts["intelligence"].main(
        [
            "--output-dir",
            str(workspace["output_dir"]),
            "--client-engagement",
            str(workspace["context_path"]),
            "record",
            "--model-output",
            str(response_path),
            "--provider",
            "openai",
            "--model",
            "gpt-test-pinned",
            "--prompt-template-version",
            "bandi-v1",
            "--recorded-by",
            "codex-local",
            "--idempotency-key",
            "cli-request-001",
            "--task",
            "WORKFLOW_GUIDANCE",
            "--subject-id",
            "SRC-CALL-001",
        ]
    )

    assert result == 0
    assert (
        _read(workspace["output_dir"] / "intelligence_register.json")["runs"][0][
            "status"
        ]
        == "MODEL_SUGGESTED"
    )


def test_intelligence_decide_cli_records_return(tmp_path: Path) -> None:
    scripts, workspace = _initialized_case(tmp_path)
    recorded = scripts["intelligence"].record_intelligence(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        model_output=_model_output(_recommendation(evidence_refs=["SRC-CALL-001"])),
        provider="openai",
        model="gpt-test-pinned",
        prompt_template_version="bandi-v1",
        recorded_by="codex-local",
        idempotency_key="cli-decision-001",
        task="WORKFLOW_GUIDANCE",
        subject_ids=["SRC-CALL-001"],
    )

    result = scripts["intelligence"].main(
        [
            "--output-dir",
            str(workspace["output_dir"]),
            "--client-engagement",
            str(workspace["context_path"]),
            "decide",
            "--intelligence-run-id",
            str(recorded["intelligence_run_id"]),
            "--decision",
            "returned",
            "--reviewer-id",
            "reviewer-001",
            "--reviewer-role",
            "commercialista",
            "--confirmed-by-user",
        ]
    )

    assert result == 0
    assert (
        _read(workspace["output_dir"] / "intelligence_register.json")["runs"][0][
            "status"
        ]
        == "RETURNED"
    )


def test_intelligence_evaluation_cli_passes() -> None:
    scripts = _scripts()

    result = scripts["evaluate_intelligence"].main(
        [
            "--cases",
            str(PLUGIN_ROOT / "evals" / "intelligence_quality_cases.json"),
        ]
    )

    assert result == 0


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


def test_opportunity_handoff_is_validated_before_source_registration(
    tmp_path: Path,
) -> None:
    scripts = _scripts()
    malformed_handoff = tmp_path / "malformed-handoff.json"
    _write(malformed_handoff, {"schema_version": "2.0"})
    workspace = _running_workspace(tmp_path, selected_source=malformed_handoff)
    scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )

    with pytest.raises(ValueError, match="opportunity_handoff"):
        scripts["register"].register_source(
            output_dir=workspace["output_dir"],
            client_engagement=workspace["context_path"],
            source=workspace["source"],
            source_id="SRC-HANDOFF-001",
            source_type="opportunity_handoff",
            title="Reviewed radar selection",
            issuer="Vera opportunity radar",
            authority_role="mechanical",
            selected_by="reviewer-001",
        )

    assert _read(workspace["output_dir"] / "source_register.json")["sources"] == []


def test_verified_opportunity_handoff_registers_as_mechanical_source(
    tmp_path: Path,
) -> None:
    from tests.plugins.test_bandi_opportunity_radar import (
        _contribution_args,
        _evidence,
        _match,
        _opportunity,
        _profile,
        _scan,
        _source,
    )

    scripts = _scripts()
    radar = scripts["opportunity_radar"]
    radar_workspace = tmp_path / "private-radar"
    radar.initialize_radar(
        radar_workspace,
        radar_id="RADAR-001",
        workspace_id="WORKSPACE-001",
        reference_date="2026-08-07",
        scope="single_client",
        authorized_by="reviewer-001",
        retention_owner="Studio Demo",
        confirmed_by_user=True,
    )
    radar.record_profile_evidence(
        radar_workspace,
        evidence=_evidence(),
        idempotency_key="evidence-1",
        **_contribution_args(),
    )
    radar.record_profile(
        radar_workspace,
        profile=_profile(),
        idempotency_key="profile-1",
        **_contribution_args(),
    )
    radar.record_source(
        radar_workspace,
        source=_source(),
        idempotency_key="source-1",
        **_contribution_args(),
    )
    radar.review_item(
        radar_workspace,
        scope="source",
        target_id="SOURCE-REGION",
        decision="accepted",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key="review-source",
    )
    radar.record_scan(
        radar_workspace,
        scan=_scan(),
        next_scan_on=None,
        idempotency_key="scan-start-1",
        **_contribution_args(),
    )
    radar.review_item(
        radar_workspace,
        scope="scan_source_selection",
        target_id="SCAN-001",
        decision="accepted",
        reviewer_id="reviewer-001",
        reviewer_role="commercialista",
        confirmed_by_user=True,
        idempotency_key="review-scan-source-selection",
    )
    radar.record_source_check(
        radar_workspace,
        source_id="SOURCE-REGION",
        check_id="CHECK-001",
        scan_id="SCAN-001",
        check_status="checked",
        checked_at="2026-08-07T11:00:00+00:00",
        window_start="2026-06-09",
        window_end="2026-08-07",
        next_check_on="2026-08-08",
        result_count=1,
        error_code=None,
        cursor_after=None,
        idempotency_key="source-check-1",
    )
    radar.record_opportunity(
        radar_workspace,
        opportunity=_opportunity(),
        idempotency_key="opportunity-1",
        **_contribution_args(),
    )
    radar.record_match(
        radar_workspace,
        match=_match(),
        idempotency_key="match-1",
        **_contribution_args(),
    )
    for scope, target in (
        ("evidence", "EVIDENCE-CLIENT-001"),
        ("profile", "CLIENT-001"),
        ("source_check", "SOURCE-REGION"),
        ("opportunity", "OPP-001"),
        ("match", "MATCH-CLIENT-001"),
    ):
        radar.review_item(
            radar_workspace,
            scope=scope,
            target_id=target,
            decision="accepted",
            reviewer_id="reviewer-001",
            reviewer_role="commercialista",
            confirmed_by_user=True,
            idempotency_key=f"review-{scope}",
        )
    handoff = radar.create_handoff(
        radar_workspace,
        match_id="MATCH-CLIENT-001",
        output_path=radar_workspace / "handoff.json",
    )

    workspace = _running_workspace(tmp_path, selected_source=handoff)
    scripts["initialize"].initialize_case(
        workspace["output_dir"],
        client_engagement=workspace["context_path"],
        reference_date="2026-08-07",
        client_reference="CLIENT-001",
    )
    record = scripts["register"].register_source(
        output_dir=workspace["output_dir"],
        client_engagement=workspace["context_path"],
        source=workspace["source"],
        source_id="SRC-HANDOFF-001",
        source_type="opportunity_handoff",
        title="Reviewed radar selection",
        issuer="Vera opportunity radar",
        authority_role="mechanical",
        selected_by="reviewer-001",
    )

    assert record["source_type"] == "opportunity_handoff"
    assert record["authority_role"] == "mechanical"


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
    assert "Contributi Codex registrati" in dossier
    assert {item["artifact_id"] for item in manifest["artifacts"]} >= {
        "evidence.case_intake",
        "evidence.source_register",
        "evidence.application_workbench",
        "evidence.intelligence_register",
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
