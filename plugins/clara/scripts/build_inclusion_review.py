"""Render a read-only Clara client-pack inclusion checklist."""

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

from advisor_case_core import CaseWorkspaceError, build_inclusion_review

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Build the inclusion review Markdown artifact."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path. Defaults to <case-dir>/inclusion_review.md.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        result = build_inclusion_review(args.case_dir, output_path=args.out)
    except CaseWorkspaceError as exc:
        parser.error(str(exc))

    LOGGER.info("Inclusion review: %s", result.review_path)
    LOGGER.info("Pending entries: %s", result.pending_count)
    LOGGER.info("Decision-pack-ready entries: %s", result.approved_count)
    LOGGER.info("Excluded entries: %s", result.rejected_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
