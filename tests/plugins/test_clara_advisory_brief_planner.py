from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

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
        "validation_profile": "Decision brief evidence, reasoning, and source traceability review",
        "validation_scope": [
            "All material recommendation claims",
            "Dates, figures, entities, constraints, and explicit questions",
        ],
        "correction_policy": "Correct factual or source-supported errors before delivery; return judgement changes for consultant review.",
        "professional_judgement_policy": "The consultant confirms the integration recommendation and any accepted risk threshold.",
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
                "input_id": "assignment",
            },
            {
                "category": "number",
                "text": "The acquisition price is EUR 12.5 million.",
                "source_anchor": "EUR 12.5 million",
                "input_id": "assignment",
            },
            {
                "category": "date",
                "text": "The decision concerns integration before 2027-01-15.",
                "source_anchor": "2027-01-15",
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


def test_advisory_contract_rejects_missing_literal_number_before_packaging(
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
    payload["source_facts"] = [
        fact for fact in payload["source_facts"] if fact["category"] != "number"
    ]
    draft = tmp_path / "draft_advisory_contract.json"
    draft.write_text(json.dumps(payload), encoding="utf-8")

    contract_path, report_path, errors = validator.package_advisory_contract(
        draft,
        tmp_path / "reviewed",
        source_paths={"assignment": source},
    )

    assert contract_path is None
    assert any("number literal is not preserved" in error for error in errors)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["canonical_artifact_written"] is False


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
