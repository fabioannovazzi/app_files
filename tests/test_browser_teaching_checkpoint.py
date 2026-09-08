from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/browser-automation/scripts"


@pytest.fixture
def checkpoint(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "teaching_checkpoint", SCRIPTS / "teaching_checkpoint.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload():
    return {
        "schema_version": "browser-teaching-checkpoint/v1",
        "objective": "Teach one purchase posting",
        "start_state": "Authorized console",
        "end_condition": "Posting explicitly confirmed",
        "status": "needs_clarification",
        "resume_instruction": "Explain the account choice before posting",
        "steps": [
            {
                "id": "choose-account",
                "intent": "Assign an account",
                "action": "Account dialog opened",
                "decision_reason": "Account choice remains unexplained",
                "outcome": "Account controls visible",
                "postcondition": "Account assignment still needs verification",
                "status": "unresolved",
                "evidence_basis": "observed",
                "uncertainties": ["Why choose this account?"],
                "capture": {
                    "started_at": "2026-09-07T09:00:00Z",
                    "ended_at": "2026-09-07T09:00:15Z",
                    "stop_reason": "time_limit",
                    "transition_count": 1,
                    "before_sha256": "a" * 64,
                    "after_sha256": "b" * 64,
                },
            }
        ],
    }


def test_new_task_resumes_exact_question_from_saved_revision(checkpoint, tmp_path):
    directory = tmp_path / "teaching"
    checkpoint.save_checkpoint(directory, payload(), expected_revision=0)

    resumed = checkpoint.read_checkpoint(directory)

    assert (
        resumed["payload"]["resume_instruction"]
        == "Explain the account choice before posting"
    )
    assert resumed["payload"]["steps"][0]["uncertainties"] == [
        "Why choose this account?"
    ]
    assert resumed["payload"]["status"] == "needs_clarification"


def test_resolved_step_can_be_appended_without_losing_prior_evidence(
    checkpoint, tmp_path
):
    directory = tmp_path / "teaching"
    original = checkpoint.save_checkpoint(directory, payload(), expected_revision=0)
    original_bytes = original.read_bytes()
    updated = payload()
    updated["steps"][0].update(
        status="understood",
        uncertainties=[],
        decision_reason="Operator explained the purchase category",
    )
    updated["status"] = "paused"
    updated["resume_instruction"] = "Verify the final posting result"

    checkpoint.save_checkpoint(directory, updated, expected_revision=1)

    assert original.read_bytes() == original_bytes
    assert checkpoint.read_checkpoint(directory)["revision"] == 2
    assert (
        checkpoint.read_checkpoint(directory)["payload"]["resume_instruction"]
        == "Verify the final posting result"
    )


@pytest.mark.parametrize("change", ["unresolved", "unknown", "reported", "raw_capture"])
def test_unproven_or_raw_observations_cannot_be_review_ready(checkpoint, change):
    state = payload()
    state["status"] = "ready_for_review"
    step = state["steps"][0]
    step.update(status="understood", uncertainties=[])
    if change == "unresolved":
        step.update(status="unresolved", uncertainties=["Which action caused this?"])
    elif change == "unknown":
        step["evidence_basis"] = "unknown"
    elif change == "reported":
        step.update(evidence_basis="operator_report", capture=None)
    else:
        step["capture"]["controls"] = [{"name": "private account"}]

    with pytest.raises(ValueError):
        checkpoint.validate_checkpoint(state)


def test_old_notes_can_be_preserved_without_fabricating_capture(checkpoint, tmp_path):
    state = payload()
    state["steps"][0].update(evidence_basis="operator_report", capture=None)

    checkpoint.save_checkpoint(tmp_path / "imported", state, expected_revision=0)

    assert checkpoint.read_checkpoint(tmp_path / "imported")["payload"] == state


def test_stale_writer_cannot_overwrite_another_tasks_progress(checkpoint, tmp_path):
    directory = tmp_path / "teaching"
    checkpoint.save_checkpoint(directory, payload(), expected_revision=0)
    checkpoint.save_checkpoint(directory, payload(), expected_revision=1)

    with pytest.raises(ValueError, match="stale"):
        checkpoint.save_checkpoint(directory, payload(), expected_revision=1)


def test_modified_revision_is_detected_on_resume(checkpoint, tmp_path):
    directory = tmp_path / "teaching"
    path = checkpoint.save_checkpoint(directory, payload(), expected_revision=0)
    record = json.loads(path.read_text())
    record["payload"]["status"] = "paused"
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="hash chain"):
        checkpoint.read_checkpoint(directory)


def test_observed_complete_example_is_reviewable_but_never_executable(
    checkpoint, tmp_path
):
    state = payload()
    state["steps"][0].update(
        status="understood",
        uncertainties=[],
        action="Post the selected purchase",
        decision_reason="Operator explained the account choice",
        outcome="Explicit posting confirmation observed",
        postcondition="Posting confirmation linked to the journal entry",
    )
    state.update(
        status="ready_for_review",
        resume_instruction="Review and seal the separate developer pack",
    )

    checkpoint.save_checkpoint(tmp_path / "complete", state, expected_revision=0)

    resumed = checkpoint.read_checkpoint(tmp_path / "complete")
    assert resumed["payload"]["status"] == "ready_for_review"
    assert "approved_for_developer_transfer" not in resumed["payload"]


def test_existing_directory_is_not_repurposed_or_chmodded(checkpoint, tmp_path):
    with pytest.raises(FileExistsError):
        checkpoint.save_checkpoint(tmp_path, payload(), expected_revision=0)


def test_cli_saves_and_resumes_progress(checkpoint, tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload()))
    directory = tmp_path / "session"
    assert checkpoint.main(["save", str(directory), "--input", str(input_path)]) == 0

    result = checkpoint.main(["resume", str(directory)])

    assert result == 0
    assert "Explain the account choice before posting" in caplog.text


def test_cli_reports_missing_checkpoint_without_claiming_resume(checkpoint, tmp_path):
    assert checkpoint.main(["resume", str(tmp_path / "missing")]) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unsupported"),
        ("status", "executed"),
        ("objective", ""),
        ("steps", "buttons"),
    ],
)
def test_invalid_session_input_is_rejected(checkpoint, field, value):
    state = payload()
    state[field] = value
    with pytest.raises(ValueError):
        checkpoint.validate_checkpoint(state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", ""),
        ("status", "executed"),
        ("evidence_basis", "guessed"),
        ("uncertainties", []),
        ("capture", None),
    ],
)
def test_incomplete_step_input_is_rejected(checkpoint, field, value):
    state = payload()
    state["steps"][0][field] = value
    with pytest.raises(ValueError):
        checkpoint.validate_checkpoint(state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("started_at", ""),
        ("stop_reason", "success"),
        ("transition_count", True),
        ("after_sha256", "invented"),
    ],
)
def test_invalid_capture_summary_is_rejected(checkpoint, field, value):
    state = payload()
    state["steps"][0]["capture"][field] = value
    with pytest.raises(ValueError):
        checkpoint.validate_checkpoint(state)


def test_summary_preserves_reported_rules_and_exact_resume_without_claiming_execution(
    checkpoint, tmp_path
):
    state = payload()
    state["steps"][0].update(
        evidence_basis="operator_report",
        capture=None,
        decision_reason="Existing supplier mapping still needs review for unusual services",
    )
    directory = tmp_path / "saved"
    checkpoint.save_checkpoint(directory, state, expected_revision=0)

    summary = checkpoint.summarize_checkpoint(directory)

    assert summary["revision"] == 1
    assert (
        summary["steps"][0]["decision_reason"] == state["steps"][0]["decision_reason"]
    )
    assert summary["steps"][0]["evidence_basis"] == "operator_report"
    assert summary["steps"][0]["uncertainties"] == ["Why choose this account?"]
    assert summary["resume_instruction"] == state["resume_instruction"]
    assert summary["execution_verified"] is False
    assert "capture" not in summary["steps"][0]


def test_summary_rejects_a_tampered_checkpoint_instead_of_reusing_its_rules(
    checkpoint, tmp_path
):
    directory = tmp_path / "saved"
    path = checkpoint.save_checkpoint(directory, payload(), expected_revision=0)
    record = json.loads(path.read_text())
    record["payload"]["steps"][0]["decision_reason"] = "Accept every proposed mapping"
    path.write_text(json.dumps(record))

    with pytest.raises(ValueError, match="hash chain"):
        checkpoint.summarize_checkpoint(directory)


def test_summary_cli_resumes_latest_revision_and_keeps_missing_acquisition_explicit(
    checkpoint, tmp_path, caplog
):
    directory = tmp_path / "saved"
    state = payload()
    checkpoint.save_checkpoint(directory, state, expected_revision=0)
    state["resume_instruction"] = "Read the proposed mapping for one invoice"
    state["steps"][0]["outcome"] = "Review template exists; no record acquired"
    checkpoint.save_checkpoint(directory, state, expected_revision=1)
    caplog.set_level("INFO")

    result = checkpoint.main(["resume", str(directory), "--summary"])

    assert result == 0
    summary = json.loads(caplog.records[-1].message)
    assert summary["revision"] == 2
    assert (
        summary["steps"][0]["outcome"] == "Review template exists; no record acquired"
    )
    assert summary["resume_instruction"] == "Read the proposed mapping for one invoice"
    assert summary["execution_verified"] is False
