#!/usr/bin/env python3
"""Persist browser processes across conversations using existing teaching and CR tools.

The model owns intent, sanitization and result judgment. Fixed rules below enforce
identity, immutable evidence, supported execution and exact qualification scope.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import math
import os
import platform
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zipfile import ZipFile

from capability_pipeline import (
    canonical_json_bytes,
    execution_contract_sha256,
    finalize_capability,
    sha256_payload,
    validate_capability,
    validate_run_lock,
    validate_run_receipt,
    verify_clean_run,
)
from teaching_checkpoint import (
    read_checkpoint,
    save_checkpoint,
    summarize_checkpoint,
)

__all__ = ["ProcessStore", "main"]
LOG = logging.getLogger(__name__)
ID = re.compile(r"[a-z0-9][a-z0-9.-]{0,100}")
HOST_KEYS = {
    "execution_mode",
    "browser_control",
    "persistent_node",
    "local_files",
    "locale",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _machine_fingerprint() -> str:
    """Keep an opaque local scope guard; never export names or home paths."""
    return sha256_payload(
        {"system": sys.platform, "machine": platform.node(), "home": str(Path.home())}
    )


def _text(value: Any, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} requires bounded nonempty text")
    return value


def _safe(path: Path) -> Path:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("process storage must not follow symlinks")
    return path


def _write(path: Path, payload: Any) -> None:
    _safe(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical_json_bytes(payload))


def _read(path: Path) -> Any:
    _safe(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("process metadata exceeds size limit")
    return json.loads(path.read_bytes())


def _host(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != HOST_KEYS:
        raise ValueError("host requires observed tool capabilities and execution mode")
    if value["execution_mode"] not in {
        "simulated",
        "unverified",
        "live_connected_chrome",
    }:
        raise ValueError("unsupported host execution mode")
    if any(
        type(value[k]) is not bool
        for k in ("browser_control", "persistent_node", "local_files")
    ):
        raise ValueError("host capabilities must be explicit booleans")
    _text(value["locale"], "locale", 64)
    return value


def _cr_client(vera_root: Path) -> Any:
    """Resolve the installed product's existing durable submission client."""
    path = vera_root / "scripts" / "change_requests.py"
    spec = importlib.util.spec_from_file_location("browser_vera_change_requests", path)
    if spec is None or spec.loader is None:
        raise ValueError("Vera change-request client is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProcessStore:
    """A bounded user-local register, independent of chat and plugin cache paths."""

    def __init__(self, root: Path | None = None) -> None:
        location = root or Path(
            os.environ.get(
                "MPARANZA_BROWSER_DATA",
                Path.home() / ".codex" / "mparanza" / "browser-automation",
            )
        )
        self.root = _safe(location.expanduser().absolute())
        # Business outputs must never become repository or published artifacts.
        if any((p / ".git").exists() for p in (self.root, *self.root.parents)):
            raise ValueError("process storage must be outside a Git workspace")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.database = _safe(self.root / "processes.sqlite3")
        fd = os.open(self.database, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        self.database.chmod(0o600)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records (sequence INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, process_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS process_records ON records(process_id, kind)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(_safe(self.database), timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _put(self, key: str, process_id: str, kind: str, payload: Any) -> None:
        data = canonical_json_bytes(payload).decode()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO records(key, process_id, kind, payload, sha256) VALUES (?, ?, ?, ?, ?)",
                (key, process_id, kind, data, sha256_payload(payload)),
            )

    def _rows(
        self, process_id: str | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT key, payload, sha256 FROM records WHERE (? IS NULL OR process_id = ?) AND (? IS NULL OR kind = ?) ORDER BY sequence",
                (process_id, process_id, kind, kind),
            ).fetchall()
        result = []
        for _key, data, digest in rows:
            payload = json.loads(data)
            if sha256_payload(payload) != digest:
                raise ValueError("process record integrity mismatch")
            result.append(payload)
        return result

    def process(self, process_id: str) -> dict[str, Any]:
        records = self._rows(process_id, "process")
        if len(records) != 1:
            raise ValueError("unknown process; select from the local catalog")
        return records[0]

    def create(
        self, description: dict[str, Any], *, process_id: str | None = None
    ) -> dict[str, Any]:
        """Save the model-interpreted professional process, never a site-only route."""
        if not isinstance(description, dict) or set(description) != {
            "site",
            "process",
            "start_state",
            "end_condition",
        }:
            raise ValueError(
                "exact site, professional process and boundaries are required"
            )
        _text(description["site"], "site")
        _text(description["start_state"], "start_state")
        _text(description["end_condition"], "end_condition")
        process = description["process"]
        if not isinstance(process, dict) or set(process) != {
            "name",
            "objective",
            "out_of_scope",
        }:
            raise ValueError("process requires name, objective and exclusions")
        _text(process["name"], "process name")
        _text(process["objective"], "professional objective")
        if not isinstance(process["out_of_scope"], list) or not process["out_of_scope"]:
            raise ValueError("declare excluded work")
        for item in process["out_of_scope"]:
            _text(item, "exclusion")
        if process_id is not None and not re.fullmatch(
            r"process-[a-f0-9]{32}", process_id
        ):
            raise ValueError("invalid imported process identity")
        if process_id is not None and self._rows(process_id, "process"):
            current = self.process(process_id)
            if current["description"] != description:
                raise ValueError("imported process identity has a different boundary")
            return current
        # An identical descriptor has exactly one identity even after a chat restart.
        key = "process-" + sha256_payload(description)
        record: dict[str, Any] = {
            "process_id": process_id or "process-" + uuid4().hex,
            "description": description,
            "created_at": _now(),
        }
        try:
            self._put(key, record["process_id"], "process", record)
        except sqlite3.IntegrityError:
            current = next(
                p for p in self._rows(kind="process") if p["description"] == description
            )
            if process_id is not None and current["process_id"] != process_id:
                raise ValueError(
                    "same process already registered with another identity"
                )
            return current
        return record

    def import_feedback(
        self, archive: Path, *, cr_record: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Recover a developer's process identity from the existing reviewed handoff."""
        from development_request import verify_archive

        verify_archive(archive)
        with ZipFile(archive) as zipped:
            request = json.loads(zipped.read("request.json"))
            submitted_body = (
                json.loads(zipped.read("cr-request.json"))
                if cr_record is not None
                else None
            )
        if request["schema_version"] != "browser-development-request/v2":
            raise ValueError(
                "legacy handoff has no process identity; interpret it before registering"
            )
        lineage = request["browser_lifecycle"]
        imported_cr = None
        if cr_record is not None:
            envelope = cr_record["request"]
            # Match the CR store's compact JSON hash (the browser artifacts use
            # a different, pretty-printed canonical representation).
            server_hash = hashlib.sha256(
                json.dumps(
                    envelope,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            # The existing intake validates but preserves the exact request body.
            if (
                cr_record["plugin"] != "vera"
                or envelope["plugin"] != "vera"
                or envelope["request"] != submitted_body
                or cr_record["request_sha256"] != server_hash
                or cr_record["submission_id"] != envelope["submission_id"]
                or not re.fullmatch(r"CR-[1-9]\d*", cr_record["change_request_id"])
                or cr_record["status"] not in {"open", "fixed"}
            ):
                raise ValueError(
                    "administrative CR record does not match reviewed feedback"
                )
            imported_cr = {
                "change_request_id": cr_record["change_request_id"],
                "attempt_id": lineage["attempt_id"],
                "submission_id": cr_record["submission_id"],
                "status": cr_record["status"],
                "fixed_version": cr_record["fixed_version"],
                "source_record_sha256": sha256_payload(cr_record),
                "provenance": "existing_cr_administration_export",
            }
        process = self.create(
            lineage["process_description"], process_id=lineage["process_id"]
        )
        key = "imported-feedback:" + lineage["attempt_id"]
        try:
            self._put(
                key,
                process["process_id"],
                "imported_feedback",
                {
                    "attempt_id": lineage["attempt_id"],
                    "request": request,
                    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                },
            )
        except sqlite3.IntegrityError:
            existing = next(
                r
                for r in self._rows(process["process_id"], "imported_feedback")
                if r["attempt_id"] == lineage["attempt_id"]
            )
            if existing["request"] != request:
                raise ValueError(
                    "imported attempt already has different reviewed evidence"
                )
        if imported_cr is not None:
            try:
                self._put(
                    "developer-cr:" + sha256_payload(imported_cr),
                    process["process_id"],
                    "developer_cr",
                    imported_cr,
                )
            except sqlite3.IntegrityError:
                pass
        return process

    def add_version(
        self, process_id: str, capability_path: Path, release: dict[str, Any]
    ) -> dict[str, Any]:
        """Bind immutable executable source to the process and actual CR lineage."""
        process = self.process(process_id)
        capability = _read(capability_path)
        errors = validate_capability(capability)
        if errors:
            raise ValueError("; ".join(errors))
        if (
            capability["process"] != process["description"]["process"]
            or capability["site"]["name"] != process["description"]["site"]
        ):
            raise ValueError("capability belongs to a different professional process")
        versions = self._rows(process_id, "version")
        if versions and capability["capability_id"] != versions[0]["capability_id"]:
            raise ValueError("revisions must retain the capability identity")
        if not ID.fullmatch(capability["version"]):
            raise ValueError("unsafe capability version")
        if set(release) != {
            "plugin_version",
            "status",
            "evidence",
            "cr_ids",
        } or release["status"] not in {"built", "published", "deployed", "unknown"}:
            raise ValueError("release needs an explicit status and evidence")
        _text(release["plugin_version"], "release plugin version", 128)
        _text(release["evidence"], "release evidence")
        known_crs = {
            r["change_request_id"] for r in self._rows(process_id, "submission")
        }
        known_crs.update(
            r["change_request_id"] for r in self._rows(process_id, "developer_cr")
        )
        known_crs.update(
            c
            for binding in self._rows(process_id, "installed_binding")
            for c in binding["release"]["cr_ids"]
        )
        if (
            not isinstance(release["cr_ids"], list)
            or not set(release["cr_ids"]) <= known_crs
        ):
            raise ValueError("release CR references require returned server receipts")
        digest = sha256_payload(capability)
        for version in versions:
            if version["version"] == capability["version"]:
                if version["capability_sha256"] != digest:
                    raise ValueError(
                        "version is immutable; increment it for changed source"
                    )
                if version["release"] != release:
                    try:
                        self._put(
                            process_id
                            + ":release:"
                            + sha256_payload(
                                {"version": capability["version"], "release": release}
                            ),
                            process_id,
                            "release",
                            {
                                "version": capability["version"],
                                "execution_contract_sha256": version[
                                    "execution_contract_sha256"
                                ],
                                "release": release,
                                "recorded_at": _now(),
                            },
                        )
                    except sqlite3.IntegrityError:
                        pass
                return version
        directory = self.root / ("version-" + uuid4().hex)
        directory.mkdir(mode=0o700)
        _write(directory / "capability.json", capability)
        record = {
            "process_id": process_id,
            "capability_id": capability["capability_id"],
            "version": capability["version"],
            "capability_sha256": digest,
            "execution_contract_sha256": execution_contract_sha256(capability),
            "path": str(directory / "capability.json"),
            "release": release,
            "registered_at": _now(),
        }
        self._put(
            process_id + ":version:" + capability["version"],
            process_id,
            "version",
            record,
        )
        return record

    def sync_installed(self, module_root: Path) -> list[dict[str, Any]]:
        """Import exact shipped bindings; receiving environments remain unqualified."""
        imported = []
        for binding_path in sorted(
            _safe(module_root / "capabilities").glob("*/process.json")
        ):
            binding = _read(binding_path)
            if (
                set(binding)
                != {
                    "schema_version",
                    "process_id",
                    "description",
                    "capability_sha256",
                    "release",
                    "source_attempt_ids",
                }
                or binding["schema_version"] != "browser-process-binding/v1"
            ):
                raise ValueError("invalid installed process binding")
            if not isinstance(binding["source_attempt_ids"], list) or any(
                not re.fullmatch(r"attempt-[a-f0-9]{32}", str(a))
                for a in binding["source_attempt_ids"]
            ):
                raise ValueError("invalid development attempt lineage")
            cr_ids = binding["release"]["cr_ids"]
            if not isinstance(cr_ids, list) or any(
                not re.fullmatch(r"CR-[1-9]\d*", str(c)) for c in cr_ids
            ):
                raise ValueError("invalid declared release CR lineage")
            capability_path = binding_path.with_name("capability.json")
            capability = _read(capability_path)
            if sha256_payload(capability) != binding["capability_sha256"]:
                raise ValueError("installed binding does not match capability bytes")
            process_id = self.create(
                binding["description"], process_id=binding["process_id"]
            )["process_id"]
            try:
                self._put(
                    "installed-binding:" + sha256_payload(binding),
                    process_id,
                    "installed_binding",
                    binding,
                )
            except sqlite3.IntegrityError:
                pass
            imported.append(
                self.add_version(process_id, capability_path, binding["release"])
            )
        return imported

    def export_binding(self, process_id: str, output: Path) -> Path:
        """Write source metadata for the existing builder; exclude all run outputs."""
        process = self.process(process_id)
        version = self._version(process_id)
        releases = [
            r
            for r in self._rows(process_id, "release")
            if r["version"] == version["version"]
        ]
        current_release = releases[-1]["release"] if releases else version["release"]
        attempts = [a["attempt_id"] for a in self._rows(process_id, "attempt")]
        attempts += [
            a["attempt_id"] for a in self._rows(process_id, "imported_feedback")
        ]
        _write(
            output,
            {
                "schema_version": "browser-process-binding/v1",
                "process_id": process_id,
                "description": process["description"],
                "capability_sha256": version["capability_sha256"],
                "release": current_release,
                "source_attempt_ids": list(dict.fromkeys(attempts)),
            },
        )
        return output

    def record_release(
        self, process_id: str, version: str, evidence: dict[str, Any]
    ) -> dict[str, Any]:
        """Append release evidence without altering code or claiming retest success."""
        implementation = self._version(process_id, version)
        if set(evidence) != {
            "plugin_version",
            "status",
            "evidence",
            "cr_ids",
        } or evidence["status"] not in {"built", "published", "deployed", "unknown"}:
            raise ValueError("release requires an explicit status and evidence")
        _text(evidence["evidence"], "release evidence")
        _text(evidence["plugin_version"], "plugin version", 128)
        known = {s["change_request_id"] for s in self._rows(process_id, "submission")}
        if (
            not isinstance(evidence["cr_ids"], list)
            or not set(evidence["cr_ids"]) <= known
        ):
            raise ValueError("release CR references require returned server receipts")
        record = {
            "version": version,
            "execution_contract_sha256": implementation["execution_contract_sha256"],
            "release": evidence,
            "recorded_at": _now(),
        }
        self._put("release-" + uuid4().hex, process_id, "release", record)
        return record

    def refresh_status(
        self, process_id: str, vera_root: Path, **client_options: Any
    ) -> list[dict[str, Any]]:
        """Recover actual developer status through the existing private CR client."""
        self.process(process_id)
        request_ids = list(
            dict.fromkeys(
                s["change_request_id"] for s in self._rows(process_id, "submission")
            )
        )
        client = _cr_client(vera_root)
        results = []
        for offset in range(0, len(request_ids), 100):
            rows = client.lookup_requests(
                vera_root, request_ids[offset : offset + 100], **client_options
            )
            for row in rows:
                record = {**row, "checked_at": _now()}
                self._put("status-" + uuid4().hex, process_id, "cr_status", record)
                results.append(record)
        return results

    def _version(self, process_id: str, version: str | None = None) -> dict[str, Any]:
        versions = self._rows(process_id, "version")
        selected = [v for v in versions if version is None or v["version"] == version]
        if not selected:
            raise ValueError("no registered implementation; resume development")
        record = selected[-1]
        capability = _read(Path(record["path"]))
        if sha256_payload(capability) != record["capability_sha256"]:
            raise ValueError("registered capability changed")
        return record

    def begin(
        self,
        process_id: str,
        kind: str,
        host: dict[str, Any],
        *,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Create the durable report before browser or teaching work can fail."""
        process = self.process(process_id)
        _host(host)
        if kind not in {"teaching", "test", "use"}:
            raise ValueError("attempt kind must be teaching, test or use")
        implementations = self._rows(process_id, "version")
        implementation = (
            self._version(process_id, version)
            if kind != "teaching" and implementations
            else None
        )
        blocked = None
        if kind != "teaching":
            if implementation is None:
                blocked = "implementation_unavailable"
            elif not all(
                host[k] for k in ("browser_control", "persistent_node", "local_files")
            ):
                blocked = "host_capabilities_unavailable"
            elif kind == "use" and not self._qualified(
                process_id, implementation, host
            ):
                blocked = "qualification_required"
        attempt_id = "attempt-" + uuid4().hex
        directory = self.root / attempt_id
        directory.mkdir(mode=0o700)
        plan = {
            "schema_version": "browser-process-attempt/v1",
            "process_id": process_id,
            "attempt_id": attempt_id,
            "kind": kind,
            "host": host,
            "host_fingerprint": _machine_fingerprint(),
            "created_at": _now(),
            "description": process["description"],
            "implementation": implementation,
            "blocked_reason": blocked,
        }
        _write(directory / "attempt.json", plan)
        self._put(attempt_id, process_id, "attempt", plan)
        report = self.report(attempt_id)
        return {
            "process_id": process_id,
            "attempt_id": attempt_id,
            "attempt_directory": str(directory),
            "report_path": str(report),
            "blocked_reason": blocked,
        }

    def _attempt(self, attempt_id: str) -> tuple[dict[str, Any], Path]:
        if not ID.fullmatch(attempt_id):
            raise ValueError("unsafe attempt identity")
        directory = _safe(self.root / attempt_id)
        plan = _read(directory / "attempt.json")
        registered = [
            a
            for a in self._rows(plan["process_id"], "attempt")
            if a["attempt_id"] == attempt_id
        ]
        if registered != [plan]:
            raise ValueError("attempt identity or saved plan changed")
        return plan, directory

    def teach(
        self, attempt_id: str, payload: dict[str, Any], expected_revision: int
    ) -> dict[str, Any]:
        plan, directory = self._attempt(attempt_id)
        if plan["kind"] != "teaching":
            raise ValueError("teaching requires a teaching attempt")
        if expected_revision == 0 and payload.get("steps") != []:
            raise ValueError("start with an empty checkpoint before the demonstration")
        description = plan["description"]
        if (
            payload["objective"] != description["process"]["objective"]
            or payload["start_state"] != description["start_state"]
            or payload["end_condition"] != description["end_condition"]
        ):
            raise ValueError("checkpoint belongs to a different process boundary")
        save_checkpoint(
            directory / "teaching", payload, expected_revision=expected_revision
        )
        return {
            "checkpoint": summarize_checkpoint(directory / "teaching"),
            "report_path": str(self.report(attempt_id)),
        }

    def inspect(self, attempt_id: str) -> dict[str, Any]:
        """Retain a useful partial report when linked artifacts are missing/corrupt."""
        try:
            return self._inspect(attempt_id)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            registered = [
                a for a in self._rows(kind="attempt") if a["attempt_id"] == attempt_id
            ]
            if len(registered) != 1:
                raise ValueError("unknown attempt") from exc
            return {
                "plan": registered[0],
                "evidence": {
                    "result": "unverified",
                    "missing_reason": "saved_evidence_invalid_or_unavailable",
                    "failure_detail_sha256": hashlib.sha256(
                        str(exc).encode()
                    ).hexdigest(),
                    "elapsed_ms": None,
                    "receipt_sha256": None,
                    "outputs": [],
                },
                "teaching": None,
                "cr_ids": [
                    s["change_request_id"]
                    for s in self._rows(registered[0]["process_id"], "submission")
                    if s["attempt_id"] == attempt_id
                ],
            }

    def _inspect(self, attempt_id: str) -> dict[str, Any]:
        """Read bounded technical evidence, never private runtime output values."""
        plan, directory = self._attempt(attempt_id)
        evidence: dict[str, Any] = {
            "result": "unfinished",
            "missing_reason": "attempt_has_no_completed_execution",
            "elapsed_ms": None,
            "outputs": [],
            "receipt_sha256": None,
        }
        evidence_path = directory / "execution.json"
        if evidence_path.exists():
            evidence = _read(evidence_path)
            if (
                not isinstance(evidence.get("measurements"), dict)
                or set(evidence["measurements"])
                != {"model", "input_tokens", "output_tokens"}
                or any(
                    not isinstance(m, dict)
                    or set(m) != {"value", "source", "missing_reason"}
                    for m in evidence["measurements"].values()
                )
            ):
                raise ValueError("invalid host measurement evidence")
            if (
                evidence.get("schema_version") != "browser-process-execution/v1"
                or evidence.get("process_id") != plan["process_id"]
                or evidence.get("execution_mode") != plan["host"]["execution_mode"]
            ):
                raise ValueError("execution evidence scope mismatch")
            if evidence["attempt_id"] != attempt_id or evidence[
                "plan_sha256"
            ] != sha256_payload(plan):
                raise ValueError("execution evidence belongs to another attempt")
            receipt_path = directory / "run" / "run.receipt.json"
            if evidence["receipt_sha256"] is not None:
                receipt = _read(receipt_path)
                lock = _read(receipt_path.with_name("run.lock.json"))
                errors = validate_run_receipt(receipt) + validate_run_lock(lock)
                if (
                    errors
                    or sha256_payload(receipt) != evidence["receipt_sha256"]
                    or lock["receipt_sha256"] != evidence["receipt_sha256"]
                ):
                    raise ValueError("execution receipt integrity mismatch")
                implementation = plan["implementation"]
                if (
                    receipt["run_id"] != attempt_id
                    or receipt["capability_id"] != implementation["capability_id"]
                    or receipt["capability_version"] != implementation["version"]
                    or receipt["execution_contract_sha256"]
                    != implementation["execution_contract_sha256"]
                    or receipt["environment"]["execution_mode"]
                    != plan["host"]["execution_mode"]
                ):
                    raise ValueError("execution receipt identity mismatch")
                # Hash the local bytes without placing private outputs in context.
                output_bytes = _safe(
                    receipt_path.with_name("outputs.json")
                ).read_bytes()
                if hashlib.sha256(output_bytes).hexdigest() != lock["outputs_sha256"]:
                    raise ValueError("runtime output changed")
                evidence["outputs"] = [
                    {k: o[k] for k in ("name", "type", "record_count", "sha256")}
                    for o in receipt["outputs"]
                ]
                evidence["result"] = receipt["result"]
                evidence["recovery_used"] = receipt["locator_changes_during_run"]
        elif plan["blocked_reason"]:
            evidence["result"] = "blocked"
            evidence["missing_reason"] = plan["blocked_reason"]
        result = {
            "plan": plan,
            "evidence": evidence,
            "teaching": None,
            "cr_ids": [
                s["change_request_id"]
                for s in self._rows(plan["process_id"], "submission")
                if s["attempt_id"] == attempt_id
            ],
        }
        if (directory / "teaching").exists():
            result["teaching"] = summarize_checkpoint(directory / "teaching")
        return result

    def report(self, attempt_id: str) -> Path:
        result = self.inspect(attempt_id)
        plan, evidence = result["plan"], result["evidence"]
        directory = self.root / attempt_id
        lines = [
            f"# {plan['description']['process']['name']}",
            "",
            f"Processo: {plan['process_id']}",
            f"Tentativo: {attempt_id} · {plan['kind']}",
            f"Risultato: {evidence['result']}",
            f"Ambiente dichiarato: {plan['host']['execution_mode']}",
            f"Obiettivo: {plan['description']['process']['objective']}",
            f"Verifica attesa: {plan['description']['end_condition']}",
            "",
            "## Risultati verificabili",
        ]
        lines += [
            f"- {o['name']}: {o['record_count']} · SHA-256 {o['sha256']}"
            for o in evidence["outputs"]
        ] or ["- Nessun output verificato disponibile."]
        if evidence.get("receipt_sha256"):
            lines += [
                f"- [Ricevuta locale]({directory / 'run' / 'run.receipt.json'})",
                f"- [Output locali]({directory / 'run' / 'outputs.json'})",
            ]
        if result["teaching"]:
            teaching = result["teaching"]
            lines += [
                "",
                "## Insegnamento salvato",
                f"Stato: {teaching['status']}",
                f"Prossimo passo: {teaching['resume_instruction']}",
            ]
            lines += [
                f"- {s['intent']}: {s['outcome']} ({s['evidence_basis']})"
                for s in teaching["steps"]
            ]
        lines += [
            "",
            "## Misure e informazioni mancanti",
            f"Durata misurata (ms): {evidence.get('elapsed_ms')}",
            f"Limite o informazione mancante: {evidence.get('missing_reason') or 'Vedere le verifiche del risultato.'}",
            "Modello e token: disponibili solo se esposti dall’host; nessuna stima sostituisce una misura.",
            "",
            "## Segnalazione",
            "CR restituiti dal servizio: "
            + (
                ", ".join(result["cr_ids"])
                or "nessuno; nulla risulta trasmesso per questo tentativo"
            ),
            "I documenti, i valori degli output e le credenziali restano fuori dal feedback tecnico.",
            "",
            "## Prossimo passo",
            "Riprendere questo processo dal catalogo locale in una nuova conversazione. Verificare il risultato; se incompleto, conservare le prove e preparare la segnalazione revisionata.",
            "I test simulati non qualificano l’automazione sul sito reale.",
        ]
        measurement_lines = []
        for name in ("model", "input_tokens", "output_tokens"):
            measurement = evidence.get("measurements", {}).get(name, {})
            value = measurement.get("value")
            reason = (
                measurement.get("source")
                if value is not None
                else measurement.get(
                    "missing_reason", "execution_measurement_not_recorded"
                )
            )
            measurement_lines.append(
                f"{name}: {value if value is not None else 'non disponibile'} · {reason}"
            )
        insertion = lines.index("## Segnalazione")
        lines[insertion:insertion] = measurement_lines + [""]
        path = _safe(directory / "REPORT.md")
        temporary = directory / ("report-" + uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        temporary.replace(path)
        return path

    def review_result(self, attempt_id: str, review: dict[str, Any]) -> dict[str, Any]:
        """Bind a model/operator correctness judgment to the exact saved evidence."""
        result = self.inspect(attempt_id)
        if (
            set(review) != {"correct", "reviewer", "evidence"}
            or type(review["correct"]) is not bool
            or review["reviewer"] not in {"model", "operator"}
        ):
            raise ValueError(
                "review requires correctness, reviewer and concrete evidence"
            )
        _text(review["evidence"], "result review evidence")
        record = {
            "attempt_id": attempt_id,
            "evidence_sha256": sha256_payload(result["evidence"]),
            "review": review,
            "reviewed_at": _now(),
        }
        self._put(
            "review-" + uuid4().hex,
            result["plan"]["process_id"],
            "result_review",
            record,
        )
        return record

    def qualify(
        self, process_id: str, attempt_ids: list[str], max_elapsed_ms: float
    ) -> dict[str, Any]:
        """Promote only two clean live runs with checked results and accepted timing."""
        if len(set(attempt_ids)) < 2 or len(set(attempt_ids)) != len(attempt_ids):
            raise ValueError("qualification needs two distinct attempts")
        if (
            isinstance(max_elapsed_ms, bool)
            or not isinstance(max_elapsed_ms, (int, float))
            or not math.isfinite(max_elapsed_ms)
            or max_elapsed_ms <= 0
        ):
            raise ValueError("declare the accepted positive performance bound")
        attempts = [self.inspect(a) for a in attempt_ids]
        version = self._version(process_id)
        host = attempts[0]["plan"]["host"]
        reviews = self._rows(process_id, "result_review")
        for attempt in attempts:
            plan, evidence = attempt["plan"], attempt["evidence"]
            if (
                plan["process_id"] != process_id
                or plan["implementation"] != version
                or plan["host"] != host
                or plan["host_fingerprint"] != _machine_fingerprint()
            ):
                raise ValueError(
                    "qualification requires the same process, version and environment"
                )
            elapsed = evidence.get("elapsed_ms")
            if (
                evidence["result"] != "passed"
                or evidence.get("recovery_used")
                or not isinstance(elapsed, (int, float))
                or not 0 <= elapsed <= max_elapsed_ms
            ):
                raise ValueError(
                    "qualification needs a clean measured run within the performance bound"
                )
            matching = [r for r in reviews if r["attempt_id"] == plan["attempt_id"]]
            if (
                not matching
                or matching[-1]["evidence_sha256"] != sha256_payload(evidence)
                or not matching[-1]["review"]["correct"]
            ):
                raise ValueError("exact results require an explicit correctness review")
        directory = self.root / ("qualification-" + uuid4().hex)
        directory.mkdir(mode=0o700)
        # Reuse the full existing verifier; simulations and recovery cannot pass.
        capability_path = Path(version["path"])
        capability = _read(capability_path)
        if capability["status"] == "validated_local":
            capability["status"] = "discovered"
            capability["validation"].update(
                environment_scope="not_validated",
                execution_contract_sha256=None,
                receipts=[],
            )
            capability_path = directory / "capability.to-validate.json"
            _write(capability_path, capability)
        finalize_capability(
            capability_path,
            [self.root / a / "run" / "run.receipt.json" for a in attempt_ids],
            directory / "capability.json",
        )
        record = {
            "process_id": process_id,
            "version": version,
            "host": host,
            "host_fingerprint": _machine_fingerprint(),
            "attempt_ids": attempt_ids,
            "evidence_hashes": {
                a["plan"]["attempt_id"]: sha256_payload(a["evidence"]) for a in attempts
            },
            "max_elapsed_ms": max_elapsed_ms,
            "qualified_at": _now(),
            "capability_path": str(directory / "capability.json"),
        }
        self._put("qualification-" + uuid4().hex, process_id, "qualification", record)
        return record

    def _qualified(self, process_id: str, version: Any, host: Any) -> bool:
        qualifications = self._rows(process_id, "qualification")
        if not qualifications:
            return False
        record = qualifications[-1]
        if (
            record["version"] != version
            or record["host"] != host
            or host["execution_mode"] != "live_connected_chrome"
            or record["host_fingerprint"] != _machine_fingerprint()
            or version != self._version(process_id)
        ):
            return False
        for plan in self._rows(process_id, "attempt"):
            if (
                plan["kind"] == "teaching"
                or plan["implementation"] != version
                or plan["host"] != host
            ):
                continue
            result = self.inspect(plan["attempt_id"])["evidence"]
            if (
                plan["attempt_id"] in record["attempt_ids"]
                or plan["created_at"] > record["qualified_at"]
            ):
                if result["result"] != "passed" or result.get("recovery_used"):
                    return False
                try:
                    verify_clean_run(
                        Path(version["path"]),
                        self.root / plan["attempt_id"] / "run" / "run.receipt.json",
                    )
                except (ValueError, OSError):
                    return False
                if (
                    plan["attempt_id"] in record["evidence_hashes"]
                    and sha256_payload(result)
                    != record["evidence_hashes"][plan["attempt_id"]]
                ):
                    return False
                elapsed = result.get("elapsed_ms")
                if (
                    not isinstance(elapsed, (int, float))
                    or not 0 <= elapsed <= record["max_elapsed_ms"]
                ):
                    return False
                reviews = [
                    r
                    for r in self._rows(process_id, "result_review")
                    if r["attempt_id"] == plan["attempt_id"]
                ]
                if (
                    not reviews
                    or not reviews[-1]["review"]["correct"]
                    or reviews[-1]["evidence_sha256"] != sha256_payload(result)
                ):
                    return False
        return True

    def catalog(self) -> list[dict[str, Any]]:
        """Expose descriptors for current-model semantic selection, not keyword routing."""
        return [self.resume(p["process_id"]) for p in self._rows(kind="process")]

    def resume(self, process_id: str) -> dict[str, Any]:
        process = self.process(process_id)
        versions = self._rows(process_id, "version")
        attempts = self._rows(process_id, "attempt")
        qualifications = self._rows(process_id, "qualification")
        latest = self._version(process_id) if versions else None
        capability = _read(Path(latest["path"])) if latest else None
        return {
            **process,
            "versions": versions,
            "inputs": capability["inputs"] if capability else [],
            "implementation_status": (
                capability["status"] if capability else "not_implemented"
            ),
            "available_in_qualified_environment": bool(
                qualifications
                and self._qualified(process_id, latest, qualifications[-1]["host"])
            ),
            "attempts": [
                {
                    "attempt_id": a["attempt_id"],
                    "kind": a["kind"],
                    "result": self.inspect(a["attempt_id"])["evidence"]["result"],
                    "report_path": str(self.root / a["attempt_id"] / "REPORT.md"),
                }
                for a in attempts
            ],
            "cr_ids": list(
                dict.fromkeys(
                    s["change_request_id"] for s in self._rows(process_id, "submission")
                )
            ),
            "qualification": qualifications[-1] if qualifications else None,
            "release_history": self._rows(process_id, "release"),
            "cr_status": list(
                {
                    row["change_request_id"]: row
                    for row in self._rows(process_id, "cr_status")
                }.values()
            ),
            "installed_lineage": self._rows(process_id, "installed_binding"),
            "developer_cr_lineage": self._rows(process_id, "developer_cr"),
            "imported_development_attempts": [
                r["attempt_id"] for r in self._rows(process_id, "imported_feedback")
            ],
            "routing_policy": "The current model matches the professional objective and exclusions; ask if ambiguous. Qualification is checked again for the actual host before use.",
        }

    def prepare_feedback(
        self,
        attempt_id: str,
        request: dict[str, Any],
        *,
        problem: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Freeze model-sanitized findings plus useful technical evidence for review."""
        from development_request import prepare_request

        result = self.inspect(attempt_id)
        plan, evidence = result["plan"], result["evidence"]
        implementation = plan["implementation"]
        lineage = {
            "process_id": plan["process_id"],
            "attempt_id": attempt_id,
            "attempt_kind": plan["kind"],
            "process_description": plan["description"],
            "capability_id": (
                implementation["capability_id"] if implementation else None
            ),
            "capability_version": implementation["version"] if implementation else None,
            "execution_contract_sha256": (
                implementation["execution_contract_sha256"] if implementation else None
            ),
            "previous_cr_ids": list(
                dict.fromkeys(
                    s["change_request_id"]
                    for s in self._rows(plan["process_id"], "submission")
                )
            ),
            "execution": {
                k: evidence.get(k)
                for k in (
                    "result",
                    "missing_reason",
                    "execution_mode",
                    "elapsed_ms",
                    "elapsed_source",
                    "receipt_sha256",
                    "recovery_used",
                    "measurements",
                )
            },
            "outputs": evidence["outputs"],
            "checkpoint": None,
        }
        directory = self.root / attempt_id
        checkpoint = directory / "teaching"
        if checkpoint.exists():
            saved = read_checkpoint(checkpoint)
            lineage["checkpoint"] = {
                "sha256": saved["sha256"],
                "revision": saved["revision"],
                "step_count": len(saved["payload"]["steps"]),
            }
        request = {
            **request,
            "schema_version": "browser-development-request/v2",
            "request_id": attempt_id,
            "browser_lifecycle": lineage,
        }
        # The same reviewed body carries identifiers and evidence to the CR server;
        # ZIP generation does not masquerade as uploading binary attachments.
        body = request
        kind = "capability"
        if problem is not None:
            kind = "problem"
            diagnostics = {**problem["diagnostics"]}
            technical = [
                "Browser process lineage: "
                + json.dumps(
                    {
                        k: v
                        for k, v in lineage.items()
                        if k not in {"outputs", "execution", "process_description"}
                    },
                    ensure_ascii=False,
                )
            ]
            technical += [
                "Browser execution: "
                + json.dumps(lineage["execution"], ensure_ascii=False)
            ]
            technical += [
                "Output evidence: " + json.dumps(o, ensure_ascii=False)
                for o in lineage["outputs"]
            ]
            diagnostics["evidence"] = [*diagnostics["evidence"], *technical]
            diagnostics["correlation_ids"] = [plan["process_id"], attempt_id]
            body = {**problem, "diagnostics": diagnostics}
        review_id = "feedback-" + uuid4().hex
        review_directory = directory / review_id
        prepared = prepare_request(
            request,
            review_directory,
            checkpoint=checkpoint if checkpoint.exists() else None,
            cr_body=body,
        )
        record = {
            "feedback_id": review_id,
            "attempt_id": attempt_id,
            "kind": kind,
            "directory": str(review_directory),
            "review_sha256": prepared["review_sha256"],
            "cr_body_sha256": sha256_payload(body),
            "prepared_at": _now(),
        }
        self._put(review_id, plan["process_id"], "feedback", record)
        return {**record, **prepared, "sent": False, "cr_id": None}

    def submit_feedback(
        self,
        feedback_id: str,
        vera_root: Path,
        *,
        approval_id: str,
        expected_sha256: str,
        transmission_authorized: bool,
        client_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send only an exact authorized package body; retain real idempotent receipts."""
        from development_request import export_request, verify_archive

        if any(
            (path / ".vera-onboarding-local-only").exists()
            for path in (self.root, *self.root.parents)
        ):
            raise ValueError("tutorial feedback must remain local")
        _text(approval_id, "actual transmission approval reference")
        if transmission_authorized is not True:
            raise ValueError(
                "transmission requires authorization for the exact reviewed body"
            )
        records = [
            r for r in self._rows(kind="feedback") if r["feedback_id"] == feedback_id
        ]
        if len(records) != 1:
            raise ValueError("unknown reviewed feedback")
        record = records[0]
        if record["review_sha256"] != expected_sha256:
            raise ValueError("approval does not cover this exact feedback")
        plan, directory = self._attempt(record["attempt_id"])
        archive = directory / (feedback_id + ".zip")
        if not archive.exists():
            export_request(
                Path(record["directory"]),
                archive,
                expected_sha256=expected_sha256,
                approval_id=approval_id,
            )
        verify_archive(archive)
        with ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read("review-manifest.json"))
            body = json.loads(zipped.read("cr-request.json"))
        if (
            sha256_payload(manifest) != expected_sha256
            or sha256_payload(body) != record["cr_body_sha256"]
        ):
            raise ValueError("archived feedback differs from reviewed content")
        body_path = directory / (feedback_id + ".submission.json")
        if not body_path.exists():
            _write(body_path, body)
        elif _read(body_path) != body:
            raise ValueError("frozen submission changed")
        existing = [
            s
            for s in self._rows(plan["process_id"], "submission")
            if s["feedback_id"] == feedback_id
        ]
        if existing:
            return existing[0]
        client = _cr_client(vera_root)
        submit = (
            client.submit_problem
            if record["kind"] == "problem"
            else client.submit_suggestion
        )
        receipt = submit(vera_root, body_path, **(client_options or {}))
        # Status tokens remain exclusively in the established private CR client.
        returned = {
            "feedback_id": feedback_id,
            "attempt_id": plan["attempt_id"],
            "process_id": plan["process_id"],
            "change_request_id": receipt["change_request_id"],
            "status": receipt["status"],
            "fixed_version": receipt.get("fixed_version"),
            "submitted_at": _now(),
            "body_sha256": record["cr_body_sha256"],
            "delivery": "reviewed_structured_text",
            "zip_uploaded": False,
            "archive_path": str(archive),
        }
        try:
            self._put(
                "submission:" + feedback_id, plan["process_id"], "submission", returned
            )
        except sqlite3.IntegrityError:
            return next(
                s
                for s in self._rows(plan["process_id"], "submission")
                if s["feedback_id"] == feedback_id
            )
        self.report(plan["attempt_id"])
        return returned


def main(argv: list[str] | None = None) -> int:
    """CLI inputs are assembled by Vera, never by the accountant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument(
        "command",
        choices=(
            "catalog",
            "create",
            "resume",
            "version",
            "begin",
            "teach",
            "inspect",
            "report",
            "review",
            "qualify",
            "prepare-feedback",
            "submit-feedback",
            "import-feedback",
            "sync-installed",
            "export-binding",
            "record-release",
            "refresh-status",
        ),
    )
    parser.add_argument("--process")
    parser.add_argument("--attempt")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--capability", type=Path)
    parser.add_argument("--kind", choices=("teaching", "test", "use"))
    parser.add_argument("--expected-revision", type=int, default=0)
    parser.add_argument("--vera-root", type=Path)
    parser.add_argument("--module-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cr-record", type=Path)
    args = parser.parse_args(argv)
    try:
        store = ProcessStore(args.root)
        payload: Any = (
            _read(args.input)
            if args.input and args.command != "import-feedback"
            else None
        )
        if args.command == "catalog":
            result: Any = store.catalog()
        elif args.command == "create":
            result = store.create(payload)
        elif args.command == "import-feedback":
            result = store.import_feedback(
                args.input, cr_record=_read(args.cr_record) if args.cr_record else None
            )
        elif args.command == "sync-installed":
            result = store.sync_installed(
                args.module_root or Path(__file__).resolve().parents[1]
            )
        elif args.command == "export-binding":
            result = str(store.export_binding(args.process, args.output))
        elif args.command == "record-release":
            result = store.record_release(
                args.process, payload["version"], payload["release"]
            )
        elif args.command == "refresh-status":
            result = store.refresh_status(args.process, args.vera_root)
        elif args.command == "resume":
            result = store.resume(args.process)
        elif args.command == "version":
            result = store.add_version(args.process, args.capability, payload)
        elif args.command == "begin":
            result = store.begin(args.process, args.kind, payload)
        elif args.command == "teach":
            result = store.teach(args.attempt, payload, args.expected_revision)
        elif args.command == "review":
            result = store.review_result(args.attempt, payload)
        elif args.command == "qualify":
            result = store.qualify(
                args.process, payload["attempt_ids"], payload["max_elapsed_ms"]
            )
        elif args.command == "prepare-feedback":
            result = store.prepare_feedback(
                args.attempt, payload["request"], problem=payload.get("problem")
            )
        elif args.command == "submit-feedback":
            result = store.submit_feedback(
                payload["feedback_id"],
                args.vera_root,
                approval_id=payload["approval_id"],
                expected_sha256=payload["review_sha256"],
                transmission_authorized=payload["transmission_authorized"],
            )
        elif args.command == "report":
            result = str(store.report(args.attempt))
        else:
            result = store.inspect(args.attempt)
        LOG.info("%s", json.dumps(result, ensure_ascii=False))
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RuntimeError,
        sqlite3.Error,
    ) as exc:
        LOG.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
