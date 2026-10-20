"""Exercise task persistence through the native service outside the chat sandbox."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest

from modules.operational_incidents.api import _dispatch
from modules.operational_incidents.store import IncidentStore
from tests.plugins.test_incident_native_host import call, installed

__all__: list[str] = []

PIPELINES = {
    "vera": "journal-bank-reconciliation",
    "clara": "reporting-engine",
    "lucia": "contenzioso-tributario",
}


@pytest.fixture
def native_service(tmp_path):
    store = IncidentStore(tmp_path / "service.sqlite3")
    rejected_runs = set()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            operation = self.path.rsplit("/", 1)[-1]
            requests.append((operation, payload))
            rejected = payload.get("event", {}).get("run_id") in rejected_runs
            value = {} if rejected else _dispatch(store, operation, payload)
            encoded = json.dumps(value).encode()
            self.send_response(503 if rejected else 200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield store, f"http://127.0.0.1:{server.server_port}", rejected_runs, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def start_arguments(run_id, product="vera"):
    return {
        "operation": "start",
        "run_id": run_id,
        "pipeline": PIPELINES[product],
        "host": "codex",
        "sample_kind": "agent_test",
    }


def queued_rows(tmp_path, run_id):
    database = tmp_path / "unused-task-state/workflow-usage.sqlite3"
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT payload,receipt FROM events WHERE run_id=? ORDER BY sequence",
            (run_id,),
        ).fetchall()


@pytest.mark.parametrize("product", PIPELINES)
def test_native_task_start_retry_completion_and_status_preserve_owner_and_old_queue(
    native_service, tmp_path, product
):
    store, endpoint, rejected_runs, requests = native_service
    root = installed(tmp_path, endpoint, product)
    device = tmp_path / "native-host"
    tool = f"{product}_workflow_usage"
    historical_run = str(uuid4())
    rejected_runs.add(historical_run)
    old = call(root, device, tool, start_arguments(historical_run, product))
    old_rows = queued_rows(tmp_path, historical_run)
    saved_identity = (tmp_path / "unused-task-state/state.json").read_bytes()
    identity = json.loads(saved_identity)["credentials"]
    run_id = str(uuid4())
    requests.clear()

    started = call(root, device, tool, start_arguments(run_id, product))
    repeated = call(root, device, tool, start_arguments(run_id, product))
    completed = call(
        root,
        device,
        tool,
        {"operation": "record", "run_id": run_id, "kind": "completed"},
    )
    status = call(root, device, tool, {"operation": "status", "run_id": run_id})

    assert old["structuredContent"]["delivery"]["queued"] == 1
    assert started["structuredContent"]["delivery"]["delivered"] == 1
    assert repeated["structuredContent"]["delivery"]["delivered"] == 0
    assert completed["structuredContent"]["delivery"]["queued"] == 0
    remote = status["structuredContent"]["remote"]
    assert remote["installation_id"] == identity["installation_id"]
    assert remote["state"] == "completed"
    assert remote["sequence"] == 2
    assert remote["sample_kind"] == "agent_test"
    assert remote["product"] == product
    assert remote["current_version"] == "0.1.391"
    computer = json.loads((device / "identity.json").read_text())
    assert remote["reporting"]["computer_link"] == "verified"
    assert remote["reporting"]["computer_id"] == computer["device_id"]
    assert identity["installation_key"] not in json.dumps(status)
    assert computer["device_key"] not in json.dumps(status)
    assert queued_rows(tmp_path, historical_run) == old_rows
    assert (tmp_path / "unused-task-state/state.json").read_bytes() == saved_identity
    transmitted_runs = {
        payload["event"]["run_id"]
        for operation, payload in requests
        if operation == "workflow-record"
    }
    assert transmitted_runs == {run_id}
    assert len(store.workflow_inspect(run_id)["events"]) == 2
    payload, receipt = queued_rows(tmp_path, run_id)[0]
    assert (
        json.loads(receipt)["payload_sha256"]
        == hashlib.sha256(payload.encode()).hexdigest()
    )
    assert json.loads(receipt)["installation_id"] == identity["installation_id"]


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("sandbox-exec") is None,
    reason="Reproduce the observed macOS chat sandbox boundary",
)
def test_native_service_persists_when_chat_shell_cannot_write_global_state(
    native_service, tmp_path
):
    _, endpoint, _, _ = native_service
    root = installed(tmp_path, endpoint)
    device = tmp_path / "native-host"
    call(root, device, "vera_workflow_usage", start_arguments(str(uuid4())))
    run_id = str(uuid4())
    state = tmp_path / "unused-task-state"
    profile = f"(version 1)(allow default)(deny file-write* (subpath {json.dumps(str(state))}))"

    restricted = subprocess.run(
        [
            "sandbox-exec",
            "-p",
            profile,
            sys.executable,
            str(root / "scripts/workflow_usage.py"),
            "start",
            "--run-id",
            run_id,
            "--pipeline",
            PIPELINES["vera"],
            "--host",
            "codex",
            "--sample-kind",
            "agent_test",
        ],
        env={
            **os.environ,
            "MPARANZA_INCIDENT_STATE_DIR": str(state),
            "MPARANZA_INCIDENT_DEVICE_DIR": str(device),
            "MPARANZA_INCIDENT_HOST": "codex",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = call(root, device, "vera_workflow_usage", start_arguments(run_id))

    assert restricted.returncode == 1
    assert "Usage reporting unavailable (OperationalError)" in restricted.stderr
    assert "operation=start" in restricted.stderr
    assert "SQLITE_READONLY" in restricted.stderr
    assert result["structuredContent"]["delivery"]["delivered"] == 1
    assert len(queued_rows(tmp_path, run_id)) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"operation": "flush"},
        {"operation": "flush", "run_id": str(uuid4()), "all": True},
        {"operation": "start", "run_id": str(uuid4()), "command": "PRIVATE_SENTINEL"},
        {
            "operation": "record",
            "run_id": str(uuid4()),
            "kind": "completed",
            "fields": {"deliver": False},
        },
        {"operation": "record", "run_id": str(uuid4()), "kind": "receipt"},
    ],
)
def test_native_usage_rejects_commands_and_global_queue_operations_before_storage(
    tmp_path, arguments
):
    root = installed(tmp_path)
    device = tmp_path / "native-host"

    result = call(root, device, "vera_workflow_usage", arguments)

    assert result["isError"] is True
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert not (tmp_path / "unused-task-state").exists()
    assert not device.exists()


def test_native_usage_storage_failure_has_source_and_sqlite_facts(tmp_path):
    root = installed(tmp_path)
    state = tmp_path / "unused-task-state"
    state.mkdir()
    (state / "workflow-usage.sqlite3").write_bytes(b"PRIVATE_SENTINEL not a database")

    result = call(
        root,
        tmp_path / "native-host",
        "vera_workflow_usage",
        start_arguments(str(uuid4())),
    )

    assert result["isError"] is True
    facts = result["structuredContent"]["technical_facts"]
    assert facts["sqlite_errorname"] == "SQLITE_NOTADB"
    assert facts["events"]
    assert "PRIVATE_SENTINEL" not in json.dumps(result)


def test_native_flush_delivers_the_retained_event_without_replacing_it(
    native_service, tmp_path
):
    _, endpoint, rejected_runs, _ = native_service
    root = installed(tmp_path, endpoint)
    device = tmp_path / "native-host"
    run_id = str(uuid4())
    rejected_runs.add(run_id)
    call(root, device, "vera_workflow_usage", start_arguments(run_id))
    original_payload, original_receipt = queued_rows(tmp_path, run_id)[0]
    rejected_runs.clear()

    result = call(
        root, device, "vera_workflow_usage", {"operation": "flush", "run_id": run_id}
    )

    assert original_receipt is None
    assert result["structuredContent"]["delivered"] == 1
    assert result["structuredContent"]["queued"] == 0
    payload, receipt = queued_rows(tmp_path, run_id)[0]
    assert payload == original_payload
    assert json.loads(receipt)["event_id"] == json.loads(payload)["event_id"]


@pytest.mark.parametrize(
    "relative", ["scripts/workflow_usage.py", "usage/pipelines.json"]
)
def test_native_usage_checks_its_added_snapshot_components_before_execution(
    tmp_path, relative
):
    root = installed(tmp_path)
    (root / relative).write_text("PRIVATE_SENTINEL")

    result = call(
        root,
        tmp_path / "native-host",
        "vera_workflow_usage",
        start_arguments(str(uuid4())),
    )

    assert result["isError"] is True
    assert "build index" in result["content"][0]["text"]
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert not (tmp_path / "unused-task-state").exists()
