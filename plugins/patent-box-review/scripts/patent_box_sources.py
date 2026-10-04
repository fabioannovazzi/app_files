"""Host-operated public research actions; no automatic schedule or notifications."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["main"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from patent_box import monitor_service
from patent_box.contracts import ContractError, read_json
from patent_box.source_acquisition import (
    acquire,
    attach_text,
    compare_scans,
    finish_scan,
    open_scan,
    write_impact_queue,
)

LOGGER = logging.getLogger(__name__)


def _read(path: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 16 * 1024 * 1024
    ):
        raise ContractError("Expected a bounded, selected JSON file")
    value = read_json(path)
    if not isinstance(value, dict):
        raise ContractError("Expected an object")
    return value


def main(argv: list[str] | None = None) -> int:
    """Expose immutable source acquisitions and conservative private impact proposals."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("open")
    start.add_argument("--plan", required=True, type=Path)
    start.add_argument("--output-root", required=True, type=Path)
    fetch = commands.add_parser("acquire")
    fetch.add_argument("--scan", required=True, type=Path)
    fetch.add_argument("--scope-id", required=True)
    fetch.add_argument("--url", required=True)
    fetch.add_argument("--kind", choices=("LISTING", "DOCUMENT"), required=True)
    fetch.add_argument("--parent-receipt-id")
    extraction = commands.add_parser("attach-text")
    extraction.add_argument("--scan", required=True, type=Path)
    extraction.add_argument("--receipt-id", required=True)
    extraction.add_argument("--text", required=True, type=Path)
    extraction.add_argument("--extractor", required=True)
    finish = commands.add_parser("finish")
    finish.add_argument("--scan", required=True, type=Path)
    finish.add_argument("--review", required=True, type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("--before", required=True, type=Path)
    compare.add_argument("--after", required=True, type=Path)
    impact = commands.add_parser("impact")
    impact.add_argument("--before", required=True, type=Path)
    impact.add_argument("--after", required=True, type=Path)
    impact.add_argument("--private-case-index", required=True, type=Path)
    impact.add_argument("--private-output", required=True, type=Path)
    service_config = commands.add_parser("monitor-configure")
    service_config.add_argument("--private-root", type=Path, required=True)
    service_config.add_argument("--public-root", type=Path, required=True)
    service_config.add_argument("--private-case-index", type=Path)
    service_config.add_argument("--plan", type=Path, required=True)
    service_config.add_argument("--owner", required=True)
    service_config.add_argument("--interval-hours", type=int, default=168)
    schedule = commands.add_parser("monitor-record-schedule")
    schedule.add_argument("--private-root", type=Path, required=True)
    schedule.add_argument("--host-reference", required=True)
    schedule.add_argument("--owner", required=True)
    schedule.add_argument("--state", choices=("ACTIVE", "PAUSED"), required=True)
    service_start = commands.add_parser("monitor-begin")
    service_start.add_argument("--private-root", type=Path, required=True)
    service_start.add_argument("--plan", type=Path, required=True)
    service_start.add_argument(
        "--trigger",
        choices=("PERIODIC", "OPEN_CASE", "CLOSE_CASE", "MANUAL_RETRY"),
        default="PERIODIC",
    )
    for name in ("monitor-finish", "monitor-fail", "monitor-status"):
        command = commands.add_parser(name)
        command.add_argument("--private-root", type=Path, required=True)
        if name != "monitor-status":
            command.add_argument("--job-id", required=True)
        if name == "monitor-fail":
            command.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    if args.command == "monitor-configure":
        result = monitor_service.configure(
            args.private_root,
            public_root=args.public_root,
            owner=args.owner,
            plan=_read(args.plan),
            private_case_index=args.private_case_index,
            interval_hours=args.interval_hours,
        )
    elif args.command == "monitor-record-schedule":
        result = monitor_service.record_schedule(
            args.private_root,
            host_reference=args.host_reference,
            owner=args.owner,
            active=args.state == "ACTIVE",
            at=datetime.now(timezone.utc),
        )
    elif args.command == "monitor-begin":
        result = monitor_service.begin(
            args.private_root,
            _read(args.plan),
            trigger=args.trigger,
            at=datetime.now(timezone.utc),
        )
    elif args.command == "monitor-status":
        result = monitor_service.status(
            args.private_root, at=datetime.now(timezone.utc)
        )
    elif args.command == "monitor-finish":
        result = monitor_service.finish(
            args.private_root, args.job_id, at=datetime.now(timezone.utc)
        )
    elif args.command == "monitor-fail":
        result = monitor_service.fail(
            args.private_root,
            args.job_id,
            reason=args.reason,
            at=datetime.now(timezone.utc),
        )
    elif args.command == "open":
        result = open_scan(_read(args.plan), args.output_root)
    elif args.command == "acquire":
        result = acquire(
            args.scan,
            scope_id=args.scope_id,
            url=args.url,
            kind=args.kind,
            parent_receipt_id=args.parent_receipt_id,
        )
    elif args.command == "attach-text":
        result = attach_text(
            args.scan,
            receipt_id=args.receipt_id,
            text_path=args.text,
            extractor=args.extractor,
        )
    elif args.command == "finish":
        result = finish_scan(args.scan, _read(args.review))
    else:
        result = compare_scans(args.before, args.after)
        if args.command == "impact":
            for public_directory in (args.before.resolve(), args.after.resolve()):
                if args.private_output.resolve().is_relative_to(
                    public_directory
                ) or args.private_case_index.resolve().is_relative_to(public_directory):
                    raise ContractError(
                        "Private case index and impact queue must stay outside public scan directories"
                    )
            result = write_impact_queue(
                result, _read(args.private_case_index), args.private_output
            )
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        LOGGER.error("Source acquisition incomplete: %s", error)
        raise SystemExit(2) from error
