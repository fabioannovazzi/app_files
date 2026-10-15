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
from tests.modules.operational_incidents.test_oauth import connection_headers


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


def test_scoped_remedy_does_not_reach_another_installation_with_same_signal(tmp_path):
    store, first = registered(tmp_path)
    second = credentials()
    store.register(second)
    one = store.report(first, report())
    two = store.report(second, report())

    store.remedy(
        one["incident_id"],
        Remedy(
            target_report_id=one["report_id"],
            kind="user-action",
            summary="First case action",
            evidence="Only the first cause was established",
            instructions="Resume the first original command",
            expected_outcome="First case succeeds",
        ),
    )

    assert one["incident_id"] == two["incident_id"]
    assert (
        store.status(first)["incidents"][0]["remedy"]["target_report_id"]
        == one["report_id"]
    )
    assert store.status(second)["incidents"][0]["remedy"]["kind"] == "investigating"


def test_other_target_remedy_preserves_first_applicable_revision_and_recovery(tmp_path):
    store, first = registered(tmp_path)
    second = credentials()
    store.register(second)
    one = store.report(first, report())
    two = store.report(second, report())
    store.remedy(
        one["incident_id"],
        Remedy(
            target_report_id=one["report_id"],
            kind="user-action",
            summary="First",
            evidence="First diagnosed cause",
            instructions="First action",
            expected_outcome="First succeeds",
        ),
    )
    store.remedy(
        two["incident_id"],
        Remedy(
            target_report_id=two["report_id"],
            kind="user-action",
            summary="Second",
            evidence="Second diagnosed cause",
            instructions="Second action",
            expected_outcome="Second succeeds",
        ),
    )
    original_revision = store.status(first)["incidents"][0]["revision"]

    recovered = store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=one["incident_id"],
            report_id=one["report_id"],
            remedy_revision=original_revision,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
        ),
    )

    assert original_revision == 2
    assert store.status(second)["incidents"][0]["revision"] == 3
    assert recovered["status"] == "recovered"
    assert store.status(second)["incidents"][0]["status"] == "open"
    assert [
        r["revision"] for r in store.show(one["incident_id"])["remedy_revisions"]
    ] == [1, 2, 3]


def test_new_failure_does_not_inherit_a_remedy_for_an_older_report(tmp_path):
    store, first = registered(tmp_path)
    one = store.report(first, report())
    store.remedy(
        one["incident_id"],
        Remedy(
            target_report_id=one["report_id"],
            kind="user-action",
            summary="Old case",
            evidence="Old cause",
            instructions="Old action",
            expected_outcome="Old succeeds",
        ),
    )
    latest = store.report(first, report())

    state = store.status(first)["incidents"][0]

    assert state["latest_report_id"] == latest["report_id"]
    assert state["remedy"]["kind"] == "investigating"


def test_legacy_migration_keeps_surviving_revision_without_inventing_history(tmp_path):
    import sqlite3

    store, first = registered(tmp_path)
    one = store.report(first, report())
    store.remedy(
        one["incident_id"],
        Remedy(
            target_report_id=one["report_id"],
            kind="user-action",
            summary="Known current action",
            evidence="Current evidence",
            instructions="Current action",
            expected_outcome="Success",
        ),
    )
    with sqlite3.connect(tmp_path / "incidents.sqlite3") as connection:
        connection.execute("DROP TABLE operational_remedy_revisions")
    migrated = IncidentStore(tmp_path / "incidents.sqlite3")

    detail = migrated.show(one["incident_id"])

    assert len(detail["remedy_revisions"]) == 1
    assert detail["remedy_revisions"][0]["revision"] == 2
    assert (
        migrated.status(first)["incidents"][0]["remedy"]["instructions"]
        == "Current action"
    )


def test_obsolete_report_cannot_receive_a_new_remedy(tmp_path):
    store, first = registered(tmp_path)
    old = store.report(first, report())
    store.report(first, report())
    proposed = Remedy(
        target_report_id=old["report_id"],
        kind="user-action",
        summary="Old",
        evidence="Old cause",
        instructions="Old action",
        expected_outcome="Success",
    )

    with pytest.raises(IncidentConflict, match="obsolete"):
        store.remedy(old["incident_id"], proposed)

    assert store.show(old["incident_id"])["revision"] == 1


def test_delayed_failure_for_recovered_episode_is_recorded_without_reopening(tmp_path):
    store, first = registered(tmp_path)
    original = store.report(first, report())
    store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=original["incident_id"],
            report_id=original["report_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
        ),
    )

    delayed = store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=original["incident_id"],
            report_id=original["report_id"],
            remedy_revision=1,
            status="failed",
        ),
    )

    assert delayed["recorded"] is True
    assert delayed["delivery_updated"] is False
    assert store.status(first)["incidents"][0]["status"] == "recovered"
    assert len(store.show(original["incident_id"])["outcomes"]) == 2


@pytest.mark.parametrize("target", [None, "foreign"])
def test_remedy_rejects_missing_or_foreign_original_target(tmp_path, target):
    store, first = registered(tmp_path)
    one = store.report(first, report())
    value = Remedy(
        target_report_id=uuid4() if target else None,
        kind="user-action",
        summary="Action",
        evidence="Cause",
        instructions="Action",
        expected_outcome="Success",
    )

    with pytest.raises((IncidentConflict, IncidentNotFound)):
        store.remedy(one["incident_id"], value)

    assert store.show(one["incident_id"])["revision"] == 1


def test_full_incident_remedy_delivery_and_actual_recovery(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    remedy = Remedy(
        target_report_id=receipt["report_id"],
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
            report_id=receipt["report_id"],
            remedy_revision=delivery["revision"],
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
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
            report_id=one["report_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
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
            target_report_id=receipt["report_id"],
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
                report_id=receipt["report_id"],
                remedy_revision=1,
                status="recovered",
                execution_succeeded=True,
                original_task_verified=True,
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
                report_id=receipt["report_id"],
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
            report_id=receipt["report_id"],
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
            report_id=receipt["report_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
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
        headers=connection_headers(store),
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


def test_remote_registration_reuses_saved_identity_without_local_uuid_generator(
    tmp_path,
):
    store = IncidentStore(tmp_path / "store.sqlite3")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store
    client = TestClient(app)
    headers = connection_headers(store)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "vera_incident_register", "arguments": {}},
    }

    reply = client.post("/mcp/vera-incidents", headers=headers, json=payload).json()[
        "result"
    ]["structuredContent"]
    repeated = client.post("/mcp/vera-incidents", headers=headers, json=payload).json()[
        "result"
    ]["structuredContent"]

    assert reply["installation_id"] == repeated["installation_id"]
    assert reply["binding"] == "saved-connector"
    assert "credentials" not in reply


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
        report_id=receipt["report_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=True,
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


def test_delayed_success_cannot_close_a_newer_reported_episode(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    store.report(first, report())
    with pytest.raises(IncidentConflict, match="newer failure"):
        store.outcome(
            first,
            Outcome(
                outcome_id=uuid4(),
                incident_id=receipt["incident_id"],
                report_id=receipt["report_id"],
                remedy_revision=1,
                status="recovered",
                execution_succeeded=True,
                original_task_verified=True,
            ),
        )
    assert store.queue()[0]["status"] == "open"


def test_recovery_without_report_identity_cannot_close_an_episode(tmp_path):
    store, first = registered(tmp_path)
    receipt = store.report(first, report())
    with pytest.raises(IncidentConflict, match="reported episode"):
        store.outcome(
            first,
            Outcome(
                outcome_id=uuid4(),
                incident_id=receipt["incident_id"],
                remedy_revision=1,
                status="recovered",
                execution_succeeded=True,
                original_task_verified=True,
            ),
        )
    assert store.queue()[0]["status"] == "open"


def test_old_failed_recovery_keeps_evidence_without_reopening_newer_success(tmp_path):
    store, first = registered(tmp_path)
    old = store.report(first, report())
    latest = store.report(first, report())
    store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=latest["incident_id"],
            report_id=latest["report_id"],
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
        ),
    )
    recorded = store.outcome(
        first,
        Outcome(
            outcome_id=uuid4(),
            incident_id=old["incident_id"],
            report_id=old["report_id"],
            remedy_revision=1,
            status="failed",
        ),
    )
    assert recorded["recorded"] is True
    assert recorded["delivery_updated"] is False
    assert store.queue() == []
    assert len(store.show(old["incident_id"])["outcomes"]) == 2


def test_unknown_capability_first_does_not_break_later_registration(tmp_path):
    store = IncidentStore(tmp_path / "new.sqlite3")
    first = credentials()
    with pytest.raises(IncidentNotFound):
        store.status(first)

    result = store.register(first)

    assert result["registered"] is True
    assert store.status(first)["incidents"] == []


def test_saved_connection_reads_reports_after_task_local_identity_changes(tmp_path):
    from modules.operational_incidents.store import ConnectionActor

    store, parent = registered(tmp_path)
    actor = ConnectionActor(parent.installation_id, parent.installation_id)
    task_a = credentials()
    task_b = credentials()
    store.link_connection(actor, task_a)
    receipt = store.report(task_a, report())
    store.link_connection(actor, task_b)

    status = store.connection_status(actor)

    assert status["installation_id"] == str(parent.installation_id)
    assert status["incidents"][0]["latest_report_id"] == receipt["report_id"]
    assert status["incidents"][0]["installation_id"] == str(task_a.installation_id)


def test_saved_connection_rejects_an_unproved_foreign_installation(tmp_path):
    from modules.operational_incidents.store import ConnectionActor

    store, parent = registered(tmp_path)
    actor = ConnectionActor(parent.installation_id, parent.installation_id)
    foreign = credentials()
    store.register(foreign)
    forged = foreign.model_copy(update={"installation_key": "x" * 32})

    with pytest.raises(IncidentNotFound):
        store.link_connection(actor, forged)

    assert store.connection_members(actor) == [str(parent.installation_id)]


def test_saved_connection_recovery_closes_only_the_original_linked_report(tmp_path):
    from modules.operational_incidents.store import ConnectionActor

    store, parent = registered(tmp_path)
    actor = ConnectionActor(parent.installation_id, parent.installation_id)
    task_a = credentials()
    task_b = credentials()
    store.link_connection(actor, task_a)
    store.link_connection(actor, task_b)
    receipt_a = store.report(task_a, report())
    receipt_b = store.report(task_b, report())
    recovery = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt_a["incident_id"],
        report_id=receipt_a["report_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=True,
    )

    result = store.connection_outcome(actor, recovery)

    assert result["status"] == "recovered"
    assert store.status(task_a)["incidents"][0]["status"] == "recovered"
    assert (
        store.status(task_b)["incidents"][0]["latest_report_id"]
        == receipt_b["report_id"]
    )
    assert store.status(task_b)["incidents"][0]["status"] == "open"


def test_saved_connection_cannot_close_an_unlinked_foreign_report(tmp_path):
    from modules.operational_incidents.store import ConnectionActor

    store, parent = registered(tmp_path)
    actor = ConnectionActor(parent.installation_id, parent.installation_id)
    foreign = credentials()
    store.register(foreign)
    receipt = store.report(foreign, report())
    recovery = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt["incident_id"],
        report_id=receipt["report_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=True,
    )

    with pytest.raises(IncidentNotFound):
        store.connection_outcome(actor, recovery)

    assert store.status(foreign)["incidents"][0]["status"] == "open"


def test_reviewed_evidence_attaches_to_original_episode_and_is_idempotent(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    evidence = original.model_copy(
        update={
            "report_id": uuid4(),
            "evidence_for_report_id": original.report_id,
            "diagnostics": original.diagnostics,
        }
    )

    added = store.report(owner, evidence)

    assert added["incident_id"] == receipt["incident_id"]
    assert store.report(owner, evidence)["deduplicated"] is True
    assert len(store.queue()) == 1
    assert store.status(owner)["incidents"][0]["latest_report_id"] == str(
        original.report_id
    )
    assert store.show(receipt["incident_id"])["evidence"][0][
        "evidence_for_report_id"
    ] == str(original.report_id)


def test_supplement_cannot_access_foreign_report_or_change_execution_boundary(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    store.report(owner, original)
    other = credentials()
    store.register(other)
    evidence = original.model_copy(
        update={"report_id": uuid4(), "evidence_for_report_id": original.report_id}
    )

    with pytest.raises(IncidentNotFound):
        store.report(other, evidence)
    with pytest.raises(IncidentConflict):
        store.report(
            owner, evidence.model_copy(update={"workflow": "different-workflow"})
        )


def test_late_diagnostics_do_not_reopen_recovered_original_episode(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    store.outcome(
        owner,
        Outcome(
            outcome_id=uuid4(),
            incident_id=receipt["incident_id"],
            report_id=original.report_id,
            remedy_revision=1,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
        ),
    )
    evidence = original.model_copy(
        update={"report_id": uuid4(), "evidence_for_report_id": original.report_id}
    )

    store.report(owner, evidence)

    assert store.show(receipt["incident_id"])["status"] == "recovered"
    assert store.status(owner)["incidents"][0]["latest_report_id"] == str(
        original.report_id
    )


@pytest.mark.parametrize("linked", [True, False])
def test_saved_connector_supplement_requires_original_installation_link(
    tmp_path, linked
):
    from uuid import UUID

    from modules.operational_incidents.store import ConnectionActor

    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_incident_store] = lambda: store
    client = TestClient(app)
    headers = connection_headers(store)

    def invoke(name, arguments):
        return client.post(
            "/mcp/vera-incidents",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        ).json()["result"]

    registered_connection = invoke("vera_incident_register", {})["structuredContent"][
        "installation_id"
    ]
    if linked:
        actor = ConnectionActor(
            UUID(registered_connection), UUID(registered_connection)
        )
        store.link_connection(actor, owner)
    evidence = original.model_copy(
        update={"report_id": uuid4(), "evidence_for_report_id": original.report_id}
    )

    result = invoke(
        "vera_incident_report", {"report": evidence.model_dump(mode="json")}
    )

    assert result["isError"] is (not linked)
    assert len(store.show(receipt["incident_id"])["evidence"]) == int(linked)
    assert store.status(owner)["incidents"][0]["latest_report_id"] == str(
        original.report_id
    )


@pytest.mark.parametrize(
    "direction", ["execution-to-evidence", "evidence-to-execution"]
)
def test_report_uuid_cannot_be_reused_across_execution_and_supplement(
    tmp_path, direction
):
    store, owner = registered(tmp_path)
    original = report()
    store.report(owner, original)
    extra_id = original.report_id if direction == "execution-to-evidence" else uuid4()
    evidence = original.model_copy(
        update={"report_id": extra_id, "evidence_for_report_id": original.report_id}
    )
    if direction == "evidence-to-execution":
        store.report(owner, evidence)
    candidate = (
        evidence
        if direction == "execution-to-evidence"
        else original.model_copy(update={"report_id": extra_id})
    )

    with pytest.raises(IncidentConflict):
        store.report(owner, candidate)
