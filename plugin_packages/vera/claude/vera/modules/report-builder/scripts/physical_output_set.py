"""Exact workflow-owned output closure for Report Builder runs.

File ownership, canonical revision paths, and physical entry types are
mechanically verifiable.  This module does not decide whether report
conclusions are professionally sufficient or whether a reviewer should accept
them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "BASE_OUTPUT_PATHS",
    "expected_output_paths",
    "validate_output_set",
]

BASE_OUTPUT_PATHS = frozenset(
    {
        "final_artifacts.json",
        "report.docx",
        "report_analysis.json",
        "report_audit.json",
        "report_draft.md",
        "report_tables.json",
        "report_tables.xlsx",
        "review_handoff.md",
        "review_integrity.json",
        "review_payload.json",
        "run_intake.json",
        "source_index.json",
        "ui_decisions.json",
        "used_recipe.json",
    }
)
INSPECTION_OUTPUT_PATHS = frozenset(
    {
        "inspection.json",
        "suggested_recipe.json",
    }
)
NUMERIC_OUTPUT_PATHS = frozenset(
    {
        "numeric_evidence_ledger.json",
        "source_receipts.json",
    }
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_item_id(value: object) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", _clean_text(value))
    return cleaned.strip("-")[:80] or "item"


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return payload


def _canonical_relative_path(value: object) -> Path:
    text = _clean_text(value)
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or ".." in candidate.parts
        or "\\" in text
        or candidate.as_posix() != text
    ):
        raise ValueError("Report Builder extracted source path is not canonical.")
    return candidate


def _source_root(output_dir: Path, value: str) -> Path:
    """Resolve an absolute or managed run-relative private source root."""

    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    relative = _canonical_relative_path(value)
    run_root = output_dir.resolve()
    while True:
        context_path = run_root / "context.json"
        try:
            observed = context_path.lstat()
        except FileNotFoundError:
            observed = None
        if (
            observed is not None
            and stat.S_ISREG(observed.st_mode)
            and not stat.S_ISLNK(observed.st_mode)
            and observed.st_nlink == 1
        ):
            resolved = (run_root / relative).resolve()
            if resolved == run_root or not resolved.is_relative_to(run_root):
                raise ValueError("Report Builder source root leaves the customer run.")
            return resolved
        parent = run_root.parent
        if parent == run_root:
            raise ValueError("Report Builder portable source root has no customer run.")
        run_root = parent


def _extracted_source_paths(output_dir: Path) -> set[str]:
    source_index = _read_object(output_dir / "source_index.json")
    raw_sources = source_index.get("sources")
    raw_bindings = source_index.get("archive_member_bindings")
    if not isinstance(raw_sources, list) or not isinstance(raw_bindings, list):
        raise ValueError("Report Builder source index has no physical perimeter.")
    bindings = {
        binding.get("member_artifact_id"): binding
        for binding in raw_bindings
        if isinstance(binding, Mapping)
        and isinstance(binding.get("member_artifact_id"), str)
    }
    extracted_root = (output_dir / "extracted_inputs").resolve()
    paths: set[str] = set()
    for source in raw_sources:
        if not isinstance(source, Mapping):
            raise ValueError("Report Builder source index entry is malformed.")
        root_path = source.get("root_path")
        receipt = source.get("receipt")
        if not isinstance(root_path, str) or not isinstance(receipt, Mapping):
            raise ValueError("Report Builder source index entry is malformed.")
        source_root = _source_root(output_dir, root_path)
        if not source_root.is_relative_to(extracted_root):
            continue
        relative_root = source_root.relative_to(output_dir.resolve())
        if (
            len(relative_root.parts) < 2
            or relative_root.parts[0] != "extracted_inputs"
            or not re.fullmatch(r"[A-Za-z0-9._-]+", relative_root.parts[1])
        ):
            raise ValueError("Report Builder extracted source root is not canonical.")
        relative_file = relative_root / _canonical_relative_path(receipt.get("path"))
        binding = bindings.get(source.get("artifact_id"))
        if not isinstance(binding, Mapping) or Path(
            *relative_file.parts[2:]
        ) != _canonical_relative_path(binding.get("member_path")):
            raise ValueError(
                "Report Builder extracted source path is not archive-bound."
            )
        paths.add(relative_file.as_posix())
    return paths


def _expected_directories(paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for value in paths:
        parent = Path(value).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _physical_tree(output_dir: Path) -> tuple[set[str], set[str]]:
    root = Path(output_dir)
    root_stat = root.lstat()
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("Report Builder output root must be a real directory.")
    files: set[str] = set()
    directories: set[str] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                observed = entry.stat(follow_symlinks=False)
                relative = Path(entry.path).relative_to(root).as_posix()
                if stat.S_ISLNK(observed.st_mode):
                    raise ValueError(
                        "Report Builder physical output set cannot contain symlinks."
                    )
                if stat.S_ISDIR(observed.st_mode):
                    directories.add(relative)
                    pending.append(Path(entry.path))
                    continue
                if not stat.S_ISREG(observed.st_mode):
                    raise ValueError(
                        "Report Builder physical output set cannot contain special "
                        "files."
                    )
                if observed.st_nlink != 1:
                    raise ValueError(
                        "Report Builder physical output set cannot contain hardlinks."
                    )
                files.add(relative)
    return files, directories


def _review_paths(
    output_dir: Path,
    applied: Mapping[str, Any],
    *,
    permit_review_transition: bool,
) -> set[str]:
    raw_effects = applied.get("effects")
    if not isinstance(raw_effects, list):
        raise ValueError("Report Builder review successor has no effect perimeter.")
    effects = [effect for effect in raw_effects if isinstance(effect, Mapping)]
    if len(effects) != len(raw_effects):
        raise ValueError("Report Builder review successor effects are malformed.")
    edit_effects = [
        effect for effect in effects if _clean_text(effect.get("action")) == "edit"
    ]
    paths = {"applied_decisions.json"}
    for effect in effects:
        revision = _clean_text(effect.get("revision_artifact"))
        if effect not in edit_effects:
            if revision:
                raise ValueError(
                    "Report Builder non-edit effect cannot own a revision artifact."
                )
            continue
        if _clean_text(effect.get("target_artifact")) != "report.docx":
            raise ValueError(
                "Report Builder successor contains an unsupported material edit."
            )
        expected_revision = (
            f"revisions/report__{_safe_item_id(effect.get('item_id'))}.txt"
        )
        if revision != expected_revision:
            raise ValueError("Report Builder successor revision path is not canonical.")
        paths.add(expected_revision)
    raw_backups = applied.get("original_backup_paths")
    if not isinstance(raw_backups, list) or not all(
        isinstance(path, str) for path in raw_backups
    ):
        raise ValueError("Report Builder successor backup perimeter is malformed.")
    expected_backups = (
        [
            "revisions/originals/"
            f"report__{_safe_item_id(edit_effects[0].get('item_id'))}.docx"
        ]
        if edit_effects
        else []
    )
    allowed_backups = (
        [[], expected_backups] if permit_review_transition else [expected_backups]
    )
    if raw_backups not in allowed_backups:
        raise ValueError("Report Builder successor backup path is not canonical.")
    paths.update(raw_backups)
    raw_history = applied.get("review_history_paths", [])
    if (
        not isinstance(raw_history, list)
        or not all(isinstance(path, str) for path in raw_history)
        or len(raw_history) != len(set(raw_history))
    ):
        raise ValueError("Report Builder review history perimeter is malformed.")
    for history_path in raw_history:
        match = re.fullmatch(
            r"revisions/history/application__([0-9a-f]{64})\.json",
            history_path,
        )
        if match is None:
            raise ValueError("Report Builder review history path is not canonical.")
        history = _read_object(output_dir / history_path)
        expected_fields = {
            "schema_version",
            "archived_at",
            "predecessor_checkpoint",
            "predecessor_integrity",
            "run_intake",
            "review_payload",
            "ui_decisions",
            "applied_decisions",
            "final_artifacts",
            "content_sha256",
        }
        content = dict(history)
        digest = content.pop("content_sha256", None)
        replayed = hashlib.sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if (
            set(history) != expected_fields
            or history.get("schema_version") != "report_builder.review_history_entry.v2"
            or digest != replayed
            or match.group(1) != replayed
        ):
            raise ValueError("Report Builder review history entry is stale.")
        paths.add(history_path)
    raw_retained = applied.get("retained_review_paths", [])
    if (
        not isinstance(raw_retained, list)
        or not all(isinstance(path, str) for path in raw_retained)
        or len(raw_retained) != len(set(raw_retained))
    ):
        raise ValueError("Report Builder retained review perimeter is malformed.")
    for retained_path in raw_retained:
        if (
            re.fullmatch(
                r"revisions/(?:report__[A-Za-z0-9._-]+\.txt|"
                r"originals/report__[A-Za-z0-9._-]+\.docx)",
                retained_path,
            )
            is None
        ):
            raise ValueError("Report Builder retained review path is not canonical.")
        paths.add(retained_path)
    return paths


def expected_output_paths(
    output_dir: Path,
    *,
    permit_review_transition: bool = False,
) -> set[str]:
    """Return the exact trusted file profile for the persisted run state."""

    root = Path(output_dir)
    paths = set(BASE_OUTPUT_PATHS)
    present_inspection = {
        name for name in INSPECTION_OUTPUT_PATHS if (root / name).exists()
    }
    if present_inspection and present_inspection != set(INSPECTION_OUTPUT_PATHS):
        raise ValueError("Report Builder inspection output pair is incomplete.")
    paths.update(present_inspection)
    present_numeric = {name for name in NUMERIC_OUTPUT_PATHS if (root / name).exists()}
    if present_numeric and present_numeric != set(NUMERIC_OUTPUT_PATHS):
        raise ValueError("Report Builder numeric output pair is incomplete.")
    paths.update(present_numeric)
    if (root / "extracted_inputs").exists():
        paths.update(_extracted_source_paths(root))
    applied_path = root / "applied_decisions.json"
    if applied_path.exists():
        paths.update(
            _review_paths(
                root,
                _read_object(applied_path),
                permit_review_transition=permit_review_transition,
            )
        )
    return paths


def validate_output_set(
    output_dir: Path,
    *,
    permit_missing_integrity: bool = False,
    permit_review_transition: bool = False,
) -> dict[str, list[str]]:
    """Require exact equality with the trusted current run profile."""

    root = Path(output_dir)
    expected_files = expected_output_paths(
        root,
        permit_review_transition=permit_review_transition,
    )
    actual_files, actual_directories = _physical_tree(root)
    expected_directories = _expected_directories(expected_files)
    unexpected_files = sorted(actual_files - expected_files)
    missing_files = sorted(expected_files - actual_files)
    unexpected_directories = sorted(actual_directories - expected_directories)
    missing_directories = sorted(expected_directories - actual_directories)
    if permit_missing_integrity:
        missing_files = [
            path for path in missing_files if path != "review_integrity.json"
        ]
    if (
        unexpected_files
        or missing_files
        or unexpected_directories
        or missing_directories
    ):
        raise ValueError(
            "Report Builder physical output set does not close; "
            f"missing={missing_files}, unexpected={unexpected_files}, "
            f"missing_directories={missing_directories}, "
            f"unexpected_directories={unexpected_directories}."
        )
    return {
        "physical_paths": sorted(actual_files),
        "physical_directories": sorted(actual_directories),
    }
