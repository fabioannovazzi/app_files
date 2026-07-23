"""Upload an existing audio recording to hosted Clara and import the bundle."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import logging
import math
import mimetypes
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Mapping

from advisor_case_core import (
    SUPPORTED_LANGUAGES,
    CaseWorkspaceError,
    load_case_file,
    refresh_case_brief,
    validate_case_workspace,
)
from import_hosted_voice_bundle import (
    HostedVoiceImportResult,
    import_hosted_voice_bundle,
)
from launch_hosted_voice import (
    MAX_CASE_CONTEXT_CHARS,
    build_case_context,
    read_private_text_file,
    validate_hosted_url,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "HostedAudioUploadResult",
    "authenticate_with_magic_link",
    "authenticate_with_session_cookie",
    "bind_session_cookie",
    "build_source_metadata",
    "poll_upload_job",
    "request_context_launch_token",
    "request_magic_link",
    "upload_audio_file",
    "upload_hosted_audio",
    "main",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mparanza.com"
DEFAULT_LANGUAGE = "it"
UPLOAD_COPY_BLOCK_BYTES = 1024 * 1024
CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024
RETRYABLE_CHUNKED_UPLOAD_STATUS_CODES = {408, 413, 429, 502, 503, 504}
DEFAULT_POLL_SECONDS = 60 * 60
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0


@dataclass(frozen=True)
class HostedAudioUploadResult:
    """Files created by a hosted audio upload run."""

    run_dir: Path
    bundle_path: Path
    upload_response_path: Path
    final_job_payload_path: Path
    import_result: HostedVoiceImportResult | None


@dataclass(frozen=True)
class JsonResponse:
    """Small HTTP response wrapper used by the hosted audio client."""

    status_code: int
    payload: dict[str, Any]


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_base_url(base_url: str) -> str:
    clean = validate_hosted_url(base_url)
    parts = urllib.parse.urlsplit(clean)
    if parts.path not in {"", "/"}:
        raise CaseWorkspaceError("Hosted Voice base URL must not contain a path.")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects away from the pinned Hosted Voice origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_hosted_url(newurl, allow_query=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _new_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        _PinnedRedirectHandler(),
    )


def _read_json_response(
    opener: urllib.request.OpenerDirector,
    request: urllib.request.Request,
    *,
    timeout_seconds: float,
) -> JsonResponse:
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return JsonResponse(
                status_code=response.status,
                payload=json.loads(body) if body.strip() else {},
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            payload = {"detail": body[:1_000] or str(exc)}
        return JsonResponse(status_code=exc.code, payload=payload)
    except (OSError, urllib.error.URLError) as exc:
        raise CaseWorkspaceError(f"hosted audio request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CaseWorkspaceError("hosted audio response was not valid JSON") from exc


def _extract_magic_link(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise CaseWorkspaceError("missing mparanza magic link")
    match = re.search(
        r"https://mparanza\.com/auth/magic/consume\?token=[^)\s]+",
        clean,
    )
    magic_link = match.group(0) if match else clean
    validate_hosted_url(
        magic_link,
        required_path="/auth/magic/consume",
        allow_query=True,
    )
    token = urllib.parse.parse_qs(urllib.parse.urlsplit(magic_link).query).get(
        "token", [""]
    )[0]
    if not token:
        raise CaseWorkspaceError("invalid mparanza magic link")
    return magic_link


def _launch_token_from_url(final_url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(final_url).query).get(
        "session",
        [""],
    )[0]


def _refresh_case_context_sources(case_dir: Path, purpose: str) -> None:
    """Refresh derived local context files before the authenticated upload."""

    refresh_case_brief(case_dir)


def _request_launch_token(
    opener: urllib.request.OpenerDirector,
    launch_url: str,
    *,
    action: str,
    timeout_seconds: float,
) -> str:
    validate_hosted_url(
        launch_url,
        required_path="/case-notes/voice/launch",
    )
    request = urllib.request.Request(launch_url, method="GET")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise CaseWorkspaceError(f"{action} failed: {exc}") from exc
    validate_hosted_url(
        final_url,
        required_path="/case-notes/voice",
        allow_query=True,
    )
    launch_token = _launch_token_from_url(final_url)
    if not launch_token:
        raise CaseWorkspaceError(f"{action} did not return a Clara launch token")
    return launch_token


def _cookie_jar(opener: urllib.request.OpenerDirector) -> http.cookiejar.CookieJar:
    for handler in opener.handlers:
        if isinstance(handler, urllib.request.HTTPCookieProcessor):
            return handler.cookiejar
    raise CaseWorkspaceError("hosted audio client has no origin-bound cookie jar")


def bind_session_cookie(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str,
    cookie_header: str,
) -> None:
    """Bind supplied cookies to the validated Hosted Voice origin."""

    normalized_base_url = _normalize_base_url(base_url)
    parts = urllib.parse.urlsplit(normalized_base_url)
    clean = re.sub(r"^\s*cookie\s*:\s*", "", cookie_header, flags=re.IGNORECASE).strip()
    if not clean:
        raise CaseWorkspaceError("missing mparanza cookie header")
    parsed = SimpleCookie()
    parsed.load(clean)
    if not parsed:
        raise CaseWorkspaceError("invalid mparanza cookie header")
    jar = _cookie_jar(opener)
    jar.clear()
    for name, morsel in parsed.items():
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=name,
                value=morsel.value,
                port=None,
                port_specified=False,
                domain=parts.hostname or "",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": None},
                rfc2109=False,
            )
        )


def request_context_launch_token(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str,
    case_context: str,
    language: str = DEFAULT_LANGUAGE,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> str:
    """Send case context in an authenticated HTTPS body and return an opaque token."""

    request = urllib.request.Request(
        f"{_normalize_base_url(base_url)}/case-notes/api/voice/launch",
        data=_json_bytes({"case_context": case_context, "language": language}),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    response = _read_json_response(opener, request, timeout_seconds=timeout_seconds)
    if response.status_code != 200:
        detail = response.payload.get("detail") or response.payload
        raise CaseWorkspaceError(f"hosted voice context launch failed: {detail}")
    launch_token = str(response.payload.get("launch_token", "")).strip()
    if not launch_token or not re.fullmatch(r"[A-Za-z0-9_-]+", launch_token):
        raise CaseWorkspaceError("hosted voice context launch returned no valid token")
    return launch_token


def request_magic_link(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str = DEFAULT_BASE_URL,
    email: str,
    redirect_path: str = "/case-notes/voice/launch",
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> None:
    """Ask mparanza to email a one-time magic link."""

    request = urllib.request.Request(
        f"{_normalize_base_url(base_url)}/auth/magic/request",
        data=_json_bytes({"email": email, "redirect_path": redirect_path}),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    response = _read_json_response(opener, request, timeout_seconds=timeout_seconds)
    if response.status_code != 200:
        detail = response.payload.get("detail") or response.payload
        raise CaseWorkspaceError(f"magic link request failed: {detail}")


def authenticate_with_magic_link(
    opener: urllib.request.OpenerDirector,
    magic_link: str,
    *,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> str:
    """Consume a mparanza magic link and return a Clara launch token."""

    request = urllib.request.Request(_extract_magic_link(magic_link), method="GET")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise CaseWorkspaceError(f"magic link login failed: {exc}") from exc
    validate_hosted_url(final_url, allow_query=True)
    launch_token = _launch_token_from_url(final_url)
    if not launch_token:
        raise CaseWorkspaceError("magic link login did not return a Clara launch token")
    return launch_token


def authenticate_with_session_cookie(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str = DEFAULT_BASE_URL,
    cookie_header: str,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> str:
    """Use an existing mparanza session cookie to return a Clara launch token."""

    bind_session_cookie(
        opener,
        base_url=base_url,
        cookie_header=cookie_header,
    )
    return _request_launch_token(
        opener,
        f"{_normalize_base_url(base_url)}/case-notes/voice/launch",
        action="session cookie launch",
        timeout_seconds=timeout_seconds,
    )


def build_source_metadata(
    *,
    source_type: str = "",
    title: str = "",
    interview_date: str = "",
    participants: str = "",
    interviewer: str = "",
    notes: str = "",
) -> dict[str, str]:
    """Return source metadata accepted by the hosted Clara audio endpoint."""

    values = {
        "source_type": source_type,
        "title": title,
        "interview_date": interview_date,
        "participants": participants,
        "interviewer": interviewer,
        "notes": notes,
    }
    return {
        key: str(value).strip() for key, value in values.items() if str(value).strip()
    }


def _guess_audio_content_type(audio_path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(str(audio_path))
    return guessed or "application/octet-stream"


def _write_multipart_line(handle: Any, value: str) -> None:
    handle.write(value.encode("utf-8"))


def _write_multipart_fields(
    handle: Any,
    *,
    boundary: str,
    fields: Mapping[str, str],
) -> None:
    for name, value in fields.items():
        _write_multipart_line(handle, f"--{boundary}\r\n")
        _write_multipart_line(
            handle,
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n',
        )
        handle.write(value.encode("utf-8"))
        _write_multipart_line(handle, "\r\n")


def _copy_file_bytes(
    *,
    source_handle: Any,
    output_handle: Any,
    byte_count: int | None,
) -> int:
    copied = 0
    while byte_count is None or copied < byte_count:
        read_size = UPLOAD_COPY_BLOCK_BYTES
        if byte_count is not None:
            read_size = min(read_size, byte_count - copied)
        if read_size <= 0:
            break
        data = source_handle.read(read_size)
        if not data:
            break
        output_handle.write(data)
        copied += len(data)
    return copied


def _write_multipart_audio_field(
    handle: Any,
    *,
    boundary: str,
    field_name: str,
    filename: str,
    audio_path: Path,
    audio_content_type: str,
    offset: int = 0,
    byte_count: int | None = None,
) -> None:
    _write_multipart_line(handle, f"--{boundary}\r\n")
    _write_multipart_line(
        handle,
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        ),
    )
    _write_multipart_line(handle, f"Content-Type: {audio_content_type}\r\n\r\n")
    with audio_path.open("rb") as audio_handle:
        if offset:
            audio_handle.seek(offset)
        copied = _copy_file_bytes(
            source_handle=audio_handle,
            output_handle=handle,
            byte_count=byte_count,
        )
    if byte_count is not None and copied != byte_count:
        raise CaseWorkspaceError("audio file ended while preparing upload chunk")
    _write_multipart_line(handle, "\r\n")


def _write_multipart_upload_body(
    *,
    body_path: Path,
    boundary: str,
    fields: Mapping[str, str],
    audio_path: Path,
    audio_content_type: str,
) -> int:
    """Write a multipart upload body to disk without loading audio into memory."""

    with body_path.open("wb") as handle:
        _write_multipart_fields(handle, boundary=boundary, fields=fields)
        _write_multipart_audio_field(
            handle,
            boundary=boundary,
            field_name="audio",
            filename=audio_path.name,
            audio_path=audio_path,
            audio_content_type=audio_content_type,
        )
        _write_multipart_line(handle, f"--{boundary}--\r\n")
    return body_path.stat().st_size


def _write_multipart_chunk_body(
    *,
    body_path: Path,
    boundary: str,
    chunk_index: int,
    audio_path: Path,
    audio_content_type: str,
    offset: int,
    byte_count: int,
) -> int:
    """Write one audio chunk multipart body to disk."""

    with body_path.open("wb") as handle:
        _write_multipart_fields(
            handle,
            boundary=boundary,
            fields={"chunk_index": str(chunk_index)},
        )
        _write_multipart_audio_field(
            handle,
            boundary=boundary,
            field_name="audio",
            filename=f"{audio_path.name}.part-{chunk_index + 1}",
            audio_path=audio_path,
            audio_content_type=audio_content_type,
            offset=offset,
            byte_count=byte_count,
        )
        _write_multipart_line(handle, f"--{boundary}--\r\n")
    return body_path.stat().st_size


def _read_response_detail(response: JsonResponse) -> Any:
    return response.payload.get("detail") or response.payload


def _raise_unexpected_response(response: JsonResponse, action: str) -> None:
    detail = _read_response_detail(response)
    raise CaseWorkspaceError(f"{action} failed ({response.status_code}): {detail}")


def _should_retry_upload_as_chunks(
    *,
    audio_size_bytes: int,
    response: JsonResponse | None = None,
    error: CaseWorkspaceError | None = None,
) -> bool:
    if audio_size_bytes <= CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES:
        return False
    if response is not None:
        return response.status_code in RETRYABLE_CHUNKED_UPLOAD_STATUS_CODES
    return error is not None


def _submit_single_audio_upload(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str,
    fields: Mapping[str, str],
    audio_path: Path,
    audio_content_type: str,
    timeout_seconds: float,
) -> JsonResponse:
    boundary = f"clara-hosted-audio-{_now_compact()}"
    with tempfile.TemporaryDirectory(prefix="clara-hosted-upload-") as temp_dir_name:
        body_path = Path(temp_dir_name) / "upload.multipart"
        body_size = _write_multipart_upload_body(
            body_path=body_path,
            boundary=boundary,
            fields=fields,
            audio_path=audio_path,
            audio_content_type=audio_content_type,
        )
        with body_path.open("rb") as body_handle:
            request = urllib.request.Request(
                f"{_normalize_base_url(base_url)}/case-notes/api/voice/upload",
                data=body_handle,
                method="POST",
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(body_size),
                },
            )
            return _read_json_response(
                opener,
                request,
                timeout_seconds=timeout_seconds,
            )


def _post_multipart_body(
    opener: urllib.request.OpenerDirector,
    *,
    url: str,
    body_path: Path,
    boundary: str,
    body_size: int,
    timeout_seconds: float,
) -> JsonResponse:
    with body_path.open("rb") as body_handle:
        request = urllib.request.Request(
            url,
            data=body_handle,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(body_size),
            },
        )
        return _read_json_response(
            opener,
            request,
            timeout_seconds=timeout_seconds,
        )


def _submit_chunked_audio_upload(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str,
    fields: Mapping[str, str],
    audio_path: Path,
    audio_content_type: str,
    audio_size_bytes: int,
    timeout_seconds: float,
) -> JsonResponse:
    total_chunks = math.ceil(audio_size_bytes / CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES)
    start_fields = {
        **fields,
        "filename": audio_path.name or "audio-upload",
        "content_type": audio_content_type,
        "total_bytes": str(audio_size_bytes),
        "total_chunks": str(total_chunks),
    }
    normalized_base_url = _normalize_base_url(base_url)
    with tempfile.TemporaryDirectory(prefix="clara-hosted-upload-chunks-") as temp_dir:
        temp_dir_path = Path(temp_dir)
        start_boundary = f"clara-hosted-audio-start-{_now_compact()}"
        start_body_path = temp_dir_path / "start.multipart"
        with start_body_path.open("wb") as start_handle:
            _write_multipart_fields(
                start_handle,
                boundary=start_boundary,
                fields=start_fields,
            )
            _write_multipart_line(start_handle, f"--{start_boundary}--\r\n")
        start_response = _post_multipart_body(
            opener,
            url=f"{normalized_base_url}/case-notes/api/voice/upload/chunks/start",
            body_path=start_body_path,
            boundary=start_boundary,
            body_size=start_body_path.stat().st_size,
            timeout_seconds=timeout_seconds,
        )
        if start_response.status_code != 201:
            _raise_unexpected_response(start_response, "chunked audio upload start")
        upload_id = str(start_response.payload.get("upload_id", "")).strip()
        if not upload_id:
            raise CaseWorkspaceError("chunked audio upload did not return an upload id")
        chunk_size = int(
            start_response.payload.get("chunk_size") or CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES
        )
        for chunk_index in range(total_chunks):
            offset = chunk_index * chunk_size
            byte_count = min(chunk_size, audio_size_bytes - offset)
            chunk_boundary = f"clara-hosted-audio-part-{chunk_index}-{_now_compact()}"
            chunk_body_path = temp_dir_path / f"chunk-{chunk_index:06d}.multipart"
            chunk_body_size = _write_multipart_chunk_body(
                body_path=chunk_body_path,
                boundary=chunk_boundary,
                chunk_index=chunk_index,
                audio_path=audio_path,
                audio_content_type=audio_content_type,
                offset=offset,
                byte_count=byte_count,
            )
            chunk_response = _post_multipart_body(
                opener,
                url=(
                    f"{normalized_base_url}/case-notes/api/voice/upload/chunks/"
                    f"{urllib.parse.quote(upload_id, safe='')}"
                ),
                body_path=chunk_body_path,
                boundary=chunk_boundary,
                body_size=chunk_body_size,
                timeout_seconds=timeout_seconds,
            )
            if chunk_response.status_code != 200:
                _raise_unexpected_response(
                    chunk_response,
                    f"chunked audio upload part {chunk_index + 1}",
                )
            chunk_body_path.unlink(missing_ok=True)
        finish_request = urllib.request.Request(
            (
                f"{normalized_base_url}/case-notes/api/voice/upload/chunks/"
                f"{urllib.parse.quote(upload_id, safe='')}/finish"
            ),
            method="POST",
        )
        finish_response = _read_json_response(
            opener,
            finish_request,
            timeout_seconds=timeout_seconds,
        )
        if finish_response.status_code != 202:
            _raise_unexpected_response(finish_response, "chunked audio upload finish")
        return finish_response


def upload_audio_file(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str = DEFAULT_BASE_URL,
    launch_token: str,
    case_context: str = "",
    audio_path: Path,
    source_metadata: Mapping[str, str],
    language: str = DEFAULT_LANGUAGE,
    audio_content_type: str | None = None,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Upload one audio file to the hosted Clara transcription endpoint."""

    source_path = audio_path.expanduser()
    if not source_path.is_file():
        raise CaseWorkspaceError(f"audio file does not exist: {source_path}")
    audio_size_bytes = source_path.stat().st_size
    content_type = audio_content_type or _guess_audio_content_type(source_path)
    fields = {
        "launch_token": launch_token,
        "language": language,
        "case_context": case_context,
        "source_metadata_json": json.dumps(dict(source_metadata), ensure_ascii=False),
    }
    try:
        response = _submit_single_audio_upload(
            opener,
            base_url=base_url,
            fields=fields,
            audio_path=source_path,
            audio_content_type=content_type,
            timeout_seconds=timeout_seconds,
        )
    except CaseWorkspaceError as exc:
        if not _should_retry_upload_as_chunks(
            audio_size_bytes=audio_size_bytes,
            error=exc,
        ):
            raise
        LOGGER.info("Single hosted upload failed; retrying in upload parts: %s", exc)
        response = _submit_chunked_audio_upload(
            opener,
            base_url=base_url,
            fields=fields,
            audio_path=source_path,
            audio_content_type=content_type,
            audio_size_bytes=audio_size_bytes,
            timeout_seconds=timeout_seconds,
        )
    if _should_retry_upload_as_chunks(
        audio_size_bytes=audio_size_bytes,
        response=response,
    ):
        LOGGER.info(
            "Single hosted upload returned %s; retrying in upload parts.",
            response.status_code,
        )
        response = _submit_chunked_audio_upload(
            opener,
            base_url=base_url,
            fields=fields,
            audio_path=source_path,
            audio_content_type=content_type,
            audio_size_bytes=audio_size_bytes,
            timeout_seconds=timeout_seconds,
        )
    if response.status_code != 202:
        _raise_unexpected_response(response, "hosted audio upload")
    return response.payload


def poll_upload_job(
    opener: urllib.request.OpenerDirector,
    *,
    base_url: str = DEFAULT_BASE_URL,
    job_id: str,
    run_dir: Path,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Poll a hosted Clara upload job until it completes or fails."""

    deadline = time.monotonic() + poll_seconds
    latest_payload: dict[str, Any] = {}
    last_progress_key: tuple[Any, ...] | None = None
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"{_normalize_base_url(base_url)}/case-notes/api/voice/upload/{job_id}",
            method="GET",
        )
        response = _read_json_response(opener, request, timeout_seconds=timeout_seconds)
        latest_payload = response.payload
        (run_dir / "latest_job_payload.json").write_text(
            json.dumps(latest_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if response.status_code != 200:
            _raise_unexpected_response(response, "hosted audio job poll")
        progress_key = (
            latest_payload.get("status"),
            latest_payload.get("phase") or latest_payload.get("phase_label"),
            latest_payload.get("progress_percent"),
            latest_payload.get("message"),
        )
        if progress_key != last_progress_key:
            LOGGER.info(
                "Job %s: status=%s phase=%s progress=%s message=%s",
                job_id,
                latest_payload.get("status"),
                latest_payload.get("phase") or latest_payload.get("phase_label"),
                latest_payload.get("progress_percent"),
                latest_payload.get("message"),
            )
            last_progress_key = progress_key
        if latest_payload.get("status") in {"done", "error"}:
            return latest_payload
        time.sleep(poll_interval_seconds)
    raise CaseWorkspaceError(f"hosted audio job timed out after {poll_seconds} seconds")


def upload_hosted_audio(
    *,
    case_dir: Path,
    audio_path: Path,
    magic_link: str = "",
    cookie_header: str = "",
    output_dir: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    source_metadata: Mapping[str, str] | None = None,
    language: str | None = None,
    include_case_context: bool = True,
    max_context_chars: int = MAX_CASE_CONTEXT_CHARS,
    import_bundle: bool = True,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> HostedAudioUploadResult:
    """Upload through an authenticated hosted session and optionally import."""

    errors = validate_case_workspace(case_dir)
    ordinary_folder_upload = (
        not include_case_context
        and not import_bundle
        and not (case_dir / "case_manifest.json").exists()
    )
    if errors and not ordinary_folder_upload:
        raise CaseWorkspaceError("; ".join(errors))
    manifest = {} if ordinary_folder_upload else load_case_file(case_dir, "manifest")
    resolved_language = (
        str(language or manifest.get("output_language") or DEFAULT_LANGUAGE)
        .strip()
        .lower()
    )
    if resolved_language not in SUPPORTED_LANGUAGES:
        raise CaseWorkspaceError(f"Unsupported voice language: {resolved_language}")
    source_path = audio_path.expanduser()
    if not source_path.is_file():
        raise CaseWorkspaceError(f"audio file does not exist: {source_path}")

    run_dir = output_dir or case_dir / "hosted_voice_uploads" / _now_compact()
    run_dir.mkdir(parents=True, exist_ok=True)
    normalized_base_url = _normalize_base_url(base_url)
    opener = _new_opener()
    case_context = ""
    if include_case_context:
        _refresh_case_context_sources(case_dir, "transcription")
        case_context = build_case_context(
            case_dir,
            max_chars=max_context_chars,
            purpose="transcription",
        )
    if cookie_header:
        resolved_launch_token = authenticate_with_session_cookie(
            opener,
            base_url=normalized_base_url,
            cookie_header=cookie_header,
            timeout_seconds=timeout_seconds,
        )
    elif magic_link:
        resolved_launch_token = authenticate_with_magic_link(
            opener,
            magic_link,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise CaseWorkspaceError(
            "provide --magic-link-file, --request-magic-link, or "
            "--cookie-header-file"
        )
    metadata = dict(source_metadata or {})
    if not metadata.get("title"):
        metadata["title"] = source_path.stem

    upload_payload = upload_audio_file(
        opener,
        base_url=normalized_base_url,
        launch_token=resolved_launch_token,
        case_context=case_context,
        audio_path=source_path,
        source_metadata=metadata,
        language=resolved_language,
        timeout_seconds=timeout_seconds,
    )
    upload_response_path = run_dir / "upload_response.json"
    upload_response_path.write_text(
        json.dumps(upload_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    job_id = str(upload_payload.get("job_id", "")).strip()
    if not job_id:
        raise CaseWorkspaceError("hosted audio upload did not return a job id")

    final_payload = poll_upload_job(
        opener,
        base_url=normalized_base_url,
        job_id=job_id,
        run_dir=run_dir,
        poll_seconds=poll_seconds,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    final_job_payload_path = run_dir / "final_job_payload.json"
    final_job_payload_path.write_text(
        json.dumps(final_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if final_payload.get("status") != "done":
        raise CaseWorkspaceError(str(final_payload.get("message") or final_payload))
    bundle = final_payload.get("bundle")
    if not isinstance(bundle, Mapping):
        raise CaseWorkspaceError("completed hosted audio job did not return a bundle")
    bundle_path = run_dir / "bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    import_result = (
        import_hosted_voice_bundle(
            case_dir,
            bundle_path,
            title=str(metadata.get("title") or "Hosted audio upload"),
            companion_audio_path=source_path,
        )
        if import_bundle
        else None
    )
    return HostedAudioUploadResult(
        run_dir=run_dir,
        bundle_path=bundle_path,
        upload_response_path=upload_response_path,
        final_job_payload_path=final_job_payload_path,
        import_result=import_result,
    )


def _magic_link_from_args(args: argparse.Namespace) -> str:
    if args.magic_link_file:
        return read_private_text_file(args.magic_link_file, label="magic link")
    if args.request_magic_link:
        opener = _new_opener()
        request_magic_link(
            opener,
            base_url=args.base_url,
            email=args.request_magic_link,
            redirect_path="/case-notes/voice/launch",
            timeout_seconds=args.timeout_seconds,
        )
        LOGGER.info(
            "Magic link requested for %s. Paste the received link below.",
            args.request_magic_link,
        )
        return input("Magic link: ")
    return ""


def _cookie_header_from_args(args: argparse.Namespace) -> str:
    if args.cookie_header_file:
        return read_private_text_file(
            args.cookie_header_file,
            label="session cookie",
        )
    return ""


def main() -> int:
    """Run the hosted existing-audio upload workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--magic-link-file", type=Path)
    parser.add_argument("--cookie-header-file", type=Path)
    parser.add_argument(
        "--request-magic-link",
        metavar="EMAIL",
        help="Request a magic link, then prompt for the emailed URL.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--no-import", action="store_true")
    parser.add_argument(
        "--language",
        choices=sorted(SUPPORTED_LANGUAGES),
        help="Transcription language; defaults to the Clara case output language.",
    )
    parser.add_argument(
        "--no-case-context",
        action="store_true",
        help="Do not send local Clara case context in the hosted upload body.",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=MAX_CASE_CONTEXT_CHARS,
        help="Maximum local case-context characters sent in the upload body.",
    )
    parser.add_argument("--source-type", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--interview-date", default="")
    parser.add_argument("--participants", default="")
    parser.add_argument("--interviewer", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    source_metadata = build_source_metadata(
        source_type=args.source_type,
        title=args.title,
        interview_date=args.interview_date,
        participants=args.participants,
        interviewer=args.interviewer,
        notes=args.notes,
    )
    result = upload_hosted_audio(
        case_dir=args.case_dir,
        audio_path=args.audio,
        magic_link=_magic_link_from_args(args),
        cookie_header=_cookie_header_from_args(args),
        output_dir=args.output_dir,
        base_url=args.base_url,
        source_metadata=source_metadata,
        language=args.language,
        include_case_context=not args.no_case_context,
        max_context_chars=args.max_context_chars,
        import_bundle=not args.no_import,
        poll_seconds=args.poll_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    LOGGER.info("Hosted upload run: %s", result.run_dir)
    LOGGER.info("Bundle JSON: %s", result.bundle_path)
    if result.import_result is not None:
        LOGGER.info("Transcript material: %s", result.import_result.material_id)
        LOGGER.info("Session folder: %s", result.import_result.session_dir)
        if result.import_result.audio_path is not None:
            LOGGER.info("Audio file: %s", result.import_result.audio_path)
    else:
        LOGGER.info("Bundle saved but not imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
