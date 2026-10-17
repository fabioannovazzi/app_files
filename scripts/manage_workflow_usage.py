"""Inspect real pipeline use and feedback without reading professional work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.operational_incidents.store import IncidentStore
from modules.run_receipts.store import get_run_receipt_store
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.workflow_usage.reporting import render_html, summarize

__all__ = ["main"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summary")
    summary.add_argument("--limit", type=int, default=10000)
    summary.add_argument("--html", type=Path)
    show = commands.add_parser("show")
    show.add_argument("run_id")
    commands.add_parser("testing-status")
    reset = commands.add_parser("testing-reset")
    reset.add_argument("--agent-device", action="append", required=True)
    args = parser.parse_args()
    load_env_from_secrets_file()
    store = IncidentStore(args.sqlite_path)
    if args.command == "summary":
        result = summarize(
            store.workflow_overview(args.limit),
            get_run_receipt_store().inventory(args.limit),
        )
        if args.html:
            args.html.write_text(render_html(result), encoding="utf-8")
            args.html.chmod(0o600)
    elif args.command == "show":
        result = store.workflow_inspect(args.run_id)
    elif args.command == "testing-reset":
        result = store.workflow_testing_reset(args.agent_device)
    else:
        result = store.workflow_testing()
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
