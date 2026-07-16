"""Refresh the derived Clara working brief."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import refresh_case_brief

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run case-brief refresh."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = refresh_case_brief(args.case_dir)
    LOGGER.info(
        "Case brief refreshed: %s ready=%s pending=%s open_questions=%s issues=%s",
        result.brief_path,
        result.approved_count,
        result.pending_count,
        result.open_question_count,
        result.issue_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
