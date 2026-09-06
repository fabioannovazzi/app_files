"""Commit a model-authored advisory workpaper against declared case lineage."""

from __future__ import annotations

# Direct CLI calls must select dependencies before importing workflow modules.
if __name__ == "__main__":
    import runpy as _runpy
    from pathlib import Path as _Path

    for _parent in _Path(__file__).resolve().parents:
        _launcher = _parent / "scripts" / "self_relaunch.py"
        if not _launcher.is_file():
            _launcher = _parent / "clara" / "scripts" / "self_relaunch.py"
        if _launcher.is_file():
            _runpy.run_path(str(_launcher))["ensure_running_in_managed_venv"](__file__)
            break
    else:
        # Standalone components retain their host's dependency setup.
        if any(
            (_p / "components.json").is_file()
            for _p in _Path(__file__).resolve().parents
        ):
            raise SystemExit(
                "Managed Python launcher is missing; rebuild the plugin package."
            )

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
