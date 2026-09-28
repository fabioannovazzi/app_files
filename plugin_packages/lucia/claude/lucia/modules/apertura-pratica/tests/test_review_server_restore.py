"""Regression coverage for saved review recovery and stale browser submissions."""

from __future__ import annotations

import io
import json
import sys
from http import HTTPStatus
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from apertura_pratica_core import (
    initialize_workspace,
    load_json,
    prepare_review,
    review_payload_hash,
    write_json,
)
from review_server import ReviewHandler, saved_review


def workspace(tmp_path):
    root = initialize_workspace(
        tmp_path / "matter",
        opening_mode="new_client_new_matter",
        client_reference="qa-client",
        matter_reference="qa-matter",
        language="it",
    )
    prepare_review(root)
    return root


def submission(root):
    review = load_json(root / "review_payload.json")
    return dict(
        reviewer="Claude QA fictional reviewer",
        run_id=review["run_id"],
        intake_sha256=review["intake_sha256"],
        review_payload_sha256=review_payload_hash(review),
        decisions=[
            dict(
                item_id=review["items"][0]["id"],
                action="return",
                note="Fictional QA: return for missing information, no acceptance.",
            )
        ],
    )


def post(root, data):
    handler = object.__new__(ReviewHandler)
    handler.run_dir, handler.token = root, "qa-token"
    handler.path = "/qa-token/api/decisions"
    raw = json.dumps(data).encode()
    handler.headers = {"Content-Length": str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    replies = []
    handler._json = lambda status, payload: replies.append((status, payload))
    handler.do_POST()
    return replies[0]


def test_saved_return_decision_restores_across_review_regeneration(tmp_path):
    root = workspace(tmp_path)
    data = submission(root)
    assert post(root, data)[0] == HTTPStatus.OK
    before = (root / "pending_review_decisions.json").read_bytes()
    prepare_review(root)
    restored, status = saved_review(root, load_json(root / "review_payload.json"))
    assert status == "current"
    assert restored["reviewer"] == data["reviewer"]
    assert restored["decisions"] == data["decisions"]
    assert (root / "pending_review_decisions.json").read_bytes() == before
    assert not (root / "applied_decisions.json").exists()


def test_changed_intake_preserves_but_does_not_restore_old_decisions(tmp_path):
    root = workspace(tmp_path)
    old_page = submission(root)
    assert post(root, old_page)[0] == HTTPStatus.OK
    before = (root / "pending_review_decisions.json").read_bytes()
    intake = load_json(root / "matter_intake.json")
    intake["matter"]["objective"] = "Changed fictional scope needs new review"
    write_json(root / "matter_intake.json", intake)
    # Even before regeneration, the current intake must be checked.
    assert saved_review(root, load_json(root / "review_payload.json")) == (
        None,
        "unavailable",
    )
    assert post(root, old_page)[0] == HTTPStatus.BAD_REQUEST
    prepare_review(root)
    assert saved_review(root, load_json(root / "review_payload.json")) == (
        None,
        "unavailable",
    )
    assert post(root, old_page)[0] == HTTPStatus.BAD_REQUEST
    assert (root / "pending_review_decisions.json").read_bytes() == before


@pytest.mark.parametrize(
    "defect", ["missing_hash", "unknown_item", "duplicate", "invalid_action"]
)
def test_invalid_browser_decision_cannot_replace_saved_review(tmp_path, defect):
    root = workspace(tmp_path)
    data = submission(root)
    assert post(root, data)[0] == HTTPStatus.OK
    before = (root / "pending_review_decisions.json").read_bytes()
    if defect == "missing_hash":
        data.pop("review_payload_sha256")
    elif defect == "unknown_item":
        data["decisions"][0]["item_id"] = "not-in-this-review"
    elif defect == "duplicate":
        data["decisions"].append(dict(data["decisions"][0]))
    else:
        data["decisions"][0]["action"] = "not-an-action"
    assert post(root, data)[0] == HTTPStatus.BAD_REQUEST
    assert (root / "pending_review_decisions.json").read_bytes() == before


def test_corrupt_saved_file_is_preserved_and_not_restored(tmp_path):
    root = workspace(tmp_path)
    path = root / "pending_review_decisions.json"
    path.write_text("{broken")
    assert saved_review(root, load_json(root / "review_payload.json")) == (
        None,
        "unavailable",
    )
    assert path.read_text() == "{broken"
