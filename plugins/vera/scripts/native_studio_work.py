"""Owner-local native view over the maintained studio-work register.

Paging, exact revisions and retry receipts are mechanical audit safeguards.
Meaning, priorities and calendar execution remain in the specialist workflow.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from studio_work import FIELDS, StudioWork, encode, storage_root, text

__all__ = ["NativeStudioWork", "main"]
TABLES = {"items": "records", "operations": "operations", "meetings": "meetings"}
# Full queries are fixed literals; caller fields never become SQL identifiers.
SCOPE_QUERIES = {
    "settings": "SELECT * FROM settings ORDER BY id",
    "records": "SELECT * FROM records ORDER BY id",
    "operations": "SELECT * FROM operations ORDER BY id",
    "meetings": "SELECT * FROM meetings ORDER BY id",
    "history": "SELECT * FROM history ORDER BY sequence",
}
COUNT_QUERIES = {
    "items": "SELECT COUNT(*) FROM records",
    "operations": "SELECT COUNT(*) FROM operations",
    "meetings": "SELECT COUNT(*) FROM meetings",
    "history": "SELECT COUNT(*) FROM history",
}
PAGE_QUERIES = {
    "items": "SELECT * FROM records ORDER BY id LIMIT 30 OFFSET ?",
    "operations": "SELECT * FROM operations ORDER BY id LIMIT 30 OFFSET ?",
    "meetings": "SELECT * FROM meetings ORDER BY id LIMIT 30 OFFSET ?",
    "history": "SELECT * FROM history ORDER BY sequence DESC LIMIT 30 OFFSET ?",
}


class NativeStudioWork:
    """Keep drafts and exact local save intents beside the authoritative ledger."""

    def __init__(self, root: Path) -> None:
        self.service = StudioWork(root)
        self.db = self.service.db
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS native_work_drafts (
            id TEXT PRIMARY KEY, revision INTEGER NOT NULL, scope TEXT NOT NULL,
            fields TEXT NOT NULL, state TEXT NOT NULL, intent TEXT, result TEXT)"""
        )

    def close(self) -> None:
        """Close the maintained connection."""
        self.service.close()

    def scope(self) -> str:
        """Bind actual owner location, implementation and current business state."""
        digest = hashlib.sha256(str(self.service.path.absolute()).encode())
        root = Path(__file__).resolve().parents[1]
        for name in (
            "scripts/studio_work.py",
            "scripts/native_studio_work.py",
            "mcp/studio-work.cjs",
            "mcp/studio-work-panel.cjs",
            "ui/studio-work.js",
            "ui/studio-work.html",
            "ui/studio-work.css",
            "ui/workspace.css",
            "ui/custom_select.js",
            "ui/InstrumentSans-Regular.ttf",
        ):
            digest.update(name.encode())
            digest.update(hashlib.sha256((root / name).read_bytes()).digest())
        for table, query in SCOPE_QUERIES.items():
            digest.update(table.encode())
            for row in self.db.execute(query):
                digest.update(encode(dict(row)).encode())
                digest.update(b"\n")
        return digest.hexdigest()

    def draft(self, form: str, scope: str) -> dict[str, Any]:
        """Return incomplete literal fields; never restore user confirmation."""
        self.form(form)
        row = self.db.execute(
            "SELECT * FROM native_work_drafts WHERE id=?", (form,)
        ).fetchone()
        if row is None:
            return {"revision": 0, "fields": {}, "state": "draft", "stale": False}
        return {
            "revision": row["revision"],
            "fields": json.loads(row["fields"]),
            "state": row["state"],
            "stale": row["scope"] != scope,
            "result": json.loads(row["result"]) if row["result"] else None,
        }

    def form(self, value: Any) -> str:
        """Allow only literal forms or an actual existing commitment."""
        text(value, "form")
        if value not in {"capture", "meeting"}:
            if not value.startswith("record:"):
                raise ValueError("Unknown studio-work form")
            self.service.record(value.removeprefix("record:"))
        return value

    def page(self, args: dict[str, Any]) -> dict[str, Any]:
        """Page every register collection with a stable business-state receipt."""
        collection = args.get("collection", "items")
        offset = args.get("offset", 0)
        if (
            collection not in {*TABLES, "history"}
            or type(offset) is not int
            or offset < 0
        ):
            raise ValueError("Invalid register page")
        self.db.execute("BEGIN")
        try:
            scope = self.scope()
            if args.get("expected_scope") and args["expected_scope"] != scope:
                raise ValueError("Register changed; reread before continuing")
            settings = self.service.settings()
            day = args.get("day")
            if day:
                date.fromisoformat(day)
            elif settings.get("timezone"):
                day = datetime.now(ZoneInfo(settings["timezone"])).date().isoformat()
            total = self.db.execute(COUNT_QUERIES[collection]).fetchone()[0]
            rows = self.db.execute(PAGE_QUERIES[collection], (offset,)).fetchall()
            if collection == "items":
                items = [self.service.record(row["id"]) for row in rows]
            elif collection == "operations":
                items = [self.service.operation(row["id"]) for row in rows]
            elif collection == "meetings":
                items = [json.loads(row["body"]) for row in rows]
            else:
                items = [{**dict(row), "body": json.loads(row["body"])} for row in rows]
            counts = {
                name: self.db.execute(COUNT_QUERIES[name]).fetchone()[0]
                for name in TABLES
            }
            counts["history"] = self.db.execute(
                "SELECT COUNT(*) FROM history"
            ).fetchone()[0]
            value = {
                "scope_revision": scope,
                "collection": collection,
                "offset": offset,
                "items": items,
                "total": total,
                "next_offset": offset + 30 if total > offset + 30 else None,
                "settings": settings,
                "counts": counts,
                "day": day,
                "calendar_refresh_required": True,
                "scheduler_installed": False,
            }
            if args.get("form"):
                form = self.form(args["form"])
                value.update(form=form, draft=self.draft(form, scope))
                if form.startswith("record:"):
                    value["record"] = self.service.record(form.removeprefix("record:"))
            self.db.execute("COMMIT")
            return value
        except (ValueError, KeyError, TypeError, sqlite3.Error):
            self.db.execute("ROLLBACK")
            raise

    def fields(self, form: str, value: Any) -> dict[str, Any]:
        """Bound literal partial fields, including source-based meeting actions."""
        if not isinstance(value, dict) or len(encode(value).encode()) > 250000:
            raise ValueError("Invalid or oversized incomplete fields")
        if form == "meeting":
            if set(value) - {"meeting", "actions"}:
                raise ValueError("Unknown meeting draft field")
            meeting = value.get("meeting", {})
            actions = value.get("actions", [])
            if (
                not isinstance(meeting, dict)
                or set(meeting)
                - {
                    "title",
                    "date",
                    "client",
                    "participants",
                    "source",
                    "summary",
                    "decisions",
                    "missing_documents",
                }
                or not isinstance(actions, list)
                or len(actions) > 100
            ):
                raise ValueError("Invalid meeting draft")
            for item in actions:
                self.fields("capture", item)
        elif set(value) - FIELDS:
            raise ValueError("Unknown commitment draft field")
        return value

    def edit(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Persist or clear only the exact private draft under SQLite CAS."""
        form = self.form(args["form"])
        self.db.execute("BEGIN IMMEDIATE")
        try:
            scope = self.scope()
            if args["scope_revision"] != scope:
                raise ValueError("Register changed; reread and compare the draft")
            draft = self.draft(form, scope)
            if args["expected_draft_revision"] != draft["revision"]:
                raise ValueError("Draft changed in another panel; reread it")
            if draft["state"] == "pending":
                raise ValueError("Recover the retained local save before editing")
            if action == "draft_save" and (
                draft["stale"] or draft["state"] == "completed"
            ):
                raise ValueError(
                    "Compare and discard only the private draft before starting again"
                )
            fields = (
                {} if action == "draft_clear" else self.fields(form, args["fields"])
            )
            revision = draft["revision"] + 1
            self.db.execute(
                "INSERT OR REPLACE INTO native_work_drafts VALUES(?,?,?,?,'draft',NULL,NULL)",
                (form, revision, scope, encode(fields)),
            )
            self.db.execute("COMMIT")
        except (ValueError, KeyError, TypeError, sqlite3.Error):
            self.db.execute("ROLLBACK")
            raise
        return self.page({"form": form})

    def submit(self, args: dict[str, Any]) -> dict[str, Any]:
        """Retain an authorized exact intent, then call the public local engine."""
        form = self.form(args["form"])
        if args.get("human_confirmed") is not True:
            raise ValueError("Renew confirmation of this local save")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            scope = self.scope()
            draft = self.draft(form, scope)
            if args["scope_revision"] != scope or draft["stale"]:
                raise ValueError("Register changed; compare before saving")
            if (
                args["expected_draft_revision"] != draft["revision"]
                or draft["state"] != "draft"
            ):
                raise ValueError("Draft changed or already submitted; reread it")
            if not draft["revision"]:
                raise ValueError("Retain the incomplete fields before submitting")
            fields = self.fields(form, draft["fields"])
            key = "native-work:" + uuid.uuid4().hex
            if form == "capture":
                action, payload = "capture", {"request_key": key, "item": fields}
            elif form == "meeting":
                action, payload = "meeting", {"request_key": key, **fields}
            else:
                item = self.service.record(form.removeprefix("record:"))
                action, payload = "change", {
                    "request_key": key,
                    "item_id": item["id"],
                    "expected_revision": item["revision"],
                    "patch": fields,
                }
            self.db.execute(
                "UPDATE native_work_drafts SET state='pending',intent=? WHERE id=?",
                (encode({"action": action, "arguments": payload}), form),
            )
            self.db.execute("COMMIT")
        except (ValueError, KeyError, TypeError, sqlite3.Error):
            self.db.execute("ROLLBACK")
            raise
        return self.recover(
            {"form": form, "expected_draft_revision": draft["revision"]}
        )

    def recover(self, args: dict[str, Any]) -> dict[str, Any]:
        """Replay only a retained local intent; never prepare/claim a connector."""
        form = self.form(args["form"])
        row = self.db.execute(
            "SELECT * FROM native_work_drafts WHERE id=?", (form,)
        ).fetchone()
        if row is None or args["expected_draft_revision"] != row["revision"]:
            raise ValueError("Local save receipt changed; reread it")
        if row["state"] == "completed":
            return self.page({"form": form})
        if row["state"] != "pending" or not row["intent"]:
            raise ValueError("No retained local save to recover")
        intent = json.loads(row["intent"])
        if intent["action"] not in {"capture", "change", "meeting"}:
            raise ValueError("Native panel cannot dispatch a calendar operation")
        try:
            result = self.service.dispatch(intent["action"], intent["arguments"])
        except (ValueError, KeyError, TypeError):
            # Public dispatch rolled back a known validation refusal, not uncertainty.
            self.db.execute(
                "UPDATE native_work_drafts SET state='draft',intent=NULL WHERE id=? AND revision=? AND intent=?",
                (form, row["revision"], row["intent"]),
            )
            raise
        self.db.execute(
            "UPDATE native_work_drafts SET state='completed',result=? WHERE id=? AND revision=? AND intent=?",
            (encode(result), form, row["revision"], row["intent"]),
        )
        return self.page({"form": form})

    def dispatch(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        """Keep the native API bounded to reading and explicit local saves."""
        if action == "context":
            page = self.page({"expected_scope": args["scope_revision"]})
            collection = args["collection"]
            if collection == "items":
                item = self.service.record(args["item_id"])
            elif collection == "operations":
                item = self.service.operation(args["item_id"])
            elif collection == "meetings":
                row = self.db.execute(
                    "SELECT body FROM meetings WHERE id=?", (args["item_id"],)
                ).fetchone()
                if row is None:
                    raise ValueError("Unknown meeting")
                item = json.loads(row["body"])
            else:
                raise ValueError("Choose one commitment, meeting or operation")
            if self.scope() != page["scope_revision"]:
                raise ValueError("Register changed during selection; reread it")
            return {
                "scope_revision": page["scope_revision"],
                "collection": collection,
                "selection": item,
                "calendar_refresh_required": True,
                "external_write_authorized": False,
                "model_data": "Only this selected stored record is returned to the host model; names and supplied notes are not anonymized.",
            }
        if action == "page":
            return self.page(args)
        if action in {"draft_save", "draft_clear"}:
            return self.edit(action, args)
        if action == "submit":
            return self.submit(args)
        if action == "recover":
            return self.recover(args)
        raise ValueError("Unknown native studio-work action")


def main() -> int:
    """Run the native adapter in the already prepared owner runtime."""
    service = None
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Oversized native studio-work request")
        request = json.loads(raw)
        service = NativeStudioWork(storage_root())
        result = service.dispatch(request["action"], request.get("arguments", {}))
        sys.stdout.write(encode(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        logging.error("Native studio work refused: %s", error)
        return 1
    finally:
        if service:
            service.close()


if __name__ == "__main__":
    raise SystemExit(main())
