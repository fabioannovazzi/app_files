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
    list_studio_client_identities,
    match_studio_email_client,
    open_archive_source,
    plan_gmail_client_search,
    refresh_archive,
    search_archive,
    set_studio_client_identity,
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
    subparsers.add_parser("clients")

    configure_client = subparsers.add_parser("configure-client")
    configure_client.add_argument("--scope-id", required=True)
    configure_client.add_argument("--email-address", action="append", default=[])
    configure_client.add_argument("--legal-name", action="append", default=[])
    configure_client.add_argument("--tax-identifier", action="append", default=[])
    configure_client.add_argument("--replace-orphaned-scope-id")

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

    plan_gmail = subparsers.add_parser("plan-gmail")
    plan_gmail.add_argument("--scope-id", required=True)
    plan_gmail.add_argument("--topic")
    plan_gmail.add_argument("--after")
    plan_gmail.add_argument("--before")

    match_email = subparsers.add_parser("match-email")
    match_email.add_argument("--header-address", action="append", required=True)
    match_email.add_argument("--headers-complete", action="store_true")
    match_email.add_argument("--expected-scope-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one Studio Archive operation and emit structured JSON."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "configure":
            result = configure_archive(args.archive_root)
        elif args.command == "status":
            result = studio_archive_status()
        elif args.command == "clients":
            result = list_studio_client_identities()
        elif args.command == "configure-client":
            result = set_studio_client_identity(
                args.scope_id,
                email_addresses=args.email_address,
                legal_names=args.legal_name,
                tax_identifiers=args.tax_identifier,
                replace_orphaned_scope_id=args.replace_orphaned_scope_id,
            )
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
        elif args.command == "open":
            result = open_archive_source(
                args.source_id,
                context_chunks=args.context_chunks,
            )
        elif args.command == "plan-gmail":
            result = plan_gmail_client_search(
                args.scope_id,
                topic=args.topic,
                after=args.after,
                before=args.before,
            )
        else:
            result = match_studio_email_client(
                args.header_address,
                headers_complete=args.headers_complete,
                expected_scope_id=args.expected_scope_id,
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
