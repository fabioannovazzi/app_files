from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from scripts import build_vera_youtube_video_guides as renderer
from scripts.video_voice_policy import (
    APPROVED_VIDEO_VOICES,
    OPENAI_VIDEO_TTS_MODEL,
    SUPPORTED_VIDEO_LANGUAGES,
    VIDEO_VOICE_BY_LANGUAGE,
    video_voice_for_language,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_BUILDER_SOURCES = tuple(
    path
    for path in sorted((REPO_ROOT / "scripts").rglob("*.py"))
    if "video" in path.stem.lower()
)
APPLE_VOICE_PATTERN = re.compile(
    r"\b(?:Alice|Samantha|Thomas|Anna|M[oó]nica)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    ("language", "expected_voice"),
    (
        ("it", "marin"),
        ("en", "cedar"),
        ("fr", "cedar"),
        ("de", "cedar"),
        ("es", "cedar"),
        (" IT ", "marin"),
        ("ES", "cedar"),
    ),
)
def test_video_voice_for_language_enforces_policy(
    language: str,
    expected_voice: str,
) -> None:
    assert video_voice_for_language(language) == expected_voice


def test_voice_policy_has_one_mapping_and_derived_sets() -> None:
    assert dict(VIDEO_VOICE_BY_LANGUAGE) == {
        "it": "marin",
        "en": "cedar",
        "fr": "cedar",
        "de": "cedar",
        "es": "cedar",
    }
    assert SUPPORTED_VIDEO_LANGUAGES == frozenset(VIDEO_VOICE_BY_LANGUAGE)
    assert APPROVED_VIDEO_VOICES == frozenset(VIDEO_VOICE_BY_LANGUAGE.values())
    assert APPROVED_VIDEO_VOICES == {"marin", "cedar"}


def test_video_voice_for_language_rejects_unsupported_language() -> None:
    with pytest.raises(ValueError, match="Unsupported video language"):
        video_voice_for_language("pt")


@pytest.mark.parametrize(
    ("language", "expected_voice"),
    (
        ("it", "marin"),
        ("en", "cedar"),
        ("fr", "cedar"),
        ("de", "cedar"),
        ("es", "cedar"),
    ),
)
def test_speech_request_uses_central_model_and_voice_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    language: str,
    expected_voice: str,
) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"RIFF-test"

    def fake_urlopen(request: object, *, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    output_path = tmp_path / f"{language}.wav"
    monkeypatch.setattr(renderer.urllib.request, "urlopen", fake_urlopen)

    renderer._request_openai_speech(
        api_key="test-key",
        language=language,
        text="Test narration.",
        output_path=output_path,
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["model"] == OPENAI_VIDEO_TTS_MODEL
    assert payload["voice"] == expected_voice
    assert captured["timeout"] == 240
    assert output_path.read_bytes() == b"RIFF-test"


def test_speech_request_retries_transient_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts = 0
    delays: list[float] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"RIFF-recovered"

    def flaky_urlopen(_request: object, *, timeout: int) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        assert timeout == 240
        if attempts < 3:
            raise HTTPError(
                renderer.OPENAI_SPEECH_ENDPOINT,
                429 if attempts == 1 else 503,
                "transient",
                hdrs=None,
                fp=None,
            )
        return FakeResponse()

    monkeypatch.setattr(renderer.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(renderer.time, "sleep", delays.append)
    output_path = tmp_path / "recovered.wav"

    renderer._request_openai_speech(
        api_key="test-key",
        language="it",
        text="Test narration.",
        output_path=output_path,
    )

    assert attempts == 3
    assert delays == [1.0, 2.0]
    assert output_path.read_bytes() == b"RIFF-recovered"


def test_speech_request_stops_after_bounded_url_error_retries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts = 0
    delays: list[float] = []
    api_key = "secret-key-that-must-not-appear"
    narration = "Private narration that must not appear"

    def failing_urlopen(_request: object, *, timeout: int) -> None:
        nonlocal attempts
        attempts += 1
        assert timeout == 240
        raise URLError("temporary DNS failure")

    monkeypatch.setattr(renderer.urllib.request, "urlopen", failing_urlopen)
    monkeypatch.setattr(renderer.time, "sleep", delays.append)

    with pytest.raises(RuntimeError, match="failed after 4 attempts") as exc_info:
        renderer._request_openai_speech(
            api_key=api_key,
            language="en",
            text=narration,
            output_path=tmp_path / "failed.wav",
        )

    assert attempts == renderer.TTS_MAX_ATTEMPTS
    assert delays == [1.0, 2.0, 4.0]
    assert api_key not in str(exc_info.value)
    assert narration not in str(exc_info.value)


def test_speech_request_does_not_retry_non_transient_http_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    attempts = 0
    delays: list[float] = []

    def rejected_urlopen(_request: object, *, timeout: int) -> None:
        nonlocal attempts
        attempts += 1
        assert timeout == 240
        raise HTTPError(
            renderer.OPENAI_SPEECH_ENDPOINT,
            400,
            "bad request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(renderer.urllib.request, "urlopen", rejected_urlopen)
    monkeypatch.setattr(renderer.time, "sleep", delays.append)

    with pytest.raises(RuntimeError, match="rejected with HTTP 400"):
        renderer._request_openai_speech(
            api_key="test-key",
            language="de",
            text="Test narration.",
            output_path=tmp_path / "rejected.wav",
        )

    assert attempts == 1
    assert delays == []


def test_tracked_video_builder_sources_exclude_apple_speech() -> None:
    assert VIDEO_BUILDER_SOURCES
    violations: list[str] = []
    for source_path in VIDEO_BUILDER_SOURCES:
        source = source_path.read_text(encoding="utf-8")
        if "/usr/bin/say" in source:
            violations.append(f"{source_path.relative_to(REPO_ROOT)}: /usr/bin/say")
        for match in APPLE_VOICE_PATTERN.finditer(source):
            violations.append(f"{source_path.relative_to(REPO_ROOT)}: {match.group(0)}")

    assert not violations, "Forbidden Apple narration found:\n" + "\n".join(violations)
