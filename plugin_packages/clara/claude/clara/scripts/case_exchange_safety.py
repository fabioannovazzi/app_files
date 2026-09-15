"""Preflight untrusted case exchanges before any filesystem mutation.

Fixed path and size rules protect the user's filesystem; no semantic case
judgment is performed here.
"""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from zipfile import ZipFile

__all__ = ["load_exchange", "validate_destinations"]

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 10_000
EXCHANGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _relative(value: Any) -> PurePosixPath:
    """Require a portable, non-aliased relative archive path."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("unsafe exchange path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(part.endswith((".", " ")) or ":" in part for part in path.parts)
        or any(PureWindowsPath(part).is_reserved() for part in path.parts)
    ):
        raise ValueError(f"unsafe exchange path: {value}")
    return path


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate exchange field: {key}")
        result[key] = value
    return result


def load_exchange(package_path: Path) -> dict[str, Any]:
    """Validate all archive names and declared destinations before reading files."""
    if package_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("case exchange exceeds archive size limit")
    with ZipFile(package_path) as archive:
        members = archive.infolist()
        if (
            len(members) > MAX_MEMBERS
            or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES
        ):
            raise ValueError("case exchange exceeds expanded size/member limit")
        names: set[str] = set()
        for member in members:
            path = _relative(
                member.filename.rstrip("/") if member.is_dir() else member.filename
            )
            key = path.as_posix().casefold()
            if key in names or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError("duplicate or symbolic-link exchange member")
            names.add(key)
        try:
            info = archive.getinfo("case_update.json")
        except KeyError as exc:
            raise ValueError("case update package is missing case_update.json") from exc
        if info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("case exchange manifest exceeds size limit")
        payload = json.loads(archive.read(info), object_pairs_hook=_unique_object)
        if not isinstance(payload, dict):
            raise ValueError("case update package must contain a JSON object")
        identifier = payload.get("exchange_id")
        if (
            not isinstance(identifier, str)
            or not EXCHANGE_ID.fullmatch(identifier)
            or PureWindowsPath(identifier).is_reserved()
        ):
            raise ValueError("unsafe exchange_id: expected one portable identifier")
        destinations: dict[str, str] = {}
        for field in ("included_files", "included_lineage_files"):
            records = payload.get(field, [])
            if not isinstance(records, list):
                raise ValueError(f"invalid exchange {field}")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"invalid exchange {field} record")
                source = _relative(record.get("archive_path"))
                if source.as_posix() not in archive.namelist():
                    raise ValueError(f"missing exchange member: {source}")
                target = (
                    _relative(record.get("relative_path"))
                    if field == "included_files"
                    else PurePosixPath("lineage/artifacts") / source.name
                )
                key = target.as_posix().casefold()
                if key in destinations and destinations[key] != source.as_posix():
                    raise ValueError(f"colliding exchange destination: {target}")
                destinations[key] = source.as_posix()
        return payload


def validate_destinations(case_dir: Path, payload: dict[str, Any]) -> Path:
    """Reject symlink ancestors before snapshot, extraction or rollback."""
    case_root = case_dir.resolve()
    root = case_root / "exchange_imports" / payload["exchange_id"]
    paths = [root]
    for field in ("included_files", "included_lineage_files"):
        for record in payload.get(field, []):
            relative = (
                _relative(record["relative_path"])
                if field == "included_files"
                else PurePosixPath("lineage/artifacts")
                / _relative(record["archive_path"]).name
            )
            paths.append(root.joinpath(*relative.parts))
    if root.exists():
        paths.extend(root.rglob("*"))
    for path in paths:
        for candidate in (path, *path.parents):
            if candidate == case_root:
                break
            if candidate.is_symlink():
                raise ValueError(f"symbolic-link exchange destination: {candidate}")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("exchange destination escapes root")
    return root
