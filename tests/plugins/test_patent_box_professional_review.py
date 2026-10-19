"""Exact-proposal confirmation integration using fictional archive/source fixtures."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "plugins/patent-box-review")
)
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "plugins/patent-box-review/tests")
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_box import source_acquisition as sources
from patent_box.authorization import request_bytes
from patent_box.contracts import ContractError, canonical_hash
from patent_box.proposal_review import verify_control_review
from patent_box.source_transport import PublicResponse
from test_patent_box_workflow import model_proposal, running_case, workflow
from test_source_acquisition import plan, review

NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)


@pytest.fixture
def review_case(tmp_path, workflow, monkeypatch):
    run = running_case(tmp_path, workflow, demo=False)
    payload = model_proposal(run, workflow)
    # Fictional source classification exercises REAL-mode mechanics, not legal acceptance.
    for source in payload["rules"]["sources"]:
        source["authority_type"] = "GUIDANCE"
    digest = workflow.propose(run["context"], payload)["proposal_digest"]
    proposal = json.loads((run["output"] / f"proposal_{digest}.json").read_text())
    source = proposal["rules"]["sources"][0]
    original = next(
        row
        for row in run["session"]["inputs"]
        if row["evidence_id"] == source["snapshot_evidence_id"]
    )
    raw = (run["output"] / original["path"]).read_bytes()
    monkeypatch.setattr(sources, "_now", lambda: NOW.isoformat())
    scan = Path(
        sources.open_scan(
            plan("https://institution.example/document"), tmp_path / "public"
        )["directory"]
    )
    receipt = sources.acquire(
        scan,
        scope_id="PUBLIC",
        url="https://institution.example/document",
        kind="DOCUMENT",
        fetcher=lambda url, **kwargs: PublicResponse(url, "text/plain", raw),
    )
    coverage = review(receipt)
    coverage["source_selections"][0]["source_id"] = source["source_id"]
    sources.finish_scan(scan, coverage)
    prepared = workflow.prepare_professional_review(
        run["context"], digest=digest, source_scan=scan, at=NOW
    )
    request = prepared["request"]
    return {
        **run,
        "digest": digest,
        "proposal": proposal,
        "scan": scan,
        "prepared_review": prepared,
    }


def accept(workflow, case, **changes):
    args = {
        "digest": case["digest"],
        "request_digest": case["prepared_review"]["request_digest"],
        "reviewer": "synthetic-user-with-no-professional-role",
        "confirmation_ref": "fixture-user-said-yes",
        "confirmed": True,
        "at": NOW,
    }
    args.update(changes)
    return workflow.accept_professional_review(case["context"], **args)


def test_real_calculation_uses_user_confirmation_without_keys_roles_or_mandates(
    workflow, review_case, monkeypatch
):
    monkeypatch.delenv("VERA_PATENT_BOX_AUTHORITY_CONFIG", raising=False)
    case = review_case
    accepted = accept(workflow, case)
    assert accepted["signature"] is None
    assert accepted["identity_assurance"] == "USER_CONFIRMATION_NOT_AUTHENTICATED"
    workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)
    assert (case["output"] / f"calculation_{case['digest']}" / "result.json").is_file()


@pytest.mark.parametrize(
    "change", [{"confirmed": False}, {"reviewer": ""}, {"confirmation_ref": ""}]
)
def test_no_confirmation_writes_no_decision(workflow, review_case, change):
    with pytest.raises(ValueError):
        accept(workflow, review_case, **change)
    assert not (
        review_case["output"] / f"confirmed_decision_{review_case['digest']}.json"
    ).exists()


def test_missing_confirmation_blocks_real_calculation(workflow, review_case):
    with pytest.raises(ValueError, match="Confirmation of the exact"):
        workflow.calculate_draft(
            review_case["context"], digest=review_case["digest"], at=NOW
        )


def test_changed_confirmation_is_not_reused(workflow, review_case):
    case = review_case
    accepted = accept(workflow, case)
    path = case["output"] / f"user_decision_{accepted['request_digest']}.json"
    data = json.loads(path.read_text())
    data["confirmation_ref"] = "different message"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Saved decision differs"):
        workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)


def test_changed_source_preflight_is_rejected(workflow, review_case):
    case = review_case
    accept(workflow, case)
    location = Path(case["prepared_review"]["directory"]) / "source_preflight.json"
    data = json.loads(location.read_text())
    data["exhaustive_legal_monitoring"] = True
    location.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="bindings changed"):
        workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)


def test_final_artifact_confirmation_needs_no_signature_and_detects_changes(
    workflow, review_case
):
    case = review_case
    accept(workflow, case)
    workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)
    prepared = workflow.prepare_professional_review(
        case["context"],
        digest=case["digest"],
        source_scan=case["scan"],
        action="APPROVE_DOSSIER",
        at=NOW,
    )
    record = accept(workflow, case, request_digest=prepared["request_digest"])
    assert record["signature"] is None
    result = case["output"] / f"calculation_{case['digest']}" / "result.json"
    result.write_text("{}")
    with pytest.raises(ValueError, match="artifacts changed"):
        workflow.professional_review._verify_record(
            {
                "client_id": case["client"]["client_id"],
                "engagement_id": case["engagement"]["engagement_id"],
            },
            case["session"],
            case["output"],
            case["proposal"],
            action="APPROVE_DOSSIER",
            at=NOW,
        )


def test_reopening_requires_a_new_user_decision_without_signature(
    workflow, review_case
):
    case = review_case
    accept(workflow, case)
    workflow.calculate_draft(case["context"], digest=case["digest"], at=NOW)
    final = workflow.prepare_professional_review(
        case["context"],
        digest=case["digest"],
        source_scan=case["scan"],
        action="APPROVE_DOSSIER",
        at=NOW,
    )
    accept(workflow, case, request_digest=final["request_digest"])
    previous = case["output"] / f"professional_approval_{case['digest']}.json"
    prior_bytes = previous.read_bytes()
    revised = copy.deepcopy(case["proposal"])
    revised["narratives"][0]["text"] += " Revised explanation."
    digest = workflow.propose(case["context"], revised)["proposal_digest"]
    with pytest.raises(ValueError, match="Confirmation of the exact"):
        workflow.prepare_professional_review(
            case["context"],
            digest=digest,
            source_scan=case["scan"],
            at=NOW,
        )
    reopening = workflow.prepare_professional_review(
        case["context"],
        digest=digest,
        source_scan=case["scan"],
        action="REOPEN_CASE",
        previous_digest=case["digest"],
        reason="User requested this exact revised explanation",
        at=NOW,
    )
    accept(workflow, case, digest=digest, request_digest=reopening["request_digest"])
    controls = workflow.prepare_professional_review(
        case["context"],
        digest=digest,
        source_scan=case["scan"],
        at=NOW,
    )
    accept(workflow, case, digest=digest, request_digest=controls["request_digest"])
    workflow.calculate_draft(case["context"], digest=digest, at=NOW)
    assert previous.read_bytes() == prior_bytes
    assert (case["output"] / f"calculation_{digest}" / "result.json").is_file()
