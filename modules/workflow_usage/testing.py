"""Public testing levels from completed runs in an explicit counting epoch."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable
from uuid import UUID, uuid4

from modules.workflow_usage.contracts import pipeline_catalog
from modules.workflow_usage.products import Product, product_name

__all__ = ["SCHEMA", "reset", "inspect", "public_status"]

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS vera_workflow_testing_epochs (epoch_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, agent_devices_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS workflow_testing_epoch_products (epoch_id TEXT PRIMARY KEY, product TEXT NOT NULL)",
)


def reset(
    connection: Any,
    sql: Callable[[str], str],
    agent_devices: list[str],
    now: str,
    product: Product = "vera",
) -> dict[str, Any]:
    """Start a fresh counter without deleting usage or earlier counting epochs."""
    product_name(product)
    devices = sorted({str(UUID(value)) for value in agent_devices})
    if not devices:
        raise ValueError("At least one registered agent computer is required")
    for device in devices:
        if (
            connection.execute(
                sql("SELECT device_id FROM operational_devices WHERE device_id=?"),
                (device,),
            ).fetchone()
            is None
        ):
            raise ValueError("Agent computer is not registered")
    epoch = {"epoch_id": str(uuid4()), "started_at": now, "agent_devices": devices}
    connection.execute(
        sql("INSERT INTO vera_workflow_testing_epochs VALUES (?,?,?)"),
        (epoch["epoch_id"], now, json.dumps(devices)),
    )
    connection.execute(
        sql("INSERT INTO workflow_testing_epoch_products VALUES (?,?)"),
        (epoch["epoch_id"], product),
    )
    return epoch


def inspect(
    connection: Any, sql: Callable[[str], str], product: Product = "vera"
) -> dict[str, Any]:
    """Exact event times and native device IDs make these counts reproducible.

    The product owner's rule classifies their computer as agent testing and
    other computers as professional use. This is a counting convention, not
    semantic evaluation of the work, stars, or identification of individuals.
    """
    product_name(product)
    row = connection.execute(
        sql(
            "SELECT e.* FROM vera_workflow_testing_epochs e LEFT JOIN workflow_testing_epoch_products p ON p.epoch_id=e.epoch_id WHERE COALESCE(p.product,'vera')=? ORDER BY e.started_at DESC,e.epoch_id DESC LIMIT 1"
        ),
        (product,),
    ).fetchone()
    evidence: dict[str, dict[str, Any]] = {
        key: {"agent_runs": [], "professional_devices": {}, "unlinked_runs": []}
        for key in pipeline_catalog(product)
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "epoch_id": row["epoch_id"] if row else None,
        "started_at": row["started_at"] if row else None,
        "pipelines": evidence,
        "excluded_test_runs": 0,
    }
    if row is not None:
        baseline = datetime.fromisoformat(row["started_at"])
        agent_devices = set(json.loads(row["agent_devices_json"]))
        cursor = connection.execute(
            sql(
                "SELECT r.projection_json,d.device_id,e.payload_json,e.received_at "
                "FROM vera_workflow_events e "
                "JOIN vera_workflow_runs r ON r.run_id=e.run_id "
                "LEFT JOIN operational_device_links d ON d.installation_id=r.installation_id "
                "WHERE e.received_at>? ORDER BY e.received_at,e.event_id"
            ),
            (row["started_at"],),
        )
        while rows := cursor.fetchmany(1000):
            for item in rows:
                event = json.loads(item["payload_json"])
                if event["kind"] != "completed":
                    continue
                # Delayed delivery of an old completion cannot repopulate a reset.
                if datetime.fromisoformat(event["occurred_at"]) <= baseline:
                    continue
                run = json.loads(item["projection_json"])
                if run.get("product", "vera") != product:
                    continue
                if run["state"] != "completed" or run["pipeline"] not in evidence:
                    continue
                target = evidence[run["pipeline"]]
                device = item["device_id"]
                if device in agent_devices:
                    target["agent_runs"].append(run["run_id"])
                elif run["sample_kind"] != "user":
                    result["excluded_test_runs"] += 1
                elif device is None:
                    # A reporter/connector UUID is not a computer. Re-evaluation
                    # picks up a later proven host link without replaying the run.
                    target["unlinked_runs"].append(run["run_id"])
                else:
                    target["professional_devices"].setdefault(device, []).append(
                        run["run_id"]
                    )
    for target in evidence.values():
        count = len(target["professional_devices"])
        target["status"] = (
            "repeated"
            if count >= 3
            else "tried" if count else "agent" if target["agent_runs"] else "untried"
        )
    return result


def public_status(evidence: dict[str, Any]) -> dict[str, Any]:
    """Expose only the legend state, never computer IDs, run IDs or feedback."""
    return {
        "schema_version": 1,
        "epoch_id": evidence["epoch_id"],
        "started_at": evidence["started_at"],
        "pipelines": {
            key: value["status"] for key, value in evidence["pipelines"].items()
        },
    }
