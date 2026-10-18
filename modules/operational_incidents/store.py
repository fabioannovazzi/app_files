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
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import psycopg

from modules.operational_incidents.contracts import (
    Credentials,
    DeviceCredentials,
    Outcome,
    RecoveryEvent,
    Remedy,
    Report,
    ReporterStatus,
)
from modules.operational_incidents.evidence import (
    capture_coverage,
    diagnostic_followup,
    incident_summary,
    remedy_followup,
)
from modules.pdp.postgres_compat import (
    DICT_ROW_FACTORY,
    connect_pdp_database,
    is_postgres_enabled,
)
from modules.utilities.cache import get_cache_dir
from modules.workflow_usage import repository as workflow_repository
from modules.workflow_usage import testing as workflow_testing
from modules.workflow_usage.contracts import WorkflowEvent
from modules.workflow_usage.products import Product, product_name
from modules.workflow_usage.reporting import evidence_hash

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
    "CREATE TABLE IF NOT EXISTS operational_installation_products (installation_id TEXT PRIMARY KEY, product TEXT NOT NULL)",
    *workflow_repository.SCHEMA,
    *workflow_testing.SCHEMA,
    "CREATE TABLE IF NOT EXISTS operational_host_sessions (device_id TEXT NOT NULL, session_id TEXT NOT NULL, payload_json TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY KEY (device_id,session_id))",
    "CREATE TABLE IF NOT EXISTS operational_app_links (installation_id TEXT PRIMARY KEY, app_installation_id TEXT NOT NULL, native_app TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_reporter_sessions (installation_id TEXT NOT NULL, session_id TEXT NOT NULL, payload_json TEXT NOT NULL, last_seen TEXT NOT NULL, PRIMARY KEY (installation_id,session_id))",
    "CREATE TABLE IF NOT EXISTS operational_devices (device_id TEXT PRIMARY KEY, key_hash TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_device_links (installation_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, recorded_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS operational_recovery_events (event_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, incident_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)",
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


def _report_payload(report: Report) -> dict[str, Any]:
    """Keep immutable legacy retry bytes while adding optional evidence fields."""
    payload = report.model_dump(mode="json")
    for name in (
        "session_id",
        "operation_id",
        "input_binding",
        "worker_runtime_version",
        "worker_platform",
        "response_to_remedy_revision",
    ):
        if payload[name] is None:
            payload.pop(name)
    if payload["capture_state"] == "legacy":
        payload.pop("capture_state")
    for diagnostic in payload["diagnostics"]:
        if not diagnostic["technical_frames"]:
            diagnostic.pop("technical_frames")
    return payload


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
            if self._installation_product(
                connection, str(credentials.installation_id)
            ) != self._installation_product(connection, str(credentials.connection_id)):
                raise IncidentNotFound("Installation is outside the connector product")
            return
        actual = hashlib.sha256(credentials.installation_key.encode()).hexdigest()
        if row is None or not hmac.compare_digest(row["key_hash"], actual):
            raise IncidentNotFound("Installation capability is unavailable")

    def workflow_record(
        self, actor: Credentials | ConnectionActor, event: WorkflowEvent
    ) -> dict[str, Any]:
        """Record task events using the already-proven installation identity."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, actor)
            owner = self._workflow_owner(connection, actor, str(event.run_id))
            return workflow_repository.record(
                connection,
                self._sql,
                owner,
                event,
                _now(),
                product=self._installation_product(connection, owner),
            )

    def _workflow_owner(
        self, connection: Any, actor: Credentials | ConnectionActor, run_id: str
    ) -> str:
        row = workflow_repository.get_run(connection, self._sql, run_id)
        owner = (
            row["installation_id"] if row is not None else str(actor.installation_id)
        )
        if owner != str(actor.installation_id):
            if not isinstance(actor, ConnectionActor):
                raise IncidentNotFound("Run is outside this installation")
            self._authorize(
                connection, ConnectionActor(UUID(owner), actor.connection_id)
            )
        return owner

    def workflow_status(
        self, actor: Credentials | ConnectionActor, run_id: str
    ) -> dict[str, Any]:
        """Return one authorized task with all exact event evidence."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, actor)
            self._workflow_owner(connection, actor, run_id)
            row = workflow_repository.get_run(connection, self._sql, run_id)
            if row is None:
                raise IncidentNotFound("Task has not reached the server")
            events = connection.execute(
                self._sql(
                    "SELECT payload_json,received_at,sequence FROM vera_workflow_events WHERE run_id=? ORDER BY sequence"
                ),
                (run_id,),
            ).fetchall()
            return {
                **json.loads(row["projection_json"]),
                "events": [
                    {
                        "event": json.loads(item["payload_json"]),
                        "server_sequence": item["sequence"],
                        "received_at": item["received_at"],
                    }
                    for item in events
                ],
                "feedback_url": f"https://mparanza.com/{self._installation_product(connection, row['installation_id'])}/feedback/{run_id}#{row['feedback_key']}",
            }

    def workflow_feedback(
        self,
        run_id: str,
        key: str,
        event_id: UUID,
        stars: int,
        comment: str | None,
        product: Product = "vera",
    ) -> dict[str, Any]:
        """Persist an explicit form answer under its run-specific capability."""
        with self._connection() as connection:
            self._schema(connection)
            return workflow_repository.feedback(
                connection,
                self._sql,
                run_id,
                key,
                event_id,
                stars,
                comment,
                _now(),
                product,
            )

    def workflow_inspect(self, run_id: str) -> dict[str, Any]:
        """Operator-only exact evidence; no capability keys or client material."""
        UUID(run_id)
        with self._connection() as connection:
            self._schema(connection)
            row = workflow_repository.get_run(connection, self._sql, run_id)
            if row is None:
                raise IncidentNotFound("Unknown workflow run")
            events = connection.execute(
                self._sql(
                    "SELECT payload_json,received_at FROM vera_workflow_events WHERE run_id=? ORDER BY sequence"
                ),
                (run_id,),
            ).fetchall()
            projection = json.loads(row["projection_json"])
            inspected = {
                "run": projection,
                "events": [
                    {
                        "event": json.loads(item["payload_json"]),
                        "received_at": item["received_at"],
                    }
                    for item in events
                ],
            }

            return {**inspected, "evidence_sha256": evidence_hash(inspected)}

    def workflow_overview(self, limit: int = 10000) -> dict[str, Any]:
        """Operator-only inventory; never expose installation usage publicly."""
        if not 1 <= limit <= 100000:
            raise ValueError("Usage inventory limit must be 1–100000")
        with self._connection() as connection:
            self._schema(connection)
            return workflow_repository.overview(connection, self._sql, limit)

    def workflow_testing_reset(
        self, agent_devices: list[str], product: Product = "vera"
    ) -> dict[str, Any]:
        """Operator-only reset of the public testing counter; preserve all work."""
        with self._connection() as connection:
            self._schema(connection)
            return workflow_testing.reset(
                connection, self._sql, agent_devices, _now(), product
            )

    def workflow_testing(self, product: Product = "vera") -> dict[str, Any]:
        """Operator evidence for the current public testing levels."""
        with self._connection() as connection:
            self._schema(connection)
            return workflow_testing.inspect(connection, self._sql, product)

    def _installation_product(self, connection: Any, installation_id: str) -> Product:
        """Legacy installations retain their original Vera namespace."""
        row = connection.execute(
            self._sql(
                "SELECT product FROM operational_installation_products WHERE installation_id=?"
            ),
            (installation_id,),
        ).fetchone()
        return product_name(row["product"] if row else "vera")

    def product(self, actor: Credentials | ConnectionActor) -> Product:
        """Return the authenticated installation's immutable product namespace."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, actor)
            return self._installation_product(connection, str(actor.installation_id))

    def register(
        self,
        credentials: Credentials,
        device: DeviceCredentials | None = None,
        native_status: ReporterStatus | None = None,
        product: Product | None = None,
    ) -> dict[str, Any]:
        """Register an installation; host linkage requires both local capabilities."""
        with self._connection() as connection:
            self._schema(connection)
            previous = connection.execute(
                self._sql(
                    "SELECT installation_id FROM operational_installations WHERE installation_id=?"
                ),
                (str(credentials.installation_id),),
            ).fetchone()
            registered_product = self._installation_product(
                connection, str(credentials.installation_id)
            )
            selected_product = product_name(product or registered_product)
            if previous is not None and selected_product != registered_product:
                raise IncidentConflict(
                    "Installation already belongs to another product"
                )
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
            connection.execute(
                self._sql(
                    "INSERT INTO operational_installation_products VALUES (?,?) ON CONFLICT (installation_id) DO NOTHING"
                ),
                (str(credentials.installation_id), selected_product),
            )
            if device is not None:
                self._link_device(connection, credentials, device)
            if native_status is not None:
                if device is None or device.native_app != native_status.host:
                    raise IncidentConflict(
                        "Native observation requires matching host proof"
                    )
                connection.execute(
                    self._sql(
                        "INSERT INTO operational_host_sessions VALUES (?,?,?,?) ON CONFLICT (device_id,session_id) DO UPDATE SET payload_json=excluded.payload_json,last_seen=excluded.last_seen"
                    ),
                    (
                        str(device.device_id),
                        str(native_status.session_id),
                        _json(native_status.model_dump(mode="json")),
                        _now(),
                    ),
                )
        result = {
            "installation_id": str(credentials.installation_id),
            "registered": True,
        }
        if device is not None:
            result["device_id"] = str(device.device_id)
            if device.native_app is not None:
                result["app_installation_id"] = str(
                    uuid5(device.device_id, "vera-app:" + device.native_app)
                )
                result["native_app"] = device.native_app
        return result

    def _link_device(
        self, connection: Any, credentials: Credentials, device: DeviceCredentials
    ) -> None:
        """Match opaque host and installation proofs, never hostnames or IPs."""
        digest = hashlib.sha256(device.device_key.encode()).hexdigest()
        connection.execute(
            self._sql(
                "INSERT INTO operational_devices VALUES (?,?,?) ON CONFLICT (device_id) DO NOTHING"
            ),
            (str(device.device_id), digest, _now()),
        )
        recorded = connection.execute(
            self._sql("SELECT key_hash FROM operational_devices WHERE device_id=?"),
            (str(device.device_id),),
        ).fetchone()
        if recorded is None or not hmac.compare_digest(recorded["key_hash"], digest):
            raise IncidentNotFound("Host capability is unavailable")
        previous = connection.execute(
            self._sql(
                "SELECT device_id FROM operational_device_links WHERE installation_id=?"
            ),
            (str(credentials.installation_id),),
        ).fetchone()
        if previous is not None and previous["device_id"] != str(device.device_id):
            raise IncidentConflict("Installation already belongs to another host")
        connection.execute(
            self._sql(
                "INSERT INTO operational_device_links VALUES (?,?,?) ON CONFLICT (installation_id) DO NOTHING"
            ),
            (str(credentials.installation_id), str(device.device_id), _now()),
        )
        if device.native_app is None:
            return
        app_id = str(uuid5(device.device_id, "vera-app:" + device.native_app))
        previous_app = connection.execute(
            self._sql(
                "SELECT app_installation_id FROM operational_app_links WHERE installation_id=?"
            ),
            (str(credentials.installation_id),),
        ).fetchone()
        if previous_app is not None and previous_app["app_installation_id"] != app_id:
            raise IncidentConflict(
                "Reporter instance already belongs to another native app"
            )
        connection.execute(
            self._sql(
                "INSERT INTO operational_app_links VALUES (?,?,?,?) ON CONFLICT (installation_id) DO NOTHING"
            ),
            (str(credentials.installation_id), app_id, device.native_app, _now()),
        )

    def link_connection(self, actor: ConnectionActor, credentials: Credentials) -> None:
        """Link local state only with proof of both the connection and local capability."""
        self.register(credentials, product=self.product(actor))
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
        incidents: list[dict[str, Any]] = []
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
            "poll_after_seconds": 60,
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
        payload = _report_payload(report)
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
            ) or any(
                payload.get(key) != source.get(key)
                for key in ("session_id", "operation_id", "input_binding")
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
            if report.response_to_remedy_revision is not None:
                request = connection.execute(
                    self._sql(
                        "SELECT remedy_json FROM operational_remedy_revisions WHERE incident_id=? AND revision=?"
                    ),
                    (original["incident_id"], report.response_to_remedy_revision),
                ).fetchone()
                request_value = json.loads(request["remedy_json"]) if request else {}
                if request_value.get(
                    "kind"
                ) != "diagnostic-request" or request_value.get(
                    "target_report_id"
                ) != str(
                    report.evidence_for_report_id
                ):
                    raise IncidentConflict(
                        "Diagnostic reply does not match a retained request for this report"
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
        if report.product != self.product(credentials):
            raise IncidentConflict("Report belongs to another product")
        if report.evidence_for_report_id is not None:
            return self._supplement(credentials, report)
        payload = _report_payload(report)
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
                                "codex": f"https://mparanza.com/static/shared/plugin-downloads/index.html?product={self._installation_product(connection, str(credentials.installation_id))}&lang=it",
                                "cowork": f"https://mparanza.com/static/shared/{self._installation_product(connection, str(credentials.installation_id))}/downloads/{self._installation_product(connection, str(credentials.installation_id))}-cowork-plugin.zip",
                            }
                            if remedy["kind"] == "update"
                            else {}
                        ),
                    }
                )
                original_row = connection.execute(
                    self._sql(
                        "SELECT payload_json,created_at FROM operational_reports WHERE report_id=?"
                    ),
                    (row["latest_report_id"],),
                ).fetchone()
                supplements = [
                    json.loads(item["payload_json"])
                    for item in connection.execute(
                        self._sql(
                            "SELECT payload_json FROM operational_report_evidence WHERE original_report_id=?"
                        ),
                        (row["latest_report_id"],),
                    ).fetchall()
                ]
                incidents[-1]["capture"] = capture_coverage(
                    json.loads(original_row["payload_json"]),
                    supplements,
                    original_row["created_at"],
                )
                if remedy["kind"] == "diagnostic-request":
                    replies = [
                        item["report_id"]
                        for item in supplements
                        if item.get("response_to_remedy_revision") == revision
                    ]
                    incidents[-1]["diagnostic_exchange"] = {
                        "request_revision": revision,
                        "state": "responded" if replies else "awaiting-vera",
                        "response_report_ids": replies,
                    }
        for incident in incidents:
            if incident["remedy"]["kind"] != "investigating":
                self.progress(
                    credentials,
                    RecoveryEvent(
                        event_id=uuid5(
                            NAMESPACE_URL,
                            f"{credentials.installation_id}:{incident['latest_report_id']}:{incident['revision']}:received",
                        ),
                        incident_id=incident["incident_id"],
                        report_id=incident["latest_report_id"],
                        remedy_revision=incident["revision"],
                        kind="remedy-received",
                        operation_id=incident["report_metadata"].get("operation_id"),
                    ),
                )
        return {"incidents": incidents, "poll_after_seconds": 60}

    def progress(
        self, credentials: Credentials | ConnectionActor, event: RecoveryEvent
    ) -> dict[str, Any]:
        """Record an observed step; progress never closes an original task."""
        encoded = _json(event.model_dump(mode="json"))
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            original = connection.execute(
                self._sql(
                    "SELECT * FROM operational_reports WHERE report_id=? AND installation_id=? AND incident_id=?"
                ),
                (
                    str(event.report_id),
                    str(credentials.installation_id),
                    str(event.incident_id),
                ),
            ).fetchone()
            if original is None:
                raise IncidentNotFound(
                    "Original report is outside the installation scope"
                )
            latest = connection.execute(
                self._sql(
                    "SELECT report_id FROM operational_reports WHERE installation_id=? AND incident_id=? ORDER BY created_at DESC LIMIT 1"
                ),
                (str(credentials.installation_id), str(event.incident_id)),
            ).fetchone()
            row = connection.execute(
                self._sql(
                    "SELECT revision FROM operational_incidents WHERE incident_id=?"
                ),
                (str(event.incident_id),),
            ).fetchone()
            revision, _ = self._applicable_remedy(
                connection,
                str(event.incident_id),
                str(event.report_id),
                row["revision"],
            )
            payload = json.loads(original["payload_json"])
            if (
                latest["report_id"] != str(event.report_id)
                or revision != event.remedy_revision
            ):
                raise IncidentConflict(
                    "Progress does not match the current original episode"
                )
            if payload.get("operation_id") is not None and payload[
                "operation_id"
            ] != str(event.operation_id):
                raise IncidentConflict("Progress belongs to another operation")
            previous = connection.execute(
                self._sql(
                    "SELECT payload_json,installation_id FROM operational_recovery_events WHERE event_id=?"
                ),
                (str(event.event_id),),
            ).fetchone()
            if previous is not None and (
                previous["payload_json"] != encoded
                or previous["installation_id"] != str(credentials.installation_id)
            ):
                raise IncidentConflict(
                    "Recovery event identifier belongs to different evidence"
                )
            connection.execute(
                self._sql(
                    "INSERT INTO operational_recovery_events VALUES (?,?,?,?,?) ON CONFLICT (event_id) DO NOTHING"
                ),
                (
                    str(event.event_id),
                    str(credentials.installation_id),
                    str(event.incident_id),
                    encoded,
                    _now(),
                ),
            )
        return {
            "recorded": True,
            "event_id": str(event.event_id),
            "kind": event.kind,
            "installation_id": str(credentials.installation_id),
            "report_id": str(event.report_id),
            "incident_id": str(event.incident_id),
        }

    def remedy(
        self, incident_id: str, remedy: Remedy, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
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
            if expected_revision is not None and row["revision"] != expected_revision:
                raise IncidentConflict(
                    "Incident changed since diagnosis; inspect it again"
                )
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
                applicable_revision, applicable = self._applicable_remedy(
                    connection,
                    incident_id,
                    str(remedy.target_report_id),
                    row["revision"],
                )
                # Exact equality prevents repeated polls from triggering another retry.
                # This is delivery idempotency, not semantic diagnosis.
                if Remedy.model_validate(applicable) == remedy:
                    return {
                        "incident_id": incident_id,
                        "revision": applicable_revision,
                        "status": "awaiting-recovery",
                        "deduplicated": True,
                    }
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
            "deduplicated": False,
        }

    def outcome(
        self, credentials: Credentials | ConnectionActor, outcome: Outcome
    ) -> dict[str, Any]:
        """Close this delivery only after an actual successful execution receipt."""
        if outcome.status == "recovered" and not outcome.execution_succeeded:
            raise IncidentConflict("Recovery requires successful execution evidence")
        payload = outcome.model_dump(mode="json")
        for name in ("operation_id", "input_binding", "original_task_verified"):
            if not payload[name]:
                payload.pop(name)
        encoded = _json(payload)
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
            revision, applicable = self._applicable_remedy(
                connection,
                str(outcome.incident_id),
                latest["report_id"],
                row["revision"],
            )
            if revision != outcome.remedy_revision:
                raise IncidentConflict(
                    "Remedy changed; read current status before reporting recovery"
                )
            if (
                applicable["kind"] == "diagnostic-request"
                and outcome.status == "recovered"
            ):
                raise IncidentConflict(
                    "A diagnostic exchange cannot certify original-task recovery"
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
            source = json.loads(
                connection.execute(
                    self._sql(
                        "SELECT payload_json FROM operational_reports WHERE report_id=?"
                    ),
                    (latest["report_id"],),
                ).fetchone()["payload_json"]
            )
            if outcome.status == "recovered" and not outcome.original_task_verified:
                raise IncidentConflict(
                    "Recovery requires verification of the original task"
                )
            if outcome.status == "recovered" and source.get("operation_id") is not None:
                if (
                    not outcome.original_task_verified
                    or source["operation_id"] != str(outcome.operation_id)
                    or (
                        source.get("input_binding") is not None
                        and source["input_binding"] != outcome.input_binding
                    )
                ):
                    raise IncidentConflict(
                        "Recovery requires verification of the original operation and inputs"
                    )
                attempts = connection.execute(
                    self._sql(
                        "SELECT payload_json FROM operational_recovery_events WHERE installation_id=? AND incident_id=?"
                    ),
                    (str(credentials.installation_id), str(outcome.incident_id)),
                ).fetchall()
                if not any(
                    (event := json.loads(attempt["payload_json"]))["kind"]
                    == "retry-succeeded"
                    and event["report_id"] == str(outcome.report_id)
                    and event["remedy_revision"] == outcome.remedy_revision
                    and event["operation_id"] == str(outcome.operation_id)
                    for attempt in attempts
                ):
                    raise IncidentConflict(
                        "Recovery requires a successful original-operation retry"
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

    def observe_reporter(
        self, credentials: Credentials | ConnectionActor, status: ReporterStatus
    ) -> None:
        """Save observed capabilities without claiming other sessions updated."""
        with self._connection() as connection:
            self._schema(connection)
            self._authorize(connection, credentials)
            connection.execute(
                self._sql(
                    "INSERT INTO operational_reporter_sessions(installation_id,session_id,payload_json,last_seen) VALUES(?,?,?,?) ON CONFLICT(installation_id,session_id) DO UPDATE SET payload_json=excluded.payload_json,last_seen=excluded.last_seen"
                ),
                (
                    str(credentials.installation_id),
                    str(status.session_id),
                    _json(status.model_dump(mode="json")),
                    _now(),
                ),
            )

    def installation(self, installation_id: str) -> dict[str, Any]:
        """Operator lookup includes history and host links, without any credential."""
        identifier = str(UUID(installation_id))
        with self._connection() as connection:
            self._schema(connection)
            row = connection.execute(
                self._sql(
                    "SELECT installation_id,created_at FROM operational_installations WHERE installation_id=?"
                ),
                (identifier,),
            ).fetchone()
            if row is None:
                raise IncidentNotFound("Installation is unavailable")
            device = connection.execute(
                self._sql(
                    "SELECT device_id,recorded_at FROM operational_device_links WHERE installation_id=?"
                ),
                (identifier,),
            ).fetchone()
            app = connection.execute(
                self._sql(
                    "SELECT app_installation_id,native_app,recorded_at FROM operational_app_links WHERE installation_id=?"
                ),
                (identifier,),
            ).fetchone()
            connections = connection.execute(
                self._sql(
                    "SELECT connection_id FROM operational_connection_links WHERE installation_id=?"
                ),
                (identifier,),
            ).fetchall()
            incidents = connection.execute(
                self._sql(
                    "SELECT i.* FROM operational_incidents i JOIN operational_deliveries d ON i.incident_id=d.incident_id WHERE d.installation_id=? ORDER BY i.created_at"
                ),
                (identifier,),
            ).fetchall()
            sessions = connection.execute(
                self._sql(
                    "SELECT payload_json,last_seen FROM operational_reporter_sessions WHERE installation_id=? ORDER BY last_seen DESC"
                ),
                (identifier,),
            ).fetchall()
            return {
                **dict(row),
                "product": self._installation_product(connection, identifier),
                "host_link": dict(device) if device else None,
                "app_link": dict(app) if app else None,
                "saved_connections": [item["connection_id"] for item in connections],
                "reporter_sessions": [
                    {**json.loads(item["payload_json"]), "last_seen": item["last_seen"]}
                    for item in sessions
                ],
                "incidents": [
                    self._details(connection, dict(item)) for item in incidents
                ],
            }

    def app_installation(self, app_installation_id: str) -> dict[str, Any]:
        """Inspect one proven app profile across task-local reporter instances."""
        identifier = str(UUID(app_installation_id))
        queries = {
            "reports": "SELECT r.* FROM operational_reports r JOIN operational_app_links a ON a.installation_id=r.installation_id WHERE a.app_installation_id=? ORDER BY r.created_at",
            "evidence": "SELECT e.* FROM operational_report_evidence e JOIN operational_app_links a ON a.installation_id=e.installation_id WHERE a.app_installation_id=? ORDER BY e.created_at",
            "outcomes": "SELECT o.* FROM operational_outcomes o JOIN operational_app_links a ON a.installation_id=o.installation_id WHERE a.app_installation_id=? ORDER BY o.created_at",
            "recovery_events": "SELECT e.* FROM operational_recovery_events e JOIN operational_app_links a ON a.installation_id=e.installation_id WHERE a.app_installation_id=? ORDER BY e.created_at",
        }
        with self._connection() as connection:
            self._schema(connection)
            members = connection.execute(
                self._sql(
                    "SELECT a.installation_id,a.native_app,a.recorded_at,d.device_id FROM operational_app_links a JOIN operational_device_links d ON d.installation_id=a.installation_id WHERE a.app_installation_id=? ORDER BY a.installation_id"
                ),
                (identifier,),
            ).fetchall()
            if not members:
                raise IncidentNotFound("Native app installation is unavailable")
            evidence: dict[str, Any] = {}
            for name, query in queries.items():
                records = []
                for row in connection.execute(
                    self._sql(query), (identifier,)
                ).fetchall():
                    record = dict(row)
                    payload = json.loads(record.pop("payload_json"))
                    records.append({**record, "payload": payload})
                evidence[name] = records
            deliveries = [
                dict(row)
                for row in connection.execute(
                    self._sql(
                        "SELECT d.* FROM operational_deliveries d JOIN operational_app_links a ON a.installation_id=d.installation_id WHERE a.app_installation_id=? ORDER BY d.incident_id,d.installation_id"
                    ),
                    (identifier,),
                ).fetchall()
            ]
            return {
                "app_installation_id": identifier,
                "native_app": members[0]["native_app"],
                "device_id": members[0]["device_id"],
                "reporter_instances": [dict(row) for row in members],
                "native_broker_sessions": [
                    {**json.loads(row["payload_json"]), "last_seen": row["last_seen"]}
                    for row in connection.execute(
                        self._sql(
                            "SELECT payload_json,last_seen FROM operational_host_sessions WHERE device_id=? ORDER BY last_seen"
                        ),
                        (members[0]["device_id"],),
                    ).fetchall()
                    if json.loads(row["payload_json"])["host"]
                    == members[0]["native_app"]
                ],
                "incident_ids": sorted({row["incident_id"] for row in deliveries}),
                "deliveries": deliveries,
                **evidence,
                "scope": "Only this linked native app profile. Use show on each incident ID for full investigation and applicable remedy history. Delivery state alone does not certify original-task recovery.",
            }

    def registry(self) -> dict[str, Any]:
        """Count all recorded affected identities without a queue-size assumption."""
        queries = {
            "registered_installations": "SELECT COUNT(*) AS n FROM operational_installations",
            "linked_host_devices": "SELECT COUNT(DISTINCT device_id) AS n FROM operational_device_links",
            "reports_received": "SELECT COUNT(*) AS n FROM operational_reports",
            "reporting_installations": "SELECT COUNT(DISTINCT installation_id) AS n FROM operational_reports",
            "unresolved_installations": "SELECT COUNT(DISTINCT installation_id) AS n FROM operational_deliveries WHERE status!='recovered'",
            "unresolved_linked_host_devices": "SELECT COUNT(DISTINCT h.device_id) AS n FROM operational_device_links h JOIN operational_deliveries d ON d.installation_id=h.installation_id WHERE d.status!='recovered'",
            "unresolved_unlinked_installations": "SELECT COUNT(DISTINCT d.installation_id) AS n FROM operational_deliveries d LEFT JOIN operational_device_links h ON h.installation_id=d.installation_id WHERE d.status!='recovered' AND h.device_id IS NULL",
            "linked_app_installations": "SELECT COUNT(DISTINCT app_installation_id) AS n FROM operational_app_links",
            "unresolved_linked_app_installations": "SELECT COUNT(DISTINCT a.app_installation_id) AS n FROM operational_app_links a JOIN operational_deliveries d ON d.installation_id=a.installation_id WHERE d.status!='recovered'",
            "unresolved_app_unlinked_instances": "SELECT COUNT(DISTINCT d.installation_id) AS n FROM operational_deliveries d LEFT JOIN operational_app_links a ON a.installation_id=d.installation_id WHERE d.status!='recovered' AND a.installation_id IS NULL",
        }
        with self._connection() as connection:
            self._schema(connection)
            result = {
                name: connection.execute(query).fetchone()["n"]
                for name, query in queries.items()
            }
        return {
            **result,
            "registered_reporter_instances": result["registered_installations"],
            "reporting_instances": result["reporting_installations"],
            "unresolved_instances": result["unresolved_installations"],
            "identity_units": "Legacy installation-count fields count reporter instances, which may be task-local. Linked app installations are proven native app profiles under host identities; they are not plugin-copy or population counts.",
            "coverage_basis": "registered and reporting identities only; unlinked app and host identities remain unknown",
        }

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
        report_rows = connection.execute(
            self._sql(
                "SELECT report_id,installation_id,created_at,payload_json FROM operational_reports WHERE incident_id=? ORDER BY created_at"
            ),
            (incident["incident_id"],),
        ).fetchall()
        incident["reports"] = [json.loads(row["payload_json"]) for row in report_rows]
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
        outcome_rows = connection.execute(
            self._sql(
                "SELECT installation_id,created_at,payload_json FROM operational_outcomes WHERE incident_id=? ORDER BY created_at"
            ),
            (incident["incident_id"],),
        ).fetchall()
        incident["outcomes"] = [json.loads(row["payload_json"]) for row in outcome_rows]
        incident["outcome_records"] = [
            {
                "installation_id": row["installation_id"],
                "recorded_at": row["created_at"],
                "payload": payload,
            }
            for row, payload in zip(outcome_rows, incident["outcomes"])
        ]
        devices = {
            row["installation_id"]: row["device_id"]
            for row in connection.execute(
                "SELECT installation_id,device_id FROM operational_device_links"
            ).fetchall()
        }
        apps = {
            row["installation_id"]: {
                key: row[key]
                for key in ("app_installation_id", "native_app", "recorded_at")
            }
            for row in connection.execute(
                self._sql(
                    "SELECT DISTINCT a.* FROM operational_app_links a JOIN operational_reports r ON a.installation_id=r.installation_id WHERE r.incident_id=?"
                ),
                (incident["incident_id"],),
            ).fetchall()
        }
        records = [
            {
                "report_id": row["report_id"],
                "installation_id": row["installation_id"],
                "created_at": row["created_at"],
                "payload": payload,
            }
            for row, payload in zip(report_rows, incident["reports"])
        ]
        coverage = [
            capture_coverage(row["payload"], incident["evidence"], row["created_at"])
            for row in records
        ]
        incident["report_records"] = [
            {
                **{
                    key: row[key]
                    for key in ("report_id", "installation_id", "created_at")
                },
                "device_id": devices.get(row["installation_id"]),
                "reporter_instance_id": row["installation_id"],
                "app_link": apps.get(row["installation_id"]),
                "capture": capture,
            }
            for row, capture in zip(records, coverage)
        ]
        incident["reporting_summary"] = incident_summary(
            records,
            devices,
            coverage,
            {
                identifier: value["app_installation_id"]
                for identifier, value in apps.items()
            },
        )
        incident["recovery_events"] = [
            {
                "installation_id": row["installation_id"],
                "recorded_at": row["created_at"],
                **json.loads(row["payload_json"]),
            }
            for row in connection.execute(
                self._sql(
                    "SELECT installation_id,created_at,payload_json FROM operational_recovery_events WHERE incident_id=? ORDER BY created_at"
                ),
                (incident["incident_id"],),
            ).fetchall()
        ]
        latest = {row["installation_id"]: row for row in records}
        incident["diagnostic_requests"] = []
        incident["remedy_followups"] = []
        for delivery in incident["deliveries"]:
            original = latest[delivery["installation_id"]]
            revision, remedy = self._applicable_remedy(
                connection,
                incident["incident_id"],
                original["report_id"],
                incident["revision"],
            )
            published = next(
                row["recorded_at"]
                for row in incident["remedy_revisions"]
                if row["revision"] == revision
            )
            session = connection.execute(
                self._sql(
                    "SELECT payload_json,last_seen FROM operational_reporter_sessions WHERE installation_id=? ORDER BY last_seen DESC LIMIT 1"
                ),
                (original["installation_id"],),
            ).fetchone()
            contact = (
                {
                    **json.loads(session["payload_json"]),
                    "last_seen": session["last_seen"],
                }
                if session
                else None
            )
            followup = remedy_followup(
                original=original,
                remedy=remedy,
                revision=revision,
                published_at=published,
                supplements=incident["evidence"],
                events=incident["recovery_events"],
                outcomes=incident["outcome_records"],
                reporter_contact=contact,
            )
            followup.update(
                device_id=devices.get(original["installation_id"]),
                app_link=apps.get(original["installation_id"]),
            )
            incident["remedy_followups"].append(followup)
            if (
                remedy["kind"] == "diagnostic-request"
                and delivery["status"] != "recovered"
            ):
                incident["diagnostic_requests"].append(
                    diagnostic_followup(
                        report_id=original["report_id"],
                        installation_id=original["installation_id"],
                        revision=revision,
                        published_at=published,
                        supplements=incident["evidence"],
                        events=incident["recovery_events"],
                        last_reporter_seen_at=contact["last_seen"] if contact else None,
                    )
                )
        return incident
