#!/usr/bin/env python3
"""Native-panel projection and actions over the ordinary Agenzia worker and files."""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

from ade_acquisition.contracts import AcquisitionError, Plan, canonical_hash
from ade_acquisition.engine import load_events, timestamp
from ade_acquisition.reports import prepare_f24
from ade_acquisition.storage import Store, atomic_json, read_json
from agenzia_acquire import _archive, _run_path, _start, _summary

__all__ = ["dispatch", "main"]


def _draft(store: Store, source: Plan) -> tuple[Path, dict[str, Any]]:
    directory = store.root / "ui" / canonical_hash(source.payload())
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "draft.json"
    value = read_json(path) if path.exists() else source.payload()
    Plan.parse(value)
    return path, value


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """Revalidate source, exact draft revision and run scope before every action."""
    action, args = request["action"], request.get("args", {})
    store = Store(Path(request["output_directory"]))
    source = Plan.parse(read_json(Path(request["plan_path"])))
    source_revision = canonical_hash(source.payload())
    if request.get("source_revision") and request["source_revision"] != source_revision:
        raise AcquisitionError("source-plan-changed-reopen-panel")
    path, draft = _draft(store, source)
    revision = canonical_hash(draft)
    result: dict[str, Any] = {
        "source_revision": source_revision,
        "revision": revision,
        "plan": draft,
        "source_clients": source.payload()["clients"],
        "state": "planned",
    }
    recent_path = path.parent / "recent-runs.json"
    recent = read_json(recent_path) if recent_path.exists() else []
    result["recent_runs"] = [
        {**entry, "state": _summary(_run_path(store, entry["run_id"]))["state"]}
        for entry in recent
    ]
    if action == "open":
        return result
    if action in {"save", "start"}:
        with Store(path.parent).lock():
            recent = read_json(recent_path) if recent_path.exists() else []
            current = read_json(path) if path.exists() else source.payload()
            if args["revision"] != canonical_hash(current):
                raise AcquisitionError("draft-changed-reload-before-saving")
            if action == "save":
                updated = Plan.parse(args["plan"])
                by_vat = {client.vat_number: client for client in source.clients}
                if any(
                    by_vat.get(client.vat_number) != client
                    for client in updated.clients
                ):
                    raise AcquisitionError("plan-client-outside-selected-source")
                atomic_json(path, updated.payload())
                return {
                    **result,
                    "revision": canonical_hash(updated.payload()),
                    "plan": updated.payload(),
                }
            request_id = args["request_id"]
            if not isinstance(request_id, str) or not re.fullmatch(
                r"[a-zA-Z0-9-]{1,80}", request_id
            ):
                raise AcquisitionError("start-request-id-invalid")
            for entry in recent:
                if entry["request_id"] == request_id:
                    if entry["plan_revision"] != canonical_hash(current):
                        raise AcquisitionError("start-request-plan-mismatch")
                    return {**result, **_summary(_run_path(store, entry["run_id"]))}
            started = _start(
                store, Plan.parse(current), f"{source_revision}:{request_id}"
            )
            recent.append(
                {
                    "request_id": request_id,
                    "plan_revision": canonical_hash(current),
                    "run_id": started["run_id"],
                    "started_at": timestamp(),
                }
            )
            atomic_json(recent_path, recent)
            return {**result, **started, "recent_runs": recent}
    run = _run_path(store, args["run_id"])
    plan = Plan.parse(read_json(run / "plan.json"))
    source_clients = {client.vat_number: client for client in source.clients}
    if any(source_clients.get(client.vat_number) != client for client in plan.clients):
        raise AcquisitionError("run-client-outside-selected-source")
    if action == "continue":
        if read_json(run / "status.json")["state"] != "waiting_for_login":
            raise AcquisitionError("run-not-waiting-for-login")
        atomic_json(run / "auth-ready.json", {"ready": True})
    elif action == "cancel":
        atomic_json(run / "cancel.json", {"cancel": True})
    elif action == "resume":
        request_id = args["request_id"]
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9-]{1,80}", request_id
        ):
            raise AcquisitionError("start-request-id-invalid")
        with Store(path.parent).lock():
            recent = read_json(recent_path) if recent_path.exists() else []
            started = _start(
                store, plan, f"{source_revision}:resume:{run.name}:{request_id}"
            )
            if not any(entry["run_id"] == started["run_id"] for entry in recent):
                recent.append(
                    {
                        "request_id": request_id,
                        "plan_revision": canonical_hash(plan.payload()),
                        "run_id": started["run_id"],
                        "started_at": timestamp(),
                    }
                )
                atomic_json(recent_path, recent)
        return {**result, **started, "plan": plan.payload(), "recent_runs": recent}
    elif action == "f24":
        if read_json(run / "status.json").get("reports_ready") is not True:
            raise AcquisitionError("report-not-ready")
        if args["revision"] != canonical_hash(read_json(run / "report.json")):
            raise AcquisitionError("report-changed-reopen-review")
        pdf = prepare_f24(run, plan, args["review"])
        return {
            **result,
            "state": "draft",
            "download": {
                "name": pdf.name,
                "mime": "application/pdf",
                "base64": base64.b64encode(pdf.read_bytes()).decode(),
            },
        }
    elif action == "archive":
        return {**result, **_archive(store, run, plan)}
    elif action == "download":
        allowed = {
            "riepilogo.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "fatture.csv": "text/csv",
            "model_data_report.md": "text/markdown",
        }
        name = args["name"]
        if name not in allowed:
            raise AcquisitionError("output-not-available")
        if read_json(run / "status.json").get("reports_ready") is not True:
            raise AcquisitionError("report-not-ready")
        file = store.safe_path(f"runs/{run.name}/{name}")
        if not file.is_file() or file.stat().st_size > 16_000_000:
            raise AcquisitionError("output-unavailable-or-too-large")
        return {
            **result,
            "state": "download",
            "download": {
                "name": name,
                "mime": allowed[name],
                "base64": base64.b64encode(file.read_bytes()).decode(),
            },
        }
    elif action != "status":
        raise AcquisitionError("panel-action-invalid")
    status = _summary(run)
    detail = read_json(run / "status.json")
    invoice_events = [
        event
        for event in load_events(run, allow_pending=True)
        if event["kind"] == "invoice"
    ]
    offset = args.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise AcquisitionError("panel-offset-invalid")
    if args.get("exceptions_only", False):
        invoice_events = [
            event for event in invoice_events if event["status"] == "failed"
        ]
    evidence: dict[str, Any] = {}
    if detail.get("reports_ready") is True and (run / "report.json").is_file():
        report = read_json(run / "report.json")
        evidence = {
            "report_revision": canonical_hash(report),
            "stamp_duty": report["stamp_duty"],
            "cash_review_issues": report["cash_review_issues"],
        }
    return {
        **result,
        **status,
        "plan": plan.payload(),
        "scopes": detail.get("scopes", []),
        "invoice_results": invoice_events[offset : offset + 40],
        "invoice_total": len(invoice_events),
        "offset": offset,
        "current": detail.get("current"),
        **evidence,
    }


def main() -> int:
    try:
        value = json.load(sys.stdin)
        result = dispatch(value)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        return 0
    except (AcquisitionError, OSError, ValueError, KeyError, TypeError) as exc:
        code = (
            exc.code
            if isinstance(exc, AcquisitionError)
            else "panel-input-or-file-invalid"
        )
        sys.stdout.write(json.dumps({"state": "failed", "error": code}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
