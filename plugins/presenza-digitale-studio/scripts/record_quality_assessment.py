#!/usr/bin/env python3
"""Record model-led quality review of the rendered site."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import record_quality_assessment

__all__ = ["main"]


def main() -> int:
    """Parse arguments and record a quality assessment."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--recorded-by", required=True)
    args = parser.parse_args()
    output = record_quality_assessment(
        args.run_dir,
        args.assessment,
        provider=args.provider,
        model=args.model,
        recorded_by=args.recorded_by,
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Quality assessment recorded: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
