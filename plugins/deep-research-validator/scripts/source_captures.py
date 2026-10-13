"""Preserve resource IDs and immutable evidence bytes, without judging authority."""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from vera_assurance.serialization import exclusive_file_lock

__all__ = ["persist_captures", "write_inventory_snapshot", "write_current_inventory"]

MANIFEST = "source_capture_manifest.json"


def _key(record: dict[str, Any]) -> str:
    """Exact resource identity is bookkeeping; legal identity remains model-led."""
    kind = record.get("kind")
    locator = (
        record.get("requested_url") or record.get("url")
        if kind == "url"
        else record.get("path")
    )
    if kind not in {"url", "file"} or not isinstance(locator, str) or not locator:
        raise ValueError("A source requires its actual URL or file locator")
    return json.dumps([kind, locator], ensure_ascii=False)


def _capture_id(record: dict[str, Any]) -> str:
    identity = {
        key: record.get(key)
        for key in (
            "source_bytes_sha256",
            "extracted_text_sha256",
            "capture_scope",
            "status",
        )
    }
    return (
        "capture-"
        + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    )


def _immutable(path: Path, raw: bytes, base: Path) -> None:
    if not path.resolve().is_relative_to(base):
        raise ValueError("Source capture escapes its evidence directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError(f"Immutable source capture changed: {path.name}")


def _load_manifest(base: Path) -> dict[str, Any]:
    path = base / MANIFEST
    if path.exists():
        if not path.resolve().is_relative_to(base):
            raise ValueError("Source manifest escapes its evidence directory")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != "1.0"
            or not isinstance(manifest.get("sources"), list)
        ):
            raise ValueError("Invalid persistent source manifest")
    else:
        manifest = {"schema_version": "1.0", "sources": []}
        previous = base / "source_inventory.json"
        if previous.exists():
            if not previous.resolve().is_relative_to(base):
                raise ValueError(
                    "Previous source inventory escapes its evidence directory"
                )
            for record in json.loads(previous.read_text(encoding="utf-8")).get(
                "sources", []
            ):
                old = dict(record)
                history = old.pop("capture_history", [])
                if old.get("captured_text_path") and not history:
                    old["capture_id"] = _capture_id(old)
                    history = [dict(old)]
                manifest["sources"].append(
                    {
                        "key": _key(old),
                        "source_id": old["source_id"],
                        "capture_history": history,
                        "last_record": old,
                    }
                )
            manifest["history_scope"] = (
                "Imported latest inventory only; earlier unretained inspections cannot be reconstructed."
            )
    keys, identifiers = set(), set()
    for entry in manifest["sources"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("key"), str)
            or not isinstance(entry.get("source_id"), str)
            or not isinstance(entry.get("capture_history"), list)
            or not isinstance(entry.get("last_record"), dict)
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("capture_id"), str)
                for item in entry.get("capture_history", [])
            )
        ):
            raise ValueError("Invalid persistent source identity")
        if entry["key"] in keys or entry["source_id"] in identifiers:
            raise ValueError("Duplicate persistent source identity")
        keys.add(entry["key"])
        identifiers.add(entry["source_id"])
    return manifest


def persist_captures(
    records: list[dict[str, Any]],
    capture_dir: Path,
    base_dir: Path,
    *,
    lock_held: bool = False,
) -> list[dict[str, Any]]:
    """Append observations and reuse exact bytes; never recycle an existing ID."""
    base = base_dir.resolve()
    if not capture_dir.resolve().is_relative_to(base):
        raise ValueError("Source captures must remain in the inventory directory")
    base.mkdir(parents=True, exist_ok=True)
    lock = base / ".source_capture_manifest.lock"
    # The shared OS lock is released after crashes, allowing research to resume.
    with nullcontext() if lock_held else exclusive_file_lock(lock):
        manifest = _load_manifest(base)
        entries = {entry["key"]: entry for entry in manifest["sources"]}
        used = {entry["source_id"] for entry in entries.values()}
        canonical: dict[str, tuple[str, str]] = {}
        for entry in entries.values():
            for capture in entry["capture_history"]:
                if capture.get("extracted_text_sha256") and capture.get(
                    "captured_text_path"
                ):
                    canonical.setdefault(
                        capture["extracted_text_sha256"],
                        (entry["source_id"], capture["captured_text_path"]),
                    )
        out, seen = [], set()
        next_id = 1
        for raw_record in records:
            record = dict(raw_record)
            text = str(record.pop("_captured_text", "") or "")
            original = record.pop("_captured_bytes", None)
            key = _key(record)
            entry = entries.get(key)
            if entry is None:
                while f"source-{next_id:03d}" in used:
                    next_id += 1
                entry = {
                    "key": key,
                    "source_id": f"source-{next_id:03d}",
                    "capture_history": [],
                    "last_record": {},
                }
                used.add(entry["source_id"])
                entries[key] = entry
                manifest["sources"].append(entry)
            record["source_id"] = entry["source_id"]
            record["observed_at"] = datetime.now(timezone.utc).isoformat()
            if isinstance(original, bytes):
                original_digest = hashlib.sha256(original).hexdigest()
                if original_digest != record.get("source_bytes_sha256"):
                    raise ValueError(
                        "Original source bytes differ from their recorded digest"
                    )
                original_path = (
                    capture_dir / "originals" / f"bytes-{original_digest}.bin"
                )
                _immutable(original_path, original, base)
                record["captured_original_path"] = (
                    original_path.resolve().relative_to(base).as_posix()
                )
            if text:
                encoded = text.encode("utf-8")
                digest = hashlib.sha256(encoded).hexdigest()
                if digest != record.get("extracted_text_sha256"):
                    raise ValueError("Extracted text differs from its recorded digest")
                text_path = capture_dir / f"text-{digest}.txt"
                # Writing bytes fixes newline identity across Linux, macOS and Windows.
                _immutable(text_path, encoded, base)
                record["captured_text_path"] = (
                    text_path.resolve().relative_to(base).as_posix()
                )
                previous = canonical.get(digest)
                if previous and previous[0] != record["source_id"]:
                    record["duplicate_content_of_source_id"] = previous[0]
                    record["capture_reused"] = True
                canonical.setdefault(
                    digest, (record["source_id"], record["captured_text_path"])
                )
            if text or isinstance(original, bytes):
                record["capture_id"] = _capture_id(record)
                if record["capture_id"] not in {
                    item["capture_id"] for item in entry["capture_history"]
                }:
                    entry["capture_history"].append(dict(record))
            entry["last_record"] = dict(record)
            record["capture_history"] = list(entry["capture_history"])
            record["inspected_this_pass"] = True
            if key in seen:
                out = [item for item in out if item["source_id"] != record["source_id"]]
            out.append(record)
            seen.add(key)
        for key, entry in entries.items():
            if key not in seen:
                out.append(
                    {
                        **entry["last_record"],
                        "capture_history": list(entry["capture_history"]),
                        "inspected_this_pass": False,  # nosec B105
                    }
                )
        temporary = base / f".source-manifest-{uuid4().hex}.tmp"
        temporary.write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
        )
        temporary.replace(base / MANIFEST)
        return out


def write_inventory_snapshot(base: Path, raw: bytes) -> Path:
    """Retain each exact inventory so prior capture references remain resolvable."""
    path = base / f"source_inventory-{hashlib.sha256(raw).hexdigest()}.json"
    _immutable(path, raw, base.resolve())
    return path


def write_current_inventory(base: Path, raw: bytes) -> Path:
    """Atomically advance the current pointer after retaining its exact snapshot."""
    path = base / "source_inventory.json"
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("Current inventory escapes its evidence directory")
    temporary = base / f".source-inventory-{uuid4().hex}.tmp"
    temporary.write_bytes(raw)
    temporary.replace(path)
    return path
