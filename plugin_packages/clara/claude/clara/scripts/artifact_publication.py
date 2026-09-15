"""Publish complete artifact snapshots through one atomic current-generation pointer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from case_store import atomic_text

__all__ = ["publish_snapshot", "verify_snapshot"]


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _member(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise ValueError("Media manifest contains an unsafe output path")
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Media output escapes its publication root")
    return path


def publish_snapshot(
    root: Path,
    work: Path,
    *,
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    manifest_name: str,
    pointer_name: str,
    status: str,
) -> dict[str, Any]:
    """Copy verified artifacts before committing a current-generation pointer."""
    destination = work / "published"
    destination.mkdir()
    for record in records:
        source = _member(root, record["path"])
        target = _member(destination, record["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if _hash(target) != record["sha256"] or _hash(source) != record["sha256"]:
            raise ValueError("Media artifact changed during publication")
    manifest_path = destination / manifest_name
    atomic_text(
        manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    pointer = {
        "schema_version": 1,
        "status": status,
        "manifest": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": _hash(manifest_path),
    }
    atomic_text(root / pointer_name, json.dumps(pointer, indent=2) + "\n")
    return pointer


def verify_snapshot(
    root: Path, *, pointer_name: str, status: str, output_field: tuple[str, ...]
) -> dict[str, Any]:
    """Verify the complete published snapshot; semantic review remains separate."""
    pointer_hash = _hash(root / pointer_name)
    pointer = json.loads((root / pointer_name).read_text(encoding="utf-8"))
    if pointer.get("status") != status:
        raise ValueError("No completed current media generation")
    manifest_path = _member(root, pointer["manifest"])
    if _hash(manifest_path) != pointer["manifest_sha256"]:
        raise ValueError("Published media manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest
    for field in output_field:
        records = records[field]
    for record in records:
        if _hash(_member(manifest_path.parent, record["path"])) != record["sha256"]:
            raise ValueError("Published media output changed")
    if _hash(root / pointer_name) != pointer_hash:
        raise ValueError("Current media generation changed during verification")
    return {
        **pointer,
        "generation_directory": str(manifest_path.parent),
        "identity_verified": True,
    }
