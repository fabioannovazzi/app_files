"""Incident lifecycle, remote transport and privacy/security boundaries."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from modules.operational_incidents.api import TOOLS, get_incident_store, router
from modules.operational_incidents.contracts import Credentials, Outcome, Remedy, Report
from modules.operational_incidents.store import (
    IncidentConflict,
    IncidentNotFound,
    IncidentStore,
)


def credentials() -> Credentials:
    return Credentials(installation_id=uuid4(), installation_key=uuid4().hex)


def report() -> Report:
    return Report(
        report_id=uuid4(),
        product_version="0.1.361",
        host="codex",
        platform="unknown",
        workflow="journal-sampling",
        stage="execution-startup",
        diagnostics=[
            {
                "component": "host-exec",
                "error_type": "CreateProcessError",
                "stage": "execution-startup",
                "message": "setup refresh had errors",
                "evidence_source": "observed-tool-result",
            }
        ],
        unavailable=["Host technical log inaccessible because local execution failed"],
    )


def registered(tmp_path):
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    first = credentials()
    store.register(first)
    return store, first


def test_full_incident_remedy_delivery_and_actual_recovery(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    remedy = Remedy(
        kind="user-action",
        summary="Complete the pending host update",
        evidence="Host status is restart_required",
        instructions="Fully close and reopen the host",
        expected_outcome="Original helper starts and runs",
    )
    delivery = store.remedy(receipt["incident_id"], remedy)
    status = store.status(first)["incidents"][0]
    assert status["remedy"]["instructions"] == "Fully close and reopen the host"
    result = store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=receipt["incident_id"],
            remedy_revision=delivery["revision"],
            status="recovered",
            execution_succeeded=True,
        ),
    )
    assert result["status"] == "recovered"
    assert store.queue() == []
    assert (
        store.show(receipt["incident_id"])["outcomes"][0]["execution_succeeded"] is True
    )


def test_identical_signals_share_investigation_without_closing_other_users(tmp_path):
    store, first = registered(tmp_path)
    second = credentials()
    store.register(second)
    one = store.report(first, report())
    two = store.report(second, report())
    assert one["incident_id"] == two["incident_id"]
    store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=one["incident_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
        ),
    )
    assert store.queue()[0]["status"] == "open"
    assert store.status(second)["incidents"][0]["status"] == "open"


def test_report_retries_are_idempotent_and_conflicting_ids_rejected(tmp_path):
    store, first = registered(tmp_path)
    evidence = report()
    original = store.report(first, evidence)
    repeated = store.report(first, evidence)
    assert original["incident_id"] == repeated["incident_id"]
    assert repeated["deduplicated"] is True
    changed = evidence.model_copy(update={"stage": "different-stage"})
    with pytest.raises(IncidentConflict):
        store.report(first, changed)
    assert len(store.queue()[0]["reports"]) == 1


def test_capability_cannot_read_another_installation(tmp_path):
    store, first = registered(tmp_path)
    store.report(first, report())
    wrong = first.model_copy(update={"installation_key": uuid4().hex})
    with pytest.raises(IncidentNotFound):
        store.status(wrong)
    with pytest.raises(IncidentNotFound):
        store.register(wrong)


def test_installation_with_no_reports_sees_no_other_incidents(tmp_path):
    store, first = registered(tmp_path)
    store.report(first, report())
    second = credentials()
    store.register(second)
    assert store.status(second) == {"incidents": []}


def test_update_available_is_not_recovered_and_stale_outcome_is_rejected(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    store.remedy(
        receipt["incident_id"],
        Remedy(
            kind="update",
            summary="Install corrected Vera",
            evidence="Verified published ZIP",
            required_version="0.1.362",
            expected_outcome="Original operation succeeds",
        ),
    )
    assert store.status(first)["incidents"][0]["status"] == "open"
    with pytest.raises(IncidentConflict, match="changed"):
        store.outcome(
            first,
            Outcome(
                outcome_id=uuid4(),
                incident_id=receipt["incident_id"],
                remedy_revision=1,
                status="recovered",
                execution_succeeded=True,
            ),
        )


def test_false_recovery_receipt_is_rejected(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    with pytest.raises(IncidentConflict, match="successful execution"):
        store.outcome(
            first,
            Outcome(
                outcome_id=uuid4(),
                incident_id=receipt["incident_id"],
                remedy_revision=1,
                status="recovered",
            ),
        )
    assert store.queue()[0]["status"] == "open"


def test_failed_recovery_keeps_all_new_diagnostics(tmp_path):
    store, first = registered(tmp_path)
    evidence = report()
    receipt = store.report(first, evidence)
    result = store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=receipt["incident_id"],
            remedy_revision=1,
            status="failed",
            diagnostics=evidence.diagnostics,
        ),
    )
    assert result["status"] == "failed"
    assert (
        store.queue()[0]["outcomes"][0]["diagnostics"][0]["message"]
        == "setup refresh had errors"
    )


def test_recurrence_reopens_a_recovered_delivery(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=receipt["incident_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
        ),
    )
    next_receipt = store.report(first, report())
    assert next_receipt["incident_id"] == receipt["incident_id"]
    assert store.status(first)["incidents"][0]["status"] == "open"


@pytest.mark.parametrize(
    "message",
    [
        "cannot open /Users/private-person/client/report.pdf",
        "cannot open C:\\Users\\private-person\\client\\report.pdf",
        "token=do-not-send foo@example.com",
    ],
)
def test_diagnostic_path_and_credential_values_are_removed_without_losing_stage(
    message,
):
    value = report().model_dump()
    value["diagnostics"][0]["message"] = message
    cleaned = Report.model_validate(value)
    assert "private-person" not in cleaned.diagnostics[0].message
    assert "do-not-send" not in cleaned.diagnostics[0].message
    assert "foo@example.com" not in cleaned.diagnostics[0].message
    assert cleaned.diagnostics[0].stage == "execution-startup"


def test_unrelated_case_payload_and_remote_shell_repair_are_rejected():
    with pytest.raises(ValidationError):
        Report.model_validate(
            {**report().model_dump(), "client_document": "private case"}
        )
    with pytest.raises(ValidationError):
        Remedy(
            kind="automatic",
            summary="Unsupported",
            evidence="Unknown",
            expected_outcome="Unknown",
            action="execute-downloaded-command",
        )


def test_remote_mcp_report_works_without_starting_a_local_process(
    tmp_path, monkeypatch
):
    store, first = registered(tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store

    def blocked(*_args, **_kwargs):
        raise AssertionError("The remote transport must not launch a local process")

    monkeypatch.setattr("subprocess.run", blocked)
    client = TestClient(app)
    response = client.post(
        "/mcp/vera-incidents",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "vera_incident_report",
                "arguments": {
                    "credentials": first.model_dump(mode="json"),
                    "report": report().model_dump(mode="json"),
                },
            },
        },
    )
    assert response.json()["result"]["structuredContent"]["recorded"] is True
    assert len(store.queue()) == 1


def test_remote_registration_needs_no_local_uuid_generator(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: IncidentStore(
        tmp_path / "store.sqlite3"
    )
    client = TestClient(app)
    reply = client.post(
        "/mcp/vera-incidents",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "vera_incident_register", "arguments": {}},
        },
    ).json()["result"]["structuredContent"]
    assert Credentials.model_validate(reply["credentials"])
    status = client.post(
        "/api/operational-incidents/status", json={"credentials": reply["credentials"]}
    )
    assert status.json() == {"incidents": []}


def test_mcp_schemas_have_resolvable_references():
    tool = next(item for item in TOOLS if item["name"] == "vera_incident_report")
    validator = Draft202012Validator(tool["inputSchema"])
    validator.validate(
        {
            "credentials": credentials().model_dump(mode="json"),
            "report": report().model_dump(mode="json"),
        }
    )


def test_invalid_request_does_not_echo_private_input(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: IncidentStore(
        tmp_path / "store.sqlite3"
    )
    reply = TestClient(app).post(
        "/api/operational-incidents/report", json={"private": "do-not-echo-client"}
    )
    assert reply.status_code == 422
    assert "do-not-echo-client" not in reply.text


def test_retry_of_old_outcome_cannot_close_a_new_failure(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    recovered = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt["incident_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
    )
    store.outcome(first, recovered)
    store.report(first, report())
    store.outcome(first, recovered)
    assert store.queue()[0]["status"] == "open"


def test_public_transport_rate_bound_expires(monkeypatch):
    from fastapi import HTTPException

    from modules.operational_incidents import api

    monkeypatch.setattr(api, "_RATE_EVENTS", api.OrderedDict())
    monkeypatch.setattr(api, "_GLOBAL_EVENTS", api.deque())
    monkeypatch.setattr(api.time, "monotonic", lambda: 100.0)
    for _ in range(120):
        api._admit("technical-source")
    with pytest.raises(HTTPException) as caught:
        api._admit("technical-source")
    assert caught.value.status_code == 429
    monkeypatch.setattr(api.time, "monotonic", lambda: 161.0)
    api._admit("technical-source")
