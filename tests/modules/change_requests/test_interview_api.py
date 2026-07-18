from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.change_requests import api as change_request_api
from modules.change_requests import store as change_request_store
from modules.change_requests.store import ChangeRequestStore
from modules.hosted_interviews import api as hosted_interview_api


def _client(store: ChangeRequestStore) -> TestClient:
    app = FastAPI()
    app.include_router(hosted_interview_api.site_router)
    app.include_router(hosted_interview_api.public_router)
    app.include_router(change_request_api.router)
    app.dependency_overrides[change_request_api.get_change_request_store] = (
        lambda: store
    )
    return TestClient(app)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "submission_id": "f781cd18-e09b-47d9-97ef-31041ad72c79",
        "plugin": "clara",
        "plugin_version": "1.2.3",
        "opportunity": "Turn reviewed interview findings into a decision memo.",
        "language": "it",
    }


def test_interview_submission_returns_same_three_minute_link_on_retry(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "interviews"))
    store = ChangeRequestStore(sqlite_path=tmp_path / "requests.sqlite3")
    client = _client(store)

    first = client.post("/api/change-requests/interviews", json=_payload())
    second = client.post("/api/change-requests/interviews", json=_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    assert first.json()["change_request_id"] == "CR-1"
    token = first.json()["interview_url"].rsplit("/", 1)[-1]
    interview = hosted_interview_api._load_record_for_token(token)
    assert interview["max_duration_seconds"] == 180
    assert interview["interviewer_name"] == "Mparanza"
    assert interview["change_request_id"] == "CR-1"
    assert len(store.list_open()) == 1


def test_completing_improvement_interview_attaches_transcript_to_request(
    tmp_path: Path, monkeypatch
) -> None:
    interviews_root = tmp_path / "interviews"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(interviews_root))
    store = ChangeRequestStore(sqlite_path=tmp_path / "requests.sqlite3")
    client = _client(store)
    created = client.post("/api/change-requests/interviews", json=_payload()).json()
    token = created["interview_url"].rsplit("/", 1)[-1]
    record = hosted_interview_api._load_record_for_token(token)
    record_path = interviews_root / "sessions" / record["token_hash"] / "interview.json"
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    persisted["status"] = hosted_interview_api.INTERVIEW_STATUS_STARTED
    persisted["started_at"] = hosted_interview_api._iso(hosted_interview_api._now())
    persisted["active_attempt_id"] = "attempt-1"
    record_path.write_text(json.dumps(persisted), encoding="utf-8")
    monkeypatch.setattr(change_request_store, "get_change_request_store", lambda: store)
    monkeypatch.setattr(
        hosted_interview_api,
        "_post_call_interviewee_transcription_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        hosted_interview_api, "_send_completion_notification", lambda *_args: False
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "attempt-1",
            "user_transcript": "I need the plugin to create the memo automatically.",
            "assistant_transcript": "What should the memo contain?",
            "elapsed_seconds": 42,
            "transcript_words": 9,
        },
    )

    assert response.status_code == 200
    request_record = store.get("CR-1")
    assert request_record is not None
    assert request_record.interview_json is not None
    completion = json.loads(request_record.interview_json)
    assert completion["user_transcript"].startswith("I need the plugin")
    assert completion["elapsed_seconds"] == 42
