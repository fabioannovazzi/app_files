"""Durable task-level usage and actual user feedback, using Vera's existing identity."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import runpy
import sqlite3
import stat
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import operational_incidents as incidents

_reporting_product = runpy.run_path(
    str(Path(__file__).with_name("reporting_product.py"))
)
product_name = _reporting_product["product_name"]
installed_reference_path = _reporting_product["installed_reference_path"]

__all__ = [
    "start",
    "record",
    "flush",
    "pending",
    "acknowledge",
    "status",
    "attach_receipt",
    "build_report",
    "stamp_report",
    "startup_context",
    "main",
]
LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _database() -> sqlite3.Connection:
    path = (
        Path(incidents.local_context()["outbox_path"]).parent / "workflow-usage.sqlite3"
    )
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("Usage state must be an ordinary private file")
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o600:
        path.chmod(0o600)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, pipeline TEXT NOT NULL, sample_kind TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL, receipt TEXT, UNIQUE(run_id,sequence))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS remote_state (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    connection.commit()
    return connection


def _version() -> str:
    for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = ROOT / relative
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))["version"]
    raise ValueError("Installed product version unavailable")


def _owner() -> tuple[dict[str, str], str]:
    context = incidents.local_context()
    return context["credentials"], context["client_status"]["host"]


def _send(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    return incidents.workflow_transport(operation, payload)


def _pending(
    connection: sqlite3.Connection, run_id: str | None = None
) -> list[sqlite3.Row]:
    if run_id is None:
        return connection.execute(
            "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY sequence) AS queue_rank FROM events WHERE receipt IS NULL) ORDER BY queue_rank,run_id LIMIT 100"
        ).fetchall()
    return connection.execute(
        "SELECT * FROM events WHERE receipt IS NULL AND run_id=? ORDER BY sequence",
        (run_id,),
    ).fetchall()


def _queued_count(connection: sqlite3.Connection, run_id: str | None = None) -> int:
    """Count the same delivery scope; other tasks cannot make this task pending."""
    if run_id is None:
        return connection.execute(
            "SELECT COUNT(*) FROM events WHERE receipt IS NULL"
        ).fetchone()[0]
    return connection.execute(
        "SELECT COUNT(*) FROM events WHERE receipt IS NULL AND run_id=?", (run_id,)
    ).fetchone()[0]


def _match_ack(row: sqlite3.Row, owner: str, reply: dict[str, Any]) -> None:
    digest = hashlib.sha256(row["payload"].encode()).hexdigest()
    expected = {
        "recorded": True,
        "event_id": row["event_id"],
        "run_id": row["run_id"],
        "installation_id": owner,
        "sequence": row["sequence"],
        "payload_sha256": digest,
    }
    if any(reply.get(key) != value for key, value in expected.items()):
        raise ValueError("Usage acknowledgement does not match queued evidence")


def pending(*, run_id: str | None = None) -> dict[str, Any]:
    """Expose exact events in the selected scope for authenticated delivery."""
    connection = _database()
    try:
        credentials, _ = _owner()
        rows = _pending(connection, run_id)
        return {
            "credentials": credentials,
            "events": [json.loads(row["payload"]) for row in rows],
            "queued": _queued_count(connection, run_id),
        }
    finally:
        connection.close()


def acknowledge(reply: dict[str, Any]) -> dict[str, Any]:
    """Persist an actual connector receipt without replacing the local identity."""
    connection = _database()
    try:
        with connection:
            row = connection.execute(
                "SELECT * FROM events WHERE event_id=?", (reply["event_id"],)
            ).fetchone()
            if row is None:
                raise ValueError("Acknowledged event is not in local state")
            owner = connection.execute(
                "SELECT owner FROM runs WHERE run_id=?", (row["run_id"],)
            ).fetchone()["owner"]
            _match_ack(row, owner, reply)
            connection.execute(
                "UPDATE events SET receipt=? WHERE event_id=? AND receipt IS NULL",
                (_json(reply), row["event_id"]),
            )
        return {"acknowledged": True, "event_id": row["event_id"]}
    finally:
        connection.close()


def flush(*, run_id: str | None = None) -> dict[str, Any]:
    """Replay and report only the selected scope, preserving exact owner/hash."""
    credentials, _ = _owner()
    connection = _database()
    delivered = 0
    deadline = time.monotonic() + 20
    blocked: dict[str, str] = {}
    try:
        for row in _pending(connection, run_id):
            if time.monotonic() >= deadline:
                break
            if row["run_id"] in blocked:
                continue
            owner = connection.execute(
                "SELECT owner FROM runs WHERE run_id=?", (row["run_id"],)
            ).fetchone()["owner"]
            if owner != credentials["installation_id"]:
                blocked[row["run_id"]] = "reporting_identity_changed"
                continue
            payload = json.loads(row["payload"])
            try:
                reply = _send(
                    "workflow-record", {"credentials": credentials, "event": payload}
                )
                _match_ack(row, owner, reply)
            except (OSError, ValueError, KeyError) as error:
                blocked[row["run_id"]] = type(error).__name__
                continue
            with connection:
                connection.execute(
                    "UPDATE events SET receipt=? WHERE event_id=? AND receipt IS NULL",
                    (_json(reply), row["event_id"]),
                )
            delivered += 1
        queued = _queued_count(connection, run_id)
        return {"delivered": delivered, "queued": queued, "blocked": blocked}
    finally:
        connection.close()


def status(run_id: str, *, remote: bool = True) -> dict[str, Any]:
    """Keep remote evidence separate from locally queued, unacknowledged events."""
    run_id = str(UUID(run_id))
    credentials, _ = _owner()
    connection = _database()
    try:
        if remote:
            try:
                result = _send(
                    "workflow-status", {"credentials": credentials, "run_id": run_id}
                )
                if (
                    result["run_id"] != run_id
                    or result["installation_id"] != credentials["installation_id"]
                ):
                    raise ValueError("Usage status owner mismatch")
                with connection:
                    connection.execute(
                        "INSERT INTO remote_state VALUES (?,?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload",
                        (run_id, _json(result)),
                    )
            except (OSError, ValueError, KeyError):
                LOGGER.info("Task usage status remains pending")
        saved = connection.execute(
            "SELECT payload FROM remote_state WHERE run_id=?", (run_id,)
        ).fetchone()
        rows = connection.execute(
            "SELECT payload,receipt FROM events WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        return {
            "run_id": run_id,
            "remote": json.loads(saved["payload"]) if saved else None,
            "local_events": [
                {
                    "event": json.loads(row["payload"]),
                    "acknowledged": row["receipt"] is not None,
                }
                for row in rows
            ],
            "queued": len(_pending(connection, run_id)),
        }
    finally:
        connection.close()


def start(
    run_id: str,
    pipeline: str,
    *,
    sample_kind: str,
    host: str = "unknown",
    deliver: bool = True,
) -> dict[str, Any]:
    """Start once with a retained UUID; never count internal helpers as new work."""
    run_id = str(UUID(run_id))
    catalog = json.loads((ROOT / "usage/pipelines.json").read_text(encoding="utf-8"))
    if pipeline not in catalog["pipelines"] or sample_kind not in {
        "user",
        "synthetic",
        "agent_test",
    }:
        raise ValueError(
            "Choose a registered primary pipeline and explicit sample kind"
        )
    if host not in {"codex", "cowork", "chatgpt", "antigravity", "unknown"}:
        raise ValueError("Choose the observed app or unknown")
    credentials, _ = _owner()
    connection = _database()
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if existing and (
                existing["owner"],
                existing["pipeline"],
                existing["sample_kind"],
            ) != (credentials["installation_id"], pipeline, sample_kind):
                raise ValueError("Run UUID already binds another task")
            if existing is None:
                connection.execute(
                    "INSERT INTO runs VALUES (?,?,?,?)",
                    (run_id, credentials["installation_id"], pipeline, sample_kind),
                )
                _append(
                    connection,
                    run_id,
                    "started",
                    {"pipeline": pipeline, "host": host, "sample_kind": sample_kind},
                )
    finally:
        connection.close()
    delivery = flush(run_id=run_id) if deliver else {"queued": True}
    return {"run_id": run_id, "delivery": delivery}


def _append(
    connection: sqlite3.Connection, run_id: str, kind: str, fields: dict[str, Any]
) -> dict[str, Any]:
    local = (
        connection.execute(
            "SELECT MAX(sequence) FROM events WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        or 0
    )
    remote = connection.execute(
        "SELECT payload FROM remote_state WHERE run_id=?", (run_id,)
    ).fetchone()
    sequence = (
        max(local, json.loads(remote["payload"])["sequence"] if remote else 0) + 1
    )
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": run_id,
        "sequence": sequence,
        "kind": kind,
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "product_version": _version(),
        **({"product": product_name(ROOT)} if product_name(ROOT) != "vera" else {}),
        **{key: value for key, value in fields.items() if value is not None},
    }
    connection.execute(
        "INSERT INTO events VALUES (?,?,?,?,NULL)",
        (event["event_id"], run_id, sequence, _json(event)),
    )
    return event


def record(
    run_id: str, kind: str, *, deliver: bool = True, **fields: Any
) -> dict[str, Any]:
    """Persist before networking; exact repeated calls reuse the retained event."""
    run_id = str(UUID(run_id))
    allowed = {
        "resumed": set(),
        "completed": set(),
        "failed": set(),
        "cancelled": set(),
        "feedback_prompted": set(),
        "feedback": {"stars", "comment", "feedback_source"},
        "receipt": {"receipt_id", "receipt_version", "report_sha256"},
        "incident": {"incident_report_id"},
    }
    if kind not in allowed or set(fields) - allowed[kind]:
        raise ValueError("Unexpected usage event fields")
    if kind == "feedback" and (
        type(fields.get("stars")) is not int
        or not 1 <= fields["stars"] <= 5
        or len(fields.get("comment") or "") > 2000
    ):
        raise ValueError("Feedback requires 1–5 stars and at most 2000 characters")
    if deliver:
        flush(run_id=run_id)
        status(run_id)
    connection = _database()
    ask = False
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise ValueError("Start this task before recording an outcome")
            previous = connection.execute(
                "SELECT payload FROM events WHERE run_id=? ORDER BY sequence DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            old = json.loads(previous["payload"])
            remote = connection.execute(
                "SELECT payload FROM remote_state WHERE run_id=?", (run_id,)
            ).fetchone()
            projection = json.loads(remote["payload"]) if remote else {}
            history = [
                json.loads(row["payload"])
                for row in connection.execute(
                    "SELECT payload FROM events WHERE run_id=? ORDER BY sequence",
                    (run_id,),
                )
            ]
            lifecycle = [
                item
                for item in history
                if item["kind"]
                in {"started", "resumed", "completed", "failed", "cancelled"}
            ]
            state = lifecycle[-1]["kind"]
            if state in {"started", "resumed"}:
                state = "unknown"
            if projection and projection["sequence"] > old["sequence"]:
                state = projection["state"]
            already_prompted = (
                projection.get("feedback_prompted")
                or projection.get("feedback")
                or any(
                    item["kind"] in {"feedback_prompted", "feedback"}
                    for item in history
                )
            )
            if kind == "feedback_prompted" and (
                already_prompted or run["sample_kind"] != "user"
            ):
                return {"run_id": run_id, "ask": False}
            if kind in {"completed", "failed", "cancelled"}:
                if state == kind:
                    return {"run_id": run_id, "duplicate": True, "ask": False}
                if state != "unknown":
                    raise ValueError(
                        "Resume the original task before changing its outcome"
                    )
            if kind == "resumed" and state not in {"failed", "cancelled"}:
                if lifecycle[-1]["kind"] == "resumed":
                    return {"run_id": run_id, "duplicate": True, "ask": False}
                raise ValueError("Only a failed or cancelled task can resume")
            if kind in {"feedback", "feedback_prompted"} and state == "unknown":
                raise ValueError("Deliver an observed task outcome before feedback")
            if kind == "feedback":
                expected_source = (
                    {"user_chat", "user_form"}
                    if run["sample_kind"] == "user"
                    else {"synthetic_test"}
                )
                if fields.get("feedback_source") not in expected_source:
                    raise ValueError("Feedback source does not match this run")
            if kind in {"receipt", "incident"} and any(
                item["kind"] == kind
                and all(item.get(key) == value for key, value in fields.items())
                for item in history
            ):
                return {"run_id": run_id, "duplicate": True, "ask": False}
            if old["kind"] == kind and all(
                old.get(key) == value for key, value in fields.items()
            ):
                event = old
            else:
                event = _append(connection, run_id, kind, fields)
                ask = kind == "feedback_prompted"
    finally:
        connection.close()
    delivery = flush(run_id=run_id) if deliver else {"queued": True}
    return {
        "run_id": run_id,
        "event_id": event["event_id"],
        "ask": ask,
        "delivery": delivery,
    }


def attach_receipt(
    run_id: str, receipt_path: Path, *, deliver: bool = True
) -> dict[str, Any]:
    """Link proof metadata only; the service checks the retained signed receipt."""
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    if value.get("status") == "stamped" and "receipt" in value:
        value = value["receipt"]
    if value.get("product", "vera") != product_name(ROOT):
        raise ValueError("Receipt belongs to another product")
    return record(
        run_id,
        "receipt",
        deliver=deliver,
        receipt_id=str(UUID(value["receipt_id"])),
        receipt_version=value["plugin_version"],
        report_sha256=value["report_sha256"],
    )


def _link_built_report(run_id: str, result: dict[str, Any]) -> dict[str, Any]:
    receipt = result.get("server_receipt", result)
    if receipt.get("status") == "stamped":
        try:
            result["workflow_usage"] = attach_receipt(
                run_id, Path(receipt["receipt_path"])
            )
        except (OSError, ValueError, KeyError, sqlite3.Error):
            result["workflow_usage"] = {
                "status": "pending",
                "reason": "usage_link_unavailable",
            }
    else:
        result["workflow_usage"] = {
            "status": "not_linked",
            "receipt_status": receipt.get("status", "unknown"),
        }
    return result


def build_report(
    run_id: str,
    input_path: Path,
    output_dir: Path,
    *,
    evidence_root: Path | None = None,
    local_only: bool = False,
) -> dict[str, Any]:
    """Use the existing shared report builder unchanged, then link its actual proof."""
    from model_data_report import main as report_main

    arguments = ["build", "--input", str(input_path), "--output-dir", str(output_dir)]
    if evidence_root is not None:
        arguments += ["--evidence-root", str(evidence_root)]
    if local_only:
        arguments.append("--local-only")
    output = io.StringIO()
    with redirect_stdout(output):
        code = report_main(arguments)
    if code != 0:
        raise ValueError("The model-data report could not be built")
    return _link_built_report(run_id, json.loads(output.getvalue()))


def stamp_report(run_id: str, report_path: Path, output_dir: Path) -> dict[str, Any]:
    """Retry the original signed receipt without creating a different task."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema_version") in {3, 4} and report.get("product") == "vera":
        raise ValueError(
            "Vera Archive receipts are bound and retried automatically for the Archive run; "
            "a separate workflow-usage task cannot stamp or link this report."
        )
    from notarized_run_receipt import NotarizedRunReceiptError, stamp_model_data_report

    try:
        result = stamp_model_data_report(
            report_path, output_dir=output_dir, plugin_root=ROOT
        )
    except NotarizedRunReceiptError:
        return {"status": "pending", "reason": "receipt_service_unavailable"}
    return _link_built_report(run_id, result)


def startup_context() -> str:
    """Expose a diagnostic backlog count without selecting unrelated task IDs."""
    connection = _database()
    try:
        return (
            f"{product_name(ROOT).title()} workflow usage: follow "
            f"{installed_reference_path('workflow-usage.md', ROOT)} for every substantive "
            "task, including AI-only work. One primary task UUID; Studio Archive is "
            "infrastructure. Start/record saves and delivers only that task's events. "
            "Retry delivery with workflow_usage.py flush --run-id <retained-uuid>. "
            f"Pending events across retained tasks: {_queued_count(connection)}. "
            "Unrelated pending events are not a prerequisite for current work. "
            "Never infer stars or completion; record the user's actual answer after delivery."
        )
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("start")
    begin.add_argument("--run-id", required=True)
    begin.add_argument("--pipeline", required=True)
    begin.add_argument(
        "--host",
        choices=("codex", "cowork", "chatgpt", "antigravity", "unknown"),
        required=True,
    )
    begin.add_argument(
        "--sample-kind", choices=("user", "synthetic", "agent_test"), required=True
    )
    emit = commands.add_parser("record")
    emit.add_argument("--run-id", required=True)
    emit.add_argument("--kind", required=True)
    emit.add_argument(
        "--fields",
        type=Path,
        help="Exact small usage fields JSON, never a client document",
    )
    attach = commands.add_parser("receipt")
    attach.add_argument("--run-id", required=True)
    attach.add_argument("--receipt", type=Path, required=True)
    inspect = commands.add_parser("status")
    inspect.add_argument("--run-id", required=True)
    build = commands.add_parser("build-report")
    build.add_argument("--run-id", required=True)
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--evidence-root", type=Path)
    build.add_argument("--local-only", action="store_true")
    stamp = commands.add_parser("stamp-report")
    stamp.add_argument("--run-id", required=True)
    stamp.add_argument("--report", type=Path, required=True)
    stamp.add_argument("--output-dir", type=Path, required=True)
    for command in ("flush", "pending"):
        scoped = commands.add_parser(command)
        scoped.add_argument(
            "--run-id",
            help="Select this task's events; omitted for whole-outbox maintenance",
        )
    ack = commands.add_parser("ack")
    ack.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            result = start(
                args.run_id, args.pipeline, sample_kind=args.sample_kind, host=args.host
            )
        elif args.command == "record":
            fields = (
                json.loads(args.fields.read_text(encoding="utf-8"))
                if args.fields
                else {}
            )
            result = record(args.run_id, args.kind, **fields)
        elif args.command == "receipt":
            result = attach_receipt(args.run_id, args.receipt)
        elif args.command == "status":
            result = status(args.run_id)
        elif args.command == "build-report":
            result = build_report(
                args.run_id,
                args.input,
                args.output_dir,
                evidence_root=args.evidence_root,
                local_only=args.local_only,
            )
        elif args.command == "stamp-report":
            result = stamp_report(args.run_id, args.report, args.output_dir)
        elif args.command == "pending":
            result = pending(run_id=args.run_id)
        elif args.command == "ack":
            result = acknowledge(json.loads(args.receipt.read_text(encoding="utf-8")))
        else:
            result = flush(run_id=args.run_id)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        LOGGER.error(
            "Usage reporting unavailable (%s); preserve the original task and queued events",
            type(error).__name__,
        )
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
