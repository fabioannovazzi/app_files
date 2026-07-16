#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from typing import Iterable

from modules.utilities.session_cleanup import cleanup_sessions


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean up persisted FastAPI session files.",
    )
    parser.add_argument(
        "--retention-hours",
        type=float,
        default=72.0,
        help="Remove session files older than this many hours (default: 72).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would be removed without deleting them.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    removed, scanned = cleanup_sessions(args.retention_hours, dry_run=args.dry_run)
    print(f"Scanned {scanned} session artifacts, removed {removed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
