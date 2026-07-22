"""Register locally supplied INPS portal exports as immutable local evidence.

This module intentionally performs no browser automation, authentication, network
request, or portal submission. It accepts regular files supplied from local
storage and records a bounded, reviewable manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

__all__ = [
    "PortalExportError",
    "register_portal_exports",
    "verify_portal_export",
]

LOGGER = logging.getLogger(__name__)
SCRIPT_PATH = Path(__file__).resolve()
COMPONENT_ROOT = SCRIPT_PATH.parents[1]
MANIFEST_NAME = "manifest.json"
MANIFEST_TYPE = "inps_official_portal_export_registration"
SCHEMA_VERSION = "2.0"
MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_SIZE_BYTES = 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
INSPECTION_BYTES = 16 * 1024

MEDIA_BY_SUFFIX = {
    ".csv": ("text/csv", ".csv"),
    ".jpeg": ("image/jpeg", ".jpg"),
    ".jpg": ("image/jpeg", ".jpg"),
    ".pdf": ("application/pdf", ".pdf"),
    ".png": ("image/png", ".png"),
    ".tif": ("image/tiff", ".tif"),
    ".tiff": ("image/tiff", ".tif"),
    ".txt": ("text/plain", ".txt"),
    ".xml": ("application/xml", ".xml"),
}
MEDIA_BY_STORED_SUFFIX = {
    stored_suffix: media_type
    for media_type, stored_suffix in set(MEDIA_BY_SUFFIX.values())
}
FORBIDDEN_SUFFIXES = {
    ".cookies",
    ".crx",
    ".db",
    ".har",
    ".htm",
    ".html",
    ".json",
    ".jsonl",
    ".ldb",
    ".localstorage",
    ".log",
    ".sqlite",
    ".sqlite3",
    ".webarchive",
}
FORBIDDEN_BROWSER_NAMES = {
    "browser profile",
    "cookies",
    "history",
    "login data",
    "local storage",
    "network persistent state",
    "preferences",
    "secure preferences",
    "session storage",
    "web data",
}
OFFICIAL_HOST_ROOTS = ("inps.it",)
REGISTRATION_ID_RE = re.compile(r"^INPS-EXPORT-[0-9a-f]{32}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STORED_NAME_RE = re.compile(
    r"^inps-export-(?P<index>[0-9]{3})-(?P<digest>[0-9a-f]{12})"
    r"(?P<suffix>\.[a-z0-9]+)$"
)
TOP_LEVEL_KEYS = {
    "schema_version",
    "manifest_type",
    "registration_id",
    "created_at",
    "source_origin",
    "safety",
    "artifacts",
}
SAFETY_KEYS = {
    "source_files_supplied_locally",
    "network_access_performed",
    "portal_automation_performed",
    "credentials_collected",
    "cookies_collected",
    "browser_profile_data_collected",
    "submission_performed",
}
ARTIFACT_KEYS = {
    "artifact_id",
    "stored_name",
    "original_name_sha256",
    "media_type",
    "size_bytes",
    "sha256",
}
SAFE_SAFETY_VALUES = {
    "source_files_supplied_locally": True,
    "network_access_performed": False,
    "portal_automation_performed": False,
    "credentials_collected": False,
    "cookies_collected": False,
    "browser_profile_data_collected": False,
    "submission_performed": False,
}


class PortalExportError(ValueError):
    """Raised when an export registration or manifest is unsafe or invalid."""


@dataclass(frozen=True)
class _SourcePlan:
    path: Path
    device: int
    inode: int
    size_bytes: int
    modified_ns: int
    media_type: str
    stored_suffix: str
    sha256: str
    original_name_sha256: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_root() -> Path | None:
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    return None


def _forbidden_output_roots() -> set[Path]:
    roots = {COMPONENT_ROOT.resolve()}
    git_root = _git_root()
    if git_root is not None:
        roots.add(git_root)
    for candidate in SCRIPT_PATH.parents:
        if (candidate / ".codex-plugin" / "plugin.json").is_file():
            roots.add(candidate.resolve())
    return roots


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _canonical_new_output_dir(output_dir: Path) -> Path:
    expanded = output_dir.expanduser()
    if expanded.exists() or expanded.is_symlink():
        raise PortalExportError(
            "output directory must be new and must not be a symlink"
        )
    parent = expanded.parent.resolve(strict=True)
    if not parent.is_dir():
        raise PortalExportError("output directory parent must be a directory")
    resolved = parent / expanded.name
    if any(_is_within(resolved, root) for root in _forbidden_output_roots()):
        raise PortalExportError(
            "output directory must be outside the Git/plugin workspace"
        )
    return resolved


def _existing_output_dir(output_dir: Path) -> Path:
    if output_dir.is_symlink():
        raise PortalExportError("output directory must not be a symlink")
    resolved = output_dir.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise PortalExportError("registered output path must be a directory")
    if any(_is_within(resolved, root) for root in _forbidden_output_roots()):
        raise PortalExportError(
            "registered output must remain outside Git/plugin workspace"
        )
    _require_owner_only(resolved, directory=True)
    return resolved


def _require_owner_only(path: Path, *, directory: bool) -> None:
    details = path.stat(follow_symlinks=False)
    permissions = stat.S_IMODE(details.st_mode)
    required_owner_bits = 0o700 if directory else 0o600
    if permissions & 0o077 or permissions & required_owner_bits != required_owner_bits:
        kind = "directory" if directory else "file"
        raise PortalExportError(f"registered {kind} is not owner-only: {path.name}")
    if hasattr(os, "getuid") and details.st_uid != os.getuid():
        raise PortalExportError(
            f"registered path is not owned by the current user: {path.name}"
        )


def _normalize_origin(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortalExportError("source origin is required")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https":
        raise PortalExportError("source origin must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise PortalExportError("source origin must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise PortalExportError(
            "source origin must contain only scheme and official host"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise PortalExportError("source origin has an invalid port") from exc
    if port not in {None, 443}:
        raise PortalExportError("source origin may use only the default HTTPS port")
    hostname = parsed.hostname
    if hostname is None or hostname.endswith("."):
        raise PortalExportError("source origin has an invalid host")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise PortalExportError("source origin has an invalid host") from exc
    labels = ascii_hostname.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or re.fullmatch(r"[a-z0-9-]+", label) is None
        for label in labels
    ):
        raise PortalExportError("source origin has an invalid host")
    if not any(
        ascii_hostname == root or ascii_hostname.endswith(f".{root}")
        for root in OFFICIAL_HOST_ROOTS
    ):
        raise PortalExportError("source origin must be an official inps.it host")
    return f"https://{ascii_hostname}"


def _normalize_timestamp(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortalExportError(f"{field} is required")
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise PortalExportError(f"{field} must be an ISO date-time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortalExportError(f"{field} must include a timezone")
    return parsed.replace(microsecond=0).isoformat()


def _open_regular_source(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PortalExportError("cannot open source as a regular file") from exc
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode):
        os.close(descriptor)
        raise PortalExportError("source is not a regular file")
    return descriptor, details


def _browser_artifact_name(path: Path) -> bool:
    normalized_stem = " ".join(
        part for part in re.split(r"[^a-z0-9]+", path.stem.casefold()) if part
    )
    return normalized_stem in FORBIDDEN_BROWSER_NAMES or any(
        normalized_stem.startswith(f"{name} ") for name in FORBIDDEN_BROWSER_NAMES
    )


def _decode_text_prefix(head: bytes) -> str:
    encodings = ("utf-16",) if head.startswith((b"\xff\xfe", b"\xfe\xff")) else ()
    for encoding in (*encodings, "utf-8-sig", "cp1252"):
        try:
            return head.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _validate_content_signature(suffix: str, head: bytes, *, name: str) -> None:
    if not head:
        raise PortalExportError(f"source file is empty: {name}")
    if suffix == ".pdf" and not head.startswith(b"%PDF-"):
        raise PortalExportError(f"PDF signature is invalid: {name}")
    if suffix == ".png" and not head.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PortalExportError(f"PNG signature is invalid: {name}")
    if suffix in {".jpg", ".jpeg"} and not head.startswith(b"\xff\xd8\xff"):
        raise PortalExportError(f"JPEG signature is invalid: {name}")
    if suffix in {".tif", ".tiff"} and not head.startswith((b"II*\x00", b"MM\x00*")):
        raise PortalExportError(f"TIFF signature is invalid: {name}")
    if suffix not in {".csv", ".txt", ".xml"}:
        return
    if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise PortalExportError(f"text export contains binary data: {name}")
    text = _decode_text_prefix(head).lstrip("\ufeff \t\r\n").casefold()
    text_sample = text[:4096]
    if "<!doctype html" in text_sample or re.search(r"<html(?:\s|>)", text_sample):
        raise PortalExportError(f"HTML exports are not accepted: {name}")
    if suffix == ".xml" and not text.startswith(("<?xml", "<")):
        raise PortalExportError(f"XML signature is invalid: {name}")
    cookie_markers = (
        "# netscape http cookie file",
        "cookie:",
        "expiration\tname\tvalue",
        "set-cookie:",
        "localstorage",
        "sessionstorage",
    )
    if any(marker in text_sample for marker in cookie_markers):
        raise PortalExportError(
            f"cookie or browser-storage export is forbidden: {name}"
        )
    if suffix in {".csv", ".txt"} and all(
        marker in text_sample for marker in ('"log"', '"creator"', '"entries"')
    ):
        raise PortalExportError(f"HAR browser export is forbidden: {name}")


def _source_fingerprint(details: os.stat_result) -> tuple[int, int, int, int]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_size,
        details.st_mtime_ns,
    )


def _inspect_source(source: Path, *, source_index: int) -> _SourcePlan:
    source_label = f"source[{source_index}]"
    if source.is_symlink():
        raise PortalExportError(f"source symlinks are forbidden: {source_label}")
    suffix = source.suffix.casefold()
    if suffix in FORBIDDEN_SUFFIXES:
        raise PortalExportError(
            f"browser/profile export format is forbidden: {source_label}"
        )
    if suffix not in MEDIA_BY_SUFFIX:
        raise PortalExportError(f"unsupported evidence format: {source_label}")
    if _browser_artifact_name(source):
        raise PortalExportError(
            f"browser profile artifact is forbidden: {source_label}"
        )

    descriptor, before = _open_regular_source(source)
    digest = hashlib.sha256()
    head = bytearray()
    try:
        if before.st_size <= 0:
            raise PortalExportError(f"source file is empty: {source_label}")
        if before.st_size > MAX_FILE_SIZE_BYTES:
            raise PortalExportError(
                f"source file exceeds the registrar size limit: {source_label}"
            )
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            if len(head) < INSPECTION_BYTES:
                head.extend(chunk[: INSPECTION_BYTES - len(head)])
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _source_fingerprint(before) != _source_fingerprint(after):
        raise PortalExportError(
            f"source changed while it was inspected: {source_label}"
        )
    _validate_content_signature(suffix, bytes(head), name=source_label)
    media_type, stored_suffix = MEDIA_BY_SUFFIX[suffix]
    name_hash = hashlib.sha256(source.name.encode("utf-8", "surrogatepass")).hexdigest()
    return _SourcePlan(
        path=source,
        device=before.st_dev,
        inode=before.st_ino,
        size_bytes=before.st_size,
        modified_ns=before.st_mtime_ns,
        media_type=media_type,
        stored_suffix=stored_suffix,
        sha256=digest.hexdigest(),
        original_name_sha256=name_hash,
    )


def _copy_plan(plan: _SourcePlan, destination: Path, *, source_index: int) -> None:
    source_label = f"source[{source_index}]"
    source_descriptor, before = _open_regular_source(plan.path)
    expected = (plan.device, plan.inode, plan.size_bytes, plan.modified_ns)
    if _source_fingerprint(before) != expected:
        os.close(source_descriptor)
        raise PortalExportError(f"source changed after inspection: {source_label}")
    destination_descriptor = -1
    digest = hashlib.sha256()
    copied = 0
    try:
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.fchmod(destination_descriptor, 0o600)
        while True:
            chunk = os.read(source_descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            copied += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                if written <= 0:
                    raise OSError("short write while registering portal export")
                view = view[written:]
        after = os.fstat(source_descriptor)
        os.fsync(destination_descriptor)
    finally:
        os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)
    if (
        _source_fingerprint(after) != expected
        or copied != plan.size_bytes
        or digest.hexdigest() != plan.sha256
    ):
        destination.unlink(missing_ok=True)
        raise PortalExportError(f"source changed while it was copied: {source_label}")


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while writing registration manifest")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cleanup_failed_registration(destination_dir: Path) -> None:
    """Remove partial registrar output or leave a non-sensitive failure marker."""

    if not destination_dir.is_dir() or destination_dir.is_symlink():
        return
    for entry in destination_dir.iterdir():
        if entry.is_file() or entry.is_symlink():
            entry.unlink(missing_ok=True)
    try:
        destination_dir.rmdir()
    except OSError:
        marker = destination_dir / ".registration-incomplete"
        if not marker.exists():
            _write_private_json(
                marker,
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "incomplete_registration_do_not_use",
                },
            )


def register_portal_exports(
    source_files: list[Path],
    output_dir: Path,
    *,
    source_origin: str,
) -> Path:
    """Copy locally supplied exports into a new private evidence directory."""

    if not source_files:
        raise PortalExportError("at least one locally supplied source file is required")
    if len(source_files) > 999:
        raise PortalExportError("a registration may contain at most 999 source files")
    canonical_origin = _normalize_origin(source_origin)

    plans = [
        _inspect_source(Path(source), source_index=index)
        for index, source in enumerate(source_files, start=1)
    ]
    identities = {(plan.device, plan.inode) for plan in plans}
    if len(identities) != len(plans):
        raise PortalExportError(
            "the same source file cannot be registered more than once"
        )

    destination_dir = _canonical_new_output_dir(output_dir)
    destination_dir.mkdir(mode=0o700)
    os.chmod(destination_dir, 0o700)

    try:
        artifacts: list[dict[str, Any]] = []
        for index, plan in enumerate(plans, start=1):
            stored_name = (
                f"inps-export-{index:03d}-{plan.sha256[:12]}{plan.stored_suffix}"
            )
            _copy_plan(plan, destination_dir / stored_name, source_index=index)
            artifacts.append(
                {
                    "artifact_id": f"ART-{index:03d}",
                    "stored_name": stored_name,
                    "original_name_sha256": plan.original_name_sha256,
                    "media_type": plan.media_type,
                    "size_bytes": plan.size_bytes,
                    "sha256": plan.sha256,
                }
            )

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "manifest_type": MANIFEST_TYPE,
            "registration_id": f"INPS-EXPORT-{uuid4().hex}",
            "created_at": _utc_now(),
            "source_origin": canonical_origin,
            "safety": dict(SAFE_SAFETY_VALUES),
            "artifacts": artifacts,
        }
        manifest_path = destination_dir / MANIFEST_NAME
        _write_private_json(manifest_path, manifest)
        verify_portal_export(destination_dir)
    except (OSError, PortalExportError):
        _cleanup_failed_registration(destination_dir)
        raise
    return manifest_path


def _strict_object(value: object, *, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PortalExportError(f"{field} must contain exactly the declared fields")
    return value


def _json_object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PortalExportError(f"manifest contains duplicate key: {key}")
        value[key] = item
    return value


def _load_strict_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise PortalExportError("manifest must not be a symlink")
    details = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise PortalExportError("manifest must be a regular file")
    if details.st_size <= 0 or details.st_size > MAX_MANIFEST_SIZE_BYTES:
        raise PortalExportError("manifest size is invalid")
    _require_owner_only(path, directory=False)
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicate_keys,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PortalExportError("manifest is not valid UTF-8 JSON") from exc
    return _strict_object(payload, keys=TOP_LEVEL_KEYS, field="manifest")


def _validate_safety(value: object) -> None:
    safety = _strict_object(value, keys=SAFETY_KEYS, field="safety")
    for field, expected in SAFE_SAFETY_VALUES.items():
        if safety[field] is not expected:
            raise PortalExportError(f"safety.{field} has an unsafe value")


def _hash_file(path: Path) -> str:
    descriptor, _details = _open_regular_source(path)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _validate_artifact(
    value: object, *, index: int, output_dir: Path
) -> tuple[str, Path]:
    artifact = _strict_object(
        value, keys=ARTIFACT_KEYS, field=f"artifacts[{index - 1}]"
    )
    expected_id = f"ART-{index:03d}"
    if artifact["artifact_id"] != expected_id:
        raise PortalExportError(f"artifact ID must be {expected_id}")
    stored_name = artifact["stored_name"]
    if not isinstance(stored_name, str):
        raise PortalExportError("artifact stored_name must be a string")
    match = STORED_NAME_RE.fullmatch(stored_name)
    if match is None or int(match.group("index")) != index:
        raise PortalExportError("artifact stored_name is not collision-safe")
    if artifact["original_name_sha256"] is None or not isinstance(
        artifact["original_name_sha256"], str
    ):
        raise PortalExportError("artifact original-name hash is required")
    if HEX_SHA256_RE.fullmatch(artifact["original_name_sha256"]) is None:
        raise PortalExportError("artifact original-name hash is invalid")
    if (
        not isinstance(artifact["sha256"], str)
        or HEX_SHA256_RE.fullmatch(artifact["sha256"]) is None
    ):
        raise PortalExportError("artifact SHA-256 is invalid")
    if match.group("digest") != artifact["sha256"][:12]:
        raise PortalExportError("artifact stored_name digest does not match SHA-256")
    expected_media = MEDIA_BY_STORED_SUFFIX.get(match.group("suffix"))
    if artifact["media_type"] != expected_media:
        raise PortalExportError("artifact media type does not match its suffix")
    size = artifact["size_bytes"]
    if (
        isinstance(size, bool)
        or not isinstance(size, int)
        or not 0 < size <= MAX_FILE_SIZE_BYTES
    ):
        raise PortalExportError("artifact size is invalid")
    artifact_path = output_dir / stored_name
    if artifact_path.is_symlink():
        raise PortalExportError("registered artifact must not be a symlink")
    details = artifact_path.stat(follow_symlinks=False)
    if not stat.S_ISREG(details.st_mode):
        raise PortalExportError("registered artifact must be a regular file")
    _require_owner_only(artifact_path, directory=False)
    if details.st_size != size:
        raise PortalExportError("registered artifact size does not match manifest")
    if _hash_file(artifact_path) != artifact["sha256"]:
        raise PortalExportError("registered artifact hash does not match manifest")
    with artifact_path.open("rb") as handle:
        head = handle.read(INSPECTION_BYTES)
    source_suffixes = {
        suffix
        for suffix, (media_type, stored_suffix) in MEDIA_BY_SUFFIX.items()
        if media_type == artifact["media_type"]
        and stored_suffix == match.group("suffix")
    }
    validation_suffix = sorted(source_suffixes)[0]
    _validate_content_signature(validation_suffix, head, name=stored_name)
    return stored_name, artifact_path


def verify_portal_export(output_dir: Path) -> dict[str, Any]:
    """Strictly verify a registered export directory and return its manifest."""

    registered_dir = _existing_output_dir(output_dir)
    manifest = _load_strict_manifest(registered_dir / MANIFEST_NAME)
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise PortalExportError("manifest schema_version is unsupported")
    if manifest["manifest_type"] != MANIFEST_TYPE:
        raise PortalExportError("manifest_type is invalid")
    registration_id = manifest["registration_id"]
    if (
        not isinstance(registration_id, str)
        or REGISTRATION_ID_RE.fullmatch(registration_id) is None
    ):
        raise PortalExportError("registration_id is invalid")
    _normalize_timestamp(manifest["created_at"], field="created_at")
    if _normalize_origin(manifest["source_origin"]) != manifest["source_origin"]:
        raise PortalExportError("source_origin is not canonical")
    _validate_safety(manifest["safety"])
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise PortalExportError("manifest must contain at least one artifact")
    expected_names = {MANIFEST_NAME}
    for index, artifact in enumerate(artifacts, start=1):
        stored_name, _artifact_path = _validate_artifact(
            artifact, index=index, output_dir=registered_dir
        )
        if stored_name in expected_names:
            raise PortalExportError("manifest contains duplicate stored names")
        expected_names.add(stored_name)
    actual_names = {entry.name for entry in registered_dir.iterdir()}
    if actual_names != expected_names:
        raise PortalExportError(
            "registered directory contains missing or unexpected files"
        )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser(
        "register", help="Register INPS exports already present in local storage."
    )
    register.add_argument("source_files", nargs="+", type=Path)
    register.add_argument("--output-dir", required=True, type=Path)
    register.add_argument("--source-origin", required=True)

    verify = subparsers.add_parser("verify", help="Verify a registered export.")
    verify.add_argument("output_dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the registrar command-line interface."""

    args = _build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            manifest = verify_portal_export(args.output_dir)
            LOGGER.info(
                "Verified INPS export %s with %d artifact(s).",
                manifest["registration_id"],
                len(manifest["artifacts"]),
            )
            return 0
        manifest_path = register_portal_exports(
            args.source_files,
            args.output_dir,
            source_origin=args.source_origin,
        )
    except (OSError, PortalExportError) as exc:
        LOGGER.error("%s", exc)
        return 1
    LOGGER.info("Registered official INPS export manifest at %s.", manifest_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
