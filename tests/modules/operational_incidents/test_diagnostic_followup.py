"""Published requests, actual receipt and replies are separate evidence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from modules.operational_incidents.evidence import diagnostic_followup
from tests.modules.operational_incidents.test_agent_exchange import (
    reply_to,
    request_for,
)
from tests.modules.operational_incidents.test_incidents import (
    credentials,
    registered,
    report,
)

PUBLISHED = "2026-10-17T08:00:00+00:00"
NOW = datetime(2026, 10, 17, 8, 30, tzinfo=timezone.utc)


def followup(*, events=(), supplements=(), seen=None):
    return diagnostic_followup(
        report_id="original",
        installation_id="owner",
        revision=2,
        published_at=PUBLISHED,
        events=list(events),
        supplements=list(supplements),
        last_reporter_seen_at=seen,
        now=NOW,
    )


def receipt(**changes):
    return {
        "installation_id": "owner",
        "report_id": "original",
        "remedy_revision": 2,
        "kind": "remedy-received",
        "recorded_at": "2026-10-17T08:25:00+00:00",
        **changes,
    }


def test_published_request_without_receipt_is_overdue_not_received():
    result = followup(seen="2026-10-16T22:53:00+00:00")

    assert result["state"] == "published-awaiting-receipt"
    assert result["received_at"] is None
    assert result["overdue"] is True
    assert result["reply_due_at"] == "2026-10-17T08:15:00+00:00"
    assert result["reporter_seen_after_publication"] is False


def test_missing_contact_is_unknown_and_does_not_assert_host_offline():
    result = followup()

    assert result["reporter_seen_after_publication"] is None
    assert result["last_reporter_seen_at"] is None
    assert result["state"] == "published-awaiting-receipt"


def test_recent_contact_alone_does_not_prove_request_receipt():
    result = followup(seen="2026-10-17T08:20:00+00:00")

    assert result["reporter_seen_after_publication"] is True
    assert result["received_at"] is None
    assert result["state"] == "published-awaiting-receipt"


def test_actual_receipt_starts_the_reply_deadline_from_receipt_time():
    result = followup(events=[receipt()])

    assert result["state"] == "received-awaiting-reply"
    assert result["received_at"] == "2026-10-17T08:25:00+00:00"
    assert result["reply_due_at"] == "2026-10-17T08:40:00+00:00"
    assert result["overdue"] is False


def test_received_request_without_reply_becomes_overdue():
    result = followup(events=[receipt(recorded_at=PUBLISHED)])

    assert result["state"] == "received-awaiting-reply"
    assert result["overdue"] is True


@pytest.mark.parametrize(
    "wrong",
    [dict(installation_id="other"), dict(report_id="other"), dict(remedy_revision=1)],
)
def test_another_owner_report_or_revision_cannot_acknowledge_request(wrong):
    result = followup(events=[receipt(**wrong)])

    assert result["state"] == "published-awaiting-receipt"
    assert result["received_at"] is None


def test_only_exact_revision_reply_answers_request_without_claiming_recovery():
    reply = {
        "report_id": "reply",
        "evidence_for_report_id": "original",
        "response_to_remedy_revision": 2,
        "capture_state": "unavailable",
    }

    result = followup(supplements=[reply])

    assert result["state"] == "responded"
    assert result["response_report_ids"] == ["reply"]
    assert result["overdue"] is False
    assert "recovered" not in result.values()


@pytest.mark.parametrize(
    "wrong", [dict(evidence_for_report_id="other"), dict(response_to_remedy_revision=1)]
)
def test_unrelated_or_late_reply_does_not_clear_current_overdue_request(wrong):
    reply = {
        "report_id": "reply",
        "evidence_for_report_id": "original",
        "response_to_remedy_revision": 2,
        **wrong,
    }

    result = followup(supplements=[reply])

    assert result["state"] == "published-awaiting-receipt"
    assert result["overdue"] is True


def test_operator_show_is_read_only_and_does_not_acknowledge_request(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    stored = store.report(owner, original)
    store.remedy(stored["incident_id"], request_for(original.report_id))

    result = store.show(stored["incident_id"])

    assert result["diagnostic_requests"][0]["state"] == "published-awaiting-receipt"
    assert result["recovery_events"] == []


def test_operator_show_observes_actual_client_receipt(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    stored = store.report(owner, original)
    store.remedy(stored["incident_id"], request_for(original.report_id))
    store.status(owner)

    result = store.show(stored["incident_id"])

    assert result["diagnostic_requests"][0]["state"] == "received-awaiting-reply"
    assert result["diagnostic_requests"][0]["received_at"] is not None


def test_operator_view_retains_each_owners_applicable_request_revision(tmp_path):
    store, owner = registered(tmp_path)
    other = credentials()
    store.register(other)
    original = report()
    first = store.report(owner, original)
    second_report = report()
    store.report(other, second_report)
    one = store.remedy(first["incident_id"], request_for(original.report_id))
    two = store.remedy(first["incident_id"], request_for(second_report.report_id))
    store.status(owner)

    result = store.show(first["incident_id"])

    indexed = {item["report_id"]: item for item in result["diagnostic_requests"]}
    assert indexed[str(original.report_id)]["request_revision"] == one["revision"]
    assert indexed[str(original.report_id)]["state"] == "received-awaiting-reply"
    assert indexed[str(second_report.report_id)]["request_revision"] == two["revision"]
    assert (
        indexed[str(second_report.report_id)]["state"] == "published-awaiting-receipt"
    )


def test_operator_view_records_reply_without_closing_original(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    stored = store.report(owner, original)
    request = store.remedy(stored["incident_id"], request_for(original.report_id))
    reply = reply_to(original, request["revision"])
    store.report(owner, reply)

    result = store.show(stored["incident_id"])

    assert result["diagnostic_requests"][0]["state"] == "responded"
    assert result["diagnostic_requests"][0]["response_report_ids"] == [
        str(reply.report_id)
    ]
    assert result["status"] == "open"
