#!/usr/bin/env python3
"""Vera's single Agenzia acquisition entry point: plan, start, status, resume and review."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ade_acquisition.contracts import (
    OPERATIONS,
    AcquisitionError,
    Plan,
    canonical_hash,
    read_clients,
)
from ade_acquisition.engine import Acquisition, load_events, timestamp
from ade_acquisition.portal import Portal, open_browser
from ade_acquisition.reports import prepare_f24, write_reports
from ade_acquisition.storage import Store, atomic_json, private_root, read_json

__all__ = ["main"]


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _run_path(store: Store, run_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise AcquisitionError("run-id-invalid")
    run = store.safe_path(f"runs/{run_id}")
    if not run.is_dir():
        raise AcquisitionError("run-not-found")
    return run


def _summary(run: Path) -> dict[str, Any]:
    state = read_json(run / "status.json")
    selected = {
        key: value for key, value in state.items() if key not in {"scopes", "current"}
    }
    pending_reports = (
        state["state"] in {"complete", "partial", "cancelled"}
        and state.get("reports_ready") is False
    )
    if (
        state["state"] in {"running", "waiting_for_login", "starting"}
        or pending_reports
    ):
        store = Store(run.parent.parent)
        live = False
        try:
            with store.lock():
                pass
        except AcquisitionError as exc:
            if exc.code != "acquisition-already-running":
                raise
            marker = store.root / ".worker-current.json"
            live = marker.is_file() and read_json(marker).get("run_id") == run.name
        selected["worker_active"] = live
        if pending_reports and live:
            selected["state"] = "finalizing"
        age = (
            datetime.now(timezone.utc) - datetime.fromisoformat(state["updated_at"])
        ).total_seconds()
        if not live and (state["state"] != "starting" or age > 60):
            selected["state"] = "interrupted"
            selected["stop_reason"] = "worker-no-longer-active"
    selected.update(run_id=run.name, run_directory=str(run))
    return selected


def _start(store: Store, plan: Plan, request_id: str | None = None) -> dict[str, Any]:
    """Reserve a durable run before launching; retries cannot launch a second worker."""
    control = Store(store.root / "launch-control")
    with control.lock():
        receipt = (
            control.root / f"{canonical_hash(request_id)}.json" if request_id else None
        )
        if receipt and receipt.exists():
            previous = read_json(receipt)
            if previous["plan_revision"] != canonical_hash(plan.payload()):
                raise AcquisitionError("start-request-plan-mismatch")
            return _summary(_run_path(store, previous["run_id"]))
        latest = control.root / "latest.json"
        if latest.exists():
            previous = _summary(_run_path(store, read_json(latest)["run_id"]))
            if previous["state"] in {
                "starting",
                "running",
                "waiting_for_login",
                "finalizing",
            }:
                raise AcquisitionError("acquisition-already-running")
        with store.lock():
            pass
        run = store.new_run(plan.payload())
        atomic_json(
            run / "status.json", {"state": "starting", "updated_at": timestamp()}
        )
        reservation = {
            "run_id": run.name,
            "plan_revision": canonical_hash(plan.payload()),
        }
        if receipt:
            atomic_json(receipt, reservation)
        atomic_json(latest, reservation)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--output",
            str(store.root),
            "--run-id",
            run.name,
        ]
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **kwargs)
        except OSError as exc:
            atomic_json(
                run / "status.json",
                {
                    "state": "failed",
                    "error": "worker-launch-failed",
                    "updated_at": timestamp(),
                },
            )
            raise AcquisitionError("worker-launch-failed") from exc
        # PID is separate: the worker may already have written a newer status.
        atomic_json(run / "process.json", {"pid": process.pid})
        return {
            "state": "starting",
            "run_id": run.name,
            "run_directory": str(run),
            "pid": process.pid,
        }


def _worker(store: Store, run: Path) -> dict[str, Any]:
    plan = Plan.parse(read_json(run / "plan.json"))
    state: dict[str, Any] = {
        "state": "starting",
        "pid": os.getpid(),
        "updated_at": timestamp(),
    }
    try:
        with store.lock():
            atomic_json(store.root / ".worker-current.json", {"run_id": run.name})
            with open_browser() as page:
                state.update(
                    state="waiting_for_login",
                    updated_at=timestamp(),
                    next_action="Complete login in Chrome, then tell Vera to continue.",
                )
                atomic_json(run / "status.json", state)
                deadline = time.monotonic() + 1800
                while not (run / "auth-ready.json").exists():
                    if (run / "cancel.json").exists():
                        raise AcquisitionError("cancelled")
                    if time.monotonic() > deadline:
                        raise AcquisitionError("login-wait-expired")
                    if page.is_closed():
                        raise AcquisitionError("browser-closed")
                    page.wait_for_timeout(500)
                engine = Acquisition(store, run, plan, Portal(page))
                state = engine.execute()
                state.update(write_reports(run, plan, state))
                atomic_json(run / "status.json", state)
    except (AcquisitionError, OSError, sqlite3.Error, ImportError, ValueError) as exc:
        code = (
            exc.code
            if isinstance(exc, AcquisitionError)
            else "local-runtime-or-storage-error"
        )
        if (run / "status.json").exists():
            state = read_json(run / "status.json")
        state.update(
            state="cancelled" if code == "cancelled" else "failed",
            error=code,
            updated_at=timestamp(),
        )
        atomic_json(run / "status.json", state)
    return _summary(run)


def _archive(store: Store, run: Path, plan: Plan) -> dict[str, Any]:
    """Import verified originals through Studio Archive's existing public CLI."""
    script = (
        Path(__file__).resolve().parents[2]
        / "studio-archive"
        / "scripts"
        / "studio_archive.py"
    )
    if not script.is_file():
        raise AcquisitionError("studio-archive-component-unavailable")

    def call(arguments: list[str]) -> dict[str, Any]:
        response = subprocess.run(
            [sys.executable, str(script), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if response.returncode:
            raise AcquisitionError("studio-archive-import-failed")
        try:
            return json.loads(response.stdout)
        except ValueError as exc:
            raise AcquisitionError("studio-archive-response-invalid") from exc

    bindings = {
        client.vat_number: client for client in plan.clients if client.archive_client_id
    }
    if not bindings:
        raise AcquisitionError("archive-binding-required")
    for client in bindings.values():
        resolved = call(
            [
                "resolve-client",
                "--identity-kind",
                "tax_identifier",
                "--identity-value",
                client.tax_code,
            ]
        )
        if (
            resolved.get("resolution_status") != "exact_match"
            or resolved["matches"][0]["client_id"] != client.archive_client_id
        ):
            raise AcquisitionError("archive-client-identity-mismatch")
    receipts_path = run / "archive-imports.json"
    receipts = read_json(receipts_path) if receipts_path.exists() else []
    imported = {(item["client"], item["sha256"]) for item in receipts}
    for event in load_events(run):
        matched_client = bindings.get(event.get("client", ""))
        if (
            event["kind"] != "invoice"
            or not matched_client
            or event["status"] not in {"downloaded", "verified_existing"}
        ):
            continue
        record = event["record"]
        if not store.verified(record):
            raise AcquisitionError("archive-original-no-longer-valid")
        original = record["artifacts"][0]
        key = (matched_client.vat_number, original["sha256"])
        if key in imported:
            continue
        receipt = call(
            [
                "import-document",
                "--client-id",
                matched_client.archive_client_id,
                "--engagement-id",
                matched_client.archive_engagement_id,
                "--role",
                "source",
                "--source-path",
                str(store.safe_path(original["path"])),
            ]
        )
        receipts.append(
            {
                "client": matched_client.vat_number,
                "sha256": original["sha256"],
                "receipt": receipt,
            }
        )
        atomic_json(receipts_path, receipts)
        imported.add(key)
    return {
        "state": "imported",
        "originals": len(receipts),
        "receipts": str(receipts_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--clients", type=Path, required=True)
    plan.add_argument("--sheet")
    plan.add_argument("--date-from", required=True)
    plan.add_argument("--date-to", required=True)
    plan.add_argument(
        "--operations", nargs="+", choices=sorted(OPERATIONS), required=True
    )
    plan.add_argument(
        "--access-mode",
        choices=["delega_diretta", "incaricato"],
        default="delega_diretta",
    )
    plan.add_argument("--work-identity", default="")
    plan.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Private plan JSON file outside source repositories.",
    )
    start = commands.add_parser("start")
    start.add_argument("--plan", type=Path, required=True)
    start.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Persistent local acquisition folder.",
    )
    for name in ("status", "continue", "cancel", "resume", "worker", "f24", "archive"):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--run-id", required=True)
        if name == "f24":
            command.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            payload = {
                "schema_version": "vera-agenzia-plan/v1",
                "clients": read_clients(args.clients, args.sheet),
                "date_from": args.date_from,
                "date_to": args.date_to,
                "operations": args.operations,
                "access_mode": args.access_mode,
                "work_identity": args.work_identity,
            }
            plan = Plan.parse(payload)
            output = private_root(args.output.parent) / args.output.name
            atomic_json(output, plan.payload())
            _emit(
                {
                    "state": "planned",
                    "clients": len(plan.clients),
                    "plan": str(output),
                    "date_from": args.date_from,
                    "date_to": args.date_to,
                    "operations": args.operations,
                }
            )
            return 0
        store = Store(args.output)
        if args.command == "start":
            result = _start(store, Plan.parse(read_json(args.plan)))
        else:
            run = _run_path(store, args.run_id)
            plan = Plan.parse(read_json(run / "plan.json"))
            if args.command == "worker":
                result = _worker(store, run)
            elif args.command == "status":
                result = _summary(run)
            elif args.command == "continue":
                if read_json(run / "status.json")["state"] != "waiting_for_login":
                    raise AcquisitionError("run-not-waiting-for-login")
                atomic_json(run / "auth-ready.json", {"ready": True})
                result = {"state": "continue-requested"}
            elif args.command == "cancel":
                atomic_json(run / "cancel.json", {"cancel": True})
                result = {"state": "cancel-requested"}
            elif args.command == "resume":
                with store.lock():
                    pass
                result = _start(store, plan)
            elif args.command == "f24":
                result = {
                    "state": "draft",
                    "pdf": str(prepare_f24(run, plan, read_json(args.review))),
                }
            else:
                result = _archive(store, run, plan)
        _emit(result)
        return 1 if result["state"] == "failed" else 0
    except (AcquisitionError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        code = (
            exc.code
            if isinstance(exc, AcquisitionError)
            else "local-file-or-runtime-error"
        )
        _emit({"state": "failed", "error": code})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
