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
import runpy
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

_reporting_product = runpy.run_path(
    str(Path(__file__).with_name("reporting_product.py"))
)
product_name = _reporting_product["product_name"]
installed_reference_path = _reporting_product["installed_reference_path"]

__all__ = [
    "report_failure",
    "check_incidents",
    "record_success",
    "report_pdf_recovery",
    "startup_context",
    "local_context",
    "reporting_credentials",
    "workflow_transport",
    "diagnostic_directory",
    "retain_diagnostic",
    "acknowledge_diagnostic",
    "acknowledge_delivery",
    "execution_identity",
    "record_execution_progress",
    "verify_original_task",
    "host_identity",
    "link_host",
    "main",
]
LOGGER = logging.getLogger(__name__)
SERVER = "https://mparanza.com/api/operational-incidents"
ROOT = Path(__file__).resolve().parents[1]
_LIMIT = 2 * 1024 * 1024
_SESSION = (
    str(UUID(os.environ["MPARANZA_INCIDENT_HOST_SESSION"]))
    if os.environ.get("MPARANZA_INCIDENT_HOST_SESSION")
    else str(uuid4())
)


def _host() -> str:
    configured = os.environ.get("MPARANZA_INCIDENT_HOST")
    if configured in {"codex", "cowork"}:
        return configured
    # Codex sets PLUGIN_ROOT and also CLAUDE_PLUGIN_ROOT for compatibility.
    # Its explicit host variable must win so hooks retain the CLI's userID.
    if os.environ.get("PLUGIN_ROOT"):
        return "codex"
    if (
        os.environ.get("CLAUDE_PLUGIN_ROOT")
        or not (ROOT / ".codex-plugin/plugin.json").is_file()
    ):
        return "cowork"
    return "codex"


def _state_path(*, create: bool = True) -> Path:
    base = (
        Path(
            os.environ.get(
                "MPARANZA_INCIDENT_STATE_DIR",
                str(
                    Path.home()
                    / ".mparanza"
                    / product_name(ROOT)
                    / "incidents"
                    / _host()
                ),
            )
        )
        .expanduser()
        .absolute()
    )
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ValueError("Incident state must not traverse symbolic links")
    if create:
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == "posix" and stat.S_IMODE(base.stat().st_mode) != 0o700:
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
            if not isinstance(value, dict) or set(value) != {"device_id", "device_key"}:
                raise ValueError("Invalid host identity")
            if not isinstance(value["device_id"], str):
                raise ValueError("Invalid host identity")
            UUID(value["device_id"])
            if not isinstance(value["device_key"], str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{32,128}", value["device_key"]
            ):
                raise ValueError("Invalid host capability")
            return value
        value = {"device_id": str(uuid4()), "device_key": secrets.token_urlsafe(32)}
        with path.open("x", encoding="utf-8") as handle:
            if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o600:
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
        "native_app": _host(),
        "broker_status": _reporter_status(),
    }


def link_host(credentials: dict[str, str]) -> dict[str, Any]:
    """Link a guest's proven installation through the connected native host."""
    UUID(credentials["installation_id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", credentials["installation_key"]):
        raise ValueError("Invalid installation capability")
    device = _host_credentials()
    if device is None:
        raise ValueError("Host linkage requires the native host helper")
    receipt = _post(
        "register",
        {
            "credentials": credentials,
            "device": {**device, "native_app": _host()},
            "native_status": _reporter_status(),
        },
    )
    return {
        name: receipt[name]
        for name in (
            "installation_id",
            "registered",
            "device_id",
            "app_installation_id",
            "native_app",
            "next_report_id",
        )
        if name in receipt
    }


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
    if os.name == "posix" and stat.S_IMODE(directory.stat().st_mode) != 0o700:
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
    if os.name == "posix" and stat.S_IMODE(target.stat().st_mode) != 0o600:
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
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) != 0o600:
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
    if _local_delivery_only():
        state["delivery_mode"] = "local-only"
    path = _state_path()
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(state, handle, ensure_ascii=False)
        temporary = Path(handle.name)
    if os.name == "posix" and stat.S_IMODE(temporary.stat().st_mode) != 0o600:
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
    if receipt.get("evidence_for_report_id"):
        state = _read()
        if receipt in state.get("recovery_evidence_receipts", []):
            return {
                "acknowledged": True,
                "operation": "report",
                "queued": len(state["outbox"]),
            }
        _accept_recovery_evidence(state, receipt)
        return {
            "acknowledged": True,
            "operation": "report",
            "queued": len(state["outbox"]),
        }
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


def _local_delivery_only() -> bool:
    mode = os.environ.get("MPARANZA_INCIDENT_DELIVERY", "automatic")
    if mode not in {"automatic", "local-only"}:
        raise ValueError("Unknown operational incident delivery mode")
    return mode == "local-only"


def _post(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    if _local_delivery_only():
        raise urllib.error.URLError("Operational incident delivery is local-only")
    if operation == "register":
        payload = {**payload, "product": product_name(ROOT)}
    # A native broker linking a guest must never claim the guest ran its version.
    if "native_status" not in payload:
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


def workflow_transport(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Reuse the registered local capability and fixed, redirect-free transport."""
    if operation not in {"workflow-record", "workflow-status", "archive-stamp"}:
        raise ValueError("Unknown workflow usage operation")
    registration: dict[str, Any] = {"credentials": payload["credentials"]}
    try:
        device = _host_credentials()
        if device is not None:
            registration["device"] = {**device, "native_app": _host()}
            registration["native_status"] = _reporter_status()
    except (OSError, ValueError, sqlite3.Error):
        LOGGER.warning("Computer identity is unavailable; usage delivery continues.")
    _post("register", registration)
    return _post(operation, payload)


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
                                "component": product_name(ROOT) + "-runtime",
                                "error_type": "ObservedExecutionSuccess",
                                "stage": "execution-receipt",
                                "exit_code": 0,
                                "evidence_source": "observed-tool-result",
                                "message": (
                                    "Verified helper execution succeeded: "
                                    + item["payload"]["operation"]
                                    + "; "
                                    + product_name(ROOT).title()
                                    + " "
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
    if _local_delivery_only() or state.get("delivery_mode") == "local-only":
        return
    if not state["registered"]:
        _post("register", {"credentials": state["credentials"]})
        state["registered"] = True
        _write(state)
    if state.get("host_binding_session") != _SESSION:
        try:
            device = _host_credentials()
            if device is not None:
                receipt = link_host(state["credentials"])
                if receipt.get("device_id") == device["device_id"] and receipt.get(
                    "app_installation_id"
                ):
                    state["host_binding"] = {
                        name: receipt[name]
                        for name in ("device_id", "app_installation_id", "native_app")
                    }
                    state["host_binding_session"] = _SESSION
                    _write(state)
        except (OSError, ValueError, KeyError, sqlite3.Error):
            LOGGER.warning(
                "Native incident identity could not be linked; technical reporting continues."
            )
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
        if reply.get("evidence_for_report_id"):
            _accept_recovery_evidence(state, reply)
        else:
            _accept_delivery(state, reply)
        delivered += 1


def _identity() -> dict[str, str]:
    for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = ROOT / name
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            return {"product": product_name(ROOT), "product_version": value["version"]}
    raise ValueError("Installed product manifest is unavailable")


def _reporter_status() -> dict[str, Any]:
    """Describe this observed process, never infer other running app versions."""
    return {
        "session_id": _SESSION,
        "protocol": 3,
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
    evidence_for: dict[str, Any] | None = None,
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
                    "component": product_name(ROOT) + "-runtime",
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
        if evidence_for is not None:
            # Server supplementation requires the original episode identity,
            # including its session/version when a retry uses a fresh process.
            for key in (
                "product",
                "product_version",
                "host",
                "platform",
                "workflow",
                "stage",
                "session_id",
                "operation_id",
                "input_binding",
            ):
                if key in evidence_for:
                    report[key] = evidence_for[key]
                else:
                    report.pop(key, None)
            report["evidence_for_report_id"] = evidence_for["report_id"]
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
                    "independent_connector": product_name(ROOT) + "_incident_report",
                    "report": reports[0],
                }
            return {
                "reporting": "delivered",
                "incident_id": next(
                    row["incident_id"]
                    for row in state["receipts"]
                    + state.get("recovery_evidence_receipts", [])
                    if row["report_id"] == reports[0]["report_id"]
                ),
                "report": reports[0],
            }
        except (OSError, ValueError, urllib.error.URLError):
            return {
                "reporting": "queued",
                "independent_connector": product_name(ROOT) + "_incident_report",
                "report": reports[0],
            }
    except (OSError, ValueError, KeyError) as error:
        LOGGER.warning("Incident local queue unavailable: %s", type(error).__name__)
        return {
            "reporting": "local-state-unavailable",
            "independent_connector": product_name(ROOT) + "_incident_report",
        }


def report_failure(workflow: str, stage: str, message: str, **kwargs) -> dict[str, Any]:
    """Record failures without making incident infrastructure a task dependency."""
    try:
        with _state_lock():
            return _report_failure(workflow, stage, message, **kwargs)
    except (OSError, ValueError, sqlite3.Error):
        return {
            "reporting": "local-state-unavailable",
            "independent_connector": product_name(ROOT) + "_incident_report",
        }


def _accept_recovery_evidence(state: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Acknowledge only queued supplements; never promote them to original tasks."""
    if (
        receipt.get("recorded") is not True
        or receipt.get("installation_id") != state["credentials"]["installation_id"]
    ):
        raise ValueError("Recovery evidence receipt has the wrong installation")
    item = next(
        (
            item
            for item in state["outbox"]
            if item["operation"] == "report"
            and item["payload"]["report"]["report_id"] == receipt.get("report_id")
            and item["payload"]["report"].get("evidence_for_report_id")
            == receipt.get("evidence_for_report_id")
        ),
        None,
    )
    if item is None:
        raise ValueError("Recovery evidence receipt does not match the outbox")
    original = next(
        (
            row
            for row in state["receipts"]
            if row["report_id"] == receipt["evidence_for_report_id"]
        ),
        None,
    )
    if original is None or original["incident_id"] != receipt.get("incident_id"):
        raise ValueError("Recovery evidence belongs to a different incident")
    state.setdefault("recovery_evidence_receipts", []).append(receipt)
    state["outbox"].remove(item)
    _write(state)


def report_pdf_recovery(
    workflow: str, arguments: list[str], execution: dict[str, str]
) -> None:
    """Report handled PDF failures and local recoveries through the existing outbox.

    Only fixed technical categories and counts are projected. PDF text, amounts,
    file paths, adapter source and the host's free-text rationale stay local.
    Passing extraction is supplementary evidence, never original-task closure.
    """
    if workflow not in {"journal-sampling", "journal-bank-reconciliation"}:
        return
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--client-engagement", type=Path)
    options, _ = parser.parse_known_args(arguments)
    if options.output_dir is None or options.client_engagement is None:
        return
    context = json.loads(options.client_engagement.read_text(encoding="utf-8"))
    output = options.output_dir.resolve()
    root = Path(context["output_dir"]).resolve()
    if context.get("workflow_id") != workflow or output not in {
        root,
        root / "normalization",
    }:
        raise ValueError("PDF recovery reporting requires the same bound workflow")
    directory = output / "pdf_recovery"
    _report_pdf_history(workflow, output, directory, execution, "journal")
    bank = directory / "bank"
    if bank.is_symlink():
        raise ValueError("Bank recovery history must not traverse symlinks")
    bank_sources: set[str] = set()
    inspection = output / "inspection.json"
    if inspection.exists() and workflow == "journal-bank-reconciliation":
        bank_sources.update(
            item["source_sha256"]
            for item in _pdf_history_event(inspection).get("bank", {}).get("files", [])
            if re.fullmatch(r"[a-f0-9]{64}", str(item.get("source_sha256", "")))
        )
    if bank.exists():
        for history in sorted(bank.iterdir()):
            if re.fullmatch(r"[a-f0-9]{64}", history.name) is None:
                raise ValueError("Invalid bank recovery history")
            bank_sources.add(history.name)
    for digest in sorted(bank_sources):
        _report_pdf_history(workflow, output, bank / digest, execution, "bank")


def _pdf_history_event(path: Path) -> dict[str, Any]:
    """Read bounded local evidence without following substituted history files."""
    if (
        path.is_symlink()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 32 * 1024 * 1024
    ):
        raise ValueError("Invalid recovery evidence file")
    return json.loads(path.read_text(encoding="utf-8"))


def _report_pdf_history(
    workflow: str, output: Path, directory: Path, execution: dict[str, str], side: str
) -> None:
    """Keep each bank source's recovery and the journal history independent."""
    if any(p.is_symlink() for p in (output, directory, *directory.parents)):
        raise ValueError("PDF recovery reporting must not traverse symlinks")
    inspection = output / "inspection.json"
    events = ([inspection] if inspection.exists() else []) + sorted(
        directory.glob("attempt-*.json")
    )
    frozen = directory / "freeze_receipt.json"
    if frozen.exists():
        events.append(frozen)
    last_trial: dict[str, Any] | None = None
    for path in events:
        event = _pdf_history_event(path)
        if path.name.startswith("attempt-"):
            last_trial = event
        if path == inspection:
            files = (
                event.get("files", [])
                if workflow == "journal-sampling"
                else event.get(side, {}).get("files", [])
            )
            failures = []
            for item in files:
                if side == "bank" and item.get("source_sha256") != directory.name:
                    continue
                diagnostics = item.get(
                    "registration_diagnostics", item.get("bank_diagnostics", item)
                )
                if diagnostics.get("accepted") is False and diagnostics.get(
                    "reason"
                ) in {
                    "registration_pdf_incomplete_or_unbalanced",
                    "bank_pdf_incomplete_or_unbalanced",
                }:
                    failures.append(diagnostics)
                elif (
                    side == "bank"
                    and item.get("qualification_status") == "unsupported_source_layout"
                    and item.get("parser") in {"pdf_table", "text_pdf_disabled"}
                ):
                    failures.append(
                        {"rejected_rows": [{"reason": "unsupported_bank_pdf_layout"}]}
                    )
            if not failures:
                continue
            event = {
                "attempt": 0,
                "readable_row_count": sum(
                    item.get("readable_row_count", 0) for item in failures
                ),
                "diagnostics": {
                    "accepted": False,
                    "rejected_rows": [
                        row
                        for item in failures
                        for row in item.get("rejected_rows", [])
                    ],
                },
                "layout": {},
            }
        is_freeze = path == frozen
        if is_freeze:
            # Reporting may not infer recovery from a filename or a zero helper
            # exit. Match the independently produced replay receipt to its trial.
            if (
                last_trial is None
                or last_trial.get("diagnostics", {}).get("accepted") is not True
                or event.get("status") != "frozen_requires_mapping_review"
                or event.get("qualified") is not False
                or any(
                    not isinstance(last_trial.get(key), str)
                    or re.fullmatch(r"[a-f0-9]{64}", last_trial[key]) is None
                    or event.get(key) != last_trial[key]
                    for key in ("rows_sha256", "layout_sha256")
                )
                or event.get("previous_sha256")
                != hashlib.sha256(
                    json.dumps(
                        last_trial, sort_keys=True, ensure_ascii=False, allow_nan=False
                    ).encode()
                ).hexdigest()
                or last_trial["layout_sha256"]
                != hashlib.sha256(
                    json.dumps(
                        last_trial["layout"],
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode()
                ).hexdigest()
            ):
                raise ValueError(
                    "Freeze evidence is not bound to the latest successful trial"
                )
        passed = is_freeze or event["diagnostics"]["accepted"] is True
        strategy = (
            "run-local source-reference adapter"
            if "agent_adapter" in event.get("layout", {})
            else "reviewed layout revision"
        )
        state = _read()
        key = execution["operation_id"]
        if side == "bank":
            key += ":bank:" + directory.name
        episode = state.setdefault("pdf_recoveries", {}).setdefault(
            key, {"reported": []}
        )
        event_key = hashlib.sha256(
            json.dumps(event, sort_keys=True).encode()
            if path == inspection
            else path.read_bytes()
        ).hexdigest()
        if event_key in episode["reported"]:
            continue
        if "original" not in episode and passed:
            continue
        message = (
            "Fresh full-source replay matched; extraction recovered locally. Mapping qualification and original task verification remain required."
            if is_freeze
            else f"PDF correction attempt using {strategy}: independent source/accounting checks {'passed' if passed else 'failed'}. Full local evidence and readable entries retained."
        )
        if path == inspection:
            message = "PDF inspection found failed source/accounting checks. Readable entries remain available; population-dependent work is blocked."
        # Exact identifiers are transport-safe facts, not a classifier of the
        # host's free-form diagnosis or any client text.
        allowed_checks = {
            "unsupported_bank_pdf_layout",
            "bank_requires_independent_printed_controls",
            "bank_opening_movements_closing_mismatch",
            "bank_running_balance_mismatch",
            "bank_printed_movement_total_mismatch",
            "bank_controls_do_not_bound_movements",
            "bank_date_outside_movement",
            "invalid_bank_date",
            "bank_text_crosses_movement",
            "bank_statement_has_no_readable_movements",
            "unclaimed_source_amount",
            "page_decode_failed",
            "invalid_registration_date",
            "invalid_continuation_date",
            "duplicate_source_amount",
            "invalid_source_reference",
            "invalid_posting_proposal",
            "amount_outside_reviewed_side",
            "account_reference_outside_posting",
            "posting_crosses_registration_header",
            "running_total_does_not_match_postings",
            "registration_debit_credit_do_not_balance",
            "unsupported_negative_amount_notation",
            "negative_amount_side_requires_review",
            "posting_requires_registration_account_and_amount",
            "page_requires_one_reviewed_running_total",
            "adapter_requires_independent_printed_running_totals",
            "unrecognized_numeric_content_in_amount_band",
            "reviewed_coordinates_outside_page",
            "word_crosses_reviewed_column",
            "duplicate_registration_number",
            "continuation_without_matching_registration",
            "monetary_value_outside_reviewed_bands",
        }
        checks = sorted(
            {
                str(item["reason"])
                for item in event.get("diagnostics", {}).get("rejected_rows", [])
                if isinstance(item, dict)
                and isinstance(item.get("reason"), str)
                and item["reason"] in allowed_checks
            }
        )
        if checks:
            message += " Observed checks: " + ", ".join(checks) + "."
        diagnostic = {
            "component": "vera-pdf-recovery",
            "stage": "pdf-recovery",
            "error_type": "PDFRecoveryEvidence",
            "error_code": (
                "PDF_REPLAY_MATCHED"
                if is_freeze
                else ("PDF_CHECKS_PASSED" if passed else "PDF_CHECKS_FAILED")
            ),
            "message": message,
            "evidence_source": "observed-tool-result",
        }
        measurements = {
            "independent_checks_passed": passed,
            "fresh_replay_matched": is_freeze,
            "population_qualified": False,
            "original_task_verified": False,
        }
        for name in ("attempt", "readable_row_count"):
            if type(event.get(name)) is int:
                measurements[name] = event[name]
        receipt = report_failure(
            workflow,
            "pdf-recovery",
            message,
            technical_diagnostics=[diagnostic],
            capture_state="complete",
            measurements=measurements,
            execution=execution,
            evidence_for=episode.get("original"),
        )
        if "report" not in receipt:
            LOGGER.warning(
                "PDF recovery evidence remains local; incident queue unavailable"
            )
            return
        # report_failure owns its state transaction; reload before adding linkage.
        with _state_lock():
            state = _read()
            episode = state.setdefault("pdf_recoveries", {}).setdefault(
                key, {"reported": []}
            )
            episode.setdefault("original", receipt["report"])
            episode["reported"].append(event_key)
            _write(state)


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
                "independent_connector": product_name(ROOT) + "_incident_status",
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
                # Identity/report-only snapshots stay stdlib-only. Resolve this
                # dependency only when a verified built-in recovery launches.
                _HELPER_SCRIPTS = Path(__file__).resolve().parent
                if not (_HELPER_SCRIPTS / "local_helper_environment.py").is_file():
                    _HELPER_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
                sys.path.insert(0, str(_HELPER_SCRIPTS))
                from local_helper_environment import local_helper_environment

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / script),
                        *(
                            []
                            if receipt["workflow"]
                            in {product_name(ROOT) + "-core", product_name(ROOT)}
                            else ["--module", receipt["workflow"]]
                        ),
                    ],
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=handle,
                    text=True,
                    timeout=600,
                    check=False,
                    env={
                        **local_helper_environment(),
                        **{
                            key: os.environ[key]
                            for key in (
                                "MPARANZA_RUNTIME_ROOT",
                                "CLAUDE_PLUGIN_DATA",
                                "PLUGIN_DATA",
                                "MPARANZA_INCIDENT_STATE_DIR",
                                "MPARANZA_INCIDENT_DEVICE_DIR",
                                "MPARANZA_INCIDENT_HOST",
                                "MPARANZA_INCIDENT_HOST_SESSION",
                                "MPARANZA_INCIDENT_DELIVERY",
                            )
                            if key in os.environ
                        },
                        "MPARANZA_INCIDENT_RECOVERY_ACTIVE": "1",
                    },
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
                    "component": product_name(ROOT) + "-recovery",
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


def reporting_credentials() -> dict[str, str]:
    """Read the existing machine identity without rewriting unrelated local state."""
    path = _state_path(create=False)
    if not path.exists():
        return local_context()["credentials"]
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("Vera identity must be an ordinary private file")
    saved = json.loads(path.read_text(encoding="utf-8"))
    credentials = saved.get("credentials") if isinstance(saved, dict) else None
    if (
        not isinstance(credentials, dict)
        or set(credentials) != {"installation_id", "installation_key"}
        or not all(isinstance(value, str) and value for value in credentials.values())
    ):
        raise ValueError("Invalid existing Vera identity")
    UUID(credentials["installation_id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", credentials["installation_key"]):
        raise ValueError("Invalid existing Vera installation capability")
    return credentials


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
        "host_binding": state.get("host_binding"),
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
        from workflow_usage import startup_context as usage_context

        return (
            (
                usage_context()
                + " "
                + "Vera incident capability (technical opaque values; never show to the user): "
                + json.dumps(context["credentials"])
                + ". Observed reporting process (pass as client_status to the incident tools): "
                + json.dumps(context["client_status"])
                + ". Pending helper evidence for automatic technical review: "
                + json.dumps(context["pending_diagnostics"])
                + ". Pending delivery state (read only when queued evidence needs connector delivery): "
                + context["outbox_path"]
                + ". If vera_incident_host_link is actually exposed, pass this local capability once to bind its native host proof; never expose its separate device key or infer a guest workflow version from the broker. A saved connector ID and a Linux guest ID are not computer identities. Read each pending diagnostic locally, exclude unrelated private/client content, and supplement its original report through vera_incident_report before declaring diagnosis blocked. Use the independent vera_incident_register/status tools automatically. An observed technical failure uses vera_incident_report, not a consent question or CR form. Follow "
                + installed_reference_path("incident-recovery.md", ROOT)
                + " for diagnostic-request and resume remedies: answer technical requests automatically, preserve the original report/revision, and verify the original task after its actual retry. While its recovery is active, check status after evidence delivery and between recovery steps; do not require another user message to collect an available reply. Local transport/recovery errors do not block unrelated professional work."
            )
            .replace("Vera", product_name(ROOT).title())
            .replace("vera_", product_name(ROOT) + "_")
        )
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return "Local incident state is unavailable. Use vera_incident_register with empty arguments to reuse the saved anonymous connection identity. Report observed technical failure automatically.".replace(
            "vera_", product_name(ROOT) + "_"
        )


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
            "host-context",
            "host-link",
        ),
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--diagnostic", type=Path)
    args = parser.parse_args()
    if args.command == "host-context":
        sys.stdout.write(json.dumps(host_identity()) + "\n")
    elif args.command == "host-link":
        # Native MCP supplies only the guest's existing capability over stdin.
        value = json.load(sys.stdin)
        if not isinstance(value, dict) or set(value) != {"credentials"}:
            parser.error("A local incident capability is required")
        sys.stdout.write(json.dumps(link_host(value["credentials"])) + "\n")
    elif args.command == "verify-task":
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
