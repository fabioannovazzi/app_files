#!/usr/bin/env python3
"""Initialize a private Presenza digitale dello studio workspace."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import initialize_workspace

__all__ = ["main"]


def main() -> int:
    """Parse arguments and initialize the workspace."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--retention-owner", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_by_user:
        parser.error("--confirmed-by-user is required")
    output = initialize_workspace(
        args.workspace,
        workspace_id=args.workspace_id,
        owner=args.owner,
        retention_owner=args.retention_owner,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Workspace ready: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
