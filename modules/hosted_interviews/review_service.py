"""HTTP-independent hosted interview quality review operations."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from modules.hosted_interviews.campaigns import LEGACY_UNCLASSIFIED_CAMPAIGN_ID
from modules.utilities import config as utilities_config

__all__ = [
    "generate_interview_quality_review",
    "create_partner_whisper",
    "VoiceSessionError",
    "ReviewProviderError",
]

DEFAULT_INTERVIEW_REVIEW_TIMEOUT_SECONDS = 120


MAX_PREPARED_TEXT_CHARS = 12_000


SUPPORTED_LANGUAGES = {"it", "en", "fr", "de", "es"}


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


class VoiceSessionError(RuntimeError):
    """Raised when hosted-interview external model work fails."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _clean_text(value: str, *, max_chars: int = MAX_PREPARED_TEXT_CHARS) -> str:
    return " ".join((value or "").replace("\x00", " ").split())[:max_chars]


def _clean_language(value: str) -> str:
    language = (value or "it").strip().lower()
    return language if language in SUPPORTED_LANGUAGES else "it"


def _default_review_model() -> str:
    model = os.getenv("HOSTED_INTERVIEW_REVIEW_MODEL", "").strip()
    if model:
        return model
    naming_params = utilities_config.get_naming_params()
    return naming_params["gpt55Thinking"]


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


def _text_word_count(value: str) -> int:
    return len([part for part in str(value or "").split() if part.strip()])


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


def _interview_review_system_prompt(record: Mapping[str, Any]) -> str:
    """Return review instructions aligned with the interview language."""

    lines = [
        "You are an interview quality auditor for Clara hosted interviews.",
        "Your job is to diagnose the interview process and resulting transcript, not to repair the transcript.",
        "Separate observed evidence from inference. Every key finding must cite a short transcript or event evidence snippet.",
        "Assess whether the interview asked useful follow-ups, detected evasive answers, separated facts from opinions, grounded claims, preserved uncertainty, avoided language drift, and produced material usable by a consultant, analyst, researcher, or operator.",
        "Suggest pipeline improvements only when supported by the supplied evidence. Also identify what should not be changed.",
        "Do not invent facts, names, dates, metrics, quotes, or contradictions that are not present in the transcript.",
    ]
    if _clean_language(str(record.get("language", "it"))) == "es":
        lines.append(
            "Write every human-readable narrative field in Spanish. Preserve short "
            "evidence quotes in their source language, and keep schema keys and "
            "enumerated values exactly as defined."
        )
    return "\n".join(lines)


class ReviewProviderError(VoiceSessionError):
    """Classified operational error without provider response or transcript text."""

    def __init__(
        self,
        category: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        stage: str = "interview_quality_review",
    ) -> None:
        self.stage = stage
        self.category = category
        self.retryable = retryable
        self.status_code = status_code
        label = (
            "Partner whisper"
            if stage == "partner_whisper"
            else "Interview quality review"
        )
        super().__init__(
            f"{label} failed: {category}; HTTP={status_code}; retryable={retryable}"
        )


def _request_review_payload(
    request: urllib.request.Request, timeout_seconds: float
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
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
        raise ReviewProviderError(
            category, retryable=code in {408, 429} or code >= 500, status_code=code
        ) from None
    except TimeoutError:
        raise ReviewProviderError("timeout", retryable=True) from None
    except urllib.error.URLError:
        raise ReviewProviderError("network", retryable=True) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ReviewProviderError("invalid_response", retryable=False) from None
    if not isinstance(payload, dict):
        raise ReviewProviderError("invalid_response", retryable=False)
    return payload


def generate_interview_quality_review(
    *,
    api_key: str,
    record: Mapping[str, Any],
    completion: Mapping[str, Any],
    events: list[dict[str, Any]],
    dialog_turns: list[dict[str, str]],
    model: str | None = None,
    endpoint: str = "https://api.openai.com/v1/responses",
    timeout_seconds: float = DEFAULT_INTERVIEW_REVIEW_TIMEOUT_SECONDS,
    provider: (
        Callable[[urllib.request.Request, float], Mapping[str, Any]] | None
    ) = None,
) -> dict[str, Any]:
    """Generate an evidence-first diagnostic review of a completed interview."""

    system_prompt = _interview_review_system_prompt(record)
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
    response_payload = (provider or _request_review_payload)(request, timeout_seconds)
    review = _json_object_from_text(_response_output_text(response_payload))
    if not review:
        raise VoiceSessionError("Interview quality review returned no JSON object.")
    review["schema_version"] = 1
    review["generated_at"] = _iso(_now())
    review["model"] = model or _default_review_model()
    return review


MAX_PARTNER_WHISPER_CHARS = 240


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
    provider: (
        Callable[[urllib.request.Request, float], Mapping[str, Any]] | None
    ) = None,
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
        response_payload = (provider or _request_review_payload)(
            request, timeout_seconds
        )
    except ReviewProviderError as exc:
        raise ReviewProviderError(
            exc.category,
            retryable=exc.retryable,
            status_code=exc.status_code,
            stage="partner_whisper",
        ) from None
    payload = _json_object_from_text(_response_output_text(response_payload))
    whisper = payload.get("whisper")
    return _clean_partner_whisper(whisper if isinstance(whisper, str) else "")
