from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil

# Fixed local media tools are invoked with argument lists and without a shell.
import subprocess  # nosec B404
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from playwright.sync_api import Browser, Page, sync_playwright

__all__ = ["build_vera_local_video_guides", "main"]

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = REPO_ROOT / "static" / "shared" / "video-production"
SPEC_PATH = PRODUCTION_ROOT / "vera-missing-guides.json"
FRAME_TEMPLATE_PATH = PRODUCTION_ROOT / "guide-frame.html"
OUTPUT_ROOT = PRODUCTION_ROOT / "rendered"
MANIFEST_PATH = OUTPUT_ROOT / "manifest.json"

VOICE_BY_LANGUAGE = {
    "it": "Alice",
    "en": "Samantha",
    "fr": "Thomas",
    "de": "Anna",
}
LANGUAGE_LABELS = {
    "it": "Italiano",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
}
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_RATE = 30
LEAD_SECONDS = 0.8
TAIL_SECONDS = 0.8
TARGET_LOUDNESS_LUFS = -16
EXPECTED_LOCALIZATIONS = {
    ("client-onboarding", "core", "it"),
    ("client-onboarding", "core", "en"),
    ("client-onboarding", "core", "fr"),
    ("client-onboarding", "core", "de"),
    ("client-onboarding", "italy", "it"),
    ("client-onboarding", "italy", "en"),
    ("client-onboarding", "italy", "fr"),
    ("client-onboarding", "italy", "de"),
    ("journal-sampling", "core", "it"),
    ("journal-sampling", "core", "en"),
    ("journal-sampling", "core", "fr"),
    ("journal-sampling", "core", "de"),
    ("check-entries", "core", "it"),
    ("check-entries", "core", "en"),
    ("check-entries", "core", "fr"),
    ("check-entries", "core", "de"),
    ("check-entries", "italy-fatturapa", "en"),
    ("check-entries", "italy-fatturapa", "fr"),
    ("check-entries", "italy-fatturapa", "de"),
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


def _artifact_record(path: Path, mime_type: str) -> dict[str, Any]:
    """Describe a rendered artifact relative to the output manifest."""

    return {
        "path": path.relative_to(OUTPUT_ROOT).as_posix(),
        "mimeType": mime_type,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sentences(text: str) -> list[str]:
    """Split narration into ordered sentences without losing punctuation."""

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip())]
    return [part for part in parts if part]


def _partition_sentences(text: str, group_count: int) -> list[str]:
    """Partition narration into contiguous, near-balanced scene captions."""

    sentences = _sentences(text)
    if len(sentences) < group_count:
        words = text.split()
        groups: list[str] = []
        for index in range(group_count):
            start = round(index * len(words) / group_count)
            end = round((index + 1) * len(words) / group_count)
            groups.append(" ".join(words[start:end]))
        return groups

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
    captions: Sequence[str],
    target_seconds: float,
    effective_pause_seconds: float,
) -> list[float]:
    """Allocate visual time by narration weight with fixed lead and tail."""

    pause_count = len(captions) - 1
    spoken_seconds = (
        target_seconds
        - LEAD_SECONDS
        - TAIL_SECONDS
        - effective_pause_seconds * pause_count
    )
    if spoken_seconds <= 0:
        raise ValueError("Inter-scene pauses leave no time for narration")
    weights = [max(1, len(caption.split())) for caption in captions]
    weight_total = sum(weights)
    durations = [spoken_seconds * weight / weight_total for weight in weights]
    for index in range(pause_count):
        durations[index] += effective_pause_seconds
    durations[0] += LEAD_SECONDS
    durations[-1] += TAIL_SECONDS
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


def _write_captions(
    output_path: Path,
    captions: Sequence[str],
    scene_durations: Sequence[float],
) -> None:
    """Write one readable cue per visual scene."""

    cue_start = LEAD_SECONDS
    lines = ["WEBVTT", ""]
    for index, (caption, scene_duration) in enumerate(
        zip(captions, scene_durations, strict=True),
        start=1,
    ):
        spoken_scene_duration = scene_duration
        if index == 1:
            spoken_scene_duration -= LEAD_SECONDS
        if index == len(captions):
            spoken_scene_duration -= TAIL_SECONDS
        cue_end = cue_start + spoken_scene_duration
        lines.extend(
            [
                str(index),
                f"{_vtt_timestamp(cue_start)} --> {_vtt_timestamp(cue_end)}",
                caption,
                "",
            ]
        )
        cue_start = cue_end
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _render_speech(
    *,
    say: str,
    ffprobe: str,
    voice: str,
    narration_parts: Sequence[str],
    target_seconds: float,
    output_path: Path,
) -> tuple[int, int, float, float]:
    """Synthesize narration at a measured rate without trimming spoken text."""

    desired_seconds = target_seconds - LEAD_SECONDS - TAIL_SECONDS
    rate = 100
    plain_narration = " ".join(narration_parts)
    duration = 0.0
    for _ in range(6):
        _run(
            [
                say,
                "-v",
                voice,
                "-r",
                str(rate),
                "-o",
                str(output_path),
                plain_narration,
            ]
        )
        duration = _probe_duration(ffprobe, output_path)
        if duration <= desired_seconds:
            break
        rate = min(220, max(rate + 1, math.ceil(rate * duration / desired_seconds)))

    plain_duration = duration
    pause_count = max(1, len(narration_parts) - 1)
    pause_ms = max(0, round((desired_seconds - duration) * 1000 / pause_count))
    pause_ms = min(3500, pause_ms)
    for _ in range(6):
        narrated_text = f" [[slnc {pause_ms}]] ".join(narration_parts)
        _run(
            [
                say,
                "-v",
                voice,
                "-r",
                str(rate),
                "-o",
                str(output_path),
                narrated_text,
            ]
        )
        duration = _probe_duration(ffprobe, output_path)
        delta_seconds = desired_seconds - duration
        if -0.15 <= delta_seconds <= 0.25:
            break
        pause_ms = min(
            3500,
            max(0, pause_ms + round(delta_seconds * 1000 / pause_count)),
        )

    if duration > desired_seconds + 0.15 or duration < desired_seconds - 0.35:
        raise ValueError(
            f"Narration did not converge on its target: {duration:.3f}s vs "
            f"{desired_seconds:.3f}s ({voice}, rate {rate}, pause {pause_ms}ms)"
        )
    effective_pause_seconds = max(0.0, (duration - plain_duration) / pause_count)
    return rate, pause_ms, effective_pause_seconds, duration


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
    say: str,
    ffmpeg: str,
    ffprobe: str,
) -> dict[str, Any]:
    """Build and validate one localized Vera guide."""

    module = concept["module"]
    edition = concept["edition"]
    target_seconds = float(concept["targetDurationSeconds"])
    output_dir = OUTPUT_ROOT / module / edition / language
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / "guide.mp4"
    poster_path = output_dir / "poster.jpg"
    captions_path = output_dir / "captions.vtt"
    transcript_path = output_dir / "transcript.txt"
    captions = _partition_sentences(
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
        narration_path = work_root / "narration.aiff"
        voice = VOICE_BY_LANGUAGE[language]
        (
            speech_rate,
            inter_scene_pause_ms,
            effective_pause_seconds,
            speech_duration,
        ) = _render_speech(
            say=say,
            ffprobe=ffprobe,
            voice=voice,
            narration_parts=captions,
            target_seconds=target_seconds,
            output_path=narration_path,
        )
        scene_durations = _scene_durations(
            captions,
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

    _write_captions(captions_path, captions, scene_durations)
    transcript_path.write_text(
        f"{localization['title']}\n\n{localization['narration']}\n",
        encoding="utf-8",
    )
    media = _validate_media(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        video_path=video_path,
        poster_path=poster_path,
        target_seconds=target_seconds,
    )
    files = {
        "video": _artifact_record(video_path, "video/mp4"),
        "poster": _artifact_record(poster_path, "image/jpeg"),
        "captions": _artifact_record(captions_path, "text/vtt"),
        "transcript": _artifact_record(transcript_path, "text/plain"),
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
        "status": "local_rendered",
        "targetDurationSeconds": target_seconds,
        "speechDurationSeconds": round(speech_duration, 3),
        "voice": {
            "name": VOICE_BY_LANGUAGE[language],
            "rate": speech_rate,
            "interScenePauseMs": inter_scene_pause_ms,
            "effectiveInterScenePauseSeconds": round(effective_pause_seconds, 3),
        },
        "pageTargets": concept["pageTargets"],
        "cueCount": len(captions),
        "sceneDurationsSeconds": [round(value, 3) for value in scene_durations],
        "files": files,
        "media": media,
    }


def build_vera_local_video_guides() -> Path:
    """Render all missing Vera guide localizations and write their manifest."""

    say = _required_tool("say", "/usr/bin/say")
    ffmpeg = _required_tool("ffmpeg", "/opt/homebrew/bin/ffmpeg")
    ffprobe = _required_tool("ffprobe", "/opt/homebrew/bin/ffprobe")
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    frame_template = FRAME_TEMPLATE_PATH.read_text(encoding="utf-8")
    if "/*__FRAME_DATA__*/" not in frame_template:
        raise ValueError("Frame template is missing its data marker")

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

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
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
            for concept in spec["concepts"]:
                for language, localization in concept["localizations"].items():
                    entries.append(
                        _build_one_guide(
                            page=page,
                            frame_template=frame_template,
                            concept=concept,
                            language=language,
                            localization=localization,
                            say=say,
                            ffmpeg=ffmpeg,
                            ffprobe=ffprobe,
                        )
                    )
        finally:
            browser.close()

    manifest = {
        "schemaVersion": "2.0.0",
        "generatedAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "publicationStatus": "local_rendered",
        "remotePublish": False,
        "generator": "scripts/build_vera_local_video_guides.py",
        "frameTemplate": "../guide-frame.html",
        "specification": "../vera-missing-guides.json",
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
        description="Render the local multilingual Vera website guides.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show subprocess-level diagnostic detail.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the command-line renderer."""

    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    build_vera_local_video_guides()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
