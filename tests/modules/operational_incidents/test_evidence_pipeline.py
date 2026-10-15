"""Evidence coverage, proven host counts and original-episode recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.operational_incidents.contracts import (
    Credentials,
    DeviceCredentials,
    Outcome,
    RecoveryEvent,
    Remedy,
    ReporterStatus,
)
from modules.operational_incidents.evidence import capture_coverage
from modules.operational_incidents.store import IncidentConflict, IncidentNotFound
from tests.modules.operational_incidents.test_incidents import registered, report


def test_observed_reporter_upgrade_does_not_rewrite_old_failure(tmp_path):
    from modules.operational_incidents.api import _dispatch

    store, owner = registered(tmp_path)
    original = report()
    store.report(owner, original)
    observed = ReporterStatus(
        session_id=uuid4(),
        protocol=2,
        product_version="0.1.999",
        host="codex",
        platform="macos",
        runtime_version="3.13.4",
    )

    _dispatch(
        store,
        "status",
        {
            "credentials": owner.model_dump(mode="json"),
            "client_status": observed.model_dump(mode="json"),
        },
    )

    installation = store.installation(str(owner.installation_id))
    assert installation["reporter_sessions"][0]["product_version"] == "0.1.999"
    assert installation["reporter_sessions"][0]["protocol"] == 2
    assert (
        installation["incidents"][0]["reports"][0]["product_version"]
        == original.product_version
    )


def test_observed_reporter_requires_matching_installation_capability(tmp_path):
    store, owner = registered(tmp_path)
    status = ReporterStatus(
        session_id=uuid4(),
        protocol=2,
        product_version="0.1.999",
        host="codex",
        platform="macos",
    )
    forged = owner.model_copy(update={"installation_key": "x" * 32})

    with pytest.raises(IncidentNotFound):
        store.observe_reporter(forged, status)

    assert store.installation(str(owner.installation_id))["reporter_sessions"] == []


def test_missing_capture_becomes_overdue_without_continuously_changing_evidence():
    original = report().model_dump(mode="json")
    before = capture_coverage(
        original,
        [],
        "2026-01-01T00:00:00+00:00",
        now=datetime(2026, 1, 1, 0, 14, tzinfo=timezone.utc),
    )
    overdue = capture_coverage(
        original,
        [],
        "2026-01-01T00:00:00+00:00",
        now=datetime(2026, 1, 1, 0, 16, tzinfo=timezone.utc),
    )
    unchanged = capture_coverage(
        original,
        [],
        "2026-01-01T00:00:00+00:00",
        now=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert before["capture_overdue"] is False
    assert overdue["capture_overdue"] is True
    assert overdue == unchanged


def test_legacy_exit_report_is_accepted_but_visible_as_incomplete(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())

    record = store.show(receipt["incident_id"])

    assert record["reporting_summary"]["incomplete_capture"] == 1
    assert record["reporting_summary"]["unlinked_installations"] == 1
    assert record["reporting_summary"]["host_linkage_complete"] is False
    assert record["report_records"][0]["capture"]["state"] == "legacy"
    assert record["outcomes"] == []


def test_registry_distinguishes_attempts_installations_and_unlinked_hosts(tmp_path):
    store, owner = registered(tmp_path)
    store.report(owner, report())
    store.report(owner, report())

    registry = store.registry()

    assert registry["reports_received"] == 2
    assert registry["reporting_installations"] == 1
    assert registry["unresolved_linked_host_devices"] == 0
    assert registry["unresolved_unlinked_installations"] == 1


def test_structured_receipt_keeps_incomplete_host_review_visible():
    original = report().model_dump(mode="json")
    original.update(
        capture_state="complete", measurements={"diagnostic_review_pending": True}
    )

    capture = capture_coverage(
        original,
        [],
        "2026-01-01T00:00:00+00:00",
        now=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
    )

    assert capture["technical_evidence_received"] is True
    assert capture["capture_complete"] is False
    assert capture["review_pending"] is True
    assert capture["capture_overdue"] is True


def test_technical_supplement_completes_capture_without_closing_original(tmp_path):
    store, owner = registered(tmp_path)
    original = report().model_copy(update={"capture_state": "pending"})
    receipt = store.report(owner, original)
    store.report(
        owner,
        original.model_copy(
            update={"report_id": uuid4(), "evidence_for_report_id": original.report_id}
        ),
    )

    record = store.show(receipt["incident_id"])

    assert record["reporting_summary"]["evidence_received"] == 1
    assert record["reporting_summary"]["report_count"] == 1
    assert record["status"] == "open"


def test_two_app_installations_on_proven_host_count_as_one_host(tmp_path):
    store, first = registered(tmp_path)
    second = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    device = DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex)
    store.register(first, device)
    store.register(second, device)
    receipt = store.report(first, report())
    store.report(second, report())

    summary = store.show(receipt["incident_id"])["reporting_summary"]

    assert summary["reporting_installations"] == 2
    assert summary["linked_host_devices"] == 1
    assert summary["host_linkage_complete"] is True


def test_foreign_host_capability_cannot_link_an_installation(tmp_path):
    store, first = registered(tmp_path)
    device = DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex)
    store.register(first, device)
    forged = device.model_copy(update={"device_key": uuid4().hex})

    with pytest.raises(IncidentNotFound, match="Host capability"):
        store.register(first, forged)


def test_installation_cannot_silently_move_between_host_identities(tmp_path):
    store, first = registered(tmp_path)
    store.register(first, DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex))

    with pytest.raises(IncidentConflict, match="another host"):
        store.register(
            first, DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex)
        )


def test_status_read_records_remedy_receipt_once_without_marking_applied(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    store.remedy(
        receipt["incident_id"],
        Remedy(
            kind="user-action",
            target_report_id=receipt["report_id"],
            summary="Correct the original invocation",
            evidence="Missing required option observed",
            instructions="Resume with the original engagement context",
            expected_outcome="Original operation succeeds",
        ),
    )

    store.status(owner)
    store.status(owner)
    record = store.show(receipt["incident_id"])

    assert [event["kind"] for event in record["recovery_events"]] == ["remedy-received"]
    assert record["status"] == "open"


@pytest.mark.parametrize("kind", ["retry-started", "retry-succeeded", "remedy-applied"])
def test_progress_cannot_close_original_operation(tmp_path, kind):
    store, owner = registered(tmp_path)
    original = report().model_copy(update={"operation_id": uuid4()})
    receipt = store.report(owner, original)

    store.progress(
        owner,
        RecoveryEvent(
            event_id=uuid4(),
            incident_id=receipt["incident_id"],
            report_id=original.report_id,
            remedy_revision=1,
            kind=kind,
            operation_id=original.operation_id,
        ),
    )

    assert store.show(receipt["incident_id"])["status"] == "open"


@pytest.mark.parametrize("mismatch", ["operation", "inputs", "original-task"])
def test_recovery_requires_original_operation_inputs_and_host_verification(
    tmp_path, mismatch
):
    store, owner = registered(tmp_path)
    original = report().model_copy(
        update={"operation_id": uuid4(), "input_binding": "a" * 64}
    )
    receipt = store.report(owner, original)
    outcome = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt["incident_id"],
        report_id=original.report_id,
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=mismatch != "original-task",
        operation_id=uuid4() if mismatch == "operation" else original.operation_id,
        input_binding="b" * 64 if mismatch == "inputs" else original.input_binding,
    )

    with pytest.raises(IncidentConflict, match="original operation and inputs"):
        store.outcome(owner, outcome)


def test_matching_original_task_outcome_closes_only_its_installation(tmp_path):
    store, owner = registered(tmp_path)
    other = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(other)
    original = report().model_copy(
        update={"operation_id": uuid4(), "input_binding": "a" * 64}
    )
    receipt = store.report(owner, original)
    store.report(other, report())
    store.progress(
        owner,
        RecoveryEvent(
            event_id=uuid4(),
            incident_id=receipt["incident_id"],
            report_id=original.report_id,
            remedy_revision=1,
            kind="retry-succeeded",
            operation_id=original.operation_id,
        ),
    )

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
            operation_id=original.operation_id,
            input_binding=original.input_binding,
        ),
    )

    assert store.status(owner)["incidents"][0]["status"] == "recovered"
    assert store.status(other)["incidents"][0]["status"] == "open"


def test_another_installation_cannot_write_progress_for_original(tmp_path):
    store, owner = registered(tmp_path)
    other = Credentials(installation_id=uuid4(), installation_key=uuid4().hex)
    store.register(other)
    receipt = store.report(owner, report())

    with pytest.raises(IncidentNotFound):
        store.progress(
            other,
            RecoveryEvent(
                event_id=uuid4(),
                incident_id=receipt["incident_id"],
                report_id=receipt["report_id"],
                remedy_revision=1,
                kind="retry-started",
            ),
        )
