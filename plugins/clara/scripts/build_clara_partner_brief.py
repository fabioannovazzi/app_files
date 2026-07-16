"""Render Clara's local HTML partner brief."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import render_clara_partner_brief

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run Clara partner-brief rendering."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = render_clara_partner_brief(args.case_dir, output_path=args.output)
    LOGGER.info("Clara partner brief: %s", result.html_path)
    LOGGER.info("Open clarifications: %s", result.open_clarification_count)
    LOGGER.info("Next steps: %s", result.next_step_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
