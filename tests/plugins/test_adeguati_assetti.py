from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/adeguati-assetti/scripts/assetti_review.py"
spec = importlib.util.spec_from_file_location("assetti_review_test", SCRIPT)
assert spec and spec.loader
assetti = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assetti)


def source_row(path: Path, root: Path, source_id: str = "S1") -> dict:
    return {
        "id": source_id,
        "path": path.relative_to(root).as_posix(),
        "title": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def review_for(path: Path, root: Path) -> dict:
    citation = {
        "source_id": "S1",
        "locator": "Reporting policy and inventory, lines 1–2",
    }
    return {
        "schema_version": 1,
        "jurisdiction": "IT",
        "as_of": "2026-09-07",
        "scope": "Reporting arrangements; payment controls not assessed.",
        "company_context": "Small owner-managed service company, one site.",
        "proportionality_basis": "A concise reporting process may be sufficient; assess actual use.",
        "sources": [source_row(path, root)],
        "legal_basis": [
            {
                "title": "Illustrative professional basis for synthetic tests",
                "url": "https://commercialisti.it/",
                "locator": "Methodology",
                "checked_at": "2026-09-07",
                "applicability": "Synthetic case; no legal conclusion.",
            }
        ],
        "observations": [
            {
                "id": "O1",
                "area": "Management reporting",
                "description": "Policy requires monthly reports; inventory contains only two quarterly reports.",
                "proportionality": "Assess whether report frequency supports this company’s decisions.",
                "assessment": "Actual monthly operation is unknown; absence from this inventory is not proof of absence.",
                "evidence_state": "unknown",
                "citations": [citation],
            }
        ],
        "findings": [
            {
                "id": "F1",
                "observation_ids": ["O1"],
                "observation": "Evidence of monthly use has not been supplied.",
                "interpretation": "The review cannot establish timely information for decisions.",
                "alternatives": "Reports may exist elsewhere or informal controls may serve the need.",
                "follow_up": "Request examples of report delivery and resulting decisions.",
                "citations": [citation],
            }
        ],
        "actions": [
            {
                "id": "A1",
                "finding_ids": ["F1"],
                "proposal": "Inspect reporting and decision examples.",
                "owner": "Proposed: administrator; confirmation pending.",
                "timing": "To agree with the professional.",
                "priority_reason": "Resolve whether management receives timely information.",
                "completion_evidence_needed": "Dated reports and evidence of review and response.",
                "status": "proposed",
            }
        ],
        "assessment": "Operating effectiveness remains unverified within the supplied scope.",
        "assessment_citations": [citation],
        "limitations": "No interviews or direct observations; no certification.",
    }


def case(tmp_path: Path) -> dict:
    source = tmp_path / "reporting.txt"
    source.write_text("Monthly reporting policy.\nInventory: two quarterly reports.\n")
    return review_for(source, tmp_path)


def build(review: dict, root: Path) -> dict:
    return assetti.build_record(
        review, input_root=root, client_id="client-a", engagement_id="eng-a"
    )


def decision(review: dict) -> dict:
    return {
        "proposal_sha256": assetti.digest(review),
        "reviewer_ref": "professional-a",
        "reviewed_at": "2026-09-07",
        "conclusion": "Request operating evidence; assessment remains limited.",
        "finding_dispositions": {
            "F1": "Open; proposed action A1 accepted for investigation."
        },
        "next_review_date": None,
        "review_date_reason": "Await evidence; no monitoring scheduled.",
    }


def prior_case(tmp_path: Path) -> tuple[dict, dict]:
    review = case(tmp_path)
    record = build(review, tmp_path)
    prior_path = tmp_path / "previous.json"
    prior_path.write_text(json.dumps(record))
    current = copy.deepcopy(review)
    current["sources"].append(source_row(prior_path, tmp_path, "PREVIOUS"))
    current["previous"] = {
        "source_id": "PREVIOUS",
        "record_sha256": record["record_sha256"],
    }
    current["changes_since_previous"] = "No new operating evidence supplied."
    current["prior_action_review"] = {
        "A1": {
            "status": "not_assessed",
            "assessment": "Still awaiting reports and decision evidence.",
            "citations": [],
            "current_action_ids": [],
        }
    }
    return current, record


def test_unknown_evidence_and_proposed_actions_remain_visible(tmp_path: Path) -> None:
    review = case(tmp_path)
    record = build(review, tmp_path)
    memo = assetti.render_memo(record)
    assert record["status"] == "draft_for_review"
    assert record["review"] == review
    assert "absence from this inventory is not proof of absence" in memo
    assert "confirmation pending" in memo
    assert "payment controls not assessed" in memo
    assert "operating effectiveness" in record["assurance_limit"]
    assert "calculation" not in record


@pytest.mark.parametrize(
    "state", ["documented", "reported", "operating_evidence", "unknown"]
)
def test_provenance_state_does_not_assign_adequacy(tmp_path: Path, state: str) -> None:
    review = case(tmp_path)
    review["observations"][0]["evidence_state"] = state
    record = build(review, tmp_path)
    assert record["review"]["assessment"] == review["assessment"]
    assert record["status"] == "draft_for_review"


def test_no_findings_remains_draft_without_certification(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["findings"] = []
    review["actions"] = []
    record = build(review, tmp_path)
    assert record["status"] == "draft_for_review"
    assert "No certification is issued" in assetti.render_memo(record)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("schema_version", True, "Expected version"),
        ("jurisdiction", "FR", "Expected version"),
        ("as_of", "20260907", "YYYY-MM-DD"),
        ("scope", "", "scope"),
        ("sources", [], "At least one source"),
        ("legal_basis", [], "professional basis"),
        ("observations", [], "scoped observation"),
        ("actions", {}, "array of objects"),
        ("findings", ["bad"], "array of objects"),
    ],
)
def test_invalid_review_contract_rejected(
    tmp_path: Path, field: str, value, error: str
) -> None:
    review = case(tmp_path)
    review[field] = value
    with pytest.raises(ValueError, match=error):
        build(review, tmp_path)


@pytest.mark.parametrize(
    "collection", ["sources", "observations", "findings", "actions"]
)
def test_duplicate_ids_rejected(tmp_path: Path, collection: str) -> None:
    review = case(tmp_path)
    review[collection].append(copy.deepcopy(review[collection][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        build(review, tmp_path)


@pytest.mark.parametrize(
    "citation",
    [
        [],
        ["bad"],
        [{"source_id": "missing", "locator": "p1"}],
        [{"source_id": "S1", "locator": ""}],
    ],
)
def test_missing_or_unbound_citations_rejected(tmp_path: Path, citation) -> None:
    review = case(tmp_path)
    review["observations"][0]["citations"] = citation
    with pytest.raises(ValueError):
        build(review, tmp_path)


@pytest.mark.parametrize("refs", ["O1", [], ["missing"], ["O1", "O1"], [1]])
def test_invalid_finding_links_rejected(tmp_path: Path, refs) -> None:
    review = case(tmp_path)
    review["findings"][0]["observation_ids"] = refs
    with pytest.raises(ValueError, match="Finding observations"):
        build(review, tmp_path)


def test_source_modified_after_import_rejected(tmp_path: Path) -> None:
    review = case(tmp_path)
    (tmp_path / "reporting.txt").write_text("Changed evidence")
    with pytest.raises(ValueError, match="Source digest mismatch"):
        build(review, tmp_path)


@pytest.mark.parametrize("path", ["../outside.txt", "/tmp/outside.txt"])
def test_source_traversal_rejected(tmp_path: Path, path: str) -> None:
    review = case(tmp_path)
    review["sources"][0]["path"] = path
    with pytest.raises(ValueError, match="relative"):
        build(review, tmp_path)


def test_source_symlink_escape_rejected(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    review = case(inputs)
    outside = tmp_path / "outside.txt"
    outside.write_text("Outside evidence")
    link = inputs / "linked.txt"
    link.symlink_to(outside)
    review["sources"][0]["path"] = link.name
    with pytest.raises(ValueError, match="escapes"):
        build(review, inputs)


def test_completed_action_without_evidence_rejected(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["actions"][0].update(
        status="completed",
        completion_citations=[],
        completion_assessment="Claimed complete",
    )
    with pytest.raises(ValueError, match="citations"):
        build(review, tmp_path)


def test_completed_action_preserves_evidence_and_limited_assessment(
    tmp_path: Path,
) -> None:
    review = case(tmp_path)
    review["actions"][0].update(
        status="completed",
        completion_citations=review["assessment_citations"],
        completion_assessment="Inspection completed; operation remains unverified.",
    )
    record = build(review, tmp_path)
    assert "Inspection completed; operation remains unverified." in assetti.render_memo(
        record
    )
    assert record["status"] == "draft_for_review"


def test_exact_professional_decision_preserves_open_findings(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["professional_decision"] = decision(review)
    record = build(review, tmp_path)
    assert record["status"] == "professional_decision_recorded"
    assert record["review"]["findings"][0]["id"] == "F1"
    assert record["review"]["actions"][0]["status"] == "proposed"
    assert "Open; proposed action A1 accepted" in assetti.render_memo(record)


def test_decision_cannot_be_reused_after_proposal_changes(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["professional_decision"] = decision(review)
    review["actions"][0]["proposal"] = "A different action"
    with pytest.raises(ValueError, match="exact proposal"):
        build(review, tmp_path)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("finding_dispositions", {}, "every finding"),
        ("reviewer_ref", "", "reviewer_ref"),
        ("reviewed_at", "2026-09-06", "precedes the assessment"),
        ("next_review_date", "2026-09-06", "Next review precedes"),
    ],
)
def test_invalid_professional_decision_rejected(
    tmp_path: Path, field: str, value, error: str
) -> None:
    review = case(tmp_path)
    review["professional_decision"] = decision(review)
    review["professional_decision"][field] = value
    with pytest.raises(ValueError, match=error):
        build(review, tmp_path)


def test_follow_up_binds_previous_record_and_preserves_unresolved_action(
    tmp_path: Path,
) -> None:
    review, previous = prior_case(tmp_path)
    record = build(review, tmp_path)
    assert record["previous_record_sha256"] == previous["record_sha256"]
    assert "Still awaiting reports" in assetti.render_memo(record)
    assert record["review"]["actions"][0]["status"] == "proposed"


def test_follow_up_cannot_silently_drop_prior_actions(tmp_path: Path) -> None:
    review, _ = prior_case(tmp_path)
    review["prior_action_review"] = {}
    with pytest.raises(ValueError, match="every prior action"):
        build(review, tmp_path)


@pytest.mark.parametrize("identity", ["client_id", "engagement_id"])
def test_previous_review_from_another_case_rejected(
    tmp_path: Path, identity: str
) -> None:
    review, previous = prior_case(tmp_path)
    previous[identity] = "another"
    previous["record_sha256"] = assetti.digest(
        {k: v for k, v in previous.items() if k != "record_sha256"}
    )
    path = tmp_path / "previous.json"
    path.write_text(json.dumps(previous))
    review["sources"][1] = source_row(path, tmp_path, "PREVIOUS")
    review["previous"]["record_sha256"] = previous["record_sha256"]
    with pytest.raises(ValueError, match="another client or engagement"):
        build(review, tmp_path)


def test_changed_previous_record_rejected_even_with_new_source_hash(
    tmp_path: Path,
) -> None:
    review, previous = prior_case(tmp_path)
    previous["review"]["assessment"] = "Changed historical assessment"
    path = tmp_path / "previous.json"
    path.write_text(json.dumps(previous))
    review["sources"][1] = source_row(path, tmp_path, "PREVIOUS")
    with pytest.raises(ValueError, match="Previous record digest mismatch"):
        build(review, tmp_path)


def test_save_retry_is_idempotent_and_preserves_old_versions(tmp_path: Path) -> None:
    review = case(tmp_path)
    first = build(review, tmp_path)
    output = tmp_path / "out"
    path = assetti.save_record(first, output)
    before = path.read_bytes()
    review["assessment"] = "Revised assessment; further evidence is needed."
    second = assetti.save_record(build(review, tmp_path), output)
    retried = assetti.save_record(first, output)
    assert retried == path
    assert second != path
    assert path.read_bytes() == before


def test_mutated_record_cannot_be_saved(tmp_path: Path) -> None:
    record = build(case(tmp_path), tmp_path)
    record["review"]["assessment"] = "Tampered"
    with pytest.raises(ValueError, match="changed after validation"):
        assetti.save_record(record, tmp_path / "out")


@pytest.mark.parametrize("suffix", [".json", ".md"])
def test_existing_output_tampering_rejected(tmp_path: Path, suffix: str) -> None:
    record = build(case(tmp_path), tmp_path)
    output = tmp_path / "out"
    path = assetti.save_record(record, output)
    path.with_suffix(suffix).write_text("Changed")
    with pytest.raises(ValueError, match="Existing output differs"):
        assetti.save_record(record, output)


def test_output_symlink_rejected_without_writing(tmp_path: Path) -> None:
    record = build(case(tmp_path), tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    link = tmp_path / "out"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        assetti.save_record(record, link)
    assert list(destination.iterdir()) == []


def run_cli(workspace: dict, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    source = workspace["input_paths"][0]
    root = Path(workspace["context"]["run_root"]) / "inputs"
    review = review_for(source, root)
    path = workspace["output_dir"] / "review_input.json"
    path.write_text(json.dumps(review))
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_writes_review_with_real_archive_receipts(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace(
        "adeguati-assetti",
        input_files={"reporting.txt": "Reporting policy and inventory"},
    )
    result = run_cli(workspace)
    assert result.returncode == 0, result.stderr
    records = list(workspace["output_dir"].glob("adeguati-assetti-*.json"))
    assert len(records) == 1
    assert (
        json.loads(records[0].read_text())["client_id"]
        == workspace["context"]["client_id"]
    )
    assert records[0].with_suffix(".md").is_file()


def test_cli_rejects_wrong_archive_workflow(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace(
        "aml-review", input_files={"reporting.txt": "Wrong workflow"}
    )
    result = run_cli(workspace)
    assert result.returncode != 0
    assert not list(workspace["output_dir"].glob("adeguati-assetti-*"))


def test_cli_rejects_changed_imported_source(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace(
        "adeguati-assetti", input_files={"reporting.txt": "Original"}
    )
    workspace["input_paths"][0].write_text("Changed after receipt")
    result = run_cli(workspace)
    assert result.returncode != 0
    assert not list(workspace["output_dir"].glob("adeguati-assetti-*"))


@pytest.mark.parametrize(
    "disposition",
    [
        "Complete without evidence",
        {"status": "completed", "assessment": "Claimed complete", "citations": []},
        {
            "status": "superseded",
            "assessment": "Replaced",
            "current_action_ids": ["missing"],
        },
    ],
)
def test_prior_action_cannot_close_or_disappear_without_bound_evidence(
    tmp_path: Path, disposition
) -> None:
    review, _ = prior_case(tmp_path)
    review["prior_action_review"]["A1"] = disposition
    with pytest.raises(ValueError):
        build(review, tmp_path)


def test_prior_action_closure_renders_its_evidence(tmp_path: Path) -> None:
    review, _ = prior_case(tmp_path)
    review["prior_action_review"]["A1"] = {
        "status": "completed",
        "assessment": "Inspection completed; broader operation is still unknown.",
        "citations": [
            {"source_id": "S1", "locator": "Dated inspection note, paragraph 4"}
        ],
        "current_action_ids": [],
    }
    record = build(review, tmp_path)
    assert "Dated inspection note, paragraph 4" in assetti.render_memo(record)
    assert "broader operation is still unknown" in assetti.render_memo(record)


def test_cli_follow_up_uses_finalized_same_engagement_artifact(
    vera_workflow_workspace,
) -> None:
    first = vera_workflow_workspace(
        "adeguati-assetti",
        engagement_id="assetti-case",
        input_files={"reporting.txt": "Reporting evidence"},
    )
    first_result = run_cli(first)
    assert first_result.returncode == 0, first_result.stderr
    second = vera_workflow_workspace(
        "adeguati-assetti", engagement_id="assetti-case", upstream_workspace=first
    )
    previous_path = next(
        path
        for path in second["input_paths"]
        if path.suffix == ".json"
        and json.loads(path.read_text()).get("workflow_id") == "adeguati-assetti"
    )
    previous = json.loads(previous_path.read_text())
    review = review_for(previous_path, Path(second["context"]["run_root"]) / "inputs")
    review["previous"] = {"source_id": "S1", "record_sha256": previous["record_sha256"]}
    review["changes_since_previous"] = (
        "Historical record imported; no new operating evidence supplied."
    )
    review["prior_action_review"] = {
        "A1": {
            "status": "not_assessed",
            "assessment": "Awaiting new evidence.",
            "citations": [],
            "current_action_ids": [],
        }
    }
    review_path = second["output_dir"] / "review_input.json"
    review_path.write_text(json.dumps(review))

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            str(second["context_path"]),
            "--review",
            str(review_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    saved = next(second["output_dir"].glob("adeguati-assetti-*.json"))
    assert (
        json.loads(saved.read_text())["previous_record_sha256"]
        == previous["record_sha256"]
    )
    assert "Awaiting new evidence" in saved.with_suffix(".md").read_text()


def intelligent_case(tmp_path: Path) -> dict:
    review = case(tmp_path)
    review["intelligent_review"] = {
        "version": 1,
        "coverage": [
            {
                "id": "C1",
                "area": "Reporting",
                "status": "assessed",
                "reason": "Limited to supplied reporting examples.",
                "observation_ids": ["O1"],
            },
            {
                "id": "C2",
                "area": "Payments",
                "status": "excluded",
                "reason": "Outside agreed scope; no company-wide conclusion.",
                "observation_ids": [],
            },
        ],
        "processes": [
            {
                "id": "P1",
                "process": "Monthly reporting",
                "risk": "Late management response",
                "responsibility": "Administrator, as reported",
                "control": "Monthly review required by policy",
                "information_flow": "Delivery unverified",
                "operation": "Two quarterly reports; informal reviews may exist",
                "gap": "Monthly operation unknown",
                "observation_ids": ["O1"],
            }
        ],
        "questions": [
            {
                "id": "Q1",
                "question": "Show the latest review and response",
                "why_it_matters": "Could substantiate an informal control",
                "evidence_needed": "Dated report and decision",
                "status": "Unanswered",
                "observation_ids": ["O1"],
            }
        ],
        "chronology": [
            {
                "id": "T1",
                "event_date": "Unknown",
                "known_at": "Unknown; upload date is not availability to management",
                "recipient": "Unverified",
                "event": "Reporting policy supplied",
                "response": "No decision evidence",
                "uncertainty": "Cannot establish prior use",
                "observation_ids": ["O1"],
            }
        ],
        "decision_brief": "Discuss A1; do not infer that missing reports never existed.",
        "action_ids": ["A1"],
        "next_review": "Proposed after a reporting cycle; inspect review and exception handling.",
    }
    return review


def test_intelligent_analysis_survives_save_reopen_and_renders(tmp_path: Path) -> None:
    record = build(intelligent_case(tmp_path), tmp_path)
    output = tmp_path / "output"
    assetti.save_record(record, output)
    reopened = json.loads(next(output.glob("*.json")).read_text())
    memo = next(output.glob("*.md")).read_text()
    assert reopened == record
    assert "Could substantiate an informal control" in memo
    assert "upload date is not availability to management" in memo
    assert "Outside agreed scope; no company-wide conclusion" in memo
    assert "inspect review and exception handling" in memo
    assert reopened["status"] == "draft_for_review"


@pytest.mark.parametrize(
    "section", ["coverage", "processes", "questions", "chronology"]
)
def test_intelligent_sections_reject_unbound_observations(
    tmp_path: Path, section: str
) -> None:
    review = intelligent_case(tmp_path)
    review["intelligent_review"][section][0]["observation_ids"] = ["MISSING"]
    with pytest.raises(ValueError, match="unknown IDs"):
        build(review, tmp_path)


def test_intelligent_analysis_change_invalidates_professional_approval(
    tmp_path: Path,
) -> None:
    review = intelligent_case(tmp_path)
    review["professional_decision"] = decision(review)
    review["intelligent_review"]["processes"][0]["operation"] = "Revised interpretation"
    with pytest.raises(ValueError, match="exact proposal"):
        build(review, tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("coverage", []),
        ("questions", {}),
        ("action_ids", ["MISSING"]),
        ("decision_brief", ""),
    ],
)
def test_incomplete_intelligent_records_rejected(
    tmp_path: Path, field: str, value
) -> None:
    review = intelligent_case(tmp_path)
    review["intelligent_review"][field] = value
    with pytest.raises(ValueError):
        build(review, tmp_path)
