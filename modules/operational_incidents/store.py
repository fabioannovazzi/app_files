"""Durable incident, delivery and outcome records with capability-scoped access."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg

from modules.operational_incidents.contracts import Credentials, Outcome, Remedy, Report
from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    connect_pdp_database,
    is_postgres_enabled,
)
from modules.utilities.cache import get_cache_dir

__all__ = ["IncidentStore", "IncidentConflict", "IncidentNotFound", "ConnectionActor"]


@dataclass(frozen=True)
class ConnectionActor:
    """Server-created identity proven by the saved connector's OAuth token."""

    installation_id: UUID
    connection_id: UUID


class IncidentConflict(ValueError):
    """A retry or remedy does not match the immutable saved record."""


class IncidentNotFound(ValueError):
    """An installation capability or incident is unavailable."""


_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operational_remedy_revisions (incident_id TEXT NOT NULL, revision INTEGER NOT NULL, remedy_json TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY (incident_id,revision))",
    "CREATE TABLE IF NOT EXISTS operational_report_evidence (report_id TEXT PRIMARY KEY, original_report_id TEXT NOT NULL, installation_id TEXT NOT NULL, incident_id TEXT NOT NULL, payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_connection_links (connection_id TEXT NOT NULL, installation_id TEXT NOT NULL, PRIMARY KEY (connection_id, installation_id))",
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
                except (ValueError, OSError, sqlite3.Error):
                    self._ready = False
                    raise
                finally:
                    connection.close()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._postgres else sql

    def _schema(self, connection: Any) -> None:
        if not self._ready:
            for statement in _SCHEMA:
                connection.execute(statement)
            # Snapshot only the surviving legacy revision; lost history is unknown.
            connection.execute(
                self._sql(
                    "INSERT INTO operational_remedy_revisions SELECT incident_id,revision,remedy_json,? FROM operational_incidents WHERE 1=1 ON CONFLICT (incident_id,revision) DO NOTHING"
                ),
                (_now(),),
            )
            self._ready = True

    def _save_remedy_revision(self, connection: Any, incident_id: str) -> None:
        connection.execute(
            self._sql(
                "INSERT INTO operational_remedy_revisions SELECT incident_id,revision,remedy_json,? FROM operational_incidents WHERE incident_id=? ON CONFLICT (incident_id,revision) DO NOTHING"
            ),
            (_now(), incident_id),
        )

    def _applicable_remedy(
        self, connection: Any, incident_id: str, report_id: str, fallback_revision: int
    ) -> tuple[int, dict[str, Any]]:
        """Match explicit report identity; grouping is not proof of a common cause."""
        rows = connection.execute(
            self._sql(
                "SELECT revision,remedy_json FROM operational_remedy_revisions WHERE incident_id=? ORDER BY revision DESC"
            ),
            (incident_id,),
        ).fetchall()
        for row in rows:
            remedy = json.loads(row["remedy_json"])
            if remedy.get("target_report_id") == report_id or (
                remedy["kind"] == "investigating"
                and remedy.get("target_report_id") is None
            ):
                return row["revision"], remedy
        return fallback_revision, Remedy(
            kind="investigating",
            summary="Il problema è in diagnosi; nessun rimedio è assegnato a questa segnalazione.",
            evidence="No scoped remedy is available for this original report. Earlier overwritten revisions cannot be reconstructed.",
            expected_outcome="Successful execution of the original operation",
        ).model_dump(mode="json")

    def _authorize(
        self, connection: Any, credentials: Credentials | ConnectionActor
    ) -> None:
        row = connection.execute(
            self._sql(
                "SELECT key_hash FROM operational_installations WHERE installation_id=?"
            ),
            (str(credentials.installation_id),),
        ).fetchone()
        if isinstance(credentials, ConnectionActor):
            linked = (
                credentials.installation_id == credentials.connection_id
                or connection.execute(
                    self._sql(
                        "SELECT 1 FROM operational_connection_links WHERE connection_id=? AND installation_id=?"
                    ),
                    (str(credentials.connection_id), str(credentials.installation_id)),
                ).fetchone()
                is not None
            )
            if row is None or not linked:
                raise IncidentNotFound("Installation is outside the connector scope")
            return
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

    def link_connection(self, actor: ConnectionActor, credentials: Credentials) -> None:
        """Link local state only with proof of both the connection and local capability."""
        self.register(credentials)
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, actor)
            self._authorize(connection, credentials)
            connection.execute(
                self._sql(
                    "INSERT INTO operational_connection_links VALUES (?,?) ON CONFLICT (connection_id,installation_id) DO NOTHING"
                ),
                (str(actor.connection_id), str(credentials.installation_id)),
            )

    def connection_members(self, actor: ConnectionActor) -> list[str]:
        """Return only installation IDs cryptographically linked to this connection."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, actor)
            rows = connection.execute(
                self._sql(
                    "SELECT installation_id FROM operational_connection_links WHERE connection_id=?"
                ),
                (str(actor.connection_id),),
            ).fetchall()
        return sorted(
            {str(actor.connection_id), *(row["installation_id"] for row in rows)}
        )

    def connection_status(self, actor: ConnectionActor) -> dict[str, Any]:
        """Read remedies across saved local identities, including expired task containers."""
        incidents = []
        for identifier in self.connection_members(actor):
            member = ConnectionActor(UUID(identifier), actor.connection_id)
            incidents.extend(
                {**row, "installation_id": identifier}
                for row in self.status(member)["incidents"]
            )
        return {
            "installation_id": str(actor.connection_id),
            "binding": "saved-connector",
            "incidents": incidents,
        }

    def connection_outcome(
        self, actor: ConnectionActor, outcome: Outcome
    ) -> dict[str, Any]:
        """Bind the resumed operation to its actual report's linked installation."""
        identifier = str(actor.connection_id)
        if outcome.report_id is not None:
            with self._connection() as connection:
                self._schema(connection)
                row = connection.execute(
                    self._sql(
                        "SELECT installation_id FROM operational_reports WHERE report_id=?"
                    ),
                    (str(outcome.report_id),),
                ).fetchone()
            if row is None:
                raise IncidentNotFound("Original report is unavailable")
            identifier = row["installation_id"]
        member = ConnectionActor(UUID(identifier), actor.connection_id)
        return self.outcome(member, outcome)

    def connection_report(
        self, actor: ConnectionActor, report: Report
    ) -> dict[str, Any]:
        """Bind supplemental diagnostics to the original proven connection member."""
        member = actor
        if report.evidence_for_report_id is not None:
            with self._connection() as connection:
                self._schema(connection)
                self._authorize(connection, actor)
                row = connection.execute(
                    self._sql(
                        "SELECT installation_id FROM operational_reports WHERE report_id=?"
                    ),
                    (str(report.evidence_for_report_id),),
                ).fetchone()
            if row is None:
                raise IncidentNotFound("Original report is unavailable")
            member = ConnectionActor(UUID(row["installation_id"]), actor.connection_id)
        return self.report(member, report)

    def _supplement(
        self, credentials: Credentials | ConnectionActor, report: Report
    ) -> dict[str, Any]:
        """Append reviewed evidence without creating, reopening or replacing an episode."""
        payload = report.model_dump(mode="json")
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            original = connection.execute(
                self._sql(
                    "SELECT * FROM operational_reports WHERE report_id=? AND installation_id=?"
                ),
                (str(report.evidence_for_report_id), str(credentials.installation_id)),
            ).fetchone()
            if original is None:
                raise IncidentNotFound(
                    "Original report is outside the installation scope"
                )
            source = json.loads(original["payload_json"])
            # Exact episode binding is a mechanical security rule, not diagnosis.
            if any(
                payload[key] != source[key]
                for key in (
                    "product",
                    "product_version",
                    "host",
                    "platform",
                    "workflow",
                    "stage",
                )
            ):
                raise IncidentConflict(
                    "Supplemental evidence does not match the original execution"
                )
            existing = connection.execute(
                self._sql(
                    "SELECT * FROM operational_report_evidence WHERE report_id=?"
                ),
                (str(report.report_id),),
            ).fetchone()
            collision = connection.execute(
                self._sql("SELECT 1 FROM operational_reports WHERE report_id=?"),
                (str(report.report_id),),
            ).fetchone()
            if collision is not None or (
                existing is not None and existing["payload_hash"] != digest
            ):
                raise IncidentConflict(
                    "Report identifier already belongs to different evidence"
                )
            if existing is None:
                connection.execute(
                    self._sql(
                        "INSERT INTO operational_report_evidence VALUES (?,?,?,?,?,?,?)"
                    ),
                    (
                        str(report.report_id),
                        str(report.evidence_for_report_id),
                        str(credentials.installation_id),
                        original["incident_id"],
                        digest,
                        encoded,
                        _now(),
                    ),
                )
        return {
            "incident_id": original["incident_id"],
            "installation_id": str(credentials.installation_id),
            "report_id": str(report.report_id),
            "evidence_for_report_id": str(report.evidence_for_report_id),
            "recorded": True,
            "deduplicated": existing is not None,
        }

    def report(
        self, credentials: Credentials | ConnectionActor, report: Report
    ) -> dict[str, Any]:
        """Group exact technical signals for investigation, not assumed root causes."""
        if report.evidence_for_report_id is not None:
            return self._supplement(credentials, report)
        payload = report.model_dump(mode="json")
        # Preserve old retry hashes when the optional evidence link is absent.
        payload.pop("evidence_for_report_id", None)
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
                    "installation_id": str(credentials.installation_id),
                    "report_id": str(report.report_id),
                    "recorded": True,
                    "deduplicated": True,
                }
            if (
                connection.execute(
                    self._sql(
                        "SELECT 1 FROM operational_report_evidence WHERE report_id=?"
                    ),
                    (str(report.report_id),),
                ).fetchone()
                is not None
            ):
                raise IncidentConflict(
                    "Report identifier already belongs to supplemental evidence"
                )
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
            self._save_remedy_revision(connection, incident_id)
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
            "installation_id": str(credentials.installation_id),
            "report_id": str(report.report_id),
            "recorded": True,
            "deduplicated": False,
        }

    def status(self, credentials: Credentials | ConnectionActor) -> dict[str, Any]:
        """Return only this installation's incidents and structured remedies."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            rows = connection.execute(
                self._sql(
                    "SELECT i.incident_id,i.revision,i.remedy_json,d.status,(SELECT r.report_id FROM operational_reports r WHERE r.incident_id=i.incident_id AND r.installation_id=d.installation_id ORDER BY r.created_at DESC LIMIT 1) AS latest_report_id FROM operational_incidents i JOIN operational_deliveries d ON i.incident_id=d.incident_id WHERE d.installation_id=? ORDER BY i.updated_at"
                ),
                (str(credentials.installation_id),),
            ).fetchall()
            incidents = []
            for row in rows:
                revision, remedy = self._applicable_remedy(
                    connection,
                    row["incident_id"],
                    row["latest_report_id"],
                    row["revision"],
                )
                incidents.append(
                    {
                        "incident_id": row["incident_id"],
                        "revision": revision,
                        "latest_report_id": row["latest_report_id"],
                        "status": row["status"],
                        "remedy": remedy,
                        "report_metadata": {
                            key: value
                            for key, value in json.loads(
                                connection.execute(
                                    self._sql(
                                        "SELECT payload_json FROM operational_reports WHERE report_id=?"
                                    ),
                                    (row["latest_report_id"],),
                                ).fetchone()["payload_json"]
                            ).items()
                            if key not in {"diagnostics", "measurements", "unavailable"}
                        },
                        "download_urls": (
                            {
                                "codex": "https://mparanza.com/static/shared/plugin-downloads/index.html?product=vera&lang=it",
                                "cowork": "https://mparanza.com/static/shared/vera/downloads/vera-cowork-plugin.zip",
                            }
                            if remedy["kind"] == "update"
                            else {}
                        ),
                    }
                )
        return {"incidents": incidents}

    def remedy(self, incident_id: str, remedy: Remedy) -> dict[str, Any]:
        """Operator-only publication; clients cannot deliver executable commands."""
        if remedy.kind != "investigating" and remedy.target_report_id is None:
            raise IncidentConflict("A remedy must target its diagnosed original report")
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
            if remedy.target_report_id is not None:
                original = connection.execute(
                    self._sql(
                        "SELECT installation_id FROM operational_reports WHERE incident_id=? AND report_id=?"
                    ),
                    (incident_id, str(remedy.target_report_id)),
                ).fetchone()
                if original is None:
                    raise IncidentNotFound("Remedy target is outside this incident")
                delivery = connection.execute(
                    self._sql(
                        "SELECT status,(SELECT report_id FROM operational_reports WHERE incident_id=? AND installation_id=? ORDER BY created_at DESC LIMIT 1) AS latest_report_id FROM operational_deliveries WHERE incident_id=? AND installation_id=?"
                    ),
                    (
                        incident_id,
                        original["installation_id"],
                        incident_id,
                        original["installation_id"],
                    ),
                ).fetchone()
                if (
                    delivery["latest_report_id"] != str(remedy.target_report_id)
                    or delivery["status"] == "recovered"
                ):
                    raise IncidentConflict(
                        "Remedy target is obsolete or already recovered"
                    )
            self._save_remedy_revision(connection, incident_id)
            revision = row["revision"] + 1
            connection.execute(
                self._sql(
                    "UPDATE operational_incidents SET revision=?,remedy_json=?,updated_at=? WHERE incident_id=?"
                ),
                (revision, _json(remedy.model_dump(mode="json")), _now(), incident_id),
            )
            self._save_remedy_revision(connection, incident_id)
        return {
            "incident_id": incident_id,
            "revision": revision,
            "status": "awaiting-recovery",
        }

    def outcome(
        self, credentials: Credentials | ConnectionActor, outcome: Outcome
    ) -> dict[str, Any]:
        """Close this delivery only after an actual successful execution receipt."""
        if outcome.status == "recovered" and not outcome.execution_succeeded:
            raise IncidentConflict("Recovery requires successful execution evidence")
        encoded = _json(outcome.model_dump(mode="json"))
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            row = connection.execute(
                self._sql(
                    "SELECT i.revision,d.status AS delivery_status FROM operational_incidents i JOIN operational_deliveries d ON i.incident_id=d.incident_id WHERE i.incident_id=? AND d.installation_id=?"
                ),
                (str(outcome.incident_id), str(credentials.installation_id)),
            ).fetchone()
            if row is None:
                raise IncidentNotFound("Incident is unavailable")
            latest = connection.execute(
                self._sql(
                    "SELECT report_id FROM operational_reports WHERE incident_id=? AND installation_id=? ORDER BY created_at DESC LIMIT 1"
                ),
                (str(outcome.incident_id), str(credentials.installation_id)),
            ).fetchone()
            revision, _ = self._applicable_remedy(
                connection,
                str(outcome.incident_id),
                latest["report_id"],
                row["revision"],
            )
            if revision != outcome.remedy_revision:
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
                    "installation_id": str(credentials.installation_id),
                    "outcome_id": str(outcome.outcome_id),
                    "report_id": str(outcome.report_id) if outcome.report_id else None,
                    "remedy_revision": outcome.remedy_revision,
                    "status": outcome.status,
                    "recorded": True,
                }
            same_episode = (
                outcome.report_id is not None
                and str(outcome.report_id) == latest["report_id"]
            )
            if outcome.status == "recovered" and not same_episode:
                raise IncidentConflict(
                    "A newer failure exists; recovery must match the reported episode"
                )
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
            if not same_episode or (
                row["delivery_status"] == "recovered" and outcome.status != "recovered"
            ):
                return {
                    "incident_id": str(outcome.incident_id),
                    "installation_id": str(credentials.installation_id),
                    "outcome_id": str(outcome.outcome_id),
                    "report_id": str(outcome.report_id) if outcome.report_id else None,
                    "remedy_revision": outcome.remedy_revision,
                    "status": outcome.status,
                    "recorded": True,
                    "delivery_updated": False,
                }
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
            "installation_id": str(credentials.installation_id),
            "outcome_id": str(outcome.outcome_id),
            "report_id": str(outcome.report_id) if outcome.report_id else None,
            "remedy_revision": outcome.remedy_revision,
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
        incident["remedy_revisions"] = [
            {
                "revision": row["revision"],
                "remedy": json.loads(row["remedy_json"]),
                "recorded_at": row["recorded_at"],
            }
            for row in connection.execute(
                self._sql(
                    "SELECT revision,remedy_json,recorded_at FROM operational_remedy_revisions WHERE incident_id=? ORDER BY revision"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        incident["reports"] = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                self._sql(
                    "SELECT payload_json FROM operational_reports WHERE incident_id=? ORDER BY created_at"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        incident["evidence"] = [
            json.loads(row["payload_json"])
            for row in connection.execute(
                self._sql(
                    "SELECT payload_json FROM operational_report_evidence WHERE incident_id=? ORDER BY created_at"
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
