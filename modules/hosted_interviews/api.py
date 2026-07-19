from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator

from modules.auth.dependencies import (
    require_site_permission,
    require_site_permission_for_request,
)
from modules.auth.session import AuthenticatedUser
from modules.case_notes_voice.api import (
    DEFAULT_UPLOAD_TRANSCRIPTION_MODEL,
)
from modules.case_notes_voice.api import VoiceSessionError as AudioTranscriptionError
from modules.case_notes_voice.api import (
    create_audio_transcription,
)
from modules.hosted_interviews.campaigns import (
    LEGACY_UNCLASSIFIED_CAMPAIGN_ID,
    UnknownInterviewCampaignError,
    build_campaign_interview_payload,
    get_interview_campaign,
    list_interview_campaigns,
)
from modules.notifications.resend_client import send_plain_text_email
from modules.openai_realtime import (
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_TRANSCRIPTION_MODEL,
    OpenAIRealtimeError,
    create_realtime_call_with_metadata,
)
from modules.utilities import config as utilities_config
from modules.utilities.cache import get_cache_dir
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = [
    "INTERVIEW_MODE_PLUGIN_IMPROVEMENT",
    "NOTIFICATION_EMAIL_ENV",
    "PLUGIN_IMPROVEMENT_CAMPAIGN_ID",
    "PreparedCampaignInterviewRequest",
    "PreparedInterviewRequest",
    "admin_router",
    "create_prepared_interview",
    "public_router",
    "site_router",
]

NOTIFICATION_EMAIL_ENV = "HOSTED_INTERVIEW_NOTIFICATION_EMAIL"
DEFAULT_MODEL = DEFAULT_REALTIME_MODEL
DEFAULT_TRANSCRIPTION_MODEL = DEFAULT_REALTIME_TRANSCRIPTION_MODEL
POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL = DEFAULT_UPLOAD_TRANSCRIPTION_MODEL
DEFAULT_TOKEN_TTL_HOURS = 7 * 24
DEFAULT_INTERVIEW_DURATION_SECONDS = 15 * 60
DEFAULT_INTERVIEW_REVIEW_TIMEOUT_SECONDS = 120
DEFAULT_INTERVIEW_REVIEW_RETRY_TIMEOUT_SECONDS = 180
PUBLIC_URL_TOKEN_PLACEHOLDER = "TOKEN"
MAX_PREPARED_TEXT_CHARS = 12_000
MAX_PREPARED_LIST_ITEMS = 24
MAX_EVENT_PAYLOAD_CHARS = 20_000
MAX_AUDIO_CHUNK_BYTES = 20 * 1024 * 1024
MAX_VIDEO_CHUNK_BYTES = 75 * 1024 * 1024
MAX_SIDEBAND_TURNS = 18
MAX_TRANSCRIPT_TAIL_CHARS = 5_000
MAX_PARTNER_WHISPER_CHARS = 240
STARTED_ATTEMPT_STALE_SECONDS = DEFAULT_INTERVIEW_DURATION_SECONDS + 5 * 60
SUPPORTED_LANGUAGES = {"it", "en", "fr", "de"}
INTERVIEW_STATUS_READY = "ready"
INTERVIEW_STATUS_STARTED = "started"
INTERVIEW_STATUS_COMPLETED = "completed"
INTERVIEW_STATUS_FAILED_TECHNICAL = "failed_technical"
INTERVIEW_STATUS_INCOMPLETE = "incomplete"
INTERVIEW_STATUS_UNUSABLE = "unusable"
PUBLIC_STATUS = {
    INTERVIEW_STATUS_READY,
    INTERVIEW_STATUS_STARTED,
    INTERVIEW_STATUS_COMPLETED,
    INTERVIEW_STATUS_FAILED_TECHNICAL,
    INTERVIEW_STATUS_INCOMPLETE,
    INTERVIEW_STATUS_UNUSABLE,
}
RETRYABLE_INTERVIEW_STATUSES = {
    INTERVIEW_STATUS_FAILED_TECHNICAL,
    INTERVIEW_STATUS_INCOMPLETE,
    INTERVIEW_STATUS_UNUSABLE,
}
POST_COMPLETION_EVENT_TYPES = {
    "post_call_interviewee_transcription_started",
    "post_call_interviewee_transcription_completed",
    "post_call_interviewee_transcription_failed",
    "post_call_completion_reclassified",
}
MIN_COMPLETED_INTERVIEWEE_WORDS = 25
MIN_PLUGIN_IMPROVEMENT_INTERVIEWEE_WORDS = 3
NON_SUBSTANTIVE_INTERVIEWER_TURN_NORMALIZED = {
    "daccord je vois",
    "d accord je vois",
    "einen moment",
    "gut ich verstehe",
    "one moment",
    "one possibility is",
    "right i see",
    "take",
    "un attimo",
    "un instant",
}
INTERVIEW_MODE_CASE = "case_interview"
INTERVIEW_MODE_PLUGIN_IMPROVEMENT = "plugin_improvement_interview"
INTERVIEW_MODE_RESEARCH = "research_interview"
PLUGIN_IMPROVEMENT_CAMPAIGN_ID = "plugin-improvement-v1"
INTERVIEW_REVIEW_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "hosted_interview_quality_review",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "summary",
            "overall_quality",
            "key_findings",
            "missed_opportunities",
            "evidence_backed_claims",
            "uncertainties",
            "contradictions",
            "follow_up_questions",
            "pipeline_improvements",
            "do_not_change",
        ],
        "properties": {
            "summary": {"type": "string"},
            "overall_quality": {
                "type": "string",
                "enum": ["strong", "usable", "weak", "failed"],
            },
            "key_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "severity",
                        "category",
                        "evidence",
                        "diagnosis",
                        "suggested_improvement",
                        "confidence",
                    ],
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "category": {"type": "string"},
                        "evidence": {"type": "string"},
                        "diagnosis": {"type": "string"},
                        "suggested_improvement": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                },
            },
            "missed_opportunities": {"type": "array", "items": {"type": "string"}},
            "evidence_backed_claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["claim", "supporting_quote", "confidence"],
                    "properties": {
                        "claim": {"type": "string"},
                        "supporting_quote": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                },
            },
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "contradictions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["description", "evidence", "confidence"],
                    "properties": {
                        "description": {"type": "string"},
                        "evidence": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                },
            },
            "follow_up_questions": {"type": "array", "items": {"type": "string"}},
            "pipeline_improvements": {"type": "array", "items": {"type": "string"}},
            "do_not_change": {"type": "array", "items": {"type": "string"}},
        },
    },
}

LOGGER = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")
site_router = APIRouter(prefix="/case-notes", tags=["hosted-interviews-site"])
public_router = APIRouter(
    prefix="/case-notes/api/interviews", tags=["hosted-interviews-public"]
)
admin_router = APIRouter(
    prefix="/case-notes/api/voice/interviews", tags=["hosted-interviews-admin"]
)


def _notification_email() -> str:
    """Return the operator recipient configured for interview notifications."""

    return str(os.getenv(NOTIFICATION_EMAIL_ENV, "") or "").strip()


class HostedInterviewError(RuntimeError):
    """Raised when a hosted interview cannot be prepared or used."""


class VoiceSessionError(RuntimeError):
    """Raised when hosted-interview external model work fails."""


class PreparedInterviewRequest(BaseModel):
    """Server-side package used to prepare one public interview link."""

    @model_validator(mode="before")
    @classmethod
    def _reject_external_change_request_binding(cls, value: Any) -> Any:
        if isinstance(value, Mapping) and "change_request_id" in value:
            raise ValueError("change_request_id is reserved for internal binding.")
        return value

    interview_campaign_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*$",
    )
    case_id: str = Field(default="test", max_length=120)
    case_name: str = Field(default="Test interview", max_length=240)
    participant_name: str = Field(default="", max_length=240)
    client_project: str = Field(default="", max_length=240)
    interview_title: str = Field(default="Interview", max_length=240)
    interviewee_role: str = Field(default="", max_length=240)
    interview_mode: str = Field(default=INTERVIEW_MODE_CASE, max_length=80)
    language: str = "it"
    purpose: str = Field(default="", max_length=MAX_PREPARED_TEXT_CHARS)
    participant_intro: str = Field(default="", max_length=MAX_PREPARED_TEXT_CHARS)
    background_context: str = Field(default="", max_length=MAX_PREPARED_TEXT_CHARS)
    hypotheses_to_test: list[str] = Field(default_factory=list)
    priority_topics: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    interviewer_name: str = Field(default="Clara", min_length=1, max_length=80)
    max_duration_seconds: int = Field(
        default=DEFAULT_INTERVIEW_DURATION_SECONDS,
        ge=60,
        le=DEFAULT_INTERVIEW_DURATION_SECONDS,
    )
    expires_in_hours: int = Field(default=DEFAULT_TOKEN_TTL_HOURS, ge=1, le=24 * 30)


class PreparedInterviewResponse(BaseModel):
    """Created interview link details returned to the authenticated preparer."""

    interview_campaign_id: str
    token: str
    public_url: str
    expires_at: str
    notification_email: str


class PreparedCampaignInterviewRequest(BaseModel):
    """Participant-specific fields used with one registered campaign brief."""

    case_id: str = Field(min_length=1, max_length=120)
    participant_name: str = Field(min_length=1, max_length=240)
    language: str = "it"
    interviewee_role: str = Field(default="", max_length=240)
    expires_in_hours: int = Field(default=DEFAULT_TOKEN_TTL_HOURS, ge=1, le=24 * 30)


class InterviewCampaignResponse(BaseModel):
    """Non-sensitive metadata for one selectable interview campaign."""

    interview_campaign_id: str
    name: str
    description: str
    interview_title: str
    interview_mode: str


class InterviewSessionRequest(BaseModel):
    """Browser SDP offer for a public hosted interview."""

    sdp: str = Field(min_length=1)
    language: str = "it"
    model: str = DEFAULT_MODEL


class InterviewEventRequest(BaseModel):
    """Small autosaved browser event."""

    attempt_id: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class CompleteInterviewRequest(BaseModel):
    """Final transcript and telemetry sent when the interviewee ends."""

    attempt_id: str = Field(min_length=1, max_length=120)
    user_transcript: str = Field(default="", max_length=200_000)
    assistant_transcript: str = Field(default="", max_length=200_000)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    transcript_words: int = Field(default=0, ge=0)
    audio_chunks: int = Field(default=0, ge=0)
    video_chunks: int = Field(default=0, ge=0)
    screen_capture_metadata: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HostedInterviewError("Invalid interview timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _interviews_root() -> Path:
    configured = os.getenv("HOSTED_INTERVIEWS_ROOT", "").strip()
    root = Path(configured) if configured else get_cache_dir("hosted_interviews")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_dir_for_hash(token_hash: str) -> Path:
    if not token_hash or any(char not in "0123456789abcdef" for char in token_hash):
        raise HostedInterviewError("Invalid interview token.")
    return _interviews_root() / "sessions" / token_hash


def _session_dir(token: str) -> Path:
    return _session_dir_for_hash(_token_hash(token.strip()))


def _record_path(session_dir: Path) -> Path:
    return session_dir / "interview.json"


def _events_path(session_dir: Path) -> Path:
    return session_dir / "events.ndjson"


def _completion_path(session_dir: Path) -> Path:
    return session_dir / "completed.json"


def _review_path(session_dir: Path) -> Path:
    return session_dir / "review.json"


def _review_error_path(session_dir: Path) -> Path:
    return session_dir / "review_error.json"


def _archive_retryable_attempt_files(session_dir: Path) -> None:
    attempt_files = [
        _events_path(session_dir),
        _completion_path(session_dir),
        _review_path(session_dir),
        _review_error_path(session_dir),
    ]
    audio_dir = session_dir / "audio"
    video_dir = session_dir / "video"
    has_attempt_data = (
        any(path.exists() for path in attempt_files)
        or (audio_dir.exists() and any(audio_dir.iterdir()))
        or (video_dir.exists() and any(video_dir.iterdir()))
    )
    if not has_attempt_data:
        return
    archive_dir = session_dir / "attempts" / _now().strftime("%Y%m%dT%H%M%S%fZ")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in attempt_files:
        if path.exists():
            path.replace(archive_dir / path.name)
    if audio_dir.exists() and any(audio_dir.iterdir()):
        audio_dir.replace(archive_dir / "audio")
    if video_dir.exists() and any(video_dir.iterdir()):
        video_dir.replace(archive_dir / "video")
    audio_dir.mkdir(exist_ok=True)
    video_dir.mkdir(exist_ok=True)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HostedInterviewError("Invalid or expired interview link.") from exc
    except json.JSONDecodeError as exc:
        raise HostedInterviewError("Interview record is not readable.") from exc
    if not isinstance(payload, dict):
        raise HostedInterviewError("Interview record is invalid.")
    return payload


def _clean_text(value: str, *, max_chars: int = MAX_PREPARED_TEXT_CHARS) -> str:
    return " ".join((value or "").replace("\x00", " ").split())[:max_chars]


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw_value in values[:MAX_PREPARED_LIST_ITEMS]:
        value = _clean_text(str(raw_value), max_chars=1_000)
        if value:
            cleaned.append(value)
    return cleaned


def _clean_language(value: str) -> str:
    language = (value or "it").strip().lower()
    return language if language in SUPPORTED_LANGUAGES else "it"


def _clean_interview_mode(value: str) -> str:
    normalized = (value or INTERVIEW_MODE_CASE).strip().lower().replace("-", "_")
    normalized = "_".join(normalized.split())
    if normalized in {"research", "research_interview", "survey"}:
        return INTERVIEW_MODE_RESEARCH
    if normalized in {
        "plugin_improvement",
        "plugin_improvement_interview",
    }:
        return INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    return INTERVIEW_MODE_CASE


def _resolve_openai_api_key() -> str:
    load_env_from_secrets_file()
    for env_path in (_repo_root() / ".env", Path.cwd() / ".env"):
        if env_path.exists():
            _load_simple_env_file(env_path)
    for key_name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "openAiKey"):
        api_key = os.getenv(key_name, "").strip()
        if api_key:
            return api_key
    raise VoiceSessionError("OpenAI API key is not configured on the server.")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _load_simple_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        clean_value = value.strip().strip("'\"")
        if clean_key and clean_value:
            os.environ.setdefault(clean_key, clean_value)


def _default_partner_model() -> str:
    naming_params = utilities_config.get_naming_params()
    return naming_params["gpt55Thinking"]


def _clean_partner_whisper(value: str) -> str:
    clean = " ".join(value.split())
    if len(clean) > MAX_PARTNER_WHISPER_CHARS:
        return clean[:MAX_PARTNER_WHISPER_CHARS].rstrip()
    return clean


def create_partner_whisper(
    *,
    api_key: str,
    prompt: str,
    model: str | None = None,
    endpoint: str = "https://api.openai.com/v1/responses",
    safety_identifier: str = "hosted-interview-partner",
    timeout_seconds: float = 8,
) -> str:
    """Ask the hosted-interview silent partner for one optional steering note."""

    body = json.dumps(
        {
            "model": model or _default_partner_model(),
            "input": prompt,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": safety_identifier,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceSessionError(
            f"Partner whisper failed: HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise VoiceSessionError(f"Partner whisper failed: {exc}") from exc
    payload = _json_object_from_text(_response_output_text(response_payload))
    whisper = payload.get("whisper")
    return _clean_partner_whisper(whisper if isinstance(whisper, str) else "")


def _default_review_model() -> str:
    model = os.getenv("HOSTED_INTERVIEW_REVIEW_MODEL", "").strip()
    if model:
        return model
    naming_params = utilities_config.get_naming_params()
    return naming_params["gpt55Thinking"]


def _output_url_for_record(record: Mapping[str, Any]) -> str:
    public_url = str(record.get("public_url", "")).strip().rstrip("/")
    return f"{public_url}/output" if public_url else ""


def _bundle_url_for_record(record: Mapping[str, Any]) -> str:
    public_url = str(record.get("public_url", "")).strip().rstrip("/")
    if not public_url:
        return ""
    marker = "/case-notes/interview/"
    if marker not in public_url:
        return f"{public_url}/bundle"
    return (
        public_url.replace(marker, "/case-notes/api/voice/interviews/", 1) + "/bundle"
    )


def _review_url_for_record(record: Mapping[str, Any]) -> str:
    public_url = str(record.get("public_url", "")).strip().rstrip("/")
    if not public_url:
        return ""
    marker = "/case-notes/interview/"
    if marker not in public_url:
        return f"{public_url}/review"
    return (
        public_url.replace(marker, "/case-notes/api/voice/interviews/", 1) + "/review"
    )


def _response_output_text(response_payload: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    output = response_payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str):
        chunks.append(output_text)
    return "".join(chunks).strip()


def _json_object_from_text(value: str) -> dict[str, Any]:
    clean = value.strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _public_safety_identifier(token_hash: str) -> str:
    return "hosted-interview-" + token_hash[:32]


def _prepared_payload(
    payload: PreparedInterviewRequest,
    *,
    token_hash: str,
    created_by: str,
    public_url: str,
    now: datetime,
    change_request_id: str,
) -> dict[str, Any]:
    expires_at = now + timedelta(hours=payload.expires_in_hours)
    return {
        "schema_version": 2,
        "interview_campaign_id": payload.interview_campaign_id,
        "token_hash": token_hash,
        "token_hint": token_hash[:8],
        "created_at": _iso(now),
        "expires_at": _iso(expires_at),
        "created_by": created_by,
        "status": "ready",
        "public_url": public_url,
        "notification_email": _notification_email(),
        "case_id": _clean_text(payload.case_id, max_chars=120) or "test",
        "case_name": _clean_text(payload.case_name, max_chars=240) or "Test interview",
        "participant_name": _clean_text(payload.participant_name, max_chars=240),
        "client_project": _clean_text(payload.client_project, max_chars=240),
        "interview_title": _clean_text(payload.interview_title, max_chars=240)
        or "Interview",
        "interviewee_role": _clean_text(payload.interviewee_role, max_chars=240),
        "interview_mode": _clean_interview_mode(payload.interview_mode),
        "language": _clean_language(payload.language),
        "purpose": _clean_text(payload.purpose),
        "participant_intro": _clean_text(payload.participant_intro),
        "background_context": _clean_text(payload.background_context),
        "hypotheses_to_test": _clean_list(payload.hypotheses_to_test),
        "priority_topics": _clean_list(payload.priority_topics),
        "questions": _clean_list(payload.questions),
        "red_flags": _clean_list(payload.red_flags),
        "boundaries": _clean_list(payload.boundaries),
        "interviewer_name": _clean_text(payload.interviewer_name, max_chars=80)
        or "Clara",
        "max_duration_seconds": payload.max_duration_seconds,
        "change_request_id": change_request_id,
    }


def create_prepared_interview(
    payload: PreparedInterviewRequest,
    *,
    created_by: str = "",
    public_url_base: str = "https://mparanza.com/case-notes/interview",
    now: datetime | None = None,
    change_request_id: str = "",
) -> tuple[str, dict[str, Any]]:
    """Create and persist one no-login public interview link."""

    timestamp = now or _now()
    clean_change_request_id = change_request_id.strip().upper()
    if (
        clean_change_request_id
        and re.fullmatch(r"CR-[1-9][0-9]*", clean_change_request_id) is None
    ):
        raise ValueError("Invalid internal change-request binding.")
    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    clean_base = public_url_base.rstrip("/")
    public_url = f"{clean_base}/{token}"
    session_dir = _session_dir_for_hash(token_hash)
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "audio").mkdir(exist_ok=True)
    (session_dir / "video").mkdir(exist_ok=True)
    record = _prepared_payload(
        payload,
        token_hash=token_hash,
        created_by=created_by,
        public_url=public_url,
        now=timestamp,
        change_request_id=clean_change_request_id,
    )
    _write_json(_record_path(session_dir), record)
    return token, record


def _load_record_for_token(
    token: str, *, allow_completed: bool = True
) -> dict[str, Any]:
    clean_token = token.strip()
    if not clean_token:
        raise HostedInterviewError("Missing interview token.")
    record = _read_json(_record_path(_session_dir(clean_token)))
    record.setdefault("interview_campaign_id", LEGACY_UNCLASSIFIED_CAMPAIGN_ID)
    status_value = str(record.get("status", ""))
    if status_value == "revoked":
        raise HostedInterviewError("This interview link has been revoked.")
    if status_value == INTERVIEW_STATUS_COMPLETED and not allow_completed:
        raise HostedInterviewError("This interview has already been completed.")
    if status_value not in PUBLIC_STATUS and status_value != "revoked":
        raise HostedInterviewError("This interview link is not active.")
    expires_at = _parse_iso_timestamp(str(record.get("expires_at", "")))
    if expires_at <= _now():
        raise HostedInterviewError("This interview link has expired.")
    return record


def _new_attempt_id() -> str:
    return secrets.token_urlsafe(18)


def _started_attempt_is_stale(
    record: Mapping[str, Any], *, now: datetime | None = None
) -> bool:
    if str(record.get("status", "")) != INTERVIEW_STATUS_STARTED:
        return False
    started_at = str(record.get("started_at", "")).strip()
    if not started_at:
        return True
    try:
        parsed = _parse_iso_timestamp(started_at)
    except HostedInterviewError:
        return True
    return parsed + timedelta(seconds=STARTED_ATTEMPT_STALE_SECONDS) <= (now or _now())


def _active_attempt_record(token: str, attempt_id: str) -> dict[str, Any]:
    record = _load_record_for_token(token, allow_completed=True)
    if str(record.get("status", "")) != INTERVIEW_STATUS_STARTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview does not have an active started attempt.",
        )
    expected_attempt_id = str(record.get("active_attempt_id", "")).strip()
    if not attempt_id.strip() or attempt_id.strip() != expected_attempt_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This interview attempt is no longer active.",
        )
    return record


def _save_record_for_token(token: str, record: Mapping[str, Any]) -> None:
    _write_json(_record_path(_session_dir(token)), record)


def _append_event(token: str, event_type: str, payload: Mapping[str, Any]) -> None:
    session_dir = _session_dir(token)
    session_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "captured_at": _iso(_now()),
        "event_type": _clean_text(event_type, max_chars=80),
        "payload": payload,
    }
    with _events_path(session_dir).open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        )


def _brief_lines(record: Mapping[str, Any]) -> list[str]:
    list_fields = [
        ("Hypotheses to test", record.get("hypotheses_to_test", [])),
        ("Priority topics", record.get("priority_topics", [])),
        ("Prepared questions", record.get("questions", [])),
        ("Red flags", record.get("red_flags", [])),
        ("Boundaries / do not ask", record.get("boundaries", [])),
    ]
    lines = [
        f"Interview campaign id: {record.get('interview_campaign_id', LEGACY_UNCLASSIFIED_CAMPAIGN_ID)}",
        f"Case id: {record.get('case_id', '')}",
        f"Case name: {record.get('case_name', '')}",
        f"Client/project: {record.get('client_project', '')}",
        f"Interview title: {record.get('interview_title', '')}",
        f"Interviewee role: {record.get('interviewee_role', '')}",
        f"Interview mode: {_clean_interview_mode(str(record.get('interview_mode', '')))}",
        f"Purpose: {record.get('purpose', '')}",
        f"Background context: {record.get('background_context', '')}",
    ]
    for label, values in list_fields:
        if isinstance(values, list) and values:
            lines.append(label + ":")
            lines.extend(f"- {item}" for item in values if isinstance(item, str))
    return [line for line in lines if line.strip() and not line.endswith(": ")]


def _thinking_bridge_examples(language: str) -> str:
    normalized = language.strip().lower()
    if normalized.startswith("it"):
        return "'Un attimo.' or 'Va bene, capisco.'"
    if normalized.startswith("fr"):
        return "'Un instant.' or 'D’accord, je vois.'"
    if normalized.startswith("de"):
        return "'Einen Moment.' or 'Gut, ich verstehe.'"
    return "'One moment.' or 'Right, I see.'"


def _interview_mode_instructions(record: Mapping[str, Any]) -> list[str]:
    mode = _clean_interview_mode(str(record.get("interview_mode", "")))
    if mode == INTERVIEW_MODE_RESEARCH:
        return [
            "Mode: research interview.",
            "Objective: understand this participant's perspective while naturally covering the shared research dimensions well enough to compare across participants later.",
            "Preserve comparability without sounding scripted. If a shared dimension is missing, reach it through the conversation rather than forcing a survey-style item.",
            "Capture language, examples, objections, use cases, and differences that may become useful themes or segments in the cross-interview synthesis.",
            "The prepared brief and boundaries determine whether a product or service should be discussed. Do not impose a generic product ban, and do not introduce sales language outside the prepared scope.",
        ]
    return [
        "Mode: case interview.",
        "Objective: understand this specific situation deeply: context, constraints, chronology, decisions, risks, bottlenecks, and unresolved questions.",
        "Follow the case where it leads. Comparability with other interviews is less important than representing this situation accurately and usefully.",
        "The likely output is a case note, advisory memo, or decision input, so preserve nuance and uncertainty.",
    ]


def _plugin_improvement_closing_handoff(language: str) -> str:
    normalized = language.strip().lower()
    if normalized.startswith("it"):
        return 'Grazie. Premi "Termina e salva" ora.'
    if normalized.startswith("fr"):
        return "Merci. Appuyez maintenant sur « End and save »."
    if normalized.startswith("de"):
        return "Vielen Dank. Klicken Sie jetzt auf „End and save“."
    return 'Thank you. Press "End and save" now.'


def _plugin_improvement_instructions(record: Mapping[str, Any], language: str) -> str:
    """Return the short, two-question-response-turn suggestion contract."""

    brief = "\n".join(_brief_lines(record))
    closing_handoff = _plugin_improvement_closing_handoff(language)
    return "\n\n".join(
        [
            "You are Mparanza's hosted AI interviewer for one plugin improvement suggestion.",
            "Use any concrete opportunity details already present in the prepared brief. Do not make the participant repeat details they have already supplied.",
            "There is a hard maximum of two interviewer question-response turns for the whole interview.",
            "Each question-response turn must contain exactly one short question.",
            "For the opening, inspect the background context. If it already contains a concrete requested behavior, ask for the single most important missing implementation detail. Otherwise use the single prepared question as the fallback opening.",
            "After the first answer, decide whether one implementation-relevant detail is still essential. If not, close immediately. If so, ask one short adaptive follow-up and no other question.",
            "A clarification or rephrasing uses the optional follow-up. After any follow-up answer, close immediately without another question.",
            "Do not ask a generic final question, ask whether anything was missed, summarize as a question, or cover the priority topics as a checklist.",
            f"Every closing must contain no question and end with exactly: {closing_handoff}",
            "The browser has a hard one-minute limit. Finish earlier as soon as the answer is usable.",
            "Respect every prepared boundary. Never request client material, identifying details, files, credentials, or secrets.",
            f"Use this configured language for the whole interview: {language}.",
            "Prepared interview brief:",
            brief or "(No prepared brief supplied.)",
        ]
    )


def _interview_instructions(record: Mapping[str, Any], language: str) -> str:
    if (
        _clean_interview_mode(str(record.get("interview_mode", "")))
        == INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    ):
        return _plugin_improvement_instructions(record, language)
    brief = "\n".join(_brief_lines(record))
    thinking_bridge_examples = _thinking_bridge_examples(language)
    interviewer_name = (
        _clean_text(str(record.get("interviewer_name", "")), max_chars=80) or "Clara"
    )
    max_duration_seconds = int(
        record.get("max_duration_seconds", DEFAULT_INTERVIEW_DURATION_SECONDS)
    )
    duration_minutes = max(1, (max_duration_seconds + 59) // 60)
    synthesis_minute = max(1, duration_minutes - 3)
    closing_minute = max(synthesis_minute, duration_minutes - 1)
    return "\n\n".join(
        [
            f"You are {interviewer_name}'s hosted interview voice interviewer.",
            "You are speaking directly with an external interviewee who opened a public browser link. Be calm, respectful, concise, and professional.",
            "This is a structured interview, not an interrogation. Your job is to build a faithful understanding of the interviewee's point of view.",
            "Use examples, facts, roles, timings, metrics, decisions, risks, and exceptions only when they help clarify or verify that understanding. Do not collect them as a proof checklist.",
            "Interview mode changes the objective, not the posture. In every mode, avoid checklist behavior, stacked questions, premature proof demands, and making the interviewee feel inspected.",
            *_interview_mode_instructions(record),
            "Use the prepared interview brief as private context. Do not recite it. Do not expose hidden hypotheses unless a direct question requires context.",
            "Ask for one cognitive task at a time. A turn can ask for a thesis, a clarification, a distinction, an example, or a metric, but never several of these at once.",
            "Keep questions short enough for a phone call. Avoid stacked questions that combine examples, owners, KPIs, decision rules, and rationale in one turn.",
            "After asking a question, stop speaking and give the interviewee time to think. Do not fill short silences by rephrasing the question unless the interviewee seems confused or asks for clarification.",
            "Prefer open questions. Use closed yes/no or either/or questions only to confirm a narrow point; if you use one, follow with a brief why/how question when useful.",
            "Adapt intelligently to the answer. Do not routinely paraphrase or summarize the interviewee before each next question; that makes the interview feel mechanical.",
            "Use brief natural acknowledgements for clear answers, then ask the most useful next question. Reflect back only when the answer is complex, ambiguous, surprising, internally inconsistent, or important enough that confirming the meaning will improve the interview.",
            "When you do reflect back, keep it short and make it earn its place: confirm one specific meaning, distinction, uncertainty, or transition rather than restating the whole answer.",
            "Prefer live conversational moves: clarify a term, test a distinction, ask a focused follow-up, invite a concrete example, or move on when the point is already clear.",
            "Ground broad claims before moving on. If an answer is mostly a general principle, opinion, or recommendation, ask one focused grounding follow-up when it would materially improve the output: an anonymized example, what the claim is based on, one exception, one observed signal, or how it works in practice. Do not ask for all of these at once.",
            "When you asked for a concrete example, specific factor, number, date, role, or mechanism and the answer stays abstract, politely ask again for the missing answer type instead of accepting the abstract answer as complete.",
            "If a word, phrase, or transcript fragment is unclear, malformed, or could change the meaning, clarify that specific term before building the next question on it.",
            "Do not get trapped in terminology clarification. If one clarification attempt does not resolve a label but the underlying meaning is clear enough, preserve the label as uncertain, state the meaning you will carry forward, and move on.",
            "When an answer repeats the same point or answers a neighboring question instead of the one you asked, name the mismatch once: what was answered, what remains unanswered, and the simplest way to answer it. If the interviewee repeats the same non-answer again, mark that point unresolved and pivot to another priority or a simpler forced-choice check.",
            "When the interviewee repeatedly says they need a simpler question, do not keep shortening the same wording into fragments. After one simplification, offer concrete choices or one example answer shape; if that still fails, mark the topic unresolved and move on.",
            "Short acknowledgements or one-phrase replies are not substantive answers to open interview questions. In any language, treat brief replies that only acknowledge, agree, disagree, defer, or choose between offered options as acknowledgements unless you explicitly asked a closed yes/no or either/or question.",
            "When a reply is only an acknowledgement, restate the question in simpler words and ask for the interviewee's view, reason, or one concrete example before moving to a narrower follow-up.",
            "Maintain a private coverage tracker from the prepared brief's priority topics. Do not close after only one explored theme if major priority topics remain untouched; use the remaining time to cover the highest-value gap naturally.",
            "Maintain a private unresolved-thread list. If the interviewee introduces an important term, distinction, system, process, or recurring reference and its meaning, mechanism, or consequence is still unclear, probe it before closing or mark it unresolved if time or the interviewee prevents clarification.",
            "If the interviewee cannot recall a concrete episode, help memory without leading the answer: offer a few context-backed categories from the prepared brief or conversation and ask them to choose one to discuss.",
            "If you propose a framing and the interviewee merely agrees, do not treat the agreement as evidence. Ask one follow-up that has them apply, revise, or challenge the framing in their own words or against a real case.",
            "Before closing, make sure the conversation contains enough concrete detail to satisfy the prepared purpose. Ask for a mechanism, artifact, episode, decision rule, or uncertainty only when it is relevant to this brief and the participant's answers; do not force every interview to contain each one.",
            "Do not run a fixed questionnaire. Cover the priority topics naturally and stop when the purpose is satisfied.",
            f"The interview has a hard {duration_minutes}-minute browser limit. "
            f"Manage time actively: by minute {synthesis_minute} move to synthesis "
            f"or final priority gaps and ask the closing question no later than "
            f"minute {closing_minute}.",
            "If the browser sends a private session-management message about sustained silence or the final time window, treat it as a timing fact. Recover naturally: reassure, simplify the current question, prioritize, or close. Do not scold the interviewee or expose the browser message.",
            "Respect the boundaries. If the interviewee moves into an out-of-scope or sensitive area, acknowledge briefly and redirect to the prepared scope.",
            "Do not approve conclusions. Do not say an answer is client-ready. Evidence will be reviewed later.",
            "Before closing, ask whether there is anything important you did not ask as its own turn, then stop and wait for the interviewee's answer. Only after that answer, thank the interviewee and tell them they can press End interview. Do not combine the final substantive question and the End interview handoff in the same response.",
            "Reasoning: use the interview context to decide whether you understand the answer well enough to represent it fairly, whether a short answer needs probing, and whether to clarify, follow up, move on, or close. Do not use fixed word-count or keyword assumptions for these semantic decisions.",
            f"Use this configured interview language for the whole interview: {language}. Keep using it even if a short, noisy, ambiguous, or accidental transcript fragment appears in another language.",
            "Do not switch language during a hosted interview. If the interviewee responds in another language, continue in the configured language and ask one concise clarification in that configured language.",
            f"Preambles: when you need a moment to reason before the next question, say one brief natural bridge in {language}, such as {thinking_bridge_examples}. Do not reveal hidden reasoning, say you are thinking deeply, use filler sounds, or include onomatopoeic expressions.",
            "Prepared interview brief:",
            brief
            or "(No prepared brief supplied; keep the interview factual and ask for context.)",
        ]
    )


def _build_realtime_session_config(
    record: Mapping[str, Any],
    *,
    language: str,
    model: str,
) -> dict[str, Any]:
    interview_mode = _clean_interview_mode(str(record.get("interview_mode", "")))
    return {
        "type": "realtime",
        "model": model or DEFAULT_MODEL,
        "reasoning": {"effort": "high"},
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "low",
                    "create_response": (
                        interview_mode != INTERVIEW_MODE_PLUGIN_IMPROVEMENT
                    ),
                    "interrupt_response": (
                        interview_mode != INTERVIEW_MODE_PLUGIN_IMPROVEMENT
                    ),
                },
                "transcription": {
                    "model": DEFAULT_TRANSCRIPTION_MODEL,
                    "language": language,
                },
            },
            "output": {
                "voice": "marin",
            },
        },
        "instructions": _interview_instructions(record, language),
        "tracing": "auto",
    }


def _transcript_tail_from_turns(turns: list[dict[str, str]], max_chars: int) -> str:
    lines = [
        f"{turn.get('speaker', '').strip()}: {turn.get('text', '').strip()}"
        for turn in turns[-MAX_SIDEBAND_TURNS:]
        if turn.get("text", "").strip()
    ]
    value = "\n".join(lines)
    return value[-max_chars:] if len(value) > max_chars else value


def _live_partner_prompt(
    record: Mapping[str, Any],
    *,
    language: str,
    turns: list[dict[str, str]],
    latest_speaker: str,
    latest_text: str,
    last_whisper: str,
) -> str:
    context = "\n".join(_brief_lines(record))
    transcript_tail = _transcript_tail_from_turns(turns, MAX_TRANSCRIPT_TAIL_CHARS)
    mode = _clean_interview_mode(str(record.get("interview_mode", "")))
    return "\n".join(
        [
            "You are the silent process checker for a live hosted interview.",
            "You do not speak to the interviewee and you are not a second interviewer. You may send one private corrective note to the interviewer, or an empty string.",
            "",
            "The intended method is a structured interview: build accurate understanding, then use grounding details only when they clarify or verify that understanding.",
            f"Interview mode: {mode}. The mode changes the objective, not the calm non-checklist posture.",
            "",
            "Whisper only when the process is drifting:",
            "- the interviewer is becoming too intense, forensic, or checklist-like;",
            "- the interviewer asks for too many cognitive tasks in one turn;",
            "- the interviewer asks prematurely for proof details such as owners, KPIs, metrics, examples, timings, or decision rules;",
            "- the interviewer mechanically repeats or summarizes answers instead of advancing the conversation;",
            "- the interviewer probes before understanding an ambiguous or important answer;",
            "- the interviewer accepts broad, abstract, or unclear answers without grounding or clarification when the output needs usable evidence;",
            "- the interviewer appears ready to close after only one explored theme while major priority topics from the brief remain untouched;",
            "- an important live thread, term, process, or repeated reference remains unresolved and the interviewer is moving on or closing;",
            "- the interviewee cannot recall an example and the interviewer does not offer context-backed artifact categories to help memory;",
            "- the interviewer proposes a framing, receives mere agreement, and fails to ask the interviewee to apply, revise, or challenge it;",
            "- the conversation lacks concrete detail needed for the prepared purpose;",
            "- the interviewer keeps relitigating an uncertain label after the meaning is already usable;",
            "- the interviewer keeps asking near-variants after the interviewee repeats the same non-answer;",
            "- the interviewer keeps shrinking the same question after the interviewee repeatedly asks for a simpler version;",
            "- the interviewer appears to interrupt, rush, or leave too little room for thought;",
            "- the interviewer uses a language different from the configured interview language, repeats itself, or drifts from the prepared scope;",
            "- time is running short and the interviewer has not begun closing or prioritizing.",
            "",
            "Return JSON only with this exact shape:",
            '{"whisper": "short private note or empty string"}',
            "",
            "Rules:",
            "- Default to an empty whisper. Intervene only for a clear process failure visible in the recent transcript.",
            "- Do not intervene for a single imperfect but acceptable turn. Intervene only when the issue is likely to harm the next interviewer move.",
            "- Under 35 words.",
            "- Imperative, specific, and grounded in the interview process failure.",
            "- Do not suggest new interview questions or topic probes.",
            "- Do not ask for missing evidence. Correct the interviewer's posture instead.",
            "- Do not introduce topics outside the prepared boundaries.",
            "- Do not repeat the previous whisper unless the same process failure is clearly continuing.",
            f"- Previous whisper: {last_whisper.strip() or '(none)'}",
            "",
            "Good whispers:",
            '- "Slow down; ask one simpler question."',
            '- "You are summarizing too much; move the conversation forward."',
            '- "Give more room before the next question."',
            '- "This is becoming too forensic; return to understanding."',
            '- "Ground the broad claim before moving on."',
            '- "Check priority coverage before closing."',
            '- "Resolve the live thread or mark it unresolved."',
            '- "Offer artifact categories to recover a concrete example."',
            '- "Do not accept agreement to your framing as evidence."',
            '- "Capture one missing depth dimension before closing."',
            '- "Mark the label uncertain and move on."',
            '- "Name the non-answer once, then pivot."',
            '- "Offer choices once; then mark unresolved."',
            "",
            f"Language: {language}",
            "",
            "Prepared interview brief:",
            context or "(none)",
            "",
            "Recent live transcript:",
            transcript_tail or "(none)",
            "",
            f"Latest {latest_speaker} turn:",
            latest_text,
        ]
    )


def _instructions_with_partner_note(
    record: Mapping[str, Any],
    *,
    language: str,
    whisper: str,
) -> str:
    return "\n\n".join(
        [
            _interview_instructions(record, language),
            "Live silent partner note (private):",
            whisper,
            "Use this note only if it improves the next natural interviewer move. Do not mention the silent partner or the note.",
        ]
    )


async def _hosted_partner_sideband_loop(
    *,
    token: str,
    record: Mapping[str, Any],
    call_id: str,
    api_key: str,
    language: str,
) -> None:
    import websockets

    turns: list[dict[str, str]] = []
    last_whisper = ""
    safety_identifier = _public_safety_identifier(str(record["token_hash"]))
    url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
    async with websockets.connect(
        url,
        additional_headers={
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Safety-Identifier": safety_identifier,
        },
    ) as websocket:
        _append_event(token, "partner_sideband_connected", {"call_id": call_id})
        async for raw_message in websocket:
            try:
                event = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, Mapping):
                continue
            event_type = str(event.get("type", ""))
            latest_speaker = ""
            latest_text = ""
            if event_type == "conversation.item.input_audio_transcription.completed":
                latest_text = _clean_text(
                    str(event.get("transcript", "")), max_chars=4_000
                )
                latest_speaker = "Interviewee"
            elif event_type == "response.output_audio_transcript.done":
                latest_text = _clean_text(
                    str(event.get("transcript", "")), max_chars=4_000
                )
                latest_speaker = "Interviewer"
            if not latest_text or not latest_speaker:
                continue
            turns.append({"speaker": latest_speaker, "text": latest_text})
            del turns[:-MAX_SIDEBAND_TURNS]
            prompt = _live_partner_prompt(
                record,
                language=language,
                turns=turns,
                latest_speaker=latest_speaker,
                latest_text=latest_text,
                last_whisper=last_whisper,
            )
            try:
                whisper = await asyncio.to_thread(
                    create_partner_whisper,
                    api_key=api_key,
                    prompt=prompt,
                    model=_default_partner_model(),
                    safety_identifier=safety_identifier,
                )
            except VoiceSessionError as exc:
                LOGGER.info("Hosted interview partner sideband skipped: %s", exc)
                continue
            if not whisper:
                if last_whisper:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "session.update",
                                "session": {
                                    "type": "realtime",
                                    "instructions": _interview_instructions(
                                        record, language
                                    ),
                                },
                            }
                        )
                    )
                    _append_event(
                        token,
                        "partner_whisper_cleared",
                        {
                            "call_id": call_id,
                            "latest_speaker": latest_speaker,
                        },
                    )
                    last_whisper = ""
                continue
            last_whisper = whisper[:MAX_PARTNER_WHISPER_CHARS]
            await websocket.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "instructions": _instructions_with_partner_note(
                                record,
                                language=language,
                                whisper=last_whisper,
                            ),
                        },
                    }
                )
            )
            _append_event(
                token,
                "partner_whisper",
                {
                    "call_id": call_id,
                    "latest_speaker": latest_speaker,
                    "whisper": last_whisper,
                },
            )


def _run_partner_sideband(
    *,
    token: str,
    record: Mapping[str, Any],
    call_id: str,
    api_key: str,
    language: str,
) -> None:
    try:
        asyncio.run(
            _hosted_partner_sideband_loop(
                token=token,
                record=record,
                call_id=call_id,
                api_key=api_key,
                language=language,
            )
        )
    except Exception as exc:  # noqa: BLE001 - sideband must not break interview
        LOGGER.info("Hosted interview partner sideband ended: %s", exc)
        try:
            _append_event(
                token,
                "partner_sideband_closed",
                {"call_id": call_id, "message": str(exc)[:500]},
            )
        except Exception:  # noqa: BLE001 - best-effort telemetry
            return


def _start_partner_sideband(
    *,
    token: str,
    record: Mapping[str, Any],
    call_id: str,
    api_key: str,
    language: str,
) -> None:
    if not call_id:
        _append_event(
            token, "partner_sideband_unavailable", {"reason": "missing_call_id"}
        )
        return
    thread = threading.Thread(
        target=_run_partner_sideband,
        kwargs={
            "token": token,
            "record": dict(record),
            "call_id": call_id,
            "api_key": api_key,
            "language": language,
        },
        name=f"hosted-interview-partner-{call_id}",
        daemon=True,
    )
    thread.start()


def _safe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    if len(encoded) > MAX_EVENT_PAYLOAD_CHARS:
        return {
            "truncated": True,
            "text": encoded[:MAX_EVENT_PAYLOAD_CHARS],
        }
    decoded = json.loads(encoded)
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _send_completion_notification(
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
) -> bool:
    recipient = str(record.get("notification_email") or _notification_email()).strip()
    if not recipient:
        LOGGER.info(
            "Hosted-interview completion notification skipped: %s is not configured.",
            NOTIFICATION_EMAIL_ENV,
        )
        return False
    completion_status = str(
        completion.get("completion_status", record.get("status", ""))
    )
    interview_title = record.get("interview_title", "Interview")
    subject = f"Hosted interview ended - {interview_title} ({completion_status})"
    lines = [
        "A hosted interview has ended.",
        "",
        f"Interview campaign: {record.get('interview_campaign_id', LEGACY_UNCLASSIFIED_CAMPAIGN_ID)}",
        f"Case: {record.get('case_name', '')}",
        f"Case id: {record.get('case_id', '')}",
        f"Interview: {record.get('interview_title', '')}",
        f"Role: {record.get('interviewee_role', '')}",
        f"Token hint: {record.get('token_hint', '')}",
        f"Status: {completion_status}",
        f"Status reason: {completion.get('completion_status_reason', '')}",
        f"Completed at: {completion.get('completed_at', '')}",
        f"Transcript words: {completion.get('transcript_words', 0)}",
        f"Audio chunks received: {completion.get('audio_chunks', 0)}",
        f"Video chunks received: {completion.get('video_chunks', 0)}",
        "",
        f"Output page: {_output_url_for_record(record)}",
        f"JSON bundle: {_bundle_url_for_record(record)}",
        f"Quality review: {_review_url_for_record(record)}",
        "",
        "The session is stored server-side and ready for export/import review.",
    ]
    return send_plain_text_email(recipient, subject, "\n".join(lines))


def _completion_for_session(session_dir: Path) -> dict[str, Any]:
    return (
        _read_json(_completion_path(session_dir))
        if _completion_path(session_dir).exists()
        else {}
    )


def _review_for_session(session_dir: Path) -> dict[str, Any]:
    return (
        _read_json(_review_path(session_dir))
        if _review_path(session_dir).exists()
        else {}
    )


def _review_error_for_session(session_dir: Path) -> dict[str, Any]:
    return (
        _read_json(_review_error_path(session_dir))
        if _review_error_path(session_dir).exists()
        else {}
    )


def _post_call_interviewee_transcription_enabled() -> bool:
    configured = os.getenv("HOSTED_INTERVIEW_POST_CALL_TRANSCRIPTION", "1")
    return configured.strip().lower() not in {"0", "false", "off", "no"}


def _event_count_for_session(session_dir: Path) -> int:
    if not _events_path(session_dir).exists():
        return 0
    return sum(
        1
        for line in _events_path(session_dir).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _audio_chunk_count_for_session(session_dir: Path) -> int:
    audio_dir = session_dir / "audio"
    if not audio_dir.exists():
        return 0
    return sum(1 for path in audio_dir.iterdir() if path.is_file())


def _audio_files_for_session(session_dir: Path) -> list[dict[str, Any]]:
    return _media_files_for_session(session_dir, "audio")


def _content_type_for_media_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".m4a", ".mp4", ".m4v"}:
        return "video/mp4" if path.parent.name == "video" else "audio/mp4"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".webm":
        return "video/webm" if path.parent.name == "video" else "audio/webm"
    return "application/octet-stream"


def _media_files_for_session(
    session_dir: Path, folder_name: str
) -> list[dict[str, Any]]:
    media_dir = session_dir / folder_name
    if not media_dir.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(media_dir.iterdir()):
        if not path.is_file():
            continue
        files.append(
            {
                "file_name": path.name,
                "relative_path": str(path.relative_to(session_dir)),
                "content_type": _content_type_for_media_path(path),
                "bytes": path.stat().st_size,
            }
        )
    return files


def _read_events_for_session(session_dir: Path) -> list[dict[str, Any]]:
    if not _events_path(session_dir).exists():
        return []
    events = []
    for line in _events_path(session_dir).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _events_for_current_run(
    events: list[dict[str, Any]], completion: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return only events from the run associated with the current completion.

    Run boundaries are mechanical browser events. Filtering by the latest
    `started` before the current completion prevents reset/reused links from
    mixing old transcripts into current output and review artifacts.
    """

    if not events:
        return []
    completed_at = str(completion.get("completed_at", "")).strip()
    start_index: int | None = None
    for index, event in enumerate(events):
        if str(event.get("event_type", "")) != "started":
            continue
        captured_at = str(event.get("captured_at", "")).strip()
        if completed_at and captured_at and captured_at > completed_at:
            continue
        start_index = index
    if start_index is None:
        return events
    current_events = events[start_index:]
    if not completed_at:
        return current_events
    return [
        event
        for event in current_events
        if str(event.get("event_type", "")) in POST_COMPLETION_EVENT_TYPES
        or not str(event.get("captured_at", "")).strip()
        or str(event.get("captured_at", "")).strip() <= completed_at
    ]


def _split_transcript_turns(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _normalized_dialog_fragment(value: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else " " for character in value
    )
    return " ".join(normalized.split())


def _is_non_substantive_interviewer_turn(text: str) -> bool:
    """Filter mechanically identifiable bridge or partial interviewer artifacts."""

    return (
        _normalized_dialog_fragment(text) in NON_SUBSTANTIVE_INTERVIEWER_TURN_NORMALIZED
    )


def _dialog_turns_from_completion(
    completion: Mapping[str, Any],
) -> list[dict[str, str]]:
    interviewer_turns = _split_transcript_turns(
        str(completion.get("assistant_transcript", ""))
    )
    interviewee_turns = _split_transcript_turns(
        str(completion.get("user_transcript", ""))
    )
    dialogue = []
    max_turns = max(len(interviewer_turns), len(interviewee_turns))
    for index in range(max_turns):
        if index < len(interviewer_turns):
            dialogue.append(
                {
                    "speaker": "Interviewer",
                    "text": interviewer_turns[index],
                    "captured_at": "",
                }
            )
        if index < len(interviewee_turns):
            dialogue.append(
                {
                    "speaker": "Interviewee",
                    "text": interviewee_turns[index],
                    "captured_at": "",
                }
            )
    return dialogue


def _dialog_turns_for_session(
    events: list[dict[str, Any]], completion: Mapping[str, Any]
) -> list[dict[str, str]]:
    dialogue = []
    for event in events:
        event_type = str(event.get("event_type", ""))
        if event_type not in {
            "interviewer_turn",
            "interviewee_turn",
            "interviewee_partial_turn_flushed",
        }:
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, Mapping):
            continue
        text = _clean_text(str(payload.get("text", "")), max_chars=20_000)
        if not text:
            continue
        if event_type == "interviewer_turn" and _is_non_substantive_interviewer_turn(
            text
        ):
            continue
        speaker = "Interviewer" if event_type == "interviewer_turn" else "Interviewee"
        if (
            event_type == "interviewee_turn"
            and dialogue
            and dialogue[-1].get("source_event") == "interviewee_partial_turn_flushed"
            and text.startswith(dialogue[-1]["text"])
        ):
            dialogue.pop()
        dialogue.append(
            {
                "speaker": speaker,
                "text": text,
                "captured_at": str(event.get("captured_at", "")),
                "source_event": event_type,
            }
        )
    return dialogue or _dialog_turns_from_completion(completion)


def _text_word_count(value: str) -> int:
    return len([part for part in str(value or "").split() if part.strip()])


def _interviewee_word_count(
    dialog_turns: list[dict[str, str]], completion: Mapping[str, Any]
) -> int:
    words_from_dialog = sum(
        _text_word_count(str(turn.get("text", "")))
        for turn in dialog_turns
        if str(turn.get("speaker", "")).strip().lower() == "interviewee"
    )
    return max(
        words_from_dialog,
        _text_word_count(str(completion.get("user_transcript", ""))),
    )


def _event_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload", {})
    return payload if isinstance(payload, Mapping) else {}


def _has_connection_or_transcription_failure(
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    *,
    interviewee_words: int,
) -> bool:
    telemetry = completion.get("telemetry", {})
    if not isinstance(telemetry, Mapping):
        telemetry = {}
    peer_state = str(telemetry.get("peer_connection_state", "")).lower()
    data_state = str(telemetry.get("data_channel_state", "")).lower()
    if peer_state in {"failed", "disconnected"}:
        return True
    if data_state in {"failed"}:
        return True
    for event in events:
        event_type = str(event.get("event_type", ""))
        payload = _event_payload(event)
        detail = str(payload.get("detail", "")).lower()
        state = str(payload.get("state", "")).lower()
        if event_type == "connection_issue" and any(
            marker in f"{detail} {state}"
            for marker in ("failed", "disconnected", "closed")
        ):
            return True
    if interviewee_words == 0 and int(completion.get("audio_chunks", 0) or 0) > 0:
        return True
    if interviewee_words == 0:
        event_types = {str(event.get("event_type", "")) for event in events}
        return (
            "speech_started" in event_types
            and "transcription_completed_empty" in event_types
        )
    return False


def _has_media_upload_failure(
    completion: Mapping[str, Any], events: list[dict[str, Any]]
) -> bool:
    telemetry = completion.get("telemetry", {})
    if not isinstance(telemetry, Mapping):
        telemetry = {}
    upload_errors = telemetry.get("upload_errors")
    if isinstance(upload_errors, list) and upload_errors:
        return True
    return any(
        str(event.get("event_type", ""))
        in {"audio_chunk_upload_error", "video_chunk_upload_error"}
        for event in events
    )


def _classify_completion_status(
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    dialog_turns: list[dict[str, str]],
) -> tuple[str, str]:
    """Use mechanical gates only for transport failures and obvious thinness."""

    if _has_media_upload_failure(completion, events):
        return INTERVIEW_STATUS_FAILED_TECHNICAL, "media_upload_failed"
    interviewee_words = _interviewee_word_count(dialog_turns, completion)
    has_failure = _has_connection_or_transcription_failure(
        completion,
        events,
        interviewee_words=interviewee_words,
    )
    is_plugin_improvement = (
        _clean_interview_mode(str(record.get("interview_mode", "")))
        == INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    )
    # This deliberately low mechanical gate rejects empty or one-word attempts.
    # It does not claim semantic usefulness; central triage owns that judgment.
    minimum_words = (
        MIN_PLUGIN_IMPROVEMENT_INTERVIEWEE_WORDS
        if is_plugin_improvement
        else MIN_COMPLETED_INTERVIEWEE_WORDS
    )
    if interviewee_words < minimum_words:
        if has_failure:
            return (
                INTERVIEW_STATUS_FAILED_TECHNICAL,
                "connection_or_transcription_failed_before_usable_interview",
            )
        return INTERVIEW_STATUS_INCOMPLETE, "too_little_interviewee_substance"
    if is_plugin_improvement and interviewee_words < MIN_COMPLETED_INTERVIEWEE_WORDS:
        return INTERVIEW_STATUS_COMPLETED, "completed_short_plugin_improvement"
    return INTERVIEW_STATUS_COMPLETED, "completed_with_minimum_substance"


def _initial_interviewee_audio_transcription_metadata(
    *,
    enabled: bool,
    audio_chunks: int,
) -> dict[str, Any]:
    status_value = "queued" if enabled and audio_chunks > 0 else "unavailable"
    reason = ""
    if not enabled:
        status_value = "disabled"
        reason = "post-call interviewee transcription disabled"
    elif audio_chunks <= 0:
        reason = "no interviewee microphone audio chunks were uploaded"
    return {
        "schema_version": 1,
        "status": status_value,
        "source": "recorded_interviewee_microphone",
        "model": POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL,
        "reason": reason,
    }


def _should_run_post_call_interviewee_transcription(
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
) -> bool:
    if not _post_call_interviewee_transcription_enabled():
        return False
    if int(completion.get("audio_chunks", 0) or 0) <= 0:
        return False
    metadata = completion.get("interviewee_audio_transcription", {})
    if not isinstance(metadata, Mapping):
        return True
    if str(metadata.get("status", "")).strip().lower() == "complete":
        return False
    return not _has_media_upload_failure(completion, events)


def _hosted_interview_transcription_context(record: Mapping[str, Any]) -> str:
    return "\n".join(_brief_lines(record))[:12_000]


def _assemble_interviewee_audio_chunks(
    *,
    session_dir: Path,
    audio_files: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, str]:
    if not audio_files:
        raise VoiceSessionError("No interviewee microphone audio chunks were uploaded.")
    first_name = str(audio_files[0].get("file_name", "interviewee-audio.webm"))
    suffix = Path(first_name).suffix.lower() or ".webm"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"interviewee-microphone{suffix}"
    with output_path.open("wb") as output_handle:
        for media_file in audio_files:
            relative_path = str(media_file.get("relative_path", "")).strip()
            if not relative_path:
                raise VoiceSessionError("Interviewee audio chunk metadata is invalid.")
            chunk_path = session_dir / relative_path
            if not chunk_path.exists() or not chunk_path.is_file():
                raise VoiceSessionError(
                    f"Interviewee audio chunk is missing: {relative_path}."
                )
            with chunk_path.open("rb") as chunk_handle:
                shutil.copyfileobj(chunk_handle, output_handle)
    if output_path.stat().st_size <= 0:
        raise VoiceSessionError("Assembled interviewee microphone audio is empty.")
    content_type = str(audio_files[0].get("content_type", "")).strip()
    if not content_type:
        content_type = _content_type_for_media_path(output_path)
    return output_path, content_type


def _transcribe_interviewee_audio_chunks(
    *,
    record: Mapping[str, Any],
    session_dir: Path,
) -> dict[str, Any]:
    audio_files = _audio_files_for_session(session_dir)
    with tempfile.TemporaryDirectory(prefix="hosted-interview-audio-") as temp_dir_name:
        audio_path, content_type = _assemble_interviewee_audio_chunks(
            session_dir=session_dir,
            audio_files=audio_files,
            output_dir=Path(temp_dir_name),
        )
        result = create_audio_transcription(
            api_key=_resolve_openai_api_key(),
            audio_path=audio_path,
            audio_size_bytes=audio_path.stat().st_size,
            filename=audio_path.name,
            content_type=content_type,
            language=_clean_language(str(record.get("language", "it"))),
            case_context=_hosted_interview_transcription_context(record),
            model=POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL,
            safety_identifier=_public_safety_identifier(str(record["token_hash"])),
        )
    return {
        "text": result.text,
        "metadata": dict(result.metadata),
        "audio_files": audio_files,
    }


def _write_completion_status(
    *,
    token: str,
    record: Mapping[str, Any],
    completion: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_dir = _session_dir(token)
    dialog_turns = _dialog_turns_for_session(events, completion)
    final_status, status_reason = _classify_completion_status(
        record,
        completion,
        events,
        dialog_turns,
    )
    prior_status = str(completion.get("completion_status", ""))
    prior_reason = str(completion.get("completion_status_reason", ""))
    completion["completion_status"] = final_status
    completion["completion_status_reason"] = status_reason
    _write_json(_completion_path(session_dir), completion)
    updated = dict(record)
    updated["status"] = final_status
    updated["ended_at"] = completion["completed_at"]
    updated["completion_status_reason"] = status_reason
    updated.pop("active_attempt_id", None)
    if final_status == INTERVIEW_STATUS_COMPLETED:
        updated["completed_at"] = completion["completed_at"]
    else:
        updated.pop("completed_at", None)
    _save_record_for_token(token, updated)
    if prior_status and (prior_status != final_status or prior_reason != status_reason):
        _append_event(
            token,
            "post_call_completion_reclassified",
            {
                "previous_status": prior_status,
                "previous_status_reason": prior_reason,
                "status": final_status,
                "status_reason": status_reason,
            },
        )
    return updated, completion


def _apply_post_call_interviewee_transcription(
    *,
    token: str,
    record: Mapping[str, Any],
    completion: dict[str, Any],
) -> dict[str, Any]:
    session_dir = _session_dir(token)
    live_transcript = str(
        completion.get("live_user_transcript") or completion.get("user_transcript", "")
    )
    completion["live_user_transcript"] = live_transcript
    metadata = dict(completion.get("interviewee_audio_transcription", {}))
    metadata.update(
        {
            "schema_version": 1,
            "status": "running",
            "source": "recorded_interviewee_microphone",
            "model": POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL,
            "started_at": _iso(_now()),
            "live_transcript_words": _text_word_count(live_transcript),
        }
    )
    completion["interviewee_audio_transcription"] = metadata
    _write_json(_completion_path(session_dir), completion)
    _append_event(
        token,
        "post_call_interviewee_transcription_started",
        {"model": POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL},
    )
    try:
        result = _transcribe_interviewee_audio_chunks(
            record=record,
            session_dir=session_dir,
        )
    except (AudioTranscriptionError, VoiceSessionError, OSError) as exc:
        metadata.update(
            {
                "status": "error",
                "completed_at": _iso(_now()),
                "message": str(exc)[:1_000],
                "audio_files": _audio_files_for_session(session_dir),
            }
        )
        completion["interviewee_audio_transcription"] = metadata
        completion["transcript_source"] = "realtime_live_asr"
        _write_json(_completion_path(session_dir), completion)
        _append_event(
            token,
            "post_call_interviewee_transcription_failed",
            {"message": str(exc)[:1_000]},
        )
        return completion
    final_text = _clean_text(str(result.get("text", "")), max_chars=200_000)
    if not final_text:
        metadata.update(
            {
                "status": "error",
                "completed_at": _iso(_now()),
                "message": "Post-call interviewee transcription returned no text.",
                "audio_files": result.get("audio_files", []),
            }
        )
        completion["interviewee_audio_transcription"] = metadata
        completion["transcript_source"] = "realtime_live_asr"
        _write_json(_completion_path(session_dir), completion)
        _append_event(
            token,
            "post_call_interviewee_transcription_failed",
            {"message": metadata["message"]},
        )
        return completion
    completion["user_transcript"] = final_text
    completion["transcript_words"] = _text_word_count(final_text)
    completion["transcript_source"] = "post_call_interviewee_audio"
    metadata.update(
        {
            "status": "complete",
            "completed_at": _iso(_now()),
            "final_transcript_words": completion["transcript_words"],
            "audio_files": result.get("audio_files", []),
            "transcription_metadata": result.get("metadata", {}),
        }
    )
    completion["interviewee_audio_transcription"] = metadata
    _write_json(_completion_path(session_dir), completion)
    _append_event(
        token,
        "post_call_interviewee_transcription_completed",
        {
            "model": POST_CALL_INTERVIEWEE_TRANSCRIPTION_MODEL,
            "final_transcript_words": completion["transcript_words"],
        },
    )
    return completion


def _review_transcript_payload(dialog_turns: list[dict[str, str]]) -> str:
    lines = []
    for turn in dialog_turns:
        speaker = str(turn.get("speaker", "")).strip() or "Unknown"
        text = _clean_text(str(turn.get("text", "")), max_chars=6_000)
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)[:80_000]


def _review_text_excerpt(value: Any, *, max_chars: int) -> str:
    return _clean_text(str(value or ""), max_chars=max_chars)


def _review_transcript_provenance(completion: Mapping[str, Any]) -> dict[str, Any]:
    post_call_metadata = completion.get("interviewee_audio_transcription", {})
    if not isinstance(post_call_metadata, Mapping):
        post_call_metadata = {}
    live_transcript = str(completion.get("live_user_transcript", ""))
    final_transcript = str(completion.get("user_transcript", ""))
    provenance: dict[str, Any] = {
        "source": completion.get("transcript_source", ""),
        "final_interviewee_transcript_words": _text_word_count(final_transcript),
        "live_interviewee_transcript_words": _text_word_count(live_transcript),
        "post_call_interviewee_transcription": {
            key: value
            for key, value in post_call_metadata.items()
            if key not in {"audio_files", "transcription_metadata"}
        },
        "post_call_transcription_metadata": post_call_metadata.get(
            "transcription_metadata", {}
        ),
        "post_call_audio_files": post_call_metadata.get("audio_files", []),
        "final_interviewee_transcript": _review_text_excerpt(
            final_transcript,
            max_chars=80_000,
        ),
    }
    if live_transcript and live_transcript != final_transcript:
        provenance["live_interviewee_transcript"] = _review_text_excerpt(
            live_transcript,
            max_chars=30_000,
        )
    return provenance


def _interview_review_prompt(
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    dialog_turns: list[dict[str, str]],
) -> str:
    event_summary: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type", "")).strip() or "unknown"
        event_summary[event_type] = event_summary.get(event_type, 0) + 1
    payload = {
        "record": {
            "interview_campaign_id": record.get(
                "interview_campaign_id", LEGACY_UNCLASSIFIED_CAMPAIGN_ID
            ),
            "case_id": record.get("case_id", ""),
            "case_name": record.get("case_name", ""),
            "client_project": record.get("client_project", ""),
            "interview_title": record.get("interview_title", ""),
            "interviewee_role": record.get("interviewee_role", ""),
            "interview_mode": record.get("interview_mode", ""),
            "language": record.get("language", ""),
            "purpose": record.get("purpose", ""),
            "background_context": record.get("background_context", ""),
            "hypotheses_to_test": record.get("hypotheses_to_test", []),
            "priority_topics": record.get("priority_topics", []),
            "questions": record.get("questions", []),
            "red_flags": record.get("red_flags", []),
            "boundaries": record.get("boundaries", []),
        },
        "completion": {
            "completed_at": completion.get("completed_at", ""),
            "elapsed_seconds": completion.get("elapsed_seconds"),
            "transcript_words": completion.get("transcript_words", 0),
            "client_transcript_words": completion.get("client_transcript_words", 0),
            "audio_chunks": completion.get("audio_chunks", 0),
            "video_chunks": completion.get("video_chunks", 0),
            "screen_capture_metadata": completion.get("screen_capture_metadata", {}),
            "telemetry": completion.get("telemetry", {}),
        },
        "transcript_provenance": _review_transcript_provenance(completion),
        "event_summary": event_summary,
        "dialog_transcript": _review_transcript_payload(dialog_turns),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _generate_interview_quality_review(
    *,
    api_key: str,
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    dialog_turns: list[dict[str, str]],
    model: str | None = None,
    endpoint: str = "https://api.openai.com/v1/responses",
    timeout_seconds: float = DEFAULT_INTERVIEW_REVIEW_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Generate an evidence-first diagnostic review of a completed interview."""

    system_prompt = "\n".join(
        [
            "You are an interview quality auditor for Clara hosted interviews.",
            "Your job is to diagnose the interview process and resulting transcript, not to repair the transcript.",
            "Separate observed evidence from inference. Every key finding must cite a short transcript or event evidence snippet.",
            "Assess whether the interview asked useful follow-ups, detected evasive answers, separated facts from opinions, grounded claims, preserved uncertainty, avoided language drift, and produced material usable by a consultant, analyst, researcher, or operator.",
            "Suggest pipeline improvements only when supported by the supplied evidence. Also identify what should not be changed.",
            "Do not invent facts, names, dates, metrics, quotes, or contradictions that are not present in the transcript.",
        ]
    )
    body = json.dumps(
        {
            "model": model or _default_review_model(),
            "reasoning": {"effort": "medium"},
            "store": False,
            "input": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": _interview_review_prompt(
                        record, completion, events, dialog_turns
                    ),
                },
            ],
            "text": {"format": INTERVIEW_REVIEW_RESPONSE_FORMAT},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": _public_safety_identifier(
                str(record["token_hash"])
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceSessionError(
            f"Interview quality review failed: HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise VoiceSessionError(f"Interview quality review failed: {exc}") from exc
    review = _json_object_from_text(_response_output_text(response_payload))
    if not review:
        raise VoiceSessionError("Interview quality review returned no JSON object.")
    review["schema_version"] = 1
    review["generated_at"] = _iso(_now())
    review["model"] = model or _default_review_model()
    return review


def _write_interview_quality_review(
    *,
    token: str,
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    dialog_turns: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_dir = _session_dir(token)
    try:
        review = _generate_interview_quality_review(
            api_key=_resolve_openai_api_key(),
            record=record,
            completion=completion,
            events=events,
            dialog_turns=dialog_turns,
        )
    except VoiceSessionError as exc:
        if "timed out" in str(exc).lower():
            try:
                review = _generate_interview_quality_review(
                    api_key=_resolve_openai_api_key(),
                    record=record,
                    completion=completion,
                    events=events,
                    dialog_turns=dialog_turns,
                    timeout_seconds=DEFAULT_INTERVIEW_REVIEW_RETRY_TIMEOUT_SECONDS,
                )
            except VoiceSessionError as retry_exc:
                error_payload = {
                    "schema_version": 1,
                    "generated_at": _iso(_now()),
                    "error": str(retry_exc),
                    "retry_after_timeout": True,
                }
                _write_json(_review_error_path(session_dir), error_payload)
                LOGGER.info(
                    "Hosted interview quality review skipped after retry: %s",
                    retry_exc,
                )
                return {}, error_payload
        else:
            error_payload = {
                "schema_version": 1,
                "generated_at": _iso(_now()),
                "error": str(exc),
            }
            _write_json(_review_error_path(session_dir), error_payload)
            LOGGER.info("Hosted interview quality review skipped: %s", exc)
            return {}, error_payload
    review.setdefault("schema_version", 1)
    review.setdefault("generated_at", _iso(_now()))
    review.setdefault("model", _default_review_model())
    _write_json(_review_path(session_dir), review)
    error_path = _review_error_path(session_dir)
    if error_path.exists():
        error_path.unlink()
    return review, {}


def _run_interview_quality_review_task(token: str) -> None:
    try:
        record = _load_record_for_token(token)
    except HostedInterviewError as exc:
        LOGGER.info("Hosted interview quality review task skipped: %s", exc)
        return
    if (
        _clean_interview_mode(str(record.get("interview_mode", "")))
        == INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    ):
        LOGGER.info("Hosted interview quality review skipped for plugin improvement")
        return
    session_dir = _session_dir(token)
    completion = _completion_for_session(session_dir)
    if not completion:
        LOGGER.info("Hosted interview quality review task skipped: no completion")
        return
    events = _read_events_for_session(session_dir)
    events = _events_for_current_run(events, completion)
    dialog_turns = _dialog_turns_for_session(events, completion)
    review, _review_error = _write_interview_quality_review(
        token=token,
        record=record,
        completion=completion,
        events=events,
        dialog_turns=dialog_turns,
    )
    if review.get("overall_quality") != "failed":
        _send_completion_notification(record, completion)
        return
    updated = dict(record)
    updated["status"] = INTERVIEW_STATUS_UNUSABLE
    updated["completion_status_reason"] = "quality_review_failed"
    updated["ended_at"] = completion.get("completed_at", _iso(_now()))
    updated.pop("completed_at", None)
    completion["completion_status"] = INTERVIEW_STATUS_UNUSABLE
    completion["completion_status_reason"] = "quality_review_failed"
    _write_json(_completion_path(session_dir), completion)
    _save_record_for_token(token, updated)
    _send_completion_notification(updated, completion)
    _append_event(
        token,
        INTERVIEW_STATUS_UNUSABLE,
        {
            "status": INTERVIEW_STATUS_UNUSABLE,
            "status_reason": "quality_review_failed",
            "review_generated_at": review.get("generated_at", ""),
        },
    )


def _attach_change_request_completion(
    record: Mapping[str, Any], completion: Mapping[str, Any]
) -> None:
    """Attach a finalized transcript only through its server-created URL binding."""

    change_request_id = str(record.get("change_request_id", "") or "").strip()
    interview_url = str(record.get("public_url", "") or "").strip()
    if not change_request_id:
        return
    from modules.change_requests.store import (
        ChangeRequestConflictError,
        ChangeRequestNotFoundError,
        ChangeRequestStoreUnavailableError,
        get_change_request_store,
    )

    try:
        get_change_request_store().attach_interview_completion(
            change_request_id,
            {
                "schema_version": 1,
                "completed_at": completion["completed_at"],
                "language": record.get("language", ""),
                "user_transcript": completion["user_transcript"],
                "assistant_transcript": completion["assistant_transcript"],
                "elapsed_seconds": completion["elapsed_seconds"],
                "transcript_source": completion.get("transcript_source", ""),
            },
            interview_url=interview_url,
        )
    except (
        ChangeRequestConflictError,
        ChangeRequestNotFoundError,
        ChangeRequestStoreUnavailableError,
    ) as exc:
        LOGGER.error(
            "Unable to attach hosted interview completion to %s: %s",
            change_request_id,
            exc,
        )


@contextmanager
def _try_post_completion_task_lock(session_dir: Path) -> Iterator[bool]:
    """Admit only one post-completion task for a session across workers."""

    lock_path = session_dir / ".post-completion.lock"
    with lock_path.open("a+b") as lock_file:
        if sys.platform == "win32":
            msvcrt = importlib.import_module("msvcrt")
            lock_file.seek(0)
            if not lock_file.read(1):
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
            try:
                yield True
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl = importlib.import_module("fcntl")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _run_interview_post_completion_task(token: str) -> None:
    try:
        record = _load_record_for_token(token)
    except HostedInterviewError as exc:
        LOGGER.info("Hosted interview post-completion task skipped: %s", exc)
        return
    session_dir = _session_dir(token)
    with _try_post_completion_task_lock(session_dir) as acquired:
        if not acquired:
            LOGGER.info(
                "Hosted interview post-completion task skipped: already running"
            )
            return
        _run_interview_post_completion_task_locked(token, session_dir, record)


def _run_interview_post_completion_task_locked(
    token: str, session_dir: Path, record: Mapping[str, Any]
) -> None:
    completion = _completion_for_session(session_dir)
    if not completion:
        LOGGER.info("Hosted interview post-completion task skipped: no completion")
        return
    events = _read_events_for_session(session_dir)
    events = _events_for_current_run(events, completion)
    if _should_run_post_call_interviewee_transcription(completion, events):
        completion = _apply_post_call_interviewee_transcription(
            token=token,
            record=record,
            completion=dict(completion),
        )
        events = _read_events_for_session(session_dir)
        events = _events_for_current_run(events, completion)
        record, completion = _write_completion_status(
            token=token,
            record=record,
            completion=dict(completion),
            events=events,
        )
    if str(completion.get("completion_status", "")) == INTERVIEW_STATUS_COMPLETED:
        _attach_change_request_completion(record, completion)
        if (
            _clean_interview_mode(str(record.get("interview_mode", "")))
            == INTERVIEW_MODE_PLUGIN_IMPROVEMENT
        ):
            _send_completion_notification(record, completion)
        else:
            _run_interview_quality_review_task(token)
        return
    _send_completion_notification(record, completion)


@admin_router.get("/campaigns", response_model=list[InterviewCampaignResponse])
def interview_campaigns(
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> list[InterviewCampaignResponse]:
    """List the exact, versioned campaign briefs available to preparers."""

    del user
    return [
        InterviewCampaignResponse(
            interview_campaign_id=campaign.interview_campaign_id,
            name=campaign.name,
            description=campaign.description,
            interview_title=campaign.interview_title,
            interview_mode=campaign.interview_mode,
        )
        for campaign in list_interview_campaigns()
    ]


@admin_router.post(
    "/campaigns/{interview_campaign_id}/interviews",
    response_model=PreparedInterviewResponse,
)
def prepare_campaign_interview(
    interview_campaign_id: str,
    payload: PreparedCampaignInterviewRequest,
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> PreparedInterviewResponse:
    """Create one link from an exact registered campaign brief."""

    try:
        prepared_payload = PreparedInterviewRequest.model_validate(
            build_campaign_interview_payload(
                interview_campaign_id,
                case_id=payload.case_id,
                language=payload.language,
                participant_name=payload.participant_name,
                interviewee_role=payload.interviewee_role,
                expires_in_hours=payload.expires_in_hours,
            )
        )
    except UnknownInterviewCampaignError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    public_url_base = str(
        request.url_for("hosted_interview_page", token=PUBLIC_URL_TOKEN_PLACEHOLDER)
    )
    token, record = create_prepared_interview(
        prepared_payload,
        created_by="" if user is None else user.email,
        public_url_base=public_url_base.removesuffix("/TOKEN"),
    )
    return PreparedInterviewResponse(
        interview_campaign_id=str(record["interview_campaign_id"]),
        token=token,
        public_url=str(record["public_url"]),
        expires_at=str(record["expires_at"]),
        notification_email=str(record["notification_email"]),
    )


@admin_router.post("", response_model=PreparedInterviewResponse)
def prepare_interview(
    payload: PreparedInterviewRequest,
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> PreparedInterviewResponse:
    """Create a public no-login hosted interview link."""

    public_url_base = str(
        request.url_for("hosted_interview_page", token=PUBLIC_URL_TOKEN_PLACEHOLDER)
    )
    token, record = create_prepared_interview(
        payload,
        created_by="" if user is None else user.email,
        public_url_base=public_url_base.removesuffix("/TOKEN"),
    )
    return PreparedInterviewResponse(
        interview_campaign_id=str(record["interview_campaign_id"]),
        token=token,
        public_url=str(record["public_url"]),
        expires_at=str(record["expires_at"]),
        notification_email=str(record["notification_email"]),
    )


@admin_router.get("/{token}/bundle")
def export_interview_bundle(
    token: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Return the server-side bundle for local Clara import/review."""

    del user
    try:
        record = _load_record_for_token(token)
        session_dir = _session_dir(token)
        events = _read_events_for_session(session_dir)
        completion = (
            _read_json(_completion_path(session_dir))
            if _completion_path(session_dir).exists()
            else {}
        )
        events = _events_for_current_run(events, completion)
        review = _review_for_session(session_dir)
        review_error = _review_error_for_session(session_dir)
        video_files = _media_files_for_session(session_dir, "video")
        screen_capture_metadata = completion.get("screen_capture_metadata", {})
        if not isinstance(screen_capture_metadata, Mapping):
            screen_capture_metadata = {}
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    first_video_file = video_files[0] if video_files else {}
    return JSONResponse(
        {
            "record": record,
            "events": events,
            "completion": completion,
            "review": review,
            "review_error": review_error,
            "video_file_name": first_video_file.get("file_name", ""),
            "video_content_type": first_video_file.get("content_type", ""),
            "video_chunks": completion.get("video_chunks", len(video_files)),
            "video_files": video_files,
            "screen_capture_metadata": screen_capture_metadata,
        }
    )


@admin_router.get("/{token}/review")
def export_interview_review(
    token: str,
    user: AuthenticatedUser | None = Depends(require_site_permission_for_request),
) -> JSONResponse:
    """Return the generated post-interview quality review artifact."""

    del user
    try:
        session_dir = _session_dir(token)
        _load_record_for_token(token)
        review = _review_for_session(session_dir)
        review_error = _review_error_for_session(session_dir)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if not review and not review_error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview quality review is not available.",
        )
    return JSONResponse({"review": review, "review_error": review_error})


@site_router.get("/interview/{token}/output", name="hosted_interview_output_page")
def hosted_interview_output_page(
    token: str,
    request: Request,
    user: AuthenticatedUser | None = Depends(require_site_permission("clara")),
):
    """Render a private readable output page for a completed hosted interview."""

    del user
    try:
        record = _load_record_for_token(token)
        session_dir = _session_dir(token)
        completion = _completion_for_session(session_dir)
        review = _review_for_session(session_dir)
        review_error = _review_error_for_session(session_dir)
        events = _read_events_for_session(session_dir)
        events = _events_for_current_run(events, completion)
        dialog_turns = _dialog_turns_for_session(events, completion)
        event_count = len(events)
        audio_chunk_count = _audio_chunk_count_for_session(session_dir)
        error_message = ""
    except HostedInterviewError as exc:
        record = {}
        completion = {}
        review = {}
        review_error = {}
        dialog_turns = []
        event_count = 0
        audio_chunk_count = 0
        error_message = str(exc)
    response = templates.TemplateResponse(
        request,
        "hosted_interview_output.html",
        {
            "request": request,
            "token": token,
            "record": record,
            "completion": completion,
            "review": review,
            "review_error": review_error,
            "dialog_turns": dialog_turns,
            "event_count": event_count,
            "audio_chunk_count": audio_chunk_count,
            "bundle_url": f"/case-notes/api/voice/interviews/{token}/bundle",
            "review_url": f"/case-notes/api/voice/interviews/{token}/review",
            "error_message": error_message,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@site_router.get("/interview/{token}", name="hosted_interview_page")
def hosted_interview_page(token: str, request: Request):
    """Render the no-login interview page."""

    try:
        record = _load_record_for_token(token)
        language = record.get("language", "it")
        is_italian = str(language).lower().startswith("it")
        session_ready = record.get("status") != INTERVIEW_STATUS_COMPLETED
        if not session_ready:
            status_message = (
                "Intervista completata" if is_italian else "Interview completed"
            )
            status_detail = (
                "Grazie. Le risposte sono state salvate."
                if is_italian
                else "Thank you. The responses have been saved."
            )
        elif record.get("status") in RETRYABLE_INTERVIEW_STATUSES:
            status_message = "Puoi riprovare" if is_italian else "You can try again"
            status_detail = (
                "Il browser chiederà di nuovo l'accesso al microfono."
                if is_italian
                else "The browser will request microphone access again."
            )
        else:
            status_message = "Prima di iniziare" if is_italian else "Before you begin"
            status_detail = (
                "Il browser ti chiederà di autorizzare il microfono. Le tue "
                "risposte vocali verranno registrate e trascritte; le domande "
                "cambieranno in base alle tue risposte."
                if is_italian
                else "The browser will ask for microphone access. Your spoken "
                "responses will be recorded and transcribed; the questions will "
                "change based on your answers."
            )
    except HostedInterviewError as exc:
        record = {}
        language = "it"
        session_ready = False
        status_message = {
            "Invalid interview token.": "Questo link non è valido o è scaduto.",
            "Invalid or expired interview link.": "Questo link non è valido o è scaduto.",
            "This interview link has been revoked.": "Questo link è stato revocato.",
            "This interview has already been completed.": "Questa intervista è già stata completata.",
            "This interview link is not active.": "Questo link non è attivo.",
            "This interview link has expired.": "Questo link è scaduto.",
        }.get(str(exc), "Non è possibile aprire questa intervista.")
        status_detail = "Chiedi a chi ti ha invitato di inviarti un nuovo link."
    participant_intro = record.get("participant_intro", "")
    if not participant_intro and language == "it":
        try:
            campaign = get_interview_campaign(record.get("interview_campaign_id", ""))
            participant_intro = campaign.participant_intro
        except UnknownInterviewCampaignError:
            participant_intro = ""
    if not participant_intro:
        participant_intro = record.get("purpose", "")
    response = templates.TemplateResponse(
        request,
        "hosted_interview.html",
        {
            "request": request,
            "token": token,
            "session_ready": session_ready,
            "status_message": status_message,
            "status_detail": status_detail,
            "interview_title": record.get("interview_title", "Interview"),
            "page_label": record.get("participant_name") or record.get("case_name", ""),
            "participant_intro": participant_intro,
            "interview_mode": record.get("interview_mode", INTERVIEW_MODE_CASE),
            "language": language,
            "default_model": DEFAULT_MODEL,
            "max_duration_seconds": int(
                record.get("max_duration_seconds", DEFAULT_INTERVIEW_DURATION_SECONDS)
            ),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@public_router.get("/{token}/status")
def public_interview_status(token: str) -> JSONResponse:
    """Return a minimal status for the public page."""

    try:
        record = _load_record_for_token(token)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return JSONResponse(
        {
            "status": record.get("status", ""),
            "interview_title": record.get("interview_title", ""),
            "case_name": record.get("case_name", ""),
        }
    )


@public_router.post("/{token}/session")
def public_interview_session(
    token: str, payload: InterviewSessionRequest
) -> JSONResponse:
    """Create a server-side Realtime session for the public interview page."""

    try:
        record = _load_record_for_token(token, allow_completed=False)
        record_status = str(record.get("status", ""))
        should_archive_attempt = record_status in RETRYABLE_INTERVIEW_STATUSES
        if record_status == INTERVIEW_STATUS_STARTED:
            if not _started_attempt_is_stale(record):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This interview already has an active started attempt.",
                )
            should_archive_attempt = True
        if record_status not in {
            INTERVIEW_STATUS_READY,
            INTERVIEW_STATUS_STARTED,
            *RETRYABLE_INTERVIEW_STATUSES,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This interview link cannot start a new attempt.",
            )
        language = _clean_language(
            payload.language or str(record.get("language", "it"))
        )
        session_config = _build_realtime_session_config(
            record,
            language=language,
            model=DEFAULT_MODEL,
        )
        api_key = _resolve_openai_api_key()
        realtime_call = create_realtime_call_with_metadata(
            api_key=api_key,
            sdp=payload.sdp,
            session_config=session_config,
            safety_identifier=_public_safety_identifier(str(record["token_hash"])),
        )
        attempt_id = _new_attempt_id()
        if record_status == INTERVIEW_STATUS_READY or should_archive_attempt:
            if should_archive_attempt:
                _archive_retryable_attempt_files(_session_dir(token))
            updated = dict(record)
            updated["status"] = INTERVIEW_STATUS_STARTED
            updated["started_at"] = _iso(_now())
            updated["active_attempt_id"] = attempt_id
            updated.pop("completed_at", None)
            updated.pop("ended_at", None)
            updated.pop("completion_status_reason", None)
            _save_record_for_token(token, updated)
            record = updated
        if (
            _clean_interview_mode(str(record.get("interview_mode", "")))
            != INTERVIEW_MODE_PLUGIN_IMPROVEMENT
        ):
            _start_partner_sideband(
                token=token,
                record=record,
                call_id=realtime_call.call_id,
                api_key=api_key,
                language=language,
            )
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except OpenAIRealtimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return JSONResponse({"sdp": realtime_call.sdp, "attempt_id": attempt_id})


@public_router.post("/{token}/event")
def public_interview_event(token: str, payload: InterviewEventRequest) -> JSONResponse:
    """Autosave a public interview transcript/status event."""

    try:
        _active_attempt_record(token, payload.attempt_id)
        _append_event(token, payload.event_type, _safe_payload(payload.payload))
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return JSONResponse({"ok": True})


@public_router.post("/{token}/audio-chunk")
async def public_interview_audio_chunk(
    token: str,
    attempt_id: str = Form(min_length=1, max_length=120),
    chunk_index: int = Form(ge=0),
    file: UploadFile = File(...),
) -> JSONResponse:
    """Autosave one audio chunk from the public interview page."""

    try:
        _active_attempt_record(token, attempt_id)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    content = await file.read()
    if len(content) > MAX_AUDIO_CHUNK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio chunk is too large.",
        )
    session_dir = _session_dir(token)
    audio_dir = session_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename or "chunk.webm").suffix.lower()
    if extension not in {".webm", ".m4a", ".mp4", ".ogg", ".wav"}:
        extension = ".webm"
    chunk_name = f"chunk-{chunk_index:06d}{extension}"
    chunk_path = audio_dir / chunk_name
    if chunk_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio chunk already exists for this attempt.",
        )
    chunk_path.write_bytes(content)
    _append_event(
        token,
        "audio_chunk",
        {
            "chunk_index": chunk_index,
            "filename": chunk_name,
            "content_type": file.content_type or "",
            "bytes": len(content),
        },
    )
    return JSONResponse({"ok": True, "filename": chunk_name})


@public_router.post("/{token}/video-chunk")
async def public_interview_video_chunk(
    token: str,
    attempt_id: str = Form(min_length=1, max_length=120),
    chunk_index: int = Form(ge=0),
    file: UploadFile = File(...),
) -> JSONResponse:
    """Autosave one optional screen video chunk for the public interview."""

    try:
        _active_attempt_record(token, attempt_id)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    content = await file.read()
    if len(content) > MAX_VIDEO_CHUNK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Video chunk is too large.",
        )
    session_dir = _session_dir(token)
    video_dir = session_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename or "chunk.webm").suffix.lower()
    if extension not in {".webm", ".mp4", ".m4v", ".mov"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported video chunk file type.",
        )
    chunk_name = f"chunk-{chunk_index:06d}{extension}"
    chunk_path = video_dir / chunk_name
    if chunk_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Video chunk already exists for this attempt.",
        )
    chunk_path.write_bytes(content)
    _append_event(
        token,
        "video_chunk",
        {
            "chunk_index": chunk_index,
            "filename": chunk_name,
            "content_type": file.content_type or "",
            "bytes": len(content),
        },
    )
    return JSONResponse({"ok": True, "filename": chunk_name})


@public_router.post("/{token}/complete")
def public_interview_complete(
    token: str, payload: CompleteInterviewRequest, background_tasks: BackgroundTasks
) -> JSONResponse:
    """End a public interview and classify whether it produced usable output."""

    try:
        _load_record_for_token(token)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    session_dir = _session_dir(token)
    with _try_post_completion_task_lock(session_dir) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Interview completion is already being processed.",
            )
        return _public_interview_complete_locked(
            token,
            payload,
            background_tasks,
            session_dir=session_dir,
        )


def _public_interview_complete_locked(
    token: str,
    payload: CompleteInterviewRequest,
    background_tasks: BackgroundTasks,
    *,
    session_dir: Path,
) -> JSONResponse:
    """Persist one completion while holding its cross-worker session lock."""

    try:
        record = _active_attempt_record(token, payload.attempt_id)
    except HostedInterviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    post_call_transcription_enabled = _post_call_interviewee_transcription_enabled()
    completion = {
        "schema_version": 1,
        "attempt_id": payload.attempt_id,
        "completed_at": _iso(_now()),
        "live_user_transcript": payload.user_transcript,
        "user_transcript": payload.user_transcript,
        "assistant_transcript": payload.assistant_transcript,
        "transcript_source": "realtime_live_asr",
        "elapsed_seconds": payload.elapsed_seconds,
        "transcript_words": _text_word_count(payload.user_transcript),
        "client_transcript_words": payload.transcript_words,
        "audio_chunks": payload.audio_chunks,
        "video_chunks": payload.video_chunks,
        "screen_capture_metadata": _safe_payload(payload.screen_capture_metadata),
        "telemetry": _safe_payload(payload.telemetry),
        "interviewee_audio_transcription": (
            _initial_interviewee_audio_transcription_metadata(
                enabled=post_call_transcription_enabled,
                audio_chunks=payload.audio_chunks,
            )
        ),
    }
    events = _read_events_for_session(session_dir)
    events = _events_for_current_run(events, completion)
    updated, completion = _write_completion_status(
        token=token,
        record=record,
        completion=completion,
        events=events,
    )
    final_status = str(completion.get("completion_status", ""))
    status_reason = str(completion.get("completion_status_reason", ""))
    is_plugin_improvement = (
        _clean_interview_mode(str(updated.get("interview_mode", "")))
        == INTERVIEW_MODE_PLUGIN_IMPROVEMENT
    )
    should_run_post_call_task = _should_run_post_call_interviewee_transcription(
        completion,
        events,
    )
    if not should_run_post_call_task and final_status == INTERVIEW_STATUS_COMPLETED:
        _attach_change_request_completion(updated, completion)
    review_status = "skipped"
    if should_run_post_call_task:
        review_status = "queued_after_post_call_transcription"
    elif final_status == INTERVIEW_STATUS_COMPLETED and is_plugin_improvement:
        review_status = "skipped_for_plugin_improvement"
    elif final_status == INTERVIEW_STATUS_COMPLETED:
        review_status = "queued"
    _append_event(
        token,
        (
            INTERVIEW_STATUS_COMPLETED
            if final_status == INTERVIEW_STATUS_COMPLETED
            else final_status
        ),
        {
            "completed_at": completion["completed_at"],
            "status": final_status,
            "status_reason": status_reason,
            "transcript_words": completion["transcript_words"],
            "client_transcript_words": payload.transcript_words,
            "audio_chunks": payload.audio_chunks,
            "video_chunks": payload.video_chunks,
            "transcript_source": completion["transcript_source"],
            "interviewee_audio_transcription_status": completion[
                "interviewee_audio_transcription"
            ]["status"],
        },
    )
    if should_run_post_call_task:
        background_tasks.add_task(_run_interview_post_completion_task, token)
        notification_sent = False
        notification_status = "queued_after_post_call_transcription"
    elif final_status == INTERVIEW_STATUS_COMPLETED and is_plugin_improvement:
        notification_sent = _send_completion_notification(updated, completion)
        notification_status = "sent" if notification_sent else "failed"
    elif final_status == INTERVIEW_STATUS_COMPLETED:
        background_tasks.add_task(_run_interview_quality_review_task, token)
        notification_sent = False
        notification_status = "queued_after_review"
    else:
        notification_sent = _send_completion_notification(updated, completion)
        notification_status = "sent" if notification_sent else "failed"
    response_status = "processing" if should_run_post_call_task else final_status
    return JSONResponse(
        {
            "ok": True,
            "status": response_status,
            "provisional_status": final_status,
            "completion_status_reason": status_reason,
            "notification_sent": notification_sent,
            "notification_status": notification_status,
            "output_url": _output_url_for_record(updated),
            "bundle_url": _bundle_url_for_record(updated),
            "review_url": _review_url_for_record(updated),
            "review_status": review_status,
            "review_error": "",
        }
    )
