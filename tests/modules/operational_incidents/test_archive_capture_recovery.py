"""Real Archive failure -> technical HTTP intake -> same-input refresh recovery."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.operational_incidents import api
from modules.operational_incidents.contracts import Remedy, Report
from tests.modules.operational_incidents.test_incidents import registered
from tests.plugins.test_incident_technical_runner import RUNNER, archive_command


def test_handled_archive_error_reaches_service_and_original_refresh_can_recover(
    tmp_path, monkeypatch
):
    # The only source is an original synthetic text file, present before failure.
    archive = tmp_path / "original-archive"
    customer = archive / "Synthetic client"
    customer.mkdir(parents=True)
    original = customer / "source.txt"
    original.write_text("Synthetic original source for the capture regression.")
    original_digest = hashlib.sha256(original.read_bytes()).hexdigest()
    arguments = ["refresh"]
    failure, captured = archive_command(tmp_path, arguments)
    assert failure.returncode == 1

    store, owner = registered(tmp_path)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_incident_store] = lambda: store
    monkeypatch.setattr(api, "_RATE_EVENTS", api.OrderedDict())
    monkeypatch.setattr(api, "_GLOBAL_EVENTS", api.deque())
    client = TestClient(app)
    capability = owner.model_dump(mode="json")
    operation = str(uuid4())
    diagnostics = [
        {
            **{key: value for key, value in item.items() if key != "detail_available"},
            "component": "vera-runtime",
            "stage": "helper:studio_archive.py",
            "exit_code": 1,
            "evidence_source": "runtime-exception",
        }
        for item in captured["events"]
    ]
    version = json.loads((RUNNER.parents[1] / ".codex-plugin/plugin.json").read_text())[
        "version"
    ]
    report = Report(
        report_id=uuid4(),
        product_version=version,
        host="codex",
        platform=captured["worker_platform"],
        runtime_version=captured["worker_runtime_version"],
        worker_platform=captured["worker_platform"],
        worker_runtime_version=captured["worker_runtime_version"],
        workflow="studio-archive",
        stage="helper:studio_archive.py",
        operation_id=operation,
        input_binding=original_digest,
        capture_state="complete",
        diagnostics=diagnostics,
    )
    sent = client.post(
        "/api/operational-incidents/report",
        json={"credentials": capability, "report": report.model_dump(mode="json")},
    )
    assert sent.status_code == 200
    receipt = sent.json()
    incident_id = receipt["incident_id"]
    before = store.show(incident_id)
    assert (
        before["reports"][0]["diagnostics"][0]["error_type"]
        == "ArchiveNotConfiguredError"
    )
    assert original.read_text() not in json.dumps(before)
    remedy = store.remedy(
        incident_id,
        Remedy(
            target_report_id=report.report_id,
            kind="resume",
            summary="Connect the already-authorized synthetic archive and retry refresh",
            evidence="The actual worker captured ArchiveNotConfiguredError and its source message.",
            instructions="Use the normal archive configuration for the original fixture root, then retry the same refresh and verify its result and unchanged source.",
            expected_outcome="The original source is indexed without failed files.",
        ),
    )
    status = client.post(
        "/api/operational-incidents/status", json={"credentials": capability}
    )
    assert status.status_code == 200
    premature = {
        "outcome_id": str(uuid4()),
        "incident_id": incident_id,
        "report_id": str(report.report_id),
        "remedy_revision": remedy["revision"],
        "operation_id": operation,
        "input_binding": original_digest,
        "status": "recovered",
        "execution_succeeded": True,
    }
    refused = client.post(
        "/api/operational-incidents/outcome",
        json={"credentials": capability, "outcome": premature},
    )
    assert refused.status_code == 409
    assert store.show(incident_id)["status"] == "open"

    configured, _ = archive_command(
        tmp_path,
        [
            "configure",
            "--archive-root",
            str(archive.resolve()),
            "--host-folder-access-approved",
        ],
    )
    assert configured.returncode == 0
    started = {
        "event_id": str(uuid4()),
        "incident_id": incident_id,
        "report_id": str(report.report_id),
        "remedy_revision": remedy["revision"],
        "operation_id": operation,
        "kind": "retry-started",
    }
    progress = client.post(
        "/api/operational-incidents/progress",
        json={"credentials": capability, "progress": started},
    )
    assert progress.status_code == 200
    retried, diagnostic = archive_command(tmp_path, arguments)
    assert retried.returncode == 0
    result = json.loads(retried.stdout)
    assert result["status"] == "refreshed"
    assert result["indexed_files"] == 1
    assert result["failed_files"] == 0
    assert diagnostic is None
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_digest
    succeeded = {**started, "event_id": str(uuid4()), "kind": "retry-succeeded"}
    progress = client.post(
        "/api/operational-incidents/progress",
        json={"credentials": capability, "progress": succeeded},
    )
    assert progress.status_code == 200
    actual = {**premature, "outcome_id": str(uuid4()), "original_task_verified": True}
    recovered = client.post(
        "/api/operational-incidents/outcome",
        json={"credentials": capability, "outcome": actual},
    )

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "recovered"
    assert store.show(incident_id)["status"] == "recovered"
    assert store.queue() == []
