from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.change_requests import api as change_request_api
from modules.change_requests import store as change_request_store
from modules.change_requests.store import ChangeRequestStore
from modules.hosted_interviews import api as hosted_interview_api
from modules.openai_realtime import RealtimeCallResult


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


def test_interview_submission_returns_same_one_minute_link_on_retry(
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
    assert interview["max_duration_seconds"] == 60
    assert interview["interviewer_name"] == "Mparanza"
    assert (
        interview["interview_mode"]
        == hosted_interview_api.INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    )
    assert interview["priority_topics"] == []
    assert interview["questions"] == ["Cosa dovrebbe fare meglio Clara?"]
    assert "Non nominare clienti" in interview["participant_intro"]
    assert interview["change_request_id"] == "CR-1"
    instructions = hosted_interview_api._interview_instructions(interview, "it")
    assert "hard maximum of two interviewer question-response turns" in instructions
    assert (
        "ask for the single most important missing implementation detail"
        in instructions
    )
    assert "prepared question as the fallback opening" in instructions
    assert "Do not ask a generic final question" in instructions
    assert "anything important you did not ask as its own turn" not in instructions
    assert "private coverage tracker" not in instructions
    assert len(store.list_open()) == 1


def test_interview_opening_question_names_vera(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "interviews"))
    store = ChangeRequestStore(sqlite_path=tmp_path / "requests.sqlite3")
    payload = _payload()
    payload.update(
        {
            "submission_id": "79a4759f-57bf-416b-8834-e93263307133",
            "plugin": "vera",
            "language": "en",
        }
    )

    response = _client(store).post("/api/change-requests/interviews", json=payload)

    assert response.status_code == 201
    token = response.json()["interview_url"].rsplit("/", 1)[-1]
    interview = hosted_interview_api._load_record_for_token(token)
    assert interview["questions"] == ["What should Vera do better?"]
    assert "Do not name clients or customers" in interview["participant_intro"]


def test_interview_submission_accepts_spanish_and_localizes_intro(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "interviews"))
    store = ChangeRequestStore(sqlite_path=tmp_path / "requests.sqlite3")
    payload = _payload()
    payload.update(
        {
            "submission_id": "74803396-2558-4503-bd32-650cedb3963e",
            "language": "es",
        }
    )

    response = _client(store).post("/api/change-requests/interviews", json=payload)

    assert response.status_code == 201
    token = response.json()["interview_url"].rsplit("/", 1)[-1]
    interview = hosted_interview_api._load_record_for_token(token)
    assert interview["language"] == "es"
    assert interview["questions"] == ["¿Qué debería hacer mejor Clara?"]
    assert "No menciones a clientes" in interview["participant_intro"]


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


def test_successful_retry_replaces_no_change_request_completion(
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
    persisted["active_attempt_id"] = "attempt-incomplete"
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

    incomplete = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "attempt-incomplete",
            "user_transcript": "yes",
            "assistant_transcript": "What should Clara do better?",
            "elapsed_seconds": 10,
            "transcript_words": 1,
        },
    )
    after_incomplete = store.get("CR-1")
    monkeypatch.setattr(hosted_interview_api, "_resolve_openai_api_key", lambda: "key")
    monkeypatch.setattr(
        hosted_interview_api,
        "create_realtime_call_with_metadata",
        lambda **_kwargs: RealtimeCallResult(sdp="answer-sdp", call_id="rtc-retry"),
    )
    retry_session = client.post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it"},
    )
    retry_attempt_id = retry_session.json()["attempt_id"]
    completed = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": retry_attempt_id,
            "user_transcript": "Esporta ogni tabella",
            "assistant_transcript": "Quale formato deve avere?",
            "elapsed_seconds": 20,
            "transcript_words": 3,
        },
    )

    assert incomplete.status_code == 200
    assert (
        incomplete.json()["status"] == hosted_interview_api.INTERVIEW_STATUS_INCOMPLETE
    )
    assert after_incomplete is not None
    assert after_incomplete.interview_json is None
    assert retry_session.status_code == 200
    assert completed.status_code == 200
    assert completed.json()["status"] == hosted_interview_api.INTERVIEW_STATUS_COMPLETED
    final_request = store.get("CR-1")
    assert final_request is not None
    assert final_request.interview_json is not None
    attached = json.loads(final_request.interview_json)
    assert attached["user_transcript"] == "Esporta ogni tabella"


def test_post_call_transcript_is_finalized_before_change_request_attachment(
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
    persisted["active_attempt_id"] = "attempt-final"
    record_path.write_text(json.dumps(persisted), encoding="utf-8")
    monkeypatch.setattr(change_request_store, "get_change_request_store", lambda: store)
    monkeypatch.setattr(
        hosted_interview_api,
        "_should_run_post_call_interviewee_transcription",
        lambda *_args: True,
    )

    def finalize_transcript(**kwargs):
        completion = kwargs["completion"]
        completion["user_transcript"] = "Final transcript from recorded audio."
        completion["transcript_source"] = "post_call_interviewee_audio"
        return completion

    monkeypatch.setattr(
        hosted_interview_api,
        "_apply_post_call_interviewee_transcription",
        finalize_transcript,
    )
    monkeypatch.setattr(
        hosted_interview_api, "_run_interview_quality_review_task", lambda *_args: None
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "attempt-final",
            "user_transcript": "Provisional live transcript.",
            "assistant_transcript": "What should the capability do?",
            "elapsed_seconds": 42,
            "transcript_words": 3,
            "audio_chunks": 1,
        },
    )

    assert response.status_code == 200
    request_record = store.get("CR-1")
    assert request_record is not None
    completion = json.loads(request_record.interview_json or "{}")
    assert completion["user_transcript"] == "Final transcript from recorded audio."
    assert completion["transcript_source"] == "post_call_interviewee_audio"


def test_concurrent_post_call_task_cannot_attach_provisional_transcript(
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
    persisted["active_attempt_id"] = "attempt-concurrent"
    record_path.write_text(json.dumps(persisted), encoding="utf-8")
    transcription_started = threading.Event()
    release_transcription = threading.Event()
    final_transcript = (
        "The final recorded-audio transcript explains the requested capability, "
        "its intended users, the reviewed output, the evidence requirements, and "
        "the concrete workflow in enough detail to replace provisional live text."
    )

    def transcribe(**_kwargs):
        transcription_started.set()
        assert release_transcription.wait(timeout=2)
        return {
            "text": final_transcript,
            "metadata": {"status": "complete"},
            "audio_files": [],
        }

    monkeypatch.setattr(change_request_store, "get_change_request_store", lambda: store)
    monkeypatch.setattr(
        hosted_interview_api,
        "_post_call_interviewee_transcription_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        hosted_interview_api, "_transcribe_interviewee_audio_chunks", transcribe
    )
    monkeypatch.setattr(
        hosted_interview_api, "_run_interview_quality_review_task", lambda *_args: None
    )
    monkeypatch.setattr(
        hosted_interview_api, "_send_completion_notification", lambda *_args: False
    )
    response_holder: dict[str, int] = {}

    def complete_interview() -> None:
        response = client.post(
            f"/case-notes/api/interviews/{token}/complete",
            json={
                "attempt_id": "attempt-concurrent",
                "user_transcript": "Provisional live transcript.",
                "assistant_transcript": "What should the capability do?",
                "elapsed_seconds": 42,
                "transcript_words": 3,
                "audio_chunks": 1,
            },
        )
        response_holder["status_code"] = response.status_code

    completion_thread = threading.Thread(target=complete_interview)
    completion_thread.start()
    assert transcription_started.wait(timeout=2)

    hosted_interview_api._run_interview_post_completion_task(token)

    pending_record = store.get("CR-1")
    assert pending_record is not None
    assert pending_record.interview_json is None
    release_transcription.set()
    completion_thread.join(timeout=2)
    assert not completion_thread.is_alive()

    assert response_holder["status_code"] == 200
    completed_record = store.get("CR-1")
    assert completed_record is not None
    completion = json.loads(completed_record.interview_json or "{}")
    assert completion["user_transcript"] == final_transcript
    assert completion["transcript_source"] == "post_call_interviewee_audio"


def test_concurrent_completion_request_cannot_bypass_final_transcript_lock(
    tmp_path: Path, monkeypatch
) -> None:
    interviews_root = tmp_path / "interviews"
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(interviews_root))
    store = ChangeRequestStore(sqlite_path=tmp_path / "requests.sqlite3")
    first_client = _client(store)
    second_client = _client(store)
    created = first_client.post(
        "/api/change-requests/interviews", json=_payload()
    ).json()
    token = created["interview_url"].rsplit("/", 1)[-1]
    record = hosted_interview_api._load_record_for_token(token)
    record_path = interviews_root / "sessions" / record["token_hash"] / "interview.json"
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    persisted["status"] = hosted_interview_api.INTERVIEW_STATUS_STARTED
    persisted["started_at"] = hosted_interview_api._iso(hosted_interview_api._now())
    persisted["active_attempt_id"] = "attempt-http-race"
    record_path.write_text(json.dumps(persisted), encoding="utf-8")
    active_attempt_checked = threading.Event()
    release_first_completion = threading.Event()
    original_active_attempt_record = hosted_interview_api._active_attempt_record
    final_transcript = (
        "The recorded-audio transcript describes the requested capability, the "
        "intended workflow, the reviewed evidence, the expected output, and the "
        "user decision in enough detail to supersede both provisional payloads."
    )

    def pause_after_active_attempt_check(*args, **kwargs):
        active_record = original_active_attempt_record(*args, **kwargs)
        active_attempt_checked.set()
        assert release_first_completion.wait(timeout=2)
        return active_record

    def transcribe(**_kwargs):
        return {
            "text": final_transcript,
            "metadata": {"status": "complete"},
            "audio_files": [],
        }

    monkeypatch.setattr(change_request_store, "get_change_request_store", lambda: store)
    monkeypatch.setattr(
        hosted_interview_api, "_active_attempt_record", pause_after_active_attempt_check
    )
    monkeypatch.setattr(
        hosted_interview_api,
        "_post_call_interviewee_transcription_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        hosted_interview_api, "_transcribe_interviewee_audio_chunks", transcribe
    )
    monkeypatch.setattr(
        hosted_interview_api, "_run_interview_quality_review_task", lambda *_args: None
    )
    response_holder: dict[str, int] = {}

    def complete_with_recorded_audio() -> None:
        response = first_client.post(
            f"/case-notes/api/interviews/{token}/complete",
            json={
                "attempt_id": "attempt-http-race",
                "user_transcript": "First provisional live transcript.",
                "assistant_transcript": "What should the capability do?",
                "elapsed_seconds": 42,
                "transcript_words": 4,
                "audio_chunks": 1,
            },
        )
        response_holder["status_code"] = response.status_code

    first_completion = threading.Thread(target=complete_with_recorded_audio)
    first_completion.start()
    assert active_attempt_checked.wait(timeout=2)

    competing_response = second_client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "attempt-http-race",
            "user_transcript": "Competing provisional transcript.",
            "assistant_transcript": "Competing question.",
            "elapsed_seconds": 10,
            "transcript_words": 3,
            "audio_chunks": 0,
        },
    )

    assert competing_response.status_code == 409
    pending_record = store.get("CR-1")
    assert pending_record is not None
    assert pending_record.interview_json is None
    release_first_completion.set()
    first_completion.join(timeout=2)
    assert not first_completion.is_alive()
    assert response_holder["status_code"] == 200
    completed_record = store.get("CR-1")
    assert completed_record is not None
    completion = json.loads(completed_record.interview_json or "{}")
    assert completion["user_transcript"] == final_transcript
    assert completion["transcript_source"] == "post_call_interviewee_audio"
