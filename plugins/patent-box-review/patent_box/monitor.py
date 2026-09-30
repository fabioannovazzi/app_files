"""Compare supplied source snapshots and prepare review queues. No scheduler."""

from __future__ import annotations

from typing import Any

from .contracts import ContractError, canonical_hash, indexed, validate

__all__ = ["compare_snapshots", "impact_queue"]


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    validate(before, "source-snapshot.schema.json")
    validate(after, "source-snapshot.schema.json")
    for snapshot in (before, after):
        for source in snapshot["sources"]:
            if source["fetch_status"] == "OK" and not source["content_sha256"]:
                raise ContractError(
                    "Successful source retrieval requires a content hash"
                )
            if (
                source["affected_from"]
                and source["affected_to"]
                and source["affected_from"] > source["affected_to"]
            ):
                raise ContractError("Invalid source applicability interval")
    old = indexed(before["sources"], "source_id")
    new = indexed(after["sources"], "source_id")
    events = []
    for sid in sorted(set(old) | set(new)):
        a, b = old.get(sid), new.get(sid)
        if b is None or b["fetch_status"] != "OK":
            kind = "SOURCE_UNAVAILABLE"
        elif a is None:
            kind = "NEW_CANDIDATE"
        elif a["fetch_status"] != "OK":
            kind = "SOURCE_RESTORED_REVIEW_REQUIRED"
        elif a["content_sha256"] != b["content_sha256"]:
            kind = "CONTENT_CHANGED_REVIEW_REQUIRED"
        elif {k: v for k, v in a.items() if k not in ("retrieved_at",)} != {
            k: v for k, v in b.items() if k not in ("retrieved_at",)
        }:
            kind = "METADATA_CHANGED_REVIEW_REQUIRED"
        else:
            continue
        # A candidate mapping cannot narrow the queue until a reviewer accepts it.
        candidates = [r for r in (a, b) if r]
        verified = [r for r in candidates if r["impact_reviewed"]]
        rule_ids = sorted({rid for row in verified for rid in row["rule_ids"]})
        unknown = not b or not b["impact_reviewed"] or not rule_ids
        event = {
            "source_id": sid,
            "kind": kind,
            "rule_ids": rule_ids,
            "mapping_unknown": unknown,
            "affected_from": b["affected_from"] if b and b["impact_reviewed"] else None,
            "affected_to": b["affected_to"] if b and b["impact_reviewed"] else None,
            "before_hash": a["content_sha256"] if a else None,
            "after_hash": b["content_sha256"] if b else None,
            "regime": b["regime"] if b else "UNKNOWN",
            "regime_reviewed": bool(b and b["impact_reviewed"]),
            "changes_active_rules": False,
        }
        event["event_id"] = canonical_hash(event)
        events.append(event)
    incomplete = after["coverage"] != "COMPLETE_DECLARED_SCOPE" or any(
        e["kind"] == "SOURCE_UNAVAILABLE" for e in events
    )
    return {
        "schema_version": "1.0",
        "before_hash": canonical_hash(before),
        "after_hash": canonical_hash(after),
        "coverage": "PARTIAL" if incomplete else after["coverage"],
        "events": events,
        "status": "PARTIAL_SCAN" if incomplete else "COMPARED_DECLARED_SCOPE",
        "not_exhaustive_legal_monitoring": True,
    }


def impact_queue(
    comparison: dict[str, Any], case_index: dict[str, Any]
) -> dict[str, Any]:
    validate(case_index, "case-index.schema.json")
    indexed(case_index["cases"], "case_id")
    queue = []
    for event in comparison["events"]:
        for case in case_index["cases"]:
            if (
                event["regime_reviewed"]
                and event["regime"] == "OLD"
                and case["regime"] == "NEW"
            ):
                continue
            if not event["mapping_unknown"] and not set(event["rule_ids"]) & set(
                case["rule_ids"]
            ):
                continue
            if event["affected_from"] and case["period_end"] < event["affected_from"]:
                continue
            if event["affected_to"] and case["period_start"] > event["affected_to"]:
                continue
            queue.append(
                {
                    "event_id": event["event_id"],
                    "case_id": case["case_id"],
                    "previous_case_hash": case["approved_hash"],
                    "action": (
                        "PROPOSE_REOPEN"
                        if case["state"] == "APPROVED"
                        else "REVIEW_OPEN_CASE"
                    ),
                    "reason": event["kind"],
                    "automatic_mutation": False,
                }
            )
    return {
        "schema_version": "1.0",
        "items": queue,
        "case_index_hash": canonical_hash(case_index),
    }
