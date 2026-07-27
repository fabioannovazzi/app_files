"""Exact workflow-owned file-set closure for Check Entries runs.

The rule is deterministic because file ownership, canonical review-revision
paths, and directory membership are mechanically verifiable. It does not
decide whether evidence is sufficient or whether a reviewer should accept an
entry.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "BASE_OUTPUT_PATHS",
    "validate_initial_output_set",
    "validate_review_successor_output_set",
    "validate_review_transition_output_set",
]

BASE_OUTPUT_PATHS = frozenset(
    {
        "assurance_envelope.json",
        "check_audit.json",
        "check_results.csv",
        "check_results.xlsx",
        "execution_recipe.json",
        "final_artifacts.json",
        "invoice_inventory.json",
        "normalized_entries.csv",
        "numeric_evidence_ledger.json",
        "pdf_inventory.json",
        "prepared_support_facts.csv",
        "review_handoff.md",
        "review_notes.md",
        "review_payload.json",
        "run_intake.json",
        "support_manifest.json",
        "ui_decisions.json",
    }
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_item_id(value: object) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", _clean_text(value))
    return cleaned.strip("-")[:80] or "item"


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
        raise ValueError("Check Entries output root must be a real directory.")
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
                        "Check Entries physical output set cannot contain symlinks."
                    )
                if stat.S_ISDIR(observed.st_mode):
                    directories.add(relative)
                    pending.append(Path(entry.path))
                    continue
                if not stat.S_ISREG(observed.st_mode):
                    raise ValueError(
                        "Check Entries physical output set cannot contain special files."
                    )
                if observed.st_nlink != 1:
                    raise ValueError(
                        "Check Entries physical output set cannot contain hardlinks."
                    )
                files.add(relative)
    return files, directories


def _review_effects(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_effects = value.get("effects")
    if not isinstance(raw_effects, list):
        raise ValueError("Check Entries review successor has no effect perimeter.")
    effects = [effect for effect in raw_effects if isinstance(effect, Mapping)]
    if len(effects) != len(raw_effects):
        raise ValueError("Check Entries review successor effects are malformed.")
    return effects


def _review_paths(effects: Sequence[Mapping[str, Any]]) -> set[str]:
    paths = {"applied_decisions.json"}
    edit_effects: list[Mapping[str, Any]] = []
    for effect in effects:
        if _clean_text(effect.get("action")) != "edit":
            continue
        if _clean_text(effect.get("target_artifact")) != "check_results.csv":
            raise ValueError(
                "Check Entries successor contains an unsupported material edit."
            )
        item_id = _safe_item_id(effect.get("item_id"))
        expected_revision = f"revisions/check_results__{item_id}.txt"
        expected_csv_backup = f"revisions/originals/check_results__{item_id}.csv"
        revision = _clean_text(effect.get("revision_artifact"))
        if revision:
            if revision != expected_revision:
                raise ValueError(
                    "Check Entries successor revision path is not canonical."
                )
            paths.add(revision)
        backup = _clean_text(effect.get("original_artifact_backup"))
        if backup != expected_csv_backup:
            raise ValueError("Check Entries successor original path is not canonical.")
        paths.add(backup)
        edit_effects.append(effect)
    if edit_effects:
        first_item_id = _safe_item_id(edit_effects[0].get("item_id"))
        paths.add(f"revisions/originals/check_results__{first_item_id}.xlsx")
    return paths


def _validate_exact(
    output_dir: Path,
    expected_files: set[str],
    *,
    permit_missing_review_paths: bool,
) -> dict[str, list[str]]:
    actual_files, actual_directories = _physical_tree(output_dir)
    expected_directories = _expected_directories(expected_files)
    unexpected_files = sorted(actual_files - expected_files)
    missing_files = sorted(expected_files - actual_files)
    unexpected_directories = sorted(actual_directories - expected_directories)
    missing_directories = sorted(expected_directories - actual_directories)
    if permit_missing_review_paths:
        missing_files = sorted(
            path for path in missing_files if path in BASE_OUTPUT_PATHS
        )
        missing_directories = []
    if (
        unexpected_files
        or missing_files
        or unexpected_directories
        or missing_directories
    ):
        raise ValueError(
            "Check Entries physical output set does not close; "
            f"missing={missing_files}, unexpected={unexpected_files}, "
            f"missing_directories={missing_directories}, "
            f"unexpected_directories={unexpected_directories}."
        )
    return {
        "physical_paths": sorted(actual_files),
        "physical_directories": sorted(actual_directories),
    }


def validate_initial_output_set(output_dir: Path) -> dict[str, list[str]]:
    """Require the exact initial workflow-owned run tree."""

    return _validate_exact(
        Path(output_dir),
        set(BASE_OUTPUT_PATHS),
        permit_missing_review_paths=False,
    )


def validate_review_transition_output_set(
    output_dir: Path,
    applied_decisions: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Reject foreign paths before a reviewed successor is finalized."""

    expected = set(BASE_OUTPUT_PATHS) | _review_paths(
        _review_effects(applied_decisions)
    )
    return _validate_exact(
        Path(output_dir),
        expected,
        permit_missing_review_paths=True,
    )


def validate_review_successor_output_set(
    output_dir: Path,
    reviewed_decision: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Require exact equality for the accepted post-review run tree."""

    content = reviewed_decision.get("content")
    if not isinstance(content, Mapping):
        raise ValueError("Check Entries review decision content is malformed.")
    expected = set(BASE_OUTPUT_PATHS) | _review_paths(_review_effects(content))
    return _validate_exact(
        Path(output_dir),
        expected,
        permit_missing_review_paths=False,
    )
