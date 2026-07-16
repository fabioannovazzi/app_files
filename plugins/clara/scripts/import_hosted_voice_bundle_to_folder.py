"""Import a hosted Clara voice bundle into an ordinary document folder.

This helper deliberately does not initialize or mutate a Clara case workspace.
It keeps the source bundle durable, writes a readable transcript document, and
records enough content fingerprints to make repeated imports idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping
from zipfile import BadZipFile, ZipFile

__all__ = [
    "PlainFolderImportError",
    "PlainFolderVoiceImportResult",
    "import_hosted_voice_bundle_to_folder",
    "main",
]

LOGGER = logging.getLogger(__name__)
REGISTRY_RELATIVE_PATH = Path(".clara") / "voice_imports.json"
REGISTRY_KIND = "clara_plain_folder_voice_imports"
SUPPORTED_SOURCE = "case_notes_hosted_voice"
BUNDLE_PREFIXES = ("case-notes-voice-", "case-notes-audio-")
TRANSCRIPT_FIELDS = (
    "user_transcript",
    "raw_transcription_text",
    "transcript_text_prompted",
    "realtime_user_transcript",
)
MARKER_PATTERN = re.compile(
    r"<!--\s*clara-plain-voice-import:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)
TRANSCRIPT_HEADING_PATTERN = re.compile(
    r"^##\s+(?:Transcript|Trascrizione|Transcription|Transkript)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class PlainFolderImportError(ValueError):
    """Raised when an ordinary-folder import cannot be completed safely."""


@dataclass(frozen=True)
class PlainFolderVoiceImportResult:
    """Artifacts selected or created by an ordinary-folder import."""

    status: str
    target_dir: Path
    registry_path: Path
    import_id: str
    transcript_path: Path
    bundle_path: Path
    media_paths: tuple[Path, ...]
    dedupe_reason: str | None
    variant_of: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _BundleInspection:
    payload: dict[str, Any]
    transcript: str
    transcript_field: str
    bundle_sha256: str
    payload_sha256: str
    transcript_sha256: str
    audio_sha256: str | None
    video_sha256: str | None
    session_key: str
    identity_sha256: str


@dataclass(frozen=True)
class _DuplicateMatch:
    entry: dict[str, Any] | None
    transcript_path: Path
    reason: str


@dataclass(frozen=True)
class _RegistryMatch:
    entry: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class _ArtifactSelection:
    path: Path
    managed: bool


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def _target_import_lock(target_dir: Path) -> Iterator[None]:
    lock_key = _sha256_bytes(str(target_dir).encode("utf-8"))[:24]
    lock_path = Path(tempfile.gettempdir()) / f"clara-plain-import-{lock_key}.lock"
    with lock_path.open("a+b") as lock_file:
        if sys.platform == "win32":
            msvcrt = importlib.import_module("msvcrt")
            lock_file.seek(0)
            if not lock_file.read(1):
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl = importlib.import_module("fcntl")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _normalize_transcript_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def _transcript_identity_text(value: str) -> str:
    return " ".join(_normalize_transcript_text(value).split())


def _select_transcript(payload: Mapping[str, Any]) -> tuple[str, str]:
    for field in TRANSCRIPT_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        transcript = _normalize_transcript_text(value)
        if transcript:
            return transcript, field
    raise PlainFolderImportError("hosted voice bundle does not contain a transcript")


def _validate_archive_member_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    member_path = PurePosixPath(normalized)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise PlainFolderImportError(
            f"hosted voice ZIP contains an unsafe member path: {name}"
        )


def _sha256_zip_member(archive: ZipFile, member_name: str) -> str | None:
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir() and Path(member.filename).name == member_name
    ]
    if len(matches) > 1:
        raise PlainFolderImportError(
            f"hosted voice ZIP contains duplicate media members: {member_name}"
        )
    if not matches:
        return None
    digest = hashlib.sha256()
    with archive.open(matches[0]) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_zip_payload_and_media(
    bundle_path: Path,
) -> tuple[dict[str, Any], str | None, str | None]:
    try:
        with ZipFile(bundle_path) as archive:
            for member in archive.infolist():
                _validate_archive_member_name(member.filename)
            json_members = [
                member
                for member in archive.infolist()
                if not member.is_dir()
                and Path(member.filename).suffix.lower() == ".json"
                and Path(member.filename).name.startswith(BUNDLE_PREFIXES)
            ]
            if len(json_members) != 1:
                raise PlainFolderImportError(
                    "hosted voice ZIP must contain exactly one case-notes JSON file"
                )
            try:
                payload = json.loads(archive.read(json_members[0]).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise PlainFolderImportError(
                    "hosted voice ZIP JSON is not readable"
                ) from error
            if not isinstance(payload, dict):
                raise PlainFolderImportError(
                    "hosted voice bundle JSON must be an object"
                )
            audio_name = Path(str(payload.get("audio_file_name", ""))).name
            video_name = Path(str(payload.get("video_file_name", ""))).name
            audio_sha256 = (
                _sha256_zip_member(archive, audio_name) if audio_name else None
            )
            video_sha256 = (
                _sha256_zip_member(archive, video_name) if video_name else None
            )
            return payload, audio_sha256, video_sha256
    except BadZipFile as error:
        raise PlainFolderImportError(
            "hosted voice ZIP bundle is not a valid zip file"
        ) from error


def _read_json_payload_and_media(
    bundle_path: Path,
) -> tuple[dict[str, Any], str | None, str | None]:
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlainFolderImportError(
            "hosted voice bundle JSON is not readable"
        ) from error
    if not isinstance(payload, dict):
        raise PlainFolderImportError("hosted voice bundle JSON must be an object")

    def companion_sha256(field: str) -> str | None:
        name = Path(str(payload.get(field, ""))).name
        if not name:
            return None
        companion = bundle_path.parent / name
        return _sha256_file(companion) if companion.is_file() else None

    return (
        payload,
        companion_sha256("audio_file_name"),
        companion_sha256("video_file_name"),
    )


def _validate_captured_at(payload: Mapping[str, Any]) -> str:
    captured_at = str(payload.get("captured_at", "")).strip()
    if not captured_at:
        raise PlainFolderImportError("hosted voice bundle is missing captured_at")
    try:
        datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlainFolderImportError(
            "hosted voice bundle captured_at is not a valid ISO timestamp"
        ) from error
    return captured_at


def _inspect_bundle(bundle_path: Path) -> _BundleInspection:
    source = bundle_path.expanduser().resolve()
    if not source.is_file():
        raise PlainFolderImportError(f"hosted voice bundle does not exist: {source}")
    if source.suffix.lower() not in {".zip", ".json"}:
        raise PlainFolderImportError("hosted voice bundle must be a ZIP or JSON file")
    if source.suffix.lower() == ".zip":
        payload, audio_sha256, video_sha256 = _read_zip_payload_and_media(source)
    else:
        payload, audio_sha256, video_sha256 = _read_json_payload_and_media(source)
    if payload.get("schema_version") != 1:
        raise PlainFolderImportError("unsupported hosted voice schema version")
    if payload.get("source") != SUPPORTED_SOURCE:
        raise PlainFolderImportError("hosted voice bundle has unsupported source")

    captured_at = _validate_captured_at(payload)
    transcript, transcript_field = _select_transcript(payload)
    transcript_sha256 = _sha256_bytes(
        _transcript_identity_text(transcript).encode("utf-8")
    )
    session_key = "|".join(
        [
            SUPPORTED_SOURCE,
            captured_at,
            str(payload.get("audio_file_name", "")).strip(),
            str(payload.get("original_audio_file_name", "")).strip(),
        ]
    )
    identity_payload = {
        "session_key": session_key,
        "transcript_sha256": transcript_sha256,
        "audio_sha256": audio_sha256,
        "video_sha256": video_sha256,
    }
    return _BundleInspection(
        payload=dict(payload),
        transcript=transcript,
        transcript_field=transcript_field,
        bundle_sha256=_sha256_file(source),
        payload_sha256=_canonical_json_sha256(payload),
        transcript_sha256=transcript_sha256,
        audio_sha256=audio_sha256,
        video_sha256=video_sha256,
        session_key=session_key,
        identity_sha256=_canonical_json_sha256(identity_payload),
    )


def _default_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": REGISTRY_KIND,
        "updated_at": None,
        "imports": [],
    }


def _registry_path_for_target(target_dir: Path) -> Path:
    control_dir = target_dir / REGISTRY_RELATIVE_PATH.parent
    if control_dir.is_symlink():
        raise PlainFolderImportError(
            f"plain-folder control directory must not be a symlink: {control_dir}"
        )
    if control_dir.exists() and not control_dir.is_dir():
        raise PlainFolderImportError(
            f"plain-folder control path is not a directory: {control_dir}"
        )
    registry_path = target_dir / REGISTRY_RELATIVE_PATH
    if registry_path.is_symlink():
        raise PlainFolderImportError(
            f"plain-folder import registry must not be a symlink: {registry_path}"
        )
    return registry_path


def _load_registry(registry_path: Path) -> dict[str, Any]:
    if not registry_path.exists():
        return _default_registry()
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlainFolderImportError(
            f"plain-folder import registry is not readable: {registry_path}"
        ) from error
    if not isinstance(registry, dict):
        raise PlainFolderImportError("plain-folder import registry must be an object")
    if registry.get("schema_version") != 1 or registry.get("kind") != REGISTRY_KIND:
        raise PlainFolderImportError("unsupported plain-folder import registry")
    if not isinstance(registry.get("imports"), list):
        raise PlainFolderImportError(
            "plain-folder import registry imports must be a list"
        )
    return registry


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _install_temporary_file(temporary_path: Path, destination: Path) -> None:
    try:
        destination.hardlink_to(temporary_path)
    except FileExistsError as error:
        raise PlainFolderImportError(
            f"refusing to overwrite a concurrently created artifact: {destination}"
        ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_create_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        temporary_path = Path(handle.name)
    _install_temporary_file(temporary_path, path)


def _atomic_write_registry(
    registry_path: Path,
    registry: Mapping[str, Any],
) -> None:
    _atomic_write_text(
        registry_path,
        json.dumps(registry, indent=2, ensure_ascii=True) + "\n",
    )


def _safe_relative_path(target_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(target_dir.resolve()).as_posix()
    except ValueError as error:
        raise PlainFolderImportError(
            f"artifact is outside the target folder: {path}"
        ) from error


def _resolve_registry_artifact(target_dir: Path, value: Any) -> Path | None:
    relative = Path(str(value or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (target_dir / relative).resolve()
    try:
        candidate.relative_to(target_dir.resolve())
    except ValueError:
        return None
    return candidate


def _entry_identity(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    identity = entry.get("identity")
    return identity if isinstance(identity, Mapping) else {}


def _entry_transcript_path(
    target_dir: Path,
    entry: Mapping[str, Any],
) -> Path | None:
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return None
    transcript = artifacts.get("transcript")
    if not isinstance(transcript, Mapping):
        return None
    path = _resolve_registry_artifact(target_dir, transcript.get("path"))
    return path if path is not None and path.is_file() else None


def _entry_bundle_path(
    target_dir: Path,
    entry: Mapping[str, Any],
) -> Path | None:
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return None
    bundle = artifacts.get("bundle")
    if not isinstance(bundle, Mapping):
        return None
    path = _resolve_registry_artifact(target_dir, bundle.get("path"))
    return path if path is not None and path.is_file() else None


def _registry_match_reason(
    entry: Mapping[str, Any],
    inspection: _BundleInspection,
) -> str | None:
    identity = _entry_identity(entry)
    if identity.get("bundle_sha256") == inspection.bundle_sha256:
        return "bundle_sha256"
    same_media = (
        identity.get("audio_sha256") == inspection.audio_sha256
        and identity.get("video_sha256") == inspection.video_sha256
    )
    if identity.get("payload_sha256") == inspection.payload_sha256 and same_media:
        return "payload_sha256"
    if (
        inspection.audio_sha256
        and identity.get("audio_sha256") == inspection.audio_sha256
        and identity.get("video_sha256") == inspection.video_sha256
        and identity.get("transcript_sha256") == inspection.transcript_sha256
    ):
        return "audio_video_and_transcript_sha256"
    if (
        not inspection.audio_sha256
        and not identity.get("audio_sha256")
        and identity.get("video_sha256") == inspection.video_sha256
        and identity.get("session_key") == inspection.session_key
        and identity.get("transcript_sha256") == inspection.transcript_sha256
    ):
        return "session_media_and_transcript_sha256"
    return None


def _find_registry_match(
    registry: Mapping[str, Any],
    inspection: _BundleInspection,
) -> _RegistryMatch | None:
    for raw_entry in registry.get("imports", []):
        if not isinstance(raw_entry, dict):
            continue
        reason = _registry_match_reason(raw_entry, inspection)
        if reason:
            return _RegistryMatch(raw_entry, reason)
    return None


def _find_registry_duplicate(
    target_dir: Path,
    registry: Mapping[str, Any],
    inspection: _BundleInspection,
) -> _DuplicateMatch | None:
    match = _find_registry_match(registry, inspection)
    if match is None:
        return None
    transcript_path = _entry_transcript_path(target_dir, match.entry)
    if transcript_path is None:
        return None
    return _DuplicateMatch(match.entry, transcript_path, match.reason)


def _find_identity_variant(
    registry: Mapping[str, Any],
    inspection: _BundleInspection,
) -> str | None:
    for raw_entry in registry.get("imports", []):
        if not isinstance(raw_entry, Mapping):
            continue
        identity = _entry_identity(raw_entry)
        same_audio = bool(
            inspection.audio_sha256
            and identity.get("audio_sha256") == inspection.audio_sha256
        )
        same_session = identity.get("session_key") == inspection.session_key
        same_payload = identity.get("payload_sha256") == inspection.payload_sha256
        changed_transcript = (
            identity.get("transcript_sha256") != inspection.transcript_sha256
        )
        changed_audio = identity.get("audio_sha256") != inspection.audio_sha256
        changed_video = identity.get("video_sha256") != inspection.video_sha256
        if (
            (same_payload and (changed_audio or changed_video))
            or (same_audio and (changed_transcript or changed_video))
            or (same_session and (changed_transcript or changed_audio or changed_video))
        ):
            return str(raw_entry.get("id", "")).strip() or None
    return None


def _read_import_marker(path: Path) -> Mapping[str, Any] | None:
    try:
        prefix = path.read_text(encoding="utf-8")[:8192]
    except (OSError, UnicodeDecodeError):
        return None
    match = MARKER_PATTERN.search(prefix)
    if match is None:
        return None
    try:
        marker = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return marker if isinstance(marker, Mapping) else None


def _find_unregistered_transcript(
    target_dir: Path,
    inspection: _BundleInspection,
    expected_name: str,
    *,
    allow_content_adoption: bool,
) -> _DuplicateMatch | None:
    if not target_dir.exists():
        return None
    candidates: list[Path] = []
    expected = target_dir / expected_name
    if expected.is_file():
        candidates.append(expected)
    for path in sorted(target_dir.glob("*.md")):
        lowered = path.name.lower()
        if path not in candidates and ("transcript" in lowered or "trascr" in lowered):
            candidates.append(path)
    transcript_identity = _transcript_identity_text(inspection.transcript)
    for path in candidates:
        marker = _read_import_marker(path)
        if marker is not None:
            if marker.get("identity_sha256") == inspection.identity_sha256:
                return _DuplicateMatch(None, path, "embedded_identity_marker")
            if marker.get("payload_sha256") == inspection.payload_sha256:
                return _DuplicateMatch(None, path, "embedded_payload_marker")
        try:
            document = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        normalized_document = _transcript_identity_text(document)
        if (
            allow_content_adoption
            and path == expected
            and transcript_identity
            and transcript_identity in normalized_document
        ):
            return _DuplicateMatch(None, path, "existing_transcript_content")
    return None


def _find_existing_bundle_copy(
    target_dir: Path,
    source: Path,
    inspection: _BundleInspection,
    entry: Mapping[str, Any] | None = None,
) -> Path | None:
    if source.parent.resolve() == target_dir.resolve():
        return source
    if entry is not None:
        registered = _entry_bundle_path(target_dir, entry)
        if registered is not None:
            recorded_sha256 = str(
                _entry_identity(entry).get("bundle_sha256", "")
            ).strip()
            if recorded_sha256 and _sha256_file(registered) != recorded_sha256:
                raise PlainFolderImportError(
                    f"registered bundle content changed: {registered}"
                )
            return registered
    if not target_dir.exists():
        return None
    for pattern in ("case-notes-audio-*", "case-notes-voice-*"):
        for candidate in sorted(target_dir.glob(pattern)):
            if (
                candidate.is_file()
                and candidate.suffix.lower() in {".zip", ".json"}
                and _sha256_file(candidate) == inspection.bundle_sha256
            ):
                return candidate
    return None


def _available_path(target_dir: Path, desired_name: str) -> Path:
    safe_name = Path(desired_name).name
    if not safe_name or safe_name != desired_name:
        raise PlainFolderImportError(f"unsafe output filename: {desired_name}")
    desired = target_dir / safe_name
    if not desired.exists():
        return desired
    for index in range(2, 10000):
        candidate = desired.with_name(f"{desired.stem}-{index}{desired.suffix}")
        if not candidate.exists():
            return candidate
    raise PlainFolderImportError(f"could not allocate output filename for {safe_name}")


def _copy_file_atomically(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, handle, length=1024 * 1024)
    _install_temporary_file(temporary_path, destination)


def _copy_loose_media(
    source_bundle: Path,
    target_dir: Path,
    payload: Mapping[str, Any],
    *,
    dry_run: bool,
) -> tuple[_ArtifactSelection, ...]:
    if source_bundle.suffix.lower() == ".zip":
        return ()
    copied: list[_ArtifactSelection] = []
    seen: set[Path] = set()
    for field in ("audio_file_name", "video_file_name"):
        name = Path(str(payload.get(field, ""))).name
        source = source_bundle.parent / name if name else None
        if source is None or source in seen or not source.is_file():
            continue
        seen.add(source)
        if source.parent.resolve() == target_dir.resolve():
            copied.append(_ArtifactSelection(source, False))
            continue
        destination = target_dir / name
        if destination.exists():
            if _sha256_file(destination) == _sha256_file(source):
                copied.append(_ArtifactSelection(destination, False))
                continue
            destination = _available_path(target_dir, name)
        if not dry_run:
            _copy_file_atomically(source, destination)
        copied.append(_ArtifactSelection(destination, True))
    return tuple(copied)


def _source_metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = payload.get("source_metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _duration_seconds(payload: Mapping[str, Any]) -> float | None:
    value = payload.get("capture_elapsed_seconds")
    if value in (None, ""):
        transcription = payload.get("transcription_metadata")
        if isinstance(transcription, Mapping):
            value = transcription.get("source_duration_seconds")
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "not available"
    total = max(0, round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def _transcript_markdown(
    inspection: _BundleInspection,
    *,
    source_bundle_name: str,
    title_override: str | None,
) -> str:
    payload = inspection.payload
    metadata = _source_metadata(payload)
    language = str(payload.get("language", "")).strip()
    italian = language.lower().startswith("it")
    source_title = str(metadata.get("title", "")).strip()
    title = (title_override or source_title or "Hosted voice").strip()
    participants = str(metadata.get("participants", "")).strip()
    captured_at = str(payload.get("captured_at", "")).strip()
    marker = json.dumps(
        {
            "schema_version": 1,
            "identity_sha256": inspection.identity_sha256,
            "payload_sha256": inspection.payload_sha256,
            "transcript_sha256": inspection.transcript_sha256,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    if italian:
        heading = f"# {title} — Trascrizione della call"
        labels = {
            "captured": "Registrata",
            "duration": "Durata",
            "participants": "Partecipanti indicati nei metadati",
            "language": "Lingua",
            "source": "File sorgente",
        }
        status = (
            "Trascrizione automatica conservata senza attribuzione certa dei "
            "singoli interventi. Correggere o attribuire i parlanti solo quando "
            "il testo o altra evidenza autorizzata lo supportano."
        )
        section = "## Trascrizione"
    else:
        heading = f"# {title} — Call transcript"
        labels = {
            "captured": "Captured",
            "duration": "Duration",
            "participants": "Participants listed in metadata",
            "language": "Language",
            "source": "Source file",
        }
        status = (
            "This automatic transcript is preserved without verified speaker "
            "attribution. Correct or attribute speakers only when supported by "
            "the text or other authorized evidence."
        )
        section = "## Transcript"
    participant_value = participants or "not available"
    language_value = language or "not available"
    return "\n".join(
        [
            f"<!-- clara-plain-voice-import: {marker} -->",
            heading,
            "",
            f"- {labels['captured']}: {captured_at}",
            f"- {labels['duration']}: {_format_duration(_duration_seconds(payload))}",
            f"- {labels['participants']}: {participant_value}",
            f"- {labels['language']}: {language_value}",
            f"- {labels['source']}: `{source_bundle_name}`",
            "",
            f"> {status}",
            "",
            section,
            "",
            inspection.transcript,
            "",
        ]
    )


def _artifact_record(
    target_dir: Path,
    path: Path,
    *,
    managed: bool,
    sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "path": _safe_relative_path(target_dir, path),
        "sha256": sha256 or (_sha256_file(path) if path.is_file() else None),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "managed": managed,
    }


def _build_registry_entry(
    target_dir: Path,
    inspection: _BundleInspection,
    *,
    bundle_path: Path,
    bundle_managed: bool,
    transcript_path: Path,
    transcript_managed: bool,
    media_artifacts: tuple[_ArtifactSelection, ...],
    imported_at: str,
    variant_of: str | None,
) -> dict[str, Any]:
    payload = inspection.payload
    metadata = _source_metadata(payload)
    entry: dict[str, Any] = {
        "id": f"imp-{inspection.identity_sha256[:16]}",
        "imported_at": imported_at,
        "source": SUPPORTED_SOURCE,
        "captured_at": str(payload.get("captured_at", "")).strip(),
        "input_name": bundle_path.name,
        "identity": {
            "identity_sha256": inspection.identity_sha256,
            "session_key": inspection.session_key,
            "bundle_sha256": inspection.bundle_sha256,
            "payload_sha256": inspection.payload_sha256,
            "transcript_sha256": inspection.transcript_sha256,
            "audio_sha256": inspection.audio_sha256,
            "video_sha256": inspection.video_sha256,
        },
        "artifacts": {
            "bundle": _artifact_record(
                target_dir,
                bundle_path,
                managed=bundle_managed,
                sha256=inspection.bundle_sha256,
            ),
            "transcript": _artifact_record(
                target_dir,
                transcript_path,
                managed=transcript_managed,
            ),
            "media": [
                _artifact_record(
                    target_dir,
                    artifact.path,
                    managed=artifact.managed,
                )
                for artifact in media_artifacts
            ],
        },
        "metadata": {
            "capture_source": str(payload.get("capture_source", "")).strip(),
            "language": str(payload.get("language", "")).strip(),
            "title": str(metadata.get("title", "")).strip(),
            "participants": str(metadata.get("participants", "")).strip(),
            "transcript_field": inspection.transcript_field,
        },
    }
    if variant_of:
        entry["variant_of"] = variant_of
    return entry


def _result_from_duplicate(
    target_dir: Path,
    registry_path: Path,
    source: Path,
    inspection: _BundleInspection,
    duplicate: _DuplicateMatch,
    *,
    registry: dict[str, Any],
    now_iso: str,
    dry_run: bool,
    transcript_managed_on_repair: bool = False,
) -> PlainFolderVoiceImportResult:
    registered_bundle = (
        _entry_bundle_path(target_dir, duplicate.entry)
        if duplicate.entry is not None
        else None
    )
    registered_transcript = (
        _entry_transcript_path(target_dir, duplicate.entry)
        if duplicate.entry is not None
        else None
    )
    existing_bundle = _find_existing_bundle_copy(
        target_dir,
        source,
        inspection,
        duplicate.entry,
    )
    bundle_managed = False
    if existing_bundle is None:
        existing_bundle = _available_path(target_dir, source.name)
        bundle_managed = True
        if not dry_run:
            _copy_file_atomically(source, existing_bundle)
    media_artifacts = _copy_loose_media(
        source,
        target_dir,
        inspection.payload,
        dry_run=dry_run,
    )
    media_paths = tuple(artifact.path for artifact in media_artifacts)
    warnings: list[str] = []
    registry_repaired = False
    if duplicate.entry is not None:
        import_id = str(duplicate.entry.get("id", "")).strip()
        recorded = duplicate.entry.get("artifacts")
        if not isinstance(recorded, dict):
            recorded = {}
            duplicate.entry["artifacts"] = recorded
        transcript_record = recorded.get("transcript")
        if isinstance(transcript_record, Mapping):
            recorded_sha = str(transcript_record.get("sha256", "")).strip()
            if (
                registered_transcript is not None
                and recorded_sha
                and _sha256_file(duplicate.transcript_path) != recorded_sha
            ):
                warnings.append(
                    "The existing transcript document was edited after import and was preserved."
                )
        if registered_bundle is None:
            recorded["bundle"] = _artifact_record(
                target_dir,
                existing_bundle,
                managed=bundle_managed,
                sha256=inspection.bundle_sha256,
            )
            registry_repaired = True
        recorded_media = recorded.get("media")
        recorded_media_paths: list[Path] = []
        if isinstance(recorded_media, list):
            for raw_media in recorded_media:
                if not isinstance(raw_media, Mapping):
                    continue
                path = _resolve_registry_artifact(
                    target_dir,
                    raw_media.get("path"),
                )
                if path is not None and path.is_file():
                    recorded_media_paths.append(path)
        if media_artifacts and (
            tuple(path.resolve() for path in recorded_media_paths)
            != tuple(path.resolve() for path in media_paths)
            or any(artifact.managed for artifact in media_artifacts)
        ):
            recorded["media"] = [
                _artifact_record(
                    target_dir,
                    artifact.path,
                    managed=artifact.managed,
                )
                for artifact in media_artifacts
            ]
            registry_repaired = True
        if (
            transcript_managed_on_repair
            or registered_transcript is None
            or registered_transcript.resolve() != duplicate.transcript_path.resolve()
        ):
            recorded["transcript"] = _artifact_record(
                target_dir,
                duplicate.transcript_path,
                managed=transcript_managed_on_repair,
            )
            registry_repaired = True
        if registry_repaired:
            registry["updated_at"] = now_iso
            if not dry_run:
                _atomic_write_registry(registry_path, registry)
    else:
        import_id = f"imp-{inspection.identity_sha256[:16]}"
        entry = _build_registry_entry(
            target_dir,
            inspection,
            bundle_path=existing_bundle,
            bundle_managed=bundle_managed,
            transcript_path=duplicate.transcript_path,
            transcript_managed=False,
            media_artifacts=media_artifacts,
            imported_at=now_iso,
            variant_of=None,
        )
        registry["imports"].append(entry)
        registry["updated_at"] = now_iso
        if not dry_run:
            _atomic_write_registry(registry_path, registry)
    return PlainFolderVoiceImportResult(
        status=(
            "repaired"
            if registry_repaired
            else "already_imported" if duplicate.entry is not None else "adopted"
        ),
        target_dir=target_dir,
        registry_path=registry_path,
        import_id=import_id,
        transcript_path=duplicate.transcript_path,
        bundle_path=existing_bundle,
        media_paths=media_paths,
        dedupe_reason=duplicate.reason,
        variant_of=None,
        warnings=tuple(warnings),
    )


def _import_hosted_voice_bundle_to_folder_unlocked(
    target_dir: Path,
    bundle_path: Path,
    *,
    title: str | None = None,
    allow_variant: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PlainFolderVoiceImportResult:
    """Import *bundle_path* into an ordinary folder without case initialization."""

    target = target_dir.expanduser().resolve()
    source = bundle_path.expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise PlainFolderImportError(f"target is not a folder: {target}")
    if (target / "case_manifest.json").exists():
        raise PlainFolderImportError(
            "target is a Clara case workspace; use import_hosted_voice_bundle.py"
        )
    inspection = _inspect_bundle(source)
    registry_path = _registry_path_for_target(target)
    registry = _load_registry(registry_path)
    now_iso = _now_iso(now)
    if not target.exists() and not dry_run:
        target.mkdir(parents=True)

    registry_match = _find_registry_match(registry, inspection)
    variant_of = _find_identity_variant(registry, inspection)
    if variant_of and not allow_variant:
        raise PlainFolderImportError(
            "bundle conflicts with an existing recording identity; rerun with "
            "--allow-variant only if the alternate transcript/media should be kept"
        )
    adoption_bundle = _find_existing_bundle_copy(
        target,
        source,
        inspection,
        registry_match.entry if registry_match is not None else None,
    )
    expected_transcript_name = f"{(adoption_bundle or source).stem}-transcript.md"
    duplicate = _find_registry_duplicate(target, registry, inspection)
    if duplicate is None and variant_of is None:
        unregistered = _find_unregistered_transcript(
            target,
            inspection,
            expected_transcript_name,
            allow_content_adoption=adoption_bundle is not None,
        )
        if unregistered is not None and registry_match is not None:
            duplicate = _DuplicateMatch(
                registry_match.entry,
                unregistered.transcript_path,
                registry_match.reason,
            )
        else:
            duplicate = unregistered
    if duplicate is not None:
        return _result_from_duplicate(
            target,
            registry_path,
            source,
            inspection,
            duplicate,
            registry=registry,
            now_iso=now_iso,
            dry_run=dry_run,
        )

    if registry_match is not None:
        existing_bundle = _find_existing_bundle_copy(
            target,
            source,
            inspection,
            registry_match.entry,
        )
        bundle_name = (
            existing_bundle.name if existing_bundle is not None else source.name
        )
        transcript_path = _available_path(
            target,
            f"{Path(bundle_name).stem}-transcript.md",
        )
        if not dry_run:
            _atomic_create_text(
                transcript_path,
                _transcript_markdown(
                    inspection,
                    source_bundle_name=bundle_name,
                    title_override=title,
                ),
            )
        return _result_from_duplicate(
            target,
            registry_path,
            source,
            inspection,
            _DuplicateMatch(
                registry_match.entry,
                transcript_path,
                registry_match.reason,
            ),
            registry=registry,
            now_iso=now_iso,
            dry_run=dry_run,
            transcript_managed_on_repair=True,
        )

    existing_bundle = _find_existing_bundle_copy(target, source, inspection)
    bundle_managed = existing_bundle is None
    destination_bundle = existing_bundle or _available_path(target, source.name)
    if bundle_managed and not dry_run:
        _copy_file_atomically(source, destination_bundle)
    media_artifacts = _copy_loose_media(
        source,
        target,
        inspection.payload,
        dry_run=dry_run,
    )
    media_paths = tuple(artifact.path for artifact in media_artifacts)
    transcript_path = _available_path(
        target,
        f"{destination_bundle.stem}-transcript.md",
    )
    transcript_markdown = _transcript_markdown(
        inspection,
        source_bundle_name=destination_bundle.name,
        title_override=title,
    )
    if not dry_run:
        _atomic_create_text(transcript_path, transcript_markdown)

    status = "repaired" if existing_bundle is not None else "imported"
    entry = _build_registry_entry(
        target,
        inspection,
        bundle_path=destination_bundle,
        bundle_managed=bundle_managed,
        transcript_path=transcript_path,
        transcript_managed=True,
        media_artifacts=media_artifacts,
        imported_at=now_iso,
        variant_of=variant_of,
    )
    registry["imports"].append(entry)
    registry["updated_at"] = now_iso
    if not dry_run:
        _atomic_write_registry(registry_path, registry)
    return PlainFolderVoiceImportResult(
        status=status,
        target_dir=target,
        registry_path=registry_path,
        import_id=str(entry["id"]),
        transcript_path=transcript_path,
        bundle_path=destination_bundle,
        media_paths=media_paths,
        dedupe_reason=None,
        variant_of=variant_of,
        warnings=(),
    )


def import_hosted_voice_bundle_to_folder(
    target_dir: Path,
    bundle_path: Path,
    *,
    title: str | None = None,
    allow_variant: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PlainFolderVoiceImportResult:
    """Import a hosted voice bundle while serializing writes per target folder."""

    target = target_dir.expanduser().resolve()
    with _target_import_lock(target):
        return _import_hosted_voice_bundle_to_folder_unlocked(
            target,
            bundle_path,
            title=title,
            allow_variant=allow_variant,
            dry_run=dry_run,
            now=now,
        )


def main() -> int:
    """Run an ordinary-folder hosted voice import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_dir", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--allow-variant", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = import_hosted_voice_bundle_to_folder(
            args.target_dir,
            args.bundle,
            title=args.title,
            allow_variant=args.allow_variant,
            dry_run=args.dry_run,
        )
    except PlainFolderImportError as error:
        LOGGER.error("Plain-folder import failed: %s", error)
        return 2
    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "status": result.status,
                    "import_id": result.import_id,
                    "bundle_path": str(result.bundle_path),
                    "transcript_path": str(result.transcript_path),
                    "registry_path": str(result.registry_path),
                    "dedupe_reason": result.dedupe_reason,
                    "variant_of": result.variant_of,
                    "warnings": list(result.warnings),
                },
                ensure_ascii=True,
            )
            + "\n"
        )
    else:
        LOGGER.info("Plain-folder import status: %s", result.status)
        LOGGER.info("Bundle: %s", result.bundle_path)
        LOGGER.info("Transcript: %s", result.transcript_path)
        LOGGER.info("Registry: %s", result.registry_path)
        for warning in result.warnings:
            LOGGER.warning("Warning: %s", warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
