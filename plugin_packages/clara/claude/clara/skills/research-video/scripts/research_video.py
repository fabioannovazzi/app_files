#!/usr/bin/env python3
"""Prepare, approve, render, and validate a source-grounded research video."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess  # nosec B404
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
import wave
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

__all__ = [
    "approve_run",
    "main",
    "prepare_run",
    "render_run",
]

LOGGER = logging.getLogger(__name__)

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
OPENAI_SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
OPENAI_TTS_VOICE = "cedar"
TTS_INSTRUCTIONS = (
    "Speak in natural contemporary English, like an experienced professional "
    "explaining carefully reviewed research to a colleague. Keep the delivery "
    "calm, clear, measured, and conversational. Never sound promotional, "
    "dramatic, emphatic, or like a radio advertisement. Preserve qualifications "
    "and pronounce figures deliberately."
)

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_RATE = 30
LEAD_SECONDS = 0.6
TAIL_SECONDS = 0.6
INTER_SCENE_PAUSE_SECONDS = 0.9
TRANSITION_SECONDS = 0.4
TARGET_LOUDNESS_LUFS = -16
MAX_SCENES = 20
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
MAX_NARRATION_CHARACTERS = 2500
MOTION_VALUES = {
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "static",
    "layered_parallax",
}
FLAT_MOTION_SEQUENCE = ("zoom_in", "pan_right", "zoom_out", "pan_left")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SCENE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one local file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    """Return a canonical digest for a JSON-compatible value."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: object) -> None:
    """Write readable UTF-8 JSON with a final newline."""

    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object or raise a precise contract error."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _nonempty_text(value: object, *, field: str, maximum: int) -> str:
    """Return normalized non-empty text within a mechanical size bound."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    return normalized


def _ensure_output_boundary(output_dir: Path) -> Path:
    """Keep user-data runs outside editable or packaged plugin source."""

    resolved = output_dir.expanduser().resolve()
    if resolved == PLUGIN_ROOT or resolved.is_relative_to(PLUGIN_ROOT):
        raise ValueError("Research-video outputs must stay outside plugin source")
    return resolved


def _inspect_image(path_value: object, *, field: str) -> dict[str, Any]:
    """Validate and fingerprint one ordinary raster image."""

    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError(f"{field} must name a local image")
    candidate = Path(path_value).expanduser()
    if candidate.is_symlink():
        raise ValueError(f"{field} must not be a symbolic link")
    path = candidate.resolve()
    if not path.is_file():
        raise ValueError(f"{field} does not exist: {path}")
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError(f"{field} must be PNG, JPEG, or WebP: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_IMAGE_BYTES:
        raise ValueError(f"{field} has an unsupported size: {size} bytes")
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
            image_format = image.format or path.suffix.lstrip(".").upper()
            has_alpha = mode in {"LA", "RGBA"} or "transparency" in image.info
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValueError(f"{field} is not a readable image: {path}") from exc
    if width < 64 or height < 64:
        raise ValueError(f"{field} is too small for video: {width}x{height}")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"{field} exceeds {MAX_IMAGE_PIXELS} decoded pixels")
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": size,
        "width": width,
        "height": height,
        "mode": mode,
        "format": image_format,
        "has_alpha": has_alpha,
    }


def _validate_source_basis(value: object, *, scene_id: str) -> list[dict[str, str]]:
    """Validate explicit source-basis records without judging their meaning."""

    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise ValueError(f"Scene {scene_id} requires 1-12 source_basis items")
    basis: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict) or set(item) != {"reference", "supports"}:
            raise ValueError(
                f"Scene {scene_id} source_basis item {index} has invalid fields"
            )
        basis.append(
            {
                "reference": _nonempty_text(
                    item["reference"],
                    field=f"Scene {scene_id} source_basis reference",
                    maximum=500,
                ),
                "supports": _nonempty_text(
                    item["supports"],
                    field=f"Scene {scene_id} source_basis support",
                    maximum=1200,
                ),
            }
        )
    return basis


def _canonicalize_plan(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate one scene plan and return canonical content plus visual inventory."""

    if set(raw) != {"schema_version", "title", "language", "scenes"}:
        raise ValueError("Scene plan has unexpected or missing top-level fields")
    if raw["schema_version"] != 1:
        raise ValueError("scene_plan.schema_version must be 1")
    if raw["language"] != "en":
        raise ValueError("The first research-video contract supports English only")
    title = _nonempty_text(raw["title"], field="title", maximum=180)
    scenes_value = raw["scenes"]
    if not isinstance(scenes_value, list) or not 2 <= len(scenes_value) <= MAX_SCENES:
        raise ValueError(f"Scene plan requires 2-{MAX_SCENES} scenes")

    canonical_scenes: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    allowed_fields = {
        "id",
        "image",
        "foreground_image",
        "narration",
        "motion",
        "source_basis",
    }
    for index, value in enumerate(scenes_value):
        if not isinstance(value, dict) or not set(value) <= allowed_fields:
            raise ValueError(f"Scene {index + 1} has unsupported fields")
        if not {"id", "image", "narration", "source_basis"} <= set(value):
            raise ValueError(f"Scene {index + 1} is missing required fields")
        scene_id = _nonempty_text(value["id"], field="scene.id", maximum=64)
        if not SCENE_ID_PATTERN.fullmatch(scene_id):
            raise ValueError(f"Invalid scene id: {scene_id!r}")
        if scene_id in seen_ids:
            raise ValueError(f"Duplicate scene id: {scene_id}")
        seen_ids.add(scene_id)

        image = _inspect_image(value["image"], field=f"Scene {scene_id} image")
        foreground_value = value.get("foreground_image")
        motion = (
            value.get("motion")
            or FLAT_MOTION_SEQUENCE[index % len(FLAT_MOTION_SEQUENCE)]
        )
        if motion not in MOTION_VALUES:
            raise ValueError(f"Scene {scene_id} has unsupported motion: {motion!r}")
        foreground: dict[str, Any] | None = None
        if foreground_value is not None:
            foreground = _inspect_image(
                foreground_value,
                field=f"Scene {scene_id} foreground_image",
            )
            if motion != "layered_parallax":
                raise ValueError(
                    f"Scene {scene_id} foreground_image requires layered_parallax"
                )
            if (
                Path(foreground["path"]).suffix.lower() != ".png"
                or not foreground["has_alpha"]
            ):
                raise ValueError(
                    f"Scene {scene_id} foreground_image must be a transparent PNG"
                )
            if (foreground["width"], foreground["height"]) != (
                image["width"],
                image["height"],
            ):
                raise ValueError(
                    f"Scene {scene_id} foreground and background dimensions must match"
                )
        elif motion == "layered_parallax":
            raise ValueError(
                f"Scene {scene_id} layered_parallax requires foreground_image"
            )

        canonical_scene: dict[str, Any] = {
            "id": scene_id,
            "image": image["path"],
            "narration": _nonempty_text(
                value["narration"],
                field=f"Scene {scene_id} narration",
                maximum=MAX_NARRATION_CHARACTERS,
            ),
            "motion": motion,
            "source_basis": _validate_source_basis(
                value["source_basis"],
                scene_id=scene_id,
            ),
        }
        if foreground is not None:
            canonical_scene["foreground_image"] = foreground["path"]
        canonical_scenes.append(canonical_scene)
        inventory.append(
            {
                "scene_id": scene_id,
                "role": "background" if foreground is not None else "scene",
                **image,
            }
        )
        if foreground is not None:
            inventory.append(
                {
                    "scene_id": scene_id,
                    "role": "foreground",
                    **foreground,
                }
            )
    return (
        {
            "schema_version": 1,
            "title": title,
            "language": "en",
            "scenes": canonical_scenes,
        },
        inventory,
    )


def _narration_markdown(plan: Mapping[str, Any]) -> str:
    """Return the clean user-facing narration script."""

    lines = [f"# {plan['title']}", "", "## Narration script", ""]
    for index, scene in enumerate(plan["scenes"], start=1):
        lines.extend(
            [
                f"### Scene {index}",
                "",
                scene["narration"],
                "",
            ]
        )
    return "\n".join(lines)


def _review_markdown(plan: Mapping[str, Any]) -> str:
    """Return a bounded narration and source-basis review packet."""

    lines = [
        f"# Research video review — {plan['title']}",
        "",
        "Review every narration scene against its image and source basis before approval.",
        "Only narration text is sent to OpenAI speech during rendering.",
        "",
    ]
    for index, scene in enumerate(plan["scenes"], start=1):
        lines.extend(
            [
                f"## Scene {index} · {scene['id']}",
                "",
                f"- Image: `{Path(scene['image']).name}`",
                f"- Motion: `{scene['motion']}`",
                f"- Narration: {scene['narration']}",
                "- Source basis:",
            ]
        )
        for basis in scene["source_basis"]:
            lines.append(f"  - {basis['reference']}: {basis['supports']}")
        lines.append("")
    return "\n".join(lines)


def prepare_run(scene_plan_path: Path, output_dir: Path) -> dict[str, Any]:
    """Validate and fingerprint a scene plan without external calls or rendering."""

    output_root = _ensure_output_boundary(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    if (output_root / "narration_approval.json").exists():
        raise ValueError("Use a fresh output directory for a changed approved plan")
    raw = _read_json(scene_plan_path.expanduser().resolve())
    plan, inventory = _canonicalize_plan(raw)
    plan_hash = _json_sha256(plan)
    _write_json(output_root / "scene_plan.json", plan)
    (output_root / "narration_script.md").write_text(
        _narration_markdown(plan),
        encoding="utf-8",
    )
    (output_root / "review_packet.md").write_text(
        _review_markdown(plan),
        encoding="utf-8",
    )
    intake = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "status": "ready_for_review",
        "created_at": _utc_now(),
        "title": plan["title"],
        "language": "en",
        "scene_count": len(plan["scenes"]),
        "scene_plan_sha256": plan_hash,
        "visual_inventory": inventory,
        "voice": {
            "provider": "OpenAI",
            "model": OPENAI_TTS_MODEL,
            "name": OPENAI_TTS_VOICE,
        },
        "data_posture": {
            "local_files_read": [item["path"] for item in inventory],
            "external_boundary": "OpenAI speech endpoint after exact-plan approval",
            "external_content": "Approved narration text only",
            "images_uploaded": False,
            "source_basis_uploaded": False,
        },
        "execution_trace": [
            {
                "step_id": "prepare-scene-plan",
                "kind": "deterministic_prepare",
                "status": "completed",
                "execution_location": "local_codex_workspace",
                "inputs": [str(scene_plan_path.expanduser().resolve())],
                "outputs": [
                    str(output_root / "scene_plan.json"),
                    str(output_root / "narration_script.md"),
                    str(output_root / "review_packet.md"),
                    str(output_root / "run_intake.json"),
                ],
            }
        ],
    }
    _write_json(output_root / "run_intake.json", intake)
    LOGGER.info("Research video prepared for review: %s", output_root)
    return intake


def _verify_visual_inventory(run_dir: Path, intake: Mapping[str, Any]) -> None:
    """Fail when an approved visual changed or disappeared."""

    for item in intake["visual_inventory"]:
        path = Path(item["path"])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Visual is unavailable or no longer ordinary: {path}")
        if _sha256(path) != item["sha256"]:
            raise ValueError(f"Visual changed after preparation: {path.name}")
    plan = _read_json(run_dir / "scene_plan.json")
    if _json_sha256(plan) != intake["scene_plan_sha256"]:
        raise ValueError("scene_plan.json changed after preparation")


def approve_run(run_dir: Path, approved_by: str = "requesting_user") -> dict[str, Any]:
    """Bind approval to the exact plan, narration script, and review packet."""

    root = run_dir.expanduser().resolve()
    intake = _read_json(root / "run_intake.json")
    _verify_visual_inventory(root, intake)
    narration_path = root / "narration_script.md"
    review_path = root / "review_packet.md"
    approval = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "approved_at": _utc_now(),
        "approved_by": _nonempty_text(
            approved_by,
            field="approved_by",
            maximum=120,
        ),
        "scope": "exact narration, scene order, motion, source basis, and visual bytes",
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "narration_script_sha256": _sha256(narration_path),
        "review_packet_sha256": _sha256(review_path),
        "external_tts_approved": True,
        "external_content": "approved narration text only",
    }
    _write_json(root / "narration_approval.json", approval)
    intake["status"] = "approved_for_render"
    intake["approved_at"] = approval["approved_at"]
    _write_json(root / "run_intake.json", intake)
    LOGGER.info("Narration and scene plan approved for rendering: %s", root)
    return approval


def _verify_approval(run_dir: Path, intake: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current approval or fail closed on any approved-byte drift."""

    approval = _read_json(run_dir / "narration_approval.json")
    expected = {
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "narration_script_sha256": _sha256(run_dir / "narration_script.md"),
        "review_packet_sha256": _sha256(run_dir / "review_packet.md"),
    }
    for field, value in expected.items():
        if approval.get(field) != value:
            raise ValueError(f"Approval is stale: {field} no longer matches")
    if approval.get("external_tts_approved") is not True:
        raise ValueError("OpenAI speech transmission has not been approved")
    return approval


def _speech_payload(text: str) -> dict[str, str]:
    """Return the fixed English narration request body."""

    return {
        "model": OPENAI_TTS_MODEL,
        "voice": OPENAI_TTS_VOICE,
        "input": text,
        "instructions": TTS_INSTRUCTIONS,
        "response_format": "wav",
    }


def _synthesize_scene(api_key: str, text: str, output_path: Path) -> None:
    """Synthesize one approved scene narration without logging its content."""

    if len(api_key.strip()) < 20:
        raise RuntimeError("OPENAI_API_KEY is missing or invalid")
    request = urllib.request.Request(
        OPENAI_SPEECH_ENDPOINT,
        data=json.dumps(_speech_payload(text)).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(1, 5):
        retry_error: BaseException
        try:
            with urllib.request.urlopen(request, timeout=240) as response:  # nosec B310
                output_path.write_bytes(response.read())
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise RuntimeError(
                    f"Narration request was rejected with HTTP {exc.code}"
                ) from exc
            retry_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            retry_error = exc
        if attempt == 4:
            raise RuntimeError(
                "Narration request failed after four attempts"
            ) from retry_error
        time.sleep(min(2 ** (attempt - 1), 8))


def _wav_duration(path: Path) -> float:
    """Return a finite positive PCM WAV duration."""

    try:
        with wave.open(str(path), "rb") as source:
            duration = source.getnframes() / float(source.getframerate())
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError(
            f"OpenAI speech did not return a readable WAV: {path}"
        ) from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"Invalid WAV duration: {duration}")
    return duration


def _resolve_ffmpeg() -> str:
    """Use system FFmpeg or the dependency declared by Clara."""

    system = shutil.which("ffmpeg")
    if system:
        return system
    from imageio_ffmpeg import get_ffmpeg_exe

    bundled = str(get_ffmpeg_exe()).strip()
    if not bundled:
        raise RuntimeError("FFmpeg is unavailable")
    return bundled


def _run_media(
    command: Sequence[str],
    *,
    capture_output: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one fixed local media command without a shell."""

    return subprocess.run(  # nosec B603
        list(command),
        check=check,
        capture_output=capture_output,
        text=True,
    )


def _fit_canvas(source: Path, output: Path, *, transparent: bool) -> None:
    """Fit an image on a safe 16:9 canvas without cropping source content."""

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        margin = 0.90
        maximum = (round(FRAME_WIDTH * margin), round(FRAME_HEIGHT * margin))
        image.thumbnail(maximum, Image.Resampling.LANCZOS)
        background = (0, 0, 0, 0) if transparent else (250, 250, 248, 255)
        canvas = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), background)
        position = (
            (FRAME_WIDTH - image.width) // 2,
            (FRAME_HEIGHT - image.height) // 2,
        )
        canvas.alpha_composite(image, dest=position)
        canvas.save(output, format="PNG")


def _motion_filter(motion: str, frame_count: int) -> str:
    """Return a bounded FFmpeg filter for one mechanically selected motion."""

    frames = max(frame_count, 1)
    denominator = max(frames - 1, 1)
    if motion == "static":
        return f"scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=lanczos,fps={FRAME_RATE},format=yuv420p"
    if motion == "zoom_in":
        zoom = "min(zoom+0.00035,1.035)"
        x = "iw/2-(iw/zoom/2)"
    elif motion == "zoom_out":
        zoom = "if(eq(on,0),1.035,max(1.0,zoom-0.00035))"
        x = "iw/2-(iw/zoom/2)"
    elif motion == "pan_left":
        zoom = "1.035"
        x = f"(iw-iw/zoom)*(1-on/{denominator})"
    else:
        zoom = "1.035"
        x = f"(iw-iw/zoom)*(on/{denominator})"
    return (
        f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={FRAME_WIDTH}x{FRAME_HEIGHT}:fps={FRAME_RATE},"
        "format=yuv420p"
    )


def _render_scene_clip(
    *,
    ffmpeg: str,
    background: Path,
    foreground: Path | None,
    motion: str,
    duration: float,
    output: Path,
) -> None:
    """Render one silent H.264 scene with restrained motion."""

    frames = max(round(duration * FRAME_RATE), 1)
    command = [ffmpeg, "-y", "-v", "error", "-loop", "1", "-i", str(background)]
    if foreground is None:
        command.extend(["-vf", _motion_filter(motion, frames)])
    else:
        command.extend(["-loop", "1", "-i", str(foreground)])
        background_filter = _motion_filter("zoom_in", frames).replace(
            ",format=yuv420p", ""
        )
        overlay = (
            f"[0:v]{background_filter}[bg];"
            f"[1:v]scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=lanczos,format=rgba[fg];"
            f"[bg][fg]overlay=x='4*sin(2*PI*t/{max(duration, 0.1):.6f})':"
            f"y='3*cos(2*PI*t/{max(duration, 0.1):.6f})':shortest=1,"
            "format=yuv420p[v]"
        )
        command.extend(["-filter_complex", overlay, "-map", "[v]"])
    command.extend(
        [
            "-t",
            f"{duration:.6f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    _run_media(command)


def _visual_clip_durations(speech_durations: Sequence[float]) -> list[float]:
    """Allocate visual time so every cross-fade occurs inside narration silence."""

    result: list[float] = []
    last = len(speech_durations) - 1
    for index, speech in enumerate(speech_durations):
        before = LEAD_SECONDS if index == 0 else INTER_SCENE_PAUSE_SECONDS / 2
        after = TAIL_SECONDS if index == last else INTER_SCENE_PAUSE_SECONDS / 2
        transition_allowance = 0.0
        if index > 0:
            transition_allowance += TRANSITION_SECONDS / 2
        if index < last:
            transition_allowance += TRANSITION_SECONDS / 2
        result.append(before + speech + after + transition_allowance)
    return result


def _join_visuals(
    ffmpeg: str,
    clips: Sequence[Path],
    durations: Sequence[float],
    output: Path,
) -> None:
    """Cross-fade scene clips at measured silent boundaries."""

    command: list[str] = [ffmpeg, "-y", "-v", "error"]
    for clip in clips:
        command.extend(["-i", str(clip)])
    filters: list[str] = []
    previous = "[0:v]"
    for index in range(1, len(clips)):
        label = f"v{index}"
        offset = sum(durations[:index]) - TRANSITION_SECONDS * index
        filters.append(
            f"{previous}[{index}:v]xfade=transition=fade:"
            f"duration={TRANSITION_SECONDS:.6f}:offset={offset:.6f}[{label}]"
        )
        previous = f"[{label}]"
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            previous,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    _run_media(command)


def _join_audio(
    ffmpeg: str,
    scenes: Sequence[Path],
    output: Path,
    work_dir: Path,
) -> float:
    """Join scene speech with bounded silence and normalize the final voice track."""

    silence_specs = [LEAD_SECONDS, INTER_SCENE_PAUSE_SECONDS, TAIL_SECONDS]
    silence_paths: list[Path] = []
    for index, seconds in enumerate(silence_specs):
        path = work_dir / f"silence-{index}.wav"
        _run_media(
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
                f"{seconds:.6f}",
                "-c:a",
                "pcm_s16le",
                str(path),
            ]
        )
        silence_paths.append(path)
    inputs: list[Path] = [silence_paths[0]]
    for index, scene in enumerate(scenes):
        inputs.append(scene)
        if index < len(scenes) - 1:
            inputs.append(silence_paths[1])
    inputs.append(silence_paths[2])
    command: list[str] = [ffmpeg, "-y", "-v", "error"]
    for path in inputs:
        command.extend(["-i", str(path)])
    filters: list[str] = []
    labels: list[str] = []
    for index in range(len(inputs)):
        label = f"a{index}"
        labels.append(f"[{label}]")
        filters.append(
            f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:"
            f"channel_layouts=mono[{label}]"
        )
    filters.append(
        f"{''.join(labels)}concat=n={len(inputs)}:v=0:a=1,"
        f"loudnorm=I={TARGET_LOUDNESS_LUFS}:TP=-1.5:LRA=11[aout]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(output),
        ]
    )
    _run_media(command)
    return (
        LEAD_SECONDS
        + TAIL_SECONDS
        + sum(_wav_duration(path) for path in scenes)
        + INTER_SCENE_PAUSE_SECONDS * (len(scenes) - 1)
    )


def _mux(ffmpeg: str, visual: Path, audio: Path, output: Path) -> None:
    """Combine the validated local video and narration tracks."""

    _run_media(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(visual),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def _vtt_timestamp(seconds: float) -> str:
    """Format one WebVTT timestamp."""

    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def _write_captions(
    output: Path,
    scenes: Sequence[Mapping[str, Any]],
    speech_durations: Sequence[float],
) -> None:
    """Write one source-aligned cue per narration scene."""

    lines = ["WEBVTT", ""]
    start = LEAD_SECONDS
    for index, (scene, duration) in enumerate(
        zip(scenes, speech_durations, strict=True),
        start=1,
    ):
        end = start + duration
        caption = "\n".join(textwrap.wrap(scene["narration"], width=72))
        lines.extend(
            [
                str(index),
                f"{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}",
                caption,
                "",
            ]
        )
        start = end + INTER_SCENE_PAUSE_SECONDS
    output.write_text("\n".join(lines), encoding="utf-8")


def _validate_media(ffmpeg: str, video: Path) -> dict[str, Any]:
    """Decode the complete MP4 and verify the required stream contract."""

    _run_media([ffmpeg, "-v", "error", "-i", str(video), "-f", "null", "-"])
    probe = _run_media(
        [ffmpeg, "-hide_banner", "-i", str(video), "-f", "null", "-"],
        capture_output=True,
        check=False,
    )
    detail = probe.stderr
    required = (
        ("Video: h264", "H.264 video stream"),
        ("Audio: aac", "AAC audio stream"),
        (f"{FRAME_WIDTH}x{FRAME_HEIGHT}", "16:9 frame dimensions"),
    )
    missing = [label for marker, label in required if marker not in detail]
    if missing:
        raise ValueError(f"Rendered MP4 is missing: {', '.join(missing)}")
    return {
        "container": "video/mp4",
        "video_codec": "h264",
        "audio_codec": "aac",
        "width": FRAME_WIDTH,
        "height": FRAME_HEIGHT,
        "frame_rate": FRAME_RATE,
        "decoded_without_error": True,
    }


def _artifact(
    path: Path, kind: str, status: str = "ready_for_review"
) -> dict[str, Any]:
    """Return a stable artifact manifest record."""

    return {
        "path": path.name,
        "kind": kind,
        "status": status,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _verify_existing_render(run_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Return an idempotent render only when every declared artifact still matches."""

    manifest = _read_json(run_dir / "final_artifacts.json")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Existing final artifact manifest is incomplete")
    for item in outputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("Existing final artifact entry is malformed")
        path = run_dir / item["path"]
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ValueError(
                f"Existing rendered artifact is missing or changed: {path.name}"
            )
    return report


def render_run(run_dir: Path, *, api_key: str | None = None) -> dict[str, Any]:
    """Synthesize, render, validate, and declare one approved research video."""

    root = run_dir.expanduser().resolve()
    intake = _read_json(root / "run_intake.json")
    _verify_visual_inventory(root, intake)
    approval = _verify_approval(root, intake)
    plan = _read_json(root / "scene_plan.json")
    existing_report = root / "render_report.json"
    if existing_report.is_file():
        report = _read_json(existing_report)
        if report.get("scene_plan_sha256") == intake["scene_plan_sha256"]:
            return _verify_existing_render(root, report)
        raise ValueError("Use a fresh output directory for a different rendered plan")
    selected_key = (
        api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
    )
    ffmpeg = _resolve_ffmpeg()

    final_video = root / "research_video.mp4"
    final_poster = root / "poster.jpg"
    final_captions = root / "captions.vtt"
    with tempfile.TemporaryDirectory(prefix="clara-research-video-") as temp_dir:
        work = Path(temp_dir)
        narration_paths: list[Path] = []
        speech_durations: list[float] = []
        canvas_paths: list[Path] = []
        foreground_paths: list[Path | None] = []
        for index, scene in enumerate(plan["scenes"], start=1):
            narration_path = work / f"narration-{index:02d}.wav"
            _synthesize_scene(selected_key, scene["narration"], narration_path)
            narration_paths.append(narration_path)
            speech_durations.append(_wav_duration(narration_path))

            canvas_path = work / f"canvas-{index:02d}.png"
            _fit_canvas(Path(scene["image"]), canvas_path, transparent=False)
            canvas_paths.append(canvas_path)
            foreground_path: Path | None = None
            if "foreground_image" in scene:
                foreground_path = work / f"foreground-{index:02d}.png"
                _fit_canvas(
                    Path(scene["foreground_image"]),
                    foreground_path,
                    transparent=True,
                )
            foreground_paths.append(foreground_path)

        with Image.open(canvas_paths[0]) as first_canvas:
            poster = first_canvas.convert("RGB")
        if foreground_paths[0] is not None:
            with Image.open(foreground_paths[0]) as foreground:
                poster.paste(foreground, (0, 0), foreground)
        temporary_poster = work / "poster.jpg"
        poster.save(temporary_poster, format="JPEG", quality=92)
        poster.close()

        clip_durations = _visual_clip_durations(speech_durations)
        clips: list[Path] = []
        for index, (scene, background, foreground, duration) in enumerate(
            zip(
                plan["scenes"],
                canvas_paths,
                foreground_paths,
                clip_durations,
                strict=True,
            ),
            start=1,
        ):
            clip = work / f"scene-{index:02d}.mp4"
            _render_scene_clip(
                ffmpeg=ffmpeg,
                background=background,
                foreground=foreground,
                motion=scene["motion"],
                duration=duration,
                output=clip,
            )
            clips.append(clip)
        visual = work / "visual.mp4"
        audio = work / "voice.m4a"
        _join_visuals(ffmpeg, clips, clip_durations, visual)
        target_duration = _join_audio(ffmpeg, narration_paths, audio, work)
        rendered = work / "research_video.mp4"
        _mux(ffmpeg, visual, audio, rendered)
        media = _validate_media(ffmpeg, rendered)
        shutil.copy2(rendered, final_video)
        shutil.copy2(temporary_poster, final_poster)

    _write_captions(final_captions, plan["scenes"], speech_durations)
    report = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "status": "ready_for_review",
        "rendered_at": _utc_now(),
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "approval_sha256": _json_sha256(approval),
        "scene_count": len(plan["scenes"]),
        "target_duration_seconds": round(target_duration, 3),
        "scene_speech_durations_seconds": [
            round(value, 3) for value in speech_durations
        ],
        "scene_visual_durations_seconds": [round(value, 3) for value in clip_durations],
        "transition": {
            "type": "cross_fade",
            "duration_seconds": TRANSITION_SECONDS,
            "placement": "inside inter-scene narration silence",
        },
        "voice": {
            "provider": "OpenAI",
            "model": OPENAI_TTS_MODEL,
            "name": OPENAI_TTS_VOICE,
        },
        "media": media,
        "requires_semantic_review": True,
        "flat_image_parallax_claimed": False,
    }
    _write_json(root / "render_report.json", report)
    final_artifacts = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "status": "ready_for_review",
        "review_status": "pending_semantic_and_visual_review",
        "outputs": [
            _artifact(final_video, "video/mp4"),
            _artifact(final_poster, "image/jpeg"),
            _artifact(final_captions, "text/vtt"),
            _artifact(root / "narration_script.md", "text/markdown"),
            _artifact(root / "render_report.json", "application/json"),
        ],
        "caveats": [
            "Mechanical validation does not prove scientific or source fidelity.",
            "Flat images use restrained pan or zoom, not true parallax.",
        ],
        "next_actions": [
            "Watch the complete video and review every scene against its source basis.",
            "Revise, reapprove, and rerender if narration, legibility, pacing, or motion is materially wrong.",
        ],
    }
    _write_json(root / "final_artifacts.json", final_artifacts)
    intake["status"] = "ready_for_review"
    intake["execution_trace"].append(
        {
            "step_id": "render-research-video",
            "kind": "external_tts_and_local_media_render",
            "status": "completed",
            "execution_location": "openai_speech_and_local_codex_workspace",
            "inputs": [
                str(root / "scene_plan.json"),
                str(root / "narration_approval.json"),
            ],
            "outputs": [
                str(final_video),
                str(final_poster),
                str(final_captions),
                str(root / "render_report.json"),
                str(root / "final_artifacts.json"),
            ],
        }
    )
    _write_json(root / "run_intake.json", intake)
    LOGGER.info("Research video rendered and ready for review: %s", final_video)
    return report


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Validate and prepare a scene plan")
    prepare.add_argument("--scene-plan", required=True, type=Path)
    prepare.add_argument("--output-dir", required=True, type=Path)
    approve = subparsers.add_parser("approve", help="Bind approval to prepared bytes")
    approve.add_argument("--run-dir", required=True, type=Path)
    approve.add_argument("--approved-by", default="requesting_user")
    render = subparsers.add_parser("render", help="Render an approved scene plan")
    render.add_argument("--run-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the research-video command line interface."""

    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "prepare":
        prepare_run(args.scene_plan, args.output_dir)
    elif args.command == "approve":
        approve_run(args.run_dir, args.approved_by)
    else:
        render_run(args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
