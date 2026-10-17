"""Count open technical cases from complete evidence and explicit AI reviews.

Exact IDs and hashes make the arithmetic auditable. Semantic decisions about
fixtures and original-task recovery belong to the reviewing agent, never to
error keywords, operating systems, exit codes or free-text ledger dispositions.
This read-only projection does not close incidents or manufacture host outcomes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["evidence_hash", "payload_hash", "summarize", "main"]


def payload_hash(value: Any) -> str:
    """Hash a JSON payload using the incident ledger's canonical encoding."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def evidence_hash(incident: dict[str, Any]) -> str:
    """Pin all inspected evidence except derived wall-clock capture summaries."""
    evidence = copy.deepcopy(incident)
    evidence.pop("reporting_summary", None)
    # Receipt/reply payloads are already pinned below. Deadlines and reporter
    # heartbeats are derived monitoring facts, not new technical evidence.
    evidence.pop("diagnostic_requests", None)
    evidence.pop("remedy_followups", None)
    for record in evidence.get("report_records", []):
        # Derived from report/evidence payloads and the current clock; those
        # original payloads and reporting identities remain in this digest.
        record.pop("capture", None)
    return payload_hash(evidence)


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed = {row[key]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"Duplicate {key} in snapshot")
    return indexed


def summarize(snapshot: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Fail on partial reads; an absent or stale review leaves the case open."""
    queue = snapshot["queue"]
    limit = snapshot["queue_limit"]
    if not 1 <= limit <= 1000 or len(queue) >= limit:
        raise ValueError("Queue may be truncated; retain the last complete count")
    queued = _index(queue, "incident_id")
    inspected = _index(snapshot["incidents"], "incident_id")
    previous = set(ledger.get("last_monitor_check", {}).get("queue_ids", []))
    if not (set(queued) | previous) <= set(inspected):
        raise ValueError("Missing show evidence; retain the last complete count")
    for incident_id in previous - set(queued):
        if inspected[incident_id]["status"] != "recovered":
            raise ValueError("An unresolved incident disappeared; refresh the queue")

    groups: dict[str, list[str]] = {
        "effective_open": [],
        "controlled_fixture": [],
        "technical_recovery_pending_closure": [],
    }
    items = []
    reviews = ledger.get("monitor_reviews", {})
    for incident_id, queued_incident in queued.items():
        incident = inspected[incident_id]
        if incident["status"] == "recovered" or evidence_hash(
            queued_incident
        ) != evidence_hash(incident):
            raise ValueError("Queue changed during inspection; refresh the snapshot")
        reports = _index(incident["reports"], "report_id")
        report_hashes = {key: payload_hash(value) for key, value in reports.items()}
        digest = evidence_hash(incident)
        review = reviews.get(incident_id, {})
        category = "effective_open"
        matching = bool(
            report_hashes
            and review.get("report_hashes") == report_hashes
            and review.get("evidence_sha256") == digest
            and review.get("reviewed_at")
            and review.get("reason")
            and review.get("evidence_refs")
        )
        kind = review.get("kind")
        if matching and kind == "controlled_fixture":
            category = kind
        elif matching and kind == "technical_recovery_pending_closure":
            verification = review.get("verification", {})
            # This is a reviewed technical scope, not a protocol-level recovered
            # outcome. Keep administrative closure visible as remaining work.
            if (
                verification.get("original_task_verified") is True
                and verification.get("original_inputs_preserved") is True
                and verification.get("scope")
                and verification.get("result")
            ):
                category = kind
        groups[category].append(incident_id)
        items.append(
            {
                "incident_id": incident_id,
                "category": category,
                "registry_status": incident["status"],
                "evidence_sha256": digest,
                "report_hashes": report_hashes,
                "review_applied": category != "effective_open",
                "review_stale": bool(review) and not matching,
            }
        )
    counts = {f"{key}_incidents": len(value) for key, value in groups.items()}
    return {
        "raw_open_incidents": len(queued),
        **counts,
        "summary_it": (
            f"Problemi tecnici aperti: {counts['effective_open_incidents']}. "
            "Recuperi tecnici verificati in attesa di chiusura nel registro: "
            f"{counts['technical_recovery_pending_closure_incidents']}. "
            f"Prove controllate escluse: {counts['controlled_fixture_incidents']}."
        ),
        "basis": "distinct incident records, not reports, installations or machines",
        "items": items,
    }


def main() -> None:
    """Emit the count without writing to the registry or private ledgers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = summarize(
            json.loads(args.snapshot.read_text(encoding="utf-8")),
            json.loads(args.ledger.read_text(encoding="utf-8")),
        )
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Count unavailable: {error}\n")
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
