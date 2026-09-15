from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from modules.hosted_interviews import review_service


def _review(**options):
    return review_service.generate_interview_quality_review(
        api_key="synthetic-secret",
        record={"token_hash": "a" * 64, "language": "es"},
        completion={},
        events=[],
        dialog_turns=[],
        model="synthetic-model",
        **options,
    )


def test_review_service_injected_provider_preserves_request_controls() -> None:
    captured = {}

    def provider(request, timeout):
        captured.update(json.loads(request.data))
        captured["timeout"] = timeout
        return {"output_text": '{"summary":"Synthetic evidence review"}'}

    result = _review(provider=provider, timeout_seconds=7)

    assert result["summary"] == "Synthetic evidence review"
    assert result["model"] == "synthetic-model"
    assert captured["store"] is False
    assert captured["reasoning"] == {"effort": "medium"}
    assert captured["text"]["format"] == review_service.INTERVIEW_REVIEW_RESPONSE_FORMAT
    assert "Spanish" in captured["input"][0]["content"]
    assert captured["timeout"] == 7


def test_review_service_timeout_has_retryable_stage_without_sensitive_detail(
    monkeypatch,
) -> None:
    def timeout(*args, **kwargs):
        raise TimeoutError("sensitive request content")

    monkeypatch.setattr(review_service.urllib.request, "urlopen", timeout)

    with pytest.raises(review_service.ReviewProviderError) as caught:
        _review()

    assert caught.value.stage == "interview_quality_review"
    assert caught.value.category == "timeout"
    assert caught.value.retryable is True
    assert "sensitive request content" not in str(caught.value)


def test_review_service_provider_error_does_not_echo_client_body(monkeypatch) -> None:
    def reject(request, **kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "client-name",
            {},
            io.BytesIO(b"synthetic-secret and transcript"),
        )

    monkeypatch.setattr(review_service.urllib.request, "urlopen", reject)

    with pytest.raises(review_service.ReviewProviderError) as caught:
        _review()

    assert caught.value.category == "rate_limit"
    assert caught.value.status_code == 429
    assert caught.value.retryable is True
    assert "synthetic-secret" not in str(caught.value)
    assert "client-name" not in str(caught.value)


def test_review_service_import_does_not_initialize_http_adapter() -> None:
    repository = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from modules.hosted_interviews.review_service import generate_interview_quality_review; assert callable(generate_interview_quality_review); assert 'modules.hosted_interviews.api' not in sys.modules",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr


def test_partner_service_injected_provider_preserves_request_and_cleans_note() -> None:
    captured = {}

    def provider(request, timeout):
        captured.update(json.loads(request.data))
        captured["timeout"] = timeout
        return {"output_text": '{"whisper":"  Ask about ownership.  "}'}

    note = review_service.create_partner_whisper(
        api_key="synthetic-secret",
        prompt="Synthetic interview context",
        model="synthetic-model",
        provider=provider,
    )

    assert note == "Ask about ownership."
    assert captured == {
        "model": "synthetic-model",
        "input": "Synthetic interview context",
        "timeout": 8,
    }


def test_partner_service_timeout_identifies_partner_stage(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise TimeoutError("private provider detail")

    monkeypatch.setattr(review_service.urllib.request, "urlopen", timeout)

    with pytest.raises(review_service.ReviewProviderError) as caught:
        review_service.create_partner_whisper(
            api_key="synthetic-secret", prompt="Private prompt", model="synthetic-model"
        )

    assert caught.value.stage == "partner_whisper"
    assert caught.value.retryable is True
    assert "Private prompt" not in str(caught.value)
    assert "private provider detail" not in str(caught.value)
