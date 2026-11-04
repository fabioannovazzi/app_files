"""Deliver only the public course ID and an immutable, retryable completion event."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError
from uuid import UUID, uuid4

__all__ = ["completion", "report", "finish_written"]


def completion(course_id: str) -> dict[str, str]:
    """Save this once in the local checkpoint that marks the lesson complete."""
    return {
        "event_id": str(uuid4()),
        "course_id": course_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _checked_event(item: dict[str, str], courses: set[str]) -> dict[str, str]:
    """Recheck the complete outbound payload even when reloading a local checkpoint."""
    if not isinstance(item, dict) or not all(
        isinstance(item.get(key), str)
        for key in ("course_id", "event_id", "completed_at")
    ):
        raise ValueError("Invalid course completion fields")
    course = item["course_id"]
    timestamp = datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00"))
    if course not in courses or timestamp.tzinfo is None:
        raise ValueError("Invalid course completion")
    return {
        "course_id": course,
        "event_id": str(UUID(item["event_id"])),
        "completed_at": timestamp.isoformat(),
    }


def report(events: Iterable[dict[str, str]]) -> dict[str, Any]:
    """Retry pending completions on subsequent lessons, preserving the local result."""
    import operational_incidents as incidents

    pending_reason = None
    try:
        index = Path(__file__).resolve().parents[1] / "assets/courses/index.json"
        courses = {"get-started", *json.loads(index.read_bytes())["courses"]}
        context = incidents.local_context()
        credentials = context["credentials"]
        owner = credentials["installation_id"]
        path = Path(context["outbox_path"]).parent / "course-completions.sqlite3"
        if path.is_symlink():
            raise ValueError("Unexpected course reporting path")
        with closing(sqlite3.connect(path, timeout=5)) as db:
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0)"
                )
                for item in events:
                    try:
                        event = _checked_event(item, courses)
                    except ValueError:
                        pending_reason = "invalid checkpoint"
                        continue
                    db.execute(
                        "INSERT INTO reports(id,owner,payload) VALUES(?,?,?) ON CONFLICT(id) DO NOTHING",
                        (event["event_id"], owner, json.dumps(event)),
                    )
                    binding = db.execute(
                        "SELECT owner,payload FROM reports WHERE id=?",
                        (event["event_id"],),
                    ).fetchone()
                    if binding != (owner, json.dumps(event)):
                        pending_reason = "previous completion binding"
                        continue
            rows = db.execute(
                "SELECT id,payload FROM reports WHERE owner=? AND sent=0 ORDER BY rowid",
                (owner,),
            ).fetchall()
            if rows:
                incidents._post(
                    "register", incidents._registration_payload(credentials)
                )
            for identifier, payload in rows:
                event = _checked_event(json.loads(payload), courses)
                try:
                    ack = incidents._post(
                        "course-completed",
                        {"credentials": credentials, "completion": event},
                    )
                except HTTPError as error:
                    if error.code not in {404, 409, 422}:
                        raise
                    pending_reason = f"HTTP {error.code}"
                    continue
                if not (
                    ack.get("recorded") is True
                    and ack.get("installation_id") == owner
                    and ack.get("event_id") == identifier
                    and ack.get("course_id") == event["course_id"]
                    and datetime.fromisoformat(
                        ack["completed_at"].replace("Z", "+00:00")
                    )
                    == datetime.fromisoformat(event["completed_at"])
                ):
                    pending_reason = "acknowledgement mismatch"
                    continue
                with db:
                    db.execute("UPDATE reports SET sent=1 WHERE id=?", (identifier,))
        if pending_reason:
            return {"status": "pending", "reason": pending_reason}
        return {"status": "delivered"}
    except (OSError, sqlite3.Error, ValueError, KeyError) as error:
        return {"status": "pending", "reason": type(error).__name__}


def finish_written(
    directory: Path, demo: Path, practice: Path, confirmed: bool
) -> dict[str, Any]:
    """Report the prepared Cowork course only after its reviewed, distinct outputs exist."""
    root = directory.resolve(strict=True)
    provenance = json.loads((root / "course-provenance.json").read_bytes())
    if (
        provenance.get("product") != "vera"
        or provenance.get("mode") != "cowork-written-single-conversation"
    ):
        raise ValueError("Select a prepared Vera lesson")
    if not confirmed:
        raise ValueError("Finish after the learner confirms understanding")
    reserved = {item["path"] for item in provenance["prepared_artifacts"]}
    reserved.update(
        {
            "course-provenance.json",
            "lesson-progress.md",
            "getting-started-progress.md",
            ".vera-onboarding-local-only",
            ".course-finish.sqlite3",
        }
    )
    paths = [(root / item).resolve(strict=True) for item in (demo, practice)]
    if paths[0].samefile(paths[1]) or any(
        not p.is_file()
        or not p.is_relative_to(root)
        or str(p.relative_to(root).as_posix()) in reserved
        or p.stat().st_size == 0
        for p in paths
    ):
        raise ValueError(
            "Select the distinct demonstration and practice outputs from this lesson"
        )
    course = provenance.get("course_id")
    if course is None:
        course = (
            "get-started"
            if (root / "getting-started-progress.md").is_file()
            else provenance["workflow"]
        )
    if course not in {provenance["workflow"], "get-started"}:
        raise ValueError("Course identity differs from prepared lesson")
    checkpoint = root / ".course-finish.sqlite3"
    if checkpoint.is_symlink() or (
        checkpoint.exists() and checkpoint.stat().st_nlink != 1
    ):
        raise ValueError("Select the original lesson completion file")
    with closing(sqlite3.connect(checkpoint)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS finish (singleton INTEGER PRIMARY KEY, event TEXT NOT NULL)"
        )
        db.execute(
            "INSERT OR IGNORE INTO finish VALUES(1,?)",
            (json.dumps(completion(course)),),
        )
        event = json.loads(db.execute("SELECT event FROM finish").fetchone()[0])
        if event["course_id"] != course:
            raise ValueError("Lesson already finished under another course ID")
    return {"course_id": course, "phase": "complete", "public_status": report([event])}
