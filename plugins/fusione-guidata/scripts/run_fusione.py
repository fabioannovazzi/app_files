#!/usr/bin/env python3
"""Create, update, inspect and demonstrate the versioned merger case and P1 workpapers."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fusione_case import CaseStore
from fusione_demo import run_demo
from fusione_model import CaseError
from fusione_p1_demo import run_p1_demo
from fusione_report import export_report

__all__ = ["main"]
LOGGER = logging.getLogger(__name__)


def _load(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise CaseError("The request must be one JSON object.")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--output", type=Path, required=True)
    p1_demo = commands.add_parser("demo-p1")
    p1_demo.add_argument("--output", type=Path, required=True)
    for name in ("init", "apply", "show", "export"):
        command = commands.add_parser(name)
        command.add_argument("--case", type=Path, required=True)
        command.add_argument("--actor", required=True)
        if name in {"init", "apply"}:
            command.add_argument("--request", type=Path, required=True)
        if name == "show":
            command.add_argument("--id")
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument(
                "--runtime-profile",
                choices=("openai-codex", "anthropic-cowork"),
                default="openai-codex",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(args.output)
        elif args.command == "demo-p1":
            result = run_p1_demo(args.output)
        elif args.command == "init":
            store = CaseStore.create(args.case, args.actor, _load(args.request))
            result = store.metadata
        else:
            store = CaseStore(args.case, args.actor)
            if args.command == "show":
                result = (
                    {"record": store.read(args.id), "status": store.status(args.id)}
                    if args.id
                    else store.report()
                )
            elif args.command == "export":
                result = export_report(
                    store, args.output, runtime_profile=args.runtime_profile
                )
            else:
                request = _load(args.request)
                action = request.pop("action", None)
                if action == "put":
                    result = store.put(**request)
                elif action == "import_evidence":
                    request["source"] = Path(request["source"])
                    result = store.import_evidence(**request)
                elif action == "workpaper":
                    result = store.workpaper(**request)
                elif action == "bind_archive":
                    request["client_root"] = Path(request["client_root"])
                    result = store.bind_archive(**request)
                elif action == "import_archive":
                    result = store.import_archive(**request)
                elif action == "artifact":
                    request["source"] = Path(request["source"])
                    result = store.artifact(**request)
                elif action == "approve":
                    result = store.approve(**request)
                elif action == "grant":
                    store.grant(**request)
                    result = {"status": "grant_recorded"}
                else:
                    raise CaseError(
                        "Unknown action; use put, import_evidence, bind_archive, import_archive, workpaper, artifact, approve or grant."
                    )
    except (CaseError, OSError, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        LOGGER.error("Fusione: %s", exc)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 1 if args.command in {"demo", "demo-p1"} and not result["passed"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
