"""Atomic event ingestion and projections within the incident store transaction."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Callable
from uuid import UUID, uuid4

from modules.workflow_usage.contracts import WorkflowEvent
from modules.workflow_usage.products import Product

__all__ = ["SCHEMA", "WorkflowConflict", "record", "get_run", "feedback", "overview"]

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS vera_workflow_runs (run_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, projection_json TEXT NOT NULL, feedback_key TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS vera_workflow_events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload_json TEXT NOT NULL, received_at TEXT NOT NULL, UNIQUE (run_id,sequence))",
    "CREATE TABLE IF NOT EXISTS vera_workflow_receipts (receipt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS vera_workflow_owner ON vera_workflow_runs (installation_id)",
)
TERMINAL = {"completed", "failed", "cancelled"}


class WorkflowConflict(ValueError):
    """An event conflicts with retained identity, sequence, or evidence."""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_run(connection: Any, sql: Callable[[str], str], run_id: str) -> Any:
    """Return internal row; callers must authorize before exposing its fields."""
    return connection.execute(
        sql("SELECT * FROM vera_workflow_runs WHERE run_id=?"), (run_id,)
    ).fetchone()


def record(
    connection: Any,
    sql: Callable[[str], str],
    owner: str,
    event: WorkflowEvent,
    now: str,
    *,
    form_submission: bool = False,
    product: Product = "vera",
) -> dict[str, Any]:
    """Exactly-once storage uses immutable UUIDs and sequential compare-and-swap."""
    run_id = str(event.run_id)
    if (event.product or "vera") != product:
        raise WorkflowConflict("Event belongs to another product")
    row = get_run(connection, sql, run_id)
    if row is not None and row["installation_id"] != owner:
        raise WorkflowConflict("Run is outside this installation")
    payload = _json(event.model_dump(mode="json", exclude_none=True))
    existing = connection.execute(
        sql("SELECT * FROM vera_workflow_events WHERE event_id=?"),
        (str(event.event_id),),
    ).fetchone()
    if existing is not None:
        if existing["payload_json"] != payload or row is None:
            raise WorkflowConflict("Event UUID already binds different evidence")
        return _ack(row, event, duplicate=True)
    if row is None:
        if event.kind != "started" or event.sequence != 1:
            raise WorkflowConflict("Start must be recorded before subsequent events")
        projection: dict[str, Any] = {
            "product": product,
            "run_id": run_id,
            "installation_id": owner,
            "pipeline": event.pipeline,
            "host": event.host,
            "sample_kind": event.sample_kind,
            "started_version": event.product_version,
            "started_at": now,
            "state": "unknown",
            "sequence": 0,
            "client_sequence": 0,
            "receipts": [],
            "incident_report_ids": [],
            "feedback": None,
            "feedback_prompted": False,
            "failure_count": 0,
            "resume_count": 0,
        }
        key = secrets.token_urlsafe(32)
    else:
        projection = json.loads(row["projection_json"])
        key = row["feedback_key"]
        if event.kind == "started":
            raise WorkflowConflict("A task starts once; resume its existing UUID")
    server_sequence = projection["sequence"] + 1
    # The hosted form is a separate writer. It must not consume the client's
    # durable event sequence while that client is offline. Preserve submitted
    # bytes and assign a separate server ordering to both streams.
    expected_sequences = {server_sequence}
    if not form_submission:
        expected_sequences.add(projection["client_sequence"] + 1)
    if event.sequence not in expected_sequences:
        raise WorkflowConflict("Stale or missing event sequence; read run status")
    if event.kind in TERMINAL:
        if projection["state"] != "unknown":
            raise WorkflowConflict("Task already has an outcome; resume explicitly")
        projection["state"] = event.kind
        projection["outcome_at"] = now
        if event.kind == "failed":
            projection["failure_count"] += 1
    elif event.kind == "resumed":
        if projection["state"] not in {"failed", "cancelled"}:
            raise WorkflowConflict("Only failed or cancelled tasks can resume")
        projection["state"] = "unknown"
        projection["resume_count"] += 1
    elif event.kind == "receipt":
        claim = connection.execute(
            sql("SELECT run_id FROM vera_workflow_receipts WHERE receipt_id=?"),
            (str(event.receipt_id),),
        ).fetchone()
        if claim is not None:
            raise WorkflowConflict("Receipt already belongs to a recorded run")
        connection.execute(
            sql("INSERT INTO vera_workflow_receipts VALUES (?,?)"),
            (str(event.receipt_id), run_id),
        )
        projection["receipts"].append(
            {
                "receipt_id": str(event.receipt_id),
                "report_sha256": event.report_sha256,
                "product_version": event.receipt_version,
            }
        )
    elif event.kind == "incident":
        report = connection.execute(
            sql("SELECT installation_id FROM operational_reports WHERE report_id=?"),
            (str(event.incident_report_id),),
        ).fetchone()
        if report is None or report["installation_id"] != owner:
            raise WorkflowConflict("Incident report is outside this installation")
        identifier = str(event.incident_report_id)
        if identifier not in projection["incident_report_ids"]:
            projection["incident_report_ids"].append(identifier)
    elif event.kind in {"feedback", "feedback_prompted"}:
        if projection["state"] not in TERMINAL:
            raise WorkflowConflict("Feedback follows an observed task outcome")
        if event.kind == "feedback_prompted":
            if projection["feedback_prompted"]:
                raise WorkflowConflict("Feedback was already offered for this task")
            projection["feedback_prompted"] = True
        else:
            if (
                projection["sample_kind"] != "user"
                and event.feedback_source != "synthetic_test"
            ):
                raise WorkflowConflict("Test feedback must be explicitly synthetic")
            if (
                projection["sample_kind"] == "user"
                and event.feedback_source == "synthetic_test"
            ):
                raise WorkflowConflict("Synthetic feedback cannot rate a user task")
            projection["feedback"] = {
                "stars": event.stars,
                "comment": event.comment,
                "source": event.feedback_source,
                "event_id": str(event.event_id),
                "received_at": now,
            }
    projection.update(
        sequence=server_sequence, current_version=event.product_version, updated_at=now
    )
    if not form_submission:
        projection["client_sequence"] = event.sequence
    connection.execute(
        sql("INSERT INTO vera_workflow_events VALUES (?,?,?,?,?)"),
        (str(event.event_id), run_id, server_sequence, payload, now),
    )
    connection.execute(
        sql(
            "INSERT INTO vera_workflow_runs VALUES (?,?,?,?) ON CONFLICT (run_id) DO UPDATE SET projection_json=excluded.projection_json"
        ),
        (run_id, owner, _json(projection), key),
    )
    return _ack(get_run(connection, sql, run_id), event, duplicate=False)


def _ack(row: Any, event: WorkflowEvent, *, duplicate: bool) -> dict[str, Any]:
    projection = json.loads(row["projection_json"])
    return {
        "recorded": True,
        "duplicate": duplicate,
        "event_id": str(event.event_id),
        "run_id": str(event.run_id),
        "installation_id": row["installation_id"],
        "sequence": event.sequence,
        "current_sequence": projection["sequence"],
        "payload_sha256": hashlib.sha256(
            _json(event.model_dump(mode="json", exclude_none=True)).encode()
        ).hexdigest(),
        "state": projection["state"],
        "feedback_url": f"https://mparanza.com/{projection.get('product', 'vera')}/feedback/{event.run_id}#{row['feedback_key']}",
    }


def feedback(
    connection: Any,
    sql: Callable[[str], str],
    run_id: str,
    key: str,
    event_id: UUID,
    stars: int,
    comment: str | None,
    now: str,
    product: Product = "vera",
) -> dict[str, Any]:
    """A per-run form capability can rate only that run, never read other records."""
    row = get_run(connection, sql, run_id)
    if row is None or not hmac.compare_digest(key, row["feedback_key"]):
        raise WorkflowConflict("Feedback link is unavailable")
    projection = json.loads(row["projection_json"])
    if projection.get("product", "vera") != product:
        raise WorkflowConflict("Feedback belongs to another product")
    old = connection.execute(
        sql(
            "SELECT payload_json FROM vera_workflow_events WHERE event_id=? AND run_id=?"
        ),
        (str(event_id), run_id),
    ).fetchone()
    if old is not None:
        previous = WorkflowEvent.model_validate_json(old["payload_json"])
        if (
            previous.kind != "feedback"
            or previous.stars != stars
            or previous.comment != comment
        ):
            raise WorkflowConflict("Feedback retry changed the original answer")
        return {"recorded": True, "event_id": str(event_id)}
    event = WorkflowEvent(
        product=(
            projection.get("product")
            if projection.get("product", "vera") != "vera"
            else None
        ),
        event_id=event_id,
        run_id=UUID(run_id),
        sequence=projection["sequence"] + 1,
        kind="feedback",
        occurred_at=now,
        product_version=projection["current_version"],
        stars=stars,
        comment=comment,
        feedback_source=(
            "user_form" if projection["sample_kind"] == "user" else "synthetic_test"
        ),
    )
    record(
        connection,
        sql,
        row["installation_id"],
        event,
        now,
        form_submission=True,
        product=projection.get("product", "vera"),
    )
    return {"recorded": True, "event_id": str(event_id)}


def overview(connection: Any, sql: Callable[[str], str], limit: int) -> dict[str, Any]:
    """Bound operator reads explicitly; truncated inventories are never totals."""
    total = connection.execute(
        "SELECT COUNT(*) AS n FROM vera_workflow_runs"
    ).fetchone()["n"]
    rows = connection.execute(
        sql("SELECT projection_json FROM vera_workflow_runs ORDER BY run_id LIMIT ?"),
        (limit,),
    ).fetchall()
    return {
        "runs": [json.loads(row["projection_json"]) for row in rows],
        "total": total,
        "complete": total <= limit,
    }
