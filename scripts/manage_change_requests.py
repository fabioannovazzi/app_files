#!/usr/bin/env python3
"""Inspect and close Mparanza change requests from the server environment."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.change_requests.store import (
    ChangeRequestConflictError,
    ChangeRequestManifestError,
    ChangeRequestNotFoundError,
    ChangeRequestRecord,
    ChangeRequestStore,
    ChangeRequestStoreUnavailableError,
)
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = ["main", "parse_args"]

LOGGER = logging.getLogger(__name__)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse operator commands."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        help="Use an explicit local SQLite store instead of configured Postgres.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="List oldest open requests.")
    list_parser.add_argument("--limit", type=int, default=100)

    show_parser = commands.add_parser("show", help="Show one complete request.")
    show_parser.add_argument("change_request_id")

    fixed_parser = commands.add_parser(
        "fixed", help="Mark a request fixed after its plugin version is published."
    )
    fixed_parser.add_argument("change_request_id")
    fixed_parser.add_argument("--published-version", required=True)
    fixed_parser.add_argument(
        "--manifest",
        type=Path,
        help="Override the local published plugin manifest path.",
    )
    return parser.parse_args(list(argv))


def _record_payload(
    record: ChangeRequestRecord, *, include_request: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "change_request_id": record.change_request_id,
        "submission_id": record.submission_id,
        "plugin": record.plugin,
        "plugin_version": record.plugin_version,
        "kind": record.kind,
        "status": record.status,
        "interview_url": record.interview_url,
        "fixed_version": record.fixed_version,
        "install_url": record.install_url,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "fixed_at": record.fixed_at,
    }
    if include_request:
        payload["request"] = record.request
        payload["request_sha256"] = record.request_sha256
        payload["interview"] = (
            json.loads(record.interview_json) if record.interview_json else None
        )
    return payload


def _write_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one operator command and emit machine-readable JSON."""

    args = parse_args(argv if argv is not None else sys.argv[1:])
    load_env_from_secrets_file()
    store = ChangeRequestStore(sqlite_path=args.sqlite_path)
    try:
        if args.command == "list":
            records = store.list_open(limit=args.limit)
            _write_json(
                [_record_payload(record, include_request=False) for record in records]
            )
            return 0
        if args.command == "show":
            record = store.get(args.change_request_id)
            if record is None:
                raise ChangeRequestNotFoundError("Unknown change request.")
            _write_json(_record_payload(record, include_request=True))
            return 0
        if args.command == "fixed":
            record = store.mark_fixed(
                args.change_request_id,
                published_version=args.published_version,
                manifest_path=args.manifest,
            )
            _write_json(_record_payload(record, include_request=False))
            return 0
    except (
        ChangeRequestConflictError,
        ChangeRequestManifestError,
        ChangeRequestNotFoundError,
        ChangeRequestStoreUnavailableError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 2
    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
