"""Validate a Clara case workspace mechanically."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from advisor_case_core import validate_case_workspace

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Run workspace validation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    errors = validate_case_workspace(args.case_dir)
    if errors:
        for error in errors:
            LOGGER.error("validation_error: %s", error)
        return 1

    LOGGER.info("validation_errors=[]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
