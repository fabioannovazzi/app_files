"""Mechanical evidence coverage and counts, without inferring a root cause."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = [
    "capture_coverage",
    "diagnostic_followup",
    "incident_summary",
    "remedy_followup",
]


def diagnostic_followup(
    *,
    report_id: str,
    installation_id: str,
    revision: int,
    published_at: str,
    supplements: list[dict[str, Any]],
    events: list[dict[str, Any]],
    last_reporter_seen_at: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Expose exact receipts and the existing 15-minute collection deadline.

    These are mechanical delivery facts, not a diagnosis of host availability
    or a rule choosing a remedy. Only the agent decides the next recovery step.
    """
    replies = [
        item["report_id"]
        for item in supplements
        if item.get("evidence_for_report_id") == report_id
        and item.get("response_to_remedy_revision") == revision
    ]
    receipts = [
        item["recorded_at"]
        for item in events
        if item["installation_id"] == installation_id
        and item["report_id"] == report_id
        and item["remedy_revision"] == revision
        and item["kind"] == "remedy-received"
    ]
    received_at = min(receipts) if receipts else None
    published = datetime.fromisoformat(published_at)
    due = datetime.fromisoformat(received_at or published_at) + timedelta(minutes=15)
    return {
        "report_id": report_id,
        "installation_id": installation_id,
        "request_revision": revision,
        "published_at": published_at,
        "received_at": received_at,
        "response_report_ids": replies,
        "state": (
            "responded"
            if replies
            else (
                "received-awaiting-reply"
                if received_at
                else "published-awaiting-receipt"
            )
        ),
        "reply_due_at": due.isoformat(),
        "overdue": not replies and (now or datetime.now(timezone.utc)) >= due,
        "last_reporter_seen_at": last_reporter_seen_at,
        "reporter_seen_after_publication": (
            datetime.fromisoformat(last_reporter_seen_at) >= published
            if last_reporter_seen_at
            else None
        ),
    }


def remedy_followup(
    *,
    original: dict[str, Any],
    remedy: dict[str, Any],
    revision: int,
    published_at: str,
    supplements: list[dict[str, Any]],
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    reporter_contact: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Project exact delivery/progress facts for every actionable remedy.

    ID matching and a 15-minute attention cadence are mechanically verifiable.
    An overdue check is not a failed task, offline host or diagnosis. The agent
    owns the next action; only a matching original-task outcome proves recovery.
    """
    report_id = original["report_id"]
    owner = original["installation_id"]
    payload = original["payload"]
    result = diagnostic_followup(
        report_id=report_id,
        installation_id=owner,
        revision=revision,
        published_at=published_at,
        supplements=supplements,
        events=events,
        last_reporter_seen_at=(
            reporter_contact["last_seen"] if reporter_contact else None
        ),
        now=now,
    )
    matching_events = [
        event
        for event in events
        if event["installation_id"] == owner
        and event["report_id"] == report_id
        and event["remedy_revision"] == revision
    ]
    matching_outcomes = [
        row
        for row in outcomes
        if row["installation_id"] == owner
        and row["payload"].get("report_id") == report_id
        and row["payload"]["remedy_revision"] == revision
    ]
    latest_event = max(
        (event for event in matching_events if event["kind"] != "remedy-received"),
        key=lambda row: row["recorded_at"],
        default=None,
    )
    latest_outcome = max(
        matching_outcomes, key=lambda row: row["recorded_at"], default=None
    )
    outcome = latest_outcome["payload"] if latest_outcome else {}
    verified = (
        remedy["kind"] != "diagnostic-request"
        and outcome.get("status") == "recovered"
        and outcome.get("execution_succeeded") is True
        and outcome.get("original_task_verified") is True
        and (
            payload.get("operation_id") is None
            or (
                outcome.get("operation_id") == payload["operation_id"]
                and any(
                    event["kind"] == "retry-succeeded"
                    and event.get("operation_id") == payload["operation_id"]
                    for event in matching_events
                )
            )
        )
        and (
            payload.get("input_binding") is None
            or outcome.get("input_binding") == payload["input_binding"]
        )
    )
    if remedy["kind"] != "diagnostic-request":
        state = (
            "received-awaiting-action"
            if result["received_at"]
            else "published-awaiting-receipt"
        )
        if remedy["kind"] == "investigating":
            # A fallback investigation is not a published scoped remedy.
            state = "investigating"
            result.update(
                published_at=None,
                received_at=None,
                reporter_seen_after_publication=None,
            )
        transitions = {
            "remedy-applied": "applied-awaiting-original-task",
            "retry-started": "retry-in-progress",
            "retry-failed": "retry-failed",
            "retry-succeeded": "awaiting-original-task-verification",
            "capture-unavailable": "evidence-unavailable",
        }
        if latest_event:
            state = transitions.get(latest_event["kind"], state)
        if latest_outcome and (
            not latest_event
            or latest_outcome["recorded_at"] >= latest_event["recorded_at"]
        ):
            state = {
                "failed": "outcome-failed",
                "action-required": "action-required",
            }.get(outcome["status"], state)
        if verified:
            state = "verified-recovered"
        timestamps = [
            (
                original["created_at"]
                if remedy["kind"] == "investigating"
                else published_at
            )
        ]
        timestamps.extend(
            row["recorded_at"] for row in matching_events + matching_outcomes
        )
        due = max(datetime.fromisoformat(value) for value in timestamps) + timedelta(
            minutes=15
        )
        result.update(
            state=state,
            overdue=not verified and (now or datetime.now(timezone.utc)) >= due,
        )
        result.pop("reply_due_at")
        result["next_check_due_at"] = due.isoformat()
    else:
        result["next_check_due_at"] = result["reply_due_at"]
    progress_id = latest_event.get("event_id", "") if latest_event else ""
    outcome_id = outcome.get("outcome_id", "")
    response_ids = ",".join(result["response_report_ids"])
    result.update(
        remedy_revision=revision,
        remedy_kind=remedy["kind"],
        required_version=remedy.get("required_version"),
        original_reported_at=original["created_at"],
        original_version=payload["product_version"],
        workflow=payload["workflow"],
        host=payload["host"],
        platform=payload["platform"],
        operation_id=payload.get("operation_id"),
        input_binding_present=payload.get("input_binding") is not None,
        reporter_contact=reporter_contact,
        latest_progress=latest_event,
        latest_outcome=latest_outcome,
        original_task_verified=verified,
        attention_key=f"{owner}|{report_id}|{revision}|{result['state']}|{progress_id}|{outcome_id}|{response_ids}",
        deadline_basis="attention cadence; never a task execution timeout",
    )
    if payload.get("product", "vera") != "vera":
        result["product"] = payload["product"]
    return result


def capture_coverage(
    report: dict[str, Any],
    supplements: list[dict[str, Any]],
    created_at: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Expose missing collection as such; receipt acceptance is not diagnosis."""
    linked = [
        r for r in supplements if r.get("evidence_for_report_id") == report["report_id"]
    ]
    state = report.get("capture_state", "legacy")
    received = state == "complete" or bool(linked)
    # A delivered supplement is not proof that its own capture/review finished.
    complete = any(
        item.get("capture_state") == "complete"
        and item.get("measurements", {}).get("diagnostic_review_pending") is not True
        for item in (report, *linked)
    )
    review_pending = not complete and any(
        item.get("measurements", {}).get("diagnostic_review_pending") is True
        for item in (report, *linked)
    )
    due = datetime.fromisoformat(created_at) + timedelta(minutes=15)
    return {
        "state": (
            "review-pending" if review_pending else "received" if received else state
        ),
        "technical_evidence_received": received,
        "capture_complete": complete,
        "review_pending": review_pending,
        "capture_overdue": not complete and (now or datetime.now(timezone.utc)) >= due,
        "capture_due_at": due.isoformat(),
        "supplement_count": len(linked),
        "next_step": (
            "review-and-supplement-retained-evidence"
            if review_pending
            else (
                "diagnose-evidence"
                if complete
                else "collect-missing-technical-evidence"
            )
        ),
    }


def incident_summary(
    reports: list[dict[str, Any]],
    devices: dict[str, str],
    coverage: list[dict[str, Any]],
    app_installations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Count proven identifiers; an unlinked installation is not a physical PC."""
    installations = {row["installation_id"] for row in reports}
    linked = {
        devices[identifier] for identifier in installations if identifier in devices
    }
    apps = app_installations or {}
    return {
        "report_count": len(reports),
        "reporting_installations": len(installations),
        "reporting_instances": len(installations),
        "linked_app_installations": len(
            {apps[identifier] for identifier in installations if identifier in apps}
        ),
        "app_unlinked_instances": len(installations - apps.keys()),
        "app_linkage_complete": installations <= apps.keys(),
        "linked_host_devices": len(linked),
        "unlinked_installations": len(installations - devices.keys()),
        "host_linkage_complete": installations <= devices.keys(),
        "evidence_received": sum(
            row["technical_evidence_received"] for row in coverage
        ),
        "incomplete_capture": sum(not row["capture_complete"] for row in coverage),
        "review_pending": sum(row["review_pending"] for row in coverage),
        "overdue_capture": sum(row["capture_overdue"] for row in coverage),
        "reported_versions": sorted(
            {row["payload"]["product_version"] for row in reports}
        ),
        "coverage_basis": "received reports only; reporter instances may be task-local; app and host counts require native proof",
    }
