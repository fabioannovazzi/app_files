from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.auth import dependencies as auth_dependencies
from modules.auth.config import get_auth_config
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import create_session_cookie
from modules.hosted_interviews import api
from modules.hosted_interviews.campaigns import (
    AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
    CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
    COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
    LEGACY_UNCLASSIFIED_CAMPAIGN_ID,
    build_campaign_interview_payload,
)
from modules.openai_realtime import RealtimeCallResult

TEST_NOTIFICATION_EMAIL = "notifications@example.com"


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.site_router)
    app.include_router(api.public_router)
    app.include_router(api.admin_router)
    return TestClient(app)


def _client_for_viewer(viewer_email: str) -> TestClient:
    client = _client()
    if not viewer_email:
        return client
    config = get_auth_config()
    session_cookie, _ = create_session_cookie(
        GoogleUserInfo(email=viewer_email), config
    )
    client.cookies.set(config.session_cookie_name, session_cookie)
    return client


def _prepare_test_interview(
    tmp_path: Path, monkeypatch, *, interview_mode: str = api.INTERVIEW_MODE_CASE
) -> tuple[str, dict]:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTH_ENABLED", "0")
    get_auth_config.cache_clear()
    return api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id="internal-test-interview-v1",
            case_id="internal-test",
            case_name="Internal test",
            interview_title="Operations interview",
            interviewee_role="Production lead",
            interview_mode=interview_mode,
            purpose="Understand operational bottlenecks.",
            background_context="The interview should focus on production facts.",
            questions=["Who decides when quality and timing conflict?"],
            red_flags=["Vague ownership"],
            boundaries=["Do not ask family-political questions."],
        ),
        public_url_base="https://mparanza.com/case-notes/interview",
    )


def _mark_started_attempt(
    tmp_path: Path, record: dict, *, attempt_id: str = "attempt-test"
) -> str:
    session_dir = tmp_path / "sessions" / record["token_hash"]
    record_path = session_dir / "interview.json"
    current = json.loads(record_path.read_text(encoding="utf-8"))
    current["status"] = api.INTERVIEW_STATUS_STARTED
    current["started_at"] = api._iso(api._now())
    current["active_attempt_id"] = attempt_id
    record_path.write_text(json.dumps(current), encoding="utf-8")
    return attempt_id


def _sample_review() -> dict:
    return {
        "summary": "The interview captured a usable answer but needed one follow-up.",
        "overall_quality": "usable",
        "key_findings": [
            {
                "severity": "medium",
                "category": "missed follow-up",
                "evidence": "Interviewee: Answer",
                "diagnosis": "The answer was accepted without grounding.",
                "suggested_improvement": "Ask one concrete follow-up.",
                "confidence": "high",
            }
        ],
        "missed_opportunities": ["Ask for one example."],
        "evidence_backed_claims": [
            {
                "claim": "The interviewee gave an answer.",
                "supporting_quote": "Answer",
                "confidence": "high",
            }
        ],
        "uncertainties": ["No mechanism was captured."],
        "contradictions": [],
        "follow_up_questions": ["Can you give one example?"],
        "pipeline_improvements": ["Keep the review separate from the live interview."],
        "do_not_change": ["Do not make the live interview more forensic."],
    }


@pytest.fixture(autouse=True)
def _disable_post_call_interviewee_transcription(monkeypatch) -> None:
    monkeypatch.setenv(api.NOTIFICATION_EMAIL_ENV, TEST_NOTIFICATION_EMAIL)
    monkeypatch.setattr(
        api,
        "_post_call_interviewee_transcription_enabled",
        lambda: False,
    )


def test_prepared_interview_is_case_agnostic(tmp_path: Path, monkeypatch) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)

    assert token
    assert record["schema_version"] == 2
    assert record["interview_campaign_id"] == "internal-test-interview-v1"
    assert record["case_id"] == "internal-test"
    assert record["interview_mode"] == api.INTERVIEW_MODE_CASE
    assert record["notification_email"] == TEST_NOTIFICATION_EMAIL


@pytest.mark.parametrize(
    ("path_template", "viewer_email", "expected_status"),
    [
        ("/case-notes/interview/{token}", "", 200),
        ("/case-notes/api/interviews/{token}/status", "", 200),
        ("/case-notes/api/voice/interviews/campaigns", "clara@example.com", 200),
        ("/case-notes/api/voice/interviews/campaigns", "other@example.com", 403),
        ("/case-notes/interview/{token}/output", "clara@example.com", 200),
        ("/case-notes/interview/{token}/output", "other@example.com", 403),
    ],
)
def test_clara_users_administer_interviews_while_participant_links_are_public(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_template: str,
    viewer_email: str,
    expected_status: int,
) -> None:
    # Arrange
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"clara": ["clara@example.com"]}), encoding="utf-8"
    )
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps(
            {
                "clara": [
                    "/downloads/clara",
                    "/static/shared/clara/downloads",
                    "/case-notes/voice",
                    "/case-notes/api/voice",
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path / "interviews"))
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dummy-secret")
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    get_auth_config.cache_clear()
    token, _record = api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id="permission-test-v1",
            case_id="permission-test",
            case_name="Permission test",
            interview_title="Permission test interview",
            interviewee_role="Participant",
            purpose="Verify hosted interview permissions.",
        ),
        public_url_base="https://mparanza.com/case-notes/interview",
    )
    client = _client_for_viewer(viewer_email)

    # Act
    response = client.get(path_template.format(token=token), follow_redirects=False)

    # Assert
    assert response.status_code == expected_status


def test_registered_campaign_endpoint_creates_needs_onboarding_link(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTH_ENABLED", "0")
    get_auth_config.cache_clear()
    client = _client()

    campaigns_response = client.get("/case-notes/api/voice/interviews/campaigns")
    create_response = client.post(
        (
            "/case-notes/api/voice/interviews/campaigns/"
            f"{COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID}/interviews"
        ),
        json={
            "case_id": "participant-001",
            "participant_name": "Participant Example",
            "language": "it",
        },
    )

    assert campaigns_response.status_code == 200
    campaign_ids = {item["interview_campaign_id"] for item in campaigns_response.json()}
    assert campaign_ids == {
        AI_ADOPTION_RESEARCH_CAMPAIGN_ID,
        CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
        COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID,
    }
    assert create_response.status_code == 200
    payload = create_response.json()
    assert (
        payload["interview_campaign_id"] == COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID
    )
    bundle_response = client.get(
        f"/case-notes/api/voice/interviews/{payload['token']}/bundle"
    )
    record = bundle_response.json()["record"]
    assert (
        record["interview_campaign_id"] == COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID
    )
    assert "what AI currently delivers well or poorly" in record["purpose"]
    assert record["participant_intro"].startswith("Questa breve intervista")
    assert record["participant_name"] == "Participant Example"
    assert "Adoption barriers inside the firm" not in record["priority_topics"]
    assert record["questions"] == []
    assert any(
        "which process they would test first" in boundary
        for boundary in record["boundaries"]
    )


def test_registered_campaign_endpoint_rejects_unknown_id(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTH_ENABLED", "0")
    get_auth_config.cache_clear()

    response = _client().post(
        (
            "/case-notes/api/voice/interviews/campaigns/"
            "missing-interview-campaign-v1/interviews"
        ),
        json={
            "case_id": "participant-001",
            "participant_name": "Participant Example",
            "language": "it",
        },
    )

    assert response.status_code == 404
    assert "Unknown interview campaign" in response.json()["detail"]


def test_existing_working_group_link_uses_italian_participant_copy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    monkeypatch.setenv("AUTH_ENABLED", "0")
    get_auth_config.cache_clear()
    client = _client()
    create_response = client.post(
        (
            "/case-notes/api/voice/interviews/campaigns/"
            f"{COMMERCIALISTI_AI_WORKING_GROUP_CAMPAIGN_ID}/interviews"
        ),
        json={
            "case_id": "existing-participant",
            "participant_name": "Participant Example",
            "language": "it",
        },
    )
    token = create_response.json()["token"]
    bundle = client.get(f"/case-notes/api/voice/interviews/{token}/bundle").json()
    record = bundle["record"]
    record.pop("participant_intro")
    record_path = tmp_path / "sessions" / record["token_hash"] / "interview.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    response = client.get(f"/case-notes/interview/{token}")

    assert response.status_code == 200
    assert response.context["participant_intro"].startswith(
        "Questa breve intervista serve a capire"
    )
    assert (
        "Understand where commercialisti want AI"
        not in response.context["participant_intro"]
    )
    assert response.context["language"] == "it"
    assert response.context["page_label"] == "Participant Example"


def test_public_page_is_simple_and_does_not_show_transcript(
    tmp_path: Path, monkeypatch
) -> None:
    token, _record = _prepare_test_interview(tmp_path, monkeypatch)
    response = _client().get(f"/case-notes/interview/{token}")
    template = Path("templates/hosted_interview.html").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert "Inizia l'intervista" in template
    assert '<p class="eyebrow">{{ page_label }}</p>' in template
    assert "Intervista vocale" not in template
    assert "massimo 15 minuti" not in template
    assert "Voice interview" not in template
    assert "15 minutes maximum" not in template
    assert "Termina e salva" in template
    assert response.context["status_message"] == "Prima di iniziare"
    assert "autorizzare il microfono" in response.context["status_detail"]
    assert "registrate e trascritte" in response.context["status_detail"]
    assert "domande cambieranno" in response.context["status_detail"]
    assert "hosted-interview.js" in template
    assert "<textarea" not in template
    assert "Transcript" not in template
    assert "data-token" in template
    assert "data-mode" in template
    assert 'data-max-seconds="{{ max_duration_seconds }}"' in template


def test_invalid_public_link_uses_clear_italian_copy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))

    response = _client().get("/case-notes/interview/not-a-valid-token")

    assert response.status_code == 200
    assert response.context["session_ready"] is False
    assert response.context["status_message"] == "Questo link non è valido o è scaduto."
    assert response.context["status_detail"].startswith("Chiedi a chi ti ha invitato")


def test_public_session_uses_prepared_context(tmp_path: Path, monkeypatch) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    captured: dict[str, object] = {}
    started_sidebands: list[dict[str, object]] = []

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_test123")

    def fake_start_sideband(**kwargs):
        started_sidebands.append(kwargs)

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", fake_start_sideband)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "untrusted-model"},
    )

    assert response.status_code == 200
    assert response.json()["sdp"] == "answer-sdp"
    assert response.json()["attempt_id"]
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    assert session_config["model"] == api.DEFAULT_MODEL
    instructions = str(session_config["instructions"])
    assert "Production lead" in instructions
    assert "Do not ask family-political questions." in instructions
    assert "hard 15-minute browser limit" in instructions
    assert "build a faithful understanding" in instructions
    assert "Do not collect them as a proof checklist" in instructions
    assert "Interview mode changes the objective, not the posture" in instructions
    assert "Mode: case interview." in instructions
    assert "understand this specific situation deeply" in instructions
    assert "case note, advisory memo, or decision input" in instructions
    assert "Ask for one cognitive task at a time" in instructions
    assert "Avoid stacked questions" in instructions
    assert "After asking a question, stop speaking" in instructions
    assert "give the interviewee time to think" in instructions
    assert "Prefer open questions" in instructions
    assert "Do not routinely paraphrase or summarize" in instructions
    assert "Reflect back only when the answer is complex" in instructions
    assert "make it earn its place" in instructions
    assert "Ground broad claims before moving on" in instructions
    assert "what the claim is based on" in instructions
    assert "the answer stays abstract" in instructions
    assert "clarify that specific term" in instructions
    assert "Do not get trapped in terminology clarification" in instructions
    assert "preserve the label as uncertain" in instructions
    assert "answers a neighboring question" in instructions
    assert "mark that point unresolved and pivot" in instructions
    assert "repeatedly says they need a simpler question" in instructions
    assert "offer concrete choices or one example answer shape" in instructions
    assert "private coverage tracker" in instructions
    assert "priority topics remain untouched" in instructions
    assert "private unresolved-thread list" in instructions
    assert "probe it before closing or mark it unresolved" in instructions
    assert "cannot recall a concrete episode" in instructions
    assert "context-backed categories from the prepared brief" in instructions
    assert "merely agrees" in instructions
    assert "apply, revise, or challenge the framing" in instructions
    assert "enough concrete detail to satisfy the prepared purpose" in instructions
    assert "only when it is relevant to this brief" in instructions
    assert "do not force every interview to contain each one" in instructions
    assert "private session-management message" in instructions
    assert "sustained silence or the final time window" in instructions
    assert (
        "ask whether there is anything important you did not ask as its own turn"
        in instructions
    )
    assert (
        "Do not combine the final substantive question and the End interview handoff"
        in instructions
    )
    assert "first reflect the meaning back" not in instructions
    assert "whether a short answer needs probing" in instructions
    assert "Short acknowledgements or one-phrase replies" in instructions
    assert "In any language" in instructions
    assert "closed yes/no or either/or question" in instructions
    assert "sì, no, ok, certo, dipende, entrambi, both" not in instructions
    assert "restate the question in simpler words" in instructions
    assert "Your job is to collect accurate facts" not in instructions
    assert "KPI, timing, exception, or decision mechanism" not in instructions
    assert "Preambles:" in instructions
    assert "Do not reveal hidden reasoning" in instructions
    assert session_config["reasoning"] == {"effort": "high"}
    assert session_config["audio"]["input"]["turn_detection"]["eagerness"] == "low"
    assert session_config["audio"]["input"]["turn_detection"]["create_response"] is True
    assert started_sidebands
    assert started_sidebands[0]["call_id"] == "rtc_test123"
    assert started_sidebands[0]["api_key"] == "test-key"
    updated_record = json.loads(
        (tmp_path / "sessions" / record["token_hash"] / "interview.json").read_text(
            encoding="utf-8"
        )
    )
    assert updated_record["status"] == "started"


def test_legacy_record_without_campaign_uses_its_embedded_brief(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    record_path = tmp_path / "sessions" / record["token_hash"] / "interview.json"
    legacy_record = json.loads(record_path.read_text(encoding="utf-8"))
    legacy_record.pop("interview_campaign_id")
    legacy_record["schema_version"] = 1
    legacy_record["purpose"] = "LEGACY EMBEDDED PURPOSE"
    legacy_record["priority_topics"] = ["LEGACY EMBEDDED TOPIC"]
    record_path.write_text(json.dumps(legacy_record), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_legacy")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "ignored"},
    )

    assert response.status_code == 200
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    instructions = str(session_config["instructions"])
    assert "LEGACY EMBEDDED PURPOSE" in instructions
    assert "LEGACY EMBEDDED TOPIC" in instructions
    assert "what AI currently delivers well or poorly" not in instructions
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted["interview_campaign_id"] == LEGACY_UNCLASSIFIED_CAMPAIGN_ID


def test_public_session_archives_stuck_started_attempt_on_retry(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    session_dir = tmp_path / "sessions" / record["token_hash"]
    record_path = session_dir / "interview.json"
    active_record = json.loads(record_path.read_text(encoding="utf-8"))
    active_record["status"] = api.INTERVIEW_STATUS_STARTED
    active_record["started_at"] = "2026-06-30T09:43:38+00:00"
    record_path.write_text(json.dumps(active_record), encoding="utf-8")
    (session_dir / "events.ndjson").write_text(
        '{"event_type":"started","payload":{}}\n',
        encoding="utf-8",
    )
    audio_dir = session_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "chunk-000000.webm").write_bytes(b"old-audio")
    video_dir = session_dir / "video"
    video_dir.mkdir(exist_ok=True)
    (video_dir / "chunk-000000.webm").write_bytes(b"old-video")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "create_realtime_call_with_metadata",
        lambda **_kwargs: RealtimeCallResult(sdp="answer-sdp", call_id="rtc_retry"),
    )
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 200
    assert response.json()["attempt_id"]
    retry_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert retry_record["status"] == api.INTERVIEW_STATUS_STARTED
    assert retry_record["started_at"] != "2026-06-30T09:43:38+00:00"
    assert retry_record["active_attempt_id"] == response.json()["attempt_id"]
    assert not (session_dir / "events.ndjson").exists()
    assert not (session_dir / "audio" / "chunk-000000.webm").exists()
    assert not (session_dir / "video" / "chunk-000000.webm").exists()
    attempts = list((session_dir / "attempts").glob("*"))
    assert len(attempts) == 1
    assert (attempts[0] / "events.ndjson").exists()
    assert (attempts[0] / "audio" / "chunk-000000.webm").read_bytes() == b"old-audio"
    assert (attempts[0] / "video" / "chunk-000000.webm").read_bytes() == b"old-video"


def test_public_session_rejects_duplicate_active_started_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    session_dir = tmp_path / "sessions" / record["token_hash"]
    record_path = session_dir / "interview.json"
    attempt_id = _mark_started_attempt(tmp_path, record)
    realtime_calls: list[dict] = []

    def fake_realtime_call(**kwargs):
        realtime_calls.append(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_duplicate")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 409
    assert not realtime_calls
    unchanged_record = json.loads(record_path.read_text(encoding="utf-8"))
    assert unchanged_record["status"] == api.INTERVIEW_STATUS_STARTED
    assert unchanged_record["active_attempt_id"] == attempt_id
    assert not (session_dir / "attempts").exists()


def test_research_interview_mode_uses_shared_dimensions_without_checklist(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    token, record = api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id="commercialisti-research-test-v1",
            case_id="ai-commercialisti",
            case_name="Commercialisti AI research",
            interview_title="AI usage by commercialisti",
            interviewee_role="Commercialista",
            interview_mode="research",
            purpose="Understand how commercialisti use AI across many interviews.",
            priority_topics=["Current AI uses", "Trust barriers"],
        ),
        public_url_base="https://mparanza.com/case-notes/interview",
    )
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_test123")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 200
    assert record["interview_mode"] == api.INTERVIEW_MODE_RESEARCH
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    instructions = str(session_config["instructions"])
    assert "Interview mode: research_interview" in instructions
    assert "Mode: research interview." in instructions
    assert "shared research dimensions" in instructions
    assert "compare across participants later" in instructions
    assert "Preserve comparability without sounding scripted" in instructions
    assert "prepared brief and boundaries determine" in instructions
    assert "Do not impose a generic product ban" in instructions
    assert "Interview mode changes the objective, not the posture" in instructions
    assert "Do not collect them as a proof checklist" in instructions
    assert "Your job is to collect accurate facts" not in instructions


def test_clara_research_prompt_discusses_clara_and_starts_from_a_concrete_task() -> (
    None
):
    record = build_campaign_interview_payload(
        CLARA_NEEDS_RESEARCH_CAMPAIGN_ID,
        case_id="clara-prompt-test",
        language="it",
    )

    instructions = api._interview_instructions(record, "it")

    assert "product-needs interview about Clara" in instructions
    assert "Begin with the first concrete thing" in instructions
    assert "describe them briefly in plain language" in instructions
    assert "Do not impose a generic product ban" in instructions
    assert "Do not introduce product, plugin, installation" not in instructions
    assert "structured consultant interview" not in instructions
    assert "do not force every interview to contain each one" in instructions


def test_unknown_interview_mode_normalizes_to_case_interview(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOSTED_INTERVIEWS_ROOT", str(tmp_path))
    token, record = api.create_prepared_interview(
        api.PreparedInterviewRequest(
            interview_campaign_id="unsupported-mode-test-v1",
            case_id="unsupported-mode",
            case_name="Unsupported mode",
            interview_title="Partner discussion",
            interviewee_role="Partner",
            interview_mode="unsupported_mode",
            purpose="Capture the discussion.",
        ),
        public_url_base="https://mparanza.com/case-notes/interview",
    )
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_unknown")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 200
    assert record["interview_mode"] == api.INTERVIEW_MODE_CASE
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    instructions = str(session_config["instructions"])
    assert "Interview mode: case_interview" in instructions
    assert "Mode: case interview." in instructions
    assert "Preserve references to slide numbers" not in instructions


def test_english_session_uses_english_thinking_bridges(
    tmp_path: Path, monkeypatch
) -> None:
    token, _record = _prepare_test_interview(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_test123")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "en", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 200
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    instructions = str(session_config["instructions"])
    assert (
        "Use this configured interview language for the whole interview: en."
        in instructions
    )
    assert "short, noisy, ambiguous, or accidental transcript fragment" in instructions
    assert "Do not switch language during a hosted interview" in instructions
    assert "One moment." in instructions
    assert "Right, I see." in instructions
    assert "One moment, I want to make sure I understand." not in instructions
    assert "Let me check that I understood correctly." not in instructions
    assert "Un attimo" not in instructions
    assert "Vorrei verificare" not in instructions


def test_german_session_uses_german_thinking_bridges(
    tmp_path: Path, monkeypatch
) -> None:
    token, _record = _prepare_test_interview(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_realtime_call(**kwargs):
        captured.update(kwargs)
        return RealtimeCallResult(sdp="answer-sdp", call_id="rtc_test123")

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "create_realtime_call_with_metadata", fake_realtime_call)
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "de", "model": "gpt-realtime-2"},
    )

    assert response.status_code == 200
    session_config = captured["session_config"]
    assert isinstance(session_config, dict)
    instructions = str(session_config["instructions"])
    assert (
        "Use this configured interview language for the whole interview: de."
        in instructions
    )
    assert "Do not switch language during a hosted interview" in instructions
    assert "Einen Moment." in instructions
    assert "Gut, ich verstehe." in instructions
    assert "Einen Moment, ich möchte sicherstellen" not in instructions
    assert "Lassen Sie mich kurz prüfen" not in instructions
    assert "Un attimo" not in instructions
    assert "One moment, I want to make sure I understand." not in instructions


def test_partner_prompt_checks_process_instead_of_suggesting_questions(
    tmp_path: Path, monkeypatch
) -> None:
    _token, record = _prepare_test_interview(tmp_path, monkeypatch)

    prompt = api._live_partner_prompt(
        record,
        language="en",
        turns=[
            {
                "speaker": "Interviewer",
                "text": "What should clients understand about AI adoption?",
            },
            {
                "speaker": "Interviewee",
                "text": "It is more about organizational learning than tools.",
            },
        ],
        latest_speaker="Interviewee",
        latest_text="It is more about organizational learning than tools.",
        last_whisper="",
    )

    assert "silent process checker" in prompt
    assert "not a second interviewer" in prompt
    assert "build accurate understanding" in prompt
    assert "Interview mode: case_interview" in prompt
    assert "mode changes the objective" in prompt
    assert "process is drifting" in prompt
    assert "too intense, forensic, or checklist-like" in prompt
    assert "too many cognitive tasks in one turn" in prompt
    assert "mechanically repeats or summarizes answers" in prompt
    assert "probes before understanding an ambiguous or important answer" in prompt
    assert "accepts broad, abstract, or unclear answers" in prompt
    assert "output needs usable evidence" in prompt
    assert "after only one explored theme" in prompt
    assert "important live thread" in prompt
    assert "context-backed artifact categories" in prompt
    assert "receives mere agreement" in prompt
    assert "lacks concrete detail needed for the prepared purpose" in prompt
    assert "keeps relitigating an uncertain label" in prompt
    assert "keeps asking near-variants" in prompt
    assert "keeps shrinking the same question" in prompt
    assert "different from the configured interview language" in prompt
    assert "Default to an empty whisper" in prompt
    assert "single imperfect but acceptable turn" in prompt
    assert "has not begun closing or prioritizing" in prompt
    assert "Do not repeat the previous whisper" in prompt
    assert "Good whispers:" in prompt
    assert "You are summarizing too much; move the conversation forward." in prompt
    assert "Ground the broad claim before moving on." in prompt
    assert "Check priority coverage before closing." in prompt
    assert "Resolve the live thread or mark it unresolved." in prompt
    assert "Offer artifact categories to recover a concrete example." in prompt
    assert "Do not accept agreement to your framing as evidence." in prompt
    assert "Capture one missing depth dimension before closing." in prompt
    assert "Mark the label uncertain and move on." in prompt
    assert "Name the non-answer once, then pivot." in prompt
    assert "Offer choices once; then mark unresolved." in prompt
    assert "Do not suggest new interview questions or topic probes." in prompt
    assert "Do not ask for missing evidence" in prompt
    assert (
        "an owner, KPI, timing, example, exception, or decision mechanism is missing"
        not in prompt
    )
    assert "Do not draft a full spoken question" not in prompt


def test_partner_sideband_clears_stale_whisper_when_model_returns_empty(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    sent_messages: list[dict] = []
    websocket_messages = [
        json.dumps(
            {
                "type": "response.output_audio_transcript.done",
                "transcript": "Can you explain how the process works?",
            }
        ),
        json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "We review quality issues every Thursday.",
            }
        ),
    ]

    class FakeWebsocket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not websocket_messages:
                raise StopAsyncIteration
            return websocket_messages.pop(0)

        async def send(self, message: str) -> None:
            sent_messages.append(json.loads(message))

    fake_websocket = FakeWebsocket()
    whispers = ["Slow down; ask one simpler question.", ""]

    def fake_create_partner_whisper(**_kwargs):
        return whispers.pop(0)

    monkeypatch.setitem(
        sys.modules,
        "websockets",
        types.SimpleNamespace(connect=lambda *_args, **_kwargs: fake_websocket),
    )
    monkeypatch.setattr(api, "create_partner_whisper", fake_create_partner_whisper)

    asyncio.run(
        api._hosted_partner_sideband_loop(
            token=token,
            record=record,
            call_id="rtc_sideband",
            api_key="test-key",
            language="en",
        )
    )

    assert len(sent_messages) == 2
    first_instructions = sent_messages[0]["session"]["instructions"]
    second_instructions = sent_messages[1]["session"]["instructions"]
    assert "Live silent partner note" in first_instructions
    assert "Slow down; ask one simpler question." in first_instructions
    assert "Live silent partner note" not in second_instructions
    assert "Slow down; ask one simpler question." not in second_instructions
    session_dir = tmp_path / "sessions" / record["token_hash"]
    events_text = (session_dir / "events.ndjson").read_text(encoding="utf-8")
    assert "partner_whisper" in events_text
    assert "partner_whisper_cleared" in events_text


def test_event_audio_and_completion_are_saved_and_notify_recipients(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    answer = (
        "The production lead explained that timing conflicts are escalated to "
        "operations every Thursday, with quality defects measured before any "
        "delivery promise is confirmed to the client."
    )
    sent: list[tuple[str, str, str]] = []

    def fake_send_email(recipients, subject, body, **_kwargs):
        sent.append((recipients, subject, body))
        return True

    monkeypatch.setattr(api, "send_plain_text_email", fake_send_email)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()

    interviewer_event_response = client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "interviewer_turn",
            "payload": {"text": "Question"},
        },
    )
    interviewee_event_response = client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "interviewee_turn",
            "payload": {"text": answer},
        },
    )
    audio_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )
    complete_response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Question",
            "elapsed_seconds": 12,
            "transcript_words": 28,
            "audio_chunks": 1,
            "telemetry": {"turns": 1},
        },
    )

    assert interviewer_event_response.status_code == 200
    assert interviewee_event_response.status_code == 200
    assert audio_response.status_code == 200
    assert complete_response.status_code == 200
    assert complete_response.json()["notification_sent"] is False
    assert complete_response.json()["notification_status"] == "queued_after_review"
    assert complete_response.json()["status"] == api.INTERVIEW_STATUS_COMPLETED
    assert complete_response.json()["output_url"].endswith(f"/{token}/output")
    assert complete_response.json()["bundle_url"].endswith(f"/{token}/bundle")
    assert complete_response.json()["review_url"].endswith(f"/{token}/review")
    assert complete_response.json()["review_status"] == "queued"
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert (session_dir / "audio" / "chunk-000000.webm").read_bytes() == b"audio-bytes"
    assert "interviewee_turn" in (session_dir / "events.ndjson").read_text(
        encoding="utf-8"
    )
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    assert completion["user_transcript"] == answer
    events = api._read_events_for_session(session_dir)
    dialog_turns = api._dialog_turns_for_session(events, completion)
    assert [turn["speaker"] for turn in dialog_turns] == ["Interviewer", "Interviewee"]
    assert [turn["text"] for turn in dialog_turns] == ["Question", answer]
    review = json.loads((session_dir / "review.json").read_text(encoding="utf-8"))
    assert (
        review["summary"]
        == "The interview captured a usable answer but needed one follow-up."
    )
    assert review["schema_version"] == 1
    assert sent
    assert sent[0][0] == TEST_NOTIFICATION_EMAIL
    assert f"/case-notes/interview/{token}/output" in sent[0][2]
    assert f"/case-notes/api/voice/interviews/{token}/bundle" in sent[0][2]
    assert f"/case-notes/api/voice/interviews/{token}/review" in sent[0][2]

    output_response = client.get(f"/case-notes/interview/{token}/output")
    output_template = Path("templates/hosted_interview_output.html").read_text(
        encoding="utf-8"
    )

    assert output_response.status_code == 200
    assert "Dialog Transcript" in output_template
    assert "Quality Review" in output_template
    assert "Open quality review" in output_template
    assert "Transcript source" in output_template
    assert "Mic transcript" in output_template
    assert "Final Interviewee Transcript" in output_template
    assert "Open JSON bundle" in output_template


def test_post_call_mic_transcription_replaces_live_interviewee_transcript(
    tmp_path: Path,
    monkeypatch,
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    live_transcript = (
        "The live transcript says operations meets weekly but misses the "
        "specific escalation path, quality threshold, and delivery decision "
        "rule that were explained by the interviewee."
    )
    final_transcript = (
        "The post call microphone transcript says the operations lead escalates "
        "quality conflicts to the plant manager every Thursday, uses the defect "
        "threshold before committing delivery dates, and documents the exception "
        "rule in the production review log."
    )
    captured_review: dict[str, object] = {}

    def fake_transcribe(**kwargs):
        captured_review["transcription_session_dir"] = kwargs["session_dir"]
        return {
            "text": final_transcript,
            "metadata": {
                "status": "complete",
                "coverage_complete": True,
                "transcription_model": "gpt-4o-transcribe",
            },
            "audio_files": [
                {
                    "file_name": "chunk-000000.webm",
                    "relative_path": "audio/chunk-000000.webm",
                    "content_type": "audio/webm",
                    "bytes": 11,
                }
            ],
        }

    def fake_review(**kwargs):
        captured_review["dialog_turns"] = kwargs["dialog_turns"]
        captured_review["completion"] = dict(kwargs["completion"])
        return _sample_review()

    monkeypatch.setattr(
        api, "_post_call_interviewee_transcription_enabled", lambda: True
    )
    monkeypatch.setattr(api, "_transcribe_interviewee_audio_chunks", fake_transcribe)
    monkeypatch.setattr(api, "_generate_interview_quality_review", fake_review)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()
    client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "interviewer_turn",
            "payload": {"text": "How are delivery conflicts handled?"},
        },
    )
    client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "interviewee_turn",
            "payload": {"text": live_transcript},
        },
    )
    audio_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": live_transcript,
            "assistant_transcript": "How are delivery conflicts handled?",
            "elapsed_seconds": 180,
            "transcript_words": 26,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert _wait_until(lambda: (session_dir / "review.json").exists())
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    events_text = (session_dir / "events.ndjson").read_text(encoding="utf-8")

    assert audio_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert response.json()["provisional_status"] == api.INTERVIEW_STATUS_COMPLETED
    assert (
        response.json()["notification_status"] == "queued_after_post_call_transcription"
    )
    assert response.json()["review_status"] == "queued_after_post_call_transcription"
    assert completion["live_user_transcript"] == live_transcript
    assert completion["user_transcript"] == final_transcript
    assert completion["transcript_source"] == "post_call_interviewee_audio"
    assert completion["interviewee_audio_transcription"]["status"] == "complete"
    assert (
        completion["interviewee_audio_transcription"]["transcription_metadata"][
            "transcription_model"
        ]
        == "gpt-4o-transcribe"
    )
    assert "post_call_interviewee_transcription_completed" in events_text
    assert [turn["speaker"] for turn in captured_review["dialog_turns"]] == [
        "Interviewer",
        "Interviewee",
    ]
    assert [turn["text"] for turn in captured_review["dialog_turns"]] == [
        "How are delivery conflicts handled?",
        live_transcript,
    ]
    assert captured_review["completion"]["user_transcript"] == final_transcript
    review_prompt = api._interview_review_prompt(
        record,
        completion,
        api._read_events_for_session(session_dir),
        captured_review["dialog_turns"],
    )
    assert '"source": "post_call_interviewee_audio"' in review_prompt
    assert final_transcript in review_prompt
    assert live_transcript in review_prompt
    assert (session_dir / "review.json").exists()


def test_post_call_mic_transcription_can_recover_live_asr_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    final_transcript = (
        "The recovered microphone transcript describes how the production lead "
        "uses a weekly review meeting, names the escalation owner, explains the "
        "quality defect threshold, and describes the delivery timing rule in "
        "enough detail for the interview to be usable."
    )
    monkeypatch.setattr(
        api, "_post_call_interviewee_transcription_enabled", lambda: True
    )
    monkeypatch.setattr(
        api,
        "_transcribe_interviewee_audio_chunks",
        lambda **_kwargs: {
            "text": final_transcript,
            "metadata": {"status": "complete", "coverage_complete": True},
            "audio_files": [],
        },
    )
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()
    client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": "",
            "assistant_transcript": "Opening question",
            "elapsed_seconds": 180,
            "transcript_words": 0,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert _wait_until(lambda: (session_dir / "review.json").exists())
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    updated_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    events_text = (session_dir / "events.ndjson").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert (
        response.json()["provisional_status"] == api.INTERVIEW_STATUS_FAILED_TECHNICAL
    )
    assert completion["completion_status"] == api.INTERVIEW_STATUS_COMPLETED
    assert completion["completion_status_reason"] == "completed_with_minimum_substance"
    assert completion["transcript_source"] == "post_call_interviewee_audio"
    assert completion["user_transcript"] == final_transcript
    assert updated_record["status"] == api.INTERVIEW_STATUS_COMPLETED
    assert "post_call_completion_reclassified" in events_text
    assert (session_dir / "review.json").exists()


def test_failed_post_call_mic_transcription_preserves_live_transcript(
    tmp_path: Path,
    monkeypatch,
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    live_transcript = (
        "The live transcript captured a substantive explanation of ownership, "
        "quality thresholds, weekly cadence, exception handling, and delivery "
        "tradeoffs even though post call transcription later failed."
    )

    def fake_transcribe(**_kwargs):
        raise api.VoiceSessionError("microphone audio could not be decoded")

    monkeypatch.setattr(
        api, "_post_call_interviewee_transcription_enabled", lambda: True
    )
    monkeypatch.setattr(api, "_transcribe_interviewee_audio_chunks", fake_transcribe)
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()
    client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": live_transcript,
            "assistant_transcript": "Question",
            "elapsed_seconds": 180,
            "transcript_words": 25,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert _wait_until(lambda: (session_dir / "review.json").exists())
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    events_text = (session_dir / "events.ndjson").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert completion["user_transcript"] == live_transcript
    assert completion["live_user_transcript"] == live_transcript
    assert completion["transcript_source"] == "realtime_live_asr"
    assert completion["interviewee_audio_transcription"]["status"] == "error"
    assert (
        "microphone audio could not be decoded"
        in completion["interviewee_audio_transcription"]["message"]
    )
    assert "post_call_interviewee_transcription_failed" in events_text
    assert (session_dir / "review.json").exists()


def test_completion_requires_active_attempt(tmp_path: Path, monkeypatch) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    session_dir = tmp_path / "sessions" / record["token_hash"]

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "forged-attempt",
            "user_transcript": "This should not be accepted without a started attempt.",
            "assistant_transcript": "Question",
            "elapsed_seconds": 120,
            "transcript_words": 12,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )

    assert response.status_code == 409
    assert not (session_dir / "completed.json").exists()


def test_public_attempt_endpoints_reject_wrong_attempt_id(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()

    event_response = client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": "wrong-attempt",
            "event_type": "interviewee_turn",
            "payload": {"text": "Answer"},
        },
    )
    audio_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": "wrong-attempt", "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )
    complete_response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": "wrong-attempt",
            "user_transcript": "This should not bind to the active attempt.",
            "assistant_transcript": "Question",
            "elapsed_seconds": 120,
            "transcript_words": 12,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )

    assert attempt_id == "attempt-test"
    assert event_response.status_code == 409
    assert audio_response.status_code == 409
    assert complete_response.status_code == 409


def test_chunks_do_not_overwrite_and_stop_after_completion(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    answer = (
        "The respondent gave a concrete explanation of the review cadence, "
        "named the escalation owner, described the threshold used for quality "
        "exceptions, and explained how delivery timing is decided."
    )
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )
    client = _client()

    first_chunk_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"audio-bytes", "audio/webm")},
    )
    duplicate_chunk_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"replacement-audio", "audio/webm")},
    )
    complete_response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Question",
            "elapsed_seconds": 180,
            "transcript_words": 29,
            "audio_chunks": 1,
            "telemetry": {},
        },
    )
    stale_event_response = client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "interviewee_turn",
            "payload": {"text": "Late answer"},
        },
    )
    stale_chunk_response = client.post(
        f"/case-notes/api/interviews/{token}/audio-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "1"},
        files={"file": ("chunk.webm", b"late-audio", "audio/webm")},
    )

    assert first_chunk_response.status_code == 200
    assert duplicate_chunk_response.status_code == 409
    assert complete_response.status_code == 200
    assert stale_event_response.status_code == 409
    assert stale_chunk_response.status_code == 409
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert (session_dir / "audio" / "chunk-000000.webm").read_bytes() == b"audio-bytes"
    updated_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    assert "active_attempt_id" not in updated_record


def test_media_upload_failure_marks_attempt_failed_technical(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    answer = (
        "The respondent gave enough substantive detail about ownership, cadence, "
        "quality thresholds, exception handling, timing tradeoffs, and decision "
        "rules that the interview would otherwise be complete."
    )
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    client = _client()
    upload_error_response = client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "audio_chunk_upload_error",
            "payload": {"chunk_index": 0, "message": "network failed"},
        },
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Question",
            "elapsed_seconds": 180,
            "transcript_words": 28,
            "audio_chunks": 1,
            "telemetry": {
                "upload_errors": [
                    {
                        "type": "audio",
                        "chunk_index": 0,
                        "message": "network failed",
                    }
                ]
            },
        },
    )

    assert upload_error_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["status"] == api.INTERVIEW_STATUS_FAILED_TECHNICAL
    assert response.json()["completion_status_reason"] == "media_upload_failed"
    assert response.json()["review_status"] == "skipped"
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert not (session_dir / "review.json").exists()


def test_optional_video_chunk_completion_and_bundle_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    answer = (
        "At minute ten we were looking at slide five, and Reviewer asked to "
        "move the margin bridge to the appendix after the executive summary."
    )
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )
    attempt_id = _mark_started_attempt(tmp_path, record)
    client = _client()

    video_response = client.post(
        f"/case-notes/api/interviews/{token}/video-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "0"},
        files={"file": ("chunk.webm", b"video-bytes", "video/webm")},
    )
    invalid_response = client.post(
        f"/case-notes/api/interviews/{token}/video-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "1"},
        files={"file": ("chunk.txt", b"not-video", "text/plain")},
    )
    monkeypatch.setattr(api, "MAX_VIDEO_CHUNK_BYTES", 4)
    oversized_response = client.post(
        f"/case-notes/api/interviews/{token}/video-chunk",
        data={"attempt_id": attempt_id, "chunk_index": "2"},
        files={"file": ("chunk.webm", b"too-large", "video/webm")},
    )
    complete_response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Which slide was visible?",
            "elapsed_seconds": 633,
            "transcript_words": 25,
            "audio_chunks": 1,
            "video_chunks": 1,
            "screen_capture_metadata": {
                "started_at": "2026-07-03T10:00:00.000Z",
                "mime_type": "video/webm",
                "width": 1920,
                "height": 1080,
                "display_surface": "browser",
            },
            "telemetry": {"turns": 1},
        },
    )
    bundle_response = client.get(f"/case-notes/api/voice/interviews/{token}/bundle")

    assert video_response.status_code == 200
    assert invalid_response.status_code == 400
    assert oversized_response.status_code == 413
    assert complete_response.status_code == 200
    assert bundle_response.status_code == 200
    session_dir = tmp_path / "sessions" / record["token_hash"]
    assert (session_dir / "video" / "chunk-000000.webm").read_bytes() == b"video-bytes"
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    assert completion["video_chunks"] == 1
    assert completion["screen_capture_metadata"]["display_surface"] == "browser"
    bundle = bundle_response.json()
    assert bundle["video_file_name"] == "chunk-000000.webm"
    assert bundle["video_content_type"] == "video/webm"
    assert bundle["video_chunks"] == 1
    assert bundle["video_files"][0]["relative_path"] == "video/chunk-000000.webm"
    assert bundle["screen_capture_metadata"]["width"] == 1920


def test_completion_does_not_require_video_chunks(tmp_path: Path, monkeypatch) -> None:
    token, record = _prepare_test_interview(
        tmp_path,
        monkeypatch,
    )
    attempt_id = _mark_started_attempt(tmp_path, record)
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": (
                "The transcript is substantial enough and does not require any "
                "screen video to complete cleanly."
            ),
            "assistant_transcript": "Question",
            "elapsed_seconds": 120,
            "transcript_words": 30,
            "audio_chunks": 1,
            "video_chunks": 0,
            "telemetry": {},
        },
    )

    assert response.status_code == 200


def test_completion_accepts_video_chunk_count_without_uploaded_video_file(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": "The transcript claims a video chunk but none was uploaded.",
            "assistant_transcript": "Question",
            "elapsed_seconds": 120,
            "transcript_words": 30,
            "audio_chunks": 1,
            "video_chunks": 1,
            "telemetry": {},
        },
    )

    assert response.status_code == 200


def test_short_manual_completion_is_marked_incomplete_without_review(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    sent: list[tuple[str, str, str]] = []

    def fake_send_email(recipients, subject, body, **_kwargs):
        sent.append((recipients, subject, body))
        return True

    monkeypatch.setattr(api, "send_plain_text_email", fake_send_email)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: _sample_review(),
    )

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": "entrambe",
            "assistant_transcript": "Opening question",
            "elapsed_seconds": 147,
            "transcript_words": 1,
            "audio_chunks": 15,
            "telemetry": {
                "turns": 1,
                "completion_reason": "manual",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == api.INTERVIEW_STATUS_INCOMPLETE
    assert (
        response.json()["completion_status_reason"]
        == "too_little_interviewee_substance"
    )
    assert response.json()["review_status"] == "skipped"
    session_dir = tmp_path / "sessions" / record["token_hash"]
    updated_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    assert updated_record["status"] == api.INTERVIEW_STATUS_INCOMPLETE
    assert "completed_at" not in updated_record
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    assert completion["user_transcript"] == "entrambe"
    assert completion["completion_status"] == api.INTERVIEW_STATUS_INCOMPLETE
    assert not (session_dir / "review.json").exists()
    assert "early_incomplete_completion_ignored" not in (
        session_dir / "events.ndjson"
    ).read_text(encoding="utf-8")
    assert sent


def test_completion_ignores_client_word_count_for_status(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    attempt_id = _mark_started_attempt(tmp_path, record)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": "ok",
            "assistant_transcript": "Opening question",
            "elapsed_seconds": 90,
            "transcript_words": 999,
            "audio_chunks": 0,
            "telemetry": {},
        },
    )
    session_dir = tmp_path / "sessions" / record["token_hash"]
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )

    assert response.status_code == 200
    assert response.json()["status"] == api.INTERVIEW_STATUS_INCOMPLETE
    assert completion["transcript_words"] == 1
    assert completion["client_transcript_words"] == 999
    assert completion["completion_status"] == api.INTERVIEW_STATUS_INCOMPLETE


def test_connection_failure_with_no_transcript_is_marked_failed_technical(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    client = _client()
    client.post(
        f"/case-notes/api/interviews/{token}/event",
        json={
            "attempt_id": attempt_id,
            "event_type": "connection_issue",
            "payload": {"source": "peer_connection", "detail": "failed"},
        },
    )

    response = client.post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": "",
            "assistant_transcript": "Opening question",
            "elapsed_seconds": 141,
            "transcript_words": 0,
            "audio_chunks": 15,
            "telemetry": {
                "turns": 0,
                "completion_reason": "manual",
                "peer_connection_state": "failed",
                "data_channel_state": "closed",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == api.INTERVIEW_STATUS_FAILED_TECHNICAL
    assert response.json()["review_status"] == "skipped"
    session_dir = tmp_path / "sessions" / record["token_hash"]
    updated_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    assert updated_record["status"] == api.INTERVIEW_STATUS_FAILED_TECHNICAL
    assert "completed_at" not in updated_record
    assert "failed_technical" in (session_dir / "events.ndjson").read_text(
        encoding="utf-8"
    )

    monkeypatch.setattr(
        api,
        "create_realtime_call_with_metadata",
        lambda **_kwargs: RealtimeCallResult(sdp="answer-sdp", call_id="rtc_retry"),
    )
    monkeypatch.setattr(api, "_start_partner_sideband", lambda **_kwargs: None)
    retry_response = client.post(
        f"/case-notes/api/interviews/{token}/session",
        json={"sdp": "offer-sdp", "language": "it", "model": "gpt-realtime-2"},
    )

    assert retry_response.status_code == 200
    retry_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    assert retry_record["status"] == api.INTERVIEW_STATUS_STARTED
    assert not (session_dir / "completed.json").exists()
    assert not (session_dir / "events.ndjson").exists()
    archived_attempts = list((session_dir / "attempts").iterdir())
    assert archived_attempts
    assert (archived_attempts[0] / "completed.json").exists()
    assert (archived_attempts[0] / "events.ndjson").exists()


def test_background_review_saves_error_without_failing_completion(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    answer = (
        "The respondent described a clear operating process with monthly review "
        "meetings, named escalation ownership, and a concrete quality threshold "
        "used before client delivery is accepted."
    )
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")

    def fake_review_failure(**_kwargs):
        raise api.VoiceSessionError("review model unavailable")

    monkeypatch.setattr(api, "_generate_interview_quality_review", fake_review_failure)

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Question",
            "elapsed_seconds": 12,
            "transcript_words": 26,
            "audio_chunks": 0,
            "telemetry": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == api.INTERVIEW_STATUS_COMPLETED
    assert response.json()["review_status"] == "queued"
    assert response.json()["review_error"] == ""
    session_dir = tmp_path / "sessions" / record["token_hash"]
    review_error = json.loads(
        (session_dir / "review_error.json").read_text(encoding="utf-8")
    )
    assert "review model unavailable" in review_error["error"]
    assert not (session_dir / "review.json").exists()


def test_review_generation_retries_once_after_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    calls: list[float | None] = []

    def fake_review(**kwargs):
        calls.append(kwargs.get("timeout_seconds"))
        if len(calls) == 1:
            raise api.VoiceSessionError(
                "Interview quality review failed: The read operation timed out"
            )
        return _sample_review()

    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(api, "_generate_interview_quality_review", fake_review)

    session_dir = tmp_path / "sessions" / record["token_hash"]
    review, review_error = api._write_interview_quality_review(
        token=token,
        record=record,
        completion={"completed_at": "2026-06-29T08:27:07+00:00"},
        events=[],
        dialog_turns=[{"speaker": "Interviewee", "text": "Substantive answer"}],
    )

    assert review["overall_quality"] == "usable"
    assert review_error == {}
    assert calls == [None, api.DEFAULT_INTERVIEW_REVIEW_RETRY_TIMEOUT_SECONDS]
    assert (session_dir / "review.json").exists()
    assert not (session_dir / "review_error.json").exists()


def test_failed_quality_review_marks_interview_unusable(
    tmp_path: Path, monkeypatch
) -> None:
    token, record = _prepare_test_interview(tmp_path, monkeypatch)
    attempt_id = _mark_started_attempt(tmp_path, record)
    answer = (
        "The respondent produced enough words for a transcript, but the turns were "
        "contradictory and did not answer the interview objective in a coherent "
        "way that a consultant could use."
    )
    failed_review = _sample_review()
    failed_review["overall_quality"] = "failed"
    monkeypatch.setattr(api, "send_plain_text_email", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(api, "_resolve_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(
        api,
        "_generate_interview_quality_review",
        lambda **_kwargs: failed_review,
    )

    response = _client().post(
        f"/case-notes/api/interviews/{token}/complete",
        json={
            "attempt_id": attempt_id,
            "user_transcript": answer,
            "assistant_transcript": "Question",
            "elapsed_seconds": 180,
            "transcript_words": 29,
            "audio_chunks": 1,
            "telemetry": {"turns": 1},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == api.INTERVIEW_STATUS_COMPLETED
    assert (
        response.json()["completion_status_reason"]
        == "completed_with_minimum_substance"
    )
    assert response.json()["review_status"] == "queued"
    session_dir = tmp_path / "sessions" / record["token_hash"]
    updated_record = json.loads(
        (session_dir / "interview.json").read_text(encoding="utf-8")
    )
    assert updated_record["status"] == api.INTERVIEW_STATUS_UNUSABLE
    completion = json.loads(
        (session_dir / "completed.json").read_text(encoding="utf-8")
    )
    assert completion["completion_status"] == api.INTERVIEW_STATUS_UNUSABLE
    assert (session_dir / "review.json").exists()


def test_browser_script_enforces_time_limit() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "maxInterviewSeconds" in script
    assert "time_limit_reached" in script
    assert "completion_reason: reason" in script


def test_browser_script_uses_realtime_led_conversation() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "createInitialResponse" in script
    assert 'context_strategy: "realtime_conversation"' in script
    assert "realtime_response_usage" in script
    assert '"/partner-whisper"' not in script
    assert "FOLLOW_UP_SETTLE_MS" not in script
    assert "FOLLOW_UP_WATCHDOG_MS" not in script
    assert "scheduleFollowUp" not in script
    assert "conversation.item.delete" not in script
    assert "text_memory_out_of_band" not in script


def test_browser_script_records_turns_without_driving_followups() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "input_audio_buffer.speech_started" in script
    assert "input_audio_buffer.speech_stopped" in script
    assert "conversation.item.input_audio_transcription.completed" in script
    assert 'postEvent("interviewee_turn"' in script
    assert 'postEvent("interviewer_turn"' in script
    assert "pendingAnswerParts" not in script
    assert "follow_up_" not in script


def test_browser_script_has_no_short_answer_completion_gate() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")
    template = Path("templates/hosted_interview.html").read_text(encoding="utf-8")

    assert "MIN_MANUAL_COMPLETION_WORDS" not in script
    assert "MIN_MANUAL_COMPLETION_TURNS" not in script
    assert "isIncompleteManualStop" not in script
    assert "early_incomplete_stop" not in script
    assert 'postJson("/complete"' in script
    assert "20260715-product-research-v2" in template


def test_browser_script_uses_attempt_id_for_attempt_writes() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")
    start_function_index = script.index("async function startInterview()")
    start_function = script[start_function_index:].split(
        "function cleanupConnection()", 1
    )[0]

    assert 'let activeAttemptId = "";' in script
    assert "let uploadErrors = [];" in script
    assert "if (!activeAttemptId) {" in script
    assert "attempt_id: activeAttemptId" in script
    assert 'form.append("attempt_id", activeAttemptId);' in script
    assert "uploadErrors.push({" in script
    assert "upload_errors: uploadErrors" in script
    assert "if (startedAt && activeAttemptId) {" in script
    assert 'activeAttemptId = payload.attempt_id || "";' in start_function
    assert start_function.index(
        'activeAttemptId = payload.attempt_id || "";'
    ) < start_function.index("startAudioRecorder(localStream);")
    assert start_function.index(
        'const response = await postJson("/session"'
    ) < start_function.index("startAudioRecorder(localStream);")


def test_browser_script_keeps_screen_recording_out_of_interview_start() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")
    template = Path("templates/hosted_interview.html").read_text(encoding="utf-8")
    start_function_index = script.index("async function startInterview()")
    start_function = script[start_function_index:].split(
        "function cleanupConnection()", 1
    )[0]

    assert "screenStream = await openScreenCapture()" not in start_function
    assert "startScreenRecorder(screenStream)" not in start_function
    assert "navigator.mediaDevices.getDisplayMedia({ video: true })" in script
    assert 'fetch(endpoint("/video-chunk")' in script
    assert "video_chunks: videoChunksUploaded" in script
    assert "screen_capture_metadata: screenCaptureMetadata" in script
    assert 'data-mode="{{ interview_mode | default(' in template
    assert "screen-captured for deck revision" not in template


def test_browser_script_manages_silence_and_near_end_without_semantic_gates() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "SILENCE_NUDGE_SECONDS = 35" in script
    assert "SILENCE_SIMPLIFY_SECONDS = 75" in script
    assert "NEAR_END_SECONDS = 120" in script
    assert "FINAL_CLOSE_SECONDS = 60" in script
    assert "manageSessionFlow()" in script
    assert "session_management_prompt" in script
    assert "silence_nudge" in script
    assert "silence_simplify" in script
    assert "isClosingHandoff" in script
    assert "closing_handoff_detected" in script
    assert "do not repeat 'No rush'" in script
    assert "categories drawn from the prepared brief or the conversation" in script
    assert "generic consulting example is fine" not in script
    assert "identify yourself clearly as an AI interviewer" in script
    assert "near_end_wrap_up" in script
    assert "final_close" in script
    assert "Timing and silence are mechanical browser facts" in script
    assert "RESPONSE_CREATE_COOLDOWN_MS = 2500" in script
    assert "RECENT_INPUT_SETTLE_MS = 3000" in script
    assert "markResponseCreateAttempt()" in script
    assert 'event.type === "response.created"' in script
    assert "active response in progress" in script
    assert "SILENT_REALTIME_STALL_MS = 90000" in script
    assert "LIKELY_SPEECH_AUDIO_BYTES = 50000" in script
    assert "LIKELY_SPEECH_CHUNKS_BEFORE_STALL = 2" in script
    assert "checkLiveConnectionStall()" in script
    assert "realtime_silent_stall" in script
    assert "Do not infer an answer that has not appeared in the transcript." in script
    assert "closing_input_muted" in script
    assert "muteLiveInputAfterClosing()" in script
    assert 'setStatus("Ready to finish"' in script
    assert "silenceRecoveryCount === 0" in script
    assert "awaitingIntervieweeAnswer" in script
    assert "MIN_MANUAL_COMPLETION_WORDS" not in script


def test_browser_script_flushes_partial_speech_and_surfaces_connection_issues() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "const FINAL_TRANSCRIPT_SETTLE_MS = 2500;" in script
    assert 'flushTranscriptDelta("completion")' in script
    assert "interviewee_partial_turn_flushed" in script
    assert "connectionstatechange" in script
    assert "handleConnectionIssue" in script
    assert "connection_issue" in script
    assert "connectionIssueHandled" in script
    assert "The live interview connection stopped responding" in script
    assert "failed_technical" in script
    assert "Please retry this link" in script


def test_browser_script_waits_for_final_audio_chunk_before_completion() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")
    stop_function = script.split("function stopAudioRecorder()", 1)[1].split(
        "function screenTrackMetadata", 1
    )[0]

    assert "activeRecorder.requestData()" in stop_function
    assert "Promise.allSettled([...pendingUploads])" in stop_function
    assert "window.setTimeout(finish, 8000)" in stop_function


def test_browser_script_treats_queued_post_call_transcription_as_processing() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")
    end_function = script.split("async function endInterview", 1)[1]

    assert (
        'responsePayload.notification_status === "queued_after_post_call_transcription"'
        in end_function
    )
    assert (
        'responsePayload.review_status === "queued_after_post_call_transcription"'
        in end_function
    )
    assert "The final microphone transcript is being processed" in end_function
    assert end_function.index("if (postCallQueued)") < end_function.index(
        'if (completionStatus === "failed_technical")'
    )


def test_browser_script_records_client_and_speech_telemetry() -> None:
    script = Path("static/js/hosted-interview.js").read_text(encoding="utf-8")

    assert "clientMetadata()" in script
    assert "SCRIPT_VERSION" in script
    assert "20260715-product-research-v2" in script
    assert 'postEvent("client_metadata", clientMetadata())' in script
    assert 'postEvent("speech_started"' in script
    assert 'postEvent("speech_stopped"' in script
    assert 'postEvent("transcription_delta_started"' in script
    assert 'postEvent("transcription_completed_empty"' in script
    assert 'postEvent("end_button_clicked"' in script


def test_dialog_turns_include_flushed_partial_interviewee_turn() -> None:
    dialog_turns = api._dialog_turns_for_session(
        [
            {
                "captured_at": "2026-06-27T10:00:00+00:00",
                "event_type": "interviewer_turn",
                "payload": {"text": "Opening question"},
            },
            {
                "captured_at": "2026-06-27T10:00:12+00:00",
                "event_type": "interviewee_partial_turn_flushed",
                "payload": {"text": "Final answer captured during shutdown"},
            },
        ],
        {},
    )

    assert [turn["speaker"] for turn in dialog_turns] == [
        "Interviewer",
        "Interviewee",
    ]
    assert dialog_turns[-1]["text"] == "Final answer captured during shutdown"


def test_dialog_turns_replace_partial_when_full_turn_arrives() -> None:
    dialog_turns = api._dialog_turns_for_session(
        [
            {
                "captured_at": "2026-06-27T10:00:12+00:00",
                "event_type": "interviewee_partial_turn_flushed",
                "payload": {"text": "This answer starts"},
            },
            {
                "captured_at": "2026-06-27T10:00:14+00:00",
                "event_type": "interviewee_turn",
                "payload": {"text": "This answer starts and then completes."},
            },
        ],
        {},
    )

    assert len(dialog_turns) == 1
    assert dialog_turns[0]["text"] == "This answer starts and then completes."


def test_dialog_turns_skip_non_substantive_interviewer_fragments() -> None:
    dialog_turns = api._dialog_turns_for_session(
        [
            {
                "captured_at": "2026-06-27T10:00:00+00:00",
                "event_type": "interviewer_turn",
                "payload": {"text": "One moment."},
            },
            {
                "captured_at": "2026-06-27T10:00:01+00:00",
                "event_type": "interviewer_turn",
                "payload": {"text": "One possibility is,"},
            },
            {
                "captured_at": "2026-06-27T10:00:02+00:00",
                "event_type": "interviewer_turn",
                "payload": {"text": "Take"},
            },
            {
                "captured_at": "2026-06-27T10:00:03+00:00",
                "event_type": "interviewer_turn",
                "payload": {"text": "Which decision rule did you use?"},
            },
            {
                "captured_at": "2026-06-27T10:00:14+00:00",
                "event_type": "interviewee_turn",
                "payload": {"text": "We used risk first, then cost."},
            },
        ],
        {},
    )

    assert [turn["text"] for turn in dialog_turns] == [
        "Which decision rule did you use?",
        "We used risk first, then cost.",
    ]


def test_current_run_events_ignore_previous_reused_link_attempts() -> None:
    events = [
        {
            "captured_at": "2026-06-27T17:07:14+00:00",
            "event_type": "started",
            "payload": {"language": "en"},
        },
        {
            "captured_at": "2026-06-27T17:08:00+00:00",
            "event_type": "interviewer_turn",
            "payload": {"text": "Old question"},
        },
        {
            "captured_at": "2026-06-27T17:08:12+00:00",
            "event_type": "interviewee_turn",
            "payload": {"text": "Old answer"},
        },
        {
            "captured_at": "2026-06-27T17:17:45+00:00",
            "event_type": "completed",
            "payload": {"completed_at": "2026-06-27T17:17:45+00:00"},
        },
        {
            "captured_at": "2026-06-30T04:31:22+00:00",
            "event_type": "started",
            "payload": {"language": "en"},
        },
        {
            "captured_at": "2026-06-30T04:32:00+00:00",
            "event_type": "interviewer_turn",
            "payload": {"text": "Current question"},
        },
        {
            "captured_at": "2026-06-30T04:32:12+00:00",
            "event_type": "interviewee_turn",
            "payload": {"text": "Current answer"},
        },
        {
            "captured_at": "2026-06-30T04:38:06+00:00",
            "event_type": "completed",
            "payload": {"completed_at": "2026-06-30T04:38:06+00:00"},
        },
        {
            "captured_at": "2026-06-30T04:39:00+00:00",
            "event_type": "interviewer_turn",
            "payload": {"text": "Late stray prompt"},
        },
    ]
    completion = {"completed_at": "2026-06-30T04:38:06+00:00"}

    current_events = api._events_for_current_run(events, completion)
    dialog_turns = api._dialog_turns_for_session(current_events, completion)

    assert [event["event_type"] for event in current_events] == [
        "started",
        "interviewer_turn",
        "interviewee_turn",
        "completed",
    ]
    assert [turn["text"] for turn in dialog_turns] == [
        "Current question",
        "Current answer",
    ]
