"""Public aggregates: exact identity sets, never individual activity or feedback."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from modules.workflow_usage.products import PRODUCTS, Product, catalog_metadata

__all__ = ["inspect"]

APPS = ("codex", "cowork", "antigravity")


@dataclass
class _Users:
    started: set[str] = field(default_factory=set)
    completed: set[str] = field(default_factory=set)

    def record(self, computer: str, completed: bool) -> None:
        self.started.add(computer)
        if completed:
            self.completed.add(computer)

    def counts(self) -> dict[str, int]:
        # The owner's dashboard definition is non-completion, not error events.
        return {
            "started": len(self.started),
            "completed": len(self.completed),
            "failed": len(self.started - self.completed),
        }


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def inspect(connection: Any, sql: Callable[[str], str], now: str) -> dict[str, Any]:
    """Count exact sets across all retained eligible runs; no time window or cap.

    ID equality, numeric versions and set difference are mechanically verifiable.
    They implement the agreed metric without inferring people or task meaning.
    """
    catalogs = {product: catalog_metadata(product) for product in PRODUCTS}
    versions = {
        product: catalog["instrumented_from_version"]
        for product, catalog in catalogs.items()
    }
    minimums = {product: _version(version) for product, version in versions.items()}
    excluded = set()
    for product in PRODUCTS:
        epoch = connection.execute(
            sql(
                "SELECT e.agent_devices_json FROM vera_workflow_testing_epochs e "
                "LEFT JOIN workflow_testing_epoch_products p ON p.epoch_id=e.epoch_id "
                "WHERE COALESCE(p.product,'vera')=? "
                "ORDER BY e.started_at DESC,e.epoch_id DESC LIMIT 1"
            ),
            (product,),
        ).fetchone()
        if epoch:
            excluded.update(json.loads(epoch["agent_devices_json"]))
    total = _Users()
    functions: dict[tuple[Product, str], _Users] = defaultdict(_Users)
    apps: dict[str, _Users] = defaultdict(_Users)
    identity_complete = True
    cursor = connection.execute(
        sql(
            "SELECT r.projection_json,COALESCE(h.device_id,d.device_id) AS device_id "
            "FROM vera_workflow_runs r "
            "LEFT JOIN operational_device_links d ON d.installation_id=r.installation_id "
            "LEFT JOIN workflow_run_hosts h ON h.run_id=r.run_id"
        )
    )
    while rows := cursor.fetchmany(1000):
        for row in rows:
            run = json.loads(row["projection_json"])
            product = run.get("product", "vera")
            computer = row["device_id"]
            if (
                product not in catalogs
                or run["sample_kind"] != "user"
                or computer in excluded
                or run["host"] not in APPS
                or _version(run["started_version"]) < minimums[product]
            ):
                continue
            if computer is None:
                identity_complete = False
                continue
            completed = run["state"] == "completed"
            total.record(computer, completed)
            functions[(product, run["pipeline"])].record(computer, completed)
            apps[run["host"]].record(computer, completed)
    return {
        "updated_at": now,
        "minimum_versions": versions,
        "supported_apps": list(APPS),
        "identity_complete": identity_complete,
        "totals": total.counts(),
        "functions": [
            {
                "product": product,
                "pipeline": pipeline,
                "label": catalogs[product]["pipelines"][pipeline],
                **users.counts(),
            }
            for (product, pipeline), users in sorted(
                functions.items(),
                key=lambda item: (PRODUCTS.index(item[0][0]), item[0][1]),
            )
        ],
        "apps": [{"app": app, **apps[app].counts()} for app in APPS if app in apps],
    }
