"""Unreceived updates are actionable blockers, not proof of recovery."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from modules.operational_incidents.contracts import (
    DeviceCredentials,
    Outcome,
    Remedy,
    ReporterStatus,
)
from modules.operational_incidents.evidence import remedy_followup
from modules.operational_incidents.reporting import (
    AlertReview,
    followup_hash,
    render_alert,
)
from tests.modules.operational_incidents.test_incidents import (
    credentials,
    registered,
    report,
)

PUBLISHED = "2026-10-17T08:00:00+00:00"
NOW = datetime(2026, 10, 17, 8, 30, tzinfo=timezone.utc)


def followup(*, events=(), outcomes=(), contact=None, **changes):
    original = {
        "report_id": "original",
        "installation_id": "owner",
        "created_at": "2026-10-15T08:00:00+00:00",
        "payload": {
            "product_version": "0.1.393",
            "workflow": "studio-archive",
            "host": "cowork",
            "platform": "macos",
            **changes,
        },
    }
    return remedy_followup(
        original=original,
        remedy={"kind": "update", "required_version": "0.1.396"},
        revision=3,
        published_at=PUBLISHED,
        supplements=[],
        events=list(events),
        outcomes=list(outcomes),
        reporter_contact=contact,
        now=NOW,
    )


def event(kind="remedy-received", **changes):
    return {
        "installation_id": "owner",
        "report_id": "original",
        "remedy_revision": 3,
        "kind": kind,
        "recorded_at": "2026-10-17T08:25:00+00:00",
        **changes,
    }


def outcome(**changes):
    return {
        "installation_id": "owner",
        "recorded_at": "2026-10-17T08:26:00+00:00",
        "payload": {
            "outcome_id": "outcome",
            "report_id": "original",
            "remedy_revision": 3,
            "status": "recovered",
            "execution_succeeded": True,
            "original_task_verified": True,
            **changes,
        },
    }


def update_for(original):
    return Remedy(
        target_report_id=original.report_id,
        kind="update",
        required_version="0.1.396",
        summary="Capture fix",
        evidence="Real helper error reproduced",
        instructions="Update once and retry original task",
        expected_outcome="Same original operation succeeds",
    )


def test_unreceived_update_retains_original_version_and_has_an_attention_deadline():
    result = followup()

    assert result["state"] == "published-awaiting-receipt"
    assert result["original_version"] == "0.1.393"
    assert result["required_version"] == "0.1.396"
    assert result["next_check_due_at"] == "2026-10-17T08:15:00+00:00"
    assert result["overdue"] is True
    assert result["original_task_verified"] is False


def test_contact_without_receipt_does_not_prove_delivery_or_installed_upgrade():
    contact = {"last_seen": "2026-10-17T08:20:00+00:00", "product_version": "0.1.393"}

    result = followup(contact=contact)

    assert result["reporter_seen_after_publication"] is True
    assert result["received_at"] is None
    assert result["state"] == "published-awaiting-receipt"
    assert result["reporter_contact"]["product_version"] == "0.1.393"


@pytest.mark.parametrize(
    "change",
    [{"installation_id": "other"}, {"report_id": "other"}, {"remedy_revision": 2}],
)
def test_other_owner_report_or_revision_cannot_receive_or_advance_update(change):
    result = followup(events=[event("retry-succeeded", **change)])

    assert result["state"] == "published-awaiting-receipt"
    assert result["latest_progress"] is None


@pytest.mark.parametrize(
    "kind,state",
    [
        ("remedy-received", "received-awaiting-action"),
        ("remedy-applied", "applied-awaiting-original-task"),
        ("retry-started", "retry-in-progress"),
        ("retry-failed", "retry-failed"),
        ("retry-succeeded", "awaiting-original-task-verification"),
        ("capture-unavailable", "evidence-unavailable"),
    ],
)
def test_actual_progress_is_visible_without_claiming_original_task_recovery(
    kind, state
):
    result = followup(events=[event(kind)])

    assert result["state"] == state
    assert result["original_task_verified"] is False
    assert result["next_check_due_at"] == "2026-10-17T08:40:00+00:00"
    assert result["overdue"] is False


def test_late_receipt_does_not_hide_observed_failed_retry():
    result = followup(events=[event("retry-failed", recorded_at=PUBLISHED), event()])

    assert result["state"] == "retry-failed"
    assert result["received_at"] == "2026-10-17T08:25:00+00:00"


@pytest.mark.parametrize(
    "status,state",
    [("failed", "outcome-failed"), ("action-required", "action-required")],
)
def test_original_failed_or_blocked_outcome_stays_actionable(status, state):
    result = followup(outcomes=[outcome(status=status)])

    assert result["state"] == state
    assert result["original_task_verified"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"original_task_verified": False},
        {"execution_succeeded": False},
        {"report_id": "other"},
        {"remedy_revision": 2},
        {"input_binding": "other"},
    ],
)
def test_incomplete_or_different_original_outcome_cannot_certify_recovery(changes):
    result = followup(outcomes=[outcome(**changes)], input_binding="binding")

    assert result["original_task_verified"] is False


def test_known_original_operation_needs_its_actual_retry_and_matching_binding():
    result = followup(
        events=[event("retry-succeeded", operation_id="operation")],
        outcomes=[outcome(operation_id="operation", input_binding="binding")],
        operation_id="operation",
        input_binding="binding",
    )

    assert result["state"] == "verified-recovered"
    assert result["original_task_verified"] is True
    assert result["overdue"] is False


def test_known_operation_without_matching_retry_does_not_close_from_outcome_alone():
    result = followup(
        events=[event("retry-succeeded", operation_id="other")],
        outcomes=[outcome(operation_id="operation")],
        operation_id="operation",
    )

    assert result["original_task_verified"] is False


def test_unchanged_wait_deadline_does_not_change_attention_event_identity():
    first = followup()
    later = followup(contact={"last_seen": "2026-10-17T08:20:00+00:00"})

    assert first["attention_key"] == later["attention_key"]


def test_operator_show_tracks_all_actionable_kinds_without_fabricating_receipt(
    tmp_path,
):
    store, owner = registered(tmp_path)
    original = report()
    saved = store.report(owner, original)
    store.remedy(saved["incident_id"], update_for(original))

    actual = store.show(saved["incident_id"])

    assert actual["remedy_followups"][0]["remedy_kind"] == "update"
    assert actual["remedy_followups"][0]["state"] == "published-awaiting-receipt"
    assert actual["recovery_events"] == []
    assert actual["diagnostic_requests"] == []


def test_exact_app_and_reporter_observation_are_separate_from_original_failure(
    tmp_path,
):
    store, owner = registered(tmp_path)
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    linked = store.register(owner, device)
    original = report()
    saved = store.report(owner, original)
    store.remedy(saved["incident_id"], update_for(original))
    store.observe_reporter(
        owner,
        ReporterStatus(
            session_id=uuid4(),
            protocol=3,
            product_version="0.1.999",
            host="cowork",
            platform="macos",
        ),
    )

    actual = store.show(saved["incident_id"])["remedy_followups"][0]

    assert actual["device_id"] == str(device.device_id)
    assert actual["app_link"]["app_installation_id"] == linked["app_installation_id"]
    assert actual["original_version"] == original.product_version
    assert actual["reporter_contact"]["product_version"] == "0.1.999"
    assert actual["received_at"] is None


def test_grouped_incident_keeps_each_original_owners_scoped_update_and_receipt(
    tmp_path,
):
    store, first = registered(tmp_path)
    second = credentials()
    store.register(second)
    one, two = report(), report()
    saved = store.report(first, one)
    store.report(second, two)
    one_rev = store.remedy(saved["incident_id"], update_for(one))["revision"]
    two_rev = store.remedy(saved["incident_id"], update_for(two))["revision"]
    store.status(first)

    actual = {
        r["report_id"]: r for r in store.show(saved["incident_id"])["remedy_followups"]
    }

    assert actual[str(one.report_id)]["remedy_revision"] == one_rev
    assert actual[str(one.report_id)]["state"] == "received-awaiting-action"
    assert actual[str(two.report_id)]["remedy_revision"] == two_rev
    assert actual[str(two.report_id)]["state"] == "published-awaiting-receipt"


def test_verified_host_closure_remains_visible_in_operator_followup(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    saved = store.report(owner, original)
    revision = store.remedy(saved["incident_id"], update_for(original))["revision"]
    store.outcome(
        owner,
        Outcome(
            outcome_id=uuid4(),
            incident_id=saved["incident_id"],
            report_id=original.report_id,
            remedy_revision=revision,
            status="recovered",
            execution_succeeded=True,
            original_task_verified=True,
        ),
    )

    actual = store.show(saved["incident_id"])

    assert actual["status"] == "recovered"
    assert actual["remedy_followups"][0]["state"] == "verified-recovered"


def alert_case(tmp_path):
    store, owner = registered(tmp_path)
    original = report().model_copy(
        update={
            "host": "cowork",
            "platform": "macos",
            "product_version": "0.1.393",
            "workflow": "studio-archive",
        }
    )
    device = DeviceCredentials(
        device_id=uuid4(), device_key=uuid4().hex, native_app="cowork"
    )
    store.register(owner, device)
    saved = store.report(owner, original)
    revision = store.remedy(saved["incident_id"], update_for(original))["revision"]
    actual = store.show(saved["incident_id"])
    row = actual["remedy_followups"][0]
    review = AlertReview(
        incident_id=saved["incident_id"],
        report_id=original.report_id,
        remedy_revision=revision,
        followup_sha256=followup_hash(row),
        observed="Aggiornamento pubblicato, ricevuta assente.",
        inferred="La pubblicazione non stabilisce la comunicazione.",
        unknown="Causa originale e recupero.",
        blocker="Nessuna ricevuta del reporter originale.",
        next_action={
            "action_id": "inspect-original-session-contact",
            "owner": "monitor",
            "instruction": "Verificare il collegamento della sessione originale.",
            "reason": "Il rimedio non risulta ricevuto.",
            "evidence_refs": [row["attention_key"]],
        },
        next_check_at="2030-01-01T08:00:00+00:00",
    )
    labels = {
        str(device.device_id): {
            "label": "Il tuo Mac",
            "verified_at": PUBLISHED,
            "evidence_ref": "inspected-native-profile",
        }
    }
    return actual, review, labels


@pytest.mark.parametrize("product", ["clara", "lucia"])
def test_alert_rejects_recovery_action_owned_by_another_product(tmp_path, product):
    incident, review, labels = alert_case(tmp_path)
    row = incident["remedy_followups"][0]
    row["product"] = product
    review = review.model_copy(
        update={
            "followup_sha256": followup_hash(row),
            "next_action": review.next_action.model_copy(update={"owner": "vera"}),
        }
    )

    with pytest.raises(ValueError, match="another product"):
        render_alert(incident, review, device_labels=labels, now=NOW)


def test_rendered_alert_names_verified_mac_app_original_version_blocker_and_owner(
    tmp_path,
):
    actual, review, labels = alert_case(tmp_path)

    result = render_alert(actual, review, labels, now=NOW)

    assert "Il tuo Mac" in result["html"]
    assert "Claude Cowork" in result["html"]
    assert "Vera 0.1.393" in result["html"]
    assert "versione proposta 0.1.396" in result["html"]
    assert "ricevuta assente" in result["html"]
    assert "Agente di monitoraggio" in result["html"]
    assert "Chiusura" not in result["html"]
    assert "setup refresh had errors" not in result["html"]
    assert result["original_task_verified"] is False


def test_unknown_device_or_unverified_alias_never_becomes_fabios_mac(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    label = next(iter(labels.values()))
    label.pop("evidence_ref")

    result = render_alert(actual, review, labels, now=NOW)

    assert "Il tuo Mac" not in result["html"]
    assert "Computer " in result["html"]


def test_unlinked_machine_and_app_remain_explicitly_unknown(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    row = actual["remedy_followups"][0]
    row.update(device_id=None, app_link=None)
    review = review.model_copy(update={"followup_sha256": followup_hash(row)})

    result = render_alert(actual, review, labels, now=NOW)

    assert "Computer non identificato" in result["html"]
    assert "collegamento non verificato" in result["html"]


@pytest.mark.parametrize("change", ["identity", "receipt", "revision", "case"])
def test_stale_or_other_episode_review_cannot_render_an_alert(tmp_path, change):
    actual, review, labels = alert_case(tmp_path)
    if change == "identity":
        actual["remedy_followups"][0]["device_id"] = str(uuid4())
    elif change == "receipt":
        actual["remedy_followups"][0]["received_at"] = PUBLISHED
    elif change == "revision":
        review = review.model_copy(update={"remedy_revision": 99})
    else:
        review = review.model_copy(update={"incident_id": uuid4()})

    with pytest.raises(ValueError):
        render_alert(actual, review, labels, now=NOW)


def test_unreceived_update_cannot_assign_next_action_to_uncontacted_vera(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    review.next_action.owner = "vera"

    with pytest.raises(ValueError, match="unreceived or overdue"):
        render_alert(actual, review, labels, now=NOW)


def test_due_time_alone_does_not_create_duplicate_alert_identity(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    later = review.model_copy(
        update={"next_check_at": datetime(2030, 1, 2, 8, tzinfo=timezone.utc)}
    )

    assert (
        render_alert(actual, review, labels, now=NOW)["event_key"]
        == render_alert(actual, later, labels, now=NOW)["event_key"]
    )


def test_reporter_contact_version_is_not_asserted_as_current_installed_version(
    tmp_path,
):
    actual, review, labels = alert_case(tmp_path)
    row = actual["remedy_followups"][0]
    row["reporter_contact"] = {"last_seen": PUBLISHED, "product_version": "0.1.999"}
    review = review.model_copy(update={"followup_sha256": followup_hash(row)})

    result = render_alert(actual, review, labels, now=NOW)

    assert "Vera 0.1.999 osservata dal reporter originale" in result["html"]
    assert "Vera 0.1.393" in result["html"]


def test_review_text_is_scrubbed_and_html_escaped(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    review = AlertReview.model_validate(
        {**review.model_dump(), "blocker": "<b>errore</b> password=secret_value"}
    )

    result = render_alert(actual, review, labels, now=NOW)

    assert "&lt;b&gt;errore&lt;/b&gt;" in result["html"]
    assert "secret_value" not in result["html"]


@pytest.mark.parametrize("field", ["blocker", "unknown", "next_action"])
def test_review_requires_blocker_unknowns_and_accountable_next_action(tmp_path, field):
    _, review, _ = alert_case(tmp_path)
    payload = review.model_dump()
    payload.pop(field)

    with pytest.raises(ValidationError):
        AlertReview.model_validate(payload)


def test_render_rejects_past_next_check(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    review = review.model_copy(update={"next_check_at": NOW})

    with pytest.raises(ValueError, match="future"):
        render_alert(actual, review, labels, now=NOW)


def test_naive_next_check_is_rejected(tmp_path):
    _, review, _ = alert_case(tmp_path)
    payload = review.model_dump()
    payload["next_check_at"] = "2030-01-01T08:00:00"

    with pytest.raises(ValidationError, match="timezone"):
        AlertReview.model_validate(payload)


def test_alert_cli_inspects_and_renders_without_mutating_evidence_or_ledger(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    incident_path = tmp_path / "incident.json"
    review_path = tmp_path / "review.json"
    ledger_path = tmp_path / "ledger.json"
    output = tmp_path / "alert.json"
    incident_path.write_text(json.dumps(actual))
    review_path.write_text(review.model_dump_json())
    ledger_path.write_text(json.dumps({"device_labels": labels}))
    script = Path(__file__).resolve().parents[3] / "scripts/render_incident_alert.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--incident",
            str(incident_path),
            "--review",
            str(review_path),
            "--ledger",
            str(ledger_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Il tuo Mac" in json.loads(output.read_text())["html"]
    assert json.loads(incident_path.read_text()) == actual
    assert json.loads(ledger_path.read_text()) == {"device_labels": labels}


def test_alert_cli_inspection_returns_hash_for_agent_review(tmp_path):
    actual, _, _ = alert_case(tmp_path)
    path = tmp_path / "incident.json"
    path.write_text(json.dumps(actual))
    script = Path(__file__).resolve().parents[3] / "scripts/render_incident_alert.py"

    result = subprocess.run(
        [sys.executable, str(script), "--incident", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["followup_sha256"] == followup_hash(
        actual["remedy_followups"][0]
    )


def test_equivalent_action_wording_does_not_create_duplicate_alert_identity(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    later = review.model_copy(deep=True)
    later.next_action.instruction = "Controllare il collegamento della stessa sessione."

    assert (
        render_alert(actual, review, labels, now=NOW)["event_key"]
        == render_alert(actual, later, labels, now=NOW)["event_key"]
    )


def test_new_failed_retry_event_is_distinct_from_unchanged_failed_wait():
    first = followup(events=[event("retry-failed", event_id="attempt-one")])
    second = followup(events=[event("retry-failed", event_id="attempt-two")])

    assert first["attention_key"] != second["attention_key"]


def test_receipted_current_vera_action_can_be_reported_without_claiming_recovery(
    tmp_path,
):
    actual, review, labels = alert_case(tmp_path)
    row = actual["remedy_followups"][0]
    row.update(received_at=PUBLISHED, overdue=False, state="received-awaiting-action")
    review = review.model_copy(update={"followup_sha256": followup_hash(row)})
    review.next_action.owner = "vera"

    result = render_alert(actual, review, labels, now=NOW)

    assert result["next_action_owner"] == "vera"
    assert result["original_task_verified"] is False


def test_overdue_received_remedy_requires_monitored_or_human_followup(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    row = actual["remedy_followups"][0]
    row.update(received_at=PUBLISHED, overdue=True, state="received-awaiting-action")
    review = review.model_copy(update={"followup_sha256": followup_hash(row)})
    review.next_action.owner = "vera"

    with pytest.raises(ValueError, match="overdue"):
        render_alert(actual, review, labels, now=NOW)


def test_next_check_outside_existing_monitoring_window_is_rejected(tmp_path):
    _, review, _ = alert_case(tmp_path)
    payload = review.model_dump()
    payload["next_check_at"] = "2030-01-01T02:00:00+00:00"

    with pytest.raises(ValidationError, match="operating window"):
        AlertReview.model_validate(payload)


def test_first_incident_can_be_reported_before_any_remedy_is_assigned(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    saved = store.report(owner, original)

    actual = store.show(saved["incident_id"])

    row = actual["remedy_followups"][0]
    assert row["state"] == "investigating"
    assert row["published_at"] is None
    assert row["received_at"] is None
    assert row["reporter_seen_after_publication"] is None
    assert row["original_task_verified"] is False
    assert actual["recovery_events"] == []


def test_new_unassigned_owner_does_not_inherit_another_reports_publication(tmp_path):
    store, first = registered(tmp_path)
    second = credentials()
    store.register(second)
    one, two = report(), report()
    saved = store.report(first, one)
    store.remedy(saved["incident_id"], update_for(one))
    store.report(second, two)

    row = next(
        r
        for r in store.show(saved["incident_id"])["remedy_followups"]
        if r["report_id"] == str(two.report_id)
    )

    assert row["state"] == "investigating"
    assert row["published_at"] is None
    assert row["received_at"] is None


def test_investigating_incident_has_an_actionable_alert_without_a_host_remedy(tmp_path):
    actual, review, labels = alert_case(tmp_path)
    row = actual["remedy_followups"][0]
    row.update(
        state="investigating",
        remedy_kind="investigating",
        required_version=None,
        published_at=None,
    )
    review = review.model_copy(update={"followup_sha256": followup_hash(row)})

    rendered = render_alert(actual, review, labels, now=NOW)

    assert "in diagnosi; nessun rimedio assegnato" in rendered["html"]
    assert "Agente di monitoraggio" in rendered["html"]
    assert "versione proposta" not in rendered["html"]
