"""Injectable Audio API transport with metadata-only operational failures."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable

__all__ = ["TranscriptionProviderError", "request_transcription"]
LOGGER = logging.getLogger(__name__)


class TranscriptionProviderError(RuntimeError):
    """Expose failure stage and retryability without provider response content."""

    def __init__(
        self, category: str, *, retryable: bool, status_code: int | None = None
    ) -> None:
        self.category = category
        self.retryable = retryable
        self.status_code = status_code
        status = f" HTTP {status_code}" if status_code is not None else ""
        super().__init__(
            f"Audio transcription failed:{status} {category}; retryable={retryable}"
        )


def request_transcription(
    request: urllib.request.Request,
    *,
    timeout_seconds: float,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute an injected multipart request; never include response bodies in errors."""
    client = opener or urllib.request.urlopen
    try:
        with client(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        category = (
            "rate_limit"
            if code == 429
            else (
                "authentication"
                if code in {401, 403}
                else "provider_error" if code >= 500 else "request_rejected"
            )
        )
        error = TranscriptionProviderError(
            category, retryable=code in {408, 429} or code >= 500, status_code=code
        )
        LOGGER.warning(
            "audio_transcription category=%s status=%s retryable=%s",
            error.category,
            code,
            error.retryable,
        )
        raise error from None
    except TimeoutError:
        raise TranscriptionProviderError("timeout", retryable=True) from None
    except urllib.error.URLError:
        raise TranscriptionProviderError("network", retryable=True) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TranscriptionProviderError("invalid_response", retryable=False) from None
    if not isinstance(payload, dict):
        raise TranscriptionProviderError("invalid_response", retryable=False)
    return payload
