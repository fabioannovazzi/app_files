from __future__ import annotations

import hashlib
import io
import json
import wave
import zipfile
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from modules.auth.config import get_auth_config
from modules.auth.dependencies import (
    require_authenticated_user,
    require_authenticated_user_for_site,
)
from modules.auth.google_identity import GoogleUserInfo
from modules.auth.session import create_session_cookie
from modules.research_video_voice import api


def _wav_bytes() -> bytes:
    """Return a small valid PCM WAV fixture."""

    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\0\0" * 1_600)
    return output.getvalue()


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "language": "it",
        "scene_plan_sha256": "a" * 64,
        "approval": {
            "approval_sha256": "b" * 64,
            "confirmed_by_user": True,
        },
        "scenes": [
            {"id": "quadro", "narration": "Il dato è un esempio sintetico."},
            {"id": "limite", "narration": "Il risultato richiede revisione."},
        ],
    }


def _client_for(email: str | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(
        api.site_router,
        dependencies=[Depends(require_authenticated_user_for_site)],
    )
    app.include_router(
        api.router,
        dependencies=[Depends(require_authenticated_user)],
    )
    client = TestClient(app)
    if email:
        config = get_auth_config()
        cookie, _expires = create_session_cookie(GoogleUserInfo(email=email), config)
        client.cookies.set(config.session_cookie_name, cookie)
    return client


@pytest.fixture(autouse=True)
def _auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "listed@example.com")
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def test_research_video_voice_requires_authentication() -> None:
    client = _client_for()

    page = client.get(
        "/case-notes/research-video/voice",
        follow_redirects=False,
    )
    api_response = client.post(
        "/case-notes/api/research-video/voice",
        json=_payload(),
        headers={"X-Mparanza-Action": "research-video-voice-v1"},
    )

    assert page.status_code == 307
    assert page.headers["location"].startswith("/auth/page?")
    assert api_response.status_code == 401


def test_signed_in_account_is_accepted_without_research_video_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("openAiKey", "k" * 32)
    monkeypatch.setattr(api, "_request_openai_speech", lambda **_kwargs: _wav_bytes())
    client = _client_for("not-listed@example.com")

    page = client.get("/case-notes/research-video/voice")
    response = client.post(
        "/case-notes/api/research-video/voice",
        json=_payload(),
        headers={"X-Mparanza-Action": "research-video-voice-v1"},
    )
    page_source = Path("templates/research_video_voice.html").read_text(
        encoding="utf-8"
    )

    assert page.status_code == 200
    assert "available to every signed-in Mparanza account" in page_source
    assert "Images, research sources" in page_source
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/zip"


def test_voice_response_is_a_hash_bound_in_memory_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = _wav_bytes()
    monkeypatch.setenv("openAiKey", "k" * 32)
    monkeypatch.setattr(api, "_request_openai_speech", lambda **_kwargs: audio)
    payload = _payload()
    client = _client_for("viewer@example.com")

    response = client.post(
        "/case-notes/api/research-video/voice",
        json=payload,
        headers={"X-Mparanza-Action": "research-video-voice-v1"},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        bundled_audio = archive.read("audio/01-quadro.wav")
        assert set(archive.namelist()) == {
            "manifest.json",
            "audio/01-quadro.wav",
            "audio/02-limite.wav",
        }
    assert bundled_audio == audio
    assert manifest["source"] == "mparanza_hosted_openai_voice"
    assert manifest["provider"] == "OpenAI"
    assert manifest["model"] == "gpt-4o-mini-tts"
    assert manifest["voice"] == "marin"
    assert manifest["approval_sha256"] == "b" * 64
    assert manifest["mparanza_application_retention"] == "in_memory_response_only"
    assert manifest["scenes"][0]["sha256"] == hashlib.sha256(audio).hexdigest()


def test_voice_endpoint_rejects_missing_action_header_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = False

    def fake_speech(**_kwargs: object) -> bytes:
        nonlocal generated
        generated = True
        return _wav_bytes()

    monkeypatch.setenv("openAiKey", "k" * 32)
    monkeypatch.setattr(api, "_request_openai_speech", fake_speech)

    response = _client_for("viewer@example.com").post(
        "/case-notes/api/research-video/voice",
        json=_payload(),
    )

    assert response.status_code == 400
    assert generated is False


@pytest.mark.parametrize(
    "change",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["scenes"].append(payload["scenes"][0].copy()),
        lambda payload: payload["approval"].update({"confirmed_by_user": False}),
    ],
)
def test_voice_endpoint_rejects_unbound_or_malformed_requests(
    change,
) -> None:
    payload = _payload()
    change(payload)

    response = _client_for("viewer@example.com").post(
        "/case-notes/api/research-video/voice",
        json=payload,
        headers={"X-Mparanza-Action": "research-video-voice-v1"},
    )

    assert response.status_code == 422


def test_provider_failure_does_not_echo_secret_or_narration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "secret-provider-credential-value"
    narration = str(_payload()["scenes"][0]["narration"])
    monkeypatch.setenv("openAiKey", secret)
    monkeypatch.setattr(
        api,
        "_request_openai_speech",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    response = _client_for("viewer@example.com").post(
        "/case-notes/api/research-video/voice",
        json=_payload(),
        headers={"X-Mparanza-Action": "research-video-voice-v1"},
    )

    assert response.status_code == 503
    assert secret not in response.text
    assert narration not in response.text


def test_server_key_resolver_accepts_existing_open_ai_key_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("openAiKey", "existing-secret-name-value")

    assert api._openai_api_key() == "existing-secret-name-value"
