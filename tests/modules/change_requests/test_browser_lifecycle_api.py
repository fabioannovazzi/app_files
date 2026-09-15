"""Run the real local lifecycle client against a mocked HTTP service boundary."""

from __future__ import annotations

import importlib
import importlib.util
import json
import urllib.error
import urllib.parse
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.change_requests import api
from modules.change_requests.store import ChangeRequestStore

ROOT = Path(__file__).resolve().parents[3]


def test_partial_browser_attempt_reaches_cr_store_and_fixed_version_survives_restart(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/browser-automation/scripts"))
    monkeypatch.setenv("MPARANZA_CHANGE_REQUEST_DATA", str(tmp_path / "client-state"))
    lifecycle = importlib.import_module("process_lifecycle")
    spec = importlib.util.spec_from_file_location(
        "browser_journey_test_support", ROOT / "tests/test_browser_process_lifecycle.py"
    )
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    server_store = ChangeRequestStore(sqlite_path=tmp_path / "server.sqlite3")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_change_request_store] = lambda: server_store
    client = TestClient(app)
    accepted = []

    def transport(request, **_kwargs):
        body = json.loads(request.data)
        path = urllib.parse.urlsplit(request.full_url).path
        response = client.post(path, json=body)
        assert response.status_code in {200, 201}, response.text
        if path == "/api/change-requests":
            accepted.append(body)
            if len(accepted) == 1:
                raise urllib.error.URLError("Synthetic reply loss after server commit")
        return support.Response(response.json())

    local = lifecycle.ProcessStore(tmp_path / "operator")
    process = local.create(support.description())["process_id"]
    attempt = local.begin(process, "teaching", support.host(browser_control=False))
    local.teach(attempt["attempt_id"], support.checkpoint(), 0)
    feedback = local.prepare_feedback(
        attempt["attempt_id"], support.development(), problem=support.problem()
    )
    options = dict(
        approval_id="Synthetic exact content and destination approval",
        expected_sha256=feedback["review_sha256"],
        transmission_authorized=True,
        client_options={"opener": transport},
    )
    with pytest.raises(RuntimeError):
        local.submit_feedback(feedback["feedback_id"], support.VERA, **options)
    restarted = lifecycle.ProcessStore(local.root)
    receipt = restarted.submit_feedback(
        feedback["feedback_id"], support.VERA, **options
    )

    assert receipt["change_request_id"] == "CR-1"
    assert len(accepted) == 2
    assert accepted[0]["submission_id"] == accepted[1]["submission_id"]
    stored = server_store.get("CR-1")
    assert stored.request["request"]["diagnostics"]["occurred_at"] is None
    assert process in stored.request["request"]["diagnostics"]["correlation_ids"]
    assert "Browser execution" in json.dumps(stored.request)
    assert "outputs.json" not in json.dumps(stored.request)
    publication = tmp_path / "synthetic-published-manifest.json"
    publication.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plugins": {
                    "vera": {
                        "published_version": "0.1.301",
                        "install_url": "https://chatgpt.com/plugins/synthetic-vera",
                    }
                },
            }
        )
    )
    server_store.mark_fixed(
        "CR-1", published_version="0.1.301", manifest_path=publication
    )

    restarted.refresh_status(process, support.VERA, opener=transport)

    recovered = lifecycle.ProcessStore(local.root).catalog()[0]
    assert recovered["cr_status"][0]["fixed_version"] == "0.1.301"
    assert recovered["qualification"] is None
    assert "status_token" not in json.dumps(recovered)
