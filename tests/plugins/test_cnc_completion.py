"""Closure and authenticated-review mechanics; fixtures are not professional acceptance."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from tests.plugins.test_composizione_negoziata import (
    SCRIPT,
    case,
    cnc,
    initial,
    ledger,
    node,
    request,
)


def closing(case, role="advisor"):
    update = initial(case)
    update["role"] = role
    for item in update["upsert_nodes"]:
        item["responsibility"] = role
    report = node(
        "final_report",
        kind="draft",
        dependencies=("forecast", "proposal"),
        content="Esito sintetico senza accordo. Mancano aging e ricevute. Handoff al professionista per alternative; nessun deposito attestato.",
    )
    report["responsibility"] = role
    update["upsert_nodes"].append(report)
    update["closure"] = {
        "outcome": "no_agreement",
        "report_id": "final_report",
        "basis_ids": ["forecast", "proposal"],
        "receipt_ids": [],
        "residual_tasks": [
            {
                "node_id": "missing_aging",
                "owner": "Synthetic professional",
                "due_basis": "Unverified: obtain source and trigger date",
            }
        ],
    }
    return update


@pytest.mark.parametrize("role", ["advisor", "esperto"])
def test_role_specific_negative_closure_retains_gaps_and_reopens_on_changed_receipt(
    case, role
):
    saved = cnc.apply_request(case.context, closing(case, role))
    update = request(
        node(
            "collection",
            dependencies=("document",),
            content="Incasso rinviato a gennaio",
        ),
        revision=1,
        key="delay",
    )
    update["role"] = role
    update["upsert_nodes"][0]["responsibility"] = role
    changed = cnc.apply_request(case.context, update)
    assert cnc.closure_status(saved["payload"]) == "draft_handoff"
    assert cnc.closure_status(changed["payload"]) == "reopened_for_review"
    assert "final_report" in changed["payload"]["stale_nodes"]
    assert saved["payload"]["closure"]["receipt_ids"] == []
    assert "nessuna; adempimenti non attestati" in cnc.render_record(saved)
    assert (
        saved["payload"]["closure"]["residual_tasks"][0]["node_id"] == "missing_aging"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "wrong_report_role",
        "fake_receipt",
        "missing_basis",
        "unlinked_basis",
        "duplicate_task",
    ],
)
def test_invalid_closure_cannot_be_saved(case, mutation):
    update = closing(case)
    if mutation == "unknown":
        update["closure"]["receipt_ids"] = ["unknown"]
    elif mutation == "wrong_report_role":
        update["upsert_nodes"][-1]["responsibility"] = "common"
    elif mutation == "fake_receipt":
        update["closure"]["receipt_ids"] = ["missing_aging"]
    elif mutation == "missing_basis":
        update["closure"]["basis_ids"] = []
    elif mutation == "unlinked_basis":
        update["closure"]["basis_ids"] = ["document"]
    else:
        update["closure"]["residual_tasks"] *= 2
    with pytest.raises(ValueError):
        cnc.apply_request(case.context, update)
    assert (
        ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW) == ()
    )


def test_attributed_json_acceptance_does_not_approve_handoff(case):
    saved = cnc.apply_request(case.context, closing(case))
    review = request(revision=1, key="untrusted-review")
    review["reviews"] = [
        {
            "node_id": "final_report",
            "node_version": saved["payload"]["nodes"]["final_report"]["version"],
            "reviewer_ref": "model claimed identity",
            "confirmation_ref": "JSON only",
            "decision": "accepted",
            "reason": "Synthetic attribution",
        }
    ]
    result = cnc.apply_request(case.context, review)
    assert cnc.closure_status(result["payload"]) == "draft_handoff"
    assert (
        result["payload"]["reviews"][-1]["authority"]
        == "record_only_identity_not_verified"
    )


def test_prepare_review_cli_exports_exact_local_node_without_approving(case):
    saved = cnc.apply_request(case.context, closing(case))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--client-engagement",
            str(case.context),
            "--review-node",
            "final_report",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    files = list(Path(case.run["output_dir"]).glob("cnc-review-*.json"))
    assert result.returncode == 0, result.stderr
    assert len(files) == 1
    exported = json.loads(files[0].read_text())
    assert exported["node"] == saved["payload"]["nodes"]["final_report"]
    assert set(exported["request"]) == {
        "request_id",
        "case_ref",
        "role",
        "node_ref",
        "node_version",
    }
    assert (
        ledger.load_workflow_history(case.root, case.engagement_id, cnc.WORKFLOW)[-1][
            "payload"
        ]["reviews"]
        == []
    )


def review_receipt(case, state):
    sys.path.insert(0, str(SCRIPT.parent))
    import cnc_review_client

    return {
        "schema_version": "vera.cnc_authenticated_review.v1",
        "request_id": str(uuid4()),
        "case_ref": cnc_review_client.case_reference(case.run["context"]),
        "role": "advisor",
        "node_ref": cnc.digest("final_report"),
        "node_version": state["nodes"]["final_report"]["version"],
        "decision": "accepted",
        "actor": "synthetic@example.test",
        "reviewed_at": "2026-09-30T00:00:00+00:00",
        "authority": "mparanza_authenticated_account",
    }


def test_wrong_scope_server_receipt_is_rejected_before_network(case):
    saved = cnc.apply_request(case.context, closing(case))
    receipt = review_receipt(case, saved["payload"])
    receipt["case_ref"] = "0" * 64
    import cnc_review_client

    with pytest.raises(ValueError, match="another case"):
        cnc_review_client.verify_receipt(
            receipt,
            case.run["context"],
            node_id="final_report",
            node_version=receipt["node_version"],
            role="advisor",
            decision="accepted",
        )


def test_verified_account_receipt_controls_handoff_and_later_rejection(
    case, tmp_path, monkeypatch
):
    """Exercise real cookie auth, durable server storage and client verification together."""
    from io import BytesIO

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules.auth import dependencies
    from modules.auth.google_identity import GoogleUserInfo
    from modules.auth.session import create_session_cookie
    from modules.cnc_review import api
    from tests.modules.auth.test_dependencies import _config

    saved = cnc.apply_request(case.context, closing(case))
    receipt = review_receipt(case, saved["payload"])
    import cnc_review_client

    config = _config(session_secret="synthetic-test-key-not-a-deployment-secret")
    monkeypatch.setattr(dependencies, "get_auth_config", lambda: config)
    store = api.ReviewStore(tmp_path / "review-server.sqlite3")
    app = FastAPI()
    app.include_router(api.api_router)
    app.dependency_overrides[api.get_store] = lambda: store
    client = TestClient(app)
    cookie, _ = create_session_cookie(
        GoogleUserInfo(email="actual-test-account@example.test"), config
    )
    client.cookies.set(config.session_cookie_name, cookie)
    target = {
        key: receipt[key]
        for key in (
            "request_id",
            "case_ref",
            "role",
            "node_ref",
            "node_version",
            "decision",
        )
    }
    headers = {"Origin": "http://testserver", "X-CNC-Review": "1"}
    response = client.post("/api/vera/cnc-reviews", json=target, headers=headers)
    assert response.status_code == 200

    class TestTransport:
        def open(self, outgoing, timeout):
            assert outgoing.full_url == cnc_review_client.ENDPOINT
            verified = client.post(
                "/api/vera/cnc-reviews/verify",
                content=outgoing.data,
                headers={"Content-Type": "application/json"},
            )
            if verified.status_code != 200:
                raise ValueError("Server rejected receipt")
            return BytesIO(verified.content)

    monkeypatch.setattr(
        cnc_review_client.urllib.request, "build_opener", lambda *args: TestTransport()
    )
    review = request(revision=1, key="authenticated")
    review["reviews"] = [
        {
            "node_id": "final_report",
            "node_version": receipt["node_version"],
            "reviewer_ref": "untrusted label",
            "confirmation_ref": "untrusted label",
            "decision": "accepted",
            "reason": "Synthetic test decision; no professional acceptance claim",
            "server_receipt": response.json(),
        }
    ]
    accepted = cnc.apply_request(case.context, review)
    assert cnc.closure_status(accepted["payload"]) == "reviewed_handoff"
    assert (
        accepted["payload"]["reviews"][-1]["reviewer_ref"]
        == "actual-test-account@example.test"
    )
    rejected_receipt = client.post(
        "/api/vera/cnc-reviews",
        json={**target, "request_id": str(uuid4()), "decision": "rejected"},
        headers=headers,
    ).json()
    rejection = copy.deepcopy(review)
    rejection.update(expected_revision=2, idempotency_key="rejection")
    rejection["reviews"][0].update(decision="rejected", server_receipt=rejected_receipt)
    rejected = cnc.apply_request(case.context, rejection)
    assert cnc.closure_status(rejected["payload"]) == "draft_handoff"
    assert len(rejected["payload"]["reviews"]) == 2
    forged = copy.deepcopy(rejection)
    forged.update(expected_revision=3, idempotency_key="forgery")
    forged["reviews"][0]["server_receipt"]["actor"] = "forged@example.test"
    with pytest.raises(ValueError, match="Server rejected"):
        cnc.apply_request(case.context, forged)


def test_handoff_metadata_cannot_inherit_approval_without_new_report_version(case):
    cnc.apply_request(case.context, closing(case))
    update = request(revision=1, key="changed-handoff-only")
    update["closure"] = closing(case)["closure"]
    update["closure"]["outcome"] = "agreement"
    with pytest.raises(ValueError, match="report version"):
        cnc.apply_request(case.context, update)
