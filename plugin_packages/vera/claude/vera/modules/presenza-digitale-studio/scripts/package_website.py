#!/usr/bin/env python3
"""Package an exact website preview or release."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import package_website

__all__ = ["main"]


def main() -> int:
    """Parse arguments and package the website."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["preview", "release"], required=True)
    args = parser.parse_args()
    output = package_website(args.run_dir, kind=args.kind)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Website package ready: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
