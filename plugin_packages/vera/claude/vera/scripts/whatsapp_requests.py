"""Owner-local WhatsApp requests and receipts; never reads or sends via WhatsApp.

Exact phone matching, immutable bytes, revisions and transactional dispatch claims
prevent wrong-recipient writes, changed attachments and duplicate sends. The host
interprets messages/documents and supplies actual UI evidence; this is no independent
verification of WhatsApp delivery. No credentials or network calls live here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from studio_work import encode, storage_root, text

__all__ = ["WhatsAppRequests", "phone", "main"]

ITEM_STATES = {
    "awaiting",
    "received",
    "checked",
    "correction_requested",
    "complete",
    "cancelled",
}
REQUEST_FIELDS = {
    "title",
    "owner",
    "engagement",
    "source",
    "due_date",
    "follow_up_date",
    "items",
    "status",
    "notes",
}


def phone(value: Any) -> str:
    """Normalize user-confirmed international numbers; never guess country codes."""
    value = text(value, "international phone").strip()
    if not re.fullmatch(r"(?:\+|00)[0-9 ()-]+", value):
        raise ValueError("Supply a complete international phone number")
    digits = re.sub(r"\D", "", value)
    if value.startswith("00"):
        digits = digits[2:]
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("Invalid international phone number")
    return "+" + digits


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def validate_request(value: dict[str, Any]) -> None:
    if (
        set(value)
        - REQUEST_FIELDS
        - {"id", "revision", "binding_id", "account", "client"}
    ):
        raise ValueError("Unknown request field")
    for key in ("title", "source", "owner"):
        text(value.get(key), key)
    if value.get("status") not in {"open", "complete", "cancelled"}:
        raise ValueError("Invalid request status")
    for key in ("due_date", "follow_up_date"):
        if value.get(key):
            date.fromisoformat(value[key])
    items = value.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Supply at least one requested item")
    identities = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {
            "id",
            "description",
            "status",
            "evidence",
        }:
            raise ValueError("Invalid request item")
        identity = text(item.get("id"), "item id")
        text(item.get("description"), "item description")
        if identity in identities or item.get("status") not in ITEM_STATES:
            raise ValueError("Duplicate item or invalid item status")
        identities.add(identity)
        if item["status"] in {
            "received",
            "checked",
            "complete",
            "correction_requested",
        }:
            text(item.get("evidence"), "source or review evidence")
    if value["status"] == "complete" and any(
        i["status"] not in {"complete", "cancelled"} for i in items
    ):
        raise ValueError("Open items remain; receipt alone is not completion")


class WhatsAppRequests:
    """Persistent records, recovery and exclusive ownership of the local UI."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or storage_root() / "whatsapp"
        for candidate in (self.root, *self.root.parents):
            if candidate.is_symlink():
                raise ValueError("WhatsApp storage must not use symlink directories")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        db_path = self.root / "requests.sqlite3"
        if db_path.is_symlink():
            raise ValueError("WhatsApp database must not be a symlink")
        self.db = sqlite3.connect(db_path, isolation_level=None, timeout=10)
        db_path.chmod(0o600)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, body TEXT);
            CREATE TABLE IF NOT EXISTS retries (key TEXT PRIMARY KEY, payload TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS ui_lock (singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT);
            CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, at TEXT, action TEXT, body TEXT);
        """
        )

    def close(self) -> None:
        self.db.close()

    def get(self, identity: str, kind: str | None = None) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT kind, body FROM records WHERE id=?", (identity,)
        ).fetchone()
        if not row or (kind and row[0] != kind):
            raise ValueError("Unknown record")
        return json.loads(row[1])

    def put(self, kind: str, value: dict[str, Any]) -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO records VALUES (?,?,?) ON CONFLICT(id) DO UPDATE "
            "SET kind=excluded.kind, body=excluded.body",
            (value["id"], kind, encode(value)),
        )
        return value

    def rows(self, kind: str) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,)
            )
        ]

    def locked(self, token: str, account: str | None = None) -> dict[str, Any]:
        row = self.db.execute("SELECT body FROM ui_lock WHERE singleton=1").fetchone()
        value = json.loads(row[0]) if row else {}
        if value.get("token") != token or (account and value.get("account") != account):
            raise ValueError(
                "Acquire exclusive WhatsApp UI access for this account first"
            )
        return value

    def call(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action == "runtime":
            # Host provenance prevents a cloud/VM ledger from pretending to lock
            # the user's native app. The agent must also match the selected device.
            native_platform = {"Darwin": "mac", "Windows": "windows"}.get(
                platform.system()
            )
            return {
                "platform": native_platform or "unsupported",
                "device_name": platform.node(),
                "storage_root": str(self.root.resolve()),
                "native_host": native_platform is not None,
                "ui_control": False,
                "device_match_required": True,
            }
        if action == "read":
            return self.get(text(args.get("id"), "id"))
        if action == "context":
            day = date.fromisoformat(args["day"])
            offset = args.get("offset", 0)
            if type(offset) is not int or offset < 0:
                raise ValueError("Invalid offset")
            account = phone(args["account"])
            requests = [
                r
                for r in self.rows("request")
                if r["account"] == account
                and (args.get("include_closed") or r["status"] == "open")
            ]
            for request in requests:
                request["follow_up_due"] = bool(
                    request.get("follow_up_date")
                    and date.fromisoformat(request["follow_up_date"]) <= day
                )
            lock = self.db.execute(
                "SELECT body FROM ui_lock WHERE singleton=1"
            ).fetchone()
            return {
                "requests": requests[offset : offset + 50],
                "total": len(requests),
                "next_offset": offset + 50 if offset + 50 < len(requests) else None,
                "unresolved_operations": [
                    o
                    for o in self.rows("operation")
                    if o["account"] == account
                    and o["status"] in {"prepared", "submitting", "uncertain"}
                ],
                "pending_archive": [
                    a
                    for a in self.rows("attachment")
                    if a["account"] == account and a["archive_status"] != "archived"
                ],
                "ui_busy": bool(lock),
                "ui_session": json.loads(lock[0]) if lock else None,
                "background_scheduler": False,
            }
        method = getattr(self, "do_" + action, None)
        if method is None:
            raise ValueError("Unknown WhatsApp action")
        key = text(args.get("request_key"), "request key")
        payload = encode({"action": action, "args": args})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                "SELECT payload, result FROM retries WHERE key=?", (key,)
            ).fetchone()
            if prior:
                if prior[0] != payload:
                    raise ValueError("Request key reused with changed content")
                result = json.loads(prior[1])
                if action == "claim":
                    result = {
                        "execute": False,
                        "operation": self.get(args["id"], "operation"),
                    }
                if action == "acquire":
                    result = self.locked(result["token"])
                self.db.execute("COMMIT")
                return result
            result = method(args)
            self.db.execute(
                "INSERT INTO retries VALUES (?,?,?)", (key, payload, encode(result))
            )
            self.db.execute(
                "INSERT INTO events(at,action,body) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), action, encode(result)),
            )
            self.db.execute("COMMIT")
            return result
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error):
            self.db.execute("ROLLBACK")
            raise

    def do_acquire(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.db.execute("SELECT 1 FROM ui_lock").fetchone():
            raise ValueError(
                "WhatsApp is owned by another session; reconcile that session before release"
            )
        value = {
            "token": str(uuid.uuid4()),
            "account": phone(args["account"]) if args.get("account") else None,
            "owner": text(args.get("owner"), "session owner"),
        }
        self.db.execute("INSERT INTO ui_lock VALUES (1,?)", (encode(value),))
        return value

    def do_release(self, args: dict[str, Any]) -> dict[str, Any]:
        lock = self.locked(args["token"])
        if any(
            o.get("lock_token") == lock["token"] and o["status"] == "submitting"
            for o in self.rows("operation")
        ):
            raise ValueError(
                "Record the dispatch outcome or uncertainty before releasing the UI"
            )
        text(args.get("evidence"), "UI session ended or crash recovery evidence")
        self.db.execute("DELETE FROM ui_lock")
        return {"released": True}

    def do_bind(self, args: dict[str, Any]) -> dict[str, Any]:
        account, recipient = phone(args["account"]), phone(args["phone"])
        lock = self.locked(args["token"])
        if lock["account"] is None:
            lock["account"] = account
            self.db.execute(
                "UPDATE ui_lock SET body=? WHERE singleton=1", (encode(lock),)
            )
        else:
            self.locked(args["token"], account)
        if phone(args["observed_phone"]) != recipient:
            raise ValueError(
                "Contact-info phone differs from the confirmed client phone"
            )
        value = {
            "account": account,
            "phone": recipient,
            "client": text(args.get("client"), "client"),
            "alias": text(args.get("alias"), "observed alias"),
            "evidence": text(
                args.get("evidence"), "actual account and contact-info observation"
            ),
            "confirmation": text(
                args.get("confirmation"), "user identity confirmation"
            ),
            "platform": args["platform"],
        }
        if value["platform"] not in {"mac", "windows"}:
            raise ValueError("Local mode requires a supported desktop host")
        value["id"] = (
            "binding-"
            + hashlib.sha256(
                encode([account, recipient, value["client"]]).encode()
            ).hexdigest()[:24]
        )
        return self.put("binding", value)

    def do_capture(self, args: dict[str, Any]) -> dict[str, Any]:
        binding = self.get(args["binding_id"], "binding")
        value = dict(args["request"])
        if set(value) - REQUEST_FIELDS:
            raise ValueError("Unknown request field")
        value.setdefault("status", "open")
        value.update(
            id=str(uuid.uuid4()),
            revision=0,
            binding_id=binding["id"],
            account=binding["account"],
            client=binding["client"],
        )
        validate_request(value)
        return self.put("request", value)

    def do_change(self, args: dict[str, Any]) -> dict[str, Any]:
        value = self.get(args["id"], "request")
        if value["revision"] != args["expected_revision"]:
            raise ValueError("Request changed; read the current revision")
        if set(args["patch"]) - REQUEST_FIELDS:
            raise ValueError("Cannot reassign an existing request's identity")
        value.update(args["patch"])
        validate_request(value)
        value["revision"] += 1
        return self.put("request", value)

    def do_stage(self, args: dict[str, Any]) -> dict[str, Any]:
        request = self.get(args["id"], "request")
        source = Path(args["path"]).expanduser()
        if not source.is_absolute() or not source.is_file():
            raise ValueError(
                "Download the selected attachment to an existing absolute local path first"
            )
        locator = text(args.get("source"), "message or local source locator")
        if args["direction"] not in {"incoming", "outgoing"}:
            raise ValueError("Invalid attachment direction")
        folder = self.root / "attachments"
        if folder.is_symlink():
            raise ValueError("Attachment store must not be a symlink")
        folder.mkdir(mode=0o700, exist_ok=True)
        identity = str(uuid.uuid4())
        target_folder = folder / identity
        target_folder.mkdir(mode=0o700)
        target = target_folder / source.name
        # Copy first and hash the retained bytes: later source changes cannot change an approved send.
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            target.chmod(0o600)
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)
        return self.put(
            "attachment",
            {
                "id": identity,
                "request_id": request["id"],
                "account": request["account"],
                "path": str(target),
                "filename": source.name,
                "sha256": digest(target),
                "bytes": target.stat().st_size,
                "source": locator,
                "direction": args["direction"],
                "archive_status": "pending",
                "archive_receipt": None,
            },
        )

    def do_archive(self, args: dict[str, Any]) -> dict[str, Any]:
        value = self.get(args["id"], "attachment")
        if args["status"] not in {"pending", "failed", "archived"}:
            raise ValueError("Invalid archive status")
        evidence = text(args.get("evidence"), "archive receipt or failure")
        if args["status"] == "archived" and args.get("sha256") != value["sha256"]:
            raise ValueError("Archive receipt must match the retained source bytes")
        value.update(archive_status=args["status"], archive_receipt=evidence)
        return self.put("attachment", value)

    def do_prepare(self, args: dict[str, Any]) -> dict[str, Any]:
        request = self.get(args["id"], "request")
        if (
            request["status"] != "open"
            or request["revision"] != args["expected_revision"]
        ):
            raise ValueError("Read the current open request before preparing a message")
        binding = self.get(request["binding_id"], "binding")
        body = args.get("body", "")
        if not isinstance(body, str) or len(body) > 20000:
            raise ValueError("Invalid message body")
        attachments = [
            self.get(identity, "attachment")
            for identity in args.get("attachment_ids", [])
        ]
        if not body.strip() and not attachments:
            raise ValueError("Empty message")
        if any(
            a["request_id"] != request["id"] or a["direction"] != "outgoing"
            for a in attachments
        ):
            raise ValueError(
                "Attachment belongs to another request or is not an outgoing selection"
            )
        intent = {
            "request_id": request["id"],
            "account": request["account"],
            "phone": binding["phone"],
            "body": body,
            "attachments": [
                {
                    key: attachment[key]
                    for key in ("id", "path", "filename", "sha256", "bytes")
                }
                for attachment in attachments
            ],
        }
        fingerprint = hashlib.sha256(encode(intent).encode()).hexdigest()
        authorization = text(
            args.get("authorization"), "specific user send instruction"
        )
        predecessor = args.get("retry_of") or args.get("repeat_of")
        if args.get("retry_of") and args.get("repeat_of"):
            raise ValueError("Choose retry or a deliberately repeated message")
        if predecessor:
            previous = self.get(predecessor, "operation")
            allowed = {"accepted"} if args.get("repeat_of") else {"failed", "cancelled"}
            if (
                previous["request_id"] != request["id"]
                or previous["status"] not in allowed
            ):
                raise ValueError(
                    "Only a resolved operation in this request can be retried or repeated"
                )
            if authorization == previous["authorization"]:
                raise ValueError(
                    "Record the new specific instruction to repeat or retry"
                )
        for operation in reversed(self.rows("operation")):
            if operation["request_id"] == request["id"]:
                if operation["fingerprint"] == fingerprint:
                    if predecessor != operation["id"]:
                        return operation
                    break
                if operation["status"] in {"prepared", "submitting", "uncertain"}:
                    raise ValueError(
                        "Resolve the existing message before preparing another"
                    )
        return self.put(
            "operation",
            {
                **intent,
                "id": str(uuid.uuid4()),
                "fingerprint": fingerprint,
                "revision": request["revision"],
                "status": "prepared",
                "delivery": "unknown",
                "authorization": authorization,
                "predecessor": predecessor,
                "evidence": None,
            },
        )

    def do_claim(self, args: dict[str, Any]) -> dict[str, Any]:
        operation = self.get(args["id"], "operation")
        self.locked(args["token"], operation["account"])
        if operation["status"] != "prepared":
            return {"execute": False, "operation": operation}
        request = self.get(operation["request_id"], "request")
        if request["revision"] != operation["revision"] or request["status"] != "open":
            raise ValueError(
                "Request changed after message preparation; cancel and prepare again"
            )
        if phone(args["observed_phone"]) != operation["phone"]:
            raise ValueError("Current contact-info phone differs from recipient")
        if phone(args["observed_account"]) != operation["account"]:
            raise ValueError("Selected WhatsApp account changed")
        for attachment in operation["attachments"]:
            if digest(Path(attachment["path"])) != attachment["sha256"]:
                raise ValueError("Prepared attachment changed")
        operation.update(status="submitting", lock_token=args["token"])
        self.put("operation", operation)
        return {"execute": True, "operation": operation}

    def do_resolve(self, args: dict[str, Any]) -> dict[str, Any]:
        operation = self.get(args["id"], "operation")
        outcome, evidence = args["outcome"], args["evidence"]
        text(evidence.get("locator"), "actual UI observation or error locator")
        if outcome == "cancelled" and operation["status"] == "prepared":
            operation.update(status=outcome, evidence=evidence)
            return self.put("operation", operation)
        updating_delivery = operation["status"] == "accepted" and outcome == "accepted"
        if (
            operation["status"] not in {"submitting", "uncertain"}
            and not updating_delivery
        ) or outcome not in {
            "accepted",
            "failed",
            "uncertain",
        }:
            raise ValueError("Invalid outcome transition")
        if outcome == "accepted":
            if (
                phone(evidence.get("phone")) != operation["phone"]
                or evidence.get("body") != operation["body"]
            ):
                raise ValueError(
                    "Observed recipient/body differs from prepared message"
                )
            if evidence.get("attachment_names", []) != [
                a["filename"] for a in operation["attachments"]
            ]:
                raise ValueError(
                    "Observed attachment names differ from prepared selection"
                )
            if evidence.get("delivery", "unknown") not in {
                "unknown",
                "sent",
                "delivered",
                "read",
            }:
                raise ValueError("Invalid delivery observation")
            delivery_order = ["unknown", "sent", "delivered", "read"]
            if delivery_order.index(
                evidence.get("delivery", "unknown")
            ) < delivery_order.index(operation["delivery"]):
                raise ValueError(
                    "Delivery evidence cannot regress a recorded observation"
                )
            operation["delivery"] = evidence.get("delivery", "unknown")
        if outcome == "failed" and evidence.get("definitive_no_send") is not True:
            raise ValueError(
                "A timeout or missing bubble is uncertain, not a definitive failure"
            )
        operation.update(status=outcome, evidence=evidence)
        return self.put("operation", operation)


def main() -> None:
    store = WhatsAppRequests()
    try:
        request = json.load(sys.stdin)
        result = store.call(request["action"], request.get("arguments", {}))
        sys.stdout.write(encode(result) + "\n")
    finally:
        store.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        logging.error("%s", error)
        sys.exit(1)
