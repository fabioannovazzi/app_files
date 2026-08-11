"""Canonical serialization and local artifact receipts for Vera."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

__all__ = [
    "SerializationValidationError",
    "artifact_receipt",
    "canonical_json_bytes",
    "canonical_json_sha256",
    "file_snapshot",
    "validate_artifact_receipt",
    "write_json",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SerializationValidationError(ValueError):
    """Raised when a canonical value or artifact receipt is invalid."""


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SerializationValidationError(f"{label} must be non-empty trimmed text")
    return value


def _identifier(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise SerializationValidationError(f"{label} must be a canonical identifier")
    return text


def _validate_structured_value(value: Any, *, label: str = "value") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise SerializationValidationError(
            f"{label} contains a binary floating-point value"
        )
    if isinstance(value, Decimal):
        raise SerializationValidationError(
            f"{label} contains Decimal; serialize it as canonical text"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SerializationValidationError(f"{label} contains a non-text key")
            _validate_structured_value(item, label=f"{label}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _validate_structured_value(item, label=f"{label}[{index}]")
        return
    raise SerializationValidationError(
        f"{label} contains unsupported type {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing."""

    _validate_structured_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    """Return the digest of :func:`canonical_json_bytes`."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_json(path: Path, value: Mapping[str, Any]) -> Path:
    """Write stable, human-readable JSON with LF termination."""

    _validate_structured_value(value)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def file_snapshot(path: Path) -> tuple[int, str]:
    """Return byte count and SHA-256 from one stable regular-file snapshot."""

    source = Path(path)
    if source.is_symlink():
        raise SerializationValidationError(f"artifact cannot be a symlink: {source}")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with source.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SerializationValidationError(
                    f"artifact must be a regular file: {source}"
                )
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                byte_count += len(chunk)
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except FileNotFoundError as exc:
        raise SerializationValidationError(
            f"artifact does not exist: {source}"
        ) from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after or byte_count != after.st_size:
        raise SerializationValidationError(
            f"artifact changed while it was read: {source}"
        )
    return byte_count, digest.hexdigest()


def _relative_file(root: Path, path: Path) -> tuple[Path, Path]:
    resolved_root = Path(root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise SerializationValidationError("artifact must stay inside its root")
    if not resolved.is_file() or resolved.is_symlink():
        raise SerializationValidationError(
            "artifact must be a regular non-symlink file"
        )
    return resolved_root, resolved


def artifact_receipt(
    root: Path,
    path: Path,
    *,
    artifact_id: str,
    role: str,
    root_id: str = "run",
    media_type: str | None = None,
) -> dict[str, Any]:
    """Build a source- or output-artifact receipt."""

    resolved_root, resolved = _relative_file(root, path)
    byte_count, digest = file_snapshot(resolved)
    receipt: dict[str, Any] = {
        "schema_version": "vera.artifact_receipt.v1",
        "artifact_id": _identifier(artifact_id, label="artifact_id"),
        "root_id": _identifier(root_id, label="root_id"),
        "role": _text(role, label="role"),
        "path": resolved.relative_to(resolved_root).as_posix(),
        "byte_count": byte_count,
        "sha256": digest,
    }
    if media_type is not None:
        receipt["media_type"] = _text(media_type, label="media_type")
    return receipt


def validate_artifact_receipt(
    root: Path | Mapping[str, Path],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an artifact receipt against the current local bytes."""

    required = {
        "schema_version",
        "artifact_id",
        "root_id",
        "role",
        "path",
        "byte_count",
        "sha256",
    }
    optional = {"media_type"}
    missing = required - set(receipt)
    unexpected = set(receipt) - required - optional
    if missing or unexpected:
        raise SerializationValidationError(
            f"artifact receipt fields invalid; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    if receipt["schema_version"] != "vera.artifact_receipt.v1":
        raise SerializationValidationError("unsupported artifact receipt schema")
    _identifier(receipt["artifact_id"], label="artifact_id")
    root_id = _identifier(receipt["root_id"], label="root_id")
    _text(receipt["role"], label="role")
    relative = Path(_text(receipt["path"], label="path"))
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(receipt["path"]):
        raise SerializationValidationError("artifact receipt path must be canonical")
    if (
        not isinstance(receipt["byte_count"], int)
        or isinstance(receipt["byte_count"], bool)
        or receipt["byte_count"] < 0
    ):
        raise SerializationValidationError("byte_count must be a non-negative integer")
    digest = _text(receipt["sha256"], label="sha256")
    if _SHA256_RE.fullmatch(digest) is None:
        raise SerializationValidationError("sha256 must be lowercase hexadecimal")
    if "media_type" in receipt:
        _text(receipt["media_type"], label="media_type")
    if isinstance(root, Mapping):
        if root_id not in root:
            raise SerializationValidationError(
                f"artifact root {root_id!r} is not available"
            )
        selected_root = Path(root[root_id])
    else:
        selected_root = Path(root)
    resolved_root = selected_root.resolve()
    unresolved_path = resolved_root / relative
    if unresolved_path.is_symlink():
        raise SerializationValidationError("artifact receipt path cannot be a symlink")
    try:
        path = unresolved_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SerializationValidationError(
            f"artifact does not exist: {unresolved_path}"
        ) from exc
    if not path.is_relative_to(resolved_root):
        raise SerializationValidationError("artifact receipt escapes its root")
    actual_count, actual_digest = file_snapshot(path)
    if receipt["byte_count"] != actual_count or digest != actual_digest:
        raise SerializationValidationError(
            "artifact receipt does not match current bytes"
        )
    return dict(receipt)
