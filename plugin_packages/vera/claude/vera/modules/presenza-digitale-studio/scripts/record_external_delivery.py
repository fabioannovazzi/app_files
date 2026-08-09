#!/usr/bin/env python3
"""Record visible website preview or publication evidence."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import record_external_delivery

__all__ = ["main"]


def main() -> int:
    """Parse arguments and record external delivery."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["preview", "release"], required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--visible-receipt", required=True)
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_by_user:
        parser.error("--confirmed-by-user is required")
    output = record_external_delivery(
        args.run_dir,
        kind=args.kind,
        destination=args.destination,
        visible_receipt=args.visible_receipt,
        confirmed_by=args.confirmed_by,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("External delivery recorded: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
