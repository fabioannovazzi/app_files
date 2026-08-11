#!/usr/bin/env python3
"""Prepare an immutable website workflow run."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import prepare_run

__all__ = ["main"]


def main() -> int:
    """Parse arguments and prepare a run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--intake", type=Path, required=True)
    args = parser.parse_args()
    output = prepare_run(args.workspace, args.intake)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Run prepared: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
