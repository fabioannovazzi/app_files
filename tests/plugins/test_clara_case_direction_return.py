from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SCRIPTS = CLARA_ROOT / "scripts"
RETURN_SCHEMA = (
    CLARA_ROOT / "contracts" / "advisory_case_direction_return.v1.schema.json"
)


def _load_core() -> Any:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(
            "clara_case_direction_return_core", SCRIPTS / "advisor_case_core.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture
def core() -> Any:
    return _load_core()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, *, case_dir: Path, role: str | None = None) -> dict[str, Any]:
    receipt = {
        "path": str(path.relative_to(case_dir)),
        "path_reference": "case_relative",
        "sha256": _sha256(path),
        "byte_count": path.stat().st_size,
    }
    if role is not None:
        receipt["role"] = role
    return receipt


def _evidence(
    artifact: dict[str, Any],
    *,
    evidence_id: str = "ev-research-001",
    recorded_at: str = "2026-08-26T08:00:00+00:00",
) -> dict[str, Any]:
    evidence_artifact = {key: value for key, value in artifact.items() if key != "role"}
    return {
        "id": evidence_id,
        "evidence_type": "local_document",
        "recorded_at": recorded_at,
        "recorded_by": "clara:advisory-case-director",
        "capture_status": "captured",
        "source": {
            "material_ids": [],
            "url": "",
            "locator": "Bounded research output",
            "artifact_refs": [evidence_artifact],
        },
        "observation": "The bounded comparison supports a plausible market mechanism.",
        "scope": "The reviewed comparison and period only.",
        "limitations": ["It does not establish target execution."],
        "verification": {
            "status": "identity_verified",
            "checked_at": recorded_at,
            "method": "Exact local artifact hash checked.",
            "notes": [],
        },
        "rechecks_evidence_id": "",
        "supersedes_evidence_id": "",
    }


def _claim(
    *,
    claim_id: str = "cl-market-001",
    evidence_id: str = "ev-research-001",
    recorded_at: str = "2026-08-26T08:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "statement": "A sufficiently durable market mechanism is plausible enough to investigate.",
        "claim_type": "conclusion",
        "recorded_at": recorded_at,
        "recorded_by": "clara:advisory-case-director",
        "provenance": {
            "workflow": "clara:advisory-case-director",
            "step": "bounded research return",
            "artifact": "source_materials/research.md",
            "locator": "Conclusion",
        },
        "evidence_links": [
            {
                "evidence_id": evidence_id,
                "relationship": "supports",
                "analysis": "The comparison supports a bounded market-level mechanism.",
                "proves": "The mechanism is plausible in the reviewed scope.",
                "does_not_prove": "The target captures the mechanism.",
            }
        ],
        "dependency": {
            "mode": "none",
            "claim_ids": [],
            "derivation_type": "reasoning",
            "explanation": "The model interpreted the bounded comparison.",
            "calculation_evidence_id": "",
        },
        "decision_use": "direct",
        "uncertainty": ["Target capability remains untested."],
        "professional_judgement_required": True,
        "appearances": [],
        "state": "active",
        "supersedes_claim_id": "",
    }


def _case(core: Any, tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    case_dir = tmp_path / "case"
    now = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    core.initialize_case(
        case_dir,
        client="Synthetic client",
        project="Synthetic diligence",
        objective="Decide whether to continue diligence",
        audience="Engagement partner",
        output_language="en",
        now=now,
    )
    question = core.add_open_question(
        case_dir,
        question="Is there a plausible durable market mechanism?",
        why_it_matters="It determines whether target diligence is worth continuing.",
        now=now,
    )
    research = case_dir / "source_materials" / "research.md"
    research.parent.mkdir(parents=True)
    research.write_text("Reviewed bounded comparison.\n", encoding="utf-8")
    return case_dir, question


def _analysis_return(case_dir: Path, question: dict[str, Any]) -> dict[str, Any]:
    research = case_dir / "source_materials" / "research.md"
    artifact = _artifact(research, case_dir=case_dir, role="branch_output")
    return {
        "schema_version": "1.0",
        "return_id": "return-research-001",
        "return_type": "analysis_branch",
        "branch": {
            "workflow": "clara:advisory-case-director",
            "question_id": question["id"],
            "question": question["question"],
            "answer": "A bounded market mechanism is plausible, but target capture is unproven.",
        },
        "answer_effect": "strengthens",
        "result_claim_ids": ["cl-market-001"],
        "source_artifacts": [artifact],
        "limitations": ["Target execution remains outside the evidence."],
        "evidence_receipts": [_evidence(artifact)],
        "claims": [_claim()],
        "judgement_entries": [
            {
                "kind": "advisor_judgement",
                "text": "The partner asked whether the target captures the mechanism.",
                "status": "pending",
                "source_material_ids": [],
                "rationale": "This question originated with the partner.",
                "advisory_claim_id": "",
                "evidence_receipt_ids": [],
            }
        ],
        "question_updates": [
            {
                "question_id": question["id"],
                "status": "answered",
                "explanation": "The bounded market question is answered at market level.",
            }
        ],
        "new_questions": [
            {
                "question": "Does the target capture this mechanism?",
                "why_it_matters": "Market plausibility does not establish target execution.",
                "source_entry_ids": [],
                "source_judgement_indexes": [0],
            }
        ],
        "validation_binding": None,
    }


def test_case_direction_return_schema_is_valid_and_separates_validation_binding() -> (
    None
):
    schema = json.loads(RETURN_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    validator = jsonschema.Draft202012Validator(schema)
    invalid = {
        "schema_version": "1.0",
        "return_id": "return-1",
        "return_type": "validation_feedback",
        "branch": {
            "workflow": "clara:advisory-deliverable-validator",
            "question_id": "",
            "question": "Is the deliverable ready?",
            "answer": "It is not ready.",
        },
        "answer_effect": "weakens",
        "result_claim_ids": ["cl-1"],
        "source_artifacts": [],
        "limitations": [],
        "evidence_receipts": [],
        "claims": [],
        "judgement_entries": [],
        "question_updates": [],
        "new_questions": [],
        "validation_binding": None,
    }

    assert list(validator.iter_errors(invalid))


def test_analysis_branch_return_updates_the_spine_atomically_and_replays(
    core: Any, tmp_path: Path
) -> None:
    case_dir, question = _case(core, tmp_path)
    declared_return = _analysis_return(case_dir, question)

    result = core.record_case_direction_return(case_dir, declared_return)
    replay = core.record_case_direction_return(case_dir, declared_return)

    claims = json.loads((case_dir / "advisory_claim_register.json").read_text())
    evidence = json.loads((case_dir / "advisory_evidence_register.json").read_text())
    questions = json.loads((case_dir / "open_questions.json").read_text())
    assert result["replayed"] is False
    assert replay["replayed"] is True
    assert [item["id"] for item in claims["claims"]] == ["cl-market-001"]
    assert [item["id"] for item in evidence["evidence"]] == ["ev-research-001"]
    assert questions["questions"][0]["status"] == "answered"
    assert (
        questions["questions"][1]["question"]
        == "Does the target capture this mechanism?"
    )
    assert questions["questions"][1]["source_entry_ids"] == ["jud-0001"]
    assert result["result_claim_closure"] == ["cl-market-001"]
    assert result["result_evidence_closure"] == ["ev-research-001"]
    assert Path(result["receipt_path"]).is_file()


def test_invalid_result_claim_rolls_back_the_whole_return(
    core: Any, tmp_path: Path
) -> None:
    case_dir, question = _case(core, tmp_path)
    declared_return = _analysis_return(case_dir, question)
    declared_return["result_claim_ids"] = ["cl-missing"]

    with pytest.raises(core.CaseWorkspaceError, match="unknown result_claim_ids"):
        core.record_case_direction_return(case_dir, declared_return)

    claims = json.loads((case_dir / "advisory_claim_register.json").read_text())
    evidence = json.loads((case_dir / "advisory_evidence_register.json").read_text())
    questions = json.loads((case_dir / "open_questions.json").read_text())
    assert claims["claims"] == []
    assert evidence["evidence"] == []
    assert questions["questions"][0]["status"] == "open"
    assert not (
        case_dir / "case_direction_returns" / "return-research-001.json"
    ).exists()


def test_recheck_receipt_is_included_from_the_original_claim_link(
    core: Any, tmp_path: Path
) -> None:
    case_dir, question = _case(core, tmp_path)
    core.record_case_direction_return(case_dir, _analysis_return(case_dir, question))
    research = case_dir / "source_materials" / "research.md"
    artifact = _artifact(research, case_dir=case_dir, role="branch_output")
    recheck_time = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)
    recheck = _evidence(
        artifact,
        evidence_id="ev-research-recheck-001",
        recorded_at=recheck_time.isoformat(),
    )
    recheck["verification"] = {
        "status": "rechecked_unchanged",
        "checked_at": recheck_time.isoformat(),
        "method": "The exact source was reviewed again.",
        "notes": [],
    }
    recheck["rechecks_evidence_id"] = "ev-research-001"
    declared_return = {
        "schema_version": "1.0",
        "return_id": "return-recheck-001",
        "return_type": "analysis_branch",
        "branch": {
            "workflow": "clara:advisory-case-director",
            "question_id": "",
            "question": "Does the source still support the current claim?",
            "answer": "The source is unchanged and the claim remains active.",
        },
        "answer_effect": "unchanged",
        "result_claim_ids": ["cl-market-001"],
        "source_artifacts": [artifact],
        "limitations": ["The recheck does not add target evidence."],
        "evidence_receipts": [recheck],
        "claims": [],
        "judgement_entries": [],
        "question_updates": [],
        "new_questions": [],
        "validation_binding": None,
    }

    result = core.record_case_direction_return(
        case_dir, declared_return, now=recheck_time
    )

    assert set(result["result_evidence_closure"]) == {
        "ev-research-001",
        "ev-research-recheck-001",
    }


def test_validation_feedback_binds_exact_review_and_pre_feedback_lineage(
    core: Any, tmp_path: Path
) -> None:
    case_dir, question = _case(core, tmp_path)
    core.record_case_direction_return(case_dir, _analysis_return(case_dir, question))
    validation_dir = case_dir / "validation"
    validation_dir.mkdir()
    deliverable_sha256 = "a" * 64
    review = {
        "deliverable_sha256": deliverable_sha256,
        "lineage_review": {"reviewed_claim_ids": ["cl-market-001"]},
        "findings": [{"id": "finding-support-gap"}],
    }
    review_path = validation_dir / "advisory_validation_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    audit = {
        "record_complete": True,
        "effective_delivery_readiness": "not_ready",
        "deliverable": {"sha256": deliverable_sha256},
        "lineage": {
            "provenance_mode": "generation_time",
            "evidence_register": {
                "sha256": _sha256(case_dir / "advisory_evidence_register.json")
            },
            "claim_register": {
                "sha256": _sha256(case_dir / "advisory_claim_register.json")
            },
            "reviewed_claim_ids": ["cl-market-001"],
        },
    }
    audit_path = validation_dir / "validation_audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    declared_return = {
        "schema_version": "1.0",
        "return_id": "return-validation-001",
        "return_type": "validation_feedback",
        "branch": {
            "workflow": "clara:advisory-deliverable-validator",
            "question_id": "",
            "question": "Is the current deliverable adequately supported?",
            "answer": "No; the target-specific link remains unsupported.",
        },
        "answer_effect": "weakens",
        "result_claim_ids": ["cl-market-001"],
        "source_artifacts": [],
        "limitations": ["The finding does not itself establish target performance."],
        "evidence_receipts": [],
        "claims": [],
        "judgement_entries": [],
        "question_updates": [],
        "new_questions": [
            {
                "question": "What target evidence can establish capture of the mechanism?",
                "why_it_matters": "The validation found the target link unsupported.",
                "source_entry_ids": [],
                "source_judgement_indexes": [],
            }
        ],
        "validation_binding": {
            "review_artifact": _artifact(review_path, case_dir=case_dir),
            "audit_artifact": _artifact(audit_path, case_dir=case_dir),
            "finding_ids": ["finding-support-gap"],
        },
    }

    result = core.record_case_direction_return(case_dir, declared_return)

    assert result["validation_binding"]["record_complete"] is True
    assert result["validation_binding"]["finding_ids"] == ["finding-support-gap"]
    questions = json.loads((case_dir / "open_questions.json").read_text())
    assert questions["questions"][-1]["question"].startswith("What target evidence")


def test_validation_feedback_rejects_a_stale_claim_register(
    core: Any, tmp_path: Path
) -> None:
    case_dir, question = _case(core, tmp_path)
    core.record_case_direction_return(case_dir, _analysis_return(case_dir, question))
    validation_dir = case_dir / "validation"
    validation_dir.mkdir()
    review_path = validation_dir / "advisory_validation_review.json"
    review_path.write_text(
        json.dumps(
            {
                "deliverable_sha256": "b" * 64,
                "lineage_review": {"reviewed_claim_ids": ["cl-market-001"]},
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    stale_claim_sha256 = _sha256(case_dir / "advisory_claim_register.json")
    evidence_sha256 = _sha256(case_dir / "advisory_evidence_register.json")
    audit_path = validation_dir / "validation_audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "record_complete": True,
                "effective_delivery_readiness": "ready",
                "deliverable": {"sha256": "b" * 64},
                "lineage": {
                    "provenance_mode": "generation_time",
                    "evidence_register": {"sha256": evidence_sha256},
                    "claim_register": {"sha256": stale_claim_sha256},
                    "reviewed_claim_ids": ["cl-market-001"],
                },
            }
        ),
        encoding="utf-8",
    )
    later_time = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    later_claim = _claim(
        claim_id="cl-later-001",
        evidence_id="ev-research-001",
        recorded_at=later_time.isoformat(),
    )
    later_claim["statement"] = "A later independent claim changed the register."
    later_claim["evidence_links"] = []
    later_claim["dependency"] = {
        "mode": "all_of",
        "claim_ids": ["cl-market-001"],
        "derivation_type": "reasoning",
        "explanation": "The later claim depends on the existing market claim.",
        "calculation_evidence_id": "",
    }
    core.record_analysis_contribution(
        case_dir,
        evidence_receipts=[],
        claims=[later_claim],
        now=later_time,
    )
    declared_return = {
        "schema_version": "1.0",
        "return_id": "return-validation-stale",
        "return_type": "validation_feedback",
        "branch": {
            "workflow": "clara:advisory-deliverable-validator",
            "question_id": "",
            "question": "Is the deliverable ready?",
            "answer": "The packaged review said it was ready.",
        },
        "answer_effect": "unchanged",
        "result_claim_ids": ["cl-market-001"],
        "source_artifacts": [],
        "limitations": [],
        "evidence_receipts": [],
        "claims": [],
        "judgement_entries": [],
        "question_updates": [],
        "new_questions": [],
        "validation_binding": {
            "review_artifact": _artifact(review_path, case_dir=case_dir),
            "audit_artifact": _artifact(audit_path, case_dir=case_dir),
            "finding_ids": [],
        },
    }

    with pytest.raises(core.CaseWorkspaceError, match="claim register changed"):
        core.record_case_direction_return(case_dir, declared_return)


def test_skills_require_branch_and_validator_returns_to_reenter_the_spine() -> None:
    director = (
        CLARA_ROOT / "skills" / "advisory-case-director" / "SKILL.md"
    ).read_text(encoding="utf-8")
    validator = (
        CLARA_ROOT / "skills" / "advisory-deliverable-validator" / "SKILL.md"
    ).read_text(encoding="utf-8")
    operating_model = (
        CLARA_ROOT
        / "skills"
        / "advisory-case-director"
        / "references"
        / "operating-model.md"
    ).read_text(encoding="utf-8")

    assert "record_case_direction_return.py" in director
    assert "common case-direction contract" in " ".join(director.split())
    assert "validation_feedback" in validator
    assert "return the packaged semantic review to the case director" in " ".join(
        validator.split()
    )
    assert "The validator is also a bounded branch" in operating_model
    assert "rejects feedback if the evidence or claim register changed" in " ".join(
        operating_model.split()
    )
