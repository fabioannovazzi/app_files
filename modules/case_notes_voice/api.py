from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping
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

DEFAULT_UPLOAD_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
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
MAX_CASE_CONTEXT_CHARS = 12_000
MAX_AUDIO_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
# Keep a safety margin below OpenAI's 25 MB transcription file limit because the
# request includes multipart overhead and provider limits are decimal MB.
MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES = 24 * 1024 * 1024
CHUNKED_AUDIO_UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024
UPLOAD_COPY_BLOCK_BYTES = 1024 * 1024
MAX_STREAM_COPY_SPLIT_ATTEMPTS = 256
MAX_UPLOAD_JOB_ERROR_CHARS = 2_000
UPLOAD_JOB_STALE_SECONDS = 24 * 60 * 60
UPLOAD_JOB_TERMINAL_STALE_SECONDS = 10 * 60
CHUNKED_UPLOAD_STALE_SECONDS = 24 * 60 * 60
VOICE_ORPHAN_STALE_SECONDS = 10 * 60
VOICE_RETENTION_CLEANUP_INTERVAL_SECONDS = 60
VOICE_RETENTION_LOCK_VERSION = 1
OPENAI_UPLOAD_TRANSCRIPTION_TIMEOUT_SECONDS = 10 * 60
UPLOAD_TRANSCRIPTION_CHUNK_SECONDS = 10 * 60
UPLOAD_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS = 30
MAX_UPLOAD_TRANSCRIPTION_CHUNK_RETRIES = 4
UPLOAD_TRANSCRIPTION_REPAIR_CHUNK_SECONDS = 2 * 60
UPLOAD_TRANSCRIPTION_REPAIR_CHUNK_OVERLAP_SECONDS = 10
MAX_UPLOAD_TRANSCRIPTION_REPAIR_SUBCHUNK_RETRIES = 1
MIN_CHUNK_TRANSCRIPTION_VALIDATION_SECONDS = 180
MIN_CHUNK_TRANSCRIPTION_WORDS_PER_MINUTE = 15
REPEATED_TRANSCRIPTION_NGRAM_WORDS = 8
REPEATED_TRANSCRIPTION_NGRAM_COUNT = 3
MAX_TRANSCRIPTION_OVERLAP_DEDUP_WORDS = 120
MIN_TRANSCRIPTION_OVERLAP_DEDUP_WORDS = 10
TRANSCRIPTION_OVERLAP_DEDUP_SIMILARITY = 0.72
MAX_TRANSCRIPTION_PROMPT_GLOSSARY_TERMS = 24
MAX_TRANSCRIPTION_PROMPT_GLOSSARY_TERM_CHARS = 96
# These codes describe spoken audio, independently of Clara's report language.
SUPPORTED_TRANSCRIPTION_LANGUAGES = {"it", "en", "fr", "de", "es"}
SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}
FFMPEG_DURATION_RE = re.compile(
    r"Duration:\s*(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+(?:\.\d+)?)"
)
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


class VoiceSessionError(RuntimeError):
    """Raised when the hosted voice surface cannot complete an action."""


class _VoiceJobInUseError(VoiceSessionError):
    """Raised when terminal cleanup must wait for the active job lock."""


@dataclass(frozen=True)
class AudioTranscriptionChunk:
    """One temporary audio chunk ready for transcription."""

    index: int
    filename: str
    content_type: str
    content: bytes = b""
    start_seconds: float = 0.0
    duration_seconds: float = 0.0
    overlap_seconds: float = 0.0
    path: Path | None = None
    audio_bytes: int | None = None


def _audio_transcription_chunk_bytes(chunk: AudioTranscriptionChunk) -> int:
    """Return chunk size without forcing path-backed audio into memory."""

    if chunk.audio_bytes is not None:
        return chunk.audio_bytes
    if chunk.path is not None:
        return chunk.path.stat().st_size
    return len(chunk.content)


def _audio_transcription_chunk_content(chunk: AudioTranscriptionChunk) -> bytes:
    """Load chunk bytes only when an API request needs them."""

    if chunk.content:
        return chunk.content
    if chunk.path is None:
        return chunk.content
    return chunk.path.read_bytes()


@dataclass(frozen=True)
class AudioTranscriptionPayload:
    """One API-safe prepared audio payload."""

    path: Path
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class DurationBearingAudioSource:
    """Uploaded audio source after duration metadata is guaranteed."""

    path: Path
    filename: str
    content_type: str
    audio_bytes: int
    duration_seconds: float
    was_normalized: bool = False


@dataclass(frozen=True)
class AudioTranscriptionResponse:
    """One transcription API response normalized for Clara."""

    text: str


@dataclass(frozen=True)
class AudioTranscriptionResult:
    """Transcribed text plus mechanical coverage diagnostics."""

    text: str
    metadata: dict[str, Any]
    raw_transcription_text: str = ""


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
        temp_path.write_text(serialized, encoding="utf-8")
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


def _normalize_case_context(case_context: str) -> str:
    normalized = "\n".join(
        line.rstrip() for line in case_context.replace("\r\n", "\n").splitlines()
    ).strip()
    if len(normalized) > MAX_CASE_CONTEXT_CHARS:
        return (
            normalized[:MAX_CASE_CONTEXT_CHARS].rstrip()
            + "\n\n[Case context truncated.]"
        )
    return normalized


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


def _safe_upload_filename(filename: str) -> str:
    clean = Path(filename or "audio-upload").name.strip()
    if not clean:
        return "audio-upload"
    return clean.replace('"', "").replace("\r", "").replace("\n", "")


def _audio_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return "mpeg" if suffix == "mpg" else suffix


def _max_audio_upload_bytes() -> int:
    configured = os.getenv("CASE_NOTES_VOICE_MAX_AUDIO_UPLOAD_BYTES", "").strip()
    if not configured:
        return MAX_AUDIO_UPLOAD_BYTES
    try:
        value = int(configured)
    except ValueError as exc:
        raise VoiceSessionError("Invalid configured audio upload size limit.") from exc
    if value <= 0:
        raise VoiceSessionError("Invalid configured audio upload size limit.")
    return value


def _upload_too_large_message(limit_bytes: int) -> str:
    limit_mebibytes = limit_bytes / (1024 * 1024)
    if limit_mebibytes >= 1:
        limit_display = f"{limit_mebibytes:.0f} MB"
    else:
        limit_display = f"{limit_bytes} bytes"
    return f"Uploaded audio file is too large. Maximum allowed is {limit_display}."


def _validate_audio_upload_metadata(
    filename: str,
    total_bytes: int,
    *,
    max_bytes: int | None = None,
) -> None:
    extension = _audio_extension(filename)
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise VoiceSessionError(f"Unsupported audio file type. Supported: {supported}.")
    if total_bytes <= 0:
        raise VoiceSessionError("Uploaded audio file is empty.")
    limit = _max_audio_upload_bytes() if max_bytes is None else max_bytes
    if total_bytes > limit:
        raise VoiceSessionError(_upload_too_large_message(limit))


def _validate_audio_upload(filename: str, audio_bytes: bytes) -> None:
    _validate_audio_upload_metadata(filename, len(audio_bytes))


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
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        raise
    return total_bytes


def _optional_binary_from_env(env_name: str) -> str | None:
    configured = os.getenv(env_name, "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    if path.exists():
        return str(path)
    discovered = shutil.which(configured)
    return discovered or configured


def _ffmpeg_binary() -> str | None:
    configured = _optional_binary_from_env("FFMPEG_BINARY")
    if configured:
        return configured
    try:
        import imageio_ffmpeg
    except ImportError:
        return shutil.which("ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ffprobe_binary() -> str | None:
    configured = _optional_binary_from_env("FFPROBE_BINARY")
    if configured:
        return configured
    return shutil.which("ffprobe")


def _run_audio_probe(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return "\n".join([completed.stdout, completed.stderr])


def _parse_ffmpeg_duration(output: str) -> float | None:
    match = FFMPEG_DURATION_RE.search(output)
    if not match:
        return None
    return (
        int(match.group("hours")) * 60 * 60
        + int(match.group("minutes")) * 60
        + float(match.group("seconds"))
    )


def _ffmpeg_duration_seconds(path: Path) -> float | None:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        return None
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _parse_ffmpeg_duration("\n".join([completed.stdout, completed.stderr]))


def _round_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)


def _audio_duration_seconds(path: Path) -> float | None:
    ffprobe = _ffprobe_binary()
    if ffprobe:
        output = _run_audio_probe(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
        if output:
            try:
                return float(output.strip().splitlines()[0])
            except (IndexError, ValueError):
                pass

    afinfo = shutil.which("afinfo")
    if afinfo:
        output = _run_audio_probe([afinfo, str(path)])
        if output:
            for line in output.splitlines():
                clean = line.strip()
                if clean.startswith("estimated duration:") and clean.endswith(" sec"):
                    raw_value = clean.removeprefix("estimated duration:").removesuffix(
                        " sec"
                    )
                    try:
                        return float(raw_value.strip())
                    except ValueError:
                        return None
    return _ffmpeg_duration_seconds(path)


def _duration_normalized_audio_filename(filename: str) -> str:
    stem = Path(_safe_upload_filename(filename)).stem or "audio-upload"
    return f"{stem}.duration-normalized.wav"


def _create_duration_normalized_audio(
    *,
    input_path: Path,
    output_dir: Path,
    filename: str,
) -> DurationBearingAudioSource:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise VoiceSessionError(
            "Could not determine uploaded audio duration, and server-side audio "
            "normalization requires ffmpeg. Configure FFMPEG_BINARY or install "
            "the declared imageio-ffmpeg dependency, then upload the file again."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_filename = _duration_normalized_audio_filename(filename)
    output_path = output_dir / normalized_filename
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    _run_ffmpeg_audio_preparation(command)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise VoiceSessionError(
            "Server-side audio normalization produced an empty audio file."
        )
    duration_seconds = _audio_duration_seconds(output_path)
    if duration_seconds is None:
        raise VoiceSessionError(
            "Server-side audio normalization completed, but the normalized audio "
            "still has no readable duration metadata."
        )
    return DurationBearingAudioSource(
        path=output_path,
        filename=normalized_filename,
        content_type="audio/wav",
        audio_bytes=output_path.stat().st_size,
        duration_seconds=duration_seconds,
        was_normalized=True,
    )


def _duration_bearing_audio_source(
    *,
    input_path: Path,
    output_dir: Path,
    filename: str,
    content_type: str,
    audio_bytes: int,
) -> DurationBearingAudioSource:
    duration_seconds = _audio_duration_seconds(input_path)
    if duration_seconds is not None:
        return DurationBearingAudioSource(
            path=input_path,
            filename=_safe_upload_filename(filename),
            content_type=content_type or "application/octet-stream",
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
        )
    return _create_duration_normalized_audio(
        input_path=input_path,
        output_dir=output_dir,
        filename=filename,
    )


def _chunk_time_windows(
    duration_seconds: float,
    *,
    chunk_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_SECONDS,
    overlap_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
) -> list[tuple[float, float, float]]:
    """Build deterministic chunk windows; overlap is an auditable guard."""

    if duration_seconds <= 0:
        return []
    if chunk_seconds <= 0:
        raise VoiceSessionError("Audio chunk duration must be positive.")
    overlap = max(0, min(overlap_seconds, chunk_seconds - 1))
    windows: list[tuple[float, float, float]] = []
    start = 0.0
    while start < duration_seconds:
        end = min(start + chunk_seconds, duration_seconds)
        windows.append((start, end, 0.0 if start == 0 else float(overlap)))
        if end >= duration_seconds:
            break
        start = max(end - overlap, start + 1)
    return windows


def _run_ffmpeg_audio_preparation(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise VoiceSessionError(
            "Uploaded audio must be prepared before transcription, "
            "but ffmpeg is not installed. "
            "Configure FFMPEG_BINARY or install the declared imageio-ffmpeg "
            "dependency, then upload the same single file again."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise VoiceSessionError(
            "Uploaded audio must be prepared before transcription, "
            f"but server-side audio preparation failed: {detail or exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VoiceSessionError("Server-side audio preparation timed out.") from exc


def _transcription_stream_copy_target_bytes() -> int:
    return MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES


def _transcription_stream_copy_chunk_count(audio_bytes: int) -> int:
    if audio_bytes < MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES:
        return 1
    return max(2, math.ceil(audio_bytes / _transcription_stream_copy_target_bytes()))


def _transcription_stream_copy_min_chunk_count(
    *,
    duration_seconds: float,
    audio_bytes: int,
    chunk_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_SECONDS,
    overlap_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
) -> int:
    duration_limited_count = len(
        _chunk_time_windows(
            duration_seconds,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
        )
    )
    return max(
        _transcription_stream_copy_chunk_count(audio_bytes),
        duration_limited_count,
    )


def _transcription_stream_copy_windows(
    *,
    duration_seconds: float,
    audio_bytes: int,
    chunk_count: int | None = None,
    chunk_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_SECONDS,
    overlap_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
) -> list[tuple[float, float, float]]:
    if duration_seconds <= 0:
        return []
    duration_limited_windows = _chunk_time_windows(
        duration_seconds,
        chunk_seconds=chunk_seconds,
        overlap_seconds=overlap_seconds,
    )
    minimum_count = _transcription_stream_copy_min_chunk_count(
        duration_seconds=duration_seconds,
        audio_bytes=audio_bytes,
        chunk_seconds=chunk_seconds,
        overlap_seconds=overlap_seconds,
    )
    count = (
        max(int(chunk_count), minimum_count)
        if chunk_count is not None
        else minimum_count
    )
    if count == len(duration_limited_windows):
        return duration_limited_windows

    overlap = max(
        0.0,
        min(
            float(overlap_seconds),
            duration_seconds / count,
        ),
    )
    windows: list[tuple[float, float, float]] = []
    for index in range(count):
        natural_start = 0.0 if index == 0 else duration_seconds * index / count
        natural_end = (
            duration_seconds
            if index == count - 1
            else duration_seconds * (index + 1) / count
        )
        start = natural_start if index == 0 else max(0.0, natural_start - overlap)
        if natural_end > start:
            windows.append(
                (
                    start,
                    natural_end,
                    0.0 if index == 0 else natural_start - start,
                )
            )
    return windows


def _audio_content_type_for_filename(filename: str, fallback: str = "") -> str:
    extension = _audio_extension(filename)
    if extension == "mp3":
        return "audio/mpeg"
    if extension in {"m4a", "mp4"}:
        return "audio/mp4"
    if extension == "wav":
        return "audio/wav"
    if extension == "webm":
        return "audio/webm"
    return fallback or "application/octet-stream"


def _stream_copy_chunk_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix and suffix.lstrip(".") in SUPPORTED_AUDIO_EXTENSIONS:
        return suffix
    return ".m4a"


def _split_audio_for_transcription_stream_copy(
    *,
    input_path: Path,
    output_dir: Path,
    input_duration_seconds: float,
    input_audio_bytes: int,
    filename: str,
    content_type: str,
    chunk_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_SECONDS,
    overlap_seconds: int = UPLOAD_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
) -> list[AudioTranscriptionChunk]:
    """Split oversized transcription audio by stream copy without re-encoding."""

    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise VoiceSessionError(
            "Uploaded audio must be stream-split before transcription, but ffmpeg "
            "is not installed. Configure FFMPEG_BINARY or install imageio-ffmpeg."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = _stream_copy_chunk_suffix(filename)
    chunk_content_type = _audio_content_type_for_filename(
        f"chunk{suffix}",
        fallback=content_type,
    )
    chunk_count = _transcription_stream_copy_min_chunk_count(
        duration_seconds=input_duration_seconds,
        audio_bytes=input_audio_bytes,
        chunk_seconds=chunk_seconds,
        overlap_seconds=overlap_seconds,
    )
    while chunk_count <= MAX_STREAM_COPY_SPLIT_ATTEMPTS:
        windows = _transcription_stream_copy_windows(
            duration_seconds=input_duration_seconds,
            audio_bytes=input_audio_bytes,
            chunk_count=chunk_count,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
        )
        if not windows:
            raise VoiceSessionError(
                "Server-side transcription stream splitting produced no chunks."
            )
        chunks: list[AudioTranscriptionChunk] = []
        oversized_chunk = False
        for index, (start_seconds, end_seconds, overlap) in enumerate(
            windows,
            start=1,
        ):
            output_path = output_dir / f"chunk-{index - 1:04d}{suffix}"
            duration = end_seconds - start_seconds
            command = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(input_path),
                "-t",
                f"{duration:.3f}",
                "-map",
                "0:a:0",
                "-vn",
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                str(output_path),
            ]
            _run_ffmpeg_audio_preparation(command)
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise VoiceSessionError(
                    "Server-side transcription stream split produced an empty chunk."
                )
            chunk_audio_bytes = output_path.stat().st_size
            if chunk_audio_bytes >= MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES:
                oversized_chunk = True
                break
            actual_duration = _audio_duration_seconds(output_path) or duration
            chunks.append(
                AudioTranscriptionChunk(
                    index=index,
                    filename=output_path.name,
                    content_type=chunk_content_type,
                    start_seconds=start_seconds,
                    duration_seconds=actual_duration,
                    overlap_seconds=overlap,
                    path=output_path,
                    audio_bytes=chunk_audio_bytes,
                )
            )
        if not oversized_chunk:
            return chunks
        chunk_count += 1
    raise VoiceSessionError(
        "Uploaded audio cannot be split into API-safe transcription chunks "
        "without re-encoding."
    )


def _transcript_word_count(transcript: str) -> int:
    return len([part for part in transcript.split() if part])


def _ends_with_sentence_punctuation(transcript: str) -> bool:
    clean = transcript.strip().rstrip("\"')]}").strip()
    return bool(clean) and clean[-1] in ".!?"


def _normalized_transcript_words(transcript: str) -> list[str]:
    return [
        word
        for word in (
            _normalized_overlap_word(match.group(0))
            for match in _transcript_word_matches(transcript)
        )
        if word
    ]


def _has_repeated_transcription_ngram(transcript: str) -> bool:
    words = _normalized_transcript_words(transcript)
    if (
        len(words)
        < REPEATED_TRANSCRIPTION_NGRAM_WORDS * REPEATED_TRANSCRIPTION_NGRAM_COUNT
    ):
        return False
    counts: dict[tuple[str, ...], int] = {}
    for index in range(len(words) - REPEATED_TRANSCRIPTION_NGRAM_WORDS + 1):
        ngram = tuple(words[index : index + REPEATED_TRANSCRIPTION_NGRAM_WORDS])
        counts[ngram] = counts.get(ngram, 0) + 1
        if counts[ngram] >= REPEATED_TRANSCRIPTION_NGRAM_COUNT:
            return True
    return False


def _chunk_transcription_validation_issue(
    chunk: AudioTranscriptionChunk,
    transcript: str,
) -> str | None:
    transcript_words = _transcript_word_count(transcript)
    if chunk.duration_seconds >= MIN_CHUNK_TRANSCRIPTION_VALIDATION_SECONDS:
        minimum_words = math.ceil(
            (chunk.duration_seconds / 60) * MIN_CHUNK_TRANSCRIPTION_WORDS_PER_MINUTE
        )
        if transcript_words < minimum_words:
            return "Chunk transcript is implausibly short for its audio duration."
    if _has_repeated_transcription_ngram(transcript):
        return "Chunk transcript contains a repeated phrase loop."
    return None


def _chunk_transcription_note(chunk: AudioTranscriptionChunk, total_chunks: int) -> str:
    start = _round_seconds(chunk.start_seconds)
    end = _round_seconds(chunk.start_seconds + chunk.duration_seconds)
    parts = [
        f"Audio chunk {chunk.index} of {total_chunks}; approximate source range {start}s to {end}s.",
    ]
    if chunk.overlap_seconds > 0:
        parts.append(
            f"The first ~{int(chunk.overlap_seconds)} seconds intentionally overlap the previous chunk for coverage."
        )
        parts.append(
            "Transcribe the entire chunk verbatim, including the overlapping opening speech; duplicate overlap text is removed later by the application."
        )
    return " ".join(parts)


def _chunk_result_metadata(
    chunk: AudioTranscriptionChunk,
    transcript: str,
    *,
    is_final_chunk: bool,
    audio_bytes: int | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    transcript_text = transcript.strip()
    transcript_chars = len(transcript_text)
    transcript_words = _transcript_word_count(transcript_text)
    if transcript_chars == 0:
        warnings.append("Chunk transcription returned no text.")
    validation_issue = _chunk_transcription_validation_issue(chunk, transcript_text)
    if validation_issue is not None:
        warnings.append(validation_issue)
    if (
        is_final_chunk
        and transcript_chars
        and not _ends_with_sentence_punctuation(transcript_text)
    ):
        warnings.append(
            "Final chunk transcript ends without sentence punctuation; verify recording end coverage."
        )
    return {
        "index": chunk.index,
        "filename": chunk.filename,
        "start_seconds": _round_seconds(chunk.start_seconds),
        "end_seconds": _round_seconds(chunk.start_seconds + chunk.duration_seconds),
        "duration_seconds": _round_seconds(chunk.duration_seconds),
        "overlap_seconds": _round_seconds(chunk.overlap_seconds),
        "audio_bytes": (
            _audio_transcription_chunk_bytes(chunk)
            if audio_bytes is None
            else audio_bytes
        ),
        "transcript_chars": transcript_chars,
        "transcript_words": transcript_words,
        "ends_with_sentence_punctuation": _ends_with_sentence_punctuation(
            transcript_text
        ),
        "warnings": warnings,
    }


def _repair_chunk_transcription_with_subchunks(
    *,
    chunk: AudioTranscriptionChunk,
    total_chunks: int,
    api_key: str,
    language: str,
    case_context: str,
    model: str,
    endpoint: str,
    safety_identifier: str,
    timeout_seconds: float,
    repair_dir: Path,
    validation_issue: str,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Repair a bad chunk transcription by re-transcribing smaller audio pieces."""

    repair_dir.mkdir(parents=True, exist_ok=True)
    source_path = chunk.path
    if source_path is None:
        source_path = repair_dir / f"source-{_safe_upload_filename(chunk.filename)}"
        source_path.write_bytes(_audio_transcription_chunk_content(chunk))

    warnings: list[str] = []
    try:
        repair_chunks = _split_audio_for_transcription_stream_copy(
            input_path=source_path,
            output_dir=repair_dir / "subchunks",
            input_duration_seconds=chunk.duration_seconds,
            input_audio_bytes=_audio_transcription_chunk_bytes(chunk),
            filename=chunk.filename,
            content_type=chunk.content_type,
            chunk_seconds=UPLOAD_TRANSCRIPTION_REPAIR_CHUNK_SECONDS,
            overlap_seconds=UPLOAD_TRANSCRIPTION_REPAIR_CHUNK_OVERLAP_SECONDS,
        )
    except VoiceSessionError as exc:
        return "", [], [f"Repair split failed: {exc}"]

    transcripts: list[str] = []
    repair_results: list[dict[str, Any]] = []
    for repair_chunk in repair_chunks:
        absolute_repair_chunk = replace(
            repair_chunk,
            start_seconds=chunk.start_seconds + repair_chunk.start_seconds,
        )
        repair_note = (
            f"{_chunk_transcription_note(absolute_repair_chunk, total_chunks)} "
            f"This is repair subchunk {repair_chunk.index} of {len(repair_chunks)} "
            f"for source chunk {chunk.index}, after the full chunk failed validation: "
            f"{validation_issue} Transcribe only the audio in this smaller repair "
            "subchunk verbatim."
        )
        transcription_response: AudioTranscriptionResponse | None = None
        subchunk_issue: str | None = None
        for attempt in range(MAX_UPLOAD_TRANSCRIPTION_REPAIR_SUBCHUNK_RETRIES + 1):
            attempt_note = repair_note
            if attempt > 0:
                attempt_note = (
                    f"{repair_note} Previous repair attempt failed validation: "
                    f"{subchunk_issue or 'invalid repair transcript'}"
                )
            transcription_response = _create_single_audio_transcription(
                api_key=api_key,
                audio_bytes=_audio_transcription_chunk_content(repair_chunk),
                filename=repair_chunk.filename,
                content_type=repair_chunk.content_type,
                language=language,
                case_context=case_context,
                model=model,
                endpoint=endpoint,
                safety_identifier=(
                    f"{safety_identifier}-chunk-{chunk.index}-repair-"
                    f"{repair_chunk.index}-attempt-{attempt + 1}"
                ),
                timeout_seconds=timeout_seconds,
                chunk_note=attempt_note,
                include_case_context=False,
            )
            subchunk_issue = _chunk_transcription_validation_issue(
                absolute_repair_chunk,
                transcription_response.text,
            )
            if subchunk_issue is None:
                break

        if transcription_response is None:
            warnings.append(
                f"Repair subchunk {repair_chunk.index} returned no transcript."
            )
            continue

        transcript = transcription_response.text
        if subchunk_issue is not None:
            warnings.append(
                f"Repair subchunk {repair_chunk.index} still failed validation: "
                f"{subchunk_issue}"
            )
        transcripts.append(transcript)
        repair_metadata = _chunk_result_metadata(
            absolute_repair_chunk,
            transcript,
            is_final_chunk=repair_chunk.index == len(repair_chunks),
        )
        repair_metadata["repair_parent_chunk_index"] = chunk.index
        repair_metadata["repair_subchunk_index"] = repair_chunk.index
        repair_metadata["repair_validation_passed"] = subchunk_issue is None
        repair_results.append(repair_metadata)

    return _join_chunk_transcripts(transcripts), repair_results, warnings


def _multipart_form_data(
    fields: Mapping[str, str],
    files: Mapping[str, tuple[str, bytes, str]] | None = None,
) -> tuple[bytes, str]:
    boundary = f"case-notes-voice-{secrets.token_hex(12)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                    "utf-8"
                ),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in (files or {}).items():
        safe_filename = _safe_upload_filename(filename)
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{safe_filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n".encode(
                    "utf-8"
                ),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


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


def _openai_timeout_message(*, action: str, timeout_seconds: float) -> str:
    return (
        f"{action} timed out after {int(timeout_seconds)} seconds while waiting "
        "for OpenAI. The audio was uploaded, but this server-side processing "
        "step did not complete. Retry the upload; the server processes long "
        "recordings in smaller chunks to reduce this risk."
    )


def _transcription_prompt(
    *,
    language: str,
    case_context: str,
    chunk_note: str = "",
    include_case_context: bool = True,
) -> str:
    context = _normalize_case_context(case_context)
    glossary = _case_context_glossary(context)[:MAX_TRANSCRIPTION_PROMPT_GLOSSARY_TERMS]
    parts = [
        "This audio belongs to a private Clara advisory case workspace.",
        "Transcribe faithfully. Preserve business names, family names, role names, numbers, and uncertainty.",
        f"Expected language: {language}.",
    ]
    if chunk_note:
        parts.append(chunk_note)
    if glossary:
        parts.extend(
            [
                "Preferred spellings / case glossary. Use these only when they match the audio:",
                "\n".join(f"- {term}" for term in glossary),
            ]
        )
    if include_case_context and context:
        parts.extend(
            [
                "Useful case vocabulary and context follows. Use it only to improve transcription spelling; do not add facts.",
                context[:1800],
            ]
        )
    return "\n".join(parts)


def _case_context_glossary(case_context: str) -> list[str]:
    """Extract a compact, conservative glossary from case context text."""

    terms: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str) -> None:
        candidate = value.strip().strip("-*#` .")
        if (
            not candidate
            or len(candidate) > MAX_TRANSCRIPTION_PROMPT_GLOSSARY_TERM_CHARS
        ):
            return
        if len(candidate) < 2:
            return
        if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", candidate):
            return
        lowered = candidate.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        terms.append(candidate)

    for raw_line in case_context.splitlines():
        line = raw_line.strip().strip("-*#` ")
        if not line:
            continue
        if ":" in line:
            _label, value = line.split(":", 1)
            add_candidate(value)
        else:
            add_candidate(line)
        if len(terms) >= MAX_TRANSCRIPTION_PROMPT_GLOSSARY_TERMS:
            break
    return terms


def _validate_transcription_request_audio(filename: str, audio_bytes: bytes) -> None:
    _validate_audio_upload(filename, audio_bytes)
    if len(audio_bytes) >= MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES:
        raise VoiceSessionError(
            "Prepared audio is larger than the OpenAI Transcriptions API "
            "25 MB limit."
        )


def _transcription_payload_text(payload: Mapping[str, Any]) -> str:
    text = str(payload.get("text", "") or "").strip()
    if text:
        return text
    raw_segments = payload.get("segments", [])
    if not isinstance(raw_segments, list):
        return ""
    return " ".join(
        str(segment.get("text", "") or "").strip()
        for segment in raw_segments
        if isinstance(segment, Mapping) and str(segment.get("text", "") or "").strip()
    )


def _create_single_audio_transcription(
    *,
    api_key: str,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str,
    case_context: str,
    model: str = DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
    endpoint: str = "https://api.openai.com/v1/audio/transcriptions",
    safety_identifier: str = "case-notes-voice-upload",
    timeout_seconds: float = OPENAI_UPLOAD_TRANSCRIPTION_TIMEOUT_SECONDS,
    chunk_note: str = "",
    include_case_context: bool = True,
) -> AudioTranscriptionResponse:
    """Transcribe one API-safe audio file through the OpenAI Audio API."""

    _validate_transcription_request_audio(filename, audio_bytes)
    fields = {
        "model": model,
        "response_format": "json",
        "temperature": "0",
    }
    fields["prompt"] = _transcription_prompt(
        language=language,
        case_context=case_context,
        chunk_note=chunk_note,
        include_case_context=include_case_context,
    )
    if language in SUPPORTED_TRANSCRIPTION_LANGUAGES:
        fields["language"] = language
    body, boundary = _multipart_form_data(
        fields,
        files={
            "file": (
                _safe_upload_filename(filename),
                audio_bytes,
                content_type or "application/octet-stream",
            )
        },
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
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceSessionError(
            f"Audio transcription failed: HTTP {exc.code}: {detail}"
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise VoiceSessionError(
            _openai_timeout_message(
                action="Audio transcription",
                timeout_seconds=timeout_seconds,
            )
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise VoiceSessionError(f"Audio transcription failed: {exc}") from exc
    transcript = _transcription_payload_text(payload)
    if not transcript:
        raise VoiceSessionError("Audio transcription returned no text.")
    return AudioTranscriptionResponse(text=transcript)


def _uploaded_audio_temp_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix and suffix.lstrip(".") in SUPPORTED_AUDIO_EXTENSIONS:
        return suffix
    return ".m4a"


def _normalized_overlap_word(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _transcript_word_matches(text: str) -> list[re.Match[str]]:
    return list(re.finditer(r"\S+", text))


def _find_duplicate_chunk_overlap(
    previous_text: str,
    transcript: str,
) -> tuple[list[re.Match[str]], list[re.Match[str]], int, int] | None:
    previous_matches = _transcript_word_matches(previous_text)
    current_matches = _transcript_word_matches(transcript)
    max_count = min(
        MAX_TRANSCRIPTION_OVERLAP_DEDUP_WORDS,
        len(previous_matches),
        len(current_matches),
    )
    if max_count < MIN_TRANSCRIPTION_OVERLAP_DEDUP_WORDS:
        return None

    previous_words = [
        _normalized_overlap_word(match.group(0))
        for match in previous_matches[-MAX_TRANSCRIPTION_OVERLAP_DEDUP_WORDS:]
    ]
    current_words = [
        _normalized_overlap_word(match.group(0))
        for match in current_matches[:MAX_TRANSCRIPTION_OVERLAP_DEDUP_WORDS]
    ]
    best_prefix_count = 0
    best_suffix_count = 0
    best_score = 0.0
    for prefix_count in range(MIN_TRANSCRIPTION_OVERLAP_DEDUP_WORDS, max_count + 1):
        current_prefix = current_words[:prefix_count]
        if not any(current_prefix):
            continue
        min_suffix_count = max(
            MIN_TRANSCRIPTION_OVERLAP_DEDUP_WORDS,
            prefix_count - 12,
        )
        max_suffix_count = min(len(previous_words), prefix_count + 12)
        for suffix_count in range(min_suffix_count, max_suffix_count + 1):
            previous_suffix = previous_words[-suffix_count:]
            if not any(previous_suffix):
                continue
            score = SequenceMatcher(
                None,
                previous_suffix,
                current_prefix,
                autojunk=False,
            ).ratio()
            if score < TRANSCRIPTION_OVERLAP_DEDUP_SIMILARITY:
                continue
            if score > best_score or (
                score == best_score and prefix_count > best_prefix_count
            ):
                best_prefix_count = prefix_count
                best_suffix_count = suffix_count
                best_score = score

    if best_prefix_count == 0:
        return None
    return previous_matches, current_matches, best_suffix_count, best_prefix_count


def _replace_duplicate_chunk_overlap(
    previous_text: str,
    transcript: str,
) -> tuple[str, str]:
    duplicate = _find_duplicate_chunk_overlap(previous_text, transcript)
    if duplicate is None:
        return previous_text.strip(), transcript.strip()
    previous_matches, _current_matches, suffix_count, _prefix_count = duplicate
    previous_cut_start = previous_matches[-suffix_count].start()
    return previous_text[:previous_cut_start].rstrip(), transcript.strip()


def _join_chunk_transcripts(transcripts: list[str]) -> str:
    joined_text = ""
    for transcript in transcripts:
        clean_transcript = transcript.strip()
        if not clean_transcript:
            continue
        if not joined_text:
            joined_text = clean_transcript
            continue
        joined_text, clean_transcript = _replace_duplicate_chunk_overlap(
            joined_text,
            clean_transcript,
        )
        if clean_transcript:
            joined_text = (
                f"{joined_text}\n\n{clean_transcript}"
                if joined_text
                else clean_transcript
            )
    return joined_text


def _transcription_status(warnings: list[str]) -> str:
    return "warning" if warnings else "complete"


def _single_transcription_metadata(
    *,
    filename: str,
    audio_bytes: int,
    duration_seconds: float,
    transcript: str,
    transcription_model: str,
) -> dict[str, Any]:
    chunk = AudioTranscriptionChunk(
        index=1,
        filename=filename,
        content_type="",
        content=b"",
        start_seconds=0.0,
        duration_seconds=duration_seconds,
        overlap_seconds=0.0,
    )
    chunk_metadata = _chunk_result_metadata(
        chunk,
        transcript,
        is_final_chunk=True,
        audio_bytes=audio_bytes,
    )
    warnings = list(chunk_metadata["warnings"])
    return {
        "schema_version": 1,
        "status": _transcription_status(warnings),
        "mode": "single",
        "transcription_model": transcription_model,
        "transcription_strategy": "clean_text_only",
        "source_duration_seconds": _round_seconds(duration_seconds),
        "chunk_count": 1,
        "chunk_overlap_seconds": 0,
        "coverage_start_seconds": 0,
        "coverage_end_seconds": _round_seconds(duration_seconds),
        "coverage_complete": True,
        "warnings": warnings,
        "chunks": [chunk_metadata],
    }


def _chunked_transcription_metadata(
    *,
    source_duration_seconds: float,
    chunks: list[AudioTranscriptionChunk],
    chunk_results: list[dict[str, Any]],
    transcription_model: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    for chunk_result in chunk_results:
        warnings.extend(str(item) for item in chunk_result.get("warnings", []))
    coverage_start = chunks[0].start_seconds if chunks else None
    coverage_end = (
        max(chunk.start_seconds + chunk.duration_seconds for chunk in chunks)
        if chunks
        else None
    )
    coverage_complete = (
        coverage_start is not None
        and coverage_start <= 0.001
        and coverage_end is not None
        and coverage_end >= source_duration_seconds - 1
    )
    if not coverage_complete:
        warnings.append("Chunk windows do not cover the full source audio duration.")
    return {
        "schema_version": 1,
        "status": _transcription_status(warnings),
        "mode": "chunked",
        "transcription_model": transcription_model,
        "transcription_strategy": "clean_text_only",
        "source_duration_seconds": _round_seconds(source_duration_seconds),
        "chunk_count": len(chunks),
        "chunk_overlap_seconds": _round_seconds(
            max((chunk.overlap_seconds for chunk in chunks), default=0.0)
        ),
        "coverage_start_seconds": _round_seconds(coverage_start),
        "coverage_end_seconds": _round_seconds(coverage_end),
        "coverage_complete": coverage_complete,
        "warnings": warnings,
        "chunks": chunk_results,
    }


def create_audio_transcription(
    *,
    api_key: str,
    audio_bytes: bytes | None = None,
    audio_path: Path | None = None,
    audio_size_bytes: int | None = None,
    filename: str,
    content_type: str,
    language: str,
    case_context: str,
    model: str = DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
    endpoint: str = "https://api.openai.com/v1/audio/transcriptions",
    safety_identifier: str = "case-notes-voice-upload",
    timeout_seconds: float = OPENAI_UPLOAD_TRANSCRIPTION_TIMEOUT_SECONDS,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    temporary_root: Path | None = None,
) -> AudioTranscriptionResult:
    """Transcribe uploaded audio as clean text for downstream Clara review."""

    def report_progress(**updates: Any) -> None:
        if progress_callback is not None:
            progress_callback(updates)

    safe_filename = _safe_upload_filename(filename)
    if audio_path is None:
        if audio_bytes is None:
            raise VoiceSessionError("Uploaded audio file is missing.")
        input_audio_bytes = len(audio_bytes)
        _validate_audio_upload_metadata(safe_filename, input_audio_bytes)
    else:
        input_audio_bytes = (
            audio_size_bytes
            if audio_size_bytes is not None
            else audio_path.stat().st_size
        )
        _validate_audio_upload_metadata(safe_filename, input_audio_bytes)
    if temporary_root is None:
        temporary_directory = tempfile.TemporaryDirectory(prefix="case-notes-audio-")
    else:
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="transcription-",
            dir=temporary_root,
        )
    with temporary_directory as temp_dir_name:
        report_progress(
            phase="preparing",
            phase_label="Preparing audio",
            message="Preparing uploaded audio for transcription.",
            progress_percent=0,
        )
        temp_dir = Path(temp_dir_name)
        if audio_path is None:
            input_path = (
                temp_dir / f"upload{_uploaded_audio_temp_suffix(safe_filename)}"
            )
            input_path.write_bytes(audio_bytes or b"")
        else:
            input_path = audio_path
        uploaded_filename = safe_filename
        source_audio = _duration_bearing_audio_source(
            input_path=input_path,
            output_dir=temp_dir / "normalized",
            filename=uploaded_filename,
            content_type=content_type,
            audio_bytes=input_audio_bytes,
        )
        if source_audio.was_normalized:
            LOGGER.info(
                "Normalized uploaded audio for readable duration metadata: "
                "filename=%s normalized_filename=%s duration_seconds=%.3f",
                safe_filename,
                source_audio.filename,
                source_audio.duration_seconds,
            )
            report_progress(
                phase="preparing",
                phase_label="Preparing audio",
                message=(
                    "Converted uploaded audio to a duration-bearing WAV before "
                    "transcription."
                ),
                progress_percent=0,
                source_duration_seconds=_round_seconds(source_audio.duration_seconds),
            )
        input_path = source_audio.path
        safe_filename = source_audio.filename
        content_type = source_audio.content_type
        input_audio_bytes = source_audio.audio_bytes
        duration_seconds = source_audio.duration_seconds

        must_prepare = (
            input_audio_bytes >= MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES
            or duration_seconds > UPLOAD_TRANSCRIPTION_CHUNK_SECONDS
        )
        request_payload: AudioTranscriptionPayload | None = None
        if not must_prepare:
            request_payload = AudioTranscriptionPayload(
                path=input_path,
                filename=safe_filename,
                content_type=content_type or "application/octet-stream",
                content=(
                    audio_bytes
                    if audio_bytes is not None and not source_audio.was_normalized
                    else input_path.read_bytes()
                ),
            )

        if request_payload is not None:
            report_progress(
                phase="transcribing",
                phase_label="Transcription",
                message="Transcribing uploaded audio.",
                completed_steps=0,
                total_steps=1,
                progress_percent=0,
                source_duration_seconds=_round_seconds(duration_seconds),
            )
            transcription_response = _create_single_audio_transcription(
                api_key=api_key,
                audio_bytes=request_payload.content,
                filename=request_payload.filename,
                content_type=request_payload.content_type,
                language=language,
                case_context=case_context,
                model=model,
                endpoint=endpoint,
                safety_identifier=safety_identifier,
                timeout_seconds=timeout_seconds,
            )
            metadata = _single_transcription_metadata(
                filename=request_payload.filename,
                audio_bytes=len(request_payload.content),
                duration_seconds=duration_seconds,
                transcript=transcription_response.text,
                transcription_model=model,
            )
            metadata["language"] = language
            metadata["audio_preparation"] = (
                "duration_normalized_wav"
                if source_audio.was_normalized
                else "original_upload"
            )
            metadata["uploaded_audio_filename"] = uploaded_filename
            metadata["transcribed_audio_filename"] = source_audio.filename
            return AudioTranscriptionResult(
                text=transcription_response.text,
                metadata=metadata,
                raw_transcription_text=transcription_response.text,
            )

        report_progress(
            phase="preparing",
            phase_label="Splitting audio",
            message="Splitting uploaded audio without re-encoding before transcription.",
            progress_percent=0,
            source_duration_seconds=_round_seconds(duration_seconds),
        )
        chunk_dir = temp_dir / "chunks"
        chunks = _split_audio_for_transcription_stream_copy(
            input_path=input_path,
            output_dir=chunk_dir,
            input_duration_seconds=duration_seconds,
            input_audio_bytes=input_audio_bytes,
            filename=safe_filename,
            content_type=content_type,
        )
        LOGGER.info(
            "Transcribing uploaded audio in %s chunks: filename=%s duration_seconds=%.3f",
            len(chunks),
            safe_filename,
            duration_seconds,
        )
        total_steps = len(chunks)
        transcripts: list[str] = []
        chunk_results: list[dict[str, Any]] = []
        for chunk in chunks:
            completed_steps = chunk.index - 1
            report_progress(
                phase="transcribing",
                phase_label="Transcription",
                message=f"Transcribing chunk {chunk.index} of {len(chunks)}.",
                completed_chunks=chunk.index - 1,
                current_chunk=chunk.index,
                total_chunks=len(chunks),
                completed_steps=completed_steps,
                total_steps=total_steps,
                progress_percent=round((completed_steps / total_steps) * 100),
                source_duration_seconds=_round_seconds(duration_seconds),
            )
            chunk_content = _audio_transcription_chunk_content(chunk)
            chunk_note = _chunk_transcription_note(chunk, len(chunks))
            transcription_response: AudioTranscriptionResponse | None = None
            validation_issue: str | None = None
            for attempt in range(MAX_UPLOAD_TRANSCRIPTION_CHUNK_RETRIES + 1):
                retry_note = chunk_note
                if attempt > 0:
                    retry_note = (
                        f"{chunk_note} Previous attempt was rejected because: "
                        f"{validation_issue or 'invalid chunk transcript'} "
                        "Transcribe the full chunk verbatim."
                    )
                    report_progress(
                        phase="transcribing",
                        phase_label="Transcription",
                        message=(
                            f"Retrying chunk {chunk.index} of {len(chunks)} "
                            f"after validation failure."
                        ),
                        completed_chunks=chunk.index - 1,
                        current_chunk=chunk.index,
                        total_chunks=len(chunks),
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                        progress_percent=round((completed_steps / total_steps) * 100),
                        source_duration_seconds=_round_seconds(duration_seconds),
                    )
                transcription_response = _create_single_audio_transcription(
                    api_key=api_key,
                    audio_bytes=chunk_content,
                    filename=chunk.filename,
                    content_type=chunk.content_type,
                    language=language,
                    case_context=case_context,
                    model=model,
                    endpoint=endpoint,
                    safety_identifier=(
                        f"{safety_identifier}-chunk-{chunk.index}-attempt-{attempt + 1}"
                    ),
                    timeout_seconds=timeout_seconds,
                    chunk_note=retry_note,
                )
                validation_issue = _chunk_transcription_validation_issue(
                    chunk,
                    transcription_response.text,
                )
                if validation_issue is None:
                    break
            if transcription_response is None:
                raise VoiceSessionError("Audio transcription returned no text.")
            if validation_issue is not None:
                report_progress(
                    phase="repairing",
                    phase_label="Repairing transcription",
                    message=(
                        f"Repairing chunk {chunk.index} of {len(chunks)} "
                        "with smaller audio subchunks after validation failure."
                    ),
                    completed_chunks=chunk.index - 1,
                    current_chunk=chunk.index,
                    total_chunks=len(chunks),
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    progress_percent=round((completed_steps / total_steps) * 100),
                    source_duration_seconds=_round_seconds(duration_seconds),
                )
                repair_text, repair_results, repair_warnings = (
                    _repair_chunk_transcription_with_subchunks(
                        chunk=chunk,
                        total_chunks=len(chunks),
                        api_key=api_key,
                        language=language,
                        case_context=case_context,
                        model=model,
                        endpoint=endpoint,
                        safety_identifier=safety_identifier,
                        timeout_seconds=timeout_seconds,
                        repair_dir=temp_dir / "repairs" / f"chunk-{chunk.index:04d}",
                        validation_issue=validation_issue,
                    )
                )
                if repair_text.strip():
                    transcript = repair_text
                    chunk_metadata = _chunk_result_metadata(
                        chunk,
                        transcript,
                        is_final_chunk=chunk.index == len(chunks),
                    )
                    repair_validation_issue = _chunk_transcription_validation_issue(
                        chunk,
                        transcript,
                    )
                    if repair_validation_issue is not None:
                        chunk_metadata["warnings"].append(
                            "Repair transcript still failed full-chunk validation: "
                            f"{repair_validation_issue}"
                        )
                    chunk_metadata["repair"] = {
                        "strategy": "smaller_audio_subchunks",
                        "trigger": validation_issue,
                        "subchunk_count": len(repair_results),
                        "warnings": repair_warnings,
                        "subchunks": repair_results,
                    }
                    transcripts.append(transcript)
                    chunk_results.append(chunk_metadata)
                    continue

                transcript = transcription_response.text
                chunk_metadata = _chunk_result_metadata(
                    chunk,
                    transcript,
                    is_final_chunk=chunk.index == len(chunks),
                )
                chunk_metadata["repair"] = {
                    "strategy": "preserve_invalid_transcript_after_failed_repair",
                    "trigger": validation_issue,
                    "warnings": repair_warnings
                    or ["Repair produced no usable subchunk transcript."],
                    "subchunks": repair_results,
                }
                transcripts.append(transcript)
                chunk_results.append(chunk_metadata)
                continue

            transcript = transcription_response.text
            transcripts.append(transcript)
            chunk_metadata = _chunk_result_metadata(
                chunk,
                transcript,
                is_final_chunk=chunk.index == len(chunks),
            )
            chunk_results.append(chunk_metadata)
        transcript = _join_chunk_transcripts(transcripts)
        if not transcript:
            raise VoiceSessionError("Audio transcription returned no text.")
    metadata = _chunked_transcription_metadata(
        source_duration_seconds=duration_seconds,
        chunks=chunks,
        chunk_results=chunk_results,
        transcription_model=model,
    )
    metadata["language"] = language
    metadata["audio_preparation"] = (
        "duration_normalized_wav" if source_audio.was_normalized else "original_upload"
    )
    metadata["uploaded_audio_filename"] = uploaded_filename
    metadata["transcribed_audio_filename"] = source_audio.filename
    return AudioTranscriptionResult(
        text=transcript,
        metadata=metadata,
        raw_transcription_text=transcript,
    )


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
        "language": language,
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


@router.post("/upload/chunks/{upload_id}")
async def upload_audio_chunk(
    upload_id: str,
    chunk_index: int = Form(...),
    audio_chunk: UploadFile = File(..., alias="audio"),
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Store one small browser-uploaded chunk for a large audio file."""

    chunk_path: Path | None = None
    chunk_written = False
    try:
        _cleanup_stale_chunked_uploads()
        metadata = _read_chunked_upload_metadata(upload_id, user)
        if str(metadata.get("status", "")).strip().lower() != "uploading":
            raise VoiceSessionError("Chunked upload is not accepting more chunks.")
        total_chunks = int(metadata["total_chunks"])
        if chunk_index < 0 or chunk_index >= total_chunks:
            raise VoiceSessionError("Invalid audio chunk index.")
        chunk_path = _chunked_upload_chunk_path(upload_id, chunk_index)
        received_chunks = {
            int(index)
            for index in metadata.get("received_chunks", [])
            if isinstance(index, int)
        }
        if chunk_index in received_chunks or chunk_path.exists():
            raise VoiceSessionError(
                f"Uploaded audio chunk {chunk_index + 1} was already received."
            )
        expected_chunk_bytes = _expected_chunk_bytes_for_index(metadata, chunk_index)
        chunk_bytes = await _write_upload_file_to_path(
            audio_chunk,
            chunk_path,
            max_bytes=expected_chunk_bytes,
            too_large_message=(
                f"Uploaded audio chunk {chunk_index + 1} is larger than expected."
            ),
        )
        chunk_written = True
        if chunk_bytes <= 0:
            raise VoiceSessionError("Uploaded audio chunk is empty.")
        if chunk_bytes != expected_chunk_bytes:
            chunk_path.unlink(missing_ok=True)
            raise VoiceSessionError(
                f"Uploaded audio chunk {chunk_index + 1} has an unexpected size."
            )
        received_chunks.add(chunk_index)
        metadata["received_chunks"] = sorted(received_chunks)
        chunk_bytes_by_index = metadata.get("chunk_bytes", {})
        if not isinstance(chunk_bytes_by_index, dict):
            chunk_bytes_by_index = {}
        chunk_hashes = metadata.get("chunk_sha256", {})
        if not isinstance(chunk_hashes, dict):
            chunk_hashes = {}
        chunk_bytes_by_index[str(chunk_index)] = chunk_bytes
        chunk_hashes[str(chunk_index)] = _file_sha256(chunk_path)
        metadata["chunk_bytes"] = chunk_bytes_by_index
        metadata["chunk_sha256"] = chunk_hashes
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_chunked_upload_metadata(upload_id, metadata)
    except (OSError, VoiceSessionError) as exc:
        if chunk_written and chunk_path is not None:
            _remove_voice_file(chunk_path)
        detail = (
            str(exc)
            if isinstance(exc, VoiceSessionError)
            else "The audio chunk could not be stored; its temporary copy was deleted."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    return JSONResponse(
        {
            "status": "received",
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "received_chunks": len(received_chunks),
            "total_chunks": total_chunks,
        }
    )


@router.post("/upload/chunks/{upload_id}/finish")
async def finish_chunked_audio_upload(
    upload_id: str,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Assemble a chunked audio upload and queue the existing transcription job."""

    try:
        _cleanup_stale_chunked_uploads()
        metadata = _read_chunked_upload_metadata(upload_id, user)
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
