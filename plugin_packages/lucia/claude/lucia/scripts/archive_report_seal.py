"""Extend an Archive seal only for its automatically owned report artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from archive_report_store import atomic_bytes, atomic_json, canonical, file_digest

__all__ = ["checkpoint", "reseal", "retain_manifest"]
FILES = {
    "model_data_report.json": "application/json",
    "model_data_report.md": "text/markdown",
    "model_data_receipt_request.json": "application/json",
    "model_data_receipt.json": "application/json",
    "model_data_receipt.html": "text/html",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).rstrip(b"\n")).hexdigest()


def _identity(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Archive artifact must be an ordinary unlinked file")
    return path.stat().st_size, file_digest(path)


def _check(root: Path, manifest: dict[str, Any], *, include_report: bool) -> None:
    body = {key: value for key, value in manifest.items() if key != "content_sha256"}
    if _digest(body) != manifest["content_sha256"]:
        raise ValueError("Archive artifact manifest seal is invalid")
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    if any(
        manifest[key] != run[key]
        for key in ("run_id", "workflow_id", "client_id", "engagement_id")
    ):
        raise ValueError("Artifact manifest belongs to another Archive run")
    output = root / "outputs"
    declared = {item["path"]: item for item in manifest["artifacts"]}
    physical = set()
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ValueError("Archive outputs cannot contain symbolic links")
        if path.is_dir():
            continue
        relative = path.relative_to(output).as_posix()
        physical.add(relative)
        if not include_report and relative in FILES:
            continue
        record = declared.get(relative)
        if record is None or _identity(path) != (
            record["byte_count"],
            record["sha256"],
        ):
            raise ValueError("Professional artifacts changed after Archive sealing")
    expected = set(declared)
    if not include_report:
        physical -= FILES.keys()
        expected -= FILES.keys()
    if physical != expected:
        raise ValueError("Archive artifact population changed after sealing")


def retain_manifest(root: Path, manifest: dict[str, Any]) -> None:
    """Retain a verified receipt so existing handoffs survive metadata revisions."""
    _check(root, manifest, include_report=False)
    current_path = root / "artifact_manifest.json"
    _identity(current_path)
    current = current_path.read_bytes()
    content = current if json.loads(current) == manifest else canonical(manifest)
    history = root / "artifact-manifest-history"
    if history.is_symlink():
        raise ValueError("Artifact receipt history cannot be a symbolic link")
    path = history / f"{manifest['content_sha256']}.json"
    if path.exists() or path.is_symlink():
        _identity(path)
        if json.loads(path.read_bytes()) != manifest:
            raise ValueError("Retained artifact receipt differs from its digest")
        return
    atomic_bytes(path, content)


def checkpoint(root: Path) -> dict[str, Any] | None:
    """Validate all sealed bytes before the reporting subsystem changes its files."""
    path = root / "artifact_manifest.json"
    if not path.is_file():
        return None
    pending = root / "reporting/seal-update.json"
    if pending.is_file():
        baseline = json.loads(pending.read_text(encoding="utf-8"))
        _check(root, baseline, include_report=False)
        retain_manifest(root, baseline)
        return baseline
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _check(root, manifest, include_report=True)
    retain_manifest(root, manifest)
    atomic_json(pending, manifest)
    return manifest


def reseal(root: Path, baseline: dict[str, Any] | None) -> None:
    """Preserve every professional record and verify it again before committing."""
    if baseline is None:
        return
    _check(root, baseline, include_report=False)
    artifacts = [item for item in baseline["artifacts"] if item["path"] not in FILES]
    for name, mime in FILES.items():
        path = root / "outputs" / name
        if not path.exists():
            continue
        size, sha256 = _identity(path)
        artifacts.append(
            {
                "artifact_id": "disclosure." + name.replace("_", "-"),
                "path": name,
                "purpose": "Record this Archive run's measured model-data boundary.",
                "audience": "review",
                "media_type": mime,
                "byte_count": size,
                "sha256": sha256,
            }
        )
    body = {key: value for key, value in baseline.items() if key != "content_sha256"}
    body["artifacts"] = sorted(artifacts, key=lambda item: item["path"])
    atomic_json(
        root / "artifact_manifest.json", {**body, "content_sha256": _digest(body)}
    )
    (root / "reporting/seal-update.json").unlink(missing_ok=True)
