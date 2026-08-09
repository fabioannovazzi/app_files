#!/usr/bin/env python3
"""Validate the exact working website package."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import validate_site

__all__ = ["main"]


def main() -> int:
    """Parse arguments and validate the site."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    output = validate_site(args.run_dir)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Site validation written: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
