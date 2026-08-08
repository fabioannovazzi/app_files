#!/usr/bin/env python3
"""Record a selected Creative Production direction or explicit internal fallback."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

from PIL import Image
from workflow_core import (
    atomic_copy_file,
    atomic_write_json,
    canonical_digest,
    file_digest,
    load_json,
    recompute_contribution_digest,
    utc_now,
    validate_input_integrity,
    validate_schema,
    workflow_lock,
)

__all__ = ["record_creative_direction_decision", "main"]

LOGGER = logging.getLogger(__name__)


def _verify_handoff(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    workbench = load_json(root / "content_workbench.json")
    version = int(workbench["version"])
    handoff = load_json(root / "creative-direction" / f"handoff-v{version:03d}.json")
    validate_schema(handoff, "creative_direction_handoff.schema.json")
    stable = {key: value for key, value in handoff.items() if key != "handoff_digest"}
    if canonical_digest(stable) != handoff["handoff_digest"]:
        raise ValueError("Creative direction handoff digest mismatch")
    expected_binding = {
        "input_digest": workbench["input_digest"],
        "contribution_digest": recompute_contribution_digest(root),
        "visual_story_digest": canonical_digest(
            workbench["contribution"]["visual_story"]
        ),
    }
    if handoff["binding"] != expected_binding:
        raise ValueError("Creative direction handoff is stale")
    return workbench, handoff


def _snapshot_directions(
    root: Path,
    directions: list[dict[str, Any]],
    *,
    version: int,
) -> list[dict[str, Any]]:
    item_ids = [row["item_id"] for row in directions]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Creative Production result repeats an item id")
    references = root / "creative-direction" / "references"
    references.mkdir(parents=True, exist_ok=True)
    if references.is_symlink() or not references.resolve().is_relative_to(root):
        raise ValueError("Creative Production reference directory is unsafe")
    directory = references / f"v{version:03d}"
    if directory.exists():
        raise ValueError("Creative Production direction snapshots already exist")
    prepared: list[tuple[dict[str, Any], Path, Path]] = []
    for index, row in enumerate(directions, start=1):
        source = Path(row["image_path"]).expanduser()
        source_resolved = source.resolve(strict=True)
        if source.is_symlink() or not source_resolved.is_file():
            raise ValueError("Creative Production reference must be a regular file")
        safe_item = re.sub(r"[^A-Za-z0-9_.-]+", "-", row["item_id"]).strip("-.")
        suffix = source_resolved.suffix.lower() or ".png"
        target = directory / f"direction-{index:02d}-{safe_item or 'item'}{suffix}"
        prepared.append((row, source_resolved, target))
    target_names = [target.name for _, _, target in prepared]
    if len(target_names) != len(set(target_names)):
        raise ValueError("Creative Production direction snapshot names collide")

    directory.mkdir()
    snapshots: list[dict[str, Any]] = []
    try:
        for row, source_resolved, target in prepared:
            atomic_copy_file(source_resolved, target)
            with Image.open(target) as image:
                if image.size != (1080, 1350):
                    raise ValueError(
                        "Creative Production reference must use the 1080 x 1350 target"
                    )
                image.verify()
            snapshots.append(
                {
                    "item_id": row["item_id"],
                    "item_revision": row["item_revision"],
                    "title": row["title"],
                    "snapshot_path": target.relative_to(root).as_posix(),
                    "sha256": file_digest(target),
                    "size_bytes": target.stat().st_size,
                }
            )
    except (OSError, ValueError):
        for target in directory.iterdir():
            if target.is_file() and not target.is_symlink():
                target.unlink()
        directory.rmdir()
        raise
    return snapshots


def _remove_snapshots(root: Path, snapshots: list[dict[str, Any]]) -> None:
    """Remove only snapshots created by the current failed transaction."""

    directories: set[Path] = set()
    for row in snapshots:
        target = (root / row["snapshot_path"]).resolve()
        if not target.is_relative_to(root) or target.is_symlink():
            continue
        directories.add(target.parent)
        if target.is_file():
            target.unlink()
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def record_creative_direction_decision(
    run_dir: Path,
    decision_path: Path,
    *,
    recorded_by: str,
    confirmed_by_user: bool,
) -> Path:
    """Persist one user-selected direction and renderer-compatible translation."""

    if not confirmed_by_user:
        raise ValueError("Creative direction selection requires --confirmed-by-user")
    root = run_dir.resolve()
    with workflow_lock(root):
        validate_input_integrity(root)
        intake = load_json(root / "run_intake.json")
        if not intake["external_routes"]["creative_production"]["selected"]:
            raise ValueError("Creative Production was not selected for this run")
        workbench, handoff = _verify_handoff(root)
        input_decision = load_json(decision_path)
        validate_schema(
            input_decision, "creative_direction_selection_input.schema.json"
        )
        if input_decision["run_id"] != workbench["run_id"]:
            raise ValueError("Creative direction decision run_id mismatch")
        if input_decision["handoff_digest"] != handoff["handoff_digest"]:
            raise ValueError("Creative direction decision targets another handoff")
        version = int(workbench["version"])
        target = root / "creative-direction" / f"decision-v{version:03d}.json"
        if target.exists():
            raise ValueError(
                "Creative direction decision already exists for this version"
            )
        selection = input_decision["selection"]
        snapshots: list[dict[str, Any]] = []
        if input_decision["outcome"] == "selected":
            if "directions" not in selection:
                raise ValueError("Selected outcome requires board directions")
            item_ids = [row["item_id"] for row in selection["directions"]]
            if selection["selected_item_id"] not in item_ids:
                raise ValueError("Selected item is not present in the board result")
            translation = selection["translation"]
            if translation["contribution_change_required"]:
                raise ValueError(
                    "Selected direction requires a superseding contribution and fresh assessments"
                )
            stored_selection: dict[str, Any] = {
                key: selection[key]
                for key in (
                    "board_id",
                    "board_revision",
                    "selected_item_id",
                    "selection_rationale",
                    "translation",
                )
            }
            snapshots = _snapshot_directions(
                root,
                selection["directions"],
                version=version,
            )
            stored_selection["directions"] = snapshots
        else:
            if "reason" not in selection:
                raise ValueError("Fallback outcome requires a fallback reason")
            stored_selection = selection
        output: dict[str, Any] = {
            "schema_version": 1,
            "workflow": "comunicazione-professionale",
            "run_id": workbench["run_id"],
            "recorded_at": utc_now(),
            "recorded_by": recorded_by,
            "confirmed_by_user": True,
            "outcome": input_decision["outcome"],
            "binding": {
                "handoff_digest": handoff["handoff_digest"],
                **handoff["binding"],
            },
            "selection": stored_selection,
        }
        try:
            output["decision_digest"] = canonical_digest(output)
            validate_schema(output, "creative_direction_decision.schema.json")
            return atomic_write_json(target, output)
        except (OSError, ValueError):
            _remove_snapshots(root, snapshots)
            raise


def main(argv: list[str] | None = None) -> int:
    """Record a selected Creative Production direction or fallback."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--recorded-by", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = record_creative_direction_decision(
            args.run_dir,
            args.decision,
            recorded_by=args.recorded_by,
            confirmed_by_user=args.confirmed_by_user,
        )
    except (OSError, ValueError, KeyError) as exc:
        LOGGER.error("CREATIVE_DIRECTION_DECISION_FAILED: %s", exc)
        return 1
    LOGGER.info("Recorded Creative Production direction decision: %s", output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
