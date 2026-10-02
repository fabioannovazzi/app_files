"""Mechanical pilot and calendar checks; no real professional attestations."""

from __future__ import annotations

import copy

import pytest

from tests.plugins.test_rating_legalita_case import CASE, prepared_case


def pilot_records(case: dict) -> None:
    """Record artificial approvals against the explicit synthetic test evidence."""
    common = {
        "reviewer": "Synthetic reviewer",
        "reviewed_on": "2026-10-02",
        "review_kind": "professional",
        "evidence_ids": ["E1"],
    }
    case["practice"]["mandate"] = {
        **common,
        "representative_declarations": "Test representative owns declarations and signature",
        "studio_investigation": "Test studio reviews selected evidence and drafts",
        "excluded_activities": "No portal transmission or automatic monitoring",
        "event_reporting_owner": "Test company contact",
        "event_reporting_channel": "Agreed test channel",
    }
    case["practice"]["data_governance"] = {
        **common,
        "notice_status_and_delivery": "Synthetic notice and delivery review",
        "processing_legal_basis": "Synthetic reviewed basis, not legal advice",
        "judicial_data_authority": "Synthetic art. 10 qualification, not consent",
        "retention_rule": "Synthetic purpose-bound retention and deletion plan",
        "retention_owner": "Test controller",
        "model_processing_review": "Synthetic account and data-path review",
        "next_review_on": "2026-12-01",
        "access_roles": ["Test reviewer"],
    }


def event_case(tmp_path, occurred_on="2026-09-02", basis="art21_1_mandatory"):
    case = prepared_case(tmp_path)
    case["events"] = [
        {
            "event_id": "EVENT-1",
            "subject_id": "PERSON-1",
            "description": "Synthetic event",
            "occurred_on": occurred_on,
            "learned_on": "2026-10-01",
        }
    ]
    case["practice"]["event_reviews"] = [
        {
            "event_id": "EVENT-1",
            "basis": basis,
            "reason": "Synthetic qualification of applicability and dates",
            "owner": "Synthetic company contact",
            "notice_sent_on": None,
            "notice_receipt_id": None,
            "reviewer": "Test reviewer",
            "reviewed_on": "2026-10-02",
            "review_kind": "synthetic_assumption",
            "evidence_ids": ["E1"],
        }
    ]
    return case


def session(identifier="TIME-1", start="09:00", end="09:40", pauses=10):
    return {
        "session_id": identifier,
        "reviewer": "Reviewer A",
        "stage": "obstacles",
        "started_at": f"2026-10-02T{start}:00+02:00",
        "ended_at": f"2026-10-02T{end}:00+02:00",
        "break_minutes": pauses,
    }


@pytest.mark.parametrize("missing", ["mandate", "data_governance"])
def test_real_pilot_without_prerequisite_stops_before_evidence_read(tmp_path, missing):
    case = prepared_case(tmp_path)
    pilot_records(case)
    case["synthetic"] = False
    case["practice"][missing] = None
    (tmp_path / "evidence.txt").unlink()

    with pytest.raises(ValueError, match="Real pilot requires reviewed mandate"):
        CASE.assess_case(case, tmp_path)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("review_kind", "synthetic_assumption", "professional practice reviews"),
        ("reviewed_on", "2026-10-03", "future"),
        ("evidence_ids", ["unknown"], "unknown evidence"),
    ],
)
def test_invalid_pilot_record_rejected(tmp_path, field, value, error):
    case = prepared_case(tmp_path)
    pilot_records(case)
    case["synthetic"] = False
    case["practice"]["mandate"][field] = value

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(case, tmp_path)


def test_expired_retention_review_stops_processing(tmp_path):
    case = prepared_case(tmp_path)
    pilot_records(case)
    case["practice"]["data_governance"]["next_review_on"] = "2026-10-01"

    with pytest.raises(ValueError, match="review is overdue"):
        CASE.assess_case(case, tmp_path)


def test_pilot_evidence_changed_rejected(tmp_path):
    case = prepared_case(tmp_path)
    pilot_records(case)
    (tmp_path / "evidence.txt").write_text("Changed")

    with pytest.raises(ValueError, match="unchanged evidence"):
        CASE.assess_case(case, tmp_path)


@pytest.mark.parametrize(
    "occurred,state",
    [
        ("2026-09-01", "scaduto"),
        ("2026-09-02", "scade_oggi"),
        ("2026-09-03", "aperto"),
        (None, "da_qualificare"),
    ],
)
def test_calendar_uses_occurrence_not_knowledge_date(tmp_path, occurred, state):
    case = event_case(tmp_path, occurred)

    result = CASE.assess_case(case, tmp_path)["practice_summary"]

    assert result["events"][0]["status"] == state
    assert result["events"][0]["learned_on"] == "2026-10-01"


def test_unclassified_event_prevents_positive_readiness(tmp_path):
    case = event_case(tmp_path)
    case["practice"]["event_reviews"] = []

    result = CASE.assess_case(case, tmp_path)

    assert result["assessment"]["status"] == "incomplete"
    assert result["practice_summary"]["events"][0]["deadline"] is None


def test_professional_nonreportable_event_is_not_given_a_deadline(tmp_path):
    case = event_case(tmp_path, basis="not_reportable")

    result = CASE.assess_case(case, tmp_path)["practice_summary"]

    assert result["events"][0]["status"] == "non_soggetto_secondo_revisione"
    assert result["events"][0]["deadline"] is None


@pytest.mark.parametrize(
    "sent,state",
    [("2026-10-01", "comunicato"), ("2026-10-02", "comunicato_tardivamente")],
)
def test_external_notice_receipt_distinguishes_timely_and_late(tmp_path, sent, state):
    case = event_case(tmp_path, "2026-09-01", "art21_4_premium")
    case["practice"]["event_reviews"][0].update(
        notice_sent_on=sent, notice_receipt_id="E1"
    )

    result = CASE.assess_case(case, tmp_path)

    assert result["practice_summary"]["events"][0]["status"] == state
    assert result["assessment"]["submission_authorized"] is False
    assert result["case"]["external_actions"] == []


@pytest.mark.parametrize(
    "updates,error",
    [
        ({"event_id": "missing"}, "unknown event"),
        ({"notice_sent_on": "2026-10-01"}, "dated receipt"),
        ({"notice_receipt_id": "E1"}, "actual transmission date"),
        (
            {"notice_sent_on": "2026-08-01", "notice_receipt_id": "E1"},
            "precede the event",
        ),
        ({"reviewed_on": "2026-10-03"}, "professionally qualified"),
    ],
)
def test_invalid_event_review_rejected(tmp_path, updates, error):
    case = event_case(tmp_path)
    case["practice"]["event_reviews"][0].update(updates)

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(case, tmp_path)


def test_measured_review_time_excludes_pauses_and_is_rendered(tmp_path):
    case = prepared_case(tmp_path)
    case["practice"]["review_sessions"] = [session()]

    result = CASE.assess_case(case, tmp_path)

    assert result["practice_summary"]["review_minutes"] == 30
    assert result["practice_summary"]["minutes_by_stage"] == {"obstacles": 30}
    assert "Minuti attivi: 30" in CASE.render_dossier(result)


def test_unmeasured_time_is_unknown_not_zero(tmp_path):
    case = prepared_case(tmp_path)

    result = CASE.assess_case(case, tmp_path)

    assert result["practice_summary"]["review_minutes"] is None
    assert "non misurati" in CASE.render_dossier(result)


@pytest.mark.parametrize(
    "rows,error",
    [
        ([session(), session()], "Duplicate review"),
        ([session(), session("TIME-2", "09:30", "10:00")], "overlap"),
        ([session(pauses=41)], "Breaks exceed"),
        ([session(start="10:00", end="09:00")], "ordered"),
    ],
)
def test_review_time_does_not_double_count_or_accept_invalid_duration(
    tmp_path, rows, error
):
    case = prepared_case(tmp_path)
    case["practice"]["review_sessions"] = rows

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(case, tmp_path)


@pytest.mark.parametrize(
    "change,error",
    [
        ("time", "practice log entries"),
        ("event_review", "practice log entries"),
        ("event", "Earlier event facts"),
    ],
)
def test_continuation_retains_event_and_time_history(tmp_path, change, error):
    case = event_case(tmp_path)
    case["practice"]["review_sessions"] = [session()]
    previous = CASE.assess_case(case, tmp_path)
    updated = copy.deepcopy(case)
    if change == "time":
        updated["practice"]["review_sessions"][0]["break_minutes"] = 0
    elif change == "event_review":
        updated["practice"]["event_reviews"][0]["reason"] = "Changed"
    else:
        updated["events"][0]["occurred_on"] = "2026-09-01"

    with pytest.raises(ValueError, match=error):
        CASE.assess_case(updated, tmp_path, previous)
