#!/usr/bin/env python3
"""Promote an accepted studio communication profile to the private workspace."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import (
    atomic_copy_file,
    atomic_write_json,
    canonical_digest,
    file_digest,
    load_json,
    load_workspace,
    require_accepted_reviews,
    utc_now,
    validate_input_integrity,
    workflow_lock,
)

__all__ = ["promote_studio_profile", "main"]

LOGGER = logging.getLogger(__name__)


def promote_studio_profile(run_dir: Path) -> Path:
    """Version and persist one accepted studio-specific format profile."""

    root = run_dir.resolve()
    intake = load_json(root / "run_intake.json")
    workspace = Path(intake["workspace_path"]).resolve()
    load_workspace(workspace)
    if root.parent != workspace / "runs":
        raise ValueError("Run directory is not bound to the declared workspace")
    with workflow_lock(workspace):
        with workflow_lock(root):
            return _promote_studio_profile_locked(root)


def _promote_studio_profile_locked(root: Path) -> Path:
    """Persist an approved profile while the run writer lock is held."""

    validate_input_integrity(root)
    workbench = load_json(root / "content_workbench.json")
    profile = workbench["contribution"].get("studio_profile_proposal")
    if profile is None:
        raise ValueError("Current contribution has no studio profile proposal")
    decisions = require_accepted_reviews(root, ["studio_profile"])
    intake = load_json(root / "run_intake.json")
    workspace = Path(intake["workspace_path"]).resolve()
    profile_path = workspace / "studio_profile.json"
    prepared_profile = intake.get("studio_profile")
    if prepared_profile is None and profile_path.exists():
        raise ValueError(
            "Studio profile appeared after run preparation; prepare a new run"
        )
    if prepared_profile is not None and (
        not profile_path.is_file()
        or file_digest(profile_path) != prepared_profile["sha256"]
    ):
        raise ValueError(
            "Studio profile changed after run preparation; prepare a new run"
        )
    previous = load_json(profile_path) if profile_path.is_file() else None
    if (
        previous
        and previous.get("approved_from", {}).get("contribution_digest")
        == workbench["contribution_digest"]
    ):
        return profile_path
    version = int(previous["version"]) + 1 if previous else 1
    if previous:
        archive_dir = workspace / "profiles"
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / f"studio_profile-v{previous['version']:03d}.json"
        if not archive_path.exists():
            atomic_write_json(archive_path, previous)
    source_register = load_json(root / "source_register.json")
    logo = source_register.get("brand_logo")
    logo_record = None
    if isinstance(logo, dict):
        source_logo = Path(logo["snapshot_path"])
        suffix = source_logo.suffix.lower()
        asset_path = workspace / "studio_assets" / f"studio-logo-v{version:03d}{suffix}"
        atomic_copy_file(source_logo, asset_path)
        logo_record = {
            "workspace_relative_path": asset_path.relative_to(workspace).as_posix(),
            "sha256": file_digest(asset_path),
            "size_bytes": asset_path.stat().st_size,
        }
    brand_assets = {"logo": logo_record}
    provenance_summary = {
        basis: sum(
            len(record["field_paths"])
            for record in profile["field_provenance"]
            if record["basis"] == basis
        )
        for basis in (
            "observed_history",
            "user_supplied",
            "vera_default_proposal",
        )
    }
    format_digest = canonical_digest(
        {
            "studio_name": intake["brand_profile"]["studio_name"],
            "brand_profile": intake["brand_profile"],
            "brand_assets": brand_assets,
            "profile": profile,
        }
    )
    payload = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "workspace_id": intake["workspace_id"],
        "version": version,
        "studio_name": intake["brand_profile"]["studio_name"],
        "brand_profile": intake["brand_profile"],
        "brand_assets": brand_assets,
        "profile": profile,
        "profile_provenance_summary": provenance_summary,
        "accepted_as_studio_standard": True,
        "format_digest": format_digest,
        "approved_from": {
            "run_id": intake["run_id"],
            "contribution_digest": workbench["contribution_digest"],
            "review_event": decisions["studio_profile"],
        },
        "promoted_at": utc_now(),
    }
    atomic_write_json(profile_path, payload)
    return profile_path


def main(argv: list[str] | None = None) -> int:
    """Promote an accepted profile."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = promote_studio_profile(args.run_dir)
    except (OSError, ValueError) as exc:
        LOGGER.error("STUDIO_PROFILE_PROMOTION_FAILED: %s", exc)
        return 1
    LOGGER.info("Promoted studio profile: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
