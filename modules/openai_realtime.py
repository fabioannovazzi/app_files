from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "DEFAULT_REALTIME_ENDPOINT",
    "DEFAULT_REALTIME_MODEL",
    "DEFAULT_REALTIME_TRANSCRIPTION_MODEL",
    "OpenAIRealtimeError",
    "RealtimeCallResult",
    "create_realtime_call",
    "create_realtime_call_with_metadata",
]

DEFAULT_REALTIME_MODEL = "gpt-realtime-2.1"
DEFAULT_REALTIME_TRANSCRIPTION_MODEL = "gpt-realtime-whisper"
DEFAULT_REALTIME_ENDPOINT = "https://api.openai.com/v1/realtime/calls"


class OpenAIRealtimeError(RuntimeError):
    """Raised when an OpenAI Realtime WebRTC call cannot be created."""


@dataclass(frozen=True)
class RealtimeCallResult:
    """SDP answer plus server-side control metadata for a Realtime call."""

    sdp: str
    call_id: str = ""


def _multipart_form_data(
    fields: Mapping[str, str],
    *,
    boundary: str = "----mparanza-realtime-boundary",
) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (f'Content-Disposition: form-data; name="{name}"\r\n\r\n').encode(
                    "utf-8"
                ),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def create_realtime_call(
    *,
    api_key: str,
    sdp: str,
    session_config: Mapping[str, Any],
    endpoint: str = DEFAULT_REALTIME_ENDPOINT,
    safety_identifier: str = "mparanza-realtime-user",
    timeout_seconds: float = 30,
) -> str:
    """Create an OpenAI Realtime WebRTC call and return the SDP answer."""

    return create_realtime_call_with_metadata(
        api_key=api_key,
        sdp=sdp,
        session_config=session_config,
        endpoint=endpoint,
        safety_identifier=safety_identifier,
        timeout_seconds=timeout_seconds,
    ).sdp


def create_realtime_call_with_metadata(
    *,
    api_key: str,
    sdp: str,
    session_config: Mapping[str, Any],
    endpoint: str = DEFAULT_REALTIME_ENDPOINT,
    safety_identifier: str = "mparanza-realtime-user",
    timeout_seconds: float = 30,
) -> RealtimeCallResult:
    """Create an OpenAI Realtime WebRTC call and return SDP plus call id."""

    body, boundary = _multipart_form_data(
        {"sdp": sdp, "session": json.dumps(session_config)}
    )
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "OpenAI-Safety-Identifier": safety_identifier,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            location = response.headers.get("Location", "")
            call_id = location.rstrip("/").split("/")[-1] if location else ""
            return RealtimeCallResult(
                sdp=response.read().decode("utf-8"),
                call_id=call_id if call_id.startswith("rtc_") else "",
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OpenAIRealtimeError(
            f"Realtime session creation failed: HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OpenAIRealtimeError(f"Realtime session creation failed: {exc}") from exc
