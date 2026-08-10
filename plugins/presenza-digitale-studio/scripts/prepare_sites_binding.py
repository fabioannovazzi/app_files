#!/usr/bin/env python3
"""Bind an exact Vera website package into its run-owned Sites project."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from workflow_core import prepare_sites_binding

__all__ = ["main"]


def main() -> int:
    """Parse arguments and prepare the Sites release binding."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--kind", choices=["preview", "release"], required=True)
    args = parser.parse_args()
    output = prepare_sites_binding(args.run_dir, kind=args.kind)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Sites binding ready: %s", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
