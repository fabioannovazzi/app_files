"""Reviewed tests close administratively without hiding new customer evidence."""

from __future__ import annotations

from uuid import uuid4

import pytest

from modules.operational_incidents.store import IncidentConflict
from scripts.summarize_incident_monitor import evidence_hash
from tests.modules.operational_incidents.test_incidents import (
    credentials,
    registered,
    report,
)


def close_reviewed(store, incident_id):
    return store.close_test(
        incident_id,
        expected_evidence_sha256=evidence_hash(store.show(incident_id)),
        note="Exact retained CI failure matches this report.",
        evidence_refs=["https://github.com/example/repo/actions/runs/123"],
    )


def test_test_closure_preserves_evidence_without_recovered_outcome(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    before = store.show(receipt["incident_id"])

    result = close_reviewed(store, receipt["incident_id"])

    saved = store.show(receipt["incident_id"])
    assert result["status"] == saved["status"] == "closed-test"
    assert saved["reports"] == before["reports"]
    assert saved["outcomes"] == []
    assert saved["test_closures"][0]["note"].startswith("Exact retained CI")
    assert store.queue() == []
    assert store.registry()["unresolved_installations"] == 0
    assert store.status(owner)["incidents"][0]["status"] == "closed-test"


def test_new_customer_report_in_same_group_reopens_closed_test(tmp_path):
    store, owner = registered(tmp_path)
    first = store.report(owner, report())
    close_reviewed(store, first["incident_id"])
    customer = credentials()
    store.register(customer)

    second = store.report(customer, report())

    assert first["incident_id"] == second["incident_id"]
    assert store.queue()[0]["status"] == "open"
    assert store.registry()["unresolved_installations"] == 1
    assert store.show(first["incident_id"])["test_closures"]


def test_new_supplement_reopens_closed_test_for_review(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    close_reviewed(store, receipt["incident_id"])
    supplement = original.model_copy(
        update={"report_id": uuid4(), "evidence_for_report_id": original.report_id}
    )

    store.report(owner, supplement)

    assert store.queue()[0]["status"] == "open"
    assert store.registry()["unresolved_installations"] == 1


def test_test_closure_rejects_unreviewed_report_added_since_snapshot(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    reviewed = evidence_hash(store.show(receipt["incident_id"]))
    store.report(owner, report())

    with pytest.raises(IncidentConflict, match="evidence changed"):
        store.close_test(
            receipt["incident_id"],
            expected_evidence_sha256=reviewed,
            note="Reviewed old test only",
            evidence_refs=["CI123"],
        )

    assert store.queue()[0]["status"] == "open"


def test_second_review_preserves_first_closure_audit(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    close_reviewed(store, receipt["incident_id"])
    first = store.show(receipt["incident_id"])["test_closures"][0]
    store.report(owner, report())

    close_reviewed(store, receipt["incident_id"])

    retained = store.show(receipt["incident_id"])
    assert len(retained["test_closures"]) == 2
    assert retained["test_closures"][0] == first
    assert retained["outcomes"] == []
