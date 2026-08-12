from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from apertura_pratica_core import (  # noqa: E402
    ValidationError,
    add_evidence,
    apply_decisions,
    canonical_json_hash,
    initialize_workspace,
    load_json,
    prepare_review,
    review_payload_hash,
    utc_now,
    validate_run,
    write_json,
)


def _confirmed(reviewer: str, timestamp: str) -> dict[str, str]:
    return {
        "status": "confirmed",
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "basis": "Confirmed by the responsible lawyer for this test matter.",
    }


def _ready_run(tmp_path: Path) -> Path:
    run_dir = initialize_workspace(
        tmp_path / "matter-run",
        opening_mode="new_client_new_matter",
        client_reference="client-001",
        matter_reference="matter-001",
        language="it",
    )
    intake = load_json(run_dir / "matter_intake.json")
    timestamp = utc_now()
    reviewer = "Avv. Test"
    intake["client"].update(display_name="Cliente Test", identity_status="verified")
    intake["confirmed_facts"] = [
        {
            "fact_id": "fact-001",
            "statement": "The client requested a defined legal review.",
            "confirmed_by": reviewer,
            "confirmed_at": timestamp,
        }
    ]
    intake["parties"][0].update(
        party_type="individual",
        roles=["client", "assisted_party"],
        identity_status="verified",
        assessment_basis="Identity and roles confirmed by the lawyer.",
    )
    intake["matter"].update(
        title="Defined test matter",
        objective="Assess the supplied issue.",
        requested_work="Prepare a reviewed memorandum.",
        summary="A bounded matter used to verify the opening contract.",
        procedural_posture="Pre-contentious assessment.",
        urgency="ordinary",
    )
    intake["matter"]["jurisdiction"] = {
        "status": "confirmed",
        "primary": "IT",
        "additional": [],
        "basis": "Confirmed by the responsible lawyer.",
    }
    intake["conflict_check"].update(
        register_scope="complete",
        register_snapshot_reference="register-snapshot-001",
        searched_at=timestamp,
        searched_party_ids=["party-client-001"],
        search_method="Responsible lawyer searched the complete approved register.",
        professional_decision={
            "status": "cleared",
            "reviewer": reviewer,
            "reviewed_at": timestamp,
            "basis": "No conflict candidate found in the recorded search.",
        },
    )
    intake["engagement"].update(
        exclusions=["Filing and external communications"],
        authority_status="verified",
        fee_terms_status="accepted",
        engagement_document_status="accepted",
        professional_owner=reviewer,
        review=_confirmed(reviewer, timestamp),
    )
    intake["engagement"]["scope_items"][0].update(
        description="Prepare the bounded reviewed memorandum.", status="confirmed"
    )
    intake["deadline_review"] = {
        "status": "confirmed_none",
        "candidates": [],
        "basis": "The lawyer confirmed that no current deadline was identified.",
        "reviewer": reviewer,
        "reviewed_at": timestamp,
    }
    intake["confidentiality"]["review"] = _confirmed(reviewer, timestamp)
    intake["aml"].update(
        applicability="not_applicable",
        basis="The responsible lawyer assessed the concrete service.",
        review=_confirmed(reviewer, timestamp),
        separate_assessment_status="not_required",
    )
    intake["privacy_retention"].update(
        notice_status="existing_approved_template",
        retention_policy_reference="firm-policy-001",
        review=_confirmed(reviewer, timestamp),
    )
    for item in intake["missing_items"]:
        item["status"] = "resolved"
    for item in intake["folder_plan"]:
        item["status"] = "accepted"
    intake["model_assessment"] = {
        "provider": "test-provider",
        "model": "test-model",
        "recorded_at": timestamp,
        "assumptions": [],
        "unresolved_questions": [],
    }
    write_json(run_dir / "matter_intake.json", intake)
    return run_dir


def test_default_intake_is_blocked_and_does_not_touch_source_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "original.txt"
    source.write_text("original", encoding="utf-8")
    run_dir = initialize_workspace(
        tmp_path / "run",
        opening_mode="existing_client_new_matter",
        client_reference="client-001",
        matter_reference="matter-001",
        language="en",
    )

    report = validate_run(run_dir)

    assert report["status"] == "blocked"
    assert source.read_text(encoding="utf-8") == "original"
    assert not any("cleared by software" in item.lower() for item in report["blockers"])


def test_evidence_intake_rejects_symbolic_links(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("private evidence", encoding="utf-8")
    linked = tmp_path / "linked.txt"
    linked.symlink_to(source)
    run_dir = initialize_workspace(
        tmp_path / "run",
        opening_mode="new_client_new_matter",
        client_reference="client-001",
        matter_reference="matter-001",
        language="it",
    )

    with pytest.raises(ValidationError, match="non-linked"):
        add_evidence(run_dir, linked, role="client_supplied")


def test_ready_intake_requires_separate_digest_bound_review(tmp_path: Path) -> None:
    run_dir = _ready_run(tmp_path)

    before_review = validate_run(run_dir)
    package = prepare_review(run_dir)

    assert before_review["status"] == "ready_for_review"
    assert package["status"] == "ready_for_review"
    assert package["conflict_cleared_by_software"] is False
    assert package["deadline_confirmed_by_software"] is False
    assert package["source_files_modified"] is False


def test_all_accepted_current_review_receipts_make_run_ready_to_open(
    tmp_path: Path,
) -> None:
    run_dir = _ready_run(tmp_path)
    prepare_review(run_dir)
    intake = load_json(run_dir / "matter_intake.json")
    review = load_json(run_dir / "review_payload.json")
    decisions = {
        "schema_version": "1.0",
        "workflow": "apertura-pratica",
        "run_id": intake["run_id"],
        "intake_sha256": canonical_json_hash(intake),
        "review_payload_sha256": review_payload_hash(review),
        "reviewer": "Avv. Test",
        "decision_source": "chat_confirmed",
        "confirmed_by_user": True,
        "saved_at": utc_now(),
        "decisions": [
            {"item_id": item["id"], "action": "accept", "note": ""}
            for item in review["items"]
        ],
    }
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

    apply_decisions(run_dir, decisions_path, confirmed_by_user=True)

    assert validate_run(run_dir)["status"] == "ready_to_open"


def test_review_cannot_be_applied_without_confirmation_or_after_intake_change(
    tmp_path: Path,
) -> None:
    run_dir = _ready_run(tmp_path)
    prepare_review(run_dir)
    intake = load_json(run_dir / "matter_intake.json")
    review = load_json(run_dir / "review_payload.json")
    decisions = {
        "schema_version": "1.0",
        "workflow": "apertura-pratica",
        "run_id": intake["run_id"],
        "intake_sha256": canonical_json_hash(intake),
        "review_payload_sha256": review_payload_hash(review),
        "reviewer": "Avv. Test",
        "decision_source": "chat_confirmed",
        "confirmed_by_user": True,
        "saved_at": utc_now(),
        "decisions": [],
    }
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
    with pytest.raises(ValidationError, match="explicit user confirmation"):
        apply_decisions(run_dir, decisions_path, confirmed_by_user=False)
    intake["matter"]["summary"] = "Changed after review."
    write_json(run_dir / "matter_intake.json", intake)

    with pytest.raises(ValidationError, match="stale"):
        apply_decisions(run_dir, decisions_path, confirmed_by_user=True)


def test_managed_run_reuses_exact_studio_archive_input_view(tmp_path: Path) -> None:
    studio_scripts = PLUGIN_ROOT.parent / "studio-archive" / "scripts"
    sys.path.insert(0, str(studio_scripts))
    import client_ledger as ledger

    client_root = tmp_path / "client-folder"
    client_root.mkdir()
    client_id = "client_0123456789abcdef01234567"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Test matter")
    source = tmp_path / "instruction.txt"
    source.write_text("Open the bounded test matter.", encoding="utf-8")
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement["engagement_id"],
        source.resolve(),
        "source",
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "apertura-pratica",
        "0.1.0",
        input_ids=[imported["receipt"]["input_id"]],
    )
    run_dir = Path(prepared["output_dir"])
    initialize_workspace(
        run_dir,
        opening_mode="new_client_new_matter",
        client_reference="client-001",
        matter_reference="matter-001",
        language="it",
    )

    record = add_evidence(
        run_dir,
        Path(prepared["context"]["input_bindings"][0]["path"]),
        role="client_supplied",
    )

    assert record["sha256"] == imported["receipt"]["sha256"]
    with pytest.raises(ValidationError, match="exact immutable input view"):
        add_evidence(run_dir, source, role="client_supplied")
