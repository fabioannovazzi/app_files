"""Count received activity by proven host identity, never by reporter UUID."""

from __future__ import annotations

import json
from typing import Any, Callable

from modules.workflow_usage.products import Product, catalog_metadata

__all__ = ["inspect"]


def inspect(
    connection: Any, sql: Callable[[str], str], since: str, product: Product
) -> dict[str, Any]:
    """Exact joins and the owner's explicit test list make counts reproducible."""
    epoch = connection.execute(
        sql(
            "SELECT e.agent_devices_json FROM vera_workflow_testing_epochs e "
            "LEFT JOIN workflow_testing_epoch_products p ON p.epoch_id=e.epoch_id "
            "WHERE COALESCE(p.product,'vera')=? "
            "ORDER BY e.started_at DESC,e.epoch_id DESC LIMIT 1"
        ),
        (product,),
    ).fetchone()
    agents = set(json.loads(epoch["agent_devices_json"])) if epoch else set()
    cursor = connection.execute(
        sql(
            "SELECT r.projection_json,d.device_id,a.last_seen "
            "FROM vera_workflow_runs r "
            "JOIN (SELECT run_id,MAX(received_at) AS last_seen FROM vera_workflow_events "
            "WHERE received_at>=? GROUP BY run_id) a ON a.run_id=r.run_id "
            "LEFT JOIN operational_device_links d ON d.installation_id=r.installation_id"
        ),
        (since,),
    )
    users: set[str] = set()
    tests: set[str] = set()
    unlinked: set[str] = set()
    excluded = 0
    runs = []
    while rows := cursor.fetchmany(1000):
        for row in rows:
            run = json.loads(row["projection_json"])
            if run.get("product", "vera") != product:
                continue
            computer = row["device_id"]
            is_test = computer in agents or run["sample_kind"] != "user"
            if is_test:
                excluded += 1
                if computer:
                    tests.add(computer)
            elif computer:
                users.add(computer)
            else:
                unlinked.add(run["installation_id"])
            runs.append(
                {
                    "run_id": run["run_id"],
                    "reporter_id": run["installation_id"],
                    "computer_id": computer,
                    "last_received_at": row["last_seen"],
                    "excluded_test": is_test,
                }
            )
    return {
        "product": product,
        "since": since,
        "activity_basis": "server_received_workflow_events",
        "verified_active_user_computers": len(users),
        "unlinked_user_reporting_instances": len(unlinked),
        "excluded_test_runs": excluded,
        "excluded_test_computers": len(tests),
        "computer_count_complete": not unlinked,
        "instrumented_from_version": catalog_metadata(product)[
            "instrumented_from_version"
        ],
        "runs": sorted(runs, key=lambda item: item["run_id"]),
        "limit": "Counts received activity only; old versions and undelivered runs remain unobserved. Unlinked reporter IDs are not additional computers.",
    }
