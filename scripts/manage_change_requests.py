#!/usr/bin/env python3
"""Inspect, triage, and close Mparanza change requests."""

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

    list_parser = commands.add_parser("list", help="List oldest unresolved requests.")
    list_parser.add_argument("--limit", type=int, default=100)
    list_parser.add_argument(
        "--triage-state",
        choices=("active", "considering", "all"),
        default="active",
        help="Select the open triage queue (default: active).",
    )

    show_parser = commands.add_parser("show", help="Show one complete request.")
    show_parser.add_argument("change_request_id")

    consider_parser = commands.add_parser(
        "consider", help="Set an open request aside for future discussion."
    )
    consider_parser.add_argument("change_request_id")

    activate_parser = commands.add_parser(
        "activate", help="Return a considering request to the active queue."
    )
    activate_parser.add_argument("change_request_id")

    needs_info_parser = commands.add_parser(
        "needs-info", help="Ask the reporter for specific additional evidence."
    )
    needs_info_parser.add_argument("change_request_id")
    needs_info_parser.add_argument("--question", required=True)

    close_parser = commands.add_parser(
        "close", help="Close a verified non-fix outcome with an explicit disposition."
    )
    close_parser.add_argument("change_request_id")
    close_parser.add_argument(
        "--disposition",
        required=True,
        choices=("duplicate", "external", "non_actionable"),
    )
    close_parser.add_argument("--note", required=True)

    reopen_parser = commands.add_parser(
        "reopen", help="Return a closed or needs-information request to active triage."
    )
    reopen_parser.add_argument("change_request_id")

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
        "triage_state": record.triage_state,
        "disposition": record.disposition,
        "revision": record.revision,
        "needs_info_question": record.needs_info_question,
        "operator_note": record.operator_note,
        "closed_at": record.closed_at,
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
        payload["follow_up_evidence"] = json.loads(record.follow_up_json)
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
            records = store.list_open(
                limit=args.limit,
                triage_state=(
                    None if args.triage_state == "all" else args.triage_state
                ),
            )
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
        if args.command in {"consider", "activate"}:
            record = store.set_triage_state(
                args.change_request_id,
                "considering" if args.command == "consider" else "active",
            )
            _write_json(_record_payload(record, include_request=False))
            return 0
        if args.command == "needs-info":
            record = store.mark_needs_info(
                args.change_request_id,
                question=args.question,
            )
            _write_json(_record_payload(record, include_request=False))
            return 0
        if args.command == "close":
            record = store.close_without_fix(
                args.change_request_id,
                disposition=args.disposition,
                note=args.note,
            )
            _write_json(_record_payload(record, include_request=False))
            return 0
        if args.command == "reopen":
            record = store.reopen(args.change_request_id)
            _write_json(_record_payload(record, include_request=False))
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
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 2
    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
