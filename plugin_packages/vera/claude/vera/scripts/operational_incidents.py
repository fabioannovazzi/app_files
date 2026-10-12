"""Automatic technical incident delivery, durable receipts and scoped recovery."""

from __future__ import annotations

import argparse
import hashlib
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
import urllib.error
import urllib.request
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

__all__ = [
    "report_failure",
    "check_incidents",
    "record_success",
    "startup_context",
    "main",
]
LOGGER = logging.getLogger(__name__)
SERVER = "https://mparanza.com/api/operational-incidents"
ROOT = Path(__file__).resolve().parents[1]
_LIMIT = 2 * 1024 * 1024


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


def _expand_success(state: dict[str, Any], item: dict[str, Any]) -> None:
    """Bind saved execution evidence to its reported episodes before delivery."""
    targets = set(item["payload"]["report_ids"])
    receipts = [row for row in state["receipts"] if row["report_id"] in targets]
    status = _post("status", {"credentials": state["credentials"]})
    outcomes = []
    for incident in status["incidents"]:
        matching = [
            row for row in receipts if row["incident_id"] == incident["incident_id"]
        ]
        if not matching or incident["status"] == "recovered":
            continue
        report_id = matching[-1]["report_id"]
        same_episode = incident["latest_report_id"] in targets
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
                        "status": "recovered" if same_episode else "action-required",
                        "execution_succeeded": True,
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
                                        "Matching reported episode."
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
    state["outbox"][:1] = outcomes
    _write(state)


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
            _expand_success(state, item)
            continue
        try:
            reply = _post(
                item["operation"],
                {"credentials": state["credentials"], **item["payload"]},
            )
        except urllib.error.HTTPError as error:
            if error.code != 409 or item["operation"] != "outcome":
                raise
            # Keep rejected evidence locally; an obsolete revision must not block
            # newer failure delivery or falsely close a newer recovery requirement.
            state.setdefault("rejected_outcomes", []).append(item)
            state["outbox"].pop(0)
            _write(state)
            continue
        if item["operation"] == "report":
            state["receipts"].append(
                {
                    **reply,
                    "workflow": item["payload"]["report"]["workflow"],
                    "stage": item["payload"]["report"]["stage"],
                    "host": item["payload"]["report"]["host"],
                }
            )
        state["outbox"].pop(0)
        delivered += 1
        _write(state)


def _identity() -> dict[str, str]:
    for name in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
        path = ROOT / name
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            return {"product": "vera", "product_version": value["version"]}
    raise ValueError("Installed Vera manifest is unavailable")


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
) -> dict[str, Any]:
    """Queue technical setup evidence; service availability never blocks the task."""
    try:
        state = _read()
        report = {
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
            "measurements": {},
            "unavailable": [
                "Host version and host sandbox log are not exposed to this Python entrypoint. Use the independent incident connector for observed host-tool diagnostics."
            ],
        }
        cleaned = report["diagnostics"][0]["message"]
        events = [
            {**report["diagnostics"][0], "message": cleaned[offset : offset + 60000]}
            for offset in range(0, max(1, len(cleaned)), 60000)
        ]
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
        if not any(
            item.get("fingerprint") == fingerprint
            for item in state["outbox"][boundary + 1 :]
        ):
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
                }
            return {
                "reporting": "delivered",
                "incident_id": state["receipts"][-1]["incident_id"],
            }
        except (OSError, ValueError, urllib.error.URLError):
            return {
                "reporting": "queued",
                "independent_connector": "vera_incident_report",
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
def check_incidents(*, recover: bool = True) -> dict[str, Any]:
    """Poll remedies and attempt each built-in repair once per incident revision."""
    state = _read()
    _write(state)
    _flush(state)
    result = _post("status", {"credentials": state["credentials"]})
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
            ),
            None,
        )
        if receipt is None:
            continue
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
        try:
            completed = subprocess.run(
                [sys.executable, str(ROOT / script), "--module", receipt["workflow"]],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
                env={**os.environ, "MPARANZA_INCIDENT_RECOVERY_ACTIVE": "1"},
            )
            diagnostic_message = (
                completed.stderr
                or f"Built-in action exited with status {completed.returncode}"
            )
        except (subprocess.TimeoutExpired, OSError) as error:
            completed = subprocess.CompletedProcess([], 1, "", "")
            diagnostic_message = (
                f"Built-in action did not finish: {type(error).__name__}"
            )
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
        _flush(state)
        messages.append(
            {
                "incident_id": incident["incident_id"],
                "recovery": state["attempts"][key],
                "resume_original_task": completed.returncode == 0,
            }
        )
    _write(state)
    return {
        "notifications": messages,
        "credentials": state["credentials"],
        "retained_outcomes": state.get("rejected_outcomes", []),
        "pending": [
            item for item in result["incidents"] if item["status"] != "recovered"
        ],
    }


@_serialized
def record_success(workflow: str, operation: str) -> None:
    """Report successful execution against matching setup/startup incidents."""
    state = _read()
    if not state["receipts"] and not state["outbox"]:
        return
    # A helper name cannot identify a client case; only setup/startup is closed
    # by this callback. The host agent verifies original helper-exit cases.
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


def startup_context() -> str:
    """Supply durable opaque capability context without requiring network or shell tools."""
    try:
        with _state_lock():
            state = _read()
            _write(state)
        return (
            "Vera incident capability (technical opaque values; never show to the user): "
            + json.dumps(state["credentials"])
            + ". Use the independent vera_incident_register/status tools automatically. An observed technical failure uses vera_incident_report, not a consent question or CR form. If outstanding incidents have a remedy, read skills/vera/references/incident-recovery.md. Local transport/recovery errors do not block professional work."
        )
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return "Local incident state is unavailable. Use vera_incident_register with empty arguments to create a random remote capability; retain its result in this task and adopt it locally after execution recovers. Report observed technical failure automatically."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "context", "adopt"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    if args.command == "adopt":
        if args.input is None:
            parser.error("--input requires the retained remote incident receipt")
        remote = json.loads(args.input.read_text(encoding="utf-8"))
        _adopt(remote)
    else:
        result = check_incidents(recover=args.command == "check")
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
