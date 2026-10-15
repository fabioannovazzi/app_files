"""Evidence coverage, proven host counts and original-episode recovery."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import UUID, uuid4

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
from modules.operational_incidents.store import (
    IncidentConflict,
    IncidentNotFound,
    IncidentStore,
)
from tests.modules.operational_incidents.test_incidents import registered, report


def test_historical_recorded_outcome_retries_without_rewriting_its_evidence(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    legacy = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt["incident_id"],
        report_id=original.report_id,
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
    )
    payload = legacy.model_dump(mode="json")
    for field in ("operation_id", "input_binding", "original_task_verified"):
        payload.pop(field)
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    # Seed an actual old-format committed recovery, not a newly allowed closure.
    with sqlite3.connect(tmp_path / "incidents.sqlite3") as connection:
        connection.execute(
            "INSERT INTO operational_outcomes VALUES (?,?,?,?,?)",
            (
                str(legacy.outcome_id),
                str(owner.installation_id),
                receipt["incident_id"],
                encoded,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "UPDATE operational_deliveries SET status='recovered' WHERE installation_id=? AND incident_id=?",
            (str(owner.installation_id), receipt["incident_id"]),
        )
        connection.execute(
            "UPDATE operational_incidents SET status='recovered' WHERE incident_id=?",
            (receipt["incident_id"],),
        )
    before = store.show(receipt["incident_id"])["outcomes"]

    repeated = store.outcome(owner, legacy)

    assert repeated["recorded"] is True
    assert repeated["outcome_id"] == str(legacy.outcome_id)
    assert store.show(receipt["incident_id"])["outcomes"] == before


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


@pytest.mark.parametrize("capture_state", ["legacy", "pending", "unavailable"])
def test_recovery_requires_original_task_verification_even_without_operation_id(
    tmp_path,
    capture_state,
):
    store, owner = registered(tmp_path)
    original = report().model_copy(update={"capture_state": capture_state})
    receipt = store.report(owner, original)
    readiness = Outcome(
        outcome_id=uuid4(),
        incident_id=receipt["incident_id"],
        report_id=original.report_id,
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
    )

    with pytest.raises(IncidentConflict, match="verification of the original task"):
        store.outcome(owner, readiness)

    assert store.show(receipt["incident_id"])["status"] == "open"
    store.outcome(owner, readiness.model_copy(update={"original_task_verified": True}))
    assert store.show(receipt["incident_id"])["status"] == "recovered"


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
    assert registry["reporting_instances"] == 1
    assert registry["linked_app_installations"] == 0
    assert registry["unresolved_app_unlinked_instances"] == 1


def test_fresh_cowork_reporters_share_one_native_app_without_duplicating_host(tmp_path):
    from tests.modules.operational_incidents.test_incidents import credentials

    store, first = registered(tmp_path)
    second, codex = credentials(), credentials()
    host = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    first_binding = store.register(first, host)
    store = IncidentStore(tmp_path / "incidents.sqlite3")
    second_binding = store.register(second, host)
    codex_binding = store.register(
        codex, host.model_copy(update={"native_app": "codex"})
    )
    original = store.report(first, report().model_copy(update={"host": "cowork"}))
    store.report(second, report().model_copy(update={"host": "cowork"}))
    store.report(codex, report())

    registry = store.registry()
    cowork = store.show(original["incident_id"])

    assert first_binding["app_installation_id"] == second_binding["app_installation_id"]
    assert first_binding["app_installation_id"] != codex_binding["app_installation_id"]
    assert registry["reporting_instances"] == 3
    assert registry["unresolved_linked_host_devices"] == 1
    assert registry["unresolved_linked_app_installations"] == 2
    assert registry["unresolved_app_unlinked_instances"] == 0
    assert cowork["reporting_summary"]["reporting_instances"] == 2
    assert cowork["reporting_summary"]["linked_app_installations"] == 1
    assert cowork["reporting_summary"]["app_linkage_complete"] is True
    assert cowork["report_records"][0]["app_link"]["native_app"] == "cowork"


def test_app_linkage_is_not_inferred_from_reported_app_name(tmp_path):
    store, owner = registered(tmp_path)
    store.register(owner, DeviceCredentials(device_id=uuid4(), device_key=uuid4().hex))
    receipt = store.report(owner, report().model_copy(update={"host": "cowork"}))

    shown = store.show(receipt["incident_id"])

    assert shown["reporting_summary"]["linked_host_devices"] == 1
    assert shown["reporting_summary"]["linked_app_installations"] == 0
    assert shown["reporting_summary"]["app_linkage_complete"] is False
    assert shown["report_records"][0]["app_link"] is None


def test_native_app_link_cannot_be_silently_reassigned(tmp_path):
    store, owner = registered(tmp_path)
    host = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="codex"
    )
    original = store.register(owner, host)

    with pytest.raises(IncidentConflict, match="another native app"):
        store.register(owner, host.model_copy(update={"native_app": "cowork"}))

    assert (
        store.installation(str(owner.installation_id))["app_link"][
            "app_installation_id"
        ]
        == original["app_installation_id"]
    )
    assert store.registry()["linked_app_installations"] == 1


def test_shared_native_app_link_does_not_grant_other_reporter_access(tmp_path):
    from tests.modules.operational_incidents.test_incidents import credentials

    store, first = registered(tmp_path)
    second = credentials()
    host = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    store.register(first, host)
    store.register(second, host)
    one, two = store.report(first, report()), store.report(second, report())
    foreign = Outcome(
        outcome_id=uuid4(),
        incident_id=two["incident_id"],
        report_id=two["report_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=True,
    )

    with pytest.raises(IncidentConflict, match="newer failure"):
        store.outcome(first, foreign)

    assert store.status(first)["incidents"][0]["latest_report_id"] == one["report_id"]
    assert str(two["report_id"]) not in json.dumps(store.status(first))
    assert store.status(second)["incidents"][0]["status"] == "open"


def test_app_history_scopes_reports_and_outcomes_in_a_shared_investigation(tmp_path):
    from tests.modules.operational_incidents.test_incidents import credentials

    store, one = registered(tmp_path)
    two, other_app = credentials(), credentials()
    host = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    binding = store.register(one, host)
    store.register(two, host)
    store.register(other_app, host.model_copy(update={"native_app": "codex"}))
    first, second, third = (
        store.report(one, report()),
        store.report(two, report()),
        store.report(other_app, report()),
    )
    supplement = report().model_copy(
        update={"evidence_for_report_id": UUID(first["report_id"])}
    )
    store.report(one, supplement)
    recovered = Outcome(
        outcome_id=uuid4(),
        incident_id=first["incident_id"],
        report_id=first["report_id"],
        remedy_revision=1,
        status="recovered",
        execution_succeeded=True,
        original_task_verified=True,
    )
    store.outcome(one, recovered)

    app = store.app_installation(binding["app_installation_id"])

    assert app["incident_ids"] == [first["incident_id"]]
    assert {row["report_id"] for row in app["reports"]} == {
        first["report_id"],
        second["report_id"],
    }
    assert third["report_id"] not in json.dumps(app)
    assert app["evidence"][0]["report_id"] == str(supplement.report_id)
    assert {row["status"] for row in app["deliveries"]} == {"open", "recovered"}
    assert app["outcomes"][0]["installation_id"] == str(one.installation_id)
    assert app["outcomes"][0]["payload"]["original_task_verified"] is True
    full = store.show(first["incident_id"])
    assert full["outcome_records"][0]["installation_id"] == str(one.installation_id)
    with pytest.raises(IncidentNotFound):
        store.app_installation(str(uuid4()))


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


@pytest.mark.parametrize(
    "mismatch, message",
    [
        ("operation", "original operation and inputs"),
        ("inputs", "original operation and inputs"),
        ("original-task", "original task"),
    ],
)
def test_recovery_requires_original_operation_inputs_and_host_verification(
    tmp_path, mismatch, message
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

    with pytest.raises(IncidentConflict, match=message):
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
