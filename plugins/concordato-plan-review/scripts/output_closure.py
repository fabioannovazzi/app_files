"""Exact whole-output closure for Concordato review runs.

The closure is deterministic because byte identity and file-set equality are
mechanically verifiable. It deliberately says nothing about the accounting,
legal, tax, or going-concern meaning of the enclosed artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vera_assurance import (
    artifact_receipt,
    canonical_json_sha256,
    validate_artifact_receipt,
    write_json,
)

__all__ = [
    "OUTPUT_CLOSURE_NAME",
    "finalize_output_closure",
    "refresh_final_artifact_index",
    "validate_final_artifact_index",
    "validate_output_closure",
]

OUTPUT_CLOSURE_NAME = "workflow_output_closure.json"
OUTPUT_CLOSURE_SCHEMA = "concordato.workflow_output_closure.v1"
OUTPUT_CLOSURE_PHASES = {
    "initial_run_finalization",
    "review_save_finalization",
    "review_apply_finalization",
}
INITIAL_OUTPUT_PATHS = {
    "amount_candidates.csv",
    "assurance_envelope.json",
    "assurance_gates.json",
    "concordato_review_summary.docx",
    "concordato_tie_out_workpaper.xlsx",
    "exact_amount_matches.csv",
    "final_artifacts.json",
    "inventory.json",
    "numeric_evidence_ledger.json",
    "raw_amount_candidates.csv",
    "review_handoff.md",
    "review_packet.md",
    "review_payload.json",
    "reviewed_decisions.json",
    "run_audit.json",
    "run_intake.json",
    "source_pages.json",
    "source_qualifications.json",
    "source_receipts.json",
    "suggested_source_role_recipe.json",
    "ui_decisions.json",
    "workbook_sheets.json",
}
REVIEW_PATH_FIELDS = {
    "revision_paths",
    "target_update_paths",
    "structured_update_paths",
    "native_regeneration_paths",
    "native_regenerated_paths",
    "original_backup_paths",
}


class OutputClosureError(ValueError):
    """Raised when a workflow output boundary is not exactly replayable."""


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OutputClosureError(f"{path.name} must be a JSON object")
    return payload


def _regular_file_set(root: Path) -> set[str]:
    if not root.is_dir() or root.is_symlink():
        raise OutputClosureError("workflow output boundary must be a real directory")
    paths: set[str] = set()
    directories: set[str] = set()
    for path in root.rglob("*"):
        observed = path.lstat()
        if stat.S_ISLNK(observed.st_mode):
            raise OutputClosureError("workflow output boundary contains a symlink")
        if stat.S_ISDIR(observed.st_mode):
            directories.add(path.relative_to(root).as_posix())
            continue
        if not stat.S_ISREG(observed.st_mode):
            raise OutputClosureError("workflow output boundary contains a special file")
        if observed.st_nlink != 1:
            raise OutputClosureError("workflow output boundary contains a hard link")
        paths.add(path.relative_to(root).as_posix())
    expected_directories: set[str] = set()
    for relative_path in paths:
        parent = Path(relative_path).parent
        while parent != Path("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    if directories != expected_directories:
        raise OutputClosureError(
            "workflow output boundary directory set does not close"
        )
    return paths


def _artifact_role(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".csv"}:
        return "workpaper"
    if suffix in {".docx", ".pdf", ".md"}:
        return "report"
    return "output"


def _media_type(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".docx": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        ".json": "application/json",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    }.get(path.suffix.lower(), "application/octet-stream")


def _receipt(output_dir: Path, relative_path: str, index: int) -> dict[str, Any]:
    path = output_dir / relative_path
    return artifact_receipt(
        output_dir,
        path,
        artifact_id=f"final_output.{index:04d}",
        root_id="run",
        role=_artifact_role(path),
        media_type=_media_type(path),
    )


def _canonical_paths(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OutputClosureError("declared_paths must be a list of strings")
    normalized: list[str] = []
    for item in value:
        path = Path(item)
        if (
            not item
            or path.is_absolute()
            or item != path.as_posix()
            or ".." in path.parts
            or "\\" in item
        ):
            raise OutputClosureError("declared output path is not canonical")
        normalized.append(item)
    if normalized != sorted(set(normalized)):
        raise OutputClosureError("declared_paths must be sorted and unique")
    return normalized


def _canonical_dynamic_path(value: object) -> str:
    if not isinstance(value, str):
        raise OutputClosureError("review output path must be text")
    normalized = _canonical_paths([value])
    if value in {OUTPUT_CLOSURE_NAME, "assurance_envelope.json"}:
        raise OutputClosureError("review output cannot replace an assurance control")
    return normalized[0]


def validate_final_artifact_index(output_dir: Path) -> dict[str, Any]:
    """Verify every indexed output against its current unlinked regular file."""

    root = Path(output_dir).resolve()
    payload = _read_object(root / "final_artifacts.json")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        raise OutputClosureError("final_artifacts.outputs must be a list")
    observed: set[str] = set()
    for raw_output in raw_outputs:
        if not isinstance(raw_output, Mapping):
            raise OutputClosureError("final artifact output record is invalid")
        raw_path = raw_output.get("path")
        relative = _canonical_paths([raw_path])[0]
        if relative in observed:
            raise OutputClosureError("final artifact output paths are not unique")
        observed.add(relative)
        path = root / relative
        try:
            stat_result = path.lstat()
        except FileNotFoundError as exc:
            raise OutputClosureError("indexed final artifact is missing") from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(stat_result.st_mode)
            or stat_result.st_nlink != 1
        ):
            raise OutputClosureError("indexed final artifact is linked or non-regular")
        if raw_output.get("size_bytes") != stat_result.st_size:
            raise OutputClosureError("indexed final artifact size is stale")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if raw_output.get("sha256") != digest:
            raise OutputClosureError("indexed final artifact digest is stale")
    if payload.get("final_ready") is not False:
        raise OutputClosureError(
            "deterministic final artifact index cannot claim professional readiness"
        )
    return payload


def refresh_final_artifact_index(output_dir: Path) -> dict[str, Any]:
    """Refresh exact byte receipts after an authorized review transition."""

    root = Path(output_dir).resolve()
    payload = _read_object(root / "final_artifacts.json")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        raise OutputClosureError("final_artifacts.outputs must be a list")
    refreshed: list[dict[str, Any]] = []
    observed: set[str] = set()
    changed = False
    for raw_output in raw_outputs:
        if not isinstance(raw_output, Mapping):
            raise OutputClosureError("final artifact output record is invalid")
        output = dict(raw_output)
        raw_path = output.get("path")
        relative = _canonical_paths([raw_path])[0]
        if relative in observed:
            raise OutputClosureError("final artifact output paths are not unique")
        observed.add(relative)
        path = root / relative
        try:
            stat_result = path.lstat()
        except FileNotFoundError as exc:
            raise OutputClosureError("indexed final artifact is missing") from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(stat_result.st_mode)
            or stat_result.st_nlink != 1
        ):
            raise OutputClosureError("indexed final artifact is linked or non-regular")
        size_bytes = stat_result.st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if output.get("size_bytes") != size_bytes or output.get("sha256") != digest:
            changed = True
        output["size_bytes"] = size_bytes
        output["sha256"] = digest
        refreshed.append(output)
    payload["outputs"] = refreshed
    if payload.get("final_ready") is not False:
        raise OutputClosureError(
            "deterministic final artifact index cannot claim professional readiness"
        )
    if changed:
        write_json(root / "final_artifacts.json", payload)
    return validate_final_artifact_index(root)


def _predecessor_digest(
    payload: Mapping[str, Any],
    *,
    expected_run_id: str,
) -> str:
    """Validate the immutable predecessor record without replaying changed files."""

    required = {
        "schema_version",
        "workflow_id",
        "run_id",
        "phase",
        "self_path",
        "previous_closure_content_sha256",
        "declared_paths",
        "artifact_receipts",
        "assurance_envelope_content_sha256",
        "content_sha256",
    }
    if set(payload) != required:
        raise OutputClosureError("predecessor output closure has invalid fields")
    if (
        payload["schema_version"] != OUTPUT_CLOSURE_SCHEMA
        or payload["workflow_id"] != "concordato-plan-review"
        or payload["run_id"] != expected_run_id
        or payload["phase"] not in OUTPUT_CLOSURE_PHASES
        or payload["self_path"] != OUTPUT_CLOSURE_NAME
    ):
        raise OutputClosureError("predecessor output closure identity is stale")
    content = dict(payload)
    digest = content.pop("content_sha256")
    if not isinstance(digest, str) or digest != canonical_json_sha256(content):
        raise OutputClosureError("predecessor output closure digest is stale")
    return digest


def _authorized_output_paths(root: Path) -> set[str]:
    """Derive the closed output set from workflow contracts, never discovery."""

    authorized = set(INITIAL_OUTPUT_PATHS)
    applied_path = root / "applied_decisions.json"
    if not applied_path.exists():
        return authorized
    applied = _read_object(applied_path)
    authorized.add("applied_decisions.json")
    for field in REVIEW_PATH_FIELDS:
        raw_value = applied.get(field)
        if raw_value is None:
            continue
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for value in values:
            authorized.add(_canonical_dynamic_path(value))
    return authorized


def validate_output_closure(
    output_dir: Path,
    closure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay every output hash and exact declared-vs-physical file-set equality."""

    root = Path(output_dir).resolve()
    payload = (
        dict(closure)
        if closure is not None
        else _read_object(root / OUTPUT_CLOSURE_NAME)
    )
    required = {
        "schema_version",
        "workflow_id",
        "run_id",
        "phase",
        "self_path",
        "previous_closure_content_sha256",
        "declared_paths",
        "artifact_receipts",
        "assurance_envelope_content_sha256",
        "content_sha256",
    }
    if set(payload) != required:
        raise OutputClosureError("workflow output closure has invalid fields")
    if payload["schema_version"] != OUTPUT_CLOSURE_SCHEMA:
        raise OutputClosureError("workflow output closure schema is unsupported")
    if payload["workflow_id"] != "concordato-plan-review":
        raise OutputClosureError("workflow output closure identity is stale")
    if payload["self_path"] != OUTPUT_CLOSURE_NAME:
        raise OutputClosureError("workflow output closure self path is stale")
    if payload["phase"] not in OUTPUT_CLOSURE_PHASES:
        raise OutputClosureError("workflow output closure phase is unsupported")
    if not isinstance(payload["run_id"], str) or not payload["run_id"].strip():
        raise OutputClosureError("workflow output closure run_id is invalid")
    run_intake = _read_object(root / "run_intake.json")
    if payload["run_id"] != run_intake.get("run_id"):
        raise OutputClosureError("workflow output closure run identity is stale")
    previous = payload["previous_closure_content_sha256"]
    if previous is not None and (
        not isinstance(previous, str)
        or len(previous) != 64
        or any(char not in "0123456789abcdef" for char in previous)
    ):
        raise OutputClosureError("previous output closure digest is invalid")

    declared = _canonical_paths(payload["declared_paths"])
    physical = _regular_file_set(root)
    if physical != {*declared, OUTPUT_CLOSURE_NAME}:
        raise OutputClosureError(
            "declared and physical workflow output file sets do not match"
        )
    missing_required = INITIAL_OUTPUT_PATHS - set(declared)
    if missing_required:
        raise OutputClosureError(
            "workflow output closure omits required artifacts: "
            f"{sorted(missing_required)}"
        )
    authorized = _authorized_output_paths(root)
    if set(declared) != authorized:
        raise OutputClosureError(
            "declared workflow outputs do not match the closed workflow allowlist"
        )

    raw_receipts = payload["artifact_receipts"]
    if not isinstance(raw_receipts, list):
        raise OutputClosureError("artifact_receipts must be a list")
    receipts: list[dict[str, Any]] = []
    for raw_receipt in raw_receipts:
        if not isinstance(raw_receipt, Mapping):
            raise OutputClosureError("artifact receipt must be an object")
        try:
            receipts.append(validate_artifact_receipt({"run": root}, raw_receipt))
        except ValueError as exc:
            raise OutputClosureError(str(exc)) from exc
    if [str(item["path"]) for item in receipts] != declared:
        raise OutputClosureError(
            "workflow output receipts do not exactly cover declared paths"
        )

    envelope = _read_object(root / "assurance_envelope.json")
    envelope_digest = envelope.get("content_sha256")
    if (
        not isinstance(envelope_digest, str)
        or envelope_digest != payload["assurance_envelope_content_sha256"]
    ):
        raise OutputClosureError("assurance envelope binding is stale")

    content = {
        "schema_version": OUTPUT_CLOSURE_SCHEMA,
        "workflow_id": "concordato-plan-review",
        "run_id": payload["run_id"],
        "phase": payload["phase"],
        "self_path": OUTPUT_CLOSURE_NAME,
        "previous_closure_content_sha256": previous,
        "declared_paths": declared,
        "artifact_receipts": receipts,
        "assurance_envelope_content_sha256": envelope_digest,
    }
    expected_digest = canonical_json_sha256(content)
    if payload["content_sha256"] != expected_digest:
        raise OutputClosureError("workflow output closure content digest is stale")
    return {**content, "content_sha256": expected_digest}


def finalize_output_closure(
    output_dir: Path,
    *,
    phase: str,
) -> dict[str, Any]:
    """Seal the current output tree after an authorized bounded transition."""

    root = Path(output_dir).resolve()
    if phase not in OUTPUT_CLOSURE_PHASES:
        raise OutputClosureError("workflow output closure phase is unsupported")
    run_intake = _read_object(root / "run_intake.json")
    run_id = run_intake.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise OutputClosureError("run intake identity is missing")
    previous: str | None = None
    closure_path = root / OUTPUT_CLOSURE_NAME
    if closure_path.exists():
        old = _read_object(closure_path)
        previous = _predecessor_digest(old, expected_run_id=run_id)
    declared = sorted(_authorized_output_paths(root))
    missing_required = INITIAL_OUTPUT_PATHS - set(declared)
    if missing_required:
        raise OutputClosureError(
            "cannot finalize an incomplete workflow output set: "
            f"{sorted(missing_required)}"
        )
    physical = _regular_file_set(root)
    physical.discard(OUTPUT_CLOSURE_NAME)
    if physical != set(declared):
        raise OutputClosureError(
            "cannot finalize missing or unexpected workflow output files"
        )
    receipts = [
        _receipt(root, relative_path, index)
        for index, relative_path in enumerate(declared, start=1)
    ]
    envelope = _read_object(root / "assurance_envelope.json")
    envelope_digest = envelope.get("content_sha256")
    if not isinstance(envelope_digest, str):
        raise OutputClosureError("assurance envelope digest is missing")
    content = {
        "schema_version": OUTPUT_CLOSURE_SCHEMA,
        "workflow_id": "concordato-plan-review",
        "run_id": run_id,
        "phase": phase,
        "self_path": OUTPUT_CLOSURE_NAME,
        "previous_closure_content_sha256": previous,
        "declared_paths": declared,
        "artifact_receipts": receipts,
        "assurance_envelope_content_sha256": envelope_digest,
    }
    payload = {**content, "content_sha256": canonical_json_sha256(content)}
    temporary = root / f".{OUTPUT_CLOSURE_NAME}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise OutputClosureError("output closure temporary path already exists")
    write_json(temporary, payload)
    os.replace(temporary, closure_path)
    return validate_output_closure(root)
