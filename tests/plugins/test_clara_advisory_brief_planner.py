from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SKILL_ROOT = CLARA_ROOT / "skills" / "advisory-brief-planner"
SCHEMA_PATH = CLARA_ROOT / "contracts" / "advisory_contract.v1.schema.json"
SCRIPT_PATH = CLARA_ROOT / "scripts" / "validate_advisory_contract.py"
REQUIRED_SEMANTIC_FIELDS = {
    "decision",
    "purpose",
    "audience",
    "deliverable_type",
    "output_language",
    "scope_included",
    "scope_excluded",
    "available_inputs",
    "evidence_requirements",
    "analysis_plan",
    "assumptions",
    "unresolved_questions",
    "success_criteria",
    "selected_clara_workflow",
    "validation_profile",
    "validation_scope",
    "correction_policy",
    "professional_judgement_policy",
}


def _load_validator() -> Any:
    """Load the planner validator from plugin source."""

    module_name = "test_clara_advisory_contract_validator"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _representative_contract() -> dict[str, Any]:
    """Return one domain-neutral, purpose-preserving advisory contract."""

    dimensions = {
        "material_facts_dates_numbers_entities_constraints_questions": "conforms",
        "decision_purpose_audience_deliverable": "conforms",
        "scope_inputs_evidence": "conforms",
        "analysis_and_success_criteria": "conforms",
        "workflow_and_generation_handoff": "conforms",
        "validation_and_professional_judgement": "conforms",
    }
    return {
        "schema_version": "1.0",
        "contract_status": "ready_for_handoff",
        "decision": "Whether the board should integrate the sales teams before 2027-01-15.",
        "purpose": "Give the board an evidence-backed integration decision and conditions.",
        "audience": "Board of Aurora Foods",
        "deliverable_type": "Board decision brief",
        "output_language": "en",
        "scope_included": [
            "Customer-retention implications of integrating the sales teams",
            "Implementation conditions before 2027-01-15",
        ],
        "scope_excluded": ["France"],
        "available_inputs": [
            {
                "id": "assignment",
                "description": "Natural advisory assignment from the board sponsor",
                "status": "available",
                "source_ref": "assignment.md",
            }
        ],
        "evidence_requirements": [
            {
                "id": "customer-loss-evidence",
                "requirement": "Evidence on customer losses that could change the integration decision",
                "rationale": "The assignment names customer loss as the decision-changing test.",
                "status": "planned",
                "input_ids": ["assignment"],
            }
        ],
        "analysis_plan": [
            {
                "id": "decision-conditions",
                "objective": "Identify the customer-retention conditions for integration",
                "method": "Weigh available customer evidence and test decision-changing losses",
                "input_ids": ["assignment"],
                "output": "Conditioned recommendation for the board",
            }
        ],
        "assumptions": [
            {
                "statement": "The requested EUR 12.5 million acquisition price is contextual, not a decision threshold.",
                "status": "provisional",
                "materiality": "contextual",
            }
        ],
        "unresolved_questions": [],
        "success_criteria": [
            "The brief states whether to integrate and what customer evidence would reverse the recommendation.",
            "France remains outside scope.",
        ],
        "selected_clara_workflow": "clara:clara",
        "validation_profile": {
            "review_dimensions": [
                "contract_conformance",
                "factual_source_support",
                "calculations_data_provenance",
                "reasoning_assumptions",
                "contradictions_missing_evidence",
                "recommendation_evidence_decision_fit",
                "professional_judgement_boundaries",
                "correction_needs",
                "residual_uncertainty",
                "delivery_readiness",
            ],
            "format_checks": [],
        },
        "validation_scope": {
            "coverage": "all_material_content",
            "included_sections": [
                "All material recommendation claims",
                "Dates, figures, entities, constraints, and explicit questions",
            ],
            "excluded_sections": [],
            "limitations": [],
        },
        "correction_policy": {
            "mode": "separate_artifact",
            "preserve_original": True,
            "allowed": True,
            "approval_required_before_delivery": True,
        },
        "professional_judgement_policy": {
            "owner": "Consultant",
            "model_role": "Identify issues and draft evidence-bounded corrections",
            "approval_required_before_delivery": True,
        },
        "source_facts": [
            {
                "category": "entity",
                "text": "Aurora Foods acquired Delta Retail.",
                "source_anchor": "Aurora Foods acquired Delta Retail",
                "input_id": "assignment",
            },
            {
                "category": "date",
                "text": "The acquisition date is 2026-09-30.",
                "source_anchor": "2026-09-30",
                "literal_value": "2026-09-30",
                "input_id": "assignment",
            },
            {
                "category": "number",
                "text": "The acquisition price is EUR 12.5 million.",
                "source_anchor": "EUR 12.5 million",
                "literal_value": "EUR 12.5",
                "input_id": "assignment",
            },
            {
                "category": "date",
                "text": "The decision concerns integration before 2027-01-15.",
                "source_anchor": "2027-01-15",
                "literal_value": "2027-01-15",
                "input_id": "assignment",
            },
            {
                "category": "constraint",
                "text": "France is outside scope.",
                "source_anchor": "Keep France outside scope",
                "input_id": "assignment",
            },
        ],
        "explicit_questions": [
            {
                "question": "Which customer losses could change the decision?",
                "input_id": "assignment",
            }
        ],
        "generation_handoff": {
            "workflow": "clara:clara",
            "objective": "Prepare the board's integration decision brief.",
            "input_ids": ["assignment"],
            "instructions": [
                "Use the advisory evidence and workpaper loops before drafting the board brief.",
                "Keep France outside scope and preserve every dated decision condition.",
            ],
            "expected_outputs": [
                "advisory_evidence_map.md",
                "advisory_workpaper.md",
                "decision_pack.md",
            ],
            "preserve_specialist_authority": True,
        },
        "model_review": {
            "method": "model_led_assignment_contract_review",
            "dimensions": dimensions,
            "overall_status": "conforms",
        },
    }


def test_advisory_contract_schema_publishes_required_cross_workflow_fields() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == "1.0"
    assert REQUIRED_SEMANTIC_FIELDS <= set(schema["required"])
    assert "Semantic contents are selected by Clara" in schema["description"]


def test_advisory_contract_packages_exact_facts_and_generation_handoff(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    source = tmp_path / "assignment.md"
    source.write_text(
        "Aurora Foods acquired Delta Retail on 2026-09-30 for EUR 12.5 million. "
        "The board must decide whether to integrate the sales teams before 2027-01-15. "
        "Keep France outside scope. Which customer losses could change the decision?\n",
        encoding="utf-8",
    )
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(
        json.dumps(_representative_contract(), ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "reviewed"

    contract_path, report_path, errors = validator.package_advisory_contract(
        draft,
        output_dir,
        source_paths={"assignment": source},
    )

    assert errors == []
    assert contract_path == output_dir / "advisory_contract.json"
    assert report_path == output_dir / "advisory_contract_validation.json"
    packaged = json.loads(contract_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert packaged["selected_clara_workflow"] == "clara:clara"
    assert packaged["generation_handoff"]["preserve_specialist_authority"] is True
    assert packaged["scope_excluded"] == ["France"]
    assert packaged["explicit_questions"][0]["question"] == (
        "Which customer losses could change the decision?"
    )
    assert report["status"] == "passed"
    assert report["source_files"][0]["filename"] == "assignment.md"
    assert report["literal_inventory"]["assignment"]["dates"] == [
        "2026-09-30",
        "2027-01-15",
    ]


def test_advisory_contract_rejects_inexact_declared_number_before_packaging(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    source = tmp_path / "assignment.md"
    source.write_text(
        "Aurora Foods acquired Delta Retail on 2026-09-30 for EUR 12.5 million. "
        "The board must decide whether to integrate the sales teams before 2027-01-15. "
        "Keep France outside scope. Which customer losses could change the decision?\n",
        encoding="utf-8",
    )
    payload = _representative_contract()
    payload["source_facts"][2]["literal_value"] = "12"
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")

    contract_path, report_path, errors = validator.package_advisory_contract(
        draft,
        tmp_path / "reviewed",
        source_paths={"assignment": source},
    )

    assert contract_path is None
    assert any("number literal" in error for error in errors)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["canonical_artifact_written"] is False


def test_advisory_contract_inventory_does_not_classify_incidental_number_as_material(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    source = tmp_path / "assignment.md"
    source.write_text(
        "Aurora Foods acquired Delta Retail on 2026-09-30 for EUR 12.5 million. "
        "The board must decide whether to integrate the sales teams before 2027-01-15. "
        "Keep France outside scope. Which customer losses could change the decision? "
        "Document version 777.\n",
        encoding="utf-8",
    )
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(_representative_contract()), encoding="utf-8")

    contract_path, report_path, errors = validator.package_advisory_contract(
        draft,
        tmp_path / "reviewed",
        source_paths={"assignment": source},
    )

    assert errors == []
    assert contract_path is not None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "777" in report["literal_inventory"]["assignment"]["numbers"]
    assert "observational" in report["limitations"][1]


def test_advisory_contract_distinguishes_exact_integer_from_decimal_literal(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    source = tmp_path / "assignment.md"
    source.write_text(
        "Aurora Foods acquired Delta Retail on 2026-09-30 for EUR 12.5 million. "
        "The board must decide whether to integrate the sales teams before 2027-01-15. "
        "Keep France outside scope. The decision threshold is 12. "
        "Which customer losses could change the decision?\n",
        encoding="utf-8",
    )
    payload = _representative_contract()
    payload["source_facts"].append(
        {
            "category": "number",
            "text": "The decision threshold is 12.",
            "source_anchor": "decision threshold is 12",
            "literal_value": "12",
            "input_id": "assignment",
        }
    )
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")

    contract_path, _, errors = validator.package_advisory_contract(
        draft,
        tmp_path / "reviewed",
        source_paths={"assignment": source},
    )

    assert errors == []
    assert contract_path is not None


def test_advisory_contract_requires_nonempty_generation_handoff_inputs() -> None:
    validator = _load_validator()
    payload = _representative_contract()
    payload["generation_handoff"]["input_ids"] = []

    errors = validator.validate_advisory_contract(payload)

    assert any(
        error.startswith("schema generation_handoff.input_ids:") for error in errors
    )


def test_advisory_contract_handoff_covers_all_referenced_inputs() -> None:
    validator = _load_validator()
    payload = _representative_contract()
    payload["available_inputs"].append(
        {
            "id": "selected-notes",
            "description": "Selected operating notes",
            "status": "available",
        }
    )
    payload["evidence_requirements"][0]["input_ids"].append("selected-notes")

    errors = validator.validate_advisory_contract(payload)

    assert any(
        "generation_handoff.input_ids must include every input referenced" in error
        and "'selected-notes'" in error
        for error in errors
    )


def test_failed_rerun_archives_prior_canonical_and_replaces_validation_report(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(_representative_contract()), encoding="utf-8")
    output_dir = tmp_path / "reviewed"
    validator.package_advisory_contract(draft, output_dir)
    invalid_payload = _representative_contract()
    invalid_payload["decision"] = ""
    draft.write_text(json.dumps(invalid_payload), encoding="utf-8")

    contract_path, report_path, errors = validator.package_advisory_contract(
        draft, output_dir
    )

    assert contract_path is None
    assert errors
    assert not (output_dir / "advisory_contract.json").exists()
    recovery_paths = list(output_dir.glob("advisory_contract.previous-*.json"))
    assert len(recovery_paths) == 1
    recovered = json.loads(recovery_paths[0].read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert recovered["decision"] == _representative_contract()["decision"]
    assert report["status"] == "failed"
    assert report["invalidated_prior_canonical"]["filename"] == recovery_paths[0].name


def test_malformed_rerun_archives_prior_canonical_and_writes_current_failure(
    tmp_path: Path,
) -> None:
    validator = _load_validator()
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(_representative_contract()), encoding="utf-8")
    output_dir = tmp_path / "reviewed"
    validator.package_advisory_contract(draft, output_dir)
    draft.write_text("{not-json", encoding="utf-8")

    with pytest.raises(validator.ContractValidationError):
        validator.package_advisory_contract(draft, output_dir)

    report = json.loads(
        (output_dir / "advisory_contract_validation.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "failed"
    assert "invalid JSON" in report["errors"][0]
    assert report["invalidated_prior_canonical"] is not None
    assert not (output_dir / "advisory_contract.json").exists()


def test_invalid_source_argument_replaces_stale_success_report(tmp_path: Path) -> None:
    validator = _load_validator()
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(_representative_contract()), encoding="utf-8")
    output_dir = tmp_path / "reviewed"
    validator.package_advisory_contract(draft, output_dir)

    exit_code = validator.main(
        [str(draft), "--output-dir", str(output_dir), "--source", "invalid"]
    )

    report = json.loads(
        (output_dir / "advisory_contract_validation.json").read_text(encoding="utf-8")
    )
    assert exit_code == 2
    assert report["status"] == "failed"
    assert "invalid --source" in report["errors"][0]
    assert report["invalidated_prior_canonical"] is not None
    assert not (output_dir / "advisory_contract.json").exists()


def test_advisory_contract_rejects_inconsistent_ready_state_and_route() -> None:
    validator = _load_validator()
    payload = copy.deepcopy(_representative_contract())
    payload["selected_clara_workflow"] = "clara:advisory-brief-planner"
    payload["generation_handoff"]["workflow"] = "clara:advisory-brief-planner"
    payload["unresolved_questions"] = [
        {
            "question": "Which board committee owns the decision?",
            "why_it_matters": "Ownership changes the decision process.",
            "blocking": True,
        }
    ]

    errors = validator.validate_advisory_contract(payload)

    assert any("non-developer Clara handoff workflow" in error for error in errors)
    assert "ready_for_handoff cannot retain a blocking unresolved question" in errors


def test_advisory_planner_is_routed_packaged_and_public_in_five_locales() -> None:
    router = (CLARA_ROOT / "skills" / "clara" / "SKILL.md").read_text(encoding="utf-8")
    catalog = (
        CLARA_ROOT / "skills" / "clara" / "references" / "workflow-catalog.md"
    ).read_text(encoding="utf-8")
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    page = (
        ROOT / "static" / "shared" / "clara-advisory-planning" / "index.html"
    ).read_text(encoding="utf-8")
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")
    planner_copy = function_copy.split('"clara-advisory-planning":', 1)[1].split(
        '"clara-presentations":', 1
    )[0]
    clara_page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "first use `advisory-brief-planner`" in router
    assert "- `advisory-brief-planner`:" in catalog
    assert "not generic prompt polishing" in skill
    assert "Do not add or use a keyword classifier" in skill
    assert "never calls a model API" in skill
    assert 'display_name: "Plan an advisory assignment"' in metadata
    assert 'data-function-page="clara-advisory-planning"' in page
    assert planner_copy.count('modelDataStatus: "relevant"') == 5
    assert "The script does not call the model or upload files." in planner_copy
    assert (
        "a downstream Clara workflow may use such a route only under its own rules"
        in planner_copy
    )
    assert 'href="../clara-advisory-planning/index.html?lang=en"' in clara_page
    assert clara_page.count('"functions.advisoryPlanning":') == 5


def test_advisory_planner_privacy_record_has_no_external_boundary() -> None:
    manifest = json.loads(
        (
            CLARA_ROOT / "privacy" / "workflows" / "advisory-brief-planner.json"
        ).read_text(encoding="utf-8")
    )
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert manifest["hosted_service_ids"] == []
    assert manifest["boundaries_beyond_codex"] == []
    assert manifest["security_controls"] == []
    assert "query_llm" not in source
    assert "openai" not in source.casefold()
    assert "requests." not in source
