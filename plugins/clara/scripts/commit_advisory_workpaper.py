"""Commit a model-authored advisory workpaper against declared case lineage."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from advisor_case_core import CaseWorkspaceError, commit_advisory_workpaper

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("authored_workpaper", type=Path)
    parser.add_argument("--claim-id", action="append", required=True)
    parser.add_argument("--change-summary", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = commit_advisory_workpaper(
            args.case_dir,
            args.authored_workpaper,
            referenced_claim_ids=args.claim_id,
            change_summary=args.change_summary,
        )
    except (CaseWorkspaceError, OSError, json.JSONDecodeError) as exc:
        LOGGER.error("Workpaper commit failed: %s", exc)
        return 1
    LOGGER.info(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
