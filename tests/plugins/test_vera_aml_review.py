from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/aml-review/scripts/aml_review.py"
spec = importlib.util.spec_from_file_location("aml_review_test", SCRIPT)
assert spec and spec.loader
aml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aml)


def review_for(path: Path, input_root: Path) -> dict:
    return {
        "schema_version": 1,
        "jurisdiction": "IT",
        "as_of": "2026-09-05",
        "scope": "Review the documented shareholder loan.",
        "sources": [
            {
                "id": "S1",
                "path": path.relative_to(input_root).as_posix(),
                "title": "Loan evidence",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
        "legal_basis": [
            {
                "title": "CNDCEC guidance",
                "url": "https://commercialisti.it/norme-per-la-professione/norme-tecniche/antiriciclaggio/",
                "locator": "Due diligence",
                "checked_at": "2026-09-05",
                "applicability": "Italian accounting engagement; illustrative test basis.",
            }
        ],
        "findings": [
            {
                "id": "F1",
                "observation": "Payer differs from contractual lender.",
                "interpretation": "Relationship requires clarification, not proof of suspicion.",
                "alternatives": "A documented payment mandate may explain it.",
                "follow_up": "Obtain the mandate and reconcile parties.",
                "citations": [{"source_id": "S1", "locator": "line 1"}],
            }
        ],
        "assessment": "The supplied evidence does not yet explain the payment route.",
        "assessment_citations": [{"source_id": "S1", "locator": "line 1"}],
        "limitations": "No independent screening performed.",
    }


def case(tmp_path: Path) -> dict:
    source = tmp_path / "loan.txt"
    source.write_text("Lender A; payer B; EUR 200000.")
    return review_for(source, tmp_path)


def build(review: dict, tmp_path: Path) -> dict:
    return aml.build_record(
        review, input_root=tmp_path, client_id="client-a", engagement_id="eng-a"
    )


def decision(proposal_hash: str) -> dict:
    return {
        "proposal_sha256": proposal_hash,
        "reviewer_ref": "professional-a",
        "reviewed_at": "2026-09-05",
        "conclusion": "Request supporting mandate; issue remains open.",
        "finding_dispositions": {"F1": "Unresolved pending evidence"},
        "next_review_date": None,
        "review_date_reason": "Await requested evidence",
    }


def test_draft_retains_uncertainty_without_automatic_approval(tmp_path: Path) -> None:
    record = build(case(tmp_path), tmp_path)
    assert record["status"] == "draft_for_review"
    assert record["calculation"] is None
    assert "not proof of suspicion" in aml.render_memo(record)


def test_empty_findings_does_not_claim_compliance(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["findings"] = []
    record = build(review, tmp_path)
    assert record["status"] == "draft_for_review"
    assert "not evidence truth" in record["assurance_limit"]


@pytest.mark.parametrize(
    "mutation",
    ["unknown_citation", "changed_source", "escape", "duplicate", "no_locator"],
)
def test_invalid_evidence_is_rejected(tmp_path: Path, mutation: str) -> None:
    review = case(tmp_path)
    if mutation == "unknown_citation":
        review["findings"][0]["citations"][0]["source_id"] = "missing"
    elif mutation == "changed_source":
        (tmp_path / "loan.txt").write_text("Altered evidence")
    elif mutation == "escape":
        review["sources"][0]["path"] = "../loan.txt"
    elif mutation == "duplicate":
        review["sources"].append(copy.deepcopy(review["sources"][0]))
    else:
        review["findings"][0]["citations"][0]["locator"] = ""
    with pytest.raises(ValueError):
        build(review, tmp_path)


def test_decision_records_open_issue_without_clearing_it(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["professional_decision"] = decision(
        build(review, tmp_path)["proposal_sha256"]
    )
    record = build(review, tmp_path)
    assert record["status"] == "professional_decision_recorded"
    assert record["review"]["findings"][0]["id"] == "F1"
    assert "Unresolved pending evidence" in aml.render_memo(record)


def test_stale_decision_cannot_approve_changed_proposal(tmp_path: Path) -> None:
    review = case(tmp_path)
    review["professional_decision"] = decision(
        build(review, tmp_path)["proposal_sha256"]
    )
    review["assessment"] = "Changed assessment"
    with pytest.raises(ValueError, match="exact proposal"):
        build(review, tmp_path)


@pytest.mark.parametrize("client_id", ["client-a", "client-b"])
def test_previous_record_requires_same_client(tmp_path: Path, client_id: str) -> None:
    review = case(tmp_path)
    previous = build(review, tmp_path)
    path = aml.save_record(previous, tmp_path)
    review["sources"].append(
        {
            "id": "S2",
            "path": path.name,
            "title": "Previous review",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
    review["previous"] = {"source_id": "S2", "record_sha256": previous["record_sha256"]}
    review["changes_since_previous"] = (
        "No new explanation received; original issue remains open."
    )
    if client_id == "client-b":
        with pytest.raises(ValueError, match="another client"):
            aml.build_record(
                review, input_root=tmp_path, client_id=client_id, engagement_id="eng-a"
            )
    else:
        result = aml.build_record(
            review, input_root=tmp_path, client_id=client_id, engagement_id="eng-a"
        )
        assert result["previous_record_sha256"] == previous["record_sha256"]


def test_save_preserves_previous_versions_and_idempotent_retry(tmp_path: Path) -> None:
    review = case(tmp_path)
    first = build(review, tmp_path)
    path = aml.save_record(first, tmp_path)
    before = path.read_bytes()
    review["assessment"] = "Additional evidence requested."
    second = aml.save_record(build(review, tmp_path), tmp_path)
    retried = aml.save_record(first, tmp_path)
    assert second != path
    assert retried == path
    assert path.read_bytes() == before


def test_cli_runs_with_actual_archive_receipts(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace(
        "aml-review", input_files={"loan.txt": "Lender A; payer B; EUR 200000."}
    )
    source = workspace["input_paths"][0]
    review = review_for(source, Path(workspace["context"]["run_root"]) / "inputs")
    review_path = workspace["output_dir"] / "review_input.json"
    review_path.write_text(json.dumps(review))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(review_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    records = list(workspace["output_dir"].glob("aml-review-*.json"))
    assert len(records) == 1
    assert (
        json.loads(records[0].read_text())["client_id"]
        == workspace["context"]["client_id"]
    )


def test_cli_rejects_wrong_workflow_before_writing(vera_workflow_workspace) -> None:
    workspace = vera_workflow_workspace("new-client")
    review_path = workspace["output_dir"] / "review_input.json"
    review_path.write_text("{}")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(review_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert not list(workspace["output_dir"].glob("aml-review-*"))


def test_main_executes_bound_run_in_process(
    vera_workflow_workspace, monkeypatch
) -> None:
    workspace = vera_workflow_workspace("aml-review")
    review = review_for(
        workspace["input_paths"][0], Path(workspace["context"]["run_root"]) / "inputs"
    )
    path = workspace["output_dir"] / "review_input.json"
    path.write_text(json.dumps(review))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(path),
        ],
    )
    assert aml.main() == 0
    assert len(list(workspace["output_dir"].glob("aml-review-*.md"))) == 1


def test_existing_calculator_preserves_unresolved_onboarding_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    source_root = ROOT / "plugins/new-client/scripts"
    monkeypatch.syspath_prepend(str(source_root))
    initializer_spec = importlib.util.spec_from_file_location(
        "aml_initializer_test", source_root / "initialize_case.py"
    )
    assert initializer_spec and initializer_spec.loader
    initializer = importlib.util.module_from_spec(initializer_spec)
    initializer_spec.loader.exec_module(initializer)
    intake = initializer.build_template(
        "CLIENT-A",
        client_type="company",
        engagement_kind="ongoing",
        assessment_date="2026-09-05",
    )
    path = tmp_path / "new_client_input.json"
    path.write_text(json.dumps(intake))
    review = case(tmp_path)
    review["sources"].append(
        {
            "id": "S2",
            "path": path.name,
            "title": "Reviewed input",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
    review["calculation_source_id"] = "S2"
    record = build(review, tmp_path)
    assert record["calculation"]["professional_review_required"] is True
    assert record["calculation"]["status"] == "blocked_unresolved_table_1"
    assert record["status"] == "draft_for_review"


def test_no_dependency_installation_required() -> None:
    dep_spec = importlib.util.spec_from_file_location(
        "aml_dependencies_test", SCRIPT.parent / "check_dependencies.py"
    )
    assert dep_spec and dep_spec.loader
    dependencies = importlib.util.module_from_spec(dep_spec)
    dep_spec.loader.exec_module(dependencies)
    assert dependencies.main([]) == 0


def test_decision_requires_disposition_of_all_findings(tmp_path: Path) -> None:
    review = case(tmp_path)
    reviewed = decision(build(review, tmp_path)["proposal_sha256"])
    reviewed["finding_dispositions"] = {}
    review["professional_decision"] = reviewed
    with pytest.raises(ValueError, match="every finding"):
        build(review, tmp_path)


def test_save_rejects_tampered_record_before_write(tmp_path: Path) -> None:
    record = build(case(tmp_path), tmp_path)
    record["review"]["assessment"] = "Tampered"
    with pytest.raises(ValueError, match="changed after validation"):
        aml.save_record(record, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_successor_uses_finalized_same_engagement_record(
    vera_workflow_workspace, monkeypatch
) -> None:
    first = vera_workflow_workspace("aml-review", engagement_id="aml-case")
    input_root = Path(first["context"]["run_root"]) / "inputs"
    review = review_for(first["input_paths"][0], input_root)
    record = aml.build_record(
        review,
        input_root=input_root,
        client_id=first["context"]["client_id"],
        engagement_id=first["context"]["engagement_id"],
    )
    saved = aml.save_record(record, first["output_dir"])
    successor = vera_workflow_workspace(
        "aml-review", engagement_id="aml-case", upstream_workspace=first
    )
    source = next(path for path in successor["input_paths"] if path.name == saved.name)
    updated = review_for(source, Path(successor["context"]["run_root"]) / "inputs")
    updated["previous"] = {"source_id": "S1", "record_sha256": record["record_sha256"]}
    updated["changes_since_previous"] = (
        "Revisit the open issue; no new underlying evidence was supplied."
    )
    path = successor["output_dir"] / "review_input.json"
    path.write_text(json.dumps(updated))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--client-engagement",
            str(successor["context_path"]),
            "--review",
            str(path),
        ],
    )
    assert aml.main() == 0
    result_path = next(successor["output_dir"].glob("aml-review-*.json"))
    result = json.loads(result_path.read_text())
    assert result["previous_record_sha256"] == record["record_sha256"]
    assert saved.is_file()


def test_packaged_cli_runs_with_archive_receipts(
    vera_workflow_workspace, tmp_path: Path
) -> None:
    archive_path = ROOT / "plugin_packages/vera/vera-plugin.zip"
    extracted = tmp_path / "packaged-vera"
    with ZipFile(archive_path) as archive:
        archive.extractall(extracted)
    script = (
        extracted
        / "vera-codex-plugin/plugins/vera/modules/aml-review/scripts/aml_review.py"
    )
    workspace = vera_workflow_workspace("aml-review")
    review = review_for(
        workspace["input_paths"][0], Path(workspace["context"]["run_root"]) / "inputs"
    )
    path = workspace["output_dir"] / "review_input.json"
    path.write_text(json.dumps(review))
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(path),
        ],
        cwd=script.parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    saved = next(workspace["output_dir"].glob("aml-review-*.json"))
    assert json.loads(saved.read_text())["workflow_id"] == "aml-review"
