"""Build Clara's first partner kickoff HTML deck."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import render_clara_kickoff_deck

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run kickoff deck rendering."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = render_clara_kickoff_deck(args.case_dir, output_path=args.output)
    LOGGER.info("Clara kickoff deck: %s", result.html_path)
    LOGGER.info("Candidate hypotheses: %s", result.hypothesis_count)
    LOGGER.info("Open questions: %s", result.open_question_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
