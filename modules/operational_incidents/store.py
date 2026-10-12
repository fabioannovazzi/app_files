"""Durable incident, delivery and outcome records with capability-scoped access."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg

from modules.operational_incidents.contracts import Credentials, Outcome, Remedy, Report
from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    connect_pdp_database,
    is_postgres_enabled,
)
from modules.utilities.cache import get_cache_dir

__all__ = ["IncidentStore", "IncidentConflict", "IncidentNotFound"]


class IncidentConflict(ValueError):
    """A retry or remedy does not match the immutable saved record."""


class IncidentNotFound(ValueError):
    """An installation capability or incident is unavailable."""


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operational_installations (installation_id TEXT PRIMARY KEY, key_hash TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_incidents (incident_id TEXT PRIMARY KEY, signal_hash TEXT UNIQUE NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL, remedy_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_reports (report_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, incident_id TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_deliveries (installation_id TEXT NOT NULL, incident_id TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (installation_id, incident_id))",
    "CREATE TABLE IF NOT EXISTS operational_outcomes (outcome_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, incident_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class IncidentStore:
    """Use the existing Postgres connection, with SQLite for local development."""

    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._postgres = sqlite_path is None and is_postgres_enabled()
        self._path = (
            sqlite_path or get_cache_dir("operational_incidents") / "incidents.sqlite3"
        )
        self._lock = threading.RLock()
        self._ready = False

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        with self._lock:
            if self._postgres:
                with connect_pdp_database(Path(".")) as connection:
                    connection.disable_transaction_replay()
                    connection.row_factory = DICT_ROW_FACTORY
                    # Serialize the small incident queue across API/operator processes.
                    connection.execute("SELECT pg_advisory_xact_lock(721946302)")
                    try:
                        yield connection
                    except (ValueError, OSError, psycopg.Error):
                        self._ready = False
                        raise
            else:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(self._path, timeout=30)
                connection.row_factory = sqlite3.Row
                try:
                    with connection:
                        connection.execute("BEGIN IMMEDIATE")
                        yield connection
                finally:
                    connection.close()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._postgres else sql

    def _schema(self, connection: Any) -> None:
        if not self._ready:
            for statement in _SCHEMA:
                connection.execute(statement)
            self._ready = True

    def _authorize(self, connection: Any, credentials: Credentials) -> None:
        row = connection.execute(
            self._sql(
                "SELECT key_hash FROM operational_installations WHERE installation_id=?"
            ),
            (str(credentials.installation_id),),
        ).fetchone()
        actual = hashlib.sha256(credentials.installation_key.encode()).hexdigest()
        if row is None or not hmac.compare_digest(row["key_hash"], actual):
            raise IncidentNotFound("Installation capability is unavailable")

    def register(self, credentials: Credentials) -> dict[str, Any]:
        """Idempotently register a random installation ID, never a machine identity."""
        with self._connection() as connection:
            self._schema(connection)
            connection.execute(
                self._sql(
                    "INSERT INTO operational_installations VALUES (?,?,?) ON CONFLICT (installation_id) DO NOTHING"
                ),
                (
                    str(credentials.installation_id),
                    hashlib.sha256(credentials.installation_key.encode()).hexdigest(),
                    _now(),
                ),
            )
            self._authorize(connection, credentials)
        return {"installation_id": str(credentials.installation_id), "registered": True}

    def report(self, credentials: Credentials, report: Report) -> dict[str, Any]:
        """Group exact technical signals for investigation, not assumed root causes."""
        payload = report.model_dump(mode="json")
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        signal = {
            key: payload[key]
            for key in (
                "product",
                "host",
                "platform",
                "workflow",
                "stage",
                "diagnostics",
            )
        }
        fingerprint = hashlib.sha256(_json(signal).encode()).hexdigest()
        now = _now()
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            old = connection.execute(
                self._sql("SELECT * FROM operational_reports WHERE report_id=?"),
                (str(report.report_id),),
            ).fetchone()
            if old:
                if (
                    old["installation_id"] != str(credentials.installation_id)
                    or old["payload_hash"] != digest
                ):
                    raise IncidentConflict(
                        "Report identifier already belongs to different evidence"
                    )
                return {
                    "incident_id": old["incident_id"],
                    "report_id": str(report.report_id),
                    "recorded": True,
                    "deduplicated": True,
                }
            incident_id = str(uuid4())
            initial = Remedy(
                kind="investigating",
                summary="Il problema è stato registrato ed è in diagnosi.",
                evidence="No cause has yet been established.",
                expected_outcome="Successful execution of the interrupted operation",
            ).model_dump(mode="json")
            connection.execute(
                self._sql(
                    "INSERT INTO operational_incidents VALUES (?,?,?,?,?,?,?) ON CONFLICT (signal_hash) DO NOTHING"
                ),
                (incident_id, fingerprint, "open", now, now, 1, _json(initial)),
            )
            incident = connection.execute(
                self._sql(
                    "SELECT incident_id FROM operational_incidents WHERE signal_hash=?"
                ),
                (fingerprint,),
            ).fetchone()
            incident_id = incident["incident_id"]
            connection.execute(
                self._sql("INSERT INTO operational_reports VALUES (?,?,?,?,?,?)"),
                (
                    str(report.report_id),
                    str(credentials.installation_id),
                    incident_id,
                    digest,
                    encoded,
                    now,
                ),
            )
            connection.execute(
                self._sql(
                    "INSERT INTO operational_deliveries VALUES (?,?,?,?) ON CONFLICT (installation_id,incident_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at"
                ),
                (str(credentials.installation_id), incident_id, "open", now),
            )
            connection.execute(
                self._sql(
                    "UPDATE operational_incidents SET status='open',updated_at=? WHERE incident_id=?"
                ),
                (now, incident_id),
            )
        return {
            "incident_id": incident_id,
            "report_id": str(report.report_id),
            "recorded": True,
            "deduplicated": False,
        }

    def status(self, credentials: Credentials) -> dict[str, Any]:
        """Return only this installation's incidents and structured remedies."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            rows = connection.execute(
                self._sql(
                    "SELECT i.incident_id,i.revision,i.remedy_json,d.status FROM operational_incidents i JOIN operational_deliveries d ON i.incident_id=d.incident_id WHERE d.installation_id=? ORDER BY i.updated_at"
                ),
                (str(credentials.installation_id),),
            ).fetchall()
        return {
            "incidents": [
                {
                    "incident_id": row["incident_id"],
                    "revision": row["revision"],
                    "status": row["status"],
                    "remedy": json.loads(row["remedy_json"]),
                    "download_urls": (
                        {
                            "codex": "https://mparanza.com/static/shared/plugin-downloads/index.html?product=vera&lang=it",
                            "cowork": "https://mparanza.com/static/shared/vera/downloads/vera-cowork-plugin.zip",
                        }
                        if json.loads(row["remedy_json"])["kind"] == "update"
                        else {}
                    ),
                }
                for row in rows
            ]
        }

    def remedy(self, incident_id: str, remedy: Remedy) -> dict[str, Any]:
        """Operator-only publication; clients cannot deliver executable commands."""
        if remedy.kind == "update" and not remedy.required_version:
            raise IncidentConflict("An update remedy requires a deployed version")
        if remedy.kind == "automatic" and remedy.action is None:
            raise IncidentConflict("An automatic remedy requires a built-in action")
        if remedy.kind == "user-action" and not remedy.instructions:
            raise IncidentConflict("A user action requires exact instructions")
        with self._connection() as connection:
            self._schema(connection)
            row = connection.execute(
                self._sql(
                    "SELECT revision FROM operational_incidents WHERE incident_id=?"
                ),
                (incident_id,),
            ).fetchone()
            if row is None:
                raise IncidentNotFound("Incident is unavailable")
            revision = row["revision"] + 1
            connection.execute(
                self._sql(
                    "UPDATE operational_incidents SET revision=?,remedy_json=?,updated_at=? WHERE incident_id=?"
                ),
                (revision, _json(remedy.model_dump(mode="json")), _now(), incident_id),
            )
        return {
            "incident_id": incident_id,
            "revision": revision,
            "status": "awaiting-recovery",
        }

    def outcome(self, credentials: Credentials, outcome: Outcome) -> dict[str, Any]:
        """Close this delivery only after an actual successful execution receipt."""
        if outcome.status == "recovered" and not outcome.execution_succeeded:
            raise IncidentConflict("Recovery requires successful execution evidence")
        encoded = _json(outcome.model_dump(mode="json"))
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            row = connection.execute(
                self._sql(
                    "SELECT i.revision FROM operational_incidents i JOIN operational_deliveries d ON i.incident_id=d.incident_id WHERE i.incident_id=? AND d.installation_id=?"
                ),
                (str(outcome.incident_id), str(credentials.installation_id)),
            ).fetchone()
            if row is None:
                raise IncidentNotFound("Incident is unavailable")
            if row["revision"] != outcome.remedy_revision:
                raise IncidentConflict(
                    "Remedy changed; read current status before reporting recovery"
                )
            previous = connection.execute(
                self._sql(
                    "SELECT payload_json,installation_id FROM operational_outcomes WHERE outcome_id=?"
                ),
                (str(outcome.outcome_id),),
            ).fetchone()
            if previous and (
                previous["payload_json"] != encoded
                or previous["installation_id"] != str(credentials.installation_id)
            ):
                raise IncidentConflict(
                    "Outcome identifier already belongs to different evidence"
                )
            if previous:
                return {
                    "incident_id": str(outcome.incident_id),
                    "status": outcome.status,
                    "recorded": True,
                }
            connection.execute(
                self._sql(
                    "INSERT INTO operational_outcomes VALUES (?,?,?,?,?) ON CONFLICT (outcome_id) DO NOTHING"
                ),
                (
                    str(outcome.outcome_id),
                    str(credentials.installation_id),
                    str(outcome.incident_id),
                    encoded,
                    _now(),
                ),
            )
            connection.execute(
                self._sql(
                    "UPDATE operational_deliveries SET status=?,updated_at=? WHERE installation_id=? AND incident_id=?"
                ),
                (
                    outcome.status,
                    _now(),
                    str(credentials.installation_id),
                    str(outcome.incident_id),
                ),
            )
            remaining = connection.execute(
                self._sql(
                    "SELECT COUNT(*) AS count FROM operational_deliveries WHERE incident_id=? AND status!='recovered'"
                ),
                (str(outcome.incident_id),),
            ).fetchone()["count"]
            connection.execute(
                self._sql(
                    "UPDATE operational_incidents SET status=?,updated_at=? WHERE incident_id=?"
                ),
                (
                    "recovered" if remaining == 0 else "open",
                    _now(),
                    str(outcome.incident_id),
                ),
            )
        return {
            "incident_id": str(outcome.incident_id),
            "status": outcome.status,
            "recorded": True,
        }

    def queue(self, limit: int = 100) -> list[dict[str, Any]]:
        """Operator queue includes every unresolved installation and all evidence."""
        with self._connection() as connection:
            self._schema(connection)
            rows = connection.execute(
                self._sql(
                    "SELECT * FROM operational_incidents WHERE status!='recovered' ORDER BY updated_at LIMIT ?"
                ),
                (max(1, min(limit, 1000)),),
            ).fetchall()
            return [self._details(connection, dict(row)) for row in rows]

    def show(self, incident_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            self._schema(connection)
            row = connection.execute(
                self._sql("SELECT * FROM operational_incidents WHERE incident_id=?"),
                (incident_id,),
            ).fetchone()
            if row is None:
                raise IncidentNotFound("Incident is unavailable")
            return self._details(connection, dict(row))

    def _details(self, connection: Any, incident: dict[str, Any]) -> dict[str, Any]:
        incident["remedy"] = json.loads(incident.pop("remedy_json"))
        incident["reports"] = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                self._sql(
                    "SELECT payload_json FROM operational_reports WHERE incident_id=? ORDER BY created_at"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        incident["deliveries"] = [
            dict(row)
            for row in connection.execute(
                self._sql(
                    "SELECT installation_id,status,updated_at FROM operational_deliveries WHERE incident_id=?"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        incident["outcomes"] = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                self._sql(
                    "SELECT payload_json FROM operational_outcomes WHERE incident_id=? ORDER BY created_at"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        return incident
