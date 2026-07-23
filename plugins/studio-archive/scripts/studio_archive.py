#!/usr/bin/env python3
"""Command-line interface for Vera Studio Archive."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from archive_core import (
    ArchiveError,
    configure_archive,
    open_archive_source,
    refresh_archive,
    search_archive,
    studio_archive_status,
)

__all__ = ["main"]


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure")
    configure.add_argument("--archive-root", type=Path, required=True)

    subparsers.add_parser("status")

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--rebuild", action="store_true")
    refresh.add_argument("--enable-ocr", action="store_true")

    search = subparsers.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--scope-id", required=True)
    search.add_argument("--limit", type=int, default=10)

    open_source = subparsers.add_parser("open")
    open_source.add_argument("--source-id", required=True)
    open_source.add_argument("--context-chunks", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one Studio Archive operation and emit structured JSON."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "configure":
            result = configure_archive(args.archive_root)
        elif args.command == "status":
            result = studio_archive_status()
        elif args.command == "refresh":
            result = refresh_archive(
                rebuild=args.rebuild,
                enable_ocr=args.enable_ocr,
            )
        elif args.command == "search":
            result = search_archive(
                args.query,
                scope_id=args.scope_id,
                limit=args.limit,
            )
        else:
            result = open_archive_source(
                args.source_id,
                context_chunks=args.context_chunks,
            )
    except (ArchiveError, OSError, sqlite3.Error) as exc:
        _emit(
            {
                "error": {
                    "code": getattr(exc, "code", "archive_operation_failed"),
                    "message": str(exc),
                }
            }
        )
        return 1
    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
