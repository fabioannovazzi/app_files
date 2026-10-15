"""Targeted agent conversations, immutable replies and original-task recovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from modules.operational_incidents.contracts import Outcome, Remedy, Report
from modules.operational_incidents.store import IncidentConflict, IncidentNotFound
from tests.modules.operational_incidents.test_incidents import (
    credentials,
    registered,
    report,
)


def request_for(report_id) -> Remedy:
    return Remedy(
        target_report_id=report_id,
        kind="diagnostic-request",
        summary="Verifica tecnica automatica",
        evidence="The original report lacks its retained technical cause.",
        instructions="Review the retained technical error using existing tools.",
        requested_evidence=["retained-technical-error"],
        expected_outcome="A reviewed technical reply for this original report.",
    )


def reply_to(original: Report, revision: int) -> Report:
    return Report.model_validate(
        {
            **original.model_dump(mode="json"),
            "report_id": str(uuid4()),
            "evidence_for_report_id": str(original.report_id),
            "response_to_remedy_revision": revision,
            "capture_state": "complete",
            "diagnostics": [
                {
                    "component": "verified-helper",
                    "stage": original.stage,
                    "error_type": "UnsupportedMode",
                    "error_code": "unsupported-calculation-mode",
                    "message": "The installed helper rejected its calculation mode.",
                    "evidence_source": "technical-log",
                }
            ],
        }
    )


def test_request_reply_is_scoped_and_does_not_close_original_task(tmp_path):
    store, owner = registered(tmp_path)
    other = credentials()
    store.register(other)
    original = report()
    receipt = store.report(owner, original)
    store.report(other, report())
    published = store.remedy(receipt["incident_id"], request_for(original.report_id))

    before = store.status(owner)["incidents"][0]
    assert before["diagnostic_exchange"]["state"] == "awaiting-vera"
    assert store.status(other)["incidents"][0]["remedy"]["kind"] == "investigating"
    reply = reply_to(original, published["revision"])
    store.report(owner, reply)

    after = store.status(owner)["incidents"][0]
    assert after["diagnostic_exchange"] == {
        "request_revision": published["revision"],
        "state": "responded",
        "response_report_ids": [str(reply.report_id)],
    }
    assert store.show(receipt["incident_id"])["status"] == "open"


def test_identical_remedy_does_not_create_another_revision_after_other_target(tmp_path):
    store, owner = registered(tmp_path)
    original = store.report(owner, report())
    remedy = request_for(original["report_id"])
    published = store.remedy(original["incident_id"], remedy)
    other = credentials()
    store.register(other)
    second = store.report(other, report())
    store.remedy(second["incident_id"], request_for(second["report_id"]))
    current_revision = store.show(original["incident_id"])["revision"]

    retry = store.remedy(
        original["incident_id"], remedy, expected_revision=current_revision
    )

    assert retry["deduplicated"] is True
    assert retry["revision"] == published["revision"]
    assert store.show(original["incident_id"])["revision"] == current_revision


def test_publication_rejects_diagnosis_based_on_a_stale_revision(tmp_path):
    store, owner = registered(tmp_path)
    original = store.report(owner, report())
    store.remedy(original["incident_id"], request_for(original["report_id"]))

    with pytest.raises(IncidentConflict, match="changed since diagnosis"):
        store.remedy(
            original["incident_id"],
            request_for(original["report_id"]),
            expected_revision=1,
        )


@pytest.mark.parametrize("revision", [1, 99])
def test_reply_rejects_a_revision_that_is_not_its_diagnostic_request(
    tmp_path, revision
):
    store, owner = registered(tmp_path)
    original = report()
    store.report(owner, original)

    with pytest.raises(IncidentConflict, match="does not match"):
        store.report(owner, reply_to(original, revision))


def test_reply_cannot_use_another_installations_request(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    published = store.remedy(receipt["incident_id"], request_for(original.report_id))
    other = credentials()
    store.register(other)

    with pytest.raises(IncidentNotFound, match="outside"):
        store.report(other, reply_to(original, published["revision"]))


def test_delayed_reply_is_retained_without_answering_a_new_request(tmp_path):
    store, owner = registered(tmp_path)
    original = report()
    receipt = store.report(owner, original)
    first = store.remedy(receipt["incident_id"], request_for(original.report_id))
    revised = request_for(original.report_id).model_copy(
        update={"requested_evidence": ["worker-runtime"]}
    )
    store.remedy(receipt["incident_id"], revised)
    reply = reply_to(original, first["revision"])

    assert store.report(owner, reply)["recorded"] is True
    assert store.report(owner, reply)["deduplicated"] is True
    assert (
        store.status(owner)["incidents"][0]["diagnostic_exchange"]["state"]
        == "awaiting-vera"
    )


def test_diagnostic_request_cannot_be_marked_recovered(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    published = store.remedy(receipt["incident_id"], request_for(receipt["report_id"]))

    with pytest.raises(IncidentConflict, match="diagnostic exchange"):
        store.outcome(
            owner,
            Outcome(
                outcome_id=uuid4(),
                report_id=receipt["report_id"],
                incident_id=receipt["incident_id"],
                remedy_revision=published["revision"],
                status="recovered",
                execution_succeeded=True,
                original_task_verified=True,
            ),
        )


@pytest.mark.parametrize(
    "update",
    [
        {"requested_evidence": []},
        {"instructions": None},
        {"requested_evidence": ["client-documents"]},
        {"command": "execute arbitrary repair"},
        {"kind": "resume"},
    ],
)
def test_agent_request_schema_rejects_unsupported_or_incomplete_requests(update):
    with pytest.raises(ValidationError):
        Remedy.model_validate(
            {**request_for(uuid4()).model_dump(mode="json"), **update}
        )


def test_diagnostic_reply_requires_original_report_binding():
    with pytest.raises(ValidationError, match="supplement its original"):
        Report.model_validate(
            {**report().model_dump(mode="json"), "response_to_remedy_revision": 2}
        )


def test_resume_requires_diagnosed_instructions():
    with pytest.raises(ValidationError, match="diagnosed instructions"):
        Remedy(
            kind="resume",
            summary="Resume",
            evidence="Diagnosis",
            expected_outcome="Success",
        )


def test_operator_cli_publishes_stdin_json_with_exact_revision(tmp_path):
    store, owner = registered(tmp_path)
    receipt = store.report(owner, report())
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[3] / "scripts/manage_incidents.py"),
        "--sqlite-path",
        str(tmp_path / "incidents.sqlite3"),
        "remedy",
        receipt["incident_id"],
        "--expected-revision",
        "1",
        "--input",
        "-",
    ]

    result = subprocess.run(
        command,
        input=request_for(receipt["report_id"]).model_dump_json(),
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(result.stdout)["revision"] == 2
    assert store.show(receipt["incident_id"])["remedy"]["kind"] == "diagnostic-request"
