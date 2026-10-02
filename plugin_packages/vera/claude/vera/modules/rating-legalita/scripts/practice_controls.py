"""Check recorded pilot prerequisites, event dates and measured review time.

Fixed checks provide reproducible date arithmetic and evidence integrity only.
Professionals determine reportability, legal bases and suitable retention rules.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

from core_rating import event_deadline

__all__ = ["practice_summary"]


def _evidence(case: dict, source_root: Path, identifiers: list[str]) -> None:
    evidence = {row["evidence_id"]: row for row in case["evidence"]}
    for identifier in identifiers:
        if identifier not in evidence:
            raise ValueError("Practice record cites unknown evidence")
        row = evidence[identifier]
        path = (source_root / row["uri"]).resolve()
        if Path(row["uri"]).is_absolute() or not path.is_relative_to(
            source_root.resolve()
        ):
            raise ValueError("Practice evidence must remain inside the input folder")
        if (
            row["read_status"] != "read"
            or row["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError("Practice record requires reviewed, unchanged evidence")


def practice_summary(case: dict, source_root: Path, previous: dict | None) -> dict:
    """Summarize explicit reviews without granting legal or transmission approval."""
    practice = case["practice"]
    mandate, privacy = practice["mandate"], practice["data_governance"]
    real = not case["synthetic"] and bool(
        case["client"] or case["subjects"] or case["events"] or case["evidence"]
    )
    if real and (mandate is None or privacy is None):
        raise ValueError(
            "Real pilot requires reviewed mandate and data governance before evidence processing"
        )
    for record in (mandate, privacy):
        if record is None:
            continue
        if record["reviewed_on"] > case["as_of"]:
            raise ValueError("Practice review is in the future")
        if real and record["review_kind"] != "professional":
            raise ValueError("Real pilot requires professional practice reviews")
        _evidence(case, source_root, record["evidence_ids"])
    if privacy is not None and privacy["next_review_on"] < case["as_of"]:
        raise ValueError("Data retention and access review is overdue")

    if previous:
        old = previous["practice"]
        for key in ("event_reviews", "review_sessions"):
            if practice[key][: len(old[key])] != old[key]:
                raise ValueError("Earlier practice log entries are immutable")
        old_events = {row["event_id"]: row for row in previous["events"]}
        current_events = {row["event_id"]: row for row in case["events"]}
        if any(current_events.get(key) != value for key, value in old_events.items()):
            raise ValueError(
                "Earlier event facts are immutable; add a correction event"
            )

    events = {row["event_id"]: row for row in case["events"]}
    reviews: dict[str, dict] = {}
    for row in practice["event_reviews"]:
        if row["event_id"] not in events:
            raise ValueError("Event review cites unknown event")
        if row["reviewed_on"] > case["as_of"] or (
            real and row["review_kind"] != "professional"
        ):
            raise ValueError(
                "Event review must be current and professionally qualified"
            )
        _evidence(case, source_root, row["evidence_ids"])
        if row["notice_sent_on"]:
            if row["notice_sent_on"] > case["as_of"] or not row["notice_receipt_id"]:
                raise ValueError("Recorded notice requires a dated receipt")
            _evidence(case, source_root, [row["notice_receipt_id"]])
        elif row["notice_receipt_id"]:
            raise ValueError("Notice receipt requires the actual transmission date")
        reviews[row["event_id"]] = row

    calendar, blockers = [], []
    for identifier, event in events.items():
        row = reviews.get(identifier)
        due, state = None, "da_qualificare"
        if (
            event["learned_on"]
            and event["occurred_on"]
            and event["learned_on"] < event["occurred_on"]
        ):
            raise ValueError("Event knowledge cannot precede occurrence")
        if any(
            event[key] and event[key] > case["as_of"]
            for key in ("occurred_on", "learned_on")
        ):
            raise ValueError("Recorded event cannot be in the future")
        if row and row["basis"] == "not_reportable":
            state = "non_soggetto_secondo_revisione"
        elif row and event["occurred_on"]:
            due = event_deadline(date.fromisoformat(event["occurred_on"])).isoformat()
            if row["notice_sent_on"]:
                if row["notice_sent_on"] < event["occurred_on"]:
                    raise ValueError("Notice cannot precede the event")
                state = (
                    "comunicato"
                    if row["notice_sent_on"] <= due
                    else "comunicato_tardivamente"
                )
            else:
                state = (
                    "scaduto"
                    if case["as_of"] > due
                    else "scade_oggi" if case["as_of"] == due else "aperto"
                )
        if state in {
            "da_qualificare",
            "scaduto",
            "scade_oggi",
            "comunicato_tardivamente",
        }:
            blockers.append(f"Evento {identifier}: {state}; revisione urgente")
        calendar.append(
            {
                "event_id": identifier,
                "occurred_on": event["occurred_on"],
                "learned_on": event["learned_on"],
                "basis": row["basis"] if row else None,
                "deadline": due,
                "owner": row["owner"] if row else None,
                "status": state,
            }
        )

    totals: dict[str, float] = {}
    intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    identifiers = set()
    for row in practice["review_sessions"]:
        if row["session_id"] in identifiers:
            raise ValueError("Duplicate review session")
        identifiers.add(row["session_id"])
        start, end = datetime.fromisoformat(row["started_at"]), datetime.fromisoformat(
            row["ended_at"]
        )
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or end <= start
            or end.date().isoformat() > case["as_of"]
        ):
            raise ValueError(
                "Review interval requires ordered, dated timezone-aware timestamps"
            )
        active = (end - start).total_seconds() / 60 - row["break_minutes"]
        if active < 0:
            raise ValueError("Breaks exceed the review interval")
        for old_start, old_end in intervals.get(row["reviewer"], []):
            if start < old_end and end > old_start:
                raise ValueError("Review intervals overlap for the same professional")
        intervals.setdefault(row["reviewer"], []).append((start, end))
        totals[row["stage"]] = totals.get(row["stage"], 0) + active
    return {
        "pilot_prerequisites_recorded": mandate is not None and privacy is not None,
        "events": calendar,
        "blockers": blockers,
        "review_minutes": round(sum(totals.values()), 2) if totals else None,
        "minutes_by_stage": {key: round(value, 2) for key, value in totals.items()},
        "measured_sessions": len(identifiers),
    }
