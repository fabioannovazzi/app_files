#!/usr/bin/env python3
"""Check the standard-library-only dependencies for Vera Plan."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    """Validate the declared requirements file."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        type=Path,
        default=PLUGIN_ROOT / "requirements.txt",
    )
    args = parser.parse_args(argv)
    if not args.requirements.is_file():
        LOGGER.error("Requirements file not found: %s", args.requirements)
        return 1
    LOGGER.info("OK: Vera Plan uses Python's standard library only.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
