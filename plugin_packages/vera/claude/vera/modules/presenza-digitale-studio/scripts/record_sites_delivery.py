#!/usr/bin/env python3
"""Record an exact succeeded Sites version and deployment."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import record_sites_delivery

__all__ = ["main"]


def main() -> int:
    """Parse arguments and record the Sites delivery receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_by_user:
        parser.error("--confirmed-by-user is required")
    output = record_sites_delivery(
        args.run_dir,
        args.receipt,
        confirmed_by=args.confirmed_by,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Sites delivery recorded: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
