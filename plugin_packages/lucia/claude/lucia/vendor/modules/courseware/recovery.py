"""Copy an explicitly selected course without reenrollment or evidence rewriting.

Exact hashes, enrollment IDs and relative paths are mechanical identity checks.
The caller selects an authorized destination; this module grants no filesystem
access and never reads an old path merely because an evidence record names it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["relocate_course", "previous_roots", "resolve_course_path"]

MARKER = "course-relocation.json"


def _ordinary(path: Path, *, directory: bool = False) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Course recovery cannot follow a symlink")
    mode = path.stat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise ValueError("Course recovery requires ordinary files and directories")


def _hash(path: Path) -> str:
    _ordinary(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    _ordinary(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Course recovery record must be an object")
    return value


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".relocation-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({**value, "sha256": _digest(value)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _marker(root: Path) -> dict[str, Any]:
    value = _read(root / MARKER)
    digest = value.pop("sha256", None)
    if (
        _digest(value) != digest
        or value.get("schema") != "mparanza.course_relocation.v1"
        or not isinstance(value.get("previous_roots"), list)
        or not all(
            isinstance(p, str) and Path(p).is_absolute()
            for p in value["previous_roots"]
        )
    ):
        raise ValueError("Course relocation record is invalid; preserve existing work")
    return value


def previous_roots(root: Path) -> tuple[Path, ...]:
    """Return only explicit, completed relocation aliases for this enrollment."""
    if not (root / MARKER).exists():
        return ()
    marker = _marker(root)
    if marker.get("complete") is not True:
        raise ValueError("Course copy is incomplete; resume the same relocation")
    if _read(root / "enrollment.json").get("onboarding_id") != marker["onboarding_id"]:
        raise ValueError("Course relocation belongs to another enrollment")
    return tuple(Path(path) for path in marker["previous_roots"])


def resolve_course_path(root: Path, value: str) -> Path:
    """Hydrate a retained course path without changing its on-disk provenance."""
    path = Path(value)
    if path.is_relative_to(root):
        return path
    for previous in previous_roots(root):
        if path.is_relative_to(previous):
            return root / path.relative_to(previous)
    return path


def _inventory(root: Path) -> tuple[list[str], dict[str, str]]:
    _ordinary(root, directory=True)
    if (root / ".saving").exists():
        raise ValueError("Finish the active course save before copying its progress")
    directories: list[str] = []
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == MARKER:
            continue
        if path.is_symlink():
            raise ValueError("Course recovery cannot follow a symlink")
        if path.is_dir():
            directories.append(relative)
        else:
            files[relative] = _hash(path)
    return directories, files


def relocate_course(source: Path, destination: Path) -> dict[str, Any]:
    """Copy exact retained progress; interrupted copies resume without overwrite.

    The source is never modified. Completed retries preserve newer destination
    work. A missing source can only be recovered from another available copy.
    """
    source = source.expanduser().absolute()
    destination = destination.expanduser().absolute()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("Select a separate course recovery destination")
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("Course recovery cannot follow a symlink")
    saved = _marker(destination) if (destination / MARKER).exists() else None
    if saved is not None:
        if saved["source"] != str(source):
            raise ValueError("Destination belongs to a different course recovery")
        if saved.get("complete") is True:
            previous_roots(destination)
            return {
                "status": "already_relocated",
                "state_root": str(destination),
                "onboarding_id": saved["onboarding_id"],
            }
    elif destination.exists():
        raise ValueError("Preserve the existing destination; select a new folder")
    enrollment = _read(source / "enrollment.json")
    profile = _read(source / "profile.json")
    if (
        not enrollment.get("onboarding_id")
        or profile.get("onboarding_id") != enrollment["onboarding_id"]
    ):
        raise ValueError("Course profile and enrollment do not match")
    directories, files = _inventory(source)
    intent = {
        "schema": "mparanza.course_relocation.v1",
        "source": str(source),
        "previous_roots": list(
            dict.fromkeys([str(source), *map(str, previous_roots(source))])
        ),
        "onboarding_id": enrollment["onboarding_id"],
        "directories": directories,
        "files": files,
        "complete": False,
    }
    if saved is not None and saved != intent:
        raise ValueError(
            "Course changed during recovery; preserve both copies for review"
        )
    if saved is None:
        destination.mkdir(mode=0o700, parents=True)
        _write(destination / MARKER, intent)
    for relative in directories:
        target = destination / relative
        target.mkdir(mode=0o700, exist_ok=True)
        _ordinary(target, directory=True)
    for relative, digest in files.items():
        target = destination / relative
        if target.exists() or target.is_symlink():
            if _hash(target) != digest:
                raise ValueError(
                    "Recovery destination contains changed evidence; preserve it"
                )
            continue
        descriptor, temporary = tempfile.mkstemp(
            prefix=".course-copy-", dir=target.parent
        )
        os.close(descriptor)
        try:
            shutil.copyfile(source / relative, temporary)
            if _hash(Path(temporary)) != digest:
                raise ValueError(
                    "Course source changed while copying; preserve its progress"
                )
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    if _inventory(source) != (directories, files):
        raise ValueError(
            "Course changed while copying; preserve both copies for review"
        )
    _write(destination / MARKER, {**intent, "complete": True})
    return {
        "status": "relocated",
        "state_root": str(destination),
        "onboarding_id": enrollment["onboarding_id"],
    }
