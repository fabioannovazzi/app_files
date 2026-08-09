#!/usr/bin/env python3
"""Record a professional website review decision."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import record_review

__all__ = ["main"]


def main() -> int:
    """Parse arguments and record a review."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--scope",
        choices=[
            "identity_and_claims",
            "responsive_preview",
            "publication_destination",
        ],
        required=True,
    )
    parser.add_argument(
        "--decision", choices=["accepted", "returned", "rejected"], required=True
    )
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--confirmed-by-user", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_by_user:
        parser.error("--confirmed-by-user is required")
    output = record_review(
        args.run_dir,
        scope=args.scope,
        decision=args.decision,
        reviewer=args.reviewer,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Review recorded: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
