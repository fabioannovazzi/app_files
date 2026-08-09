#!/usr/bin/env python3
"""Record a source-bound model-led website brief."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import record_site_brief

__all__ = ["main"]


def main() -> int:
    """Parse arguments and record the website brief."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--recorded-by", required=True)
    args = parser.parse_args()
    output = record_site_brief(
        args.run_dir,
        args.brief,
        provider=args.provider,
        model=args.model,
        recorded_by=args.recorded_by,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Site brief recorded: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
