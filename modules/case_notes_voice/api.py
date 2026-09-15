from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, BinaryIO, Callable, Mapping
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from modules.auth.dependencies import require_site_permission_for_request
from modules.auth.session import AuthenticatedUser
from modules.case_notes_voice.transcription_service import (
    DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
    MAX_CASE_CONTEXT_CHARS,
    SUPPORTED_TRANSCRIPTION_LANGUAGES,
    VoiceSessionError,
    _max_audio_upload_bytes,
    _normalize_case_context,
    _safe_upload_filename,
    _upload_too_large_message,
    _uploaded_audio_temp_suffix,
    _validate_audio_upload_metadata,
    create_audio_transcription,
)
from modules.openai_realtime import (
    DEFAULT_REALTIME_TRANSCRIPTION_MODEL,
    OpenAIRealtimeError,
    create_realtime_call_with_metadata,
)
from modules.utilities.cache import get_cache_dir
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = [
    "DEFAULT_UPLOAD_TRANSCRIPTION_MODEL",
    "VoiceSessionError",
    "create_audio_transcription",
    "start_voice_retention_cleanup",
    "stop_voice_retention_cleanup",
    "issue_voice_launch_token",
    "router",
    "site_router",
    "verify_voice_launch_token",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_LIVE_TRANSCRIPTION_DELAY = "low"
POST_TRANSCRIPTION_PROCESSING_NOTE = (
    "After transcription, local Clara/Codex must assign speaker attribution from "
    "the clean transcript and source metadata, check transcript quality against "
    "the document as a whole, and correct only obviously wrong transcription "
    "words when the intended wording is clear from the transcript context or "
    "trusted case glossary. Speaker attribution is a local text-only "
    "Codex/Clara loop: preserve the unattributed transcript, create a "
    "speaker-attributed working transcript, inspect for obvious merged turns or "
    "wrong labels, and correct only clear text-supported boundary errors. Do "
    "not use an audio or voice diarization model for Clara speaker attribution. "
    "Preserve uncertainty instead of guessing."
)
TOKEN_TTL_SECONDS = 8 * 60 * 60
VOICE_LAUNCH_TOKEN_BYTES = 32
# Keep a safety margin below OpenAI's 25 MB transcription file limit because the
# request includes multipart overhead and provider limits are decimal MB.
CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024
UPLOAD_COPY_BLOCK_BYTES = 1024 * 1024
MAX_UPLOAD_JOB_ERROR_CHARS = 2_000
UPLOAD_JOB_STALE_SECONDS = 24 * 60 * 60
UPLOAD_JOB_TERMINAL_STALE_SECONDS = 10 * 60
CHUNKED_UPLOAD_STALE_SECONDS = 24 * 60 * 60
VOICE_ORPHAN_STALE_SECONDS = 10 * 60
VOICE_RETENTION_CLEANUP_INTERVAL_SECONDS = 60
VOICE_RETENTION_LOCK_VERSION = 1
# These codes describe spoken audio, independently of Clara's report language.
SOURCE_METADATA_FIELDS = {
    "source_type",
    "title",
    "interview_date",
    "participants",
    "interviewer",
    "notes",
}
MAX_SOURCE_METADATA_VALUE_CHARS = 1_000
templates = Jinja2Templates(directory="templates")
site_router = APIRouter(prefix="/case-notes", tags=["case-notes-voice-site"])
router = APIRouter(prefix="/case-notes/api/voice", tags=["case-notes-voice"])
_VOICE_RETENTION_CLEANUP_STOP = threading.Event()
_VOICE_RETENTION_CLEANUP_THREAD: threading.Thread | None = None
_VOICE_RETENTION_CLEANUP_THREAD_LOCK = threading.Lock()
_ACTIVE_UPLOAD_JOB_IDS: set[str] = set()
_ACTIVE_UPLOAD_JOB_IDS_LOCK = threading.Lock()


class _VoiceJobInUseError(VoiceSessionError):
    """Raised when terminal cleanup must wait for the active job lock."""


class UploadedAudioBundle(BaseModel):
    """Downloaded local bundle generated from an uploaded audio file."""

    schema_version: int = 1
    source: str = "case_notes_hosted_voice"
    capture_source: str = "uploaded_audio"
    captured_at: str
    language: str = "it"
    source_metadata: dict[str, str] = Field(default_factory=dict)
    model: str
    transcription_model: str
    audio_file_name: str
    audio_content_type: str
    user_transcript: str
    raw_transcription_text: str = ""
    transcript_text_prompted: str = ""
    speaker_label_note: str = ""
    transcript_processing_note: str = ""
    assistant_transcript: str = ""
    extraction_text: str
    extraction_json: dict[str, Any]
    transcription_metadata: dict[str, Any] = Field(default_factory=dict)


class RealtimeTranscriptionSessionRequest(BaseModel):
    """Browser SDP offer for a live call transcription-only session."""

    launch_token: str = Field(..., min_length=1)
    sdp: str = Field(..., min_length=1)
    language: str = "it"


class VoiceLaunchRequest(BaseModel):
    """Case context supplied in an authenticated HTTPS request body."""

    case_context: str = Field(default="", max_length=MAX_CASE_CONTEXT_CHARS)
    language: str = "it"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_simple_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        clean_key = key.strip()
        value = raw_value.strip()
        if not clean_key or not value:
            continue
        if value.startswith(('"', "'")) and value.endswith(('"', "'")):
            value = value[1:-1]
        elif "#" in value:
            value = value.split("#", 1)[0].strip()
        if value:
            os.environ.setdefault(clean_key, value)


def _resolve_openai_api_key() -> str:
    load_env_from_secrets_file()
    _load_simple_env_file(_repo_root() / ".env")
    for key_name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "openAiKey"):
        api_key = os.getenv(key_name, "").strip()
        if api_key:
            return api_key
    raise VoiceSessionError("OpenAI API key is not configured on the server.")


def _safety_identifier(user: AuthenticatedUser | None) -> str:
    if user is None:
        return "case-notes-voice-local-dev"
    normalized = user.email.strip().lower().encode("utf-8")
    return "case-notes-voice-" + hashlib.sha256(normalized).hexdigest()[:32]


def _email_for_user(user: AuthenticatedUser | None) -> str:
    return "" if user is None else user.email.strip().lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _voice_launch_token_root() -> Path:
    configured_root = os.getenv("CASE_NOTES_VOICE_TOKEN_ROOT", "").strip()
    root = (
        Path(configured_root).expanduser().resolve()
        if configured_root
        else get_cache_dir("case_notes_voice_launch_tokens")
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def _voice_launch_token_path(token: str) -> Path:
    return _voice_launch_token_root() / f"{_token_hash(token)}.json"


def _write_voice_launch_token(token: str, payload: Mapping[str, Any]) -> None:
    path = _voice_launch_token_path(token)
    temp_path = path.with_name(f".{path.stem}.{secrets.token_hex(8)}.tmp")
    serialized = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
        path.chmod(0o600)
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        temp_path.unlink(missing_ok=True)
        raise


def _cleanup_expired_voice_launch_tokens(now: datetime | None = None) -> int:
    """Delete expired, corrupt, and abandoned Hosted Voice launch metadata."""

    timestamp = _utc_timestamp(now)
    removed = 0
    root = _voice_launch_token_root()
    for path in root.iterdir():
        if path.suffix == ".tmp":
            if _path_is_stale(
                path,
                now=timestamp,
                stale_seconds=VOICE_ORPHAN_STALE_SECONDS,
            ):
                removed += int(_remove_voice_file(path))
            continue
        if path.suffix != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = _parse_iso_timestamp(str(payload.get("expires_at", "")))
        except (OSError, AttributeError, TypeError, ValueError, json.JSONDecodeError):
            removed += int(_remove_voice_file(path))
            continue
        if expires_at <= timestamp:
            removed += int(_remove_voice_file(path))
    return removed


def _upload_job_root() -> Path:
    root = get_cache_dir("case_notes_voice_upload_jobs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _upload_job_path(job_id: str) -> Path:
    safe_job_id = "".join(
        char for char in job_id if char.isascii() and (char.isalnum() or char in "-_")
    )
    if not safe_job_id or safe_job_id != job_id:
        raise VoiceSessionError("Invalid upload job id.")
    return _upload_job_root() / f"{safe_job_id}.json"


def _write_upload_job(job_id: str, payload: Mapping[str, Any]) -> None:
    path = _upload_job_path(job_id)
    temp_path = path.with_suffix(".tmp")
    serialized = json.dumps(dict(payload), ensure_ascii=False, indent=2)
    try:
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(path)
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not delete interrupted Hosted Voice job write")
        raise


def _update_upload_job(job_id: str, updates: Mapping[str, Any]) -> None:
    path = _upload_job_path(job_id)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VoiceSessionError("Upload job state is corrupted.") from exc
        if isinstance(raw_payload, dict):
            payload.update(raw_payload)
    payload.update(dict(updates))
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_upload_job(job_id, payload)


def _read_upload_job(job_id: str, user: AuthenticatedUser | None) -> dict[str, Any]:
    path = _upload_job_path(job_id)
    if not path.exists():
        raise VoiceSessionError("Upload job was not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VoiceSessionError("Upload job state is corrupted.") from exc
    expected_email = "" if user is None else user.email.strip().lower()
    actual_email = str(payload.get("email", "")).strip().lower()
    if actual_email != expected_email:
        raise VoiceSessionError("Upload job does not belong to this user.")
    return payload


def _set_upload_job_active(job_id: str, *, active: bool) -> None:
    """Track upload jobs whose files are in use by this application process."""

    with _ACTIVE_UPLOAD_JOB_IDS_LOCK:
        if active:
            _ACTIVE_UPLOAD_JOB_IDS.add(job_id)
        else:
            _ACTIVE_UPLOAD_JOB_IDS.discard(job_id)


def _active_upload_job_ids() -> set[str]:
    """Return a snapshot of upload jobs currently processing in this process."""

    with _ACTIVE_UPLOAD_JOB_IDS_LOCK:
        return set(_ACTIVE_UPLOAD_JOB_IDS)


def _remove_voice_directory(
    path: Path,
    *,
    strict: bool = False,
) -> bool:
    """Remove one Hosted Voice directory and optionally fail closed."""

    if not path.exists():
        return False
    try:
        shutil.rmtree(path)
    except OSError as exc:
        if strict:
            raise VoiceSessionError(
                "Hosted Voice temporary data could not be deleted."
            ) from exc
        LOGGER.warning("Could not delete Hosted Voice temporary data: %s", exc)
        return False
    if strict and path.exists():
        raise VoiceSessionError("Hosted Voice temporary data could not be deleted.")
    return True


def _remove_voice_file(path: Path, *, strict: bool = False) -> bool:
    """Remove one Hosted Voice state file and optionally fail closed."""

    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError as exc:
        if strict:
            raise VoiceSessionError(
                "Hosted Voice transcript state could not be deleted."
            ) from exc
        LOGGER.warning("Could not delete Hosted Voice transcript state: %s", exc)
        return False
    if strict and path.exists():
        raise VoiceSessionError("Hosted Voice transcript state could not be deleted.")
    return True


def _delete_upload_job(
    job_id: str,
    *,
    strict: bool = False,
    lock_handle: BinaryIO | None = None,
) -> bool:
    """Delete all managed raw audio, work files, and transcript state for a job."""

    owned_lock: BinaryIO | None = None
    if lock_handle is None:
        try:
            owned_lock = _acquire_voice_job_lock(job_id, blocking=False)
        except OSError as exc:
            if strict:
                raise VoiceSessionError(
                    "Hosted Voice temporary data could not be locked for deletion."
                ) from exc
            LOGGER.warning("Could not lock Hosted Voice job %s for deletion", job_id)
            return False
        if owned_lock is None:
            if strict:
                raise _VoiceJobInUseError(
                    "Hosted Voice temporary data is still in use and was not deleted."
                )
            return False
        lock_handle = owned_lock

    removed = False
    deletion_error: VoiceSessionError | None = None
    try:
        job_path = _upload_job_path(job_id)
        sensitive_targets: tuple[tuple[Callable[..., bool], Path], ...] = (
            (_remove_voice_directory, _uploaded_audio_source_dir(job_id)),
            (_remove_voice_directory, _voice_work_dir(job_id)),
            (_remove_voice_file, job_path.with_suffix(".tmp")),
        )
        for remover, path in sensitive_targets:
            try:
                removed = remover(path, strict=strict) or removed
            except VoiceSessionError as exc:
                if deletion_error is None:
                    deletion_error = exc
        sensitive_state_remains = any(path.exists() for _, path in sensitive_targets)
        if deletion_error is None and not sensitive_state_remains:
            try:
                removed = _remove_voice_file(job_path, strict=strict) or removed
            except VoiceSessionError as exc:
                deletion_error = exc
    except OSError as exc:
        deletion_error = VoiceSessionError(
            "Hosted Voice temporary data could not be inspected for deletion."
        )
        LOGGER.warning("Could not inspect Hosted Voice job %s: %s", job_id, exc)
    finally:
        if owned_lock is not None:
            _release_voice_job_lock(owned_lock)

    if deletion_error is not None:
        if strict:
            raise deletion_error
        LOGGER.warning("Could not fully delete Hosted Voice job %s", job_id)
    return removed


def _utc_timestamp(now: datetime | None = None) -> datetime:
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _path_is_stale(path: Path, *, now: datetime, stale_seconds: int) -> bool:
    """Use the latest direct filesystem timestamp as a corrupt-state fallback."""

    try:
        latest_mtime = path.stat().st_mtime
        if path.is_dir():
            for child in path.iterdir():
                latest_mtime = max(latest_mtime, child.stat().st_mtime)
    except OSError:
        return False
    modified_at = datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
    return modified_at + timedelta(seconds=stale_seconds) <= now


def _payload_or_path_is_stale(
    payload: Mapping[str, Any],
    path: Path,
    *,
    now: datetime,
    stale_seconds: int,
) -> bool:
    for key in ("updated_at", "created_at"):
        value = payload.get(key)
        if not value:
            continue
        try:
            parsed = _parse_iso_timestamp(str(value))
        except (TypeError, ValueError):
            continue
        return parsed + timedelta(seconds=stale_seconds) <= now
    return _path_is_stale(path, now=now, stale_seconds=stale_seconds)


def _owner_process_is_alive(payload: Mapping[str, Any]) -> bool:
    try:
        owner_pid = int(payload.get("owner_pid", 0))
    except (TypeError, ValueError):
        return False
    if owner_pid <= 0:
        return False
    if owner_pid == os.getpid():
        return True
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _mark_stale_upload_jobs(now: datetime | None = None) -> int:
    """Remove terminal payloads and retire abandoned Hosted Voice jobs."""

    timestamp = _utc_timestamp(now)
    changed = 0
    active_job_ids = _active_upload_job_ids()
    for path in _upload_job_root().glob("*.json"):
        try:
            _upload_job_path(path.stem)
        except VoiceSessionError:
            if _path_is_stale(
                path,
                now=timestamp,
                stale_seconds=UPLOAD_JOB_TERMINAL_STALE_SECONDS,
            ) and _remove_voice_file(path):
                changed += 1
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if _path_is_stale(
                path,
                now=timestamp,
                stale_seconds=UPLOAD_JOB_TERMINAL_STALE_SECONDS,
            ) and _delete_upload_job(path.stem):
                changed += 1
            continue
        if not isinstance(payload, dict):
            if _path_is_stale(
                path,
                now=timestamp,
                stale_seconds=UPLOAD_JOB_TERMINAL_STALE_SECONDS,
            ) and _delete_upload_job(path.stem):
                changed += 1
            continue
        status_value = str(payload.get("status", "")).strip().lower()
        if status_value in {"done", "error"}:
            if _payload_or_path_is_stale(
                payload,
                path,
                now=timestamp,
                stale_seconds=UPLOAD_JOB_TERMINAL_STALE_SECONDS,
            ) and _delete_upload_job(path.stem):
                changed += 1
            continue
        if status_value not in {"queued", "running"}:
            if _path_is_stale(
                path,
                now=timestamp,
                stale_seconds=UPLOAD_JOB_STALE_SECONDS,
            ) and _delete_upload_job(path.stem):
                changed += 1
            continue
        job_id = path.stem
        if job_id in active_job_ids:
            continue
        is_managed_abandonment = (
            payload.get("retention_lock_version") == VOICE_RETENTION_LOCK_VERSION
        )
        owner_has_short_grace = _owner_process_is_alive(
            payload
        ) and not _payload_or_path_is_stale(
            payload,
            path,
            now=timestamp,
            stale_seconds=VOICE_ORPHAN_STALE_SECONDS,
        )
        if owner_has_short_grace:
            continue
        if not is_managed_abandonment and not _payload_or_path_is_stale(
            payload,
            path,
            now=timestamp,
            stale_seconds=UPLOAD_JOB_STALE_SECONDS,
        ):
            continue
        try:
            lock_handle = _acquire_voice_job_lock(job_id, blocking=False)
        except OSError:
            LOGGER.warning("Could not inspect Hosted Voice job lock: %s", job_id)
            continue
        if lock_handle is None:
            continue
        try:
            _remove_voice_directory(_uploaded_audio_source_dir(job_id))
            _remove_voice_directory(_voice_work_dir(job_id))
            _remove_voice_file(path.with_suffix(".tmp"))
            payload.pop("bundle", None)
            payload.pop("transcription_metadata", None)
            payload["status"] = "error"
            payload["previous_status"] = status_value
            payload["message"] = (
                "Uploaded audio transcription was interrupted or exceeded the "
                "server stale-job timeout. Its server-side files were deleted. "
                "Please upload the file again."
            )
            payload["updated_at"] = timestamp.isoformat()
            _write_upload_job(job_id, payload)
            changed += 1
        finally:
            _release_voice_job_lock(lock_handle)
    return changed


def _chunked_upload_root() -> Path:
    root = get_cache_dir("case_notes_voice_upload_chunks")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _uploaded_audio_source_root() -> Path:
    root = get_cache_dir("case_notes_voice_upload_sources")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _voice_work_root() -> Path:
    root = get_cache_dir("case_notes_voice_work")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _voice_lock_root() -> Path:
    root = get_cache_dir("case_notes_voice_locks")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_chunked_upload_id(upload_id: str) -> str:
    safe_upload_id = "".join(
        char
        for char in upload_id
        if char.isascii() and (char.isalnum() or char in "-_")
    )
    if not safe_upload_id or safe_upload_id != upload_id:
        raise VoiceSessionError("Invalid chunked upload id.")
    return safe_upload_id


def _chunked_upload_dir(upload_id: str) -> Path:
    return _chunked_upload_root() / _safe_chunked_upload_id(upload_id)


def _chunked_upload_metadata_path(upload_id: str) -> Path:
    return _chunked_upload_dir(upload_id) / "metadata.json"


def _chunked_upload_chunk_path(upload_id: str, chunk_index: int) -> Path:
    return _chunked_upload_dir(upload_id) / f"chunk-{chunk_index:06d}.part"


def _uploaded_audio_source_dir(job_id: str) -> Path:
    return _uploaded_audio_source_root() / _safe_chunked_upload_id(job_id)


def _uploaded_audio_source_path(job_id: str, filename: str) -> Path:
    return _uploaded_audio_source_dir(job_id) / (
        f"upload{_uploaded_audio_temp_suffix(filename)}"
    )


def _voice_work_dir(job_id: str) -> Path:
    return _voice_work_root() / _safe_chunked_upload_id(job_id)


def _voice_lock_path(job_id: str) -> Path:
    return _voice_lock_root() / f"{_safe_chunked_upload_id(job_id)}.lock"


def _acquire_voice_job_lock(
    job_id: str,
    *,
    blocking: bool,
) -> BinaryIO | None:
    """Acquire the cross-process retention lock for one Hosted Voice job."""

    path = _voice_lock_path(job_id)
    handle = path.open("a+b")
    flags = fcntl.LOCK_EX
    if not blocking:
        flags |= fcntl.LOCK_NB
    try:
        fcntl.flock(handle.fileno(), flags)
    except BlockingIOError:
        handle.close()
        return None
    except OSError:
        handle.close()
        raise
    return handle


def _release_voice_job_lock(handle: BinaryIO) -> None:
    """Release a Hosted Voice job lock and close its file descriptor."""

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@asynccontextmanager
async def _chunk_upload_lock(upload_id: str) -> AsyncIterator[None]:
    """Serialize cross-process upload mutations without blocking the event loop."""
    deadline = asyncio.get_running_loop().time() + 30
    handle = None
    try:
        while handle is None:
            handle = _acquire_voice_job_lock(
                f"chunk_{_safe_chunked_upload_id(upload_id)}", blocking=False
            )
            if handle is None:
                if asyncio.get_running_loop().time() >= deadline:
                    raise HTTPException(
                        status_code=409, detail="Upload is busy; retry this request."
                    )
                await asyncio.sleep(0.05)
        yield
    finally:
        if handle is not None:
            _release_voice_job_lock(handle)


def _write_chunked_upload_metadata(
    upload_id: str,
    payload: Mapping[str, Any],
) -> None:
    upload_dir = _chunked_upload_dir(upload_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = _chunked_upload_metadata_path(upload_id)
    temp_path = path.with_suffix(".tmp")
    serialized = json.dumps(dict(payload), ensure_ascii=False, indent=2)
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not delete interrupted Hosted Voice upload write")
        raise


def _read_chunked_upload_metadata(
    upload_id: str,
    user: AuthenticatedUser | None,
) -> dict[str, Any]:
    path = _chunked_upload_metadata_path(upload_id)
    if not path.exists():
        raise VoiceSessionError("Chunked upload was not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VoiceSessionError("Chunked upload state is corrupted.") from exc
    expected_email = _email_for_user(user)
    actual_email = str(payload.get("email", "")).strip().lower()
    if actual_email != expected_email:
        raise VoiceSessionError("Chunked upload does not belong to this user.")
    return payload


def _cleanup_stale_chunked_uploads(now: datetime | None = None) -> int:
    """Delete abandoned chunk uploads, including corrupt or missing metadata."""

    timestamp = _utc_timestamp(now)
    removed = 0
    for upload_dir in _chunked_upload_root().iterdir():
        if not upload_dir.is_dir():
            if _path_is_stale(
                upload_dir,
                now=timestamp,
                stale_seconds=CHUNKED_UPLOAD_STALE_SECONDS,
            ) and _remove_voice_file(upload_dir):
                removed += 1
            continue
        handle = _acquire_voice_job_lock(
            f"chunk_{_safe_chunked_upload_id(upload_dir.name)}", blocking=False
        )
        if handle is None:
            continue
        try:
            metadata_path = upload_dir / "metadata.json"
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            if not _payload_or_path_is_stale(
                payload,
                upload_dir,
                now=timestamp,
                stale_seconds=CHUNKED_UPLOAD_STALE_SECONDS,
            ):
                continue
            if _remove_voice_directory(upload_dir):
                removed += 1
        finally:
            _release_voice_job_lock(handle)
    return removed


def _cleanup_stale_upload_job_temp_files(now: datetime) -> int:
    removed = 0
    active_job_ids = _active_upload_job_ids()
    for path in _upload_job_root().glob("*.tmp"):
        job_id = path.stem
        if job_id in active_job_ids or not _path_is_stale(
            path,
            now=now,
            stale_seconds=VOICE_ORPHAN_STALE_SECONDS,
        ):
            continue
        try:
            lock_handle = _acquire_voice_job_lock(job_id, blocking=False)
        except VoiceSessionError:
            if _remove_voice_file(path):
                removed += 1
            continue
        except OSError:
            LOGGER.warning("Could not inspect Hosted Voice job lock: %s", job_id)
            continue
        if lock_handle is None:
            continue
        try:
            if _remove_voice_file(path):
                removed += 1
        finally:
            _release_voice_job_lock(lock_handle)
    return removed


def _cleanup_orphan_voice_directories(
    root: Path,
    *,
    now: datetime,
    stale_seconds: int,
) -> int:
    removed = 0
    active_job_ids = _active_upload_job_ids()
    for path in root.iterdir():
        if not path.is_dir():
            if _path_is_stale(path, now=now, stale_seconds=stale_seconds):
                removed += int(_remove_voice_file(path))
            continue
        job_id = path.name
        try:
            job_path = _upload_job_path(job_id)
        except VoiceSessionError:
            if _path_is_stale(path, now=now, stale_seconds=stale_seconds):
                removed += int(_remove_voice_directory(path))
            continue
        if job_id in active_job_ids or job_path.exists():
            continue
        if not _path_is_stale(path, now=now, stale_seconds=stale_seconds):
            continue
        try:
            lock_handle = _acquire_voice_job_lock(job_id, blocking=False)
        except (OSError, VoiceSessionError):
            LOGGER.warning("Could not inspect orphan Hosted Voice state: %s", job_id)
            continue
        if lock_handle is None:
            continue
        try:
            if _remove_voice_directory(path):
                removed += 1
        finally:
            _release_voice_job_lock(lock_handle)
    return removed


def cleanup_voice_retention_state(
    now: datetime | None = None,
) -> dict[str, int]:
    """Sweep only Hosted Voice-managed state; interview storage is out of scope."""

    timestamp = _utc_timestamp(now)
    return {
        "launch_tokens": _cleanup_expired_voice_launch_tokens(timestamp),
        "jobs": _mark_stale_upload_jobs(timestamp),
        "job_temp_files": _cleanup_stale_upload_job_temp_files(timestamp),
        "chunk_uploads": _cleanup_stale_chunked_uploads(timestamp),
        "source_directories": _cleanup_orphan_voice_directories(
            _uploaded_audio_source_root(),
            now=timestamp,
            stale_seconds=VOICE_ORPHAN_STALE_SECONDS,
        ),
        "work_directories": _cleanup_orphan_voice_directories(
            _voice_work_root(),
            now=timestamp,
            stale_seconds=VOICE_ORPHAN_STALE_SECONDS,
        ),
    }


def _run_voice_retention_cleanup() -> None:
    while (
        _VOICE_RETENTION_CLEANUP_STOP.wait(VOICE_RETENTION_CLEANUP_INTERVAL_SECONDS)
        is False
    ):
        try:
            cleanup_voice_retention_state()
        except (OSError, VoiceSessionError):
            LOGGER.exception("Hosted Voice retention cleanup failed")


def start_voice_retention_cleanup() -> None:
    """Run startup cleanup and start the idempotent periodic sweeper."""

    global _VOICE_RETENTION_CLEANUP_THREAD
    with _VOICE_RETENTION_CLEANUP_THREAD_LOCK:
        if (
            _VOICE_RETENTION_CLEANUP_THREAD is not None
            and _VOICE_RETENTION_CLEANUP_THREAD.is_alive()
        ):
            return
        cleanup_voice_retention_state()
        _VOICE_RETENTION_CLEANUP_STOP.clear()
        _VOICE_RETENTION_CLEANUP_THREAD = threading.Thread(
            target=_run_voice_retention_cleanup,
            name="hosted-voice-retention-cleanup",
            daemon=True,
        )
        _VOICE_RETENTION_CLEANUP_THREAD.start()


def stop_voice_retention_cleanup() -> None:
    """Stop the periodic Hosted Voice retention sweeper."""

    global _VOICE_RETENTION_CLEANUP_THREAD
    with _VOICE_RETENTION_CLEANUP_THREAD_LOCK:
        thread = _VOICE_RETENTION_CLEANUP_THREAD
        if thread is None:
            return
        _VOICE_RETENTION_CLEANUP_STOP.set()
        thread.join(timeout=5)
        if thread.is_alive():
            LOGGER.warning("Hosted Voice retention cleanup did not stop promptly")
            return
        _VOICE_RETENTION_CLEANUP_THREAD = None


def _trim_text(value: str, max_chars: int) -> str:
    text = value.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:].strip()


def _parse_source_metadata_json(raw_value: str) -> dict[str, str]:
    """Return compact source metadata from a browser form payload."""

    if not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise VoiceSessionError("Source metadata must be valid JSON.") from exc
    if not isinstance(parsed, Mapping):
        raise VoiceSessionError("Source metadata must be a JSON object.")
    metadata: dict[str, str] = {}
    for key, value in parsed.items():
        clean_key = str(key).strip()
        if clean_key not in SOURCE_METADATA_FIELDS:
            continue
        clean_value = str(value).strip()
        if clean_value:
            metadata[clean_key] = clean_value[:MAX_SOURCE_METADATA_VALUE_CHARS]
    return metadata


def _parse_iso_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def issue_voice_launch_token(
    *,
    user: AuthenticatedUser | None,
    case_context: str = "",
    language: str = "it",
    now: datetime | None = None,
) -> str:
    """Create an opaque token backed by short-lived server-side metadata."""

    if user is None:
        raise VoiceSessionError("Authentication is required for voice launch.")
    normalized_language = str(language or "it").strip().lower()
    if normalized_language not in SUPPORTED_TRANSCRIPTION_LANGUAGES:
        raise VoiceSessionError(f"Unsupported language: {normalized_language}")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "email": user.email.strip().lower(),
        "language": normalized_language,
        "issued_at": timestamp.isoformat(),
        "expires_at": (timestamp + timedelta(seconds=TOKEN_TTL_SECONDS)).isoformat(),
    }
    normalized_context = _normalize_case_context(case_context)
    if normalized_context:
        payload["case_context"] = normalized_context
    _cleanup_expired_voice_launch_tokens(timestamp)
    token = secrets.token_urlsafe(VOICE_LAUNCH_TOKEN_BYTES)
    _write_voice_launch_token(token, payload)
    return token


def verify_voice_launch_token(
    *,
    token: str,
    user: AuthenticatedUser | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate an opaque launch token against short-lived server metadata."""

    if user is None:
        raise VoiceSessionError("Authentication is required for voice launch.")
    clean_token = token.strip()
    if not clean_token:
        raise VoiceSessionError("Missing Clara voice launch token.")
    if len(clean_token) > 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", clean_token):
        raise VoiceSessionError("Invalid or expired Clara voice launch token.")
    path = _voice_launch_token_path(clean_token)
    if not path.exists():
        raise VoiceSessionError("Invalid or expired Clara voice launch token.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceSessionError("Invalid Clara voice launch token.") from exc
    if not isinstance(payload, dict):
        raise VoiceSessionError("Invalid Clara voice launch token.")
    expected_email = str(payload.get("email", "")).strip().lower()
    actual_email = user.email.strip().lower()
    if expected_email != actual_email:
        raise VoiceSessionError("Clara voice launch token belongs to another user.")
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    try:
        expires_at = _parse_iso_timestamp(str(payload.get("expires_at", "")))
    except (TypeError, ValueError) as exc:
        raise VoiceSessionError("Invalid Clara voice launch token.") from exc
    if expires_at <= timestamp:
        _remove_voice_file(path)
        raise VoiceSessionError("Clara voice launch token has expired.")
    payload["token_hash"] = _token_hash(clean_token)
    return payload


async def _write_upload_file_to_path(
    upload_file: UploadFile,
    output_path: Path,
    *,
    max_bytes: int | None = None,
    too_large_message: str | None = None,
) -> int:
    """Stream one FastAPI upload to disk and return the byte count."""

    limit = _max_audio_upload_bytes() if max_bytes is None else max_bytes
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(
        f".{output_path.name}.{secrets.token_hex(8)}.uploading"
    )
    total_bytes = 0
    try:
        with temp_path.open("wb") as handle:
            while True:
                try:
                    chunk = await upload_file.read(UPLOAD_COPY_BLOCK_BYTES)
                except TypeError:
                    chunk = await upload_file.read()
                    if chunk:
                        total_bytes += len(chunk)
                        if total_bytes > limit:
                            raise VoiceSessionError(
                                too_large_message or _upload_too_large_message(limit)
                            )
                        handle.write(chunk)
                    break
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise VoiceSessionError(
                        too_large_message or _upload_too_large_message(limit)
                    )
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise
    return total_bytes


def _response_output_text(response_payload: Mapping[str, Any]) -> str:
    direct = response_payload.get("output_text")
    if isinstance(direct, str):
        return direct.strip()
    chunks: list[str] = []
    raw_output = response_payload.get("output", [])
    if isinstance(raw_output, list):
        for output_item in raw_output:
            if not isinstance(output_item, Mapping):
                continue
            content = output_item.get("content", [])
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, Mapping):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    return "".join(chunks).strip()


def _uploaded_audio_bundle_payload(
    *,
    captured_at: str,
    language: str,
    source_metadata: dict[str, str],
    filename: str,
    content_type: str,
    transcript: str,
    raw_transcription_text: str,
    transcription_metadata: dict[str, Any],
) -> dict[str, Any]:
    prompted_transcript = raw_transcription_text or transcript
    bundle = UploadedAudioBundle(
        captured_at=captured_at,
        language=language,
        source_metadata=source_metadata,
        model=DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
        transcription_model=DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
        audio_file_name=filename,
        audio_content_type=content_type or "application/octet-stream",
        user_transcript=transcript,
        raw_transcription_text=prompted_transcript,
        transcript_text_prompted=prompted_transcript,
        speaker_label_note=(
            "Speaker attribution is intentionally not generated by the hosted "
            "server. Clara/Codex assigns speakers from the clean transcript "
            "and source metadata after import."
        ),
        transcript_processing_note=POST_TRANSCRIPTION_PROCESSING_NOTE,
        transcription_metadata=transcription_metadata,
        extraction_text="",
        extraction_json={
            "cleaned_notes_markdown": "",
            "entries": [],
            "open_questions": [],
        },
    )
    if hasattr(bundle, "model_dump"):
        return bundle.model_dump()
    return bundle.dict()


def _transcription_coverage_failure_message(metadata: Mapping[str, Any]) -> str:
    warnings = metadata.get("warnings", [])
    first_warning = ""
    if isinstance(warnings, list) and warnings:
        first_warning = f" First warning: {warnings[0]}"
    return (
        "Audio transcription did not pass coverage checks; no bundle was "
        f"downloaded.{first_warning}"
    )[:MAX_UPLOAD_JOB_ERROR_CHARS]


def _transcription_metadata_is_downloadable(metadata: Mapping[str, Any]) -> bool:
    status_value = str(metadata.get("status", "")).strip().lower()
    return status_value in {"complete", "warning"} and (
        metadata.get("coverage_complete") is True
    )


def _process_uploaded_audio_job(
    *,
    job_id: str,
    email: str,
    api_key: str,
    audio_path: Path,
    audio_size_bytes: int,
    filename: str,
    content_type: str,
    language: str,
    source_metadata: dict[str, str],
    case_context: str,
    safety_identifier: str,
) -> None:
    def update_progress(updates: Mapping[str, Any]) -> None:
        _update_upload_job(
            job_id,
            {
                "status": "running",
                "email": email,
                "owner_pid": os.getpid(),
                "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                **dict(updates),
            },
        )

    lock_handle: BinaryIO | None = None
    is_active = False
    cleanup_directories = [audio_path.parent]
    try:
        lock_handle = _acquire_voice_job_lock(job_id, blocking=True)
        if lock_handle is None:  # pragma: no cover - blocking locks return a handle
            raise VoiceSessionError("Hosted Voice job could not be locked.")
        _set_upload_job_active(job_id, active=True)
        is_active = True
        source_directory = _uploaded_audio_source_dir(job_id)
        work_directory = _voice_work_dir(job_id)
        for cleanup_directory in (source_directory, work_directory):
            if cleanup_directory not in cleanup_directories:
                cleanup_directories.append(cleanup_directory)
        _write_upload_job(
            job_id,
            {
                "status": "running",
                "email": email,
                "owner_pid": os.getpid(),
                "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                "message": "Transcribing uploaded audio.",
                "phase": "starting",
                "phase_label": "Starting",
                "progress_percent": 0,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        terminal_payload: dict[str, Any]
        try:
            transcription_result = create_audio_transcription(
                api_key=api_key,
                audio_path=audio_path,
                audio_size_bytes=audio_size_bytes,
                filename=filename,
                content_type=content_type,
                language=language,
                case_context=case_context,
                safety_identifier=safety_identifier,
                progress_callback=update_progress,
                temporary_root=work_directory,
            )
            captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            metadata = dict(transcription_result.metadata)
            metadata.setdefault("language", language)
            if not _transcription_metadata_is_downloadable(metadata):
                terminal_payload = {
                    "status": "error",
                    "email": email,
                    "message": _transcription_coverage_failure_message(metadata),
                    "transcription_metadata": metadata,
                    "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                bundle = _uploaded_audio_bundle_payload(
                    captured_at=captured_at,
                    language=language,
                    source_metadata=source_metadata,
                    filename=filename,
                    content_type=content_type,
                    transcript=transcription_result.text,
                    raw_transcription_text=transcription_result.raw_transcription_text,
                    transcription_metadata=metadata,
                )
                terminal_payload = {
                    "status": "done",
                    "email": email,
                    "message": "Audio transcription complete.",
                    "phase": "complete",
                    "phase_label": "Complete",
                    "progress_percent": 100,
                    "bundle": bundle,
                    "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
        except (OSError, ValueError, VoiceSessionError) as exc:
            LOGGER.exception("Clara uploaded audio job failed: job_id=%s", job_id)
            terminal_payload = {
                "status": "error",
                "email": email,
                "message": str(exc)[:MAX_UPLOAD_JOB_ERROR_CHARS],
                "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        cleanup_error: VoiceSessionError | None = None
        for cleanup_directory in cleanup_directories:
            try:
                _remove_voice_directory(cleanup_directory, strict=True)
            except VoiceSessionError as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if cleanup_error is not None:
            terminal_payload = {
                "status": "error",
                "email": email,
                "message": (
                    "Uploaded audio processing ended, but its server-side files "
                    "could not all be deleted. Download remains blocked while "
                    "cleanup is retried."
                ),
                "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        _write_upload_job(
            job_id,
            terminal_payload,
        )
    finally:
        for cleanup_directory in cleanup_directories:
            _remove_voice_directory(cleanup_directory)
        if is_active:
            _set_upload_job_active(job_id, active=False)
        if lock_handle is not None:
            _release_voice_job_lock(lock_handle)


def _validate_uploaded_audio_request_fields(
    *,
    language: str,
) -> None:
    if language not in SUPPORTED_TRANSCRIPTION_LANGUAGES:
        raise VoiceSessionError(f"Unsupported language: {language}")


def _build_realtime_transcription_session_config(
    *,
    language: str,
    case_context: str = "",
) -> dict[str, Any]:
    transcription: dict[str, Any] = {
        "model": DEFAULT_REALTIME_TRANSCRIPTION_MODEL,
        "languages": [language],
        "delay": DEFAULT_LIVE_TRANSCRIPTION_DELAY,
    }
    normalized_context = _normalize_case_context(case_context)
    if normalized_context:
        transcription["prompt"] = (
            "Use this case context only to improve transcription of names, "
            "organizations, and professional terms. Do not add facts that were "
            f"not spoken.\n\n{normalized_context}"
        )
    return {
        "type": "transcription",
        "audio": {
            "input": {
                "transcription": transcription,
                "turn_detection": None,
            },
        },
    }


def _queue_uploaded_audio_job(
    *,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser | None,
    job_id: str,
    case_context: str,
    source_metadata: dict[str, str],
    audio_path: Path,
    audio_size_bytes: int,
    filename: str,
    content_type: str,
    language: str,
) -> str:
    job_path: Path | None = None
    try:
        _mark_stale_upload_jobs()
        _validate_audio_upload_metadata(filename, audio_size_bytes)
        normalized_case_context = _normalize_case_context(case_context)
        api_key = _resolve_openai_api_key()
        email = _email_for_user(user)
        job_path = _upload_job_path(job_id)
        _write_upload_job(
            job_id,
            {
                "status": "queued",
                "email": email,
                "owner_pid": os.getpid(),
                "retention_lock_version": VOICE_RETENTION_LOCK_VERSION,
                "message": "Upload received. Waiting to start transcription.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        background_tasks.add_task(
            _process_uploaded_audio_job,
            job_id=job_id,
            email=email,
            api_key=api_key,
            audio_path=audio_path,
            audio_size_bytes=audio_size_bytes,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            language=language,
            source_metadata=source_metadata,
            case_context=normalized_case_context,
            safety_identifier=_safety_identifier(user),
        )
    except OSError as exc:
        _remove_voice_directory(audio_path.parent)
        if job_path is not None:
            _remove_voice_file(job_path.with_suffix(".tmp"))
            _remove_voice_file(job_path)
        raise VoiceSessionError(
            "Uploaded audio could not be queued and its temporary copy was deleted."
        ) from exc
    return job_id


def _expected_chunk_byte_counts(
    *,
    total_bytes: int,
    total_chunks: int,
    chunk_size: int,
) -> list[int]:
    if total_bytes <= 0 or total_chunks <= 0 or chunk_size <= 0:
        raise VoiceSessionError("Invalid audio chunk metadata.")
    expected: list[int] = []
    remaining = total_bytes
    for _chunk_index in range(total_chunks):
        chunk_bytes = min(chunk_size, remaining)
        if chunk_bytes <= 0:
            raise VoiceSessionError("Audio chunk count does not match the file size.")
        expected.append(chunk_bytes)
        remaining -= chunk_bytes
    if remaining != 0:
        raise VoiceSessionError("Audio chunk count does not match the file size.")
    return expected


def _expected_chunk_bytes_for_index(
    metadata: Mapping[str, Any],
    chunk_index: int,
) -> int:
    raw_expected = metadata.get("expected_chunk_bytes")
    if isinstance(raw_expected, list):
        try:
            value = int(raw_expected[chunk_index])
        except (IndexError, TypeError, ValueError) as exc:
            raise VoiceSessionError("Chunked upload metadata is corrupted.") from exc
        if value <= 0:
            raise VoiceSessionError("Chunked upload metadata is corrupted.")
        return value
    total_bytes = int(metadata["total_bytes"])
    total_chunks = int(metadata["total_chunks"])
    chunk_size = int(metadata.get("chunk_size", CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES))
    return _expected_chunk_byte_counts(
        total_bytes=total_bytes,
        total_chunks=total_chunks,
        chunk_size=chunk_size,
    )[chunk_index]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            data = handle.read(UPLOAD_COPY_BLOCK_BYTES)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def _assemble_chunked_audio_file(
    *,
    upload_id: str,
    metadata: Mapping[str, Any],
    output_path: Path,
) -> int:
    total_chunks = int(metadata["total_chunks"])
    total_bytes = int(metadata["total_bytes"])
    assembled_bytes = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_hashes = metadata.get("chunk_sha256", {})
    with output_path.open("wb") as output_handle:
        for chunk_index in range(total_chunks):
            chunk_path = _chunked_upload_chunk_path(upload_id, chunk_index)
            if not chunk_path.exists():
                raise VoiceSessionError(
                    f"Missing uploaded audio chunk {chunk_index + 1} of {total_chunks}."
                )
            expected_chunk_bytes = _expected_chunk_bytes_for_index(
                metadata,
                chunk_index,
            )
            actual_chunk_bytes = chunk_path.stat().st_size
            if actual_chunk_bytes != expected_chunk_bytes:
                raise VoiceSessionError(
                    f"Uploaded audio chunk {chunk_index + 1} has an unexpected size."
                )
            if isinstance(chunk_hashes, dict):
                expected_hash = str(chunk_hashes.get(str(chunk_index), "")).strip()
                if expected_hash and _file_sha256(chunk_path) != expected_hash:
                    raise VoiceSessionError(
                        f"Uploaded audio chunk {chunk_index + 1} failed integrity checks."
                    )
            with chunk_path.open("rb") as chunk_handle:
                while True:
                    data = chunk_handle.read(UPLOAD_COPY_BLOCK_BYTES)
                    if not data:
                        break
                    output_handle.write(data)
                    assembled_bytes += len(data)
    if assembled_bytes != total_bytes:
        raise VoiceSessionError(
            "Uploaded audio chunks did not match the expected file size."
        )
    return assembled_bytes


@site_router.get("/voice")
def voice_page(
    request: Request,
    session: str = Query(default=""),
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
):
    """Render the hosted Clara voice page."""

    session_ready = False
    token_error = ""
    language = "it"
    if session:
        try:
            launch_metadata = verify_voice_launch_token(token=session, user=user)
            language = str(launch_metadata.get("language") or "it")
            session_ready = True
        except VoiceSessionError as exc:
            token_error = str(exc)
    return templates.TemplateResponse(
        "case_notes_voice.html",
        {
            "request": request,
            "participant_email": user.email if user is not None else "",
            "default_transcription_model": DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
            "realtime_transcription_model": DEFAULT_REALTIME_TRANSCRIPTION_MODEL,
            "session_token": session if session_ready else "",
            "session_ready": session_ready,
            "token_error": token_error,
            "language": language,
        },
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "Vary": "Cookie",
        },
    )


@site_router.get("/voice/launch")
def launch_voice_page(
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> RedirectResponse:
    """Issue a short-lived token and redirect into the hosted voice page."""

    try:
        token = issue_voice_launch_token(user=user)
    except VoiceSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return RedirectResponse(
        f"/case-notes/voice?{urlencode({'session': token})}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.post("/launch")
def create_voice_launch(
    payload: VoiceLaunchRequest,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Issue an opaque launch token from authenticated body-supplied context."""

    try:
        token = issue_voice_launch_token(
            user=user,
            case_context=payload.case_context,
            language=payload.language,
        )
    except VoiceSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return JSONResponse(
        {
            "status": "ready",
            "launch_token": token,
            "launch_path": f"/case-notes/voice?{urlencode({'session': token})}",
        },
        headers={"Cache-Control": "no-store, private", "Pragma": "no-cache"},
    )


@router.post("/realtime-transcription/session")
def create_realtime_transcription_session(
    payload: RealtimeTranscriptionSessionRequest,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Create a Realtime transcription-only WebRTC session for live call capture."""

    try:
        _validate_uploaded_audio_request_fields(language=payload.language)
        launch_metadata = verify_voice_launch_token(
            token=payload.launch_token, user=user
        )
        session_config = _build_realtime_transcription_session_config(
            language=payload.language,
            case_context=str(launch_metadata.get("case_context", "")),
        )
        realtime_call = create_realtime_call_with_metadata(
            api_key=_resolve_openai_api_key(),
            sdp=payload.sdp,
            session_config=session_config,
            safety_identifier=_safety_identifier(user),
        )
    except VoiceSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OpenAIRealtimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return JSONResponse(
        {
            "status": "ready",
            "sdp": realtime_call.sdp,
            "call_id": realtime_call.call_id,
            "launch_token_hint": str(launch_metadata.get("token_hash", ""))[:8],
            "transcription_model": DEFAULT_REALTIME_TRANSCRIPTION_MODEL,
            "transcription_delay": DEFAULT_LIVE_TRANSCRIPTION_DELAY,
        }
    )


@router.post("/upload")
async def upload_audio(
    background_tasks: BackgroundTasks,
    launch_token: str = Form(...),
    language: str = Form("it"),
    case_context: str = Form(""),
    source_metadata_json: str = Form("{}"),
    audio_file: UploadFile = File(..., alias="audio"),
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Transcribe uploaded audio and return a local Clara import bundle."""

    try:
        _validate_uploaded_audio_request_fields(
            language=language,
        )
        source_metadata = _parse_source_metadata_json(source_metadata_json)
        launch_metadata = verify_voice_launch_token(token=launch_token, user=user)
        filename = _safe_upload_filename(audio_file.filename or "audio-upload")
        job_id = secrets.token_urlsafe(18)
        audio_path = _uploaded_audio_source_path(job_id, filename)
        audio_size_bytes = await _write_upload_file_to_path(audio_file, audio_path)
        job_id = _queue_uploaded_audio_job(
            background_tasks=background_tasks,
            user=user,
            job_id=job_id,
            case_context=(case_context or str(launch_metadata.get("case_context", ""))),
            source_metadata=source_metadata,
            audio_path=audio_path,
            audio_size_bytes=audio_size_bytes,
            filename=filename,
            content_type=audio_file.content_type or "application/octet-stream",
            language=language,
        )
    except (OSError, VoiceSessionError) as exc:
        if "audio_path" in locals():
            _remove_voice_directory(audio_path.parent)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return JSONResponse(
        {
            "status": "queued",
            "job_id": job_id,
            "message": "Upload received. Transcription is running in the background.",
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.post("/upload/chunks/start")
async def start_chunked_audio_upload(
    launch_token: str = Form(...),
    language: str = Form("it"),
    case_context: str = Form(""),
    source_metadata_json: str = Form("{}"),
    filename: str = Form(...),
    content_type: str = Form("application/octet-stream"),
    total_bytes: int = Form(...),
    total_chunks: int = Form(...),
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Create server-side state for a large browser-chunked audio upload."""

    try:
        _cleanup_stale_chunked_uploads()
        _validate_uploaded_audio_request_fields(
            language=language,
        )
        safe_filename = _safe_upload_filename(filename)
        _validate_audio_upload_metadata(safe_filename, total_bytes)
        if total_chunks <= 0:
            raise VoiceSessionError("Invalid audio chunk count.")
        expected_chunks = max(
            1,
            math.ceil(total_bytes / CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES),
        )
        if total_chunks != expected_chunks:
            raise VoiceSessionError("Audio chunk count does not match the file size.")
        expected_chunk_bytes = _expected_chunk_byte_counts(
            total_bytes=total_bytes,
            total_chunks=total_chunks,
            chunk_size=CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES,
        )
        source_metadata = _parse_source_metadata_json(source_metadata_json)
        launch_metadata = verify_voice_launch_token(token=launch_token, user=user)
        upload_id = secrets.token_urlsafe(18)
        now = datetime.now(timezone.utc).isoformat()
        _write_chunked_upload_metadata(
            upload_id,
            {
                "status": "uploading",
                "email": _email_for_user(user),
                "filename": safe_filename,
                "content_type": content_type or "application/octet-stream",
                "total_bytes": total_bytes,
                "total_chunks": total_chunks,
                "chunk_size": CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES,
                "expected_chunk_bytes": expected_chunk_bytes,
                "language": language,
                "source_metadata": source_metadata,
                "case_context": _normalize_case_context(
                    case_context or str(launch_metadata.get("case_context", ""))
                ),
                "received_chunks": [],
                "chunk_bytes": {},
                "chunk_sha256": {},
                "created_at": now,
                "updated_at": now,
            },
        )
    except VoiceSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return JSONResponse(
        {
            "status": "ready",
            "upload_id": upload_id,
            "chunk_size": CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES,
        },
        status_code=status.HTTP_201_CREATED,
    )


def _authorized_chunked_metadata(
    upload_id: str, user: AuthenticatedUser | None
) -> dict[str, Any]:
    """Map missing, invalid or unauthorized upload state to a client error."""
    try:
        return _read_chunked_upload_metadata(upload_id, user)
    except (OSError, VoiceSessionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload/chunks/{upload_id}")
async def upload_audio_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    audio_chunk: UploadFile = File(..., alias="audio"),
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Store one small browser-uploaded chunk for a large audio file."""

    # Authenticate before acquiring a lock or consuming a potentially large body.
    _authorized_chunked_metadata(upload_id, user)
    async with _chunk_upload_lock(upload_id):
        chunk_path: Path | None = None
        temporary_path: Path | None = None
        published_new = False
        try:
            metadata = _authorized_chunked_metadata(upload_id, user)
            if str(metadata.get("status", "")).strip().lower() != "uploading":
                raise VoiceSessionError("Chunked upload is not accepting more chunks.")
            total_chunks = int(metadata["total_chunks"])
            if chunk_index < 0 or chunk_index >= total_chunks:
                raise VoiceSessionError("Invalid audio chunk index.")
            chunk_path = _chunked_upload_chunk_path(upload_id, chunk_index)
            temporary_path = chunk_path.with_name(
                f".retry-{secrets.token_hex(12)}.part"
            )
            expected = _expected_chunk_bytes_for_index(metadata, chunk_index)
            chunk_bytes = await _write_upload_file_to_path(
                audio_chunk,
                temporary_path,
                max_bytes=expected,
                too_large_message=f"Uploaded audio chunk {chunk_index + 1} is larger than expected.",
            )
            if chunk_bytes <= 0 or chunk_bytes != expected:
                raise VoiceSessionError(
                    f"Uploaded audio chunk {chunk_index + 1} has an unexpected size."
                )
            digest = _file_sha256(temporary_path)
            received_chunks = {
                int(index)
                for index in metadata.get("received_chunks", [])
                if isinstance(index, int)
            }
            already_received = chunk_path.exists()
            if already_received:
                if (
                    chunk_path.stat().st_size != chunk_bytes
                    or _file_sha256(chunk_path) != digest
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="This chunk index already contains different audio bytes.",
                    )
            else:
                temporary_path.replace(chunk_path)
                published_new = True
            received_chunks.add(chunk_index)
            metadata["received_chunks"] = sorted(received_chunks)
            metadata.setdefault("chunk_bytes", {})[str(chunk_index)] = chunk_bytes
            metadata.setdefault("chunk_sha256", {})[str(chunk_index)] = digest
            metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
            _write_chunked_upload_metadata(upload_id, metadata)
        except (OSError, VoiceSessionError) as exc:
            if published_new and chunk_path is not None:
                _remove_voice_file(chunk_path)
            detail = (
                str(exc)
                if isinstance(exc, VoiceSessionError)
                else "The audio chunk could not be stored; its temporary copy was deleted."
            )
            raise HTTPException(status_code=400, detail=detail) from exc
        finally:
            if temporary_path is not None:
                _remove_voice_file(temporary_path)
    return JSONResponse(
        {
            "status": "received",
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "received_chunks": len(received_chunks),
            "received_indexes": sorted(received_chunks),
            "total_chunks": total_chunks,
            "already_received": already_received,
        }
    )


@router.get("/upload/chunks/{upload_id}")
async def inspect_chunked_audio_upload(
    upload_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Return owner-authorized received indexes for an interrupted upload."""
    _authorized_chunked_metadata(upload_id, user)
    async with _chunk_upload_lock(upload_id):
        metadata = _authorized_chunked_metadata(upload_id, user)
        indexes = [
            index
            for index in metadata.get("received_chunks", [])
            if isinstance(index, int)
            and _chunked_upload_chunk_path(upload_id, index).is_file()
            and _file_sha256(_chunked_upload_chunk_path(upload_id, index))
            == metadata.get("chunk_sha256", {}).get(str(index))
        ]
        return JSONResponse(
            {
                "upload_id": upload_id,
                "status": metadata["status"],
                "received_indexes": sorted(indexes),
                "total_chunks": metadata["total_chunks"],
            }
        )


@router.post("/upload/chunks/{upload_id}/finish")
async def finish_chunked_audio_upload(
    upload_id: str,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Assemble a chunked audio upload and queue the existing transcription job."""

    _authorized_chunked_metadata(upload_id, user)
    async with _chunk_upload_lock(upload_id):
        try:
            metadata = _authorized_chunked_metadata(upload_id, user)
            job_id = secrets.token_urlsafe(18)
            filename = str(metadata["filename"])
            audio_path = _uploaded_audio_source_path(job_id, filename)
            audio_size_bytes = _assemble_chunked_audio_file(
                upload_id=upload_id,
                metadata=metadata,
                output_path=audio_path,
            )
            _remove_voice_directory(_chunked_upload_dir(upload_id), strict=True)
            job_id = _queue_uploaded_audio_job(
                background_tasks=background_tasks,
                user=user,
                job_id=job_id,
                case_context=str(metadata.get("case_context", "")),
                source_metadata=dict(metadata.get("source_metadata", {})),
                audio_path=audio_path,
                audio_size_bytes=audio_size_bytes,
                filename=filename,
                content_type=str(metadata.get("content_type", "")),
                language=str(metadata["language"]),
            )
        except (OSError, VoiceSessionError) as exc:
            if "audio_path" in locals():
                _remove_voice_directory(audio_path.parent)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    return JSONResponse(
        {
            "status": "queued",
            "job_id": job_id,
            "message": "Upload received. Transcription is running in the background.",
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get("/upload/{job_id}")
def get_upload_audio_job(
    job_id: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Return status or final bundle for an uploaded audio transcription job."""

    try:
        _mark_stale_upload_jobs()
        payload = _read_upload_job(job_id, user)
    except VoiceSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if str(payload.get("status", "")).strip().lower() in {"done", "error"}:
        try:
            _delete_upload_job(job_id, strict=True)
        except _VoiceJobInUseError:
            return JSONResponse(
                {
                    "status": "running",
                    "phase": "finalizing",
                    "phase_label": "Finalizing",
                    "message": "Deleting server-side files before download.",
                    "progress_percent": 100,
                },
                headers={
                    "Cache-Control": "no-store, private",
                    "Pragma": "no-cache",
                },
            )
        except VoiceSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
    return JSONResponse(
        payload,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
        },
    )
