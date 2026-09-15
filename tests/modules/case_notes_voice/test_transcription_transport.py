from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from modules.case_notes_voice.transcription_transport import (
    TranscriptionProviderError,
    request_transcription,
)


def test_transcription_transport_replays_success_without_network() -> None:
    request = urllib.request.Request("https://example.invalid/transcriptions")

    result = request_transcription(
        request,
        timeout_seconds=1,
        opener=lambda *args, **kwargs: io.BytesIO(
            b'{"text":"Reviewed synthetic transcript"}'
        ),
    )

    assert result == {"text": "Reviewed synthetic transcript"}


@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (401, "authentication", False),
        (429, "rate_limit", True),
        (500, "provider_error", True),
    ],
)
def test_transcription_transport_redacts_http_body_and_classifies_retry(
    status: int, category: str, retryable: bool, caplog: pytest.LogCaptureFixture
) -> None:
    request = urllib.request.Request("https://example.invalid/transcriptions")

    def reject(*args, **kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            status,
            "sensitive-client-text",
            {},
            io.BytesIO(b"credential-and-client-content"),
        )

    with pytest.raises(TranscriptionProviderError) as caught:
        request_transcription(request, timeout_seconds=1, opener=reject)

    assert caught.value.category == category
    assert caught.value.retryable is retryable
    assert "credential-and-client-content" not in str(caught.value) + caplog.text
    assert "sensitive-client-text" not in str(caught.value) + caplog.text


def test_transcription_transport_timeout_is_replayable() -> None:
    def timeout(*args, **kwargs):
        raise TimeoutError("sensitive network details")

    with pytest.raises(TranscriptionProviderError) as caught:
        request_transcription(
            urllib.request.Request("https://example.invalid"),
            timeout_seconds=1,
            opener=timeout,
        )

    assert caught.value.category == "timeout"
    assert caught.value.retryable is True
    assert "sensitive network details" not in str(caught.value)


def test_transcription_transport_rejects_nonobject_json() -> None:
    with pytest.raises(TranscriptionProviderError, match="invalid_response"):
        request_transcription(
            urllib.request.Request("https://example.invalid"),
            timeout_seconds=1,
            opener=lambda *args, **kwargs: io.BytesIO(b"[]"),
        )
