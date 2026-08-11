#!/usr/bin/env python3
"""Validate current website workflow integrity and status."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from workflow_core import validate_run

__all__ = ["main"]


def main() -> int:
    """Parse arguments and validate the run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = validate_run(args.run_dir)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
