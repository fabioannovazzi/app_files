"""Persistent commitments and external-operation receipts for studio work.

Codex interprets meaning and priorities. SQLite transactions, revision checks and
exact receipts are mechanical safeguards against lost updates and duplicate writes.
This service has no network credentials and never claims to execute a connector.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

__all__ = ["StudioWork", "storage_root", "main"]

KINDS = {"appointment", "task", "deadline", "follow_up", "protected_time"}
STATES = {"open", "waiting", "delegated", "done", "cancelled"}
FIELDS = {
    "title",
    "kind",
    "status",
    "client",
    "engagement",
    "owner",
    "due_date",
    "start_time",
    "end_time",
    "duration_minutes",
    "priority",
    "category",
    "notes",
    "source",
    "depends_on",
    "follow_up_date",
}
CALENDAR_FIELDS = {
    "title",
    "start_time",
    "end_time",
    "start_date",
    "end_date",
    "timezone_str",
    "color_id",
    "description",
    "location",
    "reminders",
    "transparency",
    "visibility",
    "attendees",
}


def storage_root() -> Path:
    """Keep the ledger out of volatile runtime/cache/version directories.

    Only trusted host/operator environment can override storage, never tool input.
    Do not silently fall back to temporary storage after permission failure.
    """
    configured = os.environ.get("VERA_STUDIO_WORK_DATA")
    if configured:
        return Path(configured).expanduser()
    host_data = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("PLUGIN_DATA")
    if host_data:
        return Path(host_data).expanduser() / "studio-work"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return base / "Mparanza" / "Vera" / "studio-work"
    return Path.home() / ".local/share/mparanza/vera/studio-work"


def encode(value: Any) -> str:
    """Canonicalize payloads to detect changed retries."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def text(value: Any, name: str) -> str:
    """Reject empty identities and unbounded text."""
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ValueError(f"Invalid {name}")
    return value


def instant(value: str) -> datetime:
    """Require explicit offsets; interpretation of spoken dates belongs to Codex."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Times require an explicit UTC offset")
    return parsed


def validate_item(item: dict[str, Any]) -> None:
    """Validate shape and exact references, never classify professional meaning."""
    if set(item) - FIELDS:
        raise ValueError("Unknown commitment fields")
    text(item.get("title"), "title")
    text(item.get("source"), "source reference or supplied instruction")
    if item.get("kind") not in KINDS or item.get("status", "open") not in STATES:
        raise ValueError("Invalid kind or status")
    for field in ("due_date", "follow_up_date"):
        if item.get(field):
            date.fromisoformat(item[field])
    if bool(item.get("start_time")) != bool(item.get("end_time")):
        raise ValueError("Supply both appointment boundaries")
    if item.get("start_time") and instant(item["end_time"]) <= instant(
        item["start_time"]
    ):
        raise ValueError("End must follow start")
    for field in ("duration_minutes", "priority"):
        if field in item and (type(item[field]) is not int or item[field] < 0):
            raise ValueError(f"Invalid {field}")
    if "depends_on" in item and (
        not isinstance(item["depends_on"], list)
        or any(not isinstance(x, str) for x in item["depends_on"])
    ):
        raise ValueError("Dependencies must be commitment IDs")


def validate_event(action: str, payload: dict[str, Any]) -> None:
    """Bound ordinary events; invitations and recurrence need separate workflows."""
    if set(payload) - CALENDAR_FIELDS:
        raise ValueError("Unsupported calendar field")
    if payload.get("attendees"):
        raise ValueError("Invitations are a separate explicit communication")
    if action == "delete":
        if payload:
            raise ValueError("Delete accepts no event changes")
        return
    text(payload.get("title"), "event title")
    timed = bool(payload.get("start_time") or payload.get("end_time"))
    all_day = bool(payload.get("start_date") or payload.get("end_date"))
    if timed == all_day:
        raise ValueError("Choose timed or all-day event boundaries")
    if timed:
        start, end = instant(payload["start_time"]), instant(payload["end_time"])
        ZoneInfo(payload["timezone_str"])
    else:
        start, end = date.fromisoformat(payload["start_date"]), date.fromisoformat(
            payload["end_date"]
        )
    if end <= start:
        raise ValueError("Event end must follow start; all-day end is exclusive")
    if "reminders" in payload:
        reminders = payload["reminders"]
        if (
            not isinstance(reminders, dict)
            or type(reminders.get("use_default")) is not bool
        ):
            raise ValueError("Invalid reminders")
        overrides = reminders.get("overrides", [])
        if not isinstance(overrides, list) or len(overrides) > 5:
            raise ValueError("Invalid reminder overrides")
        for reminder in overrides:
            if (
                reminder.get("method") not in {"popup", "email"}
                or type(reminder.get("minutes")) is not int
                or not 0 <= reminder["minutes"] <= 40320
            ):
                raise ValueError("Invalid reminder override")


class StudioWork:
    """One durable owner-local register, independent of plugin version/chat."""

    def __init__(self, root: Path) -> None:
        self.path = root / "studio-work.sqlite3"
        if any(p.is_symlink() for p in (root, *root.parents, self.path)):
            raise ValueError("Studio work storage must not use symlinks")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, item_id TEXT NOT NULL, state TEXT NOT NULL,
                body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
                body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (
                sequence INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
                action TEXT NOT NULL, body TEXT NOT NULL);
            """
        )
        self.path.chmod(0o600)

    def close(self) -> None:
        """Release the owned database connection."""
        self.db.close()

    def record(self, item_id: str) -> dict[str, Any]:
        """Read one exact current identity."""
        row = self.db.execute("SELECT * FROM records WHERE id=?", (item_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown commitment")
        return {"id": row["id"], "revision": row["revision"], **json.loads(row["body"])}

    def operation(self, operation_id: str) -> dict[str, Any]:
        """Read persisted intent before deciding whether a write is safe."""
        row = self.db.execute(
            "SELECT * FROM operations WHERE id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown operation")
        return {"id": row["id"], "state": row["state"], **json.loads(row["body"])}

    def audit(self, action: str, body: Any) -> None:
        """Retain local change evidence in the same transaction."""
        self.db.execute(
            "INSERT INTO history(timestamp,action,body) VALUES(?,?,?)",
            (datetime.now(timezone.utc).isoformat(), action, encode(body)),
        )

    def save(self, item: dict[str, Any], revision: int) -> dict[str, Any]:
        """Write a validated record with its next revision."""
        body = {
            key: value for key, value in item.items() if key not in {"id", "revision"}
        }
        now = datetime.now(timezone.utc).isoformat()
        previous = self.db.execute(
            "SELECT body FROM records WHERE id=?", (item["id"],)
        ).fetchone()
        prior = json.loads(previous["body"]) if previous else {}
        body["created_at"] = prior.get("created_at", now)
        body["updated_at"] = now
        if body["status"] == "done":
            body["completed_at"] = prior.get("completed_at", now)
        else:
            body.pop("completed_at", None)
        validate_item({key: value for key, value in body.items() if key in FIELDS})
        pending = list(body.get("depends_on", []))
        visited = set()
        while pending:
            dependency = pending.pop()
            if dependency == item["id"]:
                raise ValueError("Dependencies cannot form a cycle")
            if dependency not in visited:
                visited.add(dependency)
                pending.extend(self.record(dependency).get("depends_on", []))
        self.db.execute(
            "INSERT OR REPLACE INTO records VALUES(?,?,?)",
            (item["id"], revision, encode(body)),
        )
        return self.record(item["id"])

    def settings(self) -> dict[str, Any]:
        """Return configured preferences without inventing studio choices."""
        row = self.db.execute("SELECT * FROM settings WHERE id=1").fetchone()
        return (
            {"revision": row["revision"], **json.loads(row["body"])}
            if row
            else {"revision": 0, "configured": False}
        )

    def dispatch(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Serialize mutations and replay identical requests without another write."""
        if action in {"read", "context", "settings", "operation"}:
            return self.read(action, args)
        key = text(args.get("request_key"), "request key")
        request = encode({"action": action, "arguments": args})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute(
                "SELECT * FROM requests WHERE key=?", (key,)
            ).fetchone()
            if previous:
                if previous["payload"] != request:
                    raise ValueError(
                        "Request key was already used for different content"
                    )
                result = json.loads(previous["result"])
                # Never replay an old dispatch authorization as permission to send again.
                if action == "claim":
                    result = {
                        "operation": self.operation(args["operation_id"]),
                        "execute": False,
                    }
                self.db.execute("COMMIT")
                return result
            result = self.mutate(action, args)
            self.audit(action, result)
            self.db.execute(
                "INSERT INTO requests VALUES(?,?,?)", (key, request, encode(result))
            )
            self.db.execute("COMMIT")
            return result
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
            self.db.execute("ROLLBACK")
            raise

    def read(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Return bounded current context, including unresolved external writes."""
        if action == "read":
            return {"item": self.record(args["item_id"])}
        if action == "settings":
            return self.settings()
        if action == "operation":
            return {"operation": self.operation(args["operation_id"])}
        if action != "context":
            raise ValueError("Unknown read action")
        day = date.fromisoformat(args["day"])
        zone = ZoneInfo(self.settings().get("timezone", "Europe/Rome"))
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid offset")
        rows = []
        for row in self.db.execute("SELECT id FROM records ORDER BY id"):
            item = self.record(row["id"])
            if args.get("include_closed") or item["status"] not in {
                "done",
                "cancelled",
            }:
                item["overdue"] = bool(
                    item.get("due_date")
                    and date.fromisoformat(item["due_date"]) < day
                    and item["status"] not in {"done", "cancelled"}
                )
                item["scheduled_today"] = bool(
                    item.get("start_time")
                    and instant(item["start_time"]).astimezone(zone).date() == day
                )
                item["completed_today"] = bool(
                    item.get("completed_at")
                    and instant(item["completed_at"]).astimezone(zone).date() == day
                )
                item["follow_up_due"] = bool(
                    item.get("follow_up_date")
                    and date.fromisoformat(item["follow_up_date"]) <= day
                    and item["status"] not in {"done", "cancelled"}
                )
                rows.append(item)
        pending = [
            self.operation(row["id"])
            for row in self.db.execute(
                "SELECT id FROM operations WHERE state IN ('prepared','in_flight','uncertain') ORDER BY id LIMIT 51"
            )
        ]
        meetings = [
            json.loads(row["body"])
            for row in self.db.execute(
                "SELECT body FROM meetings ORDER BY rowid DESC LIMIT 10"
            )
        ]
        return {
            "day": day.isoformat(),
            "settings": self.settings(),
            "items": rows[offset : offset + 50],
            "total": len(rows),
            "next_offset": offset + 50 if len(rows) > offset + 50 else None,
            "operations": pending[:50],
            "more_operations": len(pending) > 50,
            "meetings": meetings,
            "calendar_refresh_required": True,
            "scheduler_installed": False,
            "model_data": {
                "context": "Selected commitments, meeting notes, preferences and operation receipts returned by these tools reach the host model. Names and client details are not anonymized.",
                "storage": "Owner-local SQLite; no network calls from this service.",
                "external": "Host connectors send selected event or email fields to the connected account only when invoked.",
            },
        }

    def mutate(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Apply one atomic local state transition."""
        if action == "report_workspace":
            text(args["label"], "work label")
            identifier = "run_" + uuid.uuid4().hex[:24]
            output = self.path.parent / "reports" / identifier
            output.mkdir(parents=True, mode=0o700)
            return {
                "run_id": identifier,
                "label": args["label"],
                "output_dir": str(output),
                "report_created": False,
            }
        if action == "configure":
            current = self.settings()
            if args["expected_revision"] != current["revision"]:
                raise ValueError("Preferences changed; read them again")
            preferences = args["preferences"]
            if set(preferences) - {
                "timezone",
                "calendar_id",
                "working_hours",
                "protected_time",
                "durations",
                "colors",
                "reminder_minutes",
                "daily_briefing",
                "rules",
            }:
                raise ValueError("Unknown preference fields")
            ZoneInfo(preferences["timezone"])
            text(preferences["calendar_id"], "calendar ID")
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES(1,?,?)",
                (current["revision"] + 1, encode(preferences)),
            )
            return self.settings()
        if action == "capture":
            item = {"status": "open", **args["item"], "id": uuid.uuid4().hex}
            validate_item(args["item"])
            return {"item": self.save(item, 1)}
        if action == "meeting":
            meeting = args["meeting"]
            if set(meeting) - {
                "title",
                "date",
                "client",
                "participants",
                "source",
                "summary",
                "decisions",
                "missing_documents",
            }:
                raise ValueError("Unknown meeting fields")
            text(meeting["title"], "meeting title")
            text(meeting["source"], "meeting source")
            date.fromisoformat(meeting["date"])
            items = []
            for supplied in args.get("actions", []):
                validate_item(supplied)
                items.append(
                    self.save({"status": "open", **supplied, "id": uuid.uuid4().hex}, 1)
                )
            value = {
                "id": uuid.uuid4().hex,
                **meeting,
                "action_ids": [x["id"] for x in items],
            }
            self.db.execute(
                "INSERT INTO meetings VALUES(?,?)", (value["id"], encode(value))
            )
            return {"meeting": value, "items": items}
        if action == "abandon":
            operation = self.operation(args["operation_id"])
            if operation["state"] != "prepared":
                raise ValueError("Only undispatched operations may be abandoned")
            text(args["authorization"], "user instruction")
            self.db.execute(
                "UPDATE operations SET state='abandoned' WHERE id=?", (operation["id"],)
            )
            return {"operation": self.operation(operation["id"]), "execute": False}
        if action in {"claim", "resolve"}:
            return self.finish_operation(action, args)
        item = self.record(args["item_id"])
        if args["expected_revision"] != item["revision"]:
            raise ValueError("Commitment changed; read it again")
        unresolved = self.db.execute(
            "SELECT id FROM operations WHERE item_id=? AND state IN ('prepared','in_flight','uncertain')",
            (item["id"],),
        ).fetchone()
        if unresolved:
            raise ValueError(
                "Resolve the existing external operation before changing this commitment"
            )
        if action == "change":
            patch = args["patch"]
            if set(patch) - FIELDS:
                raise ValueError("Unknown commitment fields")
            if item.get("calendar") and (
                set(patch) & {"title", "start_time", "end_time", "category"}
                or patch.get("status") == "cancelled"
            ):
                raise ValueError(
                    "Calendar-linked changes require a verified update/delete operation"
                )
            return {"item": self.save({**item, **patch}, item["revision"] + 1)}
        if action != "prepare":
            raise ValueError("Unknown mutation")
        operation_action = args["action"]
        if operation_action not in {"create", "update", "delete"}:
            raise ValueError("Invalid calendar action")
        text(args["authorization"], "user instruction authorizing this action")
        if item["status"] in {"done", "cancelled"}:
            raise ValueError("Closed commitment cannot receive a calendar write")
        linked = item.get("calendar")
        if (operation_action == "create") == bool(linked):
            raise ValueError(
                "Create requires no existing event; update/delete require an existing event"
            )
        desired = args["event"]
        validate_event(operation_action, desired)
        preferences = self.settings()
        calendar_id = (
            linked["calendar_id"] if linked else preferences.get("calendar_id")
        )
        if not calendar_id:
            raise ValueError("Configure the chosen calendar first")
        identifier = uuid.uuid4().hex
        desired = dict(desired)
        if operation_action == "create":
            desired["description"] = (
                desired.get("description", "") + "\nVera operation: " + identifier
            )
        operation = {
            "item_id": item["id"],
            "item_revision": item["revision"],
            "action": operation_action,
            "desired": desired,
            "authorization": args["authorization"],
            "calendar_id": calendar_id,
            "event_id": linked["event_id"] if linked else None,
        }
        self.db.execute(
            "INSERT INTO operations VALUES(?,?,?,?)",
            (identifier, item["id"], "prepared", encode(operation)),
        )
        return {"operation": self.operation(identifier), "execute": False}

    def finish_operation(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Require read-back evidence; uncertain operations cannot be redispatched."""
        operation = self.operation(args["operation_id"])
        item = self.record(operation["item_id"])
        if action == "claim":
            if operation["state"] != "prepared":
                return {"operation": operation, "execute": False}
            if item["revision"] != operation["item_revision"]:
                raise ValueError("Commitment changed before dispatch")
            self.db.execute(
                "UPDATE operations SET state='in_flight' WHERE id=?", (operation["id"],)
            )
            desired = dict(operation["desired"])
            desired["calendar_id"] = operation["calendar_id"]
            if operation["event_id"]:
                desired["event_id"] = operation["event_id"]
            if operation["action"] == "create":
                desired["attendees"] = []
            return {
                "operation": self.operation(operation["id"]),
                "execute": True,
                "connector_tool": "google_calendar_" + operation["action"] + "_event",
                "connector_arguments": desired,
            }
        if operation["state"] not in {"in_flight", "uncertain"}:
            raise ValueError("Only dispatched operations can be resolved")
        outcome = args["outcome"]
        if outcome not in {"verified", "failed", "uncertain"}:
            raise ValueError("Invalid outcome")
        evidence = args["evidence"]
        text(evidence.get("tool"), "connector evidence tool")
        text(evidence.get("reference"), "actual tool-response reference")
        if outcome == "verified":
            if evidence.get("calendar_id") != operation["calendar_id"]:
                raise ValueError("Read-back calendar differs")
            identifier = text(evidence.get("event_id"), "read-back event ID")
            if operation["event_id"] and identifier != operation["event_id"]:
                raise ValueError("Read-back event differs")
            if operation["action"] == "delete":
                if evidence.get("absent") is not True:
                    raise ValueError("Deletion requires explicit verified absence")
                item.pop("calendar", None)
                item["status"] = "cancelled"
            else:
                event = evidence["event"]
                for field, value in operation["desired"].items():
                    actual = event.get(field)
                    if field in {"start_time", "end_time"}:
                        equal = isinstance(actual, str) and instant(actual) == instant(
                            value
                        )
                    else:
                        equal = actual == value
                    if not equal:
                        raise ValueError(f"Read-back mismatch: {field}")
                if operation["action"] == "create" and "Vera operation: " + operation[
                    "id"
                ] not in event.get("description", ""):
                    raise ValueError("Created event has no recovery marker")
                item["calendar"] = {
                    "calendar_id": operation["calendar_id"],
                    "event_id": identifier,
                }
                item["title"] = event["title"]
                for field in ("start_time", "end_time"):
                    item.pop(field, None)
                    if field in event:
                        item[field] = event[field]
                if "start_date" in event:
                    item["due_date"] = event["start_date"]
            item = self.save(item, item["revision"] + 1)
        elif outcome == "failed" and evidence.get("definitive_no_write") is not True:
            raise ValueError(
                "Unknown outcomes remain uncertain; failure requires definitive no-write evidence"
            )
        body = {
            key: value for key, value in operation.items() if key not in {"id", "state"}
        }
        body["evidence"] = evidence
        self.db.execute(
            "UPDATE operations SET state=?,body=? WHERE id=?",
            (outcome, encode(body), operation["id"]),
        )
        return {
            "operation": self.operation(operation["id"]),
            "item": item,
            "execute": False,
        }


def main() -> int:
    """Serve one bounded JSON bridge request using owner-local managed storage."""
    service = None
    try:
        request = json.loads(sys.stdin.read(1024 * 1024 + 1))
        service = StudioWork(storage_root())
        result = service.dispatch(request["action"], request["arguments"])
        sys.stdout.write(encode(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        logging.error("Studio work request refused: %s", exc)
        return 1
    finally:
        if service is not None:
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
