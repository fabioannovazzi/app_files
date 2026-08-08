#!/usr/bin/env python3
"""Initialize one exact owner-controlled communications workspace."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from workflow_core import PLUGIN_ROOT, atomic_write_json, utc_now, validate_schema

__all__ = ["initialize_workspace", "main"]

LOGGER = logging.getLogger(__name__)


def initialize_workspace(
    workspace: Path,
    *,
    workspace_id: str,
    owner: str,
    retention_owner: str,
    authorized_by: str,
    confirmed_by_user: bool,
) -> Path:
    """Create and bind a private workspace after explicit user confirmation."""

    if not confirmed_by_user:
        raise ValueError("Workspace initialization requires --confirmed-by-user")
    root = workspace.expanduser().resolve()
    repository_root = PLUGIN_ROOT.parents[1].resolve()
    if root == repository_root or root.is_relative_to(repository_root):
        raise ValueError("Communications workspace must be outside the Git repository")
    if {"public", "published", "static", "plugin_packages"} & {
        part.lower() for part in root.parts
    }:
        raise ValueError(
            "Communications workspace cannot use a public or published path"
        )

    manifest_path = root / "workspace.json"
    if root.exists():
        unexpected = [path for path in root.iterdir() if path.name != "workspace.json"]
        if unexpected and not manifest_path.is_file():
            raise ValueError(
                "Existing non-empty directory is not a communications workspace"
            )
        if manifest_path.exists():
            raise ValueError(f"Workspace already initialized: {manifest_path}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    payload = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "workspace_id": workspace_id,
        "bound_path": str(root),
        "owner": owner,
        "retention_owner": retention_owner,
        "authorized_by": authorized_by,
        "authorization_asserted_not_authenticated": True,
        "created_at": utc_now(),
    }
    validate_schema(payload, "workspace.schema.json")
    atomic_write_json(manifest_path, payload)
    (root / "runs").mkdir(mode=0o700)
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    """Run workspace initialization."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--retention-owner", required=True)
    parser.add_argument("--authorized-by")
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = initialize_workspace(
            args.workspace,
            workspace_id=args.workspace_id,
            owner=args.owner,
            retention_owner=args.retention_owner,
            authorized_by=args.authorized_by or args.owner,
            confirmed_by_user=args.confirmed_by_user,
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("WORKSPACE_INITIALIZATION_FAILED: %s", exc)
        return 1
    LOGGER.info("Initialized communications workspace: %s", path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
