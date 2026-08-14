#!/usr/bin/env python3
"""Prepare, approve, render, and validate a source-grounded research video."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import stat
import subprocess  # nosec B404
import tempfile
import textwrap
import wave
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "approve_run",
    "attach_hosted_voice",
    "main",
    "prepare_run",
    "render_run",
]

LOGGER = logging.getLogger(__name__)

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
HOSTED_VOICE_SOURCE = "mparanza_hosted_openai_voice"
HOSTED_VOICE_PROVIDER = "OpenAI"
HOSTED_VOICE_MODEL = "gpt-4o-mini-tts"
HOSTED_VOICE_NAMES = {
    "de": "cedar",
    "en": "cedar",
    "es": "cedar",
    "fr": "cedar",
    "it": "marin",
}
SUPPORTED_LANGUAGES = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
}
VOICE_DISCLOSURES = {
    "de": "KI-generierte Stimme",
    "en": "AI-generated voice",
    "es": "Voz generada por IA",
    "fr": "Voix générée par IA",
    "it": "Voce generata dall'IA",
}

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
MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_VOICE_BUNDLE_BYTES = 500 * 1024 * 1024
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
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
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
    language = raw["language"]
    if language not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"scene_plan.language must be one of: {supported}")
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
            "language": language,
            "scenes": canonical_scenes,
        },
        inventory,
    )


def _narration_markdown(plan: Mapping[str, Any]) -> str:
    """Return the clean user-facing narration script."""

    language = plan["language"]
    lines = [
        f"# {plan['title']}",
        "",
        f"- Narration language: {SUPPORTED_LANGUAGES[language]} (`{language}`)",
        f"- On-screen voice disclosure: {VOICE_DISCLOSURES[language]}",
        "",
        "## Narration script",
        "",
    ]
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


def _hosted_voice_request(
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the minimal request accepted by the authenticated Mparanza service."""

    return {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "language": plan["language"],
        "scene_plan_sha256": _json_sha256(plan),
        "approval": {
            "approval_sha256": _json_sha256(approval),
            "confirmed_by_user": True,
        },
        "scenes": [
            {"id": scene["id"], "narration": scene["narration"]}
            for scene in plan["scenes"]
        ],
    }


def _review_markdown(plan: Mapping[str, Any]) -> str:
    """Return a bounded narration and source-basis review packet."""

    lines = [
        f"# Research video review — {plan['title']}",
        "",
        "Review every narration scene against its image and source basis before approval.",
        (
            "After approval, upload the generated Mparanza voice request to the "
            "authenticated Research Video page. No user API key is required."
        ),
        (
            "Only the approved narration, language, scene identifiers, and binding "
            "hashes leave the local workspace. Images and source-basis notes stay local."
        ),
        (
            "Mparanza sends that narration to OpenAI, returns an in-memory ZIP, and "
            "does not write the request or generated audio to application storage."
        ),
        (
            "The completed video shows this disclosure on every scene: "
            f"{VOICE_DISCLOSURES[plan['language']]}"
        ),
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
        "language": plan["language"],
        "scene_count": len(plan["scenes"]),
        "scene_plan_sha256": plan_hash,
        "visual_inventory": inventory,
        "voice": {
            "provider": "Mparanza",
            "upstream_provider": HOSTED_VOICE_PROVIDER,
            "source": HOSTED_VOICE_SOURCE,
            "model": HOSTED_VOICE_MODEL,
            "name": HOSTED_VOICE_NAMES[plan["language"]],
            "disclosure": VOICE_DISCLOSURES[plan["language"]],
            "disclosure_placement": "visible footer on every scene",
        },
        "data_posture": {
            "local_files_read": [item["path"] for item in inventory],
            "mparanza_hosted_processing": (
                "After approval, exact narration and binding metadata are sent to "
                "the authenticated Mparanza service and OpenAI"
            ),
            "boundary_beyond_local_workspace": "Mparanza and OpenAI",
            "user_api_key_required": False,
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


def approve_run(
    run_dir: Path,
    approved_by: str = "requesting_user",
    *,
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    """Bind approval only after explicit user confirmation of the exact review."""

    # Approval is an audit claim, so a fixed flag is justified here: the renderer
    # must not infer user confirmation from prose or from merely running a command.
    if not confirmed_by_user:
        raise ValueError("Approval requires explicit --confirmed-by-user evidence")

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
        "scope": (
            "exact narration, hosted voice generation, scene order, motion, "
            "source basis, and visual bytes"
        ),
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "narration_script_sha256": _sha256(narration_path),
        "review_packet_sha256": _sha256(review_path),
        "voice_disclosure_sha256": _json_sha256(intake["voice"]["disclosure"]),
        "confirmed_by_user": True,
        "hosted_voice_generation_approved": True,
    }
    _write_json(root / "narration_approval.json", approval)
    plan = _read_json(root / "scene_plan.json")
    _write_json(
        root / "mparanza_voice_request.json",
        _hosted_voice_request(plan, approval),
    )
    intake["status"] = "approved_for_hosted_voice"
    intake["approved_at"] = approval["approved_at"]
    _write_json(root / "run_intake.json", intake)
    LOGGER.info("Narration and scene plan approved for rendering: %s", root)
    return approval


def _verify_approval(run_dir: Path, intake: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current approval or fail closed on any approved-byte drift."""

    approval = _read_json(run_dir / "narration_approval.json")
    if approval.get("confirmed_by_user") is not True:
        raise ValueError("Approval lacks explicit user-confirmation evidence")
    expected = {
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "narration_script_sha256": _sha256(run_dir / "narration_script.md"),
        "review_packet_sha256": _sha256(run_dir / "review_packet.md"),
        "voice_disclosure_sha256": _json_sha256(intake["voice"]["disclosure"]),
    }
    for field, value in expected.items():
        if approval.get(field) != value:
            raise ValueError(f"Approval is stale: {field} no longer matches")
    if approval.get("hosted_voice_generation_approved") is not True:
        raise ValueError("Hosted voice generation has not been approved")
    plan = _read_json(run_dir / "scene_plan.json")
    request = _read_json(run_dir / "mparanza_voice_request.json")
    if request != _hosted_voice_request(plan, approval):
        raise ValueError("Mparanza voice request no longer matches the approval")
    return approval


def _wav_duration(path: Path) -> float:
    """Return a finite positive PCM WAV duration."""

    try:
        with wave.open(str(path), "rb") as source:
            duration = source.getnframes() / float(source.getframerate())
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError(
            f"Hosted voice artifact is not a readable WAV: {path}"
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


def _safe_voice_bundle(bundle_path: Path) -> tuple[zipfile.ZipFile, dict[str, Any]]:
    """Open one bounded ordinary ZIP and return its validated JSON manifest."""

    candidate = bundle_path.expanduser()
    if candidate.is_symlink():
        raise ValueError("Hosted voice bundle must not be a symbolic link")
    path = candidate.resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_VOICE_BUNDLE_BYTES:
        raise ValueError("Hosted voice bundle has an unsupported size")
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("Hosted voice bundle is not a readable ZIP") from exc
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        archive.close()
        raise ValueError("Hosted voice bundle contains duplicate entries")
    if len(infos) > MAX_SCENES + 1:
        archive.close()
        raise ValueError("Hosted voice bundle contains unexpected entries")
    if sum(info.file_size for info in infos) > MAX_VOICE_BUNDLE_BYTES:
        archive.close()
        raise ValueError("Hosted voice bundle expands beyond the size limit")
    for info in infos:
        path_parts = Path(info.filename).parts
        mode = info.external_attr >> 16
        if (
            info.is_dir()
            or info.flag_bits & 0x1
            or info.filename.startswith(("/", "\\"))
            or "\\" in info.filename
            or ".." in path_parts
            or stat.S_ISLNK(mode)
        ):
            archive.close()
            raise ValueError("Hosted voice bundle contains an unsafe entry")
    if "manifest.json" not in names:
        archive.close()
        raise ValueError("Hosted voice bundle has no manifest.json")
    manifest_info = archive.getinfo("manifest.json")
    if not 0 < manifest_info.file_size <= 1024 * 1024:
        archive.close()
        raise ValueError("Hosted voice manifest has an unsupported size")
    try:
        manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        archive.close()
        raise ValueError("Hosted voice manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        archive.close()
        raise ValueError("Hosted voice manifest must be a JSON object")
    return archive, manifest


def attach_hosted_voice(run_dir: Path, voice_bundle_path: Path) -> dict[str, Any]:
    """Validate and attach one authenticated Mparanza narration bundle."""

    root = _ensure_output_boundary(run_dir)
    intake = _read_json(root / "run_intake.json")
    _verify_visual_inventory(root, intake)
    approval = _verify_approval(root, intake)
    plan = _read_json(root / "scene_plan.json")
    request_path = root / "mparanza_voice_request.json"
    request_payload = _read_json(request_path)
    bundle_candidate = voice_bundle_path.expanduser()
    manifest_path = root / "hosted_voice_manifest.json"
    voice_dir = root / "hosted_voice"
    archive, source_manifest = _safe_voice_bundle(bundle_candidate)
    bundle_path = bundle_candidate.resolve()
    input_hash = _sha256(bundle_path)
    if manifest_path.exists() or voice_dir.exists():
        archive.close()
        if manifest_path.is_file():
            existing = _read_json(manifest_path)
            if existing.get("input_bundle_sha256") == input_hash:
                return existing
        raise ValueError("Use a fresh run for different hosted voice artifacts")

    expected_manifest_fields = {
        "schema_version",
        "workflow",
        "source",
        "provider",
        "model",
        "voice",
        "language",
        "generated_at",
        "request_sha256",
        "scene_plan_sha256",
        "approval_sha256",
        "mparanza_application_retention",
        "scenes",
    }
    try:
        if set(source_manifest) != expected_manifest_fields:
            raise ValueError("Hosted voice manifest has unexpected or missing fields")
        expected = {
            "schema_version": 1,
            "workflow": "clara:research-video",
            "source": HOSTED_VOICE_SOURCE,
            "provider": HOSTED_VOICE_PROVIDER,
            "model": HOSTED_VOICE_MODEL,
            "voice": HOSTED_VOICE_NAMES[plan["language"]],
            "language": plan["language"],
            "request_sha256": _json_sha256(request_payload),
            "scene_plan_sha256": intake["scene_plan_sha256"],
            "approval_sha256": _json_sha256(approval),
            "mparanza_application_retention": "in_memory_response_only",
        }
        for field, value in expected.items():
            if source_manifest.get(field) != value:
                raise ValueError(f"Hosted voice manifest does not match: {field}")
        _nonempty_text(
            source_manifest.get("generated_at"),
            field="generated_at",
            maximum=80,
        )
        source_scenes = source_manifest.get("scenes")
        if not isinstance(source_scenes, list) or len(source_scenes) != len(
            plan["scenes"]
        ):
            raise ValueError("Hosted voice manifest has incomplete scene audio")
        expected_entries = {"manifest.json"}
        ffmpeg = _resolve_ffmpeg()
        staged_records: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="clara-hosted-voice-") as temp_dir:
            staged_dir = Path(temp_dir) / "hosted_voice"
            staged_dir.mkdir()
            for index, (scene, item) in enumerate(
                zip(plan["scenes"], source_scenes, strict=True),
                start=1,
            ):
                required_scene_fields = {
                    "id",
                    "audio",
                    "sha256",
                    "size_bytes",
                    "frame_count",
                    "frame_rate",
                    "channels",
                    "sample_width_bytes",
                    "duration_seconds",
                }
                if not isinstance(item, dict) or set(item) != required_scene_fields:
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} has invalid fields"
                    )
                expected_audio = f"audio/{index:02d}-{scene['id']}.wav"
                if item.get("id") != scene["id"] or item.get("audio") != expected_audio:
                    raise ValueError(
                        "Hosted voice scenes do not match the approved order"
                    )
                expected_entries.add(expected_audio)
                try:
                    info = archive.getinfo(expected_audio)
                except KeyError as exc:
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} has no declared WAV"
                    ) from exc
                if not 0 < info.file_size <= MAX_AUDIO_BYTES:
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} has an invalid size"
                    )
                audio = archive.read(info)
                if len(audio) != item.get("size_bytes") or hashlib.sha256(
                    audio
                ).hexdigest() != item.get("sha256"):
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} failed byte validation"
                    )
                source_path = staged_dir / f"source-{index:02d}.wav"
                source_path.write_bytes(audio)
                try:
                    with wave.open(str(source_path), "rb") as source:
                        media = {
                            "frame_count": source.getnframes(),
                            "frame_rate": source.getframerate(),
                            "channels": source.getnchannels(),
                            "sample_width_bytes": source.getsampwidth(),
                        }
                except (OSError, EOFError, wave.Error) as exc:
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} is not WAV"
                    ) from exc
                duration = media["frame_count"] / float(media["frame_rate"])
                for field, value in media.items():
                    if item.get(field) != value:
                        raise ValueError(
                            f"Hosted voice scene {scene['id']} has stale {field}"
                        )
                if not isinstance(
                    item.get("duration_seconds"), (int, float)
                ) or not math.isclose(
                    duration,
                    float(item["duration_seconds"]),
                    abs_tol=0.001,
                ):
                    raise ValueError(
                        f"Hosted voice scene {scene['id']} has a stale duration"
                    )
                filename = f"{index:02d}-{scene['id']}.wav"
                staged_path = staged_dir / filename
                _run_media(
                    [
                        ffmpeg,
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        str(source_path),
                        "-vn",
                        "-ar",
                        "48000",
                        "-ac",
                        "1",
                        "-c:a",
                        "pcm_s16le",
                        str(staged_path),
                    ]
                )
                source_path.unlink()
                staged_records.append(
                    {
                        "id": scene["id"],
                        "source_audio": expected_audio,
                        "source_sha256": item["sha256"],
                        "audio": f"hosted_voice/{filename}",
                        "sha256": _sha256(staged_path),
                        "duration_seconds": round(_wav_duration(staged_path), 6),
                    }
                )
            if set(archive.namelist()) != expected_entries:
                raise ValueError("Hosted voice bundle contains undeclared entries")
            shutil.copytree(staged_dir, voice_dir)
    finally:
        archive.close()

    manifest = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "source": HOSTED_VOICE_SOURCE,
        "provider": "Mparanza",
        "upstream_provider": source_manifest["provider"],
        "model": source_manifest["model"],
        "voice": source_manifest["voice"],
        "language": plan["language"],
        "attached_at": _utc_now(),
        "generated_at": source_manifest["generated_at"],
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "approval_sha256": _json_sha256(approval),
        "mparanza_voice_request_sha256": _sha256(request_path),
        "input_bundle_sha256": input_hash,
        "mparanza_application_retention": "in_memory_response_only",
        "scenes": staged_records,
    }
    _write_json(manifest_path, manifest)
    intake["status"] = "ready_to_render"
    intake["execution_trace"].append(
        {
            "step_id": "attach-hosted-voice",
            "kind": "authenticated_hosted_voice_attachment",
            "status": "completed",
            "execution_location": "mparanza_host_and_local_workspace",
            "inputs": [
                str(request_path),
                str(root / "narration_approval.json"),
                str(bundle_path),
            ],
            "outputs": [str(manifest_path), str(voice_dir)],
        }
    )
    _write_json(root / "run_intake.json", intake)
    LOGGER.info("Hosted voice artifacts attached: %s", manifest_path)
    return manifest


def _verify_hosted_voice(
    run_dir: Path,
    intake: Mapping[str, Any],
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> tuple[dict[str, Any], list[Path], list[float]]:
    """Verify the attached hosted voice manifest and staged audio bytes."""

    manifest_path = run_dir / "hosted_voice_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(
            "Hosted voice artifacts are missing; attach them before rendering"
        )
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("Hosted voice manifest schema_version is invalid")
    if manifest.get("workflow") != "clara:research-video":
        raise ValueError("Hosted voice manifest workflow is invalid")
    expected = {
        "source": HOSTED_VOICE_SOURCE,
        "provider": "Mparanza",
        "upstream_provider": HOSTED_VOICE_PROVIDER,
        "model": HOSTED_VOICE_MODEL,
        "voice": HOSTED_VOICE_NAMES[plan["language"]],
        "language": plan["language"],
        "scene_plan_sha256": intake["scene_plan_sha256"],
        "approval_sha256": _json_sha256(approval),
        "mparanza_voice_request_sha256": _sha256(
            run_dir / "mparanza_voice_request.json"
        ),
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f"Hosted voice manifest is stale: {field}")
    records = manifest.get("scenes")
    if not isinstance(records, list) or len(records) != len(plan["scenes"]):
        raise ValueError("Hosted voice manifest has incomplete scene audio")
    paths: list[Path] = []
    durations: list[float] = []
    for scene, record in zip(plan["scenes"], records, strict=True):
        if not isinstance(record, dict) or record.get("id") != scene["id"]:
            raise ValueError("Hosted voice scene order no longer matches the plan")
        relative_value = record.get("audio")
        if not isinstance(relative_value, str):
            raise ValueError(f"Hosted voice scene {scene['id']} has no audio path")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Hosted voice audio paths must stay inside the run")
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file() or path.is_symlink():
            raise ValueError(f"Hosted voice audio is unavailable: {scene['id']}")
        if _sha256(path) != record.get("sha256"):
            raise ValueError(
                f"Hosted voice audio changed after attachment: {scene['id']}"
            )
        duration = _wav_duration(path)
        recorded_duration = record.get("duration_seconds")
        if not isinstance(recorded_duration, (int, float)) or not math.isclose(
            duration,
            float(recorded_duration),
            abs_tol=0.001,
        ):
            raise ValueError(f"Hosted voice duration changed: {scene['id']}")
        paths.append(path)
        durations.append(duration)
    return manifest, paths, durations


def _fit_canvas(
    source: Path,
    output: Path,
    *,
    transparent: bool,
    voice_disclosure: str | None = None,
) -> None:
    """Fit an image on a safe 16:9 canvas without cropping source content."""

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        margin = 0.86 if voice_disclosure and not transparent else 0.90
        maximum = (round(FRAME_WIDTH * margin), round(FRAME_HEIGHT * margin))
        image.thumbnail(maximum, Image.Resampling.LANCZOS)
        background = (0, 0, 0, 0) if transparent else (250, 250, 248, 255)
        canvas = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), background)
        position = (
            (FRAME_WIDTH - image.width) // 2,
            (FRAME_HEIGHT - image.height) // 2,
        )
        canvas.alpha_composite(image, dest=position)
        if voice_disclosure and not transparent:
            draw = ImageDraw.Draw(canvas)
            font_size = max(8, round(FRAME_HEIGHT * 0.019))
            font = ImageFont.load_default(size=font_size)
            text_box = draw.textbbox((0, 0), voice_disclosure, font=font)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            padding_x = max(3, round(FRAME_WIDTH * 0.004))
            padding_y = max(1, round(FRAME_HEIGHT * 0.003))
            # The disclosure is part of the moving scene canvas. Keep it beyond
            # the maximum 3.5% pan/zoom crop so it stays wholly visible.
            right = FRAME_WIDTH - max(8, round(FRAME_WIDTH * 0.05))
            bottom = FRAME_HEIGHT - max(6, round(FRAME_HEIGHT * 0.05))
            left = right - text_width - 2 * padding_x
            top = bottom - text_height - 2 * padding_y
            draw.rounded_rectangle(
                (left, top, right, bottom),
                radius=max(2, padding_y * 2),
                fill=(250, 250, 248, 235),
                outline=(0, 32, 96, 120),
                width=1,
            )
            draw.text(
                (left + padding_x, top + padding_y - text_box[1]),
                voice_disclosure,
                font=font,
                fill=(0, 32, 96, 255),
            )
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
    path: Path,
    kind: str,
    *,
    root: Path,
    status: str = "ready_for_review",
) -> dict[str, Any]:
    """Return a stable artifact manifest record."""

    return {
        "path": str(path.relative_to(root)),
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


def render_run(run_dir: Path) -> dict[str, Any]:
    """Render, validate, and declare one hosted-voice research video."""

    root = run_dir.expanduser().resolve()
    intake = _read_json(root / "run_intake.json")
    _verify_visual_inventory(root, intake)
    approval = _verify_approval(root, intake)
    plan = _read_json(root / "scene_plan.json")
    voice_manifest, narration_paths, speech_durations = _verify_hosted_voice(
        root,
        intake,
        plan,
        approval,
    )
    existing_report = root / "render_report.json"
    if existing_report.is_file():
        report = _read_json(existing_report)
        if report.get("scene_plan_sha256") == intake["scene_plan_sha256"]:
            return _verify_existing_render(root, report)
        raise ValueError("Use a fresh output directory for a different rendered plan")
    ffmpeg = _resolve_ffmpeg()

    final_video = root / "research_video.mp4"
    final_poster = root / "poster.jpg"
    final_captions = root / "captions.vtt"
    with tempfile.TemporaryDirectory(prefix="clara-research-video-") as temp_dir:
        work = Path(temp_dir)
        canvas_paths: list[Path] = []
        foreground_paths: list[Path | None] = []
        for index, scene in enumerate(plan["scenes"], start=1):
            canvas_path = work / f"canvas-{index:02d}.png"
            _fit_canvas(
                Path(scene["image"]),
                canvas_path,
                transparent=False,
                voice_disclosure=intake["voice"]["disclosure"],
            )
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
        "hosted_voice_manifest_sha256": _sha256(root / "hosted_voice_manifest.json"),
        "scene_count": len(plan["scenes"]),
        "language": plan["language"],
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
            "provider": "Mparanza",
            "upstream_provider": voice_manifest["upstream_provider"],
            "source": HOSTED_VOICE_SOURCE,
            "model": voice_manifest["model"],
            "name": voice_manifest["voice"],
            "disclosure": intake["voice"]["disclosure"],
            "disclosure_placement": "visible footer on every scene",
        },
        "media": media,
        "requires_semantic_review": True,
        "requires_voice_content_review": True,
        "flat_image_parallax_claimed": False,
    }
    _write_json(root / "render_report.json", report)
    intake["status"] = "ready_for_review"
    intake["execution_trace"].append(
        {
            "step_id": "render-research-video",
            "kind": "hosted_voice_local_media_render",
            "status": "completed",
            "execution_location": "local_codex_workspace",
            "inputs": [
                str(root / "scene_plan.json"),
                str(root / "narration_approval.json"),
                str(root / "hosted_voice_manifest.json"),
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
    final_artifacts = {
        "schema_version": 1,
        "workflow": "clara:research-video",
        "status": "ready_for_review",
        "review_status": "pending_semantic_and_visual_review",
        "voice_disclosure": {
            "text": intake["voice"]["disclosure"],
            "placement": "visible footer on every scene",
        },
        "outputs": [
            _artifact(final_video, "video/mp4", root=root),
            _artifact(final_poster, "image/jpeg", root=root),
            _artifact(final_captions, "text/vtt", root=root),
            _artifact(root / "narration_script.md", "text/markdown", root=root),
            _artifact(root / "scene_plan.json", "application/json", root=root),
            _artifact(
                root / "mparanza_voice_request.json",
                "application/json",
                root=root,
            ),
            _artifact(root / "review_packet.md", "text/markdown", root=root),
            _artifact(
                root / "narration_approval.json",
                "application/json",
                root=root,
            ),
            _artifact(
                root / "hosted_voice_manifest.json",
                "application/json",
                root=root,
            ),
            *[_artifact(path, "audio/wav", root=root) for path in narration_paths],
            _artifact(root / "run_intake.json", "application/json", root=root),
            _artifact(root / "render_report.json", "application/json", root=root),
        ],
        "caveats": [
            "Mechanical validation does not prove scientific or source fidelity.",
            (
                "Audio hashes and durations do not prove that the spoken words "
                "match the approved narration or cryptographically authenticate "
                "the upstream provider's semantic delivery."
            ),
            "Flat images use restrained pan or zoom, not true parallax.",
        ],
        "next_actions": [
            "Watch the complete video and review every scene against its source basis.",
            "Revise, reapprove, and rerender if narration, legibility, pacing, or motion is materially wrong.",
        ],
    }
    _write_json(root / "final_artifacts.json", final_artifacts)
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
    approve.add_argument("--confirmed-by-user", action="store_true")
    attach_voice = subparsers.add_parser(
        "attach-voice",
        help="Attach an authenticated Mparanza voice bundle to an approved run",
    )
    attach_voice.add_argument("--run-dir", required=True, type=Path)
    attach_voice.add_argument("--voice-bundle", required=True, type=Path)
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
        approve_run(
            args.run_dir,
            args.approved_by,
            confirmed_by_user=args.confirmed_by_user,
        )
    elif args.command == "attach-voice":
        attach_hosted_voice(args.run_dir, args.voice_bundle)
    else:
        render_run(args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
