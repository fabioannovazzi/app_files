"""Versioned local VAT-code evidence catalog; interpretation remains reviewed input.

SQLite transactions serialize append-only events. Content hashes detect changed
history but do not authenticate a curator or professional. Nothing is shared or
promoted remotely, and matching code strings never classify a tax transaction.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import logging
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import jsonschema
from lipe_core import TREATMENTS, ContractError, check_references, digest, read_json

__all__ = [
    "assess_case_mappings",
    "dispute",
    "resolve_dispute",
    "create_catalog",
    "history",
    "record",
    "revoke",
    "lookup",
    "main",
]

SCHEMA = Path(__file__).resolve().parents[1] / "schemas/catalog-entry.schema.json"
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"enum": ["CONFIRMED"]},
        "reviewer": {"type": "string", "pattern": r"\S"},
        "reviewed_on": {"type": "string", "format": "date"},
        "reason": {"type": "string", "pattern": r"\S"},
    },
    "required": ["status", "reviewer", "reviewed_on", "reason"],
}


def _validate(value: dict, schema: dict) -> None:
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(
        validator.iter_errors(value), key=lambda error: str(error.json_path)
    )
    if errors:
        raise ContractError(f"Catalog {errors[0].json_path}: {errors[0].message}")


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _connect(path: Path, *, write: bool = False) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ContractError("Select an existing, non-symlink LIPE catalog")
    connection = sqlite3.connect(
        path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
        uri=True,
        timeout=10,
    )
    connection.execute("PRAGMA trusted_schema=OFF")
    return connection


def create_catalog(path: Path, studio_id: str, minimum_confidence: str) -> dict:
    """Create a private, studio-scoped catalog with an explicit confidence policy."""
    if not studio_id.strip():
        raise ContractError("Studio identity is required")
    if not re.fullmatch(r"(?:0\.[0-9]{2}|1\.00)", minimum_confidence):
        raise ContractError(
            "Confidence cutoff must be a two-decimal string from 0.00 to 1.00"
        )
    metadata = {
        "schema_version": "lipe.catalog.v1",
        "catalog_id": str(uuid4()),
        "studio_id": studio_id,
        "minimum_confidence": minimum_confidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "identity_authenticated": False,
        "remote_sharing": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb"):
        path.chmod(0o600)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE events (sequence INTEGER PRIMARY KEY, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO metadata VALUES (1, ?)", (_json(metadata),))
    return metadata


def _history(connection: sqlite3.Connection) -> dict:
    metadata_rows = connection.execute("SELECT payload FROM metadata").fetchall()
    if len(metadata_rows) != 1:
        raise ContractError("Invalid catalog metadata")
    metadata = json.loads(metadata_rows[0][0])
    if metadata["schema_version"] != "lipe.catalog.v1":
        raise ContractError("Unsupported catalog schema")
    previous = digest(metadata)
    events = []
    for expected, (sequence, parent, fingerprint, payload) in enumerate(
        connection.execute(
            "SELECT sequence, previous_hash, event_hash, payload FROM events ORDER BY sequence"
        ),
        1,
    ):
        event = json.loads(payload)
        if (
            sequence != expected
            or parent != previous
            or fingerprint != digest({"previous_hash": parent, "event": event})
        ):
            raise ContractError("Catalog history integrity check failed")
        events.append({"sequence": sequence, "event_hash": fingerprint, "event": event})
        previous = fingerprint
    return {"metadata": metadata, "head_hash": previous, "events": events}


def history(path: Path) -> dict:
    """Read and verify the complete local revision chain without changing it."""
    try:
        with closing(_connect(path)) as connection:
            state = _history(connection)
        _verify_objects(path, state)
        return state
    except (sqlite3.DatabaseError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ContractError("Invalid or unreadable LIPE catalog") from exc


def _object_root(path: Path) -> Path:
    root = path.parent / (path.name + ".sources")
    if root.is_symlink():
        raise ContractError("Catalog evidence directory cannot be a symlink")
    return root


def _capture_objects(path: Path, sources: list[dict], source_root: Path) -> list[dict]:
    root = _object_root(path)
    root.mkdir(exist_ok=True, mode=0o700)
    objects = []
    for source in sources:
        original = (source_root / source["path"]).resolve()
        if not original.is_relative_to(source_root.resolve()):
            raise ContractError("Catalog evidence path escapes source root")
        payload = original.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source["sha256"]:
            raise ContractError("Catalog source changed during recording")
        name = source["sha256"] + original.suffix.lower()
        destination = root / name
        if destination.is_symlink():
            raise ContractError("Catalog evidence cannot be a symlink")
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != source["sha256"]:
                raise ContractError("Stored catalog evidence changed")
        else:
            with destination.open("xb") as handle:
                destination.chmod(0o600)
                handle.write(payload)
        objects.append(
            {
                "source_id": source["source_id"],
                "object": name,
                "sha256": source["sha256"],
            }
        )
    return objects


def _verify_objects(path: Path, state: dict) -> None:
    root = _object_root(path)
    checked: set[str] = set()
    for row in state["events"]:
        for item in row["event"].get("source_objects", []):
            name = item["object"]
            if name in checked:
                continue
            if not re.fullmatch(r"[0-9a-f]{64}\.(?:pdf|txt|csv|md)", name):
                raise ContractError("Invalid catalog evidence object name")
            source = root / name
            if (
                source.is_symlink()
                or not source.is_file()
                or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]
            ):
                raise ContractError("Stored catalog evidence missing or changed")
            checked.add(name)


def _latest(state: dict) -> dict[str, dict]:
    latest = {}
    for row in state["events"]:
        event = row["event"]
        if event["kind"] in {"RECORD", "REVOKE"}:
            latest[event["entry_id"]] = row
    return latest


def _identity(entry: dict) -> tuple:
    return (
        entry["scope"],
        entry["client_id"],
        entry["software"]["name"],
        entry["software"]["version"],
        entry["side"],
        entry["code"],
    )


def _append(connection: sqlite3.Connection, state: dict, event: dict) -> dict:
    fingerprint = digest({"previous_hash": state["head_hash"], "event": event})
    row = {
        "sequence": len(state["events"]) + 1,
        "event_hash": fingerprint,
        "event": event,
    }
    connection.execute(
        "INSERT INTO events VALUES (?, ?, ?, ?)",
        (row["sequence"], state["head_hash"], fingerprint, _json(event)),
    )
    return row


def _entry_at(state: dict, row: dict) -> dict:
    if row["event"]["kind"] == "RECORD":
        return row["event"]["entry"]
    reference = row["event"]["revoked_revision"]
    return next(
        previous["event"]["entry"]
        for previous in state["events"]
        if previous["event_hash"] == reference
    )


def record(
    path: Path,
    entry: dict,
    source_root: Path,
    *,
    expected_head: str,
    supersedes: str | None = None,
) -> dict:
    """Append a reviewed/proposed entry; require exact identity for revisions."""
    _validate(entry, read_json(SCHEMA))
    if (entry["scope"] == "CLIENT") != (entry["client_id"] is not None):
        raise ContractError("Only a client override has a client identity")
    if entry["valid_until"] is not None and entry["valid_until"] < entry["valid_from"]:
        raise ContractError("Catalog validity interval is reversed")
    if (
        entry["review"]["status"] == "CONFIRMED"
        and entry["tax_class"]["treatment"] is None
    ):
        raise ContractError("Cannot confirm a mapping with unknown treatment")
    treatment = entry["tax_class"]["treatment"]
    if treatment is not None and TREATMENTS[treatment][0] != entry["side"]:
        raise ContractError("Catalog treatment and register side disagree")
    deduction = entry["tax_class"]["deductibility"]
    percent = deduction["percent"]
    if (deduction["mode"] in {"UNKNOWN", "CASE_SPECIFIC"}) != (percent is None):
        raise ContractError(
            "A fixed deduction percentage requires an explicit fixed mode"
        )
    if percent is not None:
        amount = Decimal(percent)
        if (
            not 0 <= amount <= 100
            or (deduction["mode"] == "FULL" and amount != 100)
            or (deduction["mode"] == "NONE" and amount != 0)
            or (deduction["mode"] == "PARTIAL" and not 0 < amount < 100)
        ):
            raise ContractError("Catalog deduction mode and percentage disagree")
    if (
        entry["tax_class"]["vat_rate"] is not None
        and Decimal(entry["tax_class"]["vat_rate"]) > 100
    ):
        raise ContractError("Invalid percentage")
    check_references(entry["sources"], entry["evidence"], source_root)
    if not any(
        re.search(r"(?<!\w)" + re.escape(entry["code"]) + r"(?!\w)", ref["quote"])
        for ref in entry["evidence"]
    ):
        raise ContractError("Catalog code is absent from the quoted evidence")
    if entry["scope"] == "STUDIO" and any(
        source["visibility"] == "PRIVATE_CASE" for source in entry["sources"]
    ):
        raise ContractError(
            "Studio entries require a reviewed studio reference, not private client evidence"
        )
    if entry["scope"] == "CENTRAL":
        if any(source["visibility"] != "PUBLIC" for source in entry["sources"]):
            raise ContractError(
                "Central catalog entries cannot include private case sources"
            )
        if entry["curator_review"] is None or entry["disclosure_review"] is None:
            raise ContractError(
                "Central entries require attributed curator and disclosure reviews"
            )
        _validate(entry["curator_review"], REVIEW_SCHEMA)
        _validate(entry["disclosure_review"], REVIEW_SCHEMA)
    elif entry["curator_review"] is not None or entry["disclosure_review"] is not None:
        raise ContractError("Curator/disclosure fields belong to central entries")
    with closing(_connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = _history(connection)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before recording a decision")
        previous = _latest(state).get(entry["entry_id"])
        if previous is None and supersedes is not None:
            raise ContractError("A new entry cannot supersede a foreign revision")
        if previous is not None:
            if previous["event_hash"] != supersedes:
                raise ContractError(
                    "Revision must explicitly supersede the latest entry event"
                )
            if _identity(_entry_at(state, previous)) != _identity(entry):
                raise ContractError(
                    "A revision cannot change its scope, client, software, side or code"
                )
        return _append(
            connection,
            state,
            {
                "kind": "RECORD",
                "entry_id": entry["entry_id"],
                "entry": entry,
                "source_objects": _capture_objects(path, entry["sources"], source_root),
                "supersedes": supersedes,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def revoke(
    path: Path,
    entry_id: str,
    review: dict,
    *,
    expected_head: str,
    revision: str,
    allow_fallback: bool = False,
) -> dict:
    """Revoke an exact current revision without deleting it or restoring old ones."""
    _validate(review, REVIEW_SCHEMA)
    if not isinstance(allow_fallback, bool):
        raise ContractError("Fallback permission must be explicit boolean")
    with closing(_connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = _history(connection)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before revocation")
        current = _latest(state).get(entry_id)
        if (
            current is None
            or current["event_hash"] != revision
            or current["event"]["kind"] != "RECORD"
        ):
            raise ContractError(
                "Revoke the exact current record, not an old or already revoked revision"
            )
        return _append(
            connection,
            state,
            {
                "kind": "REVOKE",
                "entry_id": entry_id,
                "revoked_revision": revision,
                "allow_fallback": allow_fallback,
                "review": review,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def lookup(
    path: Path,
    *,
    studio_id: str,
    client_id: str,
    software: dict,
    side: str,
    code: str,
    on_date: str,
) -> dict:
    """Resolve exact scope precedence; return a reviewable candidate, never approval."""
    state = history(path)
    return _lookup(
        state,
        studio_id=studio_id,
        client_id=client_id,
        software=software,
        side=side,
        code=code,
        on_date=on_date,
    )


def _lookup(
    state: dict,
    *,
    studio_id: str,
    client_id: str,
    software: dict,
    side: str,
    code: str,
    on_date: str,
) -> dict:
    if date.fromisoformat(on_date).isoformat() != on_date:
        raise ContractError("Catalog date must use YYYY-MM-DD")
    metadata = state["metadata"]
    if studio_id != metadata["studio_id"]:
        raise ContractError("Catalog belongs to a different declared studio")
    candidates: dict[str, list[dict]] = {
        scope: [] for scope in ("CLIENT", "STUDIO", "CENTRAL")
    }
    for row in _latest(state).values():
        entry = _entry_at(state, row)
        if (entry["software"], entry["side"], entry["code"]) != (software, side, code):
            continue
        if entry["scope"] == "CLIENT" and entry["client_id"] != client_id:
            continue
        if entry["valid_from"] > on_date or (
            entry["valid_until"] and on_date > entry["valid_until"]
        ):
            continue
        if row["event"]["kind"] == "REVOKE" and row["event"]["allow_fallback"]:
            continue
        candidates[entry["scope"]].append({**row, "entry": entry})
    answer: dict = {
        "catalog_id": metadata["catalog_id"],
        "studio_id": studio_id,
        "head_hash": state["head_hash"],
        "status": "UNKNOWN_CODE",
        "scope": None,
        "candidate": None,
        "alternatives": [],
        "case_confirmation_required": True,
        "identity_authenticated": False,
    }
    resolved = {
        row["event"]["dispute_hash"]
        for row in state["events"]
        if row["event"]["kind"] == "RESOLVE_DISPUTE"
    }
    answer["open_disputes"] = [
        row["event_hash"]
        for row in state["events"]
        if row["event"]["kind"] == "DISPUTE"
        and row["event_hash"] not in resolved
        and (
            row["event"]["key"]["software"],
            row["event"]["key"]["side"],
            row["event"]["key"]["code"],
        )
        == (software, side, code)
    ]
    for scope, rows in candidates.items():
        if not rows:
            continue
        answer["scope"] = scope
        answer["alternatives"] = [
            {
                "revision_hash": row["event_hash"],
                "entry": row["entry"],
                "source_objects": row["event"].get("source_objects", []),
            }
            for row in rows
        ]
        if any(row["event"]["kind"] == "REVOKE" for row in rows):
            answer["status"] = "REVOKED_OVERRIDE"
        elif len({digest(row["entry"]["tax_class"]) for row in rows}) > 1:
            answer["status"] = "CONFLICT"
        elif any(row["entry"]["review"]["status"] != "CONFIRMED" for row in rows):
            answer["status"] = "UNCONFIRMED"
        elif any(
            Decimal(row["entry"]["confidence"]["value"])
            < Decimal(metadata["minimum_confidence"])
            for row in rows
        ):
            answer["status"] = "LOW_CONFIDENCE"
        else:
            answer["status"] = "CANDIDATE_FOR_CASE_REVIEW"
            # Equivalent tax classes retain every source/revision; no timestamp wins a conflict.
            answer["candidate"] = rows[0]["entry"]["tax_class"]
        break
    if answer["open_disputes"]:
        answer.update(status="CURATOR_DISPUTE_OPEN", candidate=None)
    answer["binding"] = (
        {
            "revision_hashes": sorted(
                item["revision_hash"] for item in answer["alternatives"]
            ),
            "tax_class_hash": digest(answer["candidate"]),
        }
        if answer["status"] == "CANDIDATE_FOR_CASE_REVIEW"
        else None
    )
    return answer


def dispute(
    path: Path,
    reference_entry: dict,
    source_root: Path,
    review: dict,
    *,
    expected_head: str,
) -> dict:
    """Record an evidenced code conflict requiring a curator across catalog scopes."""
    _validate(reference_entry, read_json(SCHEMA))
    _validate(review, REVIEW_SCHEMA)
    check_references(
        reference_entry["sources"], reference_entry["evidence"], source_root
    )
    with closing(_connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = _history(connection)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before recording a dispute")
        return _append(
            connection,
            state,
            {
                "kind": "DISPUTE",
                "key": {
                    key: reference_entry[key] for key in ("software", "side", "code")
                },
                "sources": reference_entry["sources"],
                "source_objects": _capture_objects(
                    path, reference_entry["sources"], source_root
                ),
                "evidence": reference_entry["evidence"],
                "review": review,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def resolve_dispute(
    path: Path,
    dispute_hash: str,
    curator_review: dict,
    *,
    expected_head: str,
    selected_revision: str,
) -> dict:
    """Close an exact dispute through an attributed curator's current central entry."""
    _validate(curator_review, REVIEW_SCHEMA)
    with closing(_connect(path, write=True)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        state = _history(connection)
        if state["head_hash"] != expected_head:
            raise ContractError("Catalog changed; reload before resolving a dispute")
        target = next(
            (
                row["event"]
                for row in state["events"]
                if row["event_hash"] == dispute_hash
                and row["event"]["kind"] == "DISPUTE"
            ),
            None,
        )
        if target is None or any(
            row["event"]["kind"] == "RESOLVE_DISPUTE"
            and row["event"]["dispute_hash"] == dispute_hash
            for row in state["events"]
        ):
            raise ContractError("Select an unresolved catalog dispute")
        selected = next(
            (
                row
                for row in _latest(state).values()
                if row["event_hash"] == selected_revision
                and row["event"]["kind"] == "RECORD"
            ),
            None,
        )
        if selected is None:
            raise ContractError("Curator must identify a current central revision")
        entry = selected["event"]["entry"]
        if (
            entry["scope"] != "CENTRAL"
            or entry["review"]["status"] != "CONFIRMED"
            or {key: entry[key] for key in ("software", "side", "code")}
            != target["key"]
        ):
            raise ContractError(
                "The curator revision must match the disputed vendor, version, side and code"
            )
        return _append(
            connection,
            state,
            {
                "kind": "RESOLVE_DISPUTE",
                "dispute_hash": dispute_hash,
                "selected_revision": selected_revision,
                "curator_review": curator_review,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def assess_case_mappings(
    case: dict, catalog_path: Path | None, blockers: list[str]
) -> list[dict]:
    """Recheck catalog revisions over the entire quarter before using case mappings."""
    context = case["catalog_context"]
    bound = [
        mapping
        for mapping in case["mappings"]
        if mapping["catalog_binding"] is not None
    ]
    if context is None:
        if bound:
            raise ContractError(
                "Catalog-bound mappings require their studio/catalog context"
            )
        return []
    if catalog_path is None:
        blockers.append("CATALOG_NOT_AVAILABLE")
        return []
    state = history(catalog_path)
    if (state["metadata"]["catalog_id"], state["metadata"]["studio_id"]) != (
        context["catalog_id"],
        context["studio_id"],
    ):
        raise ContractError(
            "The supplied catalog does not match the reviewed case context"
        )
    start_month, end_month = (case["quarter"] - 1) * 3 + 1, case["quarter"] * 3
    start = date(case["tax_year"], start_month, 1)
    end = date(
        case["tax_year"], end_month, calendar.monthrange(case["tax_year"], end_month)[1]
    )
    assessments = []
    for mapping in bound:
        dates = {start, end}
        for row in _latest(state).values():
            entry = _entry_at(state, row)
            if (entry["software"], entry["side"], entry["code"]) != (
                case["software"],
                mapping["side"],
                mapping["code"],
            ):
                continue
            if entry["scope"] == "CLIENT" and entry["client_id"] != case["client_id"]:
                continue
            since = date.fromisoformat(entry["valid_from"])
            if start < since < end:
                dates.add(since)
            if entry["valid_until"] is not None:
                until = date.fromisoformat(entry["valid_until"])
                if start <= until < end:
                    dates.add(until + timedelta(days=1))
        checks = []
        for when in sorted(dates):
            check = _lookup(
                state,
                studio_id=context["studio_id"],
                client_id=case["client_id"],
                software=case["software"],
                side=mapping["side"],
                code=mapping["code"],
                on_date=when.isoformat(),
            )
            binding = {
                "revision_hashes": sorted(
                    item["revision_hash"] for item in check["alternatives"]
                ),
                "tax_class_hash": (
                    digest(check["candidate"])
                    if check["candidate"] is not None
                    else None
                ),
            }
            checks.append(
                {
                    "on_date": when.isoformat(),
                    "status": check["status"],
                    "scope": check["scope"],
                    "binding": binding,
                    "candidate": check["candidate"],
                    "alternatives": check["alternatives"],
                }
            )
        usable = all(
            check["status"] == "CANDIDATE_FOR_CASE_REVIEW"
            and check["binding"] == mapping["catalog_binding"]
            and check["candidate"]["treatment"] == mapping["treatment"]
            for check in checks
        )
        if not usable:
            blockers.append(
                f"CATALOG_MAPPING_STALE_OR_UNRESOLVED:{mapping['side']}:{mapping['code']}"
            )
        assessments.append(
            {
                "side": mapping["side"],
                "code": mapping["code"],
                "catalog_id": context["catalog_id"],
                "head_hash": state["head_hash"],
                "status": "CURRENT" if usable else "REVIEW_REQUIRED",
                "checks": checks,
            }
        )
    return assessments


def main(argv: list[str] | None = None) -> int:
    """Manage a selected local catalog; all results are JSON and nothing is sent."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--studio-id", required=True)
    init.add_argument("--minimum-confidence", required=True)
    add = sub.add_parser("record")
    add.add_argument("--entry", type=Path, required=True)
    add.add_argument("--source-root", type=Path, required=True)
    add.add_argument("--expected-head", required=True)
    add.add_argument("--supersedes")
    remove = sub.add_parser("revoke")
    remove.add_argument("--entry-id", required=True)
    remove.add_argument("--review", type=Path, required=True)
    remove.add_argument("--expected-head", required=True)
    remove.add_argument("--revision", required=True)
    remove.add_argument("--allow-fallback", action="store_true")
    find = sub.add_parser("lookup")
    find.add_argument("--request", type=Path, required=True)
    listing = sub.add_parser("history")
    flag = sub.add_parser("dispute")
    flag.add_argument("--entry", type=Path, required=True)
    flag.add_argument("--source-root", type=Path, required=True)
    flag.add_argument("--review", type=Path, required=True)
    flag.add_argument("--expected-head", required=True)
    resolve = sub.add_parser("resolve-dispute")
    resolve.add_argument("--dispute", required=True)
    resolve.add_argument("--curator-review", type=Path, required=True)
    resolve.add_argument("--selected-revision", required=True)
    resolve.add_argument("--expected-head", required=True)
    for command in (init, add, remove, find, listing, flag, resolve):
        command.add_argument("--catalog", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Refuse to mutate the catalog if the requested receipt cannot be created.
    with args.output.open("x", encoding="utf-8") as receipt:
        args.output.chmod(0o600)
        if args.command == "init":
            result = create_catalog(
                args.catalog, args.studio_id, args.minimum_confidence
            )
        elif args.command == "record":
            result = record(
                args.catalog,
                read_json(args.entry),
                args.source_root,
                expected_head=args.expected_head,
                supersedes=args.supersedes,
            )
        elif args.command == "revoke":
            result = revoke(
                args.catalog,
                args.entry_id,
                read_json(args.review),
                expected_head=args.expected_head,
                revision=args.revision,
                allow_fallback=args.allow_fallback,
            )
        elif args.command == "lookup":
            result = lookup(args.catalog, **read_json(args.request))
        elif args.command == "dispute":
            result = dispute(
                args.catalog,
                read_json(args.entry),
                args.source_root,
                read_json(args.review),
                expected_head=args.expected_head,
            )
        elif args.command == "resolve-dispute":
            result = resolve_dispute(
                args.catalog,
                args.dispute,
                read_json(args.curator_review),
                expected_head=args.expected_head,
                selected_revision=args.selected_revision,
            )
        else:
            result = history(args.catalog)
        receipt.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    logging.info("LIPE catalog %s: %s", args.command, args.output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
