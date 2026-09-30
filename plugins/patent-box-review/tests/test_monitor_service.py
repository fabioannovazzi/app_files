"""Default-off host coordination, source deltas and preserved private baselines."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from patent_box import monitor_service as service
from patent_box import source_acquisition as acquisition
from patent_box.contracts import ContractError
from patent_box.source_transport import PublicResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_source_acquisition import fetch_html, plan, review

NOW = datetime(2026, 9, 30, 10, tzinfo=timezone.utc)
OWNER = "Synthetic monitor owner"
ENTRY = "https://institution.example/document"


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition.time, "sleep", lambda _: None)
    root = tmp_path / "private-service"
    public = tmp_path / "public"
    index = tmp_path / "private-index.json"
    index.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cases": [
                    {
                        "case_id": "opaque-1",
                        "regime": "NEW",
                        "state": "APPROVED",
                        "period_start": "2025-01-01",
                        "period_end": "2025-12-31",
                        "rule_ids": ["RULE"],
                        "approved_hash": "1" * 64,
                    }
                ],
            }
        )
    )
    research = plan(ENTRY)
    service.configure(
        root,
        public_root=public,
        owner=OWNER,
        plan=research,
        private_case_index=index,
        interval_hours=24,
    )
    return {"root": root, "public": public, "index": index, "plan": research}


def completed(
    configured, *, at=NOW, body=b"<p>Original public rule</p>", extracted=None
):
    request = service.begin(
        configured["root"], configured["plan"], trigger="OPEN_CASE", at=at
    )
    scan = Path(request["scan"])
    receipt = acquisition.acquire(
        scan,
        scope_id="PUBLIC",
        url=ENTRY,
        kind="DOCUMENT",
        fetcher=(
            (lambda url, **kwargs: PublicResponse(url, "application/pdf", body))
            if extracted is not None
            else fetch_html(body)
        ),
    )
    if extracted is not None:
        text = configured["root"] / (request["job_id"] + ".txt")
        text.write_text(extracted)
        acquisition.attach_text(
            scan,
            receipt_id=receipt["receipt_id"],
            text_path=text,
            extractor="Synthetic host extraction v2",
        )
    acquisition.finish_scan(scan, review(receipt))
    outcome = service.finish(configured["root"], request["job_id"], at=at)
    return request, outcome


def activate(case, *, active=True, at=NOW):
    return service.record_schedule(
        case["root"],
        owner=OWNER,
        host_reference="synthetic-host-schedule",
        active=active,
        at=at,
    )


def test_monitor_starts_disabled_and_does_not_open_a_periodic_scan(configured):
    outcome = service.begin(
        configured["root"], configured["plan"], trigger="PERIODIC", at=NOW
    )
    assert outcome["status"] == "DISABLED"
    assert not configured["public"].exists()
    assert list((configured["root"] / "jobs").iterdir()) == []


def test_case_preflight_can_run_while_periodic_schedule_is_disabled(configured):
    request, outcome = completed(configured)
    assert request["trigger"] == "OPEN_CASE"
    assert outcome["status"] == "BASELINE_RECORDED"
    assert outcome["notification_required"] is True
    assert outcome["notification_delivered"] is False


def test_periodic_run_observes_configured_cadence(configured):
    completed(configured)
    activate(configured)
    result = service.begin(
        configured["root"],
        configured["plan"],
        trigger="PERIODIC",
        at=NOW + timedelta(hours=23),
    )
    assert result["status"] == "NOT_DUE"
    assert result["next_due"] == (NOW + timedelta(days=1)).isoformat()


def test_periodic_run_opens_once_when_due_and_reuses_pending_work(configured):
    activate(configured)
    first = service.begin(
        configured["root"], configured["plan"], trigger="PERIODIC", at=NOW
    )
    second = service.begin(
        configured["root"], configured["plan"], trigger="PERIODIC", at=NOW
    )
    assert second["pending_jobs"] == [first["job_id"]]
    assert len(list((configured["root"] / "jobs").iterdir())) == 1


def test_unchanged_complete_scan_is_persisted_without_requesting_a_notice(configured):
    completed(configured)
    request, outcome = completed(configured, at=NOW + timedelta(days=1))
    assert outcome["notification_required"] is False
    assert outcome["source_events"] == 0
    assert (configured["root"] / "jobs" / request["job_id"] / "outcome.json").is_file()


def test_changed_scan_builds_private_reopening_queue_without_modifying_case_index(
    configured,
):
    completed(configured)
    original_index = configured["index"].read_bytes()
    request, outcome = completed(
        configured, at=NOW + timedelta(days=1), body=b"<p>Changed public rule</p>"
    )
    queue = json.loads(
        (
            configured["root"] / "jobs" / request["job_id"] / "impact_queue.json"
        ).read_text()
    )
    assert outcome["notification_required"] is True
    assert outcome["affected_cases"] == 1
    assert queue["items"][0]["action"] == "PROPOSE_REOPEN"
    assert queue["items"][0]["previous_case_hash"] == "1" * 64
    assert configured["index"].read_bytes() == original_index
    assert not list(configured["public"].rglob("case_index.json"))


def test_changed_extraction_on_same_original_bytes_still_requests_review(configured):
    original_bytes = b"%PDF-1.7\nSynthetic opaque transport fixture\n%%EOF\n"
    completed(configured, body=original_bytes, extracted="Original host text")
    _, outcome = completed(
        configured,
        at=NOW + timedelta(days=1),
        body=original_bytes,
        extracted="Corrected host text from the same original",
    )
    assert outcome["notification_required"] is True
    assert outcome["source_events"] == 1
    assert outcome["affected_cases"] == 1


def test_partial_scan_retains_last_complete_baseline(configured):
    first, _ = completed(configured)
    request = service.begin(
        configured["root"],
        configured["plan"],
        trigger="CLOSE_CASE",
        at=NOW + timedelta(days=1),
    )
    acquisition.finish_scan(Path(request["scan"]), review())
    outcome = service.finish(
        configured["root"], request["job_id"], at=NOW + timedelta(days=1)
    )
    state = service.status(configured["root"], at=NOW + timedelta(days=1))
    assert outcome["status"] == "PARTIAL_SCAN"
    assert outcome["notification_required"] is True
    assert state["last_complete_scan"] == first["scan"]


def test_failed_host_attempt_is_visible_and_allows_a_manual_retry(configured):
    first, _ = completed(configured)
    request = service.begin(
        configured["root"],
        configured["plan"],
        trigger="CLOSE_CASE",
        at=NOW + timedelta(days=1),
    )
    outcome = service.fail(
        configured["root"],
        request["job_id"],
        reason="Host research unavailable",
        at=NOW + timedelta(days=1),
    )
    retry = service.begin(
        configured["root"],
        configured["plan"],
        trigger="MANUAL_RETRY",
        at=NOW + timedelta(days=1),
    )
    assert outcome["status"] == "HOST_RESEARCH_FAILED"
    assert outcome["notification_required"] is True
    assert retry["baseline_scan"] == first["scan"]
    assert retry["job_id"] != request["job_id"]


def test_monitor_finish_is_idempotent_for_exact_same_scan(configured):
    request, original = completed(configured)
    repeated = service.finish(
        configured["root"], request["job_id"], at=NOW + timedelta(minutes=1)
    )
    assert repeated == original


def test_paused_host_receipt_prevents_periodic_scans(configured):
    activate(configured)
    activate(configured, active=False, at=NOW + timedelta(minutes=1))
    outcome = service.begin(
        configured["root"],
        configured["plan"],
        trigger="PERIODIC",
        at=NOW + timedelta(days=1),
    )
    assert outcome["status"] == "DISABLED"


def test_monitor_rejects_unreviewed_scope_expansion(configured):
    changed = copy.deepcopy(configured["plan"])
    changed["scopes"][0]["allowed_hosts"].append("unreviewed.example")
    with pytest.raises(ContractError, match="Changed research scope"):
        service.begin(configured["root"], changed, trigger="OPEN_CASE", at=NOW)


def test_monitor_rejects_configuration_inside_public_source_storage(tmp_path):
    with pytest.raises(ContractError, match="separate absolute"):
        service.configure(
            tmp_path / "public" / "private",
            public_root=tmp_path / "public",
            owner=OWNER,
            plan=plan(ENTRY),
        )


def test_monitor_rejects_private_case_index_in_public_tree(tmp_path):
    with pytest.raises(ContractError, match="outside public"):
        service.configure(
            tmp_path / "private",
            public_root=tmp_path / "public",
            owner=OWNER,
            plan=plan(ENTRY),
            private_case_index=tmp_path / "public" / "cases.json",
        )


def test_monitor_detects_tampered_receipt(configured):
    request, _ = completed(configured)
    path = configured["root"] / "jobs" / request["job_id"] / "outcome.json"
    value = json.loads(path.read_text())
    value["notification_required"] = False
    path.write_text(json.dumps(value))
    with pytest.raises(ContractError, match="Monitor record changed"):
        service.status(configured["root"], at=NOW)


def test_monitor_rejects_empty_owner_and_invalid_cadence(tmp_path):
    with pytest.raises(ContractError, match="owner and a bounded interval"):
        service.configure(
            tmp_path / "private",
            public_root=tmp_path / "public",
            owner=" ",
            plan=plan(ENTRY),
            interval_hours=0,
        )


def test_same_timestamp_schedule_pause_is_ordered_after_activation(configured):
    activate(configured)
    activate(configured, active=False)
    assert service.status(configured["root"], at=NOW)["schedule_active"] is False


def test_same_timestamp_scan_completion_preserves_latest_baseline(configured):
    completed(configured)
    second, _ = completed(configured, body=b"<p>Second version</p>")
    assert (
        service.status(configured["root"], at=NOW)["last_complete_scan"]
        == second["scan"]
    )


def test_public_root_redirected_into_private_storage_is_rejected(configured):
    configured["public"].symlink_to(configured["root"], target_is_directory=True)
    with pytest.raises(ContractError, match="overlaps public"):
        service.begin(
            configured["root"], configured["plan"], trigger="OPEN_CASE", at=NOW
        )


def test_monitor_rejects_backdated_host_schedule_receipt(configured):
    activate(configured)
    with pytest.raises(ContractError, match="cannot precede"):
        activate(configured, active=False, at=NOW - timedelta(minutes=1))
