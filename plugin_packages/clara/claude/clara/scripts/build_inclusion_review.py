"""Render a read-only Clara client-pack inclusion checklist."""

from __future__ import annotations

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
