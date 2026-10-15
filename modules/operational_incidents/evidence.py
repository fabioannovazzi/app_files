"""Mechanical evidence coverage and counts, without inferring a root cause."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

__all__ = ["capture_coverage", "incident_summary"]


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
