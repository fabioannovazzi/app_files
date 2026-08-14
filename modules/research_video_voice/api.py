"""Authenticated, non-persistent narration generation for Research Video."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import wave
import zipfile
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.video_voice_policy import (
    OPENAI_VIDEO_TTS_MODEL,
    video_voice_for_language,
)

__all__ = [
    "HostedNarrationRequest",
    "router",
    "site_router",
]

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/case-notes/api/research-video", tags=["research-video"])
site_router = APIRouter(tags=["research-video-site"])
templates = Jinja2Templates(directory="templates")

OPENAI_SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
HOSTED_VOICE_SOURCE = "mparanza_hosted_openai_voice"
MAX_SCENES = 20
MAX_NARRATION_CHARACTERS = 2_500
MAX_TOTAL_NARRATION_CHARACTERS = 20_000
MAX_AUDIO_BYTES = 25 * 1024 * 1024
SPEECH_TIMEOUT_SECONDS = 240
SPEECH_MAX_ATTEMPTS = 4
TRANSIENT_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504}
SCENE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

NARRATION_INSTRUCTIONS = {
    "de": (
        "Sprich in natürlichem, zeitgemäßem Deutsch wie eine erfahrene Fachperson, "
        "die sorgfältig geprüfte Informationen ruhig und klar erläutert. Keine "
        "Werbe-, Radio- oder Dramastimme. Sprich Zahlen und Einschränkungen deutlich aus."
    ),
    "en": (
        "Speak in natural contemporary English like an experienced professional "
        "explaining carefully reviewed information calmly and clearly. Do not sound "
        "promotional, dramatic, or like a radio advertisement. State figures and "
        "qualifications deliberately."
    ),
    "es": (
        "Habla en un español actual y natural, como una profesional con experiencia "
        "que explica información revisada con calma y claridad. Evita un tono "
        "publicitario, dramático o radiofónico. Pronuncia con cuidado las cifras y "
        "las salvedades."
    ),
    "fr": (
        "Parle dans un français contemporain et naturel, comme une professionnelle "
        "expérimentée qui explique calmement des informations vérifiées. Évite tout "
        "ton publicitaire, dramatique ou radiophonique. Prononce distinctement les "
        "chiffres et les réserves."
    ),
    "it": (
        "Parla in italiano contemporaneo e naturale, come una professionista esperta "
        "che spiega con calma e chiarezza informazioni attentamente verificate. Evita "
        "un tono pubblicitario, drammatico o radiofonico. Pronuncia con cura cifre e "
        "qualificazioni."
    ),
}


class ApprovalProof(BaseModel):
    """Mechanical evidence that the local workflow bound user approval."""

    model_config = ConfigDict(extra="forbid")

    approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_by_user: Literal[True]


class NarrationScene(BaseModel):
    """One approved narration scene sent without its image or source material."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    narration: str = Field(min_length=1, max_length=MAX_NARRATION_CHARACTERS)

    @model_validator(mode="after")
    def validate_scene(self) -> "NarrationScene":
        if not SCENE_ID_PATTERN.fullmatch(self.id):
            raise ValueError("scene id must use lowercase letters, digits, and hyphens")
        if not self.narration.strip():
            raise ValueError("narration must not be blank")
        return self


class HostedNarrationRequest(BaseModel):
    """Bounded request accepted by the authenticated hosted voice endpoint."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    workflow: Literal["clara:research-video"]
    language: Literal["de", "en", "es", "fr", "it"]
    scene_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval: ApprovalProof
    scenes: list[NarrationScene] = Field(min_length=2, max_length=MAX_SCENES)

    @model_validator(mode="after")
    def validate_request(self) -> "HostedNarrationRequest":
        # Exact uniqueness and size bounds are deterministic because they protect
        # media packaging, provider limits, and auditable scene alignment.
        scene_ids = [scene.id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("scene ids must be unique")
        total_characters = sum(len(scene.narration) for scene in self.scenes)
        if total_characters > MAX_TOTAL_NARRATION_CHARACTERS:
            raise ValueError(
                "total narration exceeds "
                f"{MAX_TOTAL_NARRATION_CHARACTERS} characters"
            )
        return self


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _openai_api_key() -> str:
    """Return the server-held provider key without exposing it in errors or logs."""

    for key_name in ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY", "openAiKey"):
        value = os.environ.get(key_name, "").strip()
        if len(value) >= 20:
            return value
    raise RuntimeError("Hosted narration provider credentials are unavailable.")


def _normalize_wav(audio: bytes) -> tuple[bytes, dict[str, int | float]]:
    """Return finite PCM WAV bytes and mechanically verified media metadata."""

    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise RuntimeError("Hosted narration returned an invalid audio size.")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            frame_rate = source.getframerate()
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            compression_type = source.getcomptype()
            pcm_parts: list[bytes] = []
            while chunk := source.readframes(65_536):
                pcm_parts.append(chunk)
    except (OSError, EOFError, wave.Error) as exc:
        raise RuntimeError("Hosted narration returned invalid WAV audio.") from exc
    if frame_rate <= 0 or channels not in {1, 2} or compression_type != "NONE":
        raise RuntimeError("Hosted narration returned unusable WAV audio.")
    if sample_width not in {1, 2, 3, 4}:
        raise RuntimeError("Hosted narration returned an unsupported WAV sample width.")
    pcm = b"".join(pcm_parts)
    bytes_per_frame = channels * sample_width
    if not pcm or len(pcm) % bytes_per_frame:
        raise RuntimeError("Hosted narration returned unusable WAV audio.")
    frame_count = len(pcm) // bytes_per_frame
    duration = frame_count / frame_rate
    if not 0 < duration <= 600:
        raise RuntimeError("Hosted narration returned an unsupported duration.")
    normalized = io.BytesIO()
    with wave.open(normalized, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(sample_width)
        target.setframerate(frame_rate)
        target.writeframes(pcm)
    normalized_audio = normalized.getvalue()
    if len(normalized_audio) > MAX_AUDIO_BYTES:
        raise RuntimeError("Hosted narration returned an invalid audio size.")
    return normalized_audio, {
        "frame_count": frame_count,
        "frame_rate": frame_rate,
        "channels": channels,
        "sample_width_bytes": sample_width,
        "duration_seconds": round(duration, 6),
    }


def _request_openai_speech(
    *,
    api_key: str,
    language: str,
    narration: str,
) -> bytes:
    """Generate one scene with the centrally approved OpenAI video voice."""

    body = json.dumps(
        {
            "model": OPENAI_VIDEO_TTS_MODEL,
            "voice": video_voice_for_language(language),
            "input": narration,
            "instructions": NARRATION_INSTRUCTIONS[language],
            "response_format": "wav",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_SPEECH_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(1, SPEECH_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(  # nosec B310
                request,
                timeout=SPEECH_TIMEOUT_SECONDS,
            ) as response:
                audio = response.read(MAX_AUDIO_BYTES + 1)
            return audio
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP_STATUS:
                raise RuntimeError(
                    f"Hosted narration provider rejected the request with HTTP {exc.code}."
                ) from exc
            if attempt == SPEECH_MAX_ATTEMPTS:
                raise RuntimeError(
                    "Hosted narration provider remained unavailable after retries."
                ) from exc
        except (OSError, urllib.error.URLError) as exc:
            if attempt == SPEECH_MAX_ATTEMPTS:
                raise RuntimeError(
                    "Hosted narration provider remained unavailable after retries."
                ) from exc
        time.sleep(float(2 ** (attempt - 1)))
    raise RuntimeError("Hosted narration provider remained unavailable after retries.")


def _build_bundle(payload: HostedNarrationRequest) -> bytes:
    """Build one in-memory ZIP; no narration or audio is written server-side."""

    api_key = _openai_api_key()
    request_payload = payload.model_dump(mode="json")
    request_sha256 = _canonical_json_sha256(request_payload)
    voice = video_voice_for_language(payload.language)
    scene_records: list[dict[str, object]] = []
    generated_audio: list[tuple[str, bytes]] = []
    for index, scene in enumerate(payload.scenes, start=1):
        raw_audio = _request_openai_speech(
            api_key=api_key,
            language=payload.language,
            narration=scene.narration,
        )
        audio, media = _normalize_wav(raw_audio)
        filename = f"audio/{index:02d}-{scene.id}.wav"
        scene_records.append(
            {
                "id": scene.id,
                "audio": filename,
                "sha256": hashlib.sha256(audio).hexdigest(),
                "size_bytes": len(audio),
                **media,
            }
        )
        generated_audio.append((filename, audio))

    manifest = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "source": HOSTED_VOICE_SOURCE,
        "provider": "OpenAI",
        "model": OPENAI_VIDEO_TTS_MODEL,
        "voice": voice,
        "language": payload.language,
        "generated_at": datetime.now(UTC).isoformat(),
        "request_sha256": request_sha256,
        "scene_plan_sha256": payload.scene_plan_sha256,
        "approval_sha256": payload.approval.approval_sha256,
        "mparanza_application_retention": "in_memory_response_only",
        "scenes": scene_records,
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        for filename, audio in generated_audio:
            archive.writestr(filename, audio)
    return output.getvalue()


@site_router.get(
    "/case-notes/research-video/voice",
    response_class=HTMLResponse,
)
def hosted_narration_page(request: Request) -> HTMLResponse:
    """Render the authenticated narration-request upload surface."""

    return templates.TemplateResponse(
        request,
        "research_video_voice.html",
        {"request": request},
    )


@router.post("/voice")
def generate_hosted_narration(
    payload: HostedNarrationRequest,
    request: Request,
) -> Response:
    """Return an authenticated, non-persistent narration bundle."""

    if request.headers.get("x-mparanza-action") != "research-video-voice-v1":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Research Video action header.",
        )
    try:
        bundle = _build_bundle(payload)
    except RuntimeError as exc:
        LOGGER.warning("Hosted Research Video narration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=bundle,
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Disposition": (
                f'attachment; filename="research-video-voice-{timestamp}.zip"'
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
