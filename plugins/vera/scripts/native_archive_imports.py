"""User-selected file bytes into the unchanged, owned Studio Archive importer.

Fixed hashes, chunk receipts and ownership enforce mechanically verifiable
transport integrity. They never classify documents or choose their role.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_archive_navigation import (
    archive_module,
    engagement_scope,
    fingerprint,
    preparation_catalogue,
    reviewer,
)

__all__ = ["audit_engagement", "dispatch"]

CHUNK_BYTES = 65536
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_NOTE_BYTES = 256 * 1024


def owner(args: dict) -> list[str]:
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        args["client_id"],
        args["engagement_id"],
    ]


def _directory(core: Any, folder: Path, engagement: str) -> Path:
    directory = core.ledger._engagement_root(folder, engagement) / ".native-imports"
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("Native imports cannot use linked directories")
    return directory


def _read(path: Path) -> dict:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 4_000_000
    ):
        raise ValueError("Native import receipt is missing or invalid")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Native import receipt must be an object")
    return value


def _sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Native import bytes must be an ordinary single-link file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def note_fields(value: Any, *, complete: bool = False) -> dict:
    """Validate only literal shape, safe file names and bounded transport bytes."""
    if not isinstance(value, dict) or set(value) != {"name", "reported_by", "text"}:
        raise ValueError("Expected a literal note, file name and declared attribution")
    if any(not isinstance(value[k], str) for k in value):
        raise ValueError("Literal note fields must be strings")
    if (
        len(value["reported_by"]) > 500
        or len(value["text"].encode("utf-8")) > MAX_NOTE_BYTES
    ):
        raise ValueError(
            "Literal note exceeds native capture limit; import the complete original file instead"
        )
    if value["name"]:
        descriptor(
            {
                "name": value["name"],
                "byte_count": 1,
                "sha256": "0" * 64,
                "role": "source",
            }
        )
        if not value["name"].endswith(".json"):
            raise ValueError("Captured original notes use a JSON file name")
    if complete and (not value["name"] or not value["text"].strip()):
        raise ValueError("Name and literal original note are required")
    return value


def note_draft(home: Path, identity: list[str]) -> dict:
    """Recover only this owner's literal draft; never restore confirmation."""
    path = home / "note-draft.json"
    if path.is_symlink():
        raise ValueError("Literal note draft cannot be a linked file")
    if not path.exists():
        return {
            "draft_revision": "",
            "fields": {"name": "appunti-colloquio.json", "reported_by": "", "text": ""},
        }
    value = _read(path)
    if value["owner"] != identity:
        raise PermissionError("Literal note draft belongs to another owner")
    return {"draft_revision": _sha(path), "fields": note_fields(value["fields"])}


def note_source(base: Path, manifest: dict) -> str:
    """Replay the original captured JSON and its exact bytes, not a rewritten note."""
    path = base / "original-note.json"
    if _sha(path) != manifest["note_sha256"]:
        raise ValueError("Captured original note changed")
    value = _read(path)
    if (
        value.get("schema_version") != "vera.user_statement.v1"
        or value.get("kind") != "user_statement"
        or value["capture"]["owner"] != manifest["owner"]
        or value["capture"]["identity_authenticated"] is not False
    ):
        raise ValueError("Captured note provenance differs from its owner receipt")
    chosen = manifest["file"]
    note_fields(
        {
            "name": chosen["name"],
            "reported_by": value["reported_by"],
            "text": value["text"],
        },
        complete=True,
    )
    if (
        _sha(path) != chosen["sha256"]
        or path.stat().st_size != chosen["byte_count"]
        or chosen["role"] != "source"
    ):
        raise ValueError("Captured original note differs from selected transport bytes")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["note_draft_sha256"]):
        raise ValueError("Captured note requires an exact draft revision")
    return path.read_text(encoding="utf-8")


def descriptor(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "name",
        "byte_count",
        "sha256",
        "role",
    }:
        raise ValueError("Choose the exact file name, byte count, digest and role")
    name, count = value["name"], value["byte_count"]
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 200
        or name in {".", "..", "receipt.json"}
        or any(x in name for x in ("/", "\\", "\x00"))
        or any(ord(x) < 32 for x in name)
    ):
        raise ValueError("Select an ordinary file name, never a filesystem path")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not 1 <= count <= MAX_FILE_BYTES
    ):
        raise ValueError(
            "Native file transport supports 1 byte to 64 MiB; larger originals use the maintained chat import"
        )
    if not isinstance(value["sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["sha256"]
    ):
        raise ValueError("Expected the complete selected file SHA-256")
    if value["role"] not in {"journal", "source", "support"}:
        raise ValueError("Explicitly choose journal, source or support")
    return value


def inspect_upload(base: Path, core: Any, folder: Path, engagement: str) -> dict:
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ValueError("Native import directories cannot use symbolic links")
    if not re.fullmatch(r"upload-[0-9a-f]{64}", base.name):
        raise ValueError("Invalid import identity")
    manifest = _read(base / "manifest.json")
    chosen = descriptor(manifest["file"])
    if "note_sha256" in manifest:
        note_source(base, manifest)
    if manifest["owner"][2:] != [
        core.ledger.load_client_manifest(folder)["client_id"],
        engagement,
    ] or base.parent.name != fingerprint(manifest["owner"]):
        raise PermissionError("Import belongs to another owner or engagement")
    begin = _read(base / "begin.json")
    if (
        begin["manifest_sha256"] != _sha(base / "manifest.json")
        or begin.get("result", {}).get("upload_ref") != base.name
    ):
        raise ValueError("Import begin receipt requires recovery")
    state = _read(base / "state.json")
    cursor, known = 0, set()
    for row in state["chunks"]:
        offset, count = row["offset"], row["byte_count"]
        if (
            offset != cursor
            or count != min(CHUNK_BYTES, chosen["byte_count"] - cursor)
            or count <= 0
        ):
            raise ValueError("Invalid retained import chunk sequence")
        name = f"chunk-{offset:08x}"
        path = base / name
        if path.stat().st_size != count or _sha(path) != row["sha256"]:
            raise ValueError("Retained import chunk changed")
        known.add(name)
        cursor += count
    pending = []
    for path in base.glob("chunk-request-*.json"):
        request = _read(path)
        offset = request["offset"]
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 0
            or path.name != f"chunk-request-{offset:08x}.json"
        ):
            raise ValueError("Invalid chunk request identity")
        row = next((r for r in state["chunks"] if r["offset"] == offset), None)
        if "result" not in request:
            pending.append(offset)
            continue
        if (
            row is None
            or request["sha256"] != row["sha256"]
            or request["result"]
            != {"upload_ref": base.name, "received": offset + row["byte_count"]}
        ):
            raise ValueError("Chunk receipt differs from retained bytes")
    for row in state["chunks"]:
        if not (base / f"chunk-request-{row['offset']:08x}.json").exists():
            raise ValueError("Missing completed chunk receipt")
    orphans = {
        p.name for p in base.glob("chunk-*") if not p.name.startswith("chunk-request-")
    } - known
    if any(not re.fullmatch(r"chunk-[0-9a-f]{8}", name) for name in orphans):
        raise ValueError("Unknown retained import chunks")
    allowed_pending = {f"chunk-{offset:08x}" for offset in pending}
    if orphans - allowed_pending or len(pending) > 1:
        raise ValueError("Orphaned import bytes require specialist recovery")
    completion = (
        _read(base / "import.json") if (base / "import.json").exists() else None
    )
    if completion is not None and completion["manifest_sha256"] != _sha(
        base / "manifest.json"
    ):
        raise ValueError("Import intent changed")
    if completion and "result" in completion:
        result = completion["result"]
        receipt = core.ledger.load_input_receipt(folder, engagement, result["input_id"])
        if (
            any(receipt[key] != chosen[key] for key in ("sha256", "byte_count", "role"))
            or chosen["name"] not in receipt["imported_names"]
            or receipt["content_sha256"] != result["receipt_sha256"]
        ):
            raise ValueError("Conserved import receipt changed")
        status = "imported"
    elif completion:
        status = "import_recovery"
    elif pending:
        status = "chunk_recovery"
    else:
        status = "ready" if cursor == chosen["byte_count"] else "receiving"
    if completion and (cursor != chosen["byte_count"] or pending):
        raise ValueError("Import intent requires complete retained source bytes")
    return {
        "upload_ref": base.name,
        "file": chosen,
        "received": cursor,
        "status": status,
        "pending_offset": pending[0] if pending else None,
        "owner": manifest["owner"],
        **(
            {
                "origin": "user_statement",
                "note_draft_revision": manifest["note_draft_sha256"],
            }
            if "note_sha256" in manifest
            else {}
        ),
    }


def audit_engagement(core: Any, folder: Path, engagement: str) -> dict:
    """Inspect every actor's durable intent, without adopting unreceipted files."""
    directory = _directory(core, folder, engagement)
    rows = [
        inspect_upload(base, core, folder, engagement)
        for base in sorted(directory.glob("*/upload-*"))
    ]
    return {
        "rows": rows,
        "recovery_required": any(
            row["status"] in {"import_recovery", "chunk_recovery"} for row in rows
        ),
    }


def dispatch(root: Path, tool: str, args: dict, api: Any) -> dict:
    """Receive explicitly chosen bytes and import with the maintained owner/ledger gate."""
    core = archive_module(root)
    folder, engagement = engagement_scope(
        core, args["client_id"], args["engagement_id"]
    )
    directory = _directory(core, folder, args["engagement_id"])
    identity = owner(args)
    home = directory / fingerprint(identity)
    if any(p.is_symlink() for p in (home, *home.parents)):
        raise ValueError("Native import owner directory cannot be linked")
    audit = audit_engagement(core, folder, args["engagement_id"])
    current = preparation_catalogue(root, args)
    if tool == "vera_workspace_archive_import_note_read":
        draft = note_draft(home, identity)
        result = {
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "engagement_label": engagement["label"],
            "scope_revision": current["scope_revision"],
            "can_write": reviewer() and engagement["status"] == "open",
            "draft": draft,
            "max_note_bytes": MAX_NOTE_BYTES,
            "retained": [
                {k: v for k, v in row.items() if k != "owner"}
                for row in audit["rows"]
                if row["owner"] == identity
                and row.get("note_draft_revision") == draft["draft_revision"]
            ],
        }
        if args.get("upload_ref"):
            reference = args["upload_ref"]
            if not re.fullmatch(r"upload-[0-9a-f]{64}", reference):
                raise ValueError("Choose an exact retained literal note")
            item = inspect_upload(home / reference, core, folder, args["engagement_id"])
            if item["owner"] != identity or item.get("origin") != "user_statement":
                raise PermissionError(
                    "Select this owner's exact captured original note"
                )
            result.update(
                upload={k: v for k, v in item.items() if k != "owner"},
                source_text=note_source(
                    home / reference, _read(home / reference / "manifest.json")
                ),
            )
        return result
    if tool == "vera_workspace_archive_import_setup":
        offset = args.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("Invalid import page offset")
        rows = [
            {k: v for k, v in row.items() if k != "owner"}
            for row in audit["rows"]
            if row["owner"] == identity
        ]
        return {
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "engagement_label": engagement["label"],
            "scope_revision": current["scope_revision"],
            "can_import": reviewer() and engagement["status"] == "open",
            "recovery_required": audit["recovery_required"],
            "rows": rows[offset : offset + 30],
            "offset": offset,
            "total": len(rows),
            "has_more": offset + 30 < len(rows),
            "chunk_bytes": CHUNK_BYTES,
            "max_file_bytes": MAX_FILE_BYTES,
        }
    if (
        tool == "vera_workspace_archive_import_finish"
        and reviewer()
        and args.get("confirmed") is True
    ):
        reference = args["upload_ref"]
        if not re.fullmatch(r"upload-[0-9a-f]{64}", reference):
            raise ValueError("Choose an exact retained import")
        retained = inspect_upload(home / reference, core, folder, args["engagement_id"])
        if retained["owner"] == identity and retained["status"] == "imported":
            # Replay the verified outcome even though this import changed the
            # input catalogue itself. This branch performs no new write.
            return _read(home / reference / "import.json")["result"]
    if (
        not reviewer()
        or engagement["status"] != "open"
        or args.get("confirmed") is not True
    ):
        raise PermissionError(
            "Import requires an explicit reviewer choice in an open engagement"
        )
    if args["scope_revision"] != current["scope_revision"]:
        raise ValueError(
            "Engagement inputs changed; reopen and confirm this exact import"
        )
    with api.write_lock(
        core.ledger._engagement_root(folder, args["engagement_id"]) / "import-write"
    ):
        fresh = preparation_catalogue(root, args)
        if (
            fresh["scope_revision"] != current["scope_revision"]
            or fresh["engagement_status"] != "open"
        ):
            raise ValueError("Archive import authority changed")
        audit = audit_engagement(core, folder, args["engagement_id"])
        if tool in {
            "vera_workspace_archive_import_note_store",
            "vera_workspace_archive_import_note_clear",
        }:
            saved = note_draft(home, identity)
            if args["expected_draft_revision"] != saved["draft_revision"]:
                raise ValueError(
                    "Literal note draft changed; reopen before replacing it"
                )
            if tool.endswith("_clear"):
                (home / "note-draft.json").unlink(missing_ok=True)
            else:
                chosen_note = note_fields(args["fields"])
                home.mkdir(parents=True, exist_ok=True, mode=0o700)
                api.atomic_json(
                    home / "note-draft.json",
                    {
                        "owner": identity,
                        "fields": chosen_note,
                        "revision_nonce": secrets.token_hex(16),
                    },
                )
            return {
                "client_id": args["client_id"],
                "engagement_id": args["engagement_id"],
                "scope_revision": fresh["scope_revision"],
                "draft": note_draft(home, identity),
            }
        captured = None
        if tool == "vera_workspace_archive_import_note_begin":
            saved = note_draft(home, identity)
            if args["expected_draft_revision"] != saved["draft_revision"]:
                raise ValueError(
                    "Literal note draft changed; reopen before conserving it"
                )
            values = note_fields(saved["fields"], complete=True)
            reference = "upload-" + fingerprint([identity, args["idempotency_key"]])
            for row in audit["rows"]:
                if (
                    row["owner"] == identity
                    and row.get("note_draft_revision") == saved["draft_revision"]
                ):
                    if row["upload_ref"] != reference:
                        raise ValueError(
                            "This literal note already has an exact retained import; reopen that source instead of duplicating it"
                        )
            if (home / reference).exists():
                manifest = _read(home / reference / "manifest.json")
                if manifest.get("note_draft_sha256") != saved["draft_revision"]:
                    raise ValueError(
                        "Note request key belongs to a different literal draft"
                    )
                item = inspect_upload(
                    home / reference, core, folder, args["engagement_id"]
                )
                return {
                    **{k: v for k, v in item.items() if k != "owner"},
                    "source_text": note_source(home / reference, manifest),
                }
            captured = {
                "schema_version": "vera.user_statement.v1",
                "kind": "user_statement",
                "reported_by": values["reported_by"],
                "text": values["text"],
                "capture": {
                    "owner": identity,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "identity_authenticated": False,
                },
                "limitations": "User-provided statement and capture metadata; not independent evidence of truth, adoption or operating effectiveness.",
            }
            source_bytes = json.dumps(captured, ensure_ascii=False).encode("utf-8")
            args = {
                **args,
                "file": {
                    "name": values["name"],
                    "byte_count": len(source_bytes),
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "role": "source",
                },
            }
            tool = "vera_workspace_archive_import_begin"
        if tool == "vera_workspace_archive_import_begin":
            chosen = descriptor(args["file"])
            key = args["idempotency_key"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
                raise ValueError("Invalid import request key")
            reference = "upload-" + fingerprint([identity, key])
            base = home / reference
            if base.exists():
                manifest = _read(base / "manifest.json")
                if manifest["owner"] != identity or manifest["file"] != chosen:
                    raise ValueError(
                        "Import request key belongs to different selected bytes"
                    )
                return {
                    k: v
                    for k, v in inspect_upload(
                        base, core, folder, args["engagement_id"]
                    ).items()
                    if k != "owner"
                }
            if audit["recovery_required"]:
                raise ValueError(
                    "Resolve the retained interrupted import before starting another"
                )
            base.mkdir(mode=0o700, parents=True)
            if captured is not None:
                api.atomic_json(base / "original-note.json", captured)
            api.atomic_json(
                base / "manifest.json",
                {
                    "owner": identity,
                    "file": chosen,
                    "request_key": key,
                    "transport": (
                        "literal user note captured with unverified attribution; no original OS path"
                        if captured is not None
                        else "explicit browser-selected bytes; original OS path unavailable"
                    ),
                    **(
                        {
                            "note_sha256": _sha(base / "original-note.json"),
                            "note_draft_sha256": saved["draft_revision"],
                        }
                        if captured is not None
                        else {}
                    ),
                },
            )
            api.atomic_json(base / "state.json", {"chunks": []})
            result = {"upload_ref": reference, "received": 0}
            api.atomic_json(
                base / "begin.json",
                {"manifest_sha256": _sha(base / "manifest.json"), "result": result},
            )
            return {
                **result,
                "file": chosen,
                "status": "receiving",
                **(
                    {
                        "origin": "user_statement",
                        "source_text": note_source(base, _read(base / "manifest.json")),
                    }
                    if captured is not None
                    else {}
                ),
            }
        reference = args["upload_ref"]
        if not re.fullmatch(r"upload-[0-9a-f]{64}", reference):
            raise ValueError("Choose an exact retained import")
        base = home / reference
        item = inspect_upload(base, core, folder, args["engagement_id"])
        if item["owner"] != identity:
            raise PermissionError("Import belongs to another actor")
        recovering = args.get("recover", False)
        if recovering is not True and item["status"] in {
            "import_recovery",
            "chunk_recovery",
        }:
            raise ValueError(
                "Explicitly confirm recovery of this exact interrupted import"
            )
        if any(
            row["status"] in {"import_recovery", "chunk_recovery"}
            and row["upload_ref"] != reference
            for row in audit["rows"]
        ):
            raise ValueError("Another interrupted import requires recovery")
        state = _read(base / "state.json")
        if tool == "vera_workspace_archive_import_chunk":
            if item["status"] in {"imported", "import_recovery"}:
                raise ValueError("This import no longer accepts chunks")
            offset = args["offset"]
            encoded = args["data"]
            if (
                not isinstance(offset, int)
                or isinstance(offset, bool)
                or offset < 0
                or not isinstance(encoded, str)
                or len(encoded) > 4 * ((CHUNK_BYTES + 2) // 3)
            ):
                raise ValueError("Invalid bounded import chunk")
            data = base64.b64decode(encoded, validate=True)
            if (
                base64.b64encode(data).decode() != encoded
                or len(data) != min(CHUNK_BYTES, item["file"]["byte_count"] - offset)
                or not data
            ):
                raise ValueError(
                    "Choose an exact complete next chunk without truncation"
                )
            checksum = hashlib.sha256(data).hexdigest()
            intent = base / f"chunk-request-{offset:08x}.json"
            result = {"upload_ref": reference, "received": offset + len(data)}
            if intent.exists():
                saved = _read(intent)
                if saved["sha256"] != checksum:
                    raise ValueError("Chunk retry contains different bytes")
                if "result" in saved:
                    return saved["result"]
                if not recovering or item["pending_offset"] != offset:
                    raise ValueError("Explicit same-chunk recovery required")
            elif offset != item["received"] or item["status"] == "chunk_recovery":
                raise ValueError("Concurrent or out-of-order import chunk")
            else:
                api.atomic_json(intent, {"offset": offset, "sha256": checksum})
            path = base / f"chunk-{offset:08x}"
            if path.exists():
                if _sha(path) != checksum or path.stat().st_size != len(data):
                    raise ValueError("Interrupted chunk contains different bytes")
            else:
                with path.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            if not any(row["offset"] == offset for row in state["chunks"]):
                state["chunks"].append(
                    {"offset": offset, "byte_count": len(data), "sha256": checksum}
                )
                api.atomic_json(base / "state.json", state)
            api.atomic_json(
                intent, {"offset": offset, "sha256": checksum, "result": result}
            )
            return result
        if tool != "vera_workspace_archive_import_finish":
            raise ValueError("Unknown native import action")
        if item["status"] == "imported":
            return _read(base / "import.json")["result"]
        if (
            item["received"] != item["file"]["byte_count"]
            or item["status"] == "chunk_recovery"
        ):
            raise ValueError("Complete every selected byte before importing")
        intent = base / "import.json"
        source_dir = base / "source"
        source_dir.mkdir(mode=0o700, exist_ok=True)
        source = source_dir / item["file"]["name"]
        if not source.exists():
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=source_dir, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    for row in state["chunks"]:
                        stream.write((base / f"chunk-{row['offset']:08x}").read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                if (
                    temporary.stat().st_size != item["file"]["byte_count"]
                    or _sha(temporary) != item["file"]["sha256"]
                ):
                    raise ValueError(
                        "Selected complete file hash differs from staged bytes"
                    )
                temporary.replace(source)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if (
            _sha(source) != item["file"]["sha256"]
            or source.stat().st_size != item["file"]["byte_count"]
        ):
            raise ValueError("Selected complete file hash differs from staged bytes")
        if not intent.exists():
            api.atomic_json(intent, {"manifest_sha256": _sha(base / "manifest.json")})
        # The public importer deduplicates exact SHA/role and preserves filename
        # aliases. Explicit replay of this same durable intent cannot double it.
        imported = core.import_studio_client_document(
            args["client_id"],
            source,
            item["file"]["role"],
            engagement_id=args["engagement_id"],
        )
        receipt = imported["input_receipt"]
        result = {
            "status": imported["status"],
            "client_id": args["client_id"],
            "engagement_id": args["engagement_id"],
            "upload_ref": reference,
            "input_id": receipt["input_id"],
            "name": item["file"]["name"],
            "sha256": receipt["sha256"],
            "byte_count": receipt["byte_count"],
            "role": receipt["role"],
            "receipt_sha256": receipt["content_sha256"],
            "workflow_executed": False,
            "run_started": False,
        }
        api.atomic_json(
            intent, {"manifest_sha256": _sha(base / "manifest.json"), "result": result}
        )
        return result
