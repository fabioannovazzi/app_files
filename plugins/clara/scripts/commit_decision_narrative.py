"""Commit reviewed executive paragraphs against the current advisory workpaper."""

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
import logging
from pathlib import Path

from advisor_case_core import CaseWorkspaceError, commit_decision_narrative

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Commit staged narrative JSON and report its durable path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("authored_narrative", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = commit_decision_narrative(args.case_dir, args.authored_narrative)
    except (CaseWorkspaceError, OSError, ValueError) as exc:
        LOGGER.error("Narrative commit failed: %s", exc)
        return 1
    LOGGER.info("%s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
