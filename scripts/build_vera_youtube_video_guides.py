from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil

# Fixed local media tools are invoked with argument lists and without a shell.
import subprocess  # nosec B404
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from playwright.sync_api import Browser, Page, sync_playwright

if __package__:
    from .video_voice_policy import (
        OPENAI_VIDEO_TTS_MODEL,
        video_voice_for_language,
    )
else:
    from video_voice_policy import (
        OPENAI_VIDEO_TTS_MODEL,
        video_voice_for_language,
    )

__all__ = ["build_vera_youtube_video_guides", "main", "partition_narration_scenes"]

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = REPO_ROOT / "static" / "shared" / "video-production"
SPEC_PATH = PRODUCTION_ROOT / "vera-missing-guides.json"
FRAME_TEMPLATE_PATH = PRODUCTION_ROOT / "guide-frame.html"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "youtube-video-guides" / "rendered"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"
DEFAULT_SECRET_FILE = REPO_ROOT / ".secrets" / "secrets.local.toml"
OPENAI_SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
TTS_MAX_ATTEMPTS = 4
TTS_RETRY_BASE_SECONDS = 1.0
TTS_RETRY_MAX_SECONDS = 8.0
NARRATION_INSTRUCTIONS = {
    "it": (
        "Parla in italiano madrelingua contemporaneo, come una professionista "
        "esperta che spiega a un collega un metodo di lavoro concreto. Tono caldo, "
        "intelligente, calmo e conversazionale; mai pubblicitario, mai enfatico e "
        "mai da speaker radio. Questa è una parte di una guida continua: mantieni "
        "ritmo e timbro coerenti e chiudi la frase con naturalezza."
    ),
    "en": (
        "Speak in natural contemporary English, like an experienced professional "
        "explaining a practical working method to a colleague. Warm, intelligent, "
        "calm, and conversational; never salesy, emphatic, or like a radio voice-over. "
        "This is one part of a continuous guide: keep the pace and tone consistent "
        "and end the sentence naturally."
    ),
    "fr": (
        "Parlez dans un français naturel et contemporain, comme une professionnelle "
        "expérimentée qui explique à un collègue une méthode de travail concrète. "
        "Ton chaleureux, intelligent, calme et conversationnel, jamais publicitaire "
        "ni emphatique. Ceci est une partie d’un guide continu : gardez un rythme "
        "et un timbre cohérents et terminez la phrase naturellement."
    ),
    "de": (
        "Sprechen Sie natürliches, modernes Hochdeutsch, wie eine erfahrene "
        "Fachkraft, die einem Kollegen eine praktische Arbeitsweise erklärt. Warm, "
        "klug, ruhig und im Gesprächston; nie werblich, übertrieben oder wie ein "
        "Radiosprecher. Dies ist ein Teil einer fortlaufenden Anleitung: Tempo und "
        "Stimmklang sollen einheitlich bleiben, der Satz soll natürlich enden."
    ),
    "es": (
        "Habla en un español natural y contemporáneo, como una profesional con "
        "experiencia que explica a un colega un método de trabajo concreto. Tono "
        "cálido, inteligente, tranquilo y conversacional; nunca publicitario, "
        "enfático ni de locución radiofónica. Esta es una parte de una guía continua: "
        "mantén un ritmo y un timbre coherentes y termina la frase con naturalidad."
    ),
}
LANGUAGE_LABELS = {
    "it": "Italiano",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_RATE = 30
LEAD_SECONDS = 0.8
TAIL_SECONDS = 0.8
TARGET_LOUDNESS_LUFS = -16
CAPTION_MAX_CHARACTERS = 84
CAPTION_MIN_SECONDS = 1.0
CAPTION_MAX_CHARACTERS_PER_SECOND = 20.0
MIN_INTER_SCENE_PAUSE_SECONDS = 0.8
MAX_INTER_SCENE_PAUSE_SECONDS = 4.0
NATURAL_INTER_SCENE_PAUSE_SECONDS = 0.9
TRANSITION_SILENCE_MARGIN_SECONDS = 0.2
TRANSITION_MAX_VOLUME_DB = -45.0
EXPECTED_LOCALIZATIONS = {
    ("data-handling", "core", "it"),
    ("data-handling", "core", "en"),
    ("data-handling", "core", "fr"),
    ("data-handling", "core", "de"),
    ("data-handling", "core", "es"),
    ("new-client", "core", "it"),
    ("new-client", "core", "en"),
    ("new-client", "core", "fr"),
    ("new-client", "core", "de"),
    ("new-client", "core", "es"),
    ("new-client", "italy", "it"),
    ("new-client", "italy", "en"),
    ("new-client", "italy", "fr"),
    ("new-client", "italy", "de"),
    ("new-client", "italy", "es"),
    ("journal-sampling", "core", "it"),
    ("journal-sampling", "core", "en"),
    ("journal-sampling", "core", "fr"),
    ("journal-sampling", "core", "de"),
    ("journal-sampling", "core", "es"),
    ("check-entries", "core", "it"),
    ("check-entries", "core", "en"),
    ("check-entries", "core", "fr"),
    ("check-entries", "core", "de"),
    ("check-entries", "core", "es"),
    ("check-entries", "italy-fatturapa", "en"),
    ("check-entries", "italy-fatturapa", "fr"),
    ("check-entries", "italy-fatturapa", "de"),
    ("check-entries", "italy-fatturapa", "es"),
}
CORE_CHECK_ENTRY_FRAME_REPLACEMENTS = {
    "FatturaPA · TD01": "DOC-184",
    "Alfa S.r.l.": "Northwind",
    "€ 42.500": "42,500",
    "FT 184/26": "DOC-184",
}
CORE_FRAME_FORBIDDEN_PATTERN = re.compile(
    r"fatturapa|d\.\s*lgs|231/2007|antiriciclaggio|codice fiscale|partita iva|"
    r"\bpiva\b|\bcf\b|\baml\b|\bri\b|\brs\b|\b(?:italy|italia|italie|italien)\b",
    re.IGNORECASE,
)


def _required_tool(name: str, *fallbacks: str) -> str:
    """Return an executable path or raise a precise build error."""

    resolved = shutil.which(name)
    if resolved:
        return resolved
    for fallback in fallbacks:
        candidate = Path(fallback)
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"Required executable not found: {name}")


def _run(
    command: Sequence[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one production command with consistent logging and failure behavior."""

    LOGGER.debug("Running %s", " ".join(command))
    # The executable and every argument are controlled by this local renderer.
    return subprocess.run(  # nosec B603
        list(command),
        check=True,
        capture_output=capture_output,
        text=True,
    )


def _probe_duration(ffprobe: str, media_path: Path) -> float:
    """Read a finite media duration from ffprobe."""

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
    )
    duration = float(result.stdout.strip())
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid media duration for {media_path}: {duration}")
    return duration


def _probe_media(ffprobe: str, media_path: Path) -> dict[str, Any]:
    """Return the stream metadata used by the output validator."""

    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "avg_frame_rate,sample_rate,channels:format=duration"
            ),
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
    )
    return json.loads(result.stdout)


def _sha256(path: Path) -> str:
    """Return a stable SHA-256 digest for one generated artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_path(path: Path) -> str:
    """Return a stable repo-relative source path when one is available."""

    return (
        path.relative_to(REPO_ROOT).as_posix()
        if path.is_relative_to(REPO_ROOT)
        else path.as_posix()
    )


def _artifact_record(path: Path, mime_type: str) -> dict[str, Any]:
    """Describe a rendered artifact relative to the output manifest."""

    return {
        "path": path.relative_to(OUTPUT_ROOT).as_posix(),
        "mimeType": mime_type,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _contains_transcript_schema(value: object) -> bool:
    """Return whether a manifest value contains a transcript-named field."""

    if isinstance(value, dict):
        return any(
            "transcript" in str(key).casefold()
            or _contains_transcript_schema(nested_value)
            for key, nested_value in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_transcript_schema(item) for item in value)
    return False


def _validate_youtube_ready_manifest_entry(
    entry: dict[str, Any],
    *,
    expected_identity: tuple[str, str, str],
) -> None:
    """Require one final manifest entry to satisfy the YouTube voice policy."""

    identity = (
        entry.get("module"),
        entry.get("edition"),
        entry.get("language"),
    )
    if identity != expected_identity:
        raise ValueError(
            "YouTube-ready manifest identity mismatch: "
            f"{identity!r} != {expected_identity!r}"
        )
    language = expected_identity[2]
    expected_voice = video_voice_for_language(language)
    if entry.get("status") != "youtube_ready":
        raise ValueError(f"YouTube-ready manifest status is invalid for {identity!r}")
    voice = entry.get("voice")
    if (
        not isinstance(voice, dict)
        or voice.get("name") != expected_voice
        or voice.get("model") != OPENAI_VIDEO_TTS_MODEL
    ):
        raise ValueError(f"YouTube-ready manifest voice is invalid for {identity!r}")
    if _contains_transcript_schema(entry):
        raise ValueError(
            f"YouTube-ready manifest contains transcript schema for {identity!r}"
        )

    files = entry.get("files")
    expected_files = {
        "video": ("video/mp4", ".mp4"),
        "poster": ("image/jpeg", ".jpg"),
        "captions": ("text/vtt", ".vtt"),
    }
    if not isinstance(files, dict) or set(files) != set(expected_files):
        raise ValueError(f"YouTube-ready manifest files are invalid for {identity!r}")
    expected_artifact_fields = {"path", "mimeType", "bytes", "sha256"}
    for file_key, (mime_type, suffix) in expected_files.items():
        artifact = files[file_key]
        if not isinstance(artifact, dict) or set(artifact) != expected_artifact_fields:
            raise ValueError(
                f"YouTube-ready {file_key} schema is invalid for {identity!r}"
            )
        relative_path = artifact["path"]
        byte_count = artifact["bytes"]
        expected_sha256 = artifact["sha256"]
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or Path(relative_path).suffix.casefold() != suffix
            or artifact["mimeType"] != mime_type
            or type(byte_count) is not int
            or byte_count <= 0
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ValueError(
                f"YouTube-ready {file_key} metadata is invalid for {identity!r}"
            )
        artifact_path = OUTPUT_ROOT / relative_path
        if (
            not artifact_path.is_file()
            or artifact_path.stat().st_size != byte_count
            or _sha256(artifact_path) != expected_sha256
        ):
            raise ValueError(
                f"YouTube-ready {file_key} artifact is invalid for {identity!r}"
            )


def _build_input_sha256(
    *,
    concept: dict[str, Any],
    language: str,
    localization: dict[str, Any],
    frame_template: str,
) -> str:
    """Fingerprint every input that can materially change one rendered guide."""

    payload = {
        "schemaVersion": "3.2.0",
        "concept": concept,
        "language": language,
        "localization": localization,
        "frameTemplateSha256": hashlib.sha256(
            frame_template.encode("utf-8")
        ).hexdigest(),
        "ttsModel": OPENAI_VIDEO_TTS_MODEL,
        "voice": video_voice_for_language(language),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _checkpoint_path(module: str, edition: str, language: str) -> Path:
    """Return the ignored per-asset checkpoint used for safe resumability."""

    return OUTPUT_ROOT / module / edition / language / "asset.json"


def _load_valid_checkpoint(
    *,
    concept: dict[str, Any],
    language: str,
    build_input_sha256: str,
) -> dict[str, Any] | None:
    """Return a complete matching checkpoint, otherwise force a clean rebuild."""

    checkpoint_path = _checkpoint_path(
        str(concept["module"]),
        str(concept["edition"]),
        language,
    )
    if not checkpoint_path.is_file():
        return None
    try:
        entry = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    identity = (
        entry.get("module"),
        entry.get("edition"),
        entry.get("language"),
    )
    expected_identity = (concept["module"], concept["edition"], language)
    if (
        identity != expected_identity
        or entry.get("status") != "youtube_ready"
        or entry.get("buildInputSha256") != build_input_sha256
        or entry.get("voice", {}).get("name") != video_voice_for_language(language)
        or entry.get("voice", {}).get("model") != OPENAI_VIDEO_TTS_MODEL
    ):
        return None
    files = entry.get("files")
    if not isinstance(files, dict) or set(files) != {
        "video",
        "poster",
        "captions",
    }:
        return None
    for artifact in files.values():
        if not isinstance(artifact, dict):
            return None
        relative_path = artifact.get("path")
        expected_sha256 = artifact.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
            return None
        path = OUTPUT_ROOT / relative_path
        if not path.is_file() or _sha256(path) != expected_sha256:
            return None
    return entry


def _write_checkpoint(entry: dict[str, Any]) -> None:
    """Persist one fully validated entry so interrupted renders can resume."""

    checkpoint_path = _checkpoint_path(
        str(entry["module"]),
        str(entry["edition"]),
        str(entry["language"]),
    )
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sentences(text: str) -> list[str]:
    """Split narration into ordered sentences without losing punctuation."""

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip())]
    return [part for part in parts if part]


def partition_narration_scenes(text: str, group_count: int) -> list[str]:
    """Mechanically keep scene breaks at explicit sentence punctuation."""

    sentences = _sentences(text)
    if len(sentences) < group_count:
        raise ValueError(
            "Narration must contain at least one complete sentence per scene: "
            f"found {len(sentences)} sentences for {group_count} scenes"
        )
    if any(not re.search(r"[.!?]$", sentence) for sentence in sentences):
        raise ValueError("Every narration sentence must end with terminal punctuation")

    groups = []
    cursor = 0
    for group_index in range(group_count):
        groups_left = group_count - group_index
        sentences_left = len(sentences) - cursor
        if groups_left == 1:
            groups.append(" ".join(sentences[cursor:]))
            break

        target_words = (
            sum(len(sentence.split()) for sentence in sentences[cursor:]) / groups_left
        )
        take = 1
        current_words = len(sentences[cursor].split())
        while take < sentences_left - (groups_left - 1):
            next_words = len(sentences[cursor + take].split())
            if abs(current_words + next_words - target_words) >= abs(
                current_words - target_words
            ):
                break
            current_words += next_words
            take += 1
        groups.append(" ".join(sentences[cursor : cursor + take]))
        cursor += take

    if len(groups) != group_count or any(not group for group in groups):
        raise ValueError("Narration could not be partitioned into six scenes")
    return groups


def _scene_durations(
    scene_speech_durations: Sequence[float],
    target_seconds: float,
    inter_scene_pause_seconds: float,
) -> list[float]:
    """Place each visual transition at the midpoint of measured audio silence."""

    if not scene_speech_durations or any(
        duration <= 0 for duration in scene_speech_durations
    ):
        raise ValueError("Every scene must have a positive measured speech duration")
    pause_count = len(scene_speech_durations) - 1
    expected_seconds = (
        LEAD_SECONDS
        + sum(scene_speech_durations)
        + inter_scene_pause_seconds * pause_count
        + TAIL_SECONDS
    )
    if abs(expected_seconds - target_seconds) > 0.05:
        raise ValueError(
            "Measured speech and inter-scene pauses do not match the target: "
            f"{expected_seconds:.3f}s vs {target_seconds:.3f}s"
        )

    half_pause = inter_scene_pause_seconds / 2
    durations: list[float] = []
    for index, speech_duration in enumerate(scene_speech_durations):
        duration = speech_duration
        duration += LEAD_SECONDS if index == 0 else half_pause
        duration += (
            TAIL_SECONDS if index == len(scene_speech_durations) - 1 else half_pause
        )
        durations.append(duration)
    correction = target_seconds - sum(durations)
    durations[-1] += correction
    return durations


def _vtt_timestamp(seconds: float) -> str:
    """Format seconds as a WebVTT timestamp."""

    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _split_caption_cues(
    text: str,
    max_characters: int = CAPTION_MAX_CHARACTERS,
) -> list[str]:
    """Split narration at natural boundaries into mobile-readable cues."""

    if max_characters < 1:
        raise ValueError("Caption length must be positive")

    clauses = [
        clause.strip()
        for clause in re.split(r"(?<=[.!?;:,])\s+", text.strip())
        if clause.strip()
    ]
    cues: list[str] = []
    current = ""

    def append_words(words: Sequence[str]) -> None:
        nonlocal current
        for word in words:
            if len(word) > max_characters:
                if current:
                    cues.append(current)
                    current = ""
                cues.extend(
                    word[index : index + max_characters]
                    for index in range(0, len(word), max_characters)
                )
                continue
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_characters:
                cues.append(current)
                current = word
            else:
                current = candidate

    for clause in clauses:
        candidate = f"{current} {clause}".strip()
        if len(candidate) <= max_characters:
            current = candidate
            continue
        if current:
            cues.append(current)
            current = ""
        if len(clause) <= max_characters:
            current = clause
        else:
            append_words(clause.split())

    if current:
        cues.append(current)
    if not cues or any(len(cue) > max_characters for cue in cues):
        raise ValueError("Narration could not be split into readable caption cues")
    return cues


def _balanced_caption_pair(
    first: str,
    second: str,
    min_characters: int,
) -> tuple[str, str]:
    """Redistribute two adjacent cues without exceeding the cue limit."""

    words = f"{first} {second}".split()
    candidates: list[tuple[int, str, str]] = []
    for split_index in range(1, len(words)):
        left = " ".join(words[:split_index])
        right = " ".join(words[split_index:])
        if (
            min_characters <= len(left) <= CAPTION_MAX_CHARACTERS
            and min_characters <= len(right) <= CAPTION_MAX_CHARACTERS
        ):
            candidates.append((abs(len(left) - len(right)), left, right))
    if not candidates:
        raise ValueError("Short caption cue could not be rebalanced safely")
    _, left, right = min(candidates, key=lambda candidate: candidate[0])
    return left, right


def _rebalance_short_caption_cues(
    cues: Sequence[str],
    min_characters: int,
) -> list[str]:
    """Merge or rebalance short cues so each receives readable screen time."""

    balanced = list(cues)
    while len(balanced) > 1:
        short_index = next(
            (index for index, cue in enumerate(balanced) if len(cue) < min_characters),
            None,
        )
        if short_index is None:
            break

        merge_options: list[tuple[int, int, int, str]] = []
        if short_index > 0:
            merged = f"{balanced[short_index - 1]} {balanced[short_index]}"
            if len(merged) <= CAPTION_MAX_CHARACTERS:
                merge_options.append(
                    (len(merged), short_index - 1, short_index + 1, merged)
                )
        if short_index + 1 < len(balanced):
            merged = f"{balanced[short_index]} {balanced[short_index + 1]}"
            if len(merged) <= CAPTION_MAX_CHARACTERS:
                merge_options.append(
                    (len(merged), short_index, short_index + 2, merged)
                )
        if merge_options:
            _, start, end, merged = min(merge_options, key=lambda option: option[0])
            balanced[start:end] = [merged]
            continue

        pair_start = short_index - 1 if short_index > 0 else short_index
        left, right = _balanced_caption_pair(
            balanced[pair_start],
            balanced[pair_start + 1],
            min_characters,
        )
        balanced[pair_start : pair_start + 2] = [left, right]

    if any(len(cue) > CAPTION_MAX_CHARACTERS for cue in balanced):
        raise ValueError("Rebalanced caption exceeds the character limit")
    return balanced


def _write_captions(
    output_path: Path,
    scene_narration_parts: Sequence[str],
    scene_durations: Sequence[float],
    effective_pause_seconds: float,
) -> int:
    """Write cues within each scene's measured speech interval."""

    if len(scene_narration_parts) != len(scene_durations):
        raise ValueError("Caption scenes and visual scene durations must align")

    cue_index = 1
    scene_start = 0.0
    lines = ["WEBVTT", ""]
    for scene_index, (narration_part, scene_duration) in enumerate(
        zip(scene_narration_parts, scene_durations, strict=True)
    ):
        scene_end = scene_start + scene_duration
        half_pause = effective_pause_seconds / 2
        spoken_start = scene_start + (LEAD_SECONDS if scene_index == 0 else half_pause)
        spoken_end = scene_end - (
            TAIL_SECONDS
            if scene_index == len(scene_narration_parts) - 1
            else half_pause
        )
        if spoken_end <= spoken_start:
            raise ValueError("Caption scene has no positive spoken interval")

        spoken_duration = spoken_end - spoken_start
        cues = _split_caption_cues(narration_part)
        scene_character_rate = sum(len(cue) for cue in cues) / spoken_duration
        if scene_character_rate > CAPTION_MAX_CHARACTERS_PER_SECOND:
            raise ValueError(
                "Caption scene exceeds the reading-speed limit: "
                f"{scene_character_rate:.2f} characters per second"
            )
        min_characters = max(
            1,
            math.ceil(scene_character_rate * CAPTION_MIN_SECONDS),
        )
        cues = _rebalance_short_caption_cues(cues, min_characters)
        weights = [max(1, len(cue)) for cue in cues]
        total_weight = sum(weights)
        elapsed_weight = 0
        for local_index, (cue, weight) in enumerate(zip(cues, weights, strict=True)):
            cue_start = spoken_start + (
                (spoken_end - spoken_start) * elapsed_weight / total_weight
            )
            elapsed_weight += weight
            cue_end = (
                spoken_end
                if local_index == len(cues) - 1
                else spoken_start
                + (spoken_end - spoken_start) * elapsed_weight / total_weight
            )
            cue_duration = cue_end - cue_start
            cue_character_rate = len(cue) / cue_duration
            if cue_duration < CAPTION_MIN_SECONDS:
                raise ValueError(
                    f"Caption cue is too brief: {cue_duration:.3f} seconds"
                )
            if cue_character_rate > CAPTION_MAX_CHARACTERS_PER_SECOND:
                raise ValueError(
                    "Caption cue exceeds the reading-speed limit: "
                    f"{cue_character_rate:.2f} characters per second"
                )
            lines.extend(
                [
                    str(cue_index),
                    f"{_vtt_timestamp(cue_start)} --> {_vtt_timestamp(cue_end)}",
                    cue,
                    "",
                ]
            )
            cue_index += 1
        scene_start = scene_end
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return cue_index - 1


def _load_openai_api_key() -> str:
    """Load the established repository key without exposing it in logs."""

    configured_path = os.environ.get("MPARANZA_SECRETS_FILE")
    secret_file = Path(configured_path) if configured_path else DEFAULT_SECRET_FILE
    text = secret_file.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*openAiKey\s*=\s*(.+?)\s*$", text)
    api_key = match.group(1).strip().strip('"').strip("'") if match else ""
    if len(api_key) < 20:
        raise RuntimeError(
            f"openAiKey is missing from the configured secrets file: {secret_file}"
        )
    return api_key


def _request_openai_speech(
    *,
    api_key: str,
    language: str,
    text: str,
    output_path: Path,
) -> None:
    """Generate one naturally paced scene with an approved OpenAI voice."""

    voice = video_voice_for_language(language)
    if language not in NARRATION_INSTRUCTIONS:
        raise ValueError(f"Missing narration instructions for {language!r}")
    body = json.dumps(
        {
            "model": OPENAI_VIDEO_TTS_MODEL,
            "voice": voice,
            "input": text,
            "instructions": NARRATION_INSTRUCTIONS[language],
            "response_format": "wav",
        }
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
    for attempt in range(1, TTS_MAX_ATTEMPTS + 1):
        retry_error: BaseException
        retry_reason: str
        try:
            # The request constructor uses the fixed HTTPS OpenAI speech endpoint.
            with urllib.request.urlopen(  # nosec B310
                request,
                timeout=240,
            ) as response:
                output_path.write_bytes(response.read())
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise RuntimeError(
                    f"Narration request was rejected with HTTP {exc.code}"
                ) from exc
            retry_error = exc
            retry_reason = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError) as exc:
            retry_error = exc
            retry_reason = "a transient network error"

        if attempt == TTS_MAX_ATTEMPTS:
            raise RuntimeError(
                "Narration request failed after "
                f"{TTS_MAX_ATTEMPTS} attempts due to {retry_reason}"
            ) from retry_error

        delay_seconds = min(
            TTS_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
            TTS_RETRY_MAX_SECONDS,
        )
        LOGGER.warning(
            "Retrying %s narration after %s (attempt %d/%d, %.1fs backoff)",
            language,
            retry_reason,
            attempt,
            TTS_MAX_ATTEMPTS,
            delay_seconds,
        )
        time.sleep(delay_seconds)


def _render_speech(
    *,
    api_key: str,
    ffmpeg: str,
    ffprobe: str,
    language: str,
    narration_parts: Sequence[str],
    work_root: Path,
    output_path: Path,
) -> tuple[int, float, float, list[float], float]:
    """Synthesize naturally paced scenes and join them with measured silence."""

    pause_count = len(narration_parts) - 1
    if pause_count < 1:
        raise ValueError("A guide must contain at least two narrated scenes")

    scene_paths = [
        work_root / f"narration-scene-{index + 1:02d}.wav"
        for index in range(len(narration_parts))
    ]
    scene_durations: list[float] = []
    for narration_part, scene_path in zip(narration_parts, scene_paths, strict=True):
        _request_openai_speech(
            api_key=api_key,
            language=language,
            text=narration_part,
            output_path=scene_path,
        )
        scene_durations.append(_probe_duration(ffprobe, scene_path))

    inter_scene_pause_seconds = NATURAL_INTER_SCENE_PAUSE_SECONDS
    pause_ms = round(inter_scene_pause_seconds * 1000)
    silence_path = work_root / "inter-scene-silence.wav"
    _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            f"{inter_scene_pause_seconds:.6f}",
            "-c:a",
            "pcm_s16le",
            str(silence_path),
        ]
    )

    concat_inputs: list[Path] = []
    for index, scene_path in enumerate(scene_paths):
        concat_inputs.append(scene_path)
        if index < pause_count:
            concat_inputs.append(silence_path)
    command: list[str] = [ffmpeg, "-y", "-v", "error"]
    for media_path in concat_inputs:
        command.extend(["-i", str(media_path)])
    labels: list[str] = []
    filters: list[str] = []
    for index in range(len(concat_inputs)):
        label = f"a{index}"
        labels.append(f"[{label}]")
        filters.append(
            f"[{index}:a]aresample=48000,"
            f"aformat=sample_fmts=s16:channel_layouts=mono[{label}]"
        )
    filters.append(f"{''.join(labels)}concat=n={len(concat_inputs)}:v=0:a=1[narration]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[narration]",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    _run(command)
    duration = _probe_duration(ffprobe, output_path)
    expected_duration = sum(scene_durations) + inter_scene_pause_seconds * pause_count
    if abs(duration - expected_duration) > 0.15:
        raise ValueError(
            "Joined narration drifted from measured speech: "
            f"{duration:.3f}s vs {expected_duration:.3f}s"
        )
    target_seconds = round(
        LEAD_SECONDS + expected_duration + TAIL_SECONDS,
        3,
    )
    return (
        pause_ms,
        inter_scene_pause_seconds,
        duration,
        scene_durations,
        target_seconds,
    )


def _render_frames(
    *,
    page: Page,
    frame_template: str,
    concept: dict[str, Any],
    language: str,
    localization: dict[str, Any],
    work_root: Path,
    poster_path: Path,
) -> list[Path]:
    """Render the six branded scene frames and one JPEG poster."""

    rendered_template = frame_template
    if concept["module"] == "check-entries" and concept["edition"] == "core":
        for (
            country_example,
            neutral_example,
        ) in CORE_CHECK_ENTRY_FRAME_REPLACEMENTS.items():
            if country_example not in rendered_template:
                raise ValueError(
                    f"Missing core frame replacement source: {country_example!r}"
                )
            rendered_template = rendered_template.replace(
                country_example,
                neutral_example,
            )

    frame_paths: list[Path] = []
    for scene_index in range(len(concept["scenes"])):
        frame_data = {
            "module": concept["module"],
            "brand": concept.get("brand", "Vera"),
            "lang": language,
            "title": localization["title"],
            "sceneIndex": scene_index,
            "onScreen": localization["onScreen"],
        }
        html = rendered_template.replace(
            "/*__FRAME_DATA__*/",
            json.dumps(frame_data, ensure_ascii=False),
        )
        page.set_content(html, wait_until="networkidle", timeout=45_000)
        page.wait_for_function(
            "document.body.dataset.ready === 'true'",
            timeout=10_000,
        )
        page.evaluate("document.fonts.ready")
        if not page.evaluate(
            "document.fonts.check('600 48px \\\"Instrument Sans\\\"')"
        ):
            raise RuntimeError("Instrument Sans did not load in the frame renderer")

        if concept["scope"] == "core":
            visible_text = page.locator("body").inner_text()
            forbidden_match = CORE_FRAME_FORBIDDEN_PATTERN.search(visible_text)
            if forbidden_match:
                raise ValueError(
                    "Core guide frame contains country-specific text: "
                    f"{forbidden_match.group(0)!r} in "
                    f"{concept['module']}/{language}/scene-{scene_index + 1}"
                )

        page.evaluate("window.scrollTo(0, 0)")
        layout = page.evaluate("""() => ({
                width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)
            })""")
        if layout["width"] > FRAME_WIDTH or layout["height"] > FRAME_HEIGHT:
            raise ValueError(
                "Guide frame overflows its canvas: "
                f"{layout['width']}x{layout['height']} for "
                f"{concept['module']}/{concept['edition']}/{language}/scene-{scene_index + 1}"
            )

        frame_path = work_root / f"frame-{scene_index + 1:02d}.png"
        page.screenshot(path=str(frame_path), type="png")
        frame_paths.append(frame_path)
        if scene_index == 0:
            page.screenshot(path=str(poster_path), type="jpeg", quality=92)

    frame_hashes = {_sha256(path) for path in frame_paths}
    if len(frame_hashes) != len(frame_paths):
        raise ValueError("Every guide scene must render a distinct frame")
    return frame_paths


def _render_slideshow(
    *,
    ffmpeg: str,
    frame_paths: Sequence[Path],
    scene_durations: Sequence[float],
    target_seconds: float,
    work_root: Path,
    output_path: Path,
) -> None:
    """Encode the static editorial frames as a standards-based H.264 stream."""

    concat_path = work_root / "frames.ffconcat"
    concat_lines = ["ffconcat version 1.0"]
    for frame_path, duration in zip(frame_paths, scene_durations, strict=True):
        concat_lines.append(f"file '{frame_path.as_posix()}'")
        concat_lines.append(f"duration {duration:.6f}")
    concat_lines.append(f"file '{frame_paths[-1].as_posix()}'")
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            f"fps={FRAME_RATE},scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=lanczos,format=yuv420p",
            "-t",
            f"{target_seconds:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-g",
            str(FRAME_RATE * 2),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def _normalize_audio(
    *,
    ffmpeg: str,
    narration_path: Path,
    target_seconds: float,
    output_path: Path,
) -> None:
    """Normalize, lead, and pad narration to the exact guide duration."""

    delay_ms = round(LEAD_SECONDS * 1000)
    audio_filter = (
        "aresample=48000,"
        f"loudnorm=I={TARGET_LOUDNESS_LUFS}:TP=-1.5:LRA=11,"
        f"adelay={delay_ms}|{delay_ms},"
        f"apad=whole_dur={target_seconds:.3f},"
        f"atrim=duration={target_seconds:.3f}"
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(narration_path),
            "-af",
            audio_filter,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(output_path),
        ]
    )


def _mux_guide(
    *,
    ffmpeg: str,
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    """Combine validated local video and narration streams."""

    _run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def _validate_transition_silence(
    *,
    ffmpeg: str,
    video_path: Path,
    scene_durations: Sequence[float],
) -> list[float]:
    """Verify every encoded frame transition remains inside silent audio."""

    transition_seconds: list[float] = []
    elapsed = 0.0
    for scene_duration in scene_durations[:-1]:
        elapsed += scene_duration
        transition_seconds.append(elapsed)

    window_seconds = TRANSITION_SILENCE_MARGIN_SECONDS * 2
    for transition in transition_seconds:
        result = _run(
            [
                ffmpeg,
                "-ss",
                f"{transition - TRANSITION_SILENCE_MARGIN_SECONDS:.6f}",
                "-i",
                str(video_path),
                "-t",
                f"{window_seconds:.6f}",
                "-map",
                "0:a:0",
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
        )
        match = re.search(r"max_volume:\s+(-?inf|-?\d+(?:\.\d+)?) dB", result.stderr)
        if not match:
            raise ValueError(
                f"Could not measure audio at visual transition {transition:.3f}s"
            )
        measured = match.group(1)
        if measured != "-inf" and float(measured) > TRANSITION_MAX_VOLUME_DB:
            raise ValueError(
                "Visual transition overlaps audible narration: "
                f"{transition:.3f}s at {float(measured):.1f} dB"
            )
    return transition_seconds


def _validate_media(
    *,
    ffmpeg: str,
    ffprobe: str,
    video_path: Path,
    poster_path: Path,
    target_seconds: float,
) -> dict[str, Any]:
    """Decode and verify the codecs, dimensions, duration, poster, and audio."""

    probe = _probe_media(ffprobe, video_path)
    streams = probe["streams"]
    video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in streams if stream["codec_type"] == "audio")
    duration = float(probe["format"]["duration"])
    if abs(duration - target_seconds) > 0.25:
        raise ValueError(
            f"Guide duration drifted from target: {duration:.3f}s vs {target_seconds:.3f}s"
        )
    expected_video = {
        "codec_name": "h264",
        "width": FRAME_WIDTH,
        "height": FRAME_HEIGHT,
        "pix_fmt": "yuv420p",
    }
    for field, expected in expected_video.items():
        if video_stream.get(field) != expected:
            raise ValueError(
                f"Unexpected video {field}: {video_stream.get(field)!r} != {expected!r}"
            )
    if audio_stream.get("codec_name") != "aac":
        raise ValueError(f"Unexpected audio codec: {audio_stream.get('codec_name')}")
    if audio_stream.get("sample_rate") != "48000":
        raise ValueError(
            f"Unexpected audio sample rate: {audio_stream.get('sample_rate')}"
        )

    poster_probe = _probe_media(ffprobe, poster_path)
    poster_stream = next(
        stream for stream in poster_probe["streams"] if stream["codec_type"] == "video"
    )
    if (
        poster_stream.get("width"),
        poster_stream.get("height"),
    ) != (FRAME_WIDTH, FRAME_HEIGHT):
        raise ValueError("Poster dimensions do not match the guide frame")

    _run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(video_path),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
    )
    volume = _run(
        [
            ffmpeg,
            "-i",
            str(video_path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
    )
    if "mean_volume: -inf dB" in volume.stderr:
        raise ValueError("Rendered narration is silent")

    return {
        "durationSeconds": round(duration, 3),
        "width": video_stream["width"],
        "height": video_stream["height"],
        "frameRate": video_stream["avg_frame_rate"],
        "pixelFormat": video_stream["pix_fmt"],
        "videoCodec": video_stream["codec_name"],
        "audioCodec": audio_stream["codec_name"],
        "audioSampleRate": int(audio_stream["sample_rate"]),
        "audioChannels": audio_stream["channels"],
    }


def _build_one_guide(
    *,
    page: Page,
    frame_template: str,
    concept: dict[str, Any],
    language: str,
    localization: dict[str, Any],
    api_key: str,
    ffmpeg: str,
    ffprobe: str,
    build_input_sha256: str,
) -> dict[str, Any]:
    """Build and validate one localized YouTube guide."""

    module = concept["module"]
    edition = concept["edition"]
    planned_seconds = float(concept["targetDurationSeconds"])
    output_dir = OUTPUT_ROOT / module / edition / language
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / "guide.mp4"
    poster_path = output_dir / "poster.jpg"
    captions_path = output_dir / "captions.vtt"
    scene_narration_parts = partition_narration_scenes(
        localization["narration"],
        len(concept["scenes"]),
    )
    LOGGER.info("Rendering %s / %s / %s", module, edition, language)
    with tempfile.TemporaryDirectory(
        prefix=f"vera-{module}-{edition}-{language}-"
    ) as temp_dir:
        work_root = Path(temp_dir)
        frame_paths = _render_frames(
            page=page,
            frame_template=frame_template,
            concept=concept,
            language=language,
            localization=localization,
            work_root=work_root,
            poster_path=poster_path,
        )
        narration_path = work_root / "narration.wav"
        (
            inter_scene_pause_ms,
            effective_pause_seconds,
            speech_duration,
            scene_speech_durations,
            target_seconds,
        ) = _render_speech(
            api_key=api_key,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            language=language,
            narration_parts=scene_narration_parts,
            work_root=work_root,
            output_path=narration_path,
        )
        scene_durations = _scene_durations(
            scene_speech_durations,
            target_seconds,
            effective_pause_seconds,
        )
        visual_path = work_root / "visual.mp4"
        audio_path = work_root / "narration.m4a"
        _render_slideshow(
            ffmpeg=ffmpeg,
            frame_paths=frame_paths,
            scene_durations=scene_durations,
            target_seconds=target_seconds,
            work_root=work_root,
            output_path=visual_path,
        )
        _normalize_audio(
            ffmpeg=ffmpeg,
            narration_path=narration_path,
            target_seconds=target_seconds,
            output_path=audio_path,
        )
        _mux_guide(
            ffmpeg=ffmpeg,
            video_path=visual_path,
            audio_path=audio_path,
            output_path=video_path,
        )

    cue_count = _write_captions(
        captions_path,
        scene_narration_parts,
        scene_durations,
        effective_pause_seconds,
    )
    media = _validate_media(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        video_path=video_path,
        poster_path=poster_path,
        target_seconds=target_seconds,
    )
    transition_seconds = _validate_transition_silence(
        ffmpeg=ffmpeg,
        video_path=video_path,
        scene_durations=scene_durations,
    )
    files = {
        "video": _artifact_record(video_path, "video/mp4"),
        "poster": _artifact_record(poster_path, "image/jpeg"),
        "captions": _artifact_record(captions_path, "text/vtt"),
    }
    return {
        "conceptId": concept["conceptId"],
        "module": module,
        "edition": edition,
        "scope": concept["scope"],
        "jurisdiction": concept["jurisdiction"],
        "language": language,
        "languageLabel": LANGUAGE_LABELS[language],
        "title": localization["title"],
        "status": "youtube_ready",
        "buildInputSha256": build_input_sha256,
        "plannedDurationSeconds": planned_seconds,
        "targetDurationSeconds": target_seconds,
        "speechDurationSeconds": round(speech_duration, 3),
        "voice": {
            "name": video_voice_for_language(language),
            "model": OPENAI_VIDEO_TTS_MODEL,
            "interScenePauseMs": inter_scene_pause_ms,
            "effectiveInterScenePauseSeconds": round(effective_pause_seconds, 3),
        },
        "pageTargets": concept["pageTargets"],
        "cueCount": cue_count,
        "sceneSpeechDurationsSeconds": [
            round(value, 3) for value in scene_speech_durations
        ],
        "sceneDurationsSeconds": [round(value, 3) for value in scene_durations],
        "transitionSafety": {
            "sentenceBoundaryOnly": True,
            "visualCutPlacement": "inter-scene-silence-midpoint",
            "minimumInterSceneSilenceSeconds": MIN_INTER_SCENE_PAUSE_SECONDS,
            "validatedSilenceMarginSeconds": TRANSITION_SILENCE_MARGIN_SECONDS,
            "maximumValidatedVolumeDb": TRANSITION_MAX_VOLUME_DB,
            "transitionSeconds": [round(value, 3) for value in transition_seconds],
        },
        "files": files,
        "media": media,
    }


def _build_captions_only_entry(
    *,
    concept: dict[str, Any],
    language: str,
    localization: dict[str, Any],
    existing_entry: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild captions while preserving the validated rendered media."""

    identity = (concept["module"], concept["edition"], language)
    existing_identity = (
        existing_entry["module"],
        existing_entry["edition"],
        existing_entry["language"],
    )
    if existing_identity != identity:
        raise ValueError(
            f"Caption-only manifest identity mismatch: {existing_identity!r}"
        )
    if existing_entry["title"] != localization["title"]:
        raise ValueError(
            "Caption-only rendering cannot apply a changed title; "
            f"render {identity!r} in full"
        )

    output_dir = OUTPUT_ROOT / concept["module"] / concept["edition"] / language
    captions_path = output_dir / "captions.vtt"

    scene_narration_parts = partition_narration_scenes(
        localization["narration"],
        len(concept["scenes"]),
    )
    scene_durations = [
        float(value) for value in existing_entry["sceneDurationsSeconds"]
    ]
    effective_pause_seconds = float(
        existing_entry["voice"]["effectiveInterScenePauseSeconds"]
    )
    cue_count = _write_captions(
        captions_path,
        scene_narration_parts,
        scene_durations,
        effective_pause_seconds,
    )

    entry = dict(existing_entry)
    files = dict(existing_entry["files"])
    files["captions"] = _artifact_record(captions_path, "text/vtt")
    entry.update(
        {
            "conceptId": concept["conceptId"],
            "scope": concept["scope"],
            "jurisdiction": concept["jurisdiction"],
            "pageTargets": concept["pageTargets"],
            "cueCount": cue_count,
            "files": files,
        }
    )
    return entry


def build_vera_youtube_video_guides(
    modules: set[str] | None = None,
    editions: set[str] | None = None,
    *,
    languages: set[str] | None = None,
    captions_only: bool = False,
) -> Path:
    """Render selected Vera YouTube masters and write the complete manifest."""

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for concept in spec["concepts"]:
        scope = concept["scope"]
        jurisdiction = concept["jurisdiction"]
        if scope not in {"core", "country"}:
            raise ValueError(f"Unsupported guide scope: {scope!r}")
        if scope == "core" and jurisdiction is not None:
            raise ValueError("Core guides must not declare a jurisdiction")
        if scope == "country" and jurisdiction != "IT":
            raise ValueError("The current country guide pack must declare IT")

    localizations = {
        (concept["module"], concept["edition"], language)
        for concept in spec["concepts"]
        for language in concept["localizations"]
    }
    if localizations != EXPECTED_LOCALIZATIONS:
        raise ValueError(f"Unexpected Vera localization set: {sorted(localizations)!r}")

    available_modules = {concept["module"] for concept in spec["concepts"]}
    if modules:
        unknown_modules = modules - available_modules
        if unknown_modules:
            raise ValueError(f"Unknown Vera guide modules: {sorted(unknown_modules)!r}")
    available_editions = {concept["edition"] for concept in spec["concepts"]}
    if editions:
        unknown_editions = editions - available_editions
        if unknown_editions:
            raise ValueError(
                f"Unknown Vera guide editions: {sorted(unknown_editions)!r}"
            )
    available_languages = {
        language
        for concept in spec["concepts"]
        for language in concept["localizations"]
    }
    if languages:
        unknown_languages = languages - available_languages
        if unknown_languages:
            raise ValueError(
                f"Unknown Vera guide languages: {sorted(unknown_languages)!r}"
            )
    selected_concepts = [
        concept
        for concept in spec["concepts"]
        if (not modules or concept["module"] in modules)
        and (not editions or concept["edition"] in editions)
    ]
    if not selected_concepts:
        raise ValueError("The selected module and edition filters match no guides")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    existing_manifest = (
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if MANIFEST_PATH.is_file()
        else None
    )
    existing_entries = {
        (entry["module"], entry["edition"], entry["language"]): entry
        for entry in (existing_manifest or {}).get("assets", [])
    }
    rendered_entries: list[dict[str, Any]] = []
    if captions_only:
        if existing_manifest is None:
            raise ValueError("Caption-only rendering requires an existing manifest")
        for concept in selected_concepts:
            for language, localization in concept["localizations"].items():
                if languages and language not in languages:
                    continue
                identity = (concept["module"], concept["edition"], language)
                if identity not in existing_entries:
                    raise ValueError(
                        "Caption-only rendering is missing the existing entry "
                        f"{identity!r}"
                    )
                rendered_entries.append(
                    _build_captions_only_entry(
                        concept=concept,
                        language=language,
                        localization=localization,
                        existing_entry=existing_entries[identity],
                    )
                )
    else:
        api_key = _load_openai_api_key()
        ffmpeg = _required_tool("ffmpeg", "/opt/homebrew/bin/ffmpeg")
        ffprobe = _required_tool("ffprobe", "/opt/homebrew/bin/ffprobe")
        frame_template = FRAME_TEMPLATE_PATH.read_text(encoding="utf-8")
        if "/*__FRAME_DATA__*/" not in frame_template:
            raise ValueError("Frame template is missing its data marker")

        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
                device_scale_factor=1,
            )
            page.on("pageerror", lambda error: LOGGER.error("Frame error: %s", error))
            page.on(
                "console",
                lambda message: (
                    LOGGER.error("Frame console: %s", message.text)
                    if message.type == "error"
                    else None
                ),
            )
            try:
                for concept in selected_concepts:
                    for language, localization in concept["localizations"].items():
                        if languages and language not in languages:
                            continue
                        build_input_sha256 = _build_input_sha256(
                            concept=concept,
                            language=language,
                            localization=localization,
                            frame_template=frame_template,
                        )
                        checkpoint = _load_valid_checkpoint(
                            concept=concept,
                            language=language,
                            build_input_sha256=build_input_sha256,
                        )
                        if checkpoint is not None:
                            LOGGER.info(
                                "Reusing %s / %s / %s",
                                concept["module"],
                                concept["edition"],
                                language,
                            )
                            rendered_entries.append(checkpoint)
                            continue
                        entry = _build_one_guide(
                            page=page,
                            frame_template=frame_template,
                            concept=concept,
                            language=language,
                            localization=localization,
                            api_key=api_key,
                            ffmpeg=ffmpeg,
                            ffprobe=ffprobe,
                            build_input_sha256=build_input_sha256,
                        )
                        _write_checkpoint(entry)
                        rendered_entries.append(entry)
            finally:
                browser.close()

    entries_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    if modules or editions or languages or captions_only:
        entries_by_identity.update(existing_entries)
    entries_by_identity.update(
        {
            (entry["module"], entry["edition"], entry["language"]): entry
            for entry in rendered_entries
        }
    )
    ordered_identities = [
        (concept["module"], concept["edition"], language)
        for concept in spec["concepts"]
        for language in concept["localizations"]
    ]
    missing_identities = [
        identity
        for identity in ordered_identities
        if identity not in entries_by_identity
    ]
    if missing_identities:
        raise ValueError(
            "Filtered render cannot produce a complete manifest; missing "
            f"{missing_identities!r}"
        )
    entries = [entries_by_identity[identity] for identity in ordered_identities]
    for identity, entry in zip(ordered_identities, entries, strict=True):
        _validate_youtube_ready_manifest_entry(
            entry,
            expected_identity=identity,
        )

    manifest = {
        "schemaVersion": "3.0.0",
        "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "publicationStatus": "rendered_pending_youtube",
        "remotePublish": True,
        "generator": "scripts/build_vera_youtube_video_guides.py",
        "frameTemplate": _source_path(FRAME_TEMPLATE_PATH),
        "specification": _source_path(SPEC_PATH),
        "assetCount": len(entries),
        "assets": entries,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOGGER.info("Wrote %s validated guide assets to %s", len(entries), MANIFEST_PATH)
    return MANIFEST_PATH


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render multilingual Vera and shared YouTube masters.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show subprocess-level diagnostic detail.",
    )
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Render only this module and preserve other validated manifest entries.",
    )
    parser.add_argument(
        "--edition",
        action="append",
        dest="editions",
        help="Render only this edition and preserve other validated manifest entries.",
    )
    parser.add_argument(
        "--language",
        action="append",
        dest="languages",
        help="Render only this language and preserve other validated manifest entries.",
    )
    parser.add_argument(
        "--captions-only",
        action="store_true",
        help="Rebuild captions from matching rendered media without changing it.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the command-line renderer."""

    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    build_vera_youtube_video_guides(
        set(args.modules) if args.modules else None,
        set(args.editions) if args.editions else None,
        languages=set(args.languages) if args.languages else None,
        captions_only=args.captions_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
