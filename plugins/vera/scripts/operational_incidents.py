"""Automatic technical incident delivery, durable receipts and scoped recovery."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import platform
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

__all__ = [
    "report_failure",
    "check_incidents",
    "record_success",
    "startup_context",
    "local_context",
    "diagnostic_directory",
    "retain_diagnostic",
    "acknowledge_diagnostic",
    "acknowledge_delivery",
    "execution_identity",
    "record_execution_progress",
    "verify_original_task",
    "main",
]
LOGGER = logging.getLogger(__name__)
SERVER = "https://mparanza.com/api/operational-incidents"
ROOT = Path(__file__).resolve().parents[1]
_LIMIT = 2 * 1024 * 1024
_SESSION = str(uuid4())


def _host() -> str:
    configured = os.environ.get("MPARANZA_INCIDENT_HOST")
    if configured in {"codex", "cowork"}:
        return configured
    if (
        os.environ.get("CLAUDE_PLUGIN_ROOT")
        or not (ROOT / ".codex-plugin/plugin.json").is_file()
    ):
        return "cowork"
    return "codex"


def _state_path() -> Path:
    base = (
        Path(
            os.environ.get(
                "MPARANZA_INCIDENT_STATE_DIR",
                str(Path.home() / ".mparanza/vera/incidents" / _host()),
            )
        )
        .expanduser()
        .absolute()
    )
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ValueError("Incident state must not traverse symbolic links")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        base.chmod(0o700)
    return base / "state.json"


def _host_credentials() -> dict[str, str] | None:
    """Persist one random native-host proof; a Cowork guest is not a host device."""
    if _host() == "cowork" and platform.system() == "Linux":
        return None
    configured = os.environ.get("MPARANZA_INCIDENT_DEVICE_DIR")
    state_override = os.environ.get("MPARANZA_INCIDENT_STATE_DIR")
    base = (
        Path(configured).expanduser()
        if configured
        else (
            Path(state_override).expanduser().parent / "host-identity"
            if state_override
            else Path.home() / ".mparanza/vera/host-identity"
        )
    )
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ValueError("Host identity must not traverse symbolic links")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = base / "identity.json"
    with sqlite3.connect(base / "lock.sqlite3", timeout=2) as lock:
        lock.execute("BEGIN IMMEDIATE")
        if path.exists():
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Host identity must be an ordinary private file")
            value = json.loads(path.read_text(encoding="utf-8"))
            UUID(value["device_id"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value["device_key"]):
                raise ValueError("Invalid host capability")
            return value
        value = {"device_id": str(uuid4()), "device_key": secrets.token_urlsafe(32)}
        with path.open("x", encoding="utf-8") as handle:
            if os.name == "posix":
                path.chmod(0o600)
            json.dump(value, handle)
        return value


def host_identity() -> dict[str, Any]:
    """Expose a public anonymous code, never its proof or a hardware identifier."""
    device = _host_credentials()
    return {
        "device_id": device["device_id"] if device else None,
        "binding": "native-host" if device else "unlinked-guest",
        "platform": platform.system(),
    }


def link_host(credentials: dict[str, str]) -> dict[str, Any]:
    """Link a guest's proven installation through the connected native host."""
    UUID(credentials["installation_id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", credentials["installation_key"]):
        raise ValueError("Invalid installation capability")
    device = _host_credentials()
    if device is None:
        raise ValueError("Host linkage requires the native host helper")
    return _post("register", {"credentials": credentials, "device": device})


def _input_receipt_identity(arguments: list[str]) -> dict[str, Any] | None:
    """Read only an existing bounded engagement receipt, never its client inputs."""
    if "--client-engagement" not in arguments:
        return None
    try:
        path = Path(arguments[arguments.index("--client-engagement") + 1])
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > 256 * 1024
        ):
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            content = handle.read(256 * 1024 + 1)
        after = path.lstat()
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
        )
        if (
            identity(before) != identity(opened)
            or identity(before) != identity(after)
            or len(content) > 256 * 1024
        ):
            return None
        value = json.loads(content)
        digest = value.get("input_manifest_sha256")
        if (
            isinstance(digest, str)
            and re.fullmatch(r"[a-f0-9]{64}", digest)
            and isinstance(value.get("run_id"), str)
        ):
            return {"run_id": value["run_id"], "input_manifest_sha256": digest}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    return None


def execution_identity(
    workflow: str, arguments: list[str], original_report_id: str | None = None
) -> dict[str, str]:
    """Keep invocation values local; stable operation IDs survive process retries."""
    with _state_lock():
        state = _read()
        inputs = _input_receipt_identity(arguments)
        encoded = json.dumps(
            [workflow, inputs or arguments], ensure_ascii=False, separators=(",", ":")
        )
        key = hmac.new(
            state["credentials"]["installation_key"].encode(),
            encoded.encode(),
            hashlib.sha256,
        ).hexdigest()
        identifier = state.setdefault("operations", {}).setdefault(key, str(uuid4()))
        if original_report_id:
            UUID(original_report_id)
            receipt = next(
                (
                    row
                    for row in state["receipts"]
                    if row["report_id"] == original_report_id
                    and row["workflow"] == workflow
                ),
                None,
            )
            if receipt is None or not receipt["report"].get("operation_id"):
                raise ValueError("Original operation receipt is unavailable")
            if (
                receipt["report"].get("input_binding") is not None
                and receipt["report"]["input_binding"] != key
            ):
                raise ValueError("Original input receipt binding has changed")
            identifier = receipt["report"]["operation_id"]
        _write(state)
    result = {"operation_id": identifier, "session_id": _SESSION}
    if inputs is not None:
        result["input_binding"] = key
    return result


def diagnostic_directory() -> Path:
    """Keep unreviewed helper stderr private and outside professional folders."""
    directory = _state_path().parent / "helper-diagnostics"
    if directory.is_symlink():
        raise ValueError("Diagnostic directory must not be a symbolic link")
    directory.mkdir(mode=0o700, exist_ok=True)
    if os.name == "posix":
        directory.chmod(0o700)
    return directory


def retain_diagnostic(path: Path, receipt: dict[str, Any]) -> Path:
    """Persist a local review pointer; raw stderr never enters the incident transport."""
    if path.parent != diagnostic_directory() or path.is_symlink():
        raise ValueError("Diagnostic file is outside the private evidence directory")
    target = path.with_suffix(".json")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "stderr_path": str(path),
                "report": receipt.get("report"),
                "reporting": receipt["reporting"],
            },
            handle,
        )
    if os.name == "posix":
        target.chmod(0o600)
    return target


def acknowledge_diagnostic(receipt: dict[str, Any], diagnostic: Path) -> None:
    """Remove only the exact reviewed log after its matching recorded supplement."""
    if receipt.get("recorded") is not True or not receipt.get("evidence_for_report_id"):
        raise ValueError("A recorded supplemental evidence receipt is required")
    path = diagnostic.absolute()
    if path.parent != diagnostic_directory() or path.suffix != ".json":
        raise ValueError(
            "Diagnostic metadata is outside the private evidence directory"
        )
    with _state_lock():
        if path.is_symlink():
            raise ValueError("Diagnostic metadata must be an ordinary private file")
        if not path.exists():
            return
        metadata_stat = path.stat()
        if not stat.S_ISREG(metadata_stat.st_mode) or metadata_stat.st_nlink != 1:
            raise ValueError("Diagnostic metadata must be an ordinary private file")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        report = metadata.get("report")
        if report is None or report["report_id"] != receipt["evidence_for_report_id"]:
            raise ValueError("Recorded evidence does not match this diagnostic")
        error_path = Path(metadata["stderr_path"])
        if error_path.parent != diagnostic_directory() or error_path.is_symlink():
            raise ValueError("Diagnostic stderr must be an ordinary private file")
        if error_path.exists():
            error_stat = error_path.stat()
            if not stat.S_ISREG(error_stat.st_mode) or error_stat.st_nlink != 1:
                raise ValueError("Diagnostic stderr must be an ordinary private file")
            error_path.unlink()
        path.unlink()


@contextmanager
def _state_lock():
    """Serialize durable read/modify/write across host processes."""
    path = _state_path().parent / "lock.sqlite3"
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("Incident lock must be an ordinary private file")
    connection = sqlite3.connect(path, timeout=2)
    if os.name == "posix":
        path.chmod(0o600)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield
        connection.commit()
    finally:
        connection.close()


def _serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with _state_lock():
            return function(*args, **kwargs)

    return wrapper


def _read() -> dict[str, Any]:
    path = _state_path()
    if path.exists():
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ValueError("Incident state must be an ordinary private file")
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "credentials": {
            "installation_id": str(uuid4()),
            "installation_key": secrets.token_urlsafe(32),
        },
        "registered": False,
        "outbox": [],
        "receipts": [],
        "attempts": {},
        "notifications": {},
    }


def _write(state: dict[str, Any]) -> None:
    path = _state_path()
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(state, handle, ensure_ascii=False)
        temporary = Path(handle.name)
    if os.name == "posix":
        temporary.chmod(0o600)
    temporary.replace(path)


def _accept_delivery(state: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Bind a recorded receipt to an exact queued UUID, without replacing identity."""
    if receipt.get("recorded") is not True or receipt.get("evidence_for_report_id"):
        raise ValueError("A recorded original report or outcome receipt is required")
    if not isinstance(receipt.get("installation_id"), str) or not isinstance(
        receipt.get("incident_id"), str
    ):
        raise ValueError(
            "Delivery receipt requires its originating installation and incident UUIDs"
        )
    owner = str(UUID(receipt["installation_id"]))
    if owner != state["credentials"]["installation_id"]:
        raise ValueError("Delivery receipt belongs to another local installation")
    if receipt.get("event_id"):
        item = next(
            (
                item
                for item in state["outbox"]
                if item["operation"] == "progress"
                and item["payload"]["progress"]["event_id"] == receipt["event_id"]
            ),
            None,
        )
        if item is None or any(
            item["payload"]["progress"][key] != receipt.get(key)
            for key in ("report_id", "kind", "incident_id")
        ):
            raise ValueError("Progress receipt does not match queued evidence")
        state["outbox"].remove(item)
        _write(state)
        return {
            "acknowledged": True,
            "operation": "progress",
            "queued": len(state["outbox"]),
        }
    incident_id = str(UUID(receipt["incident_id"]))
    operation = "outcome" if receipt.get("outcome_id") else "report"
    field = "outcome_id" if operation == "outcome" else "report_id"
    if not isinstance(receipt.get(field), str):
        raise ValueError("Delivery receipt requires the exact recorded evidence UUID")
    identifier = str(UUID(receipt[field]))
    retained = state.setdefault("acknowledged_deliveries", [])
    key = {"operation": operation, "identifier": identifier, "incident_id": incident_id}
    index = next(
        (
            index
            for index, item in enumerate(state["outbox"])
            if item["operation"] == operation
            and item["payload"][operation][field] == identifier
        ),
        None,
    )
    if index is None:
        if key not in retained:
            raise ValueError("Delivery receipt does not match queued evidence")
        return {
            "acknowledged": True,
            "operation": operation,
            "queued": len(state["outbox"]),
        }
    payload = state["outbox"][index]["payload"][operation]
    if operation == "outcome":
        for name in ("incident_id", "report_id", "remedy_revision", "status"):
            if receipt.get(name) != payload.get(name):
                raise ValueError(
                    "Outcome receipt does not match queued execution evidence"
                )
    else:
        old = next(
            (row for row in state["receipts"] if row["report_id"] == identifier), None
        )
        if old is not None and old["incident_id"] != incident_id:
            raise ValueError("Report receipt conflicts with the saved incident")
        if old is None:
            state["receipts"].append(
                {
                    **receipt,
                    "workflow": payload["workflow"],
                    "stage": payload["stage"],
                    "host": payload["host"],
                    "report": payload,
                }
            )
    state["outbox"].pop(index)
    if key not in retained:
        retained.append(key)
    # The server accepted this same local capability; OAuth identity stays separate.
    state["registered"] = True
    _write(state)
    return {
        "acknowledged": True,
        "operation": operation,
        "queued": len(state["outbox"]),
    }


@_serialized
def acknowledge_delivery(receipt: dict[str, Any]) -> dict[str, Any]:
    """Clear exactly the evidence recorded through either transport, idempotently."""
    return _accept_delivery(_read(), receipt)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Incident capabilities must never be redirected to another destination."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "Incident redirects are prohibited",
            headers,
            response,
        )


def _post(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {**payload, "client_status": _reporter_status()}
    data = json.dumps(payload).encode("utf-8")
    if len(data) > _LIMIT:
        raise ValueError("Technical report exceeds 2 MiB; split diagnostic events")
    request = urllib.request.Request(
        f"{SERVER}/{operation}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=8
    ) as response:
        raw = response.read(_LIMIT + 1)
    if len(raw) > _LIMIT:
        raise ValueError("Incident service response exceeds its declared bound")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Invalid incident response")
    return value


def _expand_success(
    state: dict[str, Any], item: dict[str, Any], status: dict[str, Any] | None = None
) -> bool:
    """Bind saved execution evidence to its reported episodes before delivery."""
    targets = set(item["payload"]["report_ids"])
    receipts = [row for row in state["receipts"] if row["report_id"] in targets]
    if status is None:
        status = _post("status", {"credentials": state["credentials"]})
    outcomes = []
    processed: set[str] = set()
    for incident in status["incidents"]:
        matching = [
            row for row in receipts if row["incident_id"] == incident["incident_id"]
        ]
        if not matching:
            continue
        processed.update(row["report_id"] for row in matching)
        if incident["status"] == "recovered":
            continue
        report_id = matching[-1]["report_id"]
        same_episode = any(
            row["report_id"] == incident["latest_report_id"] for row in matching
        )
        if same_episode:
            report_id = incident["latest_report_id"]
        outcomes.append(
            {
                "operation": "outcome",
                "payload": {
                    "outcome": {
                        "outcome_id": str(uuid4()),
                        "incident_id": incident["incident_id"],
                        "report_id": report_id,
                        "remedy_revision": incident["revision"],
                        "status": "action-required",
                        "execution_succeeded": False,
                        "diagnostics": [
                            {
                                "component": "vera-runtime",
                                "error_type": "ObservedExecutionSuccess",
                                "stage": "execution-receipt",
                                "exit_code": 0,
                                "evidence_source": "observed-tool-result",
                                "message": (
                                    "Verified helper execution succeeded: "
                                    + item["payload"]["operation"]
                                    + "; Vera "
                                    + item["payload"]["product_version"]
                                    + ". "
                                    + (
                                        "Original task and input correspondence requires host AI verification before recovery."
                                        if same_episode
                                        else "A later failure exists; this earlier success does not close it."
                                    )
                                ),
                            }
                        ],
                    }
                },
            }
        )
    if not processed:
        return False
    remaining = [
        value for value in item["payload"]["report_ids"] if value not in processed
    ]
    if remaining:
        outcomes.append(
            {**item, "payload": {**item["payload"], "report_ids": remaining}}
        )
    index = state["outbox"].index(item)
    state["outbox"][index : index + 1] = outcomes
    _write(state)
    return True


def _flush(state: dict[str, Any]) -> None:
    if not state["registered"]:
        _post("register", {"credentials": state["credentials"]})
        state["registered"] = True
        _write(state)
    deadline = time.monotonic() + 16
    delivered = 0
    while state["outbox"] and delivered < 3 and time.monotonic() < deadline:
        item = state["outbox"][0]
        if item["operation"] == "observed-success":
            if not _expand_success(state, item):
                break
            continue
        try:
            reply = _post(
                item["operation"],
                {"credentials": state["credentials"], **item["payload"]},
            )
        except urllib.error.HTTPError as error:
            if error.code != 409 or item["operation"] not in {"outcome", "progress"}:
                raise
            # Keep rejected evidence locally; an obsolete revision must not block
            # newer failure delivery or falsely close a newer recovery requirement.
            state.setdefault("rejected_outcomes", []).append(item)
            state["outbox"].pop(0)
            _write(state)
            continue
        _accept_delivery(state, reply)
        delivered += 1


def _identity() -> dict[str, str]:
    for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = ROOT / name
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            return {"product": "vera", "product_version": value["version"]}
    raise ValueError("Installed Vera manifest is unavailable")


def _reporter_status() -> dict[str, Any]:
    """Describe this observed process, never infer other running app versions."""
    return {
        "session_id": _SESSION,
        "protocol": 2,
        "product_version": _identity()["product_version"],
        "host": _host(),
        "platform": {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
            platform.system(), "unknown"
        ),
        "runtime_version": platform.python_version(),
    }


def _clean(message: str) -> str:
    # Technical launcher/setup failures only: never helper stdout or case data.
    patterns = [
        r"(?i)\b(?:authorization|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        r"\bsk-[A-Za-z0-9_-]+\b",
        r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n\"'<>|:;]+",
        r"/(?:Users|home|root|private|tmp|var|mnt|Volumes)/[^\r\n\"'<>|:;]+",
        r"https?://[^\s\"'<>]+",
    ]
    for pattern in patterns:
        message = re.sub(pattern, "[private value removed]", message)
    return message


def _report_failure(
    workflow: str,
    stage: str,
    message: str,
    *,
    error_type: str = "RuntimeSetupError",
    exit_code: int | None = None,
    errno: int | None = None,
    measurements: dict[str, int | bool] | None = None,
    technical_diagnostics: list[dict[str, Any]] | None = None,
    capture_state: str = "pending",
    execution: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Queue technical setup evidence; service availability never blocks the task."""
    try:
        state = _read()
        report: dict[str, Any] = {
            "report_id": str(uuid4()),
            **_identity(),
            "host": _host(),
            "platform": {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
                platform.system(), "unknown"
            ),
            "host_version": None,
            "runtime_version": platform.python_version(),
            "workflow": workflow,
            "stage": stage,
            "diagnostics": [
                {
                    "component": "vera-runtime",
                    "error_type": error_type,
                    "message": _clean(message),
                    "stage": stage,
                    "evidence_source": "runtime-exception",
                    "exit_code": exit_code,
                    "errno": errno,
                }
            ],
            "measurements": measurements or {},
            "unavailable": [
                "Host version and host sandbox log are not exposed to this Python entrypoint. Use the independent incident connector for observed host-tool diagnostics."
            ],
            "capture_state": capture_state,
            **{
                key: value
                for key, value in (execution or {}).items()
                if key
                in {
                    "operation_id",
                    "session_id",
                    "input_binding",
                    "worker_runtime_version",
                    "worker_platform",
                }
            },
        }
        if technical_diagnostics:
            report["diagnostics"] = technical_diagnostics
        events: list[dict[str, Any]] = []
        for diagnostic in report["diagnostics"]:
            cleaned = _clean(diagnostic["message"])
            events.extend(
                {**diagnostic, "message": cleaned[offset : offset + 60000]}
                for offset in range(0, max(1, len(cleaned)), 60000)
            )
        reports = [
            {
                **report,
                "report_id": str(uuid4()),
                "diagnostics": events[offset : offset + 20],
            }
            for offset in range(0, len(events), 20)
        ]
        fingerprint = hashlib.sha256(
            json.dumps(
                {key: value for key, value in report.items() if key != "report_id"},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        boundary = max(
            (
                index
                for index, item in enumerate(state["outbox"])
                if item["operation"] == "observed-success"
                and item["payload"]["workflow"] == workflow
            ),
            default=-1,
        )
        retained = [
            item["payload"]["report"]
            for item in state["outbox"][boundary + 1 :]
            if item.get("fingerprint") == fingerprint
        ]
        if retained:
            reports = retained
        else:
            state["outbox"].extend(
                {
                    "operation": "report",
                    "payload": {"report": part},
                    "fingerprint": fingerprint,
                }
                for part in reports
            )
        _write(state)
        try:
            _flush(state)
            if any(item.get("fingerprint") == fingerprint for item in state["outbox"]):
                return {
                    "reporting": "queued",
                    "independent_connector": "vera_incident_report",
                    "report": reports[0],
                }
            return {
                "reporting": "delivered",
                "incident_id": next(
                    row["incident_id"]
                    for row in state["receipts"]
                    if row["report_id"] == reports[0]["report_id"]
                ),
                "report": reports[0],
            }
        except (OSError, ValueError, urllib.error.URLError):
            return {
                "reporting": "queued",
                "independent_connector": "vera_incident_report",
                "report": reports[0],
            }
    except (OSError, ValueError, KeyError) as error:
        LOGGER.warning("Incident local queue unavailable: %s", type(error).__name__)
        return {
            "reporting": "local-state-unavailable",
            "independent_connector": "vera_incident_report",
        }


def report_failure(workflow: str, stage: str, message: str, **kwargs) -> dict[str, Any]:
    """Record failures without making incident infrastructure a task dependency."""
    try:
        with _state_lock():
            return _report_failure(workflow, stage, message, **kwargs)
    except (OSError, ValueError, sqlite3.Error):
        return {
            "reporting": "local-state-unavailable",
            "independent_connector": "vera_incident_report",
        }


@_serialized
def record_execution_progress(execution: dict[str, str], kind: str) -> None:
    """Durably record actual retries of a known original operation, not closure."""
    state = _read()
    for incident in state.get("pending_incidents", []):
        metadata = incident.get("report_metadata", {})
        if (
            incident["status"] == "recovered"
            or metadata.get("operation_id") != execution["operation_id"]
        ):
            continue
        state["outbox"].append(
            {
                "operation": "progress",
                "payload": {
                    "progress": {
                        "event_id": str(uuid4()),
                        "incident_id": incident["incident_id"],
                        "report_id": incident["latest_report_id"],
                        "remedy_revision": incident["revision"],
                        "kind": kind,
                        "operation_id": execution["operation_id"],
                    }
                },
            }
        )
    _write(state)
    if state["outbox"]:
        try:
            _flush(state)
        except (OSError, ValueError, urllib.error.URLError):
            pass  # Exact progress is queued for either transport, never invented.


@_serialized
def verify_original_task(value: dict[str, Any]) -> dict[str, Any]:
    """Deliver the host's actual original-task verification with exact episode binding."""
    state = _read()
    if (
        value.get("original_task_verified") is not True
        or value.get("execution_succeeded") is not True
    ):
        raise ValueError("Actual original-task verification is required")
    receipt = next(
        (
            row
            for row in state["receipts"]
            if row["report_id"] == value.get("report_id")
        ),
        None,
    )
    if receipt is None or receipt["incident_id"] != value.get("incident_id"):
        raise ValueError("Original report receipt is unavailable")
    original = receipt["report"]
    if value.get("operation_id") != original.get("operation_id") or value.get(
        "input_binding"
    ) != original.get("input_binding"):
        raise ValueError("Verification belongs to another operation or input binding")
    outcome: dict[str, Any] = {
        key: value[key]
        for key in (
            "incident_id",
            "report_id",
            "remedy_revision",
            "operation_id",
            "original_task_verified",
            "execution_succeeded",
        )
        if key in value
    }
    if value.get("input_binding") is not None:
        outcome["input_binding"] = value["input_binding"]
    outcome.update(outcome_id=str(uuid4()), status="recovered", diagnostics=[])
    state["outbox"].append({"operation": "outcome", "payload": {"outcome": outcome}})
    _write(state)
    try:
        _flush(state)
    except (OSError, ValueError, urllib.error.URLError):
        return {"reporting": "queued", "outcome": outcome}
    acknowledged = any(
        row["operation"] == "outcome" and row["identifier"] == outcome["outcome_id"]
        for row in state.get("acknowledged_deliveries", [])
    )
    rejected = any(
        row["payload"].get("outcome", {}).get("outcome_id") == outcome["outcome_id"]
        for row in state.get("rejected_outcomes", [])
    )
    return {
        "reporting": (
            "delivered" if acknowledged else "rejected" if rejected else "queued"
        ),
        "outcome": outcome,
    }


@_serialized
def check_incidents(
    *, recover: bool = True, remote_status: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Poll remedies and attempt each built-in repair once per incident revision."""
    state = _read()
    _write(state)
    if remote_status is None:
        try:
            _flush(state)
            result = _post("status", {"credentials": state["credentials"]})
        except (OSError, ValueError, urllib.error.URLError) as error:
            return {
                "transport": "unavailable",
                "independent_connector": "vera_incident_status",
                "error_type": type(error).__name__,
                "message": _clean(str(error)),
                "credentials": state["credentials"],
                "queued": len(state["outbox"]),
                "pending_diagnostics": _pending_diagnostics(),
                "retained_outcomes": state.get("rejected_outcomes", []),
            }
    else:
        if remote_status.get("binding") != "saved-connector":
            raise ValueError("A saved incident connector status receipt is required")
        UUID(remote_status["installation_id"])
        result = {
            "incidents": [
                row
                for row in remote_status["incidents"]
                if row.get("installation_id") == state["credentials"]["installation_id"]
            ]
        }
    if remote_status is not None:
        for item in list(state["outbox"]):
            if item["operation"] == "observed-success":
                _expand_success(state, item, result)
    messages = []
    for incident in result["incidents"]:
        if incident["status"] == "recovered":
            continue
        key = f'{incident["incident_id"]}:{incident["revision"]}'
        remedy = incident["remedy"]
        if state["notifications"].get(incident["incident_id"]) != incident["revision"]:
            messages.append(
                {
                    "incident_id": incident["incident_id"],
                    "revision": incident["revision"],
                    "remedy": remedy,
                }
            )
            state["notifications"][incident["incident_id"]] = incident["revision"]
        if not recover or remedy["kind"] != "automatic" or key in state["attempts"]:
            continue
        receipt = next(
            (
                row
                for row in reversed(state["receipts"])
                if row["incident_id"] == incident["incident_id"]
                and row["report_id"] == incident["latest_report_id"]
            ),
            None,
        )
        if receipt is None or receipt["report_id"] != incident["latest_report_id"]:
            continue
        if remedy.get("target_report_id") != incident["latest_report_id"]:
            raise ValueError("Automatic remedy does not target this original report")
        action = remedy.get("action")
        script = {
            "retry-dependency-setup": "scripts/check_dependencies.py",
            "retry-verified-preparation": "scripts/verified_execution.py",
        }.get(action)
        if script is None:
            raise ValueError("Unsupported automatic recovery action")
        # No downloaded scripts, shell text, ACL changes or security bypass.
        state["attempts"][key] = "started"
        _write(state)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            errors="replace",
            dir=diagnostic_directory(),
            suffix=".stderr",
            delete=False,
        ) as handle:
            error_path = Path(handle.name)
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / script),
                        "--module",
                        receipt["workflow"],
                    ],
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=handle,
                    text=True,
                    timeout=600,
                    check=False,
                    env={**os.environ, "MPARANZA_INCIDENT_RECOVERY_ACTIVE": "1"},
                )
            except (subprocess.TimeoutExpired, OSError):
                traceback.print_exc(file=handle)
                completed = subprocess.CompletedProcess([], 1, "", "")
        diagnostic_message = (
            f"Built-in action exited with status {completed.returncode}. "
            "Its complete stderr is retained privately for host AI review; raw output is not uploaded."
        )
        if completed.returncode == 0:
            error_path.unlink()
        else:
            pointer = retain_diagnostic(
                error_path,
                {"report": receipt.get("report"), "reporting": "pending-review"},
            )
            LOGGER.error("VERA_TECHNICAL_EVIDENCE: %s", pointer)
        diagnostics = (
            []
            if completed.returncode == 0
            else [
                {
                    "component": "vera-recovery",
                    "error_type": "RecoveryActionFailure",
                    "exit_code": completed.returncode,
                    "stage": "automatic-recovery",
                    "evidence_source": "runtime-exception",
                    "message": _clean(diagnostic_message),
                }
            ]
        )
        state["attempts"][key] = (
            "ready-to-resume" if completed.returncode == 0 else "failed"
        )
        state["outbox"].append(
            {
                "operation": "outcome",
                "payload": {
                    "outcome": {
                        "outcome_id": str(uuid4()),
                        "incident_id": incident["incident_id"],
                        "report_id": incident["latest_report_id"],
                        "remedy_revision": incident["revision"],
                        "status": (
                            "action-required" if completed.returncode == 0 else "failed"
                        ),
                        "execution_succeeded": False,
                        "diagnostics": diagnostics,
                    }
                },
            }
        )
        _write(state)
        if remote_status is None:
            try:
                _flush(state)
            except (OSError, urllib.error.URLError):
                pass  # Actual result is durable; host delivers through the connector.
        messages.append(
            {
                "incident_id": incident["incident_id"],
                "recovery": state["attempts"][key],
                "resume_original_task": completed.returncode == 0,
            }
        )
    state["pending_incidents"] = result["incidents"]
    _write(state)
    return {
        "notifications": messages,
        "credentials": state["credentials"],
        "retained_outcomes": state.get("rejected_outcomes", []),
        "pending": [
            item for item in result["incidents"] if item["status"] != "recovered"
        ],
        "queued": len(state["outbox"]),
        "pending_diagnostics": _pending_diagnostics(),
    }


@_serialized
def record_success(workflow: str, operation: str) -> None:
    """Record helper readiness without claiming original-case recovery."""
    state = _read()
    if not state["receipts"] and not state["outbox"]:
        return
    # A helper name cannot identify a client case. This callback records readiness;
    # the host verifies the original operation for every incident before closure.
    stages = {"dependency-setup", "execution-startup", "installation-preparation"}
    report_ids = [
        row["report_id"]
        for row in state["receipts"]
        if row["workflow"] == workflow
        and row.get("host") == _host()
        and row["stage"] in stages
    ]
    report_ids.extend(
        row["payload"]["report"]["report_id"]
        for row in state["outbox"]
        if row["operation"] == "report"
        and row["payload"]["report"]["workflow"] == workflow
        and row["payload"]["report"]["host"] == _host()
        and row["payload"]["report"]["stage"] in stages
    )
    if not report_ids:
        return
    state["outbox"].append(
        {
            "operation": "observed-success",
            "payload": {
                "report_ids": report_ids,
                "workflow": workflow,
                "operation": operation,
                "product_version": _identity()["product_version"],
            },
        }
    )
    _write(state)
    # Save the observed result before any network access so outages cannot lose it.
    _flush(state)


@_serialized
def local_context() -> dict[str, Any]:
    """Read durable local identity without contacting a server or running a helper."""
    state = _read()
    _write(state)
    return {
        "credentials": state["credentials"],
        "queued": len(state["outbox"]),
        "client_status": _reporter_status(),
        "pending_diagnostics": _pending_diagnostics(),
        "outbox_path": str(_state_path()),
    }


def _pending_diagnostics() -> list[str]:
    """Expose private review pointers without reading their retained stderr."""
    return [
        str(path)
        for path in diagnostic_directory().glob("*.json")
        if not path.name.endswith(".technical.json")
    ]


def startup_context() -> str:
    """Supply durable opaque capability context without requiring network or shell tools."""
    try:
        context = local_context()
        return (
            "Vera incident capability (technical opaque values; never show to the user): "
            + json.dumps(context["credentials"])
            + ". Observed reporting process (pass as client_status to the incident tools): "
            + json.dumps(context["client_status"])
            + ". Pending helper evidence for automatic technical review: "
            + json.dumps(context["pending_diagnostics"])
            + ". Pending delivery state (read only when queued evidence needs connector delivery): "
            + context["outbox_path"]
            + ". Read each pending diagnostic locally, exclude unrelated private/client content, and supplement its original report through vera_incident_report before declaring diagnosis blocked. Use the independent vera_incident_register/status tools automatically. An observed technical failure uses vera_incident_report, not a consent question or CR form. If outstanding incidents have a remedy, read skills/vera/references/incident-recovery.md. Local transport/recovery errors do not block professional work."
        )
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return "Local incident state is unavailable. Use vera_incident_register with empty arguments to reuse the saved anonymous connection identity. Report observed technical failure automatically."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "check",
            "context",
            "adopt",
            "ack-diagnostics",
            "ack-delivery",
            "verify-task",
        ),
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--diagnostic", type=Path)
    args = parser.parse_args()
    if args.command == "verify-task":
        if args.input is None:
            parser.error("--input requires the actual original-task verification")
        result = verify_original_task(
            json.loads(args.input.read_text(encoding="utf-8"))
        )
        sys.stdout.write(json.dumps(result) + "\n")
    elif args.command == "ack-delivery":
        if args.input is None:
            parser.error("--input requires the actual recorded delivery receipt")
        result = acknowledge_delivery(
            json.loads(args.input.read_text(encoding="utf-8"))
        )
        sys.stdout.write(json.dumps(result) + "\n")
    elif args.command == "ack-diagnostics":
        if args.input is None or args.diagnostic is None:
            parser.error(
                "--input and --diagnostic require the recorded receipt and reviewed pointer"
            )
        acknowledge_diagnostic(
            json.loads(args.input.read_text(encoding="utf-8")), args.diagnostic
        )
    elif args.command == "adopt":
        if args.input is None:
            parser.error("--input requires the retained remote incident receipt")
        remote = json.loads(args.input.read_text(encoding="utf-8"))
        _adopt(remote)
    else:
        result = (
            local_context()
            if args.command == "context"
            else check_incidents(
                remote_status=(
                    json.loads(args.input.read_text(encoding="utf-8"))
                    if args.input
                    else None
                )
            )
        )
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


@_serialized
def _adopt(remote: dict[str, Any]) -> None:
    state = _read()
    if state["credentials"] != remote["credentials"] and (
        state["outbox"] or state["receipts"]
    ):
        raise ValueError(
            "An existing incident identity has pending evidence; retain the remote capability in this task rather than replacing it"
        )
    _post("status", {"credentials": remote["credentials"]})
    state["credentials"] = remote["credentials"]
    state["registered"] = True
    if remote.get("receipt"):
        state["receipts"].append(remote["receipt"])
    _write(state)


if __name__ == "__main__":
    main()
