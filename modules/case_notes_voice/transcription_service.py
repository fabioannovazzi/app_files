"""Transport-independent audio preparation, transcription and coverage service."""

from __future__ import annotations

import logging
import math
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Mapping

from modules.case_notes_voice.transcription_transport import (
    TranscriptionProviderError,
    request_transcription,
)
from modules.utilities import config as utilities_config

__all__ = [
    "create_audio_transcription",
    "VoiceSessionError",
    "DEFAULT_UPLOAD_TRANSCRIPTION_MODEL",
    "AudioTranscriptionResult",
]

LOGGER = logging.getLogger(__name__)


DEFAULT_UPLOAD_TRANSCRIPTION_MODEL = utilities_config.get_naming_params()[
    "gptTranscribe"
]


MAX_CASE_CONTEXT_CHARS = 12_000


MAX_AUDIO_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


MAX_OPENAI_AUDIO_TRANSCRIPTION_BYTES = 24 * 1024 * 1024


MAX_STREAM_COPY_SPLIT_ATTEMPTS = 256


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


SUPPORTED_TRANSCRIPTION_LANGUAGES = {"it", "en", "fr", "de", "es"}


SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}


FFMPEG_DURATION_RE = re.compile(
    r"Duration:\s*(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+(?:\.\d+)?)"
)


class VoiceSessionError(RuntimeError):
    """Raised when the hosted voice surface cannot complete an action."""


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
        fields["languages[]"] = language
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
        payload = request_transcription(request, timeout_seconds=timeout_seconds)
    except TranscriptionProviderError as exc:
        if exc.category == "timeout":
            raise VoiceSessionError(
                _openai_timeout_message(
                    action="Audio transcription", timeout_seconds=timeout_seconds
                )
            ) from exc
        raise VoiceSessionError(str(exc)) from exc
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
